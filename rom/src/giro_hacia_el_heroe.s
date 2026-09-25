; --- el giro hacia el héroe ------------------------------------------------
;
; `Game_Event::ScheduleForegroundExecution`: el evento que el héroe dispara
; —con la tecla de acción o por contacto— se da vuelta hacia él, salvo que su
; animación fije la dirección. Mira para ahí mientras dura su página y al
; terminar vuelve a su pose, que es el `UpdateFacing` de
; `OnFinishForegroundEvent`. Las reglas —cuándo gira, cuándo se deshace— están
; en `giro_disparar` y `giro_revisar`, acá abajo.
;
; Hay un solo giro a la vez: sólo gira el evento que disparó el héroe, y el
; anterior terminó su página antes. Su estado vive en la RAM lejana:
;
;   GIRO_EV     el evento, o $FF. **No se guarda su fila**: las filas se
;               reordenan cuando alguien camina —`acomodar_npc`—, y la fila
;               guardada pasaba a ser de otro. La primera versión le devolvía
;               el tile del Bum de Lashe City al evento que había quedado en su
;               lugar; lo encontró `bum-vuelve`. Se la busca con
;               `npc_de_evento` cada vez.
;   GIRO_K      la entrada de `npc_poses` de su gráfico, y GIRO_PPOSE la pose
;               de su página: con las dos, un refresco sabe si la página
;               nueva trae el mismo gráfico
;   GIRO_DIR    hacia dónde mira
;   GIRO_*_ANT  el tile, los atributos y la pose de la fila antes de girar,
;               para devolvérselos
;   ELEG_K, ELEG_POSE   el +30 y el +31 de la página que ganó la última vez
;               que corrió `buscar_pagina_de_evento`
;
; Un quieto comparte su ranura de VRAM con los otros quietos de la misma pose,
; así que para girar se muda a la ranura de giro del mapa, `M_GIRO_TILE4`, y
; se le sube ahí la pose nueva. Uno que camina o que anima quieto tiene la
; suya y gira en el lugar.
FAR_GIRO   = $30C0
GIRO_EV    = $7E0000 + FAR_GIRO
GIRO_K     = GIRO_EV + 3
GIRO_PPOSE = GIRO_EV + 4
GIRO_TILE_ANT = GIRO_EV + 5
GIRO_ATTR_ANT = GIRO_EV + 6
GIRO_POSE_ANT = GIRO_EV + 7
GIRO_DIR   = GIRO_EV + 8
ELEG_K     = GIRO_EV + 9
ELEG_POSE  = GIRO_EV + 10

; Sin giro. En el reset y al cargar un mapa: las filas son otras.
.proc giro_limpiar
.a8
.i16
    lda #$FF
    sta f:GIRO_EV
    rts
.endproc

; La página de `ev_buscado` acaba de encolarse por el héroe: si gira, que
; mire hacia él. La celda del evento es (celda_x, celda_y) y la del héroe
; (tile_x, tile_y). Entra con ELEG_K y ELEG_POSE de su página.
.proc giro_disparar
.a8
.i16
    lda f:ELEG_K
    cmp #$FF
    bne gira
    rts                         ; la página no gira
gira:
    lda ev_buscado
    jsr ranura_del_evento
    cpx #$FFFF
    beq sin_ruta
    ; `IsFacingLocked`: la orden 26 de su ruta le fijó la mirada y sólo la 27
    ; se la suelta, así que no gira ni con el héroe hablándole. La ruta puede
    ; haber terminado hace rato —el bit queda en la ranura— y por eso se mira
    ; antes que `ruta_ocupada`: es el director muerto de `RunDirectorScene`,
    ; que hace `26` y nunca un `27` (mapas 19, 46 y 96).
    lda ruta_ev + 18, x
    and #$08
    bne fija
    jsr ruta_ocupada
    beq sin_ruta                ; la ranura quedó de una ruta que ya terminó
fija:
    rts                         ; una ruta andando: ella decide adónde mira
sin_ruta:
    lda ev_buscado
    jsr npc_de_evento
    cpy #$FFFF
    bne con_fila
    rts
con_fila:
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne puede
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    cmp #$FF
    bne puede
    rts                         ; un quieto sin ranura de giro
puede:
    phy
    jsr giro_deshacer           ; si quedaba otro, vuelve a lo suyo
    ply

    ; Hacia dónde: `GetDirectionToCharacter`, con sx y sy del evento menos el
    ; héroe. Si |sx| > |sy| gana el horizontal; si no, el vertical.
    rep #$20
.a16
    lda celda_x
    sec
    sbc tile_x
    pha                         ; sx
    bpl sx_pos
    eor #$FFFF
    inc a
sx_pos:
    sta temp                    ; |sx|
    lda celda_y
    sec
    sbc tile_y
    sta temp + 2                ; sy
    bpl sy_pos
    eor #$FFFF
    inc a
sy_pos:
    cmp temp
    bcs vertical                ; |sy| >= |sx|
    pla
    bmi a_la_derecha            ; el evento a la izquierda del héroe
    lda #DIR_LEFT
    bra dir_lista
a_la_derecha:
    lda #DIR_RIGHT
    bra dir_lista
vertical:
    pla
    lda temp + 2
    beq abajo
    bmi abajo                   ; el evento arriba del héroe
    lda #DIR_UP
    bra dir_lista
abajo:
    lda #DIR_DOWN
dir_lista:
    sep #$20
.a8
    sta f:GIRO_DIR

    lda ev_buscado
    sta f:GIRO_EV
    lda f:ELEG_K
    sta f:GIRO_K
    lda f:ELEG_POSE
    sta f:GIRO_PPOSE
    lda npc_buf + 6, y
    sta f:GIRO_TILE_ANT
    lda npc_buf + 7, y
    sta f:GIRO_ATTR_ANT
    lda npc_buf + 12, y
    sta f:GIRO_POSE_ANT
    jmp giro_aplicar
.endproc

; La pose que mira hacia GIRO_DIR, en la fila Y: la columna de la de antes
; y la fila de la dirección.
.proc giro_aplicar
.a8
.i16
    lda f:GIRO_POSE_ANT
columna:
    cmp #3
    bcc con_columna
    sbc #3                      ; el carry quedó en 1
    bra columna
con_columna:
    sta temp
    lda f:GIRO_DIR
    asl a
    clc
    adc f:GIRO_DIR
    clc
    adc temp
    sta temp                    ; la pose nueva
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    beq quieto
    lda npc_buf + 13, y
    bmi listo                   ; anima quieto: `animar_quietos` la sube
    sty npc_fila
    lda temp
    jmp subir_pose_npc
quieto:
    ; A la ranura de giro: su tile, con el bit 8 en los atributos.
    lda temp
    sta npc_buf + 12, y
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    asl a
    asl a                       ; el tile: el byte por cuatro, y el bit 8
    sta npc_buf + 6, y
    lda #0
    rol a
    sta temp + 1
    lda npc_buf + 7, y
    and #$FE
    ora temp + 1
    sta npc_buf + 7, y
    ; Y la pose, de las doce de su gráfico: (k * 12 + pose) * 3 en `npc_poses`.
    lda f:GIRO_K
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
    adc temp + 2                ; treinta y seis por gráfico
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
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; el tile
    asl a
    asl a
    asl a
    asl a                       ; dieciséis palabras por tile
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne listo
    jsr giro_deshacer           ; la cola estaba llena: no gira
listo:
    rts
.endproc

; Si la ranura de ruta X tiene algo andando: la ruta propia de su página,
; órdenes por dar, un paso, una espera o un salto. Z=1 si está libre. Es
; `Ruta.pendiente or Ruta.de_pagina` en eventos.py. Una ranura no se suelta
; hasta que se carga otro mapa, así que "tiene ranura" no alcanzaba: el
; `GangMember1` de Lashe City, al que una escena ya había movido, no giraba
; nunca más. taro lo encontró jugando.
.proc ruta_ocupada
.a8
.i16
    lda ruta_ev + 18, x
    and #$01
    bne si
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc si
    lda ruta_ev + 7, x
    ora ruta_ev + 9, x
    ora ruta_ev + 13, x
    bne si
    lda #0
    rts
si:
    lda #1
    rts
.endproc

; Se terminó el giro: la fila vuelve a lo suyo. No toca nada si no hay.
.proc giro_deshacer
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    jsr npc_de_evento
    lda #$FF
    sta f:GIRO_EV
    cpy #$FFFF
    beq nada
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne propia
    lda f:GIRO_TILE_ANT
    sta npc_buf + 6, y
    lda f:GIRO_ATTR_ANT
    sta npc_buf + 7, y
    lda f:GIRO_POSE_ANT
    sta npc_buf + 12, y
    rts
propia:
    lda npc_buf + 13, y
    bmi nada                    ; anima quieto: vuelve solo, el cuadro que viene
    sty npc_fila
    lda f:GIRO_POSE_ANT
    jmp subir_pose_npc
nada:
    rts
.endproc

; A: un evento que se queda con una ranura de ruta. Si era el que giraba, el
; giro se termina: desde ahora adónde mira lo decide la ruta.
.proc giro_por_ruta
.a8
.i16
    cmp f:GIRO_EV
    bne nada
    jmp giro_deshacer
nada:
    rts
.endproc

; Al empezar un refresco que aplica páginas: si el evento que gira cambió a
; una página que no gira o con otro gráfico, el giro se termina. Es el
; `SetFacing(page->character_direction)` de `Game_Event::RefreshPage`, que
; sólo pasa si la página nueva es otra.
.proc giro_revisar
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jsr buscar_pagina_de_evento
    lda elegida_hay
    beq deshacer                ; se quedó sin página
    lda f:ELEG_K
    cmp #$FF
    beq deshacer
    cmp f:GIRO_K
    bne deshacer
    lda f:ELEG_POSE
    cmp f:GIRO_PPOSE
    bne deshacer
nada:
    rts
deshacer:
    jmp giro_deshacer
.endproc

; La fila Y acaba de recibir el gráfico de su página: si es la del evento que
; gira y el giro sigue, se lo vuelve a poner encima.
.proc giro_reponer
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    cmp npc_buf + 8, y
    bne nada
    lda npc_buf + 12, y
    sta f:GIRO_POSE_ANT
    lda npc_buf + 6, y
    sta f:GIRO_TILE_ANT
    lda npc_buf + 7, y
    sta f:GIRO_ATTR_ANT
    jmp giro_aplicar
nada:
    rts
.endproc

; Hacia dónde mira la fila Y para `animar_quietos`: la de su página, o la del
; giro si es la que gira. Devuelve A.
.proc mirada_de_fila
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq propia
    cmp npc_buf + 8, y
    bne propia
    lda f:GIRO_DIR
    rts
propia:
    lda npc_buf + 10, y
    rts
.endproc

