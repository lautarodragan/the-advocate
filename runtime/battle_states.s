.segment "FAR2"

; --- the conditions in battle ---------------------------------------------------
;
; RM2k's states, `Game_Battler`'s, with what the battle does with them —and the
; model too, `Held` in `rm2k-snes-battle`'s `simulate.rs`, which rolls in the
; same order: that order is the contract—. An enemy gets them from a troop
; page's `ChangeMonsterCondition` (OP_MONSTER_STATE); an actor brings its own
; from the map —see party_states.s, and `ba_st_actor_in` below— and a page's
; `ChangeCondition` gives it more; and since 2026-11-01 a skill gives and
; takes them on either side —`ba_st_skill`—. What a condition is comes from
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
; * The HP and SP each time its holder acts, `ApplyConditions`:
;   `ba_st_turn`, from `ba_st_heal`.
;
; What it does not do —the skills it seals, a weapon that gives one— is said
; by the divergence `what-battle-conditions-do-not-model` in the book.
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
ba_st_ptr:      .res 2          ; `ba_st_skill`: where in `st_lists`,
ba_st_held:     .res 1          ; whether the target holds the one looked at,
ba_st_died:     .res 1          ; and whether it gave death
ba_st_col:      .res 1          ; `ba_st_odds`: the condition's column,
ba_st_keep:     .res 1          ; and what the armor leaves of it
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
    jsr ba_st_turn              ; `ApplyConditions`, after the releases
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

; --- the actors' -----------------------------------------------------------------
;
; An actor's conditions are its own, on the map as in battle —see
; party_states.s—: the battle takes them into its places when the actor
; comes in, and gives them back each time a troop page runs and when it
; ends, the same as the HP and SP —`ba_sync_out` and `ba_sync_in`—. A page
; that gives or takes one writes the actor's, and the battle takes it up
; again after the page.

; Combatant A8, an actor —`BA_NUMBER`—, takes its conditions from the
; actor's places, and its parameters with them. If its restriction changed,
; the action it had this turn is lost, as `AddState` and `RemoveStates` do.
; Clobbers X, Y and this file's scratch.
.proc ba_st_actor_in
.a8
.i16
    sta .loword(ba_st_c)
    jsr ba_st_restr
    pha                         ; the restriction before
    lda .loword(ba_st_c)
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; the actor's places: `act_st_x`
    tay
    sep #$20
.a8
    lda .loword(ba_st_c)
    jsr ba_st_x
    rep #$20
.a16
    lda .loword(far_act_states), y
    sta .loword(ba_states), x
    lda .loword(far_act_states) + 2, y
    sta .loword(ba_states) + 2, x
    lda .loword(far_act_states) + 4, y
    sta .loword(ba_states) + 4, x
    lda .loword(far_act_states) + 6, y
    sta .loword(ba_states) + 6, x
    sep #$20
.a8
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
    rts
.endproc
.assert ST_BYTES = 8, error, "ba_st_actor_in copies four places"

; And back: combatant A8's conditions to its actor's places. Keeps Y;
; clobbers A and X.
.proc ba_st_actor_out
.a8
.i16
    phy
    pha
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    tay
    sep #$20
.a8
    pla
    jsr ba_st_x
    rep #$20
.a16
    lda .loword(ba_states), x
    sta .loword(far_act_states), y
    lda .loword(ba_states) + 2, x
    sta .loword(far_act_states) + 2, y
    lda .loword(ba_states) + 4, x
    sta .loword(far_act_states) + 4, y
    lda .loword(ba_states) + 6, x
    sta .loword(far_act_states) + 6, y
    sep #$20
.a8
    ply
    rts
.endproc

; --- each time its holder acts ----------------------------------------------------
;
; `Game_Battler::ApplyConditions`, which `ProcessBattleActionBegin` runs right
; after `BattleStateHeal`: each condition `ba_st_c` still holds, in order,
; changes its HP by `hp_change_val` plus `hp_change_max` percent of its
; maximum —a loss never kills, `ChangeHp(-hp, false)`, and a fallen one does
; not change— and its SP the same, between zero and the maximum. It rolls
; nothing and says nothing of its own: the condition's message is
; `ba_st_heal`'s. `state_turn` has the four numbers and `state_turn_loss`
; which are losses. Keeps A; clobbers `BA_T*`, X, Y, `temp` and this
; file's scratch.
.proc ba_st_turn
.a8
.i16
    pha
    lda .loword(ba_st_c)
    jsr ba_st_x
    stx .loword(ba_st_k)
    ldy #ST_PLACES
place:
    phy
    ldx .loword(ba_st_k)
    lda .loword(ba_states), x
    beq out
    sta .loword(ba_st_id)
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; `state_turn`'s row: four words
    sta .loword(ba_st_ptr)
    tax
    sep #$20
.a8
    lda #BA_HP
    jsr change
    rep #$20
.a16
    lda .loword(ba_st_ptr)
    clc
    adc #4
    tax
    sep #$20
.a8
    lda #BA_SP
    jsr change
    rep #$20
.a16
    inc .loword(ba_st_k)
    inc .loword(ba_st_k)
    sep #$20
.a8
    ply
    dey
    bne place
    pla
    rts
out:
    ply
    pla
    rts

; A8 = `BA_HP` or `BA_SP`, the field it changes, with its maximum two bytes
; after it; X = its two words in `state_turn`.
change:
    sta .loword(ba_st_r)
    rep #$20
.a16
    lda f:state_turn, x
    sta BA_T0                   ; the value
    lda f:state_turn + 2, x
    sta BA_T2                   ; and the percentage, a byte for `ba_mul`
    ora BA_T0
    bne changes
    sep #$20
.a8
    rts                         ; nothing: the usual
changes:
.a16
    ; The field's place: the combatant's, plus the field.
    sep #$20
.a8
    lda .loword(ba_st_c)
    jsr ba_x
    rep #$21                    ; and the carry clear
.a16
    lda .loword(ba_st_r)
    and #$00FF
    sta BA_T1
    txa
    adc BA_T1
    sta BA_T1                   ; X for the field, from here on
    ; `val + max * pct / 100`, in two halves so that nothing goes past
    ; sixteen bits: `(max / 100) * pct + (max % 100) * pct / 100`, which
    ; truncates the same.
    tax
    lda BA_ONE + 2, x           ; the maximum, after the field
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div                  ; the hundreds in `temp`, the rest in `comp_and`
    lda comp_and
    pha
    lda temp
    jsr ba_mul
    clc
    adc BA_T0
    sta BA_T0
    pla
    jsr ba_mul
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    clc
    adc BA_T0
    sta BA_T0                   ; the amount
    ; Is it a loss? Bit 0 for the HP, bit 1 for the SP.
    sep #$20
.a8
    lda .loword(ba_st_id)
    jsr ba_ax
    lda f:state_turn_loss, x
    pha
    lda .loword(ba_st_r)
    cmp #BA_SP
    pla
    ldx BA_T1                   ; neither touches C
    bcc hp_bit                  ; `BA_HP` is the lower field
    lsr a
hp_bit:
    and #1
    rep #$20
.a16
    bne loses
    ; A gain, up to the maximum. A fallen one's HP do not change.
    lda .loword(ba_st_r)
    and #$00FF
    cmp #BA_HP
    bne gains
    lda BA_ONE, x
    beq unchanged
gains:
    lda BA_ONE, x
    clc
    adc BA_T0
    cmp BA_ONE + 2, x
    bcc put
    lda BA_ONE + 2, x
    bra put
loses:
    lda BA_ONE, x
    beq unchanged               ; fallen, or no SP: nothing to lose
    sec
    sbc BA_T0
    beq floor
    bcs put
floor:
    ; Below: the HP stop at 1, the SP at 0.
    lda .loword(ba_st_r)
    and #$00FF
    cmp #BA_HP
    bne zero
    lda #1
    bra put
zero:
    lda #0
put:
    sta BA_ONE, x
unchanged:
    sep #$20
.a8
    rts
.endproc
.assert BA_HPMAX = BA_HP + 2 && BA_SPMAX = BA_SP + 2, error, "ba_st_turn finds the maximum after the field"
.assert BA_HP < BA_SP, error, "ba_st_turn tells the HP by the lower field"

; --- what a skill gives ---------------------------------------------------------
;
; `Skill::vExecute`'s conditions, after the parameters and before the
; attributes, from `ba_skill_one` —the model's `skill_states` in
; `rm2k-snes-battle`, which rolls the same in the same order—. For each
; condition of the skill's `state_effects`, in order, on `BA_MTGT`:
;
; * against enemies, one it already holds says so —`message_already`— and
;   rolls nothing;
; * otherwise **one roll** against the skill's hit, in `BA_S0`; if it comes
;   up, one that targets its own side takes it away —`message_recovery`—
;   if it is there, and one against enemies rolls **a second time**
;   against its odds on the target —`ba_st_odds`— and gives it, with
;   `AddState` —`message_actor` or `message_enemy`—.
;
; Each is a line of the skill's results, and a success. The dead one given
; kills, as a troop page's does; taken away, nothing: no target of a skill
; is fallen. A8 = 1 and Z clear if it gave death, after which `vExecute`
; skips the attributes. `BA_S3` is the skill's `skill_affects`. Clobbers
; `BA_T*`, X, Y and this file's scratch; keeps `BA_S*`.
BA_RES_GIVEN = 8                ; see `BA_RES_*` in battle_skills.s
BA_RES_TAKEN = 9
BA_RES_ALREADY = 10
.proc ba_st_skill
.a8
.i16
    stz .loword(ba_st_died)
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_st_at, x
    sta .loword(ba_st_ptr)
    sep #$20
.a8
    bne other
    jmp done                    ; the usual: it gives nothing
other:
    ldx .loword(ba_st_ptr)
    lda f:st_lists, x
    bne one
    jmp done
one:
    sta .loword(ba_st_id)
    inx
    stx .loword(ba_st_ptr)
    ; Held?
    cmp #ST_DEAD
    bne a_place
    lda BA_MTGT
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq held
    lda #0
    bra seen
held:
    lda #1
    bra seen
a_place:
    lda BA_MTGT
    jsr ba_st_has
seen:
    sta .loword(ba_st_held)
    lda BA_S3
    and #$40
    beq own_side
    ; --- against enemies ---
    lda .loword(ba_st_held)
    beq rolls
    ldy #BA_RES_ALREADY
    jsr line
    bra other
rolls:
    lda BA_S0
    jsr ba_pct
    beq other
    jsr ba_st_odds
    jsr ba_pct
    beq other
    lda .loword(ba_st_id)
    cmp #ST_DEAD
    beq kills
    lda BA_MTGT
    sta .loword(ba_st_c)
    lda .loword(ba_st_id)
    jsr ba_st_add
    lda BA_MTGT
    jsr ba_st_has
    beq other                   ; the purge took it at once
    ldy #BA_RES_GIVEN
    jsr line
    bra other
kills:
    ; `AddState(kDeathID)`: the HP and the modifiers at zero, as
    ; `ba_st_change` does; the scene erases an enemy at zero HP.
    lda BA_MTGT
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
    lda BA_MTGT
    jsr ba_st_params
    ldy #BA_RES_GIVEN
    jsr line
    lda #1
    sta .loword(ba_st_died)
    jmp other
    ; --- on its own side ---
own_side:
    lda BA_S0
    jsr ba_pct
    bne cures
    jmp other
cures:
    lda .loword(ba_st_held)
    bne has_it
    jmp other
has_it:
    lda .loword(ba_st_id)
    cmp #ST_DEAD
    bne not_dead
    jmp other
not_dead:
    lda BA_MTGT
    sta .loword(ba_st_c)
    lda .loword(ba_st_id)
    jsr ba_st_remove
    bne taken
    jmp other
taken:
    ldy #BA_RES_TAKEN
    jsr line
    jmp other
done:
    lda .loword(ba_st_died)
    rts

; The line for `ba_st_id`, Y what.
line:
    rep #$20
.a16
    lda .loword(ba_st_id)
    and #$00FF
    jsr ba_res_add
    sep #$20
.a8
    rts
.endproc

; `GetStateProbability` of `ba_st_id` on `BA_MTGT`, in A8: the rate of its
; rank —`st_ranks`, an actor's row by its number and an enemy's by its `k`
; after the actors'—, and on an actor what its armor leaves of it: the
; lowest `item_st_pct` of the shield, armor, helmet and accessory that list
; it. A condition no skill or weapon gives has no column and no odds.
; Clobbers `BA_T*`, X and Y.
.proc ba_st_odds
.a8
.i16
    lda .loword(ba_st_id)
    jsr ba_ax
    lda f:st_used, x
    cmp #$FF
    bne has_column
    lda #0
    rts
has_column:
    sta .loword(ba_st_col)
    lda #ST_USED_N
    sta BA_T2
    stz BA_T2 + 1
    lda #100
    sta .loword(ba_st_keep)
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs an_enemy
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    rep #$20
.a16
    and #$00FF
    sta BA_T1
    jsr ba_mul                  ; the actor times ST_USED_N
    sta BA_T0
    lda BA_T1
    jsr armor
    bra row
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
    jsr ba_mul                  ; (ACTORS_N + k) times ST_USED_N
    sta BA_T0
row:
    lda .loword(ba_st_col)
    and #$00FF
    clc
    adc BA_T0
    tax
    lda f:st_ranks, x           ; the rank, and what is after it
    and #$00FF
    sta BA_T0
    lda .loword(ba_st_col)
    and #$00FF
    sta BA_T1
    asl a
    asl a
    clc
    adc BA_T1                   ; the column times five: its rates
    clc
    adc BA_T0
    tax
    lda f:st_rate, x
    and #$00FF                  ; the rate, 0 to 100
    sep #$20
.a8
    sta BA_T2
    lda .loword(ba_st_keep)
    cmp #100
    beq ready
    ; `rate * keep / 100`, as easyrpg truncates it.
    rep #$20
.a16
    and #$00FF
    jsr ba_mul
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sep #$20
.a8
    rts
ready:
    lda BA_T2
    rts

; A16 = the actor: its equipment's lowest `item_st_pct` for `ba_st_id`, in
; `ba_st_keep`. Keeps `BA_T0` and `BA_T2`.
.a16
armor:
    jsr ba_attr_equipment_row
    tay
    lda #5
    sta BA_T1
slot:
    tyx
    lda FAR_EQUIPMENT, x
    jsr ba_attr_item_k
    bcs next
    stx .loword(ba_st_k)        ; its `k`
    lda f:item_st_pct, x        ; the byte table: the high byte is not looked at
    and #$0080
    bne next                    ; a weapon gives, it does not resist
    txa
    asl a
    tax
    lda f:item_st_at, x
    beq next
    tax
listed:
    sep #$20
.a8
    lda f:st_lists, x
    beq next_8
    cmp .loword(ba_st_id)
    beq it_lists
    inx
    bra listed
it_lists:
    ldx .loword(ba_st_k)
    lda f:item_st_pct, x
    cmp .loword(ba_st_keep)
    bcs next_8
    sta .loword(ba_st_keep)
next_8:
    rep #$20
.a16
next:
    iny
    iny
    dec BA_T1
    bne slot
    rts
.a8
.endproc
