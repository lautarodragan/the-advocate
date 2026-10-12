.segment "FAR2"

; The battle's xorshift, the same as `events.next_random` and
; `rain_random`, but on `BA_SEED`, which has **its own seed**: fighting does
; not advance the map's randomness, so a random `ControlVars` gives the same
; with a battle in between and without one.
.proc ba_random
.a16
.i16
    lda BA_SEED
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor BA_SEED
    sta BA_SEED
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor BA_SEED
    sta BA_SEED
    xba
    and #$FF00
    eor BA_SEED
    sta BA_SEED
    rts
.endproc

; `temp` divided by `temp + 2`: the quotient ends up in `temp` and the
; remainder in `comp_and`. Shift and subtract, sixteen passes.
;
; It exists because the hardware divider is **eight bits** and here there are
; two divisions that do not fit: the hit adjustment for agility divides by
; twice the agility —up to 600 in this game— and the damage variance, by the
; adjustment, which gets to the same. Doing them with the hardware divider
; meant truncating, and truncating changes the number: the two sides would no
; longer agree.
;
; **The divisor has to be less than 32768**: the remainder comes in through a
; `rol` and a larger one would overflow off the top. None of the ones used
; comes close.
.proc ba_div
.a16
.i16
    stz comp_and
    ldy #16
loop:
    asl temp
    rol comp_and
    lda comp_and
    sec
    sbc temp + 2
    bcc no_enters
    sta comp_and
    inc temp                    ; the quotient bit that just came in
no_enters:
    dey
    bne loop
    lda temp
    rts
.endproc

; A16 = n; returns with A16 = a number from 0 to n, inclusive. It is easyrpg's
; `Rand::GetRandomNumber(0, n)` with our randomness: see `Rng::up_to` in
; `rm2k-snes-battle`.
.proc ba_until
.a16
.i16
    inc a
    sta temp + 2
    jsr ba_random
    sta temp
    jsr ba_div
    lda comp_and
    rts
.endproc

; A8 = the percentage; returns with A8 at 1 if it came up and Z set
; accordingly. It is `Rand::PercentChance(int)`: `GetRandomNumber(0, 99) <
; rate`.
.proc ba_pct
.a8
.i16
    sta BA_T2
    rep #$20
.a16
    lda #99
    jsr ba_until
    sta BA_T0
    lda BA_T2
    and #$00FF
    cmp BA_T0                 ; C=1 if the percentage >= the roll
    sep #$20
.a8
    beq no                      ; equal: the roll is not less
    bcc no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 times the byte in `BA_T2`, in A16. Two hardware products, since it is
; eight by eight.
;
; The registers go through `f:` and not absolute: here the data bank is $7E,
; so a bare `sta WRMPYA` would write to WRAM and the product would come from a
; register nobody touched. It cost an afternoon and it looked like every hit
; missed.
.proc ba_mul
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB                  ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta comp_or23
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    xba                         ; times 256: that is what the high byte weighs
    and #$FF00
    clc
    adc comp_or23
    rts
.endproc

; A8 to X, with the upper byte at zero. It exists so as not to write `ldx` on
; a one-byte variable: with sixteen-bit indexes it would take the next byte
; along, which is the trap AGENTS.md names.
.proc ba_ax
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = a place in the troop of `BA_TROOP_K`; X = its member's index in
; `troop_member` and in the scene's `member_*` tables. The index is sixteen
; bits and `troop_init` words since 2026-10-10: Vampires Dawn's troops take
; 470 members. Clobbers A.
.proc ba_member_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    pha
    lda BA_TROOP_K
    asl a
    tax
    pla
    clc
    adc f:troop_init, x
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = the combatant; X = its offset inside `BA_ONE`. It is 40 bytes, that is
; thirty-two plus eight: two shifts and an add, no table.
.proc ba_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times eight
    sta temp + 2
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = the combatant; Z=0 if it is alive, that is, if the slot exists and it
; has HP left. **It does not use `pl*`**: the usual trap.
.proc ba_alive
.a8
.i16
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq no
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq no
    lda #1
    rts
no:
    lda #0
    rts
.endproc


; --- setting up the battle ------------------------------------------------
;
; The party in slots 0 to 3 and the troop in 4 to 11. The place being fixed
; and not a compacted list is what keeps a dead one showing in its line, as on
; the screen.

; Parameter `A` —0 attack, 1 defense, 3 agility— of the actor in `BA_S0`, in
; `BA_T2`. It goes through memory and not the accumulator on purpose: a
; routine that enters with 8-bit A and leaves with 16-bit A leaves the
; assembler believing something else, and an `lda #1` coming after would eat
; the next opcode. It already happened, and what showed was an attack of 999.
; It is `eq_parameter`, the same one the equipment screen uses: the level's
; value plus what each piece adds, capped to [1, 999]. `comp_col + 1` at zero
; is "nothing is being chosen", the simple path of `eq_effective`. **Clobbers
; X.**
.proc ba_param
.a8
.i16
    sta comp_or01 + 2
    stz comp_or01 + 3
    stz comp_col + 1
    lda BA_S0
    sta comp_char
    stz comp_char + 1
    jsl f:ba_t_param
    rep #$20
.a16
    lda comp_dup
    sta BA_T2
    sep #$20
.a8
    rts
.endproc

; The `sp_cost` of the weapon the actor in `BA_S0` has equipped, in A8, or
; zero: `weapon_sp_of`. The weapon is slot 0 of `FAR_EQUIPMENT`, which is
; read directly because the battle runs with the data bank at $7E, and the cost
; comes from `item_sp`, which is zero for anything that is not a weapon.
; Clobbers X and `BA_T0`.
.proc ba_weapon_sp
.a8
.i16
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    sta BA_T0
    asl a
    asl a
    clc
    adc BA_T0                   ; the actor times ten: five slots of two
    tax
    lda FAR_EQUIPMENT, x
    beq nothing
    cmp #ITEMS_N
    bcs nothing
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq nothing8                ; an item the cartridge does not carry
    jsr ba_ax
    lda f:item_sp, x
    rts
.a16
nothing:
    sep #$20
.a8
nothing8:
    lda #0
    rts
.endproc

; The critical hit chance of the actor in `BA_S0`, in A8, as the whole
; percentage `ba_pct` rolls against: `Game_Actor::GetCriticalHitChance`, its
; own `1 / critical_hit_chance` plus the best `critical_hit` of the weapons
; in slots 0 and 1 —the second holds one only with `two_weapon`—. RM2k adds
; them in floating point and they do not add up to the integers they look
; like, so this does not add: it looks the result up in `crit_table`, at the
; actor's row and its best weapon's column. See `critical_percent` in
; `rm2k-snes-battle`, which writes the table and is the model's too.
; Clobbers X, `BA_T0` and `BA_T1`.
.proc ba_crit_of
.a8
.i16
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    sta BA_T0
    asl a
    asl a
    clc
    adc BA_T0                   ; the actor times ten: five slots of two
    sta BA_T1
    tax
    lda FAR_EQUIPMENT, x
    jsr column                  ; the first slot's
.a8
    sta BA_T0
    rep #$20
.a16
    ldx BA_T1
    lda FAR_EQUIPMENT + 2, x
    jsr column                  ; and the second's
.a8
    cmp BA_T0
    bcs the_best                ; the columns go by bonus: the higher wins
    lda BA_T0
the_best:
    sta BA_T0
    stz BA_T0 + 1
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:actor_crit_row, x
    clc
    adc BA_T0
    tax
    sep #$20
.a8
    lda f:crit_table, x
    rts

; A16 an item from `FAR_EQUIPMENT`; leaves in A8 its column, `item_crit_k`,
; which is 0 for no item, one the cartridge does not carry, or one that is
; not a weapon.
.a16
column:
    beq none
    cmp #ITEMS_N
    bcs none
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq none8                   ; an item the cartridge does not carry
    jsr ba_ax
    lda f:item_crit_k, x
    rts
.a16
none:
    sep #$20
.a8
none8:
    lda #0
    rts
.endproc

; Actor `BA_S0` into party slot `BA_S1`, as the battle starts it: the HP and
; SP of the saved game, the parameters of its level and equipment, and no
; modifiers. It is `ba_build`'s, and since 2026-09-30 also `ba_sync_in`'s, for
; whoever a troop page brings into the party halfway through: in RM2k one who
; joins the battle is the same `Game_Actor` it was on the map. Clobbers
; `BA_S2` to `BA_S6`, `BA_T*`, A, X and Y.
.proc ba_actor_setup
.a8
.i16
    ldy #0
    jsl f:level_param
    stx BA_S2                 ; the max HP for its level
    ; All of its data into the scratch words: `ba_param` clobbers X, so first
    ; it is gathered and then written with X set, all at once.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:actor_txt, x
    sta BA_S3                 ; and the text number of its name
    lda FAR_HP, x
    sta BA_S4                 ; the HP the saved game brings
    sep #$20
.a8
    lda #0
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S5                   ; the attack
    sep #$20
.a8
    lda #1
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S6                   ; the defense
    sep #$20
.a8
    lda #3
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_T0                   ; the agility
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S2
    sta BA_ONE + BA_HPMAX, x
    lda BA_S4
    sta BA_ONE + BA_HP, x
    lda BA_S5
    sta BA_ONE + BA_ATK, x
    lda BA_S6
    sta BA_ONE + BA_DEF, x
    lda BA_T0
    sta BA_ONE + BA_AGI, x
    lda BA_S3
    sta BA_ONE + BA_TXT, x
    sep #$20
.a8
    lda #BA_HIT_ACTOR
    sta BA_ONE + BA_HIT, x
    lda BA_S0
    sta BA_ONE + BA_NUMBER, x
    lda #(BAF_HAS | BAF_ACTOR)
    sta BA_ONE + BA_FLAGS, x
    ; And what the skills need: the SP —which come from the saved game, like
    ; the HP— and the spirit, which until 2026-09-13 was not read because no
    ; formula asked for it. It goes in a second pass because `ba_param`
    ; clobbers X and it has to be set again.
    lda #2
    jsr ba_param                ; the spirit, `eq_parameter` like the others
    rep #$20
.a16
    sep #$20
.a8
    lda BA_S0
    ldy #1
    jsl f:level_param
    stx BA_S3                 ; the max SP for its level
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda FAR_SP, x
    sta BA_S4
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_ONE + BA_SP, x
    lda BA_S3
    sta BA_ONE + BA_SPMAX, x
    lda BA_T2
    sta BA_ONE + BA_SPI, x
    sta BA_ONE + BA_BSPI, x
    lda BA_S5
    sta BA_ONE + BA_BATK, x
    lda BA_S6
    sta BA_ONE + BA_BDEF, x
    lda BA_T0
    sta BA_ONE + BA_BAGI, x
    lda #0                      ; no modifiers: the battle has just started
    sta BA_ONE + BA_MATK, x
    sta BA_ONE + BA_MDEF, x
    sta BA_ONE + BA_MSPI, x
    sta BA_ONE + BA_MAGI, x
    sep #$20
.a8
    ; And what attacking costs it, which does not change in the equipment
    ; while the battle lasts: `weapon_sp_of`.
    jsr ba_weapon_sp
    pha
    lda BA_S1
    jsr ba_ax
    pla
    sta f:BA_WEAPON_SP, x
    ; And its critical hit, which depends on the weapon too.
    jsr ba_crit_of
    pha
    lda BA_S1
    jsr ba_x
    pla
    sta BA_ONE + BA_CRIT, x
    rts
.endproc

.proc ba_build
.a8
.i16
    ; All slots empty: the screen and the sweeps look at `BAF_HAS`.
    lda #0
other_slot:
    pha
    jsr ba_x
    lda #0
    sta BA_ONE + BA_FLAGS, x
    pla
    inc a
    cmp #BA_COMB_MAX
    bcc other_slot
    stz BA_NACTORS
    stz BA_KID

    ; --- the party ---
    lda #0
    sta BA_S1                 ; the place in the party
other_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    cmp party_n
    sep #$20
.a8
    bcc has_place
    jmp party_ready
has_place:
    lda BA_S1
    cmp #BA_PARTY_MAX
    bcc has_slot
    jmp party_ready
has_slot:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    bne with_actor
    jmp next_actor              ; a party slot with nobody in it
with_actor:
    sta BA_S0                 ; the actor from the LDB
    jsr ba_actor_setup
    inc BA_NACTORS
next_actor:
    inc BA_S1
    jmp other_actor
party_ready:

    ; --- the troop ---
    ; The bytecode carries the RM2k number, so it has to be looked up. A troop
    ; this cartridge does not carry is a battle with no enemies, and
    ; `battle_run` wins it by itself: it is the same thing the converter
    ; does with a song that did not fit.
    ; The count goes in sixteen bits, all of `BA_S1`: past 255 troops it is
    ; no byte.
    rep #$20
.a16
    lda #$FFFF
    sta BA_TROOP_K
    stz BA_S1
seek:
    lda BA_S1
    cmp #TROOPS_N
    bcs no_troop
    asl a
    tax
    lda f:troop_id, x
    cmp BA_TROOP
    beq got_it
    inc BA_S1
    bra seek
no_troop:
    sep #$20
.a8
    rts
got_it:
.a16
    lda BA_S1
    sta BA_TROOP_K              ; for `scene_troop_backdrop`
    tax
    sep #$20
.a8
    lda f:troop_n, x
    sta BA_S2                 ; how many members
    lda #0
    sta BA_S1                 ; the place in the troop
other_enemy:
    lda BA_S1
    cmp BA_S2
    bcc has_member
    jmp troop_list
has_member:
    cmp #BA_ENEMIES_MAX
    bcc has_slot_enemy
    jmp troop_list
has_slot_enemy:
    lda BA_S1
    jsr ba_member_x
    lda f:troop_member, x       ; the enemy, as a place in the tables
    sta BA_S0
    ; As with the actor: first everything is gathered and then written,
    ; because the long index is X and there are two tables to walk with it.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:enemy_hp, x
    sta BA_S4
    lda f:enemy_atk, x
    sta BA_S5
    lda f:enemy_def, x
    sta BA_S6
    lda f:enemy_agi, x
    sta BA_T0
    lda f:enemy_txt, x
    sta BA_T1
    sep #$20
.a8
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enemy_hit, x
    sta BA_T2
    lda f:enemy_crit, x
    sta BA_T2 + 1
    lda BA_S1
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_ONE + BA_HP, x
    sta BA_ONE + BA_HPMAX, x
    lda BA_S5
    sta BA_ONE + BA_ATK, x
    lda BA_S6
    sta BA_ONE + BA_DEF, x
    lda BA_T0
    sta BA_ONE + BA_AGI, x
    lda BA_T1
    sta BA_ONE + BA_TXT, x
    sep #$20
.a8
    lda BA_T2
    sta BA_ONE + BA_HIT, x
    lda BA_T2 + 1
    sta BA_ONE + BA_CRIT, x
    lda BA_S1
    sta BA_ONE + BA_NUMBER, x
    ; Hidden or not, by the bit of its place in `troop_hidden`: the troop's
    ; `invisible`, which `Game_Enemy` copies in `SetHidden` when set up.
    phx
    rep #$20
.a16
    lda BA_TROOP_K
    tax
    sep #$20
.a8
    lda f:troop_hidden, x
    sta BA_T0
    lda BA_S1
    jsr ba_ax
    lda f:scn_bits, x
    and BA_T0
    plx
    cmp #0                      ; `plx` overwrote Z: the AGENTS.md trap
    beq to_view
    lda #BAF_HIDDEN
    bra with_flags
to_view:
    lda #BAF_HAS
with_flags:
    sta BA_ONE + BA_FLAGS, x
    ; The skill data: the SP, the spirit and the four bases. It uses them
    ; —since 2026-09-27, see `ba_enemy_action`— and **receives them**:
    ; Mental Hack lowers its defense and spirit, and that needs the base and
    ; the modifier.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    phx
    tax
    lda f:enemy_sp, x
    sta BA_T0
    lda f:enemy_spi, x
    sta BA_T1
    plx
    lda BA_T0
    sta BA_ONE + BA_SP, x
    sta BA_ONE + BA_SPMAX, x
    lda BA_T1
    sta BA_ONE + BA_SPI, x
    sta BA_ONE + BA_BSPI, x
    lda BA_ONE + BA_ATK, x
    sta BA_ONE + BA_BATK, x
    lda BA_ONE + BA_DEF, x
    sta BA_ONE + BA_BDEF, x
    lda BA_ONE + BA_AGI, x
    sta BA_ONE + BA_BAGI, x
    lda #0
    sta BA_ONE + BA_MATK, x
    sta BA_ONE + BA_MDEF, x
    sta BA_ONE + BA_MSPI, x
    sta BA_ONE + BA_MAGI, x
    sep #$20
.a8
    inc BA_KID
    inc BA_S1
    jmp other_enemy
troop_list:
    rts
.endproc

; --- the hit --------------------------------------------------------------
;
; easyrpg's `Normal::vExecute`: **three rolls in this order** —hit, critical
; and variance— and the critical one is rolled even if the chance is zero.
; That order is the contract with `rm2k-snes-battle`: changing it on one
; side throws the other side's randomness out of step and it does not show
; until a hit comes out different.
;
; The source in `BA_MWHO` and the target in `BA_MTGT`. Leaves the damage in
; `BA_MDMG`, with $FFFF if the hit missed, and lowers the target's HP.
.proc ba_attack
.a8
.i16
    ; `Normal::vStart`: the weapon's SP, before anything else and without
    ; rolling, even if it then misses. With SP at zero it attacks anyway —RM2k
    ; does not grey out `Attack`— and they stay at zero. An enemy carries no
    ; weapon.
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcs no_weapon
    jsr ba_ax
    lda f:BA_WEAPON_SP, x
    sta BA_T2
    stz BA_T2 + 1
    lda BA_MWHO
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_charged
    lda #0
sp_charged:
    sta BA_ONE + BA_SP, x
    sep #$20
.a8
no_weapon:
    lda BA_MWHO
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; the source's offset
    sep #$20
.a8
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; and the target's
    sep #$20
.a8

    ; --- the hit chance, with the agility adjustment ---
    ldx BA_S0
    lda #100
    sec
    sbc BA_ONE + BA_HIT, x      ; X is the offset, already sixteen bits
    sta BA_T2                   ; 100 - hit, which is the product's byte
    rep #$20
.a16
    lda BA_ONE + BA_AGI, x
    bne agi_has
    lda #1                      ; `max(1, GetAgi())` from
                                ; CalcToHitAgiAdjustment
agi_has:
    sta BA_S2                   ; the source's agility
    ldx BA_S1
    lda BA_ONE + BA_AGI, x
    clc
    adc BA_S2
    jsr ba_mul                  ; (100 - hit) * (agiF + agiB)
    sta BA_S3
    lda BA_S2
    asl a
    sta temp + 2                ; the divisor: twice the agility
    ; Rounding up, which is what easyrpg's truncation on `100 - x` does:
    ; see `hit_rate_by_agility` in `rm2k-snes-battle`.
    lda BA_S3
    clc
    adc temp + 2
    dec a
    sta temp
    jsr ba_div
    sta BA_S3
    lda #100
    sec
    sbc BA_S3
    bpl hit_ready
    lda #0
hit_ready:
    sep #$20
.a8
    jsr ba_pct
    sta BA_S4                   ; 1 if it hit
    beq crit_zero
    lda BA_S0
    jsr ba_ax
    lda BA_ONE + BA_CRIT, x
    bra crit_strip
crit_zero:
    lda #0
crit_strip:
    jsr ba_pct
    sta BA_S5                   ; 1 if it was critical
    lda BA_S4
    bne sticks
    rep #$20
.a16
    lda #$FFFF
    sta BA_MDMG
    sep #$20
.a8
    rts

    ; --- the damage: max(0, atk / 2 - def / 4) ---
sticks:
    rep #$20
.a16
    ldx BA_S0
    lda BA_ONE + BA_ATK, x
    lsr a
    sta BA_S2
    ldx BA_S1
    lda BA_ONE + BA_DEF, x
    lsr a
    lsr a
    cmp BA_S2
    bcc has_damage
    lda #0
    sta BA_S2
    bra no_variance
has_damage:
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    sta BA_S2
    sep #$20
.a8
    lda BA_S5
    beq no_critical
    rep #$20
.a16
    ; A critical triples it: `dmg *= 3`.
    lda BA_S2
    asl a
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
no_critical:
    rep #$20
.a16
    ; The variance of `VarianceAdjustEffect` with var = 4:
    ;     adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2
    lda BA_S2
    asl a
    asl a
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne adjust_ready
    lda #1
adjust_ready:
    sta BA_S3
    jsr ba_until                ; A16 is still the adjustment
    clc
    adc BA_S2
    sta BA_S2
    lda BA_S3
    lsr a
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    bpl variance_ready
    lda #0                      ; cannot happen: 0.8 times the damage is
                                ; positive
variance_ready:
    sta BA_S2
no_variance:
    sep #$20
.a8
    ; Whoever is defending takes half: `AdjustDamageForDefend`.
    ldx BA_S1
    lda BA_ONE + BA_FLAGS, x
    and #BAF_DEF
    beq no_defense
    rep #$20
.a16
    lda BA_S2
    lsr a
    sta BA_S2
    sep #$20
.a8
no_defense:
    rep #$20
.a16
    lda BA_S2
    cmp #(BA_DAMAGE_MAX + 1)
    bcc damage_ready
    lda #BA_DAMAGE_MAX
damage_ready:
    sta BA_MDMG
    ldx BA_S1
    lda BA_ONE + BA_HP, x
    sec
    sbc BA_MDMG
    bpl hp_ready
    lda #0
hp_ready:
    sta BA_ONE + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; --- the turn -------------------------------------------------------------

; The enemies' actions: `CreateEnemyActions`. Each living one chooses what to
; do —`ba_enemy_action`— and then against whom, which is the order of
; `MakeAttack` and `MakeSkillAction` and the contract with `enemy_actions`
; in `rm2k-snes-battle`:
;
; * attacking, or a skill with `enemy` scope: a random living actor, **one
;   roll**;
; * one with `ally` scope: a random living enemy, **one roll**;
; * `self`, `enemies` and `party`: no roll. It is recorded on its user, and
;   the scope decides whom it falls on: see `ba_skill_use`.
;
; It goes before the execution order, which is how `SelectNextActor` calls
; it. If no living actor is left it stops and the remaining enemies are left
; without an action, which is the model's `break`: without that the two sides
; would roll a different number of times.
.proc ba_enemy_actions
.a8
.i16
    lda #BA_PARTY_MAX
    sta BA_S0
other:
    lda BA_S0
    cmp #BA_COMB_MAX
    bcc continues
    rts
continues:
    lda BA_S0
    jsr ba_alive
    bne lives
    jmp next
lives:
    ; The living actors, in a list, to pick one.
    lda #0
    jsr ba_alive_on_side
    lda BA_S1
    bne has_actors
    rts                         ; nobody left to hit
has_actors:
    lda BA_S0
    jsr ba_enemy_action
    sta BA_T1                   ; the action: a `k`, or attack, or nothing
    cmp #BA_EACC_NOTHING
    bne with_action
    jmp next
with_action:
    cmp #BA_EACC_ATTACK
    beq to_actor
    jsr ba_ax
    lda f:skill_scope, x
    cmp #BA_SCOPE_ENEMY
    beq to_actor
    cmp #BA_SCOPE_ALLY
    beq to_ally
    lda BA_S0                   ; `self`, `enemies`, `party`: its user
    bra record
to_ally:
    lda #BA_PARTY_MAX
    jsr ba_alive_on_side
to_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    dec a
    jsr ba_until
    tax
    sep #$20
.a8
    lda BA_CAND, x
record:
    sta BA_T0                   ; the chosen target
    lda BA_S0
    jsr ba_ax
    lda BA_T1
    sta BA_ACC_SKILL, x         ; the `k`, which `ba_skill_use` reads from here
    lda BA_S0
    asl a
    jsr ba_ax                   ; two bytes of action per combatant
    lda BA_T1
    cmp #BA_EACC_ATTACK
    beq is_attack
    lda #BA_SKILL
    bra command_list
is_attack:
    lda #BA_ATTACK
command_list:
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACTIONS
    jsr ba_ax
    lda BA_S0
    sta BA_EXEC, x
    inc BA_NACTIONS
next:
    inc BA_S0
    jmp other
.endproc

; The living ones of a side —A8 = 0 the party, `BA_PARTY_MAX` the troop— in
; `BA_CAND`, and how many in `BA_S1`. Clobbers `BA_S2`, A and X.
.proc ba_alive_on_side
.a8
.i16
    sta BA_S2
    clc
    adc #BA_PARTY_MAX           ; the party is four places
    cmp #BA_PARTY_MAX + 1
    bcc cap_ready
    lda #BA_COMB_MAX            ; and the troop, eight
cap_ready:
    sta BA_S2 + 1
    stz BA_S1
seek:
    lda BA_S2
    cmp BA_S2 + 1
    bcs ready
    jsr ba_alive
    beq no_lives
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_CAND, x
    inc BA_S1
no_lives:
    inc BA_S2
    bra seek
ready:
    rts
.endproc

; What enemy A8 does: `enemy_action` in `rm2k-snes-battle`, which is
; `SelectEnemyAiActionRpgRtCompat` with its list of `eacc_*`. Answers in A8
; the skill's `k`, `BA_EACC_ATTACK` or `BA_EACC_NOTHING`.
;
; 1. The possible ones are the attack and the skills its SP can pay for.
; 2. Each possible one weighs `max(0, rating - maximum + 10)`, and zero the one
;    that is not effective —bit 7 of `eacc_weight`—, which still counts toward
;    the maximum.
; 3. **With only one that has weight, no roll**; with more, `rand(0, sum - 1)`
;    and it is chosen by weight in list order.
;
; The weights go in `BA_SKILL_LIST`, which belongs to the skill-choosing screen
; and is rebuilt each time it opens: here the commands are already given.
; Clobbers `BA_S3` to `BA_S6`, `BA_T0`, `BA_T2`, A and X; not `BA_S0` or
; `BA_S1`.
.assert ACTIONS_MAX <= BA_SKILL_MAX, error, "an enemy's actions do not fit in BA_SKILL_LIST"
.proc ba_enemy_action
.a8
.i16
    ; --- which enemy of the tables it is: `troop_member` of its place ---
    sta BA_S3
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    sta BA_T0                   ; its place in the troop
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    sta BA_S4                   ; the SP it has left
    sep #$20
.a8
    lda BA_T0
    jsr ba_member_x
    lda f:troop_member, x
    sta BA_S5 + 1               ; which enemy of the tables, for `ba_eacc_x`
    jsr ba_ax
    lda f:enemy_acc_n, x
    sta BA_S5                   ; how many actions
    ; --- 1: the possible ones, with their raw weight, and the maximum ---
    stz BA_S6                   ; the maximum
    stz BA_T2                   ; which one it is at
possibles:
    lda BA_T2
    cmp BA_S5
    bcs views
    jsr ba_eacc_x
    lda f:eacc_weight, x
    sta BA_T0
    lda f:eacc_skill, x
    cmp #BA_EACC_ATTACK
    beq possible
    jsr ba_skill_cost           ; can its SP pay for it?
    sta BA_T0 + 1
    rep #$20
.a16
    lda BA_T0 + 1
    and #$00FF
    cmp BA_S4
    sep #$20
.a8
    beq possible
    bcc possible
    stz BA_T0                   ; they cannot: it weighs zero
    bra record_weight
possible:
    lda BA_T0
    and #$7F
    cmp BA_S6
    bcc record_weight
    sta BA_S6
record_weight:
    lda BA_T2
    jsr ba_ax
    lda BA_T0
    sta BA_SKILL_LIST, x
    inc BA_T2
    bra possibles
views:
    ; --- 2: the real weights, the sum, how many and the last one ---
    stz BA_S4                   ; the sum
    stz BA_S4 + 1               ; how many have weight
    stz BA_T2
weights:
    lda BA_T2
    cmp BA_S5
    bcs weighted
    jsr ba_ax
    lda BA_SKILL_LIST, x
    beq no_weight               ; impossible
    bmi no_weight8              ; not effective
    clc
    adc #10
    sec
    sbc BA_S6                   ; rating + 10 - maximum, which does not go
                                ; below 10 - 127
    bmi no_weight8
    beq no_weight8
    sta BA_SKILL_LIST, x
    clc
    adc BA_S4
    sta BA_S4
    inc BA_S4 + 1
    lda BA_T2
    sta BA_S3 + 1               ; the last one with weight
    bra next_weight
no_weight8:
    lda #0
    sta BA_SKILL_LIST, x
no_weight:
next_weight:
    inc BA_T2
    bra weights
weighted:
    lda BA_S4 + 1
    bne any
    lda #BA_EACC_NOTHING
    rts
any:
    cmp #1
    beq chosen                  ; only one: no roll
    ; --- 3: by weight ---
    rep #$20
.a16
    lda BA_S4
    and #$00FF
    dec a
    jsr ba_until
    sep #$20
.a8
    sta BA_T0                   ; `which`, less than the sum
    stz BA_T2
per_weight:
    lda BA_T2
    jsr ba_ax
    lda BA_T0
    sec
    sbc BA_SKILL_LIST, x
    bcc falls_here              ; `which` went negative
    sta BA_T0
    inc BA_T2
    bra per_weight
falls_here:
    lda BA_T2
    sta BA_S3 + 1
chosen:
    lda BA_S3 + 1
    jsr ba_eacc_x
    lda f:eacc_skill, x
    rts
.endproc

; A8 = an action in the list of the enemy in `BA_S5 + 1` —a place in the
; enemy tables—; X = its index in `eacc_*`. Sixteen bits and
; `enemy_acc_init` words since 2026-10-10: Vampires Dawn's enemies take 344
; actions. Clobbers A.
.proc ba_eacc_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    pha
    lda BA_S5 + 1
    and #$00FF
    asl a
    tax
    pla
    clc
    adc f:enemy_acc_init, x
    tax
    sep #$20
.a8
    rts
.endproc

; The execution order: `agi + rand(0, agi / 4 + 3)` for each one that acts,
; from highest to lowest and with a **stable** order, which is what
; `std::sort` does on a list that already comes stacked in the order it was
; pushed. It is `CreateExecutionOrder`. **One roll per action**, in that same
; order: first the party and then the troop.
.proc ba_exec_order
.a8
.i16
    lda #0
    sta BA_S0
strip:
    lda BA_S0
    cmp BA_NACTIONS
    bcs rolled
    lda BA_S0
    jsr ba_ax
    lda BA_EXEC, x
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; its offset
    lda BA_ONE + BA_AGI, x
    lsr a
    lsr a
    clc
    adc #3
    jsr ba_until
    sta BA_T0
    ldx BA_S1
    lda BA_ONE + BA_AGI, x
    clc
    adc BA_T0
    sta BA_ONE + BA_SORT, x
    sep #$20
.a8
    inc BA_S0
    bra strip
rolled:
    ; And the ordering, by insertion: there are twelve at most, and it stays
    ; **stable** if one only moves past the one above it when that one is
    ; strictly less.
    lda #1
    sta BA_S0
outside:
    lda BA_S0
    cmp BA_NACTIONS
    bcs sorted
    lda BA_S0
    jsr ba_ax
    lda BA_EXEC, x
    sta BA_S2                   ; the one being placed
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_SORT, x
    sta BA_S3
    sep #$20
.a8
    lda BA_S0
    sta BA_S1
inside:
    lda BA_S1
    beq put
    dec a
    jsr ba_ax
    lda BA_EXEC, x
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_SORT, x
    cmp BA_S3
    sep #$20
.a8
    bcs put                     ; the one above is greater or equal: it stays
                                ; there
    lda BA_S1
    dec a
    jsr ba_ax
    lda BA_EXEC, x
    inx
    sta BA_EXEC, x
    dec BA_S1
    bra inside
put:
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_EXEC, x
    inc BA_S0
    bra outside
sorted:
    rts
.endproc

; --- the screen -----------------------------------------------------------
;
; Text on the same grid of 32 by 28 cells as the equipment screen and the
; shop. The geometry comes from `rm2k-snes-battle` and the converter emits
; the positions, so it is written **by only one of the two sides**. Every
; window goes in the band below the scene, as RM2k's: see `ba_compose`.

; `BA_T1` = A16 + `BA_S0` times what a line measures: where line number
; `BA_S0` of the list starting at A16 begins.
.proc ba_row
.a16
.i16
    sta BA_T2
    lda BA_S0
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc BA_T2
    sta BA_T1
    rts
.endproc

; The write cursor at column A16 of line `BA_T1`.
.proc ba_go
.a16
.i16
    clc
    adc BA_T1
    sta pick_table
    rts
.endproc

; An enemy's line in the list to attack: its name, and its HP only with
; `BA_HP_ENEMIES`. A8 = the combatant, `BA_T1` = where its line starts.
.proc ba_line
.a8
.i16
    sta BA_S4
    jsr ba_x
    stx BA_S5                   ; its offset, which `scr_text` overwrites
    stz temp + 1
    rep #$20
.a16
    lda #BA_ENEMY_NAME_DX
    jsr ba_go
    ldx BA_S5
    lda BA_ONE + BA_TXT, x
    tax
    sep #$20
.a8
    lda #BA_ENEMY_NAME_WIDTH
    sta comp_dup + 3
    lda #1
    sta TL_BY_REF
    jsl f:ba_t_text
.if ::BA_HP_ENEMIES = 0
    ; An enemy does not show its HP, as in RM2k: the line is only its name.
    ; With `[debug] enemy_hp` in the project file they show, for debugging,
    ; where the party's go —the list leaves them out then—. The `::` is not
    ; redundant: inside a `.proc`, `ca65` does not give a constant value to a
    ; bare name, which could be defined further down in the same `.proc`.
    rts
.else
    rep #$20
.a16
    lda #BA_HP_DX
    jsr ba_go
    sep #$20
.a8
    ldx #BA_TXT_HP
    jsl f:ba_t_text
    ldx BA_S5
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    jsr ba_capped
    sep #$20
.a8
    jsl f:ba_t_number
    rts
.endif
.endproc

; An actor's line in the band: its name, its state, and its HP and SP, in
; gray if it is down —RM2k's `Window_BattleStatus`, `Talan  Normal  HP 49/ 49
; SP 49`—. A8 = the actor's slot, `BA_T1` = where its line starts.
;
; The state is the database's `normal_status`, or the dead state's name for
; one at zero HP: the battle has no other states. The HP and the SP are
; **one run each** —the term, copied, the number in three places and, in
; the HP, the slash and the maximum—, and the name and the state go by
; reference: a line of the band also carries a command, and with the
; letters copied they did not fit in a row's record. See `TL_BY_REF`.
.proc ba_party_line
.a8
.i16
    sta BA_S4
    jsr ba_alive
    beq dead
    lda #0
    bra variant
dead:
    lda #1
variant:
    sta temp + 1
    lda BA_S4
    jsr ba_x
    stx BA_S5                   ; its offset, which `scr_text` overwrites
    rep #$20
.a16
    lda #BA_NAME_DX
    jsr ba_go
    ldx BA_S5
    lda BA_ONE + BA_TXT, x
    tax
    sep #$20
.a8
    lda #BA_NAME_WIDTH
    sta comp_dup + 3
    lda #1
    sta TL_BY_REF
    jsl f:ba_t_text
    rep #$20
.a16
    lda #BA_STATE_DX
    jsr ba_go
    sep #$20
.a8
    lda #BA_STATE_WIDTH
    sta comp_dup + 3
    lda #1
    sta TL_BY_REF
    ldx #BA_TXT_NORMAL
    lda temp + 1
    beq state_set
    ldx #BA_TXT_DEAD
state_set:
    jsl f:ba_t_text
    ; "HP", the HP in three places, the slash and the maximum, as one run
    rep #$20
.a16
    lda #BA_HP_DX
    jsr ba_go
    sep #$20
.a8
    ldx #BA_TXT_HP
    jsl f:ba_t_text
    ldx BA_S5
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    jsr ba_capped
    sep #$20
.a8
    jsl f:ba_t_number
    lda #$2F                    ; the slash between the HP and their maximum
    jsl f:ba_t_glyph
    ldx BA_S5
    rep #$20
.a16
    lda BA_ONE + BA_HPMAX, x
    jsr ba_capped
    sep #$20
.a8
    jsl f:ba_t_number
    ; and "SP" with the SP, another
    rep #$20
.a16
    lda #BA_SP_DX
    jsr ba_go
    sep #$20
.a8
    ldx #BA_TXT_SP
    jsl f:ba_t_text
    ldx BA_S5
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    jsr ba_capped
    sep #$20
.a8
    jsl f:ba_t_number
    rts
.endproc

; A16 into `comp_dup`, capped at 999 as RM2k's window shows it, in three
; places. Comes and goes with A16.
.proc ba_capped
.a16
.i16
    cmp #1000
    bcc fits
    lda #999
fits:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    rep #$20
.a16
    rts
.endproc

; The name of combatant A8 wherever `pick_table` says, in full.
.proc ba_name
.a8
.i16
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_TXT, x
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_text
    rts
.endproc

; A game term —X already set— wherever `pick_table` says, in full.
.proc ba_finished
.a8
.i16
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_text
    rts
.endproc

; The message, according to `BA_MTYPE`. Victory does not go through here: it
; goes in the same window, see `ba_vic_message`. All the words come from
; the LDB —`attacking`, `enemy_damaged`, `defeat`...— and are put together as
; in `game_message_terms.cpp`: the name stuck to the term, and in the damage
; one the number in the middle. None of them is ours.
;
; **It is put together in `BA_MBUF` first and drawn after**, by `ba_flow`:
; RM2k's lines are as long as the pieces make them —"Talan has perceived the
; enemy aura." is thirty-five— and one line here carries thirty-one. Drawn
; letter by letter, what did not fit went on in the cell below, which is the
; bottom half of the line. So each of RM2k's lines is cut at the spaces into
; as many as it takes, up to the window's four.
.proc ba_message
.a8
.i16
    jsr ba_mopen
    lda BA_MTYPE
    cmp #BA_MSG_ATTACK
    beq attack
    cmp #BA_MSG_DEFENDS
    beq defends
    cmp #BA_MSG_NO_FLED
    beq no_fled
    cmp #BA_MSG_FLED
    beq fled
    cmp #BA_MSG_ITEM
    beq uses_item
    cmp #BA_MSG_SKILL
    beq uses_skill
    cmp #BA_MSG_ITEM_SP
    beq item_sp
    ldx #BA_TXT_DEFEAT
    jmp only
item_sp:
    jmp item
uses_skill:
    jmp skill
uses_item:
    jmp item
fled:
    ldx #BA_TXT_FLED
    jmp only
no_fled:
    ldx #BA_TXT_NO_FLED
only:
    jsr ba_put_text
    jmp ba_flow
defends:
    lda BA_MWHO
    jsr ba_put_name
    ldx #BA_TXT_DEFENDS
    jsr ba_put_text
    jmp ba_flow
attack:
    lda BA_MWHO
    jsr ba_put_name
    ldx #BA_TXT_ATTACKS
    jsr ba_put_text
    ; The second line: the result on the target.
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    rep #$20
.a16
    lda BA_MDMG
    cmp #$FFFF
    sep #$20
.a8
    bne stuck
    jmp failed
stuck:
    ; `<name> <damage> health lost.`
    lda #$20                    ; the space between the name and the number
    jsr ba_put
    rep #$20
.a16
    lda BA_MDMG
    sta BA_T0
    sep #$20
.a8
    jsr ba_put_number
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs is_enemy
    ldx #BA_TXT_DAMAGE_ACTOR
    bra says
is_enemy:
    ldx #BA_TXT_DAMAGE_ENEMY
says:
    jsr ba_put_text
    jmp ba_flow
item:
    ; `<who> <item> used.`, which is
    ; `source.GetName() + " " + item.name + terms.use_item` from
    ; `GetItemStartMessage2k`.
    lda BA_MWHO
    jsr ba_put_name
    lda #$20
    jsr ba_put
    rep #$20
.a16
    lda BA_MITEM
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; times three: `3k` is the item's name
    tax
    sep #$20
.a8
    jsr ba_put_text
    ldx #BA_TXT_USES
    jsr ba_put_text
    ; The second line, the result: RM2k writes one after the other in the
    ; same place —see `ba_item_use`—, and here each is a message. The SP one
    ; goes alone when there is no HP line, and after it when there is.
    lda BA_MTYPE
    cmp #BA_MSG_ITEM_SP
    beq sp_line
    lda BA_MREVIVED
    bne revived
    lda BA_MHPLINE
    bne hp_line
    rep #$20
.a16
    lda BA_MSP
    sep #$20
.a8
    bne sp_line
    jmp ba_flow                 ; nothing changed: the first line alone
revived:
    ; Revived: `<target> has revived!`, the dead state's `message_recovery`,
    ; stuck to the name. RM2k does not show the HP one when it revives
    ; —`IsRevived` in the `ePreHp` of `ProcessBattleActionParamEffects`— but
    ; the one for the states it removed —`ProcessBattleActionStateEffects`—,
    ; and of those the port only knows the dead one.
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    ldx #BA_TXT_REVIVED
    jsr ba_put_text
    jmp ba_flow
hp_line:
    ; `<target> HP <n> Recovered`, which is `GetHpSpRecoveredMessage`.
    ldx #BA_TXT_HP
    rep #$20
.a16
    lda BA_MHEAL
    bra recovered
sp_line:
.a8
    ; And with the SP: `GetSpRecoveredMessage` is the same with
    ; `spirit_points`.
    ldx #BA_TXT_SP
    rep #$20
.a16
    lda BA_MSP
recovered:
    pha                         ; the number, and below it the term
    sep #$20
.a8
    phx
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    lda #$20
    jsr ba_put
    plx
    jsr ba_put_text
    lda #$20
    jsr ba_put
    rep #$20
.a16
    pla
    sta BA_T0
    sep #$20
.a8
    jsr ba_put_number
    ldx #BA_TXT_RECOVERED
    jsr ba_put_text
    jmp ba_flow
skill:
    ; `<who><using_message1>` on top and `<using_message2>` below, which is
    ; `GetSkillFirstStartMessage2k` and its sibling. Both lines come from the
    ; LDB, like everything this screen writes.
    lda BA_MWHO
    jsr ba_put_name
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_msg1, x
    tax
    sep #$20
.a8
    jsr ba_put_text
    jsr ba_mnext
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_msg2, x
    tax
    sep #$20
.a8
    jsr ba_put_text
    jmp ba_flow
failed:
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs fails_enemy
    ldx #BA_TXT_NO_DAMAGE_ACTOR
    bra fails_says
fails_enemy:
    ldx #BA_TXT_NO_DAMAGE_ENEMY
fails_says:
    jsr ba_put_text
    jmp ba_flow
.endproc

; --- the message, put together before it is drawn ----------------------------
;
; `BA_MBUF` holds RM2k's two lines, one after the other, a letter per byte;
; `BA_MPTR` is where the next letter goes and `BA_MLIM` where the line being
; written ends. What does not fit in `BA_MBUF_MAX` is dropped: no message of
; the game comes near it.

; The first line, empty.
.proc ba_mopen
.a8
.i16
    rep #$20
.a16
    lda #BA_MBUF
    sta BA_MPTR
    sta BA_MSTART
    clc
    adc #BA_MBUF_MAX
    sta BA_MLIM
    sep #$20
.a8
    lda #1
    sta BA_MN
    rts
.endproc

; The second line: the first ends where it is.
.proc ba_mnext
.a8
.i16
    rep #$20
.a16
    lda BA_MPTR
    sta BA_MEND
    lda #BA_MBUF + BA_MBUF_MAX
    sta BA_MPTR
    sta BA_MSTART + 2
    clc
    adc #BA_MBUF_MAX
    sta BA_MLIM
    sep #$20
.a8
    lda #2
    sta BA_MN
    rts
.endproc

; A8, a letter, at the end of the line being written. Clobbers X.
.proc ba_put
.a8
.i16
    ldx BA_MPTR
    cpx BA_MLIM
    bcs full
    sta a:0, x                  ; bank $7E: the data bank of the battle
    inx
    stx BA_MPTR
full:
    rts
.endproc

; Text X —see `item_txt_*`— at the end of the line, whole. Clobbers X, Y
; and `BA_MCOUNT`.
.proc ba_put_text
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    beq done
    sta BA_MCOUNT
    ldy #0
letter:
    lda [msg_ptr], y
    jsr ba_put
    iny
    dec BA_MCOUNT
    bne letter
done:
    rts
.endproc

; The name of combatant A8 at the end of the line, whole.
.proc ba_put_name
.a8
.i16
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_TXT, x
    tax
    sep #$20
.a8
    jmp ba_put_text
.endproc

; The number in `BA_T0`, 0 to 9999, at the end of the line with no leading
; spaces: easyrpg sticks the damage to the name without padding. Clobbers
; `BA_T0`, X and Y.
.proc ba_put_number
.a8
.i16
    stz BA_MCOUNT               ; whether a digit has gone already
    ldx #0
power:
    ldy #0
    rep #$20
.a16
    lda BA_T0
subtract:
    cmp f:powers, x
    bcc digit
    sbc f:powers, x             ; C=1 from the cmp
    iny
    bra subtract
digit:
    sta BA_T0
    sep #$20
.a8
    tya
    bne write
    lda BA_MCOUNT
    beq next                    ; a zero before everything else
    lda #0
write:
    clc
    adc #'0'
    phx
    jsr ba_put
    plx
    lda #1
    sta BA_MCOUNT
next:
    inx
    inx
    cpx #6
    bcc power
    lda BA_T0                   ; the units, always
    clc
    adc #'0'
    jmp ba_put
powers:
    .word 1000, 100, 10
.endproc

; How many letters from `BA_MP` fit in a line —their advances add up to
; `BA_PAGE_MSG_WIDTH` cells at most—, up to `BA_ME`; one at least, so that
; the cut always moves. Uses `BA_MB`. A16.
.proc ba_fit
.a16
.i16
    stz BA_MB                   ; the pixels so far
    ldx BA_MP
letter:
    cpx BA_ME
    bcs done
    lda a:0, x
    and #$00FF
    sec
    sbc #' '
    phx
    tax
    lda f:font_advance, x
    plx
    and #$00FF
    clc
    adc BA_MB
    cmp #(BA_PAGE_MSG_WIDTH * 8 + 1)
    bcs done
    sta BA_MB
    inx
    bra letter
done:
    txa
    sec
    sbc BA_MP
    bne some
    inc a
some:
    rts
.endproc

; The message's lines, cut and drawn: each of RM2k's lines in `BA_MBUF` is
; cut into lines as wide as `BA_PAGE_MSG_WIDTH` cells at its spaces —a word
; longer than that, at the edge—, and the spaces of the cut go nowhere. A
; line is measured in pixels, with the font's advances: until 2026-10-03 it
; was `BA_PAGE_MSG_WIDTH` letters, one per cell. Up to `BA_MLINES_MAX`
; lines, from the window's first, `BA_MSG_POS1`, down: RM2k's message
; window, which takes the whole band. Until 2026-10-04 the last went on the
; bottom line of the screen and the others over the party's. Clobbers
; everything.
.proc ba_flow
.a8
.i16
    lda BA_MN
    cmp #2                      ; C=1 if it is the second
    rep #$20
.a16
    lda BA_MPTR
    ldx #0
    bcc first_end
    ldx #2
first_end:
    sta BA_MEND, x              ; where the line being written ends
    sep #$20
.a8
    stz BA_MDN
    stz BA_MI
one_line:
    lda BA_MI
    cmp BA_MN
    bcc cut_it
    jmp draw
cut_it:
    asl a
    jsr ba_ax
    rep #$20
.a16
    lda BA_MSTART, x
    sta BA_MP
    lda BA_MEND, x
    sta BA_ME
    sep #$20
.a8
again:
    lda BA_MDN
    cmp #BA_MLINES_MAX
    bcs line_done
    rep #$20
.a16
    lda BA_ME
    sec
    sbc BA_MP
    beq line_done16             ; nothing left
    pha
    jsr ba_fit
    cmp 1, s
    bcc too_long                ; fewer than what is left
    pla
    jsr ba_mline                ; the rest, as it is
line_done16:
    sep #$20
.a8
line_done:
    inc BA_MI
    jmp one_line
.a16
too_long:
    ; The last space at most one line further on: the line is what is
    ; before it.
    sta BA_MB                   ; how many fit, for a word with no space
    pla
    lda BA_MP
    clc
    adc BA_MB
    tax
    sep #$20
.a8
seek:
    cpx BA_MP
    beq no_space
    lda a:0, x
    cmp #$20
    beq space
    dex
    bra seek
no_space:
    ; A word longer than the line: cut at the edge.
    rep #$20
.a16
    lda BA_MB
    jsr ba_mline
    lda BA_MP
    clc
    adc BA_MB
    sta BA_MP
    bra skip_spaces
.a8
space:
    stx BA_MB
    ; Without the spaces before the cut.
trim:
    dex
    cpx BA_MP
    bcc trimmed
    lda a:0, x
    cmp #$20
    beq trim
trimmed:
    inx
    rep #$20
.a16
    txa
    sec
    sbc BA_MP
    jsr ba_mline
    lda BA_MB
    sta BA_MP
skip_spaces:
    ; And the next one starts after the spaces.
    ldx BA_MP
    sep #$20
.a8
skip:
    cpx BA_ME
    bcs skipped
    lda a:0, x
    cmp #$20
    bne skipped
    inx
    bra skip
skipped:
    stx BA_MP
    jmp again

draw:
    rep #$20
.a16
    lda #BA_MSG_POS1
    sta BA_T1
    sep #$20
.a8
    stz BA_MI
    stz temp + 1                ; white
each:
    lda BA_MI
    cmp BA_MDN
    bcc a_line
    rts
a_line:
    ; The line blank first: it is the row's text that goes, in the text
    ; layer —nothing else is drawn under the message since 2026-10-04, but
    ; it costs nothing—.
    rep #$20
.a16
    lda BA_T1
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the row: 64 bytes each
    sep #$20
.a8
    jsl f:tl_clear_row + FAST
    rep #$20
.a16
    lda #BA_MSG_DX
    jsr ba_go
    lda BA_MI
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; three bytes per line
    tax
    lda BA_MDL, x
    sta BA_MP                   ; where it starts
    lda BA_MDL + 2, x
    and #$00FF
    sta BA_T0                   ; and how many letters
    sep #$20
.a8
letter:
    lda BA_T0
    beq next_line
    dec BA_T0
    ldx BA_MP
    lda a:0, x
    inx
    stx BA_MP
    jsl f:ba_t_glyph
    bra letter
next_line:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_ROW_BYTES
    sta BA_T1
    sep #$20
.a8
    inc BA_MI
    bra each
.endproc

; One more line to draw: from `BA_MP`, A16 letters. Comes and goes with A16.
.proc ba_mline
.a16
.i16
    pha
    lda BA_MDN
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; three bytes per line
    tax
    lda BA_MP
    sta BA_MDL, x
    pla
    sep #$20
.a8
    sta BA_MDL + 2, x
    inc BA_MDN
    rep #$20
.a16
    rts
.endproc
