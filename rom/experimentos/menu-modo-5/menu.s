; La maqueta del menú de pausa, como imagen fija: una prueba de hardware del
; modo 5, no el juego. Tres pantallas —las que `armar.py` convierte de
; `maqueta/`—; derecha o A pasa a la siguiente, izquierda a la anterior, y B
; esconde o muestra el número de la esquina.
;
; Cada cambio apaga la pantalla, sube todo de nuevo por DMA —paletas,
; sprites, tilemap y tiles— y la vuelve a prender. No hay NMI: el bucle
; espera el vblank mirando HVBJOY.

.p816
.smart -

INIDISP  = $2100
OBSEL    = $2101
OAMADDL  = $2102
OAMDATA  = $2104
BGMODE   = $2105
MOSAIC   = $2106
BG1SC    = $2107
BG12NBA  = $210B
BG1HOFS  = $210D
BG1VOFS  = $210E
VMAIN    = $2115
VMADDL   = $2116
CGADD    = $2121
TM       = $212C
TS       = $212D
CGWSEL   = $2130
CGADSUB  = $2131
COLDATA  = $2132
SETINI   = $2133
NMITIMEN = $4200
MDMAEN   = $420B
HDMAEN   = $420C
MEMSEL   = $420D
HVBJOY   = $4212
JOY1L    = $4218
DMAP0    = $4300
BBAD0    = $4301
A1T0L    = $4302
A1B0     = $4304
DAS0L    = $4305

; Los botones, en la palabra de JOY1L.
BOTON_B       = $8000
BOTON_IZQ     = $0200
BOTON_DER     = $0100
BOTON_A       = $0080

.segment "ZEROPAGE"
pantalla:   .res 2      ; cuál se muestra, 0..PANTALLAS-1
anterior:   .res 2      ; los botones del cuadro anterior
sin_marca:  .res 1      ; distinto de 0: la marca escondida

.segment "HEADER"
    ; Lo mismo que el encabezado del juego (`tools/runtime/header.s`), que
    ; ya anda en el FX Pak, salvo el tamaño y que no lleva batería.
    .byte "ABL MENU MODO 5      "   ; 21 caracteres
    .byte $30                       ; LoROM, FastROM: ver MEMSEL
    .byte $00                       ; sólo ROM
    .byte $07                       ; 128 KB (log2 de los KB)
    .byte $00                       ; sin SRAM
    .byte $01                       ; región
    .byte $00                       ; desarrollador
    .byte $00                       ; versión
    .word $FFFF                     ; complemento, lo escribe `armar.py`
    .word $0000                     ; suma, ídem

.segment "VECTORS"
    .word 0, 0, 0, 0, 0
    .word .loword(nada)             ; $FFEA NMI nativo, apagado igual
    .word 0
    .word .loword(nada)             ; $FFEE IRQ nativo
    .word 0, 0, 0, 0, 0, 0
    .word .loword(reset)            ; $FFFC RESET
    .word .loword(nada)             ; $FFFE IRQ de emulación

.segment "CODE"

nada:
    rti

reset:
    sei
    clc
    xce
    ; Al banco $80, que es donde la ROM va rápida con MEMSEL.
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
    sta INIDISP                     ; pantalla apagada
    stz NMITIMEN
    stz HDMAEN
    lda #1
    sta MEMSEL

    ; Todos los registros de la PPU en 0: bsnes arranca con basura, como la
    ; consola.
    ldx #OBSEL
:   stz a:0,x
    inx
    cpx #BG1HOFS
    bne :-
    ; Los de desplazamiento se escriben dos veces cada uno.
:   stz a:0,x
    stz a:0,x
    inx
    cpx #VMAIN
    bne :-
    ldx #CGADD
:   stz a:0,x
    inx
    cpx #SETINI + 1
    bne :-

    ; **BG1VOFS en -1**: la primera línea que se ve es la 1 del fondo, así
    ; que con 0 la fila de arriba de la imagen quedaría escondida. Los
    ; sprites ya salen una línea más abajo de su Y, así que con esto la
    ; fila y y un sprite en Y = y caen juntos.
    lda #$FF
    sta BG1VOFS
    lda #$03
    sta BG1VOFS

    lda #$70
    sta BG1SC                       ; tilemap de 32x32 en $7000
    stz BG12NBA                     ; tiles de BG1 desde 0
    lda #$03
    sta OBSEL                       ; sprites de 8x8, tiles en $6000
    ; La subpantalla sin nada muestra COLDATA: en negro, como el fondo.
    ; En modo 5 las columnas pares salen de ahí.
    lda #$E0
    sta COLDATA
    stz CGWSEL
    stz CGADSUB
    stz SETINI                      ; sin entrelazado: 224 líneas

    rep #$20
    .a16
    stz pantalla
    lda #$FFFF
    sta anterior                    ; nada cuenta como apretado al arrancar
    sep #$20
    .a8
    stz sin_marca

    lda #1
    sta NMITIMEN                    ; sólo la lectura automática del control
    jsr mostrar

bucle:
    ; El comienzo del vblank, y después la lectura automática del control:
    ; que empiece y que termine. Mirar sólo que termine no alcanza, porque
    ; al entrar al vblank todavía no empezó, y leer JOY1L mientras la
    ; consola lo está llenando da botones a medias —en bsnes, un cambio de
    ; pantalla perdido o dos por cada toque—. Se llega acá siempre al
    ; principio del vblank (ver @esperar), así que la lectura no pasó.
:   lda HVBJOY
    bpl :-
:   lda HVBJOY
    lsr
    bcc :-
:   lda HVBJOY
    lsr
    bcs :-

    rep #$20
    .a16
    ldx JOY1L
    lda anterior
    eor #$FFFF
    stx anterior
    and anterior                    ; lo que se apretó en este cuadro
    bit #BOTON_DER | BOTON_A
    beq :+
    lda pantalla
    inc
    cmp #PANTALLAS
    bne @elegida
    lda #0
    bra @elegida
:   bit #BOTON_IZQ
    beq :+
    lda pantalla
    bne @menos
    lda #PANTALLAS
@menos:
    dec
@elegida:
    sta pantalla
    sep #$20
    .a8
    jsr mostrar
    bra @esperar
:   .a16
    bit #BOTON_B
    sep #$20
    .a8
    beq @esperar
    lda sin_marca
    eor #1
    sta sin_marca
    jsr mostrar

@esperar:
    ; Hasta que el vblank termine, para no leer el mismo cuadro dos veces.
:   lda HVBJOY
    bmi :-
    bra bucle

; Muestra `pantalla`: la apaga, copia todo, pone el modo y la prende.
.a8
.i16
mostrar:
    lda #$80
    sta INIDISP
    rep #$20
    .a16
    lda pantalla
    asl
    tax
    lda copias,x
    tay
    sep #$20
    .a8
@copia:
    lda a:0,y
    beq @listo
    cmp #1
    bne :+
    lda #$80
    sta VMAIN                       ; de a palabras, avanzando con la alta
    rep #$20
    .a16
    lda a:1,y
    sta VMADDL
    sep #$20
    .a8
    lda #$01                        ; dos registros, $2118 y $2119
    ldx #$18
    bra @copiar
:   cmp #2
    bne :+
    lda a:1,y
    sta CGADD
    lda #$00
    ldx #$22
    bra @copiar
:   rep #$20                        ; la OAM
    .a16
    lda a:1,y
    sta OAMADDL
    sep #$20
    .a8
    lda #$00
    ldx #$04
@copiar:
    sta DMAP0
    txa
    sta BBAD0
    rep #$20
    .a16
    lda a:3,y
    sta A1T0L
    lda a:6,y
    sta DAS0L
    sep #$20
    .a8
    lda a:5,y
    sta A1B0
    lda #1
    sta MDMAEN
    rep #$20
    .a16
    tya
    clc
    adc #8
    tay
    sep #$20
    .a8
    bra @copia

@listo:
    ; La marca es el sprite 0: para esconderla se la baja de la pantalla.
    lda sin_marca
    beq :+
    stz OAMADDL
    stz OAMADDL + 1
    stz OAMDATA                     ; X
    lda #$E0
    sta OAMDATA                     ; Y
:
    ldx pantalla
    lda modos,x
    sta BGMODE
    ; BG1 y los sprites en las dos pantallas: en modo 5 las columnas pares
    ; salen de la subpantalla, y sin ella falta la mitad de los pixeles. En
    ; modo 3 la subpantalla no se ve, y va igual.
    lda #$11
    sta TM
    sta TS
    lda #$0F
    sta INIDISP
    rts

.include "datos.inc"
