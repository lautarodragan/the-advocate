.segment "CODE"

; --- the action button -------------------------------------------------------
;
; Talking to something. It is what turns this into a game and not a cutscene:
; of the 1599 pages of this game that fire this way, 1006 already compile,
; against 110 autostart ones.
;
; The rule comes from `Game_Player::CheckActionEvent`: the touch events in
; front, the hero's cell and then the one in front, all three. What is not
; here yet is the loop of up to three counters.

; Every event on (cell_x, cell_y) whose active page has `trigger_sought`,
; seen from the side `own_action` says, gets queued: `queue_by_action`
; decides each one. Returns A nonzero, with Z, if any was.
;
; **Every one, not the first**: it is `Game_Player::CheckEventTriggerThere`
; and `CheckEventTriggerHere`, which walk the whole list of the map's events
; and schedule each one standing on the cell whose page matches. Until
; 2026-11-20 this returned the first row on the cell and asked only that
; one, and Desert Nightmare stopped on day 1 twice: on map 12 the box, pushed
; onto the ladder to map 13 and left on an empty action page below, hid the
; ladder's touch page; on map 2 the dog, invisible on the middle of the
; gate, hid the teleport's twin under it. See `test_two_events_on_a_cell.py`
; in the test game and tasks/a-second-event-on-a-cell-is-never-asked.md.
;
; Marking several is safe for the same reason as in `try_action`: one bit per
; event, run by event number. The rows go **back to front**, so the
; lowest-numbered one is marked last and its turn toward the hero is the one
; that survives —RM2k turns each, here there is one turn at a time—; and it
; is also the cheaper way: see below. The twins come after the rows.
;
; **What it costs.** It runs on every bump —each frame the pad holds the hero
; against something—, on every step that ends and three times for the
; button. The walk is one compare per row, against `cell_x` held in A, in
; sixteen bits and back to front: under half of what the old walk paid per
; row. So the whole walk costs less than the old one did to find nothing,
; which is what a step onto an empty cell and a bump against a wall always
; paid, and those are most calls; what costs more than before is a bump into
; an event early in the table, which the old walk found at once. Measured in
; the task.
.proc action_in_cell
.a8
.i16
    lda #0
    sta f:cell_queued
    rep #$20
.a16
    lda ev_total
    asl a
    asl a                       ; times EV_STRIDE
.assert EV_STRIDE = 4, error, "the arithmetic above multiplies by four by hand"
    tay
    lda cell_x                  ; held in A for the whole walk: one compare a row
    bra next
other:
    cmp ev_pos_buf, y
    beq same_x
next:
    dey
    dey
    dey
    dey                         ; EV_STRIDE
    bpl other
    ; And the twins on the cell: a map whose events fit has none, and its
    ; count is one word.
    jsr twin_table
    beq done
    tax
    iny
    iny
look:
    lda [npc_ptr], y            ; +0 x
    cmp cell_x
    bne twin_next
    iny
    iny
    lda [npc_ptr], y            ; +2 y
    dey
    dey
    cmp cell_y
    bne twin_next
    phy
    phx
    iny
    iny
    iny
    iny
    lda [npc_ptr], y            ; +4 the event whose row it shares
    jsr queue_one
    jsr twin_table              ; `npc_ptr` again: the page it queued may
    plx                         ; have borrowed it
    ply
twin_next:
    tya
    clc
    adc #TWIN_STRIDE
    tay
    dex
    bne look
done:
    sep #$20
.a8
    lda f:cell_queued
    rts
.a16
same_x:
    lda ev_pos_buf + 2, y
    cmp cell_y
    bne not_here
    phy
    tya
    lsr a
    lsr a                       ; the index: EV_MAX is 128
    jsr queue_one
    ply
not_here:
    lda cell_x                  ; back in A for the walk
    bra next
.endproc

.pushseg
.segment "FARBSS"
; Whether `action_in_cell` queued any of the events on its cell.
cell_queued: .res 1
.popseg

; `queue_by_action` for the event in A, noted in `cell_queued`. Enters and
; leaves in sixteen bits. Clobbers X and Y.
.proc queue_one
.a16
.i16
    sta ev_sought
    sep #$20
.a8
    jsr queue_by_action
    ora f:cell_queued
    sta f:cell_queued
    rep #$20
.a16
    rts
.endproc

; `npc_ptr` at the map's positions and Y past its rows, at the word with how
; many twins it has, which it leaves in A with Z. In and out in sixteen bits;
; clobbers X.
;
; A twin is an event the converter left without a row because its map has
; more than `EV_MAX` and its pages are the same as another's: invisible and
; still, so the only things it does are fire those pages from its own cell
; and, on the hero's layer, stop him —see `hero_blocked_rest`—. Its cell lives in ROM, behind the map's
; positions —a word with how many, then TWIN_STRIDE bytes each: x, y and
; the event whose row it shares—; see `ev_pos_bytes` in `rm2k-snes-mapdata`.
; It is looked at only after the rows, and a map whose events fit has none:
; its word is 0.
;
; `npc_ptr` is borrowed: it only lives while the load copies a table.
.proc twin_table
.a16
.i16
    ldx map_ofs
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
    rts
.endproc

; The first twin on (cell_x, cell_y), if there is one: the index of the event
; whose row it shares in A, or $FF. For the step into it, which only asks
; whether it blocks: see `twin_at_dest`.
.proc twin_in_cell
.a8
.i16
    rep #$20
.a16
    jsr twin_table
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
    ; The event first, from +0, and the page only if it is the one: reading
    ; every page of the map whole cost more than a frame on a map of four
    ; hundred pages, each time A was pressed. Not stopping past it: the test
    ; cartridges' pages of event 0 go at the end of the table.
    rep #$20
.a16
    ldy page_ofs
    lda [page_ptr], y
    cmp ev_sought
    sep #$20
.a8
    bne next                    ; not the event we are looking at
    jsr read_page_head
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
; An event that fires twice before running runs once, as in RM2k: the queue
; is one bit per event, see `mark_waiting`.
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
    ; come the action pages.
    ;
    ; **All three are looked at, whatever the one before queued**: RPG_RT ORs
    ; them. Until 2026-11-02 each stopped at the first one it queued, and the
    ; first rock of Zounds, on map 33, could not be mined from above: its top
    ; half, events 17 and 18, is an action event with an empty page above the
    ; hero, so standing on it queued that page and the bottom half in front,
    ; on the hero's layer and with the mining page, was never looked at. See
    ; `test_zounds_action_from_above.py` in the ports.
    ;
    ; Marking several is safe: it is one bit per event —`mark_waiting`—, and
    ; `start_waiting` runs them one after the other by event number, which is
    ; `Game_Map::Update`'s order and not this one. The order here only
    ; decides whose turn toward the hero survives, since there is one at a
    ; time: the last one marked —see `turn_toward_hero.s`—.
    jsr try_bump
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
    stz own_action
    jsr front_cell
    jsr action_in_cell
    ; Whether any of the three queued: the caller only presses here with
    ; nobody waiting —it looked at `waiting_n` first, in `events_tick`—, so
    ; the count says it, without keeping three answers.
    lda waiting_n
    rts
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
    ; and it is the way he last tried to go. See `hero_heading`. After a
    ; diagonal step of a move route they part too, and `XwithDirection` moves
    ; nothing with a diagonal: he looks at his own cell. See `try_diagonal`.
    lda hero_heading
    cmp #4
    bcs look
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

