.segment "CODE"
.a8
.i16

; --- el intérprete: el teletransporte --------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

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
    iny                         ; los dos bytes de la Y, que se leyeron sin
    iny                         ; avanzar el cursor
saltar:
    lda #1
    sta salto_hay
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


; `MemorizeLocation` y `RecallToLocation`: como `op_heal`, sólo la entrada. El
; cuerpo es `lugar_recordado`, fuera del banco 0, y vuelve con el acarreo
; prendido si hay que saltar, con el destino ya puesto en `salto_*`: el salto
; termina acá, como el de `op_teleport`.
.proc op_location
    jsl f:lugar_recordado
    bcs saltar
    jmp correr_codigo::otro
saltar:
    jmp op_teleport::saltar

.endproc
