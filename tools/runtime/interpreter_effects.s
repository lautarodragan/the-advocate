.segment "CODE"
.a8
.i16

; --- the interpreter: pictures, animation and weather ----------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; The three for the sign. `OP_PICTURE` shows it already with its tone
; —`Game_Pictures::Show` leaves `time_left` at zero—, `OP_PICTURE_MOVE` starts
; the ramp toward another tone and `OP_PICTURE_ERASE` removes it. None of them
; ends the frame: if the page waits for as long as the fade lasts, the
; converter puts an OP_DELAY after it, same as for `FlashScreen` and the
; shake.
.proc op_picture
    ldx #$0000
img_set:
    lda [code_ptr], y
    cpx #3
    bcs img_set_sat           ; the fourth operand is the saturation, which
    sta f:PICTURE_TONE, x        ; is not stored: the picture's is always neutral
    sta f:PICTURE_FROM, x
    sta f:PICTURE_TO, x
img_set_sat:
    iny
    inx
    cpx #4
    bne img_set
    lda #1
    sta f:PICTURE_ACTIVE
    lda #0
    sta f:PICTURE_STEP
    sta f:PICTURE_STEPS
    jsr picture_palette
    jmp run_code::other

.endproc

.proc op_picture_move
    ldx #$0000
img_move:
    lda [code_ptr], y
    cpx #3
    bcs img_move_sat           ; the saturation, again
    sta f:PICTURE_TO, x
img_move_sat:
    iny
    inx
    cpx #4
    bne img_move
    lda [code_ptr], y
    sta f:PICTURE_STEPS
    iny
    ; A `Move` on a picture that was not shown writes the target to something
    ; that is not drawn: the operands are consumed anyway —the stream has to
    ; stay on the same byte on both sides— and nothing else happens.
    lda f:PICTURE_ACTIVE
    beq img_move_end
    lda f:PICTURE_STEPS
    bne img_move_ramp
    ldx #$0000
img_move_already:
    lda f:PICTURE_TO, x
    sta f:PICTURE_TONE, x
    sta f:PICTURE_FROM, x
    inx
    cpx #3
    bne img_move_already
    lda #0
    sta f:PICTURE_STEP
    jsr picture_palette
    jmp run_code::other
img_move_ramp:
    ldx #$0000
img_move_from:
    lda f:PICTURE_TONE, x
    sta f:PICTURE_FROM, x
    inx
    cpx #3
    bne img_move_from
    lda #0
    sta f:PICTURE_STEP
img_move_end:
    jmp run_code::other

.endproc

.proc op_picture_erase
    lda #0
    sta f:PICTURE_ACTIVE
    jmp run_code::other

.endproc

; `OP_ANIMATION`: the RM2k animation number, what it is drawn on, how many
; entries, and the entries, which stay in the bytecode. See OP_ANIMATION in
; eventos.py and `battle_anim_tick`. The new one replaces whatever was running,
; and it costs no tick.
;
; The first two bytes are for the **drawing**, which runs on its own and lasts
; longer than the timeline: see `anim_drawing_start`.
.proc op_animation
    lda [code_ptr], y            ; the RM2k animation number
    sta temp
    iny
    lda [code_ptr], y            ; and what it goes on: $FF is the screen
    sta temp + 1
    iny
    phy
    jsr anim_drawing_start
    ply
    lda [code_ptr], y            ; how many
    sta f:ANIM_N
    iny
    rep #$20
.a16
    tya
    clc
    adc code_ptr
    sta f:ANIM_PTR              ; the first one, in the bytecode's bank
    sep #$20
.a8
    lda code_ptr + 2
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
    jmp run_code::other

.endproc

; `WeatherEffects`: the type and the strength. It costs no tick.
.proc op_weather
.a8
.i16
    lda [code_ptr], y
    sta temp
    iny
    lda [code_ptr], y
    sta temp + 1
    iny
    phy
    jsr weather_set
    ply
    jmp run_code::other

.endproc

