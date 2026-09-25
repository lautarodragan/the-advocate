.segment "CODE"
.a8
.i16

; --- el intérprete: Game Over ----------------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `GameOver`: volver al arranque, igual que perder una pelea sin manejador de
; derrota —ver `op_battle_destination`—, y por lo mismo con `jml`: no hay a
; dónde volver.
;
; Antes, lo que `CommandGameOver` pide: **que no haya un mensaje abierto**. Si
; lo hay, espera, como `op_message` con el de otro. El primer plano no llega
; acá con uno abierto —`eventos_tick` no lo llama—; un paralelo sí, y sin esto
; el reinicio se comería el mensaje que otro está mostrando.
.proc op_game_over
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
    jml f:reset

.endproc

