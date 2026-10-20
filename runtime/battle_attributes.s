.segment "FAR2"

; --- the attributes ---------------------------------------------------------
;
; What a weakness or a resistance does to a hit: easyrpg's
; `ApplyAttributeMultiplier`, RM2k 2000's path, and the model's
; `attributes::apply` in `rm2k-snes-battle`, which is where each rule is
; explained. In short: of the attributes the hit carries, the best rate of the
; target's rank among the physical ones and the best among the magical ones;
; the effect goes through each kind there is, physical first —
; `magical * (physical * effect / 100) / 100`—. A normal attack carries its
; weapons' attributes, and only an actor's; a skill, its own. The target's
; rank is its own, and an actor's goes one step up —more resistant— if any
; armor it wears carries the attribute; and then the shift a skill with
; `affect_attr_defence` gave it in this battle, one step at most either way:
; see `ba_attr_shift`.
;
; The tables are the converter's, outside bank 0: see `attributes` in
; rm2k-snes/mapdata's `emit.rs`. The attributes are numbered from 0 among the
; ones something can carry, `ATTR_N` of them.
;
; **The scratch is the zero page's `comp_*`**, which the battle already lends
; to `ba_mul` and `ba_div`, and `temp`: nothing here lives past the call,
; and adding far RAM for it was not worth it. `ba_mul` is only called before
; `ATTR_ACTOR` is written, because it clobbers `comp_or23`.
;
; **The shifts do live past the call**, the whole battle: a signed byte per
; combatant and attribute, -1, 0 or +1 —easyrpg's `attribute_shift`—, only
; for the attributes some carried skill can shift, which the converter
; numbers first, `ATTR_SHIFT_N` of them. A row of `ATTR_SHIFT_N` per
; combatant, in combatant order. They are cleared when the battle starts,
; when an actor gets up or comes in —easyrpg clears them when the dead state
; is added, which is the same seen from outside: a fallen one is neither hit
; nor shifted—, and for the target of a heal from the skills screen, which
; borrows combatant 1 and must find no shift there.
.pushseg
.segment "FARBSS"
ba_attr_shifts: .res BA_COMB_MAX * ATTR_SHIFT_N
.popseg
ATTR_EFFECT = comp_dup          ; word: the effect being multiplied
ATTR_ROW1   = comp_dup + 2      ; word: one set's row in `attr_sets`
ATTR_ROW2   = comp_or01         ; word: and the other's; 0 is the empty set
ATTR_RANKS  = comp_or01 + 2     ; word: the target's row in `attr_ranks`
ATTR_ACTOR  = comp_or23         ; word: an actor target's row of
                                ; `FAR_EQUIPMENT`, $FFFF for an enemy
ATTR_A      = comp_or23 + 2     ; word: the attribute being looked at
ATTR_PHYS   = comp_and          ; word: the best physical rate, $FFFF none
ATTR_MAG    = comp_and + 2      ; word: the best magical rate

; `ITEM_WEAPON` and the armor's, of `rpg::Item::Type`: shield, armor, helmet
; and accessory are 2 to 5.
ITEM_TYPE_WEAPON = 1
ITEM_TYPE_ARMOR_FIRST = 2
ITEM_TYPE_ARMOR_LAST = 5

; A16 = the effect of skill `BA_MSKILL` on `BA_MTGT`, already at least zero;
; returns with it through the attributes, in A16. Clobbers X, Y, `BA_T*`,
; `temp` and the `comp_*` above.
.proc ba_attr_skill
.a16
.i16
    sta ATTR_EFFECT
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_attr, x
    sta ATTR_ROW1
    stz ATTR_ROW2
    jmp ba_attr_apply
.endproc

; A16 = the damage of `BA_MWHO`'s normal attack on `BA_MTGT`, already at
; least zero; returns with it through its weapons' attributes, in A16: those
; of the weapons in its first two slots, which an enemy does not have.
; Clobbers what `ba_attr_skill` does.
.proc ba_attr_attack
.a16
.i16
    sta ATTR_EFFECT
    sep #$20
.a8
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcc of_an_actor
    rep #$20
.a16
    lda ATTR_EFFECT
    rts
of_an_actor:
.a8
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rep #$20
.a16
    jsr ba_attr_equipment_row
    sta BA_T1
    tax
    lda FAR_EQUIPMENT, x
    jsr weapon_row
    sta ATTR_ROW1
    ldx BA_T1
    lda FAR_EQUIPMENT + 2, x
    jsr weapon_row
    sta ATTR_ROW2
    jmp ba_attr_apply

; A16 an item of `FAR_EQUIPMENT`; A16 its row in `attr_sets` if it is a
; weapon the cartridge carries, and the empty set's otherwise: a shield in
; the second slot attacks with nothing.
weapon_row:
    jsr ba_attr_item_k
    bcs none
    sep #$20
.a8
    lda f:item_type, x
    cmp #ITEM_TYPE_WEAPON
    rep #$20
.a16
    bne none
    txa
    asl a
    tax
    lda f:item_attr, x
    rts
none:
    lda #0
    rts
.endproc

; A16 = an actor's LDB number; A16 = where its five slots start in
; `FAR_EQUIPMENT`, ten times the number.
.proc ba_attr_equipment_row
.a16
.i16
    and #$00FF
    asl a
    sta temp
    asl a
    asl a
    clc
    adc temp
    rts
.endproc

; A16 = an item of `FAR_EQUIPMENT`, by its LDB number; X = its `k` and C=0, or
; C=1 if there is none or the cartridge does not carry it. Clobbers A.
.proc ba_attr_item_k
.a16
.i16
    cmp #0
    beq none
    cmp #ITEMS_N
    bcs none
    asl a
    tax
    lda f:item_k, x
    tax
    inc a
    beq none                    ; $FFFF: the cartridge does not carry it
    clc
    rts
none:
    sec
    rts
.endproc

; What the sets in `ATTR_ROW1` and `ATTR_ROW2` do to `ATTR_EFFECT` against
; `BA_MTGT`: the common part of the two above. Returns with A16 the effect.
.proc ba_attr_apply
.a16
.i16
    lda #ATTR_N
    bne some
    lda ATTR_EFFECT
    rts
some:
    ; The target's row of ranks: an actor's by its LDB number, an enemy's by
    ; its `k`, after the actors'.
    sep #$20
.a8
    lda #ATTR_N
    sta BA_T2
    stz BA_T2 + 1
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs an_enemy
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rep #$20
.a16
    and #$00FF
    sta BA_T1
    jsr ba_mul                  ; the actor times ATTR_N
    sta ATTR_RANKS
    lda BA_T1
    jsr ba_attr_equipment_row
    sta ATTR_ACTOR
    bra walk
an_enemy:
.a8
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x   ; its place in the troop
    jsr ba_member_x
    lda f:troop_member, x       ; and its `k`
    rep #$20
.a16
    and #$00FF
    clc
    adc #ACTORS_N
    jsr ba_mul                  ; (ACTORS_N + k) times ATTR_N
    sta ATTR_RANKS
    lda #$FFFF
    sta ATTR_ACTOR

walk:
    lda #$FFFF
    sta ATTR_PHYS
    sta ATTR_MAG
    stz ATTR_A
other:
    lda ATTR_A
    cmp #ATTR_N
    bcs combine
    ; Whether either set has it.
    clc
    adc ATTR_ROW1
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    sta BA_T0
    rep #$20
.a16
    lda ATTR_A
    clc
    adc ATTR_ROW2
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    ora BA_T0
    bne carried
    rep #$20
.a16
    jmp next
carried:
    rep #$20
.a16
    jsr rank
    ; The rate: `attr_rate`, a word at (5 * attribute + rank) * 2.
    sta BA_T0
    lda ATTR_A
    asl a
    asl a
    clc
    adc ATTR_A
    clc
    adc BA_T0
    asl a
    tax
    lda f:attr_rate, x
    sta BA_T0
    bmi next                    ; a negative rate counts for nothing
    ldx ATTR_A
    sep #$20
.a8
    lda f:attr_magic, x
    bne magical
    rep #$20
.a16
    lda ATTR_PHYS
    bmi best_phys               ; none yet
    lda BA_T0
    cmp ATTR_PHYS
    bcc next
best_phys:
    lda BA_T0
    sta ATTR_PHYS
    bra next
magical:
    rep #$20
.a16
    lda ATTR_MAG
    bmi best_mag
    lda BA_T0
    cmp ATTR_MAG
    bcc next
best_mag:
    lda BA_T0
    sta ATTR_MAG
next:
    inc ATTR_A
    jmp other

combine:
    lda ATTR_PHYS
    bmi no_phys
    jsr scale
no_phys:
    lda ATTR_MAG
    bmi no_mag
    jsr scale
no_mag:
    lda ATTR_EFFECT
    rts

; A16 = the target's rank in `ATTR_A`, 0 to 4: its own and, an actor's, one
; step up if a piece of armor it wears carries the attribute —however many
; do—, and no further than `E`.
rank:
    lda ATTR_RANKS
    clc
    adc ATTR_A
    tax
    lda f:attr_ranks, x
    and #$00FF
    sta BA_T1
    lda ATTR_ACTOR
    bmi ranked                  ; an enemy wears nothing
    ldy #0
slot:
    sty BA_T2
    tya
    clc
    adc ATTR_ACTOR
    tax
    lda FAR_EQUIPMENT, x
    jsr ba_attr_item_k
    bcs other_slot
    sep #$20
.a8
    lda f:item_type, x
    cmp #ITEM_TYPE_ARMOR_FIRST
    bcc other_slot8
    cmp #ITEM_TYPE_ARMOR_LAST + 1
    bcs other_slot8
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_attr, x
    clc
    adc ATTR_A
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    bne boosted
other_slot8:
    rep #$20
.a16
other_slot:
    ldy BA_T2
    iny
    iny
    cpy #10
    bcc slot
    bra ranked
boosted:
    rep #$20
.a16
    lda BA_T1
    cmp #4
    bcs ranked                  ; already `E`
    inc BA_T1
ranked:
    ; And the shift, if this attribute can have one: base plus shift,
    ; clamped to `A`..`E`, which is `GetAttributeRate`.
    lda ATTR_A
    cmp #ATTR_SHIFT_N
    bcs unshifted
    sep #$20
.a8
    lda BA_MTGT
    jsr ba_attr_row
    rep #$21                    ; and the carry clear for the addition
.a16
    txa
    adc ATTR_A
    tax
    lda .loword(ba_attr_shifts), x
    and #$00FF
    cmp #$0080
    bcc shift_ready
    ora #$FF00                  ; -1
shift_ready:
    clc
    adc BA_T1
    bpl not_below_a
    lda #0
not_below_a:
    cmp #5
    bcc unshifted_a
    lda #4
unshifted_a:
    sta BA_T1
unshifted:
    lda BA_T1
    rts

; `ATTR_EFFECT = ATTR_EFFECT * A16 / 100`, the rate in A16 between 0 and
; $7FFF: the product in thirty-two bits —an effect of a thousand through two
; rates of three hundred goes past sixteen— and the quotient capped at
; $7FFF, which the damage's cap of 999 takes down after. In software, shift
; and add and shift and subtract: it is once per hit.
scale:
    sta BA_T0                   ; the multiplier, eaten from the bottom
    stz temp
    stz temp + 2
    lda ATTR_EFFECT
    sta BA_T1                   ; the multiplicand, in thirty-two bits
    stz BA_T2
    ldy #16
multiply:
    lsr BA_T0
    bcc no_add
    lda temp
    clc
    adc BA_T1
    sta temp
    lda temp + 2
    adc BA_T2
    sta temp + 2
no_add:
    asl BA_T1
    rol BA_T2
    dey
    bne multiply
    ; And divided by a hundred: the quotient goes into `temp` as the
    ; dividend leaves it, and the remainder stays in `BA_T0`.
    stz BA_T0
    ldy #32
divide:
    asl temp
    rol temp + 2
    rol BA_T0
    lda BA_T0
    sec
    sbc #100
    bcc no_subtract
    sta BA_T0
    inc temp                    ; the quotient bit that just came in
no_subtract:
    dey
    bne divide
    lda temp + 2
    bne too_big
    lda temp
    bpl scaled
too_big:
    lda #$7FFF
scaled:
    sta ATTR_EFFECT
    rts
.endproc

; --- the shifts --------------------------------------------------------------

; A8 = a combatant; X = where its row starts in `ba_attr_shifts`: the
; combatant times `ATTR_SHIFT_N`, added up, since it is at most eleven times.
; Leaves A8. Clobbers Y.
.proc ba_attr_row
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    lda #0
    cpy #0
    beq ready
add:
    clc
    adc #ATTR_SHIFT_N
    dey
    bne add
ready:
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = a combatant: its ranks back to the database's. Clobbers A, X and Y.
.proc ba_attr_unshift
.a8
.i16
    jsr ba_attr_row
    ldy #ATTR_SHIFT_N
    beq done
clear:
    stz .loword(ba_attr_shifts), x
    inx
    dey
    bne clear
done:
    rts
.endproc

; Nobody has a shift: from `battle_run`, before anything. Clobbers A and X.
.proc ba_attr_unshift_all
.a8
.i16
    ldx #BA_COMB_MAX * ATTR_SHIFT_N
    beq done
clear:
    dex
    stz .loword(ba_attr_shifts), x
    bne clear
    ; (`stz` leaves the flags alone: the `bne` sees the `dex`.)
done:
    rts
.endproc

; `affect_attr_defence` on `BA_MTGT`, after the four parameters, as
; `Skill::vExecute` and the model's `skill_on` in `rm2k-snes-battle`, which
; is where the rule is explained: for each attribute of skill `BA_MSKILL`,
; in database order, if the target's shift can still move —a step weaker on
; one it targets as an enemy, a step more resistant on an ally, never past
; one step—, a roll against the hit rate in `BA_S0`, and the step if it comes
; up. **At the bound there is no roll.** The damage, already done, read the
; rank as it was. Clobbers `BA_S1`, `BA_S2`, `BA_S4`, `BA_S5`, what
; `ba_pct` does, A, X and Y.
.proc ba_attr_shift
.a8
.i16
    lda BA_MSKILL
    jsr ba_ax
    lda f:skill_shifts, x
    bne shifts
    rts
shifts:
    lda f:skill_affects, x
    and #$40                    ; it targets enemies
    beq ally
    lda #$FF
    bra step_ready
ally:
    lda #1
step_ready:
    sta BA_S5                   ; the step, +1 or -1
    lda BA_MTGT
    jsr ba_attr_row
    stx BA_S4                   ; the target's row
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_attr, x
    sta BA_S1                   ; the skill's set
    stz BA_S2                   ; the attribute
attribute:
    lda BA_S2
    cmp #ATTR_SHIFT_N           ; the skill carries no other: see the top
    bcs done
    clc
    adc BA_S1
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    beq next
    jsr shift_x
    lda .loword(ba_attr_shifts), x
    cmp BA_S5
    beq next                    ; already a step that way
    lda BA_S0
    jsr ba_pct
    beq next
    jsr shift_x
    lda .loword(ba_attr_shifts), x
    clc
    adc BA_S5
    sta .loword(ba_attr_shifts), x
    ; A success, `SetIsSuccess`, though this battle writes no line for it:
    ; see `ba_res_ok` in battle_skills.s.
    inc .loword(ba_res_ok)
next:
    rep #$20
.a16
    inc BA_S2
    bra attribute
done:
    sep #$20
.a8
    rts

; X = the target's byte for attribute `BA_S2`. Leaves A8.
shift_x:
    rep #$21                    ; and the carry clear for the addition
.a16
    lda BA_S4
    adc BA_S2
    tax
    sep #$20
.a8
    rts
.endproc
