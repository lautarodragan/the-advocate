.segment "CODE"
.a8
.i16

; --- the interpreter: the button and the wait -------------------------------
;
; Opcode handlers: the dispatch of `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or cuts the frame short with `rts`.

; `KeyInputProc`: which button the player pressed, stored in a variable. See
; OP_KEY in eventos.py, which is where the reason lives for why the waiting
; form is emitted twice.
;
; The one that **waits** and finds nothing rewinds its own cursor to this same
; opcode and hands control back: the next frame runs it again. That is what
; avoids having to store "I am waiting" somewhere —the interpreter of a
; parallel event is seven bytes and none of them is spare—.
.proc op_key
.a8
.i16
    lda [code_ptr], y            ; the variable's slot
    iny
    sta temp
    lda [code_ptr], y            ; the flags
    iny
    sta temp + 1
    and #KEY_STARTS
    beq tecla_mirar
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
    jsr var_write            ; with its refresh, if the flags ask for it
    sty ev_cur
    rts
tecla_mirar:
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
    beq tecla_leer
    lda msg_open
    ora msg_state              ; also while it is being composed
    ora pick_active
    bne tecla_rebobinar
tecla_leer:
    phy
    jsr key_value
    ply
    sta temp + 2                ; the value, which is where var_write takes it from
    stz temp + 3
    lda temp + 1
    and #KEY_WAIT
    beq tecla_guardar           ; without a wait, whatever is there is stored, zero included
    lda temp + 2
    bne tecla_guardar
tecla_rebobinar:
    dey                         ; nothing yet: the cursor goes back to this opcode
    dey
    dey
    sty ev_cur
    rts
tecla_guardar:
    lda temp + 1
    xba
    lda temp
    jsr var_write            ; `SetNeedRefreshForVarChange`, like ControlVars:
    jmp run_code::otro     ; the flags decide it. See `var_write`

.endproc

.proc op_delay
    ; And here control is handed back. It used to be skipped, and the comment
    ; said there were no frames to let go by because this ran with the screen
    ; off while the map was loading. That stopped being true: the interpreter
    ; runs from the main loop, with the screen on, and an RM2k wait is time the
    ; player watches go by.
    rep #$20
.a16
    lda [code_ptr], y            ; how many frames, sixteen bits
    sta ev_waiting
    sep #$20
.a8
    iny
    iny
    sty ev_cur
    rts

.endproc
