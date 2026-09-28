.segment "FAR"

; --- las páginas de evento de la tropa ----------------------------------------
;
; `Game_Interpreter_Battle`: cada tropa trae sus páginas, y una corre cuando
; se cumple su disparador. Es lo que hace andar los sistemas de batalla de los
; personajes —Detect Aura prende el switch 134 y la página de la tropa que lo
; mira dice de qué color es el aura—. El código es el de los mapas y corre en
; el mismo intérprete, por el puente `ba_t_pagina`; lo de acá decide **cuándo**.
;
; La regla sale de easyrpg y no de memoria: `ScheduleNextPage` prueba las
; páginas en orden y arranca la primera que se cumpla y **no haya corrido en
; este turno**; cuando termina, prueba de nuevo, hasta que no quede ninguna. Lo
; de "este turno" lo borra `NextTurn`, que es cuando el grupo terminó de dar
; las órdenes. Y los momentos son tres: antes de pedir las órdenes, antes de
; cada acción y después de la última —ver los que llaman a `ba_pag_probar`—.

; Las páginas de la tropa de esta pelea, desde `BA_TROPA_K`. Una tropa que el
; cartucho no lleva no tiene ninguna.
.proc ba_pag_armar
.a8
.i16
    stz BA_PAG_N
    rep #$20
.a16
    stz BA_PAG_ESPERA
    stz BA_TURNO                ; el `turns` de `Game_Party`, que la pelea
                                ; pone en cero al empezar
    sep #$20
.a8
    lda BA_TROPA_K
    cmp #$FF
    beq listo
    jsr ba_ax
    lda f:tropa_pag_n, x
    sta BA_PAG_N
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:tropa_pag_ini, x
    sta BA_PAG_INI
    sep #$20
.a8
    jsr ba_pag_turno
listo:
    rts
.endproc

; `ResetPagesExecuted`: ninguna corrió todavía en este turno.
.proc ba_pag_turno
.a8
.i16
    ldx #0
otra:
    stz BA_PAG_HECHA, x
    inx
    cpx #TROPA_PAG_MAX
    bne otra
    rts
.endproc

; Si hay una página para correr, la deja lista —su código, el cursor en cero,
; anotada como corrida— con la pelea en `BA_M_PAGINA`, y vuelve con A8 en 1.
; Si no, en 0. **La Z vale lo mismo que A**: sale de un `lda` explícito.
;
; Primero `CheckBattleEndConditions`: con un lado entero caído la pelea se
; termina y no corre ninguna. Se lleva `BA_S0`, `BA_T*`, A, X e Y.
.proc ba_pag_probar
.a8
.i16
    lda BA_PAG_N
    beq no
    jsr ba_enemigo_vivo
    cmp #$FF
    beq no
    lda #0
    sta BA_PAG_I
alguien:
    lda BA_PAG_I
    cmp BA_NACT
    bcs no                      ; nadie del grupo en pie
    jsr ba_vivo
    bne hay_grupo
    inc BA_PAG_I
    bra alguien
hay_grupo:
    lda #0
    sta BA_PAG_I
otra:
    lda BA_PAG_I
    cmp BA_PAG_N
    bcs no
    jsr ba_ax
    lda BA_PAG_HECHA, x
    bne siguiente
    jsr ba_pag_cumple
    bne esta
siguiente:
    inc BA_PAG_I
    bra otra
esta:
    lda BA_PAG_I
    jsr ba_ax
    lda #1
    sta BA_PAG_HECHA, x
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_cod, x
    sta BA_PAG_COD
    stz BA_PAG_CUR
    lda #$FFFF
    sta BA_PAG_MSG
    sep #$20
.a8
    lda #1
    sta BA_PAG_ACT
    lda #BA_M_PAGINA
    sta BA_MODO
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si la página `BA_PAG_I` de la tropa se cumple: `AreConditionsMet`, con los
; seis disparadores que la ROM sabe mirar —los de RM2k; los tres de 2003 no
; existen en este juego—. Deja en `BA_PAG_G` su lugar en las tablas `tpag_*`
; y vuelve con Z=0 si se cumple. Se lleva `BA_T*`, `temp`, A, X e Y.
.proc ba_pag_cumple
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_I
    and #$00FF
    clc
    adc BA_PAG_INI
    sta BA_PAG_G
    tax
    sep #$20
.a8
    lda f:tpag_flags, x
    sta BA_PAG_FL               ; los disparadores, que sobreviven a los `jsr`
    and #TPAG_SWITCH_A
    beq sin_a
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_a, x
    jsr ba_pag_switch
.a8
    bne sin_a
    jmp no
sin_a:
    lda BA_PAG_FL
    and #TPAG_SWITCH_B
    beq sin_b
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_b, x
    jsr ba_pag_switch
.a8
    bne sin_b
    jmp no
sin_b:
    lda BA_PAG_FL
    and #TPAG_VARIABLE
    beq sin_var
    ; La variable, `>=` con signo: `Get(variable_id) >= variable_value`.
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_valor, x
    sta BA_T0
    lda f:tpag_var, x
    asl a
    tax
    lda FAR_VARIABLES, x
    sec
    sbc BA_T0
    bvc sin_desborde
    eor #$8000                  ; con desborde, el signo es el contrario
sin_desborde:
    sep #$20                    ; `sep` no toca N
.a8
    bpl sin_var
    jmp no
sin_var:
    lda BA_PAG_FL
    and #TPAG_CON_CABECERA
    bne con_cabecera
    jmp si
con_cabecera:
    jsr ba_pag_cabecera
    lda BA_PAG_FL
    and #TPAG_TURNO
    beq sin_turno
    ; El turno: `Game_Battle::CheckTurns(turno, turn_b, turn_a)`, con la base
    ; y el múltiplo **en ese orden**, que es el contrario del que sugieren los
    ; nombres de liblcf. Sin múltiplo, justo en la base; con él, en la base y
    ; cada tantos. El conversor los deja en la cabecera ya en su lugar.
    rep #$20
.a16
    lda BA_TURNO
    sec
    sbc BA_COND + BA_COND_BASE
    bcc no_turno                ; todavía no llegó a la base
    sta temp
    lda BA_COND + BA_COND_MULT
    bne con_multiplo
    lda temp
    bne no_turno
    bra turno_si
con_multiplo:
    sta temp + 2
    jsr ba_div                  ; el resto, en `comp_and`
    lda comp_and
    bne no_turno
turno_si:
    sep #$20
.a8
    bra sin_turno
no_turno:
    jmp no
sin_turno:
    lda BA_PAG_FL
    and #TPAG_ENEMIGO
    beq sin_enemigo
    ; Los HP de un enemigo, por su lugar en la tropa. `GetEnemy` no mira si
    ; está oculto ni si murió: sólo si el lugar existe.
    lda BA_COND + BA_COND_EMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_EMAX
    sta BA_PCT_MAX
    lda BA_COND + BA_COND_ENE
    cmp BA_NENE
    bcs no
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    jsr ba_pag_hp
    beq no
sin_enemigo:
    lda BA_PAG_FL
    and #TPAG_ACTOR
    beq si
    ; Los HP de un actor, por su número del LDB. **Sólo si está en el
    ; grupo**: `Game_Actors::GetActor` contesta por cualquiera, pero los HP de
    ; uno que no pelea viven en `FAR_HP` sin su máximo a mano, y las dos
    ; páginas del juego que miran esto son de Talan en la pelea de los Lazer
    ; Teeth, donde está. Ver `batalla.PaginaDeTropa`, que hace lo mismo.
    lda BA_COND + BA_COND_AMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_AMAX
    sta BA_PCT_MAX
    lda #0
    sta BA_T0 + 1               ; la ranura del grupo que se mira
busca_actor:
    lda BA_T0 + 1
    cmp BA_NACT
    bcs no
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq otro_actor
    lda BA_UNO + BA_NUMERO, x
    cmp BA_COND + BA_COND_ACT
    beq actor_hallado
otro_actor:
    inc BA_T0 + 1
    bra busca_actor
actor_hallado:
    jsr ba_pag_hp
    beq no
si:
    lda #1
    rts
no:
.a8
    sep #$20
    lda #0
    rts
.endproc

; La cabecera de la página `BA_PAG_G` —los números del turno y de los HP, que
; el conversor pone delante de su código, `TPAG_CABECERA` bytes antes de donde
; apunta `tpag_cod`— a `BA_COND`. Se lee con el banco de datos en el de
; `tropa_codigo`, que entra entero en un banco, y se escribe con `f:`. Se
; lleva A, X e Y. Ver `eventos.cabecera_de_tropa`.
.proc ba_pag_cabecera
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_cod, x
    sec
    sbc #TPAG_CABECERA
    tay
    sep #$20
.a8
    phb
    lda #^tropa_codigo
    pha
    plb
    ldx #0
otro:
    lda a:$0000, y
    sta f:BAT_LARGO + BA_COND, x
    iny
    inx
    cpx #TPAG_CABECERA
    bne otro
    plb
    rts
.endproc

; Si los HP del combatiente de desplazamiento X —el de `ba_x`— están entre
; `BA_PCT_MIN` y `BA_PCT_MAX` por ciento, contados como los cuenta
; `AreConditionsMet`: `100 * hp / hp_max`, entero. Sin dividir: que el
; cociente sea al menos `min` es `min * hp_max <= 100 * hp`, y que no pase de
; `max` es `100 * hp < (max + 1) * hp_max`. Los productos pasan de dieciséis
; bits —cien veces los HP de un jefe— y por eso van en veinticuatro. Vuelve
; con A8 y Z=0 si está. Se lleva `BA_T1`, `BA_T2` y `temp`.
.proc ba_pag_hp
.a8
.i16
    stx BA_T1
    lda #100
    sta BA_T2
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    jsr ba_mul24
    lda BA_P24
    sta BA_P_HP
    lda BA_P24 + 1
    sta BA_P_HP + 1
    sep #$20
.a8
    lda BA_PCT_MIN
    sta BA_T2
    rep #$20
.a16
    ldx BA_T1
    lda BA_UNO + BA_HPMAX, x
    jsr ba_mul24
    lda BA_P_HP
    sec
    sbc BA_P24
    sep #$20                    ; `sep` no toca C
.a8
    lda BA_P_HP + 2
    sbc BA_P24 + 2
    bcc no                      ; 100 hp < min * hp_max
    lda BA_PCT_MAX
    inc a
    sta BA_T2
    rep #$20
.a16
    ldx BA_T1
    lda BA_UNO + BA_HPMAX, x
    jsr ba_mul24
    lda BA_P_HP
    sec
    sbc BA_P24
    sep #$20
.a8
    lda BA_P_HP + 2
    sbc BA_P24 + 2
    bcs no                      ; 100 hp >= (max + 1) * hp_max
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 por el byte de `BA_T2`, en veinticuatro bits, en `BA_P24`: `ba_mul`
; sin perder lo que pasa de dieciséis. Se lleva `temp`.
.proc ba_mul24
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB                ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta BA_P24
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB
    stz BA_P24 + 2              ; mientras tanto
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL                ; el byte alto por el multiplicador, que pesa
    clc                         ; 256: se suma corrido un byte
    adc BA_P24 + 1
    sta BA_P24 + 1
    rts
.endproc

; `ShowHiddenMonster`: el enemigo del lugar A8 de la tropa deja de estar
; oculto y pasa a contar para todo —blanco, victoria, acciones—, que es lo
; que hace `SetHidden(false)`. Uno que no estaba oculto no cambia: el comando
; no revive a nadie. Lo dibuja `escena_tick`, que pone en la escena a todo el
; que está vivo y no se ve. Lo llama `op_show_enemy` desde el intérprete, con
; el banco de datos en 0: acá se pone el de la pelea.
.proc ba_mostrar_oculto
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp BA_NENE
    bcs listo
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    bit #BAF_OCULTO
    beq listo
    and #<~BAF_OCULTO
    ora #BAF_HAY
    sta BA_UNO + BA_FLAGS, x
listo:
    plb
    rtl
.endproc

; A16 el número de switch; vuelve con A8 y Z=0 si está prendido. Es el mismo
; bitmap que mira el mapa, `switches`, en la RAM baja, que con el banco de
; datos en $7E está en su lugar de siempre. Se lleva X e Y.
.proc ba_pag_switch
.a16
.i16
    pha
    lsr a
    lsr a
    lsr a
    tay                         ; qué byte
    pla
    and #$0007
    tax                         ; y qué bit
    sep #$20
.a8
    lda f:mascara, x
    and switches, y
    rts
.endproc

; Un tramo de la página que está corriendo, y lo que sigue: si pidió un
; mensaje, a la pantalla; si terminó, la que siga; y si no queda ninguna, la
; pelea sigue por donde estaba —`BA_PAG_VUELTA`—.
.proc ba_pag_paso
.a8
.i16
    ; Una espera de la página —la de un `ShakeScreen` que espera, que el
    ; conversor emite como OP_DELAY— se cuenta acá, un cuadro por vuelta, que
    ; es lo que `eventos_tick` hace con la del mapa.
    rep #$20
.a16
    lda BA_PAG_ESPERA
    beq sin_espera
    dec a
    sta BA_PAG_ESPERA
    sep #$20
.a8
    rts
sin_espera:
    sep #$20
otro_tramo:
.a8
    rep #$20
.a16
    ; `ev_esperando` es del intérprete del mapa, que quedó a medio correr
    ; adentro de `op_battle`: el de la página se guarda aparte.
    lda ev_esperando
    pha
    stz ev_esperando
    sep #$20
.a8
    jsl f:ba_t_pagina
    rep #$20
.a16
    lda ev_esperando
    sta BA_PAG_ESPERA
    pla
    sta ev_esperando
    lda BA_PAG_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne a_la_pantalla
    lda BA_PAG_ACT
    bne a_la_pantalla           ; no terminó y no pidió nada: no pasa con los
                                ; comandos de `TROPA_COMANDOS`, pero si pasara
                                ; sigue el cuadro que viene
    jsr ba_pag_probar
    bne otro_tramo              ; la que sigue, en este mismo cuadro
    lda BA_PAG_VUELTA
    bne a_las_ordenes
    jmp ba_ejecutar
a_las_ordenes:
    lda #BA_M_ORDEN
    sta BA_MODO
a_la_pantalla:
    jmp ba_componer
.endproc

; El mensaje de la página, en los renglones del grupo: ver `BA_PAG_MSG_FILA0`
; en pantallas.py. Lo lee de `mensajes_tropa` con el formato de siempre —la
; cabecera con los renglones y cada renglón con su largo, un byte por letra con
; el ASCII menos 32— y lo escribe con los glifos de la pantalla, cortado a
; `BA_PAG_MSG_ANCHO`. El bloque entra en un banco —lo garantiza el
; conversor—, así que el puntero se avanza con Y y el banco queda fijo.
.proc ba_pag_mensaje
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_MSG
    clc
    adc #.loword(mensajes_tropa)
    sta msg_ptr
    lda #BA_PAG_MSG_POS0
    sta BA_T1
    sep #$20
.a8
    lda #^mensajes_tropa
    sta msg_ptr + 2
    stz temp + 1                ; en blanco
    lda [msg_ptr]
    and #CABECERA_LINEAS
    sta BA_PAG_I                ; los renglones que quedan
    ldy #1
renglon:
    lda BA_PAG_I
    beq listo
    rep #$20
.a16
    lda #BA_PAG_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda [msg_ptr], y            ; el largo
    iny
    sta BA_T0                   ; las letras que le quedan
    stz BA_T2                   ; y las que ya se escribieron
letra:
    lda BA_T0
    beq fin_renglon
    dec BA_T0
    lda BA_T2
    cmp #BA_PAG_MSG_ANCHO
    bcs no_entra                ; se consume y no se dibuja
    inc BA_T2
    lda [msg_ptr], y
    clc
    adc #ITEM_PRIMER_CARACTER
    phy
    jsl f:ba_t_glifo
    ply
no_entra:
    iny
    bra letra
fin_renglon:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_FILA_BYTES
    sta BA_T1
    sep #$20
.a8
    dec BA_PAG_I
    bra renglon
listo:
    rts
.endproc

