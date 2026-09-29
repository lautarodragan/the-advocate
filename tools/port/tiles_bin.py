"""Voodoo, the binary that turns an image that already fits into tiles.

It takes an 8-bit indexed PNG whose indices are CGRAM entries —on a 4bpp
layer, `index >> 4` is the palette— and returns tiles, tilemap and CGRAM.
**It decides nothing visible**: which colors stay and which palette each
cell goes in was decided by the allocator before writing the image: see
"`tools/voodoo/` no decide colores" in `AGENTS.md`.

This module is still called `tiles_bin` because it names **what it
produces** —tiles— and not who produces them, like `brr_samples`.

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

FALTA = """`voodoo` is missing, the converter from images to tiles.

It is a Rust binary that lives in `tools/voodoo/` and is installed as a
system tool:

    just -f tools/justfile install"""


def binario():
    """The path of the `voodoo` on the PATH. Exits with the message if it is
    not there."""
    ruta = shutil.which("voodoo")
    if ruta is None:
        raise SystemExit(FALTA)
    return ruta


def version():
    """What produced whatever is in a cache: this file and the installed
    binary, which is what actually did the converting."""
    h = hashlib.sha256()
    for ruta in (os.path.abspath(__file__), binario()):
        with open(ruta, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def png_indexado(ancho, alto, pixeles, colores, transparentes):
    """The bytes of an 8-bit indexed PNG.

    `colores` are the 256 CGRAM entries in 15 bits, or None. `transparentes`
    says which entries do not draw: `voodoo` does not care, since it knows
    from the depth, but whoever opens the image to look at it does.
    """
    from PIL import Image
    imagen = Image.new("P", (ancho, alto))
    imagen.putdata(pixeles)
    paleta = []
    for color in colores:
        r, g, b = color if color is not None else (0, 0, 0)
        paleta += [r << 3, g << 3, b << 3]
    imagen.putpalette(paleta)
    salida = io.BytesIO()
    imagen.save(salida, format="PNG",
                transparency=bytes(0 if t else 255 for t in transparentes))
    return salida.getvalue()


def convertir(png, bpp, columnas, prioridad=False, animaciones=(),
              max_tiles=None):
    """Converts an indexed PNG. Returns (tiles, cgram, tilemap, corridas).

    `animaciones` are lists of PNGs: the drawings of each one besides the
    image. `corridas` is, per animation, (first tile, how many, bytes of each
    drawing).
    """
    with tempfile.TemporaryDirectory(prefix="voodoo-") as d:
        entrada = os.path.join(d, "imagen.png")
        with open(entrada, "wb") as f:
            f.write(png)
        args = [binario(), "convert", entrada, "--bpp", str(bpp),
                "-o", os.path.join(d, "tiles.bin"),
                "--palette", os.path.join(d, "cgram.bin"),
                "--tilemap", os.path.join(d, "tilemap.bin"), "--json"]
        if prioridad:
            args.append("--priority")
        if max_tiles is not None:
            args += ["--max-tiles", str(max_tiles)]
        for a, dibujos in enumerate(animaciones):
            rutas = []
            for n, dibujo in enumerate(dibujos):
                ruta = os.path.join(d, "anim%d-%d.png" % (a, n))
                with open(ruta, "wb") as f:
                    f.write(dibujo)
                rutas.append(ruta)
            args += ["--animation", ",".join(rutas),
                     "--animation-out", os.path.join(d, "anim%d.bin" % a)]
        hecho = subprocess.run(args, capture_output=True, text=True)
        if hecho.returncode:
            raise SystemExit("voodoo exited with %d: %s"
                             % (hecho.returncode, hecho.stderr.strip()))
        informe = json.loads(hecho.stdout)

        def leer(nombre):
            with open(os.path.join(d, nombre), "rb") as f:
                return f.read()

        crudo = leer("tilemap.bin")
        palabras = [int.from_bytes(crudo[i:i + 2], "little")
                    for i in range(0, len(crudo), 2)]
        tilemap = [palabras[i:i + columnas]
                   for i in range(0, len(palabras), columnas)]
        corridas = []
        for a, corrida in enumerate(informe["animations"]):
            datos = leer("anim%d.bin" % a)
            largo = len(datos) // corrida["frames"] if corrida["frames"] else 0
            corridas.append((corrida["first"], corrida["tiles"],
                             [datos[i:i + largo]
                              for i in range(0, len(datos), largo or 1)]
                             if largo else [b""] * corrida["frames"]))
        return leer("tiles.bin"), leer("cgram.bin"), tilemap, corridas
