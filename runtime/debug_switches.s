; --- the debug screen's switches for the global state -------------------------
;
; The last page of the debug screen —left from its first page— is not the
; game's: three rows, `Tint`, `Timer` and `Weather`, each `[ON]` while the
; game has its way and `[OFF]` while A forced it off. They are for
; bisecting lag and other bugs in a game as it is played: the state the game
; leaves on across maps, which a test's jump clears and a played game keeps.
; taro asked for it on 2026-11-17, after the opening's tint —saturation 40,
; left on through every door— turned out to be the ~35 frames each stone
; lost in the Lazer Teeth HQ, and the timer on screen three more.
;
;   Tint      the screen's `TintScreen`: forced off, the screen is neutral,
;             so the palettes and the flashes take their untinted paths
;   Timer     whether the timer is drawn: forced off, its digits are not
;             —`timer_oam`—; the count runs on, and it still fires its pages
;   Weather   the rain and the sandstorm: forced off, `weather_set` with no
;             weather, so no drops, no grains and no sand overlay
;
; **Forcing one off keeps what the game wants**, and gives it back when the
; switch is turned on again: the game's tint, whether its timer shows and its
; weather go to `dbg_kept`, and the live state is the off one. What the
; game asks for while it is forced off goes there too —`dbg_tint_given`,
; `dbg_timer_given` and `dbg_weather_given`, hooks in the three
; commands—, and a save made meanwhile saves the game's, not the forced one
; —`dbg_unforce` and `dbg_force` around the copy, in `save_game`—. So
; turning a switch off and on again changes nothing the game sees. A reset
; —End Game, a Game Over— turns them all on again: `dbg_off_boot`.
;
; **What is not here, and why**:
;
;   * The screen's flash and shake: in RM2k 2000 they always end, so they
;     are not state that stays across maps.
;   * The pictures and the panorama: they are what the game shows —Zounds'
;     menus are pictures—, and they cost per frame only while they move.
;   * The counter's digits —`counter.s`—: `enter_map` hides them, so they
;     do not cross a door.
;   * The parallel common events: they are the game's logic, and turning
;     them off changes what happens, not only what it costs.
;
; **What it costs**: nothing per frame. The forced state is the game's own
; off state, so the main loop does not ask; the three hooks run only when a
; page asks for a tint, a timer or a weather, and each is a `jsl` —four
; bytes— in bank 0. The rest lives in `FAR2` and `FAR3`, and only with the debug screen
; —`[debug] debug_screen`—: without it this file assembles nothing.

.if ::DEBUG_SCREEN

; The switches' bits in `dbg_off`, a row each, in the page's order.
DBG_OFF_TINT    = $01
DBG_OFF_TIMER   = $02
DBG_OFF_WEATHER = $04
DBG_OFF_ROWS    = 3

.pushseg
.segment "FARBSS"
; Which are forced off. `dbg_off_boot` zeroes it.
dbg_off: .res 1
; What the game wants while its switch is off: the tint's four channels
; —`tint_r`, `tint_g`, `tint_b` and `tint_s`—, whether the timer shows, and
; the weather's type and strength.
dbg_kept: .res 7
.popseg
DBG_KEPT_TINT    = dbg_kept + 0
DBG_KEPT_TIMER   = dbg_kept + 4
DBG_KEPT_WEATHER = dbg_kept + 5

; **Split between two banks, and tight**: what the commands and `save_game`
; call is in `FAR2`, and what only the screen calls is in `FAR3`, next to it.
; Neither bank had room for all of it in every game: Sunset over Imdahl's
; `FAR2` and Zounds' `FAR3` are the fullest —measure them with `just space`
; before adding here—.
.pushseg
.segment "FAR2"
.a8
.i16

; From `boot_init`: none forced off. Clobbers A.
.proc dbg_off_boot
    lda #0
    sta f:dbg_off
    rtl
.endproc

; --- the hooks in the commands ------------------------------------------------

; `op_tint` just wrote the tint: if it is forced off, what was written is the
; game's, and the screen stays neutral. Keeps Y.
.proc dbg_tint_given
    lda f:dbg_off
    lsr a                       ; DBG_OFF_TINT, into the carry
    bcc done
    jsl f:dbg_tint_off
done:
    rtl
.endproc

; `op_timer` starts the timer, with A whether it shows: if the timer is
; forced off, that is the game's, and A comes back 0. Keeps X and Y.
.proc dbg_timer_given
    pha
    lda f:dbg_off
    and #DBG_OFF_TIMER
    beq not_forced
    pla
    sta f:DBG_KEPT_TIMER
    lda #0
    rtl
not_forced:
    pla
    rtl
.endproc

; `op_weather` asks for the weather in `temp` —the type— and `temp + 1` —the
; strength—: if it is forced off, that is the game's, and it asks for none.
; Keeps X and Y.
.proc dbg_weather_given
    lda f:dbg_off
    and #DBG_OFF_WEATHER
    beq done
    lda temp
    sta f:DBG_KEPT_WEATHER
    lda temp + 1
    sta f:DBG_KEPT_WEATHER + 1
    stz temp
    stz temp + 1
done:
    rtl
.endproc

; --- forcing off and giving back the tint and the timer -------------------------

; The tint to `dbg_kept`, and the screen neutral. `tint_r`, `tint_g` and
; `tint_b` are three bytes in a row of the direct page. Keeps Y.
.proc dbg_tint_off
    phx
    ldx #2
each:
    lda tint_r, x
    sta f:DBG_KEPT_TINT, x
    lda #TINT_NEUTRAL
    sta tint_r, x
    dex
    bpl each
    lda f:tint_s
    sta f:DBG_KEPT_TINT + 3
    lda #TINT_NEUTRAL
    sta f:tint_s
    plx
    rtl
.endproc
.assert tint_g = tint_r + 1 && tint_b = tint_r + 2, error, "dbg_tint_off takes tint_r, tint_g and tint_b as three bytes in a row"

; And back from `dbg_kept`. Clobbers X.
.proc dbg_tint_back
    ldx #2
each:
    lda f:DBG_KEPT_TINT, x
    sta tint_r, x
    dex
    bpl each
    lda f:DBG_KEPT_TINT + 3
    sta f:tint_s
    rtl
.endproc

; Whether the timer shows, to `dbg_kept`, and hidden.
.proc dbg_timer_off
    lda f:timer_visible
    sta f:DBG_KEPT_TIMER
    lda #0
    sta f:timer_visible
    rtl
.endproc

; And back: only if it still runs. A timer that stopped meanwhile —its end,
; or a `StopTimer`— hides as RM2k hides it, and no hook had to see that: a
; timer that does not run never shows —see `timer_tick` and `op_timer`—.
.proc dbg_timer_back
    lda f:timer_active
    beq hidden
    lda f:DBG_KEPT_TIMER
hidden:
    sta f:timer_visible
    rtl
.endproc

; --- the save ------------------------------------------------------------------

; Around `save_game`'s copy: what is forced off goes back to the game's for
; the copy —`dbg_unforce`— and off again after it —`dbg_force`—. The
; weather is not saved, so it is not touched. Clobbers A and X.
.proc dbg_unforce
    lda f:dbg_off
    lsr a                       ; DBG_OFF_TINT
    bcc tint_done
    jsl f:dbg_tint_back
tint_done:
    lda f:dbg_off
    and #DBG_OFF_TIMER
    beq done
    jsl f:dbg_timer_back
done:
    rtl
.endproc

.proc dbg_force
    lda f:dbg_off
    lsr a                       ; DBG_OFF_TINT
    bcc tint_done
    jsl f:dbg_tint_off
tint_done:
    lda f:dbg_off
    and #DBG_OFF_TIMER
    beq done
    jsl f:dbg_timer_off
done:
    rtl
.endproc
.assert DBG_OFF_TINT = 1, error, "the hooks find the tint's switch with an lsr"

.popseg

; --- the page, next to the screen ----------------------------------------------

.pushseg
.segment "FAR3"
.a8
.i16

; Row A of the page, forced off if it was not and given back if it was. The
; map takes it when the pause menu closes: `back_to_map` applies the tint
; and its palettes, the timer's included, and the objects are built again.
.proc dbg_off_flip
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:dbg_off_bits, x
    sta temp
    lda f:dbg_off
    eor temp
    sta f:dbg_off
    and temp
    beq back                    ; it was off, and goes back
    cpx #1
    bcc tint_now_off
    beq timer_now_off
    ; The weather to `dbg_kept`, and none.
    lda f:WEATHER_L
    sta f:DBG_KEPT_WEATHER
    lda f:WEATHER_L + 1
    sta f:DBG_KEPT_WEATHER + 1
    stz temp
    stz temp + 1
    bra weather_now
tint_now_off:
    jsl f:dbg_tint_off
    rts
timer_now_off:
    jsl f:dbg_timer_off
    rts
back:
    cpx #1
    bcc tint_now_back
    beq timer_now_back
    ; And back: `weather_set` starts it again, its drops off and its
    ; randomness at its seed, as a `WeatherEffects` that changes it does.
    lda f:DBG_KEPT_WEATHER
    sta temp
    lda f:DBG_KEPT_WEATHER + 1
    sta temp + 1
weather_now:
    CALL0 weather_set
    rts
tint_now_back:
    jsl f:dbg_tint_back
    rts
timer_now_back:
    jsl f:dbg_timer_back
    rts
.endproc

; Carry set if row A is forced off. Clobbers A and X.
.proc dbg_off_is
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:dbg_off_bits, x
    and f:dbg_off
    cmp #1                      ; a bit at all: carry set
    rts
.endproc

; Row A's name, a length and its letters: X its offset in `dbg_off_names`.
; Clobbers A.
.proc dbg_off_name
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:dbg_off_name_at, x
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

dbg_off_bits:
    .byte DBG_OFF_TINT, DBG_OFF_TIMER, DBG_OFF_WEATHER
.assert * - dbg_off_bits = DBG_OFF_ROWS, error, "a switch of the state without its bit"
; The names, in the screen's letters: an ASCII letter is its own byte —see
; `Glyphs::encode` in rm2k-snes-screens—, and the console's glyphs are
; always there.
dbg_off_names:
dbg_off_name_tint:    .byte 4, "Tint"
dbg_off_name_timer:   .byte 5, "Timer"
dbg_off_name_weather: .byte 7, "Weather"
dbg_off_name_at:
    .byte dbg_off_name_tint - dbg_off_names, dbg_off_name_timer - dbg_off_names
    .byte dbg_off_name_weather - dbg_off_names
.assert * - dbg_off_name_at = DBG_OFF_ROWS, error, "a switch of the state without its name"

.popseg
.endif
