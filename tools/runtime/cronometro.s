.segment "CODE"

; --- el cronómetro ---------------------------------------------------------
; Un cuadro de la cuenta. Es `Game_Party::UpdateTimers`, y lo que importa es el
; final: al llegar a cero segundos RM2k llama a `StopTimer`, que apaga la cuenta
; **y la esconde**. O sea que el último valor que se ve es 00:01 y después no
; queda nada dibujado, no un 00:00 congelado.
.proc timer_tick
.a8
.i16
    lda timer_activo
    bne corre
    rts
corre:
    lda timer_sub
    beq otro_segundo
    dec timer_sub
    rts
otro_segundo:
    lda #(TIMER_CUADROS - 1)
    sta timer_sub
    rep #$20
.a16
    lda timer_seg
    beq apagar_16               ; ya estaba en cero: no hay qué bajar
    dec a
    sta timer_seg
    sep #$20
.a8
    jsr timer_digitos
    lda timer_seg
    ora timer_seg + 1
    beq apagar
    rts
.a16
apagar_16:
    sep #$20
.a8
apagar:
    stz timer_activo
    lda timer_visible
    stz timer_visible           ; `stz` no toca Z: el salto mira el `lda`
    beq ya_no_se_veia
    jsr timer_repintar          ; sus entradas vuelven a teñirse
ya_no_se_veia:
    rts
.endproc

; Los cuatro dígitos de `timer_seg`, de los minutos a los segundos. Se llama
; cuando el segundo cambia y no en cada cuadro: son dos divisiones por restas
; sucesivas, y a 60 hercios serían sesenta veces el mismo resultado.
;
; Los minutos entran en dos dígitos porque el conversor no deja pasar un
; cronómetro de más de 1092 segundos: el tope se lo pone la cuenta de cuadros
; en dieciséis bits, no la pantalla.
.proc timer_digitos
.a8
.i16
    rep #$20
.a16
    lda timer_seg
    ldx #0
menos_60:
    cmp #60
    bcc listo_60
    sec
    sbc #60
    inx
    bra menos_60
listo_60:
    sta temp                    ; los segundos sueltos
    txa
    sta temp + 2                ; y los minutos
    sep #$20
.a8

    lda temp + 2                ; los minutos, en dos dígitos
    ldx #0
menos_10a:
    cmp #10
    bcc listo_10a
    sec
    sbc #10
    inx
    bra menos_10a
listo_10a:
    sta timer_dig + 1
    txa                         ; con A de ocho bits es el byte bajo de X
    sta timer_dig + 0

    lda temp                    ; y los segundos
    ldx #0
menos_10b:
    cmp #10
    bcc listo_10b
    sec
    sbc #10
    inx
    bra menos_10b
listo_10b:
    sta timer_dig + 3
    txa
    sta timer_dig + 2
    rts
.endproc

; Los cinco glifos del cronómetro en OAM, cada uno como dos objetos de 8x8
; apilados. Van **primero**, o sea en los objetos de índice más bajo, que son
; los que la consola pone adelante: en RM2k el cronómetro es `Priority_Timer`,
; que está por encima de todo lo demás, ventana de mensaje incluida. Acá eso lo
; da la prioridad 3 de objeto, que gana contra las dos capas.
;
; Los dos puntos parpadean: se dibujan sólo en la mitad de arriba del segundo,
; que es el `frames % 60 < 30 -> continue` de `Sprite_Timer::Draw`.
.proc timer_oam
.a8
.i16
    lda timer_visible
    bne hay
    rts
hay:
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_BASE, x
    ora f:mapa_tabla + M_TIMER_BASE + 1, x
    bne dibujar
    rts                         ; esta ROM no lleva los glifos
dibujar:
    stz obj_grande              ; los dígitos son de 8x8
    stz timer_i
cada_glifo:
    lda timer_i
    cmp #5
    bcc hay_glifo
    jmp fin
hay_glifo:
    cmp #2
    bne es_digito
    ; Los dos puntos, y sólo si toca.
    lda timer_sub
    cmp #(TIMER_CUADROS / 2)
    bcc siguiente
    lda #TIMER_DOS_PUNTOS
    bra con_glifo
es_digito:
    ; El índice en `timer_dig`: la posición, menos uno si va detrás de los dos
    ; puntos, que no tienen dígito propio.
    cmp #2
    bcc sin_ajuste
    dec a
sin_ajuste:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda timer_dig, x
con_glifo:
    sta timer_glifo
    stz timer_mitad
cada_mitad:
    ; Dónde cae en pantalla. La X no lleva el corrimiento de los personajes:
    ; los dígitos son de 8x8 y su esquina es su esquina.
    rep #$20
.a16
    lda timer_i
    and #$00FF
    ; Ocho por glifo, que es un corrimiento y no una multiplicación.
    asl a
    asl a
    asl a
    clc
    adc #TIMER_X
    sta obj_x
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc #TIMER_Y
    sta obj_y

    ; Y qué tile: los once glifos entran en una fila de dieciséis, así que la
    ; mitad de abajo está justo dieciséis más adelante.
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc timer_glifo             ; en dieciséis bits se lleva al byte de al
    and #$00FF                  ; lado, y por eso el `and`
    ldx mapa_ofs
    clc
    adc f:mapa_tabla + M_TIMER_BASE, x
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: prioridad 3 —adelante de las dos capas—, la paleta del
    ; cronómetro, y el noveno bit del tile.
    lda temp + 1
    and #$01
    sta temp + 2
    lda f:mapa_tabla + M_TIMER_PAL, x
    and #$07
    asl a
    ora #$30
    ora temp + 2
    sta obj_attr
    jsr emit_object

    inc timer_mitad
    lda timer_mitad
    cmp #2
    bcc cada_mitad
siguiente:
    inc timer_i
    jmp cada_glifo
fin:
    lda #$02                    ; y lo que siga vuelve a ser de 32x32
    sta obj_grande
    rts
.endproc

