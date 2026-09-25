; --- la tecla de acción -----------------------------------------------------
;
; Hablarle a algo. Es lo que convierte a esto en un juego y no en una cinemática:
; de las 1599 páginas de este juego que se disparan así, 1006 ya compilan, contra
; 110 automáticas.
;
; La regla sale de `Game_Player::CheckActionEvent`: se mira la celda del héroe y
; después la de adelante. Lo que allá va antes —los eventos que se disparan al
; tocarlos— todavía no está, y el lazo de hasta tres mostradores tampoco.

; ¿Hay un evento en (celda_x, celda_y)? Devuelve su índice en A, o $FF.
.proc evento_en_celda
.a8
.i16
    ldy #$0000
    ldx #$0000
buscar:
    cpx ev_total
    beq no_hay
    rep #$20
.a16
    lda ev_pos_buf, y
    cmp celda_x
    bne siguiente
    lda ev_pos_buf + 2, y
    cmp celda_y
    bne siguiente
    sep #$20
.a8
    txa                         ; el índice cabe en un byte: EV_MAX es 128
    rts
siguiente:
.a16                            ; se llega en dieciséis, del `bne` de arriba
    tya
    clc
    adc #EV_STRIDE
    tay
    sep #$20
.a8
    inx
    bra buscar
no_hay:
    lda #$FF
    rts
.endproc

; Encola la página activa del evento `ev_buscado` si la dispara la tecla de
; acción. Devuelve A distinto de cero si encoló algo.
;
; Es la misma regla de selección que `encolar_eventos` —gana la de número más
; alto que cumpla sus condiciones— pero para un evento solo, y sin tocar el
; cursor de la cola de los automáticos.
; La página activa del evento `ev_buscado`, a `elegida`. Sin mirar el trigger:
; quien llama decide qué hacer con ella. Es la misma regla de siempre —gana la
; de número más alto cuyas condiciones se cumplen— y se resuelve **en el
; momento de usarla**, no cuando se marcó el evento, que es lo que hace
; `Game_Map::Update` al empujar el evento que estaba esperando.
.proc buscar_pagina_de_evento
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    beq sin_paginas
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz elegida_hay

recorrer:
    jsr leer_pagina
    rep #$20
.a16
    lda pg_evento
    cmp ev_buscado
    sep #$20
.a8
    bne siguiente               ; no es el evento que estamos mirando
    jsr condiciones_ok
    beq siguiente
    lda pg_trigger
    sta elegida_trigger
    lda pg_capa
    sta elegida_capa
    rep #$20
.a16
    lda pg_cod
    sta elegida
    sep #$20
.a8
    lda pg_cod + 2
    sta elegida + 2
    lda #1
    sta elegida_hay
    ; Y su giro, el +30 y el +31: ver `giro_disparar` y `giro_revisar`.
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #30
    tay
    sep #$20
.a8
    lda [pag_ptr], y
    sta f:ELEG_K
    iny
    lda [pag_ptr], y
    sta f:ELEG_POSE

siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    bne recorrer

    rts
sin_paginas:
.a16                            ; se llega en dieciséis; el `sep` lo achica
    sep #$20
.a8
    stz elegida_hay
    rts
.endproc

; El disparo por tecla de acción o por contacto: busca la página activa del
; evento y, si es del trigger que se pide y compiló, marca al evento.
.proc encolar_por_accion
.a8
.i16
    jsr buscar_pagina_de_evento
    lda elegida_hay
    beq no
    lda elegida_trigger
    cmp trigger_buscado
    bne no
    ; La regla de capa, opuesta según qué celda se mire: la de adelante sólo
    ; dispara eventos de la capa del héroe —`CheckEventTriggerThere` pide
    ; `Layers_same`— y la propia sólo los de otra capa —`CheckEventTriggerHere`
    ; pide `!= Layers_same`—. No es simetría de adorno: un evento de la capa del
    ; héroe le cierra el paso, así que nunca se podría parar encima.
    ;
    ; Sólo para la tecla de acción; el contacto tiene su regla y se resuelve al
    ; compilar.
    lda trigger_buscado
    cmp #TRIGGER_ACCION
    bne sin_capa
    lda elegida_capa
    cmp #HERO_LAYER
    beq era_del_heroe
    lda accion_propia
    beq no                      ; otra capa, pero se está mirando adelante
    bra sin_capa
era_del_heroe:
    lda accion_propia
    bne no                      ; la del héroe, pero se está mirando la propia
sin_capa:
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq no                      ; la página activa no se pudo compilar
    ldx ev_buscado
    jsr marcar_esperando
    jsr giro_disparar           ; y se da vuelta hacia el héroe, si gira
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; La celda que trae (celda_x, celda_y): si hay un evento y su página activa la
; dispara la tecla, se encola. Devuelve A distinto de cero si encoló.
.proc accion_en_celda
.a8
.i16
    jsr evento_en_celda
    cmp #$FF
    beq no
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jmp encolar_por_accion
no:
    lda #0
    rts
.endproc

; El evento de contacto de la celda donde el héroe acaba de pararse.
;
; Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`. Las puertas
; son un caso particular de esto —un teletransporte en una página de contacto— y
; se atienden antes, aparte: si hubo puerta, el mapa ya cambió y acá no queda
; nada que mirar.
; Con una página corriendo **también** se mira, y la página que dispare va a
; la cola detrás de la que está corriendo: en RM2k `UpdateMovement` no pregunta
; por el intérprete, `ScheduleForegroundExecution` deja al evento esperando y
; `Game_Map` lo arranca cuando el intérprete se desocupa. Acá había un guard
; que descartaba el contacto en ese caso, escrito para el pad —y para el pad
; sobra, porque `move_hero` no arranca un paso con una página en el frente—;
; con una ruta forzada sí pasaba: una página que manda a caminar al héroe y
; después espera terminaba con el contacto perdido. La cola es la misma que la
; de los automáticos, de a uno detrás del otro, que es lo que hace RM2k.
;
; Lo que no se modela, de ningún lado: un evento que se dispare dos veces antes
; de correr entra dos veces acá y una sola en RM2k, que lo marca con un bit.
.proc probar_contacto
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda #TRIGGER_TOCA_HEROE
    sta trigger_buscado
    jsr accion_en_celda
    ldx #TRIGGER_ACCION
    stx trigger_buscado         ; queda como lo espera la tecla de acción
    rts
.endproc

; La tecla de acción, desde el lazo principal.
.proc probar_accion
.a8
.i16
    ; Las dos celdas, en el orden de `Game_Player::CheckActionEvent`: primero la
    ; propia —`CheckEventTriggerHere`, que pide una capa distinta de la del
    ; héroe— y después la de adelante —`CheckEventTriggerThere`, que pide la
    ; suya—. La propia estuvo sin hacer hasta el 2026-09-07 y taro la encontró
    ; jugando: la puerta que sale del pad de Talan es `TalDoorTop`, de acción y
    ; capa 2, y se abre parándose encima.
    lda #TRIGGER_ACCION
    sta trigger_buscado
    lda #1
    sta accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    jsr accion_en_celda
    beq mirar_adelante
    rts                         ; encoló el de abajo del héroe
mirar_adelante:
    stz accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda hero_dir
    cmp #DIR_UP
    bne no_arriba
    rep #$20
.a16
    dec celda_y
    sep #$20
.a8
    bra mirar
no_arriba:
    cmp #DIR_DOWN
    bne no_abajo
    rep #$20
.a16
    inc celda_y
    sep #$20
.a8
    bra mirar
no_abajo:
    cmp #DIR_LEFT
    bne no_izquierda
    rep #$20
.a16
    dec celda_x
    sep #$20
.a8
    bra mirar
no_izquierda:
    rep #$20
.a16
    inc celda_x
    sep #$20
.a8
mirar:
    jmp accion_en_celda
.endproc

