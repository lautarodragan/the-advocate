.segment "CODE"

; --- the ShowPicture picture ------------------------------------------------
;
; Six 32x32 objects with a sprite palette all to themselves, and a fade that is
; a tint of those fifteen colors frame by frame. See `tools/port/imagen.py`,
; which is where it is written where each pixel lands and what color it is,
; and OP_PICTURE in eventos.py.
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
.proc imagen_tick
.a8
.i16
    lda f:CARTEL_ACTIVA
    beq listo
    lda f:CARTEL_PASOS
    beq listo                   ; shown and still
    lda f:CARTEL_PASO
    cmp f:CARTEL_PASOS
    bcs listo                   ; the ramp has already arrived
    lda f:CARTEL_PASO           ; `inc` has no long form
    inc a
    sta f:CARTEL_PASO
    jsr imagen_tono_ahora
    beq listo                   ; the same tone as the previous frame
    jmp imagen_paleta
listo:
    rts
.endproc

; This frame's tone, channel by channel. Leaves in A whether any changed.
;
; The subtraction always goes on the positive side, as in
; `una_tabla_de_destello`: the hardware divider has no sign, and Python's `//`
; rounds the other way with negatives. Both sides do this same computation
; split in two.
.proc imagen_tono_ahora
.a8
.i16
    lda #0
    sta f:CARTEL_CAMBIO
    ldx #$0000
canal:
    lda f:CARTEL_HASTA, x
    cmp f:CARTEL_DESDE, x
    bcc baja
    sec
    sbc f:CARTEL_DESDE, x
    jsr imagen_parte
    clc
    adc f:CARTEL_DESDE, x
    bra guardar
baja:
    lda f:CARTEL_DESDE, x
    sec
    sbc f:CARTEL_HASTA, x
    jsr imagen_parte
    eor #$FF                    ; `desde - parte` without a variable in between:
    sec                         ; ones' complement plus the carry is the minus
    adc f:CARTEL_DESDE, x
guardar:
    cmp f:CARTEL_TONO, x
    beq igual
    sta f:CARTEL_TONO, x
    lda #1
    sta f:CARTEL_CAMBIO
igual:
    inx
    cpx #3
    bne canal
    lda f:CARTEL_CAMBIO
    rts
.endproc

; A = A * CARTEL_PASO / CARTEL_PASOS, with the hardware multiplier and
; divider. The product reaches 200 * 255 and fits in sixteen bits; the
; quotient does not go past 200, so the low byte is enough.
.proc imagen_parte
.a8
.i16
    sta WRMPYA
    lda f:CARTEL_PASO
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
    lda f:CARTEL_PASOS
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
; `cgram_sombra`. `flush_video` uploads them in the vblank with a DMA of its
; own.
;
; It reuses `tabla_canal` and `armar_paleta`, which is what the screen tint
; already did: the only difference is where the three values come from and
; that the picture's saturation is always neutral —`imagen_aceptable` accepts no
; other—, so `tinte_s` is set to neutral while this runs and then given back.
; The three work tables are left with the picture's tint; `restaurar_tablas` puts
; them back as the screen tint's, copying `puro`, which is much cheaper than
; rebuilding them.
.proc imagen_paleta
.a8
.i16
    ; **And Y is saved.** `armar_paleta` uses it as the palette cursor and
    ; leaves it at 32, and whoever calls this from an opcode has it pointing
    ; into the bytecode: without this the interpreter went on reading thirty-two
    ; bytes further ahead and ran whatever was there. It was this picture's first
    ; red, and one of the kind you cannot see: the page kept running, just a
    ; different one.
    phy
    lda tinte_s
    pha
    lda #TINTE_NEUTRO
    sta tinte_s
    lda f:CARTEL_TONO + 0
    ldx #.loword(tabla_r)
    jsr tabla_canal
    lda f:CARTEL_TONO + 1
    ldx #.loword(tabla_g)
    jsr tabla_canal
    lda f:CARTEL_TONO + 2
    ldx #.loword(tabla_b)
    jsr tabla_canal
    rep #$20
.a16
    lda #.loword(imagen_cgram)
    sta tin_ptr
    lda #16
    sta tin_count
    sep #$20
.a8
    lda #^imagen_cgram
    sta tin_ptr + 2
    jsr armar_paleta            ; the sixteen, tinted, in `pal_buf`
    ; And from there to the shadow, **without touching `tinte_listo`**:
    ; setting it would send the map's three palettes up on every frame of the
    ; ramp, and that eats the vblank's pose budget.
    ldx #$0000
copia:
    lda pal_buf, x
    sta cgram_sombra + 2 * (128 + 16 * IMAGEN_PAL), x
    inx
    cpx #32
    bne copia
    pla
    sta tinte_s
    lda #1
    sta f:CARTEL_LISTO
    jsr restaurar_tablas
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
.proc imagen_oam
.a8
.i16
    lda f:CARTEL_ACTIVA
    bne hay
    rts
hay:
    lda #$02
    sta obj_grande              ; the picture's objects are 32x32
    lda #0
    sta f:CARTEL_I
cada:
    rep #$20
.a16
    lda f:CARTEL_I
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; thirty-two per object
    clc
    adc #IMAGEN_X & $FFFF       ; it is negative, and ca65 does not accept a negative immediate
    sta obj_x
    lda #IMAGEN_Y
    sta obj_y
    ; And which tile. A 32x32 object reads four tiles from four consecutive
    ; rows of the name grid, which is sixteen wide: so four objects fit in one
    ; row of blocks and the fifth starts 64 tiles further on.
    lda f:CARTEL_I
    and #$0003
    asl a
    asl a                       ; the object's four across
    sta temp
    lda f:CARTEL_I
    and #$00FC
    asl a
    asl a
    asl a
    asl a                       ; and the row of blocks, which is 64 per 4
    clc
    adc temp
    clc
    adc #IMAGEN_BASE
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: priority 3 —in front of both layers—, the picture's palette,
    ; and the tile's ninth bit.
    lda temp + 1
    and #$01
    ora #($30 | (IMAGEN_PAL * 2))
    sta obj_attr
    jsr emit_object
    lda f:CARTEL_I
    inc a
    sta f:CARTEL_I
    cmp #IMAGEN_OBJETOS
    beq salir
    jmp cada
salir:
    rts
.endproc
