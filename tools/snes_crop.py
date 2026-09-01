#!/usr/bin/env python3
"""Recorta la ventana del emulador de una captura del display entero.

Capturar la raíz de Xvfb es lo más difícil de romper, pero trae 640x480 de los
cuales la consola ocupa 256x224 y el resto es el fondo negro del servidor X. Lo
que hace falta es quedarse con el rectángulo de adentro.

No se busca "lo que no es negro": un mapa puede tener bordes negros propios y
el recorte se comería filas de verdad. Se busca el rectángulo de 256x224 —el
tamaño exacto de la pantalla de la consola— cuya posición explique mejor dónde
hay contenido. Como el emulador centra su ventana, alcanza con encontrar el
primer pixel distinto del fondo y ajustar desde ahí.
"""

import sys

from PIL import Image

WIDTH, HEIGHT = 256, 224


def main():
    if len(sys.argv) != 3:
        sys.exit("uso: snes_crop.py ENTRADA.png SALIDA.png")

    image = Image.open(sys.argv[1]).convert("RGB")
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
    x0 = max(0, min(left, image.width - WIDTH))
    y0 = max(0, min(top, image.height - HEIGHT))

    crop = image.crop((x0, y0, x0 + WIDTH, y0 + HEIGHT))
    crop.save(sys.argv[2])
    print("captura -> %s (%dx%d, recortada de %dx%d en %d,%d)"
          % (sys.argv[2], crop.width, crop.height,
             image.width, image.height, x0, y0))


if __name__ == "__main__":
    main()
