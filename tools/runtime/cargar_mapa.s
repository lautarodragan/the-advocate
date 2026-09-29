.segment "CODE"

; --- dumping the map to VRAM ------------------------------------------------
; All by DMA and with the screen off, which is when VRAM can be written
; without fighting the PPU.
; Loads in full the map whose index comes in A **as sixteen bits**: its data
; to VRAM and to CGRAM,
; its tables to where the ROM looks for them, the camera where the hero
; starts and the tilemap window filled. It is everything that has to be done
; to change map.
;
; This cannot be called with the screen on: it writes VRAM and CGRAM by DMA,
; which the PPU does not allow outside vblank.
.proc cargar_mapa_sin_eventos
.a16
.i16
    sta mapa_actual             ; to know whether the next jump changes map
    sep #$20
.a8
    jsr turn_clear            ; the rows are going to be different
    jsr animacion_limpiar       ; and the battle animation does not carry on
    rep #$20
.a16
    stz sub_n                   ; and the tile substitutions are lost when
    stz sub_refresco            ; loading a map, as in RM2k: see `sub_n`
    sep #$20
.a8
    lda #0                      ; and the picture is erased: it is the
    sta f:CARTEL_ACTIVA         ; `erase_on_map_change` of Game_Pictures, and
    sta f:CARTEL_LISTO          ; besides, its tiles belong to a single map
    jsr paquete_cargar          ; the map's audio, during the fade
    rep #$20
.a16
    lda mapa_actual
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times MAPA_STRIDE, which is 128
    sta mapa_ofs
    tax

    ; The battle animation's layout on this map: which tile its box falls on
    ; and with which palette, or that it is not drawn here. It needs
    ; `mapa_actual` and `mapa_ofs`, which have just been set.
    phx
    sep #$20
.a8
    jsr animacion_dibujo_mapa   ; enters and leaves with the accumulator at eight
    jsl f:encuentro_mapa        ; and every how many steps there is an encounter here
    rep #$20
.a16
    plx

    ; What is looked at often is copied; what is used once is read in place.
    lda f:mapa_tabla + M_MAP_BW, x
    sta mapa_ancho
    asl a
    sta mapa_cw                 ; the width in 8x8 cells is double
    lda f:mapa_tabla + M_MAP_BH, x
    sta mapa_alto
    asl a
    sta mapa_ch
    lda f:mapa_tabla + M_CAM_MAX_X, x
    sta cam_max_x
    lda f:mapa_tabla + M_CAM_MAX_Y, x
    sta cam_max_y
    lda f:mapa_tabla + M_EV_COUNT, x
    ; Everything that sweeps events goes up to here and not up to `EV_MAX`:
    ; with the hundred and twenty, a map with four events swept a hundred and
    ; sixteen too many and that was enough to lose the frame.
    sta ev_total
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; times sixteen: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "the computation above multiplies by sixteen by hand"
    sta npc_total

    ; The pointers to the two tables that are read from ROM. The second points
    ; eight bytes further, which is where each block stores its upper layer;
    ; adding eight cannot overflow the bank because the placement in
    ; `tools/ensamblado/bancos.py` guarantees the whole table fits in one.
    lda f:mapa_tabla + M_PTR_NPC_POSES, x
    sta poses_ptr
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES, x
    sta bloques_ptr
    clc
    adc #8
    sta bloques8_ptr
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES + 2, x
    sta bloques_ptr + 2
    sta bloques8_ptr + 2
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS + 2, x
    sta pass_ptr + 2
    lda f:mapa_tabla + M_PTR_NPC_POSES + 2, x
    sta poses_ptr + 2

    ; Where the hero starts: wherever the record says, unless the caller left
    ; an entry set, which is what a door does. The camera is placed before
    ; filling the window, because the window is filled around it.
    rep #$20
.a16
    lda entrada_x
    cmp #$FFFF
    bne desde_puerta
    lda f:mapa_tabla + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda f:mapa_tabla + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra puesto

desde_puerta:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; the cell is 16 pixels
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumed: the next load goes back to the record

puesto:
    sep #$20
.a8
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA
    ; And the background's tilemap, which also comes from the layout: almost
    ; always at $5800, but not in all of them. It is copied to RAM because
    ; `build_column` and `build_row` add it, and they have X busy and cannot
    ; read the table.
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_MAP, x
    sta f:FAR_VRAM_MAPA
    sep #$20
.a8
    xba
    ora #MAP_LAYOUT
    sta BG1SC

    ; The panned camera goes back to zero when changing map, and at once: it is
    ; what `Game_Player::PerformTeleport` does with `map_changed`, which gives
    ; `pan_current` and `pan_finish` back their default value. A jump to the
    ; same map does not go through here and does not touch it, which is also
    ; what RM2k does.
    rep #$20
.a16
    stz pan_x
    stz pan_y
    stz pan_dest_x
    stz pan_dest_y
    stz pan_px
    stz pan_py
    sep #$20
.a8

    ; The grid, to WRAM, before anyone asks about a cell: it comes compressed.
    ; See `GRILLA`.
    jsl f:lz2_grilla + RAPIDO
    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    jsr load_ruta_graficos
    jsr load_ev_pos             ; and where each event starts, with or without a graphic
    stz refresco
    ; Before the refresh, not after: the previous map's marks are worth
    ; nothing here —their event indices would point at other events— and the
    ; refresh is the one that turns `FLAG_AUTO` back on for the ones it
    ; applies to.
    jsr clear_waits
    jsr clear_parallel
    jsr page_routes         ; and the move routes of the active pages themselves
    ; The actor table belongs to this map, so where the leader's poses fall
    ; changes when changing map even if the party is the same.
    jsr elegir_grafico_heroe
    jsr limpiar_tilemaps        ; what `fill_window` does not overwrite, from the map before
    jsr fill_window             ; leaves tira_paso_col ready, which the other one uses
    jsr load_ventana            ; tiles, palette, its own tilemap and HDMA tables
    jsr init_hero_ptr

    ; The tint is game state, not map state: it survives the teleport. The
    ; palettes just uploaded are the cartridge's, untinted, so they are tinted
    ; again here. With a neutral tint the computation is i*100/100 and leaves
    ; the colors where they were, so there is no need to ask whether there is
    ; a tint: the path is always the same.
    jsr aplicar_tinte
    stz destello_listo          ; whatever was in `pal_buf` no longer
                                ; belongs to this map; the next frame
                                ; builds it again if the flash goes on
    jsr subir_tinte             ; the screen is off: it goes now
    rts
.endproc

; And this is what has to be called: it loads the map and runs its automatic
; events.
;
; If an event requests a teleport, the cycle repeats here and not inside the
; interpreter. Calling cargar_mapa from the interpreter would be recursion,
; and two maps that point at each other would make it infinite: the stack
; sinks to the bottom and the console does anything at all. The cap on
; iterations is there for the same reason, for the case where they point at
; each other through a longer cycle.
.proc cargar_mapa
.a16
.i16
    pha                         ; the map index, which what follows would clobber
    sep #$20
.a8
    lda #SALTOS_MAX
    sta saltos_restantes        ; with stx it would be two bytes and clobber the next one
    rep #$20
.a16
    pla
    jsr cargar_mapa_sin_eventos
    rts
.endproc

; Restores what the slot screen overwrote on the map, and nothing else. It is
; for the save point, which opens it with the game running; the title does
; not need it because on leaving it loads the whole map.
;
; What it overwrote, in VRAM words: the tiles at RANURA_VRAM and the tilemap
; at RANURA_MAP, which are chosen to fall inside BG1's tile bank **in every
; layout** of `vram_layout` —the converter checks it—. The sprites, the upper
; layer, the window and the map's two tilemaps are left outside. It was not
; so with the title menu's addresses: in the wide layout the sprites start at
; $4000 and the tilemap at $4400 landed on them, which showed as 267 pixels on
; the hero of map 73 with party 11 —block 0's was spared—. And in CGRAM,
; palette 0: the background color and the message window, plus the map's
; first colors. The registers: BG2SC, BG12NBA, TM and BG2's scroll.
;
; So the tile bank is uploaded again with `load_map` —which also brings the
; lower CGRAM and the map's, and the drawing of the animation that applies—,
; it is tinted again because what was uploaded comes untinted, and the
; registers are set by `ppu_init` plus the map's BG12NBA and BG1SC. It is a
; subset of `cargar_mapa_sin_eventos`, chosen by hand: what is missing from
; there is state —events, routes, poses, the VRAM queue— and restoring it
; would restart the game.
;
; The screen is turned off by hand and **is not turned back on here**:
; `flush_video` writes `brillo` in the next vblank, and so the map appears on
; a whole frame and not halfway through one. We get here just after a vblank
; starts —the slot screen leaves right after its `read_pad`—, so the
; turn-off also lands on a frame boundary. Measured: **two** black frames
; show and then the map, because `load_map`'s 30 KB do not fit in one vblank
; and that tick lasts two frames —`cuadros_perdidos` counts one—. In RM2k
; closing the scene takes a transition, so it does not look out of place.
.proc volver_al_mapa
.a8
.i16
    lda #$80
    sta INIDISP
    jsr ppu_init
    ldx mapa_ofs
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA
    lda f:mapa_tabla + M_VRAM_MAP + 1, x
    ora #MAP_LAYOUT
    sta BG1SC                   ; the battle leaves it pointing at its scene
    jsr load_map
    ; And the upper layer, because of its palette: the screen's faces use up
    ; to eight BG2 palettes, that is entries 16 to 127, and `load_map`
    ; restores only the background's. The upper ones start at ABOVE_FIRST,
    ; which can fall in there.
    jsr load_above
    jsr aplicar_tinte
    stz destello_listo          ; `pal_buf` was from before; if the flash goes on,
                                ; the next frame builds it again
    jsr subir_tinte
    rts
.endproc

; And coming back from a **battle**, which overwrites much more than the slot
; screen.
;
; `volver_al_mapa` is enough for the shop, the menu and the slots because all
; three write nothing but `RANURA_VRAM` and `RANURA_MAP`, chosen to fall
; inside BG1's tile bank in every layout. The battle scene is not:
; `escena_subir` uploads **32 KB**, that is words $4000 to $8000, plus its
; tilemap at $3800 and 64 bytes at word 0. In the layouts of `vram_layout`
; that takes out, besides BG1's bank:
;
;   $5800  the map's tilemap            `fill_window` fills it; in the layout
;                                       that moves it down to $1800 it is not
;                                       touched, and `fill_window` refills it
;                                       all the same
;   $7800  the upper layer's            the same
;   $6800  the window's tiles           `load_ventana`, with its tilemap and HDMA
;   the sprites                         `load_sprite`: they start at 0, and
;                                       word 0 takes out the hero's first two
;                                       tiles
;
; None of that is restored by `load_map`, so until 2026-09-13 the map came
; back from battle with the background turned to garbage. What does **not**
; go here is `load_npcs` or `load_ruta_graficos`: they copy tables from the
; cartridge to RAM, the battle does not touch them, and restoring them would
; erase whatever the events had moved before the battle.
;
; It goes apart from `volver_al_mapa` and not inside it so as not to charge
; the shop, the menu and the slots for the 64 columns of `fill_window`, which
; are the only moment when that much tilemap is written at once: they do not
; need it, and one more lost frame would be eaten by the suite cases that
; look at them.
.proc volver_de_batalla
.a8
.i16
    lda #$80
    sta INIDISP                 ; what follows writes VRAM by DMA
    jsl f:escena_cgram_reponer  ; the palettes the battlers took
    jsr load_sprite             ; the pose bank, the object palette and OBSEL
    jsr poses_npc_olvidar
    jsr load_ventana
    ; The grid, which the scene overwrote in the middle of bank $7F —it is
    ; `ESC_ESCENA`— if the map has more than 32 KB of grid. It is
    ; decompressed again in full, which is simpler than tracking where the
    ; second stream starts and costs the same as entering the map. Before
    ; `fill_window`, which reads it.
    jsl f:lz2_grilla + RAPIDO
    jsr fill_window
    jmp volver_al_mapa
.endproc

; Starts a teleport fade. A carries what has to be done when the screen
; reaches black; the map, if needed, is already in `fundido_mapa`.
.proc empezar_fundido
.a8
.i16
    sta fundido_que
    lda #1
    sta fundido
    ; The fade's clock is **loop iterations**, that is ticks, and not hardware
    ; frames: that way the fade lasts FUNDIDO_TOTAL ticks however long the
    ; map load inside the black takes.
    ;
    ; It was counting `boot_cuadros` —hardware frames— since the load started
    ; taking six or seven frames inside a single iteration: counting
    ; iterations the fade lasted that much longer **in frames**, and the
    ; harness, which counted frames, ended up offset. Since 2026-09-08 the
    ; harness counts ticks —see `vueltas`— so the clock is the same on both
    ; sides again and the one that absorbs the delay is the wall clock.
    ;
    ; The start is set by `fundido_desde`, in bank 1, because with the cut it
    ; is not `vueltas`: see `transicion_del_teletransporte.s`.
    jsl f:fundido_desde
    rts
.endproc

; One frame of the fade. Returns A nonzero while the game has to stay still,
; which is the whole time it lasts.
;
; RM2k freezes the whole scene while the transition runs: `Scene::MainFunction`
; sees `IsAsyncPending()` and calls `Player::Update(false)`, which updates
; nothing. Here it is the same by default: the main loop skips the
; interpreter, the hero, the events, the timer and everything that moves
; anything. What keeps running is the music, which in RM2k does not stop
; either.
.proc fundido_tick
.a8
.i16
    lda fundido
    beq no_hay
    lda vueltas                 ; the low byte is enough: the fade lasts 70
    sec
    sbc fundido_base
    cmp #FUNDIDO_TOTAL
    bcs terminar
    cmp #FUNDIDO_CARGA
    bcc rampa                   ; still going dark
    pha
    jsr cargar_lo_pedido        ; only once: it turns itself off
    pla
rampa:
    ; This frame's brightness. Going down, the ramp is read backwards.
    cmp #FUNDIDO_RAMPA
    bcs subiendo
    eor #$FF
    clc
    adc #FUNDIDO_RAMPA          ; FUNDIDO_RAMPA - 1 - t
    bra en_la_rampa
subiendo:
    sec
    sbc #(FUNDIDO_CUADROS + FUNDIDO_NEGRO)
    bcs en_la_rampa             ; past the load: the ramp back up
    lda #0                      ; the black in the middle
    sta brillo
    bra sigue
en_la_rampa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda fundido_rampa, x
    sta brillo
sigue:
    lda #1                      ; the game stays frozen
    rts
terminar:
    stz fundido
    lda #BRILLO_MAX
    sta brillo
no_hay:
    lda #0
    rts
.endproc

; The song the map being entered turns on, between `mapa_tema_callar` and the
; end of the load, or $FF if nothing has to be turned on. In far RAM because
; bank 0's BSS is full.
TEMA_DEL_MAPA = $7E6100

; What the map being entered does to the music, which is easyrpg's
; `Game_Map::PlayBgm`: its song, if it has one —`mapa_tema`, which already
; resolved the tree's inheritance—. Returns with A holding the song to turn on
; when the map is loaded, or $FF if nothing has to be touched, and in that
; case whatever was playing goes on.
;
; Nothing is touched in two cases:
;
; * `mapa_tema` at $FF: the map has no song, or it is `music_type` 1, "an
;   event decides". Also a song beyond `TEMA_TOTAL`, same as `op_bgm` does.
; * **the song is the one already playing**. `Game_System::BgmPlay` with the
;   same name does not restart it: going from one Rat Tracks map to the other
;   does not send `KSSMKEND` back to the start. With one exception, which is
;   theirs too: if it was fading out because of a `FadeOutBGM` —their
;   `music_stopping`— it does start from zero.
;
; "Is playing" is not only `music_apagada` at zero: with an MSU-1 track the
; SPC700 is silent on purpose and `music_apagada` is 1. That is why
; `MSU_SUENA` is checked first, which is the same thing `op_fade_bgm` does.
;
; If it has to change, it is silenced here, with the screen already black: the
; MSU-1 stops and the SPC700 releases the voices, as in `batalla_bgm`.
.proc mapa_tema_callar
.a8
.i16
    ldx fundido_mapa
    lda f:mapa_tema, x
    cmp #TEMA_TOTAL
    bcs nada                    ; $FF, or one the cartridge does not carry
    pha
    lda bgm_fundido
    bne cambia                  ; it was fading out: it starts over
    lda f:MSU_SUENA
    bne suena
    lda music_apagada
    bne cambia
suena:
    lda tema_actual + 1
    bne cambia
    pla
    cmp tema_actual
    bne cambia_ya
nada:
    lda #$FF
    rts
cambia:
    pla
cambia_ya:
    pha
    jsr msu_parar
    lda #$FF
    jsr batalla_bgm             ; silence: the voices release
    pla
    rts
.endproc

; What the fade has to do on its first black frame: load the map, or move the
; hero if the jump was to the same one. It is done once and turns itself off.
;
; The screen is put in forced blanking by hand instead of waiting for vblank:
; `cargar_mapa` writes VRAM and CGRAM by DMA and with the PPU drawing those
; writes are lost. It does not show, because the brightness is already zero.
.proc cargar_lo_pedido
.a8
.i16
    lda fundido_que
    beq listo
    pha
    lda #$80
    sta INIDISP
    stz brillo                  ; and let the next vblank leave it black
    pla
    cmp #FUNDIDO_MISMO
    bne carga
    jsr mover_heroe_a
    bra hecho
carga:
    ; The new map's song is decided **before** loading it, because if it
    ; changes the playing one has to be silenced before `paquete_cargar`
    ; builds the package: that one leaves in place the samples of the song it
    ; says is playing, and the one about to be turned on needs them in their
    ; place. See `mapa_tema_callar`.
    pha
    jsr mapa_tema_callar
    sta f:TEMA_DEL_MAPA
    pla
    cmp #FUNDIDO_PUERTA
    bne salto
    rep #$20
.a16
    lda fundido_mapa            ; the index goes in sixteen bits
    jsr cargar_mapa             ; the harness's: resets the jump cap
    sep #$20
.a8
    ; The hero appears standing still on the entry cell. No jump in the game
    ; needs this —`advance_step` only triggers a teleport with the step
    ; already finished, and `move_hero` recomputes `moving` on the first live
    ; frame— but here the save comes from outside, with RAM in any state, and
    ; starting halfway through a step is not what the test asked for.
    stz step_left
    stz moving
    bra prender
salto:
    rep #$20
.a16
    lda fundido_mapa            ; the index goes in sixteen bits
    jsr cargar_mapa_sin_eventos
    sep #$20
.a8
    ; And the new map's automatic events, to the queue. The page that
    ; requested the jump keeps running —its code is in ROM and the cursor was
    ; saved— so these only start when it ends, which is RM2k's order:
    ; `Game_Interpreter_Map::OnMapChange` does not touch the interpreter's
    ; stack, only the event ids.
    ;
    ; They used to never be marked. The comment said they were queued "when
    ; this one ends" and nobody did it: after a teleport, the destination
    ; map's events never ran. Nothing saw it because the only test that
    ; teleported looked at the tint, which is set by the origin map.
    ; Today `cargar_mapa_sin_eventos` does it, inside its refresh.
prender:
    ; And the map's song, with the package already uploaded: its samples came in
    ; it. It goes before any page of the new map runs, so a `PlayBGM` from an
    ; automatic event wins over it, which is RM2k's order: `Game_Map::PlayBgm`
    ; runs when the map is set up, before its events.
    lda f:TEMA_DEL_MAPA
    cmp #$FF
    beq hecho
    jsr music_start
hecho:
    stz fundido_que
    ; And OAM, which otherwise keeps the one of the map that was left. The
    ; loop does not rebuild it while the fade lasts —`build_oam` is one of the
    ; things it skips— so the ramp back up would draw the new map with the old
    ; sprites.
    jsr build_oam
listo:
    rts
.endproc

; Moves the hero to (entrada_x, entrada_y) without touching the map. It is
; what a teleport that does not change map does: the event table, their
; positions, the routes that are running and the queued pages stay as they
; were.
.proc mover_heroe_a
.a8
.i16
    rep #$20
.a16
    lda entrada_x
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; the cell is 16 pixels
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumed
    sep #$20
.a8
    stz step_left               ; a step halfway along is cut short
    stz moving
    jsr menu_olvidar            ; and a menu request too: `MoveTo`
    jsl f:encuentro_mover       ; and the distance walked, which is the other thing it erases
    jsr follow_camera
    jsr fill_window             ; the camera jumped: the tilemap is filled again
    jsr init_hero_ptr
    rts
.endproc
