.segment "FAR2"

; --- the conditions in battle ---------------------------------------------------
;
; RM2k's states, `Game_Battler`'s, with what the battle does with them —and the
; model too, `Held` in `rm2k-snes-battle`'s `simulate.rs`, which rolls in the
; same order: that order is the contract—. **Only enemies get them**, from a
; troop page's `ChangeMonsterCondition` (OP_MONSTER_STATE): no skill, attack
; or item gives one, and the actors have none. What a condition is comes from
; the converter, one row per LDB number in the `state_*` tables.
;
; What they do, and where:
;
; * `AddState` and `RemoveStates`: `ba_st_add` and `ba_st_remove`. Given again,
;   a condition starts counting from 1; the ones ten points of priority below
;   the highest go away; and when the restriction is no longer normal —or, on
;   removing, when it changed— the action it had this turn is lost: its
;   command becomes `BA_NONE`, which is `Game_BattleAlgorithm::None`.
; * The restriction: `ba_enemy_actions` —`SetStateRestrictedAction`— and
;   `ba_st_begin` —`PrepareBattleAction`, when its turn comes—. One that
;   cannot act does nothing; one that attacks its own side (Control) or the
;   other hits a living one there, chosen with a roll each time.
; * `BattleStateHeal`, when its action begins: `ba_st_heal`, and the message
;   of the condition with the highest priority, which `ba_execute` shows
;   before the action.
; * The hit: `ba_attack` lowers the source's chance with `reduce_hit_ratio`
;   and always hits one that cannot act; a hit or a damaging skill that does
;   not kill releases with `release_by_damage` —`ba_st_by_damage`—.
; * The parameters: `ba_st_params` halves the effective ones a condition
;   halves, after the modifier, as `AdjustParam`.
;
; What it does not do —the HP and SP a condition takes each turn, the skills
; it seals— is said by the divergence `what-battle-conditions-do-not-model`
; in the book.
;
; Each combatant has four places, kept **in LDB order** with the empty ones
; at the end: that is the order easyrpg walks them in, and so the order of
; the rolls. Each place is a word: the condition's number in the low byte —0
; empty— and in the high one how long it has been held, easyrpg's
; `states[i]`. A fifth at once is not given: no game comes near.
ST_PLACES = 4
ST_BYTES = ST_PLACES * 2
ST_LAST = ST_BYTES - 2
ST_DEAD = 1                     ; `State::kDeathID`

.pushseg
.segment "FARBSS"
ba_states:      .res BA_COMB_MAX * ST_BYTES
ba_st_resume:   .res 1          ; the action whose message is on screen is
                                ; still to run: see `ba_execute`
ba_st_cmd:      .res 1          ; the action decided by `ba_st_begin`
ba_st_tgt:      .res 1
ba_st_who:      .res 1          ; whose is the message, and its text
ba_st_text:     .res 2
ba_st_next_who: .res 1          ; a release by a hit still to say, or $FF
ba_st_next_txt: .res 2
ba_st_c:        .res 1          ; scratch of this file, which nobody else
ba_st_id:       .res 1          ; touches: the callers keep theirs in
ba_st_k:        .res 2          ; `BA_S*` and in `BA_T*`
ba_st_base:     .res 2
ba_st_h:        .res 2
ba_st_r:        .res 1
ba_st_top:      .res 1
ba_st_top_pri:  .res 1
ba_st_top_rel:  .res 1
ba_st_rate:     .res 1
ba_st_restr_of: .res 1
ba_st_gone:     .res 1          ; `ba_st_heal` released something
.popseg

; Nobody has anything, no action waits and no message is pending. From
; `battle_run`, before anything.
.proc ba_st_clear
.a8
.i16
    ldx #0
    rep #$20
.a16
loop:
    stz .loword(ba_states), x
    inx
    inx
    cpx #BA_COMB_MAX * ST_BYTES
    bcc loop
    sep #$20
.a8
    stz .loword(ba_st_resume)
    lda #$FF
    sta .loword(ba_st_next_who)
    rts
.endproc

; A8 = the combatant; X = where its places start, inside `ba_states`.
; Clobbers A.
.proc ba_st_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times ST_BYTES
    tax
    sep #$20
.a8
    rts
.endproc
.assert ST_BYTES = 8, error, "ba_st_x multiplies by eight"

; A8 = the combatant; A8 = its restriction, `GetSignificantRestriction`: 1
; does nothing and wins over all, then 2 attacks the other side, then 3
; attacks its own, and 0 normal. Z follows A. Clobbers X, Y and `ba_st_r`.
.proc ba_st_restr
.a8
.i16
    jsr ba_st_x
    stz .loword(ba_st_r)
    ldy #ST_PLACES
loop:
    lda .loword(ba_states), x
    beq done                    ; the empty ones go at the end
    phx
    jsr ba_ax
    lda f:state_restrict, x
    plx
    cmp #1
    beq nothing
    cmp #2
    bne not_other_side
    sta .loword(ba_st_r)
    bra next
not_other_side:
    cmp #3
    bne next
    lda .loword(ba_st_r)
    bne next                    ; attacking the other side wins
    lda #3
    sta .loword(ba_st_r)
next:
    inx
    inx
    dey
    bne loop
done:
    lda .loword(ba_st_r)
    rts
nothing:
    lda #1
    rts
.endproc

; A8 = the combatant; A8 = the lowest `reduce_hit_ratio` of what it has, 100
; with nothing: `GetHitChanceModifierFromStates`. Clobbers X, Y and
; `ba_st_r`.
.proc ba_st_hitmod
.a8
.i16
    jsr ba_st_x
    lda #100
    sta .loword(ba_st_r)
    ldy #ST_PLACES
loop:
    lda .loword(ba_states), x
    beq done
    phx
    jsr ba_ax
    lda f:state_hit, x
    plx
    cmp .loword(ba_st_r)
    bcs next
    sta .loword(ba_st_r)
next:
    inx
    inx
    dey
    bne loop
done:
    lda .loword(ba_st_r)
    rts
.endproc

; The effective parameters of combatant A8, again: base plus modifier,
; clamped to [1, 999], and halved —never below 1— if a condition it has
; halves it. It is `AdjustParam`, and without conditions the same number
; `ba_mod` leaves. Clobbers X, Y and `ba_st_h`.
.macro ST_PARAM effective, base, modifier, bit
    .local low, clamped, halve, put
    lda BA_ONE + base, x
    clc
    adc BA_ONE + modifier, x
    bmi low
    beq low
    cmp #(BA_PARAM_MAX + 1)
    bcc clamped
    lda #BA_PARAM_MAX
    bra clamped
low:
    lda #1
clamped:
    tay
    lda .loword(ba_st_h)
    and #bit
    beq put
    tya
    lsr a
    bne halve
    lda #1
halve:
    tay
put:
    tya
    sta BA_ONE + effective, x
.endmacro

.proc ba_st_params
.a8
.i16
    pha
    jsr ba_st_x
    stz .loword(ba_st_h)
    stz .loword(ba_st_h) + 1
    ldy #ST_PLACES
loop:
    lda .loword(ba_states), x
    beq done
    phx
    jsr ba_ax
    lda f:state_halves, x
    plx
    ora .loword(ba_st_h)
    sta .loword(ba_st_h)
    inx
    inx
    dey
    bne loop
done:
    pla
    jsr ba_x
    rep #$20
.a16
    ST_PARAM BA_ATK, BA_BATK, BA_MATK, $01
    ST_PARAM BA_DEF, BA_BDEF, BA_MDEF, $02
    ST_PARAM BA_SPI, BA_BSPI, BA_MSPI, $04
    ST_PARAM BA_AGI, BA_BAGI, BA_MAGI, $08
    sep #$20
.a8
    rts
.endproc

; The same, only if combatant A8 has a condition: after a skill moved a
; modifier —`ba_skill_one`—, which `ba_mod` already left right for one that
; has none.
.proc ba_st_params_held
.a8
.i16
    pha
    jsr ba_st_x
    lda .loword(ba_states), x
    beq none
    pla
    jmp ba_st_params
none:
    pla
    rts
.endproc

; The action combatant `ba_st_c` has this turn is lost: `BA_NONE`. Clobbers A
; and X.
.proc ba_st_cancel
.a8
.i16
    lda .loword(ba_st_c)
    asl a
    jsr ba_ax
    lda #BA_NONE
    sta BA_ACC, x
    rts
.endproc

; `AddState` on combatant `ba_st_c`, condition A8: see the top. Clobbers
; `BA_T*`'s neighbours only through what it calls: X, Y, and this file's.
.proc ba_st_add
.a8
.i16
    sta .loword(ba_st_id)
    lda .loword(ba_st_c)
    jsr ba_st_x
    stx .loword(ba_st_base)
    ; --- held already: from 1 again ---
    ldy #ST_PLACES
seek:
    lda .loword(ba_states), x
    beq not_held
    cmp .loword(ba_st_id)
    beq again
    bcs not_held                ; past it: it goes here
    inx
    inx
    dey
    bne seek
    rts                         ; four already, all before it: not given
again:
    lda #1
    sta .loword(ba_states) + 1, x
    bra purge
not_held:
    ; X is where it goes. If the last place is taken there is no room.
    phx
    ldx .loword(ba_st_base)
    lda .loword(ba_states) + ST_LAST, x
    plx
    cmp #0                      ; the `plx` left Z from X: AGENTS.md's trap
    beq room
    rts
room:
    ; The ones from X on move one place, from the end.
    stx .loword(ba_st_k)
    rep #$20
.a16
    lda .loword(ba_st_base)
    clc
    adc #ST_LAST
    tay                         ; the one being written
shift:
    cpy .loword(ba_st_k)
    beq shifted
    tyx
    lda .loword(ba_states) - 2, x
    sta .loword(ba_states), x
    dey
    dey
    bra shift
shifted:
    ldx .loword(ba_st_k)
    lda .loword(ba_st_id)
    and #$00FF
    ora #$0100                  ; held for 1
    sta .loword(ba_states), x
    sep #$20
.a8
purge:
    ; --- the ones ten below the highest go: `State::Add` ---
    ldx .loword(ba_st_base)
    stz .loword(ba_st_top_pri)
    ldy #ST_PLACES
highest:
    lda .loword(ba_states), x
    beq highest_found
    phx
    jsr ba_ax
    lda f:state_priority, x
    plx
    cmp .loword(ba_st_top_pri)
    bcc lower
    sta .loword(ba_st_top_pri)
lower:
    inx
    inx
    dey
    bne highest
highest_found:
    ldx .loword(ba_st_base)
    stx .loword(ba_st_k)
other:
    ldx .loword(ba_st_k)
    lda .loword(ba_states), x
    beq purged
    jsr ba_ax
    lda f:state_priority, x
    clc
    adc #10
    bcs stays                   ; cannot be ten below anything
    cmp .loword(ba_st_top_pri)
    beq goes
    bcs stays
goes:
    ldx .loword(ba_st_k)
    jsr ba_st_drop
    bra other                   ; the next one came down to this place
stays:
    rep #$20
.a16
    inc .loword(ba_st_k)
    inc .loword(ba_st_k)
    lda .loword(ba_st_k)
    sec
    sbc .loword(ba_st_base)
    cmp #ST_BYTES
    sep #$20
.a8
    bcc other
purged:
    lda .loword(ba_st_c)
    jsr ba_st_params
    ; --- held, with a restriction: the action goes ---
    lda .loword(ba_st_c)
    jsr ba_st_has
    beq ready
    lda .loword(ba_st_c)
    jsr ba_st_restr
    beq ready
    jsr ba_st_cancel
ready:
    rts
.endproc

; X = a place inside `ba_states`: out, and the ones after it come down one.
; The combatant's places start at `ba_st_base`. Clobbers A and X.
.proc ba_st_drop
.a8
.i16
    rep #$20
.a16
    lda .loword(ba_st_base)
    clc
    adc #ST_LAST
    sta .loword(ba_st_h)        ; the last place
down:
    cpx .loword(ba_st_h)
    bcs last
    lda .loword(ba_states) + 2, x
    sta .loword(ba_states), x
    inx
    inx
    bra down
last:
    stz .loword(ba_states), x
    sep #$20
.a8
    rts
.endproc

; Whether combatant A8 has condition `ba_st_id`: A8 and Z, 1 if it does.
; Leaves X on its place. Clobbers Y.
.proc ba_st_has
.a8
.i16
    jsr ba_st_x
    ldy #ST_PLACES
seek:
    lda .loword(ba_states), x
    beq no
    cmp .loword(ba_st_id)
    beq yes
    inx
    inx
    dey
    bne seek
no:
    lda #0
    rts
yes:
    lda #1
    rts
.endproc

; `RemoveStates` on combatant `ba_st_c`, condition A8: A8 and Z, 1 if it had
; it. If the restriction changed, the action goes. Clobbers X and Y.
.proc ba_st_remove
.a8
.i16
    sta .loword(ba_st_id)
    lda .loword(ba_st_c)
    jsr ba_st_restr
    pha                         ; the restriction before
    lda .loword(ba_st_c)
    jsr ba_st_x
    stx .loword(ba_st_base)
    lda .loword(ba_st_c)
    jsr ba_st_has
    bne had
    pla
    lda #0
    rts
had:
    jsr ba_st_drop
    lda .loword(ba_st_c)
    jsr ba_st_params
    lda .loword(ba_st_c)
    jsr ba_st_restr
    sta .loword(ba_st_r)
    pla
    cmp .loword(ba_st_r)
    beq same
    jsr ba_st_cancel
same:
    lda #1
    rts
.endproc

; `ChangeMonsterCondition`, OP_MONSTER_STATE: called by `op_monster_state`
; from the interpreter, with the data bank at 0 and Y on the operands; it
; sets the battle's and leaves Y after them. A place the troop does not have
; does nothing, as `GetEnemy` giving null; a hidden or a dead one gets it all
; the same. **The dead one** (1) is `AddState(kDeathID)`: the HP at zero and
; the modifiers too, and nothing is kept, because a dead enemy neither acts
; nor gets up here —the converter does not compile taking it away—; the
; scene erases it as it erases one killed by a page's `ChangeMonsterHP`.
.proc ba_st_change
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda [code_ptr], y           ; the place
    iny
    sta BA_T0
    lda [code_ptr], y           ; whether it is taken away
    iny
    sta BA_T0 + 1
    lda [code_ptr], y           ; and which
    iny
    sta BA_T1
    phy
    lda BA_T0
    cmp BA_KID
    bcs ready
    clc
    adc #BA_PARTY_MAX
    sta .loword(ba_st_c)
    lda BA_T1
    beq ready
    rep #$20
.a16
    and #$00FF
    cmp #STATES_N               ; a word: there may be 256
    sep #$20
.a8
    bcs ready                   ; not in the tables: nobody's
    lda BA_T0 + 1
    bne takes_away
    lda BA_T1
    cmp #ST_DEAD
    beq dies
    jsr ba_st_add
    bra ready
takes_away:
    lda BA_T1
    jsr ba_st_remove
ready:
    ply
    plb
    rtl
dies:
    lda .loword(ba_st_c)
    jsr ba_x
    rep #$20
.a16
    stz BA_ONE + BA_HP, x
    stz BA_ONE + BA_MATK, x
    stz BA_ONE + BA_MDEF, x
    stz BA_ONE + BA_MSPI, x
    stz BA_ONE + BA_MAGI, x
    sep #$20
.a8
    lda .loword(ba_st_c)
    jsr ba_st_params
    bra ready
.endproc

; --- when an action begins ------------------------------------------------------

; The action of combatant `BA_MWHO`, when its turn comes: `PrepareBattleAction`
; and then `BattleStateHeal`. Leaves the action in `ba_st_cmd` and
; `ba_st_tgt`, and answers A8 = 1 —and Z clear— if there is a message to show
; before it, in `ba_st_who` and `ba_st_text`.
;
; One that cannot act does nothing; one that attacks its own side or the
; other attacks a living one there, **one roll**, even if it already chose
; when the turn began —`ba_enemy_actions`—; the rest do what was recorded,
; which a condition may have turned into `BA_NONE`. Clobbers `BA_S1`,
; `BA_S2`, `BA_T*`, X and Y.
.proc ba_st_begin
.a8
.i16
    lda BA_MWHO
    asl a
    jsr ba_ax
    lda BA_ACC, x
    sta .loword(ba_st_cmd)
    lda BA_ACC + 1, x
    sta .loword(ba_st_tgt)
    lda BA_MWHO
    jsr ba_st_restr
    beq heal
    cmp #1
    bne attacks
    lda #BA_NONE
    sta .loword(ba_st_cmd)
    bra heal
attacks:
    jsr ba_st_side
    jsr ba_alive_on_side
    lda BA_S1
    bne someone
    lda #BA_NONE
    sta .loword(ba_st_cmd)
    bra heal
someone:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    dec a
    jsr ba_until
    tax
    sep #$20
.a8
    lda BA_CAND, x
    sta .loword(ba_st_tgt)
    lda #BA_ATTACK
    sta .loword(ba_st_cmd)
heal:
    lda BA_MWHO
    jmp ba_st_heal
.endproc

; With A8 = the restriction of `BA_MWHO` —2 or 3—, the side it attacks, as
; `ba_alive_on_side` takes it: 0 the party, `BA_PARTY_MAX` the troop. 3 is
; its own side, 2 the other.
.proc ba_st_side
.a8
.i16
    sta .loword(ba_st_restr_of)
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    lda #0                      ; the party: `lda` does not touch C
    bcc in_party
    lda #BA_PARTY_MAX
in_party:
    pha
    lda .loword(ba_st_restr_of)
    cmp #3
    beq own
    pla
    eor #BA_PARTY_MAX           ; the other
    rts
own:
    pla
    rts
.endproc
.assert BA_PARTY_MAX = 4, error, "ba_st_side flips the side with an eor"

; `BattleStateHeal` on combatant A8 when its action begins: for each condition,
; in order, if it has been held for more than `hold_turn` —only then— **one
; roll** against `auto_release_prob`, and away if it comes up; if not, one
; more. And `ProcessBattleActionBegin`'s message: of the ones held and the
; ones just released, the one with the highest priority —the later one on a
; tie—; released, its `message_recovery`, always; held, its
; `message_affected`, if it has one. Answers as `ba_st_begin`.
.proc ba_st_heal
.a8
.i16
    sta .loword(ba_st_c)
    stz .loword(ba_st_top)
    stz .loword(ba_st_gone)
    lda .loword(ba_st_c)
    jsr ba_st_x
    stx .loword(ba_st_base)
    stx .loword(ba_st_k)
other:
    ldx .loword(ba_st_k)
    lda .loword(ba_states), x
    bne one
    jmp done
one:
    sta .loword(ba_st_id)
    jsr ba_ax
    lda f:state_hold, x
    ldx .loword(ba_st_k)
    cmp .loword(ba_states) + 1, x
    bcs holds                   ; held for `hold_turn` or less
    lda .loword(ba_st_id)
    jsr ba_ax
    lda f:state_auto, x
    jsr ba_pct
    beq holds
    ; Released: out, and the next one comes down to this place.
    ldx .loword(ba_st_k)
    jsr ba_st_drop
    lda #1
    sta .loword(ba_st_gone)
    jsr candidate
    bra other
holds:
    ldx .loword(ba_st_k)
    lda .loword(ba_states) + 1, x
    inc a
    beq at_most                 ; 255 turns is enough to know
    sta .loword(ba_states) + 1, x
at_most:
    lda #0
    jsr candidate
    rep #$20
.a16
    inc .loword(ba_st_k)
    inc .loword(ba_st_k)
    lda .loword(ba_st_k)
    sec
    sbc .loword(ba_st_base)
    cmp #ST_BYTES
    sep #$20
.a8
    bcc other
done:
    ; The parameters again only if something went: one with nothing, which
    ; is everyone in a battle without conditions, keeps what it had.
    lda .loword(ba_st_gone)
    beq params_ready
    lda .loword(ba_st_c)
    jsr ba_st_params
params_ready:
    lda .loword(ba_st_top)
    beq silent
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda .loword(ba_st_top_rel)
    and #$00FF
    bne released
    lda f:state_affected, x
    bra text
released:
    lda f:state_recovery, x
text:
    sta .loword(ba_st_text)
    tax
    sep #$20
.a8
    lda .loword(ba_st_c)
    sta .loword(ba_st_who)
    lda .loword(ba_st_top_rel)
    bne says                    ; released: always, even empty
    lda f:item_txt_n, x
    beq silent
says:
    lda #1
    rts
silent:
    lda #0
    rts

; A8 = whether `ba_st_id` was released: it is the message's if its priority
; is not below the one there.
candidate:
    sta .loword(ba_st_r)
    lda .loword(ba_st_id)
    jsr ba_ax
    lda f:state_priority, x
    ldx .loword(ba_st_top)
    beq takes                   ; there was none
    cmp .loword(ba_st_top_pri)
    bcc not_taken
takes:
    sta .loword(ba_st_top_pri)
    lda .loword(ba_st_id)
    sta .loword(ba_st_top)
    lda .loword(ba_st_r)
    sta .loword(ba_st_top_rel)
not_taken:
    rts
.endproc

; `BattlePhysicalStateHeal` on combatant A8, which a hit did not kill, at
; `ba_st_rate` percent —100 an attack's, `physical_rate * 10` a skill's—: for
; each condition, in order, with `release_by_damage`, **one roll** against
; `release_by_damage * rate / 100`, and away if it comes up. The first one
; released says its `message_recovery` in a message of its own after the
; hit's: see `ba_execute`. Keeps `BA_S*`; clobbers `BA_T*`, X and Y.
.proc ba_st_by_damage
.a8
.i16
    sta .loword(ba_st_c)
    lda .loword(ba_st_rate)
    bne rolls
    rts                         ; `physical_rate` 0: no roll
rolls:
    lda .loword(ba_st_c)
    jsr ba_st_x
    stx .loword(ba_st_k)
other:
    ldx .loword(ba_st_k)
    lda .loword(ba_states), x
    beq ready
    sta .loword(ba_st_id)
    jsr ba_ax
    lda f:state_damage, x
    beq next
    rep #$20
.a16
    and #$00FF
    pha
    sep #$20
.a8
    lda .loword(ba_st_rate)
    sta BA_T2
    stz BA_T2 + 1
    rep #$20
.a16
    pla
    jsr ba_mul                  ; release_by_damage * rate
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sep #$20
.a8
    jsr ba_pct
    beq next
    lda .loword(ba_st_id)
    jsr ba_st_remove
    beq next
    lda .loword(ba_st_next_who)
    cmp #$FF
    bne other                   ; the first one says it; the next one came
                                ; down to this place
    lda .loword(ba_st_c)
    sta .loword(ba_st_next_who)
    lda .loword(ba_st_id)
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:state_recovery, x
    sta .loword(ba_st_next_txt)
    sep #$20
.a8
    bra other
next:
    rep #$20
.a16
    inc .loword(ba_st_k)
    inc .loword(ba_st_k)
    lda .loword(ba_st_k)
    and #ST_BYTES - 1
    sep #$20
.a8
    bne other                   ; still inside its eight bytes
ready:
    rts
.endproc
