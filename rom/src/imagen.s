; --- el cartel del ShowPicture ----------------------------------------------
;
; Seis objetos de 32x32 con una paleta de sprite para ellos solos, y un fundido
; que es un tinte de esos quince colores cuadro a cuadro. Ver `tools/port/imagen.py`,
; que es donde está escrito dónde cae y de qué color es cada pixel, y OP_PICTURE
; en eventos.py.
;
; El cartel vive en **un solo mapa** de la ROM —el que se llevó sus tiles al
; banco de sprites; el conversor corta si otro lo muestra— y se borra al
; cambiar de mapa, que es el
; `erase_on_map_change` de `Game_Pictures`. Las dos cosas son la misma: sin sus
; tiles en VRAM no habría qué dibujar.

; Un cuadro de la rampa. `Game_Pictures::Picture::Update` interpola con
; `(finish - current) / dt` sobre `double`, y el resultado exacto de esa
; sucesión es lineal: `desde + (hasta - desde) * paso / pasos`. Acá va con
; enteros, y el signo se saca antes de dividir: el divisor del hardware no lo
; tiene.
;
; La paleta se rehace **sólo cuando el tono cambió de verdad**. En la rampa de
; 210 cuadros del "1 year earlier" el rojo sube de 0 a 100, o sea que cambia
; uno de cada dos cuadros: rehacerla igual costaba 96 productos y 96 divisiones
; por cuadro para escribir los mismos treinta y dos bytes.
.proc imagen_tick
.a8
.i16
    lda f:CARTEL_ACTIVA
    beq listo
    lda f:CARTEL_PASOS
    beq listo                   ; puesto y quieto
    lda f:CARTEL_PASO
    cmp f:CARTEL_PASOS
    bcs listo                   ; la rampa ya llegó
    lda f:CARTEL_PASO           ; `inc` no tiene forma larga
    inc a
    sta f:CARTEL_PASO
    jsr imagen_tono_ahora
    beq listo                   ; el mismo tono que el cuadro pasado
    jmp imagen_paleta
listo:
    rts
.endproc

; El tono de este cuadro, canal por canal. Deja en A si cambió alguno.
;
; La resta va siempre del lado positivo, como en `una_tabla_de_destello`: el
; divisor del hardware no tiene signo, y `//` de Python redondea para el otro
; lado con negativos. Los dos lados hacen esta misma cuenta partida en dos.
.proc imagen_tono_ahora
.a8
.i16
    lda #0
    sta f:CARTEL_CAMBIO
    ldx #$0000
canal:
    lda f:CARTEL_HASTA, x
    cmp f:CARTEL_DESDE, x
    bcc baja
    sec
    sbc f:CARTEL_DESDE, x
    jsr imagen_parte
    clc
    adc f:CARTEL_DESDE, x
    bra guardar
baja:
    lda f:CARTEL_DESDE, x
    sec
    sbc f:CARTEL_HASTA, x
    jsr imagen_parte
    eor #$FF                    ; `desde - parte` sin una variable de por medio:
    sec                         ; el complemento a uno más el acarreo es el menos
    adc f:CARTEL_DESDE, x
guardar:
    cmp f:CARTEL_TONO, x
    beq igual
    sta f:CARTEL_TONO, x
    lda #1
    sta f:CARTEL_CAMBIO
igual:
    inx
    cpx #3
    bne canal
    lda f:CARTEL_CAMBIO
    rts
.endproc

; A = A * CARTEL_PASO / CARTEL_PASOS, con el multiplicador y el divisor del
; hardware. El producto llega a 200 * 255 y entra en dieciséis bits; el
; cociente no pasa de 200, así que alcanza con el byte bajo.
.proc imagen_parte
.a8
.i16
    sta WRMPYA
    lda f:CARTEL_PASO
    sta WRMPYB
    nop                         ; ocho ciclos hasta que el producto está
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, de dieciséis bits
    sep #$20
.a8
    lda f:CARTEL_PASOS
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    rts
.endproc

; Los dieciséis colores del cartel teñidos con su tono, en su lugar de
; `cgram_sombra`. Los sube `flush_video` en el vblank con un DMA propio.
;
; Se reusan `tabla_canal` y `armar_paleta`, que es lo que el tinte de pantalla
; ya hacía: la única diferencia es de dónde salen los tres valores y que la
; saturación del cartel es siempre neutra —`imagen_aceptable` no acepta otra—,
; así que se le pone la neutra a `tinte_s` mientras dura y se la devuelve.
; Las tres tablas de trabajo quedan con el tinte del cartel; `restaurar_tablas`
; las vuelve a dejar como las del tinte de pantalla, copiando `puro`, que es
; mucho más barato que rehacerlas.
.proc imagen_paleta
.a8
.i16
    ; **Y se guarda.** `armar_paleta` la usa de cursor de la paleta y la deja
    ; en 32, y quien llama a esto desde un opcode la tiene apuntando al
    ; bytecode: sin esto el intérprete seguía leyendo treinta y dos bytes más
    ; adelante y corría lo que hubiera ahí. Fue el primer rojo de este cartel,
    ; y de los que no se ven: la página seguía corriendo, sólo que otra.
    phy
    lda tinte_s
    pha
    lda #TINTE_NEUTRO
    sta tinte_s
    lda f:CARTEL_TONO + 0
    ldx #.loword(tabla_r)
    jsr tabla_canal
    lda f:CARTEL_TONO + 1
    ldx #.loword(tabla_g)
    jsr tabla_canal
    lda f:CARTEL_TONO + 2
    ldx #.loword(tabla_b)
    jsr tabla_canal
    rep #$20
.a16
    lda #.loword(imagen_cgram)
    sta tin_ptr
    lda #16
    sta tin_count
    sep #$20
.a8
    lda #^imagen_cgram
    sta tin_ptr + 2
    jsr armar_paleta            ; los dieciséis, teñidos, en `pal_buf`
    ; Y de ahí a la sombra, **sin tocar `tinte_listo`**: prenderlo mandaría a
    ; subir las tres paletas del mapa en cada cuadro de la rampa, y eso le come
    ; al vblank el presupuesto de poses.
    ldx #$0000
copia:
    lda pal_buf, x
    sta cgram_sombra + 2 * (128 + 16 * IMAGEN_PAL), x
    inx
    cpx #32
    bne copia
    pla
    sta tinte_s
    lda #1
    sta f:CARTEL_LISTO
    jsr restaurar_tablas
    ply
    rts
.endproc

; Los objetos del cartel, si está puesto.
;
; Van **después del cronómetro y antes de los personajes**, que es el orden de
; RM2k: `Priority_Timer` es 140, `Priority_PictureOld` 120 y `Priority_Player`
; 40. En OAM eso es el orden de la lista, porque gana el índice más bajo; y la
; prioridad 3 los pone adelante de las dos capas.
;
; Cuestan **veinticuatro de los treinta y cuatro tiles por línea** en las
; veintinueve líneas que ocupan, así que ahí entran dos personajes más y no
; más. La referencia cuenta lo mismo y declara las líneas donde no alcanza.
.proc imagen_oam
.a8
.i16
    lda f:CARTEL_ACTIVA
    bne hay
    rts
hay:
    lda #$02
    sta obj_grande              ; los objetos del cartel son de 32x32
    lda #0
    sta f:CARTEL_I
cada:
    rep #$20
.a16
    lda f:CARTEL_I
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; treinta y dos por objeto
    clc
    adc #IMAGEN_X & $FFFF       ; es negativo, y ca65 no acepta un inmediato negativo
    sta obj_x
    lda #IMAGEN_Y
    sta obj_y
    ; Y qué tile. Un objeto de 32x32 lee cuatro tiles de cuatro filas seguidas
    ; de la grilla de nombres, que es de dieciséis: o sea que en una fila de
    ; bloques entran cuatro objetos y el quinto arranca 64 tiles más adelante.
    lda f:CARTEL_I
    and #$0003
    asl a
    asl a                       ; los cuatro de ancho del objeto
    sta temp
    lda f:CARTEL_I
    and #$00FC
    asl a
    asl a
    asl a
    asl a                       ; y la fila de bloques, que son 64 por cada 4
    clc
    adc temp
    clc
    adc #IMAGEN_BASE
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: prioridad 3 —adelante de las dos capas—, la paleta del cartel,
    ; y el noveno bit del tile.
    lda temp + 1
    and #$01
    ora #($30 | (IMAGEN_PAL * 2))
    sta obj_attr
    jsr emit_object
    lda f:CARTEL_I
    inc a
    sta f:CARTEL_I
    cmp #IMAGEN_OBJETOS
    beq salir
    jmp cada
salir:
    rts
.endproc

