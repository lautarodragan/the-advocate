.segment "FAR"
.a8
.i16

; --- the events that walk by a movement type ---------------------------------
;
; A page whose movement type is random, vertical, horizontal, toward the hero
; or away from him —`MoveType_random` to `MoveType_away`, 1 to 5— walks with
; no route of its own: each time it has stood still long enough, RM2k decides
; one step, `Game_Event::UpdateSelfMovement`. The converter gives that page an
; own route of a single command, `ROUTE_BY_TYPE` plus its type —49 to 53, not
; RM2k's—, which repeats; `ev_route_frame` sends it here. That way the type
; rides on everything a route already has: its slot, the step, the walk cycle,
; the wait after each step, the bump into the hero that fires an event's
; touch, and the stop while the interpreter runs a page. See `route::own` in
; rm2k-snes-events.
;
; What each decision is, from easyrpg-player's `game_event.cpp`:
;
; * random, `MoveTypeRandom`: of ten draws, three go straight on, two turn
;   left, two right, one turns back, and two stand still a random part of the
;   wait. The wait after a step is the step's times three to six fifths,
;   `SetMaxStopCountForRandom`.
; * vertical and horizontal, `MoveTypeCycle`: down —right— until something
;   is in the way, and after twenty frames of trying it turns back; up —left—
;   the same, and back down.
; * toward and away, `MoveTypeTowardsOrAwayPlayer`: off screen, a random
;   direction; on screen, of ten draws one goes on the way it was going, one
;   at random, and eight toward the hero —or away from him—.
;
; And what all of them do when the step is refused, which is not a route's
; "retry the command": the event does not turn —`SetFacing(prev_dir)`— and
; tries again on the next frame, a new decision each time; after sixty frames
; in vain, or if the bump fired a page, it turns where it tried and starts
; the whole wait over, `SetStopCount(0)`.
;
; The slot's +14 is this file's while the type walks: the frames it has been
; trying in vain, in bits 0 to 5, and in bit 6 whether +30, the direction of
; its last step, is worth reading. It is a jump's dx, which no type walks: a
; route forced on the event can jump, and `resume_page` clears it when the
; type comes back, as `load_page_into_slot` does when the page arrives.
;
; The draws come from a xorshift of their own, `walk_rng`, seeded at reset:
; the map's one is `ControlVars`'s, and walkers drawing from it every few
; frames would change every random number a page asks for. Not RM2k's
; generator either, so a random walk is random but not the same walk.

.pushseg
.segment "FARBSS"
walk_rng:    .res 2         ; the walkers' xorshift
; The command being decided —`ROUTE_BY_TYPE` plus the type— while its step is
; tried, so that `ev_route_frame` sends the refusal and the success here; 0
; when there is none. Bit 7: a cycle already tried the way back this frame.
walk_kind:   .res 1
walk_face:   .res 1         ; where the slot faced before trying
walk_cur:    .res 1         ; the direction it was going
walk_toward: .res 1         ; and the one toward the hero
walk_tries:  .res 1         ; the frames it had tried in vain before this one
.popseg

; Not RM2k's command codes: theirs end at 41. See `route::ROUTE_BY_TYPE`.
ROUTE_BY_TYPE = 48
WALK_RANDOM     = ROUTE_BY_TYPE + 1
WALK_VERTICAL   = ROUTE_BY_TYPE + 2
WALK_HORIZONTAL = ROUTE_BY_TYPE + 3
WALK_AWAY       = ROUTE_BY_TYPE + 5
WALK_TRYING = $3F           ; in +14: the frames trying in vain
WALK_KNOWN  = $40           ; in +14: +30 is its last step's direction
; Any value but zero, which a xorshift never leaves.
WALK_SEED   = $2B1D
; RM2k's margin around the screen for toward and away, two cells.
WALK_MARGIN = 32
; How many route slots a walker by type leaves free for the forced routes:
; the page that sends the most events walking at once in ABL moves four.
WALK_RESERVE = 4
; In a page's speed byte: it walks by a type. See `page_table` in
; rm2k-snes-mapdata.
PAGE_BY_TYPE = $08

.proc walk_boot
.a8
.i16
    rep #$20
.a16
    lda #WALK_SEED
    sta walk_rng
    sep #$20
.a8
    lda #0
    sta walk_kind
    rtl
.endproc

; The next draw, its high byte in A. The same xorshift as `random_next`, on
; its own state. Clobbers `temp`; keeps X and Y.
.proc walk_random
.a8
.i16
    rep #$20
.a16
    lda walk_rng
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp
    sta temp                    ; x ^= x << 7
    xba
    and #$00FF
    lsr a
    eor temp
    sta temp                    ; x ^= x >> 9
    xba
    and #$FF00
    eor temp                    ; x ^= x << 8
    sta walk_rng
    sep #$20
.a8
    xba                         ; the high byte, which mixes better
    rts
.endproc

; A draw from 0 to A - 1, with A from 1 to 255: the high byte of the draw
; times A, by the hardware multiplier. Clobbers `temp`; keeps X and Y.
.proc walk_below
.a8
.i16
    pha
    jsr walk_random
    sta WRMPYA
    pla
    sta WRMPYB                  ; eight cycles until the product is there
    nop
    nop
    nop
    nop
    lda RDMPYL + 1
    rts
.endproc

; The frames a random walker waits after a step, into A: the step's times
; three to six, over five. It is `SetMaxStopCountForRandom`; the pause that
; stands still a part of it draws a new one rather than remembering the last,
; which is the same distribution and saves the byte. With frequency 1 the
; step's is already held at 255, and six fifths of it do not fit a byte:
; it is held at 255 too.
.proc random_wait
.a8
.i16
    jsr step_wait
    sta WRMPYA
    lda #4
    jsr walk_below_keeping_a    ; 0 to 3
    clc
    adc #3
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #5
    sta WRDIVB                  ; sixteen cycles until the quotient is there
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL + 1
    beq fits
    lda #255
    rts
fits:
    lda RDDIVL
    rts
.endproc

; `walk_below` for `random_wait`, which has WRMPYA loaded: the multiplier's
; two inputs are only read when WRMPYB is written, so it is enough to keep
; the draw's product from being started. A draw from 0 to 3, by its two high
; bits.
.proc walk_below_keeping_a
.a8
.i16
    jsr walk_random
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    rts
.endproc

; The frames any character waits after a step, by slot X's frequency:
; `route_after_step`. Keeps X.
.proc step_wait
.a8
.i16
    phx
    lda route_ev + 16, x
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:route_after_step, x
    plx
    rts
.endproc

; The wait after a step that just ended in slot X, into A: a random walker's
; is its own, the rest's `route_after_step`. It is what `ev_route_frame`
; asks when a step ends. Its route says what it is: only a page's that walks
; by a type has one command from `ROUTE_BY_TYPE` on. Keeps X.
.proc walk_after_step
.a8
.i16
    lda route_ev + 18, x
    and #$01
    beq any
    rep #$20
.a16
    lda route_ev + 1, x
    sta route_ptr
    sep #$20
.a8
    lda route_ev + 3, x
    sta route_ptr + 2
    lda [route_ptr]
    cmp #WALK_RANDOM
    bne any
    jsr random_wait
    rtl
any:
    jsr step_wait
    rtl
.endproc

; The decision of slot X, whose command `walk_kind` already has, with the
; event's cell in `cell_x`/`cell_y` and the direction toward the hero in A.
; Returns the direction to try, or $FF if it stands still: then its wait is
; already set. Keeps X.
.proc walk_choose
.a8
.i16
    sta walk_toward
    lda route_ev + 8, x
    sta walk_face
    jsr walk_direction
    sta walk_cur
    lda walk_kind
    cmp #WALK_RANDOM
    beq random
    cmp #WALK_HORIZONTAL + 1
    bcc cycle
    jmp toward_or_away

random:
    lda #10
    jsr walk_below
    cmp #8
    bcs pause
    cmp #3
    bcc straight
    ; Two left, two right and one back: a quarter turn is adding three or one,
    ; half a turn two, with the directions in RM2k's order.
    cmp #5
    bcc left
    cmp #7
    bcc right
    lda #2
    bra turn
left:
    lda #3
    bra turn
right:
    lda #1
turn:
    clc
    adc walk_cur
    and #$03
    rtl
straight:
    lda walk_cur
    rtl
pause:
    ; `SetStopCount(Rand(0, max))`: what is left to wait is as random.
    jsr random_wait
    cmp #255
    beq whole                   ; 0 to 254 then, which `walk_below` takes
    inc a
whole:
    jsr walk_below
    sta route_ev + 9, x
    lda route_ev + 14, x
    and #<~WALK_TRYING
    sta route_ev + 14, x
    lda #0
    sta walk_kind
    lda #$FF
    rtl

cycle:
    ; Down —right— unless it already goes up —left—.
    ldy #DIR_DOWN
    cmp #WALK_VERTICAL
    beq default
    ldy #DIR_RIGHT
default:
    tya
    eor #$02                    ; the way back
    cmp walk_cur
    beq back
    tya
    rtl
back:
    rtl
.endproc

; The two that look at the hero, for `walk_choose`.
.proc toward_or_away
.a8
.i16
    jsr in_sight
    bcs seen
    lda #4
    jmp walk_below_rtl
seen:
    lda #10
    jsr walk_below
    cmp #0
    bne not_on
    lda walk_cur
    rtl
not_on:
    cmp #1
    bne at_hero
    lda #4
    jmp walk_below_rtl
at_hero:
    lda walk_kind
    cmp #WALK_AWAY
    beq away
    lda walk_toward
    rtl
away:
    lda walk_toward
    eor #$02                    ; `GetDirectionAwayCharacter`: half a turn
    rtl
.endproc

.proc walk_below_rtl
.a8
.i16
    jsr walk_below
    rtl
.endproc

; Whether slot X's event, at `cell_x`/`cell_y`, is on screen or within two
; cells of it: the carry. The screen is the console's, 256 by 224, and not
; RM2k's 320 by 240, so the same walker gives up on the hero a little closer.
; The point is RM2k's, `GetScreenX` and `GetScreenY`: the middle of the cell
; across, its foot down. Keeps X.
.proc in_sight
.a8
.i16
    rep #$20
.a16
    lda cell_x
    asl a
    asl a
    asl a
    asl a
    clc
    adc #8 + WALK_MARGIN
    sec
    sbc camera_x
.ifdef wrap_maps
    jsl f:wrap_fold_x           ; on the lap the screen is on: see wrap.s
.endif
    cmp #256 + 2 * WALK_MARGIN + 1
    bcs out
    lda cell_y
    asl a
    asl a
    asl a
    asl a
    clc
    adc #16 + WALK_MARGIN
    sec
    sbc camera_y
.ifdef wrap_maps
    jsl f:wrap_fold_y
.endif
    cmp #224 + 2 * WALK_MARGIN + 1
    bcs out
    sep #$20
.a8
    sec
    rts
out:
.a16
    sep #$20
.a8
    clc
    rts
.endproc

; Which way slot X was going: its last step's, if it took one; if not, where
; it faces, and if the slot has not turned it, where its row does —its
; page's—. Keeps X.
.proc walk_direction
.a8
.i16
    lda route_ev + 14, x
    and #WALK_KNOWN
    beq unknown
    lda route_ev + 30, x
    and #$03
    rts
unknown:
    lda route_ev + 8, x
    cmp #ROUTE_EV_NO_FACE
    bne ready
    jsl f:slot_npc + FAST       ; Y: its row, or $FFFF
    cpy #$FFFF
    beq none
    lda npc_buf + 10, y
    and #$03
    rts
none:
    lda #DIR_DOWN
ready:
    rts
.endproc

; Slot X's step toward `route_dir` was refused. Returns another direction to
; try on the same frame —the cycle's way back, after twenty frames—, or $FF.
; Keeps X.
.proc walk_blocked
.a8
.i16
    ; RM2k compares the stop counter before adding this frame to it: the
    ; first refusal finds it at the wait, plus nothing.
    lda route_ev + 14, x
    and #WALK_TRYING
    sta walk_tries
    cmp #WALK_TRYING
    beq counted
    inc route_ev + 14, x
counted:
    lda walk_kind
    bmi failed                  ; the way back was refused too
    cmp #WALK_VERTICAL
    beq cycle
    cmp #WALK_HORIZONTAL
    bne failed
cycle:
    lda walk_tries
    cmp #20
    bcc failed
    lda walk_kind
    ora #$80
    sta walk_kind
    lda route_dir
    eor #$02
    rtl
failed:
    lda waiting_n
    bne over                    ; the bump fired a page
    lda walk_tries
    cmp #60
    bcs over
    lda walk_face
    sta route_ev + 8, x         ; it does not turn
    bra done
over:
    ; The whole wait again, facing where it tried.
    lda route_ev + 14, x
    and #<~WALK_TRYING
    sta route_ev + 14, x
    lda walk_kind
    and #$7F
    cmp #WALK_RANDOM
    bne whole_step
    jsr random_wait
    bra wait
whole_step:
    jsr step_wait
wait:
    sta route_ev + 9, x
done:
    lda #0
    sta walk_kind
    lda #$FF
    rtl
.endproc

; Slot X's step went through: from now on its direction is the step's, and
; it has not been trying in vain. Keeps X.
.proc walk_stepped
.a8
.i16
    lda route_ev + 14, x
    and #<~WALK_TRYING
    ora #WALK_KNOWN
    sta route_ev + 14, x
    lda #0
    sta walk_kind
    rtl
.endproc

; Whether the page just read, which has an own route and no slot yet, may
; take one: the carry. One that walks by a type takes it only while
; WALK_RESERVE others stay free, so that a map full of walkers —Vampires
; Dawn's towns, with up to fifty-six— still has room for `MoveEvent`; the
; rest stand at their cell. The other own routes take it as before. Keeps
; A; X and Y are free, the caller asks for the slot afterwards.
.proc walk_may_take
.a8
.i16
    pha
    lda pg_speed
    and #PAGE_BY_TYPE
    beq yes
    ldy #0                      ; how many are free
    ldx #$0000
seek:
    lda route_ev, x
    cmp #ROUTE_EV_FREE
    bne taken
    iny
taken:
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
    cpy #WALK_RESERVE + 1
    bcs yes
    pla
    clc
    rtl
yes:
    pla
    sec
    rtl
.endproc
