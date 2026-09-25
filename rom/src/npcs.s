.segment "CODE"

; Sube la pose A del NPC de la fila Y, si no es la que ya está en la VRAM.
;
; Salió de adentro de `refrescar_npc`, que era el único que la necesitaba, el
; día que hubo un segundo: `animar_quietos`. `npc_fila` tiene que traer la misma
; fila que Y, que es como venía.
.proc subir_pose_npc
.a8
.i16
    ; El tile de la fila es fijo —es su ranura— y lo que cambia son los tiles de
    ; la ranura, que se encolan acá y suben en el vblank que viene con la OAM.
    cmp npc_buf + 12, y
    bne cambia
    rts
cambia:
    sta npc_buf + 12, y
    sta temp                    ; la pose

    ; El puntero a la pose, de `npc_poses`: doce punteros de tres bytes por
    ; personaje animado, o sea (k * 12 + pose) * 3.
    lda npc_buf + 9, y
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; por cuatro
    sta temp + 2
    asl a
    asl a
    asl a                       ; por treinta y dos
    clc
    adc temp + 2                ; treinta y seis por personaje
    sta temp + 2
    lda temp
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; la pose por tres
    clc
    adc temp + 2
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2

    ; El destino: su ranura, que es el tile de la fila por dieciséis palabras
    ; desde donde arranca el banco de sprites.
    ldy npc_fila
    lda npc_buf + 7, y
    and #$01                    ; el bit 8 del tile vive en los atributos
    xba
    lda npc_buf + 6, y
    rep #$20
.a16
    asl a
    asl a
    asl a
    asl a                       ; dieciséis palabras por tile
    ldx mapa_ofs
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne listo
    ; La cola estaba llena: se vuelve a pedir el cuadro que viene.
    ldy npc_fila
    lda #$FF
    sta npc_buf + 12, y
listo:
    rts
.endproc

; Deja la fila del NPC de la ranura X donde el evento está ahora: la posición en
; pixeles, la clave con la que se ordena, y el tile de la pose que le toca.
;
; Lo primero que hace es copiarse de la ranura lo que necesita, y recién después
; usa X para otra cosa. Es más largo de leer y mucho más difícil de romper:
; adentro se llaman tres rutinas y todas usan índices.
.proc refrescar_npc
.a8
.i16
    stz salto_alto
    stz salto_alto + 1
    jsr celda_del_evento        ; deja su celda en celda_x/celda_y, y usa X
    lda ruta_ev + 7, x
    sta slot_cuadros            ; si hay un paso en curso
    rep #$20
.a16
    lda ruta_ev + 22, x         ; y cuánto le falta, de 256 por celda: a
    lsr a                       ; pixeles, tirando los dieciseisavos
    lsr a
    lsr a
    lsr a
    sta slot_px
    sep #$20
.a8
    lda ruta_ev + 8, x
    sta slot_mira
    lda ruta_ev + 30, x
    sta slot_dir                ; la dirección del paso en curso
    lda ruta_ev + 10, x
    sta slot_paso
    lda ruta_ev + 0, x
    jsr npc_de_evento
    sty npc_fila
    cpy #$FFFF
    bne hay_fila
    rts                         ; el evento no tiene gráfico: no hay qué mover
hay_fila:

    ; Dónde está, en pixeles: la celda por dieciséis, menos lo que le falte al
    ; paso en curso a WALK_SPEED por cuadro.
    rep #$20
.a16
    lda celda_x
    asl a
    asl a
    asl a
    asl a
    sta npc_px
    lda celda_y
    asl a
    asl a
    asl a
    asl a
    sta npc_py
    lda slot_px                 ; los pixeles que faltan del paso
    sta temp
    sep #$20
.a8
    lda slot_cuadros
    beq sin_paso_npc            ; sin paso en curso, ya está en su celda
    bra con_paso_npc
sin_paso_npc:
    ; ¿Está saltando? Entonces la celda es la de destino y el dibujo va detrás,
    ; con el arco encima. La clave de orden sale de la posición **sin** el arco:
    ; es `GetScreenY(false)`, así que quien está en el aire no se adelanta.
    lda ruta_ev + 13, x
    beq puesto
    sta salto_resta
    lda ruta_ev + 14, x
    sta salto_dx
    lda ruta_ev + 15, x
    sta salto_dy
    phx
    jsr salto_posicion_npc
    jsr alto_del_salto
    plx
    bra puesto
con_paso_npc:

    ; La dirección del paso, que va aparte de hacia dónde mira: con la mirada
    ; fija —los droides del mapa 2— sube mirando abajo. Por tabla, porque en
    ; diagonal hay que descontar en los dos ejes: los pixeles que faltan se le
    ; restan al sentido del paso, o sea que quien va hacia la derecha se dibuja
    ; todavía a la izquierda de su celda. X se pisa y no lo necesita nadie
    ; más: de acá en adelante el índice es `npc_fila`.
    lda slot_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:paso_dx, x
    beq sin_dx_npc
    bmi mas_px                  ; $FF, o sea hacia la izquierda
    jsr restar_a_px
    bra sin_dx_npc
mas_px:
    jsr sumar_a_px
sin_dx_npc:
    lda f:paso_dy, x
    beq puesto
    bmi mas_py                  ; venía de abajo: todavía le falta subir
    jsr restar_a_py
    bra puesto
mas_py:
    jsr sumar_a_py

puesto:
    ; A la fila: la posición, y la clave con la capa que ya traía.
    ldy npc_fila
    rep #$20
.a16
    lda npc_px
    sta npc_buf + 0, y
    lda npc_py
    sta npc_buf + 2, y
    sep #$20
.a8
    lda salto_alto
    sta npc_buf + 11, y         ; cuánto levantar el dibujo, sin tocar la clave
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$F000                  ; la capa se queda; la Y se reemplaza
    sta temp
    lda npc_py
    and #$0FFF
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8

    ; La pose: hacia dónde mira por tres, más la columna del ciclo. La columna 3
    ; dibuja la misma que la 1, que es como RM2k arma un ciclo de cuatro con
    ; tres columnas.
    lda slot_mira
    cmp #RUTA_EV_SIN_MIRAR
    bne tiene_dir
    lda npc_buf + 10, y         ; todavía no giró: mira adonde dice su página
tiene_dir:
    ; Y si es el que mira al héroe, adonde dice el giro: su ranura está
    ; libre, porque con una ruta andando no gira. Ver `giro_disparar`.
    pha
    lda f:GIRO_EV
    cmp npc_buf + 8, y
    bne sin_giro
    pla
    lda f:GIRO_DIR
    pha
sin_giro:
    pla
    sta temp
    asl a
    clc
    adc temp                    ; por tres
    sta temp
    lda slot_paso
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    clc
    adc temp                    ; la pose, de 0 a 11
    jsr subir_pose_npc
acomodar:
    jmp acomodar_npc            ; y la fila, a donde le toque ahora
.endproc

; Si la fila `cmp_a` va **antes** que la `cmp_b` en el orden de dibujado.
; Devuelve A distinto de cero si sí.
;
; El orden es el de RM2k: mayor Y —que va adentro de la clave, junto con la
; capa—, después mayor X, y después mayor id. Los tres desempates hacen falta
; porque un evento que camina cambia de fila todo el tiempo y empata con
; cualquiera; con NPCs quietos casi nunca se notaba.
.proc npc_va_antes
.a8
.i16
    rep #$20
.a16
    ldy cmp_a
    lda npc_buf + 4, y
    ldy cmp_b
    cmp npc_buf + 4, y
    beq por_x
    sep #$20
.a8
    bcc no
    bra si
por_x:
.a16                            ; se llega en dieciséis, desde el `beq` de arriba
    ldy cmp_a
    lda npc_buf + 0, y
    ldy cmp_b
    cmp npc_buf + 0, y
    beq por_evento
    sep #$20
.a8
    bcc no
    bra si
por_evento:
.a16                            ; ídem: el `sep` de abajo lo achica
    sep #$20
.a8
    ldy cmp_a
    lda npc_buf + 8, y
    ldy cmp_b
    cmp npc_buf + 8, y
    bcc no
    beq no                      ; iguales: no hay nada que reacomodar
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Intercambia las dos filas que apuntan `cmp_a` y `cmp_b`, de a palabras.
.proc npc_swap
.a8
.i16
    ldx #$0000
otra:
    rep #$20
.a16
    txa
    clc
    adc cmp_a
    tay
    lda npc_buf, y
    sta temp
    txa
    clc
    adc cmp_b
    tay
    lda npc_buf, y
    pha
    lda temp
    sta npc_buf, y
    txa
    clc
    adc cmp_a
    tay
    pla
    sta npc_buf, y
    txa
    clc
    adc #2
    tax
    cpx #NPC_STRIDE
    sep #$20
.a8
    bcc otra
    rts
.endproc

; Deja la fila `npc_fila` donde le toca ahora, con la tabla ya ordenada.
;
; Sólo se mueve la que cambió, y a lo sumo unos pocos lugares: la Y cambia de a
; dos pixeles por cuadro. Ordenar la tabla entera todos los cuadros costaría lo
; mismo aunque no se moviera nadie.
.proc acomodar_npc
.a8
.i16
subir:
    lda npc_fila
    ora npc_fila + 1
    beq bajar                   ; ya es la primera
    rep #$20
.a16
    lda npc_fila
    sta cmp_a
    sec
    sbc #NPC_STRIDE
    sta cmp_b
    sep #$20
.a8
    jsr npc_va_antes
    beq bajar
    jsr npc_swap
    rep #$20
.a16
    lda cmp_b
    sta npc_fila
    sep #$20
.a8
    bra subir

bajar:
    rep #$20
.a16
    lda npc_fila
    clc
    adc #NPC_STRIDE
    cmp npc_total
    sep #$20
.a8
    bcs listo                   ; ya es la última
    rep #$20
.a16
    lda npc_fila
    sta cmp_b
    clc
    adc #NPC_STRIDE
    sta cmp_a
    sep #$20
.a8
    jsr npc_va_antes
    beq listo
    jsr npc_swap
    rep #$20
.a16
    lda cmp_a
    sta npc_fila
    sep #$20
.a8
    bra bajar
listo:
    rts
.endproc

; Las cuatro sumas del paso en curso, con `temp` trayendo los pixeles que
; faltan. Están aparte porque el `rep`/`sep` de cada una adentro del `cmp`
; alargaba el procedimiento hasta que los saltos no llegaban.
.proc sumar_a_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    clc
    adc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc restar_a_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    sec
    sbc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc sumar_a_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    clc
    adc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

.proc restar_a_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    sec
    sbc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

