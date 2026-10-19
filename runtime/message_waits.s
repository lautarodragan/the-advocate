; In `FAR3`, the fourth code bank, since 2026-10-19: every door in is a
; `jsl` or a `jml` and every table goes with `f:`, so it runs from any bank,
; and `FAR2` had no room left for the special items in battle in Sunset
; over Imdahl, whose painted maps carry more code there.
.segment "FAR3"
.a8
.i16

; --- the waits in the middle of a box: `\.`, `\|` and `\!` --------------------
; RM2k types a box letter by letter, and an escape in the middle of it stops
; the typing: `\.` 16 frames, `\|` 61 and `\!` until a key —easyrpg's
; `Window_Message::UpdateMessage`—. What was typed stays on screen meanwhile.
;
; The console does not type: the composer builds the box a line at a time
; off screen, and the window appears when it has all four. So a wait is done
; by **cutting the box there**: the line ends at the wait and the ones below
; come out blank —the composer already primes and uploads the lines a box
; does not carry—, the window appears with what there is, the wait runs,
; and then the box is composed again **from the start of the line that was
; cut**, which draws its first stretch again where it already was and goes
; on. The lines above it are not touched: they are already in VRAM.
;
; What that costs, and why it is this and not something else: the text
; buffer is one line —`text_buf`—, and blanking the lines below while
; keeping the one half drawn would ask for a second buffer, or for uploads
; straight from ROM in the vblank. Drawing the cut line again is a few
; frames of the composer, and needs nothing new in bank 0 but the hooks.
;
; A box that carries waits says so in its first letter, `MESSAGE_WAIT` with
; `MESSAGE_WAIT_ANNOUNCE` —the converter puts it there; see `WAIT` in the
; event compiler's `messages.rs`—: from then on `MSG_WAIT_HOLD` holds the
; page, so the box's tail —its `\|` pauses and its `\^`— counts from when the
; last stretch is on screen, as in RM2k, and not from when the page asked for
; the box.
;
; Each wait counts in its line's length like a letter, and is taken off it
; here: a wait at the end of a line, after its last letter, is still read.

; Where the box is. 0: no wait in it. `HOLD_DRAWING`: it carries waits and is
; being composed, or a stretch after a wait —the page holds until it is on
; screen—. `HOLD_WAITING`: it was cut at a wait and is on screen, or about
; to be, waiting.
HOLD_DRAWING = 2
HOLD_WAITING = 1

.pushseg
.segment "FARBSS"
MSG_WAIT_HOLD:  .res 1
; How many waits of the line being composed are already done, and are passed
; over without stopping: the line is composed again from its start after
; each one. `msg_start` clears it together with `MSG_WAIT_HOLD`, in one
; sixteen-bit store, so it goes right after it.
MSG_WAIT_SKIP:  .res 1
MSG_WAIT_SEEN:  .res 1      ; the waits read in this line so far
MSG_WAIT_KIND:  .res 1      ; frames, or `MESSAGE_WAIT_KEY`
MSG_WAIT_LEFT:  .res 1      ; the frames still to wait
MSG_WAIT_LINES: .res 1      ; the box's header, before cutting it
MSG_WAIT_LINE:  .res 1      ; the line that was cut
MSG_WAIT_PTR:   .res 3      ; where the line being composed starts: its length
.popseg
.assert MSG_WAIT_SKIP = MSG_WAIT_HOLD + 1, error, "msg_start clears MSG_WAIT_HOLD and MSG_WAIT_SKIP with one store"

; What follows `MESSAGE_WAIT`: the frames, a key, or the announcement. See
; `WAIT_KEY` and `WAIT_ANNOUNCE` in the event compiler's `messages.rs`.
MESSAGE_WAIT_KEY      = 0
MESSAGE_WAIT_ANNOUNCE = $FF

; The start of a line, from `message_tick`, before its length is read: the
; letter pending from a pair and the digits of a variable are cleared —this
; is the only place, see `msg_letter`—, and where the line starts is kept,
; to compose it again after a wait. Not while a cut box is being finished:
; its lines below the cut are blank, and the one to go back to is the cut
; one.
.proc msg_line_start
.a8
.i16
    lda #0
    sta f:FAR_MSG_SECOND
    sta f:MSG_DIGITS_N
    sta f:MSG_WAIT_SEEN
    lda f:MSG_WAIT_HOLD
    cmp #HOLD_WAITING
    beq done
    rep #$20
.a16
    lda msg_ptr
    sta f:MSG_WAIT_PTR
    sep #$20
.a8
    lda msg_ptr + 2
    sta f:MSG_WAIT_PTR + 2
done:
    rtl
.endproc

; `MESSAGE_WAIT`, from `msg_letter`, which jumps here with `msg_ptr` on the
; byte that says which. Answers like `msg_letter` —the next letter in A,
; with an `rtl`— and keeps X, which is the composer's count.
;
; A wait already done goes on to the next letter; a new one cuts the box:
; the line ends where it is —its length becomes the letters already
; drawn— and so do the lines, so the ones below come out blank. What it
; answers then is a space, which draws nothing: the composer counts it and
; finds the line over.
.proc msg_wait_mark
.a8
.i16
    ldy #0
    lda [msg_ptr], y            ; which wait
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
    pha
    lda f:msg_length            ; it is not a letter
    dec a
    sta f:msg_length
    pla
    cmp #MESSAGE_WAIT_ANNOUNCE
    bne a_wait
    lda #HOLD_DRAWING
    sta f:MSG_WAIT_HOLD
    bra next
a_wait:
    pha
    lda f:MSG_WAIT_SEEN
    inc a
    sta f:MSG_WAIT_SEEN
    lda f:MSG_WAIT_SKIP
    beq cut
    dec a                       ; one already waited for: on
    sta f:MSG_WAIT_SKIP
    pla
next:
    ; The next letter, or a space if the line ended with the wait.
    lda f:msg_col
    cmp f:msg_length
    bcs blank
    jml f:msg_letter
cut:
    pla
    sta f:MSG_WAIT_KIND
    sta f:MSG_WAIT_LEFT
    lda f:MSG_WAIT_SEEN
    sta f:MSG_WAIT_SKIP         ; the ones to pass over when composing it again
    lda f:msg_col
    sta f:msg_length
    lda f:msg_lines
    sta f:MSG_WAIT_LINES
    and #($FF ^ HEADER_LINES)   ; the auto-close and the pauses stay
    pha
    lda f:msg_line
    sta f:MSG_WAIT_LINE
    inc a                       ; the lines up to this one, and no more
    ora 1, s
    sta f:msg_lines
    pla
    lda #HOLD_WAITING
    sta f:MSG_WAIT_HOLD
blank:
    lda #0                      ; a space: draws nothing
    rtl
.endproc

; Once per frame, from the top of `message_tick`: the wait of a cut box, and
; going back to composing it when it is over.
;
; It counts from when the stretch is on screen —`msg_state` back at zero,
; which `flush_video` does when it turns the window on—, not from the cut:
; in RM2k the wait starts once what comes before it is typed. A does not
; skip a timed wait, as in RM2k, where `wait_count` goes before
; `WaitForInput`; and `\!` takes A or B, Decision or Cancel, and consumes
; the edge, so that the box's own end does not take it too.
;
; With `HOLD_DRAWING` it only looks for the end: the box, or its stretch
; after the last wait, finished composing and is on screen, and the page can
; take its tail.
.proc msg_hold_tick
.a8
.i16
    lda f:MSG_WAIT_HOLD
    beq done
    cmp #HOLD_WAITING
    beq waiting
    lda f:msg_state
    bne done                    ; still composing
    lda #0
    sta f:MSG_WAIT_HOLD
done:
    rtl
waiting:
    lda f:msg_state
    bne done                    ; the stretch is not on screen yet
    lda f:MSG_WAIT_KIND
    beq a_key
    lda f:MSG_WAIT_LEFT
    dec a
    sta f:MSG_WAIT_LEFT
    bne done
    bra resume
a_key:
    lda pad_a
    beq not_a
    lda pad_a_prev
    bne not_a                   ; it was already held: not an edge
    lda pad_a
    sta pad_a_prev
    bra resume
not_a:
    lda pad
    eor pad_prev
    and pad
    and #PAD_B
    beq done
    lda pad_prev
    ora #PAD_B
    sta pad_prev
resume:
    ; The cut line again from its start, with the header it had: the
    ; window stays up, and what was drawn is drawn again where it already
    ; was.
    lda f:MSG_WAIT_LINES
    sta f:msg_lines
    lda f:MSG_WAIT_LINE
    sta f:msg_line
    rep #$20
.a16
    lda f:MSG_WAIT_PTR
    sta msg_ptr
    sep #$20
.a8
    lda f:MSG_WAIT_PTR + 2
    sta msg_ptr + 2
    lda #0
    sta f:msg_primed
    sta f:msg_upload
    lda #HOLD_DRAWING
    sta f:MSG_WAIT_HOLD
    lda #1
    sta f:msg_state             ; composing
    rtl
.endproc
