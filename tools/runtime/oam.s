.segment "CODE"

; --- building the OAM ------------------------------------------------------
; One object per NPC plus one for the hero, in the order RM2k draws them:
; first by layer and only then by Y. On the console the object with the
; lowest OAM index is the one shown on top, so the walk goes from front to
; back — which is how the converter left the table sorted.
;
; The hero is slotted in where its key puts it, it does not always go first
; nor always last: a "below" event has to stay under it even if it is further
; forward on screen, and an "above" one always covers it.
.proc build_oam
.a8
.i16
    ; Everything hidden before starting. Hiding only the tail at the end
    ; leaves the objects this frame did not use with the previous one's data,
    ; and all it takes is the camera moving for the count to change and one of
    ; them to reappear where it does not belong. It is 128 writes and it gets
    ; rid of that whole class of bug.
    jsr clear_oam
    stz high_acc
    stz hero_drawn
    rep #$20
.a16
    stz high_ptr
    stz oam_slot
    stz npc_ofs
    ; The hero's key: its layer on top and its Y below, same as in the table.
    lda hero_y
    and #$0FFF
    ora #(HERO_LAYER * 4096)
    sta hero_key
    sep #$20
.a8
    ; The timer goes before anyone: its objects are the lowest-indexed and
    ; therefore the ones shown in front. It leaves `obj_grande` at 32x32.
    lda #$02
    sta obj_grande
    jsr timer_oam
    jsr imagen_oam              ; and the picture behind it: see `imagen_oam`
    jsr animacion_dibujo_oam    ; and the battle animation behind the picture:
                                ; `Priority_BattleAnimation` is 110 against
                                ; `Priority_PictureOld`'s 120

recorrer:
    ; Each row, with X on it. `place_hero` and `place_npc` clobber X, so it is
    ; reloaded from `npc_ofs` on every pass.
    ldx npc_ofs
    cpx npc_total
    beq ultimos

    lda hero_drawn
    bne toca_npc
    ; Does the hero go before this NPC? Yes if its key is greater or equal,
    ; because the table goes from greater to smaller.
    rep #$20
.a16
    lda hero_key
    cmp npc_buf + 4, x
    sep #$20
.a8
    bcc toca_npc
    jsr place_hero
    bra recorrer

toca_npc:
    lda npc_buf + 14, x
    beq escondido               ; its active page draws nothing
    ; What `emit_object` was going to discard is discarded **here**, with the
    ; same comparison and before building the rest of the row. It discards the
    ; same as before, object by object, so the OAM comes out identical; what
    ; changes is how much an NPC that is not visible costs. A map like 11 has
    ; fifty drawn rows and thirty on screen, and the twenty outside paid for
    ; the Y, the jump and the two tile bytes for `emit_object` to throw them
    ; away. The X goes here, in the loop, and not in `place_npc`: half of them
    ; go out through it, and that way they do not even pay for the `jsr`. In
    ; the race there are forty cars and ten are visible.
    rep #$20
.a16
    lda npc_buf + 0, x          ; its position on the map
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    clc
    adc #32
    cmp #(256 + 32)
    sep #$20
.a8
    bcs escondido               ; `sep` does not touch the carry
    jsr place_npc
escondido:
    rep #$20
.a16
    lda npc_ofs
    clc
    adc #NPC_STRIDE
    sta npc_ofs
    sep #$20
.a8
    bra recorrer

ultimos:
    lda hero_drawn
    bne cerrar
    jsr place_hero
cerrar:
    jsr lluvia_oam              ; the drops, at the very end
    jsr flush_high
    rts
.endproc

; The hero's jump: consumes the move commands up to `end_jump`, adds up what
; they contribute and puts it on the other side at once. How long it lasts
; does not depend on the distance: `remaining_step` goes down from 256 to 0 by
; `hero_jump` per frame, whether it jumps one cell or five; at speed 4
; it is eleven frames.
.proc armar_salto_heroe
.a8
.i16
    stz salto_dx
    stz salto_dy
buscar:
    lda ruta_i
    cmp ruta_n
    bcs sin_fin
    jsr hero_command
    cmp #25
    beq con_fin
    jsr acumular_salto
    bra buscar
sin_fin:
    ; Without `end_jump` the jump is skipped and whatever was left of the move
    ; route is lost, which is what RM2k does on reaching the end.
    stz ruta_salto
    rts

con_fin:
    jsr salto_a_celdas          ; the offset, signed and in sixteen bits
    rep #$20
.a16
    lda tile_x
    clc
    adc salto_dx16
    sta celda_x
    lda tile_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    ; Walking through walls it lands on any cell: it is the same
    ; `if (self.GetThrough()) return true;` that a step looks at, and
    ; `puede_caer` reads it from `atravesando`, which nobody was setting here.
    ; The move route of EV0041 on map 8 —`through`, a one-cell jump over the
    ; fence, four steps— jumps in RM2k and walked in the ROM: the jump was
    ; skipped because of the fence and the steps after it did go through.
    ; Measured on 2026-09-10, 40840 pixels on frame 60.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    jsr puede_caer
    php
    stz atravesando
    stz atravesando + 1
    plp
    bne se_puede
    stz ruta_salto              ; it cannot land there: the jump is skipped
    rts
se_puede:
    rep #$20
.a16
    lda celda_x
    sta tile_x
    lda celda_y
    sta tile_y
    sep #$20
.a8
    jsr init_hero_ptr
    ; Which way it ends up facing. In place nothing changes: RM2k only sets
    ; the facing when the jump moves.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    jsr direccion_del_salto
    sta hero_dir
sin_girar:
    ; The first decrement goes in the same frame that builds the jump, as in
    ; `Game_Character::Update`, which after `UpdateNextMovementAction` already
    ; sees it jumping and calls `UpdateMovement`. SALTO_PASO is 256 and does
    ; not fit in a byte: `256 - s` in eight bits is the two's complement of
    ; `s`, which is never zero.
    jsr hero_jump
    eor #$FF
    inc a
    sta ruta_salto
    ; The cell is already the target one and the pixels trail behind, same as
    ; in a step: that way the camera follows the arc instead of jumping at
    ; once.
    jsr salto_posicion_heroe
    rts
.endproc

; One frame of a hero jump that is in the air: lowers the arc it has left and
; redraws it where it belongs. The cell already moved at the start, so the
; only thing that happens here is the pixels.
;
; It lives outside `step_route` —and `move_hero` calls it— because in RM2k
; the one that lowers the jump is `Game_Character::Update`, which checks
; `IsJumping()` **before** asking whether move commands are left, and the one
; that turns it off is `UpdateMovement`. While it was inside `step_route`,
; a jump that was the last move command of the move route was lowered by
; nobody: `move_hero` only went in there with `ruta_i < ruta_n`, and with the
; jump at the end the counter was already at its limit on the next frame. The
; hero stayed floating mid-arc forever, and 196 of the game's 410 move routes
; with a jump end on the jump. See `test_salto_colgado.py`.
;
; The decrement is read from the speed every frame, like RM2k's `Update`,
; which calls `GetMoveSpeed()` every time. Until 2026-09-26 it was the
; constant for speed 4 and an `increase_movement_speed` on the hero changed
; its step and not its jump. See `test_salto_velocidad.py`.
.proc salto_avanzar_heroe
.a8
.i16
    ; `ruta_salto - s` without storing `s` anywhere: `~s + 1` with the carry
    ; set is the subtraction, and the carry comes out clear if there was a
    ; borrow.
    jsr hero_jump
    eor #$FF
    sec
    adc ruta_salto
    bcs guardar
    lda #0
guardar:
    sta ruta_salto
    jmp salto_posicion_heroe
.endproc

; `hero_x` and `hero_y` from the target cell and what is left of the jump. It
; is RM2k's `GetSpriteX`: `x * 256 - dx * remaining` and **then** the division
; by sixteen, which is what avoids the pixel too many or too few every time
; the decrement is not a multiple of sixteen.
.proc salto_posicion_heroe
.a8
.i16
    jsr salto_a_celdas
    lda ruta_salto
    sta salto_resta
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; the cell in RM2k units: times 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_x
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_y
    sep #$20
.a8
    rts
.endproc

; `salto_dx` and `salto_dy` sign-extended to sixteen bits.
.proc salto_a_celdas
.a8
.i16
    rep #$20
.a16
    lda salto_dx
    and #$00FF
    cmp #$0080
    bcc dx_positivo
    ora #$FF00
dx_positivo:
    sta salto_dx16
    lda salto_dy
    and #$00FF
    cmp #$0080
    bcc dy_positivo
    ora #$FF00
dy_positivo:
    sta salto_dy16
    sep #$20
.a8
    rts
.endproc

; Which way the jumper ends up facing: the axis with the longer travel wins,
; and on a tie the vertical. It is the `if (abs(dy) >= abs(dx))` of
; `Game_Character::Jump`.
.proc direccion_del_salto
.a8
.i16
    rep #$20
.a16
    lda salto_dx16
    bpl dx_pos
    eor #$FFFF
    inc a
dx_pos:
    sta mirar_abs
    lda salto_dy16
    bpl dy_pos
    eor #$FFFF
    inc a
dy_pos:
    cmp mirar_abs
    bcc horizontal
    lda salto_dy16
    sep #$20
.a8
    bmi arriba
    lda #DIR_DOWN
    rts
arriba:
    lda #DIR_UP
    rts
.a16
horizontal:
    lda salto_dx16
    sep #$20
.a8
    bmi izquierda
    lda #DIR_RIGHT
    rts
izquierda:
    lda #DIR_LEFT
    rts
.endproc

; Moves `salto_px`/`salto_py` back by what the jump has left and leaves in
; `salto_alto` how much the drawing has to be raised.
;
; The height is `GetJumpHeight`: it goes up and down with what is left, and
; the curve is not linear but RM2k's table. It only moves the **drawing**:
; the order against the others comes from `GetScreenY(false)`, that is,
; without the jump, so whoever is in the air does not move ahead.
.proc alto_del_salto
.a8
.i16
    stz salto_alto
    stz salto_alto + 1
    lda salto_resta
    bne hay
    rts
hay:
    ; What is left or what was traveled, the smaller of the two, over eight;
    ; and then RM2k's table, which is not linear. It is `GetJumpHeight`, and it
    ; only moves the **drawing**: the order against the others comes from
    ; `GetScreenY(false)`, that is, without the jump, so whoever is in the air
    ; does not move ahead.
    cmp #(SALTO_PASO / 2)
    bcc de_bajada
    eor #$FF                    ; 256 - remaining, with a one-byte remaining
    inc a
de_bajada:
    lsr a
    lsr a
    lsr a
    cmp #5
    bcs mediana
    asl a                       ; less than five: double
    bra guardar
mediana:
    cmp #13
    bcs tope
    clc
    adc #4                      ; five to twelve: plus four
    bra guardar
tope:
    lda #16
guardar:
    sta salto_alto
    rts
.endproc

; `salto_val` times `salto_resta`, signed, into `salto_prod`. The console's
; unit multiplies unsigned and eight bits at a time, so it is done on the
; absolute value and the sign is given back at the end.
.proc producto_salto
.a8
.i16
    rep #$20
.a16
    lda salto_val
    sta salto_signo
    bpl positivo
    eor #$FFFF
    inc a
    sta salto_val
positivo:
    sep #$20
.a8
    lda salto_val
    sta WRMPYA
    lda salto_resta
    sta WRMPYB                  ; starts it: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta salto_prod
    lda salto_signo
    bpl listo
    lda #0
    sec
    sbc salto_prod
    sta salto_prod
listo:
    sep #$20
.a8
    rts
.endproc

; An event's jump. Same as the hero's, but reading the move route from the
; cartridge and keeping the state in the slot. X is the slot and it has to be
; returned intact.
.proc armar_salto_ev
.a8
.i16
    stz salto_dx
    stz salto_dy
    stz salto_trabado
buscar:
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcs sin_fin
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x
    cmp #25
    beq con_fin
    phx
    jsr acumular_salto
    plx
    bra buscar
sin_fin:
    ; Without `end_jump` the jump is skipped and whatever was left of the move
    ; route is lost.
    stz ruta_ev + 13, x
    rts

con_fin:
    ; `walk_everywhere`: `CheckOrMakeWayEx` returns early with
    ; `if (self.GetThrough()) return true;` right after the bounds check, so
    ; one walking through walls lands anywhere. Without this, the stone in
    ; Core's memory is a closed cell and the jump is skipped; taro saw it as
    ; Core moving on top of his little island and never jumping, and the move
    ; route that moves him starts precisely with an `atravesar_on`.
    lda ruta_ev + 12, x
    and #$01
    sta atravesando
    stz atravesando + 1
    phx
    jsr event_cell        ; its cell, which `puede_caer` needs
    jsr salto_a_celdas
    rep #$20
.a16
    lda celda_x
    clc
    adc salto_dx16
    sta celda_x
    lda celda_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    jsr puede_caer
    plx
    stz atravesando
    stz atravesando + 1
    cmp #0                      ; `plx` sets Z from what it pulls off the stack
    bne se_puede
    stz ruta_ev + 13, x
    inc salto_trabado           ; there was an `end_jump` and the cell is taken
    rts
se_puede:
    ; The target cell, which `event_cell` left in celda_x/celda_y.
    phx
    jsr move_cell_to_event
    plx
    lda salto_dx
    sta ruta_ev + 14, x
    lda salto_dy
    sta ruta_ev + 15, x
    ; Which way it ends up facing. In place nothing changes.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    phx
    jsr direccion_del_salto
    plx
    sta ruta_ev + 8, x
sin_girar:
    jsr slot_jump
    sta temp
    lda #0                      ; 256 minus this frame's, in eight bits
    sec
    sbc temp
    sta ruta_ev + 13, x
    rts
.endproc

; `npc_px` and `npc_py` from the target cell and what is left of the jump. It
; is the same computation as `salto_posicion_heroe`, with the division at the
; end.
.proc salto_posicion_npc
.a8
.i16
    jsr salto_a_celdas
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; the cell in RM2k units: times 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_px
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_py
    sep #$20
.a8
    rts
.endproc

; --- a move route's jump ---------------------------------------------------
; Adds to the jump what a move command contributes. It is the loop in
; `BeginMoveRouteJump`: what lies between `begin_jump` and `end_jump` **is not
; walked**, it is added up, and only the `move_*` and the turning ones count.
; Everything else —a wait, stopping the animation, changing the speed— RM2k
; consumes in there without doing anything, and the game puts in all three.
;
; A comes in with the move command's code; leaves `salto_dx` and `salto_dy`.
.proc acumular_salto
.a8
.i16
    cmp #8                      ; the four straight ones and the four diagonals:
    bcs no_mueve                ; inside a jump a diagonal contributes its
                                ; two axes, which is what RM2k adds
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda salto_dx
    clc
    adc f:paso_dx, x
    sta salto_dx
    lda salto_dy
    clc
    adc f:paso_dy, x
    sta salto_dy
    rts
no_mueve:
    ; The `face_*` contribute no offset, and turning without moving is not
    ; compiled, so inside a jump there is nothing else to do: RM2k consumes
    ; the rest without touching anything, not even a `wait`.
    rts
.endproc

; Can it land on cell `celda_x`, `celda_y`? Returns with Z=0 if so.
;
; It is not the same as being able to step on it walking: it is
; `CheckOrMakeWayEx` with the character jumping, which **skips the face being
; left** —hence one can jump from a place one could not walk out of— and asks
; for the target to be passable from all four sides, not only from the one
; being entered.
.proc puede_caer
.a8
.i16
    rep #$20
.a16
    lda celda_x
    bmi no_16
    cmp mapa_ancho
    bcs no_16
    lda celda_y
    bmi no_16
    cmp mapa_alto
    bcs no_16
    sep #$20
.a8
    ; One who walks through walls lands on any cell of the map: it is the
    ; `if (self.GetThrough()) return true;` of `CheckOrMakeWayEx`, which comes
    ; **after** checking the bounds and before everything else.
    lda atravesando
    beq mira_el_paso
    lda #1
    rts
mira_el_paso:
    jsr ptr_de_celda
    rep #$20
.a16
    jsr pass_del_ptr
    sep #$20
.a8
    and #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    cmp #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    bne no
    ; And that nobody is standing there: the jump is also `MakeWay`, and it
    ; looks at the others the same as a step does.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    jsr cell_blocked
    bne no
    lda #1
    rts
.a16
no_16:
    sep #$20
.a8
no:
    lda #0
    rts
.endproc


; --- an NPC ----------------------------------------------------------------
.proc place_npc
.a8
.i16
    ; The X was already set —and discarded if not visible— by the loop in
    ; `build_oam`: see there. The other half of the discard is left, the Y.
    ldx npc_ofs
    rep #$20
.a16
    lda npc_buf + 2, x
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    ; And the jump's arc, if it is jumping. It goes separately and in eight
    ; bits because byte 11 of the row is the last of the slot: reading it two
    ; at a time would take the first one of the next along.
    sep #$20
.a8
    stz temp + 1
    lda npc_buf + 11, x
    sta temp
    rep #$20
.a16
    lda obj_y
    sec
    sbc temp
    sta obj_y
    ; The other half of the discard, with the jump already added: the same
    ; cut at 224 as `emit_object`, for the same reason.
    clc
    adc #32
    cmp #(224 + 32)
    bcs fuera
    sep #$20
.a8
    lda npc_buf + 6, x
    sta obj_tile
    lda npc_buf + 7, x
    sta obj_attr
    jsr emit_object
    rts
.a16
fuera:
    sep #$20
.a8
    rts
.endproc

; --- the hero --------------------------------------------------------------
.proc place_hero
.a8
.i16
    inc hero_drawn

    ; The CharSet frame: steps 0 and 2 are the side ones, and steps 1 and 3
    ; are both the middle pose.
    lda anim_step
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    sta temp

    ; The pose is direction*3 + frame, and which tile it gets is said by the
    ; table of the actor at the front of the party. It used to be computed
    ; —the hero was always character 0 of the bank, so its block came out of a
    ; computation—, and that stopped holding once `ChangePartyMembers` can
    ; change the leader on the fly. The table also makes room for tiles wider
    ; than eight bits, which is what happens as soon as there are a few
    ; characters in the bank.
    lda hero_dir
    asl a
    clc
    adc hero_dir                ; direction * 3
    clc
    adc temp                    ; plus the frame
    sta pose_heroe
    ; With no party the pointer to the table stays at zero: nothing is drawn.
    lda hero_poses + 2
    beq sin_dibujar
    ; The pointer to the pose: three bytes per pose in the actor's table.
    lda pose_heroe
    asl a
    clc
    adc pose_heroe              ; times three
    rep #$20
.a16
    and #$00FF
    tay
    lda [hero_poses], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [hero_poses], y
    sta vq_src + 2
    ; $FFFFFF is the sentinel for "this actor has no graphic". It happens to
    ; actor 10, DummyHero, which is the one the game starts with: RM2k does
    ; not draw anything either.
    lda vq_src
    and vq_src + 1
    cmp #$FF
    beq sin_dibujar

    ; The tile is fixed: the hero lives in block 0 of the bank, and what
    ; changes are the block's tiles. If the pose in VRAM is a different one,
    ; the new one is queued and uploaded in the next vblank, along with this
    ; OAM.
    stz obj_tile
    lda #HERO_PRIORITY          ; below the layer that covers it
    ora hero_pal
    sta obj_attr
    lda pose_heroe
    cmp hero_pose_vram
    beq misma_pose
    sta hero_pose_vram
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne misma_pose
    lda #$FF
    sta hero_pose_vram          ; the queue was full: next frame
misma_pose:

    ; A jump in progress moves the drawing back and raises it. The position is
    ; RM2k's, with the division **at the end**: `x * 256 - dx * remaining`
    ; over 16. Dividing the decrement separately gives a pixel too many or too
    ; few every time it is not a multiple of 16, that is, half of the frames.
    lda ruta_salto
    sta salto_resta
    jsr alto_del_salto
    rep #$20
.a16
    lda hero_x
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda hero_y
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sec
    sbc salto_alto              ; the arc raises the drawing, not the order
    sta obj_y
    sep #$20
.a8
    jsr emit_object
sin_dibujar:
    rts
.endproc

; --- one object in OAM -----------------------------------------------------
; Discards whatever falls off screen: the object's X has nine bits and the Y
; only eight, so a far-away object would wrap around and show up on the other
; side. The ranges are shifted by 32 pixels so they can be compared unsigned.
; The +32 in both comparisons shifts the origin so that an object peeking in
; from the top or from the left —and that arrives here with a negative
; coordinate— gives a small number instead of a huge one, and a single
; unsigned comparison handles both edges.
.proc emit_object
.a8
.i16
    rep #$20
.a16
    lda obj_x
    clc
    adc #32
    cmp #(256 + 32)
    sep #$20
.a8
    bcs fuera
    rep #$20
.a16
    lda obj_y
    clc
    adc #32
    ; The bottom edge is not discarded at 256 but at 224, and it is not the
    ; same thing. The OAM Y has 8 bits and the screen 224 lines, so values 224
    ; to 255 are ambiguous: the PPU always reads them as "a bit above the top
    ; edge" and draws the object wrapped. With the cut at 256, an NPC leaving
    ; through the bottom was stored with a Y in that band and reappeared at
    ; the top, showing first its feet and then all of it.
    ;
    ; The ambiguity is needed and cannot be removed: it is what makes an
    ; object at y = -31 show its last line on line 0. What must not happen is
    ; that an object that really is at the bottom reaches it.
    cmp #(224 + 32)
    sep #$20
.a8
    bcs fuera

    rep #$20
.a16
    lda oam_slot
    asl a
    asl a
    tax                         ; four bytes per object
    sep #$20
.a8
    lda obj_x
    sta oam, x
    lda obj_y
    sta oam + 1, x
    lda obj_tile
    sta oam + 2, x
    lda obj_attr
    sta oam + 3, x

    ; Its two bits in the small table: X's ninth and the size.
    lda obj_x + 1
    and #$01
    ora obj_grande              ; 32x32 the characters, 8x8 the digits
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
fuera:
    rts
.endproc

; Puts two bits on top of the accumulator and shifts it. After four objects
; the byte ends up built in the order the console expects.
.proc push_high
.a8
.i16
    pha
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    pla
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    ora high_acc
    sta high_acc

    lda oam_slot
    and #$03
    cmp #$03
    bne listo                   ; the byte is not complete yet
    jsr store_high
listo:
    rts
.endproc

.proc store_high
.a8
.i16
    lda high_acc
    ldx high_ptr
    sta oam_high, x
    stz high_acc
    rep #$20
.a16
    inc high_ptr
    sep #$20
.a8
    rts
.endproc

; On closing a byte may be left half done. It is completed with hidden
; objects, which will end up with the Y off screen anyway.
.proc flush_high
.a8
.i16
completar:
    lda oam_slot
    and #$03
    beq listo
    lda #$02
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
    bra completar
listo:
    rts
.endproc

