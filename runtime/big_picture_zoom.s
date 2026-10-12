.segment "FAR"
.a8
.i16

; --- a big picture's zoom: mode 7 ----------------------------------------------
;
; A big picture that a `MovePicture` zooms —the photos of maps 212 to 216,
; shrinking to nothing— is carried with a **mode 7 texture** too: its own
; pixels, the same colour-memory entries as its layer, in 255 tiles chosen
; by vector quantisation (`mode7` in rm2k-snes-images). Still, it is shown
; in mode 1 at full resolution like any big one; when the zoom starts the
; console switches to mode 7 and zooms the texture with the matrix. See
; `tasks/picture-zoom-in-mode-7.md`, and the pilot's,
; `tasks/mode-7-pilot-for-the-zoom-of-the-diff-photos.md`.
;
; **Mode 7 owns VRAM's lower half and cannot be moved**: its 128x128 map in
; the low bytes of words $0000 to $3FFF and its 256 tiles in the high ones.
; So the still picture goes in the upper half —its tiles from $4000,
; `BIG_HYBRID_TILES`, its tilemap a screen of 32x32 at $7C00— and the
; texture goes up into the lower one **a piece per vblank** while it is
; still, which is what makes the switch cost no frame. A zoom that comes
; before the texture is up whole sends the rest with the screen off.
;
; **That takes the message window while it is still**: its tiles and its
; tilemap were in the upper half. No scene of A Blurred Line shows a message
; over a photo before its zoom. Once in mode 7 the upper half is free
; again, and the window goes back there a piece per vblank —`BIG_PIECES`—:
; a zoom that ends at nothing leaves mode 1 with the layer off —BIG_M7_GONE—,
; and the messages that follow over the black, the widow's in map 212, see
; the window. One that ends at another size stays in mode 7, where there is
; no second layer: a message there is not seen.
;
; The palette does not change: the texture draws with the layer's entries,
; so the tone, the transparency and the saturation go on as in mode 1. The
; sprites are off, as with any big picture. The wave is not done in mode
; 7: its HDMA writes BG1's scroll, which there is the plane's.
;
; The size follows RM2k's `MovePicture`, a straight line from the size it
; had to the one it goes to in its frames: A and D of the matrix, how many
; texels a pixel of the screen is, are `256 × 100 / size` in 8.8, computed
; every frame from the ramp's step —`big_m7_matrix`—. The point that stays
; is the picture's centre where it was drawn, or the screen's for a cropped
; one: see `center` in rm2k-snes-images.

; Where the still picture with a texture lives, in VRAM words: its tiles
; from BIG_HYBRID_TILES, at most `M7_LAYER_TILES` of them, and its tilemap,
; one screen —BG1SC's size bits at zero—. `M7_*` in rm2k-snes-convert's
; pictures.rs say the same.
BIG_HYBRID_TILES = $4000
BIG_HYBRID_MAP   = $7C00
.assert BIG_HYBRID_TILES + 960 * 16 = BIG_HYBRID_MAP, error, "the hybrid layer's tiles and tilemap are not M7_LAYER_TILES apart"
; Mode 7's plane, in words: a byte of map and a byte of tile in each.
BIG_M7_WORDS = $4000
; How much goes up per vblank. With the OAM and the palette, the vblank
; ends well before line 261: see `big_vblank`.
BIG_M7_CHUNK = 3072
; M7SEL: past the 1024 pixels of the plane, nothing; no flips.
BIG_M7SEL = $80
; BIG_M7_A when the picture is too small for the matrix, and not drawn.
BIG_M7_HIDDEN = $FFFF

; What the vblank shows, BIG_M7_SHOW's low bits; and its bit 7, that the
; upper half is no longer the still picture's: the window went back there.
BIG_M7_STILL = 0
BIG_M7_ZOOM  = 1
BIG_M7_GONE  = 2
BIG_M7_SPENT = $80

; The pieces that go up, in order, BIG_M7_PIECE: the texture's three, and
; then, once mode 7 is on screen, what the window needs back.
BIG_PIECE_ROWS   = 0            ; the map's rows, low bytes
BIG_PIECE_ZEROS  = 1            ; the rest of the map, the blank tile
BIG_PIECE_TILES  = 2            ; the tiles, high bytes
BIG_PIECE_WINDOW = 3            ; the window's tiles
BIG_PIECE_STAMP  = 4            ; its tilemap at BIG_VRAM_WINDOW
BIG_PIECE_ABOVE  = 5            ; the layer above's tilemap, empty
BIG_PIECE_BLANK  = 6            ; and its tile 0, blank
BIG_PIECES       = 7

.assert BIG_M7_END <= ANIM_DRAWINGS_END && BIG_M7_SHOW >= BIG_WAVE_B + BIG_WAVE_BYTES, error, "the zoom's bytes are not the picture's"

; The entry's six last fields: see `big_pictures_section` in
; rm2k-snes-mapdata.
BE_M7_TILES     = 18            ; long: the texture's tiles, raw
BE_M7_ROWS      = 21            ; long: its map's rows, raw
BE_M7_BYTES     = 24            ; word: its tiles' bytes, 0 if it has none
BE_M7_ROW_BYTES = 26            ; word: its rows'
BE_M7_X         = 28            ; word: the point that stays, in the texture
BE_M7_Y         = 30
.assert BE_M7_Y + 2 = BIG_ENTRY, error, "big_table's entry is not what the zoom reads"

; Picture BIG_IMG, which has a texture, into the layer with the screen off:
; `big_load`'s, in the upper half. Enters with X on its entry.
.proc big_load_hybrid
.a8
.i16
    phx
    rep #$20
.a16
    lda f:big_table + BE_BYTES, x
    sta DAS0L
    lda f:big_table + BE_TILES, x
    sta A1T0L
    lda #BIG_HYBRID_TILES
    sta VMADDL
    sep #$20
.a8
    lda f:big_table + BE_TILES + 2, x
    sta A1B0
    jsr big_dma_vram
    ; Its tilemap's left screen, which is the picture: the right one is
    ; what a wave brings in past the sides, and there is no room for it.
    plx
    phx
    lda f:big_table + BE_MAP + 2, x
    pha
    rep #$20
.a16
    lda f:big_table + BE_MAP, x
    tax
    sep #$20
.a8
    pla
    jsr big_unpack
    rep #$20
.a16
    lda #$0800                  ; one screen of 32x32
    sta DAS0L
    lda #BIG_HYBRID_MAP
    sta VMADDL
    sep #$20
.a8
    jsr big_to_vram
    ; The window's tilemap goes where `big_load` puts it, but later: see
    ; BIG_PIECE_STAMP. The HDMA's table already points there.
    lda #>BIG_VRAM_WINDOW
    sta f:MSG_SC
    jsl msg_hdma_build          ; the window's stretch, pointing there
    lda #$01
    sta BGMODE
    ldx map_ofs
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$F0
    ora #BIG_HYBRID_TILES >> 12
    sta BG12NBA
    lda #>BIG_HYBRID_MAP
    sta BG1SC
    lda #$01                    ; BG1 alone: BG2's tiles are under the picture
    sta TM
    plx
    ; Still, at its size, with the texture to go up from the first piece.
    lda #BIG_M7_STILL
    sta f:BIG_M7_SHOW
    lda #0
    sta f:BIG_M7_PIECE
    sta f:BIG_M7_DONE
    sta f:BIG_M7_DONE + 1
    lda #100
    sta f:BIG_MAG
    rep #$20
.a16
    lda #$0100
    sta f:BIG_M7_A
    sep #$20
.a8
    lda f:BIG_FLAGS
    and #$FF ^ (BIG_M7 | BIG_ZOOMING)
    ora #BIG_ON | BIG_TEXTURE
    sta f:BIG_FLAGS
    rts
.endproc

; Before another picture goes into the layer, with the screen off: if the
; one up had a texture, what it took from the window goes back now —the
; next one may be a picture without one, which counts on the window being
; where the map put it—, and its flags go.
.proc big_m7_leave
.a8
.i16
    lda f:BIG_FLAGS
    and #BIG_TEXTURE
    beq done
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECE_WINDOW
    bcs going
    lda #BIG_PIECE_WINDOW       ; its own texture is no longer wanted
    sta f:BIG_M7_PIECE
    lda #0
    sta f:BIG_M7_DONE
    sta f:BIG_M7_DONE + 1
going:
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECES
    bcs gone
    jsr big_m7_piece
    bra going
gone:
    lda f:BIG_FLAGS
    and #$FF ^ (BIG_TEXTURE | BIG_M7 | BIG_ZOOMING)
    sta f:BIG_FLAGS
done:
    rts
.endproc

; `OP_BIG_SHOW` of the picture that is already up: carry set if it has to
; be loaded again. One with a texture goes back to still at its size; if the
; window already took the upper half, the picture is no longer there.
.proc big_m7_again
.a8
.i16
    lda f:BIG_FLAGS
    and #BIG_TEXTURE
    beq keep
    lda f:BIG_M7_SHOW
    bmi load                    ; BIG_M7_SPENT
    lda #BIG_M7_STILL
    sta f:BIG_M7_SHOW
    lda #100
    sta f:BIG_MAG
    lda f:BIG_FLAGS
    and #$FF ^ BIG_ZOOMING
    sta f:BIG_FLAGS
keep:
    clc
    rts
load:
    sec
    rts
.endproc

; `OP_BIG_ZOOM`: `OP_BIG_MOVE`'s operands, and the size it goes to. Enters
; with Y on the operands and leaves it past them. On a picture without a
; texture —the number can show another one by then— it is the move alone.
.proc big_zoom
.a8
.i16
    phy
    rep #$20
.a16
    tya
    clc
    adc #9                      ; past OP_BIG_MOVE's
    tay
    sep #$20
.a8
    lda [code_ptr], y
    sta f:BIG_MAG_TO
    ply
    jsl f:big_move + FAST
    iny                         ; the size
    lda f:BIG_FLAGS
    and #BIG_TEXTURE            ; and BIG_ON: `big_load` clears it otherwise
    beq done
    phy
    jsr big_zoom_start
    ply
done:
    rtl
.endproc

; The size's ramp, after `big_move` started the rest: from the size it has
; now to BIG_MAG_TO, in the same frames, or at once.
.proc big_zoom_start
.a8
.i16
    lda f:BIG_MAG
    sta f:BIG_MAG_FROM
    ; Still and staying the size it is: a move that only tones or scrolls,
    ; which mode 1 does at full resolution.
    lda f:BIG_M7_SHOW
    and #$7F
    bne zooms                   ; not still any more
    lda f:BIG_MAG
    cmp f:BIG_MAG_TO
    bne zooms
    rts
zooms:
    jsr big_m7_texture_now
    lda f:PIC_RAMP
    cmp #PIC_BIG
    bne at_once                 ; no frames: `big_move` arrived already
    lda f:BIG_FLAGS
    ora #BIG_ZOOMING
    sta f:BIG_FLAGS
    lda #BIG_M7_ZOOM
    jsr big_m7_show_as
    jmp big_m7_matrix           ; PIC_STEP at 0: the size it had
at_once:
    lda f:BIG_FLAGS
    and #$FF ^ BIG_ZOOMING
    sta f:BIG_FLAGS
    jmp big_m7_arrive
.endproc

; The zoom's ramp over: the size it went to, in mode 7, or mode 1 with the
; layer off if it went to nothing.
.proc big_m7_arrive
.a8
.i16
    lda f:BIG_MAG_TO
    sta f:BIG_MAG
    sta f:BIG_MAG_FROM
    beq gone
    lda #BIG_M7_ZOOM
    jsr big_m7_show_as
    jmp big_m7_matrix           ; FROM and TO equal: any step is the size
gone:
    lda #BIG_M7_GONE
    ; and on into `big_m7_show_as`
.endproc
; BIG_M7_SHOW's mode at A8, keeping BIG_M7_SPENT.
.proc big_m7_show_as
.a8
.i16
    pha
    lda f:BIG_M7_SHOW
    and #BIG_M7_SPENT
    ora 1, s
    sta f:BIG_M7_SHOW
    pla
    rts
.endproc

; What is left of the texture, now and with the screen off: a zoom that
; comes before the vblanks sent it all. The screen comes back on in the
; next vblank, from `brightness`, as after `big_load`.
.proc big_m7_texture_now
.a8
.i16
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECE_WINDOW
    bcs up
    lda #$80
    sta INIDISP
each:
    jsr big_m7_piece
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECE_WINDOW
    bcc each
up:
    rts
.endproc

; One frame of the ramp, from `big_step`, with PIC_STEP already moved on:
; the size it is at, which another move starts from, and the matrix.
.proc big_m7_step
.a8
.i16
    lda f:BIG_FLAGS
    and #BIG_ZOOMING
    beq done
    lda f:BIG_MAG_TO
    cmp f:BIG_MAG_FROM
    bcc smaller
    sec
    sbc f:BIG_MAG_FROM
    jsr pic_part
    clc
    adc f:BIG_MAG_FROM
    bra size
smaller:
    lda f:BIG_MAG_FROM
    sec
    sbc f:BIG_MAG_TO
    jsr pic_part
    eor #$FF
    sec
    adc f:BIG_MAG_FROM
size:
    sta f:BIG_MAG
    lda f:PIC_STEP
    cmp f:PIC_STEPS
    bcc going
    lda f:BIG_FLAGS
    and #$FF ^ BIG_ZOOMING
    sta f:BIG_FLAGS
    jmp big_m7_arrive
going:
    jsr big_m7_matrix
done:
    rts
.endproc

; BIG_M7_A for step PIC_STEP of PIC_STEPS —one of one if there are no
; steps, and the last past them—: the size is FROM + (TO − FROM) × t / T
; percent, so
;
;     A = 256 × 100 / size = 25600 × T / (FROM × (T − t) + TO × t)
;
; with no rounding but the last one. 25600 × T takes 23 bits and the
; hardware divides 16 by 8, so it is divided by hand. Past what the matrix
; holds —a size under 0.8 %— the picture is not drawn.
.proc big_m7_matrix
.a8
.i16
    lda f:PIC_STEPS
    bne steps
    lda #1
steps:
    sta temp + 2                ; T
    lda f:PIC_STEP
    cmp temp + 2
    bcc within
    lda temp + 2
within:
    sta temp + 3                ; t
    lda f:BIG_MAG_TO
    sta WRMPYA
    lda temp + 3
    sta WRMPYB                  ; TO × t: eight cycles
    lda temp + 2
    sec
    sbc temp + 3
    sta temp + 3                ; T − t, while it multiplies
    rep #$20
.a16
    lda RDMPYL
    sta temp
    sep #$20
.a8
    lda f:BIG_MAG_FROM
    sta WRMPYA
    lda temp + 3
    sta WRMPYB                  ; FROM × (T − t)
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc temp
    beq hidden                  ; nothing: the size is 0
    sta f:BIG_M7_DIVISOR
    ; The dividend, 25600 × T plus half the divisor to round, in temp's
    ; four bytes: 100 × T, a byte up.
    lsr a
    pha
    sep #$20
.a8
    lda #100
    sta WRMPYA
    lda temp + 2
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    xba
    pha
    and #$FF00                  ; its low byte, up
    sta temp
    pla
    and #$00FF                  ; its high byte, in the third
    sta temp + 2
    pla
    clc
    adc temp
    sta temp
    lda temp + 2
    adc #0
    sta temp + 2
    jsr big_divide
    lda temp + 2
    bne hidden
    lda temp
    bmi hidden                  ; past $7FFF: the matrix's sign
    sta f:BIG_M7_A
    sep #$20
.a8
    rts
hidden:
.a16
    lda #BIG_M7_HIDDEN
    sta f:BIG_M7_A
    sep #$20
.a8
    rts
.endproc

; temp's 32 bits over BIG_M7_DIVISOR, into temp: shift and subtract, a bit
; at a time. The remainder can go past sixteen bits for a moment —the
; divisor takes them all—, and the carry out of `rol` says so.
.proc big_divide
.a16
.i16
    lda #0                      ; the remainder
    ldx #32
each:
    asl temp
    rol temp + 2
    rol a
    bcs subtract
    cmp f:BIG_M7_DIVISOR
    bcc next
subtract:
    sbc f:BIG_M7_DIVISOR        ; the carry is set on both roads
    inc temp                    ; the bit `asl` left at zero
next:
    dex
    bne each
    rts
.endproc

; The next piece of VRAM, at most BIG_M7_CHUNK bytes, by DMA: in the
; vblank, or with the screen off. Leaves BIG_M7_PIECE on the next one when
; this one is over.
.proc big_m7_piece
.a8
.i16
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECE_STAMP
    bne sized
    ; The window's tilemap, which `stamp_window_at` writes whole: 640 bytes.
    jsl f:big_stamp_far + FAST
    bra over
sized:
    lda f:BIG_IMG
    jsr big_entry
    lda f:BIG_M7_PIECE
    jsr big_m7_setup            ; the DMA from where the piece goes on
.a16
    sta f:BIG_M7_SIZE
    sec
    sbc f:BIG_M7_DONE
    cmp #BIG_M7_CHUNK + 1
    bcc fits
    lda #BIG_M7_CHUNK
fits:
    sta DAS0L
    clc
    adc f:BIG_M7_DONE
    sta f:BIG_M7_DONE
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda f:BIG_M7_DONE
    cmp f:BIG_M7_SIZE
    sep #$20
.a8
    bcc going
over:
    lda f:BIG_M7_PIECE
    inc a
    sta f:BIG_M7_PIECE
    lda #0
    sta f:BIG_M7_DONE
    sta f:BIG_M7_DONE + 1
going:
    rts
.endproc

; Piece A8 of the picture whose entry is X, set up for DMA channel 0 from
; BIG_M7_DONE bytes into it: VMAIN, the VRAM address, the source and how it
; is written. Returns with the piece's whole size in A16.
.proc big_m7_setup
.a8
.i16
    cmp #BIG_PIECE_ZEROS
    beq zeros
    bcs not_texture
    ; The map's rows: the low bytes, from word 0.
    stz VMAIN
    lda #$18
    sta BBAD0
    stz DMAP0
    lda f:big_table + BE_M7_ROWS + 2, x
    sta A1B0
    rep #$20
.a16
    lda f:big_table + BE_M7_ROWS, x
    clc
    adc f:BIG_M7_DONE
    sta A1T0L
    lda f:BIG_M7_DONE
    sta VMADDL
    lda f:big_table + BE_M7_ROW_BYTES, x
    rts
zeros:
.a8
    ; The rest of the map, tile 0: past the picture the plane is blank.
    stz VMAIN
    lda #$18
    sta BBAD0
    lda #$08                    ; one register, the source fixed
    sta DMAP0
    jsr zero_source
    rep #$20
.a16
    lda f:big_table + BE_M7_ROW_BYTES, x
    clc
    adc f:BIG_M7_DONE
    sta VMADDL
    lda #BIG_M7_WORDS
    sec
    sbc f:big_table + BE_M7_ROW_BYTES, x
    rts
not_texture:
.a8
    cmp #BIG_PIECE_TILES
    bne not_tiles
    ; The tiles: the high bytes, from word 0.
    lda #$80
    sta VMAIN
    lda #$19
    sta BBAD0
    stz DMAP0
    lda f:big_table + BE_M7_TILES + 2, x
    sta A1B0
    rep #$20
.a16
    lda f:big_table + BE_M7_TILES, x
    clc
    adc f:BIG_M7_DONE
    sta A1T0L
    lda f:BIG_M7_DONE
    sta VMADDL
    lda f:big_table + BE_M7_BYTES, x
    rts
not_tiles:
.a8
    ; The rest are words, from where the map has them.
    pha
    lda #$80
    sta VMAIN
    lda #$18
    sta BBAD0
    ldx map_ofs
    pla
    cmp #BIG_PIECE_WINDOW
    bne not_window
    ; The window's tiles, as `load_window` sends them.
    lda #$01                    ; two registers
    sta DMAP0
    win_bank window_tiles, WS_TILES
    sta A1B0
    rep #$20
.a16
    win_lo window_tiles, WS_TILES
    clc
    adc f:BIG_M7_DONE
    sta A1T0L
    lda f:map_table + M_VRAM_WINDOW, x
    jsr add_vram
    lda #WINDOW_TILES * 32
    rts
not_window:
.a8
    pha
    lda #$09                    ; two registers, the source fixed
    sta DMAP0
    jsr zero_source
    pla
    cmp #BIG_PIECE_ABOVE
    bne blank
    ; The layer above's tilemap, empty, as `big_load` leaves it.
    rep #$20
.a16
    lda #VRAM_ABOVE_MAP
    jsr add_vram
    lda #$1000                  ; its two screens of 32x32
    rts
blank:
.a8
    ; And BG2's tile 0, which that tilemap names everywhere: it was under
    ; the picture's tiles. BG12NBA's high nibble is BG2's base, in $1000
    ; words.
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$F0
    xba
    lda #0
    rep #$20
.a16
    jsr add_vram
    lda #32
    rts

; VMADDL at word A16, plus the words already up.
add_vram:
.a16
    pha
    lda f:BIG_M7_DONE
    lsr a
    clc
    adc 1, s
    sta VMADDL
    pla
    rts

; Channel 0's source at `big_zero`.
zero_source:
.a8
    rep #$20
.a16
    lda #.loword(big_zero)
    sta A1T0L
    sep #$20
.a8
    lda #^big_zero
    sta A1B0
    rts
.endproc

; In the vblank, from `big_vblank`, for a picture with a texture: the mode,
; the layers and the matrix that BIG_M7_SHOW asks for, and a piece of VRAM.
; BG1's scroll is already written: in mode 7 it is the plane's.
.proc big_m7_vblank
.a8
.i16
    lda f:BIG_M7_SHOW
    and #$7F
    cmp #BIG_M7_ZOOM
    beq zoom
    ; Mode 1: still, BG1 alone, as `big_load_hybrid` left it; gone, BG2
    ; alone —the window over the black— once it is back, and nothing until
    ; then.
    lda #$01
    sta BGMODE
    lda f:BIG_FLAGS
    and #$FF ^ BIG_M7
    sta f:BIG_FLAGS
    lda f:BIG_M7_SHOW
    and #$7F
    cmp #BIG_M7_STILL
    beq still
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECES
    lda #$00
    bcc layers
    lda #$02
    bra layers
still:
    lda #$01
    bra layers
zoom:
    php
    sei                         ; the PPU's multiplier is `irq_music`'s too
    lda #$07
    sta BGMODE
    lda #BIG_M7SEL
    sta M7SEL
    lda f:BIG_M7_A
    sta M7A
    lda f:BIG_M7_A + 1
    sta M7A
    stz M7B
    stz M7B
    stz M7C
    stz M7C
    lda f:BIG_M7_A
    sta M7D
    lda f:BIG_M7_A + 1
    sta M7D
    lda f:BIG_IMG
    jsr big_entry
    lda f:big_table + BE_M7_X, x
    sta M7X
    lda f:big_table + BE_M7_X + 1, x
    sta M7X
    lda f:big_table + BE_M7_Y, x
    sta M7Y
    lda f:big_table + BE_M7_Y + 1, x
    sta M7Y
    ; From here `irq_music` multiplies by hand; and the wave's HDMA, which
    ; writes BG1's scroll line by line, stays off.
    lda f:BIG_FLAGS
    and #$FF ^ BIG_WAVE_ON
    ora #BIG_M7
    sta f:BIG_FLAGS
    plp
    ; BG1 alone, unless it is too small to be drawn.
    rep #$20
.a16
    lda f:BIG_M7_A
    cmp #BIG_M7_HIDDEN
    sep #$20
.a8
    lda #$01
    bcc layers
    lda #$00
layers:
    sta TM
    ; And a piece: the texture's while it is still, and the window's once
    ; mode 7 or the black took the upper half from the picture. Not with a
    ; message's line waiting: the two do not fit in one vblank.
    lda f:BIG_M7_PIECE
    cmp #BIG_PIECE_WINDOW
    bcc piece
    cmp #BIG_PIECES
    bcs done
    lda f:BIG_M7_SHOW
    and #$7F
    beq done                    ; still: the upper half is the picture's
    lda f:BIG_M7_SHOW
    ora #BIG_M7_SPENT
    sta f:BIG_M7_SHOW
piece:
    lda f:msg_upload
    bne done
    jsr big_m7_piece
done:
    rts
.endproc
