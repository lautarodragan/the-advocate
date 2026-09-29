.segment "FAR"

; --- executing a skill ----------------------------------------------------
;
; `Game_BattleAlgorithm::Skill::vStart` and `vExecute`. **The order in which
; it consumes randomness is the contract with
; `batalla.Batalla.usar_habilidad`**: a switch skill finishes before any roll;
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
; The normal attack has its own written inside `ba_atacar` with the variance
; at four; this one was split out for the skills, which carry their own in the
; LDB.
.proc ba_varianza
.a16
.i16
    sta BA_T0
    bmi sin_tirar
    beq sin_tirar
    sep #$20
.a8
    lda BA_S5
    beq sin_varianza
    sta BA_T2
    rep #$20
.a16
    lda BA_T0
    jsr ba_mul                  ; the variance times the effect
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne ajuste_listo
    lda #1                      ; `max(1, ...)`
ajuste_listo:
    sta BA_T1
    jsr ba_hasta                ; A16 is still the adjustment
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
sin_tirar:
    lda BA_T0
    rts
sin_varianza:
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    rts
.endproc

; A parameter modifier moves by `BA_MEFECTO` and the effective parameter is
; recomputed: `CanChangeAtkModifier` and its siblings, plus `AdjustParam`.
;
;   BA_S4 = the target's offset inside `BA_UNO`
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
    lda BA_UNO, x
    clc
    adc BA_MEFECTO
    sta temp                    ; the modifier being asked for
    lda BA_S4
    clc
    adc BA_S6
    tax
    lda BA_UNO, x
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
    bmi arriba_ok
    lda BA_T0
    sta temp
arriba_ok:
    lda BA_T0
    lsr a
    eor #$FFFF
    inc a
    sta BA_T2                   ; -(base / 2)
    lda temp
    sec
    sbc BA_T2
    bpl abajo_ok
    lda BA_T2
    sta temp
abajo_ok:
    lda BA_S4
    clc
    adc BA_S5
    tax
    lda temp
    sta BA_UNO, x               ; the new modifier
    clc
    adc BA_T0                   ; base + modifier
    bmi al_uno
    cmp #1
    bcs no_es_cero
al_uno:
    lda #1
    bra efectivo_listo
no_es_cero:
    cmp #(BA_PARAM_MAX + 1)
    bcc efectivo_listo
    lda #BA_PARAM_MAX
efectivo_listo:
    sta BA_T2
    lda BA_S4
    clc
    adc BA_T1
    tax
    lda BA_T2
    sta BA_UNO, x
    sep #$20
.a8
    rts
.endproc

; Turns on the switch in `BA_T0`, which is the LDB's `switch_id` as is, like
; `item_switch` does with its own. It does not call `poner_switch`: that lives
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
corre:
    cpy #0
    beq mascara_lista
    asl a
    dey
    bra corre
mascara_lista:
    ora switches, x
    sta switches, x
    lda #1
    sta refresco                ; the pages that ask for it may change
    rts
.endproc

; The effect of skill `BA_MHAB` from `BA_MQUIEN` on `BA_MBLA`, **without the
; variance**: `Algo::CalcSkillEffect`. Leaves the result in `BA_MEFECTO`,
; already clamped below at zero.
.proc ba_hab_efecto
.a8
.i16
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
    ; the skill's `k`, times two for the word tables
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_power, x
    sta BA_S2                   ; the effect accumulator
    sep #$20
.a8
    ; + physical_rate * atk / 20
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_fis, x
    sta BA_T2
    beq sin_fisico
    ldx BA_S0
    rep #$20
.a16
    lda BA_UNO + BA_ATK, x
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
sin_fisico:
    ; + magical_rate * spi / 40
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_mag, x
    sta BA_T2
    beq sin_magico
    ldx BA_S0
    rep #$20
.a16
    lda BA_UNO + BA_SPI, x
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
sin_magico:
    ; Against an enemy and without `ignore_defense`, its defense and spirit
    ; are subtracted. `SkillTargetsEnemies` is bit 6 of `hab_afecta` and bit 7
    ; is `ignore_defense`.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_afecta, x
    sta BA_S3
    and #$40
    beq sin_resta
    lda BA_S3
    and #$80
    bne sin_resta
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_fis, x
    sta BA_T2
    beq sin_resta_fis
    ldx BA_S1
    rep #$20
.a16
    lda BA_UNO + BA_DEF, x
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
sin_resta_fis:
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_mag, x
    sta BA_T2
    beq sin_resta
    ldx BA_S1
    rep #$20
.a16
    lda BA_UNO + BA_SPI, x
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
sin_resta:
    rep #$20
.a16
    lda BA_S2
    bpl no_negativo
    lda #0                      ; `max(0, effect)`
no_negativo:
    sta BA_MEFECTO
    sep #$20
.a8
    ; The critical, which for an LDB skill **always comes out no**: the chance
    ; `CalcCriticalHitChance` receives is `easyrpg_critical_hit_chance`, which
    ; is 0 and not -1. The roll is made anyway, because otherwise the two
    ; sides would drift out of phase.
    lda #0
    jsr ba_pct
    beq sin_critico
    rep #$20
.a16
    lda BA_MEFECTO
    sta temp
    asl a
    clc
    adc temp                    ; times three
    sta BA_MEFECTO
    sep #$20
.a8
sin_critico:
    rts
.endproc

; The target's HP move by `BA_MEFECTO`. Healing does not kill —the
; `max(-(cur_hp - 1), hp_effect)` of `vExecute`— and damage is halved for one
; who is defending, with C++ division, which **truncates toward zero**.
.proc ba_hab_hp
.a8
.i16
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    lda BA_MEFECTO
    bmi hace_dano
    sta BA_T0
    bra aplica
hace_dano:
    sep #$20
.a8
    ldx BA_S4
    lda BA_UNO + BA_FLAGS, x
    and #BAF_DEF
    beq sin_defensa
    rep #$20
.a16
    lda BA_MEFECTO
    eor #$FFFF
    inc a
    lsr a
    eor #$FFFF
    inc a                       ; half, truncated toward zero
    sta BA_T0
    bra aplica
sin_defensa:
.a8
.i16
    rep #$20
.a16
    lda BA_MEFECTO
    sta BA_T0
aplica:
.a16
.i16
    ldx BA_S4
    lda BA_UNO + BA_HP, x
    clc
    adc BA_T0
    bmi en_cero
    cmp BA_UNO + BA_HPMAX, x
    bcc cabe
    lda BA_UNO + BA_HPMAX, x
    bra cabe
en_cero:
    lda #0
cabe:
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; And the SP, the same but with no defense that counts. None of the seven uses
; it; it is here because `vExecute` does it and because the roll before it has
; already been made.
.proc ba_hab_sp
.a8
.i16
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    clc
    adc BA_MEFECTO
    bmi sp_en_cero
    cmp BA_UNO + BA_SPMAX, x
    bcc sp_cabe
    lda BA_UNO + BA_SPMAX, x
    bra sp_cabe
sp_en_cero:
    lda #0
sp_cabe:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
    rts
.endproc

; The skill `BA_MQUIEN` chose, on `BA_MBLA`. Leaves the message ready.
.proc ba_hab_usar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_ax
    lda BA_ACC_HAB, x
    sta BA_MHAB
    ; --- `vStart`: the cost, before anything and without rolling ---
    jsr ba_hab_costo
    sta BA_T2
    stz BA_T2 + 1               ; the subtraction below is 16 bits and
                                ; `hab_sp` is 8: without this the high byte
                                ; is whatever the last one through here left,
                                ; and SP ended up at zero
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_ok
    lda #0                      ; cannot happen: without SP it is not chosen
sp_ok:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
    ; --- a switch skill turns on its switch and does nothing else ---
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_tipo, x
    cmp #BA_HAB_TIPO_SWITCH
    bne no_es_switch
    rep #$20
.a16
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_switch, x
    sta BA_T0
    lda #0
    sta BA_MEFECTO
    sep #$20
.a8
    jmp ba_switch
no_es_switch:
    ; --- on whom: `batalla.blancos_de_la_habilidad` ---
    ;
    ; `enemy` and `ally` on the chosen one, `self` on the user, and `enemies`
    ; and `party` on each living one on the opposing side or its own, in
    ; screen order and **each with its own rolls**. The message gets the last
    ; one.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_alcance, x
    cmp #BA_ALCANCE_UNO
    bne no_es_uno
    lda BA_MQUIEN
    sta BA_MBLA
    jmp ba_hab_uno
no_es_uno:
    cmp #BA_ALCANCE_ENEMIGOS
    beq de_a_muchos
    cmp #BA_ALCANCE_GRUPO
    beq de_a_muchos
    jmp ba_hab_uno
de_a_muchos:
    ; The side: the opposing one with `enemies`, its own with `party`. That
    ; the source is in the party is `BA_MQUIEN < BA_GRUPO_MAX`.
    ldy #0                      ; 0 the party, 1 the troop
    lda BA_MQUIEN
    cmp #BA_GRUPO_MAX
    bcc del_grupo
    iny
del_grupo:
    lda f:hab_alcance, x
    cmp #BA_ALCANCE_ENEMIGOS
    bne lado_listo
    tya
    eor #1
    tay
lado_listo:
    lda #0
    cpy #0
    beq primero_listo
    lda #BA_GRUPO_MAX
primero_listo:
    sta f:BA_HAB_I
otro_blanco:
    lda f:BA_HAB_I
    jsr ba_vivo
    beq no_cae
    lda f:BA_HAB_I
    sta BA_MBLA
    jsr ba_hab_uno
no_cae:
    lda f:BA_HAB_I
    inc a
    sta f:BA_HAB_I
    cmp #BA_GRUPO_MAX
    beq listos                  ; the party ends where the troop begins
    cmp #BA_COMB_MAX
    bcc otro_blanco
listos:
    rts
.endproc

; `vExecute` on target `BA_MBLA`: the effect, the variance and the hit rolls.
; Called by `ba_hab_usar`, once or once per target.
.proc ba_hab_uno
.a8
.i16
    jsr ba_hab_efecto
    ; the variance, with the skill's `variance`
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_var, x
    sta BA_S5
    rep #$20
.a16
    lda BA_MEFECTO
    jsr ba_varianza
    ; the damage cap, which is the same as an attack's
    cmp #(BA_DANO_MAX + 1)
    bcc efecto_cabe
    lda #BA_DANO_MAX
efecto_cabe:
    sta BA_MEFECTO
    sep #$20
.a8
    ; If it targets enemies the effect is negative: `SetIsPositive` is
    ; `SkillTargetsAllies`, and `vExecute` flips the sign when it is not.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_afecta, x
    sta BA_S3                   ; what it touches, which is not read again
    and #$40
    beq es_positivo
    rep #$20
.a16
    lda BA_MEFECTO
    eor #$FFFF
    inc a
    sta BA_MEFECTO
    sep #$20
.a8
es_positivo:
    ; the hit rate, which all seven carry at 100
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_hit, x
    sta BA_S0                   ; the hit rate, which survives the `jsr`s
    ; --- the HP ---
    lda BA_S3
    and #$01
    beq sin_hp
    lda BA_S0
    jsr ba_pct
    beq sin_hp
    jsr ba_hab_hp
sin_hp:
    ; --- the SP ---
    ;
    ; None of the seven the intro party knows touches them, **but the roll
    ; happens anyway**: `vExecute` makes it and removing it would put the
    ; randomness out of phase.
    lda BA_S3
    and #$02
    beq sin_sp
    lda BA_S0
    jsr ba_pct
    beq sin_sp
    jsr ba_hab_sp
sin_sp:
    ; --- the four parameters, in `vExecute`'s order ---
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    sep #$20
.a8
    lda BA_S3
    and #$04
    beq sin_atk
    lda BA_S0
    jsr ba_pct
    beq sin_atk
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
sin_atk:
    lda BA_S3
    and #$08
    beq sin_def
    lda BA_S0
    jsr ba_pct
    beq sin_def
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
sin_def:
    lda BA_S3
    and #$10
    beq sin_spi
    lda BA_S0
    jsr ba_pct
    beq sin_spi
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
sin_spi:
    lda BA_S3
    and #$20
    beq sin_agi
    lda BA_S0
    jsr ba_pct
    beq sin_agi
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
sin_agi:
    rts
.endproc

; --- skills in battle ------------------------------------------------------
;
; `Game_BattleAlgorithm::Skill` with what this port knows how to do. What each
; actor knows at the start, how much it costs and how much it does **is not
; decided here**: it comes from `batalla.habilidades_de`, `batalla.costo_de`
; and `batalla.efecto_habilidad`, which is the model with which
; `rom/pruebas/rpgmaker/test_batalla.py` predicts the exact number, and the
; converter emits it in `hab_par_*` and `hab_*`. What it knows **now** is
; `FAR_HAB`, which `ChangeSkills` changes.

; A8 = the LDB actor number of combatant `BA_ACTOR`. It is what indexes
; `hab_par_ini`, `hab_par_n` and `actor_hab_txt`, which are by actor number
; and not by place in the party.
.proc ba_actor_ldb
.a8
.i16
    lda BA_ACTOR
    jsr ba_x
    lda BA_UNO + BA_NUMERO, x
    rts
.endproc

; The skill list of the actor giving commands, into `BA_HAB_LISTA`, with how
; many in `BA_HAB_N`. They are its `FAR_HAB` pairs with the bit set —what it
; knows **now**, which `ChangeSkills` changes— that the battle knows how to
; offer, that is, with a `k` in `hab_par_k`. An actor's pairs are contiguous
; and in skill-number order, so the list comes out in `LearnSkill` order.
; Clobbers `BA_S1`, `BA_S2`, `BA_T0` and X.
.proc ba_hab_lista
.a8
.i16
    lda #0
    sta BA_HAB_N
    jsr ba_actor_ldb
    jsr ba_ax
    lda f:hab_par_n, x
    beq listo
    sta BA_S1                   ; how many pairs it has left to look at
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:hab_par_ini, x
    sta BA_S2                   ; the slot of the pair being looked at
    sep #$20
.a8
otro:
    lda BA_HAB_N
    cmp #BA_HAB_MAX
    bcs listo
    rep #$20
.a16
    lda BA_S2
    and #$0007
    tax
    sep #$20
.a8
    lda f:mascara, x
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
    lda f:FAR_LARGO + FAR_HAB, x
    and BA_T0
    beq siguiente               ; it does not know it
    ldx BA_S2
    lda f:hab_par_k, x
    cmp #$FF
    beq siguiente               ; it knows it and the battle does not offer it
    pha
    lda BA_HAB_N
    jsr ba_ax
    pla
    sta BA_HAB_LISTA, x
    inc BA_HAB_N
siguiente:
    rep #$20
.a16
    inc BA_S2
    sep #$20
.a8
    dec BA_S1
    bne otro
listo:
    rts
.endproc

; The `k` at place A8 in the list. Only A and X.
.proc ba_hab_de_lista
.a8
.i16
    jsr ba_ax
    lda BA_HAB_LISTA, x
    rts
.endproc

; The SP cost of the `k` in A8, in A8. `Algo::CalcSkillCost`: the plain
; `sp_cost`, which is what RM2k does.
.proc ba_hab_costo
.a8
.i16
    jsr ba_ax
    lda f:hab_sp, x
    rts
.endproc

; Whether combatant `BA_ACTOR` can pay for the `k` in A8: Z=0 if so. **It does
; not use the flag a `pl*` leaves**: the usual trap.
.proc ba_hab_alcanza
.a8
.i16
    jsr ba_hab_costo
    sta BA_T2
    lda BA_ACTOR
    jsr ba_x
    rep #$20
.a16
    lda BA_T2
    and #$00FF
    cmp BA_UNO + BA_SP, x
    sep #$20
.a8
    beq si                      ; exactly as many as it has is enough
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; The whole screen, in `texto_buf`.
.proc ba_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    ; --- the enemies, or the item list while one is being chosen ---
    ;
    ; They go on the same lines on purpose: while choosing what to use, what
    ; needs to be seen is the party, which is who gets healed, and not the
    ; enemies. **While choosing whom to give it to, the list of the current
    ; command goes on top**: the items one or the skills one, both in gray.
    ; Which of the two is said by `BA_ORDEN`, which stays set while the target
    ; is being chosen.
    lda BA_MODO
    cmp #BA_M_HAB
    beq a_la_lista_hab
    cmp #BA_M_ACTOR
    bne no_es_hab
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne no_es_hab
a_la_lista_hab:
    jmp la_lista_hab
no_es_hab:
    lda BA_MODO
    cmp #BA_M_ITEM
    beq a_la_lista
    cmp #BA_M_ACTOR
    bne sin_lista
a_la_lista:
    jmp la_lista
sin_lista:
    lda #0
    sta BA_S0
enemigo:
    lda BA_S0
    cmp BA_NENE
    bcs enemigos_listos
    rep #$20
.a16
    lda #BA_ENEMIGO_POS0
    jsr ba_fila
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_BLANCO
    bne sin_cursor_ene
    lda BA_S0
    cmp BA_BLANCO
    bne sin_cursor_ene
    jsr ba_cursor
sin_cursor_ene:
    stz BA_CONMAX               ; an enemy does not show its maximum
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_renglon
    inc BA_S0
    bra enemigo
enemigos_listos:
    ; --- the party ---
    ;
    ; Unless there is a message from a troop page, which goes on its lines: in
    ; RM2k the battle's message window covers the party's. See
    ; `ba_pag_mensaje`. And the same with what the victory reports.
    jsr ba_vic_en_pantalla
    beq sin_victoria
    jmp ba_vic_mensaje
sin_victoria:
    lda BA_MODO
    cmp #BA_M_PAGINA
    bne con_grupo
    rep #$20
.a16
    lda BA_PAG_MSG
    cmp #$FFFF
    sep #$20
.a8
    beq con_grupo
    jmp ba_pag_mensaje
con_grupo:
    lda #0
    sta BA_S0
actor:
    lda BA_S0
    cmp BA_NACT
    bcs actores_listos
    rep #$20
.a16
    lda #BA_GRUPO_POS0
    jsr ba_fila
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_MENSAJE
    bcs sin_cursor_act
    cmp #BA_M_ACTOR
    bne cursor_en_el_que_ordena
    lda BA_S0
    cmp BA_ITEM_BLA             ; choosing whom to heal
    bne sin_cursor_act
    bra pone_cursor_act
cursor_en_el_que_ordena:
    lda BA_S0
    cmp BA_ACTOR
    bne sin_cursor_act
pone_cursor_act:
    jsr ba_cursor
sin_cursor_act:
    lda #1
    sta BA_CONMAX
    lda BA_S0
    jsr ba_renglon
    inc BA_S0
    bra actor
actores_listos:
    ; --- the last line ---
    ;
    ; Which stays empty while a page is running: the previous action's message
    ; has already been read, and the page's goes on top.
    lda BA_MODO
    cmp #BA_M_PAGINA
    bne no_es_pagina
    rts
no_es_pagina:
    cmp #BA_M_MENSAJE
    bcc ordenes
    jmp ba_mensaje
ordenes:
    lda #0
    sta BA_S0
orden:
    lda BA_S0
    cmp #BA_ORDENES_N
    bcc hay_orden
    jmp ordenes_listas
hay_orden:
    ; Which line this one falls on: since 2026-09-13 there are five and they
    ; go on two.
    lda BA_S0
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:ba_orden_fila, x
    sta BA_T1
    sep #$20
.a8
    ; In gray while something else is being chosen —the menu is no longer in
    ; charge— and always the one that is not implemented, which is what the
    ; pause menu does with its own.
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne en_gris
    lda BA_S0
    jsr ba_ax
    lda f:ba_orden_gris, x
    bne en_gris
    ; And the skill command of an actor who knows none —Talan, who is level
    ; 1— also goes in gray, like the pause menu with what leads nowhere.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    bne sin_gris_orden
    jsr ba_hab_lista            ; what it knows now: see `FAR_HAB`
    lda BA_HAB_N
    beq en_gris
sin_gris_orden:
    lda #0
    bra pone_variante
en_gris:
    lda #1
pone_variante:
    sta BA_S1
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:ba_orden_dx, x
    sta BA_T2
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne sin_cursor_orden
    lda BA_S0
    cmp BA_ORDEN
    bne sin_cursor_orden
    stz temp + 1
    rep #$20
.a16
    lda BA_T2
    sec
    sbc #2
    jsr ba_ir
    sep #$20
.a8
    lda #$3E                    ; the cursor
    jsl f:ba_t_glifo
sin_cursor_orden:
    rep #$20
.a16
    lda BA_T2
    jsr ba_ir
    sep #$20
.a8
    lda BA_S1
    sta temp + 1
    lda #255
    sta comp_dup + 3
    ; **The second command does not say "Tech Skill"**: it says the
    ; `skill_name` of the actor giving commands —"AgentTrain", "Telepathy",
    ; "Slicing"—, which is `Game_Actor::GetSkillName`. That is why its text
    ; comes from `actor_hab_txt`, which is by actor number, and not from
    ; `ba_orden_txt`, which is fixed.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    beq texto_de_la_habilidad
    ; **Two bytes wide**, like `actor_hab_txt` and `enemigo_txt`: a text index
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
    lda f:ba_orden_txt, x
    tax
    bra texto_puesto
texto_de_la_habilidad:
.a8
.i16
    jsr ba_actor_ldb
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:actor_hab_txt, x
    tax
texto_puesto:
.a16
    sep #$20
.a8
    jsl f:ba_t_texto
    inc BA_S0
    jmp orden
ordenes_listas:
    rts

    ; --- the item list, where the enemies go ---
la_lista:
    lda #0
    sta BA_S0
fila_item:
    lda BA_S0
    cmp #BA_ENEMIGOS_MAX
    bcs no_hay_mas
    clc
    adc BA_ITEM_ARR
    cmp BA_ITEM_N
    bcc hay_item
no_hay_mas:
    jmp items_listos
hay_item:
    sta BA_S6                   ; the place in the list
    rep #$20
.a16
    lda #BA_ENEMIGO_POS0
    jsr ba_fila
    sep #$20
.a8
    ; The cursor, only while the item is being chosen: while choosing the
    ; target the list stays gray and the cursor moves to the party.
    lda BA_MODO
    cmp #BA_M_ITEM
    bne gris_item
    lda BA_S6
    cmp BA_ITEM_SEL
    bne sin_cursor_item
    jsr ba_cursor
sin_cursor_item:
    lda #0
    bra variante_item
gris_item:
    lda #1
variante_item:
    sta temp + 1
    ; the name
    rep #$20
.a16
    lda #BA_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_NOMBRE_ANCHO
    sta comp_dup + 3
    lda BA_S6
    jsr ba_item_de_lista
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
    jsl f:ba_t_texto
    ; and how many there are, with the colon in front
    rep #$20
.a16
    lda #BA_ITEM_CUENTA_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_ITEM
    beq cuenta_blanca
    lda #1
    bra cuenta_variante
cuenta_blanca:
    lda #0
cuenta_variante:
    sta temp + 1
    lda #$3A                    ; the colon
    jsl f:ba_t_glifo
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
    jsl f:ba_t_numero
    inc BA_S0
    jmp fila_item
items_listos:
    jmp enemigos_listos

    ; --- the skill list, where the enemies go ---
    ;
    ; The layout is the original's —from a capture of the real game, of
    ; 2026-09-12—: the description of the one under the cursor at the very
    ; top, and below two columns with the name on the left and the SP cost on
    ; the right, with a dash in front. It reads **by rows**, which is what the capture shows.
la_lista_hab:
    jsr ba_hab_lista
    lda BA_HAB_N
    bne hay_alguna
    jmp hab_listas
hay_alguna:
    lda BA_MODO
    cmp #BA_M_HAB
    bne hab_en_gris             ; choosing the target: no description
    ; the description of the one under the cursor
    rep #$20
.a16
    lda #BA_HAB_DESC_POS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #255
    sta comp_dup + 3
    lda BA_HAB_SEL
    jsr ba_hab_de_lista
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:hab_desc, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
hab_en_gris:
    lda #0
    sta BA_S3                   ; the place in the list
fila_hab:
    lda BA_S3
    cmp BA_HAB_N
    bcc hay_hab
    jmp hab_listas
hay_hab:
    cmp #(BA_HAB_FILAS * BA_HAB_COLUMNAS)
    bcc hay_lugar_hab
    jmp hab_listas
hay_lugar_hab:
    ; Row and column: with two columns they are an `lsr` and bit 0. If they
    ; were ever something else, this is what has to change; the converter
    ; emits `BA_HAB_COLUMNAS` so that it is visible from here that they are
    ; two.
    lda BA_S3
    lsr a
    sta BA_S0
    lda BA_S3
    and #$01
    sta BA_S4
    rep #$20
.a16
    lda #BA_HAB_POS0
    jsr ba_fila
    lda BA_S4
    and #$00FF
    beq columna_cero
    lda #BA_HAB_COLUMNA_DX
    bra columna_puesta
columna_cero:
    lda #0
columna_puesta:
    sta BA_S5                   ; the column's offset
    sep #$20
.a8
    ; This skill's `k`, and whether it can be paid for: one that cannot goes
    ; in gray, which is what RM2k does with one that cannot be used.
    lda BA_S3
    jsr ba_hab_de_lista
    sta BA_S6
    lda BA_MODO
    cmp #BA_M_HAB
    bne gris_hab                ; choosing the target, the whole list in gray
    lda BA_S6
    jsr ba_hab_alcanza
    bne se_puede
gris_hab:
    lda #1
    bra variante_hab
se_puede:
    lda #0
variante_hab:
    sta BA_S2
    ; the cursor, only while the skill is being chosen
    lda BA_MODO
    cmp #BA_M_HAB
    bne sin_cursor_hab
    lda BA_S3
    cmp BA_HAB_SEL
    bne sin_cursor_hab
    stz temp + 1
    rep #$20
.a16
    lda BA_S5
    jsr ba_ir
    sep #$20
.a8
    lda #$3E
    jsl f:ba_t_glifo
sin_cursor_hab:
    ; the name
    lda BA_S2
    sta temp + 1
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_HAB_NOMBRE_ANCHO
    sta comp_dup + 3
    rep #$20
.a16
    lda BA_S6
    and #$00FF
    asl a
    tax
    lda f:hab_txt, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; the dash and the cost
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_GUION_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_S2
    sta temp + 1
    lda #$2D                    ; the dash
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_COSTO_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_S6
    jsr ba_hab_costo
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #BA_HAB_COSTO_CIFRAS
    sta comp_dup + 2
    lda BA_S2
    sta temp + 1
    jsl f:ba_t_numero
    inc BA_S3
    jmp fila_hab
hab_listas:
    jmp enemigos_listos
.endproc
