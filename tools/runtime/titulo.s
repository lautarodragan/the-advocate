.segment "CODE"

; --- the title screen --------------------------------------------------------
;
; The LDB's image —`title_name`, which in ABL is ABL20Title— with its song
; —`title_music`, Fantasia_Of_The_Wind—, and from there into the game.
;
; **It has the VRAM to itself.** While it is shown there is no map loaded, so
; there is no layout to negotiate: the image goes on BG1, which in mode 3 has
; eight bits per pixel and addresses all of CGRAM. A map splits its colors into
; palettes of sixteen because the sprites need their own; here there are no
; sprites.
;
; The image comes compressed, and `screen_upload` uploads it, the same routine
; as the Game Over one: the tiles from $0000 and its tilemap at SCREEN_MAP.
; The VRAM layout is in mapdata.inc, next to TITLE_MENU_VRAM. On the way out,
; `enter_map` restores the bases and overwrites everything.
;
; **It runs with its own loop and not the main one.** The main loop moves the
; hero, runs the interpreter and builds the OAM, and there is none of that
; here: all that has to happen each frame is reading the pad and keeping the
; music going.
.proc title_screen
.a8
.i16
    ; Does this ROM carry a title screen? TITLE_TILES does not fit in eight
    ; bits, so the question is both bytes.
    lda #<TITLE_TILES
    ora #>TITLE_TILES
    bne hay
    rts
hay:
    jsr title_upload
    ; The title song. $FF means this ROM does not carry it —or that it did not
    ; fit in the ARAM—, and then the screen is shown silent.
    ;
    ; It goes **here and not in `title_upload`**: that one also runs when
    ; coming back from the slot screen, and there the song is still playing
    ; and must not be touched. Until 2026-09-10 it restarted it, with a comment
    ; saying that was what RM2k did, and it is not: `Scene_Title::Continue`,
    ; coming back from the load screen, does not go through `Start()`, and
    ; `Game_System::BgmPlay` with the same song already playing does not
    ; restart it. taro heard it on the console.
    lda #SONG_TITLE
    cmp #$FF
    beq mudo
    jsr music_start
mudo:
    jmp title_loop
.endproc

; Uploads the whole title screen —the image, the menu, the colors— and turns it
; on. It is separate from the loop because two paths arrive here: entering, and
; **coming back from the slot screen after cancelling**, which overwrote VRAM
; and CGRAM with its own things.
.proc title_upload
.a8
.i16
    stz HDMAEN                  ; without the message window on top

    ; --- the image, with all of CGRAM ---
    ; `screen_upload` uploads it, the Game Over one: the tiles from $0000,
    ; the tilemap at SCREEN_MAP and the colors —the menu's below and the
    ; image's above, in the same stream: see tools/port/fullscreen.py—.
    ; It leaves the screen off, BG1 in mode 3, and TM, the window and color
    ; math at zero.
    ;
    ; **It does not decompress it**: the boot did that, while waiting out its
    ; BOOT_FRAMES, and `SCREEN_BUFFER` has held it since. Decompressing it
    ; here is nine more frames of black before the title, and another nine
    ; when coming back from the slot screen —measured on 2026-09-28—. It works
    ; because nothing that runs on the title writes bank $7F: not its loop,
    ; not the music, not the slot screen. The buffer overwrites the grid and
    ; the ChipSet animation drawings of the boot map, and that is allowed
    ; because this screen is always left through `enter_map`, which
    ; rebuilds them.
.ifdef ::SCREEN_TITLE        ; no title screen, no row
    ldx #(SCREEN_TITLE * SCREEN_ROW)
    jsl f:screen_upload
.endif

    ; --- the menu tiles ---
    ; They go on BG2, which in mode 3 has four bits per pixel, so they cost
    ; half. Tile 0 is transparent and covers almost the whole screen: it is
    ; what lets the image below show. `VMAIN` is the one `screen_upload` left.
    rep #$20
.a16
    lda #TITLE_MENU_VRAM
    sta VMADDL
    lda #(TITLE_MENU_TILES * 32)
    sta DAS0L
    lda #<(title_menu_tiles)
    ora #(>(title_menu_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(title_menu_tiles)
    sta A1B0
    lda #$01
    sta DMAP0                   ; two registers, word at a time
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- and the PPU pointing at the menu ---
    lda #(TITLE_MENU_MAP / 1024 * 4)
    sta BG2SC                   ; 32x32 tilemap: the two low bits at zero
    ; The two tile bases, in steps of 4096 words: BG1 in the low nibble —at
    ; zero, where `screen_upload` put the image— and BG2 in the high one.
    lda #(TITLE_MENU_VRAM / 4096 * 16)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    ; The PPU shows line vofs+1 on the first scanline, the same as on the
    ; map: with 0 the menu comes out shifted one line up.
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    lda #$03
    sta TM                      ; the image and the menu; there are no sprites

    stz title_sel              ; it opens with the first option selected
    jsl f:title_upload_menu

    lda #$0F
    sta INIDISP                 ; and the screen on, at full brightness
    rts
.endproc
; What `screen_upload` puts in VRAM must not overwrite the menu's: the image's
; tiles, at 32 words each, go below the menu's tilemap, and the menu's tiles,
; at 16, end before the image's tilemap.
.assert TITLE_TILES * 32 <= TITLE_MENU_MAP, error, "the title tiles overwrite the menu tilemap"
.assert TITLE_MENU_VRAM + TITLE_MENU_TILES * 16 <= SCREEN_MAP, error, "the title menu tiles overwrite the image tilemap"

; The menu loop. Up and down move the cursor on the **edge** and wrap around,
; the same as `choice_tick` with ShowChoice: it is RM2k's
; `Window_Selectable::Update` with a single column, and holding down does not
; move one line per frame.
.proc title_loop
.a8
.i16
espera:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_prev
    and pad                     ; what was pressed this frame
    sta title_edges
    and #PAD_UP
    beq no_arriba
    lda title_sel
    bne sube_una
    lda #TITLE_MENU_N          ; from the first one, up wraps around
sube_una:
    dec a
    sta title_sel
    jsl f:title_upload_menu
    bra espera
no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq no_abajo
    lda title_sel
    inc a
    cmp #TITLE_MENU_N
    bcc baja_una
    lda #0                      ; and from the last one, so does down
baja_una:
    sta title_sel
    jsl f:title_upload_menu
    bra espera
no_abajo:
    ; Selecting is A or START. RM2k does not look at START —there the menu
    ; belongs to the mouse and the keyboard— but on a console the title screen
    ; is passed with START and not having it feels broken.
    lda pad_a
    beq mira_start
    lda pad_a_prev
    beq elige                   ; edge, not state
mira_start:
    lda title_edges
    and #PAD_START
    beq espera
elige:
    ; The second option is 'Resume the Story': the save is loaded and, if
    ; there is one, the map and the cell come from it. If there is none, it
    ; starts the same as the first, which is what RM2k does when there is
    ; nothing to load.
    lda title_sel
    beq salir
    ; 'Resume the Story': the slot screen, in load mode. If the player cancels
    ; with B it goes back to the title, and since that screen overwrote VRAM
    ; and CGRAM the title has to be uploaded again in full.
    lda #0
    jsr slots_screen
    cmp #$FF
    bne la_elegida
    jsr title_upload
    jmp title_loop
la_elegida:
    jsr set_slot
    jsr load_game
    beq salir                   ; the slot was empty or the checksum does not match
    jsr save_entry
    rep #$20
.a16
    lda map_current             ; the index goes in sixteen bits
    bra cargar_el_mapa
.a8
salir:
    rep #$20
.a16
    lda #MAP_INITIAL
cargar_el_mapa:
    ; VRAM was left with the title image, so the map has to be loaded again in
    ; full. But VRAM is not the only thing this screen moved: the **PPU
    ; registers** too, and `enter_map` does not restore those.
    ;
    ; `BG1SC`, `BG2SC`, the scrolls and `TM` are written by `ppu_init`, which
    ; until now ran only once at boot because nobody touched them afterwards.
    ; Without calling it again the game starts with BG1's tilemap pointing at
    ; the title's —that is, all the tiles shifted, which is what taro saw
    ; playing the demo— and with `TM` at zero, which is a black screen with
    ; the logic and the music running behind it.
    ;
    ; **snes9x and the pixel comparison did not see it**, and for a reason
    ; worth remembering: the suite looks at the title screen and not at what
    ; happens after leaving it. The frame that would have caught it did not
    ; exist.
    pha                         ; the map index, sixteen bits
    sep #$20
.a8
    lda #$80
    sta INIDISP
    stz TM                      ; and without the menu on top while everything is rebuilt
    jsr ppu_init                ; the PPU registers, as the reset left them
    ; **The title song is silenced before loading the map**, and not after
    ; with `music_boot`: `package_load` leaves in place the samples of the
    ; song it says is playing, and here that one is not playing. With a save
    ; loaded, `song_current` is already the save's, and its samples that the
    ; title's package had uploaded stayed fixed where they were, splitting the
    ; ARAM: the map's package did not fit, and the map's `PlayBGM` uploaded
    ; it all again —loading into map 1 took twice as long—.
    ; `music_off` is restored right before `music_boot`, which reads it:
    ; it is the save's.
    lda music_off
    pha
    php
    sei                         ; the SPC700 serves one at a time: see `irq_music`
    lda #1
    sta music_off
    lda #$FF
    ldx #SE_KOF
    jsr dsp_music              ; as below: without touching the sound effect voices
    plp
    rep #$20
.a16
    lda 2, s                    ; the map index, behind music_off
    jsr enter_map
    sep #$20
.a8
    pla                         ; the save's music_off
    plx                         ; the index, no longer needed
    pha
    jsr clear_oam
    jsr build_oam
    jsr flush_video
    pla
    sta music_off

    ; The music. Without this the title song keeps playing inside the game,
    ; which is what taro saw on 2026-09-10: `Fantasia_Of_The_Wind` in the
    ; corridor of the opening. `music_boot` is exactly what a ROM without a
    ; title screen does at boot —the starting map's song, or silence if it has
    ; none—, so both keep sounding the same.
    jsr music_boot
    lda music_off
    beq listo_musica
    ; `SONG_BOOT` at $FF means the map starts silent and a `PlayBGM` turns
    ; the music on, which is the usual case in this game. `music_boot` writes
    ; nothing to the DSP because at boot nothing is playing; **here something
    ; is**, so the title's voices are released by hand. With KOF and through
    ; `dsp_music`, which leaves out the ones that have a sound effect, and
    ; **not** with the master volume, which is also the sound effects': until
    ; 2026-09-26 that one was lowered, and the sound effects stayed mute until
    ; the first `PlayBGM`.
    php
    sei                         ; the SPC700 serves one at a time: see `irq_music`
    lda #$FF
    ldx #SE_KOF
    jsr dsp_music
    plp
listo_musica:
    lda #$0F
    sta INIDISP
    rts
.endproc

