.segment "FAR3"
.a8
.i16

; --- what the terrain does to whoever steps on it --------------------------
;
; A terrain of the database says more than its battle backdrop. Of that,
; what lives here is its `damage`: easyrpg's `Game_Player::Move`, which after
; `Game_Character::Move` has moved the hero onto the next cell takes the
; terrain of **that** cell and, if it hurts, takes `damage` HP from each
; actor in the party and flashes the screen red. So it is the moment the
; step **begins**, not when it ends, and every step of the hero counts: the
; pad's and a forced move route's, because the route calls the same `Move`.
; A blocked step does not get here. Not in the airship, which the console
; does not have.
;
; Who is hurt and how much is `Game_Battler::ChangeHp` with `lethal` false,
; which is `actor_change_one` in level.s: a fallen actor does not change,
; nobody goes below 1 HP and a negative damage heals up to the maximum.
; **It never kills**, so there is no Game Over here: EasyRPG's
; `easyrpg_damage_can_kill` would, and no game sets it. An actor wearing an
; armor with `no_terrain_damage` is spared —`PreventsTerrainDamage`, which
; walks only the armors: the converter sets `ITEM_USE_NO_TERRAIN_DAMAGE` in
; `item_use` only for them—, and only from a positive damage.
;
; The flash is `FlashMapStepDamage`, `FlashOnce(31, 10, 10, 20, 6)`, and it
; goes if the damage is positive and someone in the party was not spared,
; fallen or not: in easyrpg `red_flash` is set before `ChangeHp`, which is
; what does nothing to a fallen one.
;
; Poison hurts at the same moment in RM2k —`Game_Party::ApplyStateDamage`,
; after `IncSteps`, only for the pad's steps— and with the same flash: when
; the party holds conditions, that is `flash_step_damage` and
; `actor_change_one` again, not this routine, which is the terrain's.
;
; The 2003 sounds —the terrain's footstep and `on_damage_se`— are not here:
; they need the sample in the map's audio package.

; The hero has just begun a step onto the cell `hero_ptr` points at:
; `begin_step` comes here with `jsl`. Keeps X and Y; clobbers A, `temp` and
; `cells_ptr`, which nobody holds across a step —`advance_step` clobbers the
; first and its callers are done with the second—. While the party is
; walked, `cells_ptr` is two flags: someone was hurt, so it flashes; and the
; damage is negative, so nobody is spared.
.proc terrain_step
.a8
.i16
    phx
    phy
    phb
    lda #$7E                    ; `sub_key` and the party read from any bank
    pha                         ; with low RAM; $7E is the one this is sure of
    plb
    jsl f:hero_terrain
    cmp #TERRAINS_N
    bcs done                    ; a terrain the database does not have
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    ldy #0
    sty cells_ptr               ; both flags down
    lda f:terrain_damage, x
    beq done_16                 ; the usual case: it hurts nobody
    bpl hurts
    inc cells_ptr + 1           ; it heals: a word, 0 to 1, in A16
hurts:
    eor #$FFFF
    inc a
    sta temp                    ; the change `actor_change_one` adds
    sep #$20
.a8
    ldx #0
slot:
    cpx party_n
    bcs walked
    phx
    lda party, x
    pha
    lda cells_ptr + 1
    bne change                  ; healing spares nobody, and does not flash
    lda 1, s
    jsr spared
    bcs next
    lda #1
    sta cells_ptr               ; it flashes even if this one has fallen
change:
    stz temp + 3                ; `what` of `actor_change_one`: the HP, not lethal
    lda 1, s
    jsl f:actor_change_one_l
next:
    pla
    plx
    inx
    bra slot
walked:
    lda cells_ptr
    beq done
    jsr flash_step_damage
done:
    plb
    ply
    plx
    rtl
done_16:
    sep #$20
.a8
    bra done
.endproc

; `FlashMapStepDamage`: red, strength 20 of 31, six frames, which is even as
; `flash_tick` wants it —see `ANIM_FLASH_FRAMES` in the event compiler—.
.proc flash_step_damage
.a8
.i16
    lda #31
    sta flash_rgb
    lda #10
    sta flash_rgb + 1
    sta flash_rgb + 2
    lda #20                     ; the level, on a 256 scale: its high byte
    sta flash_level + 1
    stz flash_level
    lda #6
    sta flash_remain
    rts
.endproc

; Whether actor A wears an armor that spares it a terrain's damage: C=1 if
; so. Its five slots of `FAR_EQUIPMENT`, each looked up in `item_use` by its
; `k`. Clobbers A, X, Y and `temp + 2`.
.proc spared
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; ten times the actor: its five words
    tax
    ldy #5
slot:
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x
    beq next
    cmp #ITEMS_N
    bcs next
    phx
    asl a
    tax
    lda f:item_k, x
    tax
    inc a
    beq none                    ; $FFFF: the cartridge does not carry it
    lda f:item_use, x
    and #ITEM_USE_NO_TERRAIN_DAMAGE
    beq none
    plx
    sep #$20
.a8
    sec
    rts
.a16
none:
    plx
next:
    inx
    inx
    dey
    bne slot
    sep #$20
.a8
    clc
    rts
.endproc

; The terrain of the cell the hero is on, in A8: what `StoreTerrainID` would
; answer for it —see `op_terrain`, which is where this comes from—. The
; terrain of the lower layer's tile, which the converter put into the
; block's key: one byte per block, or `M_TERRAIN_PLANE` for a map with a
; single one. `cell_replaced` is in bank 0, so its lookup is copied here.
; Entered with `jsl` and with the data bank on low RAM; clobbers X, Y and
; `cells_ptr`. The battle asks it too, for a backdrop of the place: see
; `scn_terrain`.
.proc hero_terrain
.a8
.i16
    ldx map_ofs
    lda f:map_table + M_TERRAIN_PLANE, x
    bne ready                   ; a single terrain on the whole map
    rep #$20
.a16
    lda [hero_ptr]              ; which block the hero's cell is
    and cell_mask
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
    tay
    lda f:map_table + M_PTR_BLOCK_TERRAIN, x
    sta cells_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_BLOCK_TERRAIN + 2, x
    sta cells_ptr + 2
    lda [cells_ptr], y
ready:
    rtl
.endproc

; --- a character half hidden in a bush ---------------------------------------
;
; A terrain's `bush_depth` draws the lower part of the character standing on
; it half transparent: easyrpg's `Sprite_Character::Draw`, `GetHeight() /
; (4 - depth)` rows from the feet —10 of 32 with 1, 16 with 2, all of them
; with 3— at half the opacity, from the cell the character **is** on, which
; changes as the step begins. Not while jumping, nor for a character on
; another layer than the hero's.
;
; The console mixes half and half with its color math, which only touches
; objects in palettes 4 to 7, so the hero's lower rows go as objects of
; their own in front of it: 8x8 ones —the map's small size— over the same
; tiles, in a palette of 4 to 7 that holds a copy of the hero's. They are
; the last tile row, 8 rows, for depth 1 —RM2k's 10 is not a tile
; boundary—, the last two for depth 2, and the whole object in the copy for
; 3. Four objects per row, since the 24 columns of a CharSet frame fall on
; the four of the 32 object. Against what is under it: the subscreen is
; the map's two layers, as for the translucent pictures —`pic_blend`—, so
; an event behind the hero does not show through.
;
; **Only the hero**: an event standing in a bush is drawn whole. And only
; when nothing else needs palettes 4 to 7 or the color math: the map's
; characters fit in 0 to 3, no picture is up and no battle animation is
; drawn. A palette of 4 to 7 the timer, the rain or the window's objects
; take is skipped.

; This frame's bush, for the vblank: the palette the pieces went in, or 0,
; and the hero's, whose colours it gets. `build_oam` clears the first.
.pushseg
.segment "FARBSS"
far_bush: .res 2
.popseg
BUSH_SLOT = far_bush
BUSH_FROM = far_bush + 1

; From `place_hero`, right before its object: `obj_x`, `obj_y`, `obj_tile`
; and `obj_attr` are the hero's, and `obj_big` is 32x32. The pieces go into
; OAM first, so they are in front of it. Keeps X and Y; clobbers `temp`
; and `cells_ptr`, which `hero_terrain` uses.
.proc bush_oam
.a8
.i16
    phx
    phy
    lda route_jump
    bne none                    ; jumping: `GetBushDepth` is 0
    lda pic_last
    bne none                    ; a picture is in 4 to 7, and opaque ones too
    lda f:ANIMB_ACTIVE
    bne none                    ; the battle animation's box is in 4 or 5
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_SPRITE_CGRAM, x
    cmp #(4 * 16 + 1)
    sep #$20
.a8
    bcs none                    ; characters in 4 to 7 would be mixed too
    jsl f:hero_terrain
    cmp #TERRAINS_N
    bcs none
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:terrain_bush, x
    beq none
    sta temp + 2                ; the depth
    jsr bush_slot
    bcc none
    sta f:BUSH_SLOT
    asl a
    sta temp + 3                ; the slot, where `vhoopppN` has it
    lda obj_attr
    and #$0E
    lsr a
    sta f:BUSH_FROM
    lda temp + 2
    cmp #3
    bcc pieces
    ; Three or more: the whole object, in the copy.
    lda obj_attr
    and #$F1
    ora temp + 3
    sta obj_attr
    bra done
none:
    lda #0
    sta f:BUSH_SLOT
done:
    ply
    plx
    rtl
pieces:
    lda obj_attr
    pha                         ; the hero's, for its own object
    and #$F1
    ora temp + 3
    sta obj_attr
    stz obj_big                 ; 8x8
    rep #$20
.a16
    lda obj_x
    pha
    lda obj_y
    pha
    sep #$20
.a8
    ; Tile row 3, the feet, and row 2 too with depth 2.
    lda #3
    sec
    sbc temp + 2
    inc a                       ; 3 with depth 1, 2 with depth 2
    sta temp + 2                ; the row
row:
    lda #0
    sta temp + 3                ; the column
column:
    lda temp + 2
    asl a
    asl a
    asl a
    asl a
    ora temp + 3
    sta obj_tile                ; the 32 object's tile 16 * row + column
    rep #$20
.a16
    lda temp + 3
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc 3, s                    ; the hero's X
    sta obj_x
    lda temp + 2
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc 1, s                    ; the hero's Y
    sta obj_y
    sep #$20
.a8
    jsl f:emit_object_far + FAST
    lda temp + 3
    inc a
    sta temp + 3
    cmp #4
    bcc column
    lda temp + 2
    inc a
    sta temp + 2
    cmp #4
    bcc row
    rep #$20
.a16
    pla
    sta obj_y
    pla
    sta obj_x
    sep #$20
.a8
    stz obj_tile
    lda #2
    sta obj_big                 ; 32x32 again
    pla
    sta obj_attr
    bra done
.endproc

; The palette of 4 to 7 the pieces go in: the first one that neither the
; timer, nor the rain, nor the window's objects —its arrow and the inn's
; gold— take on this map. C=1 and A the palette, or C=0 if all four are
; taken. Clobbers X.
.proc bush_slot
.a8
.i16
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:arrow_objs, x         ; `vhoopppN` in its high byte, or 0
    xba
    sep #$20
.a8
    and #$0E
    lsr a
    sta temp + 3
    ldx map_ofs
    lda #4
try:
    cmp f:map_table + M_TIMER_PAL, x
    beq taken
    cmp f:map_table + M_RAIN_PAL, x
    beq taken
    cmp temp + 3
    bne free
taken:
    inc a
    cmp #8
    bcc try
    clc
    rts
free:
    sec
    rts
.endproc

; From `pic_blend`, in the vblank, when no picture mixes: the color math the
; bush asks for —the same as a translucent picture's— and the hero's colours
; as they are on screen, under a flash or a tint, into its palette; or no
; color math at all. Entered with `jsl` and with a data bank where the
; registers are.
.proc bush_blend
.a8
.i16
    lda f:BUSH_SLOT
    bne mixes
    lda #$30                    ; color math off, as `ppu_reset` leaves it
    sta CGWSEL
    stz CGADSUB
    stz TS
    rtl
mixes:
    asl a
    asl a
    asl a
    asl a
    ora #128
    sta CGADD                   ; the slot's first entry
    lda f:BUSH_FROM
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    adc #128                    ; the hero's first entry; the carry is clear
    asl a                       ; in bytes
    ldx flash_level
    bne flashing
    adc #.loword(cgram_shadow)
    bra source
flashing:
    adc #.loword(pal_buf)
source:
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; both buffers live in bank 0
    stz DMAP0
    lda #$22
    sta BBAD0                   ; CGDATA
    lda #$01
    sta MDMAEN
    lda #$02                    ; CGWSEL: add the subscreen, always
    sta CGWSEL
    lda #$50                    ; CGADSUB: add, halved, on the objects
    sta CGADSUB
    lda #$03                    ; TS: the map's two layers under them
    sta TS
    rtl
.endproc
