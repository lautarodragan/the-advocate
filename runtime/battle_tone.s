.segment "FAR2"

; --- the flash and the tint, in the battle scene ------------------------------
;
; `FlashScreen` and `TintScreen` belong to `Game_Screen` and not to the map, so
; in RM2k a troop page's go to the battle: `Spriteset_Battle` gives the
; screen's tone to the background and the battlers, and its `Screen` draws
; the flash on top of them, under the windows —`Priority_Screen` against
; `Priority_Window`—. The opcodes are the map's, `OP_FLASH_SCREEN` and
; `OP_TINT`, and they only leave the state —`flash_level`, `flash_remain`,
; `flash_rgb`, the tint and `tint_pending`—: on the map `flash_tick` and
; `apply_tint` draw it, from the main loop, which does not run while the
; battle lasts. This is the battle's, from its own loop.
;
; It is the map's same transform of the palette, over the scene's: the
; background's colours, from `SCENE_CGRAM`, and the battlers', from
; `SCENE_BAT_PALETTE`, which are BG1's and nobody else's. The windows' four
; colours, above them, and the text's, below, are left alone, as RM2k leaves
; the windows. Each colour is tinted and then flashed —the tint's tables
; composed with the flash's, the same as `flash_backdrop` runs the flash over
; the already tinted shadow— into `pal_buf`, which the battle does not use,
; and `ba_tone_upload` takes it to CGRAM in the next vblank.
;
; The sources: the background's colours are read back from CGRAM when the
; scene is up —they may have come from the `.msu`, which cannot be read again
; every frame—, and the battlers' are read from the cartridge, which is where
; `scene_upload` took them from.
;
; **And the scene starts with the tint the map had**, as in RM2k: the
; agency captain's battle (troop 240) is fought after a `TintScreen` to black,
; and its turn 0 page puts it back to neutral. A map flash that was still
; going does not carry on: the battle's entry has its own two.

.pushseg
.segment "FARBSS"
ba_bg_src:     .res SCENE_COLORS * 2  ; the background's colours, as uploaded
ba_tone_ready: .res 1                 ; `pal_buf` has a palette to upload
ba_tone_tint:  .res 1                 ; the tint changed: its tables are stale
.popseg

.assert SCENE_CGRAM + SCENE_COLORS = SCENE_BAT_PALETTE * 16, error, "the background's colours and the battlers' are not one stretch"
.assert table_g = table_r + 32 && table_b = table_g + 32, error, "the tint's tables are not contiguous"
.assert flash_tab_g = flash_tab_r + 32 && flash_tab_b = flash_tab_g + 32, error, "the flash's tables are not contiguous"

; Before anything of the battle runs: a flash the map left going stops here,
; and the battle does not take it back to the map either —see `close` in
; `battle_run`—.
.proc ba_tone_clear
.a8
.i16
    rep #$20
.a16
    stz flash_level
    sep #$20
.a8
    stz flash_remain
    rts
.endproc

; With the screen off, the scene and the windows uploaded and the turn 0 pages
; already run: the background's colours read back, and the scene with the
; tint —and the flash, if a page started one— right away.
.proc ba_tone_start
.a8
.i16
    lda #SCENE_CGRAM
    sta f:CGADD
    rep #$20
.a16
    lda #.loword(ba_bg_src)
    sta f:A1T0L
    lda #(SCENE_COLORS * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #^ba_bg_src
    sta f:A1B0
    lda #$80                    ; from the B bus to the A bus
    sta f:DMAP0
    lda #$3B                    ; CGDATAREAD
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    stz tint_pending            ; this build already takes the tint
    lda #1
    sta f:ba_tone_tint
    jsr ba_tone_build
    lda #1
    sta f:ba_tone_ready
    jmp ba_tone_upload
.endproc

; In the vblank, before the text's upload: the palette the last tick built.
; From the background's first colour to the last battler's, in one DMA.
.proc ba_tone_upload
.a8
.i16
    lda f:ba_tone_ready
    bne has
    rts
has:
    lda #0
    sta f:ba_tone_ready
    lda #SCENE_CGRAM
    sta f:CGADD
    rep #$20
.a16
    lda SCN_PAL_N
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per battler palette
    clc
    adc #(SCENE_COLORS * 2)
    sta f:DAS0L
    lda #.loword(pal_buf + SCENE_CGRAM * 2)
    sta f:A1T0L
    sep #$20
.a8
    lda #0                      ; `pal_buf` is low RAM, seen from bank 0
    sta f:A1B0
    sta f:DMAP0
    lda #$22                    ; CGDATA
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rts
.endproc

; Once per frame, at the end of the frame's work —see `wait` in
; `battle_run`—: a tint a page asked for, and a frame of the flash, and if
; either changed something, the palette built for the next vblank.
;
; The flash's frame is `flash_tick`'s, the same count: the level, on a 256
; scale, drops by `level / frames_left` with the hardware's divider, and on
; the last frame it falls to zero and the scene is built once more without
; it.
.proc ba_tone_tick
.a8
.i16
    stz temp + 3                ; whether to build
    lda tint_pending
    beq no_tint
    stz tint_pending
    lda #1
    sta f:ba_tone_tint
    sta temp + 3
no_tint:
    rep #$20
.a16
    lda flash_level
    sep #$20
.a8
    beq maybe                   ; `sep` does not touch Z
    lda #1
    sta temp + 3
    lda flash_remain
    beq off
    rep #$20
.a16
    lda flash_level
    sta f:WRDIVL                ; the dividend, 16 bits
    sep #$20
.a8
    lda flash_remain
    sta f:WRDIVB                ; starts it: the quotient takes sixteen cycles
    dec flash_remain
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda flash_level
    sec
    sbc f:RDDIVL
    sta flash_level
    sep #$20
.a8
    lda flash_remain
    bne maybe
off:
    rep #$20
.a16
    stz flash_level
    sep #$20
.a8
    stz flash_remain
maybe:
    lda temp + 3
    beq ready
    jsr ba_tone_build
    lda #1
    sta f:ba_tone_ready
ready:
    rts
.endproc

; The scene's palette, tinted and flashed, into `pal_buf` at the entries it
; goes to. Clobbers `temp`, `BA_T*`, A, X and Y.
.proc ba_tone_build
.a8
.i16
    ; The tint's tables: built again if the tint changed, and if not taken
    ; back from `pure`, which keeps them without the flash.
    lda f:ba_tone_tint
    beq fresh
    lda #0
    sta f:ba_tone_tint
    jsl f:ba_t_tint_tables
    bra tables
fresh:
    jsl f:ba_t_tint_restore
tables:
    ; And with a flash, composed with its tables: each entry of the tint's
    ; goes through the flash's of its channel.
    rep #$20
.a16
    lda flash_level
    beq colors
    sep #$20
.a8
    jsl f:ba_t_flash_tables
    rep #$20
.a16
    ldx #0
compose:
    lda table_r, x
    and #$001F
    sta temp
    txa
    and #$0060                  ; which of the three channels
    ora temp
    tay
    sep #$20
.a8
    lda flash_tab_r, y
    sta table_r, x
    rep #$20
.a16
    inx
    cpx #96
    bne compose

colors:
    ; The background's colours: the ninety-six of the one from the `.msu`, or
    ; the fallback's sixteen. The rest of the stretch nothing draws with, and
    ; it goes up as it is: building it too was the first frame of the flash
    ; going past the frame, with the page's step in the same one.
    ldx #(FALLBACK_COLORS * 2)
    lda SCN_MSU
    and #$00FF
    beq counted
    ldx #(SCENE_COLORS * 2)
counted:
    stx BA_T0
    ldy #0
background:
    tyx
    lda f:ba_bg_src, x
    jsr tone_color
    sta pal_buf + SCENE_CGRAM * 2, y
    iny
    iny
    cpy BA_T0
    bne background
    ; And each battler palette that was handed out, from the cartridge.
    stz BA_T0                   ; the slot
slot:
    lda BA_T0
    sep #$20
.a8
    cmp SCN_PAL_N
    rep #$20
.a16
    bcs ready
    tax
    lda SCN_PAL_BAT, x
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per battler
    sta BA_T1                   ; where its colours are
    lda BA_T0
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc #.loword(pal_buf + SCENE_BAT_PALETTE * 16 * 2)
    sta BA_T2                   ; and where they go
    ldy #0
battler:
    phy
    ldx BA_T1
    lda f:battler_cgram, x
    jsr tone_color
    ldx BA_T2
    sta a:$0000, x              ; low RAM, which bank $7E also sees
    inx
    inx
    stx BA_T2
    ldx BA_T1
    inx
    inx
    stx BA_T1
    ply
    iny
    cpy #16
    bne battler
    inc BA_T0
    bra slot
ready:
    sep #$20
.a8
    rts
.endproc

; A sixteen-bit colour through the tables: A in, A out. Keeps Y; clobbers X
; and `temp`. With a saturation that is not neutral it goes through
; `saturate_color` first, which is `ToneBlit`'s order, as `build_palette`.
.proc tone_color
.a16
.i16
    sta temp
    sep #$20
.a8
    lda tint_s
    cmp #TINT_NEUTRAL
    rep #$20
.a16
    bne saturated               ; `rep` does not touch Z
    lda temp
    and #$001F                  ; the red
    tax
    lda table_r, x
    and #$001F
    sta temp + 2
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; the green
    tax
    lda table_g, x
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp + 2
    sta temp + 2
    lda temp
    xba
    lsr a
    lsr a
    and #$001F                  ; the blue, which was in bits 10 to 14
    tax
    lda table_b, x
    and #$001F
    xba
    asl a
    asl a
    ora temp + 2
    rts
saturated:
    lda temp
    and #$001F
    sta sat_r
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_g
    lda temp
    xba
    lsr a
    lsr a
    and #$001F
    sta sat_b
    phy
    sep #$20
.a8
    jsl f:ba_t_saturate
    rep #$20
.a16
    ply
    ldx sat_r
    lda table_r, x
    and #$001F
    sta temp + 2
    ldx sat_g
    lda table_g, x
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp + 2
    sta temp + 2
    ldx sat_b
    lda table_b, x
    and #$001F
    xba
    asl a
    asl a
    ora temp + 2
    rts
.endproc
