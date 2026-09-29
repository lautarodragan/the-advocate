.segment "FAR"

; The battle's xorshift, the same as `eventos.azar_siguiente` and
; `lluvia_azar`, but on `BA_SEM`, which has **its own seed**: fighting does
; not advance the map's randomness, so a random `ControlVars` gives the same
; with a battle in between and without one.
.proc ba_azar
.a16
.i16
    lda BA_SEM
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor BA_SEM
    sta BA_SEM
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor BA_SEM
    sta BA_SEM
    xba
    and #$FF00
    eor BA_SEM
    sta BA_SEM
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
lazo:
    asl temp
    rol comp_and
    lda comp_and
    sec
    sbc temp + 2
    bcc no_entra
    sta comp_and
    inc temp                    ; the quotient bit that just came in
no_entra:
    dey
    bne lazo
    lda temp
    rts
.endproc

; A16 = n; returns with A16 = a number from 0 to n, inclusive. It is easyrpg's
; `Rand::GetRandomNumber(0, n)` with our randomness: see
; `batalla.Azar.hasta`.
.proc ba_hasta
.a16
.i16
    inc a
    sta temp + 2
    jsr ba_azar
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
    jsr ba_hasta
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

; A8 = the combatant; X = its offset inside `BA_UNO`. It is 40 bytes, that is
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
.proc ba_vivo
.a8
.i16
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq no
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
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
; It is `eq_parametro`, the same one the equipment screen uses: the level's
; value plus what each piece adds, capped to [1, 999]. `comp_col + 1` at zero
; is "nothing is being chosen", the simple path of `eq_efectivo`. **Clobbers
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
; zero: `batalla.sp_del_arma`. The weapon is slot 0 of `FAR_EQUIPO`, which is
; read directly because the battle runs with the data bank at $7E, and the cost
; comes from `item_sp`, which is zero for anything that is not a weapon.
; Clobbers X and `BA_T0`.
.proc ba_sp_del_arma
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
    lda FAR_EQUIPO, x
    beq nada
    cmp #ITEMS_N
    bcs nada
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq nada8                   ; an item the cartridge does not carry
    jsr ba_ax
    lda f:item_sp, x
    rts
.a16
nada:
    sep #$20
.a8
nada8:
    lda #0
    rts
.endproc

.proc ba_armar
.a8
.i16
    ; All slots empty: the screen and the sweeps look at `BAF_HAY`.
    lda #0
otra_ranura:
    pha
    jsr ba_x
    lda #0
    sta BA_UNO + BA_FLAGS, x
    pla
    inc a
    cmp #BA_COMB_MAX
    bcc otra_ranura
    stz BA_NACT
    stz BA_NENE

    ; --- the party ---
    lda #0
    sta BA_S1                 ; the place in the party
otro_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    cmp grupo_n
    sep #$20
.a8
    bcc hay_lugar
    jmp grupo_listo
hay_lugar:
    lda BA_S1
    cmp #BA_GRUPO_MAX
    bcc hay_ranura
    jmp grupo_listo
hay_ranura:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    bne con_actor
    jmp siguiente_actor         ; a party slot with nobody in it
con_actor:
    sta BA_S0                 ; the actor from the LDB
    ldy #0
    jsl f:nivel_param
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
    sta BA_UNO + BA_HPMAX, x
    lda BA_S4
    sta BA_UNO + BA_HP, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_S3
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda #BA_ACIERTO_ACTOR
    sta BA_UNO + BA_HIT, x
    lda #0
    sta BA_UNO + BA_CRIT, x   ; no actor in ABL has a critical hit
    lda BA_S0
    sta BA_UNO + BA_NUMERO, x
    lda #(BAF_HAY | BAF_ACTOR)
    sta BA_UNO + BA_FLAGS, x
    ; And what the skills need: the SP —which come from the saved game, like
    ; the HP— and the spirit, which until 2026-09-13 was not read because no
    ; formula asked for it. It goes in a second pass because `ba_param`
    ; clobbers X and it has to be set again.
    lda #2
    jsr ba_param                ; the spirit, `eq_parametro` like the others
    rep #$20
.a16
    sep #$20
.a8
    lda BA_S0
    ldy #1
    jsl f:nivel_param
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
    sta BA_UNO + BA_SP, x
    lda BA_S3
    sta BA_UNO + BA_SPMAX, x
    lda BA_T2
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_S5
    sta BA_UNO + BA_BATK, x
    lda BA_S6
    sta BA_UNO + BA_BDEF, x
    lda BA_T0
    sta BA_UNO + BA_BAGI, x
    lda #0                      ; no modifiers: the battle has just started
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    ; And what attacking costs it, which does not change in the equipment
    ; while the battle lasts: `batalla.sp_del_arma`.
    jsr ba_sp_del_arma
    pha
    lda BA_S1
    jsr ba_ax
    pla
    sta f:BA_ARMA_SP, x
    inc BA_NACT
siguiente_actor:
    inc BA_S1
    jmp otro_actor
grupo_listo:

    ; --- the troop ---
    ; The bytecode carries the RM2k number, so it has to be looked up. A troop
    ; this cartridge does not carry is a battle with no enemies, and
    ; `batalla_correr` wins it by itself: it is the same thing the converter
    ; does with a song that did not fit.
    lda #$FF
    sta BA_TROPA_K
    lda #0
    sta BA_S1
busca:
    lda BA_S1
    cmp #TROPAS_N
    bcs sin_tropa
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    asl a
    tax
    lda f:tropa_id, x
    cmp BA_TROPA
    sep #$20
.a8
    beq la_tengo
    inc BA_S1
    bra busca
sin_tropa:
    rts
la_tengo:
    lda BA_S1
    sta BA_TROPA_K              ; for `escena_tropa_fondo`
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_n, x
    sta BA_S2                 ; how many members
    lda f:tropa_ini, x
    sta BA_S3                 ; where its list starts
    lda #0
    sta BA_S1                 ; the place in the troop
otro_enemigo:
    lda BA_S1
    cmp BA_S2
    bcc hay_miembro
    jmp tropa_lista
hay_miembro:
    cmp #BA_ENEMIGOS_MAX
    bcc hay_ranura_ene
    jmp tropa_lista
hay_ranura_ene:
    rep #$20
.a16
    lda BA_S1
    clc
    adc BA_S3
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_miembro, x      ; the enemy, as a place in the tables
    sta BA_S0
    ; As with the actor: first everything is gathered and then written,
    ; because the long index is X and there are two tables to walk with it.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:enemigo_hp, x
    sta BA_S4
    lda f:enemigo_atk, x
    sta BA_S5
    lda f:enemigo_def, x
    sta BA_S6
    lda f:enemigo_agi, x
    sta BA_T0
    lda f:enemigo_txt, x
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
    lda f:enemigo_hit, x
    sta BA_T2
    lda f:enemigo_crit, x
    sta BA_T2 + 1
    lda BA_S1
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_UNO + BA_HP, x
    sta BA_UNO + BA_HPMAX, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_T1
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda BA_T2
    sta BA_UNO + BA_HIT, x
    lda BA_T2 + 1
    sta BA_UNO + BA_CRIT, x
    lda BA_S1
    sta BA_UNO + BA_NUMERO, x
    ; Hidden or not, by the bit of its place in `tropa_ocultos`: the troop's
    ; `invisible`, which `Game_Enemy` copies in `SetHidden` when set up.
    phx
    lda BA_TROPA_K
    jsr ba_ax
    lda f:tropa_ocultos, x
    sta BA_T0
    lda BA_S1
    jsr ba_ax
    lda f:esc_bits, x
    and BA_T0
    plx
    cmp #0                      ; `plx` overwrote Z: the AGENTS.md trap
    beq a_la_vista
    lda #BAF_OCULTO
    bra con_flags
a_la_vista:
    lda #BAF_HAY
con_flags:
    sta BA_UNO + BA_FLAGS, x
    ; The skill data: the SP, the spirit and the four bases. It uses them
    ; —since 2026-09-27, see `ba_accion_enemiga`— and **receives them**:
    ; Mental Hack lowers its defense and spirit, and that needs the base and
    ; the modifier.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    phx
    tax
    lda f:enemigo_sp, x
    sta BA_T0
    lda f:enemigo_spi, x
    sta BA_T1
    plx
    lda BA_T0
    sta BA_UNO + BA_SP, x
    sta BA_UNO + BA_SPMAX, x
    lda BA_T1
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_UNO + BA_ATK, x
    sta BA_UNO + BA_BATK, x
    lda BA_UNO + BA_DEF, x
    sta BA_UNO + BA_BDEF, x
    lda BA_UNO + BA_AGI, x
    sta BA_UNO + BA_BAGI, x
    lda #0
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    inc BA_NENE
    inc BA_S1
    jmp otro_enemigo
tropa_lista:
    rts
.endproc

; --- the hit --------------------------------------------------------------
;
; easyrpg's `Normal::vExecute`: **three rolls in this order** —hit, critical
; and variance— and the critical one is rolled even if the chance is zero.
; That order is the contract with `tools/port/battle.py`: changing it on one
; side throws the other side's randomness out of step and it does not show
; until a hit comes out different.
;
; The source in `BA_MQUIEN` and the target in `BA_MBLA`. Leaves the damage in
; `BA_MDANO`, with $FFFF if the hit missed, and lowers the target's HP.
.proc ba_atacar
.a8
.i16
    ; `Normal::vStart`: the weapon's SP, before anything else and without
    ; rolling, even if it then misses. With SP at zero it attacks anyway —RM2k
    ; does not grey out `Attack`— and they stay at zero. An enemy carries no
    ; weapon.
    lda BA_MQUIEN
    cmp #BA_GRUPO_MAX
    bcs sin_arma
    jsr ba_ax
    lda f:BA_ARMA_SP, x
    sta BA_T2
    stz BA_T2 + 1
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_cobrado
    lda #0
sp_cobrado:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
sin_arma:
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; the source's offset
    sep #$20
.a8
    lda BA_MBLA
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
    sbc BA_UNO + BA_HIT, x      ; X is the offset, already sixteen bits
    sta BA_T2                   ; 100 - hit, which is the product's byte
    rep #$20
.a16
    lda BA_UNO + BA_AGI, x
    bne agi_hay
    lda #1                      ; `max(1, GetAgi())` from
                                ; CalcToHitAgiAdjustment
agi_hay:
    sta BA_S2                   ; the source's agility
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_S2
    jsr ba_mul                  ; (100 - hit) * (agiF + agiB)
    sta BA_S3
    lda BA_S2
    asl a
    sta temp + 2                ; the divisor: twice the agility
    ; Rounding up, which is what easyrpg's truncation on `100 - x` does:
    ; see `batalla.acierto_por_agilidad`.
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
    bpl acierto_listo
    lda #0
acierto_listo:
    sep #$20
.a8
    jsr ba_pct
    sta BA_S4                   ; 1 if it hit
    beq crit_cero
    lda BA_S0
    jsr ba_ax
    lda BA_UNO + BA_CRIT, x
    bra crit_tira
crit_cero:
    lda #0
crit_tira:
    jsr ba_pct
    sta BA_S5                   ; 1 if it was critical
    lda BA_S4
    bne pega
    rep #$20
.a16
    lda #$FFFF
    sta BA_MDANO
    sep #$20
.a8
    rts

    ; --- the damage: max(0, atk / 2 - def / 4) ---
pega:
    rep #$20
.a16
    ldx BA_S0
    lda BA_UNO + BA_ATK, x
    lsr a
    sta BA_S2
    ldx BA_S1
    lda BA_UNO + BA_DEF, x
    lsr a
    lsr a
    cmp BA_S2
    bcc hay_dano
    lda #0
    sta BA_S2
    bra sin_varianza
hay_dano:
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    sta BA_S2
    sep #$20
.a8
    lda BA_S5
    beq sin_critico
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
sin_critico:
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
    bne ajuste_listo
    lda #1
ajuste_listo:
    sta BA_S3
    jsr ba_hasta                ; A16 is still the adjustment
    clc
    adc BA_S2
    sta BA_S2
    lda BA_S3
    lsr a
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    bpl varianza_listo
    lda #0                      ; cannot happen: 0.8 times the damage is
                                ; positive
varianza_listo:
    sta BA_S2
sin_varianza:
    sep #$20
.a8
    ; Whoever is defending takes half: `AdjustDamageForDefend`.
    ldx BA_S1
    lda BA_UNO + BA_FLAGS, x
    and #BAF_DEF
    beq sin_defensa
    rep #$20
.a16
    lda BA_S2
    lsr a
    sta BA_S2
    sep #$20
.a8
sin_defensa:
    rep #$20
.a16
    lda BA_S2
    cmp #(BA_DANO_MAX + 1)
    bcc dano_listo
    lda #BA_DANO_MAX
dano_listo:
    sta BA_MDANO
    ldx BA_S1
    lda BA_UNO + BA_HP, x
    sec
    sbc BA_MDANO
    bpl hp_listo
    lda #0
hp_listo:
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; --- the turn -------------------------------------------------------------

; The enemies' actions: `CreateEnemyActions`. Each living one chooses what to
; do —`ba_accion_enemiga`— and then against whom, which is the order of
; `MakeAttack` and `MakeSkillAction` and the contract with
; `batalla.acciones_de_los_enemigos`:
;
; * attacking, or a skill with `enemy` scope: a random living actor, **one
;   roll**;
; * one with `ally` scope: a random living enemy, **one roll**;
; * `self`, `enemies` and `party`: no roll. It is recorded on its user, and
;   the scope decides whom it falls on: see `ba_hab_usar`.
;
; It goes before the execution order, which is how `SelectNextActor` calls
; it. If no living actor is left it stops and the remaining enemies are left
; without an action, which is the model's `break`: without that the two sides
; would roll a different number of times.
.proc ba_acciones_enemigas
.a8
.i16
    lda #BA_GRUPO_MAX
    sta BA_S0
otro:
    lda BA_S0
    cmp #BA_COMB_MAX
    bcc sigue
    rts
sigue:
    lda BA_S0
    jsr ba_vivo
    bne vive
    jmp siguiente
vive:
    ; The living actors, in a list, to pick one.
    lda #0
    jsr ba_vivos_del_lado
    lda BA_S1
    bne hay_actores
    rts                         ; nobody left to hit
hay_actores:
    lda BA_S0
    jsr ba_accion_enemiga
    sta BA_T1                   ; the action: a `k`, or attack, or nothing
    cmp #BA_EACC_NADA
    bne con_accion
    jmp siguiente
con_accion:
    cmp #BA_EACC_ATACAR
    beq a_un_actor
    jsr ba_ax
    lda f:hab_alcance, x
    cmp #BA_ALCANCE_ENEMIGO
    beq a_un_actor
    cmp #BA_ALCANCE_ALIADO
    beq a_uno_suyo
    lda BA_S0                   ; `self`, `enemies`, `party`: its user
    bra anotar
a_uno_suyo:
    lda #BA_GRUPO_MAX
    jsr ba_vivos_del_lado
a_un_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    dec a
    jsr ba_hasta
    tax
    sep #$20
.a8
    lda BA_CAND, x
anotar:
    sta BA_T0                   ; the chosen target
    lda BA_S0
    jsr ba_ax
    lda BA_T1
    sta BA_ACC_HAB, x           ; the `k`, which `ba_hab_usar` reads from here
    lda BA_S0
    asl a
    jsr ba_ax                   ; two bytes of action per combatant
    lda BA_T1
    cmp #BA_EACC_ATACAR
    beq es_ataque
    lda #BA_HABILIDAD
    bra orden_lista
es_ataque:
    lda #BA_ATACAR
orden_lista:
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACC
    jsr ba_ax
    lda BA_S0
    sta BA_EJEC, x
    inc BA_NACC
siguiente:
    inc BA_S0
    jmp otro
.endproc

; The living ones of a side —A8 = 0 the party, `BA_GRUPO_MAX` the troop— in
; `BA_CAND`, and how many in `BA_S1`. Clobbers `BA_S2`, A and X.
.proc ba_vivos_del_lado
.a8
.i16
    sta BA_S2
    clc
    adc #BA_GRUPO_MAX           ; the party is four places
    cmp #BA_GRUPO_MAX + 1
    bcc tope_listo
    lda #BA_COMB_MAX            ; and the troop, eight
tope_listo:
    sta BA_S2 + 1
    stz BA_S1
busca:
    lda BA_S2
    cmp BA_S2 + 1
    bcs listo
    jsr ba_vivo
    beq no_vive
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_CAND, x
    inc BA_S1
no_vive:
    inc BA_S2
    bra busca
listo:
    rts
.endproc

; What enemy A8 does: `batalla.accion_del_enemigo`, which is
; `SelectEnemyAiActionRpgRtCompat` with its list of `eacc_*`. Answers in A8
; the skill's `k`, `BA_EACC_ATACAR` or `BA_EACC_NADA`.
;
; 1. The possible ones are the attack and the skills its SP can pay for.
; 2. Each possible one weighs `max(0, rating - maximum + 10)`, and zero the one
;    that is not effective —bit 7 of `eacc_peso`—, which still counts toward
;    the maximum.
; 3. **With only one that has weight, no roll**; with more, `rand(0, sum - 1)`
;    and it is chosen by weight in list order.
;
; The weights go in `BA_HAB_LISTA`, which belongs to the skill-choosing screen
; and is rebuilt each time it opens: here the commands are already given.
; Clobbers `BA_S3` to `BA_S6`, `BA_T0`, `BA_T2`, A and X; not `BA_S0` or
; `BA_S1`.
.assert ACCIONES_MAX <= BA_HAB_MAX, error, "an enemy's actions do not fit in BA_HAB_LISTA"
.proc ba_accion_enemiga
.a8
.i16
    ; --- which enemy of the tables it is: `tropa_miembro` of its place ---
    sta BA_S3
    jsr ba_x
    lda BA_UNO + BA_NUMERO, x
    sta BA_T0                   ; its place in the troop
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    sta BA_S4                   ; the SP it has left
    sep #$20
.a8
    lda BA_TROPA_K
    jsr ba_ax
    lda f:tropa_ini, x
    clc
    adc BA_T0
    jsr ba_ax
    lda f:tropa_miembro, x
    jsr ba_ax
    lda f:enemigo_acc_n, x
    sta BA_S5                   ; how many actions
    lda f:enemigo_acc_ini, x
    sta BA_S5 + 1               ; where they start
    ; --- 1: the possible ones, with their raw weight, and the maximum ---
    stz BA_S6                   ; the maximum
    stz BA_T2                   ; which one it is at
posibles:
    lda BA_T2
    cmp BA_S5
    bcs vistas
    clc
    adc BA_S5 + 1
    jsr ba_ax
    lda f:eacc_peso, x
    sta BA_T0
    lda f:eacc_hab, x
    cmp #BA_EACC_ATACAR
    beq posible
    jsr ba_hab_costo            ; can its SP pay for it?
    sta BA_T0 + 1
    rep #$20
.a16
    lda BA_T0 + 1
    and #$00FF
    cmp BA_S4
    sep #$20
.a8
    beq posible
    bcc posible
    stz BA_T0                   ; they cannot: it weighs zero
    bra anotar_peso
posible:
    lda BA_T0
    and #$7F
    cmp BA_S6
    bcc anotar_peso
    sta BA_S6
anotar_peso:
    lda BA_T2
    jsr ba_ax
    lda BA_T0
    sta BA_HAB_LISTA, x
    inc BA_T2
    bra posibles
vistas:
    ; --- 2: the real weights, the sum, how many and the last one ---
    stz BA_S4                   ; the sum
    stz BA_S4 + 1               ; how many have weight
    stz BA_T2
pesos:
    lda BA_T2
    cmp BA_S5
    bcs pesadas
    jsr ba_ax
    lda BA_HAB_LISTA, x
    beq sin_peso                ; impossible
    bmi sin_peso8               ; not effective
    clc
    adc #10
    sec
    sbc BA_S6                   ; rating + 10 - maximum, which does not go
                                ; below 10 - 127
    bmi sin_peso8
    beq sin_peso8
    sta BA_HAB_LISTA, x
    clc
    adc BA_S4
    sta BA_S4
    inc BA_S4 + 1
    lda BA_T2
    sta BA_S3 + 1               ; the last one with weight
    bra siguiente_peso
sin_peso8:
    lda #0
    sta BA_HAB_LISTA, x
sin_peso:
siguiente_peso:
    inc BA_T2
    bra pesos
pesadas:
    lda BA_S4 + 1
    bne alguna
    lda #BA_EACC_NADA
    rts
alguna:
    cmp #1
    beq elegida                 ; only one: no roll
    ; --- 3: by weight ---
    rep #$20
.a16
    lda BA_S4
    and #$00FF
    dec a
    jsr ba_hasta
    sep #$20
.a8
    sta BA_T0                   ; `which`, less than the sum
    stz BA_T2
por_peso:
    lda BA_T2
    jsr ba_ax
    lda BA_T0
    sec
    sbc BA_HAB_LISTA, x
    bcc cae_aca                 ; `which` went negative
    sta BA_T0
    inc BA_T2
    bra por_peso
cae_aca:
    lda BA_T2
    sta BA_S3 + 1
elegida:
    lda BA_S3 + 1
    clc
    adc BA_S5 + 1
    jsr ba_ax
    lda f:eacc_hab, x
    rts
.endproc

; The execution order: `agi + rand(0, agi / 4 + 3)` for each one that acts,
; from highest to lowest and with a **stable** order, which is what
; `std::sort` does on a list that already comes stacked in the order it was
; pushed. It is `CreateExecutionOrder`. **One roll per action**, in that same
; order: first the party and then the troop.
.proc ba_orden_ejecucion
.a8
.i16
    lda #0
    sta BA_S0
tira:
    lda BA_S0
    cmp BA_NACC
    bcs tirados
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; its offset
    lda BA_UNO + BA_AGI, x
    lsr a
    lsr a
    clc
    adc #3
    jsr ba_hasta
    sta BA_T0
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_T0
    sta BA_UNO + BA_SORT, x
    sep #$20
.a8
    inc BA_S0
    bra tira
tirados:
    ; And the ordering, by insertion: there are twelve at most, and it stays
    ; **stable** if one only moves past the one above it when that one is
    ; strictly less.
    lda #1
    sta BA_S0
afuera:
    lda BA_S0
    cmp BA_NACC
    bcs ordenado
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    sta BA_S2                   ; the one being placed
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    sta BA_S3
    sep #$20
.a8
    lda BA_S0
    sta BA_S1
adentro:
    lda BA_S1
    beq put
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    cmp BA_S3
    sep #$20
.a8
    bcs put                   ; the one above is greater or equal: it stays
                                ; there
    lda BA_S1
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    inx
    sta BA_EJEC, x
    dec BA_S1
    bra adentro
put:
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_EJEC, x
    inc BA_S0
    bra afuera
ordenado:
    rts
.endproc

; --- the screen -----------------------------------------------------------
;
; Text on black, on the same grid of 32 by 28 cells as the equipment screen
; and the shop. The geometry comes from `tools/port/screens.py` and the
; converter emits the positions, so it is written **by only one of the two
; sides**. The enemies at the top, the party at the bottom, and the last line
; is either the command menu or the message's two lines.

; `BA_T1` = A16 + `BA_S0` times what a line measures: where line number
; `BA_S0` of the list starting at A16 begins.
.proc ba_fila
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
.proc ba_ir
.a16
.i16
    clc
    adc BA_T1
    sta eleg_tabla
    rts
.endproc

; A combatant's line: its name and its HP —an enemy's, only with
; `BA_HP_ENEMIGOS`—, in grey if it is dead.
; A8 = the combatant, `BA_T1` = where its line starts, and bit 0 of
; `BA_CONMAX` says whether the max HP go too —that is, whether it belongs to
; the party—.
.proc ba_renglon
.a8
.i16
    sta BA_S4
    ; A hidden enemy has no line until it appears: in RM2k it is not on the
    ; screen, and here its line is what says it is there.
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_OCULTO
    beq a_la_vista
    rts
a_la_vista:
    lda BA_S4
    jsr ba_vivo
    beq muerto
    lda #0
    bra variante
muerto:
    lda #1
variante:
    sta temp + 1
    lda BA_S4
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S5                   ; its offset, which `pant_texto` overwrites
    lda #BA_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_NOMBRE_ANCHO
    sta comp_dup + 3
    ldx BA_S5
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
.if ::BA_HP_ENEMIGOS = 0
    ; An enemy does not show its HP, as in RM2k: the line is only its name.
    ; With `[debug] enemy_hp` in the project file they show, for debugging.
    ; The `::` is not redundant: inside a `.proc`, `ca65` does not give a
    ; constant value to a bare name, which could be defined further down in
    ; the same `.proc`.
    lda BA_CONMAX
    and #$01
    bne con_hp
    rts
con_hp:
.endif
    ; "HP"
    rep #$20
.a16
    lda #BA_HP_DX
    jsr ba_ir
    sep #$20
.a8
    ldx #BA_TXT_HP
    jsl f:ba_t_texto
    ; and the number, three digits, capped at 999 as in the reference
    rep #$20
.a16
    lda #BA_HP_NUM_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HP, x
    cmp #1000
    bcc hp_cabe
    lda #999
hp_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    lda BA_CONMAX
    and #$01
    bne con_maximo
    rts
con_maximo:
    rep #$20
.a16
    lda #BA_BARRA_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$2F                    ; the slash between the HP and their maximum
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda #BA_HPMAX_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HPMAX, x
    cmp #1000
    bcc max_cabe
    lda #999
max_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    rts
.endproc

; The ">" cursor at the start of line `BA_T1`.
.proc ba_cursor
.a8
.i16
    stz temp + 1
    rep #$20
.a16
    lda #BA_CURSOR_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$3E                    ; the cursor
    jsl f:ba_t_glifo
    rts
.endproc

; A number with no leading spaces, in `BA_T0`, wherever `eleg_tabla` says. It
; is what easyrpg does when building the damage message, which sticks the
; number to the name without padding; `pant_numero` pads, so it has to be told
; the exact width.
.proc ba_numero_justo
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    sta comp_dup
    ldx #1
    cmp #10
    bcc ancho_listo
    ldx #2
    cmp #100
    bcc ancho_listo
    ldx #3
ancho_listo:
    sep #$20
.a8
    txa                         ; the width: with M at 8 only the low byte
                                ; travels
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_numero
    rts
.endproc

; The name of combatant A8 wherever `eleg_tabla` says, in full.
.proc ba_nombre
.a8
.i16
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; A game term —X already set— wherever `eleg_tabla` says, in full.
.proc ba_termino
.a8
.i16
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; The message's two lines, according to `BA_MTIPO`. Victory does not go
; through here: it goes in the party's lines, see `ba_vic_mensaje`. All the
; words come from the LDB —`attacking`, `enemy_damaged`, `defeat`...— and are
; put together as in `game_message_terms.cpp`: the name stuck to the term, and
; in the damage one the number in the middle. None of them is ours.
.proc ba_mensaje
.a8
.i16
    rep #$20
.a16
    lda #0
    sta BA_T1
    lda #BA_MSG_POS1
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MTIPO
    cmp #BA_MSG_ATAQUE
    beq ataque
    cmp #BA_MSG_DEFIENDE
    beq defiende
    cmp #BA_MSG_NO_HUYO
    beq no_huyo
    cmp #BA_MSG_HUYO
    beq huyo
    cmp #BA_MSG_ITEM
    beq usa_item
    cmp #BA_MSG_HAB
    beq usa_hab
    ldx #BA_TXT_DERROTA
    jmp solo
usa_hab:
    jmp habilidad
usa_item:
    jmp item
huyo:
    ldx #BA_TXT_HUYO
    jmp solo
no_huyo:
    ldx #BA_TXT_NO_HUYO
solo:
    jsr ba_termino
    rts
defiende:
    lda BA_MQUIEN
    jsr ba_nombre
    ldx #BA_TXT_DEFIENDE
    jsr ba_termino
    rts
ataque:
    lda BA_MQUIEN
    jsr ba_nombre
    ldx #BA_TXT_ATACA
    jsr ba_termino
    ; The second line: the result on the target.
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_nombre
    rep #$20
.a16
    lda BA_MDANO
    cmp #$FFFF
    sep #$20
.a8
    bne pego
    jmp fallo
pego:
    ; `<name> <damage> health lost.`
    lda #$20                    ; the space between the name and the number
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_MDANO
    sta BA_T0
    sep #$20
.a8
    jsr ba_numero_justo
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs es_enemigo
    ldx #BA_TXT_DANO_ACTOR
    bra dice
es_enemigo:
    ldx #BA_TXT_DANO_ENEMIGO
dice:
    jsr ba_termino
    rts
item:
    ; `<who> <item> used.`, which is
    ; `source.GetName() + " " + item.name + terms.use_item` from
    ; `GetItemStartMessage2k`.
    lda BA_MQUIEN
    jsr ba_nombre
    lda #$20
    jsl f:ba_t_glifo
    lda #255
    sta comp_dup + 3
    stz temp + 1
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
    jsl f:ba_t_texto
    ldx #BA_TXT_USO
    jsr ba_termino
    ; `<target> HP <n> Recovered`, which is `GetHpSpRecoveredMessage`.
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_nombre
    lda BA_MREVIVIO
    beq recupero
    ; Revived: `<target> has revived!`, the dead state's `message_recovery`,
    ; stuck to the name. RM2k does not show the HP one when it revives
    ; —`IsRevived` in the `ePreHp` of `ProcessBattleActionParamEffects`— but
    ; the one for the states it removed —`ProcessBattleActionStateEffects`—,
    ; and of those the port only knows the dead one.
    ldx #BA_TXT_REVIVIO
    jsr ba_termino
    rts
recupero:
    lda #$20
    jsl f:ba_t_glifo
    ldx #BA_TXT_HP
    jsr ba_termino
    lda #$20
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_MCURA
    sta BA_T0
    sep #$20
.a8
    jsr ba_numero_justo
    ldx #BA_TXT_RECUPERO
    jsr ba_termino
    rts
habilidad:
    ; `<who><using_message1>` on top and `<using_message2>` below, which is
    ; `GetSkillFirstStartMessage2k` and its sibling. Both lines come from the
    ; LDB, like everything this screen writes.
    lda BA_MQUIEN
    jsr ba_nombre
    lda #255
    sta comp_dup + 3
    stz temp + 1
    rep #$20
.a16
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_msg1, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_msg2, x
    tax
    sep #$20
.a8
    jsr ba_termino
    rts
fallo:
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs falla_enemigo
    ldx #BA_TXT_SIN_DANO_ACTOR
    bra falla_dice
falla_enemigo:
    ldx #BA_TXT_SIN_DANO_ENEMIGO
falla_dice:
    jsr ba_termino
    rts
.endproc
