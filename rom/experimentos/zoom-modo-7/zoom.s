; El zoom de una foto Diff en modo 7: un piloto, no el juego. La foto
; aparece debajo de un destello blanco, se queda quieta y se achica del 100
; al 0 % en dos segundos, como en RM2k; después negro, y de nuevo. Los
; tiempos y las texturas los pone `armar.py` en `datos.inc`.
;
; Las cuatro variantes difieren en dos cosas: con qué textura se hace el
; zoom —la foto a media resolución, o a resolución completa con 255 tiles
; elegidos por cuantización vectorial— y qué se ve mientras está quieta —la
; misma textura en modo 7, o la foto entera en modo 1 como la muestra hoy
; el juego, con el cambio a modo 7 al empezar el zoom—. Ver `VARIANTES` en
; `armar.py`.
;
; El control:
;   derecha o A    la variante siguiente, desde el principio
;   izquierda      la anterior
;   arriba, abajo  la foto siguiente o la anterior, de las cuatro
;   B              esconde o muestra los números: la foto y la variante
;   Start          pausa
;   Y              cámara lenta: cada cuadro dura ocho
;
; **En las híbridas la textura del modo 7 se sube con la foto en pantalla**,
; de a un trozo de 4 KB por vblank, como lo tendría que hacer el juego: la
; VRAM del modo 7 es la de los tiles del mapa y de los sprites, que se usan
; hasta que la foto aparece. Antes se la ensucia, para que una subida que no
; llegue se vea. Las otras dos la suben con la pantalla apagada, en el negro
; del principio.
;
; No hay NMI: el bucle espera el vblank mirando HVBJOY, como `menu-modo-5`.

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
M7SEL    = $211A
M7A      = $211B
M7B      = $211C
M7C      = $211D
M7D      = $211E
M7X      = $211F
M7Y      = $2120
CGADD    = $2121
TM       = $212C
TS       = $212D
CGWSEL   = $2130
CGADSUB  = $2131
COLDATA  = $2132
SETINI   = $2133
SLHV     = $2137
OPVCT    = $213D
STAT78   = $213F
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

BOTON_B       = $8000
BOTON_Y       = $4000
BOTON_START   = $1000
BOTON_ARRIBA  = $0800
BOTON_ABAJO   = $0400
BOTON_IZQ     = $0200
BOTON_DER     = $0100
BOTON_A       = $0080

; Los tipos de copia de las listas de `datos.inc`; los repite `armar.py`.
COPIA_BAJOS    = 1
COPIA_ALTOS    = 2
COPIA_PALABRAS = 3
COPIA_CGRAM    = 4
COPIA_CEROS    = 5

; **La primera línea que se ve es la 1 del fondo**, en modo 1 y en modo 7:
; la pantalla empieza a dibujar con la línea vofs+1. Con esto la fila 0 de
; la foto cae en la primera línea, y en modo 7 la foto queda centrada.
AJUSTE_V = -1

.include "datos.inc"

; Lo que `verificar.py` lee de la RAM está en direcciones fijas: al principio
; de la página cero, en este orden.
.segment "ZEROPAGE"
cuadro:      .res 2     ; de la vuelta, desde 0: ver `calcular`
variante:    .res 2     ; 0..VARIANTES-1
subida_fin:  .res 2     ; en qué cuadro terminó de subir la textura, o $FFFF
linea_max:   .res 2     ; la línea más tardía en que terminó un vblank
anterior:    .res 2     ; los botones del cuadro anterior
cola:        .res 2     ; la próxima copia por vblank, o 0
sin_marca:   .res 1
pausa:       .res 1
lento:       .res 1
lento_n:     .res 1
foto:        .res 2     ; 0..FOTOS-1
; Lo que se escribe en el próximo vblank.
s_tm:        .res 1
s_bgmode:    .res 1
s_coldata:   .res 1
s_cambio:    .res 1     ; distinto de 0: subir la paleta del modo 7
s_m7a:       .res 2
s_m7d:       .res 2
s_m7x:       .res 2
s_m7y:       .res 2
s_hofs:      .res 2
s_vofs:      .res 2
t:           .res 2     ; el cuadro del zoom: 0 quieta, ZOOM ya no se ve
k:           .res 2     ; el cuadro desde que apareció la foto
vx:          .res 2     ; la variante por dos, para las tablas de palabras
tmp:         .res 2

.segment "HEADER"
    .byte "ABL ZOOM MODO 7      "   ; 21 caracteres
    .byte $30                       ; LoROM, FastROM: ver MEMSEL
    .byte $00
    .byte TAMANO_ROM
    .byte $00
    .byte $01
    .byte $00
    .byte $00
    .word $FFFF
    .word $0000

.segment "VECTORS"
    .word 0, 0, 0, 0, 0
    .word .loword(nada)
    .word 0
    .word .loword(nada)
    .word 0, 0, 0, 0, 0, 0
    .word .loword(reset)
    .word .loword(nada)

.segment "CODE"

nada:
    rti

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
    sta MEMSEL

    ; Los registros de la PPU en 0, la página cero también: bsnes arranca
    ; con basura.
    ldx #OBSEL
:   stz a:0,x
    inx
    cpx #BG1HOFS
    bne :-
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
    ldx #0
:   stz z:0,x
    inx
    cpx #$100
    bne :-

    lda #(VRAM_M1_MAPA >> 8) & $FC
    sta BG1SC                       ; tilemap de 32x32
    lda #VRAM_M1_TILES >> 12
    sta BG12NBA
    lda #VRAM_SPRITES >> 13
    sta OBSEL                       ; sprites de 8x8
    lda #$80
    sta M7SEL                       ; fuera del plano de 1024, transparente
    ; El destello: la pantalla principal suma el color fijo, en BG1 y en el
    ; fondo. Los sprites no, así el número se sigue leyendo.
    stz CGWSEL
    lda #$21
    sta CGADSUB

    ; Todos los sprites abajo de la pantalla; el 0 es la marca.
    stz OAMADDL
    stz OAMADDL + 1
    ldx #128
:   stz OAMDATA
    lda #$E0
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne :-
    ldx #32
:   stz OAMDATA
    dex
    bne :-
    ldy #.loword(comun)
    jsr copiar_todo

    rep #$20
    .a16
    lda #$FFFF
    sta anterior
    sta subida_fin
    sep #$20
    .a8
    lda #1
    sta NMITIMEN                    ; sólo la lectura automática del control
    jsr cargar
    jsr calcular

bucle:
    ; El comienzo del vblank: todo lo de la pantalla se escribe acá.
:   lda HVBJOY
    bpl :-
    jsr vblank
    ; Y la lectura del control, que empieza con el vblank y tarda unas
    ; líneas: hay que esperar a que termine (ver `menu-modo-5/menu.s`).
:   lda HVBJOY
    lsr
    bcs :-
    jsr control
    jsr avanzar
    jsr calcular
:   lda HVBJOY
    bmi :-
    bra bucle

; --- el vblank -------------------------------------------------------------

.a8
.i16
vblank:
    jsr registros
    jmp copias

; Los registros y la marca, de lo que dejó `calcular`.
.a8
.i16
registros:
    lda s_bgmode
    sta BGMODE
    lda s_tm
    sta TM
    lda s_coldata
    sta COLDATA
    lda s_m7a
    sta M7A
    lda s_m7a + 1
    sta M7A
    stz M7B
    stz M7B
    stz M7C
    stz M7C
    lda s_m7d
    sta M7D
    lda s_m7d + 1
    sta M7D
    lda s_m7x
    sta M7X
    lda s_m7x + 1
    sta M7X
    lda s_m7y
    sta M7Y
    lda s_m7y + 1
    sta M7Y
    lda s_hofs
    sta BG1HOFS
    lda s_hofs + 1
    sta BG1HOFS
    lda s_vofs
    sta BG1VOFS
    lda s_vofs + 1
    sta BG1VOFS

    ; La marca: el sprite 0 es la foto y el 1 la variante, desde 1.
    stz OAMADDL
    stz OAMADDL + 1
    lda #MARCA_X
    sta OAMDATA
    jsr marca_y
    lda foto
    clc
    adc #<TILE_MARCA
    sta OAMDATA
    lda #$30 | (PALETA_MARCA << 1) | >TILE_MARCA
    sta OAMDATA
    lda #MARCA_X + 10
    sta OAMDATA
    jsr marca_y
    lda variante
    clc
    adc #<TILE_MARCA
    sta OAMDATA
    lda #$30 | (PALETA_MARCA << 1) | >TILE_MARCA
    sta OAMDATA
    rts

marca_y:
    lda sin_marca
    beq :+
    lda #$E0                        ; abajo de la pantalla
    bra :++
:   lda #MARCA_Y
:   sta OAMDATA
    rts

; Las copias del vblank: la paleta del cambio y un trozo de la textura.
.a8
.i16
copias:

    ; El cambio de las híbridas: la paleta del modo 7 en el mismo vblank en
    ; que cambia el modo.
    lda s_cambio
    beq :+
    stz s_cambio
    ldx vx
    ldy v_cgram,x
    jsr copiar
:
    ; Un trozo de la textura, si hay y la foto ya apareció.
    ldy cola
    beq @fin
    rep #$20
    .a16
    lda cuadro
    cmp #NEGRO_ANTES
    sep #$20
    .a8
    bcc @fin
    jsr copiar
    rep #$20
    .a16
    tya
    clc
    adc #8
    tay
    sep #$20
    .a8
    lda a:0,y
    bne :+
    ldy #0
    ldx cuadro
    stx subida_fin
:   sty cola
@fin:
    ; En qué línea terminó: si pasó la 261 dio la vuelta y se comió el
    ; principio del cuadro siguiente, y una copia ahí no llega a la VRAM.
    lda STAT78                      ; el próximo OPVCT da el byte bajo
    lda SLHV
    lda OPVCT
    xba
    lda OPVCT
    and #1
    xba
    rep #$20
    .a16
    cmp #225
    bcs :+
    adc #262
:   cmp linea_max
    bcc :+
    sta linea_max
:   sep #$20
    .a8
    rts

; --- el control ------------------------------------------------------------

.a8
.i16
control:
    rep #$20
    .a16
    ldx JOY1L
    lda anterior
    eor #$FFFF
    stx anterior
    and anterior                    ; lo que se apretó en este cuadro
    sta tmp
    bit #BOTON_DER | BOTON_A
    beq :+
    lda variante
    inc
    cmp #VARIANTES
    bne @elegida
    lda #0
    bra @elegida
:   bit #BOTON_IZQ
    beq @otros
    lda variante
    bne :+
    lda #VARIANTES
:   dec
@elegida:
    sta variante
@de_nuevo:
    stz cuadro
    sep #$20
    .a8
    jmp cargar
@otros:
    .a16
    bit #BOTON_ARRIBA
    beq :+
    lda foto
    inc
    cmp #FOTOS
    bne @foto
    lda #0
    bra @foto
:   bit #BOTON_ABAJO
    beq @botones
    lda foto
    bne :+
    lda #FOTOS
:   dec
@foto:
    sta foto
    bra @de_nuevo
@botones:
    sep #$20
    .a8
    lda tmp + 1
    bit #>BOTON_B
    beq :+
    lda sin_marca
    eor #1
    sta sin_marca
    lda tmp + 1
:   bit #>BOTON_START
    beq :+
    lda pausa
    eor #1
    sta pausa
    lda tmp + 1
:   bit #>BOTON_Y
    beq :+
    lda lento
    eor #1
    sta lento
:   rts

; El cuadro siguiente: con pausa no avanza, en cámara lenta uno de cada
; ocho. Al terminar la vuelta, la carga de nuevo.
.a8
.i16
avanzar:
    lda pausa
    bne @no
    lda lento
    beq :+
    inc lento_n
    lda lento_n
    and #7
    bne @no
:   rep #$20
    .a16
    lda cuadro
    inc
    cmp #NEGRO_ANTES + QUIETA + ZOOM + NEGRO_DESPUES
    bcc :+
    lda #0
:   sta cuadro
    sep #$20
    .a8
    lda cuadro
    ora cuadro + 1
    bne @no
    jmp cargar
@no:
    rts

; --- la carga --------------------------------------------------------------

; Con la pantalla apagada, en el negro del principio: lo de la variante que
; va con la foto. Las no híbridas suben la textura del modo 7 entera y su
; paleta; las híbridas, la foto del modo 1 y su paleta, ensucian la VRAM
; del modo 7 y dejan la textura en `cola`, para el vblank.
.a8
.i16
cargar:
    lda #$80
    sta INIDISP
    rep #$20
    .a16
    lda foto                        ; vx = (foto · VARIANTES + variante) · 2
    .repeat VARIANTES - 1
    clc
    adc foto
    .endrepeat
    clc
    adc variante
    asl
    sta vx
    tax
    lda #$FFFF
    sta subida_fin
    stz cola
    sep #$20
    .a8
    lda v_hibrida,x
    bne @hibrida
    ldy v_cgram,x
    jsr copiar_todo
    ldx vx
    ldy v_copias,x
    jsr copiar_todo
    bra @listo
@hibrida:
    ldy v_cgram_m1,x
    jsr copiar_todo
    ldx vx
    ldy v_modo1,x
    jsr copiar_todo
    ; La basura: las 16 K palabras del modo 7 en $5555.
    lda #$80
    sta VMAIN
    stz VMADDL
    stz VMADDL + 1
    lda #$09                        ; fuente fija, dos registros
    sta DMAP0
    lda #$18
    sta BBAD0
    rep #$20
    .a16
    lda #.loword(basura)
    sta A1T0L
    lda #$8000
    sta DAS0L
    sep #$20
    .a8
    lda #^basura
    sta A1B0
    lda #1
    sta MDMAEN
    ldx vx
    rep #$20
    .a16
    lda v_copias,x
    sta cola
    sep #$20
    .a8
@listo:
    jsr calcular
    jsr registros
    lda #$0F
    sta INIDISP
    rts

; Todas las copias de la lista que empieza en Y.
.a8
.i16
copiar_todo:
:   lda a:0,y
    beq :+
    jsr copiar
    rep #$20
    .a16
    tya
    clc
    adc #8
    tay
    sep #$20
    .a8
    bra :-
:   rts

; Una copia por DMA: la de la entrada en Y, que no cambia.
.a8
.i16
copiar:
    lda a:0,y
    cmp #COPIA_CGRAM
    bne :+
    lda a:1,y
    sta CGADD
    lda #$00
    ldx #$22
    bra @copiar
:   pha
    rep #$20
    .a16
    lda a:1,y
    sta VMADDL
    sep #$20
    .a8
    pla
    cmp #COPIA_BAJOS
    bne :+
    stz VMAIN                       ; avanza al escribir el byte bajo
    lda #$00
    ldx #$18
    bra @copiar
:   cmp #COPIA_CEROS
    bne :+
    stz VMAIN
    lda #$08                        ; la fuente fija: el mismo cero
    ldx #$18
    bra @copiar
:   cmp #COPIA_ALTOS
    bne :+
    lda #$80                        ; avanza al escribir el alto
    sta VMAIN
    lda #$00
    ldx #$19
    bra @copiar
:   lda #$80                        ; de a palabras
    sta VMAIN
    lda #$01
    ldx #$18
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
    rts

; --- el cuadro -------------------------------------------------------------

; Lo que se escribe en el próximo vblank, según el cuadro de la vuelta:
;
;   0 .. NEGRO_ANTES            negro
;   la foto, con el destello en sus primeros DESTELLO cuadros
;   QUIETA cuadros quieta, a escala 1                        t = 0
;   ZOOM cuadros achicándose, en el t-ésimo a 1 − t/ZOOM     t = 1..ZOOM
;   NEGRO_DESPUES de negro
.a8
.i16
calcular:
    lda #$10
    sta s_tm                        ; sólo los sprites: la marca
    lda #$E0
    sta s_coldata                   ; nada que sumar
    rep #$20
    .a16
    lda cuadro
    sec
    sbc #NEGRO_ANTES
    bcs :+
    sep #$20
    .a8
    rts
:   .a16
    sta k
    cmp #DESTELLO
    bcs :+
    ldx vx
    clc
    adc v_destello,x
    tay
    sep #$20
    .a8
    lda a:0,y
    ora #$E0
    sta s_coldata
    rep #$20
    .a16
    lda k
:   sec
    sbc #QUIETA - 1
    bcs :+
    lda #0
:   sta t
    cmp #ZOOM
    sep #$20
    .a8
    bcc :+
    rts                             ; ya no se ve
:   lda #$11
    sta s_tm
    ldx vx
    lda v_hibrida,x
    beq @modo7
    lda t
    bne :+
    ; Quieta, en modo 1: sin desplazamiento, salvo la primera línea.
    lda #1
    sta s_bgmode
    rep #$20
    .a16
    stz s_hofs
    lda #.loword(AJUSTE_V)
    sta s_vofs
    sep #$20
    .a8
    rts
:   cmp #1
    bne @modo7
    sta s_cambio                    ; el primer cuadro del zoom: la paleta
@modo7:
    lda #7
    sta s_bgmode
    rep #$20
    .a16
    lda t
    asl
    sta tmp
    lda v_matriz_a,x
    clc
    adc tmp
    tay
    lda a:0,y
    sta s_m7a
    lda v_matriz_d,x
    clc
    adc tmp
    tay
    lda a:0,y
    sta s_m7d
    ; El centro de la textura queda en el centro de la pantalla.
    lda v_centro_x,x
    sta s_m7x
    sec
    sbc #128
    and #$1FFF
    sta s_hofs
    lda v_centro_y,x
    sta s_m7y
    sec
    sbc #112 - AJUSTE_V
    and #$1FFF
    sta s_vofs
    sep #$20
    .a8
    rts
