.segment "CODE"
.a8
.i16

; --- the interpreter: teleport ---------------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

.proc op_teleport
    rep #$20
.a16
    lda [code_ptr], y            ; the map, as a word since the format has
    sta jump_map              ; to be able to name all 328 in the game
    iny
    iny
    lda [code_ptr], y
    sta jump_x
    iny
    iny
    lda [code_ptr], y
    sta jump_y
    sep #$20
.a8
    iny                         ; the two bytes of the Y, which were read
    iny                         ; without advancing the cursor
jump:
    lda #1
    sta jump_has
    ; And it ends the frame, which is exactly what
    ; `Game_Interpreter_Map::CommandTeleport` does in easyrpg-player: it queues
    ; the transfer, does `index++` and returns false. The map loads between
    ; this frame and the next, and the page resumes at the command after this
    ; one with the cursor saved here. No page in the game that compiles today
    ; has commands after a teleport —measured over the whole game—; the
    ; opening cutscene has eleven.
    sty ev_cur
    rts
.endproc


; `MemorizeLocation` and `RecallToLocation`: like `op_heal`, only the entry
; point. The body is `remembered_place`, outside bank 0, and it returns with
; carry set if there is a transfer to do, with the destination already in
; `salto_*`: the transfer finishes here, like the one in `op_teleport`.
.proc op_location
    jsl f:remembered_place
    bcs jump
    jmp run_code::other
jump:
    jmp op_teleport::jump

.endproc
