.segment "CODE"

; How many ticks autofire keeps A pressed and how many released: four and
; four make 7.5 presses per second. It is there to be tuned by playing, but it
; has to be a power of two, because the phase is one bit of the counter; and
; that way the counter also wraps at 256 without cutting a half cycle short.
AUTOFIRE_FRAMES = 4
.assert AUTOFIRE_FRAMES & (AUTOFIRE_FRAMES - 1) = 0, error, "AUTOFIRE_FRAMES has to be a power of two"
.assert AUTOFIRE_FRAMES > 0 && AUTOFIRE_FRAMES < $100, error, "AUTOFIRE_FRAMES has to fit in the one-byte counter"

; --- reading the controller ------------------------------------------------
; The console reads the controllers on its own when vblank starts, but it
; takes a few scanlines. Bit 0 of HVBJOY says whether it is still at it:
; reading earlier returns half-assembled garbage.
; The console reads the controllers on its own when vblank starts, but it does
; not start in the same cycle vblank starts: it takes a few dozen cycles, and
; then about four scanlines to finish. Bit 0 of HVBJOY is 1 while it is at it.
;
; Asking only "is it done?" has a race: since wait_vblank returns right as
; vblank starts, the read has not started yet, the bit is 0, and the code goes
; straight through reading the registers while the console is about to
; overwrite them. Every so often a half-assembled value comes out and that
; frame loses its movement, which shows as a stutter. That is why it has to
; wait first for the read to start.
.proc read_pad
.a8
.i16
arranca:
    lda HVBJOY
    and #$01
    beq arranca                 ; not started yet
termina:
    lda HVBJOY
    and #$01
    bne termina                 ; still reading
    lda pad
    sta pad_ant                 ; the previous one, for the edges below
    lda JOY1H
    sta pad
    jsl arrows_repeat         ; holding an arrow presses it again
    ; For A what matters is not the state but the edge: RM2k closes the
    ; message with `Input::IsTriggered`, that is, with the transition from
    ; released to pressed. Holding it fires nothing again, and that is why the
    ; test can press it and leave it pressed until the end.
    lda pad_a
    sta pad_a_ant
    lda JOY1L
    bit #PAD_X
    bne con_x
    stz autofire                ; so the next X starts by pressing A
    and #PAD_A
    sta pad_a
    rts
    ; X is autofire for A: while it is held, `pad_a` spends AUTOFIRE_FRAMES
    ; ticks pressed and as many released, and each return to pressed is a new
    ; edge, that is, a press. RM2k does not have it: see
    ; `workflow/divergencias/autofire-de-a-con-x.md`.
    ;
    ; The real A is added with an OR, so it wins: with A and X held `pad_a`
    ; stays pressed and there are no edges, which is the same as holding A
    ; alone. And releasing X cannot leave anything stuck or press one time too
    ; many: the next tick goes through the path above, which writes only the
    ; real A, so at most it clears a pressed `pad_a`, and that is not a rising
    ; edge.
con_x:
    and #PAD_A
    sta pad_a
    lda autofire
    inc autofire
    and #AUTOFIRE_FRAMES       ; tick 0 falls in the pressed phase: X presses now
    bne apagado
    lda #PAD_A
    tsb pad_a
apagado:
    rts
.endproc


; --- arrow repeat -----------------------------------------------------------
; It is RM2k's `Input::IsRepeated`: a held arrow fires again on its own, first
; REPEAT_WAIT frames after pressing it and then every REPEAT_EVERY, so
; holding down in a menu scrolls down by itself. The numbers are easyrpg's,
; `src/input.cpp`: `start_repeat_time = 23` and `repeat_time = 4`, with
; `press_time == 1 || (press_time >= 23 && press_time % 4 == 0)`, and
; `press_time` is 1 on the frame of the edge. So it fires on frame 0 —the
; usual edge—, on 23, on 27, on 31…: a wait of 0.38 s and fifteen per second
; after that.
;
; **It does not change any screen: it fakes their previous frame.** They all
; compute the edge the same way, `pad` against `pad_ant`, so on the repeat
; frame the held arrows are cleared from `pad_ant` and each screen sees it as a
; new press. That is what gives it to everything that in easyrpg is
; `Window_Selectable` —the menu, the items, the equipment, the slots, the
; title, a message's choices, the shop, the battle, the game end—, which moves
; the cursor with `IsRepeated`. B is not touched, and A and X live in the
; other byte of the controller.
;
; For what has to tell a press from a repeat, `flechas_repetidas` holds which
; bits were faked this frame. There are two: key input **with wait**, which in
; RM2k is plain `IsTriggered` and drops them (`key_value`), and the slots
; screen, which is `Scene_File` and does not wrap around when repeating
; (`ranuras.s`).
;
; There is **a single counter for all four**, and not one per button like
; easyrpg: pressing a new arrow resets it to zero even if another one is still
; held, so scrolling down by holding down and tapping right restarts the wait
; for down. In a one-column menu it does not show, and it costs three bytes of
; RAM less. See `workflow/divergencias/un-solo-contador-para-las-cuatro-flechas.md`.
;
; It lives in bank 1 because there is no room in bank 0; it enters with A8 and
; I16 and a data bank that sees low RAM, which is what `read_pad` already
; asks for.
REPEAT_WAIT = 23
REPEAT_EVERY   = 4
ARROWS = PAD_UP | PAD_DOWN | PAD_LEFT | PAD_RIGHT
.assert ARROWS = $0F, error, "the arrows are the low nibble of JOY1H"

.segment "FAR"
.proc arrows_repeat
.a8
.i16
    stz flechas_repetidas
    lda pad
    eor pad_ant
    and pad
    and #ARROWS
    bne de_cero                 ; an arrow just pressed: its edge is enough
    lda pad
    and #ARROWS
    beq de_cero                 ; none held
    inc flechas_cuadros
    lda flechas_cuadros
    cmp #REPEAT_WAIT
    bcc ready
    ; It steps back REPEAT_EVERY, so the next one falls at that distance and
    ; the counter never goes past REPEAT_WAIT.
    lda #REPEAT_WAIT - REPEAT_EVERY
    sta flechas_cuadros
    lda pad
    and #ARROWS
    sta flechas_repetidas
    trb pad_ant                 ; to the screens, just pressed
    rtl
de_cero:
    stz flechas_cuadros
ready:
    rtl
.endproc
