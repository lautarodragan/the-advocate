#!/usr/bin/env python3
"""Arma `exhirom.sfc`: la prueba del mapa de memoria de 8 MB, ExHiROM. Qué
hace la ROM y qué quiere decir cada franja de la pantalla, en el
encabezado de `prueba.s`; lo corre `just exhirom`, que después la verifica
en los emuladores con `verificar.py`.

    armar.py <salida.sfc>

El archivo son 8 MB de bytes pseudoaleatorios —un xorshift de semilla
fija, como el `.msu` de `msu-puerto`—, para que un banco mal mapeado no
pueda pasar por bueno: con un patrón regular, leer el banco de al lado
podría dar la misma suma. Encima van los 32 KB del código **dos veces**: en
`$008000`, que es `$80:8000` y `$C0:8000` en la consola, y en `$408000`,
que es `$00:8000` —donde la consola busca la cabecera y los vectores— y
también lo que Mednafen lee en `$80:8000` (ver `MEDNAFEN` abajo).

La ROM suma por palabras cada tramo de `CHEQUEOS` y compara con lo que
dice este script en `esperado.inc`: la suma de los bytes que el tramo
tiene que tener según el mapa de ExHiROM (`consola`), y la de los que
tendría según el de Mednafen (`mednafen`), que no es el mismo.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

LARGO = 8 << 20
BANCO = 0x10000
CODIGO = 0x8000
# Dónde va el código en el archivo: las dos copias. Ninguna suma puede
# caer encima de éstas, porque ahí no está el patrón.
COPIAS = (0x008000, 0x408000)
CABECERA = 0x7FC0               # dentro de los 32 KB del código


def consola(direccion):
    """El desplazamiento en el archivo de una dirección de la CPU, según el
    mapa de ExHiROM: los primeros 4 MB en `$C0-$FF` —y sus mitades altas
    en `$80-$BF`—, los segundos en `$40-$7D` —y sus mitades altas en
    `$00-$3F`—. Es la inversión de A23 que hace el cartucho: el FX Pak la
    hace igual (`address.v` de sd2snes, `{!A23, A21:0}`)."""
    banco, dentro = direccion >> 16, direccion & 0xFFFF
    if banco >= 0xC0:
        return (banco - 0xC0) << 16 | dentro
    if banco >= 0x80:
        assert dentro >= 0x8000, hex(direccion)
        return (banco - 0x80) << 16 | dentro
    if 0x40 <= banco < 0x7E:
        return 0x400000 | (banco - 0x40) << 16 | dentro
    assert banco < 0x40 and dentro >= 0x8000, hex(direccion)
    return 0x400000 | banco << 16 | dentro


def mednafen(direccion):
    """Lo mismo según `snes_faust` de Mednafen 1.32 (`cart.cpp`): a todo
    banco menor que `$C0` le suma 4 MB, **también a `$80-$BF`**, así que
    ahí lee los segundos 4 MB y no los primeros. En lo demás coincide."""
    if direccion >> 16 >= 0xC0:
        return direccion & 0x3FFFFF
    return 0x400000 + (direccion & 0x3FFFFF)


# Los tramos que la ROM suma: (dirección, largo, franja). La franja es la
# de la pantalla donde se ve el resultado; ver `prueba.s`.
CHEQUEOS = (
    # 1: los primeros 4 MB por `$C0-$FF`, los bancos rápidos. Uno entero
    # al principio, uno al medio y el último, y 256 bytes de cada banco.
    [(0xC00000, 0x8000, 1), (0xC10000, BANCO, 1), (0xE50000, BANCO, 1),
     (0xFF0000, BANCO, 1)]
    + [((b << 16), 0x100, 1) for b in range(0xC1, 0x100)]
    # 2: los segundos 4 MB por `$40-$7D`, igual, salvo las mitades bajas de
    # `$70-$7D`, que van aparte.
    + [(0x400000, 0x8000, 2), (0x410000, BANCO, 2), (0x600000, BANCO, 2),
       (0x6F0000, BANCO, 2), (0x7D8000, 0x8000, 2)]
    + [((b << 16), 0x100, 2) for b in range(0x41, 0x70)]
    + [((b << 16) | 0x8000, 0x100, 2) for b in range(0x70, 0x7E)]
    # 3: las mitades altas de los segundos 4 MB por `$00-$3F`: las de
    # `$7E` y `$7F`, que tapa la WRAM y sólo se ven por `$3E` y `$3F`, y
    # dos más.
    + [(0x3E8000, 0x8000, 3), (0x3F8000, 0x8000, 3), (0x208000, 0x8000, 3),
       (0x018000, 0x8000, 3)]
    # 4: las mitades altas de los primeros 4 MB por `$80-$BF`. Es donde
    # Mednafen no hace lo que la consola.
    + [(0x818000, 0x8000, 4), (0x9F8000, 0x8000, 4), (0xBF8000, 0x8000, 4)]
    # 5: las mitades bajas de `$70-$7D`. En el cartucho son ROM, pero
    # mesen-s, Mesen2 y el módulo `snes` de Mednafen ponen ahí la SRAM de
    # LoROM también en ExHiROM, así que el juego no las puede usar.
    + [(0x7D0000, 0x8000, 5)]
    + [((b << 16), 0x100, 5) for b in range(0x70, 0x7E)]
)


def contenido():
    estado = 0x2545F491
    out = bytearray(LARGO)
    for i in range(0, LARGO, 4):
        estado ^= (estado << 13) & 0xFFFFFFFF
        estado ^= estado >> 17
        estado ^= (estado << 5) & 0xFFFFFFFF
        out[i:i + 4] = estado.to_bytes(4, "little")
    return out


def suma(datos):
    """La de la ROM: por palabras, módulo 65536."""
    return sum(int.from_bytes(datos[i:i + 2], "little")
               for i in range(0, len(datos), 2)) & 0xFFFF


def tramo(datos, desde, largo):
    for copia in COPIAS:
        assert desde + largo <= copia or desde >= copia + CODIGO, (
            "el tramo $%06X cae sobre el código" % desde)
    return datos[desde:desde + largo]


def main():
    salida = os.path.abspath(sys.argv[1])
    directorio = os.path.dirname(salida)
    os.makedirs(directorio, exist_ok=True)
    datos = contenido()
    with open(os.path.join(directorio, "esperado.inc"), "w") as f:
        f.write("CHEQUEOS_N = %d\n\nchequeos:\n" % len(CHEQUEOS))
        f.write("; dirección, franja, palabras, suma esperada, la de Mednafen\n")
        for direccion, largo, franja in CHEQUEOS:
            esperada = suma(tramo(datos, consola(direccion), largo))
            otra = suma(tramo(datos, mednafen(direccion), largo))
            f.write("    .faraddr $%06X\n    .byte %d\n    .word $%04X, $%04X, $%04X\n"
                    % (direccion, franja, largo // 2, esperada, otra))
    objeto = os.path.join(directorio, "prueba.o")
    codigo = os.path.join(directorio, "codigo.bin")
    subprocess.run(["ca65", "-g", "--cpu", "65816", "-I", directorio,
                    os.path.join(AQUI, "prueba.s"), "-o", objeto], check=True)
    subprocess.run(["ld65", "-C", os.path.join(AQUI, "memoria.cfg"), objeto,
                    "-o", codigo, "--dbgfile", salida + ".dbg"], check=True)
    with open(codigo, "rb") as f:
        bloque = f.read()
    assert len(bloque) == CODIGO, len(bloque)
    for copia in COPIAS:
        datos[copia:copia + CODIGO] = bloque
    # La suma de la cabecera, en las dos copias: el FX Pak la puntúa al
    # elegir dónde está la cabecera, y la que gana es la de $40FFC0
    # porque el mapeo $35 le suma ahí (`smc_headerscore` de sd2snes). Las
    # dos copias valen $FFFF y $0000 antes de escribirla, así que la suma
    # no cambia al escribirla en las dos.
    total = sum(datos) & 0xFFFF
    for copia in COPIAS:
        c = copia + CABECERA
        datos[c + 0x1C:c + 0x1E] = (total ^ 0xFFFF).to_bytes(2, "little")
        datos[c + 0x1E:c + 0x20] = total.to_bytes(2, "little")
    assert sum(datos) & 0xFFFF == total
    with open(salida, "wb") as f:
        f.write(datos)
    print("%s (%d bytes, %d tramos)" % (salida, len(datos), len(CHEQUEOS)))


if __name__ == "__main__":
    main()
