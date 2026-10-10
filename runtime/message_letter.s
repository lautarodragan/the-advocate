.segment "FAR"
.a8
.i16

; --- the next letter of a text box, through the pair table -------------------
;
; The text block is written with DTE, dual tile encoding: a byte below
; `MESSAGE_PAIR_FIRST` is one letter —its index in the font, the ASCII
; minus 32— and one from there up stands for **two**, the ones in
; `message_pairs`, a single level deep. The converter chooses the pairs over
; the cartridge's texts; see `Pairs` in the event compiler's `messages.rs`.
;
; This is what `message_tick` asks for each letter, with a `jsl`: it lives in
; bank 1 because bank 0 has no room, and it costs the composer one `jsl` and
; one `rtl` a letter, nothing next to `compose_char`. `msg_ptr` is in the
; direct page and the rest goes with `f:`, so it does not depend on the data
; bank.

; The next letter in A, 8 bits: the second one of a pair, if one was left
; waiting, or the next byte's, advancing `msg_ptr`. Clobbers Y.
;
; The second letter waits in `FAR_MSG_SECOND` with bit 7 set, because the
; letter 0 is the space and "nothing waiting" has to be zero. `message_tick`
; clears it at the start of each line, and that is the only thing that makes
; it safe: the WRAM does not boot at zero —bsnes fills it with garbage, and
; the unused bytes around this one read $55 in the suite's core—.
.proc msg_letter
.a8
.i16
    lda f:MSG_DIGITS_N
    beq no_digit
    ; A digit of a variable's value still waiting: see `variable`.
    dec a
    sta f:MSG_DIGITS_N
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:MSG_DIGITS, x
    plx
    rtl
no_digit:
    lda f:FAR_MSG_SECOND
    beq read_byte
    and #$7F
    tay
    lda #0
    sta f:FAR_MSG_SECOND
    tya                         ; the letter: the flags are not looked at
    rtl
read_byte:
    ldy #0
    lda [msg_ptr], y
    ; One byte further, crossing banks: the same as `msg_ptr_next`, which is
    ; in bank 0 and is reached with `jsr` only from there.
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
    cmp #MESSAGE_VARIABLE
    beq variable
    cmp #MESSAGE_PAIR_FIRST
    bcc letter
    ; A pair: two bytes, the first letter and then the second, which a
    ; single 16-bit read brings, the first one in A and the second in B.
    rep #$20
.a16
    and #$00FF
    asl a
    phx
    tax
    lda f:message_pairs - MESSAGE_PAIR_FIRST * 2, x
    plx
    sep #$20
.a8
    xba
    ora #$80
    sta f:FAR_MSG_SECOND
    xba                         ; and the first one, to draw now
letter:
    rtl

    ; `\V[n]`: the value of the variable whose slot is the next byte, in
    ; decimal, with a minus sign if it is negative and no padding, which is
    ; what easyrpg's `PendingMessage::DefaultCommandInserter` writes. The
    ; characters go into `MSG_DIGITS` from the ones up, and are handed out
    ; from the top down: the first now, the rest on the next calls.
    ;
    ; The converter counted the value as **one** letter of the line —it does
    ; not know how many digits it will have—, so the line grows here by the
    ; rest. One that ends up past the window is cut by the composer's column
    ; cap, at the edge.
variable:
    ldy #0
    lda [msg_ptr], y            ; the slot
    rep #$20
.a16
    inc msg_ptr
    bne slot_same_bank
    sep #$20
.a8
    inc msg_ptr + 2
slot_same_bank:
    sep #$20
.a8
    phx
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per variable
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    ldx #0                      ; how many characters so far
    pha                         ; the value, for its sign at the end
    cmp #0                      ; the `ldx` left its own flags
    bpl digit
    eor #$FFFF
    inc a                       ; its magnitude: -32768 is 32768 unsigned, right
digit:
    sta f:WRDIVL                ; sixteen bits: the dividend, both bytes
    sep #$20
.a8
    lda #10
    sta f:WRDIVB                ; starts: sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda f:RDMPYL                ; the remainder, below ten
    clc
    adc #'0' - ' '              ; the font is the ASCII minus 32
    sta f:MSG_DIGITS, x
    inx
    rep #$20
.a16
    lda f:RDDIVL                ; the quotient: what is left
    bne digit
    pla                         ; the value again
    sep #$20
.a8
    bpl no_sign
    lda #'-' - ' '
    sta f:MSG_DIGITS, x
    inx
no_sign:
    txa                         ; how many there are, at most six
    dec a                       ; the one the converter already counted
    clc
    adc f:msg_length
    sta f:msg_length
    txa
    dec a
    sta f:MSG_DIGITS_N          ; the ones still to hand out
    lda f:MSG_DIGITS - 1, x     ; the top one: the sign, or the first digit
    plx
    rtl
.endproc

; The byte that stands for a variable's value in a line: `VARIABLE` in the
; event compiler's `messages.rs`, the last of the pair range.
MESSAGE_VARIABLE = $FF

; The characters of the variable's value being written, and how many are
; still to hand out: at most a sign and five digits, sixteen bits. $6120 to
; $6127, behind the call stack. **They do not travel in the save**, and
; `message_tick` clears the count at each line's start, like the second
; letter of a pair.
MSG_DIGITS_N = $7E6120
MSG_DIGITS   = $7E6121
.assert MSG_DIGITS + 6 <= $7E6128, error, "the digits of a variable overflow their RAM"
