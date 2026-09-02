#!/usr/bin/env python3
"""Recorta la ventana del emulador de una captura del display entero.

Capturar la raíz de Xvfb es lo más difícil de romper, pero trae 640x480 de los
cuales la consola ocupa 256x224 y el resto es el fondo negro del servidor X. Lo
que hace falta es quedarse con el rectángulo de adentro.

Lo correcto es que el que captura le pregunte a X dónde está la ventana y lo
pase con --en: es un dato, no una inferencia. Deducirlo de los pixeles falla
justo donde más duele, porque el fondo del servidor es negro y un mapa con el
borde de arriba negro se confunde con él: el recorte se desliza hacia abajo y
la comparación falla por algo que no tiene que ver con la ROM. Pasó con el mapa
1, que es casi todo negro, en cuanto los sprites dejaron de dibujarse envueltos
en las filas de arriba.

Sin --en se cae al método viejo, que busca el primer pixel distinto del fondo y
ancla ahí. Sirve de red, pero avisa.
"""

import argparse
import sys

from PIL import Image

WIDTH, HEIGHT = 256, 224


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entrada")
    parser.add_argument("salida")
    parser.add_argument("--en", nargs=2, type=int, metavar=("X", "Y"),
                        help="esquina de la ventana del emulador, como la "
                             "reporta X")
    args = parser.parse_args()

    image = Image.open(args.entrada).convert("RGB")

    if args.en:
        x0, y0 = args.en
        origen = "X"
    else:
        x0, y0 = por_contenido(image)
        origen = "los pixeles"
        print("aviso: nadie pasó --en, así que el recorte se dedujo del "
              "contenido. Si el mapa arranca en negro esto se corre.",
              file=sys.stderr)

    if not (0 <= x0 <= image.width - WIDTH and 0 <= y0 <= image.height - HEIGHT):
        sys.exit("la ventana en %d,%d no entra en la captura de %dx%d"
                 % (x0, y0, image.width, image.height))

    crop = image.crop((x0, y0, x0 + WIDTH, y0 + HEIGHT))
    crop.save(args.salida)
    print("captura -> %s (%dx%d, recortada de %dx%d en %d,%d según %s)"
          % (args.salida, crop.width, crop.height,
             image.width, image.height, x0, y0, origen))


def por_contenido(image):
    """La esquina deducida del primer pixel que no es del color de fondo."""
    pixels = image.load()

    # El fondo del servidor X es el color de la esquina, que la ventana del
    # emulador nunca cubre si es más chica que la pantalla.
    background = pixels[0, 0]

    left, top = image.width, image.height
    right = bottom = 0
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] != background:
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)

    if right < left:
        sys.exit("la captura está toda del color de fondo: el emulador no dibujó")

    # El contenido puede tener bordes del mismo color que el fondo del servidor,
    # así que en vez de confiar en el rectángulo medido se lo lleva al tamaño
    # exacto de la consola, anclado donde empieza lo que sí se ve.
    return (max(0, min(left, image.width - WIDTH)),
            max(0, min(top, image.height - HEIGHT)))


if __name__ == "__main__":
    main()
