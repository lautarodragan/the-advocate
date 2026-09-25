.segment "CODE"
.a8
.i16

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

