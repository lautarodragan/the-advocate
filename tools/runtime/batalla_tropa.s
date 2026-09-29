.segment "FAR"

; --- the troop's event pages --------------------------------------------------
;
; `Game_Interpreter_Battle`: each troop brings its pages, and one runs when its
; trigger is met. It is what makes the characters' battle systems work
; —Detect Aura turns on switch 134 and the troop page that watches it says
; what color the aura is—. The code is the maps' code and runs in the same
; interpreter, through the `bt_t_page` bridge; what is here decides **when**.
;
; The rule comes from easyrpg and not from memory: `ScheduleNextPage` tries the
; pages in order and starts the first one that is met and **has not run this
; turn**; when it finishes, it tries again, until none is left. The "this
; turn" part is cleared by `NextTurn`, which is when the party finished giving
; its commands. And there are three moments: before asking for the commands,
; before each action and after the last one —see the callers of
; `bt_page_test`—.

; The pages of this battle's troop, from `BT_TROOP_K`. A troop the cartridge
; does not carry has none.
.proc bt_page_build
.a8
.i16
    stz BT_PAGE_N
    rep #$20
.a16
    stz BT_PAGE_WAIT
    stz BT_TURN                ; the `turns` of `Game_Party`, which the
                                ; battle sets to zero when it starts
    sep #$20
.a8
    lda BT_TROOP_K
    cmp #$FF
    beq ready
    jsr bt_ax
    lda f:tropa_pag_n, x
    sta BT_PAGE_N
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:tropa_pag_ini, x
    sta BT_PAGE_INIT
    sep #$20
.a8
    jsr bt_page_turn
ready:
    rts
.endproc

; `ResetPagesExecuted`: none has run yet this turn.
.proc bt_page_turn
.a8
.i16
    ldx #0
otra:
    stz BT_PAGE_DONE, x
    inx
    cpx #TROPA_PAG_MAX
    bne otra
    rts
.endproc

; If there is a page to run, leaves it ready —its code, the cursor at zero,
; marked as run— with the battle in `BT_M_PAGE`, and returns with A8 at 1.
; If not, at 0. **Z matches A**: it comes from an explicit `lda`.
;
; First `CheckBattleEndConditions`: with one whole side down the battle ends
; and none runs. Clobbers `BT_S0`, `BA_T*`, A, X and Y.
.proc bt_page_test
.a8
.i16
    lda BT_PAGE_N
    beq no
    jsr bt_enemy_alive
    cmp #$FF
    beq no
    lda #0
    sta BT_PAGE_I
alguien:
    lda BT_PAGE_I
    cmp BT_NACT
    bcs no                      ; nobody in the party standing
    jsr bt_alive
    bne hay_grupo
    inc BT_PAGE_I
    bra alguien
hay_grupo:
    lda #0
    sta BT_PAGE_I
otra:
    lda BT_PAGE_I
    cmp BT_PAGE_N
    bcs no
    jsr bt_ax
    lda BT_PAGE_DONE, x
    bne siguiente
    jsr bt_page_met
    bne esta
siguiente:
    inc BT_PAGE_I
    bra otra
esta:
    lda BT_PAGE_I
    jsr bt_ax
    lda #1
    sta BT_PAGE_DONE, x
    rep #$20
.a16
    lda BT_PAGE_G
    asl a
    tax
    lda f:tpag_cod, x
    sta BT_PAGE_CODE
    stz BT_PAGE_CUR
    lda #$FFFF
    sta BT_PAGE_MSG
    sep #$20
.a8
    lda #1
    sta BT_PAGE_ACT
    lda #BT_M_PAGE
    sta BT_MODE
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether the troop's page `BT_PAGE_I` is met: `AreConditionsMet`, with the six
; triggers the ROM knows how to check —RM2k's; the three from 2003 do not
; exist in this game—. Leaves in `BT_PAGE_G` its place in the `tpag_*` tables
; and returns with Z=0 if it is met. Clobbers `BA_T*`, `temp`, A, X and Y.
.proc bt_page_met
.a8
.i16
    rep #$20
.a16
    lda BT_PAGE_I
    and #$00FF
    clc
    adc BT_PAGE_INIT
    sta BT_PAGE_G
    tax
    sep #$20
.a8
    lda f:tpag_flags, x
    sta BT_PAGE_FL               ; the triggers, which survive the `jsr`s
    and #TPAG_SWITCH_A
    beq sin_a
    rep #$20
.a16
    lda BT_PAGE_G
    asl a
    tax
    lda f:tpag_sw_a, x
    jsr bt_page_switch
.a8
    bne sin_a
    jmp no
sin_a:
    lda BT_PAGE_FL
    and #TPAG_SWITCH_B
    beq sin_b
    rep #$20
.a16
    lda BT_PAGE_G
    asl a
    tax
    lda f:tpag_sw_b, x
    jsr bt_page_switch
.a8
    bne sin_b
    jmp no
sin_b:
    lda BT_PAGE_FL
    and #TPAG_VARIABLE
    beq sin_var
    ; The variable, signed `>=`: `Get(variable_id) >= variable_value`.
    rep #$20
.a16
    lda BT_PAGE_G
    asl a
    tax
    lda f:tpag_valor, x
    sta BT_T0
    lda f:tpag_var, x
    asl a
    tax
    lda FAR_VARIABLES, x
    sec
    sbc BT_T0
    bvc sin_desborde
    eor #$8000                  ; with overflow, the sign is the opposite
sin_desborde:
    sep #$20                    ; `sep` does not touch N
.a8
    bpl sin_var
    jmp no
sin_var:
    lda BT_PAGE_FL
    and #TPAG_CON_CABECERA
    bne con_cabecera
    jmp si
con_cabecera:
    jsr bt_page_header
    lda BT_PAGE_FL
    and #TPAG_TURNO
    beq sin_turno
    ; The turn: `Game_Battle::CheckTurns(turn, turn_b, turn_a)`, with the base
    ; and the multiple **in that order**, which is the opposite of what
    ; liblcf's names suggest. Without a multiple, exactly at the base; with
    ; one, at the base and every so many. The converter leaves them in the
    ; header already in place.
    rep #$20
.a16
    lda BT_TURN
    sec
    sbc BT_COND + BT_COND_BASE
    bcc no_turno                ; it has not reached the base yet
    sta temp
    lda BT_COND + BT_COND_MULT
    bne con_multiplo
    lda temp
    bne no_turno
    bra turno_si
con_multiplo:
    sta temp + 2
    jsr bt_div                  ; the remainder, in `comp_and`
    lda comp_and
    bne no_turno
turno_si:
    sep #$20
.a8
    bra sin_turno
no_turno:
    jmp no
sin_turno:
    lda BT_PAGE_FL
    and #TPAG_ENEMIGO
    beq sin_enemigo
    ; An enemy's HP, by its place in the troop. `GetEnemy` does not check
    ; whether it is hidden or dead: only whether the place exists.
    lda BT_COND + BT_COND_EMIN
    sta BT_PCT_MIN
    lda BT_COND + BT_COND_EMAX
    sta BT_PCT_MAX
    lda BT_COND + BT_COND_ENEMY
    cmp BT_KID
    bcs no
    clc
    adc #BT_PARTY_MAX
    jsr bt_x
    jsr bt_page_hp
    beq no
sin_enemigo:
    lda BT_PAGE_FL
    and #TPAG_ACTOR
    beq si
    ; An actor's HP, by its number in the LDB. **Only if it is in the
    ; party**: `Game_Actors::GetActor` answers for anyone, but the HP of one
    ; who is not fighting live in `FAR_HP` without its maximum at hand, and
    ; the game's two pages that check this are Talan's in the Lazer Teeth
    ; battle, where he is. See `batalla.PaginaDeTropa`, which does the same.
    lda BT_COND + BT_COND_AMIN
    sta BT_PCT_MIN
    lda BT_COND + BT_COND_AMAX
    sta BT_PCT_MAX
    lda #0
    sta BT_T0 + 1               ; the party slot being checked
busca_actor:
    lda BT_T0 + 1
    cmp BT_NACT
    bcs no
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HAS
    beq otro_actor
    lda BT_ONE + BT_NUMBER, x
    cmp BT_COND + BT_COND_ACT
    beq actor_hallado
otro_actor:
    inc BT_T0 + 1
    bra busca_actor
actor_hallado:
    jsr bt_page_hp
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

; The header of page `BT_PAGE_G` —the turn and HP numbers, which the converter
; puts in front of its code, `TPAG_CABECERA` bytes before where `tpag_cod`
; points— into `BT_COND`. It is read with the data bank at that of
; `tropa_codigo`, which fits whole in one bank, and written with `f:`.
; Clobbers A, X and Y. See `eventos.cabecera_de_tropa`.
.proc bt_page_header
.a8
.i16
    rep #$20
.a16
    lda BT_PAGE_G
    asl a
    tax
    lda f:tpag_cod, x
    sec
    sbc #TPAG_CABECERA
    tay
    sep #$20
.a8
    phb
    lda #^tropa_codigo
    pha
    plb
    ldx #0
otro:
    lda a:$0000, y
    sta f:BAT_LENGTH + BT_COND, x
    iny
    inx
    cpx #TPAG_CABECERA
    bne otro
    plb
    rts
.endproc

; Whether the HP of the combatant at offset X —the one from `bt_x`— are
; between `BT_PCT_MIN` and `BT_PCT_MAX` percent, counted the way
; `AreConditionsMet` counts them: `100 * hp / hp_max`, integer. Without
; dividing: the quotient being at least `min` is `min * hp_max <= 100 * hp`,
; and it not going past `max` is `100 * hp < (max + 1) * hp_max`. The products
; go past sixteen bits —a hundred times a boss's HP— and so they go in
; twenty-four. Returns with A8 and Z=0 if it is. Clobbers `BT_T1`, `BT_T2`
; and `temp`.
.proc bt_page_hp
.a8
.i16
    stx BT_T1
    lda #100
    sta BT_T2
    rep #$20
.a16
    lda BT_ONE + BT_HP, x
    jsr bt_mul24
    lda BT_P24
    sta BT_P_HP
    lda BT_P24 + 1
    sta BT_P_HP + 1
    sep #$20
.a8
    lda BT_PCT_MIN
    sta BT_T2
    rep #$20
.a16
    ldx BT_T1
    lda BT_ONE + BT_HPMAX, x
    jsr bt_mul24
    lda BT_P_HP
    sec
    sbc BT_P24
    sep #$20                    ; `sep` does not touch C
.a8
    lda BT_P_HP + 2
    sbc BT_P24 + 2
    bcc no                      ; 100 hp < min * hp_max
    lda BT_PCT_MAX
    inc a
    sta BT_T2
    rep #$20
.a16
    ldx BT_T1
    lda BT_ONE + BT_HPMAX, x
    jsr bt_mul24
    lda BT_P_HP
    sec
    sbc BT_P24
    sep #$20
.a8
    lda BT_P_HP + 2
    sbc BT_P24 + 2
    bcs no                      ; 100 hp >= (max + 1) * hp_max
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 times the byte in `BT_T2`, in twenty-four bits, in `BT_P24`: `bt_mul`
; without losing what goes past sixteen. Clobbers `temp`.
.proc bt_mul24
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BT_T2
    sta f:WRMPYB                ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta BT_P24
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BT_T2
    sta f:WRMPYB
    stz BT_P24 + 2              ; meanwhile
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL                ; the high byte times the multiplier, which
    clc                         ; weighs 256: it is added shifted one byte
    adc BT_P24 + 1
    sta BT_P24 + 1
    rts
.endproc

; `ShowHiddenMonster`: the enemy at place A8 of the troop stops being hidden
; and starts counting for everything —target, victory, actions—, which is what
; `SetHidden(false)` does. One that was not hidden does not change: the
; command revives nobody. It is drawn by `scene_tick`, which puts in the scene
; everyone who is alive and not shown. It is called by `op_show_enemy` from
; the interpreter, with the data bank at 0: the battle's is set here.
.proc bt_show_hidden
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp BT_KID
    bcs ready
    clc
    adc #BT_PARTY_MAX
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    bit #BAF_HIDDEN
    beq ready
    and #<~BAF_HIDDEN
    ora #BAF_HAS
    sta BT_ONE + BT_FLAGS, x
ready:
    plb
    rtl
.endproc

; A16 the switch number; returns with A8 and Z=0 if it is on. It is the same
; bitmap the map looks at, `switches`, in low RAM, which with the data bank at
; $7E is in its usual place. Clobbers X and Y.
.proc bt_page_switch
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
; the battle carries on where it was —`BT_PAGE_TICK`—.
.proc bt_page_step
.a8
.i16
    ; A wait in the page —that of a `ShakeScreen` that waits, which the
    ; converter emits as OP_DELAY— is counted here, one frame per tick, which
    ; is what `events_tick` does with the map's.
    rep #$20
.a16
    lda BT_PAGE_WAIT
    beq sin_espera
    dec a
    sta BT_PAGE_WAIT
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
    jsl f:bt_t_page
    rep #$20
.a16
    lda ev_waiting
    sta BT_PAGE_WAIT
    pla
    sta ev_waiting
    lda BT_PAGE_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne a_la_pantalla
    lda BT_PAGE_ACT
    bne a_la_pantalla           ; it did not finish and asked for nothing:
                                ; that does not happen with the commands in
                                ; `TROPA_COMANDOS`, but if it did, the next
                                ; frame carries on
    jsr bt_page_test
    bne otro_tramo              ; the next one, in this same frame
    lda BT_PAGE_TICK
    bne a_las_ordenes
    jmp bt_execute
a_las_ordenes:
    lda #BT_M_COMMAND
    sta BT_MODE
a_la_pantalla:
    jmp bt_compose
.endproc

; The page's message, in the party's lines: see `BA_PAG_MSG_FILA0` in
; pantallas.py. It reads it from `mensajes_tropa` in the usual format —the
; header with the lines and each line with its length, one byte per letter
; with the ASCII minus 32— and writes it with the screen's glyphs, cut at
; `BA_PAG_MSG_ANCHO`. The block fits in one bank —the converter guarantees
; it—, so the pointer is advanced with Y and the bank stays fixed.
.proc bt_page_message
.a8
.i16
    rep #$20
.a16
    lda BT_PAGE_MSG
    clc
    adc #.loword(mensajes_tropa)
    sta msg_ptr
    lda #BA_PAG_MSG_POS0
    sta BT_T1
    sep #$20
.a8
    lda #^mensajes_tropa
    sta msg_ptr + 2
    stz temp + 1                ; blank
    lda [msg_ptr]
    and #CABECERA_LINEAS
    sta BT_PAGE_I                ; the lines left
    ldy #1
renglon:
    lda BT_PAGE_I
    beq ready
    rep #$20
.a16
    lda #BA_PAG_MSG_DX
    jsr bt_go
    sep #$20
.a8
    lda [msg_ptr], y            ; the length
    iny
    sta BT_T0                   ; the letters it has left
    stz BT_T2                   ; and the ones already written
letra:
    lda BT_T0
    beq fin_renglon
    dec BT_T0
    lda BT_T2
    cmp #BA_PAG_MSG_ANCHO
    bcs no_entra                ; consumed and not drawn
    inc BT_T2
    lda [msg_ptr], y
    clc
    adc #ITEM_PRIMER_CARACTER
    phy
    jsl f:bt_t_glyph
    ply
no_entra:
    iny
    bra letra
fin_renglon:
    rep #$20
.a16
    lda BT_T1
    clc
    adc #BA_FILA_BYTES
    sta BT_T1
    sep #$20
.a8
    dec BT_PAGE_I
    bra renglon
ready:
    rts
.endproc
