.segment "CODE"

; Whether the neighboring cell in the direction A carries exists, that is,
; whether it does not fall off the map. Returns A nonzero if it exists.
;
; It is split from `cell_allowed` for a reason of reach and not of design:
; together, the `beq` of the first check ended up 130 bytes from the exit and
; the assembler balked. `sep`/`rep` do not touch Z or C, so the result of the
; sixteen-bit comparison survives the width change.
.proc cell_neighbor_exists
.a8
.i16
    cmp #DIR_UP
    bne test_down
    rep #$20
.a16
    lda cell_y
    sep #$20
.a8
    beq no                      ; already on the top row
    bra if
test_down:
    cmp #DIR_DOWN
    bne test_left
    rep #$20
.a16
    lda cell_y
    inc a
    cmp map_height
    sep #$20
.a8
    bcs no
    bra if
test_left:
    cmp #DIR_LEFT
    bne test_right
    rep #$20
.a16
    lda cell_x
    sep #$20
.a8
    beq no
    bra if
test_right:
    rep #$20
.a16
    lda cell_x
    inc a
    cmp map_width
    sep #$20
.a8
    bcs no
if:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether a step can be taken from (cell_x, cell_y) in the direction A
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
.proc cell_allowed
.a8
.i16
    sta cell_dir
    stz cell_dir + 1
    jsr cell_neighbor_exists
    bne :+
    jmp no                      ; too far for a short branch
:
    ; Walking through walls both faces say yes, but the cell has to exist: it
    ; is the `if (self.GetThrough()) return true;` of
    ; `Game_Map::CheckOrMakeWayEx`, which comes after the `IsValid`.
    lda crossing
    beq with_collision
    lda #1
    rts
with_collision:

    ; The face being left.
    jsr cell_ptr
    rep #$20
.a16
    lda cell_x                 ; the cell being left, for whatever a tile
    sta pass_x                  ; event imposes on it
    lda cell_y
    sta pass_y
    jsr pass_of_ptr
    jsr pass_with_event
    sep #$20
.a8
    ldx cell_dir
    and f:pass_exit, x
    bne :+
    jmp no                      ; too far for a short branch
:

    ; And the target's face, which is the neighboring cell.
    lda cell_dir
    cmp #DIR_UP
    bne low
    rep #$20
.a16
    lda strip_step_col
    jsr ptr_minus
    bra enters
    ; The three labels that follow are reached with the accumulator **in
    ; eight bits**, even though the last thing the assembler read was an
    ; `.a16`: the `bra` above skips the width change. Without this `.a8` the
    ; `cmp` is emitted with a two-byte immediate, the CPU reads only one, and
    ; the second —a $00— runs as BRK.
low:
.a8
    cmp #DIR_DOWN
    bne left
    rep #$20
.a16
    lda strip_step_col
    jsr ptr_more
    bra enters
left:
.a8
    cmp #DIR_LEFT
    bne right
    rep #$20
.a16
    lda #2
    jsr ptr_minus
    bra enters
right:
.a8
    rep #$20
.a16
    lda #2
    jsr ptr_more
enters:
.a16
    lda cell_x                 ; and the cell being entered
    sta pass_x
    lda cell_y
    sta pass_y
    sep #$20
.a8
    ldx cell_dir
    lda f:step_dx_table, x
    jsr add_a_to_pass_x
    lda f:step_dy_table, x
    jsr add_a_to_pass_y
    rep #$20
.a16
    jsr pass_of_ptr
    jsr pass_with_event
    sep #$20
.a8
    ldx cell_dir
    and f:pass_enter, x
    bne :+
    jmp no
:
    ; And that nobody is standing on the neighboring cell. With `crossing`
    ; this is never reached: it is the `GetThrough()` above.
    rep #$20
.a16
    lda cell_x
    sta dest_x
    lda cell_y
    sta dest_y
    sep #$20
.a8
    lda f:step_dx_table, x
    jsr add_a_to_dest_x
    lda f:step_dy_table, x
    jsr add_a_to_dest_y
    jsr cell_blocked
    bne no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Whether the diagonal step A carries, 4 to 7, can be taken from (cell_x,
; cell_y). Returns A nonzero if it can, and leaves the cell where it found
; it.
;
; RM2k **does not look at the diagonal cell**: it is `Game_Character::Move`,
; which tries the two L-shapes. First the vertical and then the horizontal
; from the elbow, and if that one fails, the horizontal and then the
; vertical; it is enough for one of the two to be entirely free. That is why
; the corner between two walls cannot be crossed diagonally, and it can be
; passed if there is a way around.
;
; Each leg is a call to `cell_allowed`, that is, the same two faces and the
; same check of who is standing where as a straight step.
.proc cell_allowed_diag
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
    lda cell_x                 ; where it starts from, to go back between L and L
    sta diag_x
    lda cell_y
    sta diag_y
    sep #$20
.a8

    lda diag_v                  ; the vertical L: up and then sideways
    jsr cell_allowed
    beq other_lshape
    lda diag_v
    jsr cell_to_elbow
    lda diag_h
    jsr cell_allowed
    bne if
other_lshape:
    jsr cell_to_origin         ; the horizontal L: sideways and then up
    lda diag_h
    jsr cell_allowed
    beq no
    lda diag_h
    jsr cell_to_elbow
    lda diag_v
    jsr cell_allowed
    bne if
no:
    jsr cell_to_origin
    lda #0
    rts
if:
    jsr cell_to_origin
    lda #1
    rts
.endproc

; The cell becomes the origin plus the step of the direction A carries: the
; elbow of the L, where the second leg starts.
.proc cell_to_elbow
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    lda diag_x
    sta cell_x
    lda diag_y
    sta cell_y
    sep #$20
.a8
    lda f:step_dx_table, x
    beq no_x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc more_x
    ora #$FF00
more_x:
    clc
    adc cell_x
    sta cell_x
    sep #$20
.a8
no_x:
    lda f:step_dy_table, x
    beq no_y
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc more_y
    ora #$FF00
more_y:
    clc
    adc cell_y
    sta cell_y
    sep #$20
.a8
no_y:
    rts
.endproc

; And the cell goes back to being the origin.
.proc cell_to_origin
.a8
.i16
    rep #$20
.a16
    lda diag_x
    sta cell_x
    lda diag_y
    sta cell_y
    sep #$20
.a8
    rts
.endproc

; Which way the event in slot X ends up facing after a step along the
; diagonal in `route_dir`. The new pose comes out in A.
;
; It is `Game_Character::UpdateFacing`, and the answer is not "toward the
; diagonal": the charset has four poses and none points at a corner. The one
; it already had is kept if it is one of the two components of the step, and
; otherwise it turns 180°.
;
; The first thing is where the turn starts from, and it is not just reading
; +8: twenty of the twenty-six move routes with diagonals in this game start
; **with** the diagonal, without turning first, so ROUTE_EV_NO_FACE is still
; there and the real pose is its page's, which lives in the NPC's row.
.proc face_diagonal
.a8
.i16
    lda route_ev + 8, x
    cmp #ROUTE_EV_NO_FACE
    bne with_pose
    phx
    lda route_ev + 0, x
    jsr event_npc
    plx
    cpy #$FFFF
    beq no_row
    lda npc_buf + 10, y
    bra with_pose
no_row:
    lda #DIR_DOWN               ; no graphic: nobody's pose can be seen
with_pose:
    sta diag_facing
    lda route_dir
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
    cmp diag_facing
    beq remains
    lda diag_v
    cmp diag_facing
    beq remains
    lda diag_facing               ; neither of the two: 180°
    clc
    adc #2
    and #$03
    rts
remains:
    lda diag_facing
    rts
.endproc

; They add the signed byte A carries to dest_x / dest_y.
.proc add_a_to_dest_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positive
    ora #$FF00
positive:
    clc
    adc dest_x
    sta dest_x
    sep #$20
.a8
    rts
.endproc

.proc add_a_to_dest_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positive
    ora #$FF00
positive:
    clc
    adc dest_y
    sta dest_y
    sep #$20
.a8
    rts
.endproc

