; --- the maps that loop -------------------------------------------------------
;
; A map with `scroll_type` loops on that axis in RM2k: it is a torus, and the
; hero, the events and the camera go across its edge to the other side. It
; is easyrpg's `Game_Map::LoopHorizontal` and `LoopVertical`, and what the
; ports' maps do with it is in the book's research
; `research/2026-10-19-maps-that-wrap.md`.
;
; The record says which axes —`M_WRAP`, bit 0 across and bit 1 down—, and
; `wrap_find` copies it here when the map loads. Everything else is the
; same code as a map that does not loop, with hooks in bank 0 that come
; here with `jsl` and, if the map does not loop, go back having done
; nothing:
;
; * **The camera is a continuous view.** The window keeps cell (x, y) of the
;   map in slot (x mod 64, y mod 32), and a map's width is not a multiple of
;   64: if the camera jumped by a lap when the hero crosses the seam, every
;   slot would jump with it. So on a looping axis `camera_x` —what the window
;   and the scroll registers follow— moves by the change of the camera on the
;   map, folded the short way round, and is not that camera any more: it is
;   that plus `WRAP_O`, which changes by a lap at each seam. It is kept
;   between `VIEW_LOW` and `VIEW_HIGH` by jumping `VIEW_JUMP`, a multiple of
;   the window's 512 pixels, with `win_col` moved the same, so that it never
;   reaches zero or the top of sixteen bits.
; * **Every "position minus camera" folds into one lap** of the map centred
;   on the screen: `wrap_fold_x` and `wrap_fold_y`, after each `sbc screen_x`
;   and `sbc camera_y` that places a character. A map at least 20 cells by 15
;   —the converter checks it: see `wrap_axes`— leaves a character outside
;   the screen on one side and not on both, which is why RM2k's clones are
;   not needed.
; * **The strips read the map modulo its size**: `wrap_build_column` and
;   `wrap_build_row` take the place of `build_column` and `build_row` on a
;   map that loops, with the map's column of a window column computed from
;   the view, and the pointer computed again at the seam.
; * **Steps**: the neighbour across a looping edge exists, and the cell a
;   step reaches is folded into the map —its pointer, its passage, who
;   stands there and where the event or the hero ends up—. Distances to the
;   hero fold the short way round.
;
; What it does not do, because no map of the ports needs it: clones of a
; character on both sides of a seam, the panorama's rule on a looping axis,
; a jump across a seam —`can_fall` refuses a cell outside the map, as
; before—, the action key and an event's bump on the hero across a seam, and
; the order of the characters across a horizontal seam.
;
; **Only a cartridge with a map that loops assembles any of this**: without
; `wrap_maps` in the `.inc` this file is empty, and so are the hooks.

.ifdef wrap_maps
.pushseg
.segment "FAR3"
.a8
.i16

; The view's range and its jump: see above. The jump is a multiple of 512,
; the window's width in pixels and twice its height, so the slots of what is
; already drawn stay where they are.
VIEW_LOW  = 2048
VIEW_JUMP = 4096
VIEW_HIGH = VIEW_LOW + 2 * VIEW_JUMP
.assert VIEW_JUMP .mod (WINDOW_COLS * 8) = 0, error, "the view's jump has to keep the window's slots"
.assert VIEW_JUMP .mod (WINDOW_ROWS * 8) = 0, error, "the view's jump has to keep the window's slots"

; The state, in far RAM. The pairs go across and then down, two bytes apart:
; the camera works on both axes with X = 0 or 2, as `camera_x`, `win_col`,
; `map_cw` and their twins already are.
.pushseg
.segment "FARBSS"
WRAP_ON:    .res 2              ; bit 0 the map loops across, bit 1 down; the high byte 0
WRAP_W:     .res 4              ; its width and height, in pixels
WRAP_L:     .res 4              ; where a lap starts, left of and above the screen: negative
WRAP_O:     .res 4              ; the view minus the camera on the map
WRAP_C:     .res 4              ; the camera on the map, 0 to a lap minus one
WRAP_FRESH: .res 2              ; 1 from the map's load to its first camera
WRAP_T:     .res 2              ; scratch
WRAP_U:     .res 2
WRAP_MC:    .res 2              ; while a strip is built: the map's 8x8 column
WRAP_MB:    .res 2              ; and its 16x16 row
WRAP_NEED:  .res 2              ; 1 while the row being built has no pointer yet
WRAP_PX:    .res 2              ; the 16x16 cell `wrap_ptr` points at
WRAP_PY:    .res 2
.popseg

; A routine of bank 0 that ends in `rts`, called from here: its `rts` goes
; to `wrap_rtl`, in bank 0, and that `rtl` comes back here. A, X and Y and
; the widths in and out as the routine takes and leaves them.
.macro CALL0 routine
.local back
    phk
    per back - 1
    pea .loword(wrap_rtl - 1)
    jml routine + FAST
back:
.endmacro

; The other way round: a hook that comes here with `jsl` from the top of a
; bank 0 routine, and has done the whole of it, returns from that routine
; and not to it —its `jsl`'s three bytes off the stack, and the `rts` that
; routine would have reached, `wrap_rts` in bank 0—. That way the hook is
; the `jsl` alone, three bytes of bank 0 fewer than a `bcc` and an `rts`
; of its own, in the four that end that way. With A8, and A8 out: `value`,
; if given, is what A comes back with; otherwise A is lost. Keeps X and Y.
; Three `pla` and not `RTS0_16`'s `tcs`: with A8 they cost 12 cycles and
; 3 bytes, and the `tcs` 15 and 8 with its `rep` and `sep`.
.macro RTS0 value
    pla                         ; the `jsl`'s three bytes, off
    pla
    pla
.ifnblank value
    lda #value
.endif
    jml wrap_rts + FAST
.endmacro

; The same with A16 in and out, and A lost. With A16 the `tcs` is the cheap
; one: 9 cycles, where the pulls would need a `sep` and a `rep` for the odd
; byte, 15.
.macro RTS0_16
    tsc
    clc
    adc #3
    tcs                         ; the `jsl`'s three bytes, off
    jml wrap_rts + FAST
.endmacro

; --- the map's axes, when it loads --------------------------------------------

; From `enter_map`, with `map_ofs`, `map_width` and `map_height` set. Keeps
; nothing.
.proc wrap_find
.a8
.i16
    php
    rep #$20
.a16
    ldx map_ofs
    lda f:map_table + M_WRAP, x
    and #$0003
    sta f:WRAP_ON
    lda #1
    sta f:WRAP_FRESH
    lda map_width
    ldx #0
    jsr lap
    lda map_height
    ldx #2
    jsr lap
    plp
    rtl

; A, a size in cells, to `WRAP_W` and `WRAP_L` of axis X: a lap starts half
; of what it measures past the screen before the screen does.
lap:
    asl a
    asl a
    asl a
    asl a
    sta f:WRAP_W, x
    sec
    sbc f:screen_size, x
    lsr a
    eor #$FFFF
    inc a
    sta f:WRAP_L, x
    rts
.endproc

screen_size: .word 256, 224
half_screen: .word 128, 112
axis_bit:    .word 1, 2

; --- the camera ---------------------------------------------------------------

; `follow_camera` after `pan_follow`: on a map that loops it does the whole
; of it here and returns from `follow_camera`; on any other it comes back
; having touched nothing. A8 in and out.
.proc wrap_camera
.a8
.i16
    lda f:WRAP_ON
    bne loops
    rtl
loops:
    rep #$20
.a16
    ldx #0
axis:
    ; Where the camera wants to be on the map: what `follow_camera` computes.
    lda f:PAN_BASE, x
    clc
    adc #8
    sec
    sbc f:half_screen, x
    clc
    adc pan_px, x
    sta f:WRAP_T
    lda f:WRAP_ON
    and f:axis_bit, x
    bne this_loops
    ; This axis does not loop: kept inside the map, as `follow_camera` does.
    lda f:WRAP_T
    bpl :+
    lda #0
:   cmp cam_max_x, x
    bcc :+
    lda cam_max_x, x
:   sta camera_x, x
    bra next
this_loops:
    jsr view_axis
next:
    inx
    inx
    cpx #4
    bcc axis
    lda #0
    sta f:WRAP_FRESH
    ; What `follow_camera` leaves besides the camera.
    lda camera_y
    dec a
    sta scroll_y
    lda camera_x
    clc
    adc shake_pos
    sta screen_x
    sep #$20
.a8
    RTS0
.endproc

; Axis X of the view, with `WRAP_T` where the camera wants to be on the map.
; Keeps X. A16.
.proc view_axis
.a16
.i16
    lda f:WRAP_T
    jsr into_lap                ; the camera on the map
    sta f:WRAP_T
    lda f:WRAP_FRESH
    beq follows
    ; Just loaded: the view is the camera plus a jump, and the window is about
    ; to be filled around it.
    lda f:WRAP_T
    clc
    adc #VIEW_JUMP
    sta camera_x, x
    bra range
follows:
    ; The view moves as much as the camera did, the short way round: across
    ; the seam that is a few pixels and not a lap.
    lda f:WRAP_T
    sec
    sbc f:WRAP_C, x
    jsr short_way
    clc
    adc camera_x, x
    sta camera_x, x
range:
    lda camera_x, x
    cmp #VIEW_LOW
    bcs not_low
    adc #VIEW_JUMP
    sta camera_x, x
    lda win_col, x
    clc
    adc #VIEW_JUMP / 8
    sta win_col, x
    bra range
not_low:
    cmp #VIEW_HIGH
    bcc in_range
    sbc #VIEW_JUMP
    sta camera_x, x
    lda win_col, x
    sec
    sbc #VIEW_JUMP / 8
    sta win_col, x
    bra range
in_range:
    lda f:WRAP_T
    sta f:WRAP_C, x
    lda camera_x, x
    sec
    sbc f:WRAP_T
    sta f:WRAP_O, x
    rts
.endproc

; A, a position in pixels on axis X, into the lap: 0 to its size minus one.
; It may be any number of laps away. Keeps X and Y. A16.
.proc into_lap
.a16
.i16
low:
    cmp #0
    bpl high
    clc
    adc f:WRAP_W, x
    bra low
high:
    cmp f:WRAP_W, x
    bcc ready
    sbc f:WRAP_W, x
    bra high
ready:
    rts
.endproc

; A, a difference in pixels on axis X of less than a lap either way, the
; short way round: from minus half a lap to half a lap. Keeps X and Y. A16.
.proc short_way
.a16
.i16
    sta f:WRAP_U
    lda f:WRAP_W, x
    lsr a
    clc
    adc f:WRAP_U                ; plus half a lap: negative is too far back
    bmi back
    sec
    sbc f:WRAP_W, x             ; and past a lap, too far ahead
    bpl ahead
    lda f:WRAP_U
    rts
back:
    lda f:WRAP_U
    clc
    adc f:WRAP_W, x
    rts
ahead:
    lda f:WRAP_U
    sec
    sbc f:WRAP_W, x
    rts
.endproc

; --- what is drawn over the map -----------------------------------------------

; A16: A is a position on the map minus `screen_x`, or `camera_x`; leaves it
; in the lap that starts at `WRAP_L`, which holds the screen and a character
; on each side of it. On a map that does not loop across, as it came. Keeps
; X and Y.
.proc wrap_fold_x
.a16
.i16
    phx
    ldx #0
    bra wrap_fold_axis
.endproc

; The same down, from `camera_y`.
.proc wrap_fold_y
.a16
.i16
    phx
    ldx #2
    ; falls through
.endproc

.proc wrap_fold_axis
.a16
.i16
    pha
    lda f:WRAP_ON
    and f:axis_bit, x
    beq flat
    pla
    clc
    adc f:WRAP_O, x             ; minus the camera on the map, not the view
    sec
    sbc f:WRAP_L, x
    bpl not_back
    clc
    adc f:WRAP_W, x
    bra in_lap
not_back:
    cmp f:WRAP_W, x
    bcc in_lap
    sbc f:WRAP_W, x
in_lap:
    clc
    adc f:WRAP_L, x
    plx
    ora #0                      ; N and Z from A, as the subtraction left them
    rtl
flat:
    pla
    plx
    ora #0                      ; N and Z from A, as the subtraction left them
    rtl
.endproc

; `obj_x` and `obj_y`, the hero's drawing, both into the lap: one call
; instead of two, because two pushed a branch of `place_hero` out of reach.
; Where the lap starts moves by the sprite's offset, which a lap with a
; character's room on each side does not notice. A16; keeps X and Y.
.proc wrap_fold_obj
.a16
.i16
    lda obj_x
    jsl wrap_fold_x
    sta obj_x
    lda obj_y
    jsl wrap_fold_y
    sta obj_y
    rtl
.endproc

; A16: A is a difference of cells on the axis X says, 0 across and 2 down;
; leaves it the short way round on a map that loops on that axis, from minus
; half the map to half of it, which is easyrpg's
; `GetDistanceXfromCharacter`. Keeps X and Y.
.proc wrap_fold_cx
.a16
.i16
    phx
    ldx #0
    bra wrap_fold_cells
.endproc

.proc wrap_fold_cy
.a16
.i16
    phx
    ldx #2
    ; falls through
.endproc

.proc wrap_fold_cells
.a16
.i16
    pha
    lda f:WRAP_ON
    and f:axis_bit, x
    beq flat
    lda map_width, x
    sta f:WRAP_U
    lsr a
    clc
    adc 1, s                    ; plus half the map: negative is too far back
    bmi back
    sec
    sbc f:WRAP_U
    bpl ahead
flat:
    pla
    plx
    ora #0                      ; N and Z from A, as the subtraction left them
    rtl
back:
    pla
    clc
    adc f:WRAP_U
    plx
    ora #0                      ; N and Z from A, as the subtraction left them
    rtl
ahead:
    pla
    sec
    sbc f:WRAP_U
    plx
    ora #0                      ; N and Z from A, as the subtraction left them
    rtl
.endproc
.assert map_height = map_width + 2, error, "`wrap_fold_cells` reads the map's size by axis"
.assert camera_y = camera_x + 2, error, "the camera's axes go by X"
.assert win_row = win_col + 2, error, "the window's axes go by X"
.assert map_ch = map_cw + 2, error, "the window's axes go by X"
.assert cam_max_y = cam_max_x + 2, error, "the camera's axes go by X"
.assert pan_py = pan_px + 2, error, "the camera's axes go by X"

; `pic_on_map`, which keeps RM2k's display inside the map as RM2k does: on
; an axis that loops RM2k does not, and the display is the camera's,
; however far the view is. A16, A the display it kept; keeps X and Y. The
; drawing subtracts `screen_x` from it, the view too, so a picture stays on
; the screen.
.proc wrap_pic_x
.a16
.i16
    pha
    lda f:WRAP_ON
    and #$0001
    beq kept
    pla
    lda camera_x
    sec
    sbc #PIC_RM_LEFT
    rtl
kept:
    pla
    rtl
.endproc

.proc wrap_pic_y
.a16
.i16
    pha
    lda f:WRAP_ON
    and #$0002
    beq kept
    pla
    lda camera_y
    sec
    sbc #PIC_RM_TOP
    rtl
kept:
    pla
    rtl
.endproc

; --- steps --------------------------------------------------------------------

; A16: A, a cell on axis X, into the map if the map loops on it. Keeps X
; and Y.
.proc into_map
.a16
.i16
    pha
    lda f:WRAP_ON
    and f:axis_bit, x
    beq flat
    pla
low:
    cmp #0
    bpl high
    clc
    adc map_width, x
    bra low
high:
    cmp map_width, x
    bcc ready
    sbc map_width, x
    bra high
flat:
    pla
ready:
    rts
.endproc

; `cell_neighbor_exists`, before it looks: A8 is the direction, and on an
; axis the map loops on the neighbour is always there, which returns 1 from
; it. Otherwise it comes back with A as it came.
.proc wrap_neighbor
.a8
.i16
    pha
    and #$01                    ; 1 and 3, right and left, are across
    inc a                       ; 2 across, 1 down: the axis bit, backwards
    eor #$03                    ; 1 across, 2 down
    and f:WRAP_ON
    beq no
    pla
    RTS0 1
no:
    pla
    rtl
.endproc
.assert DIR_UP = 0 && DIR_RIGHT = 1 && DIR_DOWN = 2 && DIR_LEFT = 3, error, "`wrap_neighbor` takes the axis from the direction's low bit"

; `cell_allowed`, once it has the cell being entered in `pass_x`/`pass_y`:
; folded into the map, and the pointer, which went one cell over, pointed
; at it again if it left the map. A8. Keeps nothing but A's width.
.proc wrap_pass
.a8
.i16
    lda f:WRAP_ON
    bne loops
    rtl
loops:
    rep #$20
.a16
    ldx #0
    lda pass_x
    jsr into_map
    sta f:WRAP_PX
    eor pass_x                  ; zero if it stayed
    sta f:WRAP_U
    lda f:WRAP_PX
    sta pass_x
    ldx #2
    lda pass_y
    jsr into_map
    sta f:WRAP_PY
    eor pass_y
    ora f:WRAP_U
    tay                         ; zero if neither moved
    lda f:WRAP_PY
    sta pass_y
    tya
    beq same
    jsr wrap_ptr
same:
    sep #$20
.a8
    rtl
.endproc

; `add_a_to_dest_y`, after it adds: `dest_x`/`dest_y` folded into the map.
; A8. Keeps X and Y.
.proc wrap_dest
.a8
.i16
    lda f:WRAP_ON
    beq ready
    rep #$20
.a16
    phx
    ldx #0
    lda dest_x
    jsr into_map
    sta dest_x
    ldx #2
    lda dest_y
    jsr into_map
    sta dest_y
    plx
    sep #$20
.a8
ready:
    rtl
.endproc

; `cell_to_elbow`, after it moves: `cell_x`/`cell_y` folded into the map, so
; that the L of a diagonal can turn across a seam. A8. Keeps X and Y.
.proc wrap_cell
.a8
.i16
    lda f:WRAP_ON
    beq ready
    rep #$20
.a16
    phx
    ldx #0
    lda cell_x
    jsr into_map
    sta cell_x
    ldx #2
    lda cell_y
    jsr into_map
    sta cell_y
    plx
    sep #$20
.a8
ready:
    rtl
.endproc

; `try_diagonal`, with the hero's new cell in `tile_x`/`tile_y` and
; `cell_x`/`cell_y`: both folded into the map. A8. Keeps X and Y.
.proc wrap_tile
.a8
.i16
    lda f:WRAP_ON
    beq ready
    rep #$20
.a16
    phx
    ldx #0
    lda tile_x
    jsr into_map
    sta tile_x
    sta cell_x
    ldx #2
    lda tile_y
    jsr into_map
    sta tile_y
    sta cell_y
    plx
    sep #$20
.a8
ready:
    rtl
.endproc

; `move_event_cell`, after it moves the event whose position is at Y in
; `ev_pos_buf`: folded into the map. A8. Keeps X and Y.
.proc wrap_ev_pos
.a8
.i16
    lda f:WRAP_ON
    beq ready
    rep #$20
.a16
    phx
    ldx #0
    lda ev_pos_buf + 0, y
    jsr into_map
    sta ev_pos_buf + 0, y
    ldx #2
    lda ev_pos_buf + 2, y
    jsr into_map
    sta ev_pos_buf + 2, y
    plx
    sep #$20
.a8
ready:
    rtl
.endproc

; The hero's straight step toward A8, from `try_toward`. If it crosses a seam
; of the map, it is taken here and the carry comes back set: the step goes
; through `cell_allowed`, as his diagonal already does in `try_diagonal` —the
; two faces, a tile event's passage and who is standing there—, because his
; own `try_*` walk the grid by one cell and stop at the edge. Any other step
; comes back with the carry clear and A as it was, for his `try_*`.
.proc wrap_hero_step
.a8
.i16
    pha
    lda f:WRAP_ON
    beq no
    rep #$20
.a16
    lda 1, s
    and #$0003
    asl a
    tax
    lda f:seam_at, x
    sta f:WRAP_U
    lda f:seam_axis, x
    tax                         ; 0 across, 2 down
    lda f:WRAP_ON
    and f:axis_bit, x
    beq no16                    ; this axis does not loop
    lda f:WRAP_U
    bne at_end
    lda tile_x, x               ; up and left: the seam is at 0
    beq seam
    bra no16
at_end:
    lda map_width, x            ; down and right: at the last
    dec a
    cmp tile_x, x
    beq seam
no16:
    sep #$20
.a8
no:
    pla
    clc
    rtl
.a16
seam:
    lda tile_x
    sta cell_x
    lda tile_y
    sta cell_y
    sep #$20
.a8
    lda #HERO_WALKER
    sta walker
    lda #HERO_LAYER_INDEX
    sta walker_layer
    lda 1, s
    CALL0 cell_allowed
    cmp #0
    bne allowed
    jmp blocked
allowed:
    rep #$20
.a16
    lda 1, s
    and #$0003
    tax
    sep #$20
.a8
    lda f:step_dx_table, x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc :+
    ora #$FF00
:   sta step_dx
    clc
    adc tile_x
    phx
    ldx #0
    jsr into_map
    plx
    sta tile_x
    sta cell_x
    sep #$20
.a8
    lda f:step_dy_table, x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc :+
    ora #$FF00
:   sta step_dy
    clc
    adc tile_y
    ldx #2
    jsr into_map
    sta tile_y
    sta cell_y
    sep #$20
.a8
    CALL0 cell_ptr              ; the destination, which `begin_step` gives the hero
    CALL0 begin_step
blocked:
.a8
    pla
    sec
    rtl
.endproc
.assert tile_y = tile_x + 2, error, "`wrap_hero_step` reads the hero's cell by axis"

; By direction, up, right, down and left: the axis it crosses —0 across, 2
; down— and whether its seam is at the map's end.
seam_axis: .word 2, 0, 2, 0
seam_at:   .word 0, 1, 1, 0

; --- the pointer into the grid -------------------------------------------------

; `cells_ptr` to cell (`WRAP_PX`, `WRAP_PY`) of the grid: `cell_ptr`, which
; reads `cell_x`/`cell_y`, with the cell of its own. A16 in and out. Keeps X;
; Y not.
.proc wrap_ptr
.a16
.i16
    sep #$20
.a8
    lda f:WRAP_PY
    sta WRMPYA
    lda strip_step_col
    sta WRMPYB                  ; eight cycles: what follows pays for them
    rep #$20
.a16
    lda f:WRAP_PX
    bit cell_mask               ; N, its bit 15: set only in a wide grid
    bpl narrow
    asl a
narrow:
    sta cells_ptr
    lda RDMPYL                  ; y low times stride low
    clc
    adc cells_ptr
    sta cells_ptr
    sep #$20
.a8
    lda strip_step_col + 1
    beq no_step_height
    sta WRMPYB                  ; y low times stride high: WRMPYA is still y
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc cells_ptr + 1
    sta cells_ptr + 1
no_step_height:
    lda f:WRAP_PY + 1
    beq no_y_high
    sta WRMPYA
    lda strip_step_col
    sta WRMPYB                  ; y high times stride low
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc cells_ptr + 1
    sta cells_ptr + 1
no_y_high:
    lda cells_ptr + 1
    bmi high
    ora #>$8000
    sta cells_ptr + 1
    lda #^GRID
    bra bank
high:
    lda #^GRID_HIGH
bank:
    sta cells_ptr + 2
    rep #$20
.a16
    rts
.endproc

; `ptr_more`, here: A more bytes into the grid, past the end of a bank's
; upper half into the next one's. A16. Keeps X and Y.
.proc ptr_more_far
.a16
.i16
    clc
    adc cells_ptr
    sta cells_ptr
    bcc ready
    clc
    adc #$8000
    sta cells_ptr
    sep #$20
.a8
    lda cells_ptr + 2
    inc a
    sta cells_ptr + 2
    rep #$20
.a16
ready:
    rts
.endproc

; `cell_replaced`, here: the block a `TileSubstitution` gave the one in A.
; Uses Y; keeps X. A16.
.proc replaced_far
.a16
.i16
    ldy sub_n
    beq ready
seek:
    dey
    dey
    cmp sub_key, y
    beq found
    cpy #$0000
    bne seek
    rts
found:
    lda sub_value, y
ready:
    rts
.endproc

; Axis X's window index A —a column, or a row— as the map's 8x8 column or
; row: minus the view's offset, in cells, and into the map if it loops.
; On an axis that does not loop the view is the camera and it comes back as
; it was. A16. Keeps X and Y.
.proc map_index
.a16
.i16
    sta f:WRAP_T
    lda f:WRAP_ON
    and f:axis_bit, x
    beq flat
    lda f:WRAP_O, x
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a                       ; in 8x8 cells: it is a multiple of 16 pixels
    eor #$FFFF
    sec
    adc f:WRAP_T
low:
    cmp #0
    bpl high
    clc
    adc map_cw, x
    bra low
high:
    cmp map_cw, x
    bcc ready
    sbc map_cw, x
    bra high
flat:
    lda f:WRAP_T
ready:
    rts
.endproc

; --- the strips ---------------------------------------------------------------

; `build_column`, on a map that loops: column X of the window —the view's,
; in 8x8 cells— built into `strip_col`, and `col_addr` where it goes, and
; returns from `build_column`. On a map that does not loop it comes back
; having done nothing. A16 in and out.
.proc wrap_build_column
.a16
.i16
    lda f:WRAP_ON
    bne loops
    rtl
loops:
    stz col_addr
    txa
    sta f:WRAP_U                ; the window's column
    ldx #0
    jsr map_index
    cmp map_cw
    bcc inside
    jmp built                   ; past an edge that does not loop: nothing
inside:
    sta f:WRAP_MC
    ; Where it lands in VRAM: `build_column`'s, from the window's column.
    lda f:WRAP_U
    and #(WINDOW_COLS - 1)
    sta temp
    and #$001F
    clc
    adc f:FAR_VRAM_MAP
    sta col_addr
    lda temp
    and #$0020
    beq left
    lda col_addr
    clc
    adc #1024
    sta col_addr
left:
    lda f:WRAP_MC
    and #$0001
    asl a                       ; 0 the left half, 2 the right
    sta strip_ofs
    lda f:WRAP_MC
    lsr a
    sta f:WRAP_PX
    ; The window's top row, on the map.
    lda win_row
    ldx #2
    jsr map_index
    pha
    and #$0001
    beq from_up
    lda strip_ofs
    ora #$0004                  ; starts at the block's bottom half
    sta strip_ofs
from_up:
    pla
    lsr a
    sta f:WRAP_MB
    sta f:WRAP_PY
    jsr wrap_ptr
    ; How many rows: the whole window, or what is left of a map that does
    ; not loop down.
    lda #WINDOW_ROWS
    sta strip_left
    lda f:WRAP_ON
    and #$0002
    bne all
    lda map_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcs all
    sta strip_left
all:
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax                         ; the slot, in bytes
row:
    lda [cells_ptr]
    and cell_mask
    jsr replaced_far
    asl a
    asl a
    asl a
    asl a                       ; its record is 16 bytes
    clc
    adc strip_ofs
    tay
    lda [blocks_ptr], y
    sta strip_col, x
    lda [blocks8_ptr], y
    sta strip_col2, x
    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)  ; the window wraps
    tax
    lda strip_ofs
    eor #$0004                  ; the other half of the block
    sta strip_ofs
    and #$0004
    bne same
    lda f:WRAP_MB               ; to the next block row
    inc a
    cmp map_height
    bcc no_seam
    lda #0                      ; the seam: back to the top
    sta f:WRAP_MB
    sta f:WRAP_PY
    jsr wrap_ptr
    bra same
no_seam:
    sta f:WRAP_MB
    lda strip_step_col
    jsr ptr_more_far
same:
    dec strip_left
    beq built
    jmp row
built:
    RTS0_16
.endproc

; `build_row`, on a map that loops: row X of the window into `strip_row`,
; and `row_addr` where it goes, over the same columns `build_row` builds,
; [win_col - MARGIN_COLS, win_col + 60). Across a seam it goes on from the
; first column; on a map that does not loop across, what is outside it goes
; empty, as there; and returns from `build_row`. On a map that does not
; loop it comes back having done nothing. A16 in and out.
.proc wrap_build_row
.a16
.i16
    lda f:WRAP_ON
    bne loops
    rtl
loops:
    stz row_addr
    txa
    sta f:WRAP_U                ; the window's row
    ldx #2
    jsr map_index
    cmp map_ch
    bcc inside
    jmp built                   ; past an edge that does not loop: nothing
inside:
    pha
    and #$0001
    asl a
    asl a                       ; 0 the block's top half, 4 the bottom
    sta strip_ofs
    pla
    lsr a
    sta f:WRAP_MB
    lda f:WRAP_U
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a                       ; each screen row is 32 words
    clc
    adc f:FAR_VRAM_MAP
    sta row_addr
    ; The first column, on the map: it may be outside it on a map that does
    ; not loop across.
    lda win_col
    sec
    sbc #MARGIN_COLS
    pha
    ldx #0
    jsr map_index
    sta f:WRAP_MC
    pla
    and #(WINDOW_COLS - 1)
    asl a
    tax                         ; its slot, in bytes
    lda #WINDOW_COLS
    sta strip_total
    lda #1
    sta f:WRAP_NEED
column:
    lda f:WRAP_ON
    lsr a
    bcs with_map                ; looping across, every column is the map's
    lda f:WRAP_MC
    cmp map_cw
    bcs empty                   ; negative, or past the right edge
with_map:
    lda f:WRAP_NEED
    beq pointed
    lda #0
    sta f:WRAP_NEED
    lda strip_ofs
    and #$0004
    sta strip_ofs
    lda f:WRAP_MC
    and #$0001
    asl a                       ; 0 the left half, 2 the right
    ora strip_ofs
    sta strip_ofs
    lda f:WRAP_MC
    lsr a
    sta f:WRAP_PX
    lda f:WRAP_MB
    sta f:WRAP_PY
    phx
    jsr wrap_ptr
    plx
pointed:
    lda [cells_ptr]
    and cell_mask
    jsr replaced_far
    asl a
    asl a
    asl a
    asl a
    clc
    adc strip_ofs
    tay
    lda [blocks_ptr], y
    sta strip_row, x
    lda [blocks8_ptr], y
    sta strip_row2, x
    lda strip_ofs
    eor #$0002                  ; the other half of the block, across
    sta strip_ofs
    and #$0002
    bne next
    lda cell_bytes
    jsr ptr_more_far            ; to the next block over
    bra next
empty:
    stz strip_row, x
    stz strip_row2, x
next:
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    lda f:WRAP_MC
    inc a
    cmp map_cw
    bne no_seam
    lda f:WRAP_ON
    lsr a                       ; the carry: it loops across
    lda map_cw                  ; `lda` does not touch it
    bcc no_seam
    lda #1                      ; the seam: back to the first column, with a
    sta f:WRAP_NEED             ; pointer of its own
    lda #0
no_seam:
    sta f:WRAP_MC
    dec strip_total
    beq built
    jmp column
built:
    RTS0_16
.endproc

.popseg
.endif
