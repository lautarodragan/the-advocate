.segment "CODE"

; --- turning toward the hero -----------------------------------------------
;
; `Game_Event::ScheduleForegroundExecution`: the event the hero triggers
; —with the action button or by touch— turns around toward him, unless its
; animation locks the direction. It faces that way while its page lasts and,
; when it ends, goes back to its pose, which is the `UpdateFacing` of
; `OnFinishForegroundEvent`. The rules —when it turns, when it is undone— are
; in `turn_fire` and `turn_check`, below.
;
; There is only one turn at a time: only the event the hero triggered turns,
; and the previous one finished its page before. Its state lives in far RAM:
;
;   TURN_EV     the event, or $FF. **Its row is not saved**: rows get
;               reordered when someone walks —`fit_npc`—, and the saved
;               row ended up belonging to someone else. The first version gave
;               the Bum of Lashe City's tile back to the event that had ended
;               up in its place; `bum-vuelve` found it. The row is looked up
;               with `event_npc` every time.
;   TURN_K      the `npc_poses` entry for its graphic, and TURN_PPOSE the pose
;               of its page: with the two, a refresh knows whether the new
;               page brings the same graphic
;   TURN_DIR    which way it faces
;   GIRO_*_ANT  the row's tile, attributes and pose before turning, to give
;               them back
;   PICK_K, PICK_POSE   the +30 and the +31 of the page that won the last time
;               `seek_event_page` ran: its graphic's entry in `npc_poses`, and
;               its pose with bit 7 set if it does not turn —a page of an
;               event that walks carries the entry also when it does not:
;               see `walker_graphic`—
;
; A still one shares its VRAM slot with the other still ones of the same pose,
; so to turn it moves to the map's turn slot, `M_TURN_TILE4`, and the new pose
; is uploaded there. One that walks or animates in place has its own and turns
; where it is.
.pushseg
.segment "FARBSS"
far_turn: .res $B
.popseg
FAR_TURN   = .loword(far_turn)
TURN_EV    = $7E0000 + FAR_TURN
TURN_K     = TURN_EV + 3
TURN_PPOSE = TURN_EV + 4
TURN_TILE_PREV = TURN_EV + 5
TURN_ATTR_PREV = TURN_EV + 6
TURN_POSE_PREV = TURN_EV + 7
TURN_DIR   = TURN_EV + 8
PICK_K     = TURN_EV + 9
PICK_POSE  = TURN_EV + 10

; No turn. On reset and when loading a map: the rows are different ones.
.proc turn_clear
.a8
.i16
    lda #$FF
    sta f:TURN_EV
    rts
.endproc

; The page of `ev_sought` has just been queued by the hero: if it turns, make
; it face him. The event's cell is (cell_x, cell_y) and the hero's
; (tile_x, tile_y). Enters with PICK_K and PICK_POSE from its page.
.proc turn_fire
.a8
.i16
    lda f:PICK_POSE
    bpl turns
    rts                         ; the page does not turn: bit 7 of its +31
turns:
    lda ev_sought
    jsr event_slot
    cpx #$FFFF
    beq no_route
    ; `IsFacingLocked`: command 26 of its move route locked its facing and only
    ; 27 releases it, so it does not turn even with the hero talking to it. The
    ; route may have ended long ago —the bit stays in the slot— and that is why
    ; it is checked before `route_busy`: it is the dead director of
    ; `RunDirectorScene`, which does `26` and never a `27` (maps 19, 46 and
    ; 96).
    lda route_ev + 18, x
    and #$08
    bne fixed
    jsr route_busy
    beq no_route                ; the slot was left over from a finished route
fixed:
    rts                         ; a route running: it decides where it faces
no_route:
    lda ev_sought
    jsr event_npc
    cpy #$FFFF
    bne with_row
    rts
with_row:
    lda npc_buf + 9, y
    cmp #NPC_STILL
    bne can
    ldx map_ofs
    lda f:map_table + M_TURN_TILE4, x
    cmp #$FF
    bne can
    rts                         ; a still one with no turn slot
can:
    phy
    jsr turn_undo               ; if another one was left, it goes back to its own
    ply

    ; Which way: `GetDirectionToCharacter`, with sx and sy being the event
    ; minus the hero. If |sx| > |sy| the horizontal wins; otherwise, the
    ; vertical.
    rep #$20
.a16
    lda cell_x
    sec
    sbc tile_x
.ifdef wrap_maps
    jsl f:wrap_fold_cx          ; the short way round: see wrap.s
.endif
    pha                         ; sx
    bpl sx_pos
    eor #$FFFF
    inc a
sx_pos:
    sta temp                    ; |sx|
    lda cell_y
    sec
    sbc tile_y
.ifdef wrap_maps
    jsl f:wrap_fold_cy
.endif
    sta temp + 2                ; sy
    bpl sy_pos
    eor #$FFFF
    inc a
sy_pos:
    cmp temp
    bcs vertical                ; |sy| >= |sx|
    pla
    ; goombario: pull-branch: sx, the distance in x, saved before computing
    ; sy: negative is that the event is to the left of the hero
    bmi to_right
    lda #DIR_LEFT
    bra dir_list
to_right:
    lda #DIR_RIGHT
    bra dir_list
vertical:
    pla
    lda temp + 2
    beq down
    bmi down                    ; the event above the hero
    lda #DIR_UP
    bra dir_list
down:
    lda #DIR_DOWN
dir_list:
    sep #$20
.a8
    sta f:TURN_DIR

    lda ev_sought
    sta f:TURN_EV
    lda f:PICK_K
    sta f:TURN_K
    lda f:PICK_POSE
    sta f:TURN_PPOSE
    lda npc_buf + 6, y
    sta f:TURN_TILE_PREV
    lda npc_buf + 7, y
    sta f:TURN_ATTR_PREV
    lda npc_buf + 12, y
    sta f:TURN_POSE_PREV
    jmp turn_apply
.endproc

; The pose that faces TURN_DIR, in row Y: the column of the previous one and
; the row of the direction.
.proc turn_apply
.a8
.i16
    lda f:TURN_POSE_PREV
column:
    cmp #3
    bcc with_column
    sbc #3                      ; carry was left at 1
    bra column
with_column:
    sta temp
    lda f:TURN_DIR
    asl a
    clc
    adc f:TURN_DIR
    clc
    adc temp
    sta temp                    ; the new pose
    lda npc_buf + 9, y
    cmp #NPC_STILL
    beq still
    lda npc_buf + 13, y
    bpl not_animated
    jmp still_touched           ; animates in place: `animate_still` uploads it
not_animated:
    sty npc_row
    lda temp
    jmp upload_npc_pose
still:
    ; To the turn slot: its tile, with bit 8 in the attributes.
    lda temp
    sta npc_buf + 12, y
    ldx map_ofs
    lda f:map_table + M_TURN_TILE4, x
    asl a
    asl a                       ; the tile: the byte times four, and bit 8
    sta npc_buf + 6, y
    lda #0
    rol a
    sta temp + 1
    lda npc_buf + 7, y
    and #$FE
    ora temp + 1
    sta npc_buf + 7, y
    ; And the pose, out of its graphic's twelve: (k * 12 + pose) * 3 in
    ; `npc_poses`.
    lda f:TURN_K
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; times four
    sta temp + 2
    asl a
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2                ; thirty-six per graphic
    sta temp + 2
    lda temp
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; the pose times three
    clc
    adc temp + 2
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2
    ldx map_ofs
    lda f:map_table + M_TURN_TILE4, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; the tile
    asl a
    asl a
    asl a
    asl a                       ; sixteen words per tile
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_queue
    bne ready
    jsr turn_undo               ; the queue was full: it does not turn
ready:
    rts
.endproc

; Whether move route slot X has something running: its page's own route,
; commands still to give, a step, a wait or a jump. Z=1 if it is free. A
; slot is not released until another map is loaded —or until all are taken
; and another event needs it: `reclaim_slot`—, so "has a slot" was not
; enough: the
; `GangMember1` of Lashe City, which a scene had already moved, never turned
; again. taro found it playing.
.proc route_busy
.a8
.i16
    lda route_ev + 18, x
    and #$01
    bne if
    lda route_ev + 5, x
    cmp route_ev + 4, x
    bcc if
    lda route_ev + 7, x
    ora route_ev + 9, x
    ora route_ev + 13, x
    bne if
    lda #0
    rts
if:
    lda #1
    rts
.endproc

; The turn is over: the row goes back to its own. Touches nothing if there is
; none.
.proc turn_undo
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nothing
    jsr event_npc
    lda #$FF
    sta f:TURN_EV
    cpy #$FFFF
    beq nothing
    lda npc_buf + 9, y
    cmp #NPC_STILL
    bne own
    lda f:TURN_TILE_PREV
    sta npc_buf + 6, y
    lda f:TURN_ATTR_PREV
    sta npc_buf + 7, y
    lda f:TURN_POSE_PREV
    sta npc_buf + 12, y
    rts
own:
    lda npc_buf + 13, y
    bpl not_animated
    jmp still_touched           ; animates in place: goes back by itself, next frame
not_animated:
    sty npc_row
    lda f:TURN_POSE_PREV
    jmp upload_npc_pose
nothing:
    rts
.endproc

; A: an event that takes a move route slot. If it was the one turning, the
; turn is over: from now on the route decides where it faces.
.proc turn_per_route
.a8
.i16
    cmp f:TURN_EV
    bne nothing
    jmp turn_undo
nothing:
    rts
.endproc

; At the start of a refresh that applies pages: if the turning event changed
; to a page that does not turn or has another graphic, the turn is over. It is
; the `SetFacing(page->character_direction)` of `Game_Event::RefreshPage`,
; which only happens if the new page is a different one.
.proc turn_check
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nothing
    rep #$20
.a16
    and #$00FF
    sta ev_sought
    sep #$20
.a8
    jsr seek_event_page
    lda chosen_any
    beq undo                    ; it was left without a page
    lda f:PICK_POSE
    bmi undo                    ; the new page does not turn
    cmp f:TURN_PPOSE
    bne undo
    lda f:PICK_K
    cmp f:TURN_K
    bne undo
nothing:
    rts
undo:
    jmp turn_undo
.endproc

; Row Y has just received its page's graphic: if it is the turning event's and
; the turn is still on, it is put back on top.
.proc turn_restore
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nothing
    cmp npc_buf + 8, y
    bne nothing
    lda npc_buf + 12, y
    sta f:TURN_POSE_PREV
    lda npc_buf + 6, y
    sta f:TURN_TILE_PREV
    lda npc_buf + 7, y
    sta f:TURN_ATTR_PREV
    jmp turn_apply
nothing:
    rts
.endproc

; Which way row Y faces, for `animate_still`: its page's, or the turn's if it
; is the one turning. Returns A.
.proc facing_of_row
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq own
    cmp npc_buf + 8, y
    bne own
    lda f:TURN_DIR
    rts
own:
    lda npc_buf + 10, y
    rts
.endproc

