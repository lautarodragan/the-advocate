.segment "FAR"

; --- the battle scene --------------------------------------------------------
;
; The battle background with the monsters on top: a single 8bpp layer of
; 256x128 on BG1, which is the seven text lines at the top. **It is composed
; here, when the battle starts**, from a background and the troop's
; battlers, which the cartridge carries once each. The why, the format and
; the budget are in tools/port/escena.py.
;
; It runs from `batalla_correr` with the data bank at $7E, so the PPU
; registers and the cartridge's tables all go with `f:`, and the state here
; is named with a sixteen-bit address, like `FAR_BATALLA`.
;
; **$7E6600 to $7E67FF belongs to this**: the range was reserved in advance
; on 2026-09-21, when splitting work among tasks that touched far RAM.
ESC_ORIGEN   = $6600    ; 1: a random encounter started the battle
; The number of this battle's background among the game's, or FONDO_LISO.
; It is the one read from the `.msu`; the ROM's is ESC_RESPALDO. See "Qué
; fondos hay" in tools/port/escena.py.
ESC_FONDO    = $6601
ESC_VIS      = $6602    ; one bit per enemy: still drawn
ESC_PAL_N    = $6603    ; how many battler palettes were handed out
ESC_PAL_BAT  = $6604    ; 8 bytes: which battler each one holds
ESC_E_BAT    = $6610    ; 8 bytes: each enemy's battler, or $FF
ESC_E_PAL    = $6618    ; 8 bytes: its palette, 0 to 7
ESC_E_X      = $6620    ; 8 bytes: its corner in the scene
ESC_E_Y      = $6628
; What is left to upload to VRAM of an enemy that was just erased: whole tile
; rows of the scene, `ESC_SUB_BUDGET` bytes per vblank.
ESC_SUB_N    = $6630    ; word: how many tile rows are left; 0 is none
ESC_SUB_FILA = $6632    ; word: the next one
ESC_SUB_COL  = $6634    ; word: the first tile column
ESC_SUB_LARGO = $6636   ; word: how many bytes each row is
; How many frames composing took, counted with `boot_cuadros`: the ROM does
; not read it; the tests read it, and so does whoever wants to measure it with
; the emulator.
ESC_CUADROS  = $6638
ESC_T0       = $663A    ; scratch
ESC_E        = $663C    ; the enemy being placed or erased
ESC_I        = $663D
; The rectangle a battler is clipped to when placed: pixel rows [Y0, Y1)
; and tile columns [C0, C1) of the scene, in words.
ESC_CLIP_Y0  = $6640
ESC_CLIP_Y1  = $6642
ESC_CLIP_C0  = $6644
ESC_CLIP_C1  = $6646
; Where the walk is in the drawing order, and where the troop starts in the
; `miembro_*` tables. See `esc_por_orden`.
ESC_K        = $6648
ESC_INI      = $6649
; 1 if this battle's background comes from the MSU-1 and not from the
; cartridge: see `esc_llenar`. The tests read it too, to know which path
; ran.
ESC_MSU      = $664A
; Which of the ROM's backgrounds is drawn without MSU-1: ESC_FONDO's if the
; cartridge carries it, the replacement if not. Only valid with ESC_FONDO
; set.
ESC_RESPALDO = $664B
; What was on the direct page that gets borrowed: see `esc_dp_tomar`.
ESC_DP_GUARDA = $6680
ESC_DP_BYTES = 48

; The clean background and the composed scene, 32 KB each, in WRAM bank
; $7F, which nobody used: everything else in the ROM lives in $7E —far RAM
; goes up to $7E67FF— and no `WMADDH` is written with anything but zero. The
; clean one is what lets an enemy be erased without reading anything from
; the cartridge again: see `escena_tick`.
ESC_LIMPIO   = $7F0000
ESC_ESCENA   = $7F8000
; How many scene bytes are uploaded per vblank when an enemy is erased. The
; NTSC vblank allows about six kilobytes of DMA and `pant_subir` already
; takes the text's 1,792 in the same vblank; two more leave some margin.
ESC_SUB_BUDGET = 2048

; --- the borrowed direct page ---
;
; The `escena_poner` loop reads the battler with `[puntero], y` —its bank
; changes with each battler— and that only exists with the direct page. The
; game's is full, so a page of `pal_buf`, which the battle does not use, is
; borrowed, and what it held **is saved and restored**: the battle does not
; touch it, but coming back from it with the flash half built has no reason
; to find it overwritten. Neither the NMI nor `irq_musica` read `pal_buf`,
; and the IRQ sets its own direct page to zero.
;
; The page is aligned to 256: an unaligned direct page costs one extra cycle
; on every access, and the loop does ten per column. `pal_buf` is 512 long,
; so it always has an aligned page inside.
ED_M   = $00    ; the five 24-bit pointers, one per plane
ED_P0  = $03
ED_P1  = $06
ED_P2  = $09
ED_P3  = $0C
ED_TM  = $10    ; the mask, and a zero next to it
ED_T0  = $12    ; the four planes, one byte each: ED_T0 and ED_T2 are read as
ED_T1  = $13    ; words, which are the tile's 0/1 and 2/3 pairs
ED_T2  = $14
ED_T3  = $15
ED_MM  = $18    ; the mask in both bytes
ED_NM  = $1A    ; and negated
ED_P45 = $1C    ; planes 4 to 7, which depend on the palette
ED_P67 = $1E
ED_FX  = $20    ; where the row starts in the scene
ED_FY  = $22    ; and in the battler
ED_COLS = $24   ; how many tile columns
ED_CUENTA = $26
ED_FILAS = $28
ED_YY  = $2A    ; the scene's pixel row
ED_PASO = $2C   ; how long one row of a plane is
ED_N   = $2E    ; how many columns the battler has
; And those of `esc_doblar`, which runs before anybody is placed.
ED_FUENTE = $00 ; the 24-bit pointer to the fallback, which advances
ED_PALABRAS = $04 ; how many two-plane words of the tile pair are left

.proc esc_dp_tomar
.a8
.i16
    rep #$20
.a16
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tax
    ldy #0
guarda:
    lda a:$0000, x              ; low RAM: in bank $7E it is the same
    sta ESC_DP_GUARDA, y
    inx
    inx
    iny
    iny
    cpy #ESC_DP_BYTES
    bcc guarda
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tcd
    sep #$20
.a8
    rts
.endproc

.proc esc_dp_devolver
.a8
.i16
    rep #$20
.a16
    lda #0
    tcd
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tax
    ldy #0
repone:
    lda ESC_DP_GUARDA, y
    sta a:$0000, x
    inx
    inx
    iny
    iny
    cpy #ESC_DP_BYTES
    bcc repone
    sep #$20
.a8
    rts
.endproc

; --- placing a battler ---
;
; The inner loop, once for each shift: a battler that does not start on a
; tile edge is shifted `CORRE` bits to the right, and the `lsr`s are unrolled
; because they are half the cost. Per tile column and pixel row: five reads
; from the battler —the mask and four planes—, each one sixteen bits to also
; bring in the column to the left, and four words of the scene, which are
; the tile's eight planes in pairs. A column with nothing of the battler is
; skipped entirely.
;
; With 16-bit A, X and Y: X is the offset in the scene and Y in the
; battler. See `escena_poner`, which is the one that sets all this up.
.macro ESC_LAZO CORRE
.local fila, col, vacia, otro_tile, puesta
fila:
    ldx ED_FX
    ldy ED_FY
    lda ED_COLS
    sta ED_CUENTA
col:
    lda [ED_M], y
    .repeat CORRE
    lsr a
    .endrepeat
    and #$00FF
    beq vacia
    sta ED_TM
    xba
    ora ED_TM
    sta ED_MM
    eor #$FFFF
    sta ED_NM
    ; Each plane is stored as a word and the next one overwrites the high
    ; byte, which is garbage from the shift: that way ED_T0 ends up with
    ; planes 0 and 1 together and ED_T2 with 2 and 3.
    lda [ED_P0], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T0
    lda [ED_P1], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T1
    lda [ED_P2], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T2
    lda [ED_P3], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T3
    ; background AND NOT mask OR battler, on the drawing's planes
    lda f:ESC_ESCENA, x
    and ED_NM
    ora ED_T0
    sta f:ESC_ESCENA, x
    lda f:ESC_ESCENA + 16, x
    and ED_NM
    ora ED_T2
    sta f:ESC_ESCENA + 16, x
    ; and on the palette's, which are the mask or nothing:
    ; ((background ^ palette) & mask) ^ background
    lda f:ESC_ESCENA + 32, x
    eor ED_P45
    and ED_MM
    eor f:ESC_ESCENA + 32, x
    sta f:ESC_ESCENA + 32, x
    lda f:ESC_ESCENA + 48, x
    eor ED_P67
    and ED_MM
    eor f:ESC_ESCENA + 48, x
    sta f:ESC_ESCENA + 48, x
vacia:
    dey                         ; the column to the right: see `battler_bytes`
    txa
    clc
    adc #64                     ; the next tile
    tax
    dec ED_CUENTA
    beq :+
    jmp col                     ; with seven `lsr`s the body does not fit in a `bne`
:
    ; The next row: in the battler, the length of one row of a plane; in the
    ; scene, two bytes, unless it moves to another tile row.
    lda ED_FY
    clc
    adc ED_PASO
    sta ED_FY
    lda ED_YY
    and #7
    cmp #7
    beq otro_tile
    lda ED_FX
    inc a
    inc a
    bra puesta
otro_tile:
    lda ED_FX
    clc
    adc #(ESCENA_COLUMNAS * 64 - 14)
puesta:
    sta ED_FX
    inc ED_YY
    dec ED_FILAS
    beq :+
    jmp fila
:   rts
.endmacro

.a16
.i16
esc_lazo_0: ESC_LAZO 0
esc_lazo_1: ESC_LAZO 1
esc_lazo_2: ESC_LAZO 2
esc_lazo_3: ESC_LAZO 3
esc_lazo_4: ESC_LAZO 4
esc_lazo_5: ESC_LAZO 5
esc_lazo_6: ESC_LAZO 6
esc_lazo_7: ESC_LAZO 7
esc_lazos:
    .addr esc_lazo_0, esc_lazo_1, esc_lazo_2, esc_lazo_3
    .addr esc_lazo_4, esc_lazo_5, esc_lazo_6, esc_lazo_7
; Each enemy's bit in `ESC_VIS`.
esc_bits:
    .byte $01, $02, $04, $08, $10, $20, $40, $80
.a8

; `ESC_E` = the enemy that comes `ESC_K`-th in the drawing order, which is
; RM2k's and not the troop's: easyrpg's `Sprite_Battler::ResetZ` sorts by
; the battler's bottom edge, and with equal edges the one with the lower
; place ends up on top. The converter computes the order: `miembro_orden`.
; It clobbers X.
.proc esc_por_orden
.a8
.i16
    rep #$20
.a16
    lda ESC_K
    clc
    adc ESC_INI
    and #$00FF
    tax
    sep #$20
.a8
    lda f:miembro_orden, x
    sta ESC_E
    rts
.endproc

; A8: `ESC_E`'s bit in `ESC_VIS`. It clobbers X.
.proc esc_bit
.a8
.i16
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    sep #$20
.a8
    lda f:esc_bits, x
    rts
.endproc

; Enemy `ESC_E` onto the scene in `ESC_ESCENA`, clipped to `ESC_CLIP_*`.
; With the direct page already borrowed. If it has no battler, or if the
; clip leaves it out, it does nothing.
.proc escena_poner
.a8
.i16
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    sep #$20
.a8
    lda ESC_E_BAT, x
    cmp #$FF
    bne hay
    rts
hay:
    ; --- the battler: its measurements and its five pointers ---
    rep #$20
.a16
    and #$00FF
    tay                         ; Y: the battler
    asl a
    asl a
    tax                         ; X: its 24-bit pointer
    lda f:battler_dir, x
    sta ED_M
    sep #$20
.a8
    lda f:battler_dir + 2, x
    sta ED_M + 2
    sta ED_P0 + 2
    sta ED_P1 + 2
    sta ED_P2 + 2
    sta ED_P3 + 2
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:battler_plano, x
    sta ESC_T0
    lda ED_M
    clc
    adc ESC_T0
    sta ED_P0
    adc ESC_T0                  ; there is no carry: the battler does not cross a bank
    sta ED_P1
    adc ESC_T0
    sta ED_P2
    adc ESC_T0
    sta ED_P3
    tyx
    lda f:battler_n, x
    and #$00FF
    sta ED_N
    inc a
    sta ED_PASO
    lda f:battler_alto, x
    and #$00FF
    sta ED_FILAS                ; not clipped yet

    ; --- the palette: planes 4 to 7 of each battler pixel ---
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_PAL, x
    and #$0007
    sta ESC_T0
    lda #0
    lsr ESC_T0
    bcc :+
    ora #$00FF                  ; bit 0 is plane 4
:   lsr ESC_T0
    bcc :+
    ora #$FF00                  ; bit 1, plane 5
:   sta ED_P45
    lda #$FF00                  ; plane 7 is palette 8 onward
    lsr ESC_T0
    bcc :+
    ora #$00FF                  ; and bit 2, plane 6
:   sta ED_P67

    ; --- the columns: how many, from which, and how far the clip allows ---
    lda ESC_E_X, x
    and #$00FF
    sta ESC_T0
    and #7
    sta ED_CUENTA               ; the shift, borrowed for a moment
    lda ED_N
    ldy ED_CUENTA
    beq :+
    inc a                       ; shifted, it takes one more column
:   sta ED_COLS
    lda ESC_T0
    lsr a
    lsr a
    lsr a
    sta ESC_T0                  ; the battler's first tile column
    ; The right one, capped at the clip and at the scene's edge.
    clc
    adc ED_COLS
    cmp ESC_CLIP_C1
    bcc :+
    lda ESC_CLIP_C1
:   sta ED_COLS                 ; now it is the final column, not how many
    ; The left one: the battler's or the clip's.
    lda ESC_T0
    cmp ESC_CLIP_C0
    bcs :+
    lda ESC_CLIP_C0
:   sta ED_FX                   ; the first column touched, borrowed
    lda ED_COLS
    sec
    sbc ED_FX
    bcs :+
    jmp afuera
:   bne :+
    jmp afuera
:   sta ED_COLS                 ; how many
    ; The battler column it starts at, which is the one that gives Y.
    lda ED_FX
    sec
    sbc ESC_T0
    sta ESC_T0                  ; battler columns that are skipped
    lda ED_N
    sec
    sbc ESC_T0
    sta ED_FY                   ; its place in the row: see `battler_bytes`

    ; --- the rows ---
    lda ESC_E_Y, x
    and #$00FF
    sta ED_YY
    clc
    adc ED_FILAS
    cmp ESC_CLIP_Y1
    bcc :+
    lda ESC_CLIP_Y1
:   sta ED_FILAS                ; the final row
    lda ED_YY
    cmp ESC_CLIP_Y0
    bcs :+
    lda ESC_CLIP_Y0
:   sta ESC_T0                  ; the first one
    lda ED_FILAS
    sec
    sbc ESC_T0
    bcs :+
    jmp afuera
:   bne :+
    jmp afuera
:   sta ED_FILAS
    ; The battler rows that are skipped, times the length of each.
    lda ESC_T0
    sec
    sbc ED_YY
    tay
    lda ESC_T0
    sta ED_YY
    lda ED_FY
salta_fila:
    cpy #0
    beq filas_listas
    clc
    adc ED_PASO
    dey
    bra salta_fila
filas_listas:
    sta ED_FY
    ; And in the scene: (row / 8) * 2048 + column * 64 + (row % 8) * 2.
    lda ED_FX
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ED_FX
    lda ED_YY
    and #7
    asl a
    clc
    adc ED_FX
    sta ED_FX
    lda ED_YY
    and #$00F8
    xba                         ; times 256, that is (row / 8) * 2048
    clc
    adc ED_FX
    sta ED_FX

    ; --- the matching loop, which returns with everything in sixteen bits ---
    lda ESC_E
    and #$00FF
    tay
    lda ESC_E_X, y
    and #7
    asl a
    tax
    jsr (esc_lazos, x)
    sep #$20
.a8
    rts
afuera:
.a16
    sep #$20
.a8
    rts
.endproc

; --- composing the whole scene, when the battle starts ---
;
; With the screen off. Fills both buffers with the background —or with
; zeros—, places the troop's battlers in order and uploads everything: the
; 32 KB of tiles, the tilemap, the background's colors and one palette per
; distinct battler. Leaves in `BA_ESCENA` a 0 if there is something to show
; and $FF if not.
.proc escena_subir
.a8
.i16
    lda f:boot_cuadros
    sta ESC_CUADROS
    lda #0
    sta ESC_CUADROS + 1
    sta ESC_VIS
    sta ESC_PAL_N
    rep #$20
.a16
    lda #0
    sta ESC_SUB_N
    sep #$20
.a8

    ; --- which background: the map's if it was an encounter, the troop's if not ---
    ;
    ; And the map's can be that of the terrain the hero stands on, just as a
    ; troop can fight with the place's: it is `Game_Map::SetupBattle`. See
    ; `escena_de_la_rom` in tools/port/snes_convert.py.
    lda #FONDO_LISO
    sta ESC_FONDO
    lda ESC_ORIGEN
    beq de_la_tropa
del_lugar:
    rep #$20
.a16
    lda mapa_actual
    tax
    sep #$20
.a8
    lda f:escena_mapa_fondo, x
    cmp #FONDO_DEL_LUGAR
    bne fondo_elegido
    jsr esc_terreno             ; the terrain under the hero, in A
    cmp #FONDO_TERRENOS
    bcs sin_fondo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:fondo_terreno, x
    bra fondo_elegido
de_la_tropa:
    lda BA_TROPA_K
    cmp #$FF
    beq sin_fondo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:escena_tropa_fondo, x
    cmp #FONDO_DEL_LUGAR
    beq del_lugar
fondo_elegido:
    cmp #FONDOS_JUEGO
    bcs sin_fondo               ; FONDO_LISO, or a cartridge with no backgrounds
    sta ESC_FONDO
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:fondo_respaldo, x     ; its own if the ROM carries it, or the replacement
    sta ESC_RESPALDO
sin_fondo:
    lda #0
    sta ESC_ORIGEN              ; only `encuentro_probar` sets it

    ; --- the troop's battlers, and one palette for each distinct one ---
    lda #0
    sta ESC_E
    lda BA_TROPA_K
    cmp #$FF
    bne con_tropa
    jmp repartidos
con_tropa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_ini, x
    sta ESC_I                   ; the first member
    sta ESC_INI                 ; and again, for `esc_por_orden`
otro_enemigo:
    lda ESC_E
    cmp BA_NENE
    bcc :+
    jmp repartidos
:   rep #$20
.a16
    lda ESC_E
    and #$00FF
    tay                         ; Y: the enemy
    clc
    adc ESC_I
    and #$00FF
    tax                         ; X: the member
    sep #$20
.a8
    lda f:miembro_x, x
    sta ESC_E_X, y
    lda f:miembro_y, x
    sta ESC_E_Y, y
    lda f:miembro_battler, x
    sta ESC_E_BAT, y
    cmp #$FF
    beq siguiente
    ; Does that battler already have a palette? The limit, as a word for `cpx`.
    pha
    rep #$20
.a16
    lda ESC_PAL_N
    and #$00FF
    sta ESC_T0
    sep #$20
.a8
    pla
    ldx #0
busca_pal:
    cpx ESC_T0
    beq pal_nueva
    cmp ESC_PAL_BAT, x
    beq pal_lista
    inx
    bra busca_pal
pal_nueva:
    sta ESC_PAL_BAT, x
    inc ESC_PAL_N
pal_lista:
    txa
    sta ESC_E_PAL, y
    ; And the drawn bit, which is what `escena_tick` looks at. A hidden one
    ; is not drawn: it gets its palette, and `escena_tick` places it when it
    ; appears.
    lda ESC_E
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_OCULTO
    bne siguiente
    jsr esc_bit
    ora ESC_VIS
    sta ESC_VIS
siguiente:
    inc ESC_E
    jmp otro_enemigo
repartidos:
    lda ESC_FONDO
    cmp #$FF
    bne hay_escena
    lda ESC_VIS
    bne hay_escena
    jmp sin_escena              ; neither background nor battlers: on black, as before
hay_escena:
    lda #0
    sta BA_ESCENA

    ; --- where the background comes from: the MSU-1 if present and it is this cartridge's ---
    sta ESC_MSU
    lda ESC_FONDO
    cmp #$FF
    beq sin_msu                 ; the plain one is not read from anywhere
    jsr msu_datos_validos
    sta ESC_MSU
sin_msu:

    ; --- the background: its colors and both buffers ---
    lda ESC_MSU
    pha
    jsr esc_fondo
    ; If it started from the `.msu` and some seek did not make it in time,
    ; what was already read from there is the high-quality background and
    ; what follows the light one: they share neither colors nor tiles.
    ; Everything again from the ROM, which does not fail.
    pla
    cmp #0                      ; `pla` leaves Z from what it pulled, not from ESC_MSU
    beq fondo_listo
    lda ESC_MSU
    bne fondo_listo
    jsr esc_fondo
fondo_listo:

    ; --- the battlers, in drawing order: the later one covers ---
    rep #$20
.a16
    lda #0
    sta ESC_CLIP_Y0
    sta ESC_CLIP_C0
    lda #ESCENA_ALTO
    sta ESC_CLIP_Y1
    lda #ESCENA_COLUMNAS
    sta ESC_CLIP_C1
    sep #$20
.a8
    jsr esc_dp_tomar
    lda #0
    sta ESC_K
poner:
    lda ESC_K
    cmp BA_NENE
    bcs puestos
    jsr esc_por_orden
    jsr esc_bit                 ; only the visible ones: not a hidden one
    and ESC_VIS
    beq :+
    jsr escena_poner
:   inc ESC_K
    bra poner
puestos:
    jsr esc_dp_devolver

    ; --- the composed scene, to VRAM ---
    lda #$80
    sta f:VMAIN                 ; one word per write
    rep #$20
.a16
    lda #ESCENA_VRAM
    sta f:VMADDL
    lda #.loword(ESC_ESCENA)
    sta f:A1T0L
    lda #(ESCENA_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^ESC_ESCENA
    sta f:A1B0
    lda #$01                    ; two registers: VMDATAL and VMDATAH
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN

    ; --- the transparent tile, at word 0 ---
    rep #$20
.a16
    lda #0
    sta f:VMADDL
    lda #64
    sta f:DAS0L
    lda #.loword(escena_cero)
    sta f:A1T0L
    sep #$20
.a8
    lda #^escena_cero
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN

    ; --- the tilemap: the 512 tiles in order and the rest covered ---
    ;
    ; It is written by hand and not by DMA: they are the numbers 0, 1, 2...
    ; and emitting them would be two kilobytes of cartridge to say that.
    rep #$20
.a16
    lda #ESCENA_MAPA
    sta f:VMADDL
    lda #0
    sta ESC_T0                  ; the tile that goes in the cell
    ldx #0
celda:
    cpx #ESCENA_TILES
    bcc celda_escena
    lda #ESCENA_BLANCO
    bra celda_pone
celda_escena:
.a16
    lda ESC_T0
celda_pone:
.a16
    sta f:VMDATAL
    inc ESC_T0
    inx
    cpx #(32 * 32)
    bcc celda
    sep #$20
.a8

    ; --- and a sixteen-color palette per battler, from 8 on ---
colores_battlers:
    lda #0
    sta ESC_I
otra_paleta:
    lda ESC_I
    cmp ESC_PAL_N
    bcs listo
    asl a
    asl a
    asl a
    asl a
    clc
    adc #(ESCENA_BAT_PALETA * 16)
    sta f:CGADD
    rep #$20
.a16
    lda ESC_I
    and #$00FF
    tax
    lda ESC_PAL_BAT, x
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32
    clc
    adc #.loword(battler_cgram)
    sta f:A1T0L
    lda #32
    sta f:DAS0L
    sep #$20
.a8
    lda #^battler_cgram
    jsr esc_dma_cgram
    inc ESC_I
    bra otra_paleta
listo:
    lda f:boot_cuadros
    sec
    sbc ESC_CUADROS
    sta ESC_CUADROS
    rts
sin_escena:
.a8
    lda #$FF
    sta BA_ESCENA
    rts
.endproc

; The terrain of the cell the hero is on, in A: what `StoreTerrainID` would
; answer —see `op_terrain`, which is where this comes from—, for the
; background of a battle on a map that does not name its own. It runs when
; the battle starts, before `esc_llenar` overwrites the upper half of $7F,
; which may belong to the grid. `celda_sustituida` is in bank 0, so its
; lookup is copied here.
.proc esc_terreno
.a8
.i16
    ldx mapa_ofs
    lda f:mapa_tabla + M_TERRENO_PLANO, x
    bne listo                   ; a single terrain on the whole map
    rep #$20
.a16
    lda [hero_ptr]              ; which block the hero's cell is
    ldy sub_n
    beq sustituida
buscar:
    dey
    dey
    cmp sub_clave, y
    beq hallada
    cpy #$0000
    bne buscar
    bra sustituida
hallada:
    lda sub_valor, y
sustituida:
    sta ESC_T0
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO + 2, x
    sta celdas_ptr + 2
    ldy ESC_T0
    lda [celdas_ptr], y
listo:
    rts
.endproc

; The background of `ESC_FONDO`, from wherever `ESC_MSU` says: its colors
; and both buffers. If a `.msu` seek does not make it in time, it leaves
; ESC_MSU at 0 and goes on from the ROM: see who calls it.
;
; From the ROM, `esc_llenar` leaves only the fixed planes in both buffers,
; and `esc_doblar` enlarges the fallback into both at once. If the first came
; from the `.msu` and the second did not, `esc_doblar` overwrites the bottom
; half of every tile of the first; it does not matter, because
; `escena_subir` redoes everything from the ROM.
.proc esc_fondo
.a8
.i16
    jsr esc_colores
    lda #0
    jsr esc_llenar
    lda #$80
    jsr esc_llenar
    lda ESC_MSU
    bne listo
    lda ESC_FONDO
    cmp #$FF
    beq listo                   ; the plain one is already there: it is zeros
    jsl f:esc_doblar + RAPIDO   ; from the fast mirror: see MEMSEL
listo:
    rts
.endproc

; The background's colors, from entry ESCENA_CGRAM: the high-quality one's
; 96 if it comes from the `.msu`, the light one's 16 if it comes from the
; ROM. Nothing with the plain one.
.proc esc_colores
.a8
.i16
    lda ESC_FONDO
    cmp #$FF
    bne hay
    rts
hay:
    lda #ESCENA_CGRAM
    sta f:CGADD
    lda ESC_MSU
    beq de_la_rom
    ; From the `.msu`: its color entry is the background's second one.
    rep #$20
.a16
    lda ESC_FONDO
    and #$00FF
    asl a
    asl a
    asl a                       ; times 8: two 32-bit positions
    tax
    lda f:msu_fondo_pos + 6, x
    tay
    lda f:msu_fondo_pos + 4, x
    jsr msu_datos_buscar
.a8
    bcs no_la_encontro
    rep #$20
.a16
    lda #(ESCENA_COLORES * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #$22                    ; CGDATA
    jmp esc_dma_msu
no_la_encontro:
    lda #0
    sta ESC_MSU
de_la_rom:
    rep #$20
.a16
    lda ESC_RESPALDO
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32, which is RESPALDO_COLORES * 2
    .assert RESPALDO_COLORES * 2 = 32, error, "fondo_cgram changed its stride"
    clc
    adc #.loword(fondo_cgram)
    sta f:A1T0L
    lda #(RESPALDO_COLORES * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #^fondo_cgram
    jmp esc_dma_cgram
.endproc

; The DMA to CGRAM with source and length already set: A the source bank.
.proc esc_dma_cgram
.a8
.i16
    sta f:A1B0
    lda #0
    sta f:DMAP0                 ; `stz` has no long mode
    lda #$22
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rts
.endproc

; The DMA from the MSU-1's data port, with the length already set and the
; `.msu` already seeked: A is the destination B-bus register. The source is
; $2001 **fixed** —bit 3 of DMAP—: it is a register that advances by itself,
; not memory.
.proc esc_dma_msu
.a8
.i16
    sta f:BBAD0
    rep #$20
.a16
    lda #MSU_DATOS
    sta f:A1T0L
    sep #$20
.a8
    lda #0                      ; bank 0, where the MSU-1 lives
    sta f:A1B0
    lda #$08                    ; one byte at a time, with the source fixed
    sta f:DMAP0
    lda #$01
    sta f:MDMAEN
    rts
.endproc

; One of the scene's two buffers, with `ESC_FONDO`'s background or with
; zeros: A is the middle byte of its address, 0 the clean one and $80 the
; composed one. Through the WRAM window, which is the only way to copy from
; ROM to RAM by DMA; the bank is $7F, so WMADDH is 1.
.proc esc_llenar
.a8
.i16
    sta f:WMADDM
    sta ESC_T0 + 1              ; and again, for the ROM path
    lda #0
    sta ESC_T0
    sta f:WMADDL
    lda #1
    sta f:WMADDH
    lda #$80                    ; WMDATA
    sta f:BBAD0
    lda ESC_FONDO
    cmp #$FF
    bne con_fondo
    ; The plain background: the same zero 32,768 times, with the source fixed.
    rep #$20
.a16
    lda #.loword(escena_cero)
    sta f:A1T0L
    lda #(ESCENA_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^escena_cero
    sta f:A1B0
    lda #$08
    sta f:DMAP0
    lda #$01
    sta f:MDMAEN
    rts
con_fondo:
    lda ESC_MSU
    beq de_la_rom
    ; From the `.msu`, the 32 KB at once: the start of the tiles is sought
    ; every time, because the stream already advanced to the end with the
    ; previous buffer. Copying from one buffer to the other cannot be done
    ; by DMA —WRAM to WRAM does not work— and with `mvn` it would be several
    ; frames.
    rep #$20
.a16
    lda ESC_FONDO
    and #$00FF
    asl a
    asl a
    asl a                       ; times 8: two 32-bit positions
    tax
    lda f:msu_fondo_pos + 2, x
    tay
    lda f:msu_fondo_pos, x
    jsr msu_datos_buscar
.a8
    bcs no_la_encontro
    rep #$20
.a16
    lda #(ESCENA_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #$80                    ; WMDATA
    jmp esc_dma_msu
no_la_encontro:
    ; The MSU-1 did not finish seeking in time: this buffer comes from the
    ; ROM, and `escena_subir` redoes the rest from there.
    lda #0
    sta ESC_MSU
de_la_rom:
    ; From the ROM, only planes 4 to 7 go here, which are the same on every
    ; pixel of the fallback: the 32 bytes of `respaldo_alto` in the top half
    ; of every tile, rewinding the source and moving WMADD on each one.
    ; `esc_doblar` fills the bottom half afterwards. See "El respaldo
    ; liviano" in tools/port/escena.py.
    lda #0
    sta f:DMAP7                 ; one byte at a time, the source advancing
    lda #$80                    ; WMDATA
    sta f:BBAD7
    lda #^respaldo_alto
    sta f:A1B7
    rep #$20
.a16
    lda ESC_T0
    clc
    adc #RESPALDO_TILE          ; the top half of the first tile
    tax
    ldy #ESCENA_TILES
tile:
    txa
    sta f:WMADDL                ; and WMADDM; WMADDH stays at $7F
    lda #(64 - RESPALDO_TILE)
    sta f:DAS7L
    lda #.loword(respaldo_alto)
    sta f:A1T7L
    sep #$20
.a8
    lda #$80                    ; channel 7
    sta f:MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #64
    tax
    dey
    bne tile
    sep #$20
.a8
    rts
.endproc

; The fallback of `ESC_RESPALDO`, enlarged to double size in both buffers:
; the bottom half of every tile, which is its planes 0 to 3. `esc_llenar`
; already put the top ones there.
;
; It is CPU and not DMA because each small pixel is two across, and in
; planar that means splitting every byte in two: `respaldo_doble` does it, a
; table of 256 words. `respaldo_bytes`, in tools/port/snes_convert.py,
; leaves the bytes in the order they are read here, so the ROM only moves
; forward: for each pair of neighboring scene tiles —the left and right ones
; that come from the same row of a small tile—, eight two-plane words, each
; written on two rows —the small row, doubled vertically— and into both
; buffers.
;
; It is entered with `jsl` through the fast mirror, and runs with the data
; bank at $7F, so the buffers go with `a:`.
.proc esc_doblar
.a8
.i16
    jsr esc_dp_tomar
    lda ESC_RESPALDO
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; times 4: the row of `fondo_dir`
    tax
    lda f:fondo_dir, x
    sta ED_FUENTE
    sep #$20
.a8
    lda f:fondo_dir + 2, x
    ora #^RAPIDO                ; the fallback, through the fast mirror
    sta ED_FUENTE + 2
    phb
    lda #^ESC_LIMPIO
    pha
    plb
    .assert ^ESC_ESCENA = ^ESC_LIMPIO, error, "the scene buffers changed bank"
    .assert RESPALDO_ESCALA = 2, error, "esc_doblar only enlarges to double size"
    rep #$20
.a16
    ldy #0                      ; the pair's left tile, in the buffers
par:
    lda #8
    sta ED_PALABRAS
palabra:
    ; The front byte gives the left tile's row; the back one, the right
    ; one's. Each, through the table, is the whole two-plane word.
    lda [ED_FUENTE]
    and #$00FF
    asl a
    tax
    lda f:respaldo_doble + RAPIDO, x
    sta a:.loword(ESC_LIMPIO), y
    sta a:.loword(ESC_LIMPIO) + 2, y
    sta a:.loword(ESC_ESCENA), y
    sta a:.loword(ESC_ESCENA) + 2, y
    lda [ED_FUENTE]
    xba
    and #$00FF
    asl a
    tax
    lda f:respaldo_doble + RAPIDO, x
    sta a:.loword(ESC_LIMPIO) + 64, y
    sta a:.loword(ESC_LIMPIO) + 66, y
    sta a:.loword(ESC_ESCENA) + 64, y
    sta a:.loword(ESC_ESCENA) + 66, y
    ; The fallback does not cross a bank —it is a `.bloque`—, so the low
    ; sixteen bits are enough.
    inc ED_FUENTE
    inc ED_FUENTE
    ; The next two rows: four bytes further on. Those of planes 2/3 start at
    ; 16, which is exactly where the fourth of 0/1 ends.
    iny
    iny
    iny
    iny
    dec ED_PALABRAS
    bne palabra
    ; The next pair: the 128 bytes of the two tiles, minus the 32 already
    ; advanced.
    tya
    clc
    adc #(128 - 32)
    tay
    cpy #(ESCENA_TILES * 64)
    bcc par
    sep #$20
.a8
    plb
    jsr esc_dp_devolver
    rtl
.endproc

; --- erasing a dead enemy, and placing one that appears ---
;
; Once per frame, from the battle loop and **inside the vblank**, right after
; `ba_t_subir`. If rows of a just-erased enemy were left un-uploaded, it
; uploads the ones that fit and returns. Otherwise, it looks for a dead one
; that is still visible and erases it —or one that appeared and is not
; visible, and places it, by the same path—: the cells it covered go back to
; being the clean background's, the ones still alive are put back on top
; —clipped to those cells and in drawing order, so that who covers whom does
; not change— and it is queued for the following vblanks. One per frame: two
; that die in the same turn are erased one after the other.
;
; RM2k makes it disappear with a fade; here it goes all at once, in the
; frames it takes to upload.
.proc escena_tick
.a8
.i16
    lda BA_ESCENA
    cmp #$FF
    bne hay
    rts
hay:
    rep #$20
.a16
    lda ESC_SUB_N
    beq buscar
    jmp subir
buscar:
    sep #$20
.a8
    lda #0
    sta ESC_E
otro:
    lda ESC_E
    cmp BA_NENE
    bcc :+
    rts
:   ; Is it drawn?
    jsr esc_bit
    sta ESC_T0
    and ESC_VIS
    beq no_dibujado
    ; And dead?
    lda ESC_E
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sep #$20
.a8
    beq borrar
siguiente:
    inc ESC_E
    bra otro
no_dibujado:
    ; And is it in the battle? It is one that was hidden and
    ; `ShowHiddenMonster` brought out: it is placed the same way one is
    ; erased, with its cells redone from the clean background and the
    ; visible ones on top in drawing order, and it among them. One with no
    ; battler has nothing to place.
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    sep #$20
.a8
    lda ESC_E_BAT, x
    cmp #$FF
    beq siguiente
    lda ESC_E
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    beq siguiente
    lda ESC_T0
    ora ESC_VIS
    sta ESC_VIS
    bra repintar

borrar:
    lda ESC_T0
    eor #$FF
    and ESC_VIS
    sta ESC_VIS
repintar:
    ; The rectangle, in tiles: the columns it touches and the whole rows.
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_BAT, x
    and #$00FF
    tay
    lda ESC_E_X, x
    and #$00FF
    sta ESC_T0
    lsr a
    lsr a
    lsr a
    sta ESC_CLIP_C0
    sta ESC_SUB_COL
    tyx
    lda f:battler_n, x
    and #$00FF
    sta ESC_CLIP_C1             ; while we are at it
    lda ESC_T0
    and #7
    beq :+
    inc ESC_CLIP_C1             ; shifted, it takes one more
:   lda ESC_CLIP_C1
    clc
    adc ESC_CLIP_C0
    cmp #ESCENA_COLUMNAS
    bcc :+
    lda #ESCENA_COLUMNAS
:   sta ESC_CLIP_C1
    sec
    sbc ESC_CLIP_C0
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ESC_SUB_LARGO           ; bytes per tile row
    lda f:battler_alto, x
    and #$00FF
    sta ESC_T0
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_Y, x
    and #$00FF
    pha
    and #$00F8
    sta ESC_CLIP_Y0             ; from the first row of its first tile
    lsr a
    lsr a
    lsr a
    sta ESC_SUB_FILA
    pla
    clc
    adc ESC_T0
    clc
    adc #7
    and #$00F8
    sta ESC_CLIP_Y1             ; to the last row of its last tile
    sec
    sbc ESC_CLIP_Y0
    lsr a
    lsr a
    lsr a
    sta ESC_SUB_N

    ; --- the cells, from the clean background ---
    ; Tile row by tile row with `mvn`, which copies inside bank $7F and
    ; leaves the data bank there: it is saved and restored.
    lda ESC_SUB_FILA
    sta ESC_T0
    lda ESC_SUB_N
    sta ESC_I                   ; and ESC_I + 1: used as a word here
copia:
    lda ESC_T0
    xba                         ; row * 256...
    lsr a
    lsr a
    lsr a                       ; ...over eight: row * 32 tiles
    clc
    adc ESC_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 64 bytes
    tax
    clc
    adc #.loword(ESC_ESCENA)
    tay
    lda ESC_SUB_LARGO
    dec a                       ; `mvn` copies A + 1
    phb
    mvn #^ESC_LIMPIO, #^ESC_ESCENA
    plb
    inc ESC_T0
    dec ESC_I
    bne copia

    ; --- and the ones still alive on top, clipped to those cells ---
    sep #$20
.a8
    lda ESC_E
    pha
    jsr esc_dp_tomar
    lda #0
    sta ESC_K
reponer:
    lda ESC_K
    cmp BA_NENE
    bcs repuestos
    jsr esc_por_orden
    jsr esc_bit
    and ESC_VIS
    beq :+
    jsr escena_poner
:   inc ESC_K
    bra reponer
repuestos:
    jsr esc_dp_devolver
    pla
    sta ESC_E
    rts

    ; --- upload what fits in this vblank ---
subir:
.a16
    lda #0
    sta ESC_T0                  ; how many bytes so far
fila:
    lda ESC_T0
    clc
    adc ESC_SUB_LARGO
    cmp #(ESC_SUB_BUDGET + 1)
    bcc :+
    lda ESC_T0
    bne listo                   ; one was already uploaded and the next does not fit
    lda ESC_SUB_LARGO
:   sta ESC_T0
    ; The tile row: `(row * 32 + column)` tiles from the base.
    lda ESC_SUB_FILA
    xba
    lsr a
    lsr a
    lsr a
    clc
    adc ESC_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 words
    pha
    clc
    adc #ESCENA_VRAM
    sta f:VMADDL
    pla
    asl a                       ; times 64 bytes
    clc
    adc #.loword(ESC_ESCENA)
    sta f:A1T0L
    lda ESC_SUB_LARGO
    sta f:DAS0L
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #^ESC_ESCENA
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    inc ESC_SUB_FILA
    dec ESC_SUB_N
    bne fila
listo:
    sep #$20
.a8
    rts
.endproc

; BG1 with the scene, after `ranura_ppu_prender` has set up BG2 and turned
; the screen on. If this battle has no scene it touches nothing and the
; screen stays on black, as before 2026-09-13.
.proc escena_prender
.a8
.i16
    lda BA_ESCENA
    cmp #$FF
    beq listo
    lda #((ESCENA_MAPA / 1024) * 4)
    sta f:BG1SC                 ; 32x32, which is what covers the whole screen
    lda #((RANURA_VRAM / 4096) * 16 + (ESCENA_VRAM / 4096))
    sta f:BG12NBA               ; the text on BG2 and the scene on BG1
    lda #0
    sta f:BG1HOFS               ; `stz` has no long mode
    sta f:BG1HOFS
    lda #$FF
    sta f:BG1VOFS               ; the PPU shows vofs+1: with -1 it lands in place
    sta f:BG1VOFS
    lda #$03
    sta f:TM                    ; BG1 and BG2
listo:
    rts
.endproc

; When returning to the map, the upper eight palettes from `cgram_sombra`,
; before anything else: the battlers took them, and what the map restores by
; itself is only its objects' ones —`SPRITE_CGRAM` colors— and the timer's.
; The banner and the battle animation upload their palette only when it
; changes, so without this they would come back with a battler's colors.
; With the screen off: `volver_de_batalla`, in bank 0, calls it with the
; data bank at 0.
.proc escena_cgram_reponer
.a8
.i16
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * 128)
    sta A1T0L
    lda #256
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the shadow lives in bank 0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

