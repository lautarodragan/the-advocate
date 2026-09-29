.segment "CODE"

; --- the action button -------------------------------------------------------
;
; Talking to something. It is what turns this into a game and not a cutscene:
; of the 1599 pages of this game that fire this way, 1006 already compile,
; against 110 autostart ones.
;
; The rule comes from `Game_Player::CheckActionEvent`: look at the hero's cell
; and then at the one in front. What comes before that there —the events that
; fire on touch— is not here yet, and neither is the loop of up to three
; counters.

; Is there an event at (celda_x, celda_y)? Returns its index in A, or $FF.
.proc evento_en_celda
.a8
.i16
    ldy #$0000
    ldx #$0000
buscar:
    cpx ev_total
    beq no_hay
    rep #$20
.a16
    lda ev_pos_buf, y
    cmp celda_x
    bne siguiente
    lda ev_pos_buf + 2, y
    cmp celda_y
    bne siguiente
    sep #$20
.a8
    txa                         ; the index fits in a byte: EV_MAX is 128
    rts
siguiente:
.a16                            ; reached in sixteen bits, from the `bne` above
    tya
    clc
    adc #EV_STRIDE
    tay
    sep #$20
.a8
    inx
    bra buscar
no_hay:
    lda #$FF
    rts
.endproc

; Queues the active page of event `ev_buscado` if the action button fires it.
; Returns A nonzero if it queued something.
;
; It is the same selection rule as `encolar_eventos` —the highest-numbered one
; whose conditions hold wins— but for a single event, and without touching the
; cursor of the autostart queue.
; The active page of event `ev_buscado`, into `elegida`. Without looking at
; the trigger: the caller decides what to do with it. It is the usual rule
; —the highest-numbered one whose conditions hold wins— and it is resolved
; **at the moment of using it**, not when the event was flagged, which is what
; `Game_Map::Update` does when it pushes the event that was waiting.
.proc buscar_pagina_de_evento
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    beq sin_paginas
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz elegida_hay

recorrer:
    jsr leer_pagina
    rep #$20
.a16
    lda pg_evento
    cmp ev_buscado
    sep #$20
.a8
    bne siguiente               ; not the event we are looking at
    jsr condiciones_ok
    beq siguiente
    lda pg_trigger
    sta elegida_trigger
    lda pg_capa
    sta elegida_capa
    rep #$20
.a16
    lda pg_cod
    sta elegida
    sep #$20
.a8
    lda pg_cod + 2
    sta elegida + 2
    lda #1
    sta elegida_hay
    ; And its turn, +30 and +31: see `giro_disparar` and `giro_revisar`.
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #30
    tay
    sep #$20
.a8
    lda [pag_ptr], y
    sta f:ELEG_K
    iny
    lda [pag_ptr], y
    sta f:ELEG_POSE

siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    bne recorrer

    rts
sin_paginas:
.a16                            ; reached in sixteen bits; the `sep` narrows it
    sep #$20
.a8
    stz elegida_hay
    rts
.endproc

; The firing by action button or by touch: looks up the event's active page
; and, if it has the requested trigger and it compiled, flags the event.
.proc encolar_por_accion
.a8
.i16
    jsr buscar_pagina_de_evento
    lda elegida_hay
    beq no
    lda elegida_trigger
    cmp trigger_buscado
    bne no
    ; The layer rule, opposite depending on which cell is looked at: the one
    ; in front only fires events on the hero's layer —`CheckEventTriggerThere`
    ; asks for `Layers_same`— and the hero's own cell only those on another
    ; layer —`CheckEventTriggerHere` asks for `!= Layers_same`—. It is not
    ; decorative symmetry: an event on the hero's layer blocks the way, so the
    ; hero could never stand on top of it.
    ;
    ; Only for the action button; touch has its own rule and is resolved at
    ; compile time.
    lda trigger_buscado
    cmp #TRIGGER_ACCION
    bne sin_capa
    lda elegida_capa
    cmp #HERO_LAYER
    beq era_del_heroe
    lda accion_propia
    beq no                      ; another layer, but we are looking ahead
    bra sin_capa
era_del_heroe:
    lda accion_propia
    bne no                      ; the hero's layer, but we are looking at our own cell
sin_capa:
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq no                      ; the active page could not be compiled
    ldx ev_buscado
    jsr marcar_esperando
    jsr giro_disparar           ; and it turns toward the hero, if it turns
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; The cell given in (celda_x, celda_y): if there is an event and its active
; page is fired by the button, it gets queued. Returns A nonzero if it queued.
.proc accion_en_celda
.a8
.i16
    jsr evento_en_celda
    cmp #$FF
    beq no
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jmp encolar_por_accion
no:
    lda #0
    rts
.endproc

; The touch event of the cell the hero has just stopped on.
;
; It is `CheckEventTriggerHere` from `Game_Player::UpdateMovement`. Doors are
; a particular case of this —a teleport in a touch page— and they are handled
; earlier, separately: if there was a door, the map already changed and there
; is nothing left to look at here.
; With a page running it is **also** checked, and the page it fires goes into
; the queue behind the one running: in RM2k `UpdateMovement` does not ask
; about the interpreter, `ScheduleForegroundExecution` leaves the event
; waiting and `Game_Map` starts it when the interpreter frees up. There used
; to be a guard here that dropped the touch in that case, written for the pad
; —and for the pad it is superfluous, because `move_hero` does not start a
; step with a page in the foreground—; with a forced route it did happen: a
; page that sends the hero walking and then waits ended up with the touch
; lost. The queue is the same as the autostart one, one behind the other,
; which is what RM2k does.
;
; What is not modeled, on either side: an event that fires twice before
; running comes in here twice and only once in RM2k, which flags it with a
; bit.
.proc probar_contacto
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda #TRIGGER_TOCA_HEROE
    sta trigger_buscado
    jsr accion_en_celda
    ldx #TRIGGER_ACCION
    stx trigger_buscado         ; left as the action button expects it
    rts
.endproc

; The action button, from the main loop. Returns A nonzero if it queued
; something.
.proc probar_accion
.a8
.i16
    ; With a live forced route of the hero there is no talking: it is the
    ; `IsMoveRouteOverwritten()` in `game_player.cpp:297`, which returns
    ; before looking at the button. The `IsStopping()` the caller checks
    ; —`step_left`— is not enough, because between two steps of a route, in a
    ; `wait` and in the air, `step_left` is zero. These are the three hero
    ; things from `hay_rutas` without the step one, which was already checked
    ; there. It goes here and not next to that one because there the `beq
    ; nada` above no longer reached.
    ;
    ; It was missing, and it showed when the page ends before its route: the
    ; one in `EV0043` of map 8 is a lone `MoveEvent`, so the hero went down the
    ; pipe with no page anymore, and an A between two steps, at (52,20) facing
    ; down, talked to the `EV0052` opposite —hero's layer, placed to be faced
    ; from the left— and sent him back up. With an emulator's autofire, which
    ; presses every two frames, it always happened. Caught by
    ; `test_accion_con_ruta.py`.
    lda ruta_salto
    bne con_ruta                ; in the air
    lda ruta_espera
    bne con_ruta                ; in a route `wait`
    lda ruta_i
    cmp ruta_n
    bcc con_ruta                ; it has move commands left
    ; The two cells, in the order of `Game_Player::CheckActionEvent`: first the
    ; hero's own —`CheckEventTriggerHere`, which asks for a layer different
    ; from the hero's— and then the one in front —`CheckEventTriggerThere`,
    ; which asks for the hero's—. The own cell was left undone until
    ; 2026-09-07 and taro found it playing: the door out of Talan's pad is
    ; `TalDoorTop`, action-triggered and on layer 2, and it opens by standing
    ; on it.
    lda #TRIGGER_ACCION
    sta trigger_buscado
    lda #1
    sta accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    jsr accion_en_celda
    beq mirar_adelante
    rts                         ; queued the one under the hero
mirar_adelante:
    stz accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda hero_dir
    cmp #DIR_UP
    bne no_arriba
    rep #$20
.a16
    dec celda_y
    sep #$20
.a8
    bra mirar
no_arriba:
    cmp #DIR_DOWN
    bne no_abajo
    rep #$20
.a16
    inc celda_y
    sep #$20
.a8
    bra mirar
no_abajo:
    cmp #DIR_LEFT
    bne no_izquierda
    rep #$20
.a16
    dec celda_x
    sep #$20
.a8
    bra mirar
no_izquierda:
    rep #$20
.a16
    inc celda_x
    sep #$20
.a8
mirar:
    jmp accion_en_celda
con_ruta:
    lda #0
    rts
.endproc

