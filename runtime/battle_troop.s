.segment "FAR2"

; --- the troop's event pages --------------------------------------------------
;
; `Game_Interpreter_Battle`: each troop brings its pages, and one runs when its
; trigger is met. It is what makes the characters' battle systems work
; —Detect Aura turns on switch 134 and the troop page that watches it says
; what color the aura is—. The code is the maps' code and runs in the same
; interpreter, through the `ba_t_page` bridge; what is here decides **when**.
;
; The rule comes from easyrpg and not from memory: `ScheduleNextPage` tries the
; pages in order and starts the first one that is met and **has not run this
; turn**; when it finishes, it tries again, until none is left. The "this
; turn" part is cleared by `NextTurn`, which is when the party finished giving
; its commands. And there are three moments: before asking for the commands,
; before each action and after the last one —see the callers of
; `ba_page_test`—.

; Nonzero once a troop page ran `TerminateBattle` or `ForceFlee`:
; `op_battle_abort` sets it to 1 and `op_battle_flee` to `BA_ABORT_FLEE`, and
; `ba_page_step` ends the battle, aborted or escaped. `battle_run` clears it
; when the battle starts.
.pushseg
.segment "FARBSS"
ba_abort: .res 1
.popseg
BA_ABORT_FLEE = 2

.assert BA_PAGE_DONE + TROOP_PAGE_MAX <= FAR_PAGE + $200, error, "BA_PAGE_DONE goes past the troop pages' range of far RAM"

; The pages of this battle's troop, from `BA_TROOP_K`. A troop the cartridge
; does not carry has none.
.proc ba_page_build
.a8
.i16
    stz BA_PAGE_N
    rep #$20
.a16
    stz BA_PAGE_WAIT
    stz BA_TURN                 ; the `turns` of `Game_Party`, which the
                                ; battle sets to zero when it starts
    sep #$20
.a8
    lda BA_TROOP_K + 1          ; a word: its high byte alone says $FFFF
    cmp #$FF
    beq ready
    rep #$20
.a16
    lda BA_TROOP_K
    tax
    sep #$20
.a8
    lda f:troop_page_n, x
    sta BA_PAGE_N
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:troop_page_init, x
    sta BA_PAGE_INIT
    sep #$20
.a8
    jsr ba_page_turn
ready:
    rts
.endproc

; `ResetPagesExecuted`: none has run yet this turn.
.proc ba_page_turn
.a8
.i16
    ldx #0
other:
    stz BA_PAGE_DONE, x
    inx
    cpx #TROOP_PAGE_MAX
    bne other
    rts
.endproc

; If there is a page to run, leaves it ready —its code, the cursor at zero,
; marked as run— with the battle in `BA_M_PAGE`, and returns with A8 at 1.
; If not, at 0. **Z matches A**: it comes from an explicit `lda`.
;
; First `CheckBattleEndConditions`: with one whole side down the battle ends
; and none runs. Clobbers `BA_S0`, `BA_T*`, A, X and Y.
.proc ba_page_test
.a8
.i16
    lda BA_PAGE_N
    beq no
    jsr ba_enemy_alive
    cmp #$FF
    beq no
    lda #0
    sta BA_PAGE_I
anyone:
    lda BA_PAGE_I
    cmp BA_NACTORS
    bcs no                      ; nobody in the party standing
    jsr ba_alive
    bne has_party
    inc BA_PAGE_I
    bra anyone
has_party:
    lda #0
    sta BA_PAGE_I
other:
    lda BA_PAGE_I
    cmp BA_PAGE_N
    bcs no
    jsr ba_ax
    lda BA_PAGE_DONE, x
    bne next
    jsr ba_page_met
    bne is
next:
    inc BA_PAGE_I
    bra other
is:
    lda BA_PAGE_I
    jsr ba_ax
    lda #1
    sta BA_PAGE_DONE, x
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_code, x
    sta BA_PAGE_CODE
    stz BA_PAGE_CUR
    lda #$FFFF
    sta BA_PAGE_MSG
    sep #$20
.a8
    lda #1
    sta BA_PAGE_ACT
    lda #BA_M_PAGE
    sta BA_MODE
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether the troop's page `BA_PAGE_I` is met: `AreConditionsMet`, with the six
; triggers the ROM knows how to check —RM2k's; the three from 2003 do not
; exist in this game—. Leaves in `BA_PAGE_G` its place in the `tpage_*` tables
; and returns with Z=0 if it is met. Clobbers `BA_T*`, `temp`, A, X and Y.
.proc ba_page_met
.a8
.i16
    rep #$20
.a16
    lda BA_PAGE_I
    and #$00FF
    clc
    adc BA_PAGE_INIT
    sta BA_PAGE_G
    tax
    sep #$20
.a8
    lda f:tpage_flags, x
    sta BA_PAGE_FL              ; the triggers, which survive the `jsr`s
    and #TPAGE_SWITCH_A
    beq no_a
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_sw_a, x
    jsr ba_page_switch
.a8
    bne no_a
    jmp no
no_a:
    lda BA_PAGE_FL
    and #TPAGE_SWITCH_B
    beq no_b
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_sw_b, x
    jsr ba_page_switch
.a8
    bne no_b
    jmp no
no_b:
    lda BA_PAGE_FL
    and #TPAGE_VARIABLE
    beq no_var
    ; The variable, signed `>=`: `Get(variable_id) >= variable_value`.
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_value, x
    sta BA_T0
    lda f:tpage_var, x
    asl a
    tax
    lda FAR_VARIABLES, x
    sec
    sbc BA_T0
    bvc no_overflow
    eor #$8000                  ; with overflow, the sign is the opposite
no_overflow:
    sep #$20                    ; `sep` does not touch N
.a8
    bpl no_var
    jmp no
no_var:
    lda BA_PAGE_FL
    and #TPAGE_WITH_HEADER
    bne with_header
    jmp if
with_header:
    jsr ba_page_header
    lda BA_PAGE_FL
    and #TPAGE_TURN
    beq no_turn
    ; The turn: `Game_Battle::CheckTurns(turn, turn_b, turn_a)`, with the base
    ; and the multiple **in that order**, which is the opposite of what
    ; liblcf's names suggest. Without a multiple, exactly at the base; with
    ; one, at the base and every so many. The converter leaves them in the
    ; header already in place.
    rep #$20
.a16
    lda BA_TURN
    sec
    sbc BA_COND + BA_COND_BASE
    bcc not_turn                ; it has not reached the base yet
    sta temp
    lda BA_COND + BA_COND_MULT
    bne with_multiple
    lda temp
    bne not_turn
    bra its_turn
with_multiple:
    sta temp + 2
    jsr ba_div                  ; the remainder, in `comp_and`
    lda comp_and
    bne not_turn
its_turn:
    sep #$20
.a8
    bra no_turn
not_turn:
    jmp no
no_turn:
    lda BA_PAGE_FL
    and #TPAGE_ENEMY
    beq no_enemy
    ; An enemy's HP, by its place in the troop. `GetEnemy` does not check
    ; whether it is hidden or dead: only whether the place exists.
    lda BA_COND + BA_COND_EMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_EMAX
    sta BA_PCT_MAX
    lda BA_COND + BA_COND_ENEMY
    cmp BA_KID
    bcs no
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    jsr ba_page_hp
    beq no
no_enemy:
    lda BA_PAGE_FL
    and #TPAGE_ACTOR
    beq if
    ; An actor's HP, by its number in the LDB. **Only if it is in the
    ; party**: `Game_Actors::GetActor` answers for anyone, but the HP of one
    ; who is not fighting live in `FAR_HP` without its maximum at hand, and
    ; the game's two pages that check this are Talan's in the Lazer Teeth
    ; battle, where he is. `rm2k-snes-battle`'s `TroopPage` does the same.
    lda BA_COND + BA_COND_AMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_AMAX
    sta BA_PCT_MAX
    lda #0
    sta BA_T0 + 1               ; the party slot being checked
seek_actor:
    lda BA_T0 + 1
    cmp BA_NACTORS
    bcs no
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq other_actor
    lda BA_ONE + BA_NUMBER, x
    cmp BA_COND + BA_COND_ACT
    beq actor_found
other_actor:
    inc BA_T0 + 1
    bra seek_actor
actor_found:
    jsr ba_page_hp
    beq no
if:
    lda #1
    rts
no:
.a8
    sep #$20
    lda #0
    rts
.endproc

; The header of page `BA_PAGE_G` —the turn and HP numbers, which the converter
; puts in front of its code, `TPAGE_HEADER` bytes before where `tpage_code`
; points— into `BA_COND`. It is read with the data bank at that of
; `troop_code`, which fits whole in one bank, and written with `f:`.
; Clobbers A, X and Y. See `Trigger::header` in the event compiler.
.proc ba_page_header
.a8
.i16
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_code, x
    sec
    sbc #TPAGE_HEADER
    tay
    sep #$20
.a8
    phb
    lda #^troop_code
    pha
    plb
    ldx #0
other:
    lda a:$0000, y
    sta f:BAT_LENGTH + BA_COND, x
    iny
    inx
    cpx #TPAGE_HEADER
    bne other
    plb
    rts
.endproc

; Whether the HP of the combatant at offset X —the one from `ba_x`— are
; between `BA_PCT_MIN` and `BA_PCT_MAX` percent, counted the way
; `AreConditionsMet` counts them: `100 * hp / hp_max`, integer. Without
; dividing: the quotient being at least `min` is `min * hp_max <= 100 * hp`,
; and it not going past `max` is `100 * hp < (max + 1) * hp_max`. The products
; go past sixteen bits —a hundred times a boss's HP— and so they go in
; twenty-four. Returns with A8 and Z=0 if it is. Clobbers `BA_T1`, `BA_T2`
; and `temp`.
.proc ba_page_hp
.a8
.i16
    stx BA_T1
    lda #100
    sta BA_T2
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    jsr ba_mul24
    lda BA_P24
    sta BA_P_HP
    lda BA_P24 + 1
    sta BA_P_HP + 1
    sep #$20
.a8
    lda BA_PCT_MIN
    sta BA_T2
    rep #$20
.a16
    ldx BA_T1
    lda BA_ONE + BA_HPMAX, x
    jsr ba_mul24
    lda BA_P_HP
    sec
    sbc BA_P24
    sep #$20                    ; `sep` does not touch C
.a8
    lda BA_P_HP + 2
    sbc BA_P24 + 2
    bcc no                      ; 100 hp < min * hp_max
    lda BA_PCT_MAX
    inc a
    sta BA_T2
    rep #$20
.a16
    ldx BA_T1
    lda BA_ONE + BA_HPMAX, x
    jsr ba_mul24
    lda BA_P_HP
    sec
    sbc BA_P24
    sep #$20
.a8
    lda BA_P_HP + 2
    sbc BA_P24 + 2
    bcs no                      ; 100 hp >= (max + 1) * hp_max
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 times the byte in `BA_T2`, in twenty-four bits, in `BA_P24`: `ba_mul`
; without losing what goes past sixteen. Clobbers `temp`.
.proc ba_mul24
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB                ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta BA_P24
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB
    stz BA_P24 + 2              ; meanwhile
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL                ; the high byte times the multiplier, which
    clc                         ; weighs 256: it is added shifted one byte
    adc BA_P24 + 1
    sta BA_P24 + 1
    rts
.endproc

; `ShowHiddenMonster`: the enemy at place A8 of the troop stops being hidden
; and starts counting for everything —target, victory, actions—, which is what
; `SetHidden(false)` does. One that was not hidden does not change: the
; command revives nobody. It is drawn by `scene_tick`, which puts in the scene
; everyone who is alive and not shown. It is called by `op_show_enemy` from
; the interpreter, with the data bank at 0: the battle's is set here.
.proc ba_show_hidden
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp BA_KID
    bcs ready
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    bit #BAF_HIDDEN
    beq ready
    and #<~BAF_HIDDEN
    ora #BAF_HAS
    sta BA_ONE + BA_FLAGS, x
ready:
    plb
    rtl
.endproc

; A16 the switch number; returns with A8 and Z=0 if it is on. It is the same
; table the map looks at, `switches`, in far RAM. Clobbers X and Y.
.proc ba_page_switch
.a16
.i16
    pha
    lsr a
    lsr a
    lsr a
    tay                         ; which byte
    pla
    and #$0007
    tax                         ; and which bit
    sep #$20
.a8
    lda f:mask, x
    tyx                         ; the table is far, and a long index is X
    and f:switches, x
    rts
.endproc

; One stretch of the running page, and what follows: if it asked for a
; message, to the screen; if it finished, the next one; and if none is left,
; the battle carries on where it was —`BA_PAGE_TICK`—.
.proc ba_page_step
.a8
.i16
    ; A wait in the page —a `Wait`, or that of a `ShakeScreen`, a
    ; `FlashScreen` or a `TintScreen` that waits, which the converter emits as
    ; OP_DELAY— is counted here, one frame per tick, which is what
    ; `events_tick` does with the map's.
    rep #$20
.a16
    lda BA_PAGE_WAIT
    beq no_wait
    dec a
    sta BA_PAGE_WAIT
    sep #$20
.a8
    rts
no_wait:
    sep #$20
other_stretch:
.a8
    ; The party's HP and SP out to the saved game's, where the map's opcodes
    ; —`ChangeHP`, `ControlVars` with an actor's HP, `ChangePartyMembers`—
    ; read and write them, and back after the stretch. See `ba_sync_out`.
    jsr ba_sync_out
    rep #$20
.a16
    ; `ev_waiting` belongs to the map's interpreter, which was left halfway
    ; through inside `op_battle`: the page's is kept separately.
    lda ev_waiting
    pha
    stz ev_waiting
    sep #$20
.a8
    jsl f:ba_t_page
    rep #$20
.a16
    lda ev_waiting
    sta BA_PAGE_WAIT
    pla
    sta ev_waiting
    sep #$20
.a8
    jsr ba_sync_in
    ; A `TerminateBattle` ended the page, and with it the battle: no other
    ; page runs, nothing is composed —the battle leaves from the screen it
    ; was showing— and the loop closes it on its next frame. See
    ; `op_battle_abort`.
    lda f:ba_abort
    beq not_aborted
    cmp #BA_ABORT_FLEE
    beq fled
    lda #BA_ABORT_R
    sta BA_RESULT
    lda #BA_M_ABORT
    sta BA_MODE
    rts
fled:
    ; A `ForceFlee` ended it instead: the party escaped, with the message
    ; and the sound of an escape that succeeded —`o_flees` in battle_run.s,
    ; without `ba_flee`'s dice—. See `op_battle_flee`.
    lda #BA_ESCAPE_R
    sta BA_RESULT
    lda #BA_MSG_FLED
    sta BA_MTYPE
    jsr ba_show
    rep #$20
.a16
    lda #BA_SE_FLEE
    jsl f:ba_t_sound
    sep #$20
.a8
    lda #BA_M_END
    sta BA_MODE
    rts
not_aborted:
    rep #$20
.a16
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne to_screen
    lda BA_PAGE_ACT
    bne to_screen               ; it did not finish and asked for nothing:
                                ; that does not happen with the commands in
                                ; `TROOP_COMMANDS`, but if it did, the next
                                ; frame carries on
    jsr ba_page_test
    bne other_stretch           ; the next one, in this same frame
    lda BA_PAGE_TICK
    bne to_commands
    jmp ba_execute
to_commands:
    lda #BA_M_COMMAND
    sta BA_MODE
to_screen:
    jmp ba_compose
.endproc

; The page's message, in the message window: see `BA_PAGE_MSG_ROW0` in
; `rm2k-snes-battle`'s `screen.rs`. It reads it from `messages_troop` in the
; usual format —the header with the lines and each line with its length, one
; byte per letter with the ASCII minus 32: unlike `messages`, this block is
; written without pairs, so this does not look up `message_pairs`— and
; writes it in the screen's text, cut where it passes `BA_PAGE_MSG_WIDTH`
; cells —in pixels, with the font's advances: until 2026-10-03 it was that
; many letters—. The block fits in one bank —the converter guarantees it—,
; so the pointer is advanced with Y and the bank stays fixed.
;
; A variable's value, `\V[n]`, and a name written when the box opens,
; `\N[0]` or a renamed actor's, come as the map's do —`MESSAGE_VARIABLE` and
; its slot, `MESSAGE_NAME` and its actor— and are written here, letter by
; letter, as `msg_letter` does on the map: see `variable` and `name`. Until
; 2026-10-15 their bytes were drawn as two letters.
.proc ba_page_message
.a8
.i16
    rep #$20
.a16
    lda BA_PAGE_MSG
    clc
    adc #.loword(messages_troop)
    sta msg_ptr
    lda #BA_PAGE_MSG_POS0
    sta BA_T1
    sep #$20
.a8
    lda #^messages_troop
    sta msg_ptr + 2
    stz temp + 1                ; blank
    lda [msg_ptr]
    and #HEADER_LINES
    sta BA_PAGE_I               ; the lines left
    ldy #1
line:
    lda BA_PAGE_I
    beq ready
    rep #$20
.a16
    lda #BA_PAGE_MSG_DX
    jsr ba_go
    sep #$20
.a8
    lda [msg_ptr], y            ; the length
    iny
    sta BA_T0                   ; the letters it has left
    rep #$20
.a16
    stz BA_T2                   ; and the pixels already written
    sep #$20
.a8
letter:
    lda BA_T0
    beq end_line
    dec BA_T0
    lda [msg_ptr], y
    iny
    cmp #MESSAGE_VARIABLE
    beq variable
    cmp #MESSAGE_NAME
    beq name
    jsr put
    bra letter
end_line:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_ROW_BYTES
    sta BA_T1
    sep #$20
.a8
    dec BA_PAGE_I
    bra line
ready:
    rts

    ; The value of the variable whose slot follows, in decimal, with its
    ; sign: the digits go into `MSG_DIGITS` from the ones up, and are put
    ; from the top down. The map's composer is not composing in battle.
variable:
    lda [msg_ptr], y            ; the slot
    iny
    phy
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    ldx #0                      ; how many characters so far
    pha                         ; the value, for its sign
    cmp #0                      ; the `ldx` left its own flags
    bpl digit
    eor #$FFFF
    inc a
digit:
    sta f:WRDIVL
    sep #$20
.a8
    lda #10
    sta f:WRDIVB                ; sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda f:RDMPYL                ; the remainder
    clc
    adc #'0' - ' '
    sta f:MSG_DIGITS, x
    inx
    rep #$20
.a16
    lda f:RDDIVL                ; the quotient
    bne digit
    pla                         ; the value: N is its sign, on purpose
    sep #$20
.a8
    bpl put_digits
    lda #'-' - ' '
    sta f:MSG_DIGITS, x
    inx
put_digits:
    dex
    phx
    lda f:MSG_DIGITS, x
    jsr put
    plx
    cpx #0
    bne put_digits
    ply
    jmp letter

    ; The name of the actor that follows, 0 the leader, from its text:
    ; `msg_ptr` points at it while it is put, and comes back to the box.
name:
    lda [msg_ptr], y            ; the actor
    iny
    phy
    rep #$20
.a16
    and #$00FF
    bne by_number
    lda party_n
    and #$00FF
    beq no_name                 ; no one leads: nothing
    lda party
    and #$00FF
by_number:
    asl a
    tax
    jsl f:actor_name_txt
    cmp #$FFFF
    beq no_name
    tax
    lda msg_ptr
    pha
    sep #$20
.a8
    lda msg_ptr + 2
    pha
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    pha                         ; the letters left, on the stack
    ldy #0
name_letter:
    lda 1, s
    beq name_done
    dec a
    sta 1, s
    lda [msg_ptr], y
    sec
    sbc #' '
    phy
    jsr put
    ply
    iny
    bra name_letter
name_done:
    pla                         ; the count, at zero
    pla
    sta msg_ptr + 2
    rep #$20
.a16
    pla
    sta msg_ptr
no_name:
    sep #$20
.a8
    ply
    jmp letter

    ; A8: a letter, as its index in the font. Written if it fits in the
    ; line; past the edge, consumed and not drawn, and nothing after it.
    ; Keeps Y. Clobbers A and X.
put:
    pha
    rep #$20
.a16
    and #$00FF
    tax
    lda f:font_advance, x
    and #$00FF
    clc
    adc BA_T2
    cmp #(BA_PAGE_MSG_WIDTH * 8 + 1)
    bcc enters
    lda #$7FFF                  ; and nothing after it either
enters:
    sta BA_T2
    sep #$20
.a8
    pla
    bcs no_enters               ; `pla` keeps C
    clc
    adc #ITEM_FIRST_CHAR
    phy
    jsl f:ba_t_glyph
    ply
no_enters:
    rts
.endproc

; --- what a page does to the party ------------------------------------------
;
; In RM2k the battle has no HP of its own: an actor's are those of its
; `Game_Actor`, the same one the map sees, so a `ChangeHP` or a `FullHeal` in
; a troop page, a `ControlVars` that reads Talan's HP or a
; `ChangePartyMembers` do in battle what they do on the map. Here the battle
; keeps them in `BA_ONE` and hands them back to `FAR_HP` and `FAR_SP` when it
; ends. So that those opcodes do not need to know there is a battle, a page's
; stretch runs between these two: the HP and SP go out to the saved game's
; before, and come back after, together with whatever changed in `party`.

; The HP and SP of each actor who is fighting, to `FAR_HP` and `FAR_SP`. It is
; also what the battle does when it closes. Clobbers `BA_T0` to `BA_T2`, A
; and X.
.proc ba_sync_out
.a8
.i16
    stz BA_T0
other:
    lda BA_T0
    cmp #BA_PARTY_MAX
    bcs ready
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq next                    ; nobody, or one a page took out: see below
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    sta BA_T1
    lda BA_ONE + BA_SP, x
    sta BA_T2
    lda BA_ONE + BA_NUMBER, x
    and #$00FF
    asl a
    tax
    lda BA_T1
    sta FAR_HP, x
    lda BA_T2
    sta FAR_SP, x
    sep #$20
.a8
next:
    inc BA_T0
    bra other
ready:
    rts
.endproc

; And back: the HP and SP of whoever is still in `party`, and the party's
; changes.
;
; **One who leaves** keeps its place empty, with `BAF_HIDDEN` and without
; `BAF_HAS`, which is what everything that looks at who is there skips
; —`Exists()`— and what `ba_line` does not draw. Its pending action is lost,
; as with easyrpg's `RemoveCurrentAction` for one who does not exist.
;
; **One who joins** goes to the first place without `BAF_HAS`, from the
; saved game's HP and SP as `ba_build` would have brought it. It has no
; action this turn —`CreateBattleActions` already ran—, and if the place
; had one pending from whoever left it, it is dropped.
;
; RM2k compacts the list instead: the one who leaves takes its line with it
; and the one who joins goes last. Here the places do not move, because
; everything pending —the commands, the order, the targets— points at them.
; With the game's summons, which take Emily out and put the summon in, it
; shows as the summon in Emily's line and not at the bottom. See
; `divergences/` in the book.
;
; And whoever stays takes up what a page changed of its equipment:
; `ba_reparam`.
;
; Clobbers `BA_S0` to `BA_S6`, `BA_T*`, A, X and Y.
.proc ba_sync_in
.a8
.i16
    stz BA_S1
present:
    lda BA_S1
    cmp #BA_PARTY_MAX
    bcs to_added
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq next_present
    lda BA_ONE + BA_NUMBER, x
    sta BA_S0
    jsr ba_in_party
    bne stays
    lda BA_S1
    jsr ba_x
    lda #(BAF_ACTOR | BAF_HIDDEN)
    sta BA_ONE + BA_FLAGS, x
    bra next_present
stays:
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tay
    lda FAR_HP, y
    sta BA_ONE + BA_HP, x
    lda FAR_SP, y
    sta BA_ONE + BA_SP, x
    sep #$20
.a8
    jsr ba_reparam
next_present:
    inc BA_S1
    bra present
to_added:
    stz BA_SYNC_I
member:
    rep #$20
.a16
    lda BA_SYNC_I
    and #$00FF
    cmp party_n
    sep #$20
.a8
    bcs ready
    rep #$20
.a16
    lda BA_SYNC_I
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    sta BA_S0
    jsr ba_fighting
    bne next_member
    stz BA_S1
free:
    lda BA_S1
    cmp #BA_PARTY_MAX
    bcs next_member             ; cannot happen: the party is four at most
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq found
    inc BA_S1
    bra free
found:
    jsr ba_actor_setup
    lda BA_S1
    inc a
    cmp BA_NACTORS
    bcc counted
    sta BA_NACTORS
counted:
    lda BA_S1
    jsr ba_drop_actions
next_member:
    inc BA_SYNC_I
    bra member
ready:
    rts
.endproc

; The four parameters of actor `BA_S0`, in party place `BA_S1`, from its
; level and its equipment again, with the modifiers the battle gave it kept:
; in RM2k `GetAtk` and its siblings add the equipment every time they are
; asked, so a `ChangeEquipment` in a troop page counts from the next action.
; And what attacking costs it and its critical hit, which the weapon says.
; The same arithmetic as `ba_build` and `ba_mod`. Clobbers `BA_S2`, `BA_T*`,
; A, X and Y.
.proc ba_reparam
.a8
.i16
    stz BA_S2                   ; which one: 0 attack, 1 defense, 2 spirit,
                                ; 3 agility
other:
    lda BA_S2
    jsr ba_param                ; `BA_T2`: its base
    lda BA_S1
    jsr ba_x
    stx BA_T0                   ; the place's offset
    lda BA_S2
    asl a
    jsr ba_ax
    rep #$20
.a16
    lda f:base, x
    clc
    adc BA_T0
    tay
    lda BA_T2
    sta BA_ONE, y
    lda f:modifier, x
    clc
    adc BA_T0
    tay
    lda BA_ONE, y
    clc
    adc BA_T2                   ; base + modifier, in [1, BA_PARAM_MAX]
    bmi to_one
    cmp #1
    bcs not_zero
to_one:
    lda #1
    bra fits
not_zero:
    cmp #(BA_PARAM_MAX + 1)
    bcc fits
    lda #BA_PARAM_MAX
fits:
    sta BA_T1
    lda f:effective, x
    clc
    adc BA_T0
    tay
    lda BA_T1
    sta BA_ONE, y
    sep #$20
.a8
    inc BA_S2
    lda BA_S2
    cmp #4
    bcc other
    jsr ba_weapon_sp
    pha
    lda BA_S1
    jsr ba_ax
    pla
    sta f:BA_WEAPON_SP, x
    jsr ba_crit_of              ; the weapon's bonus changed with it
    pha
    lda BA_S1
    jsr ba_x
    pla
    sta BA_ONE + BA_CRIT, x
    rts
base:
    .word BA_BATK, BA_BDEF, BA_BSPI, BA_BAGI
modifier:
    .word BA_MATK, BA_MDEF, BA_MSPI, BA_MAGI
effective:
    .word BA_ATK, BA_DEF, BA_SPI, BA_AGI
.endproc

; Z=0 if actor A8 is in `party`, which is the list the map's opcodes change.
; With the data bank at $7E it is in its usual place: it lives in low RAM.
; Clobbers `BA_T2` and X.
.proc ba_in_party
.a8
.i16
    sta BA_T2
    ldx #0
other:
    cpx party_n
    bcs no
    lda party, x
    cmp BA_T2
    beq yes
    inx
    bra other
yes:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Z=0 if actor `BA_S0` is fighting: in a place of the party with `BAF_HAS`.
; Clobbers `BA_T2` and X.
.proc ba_fighting
.a8
.i16
    stz BA_T2
other:
    lda BA_T2
    cmp #BA_PARTY_MAX
    bcs no
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq next
    lda BA_ONE + BA_NUMBER, x
    cmp BA_S0
    beq yes
next:
    inc BA_T2
    bra other
yes:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; The actions still pending in this turn's order —from `BA_I` on— of
; combatant A8, out of the list. Clobbers `BA_T2`, A, X and Y.
.proc ba_drop_actions
.a8
.i16
    sta BA_T2
    rep #$20
.a16
    lda BA_I
    and #$00FF
    tax                         ; the one read
    tay                         ; and the one written
    sep #$20
.a8
other:
    txa
    cmp BA_NACTIONS
    bcs ready
    lda BA_EXEC, x
    cmp BA_T2
    beq drop
    sta BA_EXEC, y
    iny
drop:
    inx
    bra other
ready:
    tya
    sta BA_NACTIONS
    rts
.endproc

; `ChangeMonsterHP` and `ChangeMonsterMP`, OP_ENEMY: `Game_Interpreter_Battle`'s
; two, on the enemy at a place of the troop. Called by `op_enemy` from the
; interpreter, with the data bank at 0 and Y on the operands: it sets the
; battle's and leaves Y after them.
;
; The HP one is `ChangeHp`: a dead one does not change, it does not go past
; the maximum, and a loss that is not lethal leaves it at 1. One that dies
; sounds like one killed by a hit —`SFX_EnemyKill`, the `BA_SE_DEATH` of
; `ba_hit_sound`— and `scene_tick` erases it as it erases that one. A hidden
; one is changed all the same: `GetEnemy` does not ask. The SP one is `SetSp`,
; between zero and the maximum.
;
; With `ENEMY_BY_VARIABLE` the amount is a variable's slot, and its value,
; signed, is what is added —turned around with `ENEMY_SUBTRACTS`—: The Book
; of Three's Last Stand. A sum past $7FFF overflows as signed, and that is a
; gain that goes to the maximum, not a loss.
ENEMY_SP          = $01         ; what: the SP and not the HP
ENEMY_BY_VARIABLE = $20         ; the amount is a variable's slot
ENEMY_SUBTRACTS   = $40         ; and its value is taken away
ENEMY_LETHAL      = $80         ; and on top, that a loss of HP can kill
.proc ba_enemy_change
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda [code_ptr], y           ; the place
    iny
    sta BA_T0
    lda [code_ptr], y           ; what
    iny
    sta BA_T0 + 1
    rep #$20
.a16
    lda [code_ptr], y           ; and how much, signed
    iny
    iny
    sta BA_T1
    lda BA_T0
    and #(ENEMY_BY_VARIABLE * 256)
    beq amount_ready
    lda BA_T1
    and #VAR_SLOT
    asl a                       ; two bytes per variable
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta BA_T1
    lda BA_T0
    and #(ENEMY_SUBTRACTS * 256)
    beq amount_ready
    lda #0
    sec
    sbc BA_T1
    sta BA_T1
amount_ready:
    sep #$20
.a8
    phy
    lda BA_T0
    cmp BA_KID
    bcs ready
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    lda BA_T0 + 1
    and #ENEMY_SP
    bne sp
    rep #$20
.a16
    lda BA_ONE + BA_HP, x
    beq ready16                 ; dead: `ChangeHp` does nothing to it
    clc
    adc BA_T1
    bvs top                     ; a gain past $7FFF
    bmi down
    beq down
    cmp BA_ONE + BA_HPMAX, x
    bcc put
top:
    lda BA_ONE + BA_HPMAX, x
put:
    sta BA_ONE + BA_HP, x
ready16:
    sep #$20
.a8
ready:
    ply
    plb
    rtl
.a16
down:
    lda BA_T0
    and #(ENEMY_LETHAL * 256)
    bne dies
    lda #1
    bra put
dies:
    stz BA_ONE + BA_HP, x
    lda #BA_SE_DEATH
    jsl f:ba_t_sound
.a8
    bra ready
sp:
    rep #$20
.a16
    lda BA_ONE + BA_SP, x
    clc
    adc BA_T1
    bvs sp_top                  ; a gain past $7FFF
    bpl sp_positive
    lda #0
sp_positive:
    cmp BA_ONE + BA_SPMAX, x
    bcc sp_put
sp_top:
    lda BA_ONE + BA_SPMAX, x
sp_put:
    sta BA_ONE + BA_SP, x
    bra ready16
.endproc
