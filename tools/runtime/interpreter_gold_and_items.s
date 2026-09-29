.segment "CODE"
.a8
.i16

; --- the interpreter: gold and items ---------------------------------------
;
; Opcode handlers: the `run_code` dispatch, in interpreter.s, jumps to
; each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; `ChangeGold`: adds or subtracts and clamps to [0, GOLD_MAX], which is what
; `Game_Party::GainGold` does. The amount takes three bytes because RM2k's cap
; is 999999 and this game uses the full value.
;
; There is nowhere to show it —the menu does not exist— but there is someone
; who asks for it: the gold branch of `ConditionalBranch`.
.proc op_gold
    lda [code_ptr], y            ; the sign: 0 adds, 1 subtracts
    sta temp
    iny
    rep #$20
.a16
    lda [code_ptr], y            ; the low 16 bits of the amount
    sta temp + 2
    sep #$20
.a8
    iny
    iny
    lda [code_ptr], y            ; and the high byte
    sta temp + 1                ; the high byte of the amount
    iny
    phy

    lda temp
    bne gold_remain
    ; Add: 24 bits, and if it goes past GOLD_MAX it stays at GOLD_MAX.
    rep #$20
.a16
    lda gold
    clc
    adc temp + 2
    sta gold
    sep #$20
.a8
    lda gold + 2
    adc temp + 1
    sta gold + 2
    bra gold_clips
gold_remain:
    rep #$20
.a16
    lda gold
    sec
    sbc temp + 2
    sta gold
    sep #$20
.a8
    lda gold + 2
    sbc temp + 1
    sta gold + 2
    bcs gold_clips
    ; It went below zero: it stays at zero.
    rep #$20
.a16
    stz gold
    sep #$20
.a8
    stz gold + 2
    bra gold_ready
gold_clips:
    ; Did it go past GOLD_MAX? Compared as 24 bits, high byte first.
    lda gold + 2
    cmp #^GOLD_MAX
    bcc gold_ready
    bne gold_cap
    rep #$20
.a16
    lda gold
    cmp #.loword(GOLD_MAX)
    sep #$20
.a8
    bcc gold_ready
    beq gold_ready
gold_cap:
    rep #$20
.a16
    lda #.loword(GOLD_MAX)
    sta gold
    sep #$20
.a8
    lda #^GOLD_MAX
    sta gold + 2
gold_ready:
    ply
    jmp run_code::other

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
    lda [code_ptr], y            ; the item
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sta temp + 2                ; the port advances on read and cannot be read
    iny                         ; again: the address is saved
    iny
    sep #$20
.a8
    stz WMADDH
    lda [code_ptr], y            ; how much, signed
    iny
    sta temp
    lda WMDATA                  ; the count there was
    clc
    adc temp
    bit temp
    bmi item_rest
    ; It added: if it went past ITEM_MAX —or wrapped around— it stays at the cap.
    bcs item_cap
    cmp #(ITEM_MAX + 1)
    bcc item_save
item_cap:
    lda #ITEM_MAX
    bra item_save
item_rest:
    ; It subtracted: with no carry it went below zero, and it stays at zero.
    bcs item_save
    lda #0
item_save:
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
    sta refresh
    jmp run_code::other

.endproc

