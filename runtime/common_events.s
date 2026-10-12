.segment "FAR"
.a8
.i16

; --- the shared common event bodies -------------------------------------------
;
; The automatic common events and every one they call, compiled once and
; apart from the maps —see `commons.rs` in the event compiler—: each body in
; the cartridge, read where it is like the troops' pages. `common_body_lo`
; and `common_body_bank` say where each one starts, by its index; the
; automatic ones are `COMAUTO_N` entries of `comauto_byte`, `comauto_mask` and
; `comauto_body`, in the order of their numbers.
;
; They live in bank 1 because bank 0 has no room: the interpreter reaches
; them with a `jsl` from `op_call` and `op_return`, and `events_tick` and
; the hero with one more. Everything goes long or through the direct page:
; `op_call` and `op_return` come with the bytecode's data bank.

; The interpreter's call stack, in far RAM: how deep it is, and per level
; where the caller was —its `code_ptr`, three bytes, and its cursor, two—.
; Three levels are what the game this was written for asks: the converter
; emits the deepest chain as `COMMON_DEPTH`, and the `.assert` below stops
; the build if it ever needs more. **It does not travel in the save**: the
; menu does not open with a page running.
;
; $6110 to $611F, behind $6100, which was `MAP_SONG`'s. The work of
; 2026-10-02 had set aside $2560 to $256F for this, but that is inside
; `FAR_PAIR_LIST`, which goes up to $257F with `PARALLEL_MAX` at 48, and the
; car chase has forty parallels.
CALL_DEPTH = $7E6110
CALL_STACK = $7E6111
CALL_ENTRY = 5
CALL_LEVELS = 3
.assert CALL_STACK + CALL_LEVELS * CALL_ENTRY <= $7E6120, error, "the call stack overflows its range"
.assert COMMON_DEPTH <= CALL_LEVELS + 1, error, "a chain of calls is deeper than the call stack"

; Starts the first automatic common event whose switch is on, if the
; foreground interpreter is free: `Game_Map::UpdateForegroundEvents`, which
; looks at the common events in their order and pushes the first one that
; `IsWaitingForegroundExecution`. Returns A = 1 if one started —with
; `code_ptr`, `ev_cur` and `ev_active` set, as `start_waiting` leaves them—
; and A = 0 if none, with Z from it.
;
; It is the map's waiting events first and then this, not the other way
; around: easyrpg pushes the common event and then the map's event on top of
; it, so the map's runs first and the common event after it, on the same
; frame. Here the common event waits for the queue of the map to empty,
; which is the same thing when one event is waiting, and the common event
; one or more turns later when several are.
;
; The event that is running is none, $FFFF: a common event's frame has no
; event —`frame.event_id` is 0 for `EventType::CommonEvent`—, so there is no
; one to turn back to its pose nor to mark again.
.proc common_start
.a8
.i16
    ldx #0
other:
    cpx #COMAUTO_N
    bcc has
    lda #0
    rtl
has:
    jsr switch_of
    beq off
    lda f:comauto_body, x
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:common_body_lo, x
    sta code_ptr
    stz ev_cur
    lda #$FFFF
    sta f:ev_running
    sep #$20
.a8
    lda f:common_body_bank, x
    sta code_ptr + 2
    lda #0
    sta f:CALL_DEPTH            ; a new frame: nobody to return to
    lda #1
    sta ev_active
    rtl
off:
    inx
    bra other
.endproc

; Whether some automatic common event's switch is on: A != 0 if so, with Z
; from it. It is the half of `Game_Map::IsAnyEventStarting` that looks at
; the common events, and the hero asks it before walking: with one about to
; start he does not take a step, as with a map's event waiting.
.proc common_waiting
.a8
.i16
    ldx #0
other:
    cpx #COMAUTO_N
    bcc has
    lda #0
    rtl
has:
    jsr switch_of
    bne on
    inx
    bra other
on:
    lda #1
    rtl
.endproc

; Whether the switch of automatic common event X is on: A != 0 and Z clear
; if so. Keeps X; clobbers Y.
.proc switch_of
.a8
.i16
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:comauto_byte, x
    tay
    sep #$20
.a8
    plx
    phx
    lda f:comauto_mask, x
    sta temp
    tyx
    lda f:switches, x
    and temp
    plx
    cmp #0                      ; the `plx` left its own flags
    rts
.endproc

; `OP_CALL`, from `op_call` with Y on its operand: the body it names starts,
; and where this page was goes on the stack. With the stack full the call is
; skipped, which is what a call does whose body does not compile —and what
; RPG_RT does instead of crashing is not something to copy—.
.proc call_enter
.a8
.i16
    lda [code_ptr], y           ; the body's index
    iny
    pha
    lda f:CALL_DEPTH
    cmp #CALL_LEVELS
    bcc room
    pla
    rtl
room:
    ; This level's entry: depth times five.
    sta temp
    asl a
    asl a
    clc
    adc temp
    rep #$20
.a16
    and #$00FF
    tax
    lda code_ptr
    sta f:CALL_STACK, x
    tya
    sta f:CALL_STACK + 3, x
    sep #$20
.a8
    lda code_ptr + 2
    sta f:CALL_STACK + 2, x
    lda f:CALL_DEPTH
    inc a
    sta f:CALL_DEPTH
    pla
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:common_body_lo, x
    sta code_ptr
    sep #$20
.a8
    lda f:common_body_bank, x
    sta code_ptr + 2
    ldy #0
    rtl
.endproc

; `OP_RETURN`: back to whoever called, with the carry clear; or, if nobody
; did, the carry set, and `op_return` ends the page like `OP_DONE`.
.proc call_leave
.a8
.i16
    lda f:CALL_DEPTH
    bne has
    sec
    rtl
has:
    dec a
    sta f:CALL_DEPTH
    sta temp
    asl a
    asl a
    clc
    adc temp
    rep #$20
.a16
    and #$00FF
    tax
    lda f:CALL_STACK, x
    sta code_ptr
    lda f:CALL_STACK + 3, x
    tay
    sep #$20
.a8
    lda f:CALL_STACK + 2, x
    sta code_ptr + 2
    clc
    rtl
.endproc
