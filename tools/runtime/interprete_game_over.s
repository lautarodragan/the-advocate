.segment "CODE"
.a8
.i16

; --- el intérprete: Game Over ----------------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `ReturntoTitleScreen` y `GameOver`: el primero vuelve al arranque —la
; pantalla de título, si la ROM la lleva— y el segundo pasa antes por la
; pantalla de Game Over, que es lo mismo que perder una pelea sin manejador de
; derrota: ver rom/src/game_over.s. Los dos con `jml`: no hay a dónde volver.
;
; Comparten todo menos el final, y A alto dice cuál es: `op_return_to_title`
; carga 0 y se saltea el `lda #1` con el byte de un `bit` absoluto, que se
; come los dos bytes que siguen sin tocar A. Es un truco, y está porque en el
; banco 0 cada byte cuenta. `xba` lo guarda en B mientras el resto mira sólo
; el byte bajo.
;
; Antes, lo que `CommandGameOver` y `CommandReturnToTitleScreen` piden: **que
; no haya un mensaje abierto**. Si lo hay, esperan, como `op_message` con el
; de otro. El primer plano no llega acá con uno abierto —`eventos_tick` no lo
; llama—; un paralelo sí, y sin esto el reinicio se comería el mensaje que
; otro está mostrando.
.proc op_return_to_title
    lda #0
    .byte $2C                   ; bit abs: se come el `lda #1` de abajo
.endproc
.proc op_game_over
    lda #1
    xba
    lda par_ev
    cmp #$FF
    beq game_over_ya            ; primer plano
    lda msg_abierto
    ora msg_estado
    ora eleg_activo
    beq game_over_ya
    dey                         ; el cursor vuelve a este mismo opcode
    sty ev_cur
    rts
game_over_ya:
    xba                         ; y la Z, del que era: 0 es volver al título
    beq al_titulo
    jml f:game_over_desde_el_mapa
al_titulo:
    jml f:reset

.endproc

