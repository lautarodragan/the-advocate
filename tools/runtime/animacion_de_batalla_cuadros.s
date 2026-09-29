.segment "FAR"

; --- el cuadro de la animación de batalla, rearmado -------------------------
;
; El cartucho guarda cada cuadro **sin sus tiles vacíos**: una lista de tiles,
; cada uno con su número en la caja delante —un byte de 0 a 63 y sus 32 bytes—
; y $FF al final. Ver `cuadro_sin_vacios` en snes_convert.py. Acá se rearman
; los 2 KB en `ANIMB_BUF`, que es de donde el vblank los sube enteros: lo que
; queda en la VRAM es lo mismo que cuando el cartucho los traía completos.
;
; El buffer se mantiene en cero salvo los tiles del último cuadro armado, que
; `ANIMB_PREV` apunta. Así que armar uno nuevo es borrar esos y copiar los del
; nuevo, y cuesta lo que pesan los dos y no los 2 KB: los cuadros son casi
; todos transparencia. Corre en el lazo principal, con la pantalla prendida,
; y por eso copia la CPU y no un DMA a $2180: un DMA general fuera del vblank
; se cruza con el HDMA de la ventana de mensaje, y en la primera revisión de
; la CPU de la consola ese cruce la puede colgar.
;
; Vive en el banco 1 porque en el banco 0 no hay lugar, y se entra por su
; espejo rápido, igual que el código del banco 0 —ver MEMSEL—. Cada tile se
; copia desenrollado, dieciséis palabras seguidas, porque un lazo de a palabra
; gasta en contar y en saltar casi lo mismo que en copiar; el `jmp` del final
; de cada lazo es por eso: el cuerpo desenrollado no le deja alcance a un
; `bra`.

; Todo el buffer en cero y ningún cuadro armado. Lo llama `cargar_mapa`, con la
; pantalla apagada; es lo que hace falta al menos una vez desde el encendido,
; porque la WRAM arranca con basura en la consola —y en bsnes—.
.proc anim_buf_limpiar
.a8
.i16
    php
    rep #$20
.a16
    lda #0
    ldx #ANIM_B_BYTES - 2
borra:
    sta f:ANIMB_BUF, x
    dex
    dex
    bpl borra
    sep #$20
.a8
    sta f:ANIMB_PREV + 2        ; A es cero: ningún cuadro armado
    plp
    rtl
.endproc

; Arma en `ANIMB_BUF` el cuadro `ANIMB_CUADRO` de la animación de la fila
; `ANIMB_FILA`. Pisa A, X, Y y `temp`.
.proc anim_cuadro_armar
.a8
.i16
    phb
    lda f:ANIMB_PREV + 2
    beq sin_anterior
    ora #^RAPIDO                ; su espejo rápido: ver MEMSEL
    pha
    plb                         ; el banco del cuadro anterior
    rep #$20
.a16
    lda f:ANIMB_PREV
    tay
    sep #$20
.a8
    ; Sus tiles, a cero.
borrar:
    lda a:0, y
    bmi sin_anterior            ; $FF: se terminó. Los tiles van de 0 a 63
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por tile
    tax
    tya
    clc
    adc #33                     ; el número y sus 32 bytes
    tay
    lda #0
.repeat 16, i
    sta f:ANIMB_BUF + i * 2, x
.endrepeat
    sep #$20
.a8
    jmp borrar

sin_anterior:
    ; El puntero del nuevo: el primero de la animación más el que toca, cuatro
    ; bytes por puntero. Es la cuenta que hacía el vblank cuando subía el
    ; cuadro directo del cartucho.
    rep #$20
.a16
    lda f:ANIMB_FILA
    tax
    lda f:anim_batalla_tabla + 4, x
    clc
    adc f:ANIMB_CUADRO
    asl a
    asl a
    tax
    lda f:anim_batalla_cuadros, x
    sta f:ANIMB_PREV
    tay
    sep #$20
.a8
    lda f:anim_batalla_cuadros + 2, x
    sta f:ANIMB_PREV + 2
    ora #^RAPIDO
    pha
    plb                         ; el banco del cuadro nuevo
copiar:
    lda a:0, y
    bpl un_tile
    plb                         ; $FF: listo
    rtl
un_tile:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    tax
.repeat 16, i
    lda a:1 + i * 2, y
    sta f:ANIMB_BUF + i * 2, x
.endrepeat
    tya
    clc
    adc #33
    tay
    sep #$20
.a8
    jmp copiar
.endproc
