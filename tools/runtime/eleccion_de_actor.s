.segment "FAR"

; --- las ventanas de la elección de actor -----------------------------------
;
; `Scene_ActorTarget` con las ventanas del System en BG1, como ítems y equipo:
; a la izquierda el nombre de la medicina y "Owned Items" con la cantidad, a
; la derecha el grupo, y la barra roja sobre la fila marcada. La pantalla
; sigue siendo `objetivo_pantalla`, en el banco 0, con el banco del menú en
; BG2; esto es lo que le suma, fuera del banco 0. La geometría y el porqué
; están en `OBJETIVO_VENTANAS`, en titulo.py, y `render_objetivo` es la
; referencia.
;
; BG1 tiene **su propia base**, `OBJETIVO_VRAM`, detrás del tilemap del menú:
; en la de BG2 no queda lugar, porque el banco del menú llega casi hasta su
; tilemap. Todo cae en lo que `load_map` repone al cerrar el menú —lo
; controla `_controlar_objetivo`—, y los colores van en 128..143, que son los
; de los sprites del menú y los repone `menu_exp_cerrar`.
;
; `eleg_cancel` dice cuál: en 0, para la medicina de `eleg_flancos`, con las
; dos ventanas de la izquierda; si no, para elegir a quién equipar, sin ellas.
; Se entra con `jsl`, con el banco de datos en el 0: los registros y
; `item_id` van en absoluto.

; Las ventanas, y el nombre y la cantidad si es una medicina. Con la pantalla
; apagada, detrás de `ranura_banco_subir`.
.proc objetivo_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #OBJETIVO_VRAM
    sta VMADDL
    lda #(OBJETIVO_TILES * 64)
    sta DAS0L
    lda #.loword(objetivo_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; El tilemap, que es uno solo: el con ítem. Sin ítem se le borran las
    ; celdas de las dos ventanas de la izquierda —ver `objetivo_compacto`—.
    rep #$20
.a16
    lda #OBJETIVO_MAPA
    sta VMADDL
    lda #(32 * 28 * 2)
    sta DAS0L
    lda #.loword(objetivo_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_mapa)
    sta A1B0
    lda #$01
    sta MDMAEN
    lda eleg_cancel
    beq colores
    rep #$20
.a16
    lda #OBJETIVO_MAPA
borrar_fila:
    sta VMADDL
    ldx #OBJETIVO_BORRAR_COLS
borrar_celda:
    stz VMDATAL                 ; las dos mitades de la palabra: A de 16
    dex
    bne borrar_celda
    clc
    adc #32
    cmp #(OBJETIVO_MAPA + OBJETIVO_BORRAR_FILAS * 32)
    bcc borrar_fila
    sep #$20
.a8
colores:
    ; Los colores.
    lda #OBJETIVO_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(OBJETIVO_COLORES * 2)
    sta DAS0L
    lda #.loword(objetivo_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(objetivo_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda eleg_cancel
    beq nombre
    rtl
nombre:
    ; Los dos renglones del nombre: `objetivo_nombres` tiene
    ; 2 * OBJETIVO_NOMBRE_ANCHO letras por medicina, y `objetivo_nombre_de`
    ; dice cuál es la del `k`.
    rep #$20
.a16
    lda eleg_flancos
    and #$00FF
    tax
    lda f:objetivo_nombre_de, x
    and #$00FF
    sta temp
    asl a
    asl a
    clc
    adc temp                    ; k * 5
    asl a
    asl a
    clc
    adc temp                    ; k * 21
    clc
    adc temp                    ; k * 22
    .assert OBJETIVO_NOMBRE_ANCHO = 11, error, "el nombre se indexa por k * 22"
    tax
    ldy #OBJETIVO_NOMBRE_VRAM
    jsr renglon
    rep #$20
.a16
    txa
    clc
    adc #OBJETIVO_NOMBRE_ANCHO
    tax
    ldy #(OBJETIVO_NOMBRE_VRAM + 64)
    jsr renglon
    jmp objetivo_cuantos

; Un renglón: X su primera letra en `objetivo_nombres`, Y la celda. Las celdas
; de arriba de todas las letras y después las de abajo, como
; `ranura_texto_escribir`. Deja X como estaba y vuelve con A de 8 bits.
renglon:
    sep #$20
.a8
    sty VMADDL
    stz temp + 2                ; las celdas de arriba
    stz temp + 3
    jsr pasada
    rep #$20
.a16
    tya
    clc
    adc #32                     ; y las de abajo
    sta VMADDL
    sep #$20
.a8
    lda #2
    sta temp + 2
pasada:
    phx
    lda #OBJETIVO_NOMBRE_ANCHO
    sta temp
letra:
    lda f:objetivo_nombres, x
    phx
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; cuatro bytes por glifo
    clc
    adc temp + 2
    tax
    lda f:ranura_glifo_celdas, x
    sta VMDATAL
    sep #$20
.a8
    plx
    inx
    dec temp
    bne letra
    plx
    rts
.endproc

; Cuántos quedan de la medicina de `eleg_flancos`, en dos cifras —la de las
; decenas en blanco si es cero—, al lado de "Owned Items". En el vblank
; después de usarla, o con la pantalla apagada al abrir. Sin medicina, nada.
.proc objetivo_cuantos
.a8
.i16
    lda eleg_cancel
    beq medicina
    rtl
medicina:
    rep #$20
.a16
    lda eleg_flancos
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
    ldx #0
diez:
    cmp #10
    bcc unidades
    sbc #10
    inx
    bra diez
unidades:
    sta temp + 1                ; las unidades
    txa
    sta temp                    ; y las decenas
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #OBJETIVO_CUANTOS_VRAM
    sta VMADDL
    sep #$20
.a8
    stz temp + 2                ; las celdas de arriba
    jsr dos
    rep #$20
.a16
    lda #(OBJETIVO_CUANTOS_VRAM + 32)
    sta VMADDL
    sep #$20
.a8
    lda #2                      ; y las de abajo
    sta temp + 2
    jsr dos
    rtl

dos:
    lda temp
    beq blanco
    clc
    adc #('0' - ITEM_PRIMER_CARACTER)
blanco:                         ; el espacio es el primer glifo
    jsr glifo
    lda temp + 1
    clc
    adc #('0' - ITEM_PRIMER_CARACTER)
glifo:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    clc
    adc temp + 2
    and #$00FF                  ; `temp + 3` no es parte del desplazamiento
    tax
    lda f:ranura_glifo_celdas, x
    sta VMDATAL
    sep #$20
.a8
    rts
.endproc

; La barra en la fila A del grupo: `temp + 3` en 1 la pinta y en 0 la borra.
; Las dos cosas son copiar el rectángulo de BG1 donde la barra cambia algo
; —`OBJETIVO_BARRA_FILAS` por `OBJETIVO_BARRA_COLS` celdas, ver
; `objetivo_compacto`—: de `objetivo_barras`, que lo tiene con la barra, o del
; tilemap. Un DMA por fila de celdas, que con la de borrar y la de pintar
; entran en el vblank. Con ítem y sin ítem es el mismo: el rectángulo no toca
; las ventanas de la izquierda. Se lleva `temp` a `temp + 3`: el que llama
; vuelve a poner `temp + 3` antes de cada vez.
BARRA_BYTES = OBJETIVO_BARRA_FILAS * OBJETIVO_BARRA_COLS * 2
.proc objetivo_barra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:fila_vram, x          ; la primera celda del rectángulo
    sta temp                    ; `temp` y `temp + 1`
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda temp + 3
    beq borra
    lda #^(objetivo_barras)
    sta A1B0
    rep #$20
.a16
    lda f:barra_ofs, x
    clc
    adc #.loword(objetivo_barras)
    ldy #(OBJETIVO_BARRA_COLS * 2) ; el rectángulo va seguido
    bra filas
.a8
borra:
    lda #^(objetivo_mapa)
    sta A1B0
    rep #$20
.a16
    lda temp
    sec
    sbc #OBJETIVO_MAPA
    asl a                       ; de palabras de la VRAM a bytes del tilemap
    clc
    adc #.loword(objetivo_mapa)
    ldy #64                     ; una fila entera del tilemap
filas:
    sty temp + 2                ; cuánto avanza el origen por fila
    ldx #OBJETIVO_BARRA_FILAS
fila:
    sta A1T0L
    pha
    lda temp
    sta VMADDL
    clc
    adc #32
    sta temp
    lda #(OBJETIVO_BARRA_COLS * 2)
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    dex
    bne fila
    sep #$20
.a8
    rtl

PRIMERA = OBJETIVO_MAPA + OBJETIVO_BARRA_FILA0 * 32 + OBJETIVO_BARRA_COL0
FILA = MENU_ACTOR_FILAS * 32
fila_vram:
    .word PRIMERA, PRIMERA + FILA, PRIMERA + 2 * FILA, PRIMERA + 3 * FILA
barra_ofs:
    .word 0, BARRA_BYTES, 2 * BARRA_BYTES, 3 * BARRA_BYTES
    .assert MENU_FILAS_GRUPO = 4, error, "una palabra por fila del grupo"
.endproc

; BG2 con el grupo y BG1 con las ventanas, cada una con su base, y la
; pantalla prendida. Es `ranura_ppu_prender` más BG1.
.proc objetivo_ppu_prender
.a8
.i16
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(OBJETIVO_MAPA / 1024 * 4)
    sta BG1SC
    lda #(RANURA_VRAM / 4096 * 16 + OBJETIVO_VRAM / 4096)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    stz BG1HOFS
    stz BG1HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    sta BG1VOFS
    sta BG1VOFS
    lda #$03
    sta TM
    lda #$0F
    sta INIDISP
    rtl
.endproc
