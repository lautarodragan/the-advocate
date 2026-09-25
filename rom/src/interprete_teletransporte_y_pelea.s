.proc op_teleport
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

