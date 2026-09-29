.segment "CODE"

; --- the timer -------------------------------------------------------------
; One frame of the countdown. It is `Game_Party::UpdateTimers`, and what
; matters is the end: on reaching zero seconds RM2k calls `StopTimer`, which
; stops the count **and hides it**. So the last value shown is 00:01 and after
; that nothing is left drawn, not a frozen 00:00.
.proc timer_tick
.a8
.i16
    lda timer_activo
    bne corre
    rts
corre:
    lda timer_sub
    beq otro_segundo
    dec timer_sub
    rts
otro_segundo:
    lda #(TIMER_CUADROS - 1)
    sta timer_sub
    rep #$20
.a16
    lda timer_seg
    beq apagar_16               ; it was already at zero: nothing to decrement
    dec a
    sta timer_seg
    sep #$20
.a8
    jsr timer_digitos
    lda timer_seg
    ora timer_seg + 1
    beq apagar
    rts
.a16
apagar_16:
    sep #$20
.a8
apagar:
    stz timer_activo
    lda timer_visible
    stz timer_visible           ; `stz` does not touch Z: the branch looks at the `lda`
    beq ya_no_se_veia
    jsr timer_repintar          ; its entries get tinted again
ya_no_se_veia:
    rts
.endproc

; The four digits of `timer_seg`, from minutes to seconds. It is called when
; the second changes and not every frame: it is two divisions by repeated
; subtraction, and at 60 hertz that would be the same result sixty times.
;
; The minutes fit in two digits because the converter does not let through a
; timer of more than 1092 seconds: the cap comes from the frame count in
; sixteen bits, not from the screen.
.proc timer_digitos
.a8
.i16
    rep #$20
.a16
    lda timer_seg
    ldx #0
menos_60:
    cmp #60
    bcc listo_60
    sec
    sbc #60
    inx
    bra menos_60
listo_60:
    sta temp                    ; the leftover seconds
    txa
    sta temp + 2                ; and the minutes
    sep #$20
.a8

    lda temp + 2                ; the minutes, in two digits
    ldx #0
menos_10a:
    cmp #10
    bcc listo_10a
    sec
    sbc #10
    inx
    bra menos_10a
listo_10a:
    sta timer_dig + 1
    txa                         ; with 8-bit A it is the low byte of X
    sta timer_dig + 0

    lda temp                    ; and the seconds
    ldx #0
menos_10b:
    cmp #10
    bcc listo_10b
    sec
    sbc #10
    inx
    bra menos_10b
listo_10b:
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
    bne hay
    rts
hay:
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_BASE, x
    ora f:mapa_tabla + M_TIMER_BASE + 1, x
    bne dibujar
    rts                         ; this ROM does not carry the glyphs
dibujar:
    stz obj_grande              ; the digits are 8x8
    stz timer_i
cada_glifo:
    lda timer_i
    cmp #5
    bcc hay_glifo
    jmp fin
hay_glifo:
    cmp #2
    bne es_digito
    ; The colon, and only when it is due.
    lda timer_sub
    cmp #(TIMER_CUADROS / 2)
    bcc siguiente
    lda #TIMER_DOS_PUNTOS
    bra con_glifo
es_digito:
    ; The index into `timer_dig`: the position, minus one if it comes after
    ; the colon, which has no digit of its own.
    cmp #2
    bcc sin_ajuste
    dec a
sin_ajuste:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda timer_dig, x
con_glifo:
    sta timer_glifo
    stz timer_mitad
cada_mitad:
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
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc #TIMER_Y
    sta obj_y

    ; And which tile: the eleven glyphs fit in a row of sixteen, so the lower
    ; half is exactly sixteen further on.
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc timer_glifo             ; in sixteen bits it carries into the next
    and #$00FF                  ; byte, and hence the `and`
    ldx mapa_ofs
    clc
    adc f:mapa_tabla + M_TIMER_BASE, x
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
    lda f:mapa_tabla + M_TIMER_PAL, x
    and #$07
    asl a
    ora #$30
    ora temp + 2
    sta obj_attr
    jsr emit_object

    inc timer_mitad
    lda timer_mitad
    cmp #2
    bcc cada_mitad
siguiente:
    inc timer_i
    jmp cada_glifo
fin:
    lda #$02                    ; and whatever follows is 32x32 again
    sta obj_grande
    rts
.endproc

