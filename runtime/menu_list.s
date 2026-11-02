.segment "FAR"
; **The whole file's code is in `FAR3`**, like `menu_experience.s`, and
; `FAR` above is only what the next file in main.s inherits. Everything is
; entered with `jsl`, sets its own data bank where it touches bank 0
; absolute, and reads the converter's tables long.
.pushseg
.segment "FAR3"

; --- the party panel ---------------------------------------------------------
;
; The party of `Scene_Menu` and `Scene_ActorTarget`: one row per actor, its
; fixed block, its face, its name composed —`tl_strip`— and its level, its
; maximum and its current HP one letter per cell, and its condition over the
; block's "Normal" —`menu_state_paint`, in menu_states.s—. The two screens share the
; row; they do not share the panel:
;
; * **the actor choice** shows the four rows, seven cells each, painted
;   where they are seen —`menu_party_paint`—, with its SP in sprites;
; * **the pause menu** shows three rows of nine cells, with the SP as a
;   fourth line of cells and the experience in sprites under it, and
;   scrolls a whole row when the bar goes past them —`menu_list_paint`,
;   `menu_choose`—. Four of its rows would be 288 lines.
;
; The geometry and the why are in `MENU_LIST_ROWS` of `rm2k-snes-screens`,
; whose `render` is the reference for both.
;
; **A scroll writes nothing but its three rows' cells.** Nothing of VRAM can
; be written outside the vblank, and three rows painted again —three names
; composed into tiles— do not fit in one: so when the menu opens each
; actor's row is painted **once**, on the first row's cells, and read back
; to WRAM; a scroll uploads the three rows shown from there, and the OAM
; with their experience, in one vblank. A row's cells point at its tiles,
; wherever they are put, so the name composed on the first row is the same
; on the third.
;
; Where they are kept is the start of `LZ2_BUFFER`, written by name and
; without a label of its own —`test_wram_reservations.py` would take a new
; one there as a trespasser—: the load buffer is free while the menu is
; open, because the menu does not open with a big picture up and the map
; comes back through a load, and its first $1100 bytes are below
; `CODE_CARRY`. A screen the menu opens —a custom menu— may use it: the
; menu is painted again when it comes back.
;
; It all left bank 0 —and the choice and the bar, bank 1— the day the menu
; started scrolling, 2026-11-01: there were tens of bytes left in the first
; and some five hundred in the second.

.pushseg
.segment "FARBSS"
far_menu_top: .res 1            ; the first party member the menu shows
.popseg

MENU_LIST_BYTES = MENU_ACTOR_COLS * 2           ; one cell row of a row
MENU_ACTOR_BYTES = MENU_LIST_ROWS * MENU_LIST_BYTES
.assert MENU_ROWS_PARTY * MENU_ACTOR_BYTES <= CODE_CARRY - LZ2_BUFFER, error, "the menu's rows reach the carried bytecode"
.assert MENU_SHOWN * MENU_LIST_ROWS <= 28, error, "the menu's rows go past the screen"
.assert MENU_SHOWN < MENU_ROWS_PARTY, error, "the menu shows every row: nothing scrolls"

; The actor choice's panel: the first four members, each on its row. With
; the screen off; with any data bank.
.proc menu_party_paint
.a8
.i16
    phb
    lda #0
    pha
    plb
    jsl f:menu_states_forget    ; the bank went up again
    lda #0
member:
    cmp party_n
    bcs ready
    cmp #MENU_ROWS_PARTY
    bcs ready
    pha
    tax                         ; on its own row
    jsr menu_row_paint
    pla
    inc a
    bra member
ready:
    plb
    rtl
.endproc

; The pause menu's panel, with the screen off, from `menu_upload`: each
; member's row painted on the first row's cells and kept, and the first
; three shown. With any data bank.
.proc menu_list_paint
.a8
.i16
    phb
    lda #0
    pha
    plb
    jsl f:menu_states_forget    ; the bank went up again
    lda #0
    sta f:far_menu_top          ; it opens at the top, as RM2k's
member:
    cmp party_n
    bcs shown
    cmp #MENU_ROWS_PARTY
    bcs shown
    pha
    jsr clear                   ; what the previous one left
    lda 1, s
    ldx #0                      ; on the first row
    jsr menu_row_paint
    lda 1, s
    jsr menu_sp_cells
    lda 1, s
    jsr keep
    pla
    inc a
    bra member
shown:
    jsl f:menu_list_show
    plb
    rtl

; The first row's cells, blank: a fixed source of zeros, cell row by cell
; row. `temp` carries the VRAM address.
clear:
    lda #$80
    sta VMAIN
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #^zero
    sta A1B0
    ldy #.loword(zero)
    rep #$20
.a16
    lda #MENU_LIST_VRAM
    sta temp
blank:
    lda temp
    sta VMADDL
    sty A1T0L
    lda #MENU_LIST_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$21                    ; and the carry at zero
.a16
    lda temp
    adc #32
    sta temp
    cmp #(MENU_LIST_VRAM + MENU_LIST_ROWS * 32)
    bcc blank
    sep #$20
.a8
    rts

; And read back: the first row's cells into member A's place in the buffer,
; a DMA from the PPU per cell row. **Each row starts with a word read and
; thrown away**: writing VMADD prefetches the word, but the first read loads
; the prefetch again from the same address before moving on —"Prefetch
; occurs BEFORE incrementing", a glitch of the hardware that fullsnes
; describes and snes9x follows—, so without it the first word comes twice
; and the row lands one cell to the right.
keep:
    jsr menu_list_kept          ; Y: where its cells go
    lda #$80
    sta VMAIN
    lda #$81                    ; from the PPU, two registers
    sta DMAP0
    lda #<VMDATALREAD
    sta BBAD0
    lda #^LZ2_BUFFER
    sta A1B0
    rep #$20
.a16
    lda #MENU_LIST_VRAM
    sta temp
read:
    lda temp
    sta VMADDL
    sep #$20
.a8
    lda VMDATALREAD             ; the word that comes twice
    lda VMDATALREAD + 1
    rep #$20
.a16
    sty A1T0L
    lda #MENU_LIST_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$21                    ; and the carry at zero
.a16
    tya
    adc #MENU_LIST_BYTES
    tay
    lda temp
    adc #32
    sta temp
    cmp #(MENU_LIST_VRAM + MENU_LIST_ROWS * 32)
    bcc read
    sep #$20
.a8
    rts
.endproc

; Where member A's row is kept, in Y: its place in the start of the load
; buffer. Clobbers A and X; returns with an eight-bit A.
.proc menu_list_kept
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    lda #.loword(LZ2_BUFFER)
times:
    dex
    bmi there
    clc
    adc #MENU_ACTOR_BYTES
    bra times
there:
    tay
    sep #$20
.a8
    rts
.endproc

; The three rows `far_menu_top` says, from where they were kept: blank
; where there is nobody. With the screen off or in the vblank: they are
; 27 DMAs of one cell row each. With any data bank; clobbers `temp`.
.proc menu_list_show
.a8
.i16
    phb
    lda #0
    pha
    plb
    lda #$80
    sta VMAIN
    lda #$18
    sta BBAD0
    rep #$20
.a16
    lda #MENU_LIST_VRAM
    sta temp
    sep #$20
.a8
    lda f:far_menu_top
    sta temp + 2                ; the member on this row
row:
    jsr source
    lda #MENU_LIST_ROWS
    sta temp + 3
cells:
    rep #$21                    ; and the carry at zero
.a16
    lda temp
    sta VMADDL
    adc #32
    sta temp
    sty A1T0L
    lda #MENU_LIST_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    lda DMAP0
    and #$08
    bne same                    ; a fixed source: the same zeros again
    rep #$21
.a16
    tya
    adc #MENU_LIST_BYTES
    tay
    sep #$20
.a8
same:
    dec temp + 3
    bne cells
    inc temp + 2
    lda temp + 2
    sec
    sbc f:far_menu_top
    cmp #MENU_SHOWN
    bcc row
    plb
    rtl

; Y, DMAP0 and A1B0 for member `temp + 2`: its kept row, or zeros if there
; is nobody there.
source:
    lda party_n
    cmp #MENU_ROWS_PARTY
    bcc counted
    lda #MENU_ROWS_PARTY
counted:
    cmp temp + 2
    beq nobody
    bcc nobody
    lda #$01
    sta DMAP0
    lda #^LZ2_BUFFER
    sta A1B0
    lda temp + 2
    jmp menu_list_kept          ; its `rts` is this one's
nobody:
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #^zero
    sta A1B0
    ldy #.loword(zero)
    rts
.endproc

; Member A's row on panel row X —the entry of `menu_row_vram`—: the row's
; fixed block, the face, and on top the name, the level, the maximum and
; the current HP. With the screen off and the data bank at 0.
;
; **The block is a single one for every row and every actor**: it carries
; the level term, the status and the HP term, which depend on no one. What
; does depend on the actor is written over it, and that is what keeps the
; tile bank from growing with the number of actors: its name composed
; —`tl_strip`— and its level and its maximum with glyphs, one per cell
; —`slot_text_write`—.
;
; The member and the row stay on the stack for the whole pass and each step
; takes them from there instead of saving them: the direct page is full
; —`temp` and `temp + 2` are used by the routines that write— and each step
; runs once per row, with the PPU off. Until 2026-11-01 it was the menu's
; `menu_party_paint`, in bank 0, with the row and the member the same.
.proc menu_row_paint
.a8
.i16
    pha                         ; 2, s: the member
    txa
    pha                         ; 1, s: the row
    lda 2, s
    jsr actor
    cmp #MENU_ACTORS_N
    bcc known
    jmp done                    ; one this ROM does not know
known:

    ; --- the row's fixed block ---
    lda 1, s
    jsr row_vram
    lda #(MENU_ACTOR_COLS * 2)
    sta temp
    lda #MENU_ACTOR_ROWS
    sta temp + 2
    ldx #MENU_BLK_ROW
    jsl f:slot_rect_upload_far

    ; --- the face, in the row's top left corner ---
    lda 1, s
    jsr row_vram
    lda 2, s
    jsr actor
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:slot_face_block, x
    cmp #$FF
    beq no_face
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #(MENU_FACE_CELLS * 2)
    sta temp
    lda #MENU_FACE_CELLS
    sta temp + 2
    jsl f:slot_rect_upload_far
no_face:

    ; --- the name ---
    lda 1, s
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NAME_OFS
    tay
    sep #$20
.a8
    lda 2, s
    jsr actor
    jsl f:actor_name_row_now    ; its row, or a rename's: actor_names.s
    ldx #SLOT_TEXT_NAME
    jsl f:slot_text_of_far
    lda #MENU_NAME_COLS
    jsl f:tl_strip + FAST       ; composed: see `tl_strip`

    ; --- the level ---
    lda 1, s
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_LEVEL_OFS
    tay
    sep #$20
.a8
    lda 2, s
    jsr actor
    jsl f:text_level            ; the current one: it goes up by fighting
    lda #SLOT_LEVEL_DIGITS
    jsl f:slot_text_write_far

    ; --- the condition, over the block's "Normal": menu_states.s ---
    lda 1, s
    jsr row_vram
    lda 2, s
    jsr actor                   ; and X, the member
    jsl f:menu_state_paint

    ; --- the maximum, after the slash ---
    lda 1, s
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_MAX_OFS
    tay
    sep #$20
.a8
    lda 2, s
    jsr actor
    jsl f:text_max              ; the one for its current level, like the level
    lda #MENU_MAX_DIGITS
    jsl f:slot_text_write_far

    ; --- and the current HP, which are not cartridge text but state ---
    lda 1, s
    sta temp + 2                ; the row
    lda 2, s
    jsr actor
    sta temp                    ; the actor
    jsl f:menu_hp_write
done:
    pla
    pla
    rts

; The actor of the member given in A.
actor:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    rts

; The cell where row A starts in the tilemap, in Y.
row_vram:
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per entry
    tax
    lda menu_row_vram, x
    tay
    sep #$20
.a8
    rts
.endproc

; The pause menu's fourth line for member A, on the first row: the SP term
; and `"%3d/%d"` one letter per cell, under the HP's —`MENU_SP_ROW`—. The
; text is the actor choice's, `menu_sp_text`; the term's words get the
; priority bit the bank's blocks carry, so BG1's bar stays under them. With
; the screen off and the data bank at 0.
.proc menu_sp_cells
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    cmp #MENU_ACTORS_N
    bcc known
    rts                         ; one this ROM does not know
known:
    jsr menu_sp_text            ; into MENU_EXP_TEXT
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(MENU_LIST_VRAM + MENU_SP_TERM_OFS)
    sta VMADDL
    lda f:menu_sp_finished
    ora #$2000
    sta VMDATAL
    lda f:menu_sp_finished + 2
    ora #$2000
    sta VMDATAL
    lda #(MENU_LIST_VRAM + MENU_SP_TERM_OFS + 32)
    sta VMADDL
    lda f:menu_sp_finished + 4
    ora #$2000
    sta VMDATAL
    lda f:menu_sp_finished + 6
    ora #$2000
    sta VMDATAL
    ; The letters: their upper cells, which follow each other, and then
    ; the lower ones.
    lda #(MENU_LIST_VRAM + MENU_SP_NUM_OFS)
    sta VMADDL
    lda #0
    jsr letters
    lda #(MENU_LIST_VRAM + MENU_SP_NUM_OFS + 32)
    sta VMADDL
    lda #2
    jsr letters
    sep #$20
.a8
    rts

; A16: 0 for the upper cells, 2 for the lower ones.
.a16
letters:
    sta temp
    ldx #0
letter:
    phx
    lda f:MENU_EXP_TEXT, x
    and #$00FF
    sec
    sbc #ITEM_FIRST_CHAR
    asl a
    asl a                       ; two words per letter
    clc
    adc temp
    tax
    lda f:slot_glyph_cells, x
    sta VMDATAL
    plx
    inx
    cpx #MENU_SP_LETTERS
    bcc letter
    rts
.a8
.endproc

; --- the bar on the pause menu -----------------------------------------------
;
; `Scene_Menu` chooses whom a command is for over its own party panel: the
; commands stay on the left with their cursor, and the red bar goes over
; the row's text —`UpdateActorSelection`—. It is the actor choice's bar,
; with its tiles and colours, but over nothing: the menu has no windows, so
; outside the bar BG1 is empty and erasing it is writing zeros. The geometry
; is `MENU_BAR` of `rm2k-snes-screens`, whose `render` of the menu is the
; reference. Its tiles and colours are uploaded by `menu_bar_upload`, in
; `actor_choice.s`.

; The bar on panel row A —0 to `MENU_SHOWN - 1`, a row seen, not a
; member—: `temp + 3` at 1 paints it and at 0 erases it. One DMA per row of
; cells, which fits in the vblank. It clobbers `temp` through `temp + 2`.
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
ROW = MENU_LIST_ROWS * 32
row_vram:
    .word FIRST, FIRST + ROW, FIRST + 2 * ROW
    .assert MENU_SHOWN = 3, error, "one word per row shown"
.endproc

; --- whom a command is for ---------------------------------------------------
;
; `Scene_Menu::UpdateActorSelection`: the menu stays as it is, with the
; cursor on the command, and the bar goes over the party panel —see
; `menu_bar`—, always starting on the first member. Up and down wrap around,
; like any `Window_Selectable`, and the panel scrolls a whole row when the
; bar goes past the three shown, as `Window_Selectable::UpdateCursorRect`
; moves its top row. Returns with the member in A, or $FF if B was pressed,
; with the bar erased. Called with `jsl` and the data bank at 0, just after
; `read_pad`, still inside the vblank; `title_sel` is the member while it
; lasts: the caller puts the command back.
;
; Confirmed against the RPG_RT of 2015 under Wine and easyrpg's
; `scene_menu.cpp`: see the task `who-to-equip-from-the-menu`.
.proc menu_choose
.a8
.i16
    stz title_sel
    ; Back to the top, if a choice B canceled left it scrolled: the next
    ; vblank, with the bar not yet painted.
    lda f:far_menu_top
    beq top
    lda #0
    sta f:far_menu_top
    jsl f:menu_exp_build
    jsl f:ba_t_vblank
    jsl f:menu_list_show
    jsl f:menu_sp_upload
top:
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
    jsr seen
    jsl f:menu_bar
    lda #$FF                    ; B: nothing chosen
    rtl
no_b:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                    ; it was already held: not an edge
    ; Skills asks for someone who can act —`Scene_Menu`, `CanAct()`—: one
    ; at 0 HP is refused and the bar stays, where RM2k plays its buzzer.
    ; Outside battle this port keeps no states, so fallen is all it can be.
    lda f:CM_MENU_CMD
    cmp #MENU_SKILL
    bne chosen
    rep #$20
.a16
    lda title_sel
    and #$00FF
    tax
    lda party, x
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    sep #$20
.a8
    beq wait                    ; `sep` leaves Z as the `lda` of the HP left it
chosen:
    lda title_sel
    rtl

; How many members the panel has, in A.
rows_n:
    lda party_n
    cmp #MENU_ROWS_PARTY
    bcc rows_ready
    lda #MENU_ROWS_PARTY
rows_ready:
    rts

; The row seen that `title_sel` is on, in A.
seen:
    lda title_sel
    sec
    sbc f:far_menu_top
    rts

; The bar from the member it was on to the one in A. If that one is not
; shown, the panel scrolls: the OAM is built now and, in the next vblank,
; the bar erased, the three rows and the OAM up and the bar painted —one
; frame, without a black one—. Otherwise the bar moves in this vblank.
move:
    pha                         ; 2, s: the new member
    jsr seen
    pha                         ; 1, s: the row the bar is on
    lda 2, s
    jsr aim
    cmp f:far_menu_top
    beq still
    sta f:far_menu_top
    jsl f:menu_exp_build        ; in RAM, with the screen on
    jsl f:ba_t_vblank
    stz temp + 3
    pla
    jsl f:menu_bar
    jsl f:menu_list_show
    jsl f:menu_sp_upload
    bra paint
still:
    stz temp + 3
    pla
    jsl f:menu_bar
paint:
    pla
    sta title_sel
    lda #1
    sta temp + 3
    jsr seen
    jsl f:menu_bar
    rts

; The first member shown so that member A is: the same if it is, A if it is
; above, and the one that leaves it last if it is below. Clobbers `temp`.
aim:
    cmp f:far_menu_top
    bcc aimed                   ; above the first shown: it goes first
    sta temp
    lda f:far_menu_top
    clc
    adc #(MENU_SHOWN - 1)
    cmp temp
    bcs shown                   ; the last shown is it or below it
    lda temp
    sec
    sbc #(MENU_SHOWN - 1)       ; below: it goes last
aimed:
    rts
shown:
    lda f:far_menu_top
    rts
.endproc
.popseg
