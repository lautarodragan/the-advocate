.segment "CODE"
.a8
.i16

; --- the interpreter: the timer --------------------------------------------
;
; Opcode handlers: the dispatch of `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; The timer: set, start or stop. The five operand bytes are fixed even though
; each operation uses two, so the cursor advances the same in all three.
.proc op_timer
    lda [code_ptr], y            ; the operation
    sta temp
    iny
    cmp #TIMER_PONER
    bne no_pone
    rep #$20
.a16
    lda [code_ptr], y            ; the seconds, sixteen bits
timer_poner_16:
    sta timer_sec
    sep #$20
.a8
    ; `Game_Party::SetTimer` stores `seconds * 60 + 59`: the extra 59 are what
    ; make the requested value show for a whole second and not a single frame.
    ; Here the frames are kept separately, so they are the remainder and
    ; nothing else.
    lda #TIMER_DE_MAS
    sta timer_sub
    jsr timer_digits
    bra timer_fin
no_pone:
    cmp #TIMER_PONER_VAR
    bne no_pone_var
    ; The seconds from a variable, which is what the Tram Officer on map 9
    ; does: "what the timer has left, minus sixty". A negative variable sets
    ; zero, like `Game_Party::SetTimer`.
    lda [code_ptr], y            ; the slot
    phy
    jsr var_read                ; 16-bit A
.a16
    ply
    cmp #0                      ; the variable's sign, which `ply` overwrote
                                ; with the cursor: see `song_ensure`
    bpl timer_poner_16
    lda #0
    bra timer_poner_16
.a8
no_pone_var:
    cmp #TIMER_ARRANCAR
    bne timer_para
    lda #1
    sta timer_active
    iny
    iny
    lda [code_ptr], y            ; whether it shows
    dey
    dey
    cmp timer_visible
    beq timer_fin               ; it already showed, or already didn't:
                                ; nothing to repaint
    sta timer_visible
    jsr timer_repaint          ; its palette entries change owner
    bra timer_fin
timer_para:
    ; `StopTimer` turns off both things, not just the count.
    lda timer_visible
    stz timer_active
    stz timer_visible           ; `stz` does not touch Z: the branch looks at
                                ; the `lda`
    beq timer_fin
    jsr timer_repaint
timer_fin:
    rep #$20
.a16
    tya
    clc
    adc #3                      ; the three remaining operands: the first one
    tay                         ; was consumed by the operation's `iny`
    sep #$20
.a8
    jmp run_code::otro

.endproc
