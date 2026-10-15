.segment "FAR"

; --- ControlVars: multiply, divide, modulo, and an item's count -------------
;
; What `op_var` does outside bank 0. The variables are sixteen bits signed
; —the book's divergence "Variables saturate at sixteen bits"—, and here the
; numbers are RM2k's: easyrpg's `VarMult`, `VarDiv` and `VarMod`, which work
; in 32 bits and clamp the result to the variable's range, and
; `ControlVariables::Item`.

; The operations past add and subtract, with RM2k's numbers, as the compiler
; leaves them in OP_VAR: see VAR_MODULO in the event compiler.
VAR_MULTIPLY = 3
VAR_DIVIDE   = 4

; A16: what the variable had; `temp + 2`: the operand; `temp + 1`: the
; operation, VAR_MULTIPLY, VAR_DIVIDE or the modulo, with VAR_REFRESH on top.
; Leaves the result in `temp + 2` and returns with A8. Clobbers X.
;
; * Multiplying keeps the whole 32-bit product and clamps it to the word:
;   `VarMult` overflows to the edge on the product's side, and the edge here
;   is -32768 or 32767.
; * Dividing truncates toward zero and the remainder takes the dividend's
;   sign, as C's `/` and `%` do. By zero, the division leaves the variable as
;   it was and the modulo gives 0. -32768 / -1 is 32768, which clamps.
;
; `comp_dup` and `comp_and` are the text compositor's scratch: it only uses
; them while it draws a glyph, and the battle's `ba_div` borrows them the
; same way.
.proc var_arith
.a16
.i16
    tax                         ; l, what the variable had
    eor temp + 2
    sta comp_dup                ; bit 15: the sign of the product or quotient
    stx comp_dup + 2            ; and l's, which the remainder takes
    sep #$20
.a8
    lda temp + 1
    and #<~VAR_REFRESH
    cmp #VAR_MULTIPLY
    rep #$20
.a16
    beq multiply
    lda temp + 2
    bne divide
    ; By zero. The modulo is 0, which `temp + 2` already is.
    sep #$20
.a8
    lda temp + 1
    and #<~VAR_REFRESH
    cmp #VAR_DIVIDE
    bne done
    stx temp + 2                ; the division leaves l
done:
    rtl
.a16
divide:
    bpl :+
    eor #$FFFF
    inc a
:   pha                         ; |r|
    txa
    bpl :+
    eor #$FFFF
    inc a                       ; -32768 is $8000, which unsigned is right
:   sta temp + 2                ; |l|
    pla
    jsl udiv16                  ; temp + 2 = |q|, A = |remainder|
    tax
    sep #$20
.a8
    lda temp + 1
    and #<~VAR_REFRESH
    cmp #VAR_DIVIDE
    rep #$20
.a16
    beq quotient
    txa                         ; the modulo, with l's sign
    bit comp_dup + 2
    bpl store
    eor #$FFFF
    inc a
    bra store
quotient:
    lda temp + 2
    bit comp_dup
    bmi negate                  ; |q| <= 32768, so -|q| fits
    cmp #$8000                  ; only -32768 / -1 gets here: 32768
    bcc store
    bra too_big
multiply:
    ; |l| times |r|, shifting and adding: the product's low word in A and its
    ; high word in `comp_and`, the multiplicand |l| in `comp_dup + 2` —l's
    ; sign is no longer needed— and the multiplier |r| shifting out of
    ; `temp + 2`.
    txa
    bpl :+
    eor #$FFFF
    inc a
:   sta comp_dup + 2
    lda temp + 2
    bpl :+
    eor #$FFFF
    inc a
:   sta temp + 2
    stz comp_and
    lda #0
    ldx #16
multiply_bit:
    asl a
    rol comp_and
    asl temp + 2
    bcc multiply_next
    clc
    adc comp_dup + 2
    bcc multiply_next
    inc comp_and
multiply_next:
    dex
    bne multiply_bit
    ; Clamped to the word: 32767 on the positive side and -32768 on the
    ; negative one, which is 32768 in magnitude.
    ldx comp_and
    bne overflow
    bit comp_dup
    bpl positive
    cmp #$8001
    bcs too_small
negate:
    eor #$FFFF
    inc a
    bra store
positive:
    cmp #$8000
    bcc store
too_big:
    lda #$7FFF
    bra store
overflow:
    bit comp_dup
    bpl too_big
too_small:
    lda #$8000
store:
    sta temp + 2
    sep #$20
.a8
    rtl
.endproc

; `temp + 2` divided by A16, both unsigned: the quotient ends up in
; `temp + 2` and the remainder in A16. Shift and subtract, sixteen passes; the
; divisor can be any word but zero —the remainder can reach seventeen bits,
; which the carry holds—. `op_var`'s random draw and `var_arith` share it.
; Clobbers X.
.proc udiv16
.a16
.i16
    pha                         ; 1,s: the divisor
    lda #0
    ldx #16
next_bit:
    asl temp + 2
    rol a
    bcs subtract                ; seventeen bits: surely the divisor or more
    cmp 1,s
    bcc no_enters
subtract:
    sbc 1,s                     ; C is set on both ways in
    inc temp + 2                ; the quotient bit that just came in
no_enters:
    dex
    bne next_bit
    plx                         ; the divisor, dropped
    rtl
.endproc

; `ControlVars` from an item, class 4, for `op_var`: Y on its `a` —the item,
; by its RM2k number— with `b` after it: 0 how many the party carries, 1 how
; many its members have equipped. Those are `ControlVariables::Item`'s,
; `GetItemCount` and `GetEquippedItemCount`. Returns the count in A16 **with
; the accumulator at sixteen bits**, and Y as it came. Clobbers X and
; `temp + 2`, which is `op_var`'s operand and is written after this.
.proc var_item_count
.a8
.i16
    phy
    rep #$20
.a16
    lda [code_ptr], y           ; the item
    tax
    iny
    iny
    lda [code_ptr], y           ; which count
    and #$00FF
    bne equipped
    ; Carried: one byte per item, by its number. The compiler lets through
    ; only what the inventory has room for.
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    rep #$20
.a16
    and #$00FF
    ply
    rtl
equipped:
    ; Each member's five slots, which hold the item's number as a word, and
    ; 0 when empty: counting 0 counts the empty slots, as RPG_RT does.
    stx temp + 2
    lda #0
    pha                         ; 1,s: the count
    ldy #0                      ; the place in the party
member:
    cpy party_n
    beq counted
    lda party, y                ; the actor, a byte
    and #$00FF
    sta comp_dup
    asl a
    asl a
    adc comp_dup                ; C is clear: an actor is a byte
    asl a                       ; times ten, which is what a row measures
    tax
.repeat 5, slot
    lda f:FAR_LENGTH + FAR_EQUIPMENT + slot * 2, x
    cmp temp + 2
    bne :+
    lda 1, s
    inc a
    sta 1, s
:
.endrepeat
    iny
    bra member
counted:
    pla
    ply
    rtl
.endproc
