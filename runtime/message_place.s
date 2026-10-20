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
; so does the composer. The 224 lines go in stretches —the window's and the
; map's above, below and, without the background, between its lines—, and
; the ones of more than 127 lines in two entries, because an entry's counter
; is seven bits: see `msg_hdma_build`.
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
.ifdef wrap_maps
    jsl f:wrap_fold_y           ; on the lap the screen is on: see wrap.s
.endif
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

; Everything from here to `place_rows` —building the HDMA, the window's
; bands and the trade over a painting— lives in FAR3, bank $C1, and not in
; FAR2 with `msg_place`: on a painted map's cartridge bank $C0 had no room
; for the bands, Sunset over Imdahl's went 110 bytes over. It is all
; reached with `jsl`, and the tables it reads go with `f:`.
.pushseg
.segment "FAR3"
.a8
.i16

; The HDMA for the window `MSG_PLACE` says, with its tilemap at `MSG_SC`:
; BG2's tilemap and scroll by stretch, in `hdma_sc` and `hdma_ofs`, and
; which of the ROM's `mask_*` hides the objects under the window. The map's
; stretches carry `VRAM_ABOVE_MAP` and point at `hdma_ofs_map`, the camera,
; which `flush_video` writes every frame while the window is up; the
; window's carry its tilemap and point at `hdma_ofs_window`, the scroll
; that makes its first line land where the window starts, `MSG_VOFS`.
;
; **The window's lines are not always its eighty.** It is six bands
; —`window_bands`: the frame's top row, the four lines of text and the
; bottom row—, and only the bands the window draws on take BG2 from the
; map: all six with the frame, and without it the ones in `msg_bands`. On
; the others BG2 is the map's layer above, and its roofs and treetops show
; between the lines of a message without a background. That is why the
; stretches are built here, band by band, and not taken from a table per
; position.
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
    ; And whether it goes in them or in objects, before `msg_bands` asks.
    jsr arrow_obj_choose
    lda f:MSG_PLACE
    and #MSG_WHERE
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; four bytes per position
    tax
    sep #$20
.a8
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
    lda f:place_rows + 2, x     ; the position's, in the same bank
    tay
    sep #$20
.a8
with_mask:
    sty A1T3L
    sty A1T6L                   ; BG1's, the same: see `pano_ppu`
    lda #^mask_none
    sta A1B3
    sta A1B6

    ; The scroll: line W of the screen shows line `vofs + 1 + W` of the
    ; layer, and the window's tilemap is 256 lines tall, so for its first row
    ; to land on W it is `-1 - W`, plus the frame's 80 lines without the
    ; background. `sbc` with the carry clear subtracts the one. It is the
    ; same on every band of the window: they are all the same picture, cut.
    lda f:MSG_PLACE
    and #MSG_BARE
    beq framed
    lda #(TEXT_WINDOW_ROWS * 8)
framed:
    clc
    sbc f:place_rows + 0, x
    sta f:MSG_VOFS
    rep #$20
.a16
    lda #0
    sta hdma_ofs_window         ; no horizontal scroll
    sep #$20
.a8
    lda f:MSG_VOFS
    sta hdma_ofs_window + 2
    stz hdma_ofs_window + 3

    ; The stretches, top to bottom: the map down to the window, the bands
    ; one by one —each the window's or the map's—, and the map below it.
    ; A stretch runs while the kind does not change, and `run_emit` cuts it
    ; in entries of seven bits.
    lda f:place_rows + 0, x     ; the map above the window
    sta f:MSG_RUN_LINES
    pha                         ; at 1,s: where the window starts
    lda f:MSG_PLACE
    and #MSG_BARE
    beq every_band
    jsl f:msg_bands
    bra with_bands
every_band:
    lda #WINDOW_BANDS_ALL
with_bands:
    sta f:MSG_RUN_BANDS
    lda #0
    sta f:MSG_RUN_KIND          ; the map's
    sta f:MSG_RUN_BAND
    ldx #0                      ; where in `hdma_sc`
    ldy #0                      ; and in `hdma_ofs`
band:
    lda f:MSG_RUN_BANDS
    lsr a                       ; this band's bit, into the carry
    sta f:MSG_RUN_BANDS
    lda #0
    rol a                       ; 1 if it is the window's
    cmp f:MSG_RUN_KIND
    beq same_kind
    ; The kind changes: the stretch so far goes out, and a new one starts.
    pha
    lda f:MSG_RUN_LINES
    jsr run_emit
    pla
    sta f:MSG_RUN_KIND
    lda #0
    sta f:MSG_RUN_LINES
same_kind:
    phx
    lda f:MSG_RUN_BAND
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:window_bands, x
    plx
    clc
    adc f:MSG_RUN_LINES
    sta f:MSG_RUN_LINES
    lda f:MSG_RUN_BAND
    inc a
    sta f:MSG_RUN_BAND
    cmp #WINDOW_BANDS
    bne band
    ; And the map below the window, which goes on the last band's stretch
    ; if that one is the map's.
    lda f:MSG_RUN_KIND
    beq below
    lda f:MSG_RUN_LINES
    jsr run_emit
    lda #0
    sta f:MSG_RUN_KIND
    sta f:MSG_RUN_LINES
below:
    pla                         ; where the window starts
    clc
    adc #(TEXT_WINDOW_ROWS * 8)
    sta f:MSG_RUN_BAND          ; where it ends: the band count is done
    lda #<LINES
    sec
    sbc f:MSG_RUN_BAND
    clc
    adc f:MSG_RUN_LINES
    jsr run_emit
    lda #0
    sta hdma_sc, x              ; the ends of the tables
    sta hdma_ofs, y

    ; Channels 2, 3 and 6 to BG2's scroll and the two masks, as always,
    ; unless the window goes over a painting: see `msg_swap_build`. Here and
    ; not only in `build_hdma` because a window over a painting points them
    ; elsewhere, and the next one has to bring them back.
    lda #<BG2HOFS
    sta BBAD2
    lda #<WOBJSEL
    sta BBAD3
    lda #<W12SEL
    sta BBAD6
    lda #0
    sta f:MSG_SWAP
.ifdef paint_table
    lda msg_open                ; a map's load builds the tables with none up
    beq no_swap
    lda f:MSG_PLACE
    and #MSG_BARE
    beq no_swap
    lda f:PAINT_ON
    beq no_swap
    lda f:BIG_FLAGS
    lsr a                       ; a big picture is BG1: no painting to trade
    bcs no_swap
    jsr msg_swap_build
no_swap:
.endif
    ply
    plx
    plp
    rtl
.endproc

; A stretch of A lines, from 0 to `LINES`, of the kind `MSG_RUN_KIND` says
; —0 the map's, 1 the window's—, into `hdma_sc` at X and `hdma_ofs` at Y,
; which it leaves past it. An entry's count is seven bits, so a stretch of
; more than 127 lines goes in two; one of none, in none.
.proc run_emit
.a8
.i16
more:
    cmp #0                      ; for the flags: the callers come with any
    beq done
    cmp #128
    bcc last
    sbc #127                    ; the carry is set: what is left after one
    pha
    lda #127
    jsr entry
    pla
    bra more
last:
    jsr entry
done:
    rts

entry:
    sta hdma_sc, x
    sta hdma_ofs, y
    lda f:MSG_RUN_KIND
    beq of_the_map
    lda f:MSG_SC
    sta hdma_sc + 1, x
    rep #$20
.a16
    lda #.loword(hdma_ofs_window)
    bra with_scroll
of_the_map:
.a8
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1, x
    rep #$20
.a16
    lda #.loword(hdma_ofs_map)
with_scroll:
    sta hdma_ofs + 1, y         ; `hdma_ofs` is indirect: see `build_hdma`
    sep #$20
.a8
    inx
    inx
    iny
    iny
    iny
    rts
.endproc

; The window's six bands, top to bottom, in lines: the frame's top row, the
; four lines of text and the frame's bottom row, where the arrow is. A line
; of text is the composer's: two cell rows, which is what it primes and
; uploads per line —the glyph starts two lines in, `TEXT_OFS_Y`, and with
; its shadow ends on the fifteenth—, so a band holds all of its line and
; nothing of the next.
WINDOW_BANDS = 6
WINDOW_BANDS_ALL = %111111
WINDOW_BAND_ARROW = %100000     ; the bottom row's bit
WINDOW_BAND_LINES = %011110     ; the four lines', the first in bit 1
window_bands:
    .byte WINDOW_BORDER, 16, 16, 16, 16, WINDOW_BORDER
window_bands_end:
.assert window_bands_end - window_bands = WINDOW_BANDS, error, "window_bands is not six bands"
.assert 2 * WINDOW_BORDER + WINDOW_TEXT_LINES * 16 = TEXT_WINDOW_ROWS * 8, error, "the window's bands do not add up to its height"
.assert TEXT_OFS_Y + 12 + 1 <= 16, error, "a glyph with its shadow does not fit in its line's band"

; Which bands a window without its background draws on, in A: those of its
; lines with text, which `msg_line_rows` left in `MSG_ROWS` as the composer
; went through them, and the bottom row if the page can show the arrow in
; the cells. The top row, never: nothing is drawn there without the frame.
.proc msg_bands
.a8
.i16
    lda f:MSG_ROWS
    and #WINDOW_BAND_LINES
    pha
    ; The arrow is up when `msg_arrow` says, and that is decided frame by
    ; frame: what is known here is whether it can be, and with a choice or
    ; the digits it cannot, nor with a `\^` closing the page —unless its
    ; typing stops at a `\!`, which waits for the key with the arrow: the
    ; tables are built again then, see `msg_pace_vblank`—. RM2k draws it
    ; with the window's opacity at zero too: `Window::Draw` blits it apart.
    ; Unless it is drawn as objects, in a map with room for them: then the
    ; bottom row is the map's too. See `arrow_obj_choose`.
    lda f:MSG_ARROW_OBJ + 1
    bmi no_arrow
    lda pick_active
    bne no_arrow
    lda f:FAR_MSG_AUTO
    beq arrow
    lda f:MSG_KEY
    beq no_arrow
arrow:
    pla
    ora #WINDOW_BAND_ARROW
    pha
no_arrow:
    pla
    rtl
.endproc

; The start of each line, from `message_tick` with its length read —zero
; for a line the box does not carry—: whether the window draws on its band,
; in `MSG_ROWS`. It is decided here and not by the converter because a line
; with a `\N` or a `\V` has a length anyway. A box being typed reaches its
; lines with the window already up, so the tables are built again when a
; line's band changes: see `msg_pace_vblank` in message_pace.s.
;
; A line draws if it has letters; on a choice, if it is an option, even an
; empty one, which the bar goes over and the window must not jump when it
; moves; and with a face, all four, because the face covers lines 16 to 63
; of the window. Only this line's bit is written: the digits of an
; `InputNumber` compose from a line down, and the ones above keep theirs.
.proc msg_line_rows
.a8
.i16
    phx
    lda f:msg_line
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:MSG_ROWS
    and f:line_band_off, x
    sta f:MSG_ROWS
    lda f:MSG_FACE_DRAW
    bne draws
    lda f:msg_length
    bne draws
    lda pick_active
    cmp #PICK_CHOICE
    bne done
    lda f:msg_lines
    and #HEADER_LINES
    cmp f:msg_line
    beq done                    ; past the options
    bcc done
draws:
    lda f:MSG_ROWS
    ora f:line_band, x
    sta f:MSG_ROWS
done:
    plx
    rtl
.endproc
line_band:
    .byte %000010, %000100, %001000, %010000
line_band_off:
    .byte $FF ^ %000010, $FF ^ %000100, $FF ^ %001000, $FF ^ %010000
.assert WINDOW_TEXT_LINES = 4, error, "line_band has one bit per line of four"

; What `msg_line_rows` and `msg_hdma_build` leave and use. Far RAM: the
; first is written while composing and read in the vblank, and the rest is
; the build's scratch.
.pushseg
.segment "FARBSS"
MSG_ROWS:      .res 1           ; the bands of the lines that draw, as `line_band`
MSG_RUN_BANDS: .res 1           ; the bands still to go, from bit 0
MSG_RUN_BAND:  .res 1           ; which band
MSG_RUN_KIND:  .res 1           ; the stretch's: 0 the map, 1 the window
MSG_RUN_LINES: .res 1           ; how many lines it has so far
.popseg

; What `msg_swap_build` leaves for the HDMA and for `flush_video`. Far RAM:
; HDMA reads any bank, and channels 3 and 6 take it from `A1B3` and `A1B6`.
.pushseg
.segment "FARBSS"
MSG_SWAP:     .res 1            ; 1 while the window on screen trades BG1 and BG2
MSG_SWAP_SC1: .res HDMA_ENTRIES * 2 + 1   ; BG1SC by stretch, as `hdma_sc` is BG2SC
MSG_SWAP_NBA: .res HDMA_ENTRIES * 2 + 1   ; and BG12NBA
.popseg

.ifdef paint_table
; A window without its background over a painted map: on its lines BG1 and
; BG2 trade places, so the letters are BG1 and the painting BG2.
;
; The painting is BG1, and its cells in front of the hero —the pictures
; drawn into the map: roofs, lights, fogs— are priority 1. The window is
; BG2, and in mode 1 BG2 never goes in front of BG1 priority 1, whatever its
; own priority. With the frame that is solved by hiding BG1 on the window's
; lines —channel 6, see `pano_ppu`—, but without it what is under the window
; has to be seen, and so the mask was `mask_none` and the cells in front
; covered the letters: on Sunset over Imdahl's GateStreet, whose fog is
; drawn into the map, the scene's messages came out with a glyph or two, on
; 2026-10-16. RM2k draws the text above everything.
;
; So on the window's lines BG1 shows the window's tilemap, with BG2's tile
; base and the window's scroll, and BG2 shows the painting, with BG1's tile
; base and the camera's scroll. In mode 1 both are 4bpp, so trading them is
; only tilemap, base and scroll. The letters are priority 1 —the window's
; cells carry the layer above's—, in front of the painting's cells in front
; of the hero; and those, now BG2 priority 1, keep their place against the
; objects, between priority 3 and 2 as BG1 priority 1 was. What those lines
; lose is the layer above —BG2's on a painted map—, which a window without
; its background already hid: there BG2 was the window.
;
; The channels are the two masks', which a window without its background
; does not use: 6 writes BG1SC and 3 BG12NBA, from `MSG_SWAP_SC1` and
; `MSG_SWAP_NBA` in the same stretches as `hdma_sc`; 2 writes BG1's scroll
; instead of BG2's, from the same `hdma_ofs` —the camera on the map's
; stretches, the window's on its own—; and BG2's scroll is the camera on
; every line, which `flush_video` writes anyway. When the window closes,
; `flush_video` puts BG1SC and BG12NBA back: the HDMA leaves them as its last
; line wrote them.
.proc msg_swap_build
.a8
.i16
    lda #1
    sta f:MSG_SWAP
    ; The map's BG1SC and BG12NBA, at 1,s and 2,s.
    ldx map_ofs
    lda f:map_table + M_BG12NBA_VALUE, x
    pha
    lda f:map_table + M_VRAM_MAP + 1, x
    ora #MAP_LAYOUT
    pha
    ; Every stretch of `hdma_sc`, with its lines: the map's keep the map's
    ; values, and the window's are traded —the window to BG1 and the
    ; painting to BG2—. A window's stretch is the one with `MSG_SC`, which
    ; no stretch of the map has: the window's tilemap is its own.
    ldx #0
stretch:
    lda hdma_sc, x
    sta f:MSG_SWAP_SC1, x
    sta f:MSG_SWAP_NBA, x
    beq done                    ; the end's zero, copied too
    lda hdma_sc + 1, x
    cmp f:MSG_SC
    beq window
    lda 1, s
    sta f:MSG_SWAP_SC1 + 1, x
    lda 2, s
    sta f:MSG_SWAP_NBA + 1, x
    bra next
window:
    sta f:MSG_SWAP_SC1 + 1, x   ; the window, to BG1
    lda 1, s
    sta hdma_sc + 1, x          ; the painting, to BG2
    lda 2, s
    asl a                       ; the two nibbles traded: BG12NBA has BG1's
    adc #$80                    ; base in the low one and BG2's in the high
    rol a
    asl a
    adc #$80
    rol a
    sta f:MSG_SWAP_NBA + 1, x
next:
    inx
    inx
    bra stretch
done:
    pla
    pla
    ; And the channels to their registers and tables.
    lda #<BG1HOFS
    sta BBAD2
    lda #<BG12NBA
    sta BBAD3
    lda #<BG1SC
    sta BBAD6
    ldx #.loword(MSG_SWAP_NBA)
    stx A1T3L
    ldx #.loword(MSG_SWAP_SC1)
    stx A1T6L
    lda #^MSG_SWAP_SC1
    sta A1B3
    sta A1B6
    rts
.endproc
.endif
.popseg

; Per position, four bytes: the window's first line on screen, a byte of
; padding, and the address of its objects' mask.
PLACE_TOP    = 0
PLACE_MIDDLE = (LINES - TEXT_WINDOW_ROWS * 8) / 2
PLACE_BOTTOM = LINES - TEXT_WINDOW_ROWS * 8
place_rows:
    .byte PLACE_TOP, 0
    .word .loword(mask_top)
    .byte PLACE_MIDDLE, 0
    .word .loword(mask_middle)
    .byte PLACE_BOTTOM, 0
    .word .loword(mask_bottom)
place_rows_end:
.assert place_rows_end - place_rows = 3 * 4, error, "place_rows is not four bytes per position"
.assert PLACE_MIDDLE <= 127, error, "the middle window's masks do not fit in seven bits"
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
