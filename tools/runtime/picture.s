.segment "CODE"

; --- the ShowPicture pictures: what stays in bank 0 --------------------------
;
; The slots, the ramps and the drawing are in picture_far.s, in bank 1: bank 0
; has no room. What stays here is what leans on bank 0's routines —the
; palette, built with the screen tint's tables— and the bridge back to
; `emit_object`.

; Slot A's sixteen colours tinted with its tone, in the place of its palette
; in `cgram_shadow`, and the slot marked so `pic_flush` uploads them. Enters
; with `tint_ptr` on the picture's colours, which the caller found in its
; entry. Called with `jsl` from bank 1.
;
; It reuses `channel_table` and `build_palette`, which is what the screen
; tint already did: the only difference is where the three values come from
; and that a picture's saturation is always neutral —`picture_fits` accepts
; no other—, so `tint_s` is set to neutral while this runs and then given
; back. The three work tables are left with the picture's tint;
; `restore_tables` puts them back as the screen tint's, copying `pure`, which
; is much cheaper than rebuilding them.
;
; Slot s takes sprite palette 7 - s: see `picture_of_image` in
; rm2k-snes-map-sprites.
.proc pic_palette
.a8
.i16
    ; **And Y is saved.** `build_palette` uses it as the palette cursor and
    ; leaves it at 32, and whoever calls this from an opcode has it pointing
    ; into the bytecode: without this the interpreter went on reading thirty-two
    ; bytes further ahead and ran whatever was there. It was the first
    ; picture's first red, and one of the kind you cannot see: the page kept
    ; running, just a different one.
    phy
    rep #$20
.a16
    and #$00FF
    pha                         ; the slot
    asl a
    clc
    adc 1, s
    tax                         ; its tone, three bytes per slot
    sep #$20
.a8
    lda tint_s
    pha
    lda #TINT_NEUTRAL
    sta tint_s
    lda f:PIC_TONE + 2, x
    pha
    lda f:PIC_TONE + 1, x
    pha
    lda f:PIC_TONE + 0, x
    ldx #.loword(table_r)
    jsr channel_table
    pla
    ldx #.loword(table_g)
    jsr channel_table
    pla
    ldx #.loword(table_b)
    jsr channel_table
    rep #$20
.a16
    lda #16
    sta tint_count
    sep #$20
.a8
    jsr build_palette           ; the sixteen, tinted, in `pal_buf`
    pla
    sta tint_s
    ; And from there to the shadow, **without touching `tint_ready`**:
    ; setting it would send the map's three palettes up on every frame of a
    ; ramp, and that eats the vblank's pose budget. Palette 7 - s is entry
    ; 128 + 16 * (7 - s), that is 2 * 240 - 32 * s bytes into the shadow.
    rep #$20
.a16
    lda 1, s                    ; the slot
    xba                         ; times 256
    lsr a
    lsr a
    lsr a                       ; times 32
    eor #$FFFF
    sec
    adc #2 * (128 + 16 * 7)
    tax
    ldy #$0000
copy:
    lda pal_buf, y
    sta cgram_shadow, x
    inx
    inx
    iny
    iny
    cpy #32
    bne copy
    plx                         ; the slot
    sep #$20
.a8
    lda f:PIC_FLAGS, x
    ora #PIC_PENDING
    sta f:PIC_FLAGS, x
    jsr restore_tables
    ply
    rtl
.endproc

; The palettes the slots left waiting, to CGRAM: for the vblank, or with the
; screen off. Thirty-two bytes each, apart from the map's three: a picture's
; palette falls above `SPRITE_CGRAM`, that is, outside what `upload_palettes`
; uploads.
.proc pic_flush
.a8
.i16
    ldx #$0000
each:
    lda f:PIC_FLAGS, x
    bpl next                    ; PIC_PENDING is bit 7
    and #$FF ^ PIC_PENDING
    sta f:PIC_FLAGS, x
    ; Palette 7 - s: entry 240 - 16 * s.
    txa
    asl a
    asl a
    asl a
    asl a
    eor #$FF
    sec
    adc #128 + 16 * 7
    sta CGADD
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc #.loword(cgram_shadow)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    plx
next:
    inx
    cpx #PIC_SLOTS
    bne each
    ; fall through to `pic_blend`
.endproc

; **The translucency experiment**, 2026-10-01: a picture half transparent
; —from `PIC_HALF` to `PIC_HIDDEN`— is mixed half and half with what is
; under it, with the console's color math. Only the objects take part, and
; the hardware only mixes the ones in sprite palettes 4 to 7: the pictures
; are in 7 and 6, and the hero and the events stay opaque **if their map
; leaves them in 0 to 3** —a map with five or six character palettes, or the
; battle animation's box in 4 or 5, gets those mixed too while the picture
; is up—. The subscreen is the map's two layers; the message window, which
; is BG2, is not mixed because only the objects are, and the objects are
; masked on its lines anyway.
;
; The console mixes at 50 % or adds; RM2k's transparency is any
; percentage. So 25 to 75 is half, under 25 opaque, 76 and over not drawn:
; the shadow of 311, 100 to 50, is not there and then half; the smoke of
; 207, 40, is half.
;
; It is written on every vblank of the map, from the slots: off is
; `ppu_reset`'s, and the battle's fade leaves it that way too. See
; `decisiones/el-color-math-no-se-usa.md`, which was about translucent
; **events** and not pictures.
PIC_HALF = 25
.proc pic_blend
.a8
.i16
    ldx #$0000
each:
    lda f:PIC_IMG, x
    cmp #PIC_NONE
    beq next
    lda f:PIC_TRANS, x
    cmp #PIC_HALF
    bcc next
    cmp #PIC_HIDDEN
    bcs next
    lda #$02                    ; CGWSEL: add the subscreen, always
    sta CGWSEL
    lda #$50                    ; CGADSUB: add, halved, on the objects
    sta CGADSUB
    lda #$03                    ; TS: the map's two layers under them
    sta TS
    rts
next:
    inx
    cpx #PIC_SLOTS
    bne each
    lda #$30                    ; color math off, as `ppu_reset` leaves it
    sta CGWSEL
    stz CGADSUB
    stz TS
    rts
.endproc

; --- the big picture: what stays in bank 0 ------------------------------------
;
; See big_picture.s. These lean on bank 0's routines: the palette on the
; screen tint's, the window's tilemap on `stamp_window`, and the way back on
; the battle's.

; The big picture's seven palettes with its tone, its transparency and its
; saturation, into BIG_PAL, and BIG_PENDING for the vblank. Enters with
; `tint_ptr` on its colours. Called with `jsl` from bank 1.
;
; `pic_palette`'s road, with two differences: the saturation is the
; picture's —`build_palette` already does any—, and **the transparency
; darkens**: there is only black under the layer, so each channel's value
; is scaled by what is left, `tone × (100 - transparency) / 100`, before its
; table is built. It is exact for a tone that darkens; for one that
; brightens, the hard light and the fade do not commute and this is an
; approximation, which no picture of the game asks for.
.proc big_palette_build
.a8
.i16
    phy                         ; the bytecode's cursor: see `pic_palette`
    lda tint_s
    pha
    lda f:BIG_SAT
    sta tint_s
    ldx #2
fade:
    lda f:BIG_TONE, x
    sta WRMPYA
    lda #TINT_NEUTRAL
    sec
    sbc f:BIG_TRANS
    sta WRMPYB                  ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #TINT_NEUTRAL
    sta WRDIVB                  ; starts: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    pha                         ; blue, green and red: red on top
    dex
    bpl fade
    pla
    ldx #.loword(table_r)
    jsr channel_table
    pla
    ldx #.loword(table_g)
    jsr channel_table
    pla
    ldx #.loword(table_b)
    jsr channel_table
    rep #$20
.a16
    lda #BIG_PALETTES * 16
    sta tint_count
    sep #$20
.a8
    jsr build_palette           ; the 112, in `pal_buf`
    pla
    sta tint_s
    ldx #$0000
copy:
    lda pal_buf, x
    sta f:BIG_PAL, x
    inx
    cpx #BIG_PALETTES * 32
    bne copy
    lda f:BIG_FLAGS
    ora #BIG_PENDING
    sta f:BIG_FLAGS
    jsr restore_tables
    ply
    rtl
.endproc

; The window's tilemap at BIG_VRAM_WINDOW, with the screen off.
.proc big_stamp_far
.a8
.i16
    rep #$20
.a16
    lda #BIG_VRAM_WINDOW
    jsr stamp_window_at
    rtl
.endproc

; The map back after a big picture, with the screen off: what the layer
; overwrote is what a battle overwrites —the sprites, BG1's tiles and
; tilemap, the window's tilemap and HDMA, the layer above's tilemap— and is
; put back the way `back_from_battle` puts it, without what only the battle
; touches: the grid and the battlers' palettes. `back_to_map` sets mode 3
; and the main screen again, and the map's palettes tinted.
.proc big_back_far
.a8
.i16
    jsr load_sprite             ; the pose bank, the object palette and OBSEL
    jsr npc_poses_forget
    jsr load_window
    jsr fill_window
    jsr back_to_map
    rtl
.endproc

; `emit_object` for bank 1: the pictures are drawn from there.
.proc emit_object_far
    jsr emit_object
    rtl
.endproc
