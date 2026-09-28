.segment "CODE"

; --- la ventana de mensaje -------------------------------------------------
; Sus tiles y su paleta se suben una sola vez, con la pantalla apagada, igual
; que los de la capa de encima. Viven detrás de los de encima, y BG2 los
; alcanza con la misma base: según el reparto, la capa de encima tiene 128 o
; 256 tiles y la ventana arranca en ese índice. Por eso el conversor emite dos
; planos de celdas, uno con cada corrimiento sumado, y `estampar_ventana`
; elige.
;
; Su paleta es la **0**, o sea las entradas que están debajo del fondo, y la
; sube `cargar_mapa_sin_eventos` junto con el color de fondo de la pantalla.
.proc load_ventana
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(ventana_tiles)
    sta A1T0L
    lda #(VENTANA_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; La paleta de la ventana no se sube acá: es la **0**, o sea las entradas
    ; que `cargar_mapa_sin_eventos` ya subió junto con el color de fondo. Antes
    ; iba flotando debajo de la capa de encima más baja de la ROM y se subía
    ; por su cuenta; con eso el fondo de todos los mapas quedaba apretado
    ; abajo de ella —47 colores— aunque tuvieran media CGRAM libre arriba.

    ; El tilemap propio y las tablas del HDMA, que son de este mapa: la ventana
    ; vive en un lugar de la VRAM que depende del reparto.
    jsr estampar_ventana
    jsr armar_hdma
    rts
.endproc

; Escribe el tilemap propio de la ventana: 320 celdas seguidas, un solo DMA.
;
; Acá está toda la diferencia con lo que había antes. La ventana ya no se
; estampa en el tilemap del mapa —que se scrollea— sino en uno suyo, de 32x32,
; que no comparte con nadie. Como es propio, sus diez filas de 32 celdas son
; 320 palabras contiguas: no hay tramos, ni envoltura, ni columna 32 que
; esquivar. Y como nadie más lo toca, esto corre **una sola vez por mapa**,
; desde `load_ventana` y con la pantalla ya apagada.
;
; Quién lo muestra y dónde lo decide el HDMA; ver `armar_hdma`.
.proc estampar_ventana
.a8
.i16
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    ; Qué plano: el que tiene horneado el índice donde arranca la ventana, que
    ; es la distancia entre ella y la base de BG2 —el nibble alto de
    ; BG12NBA—. Los repartos la ponen 128 tiles detrás o, el de la capa de
    ; encima de 256, 256: 256 tiles de 4bpp son $1000 palabras, $10 en el
    ; byte alto. Ver `VENTANA_BASES` en el conversor.
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    and #$F0
    sta temp
    lda f:mapa_tabla + M_VRAM_VENTANA + 1, x
    sec
    sbc temp
    cmp #$10                    ; el acarreo sobrevive al `rep` y al `lda`
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP, x
    sta VMADDL
    lda #(VENTANA_FILAS * VENTANA_COLS * 2)
    sta DAS0L
    bcs plano_256
    lda #.loword(ventana_celdas)
    sta A1T0L
    sep #$20
.a8
    lda #^ventana_celdas
    bra con_plano
plano_256:
.a16
    lda #.loword(ventana_celdas_256)
    sta A1T0L
    sep #$20
.a8
    lda #^ventana_celdas_256
con_plano:
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Deja armadas las dos tablas del HDMA y programa sus canales. Corre una vez por
; mapa, junto con el resto de la carga.
;
; Lo que el HDMA consigue, y que ninguna cantidad de estampado conseguía: BG2
; cambia de tilemap y de scroll **a mitad de cuadro**. De la línea 0 a la 143
; sigue siendo la capa de encima del mapa, con la cámara; de la 144 a la 223 es
; el tilemap propio de la ventana, con el scroll clavado. Por eso la ventana no
; se mueve aunque la cámara sí, y por eso no hay una sola escritura de VRAM
; mientras un mensaje está en pantalla.
;
; Las dos primeras entradas llevan justo lo que `flush_video` ya escribía en los
; registros, así que arriba de la línea 144 no cambia nada. Van en dos tramos
; porque el contador de líneas de una entrada es de 7 bits y 144 no entra.
.proc armar_hdma
.a8
.i16
    lda #127
    sta hdma_sc
    sta hdma_ofs
    lda #(VENTANA_LINEA - 127)
    sta hdma_sc + 2
    sta hdma_ofs + 5
    lda #(LINEAS - VENTANA_LINEA)
    sta hdma_sc + 4
    sta hdma_ofs + 10

    ; El tilemap del mapa arriba y el de la ventana abajo. BG2SC lleva la
    ; dirección en el byte alto; el tamaño de la ventana es 0, que es 32x32.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1
    sta hdma_sc + 3
    ldx mapa_ofs
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP + 1, x
    sta hdma_sc + 5
    stz hdma_sc + 6             ; fin de tabla

    ; Y el scroll clavado de las líneas de la ventana. Los dos tramos de arriba
    ; los llena `flush_video` con la cámara de cada cuadro.
    stz hdma_ofs + 11
    stz hdma_ofs + 12
    lda #<VENTANA_VOFS
    sta hdma_ofs + 13
    lda #>VENTANA_VOFS
    sta hdma_ofs + 14
    stz hdma_ofs + 15           ; fin de tabla

    lda #$00                    ; un registro, una escritura por tramo
    sta DMAP1
    lda #<BG2SC
    sta BBAD1
    ldx #hdma_sc
    stx A1T1L
    stz A1B1                    ; las tablas viven en el banco 0

    lda #$03                    ; dos registros, dos escrituras cada uno, que
    sta DMAP2                   ; es lo que piden BG2HOFS y BG2VOFS
    lda #<BG2HOFS
    sta BBAD2
    ldx #hdma_ofs
    stx A1T2L
    stz A1B2

    ; Y el tercer canal esconde los objetos debajo de la ventana. En RM2k la
    ; ventana de mensaje tapa todo —`Priority_Window` es 130 y los personajes
    ; van por debajo—, pero acá es BG2 con prioridad 1, y un evento marcado
    ; "above" va en objetos con prioridad 2, que en el modo 3 queda *adelante*
    ; de BG2: se veía a través de la ventana. Lo cobró la tanda con la puerta
    ; del mapa 7 apenas los eventos dibujados con un tile pasaron a sprites.
    ; La máscara es la ventana 1 del PPU, de punta a punta, prendida para los
    ; objetos sólo en las líneas de la ventana de mensaje: `hdma_mascara`,
    ; que no cambia nunca y vive en la ROM.
    lda #$00
    sta DMAP3
    lda #<WOBJSEL
    sta BBAD3
    ldx #.loword(hdma_mascara)
    stx A1T3L
    lda #^hdma_mascara          ; ya no es el banco 0: vive en RODATA
    sta A1B3
    rts
.endproc

; --- el compositor de texto ------------------------------------------------
;
; Lo que hace que esto entre en un 65816. RM2k dibuja cada glifo usando sus
; pixeles como **máscara** sobre un bloque de 16x16 del System, y leído así
; pide muestrear el bloque pixel por pixel. Medido, no hace falta: cada fila
; del glifo toma un solo color —el degradé es vertical— y la sombra es un color
; plano. O sea que todo el color se reduce a doce bytes, `fuente_color`, más
; `FUENTE_SOMBRA`. Es la medición que volvió barato esto.
;
; El área de texto son 30 celdas de ancho por 8 de alto y sus 240 tiles **no
; están deduplicados**: cada celda tiene el suyo, fijo, así que componer es
; escribir un buffer y subirlo. Se hace de a un renglón —dos filas de celda, 60
; tiles, 1920 bytes— y se sube en el vblank siguiente.
;
; Un renglón se ceba con el fondo de la ventana antes de escribirle el texto,
; porque los glifos no se dibujan sobre negro sino sobre el degradé del skin.
; Eso es un DMA de la ROM a la RAM, que el DMA normal no sabe hacer: va por la
; ventana que la WRAM tiene en el bus B, o sea WMADD más $2180.

; Cuántos caracteres por vuelta del lazo. El número está **medido**, no
; elegido: componiendo el mensaje de `snes-anclada` sobre el mapa 6, con 5 no se
; pierde un cuadro, con 6 tampoco y con 8 se pierde uno. Va en 5 y no en 7 por
; margen, porque la vuelta cuesta distinto en cada mapa —el streaming del fondo,
; los NPCs, la música— y perder cuadros no se ve mirando: lo que pasa es que el
; héroe camina más lento que en RM2k.
;
; Lo que cuesta: el mensaje de tres renglones y 51 caracteres de `snes-ventana`
; tarda unos 15 cuadros en aparecer, y uno de cuatro renglones llenos tardaría
; unos 36. Es un cuarto de segundo, que en RM2k tampoco desentona: allá la
; ventana se abre con una animación.
MSG_CHARS = 5

; Dónde empieza el texto adentro de la ventana, en pixeles. Es el `border_x` de
; `Window`, el mismo que usa `tools/port/ventana.py`.
VENTANA_BORDE = 8

; La fila del glifo cae dos pixeles abajo del borde de la celda, y eso no
; depende del renglón: los cuatro empiezan en 10, 26, 42 y 58, que módulo 8 dan
; todos 2. Por eso un glifo de doce filas entra siempre en las mismas dos filas
; de celda y el buffer puede ser de dos.
TEXTO_OFS_Y = 2

; Un byte más adelante en el bloque de textos, cruzando la ventana de banco.
;
; `msg_ptr` es un puntero largo pero el compositor lo avanzaba con un `inc` de
; dieciséis bits, así que al pasar de $FFFF volvía al $0000 del **mismo** banco.
; En LoROM ahí no hay ROM: lo que sigue a $FFFF es el $8000 del banco siguiente,
; que es lo que ya sabían `ptr_mas` y `msg_empezar`.
;
; No es teórico y no bastaba con arreglar `msg_empezar`: el bloque de textos de
; `abl` mide 56 KB, o sea que cruza, y **un cuadro cuyos bytes caen
; encima del borde** empieza bien y sigue leyendo basura. Es la cinemática de
; los Neon Vipers del mapa 14: de la basura salía un largo de renglón de 76
; caracteres y con él la pantalla hecha basura, por el camino que el tope de
; `mensaje_tick` ahora corta.
.proc msg_ptr_sig
.a16
.i16
    inc msg_ptr
    bne listo
    lda #$8000
    sta msg_ptr
    sep #$20
.a8
    inc msg_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

; Arranca un mensaje: deja el puntero en su primer renglón y el compositor en
; marcha. La ventana no aparece hasta que termine.
;
; **A trae el desplazamiento del cuadro dentro de `mensajes`, en 16 bits**, y
; hay que sumárselo a un puntero largo cruzando bancos: ver el lazo de abajo y
; `msg_ptr_sig`, que es la misma cuenta para avanzar de a un byte.
.assert MENSAJES_TOPE = 4 * $10000, error, "msg_empezar multiplica el desplazamiento por cuatro: es MENSAJES_PASO en eventos.py"
.proc msg_empezar
.a16
.i16
    ; El desplazamiento es de dieciséis bits y el bloque de textos puede medir
    ; **más que la ventana de un banco de LoROM**: con los
    ; 29 mapas de `abl` son 48972 bytes y arranca en $46:8000, así que
    ; desde el desplazamiento $8000 la suma se pasa de $FFFF. Lo que sigue a
    ; $FFFF no es el $0000 del banco que viene sino su $8000, que es lo mismo
    ; que ya sabía `ptr_mas` para la grilla del mapa; acá se sumaba de a
    ; dieciséis bits y el acarreo se perdía, así que **todo cuadro de texto
    ; pasado el primer banco leía de otro lado**: la cabecera y los largos de
    ; renglón salían de cualquier cosa. El lazo suma un banco por vuelta porque
    ; un bloque de 64 KB cruza hasta dos veces.
    ;
    ; Y el desplazamiento cuenta de a cuatro bytes —`MENSAJES_PASO` en
    ; eventos.py—, así que el bloque llega a 256 KB: los dos bits que se caen
    ; de los `asl` van a `temp`, y cada uno de lo que junta son 64 KB, o sea
    ; dos bancos de LoROM. Con `rol` y no con un salto por bit a propósito:
    ; así el bit de arriba —más de 128 KB, que ningún cartucho de la tanda
    ; alcanza— corre las mismas instrucciones que el de abajo, que sí.
    phx
    stz temp
    asl a
    rol temp
    asl a
    rol temp
    pha
    lda temp
    asl a                       ; dos bancos por cada 64 KB
    clc
    adc #^mensajes
    tax
    pla
    clc
    adc #.loword(mensajes)
otro_banco:
    bcc en_el_banco
    inx
    clc
    adc #$8000
    bra otro_banco
en_el_banco:
    sta msg_ptr
    sep #$20
.a8
    txa
    sta msg_ptr + 2
    rep #$20
.a16
    plx
    ; La cola de escapes arranca limpia antes de leer la cabecera: una pausa de
    ; basura ahí dejaría la página frenada para siempre.
    lda #0
    sta f:FAR_MSG_PAUSA         ; `stz` no tiene modo largo
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ldy #0
    lda [msg_ptr], y            ; la cabecera: los renglones en los tres bits
    sta msg_lineas              ; de abajo, el autocierre en el 3 y las pausas
                                ; en el nibble de arriba. Se guarda entera y la
                                ; enmascara quien la lea; un byte más en el
                                ; banco 0 es justo lo que no hay.
    and #CABECERA_AUTOCIERRE
    sta f:FAR_MSG_AUTO
    lda msg_lineas
    lsr
    lsr
    lsr
    lsr                         ; cuántas pausas trae
    beq sin_pausa
    ; Y cuánto duran: `CUADROS_DE_PAUSA` cada una, que son 61 y no 60. El
    ; producto va en 16 bits porque quince pausas son 915 cuadros, así que lo
    ; hace el hardware, como el tinte.
    sta WRMPYA
    lda #CUADROS_DE_PAUSA
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta f:FAR_MSG_PAUSA
    sep #$20
.a8
sin_pausa:
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
    stz msg_linea
    stz msg_cebada
    stz msg_subir
    lda #1
    sta msg_estado
    rts
.endproc

; Un cuadro del compositor, desde el lazo principal.
.proc mensaje_tick
.a8
.i16
    lda msg_estado
    cmp #1
    beq trabajando
    rts
trabajando:
    lda msg_subir
    beq sin_subir
    rts                         ; el renglón anterior todavía no subió
sin_subir:
    lda msg_cebada
    bne componiendo

    ; Renglón nuevo: se le copia el fondo y se lee su largo. Los renglones que
    ; el mensaje no trae igual se ceban y se suben: en la VRAM está el texto del
    ; mensaje anterior y hay que taparlo.
    jsr cebar_linea
    stz msg_largo
    lda msg_lineas
    and #CABECERA_LINEAS        ; la cabecera trae además la cola de escapes
    sta temp
    lda msg_linea
    cmp temp
    bcs vacio
    ldy #0
    lda [msg_ptr], y
    sta msg_largo
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
vacio:
    stz msg_col
    lda #1
    sta msg_cebada

componiendo:
    ldx #MSG_CHARS
otro:
    lda msg_col
    cmp msg_largo
    bcs fin_linea
    ldy #0
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sta comp_char
    lda msg_col
    and #$00FF
    sta comp_col
    jsr msg_ptr_sig
    sep #$20
.a8
    inc msg_col
    ; El tope de la columna. El byte se consume igual —si no, el puntero
    ; quedaría desfasado y el renglón que sigue leería del medio de éste— pero
    ; no se dibuja: `componer_char` escribe en `texto_buf` con un desplazamiento
    ; que sale de la columna, y a partir de la 39 eso cae **afuera** del buffer,
    ; encima del HDMA de la ventana, de la imagen de OAM y de `vq_n`. Ver el
    ; comentario de `componer_char`, más abajo.
    ;
    ; Y el tope va acá aunque el conversor no emita nunca un renglón más largo,
    ; porque **el síntoma no señala al texto**: con `vq_n` pisado, `vram_drenar`
    ; sube bloques de 128 bytes a direcciones cualquiera de la VRAM, así que un
    ; largo de renglón malo se ve como la pantalla entera hecha basura unos
    ; cuadros más tarde y en otro mapa.
    lda comp_col
    cmp #MENSAJE_COLS
    bcs sin_dibujar
    phx
    jsr componer_char
    plx
sin_dibujar:
    dex
    bne otro
    rts

fin_linea:
    ; El renglón está listo: se sube en el vblank que viene y se pasa al que
    ; sigue. El fondo del próximo no se ceba en este mismo cuadro a propósito:
    ; el buffer todavía tiene lo que hay que subir.
    lda #1
    sta msg_subir
    stz msg_cebada
    inc msg_linea
    lda msg_linea
    cmp #VENTANA_LINEAS_TEXTO
    bcc mas
    lda #2
    sta msg_estado              ; ya está: `flush_video` prende el HDMA
mas:
    rts
.endproc

; Copia al buffer el fondo de las dos filas de celda del renglón en curso. Es
; la única forma de que los glifos queden sobre el degradé del skin y no sobre
; negro, y va por DMA de la ROM a la RAM.
.proc cebar_linea
.a8
.i16
    rep #$20
.a16
    ; El destino: siempre el principio del buffer.
    lda #.loword(texto_buf)
    sta WMADDL
    sep #$20
.a8
    stz WMADDH                  ; el buffer vive en el banco 0 de la WRAM

    rep #$20
.a16
    ; El origen: dos filas de celda por renglón, 60 tiles de 32 bytes.
    lda msg_linea
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; renglón * 64
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; renglón * 60, o sea los tiles que ya pasaron
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32 bytes cada uno
    clc
    adc #.loword(ventana_fondo)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_fondo
    sta A1B0
    lda #$00                    ; un registro, de a un byte
    sta DMAP0
    lda #<WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Sube el renglón compuesto al banco de tiles de la ventana. Va en el vblank,
; desde `flush_video`, y son 1920 bytes de un solo DMA.
.proc subir_linea
.a8
.i16
    stz msg_subir
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    rep #$20
.a16
    ; El tile donde arranca este renglón, en palabras de VRAM. El renglón que
    ; hay que subir es el anterior: `mensaje_tick` ya pasó al siguiente.
    lda msg_linea
    and #$00FF
    dec a
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; renglón * 60 tiles
    clc
    adc #VENTANA_TEXTO_BASE
    asl a
    asl a
    asl a
    asl a                       ; por 16 palabras cada tile
    clc
    adc f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el buffer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Un caracter, desde sus datos ya compuestos: `fuente_pre0` a `fuente_pre3`,
; una tabla por fase, que arma `fuente_prerender` en el conversor. Por cada
; una de las FUENTE_PRE_FILAS filas y cada una de las dos celdas que puede
; pisar vienen tres palabras —qué se conserva del buffer, y qué se prende en
; los planos 0-1 y en los 2-3—, así que pintar es leer, enmascarar y
; escribir. Una celda que no toca nada viene con la máscara en $FFFF y se
; saltea.
;
; **La columna la topa `mensaje_tick`**, no esto: acá `comp_col` ya llegó como
; buena y el desplazamiento que sale de ella se usa sin mirar. El tope está allá
; porque el byte hay que consumirlo igual aunque no se dibuje.
;
; Hasta el 2026-09-11 esto pintaba cada fila dos veces —la sombra y después
; el glifo, con una rutina `pintar` que armaba las máscaras en cada llamada—
; y corría la fila de a un bit hasta su fase: unas 25 líneas por carácter, y
; con MSG_CHARS en 5 era lo que más costaba del cuadro mientras se armaba un
; mensaje. taro lo notó en la apertura, con lluvia. El resultado es el mismo
; byte por byte: el orden de `Font::Render` —la sombra de una fila la pisa el
; glifo de la siguiente— ya viene resuelto en las tablas.
.proc componer_char
.a8
.i16
    lda comp_char
    sta WRMPYA
    lda #FUENTE_PRE_CHAR
    sta WRMPYB                  ; arranca: lo que sigue le da los ocho ciclos

    ; Dónde cae: x = borde + 6 por columna, y de ahí la celda y la fase.
    rep #$20
.a16
    lda comp_col
    sta temp
    asl a
    clc
    adc temp
    asl a                       ; por 6
    clc
    adc #VENTANA_BORDE
    sta temp                    ; x adentro de la ventana
    and #$0007
    sta comp_fase               ; 0, 2, 4 o 6
    lda temp
    lsr a
    lsr a
    lsr a
    sec
    sbc #VENTANA_TEXTO_COL      ; la columna de celda, contada desde el texto
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32 bytes de tile
    sta comp_base

    ; Sus datos: la tabla de su fase, más el carácter por FUENTE_PRE_CHAR.
    ldx comp_fase
    lda f:fuente_pre_lo, x
    clc
    adc RDMPYL
    sta comp_glifo
    sep #$20
.a8
    lda f:fuente_pre_bk, x
    sta comp_glifo + 2

    ldy #0
    lda #(TEXTO_OFS_Y * 2)
    sta comp_fila               ; de a dos: es el índice en `tabla_fila_buf`
fila:
    rep #$20
.a16
    lda comp_fila
    and #$00FF
    tax
    lda f:tabla_fila_buf, x
    clc
    adc comp_base
    tax                         ; X = el byte del buffer donde arranca la fila
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_primera
    sta comp_and
    iny
    iny
    lda texto_buf, x            ; planos 0 y 1 de la primera celda
    and comp_and
    ora [comp_glifo], y
    sta texto_buf, x
    iny
    iny
    lda texto_buf + 16, x       ; planos 2 y 3
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 16, x
    iny
    iny
    bra segunda
sin_primera:
    tya
    clc
    adc #6
    tay
segunda:
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_segunda
    sta comp_and
    iny
    iny
    lda texto_buf + 32, x       ; la celda de al lado, un tile más adelante
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 32, x
    iny
    iny
    lda texto_buf + 48, x
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 48, x
    iny
    iny
    bra otra_fila
sin_segunda:
    tya
    clc
    adc #6
    tay
otra_fila:
    sep #$20
.a8
    lda comp_fila
    clc
    adc #2
    sta comp_fila
    cmp #((TEXTO_OFS_Y + FUENTE_PRE_FILAS) * 2)
    bcc fila
    rts
.endproc

