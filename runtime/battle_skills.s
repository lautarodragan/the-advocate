.segment "FAR2"

; --- executing a skill ----------------------------------------------------
;
; `Game_BattleAlgorithm::Skill::vStart` and `vExecute`. **The order in which
; it consumes randomness is the contract with `use_skill` in
; `rm2k-snes-battle`**: a switch skill finishes before any roll;
; then comes the critical, which is always rolled even if the chance is zero;
; then the variance; and then one roll against the hit rate for each thing the
; skill affects, in the order HP, SP, attack, defense, spirit and agility.

; `Algo::VarianceAdjustEffect`: A16 = the effect, `BA_S5` = the variance.
;
;     adj = max(1, var * effect / 10); effect += rand(0, adj) - adj / 2
;
; **It only rolls if the variance and the effect are greater than zero**,
; which is easyrpg's `if`: without that condition the two sides would drift
; out of phase on the next roll every time a skill that does no damage went
; through here.
;
; The normal attack has its own written inside `ba_attack` with the variance
; at four; this one was split out for the skills, which carry their own in the
; LDB.
.proc ba_variance
.a16
.i16
    sta BA_T0
    bmi no_roll
    beq no_roll
    sep #$20
.a8
    lda BA_S5
    beq no_variance
    sta BA_T2
    rep #$20
.a16
    lda BA_T0
    jsr ba_mul                  ; the variance times the effect
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne adjust_ready
    lda #1                      ; `max(1, ...)`
adjust_ready:
    sta BA_T1
    jsr ba_until                ; A16 is still the adjustment
    clc
    adc BA_T0
    sta BA_T0
    lda BA_T1
    lsr a
    sta BA_T1
    lda BA_T0
    sec
    sbc BA_T1
    sta BA_T0
no_roll:
    lda BA_T0
    rts
no_variance:
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    rts
.endproc

; A parameter modifier moves by `BA_MEFFECT` and the effective parameter is
; recomputed: `CanChangeAtkModifier` and its siblings, plus `AdjustParam`.
;
;   BA_S4 = the target's offset inside `BA_ONE`
;   BA_S5 = the modifier's, BA_S6 = the base's, BA_T1 = the effective one's
.proc ba_mod
.a8
.i16
    rep #$20
.a16
    lda BA_S4
    clc
    adc BA_S5
    tax
    lda BA_ONE, x
    clc
    adc BA_MEFFECT
    sta temp                    ; the modifier being asked for
    lda BA_S4
    clc
    adc BA_S6
    tax
    lda BA_ONE, x
    sta BA_T0                   ; the base parameter. **The two scratch ones are
                                ; `BA_T0` and `BA_T2` and not `BA_S2` and
                                ; `BA_S3`**: the caller keeps in `BA_S3` what
                                ; the skill touches and in `BA_S0` its hit
                                ; rate, and needs them on all four passes
    ; The upper cap is the base, and the lower one its half with a minus sign.
    ; The numbers in this game are in the hundreds, so the `bmi` on the
    ; subtraction is enough: nothing comes close to the 32768 where it would
    ; wrap around.
    lda temp
    sec
    sbc BA_T0
    bmi up_ok
    lda BA_T0
    sta temp
up_ok:
    lda BA_T0
    lsr a
    eor #$FFFF
    inc a
    sta BA_T2                   ; -(base / 2)
    lda temp
    sec
    sbc BA_T2
    bpl down_ok
    lda BA_T2
    sta temp
down_ok:
    lda BA_S4
    clc
    adc BA_S5
    tax
    lda temp
    sec
    sbc BA_ONE, x
    pha                         ; how much it really moved, for its line
    lda temp
    sta BA_ONE, x               ; the new modifier
    clc
    adc BA_T0                   ; base + modifier
    bmi to_one
    cmp #1
    bcs not_zero
to_one:
    lda #1
    bra effective_ready
not_zero:
    cmp #(BA_PARAM_MAX + 1)
    bcc effective_ready
    lda #BA_PARAM_MAX
effective_ready:
    sta BA_T2
    lda BA_S4
    clc
    adc BA_T1
    tax
    lda BA_T2
    sta BA_ONE, x
    ; Its line, if it moved: `GetParameterChangeMessage`. Which parameter is
    ; which modifier, `BA_MATK` to `BA_MAGI`, a word apart.
    pla
    beq unmoved                 ; goombario: pull-branch: what was pulled is how much it moved
    pha
    lda BA_S5
    lsr a
    sec
    sbc #(BA_MATK / 2 - BA_RES_ATK)
    tay
    pla
    jsr ba_res_add
unmoved:
    sep #$20
.a8
    rts
.endproc

; Turns on the switch in `BA_T0`, which is the LDB's `switch_id` as is, like
; `item_switch` does with its own. It does not call `set_switch`: that lives
; in bank 0 and the battle runs with the data bank at $7E, so the mask is
; built here with a shift instead of being read from a cartridge table.
.proc ba_switch
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    lsr a
    lsr a
    lsr a
    tax                         ; which byte of the bitmap
    lda BA_T0
    and #$0007
    tay                         ; and which bit
    sep #$20
.a8
    lda #1
runs:
    cpy #0
    beq mask_list
    asl a
    dey
    bra runs
mask_list:
    ora f:switches, x
    sta f:switches, x
    lda #1
    sta refresh                 ; the pages that ask for it may change
    rts
.endproc

; The effect of skill `BA_MSKILL` from `BA_MWHO` on `BA_MTGT`, **without the
; variance**: `Algo::CalcSkillEffect`. Leaves the result in `BA_MEFFECT`,
; already clamped below at zero.
.proc ba_skill_effect
.a8
.i16
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
    ; the skill's `k`, times two for the word tables
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_power, x
    sta BA_S2                   ; the effect accumulator
    sep #$20
.a8
    ; + physical_rate * atk / 20
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_phys, x
    sta BA_T2
    beq no_physical
    ldx BA_S0
    rep #$20
.a16
    lda BA_ONE + BA_ATK, x
    jsr ba_mul
    sta temp
    lda #20
    sta temp + 2
    jsr ba_div
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
no_physical:
    ; + magical_rate * spi / 40
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_mag, x
    sta BA_T2
    beq no_magic
    ldx BA_S0
    rep #$20
.a16
    lda BA_ONE + BA_SPI, x
    jsr ba_mul
    sta temp
    lda #40
    sta temp + 2
    jsr ba_div
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
no_magic:
    ; Against an enemy and without `ignore_defense`, its defense and spirit
    ; are subtracted. `SkillTargetsEnemies` is bit 6 of `skill_affects` and bit 7
    ; is `ignore_defense`.
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_affects, x
    sta BA_S3
    and #$40
    beq no_remain
    lda BA_S3
    and #$80
    bne no_remain
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_phys, x
    sta BA_T2
    beq no_remain_phys
    ldx BA_S1
    rep #$20
.a16
    lda BA_ONE + BA_DEF, x
    jsr ba_mul
    sta temp
    lda #40
    sta temp + 2
    jsr ba_div
    sta BA_T0
    lda BA_S2
    sec
    sbc BA_T0
    sta BA_S2
    sep #$20
.a8
no_remain_phys:
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_mag, x
    sta BA_T2
    beq no_remain
    ldx BA_S1
    rep #$20
.a16
    lda BA_ONE + BA_SPI, x
    jsr ba_mul
    sta temp
    lda #80
    sta temp + 2
    jsr ba_div
    sta BA_T0
    lda BA_S2
    sec
    sbc BA_T0
    sta BA_S2
    sep #$20
.a8
no_remain:
    rep #$20
.a16
    lda BA_S2
    bpl no_negative
    lda #0                      ; `max(0, effect)`
no_negative:
    ; And through the target's ranks in the skill's attributes, before the
    ; critical, as `CalcSkillEffect`: see battle_attributes.s.
    jsr ba_attr_skill
    sta BA_MEFFECT
    sep #$20
.a8
    ; The critical, which for an LDB skill **always comes out no**: the chance
    ; `CalcCriticalHitChance` receives is `easyrpg_critical_hit_chance`, which
    ; is 0 and not -1. The roll is made anyway, because otherwise the two
    ; sides would drift out of phase.
    lda #0
    jsr ba_pct
    beq no_critical
    rep #$20
.a16
    lda BA_MEFFECT
    sta temp
    asl a
    clc
    adc temp                    ; times three
    sta BA_MEFFECT
    sep #$20
.a8
no_critical:
    rts
.endproc

; The target's HP move by `BA_MEFFECT`. Healing does not kill —the
; `max(-(cur_hp - 1), hp_effect)` of `vExecute`— and damage is halved for one
; who is defending, with C++ division, which **truncates toward zero**.
.proc ba_skill_hp
.a8
.i16
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    lda BA_MEFFECT
    bmi does_damage
    sta BA_T0
    bra applies
does_damage:
    sep #$20
.a8
    ldx BA_S4
    lda BA_ONE + BA_FLAGS, x
    and #BAF_DEF
    beq no_defense
    rep #$20
.a16
    lda BA_MEFFECT
    eor #$FFFF
    inc a
    lsr a
    eor #$FFFF
    inc a                       ; half, truncated toward zero
    sta BA_T0
    bra applies
no_defense:
.a8
.i16
    rep #$20
.a16
    lda BA_MEFFECT
    sta BA_T0
applies:
.a16
.i16
    ldx BA_S4
    lda BA_ONE + BA_HP, x
    pha                         ; the HP before
    clc
    adc BA_T0
    bmi in_zero
    cmp BA_ONE + BA_HPMAX, x
    bcc fits
    lda BA_ONE + BA_HPMAX, x
    bra fits
in_zero:
    lda #0
fits:
    sta BA_ONE + BA_HP, x
    ; Its line: `GetDamagedMessage` with the effect as it was asked for —at
    ; zero, `GetUndamagedMessage`— if the skill targets enemies or the effect
    ; came out negative; if not, what it really recovered —`ApplyHpEffect`
    ; in `ePreHp`, zero at full HP—, and nothing for a heal of nothing.
    sec
    sbc 1, s
    sta 1, s                    ; what it really moved, over the HP before
    sep #$20
.a8
    lda BA_S3
    and #$40
    rep #$20
.a16
    bne a_damage
    lda BA_T0
    bmi a_damage
    beq said
    lda 1, s
    ldy #BA_RES_HP
    bra say
a_damage:
    lda BA_T0
    eor #$FFFF
    inc a
    ldy #BA_RES_DAMAGE
say:
    jsr ba_res_add
said:
    pla
    ldx BA_S4
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    bne alive
    ; "If target will be killed, no further affects are applied":
    ; `ba_skill_one` stops here. See `ba_res_killed`.
    inc .loword(ba_res_killed)
    rts
alive:
    ; Damage that did not kill releases what a hit releases, at
    ; `physical_rate * 10` percent —`BattlePhysicalStateHeal` in `vExecute`—:
    ; only a skill that targets enemies, bit 6 of `BA_S3`. See
    ; battle_states.s.
    lda BA_S3
    and #$40
    beq killed
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_phys, x
    sta BA_T0
    asl a
    asl a
    adc BA_T0                   ; times five: the carry is clear, it is at
    asl a                       ; most ten. And times two
    sta .loword(ba_st_rate)
    lda BA_MTGT
    jsr ba_st_by_damage
killed:
    rts
.endproc

; And the SP, the same but with no defense that counts. None of the seven uses
; it; it is here because `vExecute` does it and because the roll before it has
; already been made.
.proc ba_skill_sp
.a8
.i16
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    pha                         ; the SP before
    clc
    adc BA_MEFFECT
    bmi sp_in_zero
    cmp BA_ONE + BA_SPMAX, x
    bcc sp_fits
    lda BA_ONE + BA_SPMAX, x
    bra sp_fits
sp_in_zero:
    lda #0
sp_fits:
    sta BA_ONE + BA_SP, x
    ; Its line, if they moved: `GetSpRecoveredMessage` or
    ; `GetSpReduceMessage`.
    sec
    sbc 1, s
    tay
    pla
    tya                         ; the flags from what moved, not from the pull
    beq unmoved
    ldy #BA_RES_SP
    jsr ba_res_add
unmoved:
    sep #$20
.a8
    rts
.endproc

; The skill `BA_MWHO` chose, on `BA_MTGT`. Leaves the message ready, and
; its result lines in the queue: see `ba_res_add`.
.proc ba_skill_use
.a8
.i16
    stz .loword(ba_res_n)
    stz .loword(ba_res_i)
    lda BA_MWHO
    jsr ba_ax
    lda BA_ACC_SKILL, x
    sta BA_MSKILL
    ; --- `vStart`: the cost, before anything and without rolling ---
    ;
    ; None for a special item's: `vStart` with an item spends the item, which
    ; `ba_record_skill` did on choosing it. Only an actor's can be one.
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcs pays
    jsr ba_ax
    lda f:ba_item_cast, x
    bne paid
pays:
    lda BA_MSKILL
    jsr ba_skill_cost
    sta BA_T2
    stz BA_T2 + 1               ; the subtraction below is 16 bits and
                                ; `skill_sp` is 8: without this the high byte
                                ; is whatever the last one through here left,
                                ; and SP ended up at zero
    lda BA_MWHO
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_ok
    lda #0                      ; cannot happen: without SP it is not chosen
sp_ok:
    sta BA_ONE + BA_SP, x
    sep #$20
.a8
paid:
    ; --- a switch skill turns on its switch and does nothing else ---
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_type, x
    cmp #BA_SKILL_TYPE_SWITCH
    bne not_switch
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_switch, x
    sta BA_T0
    lda #0
    sta BA_MEFFECT
    sep #$20
.a8
    jmp ba_switch
not_switch:
    ; --- on whom: `skill_targets` ---
    ;
    ; `enemy` and `ally` on the chosen one, `self` on the user, and `enemies`
    ; and `party` on each living one on the opposing side or its own, in
    ; screen order and **each with its own rolls** and its own lines.
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_scope, x
    cmp #BA_SCOPE_ONE
    bne not_one
    lda BA_MWHO
    sta BA_MTGT
    jmp ba_skill_one
not_one:
    cmp #BA_SCOPE_ENEMIES
    beq many_targets
    cmp #BA_SCOPE_PARTY
    beq many_targets
    jmp ba_skill_one
many_targets:
    ; The side: the opposing one with `enemies`, its own with `party`. That
    ; the source is in the party is `BA_MWHO < BA_PARTY_MAX`.
    ldy #0                      ; 0 the party, 1 the troop
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcc from_party
    iny
from_party:
    lda f:skill_scope, x
    cmp #BA_SCOPE_ENEMIES
    bne side_ready
    tya
    eor #1
    tay
side_ready:
    lda #0
    cpy #0
    beq first_ready
    lda #BA_PARTY_MAX
first_ready:
    sta f:BA_SKILL_I
other_target:
    lda f:BA_SKILL_I
    jsr ba_alive
    beq no_falls
    lda f:BA_SKILL_I
    sta BA_MTGT
    jsr ba_skill_one
no_falls:
    lda f:BA_SKILL_I
    inc a
    sta f:BA_SKILL_I
    cmp #BA_PARTY_MAX
    beq all_ready               ; the party ends where the troop begins
    cmp #BA_COMB_MAX
    bcc other_target
all_ready:
    rts
.endproc

; `vExecute` on target `BA_MTGT`: the effect, the variance and the hit rolls.
; Called by `ba_skill_use`, once or once per target.
.proc ba_skill_one
.a8
.i16
    stz .loword(ba_res_ok)
    stz .loword(ba_res_killed)
    jsr ba_skill_effect
    ; the variance, with the skill's `variance`
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_var, x
    sta BA_S5
    rep #$20
.a16
    lda BA_MEFFECT
    jsr ba_variance
    ; the damage cap, which is the same as an attack's
    cmp #(BA_DAMAGE_MAX + 1)
    bcc effect_fits
    lda #BA_DAMAGE_MAX
effect_fits:
    sta BA_MEFFECT
    sep #$20
.a8
    ; If it targets enemies the effect is negative: `SetIsPositive` is
    ; `SkillTargetsAllies`, and `vExecute` flips the sign when it is not.
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_affects, x
    sta BA_S3                   ; what it touches, which is not read again
    and #$40
    beq is_positive
    rep #$20
.a16
    lda BA_MEFFECT
    eor #$FFFF
    inc a
    sta BA_MEFFECT
    sep #$20
.a8
is_positive:
    ; the hit rate, which all seven carry at 100
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_hit, x
    sta BA_S0                   ; the hit rate, which survives the `jsr`s
    ; --- the HP ---
    lda BA_S3
    and #$01
    beq no_hp
    lda BA_S0
    jsr ba_pct
    beq no_hp
    jsr ba_skill_hp
    ; "If target will be killed, no further affects are applied": `vExecute`
    ; returns, and from here nothing is rolled, applied or written. It
    ; returns with the damage's line, a success.
    lda .loword(ba_res_killed)
    beq no_hp
    jmp returned
no_hp:
    ; --- the SP ---
    ;
    ; None of the seven the intro party knows touches them, **but the roll
    ; happens anyway**: `vExecute` makes it and removing it would put the
    ; randomness out of phase.
    lda BA_S3
    and #$02
    beq no_sp
    lda BA_S0
    jsr ba_pct
    beq no_sp
    jsr ba_skill_sp
no_sp:
    ; "!IsPositive() && !IsSuccess() && (affect_hp || affect_sp)": one that
    ; targets enemies and did nothing to the HP or the SP it touches has
    ; failed, and `vExecute` returns: neither the parameters nor the
    ; attribute ranks are rolled or applied —as `skill_rolls` in
    ; rm2k-snes-battle's simulate.rs—, and the failure's line is written.
    lda BA_S3
    and #$43
    cmp #$41
    bcc goes_on                 ; not against enemies, or not HP nor SP
    lda .loword(ba_res_ok)
    bne goes_on
    jmp returned
goes_on:
    ; --- the four parameters, in `vExecute`'s order ---
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    sep #$20
.a8
    lda BA_S3
    and #$04
    beq no_atk
    lda BA_S0
    jsr ba_pct
    beq no_atk
    rep #$20
.a16
    lda #BA_MATK
    sta BA_S5
    lda #BA_BATK
    sta BA_S6
    lda #BA_ATK
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
no_atk:
    lda BA_S3
    and #$08
    beq no_def
    lda BA_S0
    jsr ba_pct
    beq no_def
    rep #$20
.a16
    lda #BA_MDEF
    sta BA_S5
    lda #BA_BDEF
    sta BA_S6
    lda #BA_DEF
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
no_def:
    lda BA_S3
    and #$10
    beq no_spi
    lda BA_S0
    jsr ba_pct
    beq no_spi
    rep #$20
.a16
    lda #BA_MSPI
    sta BA_S5
    lda #BA_BSPI
    sta BA_S6
    lda #BA_SPI
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
no_spi:
    lda BA_S3
    and #$20
    beq no_agi
    lda BA_S0
    jsr ba_pct
    beq no_agi
    rep #$20
.a16
    lda #BA_MAGI
    sta BA_S5
    lda #BA_BAGI
    sta BA_S6
    lda #BA_AGI
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
no_agi:
    ; And the attribute ranks it shifts: see battle_attributes.s.
    jsr ba_attr_shift
returned:
    ; Nothing done is a failure, with its line: `ProcessBattleActionFailure`.
    lda .loword(ba_res_ok)
    bne succeeded
    rep #$20
.a16
    lda #0
    ldy #BA_RES_MISS
    jsr ba_res_add
    sep #$20
.a8
succeeded:
    ; And what a condition halves, halved again: `ba_mod` does not know.
    lda BA_MTGT
    jmp ba_st_params_held
.endproc

; --- what a skill wrote on each target -------------------------------------
;
; `Scene_Battle_Rpg2k` writes, under a skill's using lines, a line for each
; thing it did on each target —`ProcessBattleActionDamage` and
; `ProcessBattleActionParamEffects`—, or the failure's when it did nothing.
; `ba_skill_one` leaves them here while it executes, and `ba_execute` shows
; them one message each, after the using one: see `result` in `ba_message`.
; The model says the same lines, `results` in rm2k-snes-battle's answer.
;
; One entry per line: whom, what —`BA_RES_*`— and the number. A target gets
; six at most, the HP and the SP and the four parameters.
BA_RES_MISS   = 0               ; `GetSkillFailureMessage`, no number
BA_RES_DAMAGE = 1               ; `GetDamagedMessage`, `GetUndamagedMessage` at 0
BA_RES_HP     = 2               ; `GetHpRecoveredMessage`, what was recovered
BA_RES_SP     = 3               ; `GetSpRecoveredMessage`, or `GetSpReduceMessage`
BA_RES_ATK    = 4               ; `GetParameterChangeMessage`, signed: attack,
BA_RES_DEF    = 5               ; defense,
BA_RES_SPI    = 6               ; spirit
BA_RES_AGI    = 7               ; and agility, as the modifiers go
BA_RES_MAX    = BA_COMB_MAX * 6
.assert BA_MDEF = BA_MATK + 2 && BA_MSPI = BA_MATK + 4 && BA_MAGI = BA_MATK + 6, error, "ba_mod tells the parameter by its modifier's place"
.pushseg
.segment "FARBSS"
ba_res_who:   .res BA_RES_MAX
ba_res_what:  .res BA_RES_MAX
ba_res_value: .res 2 * BA_RES_MAX
ba_res_n:     .res 1            ; how many there are
ba_res_i:     .res 1            ; how many `ba_execute` has shown
ba_res_show:  .res 1            ; whether the message on screen is one
ba_res_ok:    .res 1            ; whether this target got something:
                                ; `SetIsSuccess`
ba_res_killed: .res 1           ; whether the skill's damage killed this
                                ; target, where `vExecute` returns
.popseg

; A line for `BA_MTGT`: Y what, A16 the number, and every one is a success.
; Comes and goes in A16; clobbers X.
.proc ba_res_add
.a16
.i16
    pha
    sep #$20
.a8
    inc .loword(ba_res_ok)
    lda .loword(ba_res_n)
    cmp #BA_RES_MAX
    bcs full
    inc .loword(ba_res_n)
    jsr ba_ax
    lda BA_MTGT
    sta .loword(ba_res_who), x
    tya
    sta .loword(ba_res_what), x
    rep #$20
.a16
    txa
    asl a
    tax
    lda 1, s
    sta .loword(ba_res_value), x
full:
    rep #$20
.a16
    pla
    rts
.endproc

; --- skills in battle ------------------------------------------------------
;
; `Game_BattleAlgorithm::Skill` with what this port knows how to do. What each
; actor knows at the start, how much it costs and how much it does **is not
; decided here**: it comes from `skills_of`, the skill's `sp_cost` and
; `skill_effect` in `rm2k-snes-battle`, which is the model with which
; `abl/tests/rpgmaker/test_battle.py`, in the-advocate-ports, predicts the exact number, and the
; converter emits it in `skill_pair_*` and `skill_*`. What it knows **now** is
; `FAR_SKILL`, which `ChangeSkills` changes.

; A8 = the LDB actor number of combatant `BA_ACTOR`. It is what indexes
; `skill_pair_init`, `skill_pair_n` and `actor_command_txt`, which are by actor number
; and not by place in the party.
.proc ba_actor_ldb
.a8
.i16
    lda BA_ACTOR
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rts
.endproc

; The skill list of the actor giving commands: how many in `BA_SKILL_N`, and
; the page the window shows —from row `BA_SKILL_TOP`— into `BA_SKILL_LIST`.
; They are its `FAR_SKILL` pairs with the bit set —what it knows **now**, which
; `ChangeSkills` changes— that the battle knows how to offer, that is, with a
; `k` in `skill_pair_k`. An actor's pairs are contiguous and in skill-number
; order, so the list comes out in `LearnSkill` order.
;
; It walks all the pairs every time, to count them, and keeps only the page:
; the whole list would not fit in `FAR_BATTLE`, and everything that reads it
; —the screen, the description, A— looks at the visible page. Up to 2026-10-04
; it kept the first 16 and the window did not scroll.
;
; `BA_SKILL_N` stops at 254 so that `BA_SKILL_SEL` plus a row still fits in a
; byte; no actor of a game comes near that.
; Clobbers `BA_S1`, `BA_S2`, `BA_T0` and X.
;
; **The walk is shared with the pause menu's skills screen** since
; 2026-10-12: `ba_skill_walk` takes the LDB actor in A, and the page is
; `ba_skill_rows` rows —`ba_skill_places` places—, which each caller sets:
; the battle's five here, the screen's eight in `skills_screen.s`.
.assert BA_SKILL_ROWS * BA_SKILL_COLUMNS <= BA_SKILL_MAX, error, "a page of the skill list does not fit in BA_SKILL_LIST"
.assert BA_SKILL_COLUMNS = 2, error, "the skill list takes a row as two places: see `ba_skill_place`"
.pushseg
.segment "FARBSS"
ba_skill_rows:   .res 1         ; the visible page's rows
ba_skill_places: .res 1         ; and its places, twice as many
.popseg
.proc ba_skill_list
.a8
.i16
    lda #BA_SKILL_ROWS
    sta .loword(ba_skill_rows)
    lda #(BA_SKILL_ROWS * BA_SKILL_COLUMNS)
    sta .loword(ba_skill_places)
    jsr ba_actor_ldb
.endproc
; The list of LDB actor A, with the data bank at $7E: see above.
.proc ba_skill_walk
.a8
.i16
    stz BA_SKILL_N
    jsr ba_ax
    lda f:skill_pair_n, x
    beq ready
    sta BA_S1                   ; how many pairs it has left to look at
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:skill_pair_init, x
    sta BA_S2                   ; the slot of the pair being looked at
    sep #$20
.a8
other:
    lda BA_SKILL_N
    cmp #254
    bcs ready
    rep #$20
.a16
    lda BA_S2
    and #$0007
    tax
    sep #$20
.a8
    lda f:mask, x
    sta BA_T0                   ; its bit
    rep #$20
.a16
    lda BA_S2
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_SKILL, x
    and BA_T0
    beq next                    ; it does not know it
    ldx BA_S2
    lda f:skill_pair_k, x
    cmp #$FF
    beq next                    ; it knows it and the battle does not offer it
    pha
    lda BA_SKILL_N
    jsr ba_skill_place
    bcs off_page                ; it is in the list, but not in the window
    jsr ba_ax
    pla
    sta BA_SKILL_LIST, x
    bra counted
off_page:
    pla
counted:
    inc BA_SKILL_N
next:
    rep #$20
.a16
    inc BA_S2
    sep #$20
.a8
    dec BA_S1
    bne other
ready:
    rts
.endproc

; The `k` at place A8 of the whole list, which has to be in the window: the
; cursor always is —see `ba_skill_see`— and the screen only draws those. Only
; A and X.
.proc ba_skill_from_list
.a8
.i16
    jsr ba_skill_place
    jsr ba_ax
    lda BA_SKILL_LIST, x
    rts
.endproc

; Place A8 of the whole list, as a place on the visible page: A8 minus two per
; row above the window. C=1 if it is not on the page —above or below—, and
; then A8 is garbage. Only A.
.proc ba_skill_place
.a8
.i16
    sec
    sbc BA_SKILL_TOP
    bcc outside
    sec
    sbc BA_SKILL_TOP            ; two per row: BA_SKILL_COLUMNS, asserted above
    bcc outside
    cmp .loword(ba_skill_places)
    rts                         ; C=1 past the last visible row
outside:
    sec
    rts
.endproc

; Makes the place the cursor marks visible, the way RM2k does it
; —`Window_Selectable::UpdateCursorRect`—: if its row is above the window, the
; window starts at it; if it is below, it ends at it. So it scrolls just
; enough, one row at a time going up or down one by one, and the cursor stays
; at the edge. Only A.
.proc ba_skill_see
.a8
.i16
    lda BA_SKILL_SEL
    lsr a                       ; its row: two columns
    cmp BA_SKILL_TOP
    bcs not_above
    sta BA_SKILL_TOP
    rts
not_above:
    inc a                       ; its row minus the page's rows, plus one
    sec
    sbc .loword(ba_skill_rows)
    bcc fits                    ; within the first page
    cmp BA_SKILL_TOP
    bcc fits
    beq fits
    sta BA_SKILL_TOP
fits:
    rts
.endproc

; The SP cost of the `k` in A8, in A8. `Algo::CalcSkillCost`: the plain
; `sp_cost`, which is what RM2k does.
.proc ba_skill_cost
.a8
.i16
    jsr ba_ax
    lda f:skill_sp, x
    rts
.endproc

; Whether combatant `BA_ACTOR` can use the `k` in A8: Z=0 if so. The battle
; has to let it be chosen at all —`skill_in_battle`, 0 for a switch skill for
; the map—, and it has to pay for it and, an actor's skill with a physical
; attribute, hold a weapon that carries it —see `ba_weapons_allow`—. **It
; does not use the flag a `pl*` leaves**: the usual trap. The `k` waits on
; the stack and not in a `BA_T*`: the list's row keeps where its line starts
; in `BA_T1` across this.
.proc ba_skill_reaches
.a8
.i16
    pha                         ; the k
    jsr ba_skill_cost           ; leaves X on the k's row
    sta BA_T2
    lda f:skill_in_battle, x    ; `Algo::IsSkillUsable` in battle
    beq no
    lda BA_ACTOR
    jsr ba_x
    rep #$20
.a16
    lda BA_T2
    and #$00FF
    cmp BA_ONE + BA_SP, x
    sep #$20
.a8
    beq if                      ; exactly as many as it has is enough
    bcs no
if:
    pla                         ; the k, into Y
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda BA_ONE + BA_NUMBER, x   ; the skill list is only ever an actor's
    jmp ba_weapons_allow
no:
    pla
    lda #0
    rts
.endproc

; The whole screen, written to the text layer —see `text_layer.s`— and the
; windows it goes in, which `ba_win_tick` puts up in step with it.
;
; It is RM2k's: the scene on top with nothing over it and every window in
; the band below —see `screen.rs` in `rm2k-snes-battle`—, so what shows
; there depends only on the mode. The party with the commands on its right,
; the System's bar on who is giving commands or whom an item goes to and on
; the command; the enemies to attack over the party's window; an item or a
; skill list, with its description in a window on top; and the battle's
; message, a page's or the victory's, alone. Until 2026-10-04 the enemies'
; names went over the scene and the party's lines and the commands under
; it, always, with ">" for a cursor and no windows.
;
; `BA_WIN_KEY` says the windows: the layout, set A's bar and set B's —$FF
; none— and whether the description's window is on top.
.proc ba_compose
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_clear
    lda #BA_LAYOUT_COMMAND
    sta BA_WIN_KEY
    lda #$FF
    sta BA_WIN_KEY + 1
    sta BA_WIN_KEY + 2
    stz BA_WIN_KEY + 3
    lda BA_MODE
    cmp #BA_M_SKILL
    bne :+
    jmp ba_skill_window
:   cmp #BA_M_ITEM
    bne :+
    jmp ba_item_window
:   cmp #BA_M_TARGET
    bne :+
    jsr ba_commands
    jmp ba_target_window
:   cmp #BA_M_MESSAGE
    beq message
    cmp #BA_M_END
    beq message
    cmp #BA_M_PAGE
    bne commands
    ; A troop page's message, in the message window; with none, the page is
    ; running —a `ShakeScreen`, a `Wait`— and the message window is empty,
    ; which is what RM2k shows between the commands and the actions. Until
    ; 2026-10-04 it showed the commands, with the skill command of an actor
    ; past the party's last.
    lda #BA_LAYOUT_WIDE
    sta BA_WIN_KEY
    rep #$20
.a16
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne page_message
    rts
page_message:
    jmp ba_page_message
message:
    lda #BA_LAYOUT_WIDE
    sta BA_WIN_KEY
    jsr ba_vic_on_screen
    beq not_victory
    jmp ba_vic_message
not_victory:
    jsl f:ba_message            ; in `FAR3`: see battle_message.s
    rts
commands:
    ; The bars: on the command while choosing one or whom it goes to, and on
    ; the actor giving it or the one it goes to.
    lda BA_MODE
    cmp #BA_M_COMMAND
    bne not_command
    lda BA_ACTOR
    sta BA_WIN_KEY + 1
    lda BA_COMMAND
    sta BA_WIN_KEY + 2
    bra bars_set
not_command:
    cmp #BA_M_ACTOR
    bne bars_set
    lda BA_ITEM_TGT
    sta BA_WIN_KEY + 1
    lda BA_COMMAND
    sta BA_WIN_KEY + 2
bars_set:
    jsr ba_commands
    jmp ba_party
.endproc

; How many commands this battle has: the five, or four without Escape in
; one that cannot be escaped from —see `BA_CAN_FLEE`—. In A8.
.assert BA_COMMAND_ESCAPE = BA_COMMANDS_N - 1, error, "Escape is the last command: ba_commands_n leaves it out by counting one less"
.proc ba_commands_n
.a8
.i16
    lda BA_CAN_FLEE
    beq without
    lda #BA_COMMANDS_N
    rts
without:
    lda #(BA_COMMANDS_N - 1)
    rts
.endproc

; The commands, one per line in their window on the right. In gray while
; something else is being chosen —the menu is no longer in charge— and
; always the one that is not implemented, which is what the pause menu does
; with its own. The bar is the window's: see `ba_compose`.
.proc ba_commands
.a8
.i16
    stz BA_S0
command:
    jsr ba_commands_n
    cmp BA_S0
    beq ready
    bcs has_command
ready:
    rts
has_command:
    rep #$20
.a16
    lda #BA_COMMAND_POS0
    jsr ba_row
    sep #$20
.a8
    lda BA_MODE
    cmp #BA_M_COMMAND
    bne in_gray
    lda BA_S0
    jsr ba_ax
    lda f:ba_command_gray, x
    bne in_gray
    ; And the skill command of an actor who knows none —Talan, who is level
    ; 1— also goes in gray, like the pause menu with what leads nowhere.
    lda BA_S0
    cmp #BA_COMMAND_SKILL
    bne no_gray_command
    jsr ba_skill_list           ; what it knows now: see `FAR_SKILL`
    lda BA_SKILL_N
    beq in_gray
no_gray_command:
    lda #0
    bra sets_variant
in_gray:
    lda #1
sets_variant:
    sta BA_S1
    rep #$20
.a16
    lda #BA_COMMAND_DX
    jsr ba_go
    sep #$20
.a8
    lda BA_S1
    sta temp + 1
    lda #BA_COMMAND_CELLS
    sta comp_dup + 3
    ; **Each actor's commands are its own**, five words per actor in
    ; `actor_command_txt`, by actor number: the second says the `skill_name`
    ; of the actor giving commands —"AgentTrain", "Telepathy", "Slicing"—,
    ; which is `Game_Actor::GetSkillName`, and a 2003 game names all five
    ; from each actor's battle commands —Zounds' Kazar uses items with
    ; "Tirar-Usar"—: see `command_names` in rm2k-snes-battle's rules. Until
    ; 2026-10-20 the other four came from a fixed table.
    ;
    ; **Two bytes wide**, like `enemy_txt`: a text index does not fit in
    ; one. With the 29 maps of `abl` the battle texts start at 273, so the
    ; one-byte table that was here until 2026-09-14 truncated them to 17, 18,
    ; 19 and 32, which are lines of an item's description: the menu drew
    ; four long texts, one on top of the other.
.assert BA_COMMANDS_N = 5, error, "actor_command_txt has five words per actor: the times ten below"
    jsr ba_actor_ldb
    rep #$20
.a16
    and #$00FF
    asl a
    sta BA_T0
    asl a
    asl a
    clc
    adc BA_T0                   ; the actor times ten: five commands of two
    sta BA_T0
    lda BA_S0
    and #$00FF
    asl a
    clc
    adc BA_T0
    tax
    lda f:actor_command_txt, x
    tax
    sep #$20
.a8
    ; By reference, as everything on a line of the band that comes from the
    ; cartridge: the command, the party's name and state and the HP and SP
    ; share a row's record. See `TL_BY_REF`.
    lda #1
    sta TL_BY_REF
    jsl f:ba_t_text
    inc BA_S0
    jmp command
.endproc

; The party, one line per actor in its window on the left. The bar is the
; window's: see `ba_compose`.
.proc ba_party
.a8
.i16
    stz BA_S0
actor:
    lda BA_S0
    cmp BA_NACTORS
    bcc has
    rts
has:
    rep #$20
.a16
    lda #BA_PARTY_POS0
    jsr ba_row
    sep #$20
.a8
    lda BA_S0
    jsr ba_party_line
    inc BA_S0
    bra actor
.endproc

; The enemies that can be attacked, in their window over the party's, in
; troop order: the living ones, which are the ones that show —a hidden one
; has no `BAF_HAS`, see `ba_alive`—. Five at a time: the window scrolls
; just enough to show the bar, as RM2k's, which is `BA_TARGET_TOP`, in
; places of this list. With `[debug] enemy_hp` each one's HP goes after its
; name. The bar on the command stays where it was, as in RM2k.
.proc ba_target_window
.a8
.i16
    lda #BA_LAYOUT_TARGET
    sta BA_WIN_KEY
    lda BA_COMMAND
    sta BA_WIN_KEY + 2
    ; Where the cursor is in the list: how many living ones go before it.
    stz BA_S1
    stz BA_S0
rank:
    lda BA_S0
    cmp BA_TARGET
    bcs ranked
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    beq :+
    inc BA_S1
:   inc BA_S0
    bra rank
ranked:
    lda BA_S1
    cmp BA_TARGET_TOP
    bcs not_above
    sta BA_TARGET_TOP           ; it went off the top: the window follows it
    bra seen
not_above:
    sec
    sbc #(BA_TARGET_ROWS - 1)
    bcc seen                    ; within the first page
    cmp BA_TARGET_TOP
    bcc seen
    beq seen
    sta BA_TARGET_TOP
seen:
    ; And the lines: `BA_S1` counts the living ones, `BA_S2` the line.
    stz BA_S1
    stz BA_S2
    stz BA_S3
enemy:
    lda BA_S3
    cmp BA_KID
    bcc has_enemy
    rts
has_enemy:
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    beq next
    lda BA_S1
    inc BA_S1
    cmp BA_TARGET_TOP
    bcc next                    ; above the window
    lda BA_S2
    cmp #BA_TARGET_ROWS
    bcs next                    ; below it
    sta BA_S0
    rep #$20
.a16
    lda #BA_ENEMY_POS0
    jsr ba_row
    sep #$20
.a8
    lda BA_S3
    cmp BA_TARGET
    bne no_bar
    lda BA_S2
    sta BA_WIN_KEY + 1
no_bar:
    lda BA_S3
    clc
    adc #BA_PARTY_MAX
    jsr ba_line
    inc BA_S2
next:
    inc BA_S3
    bra enemy
.endproc

; The description in its window on top: text X, on one line, cut at the
; window's frame. RM2k writes it whole with a smaller font. Clobbers `BA_T*`.
.proc ba_help
.a8
.i16
    lda #1
    sta BA_WIN_KEY + 3
    stz temp + 1
    rep #$20
.a16
    lda #BA_HELP_POS
    sta pick_table
    sep #$20
.a8
    lda #BA_HELP_WIDTH
    sta comp_dup + 3
    lda #1
    sta TL_BY_REF
    jsl f:ba_t_text
    rts
.endproc

; --- the item list ---------------------------------------------------------
;
; RM2k's `Window_Item` in the battle: two columns that read by rows, the
; name and the count with a colon in front —`Potion  : 99`—, five rows that
; scroll from `BA_ITEM_ARR`, the first visible row. While choosing whom to
; give it to the band shows the party, as RM2k's does.
.proc ba_item_window
.a8
.i16
    ; The wide window, with the bar on the place under the cursor in the
    ; window's places.
    lda #BA_LAYOUT_WIDE
    sta BA_WIN_KEY
    lda BA_ITEM_ARR
    asl a
    sta BA_T0
    lda BA_ITEM_SEL
    sec
    sbc BA_T0
    sta BA_WIN_KEY + 1
    ; The description of the one under the cursor, whole: `ba_item_desc`.
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:ba_item_desc, x
    tax
    sep #$20
.a8
    jsr ba_help
    ; From the first place of the window's first row to the last of its last.
    lda BA_ITEM_ARR
    asl a
    sta BA_S3                   ; the place in the whole list
row:
    lda BA_S3
    cmp BA_ITEM_N
    bcc has
    rts
has:
    lsr a
    sec
    sbc BA_ITEM_ARR
    cmp #BA_ITEM_ROWS
    bcc on_page
    rts                         ; past the window's last row
on_page:
    sta BA_S0
    lda BA_S3
    and #$01
    sta BA_S4
    rep #$20
.a16
    lda #BA_ITEM_POS0
    jsr ba_row
    lda BA_S4
    and #$00FF
    beq column_zero
    lda #BA_SKILL_COLUMN_DX
column_zero:
    sta BA_S5                   ; the column's offset
    sep #$20
.a8
    ; the name, by reference like the skills'
    stz temp + 1
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_SKILL_NAME_DX
    jsr ba_go
    sep #$20
.a8
    lda #BA_ITEM_NAME_WIDTH
    sta comp_dup + 3
    lda BA_S3
    jsr ba_item_from_list
    stx BA_S6                   ; the `k`
    rep #$20
.a16
    txa
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; times three: `3k` is the name
    tax
    sep #$20
.a8
    lda #1
    sta TL_BY_REF
    jsl f:ba_t_text
    ; the colon and how many there are
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_SKILL_DASH_DX
    jsr ba_go
    sep #$20
.a8
    stz temp + 1
    lda #$3A                    ; the colon
    jsl f:ba_t_glyph
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_ITEM_COUNT_DX
    jsr ba_go
    lda BA_S6
    asl a
    tax
    lda f:item_id, x
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_number
    inc BA_S3
    jmp row
.endproc

; Makes the highlighted item visible: scrolls the window just enough, a row
; at a time, as `ba_skill_see` does with the skills.
.proc ba_item_see
.a8
.i16
    lda BA_ITEM_SEL
    lsr a                       ; its row: two columns
    cmp BA_ITEM_ARR
    bcs not_above
    sta BA_ITEM_ARR
    rts
not_above:
    sec
    sbc #(BA_ITEM_ROWS - 1)
    bcc fits
    cmp BA_ITEM_ARR
    bcc fits
    beq fits
    sta BA_ITEM_ARR
fits:
    rts
.endproc

; --- the skill list --------------------------------------------------------
;
; The layout is the original's —from a capture of the real game, of
; 2026-09-12, and again with Wine on 2026-10-04—: the description of the one
; under the cursor on top, and in the band two columns with the name on the
; left and the SP cost on the right, with a dash in front. It reads **by
; rows**, which is what the capture shows.
.proc ba_skill_window
.a8
.i16
    jsr ba_skill_list
    lda BA_SKILL_N
    bne has_any
    rts
has_any:
    ; The wide window, with the bar on the place under the cursor in the
    ; window's places.
    lda #BA_LAYOUT_WIDE
    sta BA_WIN_KEY
    lda BA_SKILL_TOP
    asl a
    sta BA_T0
    lda BA_SKILL_SEL
    sec
    sbc BA_T0
    sta BA_WIN_KEY + 1
    ; the description of the one under the cursor
    lda BA_SKILL_SEL
    jsr ba_skill_from_list
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:skill_desc, x
    tax
    sep #$20
.a8
    jsr ba_help
    ; From the first place of the window's first row to the last of its last:
    ; the window scrolls, see `ba_skill_see`.
    lda BA_SKILL_TOP
    asl a
    sta BA_S3                   ; the place in the whole list
row_skill:
    lda BA_S3
    cmp BA_SKILL_N
    bcc has_skill
    rts
has_skill:
    jsr ba_skill_place
    bcc has_place_skill
    rts                         ; past the window's last row
has_place_skill:
    ; Row and column on the screen: with two columns they are an `lsr` of the
    ; place on the page and bit 0. If they were ever something else, this is
    ; what has to change; the converter emits `BA_SKILL_COLUMNS` so that it
    ; is visible from here that they are two.
    lsr a
    sta BA_S0
    lda BA_S3
    and #$01
    sta BA_S4
    rep #$20
.a16
    lda #BA_SKILL_POS0
    jsr ba_row
    lda BA_S4
    and #$00FF
    beq column_zero
    lda #BA_SKILL_COLUMN_DX
column_zero:
    sta BA_S5                   ; the column's offset
    sep #$20
.a8
    ; This skill's `k`, and whether it can be paid for: one that cannot goes
    ; in gray, which is what RM2k does with one that cannot be used.
    lda BA_S3
    jsr ba_skill_from_list
    sta BA_S6
    jsr ba_skill_reaches
    bne se_can
    lda #1
    bra variant_skill
se_can:
    lda #0
variant_skill:
    sta BA_S2
    ; the name
    lda BA_S2
    sta temp + 1
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_SKILL_NAME_DX
    jsr ba_go
    sep #$20
.a8
    lda #BA_SKILL_NAME_WIDTH
    sta comp_dup + 3
    ; By reference: the two columns of a row, with the letters copied, do not
    ; fit in a row's record. See `TL_BY_REF`.
    lda #1
    sta TL_BY_REF
    rep #$20
.a16
    lda BA_S6
    and #$00FF
    asl a
    tax
    lda f:skill_txt, x
    tax
    sep #$20
.a8
    jsl f:ba_t_text
    ; the dash and the cost
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_SKILL_DASH_DX
    jsr ba_go
    sep #$20
.a8
    lda BA_S2
    sta temp + 1
    lda #$2D                    ; the dash
    jsl f:ba_t_glyph
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_SKILL_COST_DX
    jsr ba_go
    sep #$20
.a8
    lda BA_S6
    jsr ba_skill_cost
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #BA_SKILL_COST_DIGITS
    sta comp_dup + 2
    lda BA_S2
    sta temp + 1
    jsl f:ba_t_number
    inc BA_S3
    jmp row_skill
.endproc
