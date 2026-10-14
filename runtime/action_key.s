.segment "CODE"

; --- the action button -------------------------------------------------------
;
; Talking to something. It is what turns this into a game and not a cutscene:
; of the 1599 pages of this game that fire this way, 1006 already compile,
; against 110 autostart ones.
;
; The rule comes from `Game_Player::CheckActionEvent`: the touch events in
; front, the hero's cell and then the one in front. What is not here yet is
; the loop of up to three counters.

; Is there an event at (cell_x, cell_y)? Returns its index in A, or $FF. A
; twin's cell answers with the event whose row it shares: see
; `twin_in_cell`.
.proc event_in_cell
.a8
.i16
    ldy #$0000
    ldx #$0000
seek:
    cpx ev_total
    beq none
    rep #$20
.a16
    lda ev_pos_buf, y
    cmp cell_x
    bne next
    lda ev_pos_buf + 2, y
    cmp cell_y
    bne next
    sep #$20
.a8
    txa                         ; the index fits in a byte: EV_MAX is 128
    rts
next:
.a16                            ; reached in sixteen bits, from the `bne` above
    tya
    clc
    adc #EV_STRIDE
    tay
    sep #$20
.a8
    inx
    bra seek
none:
    ; falls through: no row is on that cell, but a twin may be
.endproc

; The twin on (cell_x, cell_y), if there is one: the index of the event
; whose row it shares in A, or $FF.
;
; A twin is an event the converter left without a row because its map has
; more than `EV_MAX` and its pages are the same as another's: invisible,
; still and off the hero's layer, so the only thing it does is fire those
; pages from its own cell. Its cell lives in ROM, behind the map's
; positions —a word with how many, then TWIN_STRIDE bytes each: x, y and
; the event—; see `ev_pos_bytes` in `rm2k-snes-mapdata`. It is looked at
; only after the rows, and a map whose events fit has none: its word is 0.
;
; `npc_ptr` is borrowed: it only lives while the load copies a table.
.proc twin_in_cell
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_PTR_EV_POS, x
    sta npc_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_EV_POS + 2, x
    sta npc_ptr + 2
    rep #$20
.a16
    lda ev_total
    asl a
    asl a                       ; past the positions: EV_STRIDE each
.assert EV_STRIDE = 4, error, "the arithmetic above multiplies by four by hand"
    tay
    lda [npc_ptr], y            ; how many twins
    beq none
    tax
    iny
    iny
look:
    lda [npc_ptr], y            ; +0 x
    iny
    iny
    cmp cell_x
    bne other
    lda [npc_ptr], y            ; +2 y
    cmp cell_y
    bne other
    iny
    iny
    lda [npc_ptr], y            ; +4 the event whose row it shares
    sep #$20
.a8
    rts
.a16
other:
    iny
    iny
    iny
    iny                         ; from +2 to the next twin
.assert TWIN_STRIDE = 6, error, "the walk above steps six bytes by hand"
    dex
    bne look
none:
    sep #$20
.a8
    lda #$FF
    rts
.endproc

; The active page of event `ev_sought`, into `chosen`. Without looking at
; the trigger: the caller decides what to do with it. It is the rule of
; `pick_pages` —the highest-numbered one whose conditions hold wins—, for a
; single event, and it is resolved
; **at the moment of using it**, not when the event was flagged, which is what
; `Game_Map::Update` does when it pushes the event that was waiting.
.proc seek_event_page
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_PAGE_COUNT, x
    beq no_pages
    sta pages_left
    lda f:map_table + M_PTR_PAGES, x
    sta page_ptr
    stz page_ofs
    sep #$20
.a8
    lda f:map_table + M_PTR_PAGES + 2, x
    sta page_ptr + 2
    stz chosen_any

walk:
    jsr read_page
    rep #$20
.a16
    lda pg_event
    cmp ev_sought
    sep #$20
.a8
    bne next                    ; not the event we are looking at
    jsr conditions_ok
    beq next
    lda pg_trigger
    sta chosen_trigger
    lda pg_layer
    sta chosen_layer
    rep #$20
.a16
    lda pg_code
    sta chosen
    sep #$20
.a8
    lda pg_code + 2
    sta chosen + 2
    lda #1
    sta chosen_any
    ; And its turn, +30 and +31: see `turn_fire` and `turn_check`.
    rep #$20
.a16
    lda page_ofs
    clc
    adc #30
    tay
    sep #$20
.a8
    lda [page_ptr], y
    sta f:PICK_K
    iny
    lda [page_ptr], y
    sta f:PICK_POSE

next:
    rep #$20
.a16
    lda page_ofs
    clc
    adc #PAGE_BYTES
    sta page_ofs
    dec pages_left
    sep #$20
.a8
    bne walk

    rts
no_pages:
.a16                            ; reached in sixteen bits; the `sep` narrows it
    sep #$20
.a8
    stz chosen_any
    rts
.endproc

; The firing by action button or by touch: looks up the event's active page
; and, if it has the requested trigger and it compiled, flags the event.
.proc queue_by_action
.a8
.i16
    jsr seek_event_page
    lda chosen_any
    beq no
    lda chosen_trigger
    cmp trigger_sought
    beq trigger_ok
    ; The event's touch —`Trigger_collision`— fires from the hero's side
    ; exactly as touch: `CheckEventTriggerThere` and `CheckEventTriggerHere`
    ; ask for both. Its own way, the event walking into the hero, is
    ; `collide_with_hero`.
    cmp #TRIGGER_COLLISION
    bne no
    lda trigger_sought
    cmp #TRIGGER_TOUCHES_HERO
    bne no
trigger_ok:
    ; The layer rule, opposite depending on which cell is looked at: the one
    ; in front only fires events on the hero's layer —`CheckEventTriggerThere`
    ; asks for `Layers_same`— and the hero's own cell only those on another
    ; layer —`CheckEventTriggerHere` asks for `!= Layers_same`—. It is not
    ; decorative symmetry: an event on the hero's layer blocks the way, so the
    ; hero could never stand on top of it.
    ;
    ; The same rule for touch: stopping on the cell is `CheckEventTriggerHere`
    ; and the button or a bump on the one in front, `CheckEventTriggerThere`.
    ; Until 2026-10-05 touch was left to the compiler, which dropped the
    ; touch pages on the hero's layer: see `try_bump`.
    lda chosen_layer
    cmp #HERO_LAYER
    beq was_hero
    lda own_action
    beq no                      ; another layer, but we are looking ahead
    bra no_layer
was_hero:
    lda own_action
    bne no                      ; the hero's layer, but we are looking at our own cell
no_layer:
    lda chosen
    ora chosen + 1
    ora chosen + 2
    beq no                      ; the active page could not be compiled
    ldx ev_sought
    jsr mark_waiting
    jsr turn_fire               ; and it turns toward the hero, if it turns
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; The cell given in (cell_x, cell_y): if there is an event and its active
; page is fired by the button, it gets queued. Returns A nonzero if it queued.
.proc action_in_cell
.a8
.i16
    jsr event_in_cell
    cmp #$FF
    beq no
    rep #$20
.a16
    and #$00FF
    sta ev_sought
    sep #$20
.a8
    jmp queue_by_action
no:
    lda #0
    rts
.endproc

; The touch event of the cell the hero has just stopped on.
;
; It is `CheckEventTriggerHere` from `Game_Player::UpdateMovement`. Doors are
; a particular case of this —a teleport in a touch page— and they are handled
; earlier, separately: if there was a door, the map already changed and there
; is nothing left to look at here.
; With a page running it is **also** checked, and the page it fires goes into
; the queue behind the one running: in RM2k `UpdateMovement` does not ask
; about the interpreter, `ScheduleForegroundExecution` leaves the event
; waiting and `Game_Map` starts it when the interpreter frees up. There used
; to be a guard here that dropped the touch in that case, written for the pad
; —and for the pad it is superfluous, because `move_hero` does not start a
; step with a page in the foreground—; with a forced route it did happen: a
; page that sends the hero walking and then waits ended up with the touch
; lost. The queue is the same as the autostart one, one behind the other,
; which is what RM2k does.
;
; What is not modeled, on either side: an event that fires twice before
; running comes in here twice and only once in RM2k, which flags it with a
; bit.
.proc try_touch
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta cell_x
    lda tile_y
    sta cell_y
    sep #$20
.a8
    lda #1
    sta own_action              ; the own cell: the other layers
    bra touch_in_cell
.endproc

; The touch event of the cell in front, when the pad pushes the hero against
; it and he does not move.
;
; It is the `CheckEventTriggerThere` after `Move` in
; `Game_Player::UpdateNextMovementAction`: with the step refused —by the
; event itself, which is on the hero's layer and blocks, or by anything
; else— the cell in front fires its touch pages. The action button looks
; there too: see `try_action`. Measured in the original runtime with a
; shopkeeper standing in his doorway, touch and on the hero's layer: a bump
; and the button both make him talk. Until 2026-10-05 neither did here,
; because the compiler left those pages without code —"the hero would never
; step on them"— and his shop never opened.
;
; Called only from the pad, with no route and no page: a forced route that
; bumps fires nothing in RM2k either. Once it fires, `waiting_n` keeps the
; pad off until the page ends, so holding the direction does not queue it
; again.
.proc try_bump
.a8
.i16
    jsr front_cell
    stz own_action              ; the cell in front: the hero's layer
    ; falls through
.endproc

; The touch pages of (cell_x, cell_y), with `own_action` saying which of the
; two cells it is. Returns A nonzero if it queued, like `action_in_cell`.
.proc touch_in_cell
.a8
.i16
    lda #TRIGGER_TOUCHES_HERO
    sta trigger_sought
    jsr action_in_cell
    ldx #TRIGGER_ACTION
    stx trigger_sought          ; left as the action button expects it
    cmp #0                      ; the `ldx` left its own flags
    rts
.endproc

; The action button, from the main loop. Returns A nonzero if it queued
; something.
.proc try_action
.a8
.i16
    ; With a live forced route of the hero there is no talking: it is the
    ; `IsMoveRouteOverwritten()` in `game_player.cpp:297`, which returns
    ; before looking at the button. The `IsStopping()` the caller checks
    ; —`step_left`— is not enough, because between two steps of a route, in a
    ; `wait` and in the air, `step_left` is zero. These are the three hero
    ; things from `any_routes` without the step one, which was already checked
    ; there. It goes here and not next to that one because there the `beq
    ; nothing` above no longer reached.
    ;
    ; It was missing, and it showed when the page ends before its route: the
    ; one in `EV0043` of map 8 is a lone `MoveEvent`, so the hero went down the
    ; pipe with no page anymore, and an A between two steps, at (52,20) facing
    ; down, talked to the `EV0052` opposite —hero's layer, placed to be faced
    ; from the left— and sent him back up. With an emulator's autofire, which
    ; presses every two frames, it always happened. Caught by
    ; `test_action_with_route.py`.
    lda route_jump
    bne with_route              ; in the air
    lda route_wait
    bne with_route              ; in a route `wait`
    lda route_i
    cmp route_n
    bcc with_route              ; it has move commands left
    ; The two cells, in the order of `Game_Player::CheckActionEvent`: first the
    ; hero's own —`CheckEventTriggerHere`, which asks for a layer different
    ; from the hero's— and then the one in front —`CheckEventTriggerThere`,
    ; which asks for the hero's—. The own cell was left undone until
    ; 2026-09-07 and taro found it playing: the door out of Talan's pad is
    ; `TalDoorTop`, action-triggered and on layer 2, and it opens by standing
    ; on it.
    ;
    ; And before both, the touch pages of the one in front: RM2k's first
    ; `CheckEventTriggerThere` asks for touch and collision, and only then
    ; come the action pages. Each cell here stops at the first one it
    ; queues, and RM2k queues all three if there are three: an action event
    ; under the hero and a touch one in front of him, both at once, is not
    ; modeled.
    jsr try_bump
    beq own_cell
    rts                         ; queued the touch one in front
own_cell:
    lda #1
    sta own_action
    rep #$20
.a16
    lda tile_x
    sta cell_x
    lda tile_y
    sta cell_y
    sep #$20
.a8
    jsr action_in_cell
    beq look_ahead
    rts                         ; queued the one under the hero
look_ahead:
    stz own_action
    jsr front_cell
    jmp action_in_cell
with_route:
    lda #0
    rts
.endproc

; The cell in front of the hero, into (cell_x, cell_y).
.proc front_cell
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta cell_x
    lda tile_y
    sta cell_y
    sep #$20
.a8
    ; The cell of `GetDirection`, not of the `facing`: locked, the two part,
    ; and it is the way he last tried to go. See `hero_heading`.
    lda hero_lock
    beq look_facing
    lda hero_heading
    bra look_heading
look_facing:
    lda hero_dir
look_heading:
    cmp #DIR_UP
    bne no_up
    rep #$20
.a16
    dec cell_y
    sep #$20
.a8
    bra look
no_up:
    cmp #DIR_DOWN
    bne no_down
    rep #$20
.a16
    inc cell_y
    sep #$20
.a8
    bra look
no_down:
    cmp #DIR_LEFT
    bne no_left
    rep #$20
.a16
    dec cell_x
    sep #$20
.a8
    bra look
no_left:
    rep #$20
.a16
    inc cell_x
    sep #$20
.a8
look:
    rts
.endproc

