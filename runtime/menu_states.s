; In `FAR3`, like the party panel's other bodies: every door in is a `jsl`.
.segment "FAR3"
.a8
.i16

; --- the party's conditions on the menus ---------------------------------------
;
; Where the pause menu's rows, the actor choice's and the skills screen's
; status line say "Normal", RM2k's `Window_Base::DrawActorState` writes the
; condition the actor shows —`GetSignificantState`, `menu_state_of`— in
; that condition's colour. Since 2026-11-01.
;
; **On the party panel** "Normal" is baked in the row's fixed block, and
; the condition is a strip over its cells —`menu_state_paint`—: they are
; blanked, its name is composed in white with `tl_strip` like the actor's,
; and then the stage it was composed in is **recoloured** —each glyph row to
; the entry its ink says, the shadow to the shadow, for the cells to go in
; palette 1, the disabled commands'— and **moved a pixel right**, because
; "Normal" is two pixels into its cell and a strip starts one in. It goes up
; again and its cells are written with the ink's palette. Which entries
; each colour gets is the converter's decision: see `StateInks` in
; `rm2k-snes-screens`, which also says why one entry per colour and not the
; System's gradient. A condition already composed while the screen is up is
; not composed again: its tiles are pointed to again, and the converter
; counts tiles for four of them.
;
; **The actor choice draws itself again** when a use changes the condition
; a row shows —a revival, a cure—, as `Scene_ActorTarget` refreshes its
; window: composing does not fit in the vblank. See `menu_states_changed`.
;
; **The skills screen** writes the name by reference from the same table,
; in BG2's palette `SK_STATE_PALETTE` with the System colour's gradient,
; which `menu_state_ink` uploads when the screen is drawn.

STATE_INK_BYTES = 13            ; per ink: the twelve glyph rows' entries and the shadow's

.pushseg
.segment "FARBSS"
st_member:   .res 1             ; scratch of `menu_state_paint`: the member,
st_id:       .res 1             ; the condition it shows,
st_cell:     .res 2             ; the first cell of its text,
st_t:        .res 2             ; its strip's first tile,
st_k:        .res 2             ; how many columns,
st_attr:     .res 2             ; and the palette, in a tilemap word's bits
st_ink:      .res 2             ; its ink's rows, inside `state_ink_rows`
st_y:        .res 2             ; the stage row being recoloured,
st_x:        .res 2             ; its first byte,
st_nz:       .res 1             ; the pixels of a tile row with ink or shadow,
st_sh:       .res 1             ; the shadow's,
st_inked:    .res 1             ; and the ink's
st_tm:       .res 4             ; per bit plane, $FF if the row's entry has it,
st_um:       .res 4             ; and the shadow's,
st_sm:       .res 4             ; and the white's shadow's
st_best:     .res 2             ; `menu_state_of`: the priority shown, plus one
st_pick:     .res 2             ; and its condition
st_try:      .res 2
; The conditions composed while the screen is up: their number, first tile
; and columns. `menu_states_forget` empties it with the bank.
STATE_KEPT = 4
st_kept_n:   .res 2
st_kept_id:  .res STATE_KEPT
st_kept_t:   .res 2 * STATE_KEPT
st_kept_k:   .res 2 * STATE_KEPT
; The condition each member's row shows, which the actor choice compares
; after a use.
far_menu_shown: .res MENU_ROWS_PARTY
.popseg

.assert STATE_NAMES_N >= STATES_N, error, "the conditions' names do not cover every condition"
.assert STATE_NAME_W >= MENU_STATE_COLS, error, "a condition's padded name is shorter than its cells: tl_strip would cut it by letters"

; The condition actor A8 shows, A8 on return with Z: 0 is none, "Normal". The dead
; one at zero HP —it is not one of the places, see party_states.s—, and
; otherwise the one held of highest priority, the later on a tie —the
; places go in LDB order—: `GetSignificantState`. Any data bank; keeps it.
; Clobbers X and Y.
.proc menu_state_of
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    rep #$20
.a16
    and #$00FF
    pha
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    bne alive
    pla
    lda #ACT_ST_DEAD
    cmp #STATES_N
    bcc done
    lda #0                      ; a game without conditions: nobody dies of one
    bra done
alive:
    pla
    asl a
    asl a
    asl a                       ; ACT_ST_BYTES per actor
    tax
    stz .loword(st_best)
    stz .loword(st_pick)
    ldy #ST_PLACES_MAP
place:
    lda .loword(far_act_states), x
    and #$00FF
    beq picked                  ; the empty ones go at the end
    cmp #STATES_N
    bcs next
    sta .loword(st_try)
    phx
    tax
    lda f:state_priority, x
    and #$00FF
    inc a
    plx
    cmp .loword(st_best)
    bcc next                    ; `>=`: the later one on a tie
    sta .loword(st_best)
    lda .loword(st_try)
    sta .loword(st_pick)
next:
    inx
    inx
    dey
    bne place
picked:
    lda .loword(st_pick)
done:
    sep #$20
.a8
    plb
    cmp #0                      ; Z from the condition and not from the `plb`
    rtl
.endproc
.assert ACT_ST_BYTES = 8, error, "menu_state_of multiplies by eight"

; No condition composed: right after the bank goes up, which starts its
; free tiles over. Any data bank.
.proc menu_states_forget
.a8
.i16
    rep #$20
.a16
    lda #0
    sta f:st_kept_n
    sep #$20
.a8
    rtl
.endproc

; Whether a member's row would show another condition than it shows: A8
; nonzero if so, with Z. After a use on the actor choice, which draws itself
; again then. Any data bank.
.proc menu_states_changed
.a8
.i16
    lda #0
member:
    cmp party_n
    bcs same
    cmp #MENU_ROWS_PARTY
    bcs same
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    jsl f:menu_state_of
    sta f:st_try
    pla
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:far_menu_shown, x
    cmp f:st_try
    bne changed
    pla
    inc a
    bra member
changed:
    pla
    lda #1
    rtl
same:
    lda #0
    rtl
.endproc

; The condition of member X's row, actor A8, whose first tilemap cell is Y:
; nothing if it shows none —the fixed block's "Normal" stays—; otherwise
; Normal's cells blanked and the condition's name over them, in its colour.
; With the screen off, after the row's fixed block. Any data bank; keeps it.
; Clobbers A, X and Y.
.proc menu_state_paint
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    txa
    sta .loword(st_member)
    rep #$20
.a16
    tya
    clc
    adc #MENU_STATE_OFS
    sta .loword(st_cell)
    sep #$20
.a8
    pla
    jsl f:menu_state_of
    sta .loword(st_id)
    rep #$20
.a16
    lda .loword(st_member)
    and #$00FF
    tax
    sep #$20
.a8
    lda .loword(st_id)
    sta .loword(far_menu_shown), x
    bne shown
    jmp done
shown:
    ; Normal's cells, blank: two cell rows from the first.
    lda #$80
    sta f:VMAIN
    rep #$20
.a16
    lda .loword(st_cell)
    jsr blank
    lda .loword(st_cell)
    clc
    adc #32
    jsr blank
    lda .loword(st_id)
    and #$00FF
    tax
    sep #$20
.a8
    lda f:state_name_n, x
    bne named
    jmp done                    ; RM2k writes its empty name
named:
    ; Its ink: its rows and the cells' palette.
    lda f:state_ink, x
    rep #$20
.a16
    and #$00FF
    pha
    asl a
    tax
    lda f:state_ink_attr, x
    sta .loword(st_attr)
    pla
    sta .loword(st_ink)
    asl a                       ; times STATE_INK_BYTES, thirteen
    adc .loword(st_ink)         ; three times
    asl a
    asl a                       ; twelve times
    adc .loword(st_ink)         ; thirteen
    sta .loword(st_ink)
    sep #$20
.a8
    ; Composed already while the screen is up?
    ldx #0
seek:
    cpx .loword(st_kept_n)
    bcs compose
    lda .loword(st_kept_id), x
    cmp .loword(st_id)
    beq kept
    inx
    bra seek
kept:
    rep #$20
.a16
    txa
    asl a
    tax
    lda .loword(st_kept_t), x
    sta .loword(st_t)
    lda .loword(st_kept_k), x
    sta .loword(st_k)
    jmp place

.a8
compose:
    ; Its padded name, from `state_names`: `STATE_NAME_W` bytes per
    ; condition.
    lda .loword(st_id)
    sta f:WRMPYA
    lda #STATE_NAME_W
    sta f:WRMPYB
    nop                         ; eight cycles for the product
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    clc
    adc #.loword(state_names)
    sta msg_ptr
    sep #$20
.a8
    lda #^state_names
    sta msg_ptr + 2
    ldy .loword(st_cell)
    lda #STATE_NAME_W           ; no fewer letters than its cells: see the .assert
    jsl f:tl_strip + FAST       ; in white, on palette 0
    rep #$20
.a16
    lda TL_STRIP_K
    bne composed
    jmp done16                  ; no room: the converter measured it does not happen
composed:
    ; A pixel to the right reaches one more column when the last letter's
    ; shadow ends at the cell's edge: `tl_strip` counted `TL_X + 6`.
    lda TL_X
    clc
    adc #7
    lsr a
    lsr a
    lsr a
    sta .loword(st_k)
    sec
    sbc TL_STRIP_K
    asl a
    clc
    adc TL_STRIP_NEXT
    cmp TL_STRIP_OVER
    bcc more
    lda TL_STRIP_K              ; no room for it: the converter measured it
    sta .loword(st_k)           ; does not happen
    bra counted
more:
    sta TL_STRIP_NEXT
counted:
    lda .loword(st_k)
    sta TL_STRIP_K
    lda TL_STRIP_T
    sta .loword(st_t)
    jsr recolour
    jsr shift
    jsl f:tl_strip_upload
    ; Kept, if there is room.
    lda .loword(st_kept_n)
    cmp #STATE_KEPT
    bcs place
    tax
    inc a
    sta .loword(st_kept_n)
    sep #$20
.a8
    lda .loword(st_id)
    sta .loword(st_kept_id), x
    rep #$20
.a16
    txa
    asl a
    tax
    lda .loword(st_t)
    sta .loword(st_kept_t), x
    lda .loword(st_k)
    sta .loword(st_kept_k), x

place:
    ; Its cells, the strip's columns with the ink's palette: the upper
    ; tiles on the first row and the lower ones on the second.
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    rep #$20
.a16
    lda .loword(st_cell)
    sta f:VMADDL
    lda .loword(st_t)
    jsr cells
    lda .loword(st_cell)
    clc
    adc #32
    sta f:VMADDL
    lda .loword(st_t)
    inc a
    jsr cells
done16:
    sep #$20
.a8
done:
    plb
    rtl

; MENU_STATE_COLS blank cells from cell A16.
.a16
blank:
    sta f:VMADDL
    ldx #MENU_STATE_COLS
    lda #0
blank_cell:
    sta f:VMDATAL
    dex
    bne blank_cell
    rts

; `st_k` cells from tile A16, every other one: the bank's priority, as
; `tl_strip_place`, and the ink's palette.
cells:
    ora #$2000
    ora .loword(st_attr)
    ldx .loword(st_k)
    beq placed
word:
    sta f:VMDATAL
    inc a
    inc a
    dex
    bne word
placed:
    rts

; The stage's `st_k` columns, recoloured: in each of its sixteen pixel rows,
; a pixel with the shadow's entry of palette 0 takes the ink's shadow, and
; any other lit one the entry the ink gives that glyph row —the glyph starts
; `SCR_TEXT_Y` rows down—. The rows the glyph does not reach have only
; shadow. A column is a pair of tiles, the upper one's 32 bytes and then the
; lower one's; a tile row is two bytes for planes 0 and 1 and, sixteen
; further, two for planes 2 and 3. A16 in and out.
recolour:
    ; The shadow's planes, for the whole strip.
    lda .loword(st_ink)
    tax
    sep #$20
.a8
    lda f:state_ink_rows + 12, x
    ldy #.loword(st_um)
    jsr masks
    lda #SLOT_SHADOW            ; and the white's, which it replaces
    ldy #.loword(st_sm)
    jsr masks
    rep #$20
.a16
    stz .loword(st_y)
row:
    ; The row's entry: its glyph row's, or none.
    lda .loword(st_y)
    sec
    sbc #SCR_TEXT_Y
    cmp #12
    bcs no_ink                  ; above or below the glyph: only shadow
    adc .loword(st_ink)         ; the carry is clear
    tax
    sep #$20
.a8
    lda f:state_ink_rows, x
    bra entry
no_ink:
    sep #$20
    lda #0
entry:
    ldy #.loword(st_tm)
    jsr masks
    ; Its first byte: the tile, and the row in it.
    rep #$20
.a16
    lda .loword(st_y)
    and #7
    asl a
    sta .loword(st_x)
    lda .loword(st_y)
    and #8
    asl a
    asl a                       ; the lower tile, 32 bytes on
    ora .loword(st_x)
    clc
    adc #TL_STAGE
    tax
    ldy .loword(st_k)
    sep #$20
.a8
column:
    lda a:0, x
    ora a:1, x
    ora a:16, x
    ora a:17, x
    bne lit
    jmp empty
lit:
    sta .loword(st_nz)
    ; The pixels whose four planes are the shadow's entry: where none
    ; differs from its mask.
    lda a:0, x
    eor .loword(st_sm)
    eor #$FF
    sta .loword(st_sh)
    lda a:1, x
    eor .loword(st_sm) + 1
    eor #$FF
    and .loword(st_sh)
    sta .loword(st_sh)
    lda a:16, x
    eor .loword(st_sm) + 2
    eor #$FF
    and .loword(st_sh)
    sta .loword(st_sh)
    lda a:17, x
    eor .loword(st_sm) + 3
    eor #$FF
    and .loword(st_sh)
    and .loword(st_nz)
    sta .loword(st_sh)
    eor .loword(st_nz)
    sta .loword(st_inked)
    ; Each plane: the ink's pixels where the row's entry has the bit, and
    ; the shadow's where the shadow's has it.
    and .loword(st_tm)
    sta a:0, x
    lda .loword(st_sh)
    and .loword(st_um)
    ora a:0, x
    sta a:0, x
    lda .loword(st_inked)
    and .loword(st_tm) + 1
    sta a:1, x
    lda .loword(st_sh)
    and .loword(st_um) + 1
    ora a:1, x
    sta a:1, x
    lda .loword(st_inked)
    and .loword(st_tm) + 2
    sta a:16, x
    lda .loword(st_sh)
    and .loword(st_um) + 2
    ora a:16, x
    sta a:16, x
    lda .loword(st_inked)
    and .loword(st_tm) + 3
    sta a:17, x
    lda .loword(st_sh)
    and .loword(st_um) + 3
    ora a:17, x
    sta a:17, x
empty:
    rep #$21                    ; and the carry clear
.a16
    txa
    adc #64                     ; the next column
    tax
    sep #$20
.a8
    dey
    beq columns_done
    jmp column
columns_done:
    rep #$20
.a16
    inc .loword(st_y)
    lda .loword(st_y)
    cmp #16
    bcs rows_done
    jmp row
rows_done:
    rts

; The four planes' masks of the entry in A8, at Y: $FF for each bit it
; has. A8.
.a8
masks:
    ldx #4
mask:
    lsr a
    pha
    lda #0
    bcc clear
    lda #$FF
clear:
    sta a:0, y
    pla
    iny
    dex
    bne mask
    rts

; The stage's `st_k` columns a pixel to the right: in each pixel row and
; each plane, every byte rotated right, the bit that leaves a column going
; in at the left of the next. The first column takes a blank pixel. A16 in
; and out.
.a16
shift:
    stz .loword(st_x)           ; the pixel row's first byte in a column
pixel_row:
    lda #0
    jsr rotate
    lda #1
    jsr rotate
    lda #16
    jsr rotate
    lda #17
    jsr rotate
    ; The next pixel row: two bytes on, or the lower tile's first, past
    ; the upper one's planes 2 and 3.
    lda .loword(st_x)
    inc a
    inc a
    bit #15
    bne same_tile
    clc
    adc #16
same_tile:
    sta .loword(st_x)
    cmp #48
    bcc pixel_row
    rts

; One plane's byte of the pixel row, A16 bytes from its first, through the
; columns. A16 in and out.
rotate:
    clc
    adc .loword(st_x)
    adc #TL_STAGE
    tax
    ldy .loword(st_k)
    sep #$20
.a8
    clc
rotate_one:
    ror a:0, x
    php                         ; the bit that goes on to the next column
    rep #$20
.a16
    txa
    clc
    adc #64
    tax
    plp
.a8
    dey
    bne rotate_one
    rep #$20
.a16
    rts
.endproc

; The skills screen's condition colour, `menu_state_of`'s ink for the actor
; in A8, into BG2's palette `SK_STATE_PALETTE`: the System colour's twelve
; rows and its shadow, the text screens' layout. With the screen off and the
; data bank at 0, from `sk_upload`. Clobbers A, X and Y.
.proc menu_state_ink
.a8
.i16
    jsl f:menu_state_of
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:state_ink, x
    rep #$20
.a16
    and #$00FF
    sta f:st_try
    asl a                       ; 26 bytes per ink
    adc f:st_try
    asl a
    asl a
    adc f:st_try
    asl a
    clc
    adc #.loword(state_ink_cgram)
    tax
    sep #$20
.a8
    lda #(SK_STATE_PALETTE * 16 + 1)
    sta CGADD
    ldy #(2 * STATE_INK_BYTES)
word:
    lda f:state_ink_cgram & $FF0000, x
    sta CGDATA
    inx
    dey
    bne word
    rtl
.endproc
