.segment "CODE"

; --- turning toward the hero -----------------------------------------------
;
; `Game_Event::ScheduleForegroundExecution`: the event the hero triggers
; —with the action button or by touch— turns around toward him, unless its
; animation locks the direction. It faces that way while its page lasts and,
; when it ends, goes back to its pose, which is the `UpdateFacing` of
; `OnFinishForegroundEvent`. The rules —when it turns, when it is undone— are
; in `giro_disparar` and `giro_revisar`, below.
;
; There is only one turn at a time: only the event the hero triggered turns,
; and the previous one finished its page before. Its state lives in far RAM:
;
;   GIRO_EV     the event, or $FF. **Its row is not saved**: rows get
;               reordered when someone walks —`acomodar_npc`—, and the saved
;               row ended up belonging to someone else. The first version gave
;               the Bum of Lashe City's tile back to the event that had ended
;               up in its place; `bum-vuelve` found it. The row is looked up
;               with `npc_de_evento` every time.
;   GIRO_K      the `npc_poses` entry for its graphic, and GIRO_PPOSE the pose
;               of its page: with the two, a refresh knows whether the new
;               page brings the same graphic
;   GIRO_DIR    which way it faces
;   GIRO_*_ANT  the row's tile, attributes and pose before turning, to give
;               them back
;   ELEG_K, ELEG_POSE   the +30 and the +31 of the page that won the last time
;               `buscar_pagina_de_evento` ran
;
; A still one shares its VRAM slot with the other still ones of the same pose,
; so to turn it moves to the map's turn slot, `M_GIRO_TILE4`, and the new pose
; is uploaded there. One that walks or animates in place has its own and turns
; where it is.
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

; No turn. On reset and when loading a map: the rows are different ones.
.proc giro_limpiar
.a8
.i16
    lda #$FF
    sta f:GIRO_EV
    rts
.endproc

; The page of `ev_buscado` has just been queued by the hero: if it turns, make
; it face him. The event's cell is (celda_x, celda_y) and the hero's
; (tile_x, tile_y). Enters with ELEG_K and ELEG_POSE from its page.
.proc giro_disparar
.a8
.i16
    lda f:ELEG_K
    cmp #$FF
    bne gira
    rts                         ; the page does not turn
gira:
    lda ev_buscado
    jsr ranura_del_evento
    cpx #$FFFF
    beq sin_ruta
    ; `IsFacingLocked`: command 26 of its move route locked its facing and only
    ; 27 releases it, so it does not turn even with the hero talking to it. The
    ; route may have ended long ago —the bit stays in the slot— and that is why
    ; it is checked before `ruta_ocupada`: it is the dead director of
    ; `RunDirectorScene`, which does `26` and never a `27` (maps 19, 46 and
    ; 96).
    lda ruta_ev + 18, x
    and #$08
    bne fija
    jsr ruta_ocupada
    beq sin_ruta                ; the slot was left over from a finished route
fija:
    rts                         ; a route running: it decides where it faces
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
    rts                         ; a still one with no turn slot
puede:
    phy
    jsr giro_deshacer           ; if another one was left, it goes back to its own
    ply

    ; Which way: `GetDirectionToCharacter`, with sx and sy being the event
    ; minus the hero. If |sx| > |sy| the horizontal wins; otherwise, the
    ; vertical.
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
    bmi a_la_derecha            ; the event to the left of the hero
    lda #DIR_LEFT
    bra dir_lista
a_la_derecha:
    lda #DIR_RIGHT
    bra dir_lista
vertical:
    pla
    lda temp + 2
    beq abajo
    bmi abajo                   ; the event above the hero
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

; The pose that faces GIRO_DIR, in row Y: the column of the previous one and
; the row of the direction.
.proc giro_aplicar
.a8
.i16
    lda f:GIRO_POSE_ANT
columna:
    cmp #3
    bcc con_columna
    sbc #3                      ; carry was left at 1
    bra columna
con_columna:
    sta temp
    lda f:GIRO_DIR
    asl a
    clc
    adc f:GIRO_DIR
    clc
    adc temp
    sta temp                    ; the new pose
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    beq quieto
    lda npc_buf + 13, y
    bmi listo                   ; animates in place: `animar_quietos` uploads it
    sty npc_fila
    lda temp
    jmp subir_pose_npc
quieto:
    ; To the turn slot: its tile, with bit 8 in the attributes.
    lda temp
    sta npc_buf + 12, y
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    asl a
    asl a                       ; the tile: the byte times four, and bit 8
    sta npc_buf + 6, y
    lda #0
    rol a
    sta temp + 1
    lda npc_buf + 7, y
    and #$FE
    ora temp + 1
    sta npc_buf + 7, y
    ; And the pose, out of its graphic's twelve: (k * 12 + pose) * 3 in
    ; `npc_poses`.
    lda f:GIRO_K
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; times four
    sta temp + 2
    asl a
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2                ; thirty-six per graphic
    sta temp + 2
    lda temp
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; the pose times three
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
    asl a                       ; the tile
    asl a
    asl a
    asl a
    asl a                       ; sixteen words per tile
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne listo
    jsr giro_deshacer           ; the queue was full: it does not turn
listo:
    rts
.endproc

; Whether move route slot X has something running: its page's own route,
; commands still to give, a step, a wait or a jump. Z=1 if it is free. A
; slot is not released until another map is loaded, so "has a slot" was not
; enough: the
; `GangMember1` of Lashe City, which a scene had already moved, never turned
; again. taro found it playing.
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

; The turn is over: the row goes back to its own. Touches nothing if there is
; none.
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
    bmi nada                    ; animates in place: goes back by itself, next frame
    sty npc_fila
    lda f:GIRO_POSE_ANT
    jmp subir_pose_npc
nada:
    rts
.endproc

; A: an event that takes a move route slot. If it was the one turning, the
; turn is over: from now on the route decides where it faces.
.proc giro_por_ruta
.a8
.i16
    cmp f:GIRO_EV
    bne nada
    jmp giro_deshacer
nada:
    rts
.endproc

; At the start of a refresh that applies pages: if the turning event changed
; to a page that does not turn or has another graphic, the turn is over. It is
; the `SetFacing(page->character_direction)` of `Game_Event::RefreshPage`,
; which only happens if the new page is a different one.
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
    beq deshacer                ; it was left without a page
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

; Row Y has just received its page's graphic: if it is the turning event's and
; the turn is still on, it is put back on top.
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

; Which way row Y faces, for `animar_quietos`: its page's, or the turn's if it
; is the one turning. Returns A.
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

