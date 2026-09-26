.segment "CODE"
.a8
.i16

; --- el intérprete: la tienda y la pelea -----------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.
;
; La pelea se arranca con `pelea_arrancar`, que está al final de
; interprete_teletransporte_y_pelea.s: estaba detrás del último manejador,
; y traerla acá es mover código, que cambia la ROM.

; `OpenShop`: tipo, juego, cuántos y la lista, de a dos bytes cada ítem. La
; tienda se abre acá adentro y, al salir, el mapa vuelve y la página sigue.
.proc op_shop
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
    jmp correr_codigo::otro

.endproc

; `EnemyEncounter`: la tropa y los tres destinos, todos de dieciséis bits. La
; pelea se juega acá adentro y, al salir, el mapa vuelve —como en la tienda— y
; la página sigue por el destino que le tocó al resultado.
.proc op_battle
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

.endproc

.proc op_battle_destination
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
    jmp correr_codigo::otro


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
    ;
    ; **Con el mapa ya en negro**: la carga tarda de medio segundo a uno y
    ; medio, y es la transición de entrada la que la tapa. Ver
    ; `fundido_de_pelea.s`.
    jsl f:pelea_fundir_entrando
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
    jsl f:pelea_fundir_saliendo ; la pelea hasta negro, que tapa la carga
    ldx mapa_actual             ; y el audio del mapa vuelve al SPC700
    jsr batalla_audio_cargar
    lda f:BAT_LARGO + BA_TEMA_ANT
    jsr batalla_bgm             ; el tema del mapa, o el silencio que había
    plb
    jsr volver_de_batalla
    phb
    phk
    plb
    jsr pelea_fundir_al_mapa    ; y el mapa desde negro, con `flush_video`
    plb
    rts
.endproc

