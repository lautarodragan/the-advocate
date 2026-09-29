.segment "FAR"

; --- the shop ------------------------------------------------------------------
;
; `Scene_Shop`, opened by `OP_SHOP` from the interpreter, like saving: the
; screen blocks inside the page, it costs no tick, and on exit the map comes
; back and the page goes on. It is a text screen —see "the text
; screens"— and `pantallas.pantalla_tienda` is the reference for each mode. The
; System's windows and the bar go on BG1, with their own base: see
; `ti_pantalla_subir` and `ti_ventanas`, and `pantallas.TI_VENTANAS`. What
; it sells goes as `k` in `FAR_TIENDA`; the selling list, in
; `FAR_ITEM_LISTA`.
;
; The scratch space, borrowed from the message compositor:
;   ti_modo      is comp_col       ; TI_PRINCIPAL ... TI_VENDIDO
;   ti_tipo      is comp_col + 1   ; 0 buys and sells, 1 buys, 2 sells
;   ti_juego     is comp_fase      ; the message set, 0 to 2
;   ti_resaludo  is comp_fase + 1  ; whether it already went back to the main one
;   ti_elegido   is comp_base      ; the cursor
;   ti_arriba    is comp_base + 1  ; the first visible one of the list
;   ti_n         is comp_mask      ; how many there are in the mode's list
;   ti_nt        is comp_mask + 1  ; how many the shop sells
;   ti_cuantos   is comp_color     ; the quantity being chosen
;   ti_max       is comp_fila      ; and up to how many
;   ti_timer     is comp_glifo     ; the frames of the "done"
;   ti_pos       is comp_glifo + 1 ; two bytes: where the digit goes
;   ti_num       is comp_or01      ; three bytes: a 24-bit number
FAR_TIENDA = $2B00
TI_PRINCIPAL = 0
TI_COMPRAR = 1
TI_CUANTOS_COMPRA = 2
TI_COMPRADO = 3
TI_VENDER = 4
TI_CUANTOS_VENTA = 5
TI_VENDIDO = 6

; A: a place in the mode's list. Returns with A = its `k`.
.proc ti_k_de
.a8
.i16
    pha
    lda comp_col
    cmp #TI_VENDER
    bcs de_venta
    pla
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_TIENDA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
de_venta:
    pla
    jsl f:ba_t_lista
    rts
.endproc

; The item the cursor highlights, in `eq_id`, and its `k` in X.
.proc ti_item
.a8
.i16
    lda comp_base
    jsr ti_k_de
    rep #$20
.a16
    and #$00FF
    tax
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    rts
.endproc

; The price of X's `k`, in `ti_num`, halved if selling.
.proc ti_precio
.a8
.i16
    rep #$20
.a16
    txa
    asl a
    tay
    lda item_precio, y
    sta comp_or01
    sep #$20
.a8
    stz comp_or01 + 2
    lda comp_col
    cmp #TI_VENDER
    bcc listo
    rep #$20
.a16
    lsr comp_or01
    sep #$20
.a8
listo:
    rts
.endproc

; Is there enough gold for X's `k`, and does it have fewer than 99? Z=0 if it
; can be bought. `Window_ShopBuy::CheckEnable`.
.proc ti_puede
.a8
.i16
    phx
    jsr ti_precio
    plx
    ; gold >= price, 24 bits
    lda oro + 2
    bne alcanza
    rep #$20
.a16
    lda oro
    cmp comp_or01
    sep #$20
.a8
    bcc no
alcanza:
    rep #$20
.a16
    txa
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    jsr eq_inv_apuntar
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
; a time, like the menu's gold.
.proc pant_numero24
.a8
.i16
cifra:
    stz temp + 3                ; the remainder carried along
    ldx #2
dividir:
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
    bpl dividir
    rep #$20
.a16
    lda comp_glifo + 1
    sta eleg_tabla
    dec a
    dec a
    sta comp_glifo + 1
    sep #$20
.a8
    lda temp + 3
    clc
    adc #$30
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    bne cifra
    lda comp_or01 + 2
    bne cifra
    rts
.endproc

; How many of item `eq_id` the party has equipped: `GetEquippedItemCount`.
; Returns in `pant_valor`.
.proc ti_llevados
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
miembro:
    cmp grupo_n
    bcs listo
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    sta comp_char
    lda #0
ranura:
    pha
    jsr eq_leer
    rep #$20
.a16
    lda comp_or23
    cmp comp_or01
    bne otra
    inc comp_dup
otra:
    sep #$20
.a8
    pla
    inc a
    cmp #5
    bcc ranura
    pla
    inc a
    bra miembro
listo:
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
.proc ti_texto_de
.a8
.i16
    sta temp + 3
    lda comp_fase
    asl a
    asl a
    asl a                       ; times 8
    clc
    adc comp_fase
    adc comp_fase
    adc comp_fase                ; times 11
    clc
    adc temp + 3
    rep #$20
.a16
    and #$00FF
    asl a                       ; two lines each
    clc
    adc #TI_TEXTO
    tax
    sep #$20
.a8
    rts
.endproc

; A != 0 if the main mode's greeting —or the re-greeting— takes two lines: the
; commands go below, so they start one lower. It is the length of the second
; line.
.proc ti_dos_renglones
.a8
.i16
    lda comp_fase + 1
    jsr ti_texto_de
    inx
    lda f:item_txt_n, x
    rts
.endproc

; Message A of the shop's set, in the bottom window: in the main mode both
; lines, above the commands; in the other modes, just one, which is what fits
; in their window —those modes' messages are one line long, and the converter
; checks it—.
.proc ti_mensaje
.a8
.i16
    jsr ti_texto_de
    rep #$20
.a16
    lda #TI_MSG_POS
    sta eleg_tabla
    sep #$20
.a8
    lda comp_col
    bne uno
    rep #$20
.a16
    lda #TI_PRINCIPAL_MSG_POS
    sta eleg_tabla
    sep #$20
.a8
    phx
    stz temp + 1
    jsl f:ba_t_texto
    rep #$20
.a16
    lda #(TI_PRINCIPAL_MSG_POS + 128)
    sta eleg_tabla
    plx
    inx
    sep #$20
.a8
uno:
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; The currency in `eleg_tabla`, in red as in RM2k.
.proc ti_moneda
.a8
.i16
    lda #TI_ROJO
    sta temp + 1
    ldx #TI_TEXTO_MONEDA
    jsl f:ba_t_texto
    rts
.endproc

; How many rows the mode's list has: the buying one has the count and the gold
; below it, and the selling one does not.
.proc ti_filas
.a8
.i16
    lda comp_col
    cmp #TI_VENDER
    beq venta
    lda #TI_LISTA_FILAS_COMPRA
    rts
venta:
    lda #TI_LISTA_FILAS_VENTA
    rts
.endproc

; The whole screen, in the buffer: `pantallas.pantalla_tienda`. The windows and
; the bar are not: they go on BG1, and `ti_ventanas` puts them there every frame.
.proc ti_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    ; --- the message: greeting, re-greeting, or the mode's ---
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; With `f:` because `mensaje_de` is from here, that is, from bank 1, and the
    ; data bank is still 0: without the long form, the absolute would read bank 0.
    lda f:mensaje_de, x
    bne con_mensaje
    lda comp_fase + 1             ; the main mode: greeting or re-greeting
con_mensaje:
    jsr ti_mensaje
    lda comp_col
    bne no_principal
    jmp principal
no_principal:
    ; --- the help: the description of the one the cursor highlights ---
    lda comp_mask
    beq sin_ayuda
    jsr ti_item
    jsr eq_desc
sin_ayuda:
    ; --- the gold, and how many of the highlighted one it has and has equipped:
    ; in all modes of the buying layer, which is all but selling ---
    lda comp_col
    cmp #TI_VENDER
    bne cerca_12209
    jmp sin_oro
cerca_12209:
    rep #$20
.a16
    lda oro
    sta comp_or01
    lda #TI_ORO_POS
    sta comp_glifo + 1
    clc
    adc #2
    pha
    sep #$20
.a8
    lda oro + 2
    sta comp_or01 + 2
    stz temp + 1
    jsr pant_numero24
    rep #$20
.a16
    pla
    sta eleg_tabla
    sep #$20
.a8
    jsr ti_moneda
    lda comp_mask
    beq sin_oro
    rep #$20
.a16
    lda #TI_TENGO_POS
    sta eleg_tabla
    sep #$20
.a8
    lda #TI_ROJO
    sta temp + 1
    ldx #TI_TEXTO_TENGO
    jsl f:ba_t_texto
    jsr ti_item
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    rep #$20
.a16
    lda #TI_TENGO_NUM
    sta eleg_tabla
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_numero
    rep #$20
.a16
    lda #TI_LLEVO_POS
    sta eleg_tabla
    sep #$20
.a8
    lda #TI_ROJO
    sta temp + 1
    ldx #TI_TEXTO_LLEVO
    jsl f:ba_t_texto
    jsr ti_item
    jsr ti_llevados
    rep #$20
.a16
    lda #TI_LLEVO_NUM
    sta eleg_tabla
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_numero
sin_oro:
    lda comp_col
    cmp #TI_CUANTOS_COMPRA
    beq cuantos
    cmp #TI_CUANTOS_VENTA
    beq cuantos
    ; The two "done" leave the middle window empty, like RM2k.
    cmp #TI_COMPRADO
    beq vacia
    cmp #TI_VENDIDO
    beq vacia
    jmp lista
vacia:
    rts

    ; --- the quantity: the item, "x" and how many, and the total ---
cuantos:
    jsr ti_item
    rep #$20
.a16
    lda #TI_CUANTOS_POS
    sta eleg_tabla
    sep #$20
.a8
    lda #255
    jsr eq_nombre
    rep #$20
.a16
    lda #TI_CUANTOS_X_POS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$78                    ; 'x'
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda #TI_CUANTOS_NUM_POS
    sta eleg_tabla
    sep #$20
.a8
    lda comp_color
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_numero
    jsr ti_item
    jsr ti_precio
    jsr ti_por_cuantos          ; ti_num = price * quantity
    rep #$20
.a16
    lda #TI_TOTAL_POS
    sta comp_glifo + 1
    sep #$20
.a8
    stz temp + 1
    jsr pant_numero24
    rep #$20
.a16
    lda #(TI_TOTAL_POS + 2)
    sta eleg_tabla
    sep #$20
.a8
    jmp ti_moneda

    ; --- the main mode: the commands, below the greeting ---
principal:
    lda #0
orden:
    pha
    jsr orden_pos
    rep #$20
.a16
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    jsr orden_mensaje           ; which term: buy, sell or leave
    jsr ti_renglon1
    pla
    inc a
    cmp comp_mask
    bcc orden
    rts

    ; --- the list: buy or sell ---
lista:
    lda #0
lista_fila:
    pha
    clc
    adc comp_base + 1
    bcc cerca_12378
    jmp lista_listo
cerca_12378:
    cmp comp_mask
    bcc cerca_12382
    jmp lista_listo
cerca_12382:
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    sta eleg_tabla
    sta comp_glifo + 1                  ; the row, for the positions below
    sep #$20
.a8
    pla
    pha
    clc
    adc comp_base + 1
    jsr ti_k_de
    rep #$20
.a16
    and #$00FF
    tax
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    phx
    ; the color: buying, if there is enough; selling, if it is worth something
    lda comp_col
    cmp #TI_VENDER
    bcs color_venta
    jsr ti_puede
    bra color
color_venta:
    jsr ti_precio
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
color:
    beq gris
    lda #0
    bra color_listo
gris:
    lda #1
color_listo:
    sta temp + 1
    plx
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #TI_NOMBRE
    sta eleg_tabla
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
    jsl f:ba_t_texto
    pla
    sta temp + 1
    plx
    lda comp_col
    cmp #TI_VENDER
    bcs cuenta
    ; buying: the price, right-aligned
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #TI_PRECIO
    pha
    sep #$20
.a8
    jsr ti_precio
    rep #$20
.a16
    pla
    sta comp_glifo + 1
    sep #$20
.a8
    jsr pant_numero24
    bra lista_siguiente
cuenta:
    ; selling: how many it has
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #PANT_DOS_PUNTOS
    sta eleg_tabla
    sep #$20
.a8
    lda #$3A
    jsl f:ba_t_glifo
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_numero
lista_siguiente:
    ; The next row, if the mode's list has it: `ti_filas` does not touch the
    ; stack.
    jsr ti_filas
    sta temp + 3
    pla
    inc a
    cmp temp + 3
    bcs lista_fin
    jmp lista_fila
lista_fin:
    rts
lista_listo:
    pla
    rts

; A: the main mode's command. A16 = the position of its row: below the
; greeting, one lower if the greeting has two lines.
orden_pos:
    pha
    jsr ti_dos_renglones
    beq un_renglon
    pla
    inc a
    bra con_renglon
un_renglon:
    pla
con_renglon:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_ORDEN_POS0
    rts
.a8

; A: the row of the list. A16 = the position of its row.
fila_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_LISTA_POS0
    rts
.a8

; A: the command. A = the message number: 2 buy, 3 sell, 4 leave; with a
; single command, the one the type says.
orden_mensaje:
    pha
    lda comp_col + 1
    beq tres
    pla
    lda comp_col + 1                 ; 1 buys: 2; 2 sells: 3
    inc a
    rts
tres:
    pla
    clc
    adc #2
    rts

; A: the message number. Its first line, in `eleg_tabla`, in white.
ti_renglon1:
    jsr ti_texto_de
    stz temp + 1
    jsl f:ba_t_texto
    rts

; Each mode's message: 0 is "the greeting or the re-greeting".
mensaje_de:
    .byte 0, 5, 6, 7, 8, 9, 10
.endproc

; `ti_num` times `ti_cuantos`, by adding: it is 99 passes at most.
.proc ti_por_cuantos
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
    beq listo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
otra:
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
    bne otra
listo:
    rts
.endproc

; Up to how many of the highlighted one can be bought: the ones missing to 99,
; and no more than the gold pays for. Selling, the ones it has. In `ti_max`.
.proc ti_maximo
.a8
.i16
    jsr ti_item
    phx
    jsr eq_inv_apuntar
    lda WMDATA
    plx
    sta temp + 3                ; how many it has
    lda comp_col
    cmp #TI_VENDER
    bcc comprando
    lda temp + 3
    sta comp_fila
    rts
comprando:
    lda #ITEM_MAX
    sec
    sbc temp + 3
    sta temp + 3                ; the ones missing
    jsr ti_precio
    rep #$20
.a16
    lda oro
    sta comp_and
    sep #$20
.a8
    lda oro + 2
    sta comp_and + 2
    stz comp_fila
otro:
    lda comp_fila
    cmp temp + 3
    bcs listo
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
    bcc listo
    sta comp_and + 2
    rep #$20
.a16
    tya
    sta comp_and
    sep #$20
.a8
    inc comp_fila
    bra otro
listo:
    rts
.endproc

; Buy or sell `ti_cuantos` of the highlighted one: the gold and the inventory,
; like `UpdateNumberInput`.
.proc ti_cerrar_trato
.a8
.i16
    jsr ti_item
    jsr ti_precio
    jsr ti_por_cuantos
    lda comp_col
    cmp #TI_CUANTOS_VENTA
    beq vender
    ; --- buy: the gold goes down and the items go up ---
    rep #$20
.a16
    lda oro
    sec
    sbc comp_or01
    sta oro
    sep #$20
.a8
    lda oro + 2
    sbc comp_or01 + 2
    sta oro + 2
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
suma:
    phx
    jsr ti_item
    lda #1
    jsr eq_inv_mover
    plx
    dex
    bne suma
    rts
vender:
    ; --- sell: the gold goes up, capped at ORO_MAX, and the items go down ---
    jsr oro_sumar
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
quita:
    phx
    jsr ti_item
    lda #0
    jsr eq_inv_mover
    plx
    dex
    bne quita
    rts
.endproc

; `oro` plus the 24 bits of `comp_or01`, capped at ORO_MAX: the adding half of
; `Game_Party::GainGold`. The shop's selling and the victory use it
; —`ba_vic_empezar`—; `op_gold` has its own because it lives in bank 0.
.proc oro_sumar
.a8
.i16
    rep #$20
.a16
    lda oro
    clc
    adc comp_or01
    sta oro
    sep #$20
.a8
    lda oro + 2
    adc comp_or01 + 2
    sta oro + 2
    cmp #^ORO_MAX
    bcc listo
    bne tope
    rep #$20
.a16
    lda oro
    cmp #.loword(ORO_MAX)
    sep #$20
.a8
    bcc listo
    beq listo
tope:
    rep #$20
.a16
    lda #.loword(ORO_MAX)
    sta oro
    sep #$20
.a8
    lda #^ORO_MAX
    sta oro + 2
listo:
    rts
.endproc

; The selling list: the inventory the ROM knows, in `FAR_ITEM_LISTA`.
.proc ti_lista_venta
.a8
.i16
    jsl f:ba_t_armar
    lda eleg_n
    sta comp_mask
    lda comp_base
    cmp comp_mask
    bcc listo
    lda comp_mask                    ; the last one was sold: the cursor goes up
    beq cero
    dec a
cero:
    sta comp_base
listo:
    rts
.endproc

; A: the new mode. Sets what is needed to enter: the list, the cursor.
.proc ti_modo_poner
.a8
.i16
    sta comp_col
    cmp #TI_PRINCIPAL
    bne no_principal
    lda comp_col + 1
    beq tres
    lda #1
    bra n_listo
tres:
    lda #3
n_listo:
    sta comp_mask
    rts
no_principal:
    cmp #TI_COMPRAR
    bne no_comprar
    lda comp_mask + 1
    sta comp_mask
    rts
no_comprar:
    cmp #TI_VENDER
    bne listo
    jmp ti_lista_venta
listo:
    rts
.endproc

; The list's cursor, with the view following it.
.proc ti_mover
.a8
.i16
    sta comp_base
    cmp comp_base + 1
    bcs no_arriba
    sta comp_base + 1
    rts
no_arriba:
    jsr ti_filas                ; the buying one and the selling one do not measure the same
    sta temp + 3
    lda comp_base
    sec
    sbc comp_base + 1
    cmp temp + 3
    bcc listo
    lda comp_base
    sec
    sbc temp + 3
    inc a                       ; the cursor, on the last visible row
    sta comp_base + 1
listo:
    rts
.endproc

; The shop's windows, with the screen off and after the screen's bank: the red
; palette of the terms —it goes with the "goes up" one, as in the equipment
; screen—, the colors and tiles of the windows, and the help rows, which are the
; same in all three layers. `ti_ventanas` puts the rest.
.proc ti_pantalla_subir
.a8
.i16
    lda #ITEMS_CGRAM_N
    sta CGADD
    rep #$20
.a16
    lda #.loword(item_cgram_sube)
    sta A1T0L
    lda #(2 * 16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^item_cgram_sube
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #ITEM_MARCO_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #.loword(ti_marco_cgram)
    sta A1T0L
    lda #(TI_MARCO_COLORES * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_marco_cgram
    sta A1B0
    lda #$01
    sta MDMAEN
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TI_MARCO_VRAM
    sta VMADDL
    lda #.loword(ti_marco_tiles)
    sta A1T0L
    lda #(TI_MARCO_TILES * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_marco_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda #TI_MARCO_MAPA
    sta VMADDL
    lda #.loword(ti_marco_filas)
    sta A1T0L
    lda #(TI_MARCO_ARRIBA * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^ti_marco_filas
    sta A1B0
    lda #$01
    sta MDMAEN
    rts
.endproc

; BG1's windows below the help, and the bar: in each frame's vblank, behind the
; text, like `eq_barra`. The rows of the mode's layer are uploaded
; —`ti_tramos`, from `ti_marco_filas`— and on top the bar's rectangle, from
; `ti_marco_parches`. Without remembering anything: every frame restores
; everything, so neither the bar nor the previous layer can be left painted. It
; is 1408 bytes, plus the bar's, which together with the text's 1792 fit in the
; vblank —see `pantallas.tienda_compacta`—.
.proc ti_ventanas
.a8
.i16
    lda #$80
    sta VMAIN
    lda #^ti_marco_filas
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    jsr capa
    rep #$20
.a16
    asl a
    tax
    lda f:ti_capa_tramos, x
    tax
tramo:
    lda f:ti_tramos + 4, x
    beq barra
    sta DAS0L
    lda f:ti_tramos, x
    sta VMADDL
    lda f:ti_tramos + 2, x
    clc
    adc #.loword(ti_marco_filas)
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
    bra tramo
barra:
    sep #$20
.a8
    ; The bar's place in its layer: the command, the visible list row, or the
    ; quantity. The two "done" have none.
    lda comp_col
    beq en_principal
    cmp #TI_COMPRAR
    beq en_lista
    cmp #TI_VENDER
    beq en_lista
    cmp #TI_CUANTOS_COMPRA
    beq en_cuantos
    cmp #TI_CUANTOS_VENTA
    beq en_cuantos
    rts
en_cuantos:
    lda #TI_LISTA_FILAS_COMPRA  ; the quantity one, after the list's
    bra con_barra
en_lista:
    lda comp_mask
    beq sin_barra               ; the empty list has no cursor
    lda comp_base
    sec
    sbc comp_base + 1
    bra con_barra
en_principal:
    ; With a two-line greeting the commands go down one: see `orden_pos`.
    jsr ti_dos_renglones
    beq un_renglon              ; and A was left at zero
    lda #1
un_renglon:
    clc
    adc comp_base
con_barra:
    sta temp + 2
    jsr capa
    rep #$20
.a16
    tax
    sep #$20
.a8
    lda f:ti_barra_base, x
    clc
    adc temp + 2
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; eight bytes per bar
    tax
    lda f:ti_barras, x
    sta temp                    ; the VRAM word of the row
    lda f:ti_barras + 2, x
    clc
    adc #.loword(ti_marco_parches)
    sta temp + 2                ; and where it comes from
    lda f:ti_barras + 6, x
    tay                         ; how many rows
    sep #$20
.a8
    lda #^ti_marco_parches
    sta A1B0
    rep #$20
.a16
fila:
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda temp + 2
    sta A1T0L
    lda f:ti_barras + 4, x
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
    bne fila
    sep #$20
.a8
sin_barra:
    rts

; A16 = the mode's layer, `pantallas.TI_CAPA_DE_MODO`. Returns with 16-bit A.
capa:
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:ti_capa_de_modo, x
    rep #$20
.a16
    and #$00FF
    rts
.a8
.endproc

; The shop: `ti_tipo`, `ti_juego` and `FAR_TIENDA` with `ti_nt` items, set by
; `op_shop`. Returns when the player leaves.
.proc tienda_pantalla
.a8
.i16
    stz comp_fase + 1
    stz comp_base
    stz comp_base + 1
    lda comp_col + 1
    beq a_principal
    cmp #1
    beq a_comprar
    lda #TI_VENDER
    bra empieza
a_comprar:
    lda #TI_COMPRAR
    bra empieza
a_principal:
    lda #TI_PRINCIPAL
empieza:
    jsr ti_modo_poner
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_banco_subir
    jsr ti_pantalla_subir
    jsr ti_componer
    jsl f:ba_t_subir
    jsr ti_ventanas
    lda #(RANURA_VRAM / 4096 * 16 + TI_MARCO_VRAM / 4096)
    jsl f:pantalla_ppu_prender  ; BG2 and BG1, the windows with their base
    lda #1
    sta menu_abierto
espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; the controller before the DMA: see the equipment screen
    jsl f:ba_t_subir
    jsr ti_ventanas
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    ; By mode. Without `jmp (tabla, x)` in the assembler, a chain.
    lda comp_col
    bne no_es_principal
    jmp principal
no_es_principal:
    cmp #TI_CUANTOS_COMPRA
    bne :+
    jmp cuantos
:   cmp #TI_CUANTOS_VENTA
    bne :+
    jmp cuantos
:   cmp #TI_COMPRADO
    bne :+
    jmp listo_trato
:   cmp #TI_VENDIDO
    bne :+
    jmp listo_trato
:   jmp comprar                 ; buying and selling share the code

    ; --- the main mode ---
principal:
    lda titulo_flancos
    and #PAD_UP
    beq p_no_arriba
    lda comp_base
    beq espera
    dec comp_base
    jmp recomponer
p_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq p_no_abajo
    lda comp_base
    inc a
    cmp comp_mask
    bcs espera
    sta comp_base
    jmp recomponer
p_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq p_mira_a
    jmp salir
p_mira_a:
    jsr flanco_a
    beq espera
    lda comp_base
    cmp #2
    bne p_no_salir
    jmp salir
p_no_salir:
    cmp #1
    beq p_vender
    lda #TI_COMPRAR
    bra p_entrar
p_vender:
    lda #TI_VENDER
p_entrar:
    stz comp_base
    stz comp_base + 1
    jsr ti_modo_poner
    jmp recomponer

    ; --- the lists ---
comprar:
vender:
    lda titulo_flancos
    and #PAD_UP
    beq l_no_arriba
    lda comp_base
    beq espera2
    dec a
    jsr ti_mover
    jmp recomponer
l_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq l_no_abajo
    lda comp_base
    inc a
    cmp comp_mask
    bcs espera2
    jsr ti_mover
    jmp recomponer
l_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq l_mira_a
    ; B: to the main mode, with the re-greeting; without a main mode, out.
    lda comp_col + 1
    beq a_la_principal
    jmp salir
a_la_principal:
    lda comp_col
    cmp #TI_VENDER
    lda #0
    bcc cursor_listo
    lda #1                      ; the cursor on the command it is returning from
cursor_listo:
    sta comp_base
    lda #1
    sta comp_fase + 1
    lda #TI_PRINCIPAL
    jsr ti_modo_poner
    jmp recomponer
l_mira_a:
    jsr flanco_a
    beq espera2
    lda comp_mask
    beq espera2
    lda comp_col
    cmp #TI_VENDER
    bcs l_vender
    jsr ti_item                 ; X = k
    jsr ti_puede
    beq espera2                 ; grayed out: it plays a sound and does nothing
    lda #TI_CUANTOS_COMPRA
    bra l_cuantos
l_vender:
    jsr ti_item
    jsr ti_precio
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    beq espera2                 ; it is worth nothing
    lda #TI_CUANTOS_VENTA
l_cuantos:
    pha
    jsr ti_maximo
    pla
    sta comp_col
    lda #1
    sta comp_color
    jmp recomponer
espera2:
    jmp espera

    ; --- the quantity ---
cuantos:
    lda titulo_flancos
    and #PAD_RIGHT
    beq c_no_derecha
    lda #1
    bra c_sumar
c_no_derecha:
    lda titulo_flancos
    and #PAD_LEFT
    beq c_no_izquierda
    lda #$FF
    bra c_sumar
c_no_izquierda:
    lda titulo_flancos
    and #PAD_UP
    beq c_no_arriba
    lda #10
    bra c_sumar
c_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq c_no_abajo
    lda #$F6                    ; -10
c_sumar:
    ; Signed, and capped to [1, ti_max].
    clc
    adc comp_color
    bmi c_uno                   ; went below zero: it is 99 at most
    beq c_uno
    cmp comp_fila
    bcc c_poner
    beq c_poner
    lda comp_fila
    bra c_poner
c_uno:
    lda #1
c_poner:
    sta comp_color
    jmp recomponer
c_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq c_mira_a
    lda comp_col
    cmp #TI_CUANTOS_VENTA
    beq c_a_vender
    lda #TI_COMPRAR
    sta comp_col
    jmp recomponer
c_a_vender:
    lda #TI_VENDER
    sta comp_col
    jmp recomponer
c_mira_a:
    jsr flanco_a
    beq espera2
    jsr ti_cerrar_trato
    lda #TI_SEGUNDO
    sta comp_glifo
    lda comp_col
    inc a                       ; CUANTOS_COMPRA -> COMPRADO, and the selling the same
    sta comp_col
    cmp #TI_VENDIDO
    bne recomponer
    jsr ti_lista_venta          ; what was sold may no longer be there
    jmp recomponer

    ; --- the "done", one second ---
listo_trato:
    dec comp_glifo
    bne espera2
    lda comp_col
    dec a
    dec a                       ; COMPRADO -> COMPRAR, VENDIDO -> VENDER
    sta comp_col
recomponer:
    jsr ti_componer
    jmp espera

salir:
    rtl

; Z=0 if A was just pressed.
flanco_a:
    lda pad_a
    beq no_a
    lda pad_a_ant
    beq si_a
no_a:
    lda #0
    rts
si_a:
    lda #1
    rts
.endproc

