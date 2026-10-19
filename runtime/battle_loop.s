.segment "FAR2"

; --- the battle loop -------------------------------------------------------

; The average agility of one side: A8 at 0 the party and at 1 the troop. If
; nobody is left alive everyone counts, which is what `average_agility` of
; `rm2k-snes-battle` does. The result goes in `BA_T1`, capped at
; `BA_AGI_CAP`: through memory and not the accumulator, for the same reason
; as `ba_param`.
.proc ba_average
.a8
.i16
    sta BA_S6
    ; Two passes: the first counts only the living and, if there were none,
    ; the second counts everyone.
    lda #1
    sta BA_S5                   ; only the living?
tick:
    rep #$20
.a16
    lda #0
    sta BA_T0                   ; the sum
    sep #$20
.a8
    lda #0
    sta BA_S4                   ; how many
    lda BA_S6
    beq from_party
    lda #BA_PARTY_MAX
    sta BA_S0
    lda BA_KID
    clc
    adc #BA_PARTY_MAX
    sta BA_S3
    bra sum
from_party:
    lda #0
    sta BA_S0
    lda BA_NACTORS
    sta BA_S3
sum:
    lda BA_S0
    cmp BA_S3
    bcs added
    lda BA_S5
    beq count
    lda BA_S0
    jsr ba_alive
    beq next
count:
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_AGI, x
    clc
    adc BA_T0
    sta BA_T0
    sep #$20
.a8
    inc BA_S4
next:
    inc BA_S0
    bra sum
added:
    lda BA_S4
    bne divide_it
    lda BA_S5
    beq divide_it               ; neither living nor dead: there is nobody
    stz BA_S5
    bra tick
divide_it:
    rep #$20
.a16
    lda BA_S4
    and #$00FF
    bne has
    lda #1
has:
    sta temp + 2
    lda BA_T0
    sta temp
    jsr ba_div
    cmp #(BA_AGI_CAP + 1)
    bcc ready
    lda #BA_AGI_CAP
ready:
    sta BA_T1
    sep #$20
.a8
    rts
.endproc

; The chance to escape: `Scene_Battle::InitEscapeChance`.
;
;     base   = round(100 * enemy_agi / party_agi)
;     chance = clamp(150 - base, 0, 100)
;
; The rounding is `(2a + b) / (2b)`, which is `RoundTo` with integers and no
; floats: see `initial_escape_chance` in `rm2k-snes-battle`.
.proc ba_flee_chance
.a8
.i16
    lda #0
    jsr ba_average
    rep #$20
.a16
    lda BA_T1
    bne party_has
    lda #1
party_has:
    sta BA_S1                   ; the party's average
    sep #$20
.a8
    lda #1
    jsr ba_average
    rep #$20
.a16
    lda BA_T1
    sta BA_S2                   ; the troop's
    lda #200
    sta BA_T2
    lda BA_S2
    jsr ba_mul                  ; 200 times the troop's average
    clc
    adc BA_S1
    sta temp
    lda BA_S1
    asl a
    sta temp + 2
    jsr ba_div                  ; A16 = the base
    sta BA_S3
    lda #150
    sec
    sbc BA_S3
    bpl no_negative
    lda #0
no_negative:
    cmp #101
    bcc chance_list
    lda #100
chance_list:
    sep #$20
.a8
    sta BA_ESCAPE
    rts
.endproc

; `TryEscape`: roll against the chance and, if it fails, it goes up by ten.
; Returns with A8 at 1 if the escape worked.
.proc ba_flee
.a8
.i16
    lda BA_ESCAPE
    jsr ba_pct
    bne exited
    lda BA_ESCAPE
    clc
    adc #10
    cmp #101
    bcc saves
    lda #100
saves:
    sta BA_ESCAPE
    lda #0
    rts
exited:
    lda #1
    rts
.endproc

; The first living actor from `BA_ACTOR` on, or A8 at $FF if none is left.
.proc ba_next_actor
.a8
.i16
seek:
    lda BA_ACTOR
    cmp BA_NACTORS
    bcs none
    lda BA_ACTOR
    jsr ba_alive
    bne has
    inc BA_ACTOR
    bra seek
has:
    lda BA_ACTOR
    rts
none:
    lda #$FF
    rts
.endproc

; The first living enemy, in A8, or $FF.
.proc ba_enemy_alive
.a8
.i16
    lda #0
    sta BA_S0
seek:
    lda BA_S0
    cmp BA_KID
    bcs none
    lda BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    bne has
    inc BA_S0
    bra seek
has:
    lda BA_S0
    rts
none:
    lda #$FF
    rts
.endproc

; Records command A8 for actor `BA_ACTOR`, with the target in `BA_T0`, and
; pushes it onto the execution list. The order it is pushed in **matters**:
; the tie-break of the turn order is stable, so the party goes first and then
; the troop, as in `play_turn` of `rm2k-snes-battle`.
.proc ba_record
.a8
.i16
    sta BA_S1
    lda BA_ACTOR
    asl a
    jsr ba_ax
    lda BA_S1
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACTIONS
    jsr ba_ax
    lda BA_ACTOR
    sta BA_EXEC, x
    inc BA_NACTIONS
    inc BA_ACTOR
    rts
.endproc

; The message in `BA_MTYPE` on screen, for `BA_MSG_FRAMES` frames or until
; someone presses A.
.proc ba_show
.a8
.i16
    ; Whatever sound effect was left pending does not outlive the message that
    ; left it: whoever wants one on this one records it after calling here.
    rep #$20
.a16
    lda #$FFFF
    sta BA_SE2
    sep #$20
.a8
    lda #BA_M_MESSAGE
    sta BA_MODE
    lda #BA_MSG_FRAMES
    sta BA_WAIT
    jsr ba_compose
    rts
.endproc

; What plays on the hit that was just resolved, and when.
;
; RM2k plays **two** sound effects per hit: the attack's when the action
; starts —`Normal::GetStartSe`, and only when the one hitting is an enemy—
; and the result's in the message sub-state, a few frames later. Here the
; result's is left pending in `BA_SE2` and goes out after `BA_MSG_FRAMES -
; BA_SE2_FRAMES` frames. When the one hitting is in the party there is no
; first one, so the result's plays right away. (When this was written sound
; effects had a single voice and the two together would have been just one;
; since 8c9c182 they are two, see `sound_effects.s`.)
;
; The result's comes from easyrpg and not from memory: missing is
; `GetFailureSe` —dodge_se—, hitting an actor is actor_damaged_se and an
; enemy enemy_damaged_se, unless it kills it, which is the enemy_death_se of
; `ProcessBattleActionDeath`.
.proc ba_hit_sound
.a8
.i16
    lda BA_MTGT
    jsr ba_x                    ; X: the target's offset
    rep #$20
.a16
    lda BA_MDMG
    cmp #$FFFF
    beq missed
    sep #$20
.a8
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcc to_actor
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    beq died
    lda #BA_SE_DAMAGE_ENEMY
    bra recorded
died:
.a16
    lda #BA_SE_DEATH
    bra recorded
missed:
.a16
    lda #BA_SE_MISS
    bra recorded
to_actor:
.a8
    rep #$20
.a16
    lda #BA_SE_DAMAGE_ACTOR
recorded:
.a16
    sta BA_SE2
    sep #$20
.a8
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcs from_enemy
    ; Someone in the party hits: RM2k gives it no attack sound effect, so the
    ; result's has nothing to wait for and goes out at once.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sound
.a8
    rts
from_enemy:
.a8
    rep #$20
.a16
    lda #BA_SE_ATTACK
    jsl f:ba_t_sound
.a8
    rts
.endproc

; The turn, with the party's commands already recorded: the troop's, the
; execution order, and on to executing.
.proc ba_start_turn
.a8
.i16
    ; `NextTurn`: with the party's commands given, the turn goes up
    ; —`IncTurns`, which is what a page's turn condition looks at— and the
    ; pages can run again —`ResetPagesExecuted`—.
    rep #$20
.a16
    inc BA_TURN
    sep #$20
.a8
    jsr ba_page_turn
    lda #0
    sta BA_S0
clears:
    lda BA_S0
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #(BAF_HAS | BAF_ACTOR | BAF_HIDDEN) ; without BAF_DEF: defending lasts
                                ; one turn
    sta BA_ONE + BA_FLAGS, x
    inc BA_S0
    lda BA_S0
    cmp #BA_COMB_MAX
    bcc clears
    jsr ba_enemy_actions
    jsr ba_exec_order
    lda #0
    sta BA_I
    ; A failed escape says so before anybody acts: see `ba_flee_failed`.
    lda BA_FLEE_FAILED
    beq execute
    stz BA_FLEE_FAILED
    lda #BA_MSG_NO_FLED
    sta BA_MTYPE
    jmp ba_show
execute:
    jmp ba_execute
.endproc

; A victory's experience, handed out: `ProcessSceneActionVictory` gives **the
; whole sum** to each living actor in the party —`GetActiveBattlers`, that is,
; the ones that are not dead—, it does not split it among them. The sum comes
; precomputed per troop in `troop_exp`: every enemy in a victory is dead,
; which is what `Game_EnemyParty::GetExp` asks for. It runs on winning, from
; `ba_vic_start`, before showing anything. It clobbers `BA_S0`, `BA_T*`, A
; and X.
.proc ba_exp_allocate
.a8
.i16
    lda BA_RESULT
    cmp #BA_VICTORY
    bne ready
    lda BA_TROOP_K + 1          ; a word: its high byte alone says $FFFF
    cmp #$FF
    beq ready                   ; a troop the cartridge does not carry
    rep #$20
.a16
    lda BA_TROOP_K
    asl a
    tax
    lda f:troop_exp, x
    ldy #0                      ; the experience: see `ba_no_hidden`
    jsr ba_no_hidden
    sta BA_T1
    sep #$20
.a8
    stz BA_S0
other:
    lda BA_S0
    cmp BA_NACTORS
    bcs ready
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq next
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sep #$20
.a8
    beq next                    ; dead: `Exists()` leaves it out
    lda BA_ONE + BA_NUMBER, x
    jsl f:exp_add
next:
    inc BA_S0
    bra other
ready:
    rts
.endproc

; The end of the turn: either the battle is over, or commands are asked for
; again.
.proc ba_end_of_turn
.a8
.i16
    jsr ba_enemy_alive
    cmp #$FF
    bne continue
    lda #BA_VICTORY
    sta BA_RESULT
    lda #BA_MSG_VICTORY
    sta BA_MTYPE
    ; `Scene_Battle_Rpg2k`'s `BGM_Victory`: the database's, or the last
    ; `ChangeSystemBGM`'s. Games usually give it the battle's song —ABL's
    ; database and every pair of its `ChangeSystemBGM`s do—, and then it goes
    ; on, as with a `PlayBGM` of the song that plays.
    jsl f:ba_t_victory_bgm
    jsr ba_vic_start
    jsr ba_show
    lda #BA_M_END
    sta BA_MODE
    rts
continue:
    lda #0
    sta BA_ACTOR
    jsr ba_next_actor
    cmp #$FF
    bne other_turn
    lda #BA_DEFEAT
    sta BA_RESULT
    lda #BA_MSG_DEFEAT
    sta BA_MTYPE
ends:
    jsr ba_show
    lda #BA_M_END
    sta BA_MODE
    rts
other_turn:
    lda #0
    sta BA_NACTIONS
    sta BA_COMMAND
    lda #BA_M_COMMAND
    sta BA_MODE
    ; And before asking for the commands, once more: the `eCheckEvents` of
    ; `ProcessSceneActionFightAutoEscape`. What already ran this turn does not
    ; come back —the recorded ones are cleared only when the next one
    ; starts—, so this only finds what became true after the last action.
    jsr ba_page_test
    beq no_page
    lda #1
    sta BA_PAGE_TICK
    jmp ba_page_step
no_page:
    jsr ba_compose
    rts
.endproc

; The next action, skipping the ones who died along the way.
.proc ba_execute
.a8
.i16
    ; An item that recovered HP and SP still has its SP line to show, in the
    ; place of the HP one: `ProcessBattleActionParamEffects` writes one
    ; result after the other, and the action is not over until the last.
    lda BA_MSP_NEXT
    beq no_sp_line
    stz BA_MSP_NEXT
    lda #BA_MSG_ITEM_SP
    sta BA_MTYPE
    jmp ba_show
no_sp_line:
    ; A condition the hit released says so after it, in a message of its own:
    ; `ProcessBattleActionDamage` writes it below the damage. See
    ; `ba_st_by_damage`.
    lda .loword(ba_st_next_who)
    cmp #$FF
    beq nothing_released
    sta .loword(ba_st_who)
    lda #$FF
    sta .loword(ba_st_next_who)
    rep #$20
.a16
    lda .loword(ba_st_next_txt)
    sta .loword(ba_st_text)
    sep #$20
.a8
    lda #BA_MSG_STATE
    sta BA_MTYPE
    jmp ba_show
nothing_released:
    ; The action whose condition message was just shown: on to it, with no
    ; pages in between —in RM2k the message is the action's beginning—.
    lda .loword(ba_st_resume)
    beq no_resume
    stz .loword(ba_st_resume)
    lda .loword(ba_st_who)
    sta BA_MWHO
    jmp action
no_resume:
    ; Before each action, and also after the last one, the troop pages whose
    ; conditions hold: it is the `ePreAction` of `ProcessSceneActionBattle`,
    ; with its `CheckBattleEndAndScheduleEvents`. That is how the Detect Aura
    ; page runs right after Talan finishes using it and before the next one
    ; acts. When they finish, `ba_page_step` comes back here, and what already
    ; ran this turn does not run again.
    ;
    ; It goes before `other` and not inside it: skipping one who died changes
    ; nothing a page looks at, which is also why easyrpg takes the dead off
    ; the list before checking and not after.
    jsr ba_page_test
    beq other
    stz BA_PAGE_TICK
    jmp ba_page_step
other:
    lda BA_I
    cmp BA_NACTIONS
    bcc has
    jmp ba_end_of_turn
has:
    lda BA_I
    jsr ba_ax
    lda BA_EXEC, x
    sta BA_MWHO
    inc BA_I
    lda BA_MWHO
    jsr ba_alive
    beq other
    ; What it does now, with its conditions as they are —`PrepareBattleAction`
    ; and `BattleStateHeal`—, and their message before, if there is one. See
    ; battle_states.s.
    jsr ba_st_begin
    beq action
    lda #1
    sta .loword(ba_st_resume)
    lda #BA_MSG_STATE
    sta BA_MTYPE
    jmp ba_show
action:
    lda .loword(ba_st_cmd)
    sta BA_S1                   ; the command
    lda .loword(ba_st_tgt)
    sta BA_MTGT                 ; and the target
    lda BA_S1
    cmp #BA_NONE
    bne acts
    jmp ba_execute              ; nothing: on to the next, pages first
acts:
    cmp #BA_DEFEND
    beq a_defends
    cmp #BA_ITEM
    bne :+
    jmp uses_item
:   cmp #BA_SKILL
    bne attacks
    jmp uses_one_skill
a_defends:
    jmp defends
attacks:
    ; Attack. If the target died before its turn came, it is retargeted to the
    ; first living one on that side, as `Game_BattleAlgorithm` does.
    lda BA_MTGT
    jsr ba_alive
    bne sticks
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs seek_enemy
    lda #0
    sta BA_ACTOR
    jsr ba_next_actor
    cmp #$FF
    beq other
    sta BA_MTGT
    bra sticks
seek_enemy:
    jsr ba_enemy_alive
    cmp #$FF
    bne enemy_found
    jmp other
enemy_found:
    clc
    adc #BA_PARTY_MAX
    sta BA_MTGT
sticks:
    jsr ba_attack
    lda #BA_MSG_ATTACK
    sta BA_MTYPE
    jsr ba_show                 ; which clears the pending one, so it goes first
    jmp ba_hit_sound
uses_one_skill:
    ; A dead target **is not retargeted**, as with an item: `Skill`'s
    ; `IsTargetValid` discards it and the action is lost. With one that
    ; targets the party that is what happens if the one about to be healed was
    ; killed first.
    lda BA_MTGT
    jsr ba_alive
    beq other_skill
    jsr ba_skill_use
    ; A special item's says the item's line and not the skill's:
    ; `Skill::GetStartMessage` with an item whose `using_message` is 0, which
    ; is `GetItemStartMessage2k`, the same first line as a medicine's. And
    ; nothing after it, as a skill's here.
    lda BA_MWHO
    cmp #BA_PARTY_MAX
    bcs as_skill
    jsr ba_ax
    lda f:ba_item_cast, x
    beq as_skill
    lda BA_MWHO
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda BA_ACC_ITEM, x
    sta BA_MITEM
    stz BA_MHEAL
    stz BA_MSP
    sep #$20
.a8
    stz BA_MREVIVED
    stz BA_MHPLINE
    stz BA_MSP_NEXT
    lda #BA_MSG_ITEM
    bra typed
as_skill:
    lda #BA_MSG_SKILL
typed:
    sta BA_MTYPE
    jsr ba_show
    rep #$20
.a16
    lda #BA_SE_ITEM             ; the same as an item: RM2k has no other
    jsl f:ba_t_sound
.a8
    rts
other_skill:
    jmp other
uses_item:
    ; An item does not miss and nobody dodges it, so it rolls no dice; and a
    ; dead target **is not retargeted**, which is the opposite of an attack.
    jsr ba_item_use
    lda #BA_MSG_ITEM
    sta BA_MTYPE
    jsr ba_show
    rep #$20
.a16
    lda #BA_SE_ITEM
    jsl f:ba_t_sound
.a8
    rts
defends:
    lda BA_MWHO
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    ora #BAF_DEF
    sta BA_ONE + BA_FLAGS, x
    lda #BA_MSG_DEFENDS
    sta BA_MTYPE
    jmp ba_show
.endproc

