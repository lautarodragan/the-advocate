#!/usr/bin/env python3
"""Compara la ROM de w65.py contra la de ca65 + ld65, byte por byte.

Es la razón por la que se puede confiar en un ensamblador propio. Mientras el
contenedor de Debian con cc65 exista, se ensambla el mismo fuente con las dos
cadenas y se comparan los 32.768 bytes. Si son idénticos, w65.py es correcto
para todo lo que este proyecto usa; y como el proyecto no usa nada que no esté
en rom/src/main.s, eso alcanza.

Cuando difieren, mostrar el primer byte distinto no sirve de mucho: un byte de
más corre todo lo que sigue y parecen miles de diferencias. Por eso se informa
también cuántas hay y en qué región caen, que es lo que dice si el problema es
un opcode suelto o un tamaño mal calculado.

Uso:
    python3 tools/w65_check.py rom/build/abl.sfc rom/build/referencia.sfc
"""

import sys

# El mapa de la ROM, para ubicar las diferencias en algo que se entienda.
REGIONS = [
    (0x0000, 0x7FC0, "código y datos"),
    (0x7FC0, 0x7FE0, "cabecera"),
    (0x7FE0, 0x8000, "vectores"),
]


def region(offset):
    for start, end, name in REGIONS:
        if start <= offset < end:
            return name
    return "fuera del mapa"


def main():
    if len(sys.argv) != 3:
        sys.exit("uso: w65_check.py NUESTRA.sfc REFERENCIA.sfc")

    ours = open(sys.argv[1], "rb").read()
    theirs = open(sys.argv[2], "rb").read()

    print("w65.py: %d bytes" % len(ours))
    print("ca65:   %d bytes" % len(theirs))

    # Los dos tamaños ya no coinciden: w65.py arma el cartucho entero, que son
    # 256 KB, y snes.cfg describe uno de 32. Lo que se compara es el primer
    # banco, que es donde el fuente de cobertura pone todo, y del resto se
    # comprueba que sea relleno: si w65.py hubiera emitido algo ahí, sería un
    # byte que no pidió nadie.
    if len(ours) < len(theirs):
        print("DIFIEREN en el tamaño: la nuestra es más corta.")
        return 1
    sobra = ours[len(theirs):]
    if sobra.strip(b"\x00"):
        print("DIFIEREN: hay %d bytes distintos de cero fuera del primer banco."
              % len(sobra.strip(b"\x00")))
        return 1
    ours = ours[:len(theirs)]

    diffs = [i for i in range(len(ours)) if ours[i] != theirs[i]]
    if not diffs:
        print("IDÉNTICAS: %d bytes byte por byte, y el resto relleno."
              % len(ours))
        return 0

    print("DIFIEREN en %d bytes de %d (%.2f%%)"
          % (len(diffs), len(ours), 100 * len(diffs) / len(ours)))

    by_region = {}
    for offset in diffs:
        by_region.setdefault(region(offset), []).append(offset)
    for name, offsets in by_region.items():
        print("  %-16s %5d diferencias, la primera en $%04X"
              % (name, len(offsets), offsets[0]))

    first = diffs[0]
    start = max(0, first - 8)
    print()
    print("desde $%04X:" % start)
    print("  w65:  %s" % " ".join("%02X" % b for b in ours[start:first + 8]))
    print("  ca65: %s" % " ".join("%02X" % b for b in theirs[start:first + 8]))
    print("        %s^^ primera diferencia en $%04X"
          % ("   " * (first - start), first))
    return 1


if __name__ == "__main__":
    sys.exit(main())
