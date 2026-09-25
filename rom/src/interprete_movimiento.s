.segment "CODE"
.a8
.i16

; Una ruta forzada de MoveEvent. El primer operando dice sobre quién: 0 es el
; héroe, y cualquier otro número es el índice del evento en la tabla del mapa
; más uno. **No es el id de RM2k**: 39 mapas de este juego tienen huecos en la
; numeración de eventos, y traducir es cosa del conversor.
;
; De todos los comandos de ruta de RM2k acá se aceptan los cuatro de girar, los
; cuatro de mover y la espera: el conversor no emite ningún otro.
;
; face_up/right/down/left son 12, 13, 14 y 15, y nuestras direcciones son
; 0, 1, 2 y 3 en el mismo orden, así que restar doce alcanza.
;
; Los dos caminos se parecen pero no son el mismo, y la diferencia vale la pena:
; la del héroe se **copia** a RAM, y la de un evento se guarda como puntero al
; bytecode. Copiarla existe desde antes y tiene un tope, RUTA_MAX; el puntero no
; lo tiene, porque el código del mapa vive en la ROM y no se va a ningún lado.
.proc op_route
    lda [cod_ptr], y            ; sobre quién
    sta ruta_blanco
    iny
    lda [cod_ptr], y            ; con qué frecuencia
    sta ruta_frec_op
    iny
    lda [cod_ptr], y            ; cuántos comandos trae
    sta ruta_cuantas
    stz ruta_cuantas + 1
    iny
    lda ruta_blanco
    bne op_route_event

    ; --- el héroe: la ruta se copia a RAM y la camina `move_hero`, no el
    ; intérprete: en RM2k `ForceMoveRoute` es asincrónico y la página sigue.
    ; Lo que se corta es la espera —`SetStopCount(0xFFFF)`: la primera orden
    ; corre ya— y nada más: el paso o el salto en curso se terminan, como
    ; allá. Acá se cortaba también el salto, y la referencia no.
    lda ruta_cuantas
    sta temp
    stz ruta_i
    stz ruta_espera
    lda ruta_frec_op
    sta ruta_frec
    ldx #$0000
copiar_orden:
    lda temp
    beq fin_copia
    dec temp
    cpx #RUTA_MAX
    bcs saltear                 ; no entra: se consume pero no se guarda
    lda [cod_ptr], y
    sta ruta, x
    inx
saltear:
    iny
    bra copiar_orden
fin_copia:
    txa                         ; X no pasa de RUTA_MAX, así que el byte alcanza
    sta ruta_n
    jmp correr_codigo::otro     ; `bra` no llega: el lazo quedó lejos

    ; --- un evento: no se copia nada. Se anota dónde empieza la ruta dentro del
    ; bytecode y en qué orden va, y el cursor de la página saltea las órdenes.
op_route_event:
    phy
    jsr ruta_para_evento
    ply
    rep #$20
.a16
    tya
    clc
    adc ruta_cuantas
    tay
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; Planta a un evento en una celda: ChangeEventLocation. Es `MoveTo`, y nada
; más que `MoveTo`: la celda cambia ya y el paso o el salto en curso se cortan
; —`SetRemainingStep(0)`—, la ruta que tuviera sigue con la orden siguiente
; desde acá, y hacia dónde mira no cambia; la dirección la toca sólo RM2k3. La
; cinemática de apertura lo usa seis veces para traer a Core, a Manta y al
; droide a escena.
.proc op_place
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda [cod_ptr], y
    sta ev_pos_buf + 0, x       ; la celda, que es lo que miran las rutas, la
    iny                         ; tecla de acción y el contacto
    iny
    lda [cod_ptr], y
    sta ev_pos_buf + 2, x
    iny
    iny
    sep #$20
.a8
    phy
lugar_plantar:                  ; con Y ya en la pila: ver `op_place_var`
    jsr plantar_evento
    ply
    jmp correr_codigo::otro

.endproc

; `ChangeEventLocation` con la celda en **dos variables**, que es la otra rama
; de `CommandChangeEventLocation`. Lo demás es idéntico a `op_place`: el mismo
; `MoveTo`, o sea la celda cambia ya, el paso en curso se corta y ni la ruta ni
; hacia dónde mira se tocan. Ver OP_PLACE_VAR en eventos.py.
;
; Las dos lecturas van **antes** de escribir ninguna de las dos palabras, como
; en `op_swap`: una variable que se leyera después de haber movido al evento
; ya podría valer otra cosa si es una de las de coordenadas de `ControlVars`.
; En este juego no pasa —el minijuego del mapa 11 las calcula antes— pero es la
; misma regla y no cuesta nada.
;
; `var_leer` no toca X ni `temp`, así que el desplazamiento de la fila se
; calcula una sola vez y sobrevive a las dos lecturas.
.proc op_place_var
.a8
.i16
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    lda [cod_ptr], y            ; la ranura de la x
    sta temp + 1
    iny
    lda [cod_ptr], y            ; y la de la y
    sta temp + 2
    iny
    phy
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    lda temp + 1
    jsr var_leer                ; vuelve con M en dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 2
    jsr var_leer
.a16
    sta ev_pos_buf + 2, x
    pla
    sta ev_pos_buf + 0, x
    sep #$20
.a8
    bra op_place::lugar_plantar

.endproc

; `TradeEventLocations`: los dos eventos se cambian de celda, y cada uno es un
; `MoveTo` como el de `op_place` —la celda, el corte del paso, y el dibujo que
; la sigue—. Las dos celdas se leen antes de escribir ninguna.
.proc op_swap
    lda [cod_ptr], y            ; el primero: el índice más uno
    dec a
    sta trueque_a
    iny
    lda [cod_ptr], y            ; y el segundo
    dec a
    sta trueque_b
    iny
    phy
    rep #$20
.a16
    lda trueque_a
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda trueque_b
    and #$00FF
    asl a
    asl a
    tay
    lda ev_pos_buf + 0, x
    sta celda_x
    lda ev_pos_buf + 2, x
    sta celda_y
    lda ev_pos_buf + 0, y
    sta ev_pos_buf + 0, x
    lda ev_pos_buf + 2, y
    sta ev_pos_buf + 2, x
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    lda trueque_a
    sta temp
    jsr plantar_evento
    lda trueque_b
    sta temp
    jsr plantar_evento
    ply
    jmp correr_codigo::otro

.endproc

