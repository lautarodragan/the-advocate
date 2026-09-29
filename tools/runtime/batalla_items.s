.segment "FAR"

; --- using an item in battle -----------------------------------------------
;
; `Game_BattleAlgorithm::Item` with what this port knows how to do: the
; medicines that recover HP, and since 2026-09-26 the ones that revive a
; fallen actor. What goes in the list and how much it heals is not decided
; here but in `batalla.item_usable_en_batalla` and `batalla.efecto_de_item`,
; which is the model `rom/pruebas/rpgmaker/test_batalla.py` uses to predict
; the exact HP; the converter emits the result in `item_batalla`,
; `item_cura_rate`, `item_cura_hp` and `item_medicina`, which is the same one
; `medicine_use` uses.
;
; All of this runs with the data bank at $7E, so **the inventory is read with
; absolute addressing**: `FAR_ITEMS` lives in that bank and in it the
; addresses are the same. The cartridge's tables go with `f:`.

; The list of what can be used: one `k` per byte in `BT_ITEM_LIST` and how
; many in `BT_ITEM_N`. It walks the items the ROM knows in the converter's
; order, which is RM2k's number order, like `Game_Party`.
.proc bt_items_list
.a8
.i16
    lda #0
    sta BT_ITEM_N
    sta BT_S0                   ; the `k` being looked at
otro:
    lda BT_S0
    cmp #ITEMS_ROM
    bcs ready
    lda BT_S0
    jsr bt_ax
    lda f:item_batalla, x
    beq siguiente
    lda BT_S0
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
    beq siguiente
    lda BT_ITEM_N
    jsr bt_ax
    lda BT_S0
    sta BT_ITEM_LIST, x
    inc BT_ITEM_N
    lda BT_ITEM_N
    cmp #BT_ITEM_MAX
    bcs ready
siguiente:
    inc BT_S0
    bra otro
ready:
    rts
.endproc

; The `k` at place A of the list. Only A and X.
.proc bt_item_from_list
.a8
.i16
    jsr bt_ax
    lda BT_ITEM_LIST, x
    rts
.endproc

; One less in the inventory of the `k` in A. It is what RM2k does when it is
; chosen and not when it is used: otherwise the last one of an item could be
; handed out to two actors in the same turn.
.proc bt_item_consume
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

; How much the `k` in A heals the combatant `BT_MBLA`. It enters with an
; 8-bit A and leaves with a 16-bit A.
;
;     hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp
;
; capped against what the target is missing, which is easyrpg's `ChangeHp`.
; The product fits in a word because the converter stops if any actor has
; more than 655 HP.
.proc bt_item_heal
.a8
.i16
    sta BT_S3                   ; the `k`
    lda BT_MBLA
    jsr bt_x
    rep #$20
.a16
    txa
    sta BT_S4                   ; the target's offset
    sep #$20
.a8
    lda BT_S3
    jsr bt_ax
    lda f:item_cura_rate, x
    sta BT_T2                   ; the product's byte
    ldx BT_S4
    rep #$20
.a16
    lda BT_ONE + BT_HPMAX, x
    jsr bt_mul                  ; rate * hp_max, in a word
    sta temp
    lda #100
    sta temp + 2
    jsr bt_div
    sta BT_S5
    lda BT_S3
    and #$00FF
    asl a
    tax
    lda f:item_cura_hp, x
    clc
    adc BT_S5
    sta BT_S5                   ; what it would heal
    ; and what the target is missing, which is the cap
    ldx BT_S4
    lda BT_ONE + BT_HPMAX, x
    sec
    sbc BT_ONE + BT_HP, x
    cmp BT_S5
    bcc topado
    lda BT_S5
topado:
.a16
    rts
.endproc

; Whether the cursor for who gets it can stop on actor A8, with the item that
; `BT_ITEM_SEL` marks: Z=0 if yes. The actor has to be in the party and the
; item has to be of use to them —on a fallen one, only one that removes the
; death state; on one standing, any that is not `ko_only`—, which are the two
; exits of `Game_BattleAlgorithm::Item::vExecute` with no effect.
;
; **RM2k lets it stop on anyone** —`status_window` with `ChoiceMode_All`—
; and the item that is of no use is spent doing nothing. Here the cursor skips
; them, which is what it already did with the fallen before reviving them
; existed: spending a potion on a dead actor is not something anybody wants
; to do. If it is of use to nobody —an elixir with everyone standing—, A does
; not get past the list, like an empty command. It clobbers `BT_S0` and X.
.proc bt_item_usable_on
.a8
.i16
    sta BT_S0
    cmp BT_NACT
    bcs no
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HAS
    beq no
    rep #$20
.a16
    lda BT_ONE + BT_HP, x
    sep #$20
.a8
    beq caido
    lda BT_ITEM_SEL
    jsr bt_item_from_list
    jsr bt_ax
    lda f:item_medicina, x
    and #MED_KO_ONLY
    beq si
no:
    lda #0
    rts
caido:
    lda BT_ITEM_SEL
    jsr bt_item_from_list
    jsr bt_ax
    lda f:item_medicina, x
    and #MED_RAISES
    beq no
si:
    lda #1
    rts
.endproc

; The item actor `BT_MQUIEN` chose, on `BT_MBLA`: heals or revives, records
; how much, and leaves the message ready. It rolls no dice: an item does not
; miss and nobody dodges it, and **the target is not re-aimed**, which is the
; opposite of an attack: if it changed between being chosen and its turn
; coming, the item is spent anyway and does whatever `vExecute` does with it
; as it is now.
;
; It is `batalla.efecto_de_item`, branch by branch:
;
; * standing and `ko_only`: nothing, `SetIsSuccess` with no effect;
; * standing: the heal from `bt_item_heal`;
; * fallen and the item does not remove death: nothing, because
;   `ApplyHpEffect` does not touch a dead actor;
; * fallen and it removes it: the `SetHp(1)` of `RemoveStates` and then the
;   `ChangeHp(hp - 1)` of `ApplyStateEffect`, that is `max(1, heal)` with the
;   heal capped against the whole maximum. It is the same thing
;   `medicine_use` does from the menu.
;
; `BT_MREVIVIO` tells the message which of the two lines below goes.
.proc bt_item_use
.a8
.i16
    stz BT_MREVIVIO
    lda BT_MQUIEN
    jsr bt_ax
    lda BT_ACC_ITEM, x
    sta BT_MITEM
    jsr bt_ax
    lda f:item_medicina, x
    sta BT_S2                   ; its flags
    lda BT_MBLA
    jsr bt_x
    rep #$20
.a16
    lda BT_ONE + BT_HP, x
    sep #$20
.a8
    beq caido
    lda BT_S2
    and #MED_KO_ONLY
    bne nothing
    lda BT_MITEM
    jsr bt_item_heal
.a16
    sta BT_MCURA
    ldx BT_S4                   ; the target's offset, from `bt_item_heal`
    lda BT_ONE + BT_HP, x
    clc
    adc BT_MCURA
    sta BT_ONE + BT_HP, x
    sep #$20
.a8
    rts
caido:
.a8
    lda BT_S2
    and #MED_RAISES
    beq nothing
    lda BT_MITEM
    jsr bt_item_heal            ; with zero HP, the cap is the whole maximum
.a16
    cmp #0
    bne levanta
    lda #1                      ; the `SetHp(1)`, even if the item heals nothing
levanta:
    sta BT_MCURA
    ldx BT_S4
    sta BT_ONE + BT_HP, x
    sep #$20
.a8
    lda #1
    sta BT_MREVIVIO
    rts
nothing:
.a8
    rep #$20
.a16
    stz BT_MCURA
    sep #$20
.a8
    rts
.endproc
