.segment "CODE"

; --- the message window ----------------------------------------------------
; Its tiles and palette are uploaded only once, with the screen off, like
; those of the layer above. They live behind the ones of the layer above, and
; BG2 reaches them with the same base: depending on the layout, the layer
; above has 128 or 256 tiles and the window starts at that index. That is why
; the converter emits two planes of cells, one with each offset added, and
; `stamp_window` picks one.
;
; Its palette is palette **0**, that is the entries below the background, and
; `enter_map_no_events` uploads it together with the screen's backdrop
; color.
.proc load_window
.a8
.i16
    ldx map_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:map_table + M_VRAM_WINDOW, x
    sta VMADDL
    win_lo window_tiles, WS_TILES
    sta A1T0L
    lda #(WINDOW_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    win_bank window_tiles, WS_TILES
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; The window's palette is not uploaded here: it is palette **0**, that is
    ; the entries `enter_map_no_events` already uploaded together with the
    ; backdrop color. It used to float below the lowest layer above in the
    ; ROM and got uploaded on its own; with that, every map's background was
    ; squeezed below it —47 colors— even when they had half of CGRAM free
    ; above.

    ; The window's own tilemap and the HDMA tables, which belong to this map:
    ; the window lives at a VRAM location that depends on the layout.
    jsr stamp_window
    jsr build_hdma
    rts
.endproc

; Writes the window's own tilemap: 320 contiguous cells, a single DMA.
;
; **And 320 more below them**, the same DMA: the window without its frame, for
; `MessageOptions` without the background. The text cells are the same and
; every other one is cell 0, which is BG2's tile 0 —the layer above's, blank
; in every map—. Which of the two shows is only BG2's scroll on the window's
; lines, `MSG_VOFS`: the tilemap is 32x32 and the frame's ten rows left
; twenty-two unused, so taking the background off costs no VRAM write.
;
; Here is the whole difference with what there was before. The window is no
; longer stamped onto the map's tilemap —which scrolls— but onto one of its
; own, 32x32, that it shares with no one. Since it is its own, its ten rows
; of 32 cells are 320 contiguous words: there are no stretches, no wrapping,
; no column 32 to dodge. And since nobody else touches it, this runs **only
; once per map**, from `load_window` and with the screen already off.
;
; Who shows it and where is decided by HDMA; see `build_hdma`.
.proc stamp_window
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_VRAM_WINDOW_MAP, x
    ; and on into `stamp_window_at`
.endproc
; The same at VRAM word A16 and not at the map's: a big picture moves the
; window's tilemap out of its layer's way —see big_picture.s—.
.proc stamp_window_at
.a16
.i16
    sta VMADDL
    sep #$20
.a8
    lda #$80
    sta VMAIN
    ldx map_ofs
    ; Which plane: the one that has baked in the index where the window
    ; starts, which is the distance between it and BG2's base —the high
    ; nibble of BG12NBA—. The layouts put it 128 tiles behind or, the one with
    ; a 256-tile layer above, 256: 256 tiles of 4bpp are $1000 words, $10 in
    ; the high byte. See `WINDOW_BASES` in the converter.
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$F0
    sta temp
    lda f:map_table + M_VRAM_WINDOW + 1, x
    sec
    sbc temp
    cmp #$10                    ; the carry survives the `rep` and the `lda`
    rep #$20
.a16
    lda #(TEXT_WINDOW_ROWS * TEXT_WINDOW_COLS * 2 * 2)
    sta DAS0L                   ; both planes: with the frame and without it
    bcs plane_256
    win_lo window_cells, WS_CELLS
    sta A1T0L
    sep #$20
.a8
    win_bank window_cells, WS_CELLS
    bra with_plane
plane_256:
.a16
    win_lo window_cells_256, WS_CELLS_256
    sta A1T0L
    sep #$20
.a8
    win_bank window_cells_256, WS_CELLS_256
with_plane:
    sta A1B0
    ; The plane chosen, for the face's cells, which are rewritten from it
    ; with palette 1 while a face is up: these are the ROM's, palette 0, so
    ; no face is on them now. See message_face.s.
    sta f:MSG_CELLS_PTR + 2
    rep #$20
.a16
    lda A1T0L
    sta f:MSG_CELLS_PTR
    sep #$20
.a8
    lda #0
    sta f:MSG_FACE_SHOWN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Sets up the window's three HDMA tables and programs their channels. Runs
; once per map, together with the rest of the load.
;
; What HDMA achieves, and no amount of stamping achieved: BG2 changes tilemap
; and scroll **mid-frame**. On the window's 80 lines it is the window's own
; tilemap, with the scroll pinned; on the others it is still the map's layer
; above, with the camera. That is why the window does not move even though
; the camera does, and why there is not a single VRAM write while a message is
; on screen.
;
; **Which lines are the window's is not decided here**: it is the position
; `MessageOptions` asked for, and it is decided each time a window opens.
; The tables are written by `msg_hdma_build`, in message_place.s; this only
; says where the window's tilemap is and points the channels at them.
.proc build_hdma
.a8
.i16
    ldx map_ofs
    lda f:map_table + M_VRAM_WINDOW_MAP + 1, x
    sta f:MSG_SC                ; BG2SC carries the address in its high byte

    lda #$00                    ; one register, one write per stretch
    sta DMAP1
    lda #<BG2SC
    sta BBAD1
    ldx #hdma_sc
    stx A1T1L
    stz A1B1                    ; the tables live in bank 0

    lda #$43                    ; two registers, two writes each, which
    sta DMAP2                   ; is what BG2HOFS and BG2VOFS ask for; and
    lda #<BG2HOFS               ; indirect: the table says where the four
    sta BBAD2                   ; bytes are, the camera's or the window's
    ldx #hdma_ofs
    stx A1T2L
    stz A1B2
    stz DASB2                   ; and those live in bank 0 too

    ; And the third channel hides the objects under the window. In RM2k the
    ; message window covers everything —`Priority_Window` is 130 and the
    ; characters go below it—, but here it is BG2 with priority 1, and an
    ; event marked "above" goes in objects with priority 2, which in mode 3
    ; sits *in front* of BG2: it showed through the window. The suite caught
    ; it with the door on map 7 as soon as events drawn with a tile moved to
    ; sprites. The mask is the PPU's window 1, edge to edge, enabled for
    ; objects only on the lines of the message window: one of the `mask_*`
    ; in message_place.s, which `msg_hdma_build` points the channel at,
    ; because it moves with the window.
    lda #$00
    sta DMAP3
    lda #<WOBJSEL
    sta BBAD3
    ; And the same mask for BG1, on channel 6, which only a flattened map
    ; turns on: see `pano_ppu`.
    stz DMAP6
    lda #<W12SEL
    sta BBAD6
    ; The tables last, which may point channels 2, 3 and 6 elsewhere: see
    ; `msg_swap_build`.
    jsl msg_hdma_build
    rts
.endproc

; --- the text composer -----------------------------------------------------
;
; What makes this fit in a 65816. RM2k draws each glyph using its pixels as a
; **mask** over a 16x16 block of the System, and read that way it asks for
; sampling the block pixel by pixel. Measured, that is not needed: each row of
; the glyph takes a single color —the gradient is vertical— and the shadow is
; a flat color. So all the color comes down to twelve bytes, `font_color`,
; plus `FONT_SHADOW`. That is the measurement that made this cheap.
;
; The text area is 30 cells wide by 8 tall and its 240 tiles **are not
; deduplicated**: each cell has its own, fixed, so composing is writing a
; buffer and uploading it. It is done one line at a time —two cell rows, 60
; tiles, 1920 bytes— and uploaded in the next vblank.
;
; A line is primed with the window's background before the text is written
; on it, because glyphs are not drawn on black but on the skin's gradient.
; That is a DMA from ROM to RAM, which normal DMA cannot do: it goes through
; the window WRAM has on bus B, that is WMADD plus $2180.

; How many characters per pass of the loop. The number is **measured**, not
; chosen: composing the `snes-anclada` message over map 6, with 5 no frame is
; lost, with 6 neither, and with 8 one is lost. It is 5 and not 7 for margin,
; because a pass costs differently on each map —the background streaming, the
; NPCs, the music— and losing frames does not show by looking: what happens is
; that the hero walks slower than in RM2k.
;
; Measured again on 2026-10-03, when the font got variable width and the
; tables went to eight phases, over the same map with the camera scrolling,
; with that message and with one of four full lines —194 letters—: no frame
; is lost up to 18 per pass, and from 20 on they are. The margin is wider
; than it was; the number is left at 5 so that a message appears as fast as
; it always did.
;
; What it costs: the three-line, 51-character message of `snes-ventana` takes
; about 15 frames to appear, and one with four full lines would take about 36.
; That is a quarter of a second, which does not stand out in RM2k either:
; there the window opens with an animation.
MSG_CHARS = 5

; Where the text starts inside the window, in pixels. It is `Window`'s
; border, the same `BORDER` as in rm2k-snes/screens/src/layout.rs.
WINDOW_BORDER = 8

; The glyph's row falls two pixels below the cell's edge, and that does not
; depend on the line: all four start at 10, 26, 42 and 58, which modulo 8 are
; all 2. That is why a twelve-row glyph always fits in the same two cell rows
; and the buffer can be two rows tall.
TEXT_OFS_Y = 2

; One byte further in the text block, crossing the bank window.
;
; `msg_ptr` is a long pointer but the composer advanced it with a 16-bit
; `inc`, so on going past $FFFF it went back to $0000 of the **same** bank.
; What follows $FFFF is $0000 of the next one —the packing only lets the text
; block cross between two banks that continue each other—, which is what
; `msg_start` also knows. In LoROM it was $8000.
;
; It is not theoretical and fixing `msg_start` was not enough: `abl`'s text
; block is 56 KB, so it crosses, and **a box whose bytes fall across the
; edge** starts fine and goes on reading garbage. It is the Neon Vipers
; cutscene on map 14: out of the garbage came a line length of 76 characters
; and with it the whole screen turned to garbage, along the path that the cap
; in `message_tick` now cuts off.
.proc msg_ptr_next
.a16
.i16
    inc msg_ptr
    bne ready
    sep #$20
.a8
    inc msg_ptr + 2
    rep #$20
.a16
ready:
    rts
.endproc

; Starts a message: leaves the pointer on its first line and the composer
; running. The window does not appear until it finishes.
;
; **A carries the box's offset within `messages`, in 16 bits**, and it has to
; be added to a long pointer crossing banks: see the loop below and
; `msg_ptr_next`, which is the same arithmetic for advancing one byte at a
; time.
.assert MESSAGES_CAP = 4 * $10000, error, "msg_start multiplies the offset by four: it is MESSAGES_STEP in engine.rs of rm2k-snes/mapdata"
.proc msg_start
.a16
.i16
    ; The offset is sixteen bits and the text block can be **larger than a
    ; bank**, so the sum can go past $FFFF: the carry goes into the bank.
    ; When it was added sixteen bits at a time and the carry was lost, **every
    ; text box past the first bank read from somewhere else**: the header and
    ; the line lengths came out of anything.
    ;
    ; And the offset counts in steps of four bytes —`MESSAGES_STEP` in
    ; events.py—, so the block reaches 256 KB: the two bits that fall out of
    ; the `asl`s go to `temp`, and each unit of what it gathers is 64 KB, that
    ; is one bank. With `rol` and not with a branch per bit on purpose:
    ; that way the top bit —more than 128 KB, which no cartridge in the suite
    ; reaches— runs the same instructions as the bottom one, which does.
    phx
    stz temp
    asl a
    rol temp
    asl a
    rol temp
    pha
    lda temp                    ; one bank per 64 KB
    clc
    adc #^messages
    tax
    pla
    clc
    adc #.loword(messages)
    bcc in_bank
    inx                         ; the carry, into the next bank
in_bank:
    sta msg_ptr
    sep #$20
.a8
    txa
    sta msg_ptr + 2
    rep #$20
.a16
    plx
; And from here when `msg_ptr` already points at the box: the level-up
; message's, which `OP_LEVEL_PAGE` composes in RAM. Entered with A16.
at_pointer:
    ; The escape queue starts clean before reading the header: a garbage pause
    ; there would leave the page stuck forever.
    lda #0
    sta f:FAR_MSG_PAUSE         ; `stz` has no long mode
    sta f:MSG_WAIT_HOLD         ; and no wait in the middle: two bytes, with
                                ; MSG_WAIT_SKIP. See message_waits.s
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ldy #0
    lda [msg_ptr], y            ; the header: the lines in the bottom three
    sta msg_lines               ; bits, the auto-close in bit 3 and the pauses
                                ; in the top nibble. It is stored whole and
                                ; whoever reads it masks it; one more byte in
                                ; bank 0 is exactly what there is not.
    and #HEADER_AUTOCLOSE
    sta f:FAR_MSG_AUTO
    lda msg_lines
    lsr
    lsr
    lsr
    lsr                         ; how many pauses it carries
    beq no_pause
    ; And how long they last: `PAUSE_FRAMES` each, which is 61 and not 60.
    ; The product is 16 bits because fifteen pauses are 915 frames, so the
    ; hardware does it, as with the tint.
    sta WRMPYA
    lda #PAUSE_FRAMES
    sta WRMPYB                  ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta f:FAR_MSG_PAUSE
    sep #$20
.a8
no_pause:
    rep #$20
.a16
    jsr msg_ptr_next
    sep #$20
.a8
    stz msg_line
    stz msg_primed
    stz msg_upload
    ; Where the window goes and whether it has a background, **only if none
    ; is open**: a choice whose cursor moves calls here again with the window
    ; on screen, and RM2k does not move a window that is already up.
    lda msg_open
    bne placed
    jsl msg_place
    jsl f:msg_face_begin        ; and which face it draws: see message_face.s
placed:
    lda #1
    sta msg_state
    rts
.endproc
; Its name from outside: `op_level_page` is assembled before this, and ca65
; does not resolve a scope's label ahead of the scope.
msg_start_at = msg_start::at_pointer

; One frame of the composer, from the main loop.
.proc message_tick
.a8
.i16
    jsl f:msg_hold_tick         ; the wait in the middle of a box, if there is one
    lda msg_state
    cmp #1
    beq working
    rts
working:
    lda msg_upload
    beq no_upload
    rts                         ; the previous line has not been uploaded yet
no_upload:
    lda msg_primed
    bne composing

    ; New line: the background is copied into it and its length is read. The
    ; lines the message does not carry are primed and uploaded anyway: VRAM
    ; holds the previous message's text and it has to be covered.
    jsr prime_line
    stz msg_length
    ; No half of a pair waiting: this is the only place it is cleared, and
    ; every line —the first of a box too— comes through here before its
    ; first letter. A pair never crosses the end of a line in a box the
    ; converter wrote, but a broken length —the column cap, below— could
    ; leave one, and the WRAM does not boot at zero. And no digit of a
    ; variable's value either; and where the line starts is kept, for the
    ; waits: see `msg_line_start`.
    jsl f:msg_line_start
    lda msg_lines
    and #HEADER_LINES           ; the header also carries the escape queue
    sta temp
    lda msg_line
    cmp temp
    bcs void
    ldy #0
    lda [msg_ptr], y
    sta msg_length
    rep #$20
.a16
    jsr msg_ptr_next
    sep #$20
.a8
void:
    stz msg_col
    ; Where the line starts and where it may reach, `msg_x` and `MSG_EDGE`:
    ; the border, or past a face on the left; further in on a choice, as
    ; `Window_Message::InsertNewLine` adds 12 on each option's line, which
    ; leaves room for the bar's edge; and up to the text area's edge, or to
    ; a face on the right. See message_face.s.
    jsl f:msg_face_line
    jsl f:msg_line_rows         ; and whether its band is the window's
    lda #1
    sta msg_primed

composing:
    ldx #MSG_CHARS
other:
    lda msg_col
    cmp msg_length
    bcs end_line
    ; The letter, which may be half of a pair: see `msg_letter`.
    ; **`MSG_CHARS` counts letters, not bytes**, and so does `msg_length`: a
    ; pair is two passes of this loop, so the text comes out at the same
    ; pace and drawn the same as when each letter was its byte.
    jsl msg_letter
    rep #$20
.a16
    and #$00FF
    sta comp_char
    lda msg_x
    sta comp_col                ; where it starts, in pixels inside the window
    sep #$20
.a8
    inc msg_col
    phx
    ; The edge. The byte is consumed anyway —otherwise the pointer would be
    ; out of step and the next line would read from the middle of this one—
    ; but a letter that would paint past the text area is not drawn:
    ; `compose_char` writes into `text_buf` with an offset that comes from
    ; x, and past the edge that lands **outside** the buffer, on top of the
    ; window's HDMA, the OAM image and `vq_n`. See the comment on
    ; `compose_char`, further down. `font_reach` is how far each letter
    ; paints, its shadow included; a space paints nothing and always goes.
    ;
    ; And the check goes here even though the converter never emits a
    ; longer line —it measures them with the same advances—, because a
    ; variable's digits grow on the console, and because **the symptom does
    ; not point at the text**: with `vq_n` overwritten, `vram_drain` uploads
    ; 128-byte blocks to arbitrary VRAM addresses, so a bad line shows up as
    ; the whole screen turned to garbage a few frames later and on another
    ; map. It was a column cap, 39, until the font had variable width.
    rep #$20
.a16
    ldx comp_char
    lda f:font_reach, x
    and #$00FF
    clc
    adc comp_col
    cmp f:MSG_EDGE              ; the text area's edge, or a face's on the right
    sep #$20
.a8
    bcs no_draw
    jsr compose_char
    jsl f:msg_grey_char         ; an option nobody can pick: gold_window.s
no_draw:
    ; And the next one starts where this one's advance says: x is
    ; sixteen bits, so a line that grows past the edge does not wrap around
    ; to the left.
    rep #$20
.a16
    ldx comp_char
    lda f:font_advance, x
    and #$00FF
    clc
    adc msg_x
    sta msg_x
    sep #$20
.a8
    plx
    dex
    bne other
    rts

end_line:
    ; The line is ready: it goes up in the next vblank and we move on to the
    ; next one. The next one's background is not primed in this same frame on
    ; purpose: the buffer still holds what has to be uploaded.
    lda #1
    sta msg_upload
    stz msg_primed
    inc msg_line
    lda msg_line
    cmp #WINDOW_TEXT_LINES
    bcc more
    lda #2
    sta msg_state               ; done: `flush_video` turns on the HDMA
more:
    rts
.endproc

; Copies into the buffer the background of the two cell rows of the current
; line. It is the only way for the glyphs to sit on the skin's gradient and
; not on black, and it goes by DMA from ROM to RAM.
;
; Without a background it is zeros, which is BG2's transparent colour: the
; glyphs and their shadow land on the map.
;
; And a choice's highlighted option is primed with the System's cursor
; under it, which is how RM2k draws it: the cursor first and the text over
; it. See `msg_bar_source`.
.proc prime_line
.a8
.i16
    rep #$20
.a16
    ; The destination: always the start of the buffer.
    lda #.loword(text_buf)
    sta WMADDL
    sep #$20
.a8
    stz WMADDH                  ; the buffer lives in WRAM bank 0
    lda pick_active
    cmp #PICK_CHOICE
    bne no_bar
    lda msg_line
    cmp pick_sel
    bne no_bar
    jsl msg_bar_source          ; the source and the size, and A for DMAP0
    bra go
no_bar:
    lda f:MSG_PLACE
    and #MSG_BARE
    beq with_background
    ldx #.loword(zero)
    stx A1T0L
    lda #^zero
    sta A1B0
    ldx #TEXT_BUF_BYTES
    stx DAS0L
    lda #$08                    ; one register, the source fixed
    bra go
with_background:
.if ::WINDOW_BACKDROP_LINES = 1   ; `::`: inside a `.proc`, without it it is not constant
    ; Every line has the same background —a window over one colour, the
    ; project's `[windows.background]`—, so the converter wrote only one
    ; and it goes under all of them.
.if ::WINDOW_SYSTEMS > 1
    rep #$20
.a16
    win_lo window_backdrop, WS_BACKDROP
    sta A1T0L
    sep #$20
.a8
.else
    ldx #.loword(window_backdrop)
    stx A1T0L
.endif
    ldx #TEXT_BUF_BYTES
    stx DAS0L
.else
    rep #$20
.a16
    ; The source: two cell rows per line, 60 tiles of 32 bytes.
    lda msg_line
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; line * 64
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; line * 60, that is the tiles already past
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 bytes each
    clc
    win_adc window_backdrop, WS_BACKDROP
    sta A1T0L
    lda #TEXT_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
.endif
    win_bank window_backdrop, WS_BACKDROP
    sta A1B0
    lda #$00                    ; one register, one byte at a time
go:
    sta DMAP0
    lda #<WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; And the face's tiles over it, on the rows it crosses: see message_face.s.
    jsl f:msg_face_prime
    rts
.endproc

; Uploads the composed line to the window's tile bank, and the face's step
; that goes with it. It goes in the vblank, from `flush_video`, and it is
; 1920 bytes in a single DMA.
;
; **Only if it still fits.** A DMA to VRAM that runs past the vblank writes
; nothing from there on, and what the line did not write stays: a hole of
; colour 0 in the window, which shows BG1 through it until the next box
; covers it. The budget in `flush_video` keeps the poses down while a line
; waits, but a step of the ChipSet's animation goes up whatever it says, up
; to 1664 bytes, and the line goes after it: on The Book of Three's lava
; tunnels, map 46, both families stepped in the vblank Fflewddur's box
; opened, and the line ended on line 1 of the next frame —a black block,
; four and a half cells of the window's second line— (2026-10-20). So the
; line looks at the clock, and from `LINE_LATEST` on it waits for the next
; vblank with `msg_upload` still set: `message_tick` does not touch the
; buffer meanwhile, and `flush_video` does not show a box whose last line
; is not up.
;
; Outside bank 0, the tightest: it is reached with `jsl`. What it
; reads with `lda` alone is low RAM, which `flush_video`'s bank sees the
; same.
.pushseg
.segment "FAR3"

; The last line on which the DMA may start: it takes some twelve —1920
; bytes at eight master cycles, 1364 to a line—, the face's step up to
; one more, and the vblank's last line is 261. Two of margin for what goes
; after it in the same vblank: `msg_arrow`'s cells.
LINE_LATEST = 261 - 12 - 1 - 2

.proc upload_line
.a8
.i16
    lda f:STAT78                ; resets the counters' flip-flop: `tl_line`
    lda f:SLHV                  ; latches them
    lda f:OPVCT
    xba
    lda f:OPVCT
    and #$01                    ; the ninth bit; the rest is open bus
    xba
    rep #$20
.a16
    cmp #LINE_LATEST + 1
    bcs late
    cmp #LINES + 1              ; on the screen's lines: the vblank is over
    bcc late
    sep #$20
.a8
    stz msg_upload
    lda #$80
    sta VMAIN
    ldx map_ofs
    rep #$20
.a16
    ; The tile where this line starts, in VRAM words. The line to upload is
    ; the previous one: `message_tick` already moved on to the next.
    lda msg_line
    and #$00FF
    dec a
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; line * 60 tiles
    clc
    adc #WINDOW_TEXT_BASE
    asl a
    asl a
    asl a
    asl a                       ; times 16 words per tile
    clc
    adc f:map_table + M_VRAM_WINDOW, x
    sta VMADDL
    lda #.loword(text_buf)
    sta A1T0L
    lda #TEXT_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the buffer lives in bank 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; And, while a box asks for it, one step per line's vblank: the face's
    ; cells in the window's tilemap and the HDMA table of its palette, if it
    ; has one. See message_face.s.
    jsl f:msg_face_vblank
    rtl
late:
    sep #$20
.a8
    rtl
.endproc
.popseg

; One character, from its already composed data: `font_pre0` to
; `font_pre7`, one table per phase, built by `font_prerender` in the
; converter. For each of the FONT_PRE_ROWS rows and each of the two cells
; it can touch come three words —what is kept from the buffer, and what is
; set in planes 0-1 and in 2-3—, so painting is read, mask and write. A cell
; that touches nothing comes with the mask at $FFFF and is skipped.
;
; **The edge is checked by `message_tick`**, not by this: here `comp_col`
; —x, in pixels— has already arrived as good and the offset that comes from
; it is used without checking. The check is there because the byte has to be
; consumed anyway even if it is not drawn.
;
; Until 2026-09-11 this painted each row twice —the shadow and then the
; glyph, with a `pintar` routine that built the masks on each call— and
; shifted the row one bit at a time up to its phase: about 25 lines per
; character, and with MSG_CHARS at 5 it was the most expensive thing in the
; frame while a message was being built. taro noticed it in the opening, with
; rain. The result is the same byte for byte: the order of `Font::Render`
; —the shadow of a row is overwritten by the glyph of the next— already comes
; resolved in the tables.
;
; **The tables are a decision with a number, and it was taken again on
; 2026-10-03.** With the variable-width font a letter lands on any of the
; eight columns of a cell, so the precomposed tables went from four phases to
; eight: 117 KB of ROM. The other way was the font itself, one bit per pixel
; —1.1 KB, plus 4.5 KB of a table with each row shifted to each phase—, and
; the colour and the shift done here, letter by letter. Both were written and
; draw the same window pixel for pixel; measured as `MSG_CHARS` is, over map
; 6 with the camera scrolling, the one-bit one loses frames from 11 letters
; per pass —once already with 6— and this one from 20. It costs about twice
; as much per letter, and 5 would have been left with no margin to speak of.
; The 117 KB went in: the cartridge is 8 MB.
.proc compose_char
.a8
.i16
    lda comp_char
    sta WRMPYA
    lda #FONT_PRE_CHAR
    sta WRMPYB                  ; starts: what follows gives it the eight cycles

    ; Where it lands: `comp_col` is x inside the window, in pixels, and from
    ; it come the cell and the phase. Until the font had variable width x
    ; was the border plus six per column, and the phase only 0, 2, 4 or 6.
    rep #$20
.a16
    lda comp_col
    and #$0007
    asl a
    sta comp_phase              ; twice the phase: 0 to 14
    lda comp_col
    lsr a
    lsr a
    lsr a
    sec
    sbc #WINDOW_TEXT_COL        ; the cell column, counted from the text
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 bytes per tile
    sta comp_base

    ; Its data: its phase's table, plus the character times FONT_PRE_CHAR.
    ldx comp_phase
    lda f:font_pre_lo, x
    clc
    adc RDMPYL
    sta comp_glyph
    sep #$20
.a8
    lda f:font_pre_bk, x
    sta comp_glyph + 2

    ldy #0
    lda #(TEXT_OFS_Y * 2)
    sta comp_row                ; two at a time: it is the index into `row_buf_table`
row:
    rep #$20
.a16
    lda comp_row
    and #$00FF
    tax
    lda f:row_buf_table, x
    clc
    adc comp_base
    tax                         ; X = the buffer byte where the row starts
    lda [comp_glyph], y
    cmp #$FFFF
    beq no_first
    sta comp_and
    iny
    iny
    lda text_buf, x             ; planes 0 and 1 of the first cell
    and comp_and
    ora [comp_glyph], y
    sta text_buf, x
    iny
    iny
    lda text_buf + 16, x        ; planes 2 and 3
    and comp_and
    ora [comp_glyph], y
    sta text_buf + 16, x
    iny
    iny
    bra second
no_first:
    tya
    clc
    adc #6
    tay
second:
    lda [comp_glyph], y
    cmp #$FFFF
    beq no_second
    sta comp_and
    iny
    iny
    lda text_buf + 32, x        ; the neighboring cell, one tile further
    and comp_and
    ora [comp_glyph], y
    sta text_buf + 32, x
    iny
    iny
    lda text_buf + 48, x
    and comp_and
    ora [comp_glyph], y
    sta text_buf + 48, x
    iny
    iny
    bra other_row
no_second:
    tya
    clc
    adc #6
    tay
other_row:
    sep #$20
.a8
    lda comp_row
    clc
    adc #2
    sta comp_row
    cmp #((TEXT_OFS_Y + FONT_PRE_ROWS) * 2)
    bcc row
    rts
.endproc

