; --- the layer above, under a message without its background -----------------
;
; A window without its background takes BG2 on the bands of its lines of
; text —see `msg_hdma_build`—, and BG2 is the map's layer above too: on
; those lines the roofs and the treetops went away across the whole screen.
; Here the window's own plane carries the layer on those lines, so what is
; seen is the layer with the letters over it, as RM2k draws it:
;
; * **The cells without letters take the layer's tilemap entries**: the
;   map's BG2 tilemap read out of VRAM in a vblank, for the screen cells the
;   line's two cell rows cover. Both tilemaps name tiles from BG2's base,
;   so an entry is valid in either as it is.
; * **The cells with letters are composed from the layer's pixels**: the
;   layer's tile is read out of VRAM into the composer's buffer where the
;   line is primed, and the glyph is composed over it as over the window's
;   transparent. The cell takes the **text's palette** for the layer's: a
;   copy of it, a few palettes down, with the text's colours at the
;   window's indices —the composer's tables carry indices—. Which colours
;   of the layer sat there, and where the copies go, the converter decided:
;   `layer_text` in rm2k-snes-mapdata. A cell with letters over nothing
;   keeps the window's palette, as always.
; * **The copies are built after every tint** from the layer's tinted
;   colours and the window's untinted ones —`layer_text_tint`—: RM2k tones
;   the map and not the window, and so the letters stay white over a tinted
;   tree.
;
; **Only with the camera on the 8-pixel grid**, which is where it always is
; at rest —`follow_camera` puts the hero's cell centre, 8 mod 16, at half
; the screen, and the clamps are multiples of 8 too—: then the screen's
; cells are the map's, and the window's cells land on them without moving
; the text a pixel from where RM2k draws it. A window that opens with the
; camera moving keeps the old look, and one under which the camera moves
; keeps what it copied: taro left that case out of this first phase
; (2026-10-19).
;
; Nor with a face, a choice, the digits of a number, a big picture —which
; moves the window's tilemap— or a cartridge whose boxes type colours: their
; cells are the window's, as before.
;
; A line, from its start to its letters, in `LAYER_STEP`:
;
;   1  the vblank reads the line's two rows of the layer's tilemap
;   2  the main loop puts the window's cells where the layer has none, and
;      marks which cells have a tile to read
;   3  the vblank uploads the rows to the window's plane and reads those
;      tiles into the buffer, as many as fit in each vblank
;   4  ready: the composer types, and each cell a letter inks takes its
;      composed tile in the vblank its tile goes up —`msg_layer_ink`—
;   5  the vblank puts back the window's own rows of a line that carried
;      the layer for another box and does not now
;
; **And the window's bottom row**, the band of the arrow of a message
; waiting for a key in a map that keeps it in the window's cells —see
; `msg_bands`—: it takes the layer's entries with the line's, and the
; arrow's two cells give them back when it blinks off —`msg_layer_arrow`—.
;
; Meanwhile the composer waits —`msg_layer_wait`— and the HDMA keeps the
; line's band the map's —`msg_layer_vblank`—, so the band never shows the
; window's plane before it carries the layer.
;
; The cost, measured on A Blurred Line's maps 5 and 6 when it was written
; (2026-11-14): see the task `a-transparent-message-keeps-the-layer-above`
; in the-advocate-work.

.ifdef layer_text_on

.pushseg
.segment "FARBSS"
LAYER_ON:     .res 1            ; 1 while the line being composed carries it
LAYER_STEP:   .res 1            ; see above
LAYER_K:      .res 2            ; how many palettes down the text's copies are
LAYER_DIRTY:  .res 1            ; 1: `LAYER_ROWS` changed since they went up
LAYER_USED:   .res 1            ; the lines whose rows carry the layer, as `line_band`
LAYER_NEXT:   .res 1            ; the line the next step is for
LAYER_FETCH:  .res 1            ; the next cell whose tile is read, 0 to 59
LAYER_BITS:   .res 2            ; `msg_layer_ink`'s scratch
LAYER_ROW:    .res 1            ; and `entry`'s
LAYER_COL:    .res 2
LAYER_VADDR:  .res 2            ; the VRAM word of the rows in `LAYER_ROWS`
LAYER_MAPROW: .res 2            ; the layer's tilemap row of the line's first
LAYER_MAPCOL: .res 2            ; and its first column
LAYER_TILE0:  .res 2            ; the window's entry for the line's first text cell
LAYER_BG2:    .res 2            ; BG2's tile base, in words
LAYER_T:      .res 2            ; scratch
LAYER_INK:    .res WINDOW_TEXT_COLS ; per text column: bits 0 and 1 inked, top
                                ; and bottom; 2 and 3 its tile was read
LAYER_ROWS:   .res TEXT_WINDOW_COLS * 2 * 2 ; the line's two rows of the plane
LAYER_BOTTOM: .res TEXT_WINDOW_COLS * 2     ; and the window's bottom row
LAYER_MAPBOT: .res 2            ; the layer's tilemap row under that one
.popseg
.assert LAYER_BOTTOM = LAYER_ROWS + TEXT_WINDOW_COLS * 2 * 2, error, "the bottom row is read as a third row of `LAYER_ROWS`"

.pushseg
.segment "FAR3"
.a8
.i16

; The last line on which a tile is read: a DMA of 32 bytes and its setup
; take less than a line. Two of margin, as `upload_line`'s.
LAYER_LATEST = 261 - 1 - 2

; The start of each line, from `msg_line_rows` with its length read: whether
; it carries the layer, and the first step if so. Keeps X and Y.
.proc msg_layer_line
.a8
.i16
    php
    phx
    phy
    sep #$20
.a8
    lda #0
    sta f:LAYER_ON
    lda f:msg_line
    sta f:LAYER_NEXT
.if ::TEXT_INK_ENTRY = 0
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne off
    lda f:MSG_PLACE
    and #MSG_BARE
    beq off
    lda f:msg_length
    beq off
    lda pick_active
    bne off
    lda f:MSG_FACE_DRAW
    bne off
    ldx map_ofs
    lda f:map_table + M_VRAM_WINDOW_MAP + 1, x
    cmp f:MSG_SC
    bne off                     ; a big picture moved it
    lda f:screen_x
    and #7
    bne off
    lda scroll_y
    inc a
    and #7
    bne off
    rep #$20
.a16
    lda map_current
    tax
    sep #$20
.a8
    lda f:layer_texts, x
    beq off
    and #$7F                    ; bit 7: the layer's own palettes keep it
    sta f:LAYER_K
    lda #0
    sta f:LAYER_K + 1
    jsr setup
    bra done
.endif
off:
    ; The line's rows carry a copy of another box's: they go back to the
    ; window's own.
    lda f:msg_line
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:line_band, x
    cpx #0                      ; line 0: the box's bottom row too
    bne one_line
    ora #WINDOW_BAND_ARROW
one_line:
    and f:LAYER_USED
    beq done
    lda #5
    sta f:LAYER_STEP
done:
    ply
    plx
    plp
    rtl

; What the steps need, from the camera and the window as they are now.
setup:
    lda #1
    sta f:LAYER_ON
    sta f:LAYER_STEP
    ldx #WINDOW_TEXT_COLS - 1
    lda #0
clear:
    sta f:LAYER_INK, x
    dex
    bpl clear
    ; The window's entry for the line's first text cell: its tile —the
    ; window's base, the text's, the line's sixty— with the layer above's
    ; priority, which is what the converter's cells carry.
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$00F0
    xba                         ; BG2's base, in words
    sta f:LAYER_BG2
    lda f:map_table + M_VRAM_WINDOW, x
    sec
    sbc f:LAYER_BG2
    lsr a
    lsr a
    lsr a
    lsr a                       ; the window's first tile in BG2
    clc
    adc #WINDOW_TEXT_BASE
    sta f:LAYER_T
    lda f:msg_line
    and #$00FF
    sta f:LAYER_TILE0
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc f:LAYER_TILE0
    sbc f:LAYER_TILE0
    sbc f:LAYER_TILE0
    sbc f:LAYER_TILE0           ; line * 60
    clc
    adc f:LAYER_T
    ora #$2000                  ; `PRIORITY_ABOVE`
    sta f:LAYER_TILE0
    ; The screen's cell row of the line's top row, and the layer's tilemap
    ; row and column under the screen's first cell.
    lda f:MSG_PLACE
    and #MSG_WHERE
    asl a
    asl a
    tax
    lda f:place_rows, x
    and #$00FF
    lsr a
    lsr a
    lsr a
    clc
    adc #WINDOW_TEXT_ROW
    sta f:LAYER_T
    lda f:msg_line
    and #$00FF
    asl a
    clc
    adc f:LAYER_T
    sta f:LAYER_T
    lda scroll_y
    inc a
    lsr a
    lsr a
    lsr a
    clc
    adc f:LAYER_T
    and #31
    sta f:LAYER_MAPROW
    ; And the window's bottom row's.
    lda f:MSG_PLACE
    and #MSG_WHERE
    asl a
    asl a
    tax
    lda f:place_rows, x
    and #$00FF
    lsr a
    lsr a
    lsr a
    clc
    adc #WINDOW_ARROW_ROW
    sta f:LAYER_T
    lda scroll_y
    inc a
    lsr a
    lsr a
    lsr a
    clc
    adc f:LAYER_T
    and #31
    sta f:LAYER_MAPBOT
    lda f:screen_x
    lsr a
    lsr a
    lsr a
    and #63
    sta f:LAYER_MAPCOL
    sep #$20
.a8
    rts
.endproc

; From `msg_next`, before each letter: the carry set while the line's layer
; is not ready, and the composer types nothing. Step 2 is done here.
.proc msg_layer_wait
.a8
.i16
    lda f:LAYER_STEP
    beq ready
    cmp #4
    beq ready
    cmp #2
    beq cells
    sec
    rtl
ready:
    clc
    rtl
cells:
    phx
    phy
    ; Each text cell of both rows: the window's own entry where the layer
    ; has no tile, and where it has one, the mark that its tile is read.
    ; A flipped one is not: the composer cannot flip it, so a letter there
    ; goes over nothing, in the window's palette.
    ldy #0                      ; the column
column:
    rep #$20
.a16
    tya
    inc a
    asl a
    tax                         ; the top row's word of this column
    lda #0
    jsr one
    txa
    clc
    adc #TEXT_WINDOW_COLS * 2
    tax                         ; and the bottom's
    lda #1
    jsr one
    sep #$20
.a8
    iny
    cpy #WINDOW_TEXT_COLS
    bne column
    lda #0
    sta f:LAYER_FETCH
    lda #3
    sta f:LAYER_STEP
    ply
    plx
    sec
    rtl

; Row A (0 or 1) of column Y, whose word in `LAYER_ROWS` is at X. A16.
one:
.a16
    sta f:LAYER_T
    lda f:LAYER_ROWS, x
    and #$03FF
    bne has_tile
    ; The window's: the line's first entry, the row's thirty and the
    ; column.
    lda f:LAYER_T
    beq top
    lda #WINDOW_TEXT_COLS
top:
    sta f:LAYER_T
    tya
    clc
    adc f:LAYER_T
    adc f:LAYER_TILE0
    sta f:LAYER_ROWS, x
    rts
has_tile:
    lda f:LAYER_ROWS, x
    and #$C000
    bne flipped
    phx
    tyx
    sep #$20
.a8
    lda f:LAYER_T
    beq top_read
    lda #8
    bra mark
top_read:
    lda #4
mark:
    ora f:LAYER_INK, x
    sta f:LAYER_INK, x
    rep #$20
.a16
    plx
flipped:
    rts
.endproc


; The cells the letter just composed inked, from `ink_dirty` with
; `comp_glyph` and `comp_base` as `compose_char` left them: each one newly
; inked takes its composed tile, in the text's copy of the layer's palette
; if the layer's tile was read into it. A16 in and out; keeps X and Y.
.proc msg_layer_ink
.a16
.i16
    php
    phx
    phy
    sep #$20
.a8
    lda f:LAYER_STEP
    cmp #4
    bne done
    lda f:LAYER_ON
    beq done
    ; Which of its two cells and two rows the glyph inks: the composed
    ; tables say per row what is kept of each cell, all of it where nothing
    ; is drawn —see `compose_char`—. Bits 0 and 1 its cell's top and
    ; bottom, 2 and 3 the next one's.
    rep #$20
.a16
    lda #0
    sta f:LAYER_BITS
    ldy #0
    ldx #0                      ; the glyph's row
row:
    lda [comp_glyph], y
    cmp #$FFFF
    beq no_first
    jsr bit_of_row
    ora f:LAYER_BITS
    sta f:LAYER_BITS
no_first:
    tya
    clc
    adc #6
    tay
    lda [comp_glyph], y
    cmp #$FFFF
    beq no_second
    jsr bit_of_row
    asl a
    asl a
    ora f:LAYER_BITS
    sta f:LAYER_BITS
no_second:
    tya
    clc
    adc #6
    tay
    inx
    cpx #FONT_PRE_ROWS
    bne row
    ; Its cell, from the text area's left, and the next one.
    lda comp_base
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
.a8
    lda f:LAYER_BITS
    and #3
    jsr cell
    iny
    cpy #WINDOW_TEXT_COLS
    bcs done
    lda f:LAYER_BITS
    lsr a
    lsr a
    jsr cell
done:
    ply
    plx
    plp
    rtl

; The bit of glyph row X: 1 if it falls in the top cell row, 2 in the
; bottom one. A16.
bit_of_row:
.a16
    txa
    cmp #8 - TEXT_OFS_Y
    lda #1
    bcc in_top
    lda #2
in_top:
    rts

; Column Y, inked in the rows of A's bits 0 and 1: the rows newly inked
; take their composed entry. A8; keeps Y.
cell:
.a8
    phy
    tyx
    sta f:LAYER_T
    lda f:LAYER_INK, x
    and #3
    eor #$FF
    and f:LAYER_T
    beq unchanged
    sta f:LAYER_T
    ora f:LAYER_INK, x
    sta f:LAYER_INK, x
    lda f:LAYER_T
    lsr a
    bcc no_top
    pha
    lda #0
    jsr entry
    pla
no_top:
    lsr a
    bcc unchanged
    lda #1
    jsr entry
unchanged:
    ply
    rts

; The composed entry of column Y, row A: the window's tile for that cell,
; in the text's copy of the layer's palette if the layer's tile was read
; into it, and in the window's if not. A8; keeps X and Y.
entry:
.a8
    phx
    phy
    sta f:LAYER_ROW
    rep #$20
.a16
    tya
    sta f:LAYER_COL
    lda f:LAYER_ROW
    and #$00FF
    beq tile_top
    lda #WINDOW_TEXT_COLS       ; the bottom row's tiles are thirty further
tile_top:
    clc
    adc f:LAYER_COL
    adc f:LAYER_TILE0
    sta f:LAYER_T               ; the window's entry, palette 0
    lda f:LAYER_ROW
    and #$00FF
    beq word_top
    lda #TEXT_WINDOW_COLS       ; and the bottom row's words, a row further
word_top:
    sec                         ; past the column left of the text
    adc f:LAYER_COL
    asl a
    tax                         ; the cell's word in `LAYER_ROWS`
    phx
    lda f:LAYER_COL
    tax
    sep #$20
.a8
    lda f:LAYER_ROW
    beq read_top
    lda #8
    bra read
read_top:
    lda #4
read:
    and f:LAYER_INK, x
    plx
    cmp #0                      ; `plx` left Z from X
    rep #$20
.a16
    beq window
    ; The text's copy of the layer's palette: the layer's, K palettes down.
    lda f:LAYER_ROWS, x
    xba
    lsr a
    lsr a
    and #$0007
    sec
    sbc f:LAYER_K
    asl a
    asl a
    xba                         ; the palette, in bits 10 to 12
    ora f:LAYER_T
    sta f:LAYER_T
window:
    lda f:LAYER_T
    sta f:LAYER_ROWS, x
    sep #$20
.a8
    lda #1
    sta f:LAYER_DIRTY
    ply
    plx
    rts
.endproc

; From `msg_pace_vblank`, after the cells typed went up: the steps that
; touch VRAM. The carry set while the HDMA tables have to wait, so that the
; line's band does not turn on before the plane carries the layer.
.proc msg_layer_vblank
.a8
.i16
    ; The rows letters changed, with their tiles: not if those did not go
    ; up this vblank, which would show a cell pointing at a tile that is
    ; not there yet.
    lda f:LAYER_DIRTY
    beq no_dirty
    lda f:MSG_TYPED
    bne no_dirty
    lda f:msg_upload
    bne no_dirty
    jsr rows_up
    lda #0
    sta f:LAYER_DIRTY
no_dirty:
    lda f:LAYER_STEP
    cmp #1
    beq read
    cmp #2
    beq hold
    cmp #3
    beq fetch
    cmp #5
    bne free
    jmp restore
free:
    clc
    rtl
hold:
    sec
    rtl

read:
    jsr vaddr_next
    lda #$80
    sta f:VMAIN
    lda #$81                    ; from the PPU to the RAM, two registers
    sta f:DMAP0
    lda #<VMDATALREAD
    sta f:BBAD0
    lda #^LAYER_ROWS
    sta f:A1B0
    rep #$20
.a16
    lda f:LAYER_MAPROW
    ldx #0
    jsr read_row
    lda f:LAYER_MAPROW
    inc a
    and #31
    ldx #TEXT_WINDOW_COLS * 2
    jsr read_row
    lda f:LAYER_MAPBOT
    ldx #TEXT_WINDOW_COLS * 2 * 2
    jsr read_row
    sep #$20
.a8
    lda #2
    sta f:LAYER_STEP
    sec
    rtl

fetch:
    lda f:LAYER_FETCH
    bne fetching
    jsr rows_up                 ; the rows first, with the layer's entries
    jsr bottom_up               ; and the bottom row
    jsr line_bit
    ora #WINDOW_BAND_ARROW
    ora f:LAYER_USED
    sta f:LAYER_USED
fetching:
    lda #$80
    sta f:VMAIN
    lda #$81
    sta f:DMAP0
    lda #<VMDATALREAD
    sta f:BBAD0
    lda #0
    sta f:A1B0                  ; `text_buf` lives in bank 0
cell:
    lda f:LAYER_FETCH
    cmp #2 * WINDOW_TEXT_COLS
    bcc more
    jmp all
more:
    ; Its column and row.
    ldy #0
    cmp #WINDOW_TEXT_COLS
    bcc top
    sbc #WINDOW_TEXT_COLS       ; the carry is set
    iny
top:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:LAYER_INK, x
    cpy #0
    beq top_bit
    lsr a
top_bit:
    and #4
    beq next
    jsr clock
    bcs later
    ; The layer's tile, from VRAM, to the cell's place in the buffer.
    rep #$20
.a16
    txa
    sta f:LAYER_COL
    cpy #0
    beq word_top
    clc
    adc #TEXT_WINDOW_COLS
word_top:
    inc a
    asl a
    tax
    lda f:LAYER_ROWS, x
    and #$03FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:LAYER_BG2
    sta f:VMADDL
    jsr prefetched
    lda f:LAYER_COL
    asl a
    asl a
    asl a
    asl a
    asl a
    cpy #0
    beq buffer_top
    clc
    adc #WINDOW_TEXT_COLS * 32  ; the bottom row's tiles, past the top's
buffer_top:
    clc
    adc #.loword(text_buf)
    sta f:A1T0L
    lda #32
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
next:
    lda f:LAYER_FETCH
    inc a
    sta f:LAYER_FETCH
    jmp cell
all:
    lda #4
    sta f:LAYER_STEP
later:
    clc
    rtl

restore:
    jsr line_bit
    and f:LAYER_USED
    beq restore_bottom
    jsr vaddr_next
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda f:MSG_CELLS_PTR + 2
    sta f:A1B0
    rep #$20
.a16
    lda f:LAYER_NEXT
    and #$00FF
    asl a
    clc
    adc #TEXT_WINDOW_ROWS + WINDOW_TEXT_ROW
    xba
    lsr a
    lsr a                       ; times 64 bytes a row
    clc
    adc f:MSG_CELLS_PTR
    sta f:A1T0L
    lda f:LAYER_VADDR
    sta f:VMADDL
    lda #TEXT_WINDOW_COLS * 2 * 2
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    jsr line_bit
    eor #$FF
    and f:LAYER_USED
    sta f:LAYER_USED
restore_bottom:
    ; The bottom row, with the box's first line.
    lda f:LAYER_NEXT
    bne restored
    lda f:LAYER_USED
    and #WINDOW_BAND_ARROW
    beq restored
    lda f:MSG_CELLS_PTR + 2
    sta f:A1B0
    rep #$20
.a16
    lda f:MSG_CELLS_PTR
    clc
    adc #(TEXT_WINDOW_ROWS + WINDOW_ARROW_ROW) * TEXT_WINDOW_COLS * 2
    sta f:A1T0L
    jsr bottom_word
    sta f:VMADDL
    lda #TEXT_WINDOW_COLS * 2
    sta f:DAS0L
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    lda f:LAYER_USED
    and #$FF ^ WINDOW_BAND_ARROW
    sta f:LAYER_USED
restored:
    lda #0
    sta f:LAYER_STEP
    clc
    rtl

; The VRAM word of the window's bottom row in the plane without the frame.
; A16.
bottom_word:
.a16
    lda f:MSG_SC
    and #$00FC
    xba
    clc
    adc #(TEXT_WINDOW_ROWS + WINDOW_ARROW_ROW) * TEXT_WINDOW_COLS
    rts

; `LAYER_BOTTOM` to the window's bottom row. A8.
bottom_up:
.a8
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #^LAYER_BOTTOM
    sta f:A1B0
    rep #$20
.a16
    jsr bottom_word
    sta f:VMADDL
    lda #.loword(LAYER_BOTTOM)
    sta f:A1T0L
    lda #TEXT_WINDOW_COLS * 2
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rts

; `LAYER_VADDR` for line `LAYER_NEXT`: its two rows of the window's plane
; without the frame, ten rows below the framed one.
vaddr_next:
.a8
    rep #$20
.a16
    lda f:LAYER_NEXT
    and #$00FF
    asl a
    clc
    adc #TEXT_WINDOW_ROWS + WINDOW_TEXT_ROW
    asl a
    asl a
    asl a
    asl a
    asl a                       ; thirty-two words a row
    sta f:LAYER_VADDR
    lda f:MSG_SC
    and #$00FC
    xba
    clc
    adc f:LAYER_VADDR
    sta f:LAYER_VADDR
    sep #$20
.a8
    rts

; Line `LAYER_NEXT`'s bit, as `line_band`'s. A8.
line_bit:
.a8
    lda f:LAYER_NEXT
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:line_band, x
    rts

; `LAYER_ROWS` to the window's plane at `LAYER_VADDR`. A8.
rows_up:
.a8
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #^LAYER_ROWS
    sta f:A1B0
    rep #$20
.a16
    lda f:LAYER_VADDR
    sta f:VMADDL
    lda #.loword(LAYER_ROWS)
    sta f:A1T0L
    lda #TEXT_WINDOW_COLS * 2 * 2
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rts

; Row A of the layer's tilemap, from column `LAYER_MAPCOL` on for
; thirty-two, to `LAYER_ROWS` at byte X: the tilemap is two 32x32 screens
; side by side, so it is two pieces, the second from the other screen's
; left edge. A16, with the DMA's channel set up.
read_row:
.a16
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:LAYER_T               ; the row's first word in a screen
    txa
    clc
    adc #.loword(LAYER_ROWS)
    sta f:A1T0L
    lda f:LAYER_MAPCOL
    and #31
    sta f:LAYER_COL             ; the column inside its screen
    lda f:LAYER_MAPCOL
    and #32
    asl a
    asl a
    asl a
    asl a
    asl a                       ; the screen: $400 words each
    pha
    clc
    adc f:LAYER_T
    adc f:LAYER_COL
    adc #VRAM_ABOVE_MAP
    sta f:VMADDL
    jsr prefetched
    lda #32
    sec
    sbc f:LAYER_COL
    asl a
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    pla
    eor #$0400                  ; the other screen, from its left edge
    clc
    adc f:LAYER_T
    adc #VRAM_ABOVE_MAP
    sta f:VMADDL
    jsr prefetched
    lda f:LAYER_COL
    asl a
    beq one_piece               ; zero bytes would be 64 KB
    sta f:DAS0L                 ; `A1T0L` went on past the first piece
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
one_piece:
    rts

; After writing VMADD for a read, the word that comes twice, read and
; thrown away: the first read loads the prefetch again from the same
; address before moving on —see `keep` in menu_list.s—, and without it the
; row lands one cell to the right. A16, which it keeps.
prefetched:
.a16
    sep #$20
.a8
    lda f:VMDATALREAD
    lda f:VMDATALREAD + 1
    rep #$20
.a16
    rts

; The carry set if the vblank is too far along for one more tile: as
; `upload_line`'s, with its own last line. A8.
clock:
.a8
    lda f:STAT78                ; resets the counters' flip-flop
    lda f:SLHV                  ; latches them
    lda f:OPVCT
    xba
    lda f:OPVCT
    and #$01                    ; the ninth bit; the rest is open bus
    xba
    rep #$20
.a16
    cmp #LAYER_LATEST + 1
    bcs late
    cmp #LINES + 1              ; on the screen's lines: the vblank is over
    bcc late
    sep #$20
.a8
    clc
    rts
late:
    sep #$20
.a8
    sec
    rts
.endproc

; From `msg_arrow`, which just wrote the arrow's cells, with VMAIN at
; $80: off, in a window without its background whose bottom row carries the
; layer, they are the layer's and not the window's blank ones. Keeps X and Y.
.proc msg_layer_arrow
.a8
.i16
    lda f:MSG_ARROW_UP
    bne done
    lda f:MSG_PLACE
    and #MSG_BARE
    beq done
    lda f:LAYER_USED
    and #WINDOW_BAND_ARROW
    beq done
    phx
    rep #$20
.a16
    lda f:MSG_SC
    and #$00FC
    xba
    clc
    adc #(TEXT_WINDOW_ROWS + WINDOW_ARROW_ROW) * TEXT_WINDOW_COLS + WINDOW_ARROW_COL
    sta f:VMADDL
    ldx #0
cell:
    lda f:LAYER_BOTTOM + WINDOW_ARROW_COL * 2, x
    sta f:VMDATAL
    inx
    inx
    cpx #WINDOW_ARROW_CELLS * 2
    bne cell
    sep #$20
.a8
    plx
done:
    rtl
.endproc

; The text's copies of the layer's palettes, in `cgram_shadow`, from what
; `apply_tint` just left there: the layer's colours tinted, and at the
; text's entries —`LAYER_TEXT_ENTRIES`— the window's, untinted, from its
; palette in the ROM. In a map whose layer keeps the text in its own
; palettes —bit 7 of its `layer_texts`, no copies— the same over those:
; no pixel of the layer uses the text's entries there. From the end of `apply_tint`, so that every tint and
; every load builds them. Keeps nothing.
.proc layer_text_tint
.a8
.i16
    rep #$20
.a16
    lda map_current
    tax
    sep #$20
.a8
    lda f:layer_texts, x
    bne some
    rtl
some:
    rep #$20
.a16
    and #$007F
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:LAYER_BITS            ; how far down the copies are, in bytes: 0
                                ; when the layer's own palettes keep the text
    ldx map_ofs
    lda f:map_table + M_ABOVE_FIRST, x
    and #$00FF
    asl a
    sta f:LAYER_T               ; the layer's first byte in the shadow
    lda #2 * 128
    sec
    sbc f:LAYER_T
    sta f:LAYER_COL             ; and its palettes' bytes, up to the sprites'
    win_lo window_cgram, WS_CGRAM
    sta tint_ptr
    sep #$20
.a8
    win_bank window_cgram, WS_CGRAM
    sta tint_ptr + 2
    rep #$20
.a16
    ldx #0                      ; the byte, in the layer's and in the copies'
each:
    txa
    and #$001F
    tay                         ; inside its palette
    phx
    tyx
    lda f:entry_bits, x
    plx
    and #LAYER_TEXT_ENTRIES
    beq layer
    lda [tint_ptr], y           ; the window's, untinted
    bra put
layer:
    phx
    txa
    clc
    adc f:LAYER_T
    tax
    lda f:cgram_shadow, x       ; the layer's, tinted
    plx
put:
    phx
    pha
    txa
    clc
    adc f:LAYER_T
    sec
    sbc f:LAYER_BITS            ; the copies, K palettes down
    tax
    pla
    sta f:cgram_shadow, x
    plx
    inx
    inx
    txa
    cmp f:LAYER_COL
    bne each
    sep #$20
.a8
    rtl
.endproc

; Each entry of a palette's bit, by its byte.
entry_bits:
    .word $0001, $0002, $0004, $0008, $0010, $0020, $0040, $0080
    .word $0100, $0200, $0400, $0800, $1000, $2000, $4000, $8000

; The copies to CGRAM, from `cgram_shadow` and never from the flash's
; `pal_buf`: the letters do not flash —RM2k's window does not—, and
; `pal_buf` has nothing there. From `upload_palettes`. Keeps nothing.
.proc layer_text_upload
.a8
.i16
    rep #$20
.a16
    lda map_current
    tax
    sep #$20
.a8
    lda f:layer_texts, x
    and #$7F                    ; no copies: the layer's own went up already
    beq done
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:DAS0L
    sta f:LAYER_T
    ldx map_ofs
    lda f:map_table + M_ABOVE_FIRST, x
    and #$00FF
    asl a
    sec
    sbc f:LAYER_T               ; the copies' first byte
    pha
    clc
    adc #.loword(cgram_shadow)
    sta f:A1T0L
    pla
    lsr a
    sep #$20
.a8
    sta f:CGADD
    lda #0
    sta f:A1B0                  ; the shadow lives in bank 0
    sta f:DMAP0                 ; one register, byte by byte
    lda #$22
    sta f:BBAD0                 ; CGDATA
    lda #$01
    sta f:MDMAEN
done:
    rtl
.endproc

.popseg
.endif
