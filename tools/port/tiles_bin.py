"""`tiles`, el binario que convierte una imagen que ya entra en tiles.

Recibe un PNG indexado de 8 bits cuyos índices son entradas de CGRAM —en una
capa de 4bpp, `índice >> 4` es la paleta— y devuelve tiles, tilemap y CGRAM.
**No decide nada que se vea**: qué colores quedan y en qué paleta va cada
celda lo decidió el asignador antes de escribir la imagen. Ver "El asignador
corre primero" en ESTADO.md.

Se consume desde el PATH, como `brr` y `ca65`: se instala con `just
herramientas` y ningún script llama a `cargo`.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile

FALTA = """falta `tiles`, el conversor de imágenes a tiles.

Es un binario de Rust que vive en `tools/tiles/` y se instala como herramienta del
sistema:

    just herramientas"""


def binario():
    """La ruta del `tiles` del PATH. Sale con el mensaje si no está."""
    ruta = shutil.which("tiles")
    if ruta is None:
        raise SystemExit(FALTA)
    return ruta


def version():
    """Qué produjo lo que haya en un caché: este archivo y el binario
    instalado, que es lo que de verdad convirtió."""
    h = hashlib.sha256()
    for ruta in (os.path.abspath(__file__), binario()):
        with open(ruta, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def png_indexado(ancho, alto, pixeles, colores, transparentes):
    """Los bytes de un PNG indexado de 8 bits.

    `colores` son las 256 entradas de CGRAM en 15 bits, o None. `transparentes`
    dice qué entradas no dibujan: no le importa a `tiles`, que lo sabe por la
    profundidad, pero sí a quien abra la imagen para mirarla.
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
    """Convierte un PNG indexado. Devuelve (tiles, cgram, tilemap, corridas).

    `animaciones` son listas de PNG: los dibujos de cada una además de la
    imagen. `corridas` es, por animación, (primer tile, cuántos, bytes de cada
    dibujo).
    """
    with tempfile.TemporaryDirectory(prefix="tiles-") as d:
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
            raise SystemExit("tiles salió con %d: %s"
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
