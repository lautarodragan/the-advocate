.segment "CODE"
.a8
.i16

; --- the interpreter: the shake and the flashes ----------------------------
;
; Opcode handlers: the `run_code` dispatch, in interprete.s, jumps to
; each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; `ShakeScreen`: `ShakeOnce`, which does not reset the position so that two
; shakes in a row chain smoothly, or `ShakeEnd` with zero frames. It does not
; end the frame: if the page waits, the converter puts an OP_DELAY after it,
; as with the flashes.
.proc op_shake
    lda [cod_ptr], y            ; strength
    sta sacudida_fuerza
    iny
    lda [cod_ptr], y            ; speed
    sta sacudida_vel
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; frames
    sta sacudida_resta
    bne con_cuadros
    stz sacudida_pos            ; ShakeEnd: the screen goes back to its place
con_cuadros:
    iny
    iny
    sep #$20
.a8
    jmp run_code::otro

.endproc

; `FlashOnce`: the color, the level on a 256 scale, and the frames. It does
; not end the frame: if the page waits, the converter puts an OP_DELAY after
; it.
.proc op_flash_screen
    jsr flash_from_code
    jmp run_code::otro

.endproc

; Starts a flash on a character. It does not end the frame: if the page
; waits, the converter puts an OP_DELAY after it, which is exactly what
; `CommandFlashSprite` does with `SetupWait(tenths)`.
.proc op_flash
    phy
    jsr flash_start
    ply
    rep #$20
.a16
    tya
    clc
    adc #6                      ; the six operands
    tay
    sep #$20
.a8
    jmp run_code::otro

.endproc

