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
; camera scrolling, the `anchored` case: from the arrival on, composing the
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
    ; What the box typed goes up first, and its ink: see message_pace.s.
    jsl f:msg_pace_vblank
    ; A box being typed: up while a `\!` waits for its key, which is RM2k's
    ; `SetPause(true)`, and quiet while it types or a timed wait runs —
    ; `msg_state` is not 0 until it is done—.
    lda f:MSG_KEY
    bne blinks
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
    ; Drawn as objects, `arrow_oam` reads that and there are no cells to
    ; write: see the end of this file.
    pha
    lda f:MSG_ARROW_OBJ + 1
    bpl in_cells
    pla
    rtl
in_cells:
    pla
    cmp #0                      ; `pla` leaves A's Z, but `cmp` says it plainly
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
; alternates every ten frames. See `divergences/
; the-choice-bar-does-not-alternate-its-two-drawings.md` in the book.
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

; --- the arrow as objects, in a window without its background ----------------
;
; Without the background, the window's cells take BG2 —the map's layer
; above, roofs and treetops— on every line they are on, edge to edge: see
; `msg_bands`. The arrow alone kept the bottom row's eight lines, so where
; the map has room it is drawn as two 8x8 objects instead, and those lines
; are the map's. It is where RM2k has it: over everything but the timer
; —`Priority_Window` is 130 and `Priority_Timer` 140—, so priority 3 and the
; first objects after the timer's, which cover the characters' too.
;
; The room is a word per map, `arrow_objs`, which rm2k-snes-mapdata decides:
; two tiles past the sprite bank and a sprite palette nobody takes, or 0.
; Into them go the window's own arrow tiles and the window's colours, so
; nothing of the System is redrawn or loses a colour, and nobody tints them
; —the tint runs over the map's palettes only—, which is what RM2k does
; with the window. A map without that room keeps the arrow in the cells.
;
; FAR3, like the rest of what is decided when the window appears. Data bank
; 0, as in the vblank and in `build_oam`, which are its callers.
.pushseg
.segment "FAR3"
.a8
.i16
.assert ARROW_OBJ_TILES = WINDOW_ARROW_CELLS, error, "the arrow's objects are not as many as its cells"
.assert CGRAM_BASE <= 16, error, "the window's colours do not fit in a sprite palette"

; Whether this window draws its arrow as objects: the map's word in
; `MSG_ARROW_OBJ`, or 0 for the cells —a window with its background, a map
; without room, or a big picture up, which has the window's tilemap
; elsewhere and its tiles over the sprite bank—; and if so, its tiles and
; its colours to their places. From `msg_hdma_build`, in the vblank in which
; the window appears or with the screen off.
.proc arrow_obj_choose
.a8
.i16
    rep #$20
.a16
    lda #0
    sta f:MSG_ARROW_OBJ
    sep #$20
.a8
    lda f:MSG_PLACE
    and #MSG_BARE
    beq cells
    ; A big picture moves the window's tilemap from the map's: see
    ; `big_load`, which calls this before it sets BIG_ON.
    ldx map_ofs
    lda f:map_table + M_VRAM_WINDOW_MAP + 1, x
    cmp f:MSG_SC
    bne cells
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:arrow_objs, x
    sta f:MSG_ARROW_OBJ
    sep #$20                    ; `sep` does not touch Z
.a8
    beq cells
    jsr arrow_obj_load
cells:
    jsr gold_choose             ; and the inn's gold window: see gold_window.s
    rts
.endproc

; The arrow's two tiles and the window's colours to the place
; `MSG_ARROW_OBJ` says: the tiles from the sprites' base, sixteen words
; each, and the colours from entry 1 of its palette —0 is the objects'
; transparent—. 64 and up to 30 bytes, in the vblank.
.proc arrow_obj_load
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:MSG_ARROW_OBJ
    and #$01FF
    asl a
    asl a
    asl a
    asl a
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta VMADDL
    win_lo window_arrow_obj, WS_ARROW_OBJ
    sta A1T0L
    lda #(ARROW_OBJ_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    win_bank window_arrow_obj, WS_ARROW_OBJ
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda f:MSG_ARROW_OBJ + 1
    and #$0E                    ; the palette, times two
    asl a
    asl a
    asl a
    ora #$81                    ; the sprites' half, past the transparent
    sta CGADD
    rep #$20
.a16
    win_lo window_cgram, WS_CGRAM
    inc a
    inc a
    sta A1T0L
    lda #((CGRAM_BASE - 1) * 2)
    sta DAS0L
    sep #$20
.a8
    win_bank window_cgram, WS_CGRAM
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; `arrow_obj_load` for `window_swap_upload`, in FAR2: a System changed with
; the window up brings its own arrow and colours.
.proc arrow_obj_load_l
.a8
.i16
    lda f:MSG_ARROW_OBJ + 1
    bpl none
    jsr arrow_obj_load
none:
    rtl
.endproc

; The arrow's two objects, from `build_oam` with a window on screen, while
; `msg_arrow`'s count has it up and the window draws it as objects. Its corner is
; the cells' —`WINDOW_ARROW_COL` and `WINDOW_ARROW_ROW` of the window—:
; an object's Y is the line of the screen it starts on, the way the
; window's scroll puts its first row on the line the window starts. Measured
; against the cells, on 2026-10-18: the same pixels on the same lines.
;
; **It is drawn as the arrow will be on the next frame**, not as it is: the
; OAM built now goes up in the next vblank, where `msg_arrow` counts the
; blink one more, and the cells change in that vblank too. Read off
; `MSG_ARROW_UP`, the objects went up and down a frame after the cells
; did, on every edge of the blink. So the count one ahead; what it cannot
; see coming is the first frame —the count starts in the vblank the window
; appears, and the OAM was built without it— and a quiet that starts, where
; it shows one frame more, as before.
.proc arrow_oam
.a8
.i16
    jsr gold_oam                ; the inn's gold window first: gold_window.s
    lda f:MSG_ARROW_T
    cmp #$FF
    beq done                    ; quiet
    inc a
    cmp #(ARROW_FRAMES * 2)
    bcc counted
    lda #0
counted:
    cmp #ARROW_FRAMES
    bcs done                    ; off on the next frame
    lda f:MSG_ARROW_OBJ + 1
    bpl done
    stz obj_big                 ; 8x8
    lda f:MSG_PLACE
    and #MSG_WHERE
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; four bytes per position
    tax
    lda f:place_rows + 0, x
    and #$00FF
    clc
    adc #(WINDOW_ARROW_ROW * 8)
    sta obj_y
    lda #(WINDOW_ARROW_COL * 8)
    sta obj_x
    lda f:MSG_ARROW_OBJ
    ldy #ARROW_OBJ_TILES
each:
    pha
    sep #$20
.a8
    sta obj_tile
    xba
    and #$0F                    ; vhoopppN: the palette and the ninth bit,
    ora #$30                    ; and priority 3, in front of everything
    sta obj_attr
    phy
    jsl f:emit_object_far + FAST
    ply
    rep #$20
.a16
    lda obj_x
    clc
    adc #8
    sta obj_x
    pla
    inc a                       ; the next tile, its ninth bit included
    dey
    bne each
    sep #$20
.a8
    lda #$02                    ; and whatever follows is 32x32 again
    sta obj_big
done:
    rtl
.endproc

.popseg

; What the window without its background decided about its arrow when it
; appeared: the map's word of `arrow_objs`, or 0 if it is in the cells.
.pushseg
.segment "FARBSS"
MSG_ARROW_OBJ: .res 2
.popseg
