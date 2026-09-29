.segment "CODE"
.a8
.i16

; --- the interpreter: conditions and the jump ------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; `ConditionalBranch` with a switch condition. The operands are the number
; (two bytes), the polarity —copied as is from RM2k, where 0 means "it has to
; be on"— and the target: **the absolute index inside the page** the cursor
; goes to if the condition does not hold, that is, the matching `else` or
; `end`. Which one that target is was resolved by the converter, which is the
; only one that sees the whole page; here jumping is assigning Y.
.proc op_if
    ; The first byte says **what is being asked**, with RM2k's number as is: 0
    ; a switch, 3 the gold, 5 whether an actor is in the party. See
    ; `bytes_de_rama`.
    ;
    ; Each branch leaves in A whether the condition holds —zero or nonzero—
    ; and Y pointing at the polarity byte; from there on there is a single
    ; path. The switch is the only one that uses the polarity to decide: for
    ; the gold it is already inside the comparison and the actor has none.
    lda [cod_ptr], y
    iny                         ; Y -> the operand
    cmp #COND_ORO
    beq si_oro
    cmp #COND_ACTOR
    beq si_actor
    cmp #COND_ITEM
    bne :+
    jmp si_item                 ; the body is past the gold: `beq` does not reach
:

    ; --- the switch ---
    rep #$20
.a16
    phy                         ; the cursor: `switch_on` clobbers X and Y
    lda [cod_ptr], y            ; the number, 16 bits
    jsr switch_on        ; Z=1 off, Z=0 on
    beq si_apagado
    lda #$0001
    bra si_tengo
si_apagado:
    lda #$0000
si_tengo:
    ply                         ; the cursor back; `ply` does not touch A
    sep #$20
.a8
    ; A is 1 if the switch is on, and the polarity is 0 if it had to be: the
    ; `eor` gives nonzero exactly when it holds, in both directions, and
    ; without any extra branch. It goes through `temp` because the assembler
    ; has no `eor [dp], y`. The item uses the same ending, with the same
    ; polarity.
si_polaridad:
    iny
    iny                         ; Y -> the polarity
    sta temp
    lda [cod_ptr], y
    eor temp
    bra si_decide

    ; --- the actor: `IsActorInParty` ---
    ; It carries no polarity: the lower branch is the `else`, so the converter
    ; emits zero there and it is not looked at here.
si_actor:
    lda [cod_ptr], y            ; the id, which fits in a byte
    phy
    jsr in_party             ; A=1 if present, A=0 if not
    ply
    iny
    iny                         ; Y -> the polarity, which is zero
    ; **Z is set here, right next to the branch.** `si_decide` decides with a
    ; `beq`, and `ply` and the two `iny` left it the Z of the cursor, which is
    ; never zero: "is in the party" always said yes, and on the Warehouse roof
    ; Arden showed up without having been added. On 2026-09-12 the `cmp #0`
    ; went after the `ply` and before the `iny`s, which was fixing half of it:
    ; see `test_rama_grupo`.
    cmp #0
    bra si_decide

    ; --- the gold ---
    ; `CommandConditionalBranch` case 3: with the polarity at zero it is
    ; `gold >= operand` and with anything else `gold <= operand`. **They are
    ; not the negation of each other**: on equality both hold, so they are
    ; computed separately instead of flipping a bit.
si_oro:
    rep #$20
.a16
    lda [cod_ptr], y            ; against how much, 16 bits
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> the polarity
    lda oro + 2
    bne si_oro_grande           ; the gold is past 65535: greater than any
                                ; operand, which fits in a word
    rep #$20
.a16
    lda oro
    cmp temp + 2                ; C=1 if gold >= operand
    sep #$20
.a8
    lda #$01
    bcs si_oro_ge
    lda #$00
si_oro_ge:
    sta temp
    rep #$20
.a16
    lda temp + 2
    cmp oro                     ; C=1 if operand >= gold, i.e. gold <= operand
    sep #$20
.a8
    lda #$01
    bcs si_oro_le
    lda #$00
si_oro_le:
    sta temp + 1
    bra si_oro_elige
si_oro_grande:
    lda #$01
    sta temp                    ; the >= holds
    stz temp + 1                ; and the <= does not
si_oro_elige:
    lda [cod_ptr], y            ; the polarity
    beq si_oro_usa_ge
    lda temp + 1
    bra si_decide
si_oro_usa_ge:
    lda temp
    bra si_decide

    ; --- the item: `CommandConditionalBranch` case 4 ---
    ; `GetItemCount(id) > 0`, the same question as the page condition on an
    ; item and read from the same place: a byte of `FAR_ITEMS` indexed by the
    ; RM2k number. `GetEquippedItemCount` does not come in because there is no
    ; equipment, which is what `conditions_ok` already takes for granted.
    ;
    ; The polarity is the switch's —0 is "has to have it"— so it decides with
    ; the same `eor` and without an extra branch.
si_item:
    rep #$20
.a16
    lda [cod_ptr], y            ; the item number, 16 bits
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA                  ; how many there are in the inventory
    beq si_item_no
    lda #$01
    bra si_item_listo
si_item_no:
    lda #$00
si_item_listo:
    jmp si_polaridad

si_decide:
    beq si_no_cumple
    iny
    iny
    iny                         ; Y -> the next opcode
    jmp run_code::otro
si_no_cumple:
    iny                         ; Y -> the target
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp run_code::otro

.endproc

; `ConditionalBranch` on a variable: slot, value class, comparison, the
; sixteen-bit value and the target if it does not hold. The comparison is
; signed: after subtracting, "less than" is N different from V.
.proc op_if_var
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; the slot
    iny
    lda [cod_ptr], y
    sta temp + 1                ; the class: constant or another variable
    iny
    lda [cod_ptr], y            ; the comparison
    pha
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; the value, or the slot
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> the target
    ; `var_read` does not touch Y, so the cursor is not saved.
    lda temp + 1
    beq si_var_contra_constante
    lda temp + 2
    jsr var_read
.a16
    sta temp + 2
    sep #$20
.a8
si_var_contra_constante:
    pla                         ; the comparison
    bne si_var_otra
    ; "Equal", which is the one almost all of them use —the 40 pages of each
    ; lap of the race do it every frame— goes without `compare_var`: a
    ; sixteen-bit subtraction is enough.
    lda temp
    jsr var_read                ; A = the variable, sixteen bits
.a16
    cmp temp + 2
    sep #$20
.a8
    beq si_var_sigue            ; `sep` does not touch Z
    bra si_var_no
si_var_otra:
    sta temp + 1
    lda temp
    jsr var_read                ; A = the variable, sixteen bits
.a16
    jsr compare_var
.a8
    cmp #0                      ; the answer, in A: the flags are from
                                ; `compare_var`'s last computation
    bne si_var_sigue
si_var_no:
    rep #$20
.a16
    lda [cod_ptr], y            ; it does not hold: to the target
    tay
    sep #$20
.a8
    jmp run_code::otro
si_var_sigue:
    iny
    iny
    jmp run_code::otro

.endproc

; `ConditionalBranch` case 5 with two operands: "knows this skill" —sub 4—
; and "has this item equipped" —sub 5—. They go in a separate opcode and not
; in `OP_IF` because they carry **two** operands, the actor and the item or
; the skill; see OP_IF_ACTOR in eventos.py.
;
; Neither has a polarity: RM2k does not give them one, same as "is in the
; party", so the lower branch is the `else`.
;
; On entry, Y points at the sub. Both paths end at `sia_si` or at `sia_no`
; with Y already pointing at the target.
.proc op_if_actor
    lda [cod_ptr], y
    sta temp                    ; the sub
    iny
    lda [cod_ptr], y
    sta temp + 1                ; the actor, which fits in a byte
    iny
    rep #$20
.a16
    lda [cod_ptr], y
    sta temp + 2                ; the item or the skill, 16 bits
    sep #$20
.a8
    iny
    iny                         ; Y -> the target
    lda temp
    cmp #COND_ACTOR_HABILIDAD
    beq sia_habilidad

    ; --- the equipped equipment ---
    ; easyrpg's five `Get*Id()` compared against the item: it is enough for it
    ; to be in one slot. They are read from the same place the equipment
    ; screen reads them —`FAR_EQUIPO` + actor * 10, see `eq_point`— through
    ; the WRAM port, which auto-increments: one word per slot, byte by byte,
    ; because `WMDATA` is an eight-bit port and reading it two at a time would
    ; read the register next to it.
    rep #$20
.a16
    lda temp + 1
    and #$00FF                  ; the actor, without the item that follows
    asl a                       ; times two
    sta temp                    ; the sub is no longer needed
    asl a
    asl a                       ; times eight
    clc
    adc temp                    ; times ten, which is how long a row is
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #RANURAS_EQUIPO
sia_eq_otra:
    lda WMDATA
    sta temp                    ; the low byte of this slot's item
    lda WMDATA
    sta temp + 1
    rep #$20
.a16
    lda temp
    cmp temp + 2
    sep #$20
.a8
    beq sia_si                  ; `sep` does not touch Z: the comparison is still live
    dex
    bne sia_eq_otra
    bra sia_no

    ; --- the skill ---
    ; `Game_Actor::IsSkillLearned`: the bit of the (actor, skill) pair in
    ; `FAR_HAB`. The converter already put the pair's slot where the other
    ; questions carry the item, so `temp + 2` brings it and the actor is not
    ; needed. See `HABILIDAD_RANURA` in eventos.py.
sia_habilidad:
    jsl f:skill_known
    bne sia_si
sia_no:
    rep #$20
.a16
    lda [cod_ptr], y            ; the target, absolute inside the page
    tay
    sep #$20
.a8
    jmp run_code::otro
sia_si:
    iny
    iny                         ; Y -> the next opcode
    jmp run_code::otro

.endproc

; The unconditional jump the converter puts where the `else` was, so that the
; upper branch skips the lower one.
.proc op_goto
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp run_code::otro

.endproc

