#!/usr/bin/env python3
"""Genera un fuente que ejerce cada entrada de las tablas de w65.py.

La ROM del proyecto tiene 271 bytes de instrucciones, y con eso alcanza para
verificar lo que el proyecto usa hoy. Pero las tablas de w65.py tienen unas
sesenta entradas más que nadie ejerce, y una entrada sin probar es una trampa
puesta para el día que alguien la use.

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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import w65

# Un símbolo que entra en un byte y otro que no, para forzar página directa y
# absoluto sin depender de en qué segmento esté declarado.
ZP_VALUE = 0x12
ABS_VALUE = 0x2140


def lines():
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
    for mnemonic in sorted(w65.IMPLIED):
        out.append("    %s" % mnemonic)

    out.append("; --- ramas, hacia atrás y hacia adelante ---")
    out.append("atras:")
    for mnemonic in sorted(w65.BRANCHES):
        out.append("    %s atras" % mnemonic)
    for mnemonic in sorted(w65.BRANCHES):
        out.append("    %s adelante" % mnemonic)
    out.append("adelante:")

    out.append("; --- inmediatos de un byte ---")
    out += ["    .a8", "    .i8"]
    for mnemonic, modes in sorted(w65.OPCODES.items()):
        if "imm" in modes:
            out.append("    %s #$12" % mnemonic)
        if "imm8" in modes:
            out.append("    %s #$12" % mnemonic)

    out.append("; --- inmediatos de dos bytes ---")
    out += ["    .a16", "    .i16"]
    for mnemonic, modes in sorted(w65.OPCODES.items()):
        if "imm" in modes:
            out.append("    %s #$1234" % mnemonic)
    out += ["    .a8", "    .i8"]

    out.append("; --- el resto de los modos ---")
    forms = [("acc", "%s a"), ("dp", "%s zp_sym"), ("abs", "%s abs_sym"),
             ("dpil", "%s [zp_sym]"), ("dpi", "%s (zp_sym)")]
    for mnemonic, modes in sorted(w65.OPCODES.items()):
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

    instructions = sum(1 for line in lines() if line.startswith("    ")
                       and not line.startswith("    ."))
    print("%s: %d instrucciones, %d mnemónicos"
          % (args.output, instructions,
             len(w65.IMPLIED) + len(w65.BRANCHES) + len(w65.OPCODES)))


if __name__ == "__main__":
    main()
