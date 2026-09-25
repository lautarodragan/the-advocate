.segment "CODE"

; --- los eventos que se dibujan caminando ------------------------------------
;
; Un evento con gráfico que camina cambia de tres cosas por cuadro: dónde está
; en pixeles, qué pose le toca del ciclo, y con qué clave se ordena contra los
; demás. Las tres se escriben en su fila de la tabla de NPCs, que es de donde
; `build_oam` lee.

; Un cuadro del ciclo de caminata de la ranura X. Es `animate_hero`, letra por
; letra, y por eso las dos hacen lo mismo: la referencia usa una sola fórmula
; —`columna_de_caminata`— para el héroe y para los eventos.
.proc animar_ruta_ev
.a8
.i16
    ; `Game_Character::UpdateAnimation`, sin el giro en el lugar. +10 es el
    ; frame del ciclo, 0 a 3 —el 3 dibuja la columna 1—, y +11 cuántos cuadros
    ; lleva en él. Con la animación parada o saltando, el frame del medio.
    lda ruta_ev + 12, x
    and #$02
    bne quieta
    lda ruta_ev + 13, x
    bne quieta
    ; Los límites, por velocidad.
    lda ruta_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda anim_parado, y
    sta temp
    lda anim_continua, y
    sta temp + 1
    ; La cuenta sube caminando, siempre con la animación continua, y quieto
    ; sólo hasta llegar al frame del medio.
    lda ruta_ev + 18, x
    and #$10
    bne suma
    lda ruta_ev + 6, x
    bne suma
    lda ruta_ev + 10, x
    and #$01
    beq suma                    ; en el frame 0 o 2 sigue hasta el del medio
    lda ruta_ev + 11, x
    inc a
    cmp temp
    bcc suma                    ; cuenta < parado - 1
    bra ver_cambio
suma:
    inc ruta_ev + 11, x
ver_cambio:
    lda ruta_ev + 11, x
    cmp temp + 1
    bcs cambia                  ; llegó a la de continua
    lda ruta_ev + 6, x
    beq listo
    lda ruta_ev + 11, x
    cmp temp
    bcc listo                   ; caminando, a la de parado
cambia:
    lda ruta_ev + 10, x
    inc a
    and #$03                    ; el ciclo son cuatro pasos
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
listo:
    rts
quieta:
    lda #1
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
    rts
.endproc

; La fila de la tabla de NPCs del evento que trae A, en Y, o $FFFF si no tiene.
; Todas las filas llevan su índice de evento, y los índices son únicos, así que
; a lo sumo matchea una. Un evento sin gráfico no tiene fila y devuelve $FFFF.
.proc npc_de_evento
.a8
.i16
    sta temp
    ldy #$0000
buscar:
    cpy npc_total
    beq no_hay
    lda npc_buf + 8, y
    cmp temp
    beq listo
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra buscar
no_hay:
    ldy #$FFFF
listo:
    rts
.endproc

; Lo que le falta a `op_place` después de escribir la celda: que el dibujo la
; siga. Entra con el índice del evento en `temp`.
;
; Si el evento tiene ranura de ruta alcanza con cortarle el paso y el salto:
; `mover_eventos` corre después en este mismo cuadro y `refrescar_npc` lo deja
; sobre la celda nueva, con la pose que venía. Si no la tiene —un evento que
; nadie mandó a caminar— no se le da una: no se lleva ranura por esto, y su
; fila se mueve a mano, sin tocarle el tile, que es la pose de su página.
.proc plantar_evento
.a8
.i16
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp temp
    beq con_ranura
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar

    ; Sin ranura. Si tampoco tiene gráfico no hay nada que mover.
    lda temp
    jsr npc_de_evento
    cpy #$FFFF
    beq listo
    sty npc_fila
    lda temp
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    lda ev_pos_buf + 0, x       ; la celda por dieciséis: está parado en ella
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 0, y
    lda ev_pos_buf + 2, x
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 2, y
    sta npc_py
    lda npc_buf + 4, y
    and #$F000                  ; la capa se queda; la Y se reemplaza
    sta temp + 2
    lda npc_py
    and #$0FFF
    ora temp + 2
    sta npc_buf + 4, y
    sep #$20
.a8
    lda #0
    sta npc_buf + 11, y         ; sin salto: nada que levantar
    jmp acomodar_npc            ; y la fila, a donde le toque ahora

con_ranura:
    lda #0
    sta ruta_ev + 7, x          ; sin paso en curso
    sta ruta_ev + 22, x
    sta ruta_ev + 23, x
    sta ruta_ev + 13, x         ; ni salto
listo:
    rts
.endproc

