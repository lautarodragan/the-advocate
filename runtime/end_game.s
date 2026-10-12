.segment "FAR"

; --- End Game ----------------------------------------------------------------
;
; `Scene_End`: the End Game command in the pause menu. Two windows over black
; —the question, and "Yes" and "No" with the System's bar— that come whole,
; already drawn, from `rm2k-snes-screens`: the tiles, the tilemap rows
; that have something in them, and two palettes, one per highlighted command.
; Moving the cursor means uploading the other palette; the why is in the header
; of its `end_game.rs`.
;
; Everything goes on BG2, over `SLOT_VRAM` and `SLOT_MAP`, which are the
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
; `title_sel` is the highlighted command while it is shown: the menu puts it
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
    lda #END_ENTERS
    sta title_sel

    ; --- the tiles, from SLOT_VRAM ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #SLOT_VRAM
    sta VMADDL
    lda #(END_TILES * 32)
    sta DAS0L
    lda #.loword(end_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^end_tiles
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
    lda #SLOT_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #.loword(end_tiles)
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
    lda #(SLOT_MAP + END_ROW0 * 32)
    sta VMADDL
    lda #(END_ROWS * 64)
    sta DAS0L
    lda #.loword(end_map)
    sta A1T0L
    sep #$20
.a8
    lda #^end_map
    sta A1B0
    lda #$01
    sta DMAP0
    sta MDMAEN
    jsr ending_palette

    ; --- the PPU: BG2 alone, like `slot_ppu_on` ---
    lda #(SLOT_MAP / 1024 * 4)
    sta BG2SC
    lda #(SLOT_VRAM / 4096 * 16)
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

wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    ; Up and down switch commands, and with two it does not matter which: there
    ; is no cap, as in `Window_Selectable`, which wraps around.
    lda pad
    eor pad_prev
    and pad
    bit #PAD_B
    bne go_back
    and #(PAD_UP | PAD_DOWN)
    beq check_a
    lda title_sel
    eor #1
    sta title_sel
    jsr ending_palette          ; still in the vblank
    bra wait
check_a:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                    ; it was already held: not an edge
    lda title_sel
    cmp #END_NO
    bne leave
go_back:
    lda #$80
    sta INIDISP
    plb
    rtl

leave:
    ; "Yes": the song fades like a 400 ms `FadeOutBGM` —`Scene_End`'s
    ; `BgmFade`—, with the same guard as `op_fade_bgm`: with the song off
    ; there is nothing to fade, and with an MSU-1 track there is.
    lda f:MSU_PLAYING
    bne fade_step
    lda music_off
    bne screen
fade_step:
    php
    sei                         ; `irq_music` reads it: all at once or nothing
    rep #$20
.a16
    lda #END_STEP_SONG
    sta bgm_step
    lda #$FFFF
    sta bgm_level               ; full volume, which is where it goes down from
    sep #$20
.a8
    lda #1
    sta bgm_fade
    plp
screen:
    ; And the screen, to black along the converter's ramp.
    ldx #0
low:
    phx
    jsl f:ba_t_vblank
    plx
    lda f:end_ramp, x
    sta INIDISP
    inx
    cpx #END_FRAMES
    bne low
    lda #$80
    sta INIDISP
    ; The song finishes fading with the screen black: the screen fade is
    ; shorter. `bgm_fade` goes back to zero on its own, in `irq_music`; if
    ; there was no song, it already is. The cap is just in case: the song only
    ; has a few frames left, and END_FRAMES is more than enough.
    ldx #END_FRAMES
song:
    lda bgm_fade
    beq muted
    phx
    jsl f:ba_t_vblank
    plx
    dex
    bne song
muted:
    ; The music, silenced before the boot, as when leaving Game Over: the
    ; reset uploads the driver to the SPC700 again, but an MSU-1 track would
    ; keep playing through the whole boot.
    lda #0
    sta f:MSU_PLAYING
    sta MSU_CONTROL
    lda #$FF
    jsl f:ba_t_bgm
    jml f:reset
.endproc

; The palette for command `title_sel` into entries 0 to 15. With the screen
; off or inside the vblank.
.proc ending_palette
.a8
.i16
    stz CGADD
    lda title_sel
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per palette
    clc
    adc #.loword(end_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^end_cgram
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc
