.segment "FAR"

; --- the screen's bank, also outside bank 0 ---------------------------------
;
; It moved here on 2026-09-13, when `volver_de_batalla` asked for forty-six
; bytes that bank 0 no longer had: `abl` ended up at 32748 of 32704, and
; before that it had **two** to spare. This is the cheapest one to move of
; everything that measures more than a hundred bytes: it calls nobody —they are
; register writes and four DMAs— so no bridge is needed, and it does not run
; every frame but when opening a screen with the PPU off, so the `jsl`'s extra
; cycle is not noticeable.
;
; What it does require: **it is entered with `jsl` and returns with `rtl`**,
; and the data bank has to remain one where $2100..$21FF is the console,
; because it writes the registers as absolute. The six callers are all in bank
; 0; the battle's comes in through the `bt_t_bank` bridge, which is exactly
; the one that sets the data bank to zero before calling.

; The screen's bank, with the screen off: the font, the blank tilemap and the
; two palettes.
.proc items_banco_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(ITEMS_TILES * 32)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The blank tilemap: a fixed-source DMA from the first tile, which is
    ; transparent.
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$01
    sta MDMAEN
    ; The colors.
    stz CGADD
    rep #$20
.a16
    lda #(ITEMS_CGRAM_N * 2)
    sta DAS0L
    lda #<(items_cgram)
    ora #(>(items_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc


; --- the windows of the item and equipment screens ----------------------------
;
; The only two of the ones using this bank that have windows: the System's
; frame and background, on BG1, behind BG2's text —see `ITEM_VENTANAS` in
; titulo.py and `EQ_VENTANAS` in pantallas.py—. BG1 reads its tiles from the
; same base as BG2, and the windows' tiles go after the font. The tiles and the
; colors are **the same for both** —see `titulo.marcos`—; what changes is the
; tilemap.

; The screen's bank and the item windows, with the screen off: it is entered
; with `jsl`, like `items_banco_subir`.
.proc items_pantalla_subir
.a8
.i16
    jsl f:items_banco_subir
    jsr marco_subir
    ; The tilemap: the visible rows, without cursor.
    rep #$20
.a16
    lda #ITEM_MARCO_MAPA
    sta VMADDL
    lda #(ITEM_MARCO_FILAS * 64)
    sta DAS0L
    lda #.loword(items_marco_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_mapa)
    sta A1B0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; The same for the equipment screen, plus the two palettes only it uses: the
; one for the "goes up" color and the red one for the terms, which go right
; after the bank's —they are palettes 2 and 3, which the cells of those
; variants have set—. Without cursor: `eq_barra` paints it every frame.
.proc eq_pantalla_subir
.a8
.i16
    jsl f:items_banco_subir
    jsr marco_subir
    rep #$20
.a16
    lda #ITEM_MARCO_MAPA
    sta VMADDL
    lda #(ITEM_MARCO_FILAS * 64)
    sta DAS0L
    lda #.loword(eq_marco_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^(eq_marco_mapa)
    sta A1B0
    lda #$01
    sta MDMAEN
    lda #ITEMS_CGRAM_N
    sta CGADD
    rep #$20
.a16
    lda #.loword(item_cgram_sube)
    sta A1T0L
    lda #(2 * 16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^item_cgram_sube
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; The windows' tiles, which are 8bpp, and their colors, after the text's four
; palettes. Leaves channel 0 ready to upload a tilemap: VMAIN, DMAP0 and
; BBAD0.
.proc marco_subir
.a8
.i16
    ; The colors first, so the channel is left set up for VRAM.
    lda #ITEM_MARCO_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(ITEM_MARCO_COLORES * 2)
    sta DAS0L
    lda #.loword(items_marco_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #ITEM_MARCO_VRAM
    sta VMADDL
    lda #(ITEM_MARCO_TILES * 64)
    sta DAS0L
    lda #.loword(items_marco_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; BG2 with the text and BG1 with the windows, and the screen on. It is
; `ranura_ppu_prender` plus BG1.
.proc items_ppu_prender
.a8
.i16
    lda #(RANURA_VRAM / 4096 * 16 + RANURA_VRAM / 4096)
    ; Both layers from the same base, and it falls through into the next one.
.endproc

; The same, with BG12NBA in A: the shop gives BG1 a base of its own.
.proc pantalla_ppu_prender
.a8
.i16
    sta BG12NBA
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(ITEM_MARCO_MAPA / 1024 * 4)
    sta BG1SC
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

; The cursor on row A of the list, which is the System's bar: `temp + 3` at 1
; paints it and at 0 erases it. Both mean copying the two rows of BG1 cells the
; row takes: from `items_marco_barras`, which has them with the cursor on top,
; or from the tilemap without cursor. A 128-byte DMA, which fits in the vblank
; along with the description. Clobbers X and Y.
.proc items_barra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; 128 bytes per list row
    tay
    lsr a                       ; which is 64 words
    clc
    adc #(ITEM_MARCO_MAPA + ITEM_MARCO_LISTA * 32)
    tax
    sep #$20
.a8
    lda #$80
    sta VMAIN
    stx VMADDL
    lda temp + 3
    beq borra
    lda #^(items_marco_barras)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_marco_barras)
    bra fuente
.a8
borra:
    lda #^(items_marco_mapa)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_marco_mapa + ITEM_MARCO_LISTA * 64)
fuente:
    sta A1T0L
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc
