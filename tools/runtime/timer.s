.segment "CODE"

; --- the timer -------------------------------------------------------------
; One frame of the countdown. It is `Game_Party::UpdateTimers`, and what
; matters is the end: on reaching zero seconds RM2k calls `StopTimer`, which
; stops the count **and hides it**. So the last value shown is 00:01 and after
; that nothing is left drawn, not a frozen 00:00.
.proc timer_tick
.a8
.i16
    lda timer_active
    bne runs
    rts
runs:
    lda timer_sub
    beq other_second
    dec timer_sub
    rts
other_second:
    lda #(TIMER_FRAMES - 1)
    sta timer_sub
    rep #$20
.a16
    lda timer_sec
    beq off_16                  ; it was already at zero: nothing to decrement
    dec a
    sta timer_sec
    sep #$20
.a8
    jsr timer_digits
    lda timer_sec
    ora timer_sec + 1
    beq off
    rts
.a16
off_16:
    sep #$20
.a8
off:
    stz timer_active
    lda timer_visible
    stz timer_visible           ; `stz` does not touch Z: the branch looks at the `lda`
    beq already_no_se_saw
    jsr timer_repaint           ; its entries get tinted again
already_no_se_saw:
    rts
.endproc

; The four digits of `timer_sec`, from minutes to seconds. It is called when
; the second changes and not every frame: it is two divisions by repeated
; subtraction, and at 60 hertz that would be the same result sixty times.
;
; The minutes fit in two digits because the converter does not let through a
; timer of more than 1092 seconds: the cap comes from the frame count in
; sixteen bits, not from the screen.
.proc timer_digits
.a8
.i16
    rep #$20
.a16
    lda timer_sec
    ldx #0
minus_60:
    cmp #60
    bcc ready_60
    sec
    sbc #60
    inx
    bra minus_60
ready_60:
    sta temp                    ; the leftover seconds
    txa
    sta temp + 2                ; and the minutes
    sep #$20
.a8

    lda temp + 2                ; the minutes, in two digits
    ldx #0
minus_10a:
    cmp #10
    bcc ready_10a
    sec
    sbc #10
    inx
    bra minus_10a
ready_10a:
    sta timer_dig + 1
    txa                         ; with 8-bit A it is the low byte of X
    sta timer_dig + 0

    lda temp                    ; and the seconds
    ldx #0
minus_10b:
    cmp #10
    bcc ready_10b
    sec
    sbc #10
    inx
    bra minus_10b
ready_10b:
    sta timer_dig + 3
    txa
    sta timer_dig + 2
    rts
.endproc

; The timer's five glyphs in OAM, each one as two stacked 8x8 objects. They go
; **first**, that is, in the lowest-index objects, which are the ones the
; console puts in front: in RM2k the timer is `Priority_Timer`, which sits
; above everything else, message window included. Here that comes from object
; priority 3, which wins over both layers.
;
; The colon blinks: it is drawn only in the upper half of the second, which is
; the `frames % 60 < 30 -> continue` of `Sprite_Timer::Draw`.
.proc timer_oam
.a8
.i16
    lda timer_visible
    bne has
    rts
has:
    ldx map_ofs
    lda f:map_table + M_TIMER_BASE, x
    ora f:map_table + M_TIMER_BASE + 1, x
    bne draw
    rts                         ; this ROM does not carry the glyphs
draw:
    stz obj_big                 ; the digits are 8x8
    stz timer_i
each_glyph:
    lda timer_i
    cmp #5
    bcc has_glyph
    jmp end
has_glyph:
    cmp #2
    bne is_digit
    ; The colon, and only when it is due.
    lda timer_sub
    cmp #(TIMER_FRAMES / 2)
    bcc next
    lda #TIMER_TWO_POINTS
    bra with_glyph
is_digit:
    ; The index into `timer_dig`: the position, minus one if it comes after
    ; the colon, which has no digit of its own.
    cmp #2
    bcc no_adjust
    dec a
no_adjust:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda timer_dig, x
with_glyph:
    sta timer_glyph
    ; Where it lands on screen. The X does not carry the characters' offset:
    ; the digits are 8x8 and their corner is their corner.
    rep #$20
.a16
    lda timer_i
    and #$00FF
    ; Eight per glyph, which is a shift and not a multiplication.
    asl a
    asl a
    asl a
    clc
    adc #TIMER_X
    sta obj_x
    lda #TIMER_Y
    sta obj_y
    sep #$20
.a8
    jsr glyph_oam
next:
    inc timer_i
    jmp each_glyph
end:
    lda #$02                    ; and whatever follows is 32x32 again
    sta obj_big
    rts
.endproc

; One glyph of the timer's, as two stacked 8x8 objects: `timer_glyph` says
; which, and its top-left corner is (`obj_x`, `obj_y`). It leaves `obj_y`
; sixteen lower. The timer draws its five with this, and the counter its two.
.proc glyph_oam
.a8
.i16
    stz timer_half
each_half:
    ; Which tile: the eleven glyphs fit in a row of sixteen, so the lower half
    ; is exactly sixteen further on.
    rep #$20
.a16
    lda timer_half
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc timer_glyph             ; in sixteen bits it carries into the next
    and #$00FF                  ; byte, and hence the `and`
    ldx map_ofs
    clc
    adc f:map_table + M_TIMER_BASE, x
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: priority 3 —in front of both layers—, the timer's palette,
    ; and the ninth bit of the tile.
    lda temp + 1
    and #$01
    sta temp + 2
    lda f:map_table + M_TIMER_PAL, x
    and #$07
    asl a
    ora #$30
    ora temp + 2
    sta obj_attr
    jsr emit_object
    rep #$20
.a16
    lda obj_y                   ; the lower half, eight further down
    clc
    adc #8
    sta obj_y
    sep #$20
.a8
    inc timer_half
    lda timer_half
    cmp #2
    bcc each_half
    rts
.endproc

; `glyph_oam` for bank 1, where `counter_oam` lives: a `jsl` cannot come back
; with `rts`.
.proc glyph_oam_far
    jsr glyph_oam
    rtl
.endproc

