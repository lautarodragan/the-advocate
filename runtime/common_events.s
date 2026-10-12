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

; --- the parallel common events ----------------------------------------------
;
; `Game_Map::UpdateCommonEvents`: each parallel common event has **its own
; interpreter**, which runs every frame while its switch is on —or always, if
; it has none—, before the map's events, with a message open and with a page
; in progress. Like a map's parallel page, when its body ends it starts over
; on the next frame; and with the switch off it does not run but keeps where
; it was: `Game_CommonEvent::Update` only skips the `Update`, so turning the
; switch back on goes on from there. Both RPG_RT, 2000's and 2015's, do the
; same: with one that turns its own switch off and then shows two messages,
; the second never shows.
;
; Their bodies are compiled once, without a map —`parallel_commons` in the
; event compiler—, and the converter emits them as `COMPAR_N` entries of
; `compar_table`, in the order of their numbers:
;
;     +0  byte  the byte of `switches` its switch is in
;     +1  byte  the switch's mask; $00 is none, and it runs always
;     +2  byte  1 if it is pure
;     +3  word  where its body starts, and +5 its bank
;
; **The pure ones run only when what they read changes.** A body that only
; reads switches and the equipment and only writes skills and permissions
; —`commons::pure` in the compiler: in the game this was written for,
; `DisableSaving`, `EnableSaving` and `UpdateAG7 Skills`— gives the same
; result every frame until one of those changes, so it runs on the frame its
; switch turns on and on the first after `compar_owed`, which whoever changes
; them sets: `set_switch`, the menu closing —where the equipment changes—,
; `ChangeEquipment` and the permission opcode. A switch written from outside
; the ROM —the tests' `prender`— does not go through there. Running them
; every frame cost the race its sixty frames.
;
; Each one's state lives in far RAM, `COMPAR_ENTRY` bytes, so the same X walks
; the table and the state: the cursor, the wait, whether it is running and
; whether its switch was on the last frame. The map changes and it stays, as
; `Game_Map` keeps its common events across maps. It does not travel in the
; save —RPG_RT saves an empty stack for them— and starts at zero on reset.
;
; While one runs, `pair_ev` is `PAIR_COMMON` plus its index: it is what
; `op_message` notes as the message's owner, and what tells the opcodes that
; ask that this is not the foreground.
COMPAR_ENTRY = 6
PAIR_COMMON = $80
.assert EV_MAX <= PAIR_COMMON, error, "a map event's index reaches the parallel common events' pair_ev"
.assert PAIR_COMMON + COMPAR_N <= PAIR_BATTLE, error, "too many parallel common events for pair_ev"
.assert COMPAR_N * COMPAR_ENTRY < $8000, error, "compar_tick walks the table with a signed compare"

.pushseg
.segment "FARBSS"
compar_state: .res COMPAR_N * COMPAR_ENTRY + 1
compar_owed: .res 1         ; something a pure one reads changed
compar_now: .res 1          ; and this frame's copy of it
compar_saved: .res 1        ; whether the foreground's context is saved
compar_id: .res 1           ; `PAIR_COMMON` plus the index of the one at X
compar_context: .res 11     ; and where: see `compar_tick`
.popseg

; At reset: none running, none seen on, and the pure ones owed a run.
.proc compar_clear
.a8
.i16
    ldx #0
    lda #0
erase:
    sta f:compar_state, x
    inx
    cpx #COMPAR_N * COMPAR_ENTRY + 1
    bcc erase
    lda #1
    sta f:compar_owed
    rtl
.endproc

; Something a pure one reads changed —a switch, the equipment—: they run on
; the next frame. Clobbers A.
.proc compar_owe
.a8
    lda #1
    sta f:compar_owed
    rtl
.endproc

; A permission changed, which the pure ones write: they run on the next frame,
; to set it back if theirs says otherwise —`EnableSaving` against a page's
; `ChangeSaveAccess`—. Except when a parallel common event is the one that
; changed it: `DisableSaving` and `EnableSaving` would wake each other every
; frame. Clobbers A.
.proc compar_owe_access
.a8
    lda pair_ev
    cmp #PAIR_COMMON
    bcc owe
    cmp #PAIR_BATTLE
    bcc mine
owe:
    lda #1
    sta f:compar_owed
mine:
    rtl
.endproc

; One frame of each parallel common event, from `map_events`, with the data
; bank at 0. It runs every frame on every map, so the entries that do not run
; —almost all, almost always— cost a dozen instructions: their switch, and
; out. The foreground's context is saved only when one runs, in far RAM, and
; given back at the end, as `parallel_tick` does on the stack.
.proc compar_tick
.a8
.i16
.if ::COMPAR_N = 0
    rtl
.else
    lda f:compar_owed
    sta f:compar_now
    lda #0
    sta f:compar_owed           ; what changes while they run is the next frame's
    sta f:compar_saved
    lda #PAIR_COMMON
    sta f:compar_id
    ldx #0
each:
    jsr compar_one
    lda f:compar_id
    inc a
    sta f:compar_id
    rep #$21                    ; and the carry, for the add
.a16
    txa
    adc #COMPAR_ENTRY
    tax
    sep #$20
.a8
    cpx #COMPAR_N * COMPAR_ENTRY
    bcc each
    lda f:compar_saved
    beq untouched
    lda #$FF                    ; outside the loops: see `parallel_tick`
    sta pair_ev
    lda f:compar_context + 8
    sta ev_active
    lda f:compar_context + 6
    sta code_ptr + 2
    rep #$20
.a16
    lda f:compar_context + 0
    sta ev_cur
    lda f:compar_context + 2
    sta ev_waiting
    lda f:compar_context + 4
    sta code_ptr
    lda f:compar_context + 9
    sta f:ev_running
    sep #$20
.a8
untouched:
    rtl
.endif
.endproc

; One frame of the one whose entry starts at X, which it keeps.
.proc compar_one
.a8
.i16
    ; Its switch: A nonzero if on.
    lda f:compar_table + 1, x
    beq always
    sta temp
    rep #$20
.a16
    lda f:compar_table + 0, x
    and #$00FF
    tay
    sep #$20
.a8
    lda switches, y
    and temp
    bne on
    sta f:compar_state + 5, x   ; off: it keeps where it was
    rts
always:
    lda #1
on:
    ; And the last frame's, for the pure ones' edge.
    lda f:compar_state + 5, x
    sta temp + 2
    lda #1
    sta f:compar_state + 5, x
    lda f:compar_table + 2, x
    beq runs
    lda temp + 2
    beq runs                    ; a pure one whose switch just turned on
    lda f:compar_now
    bne runs
    rts
runs:
    ; Who it is, for the message: `PAIR_COMMON` plus its index.
    lda f:compar_id
    sta temp + 3
    ; With a message on screen it keeps running, unless the message is its
    ; own: see `one_parallel`.
    lda f:msg_open
    ora f:msg_state
    ora pick_active
    beq not_mine
    lda f:msg_owner
    cmp temp + 3
    bne not_mine
    rts
not_mine:
    rep #$20
.a16
    lda f:compar_state + 2, x
    beq no_wait
    dec a
    sta f:compar_state + 2, x
    sep #$20
.a8
    rts
no_wait:
.a16
    sep #$20
.a8
    lda f:compar_saved
    bne saved
    inc a
    sta f:compar_saved
    lda ev_active
    sta f:compar_context + 8
    lda code_ptr + 2
    sta f:compar_context + 6
    rep #$20
.a16
    lda ev_cur
    sta f:compar_context + 0
    lda ev_waiting
    sta f:compar_context + 2
    lda code_ptr
    sta f:compar_context + 4
    lda f:ev_running
    sta f:compar_context + 9
    sep #$20
.a8
saved:
    rep #$20
.a16
    stz ev_waiting
    lda #0
    sta ev_cur                  ; from the start, unless it was running
    sep #$20
.a8
    lda f:compar_state + 4, x
    beq begin
    rep #$20
.a16
    lda f:compar_state + 0, x
    sta ev_cur
    sep #$20
.a8
begin:
    lda #1
    sta ev_active
    lda temp + 3
    sta pair_ev
    rep #$20
.a16
    lda #$FFFF                  ; no event: a common event's frame has none
    sta f:ev_running
    lda f:compar_table + 3, x
    sta code_ptr
    sep #$20
.a8
    lda f:compar_table + 5, x
    sta code_ptr + 2
    phx
    jsl f:run_code_long + FAST
    plx
    rep #$20
.a16
    lda ev_cur
    sta f:compar_state + 0, x
    lda ev_waiting
    sta f:compar_state + 2, x
    sep #$20
.a8
    lda ev_active
    sta f:compar_state + 4, x
    rts
.endproc


