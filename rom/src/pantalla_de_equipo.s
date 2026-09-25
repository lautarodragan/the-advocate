.segment "FAR"

; --- el equipo y la tienda, fuera del banco 0 -------------------------------
;
; Las dos pantallas son tres kilobytes, y al banco 0 le quedaban doce bytes en
; el cartucho de pruebas. Bajaron acá el 2026-09-19 por la misma razón que la
; pelea y por el mismo camino: se entra con `jsl` a `equipo_pantalla` y a
; `tienda_pantalla`, y lo que necesitan del banco 0 se llama por los puentes
; `ba_t_*`, que ya estaban para la pelea —sólo hicieron falta dos nuevos,
; `ba_t_lista` y `ba_t_armar`—.
;
; **El banco de datos sigue siendo el 0**, a diferencia de la pelea: estas dos
; leen y escriben el escritorio y las tablas del banco 0 con direccionamiento
; absoluto y así siguen funcionando sin tocar nada. Lo que sí cambió es al
; revés: un dato **de acá** leído con absoluto caería en el banco 0. Hay uno
; solo, `mensaje_de`, y va con `f:`; costó una tarde de tienda sin saludo.
;
; No cuesta cuadros: las dos bloquean adentro de la página, `vueltas` no
; avanza mientras se ven, y los dos ciclos de más de cada `jsl` caen en una
; pantalla que espera al control.
;
; `Scene_Equip`: el actor, sus cuatro parámetros, las cinco ranuras con lo que
; tiene puesto; A sobre una ranura muestra la lista de lo que puede ponerse
; ahí —reemplaza a las ranuras mientras dura— con los parámetros que
; quedarían. La línea vacía del final es sacarse lo de la ranura. B vuelve.
; `pantallas.pantalla_equipo` es la referencia, y `pantallas.equipar` la regla.
;   eq_actor     es comp_char      ; el número de actor
;   eq_ranura    es comp_col       ; la ranura marcada, 0 a 4
;   eq_eligiendo es comp_col + 1   ; si se muestra la lista
;   eq_elegido   es comp_fase      ; el lugar del cursor en la lista
;   eq_arriba    es comp_fase + 1  ; y el primero que se ve
;   eq_n         es comp_base      ; cuántos hay en la lista, con la vacía
;   eq_cand      es comp_mask      ; el ítem que marca el cursor, 0 si ninguno
;   eq_suma      es comp_or01      ; un parámetro, mientras se suma
;   eq_param     es comp_or01 + 2  ; cuál
;   eq_s         es comp_or01 + 3  ; la ranura que se mira
;   eq_id        es comp_or23      ; un ítem, dos bytes
;   eq_tmp       es comp_and       ; escritorio de `eq_apuntar`, cuatro bytes

; A: la ranura. Deja apuntada la ventana de la WRAM a esa ranura del actor:
; `FAR_EQUIPO` + actor * 10 + ranura * 2.
.proc eq_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta comp_and                  ; la ranura por dos
    lda comp_char
    and #$00FF
    asl a
    sta comp_and + 2              ; el actor por dos
    asl a
    asl a                       ; por ocho
    clc
    adc comp_and + 2
    clc
    adc comp_and
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: la ranura. Vuelve con el ítem en `eq_id`.
.proc eq_leer
.a8
.i16
    jsr eq_apuntar
    lda WMDATA
    sta comp_or23
    lda WMDATA
    sta comp_or23 + 1
    rts
.endproc

; A: la ranura; `eq_id`: el ítem nuevo.
.proc eq_escribir
.a8
.i16
    jsr eq_apuntar
    lda comp_or23
    sta WMDATA
    lda comp_or23 + 1
    sta WMDATA
    rts
.endproc

; El `k` del ítem de `eq_id`, en X, y Z=1 si es ninguno o uno que la ROM no
; conoce.
.proc eq_k
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    beq ninguno
    cmp #ITEMS_N
    bcs ninguno
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq ninguno8
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
.a16
ninguno:
    sep #$20
.a8
ninguno8:
    lda #0                      ; Z=1
    rts
.endproc

; Cuántos hay en el inventario del ítem `eq_id`, en A.
.proc eq_inv_apuntar
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; Uno más —topado en 99— o uno menos del ítem `eq_id`. A: 1 suma, 0 resta.
.proc eq_inv_mover
.a8
.i16
    pha
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_and
    jsr eq_inv_apuntar
    pla
    beq resta
    lda comp_and
    cmp #ITEM_MAX
    bcs listo
    inc a
    bra escribir
resta:
    lda comp_and
    beq listo
    dec a
escribir:
    sta WMDATA
listo:
    rts
.endproc

; ¿El ítem `eq_id` es un arma a dos manos? Z=0 si sí.
.proc eq_dos_manos
.a8
.i16
    jsr eq_k
    beq no
    lda item_uso, x
    and #8
    rts
no:
    lda #0
    rts
.endproc

; El ítem que tendría la ranura A: el que tiene, o —eligiendo— el que marca
; el cursor si es la ranura elegida, y ninguno en la otra si el arma es a dos
; manos. Es `pantallas.equipar` sin tocar nada. Vuelve en `eq_id`.
.proc eq_efectivo
.a8
.i16
    sta comp_or01 + 3
    lda comp_col + 1
    beq tiene
    lda comp_or01 + 3
    cmp comp_col
    bne otra
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    rts
otra:
    ; Un arma a dos manos saca el escudo; un escudo saca el arma a dos manos.
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_or01 + 3
    cmp #1
    bne no_escudo
    lda comp_col
    bne tiene                   ; no se está eligiendo el arma
    jsr eq_dos_manos
    bne ninguno
    bra tiene
no_escudo:
    lda comp_or01 + 3
    bne tiene                   ; ni escudo ni arma: la de siempre
    lda comp_col
    cmp #1
    bne tiene                   ; no se está eligiendo el escudo
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq tiene                   ; sacarse el escudo no toca el arma
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    bne ninguno
    rts                         ; `eq_id` ya es el arma
tiene:
    lda comp_or01 + 3
    jmp eq_leer
ninguno:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; El parámetro `eq_param` —0 ataque, 1 defensa, 2 espíritu, 3 agilidad— con el
; equipo que dice `eq_efectivo`, en `pant_valor`, topado en [1, 999].
.proc eq_parametro
.a8
.i16
    ; El de su nivel de ahora: `nivel_param`, donde los cuatro de acá van del
    ; 2 al 5. Y se guarda porque `nivel_param` se la lleva y el que llama a
    ; esto no lo espera.
    phy
    rep #$20
.a16
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #2
    tay
    sep #$20
.a8
    lda comp_char
    jsl f:nivel_param
    stx comp_or01
    ply
    lda #0
ranura:
    pha
    jsr eq_efectivo
    jsr eq_k
    beq sin_puntos
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; ocho bytes por ítem
    sta comp_and
    lda comp_or01 + 2
    and #$00FF
    asl a
    clc
    adc comp_and
    tax
    lda f:item_puntos, x
    clc
    adc comp_or01
    sta comp_or01
    sep #$20
.a8
sin_puntos:
    pla
    inc a
    cmp #5
    bcc ranura
    rep #$20
.a16
    lda comp_or01
    bmi uno                     ; con signo: el equipo puede restar
    beq uno
    cmp #1000
    bcc listo
    lda #999
    bra listo
uno:
    lda #1
listo:
    sta comp_dup
    sep #$20
.a8
    rtl
.endproc

; La lista de lo que el actor puede ponerse en `eq_ranura`, como `k` en
; `FAR_ITEM_LISTA`, y al final un $FF que es la línea vacía. Cuántos en
; `eq_n`. Es `pantallas.candidatos`.
.proc eq_lista_armar
.a8
.i16
    stz comp_base
    ldx #1
otro:
    rep #$20
.a16
    txa
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq siguiente
    lda f:item_k, x
    cmp #$FF
    beq siguiente
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; X = k
    sep #$20
.a8
    lda comp_col
    inc a
    cmp item_tipo, x
    bne no_va
    ; ¿Lo puede usar el actor? Un bit por actor, ocho bytes por ítem.
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta comp_and
    lda comp_char
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc comp_and
    sta comp_and                ; el byte; `comp_and` ya no lleva k por ocho
    pla
    and #$0007
    sta comp_and + 2              ; y el bit
    sep #$20
.a8
    ; Con `f:` porque `item_actores` se mudó a RODATA el 2026-09-13: son 496
    ; bytes y el área del banco 0 ya se pasaba por quince antes de las
    ; habilidades. Cuesta un byte y un ciclo por lectura, y esto corre una vez
    ; por ítem al abrir la pantalla de equipo.
    ;
    ; **Por X y no por Y**: el 65816 no tiene `lda long, y`, sólo `long, x`. X
    ; trae el `k` del ítem y lo necesita más abajo, así que va y vuelve por la
    ; pila. El `plx` no deja ninguna bandera mirada: lo que sigue es un `and`.
    ;
    ; El índice sale de `comp_and` y no de Y, y eso no es indistinto: dos ramas
    ; mudaron este mismo código a RODATA por separado, una dejando el byte en Y
    ; —`tay`— y la otra en `comp_and`. En el merge git se quedó con el `sta
    ; comp_and` de una y dejó el `tyx` de la otra en conflicto: juntas
    ; ensamblaban y leían un registro que ya nadie cargaba.
    phx
    ldx comp_and
    lda f:item_actores, x
    plx
    ldy comp_and + 2
    beq bit_listo
correr:
    lsr a
    dey
    bne correr
bit_listo:
    and #1
    beq no_va
    txa                         ; el k, que entra en un byte
    pha
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_base
no_va:
    plx
siguiente:
    inx
    cpx #ITEMS_N
    bcs lista_lista
    jmp otro                    ; los 127 bytes de un `bcc` se quedaron cortos
                                ; al leer `item_actores` larga
lista_lista:
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda #$FF                    ; la línea vacía
    sta WMDATA
    inc comp_base
    rts
.endproc

; El ítem del lugar A de la lista, en `eq_id`: 0 si es la línea vacía.
.proc eq_de_lista
.a8
.i16
    jsl f:ba_t_lista
    cmp #$FF
    beq vacia
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    sta comp_or23
    sep #$20
.a8
    rts
vacia:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Escribe en `eleg_tabla` el nombre del ítem `eq_id`, si la ROM lo conoce, con
; no más de A letras.
.proc eq_nombre
.a8
.i16
    sta comp_dup + 3
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax                         ; 3k, el nombre
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rts
nada:
    lda #255
    sta comp_dup + 3
    rts
.endproc

; La descripción del ítem `eq_id`, en los dos renglones de arriba.
.proc eq_desc
.a8
.i16
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    inc a                       ; 3k + 1
    pha
    lda #PANT_DESC_POS
    sta eleg_tabla
    plx
    phx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rep #$20
.a16
    lda #(PANT_DESC_POS + 128)
    sta eleg_tabla
    plx
    inx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rts
nada:
    rts
.endproc

; La pantalla entera, en el búfer: `pantallas.pantalla_equipo`.
.proc eq_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    stz temp + 1
    ; --- el nombre del actor ---
    rep #$20
.a16
    lda #EQ_ACTOR_POS
    sta eleg_tabla
    lda comp_char
    and #$00FF
    asl a
    tax
    lda actor_txt, x
    tax
    cmp #$FFFF                  ; un actor sin nombre en esta ROM
    sep #$20                    ; `sep` no toca Z
.a8
    beq sin_nombre
    jsl f:ba_t_texto
sin_nombre:
    ; --- la descripción ---
    lda comp_col + 1
    beq la_puesta
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    bra desc
la_puesta:
    lda comp_col
    jsr eq_leer
desc:
    jsr eq_desc
    ; --- los parámetros: ahora y, eligiendo, después ---
    stz comp_or01 + 2
param:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    sta eleg_tabla
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #EQ_TEXTO_PARAM
    tax
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    lda comp_col + 1
    pha
    stz comp_col + 1            ; ahora: lo puesto
    jsl f:eq_parametro
    pla
    sta comp_col + 1
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_VALOR
    sta eleg_tabla
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    lda comp_col + 1
    beq sin_flecha
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_FLECHA
    sta eleg_tabla
    sep #$20
.a8
    lda #$3E                    ; '>'
    jsl f:ba_t_glifo
    jsl f:eq_parametro            ; después: con lo que marca el cursor
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
sin_flecha:
    inc comp_or01 + 2
    lda comp_or01 + 2
    cmp #4
    bcc param
    lda comp_col + 1
    bne lista
    ; --- las ranuras ---
    lda #0
ranura:
    pha
    cmp comp_col
    bne sin_cursor
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    lda #$3E
    jsl f:ba_t_glifo
sin_cursor:
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_TERM
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    rep #$20
.a16
    and #$00FF
    clc
    adc #EQ_TEXTO_RANURA
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    jsr eq_leer
    lda #EQ_RANURA_ANCHO
    jsr eq_nombre
    pla
    inc a
    cmp #5
    bcc ranura
    rts

    ; --- la lista ---
lista:
    lda #0
lista_fila:
    pha
    clc
    adc comp_fase + 1
    cmp comp_base
    bcs lista_listo
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    clc
    adc comp_fase + 1
    cmp comp_fase
    bne sin_cursor_lista
    lda #$3E
    jsl f:ba_t_glifo
sin_cursor_lista:
    pla
    pha
    clc
    adc comp_fase + 1
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq lista_siguiente         ; la línea vacía
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #PANT_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    lda #255
    jsr eq_nombre
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #PANT_DOS_PUNTOS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$3A                    ; ':'
    jsl f:ba_t_glifo
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_numero
lista_siguiente:
    pla
    inc a
    cmp #EQ_LISTA_FILAS
    bcc lista_fila
    rts
lista_listo:
    pla
    rts

; A16 = la posición del parámetro `eq_param`.
param_pos:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    rts
.a8

; A: la ranura. A16 = la posición de su fila.
fila_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; por 128: dos filas de celdas
    clc
    adc #EQ_RANURA_POS0
    rts
.a8

; A: la fila de la lista. A16 = la posición de su fila.
fila_pos_lista:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #EQ_LISTA_POS0
    rts
.a8
.endproc

; A sobre la lista: `pantallas.equipar` con lo que marca el cursor.
.proc eq_equipar
.a8
.i16
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    lda comp_col
    jsr sacar
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq listo
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda #0
    jsr eq_inv_mover            ; uno menos en el inventario
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_col
    jsr eq_escribir
    ; Las dos manos.
    lda comp_col
    bne no_arma
    jsr eq_dos_manos            ; `eq_id` es el arma nueva
    beq listo
    lda #1
    jmp sacar
no_arma:
    cmp #1
    bne listo
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    beq listo
    lda #0
    jmp sacar
listo:
    rts

; A: la ranura. Lo que tiene vuelve al inventario y queda vacía.
sacar:
    pha
    jsr eq_leer
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq vacia
    lda #1
    jsr eq_inv_mover
    stz comp_or23
    stz comp_or23 + 1
    pla
    jmp eq_escribir
vacia:
    pla
    rts
.endproc

; La pantalla de equipo del actor A, hasta que el jugador vuelve con B.
.proc equipo_pantalla
.a8
.i16
    sta comp_char
    stz comp_col
    stz comp_col + 1
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_banco_subir
    jsr eq_componer
    jsl f:ba_t_subir
    jsl f:ba_t_ppu
espera:
    jsl f:ba_t_vblank
    ; El control primero y el DMA después. Al revés, los 1792 bytes duran
    ; unas diez líneas y `read_pad` llegaba con la lectura automática del
    ; control ya terminada: esperaba la del cuadro siguiente, cada vuelta
    ; duraba dos cuadros, y un toque de un cuadro se perdía la mitad de las
    ; veces. Con el control leído, el DMA entra igual en el vblank.
    jsl f:ba_t_pad
    jsl f:ba_t_subir
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    lda comp_col + 1
    beq en_ranuras
    jmp en_lista
en_ranuras:
    lda titulo_flancos
    and #PAD_UP
    beq r_no_arriba
    lda comp_col
    beq espera
    dec comp_col
    jmp recomponer
r_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq r_no_abajo
    lda comp_col
    cmp #4
    bcs espera
    inc comp_col
    jmp recomponer
r_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq r_mira_a
    rtl
r_mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera
    jsr eq_lista_armar
    stz comp_fase
    stz comp_fase + 1
    lda #1
    sta comp_col + 1
    jmp recomponer
en_lista:
    lda titulo_flancos
    and #PAD_UP
    beq l_no_arriba
    lda comp_fase
    beq espera2
    dec comp_fase
    lda comp_fase
    cmp comp_fase + 1
    bcs recomponer
    sta comp_fase + 1
    bra recomponer
l_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq l_no_abajo
    lda comp_fase
    inc a
    cmp comp_base
    bcs espera2
    sta comp_fase
    sec
    sbc comp_fase + 1
    cmp #EQ_LISTA_FILAS
    bcc recomponer
    inc comp_fase + 1
    bra recomponer
l_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq l_mira_a
    stz comp_col + 1
    bra recomponer
l_mira_a:
    lda pad_a
    beq espera2
    lda pad_a_ant
    bne espera2
    jsr eq_equipar
    stz comp_col + 1
recomponer:
    jsr eq_componer
espera2:
    jmp espera
.endproc

