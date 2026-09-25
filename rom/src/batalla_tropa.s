.segment "FAR"

; --- las páginas de evento de la tropa ----------------------------------------
;
; `Game_Interpreter_Battle`: cada tropa trae sus páginas, y una corre cuando
; se cumple su disparador. Es lo que hace andar los sistemas de batalla de los
; personajes —Detect Aura prende el switch 134 y la página de la tropa que lo
; mira dice de qué color es el aura—. El código es el de los mapas y corre en
; el mismo intérprete, por el puente `ba_t_pagina`; lo de acá decide **cuándo**.
;
; La regla sale de easyrpg y no de memoria: `ScheduleNextPage` prueba las
; páginas en orden y arranca la primera que se cumpla y **no haya corrido en
; este turno**; cuando termina, prueba de nuevo, hasta que no quede ninguna. Lo
; de "este turno" lo borra `NextTurn`, que es cuando el grupo terminó de dar
; las órdenes. Y los momentos son tres: antes de pedir las órdenes, antes de
; cada acción y después de la última —ver los que llaman a `ba_pag_probar`—.

; Las páginas de la tropa de esta pelea, desde `BA_TROPA_K`. Una tropa que el
; cartucho no lleva no tiene ninguna.
.proc ba_pag_armar
.a8
.i16
    stz BA_PAG_N
    lda BA_TROPA_K
    cmp #$FF
    beq listo
    jsr ba_ax
    lda f:tropa_pag_n, x
    sta BA_PAG_N
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:tropa_pag_ini, x
    sta BA_PAG_INI
    sep #$20
.a8
    jsr ba_pag_turno
listo:
    rts
.endproc

; `ResetPagesExecuted`: ninguna corrió todavía en este turno.
.proc ba_pag_turno
.a8
.i16
    ldx #0
otra:
    stz BA_PAG_HECHA, x
    inx
    cpx #TROPA_PAG_MAX
    bne otra
    rts
.endproc

; Si hay una página para correr, la deja lista —su código, el cursor en cero,
; anotada como corrida— con la pelea en `BA_M_PAGINA`, y vuelve con A8 en 1.
; Si no, en 0. **La Z vale lo mismo que A**: sale de un `lda` explícito.
;
; Primero `CheckBattleEndConditions`: con un lado entero caído la pelea se
; termina y no corre ninguna. Se lleva `BA_S0`, `BA_T*`, A, X e Y.
.proc ba_pag_probar
.a8
.i16
    lda BA_PAG_N
    beq no
    jsr ba_enemigo_vivo
    cmp #$FF
    beq no
    lda #0
    sta BA_PAG_I
alguien:
    lda BA_PAG_I
    cmp BA_NACT
    bcs no                      ; nadie del grupo en pie
    jsr ba_vivo
    bne hay_grupo
    inc BA_PAG_I
    bra alguien
hay_grupo:
    lda #0
    sta BA_PAG_I
otra:
    lda BA_PAG_I
    cmp BA_PAG_N
    bcs no
    jsr ba_ax
    lda BA_PAG_HECHA, x
    bne siguiente
    jsr ba_pag_cumple
    bne esta
siguiente:
    inc BA_PAG_I
    bra otra
esta:
    lda BA_PAG_I
    jsr ba_ax
    lda #1
    sta BA_PAG_HECHA, x
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_cod, x
    sta BA_PAG_COD
    stz BA_PAG_CUR
    lda #$FFFF
    sta BA_PAG_MSG
    sep #$20
.a8
    lda #1
    sta BA_PAG_ACT
    lda #BA_M_PAGINA
    sta BA_MODO
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si la página `BA_PAG_I` de la tropa se cumple: `AreConditionsMet`, con los
; tres disparadores que la ROM sabe mirar —los demás no llegan acá: el
; conversor no emite esas páginas—. Deja en `BA_PAG_G` su lugar en las tablas
; `tpag_*` y vuelve con Z=0 si se cumple.
.proc ba_pag_cumple
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_I
    and #$00FF
    clc
    adc BA_PAG_INI
    sta BA_PAG_G
    tax
    sep #$20
.a8
    lda f:tpag_flags, x
    sta BA_T2                   ; los disparadores, que sobreviven a los `jsr`
    and #TPAG_SWITCH_A
    beq sin_a
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_a, x
    jsr ba_pag_switch
.a8
    beq no
sin_a:
    lda BA_T2
    and #TPAG_SWITCH_B
    beq sin_b
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_b, x
    jsr ba_pag_switch
.a8
    beq no
sin_b:
    lda BA_T2
    and #TPAG_VARIABLE
    beq si
    ; La variable, `>=` con signo: `Get(variable_id) >= variable_value`.
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_valor, x
    sta BA_T0
    lda f:tpag_var, x
    asl a
    tax
    lda FAR_VARIABLES, x
    sec
    sbc BA_T0
    bvc sin_desborde
    eor #$8000                  ; con desborde, el signo es el contrario
sin_desborde:
    sep #$20                    ; `sep` no toca N
.a8
    bmi no
si:
    lda #1
    rts
no:
.a8
    sep #$20
    lda #0
    rts
.endproc

; A16 el número de switch; vuelve con A8 y Z=0 si está prendido. Es el mismo
; bitmap que mira el mapa, `switches`, en la RAM baja, que con el banco de
; datos en $7E está en su lugar de siempre. Se lleva X e Y.
.proc ba_pag_switch
.a16
.i16
    pha
    lsr a
    lsr a
    lsr a
    tay                         ; qué byte
    pla
    and #$0007
    tax                         ; y qué bit
    sep #$20
.a8
    lda f:mascara, x
    and switches, y
    rts
.endproc

; Un tramo de la página que está corriendo, y lo que sigue: si pidió un
; mensaje, a la pantalla; si terminó, la que siga; y si no queda ninguna, la
; pelea sigue por donde estaba —`BA_PAG_VUELTA`—.
.proc ba_pag_paso
.a8
.i16
otro_tramo:
    jsl f:ba_t_pagina
    rep #$20
.a16
    lda BA_PAG_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne a_la_pantalla
    lda BA_PAG_ACT
    bne a_la_pantalla           ; no terminó y no pidió nada: no pasa con los
                                ; comandos de `TROPA_COMANDOS`, pero si pasara
                                ; sigue el cuadro que viene
    jsr ba_pag_probar
    bne otro_tramo              ; la que sigue, en este mismo cuadro
    lda BA_PAG_VUELTA
    bne a_las_ordenes
    jmp ba_ejecutar
a_las_ordenes:
    lda #BA_M_ORDEN
    sta BA_MODO
a_la_pantalla:
    jmp ba_componer
.endproc

; El mensaje de la página, en los renglones del grupo: ver `BA_PAG_MSG_FILA0`
; en pantallas.py. Lo lee de `mensajes_tropa` con el formato de siempre —la
; cabecera con los renglones y cada renglón con su largo, un byte por letra con
; el ASCII menos 32— y lo escribe con los glifos de la pantalla, cortado a
; `BA_PAG_MSG_ANCHO`. El bloque entra en un banco —lo garantiza el
; conversor—, así que el puntero se avanza con Y y el banco queda fijo.
.proc ba_pag_mensaje
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_MSG
    clc
    adc #.loword(mensajes_tropa)
    sta msg_ptr
    lda #BA_PAG_MSG_POS0
    sta BA_T1
    sep #$20
.a8
    lda #^mensajes_tropa
    sta msg_ptr + 2
    stz temp + 1                ; en blanco
    lda [msg_ptr]
    and #CABECERA_LINEAS
    sta BA_PAG_I                ; los renglones que quedan
    ldy #1
renglon:
    lda BA_PAG_I
    beq listo
    rep #$20
.a16
    lda #BA_PAG_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda [msg_ptr], y            ; el largo
    iny
    sta BA_T0                   ; las letras que le quedan
    stz BA_T2                   ; y las que ya se escribieron
letra:
    lda BA_T0
    beq fin_renglon
    dec BA_T0
    lda BA_T2
    cmp #BA_PAG_MSG_ANCHO
    bcs no_entra                ; se consume y no se dibuja
    inc BA_T2
    lda [msg_ptr], y
    clc
    adc #ITEM_PRIMER_CARACTER
    phy
    jsl f:ba_t_glifo
    ply
no_entra:
    iny
    bra letra
fin_renglon:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_FILA_BYTES
    sta BA_T1
    sep #$20
.a8
    dec BA_PAG_I
    bra renglon
listo:
    rts
.endproc

