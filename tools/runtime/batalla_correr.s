.segment "FAR"

; The whole battle. It is entered with `jsl` from `op_battle`, with the data
; bank already at $7E, and returns with the result in `BA_RESULT`.
;
; It runs **its own frame loop**, like `slots_screen` and like the shop:
; `ticks` does not advance while it is shown, so the battle costs no tick,
; however long the player takes. See `OP_BATTLE`
; in tools/port/events.py.
.proc battle_run
.a8
.i16
    rep #$20
.a16
    lda #BATTLE_SEED
    sta BA_SEED                  ; randomness starts the same in every battle
    lda #$FFFF
    sta BA_SE2                  ; no sound effect pending
    sep #$20
.a8
    lda #BA_VICTORY
    sta BA_RESULT
    lda #0
    sta BA_NACC
    sta BA_COMMAND
    sta BA_ACTOR
    sta BA_I
    jsr ba_build
    lda BA_KID
    bne hay_tropa
    rtl                         ; a troop this cartridge does not carry
hay_tropa:
    lda #0
    sta BA_ACTOR
    jsr ba_next_actor
    cmp #$FF
    bne hay_grupo
    lda #BA_DEFEAT             ; nobody standing: lost without fighting
    sta BA_RESULT
    rtl
hay_grupo:
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
    lda #BA_M_COMMAND
    sta BA_MODE
    ; Before the first command, the pages already met: it is the `eCheckEvents`
    ; of `ProcessSceneActionFightAutoEscape`. The first stretch runs **right
    ; here** and not on the next frame: every troop in the game brings a turn 0
    ; page that only turns on a switch, and this way the battle opens already
    ; asking for commands, as it opened before those pages ran. One that shows
    ; a message opens with the message up.
    jsr ba_page_test
    beq sin_pagina_al_empezar
    lda #1
    sta BA_PAGE_TICK
    jsr ba_page_step
sin_pagina_al_empezar:
    jsr ba_compose
    jsl f:ba_t_upload
    ; Turn the screen on **in black**, which the entry transition shows:
    ; `slot_ppu_on` writes full brightness, so it is called inside a
    ; vblank and in the same vblank it is brought down to zero —not a single
    ; line gets drawn—. See `fundido_de_pelea.s`.
    jsl f:ba_t_vblank
    jsl f:ba_t_ppu
    lda #0
    sta f:INIDISP
    jsr scene_on
    jsr battle_fade_showing
    lda #1
    sta menu_open

espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; the controller before the DMA, as in the
                                  ; shop
    jsl f:ba_t_upload
    jsr ba_shake              ; the shake, before the vblank ends
    jsr scene_tick             ; still in the vblank: an enemy that died
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    lda BA_MODE
    cmp #BA_M_COMMAND
    bne :+
    jmp modo_orden
:   cmp #BA_M_TARGET
    bne :+
    jmp modo_blanco
:   cmp #BA_M_ITEM
    bne :+
    jmp modo_item
:   cmp #BA_M_ACTOR
    bne :+
    jmp modo_actor
:   cmp #BA_M_SKILL
    bne :+
    jmp modo_hab
:   cmp #BA_M_MESSAGE
    bne :+
    jmp modo_mensaje
:   cmp #BA_M_PAGE
    bne :+
    jmp modo_pagina
:   jmp modo_fin

    ; --- choosing the command ---
espera5:
    jmp espera
modo_orden:
    lda title_edges
    and #PAD_LEFT
    beq o_no_izq
    lda BA_COMMAND
    beq espera5
    dec BA_COMMAND
    jmp recomponer
o_no_izq:
    lda title_edges
    and #PAD_RIGHT
    beq o_no_der
    lda BA_COMMAND
    cmp #(BA_COMMANDS_N - 1)
    bcs espera5
    inc BA_COMMAND
    jmp recomponer
o_no_der:
    jsr ba_flanco_a
    beq espera5
    lda BA_COMMAND
    cmp #BA_COMMAND_ATTACK
    bne o_no_ataca
    jsr ba_enemy_alive
    cmp #$FF
    beq espera5
    sta BA_TARGET
    lda #BA_M_TARGET
    sta BA_MODE
    jmp recomponer
o_no_ataca:
    cmp #BA_COMMAND_DEFEND
    bne o_no_defiende
    lda #0
    sta BA_T0
    lda #BA_DEFEND
    jsr ba_record
    jmp siguiente_actor
o_no_defiende:
    cmp #BA_COMMAND_USE
    bne o_no_usa
    ; `Use Item`: the list of what can be used. Empty, nothing happens, which
    ; is what the pause menu does with a command that leads nowhere.
    jsr ba_items_list
    lda BA_ITEM_N
    beq espera5
    lda #0
    sta BA_ITEM_SEL
    sta BA_ITEM_ARR
    lda #BA_M_ITEM
    sta BA_MODE
    jmp recomponer
o_no_usa:
    cmp #BA_COMMAND_SKILL
    bne o_no_habilidad
    ; The skill list of whoever is giving the command. Empty —Talan, who is
    ; level 1— nothing happens, which is what the menu does with a command that
    ; leads nowhere.
    jsr ba_skill_list
    lda BA_SKILL_N
    beq espera5
    lda #0
    sta BA_SKILL_SEL
    lda #BA_M_SKILL
    sta BA_MODE
    jmp recomponer
o_no_habilidad:
    cmp #BA_COMMAND_ESCAPE
    beq o_huye
    jmp espera
o_huye:
    jsr ba_flee
    beq o_no_huyo
    lda #BA_ESCAPE_R
    sta BA_RESULT
    lda #BA_MSG_FLED
    sta BA_MTIPO
    jsr ba_show
    rep #$20
.a16
    lda #BA_SE_FLEE             ; the escape_se of `Scene_Battle_Rpg2k`
    jsl f:ba_t_sound
.a8
    lda #BA_M_END
    sta BA_MODE
    jmp espera
o_no_huyo:
    lda #0
    sta BA_T0
    lda #BA_FLEE
    jsr ba_record
    jmp siguiente_actor
espera2:
    jmp espera

    ; --- choosing the target ---
modo_blanco:
    lda title_edges
    and #PAD_UP
    beq b_no_arriba
    jsr ba_blanco_arriba
    jmp recomponer
b_no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq b_no_abajo
    jsr ba_blanco_abajo
    jmp recomponer
b_no_abajo:
    lda title_edges
    and #PAD_B
    beq b_mira_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recomponer
b_mira_a:
    jsr ba_flanco_a
    beq espera2
    lda BA_TARGET
    clc
    adc #BA_PARTY_MAX
    sta BA_T0
    ; The target mode is shared by attacking and by a skill that targets the
    ; enemies; which of the two it is says `BA_COMMAND`, which is still set.
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne b_ataca
    lda #BA_SKILL
    bra b_anota
b_ataca:
    lda #BA_ATTACK
b_anota:
    jsr ba_record
    jmp siguiente_actor         ; the two modes below ended up in between

    ; --- choosing which item ---
modo_item:
    lda title_edges
    and #PAD_UP
    beq i_no_arriba
    lda BA_ITEM_SEL
    beq espera4
    dec BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq i_no_abajo
    lda BA_ITEM_SEL
    inc a
    cmp BA_ITEM_N
    bcs espera4
    sta BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_abajo:
    lda title_edges
    and #PAD_B
    beq i_mira_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recomponer
i_mira_a:
    jsr ba_flanco_a
    beq espera4
    ; Whom to give it to: the first in the party it is good for —standing for
    ; a potion, fallen for an elixir—. If it is good for nobody, A does not get
    ; past the list: see `ba_item_usable_on`.
    lda #0
    sta BA_ACTOR2
busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera4
    jsr ba_item_usable_on
    bne hay_blanco_act
    inc BA_ACTOR2
    bra busca_vivo
hay_blanco_act:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODE
    jmp recomponer
espera4:
    jmp espera

    ; --- choosing whom it is given to ---
modo_actor:
    lda title_edges
    and #PAD_UP
    beq a_no_arriba
    jsr ba_blanco_act_arriba
    jmp recomponer
a_no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq a_no_abajo
    jsr ba_blanco_act_abajo
    jmp recomponer
a_no_abajo:
    lda title_edges
    and #PAD_B
    beq a_mira_a
    ; B goes back to the list it came from: the item list or the skill list.
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne a_vuelve_a_items
    lda #BA_M_SKILL
    sta BA_MODE
    jmp recomponer
a_vuelve_a_items:
    lda #BA_M_ITEM
    sta BA_MODE
    jmp recomponer
a_mira_a:
    jsr ba_flanco_a
    beq espera4
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    bne a_es_item
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_SKILL
    jsr ba_record
    jmp siguiente_actor
a_es_item:
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
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_ITEM
    jsr ba_record
    jmp siguiente_actor

    ; --- choosing which skill ---
    ;
    ; The list has two columns and reads by rows, so left and right move by
    ; one and up and down by two.
modo_hab:
    lda title_edges
    and #PAD_LEFT
    bne h_izq
    jmp h_no_izq
h_izq:
    lda BA_SKILL_SEL
    beq espera6
    dec BA_SKILL_SEL
    jmp recomponer
h_no_izq:
    lda title_edges
    and #PAD_RIGHT
    beq h_no_der
    lda BA_SKILL_SEL
    inc a
    cmp BA_SKILL_N
    bcs espera6
    sta BA_SKILL_SEL
    jmp recomponer
h_no_der:
    lda title_edges
    and #PAD_UP
    beq h_no_arriba
    lda BA_SKILL_SEL
    cmp #BA_SKILL_COLUMNS
    bcc espera6
    sec
    sbc #BA_SKILL_COLUMNS
    sta BA_SKILL_SEL
    jmp recomponer
h_no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq h_no_abajo
    lda BA_SKILL_SEL
    clc
    adc #BA_SKILL_COLUMNS
    cmp BA_SKILL_N
    bcs espera6
    sta BA_SKILL_SEL
    jmp recomponer
espera6:
    jmp espera
h_no_abajo:
    lda title_edges
    and #PAD_B
    beq h_mira_a
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recomponer
h_mira_a:
    jsr ba_flanco_a
    beq espera7
    ; One that cannot be paid for is not chosen, which is what RM2k does with
    ; a greyed-out skill. The cost is deducted **when it executes** and not
    ; here: `Skill::vStart` runs when its turn comes.
    lda BA_SKILL_SEL
    jsr ba_skill_from_list
    sta BA_S0
    jsr ba_skill_reaches
    beq espera6
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
    ; scope: only `enemy` and `ally` ask for it —`batalla.pide_blanco`—.
    lda BA_S0
    jsr ba_ax
    lda f:skill_type, x
    cmp #BA_SKILL_TYPE_SWITCH
    beq h_sin_blanco
    lda f:skill_scope, x
    cmp #BA_SCOPE_ENEMY
    beq h_con_blanco
    cmp #BA_SCOPE_ALLY
    beq h_con_blanco
h_sin_blanco:
    lda BA_ACTOR
    sta BA_T0
    lda #BA_SKILL
    jsr ba_record
    jmp siguiente_actor
h_con_blanco:
    ; Whom it targets: bit 6 of `skill_affects` is `SkillTargetsEnemies`.
    lda BA_S0
    jsr ba_ax
    lda f:skill_affects, x
    and #$40
    beq h_a_un_aliado
    jsr ba_enemy_alive
    cmp #$FF
    beq espera7
    sta BA_TARGET
    lda #BA_M_TARGET
    sta BA_MODE
    jmp recomponer
h_a_un_aliado:
    ; The first one alive in the party, as with an item.
    lda #0
    sta BA_ACTOR2
h_busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera7                 ; cannot happen: whoever gives the command is
                                ; alive
    lda BA_ACTOR2
    jsr ba_alive
    bne h_hay_blanco
    inc BA_ACTOR2
    bra h_busca_vivo
espera7:
    jmp espera
h_hay_blanco:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODE
    jmp recomponer

siguiente_actor:
    ; On to the next one; if none is left, the turn starts.
    jsr ba_next_actor
    cmp #$FF
    beq arranca_turno
    lda #0
    sta BA_COMMAND
    lda #BA_M_COMMAND
    sta BA_MODE
    jmp recomponer
arranca_turno:
    jsr ba_start_turn
    jmp espera

    ; --- a message on screen ---
modo_mensaje:
    jsr ba_flanco_a
    bne pasa
    dec BA_WAIT
    lda BA_WAIT
    cmp #BA_SE2_FRAMES
    bne sin_segundo
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
sin_segundo:
    lda BA_WAIT
    bne espera3
pasa:
    jsr ba_execute
espera3:
    jmp espera

    ; --- a troop page ---
    ;
    ; With one of its messages on screen, it waits for A **with no time
    ; limit**: it is a `ShowMessage`, which in RM2k does not close by itself,
    ; and not one of the battle's, which does. Without a message, the page
    ; carries on.
modo_pagina:
    rep #$20
.a16
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    beq p_sigue
    jsr ba_flanco_a
    beq espera3
    rep #$20
.a16
    lda #$FFFF
    sta BA_PAGE_MSG
    sep #$20
.a8
p_sigue:
    jsr ba_page_step
    jmp espera

    ; --- the battle is over ---
modo_fin:
    jsr ba_flanco_a
    beq espera3
    ; Victory has more than one page: "N EXP", and one for each actor who
    ; leveled up.
    jsr ba_vic_next
    beq cerrar
    jmp recomponer
cerrar:
    ; The party's HP and SP go back to the saved game: since there are battles
    ; they are real state and travel in the SRAM slot.
    lda #0
    sta BA_S0
guarda:
    lda BA_S0
    cmp BA_NACT
    bcs guardados
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sta BA_T0
    lda BA_ONE + BA_SP, x
    sta BA_T1
    sep #$20
.a8
    lda BA_ONE + BA_NUMBER, x
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda BA_T0
    sta FAR_HP, x
    lda BA_T1
    sta FAR_SP, x
    sep #$20
.a8
    inc BA_S0
    bra guarda
guardados:
    rtl

recomponer:
    jsr ba_compose
    jmp espera

; Z=0 if A was just pressed. It is the same one as the shop's: `pad_a` and its
; previous value are set by `read_pad`.
ba_flanco_a:
    lda pad_a
    beq no_a
    lda pad_a_prev
    beq si_a
no_a:
    lda #0
    rts
si_a:
    lda #1
    rts

; Makes the highlighted item visible: scrolls the eight-line window just
; enough.
ba_item_ver:
    lda BA_ITEM_SEL
    cmp BA_ITEM_ARR
    bcs ver_abajo
    sta BA_ITEM_ARR             ; it went off the top: the window follows it
    rts
ver_abajo:
    sec
    sbc #BA_ENEMIES_MAX
    bcc listo_ver               ; it fits without moving anything
    inc a                       ; the first one that should be visible
    cmp BA_ITEM_ARR
    bcc listo_ver
    sta BA_ITEM_ARR
listo_ver:
    rts

; The cursor for whom the item goes to, to the actor above or below where it
; can stop —see `ba_blanco_act_sirve`—. If none is left in that direction, it
; stays where it is. It is the sibling of `ba_blanco_arriba`, over the party
; instead of over the troop.
ba_blanco_act_arriba:
    lda BA_ITEM_BLA
mira_arriba_act:
    beq nada_act
    dec a
    sta BA_ACTOR2               ; `ba_item_usable_on` clobbers `BA_S0`
    jsr ba_blanco_act_sirve
    bne pone_act
    lda BA_ACTOR2
    bra mira_arriba_act
ba_blanco_act_abajo:
    lda BA_ITEM_BLA
mira_abajo_act:
    inc a
    cmp BA_NACT
    bcs nada_act
    sta BA_ACTOR2
    jsr ba_blanco_act_sirve
    bne pone_act
    lda BA_ACTOR2
    bra mira_abajo_act
pone_act:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
nada_act:
    rts

; Whether the "whom" cursor can stop on actor A8: Z=0 if so. It is shared by an
; item and a skill that targets the party, and which of the two it is says
; `BA_COMMAND`. A skill only on those standing, which is what
; `Skill::IsTargetValid` allows with this port's skills —none removes
; death—; an item, on whoever it is good for, who may be a fallen one.
ba_blanco_act_sirve:
    pha
    lda BA_COMMAND
    cmp #BA_COMMAND_SKILL
    beq sirve_hab
    pla
    jmp ba_item_usable_on
sirve_hab:
    pla
    jmp ba_alive

; The target cursor, to the living enemy above or below. If no living one is
; left in that direction, it stays where it is.
ba_blanco_arriba:
    lda BA_TARGET
mira_arriba:
    beq nothing
    dec a
    sta BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    bne pone
    lda BA_S0
    bra mira_arriba
ba_blanco_abajo:
    lda BA_TARGET
mira_abajo:
    inc a
    cmp BA_KID
    bcs nothing
    sta BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_alive
    bne pone
    lda BA_S0
    bra mira_abajo
pone:
    lda BA_S0
    sta BA_TARGET
nothing:
    rts
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
    lda BA_SCENE
    cmp #$FF
    beq ready
    lda shake_pos
    sta f:BG1HOFS               ; absolute `stz` and `sta` would land in WRAM
    lda shake_pos + 1
    sta f:BG1HOFS
ready:
    rts
.endproc
