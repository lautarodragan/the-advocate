; `PanScreen`, en sus dos operaciones: correr la cámara sin el héroe y
; devolverla. El desplazamiento viene con signo y en 1/16 de pixel, y el paso
; por cuadro ya resuelto; lo que se cuenta acá son los cuadros que la página
; espera, que salen de **lo que falta** después de mover el destino y no de lo
; que este comando pidió. Ver `GetPanWait`.
.proc op_pan
    lda [cod_ptr], y            ; la operación
    iny
    cmp #PAN_VOLVER
    bne pan_correr
    rep #$20
.a16
    stz pan_dest_x              ; volver es ir al cero
    stz pan_dest_y
    sep #$20
.a8
    bra pan_saltear_desp
pan_correr:
    rep #$20
.a16
    lda [cod_ptr], y            ; el desplazamiento en x, con signo
    clc
    adc pan_dest_x
    sta pan_dest_x
    iny
    iny
    lda [cod_ptr], y            ; y en y
    clc
    adc pan_dest_y
    sta pan_dest_y
    sep #$20
.a8
    iny                         ; los dos de la y
    iny
    bra pan_leer_paso
pan_saltear_desp:
    iny                         ; los cuatro bytes del desplazamiento
    iny
    iny
    iny
pan_leer_paso:
    lda [cod_ptr], y            ; el paso por cuadro
    iny
    rep #$20
.a16
    and #$00FF
    sta pan_paso
    sep #$20
.a8
    lda [cod_ptr], y            ; si la página espera
    iny
    beq pan_sin_espera
    jsr pan_cuadros
    rep #$20
.a16
    sta ev_esperando
    ora #$0000                  ; `sta` no toca las banderas
    sep #$20
.a8
    ; Cero cuadros —la cámara ya estaba donde va— y la página **sigue en este
    ; mismo cuadro**: `CommandPanScreen` pone `wait_time = GetPanWait()` y
    ; devuelve true, y el lazo del intérprete sólo se detiene si `wait_time`
    ; es mayor que cero. Acá se cortaba el cuadro igual, y la puerta EV0009 del
    ; mapa 8 —un "volver" con espera y después el Teleport— llegaba al mapa 9
    ; un tick después que la referencia: el auto de Lashe City 33,36 iba 4 px
    ; atrás, medido el 2026-09-10. Lo cobra `snes-pan 6 "3 0 0 4 1"`.
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
    ; El tinte no se aplica acá: se pide, y lo hace `flush_video` en el vblank
    ; siguiente. `aplicar_tinte` sube tres paletas a CGRAM por DMA, y con el PPU
    ; dibujando esas escrituras se pierden. Mientras el intérprete corría adentro
    ; de `cargar_mapa`, con la pantalla apagada, no hacía falta; al mudarlo al
    ; lazo principal pasó a ejecutarse con la pantalla encendida y el tinte
    ; entraba a medias —quedaban teñidos la capa de encima y un sprite, y el
    ; resto no, según qué escritura pescara el vblank—.
    lda #1
    sta tinte_pendiente
    jmp correr_codigo::otro     ; `bra` no llega: el lazo quedó lejos

.endproc

