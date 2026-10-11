.segment "FAR2"
.a8
.i16

; --- the painted maps --------------------------------------------------------
;
; A map whose panorama is the map itself —fixed to it, with nothing of the
; ChipSet over it— is a painting, and the converter gives it a way of its
; own: `Way::Painted` in Wally. The painting goes in BG1, in mode 1, at 4
; bits, **one tile per 8x8 cell and no grouping**: a painting of 640x480 has
; 4,800 cells, almost all different, and grouped into what VRAM holds it was
; a mosaic of the wrong cells.
;
; **VRAM holds only the cells the screen can show**, and a row more. The
; screen is 256x224, so with the scroll halfway through a cell it shows 33
; columns and 29 rows: cell (x, y) lives in slot `(y mod 30) + 30 * (x mod
; 33)` —`PAINT_COLUMNS` and `PAINT_ROWS`, which the converter writes—, and no
; two cells on screen share one. When the camera crosses a column, the one
; coming in goes over the one that just left; a row is uploaded ahead, into
; the spare one: see `paint_tick`. A column is one run of slots and of
; cartridge, so it goes in one DMA or two; a row is 33 tiles of 32 bytes,
; one DMA each.
;
; The tilemap is the map's moving window —`build_column` and `build_row`
; build it as always, and `paint_column` and `paint_row` overwrite what goes
; to BG1 with the painting's cells: their palette and priority from the
; cartridge, and the slot by where the cell is—, and its scroll the map's.
; The blocks are still the map's, for the passability and the layer above.
;
; Each frame `paint_tick` looks at where the screen starts, decides which
; row and which columns come in, and leaves the DMAs in `PAINT_Q`;
; `paint_flush` uploads them in the vblank and takes what they cost out of
; the poses' budget.
;
; **Only a cartridge with a painted map assembles any of this**: without
; `paint_table` in the `.inc` the file is empty, and so are the calls to it,
; so the cartridges without one come out byte for byte as before.
;
; Everything here is reached with `jsl` and goes back with `rtl`.


.ifdef paint_table

; The state, in far RAM: $7E7900 to $7E791F, taken on 2026-10-11 from the gap
; between `FAR_EFFECT_IN`'s range and `TRANSITION_ERASE`.
PAINT_ON   = $7E7900            ; 1 while the loaded map is painted, else 0
PAINT_ENT  = $7E7901            ; word: its record, an offset into paint_table
PAINT_TX   = $7E7903            ; word, signed: the first column the slots hold
PAINT_TY   = $7E7905            ; word: and the first row
PAINT_QN   = $7E7907            ; word: bytes of `PAINT_Q` waiting, 0 none
PAINT_COST = $7E7909            ; what they take from the poses' budget
PAINT_ARG  = $7E790A            ; word: the column or row a strip is built for
PAINT_T    = $7E790C            ; eight words of scratch
PAINT_M    = $7E791C            ; and two for `mul16`, `mod8` and `times_rows`
PAINT_END  = $7E7920
.assert PAINT_END <= $7E7920, error, "the painted maps' state goes into TRANSITION_ERASE"
; And the row being uploaded ahead, from $7E79A0, taken on 2026-10-11 from
; the gap between `NPC_ROW_SEPARATE`'s range and `ENC_THR`: see `paint_tick`.
PAINT_JOB   = $7E79A0           ; word: the row being uploaded, $FFFF none
PAINT_JK    = $7E79A2           ; word: how many of its 33 columns are up
PAINT_LASTY = $7E79A4           ; word: last frame's camera, down
PAINT_DIR   = $7E79A6           ; 0 the camera last went down, 1 up
PAINT_END2  = $7E79A7
.assert PAINT_END2 <= $7E79C0, error, "the painted maps' row goes into ENC_THR"
; Tiles of the row ahead a frame: a row in three frames, and the camera
; crosses one every four at the walk's two pixels a frame.
PAINT_STEP  = 11
; And the queue, at the end of the grid's bank: the grid of a painted map is
; a few kilobytes —the converter checks it does not reach here— and the
; queue lasts from one tick to the next vblank. Eight bytes an entry: the
; VRAM word, the source's low word and bank, a spare byte and the length.
PAINT_Q     = $7EFE00
PAINT_Q_MAX = 40
.assert PAINT_Q + PAINT_Q_MAX * 8 <= $7F0000, error, "the painted maps' queue goes past the grid's bank"

; The fields of a `paint_table` record: see `panorama.rs` in
; rm2k-snes-mapdata.
PR_MAP     = 0
PR_W       = 2
PR_H       = 4
PR_ATTRS   = 6
PR_COLUMNS = 9
PR_VRAM    = 12
PR_BLANK   = 14

; Looks the map being entered up in `paint_table`, with `map_current` set.
; From `load_map_data`, right after `pano_find`.
.proc paint_find
.a8
.i16
    php
    rep #$30
.a16
    ldx #0
other:
    lda f:paint_table + PR_MAP, x
    cmp #$FFFF
    beq none
    cmp map_current
    beq found
    txa
    clc
    adc #PAINT_STRIDE
    tax
    bra other
none:
    sep #$20
.a8
    lda #0
    sta f:PAINT_ON
    plp
    rtl
.a16
found:
    txa
    sta f:PAINT_ENT
    lda #0
    sta f:PAINT_QN
    sep #$20
.a8
    lda #1
    sta f:PAINT_ON
    plp
    rtl
.endproc

; --- arithmetic ------------------------------------------------------------

; A times `PAINT_M + 2`, into A: the low sixteen bits. Keeps X and Y.
.proc paint_mul16
.a16
.i16
    phx
    sta f:PAINT_M               ; what shifts out from the top
    lda #0
    ldx #16
shift:
    asl a
    pha
    lda f:PAINT_M
    asl a
    sta f:PAINT_M
    pla
    bcc no_add
    clc
    adc f:PAINT_M + 2
no_add:
    dex
    bne shift
    plx
    rts
.endproc

; A mod the byte at `PAINT_M + 2`, into A, by the console's divider. A is
; not negative. Keeps X and Y.
.proc paint_mod8
.a16
.i16
    sta f:WRDIVL
    sep #$20
.a8
    lda f:PAINT_M + 2
    sta f:WRDIVB                ; sixteen cycles
    rep #$20
.a16
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda f:RDMPYL                ; the remainder
    rts
.endproc

; A times 30, `PAINT_ROWS`: a column of slots' first one. Keeps X and Y.
.assert PAINT_ROWS = 30, error, "paint_times_rows multiplies by 30"
.proc paint_times_rows
.a16
.i16
    sta f:PAINT_M
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32
    sec
    sbc f:PAINT_M
    sec
    sbc f:PAINT_M               ; 30
    rts
.endproc

; --- the tilemap ---------------------------------------------------------------

; The map's tilemap, with the screen off, at the blank tile's entry and not
; at zero, which is slot 0 —a cell of the painting—: past the map's edges
; and under a map smaller than the screen. From `clear_tilemaps`, after it
; set it to zero. The entry is not two equal bytes, so it goes in two DMAs,
; the low bytes and the high ones, each from the record's own word.
.proc paint_clear
.a8
.i16
    lda f:PAINT_ON
    bne on
    rtl
on:
    php
    phb
    pea $0000
    plb
    plb
    rep #$20
.a16
    lda f:FAR_VRAM_MAP
    sta VMADDL
    lda f:PAINT_ENT
    clc
    adc #.loword(paint_table + PR_BLANK)
    sta A1T0L
    lda #(WINDOW_COLS * WINDOW_ROWS)
    sta DAS0L
    sep #$20
.a8
    lda #^paint_table
    sta A1B0
    stz VMAIN                   ; the address moves after the low byte
    lda #$08                    ; one register, fixed source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda f:FAR_VRAM_MAP
    sta VMADDL
    inc A1T0L                   ; the high byte
    lda #(WINDOW_COLS * WINDOW_ROWS)
    sta DAS0L
    sep #$20
.a8
    lda #$80                    ; and after the high one
    sta VMAIN
    lda #$19
    sta BBAD0
    lda #$01
    sta MDMAEN
    plb
    plp
    rtl
.endproc

; `cells_ptr` at the record's cell bytes, plus A. `cells_ptr` is free here:
; `build_column` and `build_row` set it from `cells` every time they start,
; and nobody reads it after them. Sixteen bits; X is the record's offset
; after it.
.proc paint_attrs_at
.a16
.i16
    pha
    lda f:PAINT_ENT
    tax
    pla
    clc
    adc f:paint_table + PR_ATTRS, x
    sta cells_ptr
    sep #$20
.a8
    lda f:paint_table + PR_ATTRS + 2, x
    sta cells_ptr + 2
    rep #$20
.a16
    rts
.endproc

; The blank tile's entry in all of a strip of A bytes at X —`strip_col` or
; `strip_row`, which are in bank 0—: what the cells past the map show.
.proc paint_blank_strip
.a16
.i16
    lsr a
    tay                         ; in words
    phx
    lda f:PAINT_ENT
    tax
    lda f:paint_table + PR_BLANK, x
    plx
blank:
    sta f:$000000, x
    inx
    inx
    dey
    bne blank
    rts
.endproc

; Column `PAINT_ARG` of the painting into `strip_col`, over what
; `build_column` put there from the blocks: the same rows, from `win_row`,
; as many as it built, and the blank tile on the rest. From the end of
; `build_column`, only if it built one.
.proc paint_column
.a16
.i16
    php
    sep #$20
.a8
    lda f:PAINT_ON
    bne on
    plp
    rtl
on:
    rep #$30
.a16
    ldx #.loword(strip_col)
    lda #(WINDOW_ROWS * 2)
    jsr paint_blank_strip
    ; The cell's byte: column * H + win_row.
    lda f:PAINT_ENT
    tax
    lda f:paint_table + PR_H, x
    sta f:PAINT_M + 2
    lda f:PAINT_ARG
    jsr paint_mul16
    clc
    adc win_row
    jsr paint_attrs_at
    ; The slot of the column's first row: 30 * (x mod 33) + (y mod 30).
    lda #PAINT_COLUMNS
    sta f:PAINT_M + 2
    lda f:PAINT_ARG
    jsr paint_mod8
    jsr paint_times_rows
    sta f:PAINT_T + 2
    lda #PAINT_ROWS
    sta f:PAINT_M + 2
    lda win_row
    jsr paint_mod8
    sta f:PAINT_T + 4           ; y mod 30, which walks
    ; As many rows as `build_column`: the window's, or what is left of the
    ; map.
    lda map_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcc short
    lda #WINDOW_ROWS
short:
    sta f:PAINT_T + 6
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax
    ldy #0
row:
    lda [cells_ptr], y
    and #$00FF
    xba
    clc
    adc f:PAINT_T + 2
    adc f:PAINT_T + 4
    sta f:strip_col, x
    iny
    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)
    tax
    lda f:PAINT_T + 4
    inc a
    cmp #PAINT_ROWS
    bcc same_lap
    lda #0
same_lap:
    sta f:PAINT_T + 4
    lda f:PAINT_T + 6
    dec a
    sta f:PAINT_T + 6
    bne row
    plp
    rtl
.endproc

; Row `PAINT_ARG` of the painting into `strip_row`, over what `build_row`
; put there: the same columns, from `win_col - MARGIN_COLS`; the ones inside
; the map, and the blank tile on the rest. From the end of `build_row`, only
; if it built one.
.proc paint_row
.a16
.i16
    php
    sep #$20
.a8
    lda f:PAINT_ON
    bne on
    plp
    rtl
on:
    rep #$30
.a16
    ldx #.loword(strip_row)
    lda #(WINDOW_COLS * 2)
    jsr paint_blank_strip
    lda f:PAINT_ENT
    tax
    lda f:paint_table + PR_H, x
    sta f:PAINT_T + 8           ; between two columns' bytes
    ; The first column inside the map.
    lda win_col
    sec
    sbc #MARGIN_COLS
    sta f:PAINT_T               ; the strip's first column
    bpl from_it
    lda #0
from_it:
    sta f:PAINT_T + 6           ; the first one drawn
    ; How many: up to the strip's end or the map's.
    lda f:PAINT_T
    clc
    adc #WINDOW_COLS
    cmp map_cw
    bcc to_strip
    lda map_cw
to_strip:
    sec
    sbc f:PAINT_T + 6
    beq none
    bpl some
none:
    brl done                    ; the whole strip falls outside the map
some:
    sta f:PAINT_T + 12          ; how many columns
    ; The cell's byte: column * H + row.
    lda f:PAINT_T + 8
    sta f:PAINT_M + 2
    lda f:PAINT_T + 6
    jsr paint_mul16
    clc
    adc f:PAINT_ARG
    jsr paint_attrs_at
    ; Its slot: 30 * (x mod 33) + (y mod 30).
    lda #PAINT_COLUMNS
    sta f:PAINT_M + 2
    lda f:PAINT_T + 6
    jsr paint_mod8
    sta f:PAINT_T + 10          ; x mod 33, which walks
    jsr paint_times_rows
    sta f:PAINT_T + 2
    lda #PAINT_ROWS
    sta f:PAINT_M + 2
    lda f:PAINT_ARG
    jsr paint_mod8
    sta f:PAINT_T + 4           ; y mod 30
    clc
    adc f:PAINT_T + 2
    sta f:PAINT_T + 2           ; the slot, which walks
    lda f:PAINT_T + 6
    and #(WINDOW_COLS - 1)
    asl a
    tax
    ldy #0
column:
    lda [cells_ptr], y
    and #$00FF
    xba
    clc
    adc f:PAINT_T + 2
    sta f:strip_row, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    tya
    clc
    adc f:PAINT_T + 8
    tay
    ; The next column's slot: 30 further, or the first lap's.
    lda f:PAINT_T + 10
    inc a
    cmp #PAINT_COLUMNS
    bcc same_lap
    lda f:PAINT_T + 4
    sta f:PAINT_T + 2
    lda #0
    sta f:PAINT_T + 10
    bra next
same_lap:
    sta f:PAINT_T + 10
    lda f:PAINT_T + 2
    clc
    adc #PAINT_ROWS
    sta f:PAINT_T + 2
next:
    lda f:PAINT_T + 12
    dec a
    sta f:PAINT_T + 12
    bne column
done:
    plp
    rtl
.endproc

; --- the slots -------------------------------------------------------------------
;
; Scratch while a strip of slots is queued: `PAINT_T` + 0 the column, + 2
; how many or where they end, + 4 the row, + 6 the bytes, + 8 the VRAM word,
; + 10 and + 12 the source, + 14 a column of slots' first one.

; `cells_ptr` at the record's column table. Sixteen bits; X is the record's
; offset after it.
.proc paint_columns_at
.a16
.i16
    lda f:PAINT_ENT
    tax
    lda f:paint_table + PR_COLUMNS, x
    sta cells_ptr
    sep #$20
.a8
    lda f:paint_table + PR_COLUMNS + 2, x
    sta cells_ptr + 2
    rep #$20
.a16
    rts
.endproc

; One DMA into the queue at Y: the VRAM word at `PAINT_T + 8`, the source at
; `+ 10` and `+ 12`, the bytes at `+ 6`. Leaves Y past it.
.proc paint_enqueue
.a16
.i16
    tyx
    lda f:PAINT_T + 8
    sta f:PAINT_Q, x
    lda f:PAINT_T + 10
    sta f:PAINT_Q + 2, x
    lda f:PAINT_T + 12
    sta f:PAINT_Q + 4, x        ; the bank, and a spare byte
    lda f:PAINT_T + 6
    sta f:PAINT_Q + 6, x
    tya
    clc
    adc #8
    tay
    rts
.endproc

; The source of column A's cell in row `PAINT_T + 4`, into `PAINT_T + 10`
; and `+ 12`: the column's pointer plus 32 bytes a row. With `cells_ptr` at
; the column table. Keeps X and Y.
.proc paint_source_of
.a16
.i16
    phy
    sta f:PAINT_M               ; the column, times three
    asl a
    clc
    adc f:PAINT_M
    tay
    lda [cells_ptr], y
    sta f:PAINT_T + 10
    iny
    iny
    lda [cells_ptr], y
    and #$00FF
    sta f:PAINT_T + 12          ; the bank
    lda f:PAINT_T + 4
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:PAINT_T + 10
    sta f:PAINT_T + 10          ; a column never crosses a bank
    ply
    rts
.endproc

; Slot A's VRAM word: the record's plus sixteen words a slot. Keeps X and Y.
.proc paint_slot_vram
.a16
.i16
    phx
    asl a
    asl a
    asl a
    asl a
    pha
    lda f:PAINT_ENT
    tax
    pla
    clc
    adc f:paint_table + PR_VRAM, x
    plx
    rts
.endproc

; Column A of the painting into its slots, the rows the slots hold
; —`PAINT_TY` on, inside the map—: one DMA, or two if the column of slots
; laps. Into the queue at Y, which it leaves past them; nothing if the
; column is outside the map.
.proc paint_enqueue_column
.a16
.i16
    sta f:PAINT_T               ; the column
    lda f:PAINT_ENT
    tax
    lda f:PAINT_T
    cmp f:paint_table + PR_W, x ; negative is past it too
    bcc inside
    rts
inside:
    ; The rows: from the first the slots hold, as many as fit in them and
    ; in the map.
    lda f:paint_table + PR_H, x
    sec
    sbc f:PAINT_TY
    bcc no_rows
    bne rows
no_rows:
    brl none
rows:
    cmp #PAINT_ROWS
    bcc few
    lda #PAINT_ROWS
few:
    sta f:PAINT_T + 2           ; how many rows
    lda f:PAINT_TY
    sta f:PAINT_T + 4
    jsr paint_columns_at
    lda f:PAINT_T
    jsr paint_source_of
    lda #PAINT_COLUMNS
    sta f:PAINT_M + 2
    lda f:PAINT_T
    jsr paint_mod8
    jsr paint_times_rows
    sta f:PAINT_T + 14          ; the column of slots' first one
    lda #PAINT_ROWS
    sta f:PAINT_M + 2
    lda f:PAINT_T + 4
    jsr paint_mod8
    sta f:PAINT_T + 4           ; y mod 30
    ; How many fit before the column of slots laps.
    lda #PAINT_ROWS
    sec
    sbc f:PAINT_T + 4
    cmp f:PAINT_T + 2
    bcc laps
    lda f:PAINT_T + 2
laps:
    sta f:PAINT_T + 6
    lda f:PAINT_T + 2
    sec
    sbc f:PAINT_T + 6
    sta f:PAINT_T + 2           ; and how many after
    lda f:PAINT_T + 14
    clc
    adc f:PAINT_T + 4
    jsr paint_slot_vram
    sta f:PAINT_T + 8
    lda f:PAINT_T + 6
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:PAINT_T + 6           ; in bytes
    jsr paint_enqueue
    lda f:PAINT_T + 2
    beq none
    ; The rest, from the column of slots' first one and where the first
    ; run ended in the cartridge.
    lda f:PAINT_T + 10
    clc
    adc f:PAINT_T + 6
    sta f:PAINT_T + 10
    lda f:PAINT_T + 14
    jsr paint_slot_vram
    sta f:PAINT_T + 8
    lda f:PAINT_T + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:PAINT_T + 6
    jsr paint_enqueue
none:
    rts
.endproc

; Row A of the painting into its slots, from column `PAINT_T` to the one
; before `PAINT_T + 2` —the ones inside the map—, one DMA a tile. Into the
; queue at Y, past them. The row's `y mod 30` and the slot that walks live on
; the stack.
.proc paint_enqueue_row
.a16
.i16
    sta f:PAINT_T + 4           ; the row
    lda f:PAINT_ENT
    tax
    lda f:PAINT_T + 4
    cmp f:paint_table + PR_H, x
    bcc inside
    rts
inside:
    ; The columns, inside the map.
    lda f:PAINT_T + 2
    bpl ends_after
    rts                         ; all of them before the map
ends_after:
    cmp f:paint_table + PR_W, x
    bcc in_map
    lda f:paint_table + PR_W, x
in_map:
    sta f:PAINT_T + 2           ; where they end
    lda f:PAINT_T
    bpl from_it
    lda #0
from_it:
    sta f:PAINT_T               ; the first one
    cmp f:PAINT_T + 2
    bcc some
    rts
some:
    lda #PAINT_ROWS
    sta f:PAINT_M + 2
    lda f:PAINT_T + 4
    jsr paint_mod8
    pha                         ; 3, s: y mod 30
    lda #PAINT_COLUMNS
    sta f:PAINT_M + 2
    lda f:PAINT_T
    jsr paint_mod8
    sta f:PAINT_T + 14          ; x mod 33, which walks
    jsr paint_times_rows
    clc
    adc 1, s
    pha                         ; 1, s: the slot, which walks
    jsr paint_columns_at
    lda #32
    sta f:PAINT_T + 6
tile:
    lda 1, s
    jsr paint_slot_vram
    sta f:PAINT_T + 8
    lda f:PAINT_T
    jsr paint_source_of
    jsr paint_enqueue
    ; The next column: its slot 30 further, or the first lap's.
    lda f:PAINT_T + 14
    inc a
    cmp #PAINT_COLUMNS
    bcc same_lap
    lda #0
    sta f:PAINT_T + 14
    lda 3, s
    sta 1, s
    bra next
same_lap:
    sta f:PAINT_T + 14
    lda 1, s
    clc
    adc #PAINT_ROWS
    sta 1, s
next:
    lda f:PAINT_T
    inc a
    sta f:PAINT_T
    cmp f:PAINT_T + 2
    bcc tile
    pla
    pla
none:
    rts
.endproc

; Where the screen starts, in cells: across, from what the PPU is given —the
; camera and the shake—, rounded down also when it is negative; down, the
; camera, which never is: the PPU shows line `scroll_y + 1`, which is it.
; Into `PAINT_T` and `PAINT_T + 2`.
.proc paint_screen_cells
.a16
.i16
    lda f:screen_x
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    sta f:PAINT_T
    lda camera_y
    lsr a
    lsr a
    lsr a
    sta f:PAINT_T + 2
    rts
.endproc

; The queue to VRAM, with the data bank at 0. Sixteen bits.
.proc paint_flush_queue
.a16
.i16
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #$01                    ; two registers, word by word
    sta DMAP0
    lda #$18
    sta BBAD0
    rep #$20
.a16
    ldx #0
dma:
    lda f:PAINT_Q, x
    sta VMADDL
    lda f:PAINT_Q + 2, x
    sta A1T0L
    lda f:PAINT_Q + 6, x
    sta DAS0L
    sep #$20
.a8
    lda f:PAINT_Q + 4, x
    sta A1B0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #8
    tax
    cmp f:PAINT_QN
    bcc dma
    rts
.endproc

; One frame: what came into view, into the queue for `paint_flush`. After
; `follow_camera`, which set where the screen starts.
;
; **A column goes when it is needed**: it is one run of slots and of
; cartridge, two DMAs at most, and the one coming in goes over the one that
; just left. Two a frame at most; if the camera went further, the rest comes
; on the next frames.
;
; **A row goes ahead**: it is 33 DMAs, too many for the vblank of a frame
; that also takes a column. So the slots hold 30 rows and the screen shows
; 29: the spare one is on the side the camera last went, and when the camera
; crosses a row the next one is uploaded over the row that just left,
; `PAINT_STEP` tiles a frame —`PAINT_JOB` and `PAINT_JK`—, before it comes
; into view. If the camera gets there first, or turns back while the row
; that left is half overwritten, what is missing goes in that frame.
.proc paint_tick
.a8
.i16
    lda f:PAINT_ON
    bne on
    rtl
on:
    php
    rep #$30
.a16
    ; Last frame's not uploaded yet —a frame that lasted two—: the slots
    ; stay as they are, and the next one catches up.
    lda f:PAINT_QN
    beq free
    plp
    rtl
free:
    jsr paint_screen_cells
    lda f:PAINT_T
    pha                         ; where the screen starts across
    lda f:PAINT_T + 2
    pha                         ; and down
    ; Which way the camera went last, down.
    lda camera_y
    sec
    sbc f:PAINT_LASTY
    beq same_way
    sep #$20
.a8
    bmi went_up
    lda #0
    bra went
went_up:
    lda #1
went:
    sta f:PAINT_DIR
    rep #$20
.a16
same_way:
    lda camera_y
    sta f:PAINT_LASTY
    sep #$20
.a8
    lda #0
    sta f:PAINT_COST
    rep #$20
.a16
    ldy #0

    ; The columns first: a row ahead is uploaded for the columns the slots
    ; hold, and one that comes in starts it over. How many may come in is
    ; at 1, s, down at 3, s and across at 5, s.
    lda #2
    pha
column:
    lda 5, s
    sec
    sbc f:PAINT_TX
    beq columns_done
    bmi left
    lda f:PAINT_TX
    inc a
    sta f:PAINT_TX
    clc
    adc #(PAINT_COLUMNS - 1)
    bra one_column
left:
    lda f:PAINT_TX
    dec a
    sta f:PAINT_TX
one_column:
    jsr paint_enqueue_column
    lda #0
    sta f:PAINT_JK
    sep #$20
.a8
    lda f:PAINT_COST
    clc
    adc #2                      ; 960 bytes in two DMAs: two poses
    sta f:PAINT_COST
    rep #$20
.a16
    lda 1, s
    dec a
    sta 1, s
    bne column
columns_done:
    pla

    ; The row. Down is at 1, s.
    lda f:PAINT_JOB
    cmp #$FFFF
    bne a_job
    ; None going: the camera behind the slots —it moved more than a row in
    ; a frame— gets the row it needs now, and one that just crossed a row on
    ; the spare's side starts the next one.
    lda 1, s
    sec
    sbc f:PAINT_TY
    beq at_first
    bmi behind_up
    cmp #1
    beq one_down
    lda f:PAINT_TY
    clc
    adc #PAINT_ROWS
    bra behind
behind_up:
    lda f:PAINT_TY
    dec a
behind:
    sta f:PAINT_JOB
    lda #0
    sta f:PAINT_JK
    brl now
at_first:
    ; The spare row is below: going up, the one above the screen goes over
    ; it. Not past the map's top.
    lda f:PAINT_DIR
    and #$00FF
    beq no_row
    lda f:PAINT_TY
    beq no_row
    dec a
    bra start
one_down:
    ; The spare row is above: going down, the one below the screen goes over
    ; it. Not past the map's bottom.
    lda f:PAINT_DIR
    and #$00FF
    bne no_row
    lda f:PAINT_ENT
    tax
    lda f:PAINT_TY
    clc
    adc #PAINT_ROWS
    cmp f:paint_table + PR_H, x
    bcs no_row
start:
    sta f:PAINT_JOB
    lda #0
    sta f:PAINT_JK
    bra ahead
no_row:
    brl rows_done
a_job:
    ; One going: whether the camera got there first.
    sec
    sbc f:PAINT_TY
    cmp #PAINT_ROWS
    beq job_down
    cmp #$FFFF
    beq job_up
    brl now                     ; putting back a row that left: it is in view
job_down:
    ; The row below the screen over the first: needed when the screen
    ; reaches it, and the first, which it half overwrote, if the camera
    ; turned back to it.
    lda 1, s
    sec
    sbc f:PAINT_TY
    beq turned_down
    bmi turned_down
    cmp #2
    bcc ahead
    brl now
turned_down:
    lda f:PAINT_TY
    bra turned
job_up:
    ; The row above the screen over the last: the same, the other way.
    lda 1, s
    sec
    sbc f:PAINT_TY
    bmi now
    beq ahead
    lda f:PAINT_TY
    clc
    adc #(PAINT_ROWS - 1)
turned:
    sta f:PAINT_JOB             ; the one that left, back
    lda #0
    sta f:PAINT_JK
    bra now
ahead:
    lda #PAINT_COLUMNS
    sec
    sbc f:PAINT_JK
    cmp #PAINT_STEP
    bcc go
    lda #PAINT_STEP
    bra go
now:
    lda #PAINT_COLUMNS
    sec
    sbc f:PAINT_JK
go:
    ; A tiles of the row, from column `PAINT_JK` of the slots'.
    pha
    sep #$20
.a8
    clc
    adc #3
    lsr a
    lsr a                       ; a pose's time for every four DMAs of 32
                                ; bytes, rounded up: about six fit
    clc
    adc f:PAINT_COST
    sta f:PAINT_COST
    rep #$20
.a16
    lda f:PAINT_TX
    clc
    adc f:PAINT_JK
    sta f:PAINT_T
    clc
    adc 1, s
    sta f:PAINT_T + 2
    pla
    clc
    adc f:PAINT_JK
    sta f:PAINT_JK
    lda f:PAINT_JOB
    jsr paint_enqueue_row
    lda f:PAINT_JK
    cmp #PAINT_COLUMNS
    bcc rows_done
    ; The whole row is up: the slots hold one row further that way.
    lda f:PAINT_JOB
    sec
    sbc f:PAINT_TY
    cmp #PAINT_ROWS
    bne not_down
    lda f:PAINT_TY
    inc a
    sta f:PAINT_TY
    bra finished
not_down:
    cmp #$FFFF
    bne finished
    lda f:PAINT_TY
    dec a
    sta f:PAINT_TY
finished:
    lda #$FFFF
    sta f:PAINT_JOB
rows_done:
    pla
    pla
    tya
    sta f:PAINT_QN
    plp
    rtl
.endproc

; The queue, in the vblank: from `flush_video`, before the poses, which get
; what is left of the budget. It goes before them because a slot that is
; late shows the cell that left, at the screen's edge, and a pose that is
; late shows the one before.
.proc paint_flush
.a8
.i16
    lda f:PAINT_ON
    bne on
    rtl
on:
    php
    phb
    pea $0000
    plb
    plb
    rep #$30
.a16
    lda f:PAINT_QN
    beq done
    jsr paint_flush_queue
    lda #0
    sta f:PAINT_QN
    sep #$20
.a8
    lda vq_cap
    sec
    sbc f:PAINT_COST
    bcs fits
    lda #0
fits:
    sta vq_cap
done:
    plb
    plp
    rtl
.endproc

; All the slots, with the screen off: the 33 columns from where the screen
; starts, and the blank tile. From `load_above` —every load and every return
; from a screen, which overwrite them— and from `fill_window` —every jump of
; the camera—.
.proc paint_load
.a8
.i16
    lda f:PAINT_ON
    bne on
    rtl
on:
    php
    phb
    pea $0000
    plb
    plb
    rep #$30
.a16
    jsr paint_screen_cells
    lda f:PAINT_T
    sta f:PAINT_TX
    lda f:PAINT_T + 2
    sta f:PAINT_TY              ; the spare row below
    lda #$FFFF
    sta f:PAINT_JOB
    lda camera_y
    sta f:PAINT_LASTY
    sep #$20
.a8
    lda #0
    sta f:PAINT_DIR
    rep #$20
.a16
    ; The blank tile, from `zero`.
    lda #(PAINT_COLUMNS * PAINT_ROWS)
    jsr paint_slot_vram
    sta VMADDL
    lda #.loword(zero)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^zero
    sta A1B0
    lda #$80
    sta VMAIN
    lda #$09                    ; two registers, fixed source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda f:PAINT_TX
    pha                         ; 3, s: the column
    lda #PAINT_COLUMNS
    pha                         ; 1, s: how many are left
column:
    ldy #0
    lda 3, s
    jsr paint_enqueue_column
    tya
    beq outside
    sta f:PAINT_QN
    jsr paint_flush_queue
outside:
    lda 3, s
    inc a
    sta 3, s
    lda 1, s
    dec a
    sta 1, s
    bne column
    pla
    pla
    lda #0
    sta f:PAINT_QN
    plb
    plp
    rtl
.endproc

.endif
