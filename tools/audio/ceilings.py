#!/usr/bin/env python3
"""Measures each song's volume ceiling and writes `rom/parches/auto/musica/techos.toml`.

    rm2k-snes-volume-ceilings            measures, writes the table and
                                         rebuilds `release` with it:
                                         `just techos`
    rm2k-snes-volume-ceilings --measure  only measures the `release` that
                                         is built, and writes nothing

The reason for the table is in `read_ceilings` (tools/audio/snes_music.py).
This is how it comes out:

1. **A copy of `release` with every song at half the headroom**
   (`MEASURING_HEADROOM`), in `rom/build/techos/`. With that none clips, so
   the peak measured is the true one, and since each voice's volume is
   linear in the ceiling, each song's with the full headroom is double.
2. **Each whole song on the title screen**, in snes9x without MSU-1, and its
   peak. Each one's headroom is the highest that keeps that peak `MARGIN`
   below the cap, without going past `sdsp.HEADROOM`: the ones that do not
   clip stay as they were.
3. **The table is written, `release` is rebuilt and measured again**. Each
   voice's volume is rounded to an integer, so the arithmetic is
   approximate: if some song still clipped, it is lowered by as much as it
   went over and the round repeats.

What stays in the table, besides the headroom: each song's peak and level
(LUFS) with it, **up to which frame it has to be played to go through its
peak** —with that the test does not play the whole songs— and the
fingerprint of its mix, which is how the test knows the table is stale. See
`test_musica_techos.py`.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import wave
from multiprocessing import Pool

# `realpath` and not `abspath`: `just install` installs this script on the
# PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import sdsp, snes_music                      # noqa: E402
from common import environment                              # noqa: E402
from common import settings                              # noqa: E402
from common import project                              # noqa: E402

# `--project` is read before anything else: this module reads the project
# file when imported —`ROM_NAME`—, and `main`'s `parse_args` comes
# too late.
if __name__ == "__main__":
    project.from_command_line()

# Half the usual headroom: measured on 2026-09-26, with 0.25 none of the 32
# songs of `release` clips, and the loudest one stays 3.9 dB below the cap.
MEASURING_HEADROOM = sdsp.HEADROOM / 2

# What the measured ROM is called: the game's, in its project file.
ROM_NAME = settings.value("rom", "name", kind=str)

# How far the peak is allowed to go: 0.5 dB below the cap. What it absorbs is
# the rounding of each voice's volume to an integer, which makes the peak not
# scale exactly with the headroom.
MARGIN = 10 ** (-0.5 / 20)

# Where the cap lies in what comes out of the console: the DSP saturates the
# sum of the voices at 16 bits and then multiplies it by the master volume,
# MVOL/128.
CAP = 32767 * sdsp.MASTER >> 7

# How many frames before the end of boot —`BOOT_FRAMES`, read from the ROM—
# recording starts: the title screen starts its song afterwards, so it is
# slack. It used to be a fixed 90 frames from power-on, with boot at 112,
# which is what the script that measured step 5 expected; since boot got
# shorter, a fixed number would cut off the start of each song.
BEFORE_TITLE = 22

# How many frames past the peak the test plays.
AFTER_PEAK = 60

def song_names(directory):
    """The names of the cartridge's songs, in the order of their indices."""
    with open(os.path.join(directory, "musicdata.inc")) as handle:
        inc = handle.read()
    names = re.search(r"^; Songs: (.*)$", inc, re.M).group(1).split(", ")
    return ["" if n == "no music" else n for n in names]


def symbols_of(sfc):
    table = {}
    with open(sfc + ".sym") as handle:
        for line in handle:
            name, value = line.split()
            table[name] = int(value)
    return table


def with_song_on_title(rom, symbols, song):
    """The ROM with the title screen playing `song`: the immediate of the
    `lda #SONG_TITLE` it starts it with is changed. It is the only way for a
    song to play on its own, with its samples uploaded, without playing
    anything."""
    pattern = bytes([0xA9, symbols["SONG_TITLE"], 0xC9, 0xFF, 0xF0])
    where = rom.find(pattern)
    assert where >= 0 and rom.find(pattern, where + 1) < 0, (
        "cannot find the title screen's `lda #SONG_TITLE`: how it starts "
        "its song has changed, and this has to change too")
    patched = bytearray(rom)
    patched[where + 1] = song
    return bytes(patched)


def play(sfc, song, n_frames):
    """(the samples, interleaved stereo, and the rate): `n_frames` frames of
    the song from when the title starts it, in snes9x without MSU-1."""
    import numpy as np
    from emulator import retro
    symbols = symbols_of(sfc)
    with open(sfc, "rb") as handle:
        rom = with_song_on_title(handle.read(), symbols, song)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tema.sfc")
        with open(path, "wb") as handle:
            handle.write(rom)
        console = retro.Console(path, msu=False)
        rate = console.sample_rate()
        console.run(symbols["BOOT_FRAMES"] - BEFORE_TITLE)
        console.audio = bytearray()
        parts = []
        for _ in range(n_frames):
            console.run(1)
            if len(console.audio) > 1 << 20:
                parts.append(bytes(console.audio))
                console.audio = bytearray()
        parts.append(bytes(console.audio))
    return np.frombuffer(b"".join(parts), dtype="<i2"), rate


def clipped(samples):
    """How many samples ended up at the cap."""
    return int(((samples >= CAP) | (samples <= -CAP - 1)).sum())


def song_frames(directory, song):
    """How long one pass of the song lasts, from the writes the converter
    emitted —they are measured in the same process that built it—, plus one
    second."""
    return _lengths[directory][song] + 60


_lengths = {}


def _measure_one(job):
    import numpy as np
    directory, song, n_frames, lufs = job
    x, rate = play(os.path.join(directory, ROM_NAME + ".sfc"),
                   song, n_frames)
    magnitude = np.abs(x.astype(np.int32))
    peak = int(magnitude.max()) if len(x) else 0
    # The frame of the peak: the samples are left/right pairs.
    frame_no = int(magnitude.argmax()) // 2 * 60 // int(round(rate))
    row = {"recortes": clipped(x), "pico": peak, "cuadro": frame_no}
    if lufs:
        row["lufs"] = _lufs(x, rate)
    return song, row


def _lufs(x, rate):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.wav")
        w = wave.open(path, "wb")
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(int(round(rate)))
        w.writeframes(x.tobytes())
        w.close()
        result = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af",
                                 "ebur128", "-f", "null", "-"],
                                capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", result.stderr)[-1])


def measure(directory, lufs=False):
    """{song: {recortes, pico, cuadro[, lufs]}}: each whole song, once."""
    names = song_names(directory)
    built = built_songs(directory)
    _lengths[directory] = {i: t["largo"]
                           for i, t in enumerate(built) if t["largo"]}
    jobs = [(directory, i, song_frames(directory, i), lufs)
            for i, n in enumerate(names) if n and i in _lengths[directory]]
    with Pool(int(os.environ.get("PROCESOS", "8"))) as pool:
        rows = dict(pool.map(_measure_one, jobs))
    return {names[i]: row for i, row in rows.items()}


def built_songs(directory):
    """The cartridge's songs as the converter built them, in the order of
    their indices: the name, the length in frames and the fingerprint of
    each. The converter writes them in `musica.json`, next to
    `musicdata.inc`.

    Until 2026-09-26 they were rebuilt here with `build_all`, which gave
    the same result because the bank depended only on the songs. Since the
    per-package budget it also depends on each map's packages and on which
    song may be playing in each one, which come from compiling the pages:
    rebuilding it here would be a second way of answering the same thing."""
    import json
    with open(os.path.join(directory, "musica.json")) as handle:
        return json.load(handle)["temas"]


def db(peak):
    return 20 * math.log10(max(peak, 1) / float(CAP))


def write(ceilings, measured, fingerprints, path=None):
    """The table, with its reason on top."""
    path = path or snes_music.ceilings_path()
    lines = [
        "# The volume ceiling of each song of `release`: the headroom",
        "# `build_all` builds its stream with, instead of `sdsp.HEADROOM`.",
        "#",
        "# **Not edited by hand**: `just techos` writes it, playing each song",
        "# in the ROM and giving it the highest headroom that does not clip.",
        "# The reason, in `read_ceilings`, which is where the converter reads it;",
        "# how it is measured, in `rm2k-snes-volume-ceilings`.",
        "# `test_musica_techos.py` fails if any song clips or if the mix of",
        "# any of them is no longer the one measured: the fingerprint. Any",
        "# change to the mix —the samples, the envelopes, the allocation—",
        "# calls for running `just techos` again.",
        "#",
        "# Per song: `aire`, the ceiling; `pico`, in dB against the cap, and",
        "# `lufs`, the level, both measured with that headroom; `hasta`, how",
        "# many frames from the start it has to be played to go through its",
        "# peak; and `huella`, that of `mix_fingerprint`.",
        "",
        "[medida]",
        "measuring_headroom = %s" % MEASURING_HEADROOM,
        "margen_db = -0.5",
        "",
    ]
    for name in sorted(ceilings):
        row = measured[name]
        lines += [
            "[temas.\"%s\"]" % name,
            "aire = %.3f" % ceilings[name],
            "pico = %.1f" % db(row["pico"]),
            "lufs = %.1f" % row["lufs"],
            "hasta = %d" % (row["cuadro"] + AFTER_PEAK),
            'huella = "%s"' % fingerprints[name],
            "",
        ]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("\n".join(lines))


def report(measured, ceilings=None):
    for name in sorted(measured):
        row = measured[name]
        print("  %-45s %s peak %+5.1f dB, %5d clipped%s" % (
            name[:45], "headroom %.3f," % ceilings[name] if ceilings else "",
            db(row["pico"]), row["recortes"],
            ", %.1f LUFS" % row["lufs"] if "lufs" in row else ""))


# What the converter needs from the machine, which `rm2k-snes-cartridges`
# passes on to it.
TO_CONVERTER = ("game_dir", "rtp_dir", "soundfont", "cache")


def cartridges(*args, capture=False):
    """Runs `rm2k-snes-cartridges`, the one that builds `release`, with this
    project and this machine's values."""
    return subprocess.run(
        ["rm2k-snes-cartridges", "--project", project.directory(),
         *environment.as_flags(*TO_CONVERTER), *args],
        check=True, text=True, capture_output=capture).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    project.add_argument(parser)
    environment.add_arguments(parser, *TO_CONVERTER)
    parser.add_argument("--measure", action="store_true",
                        help="only measure the built `release`: clipping, "
                             "peak and LUFS of each song")
    args = parser.parse_args()
    environment.from_arguments(args, *TO_CONVERTER)
    listed = json.loads(cartridges("--list", "--json", capture=True))
    release = next(c["directory"] for c in listed["cartridges"]
                   if c["name"] == listed["release"])
    if args.measure:
        report(measure(release, lufs=True))
        return

    # The half-volume copy, in its own build directory.
    measure_dir = os.path.join(project.build(), "techos")
    print("a copy of release with the headroom at %s, in %s"
          % (MEASURING_HEADROOM, measure_dir))
    cartridges(listed["release"], "--convert-into", measure_dir,
               "--", "--measure-headroom", str(MEASURING_HEADROOM))
    at_half = measure(measure_dir)
    clipping = [n for n, f in at_half.items() if f["recortes"]]
    if clipping:
        sys.exit("with the headroom at %s these clip: %s: lower MEASURING_HEADROOM"
                 % (MEASURING_HEADROOM, ", ".join(clipping)))
    ceilings = {}
    for name, row in at_half.items():
        full = row["pico"] * sdsp.HEADROOM / MEASURING_HEADROOM
        ceilings[name] = min(sdsp.HEADROOM, math.floor(
            1000 * sdsp.HEADROOM * CAP * MARGIN / max(full, 1)) / 1000.0)

    for attempt in range(4):
        write(ceilings, {n: dict(f, lufs=0.0) for n, f in at_half.items()},
              {n: "" for n in ceilings})
        print("release with the table, round %d" % (attempt + 1))
        # Without the MSU-1 tracks: what is measured is the SPC700, and
        # the tracks do not depend on the headroom.
        cartridges(listed["release"], "--without-tracks")
        measured = measure(release, lufs=True)
        clipping = {n: f for n, f in measured.items() if f["recortes"]}
        if not clipping:
            break
        for name, row in clipping.items():
            ceilings[name] = math.floor(
                1000 * ceilings[name] * CAP * MARGIN / row["pico"]) / 1000.0
    else:
        sys.exit("after four rounds these still clip: %s"
                 % ", ".join(clipping))
    fingerprints = {t["nombre"]: t["huella"]
                    for t in built_songs(release) if t["largo"]}
    # What is rewritten now —the peaks, the fingerprints— does not change the
    # headrooms, so the cartridge just measured is still up to date: its
    # stamp looks only at the table's headrooms (see the fingerprint in
    # `rm2k-snes-cartridges`).
    write(ceilings, measured, fingerprints)
    report(measured, ceilings)
    print("-> %s" % os.path.relpath(snes_music.ceilings_path()))


if __name__ == "__main__":
    main()
