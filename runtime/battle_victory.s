.segment "FAR2"

; The window's lines: the party's, which is what it covers.
BA_VIC_LINES = BA_PARTY_MAX

; --- what the victory tells ---------------------------------------------------
;
; `ProcessSceneActionVictory` from `Scene_Battle_Rpg2k`: on winning, the
; message window says the victory term and the experience gained, and then one
; page for each actor who leveled up, with "<name> LEVEL <n> achieved!" and
; what they learned. Each page waits for A, like a map message. All the words
; come from the LDB —`victory`, `exp_received`, `level`, `level_up`,
; `skill_learned`— and the assembly is the one in `game_message_terms.cpp` for
; English RM2k, without placeholders: see `screens.level_line` and its
; sisters, which are what the converter uses to enforce that they fit.
;
; In RM2k it is the usual message window, at the bottom, **covering the
; party**; here too, since 2026-10-04: the band below the scene, from its
; first line, like the message of a troop page (`ba_page_message`). Until
; then it went on the party's four lines.
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
; randomness. Clobbers `BA_S0` to `BA_S2`, `BA_T*`, A, X and Y.
.proc ba_vic_start
.a8
.i16
    stz BA_S0
slot:
    lda BA_S0
    cmp #BA_PARTY_MAX
    bcs recorded
    jsr ba_vic_level
    pha
    lda BA_S0
    jsr ba_ax
    pla
    sta BA_VIC_BEFORE, x
    inc BA_S0
    bra slot
recorded:
    jsr ba_exp_allocate
    jsr ba_vic_gold
    jsr ba_vic_drop
    lda #$FF
    sta BA_VIC_ACTOR
    stz BA_VIC_SKIP
    stz BA_VIC_MORE
    rts
.endproc

; The troop's gold, to the party: `Game_Party::GainGold`, capped at GOLD_MAX.
; It does not check whether the troop gives zero: adding zero changes nothing.
.proc ba_vic_gold
.a8
.i16
    lda BA_TROOP_K
    cmp #$FF
    beq ready                   ; a troop the cartridge does not carry
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:troop_gold, x
    ldy #2                      ; the gold: see `ba_no_hidden`
    jsr ba_no_hidden
    sta comp_or01
    sep #$20
.a8
    stz comp_or01 + 2
    jsl f:gold_add
ready:
    rts
.endproc

; The troop's total in A16 minus that of the enemies still hidden: a victory
; with one that never appeared —the Rat King falling before calling its rats—
; does not give its experience or its gold, because `GetExp` and `GetMoney`
; add up **the dead** and a hidden one did not die. Y = 0 the experience, 2
; the gold. Returns with A16. Clobbers `BA_T0`, `BA_T2`, X and Y.
.proc ba_no_hidden
.a16
.i16
    sta BA_T2
    sep #$20
.a8
    stz BA_T0                   ; the place in the troop
other:
    lda BA_T0
    cmp BA_KID
    bcs ready
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HIDDEN
    beq next
    lda BA_T0
    jsr ba_member_x
    lda f:troop_member, x       ; the enemy, as a place in the tables
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    cpy #0
    bne is_gold
    lda BA_T2
    sec
    sbc f:enemy_exp, x
    bra subtracted
is_gold:
    lda BA_T2
    sec
    sbc f:enemy_gold, x
subtracted:
    sta BA_T2
    sep #$20
.a8
next:
    inc BA_T0
    bra other
ready:
    rep #$20
.a16
    lda BA_T2
    rts
.endproc

; What the enemies drop: `Game_EnemyParty::GenerateDrops`. For each one, in
; troop order, if it has an item it **rolls** `ba_pct` with its chance —the
; hundred percent one too, which is what `Rand::ChanceOf` does—, and if it
; comes up the item goes to the inventory, capped at ITEM_MAX like
; `Game_Party::AddItem`, and its `k` to `BA_DROP_K` so the page can tell it.
; The rolls go in the order of `roll_drops`, the model's. Everyone in the
; troop is dead —which is what `IsDead` asks for— except those still hidden.
; Clobbers `BA_S0` to `BA_S2`, `BA_T*`, A, X and Y.
.proc ba_vic_drop
.a8
.i16
    stz BA_DROP_N
    stz BA_S0                   ; the place in the troop
other:
    lda BA_S0
    cmp BA_KID
    bcc has
    rts
has:
    ; One that is still hidden did not die, and `GenerateDrops` only rolls for
    ; the dead: no roll.
    lda BA_S0
    clc
    adc #BA_PARTY_MAX
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HIDDEN
    beq to_view
    jmp next
to_view:
    ; The enemy, as a place in the tables: the same path as `ba_build`.
    lda BA_S0
    jsr ba_member_x
    lda f:troop_member, x
    sta BA_S2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:enemy_drop, x
    sta BA_S1                   ; the LDB item, or 0
    sep #$20
.a8
    beq next                    ; leaves nothing: no roll
    lda BA_S2
    jsr ba_ax
    lda f:enemy_drop_pct, x
    jsr ba_pct
    beq next
    ldx BA_S1
    lda FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs full
    inc a
    sta FAR_ITEMS, x
full:
    lda f:item_k, x             ; the converter enforces that it is carried
    pha
    lda BA_DROP_N
    jsr ba_ax
    pla
    sta BA_DROP_K, x
    inc BA_DROP_N
next:
    inc BA_S0
    bra other
.endproc

; The current level of the actor in party slot A8, or 0 if the slot is empty
; or its actor has no experience. Clobbers X.
.proc ba_vic_level
.a8
.i16
    cmp BA_NACTORS
    bcs nothing
    jsr ba_x
    lda BA_ONE + BA_FLAGS, x
    and #BAF_HAS
    beq nothing
    lda BA_ONE + BA_NUMBER, x
    jsr ba_ax
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
; Clobbers X and `BA_T0`.
.proc ba_vic_level_up
.a8
.i16
    pha
    jsr ba_vic_level
    sta BA_T0
    pla
    jsr ba_ax
    lda BA_VIC_BEFORE, x
    beq no                      ; no experience, or nobody
    cmp BA_T0
    bcs no                      ; the same level as before
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A on the end screen: if another page is left, it sets it up and returns A8
; nonzero; if not, 0, and the battle closes. A defeat or an escape have no
; pages. Clobbers X and `BA_T0`.
.proc ba_vic_next
.a8
.i16
    lda BA_RESULT
    cmp #BA_VICTORY
    bne none
    lda BA_VIC_MORE
    beq other_actor
    ; The skills that did not fit go on in another page of the same actor,
    ; which is what RM2k's window does with a message of more than four lines.
    lda BA_VIC_NEXT
    sta BA_VIC_SKIP
    lda #1
    rts
other_actor:
    stz BA_VIC_SKIP
    lda BA_VIC_ACTOR
seek:
    inc a                       ; from $FF, the first page, it goes to slot 0
    cmp BA_NACTORS
    bcs none
    sta BA_VIC_ACTOR
    jsr ba_vic_level_up
    cmp #0                      ; `jsr` does not keep the flags from the `lda` inside
    bne has
    lda BA_VIC_ACTOR
    bra seek
has:
    lda #1
    rts
none:
    lda #0
    rts
.endproc

; Z at 0 if what the screen shows is a victory: the battle ended won and the
; message is the victory's. `ba_compose` asks it before drawing the party.
.proc ba_vic_on_screen
.a8
.i16
    lda BA_MTYPE
    cmp #BA_MSG_VICTORY
    bne no
    lda BA_MODE
    cmp #BA_M_MESSAGE
    beq if
    cmp #BA_M_END
    beq if
no:
    lda #0
    rts
if:
    lda #1
    rts
.endproc

; The current page in the message window. `ba_compose` calls it with `jmp`,
; so its `rts` is the composer's: nothing else goes on the screen. Clobbers
; `BA_S0` to `BA_S4`, `BA_T*`, A, X and Y.
.proc ba_vic_message
.a8
.i16
    stz temp + 1                ; white
    rep #$20
.a16
    lda #BA_PAGE_MSG_POS0
    sta BA_T1
    lda #BA_PAGE_MSG_DX
    jsr ba_go
    sep #$20
.a8
    lda BA_VIC_ACTOR
    cmp #$FF
    beq first
    jmp from_actor
first:
    ; The lines of the victory message, four per page: see `ba_vic_line`,
    ; which counts the ones already shown.
    stz BA_VIC_MORE
    lda BA_VIC_SKIP
    sta BA_VIC_NEXT
    stz BA_S3
    stz BA_S4
    ; The victory term, on the lines the converter split it into —see
    ; `victory_lines` in `rm2k-snes-battle`—.
    jsr ba_vic_line
    bcc no_v1
    ldx #BA_TXT_VICTORY
    jsr ba_finished
no_v1:
    lda #BA_VIC_FINISHED_N      ; not with `.if`: the constant comes later
    cmp #2
    bcc line
    jsr ba_vic_line
    bcc line
    ldx #BA_TXT_VICTORY2
    jsr ba_finished
line:
    ; And the experience, if any: easyrpg's `if (exp > 0)`. The gold goes the
    ; same way, `if (money > 0)`.
    lda BA_TROOP_K
    cmp #$FF
    bne with_troop
    rts
with_troop:
    rep #$20
.a16
    and #$00FF
    asl a
    sta BA_S1                   ; the troop's place in the word-sized tables
    tax
    lda f:troop_exp, x
    ldy #0                      ; without those that stayed hidden
    jsr ba_no_hidden
    sep #$20                    ; `sep` does not touch Z
.a8
    beq no_exp
    jsr ba_vic_line
    bcc no_exp
    rep #$20
.a16
    ldx BA_S1
    lda f:troop_exp, x
    ldy #0
    jsr ba_no_hidden
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_number
    ldx #BA_TXT_EXP_RECEIVED
    jsr ba_finished
no_exp:
    rep #$20
.a16
    ldx BA_S1
    lda f:troop_gold, x
    ldy #2
    jsr ba_no_hidden
    sep #$20
.a8
    beq no_gold
    jsr ba_vic_line
    bcc no_gold
    ldx #BA_TXT_GOLD_A
    jsr ba_finished
    lda #$20
    jsl f:ba_t_glyph
    rep #$20
.a16
    ldx BA_S1
    lda f:troop_gold, x
    ldy #2
    jsr ba_no_hidden
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_number
    ldx #BA_TXT_CURRENCY
    jsr ba_finished
    ldx #BA_TXT_GOLD_B
    jsr ba_finished
no_gold:
    ; And one line per item, in the order they came up.
    stz BA_S0
item:
    lda BA_S0
    cmp BA_DROP_N
    bcs all_ready
    jsr ba_vic_line
    bcc other_item
    lda BA_S0
    jsr ba_ax
    lda BA_DROP_K, x
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; times three: `3k` is the item's name
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_text
    ldx #BA_TXT_OBTAINED
    jsr ba_finished
other_item:
    inc BA_S0
    bra item
all_ready:
    rts

from_actor:
    ; "<name> LEVEL <n> achieved!", only on its first page.
    lda #1
    sta BA_S3                   ; lines written, the top one already counted
    lda BA_VIC_SKIP
    bne no_level
    lda BA_VIC_ACTOR
    jsr ba_name
    lda #$20
    jsl f:ba_t_glyph
    ldx #BA_TXT_LEVEL
    jsr ba_finished
    lda #$20
    jsl f:ba_t_glyph
    lda BA_VIC_ACTOR
    jsr ba_vic_level
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_number
    ldx #BA_TXT_LEVEL_UP
    jsr ba_finished
    bra skills
no_level:
    stz BA_S3                   ; the continuation starts on the top one
skills:
    ; And "<skill> acquired!" for each one taught by the levels it went
    ; through, level by level like `LearnLevelSkills(old_level + 1,
    ; new_level)`. `BA_VIC_SKIP` is the ones already shown on earlier pages.
    ;
    ; **It says every one the table teaches at those levels**, and RM2k only
    ; the ones it did not know —`LearnSkill` does not announce it if it was
    ; already there—: the two differ only if a `ChangeSkills` taught it one
    ; earlier that a level teaches later, and in ABL none does. `exp_add`
    ; already set the bits, so here there is no way to know which were there.
    stz BA_VIC_MORE
    lda BA_VIC_SKIP
    sta BA_VIC_NEXT
    stz BA_S4                   ; the ones already seen, written or skipped
    lda BA_VIC_ACTOR
    jsr ba_vic_level
    sta BA_S2                   ; up to which level
    lda BA_VIC_ACTOR
    jsr ba_ax
    lda BA_VIC_BEFORE, x
    sta BA_S0                   ; the level being looked at, from the previous one + 1
    lda BA_VIC_ACTOR
    jsr ba_x
    lda BA_ONE + BA_NUMBER, x
    sta BA_S0 + 1               ; the LDB actor
level:
    lda BA_S0
    cmp BA_S2
    bcc other_level
    rts                         ; the current one has been looked at already
other_level:
    inc BA_S0
    ; The actor's pairs: `skill_pair_init` and `skill_pair_n`, like `learn_from_level`.
    lda BA_S0 + 1
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:skill_pair_init, x
    sta BA_S1                   ; the pair being looked at
    sep #$20
.a8
    lda BA_S0 + 1
    jsr ba_ax
    lda f:skill_pair_n, x
    sta BA_S2 + 1               ; how many it has left
    beq level
pair:
    ldx BA_S1
    lda f:skill_pair_level, x
    cmp BA_S0
    bne next
    inc BA_S4
    lda BA_S4
    cmp BA_VIC_SKIP
    beq next                    ; shown on an earlier page
    bcc next
    lda BA_S3
    cmp #BA_VIC_LINES
    bcc enters
    lda #1                      ; does not fit: goes on in another page
    sta BA_VIC_MORE
    bra ready
enters:
    inc BA_S3
    inc BA_VIC_NEXT
    lda BA_S3
    cmp #1
    beq up                      ; the first one of a continuation
    jsr ba_vic_text_line
up:
    rep #$20
.a16
    lda BA_S1
    asl a
    tax
    lda f:skill_pair_learns_txt, x
    tax
    sep #$20
.a8
    jsr ba_finished
    ldx #BA_TXT_LEARNED
    jsr ba_finished
next:
    rep #$20
.a16
    inc BA_S1
    sep #$20
.a8
    dec BA_S2 + 1
    beq other
    jmp pair
other:
    jmp level
ready:
    rts
.endproc

; The next line of the first page, if it belongs on this one: C at 1 and the
; position set, or C at 0 if it was shown on an earlier page —the first
; `BA_VIC_SKIP`— or it does not fit, and then `BA_VIC_MORE` is left set. It
; keeps the count in `BA_S4`, the ones seen, and `BA_S3`, the ones written,
; which `ba_vic_message` zeroes. It is the same count as an actor's skills,
; further down.
.proc ba_vic_line
.a8
.i16
    inc BA_S4
    lda BA_S4
    cmp BA_VIC_SKIP
    beq no                      ; shown on an earlier page
    bcc no
    lda BA_S3
    cmp #BA_VIC_LINES
    bcc enters
    lda #1                      ; does not fit: goes on in another page
    sta BA_VIC_MORE
no:
    clc
    rts
enters:
    inc BA_VIC_NEXT
    lda BA_S3
    beq up                      ; the page's first one is already set
    jsr ba_vic_text_line
up:
    inc BA_S3
    sec
    rts
.endproc

; The line below the one being written, from its start.
.proc ba_vic_text_line
.a8
.i16
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_ROW_BYTES
    sta BA_T1
    lda #BA_PAGE_MSG_DX
    jsr ba_go
    sep #$20
.a8
    rts
.endproc

; `BA_T0` without leading spaces, up to five digits: a troop's experience does
; not fit in `scr_number`'s three. Clobbers A, X, Y and `BA_T0`.
.proc ba_vic_number
.a8
.i16
    stz BA_T2                   ; whether a digit has been written already
    ldx #0                      ; which power of ten
power:
    ldy #0                      ; the digit
    rep #$20
.a16
remain:
    lda BA_T0
    cmp f:powers, x             ; with `f:`: the data bank is $7E
    bcc digit
    sbc f:powers, x             ; C comes from the comparison
    sta BA_T0
    iny
    bra remain
digit:
    sep #$20
.a8
    tya
    ora BA_T2
    beq zero_ahead
    sta BA_T2
    tya
    clc
    adc #$30
    phx
    jsl f:ba_t_glyph
    plx
zero_ahead:
    inx
    inx
    cpx #8
    bcc power
    lda BA_T0                   ; the units, always
    clc
    adc #$30
    jsl f:ba_t_glyph
    rts
powers:
    .word 10000, 1000, 100, 10
.endproc
