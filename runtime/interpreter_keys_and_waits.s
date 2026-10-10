.segment "CODE"
.a8
.i16

; --- the interpreter: the button and the wait -------------------------------
;
; Opcode handlers: the dispatch of `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or cuts the frame short with `rts`.

; `KeyInputProc`: which button the player pressed, stored in a variable. See
; OP_KEY in events.py, which is where the reason lives for why the waiting
; form is emitted twice.
;
; The one that **waits** and finds nothing rewinds its own cursor to this same
; opcode and hands control back: the next frame runs it again. That is what
; avoids having to store "I am waiting" somewhere —the interpreter of a
; parallel event is seven bytes and none of them is spare—.
.proc op_key
.a8
.i16
    lda [code_ptr], y           ; the variable's slot
    iny
    sta temp
    lda [code_ptr], y           ; the flags
    iny
    sta temp + 1
    and #KEY_STARTS
    beq key_look
    ; The first of the two: the variable to zero and control handed back
    ; without looking at anything. It is RPG_RT's `Input::ResetTriggerKeys()`:
    ; the edge is computed against the previous frame's pad, so letting a
    ; frame go by is losing it **for this interpreter**.
    ;
    ; For the rest of the frame that was not enough, and that is why both
    ; "previous" values are overwritten with the current pad: easyrpg says the
    ; reset also prevents "player actions for this frame such as summoning the
    ; menu or triggering events" (`game_interpreter.cpp:3403-3408`). A
    ; parallel runs before the hero, so without this the A with which the
    ; boulder engine of map 11 primes one also talked to the gate the hero was
    ; facing. It is covered by `test_con_a_y_una_direccion_la_piedra_sale_
    ; volando`.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz temp + 2
    stz temp + 3
    lda temp + 1                ; the flags, which carry the refresh bit
    xba
    lda temp
    jsr var_write               ; with its refresh, if the flags ask for it
    sty ev_cur
    rts
key_look:
    ; The waiting one does not look at the pad while there is a message or a
    ; choice on screen, **anyone's**: it is the `if
    ; (Game_Message::IsMessageActive()) break;` of `Game_Interpreter::Update`,
    ; easyrpg `game_interpreter.cpp: 470-473`. It matters for parallels, which
    ; keep running while someone else's message is open: without this, the A
    ; that closes the message of the broken PC on map 11 was also read by the
    ; boulder engine, and a boulder was lost. It is covered by
    ; `test_la_a_que_cierra_el_mensaje_no_saca_una_piedra`.
    lda temp + 1
    and #KEY_WAIT
    beq key_read
    lda msg_open
    ora msg_state               ; also while it is being composed
    ora pick_active
    bne key_rewind
key_read:
    phy
    jsr key_value
    ply
    sta temp + 2                ; the value, which is where var_write takes it from
    stz temp + 3
    lda temp + 1
    and #KEY_WAIT
    beq key_save                ; without a wait, whatever is there is stored, zero included
    lda temp + 2
    bne key_save
key_rewind:
    dey                         ; nothing yet: the cursor goes back to this opcode
    dey
    dey
    sty ev_cur
    rts
key_save:
    lda temp + 1
    xba
    lda temp
    jsr var_write               ; `SetNeedRefreshForVarChange`, like ControlVars:
    jmp run_code::other         ; the flags decide it. See `var_write`

.endproc

.proc op_delay
    ; And here control is handed back. It used to be skipped, and the comment
    ; said there were no frames to let go by because this ran with the screen
    ; off while the map was loading. That stopped being true: the interpreter
    ; runs from the main loop, with the screen on, and an RM2k wait is time the
    ; player watches go by.
    ;
    ; And the frame that runs the wait **is the first one of it**, so what is
    ; left to count is one less. In easyrpg `SetupWait` sets `wait_time` and
    ; returns true, and the interpreter loop goes back to its top in the same
    ; frame, where `wait_time--; break;` already spends one
    ; (`game_interpreter.cpp:447`): a `Wait 15` runs the next command 90
    ; frames later, not 91. Storing the whole count was one frame more per
    ; wait, and against the RPG_RT it showed: the map 16 cutscene went 161
    ; frames per round instead of 158, and the tint after `Wait 2` in
    ; `timer-cero` came out at +13 and not +12. A zero —`Wait 0`— still ends
    ; the frame, which is RM2k's "0.0 waits 1 frame".
    rep #$20
.a16
    lda [code_ptr], y           ; how many frames, sixteen bits
    beq store                   ; `lda` leaves Z: zero stays zero
    dec a
store:
    sta ev_waiting
    sep #$20
.a8
    iny
    iny
    sty ev_cur
    rts

.endproc
