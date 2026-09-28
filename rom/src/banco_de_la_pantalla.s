.segment "FAR"

; --- el banco de la pantalla, también fuera del banco 0 ---------------------
;
; Se mudó acá el 2026-09-13, cuando `volver_de_batalla` pidió cuarenta y seis
; bytes que el banco 0 ya no tenía: `abl` quedaba en 32748 de 32704, y
; antes de eso le sobraban **dos**. Ésta es la que sale más barata de mudar de
; todo lo que mide más de cien bytes: no llama a nadie —son escrituras de
; registro y cuatro DMA— así que no hace falta ningún puente, y no corre por
; cuadro sino al abrir una pantalla con el PPU apagado, o sea que el ciclo de
; más del `jsl` no se nota.
;
; Lo que sí obliga: **se entra con `jsl` y vuelve con `rtl`**, y el banco de
; datos tiene que seguir siendo uno donde $2100..$21FF sea la consola, porque
; escribe los registros en absoluto. Los seis llamadores están todos en el
; banco 0; el de la pelea entra por el puente `ba_t_banco`, que es justo el que
; pone el banco de datos en cero antes de llamar.

; El banco de la pantalla, con la pantalla apagada: la fuente, el tilemap en
; blanco y las dos paletas.
.proc items_banco_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(ITEMS_TILES * 32)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; El tilemap en blanco: un DMA de origen fijo desde el primer tile, que
    ; es transparente.
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$09                    ; dos registros, sin avanzar el origen
    sta DMAP0
    lda #$01
    sta MDMAEN
    ; Los colores.
    stz CGADD
    rep #$20
.a16
    lda #(ITEMS_CGRAM_N * 2)
    sta DAS0L
    lda #<(items_cgram)
    ora #(>(items_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc


; --- las ventanas de la pantalla de ítems -------------------------------------
;
; La pantalla de ítems es la única de las que usan este banco que lleva
; ventanas: el marco y el fondo del System, en BG1, detrás del texto de BG2 —ver
; `ITEM_VENTANAS` en titulo.py—. BG1 lee sus tiles desde la misma base que BG2,
; y los de las ventanas van detrás de la fuente.

; El banco de la pantalla y las ventanas, con la pantalla apagada: se entra con
; `jsl`, como a `items_banco_subir`.
.proc items_pantalla_subir
.a8
.i16
    jsl f:items_banco_subir
    ; Los tiles, que son de 8bpp.
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #ITEM_MARCO_VRAM
    sta VMADDL
    lda #(ITEM_MARCO_TILES * 64)
    sta DAS0L
    lda #.loword(items_marco_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; El tilemap: las filas que se ven, sin cursor.
    rep #$20
.a16
    lda #ITEM_MARCO_MAPA
    sta VMADDL
    lda #(ITEM_MARCO_FILAS * 64)
    sta DAS0L
    lda #.loword(items_marco_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_mapa)
    sta A1B0
    lda #$01
    sta MDMAEN
    ; Los colores, después de las tres paletas del texto.
    lda #ITEM_MARCO_CGRAM
    sta CGADD
    rep #$20
.a16
    lda #(ITEM_MARCO_COLORES * 2)
    sta DAS0L
    lda #.loword(items_marco_cgram)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_marco_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; BG2 con el texto y BG1 con las ventanas, y la pantalla prendida. Es
; `ranura_ppu_prender` más BG1.
.proc items_ppu_prender
.a8
.i16
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(ITEM_MARCO_MAPA / 1024 * 4)
    sta BG1SC
    lda #(RANURA_VRAM / 4096 * 16 + RANURA_VRAM / 4096)
    sta BG12NBA                 ; las dos capas desde la misma base
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

; El cursor en la fila A de la lista, que es la barra del System: `temp + 3` en
; 1 lo pinta y en 0 lo borra. Las dos cosas son copiar las dos filas de celdas
; de BG1 que ocupa la fila: de `items_marco_barras`, que las tiene con el
; cursor encima, o del tilemap sin cursor. Un DMA de 128 bytes, que entra en el
; vblank junto con la descripción. Se lleva X e Y.
.proc items_barra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; 128 bytes por fila de la lista
    tay
    lsr a                       ; que son 64 palabras
    clc
    adc #(ITEM_MARCO_MAPA + ITEM_MARCO_LISTA * 32)
    tax
    sep #$20
.a8
    lda #$80
    sta VMAIN
    stx VMADDL
    lda temp + 3
    beq borra
    lda #^(items_marco_barras)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_marco_barras)
    bra fuente
.a8
borra:
    lda #^(items_marco_mapa)
    sta A1B0
    rep #$20
.a16
    tya
    clc
    adc #.loword(items_marco_mapa + ITEM_MARCO_LISTA * 64)
fuente:
    sta A1T0L
    lda #128
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
.endproc
