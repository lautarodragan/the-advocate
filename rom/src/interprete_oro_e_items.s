.segment "CODE"
.a8
.i16

; `ChangeGold`: suma o resta y recorta a [0, ORO_MAX], que es lo que hace
; `Game_Party::GainGold`. El monto va en tres bytes porque el tope de RM2k son
; 999999 y este juego usa el valor entero.
;
; No hay dónde mostrarlo —el menú no existe— pero sí quién lo pregunta: la rama
; de oro de `ConditionalBranch`.
.proc op_gold
    lda [cod_ptr], y            ; el signo: 0 suma, 1 resta
    sta temp
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; los 16 bits bajos del monto
    sta temp + 2
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y el byte alto
    sta temp + 1                ; el byte alto del monto
    iny
    phy

    lda temp
    bne oro_resta
    ; Sumar: 24 bits, y si se pasa de ORO_MAX queda en ORO_MAX.
    rep #$20
.a16
    lda oro
    clc
    adc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    adc temp + 1
    sta oro + 2
    bra oro_recorta
oro_resta:
    rep #$20
.a16
    lda oro
    sec
    sbc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    sbc temp + 1
    sta oro + 2
    bcs oro_recorta
    ; Se fue abajo de cero: queda en cero.
    rep #$20
.a16
    stz oro
    sep #$20
.a8
    stz oro + 2
    bra oro_listo
oro_recorta:
    ; ¿Se pasó de ORO_MAX? Se compara de 24 bits, el byte alto primero.
    lda oro + 2
    cmp #^ORO_MAX
    bcc oro_listo
    bne oro_tope
    rep #$20
.a16
    lda oro
    cmp #.loword(ORO_MAX)
    sep #$20
.a8
    bcc oro_listo
    beq oro_listo
oro_tope:
    rep #$20
.a16
    lda #.loword(ORO_MAX)
    sta oro
    sep #$20
.a8
    lda #^ORO_MAX
    sta oro + 2
oro_listo:
    ply
    jmp correr_codigo::otro

.endproc

; `ChangeItems`: el ítem de dieciséis bits y cuánto se suma, con signo. Es
; `Game_Party::AddItem`: la cuenta queda en [0, ITEM_MAX]. Y como cambiar
; un ítem puede cambiar qué página está activa, pide el refresco: RM2k hace
; `SetNeedRefresh(true)` tras cada ChangeItems.
.proc op_item
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el ítem
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sta temp + 2                ; el puerto avanza al leer y no se puede leer
    iny                         ; de vuelta: se guarda la dirección
    iny
    sep #$20
.a8
    stz WMADDH
    lda [cod_ptr], y            ; cuánto, con signo
    iny
    sta temp
    lda WMDATA                  ; la cuenta que había
    clc
    adc temp
    bit temp
    bmi item_resto
    ; Sumó: si se pasó de ITEM_MAX —o dio la vuelta— queda en el tope.
    bcs item_tope
    cmp #(ITEM_MAX + 1)
    bcc item_guardar
item_tope:
    lda #ITEM_MAX
    bra item_guardar
item_resto:
    ; Restó: sin acarreo se fue abajo de cero, y queda en cero.
    bcs item_guardar
    lda #0
item_guardar:
    pha
    rep #$20
.a16
    lda temp + 2                ; el puerto avanzó al leer: se vuelve
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    lda #1
    sta refresco
    jmp correr_codigo::otro

.endproc

