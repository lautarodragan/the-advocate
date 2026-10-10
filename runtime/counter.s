.segment "FAR"
.a8
.i16

; --- the counter: a variable as two digit pictures ----------------------------
;
; What a common event of RM2k does when the project declares it a counter —see
; `compile_counter` in the event compiler—: the variable, clamped to 0..99,
; drawn with two pictures whose images are digits, and the tens picture erased
; under ten —" 9", not "09"—. Here the pictures are the timer's glyphs.
;
; It all lives in bank 1 because there is no room in bank 0: `op_counter` is
; a `jsl` to `counter_set`, and `oam_build` one to `counter_oam`, which comes
; back to bank 0 to draw through `glyph_oam_far`. That is why the RAM goes
; long, with `f:`, except the direct page's.

; `OP_COUNTER`. Enters with Y on the operands —the slot, `x` and `y`— and
; leaves it past them.
;
; The common event also writes the clamped value back into the variable, and
; this does not: nothing but the counter reads it, and the page that looks at
; it asks whether it is at zero or below, which is the same answer. It is the
; value **now**, not a live one: RM2k's pictures change only when the common
; event runs, and so does this.
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
    lda f:counter_visible
    bne shown
    lda #1
    sta f:counter_visible
    ; Its palette entries change owner: untinted now —see
    ; `upload_timer_pal`—. It is `timer_repaint`, which is in bank 0: with a
    ; neutral tint there is nothing to upload again, and asking would cost
    ; that frame's poses.
    lda tint_r
    cmp #TINT_NEUTRAL
    bne repaint
    lda tint_g
    cmp #TINT_NEUTRAL
    bne repaint
    lda tint_b
    cmp #TINT_NEUTRAL
    bne repaint
    lda f:tint_s
    cmp #TINT_NEUTRAL
    beq shown
repaint:
    lda #1
    sta f:tint_ready
shown:
    rtl
.endproc

; The counter's glyphs in OAM, from what `counter_set` left. They go **after
; the timer's and before the picture's**: in RM2k they are two pictures, under
; the timer, and they never share the screen with the one the ROM draws.
; Priority 3, like both.
.proc counter_oam
.a8
.i16
    lda f:counter_visible
    beq none
    ldx map_ofs
    lda f:map_table + M_TIMER_BASE, x
    ora f:map_table + M_TIMER_BASE + 1, x
    beq none                    ; this map does not carry the glyphs
    lda #0
    sta f:obj_big               ; the digits are 8x8
    rep #$20
.a16
    lda f:counter_x
    and #$00FF
    sta obj_x
    sep #$20
.a8
    lda f:counter_tens
    bmi ones                    ; under ten there are no tens
    jsr counter_glyph
ones:
    rep #$20
.a16
    lda obj_x                   ; the ones, one glyph to the right
    clc
    adc #8
    sta obj_x
    sep #$20
.a8
    lda f:counter_ones
    jsr counter_glyph
    lda #$02                    ; and whatever follows is 32x32 again
    sta f:obj_big
none:
    rtl
.endproc

; A: the glyph, at `obj_x` and the counter's `y`.
.proc counter_glyph
.a8
.i16
    sta f:timer_glyph
    rep #$20
.a16
    lda f:counter_y
    and #$00FF
    sta obj_y
    sep #$20
.a8
    jsl f:glyph_oam_far + FAST
    rts
.endproc
