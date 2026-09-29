.segment "FAR"

; --- the battle loop -------------------------------------------------------

; The average agility of one side: A8 at 0 the party and at 1 the troop. If
; nobody is left alive everyone counts, which is the `or list(quienes)` of
; `batalla.Batalla._promedio`. The result goes in `BT_T1`, capped at
; `BT_AGI_CAP`: through memory and not the accumulator, for the same reason
; as `bt_param`.
.proc bt_average
.a8
.i16
    sta BT_S6
    ; Two passes: the first counts only the living and, if there were none,
    ; the second counts everyone.
    lda #1
    sta BT_S5                   ; only the living?
vuelta:
    rep #$20
.a16
    lda #0
    sta BT_T0                   ; the sum
    sep #$20
.a8
    lda #0
    sta BT_S4                   ; how many
    lda BT_S6
    beq desde_el_grupo
    lda #BT_PARTY_MAX
    sta BT_S0
    lda BT_KID
    clc
    adc #BT_PARTY_MAX
    sta BT_S3
    bra suma
desde_el_grupo:
    lda #0
    sta BT_S0
    lda BT_NACT
    sta BT_S3
suma:
    lda BT_S0
    cmp BT_S3
    bcs sumados
    lda BT_S5
    beq cuenta
    lda BT_S0
    jsr bt_alive
    beq siguiente
cuenta:
    lda BT_S0
    jsr bt_x
    rep #$20
.a16
    lda BT_ONE + BT_AGI, x
    clc
    adc BT_T0
    sta BT_T0
    sep #$20
.a8
    inc BT_S4
siguiente:
    inc BT_S0
    bra suma
sumados:
    lda BT_S4
    bne dividir
    lda BT_S5
    beq dividir                 ; neither living nor dead: there is nobody
    stz BT_S5
    bra vuelta
dividir:
    rep #$20
.a16
    lda BT_S4
    and #$00FF
    bne hay
    lda #1
hay:
    sta temp + 2
    lda BT_T0
    sta temp
    jsr bt_div
    cmp #(BT_AGI_CAP + 1)
    bcc ready
    lda #BT_AGI_CAP
ready:
    sta BT_T1
    sep #$20
.a8
    rts
.endproc

; The chance to escape: `Scene_Battle::InitEscapeChance`.
;
;     base   = round(100 * enemy_agi / party_agi)
;     chance = clamp(150 - base, 0, 100)
;
; The rounding is `(2a + b) / (2b)`, which is `RoundTo` with integers and no
; floats: see `batalla.Batalla._chance_de_huir`.
.proc bt_flee_chance
.a8
.i16
    lda #0
    jsr bt_average
    rep #$20
.a16
    lda BT_T1
    bne grupo_hay
    lda #1
grupo_hay:
    sta BT_S1                   ; the party's average
    sep #$20
.a8
    lda #1
    jsr bt_average
    rep #$20
.a16
    lda BT_T1
    sta BT_S2                   ; the troop's
    lda #200
    sta BT_T2
    lda BT_S2
    jsr bt_mul                  ; 200 times the troop's average
    clc
    adc BT_S1
    sta temp
    lda BT_S1
    asl a
    sta temp + 2
    jsr bt_div                  ; A16 = the base
    sta BT_S3
    lda #150
    sec
    sbc BT_S3
    bpl no_negativa
    lda #0
no_negativa:
    cmp #101
    bcc chance_lista
    lda #100
chance_lista:
    sep #$20
.a8
    sta BT_ESCAPE
    rts
.endproc

; `TryEscape`: roll against the chance and, if it fails, it goes up by ten.
; Returns with A8 at 1 if the escape worked.
.proc bt_flee
.a8
.i16
    lda BT_ESCAPE
    jsr bt_pct
    bne salio
    lda BT_ESCAPE
    clc
    adc #10
    cmp #101
    bcc guarda
    lda #100
guarda:
    sta BT_ESCAPE
    lda #0
    rts
salio:
    lda #1
    rts
.endproc

; The first living actor from `BT_ACTOR` on, or A8 at $FF if none is left.
.proc bt_next_actor
.a8
.i16
busca:
    lda BT_ACTOR
    cmp BT_NACT
    bcs ninguno
    lda BT_ACTOR
    jsr bt_alive
    bne hay
    inc BT_ACTOR
    bra busca
hay:
    lda BT_ACTOR
    rts
ninguno:
    lda #$FF
    rts
.endproc

; The first living enemy, in A8, or $FF.
.proc bt_enemy_alive
.a8
.i16
    lda #0
    sta BT_S0
busca:
    lda BT_S0
    cmp BT_KID
    bcs ninguno
    lda BT_S0
    clc
    adc #BT_PARTY_MAX
    jsr bt_alive
    bne hay
    inc BT_S0
    bra busca
hay:
    lda BT_S0
    rts
ninguno:
    lda #$FF
    rts
.endproc

; Records command A8 for actor `BT_ACTOR`, with the target in `BT_T0`, and
; pushes it onto the execution list. The order it is pushed in **matters**:
; the tie-break of the turn order is stable, so the party goes first and then
; the troop, as in `batalla.Batalla.jugar_turno`.
.proc bt_record
.a8
.i16
    sta BT_S1
    lda BT_ACTOR
    asl a
    jsr bt_ax
    lda BT_S1
    sta BT_ACC, x
    lda BT_T0
    sta BT_ACC + 1, x
    lda BT_NACC
    jsr bt_ax
    lda BT_ACTOR
    sta BT_EXEC, x
    inc BT_NACC
    inc BT_ACTOR
    rts
.endproc

; The message in `BT_MTIPO` on screen, for `BT_MSG_FRAMES` frames or until
; someone presses A.
.proc bt_show
.a8
.i16
    ; Whatever sound effect was left pending does not outlive the message that
    ; left it: whoever wants one on this one records it after calling here.
    rep #$20
.a16
    lda #$FFFF
    sta BT_SE2
    sep #$20
.a8
    lda #BT_M_MESSAGE
    sta BT_MODE
    lda #BT_MSG_FRAMES
    sta BT_WAIT
    jsr bt_compose
    rts
.endproc

; What plays on the hit that was just resolved, and when.
;
; RM2k plays **two** sound effects per hit: the attack's when the action
; starts —`Normal::GetStartSe`, and only when the one hitting is an enemy—
; and the result's in the message sub-state, a few frames later. Here the
; result's is left pending in `BT_SE2` and goes out after `BT_MSG_FRAMES -
; BT_SE2_FRAMES` frames. When the one hitting is in the party there is no
; first one, so the result's plays right away. (When this was written sound
; effects had a single voice and the two together would have been just one;
; since 8c9c182 they are two, see `efectos_de_sonido.s`.)
;
; The result's comes from easyrpg and not from memory: missing is
; `GetFailureSe` —dodge_se—, hitting an actor is actor_damaged_se and an
; enemy enemy_damaged_se, unless it kills it, which is the enemy_death_se of
; `ProcessBattleActionDeath`.
.proc bt_hit_sound
.a8
.i16
    lda BT_MBLA
    jsr bt_x                    ; X: the target's offset
    rep #$20
.a16
    lda BT_MDANO
    cmp #$FFFF
    beq erro
    sep #$20
.a8
    lda BT_MBLA
    cmp #BT_PARTY_MAX
    bcc al_actor
    rep #$20
.a16
    lda BT_ONE + BT_HP, x
    beq murio
    lda #BA_SE_DANO_ENEMIGO
    bra anotado
murio:
.a16
    lda #BA_SE_MUERTE
    bra anotado
erro:
.a16
    lda #BA_SE_ERRAR
    bra anotado
al_actor:
.a8
    rep #$20
.a16
    lda #BA_SE_DANO_ACTOR
anotado:
.a16
    sta BT_SE2
    sep #$20
.a8
    lda BT_MQUIEN
    cmp #BT_PARTY_MAX
    bcs del_enemigo
    ; Someone in the party hits: RM2k gives it no attack sound effect, so the
    ; result's has nothing to wait for and goes out at once.
    rep #$20
.a16
    lda BT_SE2
    ldx #$FFFF
    stx BT_SE2
    jsl f:bt_t_sound
.a8
    rts
del_enemigo:
.a8
    rep #$20
.a16
    lda #BA_SE_ATAQUE
    jsl f:bt_t_sound
.a8
    rts
.endproc

; The turn, with the party's commands already recorded: the troop's, the
; execution order, and on to executing.
.proc bt_start_turn
.a8
.i16
    ; `NextTurn`: with the party's commands given, the turn goes up
    ; —`IncTurns`, which is what a page's turn condition looks at— and the
    ; pages can run again —`ResetPagesExecuted`—.
    rep #$20
.a16
    inc BT_TURN
    sep #$20
.a8
    jsr bt_page_turn
    lda #0
    sta BT_S0
limpia:
    lda BT_S0
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #(BAF_HAS | BAF_ACTOR | BAF_HIDDEN) ; without BAF_DEF: defending lasts
                                ; one turn
    sta BT_ONE + BT_FLAGS, x
    inc BT_S0
    lda BT_S0
    cmp #BT_COMB_MAX
    bcc limpia
    jsr bt_enemy_actions
    jsr bt_exec_order
    lda #0
    sta BT_I
    jmp bt_execute
.endproc

; A victory's experience, handed out: `ProcessSceneActionVictory` gives **the
; whole sum** to each living actor in the party —`GetActiveBattlers`, that is,
; the ones that are not dead—, it does not split it among them. The sum comes
; precomputed per troop in `tropa_exp`: every enemy in a victory is dead,
; which is what `Game_EnemyParty::GetExp` asks for. It runs on winning, from
; `bt_vic_start`, before showing anything. It clobbers `BT_S0`, `BA_T*`, A
; and X.
.proc bt_exp_allocate
.a8
.i16
    lda BT_RESULT
    cmp #BT_VICTORY
    bne ready
    lda BT_TROOP_K
    cmp #$FF
    beq ready                   ; a troop the cartridge does not carry
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_exp, x
    ldy #0                      ; the experience: see `bt_no_hidden`
    jsr bt_no_hidden
    sta BT_T1
    sep #$20
.a8
    stz BT_S0
otro:
    lda BT_S0
    cmp BT_NACT
    bcs ready
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HAS
    beq siguiente
    rep #$20
.a16
    lda BT_ONE + BT_HP, x
    sep #$20
.a8
    beq siguiente               ; dead: `Exists()` leaves it out
    lda BT_ONE + BT_NUMBER, x
    jsr exp_add
siguiente:
    inc BT_S0
    bra otro
ready:
    rts
.endproc

; The end of the turn: either the battle is over, or commands are asked for
; again.
.proc bt_end_of_turn
.a8
.i16
    jsr bt_enemy_alive
    cmp #$FF
    bne siguen
    lda #BT_VICTORY
    sta BT_RESULT
    lda #BT_MSG_VICTORY
    sta BT_MTIPO
    ; `Scene_Battle_Rpg2k`'s `BGM_Victory`. In ABL it is **the same song as
    ; the battle's** —both LDB fields say T_VGFighterMAX_Masako— so in
    ; practice it starts over; that they are two constants and not one is
    ; because the data is the game's and not ours.
    lda #BA_TEMA_FIN
    jsl f:bt_t_bgm
    jsr bt_vic_start
    jsr bt_show
    lda #BT_M_END
    sta BT_MODE
    rts
siguen:
    lda #0
    sta BT_ACTOR
    jsr bt_next_actor
    cmp #$FF
    bne otro_turno
    lda #BT_DEFEAT
    sta BT_RESULT
    lda #BT_MSG_DEFEAT
    sta BT_MTIPO
termina:
    jsr bt_show
    lda #BT_M_END
    sta BT_MODE
    rts
otro_turno:
    lda #0
    sta BT_NACC
    sta BT_COMMAND
    lda #BT_M_COMMAND
    sta BT_MODE
    ; And before asking for the commands, once more: the `eCheckEvents` of
    ; `ProcessSceneActionFightAutoEscape`. What already ran this turn does not
    ; come back —the recorded ones are cleared only when the next one
    ; starts—, so this only finds what became true after the last action.
    jsr bt_page_test
    beq sin_pagina
    lda #1
    sta BT_PAGE_TICK
    jmp bt_page_step
sin_pagina:
    jsr bt_compose
    rts
.endproc

; The next action, skipping the ones who died along the way.
.proc bt_execute
.a8
.i16
    ; Before each action, and also after the last one, the troop pages whose
    ; conditions hold: it is the `ePreAction` of `ProcessSceneActionBattle`,
    ; with its `CheckBattleEndAndScheduleEvents`. That is how the Detect Aura
    ; page runs right after Talan finishes using it and before the next one
    ; acts. When they finish, `bt_page_step` comes back here, and what already
    ; ran this turn does not run again.
    ;
    ; It goes before `otra` and not inside it: skipping one who died changes
    ; nothing a page looks at, which is also why easyrpg takes the dead off
    ; the list before checking and not after.
    jsr bt_page_test
    beq otra
    stz BT_PAGE_TICK
    jmp bt_page_step
otra:
    lda BT_I
    cmp BT_NACC
    bcc hay
    jmp bt_end_of_turn
hay:
    lda BT_I
    jsr bt_ax
    lda BT_EXEC, x
    sta BT_MQUIEN
    inc BT_I
    lda BT_MQUIEN
    jsr bt_alive
    beq otra
    lda BT_MQUIEN
    asl a
    jsr bt_ax
    lda BT_ACC, x
    sta BT_S1                   ; the command
    lda BT_ACC + 1, x
    sta BT_MBLA                 ; and the target
    lda BT_S1
    cmp #BT_DEFEND
    beq a_defiende
    cmp #BT_FLEE
    beq a_no_huyo
    cmp #BT_ITEM
    beq usa_un_item
    cmp #BT_SKILL
    beq usa_una_habilidad
    bra ataca
a_defiende:
    jmp defiende
a_no_huyo:
    jmp no_huyo
ataca:
    ; Attack. If the target died before its turn came, it is retargeted to the
    ; first living one on that side, as `Game_BattleAlgorithm` does.
    lda BT_MBLA
    jsr bt_alive
    bne pega
    lda BT_MBLA
    cmp #BT_PARTY_MAX
    bcs busca_enemigo
    lda #0
    sta BT_ACTOR
    jsr bt_next_actor
    cmp #$FF
    beq otra
    sta BT_MBLA
    bra pega
busca_enemigo:
    jsr bt_enemy_alive
    cmp #$FF
    beq otra
    clc
    adc #BT_PARTY_MAX
    sta BT_MBLA
pega:
    jsr bt_attack
    lda #BT_MSG_ATTACK
    sta BT_MTIPO
    jsr bt_show              ; which clears the pending one, so it goes first
    jmp bt_hit_sound
usa_una_habilidad:
    ; A dead target **is not retargeted**, as with an item: `Skill`'s
    ; `IsTargetValid` discards it and the action is lost. With one that
    ; targets the party that is what happens if the one about to be healed was
    ; killed first.
    lda BT_MBLA
    jsr bt_alive
    beq otra_hab
    jsr bt_skill_use
    lda #BT_MSG_SKILL
    sta BT_MTIPO
    jsr bt_show
    rep #$20
.a16
    lda #BA_SE_ITEM             ; the same as an item: RM2k has no other
    jsl f:bt_t_sound
.a8
    rts
otra_hab:
    jmp otra
usa_un_item:
    ; An item does not miss and nobody dodges it, so it rolls no dice; and a
    ; dead target **is not retargeted**, which is the opposite of an attack.
    jsr bt_item_use
    lda #BT_MSG_ITEM
    sta BT_MTIPO
    jsr bt_show
    rep #$20
.a16
    lda #BA_SE_ITEM
    jsl f:bt_t_sound
.a8
    rts
defiende:
    lda BT_MQUIEN
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    ora #BAF_DEF
    sta BT_ONE + BT_FLAGS, x
    lda #BT_MSG_DEFENDS
    sta BT_MTIPO
    jmp bt_show
no_huyo:
    lda #BT_MSG_NO_FLED
    sta BT_MTIPO
    jmp bt_show
.endproc

