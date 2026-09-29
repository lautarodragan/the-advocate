.segment "FAR"

; --- experience in the menu -------------------------------------------------
;
; The third line of `Window_MenuStatus`: "Ex", the current experience and the
; one the next level asks for, `"%6d/%6d"`. **It goes in sprites**, twelve
; pixels below the HP and at the font's six-pixel pitch: in the cell grid
; there was no room. The why and the geometry are in `MENU_EXP_X`, in
; titulo.py, and `render_menu` is the reference.
;
; Sprites read their tiles from `RANURA_VRAM`, so a glyph's tile in the bank
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
;   comp_fase       the top y of the row's sprites
;   comp_fase + 1   the y of the sprite being placed
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

.assert MENU_EXP_TEXTO + MENU_EXP_LETRAS <= MENU_EXP_TEXTO_FIN, error, "the experience line does not fit in its place"
.assert MENU_FILAS_GRUPO * (MENU_EXP_TERM_TILES + 2 * MENU_EXP_LETRAS) <= MENU_EXP_SPRITES, error, "the party's experience does not fit in the sprites"

; From `menu_upload`, instead of `slot_ppu_on`: the sprites, and then
; it turns the screen on with them. With the screen off.
.proc menu_exp_paint
.a8
.i16
    phb
    lda #0
    pha
    plb                         ; the registers and the tables in bank 0
    ; 8x8 sprites with the tiles from `RANURA_VRAM`.
    lda #(RANURA_VRAM / $2000)
    sta OBSEL
    ; Sprite palette 0, the text's.
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(ranura_cgram)
    sta A1T0L
    lda #(16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ranura_cgram
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
    sta comp_fase
row:
    lda comp_char
    cmp grupo_n
    bcs filas_listas
    cmp #MENU_FILAS_GRUPO
    bcs filas_listas
    jsr one_row
    lda comp_fase
    clc
    adc #MENU_ACTOR_ALTO
    sta comp_fase
    inc comp_char
    bra row
filas_listas:
    ; The leftover ones, below the screen, and the small table at zero: an
    ; eight-bit x and the small size for all of them.
    lda comp_base
    cmp #MENU_EXP_SPRITES
    bcs ocultos_listos
    stz OAMDATA
    lda #MENU_EXP_HIDDEN
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    inc comp_base
    bra filas_listas
ocultos_listos:
    ldx #(MENU_EXP_SPRITES / 4)
tabla_chica:
    stz OAMDATA
    dex
    bne tabla_chica

    jsl f:bt_t_ppu              ; the screen, on with BG2 alone
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
    lda grupo, x
    cmp #MENU_ACTORES_N
    bcc conocido
    rts                         ; one this ROM does not know
conocido:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne con_exp
    rts                         ; one who does not fight: has no experience
con_exp:
    rep #$20
.a16
    and #$00FF
    pha                         ; k, until the end of the line
    asl a
    asl a
    tax                         ; its slot in `FAR_EXP`
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_EXP + EXP_NIVEL, x
    sta comp_dup
    ; At the cap? Dashes, like RPG_RT.
    rep #$20
.a16
    lda 1, s                    ; k
    phx
    tax
    sep #$20
.a8
    lda f:exp_nivel_max, x
    plx
    cmp comp_dup
    beq tope
    bcc tope
    ; The current one.
    rep #$20
.a16
    lda f:FAR_LARGO + FAR_EXP, x
    sta comp_or01
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_EXP + 2, x
    sta comp_or01 + 2
    ldy #0
    jsr seis_cifras
    lda #'/'
    tyx
    sta f:MENU_EXP_TEXTO, x
    iny
    ; And the next level's: its curve's row in `exp_tabla`, at the current
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
    adc f:exp_curva, x
    tax
    lda f:exp_tabla, x
    sta comp_or01
    sep #$20
.a8
    lda f:exp_tabla + 2, x
    sta comp_or01 + 2
    jsr seis_cifras
    bra sprites
tope:
    rep #$20
.a16
    pla                         ; k, which is not needed
    sep #$20
.a8
    ldx #0
guion:
    lda #'-'
    cpx #MENU_EXP_CIFRAS
    bne no_barra
    lda #'/'
no_barra:
    sta f:MENU_EXP_TEXTO, x
    inx
    cpx #MENU_EXP_LETRAS
    bcc guion

sprites:
    ; --- the term: four tiles, two on top and two below ---
    ldx #0
termino:
    lda #MENU_EXP_X
    cpx #1
    beq term_der
    cpx #3
    bne term_x
term_der:
    lda #(MENU_EXP_X + 8)
term_x:
    sta comp_mask
    lda comp_fase
    cpx #2
    bcc term_y
    clc
    adc #8
term_y:
    sta comp_fase + 1
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:menu_exp_termino, x
    jsr put
.a8
    plx
    inx
    cpx #MENU_EXP_TERM_TILES
    bcc termino

    ; --- the thirteen letters, six pixels apart; a space gets no sprite ---
    lda #MENU_EXP_NUM_X
    sta comp_mask
    ldx #0
letra:
    lda f:MENU_EXP_TEXTO, x
    cmp #' '
    beq siguiente
    phx
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; two words per letter
    tax
    sep #$20
.a8
    lda comp_fase
    sta comp_fase + 1
    rep #$20
.a16
    lda f:ranura_glifo_celdas, x
    jsr put                   ; the top cell
.a8
    lda comp_fase
    clc
    adc #8
    sta comp_fase + 1
    rep #$20
.a16
    lda f:ranura_glifo_celdas + 2, x
    jsr put                   ; and the bottom one
.a8
    plx
siguiente:
    lda comp_mask
    clc
    adc #MENU_EXP_PASO
    sta comp_mask
    inx
    cpx #MENU_EXP_LETRAS
    bcc letra
    rts

; One sprite: A16 the glyph's tilemap word —tile and palette—, at
; `comp_mask`, `comp_fase + 1`. Returns with an 8-bit A, and touches neither
; X nor Y.
.a16
put:
    sep #$20
.a8
    pha                         ; the tile's low byte
    lda comp_mask
    sta OAMDATA
    lda comp_fase + 1
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
; into `MENU_EXP_TEXTO` from Y, right-aligned with spaces, and leaves Y past
; them. It clobbers X.
seis_cifras:
    stz comp_col + 1
    ldx #0
potencia:
    stz comp_col
resta:
    rep #$20
.a16
    lda comp_or01
    sec
    sbc f:potencias, x
    sta comp_and
    sep #$20                    ; `sep` does not touch the subtraction's carry
.a8
    lda comp_or01 + 2
    sbc f:potencias + 2, x
    bcc no_alcanza
    sta comp_or01 + 2
    rep #$20
.a16
    lda comp_and
    sta comp_or01
    sep #$20
.a8
    inc comp_col
    bra resta
no_alcanza:
    lda comp_col
    ora comp_col + 1
    bne cifra
    cpx #(5 * 3)
    beq cifra                   ; the units always go, even if 0
    lda #' '
    bra escribir
cifra:
    lda #1
    sta comp_col + 1
    lda comp_col
    clc
    adc #'0'
escribir:
    phx
    tyx
    sta f:MENU_EXP_TEXTO, x
    plx
    iny
    inx
    inx
    inx
    cpx #(6 * 3)
    bcc potencia
    rts

potencias:
    .faraddr 100000, 10000, 1000, 100, 10, 1
.endproc

; When closing the menu, before `back_to_map`: what `menu_exp_paint`
; changed on the map and the map does not restore by itself. OBSEL, which
; `back_to_map` does not touch, and the colors of sprite palette 0, from
; `cgram_sombra`, which has the map's even if the tint or a picture changed
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
    ldx mapa_ofs
    lda f:mapa_tabla + M_OBSEL_VALUE, x
    sta OBSEL
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * 128)
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
