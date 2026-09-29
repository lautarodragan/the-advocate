.segment "FAR"

; --- random encounters, outside bank 0 ---------------------------------------
;
; What RM2k does, from `Game_Player::UpdateEncounterSteps`, `GetEncountersAt`
; and `PrepareEncounter`, and written the same way in `eventos.Encuentros`,
; which is what it is compared against:
;
;   * each hero step **with the pad** —a forced move route exits early, via
;     `IsMoveRouteOverwritten`— adds the terrain's `encounter_rate` and checks
;     whether an encounter came up;
;   * the chance is `pmod / encounter_steps`, with `pmod` a power of two that
;     grows as one walks without anything coming up;
;   * if one comes up, it stays pending and is collected the next frame, with
;     the hero already standing still: the map's troops and those of each area
;     covering his cell are gathered, and one is picked at random.
;
; **All the arithmetic is integer**, which is what the console can do: the
; converter precomputes `1 / encounter_steps` in 1/65536 —`enc_base`— and at
; which step each row of the table is crossed —`enc_threshold_n`—, so there is
; not a single division here. See `eventos.enc_base` and
; `eventos.enc_umbrales_de_paso`, which are the same arithmetic on the other
; side.
;
; It lives here and not in bank 0 because there were eighty-five bytes left
; there: all that remains on the other side are the four `jsl` and the bridge
; to the battle. **The data bank is $7E while this runs**, as in battle: that
; way the state at $3900 is read with absolute addressing and low RAM —`temp`,
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
    ldx map_current
    lda f:enc_map, x
    sta ENC_REG
    cmp #ENC_NONE
    beq sin_encuentros
    rep #$20
.a16
    and #$00FF
    pha
    ; The record's thresholds, into RAM: the seven bytes and the padding one.
    asl a
    asl a
    asl a
    tax
    ldy #0
copiar:
.a16
    lda f:enc_threshold_n, x
    sta ENC_THR, y
    inx
    inx
    iny
    iny
    cpy #ENC_STRIDE
    bcc copiar
    pla
    asl a
    tax
    lda f:enc_base, x
    bra con_base
sin_encuentros:
.a8
    rep #$20
.a16
    lda #0
con_base:
.a16
    sta ENC_BASE
    sep #$20
.a8
    ; And the running count at zero, as in every `MoveTo`: entering a map is
    ; one.
    stz ENC_N
    stz ENC_IDX
    stz ENC_ASKS
    plb
    ply
    plx
    rtl
.endproc

; `ChangeEncounterSteps`, the body of OP_ENCOUNTER_STEPS: the new `1 / steps`
; and the seven thresholds that come from the same steps, which the converter
; already computed —see `eventos.enc_base` and
; `eventos.enc_umbrales_de_paso`—. Zero turns them off, which is what Dalia's
; trip to Tasgarde asks for. It does not touch the distance walked: easyrpg's
; `SetEncounterSteps` does not either.
;
; On a map with no troops or areas it does nothing, which is what
; `eventos.Encuentros.poner_pasos` does: with no zones there is no encounter
; to turn on. Nor does it outlast the map, as in RM2k: `encounter_map` puts
; the map's back on each load.
;
; It is entered with `jsl` from the interpreter, with Y on the operand and the
; bytecode's data bank; it returns with Y past the ten bytes.
.proc encounter_steps
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda ENC_REG
    cmp #ENC_NONE
    beq saltear
    rep #$20
.a16
    lda [code_ptr], y
    sta ENC_BASE
    iny
    iny
    ldx #0
umbral:
.a16
    lda [code_ptr], y            ; two at a time: the seven and the padding
    sta ENC_THR, x
    iny
    iny
    inx
    inx
    cpx #ENC_STRIDE
    bcc umbral
    sep #$20
.a8
    plb
    rtl
saltear:
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
    stz ENC_N
    stz ENC_IDX
    stz ENC_ASKS
    plb
    rtl
.endproc

; One hero step. Enters and leaves with an 8-bit accumulator.
.proc encounter_step
.a8
.i16
    phx
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda ENC_BASE
    bne hay
    ; Off: `encounter_steps` at zero, or a map with no troops or areas.
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    bra end
hay:
.a16
    sep #$20
.a8
    lda ENC_N
    inc a
    beq sigue_arriba            ; 255 steps without an encounter: it does not wrap around
    sta ENC_N
sigue_arriba:
.a8
    ; The table row, which **never goes down**: it is the `last_encounter_idx`
    ; over there. X points at the next row's threshold, in `ENC_THR`.
    rep #$20
.a16
    lda ENC_IDX
    and #$00FF
    tax
    sep #$20
.a8
sube:
.a8
    lda ENC_IDX
    cmp #(ENC_ROWS - 1)
    bcs con_fila                ; the last row goes no higher
    lda ENC_N
    cmp ENC_THR, x              ; did it reach the next one's threshold?
    bcc con_fila
    inx
    lda ENC_IDX
    inc a
    sta ENC_IDX
    bra sube
con_fila:
.a8
    ; The random threshold: `base` shifted by the row's `pmod`. Rows 0 to 3
    ; are 1/16, 1/8, 1/4 and 1/2; rows 4 to 7 are 2, 4, 8 and 16.
    rep #$20
.a16
    lda ENC_IDX
    and #$00FF
    tax
    lda ENC_BASE
    cpx #4
    bcs a_la_izquierda
derecha:
.a16
    lsr a
    inx
    cpx #4
    bcc derecha
    bra con_umbral
a_la_izquierda:
.a16
    dex
    dex
    dex
izquierda:
.a16
    asl a
    bcs siempre                 ; went past 1: it is a certainty, like `PercentChance`
    dex
    bne izquierda
con_umbral:
.a16
    sta temp
    jsr enc_random
    cmp temp
    bcc salio
    sep #$20
.a8
    bra end
siempre:
.a16
salio:
.a16
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    lda #1
    sta ENC_ASKS
end:
.a8
    plb
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
    jmp no_hay
pending:
.a8
    stz ENC_ASKS
    lda ENC_REG
    cmp #ENC_NONE
    bne con_registro
    jmp no_hay
con_registro:
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
    bcs contadas
    jsr enc_covers
    bcc sin_tapar
    sep #$20
.a8
    lda f:enc_troop_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    sta comp_and
sin_tapar:
.a16
    inc temp
    bra count_up
contadas:
.a16
    lda comp_and
    bne hay_tropas
    sep #$20
.a8
    bra no_hay
hay_tropas:
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
divide:
.a16
    asl comp_or23
    rol comp_or23 + 2
    lda comp_or23 + 2
    cmp comp_and + 2
    bcc sin_restar
    sec
    sbc comp_and + 2
    sta comp_or23 + 2
sin_restar:
.a16
    dey
    bne divide
    lda comp_or23 + 2
    sta comp_and                ; how many to skip
    ; Second pass: the one whose turn it is.
    sep #$20
.a8
    jsr enc_zones
    rep #$20
.a16
elegir:
.a16
    lda temp
    cmp temp + 2
    bcs no_hay16                ; cannot happen: the total came from these zones
    jsr enc_covers
    bcc sigue_eligiendo
    sep #$20
.a8
    lda f:enc_troop_n, x
    rep #$20
.a16
    and #$00FF
    sta comp_or23
    lda comp_and
    cmp comp_or23
    bcc es_de_esta
    sec
    sbc comp_or23
    sta comp_and
sigue_eligiendo:
.a16
    inc temp
    bra elegir
es_de_esta:
.a16
    sep #$20
.a8
    lda f:enc_troop_init, x
    rep #$20
.a16
    and #$00FF
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
    bra end
no_hay16:
.a16
    sep #$20
.a8
no_hay:
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
    lda ENC_REG
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enc_zone_init, x
    rep #$20
.a16
    and #$00FF
    sta temp
    sta temp + 2
    sep #$20
.a8
    lda f:enc_zone_n, x
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
; set if so, and with X at the zone number, which is what the one-byte tables
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
    bcc afuera
    cmp f:enc_right, x
    bcs afuera
    lda tile_y
    cmp f:enc_arr, x
    bcc afuera
    cmp f:enc_down, x
    bcs afuera
    ldx temp
    sec
    rts
afuera:
.a16
    ldx temp
    clc
    rts
.endproc

; The encounters' xorshift step: the same as `random_next` and `ba_random`,
; on `ENC_RNG`, which has **its own seed**. Walking does not advance the
; map's randomness: a random `ControlVars` has to give the same result with
; and without encounters. It is `eventos.Encuentros._azar`.
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

