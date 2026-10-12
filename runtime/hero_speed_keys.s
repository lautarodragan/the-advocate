.segment "FAR"
.a8
.i16

; --- the hero's speed with L and R -------------------------------------------
;
; R raises the speed the hero walks at by one and L lowers it, within RM2k's
; 1 to 6. RM2k has nothing like it: it is taro's, on 2026-09-30, and it is in
; divergences/the-heros-speed-with-l-and-r.md in the book.
;
; **It is not the hero's speed: it is a bonus on top of it.** The speed is
; `FAR_HERO_SPEED`, which forced move routes raise and lower and which travels
; in the save; the keys only move `FAR_SPEED_BONUS`, and the hero walks at the
; sum, capped at 1 and 6. That way the game's own state is never touched:
;
;   * a forced move route walks the hero at the game's speed, without the
;     bonus, while it lasts —its last step included—, and the bonus is back on
;     the first step the player takes. RM2k's `MoveRouteSpeedUp` and
;     `SpeedDown` change the speed underneath and stay, as they did;
;   * with the bonus at zero —the keys never pressed, or a cartridge that
;     turns them off— everything is RM2k's to the frame;
;   * it survives teleports and the menu, because nothing clears it but
;     reset, and the save does not carry it.
;
; The keys are read only while the player has the hero: no forced move route
; on him, no message, no page running in the foreground and no event waiting
; to start —the same guards as walking, in `move_hero`—. Menus, the battle and
; a teleport's fade have their own loops or freeze the main one, so they never
; get here. A press that falls where the keys are not read is lost, not kept
; for later: the edge is computed every frame.
;
; A cartridge turns them off with `--no-speed-keys` in its converter flags:
; then `HERO_SPEED_KEYS` is zero and the main loop does not call
; `speed_keys` —see `boot.s`—.

; Reset: no bonus, and no key held. Far RAM starts with garbage on a console
; and in bsnes.
.proc speed_keys_boot
.a8
.i16
    lda #0
    sta f:FAR_LENGTH + FAR_SPEED_BONUS
    sta f:FAR_LENGTH + FAR_SPEED_KEYS
    rtl
.endproc

; Once per frame, from the main loop before `move_hero`, with the pad already
; read. Clobbers A.
.proc speed_keys
.a8
.i16
    ; The edge: held now and not on the last frame. JOY1L is still this
    ; frame's: `read_pad` waited for the console to finish reading it.
    lda f:JOY1L
    and #(PAD_L | PAD_R)
    pha
    lda f:FAR_LENGTH + FAR_SPEED_KEYS
    eor #(PAD_L | PAD_R)
    and 1, s
    xba                         ; the edge, kept in B
    pla
    sta f:FAR_LENGTH + FAR_SPEED_KEYS
    xba
    beq ready
    pha
    jsr hero_ruled
    bne drop
    lda f:msg_open
    bne drop
    lda ev_active
    bne drop
    lda f:waiting_n
    bne drop
    ; R first, then L, each from what he walks at now: both on the same
    ; frame undo each other. The bonus is recomputed from that and not
    ; stepped, so that a press never falls on the cap and does nothing: with
    ; the game at 6 and the bonus left at +2 from before, L already gives 5.
    lda 1, s
    and #PAD_R
    beq r_done
    jsr speed_with_bonus
    cmp #6
    bcs r_done
    inc a
    jsr bonus_for
r_done:
    lda 1, s
    and #PAD_L
    beq drop
    jsr speed_with_bonus
    cmp #2
    bcc drop
    dec a
    jsr bonus_for
drop:
    pla
ready:
    rtl
.endproc

; A: the speed the player wants. Leaves the bonus that gives it over the
; game's speed.
.proc bonus_for
.a8
.i16
    sec
    sbc f:FAR_LENGTH + FAR_HERO_SPEED
    sta f:FAR_LENGTH + FAR_SPEED_BONUS
    rts
.endproc

; The speed the hero walks at, in A: the game's, or the game's plus the bonus
; when the player has him. It is what `hero_anim_frames` asks for, so it is
; what decides how far each frame of a step goes and how long each frame of
; the walk lasts. Keeps X and Y. Leaves the data bank alone: it goes with `f:`.
.proc hero_speed_now
.a8
.i16
    jsr hero_ruled
    bne game
    jsr speed_with_bonus
    rtl
game:
    lda f:FAR_LENGTH + FAR_HERO_SPEED
    rtl
.endproc

; The game's speed plus the bonus, capped at 1 and 6. The sum goes from -4 to
; 11, so the sign of eight bits is enough.
.proc speed_with_bonus
.a8
.i16
    lda f:FAR_LENGTH + FAR_HERO_SPEED
    clc
    adc f:FAR_LENGTH + FAR_SPEED_BONUS
    bmi slowest
    beq slowest
    cmp #7
    bcc ready
    lda #6
    rts
slowest:
    lda #1
ready:
    rts
.endproc

; Whether a forced move route has the hero: A nonzero and Z=0 if so. They are
; the route guards of `move_hero` —a `wait` left, a command left, a jump in
; the air— plus the route's last step still under way, which `move_hero` does
; not need to ask about because it only looks with no step in progress.
.proc hero_ruled
.a8
.i16
    lda route_wait
    bne ready
    lda route_step
    bne ready
    lda f:route_jump
    bne ready
    lda route_i
    cmp route_n
    lda #0                      ; keeps the carry of the `cmp`
    bcs ready                   ; none left: A = 0 and Z=1
    inc a
ready:
    rts
.endproc
