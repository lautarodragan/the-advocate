.segment "CODE"
.a8
.i16

; --- the teleport transition -------------------------------------------------
;
; RM2k erases and shows the screen again on every teleport with whatever
; transition the system says, and `ChangeScreenTransitions` changes it from
; then on. The ROM does three, and the converter has already decided which one
; goes —see `CHANGE_SCREEN_TRANSITIONS` in tools/port/eventos.py—:
;
;   the fade     the usual one, `fundido_tick`: the master brightness over
;                `fundido_rampa`. It is also what goes for the ones the
;                console does not do, like the zoom
;   the mosaic   the same fade, plus the MOSAIC register tied to the
;                brightness: size 16 at brightness 0, size 1 at brightness
;                15, which is what the battle does —see `fundido_de_pelea.s`,
;                which explains why the mosaic also darkens, and in RM2k it
;                does not: the load has to fall inside the black—
;   the cut      only for erasing: the fade started at its last outgoing
;                frame, so the first frame is already black and loads the
;                map, and the way back is the usual one. `fundido_desde` sets
;                it
;
; The PPU's mosaic is for the backgrounds and nothing else: **sprites do not
; get pixelated**, and in RM2k they do, because there the whole screen gets
; pixelated. With the brightness going down at the same time it is barely
; noticeable; it is in
; workflow/divergencias/las-transiciones-del-teletransporte.md.
;
; `fundido_tick` does not need to be touched for this: the mosaic is deduced
; from what the fade already carries —whether there is one, whether the load is
; still pending, and this frame's brightness— and written in the vblank, next
; to the brightness, in `fundido_mosaico`.

; `ChangeScreenTransitions`: which one —0 erase, 1 show— and the transition.
; Only the jump stays in bank 0, because the dispatch wants the handler here and
; bank 0 has no room to spare.
.proc op_transition
    jsl f:transicion_poner
    jmp correr_codigo::otro
.endproc

.segment "FAR"

; The body of `op_transition`: with Y at the first operand, and it returns with
; Y past the last one. The bytecode is read with `[cod_ptr], y`, which does not
; depend on the data bank, and far RAM with `f:`.
.proc transicion_poner
.a8
.i16
    lda [cod_ptr], y            ; which: 0 erase, 1 show
    iny
    lsr a                       ; into the carry
    lda [cod_ptr], y            ; the transition
    iny
    bcs mostrar
    sta f:TRANSICION_BORRAR
    rtl
mostrar:
    sta f:TRANSICION_MOSTRAR
    rtl
.endproc

; The byte of `vueltas` from which the fade being started counts, into
; `fundido_base`. From `empezar_fundido`.
;
; With the cut for erasing it starts `FUNDIDO_CUADROS - 1` ticks back: the
; first `fundido_tick` lands on the last frame of the outgoing half, which is
; already past `FUNDIDO_CARGA` —so it loads the map right there— and in the
; black in the middle. It is `TransitionCutOut`, which lasts one frame in RM2k,
; followed by the usual show. `fundido_tick` knows nothing about it.
.assert FUNDIDO_CARGA < FUNDIDO_CUADROS, error, "the cut has to land past the load"
.proc fundido_desde
.a8
.i16
    lda f:TRANSICION_BORRAR
    cmp #TRANSICION_CORTE
    beq corte
    lda vueltas
    bra poner
corte:
    lda vueltas
    sec
    sbc #(FUNDIDO_CUADROS - 1)
poner:
    sta f:fundido_base
    rtl
.endproc

; Both set to the fade, from reset: far RAM starts with garbage in bsnes, and
; the first teleport would come out as a mosaic if it happened to land that
; way. Any value that is neither TRANSICION_MOSAICO nor TRANSICION_CORTE is the
; fade.
.assert TRANSICION_MOSAICO <> 0, error, "zero has to be the fade"
.assert TRANSICION_CORTE <> 0, error, "zero has to be the fade"
.proc transicion_de_arranque
.a8
.i16
    lda #0
    sta f:TRANSICION_BORRAR
    sta f:TRANSICION_MOSTRAR
    rtl
.endproc

; This frame's mosaic. From `flush_video`, in the vblank and right before
; writing the brightness, so both change on the same frame.
;
; While the map load is pending —`fundido_que` nonzero— the fade is erasing the
; screen; afterwards it is showing it. With no fade, or with one that is not a
; mosaic, it turns it off: it is written every frame, so nobody else has to
; remember to turn it off. `fundido`, `fundido_que` and `brillo` live in bank
; 0's BSS, and are read with `f:` so as not to depend on the data bank.
.proc fundido_mosaico
.a8
.i16
    lda f:fundido
    beq apagado
    lda f:fundido_que
    beq mostrando
    lda f:TRANSICION_BORRAR
    bra mirar
mostrando:
    lda f:TRANSICION_MOSTRAR
mirar:
    cmp #TRANSICION_MOSAICO
    bne apagado
    lda f:brillo
    eor #$0F                    ; the size, the reverse of the brightness
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 and BG2: the map and the layer above
    bra escribir
apagado:
    lda #0
escribir:
    sta f:MOSAIC
    rtl
.endproc
