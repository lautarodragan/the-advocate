; --- the face of a message box: `ChangeFaceGraphic` --------------------------
;
; RM2k keeps one face for the message window —`Game_System`'s, set by
; `ChangeFaceGraphic`, cleared by one with no name and by the foreground
; interpreter at each event's start and end (see `face_forget`)— and draws it
; on every box until then: 48x48 at (16, 16) of the window, or at the right edge,
; with the text starting 72 pixels in when it is on the left. Here it is the
; same three things, each where it costs nothing new:
;
; * **Its tiles go in the window's text cells.** The face is six cells by
;   six, cells 1 to 6 of text rows 1 to 6 —`MSG_FACE_ROW`, `MSG_FACE_COL_*`
;   from the converter—, and the text does not use them: it starts past the
;   face. So the composer copies the face's tiles into `text_buf` after
;   priming each line's background, as it composes a letter, and the line
;   goes up as always. The cartridge carries each face the game names once,
;   36 tiles of 4bpp and fifteen colours —`message_face_N`, drawn by
;   `rm2k-snes-screens faces`—, and `OP_FACE` names one by its place in
;   `message_face_ptr`. No VRAM beyond the window's.
; * **Its colours go in BG palette 1, on the window's lines only.** The text
;   is palette 0 and the map owns every other entry, so the face's fifteen
;   are written by HDMA —channel 5, which the map leaves free— on the
;   window's first fifteen lines, one a line, before the face starts on line
;   16, and the map's own come back from `cgram_shadow` on lines 64 to 78,
;   after the face ends on 63. Over a window with its background nothing of
;   the map shows on those lines, so nothing shows the swap; see "What faces
;   do not model" in the book for the bare window. No CGRAM beyond the
;   window's.
; * **The face's cells say palette 1 in the tilemap** while a face is up:
;   `msg_face_vblank` flips the palette bits of the 36 cells, in both planes,
;   when the side changes, over the vblanks of the box's first lines, and
;   `stamp_window_at` —which writes the ROM's cells, palette 0— forgets
;   them.
;
; Everything here is cold —a box opening— and lives in `FAR3`; bank 0 has
; the hooks: `op_face`, and a `jsl` in `msg_start`, `message_tick`,
; `prime_line`, `flush_video`, `stamp_window_at`, the reset, and
; `face_forget`'s in `start_waiting` and `events_tick`; `FAR` has the one in
; `common_start`, and `FAR2` the one in `battle_run`. A cartridge
; whose game names no face carries `MESSAGE_FACES = 0` and an empty pointer
; table: the code assembles the same, and `MSG_FACE` stays at none.

.pushseg
.segment "FARBSS"
; The face RM2k's `Game_System` would hold: its place in `message_face_ptr`,
; $FFFF for none, and whether it goes on the right. Reset clears them, and
; `face_forget` the face; they
; do not travel in the save (the divergence says so).
MSG_FACE:       .res 2
MSG_FACE_RIGHT: .res 1
; What the HDMA writes, four bytes a line —CGADD twice, then the colour—:
; the face's fifteen colours, then the map's fifteen back. The tables that
; point here are in ROM, one per window position: see `face_table`.
MSG_FACE_DATA: .res 2 * 15 * 4
.popseg
.pushseg
.segment "BSS"
; What the box being composed draws, decided when it opens: 0 none, 1 a face
; on the left, 2 on the right. `MSG_FACE_SHOWN` is what the tilemap's cells
; say now, the same three values, so the cells are rewritten only when the
; side changes; `MSG_FACE_PENDING` asks the vblank for that and for the HDMA
; data, counting down. In bank 0, which is what `message_tick` and the
; vblank read; what has to outlive a battle is above, in far RAM.
MSG_FACE_DRAW:    .res 1
MSG_FACE_SHOWN:   .res 1
MSG_FACE_PENDING: .res 1
; The bit `flush_video` adds to HDMAEN while a face is up: channel 5's, or 0.
MSG_FACE_HDMA: .res 1
; Where a letter may paint up to, in pixels inside the window: the text
; area's edge, or the face's left edge with a face on the right. Set at
; every line's start by `msg_face_line`; `message_tick` compares against it.
MSG_EDGE: .res 2
; The window's cells in ROM, the plane `stamp_window_at` chose —see there—:
; what the face's cells are rewritten from.
MSG_CELLS_PTR: .res 3
; Scratch: the palette bits being written, the cell being written, the face
; row being copied or the colour entry being written.
MSG_FACE_BITS: .res 2
MSG_FACE_CELL: .res 2
MSG_FACE_STEP: .res 1
.popseg

; The bytes one face takes in ROM —its tiles, then its palette— and a row
; of six tiles: `MESSAGE_FACE_BYTES` in `rm2k-snes-mapdata`, which emits
; them, says the same.
FACE_TILES_BYTES = 6 * 6 * 32
FACE_ROW_BYTES = 6 * 32
.assert MESSAGE_FACE_BYTES = FACE_TILES_BYTES + 15 * 2, error, "a face is not 36 tiles and fifteen colours"
; The face's lines in the window: the first, past the frame and the text
; area's first row, and the one after its last. The palette has to be in
; before the first and restored from the last on: fifteen lines each way,
; one colour a line. The entry that holds between them is the lines from
; the fifteenth to the face's end.
FACE_FIRST_LINE = WINDOW_BORDER + MSG_FACE_ROW * 8
FACE_END_LINE = FACE_FIRST_LINE + 48
FACE_HOLD_LINES = FACE_END_LINE - 15
.assert FACE_FIRST_LINE >= 15, error, "fifteen lines before the face are needed for its palette"
.assert FACE_END_LINE + 15 <= TEXT_WINDOW_ROWS * 8, error, "fifteen lines after the face are needed to restore the map's"
; Palette 1's first colour, its place in `cgram_shadow`, and the palette
; bits of a tilemap word.
FACE_CGADD = 16 + 1
FACE_SHADOW = FACE_CGADD * 2
FACE_PALETTE_BIT = $0400
; The vblanks a box asks for before it shows: see `msg_face_vblank`.
FACE_STEPS = 3
; A row of cells of a line in `text_buf`, in bytes: thirty tiles; and the
; first cell of the face in the window's tilemap, before its column; and
; what is left from the face's last row of the first plane to its first row
; of the second, past the 32 words every row moves.
TEXT_BUF_ROW = WINDOW_TEXT_COLS * 32
FACE_CELL0 = (WINDOW_TEXT_ROW + MSG_FACE_ROW) * 32 + WINDOW_TEXT_COL
FACE_PLANE_STEP = TEXT_WINDOW_ROWS * 32 - 6 * 32

.pushseg
.segment "FAR3"
.a8
.i16

; `OP_FACE`, from `op_face`: the face, a word, and the side, a byte, at
; `[code_ptr], y`; Y past them.
.proc face_change
.a8
.i16
    rep #$20
.a16
    lda [code_ptr], y
    sta f:MSG_FACE
    iny
    iny
    sep #$20
.a8
    lda [code_ptr], y
    sta f:MSG_FACE_RIGHT
    iny
    rtl
.endproc

; At reset: no face, none shown, no HDMA. A loaded save does not bring one.
.proc msg_face_clear
.a8
.i16
    lda #$FF
    sta f:MSG_FACE
    sta f:MSG_FACE + 1
    lda #0
    sta f:MSG_FACE_RIGHT
    sta f:MSG_FACE_DRAW
    sta f:MSG_FACE_SHOWN
    sta f:MSG_FACE_PENDING
    sta f:MSG_FACE_HDMA
    rtl
.endproc

; No face from here on, the box up keeping the one it opened with:
; `Game_System::ClearMessageFace`. RM2k calls it when the foreground
; interpreter starts an event and when it finishes one —`Push` and
; `OnFinishStackFrame` in easyrpg's `game_interpreter.cpp`, both only with
; `main_flag`, at the bottom of the stack and outside a battle—, and when a
; battle starts —`Scene_Battle`'s constructor—. So a face lasts the event
; that set it and no longer: a page that names none shows none, whatever
; another page left. A parallel page's start and end do not clear it. From
; `start_waiting`, `common_start`, the foreground loop in `events_tick` and
; `battle_run`. Until 2026-10-19 only the reset and a `ChangeFaceGraphic`
; with no name cleared it, and Zounds' save point and chests drew the face
; of whichever page had last set one: see
; `tasks/zounds-a-message-shows-a-face-it-should-not.md` in
; the-advocate-work. A8; keeps X and Y.
.proc face_forget
.a8
.i16
    lda #$FF
    sta f:MSG_FACE
    sta f:MSG_FACE + 1
    rtl
.endproc

; A box opens with no window up, from `msg_start`: what it draws is the face
; held now, as `Window_Message::InsertNewPage` reads `Game_System`'s then.
; Keeps X and Y.
.proc msg_face_begin
.a8
.i16
    lda #FACE_STEPS
    sta f:MSG_FACE_PENDING
.if ::MESSAGE_FACES > 0
    rep #$20
.a16
    lda f:MSG_FACE
    cmp #MESSAGE_FACES
    sep #$20
.a8
    bcs none                    ; $FFFF, or a place the cartridge has not
    lda f:MSG_FACE_RIGHT
    and #$01
    inc a                       ; 1 left, 2 right
    bra store
none:
.endif
    lda #0
store:
    sta f:MSG_FACE_DRAW
    rtl
.endproc

; A line starts, from `message_tick`: where its first letter goes and where
; the last may reach. The text of a box with a face on the left starts
; `MSG_FACE_TEXT_X` in —`LeftMargin + FaceSize + RightFaceMargin`—; with
; one on the right it starts at the border and stops where the face starts.
; A choice's options go `CHOICE_INDENT` further in either way, as
; `InsertNewLine` adds 12 to `contents_x` after the face's offset.
.proc msg_face_line
.a8
.i16
    rep #$20
.a16
    lda #WINDOW_BORDER + MESSAGE_WIDTH + 1
    sta f:MSG_EDGE
    lda #WINDOW_BORDER
    sta msg_x
    sep #$20
.a8
    lda f:MSG_FACE_DRAW
    cmp #1
    bne not_left
    rep #$20
.a16
    lda #WINDOW_BORDER + MSG_FACE_TEXT_X
    sta msg_x
    sep #$20
.a8
    bra indent
not_left:
    cmp #2
    bne indent
    rep #$20
.a16
    lda #WINDOW_BORDER + MSG_FACE_RIGHT_X + 1
    sta f:MSG_EDGE
    sep #$20
.a8
indent:
    lda pick_active
    cmp #PICK_CHOICE
    bne done
    rep #$20
.a16
    lda msg_x
    clc
    adc #CHOICE_INDENT
    sta msg_x
    sep #$20
.a8
done:
    rtl
.endproc

; The face's long pointer in ROM into `temp`, from `MSG_FACE`. A8 in and
; out; X is used.
.proc face_pointer
.a8
.i16
    rep #$20
.a16
    lda f:MSG_FACE
    sta temp
    asl a
    clc
    adc temp                    ; times three: a long pointer each
    tax
    lda f:message_face_ptr, x
    sta temp
    sep #$20
.a8
    lda f:message_face_ptr + 2, x
    sta temp + 2
    rts
.endproc

; The face's first column in the text area for side A —1 left, 2 right—,
; in A8.
.proc face_column
.a8
.i16
    cmp #2
    beq right
    lda #MSG_FACE_COL_LEFT
    rts
right:
    lda #MSG_FACE_COL_RIGHT
    rts
.endproc

; After `prime_line`, from it: the face's tiles of the two cell rows of the
; line being composed, into `text_buf` over the background, by the same DMA
; from ROM through WRAM's port. Line L is text rows 2L and 2L + 1; the face
; takes rows `MSG_FACE_ROW` to `MSG_FACE_ROW + 5`, so a line carries none,
; one or two of its six rows, each `FACE_ROW_BYTES` contiguous in ROM.
.proc msg_face_prime
.a8
.i16
.if ::MESSAGE_FACES > 0
    lda f:MSG_FACE_DRAW
    bne has
    rtl
has:
    jsr face_pointer            ; `temp` is the face
    ; The face row of the line's first cell row, 2L - MSG_FACE_ROW, signed:
    ; below zero the first row is above the face, and only the second may
    ; be its.
    lda msg_line
    asl a
    sec
    sbc #MSG_FACE_ROW
    sta f:MSG_FACE_STEP
    ldx #0                      ; which of the line's two rows
each:
    lda f:MSG_FACE_STEP
    bmi next
    cmp #6
    bcs done
    jsr face_row_dma
next:
    lda f:MSG_FACE_STEP
    inc a
    sta f:MSG_FACE_STEP
    inx
    cpx #2
    bcc each
done:
.endif
    rtl
.endproc

; One row of the face —`MSG_FACE_STEP`, 0 to 5— into row X (0 or 1) of
; `text_buf`, from the face at `temp`. Keeps X.
.proc face_row_dma
.a8
.i16
    ; The destination: the buffer's row, thirty tiles each, plus the face's
    ; first column, 32 bytes a tile.
    lda f:MSG_FACE_DRAW
    jsr face_column
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32
    clc
    adc #.loword(text_buf)
    cpx #0
    beq first_row
    clc
    adc #TEXT_BUF_ROW
first_row:
    sta WMADDL
    sep #$20
.a8
    stz WMADDH                  ; the buffer lives in WRAM bank 0
    ; The source: the face's tiles plus the row's bytes. A face is one
    ; block, whole in its bank, so the sum does not leave it.
    lda f:MSG_FACE_STEP
    sta WRMPYA
    lda #FACE_ROW_BYTES
    sta WRMPYB                  ; starts: the product takes eight cycles
    lda temp + 2
    sta A1B0
    lda #$00                    ; one register, one byte at a time
    sta DMAP0
    lda #<WMDATA
    sta BBAD0
    rep #$20
.a16
    lda RDMPYL
    clc
    adc temp
    sta A1T0L
    lda #FACE_ROW_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rts
.endproc

; In the vblank, from `flush_video`, once per line uploaded, when a box
; asked for it on opening: the side that was back to palette 0, the side
; that is to palette 1, and the palette's HDMA table —one of the three per
; vblank, `MSG_FACE_PENDING` counting down from `FACE_STEPS`—. A box
; uploads its four lines in four vblanks, with the window hidden, so the
; three are done before it shows. **One side per vblank on purpose**: the
; line's 1920-byte DMA is already in it, and the 72 words of both sides on
; top of it ran past the vblank's end on the meadow, where the second side
; was lost and the face came out in the text's colours (2026-10-15).
.proc msg_face_vblank
.a8
.i16
    lda f:MSG_FACE_PENDING
    beq done
    cmp #3
    beq clear_old
    cmp #2
    beq set_new
    ; The last step: the table, if there is a face, and the channel's bit.
    lda f:MSG_FACE_DRAW
    beq off
    jsr face_table
    lda #$20                    ; channel 5
    sta f:MSG_FACE_HDMA
    bra last
off:
    lda #0
    sta f:MSG_FACE_HDMA
last:
    lda #0
    sta f:MSG_FACE_PENDING
done:
    rtl
clear_old:
    ; The side that was, if another or none is coming: back to palette 0.
    lda f:MSG_FACE_SHOWN
    beq cleared
    cmp f:MSG_FACE_DRAW
    beq cleared
    pha
    rep #$20
.a16
    lda #0
    sta f:MSG_FACE_BITS
    sep #$20
.a8
    pla
    jsr face_cells
    lda #0
    sta f:MSG_FACE_SHOWN
cleared:
    lda #2
    sta f:MSG_FACE_PENDING
    rtl
set_new:
    ; The side that is, if the cells do not say it yet: palette 1.
    lda f:MSG_FACE_DRAW
    beq set
    cmp f:MSG_FACE_SHOWN
    beq set
    pha
    rep #$20
.a16
    lda #FACE_PALETTE_BIT
    sta f:MSG_FACE_BITS
    sep #$20
.a8
    pla
    jsr face_cells
    lda f:MSG_FACE_DRAW
    sta f:MSG_FACE_SHOWN
set:
    lda #1
    sta f:MSG_FACE_PENDING
    rtl
.endproc

; The 36 cells of side A —1 left, 2 right— in the window's tilemap, both
; planes, written again from the ROM's cells with `MSG_FACE_BITS` in: six
; rows of six words each, the second plane `TEXT_WINDOW_ROWS` rows below.
; With the screen off or in the vblank, like any VRAM write.
.proc face_cells
.a8
.i16
    jsr face_column
    rep #$20
.a16
    and #$00FF
    clc
    adc #FACE_CELL0
    sta f:MSG_FACE_CELL         ; the cell, in words from the tilemap's start
    lda f:MSG_CELLS_PTR
    sta temp
    sep #$20
.a8
    lda f:MSG_CELLS_PTR + 2
    sta temp + 2
    lda #$80
    sta VMAIN                   ; a word at a time
    ldx #0                      ; the row, 0 to 11 across both planes
row:
    rep #$20
.a16
    lda f:MSG_SC
    and #$00FF
    xba                         ; the tilemap's word address: its high byte
    clc
    adc f:MSG_FACE_CELL
    sta VMADDL
    lda f:MSG_FACE_CELL
    asl a
    tay                         ; the cell's bytes in the ROM's cells
    sep #$20
.a8
    lda #6
    sta f:MSG_FACE_STEP
cell:
    rep #$20
.a16
    lda [temp], y
    and #.loword(~(FACE_PALETTE_BIT * 7))
    ora f:MSG_FACE_BITS
    sta VMDATAL
    iny
    iny
    sep #$20
.a8
    lda f:MSG_FACE_STEP
    dec a
    sta f:MSG_FACE_STEP
    bne cell
    ; The next row: 32 words on, or over to the second plane after the
    ; sixth.
    rep #$20
.a16
    lda f:MSG_FACE_CELL
    clc
    adc #32
    cpx #5
    bne same_plane
    adc #FACE_PLANE_STEP - 1    ; `cpx` left the carry set on the match: it adds the one
same_plane:
    sta f:MSG_FACE_CELL
    sep #$20
.a8
    inx
    cpx #12
    bcc row
    rts
.endproc

; The HDMA of the face's palette: channel 5 in indirect mode, the table in
; ROM —one per window position, below— and the colours it points at in
; `MSG_FACE_DATA`, filled here for the face and the map as they are now.
; Each line writes four bytes, mode 3 —CGADD twice, CGDATA twice—: one
; colour. The lines before the window write the map's own entry 31, which
; changes nothing; the window's first fifteen write the face's fifteen, one
; a line; one entry holds through the face writing its last colour again;
; the fifteen after the face put the map's back, from `cgram_shadow`,
; tinted as they are on screen; and then nothing. The table is in ROM and
; not built in RAM because the RAM is what there was not: A Blurred Line's
; release cartridge had 12 bytes of far RAM to spare, and a table with its
; colours inline is 166.
.proc face_table
.a8
.i16
    jsr face_pointer
    rep #$20
.a16
    lda temp
    clc
    adc #FACE_TILES_BYTES
    sta temp                    ; the face's palette
    sep #$20
.a8
    ldx #0                      ; the data, in bytes
    ldy #0                      ; the face's colours, two bytes each
    lda #FACE_CGADD
    sta f:MSG_FACE_STEP
face_each:
    lda f:MSG_FACE_STEP
    sta f:MSG_FACE_DATA, x
    inx
    sta f:MSG_FACE_DATA, x
    inx
    lda [temp], y
    sta f:MSG_FACE_DATA, x
    inx
    iny
    lda [temp], y
    sta f:MSG_FACE_DATA, x
    inx
    iny
    lda f:MSG_FACE_STEP
    inc a
    sta f:MSG_FACE_STEP
    cpy #30
    bcc face_each
    ; The map's back, from the shadow.
    ldy #FACE_SHADOW
    lda #FACE_CGADD
    sta f:MSG_FACE_STEP
map_each:
    lda f:MSG_FACE_STEP
    sta f:MSG_FACE_DATA, x
    inx
    sta f:MSG_FACE_DATA, x
    inx
    lda cgram_shadow, y
    sta f:MSG_FACE_DATA, x
    inx
    iny
    lda cgram_shadow, y
    sta f:MSG_FACE_DATA, x
    inx
    iny
    lda f:MSG_FACE_STEP
    inc a
    sta f:MSG_FACE_STEP
    cpy #FACE_SHADOW + 30
    bcc map_each
    ; Channel 5 at the position's table. The HDMA reads its address at the
    ; top of each frame; `flush_video` turns the channel on with the
    ; window's.
    rep #$20
.a16
    lda f:MSG_PLACE
    and #MSG_WHERE
    asl a
    tax
    lda f:face_tables, x
    sta A1T5L
    sep #$20
.a8
    lda #^face_tables
    sta A1B5
    lda #^MSG_FACE_DATA
    sta DASB5
    lda #$43                    ; indirect; two registers, two writes each
    sta DMAP5
    lda #<CGADD
    sta BBAD5
    rts
.endproc

; The tables, one per window position —top, middle, bottom, as `MSG_WHERE`
; counts them—: a line count, with the repeat bit for the entries that
; write a colour on every line, and where in `MSG_FACE_DATA` the four bytes
; of a line are. An entry's count is seven bits, so the 144 lines above
; the bottom window are two entries, as in `hdma_sc`.
; An entry: its lines, and the four bytes of `MSG_FACE_DATA` it writes
; from, as the line of the face's palette (0 to 14) or of the map's (15 to
; 29). The places are spelled out as the label plus its offset and not as
; constants, because a constant that falls in the pool's area is what
; ABL's `test_wram_reservations.py` forbids.
.macro face_entry count, line
    .byte count
    .word .loword(MSG_FACE_DATA) + (line) * 4
.endmacro
face_table_top:
    face_entry $80 | 15, 0
    face_entry FACE_HOLD_LINES, 14
    face_entry $80 | 15, 15
    .byte 0
face_table_middle:
    face_entry PLACE_MIDDLE, 29
    face_entry $80 | 15, 0
    face_entry FACE_HOLD_LINES, 14
    face_entry $80 | 15, 15
    .byte 0
face_table_bottom:
    face_entry 127, 29
    face_entry PLACE_BOTTOM - 127, 29
    face_entry $80 | 15, 0
    face_entry FACE_HOLD_LINES, 14
    face_entry $80 | 15, 15
    .byte 0
face_tables:
    .word .loword(face_table_top), .loword(face_table_middle), .loword(face_table_bottom)
.assert PLACE_TOP = 0 && PLACE_MIDDLE < 128 && PLACE_BOTTOM - 127 > 0 && PLACE_BOTTOM - 127 < 128, error, "the face's tables do not match the window's positions"
.popseg
