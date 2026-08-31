| ---------------------------------------------------------------------------
| boot.S - tabla de vectores, cabecera de cartucho y arranque
| ---------------------------------------------------------------------------

    .section .text.vectors, "ax"
    .globl  _vectors
_vectors:
    .long   0x00FFFE00              | stack pointer inicial
    .long   _start                  | PC inicial
    .rept   62
    .long   _halt                   | el resto de los vectores no hace nada
    .endr

| ---------------------------------------------------------------------------
    .section .text.header, "ax"
    .globl  _header
_header:
    .ascii  "SEGA MEGA DRIVE "      | 0x100  consola (16)
    .ascii  "(C)TARO 2026.AUG"      | 0x110  copyright (16)
    .ascii  "A BLURRED LINE - MAP RENDER                     "  | 0x120 (48)
    .ascii  "A BLURRED LINE - MAP RENDER                     "  | 0x150 (48)
    .ascii  "GM 00000000-00"        | 0x180  serial (14)
    .word   0x0000                  | 0x18E  checksum (lo parchea md_fixrom.py)
    .ascii  "J               "      | 0x190  dispositivos de IO (16)
    .long   0x00000000              | 0x1A0  inicio de ROM
    .long   0x00000000              | 0x1A4  fin de ROM (lo parchea md_fixrom.py)
    .long   0x00FF0000              | 0x1A8  inicio de RAM
    .long   0x00FFFFFF              | 0x1AC  fin de RAM
    .ascii  "            "          | 0x1B0  info de SRAM (12)
    .ascii  "                                        "  | 0x1BC  notas (40)
    .ascii  "JUE             "      | 0x1E4  region: anda en cualquiera

| ---------------------------------------------------------------------------
    .text
    .globl  _start
_start:
    move.w  #0x2700, %sr            | interrupciones enmascaradas
    move.l  #0x00FFFE00, %sp

    | TMSS: las consolas modelo 1 y posteriores piden que el cartucho escriba
    | "SEGA" en 0xA14000 antes de dejar tocar el VDP.
    move.b  0x00A10001, %d0
    andi.b  #0x0F, %d0
    beq     1f
    move.l  #0x53454741, 0x00A14000 | "SEGA"
1:
    | Frenar el Z80 y dejarlo en reset: no lo usamos y así no molesta.
    move.w  #0x0100, 0x00A11100
    move.w  #0x0100, 0x00A11200

    | Callar los cuatro canales del PSG. En un emulador arrancan en silencio,
    | pero una consola de verdad puede zumbar apenas se enciende si nadie les
    | pone la atenuación al máximo.
    move.b  #0x9F, 0x00C00011
    move.b  #0xBF, 0x00C00011
    move.b  #0xDF, 0x00C00011
    move.b  #0xFF, 0x00C00011

    | Limpiar la RAM de trabajo entera.
    lea     0x00FF0000, %a0
    move.w  #0x3FFF, %d0
2:  clr.l   (%a0)+
    dbra    %d0, 2b

    jsr     main

    .globl  _halt
_halt:
    bra     _halt
