.segment "FAR"

; --- experience in the menu -------------------------------------------------
;
; The third line of `Window_MenuStatus`: "Ex", the current experience and the
; one the next level asks for, `"%6d/%6d"`. **It goes in sprites**, twelve
; pixels below the HP and at the font's six-pixel pitch: in the cell grid
; there was no room. The why and the geometry are in `MENU_EXP_X`, in
; titulo.py, and `render_menu` is the reference.
;
; Sprites read their tiles from `SLOT_VRAM`, so a glyph's tile in the bank
; is the same number, and their palette 0 is a copy of the text's. No other
; screen turns sprites on —`slot_ppu_on` leaves only BG2—, so the
; actor choice, which shares the panel, does not show it, which is what
; `Window_ActorTarget` does. What this changes from the map —OBSEL and colors
; 128 to 143— is restored by `menu_exp_close` on the way back.
;
; It runs with the screen off: the OAM is written straight through the port,
; and nothing overwrites it while the menu is shown because `flush_video`
; does not run.
;
; The scratch space is variables borrowed from the message composer, which
; does not exist with the menu open:
;   comp_char       the party row
;   comp_phase       the top y of the row's sprites
;   comp_phase + 1   the y of the sprite being placed
;   comp_mask       its x
;   comp_base       how many sprites have been placed
;   comp_dup        the actor's level
;   comp_or01       the number being written, 24 bits
;   comp_and        the trial subtraction
;   comp_col        the digit being counted
;   comp_col + 1    whether a digit has already come out

MENU_EXP_TERM_TILES = 4         ; the term: two wide, top and bottom
MENU_EXP_HIDDEN = 224           ; a y below the last visible line
MENU_EXP_SPRITES = 128

.assert MENU_EXP_TEXT + MENU_EXP_LETTERS <= MENU_EXP_TEXT_END, error, "the experience line does not fit in its place"
.assert MENU_ROWS_PARTY * (MENU_EXP_TERM_TILES + 2 * MENU_EXP_LETTERS) <= MENU_EXP_SPRITES, error, "the party's experience does not fit in the sprites"

; From `menu_upload`, instead of `slot_ppu_on`: the sprites, and then
; it turns the screen on with them. With the screen off.
.proc menu_exp_paint
.a8
.i16
    phb
    lda #0
    pha
    plb                         ; the registers and the tables in bank 0
    ; 8x8 sprites with the tiles from `SLOT_VRAM`.
    lda #(SLOT_VRAM / $2000)
    sta OBSEL
    ; Sprite palette 0, the text's.
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(slot_cgram)
    sta A1T0L
    lda #(16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^slot_cgram
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    stz OAMADDL
    stz OAMADDL + 1
    stz comp_base               ; no sprite yet
    stz comp_char
    lda #MENU_EXP_Y
    sta comp_phase
row:
    lda comp_char
    cmp party_n
    bcs rows_lists
    cmp #MENU_ROWS_PARTY
    bcs rows_lists
    jsr one_row
    lda comp_phase
    clc
    adc #MENU_ACTOR_HEIGHT
    sta comp_phase
    inc comp_char
    bra row
rows_lists:
    ; The leftover ones, below the screen, and the small table at zero: an
    ; eight-bit x and the small size for all of them.
    lda comp_base
    cmp #MENU_EXP_SPRITES
    bcs hidden_all_ready
    stz OAMDATA
    lda #MENU_EXP_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    inc comp_base
    bra rows_lists
hidden_all_ready:
    ldx #(MENU_EXP_SPRITES / 4)
table_small:
    stz OAMDATA
    dex
    bne table_small

    jsl f:ba_t_ppu              ; the screen, on with BG2 alone
    lda #$12                    ; and the sprites on top
    sta TM
    plb
    rtl

; The line for row `comp_char`, if its actor has experience.
one_row:
    rep #$20
.a16
    lda comp_char
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    cmp #MENU_ACTORS_N
    bcc known
    rts                         ; one this ROM does not know
known:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne with_exp
    rts                         ; one who does not fight: has no experience
with_exp:
    rep #$20
.a16
    and #$00FF
    pha                         ; k, until the end of the line
    asl a
    asl a
    tax                         ; its slot in `FAR_EXP`
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + EXP_LEVEL, x
    sta comp_dup
    ; At the cap? Dashes, like RPG_RT.
    rep #$20
.a16
    lda 1, s                    ; k
    phx
    tax
    sep #$20
.a8
    lda f:exp_level_max, x
    plx
    cmp comp_dup
    beq cap
    bcc cap
    ; The current one.
    rep #$20
.a16
    lda f:FAR_LENGTH + FAR_EXP, x
    sta comp_or01
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + 2, x
    sta comp_or01 + 2
    ldy #0
    jsr six_digits
    lda #'/'
    tyx
    sta f:MENU_EXP_TEXT, x
    iny
    ; And the next level's: its curve's row in `exp_table`, at the current
    ; level, which is `GetNextExp(level)`.
    rep #$20
.a16
    pla                         ; k
    asl a
    tax
    lda comp_dup
    and #$00FF
    asl a
    asl a                       ; four bytes per level
    clc
    adc f:exp_curve, x
    tax
    lda f:exp_table, x
    sta comp_or01
    sep #$20
.a8
    lda f:exp_table + 2, x
    sta comp_or01 + 2
    jsr six_digits
    bra sprites
cap:
    rep #$20
.a16
    pla                         ; k, which is not needed
    sep #$20
.a8
    ldx #0
dash:
    lda #'-'
    cpx #MENU_EXP_DIGITS
    bne no_bar
    lda #'/'
no_bar:
    sta f:MENU_EXP_TEXT, x
    inx
    cpx #MENU_EXP_LETTERS
    bcc dash

sprites:
    ; --- the term: four tiles, two on top and two below ---
    ldx #0
finished:
    lda #MENU_EXP_X
    cpx #1
    beq term_right
    cpx #3
    bne term_x
term_right:
    lda #(MENU_EXP_X + 8)
term_x:
    sta comp_mask
    lda comp_phase
    cpx #2
    bcc term_y
    clc
    adc #8
term_y:
    sta comp_phase + 1
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:menu_exp_finished, x
    jsr put
.a8
    plx
    inx
    cpx #MENU_EXP_TERM_TILES
    bcc finished

    ; --- the thirteen letters, six pixels apart; a space gets no sprite ---
    lda #MENU_EXP_NUM_X
    sta comp_mask
    ldx #0
letter:
    lda f:MENU_EXP_TEXT, x
    cmp #' '
    beq next
    phx
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_FIRST_CHAR
    asl a
    asl a                       ; two words per letter
    tax
    sep #$20
.a8
    lda comp_phase
    sta comp_phase + 1
    rep #$20
.a16
    lda f:slot_glyph_cells, x
    jsr put                   ; the top cell
.a8
    lda comp_phase
    clc
    adc #8
    sta comp_phase + 1
    rep #$20
.a16
    lda f:slot_glyph_cells + 2, x
    jsr put                   ; and the bottom one
.a8
    plx
next:
    lda comp_mask
    clc
    adc #MENU_EXP_STEP
    sta comp_mask
    inx
    cpx #MENU_EXP_LETTERS
    bcc letter
    rts

; One sprite: A16 the glyph's tilemap word —tile and palette—, at
; `comp_mask`, `comp_phase + 1`. Returns with an 8-bit A, and touches neither
; X nor Y.
.a16
put:
    sep #$20
.a8
    pha                         ; the tile's low byte
    lda comp_mask
    sta OAMDATA
    lda comp_phase + 1
    sta OAMDATA
    pla
    sta OAMDATA
    xba                         ; the word's high byte: bit 8 of the
    and #$01                    ; tile, and the BG2 palette, which is 0
    ora #$30                    ; priority 3, sprite palette 0
    sta OAMDATA
    inc comp_base
    rts

; `comp_or01`: a 24-bit number, less than a million. Writes its six digits
; into `MENU_EXP_TEXT` from Y, right-aligned with spaces, and leaves Y past
; them. It clobbers X.
six_digits:
    stz comp_col + 1
    ldx #0
power:
    stz comp_col
remain:
    rep #$20
.a16
    lda comp_or01
    sec
    sbc f:powers, x
    sta comp_and
    sep #$20                    ; `sep` does not touch the subtraction's carry
.a8
    lda comp_or01 + 2
    sbc f:powers + 2, x
    bcc no_reaches
    sta comp_or01 + 2
    rep #$20
.a16
    lda comp_and
    sta comp_or01
    sep #$20
.a8
    inc comp_col
    bra remain
no_reaches:
    lda comp_col
    ora comp_col + 1
    bne digit
    cpx #(5 * 3)
    beq digit                   ; the units always go, even if 0
    lda #' '
    bra write
digit:
    lda #1
    sta comp_col + 1
    lda comp_col
    clc
    adc #'0'
write:
    phx
    tyx
    sta f:MENU_EXP_TEXT, x
    plx
    iny
    inx
    inx
    inx
    cpx #(6 * 3)
    bcc power
    rts

powers:
    .faraddr 100000, 10000, 1000, 100, 10, 1
.endproc

; When closing the menu, before `back_to_map`: what `menu_exp_paint`
; changed on the map and the map does not restore by itself. OBSEL, which
; `back_to_map` does not touch, and the colors of sprite palette 0, from
; `cgram_shadow`, which has the map's even if the tint or a picture changed
; them. It turns the screen off, which `back_to_map` turns off anyway.
.proc menu_exp_close
.a8
.i16
    phb
    lda #0
    pha
    plb
    lda #$80
    sta INIDISP
    ldx map_ofs
    lda f:map_table + M_OBSEL_VALUE, x
    sta OBSEL
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_shadow + 2 * 128)
    sta A1T0L
    lda #(16 * 2)
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the shadow lives in bank 0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    plb
    rtl
.endproc
