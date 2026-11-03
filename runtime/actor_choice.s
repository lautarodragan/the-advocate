.segment "FAR"

; --- the actor choice windows ------------------------------------------------
;
; `Scene_ActorTarget` with the System window on BG1, like items and
; equipment: on top the medicine's name and "Owned Items" with the count, in
; one line, below it the party the whole width, and the red bar over the
; selected row. The screen is still `target_screen`, in bank 0, with the
; menu's bank on BG2; this is what it adds, outside bank 0. The geometry and
; the why are in `TARGET_WINDOWS` of `rm2k-snes-screens`, whose `render` is
; the reference. Until 2026-11-02 the name and the count were two windows on
; the left and the party a window on the right, which at 256 wide did not
; fit.
;
; BG1 has **its own base**, `TARGET_VRAM`, behind the menu's tilemap: there
; is no room left in BG2's, because the menu's bank reaches almost up to its
; tilemap. Everything falls in what `load_map` restores when the menu closes
; —`_check_target` checks it—, and the colors go in 128..143, which are
; the menu sprites' and are restored by `menu_exp_close`.
;
; It opens for a medicine, the one in `item_sel`, and for a heal from the
; skills screen —`sk_target_on`, see `sk_heal`—, which is the same screen
; with the skill's name, the cost's term and its cost, and the bar where the
; skill's scope says. Whom to equip is chosen on the pause menu itself
; —`menu_choose`, in `menu_list.s`—. Entered with `jsl`, with the data bank
; at 0: the registers are addressed absolute.

; The windows, and the medicine's name and count. With the screen off,
; after `slot_bank_upload`. The name is composed in the menu's bank like
; the actors' names; the count, one digit per cell.
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
    lda f:sk_target_on
    beq medicine
    jmp target_skill_upload
medicine:
    ; The name, on the line on top: `target_names` has TARGET_NAME_WIDTH
    ; letters per medicine, and `target_name` says which one belongs to
    ; `k`. Composed —see `tl_strip`— like the actors' names.
    rep #$20
.a16
    ldx item_sel
    lda f:target_name, x
    jsr target_name_ofs
    adc #.loword(target_names)
    sta msg_ptr
    sep #$20
.a8
    lda #^target_names
    sta msg_ptr + 2
    jsr target_name_strip
    jmp target_count
.endproc

; A16: the name `k` in A's low byte, its offset in a table of names of
; TARGET_NAME_WIDTH letters, with the multiplier. Leaves the carry at zero,
; for the `adc` of the table's start. With the data bank at 0.
.a16
.proc target_name_ofs
    sep #$20
.a8
    sta WRMPYA
    lda #TARGET_NAME_WIDTH
    sta WRMPYB                  ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    rts
.endproc
.a8

; The name at `msg_ptr` composed on the line on top. With the screen off.
.proc target_name_strip
.a8
.i16
    lda #TARGET_NAME_WIDTH
    ldy #TARGET_NAME_VRAM
    jsl f:tl_strip + FAST
    rts
.endproc

; How many are left of the medicine in `item_sel`, in two digits —the tens
; digit blank if it is zero—, next to "Owned Items". In the vblank after using
; it, or with the screen off when opening. Without a medicine, nothing.
.proc target_count
.a8
.i16
    ; On the party every row's HP, which a skill changed —or a special item
    ; that casts one—: see `target_scope`.
    jsr target_party_hp
    lda f:sk_target_on
    beq item
    ; A skill: its cost.
    lda f:sk_used
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_sp, x
    bra count
item:
    rep #$20
.a16
    lda item_sel
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
count:
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
    pha
    lda temp + 3
    beq one                     ; erasing is always one row's
    jsr target_scope
    cmp #BA_SCOPE_PARTY
    bne one
    pla
    jmp target_bar_all
one:
    pla
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
ROW = TARGET_ROW_CELLS * 32
row_vram:
    .word FIRST, FIRST + ROW, FIRST + 2 * ROW, FIRST + 3 * ROW
bar_ofs:
    .word 0, BAR_BYTES, 2 * BAR_BYTES, 3 * BAR_BYTES
    .assert MENU_ROWS_PARTY = 4, error, "one word per party row"
.endproc

; --- the actor choice for a skill ----------------------------------------------
;
; What changes when the skills screen opens it —`sk_heal`—: `target_upload`
; writes the skill's name and the cost's term, `target_count` its cost,
; `target_bar` covers the whole party for a skill on everyone, and the
; arrows stop for a skill on oneself or on the party, whose bar does not
; move —`Window_ActorTarget`'s `SetIndex(-100)` and `SetIndex(-actor - 1)`—.
; `render` of `rm2k-snes-screens` with a `skill` is the reference.

; The skill's scope, in A: `skill_scope` of `sk_used`, or $FF for a
; medicine. A special item that casts a skill —`item_map_skill`— has its
; skill's, except on oneself, which goes as on an ally: RPG_RT leaves the
; bar free for an item, `Scene_ActorTarget::Start`, and casts it on the one
; chosen. Clobbers X.
.proc target_scope
.a8
.i16
    lda f:sk_target_on
    beq medicine
    lda f:sk_used
scope:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_scope, x
    rts
medicine:
    ldx item_sel
    lda f:item_map_skill, x
    cmp #$FF
    beq none                    ; $FF, as it came
    jsr scope
    cmp #BA_SCOPE_ONE
    bne none
    lda #BA_SCOPE_ALLY
none:
    rts
.endproc

; `target_upload` for a skill, with the screen off: the cost's term over
; "Owned Items" —its rows of the tilemap—, the name on the line on top and,
; for a skill on oneself, the bar on the user's row. Then its cost.
.proc target_skill_upload
.a8
.i16
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #^target_term
    sta A1B0
    rep #$20
.a16
    lda #(TARGET_MAP + TARGET_TERM_ROW0 * 32 + TARGET_TERM_COL0)
    sta temp
    lda #.loword(target_term)
    sta temp + 2
    ldx #TARGET_TERM_ROWS
row:
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda temp + 2
    sta A1T0L
    clc
    adc #(TARGET_TERM_COLS * 2)
    sta temp + 2
    lda #(TARGET_TERM_COLS * 2)
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    dex
    bne row
    ; The name, like a medicine's: its own copy in `skill_target_names`,
    ; which `skill_target_name` finds. Until 2026-11-02 it was the battle's
    ; text, cut in two lines here. A skill the map cannot use has none, and
    ; never opens this screen.
    lda f:sk_used
    and #$00FF
    tax
    lda f:skill_target_name, x
    and #$00FF
    cmp #$00FF
    beq unnamed
    jsr target_name_ofs
    adc #.loword(skill_target_names)
    sta msg_ptr
    sep #$20
.a8
    lda #^skill_target_names
    sta msg_ptr + 2
    jsr target_name_strip
unnamed:
    sep #$20
.a8
    ; On oneself, the bar on the user's row and nowhere else.
    jsr target_scope
    cmp #BA_SCOPE_ONE
    bne cost
    ldx #0
find:
    lda party, x
    cmp f:sk_actor
    beq found
    inx
    cpx #MENU_ROWS_PARTY
    bcc find
    ldx #0
found:
    txa
    sta title_sel
cost:
    jmp target_count
.endproc

; For a skill on the party, every row's HP: the use changed them all. In the
; vblank or with the screen off.
.proc target_party_hp
.a8
.i16
    jsr target_scope
    cmp #BA_SCOPE_PARTY
    bne none
    lda #0
row:
    cmp party_n
    bcs none
    cmp #MENU_ROWS_PARTY
    bcs none
    pha
    sta temp + 2                ; the row
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    sta temp                    ; the actor
    jsl f:menu_hp_write
    pla
    inc a
    bra row
none:
    rts
.endproc

; The bar over the first `party_n` rows, at most four, for a skill on the
; party: per row of its rectangle, the distinct cell row `target_all` says
; for that many members. One DMA per cell row; it only runs with the screen
; off, when the choice is drawn, because it never moves.
.proc target_bar_all
.a8
.i16
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #^target_all_rows
    sta A1B0
    lda party_n
    cmp #MENU_ROWS_PARTY
    bcc members
    lda #MENU_ROWS_PARTY
members:
    rep #$20
.a16
    and #$00FF
    tax
    lda #0
    dex                         ; the lists go from one member
size:
    beq sized
    clc
    adc #TARGET_ALL_ROWS
    dex
    bra size
sized:
    sta temp + 2                ; where this size's list starts
    lda #(TARGET_MAP + TARGET_ALL_ROW0 * 32 + TARGET_ALL_COL0)
    sta temp
    ldy #TARGET_ALL_ROWS
row:
    sep #$20
.a8
    ldx temp + 2
    lda f:target_all, x
    sta WRMPYA
    lda #(TARGET_ALL_COLS * 2)
    sta WRMPYB                  ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc #.loword(target_all_rows)
    sta A1T0L
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda #(TARGET_ALL_COLS * 2)
    sta DAS0L
    inc temp + 2
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    dey
    bne row
    rtl
.endproc

; In the actor choice's loop, right after it takes the pad's edges: for a
; skill on oneself or on the party, without the arrows. Returns with
; `title_edges` in A.
.proc target_locks
.a8
.i16
    jsr target_scope
    cmp #BA_SCOPE_ONE
    beq locked
    cmp #BA_SCOPE_PARTY
    bne free
locked:
    lda title_edges
    and #<~(PAD_UP | PAD_DOWN)
    sta title_edges
free:
    lda title_edges
    rtl
.endproc

; A in the actor choice: the medicine, the special item that casts a skill
; —`item_cast_use`—, or the skill. With actor A, and the answer of the one
; it goes to: A8 at 1 if it was of use.
.proc target_use
.a8
.i16
    pha
    lda f:sk_target_on
    bne skill
    ldx item_sel
    lda f:item_map_skill, x
    cmp #$FF
    bne cast
    pla
    jml f:medicine_use
cast:
    pla
    jml f:item_cast_use
skill:
    pla
    jml f:sk_heal_use
.endproc

; BG2 with the party and BG1 with the windows, each with its own base, and the
; screen on. It is `slot_ppu_on` plus BG1. From 2026-11-01 to 2026-11-02 the
; actor choice turned its SP's sprites on too, through a `target_ppu_with`.
.proc target_ppu_on
.a8
.i16
    jsl f:pano_mode3            ; the screens draw in mode 3
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
    lda #$03                    ; BG1 and BG2
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

; The bar itself —`menu_bar`— and whom a command is for —`menu_choose`—
; went to `menu_list.s`, in `FAR3`, the day the menu started scrolling its
; party: 2026-11-01.

; The screen of actor A, whom `menu_choose` chose, for the pause menu's
; command: Skills or Equipment. Called with `jsl`; returns with A at 1 if
; the menu has to close —a switch skill was used— and at 0 if it goes back
; to the commands.
.proc menu_whose_screen
.a8
.i16
    pha
    lda f:CM_MENU_CMD
    cmp #MENU_SKILL
    beq skills
    pla
    jsl f:equipment_screen
    lda #0
    rtl
skills:
    pla
    jml f:skills_screen         ; its `rtl` returns here, with A said
.endproc
