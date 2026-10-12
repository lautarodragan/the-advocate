.segment "FAR2"
.a8
.i16

; --- what RM2k puts over the message window: the arrow and the bar -------------
;
; Both are pieces of the System, and both are drawn by the converter into
; the window's own tiles, with the window's palette —`message_window.rs` in
; `rm2k-snes-screens`—: what is here is choosing which tiles go where.
;
; * **The arrow** of a message waiting for a key is two cells of the
;   window's tilemap, on its bottom edge and centred, that change between
;   the window's own and the arrow's. `window_arrow_cells` has the four
;   ways, per window base: with the frame and without it, off and on.
; * **The bar** of a choice's highlighted option is composed into the
;   window like the text: its line is primed over `window_bar` instead of
;   the bare background. See `msg_bar_source`.
;
; Everything here goes with `f:` or through the direct page: it is reached
; with `jsl`, from bank 0, and the data bank is whatever the caller had.

; How long the arrow stays up and how long it stays off: `Window::Update`
; counts `arrow_animation_frame` to forty and `Window::Draw` shows it below
; twenty. Measured on the 2015 RPG_RT with Wine: on and off about as long.
ARROW_FRAMES = 20

; The size of one way of the arrow in `window_arrow_cells`, and of one
; window base's four.
ARROW_WAY  = WINDOW_ARROW_CELLS * 2
ARROW_BASE = ARROW_WAY * 4

; One frame of the arrow, from `flush_video`, in the vblank, with the window
; on screen. It decides whether the arrow is up and, **only when that
; changed** —`MSG_ARROW_UP`—, writes the cells it should have, on or off, on
; the plane the window shows. That way nobody has to take it off when the
; window closes, when the page goes on, when a choice or the digits of an
; `InputNumber` take the window: they are written off the first vblank the
; arrow is not up. When a window appears or a big picture moves its
; tilemap, `msg_hdma_build` forgets what was written, and it is written
; again. It is two VRAM words, a few times a second.
;
; Not every frame because the vblank is the tightest budget there is, and
; most frames there is nothing to write. Measured over map 6 with the
; camera scrolling, the `anclada` case: from the arrival on, composing the
; message and with it up, `lost_frames` does not move, the same as without
; the arrow.
;
; It is up when RM2k's `Window_Message::OnFinishPage` would set `pause`: the
; page composed, no choice nor digits, no `\^` closing it by itself, and the
; `\|` pauses gone —here they are waited for before the key, in
; `events_tick`, and in RM2k before the page finishes—.
.proc msg_arrow
.a8
.i16
    ; A box cut at a wait in the middle: up while a `\!` waits for its key,
    ; which is RM2k's `SetPause(true)`, and quiet while a timed one runs and
    ; while the box is being drawn. See message_waits.s.
    lda f:MSG_WAIT_HOLD
    beq not_held
    cmp #HOLD_WAITING
    bne quiet
    lda f:MSG_WAIT_KIND
    ora f:msg_state
    bne quiet
    bra blinks
not_held:
    lda f:msg_state
    ora pick_active
    ora f:FAR_MSG_AUTO
    bne quiet
    rep #$20
.a16
    lda f:FAR_MSG_PAUSE
    sep #$20                    ; `sep` does not touch Z
.a8
    bne quiet
blinks:
    lda f:MSG_ARROW_T
    inc a                       ; from $FF, the first frame up is zero
    cmp #(ARROW_FRAMES * 2)
    bcc counted
    lda #0
counted:
    sta f:MSG_ARROW_T
    cmp #ARROW_FRAMES
    lda #0
    bcs up                      ; `lda` does not touch the carry: off
    inc a                       ; on
    bra up
quiet:
    lda #$FF
    sta f:MSG_ARROW_T
    lda #0
up:
    cmp f:MSG_ARROW_UP
    bne changed
    rtl                         ; the cells already say so
changed:
    sta f:MSG_ARROW_UP
    cmp #0                      ; `sta` leaves the `cmp`'s Z, not A's
    beq off
    lda #ARROW_WAY
off:
    sta f:MSG_ARROW_WAY
    ; Which window base: the same question `stamp_window_at` asks, the
    ; distance between the window's tiles and BG2's base.
    ldx map_ofs
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$F0
    sta f:MSG_ARROW_WAY + 1
    lda f:map_table + M_VRAM_WINDOW + 1, x
    sec
    sbc f:MSG_ARROW_WAY + 1
    cmp #$10
    lda f:MSG_ARROW_WAY
    bcc base_ready              ; `lda` does not touch the carry
    clc
    adc #ARROW_BASE
base_ready:
    sta f:MSG_ARROW_WAY
    ; And which plane: the one without the frame is 320 words further.
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:MSG_SC
    and #$00FF
    xba                         ; the tilemap's word: BG2SC is its high byte
    clc
    adc #(WINDOW_ARROW_ROW * TEXT_WINDOW_COLS + WINDOW_ARROW_COL)
    tay
    lda f:MSG_ARROW_WAY
    and #$00FF
    tax
    sep #$20
.a8
    lda f:MSG_PLACE
    and #MSG_BARE
    beq framed
    rep #$20
.a16
    tya
    clc
    adc #(WINDOW_ROWS_ * TEXT_WINDOW_COLS)
    tay
    txa
    clc
    adc #(ARROW_WAY * 2)        ; past the two ways with the frame
    tax
framed:
    rep #$20
.a16
    sty VMADDL
    ; The one-System branch goes first: Goombario reads the widths off the
    ; source in order, `.if`s and all, and the other ends in 8 bits.
.if ::WINDOW_SYSTEMS = 1
    ldy #WINDOW_ARROW_CELLS
cell:
    lda f:window_arrow_cells, x
    sta VMDATAL
    inx
    inx
    dey
    bne cell
.else
    ; The current System's table, which `lda f:table, x` cannot reach: by
    ; DMA, from its pointer plus the way.
    txa
    clc
    win_adc window_arrow_cells, WS_ARROW
    sta A1T0L
    lda #(WINDOW_ARROW_CELLS * 2)
    sta DAS0L
    sep #$20
.a8
    win_bank window_arrow_cells, WS_ARROW
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
.endif
    sep #$20
.a8
    rtl
.endproc

; The source and the size of the highlighted option's line, for
; `prime_line`'s DMA: the window's background with the System's cursor on
; that line, or the cursor alone without the background. Comes back with A
; at $00, which is what DMAP0 takes —one register, one byte at a time—.
;
; The bar is `Window_Message::UpdateCursorRect`'s rectangle, a line tall and
; as wide as the text minus four, drawn as `Window::RefreshCursor` draws it;
; it is the first of the System's two cursor drawings, which RM2k
; alternates every ten frames. See `workflow/divergencias/
; la-barra-de-la-eleccion-no-alterna-sus-dos-dibujos.md`.
.proc msg_bar_source
.a8
.i16
    lda f:MSG_PLACE
    and #MSG_BARE
    beq framed
.if ::WINDOW_SYSTEMS > 1
    rep #$20
.a16
    win_lo window_bar_bare, WS_BAR_BARE
    sta A1T0L
    sep #$20
.a8
.else
    ldx #.loword(window_bar_bare)
    stx A1T0L
.endif
    win_bank window_bar_bare, WS_BAR_BARE
    bra size
framed:
    rep #$20
.a16
    lda f:msg_line
    and #$0003                  ; four lines
    asl a
    tax
    lda f:bar_lines, x
    clc
    win_adc window_bar, WS_BAR
    sta A1T0L
    sep #$20
.a8
    win_bank window_bar, WS_BAR
size:
    sta A1B0
    ldx #TEXT_BUF_BYTES
    stx DAS0L
    lda #$00
    rtl
bar_lines:
    .word 0, TEXT_BUF_BYTES, TEXT_BUF_BYTES * 2, TEXT_BUF_BYTES * 3
.endproc
