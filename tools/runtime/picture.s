.segment "CODE"

; --- the ShowPicture picture ------------------------------------------------
;
; Six 32x32 objects with a sprite palette all to themselves, and a fade that is
; a tint of those fifteen colors frame by frame. See `tools/port/picture.py`,
; which is where it is written where each pixel lands and what color it is,
; and OP_PICTURE in events.py.
;
; The picture lives in **a single map** of the ROM —the one that took its tiles
; into the sprite bank; the converter stops if another one shows it— and is
; erased on map change, which is
; `Game_Pictures`' `erase_on_map_change`. Both things are the same: without
; its tiles in VRAM there would be nothing to draw.

; One frame of the ramp. `Game_Pictures::Picture::Update` interpolates with
; `(finish - current) / dt` over `double`, and the exact result of that
; sequence is linear: `desde + (hasta - desde) * paso / pasos`. Here it is
; done with integers, and the sign is taken out before dividing: the hardware
; divider does not have one.
;
; The palette is rebuilt **only when the tone really changed**. In the
; 210-frame ramp of "1 year earlier" the red goes up from 0 to 100, which means
; it changes one frame out of two: rebuilding it anyway cost 96 products and 96
; divisions per frame to write the same thirty-two bytes.
.proc picture_tick
.a8
.i16
    lda f:PICTURE_ACTIVE
    beq ready
    lda f:PICTURE_STEPS
    beq ready                   ; shown and still
    lda f:PICTURE_STEP
    cmp f:PICTURE_STEPS
    bcs ready                   ; the ramp has already arrived
    lda f:PICTURE_STEP           ; `inc` has no long form
    inc a
    sta f:PICTURE_STEP
    jsr picture_tone_now
    beq ready                   ; the same tone as the previous frame
    jmp picture_palette
ready:
    rts
.endproc

; This frame's tone, channel by channel. Leaves in A whether any changed.
;
; The subtraction always goes on the positive side, as in
; `one_flash_table`: the hardware divider has no sign, and Python's `//`
; rounds the other way with negatives. Both sides do this same computation
; split in two.
.proc picture_tone_now
.a8
.i16
    lda #0
    sta f:PICTURE_CHANGE
    ldx #$0000
channel:
    lda f:PICTURE_TO, x
    cmp f:PICTURE_FROM, x
    bcc low
    sec
    sbc f:PICTURE_FROM, x
    jsr picture_part
    clc
    adc f:PICTURE_FROM, x
    bra save
low:
    lda f:PICTURE_FROM, x
    sec
    sbc f:PICTURE_TO, x
    jsr picture_part
    eor #$FF                    ; `desde - parte` without a variable in between:
    sec                         ; ones' complement plus the carry is the minus
    adc f:PICTURE_FROM, x
save:
    cmp f:PICTURE_TONE, x
    beq equal
    sta f:PICTURE_TONE, x
    lda #1
    sta f:PICTURE_CHANGE
equal:
    inx
    cpx #3
    bne channel
    lda f:PICTURE_CHANGE
    rts
.endproc

; A = A * PICTURE_STEP / PICTURE_STEPS, with the hardware multiplier and
; divider. The product reaches 200 * 255 and fits in sixteen bits; the
; quotient does not go past 200, so the low byte is enough.
.proc picture_part
.a8
.i16
    sta WRMPYA
    lda f:PICTURE_STEP
    sta WRMPYB
    nop                         ; eight cycles until the product is ready
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; the dividend, sixteen bits
    sep #$20
.a8
    lda f:PICTURE_STEPS
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    rts
.endproc

; The picture's sixteen colors tinted with its tone, in their place in
; `cgram_shadow`. `flush_video` uploads them in the vblank with a DMA of its
; own.
;
; It reuses `channel_table` and `build_palette`, which is what the screen tint
; already did: the only difference is where the three values come from and
; that the picture's saturation is always neutral —`imagen_aceptable` accepts no
; other—, so `tint_s` is set to neutral while this runs and then given back.
; The three work tables are left with the picture's tint; `restore_tables` puts
; them back as the screen tint's, copying `pure`, which is much cheaper than
; rebuilding them.
.proc picture_palette
.a8
.i16
    ; **And Y is saved.** `build_palette` uses it as the palette cursor and
    ; leaves it at 32, and whoever calls this from an opcode has it pointing
    ; into the bytecode: without this the interpreter went on reading thirty-two
    ; bytes further ahead and ran whatever was there. It was this picture's first
    ; red, and one of the kind you cannot see: the page kept running, just a
    ; different one.
    phy
    lda tint_s
    pha
    lda #TINT_NEUTRAL
    sta tint_s
    lda f:PICTURE_TONE + 0
    ldx #.loword(table_r)
    jsr channel_table
    lda f:PICTURE_TONE + 1
    ldx #.loword(table_g)
    jsr channel_table
    lda f:PICTURE_TONE + 2
    ldx #.loword(table_b)
    jsr channel_table
    rep #$20
.a16
    lda #.loword(picture_cgram)
    sta tint_ptr
    lda #16
    sta tint_count
    sep #$20
.a8
    lda #^picture_cgram
    sta tint_ptr + 2
    jsr build_palette            ; the sixteen, tinted, in `pal_buf`
    ; And from there to the shadow, **without touching `tint_ready`**:
    ; setting it would send the map's three palettes up on every frame of the
    ; ramp, and that eats the vblank's pose budget.
    ldx #$0000
copy:
    lda pal_buf, x
    sta cgram_shadow + 2 * (128 + 16 * PICTURE_PAL), x
    inx
    cpx #32
    bne copy
    pla
    sta tint_s
    lda #1
    sta f:PICTURE_READY
    jsr restore_tables
    ply
    rts
.endproc

; The picture's objects, if it is shown.
;
; They go **after the timer and before the characters**, which is RM2k's
; order: `Priority_Timer` is 140, `Priority_PictureOld` 120 and
; `Priority_Player` 40. In OAM that is the order of the list, because the
; lowest index wins; and priority 3 puts them in front of both layers.
;
; They cost **twenty-four of the thirty-four tiles per line** on the
; twenty-nine lines they take, so two more characters fit there and no more.
.proc picture_oam
.a8
.i16
    lda f:PICTURE_ACTIVE
    bne has
    rts
has:
    lda #$02
    sta obj_big              ; the picture's objects are 32x32
    lda #0
    sta f:PICTURE_I
each:
    rep #$20
.a16
    lda f:PICTURE_I
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; thirty-two per object
    clc
    adc #PICTURE_X & $FFFF       ; it is negative, and ca65 does not accept a negative immediate
    sta obj_x
    lda #PICTURE_Y
    sta obj_y
    ; And which tile. A 32x32 object reads four tiles from four consecutive
    ; rows of the name grid, which is sixteen wide: so four objects fit in one
    ; row of blocks and the fifth starts 64 tiles further on.
    lda f:PICTURE_I
    and #$0003
    asl a
    asl a                       ; the object's four across
    sta temp
    lda f:PICTURE_I
    and #$00FC
    asl a
    asl a
    asl a
    asl a                       ; and the row of blocks, which is 64 per 4
    clc
    adc temp
    clc
    adc #PICTURE_BASE
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: priority 3 —in front of both layers—, the picture's palette,
    ; and the tile's ninth bit.
    lda temp + 1
    and #$01
    ora #($30 | (PICTURE_PAL * 2))
    sta obj_attr
    jsr emit_object
    lda f:PICTURE_I
    inc a
    sta f:PICTURE_I
    cmp #PICTURE_OBJECTS
    beq leave
    jmp each
leave:
    rts
.endproc
