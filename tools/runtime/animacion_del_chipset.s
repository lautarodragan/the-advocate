.segment "CODE"

; --- ChipSet animation -----------------------------------------------------
;
; Two animations that run at once and at different rates: the water
; autotiles, which change every AGUA_CUADROS and go through the cycle 0,1,2,1,
; and the "animated tiles", which change every ANIMADO_CUADROS and cycle
; through four.
;
; Animating is **overwriting the data of a few tiles in VRAM**; the tilemap is
; not touched. The converter puts the ones that change in a contiguous run at
; the end of the map's bank, sharing none with the still cells, so one step is
; a single DMA: between 128 and 1664 bytes depending on the map. See `convert`
; in tools/port/snes_convert.py.
;
; **It does not store where it is and reads nothing from the cartridge to
; decide**, and both things were mandatory, not elegance: the BSS was at 7680
; of 7680 and the direct page at 255 of 256, so there was nowhere to put
; either a counter or a pointer for `lda [puntero], y`. Where in the cycle each
; family is comes from dividing `vueltas` —minus `vueltas_congeladas`, the
; fade's ticks— by its rate with the hardware divider; where its tiles and its
; drawings are comes from `anim_tabla`, which the converter builds.
;
; The remainder of that division also says **whether this tick is the one
; where it changes**, which is the only thing to ask to know whether the DMA is
; needed.
;
; The water cycle: four steps, and the fourth draws the second again. It is
; easyrpg's `animation_step_ab`, tilemap_layer.cpp:289, with `animation_type`
; at 0, which is the default and what every ChipSet in this game has.
; Three drawings in four steps, with the fourth repeating the second. Both
; animations there are use it: the ChipSet's water —easyrpg's
; `animation_step_ab`— and a character's walk cycle, which has three columns
; and draws column 1 when the step is 3. It is `CYCLE_OF_THREE` in
; tools/rpgmaker/rm2k.py.
cycle_three:
    .byte 0, 1, 2, 1

; How far the hero advances per frame according to its speed, in **half
; units** of RM2k: RM2k counts 256 per cell and advances `1 << (1 + speed)`,
; that is 4, 8, 16, 32, 64 and 128 —`PASO_POR_VELOCIDAD` in eventos.py—, and
; here `step_left` is a byte, so it counts by twos: 128 per cell and half of
; each step. The pixels left are `step_left >> 3`: integer division drops the
; sixteenths, and at the speeds with half a pixel per frame that is the same as
; counting the frames by two.
half_step_per_speed:
    .byte 2, 4, 8, 16, 32, 64
; And every how many frames the walk frame changes:
; `GetStationaryAnimFrames`, the same numbers as `anim_idle`.
anim_per_speed:
    .byte 12, 10, 8, 6, 5, 4

; Leaves in X the entry of family Y inside `anim_tabla`. Which map it is comes
; from `mapa_ofs` without storing anything: both strides are powers of two.
.proc anim_where
.a8
.i16
    rep #$20
.a16
    lda mapa_ofs
    lsr a
    lsr a
    lsr a
.assert MAPA_STRIDE = 128, error, "the three divisions above are MAPA_STRIDE/ANIM_STRIDE"
.assert ANIM_STRIDE = 16, error, "same"
    sta temp
    tya
    asl a
    asl a
    asl a
.assert ANIM_FAM_STRIDE = 8, error, "the three multiplications are ANIM_FAM_STRIDE"
    clc
    adc temp
    tax
    sep #$20
.a8
    rts
.endproc

; Which drawing family Y gets on the tick given in X. Returns the drawing in A
; and in `temp + 3` a 1 if **this** tick is the one where it changes, that is,
; if the clock landed right on the edge.
;
; The tick is `vueltas`. Since it is sixteen bits, every 65536 ticks
; —eighteen minutes— it wraps around and the cycle skips a drawing; RM2k
; counts in thirty-two. What is lost is declared in
; workflow/divergencias/el-chipset-se-saltea-un-dibujo-cada-18-minutos.md.
.proc anim_advance
.a8
.i16
    rep #$20
.a16
    txa
    sta WRDIVL                  ; the dividend, in a single 16-bit write
    sep #$20
.a8
    lda #AGUA_CUADROS
    cpy #$0000
    beq divisor
    lda #ANIMADO_CUADROS
divisor:
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    stz temp + 3
    lda RDMPYL                  ; the remainder: zero is the tick of the change
    ora RDMPYL + 1
    bne no_cambia
    inc temp + 3
no_cambia:
    lda RDDIVL
    and #(AGUA_CICLO_N - 1)
.assert AGUA_CICLO_N = 4, error, "the cycle is trimmed with a two-bit and"
.assert ANIMADO_PASOS = 4, error, "and both cycles have the same length"
    cpy #$0000
    bne ready                   ; the animated tiles just wrap around
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda cycle_three, x
    plx
ready:
    rts
.endproc

; The DMA of one family: X its entry in `anim_tabla` and Y the drawing. The DMA
; mode is left set by the caller, which always asks for the same one.
.proc anim_upload
.a8
.i16
    pha                         ; the drawing, which the arithmetic below
                                ; overwrites
    lda f:anim_tabla + 6, x
    bne hay
    pla
    rts                         ; this family does not animate on this map
hay:
    rep #$20
.a16
    lda f:anim_tabla + 0, x
    sta VMADDL
    lda f:anim_tabla + 4, x
    sta DAS0L
    sta temp                    ; how big one drawing is
    lda f:anim_tabla + 2, x
    sta temp + 2                ; and where drawing 0 is, inside the block
    sep #$20
.a8
    ; The drawing is widened here and not in the caller: `ldy` with wide X and
    ; Y takes the next byte along, and that has already cost an afternoon
    ; twice —see `anim_tick`—. With `and #$00FF` on the wide accumulator, the
    ; high byte ends up zero wherever it comes from.
    pla
    rep #$20
.a16
    and #$00FF
    tay
saltar:
    cpy #$0000
    beq puesto
    lda temp + 2
    clc
    adc temp
    sta temp + 2
    dey
    bra saltar
puesto:
    ; The drawings are in WRAM, where `lz2_anim` left them when loading the
    ; map: the cartridge carries them compressed.
    lda #.loword(ANIM_DIBUJOS)
    clc
    adc temp + 2
    sta A1T0L
    sep #$20
.a8
    lda #^ANIM_DIBUJOS
    sta A1B0
    lda #$01
    sta MDMAEN
    rts
.endproc

; The DMA mode the two below ask for: background tiles to VRAM.
.proc anim_mode
.a8
.i16
    lda #$80
    sta VMAIN                   ; advance one word after the high byte
    lda #$01
    sta DMAP0                   ; two registers, by words
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    rts
.endproc

; Both families, right now and with no budget: it is what `load_map` does, with
; the screen off. The new map brings drawing 0 of each run in VRAM and the
; clock may be at any other, because it belongs to the saved game and not to
; the map.
.proc anim_load
.a8
.i16
    stz anim_pend               ; whatever was pending gets uploaded here
    jsr anim_mode
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; the animations' clock: see there
    tax
    sep #$20
.a8
    jsr anim_advance               ; Y is still the family
    ply
    phy
    pha
    jsr anim_where
    pla
    jsr anim_upload
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; What to upload in the coming vblank, decided in the body of the loop.
;
; It goes **after** the `inc vueltas`, so the tick it looks at is that of the
; next tick, which is the one that will show the drawing. That it is that one
; and not the previous one is measured, not reasoned: see `anim_flush`.
.proc anim_tick
.a8
.i16
    stz anim_pend
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; the animations' clock: see there
    tax
    sep #$20
.a8
    jsr anim_advance
    inc a                       ; the drawing, plus one: zero is "nothing"
    sta temp + 2
    ; And whether this tick is the one where it changes. It is checked with
    ; the accumulator in eight bits and not with `ldx`: with wide X the read
    ; also takes `temp + 4`, which is the low byte of `hero_x`, and then every
    ; tick looks like the one of the change. Uploading the drawing that is
    ; already uploaded does not show, so the bug survives the pixel
    ; comparison; what shows is the pose budget going down every frame.
    lda temp + 3
    beq siguiente
    ply
    phy
    jsr anim_where
    lda f:anim_tabla + 6, x
    beq siguiente               ; this family does not animate on this map
    lda temp + 2
    cpy #$0000
    beq baja
    asl a
    asl a
    asl a                       ; three bits per family
.assert ANIM_FAMILIAS = 2, error, "the two nibbles of anim_pend fit in a byte"
baja:
    ora anim_pend
    sta anim_pend
siguiente:
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; The step that is due, in the vblank, and only on the tick where it changes.
;
; The tick looked at is `vueltas` as is, without correcting anything for the
; frame the video lags behind. It is measured, not reasoned: with
; `vueltas - 1` the test suite goes red on **one tick in every 24** —the one of
; the change— and on no other, which is 32% of the screen on map 5. The case
; that catches it is `snes-caminando 5 left` with advance 46, that is, exactly
; tick 24.
;
; What it uploads is subtracted from the pose budget instead of setting it, so
; that it adds to whatever the tint or a line of the window already took.
.proc anim_flush
.a8
.i16
    lda anim_pend
    bne hay
    rts                         ; the usual case: an lda and a beq
hay:
    jsr anim_mode
    ldy #$0000
otra:
    ; This family's three bits, read from `anim_pend` on each pass and not
    ; from a copy in `temp`: `anim_upload` stores a word there and used to wipe
    ; out the copy. When both families changed on the same tick —every 24,
    ; which is a multiple of 6— the second was lost and kept the old drawing
    ; until the next change. It showed in 8 pixels of map 2.
    lda anim_pend
    cpy #$0000
    beq baja
    lsr a
    lsr a
    lsr a
baja:
    and #$07
    beq siguiente
    dec a                       ; the drawing `anim_tick` asked for
    phy
    pha
    jsr anim_where
    pla
    jsr anim_upload
    ; What it took, in poses: a pose is 512 bytes and a background tile 64.
    ; It is subtracted from the budget instead of setting it, so that it adds
    ; to whatever the tint or a line of the window already took.
    lda f:anim_tabla + 6, x
    lsr a
    lsr a
    lsr a
.assert BYTES_POR_TILE = 64, error, "eight background tiles fit in a 512-byte pose"
    inc a
    sta temp + 2
    lda vq_tope
    sec
    sbc temp + 2
    bcc una
    bne queda
una:
    lda #1                      ; there is always room for one pose
queda:
    sta vq_tope
    ply
siguiente:
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    stz anim_pend
    rts
.endproc
