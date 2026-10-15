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
; armor it wears carries the attribute.
;
; The tables are the converter's, outside bank 0: see `attributes` in
; rm2k-snes/mapdata's `emit.rs`. The attributes are numbered from 0 among the
; ones something can carry, `ATTR_N` of them.
;
; **The scratch is the zero page's `comp_*`**, which the battle already lends
; to `ba_mul` and `ba_div`, and `temp`: nothing here lives past the call,
; and adding far RAM for it was not worth it. `ba_mul` is only called before
; `ATTR_ACTOR` is written, because it clobbers `comp_or23`.
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
