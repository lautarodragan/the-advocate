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
; `cgram_shadow`, which `scene_cgram_restore` uploads again after a battle and
; the menus put back when they close. Which pictures each map carries, which
; sprite palettes they share —from the top, 7 down— and how each is cut into
; 32x32 and 8x8 objects is the converter's: see
; rm2k-snes/convert/src/pictures.rs.
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
; What is lost is written in `divergences/`, in the book.

; From this transparency up a picture is not drawn.
PIC_HIDDEN = 76

; RM2k's screen against the console's: how much wider and taller it is. A
; picture that goes with the map is placed where RM2k's display would be,
; which is the console's camera moved by what each one leaves to the left of
; the hero and above it.
PIC_RM_EXTRA_X = 320 - 256
PIC_RM_EXTRA_Y = 240 - 224
; The console's camera centres the hero's cell, 120 pixels from the left and
; 104 from the top; RM2k's leaves **nine** cells to the left, 144, and seven
; above, 112 —`kPanXDefault` and `kPanYDefault` in liblcf—, so its display
; is not centred sideways: the hero's cell ends at 160 of 320. Until 2026-10-11
; this was half of PIC_RM_EXTRA_X, the centred one, and the pictures that go
; with the map landed eight pixels to the left of RM2k's: the screen x of
; `character_screen`, held up against RM2k's numbers, is what showed it.
PIC_RM_LEFT = 144 - 120
PIC_RM_TOP  = 112 - 104
.assert PIC_RM_TOP = PIC_RM_EXTRA_Y / 2, error, "vertically RM2k's display is centred, like the console's"

; No picture, and no ramp: on reset and on every map change. RM2k 2000
; erases them there —`erase_on_map_change`— and besides, their tiles belong
; to the map that is being left.
.proc pic_clear
.a8
.i16
    ldx #PIC_SLOTS - 1
each:
    lda #PIC_NONE
    sta f:PIC_IMG, x
    lda #0
    sta f:PIC_FLAGS, x
    sta f:PIC_R_STEPS, x
    dex
    bpl each
    ldx #7
palettes:
    sta f:PIC_PAL_PENDING, x
    dex
    bpl palettes
    lda #PIC_NONE
    sta f:PIC_RAMP
    stz pic_dirty
    rep #$20
.a16
    stz pic_last
    sep #$20
.a8
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
    lda #0
    sta f:PIC_R_STEPS, x
    ; And the frame's loops walk up to it.
    rep #$20
.a16
    txa
    inc a
    cmp pic_last
    bcc below
    sta pic_last
below:
    sep #$20
.a8
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
    lda f:PIC_FLAGS, x
    jsr pic_place
    bcc placed
    ; A map without pictures: the compiler gives it no `OP_PICTURE`, but a
    ; page that goes on after a teleport carries its old map's.
    lda #PIC_NONE
    sta f:PIC_IMG, x
    ply
    rtl
placed:
    jsr pic_set_corner
    ; Its palette, which the converter chose: see `picture_tables`.
    phx
    lda f:PIC_IMG, x
    jsr pic_entry
    lda f:picture_data + 5, x
    plx
    sta f:PIC_PAL, x
    jsr pic_slot_palette
    ply
    rtl
.endproc

; Slot X's corner from a centre: `temp` and `temp + 2` are RM2k's x and y,
; or two variable slots if A has PIC_BY_VARIABLE —RM2k reads them once, when
; the command runs—, and they are left as the corner, on the console's screen
; or, for a picture whose flags say it goes with the map, on the map. With
; the carry set if the map carries no such picture. Keeps X.
.proc pic_place
.a8
.i16
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
    plx
    sec
    rts
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
    sep #$20
.a8
    plx
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
    clc
    rts
with_map:
    jsr pic_on_map
    clc
    rts
.endproc

; `temp` and `temp + 2` as slot X's corner. Keeps X.
.proc pic_set_corner
.a8
.i16
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
    rts
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
    sbc #PIC_RM_LEFT
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
    sbc #PIC_RM_TOP
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

; What a ramp of a slot needs besides its arrays, for the frame it is
; walked in: its step and its steps, for `pic_kn`; and, while a move is
; set up, its mode and the sign `pic_axis` found.
.pushseg
.segment "BSS"
pic_k:    .res 1
pic_n:    .res 1
pic_mode: .res 1
pic_neg:  .res 1
.popseg

; `OP_PICTURE_MOVE`: slot, the tone and transparency it goes to, in how many
; frames, the mode and where its centre goes —x and y: RM2k's screen, or
; two variable slots with PIC_BY_VARIABLE; with PIC_MOVES off it stays—.
; Enters with Y on the operands and leaves it past them.
;
; **Each slot has its own ramp**, as each RM2k picture does: a move on one
; does not end another's. The tone, the transparency and the corner go in a
; straight line from where they are, which is what `Game_Pictures::Picture::
; Update`'s `(finish - current) / time_left` gives over the frames. A
; picture that goes with the map does not move: RM2k 2000 does not move it
; either —`ignore_position` with `IsLegacy`—.
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
    rep #$20
.a16
    tya
    clc
    adc #10                     ; tone, transparency, frames, mode, x, y
    tay
    sep #$20
.a8
    rtl
shown:
    phx                         ; the slot
    ; Four bytes of ramp per slot, in `temp + 2`, and three of tone, in
    ; `temp`.
    rep #$20
.a16
    txa
    asl a
    asl a
    sta temp + 2
    txa
    asl a
    clc
    adc 1, s
    sta temp
    sep #$20
.a8
    ldx temp + 2
    lda [code_ptr], y
    iny
    sta f:PIC_R_TO + 0, x
    lda [code_ptr], y
    iny
    sta f:PIC_R_TO + 1, x
    lda [code_ptr], y
    iny
    sta f:PIC_R_TO + 2, x
    lda [code_ptr], y
    iny
    sta f:PIC_R_TO + 3, x
    ; From where it is now.
    ldx temp
    lda f:PIC_TONE + 0, x
    ldx temp + 2
    sta f:PIC_R_FROM + 0, x
    ldx temp
    lda f:PIC_TONE + 1, x
    ldx temp + 2
    sta f:PIC_R_FROM + 1, x
    ldx temp
    lda f:PIC_TONE + 2, x
    ldx temp + 2
    sta f:PIC_R_FROM + 2, x
    plx                         ; the slot
    lda f:PIC_TRANS, x
    phx
    ldx temp + 2
    sta f:PIC_R_FROM + 3, x
    plx
    ; How long, and a ramp that starts.
    lda [code_ptr], y
    iny
    sta f:PIC_R_STEPS, x
    sta pic_n
    lda #0
    sta f:PIC_R_STEP, x
    sta f:PIC_R_AX, x
    sta f:PIC_R_AY, x
    sta f:PIC_R_RX, x
    sta f:PIC_R_RY, x
    sta f:PIC_R_SIGN, x
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda #0
    sta f:PIC_R_QX, x
    sta f:PIC_R_QY, x
    sep #$20
.a8
    plx
    lda [code_ptr], y           ; the mode
    iny
    sta pic_mode
    rep #$20
.a16
    lda [code_ptr], y           ; where to
    sta temp
    iny
    iny
    lda [code_ptr], y
    sta temp + 2
    iny
    iny
    sep #$20
.a8
    phy                         ; the cursor is done with
    lda pic_mode
    and #PIC_MOVES
    beq placed
    lda f:PIC_FLAGS, x
    and #PIC_MAP_FIXED
    bne placed
    lda pic_mode
    jsr pic_place               ; the corner it goes to, in temp
    bcs placed
    lda pic_n
    bne walk
    jsr pic_set_corner          ; no frames: it is there already
    bra placed
walk:
    ; Each axis: what it moves every frame, the remainder and its sign.
    phx                         ; the slot
    rep #$20
.a16
    txa
    asl a
    tax
    lda temp
    sec
    sbc f:PIC_X, x
    jsr pic_axis
    sta f:PIC_R_QX, x
    lda 1, s
    tax
    sep #$20
.a8
    lda pic_k
    sta f:PIC_R_RX, x
    lda pic_neg
    sta f:PIC_R_SIGN, x
    rep #$20
.a16
    txa
    asl a
    tax
    lda temp + 2
    sec
    sbc f:PIC_Y, x
    jsr pic_axis
    sta f:PIC_R_QY, x
    lda 1, s
    tax
    sep #$20
.a8
    lda pic_k
    sta f:PIC_R_RY, x
    lda pic_neg
    asl a
    ora f:PIC_R_SIGN, x
    sta f:PIC_R_SIGN, x
    plx
placed:
    lda f:PIC_R_STEPS, x
    bne going
    jsr pic_arrive              ; no frames: it is there already
going:
    ply
    rtl
.endproc

; A16 = what an axis moves in `pic_n` frames, signed: answers what it moves
; every frame in A16, signed and rounded towards zero; the remainder in
; `pic_k` and whether it goes back in `pic_neg`. Keeps X and B.
;
; Bresenham's way: every frame the corner moves the quotient, and the
; remainder gathers; each time it passes the frames the corner moves one
; more pixel. After the last frame it is exactly where it was going, and in
; between where `from + d * step / steps` puts it, the line RM2k walks. The
; hardware divider takes sixteen bits by eight and has no sign, so the sign
; goes out first.
.proc pic_axis
.a16
.i16
    sep #$20
.a8
    stz pic_neg
    rep #$20
.a16
    ora #0
    bpl positive
    eor #$FFFF
    inc a
    sep #$20
.a8
    inc pic_neg
    rep #$20
.a16
positive:
    sta WRDIVL
    sep #$20
.a8
    lda pic_n
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDMPYL                  ; the remainder, under the frames
    sta pic_k
    lda pic_neg
    rep #$20
.a16
    beq plus
    lda RDDIVL
    eor #$FFFF
    inc a
    rts
plus:
    lda RDDIVL
    rts
.endproc

; Slot X where its ramp goes —its `PIC_R_TO`— now, with its palette, and no
; ramp. Keeps X.
.proc pic_arrive
.a8
.i16
    phx
    rep #$20
.a16
    txa
    asl a
    asl a
    sta temp + 2
    txa
    asl a
    clc
    adc 1, s
    sta temp
    sep #$20
.a8
    ldx temp + 2
    lda f:PIC_R_TO + 0, x
    ldx temp
    sta f:PIC_TONE + 0, x
    ldx temp + 2
    lda f:PIC_R_TO + 1, x
    ldx temp
    sta f:PIC_TONE + 1, x
    ldx temp + 2
    lda f:PIC_R_TO + 2, x
    ldx temp
    sta f:PIC_TONE + 2, x
    ldx temp + 2
    lda f:PIC_R_TO + 3, x
    plx
    sta f:PIC_TRANS, x
    lda #0
    sta f:PIC_R_STEPS, x
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
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #PIC_NONE
    sta f:PIC_IMG, x
    lda #0
    sta f:PIC_R_STEPS, x
    rtl
.endproc

; One frame of every ramp: the big one's —big_picture.s— and each slot's.
;
; `Game_Pictures::Picture::Update` interpolates with `(finish - current) /
; dt` over `double`, and the exact result of that sequence is linear: `from
; + (to - from) * step / steps`. Here it is done with integers, and the sign
; is taken out before dividing: the hardware divider does not have one.
.proc pic_tick
.a8
.i16
    jsr big_frame               ; the big one's wave and ramp: big_picture.s
    ldx #$0000
    bra test
each:
    lda f:PIC_R_STEPS, x
    beq next
    phx
    jsr pic_ramp_step
    plx
next:
    inx
test:
    cpx pic_last
    bne each
    rtl
.endproc

; One frame of slot X's ramp.
;
; The palette is rebuilt **only when the tone really changed**. In the
; 210-frame ramp of "1 year earlier" the red goes up from 0 to 100, which
; means it changes one frame out of two: rebuilding it anyway cost 96
; products and 96 divisions per frame to write the same thirty-two bytes.
.proc pic_ramp_step
.a8
.i16
    lda f:PIC_R_STEP, x
    inc a
    sta f:PIC_R_STEP, x
    sta pic_k
    lda f:PIC_R_STEPS, x
    sta pic_n
    phx                         ; the slot
    rep #$20
.a16
    txa
    asl a
    asl a
    tax                         ; four per slot
    sep #$20
.a8
    ; The four channels, the transparency on top of the stack's.
    jsr pic_lerp
    pha                         ; red
    inx
    jsr pic_lerp
    pha                         ; green
    inx
    jsr pic_lerp
    pha                         ; blue
    inx
    jsr pic_lerp
    pha                         ; transparency
    ; The stack: 1 transparency, 2 blue, 3 green, 4 red, 5 the slot.
    rep #$20
.a16
    lda 5, s
    tax
    sep #$20
.a8
    lda 1, s
    sta f:PIC_TRANS, x
    rep #$20
.a16
    txa
    asl a
    clc
    adc 5, s
    tax                         ; the tone's three bytes
    sep #$20
.a8
    stz temp                    ; whether any changed
    lda 4, s
    cmp f:PIC_TONE + 0, x
    beq :+
    sta f:PIC_TONE + 0, x
    inc temp
:   lda 3, s
    cmp f:PIC_TONE + 1, x
    beq :+
    sta f:PIC_TONE + 1, x
    inc temp
:   lda 2, s
    cmp f:PIC_TONE + 2, x
    beq :+
    sta f:PIC_TONE + 2, x
    inc temp
:   pla
    pla
    pla
    pla
    plx                         ; the slot
    lda temp
    beq same
    jsr pic_slot_palette
same:
    ; The corner: the quotient every frame, and a pixel more each time the
    ; remainder gathers past the frames.
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:PIC_X, x
    clc
    adc f:PIC_R_QX, x
    sta f:PIC_X, x
    lda f:PIC_Y, x
    clc
    adc f:PIC_R_QY, x
    sta f:PIC_Y, x
    sep #$20
.a8
    plx
    lda f:PIC_R_AX, x
    clc
    adc f:PIC_R_RX, x
    bcs x_over                  ; past 255 is past the frames too
    cmp pic_n
    bcc x_keep
x_over:
    sec
    sbc pic_n
    sta f:PIC_R_AX, x
    lda f:PIC_R_SIGN, x
    and #$01
    jsr pic_one
    jsr pic_nudge_x
    bra x_done
x_keep:
    sta f:PIC_R_AX, x
x_done:
    lda f:PIC_R_AY, x
    clc
    adc f:PIC_R_RY, x
    bcs y_over
    cmp pic_n
    bcc y_keep
y_over:
    sec
    sbc pic_n
    sta f:PIC_R_AY, x
    lda f:PIC_R_SIGN, x
    and #$02
    jsr pic_one
    jsr pic_nudge_y
    bra y_done
y_keep:
    sta f:PIC_R_AY, x
y_done:
    lda f:PIC_R_STEP, x
    cmp f:PIC_R_STEPS, x
    bcc going
    lda #0                      ; arrived
    sta f:PIC_R_STEPS, x
going:
    rts
.endproc

; A16 = 1, or -1 if A8 is not zero: the pixel a remainder adds.
.proc pic_one
.a8
.i16
    cmp #0
    rep #$20
.a16
    bne back
    lda #1
    rts
back:
    lda #$FFFF
    rts
.endproc

; A16 added to slot X's corner, on x or on y. Keeps X; leaves A at eight
; bits.
.proc pic_nudge_x
.a16
.i16
    phx
    pha
    txa
    asl a
    tax
    pla
    clc
    adc f:PIC_X, x
    sta f:PIC_X, x
    sep #$20
.a8
    plx
    rts
.endproc

.proc pic_nudge_y
.a16
.i16
    phx
    pha
    txa
    asl a
    tax
    pla
    clc
    adc f:PIC_Y, x
    sta f:PIC_Y, x
    sep #$20
.a8
    plx
    rts
.endproc

; This frame's value of ramp byte X —`PIC_R_FROM` to `PIC_R_TO`, at step
; `pic_k` of `pic_n`—, in A. Keeps X.
;
; The subtraction always goes on the positive side, as in `pic_channel`:
; the hardware divider has no sign, and a floor rounds the other way with
; negatives.
.proc pic_lerp
.a8
.i16
    lda f:PIC_R_TO, x
    cmp f:PIC_R_FROM, x
    bcc low
    sec
    sbc f:PIC_R_FROM, x
    jsr pic_kn
    clc
    adc f:PIC_R_FROM, x
    rts
low:
    lda f:PIC_R_FROM, x
    sec
    sbc f:PIC_R_TO, x
    jsr pic_kn
    eor #$FF                    ; `from - part`: ones' complement plus the
    sec                         ; carry is the minus
    adc f:PIC_R_FROM, x
    rts
.endproc

; A = A * pic_k / pic_n, with the hardware multiplier and divider: what
; `pic_part` does with the big one's step.
.proc pic_kn
.a8
.i16
    sta WRMPYA
    lda pic_k
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
    lda pic_n
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

; This frame's value of channel X of the big one's ramp —`PIC_FROM` to
; `PIC_TO`, at `PIC_STEP` of `PIC_STEPS`—, in A. Keeps X.
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

; The pictures' objects, slot by slot: slot 0 first, which is the highest
; RM2k number, in front. Called from `build_oam` with `jsl`; leaves
; `obj_big` at the characters' 32x32, as the timer leaves it.
.proc pic_oam
.a8
.i16
    ldx #$0000
    bra test
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
test:
    cpx pic_last
    bne each
    lda #$02
    sta obj_big
    rtl
.endproc

; In an object's tile word, the bit that makes it an 8x8 object: see
; `picture_tables` in rm2k-snes-mapdata, and `SMALL_BIT` in the converter's
; pictures.rs.
PIC_SMALL = $8000

; Slot X's objects: each one at its place from the corner, with its tile
; —the base plus the low nine bits of its word—, its size and the slot's
; palette.
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
    lda f:picture_data + 4, x   ; how many
    pha
    ; The stack: 1 how many are left, 2 the objects, 4 the base, 6 the slot.
    rep #$20
.a16
    lda 6, s
    asl a
    tax
    lda f:PIC_X, x
    sta temp
    lda f:PIC_Y, x
    sta temp + 2
    lda 6, s
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
    ; vhoopppN: priority 3 and the slot's palette, 7 - p from the top.
    lda f:PIC_PAL, x
    and #$07
    eor #$07
    asl a
    ora #$30
    pha
    ; The stack: 1 the attributes, 2 how many are left, 3 the objects, 5
    ; the base, 7 the slot.
object:
    lda 2, s
    beq done
    dec a
    sta 2, s
    rep #$20
.a16
    lda 3, s
    tax
    clc
    adc #4
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
    lda f:picture_data + 2, x   ; the tile word
    tax
    and #$01FF
    clc
    adc 5, s
    sta obj_tile                ; the ninth bit falls in `obj_attr`
    sep #$20
.a8
    lda 1, s
    ora obj_attr
    sta obj_attr
    rep #$20
.a16
    txa
    and #PIC_SMALL
    sep #$20
.a8
    bne small
    lda #$02                    ; 32x32
    bra size
small:
    lda #$00                    ; 8x8
size:
    sta obj_big
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
