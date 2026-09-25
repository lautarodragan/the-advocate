.segment "FAR"

; --- el lazo de la pelea --------------------------------------------------

; El promedio de agilidad de un lado: A8 en 0 el grupo y en 1 la tropa. Si no
; queda nadie vivo cuentan todos, que es el `or list(quienes)` de
; `batalla.Batalla._promedio`. El resultado va en `BA_T1`, topado en
; `BA_AGI_TOPE`: por memoria y no por el acumulador, por lo mismo que
; `ba_param`.
.proc ba_promedio
.a8
.i16
    sta BA_S6
    ; Dos vueltas: la primera cuenta sólo a los vivos y, si no hubo ninguno,
    ; la segunda cuenta a todos.
    lda #1
    sta BA_S5                   ; ¿sólo los vivos?
vuelta:
    rep #$20
.a16
    lda #0
    sta BA_T0                   ; la suma
    sep #$20
.a8
    lda #0
    sta BA_S4                   ; cuántos
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
    beq dividir                 ; ni vivos ni muertos: no hay nadie
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

; La chance de escapar: `Scene_Battle::InitEscapeChance`.
;
;     base   = redondear(100 * agi_enemigos / agi_grupo)
;     chance = recortar(150 - base, 0, 100)
;
; El redondeo es `(2a + b) / (2b)`, que es `RoundTo` con enteros y sin
; flotantes: ver `batalla.Batalla._chance_de_huir`.
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
    sta BA_S1                   ; el promedio del grupo
    sep #$20
.a8
    lda #1
    jsr ba_promedio
    rep #$20
.a16
    lda BA_T1
    sta BA_S2                   ; el de la tropa
    lda #200
    sta BA_T2
    lda BA_S2
    jsr ba_mul                  ; 200 por el promedio de la tropa
    clc
    adc BA_S1
    sta temp
    lda BA_S1
    asl a
    sta temp + 2
    jsr ba_div                  ; A16 = la base
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

; `TryEscape`: se tira contra la chance y, si falla, sube diez. Vuelve con A8
; en 1 si se escapó.
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

; El primer actor vivo desde `BA_ACTOR`, o A8 en $FF si no queda ninguno.
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

; El primer enemigo vivo, en A8, o $FF.
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

; Le anota la orden A8 al actor `BA_ACTOR`, con el blanco de `BA_T0`, y la
; apila en la lista de ejecución. El orden en que se apila **importa**: el
; desempate del orden de turnos es estable, así que primero va el grupo y
; después la tropa, como en `batalla.Batalla.jugar_turno`.
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

; El mensaje de `BA_MTIPO` en pantalla, por `BA_MSG_CUADROS` cuadros o hasta
; que alguien apriete A.
.proc ba_mostrar
.a8
.i16
    ; El efecto que hubiera quedado pendiente no sobrevive al mensaje que lo
    ; dejó: quien quiera uno en éste lo anota después de llamar acá.
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

; Qué suena en el golpe que se acaba de resolver, y cuándo.
;
; RM2k toca **dos** efectos por golpe: el del ataque al empezar la acción
; —`Normal::GetStartSe`, y sólo cuando el que pega es un enemigo— y el del
; resultado en el sub-estado del mensaje, unos cuadros más tarde. Acá el del
; resultado queda pendiente en `BA_SE2` y sale a los `BA_MSG_CUADROS -
; BA_SE2_CUADROS` cuadros. Cuando el que pega es del grupo no hay primero, así
; que el del resultado suena ya. (Cuando esto se escribió los efectos tenían
; una sola voz y los dos juntos habrían sido uno solo; desde 8c9c182 son dos,
; ver `efectos_de_sonido.s`.)
;
; El del resultado sale de easyrpg y no de memoria: errar es `GetFailureSe`
; —dodge_se—, pegarle a un actor es actor_damaged_se y a un enemigo
; enemy_damaged_se, salvo que lo mate, que es el enemy_death_se de
; `ProcessBattleActionDeath`.
.proc ba_sonido_del_golpe
.a8
.i16
    lda BA_MBLA
    jsr ba_x                    ; X: el desplazamiento del blanco
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
    ; Pega alguien del grupo: RM2k no le pone efecto de ataque, así que el del
    ; resultado no tiene a qué esperar y sale en el acto.
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

; El turno, ya con las órdenes del grupo anotadas: las de la tropa, el orden de
; ejecución, y a ejecutar.
.proc ba_empezar_turno
.a8
.i16
    ; `NextTurn`: con las órdenes del grupo dadas, las páginas pueden volver a
    ; correr —`ResetPagesExecuted`—.
    jsr ba_pag_turno
    lda #0
    sta BA_S0
limpia:
    lda BA_S0
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #(BAF_HAY | BAF_ACTOR)   ; sin BAF_DEF: la defensa dura un turno
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

; La experiencia de una victoria, repartida: `ProcessSceneActionVictory` le da
; **la suma entera** a cada actor vivo del grupo —`GetActiveBattlers`, o sea los
; que no están muertos—, no la divide entre ellos. La suma ya viene hecha por
; tropa en `tropa_exp`: todos los enemigos de una victoria están muertos, que es
; lo que `Game_EnemyParty::GetExp` pide. Corre al cerrar la pelea, con los HP ya
; de vuelta en la partida. Se lleva `BA_S0`, `BA_T*`, A y X.
.proc ba_exp_repartir
.a8
.i16
    lda BA_RESULT
    cmp #BA_VICTORIA
    bne listo
    lda BA_TROPA_K
    cmp #$FF
    beq listo                   ; una tropa que el cartucho no lleva
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_exp, x
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
    beq siguiente               ; muerto: `Exists()` lo deja afuera
    lda BA_UNO + BA_NUMERO, x
    jsr exp_sumar
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; El fin del turno: o se acabó la pelea, o se vuelve a pedir órdenes.
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
    ; El `BGM_Victory` de `Scene_Battle_Rpg2k`. En el ABL es **el mismo tema
    ; que el de la pelea** —los dos campos del LDB dicen T_VGFighterMAX_Masako—
    ; así que en la práctica vuelve a empezar; que sean dos constantes y no una
    ; es porque el dato es del juego y no nuestro.
    lda #BA_TEMA_FIN
    jsl f:ba_t_bgm
    bra termina
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
    ; Y antes de pedir las órdenes, otra vez: el `eCheckEvents` de
    ; `ProcessSceneActionFightAutoEscape`. Lo que ya corrió en el turno no
    ; vuelve —las anotadas se borran recién al empezar el que viene—, así que
    ; esto sólo encuentra lo que se cumplió después de la última acción.
    jsr ba_pag_probar
    beq sin_pagina
    lda #1
    sta BA_PAG_VUELTA
    jmp ba_pag_paso
sin_pagina:
    jsr ba_componer
    rts
.endproc

; La acción que sigue, salteando a los que murieron en el camino.
.proc ba_ejecutar
.a8
.i16
    ; Antes de cada acción, y también después de la última, las páginas de la
    ; tropa que se cumplan: es el `ePreAction` de
    ; `ProcessSceneActionBattle`, con su `CheckBattleEndAndScheduleEvents`.
    ; Así es como la página de Detect Aura corre apenas Talan termina de usarla
    ; y antes de que actúe el que sigue. Cuando terminan, `ba_pag_paso` vuelve
    ; acá, y lo que ya corrió en el turno no vuelve a correr.
    ;
    ; Va antes de `otra` y no adentro: saltear a uno que murió no cambia nada
    ; de lo que una página mira, que es también por qué easyrpg saca a los
    ; muertos de la lista antes de probar y no después.
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
    sta BA_S1                   ; la orden
    lda BA_ACC + 1, x
    sta BA_MBLA                 ; y el blanco
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
    ; Atacar. Si el blanco murió antes de que le tocara, se reapunta al primero
    ; vivo de ese lado, como hace `Game_BattleAlgorithm`.
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
    jsr ba_mostrar              ; que limpia el pendiente, así que va antes
    jmp ba_sonido_del_golpe
usa_una_habilidad:
    ; El blanco muerto **no se reapunta**, como con un ítem: `IsTargetValid`
    ; de `Skill` lo descarta y la acción se pierde. Con una que apunta al
    ; grupo eso es lo que pasa si al que se iba a curar lo mataron antes.
    lda BA_MBLA
    jsr ba_vivo
    beq otra_hab
    jsr ba_hab_usar
    lda #BA_MSG_HAB
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_ITEM             ; el mismo que un ítem: RM2k no tiene otro
    jsl f:ba_t_sonido
.a8
    rts
otra_hab:
    jmp otra
usa_un_item:
    ; El ítem no falla ni lo esquiva nadie, así que no tira azar; y el blanco
    ; muerto **no se reapunta**, que es lo contrario de un ataque.
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

