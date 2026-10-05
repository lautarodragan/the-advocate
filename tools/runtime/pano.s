.segment "FAR2"
.a8
.i16

; --- the panorama -----------------------------------------------------------
;
; RM2k's parallax background, for the maps whose panorama the cartridge shows
; —`[maps] panoramas` of the project file—. The converter decided where it
; goes: in mode 3 it is BG2, where the layer above the hero would be, at 4
; bits; in mode 1 it is BG3, behind everything, at 2 bits, and the map goes
; at 4. See `background::panorama` in Wally and `panorama.rs` in
; rm2k-snes-mapdata, which writes `pano_table`.
;
; **How it moves is `Game_Map::Parallax`**, in RM2k's units:
;
; * one that loops on an axis moves half as much as RM2k's camera, plus what
;   it scrolled on its own: `pan_x` there, in 1/32 px, starts at the camera's
;   position and `ScrollRight` adds what the camera moves; `Update` adds
;   -(1 << speed) every frame;
; * one that does not loop goes from its first pixel to its last as RM2k's
;   camera goes from one edge of the map to the other: `ResetPositionX`, which
;   is `min(w, pano - 320) * camera / w`.
;
; **RM2k's camera is not the console's.** RM2k shows 320x240 and the console
; 256x224, and both follow the hero, so what the console shows is a piece
; of what RM2k shows. The panorama is placed as RM2k places it **behind its
; own camera**, and then shifted by how far the console's camera is from
; that one: that way it sits behind the map exactly where it sits in RM2k,
; and a capture of the original lines up with the console's piece of it.
;
; **The layer is a ring.** A panorama is 640 pixels wide and the tilemap 512,
; so it does not fit whole: the console keeps a running position —`PANO_UX`,
; which wraps where both the 512 of the tilemap and the panorama's width wrap,
; their least common multiple— and writes it to the scroll register as it is.
; The tilemap holds the 64 columns and 32 rows around it, and each frame one
; column and one row at most are written as they come into view, like the
; map's: see `stream_map`. They are built outside the vblank, into
; `PANO_STRIP_*`, and `pano_vblank` uploads them.
;
; Everything here is reached with `jsl` and goes back with `rtl`.

; The state, in far RAM: $7E7E00 to $7E7EDF, allotted on 2026-10-05 between
; the end of `FAR_GROWTH`'s and `CARRY_MAP`. A word per axis goes across
; first and down after, so that one routine does both with Y at 0 or 2.
PANO_ON    = $7E7E00            ; 0, or the mode the map shows its panorama in
PANO_WAS1  = $7E7E01            ; whether the PPU is in mode 1 because of one
PANO_ENT   = $7E7E02            ; the map's record, an offset into pano_table
PANO_AX    = $7E7E04            ; what it scrolled on its own, 1/32 px, a word per axis
PANO_UX    = $7E7E08            ; the running position
PANO_OX    = $7E7E0C            ; where in the panorama the screen starts
PANO_WX    = $7E7E10            ; the running position over 8 the ring was filled for
PANO_COLV  = $7E7E14            ; the VRAM word of the column waiting, 0 none
PANO_ROWV  = $7E7E16            ; and of the row
PANO_T     = $7E7E18            ; four words of scratch
PANO_STRIP_COL = $7E7E20        ; a column of the ring: 32 entries
PANO_STRIP_ROW = $7E7E60        ; a row: 64 entries
PANO_END   = $7E7EE0
.assert PANO_END <= CARRY_MAP, error, "the panorama's state goes into the carried map"
.assert FAR_GROWTH + EXP_K * GROWTH_BYTES <= (PANO_ON & $FFFF), error, "the growth tables go into the panorama's state"
; With the data bank at $7E, as `pano_tick` runs.
P_AX   = PANO_AX & $FFFF
P_UX   = PANO_UX & $FFFF
P_OX   = PANO_OX & $FFFF
P_WX   = PANO_WX & $FFFF
P_T    = PANO_T & $FFFF
P_SCOL = PANO_STRIP_COL & $FFFF
P_SROW = PANO_STRIP_ROW & $FFFF

; The fields of a `pano_table` record: see `panorama.rs`. The ones that go
; by axis are across and down, a word each.
PT_MAP     = 0
PT_MODE    = 2
PT_FLAGS   = 3
PT_AUTO    = 4
PT_SIZE    = 8
PT_NUM     = 12
PT_DEN     = 16
PT_LCM     = 20
PT_CELLS   = 24
PT_TILEMAP = 28
PT_TILES   = 32
PT_BYTES1  = 36
PT_VRAM1   = 38
PT_BYTES2  = 40
PT_VRAM2   = 42
PT_VRAM_MAP = 44
PT_BACKDROP = 46
PT_BG3SC   = 48
PT_BG34NBA = 49
PT_RM_MAX  = 50

; A cartridge that shows no panorama does not get `pano_table` from the
; converter, so that its `.inc` stays the one it always was: it gets an empty
; one here, and every map comes out without a panorama.
.ifndef pano_table
PANO_STRIDE = 64
pano_table:
    .word $FFFF
.endif

; Nothing on reset: bsnes starts the WRAM with garbage.
.proc pano_clear
.a8
.i16
    lda #0
    sta f:PANO_ON
    sta f:PANO_WAS1
    rtl
.endproc

; Looks the map being entered up in `pano_table`, with `map_current` set: its
; record, and what scrolls on its own back to zero, which is what entering a
; map does in RM2k. Before the load: `load_above` and `fill_window` ask.
.proc pano_find
.a8
.i16
    php
    rep #$30
.a16
    ldx #0
other:
    lda f:pano_table + PT_MAP, x
    cmp #$FFFF
    beq none
    cmp map_current
    beq found
    txa
    clc
    adc #PANO_STRIDE
    tax
    bra other
none:
    sep #$20
.a8
    lda #0
    sta f:PANO_ON
    plp
    rtl
.a16
found:
    txa
    sta f:PANO_ENT
    lda #0
    sta f:PANO_AX
    sta f:PANO_AX + 2
    sta f:PANO_COLV
    sta f:PANO_ROWV
    sep #$20
.a8
    lda f:pano_table + PT_MODE, x
    sta f:PANO_ON
    plp
    rtl
.endproc

; The PPU for the map: mode 1 and BG3 if its panorama goes there, and mode 3
; back if the one before was. From `ppu_init` —which every return to the map
; goes through— and at the end of loading one. A map without a panorama after
; another without one writes nothing.
.proc pano_ppu
.a8
.i16
    php
    phb
    pea $0000
    plb
    plb
    lda f:PANO_ON
    cmp #1
    bne not_one
    lda #$01
    sta BGMODE
    lda #$17                    ; BG1, BG2, BG3 and the sprites
    sta TM
    rep #$20
.a16
    lda f:PANO_ENT
    tax
    sep #$20
.a8
    lda f:pano_table + PT_BG3SC, x
    sta BG3SC
    lda f:pano_table + PT_BG34NBA, x
    sta BG34NBA
    lda #1
    sta f:PANO_WAS1
    bra done
not_one:
    lda f:PANO_WAS1
    beq done
    lda #0
    sta f:PANO_WAS1
    lda #$03
    sta BGMODE
    lda #$13
    sta TM
done:
    plb
    plp
    rtl
.endproc

; Mode 3 for a screen that opens over the map: they all draw in mode 3, and
; `back_to_map` puts mode 1 back through `ppu_init`.
.proc pano_mode3
.a8
.i16
    lda f:PANO_ON
    cmp #1
    bne done
    lda #$03
    sta f:BGMODE
done:
    rtl
.endproc

; The panorama's tiles to VRAM, and in mode 1 the backdrop's colour: from
; `load_above`, with the screen off, which is what every load and every
; return from a screen goes through. In mode 3 its palettes came as the layer
; above's; in mode 1, inside the background's.
.proc pano_load
.a8
.i16
    lda f:PANO_ON
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
    lda f:PANO_ENT
    tax
    sep #$20
.a8
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:pano_table + PT_VRAM1, x
    sta VMADDL
    lda f:pano_table + PT_TILES, x
    sta A1T0L
    lda f:pano_table + PT_BYTES1, x
    sta DAS0L
    sep #$20
.a8
    lda f:pano_table + PT_TILES + 2, x
    sta A1B0
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The second stretch, if there is one: a DMA of zero bytes moves 65536.
    rep #$20
.a16
    lda f:pano_table + PT_BYTES2, x
    beq no_second
    sta DAS0L
    lda f:pano_table + PT_VRAM2, x
    sta VMADDL
    lda f:pano_table + PT_TILES, x
    clc
    adc f:pano_table + PT_BYTES1, x
    sta A1T0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
no_second:
    rep #$20
.a16
    lda f:pano_table + PT_BACKDROP, x
    cmp #$FFFF
    beq no_backdrop
    sep #$20
.a8
    stz CGADD
    sta CGDATA
    xba
    sta CGDATA
no_backdrop:
    sep #$20
.a8
    plb
    plp
    rtl
.endproc

; --- where it is -------------------------------------------------------------

; Where in the panorama the console's screen starts on axis Y —0 across, 2
; down—, into `PANO_T`; X is the record's offset plus Y, for its fields. With
; the data bank at $7E and A and the indices at sixteen bits. It is
; `Game_Map::Parallax`: see the top.
.proc pano_where
.a16
.i16
    ; RM2k's camera: the hero nine cells from the left of its screen and
    ; seven from the top —`Game_Player::GetDefaultPanX`, which is half the
    ; screen in cells, rounded up, less one—, plus the pan, and inside the
    ; map.
    lda hero_x, y
    clc
    adc pan_px, y
    cpy #0
    bne down
    sec
    sbc #(9 * 16)
    bra centred
down:
    sec
    sbc #(7 * 16)
centred:
    bpl not_before
    lda #0
not_before:
    cmp f:pano_table + PT_RM_MAX, x
    bcc inside
    lda f:pano_table + PT_RM_MAX, x
inside:
    sta P_T + 2                 ; RM2k's camera
    ; The flags are the high byte of the word at PT_MODE, which is the
    ; record's and not the axis': read with X at the record. The loop bit of
    ; this axis is bit 8 across and bit 9 down.
    phx
    lda f:PANO_ENT
    tax
    lda f:pano_table + PT_MODE, x
    plx
    cpy #0
    beq across
    and #$0200
    bra looped
across:
    and #$0100
looped:
    beq not_looped
    ; Looping: half the camera plus what it scrolled, in 1/32 px.
    lda P_AX, y
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    sta P_T + 4                 ; the whole pixels it scrolled
    lda P_T + 2
    and #1
    asl a
    asl a
    asl a
    asl a                       ; the camera's half pixel, in 1/32
    sta P_T
    lda P_AX, y
    and #31
    clc
    adc P_T
    cmp #32                     ; the carry is the whole pixel the halves add
    lda P_T + 4                 ; `lda` keeps it
    adc #0
    sta P_T
    lda P_T + 2
    lsr a
    clc
    adc P_T
    bra wrap
not_looped:
    lda f:pano_table + PT_DEN, x
    beq still
    ; num * camera / den, exact: a 32-bit product and a long division.
    jsr pano_mul_div
    bra wrap
still:
    lda #0
wrap:
    ; Plus how far the console's camera is from RM2k's, and inside the
    ; panorama: what it adds is less than a width.
    clc
    adc camera_x, y
    sec
    sbc P_T + 2
    sta P_T
other_lap:
    lda P_T
    cmp f:pano_table + PT_SIZE, x
    bcc fits
    sbc f:pano_table + PT_SIZE, x
    sta P_T
    bra other_lap
fits:
    rts
.endproc

; `num * P_T+2 / den` of the record's axis at X, into A: the product in 32
; bits by shifting and adding, and the quotient by shifting and subtracting.
; Neither goes past sixteen bits —the quotient is under `num`, a panorama's
; width— but the product does. Once per frame per axis; keeps X and Y.
.proc pano_mul_div
.a16
.i16
    phy
    phx
    lda f:pano_table + PT_NUM, x
    sta P_T + 4                 ; the multiplier, shifted out from the top
    lda #0
    sta P_T + 6                 ; the product: high word here, low in Y
    tay
    ldx #16
mul:
    tya
    asl a
    tay
    rol P_T + 6
    asl P_T + 4
    bcc no_add
    tya
    clc
    adc P_T + 2
    tay
    lda P_T + 6
    adc #0
    sta P_T + 6
no_add:
    dex
    bne mul
    plx
    ; Over `den`: the low word shifts into the quotient, the remainder
    ; builds up in the high one.
    sty P_T + 4
    ldy #16
div:
    asl P_T + 4
    rol P_T + 6
    lda P_T + 6
    sec
    sbc f:pano_table + PT_DEN, x
    bcc not_yet
    sta P_T + 6
    inc P_T + 4
not_yet:
    dey
    bne div
    lda P_T + 4
    ply
    rts
.endproc

; One frame: the scroll it does on its own, where the screen starts on each
; axis, the running position, and the column and row of the ring that came
; into view, built for `pano_vblank`. After `follow_camera`.
.proc pano_tick
.a8
.i16
    lda f:PANO_ON
    bne on
    rtl
on:
    php
    phb
    lda #$7E
    pha
    plb
    rep #$30
.a16
    ldy #0
axis:
    tya
    clc
    adc f:PANO_ENT
    tax
    ; What it scrolls on its own, wrapped at the panorama's width in 1/32 px.
    lda f:pano_table + PT_AUTO, x
    beq no_auto
    clc
    adc P_AX, y
    sta P_AX, y
    lda f:pano_table + PT_SIZE, x
    asl a
    asl a
    asl a
    asl a
    asl a
    sta P_T + 4
    lda P_AX, y
    bpl not_under
    clc
    adc P_T + 4
    sta P_AX, y
    bra no_auto
not_under:
    cmp P_T + 4
    bcc no_auto
    sbc P_T + 4
    sta P_AX, y
no_auto:
    jsr pano_where
    ; How far it went from last frame, the shorter way round the panorama.
    lda P_T
    sec
    sbc P_OX, y
    sta P_T + 4                 ; the step, signed
    lda P_T
    sta P_OX, y
    lda f:pano_table + PT_SIZE, x
    lsr a
    sta P_T + 6                 ; half a width
    lda P_T + 4
    bmi back
    cmp P_T + 6
    bcc stepped
    sec
    sbc f:pano_table + PT_SIZE, x
    bra stepped
back:
    eor #$FFFF
    inc a
    cmp P_T + 6
    bcc short_back
    lda P_T + 4
    clc
    adc f:pano_table + PT_SIZE, x
    bra stepped
short_back:
    lda P_T + 4
stepped:
    ; And the running position, wrapped where the ring and the panorama
    ; both wrap. It is unsigned and can go past 32767, so the wrap goes by
    ; the carry and not by the sign.
    sta P_T + 4
    lda P_T + 4                 ; the step's sign: `sta` does not set it
    bmi went_back
    lda P_UX, y
    clc
    adc P_T + 4
    cmp f:pano_table + PT_LCM, x
    bcc wrapped
    sbc f:pano_table + PT_LCM, x
    bra wrapped
went_back:
    lda P_UX, y
    clc
    adc P_T + 4                 ; a negative step: the carry is no borrow
    bcs wrapped
    adc f:pano_table + PT_LCM, x
wrapped:
    sta P_UX, y
    iny
    iny
    cpy #4
    bcs both_axes
    jmp axis
both_axes:

    ; The rows first: a column is built for the ring's rows as they are.
    ldy #2
    jsr pano_follow
    bcc no_row
    jsr pano_row
no_row:
    ldy #0
    jsr pano_follow
    bcc no_column
    jsr pano_column
no_column:
    plb
    plp
    rtl
.endproc

; Whether the ring has to take a line on axis Y, and which, in A. The ring
; holds the 64 columns and the 32 rows from `PANO_WX`, which goes after the
; running position over 8 one line a frame at most: what it takes is the line
; on the side it went, the first going back and the last going ahead. If it
; falls further behind it catches up a line a frame, which is what
; `stream_map` does with the map. Carry set if there is a line. Sixteen
; bits, the data bank at $7E.
.proc pano_follow
.a16
.i16
    tya
    clc
    adc f:PANO_ENT
    tax
    lda P_UX, y
    lsr a
    lsr a
    lsr a
    sec
    sbc P_WX, y
    beq none
    ; Wrapped to signed around the ring's period in lines.
    sta P_T
    lda f:pano_table + PT_LCM, x
    lsr a
    lsr a
    lsr a
    sta P_T + 2                 ; the period, in lines
    lsr a
    sta P_T + 4                 ; and half
    lda P_T
    bmi negative
    cmp P_T + 4
    bcc ahead
    bra behind                  ; more than half ahead is behind
negative:
    eor #$FFFF
    inc a
    cmp P_T + 4
    bcc behind
ahead:
    lda P_WX, y
    inc a
    cmp P_T + 2
    bcc ahead_in
    lda #0
ahead_in:
    sta P_WX, y
    ; The ring's last line: 63 columns on, or 31 rows.
    cpy #0
    bne ahead_down
    clc
    adc #63
    bra ahead_wrap
ahead_down:
    clc
    adc #31
ahead_wrap:
    cmp P_T + 2
    bcc ahead_done
    sbc P_T + 2
ahead_done:
    sec
    rts
behind:
    lda P_WX, y
    bne behind_in
    lda P_T + 2
behind_in:
    dec a
    sta P_WX, y
    sec
    rts
none:
    clc
    rts
.endproc

; Line A —in lines of the running position— to the panorama's row or column
; it shows, into A: its remainder over the stretch's cells on axis Y.
.proc pano_content
.a16
.i16
    pha
    tya
    clc
    adc f:PANO_ENT
    tax
    pla
other_lap:
    cmp f:pano_table + PT_CELLS, x
    bcc fits
    sbc f:pano_table + PT_CELLS, x
    bra other_lap
fits:
    rts
.endproc

; `temp` pointed at the panorama's tilemap, and the offset of the cell at
; row `P_T+4`, column `P_T+6` in it, into A: `(row * columns + column) * 2`.
; The hardware multiplies, eight bits by eight: there are not more than 255
; of either.
.proc pano_cell_offset
.a16
.i16
    lda f:PANO_ENT
    tax
    lda f:pano_table + PT_TILEMAP, x
    sta temp
    lda f:pano_table + PT_TILEMAP + 2, x
    sta temp + 2
    sep #$20
.a8
    lda P_T + 4
    sta f:WRMPYA
    lda f:pano_table + PT_CELLS, x
    sta f:WRMPYB                ; eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    clc
    adc P_T + 6
    asl a
    rts
.endproc

; Builds column A of the ring —in lines of the running position—, with the
; rows the ring holds now, into `PANO_STRIP_COL`, and leaves where it goes in
; `PANO_COLV`. Sixteen bits, the data bank at $7E.
.proc pano_column
.a16
.i16
    sta P_T + 2                 ; the column, in lines
    ldy #0
    jsr pano_content
    sta P_T + 6                 ; its column in the panorama
    lda P_WX + 2
    ldy #2
    jsr pano_content
    sta P_T + 4                 ; the ring's first row's row in the panorama
    jsr pano_cell_offset
    tay
    ; Where it lands in VRAM: the tilemap is two 32x32 screens side by side.
    lda f:PANO_ENT
    tax
    lda P_T + 2
    and #63
    cmp #32
    bcc first_screen
    clc
    adc #($400 - 32)
first_screen:
    clc
    adc f:pano_table + PT_VRAM_MAP, x
    sta P_T                     ; VRAM of row 0 of that column
    ; The ring's rows, starting with the first one's.
    lda P_WX + 2
    and #31
    asl a
    tax                         ; where in the strip
    lda #32
    sta P_T + 2                 ; how many
row:
    lda [temp], y
    sta P_SCOL, x
    inx
    inx
    txa
    and #63
    tax
    ; The next row of the panorama, wrapping at its last.
    phx
    lda f:PANO_ENT
    tax
    inc P_T + 4
    lda P_T + 4
    cmp f:pano_table + PT_CELLS + 2, x
    bcc no_wrap
    stz P_T + 4
    lda P_T + 6
    asl a
    tay                         ; back to the first row's
    bra next
no_wrap:
    tya
    clc
    adc f:pano_table + PT_CELLS, x
    adc f:pano_table + PT_CELLS, x
    tay
next:
    plx
    dec P_T + 2
    bne row
    lda P_T
    sta f:PANO_COLV
    rts
.endproc

; Builds row A of the ring, with the columns the ring holds now, into
; `PANO_STRIP_ROW`, and leaves where it goes in `PANO_ROWV`: its first
; screen's row, the second's being $400 further.
.proc pano_row
.a16
.i16
    sta P_T + 2                 ; the row, in lines
    ldy #2
    jsr pano_content
    sta P_T + 4                 ; its row in the panorama
    lda P_WX
    ldy #0
    jsr pano_content
    sta P_T + 6                 ; the ring's first column's column
    jsr pano_cell_offset
    tay
    lda f:PANO_ENT
    tax
    lda P_T + 2
    and #31
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 entries a row
    clc
    adc f:pano_table + PT_VRAM_MAP, x
    sta P_T
    lda P_WX
    and #63
    asl a
    tax
    lda #64
    sta P_T + 2
column:
    lda [temp], y
    sta P_SROW, x
    inx
    inx
    txa
    and #127
    tax
    iny
    iny
    phx
    lda f:PANO_ENT
    tax
    inc P_T + 6
    lda P_T + 6
    cmp f:pano_table + PT_CELLS, x
    bcc no_wrap
    stz P_T + 6
    tya
    sec
    sbc f:pano_table + PT_CELLS, x
    sbc f:pano_table + PT_CELLS, x
    tay                         ; back to the row's first column
no_wrap:
    plx
    dec P_T + 2
    bne column
    lda P_T
    sta f:PANO_ROWV
    rts
.endproc

; The whole ring, with the screen off: from `fill_window`, which every load
; and every jump of the camera goes through. Where the screen starts on each
; axis is the running position, and the ring's 32 rows are built and
; uploaded one by one.
.proc pano_fill
.a8
.i16
    lda f:PANO_ON
    bne on
    rtl
on:
    php
    phb
    lda #$7E
    pha
    plb
    rep #$30
.a16
    ldy #0
axis:
    tya
    clc
    adc f:PANO_ENT
    tax
    jsr pano_where
    lda P_T
    sta P_OX, y
    sta P_UX, y
    lsr a
    lsr a
    lsr a
    sta P_WX, y
    iny
    iny
    cpy #4
    bcc axis
    ; The 32 rows from the window's first, the counter on the stack: P_T is
    ; `pano_row`'s.
    ldy #32
row:
    phy
    lda P_WX + 2
    clc
    adc #32
    sec
    sbc 1, s
    jsr pano_row
    ; Uploaded now: the screen is off.
    sep #$20
.a8
    pea $0000
    plb
    plb
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:PANO_ROWV
    jsr pano_row_dma
    lda #$7E7E
    pha
    plb
    plb
    lda #0
    sta f:PANO_ROWV
    ply
    dey
    bne row
    plb
    plp
    rtl
.endproc

; The two halves of the row strip, to the VRAM word in A and $400 further.
; Data bank 0, A sixteen bits, VMAIN already advancing one word.
.proc pano_row_dma
.a16
.i16
    pha
    sta VMADDL
    lda #.loword(PANO_STRIP_ROW)
    sta A1T0L
    lda #64
    sta DAS0L
    sep #$20
.a8
    lda #^PANO_STRIP_ROW
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    pla
    clc
    adc #$400
    sta VMADDL
    lda #.loword(PANO_STRIP_ROW) + 64
    sta A1T0L
    lda #64
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    rts
.endproc

; --- in the vblank -----------------------------------------------------------

; The scroll, and the column and row waiting: from `flush_video`, after the
; map's strips. In mode 3 the scroll is BG2's, written again over the camera
; that `flush_video` just put there; in mode 1, BG3's.
.proc pano_vblank
.a8
.i16
    lda f:PANO_ON
    bne on
    rtl
on:
    php
    cmp #1
    beq bg3
    lda f:PANO_UX
    sta BG2HOFS
    lda f:PANO_UX + 1
    sta BG2HOFS
    rep #$20
.a16
    lda f:PANO_UX + 2
    dec a                       ; the PPU shows line vofs + 1
    sep #$20
.a8
    sta BG2VOFS
    xba
    sta BG2VOFS
    bra strips
bg3:
    lda f:PANO_UX
    sta BG3HOFS
    lda f:PANO_UX + 1
    sta BG3HOFS
    rep #$20
.a16
    lda f:PANO_UX + 2
    dec a
    sep #$20
.a8
    sta BG3VOFS
    xba
    sta BG3VOFS
strips:
    rep #$20
.a16
    lda f:PANO_COLV
    beq no_column
    sep #$20
.a8
    lda #$81                    ; advance 32 words: down the column
    sta VMAIN
    rep #$20
.a16
    lda f:PANO_COLV
    sta VMADDL
    lda #.loword(PANO_STRIP_COL)
    sta A1T0L
    lda #64
    sta DAS0L
    sep #$20
.a8
    lda #^PANO_STRIP_COL
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda #0
    sta f:PANO_COLV
no_column:
    lda f:PANO_ROWV
    beq no_row
    sep #$20
.a8
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:PANO_ROWV
    jsr pano_row_dma
    lda #0
    sta f:PANO_ROWV
no_row:
    plp
    rtl
.endproc

; In mode 3 the panorama is BG2, and the window's HDMA writes BG2's scroll
; on every stretch: the map's carry the panorama's and not the camera. From
; `flush_video`, after it wrote the camera there and before the window's own.
.proc pano_hdma
.a8
.i16
    lda f:PANO_ON
    cmp #3
    bne done
    lda f:PANO_UX
    sta hdma_ofs + 1
    sta hdma_ofs + 6
    sta hdma_ofs + 11
    lda f:PANO_UX + 1
    sta hdma_ofs + 2
    sta hdma_ofs + 7
    sta hdma_ofs + 12
    rep #$20
.a16
    lda f:PANO_UX + 2
    dec a
    sep #$20
.a8
    sta hdma_ofs + 3
    sta hdma_ofs + 8
    sta hdma_ofs + 13
    xba
    sta hdma_ofs + 4
    sta hdma_ofs + 9
    sta hdma_ofs + 14
done:
    rtl
.endproc
