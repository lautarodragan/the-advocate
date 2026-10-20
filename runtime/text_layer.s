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
;   **Except a text written by reference** —`TL_BY_REF`, which the
;   battle's skill list asks for—: its run keeps where the text is in ROM
;   and how many letters, six bytes however long it is. Two columns of
;   names with their dashes and costs did not fit in a record with the
;   letters copied, and until 2026-10-04 the cartridge kept thirteen letters
;   of each skill. Nothing continues such a run.; * **A row that changed is typeset**: its runs are composed into
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
;   said to what it says in one frame. A pair a row stopped using waits
;   until that switch, because the screen still shows it: at the top of
;   `TL_FREE`, which the free ones fill from the bottom. A screen that
;   changes so much at once that the pool runs out switches earlier: the
;   rows not typeset yet keep what they said until their turn, or go blank
;   if a row took another's tiles since the last switch —`tl_blank_dirty`,
;   and `tl_step`—.
; * **A row's head that did not change keeps its tiles**: the runs at the
;   start of its record that are what the screen shows, if the rest starts
;   in a column after them —`tl_split`—. The debug screen's ranges, beside
;   a list that changes whole.
; * **A held arrow waits for the text**: its repeat fires only once the
;   screen shows what it wrote —`tl_pace`—, so a list held scrolling never
;   writes over a screen that was not shown.
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
; The stage, where a row is composed, is **not** in the layer's RAM but in
; `ANIMB_BUF`, the map's battle animation frame: it is only built on the
; map, and `back_to_map` and `enter_map` clear it —`anim_buf_clear`— after
; every screen, because it is rebuilt from nothing. So a screen can use it
; as it wants. It moved there on 2026-10-04, to make room for the battle's
; 447 pairs: see `battle_bank_upload`.
TL_STAGE     = .loword(ANIMB_BUF)
TL_STAGE_BYTES = TL_COLS * 64   ; a column is two tiles, top and bottom
.assert TL_STAGE_BYTES <= ANIM_B_BYTES, error, "the stage does not fit in ANIMB_BUF"
.assert ^ANIMB_BUF = $7E, error, "the stage is read with the data bank at $7E"
; A pair's number is a word: until 2026-10-04 it was a byte, and a screen
; had 191 at most.
TL_PAIR      = TL_SHOWN + TL_ROWS * TL_RECORD ; each cell's pair, a word
TL_PAIRS     = 448                           ; a screen has 447 at most
TL_REFS      = TL_PAIR + TL_ROWS * TL_COLS * 2 ; per pair, how many cells
; Two stacks in one, of words: the free ones from the bottom, and from the
; top down the ones released that the screen still shows, until the switch.
; A pair is in one of them at most, so they never meet.
TL_FREE      = TL_REFS + TL_PAIRS
TL_UPLOAD    = TL_FREE + 2 * TL_PAIRS        ; (column, pair) to upload, words
TL_USED      = TL_UPLOAD + 4 * TL_COLS       ; per column: colour + 1 if inked
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
TL_VRAM      = TL_VARS + 26     ; where pair 0 is: `SLOT_VRAM`, or 0 in the battle
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
TL_STRIP_OVER = TL_VARS + 64    ; `tl_strip`: the first tile past the free
                                ; ones, plus one —see `tl_strip_reset`—
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
TL_WIN_KEY   = TL_SLOT_K + 2 * TL_SLOTS ; the shop's windows as last uploaded:
                                ; see `ti_windows`. Eight bytes
TL_BY_REF    = TL_WIN_KEY + 8   ; nonzero: the next `scr_text` goes by reference
TL_T_REF     = TL_WIN_KEY + 10  ; nonzero: the run being typeset is one
TL_REF_AT    = TL_WIN_KEY + 12  ; and where its next letter is, three bytes
TL_ADOPTED   = TL_WIN_KEY + 16  ; nonzero: a row took another's tiles since
                                ; the last switch —see `tl_step`—
TL_SPLIT     = TL_WIN_KEY + 18  ; the row being typeset: its first column
                                ; composed; the ones before keep their tiles
TL_SPLIT_AT  = TL_WIN_KEY + 20  ; and its first run composed, a record offset
TL_REL_FROM  = TL_WIN_KEY + 22  ; `tl_release_cols`: the first column it frees
TL_END       = TL_WIN_KEY + 24
; A run's colour byte with this bit says it goes by reference: three bytes
; of address after its count, and no letters.
TL_REF_BIT   = $80
.assert TL_END = FAR_TEXT_LAYER_END, error, "TL_BYTES, in far_ram.s, is not what the text layer takes: TL_END - TL_MAP"

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
; How many pairs go up in one vblank, at most: they go after the screen's
; own uploads —the shop's windows reach line 244 of the 261—, and an upload
; that falls out of the vblank is lost. Sixteen are some six lines; with 32,
; while the shop uploaded its windows every frame, it showed garbage tiles. A
; row with more goes up over several.
TL_PAIRS_PER_VBLANK = 16
; Where a run starts inside its cell, and where the glyph's first row goes
; inside a line's two cell rows: the screens stage's geometry, `SCR_TEXT_X`
; and `SCR_TEXT_Y`. `tl_row_ofs` is built for the second.
TL_XOFS      = SCR_TEXT_X
TL_OFS_Y     = SCR_TEXT_Y
.assert TL_OFS_Y = 2, error, "tl_row_ofs puts a glyph's first row at row 2 of its line"
; A pair: two tiles of 4bpp, 32 words, from `TL_VRAM` —`SLOT_VRAM`, or word
; 0 in the battle: see `battle_bank_upload`—. Pair 0 is never handed out:
; tile 0 is the blank one, which the cells without text point to.
TL_PAIR_WORDS = 32
; The slot screen's slots `tl_slot_name` keeps a name for.
TL_SLOTS     = 8
.assert SRAM_SLOTS_N <= TL_SLOTS, error, "tl_slot_name keeps a name per slot"
; The menu bank's tables in `scr_pre_lo` and `scr_pre_bk`.
TL_SLOT_PRE  = 16
; Where the slot screen's strips go: from the first even tile after the
; bank, up to its tilemap; or, if the converter put each screen's text
; apart —`Order::Apart` in `rm2k-snes-screens`—, over the menu's text,
; which the slot screen does not show, up to its own.
TL_STRIP_FIRST = (SLOT_NAMES_FIRST + 1) & $FFFE
; The menu's and the actor choice's: after the tiles they show, which are
; all of them unless the converter put the slot screen's text last to make
; room —`Order::MenuFirst` in `rm2k-snes-screens`—. Those screens do not
; show it, so their names may go over it.
TL_MENU_STRIP_FIRST = (SLOT_MENU_TILES + 1) & $FFFE
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
    sta TL_FREE, x
    inx
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
    cpx #(TL_ROWS * TL_COLS * 2)
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
    stz TL_BY_REF
    stz TL_T_REF
    stz TL_ADOPTED
    stz TL_SPLIT
    lda #$FFFF
    sta TL_WIN_KEY              ; the shop's windows, not uploaded yet
    sta TL_T_ROW
    sta TL_PEN_PICK
    lda #SLOT_VRAM
    sta TL_VRAM                 ; the battle moves it after: `tl_low`
    lda #1
    sta TL_SETTLE
    sep #$20
.a8
    sta tl_on                   ; `wait_vblank` typesets from now on
    plb
    rtl
.endproc

; The pairs from word 0 and not from `SLOT_VRAM`: the battle's, right after
; `tl_reset`. See `battle_bank_upload`. A8.
.proc tl_low
.a8
.i16
    tl_enter
    rep #$20
.a16
    stz TL_VRAM
    sep #$20
.a8
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
    lda TL_CUR + 1, y
    and #TL_REF_BIT
    beq copied
    lda #6                      ; by reference: its address and no letters
    bra sized
copied:
    lda TL_CUR + 2, y
    and #$00FF
    clc
    adc #3
sized:
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
.endproc

; `scr_text` of a text that is not in the cartridge's text table: the one at
; `msg_ptr`, of `temp` letters. `tl_text` falls into it, so splitting it
; changed no byte. The custom menus write their texts with it —see
; custom_menu.s—, which are in their own block.
.proc tl_text_at
.a8
.i16
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
    lda TL_BY_REF
    bne by_ref
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

    ; By reference: a run of its own, always —nothing it could continue
    ; would know where its letters end—, and after its count the text's
    ; address instead of the letters. With no room in the record for those
    ; three bytes, the empty run goes and the text does not show, as when
    ; letters do not fit.
by_ref:
    stz TL_BY_REF               ; it is for one text only, like the cap
    rep #$20
.a16
    stz TL_RUN
    jsr tl_open
    lda TL_RUN
    beq no_room                 ; not even for the run
    ldy TL_RUN_ROW
    lda TL_CUR, y
    and #$00FF
    cmp #(TL_RECORD - 1 - 3 + 1)
    bcc room
    sec
    sbc #3
    sep #$20
.a8
    sta TL_CUR, y
    rep #$20
.a16
    bra no_room
room:
    clc
    adc #3
    sep #$20
.a8
    sta TL_CUR, y               ; the longer length
    lda msg_ptr
    sta TL_CUR, x
    lda msg_ptr + 1
    sta TL_CUR + 1, x
    lda msg_ptr + 2
    sta TL_CUR + 2, x
    ldx TL_RUN
    lda temp
    sta TL_CUR, x               ; how many letters
    lda TL_CUR - 1, x
    ora #TL_REF_BIT
    sta TL_CUR - 1, x           ; and in its colour, that it is by reference
    rep #$20
.a16
no_room:
    stz TL_RUN                  ; nothing continues it
    sep #$20
.a8
    lda temp
    jsr tl_moved
    lda #255
    sta comp_dup + 3
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
    asl a
    tax
pair:
    lda TL_UPLOAD + 2, x        ; the pair
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 words each
    clc
    adc TL_VRAM
    sta f:VMADDL
    lda TL_UPLOAD, x            ; the column
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
    inx
    inx
    txa
    lsr a
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
    jsl f:tl_pace
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
    stz TL_ADOPTED              ; what the screen shows is what the rows say
    lda #1
    sta TL_SWITCHED             ; `tl_step` clears `TL_NEW` and frees the
                                ; waiting ones, out of the vblank
    sep #$20
.a8
    rts
.endproc

; After a switch, what was waiting for it is free: the waiting ones, from the
; top of `TL_FREE`, onto the free ones, with one `mvn`. Upwards, which is the
; order in which a byte never lands on one not read yet: the two together are
; fewer than `TL_PAIRS`, so the copy goes down. It was a loop in the vblank
; until 2026-10-04, and with the battle's 447 it would not have fitted. A16.
.proc tl_recycle
.a16
.i16
    lda TL_PEND_N
    beq done
    sta TL_T0
    lda #TL_PAIRS
    sec
    sbc TL_T0
    asl a
    clc
    adc #TL_FREE
    tax                         ; the lowest waiting one
    lda TL_FREE_N
    asl a
    clc
    adc #TL_FREE
    tay                         ; where the free ones end
    lda TL_T0
    asl a
    dec a                       ; `mvn` copies A + 1
    mvn #$7E, #$7E
    lda TL_FREE_N
    clc
    adc TL_T0
    sta TL_FREE_N
    stz TL_PEND_N
done:
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
; stack goes —`test_stack.py`—.
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
    jsr tl_late_step            ; the copy takes up to some thirty lines
    bcs busy
    jsr tl_not_new
    jsr tl_recycle
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
    ; A row takes at most a pair per column it composes —the ones before
    ; `TL_SPLIT` keep theirs: see `tl_split`—. If fewer are free and some
    ; wait for the switch, the switch goes first; if none wait, what does
    ; not fit stays blank.
    pha
    jsl f:tl_split
    lda #TL_COLS
    sec
    sbc TL_SPLIT
    cmp TL_FREE_N
    beq room
    bcc room
    lda TL_PEND_N
    beq room
    ; The switch shows the rows typeset so far, and the others keep showing
    ; what they said until their turn. Unless a row took another's tiles
    ; since the last switch: then a row not typeset yet may show what that
    ; one says now, its neighbour's text, and they go blank first.
    pla
    lda TL_ADOPTED
    beq early
    jsl f:tl_blank_dirty
early:
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
    ; A cell's pair is a word, at twice its index: where its tilemap word is
    ; in `TL_MAP`.
    lda TL_T0
    xba
    lsr a
    lsr a
    tay                         ; this one's first cell, times two
    lda TL_SRC
    xba
    lsr a
    lsr a
    tax                         ; and the source's
    lda #TL_COLS
    sta TL_N
column:
    lda TL_PAIR, x
    beq empty
    sta TL_PAIR, y
    phx
    tax
    sep #$20
.a8
    inc TL_REFS, x
    rep #$20
.a16
    plx
    ; Its two tilemap words, both read before writing: the source can be
    ; the row above, whose lower cells are this one's upper ones.
    lda TL_MAP, x
    sta TL_GG
    lda TL_MAP + 64, x
    sta TL_SS
    lda TL_GG
    sta TL_MAP, y
    lda TL_SS
    sta TL_MAP + 64, y
empty:
    inx
    inx
    iny
    iny
    dec TL_N
    bne column
    lda TL_T0
    jsr tl_shown_now
    lda #1
    sta TL_MAP_DIRTY
    sta TL_ADOPTED
    rts
.endproc

; Row A16's pairs go: each one counts one less, and the one nobody points to
; any more is free again —if the screen never showed it— or waits for the
; switch; its cells of the tilemap go blank, **if they are still its own**: a
; line takes two cell rows, so a row's lower cells are the next row's upper
; ones, and the line that wrote them last keeps them. Until 2026-10-03 they
; went blank anyway, and a line released under one that stayed —the shop's
; list, scrolled, under the gold of the quantity screen— cut the half of it
; that shared, for good: the row that stayed did not change, so it was not
; composed again. Leaves its first cell in
; `TL_T2` and its first tilemap byte in `TL_T3`. A16.
.proc tl_release_row
.a16
.i16
    stz TL_REL_FROM
.endproc
; The same from column `TL_REL_FROM` on: `tl_finish`'s, whose row keeps the
; tiles of the columns before `TL_SPLIT`. A16.
.proc tl_release_cols
.a16
.i16
    asl a
    asl a
    asl a
    asl a
    asl a
    sta TL_T2                   ; its first cell
    asl a
    sta TL_T3                   ; its first tilemap byte, and its first pair's
    clc
    adc TL_REL_FROM
    clc
    adc TL_REL_FROM
    tay                         ; the first one it frees
    lda #TL_COLS
    sec
    sbc TL_REL_FROM
    sta TL_T1
    bne column
    rts
column:
    lda TL_PAIR, y
    beq empty
    sta TL_C                    ; the pair, for its cells below
    tax
    lda #0
    sta TL_PAIR, y
    sep #$20
.a8
    dec TL_REFS, x
    rep #$20
.a16
    bne still
    sep #$20
.a8
    lda TL_NEW, x
    rep #$20
.a16
    beq shown
    sep #$20
.a8
    stz TL_NEW, x               ; never on screen: free now
    rep #$20
.a16
    lda TL_FREE_N
    asl a
    tax
    lda TL_C
    sta TL_FREE, x
    inc TL_FREE_N
    bra still
shown:
    ; At the top of `TL_FREE`, down from its last word.
    lda #(TL_PAIRS - 1)
    sec
    sbc TL_PEND_N
    asl a
    tax
    lda TL_C
    sta TL_FREE, x
    inc TL_PEND_N
still:
    lda TL_MAP, y
    and #$03FF
    lsr a
    cmp TL_C
    bne not_upper
    lda #0
    sta TL_MAP, y
not_upper:
    lda TL_MAP + 64, y
    and #$03FF
    lsr a
    cmp TL_C
    bne not_lower
    lda #0
    sta TL_MAP + 64, y
not_lower:
    lda #1
    sta TL_MAP_DIRTY
empty:
    iny
    iny
    dec TL_T1
    bne column
    rts
.endproc

; `tl_release_row` for `tl_blank_dirty`, which lives in `FAR3`. A16.
.proc tl_release_row_l
.a16
.i16
    jsr tl_release_row
    rtl
.endproc

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
    clc
    adc TL_T0
    sta TL_T_END
    lda TL_SPLIT_AT
    clc
    adc #TL_SHOWN
    sta TL_T_POS                ; its first run composed: see `tl_split`
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
    lda a:2, x
    and #$00FF
    sta TL_T_LEFT
    lda a:1, x
    and #$00FF
    bit #TL_REF_BIT
    bne by_ref
    sta TL_VAR                  ; the colour: the palette of what it inks
    stz TL_T_REF
    txa
    clc
    adc #3
    sta TL_T_POS
    bra loop
by_ref:
    and #($FF - TL_REF_BIT)
    sta TL_VAR
    lda #1
    sta TL_T_REF
    lda a:3, x
    sta TL_REF_AT               ; where its letters are
    lda a:5, x
    and #$00FF
    sta TL_REF_AT + 2
    txa
    clc
    adc #6
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
    lda TL_T_REF
    beq copied
    jsr tl_ref_letter
    bra fetched
copied:
    ldx TL_T_POS
    inc TL_T_POS
    lda a:0, x
    and #$00FF
fetched:
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

; The next letter of a run by reference, as a letter of the font, in A, and
; `TL_REF_AT` on the one after. It is read with the data bank at the text's
; and an absolute address, which reaches any bank with no direct page: the
; layer's typesetting runs anywhere a screen waits for the vblank, and has
; none of its own. Both interrupts set their own data bank. A16.
.proc tl_ref_letter
.a16
.i16
    ldx TL_REF_AT
    sep #$20
.a8
    lda TL_REF_AT + 2
    pha
    plb
    lda a:0, x
    xba
    lda #$7E
    pha
    plb
    xba
    rep #$20
.a16
    and #$00FF
    sec
    sbc #' '
    pha
    inc TL_REF_AT
    bne same_bank
    sep #$20
.a8
    inc TL_REF_AT + 2
    rep #$20
.a16
same_bank:
    pla
    rts
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
    lda TL_SPLIT
    sta TL_REL_FROM
    lda TL_T_ROW
    jsr tl_release_cols         ; leaves its first cell in TL_T2, tilemap TL_T3
    stz TL_UP_N
    stz TL_UP_I
    ldy TL_SPLIT
    cpy #TL_COLS
    bcs empty                   ; nothing composed: every column kept
column:
    lda TL_USED, y
    and #$00FF
    beq empty
    sta TL_G                    ; the colour + 1
    lda TL_FREE_N
    beq empty                   ; none left
    dec TL_FREE_N
    lda TL_FREE_N
    asl a
    tax
    lda TL_FREE, x
    sta TL_C                    ; the pair
    tax
    sep #$20
.a8
    lda #1
    sta TL_REFS, x
    sta TL_NEW, x
    rep #$20
.a16
    ; Its pair, a word at twice the cell's index, which is where its tilemap
    ; word is too.
    tya
    asl a
    clc
    adc TL_T3
    tax
    lda TL_C
    sta TL_PAIR, x
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
    sta TL_MAP, x
    inc a
    sta TL_MAP + 64, x
    ; And the upload: column and pair.
    lda TL_UP_N
    asl a
    asl a
    tax
    tya
    sta TL_UPLOAD, x
    lda TL_C
    sta TL_UPLOAD + 2, x
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
; bank's free ones, after its tiles and up to its tilemap —or over the
; other screen's text, which this one does not show: see `TL_STRIP_FIRST`—.
; Those screens upload their bank whole each time they open
; —`slot_bank_upload`, which starts the free ones over, and puts back the
; text the other one composed over— and write their names then, with the
; screen off; the converter measures that the most a screen asks for fits.
;
; The numbers stay one per cell: the menu rewrites the HP after healing, and
; the actor choice the medicine's count, in the vblank and with the screen
; on, and composing there does not fit. Their glyphs are the bank's, all of
; the same width, and they look like before.
;
; The stage is the text layer's, which those screens do not have on: the
; layer stops —`tl_on`— and starts again with the next `tl_reset`.

; The bank's free tiles start over, the slot screen's, and its names are
; forgotten. With the bank, from `slot_bank_upload`. The end goes in RAM,
; plus one, because it is the menu's when `tl_strip_menu` comes after.
.proc tl_strip_reset
.a8
.i16
    tl_enter
    rep #$20
.a16
    lda #TL_STRIP_FIRST
    sta TL_STRIP_NEXT
    lda #(SLOT_NAMES_END + 1)
    sta TL_STRIP_OVER
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
.assert TL_STRIP_FIRST <= SLOT_NAMES_END, error, "the slot screen has no tile for its names"
.assert SLOT_NAMES_END <= TL_STRIP_LAST, error, "the slot screen's names reach the bank's tilemap"

; The free tiles start over for the menu or the actor choice, after the
; tiles they show: right after `slot_bank_upload`. Only in a cartridge whose
; bank put the slot screen's text last; in the others it would set what
; `tl_strip_reset` already did, and it is not assembled.
.if SLOT_MENU_TILES <> SLOT_TILES
.proc tl_strip_menu
.a8
.i16
    tl_enter
    rep #$20
.a16
    lda #TL_MENU_STRIP_FIRST
    sta TL_STRIP_NEXT
    lda #(TL_STRIP_LAST + 1)
    sta TL_STRIP_OVER
    sep #$20
.a8
    plb
    rtl
.endproc
.endif

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
    cmp TL_STRIP_OVER
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

; --- what came after bank 1 filled up ------------------------------------------
;
; In `FAR3`, entered with `jsl` and without `+ FAST`, because they did not fit
; in bank 1 in ABL's MSU test cartridge. They run with the data bank at $7E
; like the rest.
.pushseg
.segment "FAR3"

; More pairs for the pool, right after `tl_reset`: A16 the first, X16 one
; past the last, below `TL_PAIRS`. They need not follow the ones `tl_reset`
; gave: the items screen takes VRAM past its tilemaps —see `items_pool`—.
.proc tl_more
.a16
.i16
    tay
    sep #$20
.a8
    tl_enter
    rep #$20
.a16
    stx TL_T0
    lda TL_FREE_N
    asl a
    tax
pair:
    tya
    sta TL_FREE, x
    inx
    inx
    iny
    cpy TL_T0
    bcc pair
    txa
    lsr a
    sta TL_FREE_N
    sep #$20
.a8
    plb
    rep #$20
.a16
    rtl
.endproc

; A held arrow repeats only when the text says what the screen wrote last:
; if it is still being typeset, the repeat `arrows_repeat` faked this frame
; is undone and tried again on the next one. RM2k repeats every four frames
; whatever happens; here a step that scrolls a list takes longer than that
; to typeset, so a held arrow wrote over a screen that was never shown, and
; the tilemap only switched when the pool ran out —taro saw the text stand
; still for a second or two, and then rows repeated: see
; `scrolling-a-list-shows-the-last-row-repeated-for-a-moment` in the
; tasks—. So holding an arrow scrolls as fast as the text can follow, and
; each step is shown whole. A press is never held back: only a repeat. It
; runs in `tl_map`, which every screen with this layer calls once per frame
; right after reading the pad and before looking at its edges. A8, data
; bank $7E.
.proc tl_pace
.a8
.i16
    lda f:arrows_repeated
    beq out
    rep #$20
.a16
    lda TL_UP_N
    ora TL_MAP_DIRTY
    bne later
    lda TL_IDLE_DONE
    bne shown
later:
    sep #$20
.a8
    lda f:arrows_repeated
    tsb pad_prev                ; not just pressed after all
    lda #0
    sta f:arrows_repeated
    lda #(REPEAT_WAIT - 1)      ; `arrows_repeat` fires on the next frame
    sta f:arrows_frames
    rtl
shown:
    sep #$20
.a8
out:
    rtl
.endproc

; The pool ran out halfway through what the screen wrote, and the tilemap
; has to switch early to free the pairs it still shows: before it does, every
; row that does not say what it will say yet goes blank. Without this the
; switch showed them with what they said before, next to the rows that had
; already taken another's tiles, and a list that scrolled showed the rows
; that came in as copies of their neighbour —taro, 2026-10-18: see
; `scrolling-a-list-shows-the-last-row-repeated-for-a-moment` in the
; tasks—. A blank row is typeset after the switch like any other. Only
; then, since 2026-10-20: if no row took another's tiles, a row that is not
; typeset yet shows what it said, which is no other row's, and blanking it
; was the debug screen's black block —see `tl_step`—. A16.
.proc tl_blank_dirty
.a16
.i16
    stz TL_DJ
row:
    ldy TL_DJ
    lda TL_FLAG, y
    and #$00FF
    cmp #TL_DIRTY
    bne next
    tya
    jsl f:tl_release_row_l + FAST
    lda TL_DJ
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    ldy TL_DJ
    sep #$20
.a8
    stz TL_SHOWN, x             ; it shows nothing: the empty record
    lda #0
    sta TL_SSIG, y              ; whose signature is 0
    rep #$20
.a16
next:
    inc TL_DJ
    lda TL_DJ
    cmp #TL_ROWS
    bcc row
    rtl
.endproc
; Where row A16 starts being composed: `TL_SPLIT`, a column, and
; `TL_SPLIT_AT`, its first run, an offset of the records. **The runs at the
; head of its record that are byte for byte what the screen shows keep their
; tiles**, if every other run, of what the row said and of what it says,
; starts in a column after the last one they ink; if not, the whole row,
; column 0. That is how the debug screen's ranges stay on screen while the
; list beside them changes: a line of the layer is the screen's whole row,
; its two windows', and composing it again took tiles for text that had not
; changed —taro saw the ranges drawn again, and a black block over them
; when the pool ran out: see `the-debug-screen-redraws-and-goes-wide` in
; the tasks—. A run by reference ends the head: its letters are not in the
; record to measure. Data bank $7E; clobbers X and Y. A16.
.proc tl_split
.a16
.i16
    asl a
    tax
    lda f:tl_rec_ofs, x
    tax
    inc a
    pha                         ; the record's first run, for `whole`
    sta TL_SPLIT_AT
    lda TL_CUR, x
    and #$00FF
    clc
    adc TL_SPLIT_AT
    sta TL_T0                   ; where what it says ends
    lda TL_SHOWN, x
    and #$00FF
    clc
    adc TL_SPLIT_AT
    sta TL_T1                   ; and what it shows
    stz TL_T2                   ; where the head's ink ends, in pixels
    ldx TL_SPLIT_AT
head:
    cpx TL_T0
    bcs headed
    cpx TL_T1
    bcs headed
    lda TL_CUR + 1, x
    and #TL_REF_BIT
    bne headed
    lda TL_CUR + 2, x
    and #$00FF
    clc
    adc #3
    sta TL_T3                   ; the run's bytes
    ; The same bytes on both sides?
    phx
    tay
    sep #$20
.a8
same:
    lda TL_CUR, x
    cmp TL_SHOWN, x
    bne differs
    inx
    dey
    bne same
    rep #$20
.a16
    plx
    jsr ink
    bra head
.a8
differs:
    rep #$20
.a16
    plx
headed:
    ; The first column the head does not ink, and every other run after it.
    lda TL_T2
    beq whole
    clc
    adc #7
    lsr a
    lsr a
    lsr a
    sta TL_T3
    ldx TL_SPLIT_AT
    lda TL_T0
    jsr after
    bcc whole
    lda TL_SPLIT_AT
    clc
    adc #(TL_SHOWN - TL_CUR)
    tax
    lda TL_T1
    clc
    adc #(TL_SHOWN - TL_CUR)
    jsr after
    bcc whole
    pla
    lda TL_T3
    cmp #TL_COLS
    bcc split
    lda #TL_COLS
split:
    sta TL_SPLIT
    rtl
whole:
    pla
    sta TL_SPLIT_AT
    stz TL_SPLIT
    rtl

; Whether every run from X to A —offsets from `TL_CUR`— starts in column
; `TL_T3` or after: carry set if so.
after:
    sta TL_N
run:
    cpx TL_N
    bcs every
    lda TL_CUR, x
    and #$00FF
    lsr a
    lsr a
    lsr a
    cmp TL_T3
    bcc before
    lda TL_CUR + 1, x
    and #TL_REF_BIT
    beq copied
    lda #6                      ; by reference: its address and no letters
    bra sized
copied:
    lda TL_CUR + 2, x
    and #$00FF
    clc
    adc #3
sized:
    sta TL_C
    txa
    clc
    adc TL_C
    tax
    bra run
every:
    sec
    rts
before:
    clc
    rts

; Run X's ink, as far as it reaches past `TL_T2`, and the head up to its
; end: X and `TL_SPLIT_AT` after it.
ink:
    ; Its ink: from its x, letter by letter, up to the farthest a glyph
    ; reaches.
    lda TL_CUR, x
    and #$00FF
    sta TL_X
    lda TL_CUR + 2, x
    and #$00FF
    sta TL_N
    phx
    inx
    inx
    inx
letter:
    lda TL_N
    beq measured
    dec TL_N
    lda TL_CUR, x
    and #$00FF
    inx
    cmp #TL_FIGURE
    bne glyph
    lda f:font_advance + ('0' - ' ')
    bra advance
glyph:
    phx
    tax
    lda f:font_reach, x
    and #$00FF
    beq no_ink                  ; a blank paints nothing
    clc
    adc TL_X
    cmp TL_T2
    bcc no_ink
    sta TL_T2
no_ink:
    lda f:font_advance, x
    plx
advance:
    and #$00FF
    clc
    adc TL_X
    sta TL_X
    bra letter
measured:
    pla
    clc
    adc TL_T3
    tax
    stx TL_SPLIT_AT             ; the head reaches here so far
    rts
.endproc
.assert TL_SHOWN - TL_CUR = TL_ROWS * TL_RECORD, error, "tl_split reads what the screen shows as TL_CUR past its rows"
.popseg
