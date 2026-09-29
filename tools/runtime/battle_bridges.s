.segment "CODE"

; --- the battle -----------------------------------------------------------------
;
; `EnemyEncounter`, opened by `OP_BATTLE` from the interpreter: like the shop
; and like saving, the screen blocks inside the page, `ticks` does not
; advance while it is up and **it costs no tick**. What sets it apart from the
; other two is that the result **chooses where the page continues**: the
; opcode carries the three destinations and here the cursor is given the one
; that applies.
;
; The rules —damage, hit, critical, variance, turn order, escape— come from
; easyrpg-player and are written twice: here and in `tools/port/battle.py`,
; which is what lets `rom/pruebas/rpgmaker/test_batalla.py` predict the exact
; number each HP will have. The screen is text, on black.
;
; **The battle code does not live in bank 0**: it is about two kilobytes and
; bank 0 had three hundred bytes left. It lives in RODATA —see
; `battle_run`, in `battle_run.s`— and is entered with `jsl`. From
; there it cannot come back here with `jsr`, which does not change the program
; bank, so the bank 0 routines the battle needs are called through these
; four-byte bridges. The data bank is still 0 on both sides, so a bridge does
; not have to touch it: all it does is switch program bank and return.
;
; **Each bridge restores the data bank**, which on the other side is $7E. It
; is not a detail: `eq_parameter` reads `actor_params` and
; `slot_ppu_on` writes BG2SC, both with absolute addressing, and with
; the bank at $7E the first would read WRAM and the second would write to RAM
; instead of the PPU. It cost an afternoon: each actor's three parameters came
; out as 999.
;
; `phk` here pushes the bank of this code, which is 0 because the `jsl`
; arrives with a $00xxxx address.
ba_t_vblank:
    phb
    phk
    plb
    jsr wait_vblank
    plb
    rtl
ba_t_pad:
    phb
    phk
    plb
    jsr read_pad
    plb
    rtl
ba_t_upload:
    phb
    phk
    plb
    jsr scr_upload
    plb
    rtl
ba_t_clear:
    phb
    phk
    plb
    jsr scr_clear
    plb
    rtl
ba_t_text:
    phb
    phk
    plb
    jsr scr_text
    plb
    rtl
ba_t_number:
    phb
    phk
    plb
    jsr scr_number
    plb
    rtl
ba_t_glyph:
    phb
    phk
    plb
    jsr scr_glyph
    plb
    rtl
ba_t_bank:
    phb
    phk
    plb
    jsl f:items_bank_upload
    plb
    rtl
ba_t_ppu:
    phb
    phk
    plb
    jsr slot_ppu_on
    plb
    rtl
ba_t_param:
    phb
    phk
    plb
    jsl f:eq_parameter
    plb
    rtl
; The two for audio, which are from this round: a sound effect —A16 the index
; into `sound_table`, $FFFF none— and the song, with A8.
ba_t_sound:
    phb
    phk
    plb
    jsr sound_play
    plb
    rtl
ba_t_bgm:
    phb
    phk
    plb
    jsr battle_bgm
    plb
    rtl
; And the audio package in X, which is `battle_audio_load`: the Game Over
; screen uses it, which uploads its own. See tools/runtime/game_over.s.
ba_t_audio:
    phb
    phk
    plb
    jsr battle_audio_load
    plb
    rtl
; One frame of the screen shake, which in RM2k belongs to `Game_Screen` and
; keeps running in battle: a `ShakeScreen` in a troop page starts it.
ba_t_shake:
    phb
    phk
    plb
    jsr shake_tick
    plb
    rtl

; And the two for the shop and the equipment, which also live outside: the
; inventory item list and building it. `ti_sell_list` and `eq_from_list` call
; them.
ba_t_list:
    phb
    phk
    plb
    jsr item_from_list
    plb
    rtl
ba_t_build:
    phb
    phk
    plb
    jsr items_build_list
    plb
    rtl

; `run_code` for whoever lives outside bank 0 and has already set up the
; context: `equipment_commons`, in equipment_from_events.s.
run_code_long:
    jsr run_code
    rtl

; A stretch of the troop page that the battle has half run: until it asks for
; a message or finishes. It is `Game_Interpreter_Battle`, and **it is the same
; interpreter as the maps'**, `run_code`: what changes is where the
; context comes from.
;
; The map's is saved on the stack and restored at the end, as in
; `parallel_tick`, and it is not a precaution: a battle is opened from
; **inside** the interpreter —`op_battle`— and on return it keeps reading the
; map's page with the `code_ptr` and the Y it had. The troop's lives in far RAM
; between one stretch and the next, because a message holds it up for several
; frames.
;
; `pair_ev` at `PAIR_BATTLE` is what tells `op_message` that the message belongs
; to the battle. The opcodes that run here are only those in
; `TROPA_COMANDOS`, in events.py: no other one knows there is no map.
ba_t_page:
    phb
    phk
    plb
    rep #$20
.a16
    lda ev_cur
    pha
    lda code_ptr
    pha
    lda f:BAT_LENGTH + BA_PAGE_CUR
    sta ev_cur
    lda f:BAT_LENGTH + BA_PAGE_CODE
    sta code_ptr
    sep #$20
.a8
    lda code_ptr + 2
    pha
    lda ev_active
    pha
    lda pair_ev
    pha
    lda #^troop_code
    sta code_ptr + 2
    lda #PAIR_BATTLE
    sta pair_ev
    lda #1
    sta ev_active
    jsr run_code
    lda ev_active
    sta f:BAT_LENGTH + BA_PAGE_ACT
    rep #$20
.a16
    lda ev_cur
    sta f:BAT_LENGTH + BA_PAGE_CUR
    sep #$20
.a8
    pla
    sta pair_ev
    pla
    sta ev_active
    pla
    sta code_ptr + 2
    rep #$20
.a16
    pla
    sta code_ptr
    pla
    sta ev_cur
    sep #$20
.a8
    plb
    rtl

; Audio package A —the battle's on entering, the map's on leaving—, with the
; music silenced first.
;
; Silencing first is not a detail: `package_load` leaves **in place** the
; samples of the song it says is playing, and those are exactly the ones that
; have to be evicted to make room for the new package. It is the same thing
; `song_ensure` does before rebuilding.
;
; The index comes in **X and 16 bits wide**, not in A: the battle package goes
; after the maps' ones, so with all 328 of the whole game it does not fit in a
; byte —and neither does `map_current`, which is what is passed on leaving—.
;
; With `BA_PACKAGE` at $FFFF —a ROM with no battles— there is nothing to load;
; it cannot happen, because this is reached from `op_battle`, but the opcode
; exists in every ROM's bytecode.
.proc battle_audio_load
.a8
.i16
    cpx #$FFFF
    beq ready
    phx
    lda #$FF
    jsr battle_bgm              ; silence, so nothing stays pinned
    plx
    rep #$20
.a16
    txa
    sta f:PKG_MAP
    sep #$20
.a8
    jsr package_load_done
ready:
    rts
.endproc

; The battle song: A is the index, or $FF to leave it silent. It is called by
; `op_battle` —on entering and on leaving— and by the battle on winning,
; through the bridge above.
;
; Silencing is not `FadeOutBGM`: it is the same thing `song_ensure` does
; before rebuilding the package, that is, releasing all eight voices and
; setting `music_off`. A map with no music is normal in this game —the
; first ones have none and a `PlayBGM` turns it on—, so coming back from a
; battle to a silent map has to really silence it and not leave the battle
; song playing.
.proc battle_bgm
.a8
.i16
    cmp #$FF
    beq mute
    jmp music_start
mute:
    php
    sei
    lda #1
    sta music_off
    lda #$FF
    ldx #SE_KOF
    jsr dsp_pair                ; all eight voices release
    plp
    rts
.endproc
