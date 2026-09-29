.segment "CODE"
.a8
.i16

; --- the interpreter: gold and items ---------------------------------------
;
; Opcode handlers: the `correr_codigo` dispatch, in interprete.s, jumps to
; each one with Y on its first operand, and each one returns to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.

; `ChangeGold`: adds or subtracts and clamps to [0, ORO_MAX], which is what
; `Game_Party::GainGold` does. The amount takes three bytes because RM2k's cap
; is 999999 and this game uses the full value.
;
; There is nowhere to show it —the menu does not exist— but there is someone
; who asks for it: the gold branch of `ConditionalBranch`.
.proc op_gold
    lda [cod_ptr], y            ; the sign: 0 adds, 1 subtracts
    sta temp
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; the low 16 bits of the amount
    sta temp + 2
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; and the high byte
    sta temp + 1                ; the high byte of the amount
    iny
    phy

    lda temp
    bne oro_resta
    ; Add: 24 bits, and if it goes past ORO_MAX it stays at ORO_MAX.
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
    ; It went below zero: it stays at zero.
    rep #$20
.a16
    stz oro
    sep #$20
.a8
    stz oro + 2
    bra oro_listo
oro_recorta:
    ; Did it go past ORO_MAX? Compared as 24 bits, high byte first.
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

; `ChangeItems`: the sixteen-bit item and how much is added, signed. It is
; `Game_Party::AddItem`: the count stays in [0, ITEM_MAX]. And since changing
; an item can change which page is active, it asks for the refresh: RM2k does
; `SetNeedRefresh(true)` after every ChangeItems.
.proc op_item
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; the item
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sta temp + 2                ; the port advances on read and cannot be read
    iny                         ; again: the address is saved
    iny
    sep #$20
.a8
    stz WMADDH
    lda [cod_ptr], y            ; how much, signed
    iny
    sta temp
    lda WMDATA                  ; the count there was
    clc
    adc temp
    bit temp
    bmi item_resto
    ; It added: if it went past ITEM_MAX —or wrapped around— it stays at the cap.
    bcs item_tope
    cmp #(ITEM_MAX + 1)
    bcc item_guardar
item_tope:
    lda #ITEM_MAX
    bra item_guardar
item_resto:
    ; It subtracted: with no carry it went below zero, and it stays at zero.
    bcs item_guardar
    lda #0
item_guardar:
    pha
    rep #$20
.a16
    lda temp + 2                ; the port advanced on read: go back
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    lda #1
    sta refresco
    jmp correr_codigo::otro

.endproc

