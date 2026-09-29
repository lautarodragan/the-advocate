.segment "CODE"

; The next command of the hero's move route, in A, and the cursor already
; advanced. Clobbers Y and overwrites `ruta_ptr`, which belongs to the events'
; pass and is not live while the hero walks: `lda [ptr], y` only reads from the
; direct page, and `ruta_heroe` does not fit there.
;
; The index goes to Y through a sixteen-bit A with the high byte cleared: `tay`
; transfers both bytes of the accumulator even when A is eight-bit. It is the
; trap noted at the top of main.s, and here it already made the move route
; read garbage and stop at the first step.
.proc orden_del_heroe
.a8
.i16
    rep #$20
.a16
    lda ruta_heroe
    sta ruta_ptr
    lda ruta_i
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_heroe + 2
    sta ruta_ptr + 2
    lda [ruta_ptr], y
    inc ruta_i
    rts
.endproc

; One command of the forced move route. Turning does not use up a frame and it
; goes on with the next; waiting does; and moving starts a one-cell step, which
; `advance_step` then walks like any other. A blocked move is skipped: RM2k
; would retry forever and a hung test says nothing.
; The jumps in here go with `jmp` and not `bra`: the body went from seven
; commands to fifteen and a `bra`'s 127 bytes of reach fell short three times
; in a row. It is the same trap that had already cut twice in the chain of
; `cmp` that was `correr_codigo`'s dispatch before the table, and it is fixed
; the same way.
.proc paso_de_ruta
.a8
.i16
    ; A `wait` in progress takes the whole frame and does not look at the move
    ; route. It is RUTA_ESPERA frames and not one: it is RM2k's
    ; `SetMaxStopCountForWait`, which with frequency 8 gives twenty.
    ; The jump in progress is not looked at here but in `move_hero`: see
    ; `salto_avanzar_heroe`.
    lda ruta_espera
    beq sin_espera
    dec ruta_espera
    rts
sin_espera:
otra_orden:
    lda ruta_i
    cmp ruta_n
    bcc hay_orden
    jmp listo                   ; the move route is over; `bcs` no longer reaches
hay_orden:
    jsr orden_del_heroe

    cmp #23                     ; wait: this one and the RUTA_ESPERA - 1 after it,
    bne no_es_wait              ; plus the turn's if the frequency is low
    lda ruta_frec
    jsr tras_giro
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_espera
    jmp listo
no_es_wait:
    cmp #12
    bcs no_es_mover
    jmp mover                   ; 0..3 are the move_*
no_es_mover:
    cmp #16
    bcc face                    ; 12..15 are the face_*
    ; Turning without moving is not compiled, and facing the hero —21— and
    ; going toward him —9— are not compiled **on the hero**: see
    ; `RUTA_ORDENES` in eventos.py. They do not get here. 9 would also fall
    ; into `mover` above, which with a direction that is not 0..3 sends the
    ; hero left by elimination, which is the same trap as the diagonals.
    cmp #24
    bne no_es_salto
    jsr armar_salto_heroe
    lda ruta_salto
    bne salto_arranco
    jmp otra_orden              ; it could not land there: skipped
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    bne no_es_fin
    jmp otra_orden              ; the `begin_jump` already consumed the pair
no_es_fin:
    cmp #28
    bcc otra_orden              ; 26 and 27 do not reach the hero
    cmp #30
    bcs no_es_velocidad
    jmp velocidad               ; 28 and 29: the speed, which stays
no_es_velocidad:
    cmp #32
    bcc frecuencia              ; 30 and 31: the move route's frequency
    cmp #34
    bne no_es_grafico_heroe
    jmp grafico_heroe           ; 34, the only one with an operand; it is far
no_es_grafico_heroe:
    cmp #35
    bne no_es_sonido_heroe
    jmp sonido_heroe            ; 35, with its operand; it is far
no_es_sonido_heroe:
    cmp #36
    bcc otra_orden              ; 32 and 33, the switches, do not get here: the
                                ; converter rejects them
    cmp #38
    bcc atravesar               ; 36 and 37
    cmp #40
    bcs otra_orden
    ; 38 stops the animation and 39 resumes it, so the subtraction goes the
    ; other way around.
    sec
    sbc #38
    eor #$01
    sta ruta_anim_para
    jmp otra_orden
atravesar:
    ; 36 turns it on and 37 off, so the low bit inverted is the value.
    and #$01
    eor #$01
    sta ruta_atraviesa
    jmp otra_orden
frecuencia:
    ; 30 raises the move route's frequency and 31 lowers it, capped at 8 and
    ; at 1: it is `increase/decrease_movement_frequence`. The frames standing
    ; still after each command come from it, so it is read from `ruta_frec`
    ; and not from anywhere else.
    ;
    ; With 1 the wait after a step is 256 frames and does not fit in
    ; `ruta_tras_paso`'s byte; the converter guarantees it is never reached,
    ; since it rejects the whole move route. Here it is capped at 1 anyway,
    ; like RM2k, in case that guard ever fails.
    and #$01
    bne frec_menos
    lda ruta_frec
    cmp #RUTA_FRECUENCIA
    bcs frec_listo
    inc ruta_frec
    bra frec_listo
frec_menos:
    lda ruta_frec
    cmp #2
    bcc frec_listo
    dec ruta_frec
frec_listo:
    jmp otra_orden
face:
    sec
    sbc #12
    sta hero_dir                ; face_*: with frequency 8 it is instant and the
    lda ruta_frec               ; next one follows; with another, it stands
    jsr tras_giro               ; still for the turn's frames
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_espera
    jmp listo

; `change_graphic` **on the hero**: 34 with its operand, the graphic's index in
; the map's table, same as on an event.
;
; It comes cheap because the two pose tables have the same shape: an entry of
; `npc_poses` is twelve three-byte pointers to the character's poses, and the
; twelve that the actor table gives the leader are written the same way. So it
; is enough to point `hero_poses` thirty-six bytes into `npc_poses` and
; `place_hero` still does not notice.
;
; Two things that are **not** done and that are what it would cost extra:
;
; * `hero_cgram` is turned off. The leader's fifteen colors are uploaded by
;   `aplicar_tinte` **into the row `hero_pal` says**, so leaving it set with
;   the new palette would write Talan's colors over the palette of the graphic
;   it changed to. While the change is in place, the hero is drawn with the new
;   graphic's palette, which already lives in CGRAM with the rest of the map's
;   sprites.
; * It does not survive a map change: `elegir_grafico_heroe` runs on load and
;   restores it. It is not laziness —the poses live in **the map's** sprite
;   bank, so the graphic from there does not exist here—.
;   The page of map 8's `EV0047`, which is the one that asked for all this,
;   changes to `Crown7` right before teleporting and back to `Future1` right
;   after, so in the game it is not noticeable.
grafico_heroe:
    lda #$FF
    sta hero_pose_vram          ; the pose in VRAM is no longer its own
    jsr orden_del_heroe         ; the operand, which is left consumed
    jsr hero_poses_de_grafico
    bcc heroe_sin_grafico
    jmp otra_orden
heroe_sin_grafico:
    ; A CharSet without a single opaque pixel —`nobodyhere`— or one that did
    ; not fit in the eight sprite palettes: the hero stops being drawn, which
    ; is what `place_hero` does with the pose pointer at zero and the same that
    ; happens to an event with its row hidden.
    stz hero_poses + 2
    stz hero_cgram + 2
    jmp otra_orden

; `play_sound_effect`: 35, with the sound effect's index after it, in two bytes.
; It is the same index as `OP_SOUND` and goes the same way, `sonido_tocar`, so
; it sounds the same as a `PlaySound`'s, with MSU-1 or without. It does not
; cost a frame: the next command runs in this one.
sonido_heroe:
    jsr orden_del_heroe         ; the low byte: leaves Y there and `ruta_ptr` set
    inc ruta_i                  ; and the cursor, past the high one
    rep #$20
.a16
    lda [ruta_ptr], y
    jsr sonido_tocar            ; with 16-bit A; returns with 8-bit A
.a8
    jmp otra_orden


mover:
    ; Diagonals do not get here: the converter rejects the page that gives one
    ; to the hero —see MOVE_EVENT in `eventos.traducir`— because the ROM only
    ; walks them on events, and none of the game's 26 move routes that use
    ; them is the hero's. Without that cut, the elimination below would send
    ; the hero to the left.
    sta hero_dir                ; move_* faces where it goes
    ; Going through walls, both sides say yes. It is
    ; `Game_Map::CheckOrMakeWayEx`'s `if (self.GetThrough()) return true;`,
    ; and it is turned on only around this step: `can_leave` and `can_enter`
    ; are also used by the pad walking, which does not look at it.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    lda hero_dir
    cmp #DIR_UP
    bne no_es_arriba
    jsr try_up
    jmp ver_si_arranco
no_es_arriba:
    cmp #DIR_RIGHT
    bne no_es_derecha
    jsr try_right
    jmp ver_si_arranco
no_es_derecha:
    cmp #DIR_DOWN
    bne no_es_abajo
    jsr try_down
    jmp ver_si_arranco
no_es_abajo:
    jsr try_left
ver_si_arranco:
    stz atravesando
    stz atravesando + 1
    lda step_left
    bne arranco                 ; blocked: skipped and the next one is tried
    jmp otra_orden
arranco:
    ; The step started, and it is noted that the move route started it:
    ; `hay_rutas` needs this to know the last step of a move route still
    ; counts.
    lda #1
    sta ruta_paso
listo:
    rts
velocidad:
    ; `increase_movement_speed` and `decrease_movement_speed`, capped at 6 and
    ; 1 like `MoveRouteSpeedUp`. On the hero the ROM used to ignore them; now
    ; they change the pace, and change it for good: RM2k restores the
    ; frequency when the move route ends and not the speed.
    cmp #29
    beq vel_menos
    jsr hero_vel_leer
    cmp #6
    bcs vel_guardar
    inc a
    bra vel_guardar
vel_menos:
    jsr hero_vel_leer
    cmp #2
    bcc vel_guardar
    dec a
vel_guardar:
    jsr hero_vel_escribir
    jmp otra_orden
.endproc

; Whether any forced move route is left unfinished, the hero's included.
; Returns A nonzero if there is. It is `Game_Map::IsAnyMovePending`, which is
; what `ProceedWithMovement` waits for.
;
; For the hero three things count, and the last one is not obvious: that it
; has commands left, that it is in the air, and that it has a step in progress
; **that the move route started**. The last one is needed because a move
; route's last step is still the move route even when no commands are left
; —without it the page would go on eight frames early—, and it has to be only
; the move route's because, once it is over, the player can start walking
; while another move route is still running, and a step from the pad is not a
; pending move route.
;
; The jump does not need that care and that is why it is looked at bare: the
; only one that sets `ruta_salto` to something other than zero is
; `armar_salto_heroe`, and only `paso_de_ruta` calls it, so a hero's jump is
; always from a move route. None comes from the pad. It was missing, and a
; `ProceedWithMovement` right after a jump let the page go with the hero still
; up in the air: there, `MoveRouteFinished` gets set inside `UpdateMovement`,
; that is, on landing.
.proc hay_rutas
.a8
.i16
    lda ruta_espera
    bne si                      ; the hero is in the middle of a `wait`
    lda ruta_salto
    bne si                      ; or is in the air
    lda ruta_i
    cmp ruta_n
    bcc si                      ; the hero has commands left
    lda ruta_paso
    beq de_eventos
    lda step_left
    bne si                      ; and the step it is taking is the move route's

de_eventos:
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    lda ruta_ev + 18, x
    and #$01
    bne siguiente               ; the page's own move route is not waited for
    lda ruta_ev + 7, x          ; a step in progress
    bne si
    lda ruta_ev + 9, x          ; or a wait
    bne si
    lda ruta_ev + 13, x         ; or a jump
    bne si
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc si                      ; it has commands left
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
    lda #0
    rts
si:
    lda #1
    rts
.endproc
