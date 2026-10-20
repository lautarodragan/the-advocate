.segment "FAR3"

; --- the battle's message ----------------------------------------------------
;
; Put together and drawn: what `ba_compose` writes in the message window when
; the screen is showing one. It is entered with `jsl` —`jsl f:ba_message`,
; from `ba_compose` in battle_skills.s— and leaves with `rtl` from the end of
; `ba_flow`, which every path reaches. It lived in battle.s, in `FAR2`, until
; 2026-10-20, when a skill's result lines did not fit in Sunset over Imdahl's
; `FAR2`: the move alone is its own commit. It calls nothing near outside this
; file but the three helpers at the end, copies of battle.s's `ba_x`, `ba_ax`
; and `ba_go`; the rest of what it calls is `jsl`.

; The message, according to `BA_MTYPE`. Victory does not go through here: it
; goes in the same window, see `ba_vic_message`. All the words come from
; the LDB —`attacking`, `enemy_damaged`, `defeat`...— and are put together as
; in `game_message_terms.cpp`: the name stuck to the term, and in the damage
; one the number in the middle. None of them is ours.
;
; **It is put together in `BA_MBUF` first and drawn after**, by `ba_flow`:
; RM2k's lines are as long as the pieces make them —"Talan has perceived the
; enemy aura." is thirty-five— and one line here carries thirty-one. Drawn
; letter by letter, what did not fit went on in the cell below, which is the
; bottom half of the line. So each of RM2k's lines is cut at the spaces into
; as many as it takes, up to the window's four.
.proc ba_message
.a8
.i16
    jsr ba_mopen
    lda BA_MTYPE
    cmp #BA_MSG_ATTACK
    beq attack
    cmp #BA_MSG_DEFENDS
    beq defends
    cmp #BA_MSG_NO_FLED
    beq no_fled
    cmp #BA_MSG_FLED
    beq fled
    cmp #BA_MSG_ITEM
    beq uses_item
    cmp #BA_MSG_SKILL
    beq uses_skill
    cmp #BA_MSG_ITEM_SP
    beq item_sp
    cmp #BA_MSG_STATE
    beq state
    ldx #BA_TXT_DEFEAT
    jmp only
state:
    ; A condition's: `<who><text>`, its `message_affected` or its
    ; `message_recovery`, stuck to the name as `PushWithSubject` and
    ; `GetStateRecoveryMessage` do. See battle_states.s.
    lda .loword(ba_st_who)
    jsr ba_put_name
    ldx .loword(ba_st_text)
    jsr ba_put_text
    jmp ba_flow
item_sp:
    jmp item
uses_skill:
    jmp skill
uses_item:
    jmp item
fled:
    ldx #BA_TXT_FLED
    jmp only
no_fled:
    ldx #BA_TXT_NO_FLED
only:
    jsr ba_put_text
    jmp ba_flow
defends:
    lda BA_MWHO
    jsr ba_put_name
    ldx #BA_TXT_DEFENDS
    jsr ba_put_text
    jmp ba_flow
attack:
    lda BA_MWHO
    jsr ba_put_name
    ldx #BA_TXT_ATTACKS
    jsr ba_put_text
    ; The second line: the result on the target.
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    rep #$20
.a16
    lda BA_MDMG
    cmp #$FFFF
    sep #$20
.a8
    bne stuck
    jmp failed
stuck:
    ; `<name> <damage> health lost.`
    lda #$20                    ; the space between the name and the number
    jsr ba_put
    rep #$20
.a16
    lda BA_MDMG
    sta BA_T0
    sep #$20
.a8
    jsr ba_put_number
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs is_enemy
    ldx #BA_TXT_DAMAGE_ACTOR
    bra says
is_enemy:
    ldx #BA_TXT_DAMAGE_ENEMY
says:
    jsr ba_put_text
    jmp ba_flow
item:
    ; `<who> <item> used.`, which is
    ; `source.GetName() + " " + item.name + terms.use_item` from
    ; `GetItemStartMessage2k`.
    lda BA_MWHO
    jsr ba_put_name
    lda #$20
    jsr ba_put
    rep #$20
.a16
    lda BA_MITEM
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; times three: `3k` is the item's name
    tax
    sep #$20
.a8
    jsr ba_put_text
    ldx #BA_TXT_USES
    jsr ba_put_text
    ; The second line, the result: RM2k writes one after the other in the
    ; same place —see `ba_item_use`—, and here each is a message. The SP one
    ; goes alone when there is no HP line, and after it when there is.
    lda BA_MTYPE
    cmp #BA_MSG_ITEM_SP
    beq sp_line
    lda BA_MREVIVED
    bne revived
    lda BA_MHPLINE
    bne hp_line
    rep #$20
.a16
    lda BA_MSP
    sep #$20
.a8
    bne sp_line
    jmp ba_flow                 ; nothing changed: the first line alone
revived:
    ; Revived: `<target> has revived!`, the dead state's `message_recovery`,
    ; stuck to the name. RM2k does not show the HP one when it revives
    ; —`IsRevived` in the `ePreHp` of `ProcessBattleActionParamEffects`— but
    ; the one for the states it removed —`ProcessBattleActionStateEffects`—,
    ; and of those the port only knows the dead one.
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    ldx #BA_TXT_REVIVED
    jsr ba_put_text
    jmp ba_flow
hp_line:
    ; `<target> HP <n> Recovered`, which is `GetHpSpRecoveredMessage`.
    ldx #BA_TXT_HP
    rep #$20
.a16
    lda BA_MHEAL
    bra recovered
sp_line:
.a8
    ; And with the SP: `GetSpRecoveredMessage` is the same with
    ; `spirit_points`.
    ldx #BA_TXT_SP
    rep #$20
.a16
    lda BA_MSP
recovered:
    pha                         ; the number, and below it the term
    sep #$20
.a8
    phx
    jsr ba_mnext
    lda BA_MTGT
    jsr ba_put_name
    lda #$20
    jsr ba_put
    plx
    jsr ba_put_text
    lda #$20
    jsr ba_put
    rep #$20
.a16
    pla
    sta BA_T0
    sep #$20
.a8
    jsr ba_put_number
    ldx #BA_TXT_RECOVERED
    jsr ba_put_text
    jmp ba_flow
skill:
    ; `<who><using_message1>` on top and `<using_message2>` below, which is
    ; `GetSkillFirstStartMessage2k` and its sibling. Both lines come from the
    ; LDB, like everything this screen writes.
    lda BA_MWHO
    jsr ba_put_name
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_msg1, x
    tax
    sep #$20
.a8
    jsr ba_put_text
    jsr ba_mnext
    rep #$20
.a16
    lda BA_MSKILL
    and #$00FF
    asl a
    tax
    lda f:skill_msg2, x
    tax
    sep #$20
.a8
    jsr ba_put_text
    jmp ba_flow
failed:
    lda BA_MTGT
    cmp #BA_PARTY_MAX
    bcs fails_enemy
    ldx #BA_TXT_NO_DAMAGE_ACTOR
    bra fails_says
fails_enemy:
    ldx #BA_TXT_NO_DAMAGE_ENEMY
fails_says:
    jsr ba_put_text
    jmp ba_flow
.endproc

; --- the message, put together before it is drawn ----------------------------
;
; `BA_MBUF` holds RM2k's two lines, one after the other, a letter per byte;
; `BA_MPTR` is where the next letter goes and `BA_MLIM` where the line being
; written ends. What does not fit in `BA_MBUF_MAX` is dropped: no message of
; the game comes near it.

; The first line, empty.
.proc ba_mopen
.a8
.i16
    rep #$20
.a16
    lda #BA_MBUF
    sta BA_MPTR
    sta BA_MSTART
    clc
    adc #BA_MBUF_MAX
    sta BA_MLIM
    sep #$20
.a8
    lda #1
    sta BA_MN
    rts
.endproc

; The second line: the first ends where it is.
.proc ba_mnext
.a8
.i16
    rep #$20
.a16
    lda BA_MPTR
    sta BA_MEND
    lda #BA_MBUF + BA_MBUF_MAX
    sta BA_MPTR
    sta BA_MSTART + 2
    clc
    adc #BA_MBUF_MAX
    sta BA_MLIM
    sep #$20
.a8
    lda #2
    sta BA_MN
    rts
.endproc

; A8, a letter, at the end of the line being written. Clobbers X.
.proc ba_put
.a8
.i16
    ldx BA_MPTR
    cpx BA_MLIM
    bcs full
    sta a:0, x                  ; bank $7E: the data bank of the battle
    inx
    stx BA_MPTR
full:
    rts
.endproc

; Text X —see `item_txt_*`— at the end of the line, whole. Clobbers X, Y
; and `BA_MCOUNT`.
.proc ba_put_text
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    beq done
    sta BA_MCOUNT
    ldy #0
letter:
    lda [msg_ptr], y
    jsr ba_put
    iny
    dec BA_MCOUNT
    bne letter
done:
    rts
.endproc

; The name of combatant A8 at the end of the line, whole.
.proc ba_put_name
.a8
.i16
    jsr bm_x
    rep #$20
.a16
    lda BA_ONE + BA_TXT, x
    tax
    sep #$20
.a8
    jmp ba_put_text
.endproc

; The number in `BA_T0`, 0 to 9999, at the end of the line with no leading
; spaces: easyrpg sticks the damage to the name without padding. Clobbers
; `BA_T0`, X and Y.
.proc ba_put_number
.a8
.i16
    stz BA_MCOUNT               ; whether a digit has gone already
    ldx #0
power:
    ldy #0
    rep #$20
.a16
    lda BA_T0
subtract:
    cmp f:powers, x
    bcc digit
    sbc f:powers, x             ; C=1 from the cmp
    iny
    bra subtract
digit:
    sta BA_T0
    sep #$20
.a8
    tya
    bne write
    lda BA_MCOUNT
    beq next                    ; a zero before everything else
    lda #0
write:
    clc
    adc #'0'
    phx
    jsr ba_put
    plx
    lda #1
    sta BA_MCOUNT
next:
    inx
    inx
    cpx #6
    bcc power
    lda BA_T0                   ; the units, always
    clc
    adc #'0'
    jmp ba_put
powers:
    .word 1000, 100, 10
.endproc

; How many letters from `BA_MP` fit in a line —their advances add up to
; `BA_PAGE_MSG_WIDTH` cells at most—, up to `BA_ME`; one at least, so that
; the cut always moves. Uses `BA_MB`. A16.
.proc ba_fit
.a16
.i16
    stz BA_MB                   ; the pixels so far
    ldx BA_MP
letter:
    cpx BA_ME
    bcs done
    lda a:0, x
    and #$00FF
    sec
    sbc #' '
    phx
    tax
    lda f:font_advance, x
    plx
    and #$00FF
    clc
    adc BA_MB
    cmp #(BA_PAGE_MSG_WIDTH * 8 + 1)
    bcs done
    sta BA_MB
    inx
    bra letter
done:
    txa
    sec
    sbc BA_MP
    bne some
    inc a
some:
    rts
.endproc

; The message's lines, cut and drawn: each of RM2k's lines in `BA_MBUF` is
; cut into lines as wide as `BA_PAGE_MSG_WIDTH` cells at its spaces —a word
; longer than that, at the edge—, and the spaces of the cut go nowhere. A
; line is measured in pixels, with the font's advances: until 2026-10-03 it
; was `BA_PAGE_MSG_WIDTH` letters, one per cell. Up to `BA_MLINES_MAX`
; lines, from the window's first, `BA_MSG_POS1`, down: RM2k's message
; window, which takes the whole band. Until 2026-10-04 the last went on the
; bottom line of the screen and the others over the party's. Clobbers
; everything.
.proc ba_flow
.a8
.i16
    lda BA_MN
    cmp #2                      ; C=1 if it is the second
    rep #$20
.a16
    lda BA_MPTR
    ldx #0
    bcc first_end
    ldx #2
first_end:
    sta BA_MEND, x              ; where the line being written ends
    sep #$20
.a8
    stz BA_MDN
    stz BA_MI
one_line:
    lda BA_MI
    cmp BA_MN
    bcc cut_it
    jmp draw
cut_it:
    asl a
    jsr bm_ax
    rep #$20
.a16
    lda BA_MSTART, x
    sta BA_MP
    lda BA_MEND, x
    sta BA_ME
    sep #$20
.a8
again:
    lda BA_MDN
    cmp #BA_MLINES_MAX
    bcs line_done
    rep #$20
.a16
    lda BA_ME
    sec
    sbc BA_MP
    beq line_done16             ; nothing left
    pha
    jsr ba_fit
    cmp 1, s
    bcc too_long                ; fewer than what is left
    pla
    jsr ba_mline                ; the rest, as it is
line_done16:
    sep #$20
.a8
line_done:
    inc BA_MI
    jmp one_line
.a16
too_long:
    ; The last space at most one line further on: the line is what is
    ; before it.
    sta BA_MB                   ; how many fit, for a word with no space
    pla
    lda BA_MP
    clc
    adc BA_MB
    tax
    sep #$20
.a8
seek:
    cpx BA_MP
    beq no_space
    lda a:0, x
    cmp #$20
    beq space
    dex
    bra seek
no_space:
    ; A word longer than the line: cut at the edge.
    rep #$20
.a16
    lda BA_MB
    jsr ba_mline
    lda BA_MP
    clc
    adc BA_MB
    sta BA_MP
    bra skip_spaces
.a8
space:
    stx BA_MB
    ; Without the spaces before the cut.
trim:
    dex
    cpx BA_MP
    bcc trimmed
    lda a:0, x
    cmp #$20
    beq trim
trimmed:
    inx
    rep #$20
.a16
    txa
    sec
    sbc BA_MP
    jsr ba_mline
    lda BA_MB
    sta BA_MP
skip_spaces:
    ; And the next one starts after the spaces.
    ldx BA_MP
    sep #$20
.a8
skip:
    cpx BA_ME
    bcs skipped
    lda a:0, x
    cmp #$20
    bne skipped
    inx
    bra skip
skipped:
    stx BA_MP
    jmp again

draw:
    rep #$20
.a16
    lda #BA_MSG_POS1
    sta BA_T1
    sep #$20
.a8
    stz BA_MI
    stz temp + 1                ; white
each:
    lda BA_MI
    cmp BA_MDN
    bcc a_line
    rtl                         ; the message's end: see the top of the file
a_line:
    ; The line blank first: it is the row's text that goes, in the text
    ; layer —nothing else is drawn under the message since 2026-10-04, but
    ; it costs nothing—.
    rep #$20
.a16
    lda BA_T1
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the row: 64 bytes each
    sep #$20
.a8
    jsl f:tl_clear_row + FAST
    rep #$20
.a16
    lda #BA_MSG_DX
    jsr bm_go
    lda BA_MI
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; three bytes per line
    tax
    lda BA_MDL, x
    sta BA_MP                   ; where it starts
    lda BA_MDL + 2, x
    and #$00FF
    sta BA_T0                   ; and how many letters
    sep #$20
.a8
letter:
    lda BA_T0
    beq next_line
    dec BA_T0
    ldx BA_MP
    lda a:0, x
    inx
    stx BA_MP
    jsl f:ba_t_glyph
    bra letter
next_line:
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_ROW_BYTES
    sta BA_T1
    sep #$20
.a8
    inc BA_MI
    bra each
.endproc

; One more line to draw: from `BA_MP`, A16 letters. Comes and goes with A16.
.proc ba_mline
.a16
.i16
    pha
    lda BA_MDN
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; three bytes per line
    tax
    lda BA_MP
    sta BA_MDL, x
    pla
    sep #$20
.a8
    sta BA_MDL + 2, x
    inc BA_MDN
    rep #$20
.a16
    rts
.endproc

; --- battle.s's three near helpers, copied: a `jsr` does not cross banks ------

; A8 = a combatant; X = its offset inside `BA_ONE`: `ba_x`.
.proc bm_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times eight
    sta temp + 2
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    rts
.endproc

; X = A8, without the byte above it: `ba_ax`.
.proc bm_ax
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; The write cursor at column A16 of line `BA_T1`: `ba_go`.
.proc bm_go
.a16
.i16
    clc
    adc BA_T1
    sta pick_table
    rts
.endproc
.a8
.i16
