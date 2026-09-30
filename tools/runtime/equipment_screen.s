.segment "FAR"

; --- equipment and the shop, outside bank 0 -----------------------------------
;
; The two screens are three kilobytes, and bank 0 had twelve bytes left in the
; test cartridge. They moved down here on 2026-09-19 for the same reason as
; battle and by the same route: they are entered with `jsl` to
; `equipment_screen` and `shop_screen`, and what they need from bank 0 is
; called through the `ba_t_*` bridges, which were already there for battle
; —only two new ones were needed, `ba_t_list` and `ba_t_build`—.
;
; **The data bank is still 0**, unlike battle: these two read and write the
; scratch space and bank 0's tables with absolute addressing and so keep working
; without touching anything. What did change is the other way around: a datum
; **from here** read with absolute addressing would land in bank 0. There is
; only one, `message`, and it goes with `f:`; it cost an afternoon of a shop
; with no greeting.
;
; It costs no frames: both block inside the page, `ticks` does not advance
; while they are shown, and the two extra cycles of each `jsl` fall on a screen
; waiting for the pad.
;
; `Scene_Equip`: the actor, their four parameters, the five slots with what
; they have on; A on a slot shows the list of what can be put on there —it
; replaces the slots while it lasts— with the parameters that would result.
; The empty line at the end is taking off what is in the slot. B goes back.
; `equipment_screen` of `rm2k-snes-screens` is the reference, and `equip` the
; rule. The windows and the cursor bar go on BG1, which BG2's text does not
; touch: see `eq_screen_upload` and `eq_bar`.
;   eq_actor     is comp_char      ; the actor number
;   eq_slot      is comp_col       ; the highlighted slot, 0 to 4
;   eq_eligiendo is comp_col + 1   ; whether the list is shown
;   eq_elegido   is comp_phase      ; the cursor's place in the list
;   eq_arriba    is comp_phase + 1  ; and the first one visible
;   eq_n         is comp_base      ; how many are in the list, with the empty one
;   eq_cand      is comp_mask      ; the item under the cursor, 0 if none
;   eq_suma      is comp_or01      ; a parameter, while being added up
;   eq_param     is comp_or01 + 2  ; which one
;   eq_s         is comp_or01 + 3  ; the slot being looked at
;   eq_id        is comp_or23      ; an item, two bytes
;   eq_tmp       is comp_and       ; `eq_point`'s scratch, four bytes

; A: the slot. Leaves the WRAM window pointing at that slot of the actor:
; `FAR_EQUIPMENT` + actor * 10 + slot * 2.
.proc eq_point
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta comp_and                  ; the slot times two
    lda comp_char
    and #$00FF
    asl a
    sta comp_and + 2              ; the actor times two
    asl a
    asl a                       ; times eight
    clc
    adc comp_and + 2
    clc
    adc comp_and
    clc
    adc #FAR_EQUIPMENT
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: the slot. Returns with the item in `eq_id`.
.proc eq_read
.a8
.i16
    jsr eq_point
    lda WMDATA
    sta comp_or23
    lda WMDATA
    sta comp_or23 + 1
    rts
.endproc

; A: the slot; `eq_id`: the new item.
.proc eq_write
.a8
.i16
    jsr eq_point
    lda comp_or23
    sta WMDATA
    lda comp_or23 + 1
    sta WMDATA
    rts
.endproc

; The `k` of the item in `eq_id`, in X, and Z=1 if it is none or one the ROM
; does not know.
.proc eq_k
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    beq none
    cmp #ITEMS_N
    bcs none
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq none8
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
.a16
none:
    sep #$20
.a8
none8:
    lda #0                      ; Z=1
    rts
.endproc

; How many of item `eq_id` are in the inventory, in A.
.proc eq_inv_point
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; One more —capped at 99— or one less of item `eq_id`. A: 1 adds, 0 subtracts.
.proc eq_inv_move
.a8
.i16
    pha
    jsr eq_inv_point
    lda WMDATA
    sta comp_and
    jsr eq_inv_point
    pla
    beq remain
    lda comp_and
    cmp #ITEM_MAX
    bcs ready
    inc a
    bra write
remain:
    lda comp_and
    beq ready
    dec a
write:
    sta WMDATA
ready:
    rts
.endproc

; Is item `eq_id` a two-handed weapon? Z=0 if so.
.proc eq_two_handed
.a8
.i16
    jsr eq_k
    beq no
    lda item_use, x
    and #8
    rts
no:
    lda #0
    rts
.endproc

; The item slot A would have: the one it has, or —while choosing— the one
; under the cursor if it is the chosen slot, and none in the other if the
; weapon is two-handed. It is the stage's `equip` without touching anything.
; Returns in `eq_id`.
.proc eq_effective
.a8
.i16
    sta comp_or01 + 3
    lda comp_col + 1
    beq has
    lda comp_or01 + 3
    cmp comp_col
    bne other
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    rts
other:
    ; A two-handed weapon removes the shield; a shield removes the two-handed
    ; weapon.
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_or01 + 3
    cmp #1
    bne no_shield
    lda comp_col
    bne has                     ; the weapon is not being chosen
    jsr eq_two_handed
    bne none
    bra has
no_shield:
    lda comp_or01 + 3
    bne has                     ; neither shield nor weapon: the usual one
    lda comp_col
    cmp #1
    bne has                     ; the shield is not being chosen
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq has                     ; taking off the shield does not touch the weapon
    lda #0
    jsr eq_read
    jsr eq_two_handed
    bne none
    rts                         ; `eq_id` is already the weapon
has:
    lda comp_or01 + 3
    jmp eq_read
none:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Parameter `eq_param` —0 attack, 1 defense, 2 spirit, 3 agility— with the
; equipment `eq_effective` says, in `scr_value`, capped to [1, 999].
.proc eq_parameter
.a8
.i16
    ; The one for their current level: `level_param`, where the four here go
    ; from 2 to 5. And Y is saved because `level_param` clobbers it and the
    ; caller of this does not expect that.
    phy
    rep #$20
.a16
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #2
    tay
    sep #$20
.a8
    lda comp_char
    jsl f:level_param
    stx comp_or01
    ply
    lda #0
slot:
    pha
    jsr eq_effective
    jsr eq_k
    beq no_points
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; eight bytes per item
    sta comp_and
    lda comp_or01 + 2
    and #$00FF
    asl a
    clc
    adc comp_and
    tax
    lda f:item_points, x
    clc
    adc comp_or01
    sta comp_or01
    sep #$20
.a8
no_points:
    pla
    inc a
    cmp #5
    bcc slot
    rep #$20
.a16
    lda comp_or01
    bmi one                     ; signed: equipment can subtract
    beq one
    cmp #1000
    bcc ready
    lda #999
    bra ready
one:
    lda #1
ready:
    sta comp_dup
    sep #$20
.a8
    rtl
.endproc

; The list of what the actor can put on in `eq_slot`, as `k` in
; `FAR_ITEM_LIST`, and at the end an $FF which is the empty line. How many in
; `eq_n`. It is `screens.candidates`.
.proc eq_list_build
.a8
.i16
    stz comp_base
    ldx #1
other:
    rep #$20
.a16
    txa
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq next
    lda f:item_k, x
    cmp #$FF
    beq next
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; X = k
    sep #$20
.a8
    lda comp_col
    inc a
    cmp item_type, x
    bne no_goes
    ; Can the actor use it? One bit per actor, eight bytes per item.
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta comp_and
    lda comp_char
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc comp_and
    sta comp_and                ; the byte; `comp_and` no longer holds k times eight
    pla
    and #$0007
    sta comp_and + 2              ; and the bit
    sep #$20
.a8
    ; With `f:` because `item_actors` moved to RODATA on 2026-09-13: it is 496
    ; bytes and bank 0's area was already fifteen over before the skills. It
    ; costs one byte and one cycle per read, and this runs once per item when
    ; opening the equipment screen.
    ;
    ; **Through X and not Y**: the 65816 has no `lda long, y`, only `long, x`.
    ; X holds the item's `k` and it is needed further down, so it goes to the
    ; stack and back. The `plx` leaves no flag being looked at: what follows
    ; is an `and`.
    ;
    ; The index comes from `comp_and` and not from Y, and that is not
    ; indifferent: two branches moved this same code to RODATA separately, one
    ; leaving the byte in Y —`tay`— and the other in `comp_and`. In the merge
    ; git kept one's `sta comp_and` and left the other's `tyx` in conflict:
    ; together they assembled and read a register nobody loaded anymore.
    phx
    ldx comp_and
    lda f:item_actors, x
    plx
    ldy comp_and + 2
    beq bit_ready
run:
    lsr a
    dey
    bne run
bit_ready:
    and #1
    beq no_goes
    txa                         ; the k, which fits in a byte
    pha
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LIST
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_base
no_goes:
    plx
next:
    inx
    cpx #ITEMS_N
    bcs list_list
    jmp other                   ; a `bcc`'s 127 bytes fell short once
                                ; `item_actors` was read long
list_list:
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LIST
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda #$FF                    ; the empty line
    sta WMDATA
    inc comp_base
    rts
.endproc

; The item at place A in the list, in `eq_id`: 0 if it is the empty line.
.proc eq_from_list
.a8
.i16
    jsl f:ba_t_list
    cmp #$FF
    beq empty
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    sta comp_or23
    sep #$20
.a8
    rts
empty:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Writes to `pick_table` the name of item `eq_id`, if the ROM knows it, with
; no more than A letters.
.proc eq_name
.a8
.i16
    sta comp_dup + 3
    jsr eq_k
    beq nothing
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax                         ; 3k, the name
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_text
    rts
nothing:
    lda #255
    sta comp_dup + 3
    rts
.endproc

; The description of item `eq_id`, on the top two lines.
.proc eq_desc
.a8
.i16
    jsr eq_k
    beq nothing
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    inc a                       ; 3k + 1
    pha
    lda #SCR_DESC_POS
    sta pick_table
    plx
    phx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_text
    rep #$20
.a16
    lda #(SCR_DESC_POS + 128)
    sta pick_table
    plx
    inx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_text
    rts
nothing:
    rts
.endproc

; The whole screen, in the buffer: the stage's `equipment_screen`.
.proc eq_compose
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_clear
    stz temp + 1
    ; --- the actor's name ---
    rep #$20
.a16
    lda #EQ_ACTOR_POS
    sta pick_table
    lda comp_char
    and #$00FF
    asl a
    tax
    lda actor_txt, x
    tax
    cmp #$FFFF                  ; an actor with no name in this ROM
    sep #$20                    ; `sep` does not touch Z
.a8
    beq no_name
    jsl f:ba_t_text
no_name:
    ; --- the description ---
    lda comp_col + 1
    beq the_set
    lda comp_phase
    jsr eq_from_list
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    bra desc
the_set:
    lda comp_col
    jsr eq_read
desc:
    jsr eq_desc
    ; --- the parameters: now and, while choosing, after ---
    stz comp_or01 + 2
param:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    sta pick_table
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #EQ_TEXT_PARAM
    tax
    sep #$20
.a8
    lda #3                      ; the term in red: `ITEM_RED`
    sta temp + 1
    jsl f:ba_t_text
    stz temp + 1
    lda comp_col + 1
    pha
    stz comp_col + 1            ; now: what is on
    jsl f:eq_parameter
    pla
    sta comp_col + 1
    rep #$20
.a16
    lda comp_dup                ; `ba_t_number` consumes it, and the new value
    pha                         ; is colored by comparing it with this one
    sep #$20
.a8
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_VALUE
    sta pick_table
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_number
    lda comp_col + 1
    beq no_arrow
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_ARROW
    sta pick_table
    sep #$20
.a8
    lda #3                      ; in red, like `Window_EquipStatus`
    sta temp + 1
    lda #$3E                    ; '>'
    jsl f:ba_t_glyph
    jsl f:eq_parameter            ; after: with what the cursor is on
    ; And its color, `Window_EquipStatus::GetNewParameterColor`'s: equal in
    ; white, more in the "goes up" one and less in gray. It is `pantallas.
    ; color_del_valor_nuevo`.
    rep #$20
.a16
    pla                         ; the current one
    cmp comp_dup
    sep #$20                    ; `sep` does not touch the `cmp`'s flags
.a8
    beq equal
    bcc uploads
    lda #1                      ; goes down: gray
    bra with_color
uploads:
    lda #2
    bra with_color
equal:
    lda #0
with_color:
    sta temp + 1
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_number
    stz temp + 1                ; what follows goes in white
    bra param_ready
no_arrow:
    rep #$20
.a16
    pla                         ; the current one, which was not needed
    sep #$20
.a8
param_ready:
    inc comp_or01 + 2
    lda comp_or01 + 2
    cmp #4
    bcs params_all_ready
    jmp param
params_all_ready:
    lda comp_col + 1
    bne list
    ; --- the slots ---
    lda #0
slot:
    pha                         ; the cursor is the bar: see `eq_bar`
    jsr row_pos
    rep #$20
.a16
    clc
    adc #EQ_SLOT_TERM
    sta pick_table
    sep #$20
.a8
    pla
    pha
    rep #$20
.a16
    and #$00FF
    clc
    adc #EQ_TEXT_SLOT
    tax
    sep #$20
.a8
    lda #3                      ; the term in red, and the name of what
    sta temp + 1                ; is on in white: `eq_name` restores it
    jsl f:ba_t_text
    pla
    pha
    jsr row_pos
    rep #$20
.a16
    clc
    adc #EQ_SLOT_NAME
    sta pick_table
    sep #$20
.a8
    pla
    pha
    jsr eq_read
    lda #EQ_SLOT_WIDTH
    jsr eq_name
    pla
    inc a
    cmp #5
    bcc slot
    rts

    ; --- the list ---
list:
    lda #0
list_row:
    pha
    clc
    adc comp_phase + 1
    cmp comp_base
    bcs list_ready
    pla
    pha
    clc
    adc comp_phase + 1
    jsr eq_from_list
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq list_next               ; the empty line
    pla
    pha
    jsr row_pos_list
    rep #$20
.a16
    clc
    adc #EQ_LIST_NAME
    sta pick_table
    sep #$20
.a8
    lda #255
    jsr eq_name
    pla
    pha
    jsr row_pos_list
    rep #$20
.a16
    clc
    adc #SCR_TWO_POINTS
    sta pick_table
    sep #$20
.a8
    stz temp + 1
    lda #$3A                    ; ':'
    jsl f:ba_t_glyph
    jsr eq_inv_point
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_number
list_next:
    pla
    inc a
    cmp #EQ_LIST_ROWS
    bcc list_row
    rts
list_ready:
    pla
    rts

; A16 = the position of parameter `eq_param`.
param_pos:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    rts
.a8

; A: the slot. A16 = the position of its row.
row_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; times 128: two rows of cells
    clc
    adc #EQ_SLOT_POS0
    rts
.a8

; A: the list row. A16 = the position of its row.
row_pos_list:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #EQ_LIST_POS0
    rts
.a8
.endproc

; A on the list: the stage's `equip` with what the cursor is on.
.proc eq_equip
.a8
.i16
    lda comp_phase
    jsr eq_from_list
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    lda comp_col
    jsr take
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq ready
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda #0
    jsr eq_inv_move             ; one less in the inventory
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_col
    jsr eq_write
    ; Two hands.
    lda comp_col
    bne no_weapon
    jsr eq_two_handed           ; `eq_id` is the new weapon
    beq ready
    lda #1
    jmp take
no_weapon:
    cmp #1
    bne ready
    lda #0
    jsr eq_read
    jsr eq_two_handed
    beq ready
    lda #0
    jmp take
ready:
    rts

; A: the slot. What it has goes back to the inventory and it is left empty.
take:
    pha
    jsr eq_read
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq empty
    lda #1
    jsr eq_inv_move
    stz comp_or23
    stz comp_or23 + 1
    pla
    jmp eq_write
empty:
    pla
    rts
.endproc

; The BG1 windows under the bar, and the bar: in each frame's vblank, behind
; the text. The rows of the bottom window are uploaded without the cursor
; —`EQ_BORDER_TEXT_N` rows of cells— and on top the cursor's two with the bar,
; from `eq_border_bars`: first those of the five slots and then those of the
; list rows. Without remembering where it was: each frame restores everything,
; so the bar cannot end up painted in two places. It is 768 bytes, some five
; vblank lines on top of the text's ten.
.proc eq_bar
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(ITEM_BORDER_MAP + EQ_BORDER_TEXT * 32)
    sta VMADDL
    lda #.loword(eq_border_map + EQ_BORDER_TEXT * 64)
    sta A1T0L
    lda #(EQ_BORDER_TEXT_N * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^(eq_border_map)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; Which one: the slot, or the visible list row.
    lda comp_col + 1
    beq in_slots
    lda comp_phase
    sec
    sbc comp_phase + 1
    ldx #(SLOTS_EQUIPMENT * 128) ; the list's, after the slots'
    bra row
in_slots:
    lda comp_col
    ldx #0
row:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; 128 bytes per row
    pha
    lsr a                       ; which is 64 words
    clc
    adc #(ITEM_BORDER_MAP + EQ_BAR_ROW0 * 32)
    sta VMADDL
    txa
    clc
    adc 1, s
    adc #.loword(eq_border_bars) ; carry was left at zero: it is a
    sta A1T0L                   ; single-bank table
    pla
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #^(eq_border_bars)
    sta A1B0
    lda #$01
    sta MDMAEN
    rts
.endproc

; The equipment screen of actor A, until the player goes back with B.
.proc equipment_screen
.a8
.i16
    sta comp_char
    stz comp_col
    stz comp_col + 1
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:eq_screen_upload
    jsr eq_compose
    jsl f:ba_t_upload
    jsr eq_bar
    jsl f:items_ppu_on          ; BG2 and BG1, the windows
wait:
    jsl f:ba_t_vblank
    ; The pad first and the DMA after. The other way around, the 1792 bytes
    ; take some ten lines and `read_pad` arrived with the pad's auto-read
    ; already over: it waited for the next frame's, each tick took two
    ; frames, and a one-frame press was lost half the time. With the pad
    ; read, the DMA still fits in vblank.
    jsl f:ba_t_pad
    jsl f:ba_t_upload
    jsr eq_bar
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    lda comp_col + 1
    beq in_slots
    jmp in_list
in_slots:
    lda title_edges
    and #PAD_UP
    beq r_no_up
    lda comp_col
    beq wait
    dec comp_col
    jmp recompose
r_no_up:
    lda title_edges
    and #PAD_DOWN
    beq r_no_down
    lda comp_col
    cmp #4
    bcs wait
    inc comp_col
    jmp recompose
r_no_down:
    lda title_edges
    and #PAD_B
    beq r_faces_a
    rtl
r_faces_a:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait
    jsr eq_list_build
    stz comp_phase
    stz comp_phase + 1
    lda #1
    sta comp_col + 1
    jmp recompose
in_list:
    lda title_edges
    and #PAD_UP
    beq l_no_up
    lda comp_phase
    beq wait2
    dec comp_phase
    lda comp_phase
    cmp comp_phase + 1
    bcs recompose
    sta comp_phase + 1
    bra recompose
l_no_up:
    lda title_edges
    and #PAD_DOWN
    beq l_no_down
    lda comp_phase
    inc a
    cmp comp_base
    bcs wait2
    sta comp_phase
    sec
    sbc comp_phase + 1
    cmp #EQ_LIST_ROWS
    bcc recompose
    inc comp_phase + 1
    bra recompose
l_no_down:
    lda title_edges
    and #PAD_B
    beq l_faces_a
    stz comp_col + 1
    bra recompose
l_faces_a:
    lda pad_a
    beq wait2
    lda pad_a_prev
    bne wait2
    jsr eq_equip
    stz comp_col + 1
recompose:
    jsr eq_compose
wait2:
    jmp wait
.endproc

