.segment "FAR2"
.a8
.i16

; --- where the message window goes --------------------------------------------
;
; `MessageOptions` says where the window is drawn —top, middle or bottom—,
; whether it has its frame and background, and whether it moves out of the
; hero's way: `FAR_MSG_OPTIONS`, which lasts until the next one. This is what
; the console does with it, in two steps:
;
; * `msg_place`, when a window opens —from `msg_start`, with none on screen—
;   decides where this one goes and leaves it in `MSG_PLACE`. It is
;   `Window_Message::InsertNewPage` asking `Game_Message::GetRealPosition`.
; * `msg_hdma_build`, in the vblank in which the window appears, writes the
;   HDMA tables that put it there.
;
; **Moving the window is choosing on which lines BG2 shows its tilemap**, and
; nothing else: the window's tilemap and its tiles stay where they are, and
; so does the composer. The 224 lines go in three stretches —the window's 80
; and the map above and below it—, because a stretch's counter is seven bits
; and the 144 lines above the window at the bottom do not fit in one. With
; three, every position fits in the same tables: see `place_rows`.
;
; The positions are RM2k's on a screen 16 lines shorter: the top one at line
; 0, the bottom one flush with the bottom, as it always was, and the middle
; one centred, at 72. RM2k has them at 0, 80 and 160 of 240.

; The bottom of the hero's cell on screen, from which `GetRealPosition`
; decides that the window would cover him. RM2k's numbers are 112 for the
; top window and the middle one's upper edge, and 160 for the bottom one and
; the middle one's lower edge, on its 240 lines. They are kept **measured
; from the window**, which is what they mean, and not from the top of the
; screen: the top window ends at 80 in both, so its 112 is the same; the
; middle one starts at 72 and not at 80, and the bottom one at 144 and not at
; 160. Over a centred hero —whose bottom is at 120 here and at 128 there— the
; three positions do the same as in RM2k: none moves.
DODGE_TOP        = 80 + 32       ; up to here, the top window moves down
DODGE_MIDDLE_TOP = 72 + 32       ; up to here, the middle one moves down
DODGE_MIDDLE_LOW = 72 + 80       ; from here, the middle one moves up
DODGE_BOTTOM     = 144           ; from here, the bottom one moves up

; Where this window goes: `MSG_PLACE`, from `FAR_MSG_OPTIONS` and the hero.
; Keeps X and Y: `msg_start` hands back its caller's.
.proc msg_place
.a8
.i16
    php
    phx
    phy
    sep #$20
.a8
    ; A new window: its arrow starts over, as `SetPause` starts its count.
    ; The previous one's stopped wherever the key closed it.
    lda #$FF
    sta f:MSG_ARROW_T
    lda f:FAR_LENGTH + FAR_MSG_OPTIONS
    pha                         ; at 1,s until the end
    and #MSG_DODGE
    beq as_asked
    ; `GetScreenY`: the bottom of the hero's cell on screen. A camera panned
    ; away can leave him above the screen; that counts as the top edge, which
    ; is what RM2k's comparisons do with a negative number.
    rep #$20
.a16
    lda hero_y
    sec
    sbc camera_y
    clc
    adc #16
    bpl on_screen
    lda #0
on_screen:
    tay
    sep #$20
.a8
    lda 1, s
    and #MSG_WHERE
    beq asked_top
    cmp #1
    beq asked_middle
    cpy #DODGE_BOTTOM
    bcs top
    bra bottom
asked_top:
    cpy #DODGE_TOP + 1
    bcs top
    bra bottom
asked_middle:
    cpy #DODGE_MIDDLE_TOP + 1
    bcc bottom
    cpy #DODGE_MIDDLE_LOW
    bcs top
    lda #1
    bra store
as_asked:
    lda 1, s
    and #MSG_WHERE
    bra store
top:
    lda #0
    bra store
bottom:
    lda #2
store:
    sta f:MSG_PLACE
    pla
    and #MSG_BARE
    ora f:MSG_PLACE
    sta f:MSG_PLACE
    ply
    plx
    plp
    rtl
.endproc

; The HDMA for the window `MSG_PLACE` says, with its tilemap at `MSG_SC`:
; BG2's tilemap and scroll by stretch, in `hdma_sc` and `hdma_ofs`, and
; which of the ROM's `mask_*` hides the objects under the window. The map's
; stretches carry `VRAM_ABOVE_MAP` and the camera, which `flush_video`
; writes every frame while the window is up; the window's carry its tilemap
; and `MSG_VOFS`, the scroll that makes its first line land on the stretch's
; first line.
;
; Without the background the scroll goes eighty lines further down, to the
; plane without the frame —see `stamp_window`—, and the objects are not
; hidden: what is under the window shows, and so do the characters.
;
; It runs in the vblank in which the window appears, or with the screen off:
; the HDMA reads these tables while it draws. Keeps X and Y.
.proc msg_hdma_build
.a8
.i16
    php
    phx
    phy
    sep #$20
.a8
    ; Whatever the arrow's cells say now is not known: this runs when a
    ; window appears and when a big picture moves its tilemap, which is
    ; stamped again without the arrow. `msg_arrow` writes them next vblank.
    lda #$FF
    sta f:MSG_ARROW_UP
    lda f:MSG_PLACE
    and #MSG_WHERE
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; eight bytes per position
    tax
    sep #$20
.a8
    lda f:place_rows + 0, x
    sta hdma_sc + 0
    sta hdma_ofs + 0
    lda f:place_rows + 1, x
    sta hdma_sc + 2
    sta hdma_ofs + 5
    lda f:place_rows + 2, x
    sta hdma_sc + 4
    sta hdma_ofs + 10
    stz hdma_sc + 6             ; the ends of the tables
    stz hdma_ofs + 15
    ; The objects' mask: the position's, or none without the background.
    ; The channel's address is written here and not in `build_hdma` because
    ; it changes with the window; the HDMA takes it at the top of the next
    ; frame, and this runs in the vblank or with the screen off.
    lda f:MSG_PLACE
    and #MSG_BARE
    beq masked
    ldy #.loword(mask_none)
    bra with_mask
masked:
    rep #$20
.a16
    lda f:place_rows + 6, x     ; the position's, in the same bank
    tay
    sep #$20
.a8
with_mask:
    sty A1T3L
    lda #^mask_none
    sta A1B3
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1
    sta hdma_sc + 3
    sta hdma_sc + 5

    lda f:place_rows + 3, x     ; the window's stretch in `hdma_ofs`
    sta f:MSG_ENTRY
    ; The scroll: line W of the screen shows line `vofs + 1 + W` of the
    ; layer, and the window's tilemap is 256 lines tall, so for its first row
    ; to land on W it is `-1 - W`, plus the frame's 80 lines without the
    ; background. `sbc` with the carry clear subtracts the one.
    lda f:MSG_PLACE
    and #MSG_BARE
    beq framed
    lda #(TEXT_WINDOW_ROWS * 8)
framed:
    clc
    sbc f:place_rows + 4, x
    sta f:MSG_VOFS
    rep #$20
.a16
    lda f:place_rows + 5, x     ; and in `hdma_sc`
    and #$00FF
    tax
    sep #$20
.a8
    lda f:MSG_SC
    sta hdma_sc + 1, x
    ; And the window's own scroll, so that a table built with the screen off
    ; is already whole: `flush_video` writes it again every frame.
    rep #$20
.a16
    lda f:MSG_ENTRY
    and #$00FF
    tax
    sep #$20
.a8
    stz hdma_ofs + 1, x
    stz hdma_ofs + 2, x
    lda f:MSG_VOFS
    sta hdma_ofs + 3, x
    stz hdma_ofs + 4, x
    ply
    plx
    plp
    rtl
.endproc

; Per position, eight bytes: the three stretches' lines from the top, the
; window's entry in `hdma_ofs` —five bytes per stretch—, its first line, its
; entry in `hdma_sc` —two per stretch— and the address of its objects' mask.
PLACE_TOP    = 0
PLACE_MIDDLE = (LINES - TEXT_WINDOW_ROWS * 8) / 2
PLACE_BOTTOM = LINES - TEXT_WINDOW_ROWS * 8
place_rows:
    .byte TEXT_WINDOW_ROWS * 8, 127, PLACE_BOTTOM - 127
    .byte 0, PLACE_TOP, 0
    .word .loword(mask_top)
    .byte PLACE_MIDDLE, TEXT_WINDOW_ROWS * 8, PLACE_MIDDLE
    .byte 5, PLACE_MIDDLE, 2
    .word .loword(mask_middle)
    .byte 127, PLACE_BOTTOM - 127, TEXT_WINDOW_ROWS * 8
    .byte 10, PLACE_BOTTOM, 4
    .word .loword(mask_bottom)
place_rows_end:
.assert place_rows_end - place_rows = 3 * 8, error, "place_rows is not eight bytes per position"
.assert PLACE_MIDDLE <= 127, error, "the middle window's stretches do not fit in seven bits"
.assert PLACE_BOTTOM = WINDOW_LINE, error, "the bottom window is not where it always was"
.assert DODGE_MIDDLE_TOP = PLACE_MIDDLE + 32 && DODGE_MIDDLE_LOW = PLACE_MIDDLE + 80, error, "the middle window moved and its dodge did not"
.assert DODGE_BOTTOM = PLACE_BOTTOM, error, "the bottom window moved and its dodge did not"

; The HDMA tables that hide the objects under the window: window 1 —edge to
; edge— enabled for the objects on the window's lines and on no other, in
; the same three stretches as BG2's. And the one for a window without its
; background, which hides nothing. **Outside bank 0**: HDMA reads from
; wherever `A1B3` says, and they never change. They were `hdma_mask`, in
; bank1.s, while the window was always at the bottom.
mask_top:
    .byte TEXT_WINDOW_ROWS * 8, $02, 127, $00, PLACE_BOTTOM - 127, $00, 0
mask_middle:
    .byte PLACE_MIDDLE, $00, TEXT_WINDOW_ROWS * 8, $02, PLACE_MIDDLE, $00, 0
mask_bottom:
    .byte 127, $00, PLACE_BOTTOM - 127, $00, TEXT_WINDOW_ROWS * 8, $02, 0
mask_none:
    .byte 127, $00, LINES - 127, $00, 0
.assert ^mask_top = ^mask_none && ^mask_bottom = ^mask_none, error, "the masks are not in one bank"
