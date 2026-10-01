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
.endproc
