; --- ShowWindow: a window of the game's own, from the System -----------------
;
; RPG Maker 2000 PLUS's `ShowWindow` —`OP_WINDOW` and `OP_WINDOW_ERASE`—: a
; window like a picture, numbered, put up and taken down by the events, but
; its pixels are not a file: its frame and background are the message
; window's, from the System in use, and its text is composed here with the
; message window's font. A game writes it as a comment, and where the comment
; stands in front of a `ShowPicture` the window takes the picture's place:
; see `windows.rs` in rm2k-snes-events, which also numbers each window's
; tiles, and the decision in the book, among RPG Maker 2000 PLUS's.
;
; **Stage one: in the message window's bank, with no message open.** A
; window takes the message window's 32x32 tilemap and its text tiles, as a
; `ShowChoice` does: it fits on every map, as the message window does, and
; costs no sprite tile. It cannot be on screen with a message, as none of
; RM2k's own menus can: when a box opens the windows are taken off the
; screen —`SW_HIDE`—, and when it closes they are drawn again, text and all,
; since the box wrote over their tiles. The game's windows are kept up all
; the same, in `SW_REC`: what is up is the events' state, what is drawn is
; this file's.
;
; **The layer above stays beside a narrow window**, as it stays beside a
; picture —taro's requirement, 2026-10-19—. On the lines a window covers,
; BG2 shows the window's tilemap and not the map's layer above, which is the
; same layer, so the window's tilemap carries the layer on those lines: the
; cells no window covers take the layer above's tilemap entries, read out of
; VRAM in a vblank, as `message_layer.s` does for a message without its
; background. Both tilemaps name tiles from BG2's base, so an entry is the
; same in either. It holds with the camera on the 8-pixel grid, which is
; where it always is at rest —see `message_layer.s`—: the screen's cells are
; then the map's, and the window's cells land on them. A window that comes up
; with the camera off the grid has nothing beside it on its lines until the
; camera stops on the grid again, and one under which the camera moves keeps
; what it copied until then; nor on a map whose BG2 is its panorama
; —`PANO_ON` 3—, where the layer above is not BG2.
;
; **The screen is composed whole**: `SW_MAP` is the screen's 28 rows of 32
; cells, and from the first row a window covers to the last, every cell is
; the layer above's or the last window's that covers it —the slots in order,
; so a higher picture number goes on top, as in RM2k—. That sw_span goes to the
; window's tilemap from its row 20 on, wrapping, so a sw_span of twelve rows or
; fewer leaves the message's two planes, rows 0 to 19, as they are; a taller
; one writes over them and they are put back when the windows go —`SW_PLANES`—.
; HDMA points BG2 at it on the sw_span's lines and hides the objects on them
; between the windows' left and right edges: PPU window 1, as the message's
; mask, from `WH0` to `WH1`.
;
; **Each window's text tiles are a run of the 239 text tiles**, each line
; after the ones before it, by the cells `OP_WINDOW` gives it. Which run is
; chosen when its text is composed —`sw_place`—: one the screen does not
; show and no other window up takes, so the old text stays on the screen
; until the new one is whole. The converter numbers each id's tiles of its
; own —`OP_WINDOW`'s `tiles`, the most any one window of that id takes—,
; so that windows up together always fit; they are where a window goes when
; no run is free. The last text tile, 239, is the windows' background, the
; first cell of the message window's: a System whose background is a
; gradient gets it flat.
;
; **A line is composed as a message's**: the background into `text_buf`, the
; letters through `msg_letter` —pairs, `\c[n]`, `\V[n]`— with
; `compose_char` and `msg_ink_char`, and the line's two rows of cells up in
; the next vblank. A colour other than 0 takes the boxes' ink, the same for
; every window up: a second colour goes with the window's nearest, as in a
; box. One line a frame.
;
; **A big picture covers the windows under its number**, as a picture covers
; the lower ones in RM2k: its layer is BG1, under the windows', so the slots
; under `SW_COVER` are left out of the screen —up, and drawn again when it
; goes— —`OP_WINDOW_COVER`, after every big picture's show and erase: see
; `window_cover` in the events compiler—.
;
; Everything is reached with `jsl`; the hooks are `op_window`,
; `op_window_erase` and `op_window_cover` in interpreter_message.s,
; `sw_tick` in the main loop,
; `sw_vblank` in `flush_video` when no message is up, `sw_lost` in
; `stamp_window_at` —a map's load, a big picture, a System— and `sw_clear`
; in `pic_clear`.
;
; **Its far RAM is mostly `SW_MAP`**, the screen's 28 rows of 32 entries:
; on Desert Nightmare it left 159 bytes of the segment (2026-11-20). A
; span is never wider than the screen, so it could hold only the span's
; rows, if a game needs the room.

.ifdef SHOW_WINDOW_SLOTS

; A slot's record: whether it is up and its text still has to be composed,
; then `OP_WINDOW`'s operands, with each line's box as a long pointer.
R_UP    = 0
R_DIRTY = 1
R_X     = 2                     ; cells
R_Y     = 3
R_W     = 4
R_H     = 5
R_STYLE = 6                     ; 0 framed, 1 only its background
R_TILES = 7                     ; its first text tile
R_N     = 8                     ; lines
R_LINES = 9                     ; four bytes each: the box, and its cells
SW_LINES_MAX = 13               ; `LINES_MAX` in windows.rs
R_USED  = R_LINES + SW_LINES_MAX * 4 ; the tiles its lines take
R_BASE  = R_USED + 1            ; where they are: its text's first tile
R_SBASE = R_USED + 2            ; and where the ones on the screen are,
R_SUSED = R_USED + 3            ; and how many; 0 none
SW_REC = R_USED + 4
SW_BACKGROUND = 239             ; `BACKGROUND_TILE` in windows.rs
SW_ROWS = LINES / 8             ; the screen's cell rows
SW_PLANE_ROW = 20               ; the first row of the window's tilemap past
                                ; the message's two planes
SW_STYLE_PLAIN = 1
; `SW_RDIRTY`'s bits: a row a change touched, and a row the screen being
; composed takes —read, composed and put up—.
RD_CHANGED = 1
RD_NOW     = 2

.pushseg
.segment "FARBSS"
SW_RECS:     .res SHOW_WINDOW_SLOTS * SW_REC
SW_MAP:      .res SW_ROWS * 32 * 2 ; the screen, composed
SW_MASK:     .res 9             ; the objects' mask, as `hdma_sc`
SW_FRAME:    .res 18            ; the frame's eight entries and the text's first
SW_MAPDIRTY: .res 1             ; 1: the screen has to be composed again
SW_SHOWN:    .res 1             ; 1 while the HDMA shows it
SW_HIDE:     .res 1             ; 1: off the screen in the next vblank
SW_COVER:    .res 1             ; the slots under it are under a big picture
SW_PLANES:   .res 1             ; 1: the message's planes were written over
SW_CUR:      .res 1             ; the slot being composed, $FF none
SW_LINE:     .res 1             ; and its line
SW_PRIMED:   .res 1             ; 1: the line has its background and length
SW_UPLOAD:   .res 1             ; 1: the line goes up in the next vblank
SW_UPTILE:   .res 2             ; its first tile, and its cells
SW_UPCELLS:  .res 2
SW_BGUP:     .res 1             ; 1: the background tile goes up
SW_READ:     .res 1             ; 1: the layer's rows are being read
SW_RROW:     .res 1             ; the next row the vblank reads
SW_PUT:      .res 1             ; 1: `SW_MAP` is going up
SW_PROW:     .res 1             ; the next row the vblank puts up
SW_TOP:      .res 1             ; the sw_span, in cell rows: its first
SW_BOT:      .res 1             ; and one past its last
SW_OFF:      .res 1             ; the window tilemap's row for the screen's 0
SW_X0:       .res 1             ; the objects' mask, in pixels
SW_X1:       .res 1
SW_CAM:      .res 2             ; the camera the layer was copied under
SW_COPY:     .res 1             ; 1: the layer is copied, 0: nothing beside
SW_T:        .res 2             ; scratch
SW_U:        .res 2
SW_V:        .res 2
SW_SLOT:     .res 1             ; `sw_overlay`'s slot
SW_CHG:      .res 1             ; `sw_show`'s: whether anything changed
SW_ROOM:     .res 1             ; `sw_one_window`'s: cells a line has room for
SW_C:        .res 1             ; and the line's own
SW_RDIRTY:   .res SW_ROWS       ; each row's `RD_` bits
SW_COST:     .res 1             ; the screen's lines of vblank, about
SW_PEND:     .res 1             ; one past the last row it puts up
SW_HOMED:    .res 1             ; 1: every window's text in its own tiles
SW_WAITED:   .res 1             ; vblanks it waited for them; $FF going up
SW_VT:       .res 2             ; the vblank's scratch: it may come in the
SW_VU:       .res 2             ; middle of the main loop's
SW_VV:       .res 2
SW_SC:       .res 2             ; the window's tilemap, a VRAM word: `MSG_SC`'s,
                                ; which a big picture moves
.popseg

.pushseg
.segment "FAR3"
.a8
.i16

; The last line a vblank step may start on: a row of 64 bytes, its setup and
; the clock read take well under two lines; the text line's two DMAs of up
; to 28 tiles, under seven. Before `VBLANK_WRITES_END`.
SW_ROW_LATEST  = VBLANK_WRITES_END - 2
SW_LINE_LATEST = VBLANK_WRITES_END - 7
SW_TABLES_LATEST = VBLANK_WRITES_END - 3

; X to slot A's record. A8 in and out.
.proc sw_rec_of
.a8
.i16
    sta f:WRMPYA
    lda #SW_REC
    sta f:WRMPYB                ; starts: eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    tax
    sep #$20
.a8
    rts
.endproc

; What runs in the vblank, and the doors from elsewhere, go in FAR2, bank
; $C0; the composer and the screen's composition in FAR3, bank $C1: with
; Desert Nightmare's painted maps in FAR3 the whole file did not fit one
; bank (2026-11-20, 1,043 bytes over). Each half calls the other with `jsl`.
.segment "FAR2"

; On reset and every map change, from `pic_clear`: no window, as RM2k erases
; the pictures there. Keeps X and Y.
.proc sw_clear
.a8
.i16
    php
    phx
    sep #$20
.a8
    ldx #SHOW_WINDOW_SLOTS * SW_REC - 1
each:
    lda #0
    sta f:SW_RECS, x
    dex
    bpl each
    sta f:SW_SHOWN
    sta f:SW_MAPDIRTY
    sta f:SW_PLANES
    sta f:SW_PRIMED
    sta f:SW_UPLOAD
    sta f:SW_BGUP
    sta f:SW_READ
    sta f:SW_PUT
    sta f:SW_HIDE
    sta f:SW_COVER              ; and no big picture
    sta f:SW_HOMED
    ldx #SW_ROWS - 1
rows:
    sta f:SW_RDIRTY, x
    dex
    bpl rows
    lda #$FF
    sta f:SW_CUR
    plx
    plp
    rtl
.endproc

; From `load_window`: the window's tiles and tilemap are the ROM's again
; —a map's load, a battle, a big picture—, so what is up is drawn again,
; text and all. Keeps X and Y.
.proc sw_lost
.a8
.i16
    php
    phx
    sep #$20
.a8
    lda #0
    sta f:SW_SHOWN              ; the load turned the HDMA off
    sta f:SW_PLANES             ; and stamped the planes
    sta f:SW_UPLOAD
    sta f:SW_READ
    sta f:SW_PUT
    jsl f:sw_none_shown
    jsl f:sw_all_dirty_l
    plx
    plp
    rtl
.endproc

.segment "FAR3"

; Every window up, to be composed again, and the screen, every row; and the
; ink and the background tile, which a box or a load wrote over. A8; keeps
; nothing.
.proc sw_all_dirty
.a8
.i16
    jsr sw_rows_changed
    ldx #0
    ldy #SHOW_WINDOW_SLOTS
each:
    lda f:SW_RECS + R_UP, x
    sta f:SW_RECS + R_DIRTY, x
    rep #$20
.a16
    txa
    clc
    adc #SW_REC
    tax
    sep #$20
.a8
    dey
    bne each
    lda #1
    sta f:SW_MAPDIRTY
    sta f:SW_BGUP
    lda #$FF
    sta f:SW_CUR
    sta f:MSG_INK               ; the first colour takes the ink again
    lda #0
    sta f:SW_PRIMED
    rts
.endproc

; `sw_all_dirty`, from FAR2.
sw_all_dirty_l:
    jsr sw_all_dirty
    rtl

; Every row of the screen changed. A8; keeps Y.
sw_rows_changed:
.a8
    ldx #SW_ROWS - 1
each_row:
    lda f:SW_RDIRTY, x
    ora #RD_CHANGED
    sta f:SW_RDIRTY, x
    dex
    bpl each_row
    rts

; `sw_rows_changed`, from FAR2.
sw_rows_changed_l:
    jsr sw_rows_changed
    rtl

; No window's tiles on the screen: the HDMA is off, or a box or a load
; writes over them. A8; keeps Y.
.proc sw_none_shown
.a8
.i16
    ldx #R_SUSED
    lda #SHOW_WINDOW_SLOTS
    sta f:SW_T
each:
    lda #0
    sta f:SW_RECS, x
    rep #$20
.a16
    txa
    clc
    adc #SW_REC
    tax
    sep #$20
.a8
    lda f:SW_T
    dec a
    sta f:SW_T
    bne each
    rtl
.endproc

.segment "FAR2"

; `sw_rec_of`, for FAR2's: X to slot A's record. A8 in and out.
sw_rec_of2:
.a8
    sta f:WRMPYA
    lda #SW_REC
    sta f:WRMPYB                ; starts: eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    tax
    sep #$20
.a8
    rts

; `OP_WINDOW`, from `op_window`: the operands at `[code_ptr], y`, Y past
; them. The window's record, and its text and the screen to be drawn —unless
; it is up already as it asks: Desert Nightmare's menu shows its options
; twice in a row, and a window drawn again for nothing is a dozen frames of
; the vblank's time—.
.proc sw_show
.a8
.i16
    lda [code_ptr], y           ; the slot
    iny
    phy
    jsr sw_rec_of2
    ply
    ; Where it was, for the rows to compose again if it moves.
    lda f:SW_RECS + R_Y, x
    sta f:SW_V
    lda f:SW_RECS + R_H, x
    sta f:SW_V + 1
    lda f:SW_RECS + R_UP, x
    sta f:SW_C
    eor #1
    sta f:SW_CHG                ; 1: something changed
    ; x, y, w, h, the style, the first tile and the lines, as they come.
    phx
    lda #R_N - R_X + 1
    sta f:SW_T
fields:
    lda [code_ptr], y
    iny
    cmp f:SW_RECS + R_X, x
    beq field_same
    sta f:SW_RECS + R_X, x
    lda #1
    sta f:SW_CHG
field_same:
    inx
    lda f:SW_T
    dec a
    sta f:SW_T
    bne fields
    plx
    phx
    ; The lines: each box's offset made a long pointer into `messages`, as
    ; `msg_start` makes it, and its cells, which it counts. Three shifts, as
    ; many as `MESSAGES_STEP` asks: until 2026-11-28 it was four bytes and two
    ; shifts, and this copy was the one missed when it changed.
.assert MESSAGES_CAP = 8 * $10000, error, "show_window multiplies the offset by eight, as msg_start: it is MESSAGES_STEP in engine.rs of rm2k-snes/mapdata"
    lda #0
    sta f:SW_ROOM
    lda f:SW_RECS + R_N, x
    sta f:SW_T                  ; lines left
    beq lines_done
    rep #$20
.a16
    txa
    clc
    adc #R_LINES
    tax                         ; X on the first line's four bytes
    sep #$20
.a8
line:
    rep #$20
.a16
    lda [code_ptr], y           ; the box's offset, in steps of eight
    iny
    iny
    stz temp
    asl a
    rol temp
    asl a
    rol temp
    asl a
    rol temp
    clc
    adc #.loword(messages)
    pha                         ; the low word
    lda temp                    ; one bank per 64 KB
    adc #^messages              ; with the carry of the sum
    sta f:SW_U
    pla
    cmp f:SW_RECS, x
    beq low_same
    sta f:SW_RECS, x
    sep #$20
.a8
    lda #1
    sta f:SW_CHG
low_same:
    sep #$20
.a8
    lda f:SW_U
    cmp f:SW_RECS + 2, x
    beq bank_same
    sta f:SW_RECS + 2, x
    lda #1
    sta f:SW_CHG
bank_same:
    lda [code_ptr], y           ; its cells
    iny
    sta f:SW_RECS + 3, x
    clc
    adc f:SW_ROOM
    sta f:SW_ROOM
    inx
    inx
    inx
    inx
    lda f:SW_T
    dec a
    sta f:SW_T
    bne line
lines_done:
    plx
    lda f:SW_ROOM
    asl a                       ; two rows of tiles a cell
    sta f:SW_RECS + R_USED, x
    lda f:SW_CHG
    beq done                    ; up already, as it is
    ; The rows it covered, if it was up, and the ones it covers.
    lda f:SW_C
    beq was_down
    lda f:SW_V + 1
    sta f:SW_ROOM
    lda f:SW_V
    jsr sw_mark
was_down:
    jsr sw_mark_x
    lda #1
    sta f:SW_RECS + R_UP, x
    sta f:SW_RECS + R_DIRTY, x
    sta f:SW_MAPDIRTY
    ; Being composed: it starts over.
    lda #$FF
    sta f:SW_CUR
    lda #0
    sta f:SW_PRIMED
done:
    rtl
.endproc

; `OP_WINDOW_ERASE`, from `op_window_erase`: the slot at `[code_ptr], y`, Y
; past it.
.proc sw_erase
.a8
.i16
    lda [code_ptr], y
    iny
    phy
    jsr sw_rec_of2
    ply
    lda f:SW_RECS + R_UP, x
    beq done
    lda #0
    sta f:SW_RECS + R_UP, x
    sta f:SW_RECS + R_DIRTY, x
    jsr sw_mark_x               ; the rows it covered
    lda #1
    sta f:SW_MAPDIRTY
done:
    rtl
.endproc

; The rows the window at record X covers, changed. A8; keeps X.
sw_mark_x:
.a8
    lda f:SW_RECS + R_H, x
    sta f:SW_ROOM
    lda f:SW_RECS + R_Y, x
    ; and on into `sw_mark`

; Rows A to A + `SW_ROOM` - 1 of the screen, changed. A8; keeps X.
sw_mark:
.a8
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
mark_more:
    lda f:SW_ROOM
    beq marked
    dec a
    sta f:SW_ROOM
    cpx #SW_ROWS
    bcs marked                  ; past the screen's last
    lda f:SW_RDIRTY, x
    ora #RD_CHANGED
    sta f:SW_RDIRTY, x
    inx
    bra mark_more
marked:
    plx
    rts

; `sw_mark`, from FAR3.
sw_mark_l:
    jsr sw_mark
    rtl

; `OP_WINDOW_COVER`, from `op_window_cover`: the slots under the one at
; `[code_ptr], y` covered by a big picture, Y past it. The screen again if
; that changed; their text stays composed.
.proc sw_cover
.a8
.i16
    lda [code_ptr], y
    iny
    cmp f:SW_COVER
    beq done
    sta f:SW_COVER
    jsl f:sw_rows_changed_l
    lda #1
    sta f:SW_MAPDIRTY
done:
    rtl
.endproc

.segment "FAR3"

; One frame of the windows, from the main loop after the message's: a box
; opening takes them off the screen; with none, a few letters of a window
; still to be composed, or the screen composed again, or the layer beside
; them copied again under a camera that moved. A8; keeps nothing.
;
; **What changes goes up on one frame** —taro's report, 2026-11-21: the
; menu's boxes showed for a dozen frames after each press half the old text
; and half the new—. A window's text is composed into tiles the screen does
; not show —`sw_place`—, a line a vblank, and the screen is composed again
; only on the rows something changed on; then those rows and the HDMA's
; tables go up in one vblank, the old windows on the screen until then. A
; stage in RAM for the new text, put up with the rows, was tried first: a
; description box's 36 cells are 2,304 bytes, and with the rows that is
; more than the vblank's twenty lines left on the menu —some 120 bytes a
; line, measured—.
.proc sw_tick
.a8
.i16
    lda msg_state
    ora msg_open
    ora pick_active
    beq no_box
    ; A box: off the screen —and the message's planes back, if the windows
    ; wrote over them—, and drawn again when it closes; and whatever was
    ; under way, from the start then, since the box writes over `text_buf`
    ; and the windows' tiles.
    lda f:SW_CUR
    inc a                       ; $FF: none being composed
    ora f:SW_SHOWN
    ora f:SW_PLANES
    ora f:SW_PUT
    ora f:SW_READ
    ora f:SW_UPLOAD
    beq quiet
    lda f:SW_SHOWN
    ora f:SW_PLANES
    beq not_shown
    lda #1
    sta f:SW_HIDE
not_shown:
    jsl f:sw_none_shown
    jsr sw_all_dirty
quiet:
    lda #0
    sta f:SW_UPLOAD             ; the box's line owns `text_buf` now
    sta f:SW_READ
    sta f:SW_PUT
busy:
    rtl
no_box:
    lda f:SW_HIDE
    bne busy                    ; the planes are going back
    lda f:SW_UPLOAD
    bne busy                    ; a line waits for its vblank
    lda f:SW_PUT
    bne busy                    ; the screen is going up
    lda f:SW_READ
    beq not_reading
    lda f:SW_MAPDIRTY
    beq reading
    ; Something changed while the layer's rows were read: its text first,
    ; and the rows again with the ones it touched.
    lda #0
    sta f:SW_READ
    bra not_reading
reading:
    lda f:SW_READ
    cmp #2
    bne wait                    ; the layer is being read
    ; Read: the windows over it, and the screen up.
    lda #0
    sta f:SW_READ
    jmp sw_overlay_and_put
not_reading:
    jsr sw_compose
    bcs wait                    ; a window's text is still being composed
    lda f:SW_MAPDIRTY
    bne screen
    ; The camera moved under the windows: the layer beside them again, once
    ; it is on the grid.
    lda f:SW_SHOWN
    beq wait
    jsr sw_on_grid
    bcc wait
    lda f:SW_COPY
    beq moved                   ; nothing was copied beside them
    jsr sw_camera_word
.a16
    cmp f:SW_CAM
    sep #$20
.a8
    beq wait
moved:
    jsr sw_rows_changed
screen:
    lda #0
    sta f:SW_MAPDIRTY
    lda f:SW_TOP                ; the span on the screen, to tell whether
    sta f:SW_U                  ; it moves
    lda f:SW_BOT
    sta f:SW_U + 1
    jsr sw_span
    bcc none_up
    jsr sw_rows_now
    ; The layer's rows first: the vblank reads them into `SW_MAP`, and the
    ; windows go over them when it is done.
    jsr sw_camera_word
.a16
    sta f:SW_CAM
    sep #$20
.a8
    jsr sw_on_grid
    lda #0
    rol a
    sta f:SW_COPY
    beq blank_rows
    lda f:SW_TOP
    sta f:SW_RROW
    lda #1
    sta f:SW_READ
wait:
    rtl
blank_rows:
    jsr sw_clear_span
    jmp sw_overlay_and_put
none_up:
    ; Nothing up: off the screen.
    lda f:SW_SHOWN
    ora f:SW_PLANES
    beq wait
    lda #1
    sta f:SW_HIDE
    rtl
.endproc

; The rows this screen takes, `RD_NOW`: the ones a change touched inside the
; span, or all of it if the span moved or was not on the screen —its rows
; land elsewhere in the window's tilemap then—. Outside the span a row is
; not seen, and when the span grows over it, it moved. The old span in
; `SW_U` and `SW_U + 1`. A8; keeps nothing.
.proc sw_rows_now
.a8
.i16
    lda f:SW_SHOWN
    beq all
    lda f:SW_U
    cmp f:SW_TOP
    bne all
    lda f:SW_U + 1
    cmp f:SW_BOT
    beq each_start
    ; Only its bottom moved: the rows on the screen stay where they were in
    ; the window's tilemap, and the ones past the shorter span are new.
    bcc shorter
    lda f:SW_BOT
shorter:
    pha                         ; the shorter span's end
    sta f:SW_ROOM
    lda #SW_ROWS
    sec
    sbc f:SW_ROOM
    sta f:SW_ROOM
    pla
    jsl f:sw_mark_l
    bra each_start
all:
    jsr sw_rows_changed
each_start:
    ldx #SW_ROWS - 1
each:
    txa                         ; X's low byte: below 28
    cmp f:SW_TOP
    bcc out
    cmp f:SW_BOT
    bcs out
    lda f:SW_RDIRTY, x
    lsr a                       ; RD_CHANGED to the carry
    bcc next
    lda #RD_NOW
    bra put
out:
    lda #0
put:
    sta f:SW_RDIRTY, x
next:
    dex
    bpl each
    rts
.endproc

; The rows are in `SW_MAP`: the windows over them, and the screen up in the
; vblank that has room for those rows and the tables: how many lines that
; is, about; and which tiles will be on the screen then. From `sw_tick`. A8.
.proc sw_overlay_and_put
.a8
.i16
    jsr sw_overlay
    ; The rows it puts up: from the first this screen takes to the last,
    ; and the ones between as they are —see `sw_commit`—; and theirs taken
    ; now, so that only a change since keeps a row.
    lda #$FF
    sta f:SW_PROW
    lda #0
    sta f:SW_PEND
    ldx #0
range:
    lda f:SW_RDIRTY, x
    and #RD_NOW
    beq range_next
    lda f:SW_PROW
    cmp #$FF
    bne first_kept
    txa                         ; X's low byte: below 28
    sta f:SW_PROW
first_kept:
    txa
    inc a
    sta f:SW_PEND
    lda #RD_CHANGED
    and f:SW_RDIRTY, x
    sta f:SW_RDIRTY, x
range_next:
    inx
    cpx #SW_ROWS
    bne range
    lda f:SW_PROW
    cmp #$FF
    bne some_rows
    lda #0                      ; none: the tables only
    sta f:SW_PROW
    sta f:SW_PEND
some_rows:
    ; A row is 64 bytes, and a line of the vblank moves some 120 by DMA
    ; —measured in snes9x on Desert Nightmare's menu, 2026-11-21: 2,316
    ; bytes from line 234 to 252—: half a line a row and six lines for
    ; the setups, the clock and the tables —measured the same day: the
    ; tables alone, three—.
    lda f:SW_PEND
    sec
    sbc f:SW_PROW
    lsr a
    clc
    adc #6
    sta f:SW_COST
    ; The tiles on the screen once it is up: each window's that is up and
    ; not under a big picture. No window is composed into them until another
    ; screen goes up: see `sw_place`.
    lda #0
    sta f:SW_V
shown:
    lda f:SW_V
    jsr sw_rec_of
    lda f:SW_RECS + R_BASE, x
    sta f:SW_RECS + R_SBASE, x
    lda f:SW_V
    cmp f:SW_COVER
    lda #0
    bcc covered
    lda f:SW_RECS + R_UP, x
    beq covered
    lda f:SW_RECS + R_USED, x
covered:
    sta f:SW_RECS + R_SUSED, x
    lda f:SW_V
    inc a
    sta f:SW_V
    cmp #SHOW_WINDOW_SLOTS
    bne shown
    lda #0
    sta f:SW_WAITED
    sta f:SW_HOMED
    lda #1
    sta f:SW_PUT
    rtl
.endproc

.segment "FAR2"

; `SW_SC` from `MSG_SC`, BG2SC's byte: the window's tilemap where the map
; has it, or where a big picture moved it —over one, the windows go over the
; picture, and the layer above they copy is the one it emptied—. A8.
sw_tilemap:
.a8
    rep #$20
.a16
    lda f:MSG_SC
    and #$00FC
    xba
    sta f:SW_SC
    sep #$20
.a8
    rts

.segment "FAR3"

; The camera as one word, to tell whether it moved: `message_layer.s`'s. A16
; out.
sw_camera_word:
.a8
    rep #$20
.a16
    lda scroll_y
    inc a
    xba
    eor f:screen_x
    rts

; The carry set if the screen's cells are the layer's: the camera on the
; 8-pixel grid, and BG2 the layer above —not a panorama's—. A8.
sw_on_grid:
.a8
    lda f:PANO_ON
    cmp #3
    beq off
    lda f:screen_x
    and #7
    bne off
    lda scroll_y
    inc a
    and #7
    bne off
    sec
    rts
off:
    clc
    rts

; The sw_span of the windows up, in `SW_TOP` and `SW_BOT`, and their left and
; right edges in `SW_X0` and `SW_X1`; the carry clear if none is up. A8;
; keeps nothing.
.proc sw_span
.a8
.i16
    lda #$FF
    sta f:SW_TOP
    sta f:SW_X0
    lda #0
    sta f:SW_BOT
    sta f:SW_X1
    sta f:SW_V                  ; none up so far
    ; From the first slot a big picture does not cover.
    lda f:SW_COVER
    cmp #SHOW_WINDOW_SLOTS
    bcs done                    ; all of them: none up
    jsr sw_rec_of
    lda #SHOW_WINDOW_SLOTS
    sec
    sbc f:SW_COVER
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
each:
    lda f:SW_RECS + R_UP, x
    beq next
    sta f:SW_V
    lda f:SW_RECS + R_Y, x
    cmp f:SW_TOP
    bcs top_kept
    sta f:SW_TOP
top_kept:
    clc
    adc f:SW_RECS + R_H, x
    cmp f:SW_BOT
    bcc bot_kept
    sta f:SW_BOT
bot_kept:
    lda f:SW_RECS + R_X, x
    asl a
    asl a
    asl a
    cmp f:SW_X0
    bcs x0_kept
    sta f:SW_X0
x0_kept:
    lda f:SW_RECS + R_X, x
    clc
    adc f:SW_RECS + R_W, x
    asl a
    asl a
    asl a                       ; one past the right edge: 256 is 0
    dec a                       ; the last pixel
    cmp f:SW_X1
    bcc x1_kept
    sta f:SW_X1
x1_kept:
next:
    rep #$20
.a16
    txa
    clc
    adc #SW_REC
    tax
    sep #$20
.a8
    dey
    bne each
done:
    lda f:SW_V
    cmp #1                      ; the carry set if one was up
    rts
.endproc

; Zero entries on the sw_span's rows of `SW_MAP` this screen takes: the
; window's tile 0 is BG2's first, blank on every map. A8; keeps nothing.
.proc sw_clear_span
.a8
.i16
    jsr sw_row_x_top
    lda f:SW_BOT
    sec
    sbc f:SW_TOP
    sta f:SW_T                  ; rows
    rep #$20
.a16
row:
    txa
    jsr sw_row_now
    rep #$20
.a16
    bne clear
    txa
    clc
    adc #64
    tax
    bra row_done
clear:
    ldy #32
cell:
    lda #0
    sta f:SW_MAP, x
    inx
    inx
    dey
    bne cell
row_done:
    sep #$20
.a8
    lda f:SW_T
    dec a
    sta f:SW_T
    rep #$20
.a16
    bne row
    sep #$20
.a8
    rts
.endproc

; Whether the row of `SW_MAP`'s byte A is one this screen takes: Z clear if
; it is. A16 in, A8 out; keeps X and Y.
sw_row_now:
.a16
    phx
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; 64 bytes a row
    tax
    sep #$20
.a8
    lda f:SW_RDIRTY, x
    and #RD_NOW
    plx
    cmp #0                      ; `plx` left Z from X
    rts

; X to the byte of `SW_MAP` where row `SW_TOP` starts. A8 in and out.
sw_row_x_top:
.a8
    lda f:SW_TOP
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a                       ; times 64 bytes a row
    tax
    sep #$20
.a8
    rts

; The windows up over `SW_MAP`, the lowest slot first, from the first a big
; picture does not cover: `sw_span` found one. A8; keeps nothing.
.proc sw_overlay
.a8
.i16
    jsr sw_frame_entries
    lda f:SW_COVER
    sta f:SW_SLOT                  ; the slot
each:
    lda f:SW_SLOT
    jsr sw_rec_of
    lda f:SW_RECS + R_UP, x
    beq next
    jsr sw_one_window
next:
    lda f:SW_SLOT
    inc a
    sta f:SW_SLOT
    cmp #SHOW_WINDOW_SLOTS
    bne each
    rts
.endproc

; The message window's frame, its eight pieces, and its first text cell, out
; of the plane `stamp_window` chose —`MSG_CELLS_PTR`, rows 0 to 9 the framed
; window, 32 cells a row—, to `SW_FRAME`: top left, top, top right, left,
; right, bottom left, bottom, bottom right, and the text's first. A8.
.proc sw_frame_entries
.a8
.i16
    lda f:MSG_CELLS_PTR + 2
    sta comp_glyph + 2
    rep #$20
.a16
    lda f:MSG_CELLS_PTR
    sta comp_glyph
    ldx #0
each:
    phx
    lda f:sw_frame_at, x
    tay
    lda [comp_glyph], y
    sta f:SW_FRAME, x
    plx
    inx
    inx
    cpx #18
    bne each
    sep #$20
.a8
    rts
.endproc

; Where each of `SW_FRAME`'s nine is in the plane, in bytes.
sw_frame_at:
    .word 0, 2, 31 * 2, 32 * 2, 63 * 2, 288 * 2, 289 * 2, 319 * 2, 33 * 2
F_TL = 0
F_T  = 2
F_TR = 4
F_L  = 6
F_R  = 8
F_BL = 10
F_B  = 12
F_BR = 14
F_TEXT = 16

; The window at record X over `SW_MAP`: its frame or its background, and its
; text's cells. A8; keeps nothing.
.proc sw_one_window
.a8
.i16
    rep #$20
.a16
    txa
    sta f:SW_U                  ; the record, for what follows
    sep #$20
.a8
    ; Its first cell's byte in `SW_MAP`, in SW_T.
    lda f:SW_RECS + R_Y, x
    jsr sw_row_bytes
.a16
    sta f:SW_T
    lda f:SW_RECS + R_X, x
    and #$00FF
    asl a
    clc
    adc f:SW_T
    sta f:SW_T
    sep #$20
.a8
    ; Row by row: `temp` the row, `temp + 1` the column.
    lda #0
    sta temp
row:
    lda #0
    sta temp + 1
    rep #$20
.a16
    lda f:SW_T
    tay                         ; Y on the cell
    jsr sw_row_now
.a8
    beq row_done                ; a row this screen does not take
cell:
    jsr record_x
    jsr sw_piece                   ; A16: the cell's entry
.a16
    tyx
    sta f:SW_MAP, x
    iny
    iny
    sep #$20
.a8
    jsr record_x
    inc temp + 1
    lda temp + 1
    cmp f:SW_RECS + R_W, x
    bne cell
row_done:
    rep #$20
.a16
    lda f:SW_T
    clc
    adc #64
    sta f:SW_T
    sep #$20
.a8
    inc temp
    lda temp
    cmp f:SW_RECS + R_H, x
    bne row

    ; The text's cells, line by line: two rows of `cells`, the top one's
    ; tiles first and then the bottom one's.
    lda f:SW_RECS + R_N, x
    bne some
    rts
some:
    sta temp + 2                ; lines left
    ; The first line's first cell: one in from the frame, or at the corner.
    lda f:SW_RECS + R_STYLE, x
    eor #SW_STYLE_PLAIN
    and #1                      ; 1 framed, 0 plain
    sta temp + 3
    ; The cells a line has room for: past them it would ink its neighbour.
    ; The compiler gives no line more since 2026-11-20 —each line has its
    ; own cells, not the widest of its id's—: kept as a guard.
    asl a
    eor #$FF
    sec
    adc f:SW_RECS + R_W, x      ; w minus the frame's two
    sta f:SW_ROOM
    lda temp + 3
    clc
    adc f:SW_RECS + R_Y, x
    jsr sw_row_bytes
.a16
    sta f:SW_T
    lda f:SW_RECS + R_X, x
    clc
    adc temp + 3
    and #$00FF
    asl a
    clc
    adc f:SW_T
    sta f:SW_T                  ; the line's top left cell, in `SW_MAP`
    ; The text's first entry, plus the window's first tile.
    lda f:SW_RECS + R_BASE, x
    and #$00FF
    clc
    adc f:SW_FRAME + F_TEXT
    sta f:SW_V                  ; the next tile's entry
    lda f:SW_U
    clc
    adc #R_LINES + 3
    sta f:SW_U                  ; on the first line's cells
    sep #$20
.a8
line:
    jsr record_x
    lda f:SW_RECS, x            ; this line's cells
    beq line_done
    sta f:SW_C
    cmp f:SW_ROOM
    bcc fits
    lda f:SW_ROOM
fits:
    sta temp + 1                ; the ones drawn
    ; The top row, and the bottom one.
    rep #$20
.a16
    lda f:SW_T
    tax
    jsr cells_run
    lda f:SW_T
    clc
    adc #64
    tax
    jsr cells_run
    sep #$20
.a8
line_done:
    rep #$20
.a16
    lda f:SW_T
    clc
    adc #128                    ; two rows down
    sta f:SW_T
    lda f:SW_U
    clc
    adc #4
    sta f:SW_U
    sep #$20
.a8
    dec temp + 2
    bne line
    rts

; `temp + 1` cells from X on, each the next tile's entry from `SW_V`; and
; `SW_V` past the row's `SW_C` tiles, the line's whole run. A16.
cells_run:
.a16
    txa
    jsr sw_row_now
    rep #$20
.a16
    beq run_done                ; a row this screen does not take
    lda temp + 1
    and #$00FF
    tay
    lda f:SW_V
run:
    sta f:SW_MAP, x
    inc a
    inx
    inx
    dey
    bne run
run_done:
    lda f:SW_C
    and #$00FF
    clc
    adc f:SW_V
    sta f:SW_V
    rts

; X to `SW_U`. A8 in and out.
record_x:
.a8
    rep #$20
.a16
    lda f:SW_U
    tax
    sep #$20
.a8
    rts
.endproc

; Cell row A's first byte in `SW_MAP`. A8 in, A16 out.
sw_row_bytes:
.a8
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a                       ; times 64 bytes a row
    rts

; The entry of cell (`temp + 1`, `temp`) of the window at record X: its
; frame's sw_piece, or its background. A8 in, A16 out; keeps Y.
.proc sw_piece
.a8
.i16
    lda f:SW_RECS + R_STYLE, x
    cmp #SW_STYLE_PLAIN
    beq background
    ; The row's kind —0 the top, 2 the bottom, 1 between— times three, plus
    ; the column's: the place in `piece_of`.
    lda f:SW_RECS + R_H, x
    dec a
    sta f:SW_V
    lda temp
    jsr kind
    sta f:SW_V + 1
    asl a
    clc
    adc f:SW_V + 1
    sta f:SW_V + 1
    lda f:SW_RECS + R_W, x
    dec a
    sta f:SW_V
    lda temp + 1
    jsr kind
    clc
    adc f:SW_V + 1
    rep #$20
.a16
    and #$00FF
    phx
    tax
    lda f:sw_piece_of, x
    plx
    and #$00FF
    cmp #$00FF
    beq background_16
    phx
    tax
    lda f:SW_FRAME, x
    plx
    rts
background:
    rep #$20
background_16:
.a16
    lda f:SW_FRAME + F_TEXT
    clc
    adc #SW_BACKGROUND
    rts

; A against the last, `SW_V`: 0 the first, 2 the last, 1 between. A8.
kind:
.a8
    cmp #0
    beq first
    cmp f:SW_V
    beq last
    lda #1
    rts
first:
    lda #0
    rts
last:
    lda #2
    rts
.endproc

; Which of `SW_FRAME` each place takes, by row kind and column kind; $FF the
; background.
sw_piece_of:
    .byte F_TL, F_T, F_TR
    .byte F_L, $FF, F_R
    .byte F_BL, F_B, F_BR

; A few letters of the lowest window still to be composed; the carry set
; while one is. A8; keeps nothing.
.proc sw_compose
.a8
.i16
top:
    lda f:SW_CUR
    cmp #$FF
    bne going
    ; The next: the lowest slot up whose text is dirty.
    lda #0
    sta f:SW_V
find:
    lda f:SW_V
    jsr sw_rec_of
    lda f:SW_RECS + R_DIRTY, x
    bne found
    lda f:SW_V
    inc a
    sta f:SW_V
    cmp #SHOW_WINDOW_SLOTS
    bne find
    clc                         ; none
    rts
found:
    lda #0
    sta f:SW_RECS + R_DIRTY, x
    sta f:SW_LINE
    sta f:SW_PRIMED
    lda f:SW_V
    sta f:SW_CUR
    jsr sw_place
going:
    lda f:SW_CUR
    jsr sw_rec_of
    lda f:SW_LINE
    cmp f:SW_RECS + R_N, x
    bcc a_line
    lda #$FF                    ; its lines are done
    sta f:SW_CUR
    bra top
a_line:
    jsr line_x
    lda f:SW_RECS + 3, x
    bne has_cells
    jmp next_line               ; an empty line: nothing to sw_compose
has_cells:
    lda f:SW_PRIMED
    bne letters
    ; The line starts: the background into `text_buf`, the pointer on its
    ; box past the header, its length, colour 0, and its edge.
    jsr sw_prime
    jsr line_x
    lda f:SW_RECS + 2, x
    sta msg_ptr + 2
    rep #$20
.a16
    lda f:SW_RECS, x
    sta msg_ptr
    sep #$20
.a8
    ldy #1
    lda [msg_ptr], y            ; the length: the header says one line
    sta msg_length
    rep #$20
.a16
    inc msg_ptr                 ; past the header and the length: a box
    inc msg_ptr                 ; starts at a multiple of four, so these
                                ; two never cross a bank's edge
    lda #WINDOW_BORDER          ; `compose_char`'s x counts from the frame
    sta msg_x
    lda f:SW_RECS + 3, x        ; and the edge, the line's cells
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc #WINDOW_BORDER
    sta f:MSG_EDGE
    sep #$20
.a8
    stz msg_col
    lda #0
    sta f:FAR_MSG_SECOND        ; no half of a pair, no digit waiting
    sta f:MSG_DIGITS_N
    jsr sw_colour_zero
    lda #1
    sta f:SW_PRIMED
letters:
    lda #MSG_CHARS * 3          ; a frame's letters: no box is being typed
    sta f:SW_V + 1
other:
    lda msg_col
    cmp msg_length
    bcs line_end
    lda f:SW_V + 1
    beq paused
    dec a
    sta f:SW_V + 1
    jsl f:msg_letter
    cmp #MSG_CONTROLLED
    beq other                   ; a colour: the length went down by one
    inc msg_col
    rep #$20
.a16
    and #$00FF
    sta comp_char
    lda msg_x
    sta comp_col
    ; Past the edge it is not drawn: `compose_char` would write past the
    ; line's cells —see `message_tick`—.
    ldx comp_char
    lda f:msg_font_reach, x
    and #$00FF
    clc
    adc comp_col
    cmp f:MSG_EDGE
    sep #$20
.a8
    bcs no_draw
    jsl f:compose_char_far      ; the message window's letter: messages.s
    jsl f:msg_ink_char
no_draw:
    rep #$20
.a16
    ldx comp_char
    lda f:msg_font_advance, x
    and #$00FF
    clc
    adc msg_x
    sta msg_x
    sep #$20
.a8
    bra other
paused:
    sec
    rts
line_end:
    ; The line goes up in the next vblank: its first tile —the window's,
    ; plus two rows of each line before it— and its cells.
    lda f:SW_CUR
    jsr sw_rec_of
    lda f:SW_RECS + R_BASE, x
    sta f:SW_UPTILE
    lda #0
    sta f:SW_UPTILE + 1
    sta f:SW_UPCELLS + 1
    lda f:SW_LINE
    sta f:SW_T                  ; lines before it
    rep #$20
.a16
    txa
    clc
    adc #R_LINES + 3
    tax                         ; on the first line's cells
    sep #$20
.a8
before:
    lda f:SW_T
    beq this_one
    dec a
    sta f:SW_T
    lda f:SW_RECS, x
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc f:SW_UPTILE
    sta f:SW_UPTILE
    inx
    inx
    inx
    inx
    sep #$20
.a8
    bra before
this_one:
    lda f:SW_RECS, x
    sta f:SW_UPCELLS
    lda #1
    sta f:SW_UPLOAD
next_line:
    lda #0
    sta f:SW_PRIMED
    lda f:SW_LINE
    inc a
    sta f:SW_LINE
    sec                         ; still composing
    rts
; X on line `SW_LINE`'s four bytes of slot `SW_CUR`. A8 in and out.
line_x:
.a8
    lda f:SW_CUR
    jsr sw_rec_of
    lda f:SW_LINE
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    sta f:SW_U
    txa
    clc
    adc f:SW_U
    adc #R_LINES
    tax
    sep #$20
.a8
    rts
.endproc

; Which tiles the text of slot `SW_CUR`, about to be composed, goes to:
; `R_BASE`, the first of a run of `R_USED` that are not on the screen and
; that no other window up takes. So the screen keeps showing the window's
; old text while the new one is composed, a line a vblank, and the new one
; shows when the screen goes up with the rows that point at it —one vblank,
; and a few rows: see `sw_commit`—. The converter gives each window id
; tiles of its own, `R_TILES`, the most any window of that id takes, so
; that windows up together never meet (`windows.rs` in rm2k-snes-events):
; with every id's in use a window has no room for a second copy of itself,
; but the ids not up leave theirs, and on Desert Nightmare's menu the
; description box finds room for its new text in all the screens the tests
; walk —not, perhaps, in a full grid with a long description—.
;
; When no run is free of the screen's tiles, one that may take the window's
; own: its text changes on the screen a line at a time, as all of them did
; before 2026-11-21. When not even that, every window goes back to its own
; tiles and is composed again —`SW_HOMED`, until that screen goes up—. A8;
; keeps nothing.
.proc sw_place
.a8
.i16
    lda f:SW_CUR
    jsr sw_rec_of
    lda f:SW_HOMED
    beq free
    lda f:SW_RECS + R_TILES, x
    jmp placed
free:
    lda f:SW_RECS + R_USED, x
    sta f:SW_C                  ; the run's length
    beq placed                  ; no text: anywhere
    lda #0
    sta f:SW_ROOM               ; 0: not on the screen's tiles; 1: but its own
round:
    lda #0
    sta f:SW_T                  ; the run's first
again:
    lda f:SW_T
    clc
    adc f:SW_C
    bcs full
    cmp #SW_BACKGROUND + 1
    bcs full                    ; past the last text tile
    lda #0
    sta f:SW_SLOT
each:
    lda f:SW_SLOT
    jsr sw_rec_of
    lda f:SW_SLOT
    cmp f:SW_CUR
    bne other
    lda f:SW_ROOM
    bne next                    ; its own, which it may take now
    jsr on_screen
    bcs again
    bra next
other:
    jsr on_screen
    bcs again
    lda f:SW_RECS + R_UP, x
    beq next
    lda f:SW_RECS + R_BASE, x   ; what another window up has composed
    sta f:SW_V
    lda f:SW_RECS + R_USED, x
    sta f:SW_V + 1
    jsr clash
    bcs again
next:
    lda f:SW_SLOT
    inc a
    sta f:SW_SLOT
    cmp #SHOW_WINDOW_SLOTS
    bne each
    lda f:SW_CUR
    jsr sw_rec_of
    lda f:SW_T
placed:
    sta f:SW_RECS + R_BASE, x
    rts
full:
    lda f:SW_ROOM
    bne home
    inc a
    sta f:SW_ROOM
    jmp round
home:
    ; No room even so: everything to its own tiles.
    lda #1
    sta f:SW_HOMED
    lda f:SW_CUR
    sta f:SW_SLOT
    jsr sw_all_dirty
    lda f:SW_SLOT               ; `sw_all_dirty` let go of it: this one is
    sta f:SW_CUR                ; being composed, from its first line
    jsr sw_rec_of
    lda #0
    sta f:SW_RECS + R_DIRTY, x
    lda f:SW_RECS + R_TILES, x
    bra placed

; The tiles of the window at record X that are on the screen, against the
; run: `clash`.
on_screen:
    lda f:SW_RECS + R_SBASE, x
    sta f:SW_V
    lda f:SW_RECS + R_SUSED, x
    sta f:SW_V + 1
    ; and on into `clash`

; The carry set if the run, `SW_C` tiles from `SW_T`, meets the `SW_V + 1`
; from `SW_V`, and then the run moved past them. Neither goes past tile
; 239. A8; keeps X.
clash:
    lda f:SW_V + 1
    beq apart                   ; none
    lda f:SW_V
    clc
    adc f:SW_V + 1
    sta temp                    ; one past them
    lda f:SW_T
    cmp temp
    bcs apart                   ; the run starts after them
    lda f:SW_T
    clc
    adc f:SW_C
    cmp f:SW_V
    beq apart
    bcc apart                   ; and ends before them
    lda temp
    sta f:SW_T
    sec
    rts
apart:
    clc
    rts
.endproc

; `text_buf` with the window's background under every cell: the first line
; of the text area's, `prime_line`'s. A8.
.proc sw_prime
.a8
.i16
    rep #$20
.a16
    lda #.loword(text_buf)
    sta f:WMADDL
    win_lo window_backdrop, WS_BACKDROP
    sta f:A1T0L
    lda #TEXT_BUF_BYTES
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH                ; the buffer lives in WRAM bank 0
    win_bank window_backdrop, WS_BACKDROP
    sta f:A1B0
    lda #$00                    ; one register, one byte at a time
    sta f:DMAP0
    lda #<WMDATA
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rts
.endproc

; Colour 0 and its rows, as a box starts: `colour` with 0. A8.
sw_colour_zero:
.a8
    lda #0
    jmp colour

.segment "FAR2"

; In the vblank, from `flush_video` when no message is up: what the windows
; left to go up, if it fits, and their HDMA. The carry set when they are on
; the screen: `flush_video` has nothing more to do for the window. Keeps X
; and Y.
.proc sw_vblank
.a8
.i16
    phx
    phy
    ; A box being composed owns the window's tiles: only taking the windows
    ; off the screen, and the planes back.
    lda msg_state
    ora pick_active
    beq free
    jmp no_put
free:
    lda f:SW_UPLOAD
    beq no_line
    jsl f:vblank_line
.a16
    cmp #SW_LINE_LATEST + 1
    sep #$20
.a8
    bcs no_line
    jsr sw_line_up
    VBLANK_WROTE 8
no_line:
.if ::TEXT_INK_ENTRY > 0
    lda f:MSG_INK_SET
    beq no_ink
    jsl f:vblank_line
.a16
    cmp #SW_ROW_LATEST + 1
    sep #$20
.a8
    bcs no_ink
    lda #0
    sta f:MSG_INK_SET
    lda #TEXT_INK_ENTRY
    sta f:CGADD
    lda f:MSG_INK_WORD
    sta f:CGDATA
    lda f:MSG_INK_WORD + 1
    sta f:CGDATA
no_ink:
.endif
    lda f:SW_BGUP
    beq no_bg
    jsl f:vblank_line
.a16
    cmp #SW_ROW_LATEST + 1
    sep #$20
.a8
    bcs no_bg
    jsr sw_background_up
    lda #0
    sta f:SW_BGUP
no_bg:
    lda f:SW_READ
    beq no_read
    jsr sw_read_rows
no_read:
    lda f:SW_PUT
    beq no_put
    jsr sw_commit
no_put:
    lda f:SW_HIDE
    beq no_hide
    jsr sw_hide
no_hide:
    lda f:SW_SHOWN
    beq off
    ; On the screen: the camera for the map's stretches, as `flush_video`
    ; does for a message's, and the channels on while the vblank lasts.
    rep #$20
.a16
    lda f:screen_x
    sta hdma_ofs_map
    lda scroll_y
    sta hdma_ofs_map + 2
    sep #$20
.a8
    jsl f:pano_hdma
    lda f:BIG_FLAGS
    and #BIG_WAVE_ON
    ora #HDMA_WINDOW
    ora f:PANO_HDMA             ; and BG1's mask, in a flattened map
    bit HVBJOY
    bpl shown
    sta HDMAEN
shown:
    ply
    plx
    sec
    rtl
off:
    ply
    plx
    clc
    rtl
.endproc

; The composed line's two rows of cells to their tiles: the top row's
; `SW_UPCELLS` tiles from `SW_UPTILE`, and the bottom row's right after.
; A8.
.proc sw_line_up
.a8
.i16
    lda #0
    sta f:SW_UPLOAD
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    stz A1B0                    ; `text_buf` lives in bank 0
    ldx map_ofs
    rep #$20
.a16
    lda f:SW_UPTILE
    clc
    adc #WINDOW_TEXT_BASE
    asl a
    asl a
    asl a
    asl a                       ; sixteen words a tile
    clc
    adc f:map_table + M_VRAM_WINDOW, x
    sta f:SW_VT
    sta VMADDL
    lda #.loword(text_buf)
    sta A1T0L
    lda f:SW_UPCELLS
    xba
    lsr a
    lsr a
    lsr a                       ; times 32 bytes
    sta f:SW_VU
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda f:SW_VU                  ; the bottom row, past the top's tiles
    lsr a
    clc
    adc f:SW_VT
    sta VMADDL
    lda #.loword(text_buf) + WINDOW_TEXT_COLS * 32
    sta A1T0L
    lda f:SW_VU
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rts
.endproc

; The windows' background tile: the text area's first cell of its
; background, to tile `SW_BACKGROUND`. A8.
.proc sw_background_up
.a8
.i16
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    win_bank window_backdrop, WS_BACKDROP
    sta A1B0
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_VRAM_WINDOW, x
    clc
    adc #(WINDOW_TEXT_BASE + SW_BACKGROUND) * 16
    sta VMADDL
    win_lo window_backdrop, WS_BACKDROP
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rts
.endproc

; The layer's tilemap rows under the sw_span that this screen takes, one at a
; time while they fit, to `SW_MAP`; the windows over them and the screen up
; when the last is in. A8.
.proc sw_read_rows
.a8
.i16
row:
    lda f:SW_RROW
    cmp f:SW_BOT
    bne a_row
    jmp all_rows
a_row:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:SW_RDIRTY, x
    and #RD_NOW
    bne take
    lda f:SW_RROW               ; one it does not take
    inc a
    sta f:SW_RROW
    bra row
take:
    jsl f:vblank_line
.a16
    cmp #SW_ROW_LATEST + 1
    sep #$20
.a8
    bcc fits
    jmp later
fits:
    lda #$80
    sta VMAIN
    lda #$81                    ; from the PPU to the RAM, two registers
    sta DMAP0
    lda #<VMDATALREAD
    sta BBAD0
    lda #^SW_MAP
    sta A1B0
    ; The screen's row R: the layer's row under it, and its column under
    ; the screen's left edge.
    lda f:SW_RROW
    rep #$20
.a16
    and #$00FF
    pha
    xba
    lsr a
    lsr a
    clc
    adc #.loword(SW_MAP)
    sta A1T0L
    lda scroll_y
    inc a
    lsr a
    lsr a
    lsr a
    clc
    adc 1, s
    and #31
    asl a
    asl a
    asl a
    asl a
    asl a
    sta 1, s                    ; the row's first word in a screen
    lda f:screen_x
    lsr a
    lsr a
    lsr a
    and #63
    sta f:SW_VT                  ; the column
    and #31
    sta f:SW_VU                  ; inside its screen
    lda f:SW_VT
    and #32
    asl a
    asl a
    asl a
    asl a
    asl a                       ; the screen: $400 words each
    sta f:SW_VV
    clc
    adc 1, s
    adc f:SW_VU
    adc #VRAM_ABOVE_MAP
    sta VMADDL
    jsr prefetched
    lda #32
    sec
    sbc f:SW_VU
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda f:SW_VV
    eor #$0400                  ; the other screen, from its left edge
    clc
    adc 1, s
    adc #VRAM_ABOVE_MAP
    sta VMADDL
    jsr prefetched
    pla
    lda f:SW_VU
    asl a
    beq one_piece               ; zero bytes would be 64 KB
    sta DAS0L                   ; `A1T0L` went on past the first sw_piece
    sep #$20
.a8
    lda #$01
    sta MDMAEN
one_piece:
    sep #$20
.a8
    lda f:SW_RROW
    inc a
    sta f:SW_RROW
    jmp row
all_rows:
    lda #2                      ; read: `sw_tick` puts the windows over
    sta f:SW_READ               ; them, outside the vblank
later:
    rts

; After writing VMADD for a read, the word read and thrown away: see
; `prefetched` in message_layer.s. A16, which it keeps.
prefetched:
.a16
    sep #$20
.a8
    lda VMDATALREAD
    lda VMDATALREAD + 1
    rep #$20
.a16
    rts
.endproc

; The screen up: the rows of `SW_MAP` this screen takes to the window's
; tilemap —from its row `SW_PLANE_ROW` on,
; wrapping—, and the HDMA's tables. All in one vblank, so that the screen
; goes from the old windows to the new ones between two frames: it starts
; only on a vblank with `SW_COST` lines left, and waits for one —the old
; windows stay meanwhile—. After `SW_WAIT_MAX` vblanks without room it goes
; up a piece at a time as they fit, as everything went before 2026-11-21:
; the frames in between show part of the change. A8.
SW_WAIT_MAX = 2
.proc sw_commit
.a8
.i16
    jsr sw_tilemap
    lda #SW_PLANE_ROW
    sec
    sbc f:SW_TOP
    and #31
    sta f:SW_OFF
    lda f:SW_WAITED
    cmp #SW_WAIT_MAX
    bcs go                      ; going up, or waited enough
    ; The last line it may start on. Off the vblank, `vblank_line` is $FFFF.
    rep #$20
.a16
    lda f:SW_COST
    and #$00FF
    eor #$FFFF
    sec
    adc #VBLANK_WRITES_END      ; the end, less the cost
    sta f:SW_VT
    sep #$20
.a8
    jsl f:vblank_line
.a16
    cmp f:SW_VT
    sep #$20
.a8
    bcc go
    beq go
    lda f:SW_WAITED
    inc a
    sta f:SW_WAITED
    rts
go:
    lda #$FF
    sta f:SW_WAITED
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #^SW_MAP
    sta A1B0
row:
    ; From `SW_PROW` to `SW_PEND`: one DMA, or two where the rows wrap past
    ; the window tilemap's last. The rows between the ones this screen takes
    ; go up too, as they are: a row has to go up for less than a DMA's setup
    ; costs to skip it —a scanline is some forty instructions—.
    lda f:SW_PROW
    cmp f:SW_PEND
    bcc a_run
    jmp all_rows
a_run:
    clc
    adc f:SW_OFF
    and #31
    sta f:SW_VU                 ; where the first lands
    lda f:SW_PEND
    sec
    sbc f:SW_PROW
    sta f:SW_VT                 ; how many
    lda #32
    sec
    sbc f:SW_VU
    cmp f:SW_VT
    bcs whole
    sta f:SW_VT                 ; up to the tilemap's last row
whole:
    lda f:SW_VT
    lsr a
    eor #$FF
    sec
    adc #VBLANK_WRITES_END - 2  ; the last line it may start on: half a
    sta f:SW_VV                 ; line a row, and its setup
    lda #0
    sta f:SW_VV + 1
    jsl f:vblank_line
.a16
    cmp f:SW_VV
    sep #$20
.a8
    bcc fits
    beq fits
    jmp later
fits:
    lda f:SW_VU
    cmp #SW_PLANE_ROW
    bcs past_planes
    lda #1
    sta f:SW_PLANES             ; a message's plane, written over
past_planes:
    rep #$20
.a16
    lda f:SW_VU
    and #$00FF
    xba
    lsr a
    lsr a
    lsr a                       ; 32 words a row
    clc
    adc f:SW_SC
    sta VMADDL
    lda f:SW_PROW
    and #$00FF
    xba
    lsr a
    lsr a
    clc
    adc #.loword(SW_MAP)
    sta A1T0L
    lda f:SW_VT
    and #$00FF
    xba
    lsr a
    lsr a                       ; 64 bytes a row
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    lda f:SW_PROW
    clc
    adc f:SW_VT
    sta f:SW_PROW
    jmp row
all_rows:
    ; Every row is up: the sw_tables, if they still fit.
    jsl f:vblank_line
.a16
    cmp #SW_TABLES_LATEST + 1
    sep #$20
.a8
    bcs later
    lda #0
    sta f:SW_PUT
    jsr sw_tables
    lda #1
    sta f:SW_SHOWN
    rts
later:
    sep #$20
.a8
    rts
.endproc

; The HDMA's three sw_tables for the sw_span —BG2's tilemap and scroll, and the
; objects' mask—, the channels pointed at them and PPU window 1 at the
; windows' edges. In the vblank. A8.
.proc sw_tables
.a8
.i16
    ; The window's scroll: no horizontal one, and the screen's line L shows
    ; the tilemap's line `vofs + 1 + L`, which has to be `L + 8 * SW_OFF`.
    rep #$20
.a16
    lda #0
    sta hdma_ofs_window
    lda f:SW_OFF
    and #$00FF
    asl a
    asl a
    asl a
    dec a
    and #$00FF
    sta hdma_ofs_window + 2
    sep #$20
.a8
    ldx #0                      ; into `hdma_sc` and `SW_MASK`
    ldy #0                      ; into `hdma_ofs`
    lda f:SW_TOP
    asl a
    asl a
    asl a
    sta f:SW_VT                  ; the sw_span's first line
    lda #0
    jsr stretch                 ; the map above
    lda f:SW_BOT
    sec
    sbc f:SW_TOP
    asl a
    asl a
    asl a
    sta f:SW_VT
    lda #1
    jsr stretch                 ; the windows'
    lda f:SW_BOT
    asl a
    asl a
    asl a
    sta f:SW_VT
    lda #<LINES
    sec
    sbc f:SW_VT
    sta f:SW_VT
    lda #0
    jsr stretch                 ; the map below
    lda #0
    sta hdma_sc, x              ; the ends
    sta f:SW_MASK, x
    sta hdma_ofs, y
    ; The channels: 1 and 2 at their sw_tables, as `build_hdma` left them, and
    ; 3 and 6 at this mask; window 1 at the windows' edges.
    lda #<BG2HOFS
    sta BBAD2
    lda #<WOBJSEL
    sta BBAD3
    lda #<W12SEL
    sta BBAD6
    ldx #.loword(SW_MASK)
    stx A1T3L
    stx A1T6L
    lda #^SW_MASK
    sta A1B3
    sta A1B6
    lda f:SW_X0
    sta WH0
    lda f:SW_X1
    sta WH1
    rts

; `SW_VT` lines of kind A —0 the map's, 1 the windows'—, in entries of at
; most 127. A8.
stretch:
    pha
more:
    lda f:SW_VT
    beq done
    cmp #128
    bcc last
    lda #127
last:
    sta hdma_sc, x
    sta f:SW_MASK, x
    sta hdma_ofs, y
    lda f:SW_VT
    sec
    sbc hdma_sc, x
    sta f:SW_VT
    lda 1, s
    beq map_kind
    lda f:MSG_SC
    sta hdma_sc + 1, x
    lda #$02                    ; window 1 on, for what is inside it
    sta f:SW_MASK + 1, x
    rep #$20
.a16
    lda #.loword(hdma_ofs_window)
    bra kind_done
map_kind:
.a8
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1, x
    lda #$00
    sta f:SW_MASK + 1, x
    rep #$20
.a16
    lda #.loword(hdma_ofs_map)
kind_done:
    sta hdma_ofs + 1, y
    sep #$20
.a8
    inx
    inx
    iny
    iny
    iny
    bra more
done:
    pla
    rts
.endproc

; Off the screen: the channels off from the next frame, PPU window 1 edge to
; edge again, and the message's planes back if the windows wrote over them.
; In the vblank; until the planes fit, it waits. A8.
.proc sw_hide
.a8
.i16
    lda #0
    sta f:SW_SHOWN              ; `flush_video` turns the HDMA off
    lda #0
    sta WH0
    lda #$FF
    sta WH1
    lda f:SW_PLANES
    beq done
    jsl f:vblank_line
.a16
    cmp #SW_LINE_LATEST + 1
    sep #$20
.a8
    bcs later
    ; The two planes, 640 words, as `stamp_window_at` writes them.
    jsr sw_tilemap
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda f:MSG_CELLS_PTR + 2
    sta A1B0
    ldx map_ofs
    rep #$20
.a16
    lda f:SW_SC
    sta VMADDL
    lda f:MSG_CELLS_PTR
    sta A1T0L
    lda #TEXT_WINDOW_ROWS * TEXT_WINDOW_COLS * 2 * 2
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    lda #0
    sta f:SW_PLANES
done:
    lda #0
    sta f:SW_HIDE
later:
    rts
.endproc

.popseg

.endif
