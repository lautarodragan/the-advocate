.segment "FAR"

; --- la experiencia en el menú -----------------------------------------------
;
; La tercera línea de `Window_MenuStatus`: "Ex", la experiencia de ahora y la
; que pide el nivel que sigue, `"%6d/%6d"`. **Va en sprites**, doce pixeles
; debajo de los HP y a los seis pixeles de la fuente: en la grilla de celdas
; no había dónde. El porqué y la geometría están en `MENU_EXP_X`, en
; titulo.py, y `render_menu` es la referencia.
;
; Los sprites leen sus tiles desde `RANURA_VRAM`, así que el tile de un glifo
; del banco es el mismo número, y su paleta 0 es una copia de la del texto.
; Ninguna otra pantalla prende los sprites —`ranura_ppu_prender` deja sólo
; BG2—, así que la elección de actor, que comparte el panel, no la muestra, que
; es lo de `Window_ActorTarget`. Lo que esto cambia del mapa —OBSEL y los
; colores 128 a 143— lo repone `menu_exp_cerrar` al volver.
;
; Corre con la pantalla apagada: la OAM se escribe derecho por el puerto, y
; nada la pisa mientras el menú se ve porque `flush_video` no corre.
;
; El escritorio son variables prestadas del compositor de mensajes, que con el
; menú abierto no hay:
;   comp_char       la fila del grupo
;   comp_fase       el y de arriba de los sprites de la fila
;   comp_fase + 1   el y del sprite que se pone
;   comp_mask       su x
;   comp_base       cuántos sprites van puestos
;   comp_dup        el nivel del actor
;   comp_or01       el número que se escribe, de 24 bits
;   comp_and        la resta de prueba
;   comp_col        la cifra que se cuenta
;   comp_col + 1    si ya salió una cifra

MENU_EXP_TERM_TILES = 4         ; el término: dos de ancho, arriba y abajo
MENU_EXP_OCULTO = 224           ; un y debajo de la última línea que se ve
MENU_EXP_SPRITES = 128

.assert MENU_EXP_TEXTO + MENU_EXP_LETRAS <= MENU_EXP_TEXTO_FIN, error, "la línea de la experiencia no entra en su lugar"
.assert MENU_FILAS_GRUPO * (MENU_EXP_TERM_TILES + 2 * MENU_EXP_LETRAS) <= MENU_EXP_SPRITES, error, "la experiencia del grupo no entra en los sprites"

; Desde `menu_subir`, en lugar de `ranura_ppu_prender`: los sprites, y después
; prende la pantalla con ellos. Con la pantalla apagada.
.proc menu_exp_pintar
.a8
.i16
    phb
    lda #0
    pha
    plb                         ; los registros y las tablas del banco 0
    ; Sprites de 8x8 con los tiles desde `RANURA_VRAM`.
    lda #(RANURA_VRAM / $2000)
    sta OBSEL
    ; La paleta 0 de los sprites, la del texto.
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(ranura_cgram)
    sta A1T0L
    lda #(16 * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ranura_cgram
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    stz OAMADDL
    stz OAMADDL + 1
    stz comp_base               ; ningún sprite todavía
    stz comp_char
    lda #MENU_EXP_Y
    sta comp_fase
fila:
    lda comp_char
    cmp grupo_n
    bcs filas_listas
    cmp #MENU_FILAS_GRUPO
    bcs filas_listas
    jsr una_fila
    lda comp_fase
    clc
    adc #MENU_ACTOR_ALTO
    sta comp_fase
    inc comp_char
    bra fila
filas_listas:
    ; Los que sobran, debajo de la pantalla, y la tabla chica en cero: la x
    ; de ocho bits y el tamaño chico para todos.
    lda comp_base
    cmp #MENU_EXP_SPRITES
    bcs ocultos_listos
    stz OAMDATA
    lda #MENU_EXP_OCULTO
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    inc comp_base
    bra filas_listas
ocultos_listos:
    ldx #(MENU_EXP_SPRITES / 4)
tabla_chica:
    stz OAMDATA
    dex
    bne tabla_chica

    jsl f:ba_t_ppu              ; la pantalla, prendida con BG2 solo
    lda #$12                    ; y los sprites encima
    sta TM
    plb
    rtl

; La línea de la fila `comp_char`, si su actor tiene experiencia.
una_fila:
    rep #$20
.a16
    lda comp_char
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    cmp #MENU_ACTORES_N
    bcc conocido
    rts                         ; uno que esta ROM no conoce
conocido:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne con_exp
    rts                         ; uno que no pelea: no tiene experiencia
con_exp:
    rep #$20
.a16
    and #$00FF
    pha                         ; k, hasta el final de la línea
    asl a
    asl a
    tax                         ; su ranura de `FAR_EXP`
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_EXP + EXP_NIVEL, x
    sta comp_dup
    ; ¿En el tope? Guiones, como el RPG_RT.
    rep #$20
.a16
    lda 1, s                    ; k
    phx
    tax
    sep #$20
.a8
    lda f:exp_nivel_max, x
    plx
    cmp comp_dup
    beq tope
    bcc tope
    ; La de ahora.
    rep #$20
.a16
    lda f:FAR_LARGO + FAR_EXP, x
    sta comp_or01
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_EXP + 2, x
    sta comp_or01 + 2
    ldy #0
    jsr seis_cifras
    lda #'/'
    tyx
    sta f:MENU_EXP_TEXTO, x
    iny
    ; Y la del nivel que sigue: la fila de su curva en `exp_tabla`, en el
    ; nivel de ahora, que es `GetNextExp(level)`.
    rep #$20
.a16
    pla                         ; k
    asl a
    tax
    lda comp_dup
    and #$00FF
    asl a
    asl a                       ; cuatro bytes por nivel
    clc
    adc f:exp_curva, x
    tax
    lda f:exp_tabla, x
    sta comp_or01
    sep #$20
.a8
    lda f:exp_tabla + 2, x
    sta comp_or01 + 2
    jsr seis_cifras
    bra sprites
tope:
    rep #$20
.a16
    pla                         ; k, que no hace falta
    sep #$20
.a8
    ldx #0
guion:
    lda #'-'
    cpx #MENU_EXP_CIFRAS
    bne no_barra
    lda #'/'
no_barra:
    sta f:MENU_EXP_TEXTO, x
    inx
    cpx #MENU_EXP_LETRAS
    bcc guion

sprites:
    ; --- el término: cuatro tiles, dos arriba y dos abajo ---
    ldx #0
termino:
    lda #MENU_EXP_X
    cpx #1
    beq term_der
    cpx #3
    bne term_x
term_der:
    lda #(MENU_EXP_X + 8)
term_x:
    sta comp_mask
    lda comp_fase
    cpx #2
    bcc term_y
    clc
    adc #8
term_y:
    sta comp_fase + 1
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:menu_exp_termino, x
    jsr poner
.a8
    plx
    inx
    cpx #MENU_EXP_TERM_TILES
    bcc termino

    ; --- las trece letras, a seis pixeles; un espacio no lleva sprite ---
    lda #MENU_EXP_NUM_X
    sta comp_mask
    ldx #0
letra:
    lda f:MENU_EXP_TEXTO, x
    cmp #' '
    beq siguiente
    phx
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; dos palabras por letra
    tax
    sep #$20
.a8
    lda comp_fase
    sta comp_fase + 1
    rep #$20
.a16
    lda f:ranura_glifo_celdas, x
    jsr poner                   ; la celda de arriba
.a8
    lda comp_fase
    clc
    adc #8
    sta comp_fase + 1
    rep #$20
.a16
    lda f:ranura_glifo_celdas + 2, x
    jsr poner                   ; y la de abajo
.a8
    plx
siguiente:
    lda comp_mask
    clc
    adc #MENU_EXP_PASO
    sta comp_mask
    inx
    cpx #MENU_EXP_LETRAS
    bcc letra
    rts

; Un sprite: A16 la palabra del tilemap del glifo —tile y paleta—, en
; `comp_mask`, `comp_fase + 1`. Vuelve con A en 8 bits, y no toca X ni Y.
.a16
poner:
    sep #$20
.a8
    pha                         ; el byte bajo del tile
    lda comp_mask
    sta OAMDATA
    lda comp_fase + 1
    sta OAMDATA
    pla
    sta OAMDATA
    xba                         ; el byte alto de la palabra: el bit 8 del
    and #$01                    ; tile, y la paleta de BG2 que es la 0
    ora #$30                    ; prioridad 3, paleta 0 de los sprites
    sta OAMDATA
    inc comp_base
    rts

; `comp_or01`: un número de 24 bits, menor que un millón. Escribe sus seis
; cifras en `MENU_EXP_TEXTO` desde Y, alineadas a la derecha con espacios, y
; deja Y detrás. Se lleva X.
seis_cifras:
    stz comp_col + 1
    ldx #0
potencia:
    stz comp_col
resta:
    rep #$20
.a16
    lda comp_or01
    sec
    sbc f:potencias, x
    sta comp_and
    sep #$20                    ; `sep` no toca el carry de la resta
.a8
    lda comp_or01 + 2
    sbc f:potencias + 2, x
    bcc no_alcanza
    sta comp_or01 + 2
    rep #$20
.a16
    lda comp_and
    sta comp_or01
    sep #$20
.a8
    inc comp_col
    bra resta
no_alcanza:
    lda comp_col
    ora comp_col + 1
    bne cifra
    cpx #(5 * 3)
    beq cifra                   ; las unidades van siempre, aunque sean 0
    lda #' '
    bra escribir
cifra:
    lda #1
    sta comp_col + 1
    lda comp_col
    clc
    adc #'0'
escribir:
    phx
    tyx
    sta f:MENU_EXP_TEXTO, x
    plx
    iny
    inx
    inx
    inx
    cpx #(6 * 3)
    bcc potencia
    rts

potencias:
    .faraddr 100000, 10000, 1000, 100, 10, 1
.endproc

; Al cerrar el menú, antes de `volver_al_mapa`: lo que `menu_exp_pintar` le
; cambió al mapa y el mapa no repone solo. OBSEL, que `volver_al_mapa` no
; toca, y los colores de la paleta 0 de los sprites, desde `cgram_sombra`, que
; tiene los del mapa aunque el tinte o una imagen los hayan cambiado. Apaga la
; pantalla, que `volver_al_mapa` apaga igual.
.proc menu_exp_cerrar
.a8
.i16
    phb
    lda #0
    pha
    plb
    lda #$80
    sta INIDISP
    ldx mapa_ofs
    lda f:mapa_tabla + M_OBSEL_VALUE, x
    sta OBSEL
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * 128)
    sta A1T0L
    lda #(16 * 2)
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; la sombra vive en el banco 0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    plb
    rtl
.endproc
