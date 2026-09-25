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

