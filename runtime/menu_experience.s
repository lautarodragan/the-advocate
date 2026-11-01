.segment "FAR"

; --- experience in the menu -------------------------------------------------
;
; The third line of `Window_MenuStatus`: "Ex", the current experience and the
; one the next level asks for, `"%6d/%6d"`. **It goes in sprites**, twelve
; pixels below the HP and at the font's six-pixel pitch: in the cell grid
; there was no room. The why and the geometry are in `MENU_EXP_X`, in
; `rm2k-snes-screens`, whose `render` is the reference.
;
; Sprites read their tiles from `SLOT_VRAM`, so a glyph's tile in the bank
; is the same number, and their palette 1 is a copy of the text's: palette
; 0, colors 128 to 143, is the menu bar's —see `menu_bar_upload`—. No other
; screen turns sprites on —`slot_ppu_on` leaves only BG2—, so the
; actor choice, which shares the panel, does not show it, which is what
; `Window_ActorTarget` does. What this changes from the map —OBSEL and colors
; 128 to 159— is restored by `menu_exp_close` on the way back.
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
    ; Sprite palette 1, the text's.
    lda #144
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
    ; And BG1, with its own base, for the bar: empty until something is
    ; chosen. `slot_ppu_on` left BG2's base, which does not change.
    lda #(SLOT_VRAM / 4096 * 16 + TARGET_VRAM / 4096)
    sta BG12NBA
    lda #$13                    ; and the sprites on top
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
    jsr put                     ; the top cell
.a8
    lda comp_phase
    clc
    adc #8
    sta comp_phase + 1
    rep #$20
.a16
    lda f:slot_glyph_cells + 2, x
    jsr put                     ; and the bottom one
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
    ora #$32                    ; priority 3, sprite palette 1
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
; `back_to_map` does not touch, and the colors of sprite palettes 0 and 1
; —the bar's and the experience's—, from
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
    lda #(32 * 2)
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

; --- the SP on the actor choice -----------------------------------------------
;
; `Window_ActorTarget`'s SP, under the HP: the term and `"%3d"`, the slash and
; the maximum, like the HP's line. **In sprites**, where the menu has the
; experience —the actor choice has none, so the row's fourth line is free—,
; and the number one letter per HP cell, so each digit sits under the HP's.
; The why and the geometry are in `MENU_SP_X`, in `rm2k-snes-screens`, whose
; `render` of the actor choice is the reference.
;
; It is built in `oam`, the map's OAM in RAM, which nobody else writes while
; a screen is open —`build_oam` runs on the map—, and goes up whole with
; `menu_sp_upload`: with the screen off when the choice opens, and in the
; vblank after a use changes someone's SP —the medicine's target, the
; skill's user—. Each row has its own objects, eighteen from the row's
; times eighteen, and a space is a hidden object: a row is rewritten without
; touching the others. The colours and OBSEL are the experience's —palette
; 1, the tiles from `SLOT_VRAM`—, and `menu_exp_close` restores them when
; the menu closes.
;
; Its scratch is the experience's: the message composer's variables and
; `MENU_EXP_TEXT`, which do not exist with a screen open.
;   comp_char       the party row
;   comp_phase      the top y of the row's sprites
;   comp_phase + 1  the y of the sprite being placed
;   comp_mask       the x of the sprite being placed
;   comp_base       the OAM byte of the object being placed, 16 bits
;   comp_col        the letter being placed
;
; **In `FAR3`**, entered from bank 0 with `jsl` and calling nothing near:
; bank 1 had some 150 bytes left in A Blurred Line's `release` and its MSU
; test cartridge overflowed. That is why it has its own `sp_digits` and
; not `three_digits`, and why it leaves with a `jml` to bank 1's
; `target_ppu_with`.

.pushseg
.segment "FAR3"

MENU_SP_ROW_OBJECTS = MENU_EXP_TERM_TILES + 2 * MENU_SP_LETTERS

.assert MENU_ROWS_PARTY * MENU_SP_ROW_OBJECTS <= MENU_EXP_SPRITES, error, "the party's SP do not fit in the sprites"
.assert MENU_EXP_TEXT + MENU_SP_LETTERS <= MENU_EXP_TEXT_END, error, "the SP line does not fit in its place"

; Every object hidden and small, and each party row's SP line, into `oam`.
; With any data bank; clobbers A, X and Y.
.proc menu_sp_build
.a8
.i16
    phb
    lda #0
    pha
    plb                         ; `oam` and the party, in bank 0
    ldx #0
hide:
    stz oam, x
    lda #MENU_EXP_HIDDEN
    sta oam + 1, x
    stz oam + 2, x
    stz oam + 3, x
    inx
    inx
    inx
    inx
    cpx #512
    bcc hide
    ldx #0
small:
    stz oam_high, x
    inx
    cpx #32
    bcc small
    stz comp_char
row:
    lda comp_char
    cmp party_n
    bcs ready
    cmp #MENU_ROWS_PARTY
    bcs ready
    jsr one_row
    inc comp_char
    bra row
ready:
    plb
    rtl

; Row `comp_char`'s line, if the cartridge knows its actor.
one_row:
    ; Its first object's byte: the row times eighteen objects of four.
    rep #$20
.a16
    lda comp_char
    and #$00FF
    asl a
    asl a
    asl a                       ; eight
    sta comp_base
    asl a
    asl a
    asl a                       ; sixty-four
    clc
    adc comp_base               ; seventy-two
    sta comp_base
    .assert MENU_SP_ROW_OBJECTS * 4 = 72, error, "the row's first object is not the row times 72"
    sep #$20
.a8
    ; And its y: the row's, plus the line's.
    lda comp_char
    sta WRMPYA
    lda #MENU_ACTOR_HEIGHT
    sta WRMPYB                  ; eight cycles
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc #MENU_SP_Y
    sta comp_phase
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
    pha                         ; the actor, until the text is done

    ; --- the text: the current SP in three places, right-aligned ---
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    cmp #1000
    bcc fits
    lda #999                    ; as the skills screen caps them
fits:
    jsr sp_digits
    sep #$20
.a8
    lda comp_dup
    bne hundreds
    lda #' '
    sta f:MENU_EXP_TEXT
    lda comp_dup + 1
    bne tens
    lda #' '
    sta f:MENU_EXP_TEXT + 1
    bra units
hundreds:
    ora #'0'
    sta f:MENU_EXP_TEXT
    lda comp_dup + 1
tens:
    ora #'0'
    sta f:MENU_EXP_TEXT + 1
units:
    lda comp_dup + 2
    ora #'0'
    sta f:MENU_EXP_TEXT + 2

    ; --- and "/%d", the maximum for its level, padded to four ---
    pla                         ; the actor
    ldy #1                      ; the SP, in `lcf.CURVES`' order
    jsl f:level_param
    rep #$20
.a16
    txa
    cmp #1000
    bcc fits_max
    lda #999
fits_max:
    jsr sp_digits
    sep #$20
.a8
    ldx #MENU_HP_DIGITS
    lda #'/'
    sta f:MENU_EXP_TEXT, x
    inx
    lda comp_dup
    beq no_hundreds
    ora #'0'
    sta f:MENU_EXP_TEXT, x
    inx
    lda comp_dup + 1
    bra with_tens               ; with hundreds the tens digit goes in even if zero
no_hundreds:
    lda comp_dup + 1
    beq no_tens
with_tens:
    ora #'0'
    sta f:MENU_EXP_TEXT, x
    inx
no_tens:
    lda comp_dup + 2
    ora #'0'
    sta f:MENU_EXP_TEXT, x
    inx
padding:
    cpx #MENU_SP_LETTERS
    bcs sprites
    lda #' '
    sta f:MENU_EXP_TEXT, x
    inx
    bra padding

sprites:
    ; --- the term: four tiles, two on top and two below ---
    ldy #0
term:
    lda #MENU_SP_X
    cpy #1
    beq term_right
    cpy #3
    bne term_x
term_right:
    lda #(MENU_SP_X + 8)
term_x:
    sta comp_mask
    lda comp_phase
    cpy #2
    bcc term_y
    clc
    adc #8
term_y:
    sta comp_phase + 1
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:menu_sp_finished, x
    jsr put
.a8
    iny
    cpy #MENU_EXP_TERM_TILES
    bcc term

    ; --- the seven letters, one per HP cell; a space stays hidden ---
    lda #MENU_SP_NUM_X
    sta comp_mask
    stz comp_col
letter:
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:MENU_EXP_TEXT, x
    cmp #' '
    bne visible
    rep #$21                    ; and the carry at zero
.a16
    lda comp_base
    adc #8                      ; its two objects, still hidden
    sta comp_base
    sep #$20
.a8
    bra next
visible:
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_FIRST_CHAR
    asl a
    asl a                       ; two words per letter
    tay
    sep #$20
.a8
    lda comp_phase
    sta comp_phase + 1
    rep #$20
.a16
    tyx
    lda f:slot_glyph_cells, x
    jsr put                     ; the top cell
.a8
    lda comp_phase
    clc
    adc #8
    sta comp_phase + 1
    rep #$20
.a16
    tyx
    lda f:slot_glyph_cells + 2, x
    jsr put                     ; and the bottom one
.a8
next:
    lda comp_mask
    clc
    adc #8
    sta comp_mask
    inc comp_col
    lda comp_col
    cmp #MENU_SP_LETTERS
    bcc letter
    rts

; One object at `comp_base`: A16 the glyph's tilemap word —tile and
; palette—, at `comp_mask`, `comp_phase + 1`. Moves `comp_base` to the next
; object. Returns with an 8-bit A, and touches neither X nor Y.
.a16
put:
    phx
    pha                         ; the word
    ldx comp_base
    sep #$20
.a8
    lda comp_mask
    sta oam, x
    lda 1, s                    ; the tile's low byte
    sta oam + 2, x
    lda 2, s                    ; the word's high byte: bit 8 of the
    and #$01                    ; tile, and the BG2 palette, which is 0
    ora #$32                    ; priority 3, sprite palette 1
    sta oam + 3, x
    lda comp_phase + 1
    sta oam + 1, x
    rep #$21
.a16
    pla                         ; the word, which is not needed any more
.a16
    txa
    adc #4
    sta comp_base
    sep #$20
.a8
    plx
    rts

; A16 —less than a thousand— into its three digits, 0 to 9, in `comp_dup`,
; `+ 1` and `+ 2`: `three_digits` of level.s, which is in bank 1. Leaves
; A at sixteen bits; clobbers X.
.a16
sp_digits:
    ldx #0
hundreds_count:
    cmp #100
    bcc hundreds_done
    sbc #100                    ; C comes from the comparison
    inx
    bra hundreds_count
hundreds_done:
    stx comp_dup                ; and a zero in `comp_dup + 1`
    ldx #0
tens_count:
    cmp #10
    bcc tens_done
    sbc #10
    inx
    bra tens_count
tens_done:
    stx comp_dup + 1            ; and a zero in `comp_dup + 2`
    sep #$20
.a8
    sta comp_dup + 2
    rep #$20
.a16
    rts
.a8
.endproc

; When the actor choice is drawn, with the screen off: the SP lines, the
; experience's object base and palette —see `menu_exp_paint`—, and the OAM
; up. `target_ppu_on` turns the sprites on with the rest.
.proc menu_sp_paint
.a8
.i16
    jsl f:menu_sp_build
    phb
    lda #0
    pha
    plb                         ; the registers, in bank 0
    lda #(SLOT_VRAM / $2000)
    sta OBSEL
    lda #144                    ; sprite palette 1, the text's
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
    plb
    jsl f:menu_sp_upload
    lda #$13                    ; BG1, BG2 and the sprites
    jml f:target_ppu_with       ; in bank 1: its `rtl` is this one's
.endproc

; After a use, with the screen on: the lines built again, and up at the
; start of the next vblank, where it returns —with the rest of that vblank
; for the HP—. It is `wait_vblank` without the text layer, which this
; screen does not have on.
.proc menu_sp_refresh
.a8
.i16
    jsl f:menu_sp_build
    phb
    lda #0
    pha
    plb
out:
    lda HVBJOY
    bmi out
in:
    lda HVBJOY
    bpl in
    plb
    bra menu_sp_upload          ; its `rtl` is this one's
.endproc

; `oam` up to the OAM, whole: in the vblank or with the screen off. It is
; `push_oam`, which is bank 0's and is entered with `jsr`.
.proc menu_sp_upload
.a8
.i16
    phb
    lda #0
    pha
    plb
    stz OAMADDL
    stz OAMADDL + 1
    ldx #.loword(oam)
    stx A1T0L
    lda #^oam
    sta A1B0
    ldy #544                    ; the 512 of the big table plus the 32 small ones
    sty DAS0L
    stz DMAP0
    lda #$04
    sta BBAD0                   ; OAMDATA
    lda #$01
    sta MDMAEN
    plb
    rtl
.endproc
.popseg
