.segment "CODE"
.a8
.i16

; --- el intérprete: el cronómetro ------------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; El cronómetro: poner, arrancar o parar. Los cinco bytes de operando son fijos
; aunque cada operación use dos, así que el cursor avanza igual en las tres.
.proc op_timer
    lda [cod_ptr], y            ; la operación
    sta temp
    iny
    cmp #TIMER_PONER
    bne no_pone
    rep #$20
.a16
    lda [cod_ptr], y            ; los segundos, de dieciséis bits
timer_poner_16:
    sta timer_seg
    sep #$20
.a8
    ; `Game_Party::SetTimer` guarda `segundos * 60 + 59`: los 59 de más son lo
    ; que hace que el valor pedido se vea un segundo entero y no un cuadro.
    ; Acá los cuadros van partidos, así que son el resto y nada más.
    lda #TIMER_DE_MAS
    sta timer_sub
    jsr timer_digitos
    bra timer_fin
no_pone:
    cmp #TIMER_PONER_VAR
    bne no_pone_var
    ; Los segundos desde una variable, que es lo que hace el Tram Officer del
    ; mapa 9: "lo que le queda al cronómetro, menos sesenta". Una variable
    ; negativa pone cero, como `Game_Party::SetTimer`.
    lda [cod_ptr], y            ; la ranura
    phy
    jsr var_leer                ; A de dieciséis bits
.a16
    ply
    cmp #0                      ; el signo de la variable, que `ply` pisó con
                                ; el cursor: ver `tema_asegurar`
    bpl timer_poner_16
    lda #0
    bra timer_poner_16
.a8
no_pone_var:
    cmp #TIMER_ARRANCAR
    bne timer_para
    lda #1
    sta timer_activo
    iny
    iny
    lda [cod_ptr], y            ; si se ve
    sta timer_visible
    dey
    dey
    bra timer_fin
timer_para:
    ; `StopTimer` apaga las dos cosas, no sólo la cuenta.
    stz timer_activo
    stz timer_visible
timer_fin:
    rep #$20
.a16
    tya
    clc
    adc #3                      ; los tres operandos que quedan: el primero ya
    tay                         ; lo consumió el `iny` de la operación
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

