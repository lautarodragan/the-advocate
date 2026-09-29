.segment "CODE"

; --- el intérprete de eventos ----------------------------------------------
;
; RM2k se queda con la página de número más alto cuyas condiciones se cumplen
; todas. Las páginas vienen agrupadas por evento y en orden, así que alcanza una
; sola pasada: se recuerda la última que cumplió, y al cambiar de evento se
; ejecuta la que haya quedado.
;
; Sólo se corren las automáticas. Las de contacto ya las cubren las puertas, y
; las de botón necesitan que haya un botón que apretar.

; Los campos de la página que está en pag_ofs, a variables.
.proc leer_pagina
.a8
.i16
    ldy pag_ofs
    rep #$20
.a16
    lda [pag_ptr], y            ; +0  a qué evento pertenece
    sta pg_evento
    sep #$20
.a8
    iny
    iny
    iny
    lda [pag_ptr], y            ; +3  qué la dispara. De a un byte: leerlo de a
    sta pg_trigger              ;     dos se llevaría puesto el switch de al lado
    iny
    rep #$20
.a16
    lda [pag_ptr], y            ; +4  el switch que pide, o 0
    sta pg_sa
    iny
    iny
    lda [pag_ptr], y            ; +6  el segundo, o 0
    sta pg_sb
    iny
    iny
    lda [pag_ptr], y            ; +8  su código: los 16 bits bajos
    sta pg_cod
    sep #$20
.a8
    iny
    iny
    lda [pag_ptr], y            ; +10 y su banco
    sta pg_cod + 2
    iny
    lda [pag_ptr], y            ; +11 el actor que pide en el grupo, o 0
    sta pg_actor
    iny
    lda [pag_ptr], y            ; +12 su capa
    sta pg_capa
    iny
    lda [pag_ptr], y            ; +13 las banderas de la ruta propia
    sta pg_flags
    iny
    lda [pag_ptr], y            ; +14 su frecuencia
    sta pg_frec
    iny
    lda [pag_ptr], y            ; +15 la velocidad de la página
    sta pg_vel
    iny
    lda [pag_ptr], y            ; +16 las órdenes de la ruta propia
    sta pg_ruta
    iny
    lda [pag_ptr], y
    sta pg_ruta + 1
    iny
    lda [pag_ptr], y
    sta pg_ruta + 2
    iny
    lda [pag_ptr], y            ; +19 cuántas
    sta pg_ruta_n
    iny
    lda [pag_ptr], y            ; +20 lo que dibuja la página, para los eventos
    sta pg_tile                 ;     que cambian de gráfico: el tile,
    iny
    lda [pag_ptr], y            ; +21 los atributos con paleta y prioridad,
    sta pg_attr
    iny
    lda [pag_ptr], y            ; +22 la pose, con el bit 7 si hay gráfico,
    sta pg_pose
    iny
    lda [pag_ptr], y            ; +23 y los bits de paso de su tile, o $FF
    sta pg_pasa
    rts
.endproc

; La página activa de cada evento y, con ella, la ruta propia que le toca. Es
; `Game_Map::Refresh` con `Game_Event::SetupFromPage`: al cargar el mapa y cada
; vez que un switch o el grupo cambian. Un evento cuya página activa es la
; misma de antes no se toca, y su ruta sigue por donde iba; uno cuya página
; cambió carga la ruta de la nueva desde el principio, con la espera del giro
; antes de la primera orden; y uno cuya página nueva no tiene ruta se queda sin
; órdenes. La velocidad de la página queda en `vel_por_ev` para las rutas
; forzadas.
;
; Son dos pasadas y no un lazo adentro del otro: la tabla de páginas se recorre
; una sola vez anotando la ganadora de cada evento, y después se mira evento
; por evento. Con eventos por páginas costaba más de un cuadro, y un cuadro
; perdido en un switch atrasa un cuadro todo lo que viene después.
; `Game_Map::Refresh` entero: elegir las páginas activas y aplicarlas.
.proc rutas_de_pagina
.a8
.i16
    jsr elegir_paginas
    jmp aplicar_paginas
.endproc

; Como `elegir_paginas`, pero mirando **sólo** los eventos con automáticas.
;
; Es lo que corre el refresco de adentro del lazo de comandos, y es lo único
; que ese refresco necesita hacer en el acto: lo que el comando siguiente puede
; llegar a mirar es qué evento tiene una automática activa. En el mapa 2 son
; cuatro páginas de sesenta y tres, contra las veintitrés que mira la completa.
; La completa corre igual, al principio del cuadro que viene.
.proc elegir_automaticas
.a8
.i16
    lda #1
    sta solo_auto
    jmp elegir_con_filtro
.endproc

; La primera mitad: qué página queda activa en cada evento, y de paso el
; `FLAG_AUTO` de cada uno.
.proc elegir_paginas
.a8
.i16
    stz solo_auto
    jmp elegir_con_filtro
.endproc

; El cuerpo de las dos, con `solo_auto` diciendo cuál es.
.proc elegir_con_filtro
.a8
.i16
    ; El `FLAG_AUTO` no se apaga con un lazo aparte sino en la primera página
    ; de cada evento, más abajo: ciento veinte vueltas en cada refresco
    ; costaban el cuadro entero cuando el refresco caía sobre algo caro.
    lda solo_auto
    beq vaciar_todo
    rep #$20
.a16
    lda #$FFFF
    sta rp_ev_ant
    bra sin_vaciar              ; la pasada corta no pisa lo de las rutas
.a8
vaciar_todo:
    rep #$20
.a16
    ldx #$0000
    lda ev_total
    asl a
    sta rp_ev_ant               ; el tope en bytes, prestado un momento
vaciar:
    lda #$FFFF
    sta eleg_por_ev, x
    inx
    inx
    cpx rp_ev_ant
    bne vaciar
    lda #$FFFF
    sta rp_ev_ant               ; y ahora sí, "ningún evento visto todavía"
.a16
sin_vaciar:
    ldx mapa_ofs
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    bne hay_paginas
    jmp sin_paginas             ; queda lejos para un salto corto
hay_paginas:
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
recorrer:
    ; Sólo las páginas de los eventos que tienen alguna con ruta propia, o
    ; gráfico que sigue a la página, o alguna automática: los bits 5, 6 y 7 de
    ; +13 lo dicen, y se lee ese byte solo. Con todas las páginas enteras esto
    ; costaba más de un cuadro, y el cuadro se perdía.
    ;
    ; Las tres cosas se resuelven en **una sola** recorrida a propósito. Con la
    ; de las automáticas aparte —que es como nació— el refresco hacía dos
    ; vueltas y volvía a perder el cuadro: se veía como el tinte de
    ; `snes-pan` llegando uno tarde.
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #13
    tay
    sep #$20
.a8
    ; Con A y no con un `ldx`: X está en 16 bits y se llevaría también
    ; `auto_n`, el byte de al lado, así que con una automática corriendo la
    ; pasada completa filtraría como la corta.
    lda solo_auto
    beq filtro_completo
    lda [pag_ptr], y
    and #$80                    ; la pasada corta: sólo las automáticas
    bra con_filtro
filtro_completo:
    lda [pag_ptr], y
    and #$E0
con_filtro:
    bne mirar_pagina
    jmp siguiente               ; la recorrida creció y ya no entra en un beq
mirar_pagina:
    jsr leer_pagina
    ; La primera página de un evento con automáticas le apaga el `FLAG_AUTO`:
    ; lo vuelve a prender, más abajo, la última de sus páginas que cumpla. Las
    ; páginas de un evento vienen juntas, así que alcanza con mirar si cambió.
    lda pg_flags
    and #$80
    beq no_es_auto
    rep #$20
.a16
    lda pg_evento
    cmp rp_ev_ant
    beq mismo_ev16
    sta rp_ev_ant
    tax
    sep #$20
.a8
    cpx #EV_MAX
    bcs no_es_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq ya_apagada
    dec auto_n
ya_apagada:
    ; Los **dos** bits, y la última página que cumpla los vuelve a poner. El
    ; de espera también: si ninguna página del evento cumple, se queda sin
    ; página activa y la marca tiene que irse, que es el
    ; `ClearWaitingForegroundExecution` que `RefreshPage` hace cuando no
    ; encuentra ninguna. Dejándola puesta, la página que acababa de terminar
    ; volvía a arrancar: en la cinemática de apertura eso reiniciaba la escena
    ; entera en el cuadro 692.
    jsr desmarcar_esperando     ; el de espera, con su cuenta
    stz ev_flags, x             ; y el de automática, que la cuenta ya bajó
    bra no_es_auto
.a16
mismo_ev16:
    sep #$20
.a8
no_es_auto:
    jsr condiciones_ok
    beq no_cumple
    ; Cumple, así que por ahora es la activa de su evento. Si el evento tiene
    ; automáticas, acá se decide si la activa lo es: escribir en cada página
    ; que cumple deja al final lo que diga la última, que es la que gana.
    lda pg_flags
    and #$80
    beq sin_auto
    ldx pg_evento
    cpx #EV_MAX
    bcs sin_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq sigue_apagada
    dec auto_n
sigue_apagada:
    lda ev_flags, x
    and #FLAG_ESPERA            ; se apaga, y abajo se vuelve a prender si toca
    sta ev_flags, x
    lda pg_trigger
    cmp #TRIGGER_AUTOMATICO
    bne no_gana_una_auto
    lda pg_cod
    ora pg_cod + 1
    ora pg_cod + 2
    beq no_gana_una_auto        ; no compiló: no hay nada que arrancar
    lda ev_flags, x
    ora #FLAG_AUTO
    sta ev_flags, x
    inc auto_n
    jsr marcar_esperando        ; sigue siendo automática: la marca vuelve
    bra sin_auto
no_gana_una_auto:
    ; La que gana no es automática, así que el evento **deja** de esperar. Se
    ; escribe en cada página que cumple y gana la última, que es la activa;
    ; marcando y no desmarcando, la página 0 de un evento dejaba la marca
    ; puesta aunque ganara la 1. Es el `ClearWaitingForegroundExecution` que
    ; `Game_Event::RefreshPage` hace al cambiar de página.
    jsr desmarcar_esperando
sin_auto:
    ; La página activa se anota para los tres casos, no sólo para los de ruta o
    ; gráfico: `arrancar_esperando` la lee de acá en vez de volver a recorrer
    ; las páginas del mapa. En el mapa 2 eso son sesenta y tres páginas por
    ; cada página que arranca, y se perdía el cuadro. La segunda pasada, que
    ; es la que toca rutas y gráficos, saltea a los que no tienen esos bits.
    rep #$20
.a16
    lda pg_evento
    asl a
    tax
    lda pag_ofs
    sta eleg_por_ev, x          ; gana la última que cumple
    sep #$20
.a8
    bra siguiente
no_cumple:
    lda pg_flags
    and #$60
    bne con_rutas
    jmp siguiente               ; sólo automáticas: ya quedó apagado arriba
con_rutas:
    ; Un evento con rutas y sin página que cumpla todavía: $FFFE, para que la
    ; segunda pasada lo distinga de los que no tienen rutas.
    rep #$20
.a16
    lda pg_evento
    asl a
    tax
    lda eleg_por_ev, x
    cmp #$FFFF
    bne ya_tiene
    ; Sin página que cumpla, por ahora: $FFFE, o $FFFD si el gráfico sigue a
    ; la página, que es el que hay que esconder.
    lda #$FFFE
    sta eleg_por_ev, x
    sep #$20
.a8
    lda pg_flags
    and #$20
    beq ya_tiene8
    rep #$20
.a16
    lda #$FFFD
    sta eleg_por_ev, x
    sep #$20
.a8
ya_tiene8:
    rep #$20
.a16
ya_tiene:
    sep #$20
.a8
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
    beq listo_eligiendo
    jmp recorrer                ; la recorrida creció y ya no entra en un bcc
listo_eligiendo:
    rts
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; La segunda mitad: cada evento con la ruta y el gráfico de su página activa.
; Recorre los eventos del mapa recargando filas de OAM y ranuras de ruta, así
; que es la cara: hacerla en medio de un cuadro costaba el cuadro entero en el
; mapa 2. Por eso el refresco a mitad de comando la deja para el principio del
; cuadro que viene, donde no cambia nada: lo que toca no se ve hasta que se
; dibuje.
.proc aplicar_paginas
.a8
.i16
    ; El giro primero, con las páginas nuevas ya elegidas y antes de que se
    ; reescriban las filas: ver `giro_revisar` y `giro_reponer`.
    jsr giro_revisar
    ; El puntero a las páginas se rearma acá y no se hereda de `elegir_paginas`:
    ; entre una y otra puede haber pasado un cuadro entero.
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz par_n                   ; la lista de paralelos se rehace entera
    stz rp_ev
    stz rp_ev + 1
cada_evento:
    rep #$20
.a16
    lda rp_ev
    cmp ev_total
    bcc :+
    jmp fin16                   ; lejos para un salto corto
:
    asl a
    tax
    lda eleg_por_ev, x
    cmp #$FFFF
    bne :+
    jmp proximo                 ; sin rutas propias: nada que mirar
:
    cmp #$FFFE
    bne :+
    jmp sin_activa16            ; con rutas, y ninguna página que cumpla
:
    cmp #$FFFD
    bne :+
    jmp esconder16              ; con gráfico de página, y ninguna: se esconde
:
    sta pag_ofs
    sep #$20
.a8
    jsr leer_pagina
    ; Si la que ganó es paralela, el evento entra en la lista de los que
    ; `paralelos_tick` corre. Se arma acá y no en cada cuadro porque cuál es la
    ; página activa sólo cambia en un refresco, y recorrer los ciento veinte
    ; eventos por cuadro es justo lo que este refresco existe para no hacer.
    lda pg_trigger
    cmp #TRIGGER_PARALELO
    bne no_es_paralela
    lda pg_cod
    ora pg_cod + 1
    ora pg_cod + 2
    beq no_es_paralela          ; no compiló: no hay nada que correr
    jsr anotar_paralelo
no_es_paralela:
    lda pg_flags
    and #$60
    bne con_ruta_o_grafico
    jmp proximo                 ; sólo automáticas: la anotación es para otro
con_ruta_o_grafico:
    jsr grafico_de_pagina       ; lo que la página dibuja, a la fila del NPC
    lda rp_ev
    jsr ranura_del_evento       ; X = su ranura, o $FFFF
    lda pg_flags
    and #$01
    beq sin_ruta
    cpx #$FFFF
    beq nueva
    rep #$20
.a16
    lda ruta_ev + 20, x
    cmp pag_ofs
    sep #$20
.a8
    bne :+
    jmp proximo                 ; la misma página de antes: sigue por donde iba
:
    bra cargar
nueva:
    lda rp_ev
    jsr giro_por_ruta
    jsr ranura_libre
    cpx #$FFFF
    bne :+
    jmp proximo                 ; no hay lugar: se queda quieto
:
    lda rp_ev
    sta ruta_ev + 0, x
    jsl f:ranura_anotar + RAPIDO
    stz ruta_ev + 6, x
    stz ruta_ev + 7, x
    lda #RUTA_EV_SIN_MIRAR
    sta ruta_ev + 8, x
    stz ruta_ev + 12, x
    stz ruta_ev + 13, x
    lda #1
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
    stz ruta_ev + 22, x
    stz ruta_ev + 23, x
cargar:
    phx
    lda rp_ev
    jsr giro_por_ruta           ; con ruta, adónde mira lo decide ella
    plx
    jsr cargar_pagina_en_ranura
    jmp proximo
sin_ruta:
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr quitar_pagina_de_ranura
    jmp proximo
.a16
esconder16:
    sep #$20
.a8
    lda rp_ev
    jsr esconder_npc
    jmp proximo
.a16
sin_activa16:
    sep #$20
.a8
    lda rp_ev
    jsr ranura_del_evento
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr quitar_pagina_de_ranura
proximo:
    rep #$20
.a16
    inc rp_ev
    sep #$20
.a8
    jmp cada_evento
.a16
fin16:
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; Lo que en `Game_Map::Update` corre **antes** del jugador: el refresco
; pendiente y `UpdateMapEvents` —`game_map.cpp:1259` y `:1274`, contra el
; `game_player->Update()` de `:1288`—.
;
; Está partido de `eventos_tick` justamente por eso: el primer plano cae del
; otro lado del héroe, y así lo que un paso encola se atiende en el mismo
; cuadro. Ver el lazo principal.
.proc eventos_de_mapa
.a8
.i16
    ; El refresco pendiente, antes de todo: es cuando `Game_Map::Update` mira
    ; `GetNeedRefresh`.
    lda refresco
    ora refresco_cuadro         ; o uno de adentro del lazo de comandos, que
    beq sin_refresco            ; hizo la pasada corta y dejó ésta debiendo
    stz refresco
    stz refresco_cuadro
    jsr rutas_de_pagina         ; que además rehace el `FLAG_AUTO` de cada
                                ; evento: la página activa cambió
sin_refresco:
    ; `Game_Event::CheckEventAutostart`, que cuelga de
    ; `Game_Event::UpdateNextMovementAction` —`game_event.cpp:409`— y por eso
    ; corre acá adentro: todo evento con una automática activa queda esperando,
    ; una vez por cuadro y **antes** del intérprete. Marcarlo más tarde —al
    ; terminar una página— le adelantaba un cuadro a las que se activan en
    ; medio de otra.
    ;
    ; `auto_n` está para que el lazo de ciento veinte no corra cuando no hay
    ; ninguna, que es casi siempre: corriéndolo igual se perdía el cuadro justo
    ; donde caía algo caro, como el tinte de `snes-pan`.
    lda auto_n
    beq sin_automaticas
    jsr esperar_automaticas
sin_automaticas:
    ; Los paralelos, que es la otra mitad de `UpdateMapEvents`
    ; —`game_event.cpp:590`—: corren antes del héroe, antes del mensaje y antes
    ; del primer plano. O sea que un evento paralelo sigue corriendo con un
    ; cuadro de texto abierto y con otra página en curso, que es justo para lo
    ; que existe.
    jmp paralelos_tick
.endproc

; Un cuadro del intérprete de primer plano, desde el lazo principal:
; `Game_Map::UpdateForegroundEvents` —`game_map.cpp:1310`— con el
; `UpdateMessage` de `:1297` pegado adelante.
;
; Acá estaba el cambio de fondo: antes `cargar_mapa` corría todas las páginas de
; una, con la pantalla apagada, y volvía con todo hecho. El tiempo quedaba
; colapsado —las esperas se salteaban, y lo que pasaba antes de un
; teletransporte no se veía nunca— y por eso nada de eso se podía verificar.
;
; Un teletransporte se atiende acá y no adentro del intérprete: llamar a
; `cargar_mapa` desde ahí sería recursión, y dos mapas que se apuntan entre sí
; la harían infinita. El tope de saltos sigue por la misma razón.
.proc eventos_tick
.a8
.i16
    rep #$20
.a16
    lda ev_esperando
    beq sin_espera
    dec a
    sta ev_esperando
    sep #$20
.a8
    rts
sin_espera:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8

    ; Con un mensaje en pantalla la página queda bloqueada, que es lo que hace
    ; `Game_Message`. Todo lo demás sigue: la ruta forzada del héroe camina y la
    ; cámara lo sigue, porque en `game_player.cpp` de easyrpg `UpdateMoveRoute`
    ; corre **antes** del guard de `IsMessageActive`. En este juego hay 186
    ; páginas donde eso pasa, y la primera está en el mapa 1.
    ; Una elección abierta manda sobre el mensaje: la ventana es la misma pero
    ; A no la cierra, la resuelve.
    lda eleg_activo
    beq sin_eleccion
    jsr eleccion_tick
    bne sin_mensaje             ; eligió: la página sigue en este mismo cuadro
    rts
sin_eleccion:
    lda msg_abierto
    ora msg_estado              ; también mientras se está componiendo
    beq sin_mensaje
    ; La pausa del `\|`, si el cuadro trae alguna. Se cuenta **desde que la
    ; página pidió el mensaje** y no desde que la ventana terminó de
    ; componerse: así no depende de lo que tarde la composición, que va de
    ; nueve a diecinueve cuadros según el texto. Con una pausa de 61 la
    ; composición termina mucho antes, así que en pantalla se ve lo mismo.
    ; **A no la saltea**: en `Window_Message::Update` el `if (wait_count > 0)`
    ; va antes de `WaitForInput()`, así que mientras la pausa corre el botón no
    ; se mira. Por eso va arriba de todo y no después del flanco.
    rep #$20
.a16
    lda f:FAR_MSG_PAUSA
    beq sin_pausa
    dec a
    sta f:FAR_MSG_PAUSA
    sep #$20
.a8
    rts
.a16
sin_pausa:
    sep #$20
.a8
    lda f:FAR_MSG_AUTO
    beq espera_boton
    ; El `\^`: el cuadro se cierra solo, sin que nadie apriete nada. Se apaga
    ; también el compositor, y no es teórico: un cuadro con `\^` y ninguna
    ; pausa se cierra antes de que termine de componerse, y sin esto
    ; `flush_video` prendería la ventana de un mensaje ya cerrado.
    lda #0
    sta f:FAR_MSG_AUTO
    stz msg_estado
    stz msg_subir
    stz msg_abierto
    bra sigue
espera_boton:
    lda msg_abierto
    beq no_avanza               ; todavía no terminó de componerse
    lda pad_a
    beq no_avanza               ; nadie apretó: el mensaje se queda
    lda pad_a_ant
    bne no_avanza               ; ya lo tenía apretado: no es un flanco
    stz msg_abierto             ; y con eso `flush_video` apaga el HDMA: cerrar
                                ; la ventana no escribe un solo byte de VRAM
    ; Y el flanco queda consumido, como el de B en la elección. Si el mensaje
    ; era de un paralelo no hay página que siga, así que este mismo cuadro cae
    ; en `probar_accion` con la A todavía "recién apretada" y le hablaba al
    ; evento que el héroe tuviera enfrente. En RM2k el mensaje sigue activo
    ; unos ocho cuadros más, mientras se anima el cierre (easyrpg
    ; `window_message.cpp:379-403`), y con un mensaje activo el héroe no busca
    ; eventos (`game_player.cpp:297`). Lo cobra `test_la_a_que_cierra_el_
    ; mensaje_no_le_habla_al_de_enfrente`.
    lda pad_a
    sta pad_a_ant
sigue:
    ; Y la página sigue **en este mismo cuadro**, cayendo en el `jsr
    ; correr_codigo` de siempre. Cerrar acá y retomar el cuadro siguiente
    ; le costaría un cuadro a cada página que cierra un mensaje.
    bra sin_mensaje
no_avanza:
    rts
sin_mensaje:

    lda ev_activo
    bne corriendo
    ; No hay página a medio correr: se toma la del primer evento que espere.
    lda esperando_n
    bne hay_esperando

    ; Nada corriendo y nada esperando: el jugador tiene el control, así que la
    ; cadena de teletransportes terminó y el presupuesto se repone.
    ;
    ; Antes lo reponía sólo `cargar_mapa`, y a esa altura el único que la
    ; llamaba era una **puerta**: un comando `Teleport` carga el mapa por
    ; `cargar_mapa_sin_eventos`, que no la toca. Así que ocho teletransportes
    ; gastaban el presupuesto para toda la partida y del noveno en adelante el
    ; `beq nada` de abajo los descartaba **en silencio**. La apertura entera son
    ; teletransportes encadenados y casi no tiene puertas: para cuando el
    ; despachante del mapa 4 quería mandar al pad de Talan ya no quedaba
    ; ninguno, el salto se perdía, y como su página es automática y su switch
    ; sigue prendido volvía a arrancar sola para siempre. taro lo vio el
    ; 2026-09-07 como un mapa vacío del que no se podía salir, con la música
    ; fundiéndose y volviendo a empezar en ciclo; el volcado de la RAM decía
    ; `mapa_actual` = 4 con el evento 1 corriendo.
    lda #SALTOS_MAX
    sta saltos_restantes

    ; La cola está vacía, así que el flanco de A es para hablar. En RM2k es el
    ; mismo botón que cierra un mensaje y que confirma, y el orden importa: con
    ; un mensaje abierto el jugador no se actualiza —arriba se sale por
    ; `no_avanza`— así que no puede hablarle a nadie mientras lee.
    ;
    ; Y sólo con el héroe quieto: `CheckActionEvent` cuelga del `if
    ; (IsStopping())` de `Game_Player::UpdateNextMovementAction`.
    lda pad_a
    beq nada
    lda pad_a_ant
    bne nada                    ; ya lo tenía apretado: no es un flanco
    lda step_left
    bne nada                    ; a mitad de un paso no se habla
    ; La ruta forzada del héroe se mira adentro: ver `probar_accion`.
    jsr probar_accion
    beq nada
    ; Marcó un evento: se arranca en este mismo cuadro.
hay_esperando:
    jsr arrancar_esperando
    beq nada                    ; ninguno tenía página con qué correr

corriendo:
    ; El `while (!interp.IsRunning())` de `Game_Map::UpdateForegroundEvents`:
    ; si la página termina, la que siga esperando arranca **en este mismo
    ; cuadro** y no en el que viene. Encadenarlas al cuadro siguiente metía un
    ; cuadro de diferencia por página, y una cinemática son decenas.
    lda #ARRANQUES_MAX
    sta arranques
seguir_corriendo:
    jsr correr_codigo
    ; Si la página terminó y era la del evento que gira, vuelve a su pose: el
    ; `UpdateFacing` de `OnFinishForegroundEvent`.
    lda ev_activo
    bne sin_fin_de_giro
    lda f:GIRO_EV
    cmp ev_corriendo
    bne sin_fin_de_giro
    jsr giro_deshacer
sin_fin_de_giro:
    ; El refresco pendiente, **al salir del intérprete**: es el
    ; `if (Game_Map::GetNeedRefresh()) Game_Map::Refresh();` del final de
    ; `Game_Interpreter::Update`, y de él depende que el idioma de RM2k
    ; funcione. Una página que prende el switch que la desactiva deja de ser la
    ; activa antes de que se decida qué corre después; sin esto, al terminar
    ; seguía pareciendo automática y volvía a arrancar en el mismo cuadro, una
    ; y otra vez hasta agotar el presupuesto de `ARRANQUES_MAX`.
    ;
    ; EasyRPG además refresca **antes de cada comando**, arriba del lazo. Acá
    ; no hace falta y sale caro: ningún opcode de los que hay lee cuál es la
    ; página activa de un evento —el único que la lee es `arrancar_esperando`,
    ; que corre justo acá abajo—. Haciéndolo por comando, la cinemática de
    ; apertura perdía cinco cuadros: sus páginas prenden switches de a montones.
    ; El día que aparezca un opcode que sí la lea, esto vuelve al lazo.
    lda refresco
    beq sin_refresco_aca
    stz refresco
    lda #1
    sta refresco_cuadro         ; la completa, al principio del cuadro que viene
    jsr elegir_automaticas
sin_refresco_aca:
    lda salto_hay
    bne hubo_salto
    lda ev_activo
    bne nada                    ; sigue corriendo: el cuadro terminó
    lda esperando_n
    beq nada
    dec arranques
    beq nada                    ; se acabó el presupuesto del cuadro
    jsr arrancar_esperando
    bne seguir_corriendo
    rts
hubo_salto:
    stz salto_hay
    rep #$20
.a16
    lda salto_x
    sta entrada_x
    lda salto_y
    sta entrada_y
    sep #$20
.a8
    ; De acá no se carga nada: se pide el fundido y el mapa se carga adentro,
    ; en el primer cuadro negro. Ver `fundido_tick`. Lo que sí queda decidido
    ; acá es **cuál** de los dos casos es, porque `mapa_actual` va a haber
    ; cambiado para cuando toque hacerlo.
    ;
    ; Un salto **al mismo mapa** no recarga nada: sólo mueve al héroe. Es el
    ; `map_changed = (GetMapId() != teleport_target.GetMapId())` de
    ; `Game_Player::PerformTeleport`. Recargarlo volvía a encolar los eventos
    ; automáticos, y con eso la cinemática de apertura —que salta dos veces
    ; adentro del mapa 1— se reiniciaba sola para siempre. Fundir, en cambio,
    ; funde igual: en RM2k el `TeleportParams` sale siempre con
    ; `erase_screen = true`, mire a donde mire el salto.
    ; El índice del mapa es de dieciséis bits —ver `mapa_actual`— y esto va por
    ; X y no por A justamente por eso: X ya es de dieciséis, así que copiar y
    ; comparar no cuesta el `rep`/`sep` que sí costaría por el acumulador. Y no
    ; es una cuenta de elegancia: con los cuatro bytes de más, el `beq nada` de
    ; `eventos_tick` se pasaba de los 128 que alcanza un salto relativo.
    ldx salto_mapa
    stx fundido_mapa
    cpx mapa_actual
    bne otro_mapa
    lda #FUNDIDO_MISMO          ; un salto al mismo mapa no recarga nada
    bra pedir_fundido
otro_mapa:
    ; El presupuesto de saltos se gasta **acá y no antes**, o sea sólo cuando
    ; se cambia de mapa: un salto al mismo mapa no lo toca.
    ;
    ; Cobrándoselo a los saltos al mismo mapa —que es lo que hacía— el
    ; presupuesto se drenaba sin reponerse nunca, porque un salto al mismo mapa
    ; no llama a `cargar_mapa`, que es quien lo repone. La escena de Talan salta
    ; tres veces adentro del mapa 3 y la apertura dos adentro del 1: después de
    ; ocho, **todo teletransporte se descartaba en silencio**. taro lo vio como
    ; puertas que se abren y no llevan a ningún lado, y como algo que "a veces
    ; pasa y a veces no": dependía de cuántos saltos llevara la partida.
    ;
    ; Y se mira antes de bajarlo, no después: con `dec` sobre cero el byte daba
    ; la vuelta a 255 y el tope fallaba **una sola vez** y después dejaba pasar
    ; doscientos cincuenta y cinco más.
    lda saltos_restantes
    bne hay_presupuesto
    lda #PANICO_SALTOS
    jmp entrar_en_panico        ; y de ahí no se vuelve
hay_presupuesto:
    dec saltos_restantes
    lda #FUNDIDO_SALTO
pedir_fundido:
    jsr empezar_fundido
    ; La página que pidió el salto sigue corriendo del otro lado: su código está
    ; en la ROM y el cursor quedó guardado. Las páginas del mapa nuevo se
    ; encolan recién cuando ésta termine.
nada:
    rts
.endproc

; La mitad de `eventos_tick` que atiende un salto pendiente, para el lazo
; principal: el `Teleport` de un paralelo con el primer plano quieto. Con
; nombre global porque `arranque.s` va antes en el ensamblado, y `ca65` no
; resuelve `eventos_tick::hubo_salto` hacia adelante.
eventos_atender_salto = eventos_tick::hubo_salto

; --- los intérpretes paralelos ----------------------------------------------
; `Game_Map::UpdateMapEvents`: cada evento con una página paralela tiene **su
; propio intérprete** y corre todos los cuadros, aparte del de primer plano, con
; un mensaje abierto y con otra página en curso. Cuando su página termina, el
; cuadro siguiente la vuelve a empezar: RPG_RT hace el `Push` antes de cada
; `Update` si el intérprete no está corriendo, así que una página que se agota
; en un cuadro se reinicia para siempre. Es lo que hace andar a los cuatro autos
; de Lashe City, cuya página entera es un `MoveEvent`.
;
; Corren con los **mismos** globales que el primer plano —`cod_ptr`, `ev_cur`,
; `ev_esperando`, `ev_activo`, `ev_corriendo`— así que ese contexto se guarda en
; la pila y se devuelve al final. Doce bytes, y cuánta pila queda debajo lo mide
; `pruebas/rpgmaker/test_pila.py`: este camino es uno de los que corre.
;
; El estado de cada uno va en la RAM del banco 1 e **indexado por evento**, no
; por ranura, y lleva de qué página es: si la página activa cambia, RM2k rehace
; el intérprete (`Game_Event::Setup`), así que se arranca de cero. Sin eso, un
; refresco en medio de una espera la dejaba a mitad de camino corriendo el
; código de otra página.
.proc limpiar_paralelos
.a8
.i16
    stz par_n
    rep #$20
.a16
    lda #FAR_PAR_ESTADO
    sta WMADDL                  ; los dos bytes bajos de la dirección
    sep #$20
.a8
    stz WMADDH
    ldx #(EV_MAX * PAR_BYTES)
borrar:
    stz WMDATA                  ; el puerto auto-incrementa
    dex
    bne borrar
    rts
.endproc

; La ventana de banco apuntada a la entrada de la lista que trae A. Es la misma
; cuenta para escribirla y para leerla, y estaba copiada en los dos lados.
.proc par_lista_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_LISTA_BYTES
    clc
    adc #FAR_PAR_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; Anota al evento `rp_ev` en la lista de paralelos del mapa, con la página que
; acaba de ganar: entra con `pg_*` de ella y con `pag_ofs` en su offset, que es
; como `aplicar_paginas` la tiene leída.
.proc anotar_paralelo
.a8
.i16
    lda par_n
    cmp #PARALELO_MAX
    bcc hay_lugar
    rts                         ; el conversor corta antes de que esto pase
hay_lugar:
    jsr par_lista_apuntar
    lda rp_ev
    sta WMDATA
    lda pg_cod
    sta WMDATA
    lda pg_cod + 1
    sta WMDATA
    lda pg_cod + 2
    sta WMDATA
    lda pag_ofs
    sta WMDATA
    lda pag_ofs + 1
    sta WMDATA
    inc par_n
    rts
.endproc

; Un cuadro de cada evento con página paralela.
.proc paralelos_tick
.a8
.i16
    lda par_n
    bne hay
    rts
hay:
    rep #$20
.a16
    lda ev_cur
    pha
    lda ev_esperando
    pha
    lda ev_corriendo
    pha
    lda cod_ptr
    pha
    sep #$20
.a8
    lda cod_ptr + 2
    pha
    lda ev_activo
    pha

    stz par_i
lazo:
    ; Primero los que se resuelven sin intérprete: `paralelos_celda`, en el
    ; banco 1, corre de corrido los que empiezan con `OP_CELL_TEST` y no pasan
    ; de ahí, y para en el primero que no es así. Con el acarreo en 1 paró en
    ; uno cuya condición se cumplió: sigue desde Y, con su intérprete.
    jsl f:paralelos_celda + RAPIDO  ; ver MEMSEL
    bcc lento
    jsr un_paralelo_seguir
    bra siguiente
lento:
    lda par_i
    cmp par_n
    bcs listos
    ; La entrada de la lista, con direccionamiento largo indexado y no por la
    ; ventana de WMADD: apuntar el puerto costaba más que leer, y esto corre
    ; por cada paralelo en cada cuadro —cuarenta y uno en cada vuelta de la
    ; carrera—.
    rep #$20
.a16
    lda par_i
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_LISTA_BYTES
    tax
    lda f:FAR_LARGO + FAR_PAR_LISTA + 1, x
    sta cod_ptr                 ; su página, ya resuelta por el refresco:
    lda f:FAR_LARGO + FAR_PAR_LISTA + 4, x
    sta pag_ofs                 ; derecho al cursor del intérprete, que es lo
    lda f:FAR_LARGO + FAR_PAR_LISTA + 0, x
    and #$00FF                  ; único que `un_paralelo` iba a hacer con ella
    asl a
    asl a
    asl a                       ; por PAR_BYTES: dónde cae su estado
    sta par_dir
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_LISTA + 0, x
    sta par_ev                  ; de qué evento es
    lda f:FAR_LARGO + FAR_PAR_LISTA + 3, x
    sta cod_ptr + 2
    jsr un_paralelo
siguiente:
    inc par_i
    lda par_i
    cmp par_n
    bcc lazo
listos:

    ; Fuera del lazo no hay paralelo, y eso es lo que `op_message` mira para
    ; saber si el mensaje que abre es de un paralelo o del primer plano.
    lda #$FF
    sta par_ev

    pla
    sta ev_activo
    pla
    sta cod_ptr + 2
    rep #$20
.a16
    pla
    sta cod_ptr
    pla
    sta ev_corriendo
    pla
    sta ev_esperando
    pla
    sta ev_cur
    sep #$20
.a8
    rts
.endproc

; Un cuadro del evento `par_ev`, con `cod_ptr`, `pag_ofs` y `par_dir` —dónde
; cae su estado— ya puestos por el lazo desde la lista de paralelos.
;
; Acá **no** se vuelve a elegir la página ni a leerla del cartucho. Era lo que
; costaba el cuadro en el HQ de los Lazer Teeth —once paralelos, y el décimo se
; pasaba— y no podía dar otra respuesta: la lista y lo que lleva adentro los
; rehace `aplicar_paginas`, que es `Game_Map::Refresh`, o sea el único momento
; en que la página activa cambia. Tampoco hace falta preguntar si la página es
; paralela y si compiló: si no lo fuera, el evento no estaría en la lista.
.proc un_paralelo
.a8
.i16
    ; Con un mensaje en pantalla un paralelo sigue corriendo —para eso
    ; existe—, **salvo que el mensaje sea suyo**: el guard de
    ; `Game_Interpreter::Update` es `IsMessageActive() && _state.show_message`
    ; (easyrpg `game_interpreter.cpp:434-441`). Sin esto, el paralelo del
    ; guardia del `Lazer Teeth HQ` prendía sus dos switches y se echaba a
    ; caminar un tick después de pedir su propio mensaje.
    ;
    ; Su estado no se lee ni se guarda: este cuadro no lo toca. El paso del
    ; evento sí se da, porque `Game_Event::Update` llama a
    ; `Game_Character::Update()` pase lo que pase con el intérprete.
    lda msg_abierto
    ora msg_estado              ; también mientras se compone
    ora eleg_activo
    beq no_es_mio
    lda msg_duenio
    cmp par_ev
    bne no_es_mio
    jmp dar_el_paso             ; `beq` no llega: el cuerpo está en el medio
no_es_mio:
    ; Su estado, en `FAR_PAR_ESTADO` + `par_dir`, con direccionamiento largo
    ; indexado: igual que la lista, y por lo mismo. Sólo se lee y se escribe
    ; lo que hace falta: con una espera en curso cambia la espera y nada más.
    rep #$20
.a16
    ldx par_dir
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 5, x
    cmp pag_ofs                 ; de qué página era este estado
    bne otra_pagina
    ; La espera, igual que la del primer plano.
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    bne esperando
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 4, x
    beq empezar                 ; no venía corriendo
    sta ev_activo               ; venía: sigue por donde quedó
    rep #$20
.a16
    stz ev_esperando
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 0, x
    sta ev_cur
    sep #$20
.a8
    bra corriendo
.a16
esperando:
    dec a
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    sep #$20
.a8
    ; Y si está corriendo, que es lo que mira su paso: una ruta propia no
    ; lee órdenes nuevas con la página en curso (`cuadro_de_ruta_ev`).
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 4, x
    sta ev_activo
    jmp dar_el_paso             ; este cuadro se le va esperando
.a16
otra_pagina:
    ; Otra página: otro intérprete, y su número queda anotado. RM2k lo rehace
    ; en `Game_Event::Setup`, así que arranca de cero. La espera y si corría
    ; se escriben ya, en cero, y no al guardar: el atajo de abajo no guarda.
    lda pag_ofs
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 5, x
    lda #0
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    sep #$20
.a8
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 4, x
empezar:
    ; No venía corriendo: la página vuelve a empezar. Es el `Push` que RPG_RT
    ; hace antes de cada `Update`, y por eso no se reinicia al terminar sino al
    ; cuadro siguiente.
    ;
    ; **El atajo de `OP_CELL_TEST`.** Una página que empieza con él —las de
    ; los autos de la carrera, las luces del mapa 11— casi siempre falla la
    ; condición y termina ahí mismo: su condición se evalúa acá, sin pasar por
    ; `correr_codigo`, y si lo que sigue es el `OP_DONE` la página terminó y
    ; su estado ya está como tiene que quedar —sin espera y sin correr—, así
    ; que no se guarda. Es exactamente la primera vuelta del intérprete y la
    ; segunda; si lo que sigue es otra cosa, el intérprete sigue desde ahí.
    ; Son casi dos líneas de las 262 del cuadro por página: ver
    ; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    lda [cod_ptr]               ; el primer opcode
    cmp #OP_CELL_TEST
    bne desde_cero
    ldy #1
    jsl f:celda_probar + RAPIDO   ; ver MEMSEL
    lda [cod_ptr], y
    bne seguir                  ; no es el OP_DONE
    stz ev_activo               ; lo que haría `op_done`
    jmp dar_el_paso
desde_cero:
    ldy #0
::un_paralelo_seguir:
seguir:
    rep #$20
.a16
    sty ev_cur
    stz ev_esperando
    sep #$20
.a8
    lda #1
    sta ev_activo
corriendo:
    rep #$20
.a16
    lda par_ev
    and #$00FF
    sta ev_corriendo            ; de quién es la página, para un MoveEvent suyo
    sep #$20
.a8
    jsr correr_codigo
    rep #$20
.a16
    ldx par_dir
    lda ev_cur
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 0, x
    lda ev_esperando
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    sep #$20
.a8
    lda ev_activo
    sta f:FAR_LARGO + FAR_PAR_ESTADO + 4, x

dar_el_paso:
    ; Y el paso de **este** evento, acá mismo y no al final de la vuelta.
    ; `Game_Event::Update` corre el intérprete paralelo y a continuación llama a
    ; `Game_Character::Update()` —easyrpg, `game_event.cpp:580`—, y
    ; `UpdateMapEvents` hace eso evento por evento. No es lo mismo que correr
    ; todos los intérpretes y después mover a todos: se ve cuando una página
    ; paralela le fuerza una ruta a **otro** evento. En Lashe City el `Car4` le
    ; pisa la suya al `Car2` en cada cuadro —los dos apuntan al id 3 de RM2k, que
    ; ahí es el `Car2`— y con los pasos todos al final el pisotón gana y el
    ; `Car2` no camina nunca. taro lo vio, y en EasyRPG y en el RPG Maker
    ; original los cuatro autos andan.
    ;
    ; La ranura sale de la marca que deja `ranura_anotar`, y no de buscarla
    ; con `ranura_del_evento`: la búsqueda recorría todas las ranuras usadas
    ; por cada paralelo en cada cuadro, y en la carrera, con cinco autos que
    ; andan y cuarenta paralelos, eran treinta líneas de las 262 del cuadro.
    ldx par_dir
    lda f:FAR_LARGO + FAR_PAR_ESTADO + PAR_RANURA, x
    beq sin_ranura
    dec a
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por RUTA_EV_STRIDE
    tax
    sep #$20
.a8
    phx
    jsr cuadro_de_ruta_ev
    plx
    phx
    jsr animar_ruta_ev
    plx
    phx
    jsr refrescar_npc
    plx
    lda ruta_ev + 18, x
    ora #$40                    ; ya dio su paso: `mover_eventos` lo saltea
    sta ruta_ev + 18, x
sin_ranura:
    rts
.endproc

; La ranura de ruta del evento cuyo índice trae A: X, o $FFFF si no tiene.
; Lo que la página activa de un evento que cambia de gráfico dibuja, copiado a
; su fila de NPC: el tile, los atributos —paleta y prioridad de su capa—, la
; pose y hacia dónde mira, si se ve, y los bits de paso de su tile. Y la clave
; de dibujado con la capa de la página, que puede cambiar —el ascensor del
; mapa 2 pasa de la capa del héroe a la de abajo al abrirse—, así que la fila
; se reacomoda como la de un evento que camina. Es `SetupFromPage` para el
; gráfico, y es lo que abre las puertas de este juego: la página con el tile
; de los escombros aparece donde antes no había nada. Entra con `pg_*` de la
; página activa y el evento en `rp_ev`.
.proc grafico_de_pagina
.a8
.i16
    ; El bit 5 dice que la fila sigue a la página, y quiere decir dos cosas
    ; según la fila:
    ;
    ; * **si no camina**, sale todo de la página activa: el tile, la paleta, la
    ;   pose y si se ve. Es lo que abre las puertas de este juego.
    ; * **si camina**, todo eso menos el tile y la paleta, que apuntan a su
    ;   ranura de doce poses y pisarlos la dejaría quieta.
    ;
    ; La distinción existe porque un evento puede caminar **y** aparecer con la
    ; página, y antes del 2026-09-08 el conversor tenía que elegir: elegía
    ; caminar, y entonces la fila —que nace escondida cuando al cargar el mapa
    ; ninguna página cumple— no aparecía nunca. taro lo encontró con el `Bum` y
    ; el `Mechanic` de Lashe City; RM2k los dibuja y la ROM no, 245 y 191
    ; pixeles.
    ;
    ; No es un bit nuevo porque en +13 no queda ninguno: con ruta propia los
    ; cinco de abajo son las banderas de la ruta. Y no hace falta, porque
    ; **la fila ya lo dice**: +9 vale NPC_QUIETO o el banco de sus poses.
    lda pg_flags
    and #$20
    bne hay_algo
    rts                         ; su fila no sigue a la página
hay_algo:
    lda rp_ev
    jsr npc_de_evento
    cpy #$FFFF
    bne hay_fila
    rts                         ; sin fila: nada que dibujar
hay_fila:
    sty npc_fila
    lda pg_pose
    bmi con_grafico
    lda #0                      ; la página no dibuja nada: escondido
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
    rts
con_grafico:
    and #$0F
    sta npc_buf + 12, y         ; la pose que hay en VRAM es ésta
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:dir_de_pose, x
    sta npc_buf + 10, y
    ; El tile y la paleta sólo si la fila no camina. Si camina, apuntan a su
    ; ranura de doce poses y pisarlos la dejarían quieta; la pose de arriba sí
    ; va, que es la que la página declara y la que el refresco sube del banco.
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne sin_tocar_el_tile
    lda pg_tile
    sta npc_buf + 6, y
    lda pg_attr
    sta npc_buf + 7, y
sin_tocar_el_tile:
    lda #1
    sta npc_buf + 14, y
    lda pg_pasa
    sta npc_buf + 15, y
    cmp #$FF
    beq :+
    sta pasa_hay                ; impone: `pasa_con_evento` tiene que mirar
:
    ; La clave: la capa de la página, con la Y de la fila.
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$0FFF
    sta temp
    lda pg_capa
    and #$00FF
    xba
    asl a
    asl a
    asl a
    asl a
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8
    phy
    jsr giro_reponer            ; si es la que gira, gira de nuevo
    ply
    jmp acomodar_npc
listo:
    rts
.endproc

; Esconde la fila del evento en A, si tiene una: no se dibuja y su tile no le
; impone nada a la celda.
.proc esconder_npc
.a8
.i16
    jsr npc_de_evento
    cpy #$FFFF
    beq listo
    lda #0
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
listo:
    rts
.endproc

.proc ranura_del_evento
.a8
.i16
    sta otro_ev
    ; De la más alta usada para abajo, y no de cero para arriba: así el corte
    ; es `X == 0`, que el `tax` deja en Z gratis, y no hace falta un límite de
    ; dieciséis bits en RAM —que no hay—. Un evento tiene a lo sumo una ranura
    ; —sólo se le da una cuando `ranura_del_evento` no le encontró ninguna— así
    ; que el orden no cambia la respuesta.
    lda ruta_ev_tope
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por RUTA_EV_STRIDE
    tax
    sep #$20
.a8
buscar:
    cpx #$0000
    beq no_tiene
    rep #$20
.a16
    txa
    sec
    sbc #RUTA_EV_STRIDE
    tax
    sep #$20
.a8
    lda ruta_ev, x
    cmp otro_ev
    bne buscar
    rts                         ; X = su ranura
no_tiene:
    ldx #$FFFF
    rts
.endproc

; Una ranura de ruta libre: X, o $FFFF si no queda ninguna.
.proc ranura_libre
.a8
.i16
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq listo
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    ldx #$FFFF
    rts                         ; sin lugar: el tope no se toca
listo:
    ; La ranura pasa a tener dueño, así que el tope sube si quedó más arriba
    ; del que había. Es el único lugar por donde se toma una: las dos —la
    ; página propia y la ruta forzada— piden acá.
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; de bytes a número de ranura
    inc a
    sep #$20
.a8
    cmp ruta_ev_tope
    bcc ya_estaba
    sta ruta_ev_tope
ya_estaba:
    rts
.endproc

; La ruta propia de la página recién leída, a la ranura X, desde el principio.
; Queda guardada también aparte —+24 a +29— para volver a ella cuando una
; ruta forzada sobre el mismo evento termine.
.proc cargar_pagina_en_ranura
.a8
.i16
    lda pg_ruta
    sta ruta_ev + 1, x
    sta ruta_ev + 24, x
    lda pg_ruta + 1
    sta ruta_ev + 2, x
    sta ruta_ev + 25, x
    lda pg_ruta + 2
    sta ruta_ev + 3, x
    sta ruta_ev + 26, x
    lda pg_ruta_n
    sta ruta_ev + 4, x
    sta ruta_ev + 27, x
    stz ruta_ev + 5, x
    lda pg_frec
    sta ruta_ev + 16, x
    sta ruta_ev + 28, x
    lda pg_vel
    sta ruta_ev + 17, x
    sta ruta_ev + 29, x
    lda pg_flags
    and #$1E
    ora #$01                    ; de página
    sta ruta_ev + 18, x
    lda pg_capa
    sta ruta_ev + 31, x         ; su capa, para chocar con los demás
    rep #$20
.a16
    lda pag_ofs
    sta ruta_ev + 20, x
    sep #$20
.a8
    lda pg_frec
    jsr tras_giro               ; `SetMaxStopCountForTurn` antes de la primera
    sta ruta_ev + 9, x
    rts
.endproc

; La página nueva del evento de la ranura X no tiene ruta: se queda sin
; órdenes y sin página a la que volver.
.proc quitar_pagina_de_ranura
.a8
.i16
    lda ruta_ev + 18, x
    and #$01
    beq listo                   ; corría una forzada: no se toca
    stz ruta_ev + 4, x
    stz ruta_ev + 5, x
    stz ruta_ev + 9, x
    lda ruta_ev + 18, x
    and #$FE
    sta ruta_ev + 18, x
listo:
    stz ruta_ev + 27, x
    rep #$20
.a16
    lda #$FFFF
    sta ruta_ev + 20, x
    sep #$20
.a8
    rts
.endproc

; Cuánto avanza el paso de la ranura X por cuadro, a `temp`, de dieciséis bits.
.proc paso_de_ranura
.a8
.i16
    lda ruta_ev + 17, x
    dec a
    asl a
    rep #$20
.a16
    and #$00FF
    tay
    phx                         ; X trae la ranura y el que llama cuenta con ella
    tyx
    lda f:paso_por_vel, x
    plx
    sta temp
    sep #$20
.a8
    rts
.endproc

; Cuánto avanza el salto de la ranura X por cuadro, en A.
.proc salto_de_ranura
.a8
.i16
    lda ruta_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    phx                         ; X trae la ranura y el que llama cuenta con ella
    tyx
    lda f:salto_por_vel, x
    plx
    rts
.endproc

; Cuánto avanza el salto del héroe por cuadro, en A: `jump_speed[move_speed - 1]`
; de RM2k, con la velocidad que le dejó la última ruta. Conserva X.
.proc salto_del_heroe
.a8
.i16
    phx
    jsr hero_vel_leer
    rep #$20
.a16
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    lda f:salto_por_vel, x
    plx
    rts
.endproc

; La capa de la página activa del evento cuyo índice trae A, o $FF si no tiene
; ninguna. Es la misma pasada que `encolar_por_accion`: gana la última página
; cuyas condiciones se cumplen. Conserva X e Y; pisa `pag_*` y `pg_*`, que
; nadie tiene a medio usar cuando esto corre —se llama desde un paso, no desde
; adentro de una búsqueda de página—.
.proc capa_activa
.a8
.i16
    phx
    phy
    rep #$20
.a16
    and #$00FF
    sta capa_ev
    sep #$20
.a8
    lda #$FF
    sta capa_hallada
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
recorrer:
    ; Sólo el evento que se busca: de las demás páginas se lee el evento y
    ; nada más. Leerlas enteras costaba, con un droide empujando contra el
    ; héroe cuadro por cuadro, más de un cuadro cada tanto.
    rep #$20
.a16
    ldy pag_ofs
    lda [pag_ptr], y            ; +0 a qué evento pertenece
    cmp capa_ev
    sep #$20
.a8
    bne siguiente
    jsr leer_pagina
    jsr condiciones_ok
    beq siguiente
    lda pg_capa
    sta capa_hallada
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
    lda capa_hallada
    ply
    plx
    rts
sin_paginas:
.a16
    sep #$20
.a8
    lda #$FF
    ply
    plx
    rts
.endproc

; Si el evento cuyo índice trae A está atravesando paredes: tiene ranura de
; ruta y la ranura lleva el bit. Devuelve A distinto de cero si sí. Pisa X.
.proc atraviesa_el_evento
.a8
.i16
    sta otro_ev
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp otro_ev
    bne siguiente
    lda ruta_ev + 12, x
    and #$01
    rts
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    lda #0
    rts
.endproc

; ¿Hay alguien parado en `dest_x`/`dest_y` que le cierre el paso a `movil`?
; Devuelve A distinto de cero si sí.
;
; Es `WouldCollide` de `game_map.cpp` con lo que este repo modela: dos
; personajes chocan si están en la misma capa —la del héroe es CAPA_HEROE— y
; no chocan si alguno de los dos atraviesa paredes. Un evento sin página
; activa no está y no choca. La celda de cada evento es la de `ev_pos_buf`,
; que se mueve al **empezar** el paso: es `IsInPosition` sobre `GetX()`, o sea
; la de destino mientras camina; y la del héroe es `tile_x`/`tile_y`, que
; `begin_step` mueve igual. Lo que no se modela es `overlap_forbidden` —17
; páginas del juego— y el conflicto de un evento con gráfico de tile contra su
; propio bloque. Pisa X e Y.
.proc celda_bloqueada
.a8
.i16
    lda movil_capa
    cmp #$FF
    beq libre_cerca             ; sin página activa no choca con nadie
    lda movil
    cmp #MOVIL_HEROE
    beq es_heroe
    jsr atraviesa_el_evento
    bne libre_cerca
    bra recorrer
es_heroe:
    ; **`atravesando` y no `ruta_atraviesa`**, que es la divergencia declarada
    ; en workflow/divergencias/atravesar-paredes-vale-mientras-dura-la-ruta.md:
    ; la bandera que deja la orden 36 vale mientras el paso lo dé la ruta forzada —ahí
    ; `paso_de_ruta` la copia a `atravesando`— y no para la caminata con el
    ; pad, que la deja en cero. Leyendo la pegajosa, cualquier página que
    ; prendiera el 36 y no lo apagara dejaba al héroe caminando por encima de
    ; **todos** los eventos para el resto de la partida, y las paredes lo
    ; seguían frenando porque `can_leave` y `can_enter` ya miraban
    ; `atravesando`: el mismo héroe atravesaba eventos y no paredes. Lo vio
    ; taro jugando, con los cofres del Sector 30, y el culpable es el
    ; Hover-Tram (mapa 13, EV0028), que prende la 36 y nunca la apaga.
    lda atravesando
    beq recorrer
libre_cerca:
    jmp libre                   ; `libre` queda lejos para un salto corto
recorrer:
    ; De atrás para adelante y en dieciséis bits, con Y en la celda de cada
    ; evento: la respuesta es un sí o un no, así que el orden no la cambia, y
    ; así la vuelta es la mitad de larga. Corre en cada paso que empieza
    ; —tres de éstas y de `pasa_con_evento` por paso—, y en la carrera, con
    ; cuarenta autos, eran nueve líneas cada una: ver
    ; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    rep #$20
.a16
    lda ev_total
    asl a
    asl a                       ; por EV_STRIDE
    tay
    bra siguiente
otro:
    lda ev_pos_buf, y
    cmp dest_x
    beq misma_x
siguiente:
    dey
    dey
    dey
    dey                         ; EV_STRIDE
    bpl otro
    sep #$20
.a8
    bra eventos_listos
.a16
misma_x:
    lda ev_pos_buf + 2, y
    cmp dest_y
    bne siguiente
    tya
    lsr a
    lsr a                       ; el índice cabe en un byte: EV_MAX es 128
    sep #$20
.a8
    cmp movil
    beq siguiente8              ; consigo mismo no
    sta otro_ev
    phy
    jsr atraviesa_el_evento
    bne no_choca
    lda otro_ev
    jsr capa_activa
    cmp movil_capa
    bne no_choca
    ply
    lda #1
    rts
no_choca:
    ply
siguiente8:
    rep #$20
.a16
    bra siguiente
.a8
eventos_listos:
    ; Y el héroe, cuando quien se mueve es un evento de su capa.
    lda movil
    cmp #MOVIL_HEROE
    beq libre
    lda movil_capa
    cmp #CAPA_HEROE
    bne libre
    lda ruta_atraviesa
    bne libre
    rep #$20
.a16
    lda tile_x
    cmp dest_x
    bne libre16
    lda tile_y
    cmp dest_y
    bne libre16
    sep #$20
.a8
    lda #1
    rts
libre16:
.a16
    sep #$20
.a8
libre:
    lda #0
    rts
.endproc

; `celda_bloqueada` para el héroe: la celda de destino ya está en dest_x/dest_y.
.proc heroe_bloqueado
.a8
.i16
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    jmp celda_bloqueada
.endproc

; `movil` y `movil_capa` desde la ranura de ruta que apunta X. Conserva X.
.proc preparar_movil
.a8
.i16
    lda ruta_ev + 0, x
    sta movil
    lda ruta_ev + 31, x         ; la capa que la ranura trae desde que se cargó
    sta movil_capa
    rts
.endproc

; ¿Se cumplen las condiciones de la página leída? Vuelve con Z=0 si sí.
; Un switch en 0 quiere decir "esta página no lo pide".
.proc condiciones_ok
.a8
.i16
    rep #$20
.a16
    lda pg_sa
    beq mirar_b
    jsr switch_encendido
    beq falla
mirar_b:
    lda pg_sb
    beq cumple
    jsr switch_encendido
    beq falla
cumple:
    sep #$20
.a8
    ; Y la condición de grupo: un 0 quiere decir "esta página no pide a nadie".
    lda pg_actor
    beq mirar_var
    jsr en_el_grupo
    beq falla8
mirar_var:
    ; Y el ítem y la variable, que se leen de la tabla y no de una copia —la
    ; BSS está llena—: +28 el ítem o 0, y +24 la ranura o $FF por "no pide
    ; ninguna", +25 cómo se compara y +26 contra qué. Es la misma comparación
    ; con signo de
    ; `ConditionalBranch`, `comparar_var`, con los mismos seis códigos: RM2k
    ; usa `CheckOperator` para las dos. Pisa X e Y, como ya lo hacía
    ; `switch_encendido`.
    ldy pag_ofs
    rep #$20
.a16
    tya
    clc
    adc #28
    tay
    lda [pag_ptr], y            ; +28 el ítem que pide, o 0
    beq sin_item
    ; Con el inventario en la RAM lejana: la cuenta del ítem, y con cero no
    ; está. Es `GetItemCount(id) + GetEquippedItemCount(id)` sin equipo.
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq falla8
    rep #$20
.a16
sin_item:
    tya
    sec
    sbc #4
    tay                         ; +24
    sep #$20
.a8
    lda [pag_ptr], y            ; +24 la ranura
    cmp #$FF
    beq cumple8
    pha
    iny
    lda [pag_ptr], y            ; +25 la comparación
    sta temp + 1
    iny
    rep #$20
.a16
    lda [pag_ptr], y            ; +26 contra qué, con signo
    sta temp + 2
    sep #$20
.a8
    pla
    jsr var_leer                ; A = la variable, de dieciséis
.a16
    jsr comparar_var
.a8
    beq falla8
cumple8:
    lda #1                      ; Z=0
    rts
falla8:
    lda #0                      ; Z=1
    rts
sin_usar:
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
falla:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
    lda #0                      ; Z=1
    rts
.endproc

; ¿Está encendido el switch cuyo número viene en A? Vuelve con Z=0 si sí.
.proc switch_encendido
.a16
.i16
    pha
    and #$0007
    tax                         ; el bit dentro del byte
    pla
    lsr a
    lsr a
    lsr a
    tay                         ; y qué byte del bitmap
    sep #$20
.a8
    lda switches, y
    and f:mascara, x
    rep #$20
.a16
    rts                         ; rep no toca Z, así que el and sigue valiendo
.endproc

; La parte de encolar, que comparten los automáticos y la tecla de acción.
; Ningún evento esperando y ninguno automático: al entrar a un mapa las marcas
; del anterior no valen nada, y sus índices de evento apuntarían a otros
; eventos. La llama la carga del mapa **antes** del refresco, que es quien
; vuelve a prender el `FLAG_AUTO` de los que corresponda.
.proc limpiar_esperas
.a8
.i16
    ldx #$0000
:   stz ev_flags, x
    inx
    cpx #EV_MAX
    bne :-
    stz esperando_n
    stz auto_n
    stz refresco_cuadro
    ; Y de quién era la página que corre: si sobrevivió a un teletransporte, su
    ; índice ya no significa nada en el mapa nuevo.
    rep #$20
.a16
    lda #$FFFF
    sta ev_corriendo
    sep #$20
.a8
    rts
.endproc

; Todo evento con una automática activa vuelve a quedar esperando. Es
; `Game_Event::CheckEventAutostart`, que corre una vez por cuadro y para todos.
; Lo llama `eventos_tick` antes del intérprete, y sólo si `auto_n` dice que hay
; alguna.
.proc esperar_automaticas
.a8
.i16
    ldx #$0000
mirar:
    lda ev_flags, x
    and #FLAG_AUTO
    beq siguiente
    jsr marcar_esperando
siguiente:
    inx
    cpx ev_total
    bne mirar
    rts
.endproc

; La página activa que anotó el refresco para el evento X, a `elegida`. Z=1 si
; no hay ninguna anotada y hay que salir a buscarla.
;
; Existe para que arrancar una página no cueste una recorrida de todas las del
; mapa. El refresco ya la resolvió; volver a resolverla acá era hacer dos veces
; el mismo trabajo, y el segundo caía en un cuadro cualquiera.
.proc pagina_desde_eleg
.a8
.i16
    stz elegida_hay
    cpx #EV_MAX
    bcs no
    rep #$20
.a16
    txa
    asl a
    tay
    lda eleg_por_ev, y
    cmp #$FFFD                  ; $FFFD, $FFFE y $FFFF son centinelas
    bcc anotada
    sep #$20
.a8
no:
    lda #0
    rts
.a16
anotada:
    sta pag_ofs
    ; Con X, y no con Y como hasta que `mapa_tabla` se mudó a RODATA: el
    ; direccionamiento absoluto largo indexado del 65816 sólo existe con X. X
    ; trae el evento y el llamador cuenta con él, así que va y vuelve por la
    ; pila; el `plx` deja N y Z del valor que saca, y por eso lo que sigue es
    ; un `jsr` y no una rama.
    phx
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    plx
    jsr leer_pagina
    lda pg_trigger
    sta elegida_trigger
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
    rts
.endproc

; Arranca la página del primer evento que esté esperando. Devuelve 0 si no
; arrancó ninguna. El orden es por número de evento, que es el mismo en que
; `Game_Map::Update` recorre `events`.
;
; La página se resuelve **acá**, no cuando se marcó el evento: entre una cosa y
; la otra puede haber pasado un refresco y ser otra la activa.
.proc arrancar_esperando
.a8
.i16
    ldx #$0000
buscar:
    lda ev_flags, x
    and #FLAG_ESPERA
    bne encontrado
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
encontrado:
    ; Se desmarca antes de saber si hay con qué correr, igual que el
    ; `ClearWaitingForegroundExecution` de `Game_Map::Update`, que corre
    ; siempre. Si la página no compiló, el evento pierde el turno; y si es
    ; automática, el barrido del cuadro que viene lo vuelve a marcar.
    lda ev_flags, x
    and #(FLAG_AUTO)            ; deja sólo el de automática
    sta ev_flags, x
    dec esperando_n
    phx
    jsr pagina_desde_eleg
    bne con_pagina
    rep #$20
.a16
    txa
    sta ev_buscado
    sep #$20
.a8
    jsr buscar_pagina_de_evento
con_pagina:
    plx
    lda elegida_hay
    beq buscar_mas
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq buscar_mas              ; la página activa no se pudo compilar
    rep #$20
.a16
    lda elegida
    sta cod_ptr
    stz ev_cur
    sep #$20
.a8
    lda elegida + 2
    sta cod_ptr + 2
    rep #$20
.a16
    txa
    sta ev_corriendo            ; para poder remarcarlo cuando termine
    sep #$20
.a8
    lda #1
    sta ev_activo
    rts
buscar_mas:
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
.endproc

; Lo contrario de `marcar_esperando`, con la misma cuenta.
.proc desmarcar_esperando
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_ESPERA
    beq no                      ; no estaba: no se descuenta de nuevo
    lda ev_flags, x
    and #(FLAG_AUTO)            ; deja sólo el de automática
    sta ev_flags, x
    dec esperando_n
no:
    rts
.endproc

; Marca al evento X como que tiene una página esperando turno. Es
; `Game_Event::ScheduleForegroundExecution`: un bit por evento, no una cola.
; Marcarlo dos veces no lo encola dos veces, que es lo que hacía falta para que
; el barrido de cada cuadro pueda remarcar sin miedo.
.proc marcar_esperando
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_ESPERA
    bne no                      ; ya estaba: no se cuenta de nuevo
    lda ev_flags, x
    ora #FLAG_ESPERA
    sta ev_flags, x
    inc esperando_n
no:
    rts
.endproc

