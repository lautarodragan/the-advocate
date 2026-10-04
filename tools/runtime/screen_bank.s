.segment "FAR"

; --- the screen's bank, also outside bank 0 ---------------------------------
;
; It moved here on 2026-09-13, when `back_from_battle` asked for forty-six
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
; 0; the battle's comes in through the `ba_t_bank` bridge, which is exactly
; the one that sets the data bank to zero before calling.

; The screen's bank, with the screen off: the blank tiles, the blank tilemap,
; the palettes, and the text layer from scratch with every pair of tiles up to
; the BG1 tilemap. Until 2026-10-03 the bank was a font, each letter in two
; cells; the text is composed now —see `text_layer.s`—, and what is left of
; the bank is tile 0, the blank one every cell without text points to, and
; tile 1, which no pair takes.
TL_POOL_WHOLE = (ITEM_BORDER_MAP - SLOT_VRAM) / TL_PAIR_WORDS - 1
.proc items_bank_upload
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #SLOT_VRAM
    sta VMADDL
    lda #(2 * 32)
    sta DAS0L
    lda #.loword(tl_zero)
    sta A1T0L
    sep #$20
.a8
    lda #^tl_zero
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The blank tilemap: the same fixed zero, which is tile 0.
    rep #$20
.a16
    lda #SLOT_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    sep #$20
.a8
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
    rep #$20
.a16
    lda #TL_POOL_WHOLE
    jsl f:tl_reset + FAST
    sep #$20
.a8
    rtl
.endproc

; The battle's: the same bank, but its text takes its pairs from word 0 —BG2
; with its base there— up to the battle's windows, `BA_WIN_VRAM`, and not
; only from `SLOT_VRAM`. In the battle, words 0 to $1FFF belong to nobody:
; they are the map's —its sprites, and in some layouts its tiles or a
; tilemap—, which `back_from_battle` uploads again whole, and the scene's
; tilemap cells below it point to word 0, which has to be blank. That one
; is pair 0, the blank one.
;
; **They are 255.** From 2026-10-04 to later that day they were 447, up to
; the scene's tilemap —a screen with every cell inked—, because the skill
; list over the scene with the party and the commands under it ran out of
; 191 and then of 255 with `letter_spacing` 2. Since the windows went to
; the band below the scene the battle writes far fewer —the description
; and the band's five lines, at most— and the windows' tiles take the rest:
; see `ba_win_load`. The converter says what the busiest lists ask for.
;
; The 64 bytes of word 0 are cleared here because `scene_upload` only
; writes them if the battle has a scene.
TL_BATTLE_VRAM = 0
TL_POOL_BATTLE = (BA_WIN_VRAM - TL_BATTLE_VRAM) / TL_PAIR_WORDS - 1
.assert TL_POOL_BATTLE < TL_PAIRS, error, "the battle's pairs do not fit in the text layer's tables"
.assert BA_WIN_VRAM <= SCENE_MAP && SCENE_MAP <= SLOT_MAP && SCENE_MAP <= SCENE_VRAM, error, "the battle's pairs reach something of the battle's"
.proc battle_bank_upload
.a8
.i16
    jsl f:items_bank_upload
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TL_BATTLE_VRAM
    sta VMADDL
    lda #(TL_PAIR_WORDS * 2)
    sta DAS0L
    lda #.loword(tl_zero)
    sta A1T0L
    sep #$20
.a8
    lda #^tl_zero
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda #TL_POOL_BATTLE
    jsl f:tl_reset + FAST
    sep #$20
.a8
    jsl f:tl_low + FAST
    rtl
.endproc

; The items and equipment screens have their windows' tiles in the same bank,
; at the end: their text has the pairs that come before. See `items_border` in
; `rm2k-snes-screens`.
ITEM_POOL_PAIRS = (ITEM_BORDER_VRAM - SLOT_VRAM) / TL_PAIR_WORDS - 1
.proc items_pool
.a8
.i16
    rep #$20
.a16
    lda #ITEM_POOL_PAIRS
    jsl f:tl_reset + FAST
    sep #$20
.a8
    rts
.endproc


; --- the windows of the item and equipment screens ----------------------------
;
; The only two of the ones using this bank that have windows: the System's
; frame and background, on BG1, behind BG2's text —see `ITEM_WINDOWS` in
; `rm2k-snes-screens` and `EQ_WINDOWS`—. BG1 reads its tiles from the
; same base as BG2, and the windows' tiles go after the font. The tiles and the
; colors are **the same for both** —see the stage's `borders`—; what
; changes is the tilemap.

; The screen's bank and the item windows, with the screen off: it is entered
; with `jsl`, like `items_bank_upload`.
.proc items_screen_upload
.a8
.i16
    jsl f:items_bank_upload
    jsr items_pool
    jsr border_upload
    ; The tilemap: the visible rows, without cursor.
    rep #$20
.a16
    lda #ITEM_BORDER_MAP
    sta VMADDL
    lda #(ITEM_BORDER_ROWS * 64)
    sta DAS0L
    lda #.loword(items_border_map)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_border_map)
    sta A1B0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; The same for the equipment screen, plus the two palettes only it uses: the
; one for the "goes up" color and the red one for the terms, which go right
; after the bank's —they are palettes 2 and 3, which the cells of those
; variants have set—. Without cursor: `eq_bar` paints it every frame.
.proc eq_screen_upload
.a8
.i16
    jsl f:items_bank_upload
    jsr items_pool
    jsr border_upload
    rep #$20
.a16
    lda #ITEM_BORDER_MAP
    sta VMADDL
    lda #(ITEM_BORDER_ROWS * 64)
    sta DAS0L
    lda #.loword(eq_border_map)
    sta A1T0L
    sep #$20
.a8
    lda #^(eq_border_map)
    sta A1B0
    lda #$01
    sta MDMAEN
    lda #ITEMS_CGRAM_N
    sta CGADD
    rep #$20
.a16
    lda #.loword(item_cgram_uploads)
    sta A1T0L
    lda #(2 * 16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^item_cgram_uploads
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
.proc border_upload
.a8
.i16
    ; The colors first, so the channel is left set up for VRAM.
    lda #ITEM_BORDER_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(ITEM_BORDER_COLORS * 2)
    sta DAS0L
    lda #.loword(items_border_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_border_cgram)
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
    lda #ITEM_BORDER_VRAM
    sta VMADDL
    lda #(ITEM_BORDER_TILES * 64)
    sta DAS0L
    lda #.loword(items_border_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_border_tiles)
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
; `slot_ppu_on` plus BG1.
.proc items_ppu_on
.a8
.i16
    lda #(SLOT_VRAM / 4096 * 16 + SLOT_VRAM / 4096)
    ; Both layers from the same base, and it falls through into the next one.
.endproc

; The same, with BG12NBA in A: the shop gives BG1 a base of its own.
.proc screen_ppu_on
.a8
.i16
    sta BG12NBA
    lda #(SLOT_MAP / 1024 * 4)
    sta BG2SC
    lda #(ITEM_BORDER_MAP / 1024 * 4)
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
; row takes: from `items_border_bars`, which has them with the cursor on top,
; or from the tilemap without cursor. A 128-byte DMA, which fits in the vblank
; along with the description. Clobbers X and Y.
.proc items_bar
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
    adc #(ITEM_BORDER_MAP + ITEM_BORDER_LIST * 32)
    tax
    sep #$20
.a8
    lda #$80
    sta VMAIN
    stx VMADDL
    lda temp + 3
    beq erase
    lda #^(items_border_bars)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_border_bars)
    bra font
.a8
erase:
    lda #^(items_border_map)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_border_map + ITEM_BORDER_LIST * 64)
font:
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
