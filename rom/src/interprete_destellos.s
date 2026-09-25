.segment "CODE"
.a8
.i16

; --- el intérprete: el temblor y los destellos -----------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `ShakeScreen`: `ShakeOnce`, que no reinicia la posición para que dos
; sacudidas seguidas se encadenen suaves, o `ShakeEnd` con cero cuadros. No
; corta el cuadro: si la página espera, el conversor le pone un OP_DELAY
; detrás, como con los destellos.
.proc op_shake
    lda [cod_ptr], y            ; fuerza
    sta sacudida_fuerza
    iny
    lda [cod_ptr], y            ; velocidad
    sta sacudida_vel
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; cuadros
    sta sacudida_resta
    bne con_cuadros
    stz sacudida_pos            ; ShakeEnd: la pantalla vuelve a su lugar
con_cuadros:
    iny
    iny
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; `FlashOnce`: el color, el nivel a escala 256 y los cuadros. No corta el
; cuadro: si la página espera, el conversor le pone un OP_DELAY detrás.
.proc op_flash_screen
    jsr destello_de_codigo
    jmp correr_codigo::otro

.endproc

; Arranca un destello sobre un personaje. No corta el cuadro: si la página
; espera, el conversor le pone un OP_DELAY detrás, que es exactamente lo que
; hace `CommandFlashSprite` con `SetupWait(tenths)`.
.proc op_flash
    phy
    jsr flash_empezar
    ply
    rep #$20
.a16
    tya
    clc
    adc #6                      ; los seis operandos
    tay
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

