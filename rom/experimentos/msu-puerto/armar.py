#!/usr/bin/env python3
"""Arma `msu-puerto.sfc` y su `.msu`: la prueba del puerto de datos del
MSU-1. Qué hace la ROM, en el encabezado de `puerto.s`; lo corre `just
msu-puerto`, que después la mide en los emuladores con `medir.py`.

    armar.py <salida.sfc>

El `.msu` es 1 MB de bytes pseudoaleatorios —un xorshift de semilla fija—,
para que un byte viejo o repetido no pueda pasar por bueno: con un patrón
regular, un búfer sin rellenar a tiempo podría devolver justo lo que se
esperaba. La ROM compara cada tramo de 32 KB contra la suma que se escribe
acá en `esperado.inc`.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

# El tamaño del `.msu`. Un mega alcanza para buscar lejos —la prueba 1 va a
# $0C0000— y para los 512 KB seguidos desde $040000.
LARGO = 1 << 20
TRAMO = 0x8000

# Los tramos que la ROM compara, en el orden en que los lee: ver `puerto.s`.
TRAMOS = [0x000000, 0x0C0000] + [0x040000 + i * TRAMO for i in range(16)]


def contenido():
    estado = 0x2545F491
    out = bytearray(LARGO)
    for i in range(0, LARGO, 4):
        estado ^= (estado << 13) & 0xFFFFFFFF
        estado ^= estado >> 17
        estado ^= (estado << 5) & 0xFFFFFFFF
        out[i:i + 4] = estado.to_bytes(4, "little")
    return bytes(out)


def suma(datos):
    """La de la ROM: por palabras, módulo 65536."""
    return sum(int.from_bytes(datos[i:i + 2], "little")
               for i in range(0, len(datos), 2)) & 0xFFFF


def main():
    salida = os.path.abspath(sys.argv[1])
    directorio = os.path.dirname(salida)
    os.makedirs(directorio, exist_ok=True)
    datos = contenido()
    with open(os.path.splitext(salida)[0] + ".msu", "wb") as f:
        f.write(datos)
    with open(os.path.join(directorio, "esperado.inc"), "w") as f:
        f.write("esperado:\n")
        for t in TRAMOS:
            f.write("    .word $%04X  ; $%06X\n" % (suma(datos[t:t + TRAMO]), t))
    objeto = os.path.join(directorio, "puerto.o")
    subprocess.run(["ca65", "-g", "--cpu", "65816", "-I", directorio,
                    os.path.join(AQUI, "puerto.s"), "-o", objeto], check=True)
    subprocess.run(["ld65", "-C", os.path.join(AQUI, "memoria.cfg"), objeto,
                    "-o", salida, "--dbgfile", salida + ".dbg"], check=True)
    # La suma del encabezado, como en `menu-modo-5`: el FX Pak la muestra.
    with open(salida, "rb") as f:
        rom = bytearray(f.read())
    rom[0x7FDC:0x7FE0] = b"\xff\xff\x00\x00"
    total = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (total ^ 0xFFFF).to_bytes(2, "little")
    rom[0x7FDE:0x7FE0] = total.to_bytes(2, "little")
    with open(salida, "wb") as f:
        f.write(rom)
    print("%s (%d bytes) y su .msu de %d" % (salida, len(rom), LARGO))


if __name__ == "__main__":
    main()
