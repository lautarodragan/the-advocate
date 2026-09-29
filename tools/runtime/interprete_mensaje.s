.segment "CODE"
.a8
.i16

; --- the interpreter: the message and the choice ----------------------------
;
; Opcode handlers: the dispatch in `correr_codigo`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.

; Opens the message window and ends the frame. The cursor is already on the
; next command —the loop's `iny`— but `eventos_tick` does not call here again
; until the player presses A.
;
; The operand is the offset of the text box inside the `mensajes` block, 16
; bits. It is not the text: emitting each box already composed is 240 4bpp
; tiles, that is 7.5 KB, and the game's 2895 would be 21 MB. What travels in
; the cartridge is one byte per letter, and the 65816 composes it, which is
; FF6's way out.
.proc op_message
    ; A parallel does not open its message on top of another one's: it
    ; **waits**. `CommandShowMessage` starts with `if
    ; (!CanShowMessage(main_flag)) return false;` and for a background
    ; interpreter that is `!is_active` (easyrpg `game_interpreter.cpp:928` and
    ; `window_message.h:216`); returning false leaves the cursor where it was,
    ; so the opcode is retried the next frame. The foreground does not need the
    ; check —with a message open `eventos_tick` does not even call it— and
    ; that is why `par_ev` decides.
    lda par_ev
    cmp #$FF
    beq abrir                   ; foreground
    cmp #PAR_PELEA
    beq en_la_pelea
    lda msg_abierto
    ora msg_estado
    ora eleg_activo
    beq abrir
    dey                         ; the cursor goes back to this same opcode
    sty ev_cur
    rts
en_la_pelea:
    ; A troop page: the message does not go to the map's window —the screen
    ; is the battle's, and `texto_buf` is the battle's— but is left noted for
    ; the battle, which draws it on its lines and waits for A. The page stays
    ; held behind it just as on the map: `ev_activo` stays at one and the
    ; cursor, on the next command. See `ba_pag_paso`.
    rep #$20
.a16
    lda [cod_ptr], y
    sta f:BAT_LARGO + BA_PAG_MSG
    iny
    iny
    sep #$20
.a8
    sty ev_cur
    rts
abrir:
    lda par_ev
    sta msg_duenio              ; $FF if the foreground opens it
    ; The message does not appear this frame: its text has to be composed,
    ; and that takes quite a few. The window turns itself on when the composer
    ; finishes; meanwhile the page is already blocked.
    stz msg_abierto
    stz eleg_activo
    rep #$20
.a16
    lda [cod_ptr], y            ; the offset, which goes in A to msg_empezar
    iny
    iny
    phy
    jsr msg_empezar
    ply
    sep #$20
.a8
    sty ev_cur
    rts

.endproc

; `ShowChoice`: opens the window with the options and ends the frame, like a
; message. The difference is that the page **does not resume where it left
; off**: when the player chooses, `eleccion_tick` sets the cursor to the
; destination of the highlighted option. That is why `ev_cur` is not saved
; here: what is saved is where the table is, which is where both come from,
; the box that is drawn and the destination.
.proc op_choice
    lda [cod_ptr], y            ; how many options
    sta eleg_n
    iny
    lda [cod_ptr], y            ; which option cancel picks, plus one
    sta eleg_cancel
    iny
    sty eleg_tabla
    stz eleg_sel                ; `Window_Selectable` starts with the index at
                                ; zero, and the first option is highlighted
    lda #1
    sta eleg_activo
    jsr eleg_abrir
    rts


.endproc

