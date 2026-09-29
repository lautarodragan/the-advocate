"""The high-quality sound effects, which the ROM reads from the `.msu` with MSU-1.

With MSU-1 and the song playing from its track, the SPC700 plays no music:
the ARAM is left for the sound effects. But the ROM cannot carry a
high-quality version of every sound effect for every package —measured on
2026-09-26, the 92 sound effects of `release`, whole at 22 kHz, came to
1.1 MB, and the package of map 3 alone asked for 291 KB against the ARAM's
62—, so the `.msu` carries them, which has no cap, and the ROM uploads them
to the ARAM through the MSU-1 data port when loading each package. Without
MSU-1, or with a `.msu` that is not this cartridge's, it uses its own: the
usual ones, which `snes_music` distributes. The mechanism is the same as the
battle backgrounds' —see docs/port/msu-datos.md— and the design with its
numbers, the task `efectos-de-calidad-con-msu-1.md`.

**Each package has its own version of each sound effect**, at the rate that
fits it. A single one per sound effect —the one that fits its worst
package— left at 4.7 kHz the sound effects that map 3 shares with ten other
packages that have room to spare: that same day, 48 of the 159 (package,
sound effect) pairs of `release` lost out. What it costs is that the ROM
uploads the sound effects again on every package even if they were already
in the ARAM, because it has nowhere to record which version was left: see
`se_msu_prepare` in tools/runtime/efectos_con_msu.s.

**Always whole, and at the highest rate that fits**: the same for all the
sound effects of the package —`RATES`, from the WAVs' rate downwards— unless
the cartridge's is higher. A sound effect the cartridge already carries
whole ends up no worse than without MSU-1: its rate is the floor. One the
cartridge carries trimmed may end up at a lower rate than there, but whole:
it is what taro asked for first, the length.
"""

import collections

from audio import brr_samples
from audio import snes_music
from audio import snes_samples

# The rates to choose from, highest to lowest. 22,050 Hz is the rate of the
# RTP's WAVs, so there is no resampling; one fixed rate for all the sound
# effects of a package, and stepped so that the same version serves more than
# one package —the BRR cache encodes it once—.
RATES = (22050, 20000, 18000, 16000, 14000, 12000, 11025, 10000, 9000, 8000,
         7500, 7000, 6500, 6000, 5500, 5000, 4500, 4000, 3500, 3000)
# What is left free in each package, as with the music: `ARAM_MARGIN`.
MARGIN = snes_music.ARAM_MARGIN


# `rate` is what `snes_music.effect_pitch` reads, the same as from a
# `SoundEffect`.
Version = collections.namedtuple("Version", "name rate data")


def build(name, rate, game_dir):
    """The whole sound effect, without a loop, at `rate` —or at its WAV's rate,
    if lower—, in BRR. It is what `snes_music.build_sound_effect` does with a
    sound effect from `se_whole()`, and the normalization is the same: it
    sounds as loud as the ROM's."""
    raw, source_rate = snes_music.read_wav(name.split("@")[0], game_dir)
    rate = min(rate, source_rate)
    count = max(brr_samples.BLOCK_SAMPLES,
                int(round(len(raw) * rate / float(source_rate)))
                // brr_samples.BLOCK_SAMPLES * brr_samples.BLOCK_SAMPLES)
    audio = snes_samples.normalize(snes_samples.resample(raw, count))
    return Version(name, rate, brr_samples.encode(audio))


def _size(length, source_rate, rate):
    """What a sound effect of `length` samples at `source_rate` Hz takes up in
    BRR, whole at `rate`: the same arithmetic as `build`, without building
    it."""
    rate = min(rate, source_rate)
    count = max(16, int(round(length * rate / float(source_rate))) // 16 * 16)
    return count // 16 * brr_samples.BLOCK_BYTES


def rates_per_package(packages, effects, free, game_dir):
    """{package name: {sound effect: rate}}: at which rate each sound effect
    of each package goes in the `.msu`.

    `packages` are (name, sound effects, bytes of the music that does get
    uploaded with MSU-1): that of the package's songs that have no track.
    `effects` is `bank.effects` —{name: (SRCN, SoundEffect)}—, which gives each
    one's floor: the cartridge's rate if it goes whole there. `free` is what
    the ARAM has for samples.
    """
    wavs = {}
    out = {}
    for name, own, music_bytes in packages:
        own = [e for e in dict.fromkeys(own) if e in effects]
        if not own:
            continue
        for e in own:
            if e not in wavs:
                raw, source_rate = snes_music.read_wav(e.split("@")[0], game_dir)
                wavs[e] = (len(raw), source_rate)
        floor = {e: 0 if effects[e][1].repeats else effects[e][1].rate
                 for e in own}
        room = free - MARGIN - music_bytes
        chosen = {}
        for rate in RATES:
            chosen = {e: max(rate, floor[e]) for e in own}
            if sum(_size(*wavs[e], chosen[e]) for e in own) <= room:
                break
        else:
            print("  high-quality sound effects: package %s does not fit even at "
                  "%d Hz; the ones that do not fit do not play with MSU-1"
                  % (name, RATES[-1]))
        out[name] = chosen
    return out
