.segment "FAR"
.a8
.i16

; --- the ShowPicture pictures -------------------------------------------------
;
; `PIC_SLOTS` pictures at a time, each shown in a slot of its own: the event
; compiler gives each RM2k picture number of a map a slot, and the opcodes
; say which. What a slot shows is an entry of the loaded map's table,
; `picture_data` —see `picture_tables` in rm2k-snes-mapdata—, whose tiles are
; in the map's sprite bank: they were uploaded with it, so showing a picture
; uploads nothing but its palette, and coming back from a battle or the menu
; finds them where they were. Their palettes too: `pic_palette` leaves them in
; `cgram_shadow`, which `scene_cgram_restore` uploads again after a battle,
; and the menu, the shop and the slots do not touch sprite palettes 6 and 7.
; Which pictures each map carries is the converter's: see
; tools/port/picture.py.
;
; **RM2k's position is the picture's centre**, and the console computes the
; corner when it shows it, from the centre and half the picture's size in
; RM2k's pixels: a picture placed by variables does not know its place until
; then. One that goes with the screen is scaled like everything RM2k puts on
; its 320x240 —four fifths across, fourteen fifteenths down, rounded down
; with the negatives too, as `Screens::place` does in rm2k-snes-images—; one
; that goes with the map is not, because the map is not: its corner is kept
; in the map's pixels, and it scrolls with the camera.
;
; They go **after the timer and the counter and before the characters**,
; which is RM2k's order: `Priority_Timer` is 140, `Priority_PictureOld` 120
; and `Priority_Player` 40. In OAM that is the order of the list, because
; the lowest index wins; and priority 3 puts them in front of both layers.
;
; The transparency goes in three steps: one three quarters transparent or
; more is not drawn at all, from a quarter it is mixed half and half with
; what is under it —the experiment of `pic_blend`, in picture.s—, and under
; that it is opaque. The shadow on map 311 appears from 100 and stays at 50.
; What is lost is written in `divergencias/`.

; From this transparency up a picture is not drawn.
PIC_HIDDEN = 76

; RM2k's screen against the console's: how much wider and taller it is. A
; picture that goes with the map is placed where RM2k's display would be,
; which is the console's camera centred on the same point.
PIC_RM_EXTRA_X = 320 - 256
PIC_RM_EXTRA_Y = 240 - 224

; No picture, and no ramp: on reset and on every map change. RM2k 2000
; erases them there —`erase_on_map_change`— and besides, their tiles belong
; to the map that is being left.
.proc pic_clear
.a8
.i16
    lda #PIC_NONE
    ldx #PIC_SLOTS - 1
each:
    sta f:PIC_IMG, x
    dex
    bpl each
    sta f:PIC_RAMP
    lda #0
    ldx #PIC_SLOTS - 1
flags:
    sta f:PIC_FLAGS, x
    dex
    bpl flags
    jsr big_clear               ; and the big one: see big_picture.s
    rtl
.endproc

; The entry of picture A8 in the loaded map's table, in X; the carry set if
; the map carries none. Leaves A at eight bits.
.proc pic_entry
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a                       ; PICTURE_ENTRY bytes each
    clc
    adc #3                      ; after the base and the count
    pha
    lda map_current
    asl a
    tax
    lda f:picture_maps, x
    beq none
    clc
    adc 1, s
    tax
    pla
    sep #$20
.a8
    clc
    rts
.a16
none:
    pla
    sep #$20
.a8
    sec
    rts
.endproc

; `OP_PICTURE`: slot, image, mode, x, y, r, g, b, transparency. Enters with Y
; on the operands and leaves it past them. The picture is up with its tone
; from this frame on —`Game_Pictures::Show` leaves `time_left` at zero—.
.proc pic_show
.a8
.i16
    lda [code_ptr], y           ; the slot
    iny
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; A ramp on this slot is over: the new picture starts still.
    txa
    cmp f:PIC_RAMP
    bne no_ramp
    lda #PIC_NONE
    sta f:PIC_RAMP
no_ramp:
    lda [code_ptr], y           ; the picture
    iny
    sta f:PIC_IMG, x
    lda [code_ptr], y           ; how it is placed
    iny
    and #PIC_BY_VARIABLE | PIC_MAP_FIXED
    sta f:PIC_FLAGS, x
    ; The centre, in `temp` and `temp + 2`.
    rep #$20
.a16
    lda [code_ptr], y
    sta temp
    iny
    iny
    lda [code_ptr], y
    sta temp + 2
    iny
    iny
    ; The tone, three bytes from slot * 3, and the transparency.
    phx
    txa
    asl a
    clc
    adc 1, s
    tax
    sep #$20
.a8
    lda [code_ptr], y
    iny
    sta f:PIC_TONE + 0, x
    lda [code_ptr], y
    iny
    sta f:PIC_TONE + 1, x
    lda [code_ptr], y
    iny
    sta f:PIC_TONE + 2, x
    plx
    lda [code_ptr], y
    iny
    sta f:PIC_TRANS, x
    phy                         ; the cursor is done with
    ; By variables: the centre is their value now, as RM2k reads it once.
    lda f:PIC_FLAGS, x
    and #PIC_BY_VARIABLE
    beq constant
    phx
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta temp
    lda temp + 2
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta temp + 2
    sep #$20
.a8
    plx
constant:
    phx
    lda f:PIC_IMG, x
    jsr pic_entry
    bcc found
    ; A map without pictures: the compiler gives it no `OP_PICTURE`, but a
    ; page that goes on after a teleport carries its old map's.
    plx
    lda #PIC_NONE
    sta f:PIC_IMG, x
    ply
    rtl
found:
    ; The corner: the centre minus half the size.
    rep #$20
.a16
    lda temp
    sec
    sbc f:picture_data + 0, x
    sta temp
    lda temp + 2
    sec
    sbc f:picture_data + 2, x
    sta temp + 2
    plx
    sep #$20
.a8
    lda f:PIC_FLAGS, x
    and #PIC_MAP_FIXED
    bne with_map
    phx
    rep #$20
.a16
    lda temp
    jsr pic_scale_x
    sta temp
    lda temp + 2
    jsr pic_scale_y
    sta temp + 2
    sep #$20
.a8
    plx
    bra place
with_map:
    jsr pic_on_map
place:
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda temp
    sta f:PIC_X, x
    lda temp + 2
    sta f:PIC_Y, x
    sep #$20
.a8
    plx
    jsr pic_slot_palette
    ply
    rtl
.endproc

; `temp` and `temp + 2`, a corner on RM2k's screen, to the map's pixels: where
; RM2k's display would be, which is the console's camera centred on the same
; point and kept inside the map as RM2k keeps its own —`cam_max_x` is the
; map's width minus the console's screen, so RM2k's bound is that minus the
; difference between the two screens—.
.proc pic_on_map
.a8
.i16
    rep #$20
.a16
    lda cam_max_x
    sec
    sbc #PIC_RM_EXTRA_X
    bpl :+
    lda #0
:   pha                         ; the farthest RM2k's display goes
    lda camera_x
    sec
    sbc #PIC_RM_EXTRA_X / 2
    bpl :+
    lda #0
:   cmp 1, s
    bcc :+
    lda 1, s
:   clc
    adc temp
    sta temp
    pla
    lda cam_max_y
    sec
    sbc #PIC_RM_EXTRA_Y
    bpl :+
    lda #0
:   pha
    lda camera_y
    sec
    sbc #PIC_RM_EXTRA_Y / 2
    bpl :+
    lda #0
:   cmp 1, s
    bcc :+
    lda 1, s
:   clc
    adc temp + 2
    sta temp + 2
    pla
    sep #$20
.a8
    rts
.endproc

; `ControlVars` class 6 with RM2k's 4 and 5: a character's x or y on **RM2k's**
; screen, `GetScreenX()` and `GetScreenY()` —the centre of its cell and its
; feet, minus where RM2k's display is—. The display is the one the pictures
; are placed on, `pic_on_map`, so a `ShowPicture` by these variables lands on
; the character as in RM2k: it is what map 207 does with its smoke. The
; jump's height is not taken off, as RM2k does: no page of the game asks in
; the middle of a jump.
;
; Enters with A8 at CHARACTER_SCREEN_X or the next one and X at the target
; times EV_STRIDE —0 the hero—, as `op_var` leaves them; `temp` is op_var's
; and goes back as it came. Returns the value in A16 **with the accumulator
; at sixteen bits**, and Y as it came. Clobbers X.
.proc character_screen
.a8
.i16
    phy
    pha                         ; which one
    rep #$20
.a16
    lda temp                    ; op_var's slot and operation
    pha
    cpx #$0000
    bne event
    lda hero_x
    sta temp
    lda hero_y
    sta temp + 2
    bra cell
event:
    ; With a row in the NPC table, its pixels, which follow a step under way;
    ; without one —an event that draws nothing, like 207's—, its cell. The
    ; search is `event_npc`'s, which lives in bank 0.
    txa
    lsr a
    lsr a
    dec a                       ; the event index: the target minus one
    sep #$20
.a8
    ldy #$0000
seek:
    cpy npc_total
    beq no_row
    cmp npc_buf + 8, y
    beq row
    pha
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    pla
    bra seek
row:
    rep #$20
.a16
    lda npc_buf + 0, y
    sta temp
    lda npc_buf + 2, y
    sta temp + 2
    bra cell
.a8
no_row:
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 0, x
    asl a
    asl a
    asl a
    asl a
    sta temp
    lda ev_pos_buf - EV_STRIDE + 2, x
    asl a
    asl a
    asl a
    asl a
    sta temp + 2
cell:
    lda temp
    clc
    adc #8                      ; the centre of the cell
    pha
    lda temp + 2
    clc
    adc #16                     ; its feet
    pha
    stz temp
    stz temp + 2
    sep #$20
.a8
    jsr pic_on_map              ; RM2k's display, in temp and temp + 2
    rep #$20
.a16
    ; The stack: 1 the feet, 3 the centre, 5 op_var's temp, 7 which one.
    lda 7, s
    and #$00FF
    cmp #CHARACTER_SCREEN_X
    bne screen_y
    lda 3, s
    sec
    sbc temp
    bra ready
screen_y:
    lda 1, s
    sec
    sbc temp + 2
ready:
    sta temp + 2
    pla
    pla
    pla
    sta temp
    sep #$20
.a8
    pla
    ply
    rep #$20
.a16
    lda temp + 2
    rtl
.endproc

; A = floor(A * 4 / 5) and A = floor(A * 14 / 15), A signed: an RM2k screen
; coordinate on the console's. The sign goes out before dividing —the
; hardware divider has none— and a negative one rounds away from zero,
; which is the floor.
.proc pic_scale_x
.a16
.i16
    ora #0
    bmi negative
    asl a
    asl a
    ldx #5
    jmp pic_divide
negative:
    eor #$FFFF
    inc a
    asl a
    asl a
    clc
    adc #4
    ldx #5
    jsr pic_divide
    eor #$FFFF
    inc a
    rts
.endproc

.proc pic_scale_y
.a16
.i16
    ora #0
    bmi negative
    jsr pic_times_14
    ldx #15
    jmp pic_divide
negative:
    eor #$FFFF
    inc a
    jsr pic_times_14
    clc
    adc #14
    ldx #15
    jsr pic_divide
    eor #$FFFF
    inc a
    rts
.endproc

.proc pic_times_14
.a16
.i16
    asl a                       ; twice
    pha
    asl a
    asl a
    asl a                       ; sixteen times
    sec
    sbc 1, s
    plx
    rts
.endproc

; A / X, sixteen bits by eight, with the hardware divider: the quotient.
.proc pic_divide
.a16
.i16
    sta WRDIVL
    sep #$20
.a8
    txa
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDDIVL
    rts
.endproc

; Slot X's palette, from its tone and its picture's colours. Keeps X.
.proc pic_slot_palette
.a8
.i16
    phx
    lda f:PIC_IMG, x
    jsr pic_entry
    bcs none
    rep #$20
.a16
    lda f:picture_data + 8, x   ; where its colours are
    clc
    adc #.loword(picture_data)
    sta tint_ptr
    sep #$20
.a8
    lda #^picture_data
    sta tint_ptr + 2
    lda 1, s                    ; the slot
    jsl f:pic_palette + FAST
none:
    plx
    rts
.endproc

; `OP_PICTURE_MOVE`: slot, and the tone and transparency it goes to in how
; many frames. Enters with Y on the operands and leaves it past them.
;
; A `Move` on a slot with nothing shown writes the target to something that
; is not drawn: the operands are consumed anyway —the stream has to stay on
; the same byte on both sides— and nothing else happens.
.proc pic_move
.a8
.i16
    lda [code_ptr], y           ; the slot
    iny
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:PIC_IMG, x
    cmp #PIC_NONE
    bne shown
    iny
    iny
    iny
    iny
    iny
    rtl
shown:
    ; Another slot's ramp ends here, where it was going: there is one. This
    ; slot's own goes on from where it is, as RM2k's does.
    lda f:PIC_RAMP
    cmp #PIC_NONE
    beq free
    cmp #PIC_BIG
    bne slot_ramp
    phx
    jsr big_arrive              ; the big one's, in big_picture.s
    plx
    bra free
slot_ramp:
    txa
    cmp f:PIC_RAMP
    beq free
    lda f:PIC_RAMP
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr pic_arrive
    plx
free:
    lda [code_ptr], y
    iny
    sta f:PIC_TO + 0
    lda [code_ptr], y
    iny
    sta f:PIC_TO + 1
    lda [code_ptr], y
    iny
    sta f:PIC_TO + 2
    lda [code_ptr], y
    iny
    sta f:PIC_TO + 3
    lda [code_ptr], y
    iny
    sta f:PIC_STEPS
    phy
    ; From where it is now.
    lda f:PIC_TRANS, x
    sta f:PIC_FROM + 3
    phx
    rep #$20
.a16
    txa
    asl a
    clc
    adc 1, s
    tax
    sep #$20
.a8
    lda f:PIC_TONE + 0, x
    sta f:PIC_FROM + 0
    lda f:PIC_TONE + 1, x
    sta f:PIC_FROM + 1
    lda f:PIC_TONE + 2, x
    sta f:PIC_FROM + 2
    plx
    lda #0
    sta f:PIC_STEP
    lda f:PIC_STEPS
    bne ramp
    ; No frames: it is there already.
    jsr pic_arrive
    ply
    rtl
ramp:
    txa
    sta f:PIC_RAMP
    ply
    rtl
.endproc

; Slot X where its ramp goes —`PIC_TO`— now, with its palette, and no ramp.
.proc pic_arrive
.a8
.i16
    lda f:PIC_TO + 3
    sta f:PIC_TRANS, x
    phx
    rep #$20
.a16
    txa
    asl a
    clc
    adc 1, s
    tax
    sep #$20
.a8
    lda f:PIC_TO + 0
    sta f:PIC_TONE + 0, x
    lda f:PIC_TO + 1
    sta f:PIC_TONE + 1, x
    lda f:PIC_TO + 2
    sta f:PIC_TONE + 2, x
    plx
    lda #PIC_NONE
    sta f:PIC_RAMP
    jmp pic_slot_palette
.endproc

; `OP_PICTURE_ERASE`: slot. Enters with Y on it and leaves it past it.
.proc pic_erase
.a8
.i16
    lda [code_ptr], y
    bpl slot                    ; before the `iny`, which leaves N of Y
    iny
    jmp big_erase               ; PIC_BIG: the big one, in its layer
slot:
    iny
    cmp f:PIC_RAMP
    bne still
    pha
    lda #PIC_NONE
    sta f:PIC_RAMP
    pla
still:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #PIC_NONE
    sta f:PIC_IMG, x
    rtl
.endproc

; One frame of the ramp. `Game_Pictures::Picture::Update` interpolates with
; `(finish - current) / dt` over `double`, and the exact result of that
; sequence is linear: `from + (to - from) * step / steps`. Here it is done
; with integers, and the sign is taken out before dividing: the hardware
; divider does not have one.
;
; The palette is rebuilt **only when the tone really changed**. In the
; 210-frame ramp of "1 year earlier" the red goes up from 0 to 100, which
; means it changes one frame out of two: rebuilding it anyway cost 96
; products and 96 divisions per frame to write the same thirty-two bytes.
.proc pic_tick
.a8
.i16
    jsr big_frame               ; the big one's wave and ramp: big_picture.s
    lda f:PIC_RAMP
    bpl ramping                 ; PIC_NONE and PIC_BIG have bit 7
    rtl
ramping:
    lda f:PIC_STEP
    inc a
    sta f:PIC_STEP
    ; The four channels, the transparency on top of the stack's.
    ldx #3
each:
    jsr pic_channel
    pha
    dex
    bpl each
    ; The slot: its transparency, and its tone, which says whether it changed.
    lda f:PIC_RAMP
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda 4, s
    sta f:PIC_TRANS, x
    phx
    rep #$20
.a16
    txa
    asl a
    clc
    adc 1, s
    tax                         ; the tone's three bytes
    sep #$20
.a8
    stz temp                    ; whether any changed
    lda 3, s                    ; red: the slot's two bytes are on top
    cmp f:PIC_TONE + 0, x
    beq :+
    sta f:PIC_TONE + 0, x
    inc temp
:   lda 4, s
    cmp f:PIC_TONE + 1, x
    beq :+
    sta f:PIC_TONE + 1, x
    inc temp
:   lda 5, s
    cmp f:PIC_TONE + 2, x
    beq :+
    sta f:PIC_TONE + 2, x
    inc temp
:   plx                         ; the slot
    pla
    pla
    pla
    pla
    lda temp
    beq same
    jsr pic_slot_palette
same:
    lda f:PIC_STEP
    cmp f:PIC_STEPS
    bcc going
    lda #PIC_NONE               ; arrived
    sta f:PIC_RAMP
going:
    rtl
.endproc

; This frame's value of channel X of the ramp, in A. Keeps X.
;
; The subtraction always goes on the positive side, as in
; `one_flash_table`: the hardware divider has no sign, and a floor rounds
; the other way with negatives.
.proc pic_channel
.a8
.i16
    lda f:PIC_TO, x
    cmp f:PIC_FROM, x
    bcc low
    sec
    sbc f:PIC_FROM, x
    jsr pic_part
    clc
    adc f:PIC_FROM, x
    rts
low:
    lda f:PIC_FROM, x
    sec
    sbc f:PIC_TO, x
    jsr pic_part
    eor #$FF                    ; `from - part` without a variable in between:
    sec                         ; ones' complement plus the carry is the minus
    adc f:PIC_FROM, x
    rts
.endproc

; A = A * PIC_STEP / PIC_STEPS, with the hardware multiplier and divider.
; The product reaches 200 * 255 and fits in sixteen bits; the quotient does
; not go past 200, so the low byte is enough.
.proc pic_part
.a8
.i16
    sta WRMPYA
    lda f:PIC_STEP
    sta WRMPYB
    nop                         ; eight cycles until the product is ready
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; the dividend, sixteen bits
    sep #$20
.a8
    lda f:PIC_STEPS
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    rts
.endproc

; The pictures' objects, slot by slot. Called from `build_oam` with `jsl`.
.proc pic_oam
.a8
.i16
    ldx #$0000
each:
    lda f:PIC_IMG, x
    cmp #PIC_NONE
    beq next
    lda f:PIC_TRANS, x
    cmp #PIC_HIDDEN
    bcs next
    phx
    jsr pic_draw
    plx
next:
    inx
    cpx #PIC_SLOTS
    bne each
    rtl
.endproc

; Slot X's objects: each one at its place from the corner, with its tile
; —the base plus its block, four objects to a row of blocks: see
; `block_tile` in picture.py— and the slot's palette.
.proc pic_draw
.a8
.i16
    phx                         ; the slot
    lda f:PIC_IMG, x
    jsr pic_entry
    bcc found
    plx
    rts
found:
    rep #$20
.a16
    lda f:picture_data + 10, x  ; the base tile
    pha
    lda f:picture_data + 6, x   ; where its objects are
    pha
    sep #$20
.a8
    lda f:picture_data + 5, x   ; its first block
    pha
    lda f:picture_data + 4, x   ; how many
    pha
    ; The stack: 1 how many are left, 2 the block, 3 the objects, 5 the
    ; base, 7 the slot.
    rep #$20
.a16
    lda 7, s
    asl a
    tax
    lda f:PIC_X, x
    sta temp
    lda f:PIC_Y, x
    sta temp + 2
    lda 7, s
    tax
    sep #$20
.a8
    lda f:PIC_FLAGS, x
    and #PIC_MAP_FIXED
    beq still
    rep #$20
.a16
    lda temp
    sec
    sbc screen_x                ; the camera plus the shake, as the characters
    sta temp
    lda temp + 2
    sec
    sbc camera_y
    sta temp + 2
    sep #$20
.a8
still:
    lda #$02
    sta obj_big                 ; 32x32
object:
    lda 1, s
    beq done
    dec a
    sta 1, s
    rep #$20
.a16
    lda 3, s
    tax
    inc a
    inc a
    sta 3, s
    lda f:picture_data, x       ; dx, and dy above
    and #$00FF
    clc
    adc temp
    sta obj_x
    lda f:picture_data, x
    xba
    and #$00FF
    clc
    adc temp + 2
    sta obj_y
    ; Its tile: the base, plus 64 per row of blocks and 4 per block.
    lda 2, s
    and #$00FF
    tax
    and #$0003
    asl a
    asl a
    sta obj_tile                ; and `obj_attr`, a word for a moment
    txa
    and #$00FC
    asl a
    asl a
    asl a
    asl a
    clc
    adc obj_tile
    clc
    adc 5, s
    sta obj_tile                ; the ninth bit falls in `obj_attr`
    sep #$20
.a8
    lda 2, s
    inc a
    sta 2, s
    ; vhoopppN: priority 3, palette 7 - slot, and the tile's ninth bit.
    lda 7, s
    eor #$07
    asl a
    ora #$30
    ora obj_attr
    sta obj_attr
    jsl f:emit_object_far + FAST
    bra object
done:
    pla
    pla
    rep #$20
.a16
    pla
    pla
    sep #$20
.a8
    plx
    rts
.endproc
