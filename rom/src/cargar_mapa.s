; --- volcado del mapa a la VRAM --------------------------------------------
; Todo por DMA y con la pantalla apagada, que es cuando se puede escribir la
; VRAM sin pelearle al PPU.
; Carga entero el mapa cuyo índice viene en A **de dieciséis bits**: sus datos
; a la VRAM y a CGRAM,
; sus tablas a donde la ROM las busca, la cámara donde arranca el héroe y la
; ventana del tilemap llena. Es todo lo que hay que hacer para cambiar de mapa.
;
; Con la pantalla encendida esto no se puede llamar: escribe VRAM y CGRAM por
; DMA, que fuera del vblank el PPU no deja.
.proc cargar_mapa_sin_eventos
.a16
.i16
    sta mapa_actual             ; para saber si el próximo salto cambia de mapa
    sep #$20
.a8
    jsr giro_limpiar            ; las filas van a ser otras
    jsr animacion_limpiar       ; y la animación de batalla no sigue
    rep #$20
.a16
    stz sub_n                   ; y las sustituciones de tiles se pierden al
    stz sub_refresco            ; cargar un mapa, como en RM2k: ver `sub_n`
    sep #$20
.a8
    lda #0                      ; y el cartel se borra: es el
    sta f:CARTEL_ACTIVA         ; `erase_on_map_change` de Game_Pictures, y
    sta f:CARTEL_LISTO          ; además sus tiles son de un solo mapa
    jsr paquete_cargar          ; el audio del mapa, en el fundido
    rep #$20
.a16
    lda mapa_actual
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por MAPA_STRIDE, que es 128
    sta mapa_ofs
    tax

    ; El reparto de la animación de batalla en este mapa: en qué tile cae su
    ; caja y con qué paleta, o que acá no se dibuja. Necesita `mapa_actual` y
    ; `mapa_ofs`, que acaban de quedar puestos.
    phx
    sep #$20
.a8
    jsr animacion_dibujo_mapa   ; entra y sale con el acumulador en ocho
    jsl f:encuentro_mapa        ; y cada cuántos pasos hay un encuentro acá
    rep #$20
.a16
    plx

    ; Lo que se mira seguido se copia; lo que se usa una vez se lee en el lugar.
    lda f:mapa_tabla + M_MAP_BW, x
    sta mapa_ancho
    asl a
    sta mapa_cw                 ; el ancho en celdas de 8x8 es el doble
    lda f:mapa_tabla + M_MAP_BH, x
    sta mapa_alto
    asl a
    sta mapa_ch
    lda f:mapa_tabla + M_CAM_MAX_X, x
    sta cam_max_x
    lda f:mapa_tabla + M_CAM_MAX_Y, x
    sta cam_max_y
    lda f:mapa_tabla + M_EV_COUNT, x
    ; Todo lo que barre eventos va hasta acá y no hasta `EV_MAX`: con los
    ; ciento veinte, un mapa de cuatro eventos barría ciento dieciséis de más y
    ; eso alcanzaba para perder el cuadro.
    sta ev_total
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; por dieciséis: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "la cuenta de arriba multiplica por dieciséis a mano"
    sta npc_total

    ; Los punteros a las dos tablas que se leen desde la ROM. El segundo apunta
    ; ocho bytes más adelante, que es donde cada bloque guarda su capa de
    ; encima; sumar ocho no puede desbordar el banco porque el acomodo de
    ; `tools/ensamblado/bancos.py` garantiza que la tabla entera entra en uno.
    lda f:mapa_tabla + M_PTR_NPC_POSES, x
    sta poses_ptr
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES, x
    sta bloques_ptr
    clc
    adc #8
    sta bloques8_ptr
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES + 2, x
    sta bloques_ptr + 2
    sta bloques8_ptr + 2
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS + 2, x
    sta pass_ptr + 2
    lda f:mapa_tabla + M_PTR_NPC_POSES + 2, x
    sta poses_ptr + 2

    ; Dónde arranca el héroe: donde diga el registro, salvo que quien llamó haya
    ; dejado una entrada puesta, que es lo que hace una puerta. La cámara se
    ; acomoda antes de llenar la ventana, porque la ventana se llena alrededor
    ; de ella.
    rep #$20
.a16
    lda entrada_x
    cmp #$FFFF
    bne desde_puerta
    lda f:mapa_tabla + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda f:mapa_tabla + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra puesto

desde_puerta:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida: la próxima carga vuelve al registro

puesto:
    sep #$20
.a8
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA

    ; La cámara corrida vuelve a cero al cambiar de mapa, y de golpe: es lo que
    ; hace `Game_Player::PerformTeleport` con `map_changed`, que le devuelve a
    ; `pan_current` y a `pan_finish` el valor por omisión. Un salto al mismo
    ; mapa no pasa por acá y no la toca, que es también lo que hace RM2k.
    rep #$20
.a16
    stz pan_x
    stz pan_y
    stz pan_dest_x
    stz pan_dest_y
    stz pan_px
    stz pan_py
    sep #$20
.a8

    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    jsr load_ruta_graficos
    jsr load_ev_pos             ; y dónde arranca cada evento, con o sin gráfico
    stz refresco
    ; Antes del refresco, no después: las marcas del mapa anterior no valen
    ; nada acá —sus índices de evento apuntarían a otros eventos— y el refresco
    ; es el que vuelve a prender el `FLAG_AUTO` de los que corresponda.
    jsr limpiar_esperas
    jsr limpiar_paralelos
    jsr rutas_de_pagina         ; y las rutas propias de las páginas activas
    ; La tabla de actores es de este mapa, así que dónde caen las poses del
    ; líder cambia al cambiar de mapa aunque el grupo sea el mismo.
    jsr elegir_grafico_heroe
    jsr limpiar_tilemaps        ; lo que `fill_window` no pisa, del mapa de antes
    jsr fill_window             ; deja listo tira_paso_col, que el otro usa
    jsr load_ventana            ; tiles, paleta, tilemap propio y tablas de HDMA
    jsr init_hero_ptr

    ; El tinte es estado del juego, no del mapa: sobrevive al teletransporte.
    ; Las paletas que se acaban de subir son las del cartucho, sin teñir, así
    ; que se vuelven a teñir acá. Con el tinte neutro la cuenta es i*100/100 y
    ; deja los colores donde estaban, así que no hace falta preguntar si hay
    ; tinte: el camino es siempre el mismo.
    jsr aplicar_tinte
    stz destello_listo          ; lo que hubiera en `pal_buf` ya no
                                ; es de este mapa; el cuadro que viene lo
                                ; vuelve a armar si el destello sigue
    jsr subir_tinte             ; la pantalla está apagada: va ya
    rts
.endproc

; Y esto es lo que hay que llamar: carga el mapa y le corre los eventos
; automáticos.
;
; Si un evento pide un teletransporte, el ciclo se repite acá y no adentro del
; intérprete. Llamar a cargar_mapa desde el intérprete sería recursión, y dos
; mapas que se apuntan entre sí la harían infinita: la pila se va al fondo y la
; consola hace cualquier cosa. El tope de vueltas está por la misma razón, para
; el caso en que se apunten con un ciclo más largo.
.proc cargar_mapa
.a16
.i16
    pha                         ; el índice del mapa, que lo de abajo pisaría
    sep #$20
.a8
    lda #SALTOS_MAX
    sta saltos_restantes        ; con stx serían dos bytes y pisaría el de al lado
    rep #$20
.a16
    pla
    jsr cargar_mapa_sin_eventos
    rts
.endproc

; El tinte que haya pedido un evento, con la pantalla apagada mientras dura.
;
; CGRAM no acepta escrituras con el PPU dibujando, así que esto no puede correr
; en cualquier momento. Se intentó primero meterlo en `flush_video`, que corre en
; el vblank, y no entra: `aplicar_tinte` arma tres tablas de canal de treinta y
; dos entradas y sube tres paletas por DMA. Lo que se pasaba del vblank caía con
; el PPU dibujando, y el resultado era un tinte a medias distinto cada vez —una
; vez la capa de encima y un sprite, otra vez el fondo con el héroe en negro y
; los NPCs sin teñir—.
;
; Y esto la tanda no lo cobra: snes9x **acepta** las escrituras a CGRAM con el
; PPU dibujando y mednafen no, así que un tinte roto puede dar verde en las
; sesenta comparaciones y verse mal en la consola. Cuando algo de CGRAM o VRAM
; anda acá adentro y no en el hardware, ésta es la primera sospecha.
;
; La otra salida que se probó —apagar la pantalla a mitad del cuadro, escribir
; el tinte y volver a prenderla— es otra trampa de las que el emulador tapa: en
; la consola son líneas negras mientras dura la cuenta, y en el emulador un
; cuadro teñido de la mitad para abajo. La vio la sacudida de pantalla, que es
; la primera receta que compara cuadro por cuadro.
;
; Apagar la pantalla es lo que ya hace el teletransporte —`cargar_lo_pedido`—
; por la misma razón. Cuesta un cuadro en negro, que en RM2k tampoco desentona: el
; motor original funde a negro en las transiciones.
.proc tinte_de_evento
.a8
.i16
    lda tinte_pendiente
    beq nada
    stz tinte_pendiente
    jsr aplicar_tinte           ; a la sombra; CGRAM se escribe en el vblank
nada:
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
    ; componerse, que es lo único que la hace coincidir cuadro a cuadro con la
    ; referencia: allá la ventana se dibuja de golpe y acá tarda entre nueve y
    ; diecinueve cuadros en componerse. Con una pausa de 61 la composición
    ; termina mucho antes, así que en pantalla se ve lo mismo.
    ;
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
    ; sería un cuadro de diferencia contra la referencia.
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
    ; cadena de teletransportes terminó y el presupuesto se repone. Es el
    ; alcance que el tope tiene en la referencia, donde `saltos` es local a
    ; `entrar_al_mapa` y se reinicia en cada entrada.
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
    ; se cambia de mapa. Es lo que hace la referencia, donde `saltos` es local
    ; a `entrar_al_mapa` y sólo lo baja el lazo que entra a un mapa nuevo; un
    ; salto al mismo mapa no lo toca.
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

; Se acabó: algo que no puede pasar pasó. A trae el código, que queda en
; `panico` para que una prueba de estado pueda decir cuál fue.
;
; No hay `printf` en una SNES y volver de acá no tiene sentido —el estado ya es
; inconsistente—, así que lo que queda es que se vea: la pantalla parpadea entre
; negro y pleno para siempre. Es feo a propósito. Lo que se quiere evitar es lo
; contrario, que el juego siga andando como si nada y el error aparezca media
; hora después convertido en otra cosa.
.proc entrar_en_panico
.a8
.i16
    sta panico
    sei                         ; ni siquiera el vblank: nada más va a pasar
lazo:
    ldx #$2000
espera_prendido:
    dex
    bne espera_prendido
    lda #$0F
    sta INIDISP
    ldx #$2000
espera_apagado:
    dex
    bne espera_apagado
    lda #$80
    sta INIDISP
    bra lazo
.endproc

; Arranca un fundido de teletransporte. A trae qué hay que hacer cuando la
; pantalla llegue a negro; el mapa, si hace falta, ya está en `fundido_mapa`.
.proc empezar_fundido
.a8
.i16
    sta fundido_que
    lda #1
    sta fundido
    ; El reloj del fundido son **vueltas del lazo**, o sea ticks, y no cuadros
    ; de hardware: así el fundido dura FUNDIDO_TOTAL ticks tarde lo que tarde la
    ; carga del mapa adentro del negro. La referencia lo contaba igual, con un
    ; contador que subía una vez por cuadro de mundo; ya no está.
    ;
    ; Estuvo contando `boot_cuadros` —cuadros de hardware— desde que la carga
    ; empezó a tardar seis o siete cuadros adentro de una sola vuelta: contando
    ; vueltas el fundido duraba eso de más **en cuadros**, y el arnés, que
    ; contaba cuadros, quedaba corrido. Desde el 2026-09-08 el arnés cuenta
    ; ticks —ver `vueltas`— así que el reloj vuelve a ser el mismo de los dos
    ; lados y el que absorbe el atraso es el reloj de pared.
    lda vueltas
    sta fundido_base
    rts
.endproc

; Un cuadro del fundido. Devuelve A distinto de cero mientras el juego tenga que
; quedarse quieto, que es todo lo que dura.
;
; RM2k congela la escena entera mientras la transición corre: `Scene::MainFunction`
; ve `IsAsyncPending()` y llama a `Player::Update(false)`, que no actualiza nada.
; Acá es lo mismo por omisión: el lazo principal se saltea el intérprete, al
; héroe, los eventos, el cronómetro y todo lo que mueva algo. Lo que sigue
; corriendo es la música, que en RM2k tampoco se corta.
.proc fundido_tick
.a8
.i16
    lda fundido
    beq no_hay
    lda vueltas                 ; el byte bajo alcanza: el fundido dura 70
    sec
    sbc fundido_base
    cmp #FUNDIDO_TOTAL
    bcs terminar
    cmp #FUNDIDO_CARGA
    bcc rampa                   ; todavía se está apagando
    pha
    jsr cargar_lo_pedido        ; una sola vez: se apaga solo
    pla
rampa:
    ; El brillo de este cuadro. Bajando, la rampa se lee al revés.
    cmp #FUNDIDO_RAMPA
    bcs subiendo
    eor #$FF
    clc
    adc #FUNDIDO_RAMPA          ; FUNDIDO_RAMPA - 1 - t
    bra en_la_rampa
subiendo:
    sec
    sbc #(FUNDIDO_CUADROS + FUNDIDO_NEGRO)
    bcs en_la_rampa             ; pasada la carga: la rampa de vuelta
    lda #0                      ; el negro del medio
    sta brillo
    bra sigue
en_la_rampa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda fundido_rampa, x
    sta brillo
sigue:
    lda #1                      ; el juego sigue congelado
    rts
terminar:
    stz fundido
    lda #BRILLO_MAX
    sta brillo
no_hay:
    lda #0
    rts
.endproc

; El tema que prende el mapa al que se entra, entre `mapa_tema_callar` y el
; final de la carga, o $FF si no hay que prender nada. En la RAM lejana porque
; la BSS del banco 0 está llena.
TEMA_DEL_MAPA = $7E6100

; Lo que el mapa al que se entra le hace a la música, que es el
; `Game_Map::PlayBgm` de easyrpg: su tema, si trae uno —`mapa_tema`, que ya
; resolvió la herencia del árbol—. Vuelve con A en el tema que hay que prender
; cuando el mapa esté cargado, o $FF si no hay que tocar nada, y en ese caso
; lo que sonaba sigue.
;
; No se toca nada en dos casos:
;
; * `mapa_tema` en $FF: el mapa no trae tema, o es el `music_type` 1, "lo
;   decide un evento". También un tema más allá de `TEMA_TOTAL`, igual que
;   hace `op_bgm`.
; * **el tema es el que ya está sonando**. `Game_System::BgmPlay` con el mismo
;   nombre no lo reinicia: pasar de un mapa de los Rat Tracks al otro no
;   vuelve `KSSMKEND` al principio. Con una salvedad, que es la suya también:
;   si se estaba apagando por un `FadeOutBGM` —su `music_stopping`— sí
;   arranca de cero.
;
; "Está sonando" no es sólo `music_apagada` en cero: con pista de MSU-1 el
; SPC700 está callado a propósito y `music_apagada` vale 1. Por eso se mira
; `MSU_SUENA` antes, que es lo mismo que hace `op_fade_bgm`.
;
; Si hay que cambiar, se calla acá, con la pantalla ya negra: el MSU-1 se para
; y el SPC700 suelta las voces, como en `batalla_bgm`.
.proc mapa_tema_callar
.a8
.i16
    ldx fundido_mapa
    lda f:mapa_tema, x
    cmp #TEMA_TOTAL
    bcs nada                    ; $FF, o uno que el cartucho no lleva
    pha
    lda bgm_fundido
    bne cambia                  ; se estaba apagando: vuelve a empezar
    lda f:MSU_SUENA
    bne suena
    lda music_apagada
    bne cambia
suena:
    lda tema_actual + 1
    bne cambia
    pla
    cmp tema_actual
    bne cambia_ya
nada:
    lda #$FF
    rts
cambia:
    pla
cambia_ya:
    pha
    jsr msu_parar
    lda #$FF
    jsr batalla_bgm             ; callar: las voces sueltan
    pla
    rts
.endproc

; Lo que el fundido tiene que hacer en su primer cuadro negro: cargar el mapa,
; o mover al héroe si el salto era al mismo. Se hace una vez y se apaga.
;
; La pantalla se pone en blanking forzado a mano en vez de esperar al vblank:
; `cargar_mapa` escribe VRAM y CGRAM por DMA y con el PPU dibujando esas
; escrituras se pierden. No se ve, porque el brillo ya viene en cero.
.proc cargar_lo_pedido
.a8
.i16
    lda fundido_que
    beq listo
    pha
    lda #$80
    sta INIDISP
    stz brillo                  ; y que el vblank que viene lo deje en negro
    pla
    cmp #FUNDIDO_MISMO
    bne carga
    jsr mover_heroe_a
    bra hecho
carga:
    ; El tema del mapa nuevo se decide **antes** de cargarlo, porque si cambia
    ; hay que callar el que suena antes de que `paquete_cargar` arme el
    ; paquete: ése deja quietas las muestras del tema que dice estar sonando,
    ; y el que se va a prender las necesita en su lugar. Ver `mapa_tema_callar`.
    pha
    jsr mapa_tema_callar
    sta f:TEMA_DEL_MAPA
    pla
    cmp #FUNDIDO_PUERTA
    bne salto
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa             ; el del arnés: reinicia el tope de saltos
    sep #$20
.a8
    ; El héroe aparece quieto en la celda de entrada. Esto no le hace falta a
    ; ningún salto del juego —`advance_step` sólo dispara un teletransporte con
    ; el paso ya terminado, y `move_hero` recalcula `moving` en el primer cuadro
    ; vivo— pero acá la partida llega desde afuera, con la RAM en cualquier
    ; estado, y arrancar a mitad de un paso no es lo que la prueba pidió.
    stz step_left
    stz moving
    bra prender
salto:
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa_sin_eventos
    sep #$20
.a8
    ; Y los eventos automáticos del mapa nuevo, a la cola. La página que pidió
    ; el salto sigue corriendo —su código está en la ROM y el cursor quedó
    ; guardado— así que éstos arrancan recién cuando ella termine, que es el
    ; orden de RM2k: `Game_Interpreter_Map::OnMapChange` no toca la pila del
    ; intérprete, sólo los ids de evento.
    ;
    ; Antes no se marcaban nunca. El comentario decía que se encolaban "cuando
    ; ésta termine" y no lo hacía nadie: después de un teletransporte, los
    ; eventos del mapa de destino no corrían jamás. Nada lo veía porque la única
    ; prueba que teletransportaba miraba el tinte, que lo pone el mapa de origen.
    ; Hoy lo hace `cargar_mapa_sin_eventos`, adentro de su refresco.
prender:
    ; Y el tema del mapa, con el paquete ya subido: sus muestras vinieron en
    ; él. Va antes de que corra ninguna página del mapa nuevo, así que un
    ; `PlayBGM` de un evento automático le gana, que es el orden de RM2k:
    ; `Game_Map::PlayBgm` corre al armar el mapa, antes que sus eventos.
    lda f:TEMA_DEL_MAPA
    cmp #$FF
    beq hecho
    jsr music_start
hecho:
    stz fundido_que
    ; Y OAM, que si no se queda con la del mapa que se dejó. El lazo no la
    ; rearma mientras el fundido dura —`build_oam` es de las cosas que se
    ; saltea— así que la rampa de vuelta iría dibujando el mapa nuevo con los
    ; sprites viejos. No es teórico: son los mil y pico de pixeles que la
    ; referencia cobró la primera vez que se comparó adentro de un fundido.
    jsr build_oam
listo:
    rts
.endproc

; Mueve al héroe a (entrada_x, entrada_y) sin tocar el mapa. Es lo que hace un
; teletransporte que no cambia de mapa: la tabla de eventos, sus posiciones, las
; rutas que estén corriendo y las páginas encoladas siguen como estaban.
.proc mover_heroe_a
.a8
.i16
    rep #$20
.a16
    lda entrada_x
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida
    sep #$20
.a8
    stz step_left               ; un paso a mitad de camino se corta
    stz moving
    jsr menu_olvidar            ; y un pedido de menú también: `MoveTo`
    jsl f:encuentro_mover       ; y lo caminado, que es lo otro que borra
    jsr follow_camera
    jsr fill_window             ; la cámara saltó: el tilemap se llena de nuevo
    jsr init_hero_ptr
    rts
.endproc

