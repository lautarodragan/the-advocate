.segment "CODE"

; --- the items screen -----------------------------------------------------------
;
; `Scene_Item`: at the top the description of the highlighted item, below the
; inventory list with how many there are. It has **its own tile bank**,
; `items_tiles`: each font character in two cells, in white and in gray, and
; the text —name and two lines of description per item— goes in ASCII in
; `item_textos`. Writing a letter is two tilemap words. The geometry comes
; from `titulo.py` and `render_items` is the reference.
;
; The windows and the cursor —the System's bar— go on BG1, and belong to
; `banco_de_la_pantalla.s`: the BG2 text knows nothing about them.
;
; The list is built on entering: the items there are and that this ROM knows,
; in number order like `Game_Party`, stored as their place `k` in the
; converter's tables, in `FAR_ITEM_LIST`. How many there are, the first one
; visible and the cursor go in borrowed variables: `pick_n`, `pick_sel` and
; `title_sel`. The choice cannot be open with the menu —the menu does not
; open with a message up— so its bytes are free; `pick_cancel`, `pick_edges`
; and `pick_table` serve as scratch, and `msg_ptr` points to the text being
; written.
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
    lda item_id, x
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
otro:
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
    beq siguiente
    lda f:item_k, x
    cmp #$FF
    beq siguiente               ; one this ROM does not know how to show
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
siguiente:
    inx
    cpx #ITEMS_N
    bcc otro
    rts
.endproc

; One letter: A the character, Y the address of the upper cell and `temp + 1`
; the variant, 0 white and 1 gray. Clobbers X.
.proc glyph_pair
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; four bytes per character
    tax
    lda temp + 1
    and #$00FF
    beq blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
blanco:
    sep #$20
.a8
    lda #$80
    sta VMAIN
    rep #$20
.a16
    sty VMADDL
    lda f:item_glifo_celdas, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda f:item_glifo_celdas + 2, x
    sta VMDATAL
    sep #$20
.a8
    rts
.endproc

; One of an item's texts: X the text number —`3k` the name, `3k + 1` and
; `3k + 2` the description lines—, `pick_table` the address of the upper cell
; of its first letter and `temp + 1` the variant. First the upper cells of all
; the letters, which are contiguous in VRAM, and then the lower ones.
.proc text_write
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; how many letters
    beq ready
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #0                      ; the upper cells
    sta temp + 2
    lda pick_table
    sta VMADDL
    sep #$20
.a8
    jsr renglon
    rep #$20
.a16
    lda #2                      ; and the lower ones
    sta temp + 2
    lda pick_table
    clc
    adc #32
    sta VMADDL
    sep #$20
.a8
    jsr renglon
ready:
    rts

renglon:
    ldy #0
letra:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    clc
    adc temp + 2                ; upper or lower
    tax
    lda temp + 1
    and #$00FF
    beq en_blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
en_blanco:
    lda f:item_glifo_celdas, x
    sta VMDATAL                 ; and VRAM advances one word
    sep #$20
.a8
    iny
    tya                         ; one letter at a time: there are fewer than 256
    cmp temp
    bcc letra
    rts
.endproc

; The description of the item under the cursor, composed in `text_buf` and
; not in VRAM: it is four rows of whole cells —256 bytes— that
; `items_desc_upload` uploads in one DMA. Writing them one word at a time did
; not fit in vblank: when moving the cursor the second line came out cut off,
; because VRAM ignores what is written to it while the screen is drawing. The
; buffer is the message composer's, which does not exist with the menu open.
; With the list empty it stays blank.
ITEM_DESC_BYTES = 4 * 64

.proc items_desc_paint
.a8
.i16
    ldx #0
borrar:
    stz text_buf, x
    inx
    cpx #ITEM_DESC_BYTES
    bcc borrar
    lda pick_n
    beq ready
    lda title_sel
    jsr item_from_list
    rep #$20
.a16
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    inc a                       ; 3k + 1, the first line
    tax
    lda #(ITEM_DESC_COL * 2)
    sta pick_table              ; where it goes, in buffer bytes
    sep #$20
.a8
    phx
    jsr renglon
    plx
    inx                         ; 3k + 2, the second
    rep #$20
.a16
    lda #(128 + ITEM_DESC_COL * 2)
    sta pick_table
    sep #$20
.a8
    jsr renglon
ready:
    rts

; Text X into the buffer, starting at byte `pick_table`: each letter's upper
; cell there and the lower one 64 bytes further on.
renglon:
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; how many letters
    beq end
    ldy #0
letra:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    tax
    lda f:item_glifo_celdas, x
    pha
    lda f:item_glifo_celdas + 2, x
    ldx pick_table
    sta text_buf + 64, x
    pla
    sta text_buf, x
    inx
    inx
    stx pick_table
    sep #$20
.a8
    iny
    tya                         ; one letter at a time: there are fewer than 256
    cmp temp
    bcc letra
end:
    rts
.endproc

; Uploads the composed description: a 256-byte DMA, which fits in any
; vblank.
.proc items_desc_upload
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(ITEM_DESC_VRAM - ITEM_DESC_COL)
    sta VMADDL
    lda #.loword(text_buf)
    sta A1T0L
    lda #ITEM_DESC_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the buffer lives in bank 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Screen row A, which has to have an item: the cursor if it applies, the
; name, the colon and the quantity, in gray if A does not use it.
.proc items_row_paint
.a8
.i16
    sta pick_cancel             ; the row
    lda pick_cancel
    clc
    adc pick_sel                ; its place in the list
    pha
    jsr item_from_list
    sta pick_edges            ; its `k`
    pla
    cmp title_sel
    bne sin_cursor
    lda #1
    sta temp + 3
    lda pick_cancel
    jsl f:items_bar
sin_cursor:
    ; --- the color: gray if A does not use it ---
    lda pick_edges
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda item_uso, x
    and #1
    eor #1
    sta temp + 1
    ; --- the name ---
    lda pick_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_NOMBRE_COL
    sta pick_table
    lda pick_edges
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    tax                         ; 3k, the name
    sep #$20
.a8
    jsr text_write
    ; --- the colon and the quantity ---
    lda pick_edges
    jsr item_count
    cmp #100
    bcc cabe
    lda #99
cabe:
    stz temp + 3                ; the tens
decenas:
    cmp #10
    bcc unidades
    sbc #10                     ; the `cmp` left carry set
    inc temp + 3
    bra decenas
unidades:
    pha                         ; the units
    lda pick_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_DOS_PUNTOS_COL
    sta pick_table
    tay
    sep #$20
.a8
    lda #$3A                    ; ':'
    jsr glyph_pair
    rep #$20
.a16
    lda pick_table
    inc a
    tay
    sep #$20
.a8
    lda temp + 3
    beq sin_decenas             ; a 7 is " 7", not "07"
    clc
    adc #$30                    ; '0'
    jsr glyph_pair
sin_decenas:
    rep #$20
.a16
    lda pick_table
    inc a
    inc a
    tay
    sep #$20
.a8
    pla
    clc
    adc #$30                    ; '0'
    jmp glyph_pair
.endproc


; The visible rows, over the blank tilemap.
.proc items_rows_paint
.a8
.i16
    lda #0
row:
    pha
    clc
    adc pick_sel
    bcs termina
    cmp pick_n
    bcs termina                 ; no more items
    pla
    pha
    jsr items_row_paint
    pla
    inc a
    cmp #ITEM_FILAS
    bcc row
    rts
termina:
    pla
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
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_screen_upload
    jsr items_desc_paint
    jsr items_desc_upload
    jsr items_rows_paint
    jsl f:items_ppu_on
    lda #1
    sta menu_open
espera:
    jsr wait_vblank
    jsr items_desc_upload        ; first thing in vblank: the description
    jsr read_pad
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_arriba
    lda title_sel
    beq espera                  ; RM2k does not wrap around in a list
    dec a
    jsr mover
    bra espera
no_arriba:
    lda title_edges
    and #PAD_DOWN
    beq no_abajo
    lda title_sel
    inc a
    cmp pick_n
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda title_edges
    and #PAD_B
    beq mira_a
    lda #0
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_prev
    bne espera                  ; it was already held: not an edge
    lda pick_n
    beq espera                  ; the list is empty
    lda title_sel
    jsr item_from_list
    sta pick_edges            ; its `k`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda item_uso, x
    and #1
    beq espera                  ; grayed out: RM2k plays a sound and does nothing
    lda item_uso, x
    and #4
    beq de_switch
    ; A medicine: the actor choice, and back to the list with the cursor where
    ; it was. The choice uses `title_sel`, so it is saved.
    lda title_sel
    pha
    lda pick_sel
    pha
    stz pick_cancel             ; for a medicine, the one in `pick_edges`
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
    bcc cursor_listo
    lda pick_n
    dec a
    sta title_sel
    bra cursor_listo
empty:
    stz title_sel
cursor_listo:
    lda title_sel
    cmp pick_sel
    bcs vista_lista
    sta pick_sel
vista_lista:
    lda #$80
    sta INIDISP
    jsl f:items_screen_upload
    jsr items_desc_paint
    jsr items_desc_upload
    jsr items_rows_paint
    jsl f:items_ppu_on
    jmp espera
de_switch:
    ; A switch item: `ConsumeItemUse` if it has uses, the switch turned on and
    ; straight to the map. `set_switch` asks for the page refresh, which is
    ; the `SetNeedRefresh(true)` over there.
    lda item_uso, x
    and #2
    beq sin_gastar
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
    lda item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
sin_gastar:
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

; The cursor to the place given in A. If it stays in view the cursor moves and
; the description changes, inside vblank; if not, the list scrolls and is
; repainted whole with the screen off, which is one black frame.
mover:
    pha
    stz temp + 3
    lda title_sel
    sec
    sbc pick_sel
    jsl f:items_bar
    pla
    sta title_sel
    cmp pick_sel
    bcc sube_la_vista
    sec
    sbc pick_sel
    cmp #ITEM_FILAS
    bcs baja_la_vista
    lda #1
    sta temp + 3
    lda title_sel
    sec
    sbc pick_sel
    jsl f:items_bar
    jmp items_desc_paint
sube_la_vista:
    lda title_sel
    sta pick_sel
    bra repintar
baja_la_vista:
    lda title_sel
    sec
    sbc #(ITEM_FILAS - 1)
    sta pick_sel
repintar:
    lda #$80
    sta INIDISP
    jsl f:items_screen_upload  ; the blank tilemap, and the rest along with it
    jsr items_desc_paint
    jsr items_desc_upload
    jsr items_rows_paint
    lda #$0F
    sta INIDISP
    rts
.endproc
