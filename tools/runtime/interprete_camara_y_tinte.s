.segment "CODE"
.a8
.i16

; --- the interpreter: the camera and the tint ------------------------------
;
; Opcode handlers: the dispatch in `correr_codigo`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.

; `PanScreen`, in its two operations: move the camera away from the hero and
; bring it back. The offset comes signed and in 1/16 of a pixel, and the
; per-frame step already resolved; what is counted here are the frames the
; page waits, which come from **what is left** after moving the target and
; not from what this command asked for. See `GetPanWait`.
.proc op_pan
    lda [cod_ptr], y            ; the operation
    iny
    cmp #PAN_VOLVER
    bne pan_correr
    rep #$20
.a16
    stz pan_dest_x              ; going back is going to zero
    stz pan_dest_y
    sep #$20
.a8
    bra pan_saltear_desp
pan_correr:
    rep #$20
.a16
    lda [cod_ptr], y            ; the x offset, signed
    clc
    adc pan_dest_x
    sta pan_dest_x
    iny
    iny
    lda [cod_ptr], y            ; and the y one
    clc
    adc pan_dest_y
    sta pan_dest_y
    sep #$20
.a8
    iny                         ; the two bytes of y
    iny
    bra pan_leer_paso
pan_saltear_desp:
    iny                         ; the four bytes of the offset
    iny
    iny
    iny
pan_leer_paso:
    lda [cod_ptr], y            ; the per-frame step
    iny
    rep #$20
.a16
    and #$00FF
    sta pan_paso
    sep #$20
.a8
    lda [cod_ptr], y            ; whether the page waits
    iny
    beq pan_sin_espera
    jsr pan_cuadros
    rep #$20
.a16
    sta ev_esperando
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
    beq pan_sin_espera
    sty ev_cur
    rts
pan_sin_espera:
    jmp correr_codigo::otro

.endproc

.proc op_tint
    lda [cod_ptr], y
    sta tinte_r
    iny
    lda [cod_ptr], y
    sta tinte_g
    iny
    lda [cod_ptr], y
    sta tinte_b
    iny
    lda [cod_ptr], y
    sta tinte_s
    iny
    ; The tint is not applied here: it is requested, and `flush_video` does it
    ; in the next vblank. `aplicar_tinte` uploads three palettes to CGRAM by
    ; DMA, and with the PPU drawing those writes are lost. While the
    ; interpreter ran inside `cargar_mapa`, with the screen off, it did not
    ; matter; when it moved to the main loop it started running with the
    ; screen on and the tint came in halfway —the upper layer and one sprite
    ; were tinted and the rest not, depending on which write the vblank
    ; caught—.
    lda #1
    sta tinte_pendiente
    jmp correr_codigo::otro     ; `bra` does not reach: the loop is far away

.endproc

