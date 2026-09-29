.segment "CODE"
.a8
.i16

; --- the interpreter: move routes and places --------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; A forced move route from MoveEvent. The first operand says on whom: 0 is the
; hero, and any other number is the event's index in the map's table plus
; one. **It is not the RM2k id**: 39 maps of this game have gaps in their
; event numbering, and translating is the converter's job.
;
; Of all of RM2k's move commands, the four turns, the four moves and the wait
; are accepted here: the converter emits no other.
;
; face_up/right/down/left are 12, 13, 14 and 15, and our directions are
; 0, 1, 2 and 3 in the same order, so subtracting twelve is enough.
;
; Both are kept as a pointer into the bytecode, which lives in the ROM and
; goes nowhere. The hero's was copied to RAM, with a 32-byte cap, until
; 2026-09-27: see `hero_route`.
.proc op_route
    lda [code_ptr], y            ; on whom
    sta route_target
    iny
    lda [code_ptr], y            ; at what frequency
    sta route_freq_op
    iny
    lda [code_ptr], y            ; how many commands it carries
    sta route_count
    stz route_count + 1
    iny
    lda route_target
    bne op_route_event

    ; --- the hero: the route is copied to RAM and `move_hero` walks it, not
    ; the interpreter: in RM2k `ForceMoveRoute` is asynchronous and the page
    ; goes on. What gets cut is the wait —`SetStopCount(0xFFFF)`: the first
    ; command runs right away— and nothing else: the step or jump in progress
    ; finishes, as there. Here the jump used to be cut too, and RM2k does not
    ; cut it.
    lda route_count
    sta route_n
    stz route_i
    stz route_wait
    lda route_freq_op
    sta route_freq
    ; The pointer, like an event's in `route_for_event`: the addition carries
    ; nothing into the bank byte because the code block fits whole in one.
    rep #$20
.a16
    tya
    clc
    adc code_ptr
    sta hero_route
    sep #$20
.a8
    lda code_ptr + 2
    sta hero_route + 2
    bra saltear_ruta

    ; --- an event: note where the route starts inside the bytecode and which
    ; command it is on, and the page's cursor skips over the commands.
op_route_event:
    phy
    jsr route_for_event
    ply
saltear_ruta:
    rep #$20
.a16
    tya
    clc
    adc route_count
    tay
    sep #$20
.a8
    jmp run_code::otro

.endproc

; Plants an event on a cell: ChangeEventLocation. It is `MoveTo`, and nothing
; but `MoveTo`: the cell changes right away and the step or jump in progress
; is cut —`SetRemainingStep(0)`—, whatever route it had goes on with the next
; command from here, and which way it faces does not change; only RM2k3
; touches the direction. The opening cutscene uses it six times to bring
; Core, Manta and the droid into the scene.
.proc op_place
    lda [code_ptr], y            ; the target: the event's index plus one
    dec a
    sta temp
    iny
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tax
    lda [code_ptr], y
    sta ev_pos_buf + 0, x       ; the cell, which is what the routes, the
    iny                         ; action button and touch look at
    iny
    lda [code_ptr], y
    sta ev_pos_buf + 2, x
    iny
    iny
    sep #$20
.a8
    phy
lugar_plantar:                  ; with Y already on the stack: see `op_place_var`
    jsr plant_event
    ply
    jmp run_code::otro

.endproc

; `ChangeEventLocation` with the cell in **two variables**, which is the other
; branch of `CommandChangeEventLocation`. The rest is identical to
; `op_place`: the same `MoveTo`, that is, the cell changes right away, the
; step in progress is cut, and neither the route nor the facing is touched.
; See OP_PLACE_VAR in eventos.py.
;
; Both reads go **before** writing either of the two words, as in `op_swap`:
; a variable read after moving the event could already hold something else if
; it is one of `ControlVars`' coordinate ones. In this game it does not happen
; —the minigame on map 11 computes them beforehand— but it is the same rule
; and costs nothing.
;
; `var_read` does not touch X or `temp`, so the row offset is computed only
; once and survives both reads.
.proc op_place_var
.a8
.i16
    lda [code_ptr], y            ; the target: the event's index plus one
    dec a
    sta temp
    iny
    lda [code_ptr], y            ; the slot for x
    sta temp + 1
    iny
    lda [code_ptr], y            ; and the one for y
    sta temp + 2
    iny
    phy
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tax
    sep #$20
.a8
    lda temp + 1
    jsr var_read                ; returns with M at sixteen
.a16
    pha
    sep #$20
.a8
    lda temp + 2
    jsr var_read
.a16
    sta ev_pos_buf + 2, x
    pla
    sta ev_pos_buf + 0, x
    sep #$20
.a8
    bra op_place::lugar_plantar

.endproc

; `TradeEventLocations`: the two events swap cells, and each one is a
; `MoveTo` like the one in `op_place` —the cell, cutting the step, and the
; drawing that follows it—. Both cells are read before writing either.
.proc op_swap
    lda [code_ptr], y            ; the first: the index plus one
    dec a
    sta swap_a
    iny
    lda [code_ptr], y            ; and the second
    dec a
    sta swap_b
    iny
    phy
    rep #$20
.a16
    lda swap_a
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tax
    lda swap_b
    and #$00FF
    asl a
    asl a
    tay
    lda ev_pos_buf + 0, x
    sta cell_x
    lda ev_pos_buf + 2, x
    sta cell_y
    lda ev_pos_buf + 0, y
    sta ev_pos_buf + 0, x
    lda ev_pos_buf + 2, y
    sta ev_pos_buf + 2, x
    lda cell_x
    sta ev_pos_buf + 0, y
    lda cell_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    lda swap_a
    sta temp
    jsr plant_event
    lda swap_b
    sta temp
    jsr plant_event
    ply
    jmp run_code::otro

.endproc

; "Wait for the move routes to finish". If none is left running it does not
; cost even one frame, which is what the `while` in `Game_Interpreter::Update`
; does; and if one is, the cursor is left **on the opcode** and the frame
; ends, so the next one asks again. It waits until **none** is left, neither
; the hero's nor any event's: it is `Game_Map::IsAnyMovePending`, and not a
; wait for the event that was just sent walking.
.proc op_wait_routes
    jsr any_routes
    beq op_wait_routes_next
    dey                         ; the cursor goes back to the opcode
    sty ev_cur
    rts
op_wait_routes_next:
    jmp run_code::otro

.endproc

; `HaltAllMovement`: every forced move route on the map is dropped at once.
; It is `Game_Map::RemoveAllPendingMoves`, that is, a `CancelMoveRoute` on the
; hero and on each event. It does not cost a frame: the page goes on in the
; same tick, which is the `return true` of `CommandHaltAllMovement`.
;
; What it does **not** do, and it is what sets it apart from `MoveTo`: the
; step and the jump in progress finish, and which way each one faces stays
; where the route left it. `any_routes` still watches them, so a
; `ProceedWithMovement` right after it waits the frames the step has left.
;
; And whoever had its page's own route goes back to it with
; `resume_page`, which is the same routine that runs when a forced one
; ends by itself: cancelling it and finishing it cannot be told apart, which
; is exactly the kind of difference nobody sees until the scene comes out
; different.
.proc op_stop_routes
.a8
.i16
    ; The hero. Its commands and wait are emptied; the step in progress is not.
    stz route_n
    stz route_i
    stz route_wait
    phy                         ; Y is the bytecode cursor
    ldx #$0000
parar_otra:
    lda route_ev, x
    cmp #ROUTE_EV_FREE
    beq parar_siguiente
    lda route_ev + 18, x
    and #$01
    bne parar_siguiente         ; the page's one is not forced
    lda route_ev + 27, x         ; does it have its own route to go back to?
    beq parar_sin_pagina
    jsr resume_page
    bra parar_siguiente
parar_sin_pagina:
    stz route_ev + 4, x
    stz route_ev + 5, x
    stz route_ev + 9, x
parar_siguiente:
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #ROUTE_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc parar_otra
    ply
    jmp run_code::otro

.endproc

