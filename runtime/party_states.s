; In `FAR3`, like the other bodies that came after bank 0 filled up: every
; door in is a `jsl`, and each one sets the data bank to $7E and gives it
; back, so it runs whatever the caller's.
.segment "FAR3"
.a8
.i16

; --- the party's conditions ---------------------------------------------------
;
; RM2k's actors hold conditions —`Game_Actor`'s `states`— on the map as in
; battle, and they travel in the save: a poison caught in a fight keeps
; hurting while the hero walks, until an antidote or an inn. Since
; 2026-11-01 each actor has here the same four places an enemy has in
; battle —see `ST_PLACES` in battle_states.s, which says why four and how a
; place is laid out: the condition's LDB number in the low byte, how long it
; has been held in the high one, in LDB order and the empty ones at the
; end—. The battle takes them into its own places when it starts and gives
; them back when a troop page runs and when it ends: see `ba_st_actor_in`
; and `ba_st_actor_out`.
;
; **The dead one is not a place**: an actor with no HP is a fallen one, as
; everywhere in this runtime —see `medicine_use`—. So adding it drops the HP
; to zero, asking for it asks for the HP, and its priority is counted as
; held when the HP are zero: that is how `State::Add`'s purge takes the
; other conditions away from a fallen one, as RM2k does when it dies.
;
; What each piece is in easyrpg:
;
; * `act_st_add` and `act_st_remove`: `ChangeCondition`, with `State::Add`
;   —held again it starts from 1; the ones ten points of priority below the
;   highest go away— and `State::Remove`. On the map RM2k adds even a
;   `battle_only` one.
; * `act_st_clear`: `FullHeal`'s `RemoveAllStates`, and the inn's.
; * `act_st_fallen`: the purge a death does, after a loss that kills.
; * `state_step`: `Game_Party::ApplyStateDamage`, each pad step.
; * The battle's end, `RemoveBattleStates`: `ba_st_actor_out` in
;   battle_states.s, with `state_end`.
;
; Equipment that gives or prevents a condition —`PermanentStates`— is not
; here: no game of the nine equips one that gives it.

ACT_ST_BYTES = 8                ; `ST_BYTES`, which battle_states.s declares later
ST_PLACES_MAP = ACT_ST_BYTES / 2
ACT_ST_DEAD = 1                 ; `State::kDeathID`

.pushseg
.segment "FARBSS"
act_st_actor: .res 1            ; scratch of this file: the actor,
act_st_id:    .res 1            ; the condition,
act_st_base:  .res 2            ; where its places start,
act_st_k:     .res 2            ; the place being looked at,
act_st_top:   .res 1            ; the highest priority held,
act_st_flash: .res 1            ; and whether a step hurt someone
act_st_n:     .res 2            ; `state_step`'s divisor
act_st_r:     .res 2            ; and remainder,
act_st_lo:    .res 2            ; the low word of the steps being divided,
act_st_amt:   .res 2            ; and the amount of the change
act_st_end:   .res 2            ; `act_st_drop`'s last place
.popseg

; Nobody holds anything, and the party has not taken a step: a new game.
; From `boot`, next to `hp_initial_set`.
.proc party_states_clear
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    ldx #0
    rep #$20
.a16
loop:
    stz .loword(far_act_states), x
    inx
    inx
    cpx #ACTORS_N * ACT_ST_BYTES
    bcc loop
    stz .loword(far_party_steps)
    stz .loword(far_party_steps) + 2
    sep #$20
.a8
    plb
    rtl
.endproc

; A8 = the actor; X = where its places start, inside `far_act_states`.
; Clobbers A.
.proc act_st_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times ACT_ST_BYTES
    tax
    sep #$20
.a8
    rts
.endproc
.assert ACT_ST_BYTES = 8, error, "act_st_x multiplies by eight"

; A8 = a condition; X = its row, sixteen bits. Clobbers A.
.proc act_st_row
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

; `ChangeCondition` on one actor, for `actor_change_one`: A8 the actor, the
; condition in the low byte of `temp`, and `ACT_TAKE` in `temp + 3` to
; take it away. A condition the cartridge's tables do not have is nobody's,
; and does nothing. Keeps `temp`; clobbers X and Y.
.proc act_st_change
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    sta .loword(act_st_actor)
    lda temp
    sta .loword(act_st_id)
    beq done
    rep #$20
.a16
    and #$00FF
    cmp #STATES_N               ; a word: there may be 256
    sep #$20
.a8
    bcs done
    lda temp + 3
    and #ACT_TAKE
    bne removes
    lda .loword(act_st_id)
    cmp #ACT_ST_DEAD
    beq dies
    jsr act_st_add
    bra done
removes:
    jsr act_st_remove
done:
    plb
    rtl
dies:
    ; `AddState(kDeathID)`: the HP at zero, and the purge.
    lda .loword(act_st_actor)
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda #0
    sta f:FAR_LENGTH + FAR_HP, x
    sep #$20
.a8
    jsr act_st_purge
    bra done
.endproc

; `State::Add` of `act_st_id` on `act_st_actor`: held again, from 1;
; otherwise in its place by LDB number, if there is room —a fifth is not
; given, as in battle—. Then the purge. With the data bank at $7E. Clobbers
; A, X and Y.
.proc act_st_add
.a8
.i16
    lda .loword(act_st_actor)
    jsr act_st_x
    stx .loword(act_st_base)
    ldy #ST_PLACES_MAP
seek:
    lda .loword(far_act_states), x
    beq here                    ; the empty ones go at the end
    cmp .loword(act_st_id)
    beq again
    bcs here                    ; past it: it goes here
    inx
    inx
    dey
    bne seek
    rts                         ; four already, all before it: not given
again:
    lda #1
    sta .loword(far_act_states) + 1, x
    jmp act_st_purge
here:
    ; X is where it goes. If the last place is taken there is no room.
    phx
    ldx .loword(act_st_base)
    lda .loword(far_act_states) + ACT_ST_BYTES - 2, x
    plx
    cmp #0                      ; the `plx` left Z from X: AGENTS.md's trap
    beq room
    rts
room:
    ; The ones from X on move one place, from the end.
    stx .loword(act_st_k)
    rep #$20
.a16
    lda .loword(act_st_base)
    clc
    adc #ACT_ST_BYTES - 2
    tay                         ; the one being written
shift:
    cpy .loword(act_st_k)
    beq shifted
    tyx
    lda .loword(far_act_states) - 2, x
    sta .loword(far_act_states), x
    dey
    dey
    bra shift
shifted:
    ldx .loword(act_st_k)
    lda .loword(act_st_id)
    and #$00FF
    ora #$0100                  ; held for 1
    sta .loword(far_act_states), x
    sep #$20
.a8
    jmp act_st_purge
.endproc

; `State::Add`'s purge on `act_st_actor`: the ones ten points of priority
; below the highest held go away, the dead one counted as held when the HP
; are zero. With the data bank at $7E. Clobbers A, X and Y.
.proc act_st_purge
.a8
.i16
    stz .loword(act_st_top)
    lda .loword(act_st_actor)
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    sep #$20
.a8
    bne alive
    lda f:state_priority + ACT_ST_DEAD
    sta .loword(act_st_top)
alive:
    lda .loword(act_st_actor)
    jsr act_st_x
    stx .loword(act_st_base)
    ldy #ST_PLACES_MAP
highest:
    lda .loword(far_act_states), x
    beq found
    phx
    jsr act_st_row
    lda f:state_priority, x
    plx
    cmp .loword(act_st_top)
    bcc lower
    sta .loword(act_st_top)
lower:
    inx
    inx
    dey
    bne highest
found:
    ldx .loword(act_st_base)
    stx .loword(act_st_k)
other:
    ldx .loword(act_st_k)
    lda .loword(far_act_states), x
    beq purged
    jsr act_st_row
    lda f:state_priority, x
    clc
    adc #10
    bcs stays                   ; cannot be ten below anything
    cmp .loword(act_st_top)
    beq goes
    bcs stays
goes:
    ldx .loword(act_st_k)
    jsr act_st_drop
    bra other                   ; the next one came down to this place
stays:
    rep #$20
.a16
    inc .loword(act_st_k)
    inc .loword(act_st_k)
    lda .loword(act_st_k)
    sec
    sbc .loword(act_st_base)
    cmp #ACT_ST_BYTES
    sep #$20
.a8
    bcc other
purged:
    rts
.endproc

; X = a place inside `far_act_states`, of the actor whose places start at
; `act_st_base`: out, and the ones after it come down one. Clobbers A and X.
.proc act_st_drop
.a8
.i16
    rep #$20
.a16
    lda .loword(act_st_base)
    clc
    adc #ACT_ST_BYTES - 2
    sta .loword(act_st_end)
down:
    txa
    cmp .loword(act_st_end)
    bcs last
    lda .loword(far_act_states) + 2, x
    sta .loword(far_act_states), x
    inx
    inx
    bra down
last:
    stz .loword(far_act_states), x
    sep #$20
.a8
    rts
.endproc

; `State::Remove` of `act_st_id` from `act_st_actor`. With the data bank at
; $7E. Clobbers A, X and Y.
.proc act_st_remove
.a8
.i16
    lda .loword(act_st_actor)
    jsr act_st_x
    stx .loword(act_st_base)
    ldy #ST_PLACES_MAP
seek:
    lda .loword(far_act_states), x
    beq none
    cmp .loword(act_st_id)
    beq found
    inx
    inx
    dey
    bne seek
none:
    rts
found:
    phx
    jsr act_st_drop
    plx
    rts
.endproc

; `RemoveAllStates`, for `FullHeal` and the inn: actor A8 holds nothing.
; Clobbers A and X.
.proc act_st_clear
.a8
.i16
    jsr act_st_x
    rep #$20
.a16
    lda #0
    sta f:far_act_states, x
    sta f:far_act_states + 2, x
    sta f:far_act_states + 4, x
    sta f:far_act_states + 6, x
    sep #$20
.a8
    rtl
.endproc
.assert ACT_ST_BYTES = 8, error, "act_st_clear clears four places"

; Actor A8 has just fallen, from a loss that kills: the purge its death
; does. Keeps `temp`; clobbers A, X and Y.
.proc act_st_fallen
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    sta .loword(act_st_actor)
    jsr act_st_purge
    plb
    rtl
.endproc

; The battle's end, after `ba_sync_out` gave each actor back its places:
; `Game_Battle::Terminate`'s `RemoveBattleStates` on the party. A fallen one
; first loses what its death purges —the battle does not purge when someone
; falls: it counts here, where it is kept—; then each one loses the ones
; `state_end` marks, the `battle_only` ones and the persistent ones that
; wear off on their own. Clobbers A, X and Y.
.proc act_st_battle_end
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    ldx #0
member:
    cpx party_n
    bcs done
    phx
    lda party, x
    sta .loword(act_st_actor)
    jsr act_st_purge            ; only a fallen one changes: see its top
    lda .loword(act_st_actor)
    jsr act_st_x
    stx .loword(act_st_base)
    stx .loword(act_st_k)
other:
    ldx .loword(act_st_k)
    lda .loword(far_act_states), x
    beq next
    jsr act_st_row
    lda f:state_end, x
    beq stays
    ldx .loword(act_st_k)
    jsr act_st_drop
    bra other                   ; the next one came down to this place
stays:
    rep #$20
.a16
    inc .loword(act_st_k)
    inc .loword(act_st_k)
    lda .loword(act_st_k)
    sec
    sbc .loword(act_st_base)
    cmp #ACT_ST_BYTES
    sep #$20
.a8
    bcc other
next:
    plx
    inx
    bra member
done:
    plb
    rtl
.endproc

; `HasState`, for `ConditionalBranch`'s `IsActorConditioned`: actor A8 and
; the condition in `temp + 2`; A8 = 1 and Z clear if it holds it. The dead
; one is zero HP. Clobbers X.
.proc act_st_has
.a8
.i16
    pha
    lda temp + 2
    cmp #ACT_ST_DEAD
    bne place
    pla
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    sep #$20
.a8
    beq yes
    bra no
place:
    pla
    jsr act_st_x
    phy
    ldy #ST_PLACES_MAP
seek:
    lda f:far_act_states, x
    beq none
    cmp temp + 2
    beq found
    inx
    inx
    dey
    bne seek
none:
    ply
no:
    lda #0
    rtl
found:
    ply
yes:
    lda #1
    rtl
.endproc

; --- each step --------------------------------------------------------------
;
; `Game_Party::ApplyStateDamage`, which `Game_Player::UpdateNextMovementAction`
; runs after `IncSteps` and before `UpdateEncounterSteps`, only for the pad's
; steps: `after_step` in hero.s calls it next to `encounter_step`. The party
; counts one more step, and each condition one of its actors holds whose
; `hp_change_map_steps` divides the count changes its HP by
; `hp_change_map_val` —a loss, or a gain with `ChangeType_gain`—, and the
; same with SP. Both are `actor_change_one`, so a loss never kills —the
; `ChangeHp(-val, false)`— and a fallen one does not change; the SP do not
; go below zero. A loss of either flashes the screen as a hurting terrain
; does —`FlashMapStepDamage`, `flash_step_damage` in terrain_steps.s—, even
; on a fallen one, as there `damage` is set before `ChangeHp`.
;
; RM2k walks the conditions and, for each, the actors; this walks the
; actors and, for each, its conditions. The HP come out the same unless one
; actor holds a condition that heals and another that hurts on the same
; step: no game has one that heals walking.
;
; The count is easyrpg's `steps`, four bytes as in the save, and the
; division is by shifts —`hp_change_map_steps` goes up to 999—, done only
; for a condition that changes something on the map.
.proc state_step
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    inc .loword(far_party_steps)
    bne counted
    inc .loword(far_party_steps) + 2
counted:
    sep #$20
.a8
    stz .loword(act_st_flash)
    ldx #0
slot:
    cpx party_n
    bcs walked
    phx
    lda party, x
    sta .loword(act_st_actor)
    jsr act_st_x
    stx .loword(act_st_k)
    ldy #ST_PLACES_MAP
place:
    phy
    ldx .loword(act_st_k)
    lda .loword(far_act_states), x
    beq actor_done
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; `state_map`'s row: four words
    tax
    sep #$20
.a8
    phx
    lda #0                      ; the HP
    jsr change
    plx
    inx
    inx
    inx
    inx
    lda #ACT_SP
    jsr change
    rep #$20
.a16
    inc .loword(act_st_k)
    inc .loword(act_st_k)
    sep #$20
.a8
    ply
    dey
    bne place
    bra next_actor
actor_done:
    ply
next_actor:
    plx
    inx
    bra slot
walked:
    lda .loword(act_st_flash)
    beq done
    jsr flash_step_damage
done:
    plb
    ply
    plx
    rtl

; X = the steps' word of a row of `state_map`, the amount after it; A8 =
; `what` of `actor_change_one`, the HP or the SP. Clobbers A, X, Y, `temp`
; and this file's scratch.
change:
    pha
    rep #$20
.a16
    lda f:state_map, x
    beq nothing                 ; nothing on the map: the usual case
    sta .loword(act_st_n)
    lda f:state_map + 2, x
    sta .loword(act_st_amt)
    jsr divides
    bne nothing
    lda .loword(act_st_amt)
    sta temp
    bpl gains
    sep #$20
.a8
    lda #1
    sta .loword(act_st_flash)
gains:
    sep #$20
.a8
    pla
    sta temp + 3
    lda .loword(act_st_actor)
    jsl f:actor_change_one_l
    rts
nothing:
    sep #$20
.a8
    pla
    rts

; In A16: Z set if `act_st_n` divides the party's steps. The remainder,
; one bit at a time from the top: it never goes past twice the divisor,
; which fits in sixteen bits. Clobbers A and Y.
.a16
divides:
    stz .loword(act_st_r)
    ldy #32
    lda .loword(far_party_steps)
    sta .loword(act_st_lo)
    lda .loword(far_party_steps) + 2
    pha
one_bit:
    asl .loword(act_st_lo)
    lda 1, s
    rol a
    sta 1, s
    rol .loword(act_st_r)
    lda .loword(act_st_r)
    cmp .loword(act_st_n)
    bcc below
    sbc .loword(act_st_n)
    sta .loword(act_st_r)
below:
    dey
    bne one_bit
    pla
    lda .loword(act_st_r)
    rts
.a8
.endproc
