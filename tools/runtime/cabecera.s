.segment "FAR"

; Hasta el próximo banco: los datos generados arrancan pegados a uno, que es lo
; único que `tools/ensamblado/bancos.py` supone del mapa de memoria.
.align $8000

; --- cabecera y vectores ---------------------------------------------------
.segment "HEADER"
    ; Es lo que muestra el menú del FX Pak y lo que lee cualquier base de datos
    ; de ROMs. Decía "ABL SNES MUSIC POC" hasta el 2026-09-09, de cuando esto era
    ; una prueba de audio; en hardware se ve, así que dejó de dar igual.
    .byte "A BLURRED LINE       "  ; 21 caracteres
    .byte $30                      ; LoROM, FastROM: ver MEMSEL
    .byte $02                      ; ROM y RAM con batería: la partida guardada
    .byte $0C                      ; tamaño: 4 MB (el byte es log2 de los KB)
    .byte $05                      ; SRAM: 32 KB, y se usan cuatro ranuras de 2048
    .byte $01                      ; región
    .byte $00                      ; desarrollador
    .byte $00                      ; versión
    .word $FFFF                    ; complemento del checksum
    .word $0000                    ; checksum

.segment "VECTORS"
; De $FFE0 a $FFFF. Los primeros ocho son los vectores del modo nativo y los
; otros ocho los del modo emulación, que es en el que arranca la consola. El
; que importa es RESET, en $FFFC.
    .word $0000     ; $FFE0  sin usar
    .word $0000     ; $FFE2  sin usar
    .word $0000     ; $FFE4  COP nativo
    .word $0000     ; $FFE6  BRK nativo
    .word $0000     ; $FFE8  ABORT nativo
    .word nmi_boot  ; $FFEA  NMI nativo: cuenta los cuadros del arranque
    .word $0000     ; $FFEC  sin usar
    .word irq_musica ; $FFEE  IRQ nativo: la música, ver `irq_musica`
    .word $0000     ; $FFF0  sin usar
    .word $0000     ; $FFF2  sin usar
    .word $0000     ; $FFF4  COP en emulación
    .word $0000     ; $FFF6  sin usar
    .word $0000     ; $FFF8  ABORT en emulación
    .word $0000     ; $FFFA  NMI en emulación
    .word reset     ; $FFFC  RESET
    .word $0000     ; $FFFE  IRQ y BRK en emulación
