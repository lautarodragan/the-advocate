.segment "CODE"

; --- the hero ---------------------------------------------------------------
; RM2k does not move the character freely: it commits to a neighboring cell
; and covers the 16 pixels to it without being able to stop. That is why the
; state is the cell it is on plus how many pixels are left of the step in
; progress, and while there are any left no other direction is accepted.
;
; The four passability bits are: down $01, left $02, right $04, up $08.
; Crossing from one cell to the next asks both for permission: the source
; has to allow leaving on that side and the destination has to allow
; entering on the opposite one. Everything else —that the upper layer rules
; unless it is decoration, that wall faces can always be crossed— the
; converter already resolved.

PASS_DOWN  = $01
PASS_LEFT  = $02
PASS_RIGHT = $04
PASS_UP    = $08

.proc move_hero
.a8
.i16
    ; If there is a step in progress, it is finished: it cannot stop halfway
    ; through a cell.
    lda step_left
    beq quieto
    jsr advance_step
    rts

quieto:
    stz moving
    ; With no step in progress there is no move route step to record. It is
    ; cleared here and not when the route ends because what matters is the
    ; step, not the route.
    stz ruta_paso
    ; A jump in the air takes the whole frame, and it is checked **before**
    ; the move command counter: in RM2k jumping is not standing still
    ; —`IsStopping()` is `!(IsMoving() || IsJumping())`— so `Update` brings
    ; the jump down without going through `UpdateNextMovementAction`. With
    ; this inside `step_route`, which is only called with
    ; `ruta_i < ruta_n`, a jump that was the route's last command was brought
    ; down by nobody. See `salto_avanzar_heroe`.
    lda ruta_salto
    beq sin_salto
    jsr salto_avanzar_heroe
    rts
sin_salto:
    ; A forced move route rules over the pad: while any of it is left, the
    ; player does not move the hero. It is what RM2k does, and it is what
    ; lets a cutscene walk him on its own.
    ;
    ; A pending `wait` is also route, even when no commands are left: a route
    ; that **ends** in `wait` —there are 21 in the game, the first on map 1—
    ; leaves `ruta_i` equal to `ruta_n` with `ruta_espera` loaded, and without
    ; this nobody brought it down: `step_route` is the only one that counts
    ; it down. In RM2k the `wait` is one more command and the route still
    ; belongs to the hero until it is done. It stayed stuck forever, and
    ; `any_routes` and the action button, which look at it, answered "there is
    ; a route" until the next one.
    lda ruta_espera
    bne con_ruta
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta
con_ruta:
    jsr step_route
    rts
sin_ruta:
    ; The menu request, in the order of `UpdateNextMovementAction`: with a
    ; page running it is thrown away; with a message open it waits; and
    ; otherwise the menu opens and the hero does not walk this frame. It goes
    ; before looking at `esperando_n` because RM2k looks at
    ; `IsAnyEventStarting` afterwards.
    lda ev_activo
    beq menu_sin_pagina
    jsr menu_olvidar
    rts
menu_sin_pagina:
    lda msg_abierto
    bne no_derecha
    ; The encounter left pending is collected here: with no page running, no
    ; message open and no forced move route, which is the order of
    ; `Game_Player::UpdateNextMovementAction` —the encounter goes **before**
    ; the menu request—. `encounter_test` leaves the troop in `BA_TROPA`.
    jsl f:encounter_test
    cmp #0                      ; the `plx` over there left its own flags
    beq sin_encuentro
    ; And losing it is Game Over, just like a page battle with no defeat
    ; handler: a random encounter **never** brings them, because there is no
    ; page to emit them. Without this, defeat handed control back to the map
    ; with the whole party at zero HP, and from then on every battle was lost
    ; by itself before opening —`battle_run` answers defeat with nobody
    ; standing—. `battle_start` collects it: see
    ; tools/runtime/game_over.s.
    jsl f:game_over_always
    jmp battle_start
sin_encuentro:
    jsr acceso_leer
    bpl menu_sin_pedido         ; bit 7 is the request
    and #$7F
    jsr acceso_escribir
    jsr menu_pantalla
    rts
menu_sin_pedido:
    ; And a message on screen rules over the pad, just like the forced move
    ; route. It is what easyrpg's `Game_Player::UpdateNextMovementAction`
    ; does, returning without looking at the input if
    ; `Game_Message::IsMessageActive()`. It goes down here and not at the very
    ; top on purpose: the forced move route **does** walk with the message
    ; open —`UpdateMoveRoute` runs before the guard— and a step already begun
    ; is finished, because in RM2k you do not stop halfway through a cell.
    lda msg_abierto
    bne no_derecha
    ; And a page running also rules over the pad. It is the
    ; `if (Game_Map::IsAnyEventStarting()) return;` of
    ; `Game_Player::UpdateNextMovementAction`: while the interpreter has
    ; something in the foreground, the player does not walk.
    ;
    ; Without this, a touch event fired and the hero took **one more step**
    ; while the message was being composed: the message takes a few frames to
    ; open and `msg_abierto` only gets set at the end.
    lda ev_activo
    bne no_derecha
    lda esperando_n
    bne no_derecha
    lda pad
    and #PAD_UP
    beq no_arriba
    lda #DIR_UP
    sta hero_dir
    jsr try_up
    bra after_step
no_arriba:
    lda pad
    and #PAD_DOWN
    beq no_abajo
    lda #DIR_DOWN
    sta hero_dir
    jsr try_down
    bra after_step
no_abajo:
    lda pad
    and #PAD_LEFT
    beq no_izquierda
    lda #DIR_LEFT
    sta hero_dir
    jsr try_left
    bra after_step
no_izquierda:
    lda pad
    and #PAD_RIGHT
    beq no_derecha
    lda #DIR_RIGHT
    sta hero_dir
    jsr try_right
after_step:
    ; A step that really started —`step_left` says so— is an RM2k step:
    ; `IncSteps` and `UpdateEncounterSteps`, which there run after `Move()`
    ; and only if the hero moved. It goes in the pad branch and not inside
    ; `advance_step` because **the steps of a forced move route do not
    ; count**: there it returns earlier, through `IsMoveRouteOverwritten`.
    lda step_left
    beq no_derecha
    jsl f:encounter_step
no_derecha:
    rts
.endproc

; Each attempt checks the map's edge, then the two permissions, and only
; then starts the step.
; All four work with the 16-bit accumulator: the hero's cell no longer fits
; in a byte —there are maps 500 cells wide— and the permissions are looked
; up with 16-bit indexes.
.proc try_up
.a8
.i16
    rep #$20
.a16
    lda tile_y
    beq no                      ; already on the top row
    lda #PASS_UP
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_menos               ; the destination: one row of blocks up
    lda #PASS_DOWN              ; and that cell has to allow entering
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    dec a
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked         ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    dec tile_y
    lda #0
    sta step_dx
    lda #$FFFF              ; -1: ca65 does not accept a negative immediate
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_down
.a8
.i16
    rep #$20
.a16
    lda tile_y
    inc a
    cmp mapa_alto
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_mas                 ; one row of blocks down
    lda #PASS_UP
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    inc a
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked         ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    inc tile_y
    lda #0
    sta step_dx
    lda #1
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_left
.a8
.i16
    rep #$20
.a16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_menos               ; the cell next to it
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    lda tile_x
    dec a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked         ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    dec tile_x
    lda #$FFFF              ; -1: ca65 does not accept a negative immediate
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_right
.a8
.i16
    rep #$20
.a16
    lda tile_x
    inc a
    cmp mapa_ancho
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_mas
    lda #PASS_LEFT
    jsr can_enter
    beq no
    lda tile_x
    inc a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr hero_blocked         ; someone standing there stops it like a wall
    bne no8
    rep #$20
.a16
    inc tile_x
    lda #1
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; arrives in sixteen; the `sep` below narrows it
    sep #$20
.a8
no8:
    rts
.endproc

; --- passability ------------------------------------------------------------
; There is no longer a table with one byte per cell: the permissions travel in
; the block. It is two hops —the cell says which block it is, the block says
; which permissions it has— and in exchange the biggest map saves twenty
; kilobytes. That two cells drawn the same but with different permissions are
; not confused is guaranteed by the converter, which puts passability in the
; block's key.
;
; Where the hero is inside the grid is not an index either: it is a pointer
; that moves with him, one cell or one row per step. That way there is never
; a need to multiply or recompute a 24-bit address from scratch, which in
; LoROM is awkward because the banks are not contiguous.

; A = the bit that is needed. Returns with Z clear if the cell has it.
.proc can_leave
.a16
.i16
    sta temp
    lda tile_x                  ; the cell being left, for whatever a tile
    sta pasa_x                  ; event imposes on it
    lda tile_y
    sta pasa_y
    jsr ptr_desde_hero
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando             ; with walk_everywhere the answer is yes
    rts
.endproc

; The same, but on the cell celdas_ptr was left pointing at: each direction
; moves it on its own before calling, and if the step is accepted
; begin_step copies it to hero_ptr. That way the destination is computed only
; once.
.proc can_enter
.a16
.i16
    sta temp
    ; The destination cell: the hero's plus the step in `hero_dir`, which is
    ; always the step's direction, also in a forced move route.
    lda tile_x
    sta pasa_x
    lda tile_y
    sta pasa_y
    sep #$20
.a8
    lda hero_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando
    rts
.endproc

; The passage bits of cell `pasa_x`/`pasa_y`: the ones A brings —the
; terrain's, from `pass_del_ptr`— unless a tile event on the lower layer
; imposes its own. It is `Game_Map::IsPassableTile`: of the events standing
; there with an active page and a tile graphic on that layer the one with the
; highest id wins, and if its tile is not one that goes above, it rules. The
; refresh left the bits in the NPC's row, +15, or $FF if it imposes nothing;
; so this is one walk of the NPC table per step and not a pass over the
; pages. What is not modeled: the "conflict with itself" of a tile event that
; walks, because none walks. It enters and leaves in sixteen bits.
.proc pasa_con_evento
.a16
.i16
    ; From the last row backwards and in sixteen bits: the last one that
    ; imposes wins, so the first one found that way is the answer. It runs
    ; twice for every step that starts, and front to back with a `rep`/`sep`
    ; per row it was nine lines each time in the race, with forty cars: see
    ; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    sta temp + 2
    lda pasa_hay
    and #$00FF
    beq ninguno                 ; no row on this map imposes anything
    ldy npc_total
    bra siguiente
otra:
    lda npc_buf + 14, y         ; whether it is there, and above that what it imposes
    cmp #$FF00
    bcs siguiente               ; $FF: imposes nothing
    bit #$00FF
    beq siguiente               ; hidden: not there
    lda npc_buf + 8, y          ; its event, and with it its cell
    and #$00FF
    asl a
    asl a                       ; times EV_STRIDE
.assert EV_STRIDE = 4, error, "the arithmetic above multiplies by four by hand"
    tax
    lda ev_pos_buf, x
    cmp pasa_x
    bne siguiente
    lda ev_pos_buf + 2, x
    cmp pasa_y
    bne siguiente
    lda npc_buf + 14, y
    xba
    and #$00FF                  ; the passage bits it imposes
    rts
siguiente:
    tya
    sec
    sbc #NPC_STRIDE
    tay
    bpl otra
ninguno:
    lda temp + 2                ; none: the terrain's
    rts
.endproc

.proc sumar_a_pasa_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_x
    sta pasa_x
    sep #$20
.a8
    rts
.endproc
.proc sumar_a_pasa_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_y
    sta pasa_y
    sep #$20
.a8
    rts
.endproc

.proc pass_del_ptr
.a16
.i16
    lda [celdas_ptr]            ; which block this cell is
    jsr celda_sustituida
    tay
    sep #$20
.a8
    lda [pass_ptr], y
    rep #$20
.a16
    and #$00FF
    rts
.endproc

.proc ptr_desde_hero
.a16
.i16
    lda hero_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda hero_ptr + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_hero
.a16
.i16
    lda celdas_ptr
    sta hero_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    sta hero_ptr + 2
    rep #$20
.a16
    rts
.endproc

; The pointer to cell (celda_x, celda_y) of the grid.
;
; It is separate from `init_hero_ptr` because now more than one thing walks:
; the events' forced move routes query cells that are not the hero's, and
; having the arithmetic written twice is how they drift apart.
;
; The offset is `celda_y * tira_paso_col + celda_x * 2`, with the CPU's
; multiplier —eight by eight bits, so in three products: the one of the two
; low bytes and the two cross ones, which land shifted by a byte; the one of
; the two high bytes falls outside the sixteen— and not by adding one row for
; every row down, which is what it did until 2026-09-27: on row 26 that was
; four lines per step of every walking event, and in the race five steps
; start in the same frame. No interrupt uses the multiplier: see the fade in
; `irq_musica`.
;
; The grid fits in 64 KB and lives in the upper half of the two banks —see
; `ptr_mas`—, so the offset fits in sixteen bits and its bit 15 tells the
; bank: without it, the upper half of $7E (the bit gets set), and with it
; that of $7F (it already has it).
.proc ptr_de_celda
.a8
.i16
    lda celda_y
    sta WRMPYA
    lda tira_paso_col
    sta WRMPYB                  ; eight cycles: what follows pays for them
    rep #$20
.a16
    lda celda_x
    asl a                       ; each cell takes two bytes
    sta celdas_ptr
    lda RDMPYL                  ; y low times stride low
    clc
    adc celdas_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda tira_paso_col + 1
    beq sin_paso_alto
    sta WRMPYB                  ; y low times stride high: WRMPYA is still y
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc celdas_ptr + 1
    sta celdas_ptr + 1
sin_paso_alto:
    lda celda_y + 1
    beq sin_y_alta
    sta WRMPYA
    lda tira_paso_col
    sta WRMPYB                  ; y high times stride low
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc celdas_ptr + 1
    sta celdas_ptr + 1
sin_y_alta:
    lda celdas_ptr + 1
    bmi alta
    ora #>$8000
    sta celdas_ptr + 1
    lda #^GRILLA
    sta celdas_ptr + 2
    rts
alta:
    lda #^GRILLA_ALTA
    sta celdas_ptr + 2
    rts
.endproc
.assert .loword(GRILLA) = $8000 && .loword(GRILLA_ALTA) = $8000 && ^GRILLA_ALTA = ^GRILLA + 1, error, "ptr_de_celda builds the pointer with the grid in the two upper halves"

; Where the hero starts inside the grid.
.proc init_hero_ptr
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
    jsr ptr_de_celda
    rep #$20
.a16
    jsr ptr_a_hero
    sep #$20
.a8
    rts
.endproc

; Starts the step: a whole cell to cover —128 half units, see
; `paso_medio_por_vel`— and the index already on the new cell, which is how
; RM2k keeps count.
.proc begin_step
.a8
.i16
    lda #128
    sta step_left
    rep #$20
.a16
    jsr ptr_a_hero              ; RM2k counts from the destination cell, which is
    sep #$20                    ; where can_enter left the pointer pointing
.a8
    jsr advance_step
    rts
.endproc

; Advances this frame's pixels and, if that completes the step, leaves the
; character exactly on the cell.
.proc advance_step
.a8
.i16
    lda #$01
    sta moving
    ; What is left of the step goes down by whatever the speed says, and the
    ; pixels are **recomputed** from the destination cell and not
    ; accumulated: with half a pixel per frame there is nothing whole to add.
    ; `step_dx` and `step_dy` are the step's direction, -1, 0 or 1.
    jsr hero_anim_frames  ; incidentally leaves X at the speed minus one
    lda step_left
    sec
    sbc paso_medio_por_vel, x
    bcs no_negativo
    lda #0
no_negativo:
    sta step_left
    lsr a
    lsr a
    lsr a                       ; the pixels left
    rep #$20
.a16
    and #$00FF
    sta temp                    ; nobody holds it during a step
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    ldx step_dx
    beq x_listo
    bmi x_desde_la_derecha
    sec
    sbc temp
    bra x_listo
x_desde_la_derecha:
    clc
    adc temp
x_listo:
    sta hero_x
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    ldx step_dy
    beq y_listo
    bmi y_desde_abajo
    sec
    sbc temp
    bra y_listo
y_desde_abajo:
    clc
    adc temp
y_listo:
    sta hero_y
    sep #$20
.a8
    lda step_left
    bne sigue                   ; the step has not finished yet
    ; While the hero has forced move route left, nothing is stepped on:
    ; neither door nor touch event. It is the `!IsMoveRouteOverwritten()` of
    ; `Game_Player::UpdateMovement`, and the last step does count because in
    ; `Game_Character::UpdateMovement` a movement that is the last command
    ; cancels the whole route **before** the check —it is commented there:
    ; "If the last command of a move route is a move or jump, RPG_RT cancels
    ; the entire move route immediately"—. With `ruta_i` already past the
    ; last command, the route is cancelled; with commands left to read, it is
    ; not. It is what lets the opening cutscene step on the event that turns
    ; the tint off: it is three cells up and the event is on the third.
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta                ; no commands left: door and touch
    ; Some are left: the step is a middle one, and the frequency says how
    ; many frames to stand still before reading the next. It holds even if
    ; the pad started the step: in RM2k `UpdateMovement` sets the counter to
    ; zero when any step ends, and `ForceMoveRoute` already set the route's
    ; limit.
    lda ruta_frec
    jsr after_step
    sta ruta_espera
    bra sigue
sin_ruta:
    ; Just stopped on the cell: is there a touch event? A door is one of
    ; those —a touch page whose only command is the `Teleport`— so it has no
    ; path of its own: it goes through the interpreter, like any other
    ; teleport.
    jsr try_touch
sigue:
    rts
.endproc

; --- walk animation ---------------------------------------------------------
; The cycle is four steps over three CharSet frames: 0, 1, 2, 1. The middle
; one is the standing pose, and it is the one it goes back to when the d-pad
; is released.
.proc animate_hero
.a8
.i16
    ; With the animation paused by a move route the pose stays on the middle
    ; one, walking or not: RM2k calls `ResetAnimation` on every frame while
    ; `IsAnimPaused()`, which leaves the middle frame and the counter at
    ; zero.
    lda ruta_anim_para
    bne quieto
    lda moving
    bne caminando
quieto:
    lda #1                      ; standing: the middle frame
    sta anim_step
    stz anim_timer
    rts

caminando:
    ; The count goes up and is compared with the limit **for the current
    ; speed**, like `GetAnimCount() >= stationary_limit`: if a move route
    ; changes the speed halfway through a frame, the next frame already comes
    ; out with the new one. Counting down from the limit, as before, the new
    ; one only took effect one frame later: one frame off from RM2k.
    inc anim_timer
    jsr hero_anim_frames
    cmp anim_timer
    beq cambia
    bcs listo                   ; the count has not reached the limit yet
cambia:
    stz anim_timer
    lda anim_step
    inc a
    and #$03                    ; the cycle is four steps
    sta anim_step
listo:
    rts
.endproc

