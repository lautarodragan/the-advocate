| ---------------------------------------------------------------------------
| boot.S - tabla de vectores, cabecera de cartucho y entry point
| ---------------------------------------------------------------------------

    .section .text.vectors, "ax"
    .globl  _vectors
_vectors:
    .long   0x00FFFE00              | SP inicial (tope de la RAM de 64K)
    .long   _start                  | PC inicial
    .rept   62
    .long   _except                 | todo lo demas: no hacer nada
    .endr

| ---------------------------------------------------------------------------
    .section .text.header, "ax"
    .globl  _header
_header:
    .ascii  "SEGA MEGA DRIVE "      | 0x100  consola (16)
    .ascii  "(C)TARO 2026.AUG"      | 0x110  copyright (16)
    .ascii  "RM2K PoC                                        "  | 0x120 (48)
    .ascii  "RM2K PoC                                        "  | 0x150 (48)
    .ascii  "GM 00000000-00"        | 0x180  serial (14)
    .word   0x0000                  | 0x18E  checksum (lo parchea fixrom.py)
    .ascii  "J               "      | 0x190  dispositivos de IO (16)
    .long   0x00000000              | 0x1A0  inicio de ROM
    .long   0x00000000              | 0x1A4  fin de ROM  (lo parchea fixrom.py)
    .long   0x00FF0000              | 0x1A8  inicio de RAM
    .long   0x00FFFFFF              | 0x1AC  fin de RAM
    .ascii  "            "          | 0x1B0  info de SRAM (12)
    .ascii  "                                        "  | 0x1BC notas (40)
    .ascii  "JUE             "      | 0x1E4  region (16)

| ---------------------------------------------------------------------------
    .text
    .globl  _start
_start:
    move.w  #0x2700, %sr            | interrupciones enmascaradas
    move.l  #0x00FFFE00, %sp

    | limpiar .bss
    lea     _bss_start, %a0
    lea     _bss_end, %a1
1:  cmp.l   %a1, %a0
    bcc     2f
    clr.l   (%a0)+
    bra     1b

2:  jsr     main
3:  bra     3b                      | main no deberia volver

    .globl  _except
_except:
    rte
