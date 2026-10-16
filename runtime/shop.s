.segment "FAR"

; --- the shop ------------------------------------------------------------------
;
; `Scene_Shop`, opened by `OP_SHOP` from the interpreter, like saving: the
; screen blocks inside the page, it costs no tick, and on exit the map comes
; back and the page goes on. It is a text screen —see "the text
; screens"— and `shop_screen` of `rm2k-snes-screens` is the reference. The
; System's windows and the bar go on BG1, with their own base: see
; `ti_screen_upload` and `ti_windows`, and the stage's `ti_windows`. What
; it sells goes as `k` in `FAR_SHOP`; the selling list, in
; `FAR_ITEM_LIST`.
;
; The scratch space, borrowed from the message compositor:
;   ti_modo      is comp_col       ; TI_MAIN ... TI_SOLD
;   ti_type      is comp_col + 1   ; 0 buys and sells, 1 buys, 2 sells
;   ti_set       is comp_phase      ; the message set, 0 to 2
;   ti_resaludo  is comp_phase + 1  ; whether it already went back to the main one
;   ti_elegido   is comp_base      ; the cursor
;   ti_arriba    is comp_base + 1  ; the first visible one of the list
;   ti_n         is comp_mask      ; how many there are in the mode's list
;   ti_nt        is comp_mask + 1  ; how many the shop sells
;   ti_count     is comp_color     ; the quantity being chosen
;   ti_max       is comp_row      ; and up to how many
;   ti_timer     is comp_glyph     ; the frames of the "done"
;   ti_pos       is comp_glyph + 1 ; two bytes: where the digit goes
;   ti_num       is comp_or01      ; three bytes: a 24-bit number
; What the shop sells, one `k` per word since 2026-10-15. It borrows the
; battle's state, as the skills screen does: a shop opens from a map page and
; no battle is alive while it is open. Until then it was 256 bytes of its own
; after the item list, which took them over when its `k` went to a word. It
; skips the battle's first bytes —`BA_RESULT`, which the Game Over reads
; after the battle— and goes where the combatants go.
FAR_SHOP = FAR_BATTLE + 96
SHOP_MAX = 255                  ; the opcode's count is a byte
.assert FAR_SHOP + 2 * SHOP_MAX <= BA_BATTLE_END, error, "the shop's list overflows the battle's state"
TI_MAIN = 0
TI_BUY = 1
TI_COUNT_BUY = 2
TI_BOUGHT = 3
TI_SELL = 4
TI_COUNT_SALE = 5
TI_SOLD = 6

; A: a place in the mode's list. Returns with X = its `k`. Only A and X.
.proc ti_k_of
.a8
.i16
    pha
    lda comp_col
    cmp #TI_SELL
    bcs from_sale
    pla
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:$7E0000 + FAR_SHOP, x
    tax
    sep #$20
.a8
    rts
from_sale:
    pla
    jsl f:ba_t_list
    rts
.endproc

; The item the cursor highlights, in `eq_id`, and its `k` in X.
.proc ti_item
.a8
.i16
    lda comp_base
    jsr ti_k_of
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x            ; outside bank 0: `f:` only indexes with X
    sta comp_or23
    txa
    lsr a
    tax                         ; X = k again
    sep #$20
.a8
    rts
.endproc

; `ti_item` and `eq_read` for the shop's party, which lives in `FAR3`, out
; of `jsr`'s reach: see shop_party.s.
ti_item_far:
    jsr ti_item
    rtl
eq_read_far:
    jsr eq_read
    rtl

; The price of X's `k`, in `ti_num`, halved if selling.
.proc ti_price
.a8
.i16
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_price, x         ; outside bank 0: `f:` only indexes with X
    sta comp_or01
    txa
    lsr a
    tax                         ; X = k again
    sep #$20
.a8
    stz comp_or01 + 2
    lda comp_col
    cmp #TI_SELL
    bcc ready
    rep #$20
.a16
    lsr comp_or01
    sep #$20
.a8
ready:
    rts
.endproc

; Is there enough gold for X's `k`, and does it have fewer than 99? Z=0 if it
; can be bought. `Window_ShopBuy::CheckEnable`.
.proc ti_can
.a8
.i16
    phx
    jsr ti_price
    plx
    ; gold >= price, 24 bits
    lda gold + 2
    bne reaches
    rep #$20
.a16
    lda gold
    cmp comp_or01
    sep #$20
.a8
    bcc no
reaches:
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x            ; outside bank 0: `f:` only indexes with X
    sta comp_or23
    txa
    lsr a
    tax                         ; X = k again
    sep #$20
.a8
    jsr eq_inv_point
    lda WMDATA
    cmp #ITEM_MAX
    bcs no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A 24-bit number from `ti_num` —it is lost—, right-aligned with its last digit
; at `ti_pos`, in the variant from `temp + 1`. It is divided by ten one byte at
; a time, like the menu's gold. The digits come out from the last one up and
; go on the stack, and from there to the text layer as one run, which it
; right-aligns: with the variable-width font a digit is not a cell any more.
.proc scr_number24
.a8
.i16
    ldy #0                      ; how many digits
digit:
    stz temp + 3                ; the remainder carried along
    ldx #2
divide_it:
    lda comp_or01, x
    sta WRDIVL
    lda temp + 3
    sta WRDIVH
    lda #10
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta comp_or01, x
    lda RDMPYL
    sta temp + 3
    dex
    bpl divide_it
    lda temp + 3
    clc
    adc #('0' - ' ')            ; a letter of the font
    pha
    iny
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    bne digit
    lda comp_or01 + 2
    bne digit
    tya
    sta f:$7E0000 + TL_DIG_N
    ldx #0
unstack:
    pla                         ; the first digit is on top
    sta f:$7E0000 + TL_DIG, x
    inx
    dey
    bne unstack
    rep #$20
.a16
    lda comp_glyph + 1
    sta pick_table
    sep #$20
.a8
    jsl f:tl_right + FAST
    rts
.endproc

; How many of item `eq_id` the party has equipped: `GetEquippedItemCount`.
; Returns in `scr_value`.
.proc ti_held
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    sta comp_or01                  ; the one being looked for
    stz comp_dup
    sep #$20
.a8
    lda #0
member:
    cmp party_n
    bcs ready
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    sta comp_char
    lda #0
slot:
    pha
    jsr eq_read
    rep #$20
.a16
    lda comp_or23
    cmp comp_or01
    bne other
    inc comp_dup
other:
    sep #$20
.a8
    pla
    inc a
    cmp #5
    bcc slot
    pla
    inc a
    bra member
ready:
    rep #$20
.a16
    lda comp_or01
    sta comp_or23
    sep #$20
.a8
    rts
.endproc

; A: the message number of the shop's set. X = the text of its first line; the
; second is the next one.
.proc ti_text_of
.a8
.i16
    sta temp + 3
    lda comp_phase
    asl a
    asl a
    asl a                       ; times 8
    clc
    adc comp_phase
    adc comp_phase
    adc comp_phase               ; times 11
    clc
    adc temp + 3
    rep #$20
.a16
    and #$00FF
    asl a                       ; two lines each
    clc
    adc #TI_TEXT
    tax
    sep #$20
.a8
    rts
.endproc

; A != 0 if the main mode's greeting —or the re-greeting— takes two lines: the
; commands go below, so they start one lower. It is the length of the second
; line.
.proc ti_two_lines
.a8
.i16
    lda comp_phase + 1
    jsr ti_text_of
    inx
    lda f:item_txt_n, x
    rts
.endproc

; Message A of the shop's set, in the bottom window: in the main mode both
; lines, above the commands; in the other modes, just one, which is what fits
; in their window —those modes' messages are one line long, and the converter
; checks it—.
.proc ti_message
.a8
.i16
    jsr ti_text_of
    rep #$20
.a16
    lda #TI_MSG_POS
    sta pick_table
    sep #$20
.a8
    lda comp_col
    bne one
    rep #$20
.a16
    lda #TI_MAIN_MSG_POS
    sta pick_table
    sep #$20
.a8
    phx
    stz temp + 1
    jsl f:ba_t_text
    rep #$20
.a16
    lda #(TI_MAIN_MSG_POS + 128)
    sta pick_table
    plx
    inx
    sep #$20
.a8
one:
    stz temp + 1
    jsl f:ba_t_text
    rts
.endproc

; The currency in `pick_table`, in red as in RM2k.
.proc ti_currency
.a8
.i16
    lda #TI_RED
    sta temp + 1
    ldx #TI_TEXT_CURRENCY
    jsl f:ba_t_text
    rts
.endproc

; How many rows the mode's list has: the buying one has the count and the gold
; below it, and the selling one does not.
.proc ti_rows
.a8
.i16
    lda comp_col
    cmp #TI_SELL
    beq sale
    lda #TI_LIST_ROWS_BUY
    rts
sale:
    lda #TI_LIST_ROWS_SALE
    rts
.endproc

; The whole screen, in the buffer: the stage's `shop_screen`. The windows and
; the bar are not: they go on BG1, and `ti_windows` puts them there every frame.
; Nor is the party, which goes in objects: what it shows is decided first.
.proc ti_compose
.a8
.i16
    jsl f:ti_party_compute
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_clear
    ; --- the message: greeting, re-greeting, or the mode's ---
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; With `f:` because `message` is from here, that is, from bank 1, and the
    ; data bank is still 0: without the long form, the absolute would read bank 0.
    lda f:message, x
    bne with_message
    lda comp_phase + 1            ; the main mode: greeting or re-greeting
with_message:
    jsr ti_message
    lda comp_col
    bne no_main
    jmp main
no_main:
    ; --- the help: the description of the one the cursor highlights ---
    lda comp_mask
    beq no_help
    jsr ti_item
    jsr eq_desc
no_help:
    ; --- the gold, and how many of the highlighted one it has and has equipped:
    ; in all modes of the buying layer, which is all but selling ---
    lda comp_col
    cmp #TI_SELL
    bne near_12209
    jmp no_gold
near_12209:
    rep #$20
.a16
    lda gold
    sta comp_or01
    lda #TI_GOLD_POS
    sta comp_glyph + 1
    clc
    adc #2
    pha
    sep #$20
.a8
    lda gold + 2
    sta comp_or01 + 2
    stz temp + 1
    jsr scr_number24
    rep #$20
.a16
    pla
    sta pick_table
    sep #$20
.a8
    jsr ti_currency
    lda comp_mask
    beq no_gold
    rep #$20
.a16
    lda #TI_HAVE_POS
    sta pick_table
    sep #$20
.a8
    lda #TI_RED
    sta temp + 1
    ldx #TI_TEXT_HAVE
    jsl f:ba_t_text
    jsr ti_item
    jsr eq_inv_point
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    rep #$20
.a16
    lda #TI_HAVE_NUM
    sta pick_table
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_number
    rep #$20
.a16
    lda #TI_CARRIED_POS
    sta pick_table
    sep #$20
.a8
    lda #TI_RED
    sta temp + 1
    ldx #TI_TEXT_CARRIED
    jsl f:ba_t_text
    jsr ti_item
    jsr ti_held
    rep #$20
.a16
    lda #TI_CARRIED_NUM
    sta pick_table
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_number
no_gold:
    lda comp_col
    cmp #TI_COUNT_BUY
    beq how_many
    cmp #TI_COUNT_SALE
    beq how_many
    ; The two "done" leave the middle window empty, like RM2k.
    cmp #TI_BOUGHT
    beq empty
    cmp #TI_SOLD
    beq empty
    jmp list
empty:
    rts

    ; --- the quantity: the item, "x" and how many, and the total ---
how_many:
    jsr ti_item
    rep #$20
.a16
    lda #TI_COUNT_POS
    sta pick_table
    sep #$20
.a8
    lda #255
    jsr eq_name
    rep #$20
.a16
    lda #TI_COUNT_X_POS
    sta pick_table
    sep #$20
.a8
    stz temp + 1
    lda #$78                    ; 'x'
    jsl f:ba_t_glyph
    rep #$20
.a16
    lda #TI_COUNT_NUM_POS
    sta pick_table
    sep #$20
.a8
    lda comp_color
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_number
    jsr ti_item
    jsr ti_price
    jsr ti_times_count          ; ti_num = price * quantity
    rep #$20
.a16
    lda #TI_TOTAL_POS
    sta comp_glyph + 1
    sep #$20
.a8
    stz temp + 1
    jsr scr_number24
    rep #$20
.a16
    lda #(TI_TOTAL_POS + 2)
    sta pick_table
    sep #$20
.a8
    jmp ti_currency

    ; --- the main mode: the commands, below the greeting ---
main:
    lda #0
command:
    pha
    jsr command_pos
    rep #$20
.a16
    sta pick_table
    sep #$20
.a8
    pla
    pha
    jsr command_message         ; which term: buy, sell or leave
    jsr ti_line1
    pla
    inc a
    cmp comp_mask
    bcc command
    rts

    ; --- the list: buy or sell ---
list:
    lda #0
list_row:
    pha
    clc
    adc comp_base + 1
    bcc near_12378
    jmp list_ready
near_12378:
    cmp comp_mask
    bcc near_12382
    jmp list_ready
near_12382:
    pla
    pha
    jsr row_pos
    rep #$20
.a16
    sta pick_table
    sta comp_glyph + 1                  ; the row, for the positions below
    sep #$20
.a8
    pla
    pha
    clc
    adc comp_base + 1
    jsr ti_k_of
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x            ; outside bank 0: `f:` only indexes with X
    sta comp_or23
    txa
    lsr a
    tax                         ; X = k again
    sep #$20
.a8
    phx
    ; the color: buying, if there is enough; selling, if it is worth something
    lda comp_col
    cmp #TI_SELL
    bcs color_sale
    jsr ti_can
    bra color
color_sale:
    jsr ti_price
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
color:
    beq gray
    lda #0
    bra color_ready
gray:
    lda #1
color_ready:
    sta temp + 1
    plx
    rep #$20
.a16
    lda comp_glyph + 1
    clc
    adc #TI_NAME
    sta pick_table
    sep #$20
.a8
    phx
    lda temp + 1
    pha
    lda #255
    sta comp_dup + 3
    jsr eq_k                    ; the name, with the variant set
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax
    sep #$20
.a8
    pla
    sta temp + 1
    pha
    jsl f:ba_t_text
    pla
    sta temp + 1
    plx
    lda comp_col
    cmp #TI_SELL
    bcs count
    ; buying: the price, right-aligned
    rep #$20
.a16
    lda comp_glyph + 1
    clc
    adc #TI_PRICE
    pha
    sep #$20
.a8
    jsr ti_price
    rep #$20
.a16
    pla
    sta comp_glyph + 1
    sep #$20
.a8
    jsr scr_number24
    bra list_next
count:
    ; selling: how many it has
    rep #$20
.a16
    lda comp_glyph + 1
    clc
    adc #SCR_TWO_POINTS
    sta pick_table
    sep #$20
.a8
    lda #$3A
    jsl f:ba_t_glyph
    jsr eq_inv_point
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_number
list_next:
    ; The next row, if the mode's list has it: `ti_rows` does not touch the
    ; stack.
    jsr ti_rows
    sta temp + 3
    pla
    inc a
    cmp temp + 3
    bcs list_end
    jmp list_row
list_end:
    rts
list_ready:
    pla
    rts

; A: the main mode's command. A16 = the position of its row: below the
; greeting, one lower if the greeting has two lines.
command_pos:
    pha
    jsr ti_two_lines
    beq line
    pla
    inc a
    bra with_line
line:
    pla
with_line:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_COMMAND_POS0
    rts
.a8

; A: the row of the list. A16 = the position of its row.
row_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_LIST_POS0
    rts
.a8

; A: the command. A = the message number: 2 buy, 3 sell, 4 leave; with a
; single command, the one the type says.
command_message:
    pha
    lda comp_col + 1
    beq three
    pla
    lda comp_col + 1                 ; 1 buys: 2; 2 sells: 3
    inc a
    rts
three:
    pla
    clc
    adc #2
    rts

; A: the message number. Its first line, in `pick_table`, in white.
ti_line1:
    jsr ti_text_of
    stz temp + 1
    jsl f:ba_t_text
    rts

; Each mode's message: 0 is "the greeting or the re-greeting".
message:
    .byte 0, 5, 6, 7, 8, 9, 10
.endproc

; `ti_num` times `ti_count`, by adding: it is 99 passes at most.
.proc ti_times_count
.a8
.i16
    rep #$20
.a16
    lda comp_or01
    sta comp_and
    stz comp_or01
    sep #$20
.a8
    lda comp_or01 + 2
    sta comp_and + 2
    stz comp_or01 + 2
    lda comp_color
    beq ready
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
other:
    rep #$20
.a16
    lda comp_or01
    clc
    adc comp_and
    sta comp_or01
    sep #$20
.a8
    lda comp_or01 + 2
    adc comp_and + 2
    sta comp_or01 + 2
    dex
    bne other
ready:
    rts
.endproc

; Up to how many of the highlighted one can be bought: the ones missing to 99,
; and no more than the gold pays for. Selling, the ones it has. In `ti_max`.
.proc ti_max
.a8
.i16
    jsr ti_item
    phx
    jsr eq_inv_point
    lda WMDATA
    plx
    sta temp + 3                ; how many it has
    lda comp_col
    cmp #TI_SELL
    bcc buying
    lda temp + 3
    sta comp_row
    rts
buying:
    lda #ITEM_MAX
    sec
    sbc temp + 3
    sta temp + 3                ; the ones missing
    jsr ti_price
    rep #$20
.a16
    lda gold
    sta comp_and
    sep #$20
.a8
    lda gold + 2
    sta comp_and + 2
    stz comp_row
other:
    lda comp_row
    cmp temp + 3
    bcs ready
    ; eq_tmp >= price? If the price is zero, always.
    rep #$20
.a16
    lda comp_and
    sec
    sbc comp_or01
    tay
    sep #$20
.a8
    lda comp_and + 2
    sbc comp_or01 + 2
    bcc ready
    sta comp_and + 2
    rep #$20
.a16
    tya
    sta comp_and
    sep #$20
.a8
    inc comp_row
    bra other
ready:
    rts
.endproc

; Buy or sell `ti_count` of the highlighted one: the gold and the inventory,
; like `UpdateNumberInput`.
.proc ti_close_deal
.a8
.i16
    jsr ti_item
    jsr ti_price
    jsr ti_times_count
    lda comp_col
    cmp #TI_COUNT_SALE
    beq sell
    ; --- buy: the gold goes down and the items go up ---
    rep #$20
.a16
    lda gold
    sec
    sbc comp_or01
    sta gold
    sep #$20
.a8
    lda gold + 2
    sbc comp_or01 + 2
    sta gold + 2
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
sum:
    phx
    jsr ti_item
    lda #1
    jsr eq_inv_move
    plx
    dex
    bne sum
    rts
sell:
    ; --- sell: the gold goes up, capped at GOLD_MAX, and the items go down ---
    jsl f:gold_add
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
removes:
    phx
    jsr ti_item
    lda #0
    jsr eq_inv_move
    plx
    dex
    bne removes
    rts
.endproc

; `gold` plus the 24 bits of `comp_or01`, capped at GOLD_MAX: the adding half of
; `Game_Party::GainGold`. The shop's selling and the victory use it
; —`ba_vic_start`—; `op_gold` has its own because it lives in bank 0. With
; `jsl`: the victory lives in `FAR2`.
.proc gold_add
.a8
.i16
    rep #$20
.a16
    lda gold
    clc
    adc comp_or01
    sta gold
    sep #$20
.a8
    lda gold + 2
    adc comp_or01 + 2
    sta gold + 2
    cmp #^GOLD_MAX
    bcc ready
    bne cap
    rep #$20
.a16
    lda gold
    cmp #.loword(GOLD_MAX)
    sep #$20
.a8
    bcc ready
    beq ready
cap:
    rep #$20
.a16
    lda #.loword(GOLD_MAX)
    sta gold
    sep #$20
.a8
    lda #^GOLD_MAX
    sta gold + 2
ready:
    rtl
.endproc

; The selling list: the inventory the ROM knows, in `FAR_ITEM_LIST`.
.proc ti_sell_list
.a8
.i16
    jsl f:ba_t_build
    lda pick_n
    sta comp_mask
    lda comp_base
    cmp comp_mask
    bcc ready
    lda comp_mask                    ; the last one was sold: the cursor goes up
    beq zero
    dec a
zero:
    sta comp_base
ready:
    rts
.endproc

; A: the new mode. Sets what is needed to enter: the list, the cursor.
.proc ti_mode_set
.a8
.i16
    sta comp_col
    cmp #TI_MAIN
    bne no_main
    lda comp_col + 1
    beq three
    lda #1
    bra n_ready
three:
    lda #3
n_ready:
    sta comp_mask
    rts
no_main:
    cmp #TI_BUY
    bne no_buy
    lda comp_mask + 1
    sta comp_mask
    rts
no_buy:
    cmp #TI_SELL
    bne ready
    jmp ti_sell_list
ready:
    rts
.endproc

; The list's cursor, with the view following it.
.proc ti_move
.a8
.i16
    sta comp_base
    cmp comp_base + 1
    bcs no_up
    sta comp_base + 1
    rts
no_up:
    jsr ti_rows                 ; the buying one and the selling one do not measure the same
    sta temp + 3
    lda comp_base
    sec
    sbc comp_base + 1
    cmp temp + 3
    bcc ready
    lda comp_base
    sec
    sbc temp + 3
    inc a                       ; the cursor, on the last visible row
    sta comp_base + 1
ready:
    rts
.endproc

; The shop's windows, with the screen off and after the screen's bank: the red
; palette of the terms —it goes with the "goes up" one, as in the equipment
; screen—, the colors and tiles of the windows, and the help rows, which are the
; same in all three layers. `ti_windows` puts the rest.
.proc ti_screen_upload
.a8
.i16
    lda #ITEMS_CGRAM_N
    sta CGADD
    rep #$20
.a16
    lda #.loword(item_cgram_uploads)
    sta A1T0L
    lda #(2 * 16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^item_cgram_uploads
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #ITEM_BORDER_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #.loword(ti_border_cgram)
    sta A1T0L
    lda #(TI_BORDER_COLORS * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_border_cgram
    sta A1B0
    lda #$01
    sta MDMAEN
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TI_BORDER_VRAM
    sta VMADDL
    lda #.loword(ti_border_tiles)
    sta A1T0L
    lda #(TI_BORDER_TILES * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_border_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda #TI_BORDER_MAP
    sta VMADDL
    lda #.loword(ti_border_rows)
    sta A1T0L
    lda #(TI_BORDER_UP * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_border_rows
    sta A1B0
    lda #$01
    sta MDMAEN
    rts
.endproc

; BG1's windows below the help, and the bar: in each frame's vblank, behind the
; text, like `eq_bar`. The rows of the mode's layer are uploaded
; —`ti_stretches`, from `ti_border_rows`— and on top the bar's rectangle, from
; `ti_border_patches`. Without remembering anything: every frame restores
; everything, so neither the bar nor the previous layer can be left painted. It
; is 1408 bytes, plus the bar's, which together with the text's 1792 fit in the
; vblank —see `compact_shop` in `rm2k-snes-screens`—.
.proc ti_windows
.a8
.i16
    ; Only when what they depend on changed: the mode, the greeting, the
    ; cursor, the list's first row and its length, which are the eight bytes
    ; from `comp_col` on. Uploading
    ; them every frame took some twenty lines of the vblank, and in the frame
    ; the text's tilemap goes up, after them, the vblank ran out —measured on
    ; 2026-10-03, with the list of eleven, it ended at line 269 of the next
    ; frame: the tilemap's last rows were lost—. The layer forgets them at
    ; each `tl_reset`, so a screen that opens uploads them.
    ldx #0
same:
    lda comp_col, x
    cmp f:$7E0000 + TL_WIN_KEY, x
    bne changed
    inx
    cpx #8
    bcc same
    rts
changed:
    ldx #0
keep:
    lda comp_col, x
    sta f:$7E0000 + TL_WIN_KEY, x
    inx
    cpx #8
    bcc keep
    lda #$80
    sta VMAIN
    lda #^ti_border_rows
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    jsr layer
    rep #$20
.a16
    asl a
    tax
    lda f:ti_layer_stretches, x
    tax
stretch:
    lda f:ti_stretches + 4, x
    beq bar
    sta DAS0L
    lda f:ti_stretches, x
    sta VMADDL
    lda f:ti_stretches + 2, x
    clc
    adc #.loword(ti_border_rows)
    sta A1T0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #6
    tax
    bra stretch
bar:
    sep #$20
.a8
    ; The bar's place in its layer: the command, the visible list row, or the
    ; quantity. The two "done" have none.
    lda comp_col
    beq in_main
    cmp #TI_BUY
    beq in_list
    cmp #TI_SELL
    beq in_list
    cmp #TI_COUNT_BUY
    beq in_count
    cmp #TI_COUNT_SALE
    beq in_count
    rts
in_count:
    lda #TI_LIST_ROWS_BUY       ; the quantity one, after the list's
    bra with_bar
in_list:
    lda comp_mask
    beq no_bar                  ; the empty list has no cursor
    lda comp_base
    sec
    sbc comp_base + 1
    bra with_bar
in_main:
    ; With a two-line greeting the commands go down one: see `command_pos`.
    jsr ti_two_lines
    beq line                    ; and A was left at zero
    lda #1
line:
    clc
    adc comp_base
with_bar:
    sta temp + 2
    jsr layer
    rep #$20
.a16
    tax
    sep #$20
.a8
    lda f:ti_bar_base, x
    clc
    adc temp + 2
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; eight bytes per bar
    tax
    lda f:ti_bars, x
    sta temp                    ; the VRAM word of the row
    lda f:ti_bars + 2, x
    clc
    adc #.loword(ti_border_patches)
    sta temp + 2                ; and where it comes from
    lda f:ti_bars + 6, x
    tay                         ; how many rows
    sep #$20
.a8
    lda #^ti_border_patches
    sta A1B0
    rep #$20
.a16
row:
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda temp + 2
    sta A1T0L
    lda f:ti_bars + 4, x
    sta DAS0L
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    dey
    bne row
    sep #$20
.a8
no_bar:
    rts

; A16 = the mode's layer, `TI_LAYER_OF_MODE`. Returns with 16-bit A.
layer:
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:ti_layer_mode, x
    rep #$20
.a16
    and #$00FF
    rts
.a8
.endproc

; The shop: `ti_type`, `ti_set` and `FAR_SHOP` with `ti_nt` items, set by
; `op_shop`. Returns when the player leaves.
.proc shop_screen
.a8
.i16
    stz comp_phase + 1
    stz comp_base
    stz comp_base + 1
    lda comp_col + 1
    beq a_main
    cmp #1
    beq a_buy
    lda #TI_SELL
    bra begins
a_buy:
    lda #TI_BUY
    bra begins
a_main:
    lda #TI_MAIN
begins:
    jsr ti_mode_set
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_bank_upload
    jsr ti_screen_upload
    jsl f:ti_party_open
    jsr ti_compose
    jsl f:ba_t_upload
    jsr ti_windows
    lda #1
    jsl f:ti_party_vblank       ; the screen is off: all of it
    lda #(SLOT_VRAM / 4096 * 16 + TI_BORDER_VRAM / 4096)
    jsl f:screen_ppu_on         ; BG2 and BG1, the windows with their base
    lda #0
    jsl f:ti_party_vblank       ; and the objects, if the layer shows them
    lda #1
    sta menu_open
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; the controller before the DMA: see the equipment screen
    ; The windows before the text. The other way around, in the frame the
    ; text's tilemap went up —1792 bytes, the longest DMA— the windows' bar
    ; fell out of the vblank and was lost that frame: measured on
    ; 2026-10-03, the windows end around line 244 and the tilemap at 254, of
    ; the 261 of the vblank.
    jsr ti_windows
    ; `scr_upload`, in its three steps, with the party between the text's
    ; uploads and its typesetting: the last two run into the frame.
    jsl f:tl_map + FAST
    jsl f:tl_vblank + FAST
    lda #0
    jsl f:ti_party_vblank
    jsl f:tl_work + FAST
    jsl f:ti_party_tick
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    ; By mode. Without `jmp (table, x)` in the assembler, a chain.
    lda comp_col
    bne not_main
    jmp main
not_main:
    cmp #TI_COUNT_BUY
    bne :+
    jmp how_many
:   cmp #TI_COUNT_SALE
    bne :+
    jmp how_many
:   cmp #TI_BOUGHT
    bne :+
    jmp ready_deal
:   cmp #TI_SOLD
    bne :+
    jmp ready_deal
:   jmp buy                     ; buying and selling share the code

    ; --- the main mode ---
main:
    lda title_edges
    and #PAD_UP
    beq p_no_up
    lda comp_base
    beq wait
    dec comp_base
    jmp recompose
p_no_up:
    lda title_edges
    and #PAD_DOWN
    beq p_no_down
    lda comp_base
    inc a
    cmp comp_mask
    bcs wait
    sta comp_base
    jmp recompose
p_no_down:
    lda title_edges
    and #PAD_B
    beq p_check_a
    jmp leave
p_check_a:
    jsr edge_a
    beq wait
    lda comp_base
    cmp #2
    bne p_no_exit
    jmp leave
p_no_exit:
    cmp #1
    beq p_sell
    lda #TI_BUY
    bra p_enter
p_sell:
    lda #TI_SELL
p_enter:
    stz comp_base
    stz comp_base + 1
    jsr ti_mode_set
    jmp recompose

    ; --- the lists ---
buy:
sell:
    lda title_edges
    and #PAD_UP
    beq l_no_up
    lda comp_base
    beq wait2
    dec a
    jsr ti_move
    jmp recompose
l_no_up:
    lda title_edges
    and #PAD_DOWN
    beq l_no_down
    lda comp_base
    inc a
    cmp comp_mask
    bcs wait2
    jsr ti_move
    jmp recompose
l_no_down:
    lda title_edges
    and #PAD_B
    beq l_check_a
    ; B: to the main mode, with the re-greeting; without a main mode, out.
    lda comp_col + 1
    beq to_main
    jmp leave
to_main:
    lda comp_col
    cmp #TI_SELL
    lda #0
    bcc cursor_ready
    lda #1                      ; the cursor on the command it is returning from
cursor_ready:
    sta comp_base
    lda #1
    sta comp_phase + 1
    lda #TI_MAIN
    jsr ti_mode_set
    jmp recompose
l_check_a:
    jsr edge_a
    beq wait2
    lda comp_mask
    beq wait2
    lda comp_col
    cmp #TI_SELL
    bcs l_sell
    jsr ti_item                 ; X = k
    jsr ti_can
    beq wait2                   ; grayed out: it plays a sound and does nothing
    lda #TI_COUNT_BUY
    bra l_count
l_sell:
    jsr ti_item
    jsr ti_price
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    beq wait2                   ; it is worth nothing
    lda #TI_COUNT_SALE
l_count:
    pha
    jsr ti_max
    pla
    sta comp_col
    lda #1
    sta comp_color
    jmp recompose
wait2:
    jmp wait

    ; --- the quantity ---
how_many:
    lda title_edges
    and #PAD_RIGHT
    beq c_no_right
    lda #1
    bra c_add
c_no_right:
    lda title_edges
    and #PAD_LEFT
    beq c_no_left
    lda #$FF
    bra c_add
c_no_left:
    lda title_edges
    and #PAD_UP
    beq c_no_up
    lda #10
    bra c_add
c_no_up:
    lda title_edges
    and #PAD_DOWN
    beq c_no_down
    lda #$F6                    ; -10
c_add:
    ; Signed, and capped to [1, ti_max].
    clc
    adc comp_color
    bmi c_one                   ; went below zero: it is 99 at most
    beq c_one
    cmp comp_row
    bcc c_set
    beq c_set
    lda comp_row
    bra c_set
c_one:
    lda #1
c_set:
    sta comp_color
    jmp recompose
c_no_down:
    lda title_edges
    and #PAD_B
    beq c_check_a
    lda comp_col
    cmp #TI_COUNT_SALE
    beq c_a_sell
    lda #TI_BUY
    sta comp_col
    jmp recompose
c_a_sell:
    lda #TI_SELL
    sta comp_col
    jmp recompose
c_check_a:
    jsr edge_a
    beq wait2
    jsr ti_close_deal
    lda #TI_SECOND
    sta comp_glyph
    lda comp_col
    inc a                       ; CUANTOS_COMPRA -> COMPRADO, and the selling the same
    sta comp_col
    cmp #TI_SOLD
    bne recompose
    jsr ti_sell_list            ; what was sold may no longer be there
    jmp recompose

    ; --- the "done", one second ---
ready_deal:
    dec comp_glyph
    bne wait2
    lda comp_col
    dec a
    dec a                       ; COMPRADO -> COMPRAR, VENDIDO -> VENDER
    sta comp_col
recompose:
    jsr ti_compose
    jmp wait

leave:
    jsl f:ti_party_close
    rtl

; Z=0 if A was just pressed.
edge_a:
    lda pad_a
    beq no_a
    lda pad_a_prev
    beq a_pressed
no_a:
    lda #0
    rts
a_pressed:
    lda #1
    rts
.endproc

