"""The Super Nintendo's sound chip: registers, envelopes and volume.

The S-DSP synthesizes nothing on its own: it plays samples. Eight voices,
each reading a sample from the SPC700's memory at whatever speed it is
asked, with an ADSR envelope and per-channel volume. The pitch of the note
comes from the reading speed, so a single sample serves for every note.

So the timbre is the sample, and the samples come from a General MIDI
SoundFont: snes_samples.py builds them.

The envelopes also come from the SoundFont: `envelope` translates each
zone's into what the DSP's ADSR and GAIN can do.
"""

import math

VOICES = 8
SAMPLE_RATE = 32000     # what the DSP reads at with a 1:1 step
CYCLE = 32              # samples per cycle of the bank's waves
MAX_PITCH = 0x3FFF

# --- registers --------------------------------------------------------------
# The per-voice ones come in groups of 16: voice v uses v*$10 + the number below.
V_VOL_L, V_VOL_R = 0x00, 0x01
V_PITCH_L, V_PITCH_H = 0x02, 0x03
V_SRCN = 0x04
V_ADSR1, V_ADSR2 = 0x05, 0x06
V_GAIN = 0x07

# The global ones live in columns $x C and $x D.
MVOL_L, MVOL_R = 0x0C, 0x1C
EVOL_L, EVOL_R = 0x2C, 0x3C
KON, KOF = 0x4C, 0x5C
FLG = 0x6C
PMON, NON, EON = 0x2D, 0x3D, 0x4D
DIR = 0x5D

FLG_BASE = 0x20         # echo off; the five low bits are the noise


# --- the envelopes ----------------------------------------------------------
#
# They come from the SoundFont, generators 33 to 40, which `gunter sf2 --json`
# returns per zone —see `brr_samples.envelope`—. Until 2026-09-25 they
# came from eight families picked by eye when the bank was synthetic, and
# what differed most was the release: the synthetic bass and the saw release
# in 30 ms in the SF2 and here they dragged a 2.4 s tail.
#
# What the DSP can do, and why the translation is not direct: each phase
# advances one step every so many samples out of the 32,000 per second, and
# how many is given by `PERIOD` for the 5-bit rate number (0 is "never").
# The attack is linear and reaches the top in 64 steps; decay, sustain and
# exponential GAIN subtract 1/256 of the level per step; linear GAIN
# subtracts 1/64.
PERIOD = [None, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192,
          160, 128, 96, 80, 64, 48, 40, 32, 24, 20, 16, 12, 10, 8, 6, 5, 4, 3,
          2, 1]

# The DSP's ADSR release cannot be configured: on writing KOF the envelope
# drops to zero in about 8 ms, which sounds like an abrupt cut. That is why
# releasing a note is not done with KOF but by clearing the ADSR bit —so
# GAIN takes over— and asking it for a decrease, whose speed can be chosen.
# The envelope continues from where it was, so the note fades out instead of
# being cut.
GAIN_LINEAR_DECREASE = 0x80     # bit 7: custom mode; bits 5-6: linear
GAIN_EXP_DECREASE = 0xA0        # bits 5-6: exponential

# **The DSP's exponential decrease is not exponential all the way down**:
# below 1/8 of the level it subtracts one at a time, and from the top it
# reaches zero in about 790 steps. Matching its slope to the SoundFont's
# silences it too early —the piano went quiet at 1.4 s instead of
# continuing at -26 dB—, so it is made to reach zero where the SoundFont is
# at about -40 dB, which is "no longer audible". Measured by the prototype in
# `workflow/tasks/todo/la-calidad-de-la-musica.md`.
STEPS_TO_ZERO = 790
DOWN_TO_DB = 40.0
# A release shorter than this uses linear GAIN: the fastest exponential takes
# 25 ms to reach zero and is not enough for the bass's 30 ms.
LINEAR_RELEASE = 0.1
# An attack shorter than this is instantaneous (A = 15): the fastest of the
# others, A = 14, already takes 4 ms.
INSTANT_ATTACK = 0.004
# And below how much the note is considered to die out on its own while held:
# then there is no sustain level to imitate, but a decay to follow.
MUTED_SUSTAIN_DB = 30.0

# dB an exponential step drops: 20·log10(256/255).
_DB_PER_STEP = 20 * math.log10(256 / 255.0)


def _seconds(timecents):
    """The SoundFont's timecents: 1200 per octave, 0 is one second and
    -12000 is "nothing"."""
    return 2.0 ** (timecents / 1200.0) if timecents > -12000 else 0.0


def _closest_rate(seconds, duration, rates):
    """From `rates`, the one that makes the phase last closest to `seconds`
    on a logarithmic scale. `duration(rate)` says how long it lasts with it."""
    return min(rates, key=lambda r: abs(math.log(max(duration(r), 1e-9)
                                                 / max(seconds, 1e-9))))


def _time_to_zero(r):
    """How long an exponential decrease at rate `r` takes to reach zero."""
    return STEPS_TO_ZERO * PERIOD[r] / float(SAMPLE_RATE)


def envelope(sf2, key):
    """(ADSR1, ADSR2, release GAIN) for a note, from the volume envelope of
    its zone in the SoundFont: the dict with the `env_*` fields of `gunter
    sf2 --json`."""
    attack = _seconds(sf2["env_attack_timecents"]) + _seconds(
        sf2["env_hold_timecents"])
    # The decay shortens with the key, around middle C.
    decay = _seconds(sf2["env_decay_timecents"]
                     + sf2["env_key_to_decay"] * (60 - key))
    sustain_db = sf2["env_sustain_centibels"] / 10.0
    release = _seconds(sf2["env_release_timecents"])

    # Attack: A from 0 to 14 uses rate 2A+1 and rises in 64 steps.
    if attack < INSTANT_ATTACK:
        ar = 15
    else:
        ar = _closest_rate(attack, lambda a: 64 * PERIOD[2 * a + 1]
                           / float(SAMPLE_RATE), range(15))

    # The SoundFont drops 100 dB in `decay` seconds, in a straight line in dB.
    if sustain_db >= MUTED_SUSTAIN_DB:
        # It dies out on its own: the sustain level at the very top —the decay
        # phase ends immediately— and the sustain goes down with the
        # SoundFont's decay, reaching zero where it reaches -40 dB.
        sl, dr = 7, 0
        sr = _closest_rate(decay * DOWN_TO_DB / 100.0, _time_to_zero,
                           range(1, 32))
    else:
        # It goes down to a level and stays: SL in eighths, and the decay
        # (rate 2D+16) with the SoundFont's slope. Above 1/8 the DSP's
        # decrease is exponential, so here the slope is what matters.
        level = 10 ** (-sustain_db / 20.0)
        sl = max(0, min(7, int(round(8 * level)) - 1))
        period = _DB_PER_STEP * SAMPLE_RATE / (100.0 / max(decay, 1e-3))
        dr = _closest_rate(period, lambda d: PERIOD[2 * d + 16], range(8))
        sr = 0

    if release < LINEAR_RELEASE:
        r = _closest_rate(release,
                          lambda r: 64 * PERIOD[r] / float(SAMPLE_RATE),
                          range(1, 32))
        gain = GAIN_LINEAR_DECREASE | r
    else:
        r = _closest_rate(release * DOWN_TO_DB / 100.0, _time_to_zero,
                          range(1, 32))
        gain = GAIN_EXP_DECREASE | r
    return (0x80 | (dr << 4) | ar, (sl << 5) | sr, gain)


# --- notes ------------------------------------------------------------------

def pitch(note, length=CYCLE):
    """The reading step for a one-cycle wave to give that note.

    The DSP advances `pitch/4096` samples for each output sample at 32 kHz, so
    a wave of `length` samples sounds at `32000 * pitch / 4096 / length`.
    Solving for pitch gives the arithmetic below.

    The register has 14 bits, so the maximum step is 4x: with 32 samples per
    cycle, about 4 kHz. Above that the note is dropped an octave.
    """
    while True:
        hertz = 440.0 * 2.0 ** ((note - 69) / 12.0)
        value = int(round(hertz * length * 4096 / SAMPLE_RATE))
        if value <= MAX_PITCH:
            return max(1, value)
        note -= 12


def pitch_for(note, root, rate, length=None):
    """The reading step to play a note with a recorded sample.

    With one-cycle waves the arithmetic came from the cycle length. With a
    recording it comes from elsewhere: the sample sounds at its original
    tuning when the DSP reads it at the same rate it was recorded at, and
    from there it is transposed by the difference in semitones against its
    reference note.

    The register has 14 bits, that is, at most four times the base rate.
    Storing at 10 kHz that gives about two and a half octaves above the
    recorded note, plenty; when it is not enough the note is dropped an
    octave, which is less out of tune than sticking at the cap.
    """
    while True:
        step = rate * 4096.0 / SAMPLE_RATE * 2.0 ** ((note - root) / 12.0)
        value = int(round(step))
        if value <= MAX_PITCH:
            return max(1, value)
        note -= 12


# The DSP adds up the eight voices and only then applies the master volume,
# with no limiting in between: if the sum overflows, it clips and sounds
# dirty. With waves that reach 0x6000 and up to half a dozen voices at once,
# the per-voice ceiling has to stay quite low. Both numbers come from
# measuring the peak of the recorded WAV, not from theory: theory assumes all
# voices peak together and in phase, which never happens.
#
# **And the clipping happens before the master volume**: the sum of the
# voices saturates at 16 bits and only then is multiplied by MASTER, so what
# prevents clipping is each voice's ceiling, and MASTER only decides at what
# level it comes out. With the drums playing again and the SoundFont's
# sustains, 16 of the 22 songs clipped —the battle one, 309,040 samples—, so
# on 2026-09-25 they were given **headroom**: each voice's ceiling HEADROOM
# times the previous one (96 and 84) and MASTER that much higher, as far as
# it goes: the register is signed and does not go past $7F.
#
# The prototype proposed 0.8 with MASTER at $78, which leaves the level the
# same, and it was not enough: all 16 still clipped, hzbreach 107,218
# samples. With 0.5 five clip, at most 858 samples (hzbreach), and the level
# drops about 3.6 dB where it did not clip before —`escape_newyork` comes out
# at -17.3 LUFS—. **And it is the ceiling, not everyone's**: since 2026-09-26
# the song that would clip at 0.5 gets a lower one, its own, measured and
# versioned —see `read_ceilings` in snes_music.py—. What does not clip stays at
# 0.5. Measured against A Blurred Line: an assumption of the engine, not data
# from the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
HEADROOM = 0.5
MASTER = min(0x7F, int(round(0x60 / HEADROOM)))
CEILING = int(round(96 * HEADROOM))
CEILING_DRUM = int(round(84 * HEADROOM))    # percussion hits hard and is
                                            # short: it can take more


# How much each thing lowers the level, measured with fluidsynth and the
# SoundFont —which is what we compare against and where the MSU-1 tracks come
# from—, relative to a note with velocity 127 and the controllers at their GM
# value:
#
# * **velocity, 40·log10(127/v) dB**, that is, the amplitude squared. The
#   SF2 specification defines it as a 96 dB concave curve, which is not
#   exactly this; fluidsynth gives this, and we follow fluidsynth.
#   Measured: 64 gives -11.9 dB, 29 gives -25.7. Until 2026-09-26 it was
#   linear —29 gave -12.8— and the mix came out skewed towards the pads,
#   which in the MIDIs have low velocity;
# * **volume (CC7) and expression (CC11), the same**: 40·log10 each. CC7 is
#   measured against 100, its GM default: a channel at 127 sounds 4 dB
#   **louder** than one that says nothing, and that is how it comes out here;
# * **pan (CC10), sine and cosine**, with the center at -3 dB on each side
#   relative to a hard pan: 0 gives +3 dB on the left, 32 gives +2.3 and
#   -5.3. The center is left at the ceiling, so a hard pan exceeds the
#   ceiling by 1.41: that is what fluidsynth does.
#
# The floor: a note the calculation does not leave at zero is heard at least
# at 2 —the prototype's, what taro listened to—. Until 2026-09-26 it was 4,
# which with the linear curve was almost never hit and with this one would
# drown out the soft notes: 4 is velocity 37.
VOLUME_FLOOR = 2


def volume(velocity, ceiling=CEILING, cc7=100, cc11=127, pan=64):
    """Left and right of a voice, from 0 to 127 (the register is signed),
    with the note's velocity and its channel's controllers."""
    amplitude = (ceiling * (velocity / 127.0) ** 2 * (cc7 / 100.0) ** 2
                 * (cc11 / 127.0) ** 2)
    # fluidsynth maps GM pan to an angle with 128 steps, not 127: 64 is the
    # exact center and 127 does not quite reach the right.
    angle = min(127, max(0, pan)) / 128.0 * math.pi / 2
    center = math.cos(math.pi / 4)

    def side(x):
        if x < 0.5:
            return 0
        return max(VOLUME_FLOOR, min(0x7F, int(round(x))))

    return (side(amplitude * math.cos(angle) / center),
            side(amplitude * math.sin(angle) / center))
