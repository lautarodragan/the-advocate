.segment "CODE"

; --- the events that are drawn walking ---------------------------------------
;
; An event with a graphic that walks changes three things per frame: where it
; is in pixels, which pose of the cycle it gets, and what key it is sorted by
; against the others. All three are written to its row in the NPC table, which
; is where `build_oam` reads from.

; One frame of the walk cycle for slot X. It is `animate_hero`, letter for
; letter, on purpose: the hero and the events walk with the same count.
.proc animate_ev_route
.a8
.i16
    ; `Game_Character::UpdateAnimation`, with the turn in place apart. +10 is the
    ; frame of the cycle, 0 to 3 —3 draws column 1—, and +11 how many frames
    ; it has been in it. With the animation stopped or jumping, the middle frame.
    ; One whose page turns in place does only that: see `spin_step`.
    lda route_ev + 18, x
    bpl no_spin
    jsl f:spin_step + FAST
    rts
no_spin:
    lda route_ev + 12, x
    and #$02
    bne still
    lda route_ev + 13, x
    bne still
    ; The limits, by speed.
    lda route_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda anim_idle, y
    sta temp
    lda anim_continues, y
    sta temp + 1
    ; The count goes up while walking, always with continuous animation, and
    ; while still only until it reaches the middle frame.
    lda route_ev + 18, x
    and #$10
    bne sum
    lda route_ev + 6, x
    bne sum
    lda route_ev + 10, x
    and #$01
    beq sum                     ; on frame 0 or 2 it goes on to the middle one
    lda route_ev + 11, x
    inc a
    cmp temp
    bcc sum                     ; count < stopped - 1
    bra see_change
sum:
    inc route_ev + 11, x
see_change:
    lda route_ev + 11, x
    cmp temp + 1
    bcs changes                 ; reached the continuous one
    lda route_ev + 6, x
    beq ready
    lda route_ev + 11, x
    cmp temp
    bcc ready                   ; walking, to the stopped one
changes:
    lda route_ev + 10, x
    inc a
    and #$03                    ; the cycle is four steps
    sta route_ev + 10, x
    stz route_ev + 11, x
ready:
    rts
still:
    lda #1
    sta route_ev + 10, x
    stz route_ev + 11, x
    rts
.endproc

; The NPC table row of the event in A, in Y, or $FFFF if it has none. Every
; row carries its event index, and the indices are unique, so at most one
; matches. An event without a graphic has no row and returns $FFFF.
.proc event_npc
.a8
.i16
    sta temp
    ldy #$0000
seek:
    cpy npc_total
    beq none
    lda npc_buf + 8, y
    cmp temp
    beq ready
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra seek
none:
    ldy #$FFFF
ready:
    rts
.endproc

; What `op_place` still needs after writing the cell: for the drawing to
; follow it. Enters with the event index in `temp`.
;
; If the event has a move route slot it is enough to cut its step and its jump:
; `move_events` runs later in this same frame and `refresh_npc` leaves it
; on the new cell, with the pose it had. If it has none —an event nobody sent
; walking— it is not given one: no slot is taken for this, and its row is moved
; by hand, without touching its tile, which is its page's pose.
.proc plant_event
.a8
.i16
    ldx #$0000
seek:
    lda route_ev, x
    cmp temp
    beq with_slot
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #ROUTE_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc seek

    ; No slot. If it has no graphic either there is nothing to move.
    lda temp
    jsr event_npc
    cpy #$FFFF
    beq ready
    sty npc_row
    lda temp
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    lda ev_pos_buf + 0, x       ; the cell times sixteen: it is standing on it
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 0, y
    lda ev_pos_buf + 2, x
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 2, y
    sta npc_py
    lda npc_buf + 4, y
    and #$F000                  ; the layer stays; the Y is replaced
    sta temp + 2
    lda npc_py
    and #$0FFF
    ora temp + 2
    sta npc_buf + 4, y
    sep #$20
.a8
    lda #0
    sta npc_buf + 11, y         ; no jump: nothing to lift
    jmp fit_npc                 ; and the row, to wherever it belongs now

with_slot:
    lda #0
    sta route_ev + 7, x         ; no step in progress
    sta route_ev + 22, x
    sta route_ev + 23, x
    sta route_ev + 13, x        ; nor jump
ready:
    rts
.endproc

