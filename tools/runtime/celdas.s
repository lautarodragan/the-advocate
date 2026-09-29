.segment "CODE"

; Whether the neighboring cell in the direction A carries exists, that is,
; whether it does not fall off the map. Returns A nonzero if it exists.
;
; It is split from `puede_celda` for a reason of reach and not of design:
; together, the `beq` of the first check ended up 130 bytes from the exit and
; the assembler balked. `sep`/`rep` do not touch Z or C, so the result of the
; sixteen-bit comparison survives the width change.
.proc celda_vecina_existe
.a8
.i16
    cmp #DIR_UP
    bne prueba_abajo
    rep #$20
.a16
    lda celda_y
    sep #$20
.a8
    beq no                      ; already on the top row
    bra si
prueba_abajo:
    cmp #DIR_DOWN
    bne prueba_izquierda
    rep #$20
.a16
    lda celda_y
    inc a
    cmp mapa_alto
    sep #$20
.a8
    bcs no
    bra si
prueba_izquierda:
    cmp #DIR_LEFT
    bne prueba_derecha
    rep #$20
.a16
    lda celda_x
    sep #$20
.a8
    beq no
    bra si
prueba_derecha:
    rep #$20
.a16
    lda celda_x
    inc a
    cmp mapa_ancho
    sep #$20
.a8
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether a step can be taken from (celda_x, celda_y) in the direction A
; carries. Returns A nonzero if it can.
;
; It is the same rule as the hero's —both faces are checked, the one being
; left and the one being entered— but from any cell, and without looking at
; who is standing where, which is also what the hero's forced move route
; does.
;
; A blocked movement is skipped. In the 26 event move routes this game
; compiles that happens **only once**, on map 117, and for that one time it
; has to be modeled: without it, that move route would last eight frames too
; long.
.proc puede_celda
.a8
.i16
    sta celda_dir
    stz celda_dir + 1
    jsr celda_vecina_existe
    bne :+
    jmp no                      ; too far for a short branch
:
    ; Walking through walls both faces say yes, but the cell has to exist: it
    ; is the `if (self.GetThrough()) return true;` of
    ; `Game_Map::CheckOrMakeWayEx`, which comes after the `IsValid`.
    lda atravesando
    beq con_colision
    lda #1
    rts
con_colision:

    ; The face being left.
    jsr ptr_de_celda
    rep #$20
.a16
    lda celda_x                 ; the cell being left, for whatever a tile
    sta pasa_x                  ; event imposes on it
    lda celda_y
    sta pasa_y
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_salir, x
    bne :+
    jmp no                      ; too far for a short branch
:

    ; And the target's face, which is the neighboring cell.
    lda celda_dir
    cmp #DIR_UP
    bne baja
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_menos
    bra entra
    ; The three labels that follow are reached with the accumulator **in
    ; eight bits**, even though the last thing the assembler read was an
    ; `.a16`: the `bra` above skips the width change. Without this `.a8` the
    ; `cmp` is emitted with a two-byte immediate, the CPU reads only one, and
    ; the second —a $00— runs as BRK.
baja:
.a8
    cmp #DIR_DOWN
    bne izquierda
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_mas
    bra entra
izquierda:
.a8
    cmp #DIR_LEFT
    bne derecha
    rep #$20
.a16
    lda #2
    jsr ptr_menos
    bra entra
derecha:
.a8
    rep #$20
.a16
    lda #2
    jsr ptr_mas
entra:
.a16
    lda celda_x                 ; and the cell being entered
    sta pasa_x
    lda celda_y
    sta pasa_y
    sep #$20
.a8
    ldx celda_dir
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_entrar, x
    bne :+
    jmp no
:
    ; And that nobody is standing on the neighboring cell. With `atravesando`
    ; this is never reached: it is the `GetThrough()` above.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_dest_x
    lda f:paso_dy, x
    jsr sumar_a_dest_y
    jsr celda_bloqueada
    bne no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether the diagonal step A carries, 4 to 7, can be taken from (celda_x,
; celda_y). Returns A nonzero if it can, and leaves the cell where it found
; it.
;
; RM2k **does not look at the diagonal cell**: it is `Game_Character::Move`,
; which tries the two L-shapes. First the vertical and then the horizontal
; from the elbow, and if that one fails, the horizontal and then the
; vertical; it is enough for one of the two to be entirely free. That is why
; the corner between two walls cannot be crossed diagonally, and it can be
; passed if there is a way around.
;
; Each leg is a call to `puede_celda`, that is, the same two faces and the
; same check of who is standing where as a straight step.
.proc puede_celda_diag
.a8
.i16
    sec
    sbc #4
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    sta diag_h
    rep #$20
.a16
    lda celda_x                 ; where it starts from, to go back between L and L
    sta diag_x
    lda celda_y
    sta diag_y
    sep #$20
.a8

    lda diag_v                  ; the vertical L: up and then sideways
    jsr puede_celda
    beq otra_ele
    lda diag_v
    jsr celda_al_codo
    lda diag_h
    jsr puede_celda
    bne si
otra_ele:
    jsr celda_al_origen         ; the horizontal L: sideways and then up
    lda diag_h
    jsr puede_celda
    beq no
    lda diag_h
    jsr celda_al_codo
    lda diag_v
    jsr puede_celda
    bne si
no:
    jsr celda_al_origen
    lda #0
    rts
si:
    jsr celda_al_origen
    lda #1
    rts
.endproc

; The cell becomes the origin plus the step of the direction A carries: the
; elbow of the L, where the second leg starts.
.proc celda_al_codo
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    lda f:paso_dx, x
    beq sin_x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_x
    ora #$FF00
mas_x:
    clc
    adc celda_x
    sta celda_x
    sep #$20
.a8
sin_x:
    lda f:paso_dy, x
    beq sin_y
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_y
    ora #$FF00
mas_y:
    clc
    adc celda_y
    sta celda_y
    sep #$20
.a8
sin_y:
    rts
.endproc

; And the cell goes back to being the origin.
.proc celda_al_origen
.a8
.i16
    rep #$20
.a16
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; Which way the event in slot X ends up facing after a step along the
; diagonal in `ruta_dir`. The new pose comes out in A.
;
; It is `Game_Character::UpdateFacing`, and the answer is not "toward the
; diagonal": the charset has four poses and none points at a corner. The one
; it already had is kept if it is one of the two components of the step, and
; otherwise it turns 180°.
;
; The first thing is where the turn starts from, and it is not just reading
; +8: twenty of the twenty-six move routes with diagonals in this game start
; **with** the diagonal, without turning first, so RUTA_EV_SIN_MIRAR is still
; there and the real pose is its page's, which lives in the NPC's row.
.proc encarar_diagonal
.a8
.i16
    lda ruta_ev + 8, x
    cmp #RUTA_EV_SIN_MIRAR
    bne con_pose
    phx
    lda ruta_ev + 0, x
    jsr npc_de_evento
    plx
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 10, y
    bra con_pose
sin_fila:
    lda #DIR_DOWN               ; no graphic: nobody's pose can be seen
con_pose:
    sta diag_mira
    lda ruta_dir
    sec
    sbc #4
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    plx
    cmp diag_mira
    beq queda
    lda diag_v
    cmp diag_mira
    beq queda
    lda diag_mira               ; neither of the two: 180°
    clc
    adc #2
    and #$03
    rts
queda:
    lda diag_mira
    rts
.endproc

; They add the signed byte A carries to dest_x / dest_y.
.proc sumar_a_dest_x
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
    adc dest_x
    sta dest_x
    sep #$20
.a8
    rts
.endproc

.proc sumar_a_dest_y
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
    adc dest_y
    sta dest_y
    sep #$20
.a8
    rts
.endproc

