.segment "CODE"
.a8
.i16

; --- the interpreter: the shop and the battle ------------------------------
;
; Opcode handlers: the dispatch of `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or cuts the frame short with `rts`.
;
; At the end goes `battle_start`, which is not a handler: it is the battle
; from start to finish, called by `op_battle` and by random encounters.

; `OpenShop`: type, set, how many and the list, two bytes per item. The shop
; opens in here and, on leaving, the map comes back and the page continues.
.proc op_shop
.a8
.i16
    lda [code_ptr], y
    sta comp_col + 1
    iny
    lda [code_ptr], y
    sta comp_phase
    iny
    lda [code_ptr], y
    iny
    sta pick_cancel             ; how many follow
    stz comp_mask + 1
    ; `item_k` lives in the code's bank and the interpreter runs with the data
    ; bank where the bytecode is: it is switched until we come back.
    phb
    phk
    plb
op_shop_other:
    lda pick_cancel
    beq op_shop_done
    rep #$20
.a16
    lda [code_ptr], y           ; the item
    iny
    iny
    asl a
    tax
    lda f:item_k, x
    cmp #$FFFF
    beq op_shop_next            ; one this ROM does not know
    pha
    lda comp_mask + 1
    and #$00FF
    asl a
    tax
    pla
    sta f:$7E0000 + FAR_SHOP, x
    sep #$20
.a8
    inc comp_mask + 1
op_shop_next:
    sep #$20
.a8
    dec pick_cancel
    bra op_shop_other
op_shop_done:
    phy
    jsl f:shop_screen
    ; The edges that closed the shop belong to it, as in the menu.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz menu_open
    lda boot_frames
    sta nmi_seen
    jsl f:screen_unerase        ; the map comes back even if an event erased it
    jsr back_to_map
    ply
    plb
    jmp run_code::other

.endproc

; `EnemyEncounter`: the troop and the three destinations, all sixteen bits.
; The battle is played in here and, on leaving, the map comes back —as with
; the shop— and the page continues at the destination the result picked.
; The escape's destination of a battle with `escape_mode` 0, which cannot be
; escaped from: `BATTLE_NO_ESCAPE` in the event compiler of
; `rm2k-snes-events`, which is where it is chosen.
BATTLE_NO_ESCAPE = $FFFE

.proc op_battle
.a8
.i16
    rep #$20
.a16
    lda [code_ptr], y           ; the troop, as an RM2k number
    sta f:BAT_LENGTH + BA_TROOP
    ; Whether it can be escaped from, which the escape's destination says:
    ; `BATTLE_NO_ESCAPE` with `escape_mode` 0. It is the battle's Escape
    ; command, which goes only where RM2k lets the party escape.
    iny
    iny
    iny
    iny
    lda [code_ptr], y
    dey
    dey
    dey
    dey
    cmp #BATTLE_NO_ESCAPE
    sep #$20
.a8
    beq no_escape               ; `sep` does not touch Z
    lda #1
    bra escape_set
no_escape:
    lda #0
escape_set:
    sta f:BAT_LENGTH + BA_CAN_FLEE
    lda #0
    sta f:BAT_LENGTH + SCN_ORIGIN ; the background, the troop's and not the map's
    jsl f:game_over_record      ; whether losing is Game Over: see game_over.s
    phy                         ; the cursor: the destinations are read on return
    jsr battle_start
    ply
    ; Y points at the troop; the four destinations come after it, one word
    ; each, in the order victory, escape, defeat, which is that of
    ; `BATTLE_HANDLERS`, and the abort of a `TerminateBattle`: `BA_RESULT`
    ; indexes them.
    lda f:BAT_LENGTH + BA_RESULT
    jmp op_battle_destination

.endproc

.proc op_battle_destination
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sty temp
    clc
    adc temp
    inc a
    inc a
    tay
    lda [code_ptr], y           ; the destination, absolute within the page
    tay
    ; `BATTLE_LOSE`, that is $FFFF —the battle had no defeat handler,
    ; because in RM2k losing it is `Scene_Gameover`— never gets here:
    ; `game_over_record` records it before fighting, and `battle_start` goes
    ; to the Game Over screen without coming back. See
    ; runtime/game_over.s.
    sep #$20
.a8
    jmp run_code::other


.endproc

; `TerminateBattle`, from a troop page: the page ends here and the battle
; with it —`ba_page_step` sees `ba_abort` when the stretch comes back—. On a
; map it does nothing and the page carries on, which is what EasyRPG's map
; interpreter does with a command it does not know.
.proc op_battle_abort
.a8
.i16
    lda pair_ev
    cmp #PAIR_BATTLE
    beq in_battle
    jmp run_code::other
in_battle:
    lda #1
    sta f:ba_abort
    jmp op_done
.endproc

; `ShowHiddenMonster`, which only exists in a troop page: the member in that
; position stops being hidden. `ba_show_hidden` does it, in the battle's
; bank, which is where its state lives.
.proc op_show_enemy
.a8
.i16
    lda [code_ptr], y
    iny
    phy
    jsl f:ba_show_hidden
    ply
    jmp run_code::other
.endproc

; `ChangeMonsterCondition`: only the entry, like `op_enemy`. `ba_st_change`
; reads the operands and leaves Y after them.
.proc op_monster_state
    jsl f:ba_st_change
    jmp run_code::other
.endproc

; `ChangeMonsterHP` and `ChangeMonsterMP`: only the entry, like `op_heal`.
; `ba_enemy_change` reads the operands and leaves Y after them.
.proc op_enemy
    jsl f:ba_enemy_change
    jmp run_code::other
.endproc

; A battle from start to finish, with the troop already set in `BA_TROOP`:
; save the map's song, load the battle's audio, fight it and go back to the
; map.
;
; It has been separate from `op_battle` since there are random encounters,
; which start it **without bytecode**: there, there is no cursor to save and
; no handlers to jump to. What is inside did not move.
.proc battle_start
.a8
.i16
    ; The map's song is saved and comes back at the end, which is RM2k's
    ; `before_battle_music` —`Scene_Battle` records it when constructed and
    ; `Game_Map` restores it on return—. $FF means "nothing was playing", and
    ; it is a real case: the game's first maps have no music.
    ; **With the data bank at 0**, which here is still the bytecode's:
    ; `music_off` and `song_current` are absolute BSS addresses and without
    ; this they would be read from the cartridge bank where the page is. It is
    ; the same trap as the `ba_t_*` bridges on the other side, and it cost
    ; exactly the same.
    phb
    phk
    plb
    ; **The MSU-1 first.** With a CD track playing, `music_start` leaves the
    ; SPC700 silent on purpose —`music_off` at 1— and looking only at that
    ; recorded $FF: at the end of the battle `battle_bgm` silenced the map's
    ; music instead of restoring it. It is the same question as
    ; `map_song_mute`, and it is answered the same way.
    lda f:MSU_PLAYING
    bne was_playing_before
    lda music_off
    bne muted_before
was_playing_before:
    lda song_current
    bra recorded
muted_before:
    lda #$FF
recorded:
    sta f:BAT_LENGTH + BA_SONG_PREV
    ; The battle's audio package: its song and its sound effects. It goes apart
    ; from the map's package and not inside it, and that is measured: the battle
    ; song is 18 samples and 51,480 B of the 64,512 of ARAM, which means that
    ; putting it in map 2's package dropped almost all of that map's 24 sound
    ; effects. It is silenced before rebuilding, as `song_ensure` does:
    ; `package_load` leaves the playing song's samples in place, and the
    ; map's have no reason to take up room inside the battle.
    ;
    ; **With the map already black**: the load takes from half a second to a
    ; second and a half, and it is the entry transition that hides it. See
    ; `battle_fade.s`.
    jsl f:battle_fade_in
    ldx #BA_PACKAGE
    jsr battle_audio_load
    lda #BA_SONG
    jsl f:bgm_level_battle_in   ; the map's level, kept; the battle's, as written
    jsr battle_bgm
    plb
    ; The data bank, at $7E: that is what lets the battle code use absolute
    ; addressing on its state without losing low RAM, which in that bank is at
    ; the same addresses. See the comment on `FAR_BATTLE`.
    phb
    lda #$7E
    pha
    plb
    jsl f:battle_run
    plb
    ; The edges that closed the battle belong to it, as in the shop and the
    ; menu: otherwise, the A that closed the last message would open whatever
    ; is on the map.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz menu_open
    lda boot_frames
    sta nmi_seen
    phb
    phk
    plb                         ; bank 0, for the same reason as on entry
    jsl f:battle_fade_out ; the battle to black, which hides the load
    ; And if it was lost and losing is Game Over, there is no coming back from
    ; here: the screen appears from the battle's black, without going through
    ; the map, as in RM2k.
    jsl f:game_over_if_lost
    ldx map_current             ; and the map's audio goes back to the SPC700
    jsr battle_audio_load
    lda f:BAT_LENGTH + BA_SONG_PREV
    jsl f:bgm_level_battle_out  ; at the level it had
    jsr battle_bgm              ; the map's song, or the silence there was
    plb
    jsr back_from_battle
    phb
    phk
    plb
    jsr battle_fade_to_map      ; and the map from black, with `flush_video`
    plb
    rts
.endproc
