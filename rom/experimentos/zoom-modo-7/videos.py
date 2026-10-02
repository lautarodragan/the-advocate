#!/usr/bin/env python3
"""Un video por foto y variante: el original a la izquierda y la ROM a la
derecha, sincronizados por el final del zoom, con el sonido del original.

    videos.py <zoom-modo-7.sfc> <originales> <salida>

`<originales>` es el directorio de las escenas capturadas del RPG_RT: una
carpeta por foto que lleva su nombre (`212-PhoneCallDiff/`), con el mapa
entero en un `escena*.mp4` a 640x480 y 60 cuadros por segundo. Deja en
`<salida>` un `<n>-<foto>-<variante>.mp4` por cada una.

**Se sincronizan por el final del zoom**, el primer cuadro negro después
de la foto, y no por el destello: en el 212 la foto se queda quieta 25
cuadros más que en los otros tres —lo que se ve a la izquierda—, y la ROM
usa los 93 de los otros.

La ROM se graba en snes9x, cuadro a cuadro, y se agranda al doble con el
vecino más cercano: los pixeles se ven.
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, os.pardir, "tools"))
sys.path.insert(0, AQUI)
from emulator import retro  # noqa: E402
from verificar import Corrida, palabra, CUADRO  # noqa: E402
from armar import FOTOS, VARIANTES, NEGRO_ANTES, QUIETA, ZOOM, NEGRO_DESPUES  # noqa: E402

VUELTA = NEGRO_ANTES + QUIETA + ZOOM + NEGRO_DESPUES
# El primer cuadro negro después de la foto, en la vuelta de la ROM.
FIN_ROM = NEGRO_ANTES + QUIETA - 1 + ZOOM


def la_escena(originales, nombre):
    carpetas = [c for c in glob.glob(os.path.join(originales, "*")) if nombre in os.path.basename(c)]
    if not carpetas:
        sys.exit("no hay una carpeta de %s en %s" % (nombre, originales))
    videos = sorted(glob.glob(os.path.join(carpetas[0], "escena*.mp4")))
    if not videos:
        sys.exit("no hay un escena*.mp4 en %s" % carpetas[0])
    return videos[0]


def fin_del_zoom(video):
    """El cuadro en que la foto termina de achicarse: el primero sin nada,
    después de uno con algo y de treinta cuadros de foto chica —entre un
    sexto y un tercio del ancho—. Es el primero de la escena: el video del
    212 sigue con el principio del 213. Mirar el cuadro más claro no
    alcanza, porque el 212 no tiene destello."""
    crudo = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", video, "-vf", "scale=160:120",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           check=True, capture_output=True).stdout
    cuadros = np.frombuffer(crudo, np.uint8).reshape(-1, 120, 160)
    columnas = (cuadros > 6).any(1)
    ancho = [int(np.ptp(np.nonzero(c)[0])) + 1 if c.any() else 0 for c in columnas]
    for i in range(30, len(ancho)):
        if ancho[i] == 0 and ancho[i - 1] > 0 and 25 <= ancho[i - 30] <= 55:
            return i
    sys.exit("%s: no encontré el final del zoom" % video)


def grabar(corrida, directorio):
    """Una vuelta entera, desde su primer cuadro, como PNG numerados."""
    for _ in range(VUELTA * 2):
        corrida.consola.run(1)
        if palabra(corrida.consola, CUADRO) == 1:
            break
    for n in range(VUELTA):
        corrida.consola.image().save(os.path.join(directorio, "%04d.png" % n))
        corrida.consola.run(1)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    rom, originales, salida = sys.argv[1:]
    os.makedirs(salida, exist_ok=True)
    corrida = Corrida("snes9x", rom)
    corrida.apretar("b")                    # sin los números de la esquina
    for f, (nombre, _, _) in enumerate(FOTOS):
        escena = la_escena(originales, nombre)
        desde = fin_del_zoom(escena) - FIN_ROM
        for v, variante in enumerate(VARIANTES):
            corrida.ir_a(f, v)
            destino = os.path.join(salida, "%d-%s-%s.mp4" % (f + 1, nombre, variante["nombre"]))
            with tempfile.TemporaryDirectory() as cuadros:
                grabar(corrida, cuadros)
                subprocess.run([
                    "ffmpeg", "-loglevel", "error", "-y",
                    "-ss", "%.4f" % (max(desde, 0) / 60), "-t", "%.4f" % (VUELTA / 60), "-i", escena,
                    "-framerate", "60", "-i", os.path.join(cuadros, "%04d.png"),
                    "-filter_complex",
                    "[0:v]tpad=start=%d:color=black[o];"
                    "[1:v]scale=512:448:flags=neighbor,pad=512:480:0:16:black[r];"
                    "[o][r]hstack=inputs=2,format=yuv420p[v]" % max(-desde, 0),
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "16",
                    "-preset", "slow", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-movflags", "+faststart", destino], check=True)
            print(destino)


if __name__ == "__main__":
    main()
