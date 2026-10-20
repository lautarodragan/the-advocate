.segment "FAR2"

; --- using an item in battle -----------------------------------------------
;
; `Game_BattleAlgorithm::Item` with what this port knows how to do: the
; medicines that recover HP, since 2026-09-26 the ones that revive a fallen
; actor, and since 2026-10-04 the ones that recover SP. What goes in the list
; and how much it heals is not decided here but in `rm2k-snes-battle`, by
; `item_usable_in_battle` and `item_effect`, which is the model the battle
; tests use to predict the exact HP and SP; the converter emits the result in
; `item_battle`, `item_heal_rate`, `item_heal_hp`, `item_heal_sp_rate`,
; `item_heal_sp` and `item_medicine`, which is the same one `medicine_use`
; uses.
;
; All of this runs with the data bank at $7E, so **the inventory is read with
; absolute addressing**: `FAR_ITEMS` lives in that bank and in it the
; addresses are the same. The cartridge's tables go with `f:`.
;
; Since 2026-10-19 a special item casts its skill, which is RM2k's
; `Scene_Battle::AssignSkill` with the item: the list offers the ones whose
; skill the battle knows —`item_skill_in_battle` in `rm2k-snes-battle`, the
; converter's `item_skill`, the skill's row or $FF— to an actor their
; `actor_set` lets use them, and choosing one goes down the skill's path
; from the target on —see `ba_item_casting` and `ba_record_skill`—, with
; `ba_item_cast` telling `ba_skill_use` not to charge SP and the message to
; be the item's.

; Per actor in the party, whether the skill it chose is cast by a special
; item: `ba_record_skill` writes it on every skill an actor chooses, so it is
; never stale when the skill runs. The item is in `BA_ACC_ITEM`.
.pushseg
.segment "FARBSS"
ba_item_cast: .res BA_PARTY_MAX
.popseg

; The list of what can be used: one `k` per word in `BA_ITEM_LIST` and how
; many in `BA_ITEM_N`. It walks the items the ROM knows in the converter's
; order, which is RM2k's number order, like `Game_Party`.
.proc ba_items_list
.a8
.i16
    stz BA_ITEM_N
    stz BA_S0                   ; the `k` being looked at, a word
    stz BA_S0 + 1
other:
    ldx BA_S0
    cpx #ITEMS_ROM
    bcs ready
    lda f:item_battle, x
    beq next
    ; A special item, only for an actor its `actor_set` lets use it:
    ; `Window_Item` asks `Game_Party::IsItemUsable` with the actor giving the
    ; command. RM2k greys it out; here, like everything this list leaves out,
    ; it does not show.
    lda f:item_skill, x
    cmp #$FF
    beq listed
    jsr ba_actor_ldb            ; clobbers X
    ldx BA_S0
    jsr ba_item_actor_can
    beq next
    ldx BA_S0
listed:
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x            ; its RM2k number
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x            ; how many there are in the inventory
    beq next
    lda BA_ITEM_N
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda BA_S0
    sta BA_ITEM_LIST, x
    sep #$20
.a8
    inc BA_ITEM_N
    lda BA_ITEM_N
    cmp #BA_ITEM_MAX
    bcs ready
next:
    rep #$20
.a16
    inc BA_S0
    sep #$20
.a8
    bra other
ready:
    rts
.endproc

; The `k` at place A of the list, in X. Only A and X.
.proc ba_item_from_list
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda BA_ITEM_LIST, x
    tax
    sep #$20
.a8
    rts
.endproc

; One use of the `k` in X spent: `item_spend`, which counts the uses of an
; item of several. It is what RM2k does when it is chosen and not when it is
; used: otherwise the last one of an item could be handed out to two actors
; in the same turn. One without uses is not spent —`ConsumeItemUse` with
; `uses` 0—, which until 2026-10-19 the battle spent anyway and the menu did
; not.
.proc ba_item_consume
.a8
.i16
    jsl f:item_spend
    rts
.endproc

; How much the `k` in X heals the combatant `BA_MTGT`. It enters with an
; 8-bit A and leaves with a 16-bit A.
;
;     hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp
;
; capped against what the target is missing, which is easyrpg's `ChangeHp`.
; The uncapped one stays in `BA_S5`, which is what decides whether RM2k
; writes the HP line —`GetAffectedHp() > 0`, before `ChangeHp`—, and the
; target's offset in `BA_S4`.
.proc ba_item_heal
.a8
.i16
    stx BA_S3                   ; the `k`
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4                   ; the target's offset
    sep #$20
.a8
    ldx BA_S3
    lda f:item_heal_rate, x
    sta BA_T2
    ldx BA_S4
    rep #$20
.a16
    lda BA_ONE + BA_HPMAX, x
    jsr ba_rate_of
    sta BA_S5
    lda BA_S3
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

; The same with the SP, for the `k` in `BA_S3` on the combatant at offset
; `BA_S4` —what `ba_item_heal` leaves—: `recover_sp_rate * GetMaxSp() / 100
; + recover_sp`, capped by `ChangeSp` against what is missing. It enters with
; an 8-bit A and leaves with a 16-bit A. Clobbers `BA_S6`.
.proc ba_item_sp
.a8
.i16
    ldx BA_S3
    lda f:item_heal_sp_rate, x
    sta BA_T2
    ldx BA_S4
    rep #$20
.a16
    lda BA_ONE + BA_SPMAX, x
    jsr ba_rate_of
    sta BA_S6
    lda BA_S3
    asl a
    tax
    lda f:item_heal_sp, x
    clc
    adc BA_S6
    sta BA_S6
    ldx BA_S4
    lda BA_ONE + BA_SPMAX, x
    sec
    sbc BA_ONE + BA_SP, x
    cmp BA_S6
    bcc capped
    lda BA_S6
capped:
.a16
    rts
.endproc

; A16 the maximum and `BA_T2` the percentage: returns with A16 = percent *
; max / 100, easyrpg's integer division. In two halves, `(max / 100) *
; percent + (max % 100) * percent / 100`, which is the same number and never
; leaves sixteen bits: until 2026-10-04 it was the product in a word, and a
; maximum past 655 would overflow it, which with the SP —and with the items
; that raise a maximum— stopped being far away. Clobbers `temp`, `comp_and`,
; `comp_or23` and Y.
.proc ba_rate_of
.a16
.i16
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    pha                         ; max / 100
    lda comp_and
    jsr ba_mul                  ; (max % 100) * percent: at most 9900
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    pha                         ; and that over 100
    lda 3, s
    jsr ba_mul                  ; (max / 100) * percent
    clc
    adc 1, s
    plx
    plx
    rts
.endproc

; Whether LDB actor A8 can use the `k` in X: `Game_Actor::IsItemUsable`, the
; actor's bit in `item_actors`, eight bytes per item, actor 1 in bit 0 of the
; first. Z=0 if so. Clobbers `BA_T0`, X and Y.
.proc ba_item_actor_can
.a8
.i16
    dec a
    pha
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta BA_T0
    lda 1, s
    and #$00F8
    lsr a
    lsr a
    lsr a
    clc
    adc BA_T0
    tax
    sep #$20
.a8
    pla
    rep #$20
.a16
    and #$0007                  ; in sixteen bits: `tay` takes B too
    tay
    sep #$20
.a8
    lda f:item_actors, x
    cpy #0
    beq bit_ready
shift:
    lsr a
    dey
    bne shift
bit_ready:
    and #1
    rts
.endproc

; Whether the command being given casts a special item's skill: the Item
; command, with an item of the list whose `item_skill` is not $FF. While the
; target is chosen the cursor of the list stays where it was, so it is still
; the item chosen. Z=0 if so. Only A and X.
.proc ba_item_casting
.a8
.i16
    lda BA_COMMAND
    cmp #BA_COMMAND_USE
    bne no
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    lda f:item_skill, x
    cmp #$FF
    beq no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; `ba_record` of a skill, `BA_SKILL` on the target in `BA_T0`, for the actor
; giving the command, whether it chose it from its skills or a special item
; casts it —`ba_item_casting`—. The item is spent here, on choosing it, as a
; medicine is —see `a_is_item` in battle_run.s—, and is kept in
; `BA_ACC_ITEM` for the message and for a failed escape to give it back;
; `ba_item_cast` says which of the two it is.
.proc ba_record_skill
.a8
.i16
    jsr ba_item_casting
    beq from_skills
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    phx
    lda BA_ACTOR
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    pla
    sta BA_ACC_ITEM, x
    tax
    sep #$20
.a8
    jsr ba_item_consume
    lda #1
    bra marked
from_skills:
    lda #0
marked:
    pha
    lda BA_ACTOR
    jsr ba_ax
    pla
    sta f:ba_item_cast, x
    lda #BA_SKILL
    jmp ba_record
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
; not get past the list, like an empty command. It clobbers `BA_S0`, `BA_T0`,
; X and Y.
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
    ; `Game_Actor::IsItemUsable`: `Item::vExecute` spends it with no effect
    ; on one that cannot; here the cursor skips it, like the rest of this
    ; routine.
    lda BA_ONE + BA_NUMBER, x
    pha
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    pla
    jsr ba_item_actor_can
    beq no
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq fallen
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    lda f:item_medicine, x
    and #MED_KO_ONLY
    beq if
no:
    lda #0
    rts
fallen:
    lda BA_ITEM_SEL
    jsr ba_item_from_list
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
; * standing: the heal from `ba_item_heal` and the SP from `ba_item_sp`;
; * fallen and the item does not remove death: nothing, because
;   `ApplyHpEffect` does not touch a dead actor;
; * fallen and it removes it: the `SetHp(1)` of `RemoveStates` and then the
;   `ChangeHp(hp - 1)` of `ApplyStateEffect`, that is `max(1, heal)` with the
;   heal capped against the whole maximum, and the SP. It is the same thing
;   `medicine_use` does from the menu.
;
; The message's second line is RM2k's first result line, and the SP one, if
; there is an HP one before it, goes in a message of its own after this one,
; which is how `ProcessBattleActionParamEffects` shows them: one after the
; other, each in the place of the one before. `BA_MREVIVED` says the revived
; line goes; `BA_MHPLINE`, the HP one —`GetAffectedHp() > 0`, before the
; cap: a full actor reads "0 Recovered"—; `BA_MSP`, the SP it got back, whose
; line only goes if it is more than zero; and `BA_MSP_NEXT`, that it still
; has to be shown, which `ba_execute` looks at before the next action.
.proc ba_item_use
.a8
.i16
    stz BA_MREVIVED
    stz BA_MHPLINE
    stz BA_MSP_NEXT
    rep #$20
.a16
    stz BA_MHEAL
    stz BA_MSP
    sep #$20
.a8
    lda BA_MWHO
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda BA_ACC_ITEM, x
    sta BA_MITEM
    tax
    sep #$20
.a8
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
    ldx BA_MITEM
    jsr ba_item_heal
.a16
    sta BA_MHEAL
    ldx BA_S4                   ; the target's offset, from `ba_item_heal`
    lda BA_ONE + BA_HP, x
    clc
    adc BA_MHEAL
    sta BA_ONE + BA_HP, x
    lda BA_S5
    sep #$20
.a8
    beq sp
    lda #1
    sta BA_MHPLINE
    bra sp
fallen:
.a8
    lda BA_S2
    and #MED_RAISES
    beq nothing
    ldx BA_MITEM
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
    lda BA_MTGT
    jsr ba_attr_unshift         ; it gets up without its shifted ranks
sp:
    jsr ba_item_sp
.a16
    sta BA_MSP
    ldx BA_S4
    clc
    adc BA_ONE + BA_SP, x
    sta BA_ONE + BA_SP, x
    lda BA_MSP
    sep #$20
.a8
    beq nothing
    ; With an HP line or the revived one before it, the SP one waits for its
    ; own message.
    lda BA_MHPLINE
    ora BA_MREVIVED
    sta BA_MSP_NEXT
nothing:
.a8
    rts
.endproc
