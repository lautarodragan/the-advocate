; --- an actor's name, which `ChangeHeroName` changes ------------------------
;
; The names an actor can have are all known when building: the database's
; and the literals of the game's `ChangeHeroName`s, which the event compiler
; numbers from one —`renames` in its indices— and the converter writes as
; texts of the cartridge's text table, `name_txt`, and as rows of
; `slot_actor_text`, from `SLOT_TEXT_ROWS` on. So what changes at run time is
; one byte per actor that some `ChangeHeroName` renames —`name_actor` says
; which, in order—: which of those names it carries, 0 the database's.
;
; Everything that draws a name asks here: the battle, the equipment and
; skills screens and the level up through `actor_name_txt`, the menu and the
; slot screen through `actor_name_row`, and the `\N[n]` of a message through
; `msg_name_mark`. A cartridge whose game renames no one carries no byte and
; no table, and each of these answers the database's name.

.if ::NAME_SLOTS > 0
.pushseg
.segment "FARBSS"
; Which rename each renamed actor carries, by its place in `name_actor`: 0
; the database's name, k the k-th of `name_txt`. It travels in the save,
; before the experience —see `save_table`—, and reset clears it.
ACTOR_NAME: .res NAME_SLOTS
.popseg
.endif

; Where the names are in a saved game, for the slot screen, which shows the
; saved leader's: `NAME_SLOTS` bytes —`SAVE_BYTES` adds them— right before
; the experience, which goes last.
SAVE_NAMES = SAVE_BYTES - EXP_K * 4 - NAME_SLOTS

; How many letters of a name a message writes at most: past the window's
; width it is cut anyway, and this keeps the line's length in its byte.
NAME_LETTERS_MAX = 32

.pushseg
; In `FAR3`, the fourth code bank: every door in is a `jsl` or a `jml`, and
; it calls nothing in bank 1. It was in bank 1, which had more room than
; `FAR2` —Sunset over Imdahl, which renames its hero, overflowed `FAR2` by
; fourteen bytes with it there—, until it and the shop's party together
; overflowed bank 1 in A Blurred Line's MSU test cartridge (2026-10-15).
.segment "FAR3"

; X16: an actor times two, as `actor_txt` is indexed. Returns in A16 the
; text number of the name it carries now, or $FFFF if the cartridge has no
; text for it. It is `lda f:actor_txt, x` with the renames, and it keeps X
; and Y. Any data bank.
.proc actor_name_txt
.a16
.i16
.if ::NAME_SLOTS > 0
    phx
    txa
    lsr a                       ; the actor
    jsr name_place
    bcs own
    lda f:ACTOR_NAME, x
    and #$00FF
    beq own                     ; the database's
    asl a
    tax
    lda f:name_txt - 2, x       ; renames count from one
    plx
    rtl
own:
    plx
.endif
    lda f:actor_txt, x
    rtl
.endproc

; A8: an actor below `SLOT_ACTORS_N`. Returns in A8 the row of
; `slot_actor_text` its name is in: its own, or a rename's. `_now` is the
; name it carries, which the menu shows; `_saved`, the one in the saved game
; of slot `slot`, which the slot screen shows —RM2k's save screen shows the
; leader's name as it was saved—. Both keep X and Y. Any data bank.
.proc actor_name_row_saved
.a8
.i16
.if ::NAME_SLOTS > 0
    phx
    pha
    jsr name_place_a8
    bcs own
    phb
    lda slot
    clc
    adc #SRAM_BANK
    pha
    plb
    lda SRAM_DATA + SAVE_NAMES, x ; the data bank is the slot's: absolute
    plb
    cmp #0                      ; `plb` left the flags of the bank
    bra row
own:
    lda #0
row:
    ; A: the rename, 0 none.
    beq database
    clc
    adc #SLOT_TEXT_ROWS - 1
    sta 1, s                    ; over the actor
database:
    pla                         ; the actor's own row, or the rename's
    plx
.endif
    rtl
.endproc

.proc actor_name_row_now
.a8
.i16
.if ::NAME_SLOTS > 0
    phx
    pha
    jsr name_place_a8
    bcs own
    lda f:ACTOR_NAME, x
    bra which
own:
    lda #0
which:
    jmp actor_name_row_saved::row
.else
    rtl
.endif
.endproc

.if ::NAME_SLOTS > 0
; A8: an actor. Returns its place in `name_actor` in X, with C clear, or C set
; if no `ChangeHeroName` renames it. Keeps A.
.proc name_place_a8
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    jsr name_place
    sep #$20
.a8
    pla                         ; `pla` keeps C
    rts
.endproc

; A16: an actor. Returns its place in `name_actor` in X, with C clear, or C
; set. Clobbers A.
.proc name_place
.a16
.i16
    ldx #0
other:
    cpx #NAME_SLOTS * 2
    bcs none
    cmp f:name_actor, x
    beq found
    inx
    inx
    bra other
found:
    txa
    lsr a                       ; an even number: C clear
    tax
none:
    rts
.endproc
.endif

; `ChangeHeroName`: OP_CHANGE_NAME's two operands —the actor's place in
; `name_actor` and the rename, from one—, read with Y at them, and Y past
; them on return. A cartridge with no renames never emits it.
.proc change_name
.a8
.i16
.if ::NAME_SLOTS > 0
    lda [code_ptr], y           ; the place
    iny
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda [code_ptr], y           ; the rename
    sta f:ACTOR_NAME, x
.endif
    iny
    rtl
.endproc

; No one renamed: at reset, before loading the save, which overwrites it.
.proc actor_names_clear
.a8
.i16
.if ::NAME_SLOTS > 0
    ldx #NAME_SLOTS - 1
other:
    lda #0
    sta f:ACTOR_NAME, x
    dex
    bpl other
.endif
    rtl
.endproc

; --- a name in a message -------------------------------------------------------
;
; `MESSAGE_NAME`, from `msg_letter`, which jumps here with `msg_ptr` on the
; actor that follows it: 0 the leader. Answers like `msg_letter` —the next
; letter in A, with an `rtl`— and keeps X, which is the composer's count.
;
; The name's letters are handed out by pointing `msg_ptr` at its text, in the
; cartridge's text table, and coming back to the line after the last one:
; where the line goes on waits in `MSG_DIGITS`, which a name does not need,
; and `MSG_DIGITS_N` counts the letters left with bit 7 set, so that
; `msg_letter` tells them from digits. `message_tick` clears it at each
; line's start, like the digits.
;
; The converter counted the name as **one** letter of the line, so the line
; grows here by the rest, as with a variable's digits, and the composer cuts
; at the window's edge what passes it: RM2k does not wrap a line a name makes
; too long either. An empty name —the leader of an empty party, which
; easyrpg writes as nothing— is not a letter, as a wait is not: the line
; loses the one counted and the next letter goes.
.proc msg_name_mark
.a8
.i16
    ldy #0
    lda [msg_ptr], y            ; the actor
    rep #$20
.a16
    inc msg_ptr
    bne same_bank
    sep #$20
.a8
    inc msg_ptr + 2
same_bank:
    sep #$20
.a8
    phx
    cmp #0                      ; the `sep` left its own flags
    bne by_number
    lda party_n
    beq nothing                 ; no one leads
    lda party
by_number:
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    jsl f:actor_name_txt
    cmp #$FFFF
    sep #$20
.a8
    beq nothing                 ; no text for it
    tax
    lda f:item_txt_n, x
    beq nothing
    cmp #NAME_LETTERS_MAX + 1
    bcc fits
    lda #NAME_LETTERS_MAX
fits:
    pha
    dec a                       ; the one the converter already counted
    clc
    adc f:msg_length
    bcc in_byte
    lda #$FF                    ; past the edge long before this
in_byte:
    sta f:msg_length
    pla
    ora #$80                    ; letters of a name, and not digits
    sta f:MSG_DIGITS_N
    ; Where the line goes on, and the name's text in its place.
    rep #$20
.a16
    lda msg_ptr
    sta f:MSG_DIGITS
    sep #$20
.a8
    lda msg_ptr + 2
    sta f:MSG_DIGITS + 2
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    plx
    jml f:msg_letter            ; its first letter
nothing:
    plx
    lda f:msg_length            ; it is not a letter
    dec a
    sta f:msg_length
    lda f:msg_col
    cmp f:msg_length
    bcs blank
    jml f:msg_letter
blank:
    lda #0                      ; a space, which draws nothing: the line is over
    rtl
.endproc

; A name's next letter, from `msg_letter`, with `MSG_DIGITS_N` in A: see
; `msg_name_mark`. After the last one `msg_ptr` goes back to the line.
; Clobbers Y.
.proc msg_name_letter
.a8
.i16
    dec a                       ; one fewer to hand out
    cmp #$80
    bne more
    lda #0                      ; this is the last
more:
    sta f:MSG_DIGITS_N
    ldy #0
    lda [msg_ptr], y
    sec
    sbc #' '                    ; the font is the ASCII minus 32
    pha
    rep #$20
.a16
    inc msg_ptr
    bne same_bank
    sep #$20
.a8
    inc msg_ptr + 2
same_bank:
    sep #$20
.a8
    lda f:MSG_DIGITS_N
    bne still
    rep #$20
.a16
    lda f:MSG_DIGITS
    sta msg_ptr
    sep #$20
.a8
    lda f:MSG_DIGITS + 2
    sta msg_ptr + 2
still:
    pla                         ; the letter: the flags are not looked at
    rtl
.endproc

.popseg
