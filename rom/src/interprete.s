; El bucle del intérprete: un opcode por vuelta hasta el FIN.
;
; Y es el cursor del bytecode y tiene que sobrevivir a todo el bucle, así que
; cada `jsr` que sale de acá lo guarda antes de irse. Las rutinas que se llaman
; usan X e Y para lo suyo —poner_switch indexa el bitmap de switches,
; aplicar_tinte recorre tres paletas— y ninguna tiene por qué saber que acá
; significan otra cosa. Sin esto, el primer OP_SWITCH dejaba a Y valiendo el
; número del switch dividido ocho, y lo que se leía como opcode siguiente era
; un byte cualquiera del medio de la página: el bucle cortaba ahí y el resto no
; corría.
.proc correr_codigo
.a8
.i16
    ldy ev_cur                  ; donde quedó el cuadro anterior
otro:
    lda [cod_ptr], y
    iny
    ; Cada opcode se despacha con `bne` al salteo y `jmp` al cuerpo, y no con un
    ; `beq` derecho al cuerpo, que es lo que había. La diferencia es el alcance:
    ; un `beq` llega a 127 bytes y el cuerpo del último opcode está detrás de
    ; todos los demás, así que el límite lo marca la suma de los otros seis.
    ;
    ; Eso ya cortó dos veces. La primera, al aparecer OP_MESSAGE, dejó a
    ; OP_TELEPORT a 140 bytes; se arregló ordenando las comparaciones como los
    ; cuerpos. La segunda fue darle su operando a OP_MESSAGE: 129 bytes, o sea
    ; que aquel arreglo duraba exactamente un opcode. Y faltan cuatro —MoveEvent
    ; sobre otro evento, FlashSprite, PlaySound y ControlVars, en ese orden y
    ; medidos con `just snes-destraba`—, así que el límite se saca del medio de
    ; una vez: un `jmp` llega a cualquier parte del banco.
    ;
    ; Sale tres bytes y cuatro ciclos por opcode que no matchea, en un despacho
    ; que corre unas pocas veces por cuadro. El orden ya no significa nada.
    cmp #OP_MESSAGE
    bne :+
    jmp op_message
:   cmp #OP_SWITCH
    bne :+
    jmp op_switch
:   cmp #OP_ROUTE
    bne :+
    jmp op_route
:   cmp #OP_PARTY
    bne :+
    jmp op_party
:   cmp #OP_DELAY
    bne :+
    jmp op_delay
:   cmp #OP_TINT
    bne :+
    jmp op_tint
:   cmp #OP_FLASH
    bne :+
    jmp op_flash
:   cmp #OP_WAIT_ROUTES
    bne :+
    jmp op_wait_routes
:   cmp #OP_BGM
    bne :+
    jmp op_bgm
:   cmp #OP_PLACE
    bne :+
    jmp op_place
:   cmp #OP_PLACE_VAR
    bne :+
    jmp op_place_var
:   cmp #OP_SWAP
    bne :+
    jmp op_swap
:   cmp #OP_SHAKE
    bne :+
    jmp op_shake
:   cmp #OP_FLASH_SCREEN
    bne :+
    jmp op_flash_screen
:   cmp #OP_FADE_BGM
    bne :+
    jmp op_fade_bgm
:   cmp #OP_PAN
    bne :+
    jmp op_pan
:   cmp #OP_TIMER
    bne :+
    jmp op_timer
:   cmp #OP_IF
    bne :+
    jmp op_if
:   cmp #OP_GOTO
    bne :+
    jmp op_goto
:   cmp #OP_CHOICE
    bne :+
    jmp op_choice
:   cmp #OP_GOLD
    bne :+
    jmp op_gold
:   cmp #OP_ITEM
    bne :+
    jmp op_item
:   cmp #OP_ACCESS
    bne :+
    jmp op_access
:   cmp #OP_ACTOR_SPRITE
    bne :+
    jmp op_actor_sprite
:   cmp #OP_KEY
    bne :+
    jmp op_key
:   cmp #OP_SHOP
    bne :+
    jmp op_shop
:   cmp #OP_BATTLE
    bne :+
    jmp op_battle
:   cmp #OP_WEATHER
    bne :+
    jmp op_weather
:   cmp #OP_ANIMATION
    bne :+
    jmp op_animation
:   cmp #OP_SOUND
    bne :+
    jmp op_sound
:   cmp #OP_PICTURE
    bne :+
    jmp op_picture
:   cmp #OP_PICTURE_MOVE
    bne :+
    jmp op_picture_move
:   cmp #OP_PICTURE_ERASE
    bne :+
    jmp op_picture_erase
:   cmp #OP_SAVE
    bne :+
    jmp op_save
:   cmp #OP_TELEPORT
    bne :+
    jmp op_teleport
:   cmp #OP_VAR
    bne :+
    jmp op_var
:   cmp #OP_IF_VAR
    bne :+
    jmp op_if_var
:   cmp #OP_IF_ACTOR
    bne :+
    jmp op_if_actor
:   cmp #OP_STOP_ROUTES
    bne :+
    jmp op_stop_routes
:   cmp #OP_HEAL
    bne :+
    jmp op_heal
:   cmp #OP_TILE_SUB
    bne :+
    jmp op_tile_sub
:   cmp #OP_TERRAIN
    bne :+
    jmp op_terrain
:   cmp #OP_EQUIPMENT
    bne :+
    jmp op_equipment
:   cmp #OP_SKILL
    bne :+
    jmp op_skill
:   cmp #OP_GAME_OVER
    bne :+
    jmp op_game_over
:   stz ev_activo              ; OP_DONE, o algo que no conocemos: se corta
    rts

; Abre la ventana de mensaje y corta el cuadro. El cursor ya quedó en el
; comando siguiente —el `iny` del lazo— pero `eventos_tick` no vuelve a llamar
; acá hasta que el jugador apriete A.
;
; El operando es el desplazamiento del cuadro de texto dentro del bloque
; `mensajes`, de 16 bits. No es el texto: emitir cada cuadro ya compuesto son
; 240 tiles de 4bpp, o sea 7,5 KB, y los 2895 del juego serían 21 MB. Lo que
; viaja en el cartucho es un byte por letra y lo compone el 65816, que es la
; salida de FF6.
op_message:
    ; Un paralelo no abre su mensaje encima del de otro: **espera**.
    ; `CommandShowMessage` arranca con `if (!CanShowMessage(main_flag)) return
    ; false;` y para un intérprete de fondo eso es `!is_active` (easyrpg
    ; `game_interpreter.cpp:928` y `window_message.h:216`); devolver false deja
    ; el cursor donde estaba, o sea que el opcode se reintenta el cuadro que
    ; viene. El primer plano no necesita el chequeo —con un mensaje abierto
    ; `eventos_tick` ni siquiera lo llama— y por eso el que decide es `par_ev`.
    lda par_ev
    cmp #$FF
    beq abrir                   ; primer plano
    cmp #PAR_PELEA
    beq en_la_pelea
    lda msg_abierto
    ora msg_estado
    ora eleg_activo
    beq abrir
    dey                         ; el cursor vuelve a este mismo opcode
    sty ev_cur
    rts
en_la_pelea:
    ; Una página de tropa: el mensaje no va a la ventana del mapa —la pantalla
    ; es la de la pelea, y `texto_buf` es suyo— sino que se le deja anotado a
    ; la pelea, que lo dibuja en sus renglones y espera la A. La página queda
    ; frenada detrás de él igual que en el mapa: `ev_activo` sigue en uno y el
    ; cursor, en el comando que viene. Ver `ba_pag_paso`.
    rep #$20
.a16
    lda [cod_ptr], y
    sta f:BAT_LARGO + BA_PAG_MSG
    iny
    iny
    sep #$20
.a8
    sty ev_cur
    rts
abrir:
    lda par_ev
    sta msg_duenio              ; $FF si lo abre el primer plano
    ; El mensaje no aparece en este cuadro: hay que componerle el texto, y eso
    ; lleva unos cuantos. La ventana se prende sola cuando el compositor
    ; termina; mientras tanto la página ya está bloqueada.
    stz msg_abierto
    stz eleg_activo
    rep #$20
.a16
    lda [cod_ptr], y            ; el desplazamiento, que va en A a msg_empezar
    iny
    iny
    phy
    jsr msg_empezar
    ply
    sep #$20
.a8
    sty ev_cur
    rts

; `ConditionalBranch` con condición de switch. Los operandos son el número (dos
; bytes), la polaridad —copiada tal cual de RM2k, donde 0 quiere decir "tiene
; que estar prendido"— y el destino: **el índice absoluto dentro de la página**
; al que va el cursor si la condición no se cumple, o sea el `else` o el `end`
; que le corresponde. Quién es ese destino lo resolvió el conversor, que es el
; único que ve la página entera; acá saltar es asignar Y.
op_if:
    ; El primer byte dice **qué se pregunta**, con el número de RM2k tal cual: 0
    ; un switch, 3 el oro, 5 si un actor está en el grupo. Ver `bytes_de_rama`.
    ;
    ; Cada rama deja en A si la condición se cumple —cero o distinto de cero— y
    ; a Y apuntando al byte de polaridad; de ahí en adelante el camino es uno
    ; solo. El switch es el único que usa la polaridad para decidir: en el oro
    ; ya está adentro de la comparación y el actor no la tiene.
    lda [cod_ptr], y
    iny                         ; Y -> el operando
    cmp #COND_ORO
    beq si_oro
    cmp #COND_ACTOR
    beq si_actor
    cmp #COND_ITEM
    bne :+
    jmp si_item                 ; el cuerpo está detrás del oro: `beq` no llega
:

    ; --- el switch ---
    rep #$20
.a16
    phy                         ; el cursor: `switch_encendido` se lleva X e Y
    lda [cod_ptr], y            ; el número, de 16 bits
    jsr switch_encendido        ; Z=1 apagado, Z=0 prendido
    beq si_apagado
    lda #$0001
    bra si_tengo
si_apagado:
    lda #$0000
si_tengo:
    ply                         ; el cursor de vuelta; `ply` no toca A
    sep #$20
.a8
    ; A vale 1 si el switch está prendido, y la polaridad 0 si tenía que
    ; estarlo: el `eor` da distinto de cero exactamente cuando se cumple, en
    ; los dos sentidos, y sin ninguna rama de más. Va por `temp` porque el
    ; ensamblador no tiene `eor [dp], y`. El objeto usa el mismo final, con la
    ; misma polaridad.
si_polaridad:
    iny
    iny                         ; Y -> la polaridad
    sta temp
    lda [cod_ptr], y
    eor temp
    bra si_decide

    ; --- el actor: `IsActorInParty` ---
    ; No lleva polaridad: la rama de abajo es el `else`, así que el conversor
    ; emite cero ahí y acá no se lo mira.
si_actor:
    lda [cod_ptr], y            ; el id, que entra en un byte
    phy
    jsr en_el_grupo             ; A=1 si está, A=0 si no
    ply
    iny
    iny                         ; Y -> la polaridad, que vale cero
    ; **La Z se arma acá, pegada al salto.** `si_decide` decide con un `beq`,
    ; y `ply` y los dos `iny` le dejaban la Z del cursor, que nunca es cero:
    ; "está en el grupo" daba que sí siempre, y en el techo del Warehouse
    ; aparecía Arden sin haberlo sumado. El 2026-09-12 el `cmp #0` iba
    ; después del `ply` y antes de los `iny`, que era arreglar la mitad: ver
    ; `test_rama_grupo`.
    cmp #0
    bra si_decide

    ; --- el oro ---
    ; `CommandConditionalBranch` caso 3: con la polaridad en cero es
    ; `oro >= operando` y con cualquier otra cosa `oro <= operando`. **No son
    ; una la negación de la otra**: en la igualdad se cumplen las dos, así que
    ; se calculan por separado en vez de dar vuelta un bit.
si_oro:
    rep #$20
.a16
    lda [cod_ptr], y            ; contra cuánto, de 16 bits
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> la polaridad
    lda oro + 2
    bne si_oro_grande           ; el oro pasa de 65535: mayor que cualquier
                                ; operando, que entra en una palabra
    rep #$20
.a16
    lda oro
    cmp temp + 2                ; C=1 si oro >= operando
    sep #$20
.a8
    lda #$01
    bcs si_oro_ge
    lda #$00
si_oro_ge:
    sta temp
    rep #$20
.a16
    lda temp + 2
    cmp oro                     ; C=1 si operando >= oro, o sea oro <= operando
    sep #$20
.a8
    lda #$01
    bcs si_oro_le
    lda #$00
si_oro_le:
    sta temp + 1
    bra si_oro_elige
si_oro_grande:
    lda #$01
    sta temp                    ; el >= se cumple
    stz temp + 1                ; y el <= no
si_oro_elige:
    lda [cod_ptr], y            ; la polaridad
    beq si_oro_usa_ge
    lda temp + 1
    bra si_decide
si_oro_usa_ge:
    lda temp
    bra si_decide

    ; --- el objeto: `CommandConditionalBranch` caso 4 ---
    ; `GetItemCount(id) > 0`, la misma pregunta que la condición de página por
    ; ítem y leída del mismo lugar: un byte de `FAR_ITEMS` indexado por el
    ; número de RM2k. `GetEquippedItemCount` no entra porque no hay equipo, que
    ; es lo que `condiciones_ok` ya da por sentado.
    ;
    ; La polaridad es la del switch —0 es "tiene que tenerlo"— así que decide
    ; con el mismo `eor` y sin una rama de más.
si_item:
    rep #$20
.a16
    lda [cod_ptr], y            ; el número de ítem, de 16 bits
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA                  ; cuántos hay en el inventario
    beq si_item_no
    lda #$01
    bra si_item_listo
si_item_no:
    lda #$00
si_item_listo:
    jmp si_polaridad

si_decide:
    beq si_no_cumple
    iny
    iny
    iny                         ; Y -> el opcode siguiente
    jmp otro
si_no_cumple:
    iny                         ; Y -> el destino
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp otro

; `ConditionalBranch` caso 5 con dos operandos: "sabe esta habilidad" —el
; sub 4— y "tiene puesto este objeto" —el 5—. Van en un opcode aparte y no en
; `OP_IF` porque llevan **dos** operandos, el actor y el ítem o la habilidad;
; ver OP_IF_ACTOR en eventos.py.
;
; Ninguna de las dos tiene polaridad: RM2k no se la da, igual que a "está en el
; grupo", así que la rama de abajo es el `else`.
;
; Al entrar, Y apunta al sub. Los dos caminos terminan en `sia_si` o en
; `sia_no` con Y ya apuntando al destino.
op_if_actor:
    lda [cod_ptr], y
    sta temp                    ; el sub
    iny
    lda [cod_ptr], y
    sta temp + 1                ; el actor, que entra en un byte
    iny
    rep #$20
.a16
    lda [cod_ptr], y
    sta temp + 2                ; el ítem o la habilidad, de 16 bits
    sep #$20
.a8
    iny
    iny                         ; Y -> el destino
    lda temp
    cmp #COND_ACTOR_HABILIDAD
    beq sia_habilidad

    ; --- el equipo puesto ---
    ; Los cinco `Get*Id()` de easyrpg comparados contra el ítem: alcanza con
    ; que esté en una ranura. Se leen del mismo lugar que los lee la pantalla
    ; de equipo —`FAR_EQUIPO` + actor * 10, ver `eq_apuntar`— por el puerto de
    ; la WRAM, que autoincrementa: una palabra por ranura, byte por byte,
    ; porque `WMDATA` es un puerto de ocho bits y leerlo de a dos leería el
    ; registro de al lado.
    rep #$20
.a16
    lda temp + 1
    and #$00FF                  ; el actor, sin el ítem que sigue
    asl a                       ; por dos
    sta temp                    ; el sub ya no hace falta
    asl a
    asl a                       ; por ocho
    clc
    adc temp                    ; por diez, que es lo que mide una fila
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #RANURAS_EQUIPO
sia_eq_otra:
    lda WMDATA
    sta temp                    ; el byte bajo del ítem de esta ranura
    lda WMDATA
    sta temp + 1
    rep #$20
.a16
    lda temp
    cmp temp + 2
    sep #$20
.a8
    beq sia_si                  ; `sep` no toca Z: la comparación sigue viva
    dex
    bne sia_eq_otra
    bra sia_no

    ; --- la habilidad ---
    ; `Game_Actor::IsSkillLearned`: el bit del par (actor, habilidad) en
    ; `FAR_HAB`. El conversor ya puso la ranura del par donde las otras
    ; preguntas llevan el ítem, así que `temp + 2` la trae y el actor no hace
    ; falta. Ver `HABILIDAD_RANURA` en eventos.py.
sia_habilidad:
    jsl f:hab_sabe
    bne sia_si
sia_no:
    rep #$20
.a16
    lda [cod_ptr], y            ; el destino, absoluto adentro de la página
    tay
    sep #$20
.a8
    jmp otro
sia_si:
    iny
    iny                         ; Y -> el opcode siguiente
    jmp otro

; `ChangeGold`: suma o resta y recorta a [0, ORO_MAX], que es lo que hace
; `Game_Party::GainGold`. El monto va en tres bytes porque el tope de RM2k son
; 999999 y este juego usa el valor entero.
;
; No hay dónde mostrarlo —el menú no existe— pero sí quién lo pregunta: la rama
; de oro de `ConditionalBranch`.
op_gold:
    lda [cod_ptr], y            ; el signo: 0 suma, 1 resta
    sta temp
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; los 16 bits bajos del monto
    sta temp + 2
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y el byte alto
    sta temp + 1                ; el byte alto del monto
    iny
    phy

    lda temp
    bne oro_resta
    ; Sumar: 24 bits, y si se pasa de ORO_MAX queda en ORO_MAX.
    rep #$20
.a16
    lda oro
    clc
    adc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    adc temp + 1
    sta oro + 2
    bra oro_recorta
oro_resta:
    rep #$20
.a16
    lda oro
    sec
    sbc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    sbc temp + 1
    sta oro + 2
    bcs oro_recorta
    ; Se fue abajo de cero: queda en cero.
    rep #$20
.a16
    stz oro
    sep #$20
.a8
    stz oro + 2
    bra oro_listo
oro_recorta:
    ; ¿Se pasó de ORO_MAX? Se compara de 24 bits, el byte alto primero.
    lda oro + 2
    cmp #^ORO_MAX
    bcc oro_listo
    bne oro_tope
    rep #$20
.a16
    lda oro
    cmp #.loword(ORO_MAX)
    sep #$20
.a8
    bcc oro_listo
    beq oro_listo
oro_tope:
    rep #$20
.a16
    lda #.loword(ORO_MAX)
    sta oro
    sep #$20
.a8
    lda #^ORO_MAX
    sta oro + 2
oro_listo:
    ply
    jmp otro

; `ChangeItems`: el ítem de dieciséis bits y cuánto se suma, con signo. Es
; `Game_Party::AddItem`: la cuenta queda en [0, ITEM_MAX]. Y como cambiar
; un ítem puede cambiar qué página está activa, pide el refresco: RM2k hace
; `SetNeedRefresh(true)` tras cada ChangeItems.
op_item:
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el ítem
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sta temp + 2                ; el puerto avanza al leer y no se puede leer
    iny                         ; de vuelta: se guarda la dirección
    iny
    sep #$20
.a8
    stz WMADDH
    lda [cod_ptr], y            ; cuánto, con signo
    iny
    sta temp
    lda WMDATA                  ; la cuenta que había
    clc
    adc temp
    bit temp
    bmi item_resto
    ; Sumó: si se pasó de ITEM_MAX —o dio la vuelta— queda en el tope.
    bcs item_tope
    cmp #(ITEM_MAX + 1)
    bcc item_guardar
item_tope:
    lda #ITEM_MAX
    bra item_guardar
item_resto:
    ; Restó: sin acarreo se fue abajo de cero, y queda en cero.
    bcs item_guardar
    lda #0
item_guardar:
    pha
    rep #$20
.a16
    lda temp + 2                ; el puerto avanzó al leer: se vuelve
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    lda #1
    sta refresco
    jmp otro

; `OpenShop`: tipo, juego, cuántos y la lista, de a dos bytes cada ítem. La
; tienda se abre acá adentro y, al salir, el mapa vuelve y la página sigue.
op_shop:
.a8
.i16
    lda [cod_ptr], y
    sta comp_col + 1
    iny
    lda [cod_ptr], y
    sta comp_fase
    iny
    lda [cod_ptr], y
    iny
    sta eleg_cancel             ; cuántos vienen
    stz comp_mask + 1
    ; `item_k` vive en el banco del código y el intérprete corre con el banco
    ; de datos donde está el bytecode: se cambia hasta volver.
    phb
    phk
    plb
op_shop_other:
    lda eleg_cancel
    beq op_shop_done
    rep #$20
.a16
    lda [cod_ptr], y            ; el ítem
    iny
    iny
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq op_shop_next         ; uno que esta ROM no conoce
    pha
    rep #$20
.a16
    lda comp_mask + 1
    and #$00FF
    clc
    adc #FAR_TIENDA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_mask + 1
op_shop_next:
    dec eleg_cancel
    bra op_shop_other
op_shop_done:
    phy
    jsl f:tienda_pantalla
    ; Los flancos que cerraron la tienda son de ella, como en el menú.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    jsr volver_al_mapa
    ply
    plb
    jmp otro

; `EnemyEncounter`: la tropa y los tres destinos, todos de dieciséis bits. La
; pelea se juega acá adentro y, al salir, el mapa vuelve —como en la tienda— y
; la página sigue por el destino que le tocó al resultado.
op_battle:
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; la tropa, como número de RM2k
    sta f:BAT_LARGO + BA_TROPA
    sep #$20
.a8
    lda #0
    sta f:BAT_LARGO + ESC_ORIGEN ; el fondo, el de la tropa y no el del mapa
    phy                         ; el cursor: los destinos se leen al volver
    jsr pelea_arrancar
    ply
    ; Y apunta a la tropa; los tres destinos vienen detrás, de a palabra, en el
    ; orden victoria, huida, derrota, que es el de `BATALLA_HANDLERS`.
    lda f:BAT_LARGO + BA_RESULT
    jmp op_battle_destination

op_battle_destination:
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sty temp
    clc
    adc temp
    inc a
    inc a
    tay
    lda [cod_ptr], y            ; el destino, absoluto dentro de la página
    tay
    ; `BATALLA_PERDER`, o sea $FFFF: la pelea no traía manejador de derrota
    ; porque en RM2k perderla es `Scene_Gameover`. Es un destino imposible —los
    ; tres son absolutos adentro de la página y ninguna llega a 64 KB— así que
    ; no hace falta un opcode nuevo ni un byte más en las otras peleas. El `iny`
    ; es el `cmp #$FFFF` barato: con A de 16 bits compararlo costaría tres
    ; bytes y en el banco 0 no sobran.
    ;
    ; **Game Over es volver al arranque**, que es la pantalla de título si esta
    ; ROM la lleva, con la partida guardada esperando en la SRAM: es lo que
    ; `Scene_Gameover` hace cuando el jugador aprieta, menos la imagen, que este
    ; port no dibuja —ver
    ; workflow/divergencias/game-over-sin-imagen-ni-tema.md—. Se va con `jml` y
    ; no devolviendo el control porque no hay a dónde volver: la página no tiene
    ; rama de derrota y `reset` repone la pila él mismo.
    iny
    bne sigue_la_pagina
    jml f:reset
sigue_la_pagina:
    dey
    sep #$20
.a8
    jmp otro


; `OP_SOUND`: el índice en `sonido_tabla`. Queda pendiente y arranca al
; final de `music_tick`, detrás de lo que la música escriba en el cuadro.
op_sound:
    jsr sonido_de_codigo
    jmp otro

; Los tres del cartel. `OP_PICTURE` lo pone ya con su tono —`Game_Pictures::
; Show` deja `time_left` en cero—, `OP_PICTURE_MOVE` arranca la rampa hacia
; otro tono y `OP_PICTURE_ERASE` lo saca. Ninguno corta el cuadro: si la página
; espera lo que dura el fundido, el conversor le pone un OP_DELAY detrás,
; igual que al `FlashScreen` y a la sacudida.
op_picture:
    ldx #$0000
img_poner:
    lda [cod_ptr], y
    cpx #3
    bcs img_poner_sat           ; el cuarto operando es la saturación, que no
    sta f:CARTEL_TONO, x        ; se guarda: la del cartel es siempre la neutra
    sta f:CARTEL_DESDE, x
    sta f:CARTEL_HASTA, x
img_poner_sat:
    iny
    inx
    cpx #4
    bne img_poner
    lda #1
    sta f:CARTEL_ACTIVA
    lda #0
    sta f:CARTEL_PASO
    sta f:CARTEL_PASOS
    jsr imagen_paleta
    jmp otro

op_picture_move:
    ldx #$0000
img_mover:
    lda [cod_ptr], y
    cpx #3
    bcs img_mover_sat           ; la saturación, otra vez
    sta f:CARTEL_HASTA, x
img_mover_sat:
    iny
    inx
    cpx #4
    bne img_mover
    lda [cod_ptr], y
    sta f:CARTEL_PASOS
    iny
    ; Un `Move` sobre una imagen que no se mostró le escribe el destino a algo
    ; que no se dibuja: los operandos se consumen igual —el stream tiene que
    ; seguir en el mismo byte de los dos lados— y no pasa nada más.
    lda f:CARTEL_ACTIVA
    beq img_mover_fin
    lda f:CARTEL_PASOS
    bne img_mover_rampa
    ldx #$0000
img_mover_ya:
    lda f:CARTEL_HASTA, x
    sta f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_ya
    lda #0
    sta f:CARTEL_PASO
    jsr imagen_paleta
    jmp otro
img_mover_rampa:
    ldx #$0000
img_mover_desde:
    lda f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_desde
    lda #0
    sta f:CARTEL_PASO
img_mover_fin:
    jmp otro

op_picture_erase:
    lda #0
    sta f:CARTEL_ACTIVA
    jmp otro

; `OP_ANIMATION`: el número de animación de RM2k, sobre qué se dibuja, cuántas
; entradas y las entradas, que se quedan en el bytecode. Ver OP_ANIMATION en
; eventos.py y `animacion_tick`. La nueva reemplaza a la que hubiera, y no
; cuesta ningún tick.
;
; Los dos primeros bytes son del **dibujo**, que va por su cuenta y dura más
; que la línea de tiempo: ver `animacion_dibujo_empezar`.
op_animation:
    lda [cod_ptr], y            ; el número de animación de RM2k
    sta temp
    iny
    lda [cod_ptr], y            ; y sobre qué va: $FF es la pantalla
    sta temp + 1
    iny
    phy
    jsr animacion_dibujo_empezar
    ply
    lda [cod_ptr], y            ; cuántas
    sta f:ANIM_N
    iny
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta f:ANIM_PTR              ; la primera, en el banco del bytecode
    sep #$20
.a8
    lda cod_ptr + 2
    sta f:ANIM_PTR + 2
    lda #0
    sta f:ANIM_T
    lda f:ANIM_N
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; ocho bytes por entrada
    sta temp
    tya
    clc
    adc temp
    tay
    sep #$20
.a8
    jmp otro

; `WeatherEffects`: el tipo y la fuerza. No cuesta ningún tick.
op_weather:
.a8
.i16
    lda [cod_ptr], y
    sta temp
    iny
    lda [cod_ptr], y
    sta temp + 1
    iny
    phy
    jsr clima_poner
    ply
    jmp otro

; `ChangeSaveAccess`, `ChangeMainMenuAccess` y `ChangeEscapeAccess`: **el bit**
; del permiso y si queda permitido. Prende o apaga ese bit de "prohibido" de
; `FAR_ACCESO`.
;
; El bit lo pone el conversor y acá no se calcula, y eso es lo que deja agregar
; permisos sin tocar este opcode: antes el operando era el número del permiso y
; el bit salía de un `inc a`, que da $01 y $02 para los dos primeros y **$03
; para el tercero**, o sea prohibir las otras dos cosas de una.
op_access:
.a8
.i16
    lda [cod_ptr], y            ; el bit: $01 guardar, $02 el menú, $04 escapar
    sta temp
    iny
    lda [cod_ptr], y            ; permitido
    iny
    sta temp + 1
    phy
    ; El permiso se mira con A de ocho bits y no con Y: con los índices en
    ; dieciséis, `ldy temp + 1` se llevaba también `temp + 2`, y un permiso
    ; en cero con basura al lado quedaba permitido.
    jsr acceso_leer
    xba                         ; B = los permisos, mientras se mira
    lda temp + 1
    beq acceso_prohibir
    lda temp
    eor #$FF
    sta temp
    xba
    and temp
    bra acceso_listo
acceso_prohibir:
    xba
    ora temp
acceso_listo:
    jsr acceso_escribir
    ply
    jmp otro

; El salto sin condición que el conversor pone donde estaba el `else`, para que
; la rama de arriba se saltee la de abajo.
op_goto:
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp otro

; `ShowChoice`: abre la ventana con las opciones y corta el cuadro, igual que
; un mensaje. La diferencia es que la página **no retoma donde quedó**: cuando
; el jugador elige, `eleccion_tick` le pone al cursor el destino de la opción
; marcada. Por eso acá no se guarda `ev_cur`: lo que se guarda es dónde está la
; tabla, que es de donde salen los dos, el cuadro que se dibuja y el destino.
op_choice:
    lda [cod_ptr], y            ; cuántas opciones
    sta eleg_n
    iny
    lda [cod_ptr], y            ; qué opción elige cancelar, más uno
    sta eleg_cancel
    iny
    sty eleg_tabla
    stz eleg_sel                ; `Window_Selectable` arranca con el índice en
                                ; cero, y la primera opción es la marcada
    lda #1
    sta eleg_activo
    jsr eleg_abrir
    rts


op_switch:
    rep #$20
.a16
    lda [cod_ptr], y            ; el número, de 16 bits
    sta temp
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y si va encendido o apagado
    iny
    phy
    jsr poner_switch
    ply
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

; Una ruta forzada de MoveEvent. El primer operando dice sobre quién: 0 es el
; héroe, y cualquier otro número es el índice del evento en la tabla del mapa
; más uno. **No es el id de RM2k**: 39 mapas de este juego tienen huecos en la
; numeración de eventos, y traducir es cosa del conversor.
;
; De todos los comandos de ruta de RM2k acá se aceptan los cuatro de girar, los
; cuatro de mover y la espera: el conversor no emite ningún otro.
;
; face_up/right/down/left son 12, 13, 14 y 15, y nuestras direcciones son
; 0, 1, 2 y 3 en el mismo orden, así que restar doce alcanza.
;
; Los dos caminos se parecen pero no son el mismo, y la diferencia vale la pena:
; la del héroe se **copia** a RAM, y la de un evento se guarda como puntero al
; bytecode. Copiarla existe desde antes y tiene un tope, RUTA_MAX; el puntero no
; lo tiene, porque el código del mapa vive en la ROM y no se va a ningún lado.
op_route:
    lda [cod_ptr], y            ; sobre quién
    sta ruta_blanco
    iny
    lda [cod_ptr], y            ; con qué frecuencia
    sta ruta_frec_op
    iny
    lda [cod_ptr], y            ; cuántos comandos trae
    sta ruta_cuantas
    stz ruta_cuantas + 1
    iny
    lda ruta_blanco
    bne op_route_event

    ; --- el héroe: la ruta se copia a RAM y la camina `move_hero`, no el
    ; intérprete: en RM2k `ForceMoveRoute` es asincrónico y la página sigue.
    ; Lo que se corta es la espera —`SetStopCount(0xFFFF)`: la primera orden
    ; corre ya— y nada más: el paso o el salto en curso se terminan, como
    ; allá. Acá se cortaba también el salto, y la referencia no.
    lda ruta_cuantas
    sta temp
    stz ruta_i
    stz ruta_espera
    lda ruta_frec_op
    sta ruta_frec
    ldx #$0000
copiar_orden:
    lda temp
    beq fin_copia
    dec temp
    cpx #RUTA_MAX
    bcs saltear                 ; no entra: se consume pero no se guarda
    lda [cod_ptr], y
    sta ruta, x
    inx
saltear:
    iny
    bra copiar_orden
fin_copia:
    txa                         ; X no pasa de RUTA_MAX, así que el byte alcanza
    sta ruta_n
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

    ; --- un evento: no se copia nada. Se anota dónde empieza la ruta dentro del
    ; bytecode y en qué orden va, y el cursor de la página saltea las órdenes.
op_route_event:
    phy
    jsr ruta_para_evento
    ply
    rep #$20
.a16
    tya
    clc
    adc ruta_cuantas
    tay
    sep #$20
.a8
    jmp otro

; Planta a un evento en una celda: ChangeEventLocation. Es `MoveTo`, y nada
; más que `MoveTo`: la celda cambia ya y el paso o el salto en curso se cortan
; —`SetRemainingStep(0)`—, la ruta que tuviera sigue con la orden siguiente
; desde acá, y hacia dónde mira no cambia; la dirección la toca sólo RM2k3. La
; cinemática de apertura lo usa seis veces para traer a Core, a Manta y al
; droide a escena.
op_place:
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda [cod_ptr], y
    sta ev_pos_buf + 0, x       ; la celda, que es lo que miran las rutas, la
    iny                         ; tecla de acción y el contacto
    iny
    lda [cod_ptr], y
    sta ev_pos_buf + 2, x
    iny
    iny
    sep #$20
.a8
    phy
lugar_plantar:                  ; con Y ya en la pila: ver `op_place_var`
    jsr plantar_evento
    ply
    jmp otro

; `ChangeEventLocation` con la celda en **dos variables**, que es la otra rama
; de `CommandChangeEventLocation`. Lo demás es idéntico a `op_place`: el mismo
; `MoveTo`, o sea la celda cambia ya, el paso en curso se corta y ni la ruta ni
; hacia dónde mira se tocan. Ver OP_PLACE_VAR en eventos.py.
;
; Las dos lecturas van **antes** de escribir ninguna de las dos palabras, como
; en `op_swap`: una variable que se leyera después de haber movido al evento
; ya podría valer otra cosa si es una de las de coordenadas de `ControlVars`.
; En este juego no pasa —el minijuego del mapa 11 las calcula antes— pero es la
; misma regla y no cuesta nada.
;
; `var_leer` no toca X ni `temp`, así que el desplazamiento de la fila se
; calcula una sola vez y sobrevive a las dos lecturas.
op_place_var:
.a8
.i16
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    lda [cod_ptr], y            ; la ranura de la x
    sta temp + 1
    iny
    lda [cod_ptr], y            ; y la de la y
    sta temp + 2
    iny
    phy
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    lda temp + 1
    jsr var_leer                ; vuelve con M en dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 2
    jsr var_leer
.a16
    sta ev_pos_buf + 2, x
    pla
    sta ev_pos_buf + 0, x
    sep #$20
.a8
    bra lugar_plantar

; `TradeEventLocations`: los dos eventos se cambian de celda, y cada uno es un
; `MoveTo` como el de `op_place` —la celda, el corte del paso, y el dibujo que
; la sigue—. Las dos celdas se leen antes de escribir ninguna.
op_swap:
    lda [cod_ptr], y            ; el primero: el índice más uno
    dec a
    sta trueque_a
    iny
    lda [cod_ptr], y            ; y el segundo
    dec a
    sta trueque_b
    iny
    phy
    rep #$20
.a16
    lda trueque_a
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda trueque_b
    and #$00FF
    asl a
    asl a
    tay
    lda ev_pos_buf + 0, x
    sta celda_x
    lda ev_pos_buf + 2, x
    sta celda_y
    lda ev_pos_buf + 0, y
    sta ev_pos_buf + 0, x
    lda ev_pos_buf + 2, y
    sta ev_pos_buf + 2, x
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    lda trueque_a
    sta temp
    jsr plantar_evento
    lda trueque_b
    sta temp
    jsr plantar_evento
    ply
    jmp otro

; `ShakeScreen`: `ShakeOnce`, que no reinicia la posición para que dos
; sacudidas seguidas se encadenen suaves, o `ShakeEnd` con cero cuadros. No
; corta el cuadro: si la página espera, el conversor le pone un OP_DELAY
; detrás, como con los destellos.
op_shake:
    lda [cod_ptr], y            ; fuerza
    sta sacudida_fuerza
    iny
    lda [cod_ptr], y            ; velocidad
    sta sacudida_vel
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; cuadros
    sta sacudida_resta
    bne con_cuadros
    stz sacudida_pos            ; ShakeEnd: la pantalla vuelve a su lugar
con_cuadros:
    iny
    iny
    sep #$20
.a8
    jmp otro

; `FlashOnce`: el color, el nivel a escala 256 y los cuadros. No corta el
; cuadro: si la página espera, el conversor le pone un OP_DELAY detrás.
op_flash_screen:
    jsr destello_de_codigo
    jmp otro

; Arranca un destello sobre un personaje. No corta el cuadro: si la página
; espera, el conversor le pone un OP_DELAY detrás, que es exactamente lo que
; hace `CommandFlashSprite` con `SetupWait(tenths)`.
op_flash:
    phy
    jsr flash_empezar
    ply
    rep #$20
.a16
    tya
    clc
    adc #6                      ; los seis operandos
    tay
    sep #$20
.a8
    jmp otro

; El cronómetro: poner, arrancar o parar. Los cinco bytes de operando son fijos
; aunque cada operación use dos, así que el cursor avanza igual en las tres.
op_timer:
    lda [cod_ptr], y            ; la operación
    sta temp
    iny
    cmp #TIMER_PONER
    bne no_pone
    rep #$20
.a16
    lda [cod_ptr], y            ; los segundos, de dieciséis bits
timer_poner_16:
    sta timer_seg
    sep #$20
.a8
    ; `Game_Party::SetTimer` guarda `segundos * 60 + 59`: los 59 de más son lo
    ; que hace que el valor pedido se vea un segundo entero y no un cuadro.
    ; Acá los cuadros van partidos, así que son el resto y nada más.
    lda #TIMER_DE_MAS
    sta timer_sub
    jsr timer_digitos
    bra timer_fin
no_pone:
    cmp #TIMER_PONER_VAR
    bne no_pone_var
    ; Los segundos desde una variable, que es lo que hace el Tram Officer del
    ; mapa 9: "lo que le queda al cronómetro, menos sesenta". Una variable
    ; negativa pone cero, como `Game_Party::SetTimer`.
    lda [cod_ptr], y            ; la ranura
    phy
    jsr var_leer                ; A de dieciséis bits
.a16
    ply
    cmp #0                      ; el signo de la variable, que `ply` pisó con
                                ; el cursor: ver `tema_asegurar`
    bpl timer_poner_16
    lda #0
    bra timer_poner_16
.a8
no_pone_var:
    cmp #TIMER_ARRANCAR
    bne timer_para
    lda #1
    sta timer_activo
    iny
    iny
    lda [cod_ptr], y            ; si se ve
    sta timer_visible
    dey
    dey
    bra timer_fin
timer_para:
    ; `StopTimer` apaga las dos cosas, no sólo la cuenta.
    stz timer_activo
    stz timer_visible
timer_fin:
    rep #$20
.a16
    tya
    clc
    adc #3                      ; los tres operandos que quedan: el primero ya
    tay                         ; lo consumió el `iny` de la operación
    sep #$20
.a8
    jmp otro

; `PlayBGM`. El operando es el índice del tema en `Temas`, y el cartucho lleva
; los que hayan entrado en la ARAM: los primeros `TEMA_TOTAL`. Un índice más
; alto es un tema que no entró y no suena, que es lo que pasaba con todos menos
; uno hasta el 2026-09-06. Ver `temas_de_la_rom` en el conversor.
op_bgm:
    lda [cod_ptr], y
    iny
    cmp #TEMA_TOTAL
    bcs otro_tema
    phy
    jsr music_start
    ply
otro_tema:
    jmp otro

; `FadeOutBGM`. El operando es cuánto baja el volumen por cuadro; lo baja
; `bgm_fundido_tick`, no acá, y la página sigue de largo en este mismo cuadro,
; que es lo que hace `CommandFadeOutBGM` devolviendo true.
;
; Con el tema apagado no se arranca nada: el fundido escribiría el volumen de un
; tema que no suena, y encima lo dejaría en cero para el `PlayBGM` que venga.
;
; Con una pista del MSU-1 sonando, en cambio, sí hay qué fundir: `music_apagada`
; vale 1 —el SPC700 está callado a propósito— y el que baja es el volumen del
; MSU-1. Sin esta salida, un `FadeOutBGM` no hacía nada y la pista seguía
; sonando para siempre.
op_fade_bgm:
    lda f:MSU_SUENA
    bne fundir
    lda music_apagada
    bne fundir_nada
fundir:
    php
    sei                         ; lo lee `irq_musica`: todo junto o nada
    lda [cod_ptr], y
    sta bgm_paso
    iny
    lda [cod_ptr], y
    sta bgm_paso + 1
    iny
    lda #$FF
    sta bgm_nivel               ; el volumen entero, que es de donde baja
    sta bgm_nivel + 1
    lda #1
    sta bgm_fundido
    plp
    jmp otro
fundir_nada:
    iny
    iny
    jmp otro

; `OpenSaveMenu`: la pantalla de ranuras en modo guardar, y la partida a la
; que el jugador elija. Sin operandos. La referencia hace lo mismo con el mismo
; opcode: ver `OP_SAVE` en tools/port/eventos.py.
;
; **Bloquea adentro del intérprete y no cuesta ningún tick**, que es lo que hace
; RM2k: `OpenSaveMenu` apila `Scene_Save`, el mapa deja de actualizarse hasta
; que se cierra, y la página sigue por el comando siguiente. Acá
; `ranuras_pantalla` corre su propio lazo de cuadros —como desde el título— y
; `vueltas` no avanza mientras se ve, así que los dos intérpretes siguen en el
; mismo tick cuando vuelve. Cancelar con B vuelve al mapa sin guardar, que es
; también lo de RM2k; elegir guarda y vuelve, sin preguntar si la ranura estaba
; ocupada, porque `Scene_Save::Action` tampoco pregunta.
;
; La pantalla pisó la VRAM de los tiles y la paleta 0, y `volver_al_mapa` los
; repone. El estado del juego no se toca: la tabla de eventos, las rutas, la
; OAM y las poses en VRAM siguen como estaban, y por eso no se llama a
; `cargar_mapa`, que reiniciaría todo eso.
;
; Hasta el 2026-09-10 esto guardaba en la ranura cargada —o en la primera— sin
; mostrar nada, y el intento de abrir la pantalla dio "negro con basura": la
; ROM de prueba no llevaba título, y sin título el conversor emitía la pantalla
; de ranuras como un byte de relleno con `RANURA_TILES` en cero. Hoy va en toda
; ROM.
op_save:
    phy
    lda #1                      ; modo guardar
    jsr ranuras_pantalla
    cmp #$FF
    beq cancelado
    jsr poner_ranura
    jsr guardar_partida
cancelado:
    jsr volver_al_mapa
    ply
    jmp otro

; "Esperá a que terminen las rutas". Si no queda ninguna corriendo no cuesta ni
; un cuadro, que es lo que hace el `while` de `Game_Interpreter::Update`; y si
; queda, el cursor se deja **en el opcode** y se corta el cuadro, así que el
; siguiente vuelve a preguntar. Espera a que no quede **ninguna**, ni la del
; héroe ni la de ningún evento: es `Game_Map::IsAnyMovePending`, y no una espera
; por el evento que se acaba de mandar a caminar.
op_wait_routes:
    jsr hay_rutas
    beq op_wait_routes_next
    dey                         ; el cursor vuelve al opcode
    sty ev_cur
    rts
op_wait_routes_next:
    jmp otro

; `HaltAllMovement`: todas las rutas forzadas del mapa se abandonan de golpe.
; Es `Game_Map::RemoveAllPendingMoves`, o sea un `CancelMoveRoute` sobre el
; héroe y sobre cada evento. No cuesta un cuadro: la página sigue en el mismo
; tick, que es el `return true` de `CommandHaltAllMovement`.
;
; Lo que **no** hace, y es lo que lo separa de `MoveTo`: el paso y el salto en
; curso se terminan, y hacia dónde mira cada uno queda donde la ruta lo dejó.
; `hay_rutas` los sigue mirando, así que un `ProceedWithMovement` pegado atrás
; espera los cuadros que le falten al paso; la referencia cuenta igual.
;
; Y quien tenía ruta propia de página vuelve a la suya con `retomar_pagina`,
; que es la misma rutina que corre cuando una forzada termina sola: cancelarla
; y terminarla no se pueden separar, que es justo la clase de diferencia que
; nadie ve hasta que la escena sale distinta.
op_stop_routes:
.a8
.i16
    ; El héroe. Se le vacían las órdenes y la espera; el paso en curso no.
    stz ruta_n
    stz ruta_i
    stz ruta_espera
    phy                         ; Y es el cursor del bytecode
    ldx #$0000
parar_otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq parar_siguiente
    lda ruta_ev + 18, x
    and #$01
    bne parar_siguiente         ; la de la página no es forzada
    lda ruta_ev + 27, x         ; ¿tiene ruta propia a la que volver?
    beq parar_sin_pagina
    jsr retomar_pagina
    bra parar_siguiente
parar_sin_pagina:
    stz ruta_ev + 4, x
    stz ruta_ev + 5, x
    stz ruta_ev + 9, x
parar_siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc parar_otra
    ply
    jmp otro

; `ControlVars`, de a una variable: ranura, operación, clase del operando, y
; a y b de dieciséis bits. Ver OP_VAR en eventos.py. Dieciséis bits con signo,
; dando la vuelta.
op_var:
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la operación
    iny
    lda [cod_ptr], y            ; la clase del operando
    iny
    phy                         ; Y -> a; se repone al final
    cmp #VAR_VARIABLE
    beq var_de_variable
    cmp #VAR_AZAR
    beq var_al_azar
    cmp #VAR_OTRO
    beq var_de_otro
    cmp #VAR_PERSONAJE
    bne :+
    jmp var_de_personaje
:
    rep #$20
.a16
    lda [cod_ptr], y            ; una constante
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_variable:
    lda [cod_ptr], y            ; la ranura de donde sale
    jsr var_leer
.a16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_otro:
    lda [cod_ptr], y
    bne var_del_timer
    ; El oro, topado en 32767: la variable es de dieciséis bits con signo.
    lda oro + 2
    bne var_oro_tope
    rep #$20
.a16
    lda oro
    bmi var_oro_tope_16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
.a16
var_oro_tope_16:
    sep #$20
.a8
var_oro_tope:
    lda #$FF
    sta temp + 2
    lda #$7F
    sta temp + 3
    bra var_aplicar
var_del_timer:
    rep #$20
.a16
    lda timer_seg               ; los segundos que le quedan al cronómetro
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_al_azar:
    ; a + x mod (b - a + 1), con x el paso siguiente del xorshift y el módulo
    ; con el divisor de ocho bits del hardware: el conversor no deja pasar un
    ; rango de más de 255.
    jsr azar_siguiente
    sta WRDIVL                  ; el dividendo, de dieciséis
    lda [cod_ptr], y            ; a
    sta temp + 2
    iny
    iny
    lda [cod_ptr], y            ; b
    sec
    sbc temp + 2
    inc a                       ; b - a + 1
    sep #$20
.a8
    sta WRDIVB                  ; arranca: dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL                  ; el resto
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_aplicar:
    ; `temp + 2` es el operando; según la operación, se pone tal cual o se
    ; suma o resta a lo que la variable tenía.
    lda temp + 1
    beq var_pone
    lda temp
    jsr var_leer                ; A = lo que tenía, de dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 1
    cmp #VAR_SUMAR
    beq var_suma
    rep #$20
.a16
    pla
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    bra var_pone
var_suma:
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_pone:
    lda temp
    jsr var_escribir            ; y el refresco, si la ranura lo pide: las
                                ; páginas que miran esta variable pueden
    ply                         ; cambiar. Ver `var_escribir`
    iny                         ; a y b, cuatro bytes
    iny
    iny
    iny
    jmp otro

var_de_personaje:
    ; La clase 6: las coordenadas de un personaje, en celdas. `a` es el blanco
    ; —0 el héroe, el índice del evento más uno, el mismo byte que OP_ROUTE— y
    ; `b` dice cuál: PERSONAJE_X o PERSONAJE_Y.
    ;
    ; La celda que se lee es la **viva**: `tile_x`/`tile_y` para el héroe y
    ; `ev_pos_buf` para un evento, que es adonde una ruta forzada, un
    ; ChangeEventLocation o un TradeEventLocations la dejaron. En RM2k es
    ; `character->GetX()`, o sea lo mismo.
    ; No se guarda ninguno de los dos operandos en RAM: la BSS está llena
    ; —dos bytes más y `ld65` avisa que no entra— y no hace falta. El blanco
    ; **por** EV_STRIDE se lleva en X, que acá no la usa nadie, y con el
    ; corrimiento puesto en la dirección: así el héroe queda con X en cero y
    ; distinguirlo es un `cpx`, que no toca el acumulador.
    lda [cod_ptr], y            ; a: el blanco
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; b: cuál coordenada
    cpx #$0000
    beq var_personaje_heroe
    ; Un evento: su celda está en `ev_pos_buf`, indexada por el índice de la
    ; tabla del mapa, que es el blanco menos uno; de ahí el - EV_STRIDE.
    cmp #PERSONAJE_X
    beq var_personaje_ev_x
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 2, x
    bra var_personaje_listo
.a8
var_personaje_ev_x:
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 0, x
    bra var_personaje_listo
.a8
var_personaje_heroe:
    cmp #PERSONAJE_X
    beq var_personaje_heroe_x
    rep #$20
.a16
    lda tile_y
    bra var_personaje_listo
.a8
var_personaje_heroe_x:
    rep #$20
.a16
    lda tile_x
var_personaje_listo:
    sta temp + 2
    sep #$20
.a8
    jmp var_aplicar

; `ConditionalBranch` por variable: ranura, clase del valor, comparación, el
; valor de dieciséis bits y el destino si no se cumple. La comparación es con
; signo: después de restar, "menor" es N distinto de V.
op_if_var:
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la clase: constante u otra variable
    iny
    lda [cod_ptr], y            ; la comparación
    pha
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; el valor, o la ranura
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> el destino
    lda temp + 1
    beq si_var_contra_constante
    lda temp + 2
    phy
    jsr var_leer
.a16
    ply
    sta temp + 2
    sep #$20
.a8
si_var_contra_constante:
    pla                         ; la comparación
    sta temp + 1
    lda temp
    phy
    jsr var_leer                ; A = la variable, de dieciséis
.a16
    jsr comparar_var
.a8
    ply
    cmp #0                      ; lo que dijo `comparar_var`, que `ply` pisó
                                ; con el cursor: ver `tema_asegurar`
    bne si_var_sigue
    rep #$20
.a16
    lda [cod_ptr], y            ; no se cumple: al destino
    tay
    sep #$20
.a8
    jmp otro
si_var_sigue:
    iny
    iny
    jmp otro

op_party:
    lda [cod_ptr], y            ; 0 = agregar, 1 = sacar
    sta temp
    iny
    lda [cod_ptr], y            ; el actor
    iny
    phy
    jsr cambiar_grupo
    ply
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

; `ChangeSpriteAssociation`: el actor y el índice del gráfico en la tabla del
; mapa, la misma que resuelve la orden 34 de una ruta. Ver OP_ACTOR_SPRITE en
; eventos.py.
;
; El `ResetGraphic()` que RM2k le hace al `Game_Player` es el `jsr
; elegir_grafico_heroe` de acá abajo, y va sólo si el que cambió es el que
; lidera: el que no lidera no se dibuja, y lo guardado lo va a leer
; `elegir_grafico_heroe` cuando le toque —al cambiar el grupo o al cargar otro
; mapa—.
;
; `aplicar_tinte` detrás por lo mismo que en `cambiar_grupo`: la fila de CGRAM
; que el líder tenía prestada queda con sus quince colores encima de los del
; mapa, y hay que reponerla desde el cartucho.
op_actor_sprite:
.a8
.i16
    lda [cod_ptr], y            ; el actor
    iny
    sta temp
    lda [cod_ptr], y            ; el gráfico
    iny
    sta temp + 1
    phy
    lda temp
    jsr actor_graf_escribir
    lda temp
    cmp grupo                   ; ¿es el líder?
    bne graf_no_lidera
    jsr elegir_grafico_heroe
    jsr aplicar_tinte
graf_no_lidera:
    ply
    jmp otro

; `FullHeal` y `ChangeHP` que suma. Acá está sólo la entrada: el cuerpo es
; `curar`, fuera del banco 0, y lee sus operandos y avanza el cursor él mismo,
; con Y en la mano.
op_heal:
    jsl f:curar
    jmp otro

; `ChangeEquipment` y `ChangeSkills`: como `op_heal`, sólo la entrada. Los
; cuerpos son `equipo_quitar` y `habilidad_cambiar`, fuera del banco 0.
op_equipment:
    jsl f:equipo_quitar
    jmp otro
op_skill:
    jsl f:habilidad_cambiar
    jmp otro

; `GameOver`: volver al arranque, igual que perder una pelea sin manejador de
; derrota —ver `op_battle_destination`—, y por lo mismo con `jml`: no hay a
; dónde volver.
;
; Antes, lo que `CommandGameOver` pide: **que no haya un mensaje abierto**. Si
; lo hay, espera, como `op_message` con el de otro. El primer plano no llega
; acá con uno abierto —`eventos_tick` no lo llama—; un paralelo sí, y sin esto
; el reinicio se comería el mensaje que otro está mostrando.
op_game_over:
    lda par_ev
    cmp #$FF
    beq game_over_ya            ; primer plano
    lda msg_abierto
    ora msg_estado
    ora eleg_activo
    beq game_over_ya
    dey                         ; el cursor vuelve a este mismo opcode
    sty ev_cur
    rts
game_over_ya:
    jml f:reset

; `TileSubstitution`: de ahora en más, donde la grilla diga tal bloque se
; dibuja tal otro. La instrucción trae **varios** pares porque RM2k sustituye
; por número de tile y acá la unidad es el bloque de 16x16, que lleva las dos
; capas juntas: un tile de RM2k puede estar en tantos bloques como
; combinaciones tenga con la otra capa. Cuáles son lo resolvió el conversor,
; ver `Sustituciones` en snes_convert.py.
;
; La tabla se aplica como `DoSubstitute` de easyrpg, que recorre la traducción
; entera y cambia **los valores** que sean el bloque viejo, no las claves:
;
;   * todo par que hoy apunte al que sale pasa a apuntar al que entra, que es
;     lo que hace que sustituir A→B y después B→A deshaga la primera en vez de
;     dejar dos reglas peleándose;
;   * y si ninguna clave es el que sale, se agrega el par, que es la entrada
;     identidad que la tabla no guarda por no ocupar lugar.
op_tile_sub:
.a8
.i16
    lda [cod_ptr], y            ; cuántos pares trae la instrucción
    iny
    sta sub_quedan
otro_par:
    sep #$20
.a8
    lda sub_quedan
    beq sub_listo
    dec a
    sta sub_quedan
    rep #$20
.a16
    lda [cod_ptr], y            ; el bloque que sale
    sta sub_de
    iny
    iny
    lda [cod_ptr], y            ; y el que entra
    sta sub_a
    iny
    iny
    stz sub_hay
    ldx #$0000
recorrer_sub:
    cpx sub_n
    beq agregar_sub
    lda sub_clave, x
    cmp sub_de
    bne no_es_clave
    inc sub_hay
no_es_clave:
    lda sub_valor, x
    cmp sub_de
    bne sigue_sub
    lda sub_a
    sta sub_valor, x
sigue_sub:
    inx
    inx
    bra recorrer_sub
agregar_sub:
    lda sub_hay
    bne otro_par                ; la clave ya estaba, y el lazo le puso el valor
    lda sub_n
    cmp #(SUB_MAX * 2)
    bcs otro_par                ; no entra. El conversor se niega a emitir un
    tax                         ; mapa que pueda llegar acá: ver SUB_MAX
    lda sub_de
    sta sub_clave, x
    lda sub_a
    sta sub_valor, x
    txa
    inc a
    inc a
    sta sub_n
    bra otro_par
sub_listo:
    rep #$20
.a16
    lda #WINDOW_COLS            ; y la ventana se rehace de a una columna por
    sta sub_refresco            ; cuadro: ver `sub_refresco`
    sep #$20
.a8
    jmp otro

; `StoreTerrainID`: el terreno de una celda a una variable.
;
; **El terreno sale del tile de la capa de abajo**, no de la alta —"RPG_RT
; always uses the terrain of the first lower tile"—, así que acá sale del
; bloque, que es lo que la ROM tiene: el conversor ya metió el terreno en la
; clave del bloque, y emitió un byte por bloque. Y como sale del bloque, una
; `TileSubstitution` puesta lo cambia, que es lo que hace `GetTerrainTag` al
; pasar por `map_info.lower_tiles`.
;
; Un mapa con un solo terreno —los 328 de este juego— no lleva tabla: la
; contesta `TERRENO_PLANO`. Fuera del mapa contesta `TERRENO_FUERA`, que es el
; terreno del **primer tile del ChipSet** y no el de ninguna celda.
op_terrain:
.a8
.i16
    lda [cod_ptr], y            ; el modo: 0 la celda escrita, 1 por variable
    iny
    sta temp
    rep #$20
.a16
    lda [cod_ptr], y
    sta celda_x
    iny
    iny
    lda [cod_ptr], y
    sta celda_y
    iny
    iny
    sep #$20
.a8
    lda [cod_ptr], y            ; la ranura donde se guarda, con VAR_REFRESCO
    iny
    sta temp + 1
    phy
    lda temp
    beq terreno_celda
    ; Por variable: lo que vino en el opcode son dos ranuras, y se leen ahora
    ; —es el `ValueOrVariable` de `CommandStoreTerrainID`—.
    lda celda_x
    jsr var_leer                ; vuelve con M en dieciséis
.a16
    sta celda_x
    sep #$20
.a8
    lda celda_y
    jsr var_leer
.a16
    sta celda_y
    sep #$20
.a8
terreno_celda:
    rep #$20
.a16
    lda celda_x                 ; `IsValid`: fuera del mapa contesta el del
    bmi terreno_afuera          ; primer tile, no el de la celda de al lado
    cmp mapa_ancho
    bcs terreno_afuera
    lda celda_y
    bmi terreno_afuera
    cmp mapa_alto
    bcs terreno_afuera
    sep #$20
.a8
    ldx mapa_ofs
    lda f:mapa_tabla + M_TERRENO_PLANO, x
    bne terreno_puesto          ; un solo terreno en todo el mapa
    jsr ptr_de_celda
    rep #$20
.a16
    lda [celdas_ptr]            ; qué bloque es la celda, ya sustituido
    jsr celda_sustituida
    sta temp + 2
    ; La tabla vive fuera del banco 0, así que se lee con un puntero de 24
    ; bits, y el único que hay libre acá es `celdas_ptr` —que ya se usó y es
    ; de todos modos temporario: cada quien lo reposiciona antes de leer—.
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO + 2, x
    sta celdas_ptr + 2
    ldy temp + 2
    lda [celdas_ptr], y
    bra terreno_puesto
terreno_afuera:
    sep #$20
.a8
    ldx mapa_ofs
    lda f:mapa_tabla + M_TERRENO_FUERA, x
terreno_puesto:
    sta temp + 2                ; de acá lo saca `var_escribir`
    stz temp + 3
    lda temp + 1
    jsr var_escribir            ; con su refresco, si la ranura lo pide
    ply
    jmp otro

; `KeyInputProc`: qué tecla apretó el jugador, guardada en una variable. Ver
; OP_KEY en eventos.py, que es donde está el porqué de que la forma que
; espera se emita dos veces.
;
; La que **espera** y no encuentra nada rebobina su propio cursor a este mismo
; opcode y devuelve el control: el cuadro que viene se la vuelve a ejecutar. Es
; lo mismo que hace la referencia devolviendo `(i, 0, None)`, y es lo que evita
; tener que guardar "estoy esperando" en algún lado —el intérprete de un evento
; paralelo son siete bytes y no le sobra ninguno—.
op_key:
.a8
.i16
    lda [cod_ptr], y            ; la ranura de la variable
    iny
    sta temp
    lda [cod_ptr], y            ; las banderas
    iny
    sta temp + 1
    and #TECLA_ARRANCA
    beq tecla_mirar
    ; La primera de las dos: la variable en cero y el control de vuelta sin
    ; mirar nada. Es el `Input::ResetTriggerKeys()` de RPG_RT: el flanco se
    ; calcula contra el pad del cuadro anterior, así que dejar pasar un cuadro
    ; es perderlo **para este intérprete**.
    ;
    ; Para el resto del cuadro no alcanzaba, y por eso se pisan los dos
    ; "anteriores" con el pad de ahora: easyrpg dice que el reset también
    ; impide "player actions for this frame such as summoning the menu or
    ; triggering events" (`game_interpreter.cpp:3403-3408`). Un paralelo corre
    ; antes que el héroe, así que sin esto la A con la que el motor de las
    ; piedras del mapa 11 prepara una le hablaba además a la reja que el héroe
    ; tenía enfrente. Lo cobra `test_con_a_y_una_direccion_la_piedra_sale_
    ; volando`.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz temp + 2
    stz temp + 3
    lda temp
    jsr var_escribir            ; con su refresco, si la ranura lo pide
    sty ev_cur
    rts
tecla_mirar:
    ; La que espera no mira el pad mientras haya un mensaje o una elección en
    ; pantalla, **de quien sea**: es el `if (Game_Message::IsMessageActive())
    ; break;` de `Game_Interpreter::Update`, easyrpg `game_interpreter.cpp:
    ; 470-473`. Importa en los paralelos, que siguen corriendo con el mensaje
    ; de otro abierto: sin esto, el A que cierra el mensaje de la PC rota del
    ; mapa 11 lo leía también el motor de las piedras, y se perdía una. Lo
    ; cobra `test_la_a_que_cierra_el_mensaje_no_saca_una_piedra`.
    lda temp + 1
    and #TECLA_ESPERA
    beq tecla_leer
    lda msg_abierto
    ora msg_estado              ; también mientras se compone
    ora eleg_activo
    bne tecla_rebobinar
tecla_leer:
    phy
    jsr tecla_valor
    ply
    sta temp + 2                ; el valor, que es de donde lo saca var_escribir
    stz temp + 3
    lda temp + 1
    and #TECLA_ESPERA
    beq tecla_guardar           ; sin espera se guarda lo que haya, cero incluido
    lda temp + 2
    bne tecla_guardar
tecla_rebobinar:
    dey                         ; todavía nada: el cursor vuelve a este opcode
    dey
    dey
    sty ev_cur
    rts
tecla_guardar:
    lda temp
    jsr var_escribir            ; `SetNeedRefreshForVarChange`, como ControlVars:
    jmp otro                    ; lo decide la ranura. Ver `var_escribir`

op_delay:
    ; Y acá se devuelve el control. Antes se salteaba, y el comentario decía
    ; que no había cuadros que dejar pasar porque esto corría con la pantalla
    ; apagada mientras se cargaba el mapa. Eso dejó de ser cierto: el intérprete
    ; corre desde el lazo principal, con la pantalla encendida, y una espera de
    ; RM2k es tiempo que el jugador ve pasar.
    rep #$20
.a16
    lda [cod_ptr], y            ; cuántos cuadros, de dieciséis bits
    sta ev_esperando
    sep #$20
.a8
    iny
    iny
    sty ev_cur
    rts

; `PanScreen`, en sus dos operaciones: correr la cámara sin el héroe y
; devolverla. El desplazamiento viene con signo y en 1/16 de pixel, y el paso
; por cuadro ya resuelto; lo que se cuenta acá son los cuadros que la página
; espera, que salen de **lo que falta** después de mover el destino y no de lo
; que este comando pidió. Ver `GetPanWait`.
op_pan:
    lda [cod_ptr], y            ; la operación
    iny
    cmp #PAN_VOLVER
    bne pan_correr
    rep #$20
.a16
    stz pan_dest_x              ; volver es ir al cero
    stz pan_dest_y
    sep #$20
.a8
    bra pan_saltear_desp
pan_correr:
    rep #$20
.a16
    lda [cod_ptr], y            ; el desplazamiento en x, con signo
    clc
    adc pan_dest_x
    sta pan_dest_x
    iny
    iny
    lda [cod_ptr], y            ; y en y
    clc
    adc pan_dest_y
    sta pan_dest_y
    sep #$20
.a8
    iny                         ; los dos de la y
    iny
    bra pan_leer_paso
pan_saltear_desp:
    iny                         ; los cuatro bytes del desplazamiento
    iny
    iny
    iny
pan_leer_paso:
    lda [cod_ptr], y            ; el paso por cuadro
    iny
    rep #$20
.a16
    and #$00FF
    sta pan_paso
    sep #$20
.a8
    lda [cod_ptr], y            ; si la página espera
    iny
    beq pan_sin_espera
    jsr pan_cuadros
    rep #$20
.a16
    sta ev_esperando
    ora #$0000                  ; `sta` no toca las banderas
    sep #$20
.a8
    ; Cero cuadros —la cámara ya estaba donde va— y la página **sigue en este
    ; mismo cuadro**: `CommandPanScreen` pone `wait_time = GetPanWait()` y
    ; devuelve true, y el lazo del intérprete sólo se detiene si `wait_time`
    ; es mayor que cero. Acá se cortaba el cuadro igual, y la puerta EV0009 del
    ; mapa 8 —un "volver" con espera y después el Teleport— llegaba al mapa 9
    ; un tick después que la referencia: el auto de Lashe City 33,36 iba 4 px
    ; atrás, medido el 2026-09-10. Lo cobra `snes-pan 6 "3 0 0 4 1"`.
    beq pan_sin_espera
    sty ev_cur
    rts
pan_sin_espera:
    jmp otro

op_tint:
    lda [cod_ptr], y
    sta tinte_r
    iny
    lda [cod_ptr], y
    sta tinte_g
    iny
    lda [cod_ptr], y
    sta tinte_b
    iny
    lda [cod_ptr], y
    sta tinte_s
    iny
    ; El tinte no se aplica acá: se pide, y lo hace `flush_video` en el vblank
    ; siguiente. `aplicar_tinte` sube tres paletas a CGRAM por DMA, y con el PPU
    ; dibujando esas escrituras se pierden. Mientras el intérprete corría adentro
    ; de `cargar_mapa`, con la pantalla apagada, no hacía falta; al mudarlo al
    ; lazo principal pasó a ejecutarse con la pantalla encendida y el tinte
    ; entraba a medias —quedaban teñidos la capa de encima y un sprite, y el
    ; resto no, según qué escritura pescara el vblank—.
    lda #1
    sta tinte_pendiente
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

op_teleport:
    rep #$20
.a16
    lda [cod_ptr], y            ; el mapa, en un word desde que el formato
    sta salto_mapa              ; tiene que poder nombrar los 328 del juego
    iny
    iny
    lda [cod_ptr], y
    sta salto_x
    iny
    iny
    lda [cod_ptr], y
    sta salto_y
    sep #$20
.a8
    lda #1
    sta salto_hay
    iny                         ; los dos bytes de la Y, que se leyeron sin
    iny                         ; avanzar el cursor
    ; Y corta el cuadro, que es exactamente lo que hace
    ; `Game_Interpreter_Map::CommandTeleport` en easyrpg-player: reserva el
    ; salto, hace `index++` y devuelve false. El mapa se carga entre este cuadro
    ; y el siguiente, y la página retoma en el comando de después con el cursor
    ; guardado acá. Ninguna página del juego que hoy compile tiene comandos
    ; después de un teletransporte —medido sobre el juego entero—; la
    ; cinemática de apertura tiene once.
    sty ev_cur
    rts
.endproc

; Una pelea de punta a punta, con la tropa ya puesta en `BA_TROPA`: guardar el
; tema del mapa, cargar el audio de la pelea, pelearla y volver al mapa.
;
; Está separada de `op_battle` desde que hay encuentros al azar, que la
; arrancan **sin bytecode**: allá no hay cursor que guardar ni manejadores a
; los que saltar. Lo de adentro no cambió de lugar.
.proc pelea_arrancar
.a8
.i16
    ; El tema del mapa se guarda y vuelve al terminar, que es el
    ; `before_battle_music` de RM2k —`Scene_Battle` lo anota al construirse y
    ; `Game_Map` lo repone al volver—. $FF quiere decir "no sonaba nada", y es
    ; un caso real: los primeros mapas del juego no traen música.
    ; **Con el banco de datos en el 0**, que acá todavía es el del bytecode:
    ; `music_apagada` y `tema_actual` son absolutos de la BSS y sin esto se
    ; leerían del banco del cartucho donde está la página. Es la misma trampa
    ; que los puentes `ba_t_*` del otro lado, y costó exactamente lo mismo.
    phb
    phk
    plb
    ; **El MSU-1 primero.** Con una pista de CD sonando, `music_start` deja el
    ; SPC700 callado a propósito —`music_apagada` en 1— y mirar sólo eso
    ; anotaba $FF: al terminar la pelea `batalla_bgm` callaba la música del
    ; mapa en vez de reponerla. Es la misma pregunta que `mapa_tema_callar`, y
    ; se contesta igual.
    lda f:MSU_SUENA
    bne sonaba_antes
    lda music_apagada
    bne callado_antes
sonaba_antes:
    lda tema_actual
    bra anotado
callado_antes:
    lda #$FF
anotado:
    sta f:BAT_LARGO + BA_TEMA_ANT
    ; El paquete de audio de la pelea: su tema y sus efectos. Va aparte del
    ; paquete del mapa y no adentro, y está medido: el tema de batalla son 18
    ; muestras y 51.480 B de los 64.512 de ARAM, o sea que metiéndolo en el
    ; paquete del mapa 2 los 24 efectos de ese mapa se caían casi enteros.
    ; Se calla antes de rearmar, como hace `tema_asegurar`: `paquete_cargar`
    ; deja quietas las muestras del tema que suena, y las del mapa no tienen
    ; por qué ocupar lugar adentro de la pelea.
    ldx #BA_PAQUETE
    jsr batalla_audio_cargar
    lda #BA_TEMA
    jsr batalla_bgm
    plb
    ; El banco de datos, en $7E: es lo que le deja al código de la pelea usar
    ; direccionamiento absoluto sobre su estado sin perder la RAM baja, que en
    ; ese banco está en las mismas direcciones. Ver el comentario de
    ; `FAR_BATALLA`.
    phb
    lda #$7E
    pha
    plb
    jsl f:batalla_correr
    plb
    ; Los flancos que cerraron la pelea son de ella, como en la tienda y en el
    ; menú: si no, el A con el que se cerró el último mensaje abriría lo que
    ; haya en el mapa.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    phb
    phk
    plb                         ; el banco 0, por lo mismo que al entrar
    ldx mapa_actual             ; y el audio del mapa vuelve al SPC700
    jsr batalla_audio_cargar
    lda f:BAT_LARGO + BA_TEMA_ANT
    jsr batalla_bgm             ; el tema del mapa, o el silencio que había
    plb
    jsr volver_de_batalla
    rts
.endproc

