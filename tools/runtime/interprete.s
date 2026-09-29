.segment "CODE"

; --- el intérprete de eventos: el lazo y el despacho -------------------------
;
; `correr_codigo` lee un opcode por vuelta y salta a su manejador. Cada
; manejador es su propio `.proc op_*` y está en uno de los `interprete_*.s`
; que main.s incluye detrás de éste, uno por familia. Como el despacho es por
; tabla, dónde está cada uno no le importa al código, con una condición: tiene
; que quedar en el banco de `correr_codigo`, porque `jmp (tabla, x)` salta
; adentro del banco del programa. Mientras todos estén en `CODE` se cumple, y
; lo cuida `test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k`.
;
; Un opcode nuevo toca dos lugares: su número en tools/protocol/events.toml
; —de donde sale, al regenerar con `just protocolo`, su entrada en la tabla del
; despacho— y su `.proc op_x` en el archivo que le toque, con el nombre del
; opcode en minúsculas. El despacho no se toca: si el manejador falta, la tabla
; no ensambla.

; El bucle del intérprete: un opcode por vuelta hasta el FIN.
;
; Y es el cursor del bytecode y tiene que sobrevivir a todo el bucle, así que
; cada `jsr` que sale de acá lo guarda antes de irse. Las rutinas que se llaman
; usan X e Y para lo suyo —poner_switch indexa el bitmap de switches,
; aplicar_tinte recorre tres paletas— y ninguna tiene por qué saber que acá
; significan otra cosa. Sin esto, el primer OP_SWITCH dejaba a Y valiendo el
; número del switch dividido ocho, y lo que se leía como opcode siguiente era
; un byte cualquiera del medio de la página: el bucle cortaba ahí y el resto no
; corría.
.proc correr_codigo
.a8
.i16
    ldy ev_cur                  ; donde quedó el cuadro anterior
otro:
    lda [cod_ptr], y
    iny
    ; Un número que no es un opcode corta la página, igual que OP_DONE y igual
    ; que hacía la cadena de `cmp` que era el despacho hasta el 2026-09-25, que
    ; terminaba en el `stz`. No
    ; debería llegar nunca —el bytecode lo emite el conversor con los mismos
    ; números—, pero llega en cuanto un manejador cuenta mal sus operandos y
    ; Y queda en el medio de una instrucción; sin el tope, ese byte indexaría
    ; más allá de la tabla y saltaría a cualquier lado.
    cmp #EVENT_OPCODE_COUNT
    bcs op_done
    ; `tax` con índices de dieciséis bits copia los dieciséis de C aunque A sea
    ; de ocho, así que el byte de arriba tiene que ser cero: es lo que quedó
    ; del manejador anterior. `xba` / `lda #0` / `xba` lo limpia sin tocar
    ; los anchos, un ciclo y tres bytes menos que `rep` / `and #$00FF` /
    ; `sep`. El `asl` va antes, en ocho bits: el tope de arriba deja el opcode
    ; por debajo de 128 y no se pierde nada.
    ;
    ; X llega pisado a cada manejador —vale el opcode por dos— y A también,
    ; con B en cero; ninguno los lee antes de escribirlos. La cadena no los
    ; tocaba, y eso se revisó siguiendo saltos y `jsr` desde cada manejador y
    ; desde los tres llamadores de `correr_codigo` al volver.
    asl a
    xba
    lda #0
    xba
    tax
    ; `jmp (abs, x)` lee la tabla del banco del programa, que es donde está: el
    ; de datos es el del bytecode (ver `op_shop`) y un `lda tabla, x` leería
    ; otra cosa.
    jmp (manejadores_de_opcode, x)
.endproc

.assert EVENT_OPCODE_COUNT <= 128, error, "el asl de correr_codigo va en 8 bits"

; OP_DONE, y cualquier número que no sea un opcode: se corta la página.
.proc op_done
.a8
.i16
    stz ev_activo
    rts
.endproc

; La entrada k es el manejador del opcode k. La emite tools/protocol/ desde
; events.toml, así que un opcode nuevo no toca esto: el manejador de `OP_X`
; tiene que llamarse `op_x`, y si falta no ensambla. Tiene que estar en el
; banco de `correr_codigo`, que es de donde la lee el `jmp`, y cada manejador
; también: un `.addr` es de dieciséis bits.
manejadores_de_opcode:
    EVENT_HANDLERS
