"""Builds the SNES sample bank from the SoundFont.

It replaces sdsp.py's one-cycle waves with real recordings. The problem stops
being inventing a timbre and becomes one of budget: the SPC700 has 64 KB for
everything.

The lever is the sample rate. The DSP resamples anyway to change the pitch
of the note, so storing at 8 or 12 kHz costs nothing extra at run time: it
only costs treble. It is exactly what the console's games did, and that is
why they sound the way they sound.

With the Windows bank the lever is barely used: its samples already come at
22 kHz and are short, so in a package with room they go whole. In the ones
that fill the ARAM —the maps with many sound effects, the battle— it goes
down, and for that `resample` filters before lowering the rate. The rule is
still not to touch the rate while there is room: the filter prevents
aliasing, it does not bring the treble back.

Three constraints rule the result:

  * **The loop has to fall on a BRR block.** The DSP loops back to the start
    of a nine-byte block, that is, every 16 samples. If the loop point falls
    mid-block, it cannot be expressed; the resampling has to be adjusted so
    it lands exactly, not rounded in the hope it works.
  * **The loop is not shortened.** FluidR3 picks long loops (almost a second
    on the piano) because inside there is beating between strings. Cutting
    it shorter introduces an audible periodicity, so when room runs short the
    rate goes down, not the length.
  * **The attacks are not touched.** They are what tells a piano from an
    organ, and they are short: trimming them saves little and costs a lot.
"""

import hashlib
import math

from audio import brr_samples
from common import environment
from common import disk_cache

# The Windows software synthesizer, which is what this game was composed and
# listened to with. Microsoft licensed a reduced subset of the Sound Canvas
# from Roland, so it is not an SC-55: it is exactly this and nothing more.
#
# Its being reduced suits us in two ways. Its samples are ten times shorter
# than FluidR3's and already come at 22 kHz, so the whole bank fits in ARAM
# without resampling anything — and resampling was, by far, what cost the
# most quality. And along the way we stop approximating a similar bank and
# sample from the one that produced the original sound.
#
# `SOUNDFONT` is set by the executable from `--soundfont`, and read when used:
# see `__getattr__` and `common/environment.py`.


def __getattr__(name):
    if name == "SOUNDFONT":
        return environment.soundfont()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


BLOCK = brr_samples.BLOCK_SAMPLES    # 16 samples per BRR block
REFERENCE_KEY = 60                 # middle C: the note the zone is picked with
PEAK = 0x6800                      # what each sample is normalized to

# General MIDI percussion lives in bank 128, and there each key is a
# different instrument instead of a different pitch. That belongs to the
# format, so the one who knows it is `gunter sf2`: here we ask for `drum:36`
# and nothing more.
DRUM_SECONDS = 0.5

MIN_RATE = 4000
MAX_RATE = 24000


class Voice:
    """An instrument ready for the SPC700."""

    def __init__(self, program, name, data, rate, root, loop_block, frames):
        self.program = program
        self.name = name
        self.data = data                # BRR
        self.rate = rate                # the rate it was stored at
        self.root = root                # which note sounds at that rate
        self.loop_block = loop_block    # which block it loops back to
        self.frames = frames

    def __repr__(self):
        return "<Voice %d %r %d B at %d Hz>" % (self.program, self.name,
                                             len(self.data), self.rate)


# --- the prepared-sample cache ---------------------------------------------
#
# What is stored here is **the whole voice**: the resampling, the
# normalization and the BRR that comes out of them. `brr_samples.encode`
# already cached the last part, and that was never the problem — the Python
# preparation that comes before was. Measured with `cProfile` over a
# conversion of `abl` **with a warm cache**: of 165 s of profile, 114.6 were
# audio, and of those 108.9 came from `build_drum_bank` —the percussion
# allocation up to step 6—, which was called 790 times in one conversion.
#
# **The hit is cached and not the bank** —`build_drum(hit, budget)` and not
# `build_drum_bank(hits, budget)`— and that is the decision. The bank has
# fewer keys, but its key carries *which hits* the cartridge asks for, so two
# cartridges with different song lists do not share a single entry. The
# single hit does: the key is a note and a budget, and those repeat across
# the rounds of the allocation, across the test cartridges and the demo.

_version = None
_fingerprints = {}
_drums = {}
_voices = {}


def _preparation_version():
    """Which version of the code produced the stored voice.

    It covers this file —the resampling, the normalization and the budget
    allocation live here— and, through `brr_samples.version()`, the bridge
    and **the installed binary**. What decides the key is what produced the
    bytes, and the bytes go through all three.
    """
    global _version
    if _version is None:
        _version = disk_cache.key(brr_samples.version(),
                                  disk_cache.version_of(
                                      "audio/snes_samples.py"))
    return _version


def soundfont_fingerprint(path):
    """The SoundFont's content, not its path.

    `--soundfont` can point to another bank, and a bank can change without
    changing its name: the key has to expire with either. It is read once per
    process because the file weighs megabytes.

    It is public because `msu.py` renders with **the same soundfont** and its
    key needs the same fingerprint, for the same reason.
    """
    if path not in _fingerprints:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _fingerprints[path] = h.hexdigest()
    return _fingerprints[path]


def _cached(memo, cache_key, parts, make):
    """A voice, from the process's memory, from disk or freshly made.

    What is stored goes inside a one-element tuple because **`None` is a
    legitimate result** —there is no such hit in the bank, or what fits in the
    budget does not even reach one block— and `disk_cache.read` returns
    `None` when there is nothing. Without the wrapper, an already computed
    "does not exist" would be computed again on every run.
    """
    if cache_key in memo:
        return memo[cache_key]
    on_disk = disk_cache.key(_preparation_version(), *parts)
    stored = disk_cache.read("muestras", on_disk)
    if stored is None:
        stored = (make(),)
        disk_cache.write("muestras", on_disk, stored)
    memo[cache_key] = stored[0]
    return stored[0]


# How far the low-pass reaches before lowering the rate, as a fraction of
# half the new rate: a bit below, because the filter's roll-off is not
# vertical and what goes past half aliases. And how many cycles of the cutoff
# frequency its kernel spans: more is a steeper roll-off and a longer filter.
CUTOFF = 0.9
CYCLES = 12


def _low_pass(samples, fraction, circular=False, after=()):
    """`samples` without what goes past `fraction` of its rate (in cycles per
    sample), as floats: a Blackman-windowed sinc.

    `circular` is for the loop: the signal repeats, so the filter sees it as
    periodic and the loop point is not left with a step. `after` is what
    follows the signal —the loop, after the attack—, so that the end of the
    attack is filtered with what really plays next and not against zeros."""
    import numpy as np
    x = np.asarray(samples, dtype=float)
    half = max(8, int(math.ceil(CYCLES / (2.0 * fraction))))
    n = np.arange(-half, half + 1)
    kernel = 2 * fraction * np.sinc(2 * fraction * n) * np.blackman(len(n))
    kernel /= kernel.sum()
    if circular:
        length = len(x)
        folded = np.zeros(length)
        np.add.at(folded, n % length, kernel)
        return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(folded), length)
    tail = np.asarray(list(after), dtype=float)
    if len(tail):
        tail = np.tile(tail, int(math.ceil(half / float(len(tail)))) + 1)
    return np.convolve(np.concatenate([x, tail[:half]]), kernel,
                       mode="same")[:len(x)]


def resample(samples, count, circular=False, after=()):
    """Changes a signal's length: low-pass if the rate goes down, and then
    linear interpolation.

    Until 2026-09-26 there was no filtering —"in pitched instruments these
    partials are weak, and the BRR error is much larger than the aliasing
    error"—, and with the Windows bank it was hardly needed, because almost
    everything went at the SoundFont's rate. Since the per-package budget
    there are samples that go down from 22 to 10 kHz, and there whatever
    goes past 5 kHz aliases onto the lows as noise that is not in the
    instrument. It is step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md`, with what was measured.

    `circular` and `after` are those of `_low_pass`.
    """
    if count <= 0 or not len(samples):
        return []
    if count == len(samples):
        return list(samples)
    if count < len(samples):
        samples = _low_pass(samples, CUTOFF * 0.5 * count / len(samples),
                            circular, after)

    step = (len(samples) - 1) / float(count)
    out = []
    for i in range(count):
        position = i * step
        index = int(position)
        fraction = position - index
        first = samples[index]
        second = samples[min(index + 1, len(samples) - 1)]
        out.append(int(round(first + (second - first) * fraction)))
    return out


def normalize(samples, peak=PEAK):
    """Brings the sample to a known amplitude.

    That way the volume is decided by the note's velocity and not by how
    loud that instrument was recorded, which varies quite a bit between
    FluidR3 presets.
    """
    top = max((abs(s) for s in samples), default=0)
    if not top:
        return list(samples)
    scale = peak / float(top)
    return [int(round(s * scale)) for s in samples]


def plan_rate(attack_frames, loop_frames, source_rate, budget):
    """At which rate to store to fit in the budget.

    Returns the highest rate that fits, bounded by MIN_RATE and MAX_RATE. The
    budget is in BRR bytes, which are nine per 16 samples.
    """
    frames = attack_frames + loop_frames
    if not frames:
        return MIN_RATE
    # How many samples fit in the budget.
    allowed = budget * BLOCK / float(brr_samples.BLOCK_BYTES)
    rate = source_rate * allowed / frames
    return int(max(MIN_RATE, min(MAX_RATE, min(rate, source_rate))))


def build_voice(soundfont, program, budget, key=REFERENCE_KEY):
    """An instrument from the SoundFont in BRR, cached. See `_cached`."""
    return _cached(_voices, (soundfont, program, budget, key),
                   (soundfont_fingerprint(soundfont), "program",
                    str(program), str(budget), str(key)),
                   lambda: _build_voice(soundfont, program, budget, key))


def _build_voice(soundfont, program, budget, key):
    """Extracts an instrument from the SoundFont and leaves it in BRR.

    The fine adjustment is in making the loop land exactly on a block. First
    it picks how many samples the loop will have —a multiple of 16— and from
    that comes the real rate, which may differ a bit from the one asked for.
    Then the attack is brought to the nearest multiple of 16 at that same
    rate.
    """
    sample = brr_samples.extract("program:%d@%d" % (program, key), soundfont)
    if sample is None:
        return None

    # Which zone covers the note, whether the loop is valid and where the root
    # key comes from are decisions of the format, and `gunter sf2` makes them:
    # here the loop already comes in frames and relative to the extracted PCM,
    # and `loop` already says no when the zone does not repeat or when the
    # loop is empty.
    looped = sample.loop
    attack_frames = sample.loop_start if looped else sample.frames
    loop_frames = sample.loop_end - sample.loop_start if looped else 0

    rate = plan_rate(attack_frames, loop_frames, sample.rate, budget)
    ratio = rate / float(sample.rate)

    if looped:
        # The loop first: its length has to be a multiple of 16, and from that
        # rounding comes the rate we will actually declare.
        loop_out = max(BLOCK, int(round(loop_frames * ratio / BLOCK)) * BLOCK)
        ratio = loop_out / float(loop_frames)
        rate = int(round(sample.rate * ratio))
    else:
        loop_out = 0

    attack_out = int(round(attack_frames * ratio / BLOCK)) * BLOCK

    loop_pcm = sample.pcm[sample.loop_start:sample.loop_end] if looped else ()
    audio = resample(sample.pcm[:attack_frames], attack_out, after=loop_pcm)
    if looped:
        audio += resample(loop_pcm, loop_out, circular=True)
    audio = normalize(audio)

    data = brr_samples.encode(
        audio, loop_block=attack_out // BLOCK if looped else None)
    return Voice(program, sample.name, data,
                 rate * 2.0 ** (-sample.cents / 1200.0), sample.root_key,
                 attack_out // BLOCK if looped else 0, len(audio))


def build_drum(soundfont, note, budget, seconds=DRUM_SECONDS):
    """A percussion hit in BRR, cached. See `_cached`."""
    return _cached(_drums, (soundfont, note, budget, seconds),
                   (soundfont_fingerprint(soundfont), "drum", str(note),
                    str(budget), repr(seconds)),
                   lambda: _build_drum(soundfont, note, budget, seconds))


def _build_drum(soundfont, note, budget, seconds):
    """A percussion hit from the standard kit.

    In General MIDI percussion lives in bank 128 and each key is a different
    instrument: 36 is the bass drum, 42 the hi-hat. Nothing is transposed, so
    the sample is stored to play at its original rate.

    It is trimmed, and a lot: FluidR3's ride cymbal lasts 2.6 seconds and the
    closed hi-hat 0.7, almost all of it a tail that dies out. Storing it whole
    would cost more than all the melodic instruments together. It is cut and
    the rest is done by the DSP envelope, which is exactly what it is for.
    """
    sample = brr_samples.extract("drum:%d" % note, soundfont)
    if sample is None:
        return None

    frames = min(sample.frames, int(seconds * sample.rate))
    rate = plan_rate(frames, 0, sample.rate, budget)
    out = int(round(frames * rate / float(sample.rate)) / BLOCK) * BLOCK
    if out < BLOCK:
        return None

    audio = normalize(resample(sample.pcm[:frames], out))
    data = brr_samples.encode(audio, loop_block=None)
    return Voice(note, sample.name, data, rate, sample.root_key, 0, out)
