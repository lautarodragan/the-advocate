.segment "FAR"

; The window's lines: the party's, which is what it covers.
BT_VIC_LINES = BT_PARTY_MAX

; --- what the victory tells ---------------------------------------------------
;
; `ProcessSceneActionVictory` from `Scene_Battle_Rpg2k`: on winning, the
; message window says the victory term and the experience gained, and then one
; page for each actor who leveled up, with "<name> LEVEL <n> achieved!" and
; what they learned. Each page waits for A, like a map message. All the words
; come from the LDB —`victory`, `exp_received`, `level`, `level_up`,
; `skill_learned`— and the assembly is the one in `game_message_terms.cpp` for
; English RM2k, without placeholders: see `pantallas.renglon_de_nivel` and its
; sisters, which are what the converter uses to enforce that they fit.
;
; In RM2k it is the usual message window, at the bottom, **covering the
; party**; here it is the party's four lines, like the message of a troop page
; (`bt_page_message`), and the bottom line is left empty.
;
; Since 2026-09-27 the first page also tells the gold —"<gold_recieved_a>
; <n><gold><gold_recieved_b>"— and one line per item the enemies dropped
; —"<item><item_recieved>"—, like `PushGoldReceivedMessage` and
; `PushItemRecievedMessages`. They are lines of the same message as the
; victory and the experience, so whatever does not fit in the four goes on to
; another page, just like an actor's skills.

; On winning, before showing anything: notes each one's level, hands out the
; experience —which levels up and teaches, see `exp_add`—, gives the gold
; and rolls the loot, and leaves the first page ready. It is the order of
; `ProcessSceneActionVictory`, which builds the message and gives everything
; to the party in the same sub-state; of the three, only the loot rolls
; randomness. Clobbers `BT_S0` to `BT_S2`, `BA_T*`, A, X and Y.
.proc bt_vic_start
.a8
.i16
    stz BT_S0
slot:
    lda BT_S0
    cmp #BT_PARTY_MAX
    bcs anotadas
    jsr bt_vic_level
    pha
    lda BT_S0
    jsr bt_ax
    pla
    sta BT_VIC_BEFORE, x
    inc BT_S0
    bra slot
anotadas:
    jsr bt_exp_allocate
    jsr bt_vic_gold
    jsr bt_vic_drop
    lda #$FF
    sta BT_VIC_ACTOR
    stz BT_VIC_SKIP
    stz BT_VIC_MORE
    rts
.endproc

; The troop's gold, to the party: `Game_Party::GainGold`, capped at ORO_MAX.
; It does not check whether the troop gives zero: adding zero changes nothing.
.proc bt_vic_gold
.a8
.i16
    lda BT_TROOP_K
    cmp #$FF
    beq ready                   ; a troop the cartridge does not carry
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_oro, x
    ldy #2                      ; the gold: see `bt_no_hidden`
    jsr bt_no_hidden
    sta comp_or01
    sep #$20
.a8
    stz comp_or01 + 2
    jsr gold_add
ready:
    rts
.endproc

; The troop's total in A16 minus that of the enemies still hidden: a victory
; with one that never appeared —the Rat King falling before calling its rats—
; does not give its experience or its gold, because `GetExp` and `GetMoney`
; add up **the dead** and a hidden one did not die. Y = 0 the experience, 2
; the gold. Returns with A16. Clobbers `BT_T0`, `BT_T2`, X and Y.
.proc bt_no_hidden
.a16
.i16
    sta BT_T2
    sep #$20
.a8
    stz BT_T0                   ; the place in the troop
otro:
    lda BT_T0
    cmp BT_KID
    bcs ready
    clc
    adc #BT_PARTY_MAX
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HIDDEN
    beq siguiente
    lda BT_TROOP_K
    jsr bt_ax
    lda f:tropa_ini, x
    clc
    adc BT_T0
    jsr bt_ax
    lda f:tropa_miembro, x      ; the enemy, as a place in the tables
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    cpy #0
    bne es_oro
    lda BT_T2
    sec
    sbc f:enemigo_exp, x
    bra restado
es_oro:
    lda BT_T2
    sec
    sbc f:enemigo_oro, x
restado:
    sta BT_T2
    sep #$20
.a8
siguiente:
    inc BT_T0
    bra otro
ready:
    rep #$20
.a16
    lda BT_T2
    rts
.endproc

; What the enemies drop: `Game_EnemyParty::GenerateDrops`. For each one, in
; troop order, if it has an item it **rolls** `bt_pct` with its chance —the
; hundred percent one too, which is what `Rand::ChanceOf` does—, and if it
; comes up the item goes to the inventory, capped at ITEM_MAX like
; `Game_Party::AddItem`, and its `k` to `BT_DROP_K` so the page can tell it.
; The order of the rolls is that of `batalla.tirar_el_botin`. Everyone in the
; troop is dead —which is what `IsDead` asks for— except those still hidden.
; Clobbers `BT_S0` to `BT_S2`, `BA_T*`, A, X and Y.
.proc bt_vic_drop
.a8
.i16
    stz BT_DROP_N
    stz BT_S0                   ; the place in the troop
otro:
    lda BT_S0
    cmp BT_KID
    bcc hay
    rts
hay:
    ; One that is still hidden did not die, and `GenerateDrops` only rolls for
    ; the dead: no roll.
    lda BT_S0
    clc
    adc #BT_PARTY_MAX
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HIDDEN
    beq a_la_vista
    jmp siguiente
a_la_vista:
    ; The enemy, as a place in the tables: the same path as `bt_build`.
    lda BT_TROOP_K
    jsr bt_ax
    lda f:tropa_ini, x
    clc
    adc BT_S0
    jsr bt_ax
    lda f:tropa_miembro, x
    sta BT_S2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:enemigo_botin, x
    sta BT_S1                   ; the LDB item, or 0
    sep #$20
.a8
    beq siguiente               ; leaves nothing: no roll
    lda BT_S2
    jsr bt_ax
    lda f:enemigo_botin_pct, x
    jsr bt_pct
    beq siguiente
    ldx BT_S1
    lda FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs lleno
    inc a
    sta FAR_ITEMS, x
lleno:
    lda f:item_k, x             ; the converter enforces that it is carried
    pha
    lda BT_DROP_N
    jsr bt_ax
    pla
    sta BT_DROP_K, x
    inc BT_DROP_N
siguiente:
    inc BT_S0
    bra otro
.endproc

; The current level of the actor in party slot A8, or 0 if the slot is empty
; or its actor has no experience. Clobbers X.
.proc bt_vic_level
.a8
.i16
    cmp BT_NACT
    bcs nothing
    jsr bt_x
    lda BT_ONE + BT_FLAGS, x
    and #BAF_HAS
    beq nothing
    lda BT_ONE + BT_NUMBER, x
    jsr bt_ax
    lda f:actor_exp_k, x
    cmp #$FF
    beq nothing
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda FAR_EXP + EXP_LEVEL, x
    rts
nothing:
    lda #0
    rts
.endproc

; A8 nonzero —and Z at 0— if the actor in slot A8 leveled up in this victory.
; Clobbers X and `BT_T0`.
.proc bt_vic_level_up
.a8
.i16
    pha
    jsr bt_vic_level
    sta BT_T0
    pla
    jsr bt_ax
    lda BT_VIC_BEFORE, x
    beq no                      ; no experience, or nobody
    cmp BT_T0
    bcs no                      ; the same level as before
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A on the end screen: if another page is left, it sets it up and returns A8
; nonzero; if not, 0, and the battle closes. A defeat or an escape have no
; pages. Clobbers X and `BT_T0`.
.proc bt_vic_next
.a8
.i16
    lda BT_RESULT
    cmp #BT_VICTORY
    bne ninguna
    lda BT_VIC_MORE
    beq otro_actor
    ; The skills that did not fit go on in another page of the same actor,
    ; which is what RM2k's window does with a message of more than four lines.
    lda BT_VIC_NEXT
    sta BT_VIC_SKIP
    lda #1
    rts
otro_actor:
    stz BT_VIC_SKIP
    lda BT_VIC_ACTOR
busca:
    inc a                       ; from $FF, the first page, it goes to slot 0
    cmp BT_NACT
    bcs ninguna
    sta BT_VIC_ACTOR
    jsr bt_vic_level_up
    cmp #0                      ; `jsr` does not keep the flags from the `lda` inside
    bne hay
    lda BT_VIC_ACTOR
    bra busca
hay:
    lda #1
    rts
ninguna:
    lda #0
    rts
.endproc

; Z at 0 if what the screen shows is a victory: the battle ended won and the
; message is the victory's. `bt_compose` asks it before drawing the party.
.proc bt_vic_on_screen
.a8
.i16
    lda BT_MTIPO
    cmp #BT_MSG_VICTORY
    bne no
    lda BT_MODE
    cmp #BT_M_MESSAGE
    beq si
    cmp #BT_M_END
    beq si
no:
    lda #0
    rts
si:
    lda #1
    rts
.endproc

; The current page on the party's lines. `bt_compose` calls it with `jmp`, so
; its `rts` is the composer's: the bottom line, the battle message's, is left
; empty. Clobbers `BT_S0` to `BT_S4`, `BA_T*`, A, X and Y.
.proc bt_vic_message
.a8
.i16
    stz temp + 1                ; white
    rep #$20
.a16
    lda #BA_PAG_MSG_POS0
    sta BT_T1
    lda #BA_PAG_MSG_DX
    jsr bt_go
    sep #$20
.a8
    lda BT_VIC_ACTOR
    cmp #$FF
    beq primera
    jmp de_un_actor
primera:
    ; The lines of the victory message, four per page: see `bt_vic_line`,
    ; which counts the ones already shown.
    stz BT_VIC_MORE
    lda BT_VIC_SKIP
    sta BT_VIC_NEXT
    stz BT_S3
    stz BT_S4
    ; The victory term, on the lines the converter split it into —see
    ; `pantallas.renglones_de_la_victoria`—.
    jsr bt_vic_line
    bcc sin_v1
    ldx #BA_TXT_VICTORIA
    jsr bt_finished
sin_v1:
    lda #BA_VIC_TERMINO_N       ; not with `.if`: the constant comes later
    cmp #2
    bcc un_renglon
    jsr bt_vic_line
    bcc un_renglon
    ldx #BA_TXT_VICTORIA2
    jsr bt_finished
un_renglon:
    ; And the experience, if any: easyrpg's `if (exp > 0)`. The gold goes the
    ; same way, `if (money > 0)`.
    lda BT_TROOP_K
    cmp #$FF
    bne con_tropa
    rts
con_tropa:
    rep #$20
.a16
    and #$00FF
    asl a
    sta BT_S1                   ; the troop's place in the word-sized tables
    tax
    lda f:tropa_exp, x
    ldy #0                      ; without those that stayed hidden
    jsr bt_no_hidden
    sep #$20                    ; `sep` does not touch Z
.a8
    beq sin_exp
    jsr bt_vic_line
    bcc sin_exp
    rep #$20
.a16
    ldx BT_S1
    lda f:tropa_exp, x
    ldy #0
    jsr bt_no_hidden
    sta BT_T0
    sep #$20
.a8
    jsr bt_vic_number
    ldx #BA_TXT_EXP_RECIBIDA
    jsr bt_finished
sin_exp:
    rep #$20
.a16
    ldx BT_S1
    lda f:tropa_oro, x
    ldy #2
    jsr bt_no_hidden
    sep #$20
.a8
    beq sin_oro
    jsr bt_vic_line
    bcc sin_oro
    ldx #BA_TXT_ORO_A
    jsr bt_finished
    lda #$20
    jsl f:bt_t_glyph
    rep #$20
.a16
    ldx BT_S1
    lda f:tropa_oro, x
    ldy #2
    jsr bt_no_hidden
    sta BT_T0
    sep #$20
.a8
    jsr bt_vic_number
    ldx #BA_TXT_MONEDA
    jsr bt_finished
    ldx #BA_TXT_ORO_B
    jsr bt_finished
sin_oro:
    ; And one line per item, in the order they came up.
    stz BT_S0
item:
    lda BT_S0
    cmp BT_DROP_N
    bcs listos
    jsr bt_vic_line
    bcc otro_item
    lda BT_S0
    jsr bt_ax
    lda BT_DROP_K, x
    rep #$20
.a16
    and #$00FF
    sta BT_T0
    asl a
    clc
    adc BT_T0                   ; times three: `3k` is the item's name
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:bt_t_text
    ldx #BA_TXT_OBTENIDO
    jsr bt_finished
otro_item:
    inc BT_S0
    bra item
listos:
    rts

de_un_actor:
    ; "<name> LEVEL <n> achieved!", only on its first page.
    lda #1
    sta BT_S3                   ; lines written, the top one already counted
    lda BT_VIC_SKIP
    bne sin_nivel
    lda BT_VIC_ACTOR
    jsr bt_name
    lda #$20
    jsl f:bt_t_glyph
    ldx #BA_TXT_NIVEL
    jsr bt_finished
    lda #$20
    jsl f:bt_t_glyph
    lda BT_VIC_ACTOR
    jsr bt_vic_level
    rep #$20
.a16
    and #$00FF
    sta BT_T0
    sep #$20
.a8
    jsr bt_vic_number
    ldx #BA_TXT_SUBIO
    jsr bt_finished
    bra habilidades
sin_nivel:
    stz BT_S3                   ; the continuation starts on the top one
habilidades:
    ; And "<skill> acquired!" for each one taught by the levels it went
    ; through, level by level like `LearnLevelSkills(old_level + 1,
    ; new_level)`. `BT_VIC_SKIP` is the ones already shown on earlier pages.
    ;
    ; **It says every one the table teaches at those levels**, and RM2k only
    ; the ones it did not know —`LearnSkill` does not announce it if it was
    ; already there—: the two differ only if a `ChangeSkills` taught it one
    ; earlier that a level teaches later, and in ABL none does. `exp_add`
    ; already set the bits, so here there is no way to know which were there.
    stz BT_VIC_MORE
    lda BT_VIC_SKIP
    sta BT_VIC_NEXT
    stz BT_S4                   ; the ones already seen, written or skipped
    lda BT_VIC_ACTOR
    jsr bt_vic_level
    sta BT_S2                   ; up to which level
    lda BT_VIC_ACTOR
    jsr bt_ax
    lda BT_VIC_BEFORE, x
    sta BT_S0                   ; the level being looked at, from the previous one + 1
    lda BT_VIC_ACTOR
    jsr bt_x
    lda BT_ONE + BT_NUMBER, x
    sta BT_S0 + 1               ; the LDB actor
nivel:
    lda BT_S0
    cmp BT_S2
    bcc otro_nivel
    rts                         ; the current one has been looked at already
otro_nivel:
    inc BT_S0
    ; The actor's pairs: `hab_par_ini` and `hab_par_n`, like `learn_from_level`.
    lda BT_S0 + 1
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:hab_par_ini, x
    sta BT_S1                   ; the pair being looked at
    sep #$20
.a8
    lda BT_S0 + 1
    jsr bt_ax
    lda f:hab_par_n, x
    sta BT_S2 + 1               ; how many it has left
    beq nivel
par:
    ldx BT_S1
    lda f:hab_par_nivel, x
    cmp BT_S0
    bne siguiente
    inc BT_S4
    lda BT_S4
    cmp BT_VIC_SKIP
    beq siguiente               ; shown on an earlier page
    bcc siguiente
    lda BT_S3
    cmp #BT_VIC_LINES
    bcc entra
    lda #1                      ; does not fit: goes on in another page
    sta BT_VIC_MORE
    bra ready
entra:
    inc BT_S3
    inc BT_VIC_NEXT
    lda BT_S3
    cmp #1
    beq arriba                  ; the first one of a continuation
    jsr bt_vic_text_line
arriba:
    rep #$20
.a16
    lda BT_S1
    asl a
    tax
    lda f:hab_par_aprende_txt, x
    tax
    sep #$20
.a8
    jsr bt_finished
    ldx #BA_TXT_APRENDIO
    jsr bt_finished
siguiente:
    rep #$20
.a16
    inc BT_S1
    sep #$20
.a8
    dec BT_S2 + 1
    beq otro
    jmp par
otro:
    jmp nivel
ready:
    rts
.endproc

; The next line of the first page, if it belongs on this one: C at 1 and the
; position set, or C at 0 if it was shown on an earlier page —the first
; `BT_VIC_SKIP`— or it does not fit, and then `BT_VIC_MORE` is left set. It
; keeps the count in `BT_S4`, the ones seen, and `BT_S3`, the ones written,
; which `bt_vic_message` zeroes. It is the same count as an actor's skills,
; further down.
.proc bt_vic_line
.a8
.i16
    inc BT_S4
    lda BT_S4
    cmp BT_VIC_SKIP
    beq no                      ; shown on an earlier page
    bcc no
    lda BT_S3
    cmp #BT_VIC_LINES
    bcc entra
    lda #1                      ; does not fit: goes on in another page
    sta BT_VIC_MORE
no:
    clc
    rts
entra:
    inc BT_VIC_NEXT
    lda BT_S3
    beq arriba                  ; the page's first one is already set
    jsr bt_vic_text_line
arriba:
    inc BT_S3
    sec
    rts
.endproc

; The line below the one being written, from its start.
.proc bt_vic_text_line
.a8
.i16
    rep #$20
.a16
    lda BT_T1
    clc
    adc #BA_FILA_BYTES
    sta BT_T1
    lda #BA_PAG_MSG_DX
    jsr bt_go
    sep #$20
.a8
    rts
.endproc

; `BT_T0` without leading spaces, up to five digits: a troop's experience does
; not fit in `scr_number`'s three. Clobbers A, X, Y and `BT_T0`.
.proc bt_vic_number
.a8
.i16
    stz BT_T2                   ; whether a digit has been written already
    ldx #0                      ; which power of ten
potencia:
    ldy #0                      ; the digit
    rep #$20
.a16
resta:
    lda BT_T0
    cmp f:potencias, x          ; with `f:`: the data bank is $7E
    bcc cifra
    sbc f:potencias, x          ; C comes from the comparison
    sta BT_T0
    iny
    bra resta
cifra:
    sep #$20
.a8
    tya
    ora BT_T2
    beq cero_adelante
    sta BT_T2
    tya
    clc
    adc #$30
    phx
    jsl f:bt_t_glyph
    plx
cero_adelante:
    inx
    inx
    cpx #8
    bcc potencia
    lda BT_T0                   ; the units, always
    clc
    adc #$30
    jsl f:bt_t_glyph
    rts
potencias:
    .word 10000, 1000, 100, 10
.endproc
