.segment "FAR2"

; The whole battle. It is entered with `jsl` from `op_battle`, with the data
; bank already at $7E, and returns with the result in `BA_RESULT`.
;
; It runs **its own frame loop**, like `slots_screen` and like the shop:
; `ticks` does not advance while it is shown, so the battle costs no tick,
; however long the player takes. See `OP_BATTLE`
; in rm2k-snes/events/src/compile.rs.
.proc battle_run
.a8
.i16
    rep #$20
.a16
    lda #BATTLE_SEED
    sta BA_SEED                 ; randomness starts the same in every battle
    lda #$FFFF
    sta BA_SE2                  ; no sound effect pending
    sep #$20
.a8
    lda #BA_VICTORY
    sta BA_RESULT
    lda #0
    sta BA_NACTIONS
    sta BA_COMMAND
    sta BA_ACTOR
    sta BA_I
    sta BA_TARGET_TOP
    sta BA_FLEE_FAILED
    sta BA_MSP_NEXT             ; no item's SP line pending: see `ba_execute`
    sta f:ba_abort              ; no `TerminateBattle` yet
    jsr ba_tone_clear           ; nor a flash of the map's: see battle_tone.s
    jsr ba_st_clear             ; nor conditions: see battle_states.s
    jsr ba_build
    lda BA_KID
    bne has_troop
    rtl                         ; a troop this cartridge does not carry
has_troop:
    lda #0
    sta BA_ACTOR
    jsr ba_next_actor
    cmp #$FF
    bne has_party
    lda #BA_DEFEAT              ; nobody standing: lost without fighting
    sta BA_RESULT
    rtl
has_party:
    jsr ba_flee_chance
    jsr ba_page_build
    ; Turn off the screen, from here: the three registers go through `f:`
    ; because the data bank is $7E and absolute ones would land in RAM.
    lda #$80
    sta f:INIDISP
    lda #0
    sta f:HDMAEN
    sta f:TM
    jsl f:ba_t_bank
    ; And the scene: the background with the monsters, composed here and
    ; uploaded to BG1. It goes with the screen off because it is 32 KB of VRAM
    ; plus the tilemap and the palettes.
    jsr scene_upload
    jsr ba_win_load             ; and the windows' tiles and colours
    lda #BA_M_COMMAND
    sta BA_MODE
    ; Before the first command, the pages already met: it is the `eCheckEvents`
    ; of `ProcessSceneActionFightAutoEscape`. The first stretch runs **right
    ; here** and not on the next frame: every troop in the game brings a turn 0
    ; page that only turns on a switch, and this way the battle opens already
    ; asking for commands, as it opened before those pages ran. One that shows
    ; a message opens with the message up.
    jsr ba_page_test
    beq no_page_start
    lda #1
    sta BA_PAGE_TICK
    jsr ba_page_step
no_page_start:
    jsr ba_compose
    jsl f:ba_t_upload
    jsr ba_win_upload           ; with the screen off, whatever the text says
    ; And the scene with the tint the map left and the one a turn 0 page may
    ; have asked for, before the entry shows it.
    jsr ba_tone_start
    ; Turn the screen on **in black**, which the entry transition shows:
    ; `slot_ppu_on` writes full brightness, so it is called inside a
    ; vblank and in the same vblank it is brought down to zero —not a single
    ; line gets drawn—. See `battle_fade.s`.
    jsl f:ba_t_vblank
    jsl f:ba_t_ppu
    lda #0
    sta f:INIDISP
    ; BG2's tiles from word 0 and not where `slot_ppu_on` put them: see
    ; `battle_bank_upload`. `scene_on` writes it again with the scene's.
    lda #(TL_BATTLE_VRAM / 4096 * 16)
    sta f:BG12NBA
    jsr scene_on
    jsl f:battle_fade_showing
    lda #1
    sta menu_open

wait:
    ; The flash and the tint, built for the vblank about to come: **after**
    ; the frame's work, as the map's `flash_tick` goes after `events_tick`,
    ; so a page's `FlashScreen` shows in the next frame, already one step
    ; down. Every mode below ends coming back here.
    jsr ba_tone_tick
    jsl f:ba_t_vblank
    jsr ba_tone_upload          ; the scene's palette, first: it is small, and
                                ; the text's upload can run long
    jsl f:ba_t_pad                ; the controller before the DMA, as in the
                                  ; shop
    jsl f:ba_t_upload
    jsr ba_win_tick             ; the windows, in the vblank too
    jsr ba_shake                ; the shake, before the vblank ends
    jsr scene_tick              ; still in the vblank: an enemy that died
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    lda BA_MODE
    cmp #BA_M_COMMAND
    bne :+
    jmp mode_command
:   cmp #BA_M_TARGET
    bne :+
    jmp mode_target
:   cmp #BA_M_ITEM
    bne :+
    jmp mode_item
:   cmp #BA_M_ACTOR
    bne :+
    jmp mode_actor
:   cmp #BA_M_SKILL
    bne :+
    jmp mode_skill
:   cmp #BA_M_MESSAGE
    bne :+
    jmp mode_message
:   cmp #BA_M_PAGE
    bne :+
    jmp mode_page
:   cmp #BA_M_ABORT
    bne :+
    jmp close                   ; a `TerminateBattle`: no end screen
:   jmp mode_end

    ; --- choosing the command ---
    ;
    ; A column, as RM2k's: up and down. Until 2026-10-04 they were two lines
    ; and the cursor went left and right.
wait5:
    jmp wait
mode_command:
    lda title_edges
    and #PAD_UP
    beq o_no_up
    lda BA_COMMAND
    beq wait5
    dec BA_COMMAND
    jmp recompose
o_no_up:
    lda title_edges
    and #PAD_DOWN
    beq o_no_down
    jsr ba_commands_n           ; four in a battle that cannot be escaped from
    dec a
    cmp BA_COMMAND
    beq wait5
    bcc wait5
    inc BA_COMMAND
    jmp recompose
o_no_down:
    jsr ba_edge_a
    beq wait5
    lda BA_COMMAND
    cmp #BA_COMMAND_ATTACK
    bne o_no_attacks
    jsr ba_enemy_alive
    cmp #$FF
    beq wait5
    sta BA_TARGET
    stz BA_TARGET_TOP
    lda #BA_M_TARGET
    sta BA_MODE
    jmp recompose
o_no_attacks:
    cmp #BA_COMMAND_DEFEND
    bne o_no_defends
    lda #0
    sta BA_T0
    lda #BA_DEFEND
    jsr ba_record
    jmp next_actor
o_no_defends:
    cmp #BA_COMMAND_USE
    bne o_no_uses
    ; `Use Item`: the list of what can be used. Empty, nothing happens, which
    ; is what the pause menu does with a command that leads nowhere.
    jsr ba_items_list
    lda BA_ITEM_N
    beq wait5
    lda #0
    sta BA_ITEM_SEL
    sta BA_ITEM_ARR
    lda #BA_M_ITEM
    sta BA_MODE
    jmp recompose
o_no_uses:
    cmp #BA_COMMAND_SKILL
    bne o_no_skill
    ; The skill list of whoever is giving the command. Empty —Talan, who is
    ; level 1— nothing happens, which is what the menu does with a command that
    ; leads nowhere.
    stz BA_SKILL_TOP            ; before the list: it keeps only the window
    jsr ba_skill_list
    lda BA_SKILL_N
    bne o_knows_some
    jmp wait
o_knows_some:
    lda #0
    sta BA_SKILL_SEL
    lda #BA_M_SKILL
    sta BA_MODE
    jmp recompose
o_no_skill:
    cmp #BA_COMMAND_ESCAPE
    beq o_flees
    jmp wait
o_flees:
    ; Escaping is the party's, as in RM2k, whoever chooses it: see
    ; `ba_flee_failed`.
    jsr ba_flee
    beq o_no_fled
    lda #BA_ESCAPE_R
    sta BA_RESULT
    lda #BA_MSG_FLED
    sta BA_MTYPE
    jsr ba_show
    rep #$20
.a16
    lda #BA_SE_FLEE             ; the escape_se of `Scene_Battle_Rpg2k`
    jsl f:ba_t_sound
.a8
    lda #BA_M_END
    sta BA_MODE
    jmp wait
o_no_fled:
    jsr ba_flee_failed
    jmp wait
wait2:
    jmp wait

    ; --- choosing the target ---
mode_target:
    lda title_edges
    and #PAD_UP
    beq b_no_up
    jsr ba_target_up
    jmp recompose
b_no_up:
    lda title_edges
    and #PAD_DOWN
    beq b_no_down
    jsr ba_target_down
    jmp recompose
b_no_down:
    lda title_edges
    and #PAD_B
    beq b_check_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recompose
b_check_a:
    jsr ba_edge_a
    beq wait2
    lda BA_TARGET
    clc
    adc #BA_PARTY_MAX
    sta BA_T0
    ; The target mode is shared by attacking and by a skill that targets the
    ; enemies; which of the two it is says `BA_COMMAND`, which is still set.
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne b_attacks
    lda #BA_SKILL
    bra b_records
b_attacks:
    lda #BA_ATTACK
b_records:
    jsr ba_record
    jmp next_actor              ; the two modes below ended up in between

    ; --- choosing which item ---
    ;
    ; Two columns that read by rows, like the skills: left and right move by
    ; one and up and down by two. Until 2026-10-04 it was one column of eight.
mode_item:
    lda title_edges
    and #PAD_LEFT
    beq i_no_left
    lda BA_ITEM_SEL
    beq wait4
    dec BA_ITEM_SEL
    bra i_moved
i_no_left:
    lda title_edges
    and #PAD_RIGHT
    beq i_no_right
    lda BA_ITEM_SEL
    inc a
    cmp BA_ITEM_N
    bcs wait4
    sta BA_ITEM_SEL
    bra i_moved
i_no_right:
    lda title_edges
    and #PAD_UP
    beq i_no_up
    lda BA_ITEM_SEL
    cmp #2
    bcc wait4
    sbc #2                      ; C=1 from the cmp
    sta BA_ITEM_SEL
    bra i_moved
i_no_up:
    lda title_edges
    and #PAD_DOWN
    beq i_no_down
    lda BA_ITEM_SEL
    clc
    adc #2
    cmp BA_ITEM_N
    bcs wait4
    sta BA_ITEM_SEL
i_moved:
    jsr ba_item_see
    jmp recompose
i_no_down:
    lda title_edges
    and #PAD_B
    beq i_check_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recompose
i_check_a:
    jsr ba_edge_a
    beq wait4
    ; Whom to give it to: the first in the party it is good for —standing for
    ; a potion, fallen for an elixir—. If it is good for nobody, A does not get
    ; past the list: see `ba_item_usable_on`.
    lda #0
    sta BA_ACTOR2
seek_alive:
    lda BA_ACTOR2
    cmp BA_NACTORS
    bcs wait4
    jsr ba_item_usable_on
    bne has_target_act
    inc BA_ACTOR2
    bra seek_alive
has_target_act:
    lda BA_ACTOR2
    sta BA_ITEM_TGT
    lda #BA_M_ACTOR
    sta BA_MODE
    jmp recompose
wait4:
    jmp wait

    ; --- choosing whom it is given to ---
mode_actor:
    lda title_edges
    and #PAD_UP
    beq a_no_up
    jsr ba_target_act_up
    jmp recompose
a_no_up:
    lda title_edges
    and #PAD_DOWN
    beq a_no_down
    jsr ba_target_act_down
    jmp recompose
a_no_down:
    lda title_edges
    and #PAD_B
    beq a_check_a
    ; B goes back to the list it came from: the item list or the skill list.
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne a_back_to_items
    lda #BA_M_SKILL
    sta BA_MODE
    jmp recompose
a_back_to_items:
    lda #BA_M_ITEM
    sta BA_MODE
    jmp recompose
a_check_a:
    jsr ba_edge_a
    beq wait4
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne a_is_item
    lda BA_ITEM_TGT
    sta BA_T0
    lda #BA_SKILL
    jsr ba_record
    jmp next_actor
a_is_item:
    ; The command is recorded and **the item is spent right away**, which is
    ; what RM2k does on choosing it: otherwise the last one of an item could be
    ; handed out to two actors in the same turn.
    lda BA_ITEM_SEL
    jsr ba_item_from_list
    pha
    lda BA_ACTOR
    jsr ba_ax
    pla
    sta BA_ACC_ITEM, x
    jsr ba_item_consume
    lda BA_ITEM_TGT
    sta BA_T0
    lda #BA_ITEM
    jsr ba_record
    jmp next_actor

    ; --- choosing which skill ---
    ;
    ; The list has two columns and reads by rows, so left and right move by
    ; one and up and down by two. Whatever moves the cursor scrolls the window
    ; just enough to show it —`ba_skill_see`—, and the screen is composed
    ; again, which is what brings the new page into `BA_SKILL_LIST`.
mode_skill:
    lda title_edges
    and #PAD_LEFT
    bne h_left
    jmp h_no_left
h_left:
    lda BA_SKILL_SEL
    beq wait6
    dec BA_SKILL_SEL
    jmp h_moved
h_no_left:
    lda title_edges
    and #PAD_RIGHT
    beq h_no_right
    lda BA_SKILL_SEL
    inc a
    cmp BA_SKILL_N
    bcs wait6
    sta BA_SKILL_SEL
    jmp h_moved
h_no_right:
    lda title_edges
    and #PAD_UP
    beq h_no_up
    lda BA_SKILL_SEL
    cmp #BA_SKILL_COLUMNS
    bcc wait6
    sec
    sbc #BA_SKILL_COLUMNS
    sta BA_SKILL_SEL
    jmp h_moved
h_no_up:
    lda title_edges
    and #PAD_DOWN
    beq h_no_down
    lda BA_SKILL_SEL
    clc
    adc #BA_SKILL_COLUMNS
    cmp BA_SKILL_N
    bcs wait6
    sta BA_SKILL_SEL
h_moved:
    jsr ba_skill_see
    jmp recompose
wait6:
    jmp wait
h_no_down:
    lda title_edges
    and #PAD_B
    beq h_check_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recompose
h_check_a:
    jsr ba_edge_a
    beq wait7
    ; One that cannot be paid for is not chosen, which is what RM2k does with
    ; a greyed-out skill. The cost is deducted **when it executes** and not
    ; here: `Skill::vStart` runs when its turn comes.
    jsr ba_skill_list           ; the window's page, whoever wrote there last
    lda BA_SKILL_SEL
    jsr ba_skill_from_list
    sta BA_S0
    jsr ba_skill_reaches
    beq wait6
    lda BA_ACTOR
    jsr ba_ax
    lda BA_S0
    sta BA_ACC_SKILL, x
    ; A switch skill **asks for no target**, whatever its `scope` points at:
    ; `Scene_Battle::AssignSkill` records it on its user and moves on. Without
    ; this, Detect Aura —`scope` 0, one enemy— asked to choose one, and if that
    ; one died before the turn the skill was lost, which does not happen in
    ; RM2k.
    ;
    ; Nor do the ones on many or on oneself, whose target is decided by the
    ; scope: only `enemy` and `ally` ask for it —see `needs_target`—.
    lda BA_S0
    jsr ba_ax
    lda f:skill_type, x
    cmp #BA_SKILL_TYPE_SWITCH
    beq h_no_target
    lda f:skill_scope, x
    cmp #BA_SCOPE_ENEMY
    beq h_with_target
    cmp #BA_SCOPE_ALLY
    beq h_with_target
h_no_target:
    lda BA_ACTOR
    sta BA_T0
    lda #BA_SKILL
    jsr ba_record
    jmp next_actor
h_with_target:
    ; Whom it targets: bit 6 of `skill_affects` is `SkillTargetsEnemies`.
    lda BA_S0
    jsr ba_ax
    lda f:skill_affects, x
    and #$40
    beq h_a_ally
    jsr ba_enemy_alive
    cmp #$FF
    beq wait7
    sta BA_TARGET
    lda #BA_M_TARGET
    sta BA_MODE
    jmp recompose
h_a_ally:
    ; The first one alive in the party, as with an item.
    lda #0
    sta BA_ACTOR2
h_seek_alive:
    lda BA_ACTOR2
    cmp BA_NACTORS
    bcs wait7                   ; cannot happen: whoever gives the command is
                                ; alive
    lda BA_ACTOR2
    jsr ba_alive
    bne h_has_target
    inc BA_ACTOR2
    bra h_seek_alive
wait7:
    jmp wait
h_has_target:
    lda BA_ACTOR2
    sta BA_ITEM_TGT
    lda #BA_M_ACTOR
    sta BA_MODE
    jmp recompose

next_actor:
    ; On to the next one; if none is left, the turn starts.
    jsr ba_next_actor
    cmp #$FF
    beq starts_turn
    lda #0
    sta BA_COMMAND
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recompose
starts_turn:
    jsr ba_start_turn
    jmp wait

    ; --- a message on screen ---
mode_message:
    jsr ba_edge_a
    bne pass
    dec BA_WAIT
    lda BA_WAIT
    cmp #BA_SE2_FRAMES
    bne no_second
    ; The hit's second sound effect, the one RM2k plays in the message
    ; sub-state. It is taken out of `BA_SE2` when fired so it does not come out
    ; again if the message runs longer.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sound
.a8
no_second:
    lda BA_WAIT
    bne wait3
pass:
    jsr ba_execute
wait3:
    jmp wait

    ; --- a troop page ---
    ;
    ; With one of its messages on screen, it waits for A **with no time
    ; limit**: it is a `ShowMessage`, which in RM2k does not close by itself,
    ; and not one of the battle's, which does. Without a message, the page
    ; carries on.
mode_page:
    rep #$20
.a16
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    beq p_continues
    jsr ba_edge_a
    beq wait3
    rep #$20
.a16
    lda #$FFFF
    sta BA_PAGE_MSG
    sep #$20
.a8
p_continues:
    jsr ba_page_step
    jmp wait

    ; --- the battle is over ---
mode_end:
    jsr ba_edge_a
    beq wait3
    ; Victory has more than one page: "N EXP", and one for each actor who
    ; leveled up.
    jsr ba_vic_next
    beq close
    jmp recompose
close:
    ; The party's HP and SP go back to the saved game: since there are battles
    ; they are real state and travel in the SRAM slot. It is the same copy a
    ; troop page's stretch does before running, and it skips, like that one,
    ; the places a page left empty.
    jsr ba_sync_out
    ; Without the battle's HDMA, and BG1 where the band left it: the exit
    ; shows the scene as it is, and the map turns on its own.
    lda #0
    sta f:HDMAEN
    ; A flash a page left going stays in the battle: the map's `flash_tick`
    ; would finish it over the map's palettes. The tint does go back with
    ; the map, which `back_to_map` applies.
    jsr ba_tone_clear
    rtl

recompose:
    jsr ba_compose
    jmp wait

; Z=0 if A was just pressed. It is the same one as the shop's: `pad_a` and its
; previous value are set by `read_pad`.
ba_edge_a:
    lda pad_a
    beq no_a
    lda pad_a_prev
    beq a_pressed
no_a:
    lda #0
    rts
a_pressed:
    lda #1
    rts

; The cursor for whom the item goes to, to the actor above or below where it
; can stop —see `ba_target_act_serves`—. If none is left in that direction, it
; stays where it is. It is the sibling of `ba_target_up`, over the party
; instead of over the troop.
ba_target_act_up:
    lda BA_ITEM_TGT
look_up_act:
    beq nothing_act
    dec a
    sta BA_ACTOR2               ; `ba_item_usable_on` clobbers `BA_S0`
    jsr ba_target_act_serves
    bne sets_act
    lda BA_ACTOR2
    bra look_up_act
ba_target_act_down:
    lda BA_ITEM_TGT
look_down_act:
    inc a
    cmp BA_NACTORS
    bcs nothing_act
    sta BA_ACTOR2
    jsr ba_target_act_serves
    bne sets_act
    lda BA_ACTOR2
    bra look_down_act
sets_act:
    lda BA_ACTOR2
    sta BA_ITEM_TGT
nothing_act:
    rts

; Whether the "whom" cursor can stop on actor A8: Z=0 if so. It is shared by an
; item and a skill that targets the party, and which of the two it is says
; `BA_COMMAND`. A skill only on those standing, which is what
; `Skill::IsTargetValid` allows with this port's skills —none removes
; death—; an item, on whoever it is good for, who may be a fallen one.
ba_target_act_serves:
    pha
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    beq serves_skill
    pla
    jmp ba_item_usable_on
serves_skill:
    pla
    jmp ba_alive

; The target cursor, to the living enemy above or below. If no living one is
; left in that direction, it stays where it is.
ba_target_up:
    lda BA_TARGET
look_up:
    beq nothing
    dec a
    sta BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    bne sets
    lda BA_S0
    bra look_up
ba_target_down:
    lda BA_TARGET
look_down:
    inc a
    cmp BA_KID
    bcs nothing
    sta BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    bne sets
    lda BA_S0
    bra look_down
sets:
    lda BA_S0
    sta BA_TARGET
nothing:
    rts
.endproc

; A failed escape: RM2k's `ProcessSceneActionEscape` with `eFailure`, which
; goes on to the turn with only the enemies' actions —`NextTurn`,
; `CreateEnemyActions`—. Escaping there is the party's, from the menu before
; the commands; here it is a fifth command, of RPG Maker 2000 PLUS, and
; whoever chooses it chooses it for everybody: the commands the ones before
; it gave are forgotten, and an item one of them chose —which is spent on
; choosing it— goes back to the inventory. The message goes first, as in
; RM2k: see `ba_start_turn`. `rm2k-snes-battle` plays it as a turn with no
; commands, so that only the enemies go into the execution order, as here.
.proc ba_flee_failed
.a8
.i16
    stz BA_S0
other:
    lda BA_S0
    cmp BA_NACTIONS
    bcs given_back
    jsr ba_ax
    lda BA_EXEC, x
    sta BA_S1                   ; who gave it
    asl a
    jsr ba_ax
    lda BA_ACC, x
    cmp #BA_ITEM
    bne next
    lda BA_S1
    jsr ba_ax
    lda BA_ACC_ITEM, x
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
    inc a                       ; it was spent from here: it fits again
    sta FAR_ITEMS, x
next:
    inc BA_S0
    bra other
given_back:
    lda #0
    sta BA_NACTIONS
    lda #1
    sta BA_FLEE_FAILED
    jmp ba_start_turn
.endproc

; The screen shake in battle: one frame of `shake_tick` and its position in
; the scene's scroll. It belongs to `Game_Screen` and not to the map, so in
; RM2k it carries on into the battle, and it is started by the `ShakeScreen`
; of a troop page —the takeoff in the agents' battle—. It moves the background
; and the battlers, which is what `Spriteset_Battle` runs with
; `GetShakeOffsetX`; the windows stay still, and here so does the text, which
; is BG2.
.proc ba_shake
.a8
.i16
    jsl f:ba_t_shake
    ; To the HDMA's table, which writes BG1HOFS per band —see `scene_on`—:
    ; the scene's band, and the description's when the scene shows there.
    ; The windows' band stays at zero.
    rep #$20
.a16
    lda shake_pos
    sta BA_HOFS_HDMA + 4
    sep #$20
.a8
    lda BA_WIN_SHOWN + 3
    rep #$20
.a16
    beq on_top                  ; `rep` does not touch Z
    lda #0
    bra top_set
on_top:
    lda shake_pos
top_set:
    sta BA_HOFS_HDMA + 1
    sep #$20
.a8
    rts
.endproc
