.segment "FAR"

; --- random encounters, outside bank 0 ---------------------------------------
;
; What RM2k does, from `Game_Player::UpdateEncounterSteps`, `GetEncountersAt`
; and `PrepareEncounter`, and written the same way in `events.Encounters`,
; which is what it is compared against:
;
;   * each hero step **with the pad** —a forced move route exits early, via
;     `IsMoveRouteOverwritten`— adds the `encounter_rate` of the terrain it
;     steps onto and checks whether an encounter came up;
;   * the chance is `pmod / encounter_steps * rate / 100`, with `pmod` a power
;     of two that grows as one walks without anything coming up; a terrain
;     worth 0 —Vampires Dawn's sea— never fights;
;   * if one comes up, it stays pending and is collected the next frame, with
;     the hero already standing still: the map's troops and those of each area
;     covering his cell are gathered, and one is picked at random.
;
; **All the arithmetic is integer**, which is what the console can do: the
; converter precomputes `1 / encounter_steps` in 1/65536 —`enc_base`—, at
; which accumulated rate each row of the table is crossed —`enc_threshold`—
; and each terrain's `rate / 100` in 1/256 —`terrain_encounter_factor`—, so
; there is not a single division here, and one multiplication per step. See
; `base`, `rate_thresholds`, `factor` and `chance` in
; `rm2k-snes/battle/src/encounters.rs`, which are the same arithmetic on the
; other side.
;
; It lives here and not in bank 0 because there were eighty-five bytes left
; there: all that remains on the other side are the four `jsl` and the bridge
; to the battle. **The data bank is $7E while this runs**, as in battle: that
; way its state in far RAM is read with absolute addressing and low RAM —`temp`,
; `tile_x`, `map_current`— is still read the same, because in bank $7E the
; addresses from $0000 to $1FFF **are** bank 0's.

; The seed for the encounters' randomness, at reset. It is a different one from
; the map's and from the battle's: see `enc_random`.
.proc encounter_boot
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda #ENC_SEED
    sta ENC_RNG
    sep #$20
.a8
    plb
    rtl
.endproc

; The current map's record, or that this map has no encounters.
.proc encounter_map
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:enc_map, x
    sta ENC_REG
    cmp #ENC_NONE
    beq no_encounters_16
    pha
    ; The record's thresholds, into RAM: the seven words and the padding one.
    asl a
    asl a
    asl a
    asl a
    tax
    ldy #0
copy:
.a16
    lda f:enc_threshold, x
    sta ENC_THR, y
    inx
    inx
    iny
    iny
    cpy #ENC_STRIDE
    bcc copy
    pla
    asl a
    tax
    lda f:enc_base, x
    bra with_base
no_encounters_16:
.a16
    lda #0
with_base:
.a16
    sta ENC_BASE
    sep #$20
.a8
    ; And the accumulated rate at zero, as in every `MoveTo`: entering a map
    ; is one.
    stz ENC_ACC
    stz ENC_ACC + 1
    stz ENC_IDX
    stz ENC_ASKS
    plb
    ply
    plx
    rtl
.endproc

; `ChangeEncounterSteps`, the body of OP_ENCOUNTER_STEPS: the new `1 / steps`
; and the seven thresholds that come from the same steps, which the converter
; already computed —see `base` and `rate_thresholds` in
; `rm2k-snes-battle`—. Zero turns them off, which is what Dalia's
; trip to Tasgarde asks for. It does not touch the distance walked: easyrpg's
; `SetEncounterSteps` does not either.
;
; On a map with no troops or areas it does nothing, which is what
; `events.Encounters.set_steps` does: with no zones there is no encounter
; to turn on. Nor does it outlast the map, as in RM2k: `encounter_map` puts
; the map's back on each load.
;
; It is entered with `jsl` from the interpreter, with Y on the operand and the
; bytecode's data bank; it returns with Y past the eighteen bytes.
.proc encounter_steps
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda ENC_REG + 1             ; see ENC_NONE: the high byte says it
    cmp #>ENC_NONE
    beq skip
    rep #$20
.a16
    lda [code_ptr], y
    sta ENC_BASE
    iny
    iny
    ldx #0
threshold:
.a16
    lda [code_ptr], y           ; two at a time: the seven and the padding
    sta ENC_THR, x
    iny
    iny
    inx
    inx
    cpx #ENC_STRIDE
    bcc threshold
    sep #$20
.a8
    plb
    rtl
skip:
.a8
    rep #$20
.a16
    tya
    clc
    adc #(2 + ENC_STRIDE)
    tay
    sep #$20
.a8
    plb
    rtl
.endproc

; The `SetTotalEncounterRate(0)` of `Game_Player::MoveTo`: a teleport —a door,
; a `Teleport`, a `ChangeEventLocation` on the hero— erases the distance
; walked. It does not touch `ENC_BASE`: the map may be the same one.
.proc encounter_move
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    stz ENC_ACC
    stz ENC_ACC + 1
    stz ENC_IDX
    stz ENC_ASKS
    plb
    rtl
.endproc

; One hero step, already begun: `hero_ptr` points at the cell it goes onto,
; whose terrain is the one `UpdateEncounterSteps` reads —`GetX`/`GetY` are
; the destination's there too—. Enters and leaves with an 8-bit
; accumulator; keeps X and Y. Clobbers `temp` and `cells_ptr`, as
; `hero_terrain` does: nobody holds them across a step.
.proc encounter_step
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda ENC_BASE
    bne has
    ; Off: `encounter_steps` at zero, or a map with no troops or areas.
    ; `SetTotalEncounterRate(0)`.
    stz ENC_ACC
    sep #$20
.a8
    stz ENC_IDX
done:
.a8
    plb
    ply
    plx
    rtl
has:
.a16
    sep #$20
.a8
    jsl f:hero_terrain
    cmp #TERRAINS_N
    bcs done                    ; easyrpg's "invalid terrain": no count, no roll
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:terrain_encounter_factor, x
    sta temp                    ; the multiplier, below
    ; `total_encounter_rate += encounter_rate`, saturating: the last row's
    ; threshold is at most $FFFF —see `STEPS_MAX`—, so past it nothing
    ; changes.
    lda f:terrain_encounter_rate, x
    clc
    adc ENC_ACC
    bcc added
    lda #$FFFF
added:
.a16
    sta ENC_ACC
    ; The table row, which **never goes down**: it is the `last_encounter_idx`
    ; over there. Y is the row and X points at the next row's threshold, a
    ; word in `ENC_THR`.
    lda ENC_IDX
    and #$00FF
    tay
    asl a
    tax
climb:
.a16
    cpy #(ENC_ROWS - 1)
    bcs with_row                ; the last row goes no higher
    lda ENC_ACC
    cmp ENC_THR, x              ; did it reach the next one's threshold?
    bcc with_row
    inx
    inx
    iny
    bra climb
with_row:
.a16
    tya
    sep #$20
.a8
    sta ENC_IDX
    rep #$20
.a16
    ; `base * factor`, thirty-two bits in `ENC_P`: shift and add, from the
    ; factor's top bit. Some five hundred cycles, once per step.
    stz ENC_P
    stz ENC_P + 2
    ldx #16
multiply:
.a16
    asl ENC_P
    rol ENC_P + 2
    asl temp
    bcc no_add
    lda ENC_P
    clc
    adc ENC_BASE
    sta ENC_P
    bcc no_add
    inc ENC_P + 2
no_add:
.a16
    dex
    bne multiply
    ; The row's `pmod`, a shift of the product: rows 0 to 3 are 1/16, 1/8,
    ; 1/4 and 1/2; rows 4 to 7 are 2, 4, 8 and 16.
    cpy #4
    bcs to_left
right:
.a16
    lsr ENC_P + 2
    ror ENC_P
    iny
    cpy #4
    bcc right
    bra shifted
to_left:
.a16
    dey
    dey
    dey
left:
.a16
    asl ENC_P
    rol ENC_P + 2
    bcs always                  ; past 1: a certainty, like `PercentChance`
    dey
    bne left
shifted:
.a16
    ; And the `/ 256` of the factor: the chance is bits 8 to 23 of the
    ; product, and anything above them is past 1 again.
    lda ENC_P + 2
    and #$FF00
    bne always
    lda ENC_P + 1
    sta temp
    jsr enc_random
    cmp temp
    bcc exited
    sep #$20
.a8
    bra end
always:
.a16
exited:
.a16
    stz ENC_ACC
    sep #$20
.a8
    stz ENC_IDX
    lda #1
    sta ENC_ASKS
end:
.a8
    plb
    ply
    plx
    rtl
.endproc

; Is there a pending encounter to fight here? Returns with 8-bit A: 1 if there
; is a battle, with the troop already set in `BA_TROOP`.
;
; It is `PrepareEncounter`: if no zone covers the cell, the pending one is
; consumed and nothing happens, which is what it does over there by returning
; `false`.
.proc encounter_test
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    lda ENC_ASKS
    bne pending
    jmp none
pending:
.a8
    stz ENC_ASKS
    lda ENC_REG + 1             ; see ENC_NONE: the high byte says it
    cmp #>ENC_NONE
    bne with_register
    jmp none
with_register:
.a8
    ; The map's range of zones: its own and one per area.
    jsr enc_zones
    ; First pass: how many troops cover the hero's cell.
    rep #$20
.a16
    lda #0
    sta comp_and
count_up:
.a16
    lda temp
    cmp temp + 2
    bcs counted
    jsr enc_covers
    bcc no_cover
    sep #$20
.a8
    lda f:enc_troop_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    sta comp_and
no_cover:
.a16
    inc temp
    bra count_up
counted:
.a16
    lda comp_and
    bne has_troops
    sep #$20
.a8
    bra none
has_troops:
.a16
    ; One at random, `Rand::GetRandomNumber(0, n - 1)`: the remainder of
    ; dividing the random number by how many there are. The division is the
    ; good old long division, by hand, because the 65816 does not divide and
    ; the battle's lives in another bank.
    sta comp_and + 2
    jsr enc_random
    sta comp_or23
    lda #0
    sta comp_or23 + 2
    ldy #16
divides:
.a16
    asl comp_or23
    rol comp_or23 + 2
    lda comp_or23 + 2
    cmp comp_and + 2
    bcc no_subtract
    sec
    sbc comp_and + 2
    sta comp_or23 + 2
no_subtract:
.a16
    dey
    bne divides
    lda comp_or23 + 2
    sta comp_and                ; how many to skip
    ; Second pass: the one whose turn it is.
    sep #$20
.a8
    jsr enc_zones
    rep #$20
.a16
pick:
.a16
    lda temp
    cmp temp + 2
    bcs no_has16                ; cannot happen: the total came from these zones
    jsr enc_covers
    bcc continues_picking
    sep #$20
.a8
    lda f:enc_troop_n, x
    rep #$20
.a16
    and #$00FF
    sta comp_or23
    lda comp_and
    cmp comp_or23
    bcc in_this_zone
    sec
    sbc comp_or23
    sta comp_and
continues_picking:
.a16
    inc temp
    bra pick
in_this_zone:
.a16
    sep #$20
.a8
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:enc_troop_init, x     ; a word: past 255 troops it is no byte
    clc
    adc comp_and
    asl a
    tax
    lda f:enc_troop, x
    sta BA_TROOP
    sep #$20
.a8
    lda #1
    sta SCN_ORIGIN              ; the battle background, the map's
    sta BA_CAN_FLEE             ; and it can be escaped from: `Game_Map::SetupBattle`
    bra end
no_has16:
.a16
    sep #$20
.a8
none:
.a8
    lda #0
end:
.a8
    plb
    ply
    plx
    rtl
.endproc

; From which zone to which zone the map's go: `temp` the first and `temp + 2`
; one past the last. Enters with an 8-bit accumulator and leaves the same.
.proc enc_zones
.a8
.i16
    rep #$20
.a16
    lda ENC_REG
    asl a
    tax
    lda f:enc_zone_init, x      ; a word: past 255 zones it is no byte
    sta temp
    sta temp + 2
    lda ENC_REG
    tax                         ; long indexing is X only: the byte table by the record
    sep #$20
.a8
    lda f:enc_zone_n, x         ; a byte: the zones one map has
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    rts
.endproc

; Does zone `temp` cover the cell the hero is standing on? Returns with carry
; set if so, and with X at the zone number, which is what the byte tables
; index by. The rectangle is **half-open** —`l <= x < r`—, which is what
; easyrpg's `Rect::IsOutOfBounds` says with the hero as a one-cell rectangle.
.proc enc_covers
.a16
.i16
    lda temp
    asl a
    tax
    lda tile_x
    cmp f:enc_left, x
    bcc outside
    cmp f:enc_right, x
    bcs outside
    lda tile_y
    cmp f:enc_arr, x
    bcc outside
    cmp f:enc_down, x
    bcs outside
    ldx temp
    sec
    rts
outside:
.a16
    ldx temp
    clc
    rts
.endproc

; The encounters' xorshift step: the same as `random_next` and `ba_random`,
; on `ENC_RNG`, which has **its own seed**. Walking does not advance the
; map's randomness: a random `ControlVars` has to give the same result with
; and without encounters. It is `events.Encounters._roll`.
.proc enc_random
.a16
.i16
    lda ENC_RNG
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor ENC_RNG
    sta ENC_RNG
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor ENC_RNG
    sta ENC_RNG
    xba
    and #$FF00
    eor ENC_RNG
    sta ENC_RNG
    rts
.endproc

