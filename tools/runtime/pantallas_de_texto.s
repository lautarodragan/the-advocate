.segment "CODE"

; --- the text screens -----------------------------------------------------------
;
; The equipment and shop screens are pure text on top of the item screen's
; font. They are composed **whole** in `texto_buf` —the 32 by 28 cell
; tilemap, 1792 bytes— and go up in one DMA at the start of each vblank, so
; composing is in no hurry. `pantallas.py` is the reference. A position is a
; byte of the buffer: row * 64 + column * 2; the cell below each letter is 64
; bytes further on.
;
; The scratch space is borrowed variables: the message composer's, `comp_*`,
; which are recomputed with each character, and with the menu open there is
; no message; and `eleg_tabla`, which is the position being written to.
PANT_BYTES = 32 * 28 * 2
;   pant_valor   is comp_dup       ; the number being written, two bytes
;   pant_ancho   is comp_dup + 2   ; in how many digits
;   pant_tope    is comp_dup + 3   ; how many letters of a text, at most

; The buffer, blank.
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

; The buffer to the tilemap: one DMA, in vblank.
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
    stz A1B0                    ; the buffer lives in bank 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; One letter: A the character, `temp + 1` the variant —0 white, 1 gray, 2 the
; "goes up" color, which only has digits, and 3 red: see `ITEM_SUBE` in
; titulo.py—. It goes at `eleg_tabla`, which advances one cell. Clobbers X
; and Y.
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
    tay                         ; one table further per variant
otra_tabla:
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
    dey
    bne otra_tabla
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

; A text: X its number —see `item_txt_*`—, at `eleg_tabla` and with the
; variant in `temp + 1`, and no more than `pant_tope` letters.
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
    sta temp                    ; how many letters
    stz temp + 2                ; which one it is on
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
    sta comp_dup + 3               ; the cap is for one text only
    rts
.endproc

; A number from `pant_valor`, 0 to 999, in `pant_ancho` digits —2 or 3— with
; leading spaces, at `eleg_tabla` and with the variant in `temp + 1`.
.proc pant_numero
.a8
.i16
    stz temp + 3                ; a digit has already been written
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
    lda comp_dup              ; the units, always
    clc
    adc #$30
    jmp pant_glifo

; X: the digit. A zero before everything else goes out as a space.
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


