.segment "CODE"
.a8
.i16

; --- the interpreter: the message and the choice ----------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; Opens the message window and ends the frame. The cursor is already on the
; next command —the loop's `iny`— but `events_tick` does not call here again
; until the player presses A.
;
; The operand is the offset of the text box inside the `messages` block, 16
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
    ; check —with a message open `events_tick` does not even call it— and
    ; that is why `pair_ev` decides.
    lda pair_ev
    cmp #$FF
    beq open                    ; foreground
    cmp #PAIR_BATTLE
    beq in_battle
    lda msg_open
    ora msg_state
    ora pick_active
    beq open
    dey                         ; the cursor goes back to this same opcode
    sty ev_cur
    rts
in_battle:
    ; A troop page: the message does not go to the map's window —the screen
    ; is the battle's, with its own text— but is left noted for
    ; the battle, which draws it on its lines and waits for A. The page stays
    ; held behind it just as on the map: `ev_active` stays at one and the
    ; cursor, on the next command. See `ba_page_step`.
    rep #$20
.a16
    lda [code_ptr], y
    sta f:BAT_LENGTH + BA_PAGE_MSG
    iny
    iny
    sep #$20
.a8
    sty ev_cur
    rts
open:
    lda pair_ev
    sta msg_owner               ; $FF if the foreground opens it
    ; The message does not appear this frame: its text has to be composed,
    ; and that takes quite a few. The window turns itself on when the composer
    ; finishes; meanwhile the page is already blocked.
    stz msg_open
    stz pick_active
window:                         ; `op_number` comes in here: see there
    rep #$20
.a16
    lda [code_ptr], y           ; the offset, which goes in A to msg_start
    iny
    iny
    phy
    jsr msg_start
    ply
    sep #$20
.a8
    sty ev_cur
    rts

.endproc

; `ShowChoice`: opens the window with the options and ends the frame, like a
; message. The difference is that the page **does not resume where it left
; off**: when the player chooses, `choice_tick` sets the cursor to the
; destination of the highlighted option. That is why `ev_cur` is not saved
; here: what is saved is where the table is, which is where both come from,
; the box that is drawn and the destination.
.proc op_choice
    lda [code_ptr], y           ; how many options
    sta pick_n
    iny
    lda [code_ptr], y           ; which option cancel picks, plus one
    ; Or $FF: cancel picks past the options, which in RM2k runs none
    ; —`CANCEL_PAST` in the event compiler—. The table carries one more entry,
    ; the last, that jumps to the end of the choice: the cursor does not
    ; reach it, and cancel picks it.
    cmp #$FF
    bne cancel_ready
    dec pick_n
    lda pick_n
    inc a
cancel_ready:
    sta pick_cancel
    iny
    sty pick_table
    stz pick_sel                ; `Window_Selectable` starts with the index at
                                ; zero, and the first option is highlighted
    lda #PICK_CHOICE
    sta pick_active
    jsr pick_open
    rts


.endproc


; `InputNumber`, with the `ShowMessage` before it: opens the message's window
; and ends the frame, like `op_message`. The digits go on the line below the
; text once it is composed, and from there it is `number_tick`'s, through
; `choice_tick`: see number_input.s. The cursor is left on the next command,
; and the page goes on from there when the player presses A.
;
; A parallel waits for someone else's window, as with a message. Opening is
; `number_open`'s, in bank 1, and then `op_message`'s from its box on: in bank
; 0 this is the guard and two jumps. There is no troop page branch, as
; `op_message` has: the troop pages' filter, `TROOP_COMMANDS` in the event
; compiler, does not take `InputNumber`.
.proc op_number
    lda pair_ev
    cmp #$FF
    beq open                    ; foreground
    lda msg_open
    ora msg_state
    ora pick_active
    beq open
    dey                         ; the cursor goes back to this same opcode
    sty ev_cur
    rts
open:
    jsl number_open             ; leaves Y on the box
    jmp op_message::window
.endproc

; `MessageOptions`: the byte goes as is to `FAR_MSG_OPTIONS`, already in the
; shape the console reads —see there—. Nothing changes on screen until the next
; window opens: `msg_place` reads it then. In a troop page it is written too,
; as `SaveSystem` is in RM2k, and the battle does not look at it.
.proc op_message_options
    lda [code_ptr], y
    iny
    sta f:FAR_LENGTH + FAR_MSG_OPTIONS
    jmp run_code::other
.endproc
