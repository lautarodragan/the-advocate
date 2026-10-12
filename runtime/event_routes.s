.segment "CODE"

; --- the events' forced move routes -----------------------------------------
;
; An event with a forced move route walks like the hero: turning does not use up
; a frame, waiting does, and moving starts a one-cell step that lasts
; FRAMES_PER_CELL. The difference with the hero is that its position lives in
; cells and not in pixels, and that —for now— it is not drawn: the move routes
; that compile are on events without a graphic. The only visible thing about
; them is how long they take, which is what `ProceedWithMovement` waits for.

; Gives a move route to event `route_target - 1`: looks for its slot, and if it
; does not have one it takes a free one. Overwriting the one it already had is
; correct —RM2k overwrites the previous forced move route, it does not chain
; it— and if there is no free one the move route is dropped, which is preferable
; to writing next to the table.
;
; What is kept when overwriting it is what `ForceMoveRoute` keeps: the step or
; jump in progress finish, the facing stays, and going through walls and the
; stopped animation remain as they were. The wait —the first command runs right
; away— and the commands are cut. Before, the whole slot was reset, and the
; event went back to facing wherever its page said until the new move route
; turned it: it was the sentinel that left `face_hero` out.
;
; Enters with Y pointing to the first command inside the bytecode.
.proc route_for_event
.a8
.i16
    phy
    lda route_target
    dec a
    jsr turn_per_route          ; with a move route, the move route decides where it faces
    ply
    lda route_target
    dec a
    sta temp                    ; the event's index

    ; First the slot that is already its own, and if not a free one. The two
    ; searches were copied here and are exactly `event_slot` and
    ; `free_slot`: calling them saves bank 0 and, the first one, brings along
    ; the `route_ev_cap` cap as a bonus.
    lda temp
    jsr event_slot
    cpx #$FFFF
    bne reused
    jsr free_slot
    cpx #$FFFF
    bne set2
    rts                         ; no room: the move route is lost

set2:
    lda temp
    sta route_ev + 0, x
    jsl f:slot_record + FAST
    stz route_ev + 6, x
    stz route_ev + 7, x         ; no step in progress
    stz route_ev + 22, x
    stz route_ev + 23, x
    lda #ROUTE_EV_NO_FACE
    sta route_ev + 8, x         ; faces wherever its page says until it turns
    stz route_ev + 12, x        ; no flags
    stz route_ev + 13, x        ; nor jump
    lda #1
    sta route_ev + 10, x        ; the middle frame, like `animate_hero`
    stz route_ev + 11, x
    stz route_ev + 18, x
    stz route_ev + 27, x        ; no page to go back to
    rep #$20
.a16
    lda #$FFFF
    sta route_ev + 20, x
    sep #$20
.a8
    ; At the speed of the page it is drawn with, which the NPC row carries at +13:
    ; it is the one RM2k leaves to a forced move route. An event without a row
    ; —without a graphic— goes at 3, a default page's.
    phy                         ; Y is the bytecode cursor, and it is needed
    lda temp                    ; afterwards: `event_npc` overwrites it
    jsr event_npc               ; Y = its row, or $FFFF; A is lost
    cpy #$FFFF
    beq no_row
    lda npc_buf + 13, y
    bra with_speed
no_row:
    lda #3
with_speed:
    ply
    sta route_ev + 17, x
    lda temp
    jsr active_layer            ; its layer, once and not on every step
    sta route_ev + 31, x
    ; And whether its page always faces the same way —the animation types
    ; 2, 3 and 4—, which is the `lock_facing` that `SetAnimationType` leaves
    ; and a forced move route does not touch. Until 2026-09-30 only a page's
    ; own route brought it, and the slot of an event without one was born
    ; turning: the trams of maps 9 and 28, whose CharSet rows are other
    ; vehicles. A reused slot already has it, or the 26 that replaced it.
    lda found_flags
    and #$08
    sta route_ev + 18, x
    ; And whether its page's graphic is fixed —`AnimType_fixed_graphic`—,
    ; which keeps the page's column instead of the middle one: ABL's
    ; missile silos, on map 92, open by turning, and their middle column is
    ; a soldier.
    lda f:FOUND_SPEED
    jsr fixed_graphic_into_slot
reused:
    lda route_ev + 18, x
    and #$FE                    ; the forced one overrides the page's, if there was one
    ora #$04                    ; and what is blocked is skipped
    sta route_ev + 18, x
    ; The pointer to the first command: the code's plus however far Y had gone.
    ; The sum does not carry anything into the bank byte because the map's code
    ; block fits whole in one —the converter's bank layout guarantees it,
    ; `tools/ensamblado/banks.py`—, which is the same argument as for the message block.
    rep #$20
.a16
    tya
    clc
    adc code_ptr
    sta route_ev + 1, x
    sep #$20
.a8
    lda code_ptr + 2
    sta route_ev + 3, x
    lda route_count
    sta route_ev + 4, x
    stz route_ev + 5, x         ; just starting
    stz route_ev + 9, x         ; and no wait in progress: the first command runs right away
    lda route_freq_op
    sta route_ev + 16, x
    rts
.endproc

; How many frames a character stands still after a step and after a turn with
; the frequency A carries. It is RM2k's stop counter —`SetMaxStopCountForStep`
; and `ForTurn`— and with 8 both give zero, which is why "turning is free and
; the steps go back to back" was exact without knowing it. The converter emits
; the tables from `events.wait_after_step` and `wait_after_turn`. They use Y
; and not X, because X is the slot of whoever asks.
.proc after_step
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda route_after_step, y
    rts
.endproc

.proc after_turn
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda route_after_turn, y
    rts
.endproc

; Which way whoever is at (cell_x, cell_y) faces to face the hero. It is
; `GetDirectionToCharacter`: the axis with more distance wins and on a tie the
; vertical; on the same cell, or with the hero further down, it faces down.
; Returns the direction in A.
.proc toward_hero
.a8
.i16
    rep #$20
.a16
    lda cell_x
    sec
    sbc tile_x
    sta temp                    ; sx, signed: positive is "the hero is to the left"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_a                   ; |sx|
    lda cell_y
    sec
    sbc tile_y
    sta temp + 2                ; sy: positive is "the hero is further up"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_b                   ; |sy|
    lda cmp_a
    cmp cmp_b
    beq vertical
    bcc vertical                ; |sx| <= |sy|: the vertical axis wins
    sep #$20
.a8
    lda temp + 1                ; the sign of sx
    bmi right
    lda #DIR_LEFT
    rts
right:
    lda #DIR_RIGHT
    rts
vertical:
.a16
    sep #$20
.a8
    lda temp + 3                ; the sign of sy
    bmi down
    lda temp + 2
    ora temp + 3
    beq down                    ; the same cell: down
    lda #DIR_UP
    rts
down:
    lda #DIR_DOWN
    rts
.endproc

; A random direction, 0 to 3, for `move_random`. Two bits of the high byte of
; the map's xorshift, which mix better than the low ones. `random_next` keeps X,
; which is the slot, and uses `temp + 2`.
.proc random_direction
.a8
.i16
    jsr random_next             ; A is sixteen bits
.a16
    xba
    sep #$20
.a8
    and #$03
    rts
.endproc

; One frame of all the event move routes that are running.
.proc move_events
.a8
.i16
    stz routes_moved
    ldx #$0000
other:
    lda route_ev, x
    cmp #ROUTE_EV_FREE
    beq next
    ; The one that already took its step tied to its parallel interpreter does not
    ; take it again: the mark is consumed here, so it lasts one frame. See
    ; `one_parallel`.
    lda route_ev + 18, x
    and #$40
    beq no_moved
    lda route_ev + 18, x
    and #$BF
    sta route_ev + 18, x
    bra next
no_moved:
    phx
    jsr ev_route_frame
    plx
    phx
    jsr animate_ev_route
    plx
    phx
    jsr refresh_npc
    plx
    lda #1
    sta routes_moved
next:
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #ROUTE_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc other
    ; From here on the one that moves is the hero again.
    lda #HERO_WALKER
    sta walker
    lda #HERO_LAYER_INDEX
    sta walker_layer
    rts
.endproc

; One frame of the move route of the slot X points to. It is the same program as
; `step_route` for the hero, and that is why both do the same with the same
; commands: if it were counted differently here, an event's move route would end
; on a different frame than the hero's and `ProceedWithMovement` would let the
; page go when it should not.
; The jumps in here go with `jmp` and not `bra`, for the same reason as in
; `step_route`: the body grew and the 127 bytes of reach fell short.
.proc ev_route_frame
.a8
.i16
    stz route_ev + 6, x
    lda route_ev + 18, x
    and #$DF                    ; `repeat`'s reload, one per frame
    sta route_ev + 18, x
    lda route_ev + 7, x
    beq no_step
    ; The step advances by what the speed says, out of 256 per cell; +7 only says
    ; there is one in progress.
    jsr step_slot
    rep #$20
.a16
    lda route_ev + 22, x
    sec
    sbc temp
    bcs no_negative
    lda #0
no_negative:
    sta route_ev + 22, x
    sep #$20
.a8
    bne still_moving
    stz route_ev + 7, x         ; the step ended on this frame
    lda route_ev + 5, x
    cmp route_ev + 4, x
    bcc with_commands
    lda route_ev + 18, x        ; no commands: only the repeating page one
    and #$03                    ; keeps waiting
    cmp #$03
    bne still_moving
with_commands:
    lda route_ev + 16, x
    jsr after_step
    sta route_ev + 9, x
still_moving:
    lda #1
    sta route_ev + 6, x
    rts
no_step:
    lda route_ev + 13, x
    beq no_jump
    jsr slot_jump
    sta temp
    lda route_ev + 13, x
    sec
    sbc temp
    bcs save_jump
    lda #0
save_jump:
    sta route_ev + 13, x
    rts
no_jump:
    ; And a `wait` in progress takes the whole frame, same as the hero's.
    lda route_ev + 9, x
    beq no_wait
    dec a
    sta route_ev + 9, x
    rts
no_wait:
    ; The page's own move route does not read new commands while the interpreter
    ; has a page running: it is `UpdateNextMovementAction`'s `IsRunning()`. The
    ; step in progress already finished above and the waits keep counting.
    ; Unless a `MessageOptions` asked for the events to go on moving: it is the
    ; `!GetMessageContinueEvents() &&` in front of that `IsRunning()`.
    lda route_ev + 18, x
    and #$01
    beq no_frozen
    lda f:FAR_LENGTH + FAR_MSG_OPTIONS
    and #MSG_CONTINUE
    bne no_frozen
    lda ev_active
    bne frozen
    lda waiting_n
    bne frozen
no_frozen:
    ; The move route's pointer to the direct page, which is where it can be read
    ; from with `[ptr], y`.
    rep #$20
.a16
    lda route_ev + 1, x
    sta route_ptr
    sep #$20
.a8
    lda route_ev + 3, x
    sta route_ptr + 2

other_command:
    lda route_ev + 5, x         ; which one it is on
    cmp route_ev + 4, x         ; how many it has
    bcc has_command
    ; The commands ran out. The repeating page one goes back to the start on the
    ; same frame, and only once per frame —`UpdateMoveRoute`'s `current_index ==
    ; start_index`—; and a forced one that ends on an event with its own move route
    ; gives it back its own, from the start.
    lda route_ev + 18, x
    and #$23
    cmp #$03
    bne no_repeats
    stz route_ev + 5, x
    lda route_ev + 18, x
    ora #$20
    sta route_ev + 18, x
    jmp other_command
no_repeats:
    lda route_ev + 18, x
    and #$01
    bne frozen                  ; the page one, finished: done
    lda route_ev + 27, x
    beq frozen                  ; no page to go back to
    jsr resume_page
frozen:
    jmp ready
has_command:
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [route_ptr], y
    inc route_ev + 5, x

    cmp #23                     ; wait: this one and the ROUTE_WAIT - 1 after it,
    bne not_wait                ; plus the turn's if the frequency is low
    lda route_ev + 16, x
    jsr after_turn
    clc
    adc #(ROUTE_WAIT - 1)
    sta route_ev + 9, x
    jmp ready
not_wait:
    cmp #12
    bcs no_moves
    cmp #8
    bne not_random
    ; `move_random`: `TurnRandom` and then `Move(GetDirection())`. The direction
    ; is two bits of the map's xorshift —the one `ControlVars` draws from—, not
    ; RM2k's own generator, so a random walk is random but not the same walk.
    jsr random_direction
    jmp move
not_random:
    cmp #9
    bne not_toward
    ; `move_towards_hero`. It is not a separate command but the two already there
    ; put together: `UpdateMoveRoute` does `TurnTowardCharacter(hero)` and then
    ; `Move(GetDirection())`, that is, 21 and a `move_*` on the same frame. That
    ; is why the direction comes from here and it falls into `move` without
    ; touching anything else: the turn, the step and what it costs are the usual.
    ; `toward_hero` does not overwrite X, which is the slot.
    jsr event_cell
    jsr toward_hero
    jmp move
not_toward:
    cmp #10
    bne to_move                 ; 0..3 the move_*, 4..7 the diagonals
    ; `move_away_from_hero`: `GetDirectionAwayCharacter`, which is
    ; `GetDirectionToCharacter` turned half a circle in every case, ties and the
    ; same cell included: the vertical wins a tie, and with the hero on the
    ; same row it goes up where toward would go down.
    jsr event_cell
    jsr toward_hero
    clc
    adc #2
    and #$03
to_move:
    jmp move
no_moves:
    cmp #16
    bcs :+
    jmp face                    ; 12..15 are the face_*; it is far
:
    cmp #21
    bne no_faces
    ; face_hero: the event's cell against the hero's, and on to `look` with the
    ; direction in A.
    jsr event_cell
    jsr toward_hero
    jmp look
no_faces:
    cmp #22
    bne no_face_away
    ; face_away_from_hero: `toward_hero` half a circle around, as `move_away`.
    jsr event_cell
    jsr toward_hero
    clc
    adc #2
    and #$03
    jmp look
no_face_away:
    ; The other turns —90 and 180 degrees, the random ones— are not compiled:
    ; they do not get here.
    cmp #24
    bne not_jump
    jsr prepare_walker          ; who jumps, to collide with the others
    lda route_ev + 5, x
    dec a
    sta jump_command            ; where the 24 is, in case it has to go back
    jsr build_ev_jump
    lda route_ev + 13, x
    bne jump_started
    ; It could not land there. With the move route skippable the jump is skipped;
    ; without that RM2k moves the cursor back to the `begin_jump` and cuts the frame
    ; —`current_index = saved_index`—, and the jump is retried frame by frame until
    ; the cell frees up. Without `end_jump` there is nothing to go back to: it is
    ; always skipped.
    lda jump_stuck
    beq skip
    lda route_ev + 18, x
    and #$04
    bne skip
    lda jump_command
    sta route_ev + 5, x
    jmp ready
skip:
    jmp other_command
jump_started:
    jmp ready
not_jump:
    cmp #25
    beq follow
    cmp #26
    bcc follow                  ; the others do nothing
    cmp #32
    bcc fix_or_speed            ; 26 and 27 the facing, 28 and 29 the speed,
    cmp #34                     ; 30 and 31 the frequency
    bne not_graphic             ; and 34 the graphic, which carries an operand
    jmp change_graphic          ; it is too far for a short branch
not_graphic:
    cmp #35
    bne not_sound
    jmp sound_ev                ; 35, with its operand
not_sound:
    cmp #36
    bcc follow                  ; 32 and 33, the switches, do not get here
    cmp #38
    bcs anim
    ; 36 turns going through walls on and 37 turns it off.
    and #$01
    eor #$01
    beq off_crosses
    lda route_ev + 12, x
    ora #$01
    bra save_flags
off_crosses:
    lda route_ev + 12, x
    and #$FE
    bra save_flags
anim:
    cmp #40
    bcs follow
    ; 38 stops the animation and 39 resumes it.
    cmp #38
    bne follow_anim
    lda route_ev + 12, x
    ora #$02
    bra save_flags
follow_anim:
    lda route_ev + 12, x
    and #$FD
save_flags:
    sta route_ev + 12, x
follow:
    jmp other_command
fix_or_speed:
    cmp #30
    bcs ev_frequency
    cmp #28
    bcs speed
    ; 26 locks the facing, 27 releases it: `lock_facing`.
    and #$01
    beq fix
    lda route_ev + 18, x
    and #$F7
    bra save_18
fix:
    lda route_ev + 18, x
    ora #$08
    bra save_18
speed:
    ; 28 raises the speed and 29 lowers it, between 1 and 6.
    and #$01
    bne more_slow
    lda route_ev + 17, x
    cmp #6
    bcs follow
    inc route_ev + 17, x
    bra follow
more_slow:
    lda route_ev + 17, x
    cmp #2
    bcc follow
    dec route_ev + 17, x
    bra follow
ev_frequency:
    ; 30 raises the frequency and 31 lowers it, between 1 and 8. See `frequency`
    ; in `step_route`, which is the same for the hero: the frames standing still
    ; after each command come from here, and the converter rejects 1.
    and #$01
    bne minus_freq
    lda route_ev + 16, x
    cmp #ROUTE_FREQUENCY
    bcs follow
    inc route_ev + 16, x
    bra follow
minus_freq:
    lda route_ev + 16, x
    cmp #2
    bcc follow
    dec route_ev + 16, x
    bra follow
save_18:
    sta route_ev + 18, x
    bra follow

; `change_graphic`: the only command with an operand. After the 34 comes the
; graphic's index in the map's table —two bytes per graphic, see
; `load_route_graphics`— and from there comes which character to take the twelve
; poses from and which palette to draw them with.
;
; It does not cost a frame: in `UpdateMoveRoute` it falls into the branch that
; does not touch the stop counter, so the next command runs on this same frame.
; It does not touch the pose either: the walk cycle stays where it was, which is
; what `SetSpriteGraphic` does.
change_graphic:
    lda route_ev + 5, x         ; the cursor already advanced when reading the command
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [route_ptr], y
    inc route_ev + 5, x         ; and now past the operand
    asl a                       ; two bytes per entry
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda route_gfx_buf, y
    sta gfx_k                   ; its entry in `npc_poses`, or $FF
    lda route_gfx_buf + 1, y
    sta gfx_pal

    lda route_ev + 0, x
    phx
    jsr event_npc               ; its row, which is what has to change
    plx
    cpy #$FFFF
    beq ready_gfx               ; an event without a graphic has no row
    lda #$FF
    sta npc_buf + 15, y         ; a CharSet imposes nothing on the cell
    lda gfx_k
    cmp #$FF
    bne with_graphic
    ; A CharSet without a single opaque pixel: the event disappears. It is the same
    ; thing `hide_npc` does, and it is 185 of the game's 437 commands 34
    ; —`nobodyhere`—, so it is not the rare case but the most common one.
    lda #0
    sta npc_buf + 14, y
    bra ready_gfx
with_graphic:
    sta npc_buf + 9, y          ; which character its poses come from
    lda npc_buf + 7, y
    and #$F1                    ; the palette lives in bits 1 to 3 of vhoopppN
    sta temp
    lda gfx_pal
    asl a
    and #$0E
    ora temp
    sta npc_buf + 7, y
    lda #$FF
    sta npc_buf + 12, y         ; the pose in VRAM is no longer its own
    lda #1
    sta npc_buf + 14, y         ; and it is visible, in case it was hidden
ready_gfx:
    jmp other_command

; `play_sound_effect`: 35, with the sound effect's index after it, in two bytes.
; Same as on the hero —see `sound_hero`—: `sound_play`, `OP_SOUND`'s path,
; and without costing a frame. X is the slot, and `sound_play` overwrites it.
sound_ev:
    lda route_ev + 5, x         ; the cursor is already on the operand
    inc a
    inc a
    sta route_ev + 5, x         ; and moves past it
    dec a
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    lda [route_ptr], y
    phx
    jsr sound_play              ; returns with 8-bit A
.a8
    plx
    jmp other_command
face:
    sec
    sbc #12
look:
    ; One that spins does not turn with a face_* either, though it costs the
    ; same: `Turn` goes through `UpdateFacing`. `bit` leaves A alone.
    bit route_ev + 18, x
    bmi looked
    sta route_ev + 8, x
looked:                         ; face_*: with frequency 8 it is instant and the
    lda route_ev + 16, x        ; next one follows; with another, it stands
    jsr after_turn              ; still for the turn's frames
    bne turn_wait
    jmp other_command
turn_wait:
    dec a
    sta route_ev + 9, x
    jmp ready


move:
    sta route_dir
    stz route_dir + 1
    lda route_ev + 18, x
    and #$88
    bne no_turn                 ; always faces the same way: `lock_facing` or the
                                ; page's animation type; or it spins, which
                                ; turns it on its own (`UpdateFacing`)
    lda route_dir
    cmp #4
    bcc right                   ; the usual four face where they go
    jsr face_diagonal           ; a diagonal has no pose of its own: see there
right:
    sta route_ev + 8, x         ; move_* faces where it goes
no_turn:
    phx
    jsr event_cell              ; leaves its position in cell_x/cell_y
    jsr prepare_walker          ; and who it is, to collide with the others
    lda route_ev + 12, x
    and #$01
    sta crossing                ; walk_everywhere: `cell_allowed` looks at it
    stz crossing + 1
    lda route_dir
    cmp #4
    bcc straight
    jsr cell_allowed_diag       ; the two L's: nobody looks at the diagonal cell
    bra tested
straight:
    jsr cell_allowed
tested:
    plx
    stz crossing
    stz crossing + 1
    ; `plx` sets Z from what it pulls off the stack, so the answer has to be
    ; looked at again: with the `beq` right after the `plx`, slot 0 —which is X = 0—
    ; always said "blocked" and no move route ever moved.
    cmp #0
    bne no_blocked
    ; Blocked. With `skippable` —the forced ones, and the page ones that ask for
    ; it— it is skipped and the next one is tried; without it, the command is
    ; retried on the coming frame, and so on until the step goes through.
    lda route_ev + 18, x
    and #$04
    beq retries
    jmp other_command
retries:
    dec route_ev + 5, x
    jmp ready
no_blocked:
    phx
    lda route_dir
    jsr move_event_cell
    plx
    lda route_dir
    sta route_ev + 30, x        ; which way the step goes, which with the facing
    lda #1                      ; locked is not where it faces
    sta route_ev + 7, x         ; there is a step in progress
    jsr step_slot
    rep #$20
.a16
    lda #JUMP_STEP
    sec
    sbc temp
    sta route_ev + 22, x        ; and this frame's part already advanced
    sep #$20
.a8
    lda #1
    sta route_ev + 6, x
ready:
    rts
.endproc

; The forced move route ended on an event that has its own move route: the
; page's comes back, saved at +24 to +29, from the start and with the turn's
; wait. RM2k resumes it where it was; here it starts over.
.proc resume_page
.a8
.i16
    lda route_ev + 24, x
    sta route_ev + 1, x
    lda route_ev + 25, x
    sta route_ev + 2, x
    lda route_ev + 26, x
    sta route_ev + 3, x
    lda route_ev + 27, x
    sta route_ev + 4, x
    stz route_ev + 5, x
    lda route_ev + 28, x
    sta route_ev + 16, x
    lda route_ev + 29, x
    sta route_ev + 17, x
    lda route_ev + 18, x
    ora #$01
    sta route_ev + 18, x
    lda route_ev + 28, x
    jsr after_turn
    sta route_ev + 9, x
    rts
.endproc

; The position of slot X's event, into cell_x/cell_y.
.proc event_cell
.a8
.i16
    lda route_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tay
    lda ev_pos_buf, y
    sta cell_x
    lda ev_pos_buf + 2, y
    sta cell_y
    sep #$20
.a8
    rts
.endproc

; And moves it one cell in the direction A carries. It is done at the **start**
; of the step, not at its end: it is what `begin_step` does with the hero, and
; counting it differently would leave the hero and the events with the cell
; changed on different frames.
; Puts the cell of slot X's event in `cell_x`, `cell_y`. The jump uses it,
; which moves it all at once instead of one step at a time.
.proc move_cell_to_event
.a8
.i16
    lda route_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    lda cell_x
    sta ev_pos_buf + 0, y
    lda cell_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    rts
.endproc

.proc move_event_cell
.a8
.i16
    sta route_dir
    stz route_dir + 1           ; it is used as a sixteen-bit index
    lda route_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    sep #$20
.a8
    ; By table and not by four comparisons: with the diagonals the cell moves on
    ; both axes at once, and this way the straight case is the one with a zero on
    ; one side. X is left overwritten; the caller already saved it.
    ldx route_dir
    lda f:step_dx_table, x
    beq no_dx
    jsr with_sign_16
.a16
    clc                         ; returns with the accumulator in sixteen
    adc ev_pos_buf + 0, y
    sta ev_pos_buf + 0, y
    sep #$20
.a8
no_dx:
    lda f:step_dy_table, x
    beq no_dy
    jsr with_sign_16
.a16
    clc
    adc ev_pos_buf + 2, y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
no_dy:
    rts
.endproc

; The signed byte A carries, extended to sixteen bits. It leaves with the
; accumulator **in sixteen**, which is where the ones adding cells want it.
.proc with_sign_16
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc ready
    ora #$FF00
ready:
    rts
.endproc

