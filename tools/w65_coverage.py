#!/usr/bin/env python3
"""Genera un fuente que ejerce cada entrada de las tablas del ensamblador.

La ROM del proyecto tiene 271 bytes de instrucciones, y con eso alcanza para
verificar lo que el proyecto usa hoy. Pero las tablas del ensamblador tienen
unas sesenta entradas más que nadie ejerce, y una entrada sin probar es una
trampa puesta para el día que alguien la use.

Así que se arma un fuente sintético con cada mnemónico en cada modo de
direccionamiento que la tabla declara, se ensambla con las dos cadenas y se
comparan. Lo que valida no es una ROM sino la tabla entera.

Sólo tiene sentido correrlo mientras exista el contenedor con ca65: es el
patrón contra el que se compara. Una vez que dio idéntico, la tabla quedó
verificada y no hace falta volver a tenerlo.

Uso:
    python3 tools/w65_coverage.py -o /tmp/cobertura.s
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import w65_bin


def tablas():
    """Las tres tablas del ensamblador, leídas de `w65 --list-opcodes`.

    Se le preguntan **al ensamblador que se va a comparar** y no a una segunda
    copia escrita acá: una copia se desfasa en silencio, y el desfase tomaría
    justo la forma de "esta entrada dejó de estar cubierta", que es lo único
    que este generador existe para evitar. Hasta el 2026-09-15 las leía de
    `tools/w65.py`, que era el ensamblador de entonces.
    """
    salida = subprocess.run([w65_bin.binario(), "--list-opcodes"],
                            check=True, capture_output=True, text=True).stdout
    implicitos, ramas, modales = [], [], {}
    for linea in salida.splitlines():
        campos = linea.split()
        if campos[0] == "implied":
            implicitos.append(campos[1])
        elif campos[0] == "branch":
            ramas.append(campos[1])
        elif campos[0] == "modal":
            # `modal lda imm A9 dp A5 …`: pares modo/opcode, y acá sólo
            # interesa qué modos declara.
            modales[campos[1]] = set(campos[2::2])
        else:
            raise AssertionError("línea que no entiendo: %r" % linea)
    return implicitos, ramas, modales

# Un símbolo que entra en un byte y otro que no, para forzar página directa y
# absoluto sin depender de en qué segmento esté declarado.
ZP_VALUE = 0x12
ABS_VALUE = 0x2140


def lines():
    IMPLIED, BRANCHES, OPCODES = tablas()
    out = [
        "; Generado por tools/w65_coverage.py. No editar.",
        ".p816",
        ".smart",
        "zp_sym  = $%02X" % ZP_VALUE,
        "abs_sym = $%04X" % ABS_VALUE,
        "",
        '.segment "CODE"',
        "cobertura:",
    ]

    out.append("; --- implícitos ---")
    for mnemonic in sorted(IMPLIED):
        out.append("    %s" % mnemonic)

    out.append("; --- ramas, hacia atrás y hacia adelante ---")
    out.append("atras:")
    for mnemonic in sorted(BRANCHES):
        out.append("    %s atras" % mnemonic)
    for mnemonic in sorted(BRANCHES):
        out.append("    %s adelante" % mnemonic)
    out.append("adelante:")

    out.append("; --- inmediatos de un byte ---")
    out += ["    .a8", "    .i8"]
    for mnemonic, modes in sorted(OPCODES.items()):
        if "imm" in modes:
            out.append("    %s #$12" % mnemonic)
        if "imm8" in modes:
            out.append("    %s #$12" % mnemonic)

    out.append("; --- inmediatos de dos bytes ---")
    out += ["    .a16", "    .i16"]
    for mnemonic, modes in sorted(OPCODES.items()):
        if "imm" in modes:
            out.append("    %s #$1234" % mnemonic)
    out += ["    .a8", "    .i8"]

    out.append("; --- el resto de los modos ---")
    forms = [("acc", "%s a"), ("dp", "%s zp_sym"), ("abs", "%s abs_sym"),
             ("dpx", "%s zp_sym,x"), ("dpy", "%s zp_sym,y"),
             ("absx", "%s abs_sym,x"), ("absy", "%s abs_sym,y"),
             ("dpil", "%s [zp_sym]"), ("dpily", "%s [zp_sym],y"),
             ("dpi", "%s (zp_sym)"), ("dpiy", "%s (zp_sym),y")]
    for mnemonic, modes in sorted(OPCODES.items()):
        for mode, form in forms:
            if mode in modes:
                out.append("    " + form % mnemonic)

    out.append("; --- expresiones ---")
    out += [
        "    lda #<abs_sym",
        "    lda #>abs_sym",
        "    lda #^abs_sym",
        # .loword da dos bytes, así que necesita el índice ancho: con .i8 ca65
        # lo rechaza por rango, y hace bien.
        "    .i16",
        "    ldx #.loword(cobertura)",
        "    .i8",
        "    lda abs_sym + 2",
        "    lda zp_sym + 1",
        "    lda #zp_sym * 2",
        "    lda #zp_sym * 2 + 1",
        "    lda #(zp_sym + 1) * 2",
        "    lda #abs_sym / 256",
        "    lda #zp_sym | 1",
        "    lda #zp_sym & 15",
        "    rts",
    ]

    # ld65 pide que existan la cabecera y los vectores para llenar sus áreas.
    out += [
        "",
        '.segment "HEADER"',
        '    .byte "COBERTURA W65        "',
        "    .byte $20, $00, $05, $00, $01, $00, $00",
        "    .word $FFFF",
        "    .word $0000",
        "",
        '.segment "VECTORS"',
        "    .word $0000, $0000, $0000, $0000",
        "    .word $0000, $0000, $0000, $0000",
        "    .word $0000, $0000, $0000, $0000",
        "    .word $0000, $0000",
        "    .word cobertura",
        "    .word $0000",
    ]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    text = "\n".join(lines()) + "\n"
    with open(args.output, "w") as handle:
        handle.write(text)

    implicitos, ramas, modales = tablas()
    instructions = sum(1 for line in lines() if line.startswith("    ")
                       and not line.startswith("    ."))
    print("%s: %d instrucciones, %d mnemónicos"
          % (args.output, instructions,
             len(implicitos) + len(ramas) + len(modales)))


if __name__ == "__main__":
    main()
