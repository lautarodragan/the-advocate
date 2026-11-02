.segment "FAR3"
.a8
.i16

; --- a special item cast from the items screen ---------------------------------
;
; RPG_RT's `Scene_Item` with a `Type_special` item: its skill —the
; converter's `item_map_skill`, a row of `skill_*` or $FF, which the screens
; stage greys the item by— is cast as the skills screen casts it, but the
; item pays instead of the SP. A switch skill never comes here: the
; converter gives the item the skill's switch in `item_switch`, and
; `items_screen` turns it on as a switch item's. Any other opens the actor
; choice for the item —its name and how many are left, as a medicine's—,
; with the bar where the skill's scope says: over everyone for a skill on
; the party, and free for one on oneself, which RPG_RT does not lock for an
; item —see `target_scope`—. A on a row comes here, through `target_use`.
;
; It lives in `FAR3`, like the other bodies that came after bank 0 filled
; up, and reaches the skills screen's effect, `sk_cast`, through its `jsl`
; door in `FAR2`, `sk_cast_far`: `FAR2` itself had no room left for this
; in Sunset over Imdahl.

.pushseg
.segment "FARBSS"
ic_best:  .res 1                ; who casts it, $FF nobody yet
ic_level: .res 1                ; and their level
ic_k:     .res 1                ; the place in `party` being looked at
.popseg

; The item `item_sel` on actor A, from the actor choice:
; `Game_Party::UseItem(item_id, target)` with a special item. The one who
; casts it is the highest level in the party who can act and whom the
; item's `actor_set` lets use it, the first one of a tie
; —`GetHighestLeveledActorWhoCanUse`—; for a skill on oneself it is the one
; chosen, who must be let use it too, and someone has to be found all the
; same —`IsItemUsable`, which asks for someone able to act—. Then
; `sk_cast`, with that one's attack and spirit, and the item spent if it was
; of use —`ConsumeItemUse`, `item_spend`—. Returns with A8 at 1 if it was of
; use and at 0 if not, Z to match, as `medicine_use`. Entered with `jsl`
; from `target_use`, with the data bank at 0. Clobbers X, Y, `temp` and the
; `MED_*` scratch.
.proc item_cast_use
.a8
.i16
    sta f:MED_ACTOR             ; the one chosen
    ; Is there any left? With the choice open the last one can be spent and
    ; A still pressed: `Scene_ActorTarget::UpdateItem`'s count.
    rep #$20
.a16
    lda item_sel
    asl a
    tax
    lda f:item_id, x
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    bne remains
    jmp refused
remains:
    ; Who would cast it.
    lda #$FF
    sta f:ic_best
    lda #0
    sta f:ic_level
    sta f:ic_k
seek:
    lda f:ic_k
    cmp party_n
    bcs sought
    jsr member
    jsr ic_can_act
    beq next
    jsr member
    jsr ic_can_use
    beq next
    jsr member
    jsr ic_level_of
    cmp f:ic_level
    beq next                    ; a tie: the first one stays
    bcc next
    sta f:ic_level
    jsr member
    sta f:ic_best
next:
    lda f:ic_k
    inc a
    sta f:ic_k
    bra seek
sought:
    lda f:ic_best
    cmp #$FF
    beq refused
    ; The skill, and for one on oneself the one chosen casts it.
    ldx item_sel
    lda f:item_map_skill, x
    sta f:sk_used
    jsr ic_ax
    lda f:skill_scope, x
    cmp #BA_SCOPE_ONE
    bne fixed
    lda f:MED_ACTOR
    jsr ic_can_use
    beq refused
    lda f:MED_ACTOR
    sta f:ic_best
fixed:
    lda f:ic_best
    sta f:sk_actor
    jsl f:sk_cast_far
    ; Nothing of a material, whatever `sk_heal_one` left in `MED_FLAGS`: the
    ; actor choice repaints the rows, not all.
    lda #0
    sta f:MED_FLAGS
    lda f:MED_USED
    beq refused
    ldx item_sel
    jsl f:item_spend
    lda #1
    rtl
refused:
    lda #0
    rtl

; The actor at place `ic_k` of the party, in A. Clobbers X.
member:
    lda f:ic_k
    jsr ic_ax
    lda party, x
    rts
.endproc

; A8 into X, sixteen bits: the battle's `ba_ax`, which is `FAR2`'s. Only X.
.proc ic_ax
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; Whether actor A can act —`Game_Battler::CanAct`—: standing, and holding
; no condition whose restriction is "does nothing". A8 at 1 if it can and 0
; if not, Z to match. Clobbers X and Y.
.proc ic_can_act
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    sep #$20
.a8
    bne standing                ; `sep` leaves Z as the HP left it
    pla
    lda #0
    rts
standing:
    pla
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    .assert ACT_ST_BYTES = 8, error, "ic_can_act multiplies by eight"
    tax
    sep #$20
.a8
    ldy #ST_PLACES_MAP
place:
    lda f:far_act_states, x
    beq can                     ; the empty ones go at the end
    phx
    jsr ic_ax
    lda f:state_restrict, x
    plx
    cmp #1
    beq cannot
    inx
    inx
    dey
    bne place
can:
    lda #1
    rts
cannot:
    lda #0
    rts
.endproc

; Whether the item `item_sel` lets actor A use it —`Game_Actor::IsItemUsable`,
; its `actor_set`—: its bit in `item_actors`, eight bytes per item, actor 1
; in bit 0 of the first, as `medicine_use` reads it. A8 at 1 or 0, Z to
; match. Clobbers X and Y.
.proc ic_can_use
.a8
.i16
    rep #$20
.a16
    and #$00FF
    dec a
    pha
    lda item_sel
    asl a
    asl a
    asl a
    sta temp
    lda 1, s
    lsr a
    lsr a
    lsr a
    clc
    adc temp
    tax
    pla
    and #$0007
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

; Actor A's current level, in A: `actor_level_of`, which lives in `FAR` and
; is reached with `jsr`. One without an experience slot cannot be in the
; party, and answers 1. Clobbers X.
.proc ic_level_of
.a8
.i16
    jsr ic_ax
    lda f:actor_exp_k, x
    cmp #$FF
    beq no_slot
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + EXP_LEVEL, x
    rts
no_slot:
    lda #1
    rts
.endproc
