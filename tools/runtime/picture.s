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
    rts
.endproc

; `emit_object` for bank 1: the pictures are drawn from there.
.proc emit_object_far
    jsr emit_object
    rtl
.endproc
