.segment "FAR"

; --- the battle scene --------------------------------------------------------
;
; The battle background with the monsters on top: a single 8bpp layer of
; 256x128 on BG1, which is the seven text lines at the top. **It is composed
; here, when the battle starts**, from a background and the troop's
; battlers, which the cartridge carries once each. The why, the format and
; the budget are in tools/port/scene.py.
;
; It runs from `battle_run` with the data bank at $7E, so the PPU
; registers and the cartridge's tables all go with `f:`, and the state here
; is named with a sixteen-bit address, like `FAR_BATTLE`.
;
; **$7E6600 to $7E67FF belongs to this**: the range was reserved in advance
; on 2026-09-21, when splitting work among tasks that touched far RAM.
SCN_ORIGIN   = $6600    ; 1: a random encounter started the battle
; The number of this battle's background among the game's, or BACKDROP_PLAIN.
; It is the one read from the `.msu`; the ROM's is SCN_FALLBACK. See "Qué
; fondos hay" in tools/port/scene.py.
SCN_BACKDROP    = $6601
SCN_VIS      = $6602    ; one bit per enemy: still drawn
SCN_PAL_N    = $6603    ; how many battler palettes were handed out
SCN_PAL_BAT  = $6604    ; 8 bytes: which battler each one holds
SCN_E_BAT    = $6610    ; 8 bytes: each enemy's battler, or $FF
SCN_E_PAL    = $6618    ; 8 bytes: its palette, 0 to 7
SCN_E_X      = $6620    ; 8 bytes: its corner in the scene
SCN_E_Y      = $6628
; What is left to upload to VRAM of an enemy that was just erased: whole tile
; rows of the scene, `SCN_SUB_BUDGET` bytes per vblank.
SCN_SUB_N    = $6630    ; word: how many tile rows are left; 0 is none
SCN_SUB_ROW = $6632    ; word: the next one
SCN_SUB_COL  = $6634    ; word: the first tile column
SCN_SUB_LENGTH = $6636   ; word: how many bytes each row is
; How many frames composing took, counted with `boot_frames`: the ROM does
; not read it; the tests read it, and so does whoever wants to measure it with
; the emulator.
SCN_FRAMES  = $6638
SCN_T0       = $663A    ; scratch
SCN_E        = $663C    ; the enemy being placed or erased
SCN_I        = $663D
; The rectangle a battler is clipped to when placed: pixel rows [Y0, Y1)
; and tile columns [C0, C1) of the scene, in words.
SCN_CLIP_Y0  = $6640
SCN_CLIP_Y1  = $6642
SCN_CLIP_C0  = $6644
SCN_CLIP_C1  = $6646
; Where the walk is in the drawing order, and where the troop starts in the
; `miembro_*` tables. See `scn_by_command`.
SCN_K        = $6648
SCN_INIT      = $6649
; 1 if this battle's background comes from the MSU-1 and not from the
; cartridge: see `scn_fill`. The tests read it too, to know which path
; ran.
SCN_MSU      = $664A
; Which of the ROM's backgrounds is drawn without MSU-1: SCN_BACKDROP's if the
; cartridge carries it, the replacement if not. Only valid with SCN_BACKDROP
; set.
SCN_FALLBACK = $664B
; What was on the direct page that gets borrowed: see `scn_dp_take`.
SCN_DP_SAVE = $6680
SCN_DP_BYTES = 48

; The clean background and the composed scene, 32 KB each, in WRAM bank
; $7F, which nobody used: everything else in the ROM lives in $7E —far RAM
; goes up to $7E67FF— and no `WMADDH` is written with anything but zero. The
; clean one is what lets an enemy be erased without reading anything from
; the cartridge again: see `scene_tick`.
SCN_CLEAN   = $7F0000
SCN_SCENE   = $7F8000
; How many scene bytes are uploaded per vblank when an enemy is erased. The
; NTSC vblank allows about six kilobytes of DMA and `scr_upload` already
; takes the text's 1,792 in the same vblank; two more leave some margin.
SCN_SUB_BUDGET = 2048

; --- the borrowed direct page ---
;
; The `scene_set` loop reads the battler with `[puntero], y` —its bank
; changes with each battler— and that only exists with the direct page. The
; game's is full, so a page of `pal_buf`, which the battle does not use, is
; borrowed, and what it held **is saved and restored**: the battle does not
; touch it, but coming back from it with the flash half built has no reason
; to find it overwritten. Neither the NMI nor `irq_music` read `pal_buf`,
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
ED_COUNT = $26
ED_ROWS = $28
ED_YY  = $2A    ; the scene's pixel row
ED_STEP = $2C   ; how long one row of a plane is
ED_N   = $2E    ; how many columns the battler has
; And those of `scn_double`, which runs before anybody is placed.
ED_FONT = $00 ; the 24-bit pointer to the fallback, which advances
ED_WORDS = $04 ; how many two-plane words of the tile pair are left

.proc scn_dp_take
.a8
.i16
    rep #$20
.a16
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tax
    ldy #0
saves:
    lda a:$0000, x              ; low RAM: in bank $7E it is the same
    sta SCN_DP_SAVE, y
    inx
    inx
    iny
    iny
    cpy #SCN_DP_BYTES
    bcc saves
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tcd
    sep #$20
.a8
    rts
.endproc

.proc scn_dp_return
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
restores:
    lda SCN_DP_SAVE, y
    sta a:$0000, x
    inx
    inx
    iny
    iny
    cpy #SCN_DP_BYTES
    bcc restores
    sep #$20
.a8
    rts
.endproc

; --- placing a battler ---
;
; The inner loop, once for each shift: a battler that does not start on a
; tile edge is shifted `RUNS` bits to the right, and the `lsr`s are unrolled
; because they are half the cost. Per tile column and pixel row: five reads
; from the battler —the mask and four planes—, each one sixteen bits to also
; bring in the column to the left, and four words of the scene, which are
; the tile's eight planes in pairs. A column with nothing of the battler is
; skipped entirely.
;
; With 16-bit A, X and Y: X is the offset in the scene and Y in the
; battler. See `scene_set`, which is the one that sets all this up.
.macro SCN_LOOP RUNS
.local row, col, empty, other_tile, set2
row:
    ldx ED_FX
    ldy ED_FY
    lda ED_COLS
    sta ED_COUNT
col:
    lda [ED_M], y
    .repeat RUNS
    lsr a
    .endrepeat
    and #$00FF
    beq empty
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
    .repeat RUNS
    lsr a
    .endrepeat
    sta ED_T0
    lda [ED_P1], y
    .repeat RUNS
    lsr a
    .endrepeat
    sta ED_T1
    lda [ED_P2], y
    .repeat RUNS
    lsr a
    .endrepeat
    sta ED_T2
    lda [ED_P3], y
    .repeat RUNS
    lsr a
    .endrepeat
    sta ED_T3
    ; background AND NOT mask OR battler, on the drawing's planes
    lda f:SCN_SCENE, x
    and ED_NM
    ora ED_T0
    sta f:SCN_SCENE, x
    lda f:SCN_SCENE + 16, x
    and ED_NM
    ora ED_T2
    sta f:SCN_SCENE + 16, x
    ; and on the palette's, which are the mask or nothing:
    ; ((background ^ palette) & mask) ^ background
    lda f:SCN_SCENE + 32, x
    eor ED_P45
    and ED_MM
    eor f:SCN_SCENE + 32, x
    sta f:SCN_SCENE + 32, x
    lda f:SCN_SCENE + 48, x
    eor ED_P67
    and ED_MM
    eor f:SCN_SCENE + 48, x
    sta f:SCN_SCENE + 48, x
empty:
    dey                         ; the column to the right: see `battler_bytes`
    txa
    clc
    adc #64                     ; the next tile
    tax
    dec ED_COUNT
    beq :+
    jmp col                     ; with seven `lsr`s the body does not fit in a `bne`
:
    ; The next row: in the battler, the length of one row of a plane; in the
    ; scene, two bytes, unless it moves to another tile row.
    lda ED_FY
    clc
    adc ED_STEP
    sta ED_FY
    lda ED_YY
    and #7
    cmp #7
    beq other_tile
    lda ED_FX
    inc a
    inc a
    bra set2
other_tile:
    lda ED_FX
    clc
    adc #(SCENE_COLUMNS * 64 - 14)
set2:
    sta ED_FX
    inc ED_YY
    dec ED_ROWS
    beq :+
    jmp row
:   rts
.endmacro

.a16
.i16
scn_loop_0: SCN_LOOP 0
scn_loop_1: SCN_LOOP 1
scn_loop_2: SCN_LOOP 2
scn_loop_3: SCN_LOOP 3
scn_loop_4: SCN_LOOP 4
scn_loop_5: SCN_LOOP 5
scn_loop_6: SCN_LOOP 6
scn_loop_7: SCN_LOOP 7
scn_loops:
    .addr scn_loop_0, scn_loop_1, scn_loop_2, scn_loop_3
    .addr scn_loop_4, scn_loop_5, scn_loop_6, scn_loop_7
; Each enemy's bit in `SCN_VIS`.
scn_bits:
    .byte $01, $02, $04, $08, $10, $20, $40, $80
.a8

; `SCN_E` = the enemy that comes `SCN_K`-th in the drawing order, which is
; RM2k's and not the troop's: easyrpg's `Sprite_Battler::ResetZ` sorts by
; the battler's bottom edge, and with equal edges the one with the lower
; place ends up on top. The converter computes the order: `member_command`.
; It clobbers X.
.proc scn_by_command
.a8
.i16
    rep #$20
.a16
    lda SCN_K
    clc
    adc SCN_INIT
    and #$00FF
    tax
    sep #$20
.a8
    lda f:member_command, x
    sta SCN_E
    rts
.endproc

; A8: `SCN_E`'s bit in `SCN_VIS`. It clobbers X.
.proc scn_bit
.a8
.i16
    rep #$20
.a16
    lda SCN_E
    and #$00FF
    tax
    sep #$20
.a8
    lda f:scn_bits, x
    rts
.endproc

; Enemy `SCN_E` onto the scene in `SCN_SCENE`, clipped to `ESC_CLIP_*`.
; With the direct page already borrowed. If it has no battler, or if the
; clip leaves it out, it does nothing.
.proc scene_set
.a8
.i16
    rep #$20
.a16
    lda SCN_E
    and #$00FF
    tax
    sep #$20
.a8
    lda SCN_E_BAT, x
    cmp #$FF
    bne has
    rts
has:
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
    lda f:battler_plane, x
    sta SCN_T0
    lda ED_M
    clc
    adc SCN_T0
    sta ED_P0
    adc SCN_T0                  ; there is no carry: the battler does not cross a bank
    sta ED_P1
    adc SCN_T0
    sta ED_P2
    adc SCN_T0
    sta ED_P3
    tyx
    lda f:battler_n, x
    and #$00FF
    sta ED_N
    inc a
    sta ED_STEP
    lda f:battler_height, x
    and #$00FF
    sta ED_ROWS                ; not clipped yet

    ; --- the palette: planes 4 to 7 of each battler pixel ---
    lda SCN_E
    and #$00FF
    tax
    lda SCN_E_PAL, x
    and #$0007
    sta SCN_T0
    lda #0
    lsr SCN_T0
    bcc :+
    ora #$00FF                  ; bit 0 is plane 4
:   lsr SCN_T0
    bcc :+
    ora #$FF00                  ; bit 1, plane 5
:   sta ED_P45
    lda #$FF00                  ; plane 7 is palette 8 onward
    lsr SCN_T0
    bcc :+
    ora #$00FF                  ; and bit 2, plane 6
:   sta ED_P67

    ; --- the columns: how many, from which, and how far the clip allows ---
    lda SCN_E_X, x
    and #$00FF
    sta SCN_T0
    and #7
    sta ED_COUNT               ; the shift, borrowed for a moment
    lda ED_N
    ldy ED_COUNT
    beq :+
    inc a                       ; shifted, it takes one more column
:   sta ED_COLS
    lda SCN_T0
    lsr a
    lsr a
    lsr a
    sta SCN_T0                  ; the battler's first tile column
    ; The right one, capped at the clip and at the scene's edge.
    clc
    adc ED_COLS
    cmp SCN_CLIP_C1
    bcc :+
    lda SCN_CLIP_C1
:   sta ED_COLS                 ; now it is the final column, not how many
    ; The left one: the battler's or the clip's.
    lda SCN_T0
    cmp SCN_CLIP_C0
    bcs :+
    lda SCN_CLIP_C0
:   sta ED_FX                   ; the first column touched, borrowed
    lda ED_COLS
    sec
    sbc ED_FX
    bcs :+
    jmp outside
:   bne :+
    jmp outside
:   sta ED_COLS                 ; how many
    ; The battler column it starts at, which is the one that gives Y.
    lda ED_FX
    sec
    sbc SCN_T0
    sta SCN_T0                  ; battler columns that are skipped
    lda ED_N
    sec
    sbc SCN_T0
    sta ED_FY                   ; its place in the row: see `battler_bytes`

    ; --- the rows ---
    lda SCN_E_Y, x
    and #$00FF
    sta ED_YY
    clc
    adc ED_ROWS
    cmp SCN_CLIP_Y1
    bcc :+
    lda SCN_CLIP_Y1
:   sta ED_ROWS                ; the final row
    lda ED_YY
    cmp SCN_CLIP_Y0
    bcs :+
    lda SCN_CLIP_Y0
:   sta SCN_T0                  ; the first one
    lda ED_ROWS
    sec
    sbc SCN_T0
    bcs :+
    jmp outside
:   bne :+
    jmp outside
:   sta ED_ROWS
    ; The battler rows that are skipped, times the length of each.
    lda SCN_T0
    sec
    sbc ED_YY
    tay
    lda SCN_T0
    sta ED_YY
    lda ED_FY
jumps_row:
    cpy #0
    beq rows_lists
    clc
    adc ED_STEP
    dey
    bra jumps_row
rows_lists:
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
    lda SCN_E
    and #$00FF
    tay
    lda SCN_E_X, y
    and #7
    asl a
    tax
    jsr (scn_loops, x)
    sep #$20
.a8
    rts
outside:
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
; distinct battler. Leaves in `BA_SCENE` a 0 if there is something to show
; and $FF if not.
.proc scene_upload
.a8
.i16
    lda f:boot_frames
    sta SCN_FRAMES
    lda #0
    sta SCN_FRAMES + 1
    sta SCN_VIS
    sta SCN_PAL_N
    rep #$20
.a16
    lda #0
    sta SCN_SUB_N
    sep #$20
.a8

    ; --- which background: the map's if it was an encounter, the troop's if not ---
    ;
    ; And the map's can be that of the terrain the hero stands on, just as a
    ; troop can fight with the place's: it is `Game_Map::SetupBattle`. See
    ; `escena_de_la_rom` in tools/port/snes_convert.py.
    lda #BACKDROP_PLAIN
    sta SCN_BACKDROP
    lda SCN_ORIGIN
    beq from_troop
from_place:
    rep #$20
.a16
    lda map_current
    tax
    sep #$20
.a8
    lda f:scene_map_backdrop, x
    cmp #PLACE_BACKDROP
    bne backdrop_chosen
    jsr scn_terrain             ; the terrain under the hero, in A
    cmp #BACKDROP_TERRAINS
    bcs no_backdrop
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:backdrop_terrain, x
    bra backdrop_chosen
from_troop:
    lda BA_TROOP_K
    cmp #$FF
    beq no_backdrop
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:scene_troop_backdrop, x
    cmp #PLACE_BACKDROP
    beq from_place
backdrop_chosen:
    cmp #BACKDROPS_GAME
    bcs no_backdrop               ; BACKDROP_PLAIN, or a cartridge with no backgrounds
    sta SCN_BACKDROP
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:backdrop_fallback, x     ; its own if the ROM carries it, or the replacement
    sta SCN_FALLBACK
no_backdrop:
    lda #0
    sta SCN_ORIGIN              ; only `encounter_test` sets it

    ; --- the troop's battlers, and one palette for each distinct one ---
    lda #0
    sta SCN_E
    lda BA_TROOP_K
    cmp #$FF
    bne with_troop
    jmp allocated
with_troop:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:troop_init, x
    sta SCN_I                   ; the first member
    sta SCN_INIT                 ; and again, for `scn_by_command`
other_enemy:
    lda SCN_E
    cmp BA_KID
    bcc :+
    jmp allocated
:   rep #$20
.a16
    lda SCN_E
    and #$00FF
    tay                         ; Y: the enemy
    clc
    adc SCN_I
    and #$00FF
    tax                         ; X: the member
    sep #$20
.a8
    lda f:member_x, x
    sta SCN_E_X, y
    lda f:member_y, x
    sta SCN_E_Y, y
    lda f:member_battler, x
    sta SCN_E_BAT, y
    cmp #$FF
    beq next
    ; Does that battler already have a palette? The limit, as a word for `cpx`.
    pha
    rep #$20
.a16
    lda SCN_PAL_N
    and #$00FF
    sta SCN_T0
    sep #$20
.a8
    pla
    ldx #0
seek_pal:
    cpx SCN_T0
    beq pal_new
    cmp SCN_PAL_BAT, x
    beq pal_list
    inx
    bra seek_pal
pal_new:
    sta SCN_PAL_BAT, x
    inc SCN_PAL_N
pal_list:
    txa
    sta SCN_E_PAL, y
    ; And the drawn bit, which is what `scene_tick` looks at. A hidden one
    ; is not drawn: it gets its palette, and `scene_tick` places it when it
    ; appears.
    lda SCN_E
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HIDDEN
    bne next
    jsr scn_bit
    ora SCN_VIS
    sta SCN_VIS
next:
    inc SCN_E
    jmp other_enemy
allocated:
    lda SCN_BACKDROP
    cmp #$FF
    bne has_scene
    lda SCN_VIS
    bne has_scene
    jmp no_scene              ; neither background nor battlers: on black, as before
has_scene:
    lda #0
    sta BA_SCENE

    ; --- where the background comes from: the MSU-1 if present and it is this cartridge's ---
    sta SCN_MSU
    lda SCN_BACKDROP
    cmp #$FF
    beq no_msu                 ; the plain one is not read from anywhere
    jsr msu_data_valid
    sta SCN_MSU
no_msu:

    ; --- the background: its colors and both buffers ---
    lda SCN_MSU
    pha
    jsr scn_backdrop
    ; If it started from the `.msu` and some seek did not make it in time,
    ; what was already read from there is the high-quality background and
    ; what follows the light one: they share neither colors nor tiles.
    ; Everything again from the ROM, which does not fail.
    pla
    cmp #0                      ; `pla` leaves Z from what it pulled, not from SCN_MSU
    beq backdrop_ready
    lda SCN_MSU
    bne backdrop_ready
    jsr scn_backdrop
backdrop_ready:

    ; --- the battlers, in drawing order: the later one covers ---
    rep #$20
.a16
    lda #0
    sta SCN_CLIP_Y0
    sta SCN_CLIP_C0
    lda #SCENE_HEIGHT
    sta SCN_CLIP_Y1
    lda #SCENE_COLUMNS
    sta SCN_CLIP_C1
    sep #$20
.a8
    jsr scn_dp_take
    lda #0
    sta SCN_K
put:
    lda SCN_K
    cmp BA_KID
    bcs set3
    jsr scn_by_command
    jsr scn_bit                 ; only the visible ones: not a hidden one
    and SCN_VIS
    beq :+
    jsr scene_set
:   inc SCN_K
    bra put
set3:
    jsr scn_dp_return

    ; --- the composed scene, to VRAM ---
    lda #$80
    sta f:VMAIN                 ; one word per write
    rep #$20
.a16
    lda #SCENE_VRAM
    sta f:VMADDL
    lda #.loword(SCN_SCENE)
    sta f:A1T0L
    lda #(SCENE_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^SCN_SCENE
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
    lda #.loword(scene_zero)
    sta f:A1T0L
    sep #$20
.a8
    lda #^scene_zero
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
    lda #SCENE_MAP
    sta f:VMADDL
    lda #0
    sta SCN_T0                  ; the tile that goes in the cell
    ldx #0
cell:
    cpx #SCENE_TILES
    bcc cell_scene
    lda #SCENE_TARGET
    bra cell_sets
cell_scene:
.a16
    lda SCN_T0
cell_sets:
.a16
    sta f:VMDATAL
    inc SCN_T0
    inx
    cpx #(32 * 32)
    bcc cell
    sep #$20
.a8

    ; --- and a sixteen-color palette per battler, from 8 on ---
colors_battlers:
    lda #0
    sta SCN_I
other_palette:
    lda SCN_I
    cmp SCN_PAL_N
    bcs ready
    asl a
    asl a
    asl a
    asl a
    clc
    adc #(SCENE_BAT_PALETTE * 16)
    sta f:CGADD
    rep #$20
.a16
    lda SCN_I
    and #$00FF
    tax
    lda SCN_PAL_BAT, x
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
    jsr scn_dma_cgram
    inc SCN_I
    bra other_palette
ready:
    lda f:boot_frames
    sec
    sbc SCN_FRAMES
    sta SCN_FRAMES
    rts
no_scene:
.a8
    lda #$FF
    sta BA_SCENE
    rts
.endproc

; The terrain of the cell the hero is on, in A: what `StoreTerrainID` would
; answer —see `op_terrain`, which is where this comes from—, for the
; background of a battle on a map that does not name its own. It runs when
; the battle starts, before `scn_fill` overwrites the upper half of $7F,
; which may belong to the grid. `cell_replaced` is in bank 0, so its
; lookup is copied here.
.proc scn_terrain
.a8
.i16
    ldx map_ofs
    lda f:map_table + M_TERRAIN_PLANE, x
    bne ready                   ; a single terrain on the whole map
    rep #$20
.a16
    lda [hero_ptr]              ; which block the hero's cell is
    ldy sub_n
    beq replaced
seek:
    dey
    dey
    cmp sub_key, y
    beq found
    cpy #$0000
    bne seek
    bra replaced
found:
    lda sub_value, y
replaced:
    sta SCN_T0
    lda f:map_table + M_PTR_BLOCK_TERRAIN, x
    sta cells_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_BLOCK_TERRAIN + 2, x
    sta cells_ptr + 2
    ldy SCN_T0
    lda [cells_ptr], y
ready:
    rts
.endproc

; The background of `SCN_BACKDROP`, from wherever `SCN_MSU` says: its colors
; and both buffers. If a `.msu` seek does not make it in time, it leaves
; SCN_MSU at 0 and goes on from the ROM: see who calls it.
;
; From the ROM, `scn_fill` leaves only the fixed planes in both buffers,
; and `scn_double` enlarges the fallback into both at once. If the first came
; from the `.msu` and the second did not, `scn_double` overwrites the bottom
; half of every tile of the first; it does not matter, because
; `scene_upload` redoes everything from the ROM.
.proc scn_backdrop
.a8
.i16
    jsr scn_colors
    lda #0
    jsr scn_fill
    lda #$80
    jsr scn_fill
    lda SCN_MSU
    bne ready
    lda SCN_BACKDROP
    cmp #$FF
    beq ready                   ; the plain one is already there: it is zeros
    jsl f:scn_double + FAST   ; from the fast mirror: see MEMSEL
ready:
    rts
.endproc

; The background's colors, from entry SCENE_CGRAM: the high-quality one's
; 96 if it comes from the `.msu`, the light one's 16 if it comes from the
; ROM. Nothing with the plain one.
.proc scn_colors
.a8
.i16
    lda SCN_BACKDROP
    cmp #$FF
    bne has
    rts
has:
    lda #SCENE_CGRAM
    sta f:CGADD
    lda SCN_MSU
    beq from_rom
    ; From the `.msu`: its color entry is the background's second one.
    rep #$20
.a16
    lda SCN_BACKDROP
    and #$00FF
    asl a
    asl a
    asl a                       ; times 8: two 32-bit positions
    tax
    lda f:msu_backdrop_pos + 6, x
    tay
    lda f:msu_backdrop_pos + 4, x
    jsr msu_data_seek
.a8
    bcs no_found
    rep #$20
.a16
    lda #(SCENE_COLORS * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #$22                    ; CGDATA
    jmp scn_dma_msu
no_found:
    lda #0
    sta SCN_MSU
from_rom:
    rep #$20
.a16
    lda SCN_FALLBACK
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32, which is FALLBACK_COLORS * 2
    .assert FALLBACK_COLORS * 2 = 32, error, "backdrop_cgram changed its stride"
    clc
    adc #.loword(backdrop_cgram)
    sta f:A1T0L
    lda #(FALLBACK_COLORS * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #^backdrop_cgram
    jmp scn_dma_cgram
.endproc

; The DMA to CGRAM with source and length already set: A the source bank.
.proc scn_dma_cgram
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
.proc scn_dma_msu
.a8
.i16
    sta f:BBAD0
    rep #$20
.a16
    lda #MSU_DATA
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

; One of the scene's two buffers, with `SCN_BACKDROP`'s background or with
; zeros: A is the middle byte of its address, 0 the clean one and $80 the
; composed one. Through the WRAM window, which is the only way to copy from
; ROM to RAM by DMA; the bank is $7F, so WMADDH is 1.
.proc scn_fill
.a8
.i16
    sta f:WMADDM
    sta SCN_T0 + 1              ; and again, for the ROM path
    lda #0
    sta SCN_T0
    sta f:WMADDL
    lda #1
    sta f:WMADDH
    lda #$80                    ; WMDATA
    sta f:BBAD0
    lda SCN_BACKDROP
    cmp #$FF
    bne with_backdrop
    ; The plain background: the same zero 32,768 times, with the source fixed.
    rep #$20
.a16
    lda #.loword(scene_zero)
    sta f:A1T0L
    lda #(SCENE_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^scene_zero
    sta f:A1B0
    lda #$08
    sta f:DMAP0
    lda #$01
    sta f:MDMAEN
    rts
with_backdrop:
    lda SCN_MSU
    beq from_rom
    ; From the `.msu`, the 32 KB at once: the start of the tiles is sought
    ; every time, because the stream already advanced to the end with the
    ; previous buffer. Copying from one buffer to the other cannot be done
    ; by DMA —WRAM to WRAM does not work— and with `mvn` it would be several
    ; frames.
    rep #$20
.a16
    lda SCN_BACKDROP
    and #$00FF
    asl a
    asl a
    asl a                       ; times 8: two 32-bit positions
    tax
    lda f:msu_backdrop_pos + 2, x
    tay
    lda f:msu_backdrop_pos, x
    jsr msu_data_seek
.a8
    bcs no_found
    rep #$20
.a16
    lda #(SCENE_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #$80                    ; WMDATA
    jmp scn_dma_msu
no_found:
    ; The MSU-1 did not finish seeking in time: this buffer comes from the
    ; ROM, and `scene_upload` redoes the rest from there.
    lda #0
    sta SCN_MSU
from_rom:
    ; From the ROM, only planes 4 to 7 go here, which are the same on every
    ; pixel of the fallback: the 32 bytes of `fallback_height` in the top half
    ; of every tile, rewinding the source and moving WMADD on each one.
    ; `scn_double` fills the bottom half afterwards. See "El respaldo
    ; liviano" in tools/port/scene.py.
    lda #0
    sta f:DMAP7                 ; one byte at a time, the source advancing
    lda #$80                    ; WMDATA
    sta f:BBAD7
    lda #^fallback_height
    sta f:A1B7
    rep #$20
.a16
    lda SCN_T0
    clc
    adc #FALLBACK_TILE          ; the top half of the first tile
    tax
    ldy #SCENE_TILES
tile:
    txa
    sta f:WMADDL                ; and WMADDM; WMADDH stays at $7F
    lda #(64 - FALLBACK_TILE)
    sta f:DAS7L
    lda #.loword(fallback_height)
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

; The fallback of `SCN_FALLBACK`, enlarged to double size in both buffers:
; the bottom half of every tile, which is its planes 0 to 3. `scn_fill`
; already put the top ones there.
;
; It is CPU and not DMA because each small pixel is two across, and in
; planar that means splitting every byte in two: `fallback_double` does it, a
; table of 256 words. `respaldo_bytes`, in tools/port/snes_convert.py,
; leaves the bytes in the order they are read here, so the ROM only moves
; forward: for each pair of neighboring scene tiles —the left and right ones
; that come from the same row of a small tile—, eight two-plane words, each
; written on two rows —the small row, doubled vertically— and into both
; buffers.
;
; It is entered with `jsl` through the fast mirror, and runs with the data
; bank at $7F, so the buffers go with `a:`.
.proc scn_double
.a8
.i16
    jsr scn_dp_take
    lda SCN_FALLBACK
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; times 4: the row of `backdrop_dir`
    tax
    lda f:backdrop_dir, x
    sta ED_FONT
    sep #$20
.a8
    lda f:backdrop_dir + 2, x
    ora #^FAST                ; the fallback, through the fast mirror
    sta ED_FONT + 2
    phb
    lda #^SCN_CLEAN
    pha
    plb
    .assert ^SCN_SCENE = ^SCN_CLEAN, error, "the scene buffers changed bank"
    .assert FALLBACK_SCALE = 2, error, "scn_double only enlarges to double size"
    rep #$20
.a16
    ldy #0                      ; the pair's left tile, in the buffers
pair:
    lda #8
    sta ED_WORDS
word:
    ; The front byte gives the left tile's row; the back one, the right
    ; one's. Each, through the table, is the whole two-plane word.
    lda [ED_FONT]
    and #$00FF
    asl a
    tax
    lda f:fallback_double + FAST, x
    sta a:.loword(SCN_CLEAN), y
    sta a:.loword(SCN_CLEAN) + 2, y
    sta a:.loword(SCN_SCENE), y
    sta a:.loword(SCN_SCENE) + 2, y
    lda [ED_FONT]
    xba
    and #$00FF
    asl a
    tax
    lda f:fallback_double + FAST, x
    sta a:.loword(SCN_CLEAN) + 64, y
    sta a:.loword(SCN_CLEAN) + 66, y
    sta a:.loword(SCN_SCENE) + 64, y
    sta a:.loword(SCN_SCENE) + 66, y
    ; The fallback does not cross a bank —it is a `.block`—, so the low
    ; sixteen bits are enough.
    inc ED_FONT
    inc ED_FONT
    ; The next two rows: four bytes further on. Those of planes 2/3 start at
    ; 16, which is exactly where the fourth of 0/1 ends.
    iny
    iny
    iny
    iny
    dec ED_WORDS
    bne word
    ; The next pair: the 128 bytes of the two tiles, minus the 32 already
    ; advanced.
    tya
    clc
    adc #(128 - 32)
    tay
    cpy #(SCENE_TILES * 64)
    bcc pair
    sep #$20
.a8
    plb
    jsr scn_dp_return
    rtl
.endproc

; --- erasing a dead enemy, and placing one that appears ---
;
; Once per frame, from the battle loop and **inside the vblank**, right after
; `ba_t_upload`. If rows of a just-erased enemy were left un-uploaded, it
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
.proc scene_tick
.a8
.i16
    lda BA_SCENE
    cmp #$FF
    bne has
    rts
has:
    rep #$20
.a16
    lda SCN_SUB_N
    beq seek
    jmp upload
seek:
    sep #$20
.a8
    lda #0
    sta SCN_E
other:
    lda SCN_E
    cmp BA_KID
    bcc :+
    rts
:   ; Is it drawn?
    jsr scn_bit
    sta SCN_T0
    and SCN_VIS
    beq no_drawn
    ; And dead?
    lda SCN_E
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq erase
next:
    inc SCN_E
    bra other
no_drawn:
    ; And is it in the battle? It is one that was hidden and
    ; `ShowHiddenMonster` brought out: it is placed the same way one is
    ; erased, with its cells redone from the clean background and the
    ; visible ones on top in drawing order, and it among them. One with no
    ; battler has nothing to place.
    rep #$20
.a16
    lda SCN_E
    and #$00FF
    tax
    sep #$20
.a8
    lda SCN_E_BAT, x
    cmp #$FF
    beq next
    lda SCN_E
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    beq next
    lda SCN_T0
    ora SCN_VIS
    sta SCN_VIS
    bra repaint

erase:
    lda SCN_T0
    eor #$FF
    and SCN_VIS
    sta SCN_VIS
repaint:
    ; The rectangle, in tiles: the columns it touches and the whole rows.
    rep #$20
.a16
    lda SCN_E
    and #$00FF
    tax
    lda SCN_E_BAT, x
    and #$00FF
    tay
    lda SCN_E_X, x
    and #$00FF
    sta SCN_T0
    lsr a
    lsr a
    lsr a
    sta SCN_CLIP_C0
    sta SCN_SUB_COL
    tyx
    lda f:battler_n, x
    and #$00FF
    sta SCN_CLIP_C1             ; while we are at it
    lda SCN_T0
    and #7
    beq :+
    inc SCN_CLIP_C1             ; shifted, it takes one more
:   lda SCN_CLIP_C1
    clc
    adc SCN_CLIP_C0
    cmp #SCENE_COLUMNS
    bcc :+
    lda #SCENE_COLUMNS
:   sta SCN_CLIP_C1
    sec
    sbc SCN_CLIP_C0
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta SCN_SUB_LENGTH           ; bytes per tile row
    lda f:battler_height, x
    and #$00FF
    sta SCN_T0
    lda SCN_E
    and #$00FF
    tax
    lda SCN_E_Y, x
    and #$00FF
    pha
    and #$00F8
    sta SCN_CLIP_Y0             ; from the first row of its first tile
    lsr a
    lsr a
    lsr a
    sta SCN_SUB_ROW
    pla
    clc
    adc SCN_T0
    clc
    adc #7
    and #$00F8
    sta SCN_CLIP_Y1             ; to the last row of its last tile
    sec
    sbc SCN_CLIP_Y0
    lsr a
    lsr a
    lsr a
    sta SCN_SUB_N

    ; --- the cells, from the clean background ---
    ; Tile row by tile row with `mvn`, which copies inside bank $7F and
    ; leaves the data bank there: it is saved and restored.
    lda SCN_SUB_ROW
    sta SCN_T0
    lda SCN_SUB_N
    sta SCN_I                   ; and SCN_I + 1: used as a word here
copy:
    lda SCN_T0
    xba                         ; row * 256...
    lsr a
    lsr a
    lsr a                       ; ...over eight: row * 32 tiles
    clc
    adc SCN_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 64 bytes
    tax
    clc
    adc #.loword(SCN_SCENE)
    tay
    lda SCN_SUB_LENGTH
    dec a                       ; `mvn` copies A + 1
    phb
    mvn #^SCN_CLEAN, #^SCN_SCENE
    plb
    inc SCN_T0
    dec SCN_I
    bne copy

    ; --- and the ones still alive on top, clipped to those cells ---
    sep #$20
.a8
    lda SCN_E
    pha
    jsr scn_dp_take
    lda #0
    sta SCN_K
restore:
    lda SCN_K
    cmp BA_KID
    bcs restored
    jsr scn_by_command
    jsr scn_bit
    and SCN_VIS
    beq :+
    jsr scene_set
:   inc SCN_K
    bra restore
restored:
    jsr scn_dp_return
    pla
    sta SCN_E
    rts

    ; --- upload what fits in this vblank ---
upload:
.a16
    lda #0
    sta SCN_T0                  ; how many bytes so far
row:
    lda SCN_T0
    clc
    adc SCN_SUB_LENGTH
    cmp #(SCN_SUB_BUDGET + 1)
    bcc :+
    lda SCN_T0
    bne ready                   ; one was already uploaded and the next does not fit
    lda SCN_SUB_LENGTH
:   sta SCN_T0
    ; The tile row: `(row * 32 + column)` tiles from the base.
    lda SCN_SUB_ROW
    xba
    lsr a
    lsr a
    lsr a
    clc
    adc SCN_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 words
    pha
    clc
    adc #SCENE_VRAM
    sta f:VMADDL
    pla
    asl a                       ; times 64 bytes
    clc
    adc #.loword(SCN_SCENE)
    sta f:A1T0L
    lda SCN_SUB_LENGTH
    sta f:DAS0L
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #^SCN_SCENE
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    inc SCN_SUB_ROW
    dec SCN_SUB_N
    bne row
ready:
    sep #$20
.a8
    rts
.endproc

; BG1 with the scene, after `slot_ppu_on` has set up BG2 and turned
; the screen on. If this battle has no scene it touches nothing and the
; screen stays on black, as before 2026-09-13.
.proc scene_on
.a8
.i16
    lda BA_SCENE
    cmp #$FF
    beq ready
    lda #((SCENE_MAP / 1024) * 4)
    sta f:BG1SC                 ; 32x32, which is what covers the whole screen
    lda #((SLOT_VRAM / 4096) * 16 + (SCENE_VRAM / 4096))
    sta f:BG12NBA               ; the text on BG2 and the scene on BG1
    lda #0
    sta f:BG1HOFS               ; `stz` has no long mode
    sta f:BG1HOFS
    lda #$FF
    sta f:BG1VOFS               ; the PPU shows vofs+1: with -1 it lands in place
    sta f:BG1VOFS
    lda #$03
    sta f:TM                    ; BG1 and BG2
ready:
    rts
.endproc

; When returning to the map, the upper eight palettes from `cgram_shadow`,
; before anything else: the battlers took them, and what the map restores by
; itself is only its objects' ones —`SPRITE_CGRAM` colors— and the timer's.
; The banner and the battle animation upload their palette only when it
; changes, so without this they would come back with a battler's colors.
; With the screen off: `back_from_battle`, in bank 0, calls it with the
; data bank at 0.
.proc scene_cgram_restore
.a8
.i16
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_shadow + 2 * 128)
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

