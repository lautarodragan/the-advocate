.segment "CODE"
.a8
.i16

; --- el intérprete: esperar y parar las rutas ------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.
;
; Arrancarlas está en interprete_movimiento.s.

; "Esperá a que terminen las rutas". Si no queda ninguna corriendo no cuesta ni
; un cuadro, que es lo que hace el `while` de `Game_Interpreter::Update`; y si
; queda, el cursor se deja **en el opcode** y se corta el cuadro, así que el
; siguiente vuelve a preguntar. Espera a que no quede **ninguna**, ni la del
; héroe ni la de ningún evento: es `Game_Map::IsAnyMovePending`, y no una espera
; por el evento que se acaba de mandar a caminar.
.proc op_wait_routes
    jsr hay_rutas
    beq op_wait_routes_next
    dey                         ; el cursor vuelve al opcode
    sty ev_cur
    rts
op_wait_routes_next:
    jmp correr_codigo::otro

.endproc

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
.proc op_stop_routes
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
    jmp correr_codigo::otro

.endproc

