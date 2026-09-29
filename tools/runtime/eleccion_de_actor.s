.segment "FAR"

; --- the actor choice windows ------------------------------------------------
;
; `Scene_ActorTarget` with the System windows on BG1, like items and
; equipment: on the left the medicine's name and "Owned Items" with the count,
; on the right the party, and the red bar over the selected row. The screen is
; still `objetivo_pantalla`, in bank 0, with the menu's bank on BG2; this is
; what it adds, outside bank 0. The geometry and the why are in
; `OBJETIVO_VENTANAS`, in titulo.py, and `render_objetivo` is the reference.
;
; BG1 has **its own base**, `OBJETIVO_VRAM`, behind the menu's tilemap: there
; is no room left in BG2's, because the menu's bank reaches almost up to its
; tilemap. Everything falls in what `load_map` restores when the menu closes
; —`_controlar_objetivo` checks it—, and the colors go in 128..143, which are
; the menu sprites' and are restored by `menu_exp_cerrar`.
;
; `eleg_cancel` says which one: at 0, for the medicine in `eleg_flancos`, with
; the two windows on the left; otherwise, for choosing whom to equip, without
; them. Entered with `jsl`, with the data bank at 0: the registers and
; `item_id` are addressed absolute.

; The windows, and the name and count if it is a medicine. With the screen
; off, after `ranura_banco_subir`.
.proc objetivo_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #OBJETIVO_VRAM
    sta VMADDL
    lda #(OBJETIVO_TILES * 64)
    sta DAS0L
    lda #.loword(objetivo_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The tilemap, which is a single one: the one with an item. Without an
    ; item, the cells of the two left windows are erased —see
    ; `objetivo_compacto`—.
    rep #$20
.a16
    lda #OBJETIVO_MAPA
    sta VMADDL
    lda #(32 * 28 * 2)
    sta DAS0L
    lda #.loword(objetivo_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_mapa)
    sta A1B0
    lda #$01
    sta MDMAEN
    lda eleg_cancel
    beq colores
    rep #$20
.a16
    lda #OBJETIVO_MAPA
borrar_fila:
    sta VMADDL
    ldx #OBJETIVO_BORRAR_COLS
borrar_celda:
    stz VMDATAL                 ; both halves of the word: 16-bit A
    dex
    bne borrar_celda
    clc
    adc #32
    cmp #(OBJETIVO_MAPA + OBJETIVO_BORRAR_FILAS * 32)
    bcc borrar_fila
    sep #$20
.a8
colores:
    ; The colors.
    lda #OBJETIVO_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(OBJETIVO_COLORES * 2)
    sta DAS0L
    lda #.loword(objetivo_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda eleg_cancel
    beq nombre
    rtl
nombre:
    ; The two lines of the name: `objetivo_nombres` has
    ; 2 * OBJETIVO_NOMBRE_ANCHO letters per medicine, and `objetivo_nombre_de`
    ; says which one belongs to `k`.
    rep #$20
.a16
    lda eleg_flancos
    and #$00FF
    tax
    lda f:objetivo_nombre_de, x
    and #$00FF
    sta temp
    asl a
    asl a
    clc
    adc temp                    ; k * 5
    asl a
    asl a
    clc
    adc temp                    ; k * 21
    clc
    adc temp                    ; k * 22
    .assert OBJETIVO_NOMBRE_ANCHO = 11, error, "the name is indexed by k * 22"
    tax
    ldy #OBJETIVO_NOMBRE_VRAM
    jsr renglon
    rep #$20
.a16
    txa
    clc
    adc #OBJETIVO_NOMBRE_ANCHO
    tax
    ldy #(OBJETIVO_NOMBRE_VRAM + 64)
    jsr renglon
    jmp objetivo_cuantos

; One line: X its first letter in `objetivo_nombres`, Y the cell. The top
; cells of all the letters and then the bottom ones, like
; `ranura_texto_escribir`. Leaves X as it was and returns with an 8-bit A.
renglon:
    sep #$20
.a8
    sty VMADDL
    stz temp + 2                ; the top cells
    stz temp + 3
    jsr pasada
    rep #$20
.a16
    tya
    clc
    adc #32                     ; and the bottom ones
    sta VMADDL
    sep #$20
.a8
    lda #2
    sta temp + 2
pasada:
    phx
    lda #OBJETIVO_NOMBRE_ANCHO
    sta temp
letra:
    lda f:objetivo_nombres, x
    phx
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; four bytes per glyph
    clc
    adc temp + 2
    tax
    lda f:ranura_glifo_celdas, x
    sta VMDATAL
    sep #$20
.a8
    plx
    inx
    dec temp
    bne letra
    plx
    rts
.endproc

; How many are left of the medicine in `eleg_flancos`, in two digits —the tens
; digit blank if it is zero—, next to "Owned Items". In the vblank after using
; it, or with the screen off when opening. Without a medicine, nothing.
.proc objetivo_cuantos
.a8
.i16
    lda eleg_cancel
    beq medicina
    rtl
medicina:
    rep #$20
.a16
    lda eleg_flancos
    and #$00FF
    asl a
    tax
    lda item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    ldx #0
diez:
    cmp #10
    bcc unidades
    sbc #10
    inx
    bra diez
unidades:
    sta temp + 1                ; the units
    txa
    sta temp                    ; and the tens
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #OBJETIVO_CUANTOS_VRAM
    sta VMADDL
    sep #$20
.a8
    stz temp + 2                ; the top cells
    jsr dos
    rep #$20
.a16
    lda #(OBJETIVO_CUANTOS_VRAM + 32)
    sta VMADDL
    sep #$20
.a8
    lda #2                      ; and the bottom ones
    sta temp + 2
    jsr dos
    rtl

dos:
    lda temp
    beq blanco
    clc
    adc #('0' - ITEM_PRIMER_CARACTER)
blanco:                         ; the space is the first glyph
    jsr glifo
    lda temp + 1
    clc
    adc #('0' - ITEM_PRIMER_CARACTER)
glifo:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    clc
    adc temp + 2
    and #$00FF                  ; `temp + 3` is not part of the offset
    tax
    lda f:ranura_glifo_celdas, x
    sta VMDATAL
    sep #$20
.a8
    rts
.endproc

; The bar on party row A: `temp + 3` at 1 paints it and at 0 erases it. Both
; are a copy of the BG1 rectangle where the bar changes something
; —`OBJETIVO_BARRA_FILAS` by `OBJETIVO_BARRA_COLS` cells, see
; `objetivo_compacto`—: from `objetivo_barras`, which has it with the bar, or
; from the tilemap. One DMA per row of cells, which fit in the vblank with the
; erasing one and the painting one. With an item or without it is the same:
; the rectangle does not touch the left windows. It clobbers `temp` through
; `temp + 3`: the caller sets `temp + 3` again before each time.
BARRA_BYTES = OBJETIVO_BARRA_FILAS * OBJETIVO_BARRA_COLS * 2
.proc objetivo_barra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:fila_vram, x          ; the rectangle's first cell
    sta temp                    ; `temp` and `temp + 1`
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda temp + 3
    beq borra
    lda #^(objetivo_barras)
    sta A1B0
    rep #$20
.a16
    lda f:barra_ofs, x
    clc
    adc #.loword(objetivo_barras)
    ldy #(OBJETIVO_BARRA_COLS * 2) ; the rectangle is contiguous
    bra filas
.a8
borra:
    lda #^(objetivo_mapa)
    sta A1B0
    rep #$20
.a16
    lda temp
    sec
    sbc #OBJETIVO_MAPA
    asl a                       ; from VRAM words to tilemap bytes
    clc
    adc #.loword(objetivo_mapa)
    ldy #64                     ; a whole tilemap row
filas:
    sty temp + 2                ; how much the source advances per row
    ldx #OBJETIVO_BARRA_FILAS
fila:
    sta A1T0L
    pha
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda #(OBJETIVO_BARRA_COLS * 2)
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    dex
    bne fila
    sep #$20
.a8
    rtl

PRIMERA = OBJETIVO_MAPA + OBJETIVO_BARRA_FILA0 * 32 + OBJETIVO_BARRA_COL0
FILA = MENU_ACTOR_FILAS * 32
fila_vram:
    .word PRIMERA, PRIMERA + FILA, PRIMERA + 2 * FILA, PRIMERA + 3 * FILA
barra_ofs:
    .word 0, BARRA_BYTES, 2 * BARRA_BYTES, 3 * BARRA_BYTES
    .assert MENU_FILAS_GRUPO = 4, error, "one word per party row"
.endproc

; BG2 with the party and BG1 with the windows, each with its own base, and the
; screen on. It is `ranura_ppu_prender` plus BG1.
.proc objetivo_ppu_prender
.a8
.i16
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(OBJETIVO_MAPA / 1024 * 4)
    sta BG1SC
    lda #(RANURA_VRAM / 4096 * 16 + OBJETIVO_VRAM / 4096)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    stz BG1HOFS
    stz BG1HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    sta BG1VOFS
    sta BG1VOFS
    lda #$03
    sta TM
    lda #$0F
    sta INIDISP
    rtl
.endproc
