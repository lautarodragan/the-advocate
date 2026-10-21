; --- the gold window, and the option nobody can pick: `ShowInn` -----------------
;
; RM2k's inn opens a `Window_Gold` next to its greeting —88x32 at the
; screen's right edge, at the top, or at the bottom when the message is at
; the top— and pushes its "Yes" with `can_afford`: without the price the
; option is drawn in `Font::ColorDisabled` and A on it does nothing but the
; buzzer, the choice staying open. Cancel is "No", which is never greyed.
; The event compiler puts two phases of `OP_INN` before the greeting —3,
; the gold window and "Yes" greyed, and 4, which a gold branch reaches only
; with the price paid for, the grey off— and this is what they start. See
; `compile_inn` in rm2k-snes-events.
;
; **The gold window is 44 8x8 objects**, where the message arrow goes as
; objects: past the map's sprite bank, after the arrow's two tiles, in the
; sprite palette nobody takes —`arrow_objs`, whose bit 14 says the gold
; window fits too, decided by `arrow_obj` in rm2k-snes-mapdata—. A map
; without that room shows no gold window, and the build says so. Mode 3 has
; no other layer: BG2 is the map's layer above everywhere but on the
; window's own lines.
;
; Its pieces are each System's `window_gold`: the empty window with the gold
; term already written, as RM2k's `DrawCurrencyValue` writes it, the fifteen
; colours of its sprite palette —the window's own and what the term adds—
; and the twelve entries a greyed option's glyph rows take. The number is
; composed here, with the window's font tables, into a copy of the two
; middle rows of tiles when a box opens, and the four rows go up one per
; vblank of the box's lines, before the window appears: see `gold_begin`
; and `gold_vblank`.
;
; **The grey is a recolour, letter by letter**: the window's letters come
; composed with their colour —`font_pre*`, 117 KB— and a second set would
; double them, so each letter just composed on a greyed line has its glyph's
; pixels —not its shadow's, not the bar's under it— moved to the window
; palette's entries nearest to System colour 3. The palette has no room for
; a grey of its own: the maps' backgrounds start right after it.
;
; All of it in FAR3, reached from bank 0 by the composer, the choice's pick
; and `op_inn`, and from FAR3 by the face's and the arrow's hooks. The data
; bank is the caller's, which reaches the registers: what is in RAM goes
; with `f:` or through the direct page.

.segment "FAR3"
.a8
.i16

GOLD_COLS = GOLD_WIDTH / 8
GOLD_ROWS = GOLD_HEIGHT / 8
GOLD_ROW_BYTES = GOLD_COLS * 32
GOLD_TILES = GOLD_COLS * GOLD_ROWS

.pushseg
.segment "FARBSS"
GOLD_ON:    .res 1              ; 1 from `OP_INN 3` until the choice is picked
CHOICE_OFF: .res 1              ; the greyed options, bit k for option k
GOLD_OBJ:   .res 2              ; the map's word of `arrow_objs` when it opened
GOLD_UP:    .res 1              ; the rows of tiles left to go up
GOLD_READY: .res 1              ; 1 once the four went up for this box
GOLD_SHOWN: .res 1              ; 1 while its objects go in the OAM
GOLD_SRC:   .res 3              ; the current System's `window_gold`
GOLD_INK:   .res 12             ; its greyed glyph rows' entries
GOLD_NUM:   .res 3              ; the gold being written, divided as it goes
GOLD_DIGIT: .res 8              ; and its digits, as letters, the last first
GOLD_X:     .res 2              ; where the next digit to the left ends
GOLD_AT:    .res 2              ; scratch: a byte of a buffer, or a tile
GOLD_KEEP:  .res 2              ; scratch: what a glyph's row keeps, a letter
GOLD_Y:     .res 1              ; scratch: a pixel row, or a count
GREY_C:     .res 1              ; a greyed row's colour,
GREY_FLIP:  .res 1              ; the planes its grey flips,
GREY_SET:   .res 1              ; and the pixels of its glyph in a cell
GOLD_BUF:   .res GOLD_ROW_BYTES * 2 ; rows 1 and 2, with the number
.popseg

; Where each part of `window_gold` starts: the tiles, the palette, the ink.
GOLD_CGRAM_AT = GOLD_TILES * 32
GOLD_INK_AT = GOLD_CGRAM_AT + 15 * 2
; At the screen's right edge, and at its top or its bottom: an object's Y is
; the line it starts on, as the arrow's.
GOLD_LEFT = 256 - GOLD_WIDTH
GOLD_TOP = PLACE_TOP
GOLD_LOW = LINES - GOLD_HEIGHT
; Bit 14 of the map's `arrow_objs` word: `GOLD_ROOM` in record.rs.
GOLD_ROOM_BIT = $40
; The byte of `GOLD_BUF` where the number's first pixel row starts: the
; buffer is rows 1 and 2, `GOLD_ROW_BYTES` each, and a pixel row of a tile is
; two bytes —planes 0 and 1; 2 and 3 are sixteen further—.
GOLD_AT0 = ((GOLD_TEXT_Y >> 3) - 1) * GOLD_ROW_BYTES + (GOLD_TEXT_Y & 7) * 2
.assert GOLD_ROWS = 4 && GOLD_TEXT_Y >= 8 && GOLD_TEXT_Y + FONT_PRE_ROWS <= 24, error, "the gold window's number is not in its two middle rows"
.assert GOLD_TILES = 44, error, "the gold window is not GOLD_OBJ_TILES in record.rs"

; `OP_INN` 3 and 4, from `inn_phase` with the phase in A: 3 opens the gold
; window with the boxes that follow and greys option 0, 4 takes the grey
; off. Returns as `inn_phase` does to go on, V and carry clear. Keeps Y.
.proc inn_gold
.a8
.i16
    cmp #3
    bne paid
    lda #1
    sta f:GOLD_ON
    sta f:CHOICE_OFF
    ; The current System's pieces, and its grey to where `msg_ink_char`
    ; reads it: the System does not change while the inn asks.
    jsr gold_source
    phy
    rep #$20
.a16
    lda #GOLD_INK_AT
    ldx #.loword(GOLD_INK)
    ldy #12
    jsr gold_to_wram
    sep #$20
.a8
    ply
    bra done
paid:
    lda #0
    sta f:CHOICE_OFF
done:
    clv
    clc
    rtl
.endproc

; `GOLD_SRC` to the current System's `window_gold`.
.proc gold_source
.a8
.i16
    rep #$20
.a16
    win_lo window_gold, WS_GOLD
    sta f:GOLD_SRC
    sep #$20
.a8
    win_bank window_gold, WS_GOLD
    sta f:GOLD_SRC + 2
    rts
.endproc

; Y bytes of `window_gold`, from its offset A16, to far RAM at X —bank $7E—,
; by DMA through WRAM's port on bus B, as `prime_line` copies ROM to RAM.
; Comes back in A16.
.proc gold_to_wram
.a16
.i16
    clc
    adc f:GOLD_SRC
    sta A1T0L
    stx WMADDL
    sty DAS0L
    sep #$20
.a8
    stz WMADDH                  ; $7E: FARBSS is `$7E2000-$7E7FFF`
    lda f:GOLD_SRC + 2
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #<WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    rts
.endproc

; A choice picked, from `choice_tick` with the option in `pick_sel`: the page
; to its body, the window closed. Returns A at 1 and Z clear, or A at 0 and Z
; set if A was pressed on a greyed option, which RM2k refuses with its
; buzzer —not played here, like every System sound— and the choice stays
; open. Cancel always picks: `choice_cancel_type` does not look at it.
;
; It was the end of `choice_tick`, in bank 0, until the grey came.
.proc choice_pick
.a8
.i16
    lda pick_edges
    and #PAD_B
    bne picks                   ; cancel
    lda pick_sel
    jsr greyed
    bcc picks
    lda #0
    rtl
picks:
    lda pick_sel
    asl
    asl
    rep #$20
.a16
    and #$00FF
    clc
    adc pick_table
    inc a
    inc a                       ; the destination comes after the box
    tay
    lda [code_ptr], y
    sta ev_cur
    sep #$20
.a8
    stz pick_active
    lda #0
    sta f:msg_open              ; and with that `flush_video` turns HDMA off
    ; And the inn's gold window and grey go with the choice.
    sta f:GOLD_ON
    sta f:CHOICE_OFF
    sta f:GOLD_SHOWN
    lda #1
    rtl
.endproc

; Carry set if option A is greyed. Keeps Y.
.proc greyed
.a8
.i16
    cmp #8
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:CHOICE_OFF
shift:
    lsr a                       ; bit X goes out last, into the carry
    dex
    bpl shift
    rts
no:
    clc
    rts
.endproc

; The letter `compose_char` just composed, in grey if its line is a greyed
; option, or in the box's colour if it is not 0 —`\c[n]`, see
; message_pace.s—: from `message_tick`, with `comp_glyph` and `comp_base` as
; it left them. For each of the glyph's twelve rows and the two cells it can
; step on, the pixels the letter set —not kept, see `font_prerender`— and of
; the glyph's colour —not the shadow's— have their planes flipped to the
; entry `MSG_INK_ROWS` gives that row: the glyph goes over whatever was
; there, so its pixels in the buffer are exactly those. And the cells it
; touched are noted for a box being typed. Leaves A8, and X and Y anything.
.proc msg_ink_char
.a8
.i16
    rep #$20
.a16
    jsr ink_dirty               ; message_pace.s
    sep #$20
.a8
    lda f:CHOICE_OFF
    beq coloured
    lda pick_active
    cmp #PICK_CHOICE
    bne coloured
    lda f:msg_line
    jsr greyed
    bcc coloured
    ; The grey's rows where the colour's go: an option has no colour.
    ldx #11
copy:
    lda f:GOLD_INK, x
    sta f:MSG_INK_ROWS, x
    dex
    bpl copy
    bra grey
coloured:
    lda f:MSG_COLOUR
    bne grey
    rtl
grey:
    ldy #0                      ; into the glyph's data: row by row, two cells
    lda #0
    sta f:GOLD_Y                ; the glyph's row
row:
    ; Its colour, and which planes its grey flips.
    lda f:GOLD_Y
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:font_color, x
    sta f:GREY_C
    eor f:MSG_INK_ROWS, x
    sta f:GREY_FLIP
    ; The buffer byte where this row starts, as `compose_char` has it.
    lda f:GOLD_Y
    clc
    adc #TEXT_OFS_Y
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    lda f:row_buf_table, x
    clc
    adc comp_base
    sta f:GOLD_AT
    sep #$20
.a8
    jsr grey_cell
    rep #$20
.a16
    lda f:GOLD_AT
    clc
    adc #32                     ; the neighbouring cell
    sta f:GOLD_AT
    sep #$20
.a8
    jsr grey_cell
    lda f:GOLD_Y
    inc a
    sta f:GOLD_Y
    cmp #FONT_HEIGHT            ; the thirteenth row is only shadow
    bcc row
    rtl
.endproc

; One cell of one glyph row for `msg_ink_char`: Y on its three words in the
; glyph's data —it leaves Y past them—, the buffer byte in `GOLD_AT`, the
; row's colour and flips in `GREY_C` and `GREY_FLIP`.
.proc grey_cell
.a8
.i16
    rep #$20
.a16
    lda [comp_glyph], y         ; what is kept: the rest is the letter's
    iny
    iny
    eor #$FFFF
    sep #$20
.a8
    sta f:GREY_SET
    lda f:GREY_FLIP
    beq skip                    ; the grey is the same entry
    lda f:GREY_SET
    bne set
skip:
    iny
    iny
    iny
    iny
    rts
set:
    ; Of those, the glyph's: each plane's bit as the colour's. Planes 0 and
    ; 1 are the low and high bytes of the first word, 2 and 3 of the second.
    ldx #0
plane:
    lda f:GREY_C
    and f:plane_bit, x
    beq off
    lda [comp_glyph], y
    bra matched
off:
    lda [comp_glyph], y
    eor #$FF
matched:
    and f:GREY_SET
    sta f:GREY_SET
    iny
    inx
    cpx #4
    bne plane
    ; And the planes that flip, flipped on those pixels, in the buffer.
    phy
    ldx #0
flip:
    lda f:GREY_FLIP
    and f:plane_bit, x
    beq kept
    phx
    txa
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    lda f:GOLD_AT
    clc
    adc f:plane_offset, x
    tax
    sep #$20
.a8
    lda f:text_buf, x
    eor f:GREY_SET
    sta f:text_buf, x
    plx
kept:
    inx
    cpx #4
    bne flip
    ply
    rts
.endproc

plane_bit:
    .byte $01, $02, $04, $08
; Where each plane's byte is from a pixel row's first, in a 4bpp tile.
plane_offset:
    .word 0, 1, 16, 17

; A box opens, from `msg_face_begin`: if the inn asked for its gold window
; and the map has room for it, the number into its tiles and the four rows
; to go up with the box's lines. Without room, or under a big picture —whose
; tiles go over the sprite bank—, the box opens without it.
.proc gold_begin
.a8
.i16
    lda #0
    sta f:GOLD_SHOWN
    sta f:GOLD_UP
    sta f:GOLD_READY
    lda f:GOLD_ON
    beq done
    lda f:BIG_FLAGS
    and #BIG_ON
    bne done
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:arrow_objs, x
    sta f:GOLD_OBJ
    sep #$20
.a8
    lda f:GOLD_OBJ + 1
    and #GOLD_ROOM_BIT
    beq done
    jsr gold_compose
    lda #GOLD_ROWS
    sta f:GOLD_UP
done:
    rts
.endproc

; The two middle rows of the empty window to `GOLD_BUF`, and the party's
; gold written into them, right-aligned at `GOLD_RIGHT`: the digits from the
; last one leftwards, each a letter of the window's font, at its own x.
.proc gold_compose
.a8
.i16
    rep #$20
.a16
    lda #GOLD_ROW_BYTES
    ldx #.loword(GOLD_BUF)
    ldy #(GOLD_ROW_BYTES * 2)
    jsr gold_to_wram
    sep #$20
.a8
    ; The digits: 24 bits divided by ten a byte at a time, as the shop's.
    lda f:gold
    sta f:GOLD_NUM
    lda f:gold + 1
    sta f:GOLD_NUM + 1
    lda f:gold + 2
    sta f:GOLD_NUM + 2
    ldy #0                      ; how many digits
digit:
    lda #0
    sta f:GOLD_Y                ; the remainder carried along
    ldx #2
divide:
    lda f:GOLD_NUM, x
    sta WRDIVL
    lda f:GOLD_Y
    sta WRDIVH
    lda #10
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta f:GOLD_NUM, x
    lda RDMPYL
    sta f:GOLD_Y
    dex
    bpl divide
    lda f:GOLD_Y
    clc
    adc #('0' - ' ')            ; a letter of the font
    phx
    tyx
    sta f:GOLD_DIGIT, x
    plx
    iny
    lda f:GOLD_NUM
    ora f:GOLD_NUM + 1
    ora f:GOLD_NUM + 2
    bne digit
    ; And each into the buffer, the last first, leftwards from the edge.
    rep #$20
.a16
    lda #GOLD_RIGHT
    sta f:GOLD_X
    sep #$20
.a8
    ldx #0
each:
    phx
    phy
    lda f:GOLD_DIGIT, x
    jsr gold_glyph
    ply
    plx
    inx
    dey
    bne each
    rts
.endproc

; Letter A into `GOLD_BUF`, ending at `GOLD_X`, which it moves left by the
; letter's advance: the window's composed tables, read as `compose_char`
; reads them, written into the two rows' own layout —eleven tiles a row—.
.proc gold_glyph
.a8
.i16
    sta f:GOLD_KEEP
    sta WRMPYA
    lda #FONT_PRE_CHAR
    sta WRMPYB                  ; starts: what follows gives it the cycles
    ; Where it starts: the edge minus its advance.
    lda #0
    xba
    lda f:GOLD_KEEP
    rep #$20
.a16
    tax
    lda f:font_advance, x
    and #$00FF
    sta f:GOLD_AT
    lda f:GOLD_X
    sec
    sbc f:GOLD_AT
    sta f:GOLD_X
    ; Its phase's table, plus the letter times FONT_PRE_CHAR.
    and #$0007
    asl a
    tax                         ; twice the phase
    lda f:font_pre_lo, x
    clc
    adc RDMPYL
    sta comp_glyph
    sep #$20
.a8
    lda f:font_pre_bk, x
    sta comp_glyph + 2
    ; The cell column's first byte, and the number's first pixel row's.
    rep #$20
.a16
    lda f:GOLD_X
    lsr a
    lsr a
    lsr a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 bytes per tile
    clc
    adc #GOLD_AT0
    sta f:GOLD_AT
    sep #$20
.a8
    lda #GOLD_TEXT_Y
    sta f:GOLD_Y
    ldy #0
row:
    jsr gold_cell
    rep #$20
.a16
    lda f:GOLD_AT
    clc
    adc #32
    sta f:GOLD_AT
    sep #$20
.a8
    jsr gold_cell
    ; The next pixel row: two bytes on, back from the neighbouring cell,
    ; and into the next row of tiles past a tile's eighth.
    rep #$20
.a16
    lda f:GOLD_AT
    sec
    sbc #30
    sta f:GOLD_AT
    sep #$20
.a8
    lda f:GOLD_Y
    inc a
    sta f:GOLD_Y
    and #7
    bne same_tile
    rep #$20
.a16
    lda f:GOLD_AT
    clc
    adc #(GOLD_ROW_BYTES - 16)
    sta f:GOLD_AT
    sep #$20
.a8
same_tile:
    lda f:GOLD_Y
    cmp #(GOLD_TEXT_Y + FONT_PRE_ROWS)
    bcc row
    rts
.endproc

; One cell of one row of `gold_glyph`: Y on its three words, which it leaves
; past them, and `GOLD_AT` on the buffer's byte: what is kept and what is
; set, in planes 0-1 and, sixteen bytes on, 2-3.
.proc gold_cell
.a8
.i16
    rep #$20
.a16
    lda [comp_glyph], y
    iny
    iny
    cmp #$FFFF
    beq none
    sta f:GOLD_KEEP
    lda f:GOLD_AT
    tax
    lda f:GOLD_BUF, x
    and f:GOLD_KEEP
    ora [comp_glyph], y
    sta f:GOLD_BUF, x
    iny
    iny
    lda f:GOLD_BUF + 16, x
    and f:GOLD_KEEP
    ora [comp_glyph], y
    sta f:GOLD_BUF + 16, x
    iny
    iny
    sep #$20
.a8
    rts
none:
.a16
    iny
    iny
    iny
    iny
    sep #$20
.a8
    rts
.endproc

; The four rows of tiles, one per vblank in which the composer uploads a
; line: from `msg_face_vblank`. Rows 0 and 3 from the cartridge, 1 and 2
; from `GOLD_BUF`, to the tiles after the arrow's two.
.proc gold_vblank
.a8
.i16
    lda f:GOLD_UP
    bne up
    rts
up:
    lda #GOLD_ROWS
    sec
    sbc f:GOLD_UP
    rep #$20
.a16
    and #$00FF
    asl a
    tax                         ; the row, times two
    ; Where: its first tile, sixteen words each, from the sprites' base.
    lda f:GOLD_OBJ
    and #$01FF
    clc
    adc #ARROW_OBJ_TILES
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:gold_row_words, x
    phx
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    plx
    sta VMADDL
    lda #GOLD_ROW_BYTES
    sta DAS0L
    ; From where: the cartridge's, or the buffer's with the number.
    lda f:gold_row_from, x
    bmi from_rom
    clc
    adc #.loword(GOLD_BUF)
    sta A1T0L
    sep #$20
.a8
    lda #^GOLD_BUF
    bra source
from_rom:
.a16
    and #$7FFF
    clc
    adc f:GOLD_SRC
    sta A1T0L
    sep #$20
.a8
    lda f:GOLD_SRC + 2
source:
    sta A1B0
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda f:GOLD_UP
    dec a
    sta f:GOLD_UP
    bne more
    lda #1
    sta f:GOLD_READY
more:
    rts
.endproc

gold_row_words:
    .word 0, GOLD_COLS * 16, GOLD_COLS * 16 * 2, GOLD_COLS * 16 * 3
; Bit 15 for the cartridge's, with the row's offset in `window_gold`; the
; buffer's offset without it.
gold_row_from:
    .word $8000, 0, GOLD_ROW_BYTES, $8000 + GOLD_ROW_BYTES * 3

; When the window appears, from `arrow_obj_choose` in the vblank: the gold
; window shows if its rows went up for this box and the window's tilemap is
; the map's —a big picture moves it, and puts its tiles over the sprite
; bank—, and its fifteen colours go to the arrow's sprite palette: the
; window's own, which are the arrow's too, and the term's after them.
.proc gold_choose
.a8
.i16
    lda #0
    sta f:GOLD_SHOWN
    lda f:GOLD_READY
    beq done
    lda f:GOLD_ON
    beq done
    ldx map_ofs
    lda f:map_table + M_VRAM_WINDOW_MAP + 1, x
    cmp f:MSG_SC
    bne done
    lda f:GOLD_OBJ + 1
    and #$0E                    ; the palette, times two
    asl a
    asl a
    asl a
    ora #$81                    ; the sprites' half, past the transparent
    sta CGADD
    rep #$20
.a16
    lda f:GOLD_SRC
    clc
    adc #GOLD_CGRAM_AT
    sta A1T0L
    lda #(15 * 2)
    sta DAS0L
    sep #$20
.a8
    lda f:GOLD_SRC + 2
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #<CGDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #1
    sta f:GOLD_SHOWN
done:
    rts
.endproc

; Its 44 objects, from `arrow_oam` with a window on screen, while it shows:
; in front of everything but the timer, as the window is in RM2k. At the
; top of the screen, or at its bottom when the window is at the top.
.proc gold_oam
.a8
.i16
    lda f:GOLD_SHOWN
    bne shows
    rts
shows:
    lda #0
    sta f:obj_big               ; 8x8
    rep #$20
.a16
    lda #GOLD_TOP
    sta obj_y
    sep #$20
.a8
    lda f:MSG_PLACE
    and #MSG_WHERE
    bne placed                  ; 0 is the top
    rep #$20
.a16
    lda #GOLD_LOW
    sta obj_y
placed:
    rep #$20
.a16
    lda f:GOLD_OBJ
    clc
    adc #ARROW_OBJ_TILES
    sta f:GOLD_AT               ; the tile, with the palette above it
    sep #$20
.a8
    lda #GOLD_ROWS
    sta f:GOLD_Y
each_row:
    rep #$20
.a16
    lda #GOLD_LEFT
    sta obj_x
    sep #$20
.a8
    ldx #GOLD_COLS
each:
    phx
    lda f:GOLD_AT
    sta obj_tile
    lda f:GOLD_AT + 1
    and #$0F                    ; vhoopppN: the palette and the ninth bit,
    ora #$30                    ; and priority 3, in front of everything
    sta obj_attr
    jsl f:emit_object_far + FAST
    rep #$20
.a16
    lda f:GOLD_AT
    inc a                       ; the next tile, its ninth bit included
    sta f:GOLD_AT
    lda obj_x
    clc
    adc #8
    sta obj_x
    sep #$20
.a8
    plx
    dex
    bne each
    rep #$20
.a16
    lda obj_y
    clc
    adc #8
    sta obj_y
    sep #$20
.a8
    lda f:GOLD_Y
    dec a
    sta f:GOLD_Y
    bne each_row
    lda #$02                    ; and whatever follows is 32x32 again
    sta f:obj_big
    rts
.endproc

; Nothing of it at the reset: from `msg_face_clear`.
.proc gold_clear
.a8
.i16
    lda #0
    sta f:GOLD_ON
    sta f:CHOICE_OFF
    sta f:GOLD_UP
    sta f:GOLD_READY
    sta f:GOLD_SHOWN
    rts
.endproc
