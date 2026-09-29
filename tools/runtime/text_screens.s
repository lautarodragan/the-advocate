.segment "CODE"

; --- the text screens -----------------------------------------------------------
;
; The equipment and shop screens are pure text on top of the item screen's
; font. They are composed **whole** in `text_buf` —the 32 by 28 cell
; tilemap, 1792 bytes— and go up in one DMA at the start of each vblank, so
; composing is in no hurry. `screens.py` is the reference. A position is a
; byte of the buffer: row * 64 + column * 2; the cell below each letter is 64
; bytes further on.
;
; The scratch space is borrowed variables: the message composer's, `comp_*`,
; which are recomputed with each character, and with the menu open there is
; no message; and `pick_table`, which is the position being written to.
SCR_BYTES = 32 * 28 * 2
;   scr_value    is comp_dup       ; the number being written, two bytes
;   scr_width    is comp_dup + 2   ; in how many digits
;   scr_cap      is comp_dup + 3   ; how many letters of a text, at most

; The buffer, blank.
.proc scr_clear
.a8
.i16
    rep #$20
.a16
    ldx #0
other:
    stz text_buf, x
    inx
    inx
    cpx #SCR_BYTES
    bcc other
    sep #$20
.a8
    rts
.endproc

; The buffer to the tilemap: one DMA, in vblank.
.proc scr_upload
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #SLOT_MAP
    sta VMADDL
    lda #.loword(text_buf)
    sta A1T0L
    lda #SCR_BYTES
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
; "goes up" color, which only has digits, and 3 red: see `ITEM_UP` in
; menus.py—. It goes at `pick_table`, which advances one cell. Clobbers X
; and Y.
.proc scr_glyph
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_FIRST_CHAR
    asl a
    asl a
    tax
    lda temp + 1
    and #$00FF
    beq target
    tay                         ; one table further per variant
other_table:
    txa
    clc
    adc #ITEM_GLYPHS_GRAY
    tax
    dey
    bne other_table
target:
    ldy pick_table
    lda f:item_glyph_cells, x
    sta text_buf, y
    lda f:item_glyph_cells + 2, x
    sta text_buf + 64, y
    iny
    iny
    sty pick_table
    sep #$20
.a8
    rts
.endproc

; A text: X its number —see `item_txt_*`—, at `pick_table` and with the
; variant in `temp + 1`, and no more than `scr_cap` letters.
.proc scr_text
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
    bcc fits
    lda comp_dup + 3
fits:
    sta temp                    ; how many letters
    stz temp + 2                ; which one it is on
letter:
    lda temp + 2
    cmp temp
    bcs ready
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [msg_ptr], y
    jsr scr_glyph
    inc temp + 2
    bra letter
ready:
    lda #255
    sta comp_dup + 3               ; the cap is for one text only
    rts
.endproc

; A number from `scr_value`, 0 to 999, in `scr_width` digits —2 or 3— with
; leading spaces, at `pick_table` and with the variant in `temp + 1`.
.proc scr_number
.a8
.i16
    stz temp + 3                ; a digit has already been written
    lda comp_dup + 2
    cmp #3
    bcc tens
    rep #$20
.a16
    ldx #0
hundred:
    lda comp_dup
    cmp #100
    bcc hundred_ready
    sbc #100
    sta comp_dup
    inx
    bra hundred
hundred_ready:
    sep #$20
.a8
    jsr digit
tens:
    rep #$20
.a16
    ldx #0
ten:
    lda comp_dup
    cmp #10
    bcc ten_ready
    sbc #10
    sta comp_dup
    inx
    bra ten
ten_ready:
    sep #$20
.a8
    jsr digit
    lda comp_dup              ; the units, always
    clc
    adc #$30
    jmp scr_glyph

; X: the digit. A zero before everything else goes out as a space.
digit:
    txa
    bne write
    lda temp + 3
    bne write_zero
    lda #$20
    jmp scr_glyph
write_zero:
    lda #0
write:
    clc
    adc #$30
    pha
    lda #1
    sta temp + 3
    pla
    jmp scr_glyph
.endproc


