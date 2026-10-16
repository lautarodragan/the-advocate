.segment "CODE"
.a8
.i16

; --- the interpreter: the camera and the tint ------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `PanScreen`, in its four operations: lock the camera and unlock it —see
; `pan_lock_set`, in camera.s—, and move it away from the hero and bring it
; back. The offset comes signed and in 1/16 of a pixel, and the
; per-frame step already resolved; what is counted here are the frames the
; page waits, which come from **what is left** after moving the target and
; not from what this command asked for. See `GetPanWait`.
.proc op_pan
    lda [code_ptr], y           ; the operation
    iny
    cmp #PAN_RUN
    bcs moves
    jsr pan_lock_set            ; lock or unlock, which never wait
    iny                         ; their six bytes, at zero
    iny
    iny
    iny
    iny
    iny
    jmp run_code::other
moves:
    cmp #PAN_RETURN
    bne pan_run
    rep #$20
.a16
    stz pan_dest_x              ; going back is going to zero
    stz pan_dest_y
    sep #$20
.a8
    bra pan_skip_after
pan_run:
    rep #$20
.a16
    lda [code_ptr], y           ; the x offset, signed
    clc
    adc pan_dest_x
    sta pan_dest_x
    iny
    iny
    lda [code_ptr], y           ; and the y one
    clc
    adc pan_dest_y
    sta pan_dest_y
    sep #$20
.a8
    iny                         ; the two bytes of y
    iny
    bra pan_read_step
pan_skip_after:
    iny                         ; the four bytes of the offset
    iny
    iny
    iny
pan_read_step:
    lda [code_ptr], y           ; the per-frame step
    iny
    rep #$20
.a16
    and #$00FF
    sta pan_step
    sep #$20
.a8
    lda [code_ptr], y           ; whether the page waits
    iny
    beq pan_no_wait
    jsr pan_frames
    rep #$20
.a16
    sta ev_waiting
    ora #$0000                  ; `sta` does not touch the flags
    sep #$20
.a8
    ; Zero frames —the camera was already where it is going— and the page
    ; **continues in this same frame**: `CommandPanScreen` sets `wait_time =
    ; GetPanWait()` and returns true, and the interpreter loop only stops if
    ; `wait_time` is greater than zero. This used to end the frame anyway, and
    ; door EV0009 on map 8 —a "go back" with wait and then the Teleport—
    ; reached map 9 one tick late: the car in Lashe City 33,36 was 4 px
    ; behind, measured on 2026-09-10. `snes-pan 6 "3 0 0 4 1"` catches it.
    beq pan_no_wait
    sty ev_cur
    rts
pan_no_wait:
    jmp run_code::other

.endproc

.proc op_tint
    lda [code_ptr], y
    sta tint_r
    iny
    lda [code_ptr], y
    sta tint_g
    iny
    lda [code_ptr], y
    sta tint_b
    iny
    lda [code_ptr], y
    sta tint_s
    iny
    ; The tint is not applied here: it is requested, and `flush_video` does it
    ; in the next vblank. `apply_tint` uploads three palettes to CGRAM by
    ; DMA, and with the PPU drawing those writes are lost. While the
    ; interpreter ran inside `enter_map`, with the screen off, it did not
    ; matter; when it moved to the main loop it started running with the
    ; screen on and the tint came in halfway —the upper layer and one sprite
    ; were tinted and the rest not, depending on which write the vblank
    ; caught—.
    lda #1
    sta tint_pending
    jmp run_code::other         ; `bra` does not reach: the loop is far away

.endproc

