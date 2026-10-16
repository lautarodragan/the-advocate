.pushseg
.segment "FAR3"

; --- the System's cursor on the pause menu's commands and on the slots -------
;
; `Window_Command`'s and `Window_SaveFile`'s cursor: the System's
; rectangle, on BG1 at 8bpp with the actor choice's tiles and colours, like
; the menu's bar over the party —see `menu_bar` in `actor_choice.s`—. Both
; screens have nothing else on BG1, so erasing it is writing zeros. Their
; text, on BG2, goes over it: the bank of the slots and the menu carries the
; priority bit. The geometry is `MENU_CMD_BAR` and `slot_bar` in
; `rm2k-snes-screens`, whose `render` is the reference, and where each one
; starts on each row is a table the converter writes: `menu_cursor_vram`
; and `slot_bar_vram`.
;
; Until 2026-10-16 both were a ">" of the bank's text: two cells written
; next to the command, and two more variants of each slot's row.
;
; It does not blink: the screens that already drew the System's cursor —the
; items, the equipment, the shop, the actor choice— draw the first of its two
; drawings, and these do the same. A Blurred Line's System has both the same.

; The command cursor on command A: `temp + 3` at 1 paints it and at 0
; erases it. Called with `jsl` and the data bank at 0, with the screen off
; or inside the vblank. It clobbers `temp` through `temp + 2`, X and Y.
.proc menu_cmd_cursor
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:menu_cursor_vram, x
    sta temp
    sep #$20
.a8
    lda #(MENU_CMD_COLS * 2)
    sta temp + 2
    ldx #MENU_CMD_ROWS
    ldy #.loword(menu_cmd_cells)
    lda #^menu_cmd_cells
    jmp bg1_rect                ; its `rtl` is this one's
.endproc

; The slot cursor on slot A, the same way.
.proc slot_cursor
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:slot_bar_vram, x
    sta temp
    sep #$20
.a8
    lda #(SLOT_BAR_COLS * 2)
    sta temp + 2
    ldx #SLOT_BAR_ROWS
    ldy #.loword(slot_bar_cells)
    lda #^slot_bar_cells
    jmp bg1_rect
.endproc

; A rectangle of BG1's tilemap, from the cell at word `temp`: X rows of
; `temp + 2` bytes each, from the cells at A:Y if `temp + 3` is 1, or zeros
; if it is 0. One DMA per row: the source is contiguous, and a DMA leaves
; its address where it ended, so it is set once.
.proc bg1_rect
.a8
.i16
    sta A1B0
    lda #$80
    sta VMAIN
    lda #$18
    sta BBAD0
    lda temp + 3
    beq erase
    lda #$01                    ; two registers, advancing
    bra source
erase:
    lda #^zero                  ; a fixed source: zeros, `bank1.s`
    sta A1B0
    ldy #.loword(zero)
    lda #$09                    ; two registers, without advancing
source:
    sta DMAP0
    sty A1T0L
row:
    rep #$20
.a16
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda temp + 2
    and #$00FF
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    dex
    bne row
    rtl
.endproc

.popseg
