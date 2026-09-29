.segment "FAR"

; --- the battle loop -------------------------------------------------------

; The average agility of one side: A8 at 0 the party and at 1 the troop. If
; nobody is left alive everyone counts, which is the `or list(quienes)` of
; `batalla.Batalla._promedio`. The result goes in `BA_T1`, capped at
; `BA_AGI_TOPE`: through memory and not the accumulator, for the same reason
; as `ba_param`.
.proc ba_promedio
.a8
.i16
    sta BA_S6
    ; Two passes: the first counts only the living and, if there were none,
    ; the second counts everyone.
    lda #1
    sta BA_S5                   ; only the living?
vuelta:
    rep #$20
.a16
    lda #0
    sta BA_T0                   ; the sum
    sep #$20
.a8
    lda #0
    sta BA_S4                   ; how many
    lda BA_S6
    beq desde_el_grupo
    lda #BA_GRUPO_MAX
    sta BA_S0
    lda BA_NENE
    clc
    adc #BA_GRUPO_MAX
    sta BA_S3
    bra suma
desde_el_grupo:
    lda #0
    sta BA_S0
    lda BA_NACT
    sta BA_S3
suma:
    lda BA_S0
    cmp BA_S3
    bcs sumados
    lda BA_S5
    beq cuenta
    lda BA_S0
    jsr ba_vivo
    beq siguiente
cuenta:
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_T0
    sta BA_T0
    sep #$20
.a8
    inc BA_S4
siguiente:
    inc BA_S0
    bra suma
sumados:
    lda BA_S4
    bne dividir
    lda BA_S5
    beq dividir                 ; neither living nor dead: there is nobody
    stz BA_S5
    bra vuelta
dividir:
    rep #$20
.a16
    lda BA_S4
    and #$00FF
    bne hay
    lda #1
hay:
    sta temp + 2
    lda BA_T0
    sta temp
    jsr ba_div
    cmp #(BA_AGI_TOPE + 1)
    bcc listo
    lda #BA_AGI_TOPE
listo:
    sta BA_T1
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
.proc ba_chance_huir
.a8
.i16
    lda #0
    jsr ba_promedio
    rep #$20
.a16
    lda BA_T1
    bne grupo_hay
    lda #1
grupo_hay:
    sta BA_S1                   ; the party's average
    sep #$20
.a8
    lda #1
    jsr ba_promedio
    rep #$20
.a16
    lda BA_T1
    sta BA_S2                   ; the troop's
    lda #200
    sta BA_T2
    lda BA_S2
    jsr ba_mul                  ; 200 times the troop's average
    clc
    adc BA_S1
    sta temp
    lda BA_S1
    asl a
    sta temp + 2
    jsr ba_div                  ; A16 = the base
    sta BA_S3
    lda #150
    sec
    sbc BA_S3
    bpl no_negativa
    lda #0
no_negativa:
    cmp #101
    bcc chance_lista
    lda #100
chance_lista:
    sep #$20
.a8
    sta BA_HUIDA
    rts
.endproc

; `TryEscape`: roll against the chance and, if it fails, it goes up by ten.
; Returns with A8 at 1 if the escape worked.
.proc ba_huir
.a8
.i16
    lda BA_HUIDA
    jsr ba_pct
    bne salio
    lda BA_HUIDA
    clc
    adc #10
    cmp #101
    bcc guarda
    lda #100
guarda:
    sta BA_HUIDA
    lda #0
    rts
salio:
    lda #1
    rts
.endproc

; The first living actor from `BA_ACTOR` on, or A8 at $FF if none is left.
.proc ba_actor_siguiente
.a8
.i16
busca:
    lda BA_ACTOR
    cmp BA_NACT
    bcs ninguno
    lda BA_ACTOR
    jsr ba_vivo
    bne hay
    inc BA_ACTOR
    bra busca
hay:
    lda BA_ACTOR
    rts
ninguno:
    lda #$FF
    rts
.endproc

; The first living enemy, in A8, or $FF.
.proc ba_enemigo_vivo
.a8
.i16
    lda #0
    sta BA_S0
busca:
    lda BA_S0
    cmp BA_NENE
    bcs ninguno
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne hay
    inc BA_S0
    bra busca
hay:
    lda BA_S0
    rts
ninguno:
    lda #$FF
    rts
.endproc

; Records command A8 for actor `BA_ACTOR`, with the target in `BA_T0`, and
; pushes it onto the execution list. The order it is pushed in **matters**:
; the tie-break of the turn order is stable, so the party goes first and then
; the troop, as in `batalla.Batalla.jugar_turno`.
.proc ba_anotar
.a8
.i16
    sta BA_S1
    lda BA_ACTOR
    asl a
    jsr ba_ax
    lda BA_S1
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACC
    jsr ba_ax
    lda BA_ACTOR
    sta BA_EJEC, x
    inc BA_NACC
    inc BA_ACTOR
    rts
.endproc

; The message in `BA_MTIPO` on screen, for `BA_MSG_CUADROS` frames or until
; someone presses A.
.proc ba_mostrar
.a8
.i16
    ; Whatever sound effect was left pending does not outlive the message that
    ; left it: whoever wants one on this one records it after calling here.
    rep #$20
.a16
    lda #$FFFF
    sta BA_SE2
    sep #$20
.a8
    lda #BA_M_MENSAJE
    sta BA_MODO
    lda #BA_MSG_CUADROS
    sta BA_ESPERA
    jsr ba_componer
    rts
.endproc

; What plays on the hit that was just resolved, and when.
;
; RM2k plays **two** sound effects per hit: the attack's when the action
; starts —`Normal::GetStartSe`, and only when the one hitting is an enemy—
; and the result's in the message sub-state, a few frames later. Here the
; result's is left pending in `BA_SE2` and goes out after `BA_MSG_CUADROS -
; BA_SE2_CUADROS` frames. When the one hitting is in the party there is no
; first one, so the result's plays right away. (When this was written sound
; effects had a single voice and the two together would have been just one;
; since 8c9c182 they are two, see `efectos_de_sonido.s`.)
;
; The result's comes from easyrpg and not from memory: missing is
; `GetFailureSe` —dodge_se—, hitting an actor is actor_damaged_se and an
; enemy enemy_damaged_se, unless it kills it, which is the enemy_death_se of
; `ProcessBattleActionDeath`.
.proc ba_sonido_del_golpe
.a8
.i16
    lda BA_MBLA
    jsr ba_x                    ; X: the target's offset
    rep #$20
.a16
    lda BA_MDANO
    cmp #$FFFF
    beq erro
    sep #$20
.a8
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcc al_actor
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
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
    sta BA_SE2
    sep #$20
.a8
    lda BA_MQUIEN
    cmp #BA_GRUPO_MAX
    bcs del_enemigo
    ; Someone in the party hits: RM2k gives it no attack sound effect, so the
    ; result's has nothing to wait for and goes out at once.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sonido
.a8
    rts
del_enemigo:
.a8
    rep #$20
.a16
    lda #BA_SE_ATAQUE
    jsl f:ba_t_sonido
.a8
    rts
.endproc

; The turn, with the party's commands already recorded: the troop's, the
; execution order, and on to executing.
.proc ba_empezar_turno
.a8
.i16
    ; `NextTurn`: with the party's commands given, the turn goes up
    ; —`IncTurns`, which is what a page's turn condition looks at— and the
    ; pages can run again —`ResetPagesExecuted`—.
    rep #$20
.a16
    inc BA_TURNO
    sep #$20
.a8
    jsr ba_pag_turno
    lda #0
    sta BA_S0
limpia:
    lda BA_S0
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #(BAF_HAY | BAF_ACTOR | BAF_OCULTO) ; without BAF_DEF: defending lasts
                                ; one turn
    sta BA_UNO + BA_FLAGS, x
    inc BA_S0
    lda BA_S0
    cmp #BA_COMB_MAX
    bcc limpia
    jsr ba_acciones_enemigas
    jsr ba_orden_ejecucion
    lda #0
    sta BA_I
    jmp ba_ejecutar
.endproc

; A victory's experience, handed out: `ProcessSceneActionVictory` gives **the
; whole sum** to each living actor in the party —`GetActiveBattlers`, that is,
; the ones that are not dead—, it does not split it among them. The sum comes
; precomputed per troop in `tropa_exp`: every enemy in a victory is dead,
; which is what `Game_EnemyParty::GetExp` asks for. It runs on winning, from
; `ba_vic_empezar`, before showing anything. It clobbers `BA_S0`, `BA_T*`, A
; and X.
.proc ba_exp_repartir
.a8
.i16
    lda BA_RESULT
    cmp #BA_VICTORIA
    bne listo
    lda BA_TROPA_K
    cmp #$FF
    beq listo                   ; a troop the cartridge does not carry
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_exp, x
    ldy #0                      ; the experience: see `ba_sin_ocultos`
    jsr ba_sin_ocultos
    sta BA_T1
    sep #$20
.a8
    stz BA_S0
otro:
    lda BA_S0
    cmp BA_NACT
    bcs listo
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq siguiente
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sep #$20
.a8
    beq siguiente               ; dead: `Exists()` leaves it out
    lda BA_UNO + BA_NUMERO, x
    jsr exp_sumar
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; The end of the turn: either the battle is over, or commands are asked for
; again.
.proc ba_fin_de_turno
.a8
.i16
    jsr ba_enemigo_vivo
    cmp #$FF
    bne siguen
    lda #BA_VICTORIA
    sta BA_RESULT
    lda #BA_MSG_VICTORIA
    sta BA_MTIPO
    ; `Scene_Battle_Rpg2k`'s `BGM_Victory`. In ABL it is **the same song as
    ; the battle's** —both LDB fields say T_VGFighterMAX_Masako— so in
    ; practice it starts over; that they are two constants and not one is
    ; because the data is the game's and not ours.
    lda #BA_TEMA_FIN
    jsl f:ba_t_bgm
    jsr ba_vic_empezar
    jsr ba_mostrar
    lda #BA_M_FIN
    sta BA_MODO
    rts
siguen:
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    bne otro_turno
    lda #BA_DERROTA
    sta BA_RESULT
    lda #BA_MSG_DERROTA
    sta BA_MTIPO
termina:
    jsr ba_mostrar
    lda #BA_M_FIN
    sta BA_MODO
    rts
otro_turno:
    lda #0
    sta BA_NACC
    sta BA_ORDEN
    lda #BA_M_ORDEN
    sta BA_MODO
    ; And before asking for the commands, once more: the `eCheckEvents` of
    ; `ProcessSceneActionFightAutoEscape`. What already ran this turn does not
    ; come back —the recorded ones are cleared only when the next one
    ; starts—, so this only finds what became true after the last action.
    jsr ba_pag_probar
    beq sin_pagina
    lda #1
    sta BA_PAG_VUELTA
    jmp ba_pag_paso
sin_pagina:
    jsr ba_componer
    rts
.endproc

; The next action, skipping the ones who died along the way.
.proc ba_ejecutar
.a8
.i16
    ; Before each action, and also after the last one, the troop pages whose
    ; conditions hold: it is the `ePreAction` of `ProcessSceneActionBattle`,
    ; with its `CheckBattleEndAndScheduleEvents`. That is how the Detect Aura
    ; page runs right after Talan finishes using it and before the next one
    ; acts. When they finish, `ba_pag_paso` comes back here, and what already
    ; ran this turn does not run again.
    ;
    ; It goes before `otra` and not inside it: skipping one who died changes
    ; nothing a page looks at, which is also why easyrpg takes the dead off
    ; the list before checking and not after.
    jsr ba_pag_probar
    beq otra
    stz BA_PAG_VUELTA
    jmp ba_pag_paso
otra:
    lda BA_I
    cmp BA_NACC
    bcc hay
    jmp ba_fin_de_turno
hay:
    lda BA_I
    jsr ba_ax
    lda BA_EJEC, x
    sta BA_MQUIEN
    inc BA_I
    lda BA_MQUIEN
    jsr ba_vivo
    beq otra
    lda BA_MQUIEN
    asl a
    jsr ba_ax
    lda BA_ACC, x
    sta BA_S1                   ; the command
    lda BA_ACC + 1, x
    sta BA_MBLA                 ; and the target
    lda BA_S1
    cmp #BA_DEFENDER
    beq a_defiende
    cmp #BA_HUIR
    beq a_no_huyo
    cmp #BA_ITEM
    beq usa_un_item
    cmp #BA_HABILIDAD
    beq usa_una_habilidad
    bra ataca
a_defiende:
    jmp defiende
a_no_huyo:
    jmp no_huyo
ataca:
    ; Attack. If the target died before its turn came, it is retargeted to the
    ; first living one on that side, as `Game_BattleAlgorithm` does.
    lda BA_MBLA
    jsr ba_vivo
    bne pega
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs busca_enemigo
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    beq otra
    sta BA_MBLA
    bra pega
busca_enemigo:
    jsr ba_enemigo_vivo
    cmp #$FF
    beq otra
    clc
    adc #BA_GRUPO_MAX
    sta BA_MBLA
pega:
    jsr ba_atacar
    lda #BA_MSG_ATAQUE
    sta BA_MTIPO
    jsr ba_mostrar              ; which clears the pending one, so it goes first
    jmp ba_sonido_del_golpe
usa_una_habilidad:
    ; A dead target **is not retargeted**, as with an item: `Skill`'s
    ; `IsTargetValid` discards it and the action is lost. With one that
    ; targets the party that is what happens if the one about to be healed was
    ; killed first.
    lda BA_MBLA
    jsr ba_vivo
    beq otra_hab
    jsr ba_hab_usar
    lda #BA_MSG_HAB
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_ITEM             ; the same as an item: RM2k has no other
    jsl f:ba_t_sonido
.a8
    rts
otra_hab:
    jmp otra
usa_un_item:
    ; An item does not miss and nobody dodges it, so it rolls no dice; and a
    ; dead target **is not retargeted**, which is the opposite of an attack.
    jsr ba_item_usar
    lda #BA_MSG_ITEM
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_ITEM
    jsl f:ba_t_sonido
.a8
    rts
defiende:
    lda BA_MQUIEN
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    ora #BAF_DEF
    sta BA_UNO + BA_FLAGS, x
    lda #BA_MSG_DEFIENDE
    sta BA_MTIPO
    jmp ba_mostrar
no_huyo:
    lda #BA_MSG_NO_HUYO
    sta BA_MTIPO
    jmp ba_mostrar
.endproc

