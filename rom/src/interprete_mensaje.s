.segment "CODE"
.a8
.i16

; --- el intérprete: el mensaje ---------------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; Abre la ventana de mensaje y corta el cuadro. El cursor ya quedó en el
; comando siguiente —el `iny` del lazo— pero `eventos_tick` no vuelve a llamar
; acá hasta que el jugador apriete A.
;
; El operando es el desplazamiento del cuadro de texto dentro del bloque
; `mensajes`, de 16 bits. No es el texto: emitir cada cuadro ya compuesto son
; 240 tiles de 4bpp, o sea 7,5 KB, y los 2895 del juego serían 21 MB. Lo que
; viaja en el cartucho es un byte por letra y lo compone el 65816, que es la
; salida de FF6.
.proc op_message
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

.endproc

