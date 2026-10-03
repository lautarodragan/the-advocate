.segment "FAR"

; --- the actor choice windows ------------------------------------------------
;
; `Scene_ActorTarget` with the System windows on BG1, like items and
; equipment: on the left the medicine's name and "Owned Items" with the count,
; on the right the party, and the red bar over the selected row. The screen is
; still `target_screen`, in bank 0, with the menu's bank on BG2; this is
; what it adds, outside bank 0. The geometry and the why are in
; `TARGET_WINDOWS` of `rm2k-snes-screens`, whose `render` is the reference.
;
; BG1 has **its own base**, `TARGET_VRAM`, behind the menu's tilemap: there
; is no room left in BG2's, because the menu's bank reaches almost up to its
; tilemap. Everything falls in what `load_map` restores when the menu closes
; —`_check_target` checks it—, and the colors go in 128..143, which are
; the menu sprites' and are restored by `menu_exp_close`.
;
; It only opens for a medicine, the one in `pick_edges`: whom to equip is
; chosen on the pause menu itself —`menu_choose`, below—. Entered with
; `jsl`, with the data bank at 0: the registers are addressed absolute.

; The windows, and the medicine's name and count. With the screen off,
; after `slot_bank_upload`. The name goes in two lines, each composed in
; the menu's bank like the actors' names; the count, one digit per cell.
.proc target_upload
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TARGET_VRAM
    sta VMADDL
    lda #(TARGET_TILES * 64)
    sta DAS0L
    lda #.loword(target_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(target_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The tilemap.
    rep #$20
.a16
    lda #TARGET_MAP
    sta VMADDL
    lda #(32 * 28 * 2)
    sta DAS0L
    lda #.loword(target_map)
    sta A1T0L
    sep #$20
.a8
    lda #^(target_map)
    sta A1B0
    lda #$01
    sta MDMAEN
    ; The colors.
    lda #TARGET_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(TARGET_COLORS * 2)
    sta DAS0L
    lda #.loword(target_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(target_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The two lines of the name: `target_names` has
    ; 2 * TARGET_NAME_WIDTH letters per medicine, and `target_name`
    ; says which one belongs to `k`.
    rep #$20
.a16
    lda pick_edges
    and #$00FF
    tax
    lda f:target_name, x
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
    .assert TARGET_NAME_WIDTH = 11, error, "the name is indexed by k * 22"
    ; Each line composed —see `tl_strip`—, from where it starts in the table.
    clc
    adc #.loword(target_names)
    sta msg_ptr
    sep #$20
.a8
    lda #^target_names
    sta msg_ptr + 2
    lda #TARGET_NAME_WIDTH
    ldy #TARGET_NAME_VRAM
    jsl f:tl_strip + FAST
    rep #$20
.a16
    lda msg_ptr
    clc
    adc #TARGET_NAME_WIDTH
    sta msg_ptr
    sep #$20
.a8
    lda #TARGET_NAME_WIDTH
    ldy #(TARGET_NAME_VRAM + 64)
    jsl f:tl_strip + FAST
    jmp target_count
.endproc

; How many are left of the medicine in `pick_edges`, in two digits —the tens
; digit blank if it is zero—, next to "Owned Items". In the vblank after using
; it, or with the screen off when opening. Without a medicine, nothing.
.proc target_count
.a8
.i16
    rep #$20
.a16
    lda pick_edges
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    ldx #0
ten:
    cmp #10
    bcc units
    sbc #10
    inx
    bra ten
units:
    sta temp + 1                ; the units
    txa
    sta temp                    ; and the tens
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TARGET_COUNT_VRAM
    sta VMADDL
    sep #$20
.a8
    stz temp + 2                ; the top cells
    jsr two
    rep #$20
.a16
    lda #(TARGET_COUNT_VRAM + 32)
    sta VMADDL
    sep #$20
.a8
    lda #2                      ; and the bottom ones
    sta temp + 2
    jsr two
    rtl

two:
    lda temp
    beq target
    clc
    adc #('0' - ITEM_FIRST_CHAR)
target:                         ; the space is the first glyph
    jsr glyph
    lda temp + 1
    clc
    adc #('0' - ITEM_FIRST_CHAR)
glyph:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    clc
    adc temp + 2
    and #$00FF                  ; `temp + 3` is not part of the offset
    tax
    lda f:slot_glyph_cells, x
    sta VMDATAL
    sep #$20
.a8
    rts
.endproc

; The bar on party row A: `temp + 3` at 1 paints it and at 0 erases it. Both
; are a copy of the BG1 rectangle where the bar changes something
; —`TARGET_BAR_ROWS` by `TARGET_BAR_COLS` cells, see
; `compact_target`—: from `target_bars`, which has it with the bar, or
; from the tilemap. One DMA per row of cells, which fit in the vblank with the
; erasing one and the painting one. It clobbers `temp` through `temp + 3`:
; the caller sets `temp + 3` again before each time.
BAR_BYTES = TARGET_BAR_ROWS * TARGET_BAR_COLS * 2
.proc target_bar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:row_vram, x           ; the rectangle's first cell
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
    beq erase
    lda #^(target_bars)
    sta A1B0
    rep #$20
.a16
    lda f:bar_ofs, x
    clc
    adc #.loword(target_bars)
    ldy #(TARGET_BAR_COLS * 2) ; the rectangle is contiguous
    bra rows
.a8
erase:
    lda #^(target_map)
    sta A1B0
    rep #$20
.a16
    lda temp
    sec
    sbc #TARGET_MAP
    asl a                       ; from VRAM words to tilemap bytes
    clc
    adc #.loword(target_map)
    ldy #64                     ; a whole tilemap row
rows:
    sty temp + 2                ; how much the source advances per row
    ldx #TARGET_BAR_ROWS
row:
    sta A1T0L
    pha
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda #(TARGET_BAR_COLS * 2)
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
    bne row
    sep #$20
.a8
    rtl

FIRST = TARGET_MAP + TARGET_BAR_ROW0 * 32 + TARGET_BAR_COL0
ROW = MENU_ACTOR_ROWS * 32
row_vram:
    .word FIRST, FIRST + ROW, FIRST + 2 * ROW, FIRST + 3 * ROW
bar_ofs:
    .word 0, BAR_BYTES, 2 * BAR_BYTES, 3 * BAR_BYTES
    .assert MENU_ROWS_PARTY = 4, error, "one word per party row"
.endproc

; BG2 with the party and BG1 with the windows, each with its own base, and the
; screen on. It is `slot_ppu_on` plus BG1.
.proc target_ppu_on
.a8
.i16
    lda #(SLOT_MAP / 1024 * 4)
    sta BG2SC
    lda #(TARGET_MAP / 1024 * 4)
    sta BG1SC
    lda #(SLOT_VRAM / 4096 * 16 + TARGET_VRAM / 4096)
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

; --- the bar on the pause menu -----------------------------------------------
;
; `Scene_Menu` chooses whom a command is for over its own party panel: the
; commands stay on the left with their cursor, and the red bar goes over
; the row's text —`UpdateActorSelection`—. It is the actor choice's bar,
; with its tiles and colours, but over nothing: the menu has no windows, so
; outside the bar BG1 is empty and erasing it is writing zeros. The geometry
; is `MENU_BAR` of `rm2k-snes-screens`, whose `render` of the menu is the
; reference.
;
; Its colours go in 128..143, the sprites' palette 0: that is why the
; menu's experience goes in palette 1 —see `menu_exp_paint`—. Everything is
; in what `load_map` and `menu_exp_close` restore when the menu closes, as
; with the actor choice.

; The tiles, the colours and an empty BG1, from `menu_upload`: with the
; screen off. BG1 is turned on by `menu_exp_paint`, with the rest.
.proc menu_bar_upload
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TARGET_VRAM
    sta VMADDL
    lda #(TARGET_TILES * 64)
    sta DAS0L
    lda #.loword(target_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(target_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; The tilemap, all zeros: a fixed source —`zero`, in `bank1.s`— writes
    ; the same byte to both halves of each word.
    rep #$20
.a16
    lda #TARGET_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #.loword(zero)
    sta A1T0L
    sep #$20
.a8
    lda #^zero
    sta A1B0
    lda #$09
    sta DMAP0
    lda #$01
    sta MDMAEN
    lda #TARGET_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(TARGET_COLORS * 2)
    sta DAS0L
    lda #.loword(target_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(target_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #(TARGET_MAP / 1024 * 4)
    sta BG1SC
    stz BG1HOFS
    stz BG1HOFS
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    rtl
.endproc

; The bar on party row A: `temp + 3` at 1 paints it and at 0 erases it. One
; DMA per row of cells, like `target_bar`, which fits in the vblank. It
; clobbers `temp` through `temp + 2`.
.proc menu_bar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:row_vram, x           ; the rectangle's first cell
    sta temp
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #$18
    sta BBAD0
    lda temp + 3
    beq erase
    lda #$01
    sta DMAP0
    lda #^(menu_bar_cells)
    sta A1B0
    rep #$20
.a16
    lda #.loword(menu_bar_cells)
    ldy #(MENU_BAR_COLS * 2)    ; the rectangle is contiguous
    bra rows
.a8
erase:
    lda #$09                    ; a fixed source: zeros
    sta DMAP0
    lda #^zero
    sta A1B0
    rep #$20
.a16
    lda #.loword(zero)
    ldy #0
rows:
    sty temp + 2                ; how much the source advances per row
    ldx #MENU_BAR_ROWS
row:
    sta A1T0L
    pha
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda #(MENU_BAR_COLS * 2)
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
    bne row
    sep #$20
.a8
    rtl

FIRST = TARGET_MAP + MENU_BAR_ROW0 * 32 + MENU_BAR_COL0
ROW = MENU_ACTOR_ROWS * 32
row_vram:
    .word FIRST, FIRST + ROW, FIRST + 2 * ROW, FIRST + 3 * ROW
    .assert MENU_ROWS_PARTY = 4, error, "one word per party row"
.endproc

; --- whom a command is for ---------------------------------------------------
;
; `Scene_Menu::UpdateActorSelection`: the menu stays as it is, with the
; cursor on the command, and the bar goes over the party panel —see
; `menu_bar`—, always starting on the first row. Up and down wrap around,
; like any `Window_Selectable`. Returns with the row in A, or $FF if B was
; pressed, with the bar erased. Called with `jsl` and the data bank at 0,
; just after `read_pad`, still inside the vblank; `title_sel` is the row
; while it lasts: the caller puts the command back. It lives here and not
; next to the menu because bank 0 has no room for it.
;
; Confirmed against the RPG_RT of 2015 under Wine and easyrpg's
; `scene_menu.cpp`: see the task `a-quien-equipar-desde-el-menu`.
.proc menu_choose
.a8
.i16
    stz title_sel
    lda #1
    sta temp + 3
    lda #0
    jsl f:menu_bar
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_up
    lda title_sel
    bne up
    jsr rows_n                  ; from the first, up wraps around
up:
    dec a
    jsr move
    bra wait
no_up:
    lda title_edges
    and #PAD_DOWN
    beq no_down
    jsr rows_n
    dec a
    cmp title_sel
    beq first                   ; from the last, down wraps around
    lda title_sel
    inc a
    bra down
first:
    lda #0
down:
    jsr move
    bra wait
no_down:
    lda title_edges
    and #PAD_B
    beq no_b
    stz temp + 3
    lda title_sel
    jsl f:menu_bar
    lda #$FF                    ; B: nothing chosen
    rtl
no_b:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                    ; it was already held: not an edge
    lda title_sel
    rtl

; How many rows the panel shows, in A.
rows_n:
    lda party_n
    cmp #MENU_ROWS_PARTY
    bcc rows_ready
    lda #MENU_ROWS_PARTY
rows_ready:
    rts

; The bar from the row it was on to the one in A.
move:
    pha
    stz temp + 3
    lda title_sel
    jsl f:menu_bar
    pla
    sta title_sel
    lda #1
    sta temp + 3
    lda title_sel
    jsl f:menu_bar
    rts
.endproc
