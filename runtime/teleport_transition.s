.segment "CODE"
.a8
.i16

; --- the teleport transition -------------------------------------------------
;
; RM2k erases and shows the screen again on every teleport with whatever
; transition the system says, and `ChangeScreenTransitions` changes it from
; then on. The ROM does three, and the converter has already decided which one
; goes —see the transitions, `TRANSITION_FADE`, in rm2k-snes/events/src/compile.rs—:
;
;   the fade     the usual one, `fade_tick`: the master brightness over
;                `fade_ramp`. It is also what goes for the ones the
;                console does not do, like the zoom
;   the mosaic   the same fade, plus the MOSAIC register tied to the
;                brightness: size 16 at brightness 0, size 1 at brightness
;                15, which is what the battle does —see `battle_fade.s`,
;                which explains why the mosaic also darkens, and in RM2k it
;                does not: the load has to fall inside the black—
;   the cut      for erasing, the fade started at its last outgoing
;                tick, so the jump's own tick is already black and the next
;                one loads the map: `fade_from` sets it. For showing, the
;                fade ends on the load's tick, at full brightness and with
;                no ramp back up: `fade_tick` does it
;
; The PPU's mosaic is for the backgrounds and nothing else: **sprites do not
; get pixelated**, and in RM2k they do, because there the whole screen gets
; pixelated. With the brightness going down at the same time it is barely
; noticeable; it is in
; divergences/the-teleport-transitions.md in the book.
;
; `fade_tick` does not need to be touched for the mosaic: it is deduced
; from what the fade already carries —whether there is one, whether the load is
; still pending, and this frame's brightness— and written in the vblank, next
; to the brightness, in `fade_mosaic`.

; `ChangeScreenTransitions`: which one —0 erase, 1 show— and the transition.
; Only the jump stays in bank 0, because the dispatch wants the handler here and
; bank 0 has no room to spare.
.proc op_transition
    jsl f:transition_set
    jmp run_code::other
.endproc

; `EraseScreen` and `ShowScreen`: the body is `screen_erase` and
; `screen_show`, in bank 1, which return with carry set if they started a
; fade. Then the page ends the frame here, as `op_teleport` does, and goes on
; with the command after this one when the fade lets the game run again:
; that is RM2k's wait for the transition. Without a fade —the cut, or
; nothing to do— it goes on right away.
.proc op_show_screen
    jsl f:screen_show
after:
    bcs wait
    jmp run_code::other
wait:
    sty ev_cur
    rts
.endproc

; After `op_show_screen`, so that `after` is already known: `ca65` does not
; resolve a scoped label forward.
.proc op_erase_screen
    jsl f:screen_erase
    jmp op_show_screen::after
.endproc

.segment "FAR"

; The body of `op_transition`: with Y at the first operand, and it returns with
; Y past the last one. The bytecode is read with `[code_ptr], y`, which does not
; depend on the data bank, and far RAM with `f:`.
.proc transition_set
.a8
.i16
    lda [code_ptr], y           ; which: 0 erase, 1 show
    iny
    lsr a                       ; into the carry
    lda [code_ptr], y           ; the transition
    iny
    bcs show
    sta f:TRANSITION_ERASE
    rtl
show:
    sta f:TRANSITION_SHOW
    rtl
.endproc

; The byte of `ticks` from which the fade being started counts, into
; `fade_base`. From `start_fade`.
;
; With the cut for erasing it starts `FADE_CUT` ticks back, on the last
; tick of the outgoing half: the jump's own tick —the one `start_fade`
; already paints— is in the black in the middle, and the first `fade_tick`
; is past `FADE_LOAD`, so it loads the map right there. It is
; `TransitionCutOut`, which lasts one frame in RM2k, followed by whatever
; the show says. `fade_tick` knows nothing about it.
FADE_CUT = FADE_TOTAL / 2 - 1
.assert FADE_CUT >= FADE_RAMP - 1, error, "the cut has to start in the black"
.assert FADE_CUT + 1 >= FADE_LOAD, error, "the cut has to land past the load"
.proc fade_from
.a8
.i16
    lda #$FF                    ; a teleport's: see `fade_mosaic`
    sta f:SCREEN_FADE
    ; With the screen erased by an event the teleport goes as the cut: there
    ; is nothing to darken, and `fade_after_load` leaves it black after the
    ; load. It is `Scene_Map::StartPendingTeleport`, which does not erase an
    ; erased screen, and `FinishPendingTeleport2`, which does not show it.
    lda f:SCREEN_ERASED
    bne cutoff
    lda f:TRANSITION_ERASE
    cmp #TRANSITION_CUTOFF
    beq cutoff
    lda ticks
    bra put
cutoff:
    lda ticks
    sec
    sbc #FADE_CUT
put:
    sta f:fade_base
    rtl
.endproc

; Both set to the fade, from reset: far RAM starts with garbage in bsnes, and
; the first teleport would come out as a mosaic if it happened to land that
; way. Any value that is neither TRANSITION_MOSAIC nor TRANSITION_CUTOFF is the
; fade.
.assert TRANSITION_MOSAIC <> 0, error, "zero has to be the fade"
.assert TRANSITION_CUTOFF <> 0, error, "zero has to be the fade"
.proc boot_transition
.a8
.i16
    lda #0
    sta f:TRANSITION_ERASE
    sta f:TRANSITION_SHOW
    sta f:SCREEN_ERASED         ; and the screen, not erased
    lda #$FF
    sta f:SCREEN_FADE           ; the harness's fades do not go through `fade_from`
    rtl
.endproc

; This frame's mosaic. From `flush_video`, in the vblank and right before
; writing the brightness, so both change on the same frame.
;
; While the map load is pending —`fade_kind` nonzero— the fade is erasing the
; screen; afterwards it is showing it. With no fade, or with one that is not a
; mosaic, it turns it off: it is written every frame, so nobody else has to
; remember to turn it off. `fade`, `fade_kind` and `brightness` live in bank
; 0's BSS, and are read with `f:` so as not to depend on the data bank.
.proc fade_mosaic
.a8
.i16
    lda f:fade
    beq off
    lda f:SCREEN_FADE           ; an `EraseScreen` or a `ShowScreen`: theirs
    cmp #$FF
    bne look
    lda f:fade_kind
    beq showing
    lda f:TRANSITION_ERASE
    bra look
showing:
    lda f:TRANSITION_SHOW
look:
    cmp #TRANSITION_MOSAIC
    bne off
    lda f:brightness
    eor #$0F                    ; the size, the reverse of the brightness
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 and BG2: the map and the layer above
    bra write
off:
    lda #0
write:
    sta f:MOSAIC
    rtl
.endproc

; --- EraseScreen and ShowScreen ---------------------------------------------
;
; They are the teleport's fade cut in half, and nothing more: `EraseScreen`
; is its way down —`FADE_RAMP` ticks to black— and ends there, on the tick the
; teleport would load the map, with the screen left black; `ShowScreen` is its
; way up, from black. The game is frozen while each one lasts, as with the
; teleport and as in RM2k, where the interpreter waits for the transition.
; Their ramps are the teleport's and not RM2k's 35 frames: the same as the
; teleport, which is what the eye compares them with.
;
; The screen stays black because `brightness` stays at zero: `SCREEN_ERASED`
; is what makes the ones that would turn it back on not do it —the teleport,
; `fade_after_load`; the way back from a battle, `battle_fade_to_map`—, and the
; battle's flashes and its fade down, `battle_fade_in`, are not done over the
; black, as RPG_RT does. The message window goes dark with it, and that is
; RM2k too: EasyRPG's `Graphics::Draw` draws nothing below the transition while
; the screen is erased.
;
; The transition: what `ChangeScreenTransitions` carries —the fade, the
; mosaic, the cut— or $FF for the teleport's, which is read here because it
; changes on the fly. The mosaic goes through `fade_mosaic`, which reads
; `SCREEN_FADE`; the cut does not need a fade: the brightness is set and the
; page goes on.

; Whether an event left the screen erased —1, and the brightness stays at
; zero until the show—, and the transition of the fade one of them is
; running, or $FF while the fade running is a teleport's. Neither travels in
; the save: RM2k's save screen shows the map again on the way back, and so
; does ours —`screen_unerase`—. Every use goes with `f:`: `battle_fade.s`
; comes before this file.
.pushseg
.segment "FARBSS"
SCREEN_ERASED: .res 1
SCREEN_FADE:   .res 1
.popseg

; With Y at the operand; returns with Y past it, and carry set if a fade
; started. Over a screen already erased it does nothing, as
; `Transition::Init` skips an erase over an erased screen.
.proc screen_erase
.a8
.i16
    lda [code_ptr], y           ; the transition
    iny
    pha
    lda f:SCREEN_ERASED
    bne nothing
    lda #1
    sta f:SCREEN_ERASED
    pla
    cmp #$FF
    bne kind
    lda f:TRANSITION_ERASE
kind:
    cmp #TRANSITION_CUTOFF
    beq cut
    sta f:SCREEN_FADE
    lda ticks                   ; this tick is the fade's first, as in `start_fade`
    sta f:fade_base
    ; And it already darkens one step: `fade_brightness` of tick 0, which is
    ; the second to last of the ramp read backwards.
    lda f:fade_ramp + FADE_RAMP - 2
    bra start
cut:
    lda #0                      ; black on the next vblank: one frame, as RM2k's
    sta f:brightness
    clc
    rtl
nothing:
    pla
    clc
    rtl
start:
    sta f:brightness
    lda #FADE_NOTHING           ; nothing to load on the black tick
    sta f:fade_kind
    lda #1
    sta f:fade
    rep #$20
.a16
    lda f:frozen_ticks          ; this tick is already frozen: see `start_fade`
    inc a
    sta f:frozen_ticks
    sep #$20
.a8
    sec
    rtl
.endproc

; The same for `ShowScreen`: the fade starts at its way up, `FADE_TOTAL -
; FADE_RAMP` ticks in, so this tick is the ramp's first step and the last one
; is full brightness. Over a screen that is not erased it does nothing; in RM2k
; it fades from the screen to itself, which is nothing to see.
.proc screen_show
.a8
.i16
    lda [code_ptr], y           ; the transition
    iny
    pha
    lda f:SCREEN_ERASED
    beq screen_erase::nothing
    lda #0
    sta f:SCREEN_ERASED
    pla
    cmp #$FF
    bne kind
    lda f:TRANSITION_SHOW
kind:
    cmp #TRANSITION_CUTOFF
    beq cut
    sta f:SCREEN_FADE
    lda ticks
    sec
    sbc #(FADE_TOTAL - FADE_RAMP)
    sta f:fade_base
    lda f:fade_ramp             ; `fade_brightness` of the first tick going up
    bra screen_erase::start
cut:
    lda #BRIGHTNESS_MAX
    sta f:brightness
    clc
    rtl
.endproc

; What the fade does after the load, from `fade_tick`. Returns carry set if it
; ends right there, on this tick, with A the brightness it leaves:
;
;   the screen erased    black: an `EraseScreen` that got there, or a teleport
;                        inside the black, which does not show it
;   the cut for showing  full brightness and no ramp back up
;
; and carry clear if the ramp goes on up. It reads the transition of the one
; running: `SCREEN_FADE`, or the teleport's when it is $FF.
.proc fade_after_load
.a8
.i16
    lda f:SCREEN_ERASED
    bne black
    lda f:SCREEN_FADE
    cmp #$FF
    bne look
    lda f:TRANSITION_SHOW
look:
    cmp #TRANSITION_CUTOFF
    bne ramp
    lda #BRIGHTNESS_MAX
    sec
    rtl
black:
    lda #0
    sec
    rtl
ramp:
    clc
    rtl
.endproc

; The scenes that are not the battle show the map again on the way back, even
; if an event erased it: `Scene_Map::TransitionOut` forgets
; `screen_erased_by_event` for any of them. From the main menu, the save
; screen and the shop, before their `back_to_map`.
.proc screen_unerase
.a8
.i16
    lda #0
    sta f:SCREEN_ERASED
    lda #BRIGHTNESS_MAX
    sta f:brightness
    rtl
.endproc
