.segment "FAR"
.a8
.i16

; --- OP_COUNTER: a variable as two digit pictures -----------------------------
;
; What the declared common event does in RM2k, in one go: the variable,
; clamped to 0..99, drawn with two pictures whose images are digits, and the
; tens picture erased under ten —" 9", not "09"—. Here the pictures are the
; timer's glyphs, which `counter_oam` draws from what this leaves.
;
; The common event also writes the clamped value back into the variable, and
; this does not: nothing but the counter reads it, and the page that looks
; at it asks whether it is at zero or below, which is the same answer. It is
; the value **now**, not a live one: RM2k's pictures change only when the
; common event runs, and so does this.
;
; It lives in bank 1 because there is no room in bank 0: `op_counter` is a
; `jsl` to here, and that is why the RAM goes long, with `f:`.
;
; Enters with Y on the operands —the slot, `x` and `y`— and leaves it past
; them.
.proc counter_set
.a8
.i16
    lda [code_ptr], y           ; the slot
    iny
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per variable
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    bpl not_below
    lda #0
not_below:
    cmp #100
    bcc fits
    lda #99
fits:
    sep #$20
.a8
    ldx #0                      ; the tens, by subtraction: at most nine
tens:
    cmp #10
    bcc done
    sbc #10                     ; the carry is set: the `cmp` said so
    inx
    bra tens
done:
    sta f:counter_ones
    txa                         ; with 8-bit A it is the low byte of X
    bne has_tens
    lda #$FF                    ; under ten there are no tens
has_tens:
    sta f:counter_tens
    lda [code_ptr], y
    sta f:counter_x
    iny
    lda [code_ptr], y
    sta f:counter_y
    iny
    lda #1
    sta f:counter_visible
    rtl
.endproc
