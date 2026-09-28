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
    ; El tilemap, con o sin las ventanas de la izquierda.
    rep #$20
.a16
    lda #OBJETIVO_MAPA
    sta VMADDL
    lda #(32 * 28 * 2)
    sta DAS0L
    sep #$20
.a8
    lda eleg_cancel
    bne sin_item
    lda #^(objetivo_mapa)
    ldx #.loword(objetivo_mapa)
    bra mapa
sin_item:
    lda #^(objetivo_mapa_sin)
    ldx #.loword(objetivo_mapa_sin)
mapa:
    sta A1B0
    stx A1T0L
    lda #$01
    sta MDMAEN
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
    ; 2 * OBJETIVO_NOMBRE_ANCHO letras por ítem, por su `k`.
    rep #$20
.a16
    lda eleg_flancos
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
; Las dos cosas son copiar las filas de celdas de BG1 de la fila del actor
; —de `objetivo_barras`, que las tiene con la barra, o del tilemap sin ella—:
; 448 bytes por DMA, que con la de borrar y la de pintar entran en el vblank.
.proc objetivo_barra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:fila_ofs, x           ; los bytes desde la primera fila
    tay
    lsr a
    clc
    adc #OBJETIVO_MAPA
    sta VMADDL
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda eleg_cancel
    bne sin_item
    lda temp + 3
    beq con_borra
    lda #^(objetivo_barras)
    ldx #.loword(objetivo_barras)
    bra fuente
con_borra:
    lda #^(objetivo_mapa)
    ldx #.loword(objetivo_mapa)
    bra fuente
sin_item:
    lda temp + 3
    beq sin_borra
    lda #^(objetivo_barras_sin)
    ldx #.loword(objetivo_barras_sin)
    bra fuente
sin_borra:
    lda #^(objetivo_mapa_sin)
    ldx #.loword(objetivo_mapa_sin)
fuente:
    sta A1B0
    rep #$20
.a16
    phy
    txa
    clc
    adc 1, s
    sta A1T0L
    ply
    lda #(MENU_ACTOR_FILAS * 64)
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl

fila_ofs:
    .word 0, MENU_ACTOR_FILAS * 64, 2 * MENU_ACTOR_FILAS * 64
    .word 3 * MENU_ACTOR_FILAS * 64
    .assert MENU_FILAS_GRUPO = 4, error, "una fila de `fila_ofs` por fila del grupo"
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
