.segment "FAR"
.a8
.i16

; --- the text layer of the screens ------------------------------------------
;
; The items', equipment's, the shop's and the battle's text, with the font's
; variable width. Until 2026-10-03 those screens wrote **one letter per
; cell**: a tile bank with each letter in two cells, and the screen was a
; tilemap of letters. With a font whose letters are four or five pixels wide
; that would leave gaps of three, so the text is **composed**, like the
; message window's: each line is drawn letter by letter, at its own x, into
; tiles of its own.
;
; What the screens' code says did not change: a text goes at a cell
; —`pick_table`, row * 64 + column * 2— and `scr_text`, `scr_glyph` and
; `scr_number` write it there. What changed is what that means:
;
; * **A write is a run**, not cells: the letters go one after the other from
;   x = 8 * column + `SCR_TEXT_X`, each moving x by its own advance. A write
;   that starts exactly where the previous one ended, in the same colour,
;   continues the run; any other starts a new one at its cell, and replaces
;   one that started at the same x. A run never reaches the cell where the
;   next one starts: a letter moves the line at most six pixels and a cell is
;   eight.
; * **What a row says is a record**, `TL_CUR`: its runs, with their x, their
;   colour and their letters. `scr_clear` empties the records, and the screen
;   writes them again; only what changed gets drawn. The letters are copied
;   into the record, so a run does not care where they came from —the item
;   texts in ROM, a number, the battle's message in RAM—, and it is not
;   capped by the cells: a description of fifty letters goes in one line.
; * **A row that changed is typeset**: its runs are composed into
;   `TL_STAGE`, 32 columns of two tiles, and each column that got ink takes a
;   pair of tiles from a pool, `TL_FREE`; the layer's tilemap, `TL_MAP`,
;   points the row's two cell rows there. A row takes no tiles where it has
;   no text, which is what lets a list of ten rows fit.
; * **A row that says what another one said takes its tiles**, without
;   typesetting: a list that scrolls one row composes one, and the others
;   move. Two rows can point to the same pair, so a pair counts who points
;   to it —`TL_REFS`—.
; * **The tilemap switches when everything is typeset**: the tiles go up as
;   each row is done, to pairs the tilemap on screen does not use, and the
;   tilemap goes up once there is nothing left, so a screen goes from what it
;   said to what it says in one frame. A pair a row stopped using waits in
;   `TL_PEND` until that switch, because the screen still shows it. A screen
;   that changes so much at once that the pool runs out switches earlier.
;
; **It typesets while the frame waits for the vblank**: `wait_vblank` calls
; `tl_idle` until the line it is on reaches `TL_LAST_LINE`. That is the
; frame's idle time, after the screen's loop read the pad, moved the cursor
; —with its own uploads, which have to fall in the vblank— and wrote its
; records. With the screen off, right after `tl_reset`, there is no budget:
; the first `scr_upload` composes and uploads everything. **So the text
; arrives some frames after the cursor**: on the items screen, measured on
; 2026-10-03 with fourteen items, four frames for a step of the cursor and
; six for a step that scrolls the list —ten rows adopt, two are typeset—.
;
; The letter comes **precomposed**, like the message window's: a table per
; phase, `scr_pre0` to `scr_pre7`, that says per row what is kept and what is
; set. The colour is the palette: every ink has the same layout —row k of
; the glyph is entry 1 + k, the shadow 13—, so one table paints them all.
; Composing them one bit per pixel, shifted as it went, was measured first:
; a description of fifty letters took nine frames to show. See `tl_glyph`.
;
; The layer's tilemap is its own and not `text_buf`: that one is the message
; window's line, and a row finished after a screen closed would land in the
; middle of a message being composed.
;
; Everything here runs with the data bank at $7E —the layer's RAM, at
; `FAR_TEXT_LAYER`— and is entered with `jsl` from bank 0, where
; `text_screens.s` has the `scr_*` everyone calls.

TL_ROWS      = 27               ; a line starts on rows 0 to 26: it takes two
TL_COLS      = 32
TL_RECORD    = 56               ; a row's record: its length, then its runs
TL_MAP       = FAR_TEXT_LAYER   ; the BG2 tilemap, 32 by 28 words
TL_CUR       = TL_MAP + 32 * 28 * 2
TL_SHOWN     = TL_CUR + TL_ROWS * TL_RECORD  ; what `TL_MAP` says
TL_STAGE     = TL_SHOWN + TL_ROWS * TL_RECORD
TL_STAGE_BYTES = TL_COLS * 64   ; a column is two tiles, top and bottom
TL_PAIR      = TL_STAGE + TL_STAGE_BYTES     ; each cell's pair in `TL_MAP`
TL_PAIRS     = 192                           ; a screen has 191 at most
TL_REFS      = TL_PAIR + TL_ROWS * TL_COLS   ; per pair, how many cells
TL_FREE      = TL_REFS + TL_PAIRS            ; the free ones, a stack
TL_PEND      = TL_FREE + TL_PAIRS            ; released, still on screen
TL_UPLOAD    = TL_PEND + TL_PAIRS            ; (column, pair) to upload
TL_USED      = TL_UPLOAD + 2 * TL_COLS       ; per column: colour + 1 if inked
TL_FLAG      = TL_USED + TL_COLS             ; per row: `TL_WRITTEN`, `TL_DIRTY`
TL_CSIG      = TL_FLAG + 28                  ; per row: its record's signature
TL_SSIG      = TL_CSIG + 28                  ; and what `TL_MAP` says's
TL_VARS      = TL_SSIG + 28
; A row written since it was last looked at, and one that says something
; other than what `TL_MAP` says. 0 is neither.
TL_WRITTEN   = 1
TL_DIRTY     = 2
TL_FREE_N    = TL_VARS + 0      ; how many pairs are free
TL_PEND_N    = TL_VARS + 2      ; and how many wait for the switch
TL_UP_N      = TL_VARS + 4      ; how many of the last row's go up
TL_UP_I      = TL_VARS + 6      ; and how many of those went up already
TL_PEN_PICK  = TL_VARS + 8      ; where the last write left `pick_table`
TL_PEN_VAR   = TL_VARS + 10     ; and in which colour
TL_RUN       = TL_VARS + 12     ; the open run's count byte, 0 none
TL_RUN_ROW   = TL_VARS + 14     ; and its row's record
TL_T_ROW     = TL_VARS + 16     ; the row being typeset, $FFFF none
TL_T_POS     = TL_VARS + 18     ; its next byte, in `TL_SHOWN`
TL_T_END     = TL_VARS + 20     ; and where its record ends
TL_T_LEFT    = TL_VARS + 22     ; letters left in the current run
TL_X         = TL_VARS + 24     ; where the next letter starts, in pixels
TL_FREE_26   = TL_VARS + 26     ; (free)
TL_VAR       = TL_VARS + 28     ; the run's colour
TL_SCAN      = TL_VARS + 30     ; the next row to look at
TL_LEFT      = TL_VARS + 32     ; nonzero: no budget, the screen is off
TL_SETTLE    = TL_VARS + 34     ; nonzero: the next upload composes it all
TL_IDLE_DONE = TL_VARS + 36     ; nonzero: nothing left to typeset
TL_MAP_DIRTY = TL_VARS + 38     ; nonzero: `TL_MAP` is not what is on screen
TL_FLUSH     = TL_VARS + 40     ; nonzero: the pool ran out, switch now
TL_C         = TL_VARS + 42     ; the letter being drawn
TL_G         = TL_VARS + 44     ; where its rows start in `font_table`
TL_PH        = TL_VARS + 46     ; its phase's shift table
TL_PS        = TL_VARS + 48     ; and its shadow's, one pixel further
TL_BASE      = TL_VARS + 50     ; the stage byte of its first column
TL_G16       = TL_VARS + 52     ; a glyph row, shifted: two cells
TL_S16       = TL_VARS + 54     ; and its shadow's
TL_GG        = TL_VARS + 56     ; one cell's, on both bytes of a word
TL_SS        = TL_VARS + 58
TL_KEEP      = TL_VARS + 60
TL_DONE      = TL_VARS + 62     ; `tl_work`: nothing was left to typeset
TL_T0        = TL_VARS + 70     ; scratch
TL_T1        = TL_VARS + 72
TL_T2        = TL_VARS + 74
TL_T3        = TL_VARS + 76
TL_N         = TL_VARS + 78     ; how many letters a write takes
TL_DIG_N     = TL_VARS + 80     ; a right-aligned number: how many digits
TL_DIG       = TL_VARS + 82     ; and the digits, as letters of the font
TL_SRC       = TL_VARS + 90     ; the row whose tiles the chosen one takes
TL_RUN_RI    = TL_VARS + 92     ; the open run's row, as a row
TL_DN        = TL_VARS + 94     ; `tl_choose`: how many rows changed
TL_DJ        = TL_VARS + 96     ; and which one of those it looks at
TL_DL        = TL_VARS + 98     ; the changed rows, one byte each
TL_NEW       = TL_DL + TL_ROWS + 1 ; per pair: nonzero if the screen never showed it
TL_SWITCHED  = TL_NEW + TL_PAIRS ; nonzero: `TL_NEW` has to be cleared
TL_KEEP_X    = TL_SWITCHED + 2 ; `tl_idle` keeps the caller's X,
TL_KEEP_Y    = TL_SWITCHED + 4 ; Y
TL_KEEP_G    = TL_SWITCHED + 6 ; and `comp_glyph`, three bytes
TL_PRE       = TL_SWITCHED + 10 ; which tables `tl_glyph` reads: 0 the
                                ; screens', `TL_SLOT_PRE` the menu bank's
TL_STRIP_NEXT = TL_SWITCHED + 12 ; `tl_strip`: the next free tile of the bank
TL_STRIP_CELL = TL_SWITCHED + 14 ; the strip's upper left tilemap word
TL_STRIP_CAP = TL_SWITCHED + 16 ; how many letters and cells, at most
TL_STRIP_N   = TL_SWITCHED + 18 ; how many letters, without the padding
TL_STRIP_T   = TL_SWITCHED + 20 ; its first tile
TL_STRIP_K   = TL_SWITCHED + 22 ; and how many columns, a pair of tiles each
TL_SLOT_T    = TL_SWITCHED + 24 ; the slot screen's names: each one's tile
TL_SLOT_K    = TL_SLOT_T + 2 * TL_SLOTS ; and columns, 0 not composed yet
TL_END       = TL_SLOT_K + 2 * TL_SLOTS
.assert TL_END <= FAR_TEXT_LAYER_END, error, "the text layer does not fit in its RAM"

; A letter that is not in the font: a blank as wide as a digit, which pads a
; number on the left so that numbers line up in a column. `FIGURE_BLANK` in
; `rm2k-snes-text`.
TL_FIGURE    = 96
; With the screen on, typesetting goes on **until this scanline**, and stops
; there until the next frame: the screen's loop reads the pad once per frame,
; and a loop that overruns its frame loses a press that lasts one —the tests
; press for one frame, and that is how it was found—. A letter is some eight
; lines, so the last one ends before the vblank.
TL_LAST_LINE = 212
; And until this one for the steps that are not a letter, which take longer:
; adopting a row or finishing one is some thirty lines.
TL_LAST_STEP = 180
SLHV         = $2137            ; reading it latches the counters
OPVCT        = $213D            ; the line, low byte and then bit 8
; How many pairs go up in one vblank, at most: with the tilemap and the
; screen's own uploads —the cursor bar— the vblank fills up, and an upload
; that falls out of it is lost. A row with more goes up over two.
TL_PAIRS_PER_VBLANK = 32
; Where a run starts inside its cell, and where the glyph's first row goes
; inside a line's two cell rows: the screens stage's geometry, `SCR_TEXT_X`
; and `SCR_TEXT_Y`. `tl_row_ofs` is built for the second.
TL_XOFS      = SCR_TEXT_X
TL_OFS_Y     = SCR_TEXT_Y
.assert TL_OFS_Y = 2, error, "tl_row_ofs puts a glyph's first row at row 2 of its line"
; A pair: two tiles of 4bpp, 32 words, from `SLOT_VRAM`. Pair 0 is never
; handed out: tile 0 is the blank one, which the cells without text point
; to.
TL_PAIR_WORDS = 32
; The slot screen's slots `tl_slot_name` keeps a name for.
TL_SLOTS     = 8
.assert SRAM_SLOTS_N <= TL_SLOTS, error, "tl_slot_name keeps a name per slot"
; The menu bank's tables in `scr_pre_lo` and `scr_pre_bk`.
TL_SLOT_PRE  = 16
; Where the menu bank's strips go: from the first even tile after its own,
; up to its tilemap.
TL_STRIP_FIRST = (SLOT_TILES + 1) & $FFFE
TL_STRIP_LAST  = (SLOT_MAP - SLOT_VRAM) / 16

; Where row k of a glyph lands in a column of the stage: rows 2 to 7 of the
; top tile, then rows 0 to 6 of the bottom one, two bytes per row.
tl_row_ofs:
    .word 4, 6, 8, 10, 12, 14, 32, 34, 36, 38, 40, 42, 44
; Where each row's record starts, counted from `TL_CUR` —or `TL_SHOWN`—.
tl_rec_ofs:
    .repeat TL_ROWS, R
    .word R * TL_RECORD
    .endrepeat
tl_zero:
    .word 0
; Sets the data bank to $7E, pushing the old one: `plb` before `rtl`. A8.
.macro tl_enter
    phb
    lda #$7E
    pha
    plb
.endmacro

; A new screen, with the screen off: A16 is how many pairs of tiles its text
; may take. Every record empty, every cell blank, the whole pool free, and the
; next upload composes everything.
.proc tl_reset
.a16
.i16
    tax
    sep #$20
.a8
    tl_enter
    rep #$20
.a16
    stx TL_FREE_N
    ; The pool: pairs n down to 1, so that 1 is on top.
    txa
    ldx #0
free:
    sep #$20
.a8
    sta TL_FREE, x
    rep #$20
.a16
    inx
    dec a
    bne free
    ldx #0
map:
    stz TL_MAP, x
    inx
    inx
    cpx #(32 * 28 * 2)
    bcc map
    ldx #0
pairs:
    stz TL_PAIR, x
    inx
    inx
    cpx #(TL_ROWS * TL_COLS)
    bcc pairs
    ldx #0
refs:
    stz TL_REFS, x
    stz TL_NEW, x
    inx
    inx
    cpx #TL_PAIRS
    bcc refs
    ldx #0
flags:
    stz TL_FLAG, x              ; and the empty record's signature is 0
    stz TL_CSIG, x
    stz TL_SSIG, x
    inx
    inx
    cpx #28
    bcc flags
    ldy #0
records:
    tyx
    lda f:tl_rec_ofs, x
    tax
    sep #$20
.a8
    stz TL_CUR, x
    stz TL_SHOWN, x
    rep #$20
.a16
    iny
    iny
    cpy #(TL_ROWS * 2)
    bcc records
    stz TL_PEND_N
    stz TL_UP_N
    stz TL_UP_I
    stz TL_RUN
    stz TL_SCAN
    stz TL_IDLE_DONE
    stz TL_MAP_DIRTY
    stz TL_FLUSH
    stz TL_LEFT
    stz TL_SWITCHED
    stz TL_PRE
    lda #$FFFF
    sta TL_T_ROW
    sta TL_PEN_PICK
    lda #1
    sta TL_SETTLE
    sep #$20
.a8
    sta tl_on                   ; `wait_vblank` typesets from now on
    plb
    rtl
.endproc

; Every record empty, to be written again. What the screen shows does not
; change until the rows are typeset.
.proc tl_clear
.a8
.i16
    tl_enter
    rep #$20
.a16
    ldx #0
records:
    phx
    lda f:tl_rec_ofs, x
    tax
    sep #$20
.a8
    stz TL_CUR, x
    rep #$20
.a16
    pla
    pha
    lsr a
    tax
    sep #$20
.a8
    lda #TL_WRITTEN
    sta TL_FLAG, x
    rep #$20
.a16
    plx
    inx
    inx
    cpx #(TL_ROWS * 2)
    bcc records
    jsr tl_no_pen
    sep #$20
.a8
    plb
    rtl
.endproc

; Row A8's record empty: what the battle does with a line it writes again.
.proc tl_clear_row
.a8
.i16
    tl_enter
    rep #$20
.a16
    and #$00FF
    cmp #TL_ROWS
    bcs out
    tay
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    sep #$20
.a8
    stz TL_CUR, x
    lda #TL_WRITTEN
    sta TL_FLAG, y
    rep #$20
.a16
    jsr tl_no_pen
out:
    sep #$20
.a8
    plb
    rtl
.endproc

; Row A16 written, and it is the open run's. Keeps A. A16.
.proc tl_mark
.a16
.i16
    sta TL_RUN_RI
    tax
    sep #$20
.a8
    lda #TL_WRITTEN
    sta TL_FLAG, x
    rep #$20
.a16
    lda TL_RUN_RI
    rts
.endproc

; No run open and no write to continue; and something to typeset. A16.
.proc tl_no_pen
.a16
.i16
    stz TL_RUN
    stz TL_IDLE_DONE
    lda #$FFFF
    sta TL_PEN_PICK
    rts
.endproc

; --- writing ---------------------------------------------------------------

; A run at `pick_table` in colour `temp + 1`, or the open one if this write
; continues it —starts where the last one ended, in the same colour—. Leaves X
; on the record's next free byte. Data bank $7E, A16.
.proc tl_open
.a16
.i16
    stz TL_IDLE_DONE            ; there is something to typeset
    lda temp + 1
    and #$00FF
    sta TL_T1                   ; the colour
    lda TL_RUN
    beq fresh
    lda pick_table
    cmp TL_PEN_PICK
    bne fresh
    lda TL_T1
    cmp TL_PEN_VAR
    bne fresh
    ; It continues, on the run's row even if `pick_table` went past the
    ; row's last cell —a line of the battle's longer than 32 letters—.
    ldx TL_RUN_RI
    sep #$20
.a8
    lda #TL_WRITTEN
    sta TL_FLAG, x
    rep #$20
.a16
    ldx TL_RUN_ROW
    lda TL_CUR, x
    and #$00FF
    sta TL_T0
    txa
    sec                         ; one more: past the length byte
    adc TL_T0
    tax
    rts
fresh:
    ; A new run at its cell: x = 8 * column + TL_XOFS. A row past the last
    ; a line can start on takes nothing.
    lda pick_table
    and #$003E
    asl a
    asl a                       ; column * 8
    clc
    adc #TL_XOFS
    sta TL_T0
    lda pick_table
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the row: 64 bytes each
    cmp #TL_ROWS
    bcc a_row
    stz TL_RUN
    ldx #0                      ; a place nobody reads: `tl_put` ignores it
    rts
a_row:
    jsr tl_mark
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    ; With that x the row may already have one, from before a write that
    ; goes over it: that one goes.
    jsr tl_drop_at
    jmp tl_append
.endproc

; Takes out of the record at X —the row's offset— the run that starts at
; x `TL_T0`, if there is one. Keeps X. A16.
.proc tl_drop_at
.a16
.i16
    stx TL_T2                   ; the record
    lda TL_CUR, x
    and #$00FF
    sec
    adc TL_T2
    sta TL_T3                   ; where the record ends
    txa
    inc a
    tay                         ; its first run
run:
    cpy TL_T3
    bcs none
    lda TL_CUR + 2, y
    and #$00FF
    clc
    adc #3
    sta TL_N                    ; the run's bytes
    lda TL_CUR, y
    and #$00FF
    cmp TL_T0
    beq found
    tya
    clc
    adc TL_N
    tay
    bra run
found:
    ; The run's bytes go: what follows moves down.
    tya
    clc
    adc TL_N
    tax                         ; the first byte after it
    sep #$20
.a8
move:
    cpx TL_T3
    bcs moved
    lda TL_CUR, x
    sta TL_CUR, y
    inx
    iny
    bra move
moved:
    ldx TL_T2
    lda TL_CUR, x
    sec
    sbc TL_N
    sta TL_CUR, x               ; the shorter length
    rep #$20
.a16
none:
    ldx TL_T2
    rts
.endproc

; Appends an empty run at x `TL_T0`, colour `TL_T1`, to the record at X —the
; row's offset—, and leaves X on its first letter and `TL_RUN` on its count.
; With no room, no run. A16.
.proc tl_append
.a16
.i16
    stz TL_IDLE_DONE
    stx TL_RUN_ROW
    lda TL_CUR, x
    and #$00FF
    cmp #(TL_RECORD - 4)
    bcc room
    stz TL_RUN
    rts
room:
    sta TL_T2
    clc
    adc #3
    sep #$20
.a8
    sta TL_CUR, x               ; the longer length
    rep #$20
.a16
    txa
    sec
    adc TL_T2
    tax                         ; the first byte after the old runs
    sep #$20
.a8
    lda TL_T0
    sta TL_CUR, x
    lda TL_T1
    sta TL_CUR + 1, x
    stz TL_CUR + 2, x
    rep #$20
.a16
    txa
    inc a
    inc a
    sta TL_RUN
    inx
    inx
    inx
    rts
.endproc

; Letter A8 —the font's index— at X, in the open run. Moves X. A8.
.proc tl_put
.a8
.i16
    pha
    lda TL_RUN
    ora TL_RUN + 1
    beq full
    ldy TL_RUN_ROW
    lda TL_CUR, y
    cmp #(TL_RECORD - 1)
    bcs full
    inc a
    sta TL_CUR, y               ; one more byte in the record
    pla
    sta TL_CUR, x
    inx
    phx
    ldx TL_RUN
    inc TL_CUR, x               ; one more letter in the run
    plx
    rts
full:
    pla
    rts
.endproc

; After a write of A8 cells: `pick_table` moves on, as before, and the next
; write that starts there continues the run.
.proc tl_moved
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc pick_table
    sta pick_table
    sta TL_PEN_PICK
    lda TL_T1
    sta TL_PEN_VAR
    sep #$20
.a8
    rts
.endproc

; `scr_glyph`: letter A8, in ASCII, at `pick_table` in colour `temp + 1`.
.proc tl_letter
.a8
.i16
    pha
    tl_enter
    rep #$20
.a16
    jsr tl_open
    sep #$20
.a8
    lda 2, s                    ; the letter, under the data bank
    sec
    sbc #' '
    jsr tl_put
    lda #1
    jsr tl_moved
    plb
    pla
    rtl
.endproc

; `scr_text`: text X —see `item_txt_*`— at `pick_table` in colour
; `temp + 1`, and no more than `comp_dup + 3` letters.
.proc tl_text
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; how many letters
    tl_enter
    ; The cap is in cells, and it was in letters while a letter took one: now
    ; it is as many letters as fit in those cells' pixels.
    lda comp_dup + 3
    cmp #255
    beq whole
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    sta TL_T0                   ; the cap, in pixels
    stz TL_T1                   ; the width so far
    ldy #0
fit:
    tya
    sep #$20
.a8
    cmp temp
    rep #$20
.a16
    bcs fitted
    lda [msg_ptr], y
    and #$00FF
    sec
    sbc #' '
    tax
    lda f:font_advance, x
    and #$00FF
    clc
    adc TL_T1
    cmp TL_T0
    beq in
    bcs fitted
in:
    sta TL_T1
    iny
    bra fit
fitted:
    sep #$20
.a8
    tya
    sta temp
whole:
    rep #$20
.a16
    jsr tl_open
    sep #$20
.a8
    lda temp                    ; after `tl_open`: `tl_drop_at` uses `TL_N`
    sta TL_N
    stz TL_N + 1
    ldy #0
letter:
    cpy TL_N
    bcs ready
    lda [msg_ptr], y
    sec
    sbc #' '
    phy
    jsr tl_put
    ply
    iny
    bra letter
ready:
    lda TL_N
    jsr tl_moved
    lda #255
    sta comp_dup + 3            ; the cap is for one text only
    plb
    rtl
.endproc

; `scr_number`: `comp_dup`, 0 to 999, in `comp_dup + 2` places —2 or 3—, at
; `pick_table` in colour `temp + 1`. The places a number does not reach go
; blank and as wide as a digit, so numbers line up on the right.
.proc tl_number
.a8
.i16
    tl_enter
    rep #$20
.a16
    jsr tl_open
    stz TL_T3                   ; whether a digit went already
    lda comp_dup + 2
    and #$00FF
    cmp #3
    bcc tens
    ldy #0
hundred:
    lda comp_dup
    cmp #100
    bcc hundred_ready
    sbc #100
    sta comp_dup
    iny
    bra hundred
hundred_ready:
    jsr digit
tens:
    ldy #0
ten:
    lda comp_dup
    cmp #10
    bcc ten_ready
    sbc #10
    sta comp_dup
    iny
    bra ten
ten_ready:
    jsr digit
    lda comp_dup                ; the units, always
    sep #$20
.a8
    clc
    adc #('0' - ' ')
    jsr tl_put
    lda comp_dup + 2
    jsr tl_moved
    plb
    rtl

; Y: a digit. A zero before every other one goes out as a figure blank.
.a16
digit:
    tya
    bne write
    lda TL_T3
    bne write
    sep #$20
.a8
    lda #TL_FIGURE
    jsr tl_put
    rep #$20
.a16
    rts
write:
    sep #$20
.a8
    clc
    adc #('0' - ' ')
    jsr tl_put
    lda #1
    sta TL_T3
    rep #$20
.a16
    rts
.endproc

; A number already in digits, right-aligned so that its last digit ends with
; the cell at `pick_table`: the shop's gold and prices, which have no fixed
; number of places. The digits are in `TL_DIG`, the first one first, as
; letters of the font, and `TL_DIG_N` of them, at most eight: the caller
; writes them there, with `$7E0000 +` the address. In colour `temp + 1`;
; `pick_table` is left on the cell after it, and nothing continues the run.
.proc tl_right
.a8
.i16
    tl_enter
    rep #$20
.a16
    stz TL_IDLE_DONE
    lda temp + 1
    and #$00FF
    sta TL_T1
    ; Its width: a digit's advance times how many.
    lda f:font_advance + ('0' - ' ')
    and #$00FF
    sta TL_T2
    lda TL_DIG_N
    and #$00FF
    sta TL_DIG_N
    tay
    lda #0
    cpy #0
    beq measured
width:
    clc
    adc TL_T2
    dey
    bne width
measured:
    sta TL_T2                   ; the run's width
    ; x = 8 * (column + 1) + TL_XOFS - 1 - width: the last digit's advance
    ; ends with the cell.
    lda pick_table
    and #$003E
    asl a
    asl a
    clc
    adc #(8 + TL_XOFS - 1)
    sec
    sbc TL_T2
    sta TL_T0
    lda pick_table
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the row: 64 bytes each
    cmp #TL_ROWS
    bcs out
    jsr tl_mark
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    jsr tl_drop_at
    jsr tl_append
    sep #$20
.a8
    ldy #0
digit:
    cpy TL_DIG_N
    bcs ready
    lda TL_DIG, y
    phy
    jsr tl_put
    ply
    iny
    bra digit
ready:
    rep #$20
.a16
out:
    stz TL_RUN                  ; nothing continues a right-aligned run
    sep #$20
.a8
    lda #1
    jsr tl_moved
    plb
    rtl
.endproc

; --- uploading -----------------------------------------------------------------

; In the vblank: the tiles of the row typeset last —to pairs the tilemap on
; screen does not point to, so they do not show yet—, `TL_PAIRS_PER_VBLANK` at
; most.
.proc tl_vblank
.a8
.i16
    tl_enter
    jsr tl_dma_pairs
    plb
    rtl
.endproc

.proc tl_dma_pairs
.a8
.i16
    rep #$20
.a16
    lda TL_UP_N
    bne some
    sep #$20
.a8
    rts
.a16
some:
    ; Up to `TL_PAIRS_PER_VBLANK` from where the last vblank left off; with
    ; the screen off, all of them.
    lda TL_SETTLE
    beq capped
    lda TL_UP_N
    bra stop
capped:
    lda TL_UP_I
    clc
    adc #TL_PAIRS_PER_VBLANK
    cmp TL_UP_N
    bcc stop
    lda TL_UP_N
stop:
    sta TL_T2                   ; where this one stops
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$7E
    sta f:A1B0
    rep #$20
.a16
    lda TL_UP_I
    asl a
    tax
pair:
    lda TL_UPLOAD + 1, x        ; the pair
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 words each
    clc
    adc #SLOT_VRAM
    sta f:VMADDL
    lda TL_UPLOAD, x            ; the column
    and #$00FF
    xba
    lsr a
    lsr a                       ; 64 bytes each
    clc
    adc #TL_STAGE
    sta f:A1T0L
    lda #64
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    inx
    inx
    txa
    lsr a
    cmp TL_T2
    bcc pair
    sta TL_UP_I
    cmp TL_UP_N
    bcc more                    ; the rest, next vblank
    stz TL_UP_N
    stz TL_UP_I
more:
    sep #$20
.a8
    rts
.endproc

; In the vblank: the tilemap, 1792 bytes in one DMA —when it changed, its
; tiles are all up, and either nothing is left to typeset or the pool ran out
; and has to be recycled—. After it, the pairs nothing on screen points to any
; more are free.
.proc tl_map
.a8
.i16
    tl_enter
    rep #$20
.a16
    lda TL_UP_N
    bne not_now
    lda TL_MAP_DIRTY
    beq not_now
    lda TL_IDLE_DONE
    ora TL_FLUSH
    beq not_now
    sep #$20
.a8
    jsr tl_switch
not_now:
    sep #$20
.a8
    plb
    rtl
.endproc

; The tilemap up, and what was waiting for it, free. A8, data bank $7E.
.proc tl_switch
.a8
.i16
    lda #$80
    sta f:VMAIN
    rep #$20
.a16
    lda #SLOT_MAP
    sta f:VMADDL
    lda #TL_MAP
    sta f:A1T0L
    lda #(32 * 28 * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #$7E
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    stz TL_MAP_DIRTY
    stz TL_FLUSH
    lda #1
    sta TL_SWITCHED             ; `tl_step` clears `TL_NEW`, out of the vblank
    ldy #0
recycle:
    cpy TL_PEND_N
    bcs recycled
    ldx TL_FREE_N
    sep #$20
.a8
    lda TL_PEND, y
    sta TL_FREE, x
    rep #$20
.a16
    inc TL_FREE_N
    iny
    bra recycle
recycled:
    stz TL_PEND_N
    sep #$20
.a8
    rts
.endproc

; With the screen off —the first `scr_upload` after `tl_reset`—, everything:
; row by row, each one's tiles up as soon as it is done, and then the
; tilemap. Any other time it does nothing: `tl_idle` typesets.
.proc tl_work
.a8
.i16
    tl_enter
    rep #$20
.a16
    lda TL_SETTLE
    bne settle
    sep #$20
.a8
    plb
    rtl
settle:
.a16
    lda comp_glyph              ; the composer borrows it
    pha
    lda comp_glyph + 2
    pha
    lda #$FFFF
    sta TL_LEFT                 ; no budget
step:
    lda TL_FLUSH
    beq go
    sep #$20
.a8
    jsr tl_switch               ; the pool ran out: recycle it now
    rep #$20
.a16
go:
    jsr tl_step
    lda #0
    rol a                       ; whether there was nothing to do
    sta TL_DONE
    sep #$20
.a8
    jsr tl_dma_pairs
    rep #$20
.a16
    lda TL_DONE
    beq step
    stz TL_SETTLE
    stz TL_LEFT
    pla
    sep #$20
.a8
    sta comp_glyph + 2
    rep #$20
.a16
    pla
    sta comp_glyph
    sep #$20
.a8
    jsr tl_switch
    plb
    rtl
.endproc

; While `wait_vblank` waits: typesets what changed, letter by letter, until
; the frame reaches `TL_LAST_LINE`. Returns at once if there is nothing to
; do, which is what it finds on the map. Keeps X and Y.
;
; What it keeps it keeps in the layer's RAM and not on the stack: it is
; called from the bottom of the battle's loop, which is the deepest the
; stack goes —`test_pila.py`—.
.proc tl_idle
.a8
.i16
    tl_enter
    lda TL_IDLE_DONE
    beq work
    plb
    rtl
work:
    rep #$20
.a16
    stx TL_KEEP_X
    sty TL_KEEP_Y
    lda comp_glyph              ; the composer borrows it: the screen's it is
    sta TL_KEEP_G
    lda comp_glyph + 2
    sta TL_KEEP_G + 2
again:
    jsr tl_late
    bcs late
    jsr tl_step
    bcc again
    lda #1
    sta TL_IDLE_DONE            ; until a screen writes again
late:
    lda TL_KEEP_G
    sta comp_glyph
    sep #$20
.a8
    lda TL_KEEP_G + 2
    sta comp_glyph + 2
    ldx TL_KEEP_X
    ldy TL_KEEP_Y
    plb
    rtl
.endproc

; Whether the frame is over for typesetting: carry set from `TL_LAST_LINE`
; on, the vblank's lines included. `tl_idle` only runs after a vblank ended
; —`wait_vblank` waits for that first—, so a line past the visible ones is
; the next vblank, which a step that took longer than expected reached: it
; has to stop there too, or it would go on through it, and the screen's loop
; would lose that frame. A16.
.proc tl_late
.a16
.i16
    jsr tl_line
    cmp #TL_LAST_LINE           ; carry set from there on
    rts
.endproc

; The line the frame is on. A16.
.proc tl_line
.a16
.i16
    sep #$20
.a8
    lda f:STAT78                ; resets the counters' flip-flop
    lda f:SLHV
    lda f:OPVCT
    xba
    lda f:OPVCT
    and #$01
    xba
    rep #$20
.a16
    rts
.endproc

; --- typesetting ---------------------------------------------------------------

; One step: a row whose record changed takes the tiles of a row that says
; what it says now, if there is one; if not, it starts being typeset,
; composes letters while the frame allows, and is finished if it got to its
; end. Nothing while a row's tiles wait for the vblank, nor while the pool
; waits for the tilemap to switch. Returns with carry set when there was
; nothing to do at all. A16.
.proc tl_step
.a16
.i16
    lda TL_SWITCHED
    beq not_switched
    jsr tl_not_new
not_switched:
    lda TL_UP_N
    bne busy
    lda TL_T_ROW
    cmp #$FFFF
    bne going
    lda TL_FLUSH
    bne busy
    jsr tl_late_step
    bcs busy
    jsr tl_resolve
    bcc busy                    ; the frame ended first
    jsr tl_choose
    bcc chosen
    rts                         ; nothing changed
chosen:
    ldx TL_SRC
    cpx #$FFFF
    beq typeset
    jsr tl_adopt                ; A this one, `TL_SRC` the one it copies
    bra busy
typeset:
    ; A row takes at most a pair per column. If fewer are free and some
    ; wait for the switch, the switch goes first; if none wait, what does not
    ; fit stays blank.
    pha
    lda TL_FREE_N
    cmp #TL_COLS
    bcs room
    lda TL_PEND_N
    beq room
    pla
    lda #1
    sta TL_FLUSH
    bra busy
room:
    pla
    jsr tl_begin
going:
    jsr tl_letters
    bcc busy
    jsr tl_late_step            ; the letters are done: it finishes next time
    bcs busy
    jsr tl_finish
busy:
    clc
    rts
.endproc

; Whether it is too late for a step that is not a letter —resolving,
; choosing, adopting a row, finishing one—: carry set from `TL_LAST_STEP`.
; Those take longer than a letter and are not cut halfway, so they stop
; earlier: one that started at `TL_LAST_LINE` would end in the vblank, and the
; screen's uploads with it. Never with the screen off. A16.
.proc tl_late_step
.a16
.i16
    lda TL_LEFT
    beq budget
    clc
    rts
budget:
    jsr tl_line
    cmp #TL_LAST_STEP
    rts
.endproc

; After a switch every pair the tilemap points to is on screen: none is new.
; Through the WRAM port, a DMA from a fixed zero. A16.
.proc tl_not_new
.a16
.i16
    stz TL_SWITCHED
    lda #TL_NEW
    sta f:WMADDL
    sep #$20
.a8
    lda #0                      ; bit 16 of the 17: 0 is bank $7E
    sta f:WMADDH
    lda #$08                    ; one register, the source does not move
    sta f:DMAP0
    lda #<WMDATA
    sta f:BBAD0
    lda #^tl_zero
    sta f:A1B0
    rep #$20
.a16
    lda #.loword(tl_zero)
    sta f:A1T0L
    lda #TL_PAIRS
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    rts
.endproc
.assert TL_NEW >= $2000 && TL_NEW + TL_PAIRS <= $10000, error, "tl_not_new clears TL_NEW through WMADD, in bank $7E"

; The rows written since they were last looked at: each one's signature, and
; whether it says something other than what `TL_MAP` says. A row written
; with what it already said —a screen writes everything again on each
; change— goes back to clean here. A row at a time, and it stops if the frame
; is over: carry set when every row is resolved. With the screen off it does
; not look at the frame. A16.
.proc tl_resolve
.a16
.i16
    ldy #0
row:
    lda TL_FLAG, y
    and #$00FF
    cmp #TL_WRITTEN
    bne next
    lda TL_LEFT
    bne in_time                 ; no budget
    phy
    jsr tl_late
    ply
    bcc in_time
    clc
    rts
in_time:
    sty TL_T0
    tya
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    jsr tl_sig                  ; of `TL_CUR` + X
    ldy TL_T0
    sep #$20
.a8
    sta TL_CSIG, y
    cmp TL_SSIG, y
    rep #$20
.a16
    bne dirty
    tya
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    tay
    jsr tl_equal
    ldy TL_T0
    bcs dirty
    sep #$20
.a8
    lda #0
    sta TL_FLAG, y              ; the same as before: clean
    rep #$20
.a16
    bra next
dirty:
    sep #$20
.a8
    lda #TL_DIRTY
    sta TL_FLAG, y
    rep #$20
.a16
next:
    iny
    cpy #TL_ROWS
    bcc row
    sec
    rts
.endproc

; The signature of the record at `TL_CUR` + X: the sum of its bytes, its
; length's included, in A8's worth. Two records that say the same have the
; same one; two that do not, almost never. A16 in and out, the sum in A.
.proc tl_sig
.a16
.i16
    lda TL_CUR, x
    and #$00FF
    tay                         ; the bytes after the length
    sep #$20
.a8
    lda TL_CUR, x               ; the length's counts too
    cpy #0
    beq summed
sum:
    inx
    clc
    adc TL_CUR, x
    dey
    bne sum
summed:
    rep #$20
.a16
    and #$00FF
    rts
.endproc

; Which changed row goes next, in A, and in `TL_SRC` the row it can take
; the tiles of, or $FFFF if it has to be typeset; carry set if none
; changed. A16.
;
; **The order is what lets a list scroll either way.** A row that takes
; another's tiles takes what that one says on screen now, and a row that is
; replaced loses what it said. So a row goes first if no other changed row
; needs what it says now: scrolling down, the top one, whose item left the
; list; scrolling up, the bottom one. And a row that has a source goes before
; one that has to be typeset. If every changed row is needed by another —two
; that swapped— the first one goes, and the other is typeset.
;
; It runs once per row that adopts, so it has to be cheap: the changed rows
; go to a list first, the "needed" question only looks at those, and the
; source is looked for by signature, a byte at a time, before comparing any
; record. Looking at every pair of rows was half a frame per call, and a list
; that scrolled took four frames only choosing.
.proc tl_choose
.a16
.i16
    lda #$FFFF
    sta TL_SRC
    sta TL_T2                   ; the first that is not needed and has no source
    ; The changed rows, in order.
    sep #$20
.a8
    ldx #0
    ldy #0
list:
    lda TL_FLAG, y
    cmp #TL_DIRTY
    bne not_changed
    tya
    sta TL_DL, x
    inx
not_changed:
    iny
    cpy #TL_ROWS
    bcc list
    rep #$20
.a16
    stx TL_DN
    txa
    bne some
    sec                         ; none changed
    rts
some:
    lda TL_DL
    and #$00FF
    sta TL_T3                   ; the first changed one
    stz TL_T0                   ; where in the list
row:
    ldx TL_T0
    lda TL_DL, x
    and #$00FF
    sta TL_T1                   ; this one
    ; Is what it says now needed by another changed row?
    stz TL_DJ
needed:
    lda TL_DJ
    cmp TL_DN
    bcs not_needed
    tax
    lda TL_DL, x
    and #$00FF
    cmp TL_T1
    beq next_needed
    tay                         ; that one
    sep #$20
.a8
    lda TL_CSIG, y              ; what that one will say
    ldx TL_T1
    cmp TL_SSIG, x              ; against what this one says
    rep #$20
.a16
    bne next_needed
    tya
    asl a
    tax
    lda f:tl_rec_ofs, x
    pha
    lda TL_T1
    asl a
    tax
    lda f:tl_rec_ofs, x
    tay
    plx
    jsr tl_equal
    bcs next_needed
    jmp next                    ; needed: later
next_needed:
    inc TL_DJ
    bra needed
not_needed:
    ; Not needed. Does a row say now what it will say?
    ldx TL_T1
    sep #$20
.a8
    lda TL_CSIG, x
    ldy #0
scan:
    cmp TL_SSIG, y
    beq maybe
scan_on:
    iny
    cpy #TL_ROWS
    bcc scan
    rep #$20
.a16
    bra no_source
.a8
maybe:
    cpy TL_T1
    beq scan_on                 ; itself
    rep #$20
.a16
    sty TL_DJ
    lda TL_T1
    asl a
    tax
    lda f:tl_rec_ofs, x
    pha
    tya
    asl a
    tax
    lda f:tl_rec_ofs, x
    tay
    plx
    jsr tl_equal
    ldy TL_DJ
    bcs differs
    sty TL_SRC
    lda TL_T1
    clc
    rts
differs:
    ldx TL_T1
    sep #$20
.a8
    lda TL_CSIG, x
    bra scan_on
.a16
no_source:
    lda TL_T2
    cmp #$FFFF
    bne next
    lda TL_T1
    sta TL_T2
next:
    inc TL_T0
    lda TL_T0
    cmp TL_DN
    bcs done
    jmp row
done:
    lda TL_T2
    cmp #$FFFF
    bne go
    lda TL_T3
go:
    clc
    rts
.endproc

; Whether row A16's record differs from what `TL_MAP` says it says: carry
; set if it does. Keeps A. A16.
.proc tl_differs
.a16
.i16
    pha
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    tay
    jsr tl_equal
    pla
    rts
.endproc

; Whether the records at `TL_CUR` + X and `TL_SHOWN` + Y are the same: carry
; clear if they are. A16.
.proc tl_equal
.a16
.i16
    sep #$20
.a8
    lda TL_CUR, x
    cmp TL_SHOWN, y
    bne differ                  ; not even the same length
    sta TL_N
    cmp #0
    beq same
compare:
    inx
    iny
    lda TL_CUR, x
    cmp TL_SHOWN, y
    bne differ
    dec TL_N
    bne compare
same:
    rep #$20
.a16
    clc
    rts
.a8
differ:
    rep #$20
.a16
    sec
    rts
.endproc

; Row A16 takes the tiles of row `TL_SRC`, which says on screen what A16
; will say: its pairs, each counting one more, and its two cells of tilemap
; per column. What A16 had goes. A16.
.proc tl_adopt
.a16
.i16
    sta TL_T0
    jsr tl_release_row
    lda TL_T0
    asl a
    asl a
    asl a
    asl a
    asl a
    tay                         ; this one's first cell
    lda TL_SRC
    asl a
    asl a
    asl a
    asl a
    asl a
    tax                         ; and the source's
    lda #TL_COLS
    sta TL_N
    sep #$20
.a8
column:
    lda TL_PAIR, x
    beq empty
    sta TL_PAIR, y
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    inc TL_REFS, x
    rep #$20
.a16
    ; Its two tilemap words: a cell's is at twice its index.
    lda 1, s
    asl a
    tax
    lda TL_MAP, x
    sta TL_GG
    lda TL_MAP + 64, x
    sta TL_SS
    tya
    asl a
    tax
    lda TL_GG
    sta TL_MAP, x
    lda TL_SS
    sta TL_MAP + 64, x
    plx
    sep #$20
.a8
empty:
    inx
    iny
    dec TL_N
    bne column
    rep #$20
.a16
    lda TL_T0
    jsr tl_shown_now
    lda #1
    sta TL_MAP_DIRTY
    rts
.endproc

; Row A16's pairs go: each one counts one less, and the one nobody points to
; any more is free again —if the screen never showed it— or waits for the
; switch; its cells of the tilemap go blank. Leaves its first cell in
; `TL_T2` and its first tilemap byte in `TL_T3`. A16.
.proc tl_release_row
.a16
.i16
    asl a
    asl a
    asl a
    asl a
    asl a
    sta TL_T2                   ; its first cell
    tay
    asl a
    sta TL_T3                   ; its first tilemap byte
    lda #TL_COLS
    sta TL_T1
    sep #$20
.a8
column:
    lda TL_PAIR, y
    beq empty
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #0
    sta TL_PAIR, y
    dec TL_REFS, x
    bne still
    lda TL_NEW, x
    beq shown
    stz TL_NEW, x               ; never on screen: free now
    txa
    ldx TL_FREE_N
    sta TL_FREE, x
    inc TL_FREE_N
    bra still
shown:
    txa
    ldx TL_PEND_N
    sta TL_PEND, x
    inc TL_PEND_N
still:
    rep #$20
.a16
    tya
    asl a
    tax
    stz TL_MAP, x
    stz TL_MAP + 64, x
    lda #1
    sta TL_MAP_DIRTY
    sep #$20
.a8
empty:
    iny
    dec TL_T1
    bne column
    rep #$20
.a16
    rts
.endproc
.assert TL_PAIRS <= 256, error, "tl_release_row counts the free and pending pairs a byte at a time"

; Row A16's record is now what `TL_MAP` says: copied to `TL_SHOWN`. A16.
.proc tl_shown_now
.a16
.i16
    asl a
    pha
    tax
    lda f:tl_rec_ofs, x
    tax
    ldy #(TL_RECORD / 2)
copy:
    lda TL_CUR, x
    sta TL_SHOWN, x
    inx
    inx
    dey
    bne copy
    ; And its signature, which `tl_resolve` already took of the record, and
    ; it is clean.
    pla
    pha
    lsr a
    tax
    sep #$20
.a8
    lda TL_CSIG, x
    sta TL_SSIG, x
    stz TL_FLAG, x
    rep #$20
.a16
    pla
    rts
.endproc
.assert TL_RECORD .mod 2 = 0, error, "tl_shown_now copies a record a word at a time"

; Row A16 starts: its record is copied to what will be shown —typesetting
; reads the copy, so a screen that writes the record again meanwhile does not
; pull the ground from under it: that row is simply typeset again—, the
; stage is cleared, and no column is inked. A16.
.proc tl_begin
.a16
.i16
    sta TL_T_ROW
    jsr tl_shown_now
    lda TL_T_ROW
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    lda TL_SHOWN, x
    and #$00FF
    sta TL_T0
    txa
    clc
    adc #(TL_SHOWN + 1)
    sta TL_T_POS                ; its first run
    clc
    adc TL_T0
    sta TL_T_END
    stz TL_T_LEFT
    ; The stage, cleared through the WRAM port: a DMA from a fixed zero.
    lda #TL_STAGE
    sta f:WMADDL
    sep #$20
.a8
    lda #0                      ; bit 16 of the 17: 0 is bank $7E
    sta f:WMADDH
    lda #$08                    ; one register, the source does not move
    sta f:DMAP0
    lda #<WMDATA
    sta f:BBAD0
    lda #^tl_zero
    sta f:A1B0
    rep #$20
.a16
    lda #.loword(tl_zero)
    sta f:A1T0L
    lda #TL_STAGE_BYTES
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    ldx #0
used:
    stz TL_USED, x
    inx
    inx
    cpx #TL_COLS
    bcc used
    rts
.endproc
.assert TL_STAGE >= $2000 && TL_STAGE + TL_STAGE_BYTES <= $10000, error, "tl_begin clears the stage through WMADD, in bank $7E"

; Composes the row's letters while the frame allows. Returns with carry set
; if the row got to its end. A16.
.proc tl_letters
.a16
.i16
loop:
    lda TL_T_LEFT
    bne letter
    ; The next run: its x, its colour —which is also its ink— and how many
    ; letters.
    ldx TL_T_POS
    cpx TL_T_END
    bcc a_run
    sec
    rts
a_run:
    lda a:0, x
    and #$00FF
    sta TL_X
    lda a:1, x
    and #$00FF
    sta TL_VAR                  ; the colour: the palette of what it inks
    lda a:2, x
    and #$00FF
    sta TL_T_LEFT
    txa
    clc
    adc #3
    sta TL_T_POS
    bra loop
letter:
    lda TL_LEFT
    bne go                      ; with the screen off, no limit
    jsr tl_late
    bcc go
    clc
    rts
go:
    dec TL_T_LEFT
    ldx TL_T_POS
    inc TL_T_POS
    lda a:0, x
    and #$00FF
    cmp #TL_FIGURE
    bne normal
    lda f:font_advance + ('0' - ' ')
    and #$00FF
    clc
    adc TL_X
    sta TL_X
    jmp loop
normal:
    sta TL_C
    tax
    lda f:font_reach, x
    and #$00FF
    beq advance                 ; a blank paints nothing
    clc
    adc TL_X
    cmp #257
    bcs advance                 ; it would paint past the screen: cut
    jsr tl_glyph
advance:
    ldx TL_C
    lda f:font_advance, x
    and #$00FF
    clc
    adc TL_X
    sta TL_X
    jmp loop
.endproc

; Row K of a glyph, at byte OFS of its column of the stage —rows 2 to 7 of
; the top tile, then 0 to 6 of the bottom one, as `tl_row_ofs` says—: in
; each of its two columns, what is kept and what is set in planes 0-1 and
; 2-3, from the glyph's data at 12 * K. A column it does not touch is $FFFF.
.macro tl_glyph_row K, OFS
    lda TL_BASE
    clc
    adc #OFS
    tax
    ldy #(K * 12)
    lda [comp_glyph], y
    cmp #$FFFF
    beq :+
    sta TL_KEEP
    ldy #(K * 12 + 2)
    lda a:0, x
    and TL_KEEP
    ora [comp_glyph], y
    sta a:0, x
    ldy #(K * 12 + 4)
    lda a:16, x
    and TL_KEEP
    ora [comp_glyph], y
    sta a:16, x
:   ldy #(K * 12 + 6)
    lda [comp_glyph], y
    cmp #$FFFF
    beq :+
    sta TL_KEEP
    ldy #(K * 12 + 8)
    lda a:64, x
    and TL_KEEP
    ora [comp_glyph], y
    sta a:64, x
    ldy #(K * 12 + 10)
    lda a:80, x
    and TL_KEEP
    ora [comp_glyph], y
    sta a:80, x
:
.endmacro

; Letter `TL_C` at x `TL_X` into the stage, from its already composed data:
; `scr_pre0` to `scr_pre7`, one table per phase, built by `font_prerender`
; in the screens stage for the inks' shared layout —row k is palette entry
; 1 + k, the shadow 13—, so one table paints every colour and the palette
; says which. Per row of the thirteen it touches and per each of the two
; columns: what is kept of the stage, and what is set in planes 0-1 and in
; 2-3; a column it does not touch comes with $FFFF and is skipped. It is the
; message window's `compose_char`, over the stage's columns. Marks the
; columns it inks. Clobbers `comp_glyph`, which `tl_idle` and `tl_work` keep.
; A16.
.proc tl_glyph
.a16
.i16
    sep #$20
.a8
    lda TL_C
    sta f:WRMPYA
    lda #FONT_PRE_CHAR
    sta f:WRMPYB                ; starts: what follows gives it the cycles
    rep #$20
.a16
    ; The columns it inks: the one it starts in, and the one its reach ends
    ; in, which is the same or the next.
    ldx TL_C
    lda f:font_reach, x
    and #$00FF
    dec a
    clc
    adc TL_X
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda TL_VAR
    inc a
    sta TL_USED, x
    rep #$20
.a16
    lda TL_X
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda TL_VAR
    inc a
    sta TL_USED, x
    rep #$20
.a16
    txa
    xba
    lsr a
    lsr a                       ; 64 bytes per column
    clc
    adc #TL_STAGE
    sta TL_BASE
    ; Its data: its phase's table, plus the letter times FONT_PRE_CHAR.
    lda TL_X
    and #$0007
    asl a
    clc
    adc TL_PRE                  ; the screens' tables or the menu bank's
    tax
    lda f:scr_pre_lo, x
    clc
    adc f:RDMPYL
    sta comp_glyph
    sep #$20
.a8
    lda f:scr_pre_bk, x
    sta comp_glyph + 2
    rep #$20
.a16
    ; The thirteen rows, unrolled: each one's place in the column is a
    ; constant, and so is where its data starts.
    tl_glyph_row 0, 4
    tl_glyph_row 1, 6
    tl_glyph_row 2, 8
    tl_glyph_row 3, 10
    tl_glyph_row 4, 12
    tl_glyph_row 5, 14
    tl_glyph_row 6, 32
    tl_glyph_row 7, 34
    tl_glyph_row 8, 36
    tl_glyph_row 9, 38
    tl_glyph_row 10, 40
    tl_glyph_row 11, 42
    tl_glyph_row 12, 44
    rts
.endproc
.assert FONT_PRE_ROWS = 13, error, "tl_row_ofs has a place for each of the thirteen rows"

; Where the composed glyphs of each phase start, indexed by twice the phase:
; that is why the banks go with a padding byte between them.
; After them, at `TL_SLOT_PRE`, the menu bank's: the same font, for the
; layout of that bank's text palette.
scr_pre_lo:
    .word .loword(scr_pre0), .loword(scr_pre1), .loword(scr_pre2), .loword(scr_pre3)
    .word .loword(scr_pre4), .loword(scr_pre5), .loword(scr_pre6), .loword(scr_pre7)
    .word .loword(slot_pre0), .loword(slot_pre1), .loword(slot_pre2), .loword(slot_pre3)
    .word .loword(slot_pre4), .loword(slot_pre5), .loword(slot_pre6), .loword(slot_pre7)
scr_pre_bk:
    .byte ^scr_pre0, 0, ^scr_pre1, 0, ^scr_pre2, 0, ^scr_pre3, 0
    .byte ^scr_pre4, 0, ^scr_pre5, 0, ^scr_pre6, 0, ^scr_pre7, 0
    .byte ^slot_pre0, 0, ^slot_pre1, 0, ^slot_pre2, 0, ^slot_pre3, 0
    .byte ^slot_pre4, 0, ^slot_pre5, 0, ^slot_pre6, 0, ^slot_pre7, 0

; The row is composed: its old pairs go —`tl_release_row`—, each inked column
; takes a free pair, which only it points to, and the tilemap points its two
; cells there, with the run's colour as the palette and the priority bit —the
; battle draws its scene on BG1—; those pairs are left to upload. A column
; with no pair left stays blank: what a screen needs at once is measured by
; the converter, but not against every combination. A16.
.proc tl_finish
.a16
.i16
    lda TL_T_ROW
    jsr tl_release_row          ; leaves its first cell in TL_T2, tilemap TL_T3
    stz TL_UP_N
    stz TL_UP_I
    ldy #0
column:
    lda TL_USED, y
    and #$00FF
    beq empty
    sta TL_G                    ; the colour + 1
    lda TL_FREE_N
    beq empty                   ; none left
    dec TL_FREE_N
    ldx TL_FREE_N
    lda TL_FREE, x
    and #$00FF
    sta TL_C                    ; the pair
    tax
    sep #$20
.a8
    lda #1
    sta TL_REFS, x
    sta TL_NEW, x
    rep #$20
.a16
    tya
    clc
    adc TL_T2
    tax
    sep #$20
.a8
    lda TL_C
    sta TL_PAIR, x
    rep #$20
.a16
    ; Its two tilemap words: tile 2 * pair and the one after, the palette
    ; and the priority.
    lda TL_G
    dec a
    xba
    asl a
    asl a                       ; the palette, bits 10 to 12
    ora #$2000
    sta TL_GG
    lda TL_C
    asl a
    ora TL_GG
    sta TL_GG
    tya
    asl a
    clc
    adc TL_T3
    tax
    lda TL_GG
    sta TL_MAP, x
    inc a
    sta TL_MAP + 64, x
    ; And the upload: column and pair.
    lda TL_UP_N
    asl a
    tax
    sep #$20
.a8
    tya
    sta TL_UPLOAD, x
    lda TL_C
    sta TL_UPLOAD + 1, x
    rep #$20
.a16
    inc TL_UP_N
empty:
    iny
    cpy #TL_COLS
    bcc column
    lda #1
    sta TL_MAP_DIRTY
    lda #$FFFF
    sta TL_T_ROW
    rts
.endproc

; --- the menu bank's strips ------------------------------------------------------
;
; The pause menu, the actor choice and the slot screen write the names
; —each actor's, a medicine's— composed, with the same letters as the text
; screens, and the numbers one per cell, with the bank's glyphs. Until
; 2026-10-03 the names went one per cell too, and with a font whose letters
; are four or five pixels wide that was a gap of three between them.
;
; A name is **a strip**: composed in the stage, from the menu bank's own
; precomposed tables —the font for the layout of its text palette, palette
; 0—, and uploaded to tiles of its own, which are taken in order from the
; bank's free ones, after its tiles and up to its tilemap. Those screens
; upload their bank whole each time they open —`slot_bank_upload`, which
; starts the free ones over— and write their names then, with the screen off;
; the converter measures that the most a screen asks for fits.
;
; The numbers stay one per cell: the menu rewrites the HP after healing, and
; the actor choice the medicine's count, in the vblank and with the screen
; on, and composing there does not fit. Their glyphs are the bank's, all of
; the same width, and they look like before.
;
; The stage is the text layer's, which those screens do not have on: the
; layer stops —`tl_on`— and starts again with the next `tl_reset`.

; The bank's free tiles start over, and the slot screen's names are
; forgotten. With the bank, from `slot_bank_upload`.
.proc tl_strip_reset
.a8
.i16
    tl_enter
    rep #$20
.a16
    lda #TL_STRIP_FIRST
    sta TL_STRIP_NEXT
    ldx #0
forget:
    stz TL_SLOT_K, x
    inx
    inx
    cpx #(2 * TL_SLOTS)
    bcc forget
    sep #$20
.a8
    plb
    rtl
.endproc
.assert TL_STRIP_FIRST <= TL_STRIP_LAST, error, "the menu's bank reaches its tilemap"

; A strip: the text at `msg_ptr`, A letters at most —its padding left
; out— and as many as fit in A cells, composed in white from Y, the tilemap
; word of its upper left cell. With the screen off. Keeps Y; clobbers A
; and X.
.proc tl_strip
.a8
.i16
    pha
    phy
    tl_enter
    rep #$20
.a16
    lda 2, s
    sta TL_STRIP_CELL
    lda 4, s
    and #$00FF
    sta TL_STRIP_CAP
    jsr tl_strip_new
    sep #$20
.a8
    plb
    ply
    pla
    rtl
.endproc

; The leader's name of the slot screen's slot `slot`, like `tl_strip`: the
; first time it is composed, and from then on the same tiles are pointed to
; again —moving the cursor repaints the row in the vblank, and composing
; there does not fit—. Keeps Y; clobbers A and X.
.proc tl_slot_name
.a8
.i16
    pha
    phy
    tl_enter
    rep #$20
.a16
    lda 2, s
    sta TL_STRIP_CELL
    lda 4, s
    and #$00FF
    sta TL_STRIP_CAP
    lda slot
    and #$00FF
    asl a
    tax
    lda TL_SLOT_K, x
    beq compose
    sta TL_STRIP_K
    lda TL_SLOT_T, x
    sta TL_STRIP_T
    jsr tl_strip_place
    bra done
compose:
    phx
    jsr tl_strip_new
    plx
    lda TL_STRIP_T
    sta TL_SLOT_T, x
    lda TL_STRIP_K
    sta TL_SLOT_K, x
done:
    sep #$20
.a8
    plb
    ply
    pla
    rtl
.endproc

; Composes `TL_STRIP_CAP` letters of `msg_ptr` to `TL_STRIP_CELL`, and
; takes and uploads its tiles: in `TL_STRIP_T` the first and in
; `TL_STRIP_K` how many columns, 0 if it had nothing or there was no room. A16.
.proc tl_strip_new
.a16
.i16
    lda comp_glyph              ; the composer borrows it
    sta TL_KEEP_G
    lda comp_glyph + 2
    sta TL_KEEP_G + 2
    jsr tl_strip_compose
    lda TL_STRIP_K
    beq none
    asl a
    clc
    adc TL_STRIP_NEXT
    cmp #(TL_STRIP_LAST + 1)
    bcs full                    ; the converter measured it does not happen
    lda TL_STRIP_NEXT
    sta TL_STRIP_T
    jsr tl_strip_upload
    jsr tl_strip_place
    lda TL_STRIP_K
    asl a
    clc
    adc TL_STRIP_NEXT
    sta TL_STRIP_NEXT
    bra none
full:
    stz TL_STRIP_K
none:
    lda TL_KEEP_G
    sta comp_glyph
    sep #$20
.a8
    lda TL_KEEP_G + 2
    sta comp_glyph + 2
    rep #$20
.a16
    rts
.endproc

; The letters into the stage, from x = `TL_XOFS`: those of the text without
; its trailing spaces, while their advances add up to the cap's cells'
; pixels. Leaves in `TL_STRIP_K` how many columns they reach. A16.
.proc tl_strip_compose
.a16
.i16
    sep #$20
.a8
    stz tl_on                   ; the stage is the strip's now
    rep #$20
.a16
    ; The padding off.
    ldy TL_STRIP_CAP
trim:
    cpy #0
    beq trimmed
    dey
    lda [msg_ptr], y
    and #$00FF
    cmp #' '
    beq trim
    iny
trimmed:
    sty TL_STRIP_N
    jsr tl_stage_clear
    lda #TL_SLOT_PRE
    sta TL_PRE
    stz TL_VAR
    lda #TL_XOFS
    sta TL_X
    lda TL_STRIP_CAP
    asl a
    asl a
    asl a
    clc
    adc #TL_XOFS
    sta TL_T0                   ; where the line may end, at most
    ldy #0
letter:
    cpy TL_STRIP_N
    bcs done
    lda [msg_ptr], y
    and #$00FF
    sec
    sbc #' '
    sta TL_C
    tax
    lda f:font_advance, x
    and #$00FF
    clc
    adc TL_X
    cmp TL_T0
    beq fits
    bcs done
fits:
    pha                         ; where the next one starts
    lda f:font_reach, x
    and #$00FF
    beq blank                   ; a blank paints nothing
    phy
    jsr tl_glyph
    ply
blank:
    pla
    sta TL_X
    iny
    bra letter
done:
    stz TL_PRE
    ; The columns the letters reach: the last one's ink and shadow end a
    ; pixel before where the next would start, at most.
    lda TL_X
    clc
    adc #6
    lsr a
    lsr a
    lsr a
    sta TL_STRIP_K
    rts
.endproc

; The stage, cleared through the WRAM port: a DMA from a fixed zero. A16.
.proc tl_stage_clear
.a16
.i16
    lda #TL_STAGE
    sta f:WMADDL
    sep #$20
.a8
    lda #0                      ; bit 16 of the 17: 0 is bank $7E
    sta f:WMADDH
    lda #$08                    ; one register, the source does not move
    sta f:DMAP0
    lda #<WMDATA
    sta f:BBAD0
    lda #^tl_zero
    sta f:A1B0
    rep #$20
.a16
    lda #.loword(tl_zero)
    sta f:A1T0L
    lda #TL_STAGE_BYTES
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    rts
.endproc

; The strip's columns, from the stage to its tiles: a column is its upper
; tile and its lower one, one after the other, and so are they in the bank.
; A16.
.proc tl_strip_upload
.a16
.i16
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$7E
    sta f:A1B0
    rep #$20
.a16
    lda TL_STRIP_T
    asl a
    asl a
    asl a
    asl a                       ; 16 words a tile
    clc
    adc #SLOT_VRAM
    sta f:VMADDL
    lda #TL_STAGE
    sta f:A1T0L
    lda TL_STRIP_K
    xba
    lsr a
    lsr a                       ; 64 bytes a column
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    rts
.endproc

; The strip's cells in the tilemap: column c is tiles `TL_STRIP_T` + 2c on
; top and the next one below, with the bank's priority and palette 0. A16.
.proc tl_strip_place
.a16
.i16
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    rep #$20
.a16
    lda TL_STRIP_CELL
    sta f:VMADDL
    lda TL_STRIP_T
    jsr cells
    lda TL_STRIP_CELL
    clc
    adc #32
    sta f:VMADDL
    lda TL_STRIP_T
    inc a
cells:
    ora #$2000                  ; the priority: see `slot_tiles`
    ldx TL_STRIP_K
    beq placed
word:
    sta f:VMDATAL
    inc a
    inc a
    dex
    bne word
placed:
    rts
.endproc
