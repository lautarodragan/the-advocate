.segment "FAR"

; La pelea entera. Se entra con `jsl` desde `op_battle`, con el banco de datos
; ya en $7E, y se vuelve con el resultado en `BA_RESULT`.
;
; Corre **su propio lazo de cuadros**, como `ranuras_pantalla` y como la
; tienda: `vueltas` no avanza mientras se ve, así que la pelea no cuesta
; ningún tick, tarde lo que tarde el jugador. Ver `OP_BATTLE`
; en tools/port/eventos.py.
.proc batalla_correr
.a8
.i16
    rep #$20
.a16
    lda #BATALLA_SEMILLA
    sta BA_SEM                  ; el azar arranca igual en toda pelea
    lda #$FFFF
    sta BA_SE2                  ; sin efecto pendiente
    sep #$20
.a8
    lda #BA_VICTORIA
    sta BA_RESULT
    lda #0
    sta BA_NACC
    sta BA_ORDEN
    sta BA_ACTOR
    sta BA_I
    jsr ba_armar
    lda BA_NENE
    bne hay_tropa
    rtl                         ; una tropa que este cartucho no lleva
hay_tropa:
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    bne hay_grupo
    lda #BA_DERROTA             ; nadie en pie: se pierde sin pelear
    sta BA_RESULT
    rtl
hay_grupo:
    jsr ba_chance_huir
    jsr ba_pag_armar
    ; Apagar la pantalla, desde acá: los tres registros van con `f:` porque el
    ; banco de datos es $7E y absolutos caerían en la RAM.
    lda #$80
    sta f:INIDISP
    lda #0
    sta f:HDMAEN
    sta f:TM
    jsl f:ba_t_banco
    ; Y la escena: el fondo con los monstruos, compuesta acá y subida a BG1.
    ; Va con la pantalla apagada porque son 32 KB de VRAM más el tilemap y
    ; las paletas.
    jsr escena_subir
    lda #BA_M_ORDEN
    sta BA_MODO
    ; Antes de la primera orden, las páginas que ya se cumplen: es el
    ; `eCheckEvents` de `ProcessSceneActionFightAutoEscape`. Corren desde el
    ; cuadro que viene, con la pantalla ya prendida.
    jsr ba_pag_probar
    beq sin_pagina_al_empezar
    lda #1
    sta BA_PAG_VUELTA
sin_pagina_al_empezar:
    jsr ba_componer
    jsl f:ba_t_subir
    ; Prender la pantalla **en negro**, que la muestra la transición de
    ; entrada: `ranura_ppu_prender` escribe el brillo lleno, así que se la
    ; llama adentro de un vblank y en el mismo vblank se baja a cero —no llega
    ; a dibujarse ninguna línea—. Ver `fundido_de_pelea.s`.
    jsl f:ba_t_vblank
    jsl f:ba_t_ppu
    lda #0
    sta f:INIDISP
    jsr escena_prender
    jsr pelea_fundir_mostrando
    lda #1
    sta menu_abierto

espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; el control antes del DMA, como en la tienda
    jsl f:ba_t_subir
    jsr escena_tick             ; todavía en el vblank: un enemigo que murió
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne :+
    jmp modo_orden
:   cmp #BA_M_BLANCO
    bne :+
    jmp modo_blanco
:   cmp #BA_M_ITEM
    bne :+
    jmp modo_item
:   cmp #BA_M_ACTOR
    bne :+
    jmp modo_actor
:   cmp #BA_M_HAB
    bne :+
    jmp modo_hab
:   cmp #BA_M_MENSAJE
    bne :+
    jmp modo_mensaje
:   cmp #BA_M_PAGINA
    bne :+
    jmp modo_pagina
:   jmp modo_fin

    ; --- eligiendo la orden ---
espera5:
    jmp espera
modo_orden:
    lda titulo_flancos
    and #PAD_LEFT
    beq o_no_izq
    lda BA_ORDEN
    beq espera5
    dec BA_ORDEN
    jmp recomponer
o_no_izq:
    lda titulo_flancos
    and #PAD_RIGHT
    beq o_no_der
    lda BA_ORDEN
    cmp #(BA_ORDENES_N - 1)
    bcs espera5
    inc BA_ORDEN
    jmp recomponer
o_no_der:
    jsr ba_flanco_a
    beq espera5
    lda BA_ORDEN
    cmp #BA_ORDEN_ATACAR
    bne o_no_ataca
    jsr ba_enemigo_vivo
    cmp #$FF
    beq espera5
    sta BA_BLANCO
    lda #BA_M_BLANCO
    sta BA_MODO
    jmp recomponer
o_no_ataca:
    cmp #BA_ORDEN_DEFENDER
    bne o_no_defiende
    lda #0
    sta BA_T0
    lda #BA_DEFENDER
    jsr ba_anotar
    jmp siguiente_actor
o_no_defiende:
    cmp #BA_ORDEN_USAR
    bne o_no_usa
    ; `Use Item`: la lista de lo que se puede usar. Vacía, no pasa nada, que
    ; es lo que hace el menú de pausa con una orden que no lleva a ningún
    ; lado.
    jsr ba_items_lista
    lda BA_ITEM_N
    beq espera5
    lda #0
    sta BA_ITEM_SEL
    sta BA_ITEM_ARR
    lda #BA_M_ITEM
    sta BA_MODO
    jmp recomponer
o_no_usa:
    cmp #BA_ORDEN_HABILIDAD
    bne o_no_habilidad
    ; La lista de habilidades del que ordena. Vacía —Talan, que es de nivel
    ; 1— no pasa nada, que es lo que el menú hace con una orden que no lleva a
    ; ningún lado.
    jsr ba_hab_lista
    lda BA_HAB_N
    beq espera5
    lda #0
    sta BA_HAB_SEL
    lda #BA_M_HAB
    sta BA_MODO
    jmp recomponer
o_no_habilidad:
    cmp #BA_ORDEN_HUIR
    beq o_huye
    jmp espera
o_huye:
    jsr ba_huir
    beq o_no_huyo
    lda #BA_HUIDA_R
    sta BA_RESULT
    lda #BA_MSG_HUYO
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_HUIR             ; el escape_se de `Scene_Battle_Rpg2k`
    jsl f:ba_t_sonido
.a8
    lda #BA_M_FIN
    sta BA_MODO
    jmp espera
o_no_huyo:
    lda #0
    sta BA_T0
    lda #BA_HUIR
    jsr ba_anotar
    jmp siguiente_actor
espera2:
    jmp espera

    ; --- eligiendo el blanco ---
modo_blanco:
    lda titulo_flancos
    and #PAD_UP
    beq b_no_arriba
    jsr ba_blanco_arriba
    jmp recomponer
b_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq b_no_abajo
    jsr ba_blanco_abajo
    jmp recomponer
b_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq b_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
b_mira_a:
    jsr ba_flanco_a
    beq espera2
    lda BA_BLANCO
    clc
    adc #BA_GRUPO_MAX
    sta BA_T0
    ; El modo del blanco lo comparten atacar y una habilidad que apunta a los
    ; enemigos; cuál de las dos es lo dice `BA_ORDEN`, que sigue puesto.
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne b_ataca
    lda #BA_HABILIDAD
    bra b_anota
b_ataca:
    lda #BA_ATACAR
b_anota:
    jsr ba_anotar
    jmp siguiente_actor         ; los dos modos de abajo quedaron en el medio

    ; --- eligiendo qué ítem ---
modo_item:
    lda titulo_flancos
    and #PAD_UP
    beq i_no_arriba
    lda BA_ITEM_SEL
    beq espera4
    dec BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq i_no_abajo
    lda BA_ITEM_SEL
    inc a
    cmp BA_ITEM_N
    bcs espera4
    sta BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq i_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
i_mira_a:
    jsr ba_flanco_a
    beq espera4
    ; A quién dárselo: al primero del grupo al que le sirve —en pie para una
    ; poción, caído para un elixir—. Si no le sirve a nadie, A no pasa de la
    ; lista: ver `ba_item_sirve_sobre`.
    lda #0
    sta BA_ACTOR2
busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera4
    jsr ba_item_sirve_sobre
    bne hay_blanco_act
    inc BA_ACTOR2
    bra busca_vivo
hay_blanco_act:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODO
    jmp recomponer
espera4:
    jmp espera

    ; --- eligiendo a quién se le da ---
modo_actor:
    lda titulo_flancos
    and #PAD_UP
    beq a_no_arriba
    jsr ba_blanco_act_arriba
    jmp recomponer
a_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq a_no_abajo
    jsr ba_blanco_act_abajo
    jmp recomponer
a_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq a_mira_a
    ; B vuelve a la lista de la que se vino: la de ítems o la de habilidades.
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne a_vuelve_a_items
    lda #BA_M_HAB
    sta BA_MODO
    jmp recomponer
a_vuelve_a_items:
    lda #BA_M_ITEM
    sta BA_MODO
    jmp recomponer
a_mira_a:
    jsr ba_flanco_a
    beq espera4
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne a_es_item
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_HABILIDAD
    jsr ba_anotar
    jmp siguiente_actor
a_es_item:
    ; Se anota la orden y **se gasta el ítem ya**, que es lo que hace RM2k al
    ; elegirlo: si no, el último de un ítem se podría repartir entre dos
    ; actores en el mismo turno.
    lda BA_ITEM_SEL
    jsr ba_item_de_lista
    pha
    lda BA_ACTOR
    jsr ba_ax
    pla
    sta BA_ACC_ITEM, x
    jsr ba_item_gastar
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_ITEM
    jsr ba_anotar
    jmp siguiente_actor

    ; --- eligiendo qué habilidad ---
    ;
    ; La lista es de dos columnas y se lee por filas, así que izquierda y
    ; derecha se mueven de a uno y arriba y abajo de a dos.
modo_hab:
    lda titulo_flancos
    and #PAD_LEFT
    bne h_izq
    jmp h_no_izq
h_izq:
    lda BA_HAB_SEL
    beq espera6
    dec BA_HAB_SEL
    jmp recomponer
h_no_izq:
    lda titulo_flancos
    and #PAD_RIGHT
    beq h_no_der
    lda BA_HAB_SEL
    inc a
    cmp BA_HAB_N
    bcs espera6
    sta BA_HAB_SEL
    jmp recomponer
h_no_der:
    lda titulo_flancos
    and #PAD_UP
    beq h_no_arriba
    lda BA_HAB_SEL
    cmp #BA_HAB_COLUMNAS
    bcc espera6
    sec
    sbc #BA_HAB_COLUMNAS
    sta BA_HAB_SEL
    jmp recomponer
h_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq h_no_abajo
    lda BA_HAB_SEL
    clc
    adc #BA_HAB_COLUMNAS
    cmp BA_HAB_N
    bcs espera6
    sta BA_HAB_SEL
    jmp recomponer
espera6:
    jmp espera
h_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq h_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
h_mira_a:
    jsr ba_flanco_a
    beq espera7
    ; La que no se puede pagar no se elige, que es lo que RM2k hace con una
    ; habilidad en gris. El costo se descuenta **al ejecutarla** y no acá:
    ; `Skill::vStart` corre cuando le toca el turno.
    lda BA_HAB_SEL
    jsr ba_hab_de_lista
    sta BA_S0
    jsr ba_hab_alcanza
    beq espera6
    lda BA_ACTOR
    jsr ba_ax
    lda BA_S0
    sta BA_ACC_HAB, x
    ; Una de switch **no pide blanco**, apunte a donde apunte su `scope`:
    ; `Scene_Battle::AssignSkill` la anota sobre el que la usa y sigue. Sin
    ; esto, Detect Aura —`scope` 0, un enemigo— pedía elegir uno, y si ése se
    ; moría antes del turno la habilidad se perdía, que en RM2k no pasa.
    ;
    ; Tampoco las de a muchos ni las de uno mismo, cuyo blanco lo decide el
    ; alcance: sólo `enemy` y `ally` lo piden —`batalla.pide_blanco`—.
    lda BA_S0
    jsr ba_ax
    lda f:hab_tipo, x
    cmp #BA_HAB_TIPO_SWITCH
    beq h_sin_blanco
    lda f:hab_alcance, x
    cmp #BA_ALCANCE_ENEMIGO
    beq h_con_blanco
    cmp #BA_ALCANCE_ALIADO
    beq h_con_blanco
h_sin_blanco:
    lda BA_ACTOR
    sta BA_T0
    lda #BA_HABILIDAD
    jsr ba_anotar
    jmp siguiente_actor
h_con_blanco:
    ; A quién apunta: el bit 6 de `hab_afecta` es `SkillTargetsEnemies`.
    lda BA_S0
    jsr ba_ax
    lda f:hab_afecta, x
    and #$40
    beq h_a_un_aliado
    jsr ba_enemigo_vivo
    cmp #$FF
    beq espera7
    sta BA_BLANCO
    lda #BA_M_BLANCO
    sta BA_MODO
    jmp recomponer
h_a_un_aliado:
    ; Al primero vivo del grupo, como con un ítem.
    lda #0
    sta BA_ACTOR2
h_busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera7                 ; no puede pasar: el que ordena está vivo
    lda BA_ACTOR2
    jsr ba_vivo
    bne h_hay_blanco
    inc BA_ACTOR2
    bra h_busca_vivo
espera7:
    jmp espera
h_hay_blanco:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODO
    jmp recomponer

siguiente_actor:
    ; Al que sigue; si no queda ninguno, empieza el turno.
    jsr ba_actor_siguiente
    cmp #$FF
    beq arranca_turno
    lda #0
    sta BA_ORDEN
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
arranca_turno:
    jsr ba_empezar_turno
    jmp espera

    ; --- un mensaje en pantalla ---
modo_mensaje:
    jsr ba_flanco_a
    bne pasa
    dec BA_ESPERA
    lda BA_ESPERA
    cmp #BA_SE2_CUADROS
    bne sin_segundo
    ; El segundo efecto del golpe, el que RM2k toca en el sub-estado del
    ; mensaje. Se saca de `BA_SE2` al dispararlo para que no vuelva a salir si
    ; el mensaje se alarga.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sonido
.a8
sin_segundo:
    lda BA_ESPERA
    bne espera3
pasa:
    jsr ba_ejecutar
espera3:
    jmp espera

    ; --- una página de tropa ---
    ;
    ; Con un mensaje suyo en pantalla, se espera la A **sin tope de tiempo**:
    ; es un `ShowMessage`, que en RM2k no se cierra solo, y no uno de los de la
    ; pelea, que sí. Sin mensaje, la página sigue.
modo_pagina:
    rep #$20
.a16
    lda BA_PAG_MSG
    cmp #$FFFF
    sep #$20
.a8
    beq p_sigue
    jsr ba_flanco_a
    beq espera3
    rep #$20
.a16
    lda #$FFFF
    sta BA_PAG_MSG
    sep #$20
.a8
p_sigue:
    jsr ba_pag_paso
    jmp espera

    ; --- la pelea terminó ---
modo_fin:
    jsr ba_flanco_a
    beq espera3
    ; La victoria tiene más de una página: "N EXP", y una por cada actor que
    ; subió de nivel.
    jsr ba_vic_siguiente
    beq cerrar
    jmp recomponer
cerrar:
    ; Los HP y los SP del grupo vuelven a la partida: desde que hay batallas
    ; son estado de verdad y viajan en la ranura de SRAM.
    lda #0
    sta BA_S0
guarda:
    lda BA_S0
    cmp BA_NACT
    bcs guardados
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sta BA_T0
    lda BA_UNO + BA_SP, x
    sta BA_T1
    sep #$20
.a8
    lda BA_UNO + BA_NUMERO, x
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda BA_T0
    sta FAR_HP, x
    lda BA_T1
    sta FAR_SP, x
    sep #$20
.a8
    inc BA_S0
    bra guarda
guardados:
    rtl

recomponer:
    jsr ba_componer
    jmp espera

; Z=0 si A se acaba de apretar. Es el mismo de la tienda: `pad_a` y su anterior
; los pone `read_pad`.
ba_flanco_a:
    lda pad_a
    beq no_a
    lda pad_a_ant
    beq si_a
no_a:
    lda #0
    rts
si_a:
    lda #1
    rts

; Que el ítem marcado se vea: corre la ventana de ocho renglones lo justo.
ba_item_ver:
    lda BA_ITEM_SEL
    cmp BA_ITEM_ARR
    bcs ver_abajo
    sta BA_ITEM_ARR             ; se fue por arriba: la ventana lo sigue
    rts
ver_abajo:
    sec
    sbc #BA_ENEMIGOS_MAX
    bcc listo_ver               ; entra sin mover nada
    inc a                       ; el primero que tendría que verse
    cmp BA_ITEM_ARR
    bcc listo_ver
    sta BA_ITEM_ARR
listo_ver:
    rts

; El cursor de a quién se le da el ítem, al actor de arriba o de abajo en el
; que puede pararse —ver `ba_blanco_act_sirve`—. Si para ese lado no queda
; ninguno, se queda donde está. Es el hermano de `ba_blanco_arriba`, sobre el
; grupo en vez de sobre la tropa.
ba_blanco_act_arriba:
    lda BA_ITEM_BLA
mira_arriba_act:
    beq nada_act
    dec a
    sta BA_ACTOR2               ; `ba_item_sirve_sobre` se lleva `BA_S0`
    jsr ba_blanco_act_sirve
    bne pone_act
    lda BA_ACTOR2
    bra mira_arriba_act
ba_blanco_act_abajo:
    lda BA_ITEM_BLA
mira_abajo_act:
    inc a
    cmp BA_NACT
    bcs nada_act
    sta BA_ACTOR2
    jsr ba_blanco_act_sirve
    bne pone_act
    lda BA_ACTOR2
    bra mira_abajo_act
pone_act:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
nada_act:
    rts

; Si el cursor de a quién puede pararse en el actor A8: Z=0 si sí. Lo
; comparten un ítem y una habilidad que apunta al grupo, y cuál de los dos es
; lo dice `BA_ORDEN`. Una habilidad sólo sobre los que están en pie, que es lo
; que `Skill::IsTargetValid` deja con las de este port —ninguna saca la
; muerte—; un ítem, sobre el que le sirva, que puede ser un caído.
ba_blanco_act_sirve:
    pha
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    beq sirve_hab
    pla
    jmp ba_item_sirve_sobre
sirve_hab:
    pla
    jmp ba_vivo

; El cursor del blanco, al enemigo vivo de arriba o de abajo. Si para ese lado
; no queda ninguno vivo, se queda donde está.
ba_blanco_arriba:
    lda BA_BLANCO
mira_arriba:
    beq nada
    dec a
    sta BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne pone
    lda BA_S0
    bra mira_arriba
ba_blanco_abajo:
    lda BA_BLANCO
mira_abajo:
    inc a
    cmp BA_NENE
    bcs nada
    sta BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne pone
    lda BA_S0
    bra mira_abajo
pone:
    lda BA_S0
    sta BA_BLANCO
nada:
    rts
.endproc

