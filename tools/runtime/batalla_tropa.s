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

; The pages of this battle's troop, from `BA_TROPA_K`. A troop the cartridge
; does not carry has none.
.proc bt_page_build
.a8
.i16
    stz BA_PAG_N
    rep #$20
.a16
    stz BA_PAG_ESPERA
    stz BA_TURNO                ; the `turns` of `Game_Party`, which the
                                ; battle sets to zero when it starts
    sep #$20
.a8
    lda BA_TROPA_K
    cmp #$FF
    beq ready
    jsr bt_ax
    lda f:tropa_pag_n, x
    sta BA_PAG_N
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:tropa_pag_ini, x
    sta BA_PAG_INI
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
    stz BA_PAG_HECHA, x
    inx
    cpx #TROPA_PAG_MAX
    bne otra
    rts
.endproc

; If there is a page to run, leaves it ready —its code, the cursor at zero,
; marked as run— with the battle in `BA_M_PAGINA`, and returns with A8 at 1.
; If not, at 0. **Z matches A**: it comes from an explicit `lda`.
;
; First `CheckBattleEndConditions`: with one whole side down the battle ends
; and none runs. Clobbers `BA_S0`, `BA_T*`, A, X and Y.
.proc bt_page_test
.a8
.i16
    lda BA_PAG_N
    beq no
    jsr bt_enemy_alive
    cmp #$FF
    beq no
    lda #0
    sta BA_PAG_I
alguien:
    lda BA_PAG_I
    cmp BA_NACT
    bcs no                      ; nobody in the party standing
    jsr bt_alive
    bne hay_grupo
    inc BA_PAG_I
    bra alguien
hay_grupo:
    lda #0
    sta BA_PAG_I
otra:
    lda BA_PAG_I
    cmp BA_PAG_N
    bcs no
    jsr bt_ax
    lda BA_PAG_HECHA, x
    bne siguiente
    jsr bt_page_met
    bne esta
siguiente:
    inc BA_PAG_I
    bra otra
esta:
    lda BA_PAG_I
    jsr bt_ax
    lda #1
    sta BA_PAG_HECHA, x
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_cod, x
    sta BA_PAG_COD
    stz BA_PAG_CUR
    lda #$FFFF
    sta BA_PAG_MSG
    sep #$20
.a8
    lda #1
    sta BA_PAG_ACT
    lda #BA_M_PAGINA
    sta BA_MODO
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether the troop's page `BA_PAG_I` is met: `AreConditionsMet`, with the six
; triggers the ROM knows how to check —RM2k's; the three from 2003 do not
; exist in this game—. Leaves in `BA_PAG_G` its place in the `tpag_*` tables
; and returns with Z=0 if it is met. Clobbers `BA_T*`, `temp`, A, X and Y.
.proc bt_page_met
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_I
    and #$00FF
    clc
    adc BA_PAG_INI
    sta BA_PAG_G
    tax
    sep #$20
.a8
    lda f:tpag_flags, x
    sta BA_PAG_FL               ; the triggers, which survive the `jsr`s
    and #TPAG_SWITCH_A
    beq sin_a
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_a, x
    jsr bt_page_switch
.a8
    bne sin_a
    jmp no
sin_a:
    lda BA_PAG_FL
    and #TPAG_SWITCH_B
    beq sin_b
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_sw_b, x
    jsr bt_page_switch
.a8
    bne sin_b
    jmp no
sin_b:
    lda BA_PAG_FL
    and #TPAG_VARIABLE
    beq sin_var
    ; The variable, signed `>=`: `Get(variable_id) >= variable_value`.
    rep #$20
.a16
    lda BA_PAG_G
    asl a
    tax
    lda f:tpag_valor, x
    sta BA_T0
    lda f:tpag_var, x
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
    lda BA_PAG_FL
    and #TPAG_CON_CABECERA
    bne con_cabecera
    jmp si
con_cabecera:
    jsr bt_page_header
    lda BA_PAG_FL
    and #TPAG_TURNO
    beq sin_turno
    ; The turn: `Game_Battle::CheckTurns(turn, turn_b, turn_a)`, with the base
    ; and the multiple **in that order**, which is the opposite of what
    ; liblcf's names suggest. Without a multiple, exactly at the base; with
    ; one, at the base and every so many. The converter leaves them in the
    ; header already in place.
    rep #$20
.a16
    lda BA_TURNO
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
    lda BA_PAG_FL
    and #TPAG_ENEMIGO
    beq sin_enemigo
    ; An enemy's HP, by its place in the troop. `GetEnemy` does not check
    ; whether it is hidden or dead: only whether the place exists.
    lda BA_COND + BA_COND_EMIN
    sta BA_PCT_MIN
    lda BA_COND + BA_COND_EMAX
    sta BA_PCT_MAX
    lda BA_COND + BA_COND_ENE
    cmp BA_NENE
    bcs no
    clc
    adc #BA_GRUPO_MAX
    jsr bt_x
    jsr bt_page_hp
    beq no
sin_enemigo:
    lda BA_PAG_FL
    and #TPAG_ACTOR
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
    jsr bt_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq otro_actor
    lda BA_UNO + BA_NUMERO, x
    cmp BA_COND + BA_COND_ACT
    beq actor_hallado
otro_actor:
    inc BA_T0 + 1
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

; The header of page `BA_PAG_G` —the turn and HP numbers, which the converter
; puts in front of its code, `TPAG_CABECERA` bytes before where `tpag_cod`
; points— into `BA_COND`. It is read with the data bank at that of
; `tropa_codigo`, which fits whole in one bank, and written with `f:`.
; Clobbers A, X and Y. See `eventos.cabecera_de_tropa`.
.proc bt_page_header
.a8
.i16
    rep #$20
.a16
    lda BA_PAG_G
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
    sta f:BAT_LARGO + BA_COND, x
    iny
    inx
    cpx #TPAG_CABECERA
    bne otro
    plb
    rts
.endproc

; Whether the HP of the combatant at offset X —the one from `bt_x`— are
; between `BA_PCT_MIN` and `BA_PCT_MAX` percent, counted the way
; `AreConditionsMet` counts them: `100 * hp / hp_max`, integer. Without
; dividing: the quotient being at least `min` is `min * hp_max <= 100 * hp`,
; and it not going past `max` is `100 * hp < (max + 1) * hp_max`. The products
; go past sixteen bits —a hundred times a boss's HP— and so they go in
; twenty-four. Returns with A8 and Z=0 if it is. Clobbers `BA_T1`, `BA_T2`
; and `temp`.
.proc bt_page_hp
.a8
.i16
    stx BA_T1
    lda #100
    sta BA_T2
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    jsr bt_mul24
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
    lda BA_UNO + BA_HPMAX, x
    jsr bt_mul24
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
    lda BA_UNO + BA_HPMAX, x
    jsr bt_mul24
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

; A16 times the byte in `BA_T2`, in twenty-four bits, in `BA_P24`: `bt_mul`
; without losing what goes past sixteen. Clobbers `temp`.
.proc bt_mul24
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
.proc bt_show_hidden
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    cmp BA_NENE
    bcs ready
    clc
    adc #BA_GRUPO_MAX
    jsr bt_x
    lda BA_UNO + BA_FLAGS, x
    bit #BAF_OCULTO
    beq ready
    and #<~BAF_OCULTO
    ora #BAF_HAY
    sta BA_UNO + BA_FLAGS, x
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
    lda f:mascara, x
    and switches, y
    rts
.endproc

; One stretch of the running page, and what follows: if it asked for a
; message, to the screen; if it finished, the next one; and if none is left,
; the battle carries on where it was —`BA_PAG_VUELTA`—.
.proc bt_page_step
.a8
.i16
    ; A wait in the page —that of a `ShakeScreen` that waits, which the
    ; converter emits as OP_DELAY— is counted here, one frame per tick, which
    ; is what `events_tick` does with the map's.
    rep #$20
.a16
    lda BA_PAG_ESPERA
    beq sin_espera
    dec a
    sta BA_PAG_ESPERA
    sep #$20
.a8
    rts
sin_espera:
    sep #$20
otro_tramo:
.a8
    rep #$20
.a16
    ; `ev_esperando` belongs to the map's interpreter, which was left halfway
    ; through inside `op_battle`: the page's is kept separately.
    lda ev_esperando
    pha
    stz ev_esperando
    sep #$20
.a8
    jsl f:bt_t_page
    rep #$20
.a16
    lda ev_esperando
    sta BA_PAG_ESPERA
    pla
    sta ev_esperando
    lda BA_PAG_MSG
    cmp #$FFFF
    sep #$20
.a8
    bne a_la_pantalla
    lda BA_PAG_ACT
    bne a_la_pantalla           ; it did not finish and asked for nothing:
                                ; that does not happen with the commands in
                                ; `TROPA_COMANDOS`, but if it did, the next
                                ; frame carries on
    jsr bt_page_test
    bne otro_tramo              ; the next one, in this same frame
    lda BA_PAG_VUELTA
    bne a_las_ordenes
    jmp bt_execute
a_las_ordenes:
    lda #BA_M_ORDEN
    sta BA_MODO
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
    lda BA_PAG_MSG
    clc
    adc #.loword(mensajes_tropa)
    sta msg_ptr
    lda #BA_PAG_MSG_POS0
    sta BA_T1
    sep #$20
.a8
    lda #^mensajes_tropa
    sta msg_ptr + 2
    stz temp + 1                ; blank
    lda [msg_ptr]
    and #CABECERA_LINEAS
    sta BA_PAG_I                ; the lines left
    ldy #1
renglon:
    lda BA_PAG_I
    beq ready
    rep #$20
.a16
    lda #BA_PAG_MSG_DX
    jsr bt_go
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
    cmp #BA_PAG_MSG_ANCHO
    bcs no_entra                ; consumed and not drawn
    inc BA_T2
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
    lda BA_T1
    clc
    adc #BA_FILA_BYTES
    sta BA_T1
    sep #$20
.a8
    dec BA_PAG_I
    bra renglon
ready:
    rts
.endproc
