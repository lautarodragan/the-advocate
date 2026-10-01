.segment "FAR"

; --- a medicine from the menu ------------------------------------------------
;
; easyrpg's `Game_Party::UseItem(id, actor)` (`game_party.cpp:322`), which is
; `Game_Actor::IsItemUsable` —the item's `actor_set`— and then
; `Game_Battler::UseItem` (`game_battler.cpp:146`), plus the `ConsumeItemUse`
; if it was of use and, before everything, the "is there any left?" of
; `Scene_ActorTarget`. The actor choice calls it on each A over a medicine.
;
; It enters with the actor in A8 and the item's `k` in `pick_edges`, where
; `items_screen` leaves it. It returns with A8 at 1 if it was of use and at
; 0 if not, and Z to match. It is entered with `jsl`, with any data bank: it
; sets $7E and restores it. It clobbers X, Y and `temp`.
;
; **A fallen actor is an actor with zero HP**, and not as a shortcut:
; easyrpg's `IsDead` (`game_battler.h:995`) looks at the HP and not at the
; state, "RPG_RT compatibility requires checking the death state and not hp".
; Outside battle this port keeps no states, so reviving one is the `SetHp(1)`
; of `RemoveStates`, and the other states in `state_set` remove nothing:
; `was_used` is only set if the actor had the state.
.proc medicine_use
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    sta MED_ACTOR
    stz MED_USED
    stz MED_REVIVED
    stz MED_REVIVED + 1
    ; Is there any left? With the choice open the last one can be spent and
    ; A still pressed.
    jsr k_in_x
    lda f:item_medicine, x
    sta MED_FLAGS
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x
    sta MED_ID
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    bne remains
    jmp no_serves
remains:
    ; `Game_Actor::IsItemUsable`: the actor's bit in `item_actors`, eight
    ; bytes per item, actor 1 in bit 0 of the first.
    jsr k_in_x
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta MED_P
    lda MED_ACTOR
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc MED_P
    tax
    pla
    and #$0007
    tay
    sep #$20
.a8
    lda f:item_actors, x
    cpy #0
    beq bit_ready
run:
    lsr a
    dey
    bne run
bit_ready:
    and #1
    bne can
    jmp no_serves
can:
    ; The maximums for their current level, like `FullHeal`.
    lda MED_ACTOR
    ldy #0
    jsl f:level_param
    stx MED_HP_MAX
    lda MED_ACTOR
    ldy #1
    jsl f:level_param
    stx MED_SP_MAX
    ; `hp_change = recover_hp_rate * GetMaxHp() / 100 + recover_hp`, and the
    ; same with SP. Capped at $FFFF, which means "more than what is missing".
    jsr k_in_x
    lda f:item_heal_rate, x
    ldx MED_HP_MAX
    jsr per_hundred
    sta MED_HP
    jsr k_in_x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_heal_hp, x
    clc
    adc MED_HP
    bcc hp_ready
    lda #$FFFF
hp_ready:
    sta MED_HP
    sep #$20
.a8
    jsr k_in_x
    lda f:item_heal_sp_rate, x
    ldx MED_SP_MAX
    jsr per_hundred
    sta MED_SP
    jsr k_in_x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_heal_sp, x
    clc
    adc MED_SP
    bcc sp_ready
    lda #$FFFF
sp_ready:
    sta MED_SP
    ; Dead or not. From here on X is the actor times two, for HP and SP.
    lda MED_ACTOR
    and #$00FF
    asl a
    tax
    lda FAR_HP, x
    sep #$20
.a8
    bne alive
    ; Dead: it is only of use if it removes the death state, and removing it is 1 HP.
    lda MED_FLAGS
    and #2
    bne raise
    jmp no_serves
raise:
    rep #$20
.a16
    lda #1
    sta FAR_HP, x
    sta MED_REVIVED
    sep #$20
.a8
    sta MED_USED
    bra heal_hp
alive:
    lda MED_FLAGS
    and #1
    beq heal_hp
    jmp no_serves               ; `ko_only` on one standing
heal_hp:
    ; `if (hp_change > 0 && !HasFullHp()) ChangeHp(hp_change - revived)`.
    ; `ChangeHp` caps at the maximum with the `SetHp` inside it, and never
    ; goes below 1 because nothing subtracts here.
    rep #$20
.a16
    lda MED_HP
    beq heal_sp
    lda FAR_HP, x
    cmp MED_HP_MAX
    bcs heal_sp                 ; full
    lda MED_HP
    sec
    sbc MED_REVIVED
    clc
    adc FAR_HP, x
    bcs hp_capped
    cmp MED_HP_MAX
    bcc hp_set
hp_capped:
    lda MED_HP_MAX
hp_set:
    sta FAR_HP, x
    sep #$20
.a8
    lda #1
    sta MED_USED
    rep #$20
.a16
heal_sp:
    ; `if (sp_change > 0 && !HasFullSp()) ChangeSp(sp_change)`.
    lda MED_SP
    beq consume
    lda FAR_SP, x
    cmp MED_SP_MAX
    bcs consume
    clc
    adc MED_SP
    bcs sp_capped
    cmp MED_SP_MAX
    bcc sp_set
sp_capped:
    lda MED_SP_MAX
sp_set:
    sta FAR_SP, x
    sep #$20
.a8
    lda #1
    sta MED_USED
consume:
    ; `ConsumeItemUse`, if it was of use and the item has uses. One at a
    ; time: RM2k counts the uses of a multi-use item, and this port does not,
    ; but this game's medicines are all single-use.
    sep #$20
.a8
    lda MED_USED
    beq ready
    lda MED_FLAGS
    and #4
    beq ready
    ldx MED_ID
    lda FAR_ITEMS, x
    dec a
    sta FAR_ITEMS, x
    bra ready
no_serves:
    stz MED_USED
ready:
    plb
    lda f:FAR_LENGTH + MED_USED ; after the `plb`: the flags come from this
    rtl

; The item's `k`, from `pick_edges` to X. Only A and X.
k_in_x:
    rep #$20
.a16
    lda pick_edges
    and #$00FF
    tax
    sep #$20
.a8
    rts

; A8 the percentage and X the maximum: returns with A16 = percent * max / 100,
; easyrpg's integer division. The product is built in 24 bits —an SP maximum
; reaches 999, and times 100 it does not fit in sixteen— and divided by
; subtraction, one bit at a time. It clobbers X and Y.
per_hundred:
.a8
    sta f:WRMPYA
    stx MED_P
    lda MED_P
    sta f:WRMPYB                ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta MED_R                   ; percent times the low byte
    sep #$20
.a8
    lda MED_P + 1
    sta f:WRMPYB                ; WRMPYA is still the percent
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL                ; percent times the high byte, which weighs 256
    xba
    pha
    and #$FF00
    clc
    adc MED_R
    sta MED_P
    pla
    and #$00FF
    adc #0                      ; the carry from the addition above
    sta MED_P + 2
    stz MED_R
    ldy #32
divide_it:
    asl MED_P
    rol MED_P + 2
    rol MED_R
    lda MED_R
    sec
    sbc #100
    bcc no_enters
    sta MED_R
    inc MED_P                   ; the quotient bit that just came in
no_enters:
    dey
    bne divide_it
    lda MED_P
    rts
.endproc

