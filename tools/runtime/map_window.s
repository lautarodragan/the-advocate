.segment "CODE"

; --- the map's moving window ----------------------------------------------------
; The PPU's tilemap is 64x32 cells and the game's maps go up to 1000x80: the
; whole map is never in VRAM. What there is is a window treated as a torus
; —cell (mx,my) always lives in slot (mx mod 64, my mod 32)— and kept up by
; rewriting the column or the row that just came on screen. The one leaving is
; 32 columns or 4 rows outside, so nobody sees it while it is overwritten.
;
; The hardware scroll wraps by itself: the register is 10 bits, that is, 1024
; pixels, and 1024 is a multiple of the 512 the window measures across. The
; camera position is written to it as is and lands where it should.
;
; What comes out of the ROM is not a tilemap but a grid of blocks: RM2k's 16x16
; cell, which is the unit the game was drawn with and which repeats a great
; deal. The block carries its four background cells, its four upper-layer cells
; and its passability, all together. Storing it like that is what takes the
; largest map from 175 KB —more than the whole ROM— down to 40.

; The grid reaches 40 KB and does not fit in a bank, so it is walked with a
; 24-bit pointer. It lives in the upper half of the two WRAM banks —see
; `GRID`—, which has the same shape as a LoROM bank: going past $FFFF does
; not lead to the next bank's $0000 but to its $8000, and these two routines
; are the only ones that know that. It was like this when the grid was read
; from the cartridge, and that is why moving it to WRAM touched nobody else.
.proc ptr_more
.a16
.i16
    clc
    adc cells_ptr
    sta cells_ptr
    bcc ready
    clc
    adc #$8000
    sta cells_ptr
    sep #$20
.a8
    lda cells_ptr + 2
    inc a
    sta cells_ptr + 2
    rep #$20
.a16
ready:
    rts
.endproc

.proc ptr_minus
.a16
.i16
    eor #$FFFF                  ; subtracting is adding the complement
    sec
    adc cells_ptr
    cmp #$8000
    bcs saves                   ; still inside the bank's upper half
    clc
    adc #$8000
    sta cells_ptr
    sep #$20
.a8
    lda cells_ptr + 2
    dec a
    sta cells_ptr + 2
    rep #$20
.a16
    rts
saves:
    sta cells_ptr
    rts
.endproc

.proc ptr_from_cells
.a16
.i16
    lda cells
    sta cells_ptr
    sep #$20
.a8
    lda cells + 2
    sta cells_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_to_cells
.a16
.i16
    lda cells_ptr
    sta cells
    sep #$20
.a8
    lda cells_ptr + 2
    sta cells + 2
    rep #$20
.a16
    rts
.endproc

; A = the block the grid says; returns with the one to use, which is different
; only if some `TileSubstitution` changed it. **Everyone** who reads a cell
; goes through here: the two strips and the passability, which in this port
; travels inside the block. Passability following the substitution is what
; RM2k does: `IsPassableLowerTile` looks at `map_info.lower_tiles` before
; `passages_down`.
;
; It uses Y, which is free in all three callers: the two that build strips load
; it right after with the block's offset, and `pass_of_ptr` too. X is not
; touched, and there it does matter: it is the strip's slot.
;
; With no substitutions set —the 328 maps of today's game— it is four cycles
; and a branch, which is what it cost to put it on the hot path.
.proc cell_replaced
.a16
.i16
    ldy sub_n
    beq ready
seek:
    dey
    dey
    cmp sub_key, y
    beq found
    cpy #$0000
    bne seek
    rts
found:
    lda sub_value, y
ready:
    rts
.endproc

; Builds column X of the map —in 8x8 cells— and leaves in col_addr where it
; goes.
;
; All 32 rows of the window are filled, not the 29 that are visible. Each row's
; slot is fixed, row mod 32, so writing extra cannot overwrite anything being
; looked at, and it saves keeping track of which part of the column was
; already right.
.proc build_column
.a16
.i16
    stz col_addr
    cpx map_cw
    bcc inside
    rts                         ; past the edge: nothing to draw
inside:

    ; Where it lands in VRAM. The window is two 32x32 screens side by side, and
    ; the right one lives 1024 words further on, not next to it.
    txa
    and #(WINDOW_COLS - 1)
    sta temp
    and #$001F
    clc
    adc f:FAR_VRAM_MAP          ; the layout picks it: see LAYOUT_VENTANA_AMBOS
    sta col_addr
    lda temp
    and #$0020
    beq left
    lda col_addr
    clc
    adc #1024
    sta col_addr
left:

    ; The block is 16x16: the block column is half the cell column and the
    ; leftover bit says which of its two halves it is.
    txa
    and #$0001
    asl a                       ; 0 the left half, 2 the right
    sta strip_ofs
    txa
    lsr a
    asl a                       ; the block column, in bytes
    sta temp

    jsr ptr_from_cells
    lda temp
    jsr ptr_more

    ; The window's top row decides the slot where it starts and which half of
    ; the block it lands in.
    lda win_row
    and #$0001
    beq from_up
    lda strip_ofs
    ora #$0004                  ; starts at the block's bottom half
    sta strip_ofs
from_up:
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax                         ; the slot, in bytes

    ; How many rows lie ahead: the whole window, or whatever is left of the
    ; map.
    lda map_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcc short
    lda #WINDOW_ROWS
short:
    sta strip_left

    ; The block index goes in Y and the slot in X, and not the other way
    ; around: the block table no longer lives in bank 0 —with several maps it
    ; does not fit— so it is read with a 24-bit pointer, and that mode only
    ; indexes by Y.
row:
    lda [cells_ptr]             ; this cell's block
    jsr cell_replaced
    asl a
    asl a
    asl a
    asl a                       ; its record is 16 bytes
    clc
    adc strip_ofs
    tay
    lda [blocks_ptr], y
    sta strip_col, x            ; the background cell
    lda [blocks8_ptr], y
    sta strip_col2, x           ; and the upper layer's

    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)  ; the window wraps
    tax

    lda strip_ofs
    eor #$0004                  ; the other half of the block
    sta strip_ofs
    and #$0004
    bne same                    ; still in the same block
    lda strip_step_col
    jsr ptr_more                ; to the next block row
same:
    dec strip_left
    bne row
    rts
.endproc

; The mirror image of the previous one: builds row X of the map in strip_row.
; All that changes is which of the two axes alternates inside the block and
; how far the pointer advances when going from one to the next.
.proc build_row
.a16
.i16
    stz row_addr
    cpx map_ch
    bcc inside
    rts                         ; past the bottom edge
inside:
    txa
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a                       ; each screen row is 32 words
    clc
    adc f:FAR_VRAM_MAP
    sta row_addr

    txa
    and #$0001
    asl a
    asl a                       ; 0 the block's top half, 4 the bottom
    sta strip_ofs
    txa
    lsr a
    sta temp                    ; the block row coming in

    ; The anchor points at the window's top block row; the one coming in may be
    ; up to fourteen rows further down, if it is the one at the foot of the
    ; screen.
    jsr ptr_from_cells
    lda temp
    sec
    sbc win_block
    beq in_row
    tax
low:
    lda strip_step_col
    jsr ptr_more
    dex
    bne low
in_row:
    ; The row starts MARGIN_COLS columns before the window, which is the same
    ; range `fill_window` and `stream_map` load: [win_col - MARGIN_COLS,
    ; win_col + 60). If it started at win_col, the row's last four columns
    ; —win_col + 60 to 63— would overwrite, on the torus, the slots of the left
    ; margin, and that was seen: the corner of the screen on map 2 showed
    ; columns from 64 further on. Negative columns and the ones past the right
    ; edge go empty, as in `build_column`.
    lda win_col
    sec
    sbc #MARGIN_COLS
    sta row_col
    and #(WINDOW_COLS - 1)
    asl a
    tax                         ; the first column's slot, in bytes
    lda #WINDOW_COLS
    sta strip_total
empty_left:
    lda row_col
    bpl with_map
    stz strip_row, x
    stz strip_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    inc row_col
    dec strip_total
    bra empty_left
with_map:
    lda row_col
    and #$0001
    beq from_left
    lda strip_ofs
    ora #$0002
    sta strip_ofs
from_left:
    lda row_col
    lsr a
    asl a                       ; the leftmost block column, in bytes
    jsr ptr_more
    lda map_cw
    sec
    sbc row_col
    cmp strip_total
    bcc short
    lda strip_total
short:
    sta strip_left
    lda strip_left
    beq empty_right             ; the whole row falls outside the map
column:
    lda [cells_ptr]
    jsr cell_replaced
    asl a
    asl a
    asl a
    asl a
    clc
    adc strip_ofs
    tay
    lda [blocks_ptr], y
    sta strip_row, x
    lda [blocks8_ptr], y
    sta strip_row2, x

    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax

    lda strip_ofs
    eor #$0002                  ; the other half of the block, now across
    sta strip_ofs
    and #$0002
    bne same
    lda #2
    jsr ptr_more                ; to the next block over
same:
    dec strip_total
    dec strip_left
    bne column
empty_right:
    lda strip_total
    beq ready
    stz strip_row, x
    stz strip_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    dec strip_total
    bra empty_right
ready:
    rts
.endproc

; What has to be redrawn this frame: the rows and the columns the camera just
; uncovered.
;
; **It is up to two per axis per tick, and that is measured.** On the same axis
; two things add up: the hero at speed 6 walks 8 px per frame
; —`half_step_per_speed` goes up to 64 eighths— and a `PanScreen` at speed 6
; moves the camera another 8 —`2 << 6` sixteenths—. Sixteen pixels are two
; 8-pixel cells. The hero's jump does not get there: the longest in the game is
; five cells in eleven frames, 7.3 px per frame.
;
; Until 2026-09-22 this drew **only one** and recorded `win_row` as if it had
; drawn all the ones the camera skipped, with a comment saying the camera never
; moved more than two pixels. The skipped row stayed wrong **forever**, because
; the window is a torus and nobody overwrites that slot again until 32 rows
; later: the map looked shifted one or two cells relative to the collision, and
; any teleport fixed it because it refills the whole window. taro found it
; playing, after the Neon Vipers cutscene.
;
; And if the camera ever jumped more than two —today it does not—, `win_row`
; **falls behind** instead of lying: what is missing gets drawn on the
; following ticks and the offset heals by itself. What is seen meanwhile is the
; screen edge lagging, which lasts as long as the jump does and not forever.
.proc stream_map
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    stz col_addr_b
    stz row_addr_b
    ; Two calls and not a loop with a counter: `build_row` and `build_column`
    ; use Y to read the blocks, so the counter would have to live in RAM, and
    ; "two per tick" reads better here than in a constant.
    jsr one_row
    jsr one_row
    jsr one_column
    jsr one_column
    ; What a `TileSubstitution` left pending: one column of the window, and
    ; only if the camera did not take any this frame —both addresses at zero
    ; means none is built—. See `sub_refresh`.
    lda sub_refresh
    beq no_refresh
    lda col_addr
    ora col_addr_b
    bne no_refresh
    dec sub_refresh
    lda win_col
    sec
    sbc #MARGIN_COLS            ; the same range `fill_window` builds
    clc
    adc sub_refresh
    tax
    jsr build_column
no_refresh:
    sep #$20
.a8
    rts
.endproc

; One more row, if the camera left one undrawn. `win_col` and `win_row` advance
; **one at a time** even if the camera jumped further: that way `build_row`'s
; block anchor stays valid step by step, and what could not be drawn in time
; stays pending instead of getting lost.
.proc one_row
.a16
.i16
    lda camera_y
    lsr a
    lsr a
    lsr a
    cmp win_row
    beq ready
    ; The `jsr` goes **after** the `bcs` and on both branches: placed before,
    ; the branch would look at a carry that went through a call. It is cheap
    ; not to have to prove that `save_row` does not touch it.
    bcs lowering
    jsr save_row                ; the previous strip, if any, to the spare
    lda win_row
    dec a
    sta win_row
    tax                         ; going up: the screen's top row comes in
    bra with_row
lowering:
    jsr save_row
    lda win_row
    inc a
    sta win_row
    clc
    adc #(VIEW_ROWS - 1)
    tax                         ; going down: the bottom one comes in
with_row:
    ; The block anchor follows the window's top row.
    phx
    lda win_row
    lsr a
    cmp win_block
    beq same_block
    pha
    bcs low_block
    jsr ptr_from_cells
    lda strip_step_col
    jsr ptr_minus
    jsr ptr_to_cells
    bra saves_block
low_block:
    jsr ptr_from_cells
    lda strip_step_col
    jsr ptr_more
    jsr ptr_to_cells
saves_block:
    pla
    sta win_block
same_block:
    plx
    jsr build_row               ; X is the row coming in
ready:
    rts
.endproc

; The mirror image, for the other axis.
.proc one_column
.a16
.i16
    lda camera_x
    lsr a
    lsr a
    lsr a
    cmp win_col
    beq ready
    bcs right                   ; the `jsr` after the branch: see `one_row`
    jsr save_column
    lda win_col
    dec a
    sta win_col
    sec
    sbc #MARGIN_COLS            ; going up: the left margin's comes in
    tax
    bra build
right:
    jsr save_column
    lda win_col
    inc a
    sta win_col
    clc
    adc #(VIEW_COLS - 1 + MARGIN_COLS)
    tax
build:
    jsr build_column
ready:
    rts
.endproc

; The row strip left built, to the spare in far RAM, so that `build_row` can
; reuse the buffer in this same tick.
;
; It is copied instead of having two sets of strips and letting `build_row`
; choose: `build_row`'s loop writes with `sta strip_row, x` and
; `stz strip_row, x`, and `stz` has no long indexed mode, so moving them to far
; RAM would cost it an `lda #0` per cell in the hot loop. The `mvn` is 256
; bytes at seven cycles and is paid **only** when the camera jumped two rows,
; which is rare.
.proc save_row
.a16
.i16
    lda row_addr
    beq ready                   ; none is built
    sta row_addr_b
    ; The row's two strips are contiguous —see their `.res`—, so they go in a
    ; single `mvn`, which copies A + 1 bytes and leaves the data bank at the
    ; destination.
    ldx #.loword(strip_row)
    ldy #.loword(FAR_STRIP_ROW)
    lda #(WINDOW_COLS * 2 * 2 - 1)
    phb
    mvn #$00, #^FAR_STRIP_ROW   ; the BSS is visible from bank 0: it is the
    plb                         ; mirror of the WRAM below $2000
    stz row_addr                ; the buffer is free
ready:
    rts
.endproc

.proc save_column
.a16
.i16
    lda col_addr
    beq ready
    sta col_addr_b
    ldx #.loword(strip_col)
    ldy #.loword(FAR_STRIP_COL)
    lda #(WINDOW_ROWS * 2 * 2 - 1)
    phb
    mvn #$00, #^FAR_STRIP_COL
    plb
    stz col_addr
ready:
    rts
.endproc

; Fills the whole window from scratch: the 64 columns, one by one. It runs with
; the screen off, at startup, and it is the only moment when that much tilemap
; is written at once.
; The map's two tilemaps —the background and the upper layer— at zero, and the
; four strips they are filled with.
;
; `build_column` and `build_row` **skip** whatever falls outside the map, and
; the strips are only written as far as the map reaches. At boot that leaves
; zeros, which is the empty cell and shows black, because the reset cleared
; all of VRAM. After a teleport or a door, on the other hand, it left whatever
; the previous map had put there: `ShakeScreen` against the edge uncovers it,
; since it moves the screen past the first column. Step 9e found it, when the
; `sacudir-borde` and `tram-viaje` cases switched to reaching their map with a
; `Teleport` instead of starting there.
;
; It runs with the screen in forced blanking, which is how every map load
; runs: it is two 4 KB DMAs to VRAM.
.proc clear_tilemaps
.a8
.i16
    lda #$80
    sta VMAIN                   ; advance one word after the high byte
    rep #$20
.a16
    lda f:FAR_VRAM_MAP
    tax
    sep #$20
.a8
    jsr zero_to_tilemap
    ldx #VRAM_ABOVE_MAP
    jsr zero_to_tilemap
    ldx #$0000
strips:
    stz strip_col, x            ; all four are contiguous: see their .res
    inx
    cpx #(WINDOW_ROWS * 2 * 2 + WINDOW_COLS * 2 * 2)
    bne strips
    rts
.endproc

; A tilemap of two 32x32 screens, from VRAM word X, to zero.
.proc zero_to_tilemap
.a8
.i16
    stx VMADDL
    ldx #.loword(zero)
    stx A1T0L
    lda #^zero
    sta A1B0
    ldx #(32 * 32 * 2 * 2)      ; two screens, in words
    stx DAS0L
    lda #$09                    ; two registers, word at a time, fixed source
    sta DMAP0
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

.proc fill_window
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    stz col_addr_b              ; and the spare ones: everything is filled from
    stz row_addr_b              ; scratch here, so anything half built is useless
    lda map_width
    asl a
    sta strip_step_col          ; the size of a block row, in bytes

    lda camera_x
    lsr a
    lsr a
    lsr a
    sta win_col
    lda camera_y
    lsr a
    lsr a
    lsr a
    sta win_row
    lsr a
    sta win_block

    ; cells = the map's grid + win_block rows. It is added one at a time
    ; instead of multiplying: it happens only once and the 65816 does not
    ; multiply. The grid is in WRAM, where `lz2_grid` decompressed it when
    ; the map loaded.
    lda #.loword(GRID)
    sta cells_ptr
    sep #$20
.a8
    lda #^GRID
    sta cells_ptr + 2
    rep #$20
.a16
    ldx win_block
    beq no_rows
sum:
    lda strip_step_col
    jsr ptr_more
    dex
    bne sum
no_rows:
    jsr ptr_to_cells

    lda win_col
    sec
    sbc #MARGIN_COLS            ; with the left margin; `build_column` skips
    sta temp + 2                ; the negative columns
    ldy #WINDOW_COLS
column:
    phy
    ldx temp + 2
    jsr build_column
    sep #$20
.a8
    jsr push_strips
    rep #$20
.a16
    inc temp + 2
    ply
    dey
    bne column
    sep #$20
.a8
    ; And the panorama's ring, if the map shows it: see pano.s.
    jsl f:pano_fill
    rts
.endproc

; `hdma_mask` and `row_buf_table` **used to live here** and moved down to
; RODATA on 2026-09-13, each separately and on the same day: see `bank1.s`.
; The HDMA reads from wherever `A1B3` says, so it does not need bank 0, and the
; compositor indexes it with X, which does have a long mode. `hdma_mask` is
; the `mask_*` of message_place.s since 2026-10-04.

