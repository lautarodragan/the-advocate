#!/usr/bin/env python3
"""Completa la cabecera del cartucho: tamaño de la ROM y checksum.

La Mega Drive quiere el tamaño de la ROM en 0x1A4 y un checksum en 0x18E. El
checksum es la suma de todas las palabras desde 0x200 hasta el final, módulo
65536. Ningún emulador lo verifica, pero el hardware con TMSS sí mira la
cabecera y cuesta dos líneas hacerlo bien.
"""

import argparse
import struct
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom")
    parser.add_argument("--pad", type=int, default=0, metavar="KB",
                        help="rellenar con ceros hasta este tamaño en KB. Los "
                             "cartuchos de verdad son potencias de dos y algún "
                             "mapper puede asumirlo")
    args = parser.parse_args()

    path = args.rom
    with open(path, "rb") as handle:
        rom = bytearray(handle.read())

    if args.pad:
        rom += bytes(max(0, args.pad * 1024 - len(rom)))

    # El tamaño tiene que ser par para que el checksum recorra palabras enteras.
    if len(rom) % 2:
        rom.append(0)

    struct.pack_into(">I", rom, 0x1A4, len(rom) - 1)
    checksum = sum(struct.unpack(">%dH" % ((len(rom) - 0x200) // 2),
                                 rom[0x200:])) & 0xFFFF
    struct.pack_into(">H", rom, 0x18E, checksum)

    with open(path, "wb") as handle:
        handle.write(rom)
    print("%s: %d bytes, checksum 0x%04X" % (path, len(rom), checksum))


if __name__ == "__main__":
    main()
