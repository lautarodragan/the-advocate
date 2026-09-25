.segment "CODE"
.a8
.i16

; `ControlVars`, de a una variable: ranura, operación, clase del operando, y
; a y b de dieciséis bits. Ver OP_VAR en eventos.py. Dieciséis bits con signo,
; dando la vuelta.
.proc op_var
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la operación
    iny
    lda [cod_ptr], y            ; la clase del operando
    iny
    phy                         ; Y -> a; se repone al final
    cmp #VAR_VARIABLE
    beq var_de_variable
    cmp #VAR_AZAR
    beq var_al_azar
    cmp #VAR_OTRO
    beq var_de_otro
    cmp #VAR_PERSONAJE
    bne :+
    jmp var_de_personaje
:
    rep #$20
.a16
    lda [cod_ptr], y            ; una constante
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_variable:
    lda [cod_ptr], y            ; la ranura de donde sale
    jsr var_leer
.a16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_otro:
    lda [cod_ptr], y
    bne var_del_timer
    ; El oro, topado en 32767: la variable es de dieciséis bits con signo.
    lda oro + 2
    bne var_oro_tope
    rep #$20
.a16
    lda oro
    bmi var_oro_tope_16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
.a16
var_oro_tope_16:
    sep #$20
.a8
var_oro_tope:
    lda #$FF
    sta temp + 2
    lda #$7F
    sta temp + 3
    bra var_aplicar
var_del_timer:
    rep #$20
.a16
    lda timer_seg               ; los segundos que le quedan al cronómetro
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_al_azar:
    ; a + x mod (b - a + 1), con x el paso siguiente del xorshift y el módulo
    ; con el divisor de ocho bits del hardware: el conversor no deja pasar un
    ; rango de más de 255.
    jsr azar_siguiente
    sta WRDIVL                  ; el dividendo, de dieciséis
    lda [cod_ptr], y            ; a
    sta temp + 2
    iny
    iny
    lda [cod_ptr], y            ; b
    sec
    sbc temp + 2
    inc a                       ; b - a + 1
    sep #$20
.a8
    sta WRDIVB                  ; arranca: dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL                  ; el resto
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_aplicar:
    ; `temp + 2` es el operando; según la operación, se pone tal cual o se
    ; suma o resta a lo que la variable tenía.
    lda temp + 1
    beq var_pone
    lda temp
    jsr var_leer                ; A = lo que tenía, de dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 1
    cmp #VAR_SUMAR
    beq var_suma
    rep #$20
.a16
    pla
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    bra var_pone
var_suma:
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_pone:
    lda temp
    jsr var_escribir            ; y el refresco, si la ranura lo pide: las
                                ; páginas que miran esta variable pueden
    ply                         ; cambiar. Ver `var_escribir`
    iny                         ; a y b, cuatro bytes
    iny
    iny
    iny
    jmp correr_codigo::otro

var_de_personaje:
    ; La clase 6: las coordenadas de un personaje, en celdas. `a` es el blanco
    ; —0 el héroe, el índice del evento más uno, el mismo byte que OP_ROUTE— y
    ; `b` dice cuál: PERSONAJE_X o PERSONAJE_Y.
    ;
    ; La celda que se lee es la **viva**: `tile_x`/`tile_y` para el héroe y
    ; `ev_pos_buf` para un evento, que es adonde una ruta forzada, un
    ; ChangeEventLocation o un TradeEventLocations la dejaron. En RM2k es
    ; `character->GetX()`, o sea lo mismo.
    ; No se guarda ninguno de los dos operandos en RAM: la BSS está llena
    ; —dos bytes más y `ld65` avisa que no entra— y no hace falta. El blanco
    ; **por** EV_STRIDE se lleva en X, que acá no la usa nadie, y con el
    ; corrimiento puesto en la dirección: así el héroe queda con X en cero y
    ; distinguirlo es un `cpx`, que no toca el acumulador.
    lda [cod_ptr], y            ; a: el blanco
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; b: cuál coordenada
    cpx #$0000
    beq var_personaje_heroe
    ; Un evento: su celda está en `ev_pos_buf`, indexada por el índice de la
    ; tabla del mapa, que es el blanco menos uno; de ahí el - EV_STRIDE.
    cmp #PERSONAJE_X
    beq var_personaje_ev_x
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 2, x
    bra var_personaje_listo
.a8
var_personaje_ev_x:
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 0, x
    bra var_personaje_listo
.a8
var_personaje_heroe:
    cmp #PERSONAJE_X
    beq var_personaje_heroe_x
    rep #$20
.a16
    lda tile_y
    bra var_personaje_listo
.a8
var_personaje_heroe_x:
    rep #$20
.a16
    lda tile_x
var_personaje_listo:
    sta temp + 2
    sep #$20
.a8
    jmp var_aplicar

.endproc

; `ConditionalBranch` por variable: ranura, clase del valor, comparación, el
; valor de dieciséis bits y el destino si no se cumple. La comparación es con
; signo: después de restar, "menor" es N distinto de V.
.proc op_if_var
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la clase: constante u otra variable
    iny
    lda [cod_ptr], y            ; la comparación
    pha
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; el valor, o la ranura
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> el destino
    lda temp + 1
    beq si_var_contra_constante
    lda temp + 2
    phy
    jsr var_leer
.a16
    ply
    sta temp + 2
    sep #$20
.a8
si_var_contra_constante:
    pla                         ; la comparación
    sta temp + 1
    lda temp
    phy
    jsr var_leer                ; A = la variable, de dieciséis
.a16
    jsr comparar_var
.a8
    ply
    cmp #0                      ; lo que dijo `comparar_var`, que `ply` pisó
                                ; con el cursor: ver `tema_asegurar`
    bne si_var_sigue
    rep #$20
.a16
    lda [cod_ptr], y            ; no se cumple: al destino
    tay
    sep #$20
.a8
    jmp correr_codigo::otro
si_var_sigue:
    iny
    iny
    jmp correr_codigo::otro

.endproc

