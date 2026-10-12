.segment "CODE"

; --- the items screen -----------------------------------------------------------
;
; `Scene_Item`: at the top the description of the highlighted item, below the
; inventory list with how many there are. The text —name and two lines of
; description per item— goes in ASCII in `item_texts`. The geometry comes
; from `rm2k-snes-screens`, whose `render` is the reference.
;
; The screen is written **whole** on each change, like the equipment and
; shop screens, with `text_screens.s`'s writers; what that means —only the
; rows that changed get composed, and the screen goes from one to the other
; at once— is `text_layer.s`. So moving the cursor or scrolling the list
; leaves the screen on: until 2026-09-30 a scroll repainted the list
; straight into VRAM with the screen off, which was a black frame and the
; windows uploaded again. Until 2026-10-03 the font was a tile bank of its
; own, each letter in two cells.
;
; The windows and the cursor —the System's bar— go on BG1, and belong to
; `screen_bank.s`: the BG2 text knows nothing about them.
;
; The list is built on entering: the items there are and that this ROM knows,
; in number order like `Game_Party`, stored as their place `k` in the
; converter's tables, in `FAR_ITEM_LIST`. How many there are, the first one
; visible and the cursor go in borrowed variables: `pick_n`, `pick_sel` and
; `title_sel`. The choice cannot be open with the menu —the menu does not
; open with a message up— so its bytes are free; `pick_cancel` and
; `pick_edges` serve as scratch, and `pick_table` is where the text writers
; write.
FAR_ITEM_LIST = $2A00

; A: a place in the list. Returns with A = its `k`. Only A.
.proc item_from_list
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ITEM_LIST
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: a `k`. Returns with A = how many of that item there are. Clobbers X.
.proc item_count
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; The list, into `FAR_ITEM_LIST`, and how many there are into `pick_n`.
.proc items_build_list
.a8
.i16
    stz pick_n
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
    beq next                    ; one this ROM does not know how to show
    pha
    rep #$20
.a16
    lda pick_n
    and #$00FF
    clc
    adc #FAR_ITEM_LIST
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    inc pick_n
next:
    inx
    cpx #ITEMS_N
    bcc other
    rts
.endproc


; The whole screen's text, written to the text layer: the description of
; the item under the cursor and the visible rows. With the list empty it stays blank.
.proc items_compose
.a8
.i16
    lda #255
    sta comp_dup + 3            ; `scr_text` without a cap
    jsr scr_clear
    lda pick_n
    beq ready
    ; --- the description: texts 3k + 1 and 3k + 2, in white ---
    lda title_sel
    jsr item_from_list
    rep #$20
.a16
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    inc a
    tax
    lda #SCR_DESC_POS
    sta pick_table
    sep #$20
.a8
    stz temp + 1
    phx
    jsr scr_text
    plx
    inx
    rep #$20
.a16
    lda #(SCR_DESC_POS + 128)
    sta pick_table
    sep #$20
.a8
    jsr scr_text
    ; --- the visible rows ---
    lda #0
row:
    pha
    clc
    adc pick_sel
    bcs ends
    cmp pick_n
    bcs ends                    ; no more items
    pla
    pha
    jsr items_row_paint
    pla
    inc a
    cmp #ITEM_ROWS
    bcc row
    rts
ends:
    pla
ready:
    rts
.endproc

; Screen row A, which has to have an item: the name, the colon and the
; quantity, in gray if A does not use it. The cursor is not text: see
; `items_bar`.
.proc items_row_paint
.a8
.i16
    sta pick_cancel             ; the row
    clc
    adc pick_sel                ; its place in the list
    jsr item_from_list
    sta pick_edges              ; its `k`
    ; --- the color: gray if A does not use it ---
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:item_use, x
    and #1
    eor #1
    sta temp + 1
    ; --- the name, text 3k ---
    lda pick_cancel
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; two rows of cells, 128 bytes
    clc
    adc #ITEM_LIST_POS
    pha                         ; the row, for the quantity
    clc
    adc #(ITEM_NAME_COL * 2)
    sta pick_table
    lda pick_edges
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    jsr scr_text
    ; --- the colon and the quantity, in two digits ---
    rep #$20
.a16
    pla
    clc
    adc #SCR_TWO_POINTS
    sta pick_table
    sep #$20
.a8
    lda #$3A                    ; ':'
    jsr scr_glyph
    lda pick_edges
    jsr item_count
    cmp #100
    bcc fits
    lda #99
fits:
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jmp scr_number
.endproc

; The cursor on its row, if the list has any.
.proc items_bar_on
.a8
.i16
    lda pick_n
    beq none
    lda #1
    sta temp + 3
    lda title_sel
    sec
    sbc pick_sel
    jsl f:items_bar
none:
    rts
.endproc

; The whole screen with the screen off: the bank, the windows, the text and
; the cursor. It is how the screen is entered, and how it comes back from the
; actor choice, which used the VRAM.
.proc items_view
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_screen_upload
    jsr items_compose
    jsr scr_upload
    jsr items_bar_on
    jsl f:items_ppu_on
    rts
.endproc

; The items screen, until the player goes back with B —A = 0, to the menu— or
; uses an item —A = 1: RM2k goes straight back to the map,
; `PopUntil(Scene::Map)`—.
.proc items_screen
.a8
.i16
    jsr items_build_list
    stz title_sel
    stz pick_sel
    jsr items_view
    lda #1
    sta menu_open
wait:
    jsr wait_vblank
    jsr read_pad                ; the pad before the DMA: see the equipment screen
    jsr scr_upload
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_up
    lda title_sel
    beq wait                    ; RM2k does not wrap around in a list
    dec a
    jsr move
    bra wait
no_up:
    lda title_edges
    and #PAD_DOWN
    beq no_down
    lda title_sel
    inc a
    cmp pick_n
    bcs wait
    jsr move
    bra wait
no_down:
    lda title_edges
    and #PAD_B
    beq check_a
    lda #0
    rts
check_a:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                    ; it was already held: not an edge
    lda pick_n
    beq wait                    ; the list is empty
    lda title_sel
    jsr item_from_list
    sta pick_edges              ; its `k`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:item_use, x
    and #1
    beq wait                    ; grayed out: RM2k plays a sound and does nothing
    lda f:item_use, x
    and #4
    beq from_switch
    ; A medicine: the actor choice, and back to the list with the cursor where
    ; it was. The choice uses `title_sel`, so it is saved.
    lda title_sel
    pha
    lda pick_sel
    pha
    jsr target_screen
    pla
    sta pick_sel
    pla
    sta title_sel
    ; The list again, which is `Scene_Item::Continue`: the medicine may have
    ; been used up entirely. A cursor left outside goes to the last one, the
    ; `SetIndex(min(index, item_max - 1))` over there, and the view follows it.
    jsr items_build_list
    lda pick_n
    beq empty
    lda title_sel
    cmp pick_n
    bcc cursor_ready
    lda pick_n
    dec a
    sta title_sel
    bra cursor_ready
empty:
    stz title_sel
cursor_ready:
    lda title_sel
    cmp pick_sel
    bcs view_list
    sta pick_sel
view_list:
    jsr items_view
    jmp wait
from_switch:
    ; A switch item: `ConsumeItemUse` if it has uses, the switch turned on and
    ; straight to the map. `set_switch` asks for the page refresh, which is
    ; the `SetNeedRefresh(true)` over there.
    lda f:item_use, x
    and #2
    beq no_consume
    lda pick_edges
    jsr item_count
    dec a
    pha
    lda pick_edges
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
no_consume:
    lda pick_edges
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_switch, x        ; lives in RODATA: see the converter
    sta temp
    sep #$20
.a8
    lda #1
    jsr set_switch
    lda #1
    rts

; The cursor to the place given in A, and the view following it. The bar moves
; now, inside this vblank —when the list scrolls it stays on the same row—,
; and the text is recomposed for the next vblank's upload: the screen stays
; on.
move:
    pha
    stz temp + 3
    lda title_sel
    sec
    sbc pick_sel
    jsl f:items_bar             ; the bar off
    pla
    sta title_sel
    cmp pick_sel
    bcs not_above
    sta pick_sel                ; it scrolls up
    bra moved
not_above:
    sec
    sbc pick_sel
    cmp #ITEM_ROWS
    bcc moved
    lda title_sel
    sec
    sbc #(ITEM_ROWS - 1)
    sta pick_sel                ; it scrolls down
moved:
    jsr items_bar_on
    jmp items_compose
.endproc
