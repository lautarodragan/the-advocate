"""LZ2, the binary that compresses what the ROM decompresses when loading a map.

The format is Nintendo's LC_LZ2, and taro chose it on 2026-09-26 with what
was measured in `workflow/tasks/*/la-compresion-de-mapas-y-graficos.md`: it
stays within 20% of zlib on the tiles and within 10 KB on the grids, and its
repeat with an absolute address into the output is what an `mvn` does in one
go. The decompressor is `lz2_decompress`, in `tools/runtime/decompress.s`.

The compressor is a separate project, `tools/snes/lz2/`, in Rust and in English,
by the rule in AGENTS.md: it does not need to know anything about this game.
And in Rust rather than here because it is an optimal parser —the shortest
encoding the format allows, with a suffix array— and in Python it would take
minutes per build. It is used from the PATH, like `voodoo` and `gunter`: it
is installed with `just install` and no script calls `cargo`.

The reference it is tested against is a different one, on purpose: `lz2.py`
in `rom/pruebas/arnes/`, written separately and without looking at the
binary.
"""

import os
import shutil
import subprocess
import tempfile

MISSING = """`lz2` is missing, the compressor of the tiles and the grids.

It is a Rust binary that lives in `tools/snes/lz2/` and is installed as a system
tool:

    just -f tools/justfile install"""

# The longest a stream can expand to: the repeat names the output position
# with sixteen bits. It is the format's, not ours.
OUTPUT_MAX = 0x10000


def binary():
    """The path of the `lz2` on the PATH. Exits with the message if it is
    not there."""
    path = shutil.which("lz2")
    if path is None:
        raise SystemExit(MISSING)
    return path


def compress_many(blocks):
    """Each block compressed, in the same order. A single process for all of
    them: there are hundreds per cartridge and launching one per block
    shows."""
    blocks = [bytes(b) for b in blocks]
    for b in blocks:
        if len(b) > OUTPUT_MAX:
            raise SystemExit("a block of %d bytes does not fit in an LZ2 stream: "
                             "the limit is %d" % (len(b), OUTPUT_MAX))
    if not blocks:
        return []
    with tempfile.TemporaryDirectory(prefix="lz2-") as d:
        args = [binary(), "compress", "--no-increasing"]
        for k, b in enumerate(blocks):
            input_path = os.path.join(d, "%d.bin" % k)
            with open(input_path, "wb") as f:
                f.write(b)
            args += [input_path, input_path + ".lz2"]
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode:
            raise SystemExit("lz2 exited with %d: %s"
                             % (done.returncode, done.stderr.strip()))
        out = []
        for k in range(len(blocks)):
            with open(os.path.join(d, "%d.bin.lz2" % k), "rb") as f:
                stream = f.read()
            missing = what_the_rom_does_not_read(stream)
            if missing:
                raise SystemExit("lz2 emitted %s, which `lz2_decompress` does not read"
                                 % missing)
            out.append(stream)
        return out


def compress(block):
    return compress_many([block])[0]


def walk(stream):
    """The commands of a stream, as (command, length). Reads only the
    headers."""
    i = 0
    while stream[i] != 0xFF:
        header = stream[i]
        if header >> 5 == 7:
            command = (header >> 2) & 7
            length = ((header & 3) << 8 | stream[i + 1]) + 1
            i += 2
        else:
            command, length = header >> 5, (header & 31) + 1
            i += 1
        i += {0: length, 1: 1, 2: 2, 3: 1, 4: 2}[command]
        yield command, length


# The two commands the format has and `lz2_decompress` does not read, on
# purpose: no block used them, and a path no test runs is the one that has
# bitten this repo the most times. The compressor does not emit the
# increasing one (3) with `--no-increasing`, and it costs almost nothing; it
# never picks the one-byte word, because a literal of one costs less. If
# either shows up, it stops here and not on the console.
def what_the_rom_does_not_read(stream):
    for command, length in walk(stream):
        if command == 3:
            return "an increasing fill"
        if command == 2 and length == 1:
            return "a one-byte word"
    return None
