; --- the battle transition --------------------------------------------------
;
; A Blurred Line's database asks for, when a battle starts,
; `battle_start_fadeout = 16` and `battle_start_fadein = 17`, and when it ends
; `battle_end_fadeout = 17` and `battle_end_fadein = 16`. In the table of
; easyrpg-player's `Game_System::GetTransition`, 16 is `TransitionZoomIn`
; when erasing and `TransitionZoomOut` when showing, and 17 is
; `TransitionMosaicOut` and `TransitionMosaicIn`. That is: the map zooms in
; until it disappears, the battle appears out of a mosaic, the battle leaves
; in a mosaic, and the map comes back zooming out. Before all that, two white
; flashes of ten frames each: `Scene_Map::TransitionOut` always prepends them
; when entering a battle, with `PrependFlashes(31, 31, 31, 31, 10, 2)`.
;
; What is done here:
;
;   the flashes        with the fixed color added to the whole screen: color
;                      math, which the game uses for nothing else
;   the zoom           out of the map, entering, **as the mosaic of the way
;                      out**: taro's, on 2026-09-30, so that entering and
;                      leaving look the same. Until then it was a fade, which
;                      is what taro decided for the transitions the console
;                      does not do: zooming the map is mode 7, and the map is
;                      in mode 3. Sprites do not get pixelated, as in the
;                      teleport's mosaic. Coming back to the map, the zoom is
;                      still a fade
;   the mosaic         with the PPU's mosaic, which is exactly that, **and
;                      fading at the same time**. The battle is two
;                      backgrounds —BG1 the scene, BG2 the text— and on the
;                      way in and out there is no sprite, so the mosaic
;                      reaches everything.
;
; Fading the mosaic is not from RM2k —there the mosaic does not darken—, and
; it is on purpose: **the audio package load has to fall inside the black**.
; Uploading the battle's, or uploading the map's again, takes between half a
; second and a second and a half depending on the cartridge and the map, and
; without this the screen was seen frozen all that time. In RM2k loading is
; instant and there is nothing to cover. So each side goes down to black,
; loads, and only then the other one comes up: however long the load takes
; —with MSU-1 the song is not uploaded—, it stays inside.
;
; The ramps are the teleport's, `fade_ramp`: master brightness has
; sixteen steps, and the mosaic is tied to it —size 16 at brightness 0, size
; 1 at brightness 15—, which are also the sixteen sizes the PPU has. In RM2k
; the zoom and the mosaic last 41 frames; here each ramp lasts
; `FADE_RAMP` and the rest is the black of the load, which is always
; longer.
;
; All of this **blocks**, like the battle itself: `ticks` does not advance,
; so the transition costs no tick —see `test_la_pelea_no_gasta_ningun_tick`—.
; RM2k also freezes the scene while a transition lasts.

.segment "CODE"

; And the map coming back, from black, already restored by
; `back_from_battle`. With `flush_video` on every frame, like the main loop
; while a fade freezes it: the scroll, the OAM and the brightness are written
; there and only there —see the end of `flush_video`—. The OAM is built once
; before, because the one in the PPU is the battle's; it is the same thing
; `load_requested` does.
.proc battle_fade_to_map
.a8
.i16
    jsr build_oam_settled
    ; An event erased the screen before the battle: it stays black, as
    ; `Scene_Map::TransitionIn` leaves it with `screen_erased_by_event`.
    lda f:SCREEN_ERASED
    bne black
    ldx #0
upload:
    lda fade_ramp, x
    sta brightness
    phx
    jsr wait_vblank
    jsr flush_video
    plx
    inx
    cpx #FADE_RAMP
    bcc upload
black:
    rts                         ; and `brightness` is left at full, as it was,
                                ; or at zero if the screen is erased
.endproc

.segment "FAR"

; The ones that call nothing in bank 0 other than `wait_vblank`, through its
; bridge, live here: bank 0 has no room to spare. They do not depend on the
; data bank —the battle's runs with $7E—, so everything goes with `f:`.

; The two flashes and the map down to black, in a mosaic. From `battle_start`, with the
; map on screen. It leaves the screen on with brightness zero: the load that
; follows does not write VRAM.
.proc battle_fade_in
.a8
.i16
    ; Nothing has been turned on yet. It is cleared here and we do not trust
    ; the previous battle to have left it at zero: the first one finds the RAM
    ; as power-on left it, which on a console —and in bsnes— is garbage.
    lda #0
    sta f:BATTLE_ON
    ; Over a screen an event erased there is nothing to flash or to fade:
    ; RPG_RT only waits, `Scene_Map::TransitionOut`. The screen is already
    ; black, which is what the load that follows asks for.
    lda f:SCREEN_ERASED
    beq lit
    rtl
lit:
    ; The fixed color is added on every layer and on the backdrop. Sprites
    ; with palettes 0 to 3 get no color math —that is the hardware—, so the
    ; hero flashes less than the map.
    lda #0
    sta f:CGWSEL
    lda #$3F
    sta f:CGADSUB
    ldy #2                      ; two flashes, with the same curve
other_flash:
    ldx #0
flash:
    jsl f:ba_t_vblank           ; `wait_vblank`: touches neither X nor Y
    lda f:battle_flash, x
    sta f:COLDATA
    inx
    cpx #10
    bcc flash
    dey
    bne other_flash
    ; And the map down to black, in a mosaic: the same ramp as the battle's
    ; way out, `battle_fade_out`, frame by frame. The first frame turns off
    ; the flash, in the same vblank; the ramp starts one step below full so
    ; as not to spend a frame on the brightness that was already there.
    ldx #(FADE_RAMP - 2)
lower:
    jsl f:ba_t_vblank
    lda #$30
    sta f:CGWSEL                ; color math off, as `ppu_reset` leaves it
    lda #0
    sta f:CGADSUB
    lda #$E0
    sta f:COLDATA
    lda f:fade_ramp, x
    sta f:INIDISP
    eor #$0F                    ; the mosaic, tied to brightness: see above
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 and BG2: the map and the layer above
    sta f:MOSAIC
    dex
    bpl lower
    ; Already black. Turned off here and not left to the battle: one that
    ; never turns anything on —see `battle_fade_out`— goes back to the map
    ; without writing it.
    lda #0
    sta f:MOSAIC
    rtl
.endproc

; The intensity of the fixed color on each frame of a flash, with all three
; channels on. It is `Flash::Update`'s curve: the level starts at 31 and on
; each frame loses `level / frames_left`, that is 31 * (10 - k) / 10,
; truncated as easyrpg truncates it when making the color.
battle_flash:
    .byte $E0|31, $E0|27, $E0|24, $E0|21, $E0|18
    .byte $E0|15, $E0|12, $E0|9,  $E0|6,  $E0|3

; The battle down to black, in a mosaic. From `battle_start`, with the
; battle already over and still on screen. If the battle never turned
; anything on —a troop the cartridge does not carry, or a party with nobody
; standing, which loses without fighting— the screen is already black since
; `battle_fade_in` and there is nothing to turn off.
.proc battle_fade_out
.a8
.i16
    lda f:BATTLE_ON
    beq ready
    lda #0
    sta f:BATTLE_ON
    ldx #(FADE_RAMP - 2)
lower:
    jsl f:ba_t_vblank
    lda f:fade_ramp, x
    sta f:INIDISP
    eor #$0F                    ; the mosaic, tied to brightness: see above
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 and BG2
    sta f:MOSAIC
    dex
    bpl lower
    lda #0
    sta f:MOSAIC                ; already black: nobody else turns it off
ready:
    rtl
.endproc

; The battle from black, in a mosaic. From `battle_run`, with the scene
; already uploaded and the screen on at brightness zero.
.proc battle_fade_showing
.a8
.i16
    lda #1
    sta f:BATTLE_ON
    ldx #0
upload:
    jsl f:ba_t_vblank           ; `wait_vblank`, which does not touch X
    lda f:fade_ramp, x
    sta f:INIDISP
    eor #$0F
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 and BG2
    sta f:MOSAIC
    inx
    cpx #FADE_RAMP
    bcc upload
    lda #0
    sta f:MOSAIC                ; the last one was already size 1: same thing, off
    rtl
.endproc
