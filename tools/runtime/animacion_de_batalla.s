.segment "CODE"

; --- the battle animation -----------------------------------------------------
;
; `OP_ANIMATION` leaves the timeline here: where the next entry is —in the
; bytecode—, how many are left, and the clock. `animacion_tick` runs once per
; frame before the flashes and fires the tick's entries: a sound effect, a
; screen flash or one on the target event. The animation's drawing is not
; done.
ANIM_PTR   = $7E30E2            ; three bytes
ANIM_N     = $7E30E5
ANIM_T     = $7E30E6

; And the picture's state, fifteen bytes in the same far RAM. **It is not in
; bank 0 because it does not fit there**: the BSS was at 7680 of 7680 and this
; is fifteen bytes more. It lives where the battle animation does and for the
; same reason: it is read and written a few times per frame, so the long
; addressing does not show, and it need not be indexed by anything other than
; the channel.
;
; The tone is **three** bytes and not four: a picture's saturation is always
; the neutral one —`imagen_aceptable` accepts no other— so there is nothing to
; interpolate there and `imagen_paleta` sets `tinte_s` to `TINTE_NEUTRO`.
; **$30E8 to $30EB belong to the MSU-1** —`MSU_HAY`, `MSU_SUENA` and
; `MSU_FACTOR`—, so this starts at $30EC and goes up to $30FA; the next block
; is `FAR_ARAM_DE`, at $3100. It started at $30E8 and overwrote them: the ROM
; stopped detecting the MSU-1 and the title music went silent. No test saw it
; —the suite compares pixels— and taro found it by listening.
FAR_CARTEL    = $7E30EC
CARTEL_ACTIVA = FAR_CARTEL + 0
CARTEL_TONO   = FAR_CARTEL + 1  ; r, g, b, with 100 neutral like the tint
CARTEL_DESDE  = FAR_CARTEL + 4
CARTEL_HASTA  = FAR_CARTEL + 7
CARTEL_PASO   = FAR_CARTEL + 10
CARTEL_PASOS  = FAR_CARTEL + 11
CARTEL_LISTO  = FAR_CARTEL + 12 ; a new palette is waiting for vblank
CARTEL_I      = FAR_CARTEL + 13
CARTEL_CAMBIO = FAR_CARTEL + 14

; And the tail of escapes of whatever text box is open: how many frames are
; left in the `\|` pause and whether it closes by itself when done —the `\^`—.
; `msg_empezar` sets them reading the box's header and `eventos_tick` uses them
; up.
;
; **They go in far RAM for the same reason as the picture**: bank 0 has no
; room. The 7680 bytes of BSS were at 7679 when this was written, that is, one
; byte fit and three are needed. Here there are five spare, left between the
; picture —which ends at $30FA— and `FAR_ARAM_DE`, at $3100. They are read
; once per frame and never indexed, so the long addressing does not show.
FAR_MSG_PAUSA = $7E30FB         ; word: up to PAUSAS_MAX times CUADROS_DE_PAUSA
FAR_MSG_AUTO  = $7E30FD

.proc animacion_limpiar
.a8
.i16
    lda #0
    sta f:ANIM_N
    sta f:ANIMB_ACTIVA          ; and the drawing, which goes on its own
    sta f:ANIMB_SUBIR
    sta f:ANIMB_PAL
    sta f:ANIMB_HAY             ; until `cargar_mapa` says otherwise
    rts
.endproc

.proc animacion_tick
.a8
.i16
    lda f:ANIM_N
    bne hay
    rts
hay:
    ; `cod_ptr` borrowed: the opcode routines read their operands from there,
    ; and whatever page is running needs it back.
    lda cod_ptr + 2
    pha
    rep #$20
.a16
    lda cod_ptr
    pha
    lda f:ANIM_PTR
    sta cod_ptr
    sep #$20
.a8
    lda f:ANIM_PTR + 2
    sta cod_ptr + 2
otra:
    ldy #0
    lda [cod_ptr], y            ; its tick
    cmp f:ANIM_T
    bne listo
    iny
    lda [cod_ptr], y            ; its type
    iny                         ; and the data, from the third byte
    cmp #ANIM_SONIDO
    bne no_sonido
    jsr sonido_de_codigo
    bra hecha
no_sonido:
    cmp #ANIM_DESTELLO
    bne no_destello
    jsr destello_de_codigo
    bra hecha
no_destello:
    jsr flash_empezar           ; the target's
hecha:
    rep #$20
.a16
    lda cod_ptr
    clc
    adc #ANIM_ENTRADA
    sta cod_ptr
    sep #$20
.a8
    lda f:ANIM_N
    dec a
    sta f:ANIM_N
    bne otra
listo:
    rep #$20
.a16
    lda cod_ptr
    sta f:ANIM_PTR
    sep #$20
.a8
    lda f:ANIM_T
    inc a
    sta f:ANIM_T
    rep #$20
.a16
    pla
    sta cod_ptr
    sep #$20
.a8
    pla
    sta cod_ptr + 2
    rts
.endproc

; --- the battle animation's drawing -------------------------------------------
;
; Four 32x32 objects in a 64x64 box, with a sprite palette of their own, and
; **the 2 KB of the current frame uploaded by DMA every two frames**. It is the
; mix of the two precedents: the objects and the palette of their own are the
; picture's, and uploading new drawings in vblank is what the ChipSet's
; animated tiles already do.
;
; Where each pixel lands and what color it is lives in
; `tools/port/animacion.py`, which is the only thing both ends share; nothing
; of that is decided here. There is one box for the whole ROM and what changes
; per map —which tile it lands on and with which palette— comes from
; `anim_batalla_reparto`, one byte per map.
;
; The state lives in far RAM, at $3600, well above the MSU-1's ($30E8), the
; picture's ($30EC to $30FA) and the audio package's tables ($3100 to $35FF):
; on 2026-09-12 an agent overwrote the MSU-1 for not looking at this RAM's
; map.
ANIMB_HAY    = $7E3600          ; this map draws animations
ANIMB_TILE   = $7E3601          ; the box's first tile, word
ANIMB_ATTR   = $7E3603          ; vhoopppN already built for the four objects
ANIMB_VRAM   = $7E3604          ; where the frame's DMA goes, in words
ANIMB_CGADD  = $7E3606          ; its palette's CGRAM entry
ANIMB_SOMBRA = $7E3607          ; and its offset in `cgram_sombra`, word
ANIMB_ACTIVA = $7E3609          ; one is being drawn
ANIMB_FILA   = $7E360A          ; its row in `anim_batalla_tabla`, word
ANIMB_BLANCO = $7E360C          ; what it goes on; $FF is the screen
ANIMB_T      = $7E360D          ; the tick, word
ANIMB_CUADRO = $7E360F          ; the current frame, word
ANIMB_N      = $7E3611          ; how many frames it has, word
ANIMB_SUBIR  = $7E3613          ; a frame is waiting for vblank
ANIMB_PAL    = $7E3614          ; and a palette
ANIMB_I      = $7E3615          ; which of the four objects is being built
ANIMB_PREV   = $7E3616          ; three bytes: the last frame built in
                                ; ANIMB_BUF, with the bank at 0 if none

; This map's layout, when loading it. The byte is 0 —"nothing is drawn here"—
; or bit 7 set with the 64-tile block and the palette, three bits each.
; See `animaciones_asm` in snes_convert.py.
.proc animacion_dibujo_mapa
.a8
.i16
    jsl f:anim_buf_limpiar      ; with the screen off, where it does not show
    lda #0
    sta f:ANIMB_ACTIVA
    sta f:ANIMB_SUBIR
    sta f:ANIMB_PAL
    sta f:ANIMB_HAY
    rep #$20
.a16
    lda mapa_actual
    tax
    sep #$20
.a8
    lda f:anim_batalla_reparto, x
    bne hay
    rts
hay:
    sta f:ANIMB_HAY
    and #$07                    ; the palette
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32: its place in `cgram_sombra`
    rep #$20
.a16
    and #$00FF
    clc
    adc #256                    ; the lower 128 entries, at two bytes
    sta f:ANIMB_SOMBRA
    sep #$20
.a8
    lda temp
    asl a
    asl a
    asl a
    asl a                       ; times 16: its CGRAM entry
    clc
    adc #128
    sta f:ANIMB_CGADD
    lda temp
    asl a
    ora #$30                    ; priority 3: in front of both layers
    sta temp + 1
    lda f:ANIMB_HAY
    lsr a
    lsr a
    lsr a
    and #$07                    ; the 64-tile block
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 64
    sta f:ANIMB_TILE
    ; The tile's ninth bit goes in the attribute, and it is the same for all
    ; four: the box starts at a multiple of 64 and takes twelve name tiles.
    xba
    sep #$20
.a8
    and #$01
    ora temp + 1
    sta f:ANIMB_ATTR
    ; And where the DMA goes: the map's sprite base plus the tile times sixteen
    ; words, which is the size of a 4bpp tile.
    ldx mapa_ofs
    rep #$20
.a16
    lda f:ANIMB_TILE
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x   ; long: `mapa_tabla` lives in RODATA
    sta f:ANIMB_VRAM
    sep #$20
.a8
    rts
.endproc

; Starts drawing animation `temp` on `temp + 1`. `op_animation` calls it, and
; the new one replaces whatever was there, like the timeline. If this map does
; not draw, or the number has no drawing, nothing happens: the sounds and the
; flashes go on the same.
.proc animacion_dibujo_empezar
.a8
.i16
    lda #0
    sta f:ANIMB_ACTIVA
    lda f:ANIMB_HAY
    beq no
    lda temp
    cmp #ANIM_B_MAX
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:anim_batalla_de, x
    cmp #ANIM_B_SIN
    beq no
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times ANIM_B_STRIDE
    sta f:ANIMB_FILA
    tax
    sep #$20
.a8
    lda f:anim_batalla_tabla, x ; how many frames
    rep #$20
.a16
    and #$00FF
    sta f:ANIMB_N
    lda #0
    sta f:ANIMB_T
    lda #$FFFF
    sta f:ANIMB_CUADRO          ; none yet: the first tick uploads 0
    sep #$20
.a8
    lda temp + 1
    sta f:ANIMB_BLANCO
    lda #1
    sta f:ANIMB_ACTIVA
    jmp animacion_dibujo_paleta
no:
    rts
.endproc

; The animation's sixteen colors to the CGRAM shadow, just as they come from
; the cartridge: they are neither tinted nor flashed, which is what RM2k does
; —the map's tone goes to the tilemap, the characters, the panorama and the
; shadows, and not to the animations—. `flush_video` uploads them in vblank.
.proc animacion_dibujo_paleta
.a8
.i16
    rep #$20
.a16
    lda f:ANIMB_FILA
    asl a
    asl a                       ; times 32: sixteen words per animation
    tax
    lda f:ANIMB_SOMBRA
    tay
copia:
    sep #$20
.a8
    lda f:anim_batalla_cgram, x
    sta cgram_sombra, y
    rep #$20
.a16
    inx
    iny
    txa
    and #$001F
    bne copia
    sep #$20
.a8
    lda #1
    sta f:ANIMB_PAL
    rts
.endproc

; One frame of the drawing. It runs once per frame, right after
; `animacion_tick`, and **the frame drawn comes from the tick before advancing
; it**: on tick 0 frame 0 is drawn, which is the same one on which RM2k's
; frame 1 `timing` fires. Two console frames per animation frame, which is
; `BattleAnimation`'s `num_frames = GetRealFrames() * 2`.
.proc animacion_dibujo_tick
.a8
.i16
    lda f:ANIMB_ACTIVA
    bne hay
    rts
hay:
    rep #$20
.a16
    lda f:ANIMB_T
    lsr a
    cmp f:ANIMB_N
    bcc sigue
    sep #$20
.a8
    lda #0
    sta f:ANIMB_ACTIVA
    rts
sigue:
.a16
    cmp f:ANIMB_CUADRO
    beq igual
    sta f:ANIMB_CUADRO
    sep #$20
.a8
    lda #1
    sta f:ANIMB_SUBIR           ; the next vblank sends it to VRAM
    ; And it is built now, out here: the vblank only copies. There is no race
    ; with the DMA because the loop uploads what is pending before calling
    ; this again.
    jsl f:anim_cuadro_armar + RAPIDO   ; from the fast mirror: see MEMSEL
    rep #$20
.a16
igual:
    lda f:ANIMB_T
    inc a
    sta f:ANIMB_T
    sep #$20
.a8
    rts
.endproc

; The 2 KB of the current frame, to VRAM. `flush_video` calls it inside vblank
; and it is taken out of the pose budget, the same as a step of the ChipSet
; animation: four poses out of the five, and only on the animation's even
; frames.
.proc animacion_dibujo_dma
.a8
.i16
    ; From far RAM and not from the cartridge: `anim_cuadro_armar` already
    ; built the frame when the tick chose it.
    rep #$20
.a16
    lda #.loword(ANIMB_BUF)
    sta A1T0L
    lda f:ANIMB_VRAM
    sta VMADDL
    lda #ANIM_B_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #^ANIMB_BUF
    sta A1B0
    lda #$80                    ; a word at a time, incrementing on $2119
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; What it took, in 512-byte poses, subtracted and not set: that way it
    ; adds to whatever the tint or a line of the window already took.
    lda vq_tope
    sec
    sbc #(ANIM_B_BYTES / 512)
    bcc una
    bne queda
una:
    lda #1                      ; there is always room left for one pose
queda:
    sta vq_tope
    rts
.endproc

; The box's four objects, if an animation is being drawn.
;
; They go **after the picture and before the characters**, which is RM2k's
; order: `Priority_Timer` is 140, `Priority_PictureOld` 120,
; `Priority_BattleAnimation` 110 and `Priority_Player` 40. In OAM that is the
; order of the list, because the lowest index wins.
;
; They cost **eight of the thirty-four tiles per line** on the 64 lines they
; take up: two objects four tiles wide on each one.
.proc animacion_dibujo_oam
.a8
.i16
    lda f:ANIMB_ACTIVA
    bne hay
    rts
hay:
    lda f:ANIMB_BLANCO
    cmp #ANIM_B_PANTALLA
    beq pantalla
    ; On the target: the center of its cell and its feet, which is
    ; `GetScreenX()` and `GetScreenY(false)`, minus the camera. The table's
    ; anchor already has `Animation::Position`'s shift baked in.
    cmp #0
    bne evento
    rep #$20
.a16
    lda hero_x
    sta temp
    lda hero_y
    sta temp + 2
    sep #$20
.a8
    bra con_celda
evento:
    dec a                       ; the target is the event index plus one
    jsr npc_de_evento
    cpy #$FFFF
    beq nada                    ; without a row there is nowhere to draw it
    lda npc_buf + 14, y
    bne con_fila
nada:
    rts                         ; no row, or hidden: not drawn
con_fila:
    rep #$20
.a16
    lda npc_buf + 0, y
    sta temp
    lda npc_buf + 2, y
    sta temp + 2
    sep #$20
.a8
con_celda:
    rep #$20
.a16
    lda temp
    clc
    adc #8                      ; the center of the cell
    sec
    sbc pantalla_x
    sta obj_x
    lda temp + 2
    clc
    adc #16                     ; its feet
    sec
    sbc camara_y
    sta obj_y
    bra restar_ancla
pantalla:
.a8
    rep #$20
.a16
    lda #ANIM_B_CENTRO_X
    sta obj_x
    lda #ANIM_B_CENTRO_Y
    sta obj_y
restar_ancla:
    ; The table's anchor, which already has `Animation::Position`'s shift
    ; baked in. The two bytes are read one at a time: the word at +1 carries
    ; X low and Y high.
    lda f:ANIMB_FILA
    tax
    lda f:anim_batalla_tabla + 1, x
    and #$00FF
    sta temp
    lda obj_x
    sec
    sbc temp
    sta temp
    lda f:anim_batalla_tabla + 2, x
    and #$00FF
    sta temp + 2
    lda obj_y
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    lda #$02
    sta obj_grande              ; all four objects are 32x32
    lda f:ANIMB_ATTR
    sta obj_attr
    lda #0
    sta f:ANIMB_I
cada:
    rep #$20
.a16
    lda f:ANIMB_I
    and #$0001
    beq sin_x
    lda temp
    clc
    adc #ANIM_B_OBJ
    bra con_x
sin_x:
    lda temp
con_x:
    sta obj_x
    lda f:ANIMB_I
    and #$0002
    beq sin_y
    lda temp + 2
    clc
    adc #ANIM_B_OBJ
    bra con_y
sin_y:
    lda temp + 2
con_y:
    sta obj_y
    lda f:ANIMB_I
    and #$00FF
    asl a
    asl a                       ; four name tiles per object
    clc
    adc f:ANIMB_TILE
    sep #$20
.a8
    sta obj_tile
    jsr emit_object
    lda f:ANIMB_I
    inc a
    sta f:ANIMB_I
    cmp #ANIM_B_OBJETOS
    bne cada
    rts
.endproc

