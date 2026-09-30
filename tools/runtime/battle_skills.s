.segment "FAR"

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
    ora switches, x
    sta switches, x
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
    sep #$20
.a8
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
    sep #$20
.a8
    rts
.endproc

; The skill `BA_MWHO` chose, on `BA_MTGT`. Leaves the message ready.
.proc ba_skill_use
.a8
.i16
    lda BA_MWHO
    jsr ba_ax
    lda BA_ACC_SKILL, x
    sta BA_MSKILL
    ; --- `vStart`: the cost, before anything and without rolling ---
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
    ; screen order and **each with its own rolls**. The message gets the last
    ; one.
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
    beq from_a_many
    cmp #BA_SCOPE_PARTY
    beq from_a_many
    jmp ba_skill_one
from_a_many:
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
    rts
.endproc

; --- skills in battle ------------------------------------------------------
;
; `Game_BattleAlgorithm::Skill` with what this port knows how to do. What each
; actor knows at the start, how much it costs and how much it does **is not
; decided here**: it comes from `skills_of`, the skill's `sp_cost` and
; `skill_effect` in `rm2k-snes-battle`, which is the model with which
; `rom/pruebas/rpgmaker/test_batalla.py` predicts the exact number, and the
; converter emits it in `skill_pair_*` and `skill_*`. What it knows **now** is
; `FAR_SKILL`, which `ChangeSkills` changes.

; A8 = the LDB actor number of combatant `BA_ACTOR`. It is what indexes
; `skill_pair_init`, `skill_pair_n` and `actor_skill_txt`, which are by actor number
; and not by place in the party.
.proc ba_actor_ldb
.a8
.i16
    lda BA_ACTOR
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rts
.endproc

; The skill list of the actor giving commands, into `BA_SKILL_LIST`, with how
; many in `BA_SKILL_N`. They are its `FAR_SKILL` pairs with the bit set —what it
; knows **now**, which `ChangeSkills` changes— that the battle knows how to
; offer, that is, with a `k` in `skill_pair_k`. An actor's pairs are contiguous
; and in skill-number order, so the list comes out in `LearnSkill` order.
; Clobbers `BA_S1`, `BA_S2`, `BA_T0` and X.
.proc ba_skill_list
.a8
.i16
    lda #0
    sta BA_SKILL_N
    jsr ba_actor_ldb
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
    cmp #BA_SKILL_MAX
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
    jsr ba_ax
    pla
    sta BA_SKILL_LIST, x
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

; The `k` at place A8 in the list. Only A and X.
.proc ba_skill_from_list
.a8
.i16
    jsr ba_ax
    lda BA_SKILL_LIST, x
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

; Whether combatant `BA_ACTOR` can pay for the `k` in A8: Z=0 if so. **It does
; not use the flag a `pl*` leaves**: the usual trap.
.proc ba_skill_reaches
.a8
.i16
    jsr ba_skill_cost
    sta BA_T2
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
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; The whole screen, in `text_buf`.
.proc ba_compose
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_clear
    ; --- the enemies, or the item list while one is being chosen ---
    ;
    ; They go on the same lines on purpose: while choosing what to use, what
    ; needs to be seen is the party, which is who gets healed, and not the
    ; enemies. **While choosing whom to give it to, the list of the current
    ; command goes on top**: the items one or the skills one, both in gray.
    ; Which of the two is said by `BA_COMMAND`, which stays set while the target
    ; is being chosen.
    lda BA_MODE
    cmp #BA_M_SKILL
    beq to_list_skill
    cmp #BA_M_ACTOR
    bne not_skill
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne not_skill
to_list_skill:
    jmp list_skill
not_skill:
    lda BA_MODE
    cmp #BA_M_ITEM
    beq to_list
    cmp #BA_M_ACTOR
    bne no_list
to_list:
    jmp list
no_list:
    lda #0
    sta BA_S0
enemy:
    lda BA_S0
    cmp BA_KID
    bcs enemies_all_ready
    rep #$20
.a16
    lda #BA_ENEMY_POS0
    jsr ba_row
    sep #$20
.a8
    lda BA_MODE
    cmp #BA_M_TARGET
    bne no_cursor_enemy
    lda BA_S0
    cmp BA_TARGET
    bne no_cursor_enemy
    jsr ba_cursor
no_cursor_enemy:
    stz BA_WITHMAX              ; an enemy does not show its maximum
    lda BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_line
    inc BA_S0
    bra enemy
enemies_all_ready:
    ; --- the party ---
    ;
    ; Unless there is a message from a troop page, which goes on its lines: in
    ; RM2k the battle's message window covers the party's. See
    ; `ba_page_message`. And the same with what the victory reports.
    jsr ba_vic_on_screen
    beq no_victory
    jmp ba_vic_message
no_victory:
    lda BA_MODE
    cmp #BA_M_PAGE
    bne with_party
    rep #$20
.a16
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    beq with_party
    jmp ba_page_message
with_party:
    lda #0
    sta BA_S0
actor:
    lda BA_S0
    cmp BA_NACTORS
    bcs actors_all_ready
    rep #$20
.a16
    lda #BA_PARTY_POS0
    jsr ba_row
    sep #$20
.a8
    lda BA_MODE
    cmp #BA_M_MESSAGE
    bcs no_cursor_act
    cmp #BA_M_ACTOR
    bne cursor_in_sorts
    lda BA_S0
    cmp BA_ITEM_TGT             ; choosing whom to heal
    bne no_cursor_act
    bra sets_cursor_act
cursor_in_sorts:
    lda BA_S0
    cmp BA_ACTOR
    bne no_cursor_act
sets_cursor_act:
    jsr ba_cursor
no_cursor_act:
    lda #1
    sta BA_WITHMAX
    lda BA_S0
    jsr ba_line
    inc BA_S0
    bra actor
actors_all_ready:
    ; --- the last line ---
    ;
    ; Which stays empty while a page is running: the previous action's message
    ; has already been read, and the page's goes on top.
    lda BA_MODE
    cmp #BA_M_PAGE
    bne not_page
    rts
not_page:
    cmp #BA_M_MESSAGE
    bcc commands
    jmp ba_message
commands:
    lda #0
    sta BA_S0
command:
    lda BA_S0
    cmp #BA_COMMANDS_N
    bcc has_command
    jmp commands_lists
has_command:
    ; Which line this one falls on: since 2026-09-13 there are five and they
    ; go on two.
    lda BA_S0
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:ba_command_row, x
    sta BA_T1
    sep #$20
.a8
    ; In gray while something else is being chosen —the menu is no longer in
    ; charge— and always the one that is not implemented, which is what the
    ; pause menu does with its own.
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
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:ba_command_dx, x
    sta BA_T2
    sep #$20
.a8
    lda BA_MODE
    cmp #BA_M_COMMAND
    bne no_cursor_command
    lda BA_S0
    cmp BA_COMMAND
    bne no_cursor_command
    stz temp + 1
    rep #$20
.a16
    lda BA_T2
    sec
    sbc #2
    jsr ba_go
    sep #$20
.a8
    lda #$3E                    ; the cursor
    jsl f:ba_t_glyph
no_cursor_command:
    rep #$20
.a16
    lda BA_T2
    jsr ba_go
    sep #$20
.a8
    lda BA_S1
    sta temp + 1
    lda #255
    sta comp_dup + 3
    ; **The second command does not say "Tech Skill"**: it says the
    ; `skill_name` of the actor giving commands —"AgentTrain", "Telepathy",
    ; "Slicing"—, which is `Game_Actor::GetSkillName`. That is why its text
    ; comes from `actor_skill_txt`, which is by actor number, and not from
    ; `ba_command_txt`, which is fixed.
    lda BA_S0
    cmp #BA_COMMAND_SKILL
    beq text_skill
    ; **Two bytes wide**, like `actor_skill_txt` and `enemy_txt`: a text index
    ; does not fit in one. With the 29 maps of `abl` the battle texts start at
    ; 273, so the one-byte table that was here until 2026-09-14 truncated them
    ; to 17, 18, 19 and 32, which are lines of an item's description: the menu
    ; drew four long texts, one on top of the other. No cartridge in the test
    ; suite reaches 256 texts.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:ba_command_txt, x
    tax
    bra text_set
text_skill:
.a8
.i16
    jsr ba_actor_ldb
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:actor_skill_txt, x
    tax
text_set:
.a16
    sep #$20
.a8
    jsl f:ba_t_text
    inc BA_S0
    jmp command
commands_lists:
    rts

    ; --- the item list, where the enemies go ---
list:
    lda #0
    sta BA_S0
row_item:
    lda BA_S0
    cmp #BA_ENEMIES_MAX
    bcs none_more
    clc
    adc BA_ITEM_ARR
    cmp BA_ITEM_N
    bcc has_item
none_more:
    jmp items_all_ready
has_item:
    sta BA_S6                   ; the place in the list
    rep #$20
.a16
    lda #BA_ENEMY_POS0
    jsr ba_row
    sep #$20
.a8
    ; The cursor, only while the item is being chosen: while choosing the
    ; target the list stays gray and the cursor moves to the party.
    lda BA_MODE
    cmp #BA_M_ITEM
    bne gray_item
    lda BA_S6
    cmp BA_ITEM_SEL
    bne no_cursor_item
    jsr ba_cursor
no_cursor_item:
    lda #0
    bra variant_item
gray_item:
    lda #1
variant_item:
    sta temp + 1
    ; the name
    rep #$20
.a16
    lda #BA_NAME_DX
    jsr ba_go
    sep #$20
.a8
    lda #BA_NAME_WIDTH
    sta comp_dup + 3
    lda BA_S6
    jsr ba_item_from_list
    sta BA_S1                   ; the `k`
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; times three: `3k` is the name
    tax
    sep #$20
.a8
    jsl f:ba_t_text
    ; and how many there are, with the colon in front
    rep #$20
.a16
    lda #BA_ITEM_COUNT_DX
    jsr ba_go
    sep #$20
.a8
    lda BA_MODE
    cmp #BA_M_ITEM
    beq count_white
    lda #1
    bra count_variant
count_white:
    lda #0
count_variant:
    sta temp + 1
    lda #$3A                    ; the colon
    jsl f:ba_t_glyph
    lda BA_S1
    rep #$20
.a16
    and #$00FF
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
    jsl f:ba_t_number
    inc BA_S0
    jmp row_item
items_all_ready:
    jmp enemies_all_ready

    ; --- the skill list, where the enemies go ---
    ;
    ; The layout is the original's —from a capture of the real game, of
    ; 2026-09-12—: the description of the one under the cursor at the very
    ; top, and below two columns with the name on the left and the SP cost on
    ; the right, with a dash in front. It reads **by rows**, which is what the capture shows.
list_skill:
    jsr ba_skill_list
    lda BA_SKILL_N
    bne has_any
    jmp skill_lists
has_any:
    lda BA_MODE
    cmp #BA_M_SKILL
    bne skill_in_gray           ; choosing the target: no description
    ; the description of the one under the cursor
    rep #$20
.a16
    lda #BA_SKILL_DESC_POS
    sta pick_table
    sep #$20
.a8
    stz temp + 1
    lda #255
    sta comp_dup + 3
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
    jsl f:ba_t_text
skill_in_gray:
    lda #0
    sta BA_S3                   ; the place in the list
row_skill:
    lda BA_S3
    cmp BA_SKILL_N
    bcc has_skill
    jmp skill_lists
has_skill:
    cmp #(BA_SKILL_ROWS * BA_SKILL_COLUMNS)
    bcc has_place_skill
    jmp skill_lists
has_place_skill:
    ; Row and column: with two columns they are an `lsr` and bit 0. If they
    ; were ever something else, this is what has to change; the converter
    ; emits `BA_SKILL_COLUMNS` so that it is visible from here that they are
    ; two.
    lda BA_S3
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
    bra column_set
column_zero:
    lda #0
column_set:
    sta BA_S5                   ; the column's offset
    sep #$20
.a8
    ; This skill's `k`, and whether it can be paid for: one that cannot goes
    ; in gray, which is what RM2k does with one that cannot be used.
    lda BA_S3
    jsr ba_skill_from_list
    sta BA_S6
    lda BA_MODE
    cmp #BA_M_SKILL
    bne gray_skill              ; choosing the target, the whole list in gray
    lda BA_S6
    jsr ba_skill_reaches
    bne se_can
gray_skill:
    lda #1
    bra variant_skill
se_can:
    lda #0
variant_skill:
    sta BA_S2
    ; the cursor, only while the skill is being chosen
    lda BA_MODE
    cmp #BA_M_SKILL
    bne no_cursor_skill
    lda BA_S3
    cmp BA_SKILL_SEL
    bne no_cursor_skill
    stz temp + 1
    rep #$20
.a16
    lda BA_S5
    jsr ba_go
    sep #$20
.a8
    lda #$3E
    jsl f:ba_t_glyph
no_cursor_skill:
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
skill_lists:
    jmp enemies_all_ready
.endproc
