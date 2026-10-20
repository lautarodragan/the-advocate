; In `FAR3`, the fourth code bank: every door in is a `jsl` or a `jml` and
; every table goes with `f:`, so it runs from any bank.
.segment "FAR3"
.a8
.i16

; --- the box typed: its pace, its waits, its colour ---------------------------
; RM2k types a box letter by letter in a window already up —easyrpg's
; `Window_Message::UpdateMessage`—, at the box's speed: `\s[n]`, 1 to 20,
; 1 when a page starts. And the escapes in the middle are done where they
; are: `\.` waits 16 frames, `\|` 61, `\!` a key; `\>` and `\<` the instant
; text, to the end of the line; `\c[n]` the colour of what follows. Here it
; is the same, in three phases of `MSG_TYPE`:
;
; * `TYPE_BLANK`: a box that opens with no window up first blanks the four
;   lines, as `InsertNewPage` clears the contents: the composer goes through
;   them as lines the box does not carry —`msg_lines` with no lines, the
;   rest of its header kept—, which primes each one with the window's
;   background and the face, uploads it, and gives the face and the inn's
;   gold window the vblanks they ask for. Then the window opens.
; * `TYPE_TYPING`: from the box's first line again, with the window up.
;   `msg_next` hands the composer its letters at RM2k's pace —
;   `SetWaitForCharacter` and `SetWaitForNonPrintable`, below—, and what was
;   typed each frame goes up in the next vblank, only the cells it touched:
;   `msg_pace_vblank`. A line that ends goes up whole, as always.
; * `TYPE_NONE`: a box drawn again with its window up —a choice's cursor
;   moving, the digits of an `InputNumber`— is not typed: it is composed
;   `MSG_CHARS` letters a frame, a line at a time, as it always was.
;
; A box is done when its last line is typed —its pauses `\|` and its `\^`
; count from then on, as in RM2k, see `events_tick`—, and `msg_state`
; stays at 1 until then, so the page, the choice and the arrow wait for it.
;
; Until 2026-10-20 the console did not type: the window appeared with the
; box whole, and a wait in the middle cut the box there and composed it
; again from the cut line —`message_waits.s`—. The colour and the speed
; were dropped.

.pushseg
.segment "BSS"
; The phase, which `choice_tick` reads from bank 0: a choice is not picked
; while its box is being typed.
MSG_TYPE: .res 1
.popseg
TYPE_NONE   = 0
TYPE_BLANK  = 1
TYPE_TYPING = 2

.pushseg
.segment "FARBSS"
MSG_SPEED:      .res 1          ; 1 to 20
MSG_INSTANT:    .res 1          ; 1 from `\>` to `\<` or the line's end
MSG_WAIT:       .res 1          ; frames before the next letter
MSG_KEY:        .res 1          ; 1 while a `\!` waits for a key
MSG_COUNT:      .res 1          ; RPG_RT's `line_char_counter`
MSG_PRINTED:    .res 1          ; whether the last thing was a letter
MSG_BUDGET:     .res 1          ; letters left this frame
MSG_COLOUR:     .res 1          ; the text colour, 0 to 19
MSG_INK:        .res 1          ; the colour that took the box's ink, $FF none
MSG_INK_SET:    .res 1          ; 1: the ink's word goes to CGRAM in the vblank
MSG_INK_WORD:   .res 2
MSG_INK_ROWS:   .res 12         ; the entries of the glyph's rows in this colour
MSG_LINES_SAVE: .res 1          ; the box's header while its lines are blanked
MSG_BOX_PTR:    .res 3          ; and its first line
MSG_TYPED:      .res 1          ; 1: the cells typed go up in the vblank
MSG_DIRTY_LO:   .res 1          ; the first and the last cell they touched,
MSG_DIRTY_HI:   .res 1          ; $FF and 0 when none
MSG_ROWS_SEEN:  .res 1          ; `MSG_ROWS` the HDMA tables were built with
MSG_UP_BYTES:   .res 2          ; `typed_up`'s scratch, in the vblank: the bytes
MSG_UP_WORD:    .res 2          ; of each row, and where the top one goes
.popseg

; What follows `MESSAGE_CONTROL`: see `CONTROL` and what follows it in the
; event compiler's `messages.rs`.
CONTROL_KEY         = 0
CONTROL_QUARTER     = 16
CONTROL_SECOND      = 61
CONTROL_COLOUR      = $80
CONTROL_SPEED       = $A0
CONTROL_INSTANT_ON  = $C0
CONTROL_INSTANT_OFF = $C1
; What `msg_letter` answers after a control: no letter, ask again. A letter
; is below 128.
MSG_CONTROLLED = $FF
; The text's twenty colours in `window_gold`, after the grey: for each the
; ink's word and the entries of the glyph's twelve rows with the ink and
; without it. `INK_COLOURS` and `INK_BYTES` in rm2k-snes-mapdata's emit.rs.
INK_COLOURS = 20
INK_BYTES = 2 + 12 + 12
GOLD_INKS_AT = GOLD_INK_AT + 12

; At reset, from `msg_face_clear`: no box being typed, nothing waiting, colour
; 0. The WRAM does not boot at zero, and `choice_tick` reads `MSG_TYPE`.
.proc msg_pace_clear
.a8
.i16
    lda #TYPE_NONE
    sta f:MSG_TYPE
    lda #0
    sta f:MSG_KEY
    sta f:MSG_WAIT
    sta f:MSG_INSTANT
    sta f:MSG_COUNT
    sta f:MSG_COLOUR
    sta f:MSG_INK_SET
    sta f:MSG_TYPED
    rts
.endproc

; A box opens with no window up, from `msg_face_begin`: its lines are
; blanked first, and it starts at speed 1, colour 0, with nothing waiting.
; Keeps X and Y.
.proc msg_pace_begin
.a8
.i16
    lda #TYPE_BLANK
    sta f:MSG_TYPE
    lda f:msg_lines
    sta f:MSG_LINES_SAVE
    and #($FF ^ HEADER_LINES)
    sta f:msg_lines
    rep #$20
.a16
    lda msg_ptr
    sta f:MSG_BOX_PTR
    sep #$20
.a8
    lda msg_ptr + 2
    sta f:MSG_BOX_PTR + 2
    lda #1
    sta f:MSG_SPEED
    lda #$FF
    sta f:MSG_INK
    lda #0
    sta f:MSG_INSTANT
    sta f:MSG_WAIT
    sta f:MSG_KEY
    sta f:MSG_COUNT
    sta f:MSG_PRINTED
    sta f:MSG_COLOUR
    sta f:MSG_INK_SET
    sta f:MSG_TYPED
    rts
.endproc

; The window turns on, from `flush_video` in the vblank, where it used to
; set `msg_state` to 0: a box whose lines were blanked goes on to be typed
; from its first line, with `msg_state` at 1; a box typed whole is done, or,
; if its last thing was a `\!`, waits for that key at 3 —RPG_RT waits for
; it, and then for the page's own—; any other is done.
.proc msg_opened
.a8
.i16
    lda f:MSG_ROWS
    sta f:MSG_ROWS_SEEN         ; what `msg_hdma_build` is about to build with
    lda f:MSG_TYPE
    cmp #TYPE_BLANK
    beq typing
    cmp #TYPE_TYPING
    bne done
    lda f:MSG_KEY
    beq done
    lda #3
    sta f:msg_state
    rtl
done:
    jsr box_done
    rtl
typing:
    lda #TYPE_TYPING
    sta f:MSG_TYPE
    lda f:MSG_LINES_SAVE
    sta f:msg_lines
    lda #0
    sta f:msg_line
    sta f:msg_primed
    rep #$20
.a16
    lda f:MSG_BOX_PTR
    sta msg_ptr
    sep #$20
.a8
    lda f:MSG_BOX_PTR + 2
    sta msg_ptr + 2
    lda #1
    sta f:msg_state
    rtl
.endproc

; The box is done: `msg_state` at 0, and nothing of its pace outlives it
; —a box drawn again, the digits of a number, compose without waiting and in
; colour 0—.
.proc box_done
.a8
.i16
    lda #TYPE_NONE
    sta f:MSG_TYPE
    lda #0
    sta f:msg_state
    sta f:MSG_WAIT
    sta f:MSG_KEY
    sta f:MSG_INSTANT
    sta f:MSG_COLOUR
    sta f:MSG_COUNT
    rts
.endproc

; Once a frame, from the top of `message_tick`: this frame's letters, and
; the wait or the key a typed box is stopped at. A box whose lines are all
; typed is done —`msg_state` to 2, which `flush_video` takes to 0 in
; `msg_opened`—, without the frames its last letter waits: RPG_RT's waits
; two and closes the page after them, and the composer would go on to the
; lines the box does not carry.
.proc msg_pace_tick
.a8
.i16
    ; Nothing composing, nothing to do: it is every frame of the game.
    lda f:msg_state
    beq done
    lda #MSG_CHARS
    sta f:MSG_BUDGET
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne done
    lda f:msg_state
    cmp #3
    beq end_key
    cmp #1
    bne done
    lda f:msg_lines
    and #HEADER_LINES
    cmp f:msg_line
    beq finished
    bcc finished
    lda f:MSG_KEY
    beq no_key
    jsr key_edge
    bcc stopped
no_key:
    lda f:MSG_WAIT
    beq done
    dec a
    sta f:MSG_WAIT
stopped:
    lda #0
    sta f:MSG_BUDGET
done:
    rtl
finished:
    lda #2
    sta f:msg_state
    rtl
end_key:
    jsr key_edge
    bcc done
    jsr box_done
    rtl
.endproc

; Whether the key a `\!` waits for was pressed, in the carry: A or B,
; Decision or Cancel, as RPG_RT's `WaitForInput`. The edge is consumed, so
; that the box's own end does not take it too; a timed wait is not skipped
; by A, as in RM2k, where `wait_count` goes before `WaitForInput`. Pressed,
; the key's wait is over.
.proc key_edge
.a8
.i16
    lda pad_a
    beq not_a
    lda pad_a_prev
    bne not_a                   ; it was already held: not an edge
    lda pad_a
    sta pad_a_prev
    bra pressed
not_a:
    lda pad
    eor pad_prev
    and pad
    and #PAD_B
    beq none
    lda pad_prev
    ora #PAD_B
    sta pad_prev
pressed:
    lda #0
    sta f:MSG_KEY
    lda #$FF                    ; the arrow's band, in a window without its
    sta f:MSG_ROWS_SEEN         ; background: see `msg_bands`
    sec
    rts
none:
    clc
    rts
.endproc

; The start of each line, from `message_tick`, before its length is read:
; the letter pending from a pair and the digits of a variable are cleared
; —this is the only place, see `msg_letter`—, and so are the cells typed. A
; page starts in colour 0. And in a box being typed the line before it has
; ended: the instant text and the counter of letters stop there.
;
; RPG_RT's `\n` also waits a frame after a line whose last thing was not a
; letter, and here that frame is already the composer's, which starts a
; line on the frame after the one that ended the last: see `msg_next`.
.proc msg_line_start
.a8
.i16
    lda #0
    sta f:FAR_MSG_SECOND
    sta f:MSG_DIGITS_N
    sta f:MSG_TYPED
    sta f:MSG_DIRTY_HI
    lda #$FF
    sta f:MSG_DIRTY_LO
    lda f:msg_line
    bne typed
    lda #0
    sta f:MSG_COLOUR
typed:
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne done
    lda #0
    sta f:MSG_INSTANT
    sta f:MSG_COUNT
    sta f:MSG_PRINTED
done:
    rtl
.endproc

; The next letter for the composer, from `message_tick` in place of
; `msg_letter`: in A with the carry and V clear; or the carry set, nothing
; more this frame —the budget, a wait or a key—; or V set, no letter and
; the line is over —it ended in a control—. Keeps X, the composer's count.
;
; The controls are done here, as `msg_letter` reads them: see
; `msg_control`. In a typed box each letter sets the frames to the next one
; —`pace_letter`—, and stopping asks the vblank for what was typed.
.proc msg_next
.a8
.i16
    phx
again:
    lda f:MSG_BUDGET
    beq stop
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne go
    lda f:MSG_KEY
    bne stop
    lda f:MSG_WAIT
    beq go
    dec a                       ; RPG_RT's loop: the wait counts this frame
    sta f:MSG_WAIT
    bra stop
go:
    jsl f:msg_letter
    cmp #MSG_CONTROLLED
    bne letter
    lda f:msg_col
    cmp f:msg_length
    bcc again
    ; The line ended in a control. If it left a wait, RPG_RT's loop counts
    ; one frame of it now and its `\n` adds one when it is over: the wait
    ; stays as it is. If not, the `\n`'s frame is the one the composer
    ; takes to start the next line.
    plx
    sep #$41                    ; V and the carry: no letter, the line is over
    clc
    rtl
letter:
    pha
    lda f:MSG_BUDGET
    dec a
    sta f:MSG_BUDGET
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne paced
    jsr pace_letter
    ; The line's last letter: the composer ends the line without asking
    ; again, so the frame RPG_RT's loop counts of its wait is counted here.
    lda f:msg_col
    inc a
    cmp f:msg_length
    bcc paced
    lda f:MSG_WAIT
    beq paced
    dec a
    sta f:MSG_WAIT
paced:
    pla
    plx
    clc
    clv
    rtl
stop:
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne stopped
    lda #1
    sta f:MSG_TYPED
stopped:
    plx
    sec
    rtl
.endproc

; The frames after a letter: easyrpg's `SetWaitForCharacter` for a letter
; one half-width wide, which every letter of the console's font is. The
; instant text, none; the box's last letter, two —unless its tail follows,
; a `\|` or a `\^`, which RPG_RT reads after it—; at speed `n` past 1,
; `n / 2 + 1`; at speed 1, every second letter one, and the line's last one
; always: two letters a frame. And `IncrementLineCharCounter`.
.proc pace_letter
.a8
.i16
    lda f:MSG_INSTANT
    bne none
    ; The line's last letter: nothing of it left after this one.
    lda f:msg_col
    inc a
    cmp f:msg_length
    bne not_last
    ; And the box's: its last line, with no tail.
    lda f:msg_lines
    and #HEADER_LINES
    dec a
    cmp f:msg_line
    bne line_last
    lda f:msg_lines
    and #($FF ^ HEADER_LINES)
    bne line_last
    lda #2
    bra set
line_last:
    lda f:MSG_SPEED
    cmp #2
    bcs speed_n
    lda #1
    bra set
not_last:
    lda f:MSG_SPEED
    cmp #2
    bcs speed_n
    lda f:MSG_COUNT
    and #1
    bra set
speed_n:
    lsr a
    inc a
    bra set
none:
    lda #0
set:
    sta f:MSG_WAIT
    lda #1
    sta f:MSG_PRINTED
    ; and on into `count_letter`
.endproc
; RPG_RT's `IncrementLineCharCounter` for a half-width letter: one at
; speed 1, where two go in a frame, and at any other speed to the next even
; number and two more.
.proc count_letter
.a8
.i16
    lda f:MSG_SPEED
    cmp #2
    lda f:MSG_COUNT
    bcs even
    inc a
    bra counted
even:
    and #$FE
    inc a
    inc a
counted:
    sta f:MSG_COUNT
    rts
.endproc

; `MESSAGE_CONTROL`, from `msg_letter`, which jumps here with `msg_ptr` on
; the byte that says which. It takes itself off the line's length —it
; counted as a letter so that one at the end of a line is still read— and
; answers `MSG_CONTROLLED` with an `rtl`, as `msg_letter` answers a letter.
;
; The colour goes in any box; the waits, the speed and the instant text only
; in one being typed. Each is easyrpg's case of `UpdateMessage`, with its
; `SetWaitForNonPrintable`.
.proc msg_control
.a8
.i16
    ldy #0
    lda [msg_ptr], y            ; which
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
    cmp #CONTROL_COLOUR
    bcc a_wait
    cmp #CONTROL_SPEED
    bcs not_colour
    ; `\c[n]`: no wait, and the colour from here on, typed or not.
    pha
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    bne untyped
    lda #0
    jsr nonprintable
untyped:
    pla
    and #$1F
    jsr colour
    bra done
not_colour:
    pha
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    beq typed
    pla
    bra done                    ; drawn again: nothing to wait for
typed:
    pla
    cmp #CONTROL_INSTANT_ON
    bcs instant
    ; `\s[n]`: no wait at the speed it had, and the new one.
    pha
    lda #0
    jsr nonprintable
    pla
    and #$1F
    sta f:MSG_SPEED
    bra done
instant:
    bne instant_off
    lda #0
    jsr nonprintable
    lda #1
    sta f:MSG_INSTANT
    bra done
instant_off:
    lda #0
    sta f:MSG_INSTANT
    lda f:MSG_SPEED
    jsr nonprintable
    bra done
a_wait:
    pha
    lda f:MSG_TYPE
    cmp #TYPE_TYPING
    beq wait_typed
    pla
    bra done
wait_typed:
    pla
    cmp #CONTROL_KEY
    beq key
    cmp #CONTROL_QUARTER
    bne timed
    ; RPG_RT lengthens `\.` by a frame a speed past 16, up to 20 —"a bug(??)"
    ; to easyrpg, which copies it—.
    lda f:MSG_SPEED
    sec
    sbc #16
    bcs past_16
    lda #0
past_16:
    clc
    adc #CONTROL_QUARTER
timed:
    jsr nonprintable
    bra done
key:
    lda #0
    jsr nonprintable
    lda #1
    sta f:MSG_KEY
    lda #$FF                    ; the arrow's band: see `msg_pace_tick`
    sta f:MSG_ROWS_SEEN
done:
    lda #MSG_CONTROLLED
    rtl
.endproc

; easyrpg's `SetWaitForNonPrintable` with the frames in A: at speed 1 a
; frame more on an odd count, none with the instant text; and the count
; goes on as a letter's once the line has one.
.proc nonprintable
.a8
.i16
    pha
    lda f:MSG_INSTANT
    bne instant
    lda f:MSG_SPEED
    cmp #2
    bcs waits
    lda f:MSG_COUNT
    and #1
    clc
    adc 1, s
    sta 1, s
waits:
    pla
    sta f:MSG_WAIT
    bra counted
instant:
    pla
counted:
    lda #0
    sta f:MSG_PRINTED
    lda f:MSG_COUNT
    beq done
    jsr count_letter
done:
    rts
.endproc

; The colour in A, 0 to 19, from here on: the entries its glyph rows take
; to `MSG_INK_ROWS`, from the current System's `window_gold`. The first
; colour other than 0 a box types takes the ink, and its word goes to
; CGRAM in the next vblank; another colour goes with the window's nearest.
; See `inks` in rm2k-snes-screens' `message_window.rs`. Keeps nothing.
;
; A cartridge whose boxes type no colour other than 0 has no ink and no
; tables —see `text_inks` in rm2k-snes-mapdata—, and a colour here is 0.
.proc colour
.a8
.i16
.if ::TEXT_INK_ENTRY = 0
    lda #0
    sta f:MSG_COLOUR
    rts
.else
    sta f:MSG_COLOUR
    cmp #0
    beq done
    jsr gold_source
    lda f:MSG_INK
    bpl taken                   ; $FF: no colour has it yet
    lda f:MSG_COLOUR
    sta f:MSG_INK
    jsr ink_at
.a16
    ldx #.loword(MSG_INK_WORD)
    ldy #2
    jsr gold_to_wram
    sep #$20
.a8
    lda #1
    sta f:MSG_INK_SET
taken:
    ; Its rows with the ink, past the word, if it is the ink's colour; the
    ; window's nearest, past those, if it is not.
    ldy #2
    lda f:MSG_INK
    cmp f:MSG_COLOUR
    beq rows
    ldy #2 + 12
rows:
    phy
    jsr ink_at
.a16
    clc
    adc 1, s
    ply
    ldx #.loword(MSG_INK_ROWS)
    ldy #12
    jsr gold_to_wram
    sep #$20
.a8
done:
    rts
.endif
.endproc

; Where colour `MSG_COLOUR`'s piece starts in `window_gold`, in A16.
.proc ink_at
.a8
.i16
    lda f:MSG_COLOUR
    sta f:WRMPYA
    lda #INK_BYTES
    sta f:WRMPYB                ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    clc
    adc #GOLD_INKS_AT
    rts
.endproc

; From `msg_arrow`, every vblank with the window up: the ink's word to
; CGRAM, what was typed since the last one to VRAM, and the HDMA tables
; again if the lines a window without its background draws on changed —a
; line typed, or the arrow of a `\!`—. Only while the vblank lasts: what
; does not fit waits for the next one.
.proc msg_pace_vblank
.a8
.i16
    phx
    phy
    lda f:HVBJOY
    bpl done
.if ::TEXT_INK_ENTRY > 0
    lda f:MSG_INK_SET
    beq no_ink
    lda #0
    sta f:MSG_INK_SET
    lda #TEXT_INK_ENTRY
    sta f:CGADD
    lda f:MSG_INK_WORD
    sta f:CGDATA
    lda f:MSG_INK_WORD + 1
    sta f:CGDATA
no_ink:
.endif
    lda f:MSG_TYPED
    beq no_typed
    ; Only if its DMA still fits: one that runs past the vblank writes
    ; nothing from there on, and the tail of the cells would be a hole until
    ; the line goes up whole. Late, `MSG_TYPED` and the cells stay for the
    ; next vblank. It is `upload_line`'s test, with this one's size.
    lda f:STAT78                ; resets the counters' flip-flop
    lda f:SLHV                  ; latches them
    lda f:OPVCT
    xba
    lda f:OPVCT
    and #$01                    ; the ninth bit; the rest is open bus
    xba
    rep #$20
.a16
    cmp #TYPED_LATEST + 1
    bcs late
    cmp #LINES + 1              ; on the screen's lines: the vblank is over
    bcc late
    sep #$20
.a8
    jsr typed_up
    bra no_typed
late:
    sep #$20
.a8
no_typed:
    lda f:MSG_PLACE
    and #MSG_BARE
    beq done
    lda f:MSG_ROWS
    cmp f:MSG_ROWS_SEEN
    beq done
    sta f:MSG_ROWS_SEEN
    jsl f:msg_hdma_build
done:
    ply
    plx
    rtl
.endproc

; The last line on which `typed_up` may start: the five letters a frame
; types touch some eight cells, 512 bytes in its two DMAs —three lines at
; eight master cycles a byte, 1364 to a line—, one more for setting them
; up, and the vblank's last line is 261. Late, the cells wait.
TYPED_LATEST = 261 - 3 - 1

; The cells of the line being typed that its letters touched since the
; last time, both cell rows, to the window's tile bank: two DMAs of a few
; tiles, where a line that ends goes up whole —`upload_line`, 1920 bytes—.
.proc typed_up
.a8
.i16
    lda #0
    sta f:MSG_TYPED
    lda f:MSG_DIRTY_HI
    cmp f:MSG_DIRTY_LO
    bcs some
    rts                         ; none touched: $FF and 0
some:
    lda #$80
    sta f:VMAIN
    ; The bytes: one tile per cell, in each row.
    lda f:MSG_DIRTY_HI
    sec
    sbc f:MSG_DIRTY_LO
    inc a
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    sta f:MSG_UP_BYTES               ; the bytes of each row
    ; The first tile: the line's sixty, and the cell.
    lda f:msg_line
    and #$00FF
    sta f:MSG_UP_WORD
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc f:MSG_UP_WORD
    sbc f:MSG_UP_WORD
    sbc f:MSG_UP_WORD
    sbc f:MSG_UP_WORD             ; line * 60
    sta f:MSG_UP_WORD
    lda f:MSG_DIRTY_LO
    and #$00FF
    pha
    clc
    adc f:MSG_UP_WORD
    adc #WINDOW_TEXT_BASE
    asl a
    asl a
    asl a
    asl a                       ; sixteen words a tile
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_WINDOW, x
    sta f:MSG_UP_WORD             ; the top row's word
    sta f:VMADDL
    pla
    asl a
    asl a
    asl a
    asl a
    asl a                       ; and its byte in `text_buf`
    pha
    clc
    adc #.loword(text_buf)
    sta f:A1T0L
    lda f:MSG_UP_BYTES
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:A1B0                  ; the buffer lives in bank 0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    ; And the bottom row: thirty tiles further in VRAM and in the buffer.
    rep #$20
.a16
    lda f:MSG_UP_WORD
    clc
    adc #WINDOW_TEXT_COLS * 16
    sta f:VMADDL
    pla
    clc
    adc #.loword(text_buf) + WINDOW_TEXT_COLS * 32
    sta f:A1T0L
    lda f:MSG_UP_BYTES
    sta f:DAS0L
    sep #$20
.a8
    lda #$01
    sta f:MDMAEN
    lda #$FF
    sta f:MSG_DIRTY_LO
    lda #0
    sta f:MSG_DIRTY_HI
    rts
.endproc

; The cells a letter just composed touched, from `msg_ink_char` with
; `comp_base` as `compose_char` left it: its cell and the next one, which
; the typed upload takes. A16 in and out.
.proc ink_dirty
.a16
.i16
    lda comp_base
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the cell, counted from the text area's left
    sep #$20
.a8
    cmp f:MSG_DIRTY_LO
    bcs not_lower
    sta f:MSG_DIRTY_LO
not_lower:
    inc a
    cmp #WINDOW_TEXT_COLS
    bcc in_area
    lda #WINDOW_TEXT_COLS - 1
in_area:
    cmp f:MSG_DIRTY_HI
    bcc not_higher
    sta f:MSG_DIRTY_HI
not_higher:
    rep #$20
.a16
    rts
.endproc
