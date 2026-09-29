.segment "FAR"
.a8
.i16

; ===========================================================================
; Los NPC, sus ranuras de ruta y la OAM, desde el banco 1
; ===========================================================================
;
; Lo que corre por cada evento que anda, o por cada fila de NPC, en cada
; cuadro o en cada paso que empieza. En la carrera —cuarenta autos, cinco que
; andan— esto se llevaba casi cien líneas de las 262 del cuadro, y el banco 0
; no tenía lugar para hacerlo más rápido: vive acá, en el espejo rápido, y los
; de allá entran con `jsl f:... + RAPIDO`. Ver
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.

; --- la fila de un NPC que cambió, a su lugar -------------------------------
;
; Deja la fila `npc_fila` donde le toca ahora, con la tabla ya ordenada, y
; `npc_fila` en su lugar nuevo. El orden es el de RM2k: mayor Y —que va
; adentro de la clave, junto con la capa—, después mayor X, y después mayor id.
; Los tres desempates hacen falta porque un evento que camina cambia de fila
; todo el tiempo y empata con cualquiera; con NPCs quietos casi nunca se
; notaba.
;
; Sólo se mueve la que cambió: la Y cambia de a dos pixeles por cuadro, y
; ordenar la tabla entera todos los cuadros costaría lo mismo aunque no se
; moviera nadie. Hasta el 2026-09-27 se movía de a un lugar, intercambiando
; las dos filas enteras en cada uno; en la carrera un auto que cambia de carril
; pasa de una vez a los siete u ocho que van por el de al lado, y cinco autos
; que arrancan su paso en el mismo cuadro sumaban treinta líneas. Ahora se
; busca primero hasta dónde va, comparando con la clave de ella, y las del
; medio se corren todas juntas con un `mvn`/`mvp`: el mismo orden al final,
; que es el que dejaban los intercambios uno por uno.
;
; Pisa `temp` y `cmp_a`, y X e Y.
.proc acomodar_lejos
.a8
.i16
    rep #$20
.a16
    ldx npc_fila
    lda npc_buf + 4, x
    sta temp                    ; su clave: la capa y la Y
    lda npc_buf + 0, x
    sta temp + 2                ; su X
    lda npc_buf + 8, x
    and #$00FF
    sta cmp_a                   ; su evento
    ; ¿Sube? Mientras vaya antes que la de arriba.
    txy
subir:
    cpy #$0000
    beq tope_arriba
    lda temp
    cmp npc_buf + 4 - NPC_STRIDE, y
    bne s_por_clave
    lda temp + 2
    cmp npc_buf + 0 - NPC_STRIDE, y
    bne s_por_clave
    lda npc_buf + 8 - NPC_STRIDE, y
    and #$00FF
    cmp cmp_a
    bcs tope_arriba             ; la de arriba tiene el id mayor o igual
    bra s_pasa
s_por_clave:
    bcc tope_arriba             ; la de arriba va antes
s_pasa:
    tya
    sec
    sbc #NPC_STRIDE
    tay
    bra subir
tope_arriba:
    cpy npc_fila
    beq no_sube
    ; Sube a Y: la fila, aparte; las de Y a la suya, un lugar abajo; y la
    ; fila en Y.
    sty cmp_a                   ; adónde va (su evento ya no hace falta)
    jsr apartar
    phb
    lda npc_fila
    sec
    sbc cmp_a                   ; cuántos bytes se corren
    dec a
    pha
    lda npc_fila
    clc
    adc #.loword(npc_buf) - 1
    tax                         ; el último de los que se corren
    adc #NPC_STRIDE             ; el acarreo quedó en cero
    tay                         ; y adónde va
    pla
    mvp #^FAR_LARGO, #^FAR_LARGO
    plb
    ldx cmp_a
    jsr volver
    sep #$20
.a8
    rtl
.a16
no_sube:
    ; ¿Baja? Mientras la de abajo vaya antes que ella.
bajar:
    tya
    clc
    adc #NPC_STRIDE
    cmp npc_total
    bcs tope_abajo
    tax
    lda npc_buf + 4, x
    cmp temp
    bne b_por_clave
    lda npc_buf + 0, x
    cmp temp + 2
    bne b_por_clave
    lda npc_buf + 8, x
    and #$00FF
    cmp cmp_a
    beq tope_abajo              ; el mismo id: no pasa
    bcc tope_abajo              ; la de abajo tiene el id menor
    bra b_pasa
b_por_clave:
    bcc tope_abajo              ; la de abajo va después
b_pasa:
    txy
    bra bajar
tope_abajo:
    cpy npc_fila
    beq listo
    sty cmp_a
    jsr apartar
    phb
    tya
    sec
    sbc npc_fila                ; cuántos bytes se corren
    dec a
    pha
    lda npc_fila
    clc
    adc #.loword(npc_buf)
    tay                         ; adónde van: donde estaba ella
    adc #NPC_STRIDE
    tax                         ; y de dónde: la que le seguía
    pla
    mvn #^FAR_LARGO, #^FAR_LARGO
    plb
    ldx cmp_a
    jsr volver
listo:
    sep #$20
.a8
    rtl

; La fila `npc_fila`, aparte en `NPC_FILA_APARTE`; y de vuelta en la X.
.a16
apartar:
    ldx npc_fila
    .repeat ::NPC_STRIDE / 2, k
    lda npc_buf + k * 2, x
    sta f:NPC_FILA_APARTE + k * 2
    .endrepeat
    rts
volver:
    .repeat ::NPC_STRIDE / 2, k
    lda f:NPC_FILA_APARTE + k * 2
    sta npc_buf + k * 2, x
    .endrepeat
    stx npc_fila
    rts
.endproc
.assert .bankbyte(npc_buf) = 0 && .loword(npc_buf) < $2000, error, "acomodar_lejos corre las filas en el banco $7E: npc_buf tiene que estar en la RAM baja"

; --- si alguna fila impone sus bits de paso --------------------------------
;
; `pasa_hay` recién cargada la tabla de NPCs: uno si alguna fila trae +15
; distinto de $FF. Corre una vez por mapa.
.proc pasa_mirar
.a8
.i16
    stz pasa_hay
    ldy #$0000
otra:
    cpy npc_total
    beq listo
    lda npc_buf + 15, y
    cmp #$FF
    beq :+
    sta pasa_hay
:
    rep #$21
.a16
    tya
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
    rtl
.endproc

; --- los objetos, escondidos ------------------------------------------------
;
; Todos los objetos arrancan escondidos, y `build_oam` lo hace al empezar cada
; cuadro. Un objeto de 32 de alto en la fila 224 ocupa de la 224 a la 255, o
; sea entero fuera de las 224 que se ven, y sin darle la vuelta al contador.
;
; Desenrollado y en el banco 1 —en el espejo rápido—, porque el lazo de a un
; objeto que había en el banco 0 se llevaba quince líneas de cada cuadro, en
; todos los mapas: un cuarto de lo que le sobraba a la carrera. Así son unas
; cuatro. Ver workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
.proc oam_esconder
.a8
.i16
    ldx #$0000
grande:
    lda #$E0
    .repeat 16, k
    sta oam + 1 + k * 4, x      ; la Y de cada objeto
    .endrepeat
    rep #$21                    ; M en dieciséis y el acarreo en cero
.a16
    txa
    adc #16 * 4
    tax
    sep #$20
.a8
    cpx #512
    bne grande
    ; La tabla chica: dos bits por objeto, el alto dice si es grande. Sólo el
    ; objeto 0 lo es; el resto quedan chicos y escondidos igual.
    rep #$20
.a16
    .repeat 16, k
    stz oam_high + k * 2
    .endrepeat
    sep #$20
.a8
    lda #$02
    sta oam_high                ; objeto 0: tamaño grande
    rtl
.endproc

; --- las ranuras de ruta ------------------------------------------------------

; La ranura de ruta X —en bytes, por RUTA_EV_STRIDE— acaba de ser del evento
; A: se anota en su estado de paralelo, `PAR_RANURA`, para que `un_paralelo`
; no tenga que buscarla. Es de los dos lugares que dan una ranura
; —`ruta_para_evento` y `aplicar_paginas`—, y vive acá por el banco 0. No toca
; A, X ni Y.
.proc ranura_anotar
    php
    rep #$30
.a16
.i16
    pha
    phx
    phy
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_BYTES
    tay
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; de bytes a número de ranura
    inc a
    tyx
    sep #$20
.a8
    sta f:FAR_LARGO + FAR_PAR_ESTADO + PAR_RANURA, x
    rep #$20
.a16
    ply
    plx
    pla
    plp
    rtl
.endproc
.assert RUTA_EV_STRIDE = 32, error, "ranura_anotar divide por RUTA_EV_STRIDE con cinco lsr"

; La fila de `npc_buf` del evento de la ranura de ruta X, en Y, o $FFFF si no
; tiene. Es `npc_de_evento` para `refrescar_npc`, que la pide por cada evento
; que anda y en cada cuadro: la búsqueda recorre las filas desde la primera, y
; en un mapa con cuarenta eventos eran cuatro líneas por cada uno.
;
; La fila se recuerda en el +19 de la ranura, más uno, y se cree sólo si
; sigue siendo de ese evento: las filas se reordenan cuando dos eventos se
; cruzan en Y (`acomodar_npc`), y una ranura recién tomada trae lo que haya
; quedado. Si no, se busca y se anota. No toca X; A se pierde.
.proc npc_de_ranura
.a8
.i16
    lda ruta_ev + 19, x
    beq buscar
    dec a
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a                       ; por NPC_STRIDE
    tay
    sep #$20
.a8
    cpy npc_total
    bcs buscar                  ; fuera de la tabla: un resto
    lda npc_buf + 8, y
    cmp ruta_ev + 0, x
    beq listo
buscar:
    lda ruta_ev + 0, x
    sta temp
    ldy #$0000
otra:
    cpy npc_total
    beq no_hay
    lda npc_buf + 8, y
    cmp temp
    beq hallada
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
hallada:
    rep #$20
.a16
    tya
    lsr a
    lsr a
    lsr a
    lsr a
    inc a
    sep #$20
.a8
    sta ruta_ev + 19, x
listo:
    rtl
no_hay:
    ldy #$FFFF
    rtl
.endproc
.assert NPC_STRIDE = 16, error, "npc_de_ranura multiplica por NPC_STRIDE con cuatro asl"
.assert NPC_MAX < 255, error, "npc_de_ranura guarda la fila más uno en un byte"
