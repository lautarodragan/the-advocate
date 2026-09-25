.segment "CODE"
.a8
.i16

; `OP_SOUND`: el índice en `sonido_tabla`. Queda pendiente y arranca al
; final de `music_tick`, detrás de lo que la música escriba en el cuadro.
.proc op_sound
    jsr sonido_de_codigo
    jmp correr_codigo::otro

.endproc

; Los tres del cartel. `OP_PICTURE` lo pone ya con su tono —`Game_Pictures::
; Show` deja `time_left` en cero—, `OP_PICTURE_MOVE` arranca la rampa hacia
; otro tono y `OP_PICTURE_ERASE` lo saca. Ninguno corta el cuadro: si la página
; espera lo que dura el fundido, el conversor le pone un OP_DELAY detrás,
; igual que al `FlashScreen` y a la sacudida.
.proc op_picture
    ldx #$0000
img_poner:
    lda [cod_ptr], y
    cpx #3
    bcs img_poner_sat           ; el cuarto operando es la saturación, que no
    sta f:CARTEL_TONO, x        ; se guarda: la del cartel es siempre la neutra
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
    bcs img_mover_sat           ; la saturación, otra vez
    sta f:CARTEL_HASTA, x
img_mover_sat:
    iny
    inx
    cpx #4
    bne img_mover
    lda [cod_ptr], y
    sta f:CARTEL_PASOS
    iny
    ; Un `Move` sobre una imagen que no se mostró le escribe el destino a algo
    ; que no se dibuja: los operandos se consumen igual —el stream tiene que
    ; seguir en el mismo byte de los dos lados— y no pasa nada más.
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

; `OP_ANIMATION`: el número de animación de RM2k, sobre qué se dibuja, cuántas
; entradas y las entradas, que se quedan en el bytecode. Ver OP_ANIMATION en
; eventos.py y `animacion_tick`. La nueva reemplaza a la que hubiera, y no
; cuesta ningún tick.
;
; Los dos primeros bytes son del **dibujo**, que va por su cuenta y dura más
; que la línea de tiempo: ver `animacion_dibujo_empezar`.
.proc op_animation
    lda [cod_ptr], y            ; el número de animación de RM2k
    sta temp
    iny
    lda [cod_ptr], y            ; y sobre qué va: $FF es la pantalla
    sta temp + 1
    iny
    phy
    jsr animacion_dibujo_empezar
    ply
    lda [cod_ptr], y            ; cuántas
    sta f:ANIM_N
    iny
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta f:ANIM_PTR              ; la primera, en el banco del bytecode
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
    asl a                       ; ocho bytes por entrada
    sta temp
    tya
    clc
    adc temp
    tay
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; `WeatherEffects`: el tipo y la fuerza. No cuesta ningún tick.
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

