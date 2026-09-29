.segment "FAR"

; --- End Game ----------------------------------------------------------------
;
; `Scene_End`: the End Game command in the pause menu. Two windows over black
; —the question, and "Yes" and "No" with the System's bar— that come whole,
; already drawn, from tools/port/end_game.py: the tiles, the tilemap rows
; that have something in them, and two palettes, one per highlighted command.
; Moving the cursor means uploading the other palette; the why is in the header
; of fin_del_juego.py.
;
; Everything goes on BG2, over `RANURA_VRAM` and `RANURA_MAP`, which are the
; places the menu and the slot screen already write: on the way back,
; `menu_upload` rebuilds them and `back_to_map` has nothing else to restore.
;
; It is entered with `jsl` from `menu_screen`, with the screen on or not,
; and:
;
;   B or "No"  returns with `rtl`, with the screen off: the menu gets rebuilt
;   "Yes"      does not return: the song and the screen fade, the music goes
;              quiet, and it ends in `reset`, which is the title screen if the
;              cartridge has one. It is the same ending as the Game Over
;              screen's, and for the same reason it does not care about the
;              stack or VRAM: the boot restores everything.
;
; `titulo_sel` is the highlighted command while it is shown: the menu puts it
; back on End Game on return, as it does with the other screens.
.proc ending_screen
.a8
.i16
    phb
    phk
    plb
    lda #$80
    sta INIDISP                 ; forced blank: VRAM is only touched this way
    stz HDMAEN
    lda #FIN_ENTRA
    sta titulo_sel

    ; --- the tiles, from RANURA_VRAM ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(FIN_TILES * 32)
    sta DAS0L
    lda #.loword(fin_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^fin_tiles
    sta A1B0
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$01
    sta MDMAEN
    ; --- the blank tilemap: fixed source at the first tile, which is zero ---
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #.loword(fin_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$01
    sta MDMAEN
    ; --- and the rows that have something ---
    rep #$20
.a16
    lda #(RANURA_MAP + FIN_FILA0 * 32)
    sta VMADDL
    lda #(FIN_FILAS * 64)
    sta DAS0L
    lda #.loword(fin_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^fin_mapa
    sta A1B0
    lda #$01
    sta DMAP0
    sta MDMAEN
    jsr ending_palette

    ; --- the PPU: BG2 alone, like `slot_ppu_on` ---
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(RANURA_VRAM / 4096 * 16)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF                    ; line vofs+1 on the first scanline: see
    sta BG2VOFS                 ; `ppu_init`
    sta BG2VOFS
    lda #$02
    sta TM
    lda #$0F
    sta INIDISP

espera:
    jsl f:bt_t_vblank
    jsl f:bt_t_pad
    ; Up and down switch commands, and with two it does not matter which: there
    ; is no cap, as in `Window_Selectable`, which wraps around.
    lda pad
    eor pad_ant
    and pad
    bit #PAD_B
    bne volver
    and #(PAD_UP | PAD_DOWN)
    beq mira_a
    lda titulo_sel
    eor #1
    sta titulo_sel
    jsr ending_palette              ; still in the vblank
    bra espera
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; it was already held: not an edge
    lda titulo_sel
    cmp #FIN_NO
    bne salir
volver:
    lda #$80
    sta INIDISP
    plb
    rtl

salir:
    ; "Yes": the song fades like a 400 ms `FadeOutBGM` —`Scene_End`'s
    ; `BgmFade`—, with the same guard as `op_fade_bgm`: with the song off
    ; there is nothing to fade, and with an MSU-1 track there is.
    lda f:MSU_PLAYING
    bne fundir
    lda music_apagada
    bne pantalla
fundir:
    php
    sei                         ; `irq_music` reads it: all at once or nothing
    rep #$20
.a16
    lda #FIN_PASO_TEMA
    sta bgm_paso
    lda #$FFFF
    sta bgm_nivel               ; full volume, which is where it goes down from
    sep #$20
.a8
    lda #1
    sta bgm_fundido
    plp
pantalla:
    ; And the screen, to black along the converter's ramp.
    ldx #0
baja:
    phx
    jsl f:bt_t_vblank
    plx
    lda f:fin_rampa, x
    sta INIDISP
    inx
    cpx #FIN_CUADROS
    bne baja
    lda #$80
    sta INIDISP
    ; The song finishes fading with the screen black: the screen fade is
    ; shorter. `bgm_fundido` goes back to zero on its own, in `irq_music`; if
    ; there was no song, it already is. The cap is just in case: the song only
    ; has a few frames left, and FIN_CUADROS is more than enough.
    ldx #FIN_CUADROS
tema:
    lda bgm_fundido
    beq callado
    phx
    jsl f:bt_t_vblank
    plx
    dex
    bne tema
callado:
    ; The music, silenced before the boot, as when leaving Game Over: the
    ; reset uploads the driver to the SPC700 again, but an MSU-1 track would
    ; keep playing through the whole boot.
    lda #0
    sta f:MSU_PLAYING
    sta MSU_CONTROL
    lda #$FF
    jsl f:bt_t_bgm
    jml f:reset
.endproc

; The palette for command `titulo_sel` into entries 0 to 15. With the screen
; off or inside the vblank.
.proc ending_palette
.a8
.i16
    stz CGADD
    lda titulo_sel
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per palette
    clc
    adc #.loword(fin_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^fin_cgram
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc
