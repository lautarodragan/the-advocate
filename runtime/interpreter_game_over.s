.segment "CODE"
.a8
.i16

; --- the interpreter: Game Over --------------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `ReturntoTitleScreen` and `GameOver`: the first goes back to boot —the
; title screen, if the ROM has one— and the second goes through the Game Over
; screen first, which is the same as losing a battle with no defeat handler:
; see runtime/game_over.s. Both with `jml`: there is nowhere to return
; to.
;
; They share everything but the ending, and the high byte of A says which one
; it is: `op_return_to_title` loads 0 and skips the `lda #1` with the byte of
; an absolute `bit`, which swallows the next two bytes without touching A. It
; is a trick, and it is there because in bank 0 every byte counts. `xba` keeps
; it in B while the rest looks only at the low byte.
;
; Before that, what `CommandGameOver` and `CommandReturnToTitleScreen` ask
; for: **that no message is open**. If one is, they wait, like `op_message`
; does with someone else's. The foreground never gets here with one open
; —`events_tick` does not call it—; a parallel one does, and without this the
; restart would swallow the message another one is showing.
.proc op_return_to_title
    lda #0
    .byte $2C                   ; bit abs: swallows the `lda #1` below
.endproc
.proc op_game_over
    lda #1
    xba
    lda pair_ev
    cmp #$FF
    beq game_over_already       ; foreground
    lda msg_open
    ora msg_state
    ora pick_active
    beq game_over_already
    dey                         ; the cursor goes back to this same opcode
    sty ev_cur
    rts
game_over_already:
    xba                         ; and Z, from whichever it was: 0 is back to the title
    beq to_title
    jml f:game_over_from_map
to_title:
    jml f:reset

.endproc

