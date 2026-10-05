.segment "CODE"

; --- the hero ---------------------------------------------------------------
; RM2k does not move the character freely: it commits to a neighboring cell
; and covers the 16 pixels to it without being able to stop. That is why the
; state is the cell it is on plus how many pixels are left of the step in
; progress, and while there are any left no other direction is accepted.
;
; The four passability bits are: down $01, left $02, right $04, up $08.
; Crossing from one cell to the next asks both for permission: the source
; has to allow leaving on that side and the destination has to allow
; entering on the opposite one. Everything else —that the upper layer rules
; unless it is decoration, that wall faces can always be crossed— the
; converter already resolved.

PASS_DOWN  = $01
PASS_LEFT  = $02
PASS_RIGHT = $04
PASS_UP    = $08

.proc move_hero
.a8
.i16
    ; If there is a step in progress, it is finished: it cannot stop halfway
    ; through a cell.
    lda step_left
    beq still
    jsr advance_step
    rts

still:
    stz moving
    ; With no step in progress there is no move route step to record. It is
    ; cleared here and not when the route ends because what matters is the
    ; step, not the route.
    stz route_step
    ; A jump in the air takes the whole frame, and it is checked **before**
    ; the move command counter: in RM2k jumping is not standing still
    ; —`IsStopping()` is `!(IsMoving() || IsJumping())`— so `Update` brings
    ; the jump down without going through `UpdateNextMovementAction`. With
    ; this inside `step_route`, which is only called with
    ; `route_i < route_n`, a jump that was the route's last command was brought
    ; down by nobody. See `jump_advance_hero`.
    lda route_jump
    beq no_jump
    jsr jump_advance_hero
    rts
no_jump:
    ; A forced move route rules over the pad: while any of it is left, the
    ; player does not move the hero. It is what RM2k does, and it is what
    ; lets a cutscene walk him on its own.
    ;
    ; A pending `wait` is also route, even when no commands are left: a route
    ; that **ends** in `wait` —there are 21 in the game, the first on map 1—
    ; leaves `route_i` equal to `route_n` with `route_wait` loaded, and without
    ; this nobody brought it down: `step_route` is the only one that counts
    ; it down. In RM2k the `wait` is one more command and the route still
    ; belongs to the hero until it is done. It stayed stuck forever, and
    ; `any_routes` and the action button, which look at it, answered "there is
    ; a route" until the next one.
    lda route_wait
    bne with_route
    lda route_i
    cmp route_n
    bcs no_route
with_route:
    jsr step_route
    rts
no_route:
    ; The menu request, in the order of `UpdateNextMovementAction`: with a
    ; page running it is thrown away; with a message open it waits; and
    ; otherwise the menu opens and the hero does not walk this frame. It goes
    ; before looking at `waiting_n` because RM2k looks at
    ; `IsAnyEventStarting` afterwards.
    lda ev_active
    beq menu_no_page
    jsr menu_forget
    rts
menu_no_page:
    lda msg_open
    bne no_right
    ; The encounter left pending is collected here: with no page running, no
    ; message open and no forced move route, which is the order of
    ; `Game_Player::UpdateNextMovementAction` —the encounter goes **before**
    ; the menu request—. `encounter_test` leaves the troop in `BA_TROOP`.
    jsl f:encounter_test
    cmp #0                      ; the `plx` over there left its own flags
    beq no_encounter
    ; And losing it is Game Over, just like a page battle with no defeat
    ; handler: a random encounter **never** brings them, because there is no
    ; page to emit them. Without this, defeat handed control back to the map
    ; with the whole party at zero HP, and from then on every battle was lost
    ; by itself before opening —`battle_run` answers defeat with nobody
    ; standing—. `battle_start` collects it: see
    ; tools/runtime/game_over.s.
    jsl f:game_over_always
    jmp battle_start
no_encounter:
    jsr access_read
    bpl menu_no_requested       ; bit 7 is the request
    and #$7F
    jsr access_write
    jsr menu_screen
    rts
menu_no_requested:
    ; And a message on screen rules over the pad, just like the forced move
    ; route. It is what easyrpg's `Game_Player::UpdateNextMovementAction`
    ; does, returning without looking at the input if
    ; `Game_Message::IsMessageActive()`. It goes down here and not at the very
    ; top on purpose: the forced move route **does** walk with the message
    ; open —`UpdateMoveRoute` runs before the guard— and a step already begun
    ; is finished, because in RM2k you do not stop halfway through a cell.
    lda msg_open
    bne no_right
    ; And a page running also rules over the pad. It is the
    ; `if (Game_Map::IsAnyEventStarting()) return;` of
    ; `Game_Player::UpdateNextMovementAction`: while the interpreter has
    ; something in the foreground, the player does not walk.
    ;
    ; Without this, a touch event fired and the hero took **one more step**
    ; while the message was being composed: the message takes a few frames to
    ; open and `msg_open` only gets set at the end.
    lda ev_active
    bne no_right
    lda waiting_n
    bne no_right
    ; And an automatic common event about to start: the other half of
    ; `IsAnyEventStarting`.
    jsl f:common_waiting + FAST
    bne no_right
    lda pad
    and #PAD_UP
    beq no_up
    lda #DIR_UP
    bra walk
no_up:
    lda pad
    and #PAD_DOWN
    beq no_down
    lda #DIR_DOWN
    bra walk
no_down:
    lda pad
    and #PAD_LEFT
    beq no_left
    lda #DIR_LEFT
    bra walk
no_left:
    lda pad
    and #PAD_RIGHT
    beq no_right
    lda #DIR_RIGHT
walk:
    jsr try_toward
after_step:
    ; A step that really started —`step_left` says so— is an RM2k step:
    ; `IncSteps` and `UpdateEncounterSteps`, which there run after `Move()`
    ; and only if the hero moved. It goes in the pad branch and not inside
    ; `advance_step` because **the steps of a forced move route do not
    ; count**: there it returns earlier, through `IsMoveRouteOverwritten`.
    lda step_left
    beq no_right
    jsl f:encounter_step
no_right:
    rts
.endproc

; A step of the hero toward direction A, from the pad or from a route. It is
; `Game_Character::Move`: `SetDirection` and then `UpdateFacing`, which with
; `lock_facing` leaves alone the `facing` —what is drawn—. Here there is only
; `hero_dir` for both while it walks, and `can_enter` reads the step's
; direction from it, so it takes A for the attempt and gets back the one it
; had if `hero_lock` is on. What RM2k's `direction` keeps after that, for the
; action key, goes to `hero_heading`.
;
; Anything that is not up, right or down goes left, by elimination: it is
; why diagonals do not reach the hero —see `step_route`—.
.proc try_toward
.a8
.i16
    xba                         ; the direction waits in B
    lda hero_dir
    pha                         ; the facing it had
    xba
    sta hero_dir
    sta hero_heading
    cmp #DIR_UP
    bne not_up
    jsr try_up
    bra tried
not_up:
    cmp #DIR_RIGHT
    bne not_right
    jsr try_right
    bra tried
not_right:
    cmp #DIR_DOWN
    bne not_down
    jsr try_down
    bra tried
not_down:
    jsr try_left
tried:
    lda hero_lock
    beq free
    pla
    sta hero_dir
    rts
free:
    pla
    rts
.endproc

; Each attempt checks the map's edge, then the two permissions, and only
; then starts the step.
; All four work with the 16-bit accumulator: the hero's cell no longer fits
; in a byte —there are maps 500 cells wide— and the permissions are looked
; up with 16-bit indexes.
.proc try_up
.a8
.i16
    rep #$20
.a16
    lda tile_y
    beq no                      ; already on the top row
    lda #PASS_UP
    jsr can_leave
    beq no
    jsr ptr_from_hero
    lda strip_step_col
    jsr ptr_minus               ; the destination: one row of blocks up
    lda #PASS_DOWN              ; and that cell has to allow entering
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    dec a
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked            ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    dec tile_y
    lda #0
    sta step_dx
    lda #$FFFF              ; -1: ca65 does not accept a negative immediate
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_down
.a8
.i16
    rep #$20
.a16
    lda tile_y
    inc a
    cmp map_height
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    jsr ptr_from_hero
    lda strip_step_col
    jsr ptr_more                ; one row of blocks down
    lda #PASS_UP
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    inc a
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked            ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    inc tile_y
    lda #0
    sta step_dx
    lda #1
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_left
.a8
.i16
    rep #$20
.a16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    jsr ptr_from_hero
    lda #2
    jsr ptr_minus               ; the cell next to it
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    lda tile_x
    dec a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked            ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    dec tile_x
    lda #$FFFF              ; -1: ca65 does not accept a negative immediate
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_right
.a8
.i16
    rep #$20
.a16
    lda tile_x
    inc a
    cmp map_width
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    jsr ptr_from_hero
    lda #2
    jsr ptr_more
    lda #PASS_LEFT
    jsr can_enter
    beq no
    lda tile_x
    inc a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked            ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    inc tile_x
    lda #1
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

; --- passability ------------------------------------------------------------
; There is no longer a table with one byte per cell: the permissions travel in
; the block. It is two hops —the cell says which block it is, the block says
; which permissions it has— and in exchange the biggest map saves twenty
; kilobytes. That two cells drawn the same but with different permissions are
; not confused is guaranteed by the converter, which puts passability in the
; block's key.
;
; Where the hero is inside the grid is not an index either: it is a pointer
; that moves with him, one cell or one row per step. That way there is never
; a need to multiply or recompute a 24-bit address from scratch, which in
; LoROM is awkward because the banks are not contiguous.

; A = the bit that is needed. Returns with Z clear if the cell has it.
.proc can_leave
.a16
.i16
    sta temp
    lda tile_x                  ; the cell being left, for whatever a tile
    sta pass_x                  ; event imposes on it
    lda tile_y
    sta pass_y
    jsr ptr_from_hero
    jsr pass_of_ptr
    jsr pass_with_event
    and temp
    ora crossing                ; with walk_everywhere the answer is yes
    rts
.endproc

; The same, but on the cell cells_ptr was left pointing at: each direction
; moves it on its own before calling, and if the step is accepted
; begin_step copies it to hero_ptr. That way the destination is computed only
; once.
.proc can_enter
.a16
.i16
    sta temp
    ; The destination cell: the hero's plus the step in `hero_dir`, which is
    ; always the step's direction, also in a forced move route.
    lda tile_x
    sta pass_x
    lda tile_y
    sta pass_y
    sep #$20
.a8
    lda hero_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:step_dx_table, x
    jsr add_a_to_pass_x
    lda f:step_dy_table, x
    jsr add_a_to_pass_y
    rep #$20
.a16
    jsr pass_of_ptr
    jsr pass_with_event
    and temp
    ora crossing
    rts
.endproc

; The passage bits of cell `pass_x`/`pass_y`: the ones A brings —the
; terrain's, from `pass_of_ptr`— unless a tile event on the lower layer
; imposes its own. It is `Game_Map::IsPassableTile`: of the events standing
; there with an active page and a tile graphic on that layer the one with the
; highest id wins, and if its tile is not one that goes above, it rules. The
; refresh left the bits in the NPC's row, +15, or $FF if it imposes nothing;
; so this is one walk of the NPC table per step and not a pass over the
; pages. What is not modeled: the "conflict with itself" of a tile event that
; walks, because none walks. It enters and leaves in sixteen bits.
.proc pass_with_event
.a16
.i16
    ; From the last row backwards and in sixteen bits: the last one that
    ; imposes wins, so the first one found that way is the answer. It runs
    ; twice for every step that starts, and front to back with a `rep`/`sep`
    ; per row it was nine lines each time in the race, with forty cars: see
    ; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    sta temp + 2
    lda pass_has
    and #$00FF
    beq none                    ; no row on this map imposes anything
    ldy npc_total
    bra next
other:
    lda npc_buf + 14, y         ; whether it is there, and above that what it imposes
    cmp #$FF00
    bcs next                    ; $FF: imposes nothing
    bit #$00FF
    beq next                    ; hidden: not there
    lda npc_buf + 8, y          ; its event, and with it its cell
    and #$00FF
    asl a
    asl a                       ; times EV_STRIDE
.assert EV_STRIDE = 4, error, "the arithmetic above multiplies by four by hand"
    tax
    lda ev_pos_buf, x
    cmp pass_x
    bne next
    lda ev_pos_buf + 2, x
    cmp pass_y
    bne next
    lda npc_buf + 14, y
    xba
    and #$00FF                  ; the passage bits it imposes
    rts
next:
    tya
    sec
    sbc #NPC_STRIDE
    tay
    bpl other
none:
    lda temp + 2                ; none: the terrain's
    rts
.endproc

.proc add_a_to_pass_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positive
    ora #$FF00
positive:
    clc
    adc pass_x
    sta pass_x
    sep #$20
.a8
    rts
.endproc
.proc add_a_to_pass_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positive
    ora #$FF00
positive:
    clc
    adc pass_y
    sta pass_y
    sep #$20
.a8
    rts
.endproc

.proc pass_of_ptr
.a16
.i16
    lda [cells_ptr]             ; which block this cell is
    jsr cell_replaced
    tay
    sep #$20
.a8
    lda [pass_ptr], y
    rep #$20
.a16
    and #$00FF
    rts
.endproc

.proc ptr_from_hero
.a16
.i16
    lda hero_ptr
    sta cells_ptr
    sep #$20
.a8
    lda hero_ptr + 2
    sta cells_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_hero
.a16
.i16
    lda cells_ptr
    sta hero_ptr
    sep #$20
.a8
    lda cells_ptr + 2
    sta hero_ptr + 2
    rep #$20
.a16
    rts
.endproc

; The pointer to cell (cell_x, cell_y) of the grid.
;
; It is separate from `init_hero_ptr` because now more than one thing walks:
; the events' forced move routes query cells that are not the hero's, and
; having the arithmetic written twice is how they drift apart.
;
; The offset is `cell_y * strip_step_col + cell_x * 2`, with the CPU's
; multiplier —eight by eight bits, so in three products: the one of the two
; low bytes and the two cross ones, which land shifted by a byte; the one of
; the two high bytes falls outside the sixteen— and not by adding one row for
; every row down, which is what it did until 2026-09-27: on row 26 that was
; four lines per step of every walking event, and in the race five steps
; start in the same frame. No interrupt uses the multiplier: see the fade in
; `irq_music`.
;
; The grid fits in 64 KB and lives in the upper half of the two banks —see
; `ptr_more`—, so the offset fits in sixteen bits and its bit 15 tells the
; bank: without it, the upper half of $7E (the bit gets set), and with it
; that of $7F (it already has it).
.proc cell_ptr
.a8
.i16
    lda cell_y
    sta WRMPYA
    lda strip_step_col
    sta WRMPYB                  ; eight cycles: what follows pays for them
    rep #$20
.a16
    lda cell_x
    asl a                       ; each cell takes two bytes
    sta cells_ptr
    lda RDMPYL                  ; y low times stride low
    clc
    adc cells_ptr
    sta cells_ptr
    sep #$20
.a8
    lda strip_step_col + 1
    beq no_step_height
    sta WRMPYB                  ; y low times stride high: WRMPYA is still y
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc cells_ptr + 1
    sta cells_ptr + 1
no_step_height:
    lda cell_y + 1
    beq no_y_high
    sta WRMPYA
    lda strip_step_col
    sta WRMPYB                  ; y high times stride low
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc cells_ptr + 1
    sta cells_ptr + 1
no_y_high:
    lda cells_ptr + 1
    bmi high
    ora #>$8000
    sta cells_ptr + 1
    lda #^GRID
    sta cells_ptr + 2
    rts
high:
    lda #^GRID_HIGH
    sta cells_ptr + 2
    rts
.endproc
.assert .loword(GRID) = $8000 && .loword(GRID_HIGH) = $8000 && ^GRID_HIGH = ^GRID + 1, error, "cell_ptr builds the pointer with the grid in the two upper halves"

; Where the hero starts inside the grid.
.proc init_hero_ptr
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
    jsr cell_ptr
    rep #$20
.a16
    jsr ptr_a_hero
    sep #$20
.a8
    rts
.endproc

; Starts the step: a whole cell to cover —128 half units, see
; `half_step_per_speed`— and the index already on the new cell, which is how
; RM2k keeps count.
.proc begin_step
.a8
.i16
    lda #128
    sta step_left
    rep #$20
.a16
    jsr ptr_a_hero              ; RM2k counts from the destination cell, which is
    sep #$20                    ; where can_enter left the pointer pointing
.a8
    jsr advance_step
    rts
.endproc

; Advances this frame's pixels and, if that completes the step, leaves the
; character exactly on the cell.
.proc advance_step
.a8
.i16
    lda #$01
    sta moving
    ; What is left of the step goes down by whatever the speed says, and the
    ; pixels are **recomputed** from the destination cell and not
    ; accumulated: with half a pixel per frame there is nothing whole to add.
    ; `step_dx` and `step_dy` are the step's direction, -1, 0 or 1.
    jsr hero_anim_frames        ; incidentally leaves X at the speed minus one
    lda step_left
    sec
    sbc half_step_per_speed, x
    bcs no_negative
    lda #0
no_negative:
    sta step_left
    lsr a
    lsr a
    lsr a                       ; the pixels left
    rep #$20
.a16
    and #$00FF
    sta temp                    ; nobody holds it during a step
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    ldx step_dx
    beq x_ready
    bmi x_from_right
    sec
    sbc temp
    bra x_ready
x_from_right:
    clc
    adc temp
x_ready:
    sta hero_x
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    ldx step_dy
    beq y_ready
    bmi y_from_down
    sec
    sbc temp
    bra y_ready
y_from_down:
    clc
    adc temp
y_ready:
    sta hero_y
    sep #$20
.a8
    lda step_left
    bne continues               ; the step has not finished yet
    ; While the hero has forced move route left, nothing is stepped on:
    ; neither door nor touch event. It is the `!IsMoveRouteOverwritten()` of
    ; `Game_Player::UpdateMovement`, and the last step does count because in
    ; `Game_Character::UpdateMovement` a movement that is the last command
    ; cancels the whole route **before** the check —it is commented there:
    ; "If the last command of a move route is a move or jump, RPG_RT cancels
    ; the entire move route immediately"—. With `route_i` already past the
    ; last command, the route is cancelled; with commands left to read, it is
    ; not. It is what lets the opening cutscene step on the event that turns
    ; the tint off: it is three cells up and the event is on the third.
    lda route_i
    cmp route_n
    bcs no_route                ; no commands left: door and touch
    ; Some are left: the step is a middle one, and the frequency says how
    ; many frames to stand still before reading the next. It holds even if
    ; the pad started the step: in RM2k `UpdateMovement` sets the counter to
    ; zero when any step ends, and `ForceMoveRoute` already set the route's
    ; limit.
    lda route_freq
    jsr after_step
    sta route_wait
    bra continues
no_route:
    ; Just stopped on the cell: is there a touch event? A door is one of
    ; those —a touch page whose only command is the `Teleport`— so it has no
    ; path of its own: it goes through the interpreter, like any other
    ; teleport.
    jsr try_touch
continues:
    rts
.endproc

; --- walk animation ---------------------------------------------------------
; The cycle is four steps over three CharSet frames: 0, 1, 2, 1. The middle
; one is the standing pose, and it is the one it goes back to when the d-pad
; is released.
.proc animate_hero
.a8
.i16
    ; With the animation paused by a move route the pose stays on the middle
    ; one, walking or not: RM2k calls `ResetAnimation` on every frame while
    ; `IsAnimPaused()`, which leaves the middle frame and the counter at
    ; zero.
    lda route_anim_for
    bne still
    lda moving
    bne walking
still:
    lda #1                      ; standing: the middle frame
    sta anim_step
    stz anim_timer
    rts

walking:
    ; The count goes up and is compared with the limit **for the current
    ; speed**, like `GetAnimCount() >= stationary_limit`: if a move route
    ; changes the speed halfway through a frame, the next frame already comes
    ; out with the new one. Counting down from the limit, as before, the new
    ; one only took effect one frame later: one frame off from RM2k.
    inc anim_timer
    jsr hero_anim_frames
    cmp anim_timer
    beq changes
    bcs ready                   ; the count has not reached the limit yet
changes:
    stz anim_timer
    lda anim_step
    inc a
    and #$03                    ; the cycle is four steps
    sta anim_step
ready:
    rts
.endproc

