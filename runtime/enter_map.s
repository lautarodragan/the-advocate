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
.proc enter_map_no_events
.a16
.i16
    ; A page that goes on after the jump keeps its bytecode, which is about
    ; to be overwritten: see `code_carry_before`. With `map_current` still
    ; the one being left.
    pha
    sep #$20
.a8
    jsl f:code_carry_before + FAST
    rep #$20
.a16
    pla
    sta map_current             ; to know whether the next jump changes map
    sep #$20
.a8
    jsr turn_clear              ; the rows are going to be different
    jsr battle_anim_clear       ; and the battle animation does not carry on
    rep #$20
.a16
    stz sub_n                   ; and the tile substitutions are lost when
    stz sub_refresh             ; loading a map, as in RM2k: see `sub_n`
    sep #$20
.a8
    jsl f:pic_clear + FAST      ; and the pictures are erased: it is the
                                ; `erase_on_map_change` of Game_Pictures, and
                                ; besides, their tiles belong to the map
    stz counter_visible         ; and the counter, which in RM2k is pictures
    jsl f:package_load_l        ; the map's audio, during the fade
    rep #$20
.a16
    lda map_current
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times MAP_STRIDE, which is 128
    sta map_ofs
    tax

    ; The battle animation's layout on this map: which tile its box falls on
    ; and with which palette, or that it is not drawn here. It needs
    ; `map_current` and `map_ofs`, which have just been set.
    phx
    sep #$20
.a8
    jsr anim_drawing_map        ; enters and leaves with the accumulator at eight
    jsl f:encounter_map         ; and every how many steps there is an encounter here
    rep #$20
.a16
    plx

    ; What is looked at often is copied; what is used once is read in place.
    lda f:map_table + M_MAP_BW, x
    sta map_width
    asl a
    sta map_cw                  ; the width in 8x8 cells is double
    lda f:map_table + M_MAP_BH, x
    sta map_height
    asl a
    sta map_ch
    lda f:map_table + M_CAM_MAX_X, x
    sta cam_max_x
    lda f:map_table + M_CAM_MAX_Y, x
    sta cam_max_y
    lda f:map_table + M_EV_COUNT, x
    ; Everything that sweeps events goes up to here and not up to `EV_MAX`:
    ; with the hundred and twenty, a map with four events swept a hundred and
    ; sixteen too many and that was enough to lose the frame.
    sta ev_total
    lda f:map_table + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; times sixteen: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "the computation above multiplies by sixteen by hand"
    sta npc_total

    ; The pointers to the poses, in ROM, and to the block table and its
    ; passability, which live in WRAM behind the grid —`lz2_grid` puts them
    ; there, below—. The second block pointer points eight bytes further,
    ; which is where each block stores its upper layer; adding eight cannot
    ; overflow the bank because the converter keeps the whole table inside
    ; $7F's half: see `check_map` in `rm2k-snes-mapdata`.
    lda f:map_table + M_PTR_NPC_POSES, x
    sta poses_ptr
    lda f:map_table + M_PTR_MAP_BLOCKS, x
    sta blocks_ptr
    clc
    adc #8
    sta blocks8_ptr
    lda f:map_table + M_PTR_BLOCK_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_MAP_BLOCKS + 2, x
    sta blocks_ptr + 2
    sta blocks8_ptr + 2
    lda f:map_table + M_PTR_BLOCK_PASS + 2, x
    sta pass_ptr + 2
    lda f:map_table + M_PTR_NPC_POSES + 2, x
    sta poses_ptr + 2

    ; Where the hero starts: wherever the record says, unless the caller left
    ; an entry set, which is what a door does. The camera is placed before
    ; filling the window, because the window is filled around it.
    rep #$20
.a16
    lda entry_x
    cmp #$FFFF
    bne from_door
    lda f:map_table + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda f:map_table + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra set

from_door:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; the cell is 16 pixels
    sta hero_x
    lda entry_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entry_x                 ; consumed: the next load goes back to the record

set:
    sep #$20
.a8
    lda f:map_table + M_BG12NBA_VALUE, x
    sta BG12NBA
    ; And the background's tilemap, which also comes from the layout: almost
    ; always at $5800, but not in all of them. It is copied to RAM because
    ; `build_column` and `build_row` add it, and they have X busy and cannot
    ; read the table.
    rep #$20
.a16
    lda f:map_table + M_VRAM_MAP, x
    sta f:FAR_VRAM_MAP
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

    ; Whether the map shows its panorama, before loading anything: the
    ; loads ask. See pano.s.
    jsl f:pano_find
.ifdef paint_table
    jsl f:paint_find            ; and whether it is painted: see painted.s
.endif
    ; The grid, to WRAM, before anyone asks about a cell: it comes compressed.
    ; See `GRID`.
    jsl f:lz2_grid + FAST
    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    jsr load_route_graphics
    jsr load_ev_pos             ; and where each event starts, with or without a graphic
    stz refresh
    ; Before the refresh, not after: the previous map's marks are worth
    ; nothing here —their event indices would point at other events— and the
    ; refresh is the one that turns `FLAG_AUTO` back on for the ones it
    ; applies to.
    jsr clear_waits
    jsr clear_parallel
    jsr page_routes             ; and the move routes of the active pages themselves
    ; The actor table belongs to this map, so where the leader's poses fall
    ; changes when changing map even if the party is the same.
    jsr pick_hero_graphic
    jsr clear_tilemaps          ; what `fill_window` does not overwrite, from the map before
    jsr fill_window             ; leaves strip_step_col ready, which the other one uses
    jsr load_window             ; tiles, palette, its own tilemap and HDMA tables
    jsr init_hero_ptr

    ; The tint is game state, not map state: it survives the teleport. The
    ; palettes just uploaded are the cartridge's, untinted, so they are tinted
    ; again here. With a neutral tint the computation is i*100/100 and leaves
    ; the colors where they were, so there is no need to ask whether there is
    ; a tint: the path is always the same.
    jsr apply_tint
    stz flash_ready             ; whatever was in `pal_buf` no longer
                                ; belongs to this map; the next frame
                                ; builds it again if the flash goes on
    jsr upload_tint             ; the screen is off: it goes now
    ; And the carried bytecode, now that nothing else uses `LZ2_BUFFER`.
    jsl f:code_carry_after + FAST
    ; And the mode, if this map's panorama or the previous one's asks to
    ; change it.
    jsl f:pano_ppu
    rts
.endproc

; And this is what has to be called: it loads the map and runs its automatic
; events.
;
; If an event requests a teleport, the cycle repeats here and not inside the
; interpreter. Calling enter_map from the interpreter would be recursion,
; and two maps that point at each other would make it infinite: the stack
; sinks to the bottom and the console does anything at all. The cap on
; iterations is there for the same reason, for the case where they point at
; each other through a longer cycle.
.proc enter_map
.a16
.i16
    pha                         ; the map index, which what follows would clobber
    sep #$20
.a8
    lda #JUMPS_MAX
    sta jumps_left              ; with stx it would be two bytes and clobber the next one
    rep #$20
.a16
    pla
    jsr enter_map_no_events
    rts
.endproc

; Restores what the slot screen overwrote on the map, and nothing else. It is
; for the save point, which opens it with the game running; the title does
; not need it because on leaving it loads the whole map.
;
; What it overwrote, in VRAM words: the tiles at SLOT_VRAM and the tilemap
; at SLOT_MAP, which are chosen to fall inside BG1's tile bank **in every
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
; subset of `enter_map_no_events`, chosen by hand: what is missing from
; there is state —events, routes, poses, the VRAM queue— and restoring it
; would restart the game.
;
; The screen is turned off by hand and **is not turned back on here**:
; `flush_video` writes `brightness` in the next vblank, and so the map appears on
; a whole frame and not halfway through one. We get here just after a vblank
; starts —the slot screen leaves right after its `read_pad`—, so the
; turn-off also lands on a frame boundary. Measured: **two** black frames
; show and then the map, because `load_map`'s 30 KB do not fit in one vblank
; and that tick lasts two frames —`lost_frames` counts one—. In RM2k
; closing the scene takes a transition, so it does not look out of place.
.proc back_to_map
.a8
.i16
    lda #$80
    sta INIDISP
    jsr ppu_init
    ldx map_ofs
    lda f:map_table + M_BG12NBA_VALUE, x
    sta BG12NBA
    lda f:map_table + M_VRAM_MAP + 1, x
    ora #MAP_LAYOUT
    sta BG1SC                   ; the battle leaves it pointing at its scene
    jsr load_map
    ; And the upper layer, because of its palette: the screen's faces use up
    ; to eight BG2 palettes, that is entries 16 to 127, and `load_map`
    ; restores only the background's. The upper ones start at ABOVE_FIRST,
    ; which can fall in there.
    jsr load_above
    jsr apply_tint
    stz flash_ready             ; `pal_buf` was from before; if the flash goes on,
                                ; the next frame builds it again
    jsr upload_tint
    ; `load_map` and `load_above` decompress into `LZ2_BUFFER`, and so does
    ; the battle —it is `SCN_CLEAN`—: the battle animation's last frame was
    ; there, and its tiles can no longer be erased one by one. Its box starts
    ; clean, and the next frame is built over it. See `anim_buf_clear`.
    jsl f:anim_buf_clear
    ; And for the same reason the bytecode of a page that goes on from
    ; another map: see `code_carry_after`.
    jsl f:code_carry_after + FAST
    rts
.endproc

; And coming back from a **battle**, which overwrites much more than the slot
; screen.
;
; `back_to_map` is enough for the shop, the menu and the slots because all
; three write nothing but `SLOT_VRAM` and `SLOT_MAP`, chosen to fall
; inside BG1's tile bank in every layout. The battle scene is not:
; `scene_upload` uploads **32 KB**, that is words $4000 to $8000, plus its
; tilemap at $3800 and 64 bytes at word 0. In the layouts of `vram_layout`
; that takes out, besides BG1's bank:
;
;   $5800  the map's tilemap            `fill_window` fills it; in the layout
;                                       that moves it down to $1800 it is not
;                                       touched, and `fill_window` refills it
;                                       all the same
;   $7800  the upper layer's            the same
;   $6800  the window's tiles           `load_window`, with its tilemap and HDMA
;   the sprites                         `load_sprite`: they start at 0, and
;                                       word 0 takes out the hero's first two
;                                       tiles
;
; None of that is restored by `load_map`, so until 2026-09-13 the map came
; back from battle with the background turned to garbage. What does **not**
; go here is `load_npcs` or `load_route_graphics`: they copy tables from the
; cartridge to RAM, the battle does not touch them, and restoring them would
; erase whatever the events had moved before the battle.
;
; It goes apart from `back_to_map` and not inside it so as not to charge
; the shop, the menu and the slots for the 64 columns of `fill_window`, which
; are the only moment when that much tilemap is written at once: they do not
; need it, and one more lost frame would be eaten by the suite cases that
; look at them.
.proc back_from_battle
.a8
.i16
    lda #$80
    sta INIDISP                 ; what follows writes VRAM by DMA
    jsl f:scene_cgram_restore   ; the palettes the battlers took
    jsr load_sprite             ; the pose bank, the object palette and OBSEL
    jsr npc_poses_forget
    jsr load_window
    ; The grid, which the battle overwrote: its half of bank $7E holds the
    ; troop's battlers —`SCN_BATTLERS`—, and in the middle of bank $7F is
    ; `SCN_SCENE`, over the rest of the grid and what lives behind it. It is
    ; decompressed again in full, as when entering the map. Before
    ; `fill_window`, which reads it.
    jsl f:lz2_grid + FAST
    jsr fill_window
    jmp back_to_map
.endproc

; Starts a teleport fade. A carries what has to be done when the screen
; reaches black; the map, if needed, is already in `fade_map`.
.proc start_fade
.a8
.i16
    sta fade_kind
    lda #1
    sta fade
    ; The fade's clock is **loop iterations**, that is ticks, and not hardware
    ; frames: that way the fade lasts FADE_TOTAL ticks however long the
    ; map load inside the black takes.
    ;
    ; It was counting `boot_frames` —hardware frames— since the load started
    ; taking six or seven frames inside a single iteration: counting
    ; iterations the fade lasted that much longer **in frames**, and the
    ; harness, which counted frames, ended up offset. Since 2026-09-08 the
    ; harness counts ticks —see `ticks`— so the clock is the same on both
    ; sides again and the one that absorbs the delay is the wall clock.
    ;
    ; The start is set by `fade_from`, in bank 1, because with the cut it
    ; is not `ticks`: see `teleport_transition.s`.
    jsl f:fade_from
    ; And **this** tick is already the fade's first: it darkens, and the
    ; animations do not count it. It is what the RPG_RT does, measured on
    ; 2026-09-29 with the map 16 cutscene: the first darker frame is 90 after
    ; the `Wait 15` that comes before the `Teleport` —the teleport's own
    ; frame— and the ChipSet's water stays still from that one to the last
    ; one of the fade, both included. Here it went dark one tick later, with
    ; the jump's tick still lit, and the round lasted a tick more than the
    ; original. Only the brightness is written: the load, if this tick is
    ; already past `FADE_LOAD` —the cut's is—, waits for the next one's
    ; `fade_tick`, at the top of the loop, and not here in the middle of it.
    lda ticks
    sec
    sbc fade_base
    jsr fade_brightness
    rep #$20
.a16
    lda f:frozen_ticks
    inc a
    sta f:frozen_ticks
    sep #$20
.a8
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
.proc fade_tick
.a8
.i16
    lda fade
    beq none
    lda ticks                   ; the low byte is enough: the fade lasts 68
    sec
    sbc fade_base
    cmp #FADE_TOTAL
    bcs finish
    cmp #FADE_LOAD
    bcc ramp                    ; still going dark
    pha
    jsr load_requested          ; only once: it turns itself off
    ; The cut for showing has no way back up: the fade ends on the load's
    ; tick, which stays frozen, and the next vblank already writes full
    ; brightness. And with the screen erased by an event it ends there too,
    ; but black: an `EraseScreen` is only the way down, and a teleport with
    ; the screen erased does not show it. See `teleport_transition.s`.
    jsl f:fade_after_load       ; carry: it ends here, with A the brightness
    bcs cut_in
    pla
ramp:
    jsr fade_brightness
    lda #1                      ; the game stays frozen
    rts
cut_in:
    sta brightness
    pla
    stz fade
    lda #1                      ; this tick, the load's, stays frozen
    rts
finish:
    stz fade
    lda #BRIGHTNESS_MAX
    sta brightness
none:
    lda #0
    rts
.endproc

; The brightness on tick A of the fade, counted from the teleport's own tick,
; which is 0 and already one step darker. Going down, the ramp is read
; backwards and starts at its second to last step —the last one is full
; brightness, which is what the tick before showed—; then the black in the
; middle; and going up the ramp ends on the fade's last tick, FADE_TOTAL - 1.
.proc fade_brightness
.a8
.i16
    cmp #(FADE_RAMP - 1)
    bcs down_done
    eor #$FF
    clc
    adc #(FADE_RAMP - 1)        ; FADE_RAMP - 2 - t
    bra in_ramp
down_done:
    sec
    sbc #(FADE_TOTAL - FADE_RAMP)
    bcs in_ramp                 ; past the load: the ramp back up
    stz brightness              ; the black in the middle
    rts
in_ramp:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda fade_ramp, x
    sta brightness
    rts
.endproc

; The song the map being entered turns on, between `map_song_mute` and the
; end of the load, or $FF if nothing has to be turned on. In far RAM because
; bank 0's BSS is full.
.pushseg
.segment "FARBSS"
MAP_SONG: .res 1
.popseg

; What the map being entered does to the music, which is easyrpg's
; `Game_Map::PlayBgm`: its song, if it has one —`map_song`, which already
; resolved the tree's inheritance—. Returns with A holding the song to turn on
; when the map is loaded, or $FF if nothing has to be touched, and in that
; case whatever was playing goes on.
;
; Nothing is touched in two cases:
;
; * `map_song` at $FF: the map has no song, or it is `music_type` 1, "an
;   event decides". Also a song beyond `SONG_TOTAL`, same as `op_bgm` does.
; * **the song is the one already playing**. `Game_System::BgmPlay` with the
;   same name does not restart it: going from one Rat Tracks map to the other
;   does not send `KSSMKEND` back to the start. With one exception, which is
;   theirs too: if it was fading out because of a `FadeOutBGM` —their
;   `music_stopping`— it does start from zero.
;
; The second is `song_playing`, which is also what a `PlayBGM` asks.
;
; If it has to change, it is silenced here, with the screen already black: the
; MSU-1 stops and the SPC700 releases the voices, as in `battle_bgm`.
.proc map_song_mute
.a8
.i16
    ldx fade_map
    lda f:map_song, x
    cmp #SONG_TOTAL
    bcs nothing                 ; $FF, or one the cartridge does not carry
    jsr song_playing
    bcs nothing                 ; it goes on
    pha
    jsr msu_stop
    lda #$FF
    jsr battle_bgm              ; silence: the voices release
    pla
    rts
nothing:
    lda #$FF
    rts
.endproc

; What map X —the cartridge's index, sixteen bits— allows, over the
; permissions: `Game_Map::Setup` writes the save, escape and teleport ones
; each time a map is entered, so a `ChangeSaveAccess` lasts until the next
; map, and a map that allows saving gives back what a page had forbidden.
; The tree's "the parent's" were resolved by the converter: `map_access`
; carries per map the bits it forbids. Only on a change of map and on a new
; game —`Setup`—: not on a jump to the same map, which RM2k does not set up
; again, nor on loading a save, whose permissions are the ones it carries
; (`SetupFromSave`). Keeps A.
;
; And the pure parallel common events are owed a run, as with the
; permission opcode: the one that forbids saving every frame while a switch
; is off —ABL's `DisableSaving`— takes it back down on the next frame, which
; is what RM2k's every frame gives.
.pushseg
.segment "FAR2"
.proc map_access_enter
.a8
.i16
    pha
    lda f:FAR_LENGTH + FAR_ACCESS
    and #<~ACCESS_MAP
    ora f:map_access, x
    sta f:FAR_LENGTH + FAR_ACCESS
    lda #1
    sta f:compar_owed
    pla
    rtl
.endproc
.popseg

; What the fade has to do on its first black frame: load the map, or move the
; hero if the jump was to the same one. It is done once and turns itself off.
;
; The screen is put in forced blanking by hand instead of waiting for vblank:
; `enter_map` writes VRAM and CGRAM by DMA and with the PPU drawing those
; writes are lost. It does not show, because the brightness is already zero.
.proc load_requested
.a8
.i16
    lda fade_kind
    beq ready
    pha
    lda #$80
    sta INIDISP
    stz brightness              ; and let the next vblank leave it black
    pla
    cmp #FADE_SAME
    bne load
    jsr move_hero_to
    bra made
load:
    ldx fade_map                ; what the new map allows: see map_access_enter
    jsl f:map_access_enter
    ; The new map's song is decided **before** loading it, because if it
    ; changes the playing one has to be silenced before `package_load`
    ; builds the package: that one leaves in place the samples of the song it
    ; says is playing, and the one about to be turned on needs them in their
    ; place. See `map_song_mute`.
    pha
    jsr map_song_mute
    sta f:MAP_SONG
    pla
    cmp #FADE_DOOR
    bne jump
    rep #$20
.a16
    lda fade_map                ; the index goes in sixteen bits
    jsr enter_map               ; the harness's: resets the jump cap
    sep #$20
.a8
    ; The hero appears standing still on the entry cell. No jump in the game
    ; needs this —`advance_step` only triggers a teleport with the step
    ; already finished, and `move_hero` recomputes `moving` on the first live
    ; frame— but here the save comes from outside, with RAM in any state, and
    ; starting halfway through a step is not what the test asked for.
    stz step_left
    stz moving
    bra on
jump:
    rep #$20
.a16
    lda fade_map                ; the index goes in sixteen bits
    jsr enter_map_no_events
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
    ; Today `enter_map_no_events` does it, inside its refresh.
on:
    ; And the map's song, with the package already uploaded: its samples came in
    ; it. It goes before any page of the new map runs, so a `PlayBGM` from an
    ; automatic event wins over it, which is RM2k's order: `Game_Map::PlayBgm`
    ; runs when the map is set up, before its events.
    lda f:MAP_SONG
    cmp #$FF
    beq made
    jsr music_start
made:
    stz fade_kind
    ; And OAM, which otherwise keeps the one of the map that was left. The
    ; loop does not rebuild it while the fade lasts —`build_oam` is one of the
    ; things it skips— so the ramp back up would draw the new map with the old
    ; sprites.
    jsr build_oam_settled
ready:
    rts
.endproc

; Moves the hero to (entry_x, entry_y) without touching the map. It is
; what a teleport that does not change map does: the event table, their
; positions, the routes that are running and the queued pages stay as they
; were.
.proc move_hero_to
.a8
.i16
    rep #$20
.a16
    lda entry_x
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; the cell is 16 pixels
    sta hero_x
    lda entry_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entry_x                 ; consumed
    sep #$20
.a8
    stz step_left               ; a step halfway along is cut short
    stz moving
    jsr menu_forget             ; and a menu request too: `MoveTo`
    jsl f:encounter_move        ; and the distance walked, which is the other thing it erases
    jsr follow_camera
    jsr fill_window             ; the camera jumped: the tilemap is filled again
    jsr init_hero_ptr
    rts
.endproc
