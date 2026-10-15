.segment "CODE"

; --- boot -------------------------------------------------------------------
.proc reset
    sei
    clc
    xce                         ; into the 65816's native mode
    jml f:fast + FAST           ; to the fast mirror: see MEMSEL
fast:
    rep #$30                    ; 16-bit A, X and Y
.a16
.i16
    ldx #$1FFF
    txs
    ; The data bank, set to the code's. On a real reset the 65816 leaves it at
    ; zero and everything below would work the same, but since 2026-09-13 we
    ; also get here with a `jml` —the Game Over of `op_battle`— and there the
    ; data bank is the bytecode's, that is, a cartridge bank: `sta INIDISP`
    ; would write to ROM instead of the PPU.
    phk
    plb

    sep #$20
.a8
    lda #$80
    sta INIDISP                 ; forced blanking: VRAM is only touched this way
    ; The region is not a cosmetic detail: the music stream is built in
    ; frames, and a PAL console gives 50 per second instead of 60. Without
    ; correcting it the song plays 17% slow.
    lda STAT78
    and #$10
    sta is_pal
    stz pal_tick

    jsr ppu_reset               ; the console does not boot clean; the emulator does
    lda #$01
    sta MEMSEL                  ; the mirror's ROM, fast
    jsr msu_detect              ; does the music come from a track?
.ifdef MSU_REQUIRED
    jsl f:msu_required          ; and if the game needs it: see msu1.s
.endif

    ; After the reset, not before: ppu_reset turns NMITIMEN off along with
    ; everything else, so enabling it first would be no use.
    lda #$01
    sta NMITIMEN                ; let the console read the pads by itself
    stz boot_frames
    stz ticks                   ; RAM starts with garbage and the harness
    stz ticks + 1               ; reads it from frame zero
    rep #$20
.a16
    lda #0
    sta f:frozen_ticks          ; and this one, which the animations subtract
    sep #$20
.a8
    lda #$81
    sta NMITIMEN                ; and the NMI, which counts the boot frames

    jsl f:pano_clear            ; before `ppu_init`, which asks it
    jsr ppu_init

    ; No entry set: the first map starts wherever its record says.
    rep #$20
.a16
    lda #$FFFF
    sta entry_x
    sep #$20
.a8

    ; The switches all start off, like a new RM2k game, and the screen
    ; untinted.
    ldx #$0000
    lda #0
erase_switches:
    sta f:switches, x           ; far: there is no long `stz`
    inx
    cpx #SWITCH_BYTES
    bne erase_switches
    lda #TINT_NEUTRAL
    sta tint_r
    sta tint_g
    sta tint_b
    sta tint_s
    stz jump_has
    lda #$FF                    ; no song remembered, like a new
    sta f:REMEMBERED_SONG       ; game: see `op_memorized_bgm`
    stz anim_pend               ; RAM starts with garbage and this triggers DMAs
    stz panic                   ; RAM starts with garbage, and 85 is not a code
    stz gold
    stz gold + 1
    stz gold + 2
    ; The party goes before loading the first map: `enter_map` picks what
    ; the hero is drawn with, and without this it would read the garbage RAM
    ; starts with. The party the game starts with, from the game's database.
    ; The hero's graphic comes from the first one, so this decides which
    ; sprite shows; that in this game actor 10 is invisible is game data, not
    ; a bug.
    ldx #$0000
copy_party:
    cpx #PARTY_INITIAL_N
    beq party_ready
    lda party_initial, x
    sta party, x
    inx
    bra copy_party
party_ready:
    rep #$20
.a16
    lda #PARTY_INITIAL_N
    sta party_n                 ; 16 bits: X and Y compare it whole
    sep #$20
.a8

    ; The interpreter and the route, at zero before loading anything. RAM
    ; starts with garbage and this reads it on the first frame: with
    ; `ev_waiting` at anything it stays counting down forever and no page
    ; runs, and with `route_i` less than `route_n` `move_hero` believes there is
    ; a forced move route pending and never reads the pad —the hero does not
    ; move—.
    ;
    ; The route one was found by taro playing in mednafen, not by the suite,
    ; and that is the part that matters: **what snes9x leaves in RAM is always
    ; the same**, so it hides exactly the errors a fixed pattern hides. With
    ; these two uninitialized, `route_i < route_n` is false on all ten snes9x
    ; runs and the error disappears; on bsnes with high entropy it shows. The
    ; whole suite was green with this inside, and on real hardware it would
    ; have failed just like in mednafen. It is measured: with these two
    ; uninitialized by hand and ten runs per core, snes9x gives 0 of 10 red
    ; and bsnes 2 of 10. Against that there is
    ; `abl/tests/rpgmaker/test_cores.py` in the-advocate-ports, which runs the same ROM on snes9x
    ; and on bsnes —the latter with `bsnes_entropy=High`— and compares the two
    ; screens with each other; that file has the rest of the numbers. Verified
    ; on 2026-09-16 by removing these two lines: of five runs, four red.
    stz ev_active
    jsr clear_waits
    stz route_n                 ; no forced move route pending
    stz route_i
    stz route_wait
    lda #8
    sta route_freq              ; the usual one, until an OP_ROUTE says otherwise
    ; And the rest of what a route leaves on. RAM starts with garbage —snes9x
    ; fills it with $55— so without this the hero would start walking through
    ; walls and with the animation stopped.
    stz route_jump
    stz route_crosses
    stz route_anim_for
    stz crossing
    stz crossing + 1
    stz tint_pending
    ; And the message window. `msg_open` with garbage leaves the page
    ; blocked forever: `events_tick` believes there is a message on screen
    ; and waits for an A that no longer closes anything. It is measured
    ; —without this `stz`, `snes-cerrar` fails on all twelve runs, and on
    ; snes9x as well as on bsnes—.
    stz msg_open
    stz pick_active
    stz msg_state
    stz msg_upload
    stz tl_on                   ; no screen has written text yet
    ; The two that say who opened the message. With garbage, `pair_ev` would
    ; make the foreground record any owner at all and `one_parallel` would skip
    ; forever the event that had that number: it is one of the errors
    ; `test_cores.py` sees and a golden does not, because bsnes starts WRAM
    ; with garbage and snes9x at zero.
    lda #$FF
    sta msg_owner
    sta pair_ev
    ; And its escape queue, for the same reason: a pause with garbage would
    ; stop the page just like `msg_open`. Today they are not read without
    ; `msg_start` having written them, but that holds only as long as the
    ; guard above stays `msg_open | msg_state`.
    rep #$20
.a16
    lda #0
    sta f:FAR_MSG_PAUSE         ; `stz` has no long mode
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ; And where the window is: `load_window` builds its HDMA tables from it
    ; before any window has decided, and a garbage position would index past
    ; `place_rows`. Nothing is seen —the HDMA is off until a window opens, and
    ; that one decides first—, but the tables would be.
    lda #2
    sta f:MSG_PLACE
    ; The two pad ones are just in case and not for a bug that was seen:
    ; `read_pad` rewrites them before anyone looks at them. They cost two
    ; instructions.
    stz pad_a
    stz pad_a_prev
    stz autofire
    stz arrows_frames           ; with an arrow held since power-on
    stz arrows_repeated
    lda #HERO_WALKER
    sta walker
    lda #HERO_LAYER_INDEX
    sta walker_layer
    stz shake_pos
    stz shake_pos + 1
    stz tint_ready
    lda #VQ_PER_FRAME
    sta vq_cap
    stz shake_remain
    stz shake_remain + 1
    stz flash_level             ; RAM starts with garbage: without this the
    stz flash_level + 1         ; first frame comes out flashed
    stz flash_remain
    stz flash_ready
    rep #$20
.a16
    stz ev_waiting
    stz ev_cur
    sep #$20
.a8

    ; Facing the camera, as RM2k starts. It goes before loading the first map
    ; because its events run there, and a forced move route can turn it: if
    ; this were after, it would overwrite what the route just decided.
    lda #DIR_DOWN
    sta hero_dir
    sta hero_heading
    stz hero_lock               ; and free to turn: RAM starts with garbage
    stz hero_hidden             ; and seen, for the same reason

    ; The timer starts off and at zero. It goes here and not in `enter_map`
    ; because in RM2k it lives in `Game_Party`: it survives maps, which is
    ; exactly what the game uses it for. RAM starts with garbage —snes9x fills
    ; it with $55— so without this it would be seen running by itself.
    stz timer_active
    stz timer_visible
    stz counter_visible         ; `enter_map` clears it too, but the title
                                ; screen comes first and draws the timer's
                                ; palette entries by that flag
    stz timer_sub
    rep #$20
.a16
    stz timer_sec
    sep #$20
.a8
    jsr timer_digits

    ; RAM starts with garbage —snes9x fills it with $55— and `flush_video`
    ; looks at both: without this the first vblank would turn the screen on
    ; with whatever brightness was left, and the loop would start believing
    ; it was inside a fade.
    stz fade
    lda #BRIGHTNESS_MAX
    sta brightness
    stz bgm_fade                ; and the same with the song's
    jsl f:boot_transition           ; and the teleport, with fade
    jsl f:encounter_boot        ; the encounters' random seed
    jsl f:walk_boot + FAST      ; and the walkers'
    jsl f:speed_keys_boot       ; and L and R's bonus on the hero's speed
    jsl f:share_boot + FAST     ; and no map with shared slots yet

    ; If the cartridge has a saved game, it is loaded here: the switches it
    ; carries decide which page is active on each event, so they have to be
    ; set **before** loading the map. And the entry is built from the saved
    ; cell, which is how a door tells `enter_map` where to plant the hero.
    lda #$FF
    sta slot                    ; none loaded; RAM starts with garbage
    ; The random seed, and the variables at zero: far RAM also starts with
    ; garbage, and a loaded save overwrites them afterwards.
    jsr clear_variables
.if ::WINDOW_SYSTEMS > 1
    lda #0                      ; the starting System, which a save overwrites
    sta f:WINDOW_SYSTEM
    sta f:WINDOW_SWAP
.endif
    jsr initial_equipment_set
    jsl f:hp_initial_set
    jsl f:initial_skills_set
    jsl f:compar_clear          ; and no parallel common event running
    jsr actor_gfx_clear
    jsl f:actor_names_clear     ; and no one renamed
    jsr weather_clear
    jsr se_clear
    jsr music_clear
    jsr turn_clear
    jsl f:aram_clear_l
    jsr battle_anim_clear
    jsl f:pic_clear + FAST      ; RAM starts with garbage
    lda #0
    sta f:GO_WAIT               ; the harness looks at it: see game_over.s
    ; The slot screen's flag too: with $55 the harness would see it open from
    ; the reset. That is what happened on 2026-09-10 with the two counters
    ; that "gave 85": they were reading the emulator's garbage.
    stz menu_open
    ; With a title screen this is not done here: loading or starting over is
    ; decided by the menu, and until the player picks it the saved game is not
    ; touched. Without a title screen —which is the whole suite— the usual
    ; still happens, that is, if there is a save it loads by itself.
    lda #<TITLE_TILES
    ora #>TITLE_TILES
    bne fresh
    lda #0                      ; no menu to choose, always the first
    jsr set_slot
    jsr load_game
    beq fresh
    jsr save_entry
    rep #$20
.a16
    lda map_current             ; the index goes in sixteen bits
    bra load
.a8
fresh:
    ldx #MAP_INITIAL            ; a new game enters the first map: its permissions
    jsl f:map_access_enter
    rep #$20
.a16
    lda #MAP_INITIAL
load:
    jsr enter_map
    sep #$20
.a8
    jsr clear_oam

    stz step_left               ; standing, no step in progress
    stz pad                     ; RAM starts with garbage and move_hero reads it
    lda #1
    sta anim_step               ; the middle frame: the standing pose
    stz anim_timer

    jsr build_oam_settled
    jsr flush_video

    lda #$0F
    sta INIDISP                 ; screen on, full brightness

    ; The upload to the SPC700 goes after turning the screen on, not before:
    ; with the map's audio package it is a third of a second, and this way the
    ; map shows up right away instead of making you stare at a black screen
    ; until it ends.
    ;
    ; And before uploading anything, command 4: **the SPC700 goes back to its
    ; IPL ROM**. We get here two ways and only one of them leaves the SPC700
    ; as if freshly powered on. With the console's reset button the line
    ; reaches both processors and the IPL starts by itself; with the
    ; `jml reset` of `op_battle`'s Game Over, it does not: the SPC700 keeps
    ; running the driver and the $AA/$BB greeting that `spc_upload` waits for
    ; **never** arrives. That was the hang of the trap chest in the Rat Tracks
    ; —screen on, map drawn and the game stuck—, and any Game Over had the
    ; same one.
    ;
    ; With the IPL running this does no harm: while it waits for $CC it looks
    ; at port 0, and here ports 2 and 3 are written. The token is incremented
    ; without waiting for an acknowledgement, because on the other side there
    ; is no longer anyone to return it.
    lda #APU_CMD_IPL
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    jsr spc_upload
    ; Port 2 is the driver's command, and `spc_upload` leaves it with whatever
    ; it sent last: at zero, the driver reads DSP pairs.
    stz APUIO2
    ; And the boot map's audio package: `enter_map` could not upload it
    ; because the driver was not running yet. See `package_load`.
    lda #1
    sta f:APU_READY
    jsl f:package_load_l
    jsr music_boot

    ; The title image, decompressed to WRAM **before** the wait, which is
    ; where there are frames to spare: decompressing it when showing it was
    ; nine more frames of black before the title. `title_upload` uploads it.
    ; A ROM with a title can go past BOOT_FRAMES because of this, and it does
    ; not matter: what counts frames from the reset is the loop, and that is
    ; reached after the title.
.ifdef SCREEN_TITLE
    ldx #(SCREEN_TITLE * SCREEN_ROW)
    jsl f:screen_decompress
.endif

    ; And we wait for boot to last what it always lasts: BOOT_FRAMES.
wait_boot:
    lda boot_frames
    cmp #BOOT_FRAMES
    bcc wait_boot
    ; The NMI keeps counting after boot: it is the only way to know whether a
    ; loop iteration overran the frame. See `count_lost`.
    lda boot_frames
    sta nmi_seen
    stz lost_frames

    ; And from here the music runs by itself, in `irq_music`: once per frame
    ; on line IRQ_LINE, however long the loop takes. It goes after the wait
    ; and not before so that the song starts on the same frame as when the
    ; loop played it.
    lda #<IRQ_LINE
    sta VTIMEL
    lda #>IRQ_LINE
    sta VTIMEH
    lda #$A1
    sta NMITIMEN                ; the NMI, the pads and the vertical IRQ
    cli

    ; The title screen, if this ROM has one. It goes **after** boot has
    ; finished counting its BOOT_FRAMES and not before: that way a ROM
    ; without a title reaches the loop on exactly the usual frame, and the 96
    ; cases of the suite —which count frames from the reset— never learn that
    ; this exists.
    jsr title_screen

loop:
    jsr wait_vblank
    ; The pad first: the console reads it by itself when vblank starts and we
    ; have to wait for that to begin. If something long were done before —the
    ; OAM DMA, for example— we would arrive with the read already finished,
    ; and waiting for it to start would mean waiting for the next frame: half
    ; a frame per iteration.
    jsr read_pad
    jsr flush_video             ; the previous frame's, still in vblank
    ; A teleport's fade freezes the whole game while it lasts, like RM2k: the
    ; only thing that keeps running is the music. See `fade_tick`.
    jsr fade_tick
    bne frozen
    ; From here down the frame follows the order of `Game_Map::Update`
    ; —easyrpg's `game_map.cpp:1256-1318`—, and what rules is **where the
    ; player falls**: there `UpdateMapEvents` goes before
    ; `game_player->Update()` (`:1274` against `:1288`) and
    ; `UpdateForegroundEvents` goes after (`:1310`), with `UpdateMessage`
    ; (`:1297`) and `UpdateTimers` (`:1304`) in between.
    ;
    ; What is **not** in that order are the screen ticks —the flash, the
    ; shake, the panned camera, the picture, the rain—: there they are
    ; `game_screen->Update()` and `game_pictures->Update()` and go at
    ; `:1305`, that is, before the interpreter, and here they go after. None
    ; of them decides whether something moves or when, so the difference is
    ; one frame in what is seen and not in what happens; moving them is
    ; another change, with its goldens.
    jsr map_events              ; `UpdateMapEvents`: refresh, automatic and
                                ; parallels, **before** the hero
    jsr animate_still           ; the ones that animate without moving, before
                                ; the routes: if one grabs one, it wins the slot
    jsr move_events             ; and the events' forced move routes, which are
                                ; the part of `UpdateMapEvents` that walks
                                ; —`Game_Character::Update()` from
                                ; `Game_Event::Update`, `game_event.cpp:608`—.
                                ; They go here and not after the interpreter so
                                ; that an event and the hero start the route a
                                ; page just gave them on the same frame: both,
                                ; on the next one. With the interpreter still
                                ; above the hero both started one frame earlier
                                ; and tied; with it below, leaving them down
                                ; there broke the tie, and `stop-routes` showed
                                ; it with the NPC one frame ahead of the hero.
.if ::HERO_SPEED_KEYS
    jsl f:speed_keys            ; L and R, before the hero walks: not RM2k's
.endif
    jsr move_hero               ; `game_player->Update()`
    jsr request_menu            ; B, at the end of the hero: see `request_menu`
    ; The timer goes **before** the interpreter, which is where
    ; `Game_Map::Update` puts it: `UpdateTimers()` runs and only then
    ; `UpdateForegroundEvents`. That is, the page that starts it does not get
    ; a frame on the same frame it starts it. After the interpreter the ROM
    ; was one frame ahead of RM2k forever, and it only showed on the frames
    ; where the colon blinks or a digit changes.
    jsr timer_tick
    ; `UpdateForegroundEvents`, **after** the hero: what the step just
    ; finished queued —a touch event, a chest, a trap— starts on this same
    ; frame and not on the next. It was above `move_hero` until 2026-09-20,
    ; and that cost every touch a frame: the queue sweep had already passed
    ; when `advance_step` filled it.
    jsr events_tick
    ; And the `Teleport` a parallel may have requested, if the foreground did
    ; not handle it: `events_tick` looks at `jump_has` only after running
    ; one of its pages, and with the foreground idle it leaves earlier. In
    ; RM2k the pending jump is handled after `Game_Map::Update`, whatever runs
    ; (`Scene_Map::UpdateStage2`). They are the race's 126 exits —each car,
    ; each finish line and the bridge—, and until it went in no `release`
    ; page jumped from a parallel.
    lda jump_has
    beq no_jump_pending
    jsr events_handle_jump
no_jump_pending:
    jsr event_tint             ; the tint the interpreter may have requested, right
                                ; after it: otherwise it would apply a frame late
    jsr battle_anim_tick        ; the battle animation, before the
                                ; flashes it triggers
    jsr anim_drawing_tick       ; and its drawing, right after: both advance the
                                ; same RM2k clock and the drawing lasts longer
    jsr flashes_tick            ; and the flashes, in the same place
    jsr shake_tick              ; and one of the screen shake
    jsr pan_tick                ; and one of the camera panned away from the hero
    jsl f:pic_tick + FAST       ; and one of a picture's fade. It goes **before**
                                ; the flash and not after: both build their
                                ; palette in `pal_buf`, and the flash leaves
                                ; its own there waiting for the vblank. The
                                ; other way round, the picture overwrote the
                                ; background's first sixteen colors on the
                                ; frame where both run.
    jsr flash_tick              ; and one of the screen flash
    jsr rain_tick               ; and one of the rain
    jsr animate_hero
    jsr follow_camera
    jsr stream_map              ; the column or row the camera uncovered
    jsl f:pano_tick             ; and the panorama's, if the map shows one
.ifdef paint_table
    jsl f:paint_tick            ; and a painted map's slots: see painted.s
.endif
    jsr message_tick            ; and a few characters of the message being
                                ; composed, if there is one
    jsr build_oam               ; and the next one is built, now outside vblank
    bra counted
frozen:
    ; A fade iteration: the tick runs —the fade and the harness count it—
    ; but the world does not, and neither do the map animations. See
    ; `frozen_ticks`.
    rep #$20
.a16
    lda f:frozen_ticks
    inc a
    sta f:frozen_ticks
    sep #$20
.a8
counted:
    rep #$20
.a16
    inc ticks
    sep #$20
.a8
    jsr anim_tick               ; which ChipSet drawing is due on the next
                                ; iteration, so the vblank only has to upload it
    jsr count_lost
    bra loop
.endproc

; How many vblanks went by since the previous iteration: one is normal, and
; each extra one is a frame the ROM lost, because the iteration took longer
; than a frame and `wait_vblank` had to wait for the next. It is checked here,
; at the end of the iteration, and not on leaving `wait_vblank`: there this
; frame's NMI may not have run yet. Against a golden a lost frame is a
; position that lags behind, and the comparison charges it in pixels without
; saying why; this counter says why. The tests read it through the emulator's
; WRAM —`Session.lost_frames`—, and on the console nobody reads it.
; Saturates at 255.
.proc count_lost
.a8
.i16
    lda boot_frames
    sec
    sbc nmi_seen
    dec a                       ; the vblank that was this iteration's due
    beq up_to_date
    clc
    adc lost_frames
    bcc fits
    lda #255
fits:
    sta lost_frames
up_to_date:
    lda boot_frames
    sta nmi_seen
    rts
.endproc

; It is over: something that cannot happen happened. A carries the code, which
; stays in `panic` so that a state test can say which one it was.
;
; There is no `printf` on a SNES and returning from here makes no sense —the
; state is already inconsistent—, so what is left is to make it visible: the
; screen flashes between black and full forever. It is ugly on purpose. What
; we want to avoid is the opposite, the game carrying on as if nothing
; happened and the error showing up half an hour later turned into something
; else.
.proc enter_panic
.a8
.i16
    sta panic
    sei                         ; not even the vblank: nothing else is going to happen
loop:
    ldx #$2000
wait_on:
    dex
    bne wait_on
    lda #$0F
    sta INIDISP
    ldx #$2000
wait_off:
    dex
    bne wait_off
    lda #$80
    sta INIDISP
    bra loop
.endproc

; --- waiting for vblank -----------------------------------------------------
; With NMI disabled, the HVBJOY flag is checked: first that it leaves the
; previous vblank and then that it enters the next one.
; The NMI: adds a frame and clears the flag. It touches nothing else, and
; leaves P as it was because `rti` pulls it from the stack. It runs during
; boot, so that boot always lasts the same, and afterwards too: see
; `count_lost`.
.proc nmi_boot
    sep #$20
.a8
    pha
    ; **The data bank, set here and not inherited.** `boot_frames` and
    ; `RDNMI` are read with absolute addressing, so they go to whatever data
    ; bank the code the NMI interrupted had. Save and load run with the bank
    ; in SRAM, and an NMI landing there added one to `$70:1C07` —byte 769 of
    ; the fourth slot— instead of to `boot_frames`: the checksum stopped
    ; matching and slot 4 loaded as empty. The other three do not go through
    ; that address, which is why only one failed. `phk` gives bank 0, because
    ; the vectors run there, and bank 0 has low WRAM and the registers.
    phb
    phk
    plb
    inc boot_frames
    lda RDNMI
    plb
    pla
    rti
.endproc

.proc wait_vblank
.a8
.i16
out:
    lda HVBJOY
    bmi out
in:
    ; The wait is when a screen's text gets typeset: see `tl_idle`. It
    ; stops on its own before the vblank.
    lda tl_on
    beq spin
    jsl f:tl_idle + FAST
spin:
    lda HVBJOY
    bpl in
    rts
.endproc

; --- PPU reset --------------------------------------------------------------
; The emulator boots with all registers at zero. The real console does not:
; it keeps whatever the previous program left, which on an EverDrive is its
; menu. If that menu left color math, the sub-screen, a window or an HDMA
; channel on, all of that keeps working under our map even though we did not
; ask for it.
;
; That is why writing the registers we use is not enough: all of them have
; to be written.
.proc ppu_reset
.a8
.i16
    lda #$80
    sta INIDISP                 ; forced blanking before touching anything

    ; The first thing is to cut per-scanline DMA: if a channel was left
    ; active, it keeps writing PPU registers on every line and nothing we do
    ; here holds.
    stz HDMAEN
    stz MDMAEN
    stz NMITIMEN

    ; The PPU registers to known values, in two stretches: the scroll ones sit
    ; in the middle and need different handling.
    ldx #$0000
low:
    lda f:ppu_low, x
    sta $2101, x
    inx
    cpx #(ppu_low_end - ppu_low)
    bne low

    ldx #$0000
high:
    lda f:ppu_high, x
    sta $2115, x
    inx
    cpx #(ppu_high_end - ppu_high)
    bne high

    ; The eight scroll registers: each one is written twice, low byte and
    ; high byte, or the latch is left half done.
    ldx #$0000
scrolls:
    stz $210D, x
    stz $210D, x
    inx
    cpx #8
    bne scrolls

    ; All of VRAM to zero, by DMA with the source fixed on a null byte.
    ; Without this the menu's tiles stay wherever ours do not reach.
    lda #$80
    sta VMAIN
    ldx #$0000
    stx VMADDL
    ldx #.loword(zero)
    stx A1T0L
    lda #^zero
    sta A1B0
    ldx #$0000                  ; 0 means 65536: the whole VRAM
    stx DAS0L
    lda #$09                    ; two registers, word at a time, fixed source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; And CGRAM, which otherwise leaves the menu's palette in the colors we
    ; do not use.
    stz CGADD
    ldx #.loword(zero)
    stx A1T0L
    lda #^zero
    sta A1B0
    ldx #512
    stx DAS0L
    lda #$08                    ; one register, byte at a time, fixed source
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; From $2101 to $210C: objects, mode, mosaic and where each layer lives. All
; at zero, which is "nothing on".
.segment "TABLES"

; What **has** to live in bank 0: it is read with `lda table, y`, and the
; 65816 has no absolute long indexed by Y —`long,X` yes, `long,Y` no—, or
; with so many different indices that the extra byte per access would cost
; more than the table. The ones read with X and rarely read were moved down
; to RODATA over the course of 2026-09-13, in three separate rounds and for
; the same reason: making room. `bank1.s` has the reason for each one and
; what could still be moved down.

; `jump_per_speed` moved down to RODATA on 2026-09-14: a single access, and
; going through X costs four bytes against the table's six. See `bank1.s`.
; Every how many frames the walk frame changes, per speed: walking and
; standing with continuous animation: `GetStationaryAnimFrames` and
; `GetContinuousAnimFrames` of `Game_Character::UpdateAnimation`.
anim_idle:
    .byte 12, 10, 8, 6, 5, 4
anim_continues:
    .byte 16, 12, 10, 8, 7, 6


.segment "CODE"

; --- the PPU ----------------------------------------------------------------
; Mode 3: BG1 with 8 bits per pixel. There each pixel is a direct index into
; CGRAM and there is no per-tile palette, so the map fits with its 60 colors
; without merging any. It costs twice the VRAM per tile and there is room to
; spare anyway.
.proc ppu_init
.a8
.i16
    lda #$03
    sta BGMODE
    ; BG2SC carries the tilemap address in the high byte and the size in the
    ; two low bits; with VRAM_ABOVE_MAP at $7800 and size 1 —two 32x32 screens
    ; side by side, that is 64x32— it comes to $79.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC                   ; the upper layer's window
    ; BG12NBA and BG1SC come from the map, so enter_map sets them —and
    ; `back_to_map`—. Here they would keep the previous map's value as soon
    ; as there is more than one: the background's tilemap is not in the same
    ; place in every layout, see LAYOUT_VENTANA_AMBOS.
    stz BG1HOFS                 ; the scroll takes two writes, low byte
    stz BG1HOFS                 ; and high byte
    ; The PPU shows line vofs+1 on the first visible scanline, not vofs. With
    ; 0 the map ends up shifted one line up; with -1 it falls in place. The
    ; pixel-by-pixel comparison against the Python render uncovered it: by eye
    ; the two images looked identical.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$13
    sta TM                      ; the map's two layers and the sprites
    ; And mode 1 with BG3, if the map's panorama goes there: see pano.s.
    jsl f:pano_ppu
    rts
.endproc
