#!/usr/bin/env python3
"""Verifica el tinte de la consola contra la cuenta de Python, sin referencia.

Es una segunda opinión sobre `evento`, y mide otra cosa. Aquella compara
la consola contra el render de Python, o sea contra un camino entero: mapa,
paleta, sprites y evento. Esta toma dos capturas de la *misma* consola —una sin
teñir y otra teñida— y pregunta sólo si la transformación de una a la otra es
exactamente `canal * valor / 100` sobre los 15 bits.

Sirve cuando la comparación grande falla y hay que saber de qué lado está el
problema: si acá da cero, el tinte no es.

Uso:
    python3 tools/snes_tinte.py sin.png con.png --tinte 0 0 100
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eventos


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sin", help="la captura sin teñir")
    parser.add_argument("con", help="la misma pantalla, teñida por la consola")
    parser.add_argument("--tinte", nargs="+", type=int, default=[0, 0, 100],
                        metavar="N",
                        help="R G B [SAT], el tinte de RM2k, de 0 a 200 con "
                             "100 neutro. Sin la saturación se usa la neutra")
    args = parser.parse_args()

    sin = Image.open(args.sin).convert("RGB")
    con = Image.open(args.con).convert("RGB")
    if sin.size != con.size:
        sys.exit("las dos capturas tienen que medir lo mismo: %s contra %s"
                 % (sin.size, con.size))

    tinte = tuple(args.tinte)
    ps, pc = sin.load(), con.load()
    mal = 0
    peor = None
    for y in range(sin.height):
        for x in range(sin.width):
            r, g, b = ps[x, y]
            palabra = eventos.tenir(
                (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10), tinte)
            esperado = (palabra & 0x1F, (palabra >> 5) & 0x1F,
                        (palabra >> 10) & 0x1F)
            real = (pc[x, y][0] >> 3, pc[x, y][1] >> 3, pc[x, y][2] >> 3)
            if real != esperado:
                mal += 1
                if peor is None:
                    peor = (x, y, esperado, real)

    total = sin.width * sin.height
    print("%s teñida %d/%d/%d contra %s" % (args.sin, tinte[0], tinte[1],
                                            tinte[2], args.con))
    print("  pixeles distintos: %d de %d" % (mal, total))
    if peor:
        print("  el primero en (%d,%d): esperaba %s y hay %s" % peor)
        sys.exit(1)
    print("El tinte de la consola es el de Python, exacto.")


if __name__ == "__main__":
    main()
