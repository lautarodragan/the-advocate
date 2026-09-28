.segment "CODE"

; --- la pantalla de ítems -------------------------------------------------------
;
; `Scene_Item`: arriba la descripción del ítem marcado, abajo la lista del
; inventario con cuántos hay. Tiene **banco de tiles propio**, `items_tiles`:
; cada carácter de la fuente en dos celdas, en blanco y en gris, y el texto
; —nombre y dos renglones de descripción por ítem— va en ASCII en
; `item_textos`. Escribir una letra son dos palabras del tilemap. La
; geometría es de `titulo.py` y `render_items` es la referencia.
;
; Las ventanas y el cursor —la barra del System— van en BG1, y son de
; `banco_de_la_pantalla.s`: el texto de BG2 no sabe nada de ellas.
;
; La lista se arma al entrar: los ítems que hay y que esta ROM conoce, en
; orden de número como `Game_Party`, guardados como su lugar `k` en las
; tablas del conversor, en `FAR_ITEM_LISTA`. Cuántos son, el primero que se ve
; y el cursor van en variables prestadas: `eleg_n`, `eleg_sel` y `titulo_sel`.
; La elección no puede estar abierta con el menú —el menú no se abre con un
; mensaje— así que sus bytes están libres; `eleg_cancel`, `eleg_flancos` y
; `eleg_tabla` hacen de escritorio, y `msg_ptr` apunta al texto que se
; escribe.
FAR_ITEM_LISTA = $2A00

; A: un lugar de la lista. Vuelve con A = su `k`. Sólo A.
.proc item_de_lista
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: un `k`. Vuelve con A = cuántos hay de ese ítem. Se lleva X.
.proc item_cuantos
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

; La lista, en `FAR_ITEM_LISTA`, y cuántos son en `eleg_n`.
.proc items_armar_lista
.a8
.i16
    stz eleg_n
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
    beq siguiente               ; uno que esta ROM no sabe mostrar
    pha
    rep #$20
.a16
    lda eleg_n
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    inc eleg_n
siguiente:
    inx
    cpx #ITEMS_N
    bcc otro
    rts
.endproc

; Una letra: A el carácter, Y la dirección de la celda de arriba y `temp + 1`
; la variante, 0 blanco y 1 gris. Se lleva X.
.proc glifo_par
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; cuatro bytes por carácter
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

; Un texto de un ítem: X el número de texto —`3k` el nombre, `3k + 1` y
; `3k + 2` los renglones de la descripción—, `eleg_tabla` la dirección de la
; celda de arriba de su primera letra y `temp + 1` la variante. Primero las
; celdas de arriba de todas las letras, que van seguidas en la VRAM, y
; después las de abajo.
.proc texto_escribir
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; cuántas letras
    beq listo
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #0                      ; las celdas de arriba
    sta temp + 2
    lda eleg_tabla
    sta VMADDL
    sep #$20
.a8
    jsr renglon
    rep #$20
.a16
    lda #2                      ; y las de abajo
    sta temp + 2
    lda eleg_tabla
    clc
    adc #32
    sta VMADDL
    sep #$20
.a8
    jsr renglon
listo:
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
    adc temp + 2                ; arriba o abajo
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
    sta VMDATAL                 ; y la VRAM avanza una palabra
    sep #$20
.a8
    iny
    tya                         ; de a una letra: son menos de 256
    cmp temp
    bcc letra
    rts
.endproc

; La descripción del ítem que marca el cursor, compuesta en `texto_buf` y no
; en la VRAM: son cuatro filas de celdas enteras —256 bytes— que
; `items_desc_subir` sube de un DMA. Escribirlas de a una palabra no entraba
; en el vblank: al mover el cursor el segundo renglón salía cortado, porque la
; VRAM ignora lo que se le escribe con la pantalla dibujando. El búfer es el
; del compositor de mensajes, que con el menú abierto no hay. Con la lista
; vacía queda en blanco.
ITEM_DESC_BYTES = 4 * 64

.proc items_desc_pintar
.a8
.i16
    ldx #0
borrar:
    stz texto_buf, x
    inx
    cpx #ITEM_DESC_BYTES
    bcc borrar
    lda eleg_n
    beq listo
    lda titulo_sel
    jsr item_de_lista
    rep #$20
.a16
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    inc a                       ; 3k + 1, el primer renglón
    tax
    lda #(ITEM_DESC_COL * 2)
    sta eleg_tabla              ; dónde va, en bytes del búfer
    sep #$20
.a8
    phx
    jsr renglon
    plx
    inx                         ; 3k + 2, el segundo
    rep #$20
.a16
    lda #(128 + ITEM_DESC_COL * 2)
    sta eleg_tabla
    sep #$20
.a8
    jsr renglon
listo:
    rts

; El texto X al búfer, desde el byte `eleg_tabla`: la celda de arriba de cada
; letra ahí y la de abajo 64 bytes más adelante.
renglon:
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; cuántas letras
    beq fin
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
    ldx eleg_tabla
    sta texto_buf + 64, x
    pla
    sta texto_buf, x
    inx
    inx
    stx eleg_tabla
    sep #$20
.a8
    iny
    tya                         ; de a una letra: son menos de 256
    cmp temp
    bcc letra
fin:
    rts
.endproc

; Sube la descripción compuesta: un DMA de 256 bytes, que entra en cualquier
; vblank.
.proc items_desc_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(ITEM_DESC_VRAM - ITEM_DESC_COL)
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #ITEM_DESC_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el búfer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; La fila A de la pantalla, que tiene que tener un ítem: el cursor si toca, el
; nombre, los dos puntos y la cantidad, en gris si A no lo usa.
.proc items_fila_pintar
.a8
.i16
    sta eleg_cancel             ; la fila
    lda eleg_cancel
    clc
    adc eleg_sel                ; su lugar en la lista
    pha
    jsr item_de_lista
    sta eleg_flancos            ; su `k`
    pla
    cmp titulo_sel
    bne sin_cursor
    lda #1
    sta temp + 3
    lda eleg_cancel
    jsl f:items_barra
sin_cursor:
    ; --- el color: gris si A no lo usa ---
    lda eleg_flancos
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
    ; --- el nombre ---
    lda eleg_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_NOMBRE_COL
    sta eleg_tabla
    lda eleg_flancos
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    tax                         ; 3k, el nombre
    sep #$20
.a8
    jsr texto_escribir
    ; --- los dos puntos y la cantidad ---
    lda eleg_flancos
    jsr item_cuantos
    cmp #100
    bcc cabe
    lda #99
cabe:
    stz temp + 3                ; las decenas
decenas:
    cmp #10
    bcc unidades
    sbc #10                     ; el `cmp` dejó el acarreo puesto
    inc temp + 3
    bra decenas
unidades:
    pha                         ; las unidades
    lda eleg_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_DOS_PUNTOS_COL
    sta eleg_tabla
    tay
    sep #$20
.a8
    lda #$3A                    ; ':'
    jsr glifo_par
    rep #$20
.a16
    lda eleg_tabla
    inc a
    tay
    sep #$20
.a8
    lda temp + 3
    beq sin_decenas             ; un 7 es " 7", no "07"
    clc
    adc #$30                    ; '0'
    jsr glifo_par
sin_decenas:
    rep #$20
.a16
    lda eleg_tabla
    inc a
    inc a
    tay
    sep #$20
.a8
    pla
    clc
    adc #$30                    ; '0'
    jmp glifo_par
.endproc


; Las filas que se ven, sobre el tilemap en blanco.
.proc items_filas_pintar
.a8
.i16
    lda #0
fila:
    pha
    clc
    adc eleg_sel
    bcs termina
    cmp eleg_n
    bcs termina                 ; no hay más ítems
    pla
    pha
    jsr items_fila_pintar
    pla
    inc a
    cmp #ITEM_FILAS
    bcc fila
    rts
termina:
    pla
    rts
.endproc

; La pantalla de ítems, hasta que el jugador vuelve con B —A = 0, al menú— o
; usa un ítem —A = 1: RM2k vuelve derecho al mapa, `PopUntil(Scene::Map)`—.
.proc items_pantalla
.a8
.i16
    jsr items_armar_lista
    stz titulo_sel
    stz eleg_sel
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_pantalla_subir
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    jsl f:items_ppu_prender
    lda #1
    sta menu_abierto
espera:
    jsr wait_vblank
    jsr items_desc_subir        ; lo primero del vblank: la descripción
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    beq espera                  ; RM2k no da la vuelta en una lista
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp eleg_n
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    lda #0
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda eleg_n
    beq espera                  ; la lista vacía
    lda titulo_sel
    jsr item_de_lista
    sta eleg_flancos            ; su `k`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda item_uso, x
    and #1
    beq espera                  ; en gris: RM2k suena y no hace nada
    lda item_uso, x
    and #4
    beq de_switch
    ; Una medicina: la elección de actor, y de vuelta a la lista con el cursor
    ; donde estaba. La elección usa `titulo_sel`, así que se guarda.
    lda titulo_sel
    pha
    lda eleg_sel
    pha
    stz eleg_cancel             ; para una medicina, la de `eleg_flancos`
    jsr objetivo_pantalla
    pla
    sta eleg_sel
    pla
    sta titulo_sel
    ; La lista de nuevo, que es `Scene_Item::Continue`: la medicina pudo
    ; haberse gastado entera. El cursor que quedó afuera va al último, el
    ; `SetIndex(min(index, item_max - 1))` de allá, y la vista lo sigue.
    jsr items_armar_lista
    lda eleg_n
    beq vacia
    lda titulo_sel
    cmp eleg_n
    bcc cursor_listo
    lda eleg_n
    dec a
    sta titulo_sel
    bra cursor_listo
vacia:
    stz titulo_sel
cursor_listo:
    lda titulo_sel
    cmp eleg_sel
    bcs vista_lista
    sta eleg_sel
vista_lista:
    lda #$80
    sta INIDISP
    jsl f:items_pantalla_subir
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    jsl f:items_ppu_prender
    jmp espera
de_switch:
    ; Un ítem de switch: `ConsumeItemUse` si tiene usos, el switch prendido y
    ; derecho al mapa. `poner_switch` pide el refresco de páginas, que es el
    ; `SetNeedRefresh(true)` de allá.
    lda item_uso, x
    and #2
    beq sin_gastar
    lda eleg_flancos
    jsr item_cuantos
    dec a
    pha
    lda eleg_flancos
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
    lda eleg_flancos
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_switch, x        ; vive en RODATA: ver el conversor
    sta temp
    sep #$20
.a8
    lda #1
    jsr poner_switch
    lda #1
    rts

; El cursor al lugar que trae A. Si queda a la vista se mueve el cursor y se
; cambia la descripción, adentro del vblank; si no, la lista se corre y se
; repinta entera con la pantalla apagada, que es un cuadro en negro.
mover:
    pha
    stz temp + 3
    lda titulo_sel
    sec
    sbc eleg_sel
    jsl f:items_barra
    pla
    sta titulo_sel
    cmp eleg_sel
    bcc sube_la_vista
    sec
    sbc eleg_sel
    cmp #ITEM_FILAS
    bcs baja_la_vista
    lda #1
    sta temp + 3
    lda titulo_sel
    sec
    sbc eleg_sel
    jsl f:items_barra
    jmp items_desc_pintar
sube_la_vista:
    lda titulo_sel
    sta eleg_sel
    bra repintar
baja_la_vista:
    lda titulo_sel
    sec
    sbc #(ITEM_FILAS - 1)
    sta eleg_sel
repintar:
    lda #$80
    sta INIDISP
    jsl f:items_pantalla_subir  ; el tilemap en blanco, y de paso el resto
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    lda #$0F
    sta INIDISP
    rts
.endproc

