; Cuánto tarda el puerto de datos del MSU-1, y si lo que entrega es lo que
; hay en el `.msu`: una prueba de hardware, no el juego. La arma `armar.py`,
; que escribe al lado un `.msu` de bytes pseudoaleatorios y le pasa a esto
; la suma de cada tramo de 32 KB (`esperado.inc`).
;
; Lee del puerto por DMA, como `scn_fill` del runtime —origen fijo en
; `$00:2001`, el bit 3 de DMAP— con la pantalla apagada, a la WRAM por
; `$2180`:
;
;   prueba 0     busca $000000 y lee 32 KB a $7F:0000
;   prueba 1     busca $0C0000 y lee 32 KB a $7F:8000: una búsqueda lejos
;   pruebas 2-9  una sola búsqueda a $040000 y después 512 KB seguidos, de
;                a dos DMA de 32 KB pegados —$7F:0000 y $7F:8000— sin
;                ninguna pausa entre los dos: el peor caso para un
;                cartucho que llena su búfer mientras la consola lee
;
; Cada tramo se suma —por palabras, módulo 65536— y se compara con lo que
; dice `armar.py`. Lo que mide queda en la WRAM desde RESULTADOS, para que
; lo lea `medir.py`; y en la pantalla, para la consola: **verde** si todos
; los tramos llegaron bien, **rojo** si alguno no, **azul** si no hay MSU-1.
;
; El tiempo se mide con el contador vertical (`$213D`): la línea antes de
; buscar, después de que la búsqueda termina y después de cada DMA. Una
; línea son 1364 ciclos maestros, y un DMA de 32 KB son unas 192, así que
; ninguno da la vuelta a las 262 del cuadro; `medir.py` resta módulo 262.

.p816
.smart -

MSU_ESTADO = $2000              ; leer: bit 7, ocupado buscando
MSU_BUSCAR = $2000              ; escribir: la posición, 32 bits; $2003 busca
MSU_DATO   = $2001
MSU_FIRMA  = $2002              ; "S-MSU1", seis bytes
INIDISP  = $2100
CGADD    = $2121
CGDATA   = $2122
TM       = $212C
SLHV     = $2137
OPVCT    = $213D
STAT78   = $213F
WMADDL   = $2181
NMITIMEN = $4200
MDMAEN   = $420B
HDMAEN   = $420C
MEMSEL   = $420D
DMAP0    = $4300
BBAD0    = $4301
A1T0L    = $4302
A1B0     = $4304
DAS0L    = $4305

; Lo que queda para `medir.py`, en la WRAM baja. Primero un byte de estado
; —0 corriendo, 1 terminó, 2 no hay MSU-1— y el número de tramos malos;
; después, por prueba, ocho palabras: las vueltas de la espera de la
; búsqueda, la línea antes de buscar, después de buscar, antes del primer
; DMA, después del primero, después del segundo, y la suma de cada mitad.
RESULTADOS = $0200
ESTADO     = RESULTADOS
MALOS      = RESULTADOS + 2
FILAS      = RESULTADOS + 16
FILA       = 16                 ; bytes por prueba

.segment "ZEROPAGE"
fila:      .res 2               ; dónde se escribe la prueba que corre
suma:      .res 2
vueltas:   .res 2
tramo:     .res 2               ; cuál de `esperado` toca comparar

.segment "HEADER"
    .byte "ABL MSU-1 PUERTO     "   ; 21 caracteres
    .byte $30                       ; LoROM, FastROM
    .byte $00                       ; sólo ROM
    .byte $05                       ; 32 KB
    .byte $00                       ; sin SRAM
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
.include "esperado.inc"         ; `esperado`: una palabra por tramo

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
    sta INIDISP                     ; pantalla apagada: el DMA va entero
    stz NMITIMEN
    stz HDMAEN
    lda #1
    sta MEMSEL

    ; Los resultados en cero: bsnes arranca la WRAM con basura.
    rep #$20
    .a16
    ldx #0
:   stz RESULTADOS,x
    inx
    inx
    cpx #FILAS + 10 * FILA - RESULTADOS
    bne :-
    lda #FILAS
    sta fila
    stz tramo
    sep #$20
    .a8

    ; ¿Hay MSU-1? La firma "S-MSU1" en $2002..$2007.
    ldx #0
:   lda f:MSU_FIRMA,x
    cmp firma,x
    bne sin_msu
    inx
    cpx #6
    bne :-

    ; Prueba 0: $000000, 32 KB a $7F:0000.
    lda #$00
    jsr buscar_en_a                 ; A = el byte 2 de la posición
    lda #$00
    jsr leer_32k                    ; A = 0: $7F:0000; $80: $7F:8000
    jsr verificar_bajo
    jsr siguiente_fila

    ; Prueba 1: $0C0000, 32 KB a $7F:8000.
    lda #$0C
    jsr buscar_en_a
    lda #$80
    jsr leer_32k
    jsr verificar_alto
    jsr siguiente_fila

    ; Pruebas 2 a 9: una búsqueda y 512 KB seguidos.
    lda #$04
    jsr buscar_en_a
    ldy #8
@seguido:
    phy
    lda #$00
    jsr leer_32k
    lda #$80
    jsr leer_32k_segundo            ; pegado al anterior: sin pausa
    jsr verificar_bajo
    jsr verificar_alto
    jsr siguiente_fila
    ply
    dey
    bne @seguido

    lda #1
    sta ESTADO
    lda MALOS
    bne @rojo
    rep #$20
    .a16
    lda #$03E0                      ; verde
    bra pintar
@rojo:
    .a8
    rep #$20
    .a16
    lda #$001F                      ; rojo
    bra pintar

sin_msu:
    .a8
    lda #2
    sta ESTADO
    rep #$20
    .a16
    lda #$7C00                      ; azul

pintar:
    .a16
    sep #$20
    .a8
    stz CGADD
    xba
    pha
    xba
    sta CGDATA
    pla
    sta CGDATA
    stz TM
    lda #$0F
    sta INIDISP
fin:
    bra fin

firma:
    .byte "S-MSU1"

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

; Busca la posición A << 16 y espera a que el MSU-1 baje el bit de ocupado,
; contando las vueltas. Anota la línea antes y después.
buscar_en_a:
    .a8
    pha
    jsr linea
    ldy fila
    sta a:2,y
    sep #$20
    .a8
    pla
    stz MSU_BUSCAR
    stz MSU_BUSCAR + 1
    sta MSU_BUSCAR + 2
    stz MSU_BUSCAR + 3              ; ésta es la que busca
    rep #$20
    .a16
    stz vueltas
    sep #$20
    .a8
@espera:
    rep #$20
    inc vueltas
    sep #$20
    lda MSU_ESTADO
    bmi @espera
    jsr linea
    ldy fila
    sta a:4,y
    lda vueltas
    sta a:0,y
    sep #$20
    .a8
    rts

; Un DMA de 32 KB del puerto a $7F:0000 (A = 0) o $7F:8000 (A = $80).
; `leer_32k` anota la línea antes y después (palabras 6 y 8);
; `leer_32k_segundo` va pegado al anterior y anota sólo la de después
; (palabra 10).
leer_32k:
    .a8
    pha
    jsr linea
    ldy fila
    sta a:6,y
    sep #$20
    .a8
    pla
    ldx #8
    bra dma
leer_32k_segundo:
    .a8
    ldx #10
dma:
    stz WMADDL
    sta WMADDL + 1
    lda #$01
    sta WMADDL + 2
    lda #$08                        ; A -> B, origen fijo, un registro
    sta DMAP0
    lda #$80                        ; WMDATA, $2180
    sta BBAD0
    stz A1B0
    rep #$20
    .a16
    lda #MSU_DATO
    sta A1T0L
    lda #$8000
    sta DAS0L
    sep #$20
    .a8
    lda #$01
    sta MDMAEN                      ; la CPU espera acá hasta que termina
    rep #$20
    .a16
    txa
    clc
    adc fila
    tay
    jsr linea
    sta a:0,y
    sep #$20
    .a8
    rts

; Suma por palabras los 32 KB de $7F:0000 o de $7F:8000, la anota en la
; fila (palabra 12 o 14) y la compara con `esperado[tramo]`.
verificar_bajo:
    .a8
    rep #$20
    .a16
    ldx #0
    stz suma
@b: lda f:$7F0000,x
    clc
    adc suma
    sta suma
    inx
    inx
    cpx #$8000
    bne @b
    ldy fila
    sta a:12,y
    bra comparar
verificar_alto:
    .a8
    rep #$20
    .a16
    ldx #0
    stz suma
@a: lda f:$7F8000,x
    clc
    adc suma
    sta suma
    inx
    inx
    cpx #$8000
    bne @a
    ldy fila
    sta a:14,y
comparar:
    .a16
    lda tramo
    asl
    tax
    lda suma
    cmp esperado,x
    beq @bien
    inc MALOS
@bien:
    inc tramo
    sep #$20
    .a8
    rts

siguiente_fila:
    rep #$20
    .a16
    lda fila
    clc
    adc #FILA
    sta fila
    sep #$20
    .a8
    rts
