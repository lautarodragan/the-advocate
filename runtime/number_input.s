.segment "FAR"
.a8
.i16

; --- `InputNumber`: the digits under a message ----------------------------------
;
; `op_number` opens the message's window, and when its lines are up the digits
; go on the line below them: it is `Window_Message::StartNumberInputProcessing`,
; which puts the number input at `y + contents_y` once the page's text is
; finished. The line is composed **by the same composer as the text**, from
; `NUMBER_LINE` in far RAM instead of from the text block: pointing `msg_ptr`
; there and asking for that single line is all it takes, and the lines below
; it come out blank, which is what the composer does with the lines a box does
; not have.
;
; The cursor is the choice's: a ">" in the column before the digit it is on,
; and a blank before the others, so the digits do not move when it moves.
; RM2k draws a frame around the digit; this way there is no sprite, no
; palette and no drawing, same as `ShowChoice`.
;
; The keys are `Window_NumberInput::Update`: up and down change the digit under
; the cursor and wrap from 9 to 0 and back, right and left move the cursor and
; wrap around, and A enters the number. B does nothing: an `InputNumber` cannot
; be cancelled. Each one counts on its **edge**, as in `choice_tick`; easyrpg
; repeats them while held (`IsRepeated`), and that is not done here.
;
; The number starts at zero with the cursor on the last digit, which is
; `SetNumber(0)` after each input and `ResetIndex` with no operator.
;
; Everything here goes with `f:` or through the direct page: it is reached
; with `jsl`, from bank 0, and the data bank is whatever the caller had.

NUMBER_ZERO   = '0' - 32            ; the font's letters are the ASCII minus 32
NUMBER_CURSOR = '>' - 32
; Not a space: the glyph after the tilde, a blank as wide as the cursor
; —`CURSOR_BLANK` in `rm2k-snes-text`—. With a variable-width font a space is
; narrower than a ">", and the digits would move with the cursor.
NUMBER_BLANK  = 127 - 32

; `op_number`, opening: Y on its operands —the variable's slot and how many
; digits— and it comes back with Y on the box, which `op_message` takes from
; there. Leaves `NUMBER_LINE` with all the digits at zero and the cursor on
; the last one, and `pick_cancel` at zero: the line is not drawn until the
; message's lines are.
.proc number_open
.a8
.i16
    lda pair_ev
    sta f:msg_owner             ; $FF if the foreground opens it
    lda #0
    sta f:msg_open
    lda #PICK_NUMBER
    sta pick_active
    sty pick_table              ; where the slot is: A reads it from here
    iny
    lda [code_ptr], y           ; how many digits
    iny
    sta pick_n
    dec a
    sta pick_sel                ; `ResetIndex`: the last digit
    stz pick_cancel
    lda pick_n
    asl a                       ; two letters per digit
    sta f:NUMBER_LINE
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
zeros:
    dex
    dex
    lda #NUMBER_ZERO
    sta f:NUMBER_LINE + 2, x
    cpx #0
    bne zeros
    jsr number_cursor
    rtl
.endproc

; Writes the cursor's column: the ">" before the digit at `pick_sel`, and a
; blank before the others. Keeps Y.
.proc number_cursor
.a8
.i16
    phy
    rep #$20
.a16
    lda pick_n                  ; and `pick_sel` in B, which the `and` drops
    and #$00FF
    tay                         ; the digit, counting down
    asl a
    tax                         ; and its two letters
    sep #$20
.a8
other:
    dex
    dex
    dey
    tya                         ; the digit, which is below 256
    cmp pick_sel
    beq here
    lda #NUMBER_BLANK
    bra put
here:
    lda #NUMBER_CURSOR
put:
    sta f:NUMBER_LINE + 1, x
    cpy #0
    bne other
    ply
    rts
.endproc

; Asks the composer for the digits' line alone: `pick_cancel` is how many
; lines the window has with it, and it is the last one. The lines below are
; composed blank, and the message's above it are left as they are.
;
; `msg_lines` takes that count and nothing more: the rest of the header —the
; auto-close and the pauses— was already read by `msg_start`.
.proc number_compose
.a8
.i16
    lda pick_cancel
    sta f:msg_lines
    dec a
    sta f:msg_line
    rep #$20
.a16
    lda #.loword(NUMBER_LINE)
    sta msg_ptr
    sep #$20
.a8
    lda #^NUMBER_LINE
    sta msg_ptr + 2
    lda #0
    sta f:msg_primed
    sta f:msg_upload
    lda #1
    sta f:msg_state
    rts
.endproc

; The number on the line, in `NUMBER_VALUE`: **saturated at 65535**, because
; the variables are sixteen bits. Six digits go up to 999999, and saturating
; is what keeps a number that does not fit from being equal to one that does
; —wrapping around, 100957 would be 35421, Drust Camp's password—. That is why
; the compiler does not take 65535 for an "equal": it would also be every
; number above it.
.proc number_value
.a8
.i16
    rep #$20
.a16
    lda #0
    sta f:NUMBER_VALUE
    ldx #0
other:
    lda f:NUMBER_VALUE
    cmp #6554                   ; times ten would go past 65535
    bcs saturates
    asl a
    sta f:NUMBER_VALUE          ; times two
    asl a
    asl a                       ; times eight
    clc
    adc f:NUMBER_VALUE
    sta f:NUMBER_VALUE          ; times ten
    lda f:NUMBER_LINE + 2, x    ; the digit, and the next cursor in B
    and #$00FF
    sec
    sbc #NUMBER_ZERO
    clc
    adc f:NUMBER_VALUE
    bcs saturates               ; 6553 times ten plus 6 or more
    sta f:NUMBER_VALUE
    inx
    inx
    sep #$20
.a8
    txa                         ; two letters per digit, below 256
    cmp f:NUMBER_LINE
    rep #$20
.a16
    bne other                   ; `rep` does not touch Z
    sep #$20
.a8
    rts
saturates:
.a16
    lda #$FFFF
    sta f:NUMBER_VALUE
    sep #$20
.a8
    rts
.endproc

; One frame of an open number input, from `choice_tick`. Returns A nonzero
; when the player pressed A: the variable is already written and the page
; carries on in this same frame, from the command after the `InputNumber`,
; which is where `op_number` left `ev_cur`.
;
; It does not use `temp`, which `events_tick` has busy; the edges go in
; `pick_edges`, as the choice's.
.proc number_tick
.a8
.i16
    lda f:msg_state
    beq composed
    lda #0                      ; a line is being composed: no keys
    rtl
composed:
    lda pick_cancel
    bne drawn
    ; The message's lines are up, and the digits go below them.
    lda f:msg_lines
    and #HEADER_LINES
    inc a
    sta pick_cancel
    bra compose
drawn:
    lda pad
    eor pad_prev
    and pad                     ; what was pressed **on this frame**
    sta pick_edges
    and #(PAD_UP | PAD_DOWN)
    beq no_digit
    rep #$20
.a16
    lda pick_sel
    and #$00FF
    asl a
    tax                         ; the digit under the cursor
    sep #$20
.a8
    lda pick_edges
    and #PAD_UP
    beq down
    lda f:NUMBER_LINE + 2, x
    inc a
    cmp #NUMBER_ZERO + 10
    bcc put_digit
    lda #NUMBER_ZERO            ; from 9 up is 0
    bra put_digit
down:
    lda f:NUMBER_LINE + 2, x
    dec a
    cmp #NUMBER_ZERO
    bcs put_digit
    lda #NUMBER_ZERO + 9        ; and from 0 down is 9
put_digit:
    sta f:NUMBER_LINE + 2, x
    bra compose
no_digit:
    lda pick_edges
    and #PAD_RIGHT
    beq no_right
    lda pick_sel
    inc a
    cmp pick_n
    bcc moved
    lda #0                      ; from the last one, right wraps around
    bra moved
no_right:
    lda pick_edges
    and #PAD_LEFT
    beq no_left
    lda pick_sel
    bne one_left
    lda pick_n                  ; and from the first one, left does too
one_left:
    dec a
moved:
    sta pick_sel
    jsr number_cursor
compose:
    jsr number_compose
    lda #0
    rtl
no_left:
    lda pad_a
    beq nothing
    lda pad_a_prev
    bne nothing                 ; it was already held: not an edge
    jsr number_value
    ldy pick_table
    lda [code_ptr], y           ; the variable's slot
    rep #$20
.a16
    and #VAR_SLOT
    asl a                       ; two bytes per variable, as `var_write`
    tax
    lda f:NUMBER_VALUE
    sta f:FAR_LENGTH + FAR_VARIABLES, x
    sep #$20
.a8
    ; The refresh **always**, as `Window_Message::InputNumber`, which calls
    ; `Game_Map::SetNeedRefresh(true)` and not the variable's
    ; `SetNeedRefreshForVarChange`.
    lda #1
    sta f:refresh
    stz pick_active
    lda #0
    sta f:msg_open              ; and with that `flush_video` turns HDMA off
    ; The A is consumed, as the message's: the page goes on in this frame and
    ; the hero must not see it as the action key.
    lda pad_a
    sta pad_a_prev
    lda #1
    rtl
nothing:
    lda #0
    rtl
.endproc
