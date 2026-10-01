; El mapa de memoria de 8 MB, ExHiROM: si la consola —o el emulador— ve
; cada banco donde el cartucho lo pone, si la SRAM está donde ExHiROM la
; pone, y si la ROM rápida es rápida. Es una prueba de hardware, no el
; juego; la arma `armar.py`, que pone el código dos veces en un archivo de
; 8 MB de bytes pseudoaleatorios y le pasa a esto la suma de cada tramo
; (`esperado.inc`).
;
; La pantalla son nueve franjas horizontales, de arriba abajo:
;
;   0  todo: verde si todo lo de abajo está bien, rojo si no
;   1  los primeros 4 MB, por $C0-$FF: tres bancos enteros, medio banco y
;      256 bytes de cada uno de los demás
;   2  los segundos 4 MB, por $40-$7D: igual, hasta $7D, el más alto, salvo
;      lo de la franja 5
;   3  las mitades altas de los segundos 4 MB, por $00-$3F: incluidas las
;      de $7E y $7F, que tapa la WRAM y sólo se ven por $3E y $3F
;   4  las mitades altas de los primeros 4 MB, por $80-$BF. **Amarillo**
;      si se ve lo que Mednafen pone ahí, que son los segundos 4 MB: no
;      es lo que hace el cartucho, y no rompe nada mientras el código esté
;      en los dos lugares —ver `armar.py`—, así que no pinta de rojo la 0
;   5  las mitades bajas de $70-$7D. En el cartucho son ROM; **amarillo** si
;      se ve otra cosa, que en mesen-s, Mesen2 y el módulo `snes` de
;      Mednafen es la SRAM. No cuenta para la 0: el juego no las usa
;   6  la SRAM: 8 KB escritos por $20:6000 y leídos por $A0:6000
;   7  la SRAM de un arranque al siguiente: **blanco** si encontró la marca
;      que dejó el arranque anterior, **gris** si es el primero. En la
;      consola se apaga y se prende: blanco quiere decir que la batería
;      —o la tarjeta del FX Pak— la guardó
;   8  FastROM: el mismo bucle corrido desde $C0 tiene que tardar menos que
;      desde $40, que siempre es lento
;
; Lo que mide queda en la WRAM desde RESULTADOS, para `verificar.py`, y
; una copia en la SRAM, en COPIA: es lo que se
; puede leer de Mednafen, que guarda la SRAM al salir.

.p816
.smart -

INIDISP  = $2100
CGADD    = $2121
CGDATA   = $2122
TM       = $212C
SLHV     = $2137
OPVCT    = $213D
STAT78   = $213F
NMITIMEN = $4200
HDMAEN   = $420C
MEMSEL   = $420D
DMAP0    = $4300
BBAD0    = $4301
A1T0L    = $4302
A1B0     = $4304

; Los resultados, en la WRAM baja.
RESULTADOS    = $0200
ESTADO        = RESULTADOS      ; 1 cuando terminó
ARRANQUES     = RESULTADOS + 1  ; los que encontró anotados en la SRAM
SRAM_MALOS    = RESULTADOS + 2  ; bytes de la SRAM que no volvieron
LINEAS_RAPIDO = RESULTADOS + 4  ; el bucle desde $C0, en líneas
LINEAS_LENTO  = RESULTADOS + 6  ; y desde $40
BARRAS        = RESULTADOS + 8  ; el color de cada franja, ver `colores`
GRUPOS        = RESULTADOS + 20 ; por franja 1-5: bit 0 algún tramo dio lo
                                ; esperado, bit 1 lo de Mednafen, bit 2 otra cosa
SUMAS         = RESULTADOS + 32 ; la suma de cada tramo, una palabra
HDMA_TABLA    = $0600

FRANJAS = 9

; Los colores de una franja.
ROJO     = 0
VERDE    = 1
AMARILLO = 2
BLANCO   = 3
GRIS     = 4

; La SRAM de ExHiROM: $6000-$7FFF de los bancos $20-$3F y $A0-$BF, 8 KB.
SRAM        = $206000
SRAM_ESPEJO = $A06000
COPIA       = $1E00             ; RESULTADOS, para leerlos de Mednafen
COPIA_LARGO = $01E0             ; hasta antes de la marca
MARCA       = $1FF0             ; ocho bytes, `marca`
CONTADOR    = $1FF8             ; los arranques, contando éste

; Las vueltas del bucle que se mide: 800 son unas 75 líneas desde la ROM
; rápida y unas 95 desde la lenta, lejos de las 262 de un cuadro, que es
; lo que el contador vertical puede medir sin dar la vuelta.
VUELTAS = 800

.segment "ZEROPAGE"
ptr:       .res 3
suma:      .res 2
indice:    .res 2               ; dónde está el tramo en `chequeos`
numero:    .res 2               ; y su número
grupo:     .res 2
temp:      .res 2

.segment "HEADER"
    .byte "ABL EXHIROM PRUEBA   "   ; 21 caracteres
    .byte $35                       ; ExHiROM, FastROM
    .byte $02                       ; ROM, RAM y batería
    .byte $0D                       ; 8 MB
    .byte $03                       ; 8 KB de SRAM
    .byte $01
    .byte $00
    .byte $00
    .word $FFFF                     ; complemento, lo escribe `armar.py`
    .word $0000                     ; suma, ídem

.segment "VECTORS"
    .word 0, 0, 0, 0, 0
    .word .loword(nada)
    .word 0
    .word .loword(nada)
    .word 0, 0, 0, 0, 0, 0
    .word .loword(reset)
    .word .loword(nada)

.segment "RODATA"
.include "esperado.inc"

marca:
    .byte "EXHIROM!"

colores:
    .word $001F                     ; rojo
    .word $03E0                     ; verde
    .word $03FF                     ; amarillo
    .word $7FFF                     ; blanco
    .word $3DEF                     ; gris

.segment "CODE"

nada:
    rti

; Los vectores son de 16 bits: la consola arranca en $00, que en ExHiROM
; son los segundos 4 MB, $408000 del archivo. Ahí está la otra copia del
; código, y de ahí se salta a la de $80, la rápida.
reset:
    sei
    clc
    xce
    jml rapido
rapido:
    rep #$38
    .a16
    .i16
    ldx #$1FFF
    txs
    lda #0
    tcd
    sep #$20
    .a8
    phk
    plb
    lda #$80
    sta INIDISP
    stz NMITIMEN
    stz HDMAEN
    lda #1
    sta MEMSEL                      ; FastROM

    ; Los resultados en cero: bsnes arranca la WRAM con basura.
    rep #$20
    .a16
    ldx #0
:   stz RESULTADOS,x
    inx
    inx
    cpx #$0200
    bne :-
    sep #$20
    .a8

    jsr chequear_rom
    jsr chequear_sram
    jsr medir_velocidad
    jsr decidir
    lda #1
    sta ESTADO
    jsr copiar_a_sram
    jsr pintar
fin:
    bra fin

; Suma cada tramo de `chequeos` por palabras y anota en GRUPOS si dio lo
; que tiene que dar, lo de Mednafen u otra cosa.
chequear_rom:
    rep #$30
    .a16
    .i16
    stz indice
    stz numero
@siguiente:
    lda numero
    cmp #CHEQUEOS_N
    bne @uno
    sep #$20
    .a8
    rts
@uno:
    .a16
    ldx indice
    lda chequeos,x
    sta ptr
    sep #$20
    .a8
    lda chequeos + 2,x
    sta ptr + 2
    lda chequeos + 3,x
    sta grupo
    stz grupo + 1
    rep #$20
    .a16
    lda chequeos + 4,x              ; las palabras
    tax
    stz suma
    ldy #0
@sumar:
    lda [ptr],y
    clc
    adc suma
    sta suma
    iny
    iny
    dex
    bne @sumar
    lda numero
    asl
    tax
    lda suma
    sta SUMAS,x
    ldx indice
    ldy #1
    cmp chequeos + 6,x              ; la de la consola
    beq @anotar
    ldy #2
    cmp chequeos + 8,x              ; la de Mednafen
    beq @anotar
    ldy #4
@anotar:
    tya
    ldx grupo
    sep #$20
    .a8
    ora GRUPOS,x
    sta GRUPOS,x
    rep #$20
    .a16
    lda indice
    clc
    adc #10
    sta indice
    inc numero
    bra @siguiente

; La SRAM: primero si quedó la marca de un arranque anterior, después 8 KB
; escritos por un lado y leídos por el otro, y al final la marca y el
; contador para el próximo. El patrón lleva el número de arranque, así
; que lo que quedó de uno anterior no pasa por bueno.
chequear_sram:
    .a8
    rep #$10
    .i16
    ldx #0
@marca:
    lda f:SRAM_ESPEJO + MARCA,x
    cmp marca,x
    bne @sin_marca
    inx
    cpx #8
    bne @marca
    lda f:SRAM_ESPEJO + CONTADOR
    bra @contado
@sin_marca:
    lda #0
@contado:
    sta ARRANQUES
    ldx #0
@escribir:
    jsr patron
    sta f:SRAM,x
    inx
    cpx #COPIA
    bne @escribir
    ldx #0
@leer:
    jsr patron
    cmp f:SRAM_ESPEJO,x
    beq @bien
    rep #$20
    .a16
    inc SRAM_MALOS
    sep #$20
    .a8
@bien:
    inx
    cpx #COPIA
    bne @leer
    ldx #0
@poner:
    lda marca,x
    sta f:SRAM + MARCA,x
    inx
    cpx #8
    bne @poner
    lda ARRANQUES
    inc a
    sta f:SRAM + CONTADOR
    rts

; El byte del patrón para X, en A: los dos bytes de X, $5A y el arranque.
patron:
    .a8
    rep #$20
    .a16
    txa
    sep #$20
    .a8
    xba
    sta temp
    xba
    eor temp
    eor #$5A
    eor ARRANQUES
    rts

; El mismo bucle desde las dos copias del código: $C0 es la de $008000,
; rápida con MEMSEL en 1, y $40 la de $408000, que es lenta siempre.
medir_velocidad:
    .a8
    jsr linea
    .a16
    sta temp
    sep #$20
    .a8
    jsl f:$C00000 + .loword(bucle)
    jsr linea
    .a16
    sec
    sbc temp
    bpl :+
    clc
    adc #262
:   sta LINEAS_RAPIDO
    jsr linea
    .a16
    sta temp
    sep #$20
    .a8
    jsl f:$400000 + .loword(bucle)
    jsr linea
    .a16
    sec
    sbc temp
    bpl :+
    clc
    adc #262
:   sta LINEAS_LENTO
    sep #$20
    .a8
    rts

; Ocho `lda` inmediatos y el salto: casi todo es leer instrucciones de la
; ROM, que es lo que cambia con la velocidad.
bucle:
    .a8
    ldx #VUELTAS
@vuelta:
    lda #0
    lda #0
    lda #0
    lda #0
    lda #0
    lda #0
    lda #0
    lda #0
    dex
    bne @vuelta
    rtl

; La línea del contador vertical, en A. Deja A en 16 bits.
linea:
    sep #$20
    .a8
    lda SLHV                        ; congela H y V
    lda STAT78                      ; y vuelve a leer V desde el byte bajo
    lda OPVCT
    xba
    lda OPVCT
    and #$01
    xba
    rep #$20
    .a16
    rts

; El color de cada franja, en BARRAS.
decidir:
    sep #$20
    .a8
    rep #$10
    .i16
    ldx #1
@grupo:
    lda GRUPOS,x
    cmp #1                          ; todos los tramos como la consola
    beq @verde
    cpx #5
    beq @amarillo                   ; la 5 informa, y no cuenta
    cpx #4
    bne @rojo
    cmp #2                          ; todos como Mednafen
    bne @rojo
@amarillo:
    lda #AMARILLO
    bra @anotar
@verde:
    lda #VERDE
    bra @anotar
@rojo:
    lda #ROJO
@anotar:
    sta BARRAS,x
    inx
    cpx #6
    bne @grupo

    lda #VERDE
    ldx SRAM_MALOS
    beq :+
    lda #ROJO
:   sta BARRAS + 6

    lda ARRANQUES
    beq :+
    lda #BLANCO
    bra :++
:   lda #GRIS
:   sta BARRAS + 7

    ; Rápido si 10 veces lo de $C0 es menos que 9 veces lo de $40, y si
    ; midió algo.
    rep #$20
    .a16
    lda LINEAS_RAPIDO
    beq @lenta
    asl
    sta temp
    asl
    asl
    clc
    adc temp
    sta temp                        ; 10 x rápido
    lda LINEAS_LENTO
    asl
    asl
    asl
    clc
    adc LINEAS_LENTO                ; 9 x lento
    cmp temp
    beq @lenta
    bcc @lenta
    sep #$20
    .a8
    lda #VERDE
    bra :+
@lenta:
    sep #$20
    .a8
    lda #ROJO
:   sta BARRAS + 8

    ; La de todo: las 1, 2, 3, 6 y 8 en verde, y la 4 en verde o amarillo.
    ; La 5 y la 7 informan.
    stz temp                        ; cuántas no
    ldx #1
@todas:
    cpx #5
    beq @otra
    cpx #7
    beq @otra
    lda BARRAS,x
    cmp #VERDE
    beq @otra
    cpx #4
    bne @mal
    cmp #AMARILLO
    beq @otra
@mal:
    inc temp
@otra:
    inx
    cpx #FRANJAS
    bne @todas
    lda temp
    beq :+
    lda #ROJO
    bra :++
:   lda #VERDE
:   sta BARRAS
    rts

copiar_a_sram:
    .a8
    ldx #0
:   lda RESULTADOS,x
    sta f:SRAM + COPIA,x
    inx
    cpx #COPIA_LARGO
    bne :-
    rts

; Las nueve franjas, de 18 líneas cada una con 6 negras debajo: el color 0
; cambiado por HDMA al principio de cada una, de a cuatro bytes —CGADD dos
; veces y CGDATA dos veces, el modo 3—, con todas las capas apagadas.
pintar:
    .a8
    ldx #0                          ; dónde se escribe en la tabla
    ldy #0                          ; la franja
@franja:
    lda #18
    sta HDMA_TABLA,x
    stz HDMA_TABLA + 1,x
    stz HDMA_TABLA + 2,x
    phx
    rep #$20
    .a16
    lda BARRAS,y
    and #$00FF
    asl
    tax
    lda colores,x
    plx
    sta HDMA_TABLA + 3,x
    stz HDMA_TABLA + 6,x
    stz HDMA_TABLA + 8,x
    sep #$20
    .a8
    lda #6
    sta HDMA_TABLA + 5,x
    rep #$20
    .a16
    txa
    clc
    adc #10
    tax
    sep #$20
    .a8
    iny
    cpy #FRANJAS
    bne @franja
    stz HDMA_TABLA,x                ; el fin de la tabla

    lda #$03                        ; A -> B, cuatro bytes en dos registros
    sta DMAP0
    lda #<CGADD
    sta BBAD0
    ldx #HDMA_TABLA
    stx A1T0L
    stz A1B0
    stz TM                          ; sólo el color de fondo
    lda #1
    sta HDMAEN
    lda #$0F
    sta INIDISP
    rts
