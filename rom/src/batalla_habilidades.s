; --- ejecutar una habilidad -----------------------------------------------
;
; `Game_BattleAlgorithm::Skill::vStart` y `vExecute`. **El orden en que consume
; azar es el contrato con `batalla.Batalla.usar_habilidad`**: una de switch
; termina antes de cualquier tiro; después va el crítico, que se tira siempre
; aunque la chance sea cero; después la varianza; y después un tiro contra el
; acierto por cada cosa que la habilidad afecta, en el orden HP, SP, ataque,
; defensa, espíritu y agilidad.

; `Algo::VarianceAdjustEffect`: A16 = el efecto, `BA_S5` = la varianza.
;
;     adj = max(1, var * efecto / 10); efecto += rand(0, adj) - adj / 2
;
; **Sólo tira si la varianza y el efecto son mayores que cero**, que es el `if`
; de easyrpg: sin esa condición los dos lados se irían de fase en el tiro
; siguiente cada vez que pasara por acá una habilidad que no hace daño.
;
; El golpe normal tiene la suya escrita adentro de `ba_atacar` con la varianza
; en cuatro; ésta salió para las habilidades, que traen la suya en el LDB.
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
    jsr ba_mul                  ; la varianza por el efecto
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne ajuste_listo
    lda #1                      ; `max(1, ...)`
ajuste_listo:
    sta BA_T1
    jsr ba_hasta                ; A16 sigue siendo el ajuste
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

; Un modificador de parámetro se mueve `BA_MEFECTO` y el parámetro efectivo se
; rehace: `CanChangeAtkModifier` y sus hermanas, más `AdjustParam`.
;
;   BA_S4 = el desplazamiento del blanco adentro de `BA_UNO`
;   BA_S5 = el del modificador, BA_S6 = el del base, BA_T1 = el del efectivo
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
    sta temp                    ; el modificador que se pide
    lda BA_S4
    clc
    adc BA_S6
    tax
    lda BA_UNO, x
    sta BA_T0                   ; el parámetro base. **Las dos de paso son
                                ; `BA_T0` y `BA_T2` y no `BA_S2` y `BA_S3`**:
                                ; el que llama lleva en `BA_S3` qué toca la
                                ; habilidad y en `BA_S0` su acierto, y los
                                ; necesita en las cuatro vueltas
    ; El tope de arriba es el base, y el de abajo su mitad con signo menos.
    ; Los números de este juego andan en centenas, así que el `bmi` sobre la
    ; resta alcanza: nada se acerca a los 32768 donde se daría vuelta.
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
    sta BA_UNO, x               ; el modificador nuevo
    clc
    adc BA_T0                   ; base + modificador
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

; Prende el switch de `BA_T0`, que es el `switch_id` del LDB tal cual, como
; hace `item_switch` con el suyo. No se llama a `poner_switch`: vive en el
; banco 0 y la pelea corre con el banco de datos en $7E, así que la máscara se
; arma acá con un corrimiento en vez de leerse de una tabla del cartucho.
.proc ba_switch
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    lsr a
    lsr a
    lsr a
    tax                         ; qué byte del bitmap
    lda BA_T0
    and #$0007
    tay                         ; y qué bit
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
    sta refresco                ; las páginas que lo piden pueden cambiar
    rts
.endproc

; El efecto de la habilidad `BA_MHAB` de `BA_MQUIEN` sobre `BA_MBLA`, **sin la
; varianza**: `Algo::CalcSkillEffect`. Deja el resultado en `BA_MEFECTO`, ya
; recortado por abajo en cero.
.proc ba_hab_efecto
.a8
.i16
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; el desplazamiento de la fuente
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; y el del blanco
    ; el `k` de la habilidad, por dos para las tablas de palabra
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_power, x
    sta BA_S2                   ; el acumulador del efecto
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
    ; Contra un enemigo y sin `ignore_defense`, se le restan su defensa y su
    ; espíritu. `SkillTargetsEnemies` es el bit 6 de `hab_afecta` y el bit 7 es
    ; `ignore_defense`.
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
    ; El crítico, que para una habilidad del LDB **siempre da que no**: la
    ; chance que `CalcCriticalHitChance` recibe es
    ; `easyrpg_critical_hit_chance`, que vale 0 y no -1. El tiro se hace igual,
    ; porque si no los dos lados se irían de fase.
    lda #0
    jsr ba_pct
    beq sin_critico
    rep #$20
.a16
    lda BA_MEFECTO
    sta temp
    asl a
    clc
    adc temp                    ; por tres
    sta BA_MEFECTO
    sep #$20
.a8
sin_critico:
    rts
.endproc

; Los HP del blanco se mueven `BA_MEFECTO`. Curar no mata —el
; `max(-(cur_hp - 1), hp_effect)` de `vExecute`— y el daño lo parte al medio el
; que se está defendiendo, con la división de C++, que **trunca hacia cero**.
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
    inc a                       ; la mitad truncada hacia cero
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

; Y los SP, igual pero sin defensa que valga. Ninguna de las siete lo usa; está
; porque `vExecute` lo hace y porque el tiro que lo precede ya se hizo.
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

; La habilidad que eligió `BA_MQUIEN`, sobre `BA_MBLA`. Deja el mensaje listo.
.proc ba_hab_usar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_ax
    lda BA_ACC_HAB, x
    sta BA_MHAB
    ; --- `vStart`: el costo, antes que nada y sin tirar azar ---
    jsr ba_hab_costo
    sta BA_T2
    stz BA_T2 + 1               ; la resta de abajo es de dieciséis bits y
                                ; `hab_sp` es de ocho: sin esto el byte de
                                ; arriba es el que dejó el que pasó por acá
                                ; antes, y los SP quedaban en cero
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_ok
    lda #0                      ; no puede pasar: sin SP no se elige
sp_ok:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
    ; --- una de switch prende su switch y no hace nada más ---
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
    jsr ba_hab_efecto
    ; la varianza, con el `variance` de la habilidad
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_var, x
    sta BA_S5
    rep #$20
.a16
    lda BA_MEFECTO
    jsr ba_varianza
    ; el tope del daño, que es el mismo de un golpe
    cmp #(BA_DANO_MAX + 1)
    bcc efecto_cabe
    lda #BA_DANO_MAX
efecto_cabe:
    sta BA_MEFECTO
    sep #$20
.a8
    ; Si apunta a enemigos el efecto es negativo: `SetIsPositive` es
    ; `SkillTargetsAllies`, y `vExecute` da vuelta el signo cuando no lo es.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_afecta, x
    sta BA_S3                   ; qué toca, que ya no se vuelve a leer
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
    ; el acierto, que las siete traen en 100
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_hit, x
    sta BA_S0                   ; el acierto, que sobrevive a los `jsr`
    ; --- los HP ---
    lda BA_S3
    and #$01
    beq sin_hp
    lda BA_S0
    jsr ba_pct
    beq sin_hp
    jsr ba_hab_hp
sin_hp:
    ; --- los SP ---
    ;
    ; Ninguna de las siete que el grupo de la intro sabe los toca, **pero el
    ; tiro va igual**: `vExecute` lo hace y sacarlo desfasaría el azar.
    lda BA_S3
    and #$02
    beq sin_sp
    lda BA_S0
    jsr ba_pct
    beq sin_sp
    jsr ba_hab_sp
sin_sp:
    ; --- los cuatro parámetros, en el orden de `vExecute` ---
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
    cmp #BA_MSG_VICTORIA
    beq victoria
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
victoria:
    ldx #BA_TXT_VICTORIA
    jmp solo
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
    ; El segundo renglón: el resultado sobre el blanco.
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
    ; `<nombre> <daño> health lost.`
    lda #$20                    ; el espacio entre el nombre y el número
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
    ; `<quien> <ítem> used.`, que es
    ; `source.GetName() + " " + item.name + terms.use_item` de
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
    adc BA_T0                   ; por tres: `3k` es el nombre del ítem
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ldx #BA_TXT_USO
    jsr ba_termino
    ; `<blanco> HP <n> Recovered`, que es `GetHpSpRecoveredMessage`.
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
    ; `<quien><using_message1>` arriba y `<using_message2>` abajo, que es
    ; `GetSkillFirstStartMessage2k` y su hermana. Los dos renglones son del
    ; LDB, como todo lo que esta pantalla escribe.
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

; --- las habilidades en la pelea -------------------------------------------
;
; `Game_BattleAlgorithm::Skill` con lo que este port sabe hacer. Qué sabe cada
; actor al empezar, cuánto cuesta y cuánto hace **no se decide acá**: sale de
; `batalla.habilidades_de`, `batalla.costo_de` y `batalla.efecto_habilidad`,
; que es el modelo con el que `pruebas/rpgmaker/test_batalla.py` predice el número
; exacto, y el conversor lo emite en `hab_par_*` y `hab_*`. Lo que sabe
; **ahora** es `FAR_HAB`, que `ChangeSkills` mueve.

; A8 = el número de actor del LDB del combatiente `BA_ACTOR`. Es lo que indexa
; `hab_par_ini`, `hab_par_n` y `actor_hab_txt`, que son por número de actor y
; no por lugar en el grupo.
.proc ba_actor_ldb
.a8
.i16
    lda BA_ACTOR
    jsr ba_x
    lda BA_UNO + BA_NUMERO, x
    rts
.endproc

; La lista de habilidades del actor que está ordenando, a `BA_HAB_LISTA`, con
; cuántas en `BA_HAB_N`. Son sus pares de `FAR_HAB` con el bit prendido —lo que
; sabe **ahora**, que `ChangeSkills` mueve— y que la pelea sabe ofrecer, o sea
; con un `k` en `hab_par_k`. Los pares de un actor van seguidos y por número de
; habilidad, así que la lista sale en el orden de `LearnSkill`. Se lleva
; `BA_S1`, `BA_S2`, `BA_T0` y X.
.proc ba_hab_lista
.a8
.i16
    lda #0
    sta BA_HAB_N
    jsr ba_actor_ldb
    jsr ba_ax
    lda f:hab_par_n, x
    beq listo
    sta BA_S1                   ; cuántos pares le quedan por mirar
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:hab_par_ini, x
    sta BA_S2                   ; la ranura del par que se mira
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
    sta BA_T0                   ; su bit
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
    beq siguiente               ; no la sabe
    ldx BA_S2
    lda f:hab_par_k, x
    cmp #$FF
    beq siguiente               ; la sabe y la pelea no la ofrece
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

; El `k` del lugar A8 de la lista. Sólo A y X.
.proc ba_hab_de_lista
.a8
.i16
    jsr ba_ax
    lda BA_HAB_LISTA, x
    rts
.endproc

; El costo en SP del `k` de A8, en A8. `Algo::CalcSkillCost`: el `sp_cost` a
; secas, que es lo que RM2k hace.
.proc ba_hab_costo
.a8
.i16
    jsr ba_ax
    lda f:hab_sp, x
    rts
.endproc

; Si el combatiente `BA_ACTOR` puede pagar el `k` de A8: Z=0 si sí. **No usa el
; flag que deja un `pl*`**: la trampa de siempre.
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
    beq si                      ; justo los que tiene alcanza
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; La pantalla entera, en `texto_buf`.
.proc ba_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    ; --- los enemigos, o la lista de ítems mientras se elige uno ---
    ;
    ; Van en los mismos renglones a propósito: eligiendo qué usar lo que hace
    ; falta ver es el grupo, que es a quién se cura, y no los enemigos.
    ; **Eligiendo a quién se le da, arriba va la lista de la orden en curso**:
    ; la de ítems o la de habilidades, en gris las dos. Cuál de las dos lo dice
    ; `BA_ORDEN`, que sigue puesto mientras se elige el blanco.
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
    stz BA_CONMAX               ; un enemigo no muestra su máximo
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_renglon
    inc BA_S0
    bra enemigo
enemigos_listos:
    ; --- el grupo ---
    ;
    ; Salvo que haya un mensaje de una página de tropa, que va en sus renglones:
    ; en RM2k la ventana de mensaje de la pelea tapa la del grupo. Ver
    ; `ba_pag_mensaje`.
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
    cmp BA_ITEM_BLA             ; eligiendo a quién curar
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
    ; --- el último renglón ---
    ;
    ; Que corriendo una página queda vacío: el mensaje de la acción anterior
    ; ya se leyó, y el de la página va arriba.
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
    ; En qué renglón cae ésta: desde el 2026-09-13 son cinco y van en dos.
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
    ; En gris mientras se elige otra cosa —el menú ya no manda— y siempre la
    ; que no está hecha, que es lo que el menú de pausa hace con las suyas.
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne en_gris
    lda BA_S0
    jsr ba_ax
    lda f:ba_orden_gris, x
    bne en_gris
    ; Y la habilidad de un actor que no sabe ninguna —Talan, que es de nivel
    ; 1— también va en gris, como el menú de pausa con lo que no lleva a
    ; ningún lado.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    bne sin_gris_orden
    jsr ba_hab_lista            ; lo que sabe ahora: ver `FAR_HAB`
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
    lda #$3E                    ; el cursor
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
    ; **La segunda orden no dice "Tech Skill"**: dice el `skill_name` del actor
    ; que está ordenando —"AgentTrain", "Telepathy", "Slicing"—, que es
    ; `Game_Actor::GetSkillName`. Por eso su texto sale de `actor_hab_txt`, que
    ; es por número de actor, y no de `ba_orden_txt`, que es fijo.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    beq texto_de_la_habilidad
    ; **De dos bytes**, como `actor_hab_txt` y `enemigo_txt`: el índice de un
    ; texto no entra en uno. Con los 29 mapas de `abl` los textos de la
    ; batalla arrancan en el 273, así que la tabla de un byte que estaba acá
    ; hasta el 2026-09-14 los truncaba a 17, 18, 19 y 32, que son renglones de
    ; la descripción de un ítem: el menú dibujaba cuatro textos largos, uno
    ; encima del otro. Ningún cartucho de la tanda llega a 256 textos.
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

    ; --- la lista de ítems, donde van los enemigos ---
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
    sta BA_S6                   ; el lugar en la lista
    rep #$20
.a16
    lda #BA_ENEMIGO_POS0
    jsr ba_fila
    sep #$20
.a8
    ; El cursor, sólo mientras se elige el ítem: eligiendo el blanco la lista
    ; queda en gris y el cursor se va al grupo.
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
    ; el nombre
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
    sta BA_S1                   ; el `k`
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; por tres: `3k` es el nombre
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; y cuántos hay, con los dos puntos adelante
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
    lda #$3A                    ; los dos puntos
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

    ; --- la lista de habilidades, donde van los enemigos ---
    ;
    ; La forma es la del original —la de una captura del juego de verdad, del
    ; 2026-09-12—: la descripción de la que marca el cursor arriba de todo, y
    ; abajo dos columnas con el nombre a la izquierda y el costo en SP a la
    ; derecha, con un guión delante. Se lee **por filas**, que es lo que la captura muestra.
la_lista_hab:
    jsr ba_hab_lista
    lda BA_HAB_N
    bne hay_alguna
    jmp hab_listas
hay_alguna:
    lda BA_MODO
    cmp #BA_M_HAB
    bne hab_en_gris             ; eligiendo el blanco: sin descripción
    ; la descripción de la que marca el cursor
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
    sta BA_S3                   ; el lugar en la lista
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
    ; Fila y columna: con dos columnas son un `lsr` y el bit 0. Si alguna vez
    ; fueran otras, esto es lo que hay que cambiar; el conversor emite
    ; `BA_HAB_COLUMNAS` para que se vea desde acá que son dos.
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
    sta BA_S5                   ; el desplazamiento de la columna
    sep #$20
.a8
    ; El `k` de esta habilidad, y si se puede pagar: la que no alcanza va en
    ; gris, que es lo que RM2k hace con una que no se puede usar.
    lda BA_S3
    jsr ba_hab_de_lista
    sta BA_S6
    lda BA_MODO
    cmp #BA_M_HAB
    bne gris_hab                ; eligiendo el blanco, la lista entera en gris
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
    ; el cursor, sólo mientras se elige la habilidad
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
    ; el nombre
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
    ; el guión y el costo
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
    lda #$2D                    ; el guión
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

