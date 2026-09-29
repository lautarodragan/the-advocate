.segment "FAR"

; --- la tienda -----------------------------------------------------------------
;
; `Scene_Shop`, abierta por `OP_SHOP` desde el intérprete, como guardar: la
; pantalla bloquea adentro de la página, no cuesta ningún tick, y al salir el
; mapa vuelve y la página sigue. Es una pantalla de texto —ver "las pantallas
; de texto"— y `pantallas.pantalla_tienda` es la referencia de cada modo. Las
; ventanas del System y la barra van en BG1, con su propia base: ver
; `ti_pantalla_subir` y `ti_ventanas`, y `pantallas.TI_VENTANAS`. Lo
; que vende va como `k` en `FAR_TIENDA`; la lista de vender, en
; `FAR_ITEM_LISTA`.
;
; El escritorio, prestado del compositor de mensajes:
;   ti_modo      es comp_col       ; TI_PRINCIPAL ... TI_VENDIDO
;   ti_tipo      es comp_col + 1   ; 0 compra y vende, 1 compra, 2 vende
;   ti_juego     es comp_fase      ; el juego de mensajes, 0 a 2
;   ti_resaludo  es comp_fase + 1  ; si ya se volvió a la principal
;   ti_elegido   es comp_base      ; el cursor
;   ti_arriba    es comp_base + 1  ; el primero que se ve de la lista
;   ti_n         es comp_mask      ; cuántos hay en la lista del modo
;   ti_nt        es comp_mask + 1  ; cuántos vende la tienda
;   ti_cuantos   es comp_color     ; la cantidad que se elige
;   ti_max       es comp_fila      ; y hasta cuánto
;   ti_timer     es comp_glifo     ; los cuadros del "listo"
;   ti_pos       es comp_glifo + 1 ; dos bytes: dónde va la cifra
;   ti_num       es comp_or01      ; tres bytes: un número de 24 bits
FAR_TIENDA = $2B00
TI_PRINCIPAL = 0
TI_COMPRAR = 1
TI_CUANTOS_COMPRA = 2
TI_COMPRADO = 3
TI_VENDER = 4
TI_CUANTOS_VENTA = 5
TI_VENDIDO = 6

; A: un lugar de la lista del modo. Vuelve con A = su `k`.
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

; El ítem que marca el cursor, en `eq_id`, y su `k` en X.
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

; El precio del `k` de X, en `ti_num`, a la mitad si se vende.
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

; ¿Alcanza el oro para el `k` de X, y tiene menos de 99? Z=0 si se puede
; comprar. `Window_ShopBuy::CheckEnable`.
.proc ti_puede
.a8
.i16
    phx
    jsr ti_precio
    plx
    ; oro >= precio, de 24 bits
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

; Un número de 24 bits de `ti_num` —se pierde—, alineado a la derecha con su
; última cifra en `ti_pos`, en la variante de `temp + 1`. Se divide por diez
; de a un byte, como el oro del menú.
.proc pant_numero24
.a8
.i16
cifra:
    stz temp + 3                ; el resto que se arrastra
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

; Cuántos del ítem `eq_id` lleva puestos el grupo: `GetEquippedItemCount`.
; Vuelve en `pant_valor`.
.proc ti_llevados
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    sta comp_or01                  ; el que se busca
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

; A: el número de mensaje del juego de la tienda. X = el texto de su primer
; renglón; el segundo es el que sigue.
.proc ti_texto_de
.a8
.i16
    sta temp + 3
    lda comp_fase
    asl a
    asl a
    asl a                       ; por 8
    clc
    adc comp_fase
    adc comp_fase
    adc comp_fase                ; por 11
    clc
    adc temp + 3
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos renglones cada uno
    clc
    adc #TI_TEXTO
    tax
    sep #$20
.a8
    rts
.endproc

; A != 0 si el saludo de la principal —o el resaludo— ocupa dos renglones:
; las órdenes van debajo, así que arrancan uno más abajo. Es el largo del
; segundo renglón.
.proc ti_dos_renglones
.a8
.i16
    lda comp_fase + 1
    jsr ti_texto_de
    inx
    lda f:item_txt_n, x
    rts
.endproc

; El mensaje A del juego de la tienda, en la ventana de abajo: en la
; principal los dos renglones, arriba de las órdenes; en los demás modos,
; uno solo, que es lo que entra en su ventana —los mensajes de esos modos
; miden un renglón, y el conversor lo controla—.
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

; La moneda en `eleg_tabla`, en rojo como en RM2k.
.proc ti_moneda
.a8
.i16
    lda #TI_ROJO
    sta temp + 1
    ldx #TI_TEXTO_MONEDA
    jsl f:ba_t_texto
    rts
.endproc

; Cuántas filas tiene la lista del modo: la de comprar tiene debajo la
; cuenta y el oro, y la de vender no.
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

; La pantalla entera, en el búfer: `pantallas.pantalla_tienda`. Las ventanas
; y la barra no: van en BG1, y las pone `ti_ventanas` en cada cuadro.
.proc ti_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    ; --- el mensaje: saludo, resaludo, o el del modo ---
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; Con `f:` porque `mensaje_de` es de acá, o sea del banco 1, y el banco de
    ; datos sigue siendo el 0: sin el largo, el absoluto leería el banco 0.
    lda f:mensaje_de, x
    bne con_mensaje
    lda comp_fase + 1             ; la principal: saludo o resaludo
con_mensaje:
    jsr ti_mensaje
    lda comp_col
    bne no_principal
    jmp principal
no_principal:
    ; --- la ayuda: la descripción del que marca el cursor ---
    lda comp_mask
    beq sin_ayuda
    jsr ti_item
    jsr eq_desc
sin_ayuda:
    ; --- el oro, y cuántos tiene y lleva puestos del que marca el cursor:
    ; en todos los modos de la capa de comprar, que son todos menos vender ---
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
    ; Los dos "listo" dejan la ventana del medio vacía, como RM2k.
    cmp #TI_COMPRADO
    beq vacia
    cmp #TI_VENDIDO
    beq vacia
    jmp lista
vacia:
    rts

    ; --- la cantidad: el ítem, "x" y cuántos, y el total ---
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
    jsr ti_por_cuantos          ; ti_num = precio * cuantos
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

    ; --- la principal: las órdenes, debajo del saludo ---
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
    jsr orden_mensaje           ; qué término: comprar, vender o salir
    jsr ti_renglon1
    pla
    inc a
    cmp comp_mask
    bcc orden
    rts

    ; --- la lista: comprar o vender ---
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
    sta comp_glifo + 1                  ; la fila, para las posiciones de abajo
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
    ; el color: comprando, si alcanza; vendiendo, si vale algo
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
    jsr eq_k                    ; el nombre, con la variante puesta
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
    ; comprando: el precio, alineado a la derecha
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
    ; vendiendo: cuántos tiene
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
    ; La fila que sigue, si la lista del modo la tiene: `ti_filas` no toca
    ; la pila.
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

; A: la orden de la principal. A16 = la posición de su fila: debajo del
; saludo, uno más abajo si el saludo tiene dos renglones.
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

; A: la fila de la lista. A16 = la posición de su fila.
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

; A: la orden. A = el número de mensaje: 2 comprar, 3 vender, 4 salir; con
; una sola orden, la que dice el tipo.
orden_mensaje:
    pha
    lda comp_col + 1
    beq tres
    pla
    lda comp_col + 1                 ; 1 compra: 2; 2 vende: 3
    inc a
    rts
tres:
    pla
    clc
    adc #2
    rts

; A: el número de mensaje. Su primer renglón, en `eleg_tabla`, en blanco.
ti_renglon1:
    jsr ti_texto_de
    stz temp + 1
    jsl f:ba_t_texto
    rts

; El mensaje de cada modo: 0 es "el saludo o el resaludo".
mensaje_de:
    .byte 0, 5, 6, 7, 8, 9, 10
.endproc

; `ti_num` por `ti_cuantos`, sumando: son 99 vueltas a lo sumo.
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

; Hasta cuántos se pueden comprar del que marca el cursor: los que faltan para
; 99, y no más de los que paga el oro. Vendiendo, los que tiene. En `ti_max`.
.proc ti_maximo
.a8
.i16
    jsr ti_item
    phx
    jsr eq_inv_apuntar
    lda WMDATA
    plx
    sta temp + 3                ; cuántos tiene
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
    sta temp + 3                ; los que faltan
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
    ; ¿eq_tmp >= precio? Si el precio es cero, siempre.
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

; Comprar o vender `ti_cuantos` del que marca el cursor: el oro y el
; inventario, como `UpdateNumberInput`.
.proc ti_cerrar_trato
.a8
.i16
    jsr ti_item
    jsr ti_precio
    jsr ti_por_cuantos
    lda comp_col
    cmp #TI_CUANTOS_VENTA
    beq vender
    ; --- comprar: el oro baja y los ítems suben ---
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
    ; --- vender: el oro sube, topado en ORO_MAX, y los ítems bajan ---
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

; `oro` más los 24 bits de `comp_or01`, topado en ORO_MAX: la mitad de
; `Game_Party::GainGold` que suma. La usan la venta de la tienda y la victoria
; —`ba_vic_empezar`—; `op_gold` tiene la suya porque vive en el banco 0.
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

; La lista de vender: el inventario que la ROM conoce, en `FAR_ITEM_LISTA`.
.proc ti_lista_venta
.a8
.i16
    jsl f:ba_t_armar
    lda eleg_n
    sta comp_mask
    lda comp_base
    cmp comp_mask
    bcc listo
    lda comp_mask                    ; se vendió el último: el cursor sube
    beq cero
    dec a
cero:
    sta comp_base
listo:
    rts
.endproc

; A: el modo nuevo. Pone lo que hace falta para entrar: la lista, el cursor.
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

; El cursor de la lista, con la vista que lo sigue.
.proc ti_mover
.a8
.i16
    sta comp_base
    cmp comp_base + 1
    bcs no_arriba
    sta comp_base + 1
    rts
no_arriba:
    jsr ti_filas                ; la de comprar y la de vender no miden igual
    sta temp + 3
    lda comp_base
    sec
    sbc comp_base + 1
    cmp temp + 3
    bcc listo
    lda comp_base
    sec
    sbc temp + 3
    inc a                       ; el cursor, en la última fila que se ve
    sta comp_base + 1
listo:
    rts
.endproc

; Las ventanas de la tienda, con la pantalla apagada y detrás del banco de la
; pantalla: la paleta roja de los términos —va con la de "sube", como en el
; equipo—, los colores y los tiles de las ventanas, y las filas de la ayuda,
; que son las mismas en las tres capas. El resto lo pone `ti_ventanas`.
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

; Las ventanas de BG1 debajo de la ayuda, y la barra: en el vblank de cada
; cuadro, detrás del texto, como `eq_barra`. Se suben las filas de la capa
; del modo —`ti_tramos`, de `ti_marco_filas`— y encima el rectángulo de la
; barra, de `ti_marco_parches`. Sin acordarse de nada: cada cuadro repone
; todo, así que ni la barra ni la capa anterior pueden quedar pintadas. Son
; 1408 bytes, más los de la barra, que con los 1792 del texto entran en el
; vblank —ver `pantallas.tienda_compacta`—.
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
    ; El lugar de la barra en su capa: la orden, la fila de la lista que se
    ; ve, o la cantidad. Los dos "listo" no tienen.
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
    lda #TI_LISTA_FILAS_COMPRA  ; la de la cantidad, detrás de las de la lista
    bra con_barra
en_lista:
    lda comp_mask
    beq sin_barra               ; la lista vacía no tiene cursor
    lda comp_base
    sec
    sbc comp_base + 1
    bra con_barra
en_principal:
    ; Con un saludo de dos renglones las órdenes bajan uno: ver `orden_pos`.
    jsr ti_dos_renglones
    beq un_renglon              ; y A quedó en cero
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
    asl a                       ; ocho bytes por barra
    tax
    lda f:ti_barras, x
    sta temp                    ; la palabra de la VRAM de la fila
    lda f:ti_barras + 2, x
    clc
    adc #.loword(ti_marco_parches)
    sta temp + 2                ; y de dónde sale
    lda f:ti_barras + 6, x
    tay                         ; cuántas filas
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

; A16 = la capa del modo, `pantallas.TI_CAPA_DE_MODO`. Vuelve con A de 16.
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

; La tienda: `ti_tipo`, `ti_juego` y `FAR_TIENDA` con `ti_nt` ítems, puestos
; por `op_shop`. Vuelve cuando el jugador sale.
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
    jsl f:pantalla_ppu_prender  ; BG2 y BG1, las ventanas con su base
    lda #1
    sta menu_abierto
espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; el control antes del DMA: ver el equipo
    jsl f:ba_t_subir
    jsr ti_ventanas
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    ; Según el modo. Sin `jmp (tabla, x)` en el ensamblador, una cadena.
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
:   jmp comprar                 ; comprar y vender comparten el código

    ; --- la principal ---
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

    ; --- las listas ---
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
    ; B: a la principal, con el resaludo; sin principal, afuera.
    lda comp_col + 1
    beq a_la_principal
    jmp salir
a_la_principal:
    lda comp_col
    cmp #TI_VENDER
    lda #0
    bcc cursor_listo
    lda #1                      ; el cursor sobre la orden de donde se vuelve
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
    beq espera2                 ; en gris: suena y no hace nada
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
    beq espera2                 ; no vale nada
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

    ; --- la cantidad ---
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
    ; Con signo, y topado en [1, ti_max].
    clc
    adc comp_color
    bmi c_uno                   ; bajó de cero: son 99 como mucho
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
    inc a                       ; CUANTOS_COMPRA -> COMPRADO, y la venta igual
    sta comp_col
    cmp #TI_VENDIDO
    bne recomponer
    jsr ti_lista_venta          ; lo vendido puede no estar más
    jmp recomponer

    ; --- el "listo", un segundo ---
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

; Z=0 si A se acaba de apretar.
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

