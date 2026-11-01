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
