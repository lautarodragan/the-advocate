.segment "CODE"
.a8
.i16

; --- the interpreter: pictures, animation and weather ----------------------
;
; Opcode handlers: the dispatch in `correr_codigo`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.

; The three for the sign. `OP_PICTURE` shows it already with its tone
; —`Game_Pictures::Show` leaves `time_left` at zero—, `OP_PICTURE_MOVE` starts
; the ramp toward another tone and `OP_PICTURE_ERASE` removes it. None of them
; ends the frame: if the page waits for as long as the fade lasts, the
; converter puts an OP_DELAY after it, same as for `FlashScreen` and the
; shake.
.proc op_picture
    ldx #$0000
img_poner:
    lda [cod_ptr], y
    cpx #3
    bcs img_poner_sat           ; the fourth operand is the saturation, which
    sta f:CARTEL_TONO, x        ; is not stored: the sign's is always neutral
    sta f:CARTEL_DESDE, x
    sta f:CARTEL_HASTA, x
img_poner_sat:
    iny
    inx
    cpx #4
    bne img_poner
    lda #1
    sta f:CARTEL_ACTIVA
    lda #0
    sta f:CARTEL_PASO
    sta f:CARTEL_PASOS
    jsr imagen_paleta
    jmp correr_codigo::otro

.endproc

.proc op_picture_move
    ldx #$0000
img_mover:
    lda [cod_ptr], y
    cpx #3
    bcs img_mover_sat           ; the saturation, again
    sta f:CARTEL_HASTA, x
img_mover_sat:
    iny
    inx
    cpx #4
    bne img_mover
    lda [cod_ptr], y
    sta f:CARTEL_PASOS
    iny
    ; A `Move` on a picture that was not shown writes the target to something
    ; that is not drawn: the operands are consumed anyway —the stream has to
    ; stay on the same byte on both sides— and nothing else happens.
    lda f:CARTEL_ACTIVA
    beq img_mover_fin
    lda f:CARTEL_PASOS
    bne img_mover_rampa
    ldx #$0000
img_mover_ya:
    lda f:CARTEL_HASTA, x
    sta f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_ya
    lda #0
    sta f:CARTEL_PASO
    jsr imagen_paleta
    jmp correr_codigo::otro
img_mover_rampa:
    ldx #$0000
img_mover_desde:
    lda f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_desde
    lda #0
    sta f:CARTEL_PASO
img_mover_fin:
    jmp correr_codigo::otro

.endproc

.proc op_picture_erase
    lda #0
    sta f:CARTEL_ACTIVA
    jmp correr_codigo::otro

.endproc

; `OP_ANIMATION`: the RM2k animation number, what it is drawn on, how many
; entries, and the entries, which stay in the bytecode. See OP_ANIMATION in
; eventos.py and `animacion_tick`. The new one replaces whatever was running,
; and it costs no tick.
;
; The first two bytes are for the **drawing**, which runs on its own and lasts
; longer than the timeline: see `animacion_dibujo_empezar`.
.proc op_animation
    lda [cod_ptr], y            ; the RM2k animation number
    sta temp
    iny
    lda [cod_ptr], y            ; and what it goes on: $FF is the screen
    sta temp + 1
    iny
    phy
    jsr animacion_dibujo_empezar
    ply
    lda [cod_ptr], y            ; how many
    sta f:ANIM_N
    iny
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta f:ANIM_PTR              ; the first one, in the bytecode's bank
    sep #$20
.a8
    lda cod_ptr + 2
    sta f:ANIM_PTR + 2
    lda #0
    sta f:ANIM_T
    lda f:ANIM_N
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; eight bytes per entry
    sta temp
    tya
    clc
    adc temp
    tay
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; `WeatherEffects`: the type and the strength. It costs no tick.
.proc op_weather
.a8
.i16
    lda [cod_ptr], y
    sta temp
    iny
    lda [cod_ptr], y
    sta temp + 1
    iny
    phy
    jsr clima_poner
    ply
    jmp correr_codigo::otro

.endproc

