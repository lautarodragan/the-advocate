"""Voodoo, the binary that turns an image that already fits into tiles.

It takes an 8-bit indexed PNG whose indices are CGRAM entries —on a 4bpp
layer, `index >> 4` is the palette— and returns tiles, tilemap and CGRAM.
**It decides nothing visible**: which colors stay and which palette each
cell goes in was decided by the allocator before writing the image: see
"`tools/voodoo/` no decide colores" in `AGENTS.md`.

This module is still called `tiles_bin` because it names **what it
produces** —tiles— and not who produces them.

It is used from the PATH, like `gunter` and `ca65`: it is installed with
`just install` and no script calls `cargo`.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile

MISSING = """`voodoo` is missing, the converter from images to tiles.

It is a Rust binary that lives in `tools/voodoo/` and is installed as a
system tool:

    just -f tools/justfile install"""


def binary():
    """The path of the `voodoo` on the PATH. Exits with the message if it is
    not there."""
    path = shutil.which("voodoo")
    if path is None:
        raise SystemExit(MISSING)
    return path


def version():
    """What produced whatever is in a cache: this file and the installed
    binary, which is what actually did the converting."""
    h = hashlib.sha256()
    for path in (os.path.abspath(__file__), binary()):
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def indexed_png(width, height, pixels, colors, transparent):
    """The bytes of an 8-bit indexed PNG.

    `colors` are the 256 CGRAM entries in 15 bits, or None. `transparent`
    says which entries do not draw: `voodoo` does not care, since it knows
    from the depth, but whoever opens the image to look at it does.
    """
    from PIL import Image
    image = Image.new("P", (width, height))
    image.putdata(pixels)
    palette = []
    for color in colors:
        r, g, b = color if color is not None else (0, 0, 0)
        palette += [r << 3, g << 3, b << 3]
    image.putpalette(palette)
    out = io.BytesIO()
    image.save(out, format="PNG",
               transparency=bytes(0 if t else 255 for t in transparent))
    return out.getvalue()


def convert(png, bpp, columns, priority=False, animations=(),
            max_tiles=None):
    """Converts an indexed PNG. Returns (tiles, cgram, tilemap, corridas).

    `animations` are lists of PNGs: the drawings of each one besides the
    image. `runs` is, per animation, (first tile, how many, bytes of each
    drawing).
    """
    with tempfile.TemporaryDirectory(prefix="voodoo-") as d:
        input_path = os.path.join(d, "imagen.png")
        with open(input_path, "wb") as f:
            f.write(png)
        args = [binary(), "convert", input_path, "--bpp", str(bpp),
                "-o", os.path.join(d, "tiles.bin"),
                "--palette", os.path.join(d, "cgram.bin"),
                "--tilemap", os.path.join(d, "tilemap.bin"), "--json"]
        if priority:
            args.append("--priority")
        if max_tiles is not None:
            args += ["--max-tiles", str(max_tiles)]
        for a, drawings in enumerate(animations):
            paths = []
            for n, drawing in enumerate(drawings):
                path = os.path.join(d, "anim%d-%d.png" % (a, n))
                with open(path, "wb") as f:
                    f.write(drawing)
                paths.append(path)
            args += ["--animation", ",".join(paths),
                     "--animation-out", os.path.join(d, "anim%d.bin" % a)]
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode:
            raise SystemExit("voodoo exited with %d: %s"
                             % (done.returncode, done.stderr.strip()))
        report = json.loads(done.stdout)

        def read(name):
            with open(os.path.join(d, name), "rb") as f:
                return f.read()

        raw = read("tilemap.bin")
        words = [int.from_bytes(raw[i:i + 2], "little")
                 for i in range(0, len(raw), 2)]
        tilemap = [words[i:i + columns]
                   for i in range(0, len(words), columns)]
        runs = []
        for a, run in enumerate(report["animations"]):
            data = read("anim%d.bin" % a)
            length = len(data) // run["frames"] if run["frames"] else 0
            runs.append((run["first"], run["tiles"],
                         [data[i:i + length]
                          for i in range(0, len(data), length or 1)]
                         if length else [b""] * run["frames"]))
        return read("tiles.bin"), read("cgram.bin"), tilemap, runs
