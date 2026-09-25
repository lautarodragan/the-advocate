; --- la animación del ChipSet ----------------------------------------------
;
; Dos animaciones que corren a la vez y a cadencias distintas: los autotiles de
; agua, que cambian cada AGUA_CUADROS y recorren el ciclo 0,1,2,1, y los "tiles
; animados", que cambian cada ANIMADO_CUADROS y dan la vuelta entre cuatro.
;
; Animar es **pisar el dato de unos pocos tiles de la VRAM**; el tilemap no se
; toca. El conversor deja los que cambian en una corrida contigua al final del
; banco del mapa, sin compartir ninguno con las celdas quietas, así que un paso
; es un DMA solo: entre 128 y 1664 bytes según el mapa. Ver `convert` en
; tools/port/snes_convert.py.
;
; **No guarda en qué punto va y no lee nada del cartucho para decidir**, y las
; dos cosas eran obligatorias y no elegancia: la BSS estaba en 7680 de 7680 y la
; página directa en 255 de 256, así que no había dónde poner ni un contador ni
; un puntero para `lda [puntero], y`. En qué punto del ciclo va cada familia
; sale de dividir `vueltas` —menos `vueltas_congeladas`, los ticks del fundido—
; por su cadencia con el divisor del hardware; dónde están sus tiles y sus
; dibujos lo trae `anim_tabla`, que arma el conversor.
;
; El resto de esa división dice además **si este tick es el del cambio**, que es
; lo único que hay que preguntar para saber si hace falta el DMA.
;
; El ciclo del agua: cuatro pasos, y el cuarto vuelve a dibujar el segundo. Es
; `animation_step_ab` de easyrpg, tilemap_layer.cpp:289, con `animation_type` en
; 0, que es el default y lo que tienen todos los ChipSets de este juego.
; Tres dibujos en cuatro pasos, con el cuarto repitiendo el segundo. Lo usan
; las dos animaciones que hay: el agua del ChipSet —`animation_step_ab` de
; easyrpg— y el ciclo de caminata de un personaje, que tiene tres columnas y
; dibuja la 1 cuando el paso es el 3. Es `CICLO_TRES` en tools/rpgmaker/rm2k.py.
ciclo_tres:
    .byte 0, 1, 2, 1

; Cuánto avanza el héroe por cuadro según su velocidad, en **medias unidades**
; de RM2k: RM2k cuenta 256 por celda y avanza `1 << (1 + velocidad)`, o sea 4,
; 8, 16, 32, 64 y 128 —`PASO_POR_VELOCIDAD` en eventos.py—, y acá `step_left`
; es un byte, así que se cuenta de a dos: 128 por celda y la mitad de cada
; paso. Los pixeles que faltan son `step_left >> 3`: la división entera tira
; los dieciseisavos, y a las velocidades con medio pixel por cuadro eso es lo
; mismo que contar los cuadros por dos.
paso_medio_por_vel:
    .byte 2, 4, 8, 16, 32, 64
; Y cada cuántos cuadros cambia el frame de la caminata: `ANIM_PARADO`.
anim_por_vel:
    .byte 12, 10, 8, 6, 5, 4

; Deja en X la entrada de la familia Y adentro de `anim_tabla`. Cuál es el mapa
; sale de `mapa_ofs` sin guardar nada: los dos pasos son potencias de dos.
.proc anim_donde
.a8
.i16
    rep #$20
.a16
    lda mapa_ofs
    lsr a
    lsr a
    lsr a
.assert MAPA_STRIDE = 128, error, "las tres divisiones de arriba son MAPA_STRIDE/ANIM_STRIDE"
.assert ANIM_STRIDE = 16, error, "ídem"
    sta temp
    tya
    asl a
    asl a
    asl a
.assert ANIM_FAM_STRIDE = 8, error, "las tres multiplicaciones son ANIM_FAM_STRIDE"
    clc
    adc temp
    tax
    sep #$20
.a8
    rts
.endproc

; Qué dibujo le toca a la familia Y en el tick que venga en X. Devuelve el
; dibujo en A y en `temp + 3` un 1 si **este** tick es aquel en que cambia, o
; sea si el reloj cayó justo en el borde.
;
; El tick es `vueltas`, el mismo número que cuenta la referencia. Como es de
; dieciséis bits, cada 65536 ticks —dieciocho minutos— da la vuelta y el ciclo
; se saltea un dibujo; RM2k cuenta en treinta y dos. La referencia da la misma
; vuelta —ver `TICK_MASCARA` en tools/rpgmaker/rm2k.py— así que los dos lados
; siguen diciendo lo mismo, y lo que se pierde está declarado en
; workflow/divergencias/el-chipset-se-saltea-un-dibujo-cada-18-minutos.md.
.proc anim_paso
.a8
.i16
    rep #$20
.a16
    txa
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #AGUA_CUADROS
    cpy #$0000
    beq divisor
    lda #ANIMADO_CUADROS
divisor:
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    stz temp + 3
    lda RDMPYL                  ; el resto: cero es el tick del cambio
    ora RDMPYL + 1
    bne no_cambia
    inc temp + 3
no_cambia:
    lda RDDIVL
    and #(AGUA_CICLO_N - 1)
.assert AGUA_CICLO_N = 4, error, "el ciclo se recorta con un and de dos bits"
.assert ANIMADO_PASOS = 4, error, "y los dos ciclos miden lo mismo"
    cpy #$0000
    bne listo                   ; los tiles animados dan la vuelta y ya está
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ciclo_tres, x
    plx
listo:
    rts
.endproc

; El DMA de una familia: X su entrada en `anim_tabla` e Y el dibujo. El modo del
; DMA lo deja puesto quien llama, que siempre pide lo mismo.
.proc anim_subir
.a8
.i16
    pha                         ; el dibujo, que las cuentas de abajo pisan
    lda f:anim_tabla + 6, x
    bne hay
    pla
    rts                         ; esta familia no anima en este mapa
hay:
    rep #$20
.a16
    lda f:anim_tabla + 0, x
    sta VMADDL
    lda f:anim_tabla + 4, x
    sta DAS0L
    sta temp                    ; cuánto mide un dibujo
    lda f:anim_tabla + 2, x
    sta temp + 2                ; y dónde está el 0, adentro del bloque
    sep #$20
.a8
    ; El dibujo se ensancha acá y no en quien llama: `ldy` con X e Y anchos se
    ; lleva el byte de al lado, y eso ya costó una tarde dos veces —ver
    ; `anim_tick`—. Con `and #$00FF` sobre el acumulador ancho, el byte alto
    ; queda en cero venga de donde venga.
    pla
    rep #$20
.a16
    and #$00FF
    tay
saltar:
    cpy #$0000
    beq puesto
    lda temp + 2
    clc
    adc temp
    sta temp + 2
    dey
    bra saltar
puesto:
    ; El bloque vive en el cartucho y su puntero está en el registro del mapa.
    ; El acomodo de `tools/ensamblado/bancos.py` garantiza que entra entero en un banco,
    ; así que la suma de
    ; dieciséis bits no se sale.
    phx
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_ANIM_TILES, x
    clc
    adc temp + 2
    sta A1T0L
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_ANIM_TILES + 2, x
    sta A1B0
    plx
    lda #$01
    sta MDMAEN
    rts
.endproc

; El modo del DMA que piden los dos de abajo: tiles de fondo a la VRAM.
.proc anim_modo
.a8
.i16
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    rts
.endproc

; Las dos familias, ya mismo y sin presupuesto: es lo que hace `load_map`, con
; la pantalla apagada. El mapa nuevo trae en la VRAM el dibujo 0 de cada
; corrida y el reloj puede estar en cualquier otro, porque es de la partida y no
; del mapa.
.proc anim_cargar
.a8
.i16
    stz anim_pend               ; lo que hubiera pendiente se sube acá
    jsr anim_modo
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; el reloj de las animaciones: ver ahí
    tax
    sep #$20
.a8
    jsr anim_paso               ; Y sigue siendo la familia
    ply
    phy
    pha
    jsr anim_donde
    pla
    jsr anim_subir
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; Qué hay que subir en el vblank que viene, decidido en el cuerpo del lazo.
;
; Va **después** del `inc vueltas`, así que el tick que mira es el de la vuelta
; que sigue, que es la que va a mostrar el dibujo. Que sea ése y no el anterior
; está medido y no razonado: ver `anim_flush`.
.proc anim_tick
.a8
.i16
    stz anim_pend
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; el reloj de las animaciones: ver ahí
    tax
    sep #$20
.a8
    jsr anim_paso
    inc a                       ; el dibujo, más uno: el cero es "nada"
    sta temp + 2
    ; Y si este tick es el del cambio. Se mira con el acumulador en ocho bits y
    ; no con `ldx`: con X ancho la lectura se lleva también `temp + 4`, que es
    ; el byte bajo de `hero_x`, y entonces todos los ticks parecen el del
    ; cambio. Subir el dibujo que ya está subido no se ve, así que el error
    ; sobrevive a la comparación de pixeles; lo que se ve es el presupuesto de
    ; poses bajando todos los cuadros.
    lda temp + 3
    beq siguiente
    ply
    phy
    jsr anim_donde
    lda f:anim_tabla + 6, x
    beq siguiente               ; esta familia no anima en este mapa
    lda temp + 2
    cpy #$0000
    beq baja
    asl a
    asl a
    asl a                       ; tres bits por familia
.assert ANIM_FAMILIAS = 2, error, "los dos nibbles de anim_pend entran en un byte"
baja:
    ora anim_pend
    sta anim_pend
siguiente:
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; El paso que toque, en el vblank, y sólo en el tick en que cambia.
;
; El tick que se mira es `vueltas` tal cual, sin corregir nada por el cuadro que
; el video va atrasado. Está medido y no razonado: con `vueltas - 1` la tanda da
; rojo en **un tick de cada 24** —el del cambio— y en ninguno más, que es 32%
; de la pantalla en el mapa 5. El caso que lo cobra es `snes-caminando 5 left`
; con el avance 46, o sea el tick 24 justo.
;
; Lo que sube se le descuenta al presupuesto de poses en vez de fijarlo, para
; que se sume a lo que ya se hayan llevado el tinte o un renglón de la ventana.
.proc anim_flush
.a8
.i16
    lda anim_pend
    bne hay
    rts                         ; el caso de siempre: un lda y un beq
hay:
    jsr anim_modo
    ldy #$0000
otra:
    ; Los tres bits de esta familia, leídos de `anim_pend` cada vuelta y no de
    ; una copia en `temp`: `anim_subir` guarda ahí una palabra y se llevaba
    ; puesta la copia. Cuando las dos familias cambiaban en el mismo tick —cada
    ; 24, que es múltiplo de 6— la segunda se perdía y se quedaba con el dibujo
    ; viejo hasta el cambio siguiente. Se veía en 8 pixeles del mapa 2.
    lda anim_pend
    cpy #$0000
    beq baja
    lsr a
    lsr a
    lsr a
baja:
    and #$07
    beq siguiente
    dec a                       ; el dibujo que pidió `anim_tick`
    phy
    pha
    jsr anim_donde
    pla
    jsr anim_subir
    ; Lo que se llevó, en poses: una pose son 512 bytes y un tile de fondo 64.
    ; Se le descuenta al presupuesto en vez de fijarlo, para que se sume a lo
    ; que ya se hayan llevado el tinte o un renglón de la ventana.
    lda f:anim_tabla + 6, x
    lsr a
    lsr a
    lsr a
.assert BYTES_POR_TILE = 64, error, "ocho tiles de fondo entran en una pose de 512"
    inc a
    sta temp + 2
    lda vq_tope
    sec
    sbc temp + 2
    bcc una
    bne queda
una:
    lda #1                      ; siempre queda para una pose
queda:
    sta vq_tope
    ply
siguiente:
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    stz anim_pend
    rts
.endproc

