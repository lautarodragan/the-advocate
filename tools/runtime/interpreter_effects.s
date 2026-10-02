.segment "CODE"
.a8
.i16

; --- the interpreter: pictures, animation and weather ----------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; The three of the pictures, which live in bank 1: see picture_far.s. None of
; them ends the frame: if the page waits for as long as a fade lasts, the
; compiler puts an OP_DELAY after it, same as for `FlashScreen` and the
; shake.
.proc op_picture
    jsl f:pic_show + FAST       ; see MEMSEL
    jmp run_code::other
.endproc

.proc op_picture_move
    jsl f:pic_move + FAST
    jmp run_code::other
.endproc

.proc op_picture_erase
    jsl f:pic_erase + FAST
    jmp run_code::other
.endproc

; `OP_ANIMATION`: the RM2k animation number, what it is drawn on, how many
; entries, and the entries, which stay in the bytecode. See OP_ANIMATION in
; events.py and `battle_anim_tick`. The new one replaces whatever was running,
; and it costs no tick.
;
; The first two bytes are for the **drawing**, which runs on its own and lasts
; longer than the timeline: see `anim_drawing_start`.
.proc op_animation
    lda [code_ptr], y           ; the RM2k animation number
    sta temp
    iny
    lda [code_ptr], y           ; and what it goes on: $FF is the screen
    sta temp + 1
    iny
    phy
    jsr anim_drawing_start
    ply
    lda [code_ptr], y           ; how many
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

