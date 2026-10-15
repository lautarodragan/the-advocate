.segment "FAR2"
.a8
.i16

; --- ChangeItems with the item or the amount in a variable -----------------
;
; `OP_ITEM_VAR`, called by `op_item_var` from the interpreter with the data
; bank at 0 and Y on the operands; it leaves Y after them. It lives out of
; bank 0, which has no room to spare: `op_item` keeps the constant case
; there, which is every `ChangeItems` of ABL.
;
; It is `CommandChangeItems` with `OperateValue`: the amount, constant or
; read, is turned around if the command subtracts, and **a value below zero
; does nothing** —RM2k's "add" cannot take items away nor "remove" give
; them, so a variable below zero leaves the inventory as it was—. Then
; `Game_Party::AddItem`: an item out of [1, ITEMS_N) does nothing, and the
; count stays in [0, ITEM_MAX]. The inventory is indexed by the LDB number
; —see `FAR_ITEMS`—, so a number read at run time needs no table.
ITEM_SUBTRACTS     = $01        ; how: the amount is taken away
ITEM_BY_VARIABLE   = $02        ; the item is a variable's slot
AMOUNT_BY_VARIABLE = $04        ; and the amount too
.proc item_by_variable
.a8
.i16
    lda [code_ptr], y           ; how
    iny
    sta temp
    rep #$20
.a16
    lda [code_ptr], y           ; the item, or its variable's slot
    iny
    iny
    sta temp + 2
    lda [code_ptr], y           ; the amount, or its variable's slot
    iny
    iny
    phy
    tay                         ; Y, the amount: it is free until the `ply`
    lda temp
    and #AMOUNT_BY_VARIABLE
    beq amount_ready
    tya
    jsr variable                ; a sixteen-bit value, signed
    tay
amount_ready:
    tya
    bmi ready                   ; below zero: `CommandChangeItems` returns
    lda temp
    and #ITEM_BY_VARIABLE
    beq item_ready
    lda temp + 2
    jsr variable
    sta temp + 2
item_ready:
    lda temp + 2
    beq ready                   ; 0 and those past the inventory, signed or
    cmp #ITEMS_N                ; not: `AddItem` does nothing with them
    bcs ready
    tax
    lda temp
    and #ITEM_SUBTRACTS
    bne subtracts
    ; It adds: the count plus the amount, capped at ITEM_MAX. The count is a
    ; byte and the amount up to $7FFF, so in sixteen bits it cannot wrap.
    lda f:FAR_LENGTH + FAR_ITEMS, x
    and #$00FF
    sta temp + 2
    tya
    clc
    adc temp + 2
    cmp #ITEM_MAX
    bcc put
    lda #ITEM_MAX
    bra put
subtracts:
    ; It takes away: the count minus the amount, and below zero it is zero.
    lda f:FAR_LENGTH + FAR_ITEMS, x
    and #$00FF
    sta temp + 2
    tya
    cmp temp + 2
    bcc fewer
    lda #0
    bra put
fewer:
    eor #$FFFF                  ; count - amount, as -(amount - count)
    sec
    adc temp + 2
put:
    sep #$20
.a8
    sta f:FAR_LENGTH + FAR_ITEMS, x
    ; RM2k does `SetNeedRefresh(true)` after every ChangeItems, as `op_item`.
    lda #1
    sta refresh
ready:
    sep #$20
.a8
    ply
    rtl

; A: a variable's slot, in sixteen bits; its value back in A. It is
; `var_read`, which is in bank 0 and a `jsr` does not reach.
.a16
variable:
    and #VAR_SLOT
    asl a                       ; two bytes per variable
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    rts
.endproc
