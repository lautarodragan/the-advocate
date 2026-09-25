.segment "CODE"
.a8
.i16

; `KeyInputProc`: qué tecla apretó el jugador, guardada en una variable. Ver
; OP_KEY en eventos.py, que es donde está el porqué de que la forma que
; espera se emita dos veces.
;
; La que **espera** y no encuentra nada rebobina su propio cursor a este mismo
; opcode y devuelve el control: el cuadro que viene se la vuelve a ejecutar. Es
; lo mismo que hace la referencia devolviendo `(i, 0, None)`, y es lo que evita
; tener que guardar "estoy esperando" en algún lado —el intérprete de un evento
; paralelo son siete bytes y no le sobra ninguno—.
.proc op_key
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
    jmp correr_codigo::otro     ; lo decide la ranura. Ver `var_escribir`

.endproc

.proc op_delay
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

.endproc

