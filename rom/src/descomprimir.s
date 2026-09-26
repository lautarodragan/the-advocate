.segment "FAR"

; --- LZ2: lo que el cartucho trae comprimido --------------------------------
;
; Los tiles del mapa, de los sprites, de la capa de encima, de la animación del
; ChipSet y la grilla viajan en el cartucho en LC_LZ2, el formato de Nintendo,
; y se descomprimen a la WRAM al cargar el mapa, con la pantalla apagada
; adentro del fundido. El formato y el porqué de éste y no otro están en
; tools/port/comprimir.py; el compresor es `tools/lz2/`.
;
; Cada comando del flujo es un encabezado —qué es y cuántos bytes hace— y su
; operando. Casi todo se resuelve con `mvn`:
;
;   literal      `mvn` del flujo a la salida
;   relleno      el byte a la salida, y un `mvn` de la salida sobre sí misma
;                corrido en uno, que lo repite: `mvn` copia de a un byte hacia
;                adelante, así que cada byte que lee es el que acaba de escribir
;   palabra      lo mismo con los dos bytes, corrido en dos
;   repetición   `mvn` de la salida a la salida: la dirección que trae es
;                absoluta —cuenta desde el principio de la salida— y se le suma
;                la base
;
; El creciente (3), que es el único que un `mvn` no hace, y la palabra de un
; solo byte **no se leen**: el conversor no los emite y lo cobra —ver
; `lo_que_la_rom_no_lee` en tools/port/comprimir.py—. Leerlos sería un camino
; que ninguna prueba ejecuta.
;
; `mvn` lleva los dos bancos **adentro de la instrucción**. El de la salida es
; uno de dos —$7E o $7F—, así que el cuerpo está escrito dos veces, una por
; banco, con el `mvn` de la salida sobre sí misma adentro: es por donde pasan
; casi todos los bytes —los tiles y más todavía la grilla son sobre todo
; repeticiones y rellenos— y así se leen del espejo rápido de la ROM. El del
; flujo cambia de bloque a bloque, así que el `mvn` del literal se arma en la
; RAM al empezar —`LZ2_TRAMPA_LIT`— y se llama con `jsl`; correr desde la WRAM
; le cuesta unos ciclos por byte, porque `mvn` vuelve a leer su código en cada
; uno.
;
; El flujo se lee con el banco de datos puesto en el suyo y `lda a:0, x`, por el
; espejo rápido: la página directa está llena y no hay dónde poner un puntero
; de 24 bits. Por eso cada bloque comprimido entra entero en un banco —lo
; declara el conversor con `.bloque`—: X no puede pasar de $FFFF.

; Descomprime un flujo. Entra con A en ocho bits y X e Y en dieciséis: X y A
; dónde está el flujo —dirección y banco—, Y dónde va la salida adentro del
; banco `LZ2_BANCO`, que pone quien llama y es $7E o $7F. Sale con X en el
; byte que sigue al $FF —ahí empieza el flujo siguiente, si hay otro pegado— e
; Y en el que sigue al último que escribió. Pisa A; deja P y el banco de datos
; como estaban.
;
; La salida no puede cruzar de banco: Y da la vuelta en $FFFF y el conversor lo
; cuida, con flujos de hasta 32 KB.
.proc lz2_descomprimir
.a8
.i16
    php
    phb
    ora #^RAPIDO                ; el flujo, por el espejo rápido
    pha
    ; La trampa del literal. En el código de máquina de `mvn` el banco de
    ; destino va primero y el de origen después.
    sta f:LZ2_TRAMPA_LIT + 2
    lda #$54                    ; mvn
    sta f:LZ2_TRAMPA_LIT
    lda #$6B                    ; rtl
    sta f:LZ2_TRAMPA_LIT + 3
    lda f:LZ2_BANCO
    sta f:LZ2_TRAMPA_LIT + 1
    plb                         ; el banco del flujo
    rep #$20
.a16
    tya
    pha                         ; 3,s: la base de la salida
    pha                         ; 1,s: el largo del comando, menos uno
    sep #$20
.a8
    lda f:LZ2_BANCO
    cmp #^GRILLA_ALTA
    bne en_el_7e
    jmp lz2_cuerpo_7f
en_el_7e:
    jmp lz2_cuerpo_7e
.endproc

; El cuerpo, para la salida en el banco `salida`. Se entra de
; `lz2_descomprimir` con el banco del flujo puesto y el largo y la base en la
; pila, y se vuelve de ahí mismo.
.macro LZ2_CUERPO salida
comando:
    sep #$20
.a8
    lda a:0, x
    cmp #$E0
    bcs largo
    ; `CCCLLLLL`: hasta 32 bytes.
    rep #$20
.a16
    and #$001F
    sta 1, s
    sep #$20
.a8
    lda a:0, x                  ; y otra vez, para despachar
    inx
    bra despachar
largo:
    cmp #$FF
    beq fin
    ; `111CCCLL LLLLLLLL`: hasta 1024. Se corre el comando a los tres bits de
    ; arriba, que es donde lo tiene el encabezado corto.
    rep #$20
.a16
    lda a:0, x
    xba
    and #$03FF
    sta 1, s
    sep #$20
.a8
    lda a:0, x
    inx
    inx
    asl a
    asl a
    asl a
despachar:
    asl a
    bcs repeticion              ; 4: el 5 y el 6 no existen
    asl a
    bcs palabra                 ; 2; el 3, el creciente, no llega nunca
    asl a
    bcs relleno
    ; 0: los bytes, del flujo a la salida.
    rep #$20
.a16
    lda 1, s
    phb
    jsl f:LZ2_TRAMPA_LIT
    plb
    bra comando

fin:
.a8
    inx                         ; el $FF
    rep #$20
.a16
    pla
    pla
    plb
    plp
    rtl

relleno:
.a8
    ; 1: el byte a la salida, y se repite corrido en uno.
    lda a:0, x
    inx
    phx                         ; el flujo, mientras X apunta a la salida
    tyx
    sta f:salida << 16, x
    iny
    rep #$20
.a16
    lda 3, s                    ; el largo menos uno, corrido por el `phx`
    beq listo                   ; era uno solo
    dec a                       ; los que faltan, menos uno
    bra en_la_salida

palabra:
.a8
    ; 2: los dos bytes a la salida, y se repiten corridos en dos. Siempre son
    ; dos o más: ver arriba.
    rep #$20
.a16
    lda a:0, x
    inx
    inx
    phx
    tyx
    sta f:salida << 16, x
    iny
    iny
    lda 3, s                    ; el largo menos uno, corrido por el `phx`
    dec a
    beq listo                   ; eran dos
    dec a
    bra en_la_salida

repeticion:
.a8
    ; 4: de la salida a la salida. La dirección viene con el byte alto primero.
    rep #$20
.a16
    lda a:0, x
    xba
    inx
    inx
    phx
    clc
    adc 5, s                    ; más la base, que el `phx` corrió a 5,s
    tax
    lda 3, s                    ; y el largo menos uno, a 3,s
en_la_salida:
    ; Con X adentro de la salida, A el largo menos uno y el puntero del flujo
    ; en la pila. El `mvn` deja el banco de datos en el de la salida.
    phb
    mvn #salida, #salida
    plb
listo:
    plx
    jmp comando

.endmacro

.proc lz2_cuerpo_7e
    LZ2_CUERPO ^GRILLA
.endproc

.proc lz2_cuerpo_7f
    LZ2_CUERPO ^GRILLA_ALTA
.endproc

; X y A del flujo que apunta el campo Y del registro del mapa: su dirección y
; su banco, listos para `lz2_descomprimir`.
.proc lz2_del_campo
.a8
.i16
    rep #$20
.a16
    tya
    clc
    adc mapa_ofs
    tax
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    pha
    rep #$20
.a16
    lda f:mapa_tabla, x
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; El bloque que apunta el campo Y del registro del mapa, descomprimido en
; `LZ2_BUFFER`, y el canal 0 del DMA apuntando ahí: reemplaza a `dma_origen`
; en `load_map`, `load_above` y `load_sprite`, que siguen poniendo el largo y
; el destino como antes. El largo sale del registro y no de lo que escribió el
; descompresor, así que lo que llega a la VRAM es lo mismo que cuando el
; cartucho traía los tiles enteros.
.proc lz2_campo
.a8
.i16
    jsr lz2_del_campo
    pha
    lda #^LZ2_BUFFER
    sta f:LZ2_BANCO
    pla
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_descomprimir + RAPIDO
    rep #$20
.a16
    lda #.loword(LZ2_BUFFER)
    sta f:A1T0L
    sep #$20
.a8
    lda #^LZ2_BUFFER
    sta f:A1B0
    rtl
.endproc

; Los dibujos de la animación del ChipSet del mapa, en `ANIM_DIBUJOS`, de
; donde los sube `anim_subir` cada vez que cambia el reloj. Tienen que quedar
; ahí mientras se esté en el mapa, así que van en un lugar propio y no en
; `LZ2_BUFFER`, que la capa de encima y los sprites pisan después: ver la
; reserva en `ram_lejana.s`.
.proc lz2_anim
.a8
.i16
    ldy #M_PTR_ANIM_TILES
    jsr lz2_del_campo
    pha
    lda #^ANIM_DIBUJOS
    sta f:LZ2_BANCO
    pla
    ldy #.loword(ANIM_DIBUJOS)
    jsl f:lz2_descomprimir + RAPIDO
    rtl
.endproc

; La grilla del mapa, descomprimida en `GRILLA`: sus primeros 32 KB en la
; mitad alta del banco $7E y el resto en la del $7F, que es la forma que
; esperan `ptr_mas` y `ptr_menos`. El conversor la parte en dos flujos, uno por
; mitad, así que ninguna salida cruza de banco; el segundo va pegado al
; primero, y puede no tener nada más que su $FF.
;
; La pelea pisa la mitad del $7F —es `ESC_ESCENA`—, así que `volver_de_batalla`
; la vuelve a descomprimir. Ver la decisión en
; workflow/decisiones/la-grilla-vive-en-la-wram.md.
.proc lz2_grilla
.a8
.i16
    ldy #M_PTR_MAP_CELDAS
    jsr lz2_del_campo
    pha                         ; el banco del flujo, para el segundo
    lda #^GRILLA
    sta f:LZ2_BANCO
    pla
    pha
    ldy #.loword(GRILLA)
    jsl f:lz2_descomprimir + RAPIDO     ; deja X en el segundo flujo
    lda #^GRILLA_ALTA
    sta f:LZ2_BANCO
    pla
    ldy #.loword(GRILLA_ALTA)
    jsl f:lz2_descomprimir + RAPIDO
    rtl
.endproc

; Los topes de cada bloque salen de la reserva de ram_lejana.s y el conversor
; los cobra al comprimir: si alguno de los dos lados se mueve solo, que no
; arme.
.assert LZ2_BUFFER + LZ2_TOPE_FONDO <= ANIM_DIBUJOS_FIN, error, "los tiles del fondo no entran en el buffer de carga"
.assert LZ2_BUFFER + LZ2_TOPE_ENCIMA_Y_SPRITES <= ANIM_DIBUJOS, error, "la capa de encima o los sprites pisarían los dibujos de la animación"
.assert ANIM_DIBUJOS + LZ2_TOPE_ANIM <= ANIM_DIBUJOS_FIN, error, "los dibujos de la animación no entran en su lugar"
.assert GRILLA_ALTA = GRILLA + $10000, error, "las dos mitades de la grilla tienen que ser la misma dirección en dos bancos seguidos: así las recorre `ptr_mas`"
.assert LZ2_TOPE_GRILLA <= 2 * (GRILLA_FIN - GRILLA), error, "la grilla más grande no entra en las dos mitades altas de la WRAM"
