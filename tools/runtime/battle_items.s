.segment "FAR"

; --- using an item in battle -----------------------------------------------
;
; `Game_BattleAlgorithm::Item` with what this port knows how to do: the
; medicines that recover HP, and since 2026-09-26 the ones that revive a fallen
; actor. What goes in the list and how much it heals is not decided here but in
; `rm2k-snes-battle`, by `item_usable_in_battle` and `item_effect`, which is
; the model `rom/pruebas/rpgmaker/test_batalla.py` uses to predict the exact
; HP; the converter emits the result in `item_battle`, `item_heal_rate`,
; `item_heal_hp` and `item_medicine`, which is the same one `medicine_use`
; uses.
;
; All of this runs with the data bank at $7E, so **the inventory is read with
; absolute addressing**: `FAR_ITEMS` lives in that bank and in it the
; addresses are the same. The cartridge's tables go with `f:`.

; The list of what can be used: one `k` per byte in `BA_ITEM_LIST` and how
; many in `BA_ITEM_N`. It walks the items the ROM knows in the converter's
; order, which is RM2k's number order, like `Game_Party`.
.proc ba_items_list
.a8
.i16
    lda #0
    sta BA_ITEM_N
    sta BA_S0                   ; the `k` being looked at
other:
    lda BA_S0
    cmp #ITEMS_ROM
    bcs ready
    lda BA_S0
    jsr ba_ax
    lda f:item_battle, x
    beq next
    lda BA_S0
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x            ; its RM2k number
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x            ; how many there are in the inventory
    beq next
    lda BA_ITEM_N
    jsr ba_ax
    lda BA_S0
    sta BA_ITEM_LIST, x
    inc BA_ITEM_N
    lda BA_ITEM_N
    cmp #BA_ITEM_MAX
    bcs ready
next:
    inc BA_S0
    bra other
ready:
    rts
.endproc

; The `k` at place A of the list. Only A and X.
.proc ba_item_from_list
.a8
.i16
    jsr ba_ax
    lda BA_ITEM_LIST, x
    rts
.endproc

; One less in the inventory of the `k` in A. It is what RM2k does when it is
; chosen and not when it is used: otherwise the last one of an item could be
; handed out to two actors in the same turn.
.proc ba_item_consume
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
    beq ready
    dec a
    sta FAR_ITEMS, x
ready:
    rts
.endproc

; How much the `k` in A heals the combatant `BA_MTGT`. It enters with an
; 8-bit A and leaves with a 16-bit A.
;
;     hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp
;
; capped against what the target is missing, which is easyrpg's `ChangeHp`.
; The product fits in a word because the converter stops if any actor has
; more than 655 HP.
.proc ba_item_heal
.a8
.i16
    sta BA_S3                   ; the `k`
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4                   ; the target's offset
    sep #$20
.a8
    lda BA_S3
    jsr ba_ax
    lda f:item_heal_rate, x
    sta BA_T2                   ; the product's byte
    ldx BA_S4
    rep #$20
.a16
    lda BA_ONE + BA_HPMAX, x
    jsr ba_mul                  ; rate * hp_max, in a word
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sta BA_S5
    lda BA_S3
    and #$00FF
    asl a
    tax
    lda f:item_heal_hp, x
    clc
    adc BA_S5
    sta BA_S5                   ; what it would heal
    ; and what the target is missing, which is the cap
    ldx BA_S4
    lda BA_ONE + BA_HPMAX, x
    sec
    sbc BA_ONE + BA_HP, x
    cmp BA_S5
    bcc capped
    lda BA_S5
capped:
.a16
    rts
.endproc

; Whether the cursor for who gets it can stop on actor A8, with the item that
; `BA_ITEM_SEL` marks: Z=0 if yes. The actor has to be in the party and the
; item has to be of use to them —on a fallen one, only one that removes the
; death state; on one standing, any that is not `ko_only`—, which are the two
; exits of `Game_BattleAlgorithm::Item::vExecute` with no effect.
;
; **RM2k lets it stop on anyone** —`status_window` with `ChoiceMode_All`—
; and the item that is of no use is spent doing nothing. Here the cursor skips
; them, which is what it already did with the fallen before reviving them
; existed: spending a potion on a dead actor is not something anybody wants
; to do. If it is of use to nobody —an elixir with everyone standing—, A does
; not get past the list, like an empty command. It clobbers `BA_S0` and X.
.proc ba_item_usable_on
.a8
.i16
    sta BA_S0
    cmp BA_NACTORS
    bcs no
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq no
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq fallen
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    jsr ba_ax
    lda f:item_medicine, x
    and #MED_KO_ONLY
    beq if
no:
    lda #0
    rts
fallen:
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    jsr ba_ax
    lda f:item_medicine, x
    and #MED_RAISES
    beq no
if:
    lda #1
    rts
.endproc

; The item actor `BA_MWHO` chose, on `BA_MTGT`: heals or revives, records
; how much, and leaves the message ready. It rolls no dice: an item does not
; miss and nobody dodges it, and **the target is not re-aimed**, which is the
; opposite of an attack: if it changed between being chosen and its turn
; coming, the item is spent anyway and does whatever `vExecute` does with it
; as it is now.
;
; It is `item_effect` of `rm2k-snes-battle`, branch by branch:
;
; * standing and `ko_only`: nothing, `SetIsSuccess` with no effect;
; * standing: the heal from `ba_item_heal`;
; * fallen and the item does not remove death: nothing, because
;   `ApplyHpEffect` does not touch a dead actor;
; * fallen and it removes it: the `SetHp(1)` of `RemoveStates` and then the
;   `ChangeHp(hp - 1)` of `ApplyStateEffect`, that is `max(1, heal)` with the
;   heal capped against the whole maximum. It is the same thing
;   `medicine_use` does from the menu.
;
; `BA_MREVIVED` tells the message which of the two lines below goes.
.proc ba_item_use
.a8
.i16
    stz BA_MREVIVED
    lda BA_MWHO
    jsr ba_ax
    lda BA_ACC_ITEM, x
    sta BA_MITEM
    jsr ba_ax
    lda f:item_medicine, x
    sta BA_S2                   ; its flags
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq fallen
    lda BA_S2
    and #MED_KO_ONLY
    bne nothing
    lda BA_MITEM
    jsr ba_item_heal
.a16
    sta BA_MHEAL
    ldx BA_S4                   ; the target's offset, from `ba_item_heal`
    lda BA_ONE + BA_HP, x
    clc
    adc BA_MHEAL
    sta BA_ONE + BA_HP, x
    sep #$20
.a8
    rts
fallen:
.a8
    lda BA_S2
    and #MED_RAISES
    beq nothing
    lda BA_MITEM
    jsr ba_item_heal            ; with zero HP, the cap is the whole maximum
.a16
    cmp #0
    bne raises
    lda #1                      ; the `SetHp(1)`, even if the item heals nothing
raises:
    sta BA_MHEAL
    ldx BA_S4
    sta BA_ONE + BA_HP, x
    sep #$20
.a8
    lda #1
    sta BA_MREVIVED
    rts
nothing:
.a8
    rep #$20
.a16
    stz BA_MHEAL
    sep #$20
.a8
    rts
.endproc
