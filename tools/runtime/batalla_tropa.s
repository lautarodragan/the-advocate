.segment "FAR"

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

; The pages of this battle's troop, from `BA_TROOP_K`. A troop the cartridge
; does not carry has none.
.proc ba_page_build
.a8
.i16
    stz BA_PAGE_N
    rep #$20
.a16
    stz BA_PAGE_WAIT
    stz BA_TURN                ; the `turns` of `Game_Party`, which the
                                ; battle sets to zero when it starts
    sep #$20
.a8
    lda BA_TROOP_K
    cmp #$FF
    beq ready
    jsr ba_ax
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
otra:
    stz BA_PAGE_DONE, x
    inx
    cpx #TROOP_PAGE_MAX
    bne otra
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
alguien:
    lda BA_PAGE_I
    cmp BA_NACT
    bcs no                      ; nobody in the party standing
    jsr ba_alive
    bne hay_grupo
    inc BA_PAGE_I
    bra alguien
hay_grupo:
    lda #0
    sta BA_PAGE_I
otra:
    lda BA_PAGE_I
    cmp BA_PAGE_N
    bcs no
    jsr ba_ax
    lda BA_PAGE_DONE, x
    bne siguiente
    jsr ba_page_met
    bne esta
siguiente:
    inc BA_PAGE_I
    bra otra
esta:
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
; exist in this game—. Leaves in `BA_PAGE_G` its place in the `tpag_*` tables
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
    sta BA_PAGE_FL               ; the triggers, which survive the `jsr`s
    and #TPAGE_SWITCH_A
    beq sin_a
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_sw_a, x
    jsr ba_page_switch
.a8
    bne sin_a
    jmp no
sin_a:
    lda BA_PAGE_FL
    and #TPAGE_SWITCH_B
    beq sin_b
    rep #$20
.a16
    lda BA_PAGE_G
    asl a
    tax
    lda f:tpage_sw_b, x
    jsr ba_page_switch
.a8
    bne sin_b
    jmp no
sin_b:
    lda BA_PAGE_FL
    and #TPAGE_VARIABLE
    beq sin_var
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
    bvc sin_desborde
    eor #$8000                  ; with overflow, the sign is the opposite
sin_desborde:
    sep #$20                    ; `sep` does not touch N
.a8
    bpl sin_var
    jmp no
sin_var:
    lda BA_PAGE_FL
    and #TPAGE_WITH_HEADER
    bne con_cabecera
    jmp si
con_cabecera:
    jsr ba_page_header
    lda BA_PAGE_FL
    and #TPAGE_TURN
    beq sin_turno
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
    bcc no_turno                ; it has not reached the base yet
    sta temp
    lda BA_COND + BA_COND_MULT
    bne con_multiplo
    lda temp
    bne no_turno
    bra turno_si
con_multiplo:
    sta temp + 2
    jsr ba_div                  ; the remainder, in `comp_and`
    lda comp_and
    bne no_turno
turno_si:
    sep #$20
.a8
    bra sin_turno
no_turno:
    jmp no
sin_turno:
    lda BA_PAGE_FL
    and #TPAGE_ENEMY
    beq sin_enemigo
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
sin_enemigo:
    lda BA_PAGE_FL
    and #TPAGE_ACTOR
    beq si
    ; An actor's HP, by its number in the LDB. **Only if it is in the
    ; party**: `Game_Actors::GetActor` answers for anyone, but the HP of one
    ; who is not fighting live in `FAR_HP` without its maximum at hand, and
    ; the game's two pages that check this are Talan's in the Lazer Teeth
    ; battle, where he is. See `batalla.PaginaDeTropa`, which does the same.
    lda BA_COND + BA_COND_AMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_AMAX
    sta BA_PCT_MAX
    lda #0
    sta BA_T0 + 1               ; the party slot being checked
busca_actor:
    lda BA_T0 + 1
    cmp BA_NACT
    bcs no
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq otro_actor
    lda BA_ONE + BA_NUMBER, x
    cmp BA_COND + BA_COND_ACT
    beq actor_hallado
otro_actor:
    inc BA_T0 + 1
    bra busca_actor
actor_hallado:
    jsr ba_page_hp
    beq no
si:
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
; Clobbers A, X and Y. See `eventos.cabecera_de_tropa`.
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
otro:
    lda a:$0000, y
    sta f:BAT_LENGTH + BA_COND, x
    iny
    inx
    cpx #TPAGE_HEADER
    bne otro
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
; bitmap the map looks at, `switches`, in low RAM, which with the data bank at
; $7E is in its usual place. Clobbers X and Y.
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
    and switches, y
    rts
.endproc

; One stretch of the running page, and what follows: if it asked for a
; message, to the screen; if it finished, the next one; and if none is left,
; the battle carries on where it was —`BA_PAGE_TICK`—.
.proc ba_page_step
.a8
.i16
    ; A wait in the page —that of a `ShakeScreen` that waits, which the
    ; converter emits as OP_DELAY— is counted here, one frame per tick, which
    ; is what `events_tick` does with the map's.
    rep #$20
.a16
    lda BA_PAGE_WAIT
    beq sin_espera
    dec a
    sta BA_PAGE_WAIT
    sep #$20
.a8
    rts
sin_espera:
    sep #$20
otro_tramo:
.a8
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
    lda BA_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne a_la_pantalla
    lda BA_PAGE_ACT
    bne a_la_pantalla           ; it did not finish and asked for nothing:
                                ; that does not happen with the commands in
                                ; `TROPA_COMANDOS`, but if it did, the next
                                ; frame carries on
    jsr ba_page_test
    bne otro_tramo              ; the next one, in this same frame
    lda BA_PAGE_TICK
    bne a_las_ordenes
    jmp ba_execute
a_las_ordenes:
    lda #BA_M_COMMAND
    sta BA_MODE
a_la_pantalla:
    jmp ba_compose
.endproc

; The page's message, in the party's lines: see `BA_PAG_MSG_FILA0` in
; pantallas.py. It reads it from `messages_troop` in the usual format —the
; header with the lines and each line with its length, one byte per letter
; with the ASCII minus 32— and writes it with the screen's glyphs, cut at
; `BA_PAGE_MSG_WIDTH`. The block fits in one bank —the converter guarantees
; it—, so the pointer is advanced with Y and the bank stays fixed.
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
    sta BA_PAGE_I                ; the lines left
    ldy #1
renglon:
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
    stz BA_T2                   ; and the ones already written
letra:
    lda BA_T0
    beq fin_renglon
    dec BA_T0
    lda BA_T2
    cmp #BA_PAGE_MSG_WIDTH
    bcs no_entra                ; consumed and not drawn
    inc BA_T2
    lda [msg_ptr], y
    clc
    adc #ITEM_FIRST_CHAR
    phy
    jsl f:ba_t_glyph
    ply
no_entra:
    iny
    bra letra
fin_renglon:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_ROW_BYTES
    sta BA_T1
    sep #$20
.a8
    dec BA_PAGE_I
    bra renglon
ready:
    rts
.endproc
