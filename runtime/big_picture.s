.segment "FAR"
.a8
.i16

; --- the big pictures: BG1 in mode 1 -------------------------------------------
;
; A `ShowPicture` too big for the sprites —an instructions page, a photo of
; the whole screen, the end of the game— is drawn in **BG1, with the console
; in mode 1 while it is up**: `decisiones/las-imagenes-grandes-en-modo-1.md`.
; Mode 1 reads BG1 at 4 bits a pixel and BG2 as mode 3 already did, so the
; message window, which is BG2, goes on as it was; the map is gone. Which
; pictures go here and how they are drawn is the converter's —see
; tools/port/picture.py—, and each is an entry of `big_table`: see
; `big_pictures_section` in rm2k-snes-mapdata.
;
; **Showing one takes the screen off**: 30 KB of tiles do not go up in a
; vblank. `big_load` turns the screen off and sends the tiles to VRAM by DMA
; straight from the cartridge —they are stored raw: see
; `big_pictures_section` in rm2k-snes-mapdata—, and decompresses the
; tilemap; the screen comes back on in the next vblank, the brightness as it
; was. The game's big pictures go up over a screen tinted black or after a
; white flash, so the black frames do not show; over a visible map —the
; photo of map 212— they are a blink.
;
; **Where it lives is the same in every VRAM layout**: its tiles from word
; 0 to $3FFF —the 1024 a tilemap entry names—, over the sprites and the
; map's tiles, and its tilemap at $4000. The window's tilemap is in that
; range in one layout, so it moves to $4800 meanwhile; BG2's tiles and the
; window's are above $5000 in all of them. The layer above the map is BG2
; too, and in mode 1 it would draw over the picture: its tilemap is
; emptied. The sprites are off: RM2k draws pictures over the characters,
; and the picture covers the screen.
;
; **Erasing it reloads the map**, the way coming back from a battle does,
; with its two black frames: `big_back_far`, in picture.s. A map change
; erases it as RM2k does, and the load puts everything back.
;
; While it is up the vblank does not upload poses, strips of the map, nor
; the ChipSet's animation —they would land on the picture—, nor the tint:
; RM2k does not tint pictures, and the map's palettes are reloaded tinted
; when it goes. See `flush_video`.

; Where the layer lives, in VRAM words.
BIG_VRAM_MAP    = $4000
BIG_VRAM_WINDOW = $4800
; BG1SC carries the tilemap's address in its six high bits; the size bits
; come with each picture.
BIG_BG1SC       = >BIG_VRAM_MAP
; Its palettes: the seven above the window's. `BIG_PALETTES` in picture.py.
BIG_PALETTES    = 7
BIG_CGRAM       = 16
; The wave's HDMA table: two stretches of half the screen's lines, each a
; count with bit 7 —one value per line— and two bytes per line, and a zero.
BIG_WAVE_LINES  = 112
BIG_WAVE_BYTES  = 2 * (1 + 2 * BIG_WAVE_LINES) + 1
.assert BIG_PAL >= ANIM_DRAWINGS, error, "the big picture's palette steps on the carried bytecode"
.assert BIG_PAL + BIG_PALETTES * 32 <= BIG_WAVE_A, error, "the big picture's palette steps on its wave"
.assert BIG_WAVE_A + BIG_WAVE_BYTES <= BIG_WAVE_B, error, "the two wave tables overlap"
.assert BIG_WAVE_B + BIG_WAVE_BYTES <= ANIM_DRAWINGS_END, error, "the wave table goes past LZ2_BUFFER"

; An entry of `big_table`: see `big_pictures_section` in rm2k-snes-mapdata.
BE_TILES  = 0                   ; long: the tiles, raw
BE_MAP    = 3                   ; long: the tilemap's
BE_COLORS = 6                   ; long: the colours, raw
BE_BYTES  = 9                   ; word: the tiles' bytes
BE_SIZE   = 11                  ; byte: BG1SC's size bits
BE_VOFS   = 12                  ; word: BG1VOFS with the scroll at zero
BE_HALF_Y = 14                  ; word: half its height, in RM2k's pixels
BE_CORNER_Y = 16                ; word: its top on the console's screen, as shown

; The entry of picture A8, in X. Leaves A at eight bits.
.proc big_entry
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; BIG_ENTRY bytes each
    tax
    sep #$20
.a8
    rts
.endproc
.assert BIG_ENTRY = 32, error, "big_entry multiplies by thirty-two"

; No big picture, and no layer: on reset and on every map change, which
; reloads the map anyway. Only the registers the load does not write are put
; back here: the mode and the main screen. Called from `pic_clear`.
.proc big_clear
.a8
.i16
    lda f:BIG_FLAGS
    lsr a
    bcc off
    lda #$03
    sta BGMODE
    lda #$13                    ; as `ppu_init`: the two layers and the sprites
    sta TM
off:
    lda #0
    sta f:BIG_FLAGS
    lda #PIC_NONE
    sta f:BIG_IMG
    rts
.endproc

; `OP_BIG_SHOW`: image, r, g, b, transparency, saturation, wave. Enters with
; Y on the operands and leaves it past them. The picture is up with its tone
; from this frame on, unscrolled and with its wave starting over, as
; `Game_Pictures::Show` leaves it.
.proc big_show
.a8
.i16
    lda [code_ptr], y           ; the image
    iny
    pha
    ldx #$0000
operands:
    lda [code_ptr], y
    iny
    sta f:BIG_TONE, x           ; r, g, b, transparency, saturation, wave:
    inx                         ; the same order as their RAM
    cpx #6
    bne operands
    phy
    ; A ramp of the big one is over: the new picture starts still.
    lda f:PIC_RAMP
    cmp #PIC_BIG
    bne no_ramp
    lda #PIC_NONE
    sta f:PIC_RAMP
no_ramp:
    lda #0
    sta f:BIG_PHASE
    sta f:BIG_Y
    sta f:BIG_Y + 1
    ; The same picture again is its tone; another one is a load.
    lda f:BIG_FLAGS
    lsr a
    bcc load
    lda 3, s                    ; the image, under the cursor
    cmp f:BIG_IMG
    bne load
    jsr big_m7_again            ; one with a texture may have to go up again
    bcc loaded
load:
    lda 3, s
    sta f:BIG_IMG
    jsr big_load
loaded:
    jsr big_wave_flag
    jsr big_palette
    ply
    pla
    rtl
.endproc
.assert BIG_TRANS = BIG_TONE + 3 && BIG_SAT = BIG_TONE + 4 && BIG_WAVE = BIG_TONE + 5, error, "big_show reads its operands in the order of their RAM"

; BIG_WAVE_ON as the strength says.
.proc big_wave_flag
.a8
.i16
    lda f:BIG_FLAGS
    and #$FF ^ BIG_WAVE_ON
    sta f:BIG_FLAGS
    lda f:BIG_WAVE
    beq still
    lda f:BIG_FLAGS
    ora #BIG_WAVE_ON
    sta f:BIG_FLAGS
still:
    rts
.endproc

; Picture BIG_IMG into the layer, with the screen off: its tiles and its
; tilemap to VRAM, the window's tilemap moved, the layer above emptied, and
; the registers. Leaves BIG_ON set; the screen comes back on in the next
; vblank, from `brightness`.
.proc big_load
.a8
.i16
    lda #$80
    sta INIDISP                 ; what follows writes VRAM by DMA
    jsr big_m7_leave            ; what one with a texture took, back
    lda #$80
    sta VMAIN
    lda f:BIG_IMG
    jsr big_entry
    ; One with a texture goes in VRAM's upper half: big_picture_zoom.s.
    rep #$20
.a16
    lda f:big_table + BE_M7_BYTES, x
    sep #$20
.a8
    beq plain
    jmp big_load_hybrid
plain:
    phx
    ; The tiles, from the cartridge to word 0.
    rep #$20
.a16
    lda f:big_table + BE_BYTES, x
    sta DAS0L
    lda f:big_table + BE_TILES, x
    sta A1T0L
    stz VMADDL
    sep #$20
.a8
    lda f:big_table + BE_TILES + 2, x
    sta A1B0
    jsr big_dma_vram
    ; The tilemap, the same way, to its place.
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
    lda #$1000                  ; two screens of 32x32
    sta DAS0L
    lda #BIG_VRAM_MAP
    sta VMADDL
    sep #$20
.a8
    jsr big_to_vram
    ; The window's tilemap where the layer does not reach, and HDMA's table
    ; pointing at it from the window's line down; `load_window` puts both
    ; back when the map returns.
    jsl f:big_stamp_far + FAST
    lda #>BIG_VRAM_WINDOW
    sta f:MSG_SC
    jsl msg_hdma_build          ; the window's stretch, pointing there
    ; The layer above, empty: its tile 0 is blank in every map.
    rep #$20
.a16
    lda #VRAM_ABOVE_MAP
    sta VMADDL
    lda #.loword(big_zero)
    sta A1T0L
    lda #$1000                  ; its two screens of 32x32
    sta DAS0L
    sep #$20
.a8
    lda #^big_zero
    sta A1B0
    lda #$09                    ; two registers, the source fixed
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The registers: mode 1, BG1's tiles from word 0 and BG2's where the map
    ; has them, BG1's tilemap at its place and size, and the two layers
    ; without the sprites.
    lda #$01
    sta BGMODE
    ldx map_ofs
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$F0
    sta BG12NBA
    plx
    lda f:big_table + BE_SIZE, x
    ora #BIG_BG1SC
    sta BG1SC
    lda #$03
    sta TM
    lda f:BIG_FLAGS
    ora #BIG_ON
    sta f:BIG_FLAGS
    rts
.endproc

; Stream X:A into LZ2_BUFFER. A tilemap, and no more: above it, from
; `CODE_CARRY`, is the bytecode a page carries from another map, which may
; be the one showing the picture.
.assert LZ2_BUFFER + $1000 <= CODE_CARRY, error, "a big picture's tilemap would overwrite the carried bytecode"
.proc big_unpack
.a8
.i16
    pha
    lda #^LZ2_BUFFER
    sta f:LZ2_BANK
    pla
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_decompress + FAST
    rts
.endproc

; DAS0L bytes from LZ2_BUFFER to where VMADDL points, word by word.
.proc big_to_vram
.a8
.i16
    ldx #.loword(LZ2_BUFFER)
    stx A1T0L
    lda #^LZ2_BUFFER
    sta A1B0
    ; and on into `big_dma_vram`
.endproc
; DAS0L bytes from A1B0:A1T0L to where VMADDL points, word by word. The
; picture's tiles may be in the `.msu`, in a cartridge that needs it: see
; `msu_dma0`.
.proc big_dma_vram
.a8
.i16
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
.ifdef MSU_REQUIRED
    jsr msu_dma0
.endif
    lda #$01
    sta MDMAEN
    rts
.endproc

; A zero word, which the DMA repeats to empty a tilemap.
big_zero:
    .word 0

; The picture's palette with its tone, its transparency and its saturation,
; for the vblank: see `big_palette_build` in picture.s.
.proc big_palette
.a8
.i16
    lda f:BIG_IMG
    jsr big_entry
    rep #$20
.a16
    lda f:big_table + BE_COLORS, x
    sta tint_ptr
    sep #$20
.a8
    lda f:big_table + BE_COLORS + 2, x
    sta tint_ptr + 2
    jsl f:big_palette_build + FAST
    rts
.endproc

; `OP_PICTURE_ERASE` of the big one: enters with Y past the slot. Takes the
; layer down and reloads the map.
.proc big_erase
.a8
.i16
    lda f:PIC_RAMP
    cmp #PIC_BIG
    bne no_ramp
    lda #PIC_NONE
    sta f:PIC_RAMP
no_ramp:
    lda f:BIG_FLAGS
    lsr a
    bcc gone
    phy
    lda #0
    sta f:BIG_FLAGS
    lda #PIC_NONE
    sta f:BIG_IMG
    lda #$80
    sta INIDISP
    stz HDMAEN                  ; the wave's channel, before the reload
    jsl f:big_back_far + FAST
    ply
gone:
    rtl
.endproc

; `OP_BIG_MOVE`: r, g, b, transparency, frames, y, wave, saturation. Enters
; with Y on the operands and leaves it past them.
;
; A move with no big picture up consumes its operands and does nothing, as
; `pic_move` does with an empty slot.
.proc big_move
.a8
.i16
    lda f:BIG_FLAGS
    lsr a
    bcs shown
    rep #$20
.a16
    tya
    clc
    adc #9
    tay
    sep #$20
.a8
    rtl
shown:
    ; Another ramp ends here, where it was going: there is one.
    lda f:PIC_RAMP
    bmi free                    ; none, or the big one's, which goes on from here
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr pic_arrive
free:
    ldx #$0000
to:
    lda [code_ptr], y
    iny
    sta f:PIC_TO, x             ; r, g, b, transparency
    lda f:BIG_TONE, x
    sta f:PIC_FROM, x           ; from where it is now
    inx
    cpx #4
    bne to
    lda [code_ptr], y
    iny
    sta f:PIC_STEPS
    ; Where its corner goes: RM2k's, from the centre and half the height,
    ; on the console's screen —fourteen fifteenths, rounded down—, against
    ; where it was shown. It is computed here and not by the compiler
    ; because which picture is up under the number is not known until now.
    ; The scroll it goes to is the opposite: the corner going up is the
    ; layer scrolling down. What the ramp walks is how far from where it is.
    phy
    lda f:BIG_IMG
    jsr big_entry
    ply
    rep #$20
.a16
    lda f:BIG_Y
    sta f:BIG_Y_FROM
    lda [code_ptr], y           ; the centre's y
    iny
    iny
    sec
    sbc f:big_table + BE_HALF_Y, x
    phx
    jsr pic_scale_y             ; the corner, on the console's screen
    plx
    eor #$FFFF
    inc a
    clc
    adc f:big_table + BE_CORNER_Y, x
    sec
    sbc f:BIG_Y
    tax                         ; the distance, signed
    sep #$20
.a8
    lda f:BIG_FLAGS
    and #$FF ^ BIG_DOWN
    sta f:BIG_FLAGS
    rep #$20
.a16
    txa
    bpl ahead
    eor #$FFFF
    inc a
    pha
    sep #$20
.a8
    lda f:BIG_FLAGS
    ora #BIG_DOWN
    sta f:BIG_FLAGS
    rep #$20
.a16
    pla
ahead:
    cmp #$0100
    bcc fits
    lda #$00FF                  ; more than the layer is tall: as far as it goes
fits:
    sep #$20
.a8
    sta f:BIG_DY
    lda f:BIG_WAVE
    sta f:BIG_WAVE_FROM
    lda [code_ptr], y
    iny
    sta f:BIG_WAVE_TO
    lda [code_ptr], y
    iny
    sta f:BIG_SAT
    phy
    lda #0
    sta f:PIC_STEP
    lda f:PIC_STEPS
    bne ramp
    jsr big_arrive
    ply
    rtl
ramp:
    lda #PIC_BIG
    sta f:PIC_RAMP
    ; The saturation goes at once: one palette now, with the tone it has.
    jsr big_palette
    ply
    rtl
.endproc

; The big one where its ramp goes, now, and no ramp.
.proc big_arrive
.a8
.i16
    ldx #3
each:
    lda f:PIC_TO, x
    sta f:BIG_TONE, x
    dex
    bpl each
    lda f:BIG_WAVE_TO
    sta f:BIG_WAVE
    lda f:BIG_DY
    jsr big_scroll_part
    lda #PIC_NONE
    sta f:PIC_RAMP
    jsr big_wave_flag
    jmp big_palette
.endproc

; BIG_Y = BIG_Y_FROM plus or minus A8, as BIG_DOWN says.
.proc big_scroll_part
.a8
.i16
    rep #$20
.a16
    and #$00FF
    pha
    sep #$20
.a8
    lda f:BIG_FLAGS
    and #BIG_DOWN
    rep #$20
.a16
    beq up
    pla
    eor #$FFFF
    inc a
    bra add
up:
    pla
add:
    clc
    adc f:BIG_Y_FROM
    sta f:BIG_Y
    sep #$20
.a8
    rts
.endproc

; Every frame, from `pic_tick`: the wave turns and the ramp steps.
.proc big_frame
.a8
.i16
    lda f:BIG_FLAGS
    lsr a
    bcs up
    rts
up:
    lda f:PIC_RAMP
    cmp #PIC_BIG
    bne no_ramp
    jsr big_step
no_ramp:
    lda f:BIG_FLAGS
    and #BIG_WAVE_ON
    beq still
    ; `Game_Pictures::Update` adds 8 to the phase every frame: a turn every
    ; 32 frames.
    lda f:BIG_PHASE
    clc
    adc #8
    sta f:BIG_PHASE
    jsr big_wave_table
still:
    rts
.endproc

; One frame of the big one's ramp: the four channels, the wave and the
; scroll, with the same arithmetic as the slots' —see `pic_tick`—. The
; palette is rebuilt only if the tone or the transparency changed.
.proc big_step
.a8
.i16
    lda f:PIC_STEP
    inc a
    sta f:PIC_STEP
    stz temp                    ; whether the palette changed
    ldx #3
each:
    jsr pic_channel
    cmp f:BIG_TONE, x
    beq same
    sta f:BIG_TONE, x
    inc temp
same:
    dex
    bpl each
    ; The wave's strength, the same way.
    lda f:BIG_WAVE_TO
    cmp f:BIG_WAVE_FROM
    bcc weaker
    sec
    sbc f:BIG_WAVE_FROM
    jsr pic_part
    clc
    adc f:BIG_WAVE_FROM
    bra wave
weaker:
    lda f:BIG_WAVE_FROM
    sec
    sbc f:BIG_WAVE_TO
    jsr pic_part
    eor #$FF
    sec
    adc f:BIG_WAVE_FROM
wave:
    sta f:BIG_WAVE
    jsr big_wave_flag
    lda f:BIG_DY
    jsr pic_part
    jsr big_scroll_part
    lda temp
    beq unchanged
    jsr big_palette
unchanged:
    jsr big_m7_step             ; and its size: big_picture_zoom.s
    lda f:PIC_STEP
    cmp f:PIC_STEPS
    bcc going
    lda #PIC_NONE
    sta f:PIC_RAMP
going:
    rts
.endproc
.assert BIG_TRANS = BIG_TONE + 3, error, "big_step walks the tone and the transparency as PIC_TO's four"

; The wave's table for the next frame, in the one the HDMA is not reading,
; and the flag that swaps them for the next vblank.
;
; `Bitmap::WaverBlit`, in easyrpg-player: line `i` of the picture moves
; `2 × depth × sin(phase + i × 2π / 32)` pixels to the right, with the depth
; twice the strength. RM2k's lines are fifteen fourteenths of the console's
; —one more every fourteen, which is what `temp + 1` counts—, and its pixels
; five fourths, which `big_depth` carries. A turn is 32 of RM2k's lines,
; eight of the phase's 256 to a line. The
; layer goes the other way from the picture, so the scroll is minus that. A
; line moved past the picture's edge shows its edge mirrored —see
; `big_tilemap` in rm2k-snes-mapdata—.
;
; The products are the CPU's multiplier and not the PPU's: that one belongs
; to `irq_music`, which can land in the middle of this.
.proc big_wave_table
.a8
.i16
    lda f:BIG_WAVE
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:big_depth, x
    sta WRMPYA                  ; it stays for every product
    ; Into the table the HDMA is not reading.
    ldx #.loword(BIG_WAVE_A)
    lda f:BIG_FLAGS
    and #BIG_B
    bne write_a
    ldx #.loword(BIG_WAVE_B)
write_a:
    stz temp                    ; RM2k's line, in the phase's units
    stz temp + 1                ; and the console's lines until one more
    ldy #$0000                  ; the line
    lda #$80 | BIG_WAVE_LINES
    sta f:$7F0000, x            ; the first stretch's count
    inx
line:
    cpy #BIG_WAVE_LINES
    bne same_stretch
    lda #$80 | BIG_WAVE_LINES
    sta f:$7F0000, x            ; and the second's
    inx
same_stretch:
    lda temp
    clc
    adc #8                      ; the next line, for the next round
    sta temp
    sec
    sbc #8
    inc temp + 1
    pha
    lda temp + 1
    cmp #14
    bne same_line
    stz temp + 1
    lda temp
    clc
    adc #8                      ; and a fifteenth every fourteen
    sta temp
same_line:
    pla
    clc
    adc f:BIG_PHASE
    pha
    and #$7F
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:big_sine, x
    plx
    sta WRMPYB                  ; starts: the product takes eight cycles
    pla                         ; and in the meantime, the phase again
    bmi left                    ; the second half of the turn: the sine is negative
    ; The picture goes right, so the layer's scroll goes left: minus the
    ; offset, sixteen bits —and minus zero is zero, high byte too—.
    rep #$20
.a16
    lda RDMPYL + 1              ; over 256: at most 32
    and #$00FF
    eor #$FFFF
    inc a
    bra put
left:
.a8
    rep #$20
.a16
    lda RDMPYL + 1
    and #$00FF
put:
    sta f:$7F0000, x
    sep #$20
.a8
    inx
    inx
    iny
    cpy #2 * BIG_WAVE_LINES
    bne line
    lda #0
    sta f:$7F0000, x            ; end of the table
    ; Ready: the next vblank points the channel at it.
    lda f:BIG_FLAGS
    eor #BIG_B
    sta f:BIG_FLAGS
    rts
.endproc
.assert ^BIG_WAVE_A = $7F && ^BIG_WAVE_B = $7F, error, "big_wave_table writes the tables in bank $7F"

; In the vblank, from `flush_video`, with the layer up: its palette if it
; changed, its scroll, and the wave's channel pointed at the table that is
; ready. What does not go up while the layer does —the map's strips— is
; dropped: the map is reloaded whole when it goes.
.proc big_vblank
.a8
.i16
    lda f:BIG_FLAGS
    bpl no_palette
    and #$FF ^ BIG_PENDING
    sta f:BIG_FLAGS
    lda #BIG_CGRAM
    sta CGADD
    ldx #.loword(BIG_PAL)
    stx A1T0L
    lda #^BIG_PAL
    sta A1B0
    ldx #BIG_PALETTES * 32
    stx DAS0L
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_palette:
    ; Its vertical scroll: the entry's, plus how far it was moved.
    lda f:BIG_IMG
    jsr big_entry
    rep #$20
.a16
    lda f:big_table + BE_VOFS, x
    clc
    adc f:BIG_Y
    sep #$20
.a8
    sta BG1VOFS
    xba
    sta BG1VOFS
    stz BG1HOFS                 ; the wave's channel writes it from line 0
    stz BG1HOFS
    ; The wave's channel at the table that is ready: the HDMA reads its
    ; address again at the top of each frame.
    lda #$02                    ; one register, written twice
    sta DMAP4
    lda #<BG1HOFS
    sta BBAD4
    lda #^BIG_WAVE_A
    sta A1B4
    ldx #.loword(BIG_WAVE_A)
    lda f:BIG_FLAGS
    and #BIG_B
    beq table_a
    ldx #.loword(BIG_WAVE_B)
table_a:
    stx A1T4L
    ; A picture with a texture: its mode, its matrix and a piece of VRAM.
    lda f:BIG_FLAGS
    and #BIG_TEXTURE
    beq without
    jsr big_m7_vblank
without:
    rep #$20
.a16
    stz col_addr
    stz col_addr_b
    stz row_addr
    stz row_addr_b
    sep #$20
.a8
    rtl
.endproc

; How far the wave moves a line at each strength, in the console's pixels
; times 256 over 127: the sine's 127 is one. `4 × strength` of RM2k's
; pixels —twice the depth, which is twice the strength— at four fifths.
big_depth:
    .byte 0, 6, 13, 19, 26, 32, 39, 45, 52, 58, 65

; The sine of the first half turn, 128 to a half and 127 at the top:
; `round(127 × sin(2π i / 256))`. The second half is the first negated.
big_sine:
    .byte 0, 3, 6, 9, 12, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46
    .byte 49, 51, 54, 57, 60, 63, 65, 68, 71, 73, 76, 78, 81, 83, 85, 88
    .byte 90, 92, 94, 96, 98, 100, 102, 104, 106, 107, 109, 111, 112, 113, 115, 116
    .byte 117, 118, 120, 121, 122, 122, 123, 124, 125, 125, 126, 126, 126, 127, 127, 127
    .byte 127, 127, 127, 127, 126, 126, 126, 125, 125, 124, 123, 122, 122, 121, 120, 118
    .byte 117, 116, 115, 113, 112, 111, 109, 107, 106, 104, 102, 100, 98, 96, 94, 92
    .byte 90, 88, 85, 83, 81, 78, 76, 73, 71, 68, 65, 63, 60, 57, 54, 51
    .byte 49, 46, 43, 40, 37, 34, 31, 28, 25, 22, 19, 16, 12, 9, 6, 3
