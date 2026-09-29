.segment "FAR"

; --- the Game Over screen ----------------------------------------------------
;
; It is RM2k's `Scene_Gameover`: the image named by the LDB's `System`, the
; system's Game Over song, a fade in, and on pressing A —or START, as on the
; title— a fade out and the title screen. It is reached by three paths:
;
;   losing a battle with no defeat handler: `op_battle` records the defeat
;                destination with `game_over_anotar`, and `battle_start`
;                asks `game_over_si_perdio` as soon as the battle finishes
;                fading to black. The map is not loaded again: in RM2k the
;                battle is erased and the image appears, without going
;                through the map
;   losing a random encounter, which is always Game Over: `game_over_siempre`
;   the `GameOver` command: `op_game_over` jumps to `game_over_desde_el_mapa`,
;                which fades the map to black like `Scene_Map::TransitionOut`
;
; **It does not return**: it ends in `reset`, which is the title screen if
; the cartridge has one, with the saved game waiting in SRAM. That is also why
; it does not look after the stack, VRAM, the WRAM at $7F, or the audio
; package: the boot restores everything. And that is why it is entered with
; `jml`.
;
; It lives in bank 1 because there is no room in bank 0: only the entry
; points stay there —three `jsl` and the `jml` of `op_game_over`— and the
; audio bridge, `ba_t_audio`. What it needs from bank 0 it asks for through
; the battle's bridges, which restore the data bank.

; How many frames each of the sixteen brightness levels lasts. They are
; easyrpg-player's: `Scene_Gameover` fades in and out in 80 frames, and the
; map is cleared with the usual fade, which is 35 —here 32, two per level—.
GO_CUADROS_PANTALLA = 5
GO_CUADROS_MAPA     = 2

; The PPU registers that only this screen sets to zero: the rest are named by
; registros.s. The map can come with the message window, a tint or a mosaic,
; and the battle with its own: without this they would show on top.
GO_W12SEL = $2123
GO_W34SEL = $2124
GO_TS     = $212D
GO_TSW    = $212F
GO_SETINI = $2133

; Where `pantalla_subir` decompresses to: the WRAM at $7F from the start. It
; is valid only during the upload —the battle and the ChipSet animation use
; that bank, and both are rebuilt afterwards—, just like `LZ2_BUFFER`. The
; 64 KB an LZ2 stream can produce fit, and it overwrites the upper half of the
; grid: Game Over is followed by the boot, and the title screen by
; `cargar_mapa`, and both decompress it again. `test_reservas_de_la_wram.py`
; lets it through.
PANTALLA_BUFFER = $7F0000
; The screen's tilemap, in VRAM words. The tiles go from $0000 and the
; heaviest image is 896 8bpp tiles, that is, up to $7000: they never get above
; that. The title puts its menu in the middle: see the `.assert` in
; `titulo_subir`.
PANTALLA_MAPA = $7C00

; `op_battle` before fighting: the defeat destination, which is six bytes
; after the troop —victory, escape, defeat, one word each—. Enters with Y on
; the troop and leaves it as it was.
.proc game_over_anotar
.a8
.i16
    rep #$20
.a16
    phy
    iny
    iny
    iny
    iny
    iny
    iny
    lda [cod_ptr], y
    sta f:GO_PIERDE
    ply
    sep #$20
.a8
    rtl
.endproc

; A random encounter: losing it is always Game Over, because there is no page
; that carries a handler.
.proc game_over_siempre
.a8
.i16
    lda #$FF
    sta f:GO_PIERDE
    sta f:GO_PIERDE + 1
    rtl
.endproc

; `battle_start`, with the battle already faded to black: if it was lost and
; the defeat destination is `BATALLA_PERDER`, it does not return. Otherwise it
; carries on as usual.
.proc game_over_si_perdio
.a8
.i16
    lda f:BAT_LARGO + BA_RESULT
    cmp #BA_DERROTA
    bne sigue
    rep #$20
.a16
    lda f:GO_PIERDE
    inc a                       ; $FFFF gives zero, and `sep` does not touch Z
    sep #$20
.a8
    bne sigue
    jmp game_over_negro
sigue:
    rtl
.endproc

; `GameOver`: the map fades to black from whatever brightness it has —it can
; be halfway through a fade— and from there, the screen.
.proc game_over_desde_el_mapa
.a8
.i16
.if ::GAME_OVER_TILES = 0     ; `::`: inside a `.proc`, without it it is not constant
    jml f:reset                 ; a ROM with no image goes straight back to the title
.else
    phk
    plb
    lda #GO_CUADROS_MAPA
    sta f:GO_CUADROS
    lda brillo
    sta f:GO_NIVEL
baja:
    jsr go_esperar
    lda f:GO_NIVEL
    beq negro
    dec a
    sta f:GO_NIVEL
    sta INIDISP
    bra baja
negro:
    jmp game_over_negro
.endif
.endproc

; The screen, with the previous one already black.
.proc game_over_negro
.a8
.i16
.if ::GAME_OVER_TILES = 0     ; `::`: inside a `.proc`, without it it is not constant
    jml f:reset
.else
    phk
    plb
    lda #$80
    sta INIDISP                 ; forced blanking: VRAM is only touched this way
    stz HDMAEN                  ; without the message window
    lda #0
    sta f:GO_ESPERA
    ; The song, first: its package —the song alone, see PAQUETE_GAME_OVER in
    ; snes_convert.py— is uploaded with the screen black, and so it plays from
    ; the first frame of the fade, as in RM2k. With an MSU-1 track the package
    ; uploads nothing and the track plays.
    ldx #PAQUETE_GAME_OVER
    jsl f:ba_t_audio
    lda #TEMA_GAME_OVER
    jsl f:ba_t_bgm
    ldx #(PANTALLA_GAME_OVER * PANTALLA_FILA)
    jsl f:pantalla_descomprimir
    jsl f:pantalla_subir        ; the same row: `pantalla_descomprimir` does
                                ; not touch X

    ; The fade in.
    lda #GO_CUADROS_PANTALLA
    sta f:GO_CUADROS
    lda #0
    sta f:GO_NIVEL
sube:
    lda f:GO_NIVEL
    sta INIDISP
    jsr go_esperar
    lda f:GO_NIVEL
    cmp #$0F
    beq arriba
    inc a
    sta f:GO_NIVEL
    bra sube
arriba:
    ; And the button, which in RM2k is `Input::DECISION`: A, on the edge.
    ; START too, as on the title screen: see `titulo_lazo`. What was pressed
    ; during the fade does not count, because `go_esperar` read the
    ; controller on every frame and the edge has already passed.
    lda #1
    sta f:GO_ESPERA
espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    lda pad_a
    beq mira_start
    lda pad_a_ant
    beq cierra
mira_start:
    lda pad
    eor pad_ant
    and pad
    and #PAD_START
    beq espera
cierra:
    lda #0
    sta f:GO_ESPERA
    ; The fade out, with the song still playing: in RM2k only the title
    ; changes it.
baja:
    jsr go_esperar
    lda f:GO_NIVEL
    beq negro
    dec a
    sta f:GO_NIVEL
    sta INIDISP
    bra baja
negro:
    lda #$80
    sta INIDISP
    ; The music, silenced before the boot: the reset uploads the driver to the
    ; SPC700 again, but an MSU-1 track would keep playing during the whole
    ; boot, until the title asks for its own.
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
    lda #$FF
    jsl f:ba_t_bgm
    jml f:reset
.endif
.endproc

; The GO_CUADROS frames, reading the controller on each one. Clobbers A.
.proc go_esperar
.a8
.i16
    lda f:GO_CUADROS
cuadro:
    pha
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    pla
    dec a
    bne cuadro
    rts
.endproc

; A full screen from `pantallas_tabla` —X is its row, in bytes—, in two steps:
; `pantalla_descomprimir` leaves it in `PANTALLA_BUFFER`, and
; `pantalla_subir` takes it from there to VRAM and CGRAM.
;
; The row is: the LZ2 stream (three bytes), how many bytes of tiles and how
; many of colors (one word each) and starting at which CGRAM color (one byte).
; The stream carries the three parts back to back: the tiles, the 32x32
; tilemap and the colors. See tools/port/fullscreen.py.
;
; Both the Game Over screen and the title use it: that is why it does not know
; which one it is uploading. It is two steps because of the title, which is
; decompressed during boot, while the BOOT_CUADROS are waited out, and only
; uploaded when shown: see `titulo_subir`.
;
; Decompressing does not touch VRAM, so it can be done with the screen on.
; Leaves X as it was.
.proc pantalla_descomprimir
.a8
.i16
.ifdef ::PANTALLA_FILA
    phb
    phk
    plb
    phx                         ; the row
    lda #^PANTALLA_BUFFER
    sta f:LZ2_BANCO
    lda f:pantallas_tabla + 2, x
    pha                         ; the stream's bank
    rep #$20
.a16
    lda f:pantallas_tabla, x
    tax
    sep #$20
.a8
    pla
    ldy #.loword(PANTALLA_BUFFER)
    jsl f:lz2_descomprimir + RAPIDO
    plx
    plb
.endif
    rtl
.endproc

; The screen that `pantalla_descomprimir` left in `PANTALLA_BUFFER`, with X on
; the same row, to VRAM and CGRAM, and the PPU set to show it on BG1 in mode
; 3, alone. Leaves the screen off: brightness is the caller's business.
.proc pantalla_subir
.a8
.i16
.ifdef ::PANTALLA_FILA
    phb
    phk
    plb
    lda #$80
    sta INIDISP

    ; --- the tiles ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #$0000
    sta VMADDL
    lda f:pantallas_tabla + 3, x
    sta DAS0L
    lda #.loword(PANTALLA_BUFFER)
    sta A1T0L
    sep #$20
.a8
    lda #^PANTALLA_BUFFER
    sta A1B0
    lda #$01
    sta DMAP0                   ; two registers, in words
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- the tilemap, after the tiles ---
    rep #$20
.a16
    lda #PANTALLA_MAPA
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda f:pantallas_tabla + 3, x
    clc
    adc #.loword(PANTALLA_BUFFER)
    sta A1T0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN                  ; the bank and destination, the ones above

    ; --- the colors, after the tilemap ---
    lda f:pantallas_tabla + 7, x
    sta CGADD
    rep #$20
.a16
    lda f:pantallas_tabla + 5, x
    sta DAS0L
    lda f:pantallas_tabla + 3, x
    clc
    adc #(.loword(PANTALLA_BUFFER) + 32 * 32 * 2)
    sta A1T0L
    sep #$20
.a8
    stz DMAP0                   ; one register, in bytes
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN

    ; --- and the PPU, with everything the map or the battle may have left ---
    lda #$03
    sta BGMODE
    lda #(PANTALLA_MAPA / 1024 * 4)
    sta BG1SC                   ; 32x32 tilemap
    stz BG12NBA                 ; BG1's tiles from $0000
    stz BG1HOFS
    stz BG1HOFS
    lda #$FF                    ; line vofs+1 on the first scanline: see
    sta BG1VOFS                 ; `ppu_init`
    sta BG1VOFS
    lda #$01
    sta TM                      ; the image alone: no sprites, no other layer
    ; Everything as `ppu_reset` leaves it —see `ppu_altos` in banco1.s—, and
    ; not zero: TMW and CGWSEL are set only by the reset, and the map expects
    ; them that way. Game Over is followed by the reset, but the title is
    ; followed by the map: with TMW at zero the message window stopped
    ; covering the objects.
    stz GO_TS
    lda #$10
    sta TMW                     ; the mask, only for the objects, which are
                                ; not visible here
    stz GO_TSW
    stz GO_W12SEL
    stz GO_W34SEL
    stz WOBJSEL
    lda #$30
    sta CGWSEL                  ; no color math: no tint, no flash
    stz CGADSUB
    stz MOSAIC
    stz GO_SETINI
    plb
.endif
    rtl
.endproc
