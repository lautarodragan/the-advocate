.segment "CODE"

; The next command of the hero's move route, in A, and the cursor already
; advanced. Clobbers Y and overwrites `route_ptr`, which belongs to the events'
; pass and is not live while the hero walks: `lda [ptr], y` only reads from the
; direct page, and `hero_route` does not fit there.
;
; The index goes to Y through a sixteen-bit A with the high byte cleared: `tay`
; transfers both bytes of the accumulator even when A is eight-bit. It is the
; trap noted at the top of main.s, and here it already made the move route
; read garbage and stop at the first step.
.proc hero_command
.a8
.i16
    rep #$20
.a16
    lda hero_route
    sta route_ptr
    lda route_i
    and #$00FF
    tay
    sep #$20
.a8
    lda hero_route + 2
    sta route_ptr + 2
    lda [route_ptr], y
    inc route_i
    rts
.endproc

; One command of the forced move route. Turning does not use up a frame and it
; goes on with the next; waiting does; and moving starts a one-cell step, which
; `advance_step` then walks like any other. A blocked move is skipped: RM2k
; would retry forever and a hung test says nothing.
; The jumps in here go with `jmp` and not `bra`: the body went from seven
; commands to fifteen and a `bra`'s 127 bytes of reach fell short three times
; in a row. It is the same trap that had already cut twice in the chain of
; `cmp` that was `run_code`'s dispatch before the table, and it is fixed
; the same way.
.proc step_route
.a8
.i16
    ; A `wait` in progress takes the whole frame and does not look at the move
    ; route. It is ROUTE_WAIT frames and not one: it is RM2k's
    ; `SetMaxStopCountForWait`, which with frequency 8 gives twenty.
    ; The jump in progress is not looked at here but in `move_hero`: see
    ; `jump_advance_hero`.
    lda route_wait
    beq no_wait
    dec route_wait
    rts
no_wait:
other_command:
    lda route_i
    cmp route_n
    bcc has_command
    jmp ready                   ; the move route is over; `bcs` no longer reaches
has_command:
    jsr hero_command

    cmp #23                     ; wait: this one and the ROUTE_WAIT - 1 after it,
    bne not_wait                ; plus the turn's if the frequency is low
    lda route_freq
    jsr after_turn
    clc
    adc #(ROUTE_WAIT - 1)
    sta route_wait
    jmp ready
not_wait:
    cmp #12
    bcs not_move
    jmp move                    ; 0..3 are the move_*
not_move:
    cmp #16
    bcc face                    ; 12..15 are the face_*
    ; Turning without moving is not compiled, and facing the hero —21— and
    ; going toward him —9— are not compiled **on the hero**: see
    ; `compile_route` in the compiler. They do not get here. 9 would also fall
    ; into `move` above, which with a direction that is not 0..3 sends the
    ; hero left by elimination, which is the same trap as the diagonals.
    cmp #24
    bne not_jump
    jsr build_hero_jump
    lda route_jump
    bne jump_started
    jmp other_command           ; it could not land there: skipped
jump_started:
    jmp ready
not_jump:
    cmp #25
    bne not_end
    jmp other_command           ; the `begin_jump` already consumed the pair
not_end:
    cmp #28
    bcs not_lock
    cmp #26
    bcc other_command           ; 16 to 22 are not compiled on the hero
    jmp lock_hero               ; 26 and 27; it is far
not_lock:
    cmp #30
    bcs not_speed
    jmp speed                   ; 28 and 29: the speed, which stays
not_speed:
    cmp #32
    bcc frequency               ; 30 and 31: the move route's frequency
    cmp #34
    bne not_graphic_hero
    jmp graphic_hero            ; 34, the only one with an operand; it is far
not_graphic_hero:
    cmp #35
    bne not_sound_hero
    jmp sound_hero              ; 35, with its operand; it is far
not_sound_hero:
    cmp #36
    bcc other_command           ; 32 and 33, the switches, do not get here: the
                                ; converter rejects them
    cmp #38
    bcc cross                   ; 36 and 37
    cmp #40
    bcs other_command
    ; 38 stops the animation and 39 resumes it, so the subtraction goes the
    ; other way around.
    sec
    sbc #38
    eor #$01
    sta route_anim_for
    jmp other_command
cross:
    ; 36 turns it on and 37 off, so the low bit inverted is the value.
    and #$01
    eor #$01
    sta route_crosses
    jmp other_command
frequency:
    ; 30 raises the move route's frequency and 31 lowers it, capped at 8 and
    ; at 1: it is `increase/decrease_movement_frequence`. The frames standing
    ; still after each command come from it, so it is read from `route_freq`
    ; and not from anywhere else.
    ;
    ; With 1 the wait after a step is 256 frames and does not fit in
    ; `route_after_step`'s byte; the converter guarantees it is never reached,
    ; since it rejects the whole move route. Here it is capped at 1 anyway,
    ; like RM2k, in case that guard ever fails.
    and #$01
    bne freq_minus
    lda route_freq
    cmp #ROUTE_FREQUENCY
    bcs freq_ready
    inc route_freq
    bra freq_ready
freq_minus:
    lda route_freq
    cmp #2
    bcc freq_ready
    dec route_freq
freq_ready:
    jmp other_command
face:
    sec
    sbc #12
    ; Also over `hero_lock`: `UpdateMoveRoute` does `SetFacing` straight
    ; for the `face_*`, without `UpdateFacing`, after their `SetDirection`.
    sta hero_heading
    sta hero_dir                ; face_*: with frequency 8 it is instant and the
    lda route_freq              ; next one follows; with another, it stands
    jsr after_turn              ; still for the turn's frames
    bne turn_wait
    jmp other_command
turn_wait:
    dec a
    sta route_wait
    jmp ready

; 26 locks the facing and 27 releases it, so the low bit inverted is the
; value. It stays after the route: see `try_toward`. Unlocked, RM2k's
; `direction` is always the `facing`, so locking starts `hero_heading` from
; `hero_dir`: a boot or a load leave the first stale.
lock_hero:
    and #$01
    eor #$01
    sta hero_lock
    lda hero_dir
    sta hero_heading
    jmp other_command

; `change_graphic` **on the hero**: 34 with its operand, the graphic's index in
; the map's table, same as on an event.
;
; It comes cheap because the two pose tables have the same shape: an entry of
; `npc_poses` is twelve three-byte pointers to the character's poses, and the
; twelve that the actor table gives the leader are written the same way. So it
; is enough to point `hero_poses` thirty-six bytes into `npc_poses` and
; `place_hero` still does not notice.
;
; Two things that are **not** done and that are what it would cost extra:
;
; * `hero_cgram` is turned off. The leader's fifteen colors are uploaded by
;   `apply_tint` **into the row `hero_pal` says**, so leaving it set with
;   the new palette would write Talan's colors over the palette of the graphic
;   it changed to. While the change is in place, the hero is drawn with the new
;   graphic's palette, which already lives in CGRAM with the rest of the map's
;   sprites.
; * It does not survive a map change: `pick_hero_graphic` runs on load and
;   restores it. It is not laziness —the poses live in **the map's** sprite
;   bank, so the graphic from there does not exist here—.
;   The page of map 8's `EV0047`, which is the one that asked for all this,
;   changes to `Crown7` right before teleporting and back to `Future1` right
;   after, so in the game it is not noticeable.
graphic_hero:
    lda #$FF
    sta hero_pose_vram          ; the pose in VRAM is no longer its own
    jsr hero_command            ; the operand, which is left consumed
    jsr hero_poses_of_graphic
    bcc hero_no_graphic
    jmp other_command
hero_no_graphic:
    ; A CharSet without a single opaque pixel —`nobodyhere`— or one that did
    ; not fit in the eight sprite palettes: the hero stops being drawn, which
    ; is what `place_hero` does with the pose pointer at zero and the same that
    ; happens to an event with its row hidden.
    stz hero_poses + 2
    stz hero_cgram + 2
    jmp other_command

; `play_sound_effect`: 35, with the sound effect's index after it, in two bytes.
; It is the same index as `OP_SOUND` and goes the same way, `sound_play`, so
; it sounds the same as a `PlaySound`'s, with MSU-1 or without. It does not
; cost a frame: the next command runs in this one.
sound_hero:
    jsr hero_command            ; the low byte: leaves Y there and `route_ptr` set
    inc route_i                 ; and the cursor, past the high one
    rep #$20
.a16
    lda [route_ptr], y
    jsr sound_play              ; with 16-bit A; returns with 8-bit A
.a8
    jmp other_command


move:
    ; Diagonals do not get here: the converter rejects the page that gives one
    ; to the hero —see MOVE_EVENT in `events.traducir`— because the ROM only
    ; walks them on events, and none of the game's 26 move routes that use
    ; them is the hero's. Without that cut, the elimination in
    ; `try_toward` would send the hero to the left.
    pha                         ; move_* faces where it goes: `try_toward`
    ; The step is noted as the move route's **before** trying it, and not
    ; once it started: `begin_step` already advances the first frame, and
    ; `hero_speed_now` has to know by then that the route rules, or the first
    ; frame of the route's last step —with no commands left— goes at the
    ; speed L and R left. Blocked, it stays at 1 with no step, which
    ; `any_routes` does not count —it asks for `step_left` too— and the next
    ; frame without a step clears.
    lda #1
    sta route_step
    ; Going through walls, both sides say yes. It is
    ; `Game_Map::CheckOrMakeWayEx`'s `if (self.GetThrough()) return true;`,
    ; and it is turned on only around this step: `can_leave` and `can_enter`
    ; are also used by the pad walking, which does not look at it.
    lda route_crosses
    beq no_cross
    lda #1
no_cross:
    sta crossing
    stz crossing + 1
    pla
    jsr try_toward
    stz crossing
    stz crossing + 1
    lda step_left
    bne started                 ; blocked: skipped and the next one is tried
    jmp other_command
started:
    ; The step started, and `route_step`, set above, says the move route
    ; started it: `any_routes` needs this to know the last step of a move
    ; route still counts.
ready:
    rts
speed:
    ; `increase_movement_speed` and `decrease_movement_speed`, capped at 6 and
    ; 1 like `MoveRouteSpeedUp`. On the hero the ROM used to ignore them; now
    ; they change the pace, and change it for good: RM2k restores the
    ; frequency when the move route ends and not the speed.
    cmp #29
    beq speed_minus
    jsr hero_speed_read
    cmp #6
    bcs speed_save
    inc a
    bra speed_save
speed_minus:
    jsr hero_speed_read
    cmp #2
    bcc speed_save
    dec a
speed_save:
    jsr hero_speed_write
    jmp other_command
.endproc

; Whether any forced move route is left unfinished, the hero's included.
; Returns A nonzero if there is. It is `Game_Map::IsAnyMovePending`, which is
; what `ProceedWithMovement` waits for.
;
; For the hero three things count, and the last one is not obvious: that it
; has commands left, that it is in the air, and that it has a step in progress
; **that the move route started**. The last one is needed because a move
; route's last step is still the move route even when no commands are left
; —without it the page would go on eight frames early—, and it has to be only
; the move route's because, once it is over, the player can start walking
; while another move route is still running, and a step from the pad is not a
; pending move route.
;
; The jump does not need that care and that is why it is looked at bare: the
; only one that sets `route_jump` to something other than zero is
; `build_hero_jump`, and only `step_route` calls it, so a hero's jump is
; always from a move route. None comes from the pad. It was missing, and a
; `ProceedWithMovement` right after a jump let the page go with the hero still
; up in the air: there, `MoveRouteFinished` gets set inside `UpdateMovement`,
; that is, on landing.
.proc any_routes
.a8
.i16
    lda route_wait
    bne if                      ; the hero is in the middle of a `wait`
    lda route_jump
    bne if                      ; or is in the air
    lda route_i
    cmp route_n
    bcc if                      ; the hero has commands left
    lda route_step
    beq from_events
    lda step_left
    bne if                      ; and the step it is taking is the move route's

from_events:
    ldx #$0000
other:
    lda route_ev, x
    cmp #ROUTE_EV_FREE
    beq next
    lda route_ev + 18, x
    and #$01
    bne next                    ; the page's own move route is not waited for
    lda route_ev + 7, x         ; a step in progress
    bne if
    lda route_ev + 9, x         ; or a wait
    bne if
    lda route_ev + 13, x        ; or a jump
    bne if
    lda route_ev + 5, x
    cmp route_ev + 4, x
    bcc if                      ; it has commands left
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
    lda #0
    rts
if:
    lda #1
    rts
.endproc
