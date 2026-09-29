.segment "CODE"

; --- turning toward the hero -----------------------------------------------
;
; `Game_Event::ScheduleForegroundExecution`: the event the hero triggers
; —with the action button or by touch— turns around toward him, unless its
; animation locks the direction. It faces that way while its page lasts and,
; when it ends, goes back to its pose, which is the `UpdateFacing` of
; `OnFinishForegroundEvent`. The rules —when it turns, when it is undone— are
; in `turn_fire` and `turn_check`, below.
;
; There is only one turn at a time: only the event the hero triggered turns,
; and the previous one finished its page before. Its state lives in far RAM:
;
;   TURN_EV     the event, or $FF. **Its row is not saved**: rows get
;               reordered when someone walks —`acomodar_npc`—, and the saved
;               row ended up belonging to someone else. The first version gave
;               the Bum of Lashe City's tile back to the event that had ended
;               up in its place; `bum-vuelve` found it. The row is looked up
;               with `event_npc` every time.
;   TURN_K      the `npc_poses` entry for its graphic, and TURN_PPOSE the pose
;               of its page: with the two, a refresh knows whether the new
;               page brings the same graphic
;   TURN_DIR    which way it faces
;   GIRO_*_ANT  the row's tile, attributes and pose before turning, to give
;               them back
;   PICK_K, PICK_POSE   the +30 and the +31 of the page that won the last time
;               `seek_event_page` ran
;
; A still one shares its VRAM slot with the other still ones of the same pose,
; so to turn it moves to the map's turn slot, `M_GIRO_TILE4`, and the new pose
; is uploaded there. One that walks or animates in place has its own and turns
; where it is.
FAR_TURN   = $30C0
TURN_EV    = $7E0000 + FAR_TURN
TURN_K     = TURN_EV + 3
TURN_PPOSE = TURN_EV + 4
TURN_TILE_PREV = TURN_EV + 5
TURN_ATTR_PREV = TURN_EV + 6
TURN_POSE_PREV = TURN_EV + 7
TURN_DIR   = TURN_EV + 8
PICK_K     = TURN_EV + 9
PICK_POSE  = TURN_EV + 10

; No turn. On reset and when loading a map: the rows are different ones.
.proc turn_clear
.a8
.i16
    lda #$FF
    sta f:TURN_EV
    rts
.endproc

; The page of `ev_buscado` has just been queued by the hero: if it turns, make
; it face him. The event's cell is (celda_x, celda_y) and the hero's
; (tile_x, tile_y). Enters with PICK_K and PICK_POSE from its page.
.proc turn_fire
.a8
.i16
    lda f:PICK_K
    cmp #$FF
    bne gira
    rts                         ; the page does not turn
gira:
    lda ev_buscado
    jsr event_slot
    cpx #$FFFF
    beq sin_ruta
    ; `IsFacingLocked`: command 26 of its move route locked its facing and only
    ; 27 releases it, so it does not turn even with the hero talking to it. The
    ; route may have ended long ago —the bit stays in the slot— and that is why
    ; it is checked before `route_busy`: it is the dead director of
    ; `RunDirectorScene`, which does `26` and never a `27` (maps 19, 46 and
    ; 96).
    lda ruta_ev + 18, x
    and #$08
    bne fija
    jsr route_busy
    beq sin_ruta                ; the slot was left over from a finished route
fija:
    rts                         ; a route running: it decides where it faces
sin_ruta:
    lda ev_buscado
    jsr event_npc
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
    jsr turn_undo           ; if another one was left, it goes back to its own
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
    sta f:TURN_DIR

    lda ev_buscado
    sta f:TURN_EV
    lda f:PICK_K
    sta f:TURN_K
    lda f:PICK_POSE
    sta f:TURN_PPOSE
    lda npc_buf + 6, y
    sta f:TURN_TILE_PREV
    lda npc_buf + 7, y
    sta f:TURN_ATTR_PREV
    lda npc_buf + 12, y
    sta f:TURN_POSE_PREV
    jmp turn_apply
.endproc

; The pose that faces TURN_DIR, in row Y: the column of the previous one and
; the row of the direction.
.proc turn_apply
.a8
.i16
    lda f:TURN_POSE_PREV
columna:
    cmp #3
    bcc con_columna
    sbc #3                      ; carry was left at 1
    bra columna
con_columna:
    sta temp
    lda f:TURN_DIR
    asl a
    clc
    adc f:TURN_DIR
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
    lda f:TURN_K
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
    jsr turn_undo           ; the queue was full: it does not turn
listo:
    rts
.endproc

; Whether move route slot X has something running: its page's own route,
; commands still to give, a step, a wait or a jump. Z=1 if it is free. A
; slot is not released until another map is loaded, so "has a slot" was not
; enough: the
; `GangMember1` of Lashe City, which a scene had already moved, never turned
; again. taro found it playing.
.proc route_busy
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
.proc turn_undo
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nada
    jsr event_npc
    lda #$FF
    sta f:TURN_EV
    cpy #$FFFF
    beq nada
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne propia
    lda f:TURN_TILE_PREV
    sta npc_buf + 6, y
    lda f:TURN_ATTR_PREV
    sta npc_buf + 7, y
    lda f:TURN_POSE_PREV
    sta npc_buf + 12, y
    rts
propia:
    lda npc_buf + 13, y
    bmi nada                    ; animates in place: goes back by itself, next frame
    sty npc_fila
    lda f:TURN_POSE_PREV
    jmp subir_pose_npc
nada:
    rts
.endproc

; A: an event that takes a move route slot. If it was the one turning, the
; turn is over: from now on the route decides where it faces.
.proc turn_per_route
.a8
.i16
    cmp f:TURN_EV
    bne nada
    jmp turn_undo
nada:
    rts
.endproc

; At the start of a refresh that applies pages: if the turning event changed
; to a page that does not turn or has another graphic, the turn is over. It is
; the `SetFacing(page->character_direction)` of `Game_Event::RefreshPage`,
; which only happens if the new page is a different one.
.proc turn_check
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nada
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jsr seek_event_page
    lda elegida_hay
    beq deshacer                ; it was left without a page
    lda f:PICK_K
    cmp #$FF
    beq deshacer
    cmp f:TURN_K
    bne deshacer
    lda f:PICK_POSE
    cmp f:TURN_PPOSE
    bne deshacer
nada:
    rts
deshacer:
    jmp turn_undo
.endproc

; Row Y has just received its page's graphic: if it is the turning event's and
; the turn is still on, it is put back on top.
.proc turn_restore
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq nada
    cmp npc_buf + 8, y
    bne nada
    lda npc_buf + 12, y
    sta f:TURN_POSE_PREV
    lda npc_buf + 6, y
    sta f:TURN_TILE_PREV
    lda npc_buf + 7, y
    sta f:TURN_ATTR_PREV
    jmp turn_apply
nada:
    rts
.endproc

; Which way row Y faces, for `animar_quietos`: its page's, or the turn's if it
; is the one turning. Returns A.
.proc facing_of_row
.a8
.i16
    lda f:TURN_EV
    cmp #$FF
    beq propia
    cmp npc_buf + 8, y
    bne propia
    lda f:TURN_DIR
    rts
propia:
    lda npc_buf + 10, y
    rts
.endproc

