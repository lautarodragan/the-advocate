.segment "CODE"
.a8
.i16

; --- the interpreter: conditions and the jump ------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `ConditionalBranch` with a switch condition. The operands are the number
; (two bytes), the polarity —copied as is from RM2k, where 0 means "it has to
; be on"— and the target: **the absolute index inside the page** the cursor
; goes to if the condition does not hold, that is, the matching `else` or
; `end`. Which one that target is was resolved by the converter, which is the
; only one that sees the whole page; here jumping is assigning Y.
.proc op_if
    ; The first byte says **what is being asked**, with RM2k's number as is: 0
    ; a switch, 2 the timer, 3 the gold, 5 whether an actor is in the party.
    ; See `branch_bytes`.
    ;
    ; Each branch leaves in A whether the condition holds —zero or nonzero—
    ; and Y pointing at the polarity byte; from there on there is a single
    ; path. The switch is the only one that uses the polarity to decide: for
    ; the gold and the timer it is already inside the comparison and the actor
    ; has none.
    lda [code_ptr], y
    iny                         ; Y -> the operand
    cmp #COND_GOLD
    beq if_gold
    cmp #COND_TIMER
    beq if_timer
    cmp #COND_ACTOR
    beq if_actor
    cmp #COND_ITEM
    bne :+
    jmp if_item                 ; the body is past the gold: `beq` does not reach
:

    ; --- the switch ---
    rep #$20
.a16
    phy                         ; the cursor: `switch_on` clobbers X and Y
    lda [code_ptr], y           ; the number, 16 bits
    jsr switch_on               ; Z=1 off, Z=0 on
    beq if_off
    lda #$0001
    bra if_have
if_off:
    lda #$0000
if_have:
    ply                         ; the cursor back; `ply` does not touch A
    sep #$20
.a8
    ; A is 1 if the switch is on, and the polarity is 0 if it had to be: the
    ; `eor` gives nonzero exactly when it holds, in both directions, and
    ; without any extra branch. It goes through `temp` because the assembler
    ; has no `eor [dp], y`. The item uses the same ending, with the same
    ; polarity.
if_polarity:
    iny
    iny                         ; Y -> the polarity
    sta temp
    lda [code_ptr], y
    eor temp
    bra if_decides

    ; --- the actor: `IsActorInParty` ---
    ; It carries no polarity: the lower branch is the `else`, so the converter
    ; emits zero there and it is not looked at here.
if_actor:
    lda [code_ptr], y           ; the id, which fits in a byte
    phy
    jsr in_party                ; A=1 if present, A=0 if not
    ply
    iny
    iny                         ; Y -> the polarity, which is zero
    ; **Z is set here, right next to the branch.** `if_decides` decides with a
    ; `beq`, and `ply` and the two `iny` left it the Z of the cursor, which is
    ; never zero: "is in the party" always said yes, and on the Warehouse roof
    ; Arden showed up without having been added. On 2026-09-12 the `cmp #0`
    ; went after the `ply` and before the `iny`s, which was fixing half of it:
    ; see `test_party_branch`.
    cmp #0
    bra if_decides

    ; --- the gold and the timer ---
    ; `CommandConditionalBranch` cases 3 and 2: with the polarity at zero it
    ; is `value >= operand` and with anything else `value <= operand`. **They
    ; are not the negation of each other**: on equality both hold, so the one
    ; the polarity asks for is computed, instead of flipping a bit. The value
    ; is the gold, or the timer's seconds: `GetTimerSeconds` is the frames over
    ; 60, which is `timer_sec`.
if_timer:
    rep #$20
.a16
    lda timer_sec
    bra if_value
.a8
if_gold:
    lda gold + 2
    beq if_gold_word
    ; The gold is past 65535: greater than any operand, which fits in a word.
    ; The >= holds and the <= does not, and the converter only emits 0 and 1.
    iny
    iny                         ; Y -> the polarity
    lda [code_ptr], y
    eor #$01
    bra if_decides
if_gold_word:
    rep #$20
.a16
    lda gold
if_value:
    sta temp                    ; the value
    lda [code_ptr], y           ; against how much, 16 bits
    sta temp + 2
    iny
    iny                         ; Y -> the polarity
    sep #$20
.a8
    lda [code_ptr], y
    rep #$20                    ; `rep` does not touch Z: the branch looks at
.a16                            ; the polarity
    bne if_at_most
    lda temp
    cmp temp + 2                ; C=1 if value >= operand
    bra if_carry
if_at_most:
    lda temp + 2
    cmp temp                    ; C=1 if operand >= value, i.e. value <= operand
if_carry:
    sep #$20
.a8
    lda #0
    rol a                       ; A = the carry, and Z with it
    bra if_decides

    ; --- the item: `CommandConditionalBranch` case 4 ---
    ; `GetItemCount(id) > 0`, the same question as the page condition on an
    ; item and read from the same place: a byte of `FAR_ITEMS` indexed by the
    ; RM2k number. `GetEquippedItemCount` does not come in because there is no
    ; equipment, which is what `conditions_ok` already takes for granted.
    ;
    ; The polarity is the switch's —0 is "has to have it"— so it decides with
    ; the same `eor` and without an extra branch.
if_item:
    rep #$20
.a16
    lda [code_ptr], y           ; the item number, 16 bits
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA                  ; how many there are in the inventory
    beq if_item_no
    lda #$01
    bra if_item_ready
if_item_no:
    lda #$00
if_item_ready:
    jmp if_polarity

if_decides:
    beq if_no_met
    iny
    iny
    iny                         ; Y -> the next opcode
    jmp run_code::other
if_no_met:
    iny                         ; Y -> the target
    rep #$20
.a16
    lda [code_ptr], y
    tay
    sep #$20
.a8
    jmp run_code::other

.endproc

; `ConditionalBranch` case 6: does a character face this way? The target is the
; hero —0— or an event's index plus one, as in `OP_ROUTE`, and the direction is
; RM2k's facing, which is the console's. No polarity: the lower branch is the
; `else`.
;
; The hero's is `hero_dir`. An event's is where the drawing reads it from: its
; route slot's, once a route has turned it, and before that its row's, which
; carries its page's —`face_diagonal` does the same look—. **An event with no
; row has no pose anyone can see, and answers down**, which is RM2k's default
; direction of a page; it diverges only for an invisible event whose page
; faces another way and which a condition asks about.
;
; `event_slot` and `event_npc` use `other_ev` and `temp`, so the two operands
; wait in `temp + 1` and `temp + 2`.
.proc op_if_facing
.a8
.i16
    lda [code_ptr], y
    sta temp + 2                ; the target
    iny
    lda [code_ptr], y
    sta temp + 1                ; the direction it has to face
    iny                         ; Y -> where it goes if it does not hold
    phy
    lda temp + 2
    bne of_event
    lda hero_dir
    bra have_facing
of_event:
    dec a                       ; the event's index
    jsr event_slot              ; X, or $FFFF
    cpx #$FFFF
    beq from_row
    lda route_ev + 8, x
    cmp #ROUTE_EV_NO_FACE
    bne have_facing             ; a route already turned it
from_row:
    lda temp + 2
    dec a
    jsr event_npc               ; Y: its row, or $FFFF
    cpy #$FFFF
    bne with_row
    lda #DIR_DOWN
    bra have_facing
with_row:
    lda npc_buf + 10, y
have_facing:
    ply                         ; `ply` does not touch A, but it does Z
    cmp temp + 1                ; the compare is the last thing before the branch
    bne facing_no
    iny
    iny                         ; Y -> the next opcode
    jmp run_code::other
facing_no:
    rep #$20
.a16
    lda [code_ptr], y
    tay
    sep #$20
.a8
    jmp run_code::other
.endproc

; `ConditionalBranch` on a variable: slot, value class, comparison, the
; sixteen-bit value and the target if it does not hold. The comparison is
; signed: after subtracting, "less than" is N different from V.
.proc op_if_var
.a8
.i16
    lda [code_ptr], y
    sta temp                    ; the slot
    iny
    lda [code_ptr], y
    sta temp + 1                ; the class: constant or another variable
    iny
    lda [code_ptr], y           ; the comparison
    pha
    iny
    rep #$20
.a16
    lda [code_ptr], y           ; the value, or the slot
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> the target
    ; `var_read` does not touch Y, so the cursor is not saved.
    lda temp + 1
    beq if_var_against_constant
    lda temp + 2
    jsr var_read
.a16
    sta temp + 2
    sep #$20
.a8
if_var_against_constant:
    pla                         ; the comparison
    bne if_var_other
    ; "Equal", which is the one almost all of them use —the 40 pages of each
    ; lap of the race do it every frame— goes without `compare_var`: a
    ; sixteen-bit subtraction is enough.
    lda temp
    jsr var_read                ; A = the variable, sixteen bits
.a16
    cmp temp + 2
    sep #$20
.a8
    beq if_var_continues        ; `sep` does not touch Z
    bra if_var_no
if_var_other:
    sta temp + 1
    lda temp
    jsr var_read                ; A = the variable, sixteen bits
.a16
    jsr compare_var
.a8
    cmp #0                      ; the answer, in A: the flags are from
                                ; `compare_var`'s last computation
    bne if_var_continues
if_var_no:
    rep #$20
.a16
    lda [code_ptr], y           ; it does not hold: to the target
    tay
    sep #$20
.a8
    jmp run_code::other
if_var_continues:
    iny
    iny
    jmp run_code::other

.endproc

; `ConditionalBranch` case 5 with two operands: "has at least this many HP"
; —sub 3—, "knows this skill" —sub 4— and "has this item equipped" —sub 5—.
; They go in a separate opcode and not in `OP_IF` because they carry **two**
; operands, the actor and the HP, the item or the skill; see OP_IF_ACTOR in
; the events compiler.
;
; None has a polarity: RM2k does not give them one, same as "is in the
; party", so the lower branch is the `else`.
;
; On entry, Y points at the sub. Both paths end at `actor_yes` or at `actor_no`
; with Y already pointing at the target.
.proc op_if_actor
    lda [code_ptr], y
    sta temp                    ; the sub
    iny
    lda [code_ptr], y
    sta temp + 1                ; the actor, which fits in a byte
    iny
    rep #$20
.a16
    lda [code_ptr], y
    sta temp + 2                ; the item or the skill, 16 bits
    sep #$20
.a8
    iny
    iny                         ; Y -> the target
    lda temp
    cmp #COND_ACTOR_SKILL
    beq actor_skill
    cmp #COND_ACTOR_HP
    beq actor_hp

    ; --- the equipped equipment ---
    ; easyrpg's five `Get*Id()` compared against the item: it is enough for it
    ; to be in one slot. They are read from the same place the equipment
    ; screen reads them —`FAR_EQUIPMENT` + actor * 10, see `eq_point`— through
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
    adc #FAR_EQUIPMENT
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #SLOTS_EQUIPMENT
actor_eq_other:
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
    beq actor_yes               ; `sep` does not touch Z: the comparison is still live
    dex
    bne actor_eq_other
    bra actor_no

    ; --- the skill ---
    ; `Game_Actor::IsSkillLearned`: the bit of the (actor, skill) pair in
    ; `FAR_SKILL`. The converter already put the pair's slot where the other
    ; questions carry the item, so `temp + 2` brings it and the actor is not
    ; needed. See `SKILL_SLOT` in events.py.
actor_skill:
    jsl f:skill_known
    bne actor_yes
    bra actor_no

    ; --- the HP ---
    ; `actor->GetHp() >= p[3]`: its word in `FAR_HP`, indexed by the actor
    ; number, against the data. Unsigned, as RM2k's HP never go below zero.
actor_hp:
    rep #$20
.a16
    lda temp + 1
    and #$00FF                  ; the actor, without the HP that follows
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    cmp temp + 2
    sep #$20
.a8
    bcs actor_yes               ; `sep` does not touch C
actor_no:
    rep #$20
.a16
    lda [code_ptr], y           ; the target, absolute inside the page
    tay
    sep #$20
.a8
    jmp run_code::other
actor_yes:
    iny
    iny                         ; Y -> the next opcode
    jmp run_code::other

.endproc

; The unconditional jump the converter puts where the `else` was, so that the
; upper branch skips the lower one.
.proc op_goto
    rep #$20
.a16
    lda [code_ptr], y
    tay
    sep #$20
.a8
    jmp run_code::other

.endproc

