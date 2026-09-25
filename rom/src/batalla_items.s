; --- usar un ítem en la pelea ---------------------------------------------
;
; `Game_BattleAlgorithm::Item` con lo que este port sabe hacer: las medicinas
; que recuperan HP. Qué entra en la lista y cuánto cura no se decide acá sino
; en `batalla.item_usable_en_batalla` y `batalla.curacion`, que es el modelo con
; el que `pruebas/rpgmaker/test_batalla.py` predice el HP exacto; el conversor emite el
; resultado en `item_batalla`, `item_cura_rate` e `item_cura_hp`.
;
; Todo esto corre con el banco de datos en $7E, así que **el inventario se lee
; con direccionamiento absoluto**: `FAR_ITEMS` vive en ese banco y en él las
; direcciones son las mismas. Las tablas del cartucho van con `f:`.

; La lista de lo que se puede usar: un `k` por byte en `BA_ITEM_LISTA` y
; cuántos en `BA_ITEM_N`. Recorre los ítems que la ROM conoce en el orden del
; conversor, que es el del número de RM2k, como `Game_Party`.
.proc ba_items_lista
.a8
.i16
    lda #0
    sta BA_ITEM_N
    sta BA_S0                   ; el `k` que se mira
otro:
    lda BA_S0
    cmp #ITEMS_ROM
    bcs listo
    lda BA_S0
    jsr ba_ax
    lda f:item_batalla, x
    beq siguiente
    lda BA_S0
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x            ; su número de RM2k
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x            ; cuántos hay en el inventario
    beq siguiente
    lda BA_ITEM_N
    jsr ba_ax
    lda BA_S0
    sta BA_ITEM_LISTA, x
    inc BA_ITEM_N
    lda BA_ITEM_N
    cmp #BA_ITEM_MAX
    bcs listo
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; El `k` del lugar A de la lista. Sólo A y X.
.proc ba_item_de_lista
.a8
.i16
    jsr ba_ax
    lda BA_ITEM_LISTA, x
    rts
.endproc

; Uno menos en el inventario del `k` que trae A. Es lo que hace RM2k al
; elegirlo y no al usarlo: si no, el último de un ítem se podría repartir entre
; dos actores en el mismo turno.
.proc ba_item_gastar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    beq listo
    dec a
    sta FAR_ITEMS, x
listo:
    rts
.endproc

; Cuánto cura el `k` de A sobre el combatiente `BA_MBLA`. Entra con A de ocho
; bits y sale con A de dieciséis.
;
;     hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp
;
; topado contra lo que le falta al blanco, que es el `ChangeHp` de easyrpg. El
; producto entra en una palabra porque el conversor corta si algún actor tiene
; más de 655 HP.
.proc ba_item_cura
.a8
.i16
    sta BA_S3                   ; el `k`
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4                   ; el desplazamiento del blanco
    sep #$20
.a8
    lda BA_S3
    jsr ba_ax
    lda f:item_cura_rate, x
    sta BA_T2                   ; el byte del producto
    ldx BA_S4
    rep #$20
.a16
    lda BA_UNO + BA_HPMAX, x
    jsr ba_mul                  ; rate * hp_max, en una palabra
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sta BA_S5
    lda BA_S3
    and #$00FF
    asl a
    tax
    lda f:item_cura_hp, x
    clc
    adc BA_S5
    sta BA_S5                   ; lo que curaría
    ; y lo que le falta al blanco, que es el tope
    ldx BA_S4
    lda BA_UNO + BA_HPMAX, x
    sec
    sbc BA_UNO + BA_HP, x
    cmp BA_S5
    bcc topado
    lda BA_S5
topado:
.a16
    rts
.endproc

; El ítem que eligió el actor `BA_MQUIEN`, sobre `BA_MBLA`: cura, anota cuánto
; y deja el mensaje listo. No tira azar: un ítem no falla ni lo esquiva nadie,
; y **el blanco muerto no se reapunta**, que es lo contrario de un ataque.
.proc ba_item_usar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_ax
    lda BA_ACC_ITEM, x
    sta BA_MITEM
    jsr ba_item_cura
.a16
    sta BA_MCURA
    ldx BA_S4                   ; el desplazamiento del blanco, de `ba_item_cura`
    lda BA_UNO + BA_HP, x
    clc
    adc BA_MCURA
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

