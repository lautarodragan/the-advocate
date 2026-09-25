; --- las pantallas de texto -----------------------------------------------------
;
; El equipo y la tienda son pantallas de puro texto sobre la fuente de la
; pantalla de ítems. Se componen **enteras** en `texto_buf` —el tilemap de 32
; por 28 celdas, 1792 bytes— y suben de un DMA al empezar cada vblank, así que
; componer no tiene apuro de tiempo. `pantallas.py` es la referencia. Una
; posición es un byte del búfer: fila * 64 + columna * 2; la celda de abajo de
; cada letra está 64 bytes más adelante.
;
; El escritorio son variables prestadas: las del compositor de mensajes,
; `comp_*`, que se recalculan con cada carácter y con el menú abierto no hay
; mensaje; y `eleg_tabla`, que es la posición donde se escribe.
PANT_BYTES = 32 * 28 * 2
;   pant_valor   es comp_dup       ; el número que se escribe, dos bytes
;   pant_ancho   es comp_dup + 2   ; en cuántas cifras
;   pant_tope    es comp_dup + 3   ; cuántas letras de un texto, a lo sumo

; El búfer en blanco.
.proc pant_limpiar
.a8
.i16
    rep #$20
.a16
    ldx #0
otra:
    stz texto_buf, x
    inx
    inx
    cpx #PANT_BYTES
    bcc otra
    sep #$20
.a8
    rts
.endproc

; El búfer al tilemap: un DMA, en el vblank.
.proc pant_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #PANT_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el búfer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Una letra: A el carácter, `temp + 1` la variante —0 blanco, 1 gris—. Va en
; `eleg_tabla`, que avanza una celda. Se lleva X e Y.
.proc pant_glifo
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    tax
    lda temp + 1
    and #$00FF
    beq blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
blanco:
    ldy eleg_tabla
    lda f:item_glifo_celdas, x
    sta texto_buf, y
    lda f:item_glifo_celdas + 2, x
    sta texto_buf + 64, y
    iny
    iny
    sty eleg_tabla
    sep #$20
.a8
    rts
.endproc

; Un texto: X su número —ver `item_txt_*`—, en `eleg_tabla` y con la variante
; de `temp + 1`, y no más de `pant_tope` letras.
.proc pant_texto
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    cmp comp_dup + 3
    bcc cabe
    lda comp_dup + 3
cabe:
    sta temp                    ; cuántas letras
    stz temp + 2                ; por cuál va
letra:
    lda temp + 2
    cmp temp
    bcs listo
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [msg_ptr], y
    jsr pant_glifo
    inc temp + 2
    bra letra
listo:
    lda #255
    sta comp_dup + 3               ; el tope es de un texto solo
    rts
.endproc

; Un número de `pant_valor`, de 0 a 999, en `pant_ancho` cifras —2 o 3— con
; espacios adelante, en `eleg_tabla` y con la variante de `temp + 1`.
.proc pant_numero
.a8
.i16
    stz temp + 3                ; ya salió una cifra
    lda comp_dup + 2
    cmp #3
    bcc decenas
    rep #$20
.a16
    ldx #0
cien:
    lda comp_dup
    cmp #100
    bcc cien_listo
    sbc #100
    sta comp_dup
    inx
    bra cien
cien_listo:
    sep #$20
.a8
    jsr cifra
decenas:
    rep #$20
.a16
    ldx #0
diez:
    lda comp_dup
    cmp #10
    bcc diez_listo
    sbc #10
    sta comp_dup
    inx
    bra diez
diez_listo:
    sep #$20
.a8
    jsr cifra
    lda comp_dup              ; las unidades, siempre
    clc
    adc #$30
    jmp pant_glifo

; X: la cifra. Un cero adelante de todo va como espacio.
cifra:
    txa
    bne escribir
    lda temp + 3
    bne escribir_cero
    lda #$20
    jmp pant_glifo
escribir_cero:
    lda #0
escribir:
    clc
    adc #$30
    pha
    lda #1
    sta temp + 3
    pla
    jmp pant_glifo
.endproc


