.segment "CODE"

; --- the events' forced move routes -----------------------------------------
;
; An event with a forced move route walks like the hero: turning does not use up
; a frame, waiting does, and moving starts a one-cell step that lasts
; CUADROS_POR_CELDA. The difference with the hero is that its position lives in
; cells and not in pixels, and that —for now— it is not drawn: the move routes
; that compile are on events without a graphic. The only visible thing about
; them is how long they take, which is what `ProceedWithMovement` waits for.

; Gives a move route to event `ruta_blanco - 1`: looks for its slot, and if it
; does not have one it takes a free one. Overwriting the one it already had is
; correct —RM2k overwrites the previous forced move route, it does not chain
; it— and if there is no free one the move route is dropped, which is preferable
; to writing next to the table.
;
; What is kept when overwriting it is what `ForceMoveRoute` keeps: the step or
; jump in progress finish, the facing stays, and going through walls and the
; stopped animation remain as they were. The wait —the first command runs right
; away— and the commands are cut. Before, the whole slot was reset, and the
; event went back to facing wherever its page said until the new move route
; turned it: it was the sentinel that left `face_hero` out.
;
; Enters with Y pointing to the first command inside the bytecode.
.proc route_for_event
.a8
.i16
    phy
    lda ruta_blanco
    dec a
    jsr turn_per_route           ; with a move route, the move route decides where it faces
    ply
    lda ruta_blanco
    dec a
    sta temp                    ; the event's index

    ; First the slot that is already its own, and if not a free one. The two
    ; searches were copied here and are exactly `event_slot` and
    ; `free_slot`: calling them saves bank 0 and, the first one, brings along
    ; the `ruta_ev_tope` cap as a bonus.
    lda temp
    jsr event_slot
    cpx #$FFFF
    bne reusada
    jsr free_slot
    cpx #$FFFF
    bne puesta
    rts                         ; no room: the move route is lost

puesta:
    lda temp
    sta ruta_ev + 0, x
    jsl f:ranura_anotar + RAPIDO
    stz ruta_ev + 6, x
    stz ruta_ev + 7, x          ; no step in progress
    stz ruta_ev + 22, x
    stz ruta_ev + 23, x
    lda #RUTA_EV_SIN_MIRAR
    sta ruta_ev + 8, x          ; faces wherever its page says until it turns
    stz ruta_ev + 12, x         ; no flags
    stz ruta_ev + 13, x         ; nor jump
    lda #1
    sta ruta_ev + 10, x         ; the middle frame, like `animate_hero`
    stz ruta_ev + 11, x
    stz ruta_ev + 18, x
    stz ruta_ev + 27, x         ; no page to go back to
    rep #$20
.a16
    lda #$FFFF
    sta ruta_ev + 20, x
    sep #$20
.a8
    ; At the speed of the page it is drawn with, which the NPC row carries at +13:
    ; it is the one RM2k leaves to a forced move route. An event without a row
    ; —without a graphic— goes at 3, a default page's.
    phy                         ; Y is the bytecode cursor, and it is needed
    lda temp                    ; afterwards: `event_npc` overwrites it
    jsr event_npc           ; Y = its row, or $FFFF; A is lost
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 13, y
    bra con_velocidad
sin_fila:
    lda #3
con_velocidad:
    ply
    sta ruta_ev + 17, x
    lda temp
    jsr active_layer             ; its layer, once and not on every step
    sta ruta_ev + 31, x
reusada:
    lda ruta_ev + 18, x
    and #$FE                    ; the forced one overrides the page's, if there was one
    ora #$04                    ; and what is blocked is skipped
    sta ruta_ev + 18, x
    ; The pointer to the first command: the code's plus however far Y had gone.
    ; The sum does not carry anything into the bank byte because the map's code
    ; block fits whole in one —the converter's bank layout guarantees it,
    ; `tools/ensamblado/bancos.py`—, which is the same argument as for the message block.
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta ruta_ev + 1, x
    sep #$20
.a8
    lda cod_ptr + 2
    sta ruta_ev + 3, x
    lda ruta_cuantas
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x          ; just starting
    stz ruta_ev + 9, x          ; and no wait in progress: the first command runs right away
    lda ruta_frec_op
    sta ruta_ev + 16, x
    rts
.endproc

; How many frames a character stands still after a step and after a turn with
; the frequency A carries. It is RM2k's stop counter —`SetMaxStopCountForStep`
; and `ForTurn`— and with 8 both give zero, which is why "turning is free and
; the steps go back to back" was exact without knowing it. The converter emits
; the tables from `eventos.espera_tras_paso` and `espera_tras_giro`. They use Y
; and not X, because X is the slot of whoever asks.
.proc after_step
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_paso, y
    rts
.endproc

.proc after_turn
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_giro, y
    rts
.endproc

; Which way whoever is at (celda_x, celda_y) faces to face the hero. It is
; `GetDirectionToCharacter`: the axis with more distance wins and on a tie the
; vertical; on the same cell, or with the hero further down, it faces down.
; Returns the direction in A.
.proc toward_hero
.a8
.i16
    rep #$20
.a16
    lda celda_x
    sec
    sbc tile_x
    sta temp                    ; sx, signed: positive is "the hero is to the left"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_a                   ; |sx|
    lda celda_y
    sec
    sbc tile_y
    sta temp + 2                ; sy: positive is "the hero is further up"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_b                   ; |sy|
    lda cmp_a
    cmp cmp_b
    beq vertical
    bcc vertical                ; |sx| <= |sy|: the vertical axis wins
    sep #$20
.a8
    lda temp + 1                ; the sign of sx
    bmi derecha
    lda #DIR_LEFT
    rts
derecha:
    lda #DIR_RIGHT
    rts
vertical:
.a16
    sep #$20
.a8
    lda temp + 3                ; the sign of sy
    bmi abajo
    lda temp + 2
    ora temp + 3
    beq abajo                   ; the same cell: down
    lda #DIR_UP
    rts
abajo:
    lda #DIR_DOWN
    rts
.endproc

; One frame of all the event move routes that are running.
.proc move_events
.a8
.i16
    stz rutas_movieron
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    ; The one that already took its step tied to its parallel interpreter does not
    ; take it again: the mark is consumed here, so it lasts one frame. See
    ; `one_parallel`.
    lda ruta_ev + 18, x
    and #$40
    beq no_movido
    lda ruta_ev + 18, x
    and #$BF
    sta ruta_ev + 18, x
    bra siguiente
no_movido:
    phx
    jsr ev_route_frame
    plx
    phx
    jsr animate_ev_route
    plx
    phx
    jsr refrescar_npc
    plx
    lda #1
    sta rutas_movieron
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc otra
    ; From here on the one that moves is the hero again.
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    rts
.endproc

; One frame of the move route of the slot X points to. It is the same program as
; `step_route` for the hero, and that is why both do the same with the same
; commands: if it were counted differently here, an event's move route would end
; on a different frame than the hero's and `ProceedWithMovement` would let the
; page go when it should not.
; The jumps in here go with `jmp` and not `bra`, for the same reason as in
; `step_route`: the body grew and the 127 bytes of reach fell short.
.proc ev_route_frame
.a8
.i16
    stz ruta_ev + 6, x
    lda ruta_ev + 18, x
    and #$DF                    ; `repeat`'s reload, one per frame
    sta ruta_ev + 18, x
    lda ruta_ev + 7, x
    beq sin_paso
    ; The step advances by what the speed says, out of 256 per cell; +7 only says
    ; there is one in progress.
    jsr step_slot
    rep #$20
.a16
    lda ruta_ev + 22, x
    sec
    sbc temp
    bcs no_negativo
    lda #0
no_negativo:
    sta ruta_ev + 22, x
    sep #$20
.a8
    bne moviendo
    stz ruta_ev + 7, x          ; the step ended on this frame
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc con_ordenes
    lda ruta_ev + 18, x         ; no commands: only the repeating page one
    and #$03                    ; keeps waiting
    cmp #$03
    bne moviendo
con_ordenes:
    lda ruta_ev + 16, x
    jsr after_step
    sta ruta_ev + 9, x
moviendo:
    lda #1
    sta ruta_ev + 6, x
    rts
sin_paso:
    lda ruta_ev + 13, x
    beq sin_salto
    jsr slot_jump
    sta temp
    lda ruta_ev + 13, x
    sec
    sbc temp
    bcs guardar_salto
    lda #0
guardar_salto:
    sta ruta_ev + 13, x
    rts
sin_salto:
    ; And a `wait` in progress takes the whole frame, same as the hero's.
    lda ruta_ev + 9, x
    beq sin_espera
    dec a
    sta ruta_ev + 9, x
    rts
sin_espera:
    ; The page's own move route does not read new commands while the interpreter
    ; has a page running: it is `UpdateNextMovementAction`'s `IsRunning()`. The
    ; step in progress already finished above and the waits keep counting.
    lda ruta_ev + 18, x
    and #$01
    beq no_congelada
    lda ev_activo
    bne congelada
    lda esperando_n
    bne congelada
no_congelada:
    ; The move route's pointer to the direct page, which is where it can be read
    ; from with `[ptr], y`.
    rep #$20
.a16
    lda ruta_ev + 1, x
    sta ruta_ptr
    sep #$20
.a8
    lda ruta_ev + 3, x
    sta ruta_ptr + 2

otra_orden:
    lda ruta_ev + 5, x          ; which one it is on
    cmp ruta_ev + 4, x          ; how many it has
    bcc hay_orden
    ; The commands ran out. The repeating page one goes back to the start on the
    ; same frame, and only once per frame —`UpdateMoveRoute`'s `current_index ==
    ; start_index`—; and a forced one that ends on an event with its own move route
    ; gives it back its own, from the start.
    lda ruta_ev + 18, x
    and #$23
    cmp #$03
    bne no_repite
    stz ruta_ev + 5, x
    lda ruta_ev + 18, x
    ora #$20
    sta ruta_ev + 18, x
    jmp otra_orden
no_repite:
    lda ruta_ev + 18, x
    and #$01
    bne congelada               ; the page one, finished: done
    lda ruta_ev + 27, x
    beq congelada               ; no page to go back to
    jsr resume_page
congelada:
    jmp listo
hay_orden:
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x

    cmp #23                     ; wait: this one and the RUTA_ESPERA - 1 after it,
    bne no_es_wait              ; plus the turn's if the frequency is low
    lda ruta_ev + 16, x
    jsr after_turn
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_ev + 9, x
    jmp listo
no_es_wait:
    cmp #12
    bcs no_mueve
    cmp #9
    bne :+
    ; `move_towards_hero`. It is not a separate command but the two already there
    ; put together: `UpdateMoveRoute` does `TurnTowardCharacter(hero)` and then
    ; `Move(GetDirection())`, that is, 21 and a `move_*` on the same frame. That
    ; is why the direction comes from here and it falls into `mover` without
    ; touching anything else: the turn, the step and what it costs are the usual.
    ; `toward_hero` does not overwrite X, which is the slot.
    jsr event_cell
    jsr toward_hero
:   jmp mover                   ; 0..3 are the move_*, and 9 already brings its own
no_mueve:
    cmp #16
    bcs :+
    jmp face                    ; 12..15 are the face_*; it is far
:
    cmp #21
    bne no_encara
    ; face_hero: the event's cell against the hero's, and on to `mirar` with the
    ; direction in A.
    jsr event_cell
    jsr toward_hero
    jmp mirar
no_encara:
    ; Turning without moving is not compiled: it does not get here.
    cmp #24
    bne no_es_salto
    jsr prepare_mover          ; who jumps, to collide with the others
    lda ruta_ev + 5, x
    dec a
    sta salto_orden             ; where the 24 is, in case it has to go back
    jsr armar_salto_ev
    lda ruta_ev + 13, x
    bne salto_arranco
    ; It could not land there. With the move route skippable the jump is skipped;
    ; without that RM2k moves the cursor back to the `begin_jump` and cuts the frame
    ; —`current_index = saved_index`—, and the jump is retried frame by frame until
    ; the cell frees up. Without `end_jump` there is nothing to go back to: it is
    ; always skipped.
    lda salto_trabado
    beq saltear
    lda ruta_ev + 18, x
    and #$04
    bne saltear
    lda salto_orden
    sta ruta_ev + 5, x
    jmp listo
saltear:
    jmp otra_orden
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    beq seguir
    cmp #26
    bcc seguir                  ; the others do nothing
    cmp #32
    bcc fijar_o_velocidad       ; 26 and 27 the facing, 28 and 29 the speed,
    cmp #34                     ; 30 and 31 the frequency
    bne no_es_grafico           ; and 34 the graphic, which carries an operand
    jmp cambiar_grafico         ; it is too far for a short branch
no_es_grafico:
    cmp #35
    bne no_es_sonido
    jmp sonido_ev               ; 35, with its operand
no_es_sonido:
    cmp #36
    bcc seguir                  ; 32 and 33, the switches, do not get here
    cmp #38
    bcs anim
    ; 36 turns going through walls on and 37 turns it off.
    and #$01
    eor #$01
    beq apagar_atraviesa
    lda ruta_ev + 12, x
    ora #$01
    bra guardar_banderas
apagar_atraviesa:
    lda ruta_ev + 12, x
    and #$FE
    bra guardar_banderas
anim:
    cmp #40
    bcs seguir
    ; 38 stops the animation and 39 resumes it.
    cmp #38
    bne seguir_anim
    lda ruta_ev + 12, x
    ora #$02
    bra guardar_banderas
seguir_anim:
    lda ruta_ev + 12, x
    and #$FD
guardar_banderas:
    sta ruta_ev + 12, x
seguir:
    jmp otra_orden
fijar_o_velocidad:
    cmp #30
    bcs ev_frecuencia
    cmp #28
    bcs velocidad
    ; 26 locks the facing, 27 releases it: `lock_facing`.
    and #$01
    beq fijar
    lda ruta_ev + 18, x
    and #$F7
    bra guardar_18
fijar:
    lda ruta_ev + 18, x
    ora #$08
    bra guardar_18
velocidad:
    ; 28 raises the speed and 29 lowers it, between 1 and 6.
    and #$01
    bne mas_lenta
    lda ruta_ev + 17, x
    cmp #6
    bcs seguir
    inc ruta_ev + 17, x
    bra seguir
mas_lenta:
    lda ruta_ev + 17, x
    cmp #2
    bcc seguir
    dec ruta_ev + 17, x
    bra seguir
ev_frecuencia:
    ; 30 raises the frequency and 31 lowers it, between 1 and 8. See `frecuencia`
    ; in `step_route`, which is the same for the hero: the frames standing still
    ; after each command come from here, and the converter rejects 1.
    and #$01
    bne menos_frec
    lda ruta_ev + 16, x
    cmp #RUTA_FRECUENCIA
    bcs seguir
    inc ruta_ev + 16, x
    bra seguir
menos_frec:
    lda ruta_ev + 16, x
    cmp #2
    bcc seguir
    dec ruta_ev + 16, x
    bra seguir
guardar_18:
    sta ruta_ev + 18, x
    bra seguir

; `change_graphic`: the only command with an operand. After the 34 comes the
; graphic's index in the map's table —two bytes per graphic, see
; `load_ruta_graficos`— and from there comes which character to take the twelve
; poses from and which palette to draw them with.
;
; It does not cost a frame: in `UpdateMoveRoute` it falls into the branch that
; does not touch the stop counter, so the next command runs on this same frame.
; It does not touch the pose either: the walk cycle stays where it was, which is
; what `SetSpriteGraphic` does.
cambiar_grafico:
    lda ruta_ev + 5, x          ; the cursor already advanced when reading the command
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x          ; and now past the operand
    asl a                       ; two bytes per entry
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_graf_buf, y
    sta graf_k                  ; its entry in `npc_poses`, or $FF
    lda ruta_graf_buf + 1, y
    sta graf_pal

    lda ruta_ev + 0, x
    phx
    jsr event_npc           ; its row, which is what has to change
    plx
    cpy #$FFFF
    beq listo_graf              ; an event without a graphic has no row
    lda #$FF
    sta npc_buf + 15, y         ; a CharSet imposes nothing on the cell
    lda graf_k
    cmp #$FF
    bne con_grafico
    ; A CharSet without a single opaque pixel: the event disappears. It is the same
    ; thing `hide_npc` does, and it is 185 of the game's 437 commands 34
    ; —`nobodyhere`—, so it is not the rare case but the most common one.
    lda #0
    sta npc_buf + 14, y
    bra listo_graf
con_grafico:
    sta npc_buf + 9, y          ; which character its poses come from
    lda npc_buf + 7, y
    and #$F1                    ; the palette lives in bits 1 to 3 of vhoopppN
    sta temp
    lda graf_pal
    asl a
    and #$0E
    ora temp
    sta npc_buf + 7, y
    lda #$FF
    sta npc_buf + 12, y         ; the pose in VRAM is no longer its own
    lda #1
    sta npc_buf + 14, y         ; and it is visible, in case it was hidden
listo_graf:
    jmp otra_orden

; `play_sound_effect`: 35, with the sound effect's index after it, in two bytes.
; Same as on the hero —see `sonido_heroe`—: `sonido_tocar`, `OP_SOUND`'s path,
; and without costing a frame. X is the slot, and `sonido_tocar` overwrites it.
sonido_ev:
    lda ruta_ev + 5, x          ; the cursor is already on the operand
    inc a
    inc a
    sta ruta_ev + 5, x          ; and moves past it
    dec a
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    lda [ruta_ptr], y
    phx
    jsr sonido_tocar            ; returns with 8-bit A
.a8
    plx
    jmp otra_orden
face:
    sec
    sbc #12
mirar:
    sta ruta_ev + 8, x          ; face_*: with frequency 8 it is instant and the
    lda ruta_ev + 16, x         ; next one follows; with another, it stands
    jsr after_turn               ; still for the turn's frames
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_ev + 9, x
    jmp listo


mover:
    sta ruta_dir
    stz ruta_dir + 1
    lda ruta_ev + 18, x
    and #$08
    bne sin_girar               ; always faces the same way: `lock_facing` or the
                                ; page's animation type
    lda ruta_dir
    cmp #4
    bcc derecho                 ; the usual four face where they go
    jsr face_diagonal        ; a diagonal has no pose of its own: see there
derecho:
    sta ruta_ev + 8, x          ; move_* faces where it goes
sin_girar:
    phx
    jsr event_cell        ; leaves its position in celda_x/celda_y
    jsr prepare_mover          ; and who it is, to collide with the others
    lda ruta_ev + 12, x
    and #$01
    sta atravesando             ; walk_everywhere: `cell_allowed` looks at it
    stz atravesando + 1
    lda ruta_dir
    cmp #4
    bcc recto
    jsr cell_allowed_diag        ; the two L's: nobody looks at the diagonal cell
    bra probado
recto:
    jsr cell_allowed
probado:
    plx
    stz atravesando
    stz atravesando + 1
    ; `plx` sets Z from what it pulls off the stack, so the answer has to be
    ; looked at again: with the `beq` right after the `plx`, slot 0 —which is X = 0—
    ; always said "blocked" and no move route ever moved.
    cmp #0
    bne no_bloqueado
    ; Blocked. With `skippable` —the forced ones, and the page ones that ask for
    ; it— it is skipped and the next one is tried; without it, the command is
    ; retried on the coming frame, and so on until the step goes through.
    lda ruta_ev + 18, x
    and #$04
    beq reintenta
    jmp otra_orden
reintenta:
    dec ruta_ev + 5, x
    jmp listo
no_bloqueado:
    phx
    lda ruta_dir
    jsr move_event_cell
    plx
    lda ruta_dir
    sta ruta_ev + 30, x         ; which way the step goes, which with the facing
    lda #1                      ; locked is not where it faces
    sta ruta_ev + 7, x          ; there is a step in progress
    jsr step_slot
    rep #$20
.a16
    lda #SALTO_PASO
    sec
    sbc temp
    sta ruta_ev + 22, x         ; and this frame's part already advanced
    sep #$20
.a8
    lda #1
    sta ruta_ev + 6, x
listo:
    rts
.endproc

; The forced move route ended on an event that has its own move route: the
; page's comes back, saved at +24 to +29, from the start and with the turn's
; wait. RM2k resumes it where it was; here it starts over.
.proc resume_page
.a8
.i16
    lda ruta_ev + 24, x
    sta ruta_ev + 1, x
    lda ruta_ev + 25, x
    sta ruta_ev + 2, x
    lda ruta_ev + 26, x
    sta ruta_ev + 3, x
    lda ruta_ev + 27, x
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x
    lda ruta_ev + 28, x
    sta ruta_ev + 16, x
    lda ruta_ev + 29, x
    sta ruta_ev + 17, x
    lda ruta_ev + 18, x
    ora #$01
    sta ruta_ev + 18, x
    lda ruta_ev + 28, x
    jsr after_turn
    sta ruta_ev + 9, x
    rts
.endproc

; The position of slot X's event, into celda_x/celda_y.
.proc event_cell
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tay
    lda ev_pos_buf, y
    sta celda_x
    lda ev_pos_buf + 2, y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; And moves it one cell in the direction A carries. It is done at the **start**
; of the step, not at its end: it is what `begin_step` does with the hero, and
; counting it differently would leave the hero and the events with the cell
; changed on different frames.
; Puts the cell of slot X's event in `celda_x`, `celda_y`. The jump uses it,
; which moves it all at once instead of one step at a time.
.proc move_cell_to_event
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    rts
.endproc

.proc move_event_cell
.a8
.i16
    sta ruta_dir
    stz ruta_dir + 1            ; it is used as a sixteen-bit index
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    sep #$20
.a8
    ; By table and not by four comparisons: with the diagonals the cell moves on
    ; both axes at once, and this way the straight case is the one with a zero on
    ; one side. X is left overwritten; the caller already saved it.
    ldx ruta_dir
    lda f:paso_dx, x
    beq sin_dx
    jsr with_sign_16
.a16
    clc                         ; returns with the accumulator in sixteen
    adc ev_pos_buf + 0, y
    sta ev_pos_buf + 0, y
    sep #$20
.a8
sin_dx:
    lda f:paso_dy, x
    beq sin_dy
    jsr with_sign_16
.a16
    clc
    adc ev_pos_buf + 2, y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
sin_dy:
    rts
.endproc

; The signed byte A carries, extended to sixteen bits. It leaves with the
; accumulator **in sixteen**, which is where the ones adding cells want it.
.proc with_sign_16
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc listo
    ora #$FF00
listo:
    rts
.endproc

