.segment "FAR"

; Up to the end of bank 1, which is the end of `FAR`'s area: what it pads is
; what `rm2k-snes-space` reports as bank 1's free space.
.align $8000

; --- header and vectors ----------------------------------------------------
; The console reads this at `$00:FFC0`, which in ExHiROM is `$40FFC0` of the
; file: bank 0's copy, which the assembler writes next to the original —see
; `MIRRORS` in tools/rm2k-snes/cartridge/src/banks.rs—. The vectors below,
; the same.
.segment "HEADER"
    ; This is what the FX Pak menu shows and what any ROM database reads. The
    ; game declares it in its project file, and the converter emits it already
    ; padded to 21 characters: see `rom_identity`.
    .byte ROM_TITLE
    .byte $35                      ; ExHiROM, FastROM: see MEMSEL
    .byte $02                      ; ROM and battery-backed RAM: the saved game
    .byte $0D                      ; size: 8 MB (the byte is log2 of the KB)
    .byte $03                      ; SRAM: 8 KB, four slots of 2048
    .byte $01                      ; region
    .byte $00                      ; developer
    .byte $00                      ; version
    .word $FFFF                    ; checksum complement
    .word $0000                    ; checksum

.segment "VECTORS"
; From $FFE0 to $FFFF. The first eight are the native-mode vectors and the
; other eight the emulation-mode ones, which is the mode the console boots in.
; The one that matters is RESET, at $FFFC.
    .word $0000     ; $FFE0  unused
    .word $0000     ; $FFE2  unused
    .word $0000     ; $FFE4  native COP
    .word $0000     ; $FFE6  native BRK
    .word $0000     ; $FFE8  native ABORT
    .word nmi_boot  ; $FFEA  native NMI: counts the frames during boot
    .word $0000     ; $FFEC  unused
    .word irq_music ; $FFEE  native IRQ: the music, see `irq_music`
    .word $0000     ; $FFF0  unused
    .word $0000     ; $FFF2  unused
    .word $0000     ; $FFF4  emulation COP
    .word $0000     ; $FFF6  unused
    .word $0000     ; $FFF8  emulation ABORT
    .word $0000     ; $FFFA  emulation NMI
    .word reset     ; $FFFC  RESET
    .word $0000     ; $FFFE  emulation IRQ and BRK
