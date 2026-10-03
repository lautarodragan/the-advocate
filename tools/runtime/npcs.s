.segment "CODE"

; Uploads pose A of the NPC in row Y, unless it is the one already in VRAM.
;
; It came out of `refresh_npc`, which was the only one that needed it, the
; day there was a second one: `animate_still`. `npc_row` has to hold the
; same row as Y, which is how it came in.
.proc upload_npc_pose
.a8
.i16
    ; The row's tile is fixed —it is its slot— and what changes are the slot's
    ; tiles, which are queued here and go up in the next vblank with the OAM.
    cmp npc_buf + 12, y
    bne changes
    rts
changes:
    sta npc_buf + 12, y
    sta temp                    ; the pose

    ; The pointer to the pose, from `npc_poses`: twelve three-byte pointers per
    ; animated character, that is (k * 12 + pose) * 3.
    lda npc_buf + 9, y
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
    adc temp + 2                ; thirty-six per character
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

    ; The destination: its slot, which is the row's tile times sixteen words
    ; from where the sprite bank starts. In a map with a cache of slots, the
    ; one it got, if it has one: if not, the pose waits in +12 for when it
    ; comes into view. See cache_slots.s.
    ldy npc_row
    lda f:SHARE_N
    bpl fixed_slot
    jsl f:cache_dest + FAST
    bcc queue
    rts
fixed_slot:
    lda npc_buf + 7, y
    and #$01                    ; bit 8 of the tile lives in the attributes
    xba
    lda npc_buf + 6, y
    rep #$20
.a16
    asl a
    asl a
    asl a
    asl a                       ; sixteen words per tile
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
queue:
    jsr vram_queue
    bne ready
    ; The queue was full: it is asked for again next frame.
    ldy npc_row
    lda #$FF
    sta npc_buf + 12, y
ready:
    rts
.endproc

; What hot-swapped poses leave behind after the bank is restored: each slot
; now holds the pose the converter left in the cartridge, not the one its NPC
; had been showing. `load_sprite` fixes the hero's —it leaves
; `hero_pose_vram` at $FF— and the NPCs' live in `npc_buf + 12`, which is the
; only part of that table this touches: it is a shadow of what is in VRAM,
; not game state.
;
; With $FF no pose matches, so each row's next `upload_npc_pose` queues it
; again. Without this the shadow would lie and an NPC that was already in its
; pose would keep the cartridge's forever.
.proc npc_poses_forget
.a8
.i16
    ldy #$0000
other:
    cpy npc_total               ; comes in bytes, not rows
    beq ready
    lda #$FF
    sta npc_buf + 12, y
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra other
ready:
    rts
.endproc

; Sets the row of the NPC in slot X to where the event is now: the position in
; pixels, the key it is sorted by, and the tile of the pose that is due.
;
; The first thing it does is copy what it needs out of the slot, and only
; after that does it use X for something else. It is longer to read and much
; harder to break: three routines are called inside and all of them use
; indexes.
.proc refresh_npc
.a8
.i16
    stz jump_height
    stz jump_height + 1
    jsr event_cell              ; leaves its cell in cell_x/cell_y, and uses X
    lda route_ev + 7, x
    sta slot_frames             ; whether there is a step in progress
    rep #$20
.a16
    lda route_ev + 22, x        ; and how much it has left, at 256 per cell: to
    lsr a                       ; pixels, dropping the sixteenths
    lsr a
    lsr a
    lsr a
    sta slot_px
    sep #$20
.a8
    lda route_ev + 8, x
    sta slot_facing
    lda route_ev + 30, x
    sta slot_dir                ; the direction of the step in progress
    lda route_ev + 10, x
    sta slot_step
    jsl f:slot_npc + FAST         ; `event_npc`, remembered in the slot
    sty npc_row
    cpy #$FFFF
    bne has_row
    rts                         ; the event has no graphic: nothing to move
has_row:

    ; Where it is, in pixels: the cell times sixteen, minus what the step in
    ; progress has left at WALK_SPEED per frame.
    rep #$20
.a16
    lda cell_x
    asl a
    asl a
    asl a
    asl a
    sta npc_px
    lda cell_y
    asl a
    asl a
    asl a
    asl a
    sta npc_py
    lda slot_px                 ; the pixels left in the step
    sta temp
    sep #$20
.a8
    lda slot_frames
    beq no_step_npc             ; no step in progress, it is already on its cell
    bra with_step_npc
no_step_npc:
    ; Is it jumping? Then the cell is the destination and the drawing lags
    ; behind, with the arc on top. The sort key comes from the position
    ; **without** the arc: it is `GetScreenY(false)`, so whoever is in the air
    ; does not move ahead.
    lda route_ev + 13, x
    beq set
    sta jump_remain
    lda route_ev + 14, x
    sta jump_dx
    lda route_ev + 15, x
    sta jump_dy
    phx
    jsr jump_npc_position
    jsr jump_height_of
    plx
    bra set
with_step_npc:

    ; The direction of the step, which is separate from which way it faces:
    ; with its facing locked —the droids on map 2— it goes up facing down. By
    ; table, because diagonally both axes have to be discounted: the pixels
    ; left are subtracted along the step's direction, so whoever is going
    ; right is still drawn to the left of its cell. X is clobbered and nobody
    ; else needs it: from here on the index is `npc_row`.
    lda slot_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:step_dx_table, x
    beq no_dx_npc
    bmi more_px                 ; $FF, that is, to the left
    jsr sub_a_from_px
    bra no_dx_npc
more_px:
    jsr add_a_to_px
no_dx_npc:
    lda f:step_dy_table, x
    beq set
    bmi more_py                 ; it came from below: it still has to go up
    jsr sub_a_from_py
    bra set
more_py:
    jsr add_a_to_py

set:
    ; Into the row: the position, and the key with the layer it already had.
    ldy npc_row
    rep #$20
.a16
    lda npc_px
    sta npc_buf + 0, y
    lda npc_py
    sta npc_buf + 2, y
    sep #$20
.a8
    lda jump_height
    sta npc_buf + 11, y         ; how much to raise the drawing, without touching the key
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$F000                  ; the layer stays; the Y is replaced
    sta temp
    lda npc_py
    and #$0FFF
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8

    ; The pose: which way it faces times three, plus the cycle's column.
    ; Column 3 draws the same as column 1, which is how RM2k builds a cycle of
    ; four out of three columns.
    lda slot_facing
    cmp #ROUTE_EV_NO_FACE
    bne has_dir
    lda npc_buf + 10, y         ; has not turned yet: faces where its page says
has_dir:
    ; And if it is the one facing the hero, where the turn says: its slot is
    ; free, because with a route running it does not turn. See
    ; `turn_fire`.
    pha
    lda f:TURN_EV
    cmp npc_buf + 8, y
    bne no_turn
    pla
    lda f:TURN_DIR
    pha
no_turn:
    pla
    sta temp
    asl a
    clc
    adc temp                    ; times three
    sta temp
    lda slot_step
    cmp #$03
    bne no_adjust
    lda #$01
no_adjust:
    clc
    adc temp                    ; the pose, 0 to 11
    jsr upload_npc_pose
fit:
    jmp fit_npc                 ; and the row, to wherever it belongs now
.endproc

; Puts row `npc_row` where it belongs now, with the table already sorted:
; see `fit_far`, in bank 1.
.proc fit_npc
.a8
.i16
    jsl f:fit_far + FAST            ; see MEMSEL
    rts
.endproc

; The four additions for the step in progress, with `temp` holding the pixels
; left. They are separate because the `rep`/`sep` of each one inside the `cmp`
; made the procedure so long that the branches did not reach.
.proc add_a_to_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    clc
    adc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc sub_a_from_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    sec
    sbc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc add_a_to_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    clc
    adc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

.proc sub_a_from_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    sec
    sbc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

