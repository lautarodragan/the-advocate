.segment "CODE"

; --- lo que va sí o sí dentro del vblank -----------------------------------
; OAM sólo se puede escribir mientras el PPU no la está leyendo, o sea en el
; vblank. Armarla lleva su tiempo —con treinta y pico de personajes, más de un
; milisegundo— así que armarla y subirla en el mismo vblank no entra: la subida
; termina cayendo afuera y los objetos salen en cualquier lado.
;
; Por eso se sube lo del cuadro anterior apenas empieza el vblank, y recién
; después se arma la del siguiente. El scroll va junto, para que el fondo y los
; sprites correspondan al mismo momento.
.proc flush_video
.a8
.i16
    jsr push_oam
    lda destello_listo
    beq sin_destello
    jsr subir_destello          ; el destello, o el tinte, van antes que las
    lda #2                      ; poses y les comen presupuesto en este
    sta vq_tope                 ; mismo vblank
    bra sin_tinte
sin_destello:
    lda tinte_listo
    beq sin_tinte
    jsr subir_tinte
    lda #2
    sta vq_tope
sin_tinte:
    ; Y un renglón de la ventana esperando también les come presupuesto: son
    ; 1920 bytes de un solo DMA, casi cuatro poses. Con las cinco de siempre el
    ; vblank se termina en el medio y lo que falta del renglón se escribe con
    ; la pantalla encendida, o sea que no se escribe: queda una franja de
    ; basura en la ventana, **fija**, y sólo en un mapa con muchos eventos
    ; moviéndose. taro la vio en Lashe City el 2026-09-08 hablándole al
    ; mecánico y al linyera; apareció con los eventos paralelos, que sumaron
    ; nueve personajes que se mueven y por lo tanto nueve poses por subir.
    lda msg_subir
    beq sin_renglon
    lda #1
    sta vq_tope
sin_renglon:
    ; Y una tira del mapa esperando —la fila o la columna que la cámara
    ; destapó— también: `push_strips` corre después de las poses y hasta el
    ; 2026-09-10 no descontaba nada, así que en un vblank con las cinco poses
    ; sus DMA caían con la pantalla encendida y la VRAM los ignoraba. La fila
    ; quedaba sin dibujar hasta que la cámara volviera a pasar por ahí. taro lo
    ; vio jugando el 2026-09-09, "medio random", y lo reproduce EV0041 del
    ; mapa 8: el salto del héroe encola poses nuevas justo cuando la cámara
    ; cruza una fila. Una fila son cuatro DMA de 64 bytes, media pose: se le
    ; descuenta una entera para no andar midiendo el borde.
    lda row_addr
    ora row_addr + 1
    ora col_addr
    ora col_addr + 1
    beq sin_tira
    lda vq_tope
    beq sin_tira
    dec a
    sta vq_tope
sin_tira:
    ; Y un paso de la animación del ChipSet, que también sale de este vblank:
    ; hasta 26 tiles de fondo, o sea 1664 bytes, que es más de tres poses. Se lo
    ; descuenta al presupuesto en vez de fijarlo, para que se sume a lo que ya
    ; se hayan llevado el tinte o un renglón de la ventana.
    jsr anim_flush
    ; Y los 2 KB del cuadro de la animación de batalla, si el tick pidió uno
    ; nuevo. Es lo más caro que se sube en un vblank —cuatro poses de las
    ; cinco— y pasa una vez cada dos cuadros. Va **antes** de `vram_drenar` por
    ; lo mismo que `anim_flush`: lo que se lleva tiene que salir del
    ; presupuesto de este vblank, y tres líneas más abajo `vq_tope` ya se
    ; resetea para el que viene. Ver `animacion_dibujo_dma`.
    lda f:ANIMB_SUBIR
    beq sin_anim_cuadro
    lda #0
    sta f:ANIMB_SUBIR
    jsr animacion_dibujo_dma
sin_anim_cuadro:
    jsr vram_drenar             ; las poses que esta OAM ya da por subidas
    lda #VQ_POR_CUADRO
    sta vq_tope                 ; el vblank que viene arranca con todo

    ; Las paletas de los destellos que quedaron pendientes del cuadro
    ; anterior, **todas**: una por ranura. Ver FAR_FLASH_PAL.
    ldx #$0000
otro_flash:
    lda flash_ev + 7, x
    beq sin_flash
    stz flash_ev + 7, x
    sta CGADD
    rep #$20
.a16
    txa
    asl a
    asl a                       ; de ocho bytes por ranura a treinta y dos
    clc
    adc #.loword(FAR_FLASH_PAL)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^FAR_FLASH_PAL
    sta A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_flash:
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc otro_flash

    ; Y la paleta del cartel, si la rampa la rehizo este cuadro. Son treinta y
    ; dos bytes y van aparte de las tres del mapa: la entrada del cartel cae
    ; arriba de `SPRITE_CGRAM`, o sea afuera de lo que sube `subir_paletas`.
    lda f:CARTEL_LISTO
    beq sin_imagen
    lda #0
    sta f:CARTEL_LISTO
    lda #(128 + 16 * IMAGEN_PAL)
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * (128 + 16 * IMAGEN_PAL))
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_imagen:

    ; Y la paleta de la animación de batalla, si acaba de empezar una. Son los
    ; mismos treinta y dos bytes que el cartel y por lo mismo: su entrada cae
    ; arriba de `SPRITE_CGRAM` y `subir_paletas` no la toca.
    lda f:ANIMB_PAL
    beq sin_anim_pal
    lda #0
    sta f:ANIMB_PAL
    lda f:ANIMB_CGADD
    sta CGADD
    rep #$20
.a16
    lda f:ANIMB_SOMBRA
    clc
    adc #.loword(cgram_sombra)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_anim_pal:

    ; Los dos registros de scroll son de escritura doble: primero el byte bajo
    ; y después el alto.
    ; Cada registro se completa antes de pasar al siguiente. Los de scroll
    ; comparten un único latch entre todos los planos, así que intercalar las
    ; escrituras —BG1 bajo, BG2 bajo, BG1 alto, BG2 alto— mezcla los valores y
    ; el plano queda desplazado dentro de su celda, moviéndose en el lugar.
    lda pantalla_x              ; la cámara más la sacudida, si la hay
    sta BG1HOFS
    lda pantalla_x + 1
    sta BG1HOFS
    lda pantalla_x
    sta BG2HOFS
    lda pantalla_x + 1
    sta BG2HOFS

    lda scroll_y
    sta BG1VOFS
    lda scroll_y + 1
    sta BG1VOFS
    lda scroll_y
    sta BG2VOFS
    lda scroll_y + 1
    sta BG2VOFS

    jsr push_strips

    ; Y el HDMA de la ventana de mensaje: prendido mientras haya una en
    ; pantalla, apagado cuando no. Eso es **todo** lo que cuesta abrirla y
    ; cerrarla; el tilemap propio ya está escrito desde que se cargó el mapa.
    ;
    ; Los dos tramos de arriba de la tabla de scroll llevan la cámara de este
    ; cuadro, la misma que se acaba de escribir en los registros: el HDMA los
    ; vuelve a escribir en la línea 0 y no cambia nada. Lo que cambia es la
    ; línea 144 para abajo.
    ; Primero el compositor: el renglón que dejó listo, y la ventana entera
    ; cuando ya no queda ninguno.
    lda msg_subir
    beq sin_subir
    jsr subir_linea
sin_subir:
    lda msg_estado
    cmp #2
    bne no_termino
    stz msg_estado
    lda #1
    sta msg_abierto
no_termino:

    lda msg_abierto
    beq sin_ventana
    lda pantalla_x
    sta hdma_ofs + 1
    sta hdma_ofs + 6
    lda pantalla_x + 1
    sta hdma_ofs + 2
    sta hdma_ofs + 7
    lda scroll_y
    sta hdma_ofs + 3
    sta hdma_ofs + 8
    lda scroll_y + 1
    sta hdma_ofs + 4
    sta hdma_ofs + 9
    lda #HDMA_VENTANA
    sta HDMAEN
    bra prender
sin_ventana:
    stz HDMAEN
    ; Sin HDMA la máscara de objetos queda como la dejó la última línea, que
    ; es prendida: se apaga a mano, como BG2SC acá abajo.
    stz WOBJSEL
    ; BG2SC hay que devolverlo a mano: el HDMA lo dejó con el tilemap de la
    ; ventana en la última línea que escribió, y sin HDMA nadie lo vuelve a
    ; tocar. Cuesta dos instrucciones y evita tener que acordarse de esto al
    ; cerrar un mensaje.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC

    ; Y último de todo, el brillo maestro.
    ;
    ; **INIDISP se escribe únicamente acá**, y eso no es prolijidad: es lo que
    ; hace que el brillo cambie entre dos cuadros y no a mitad de uno. Escribirlo
    ; desde el lazo dibuja el cuadro partido —lo de arriba con el brillo viejo y
    ; lo de abajo con el nuevo—, que es exactamente el defecto que se veía en
    ; cada teletransporte: la pantalla volvía a prenderse cuando terminaba la
    ; carga, o sea a mitad de cuadro, y encima con el scroll y OAM del mapa
    ; viejo, porque esos también se escriben acá y sólo en el vblank.
    ;
    ; Quien quiera cambiar el brillo escribe `brillo` y espera al vblank
    ; siguiente, igual que quien mueve un sprite escribe OAM y espera. La única
    ; excepción es el blanking forzado de una carga, que `fundido_tick` escribe
    ; a mano: ahí la pantalla ya está en negro y el cambio no se ve.
prender:
    lda brillo
    sta INIDISP
    rts
.endproc

; Sube Y bytes desde la dirección X de la RAM a la VRAM, que ya quedó apuntada.
.proc dma_a_vram
.a8
.i16
    stx A1T0L
    lda tira_banco              ; 0 la tira de esta vuelta, $7E la de repuesto
    sta A1B0
    sty DAS0L
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

; Las tiras que dejó armadas stream_map. Van acá y no donde se arman porque la
; VRAM sólo se puede escribir en el vblank; armarlas adentro no entraría.
.proc push_strips
.a8
.i16
    ; Cuatro tiras como mucho: la columna y la fila que armó esta vuelta, y las
    ; de repuesto que dejó guardadas si la cámara destapó dos de un eje. Cada
    ; una sube sola, y una dirección en cero es que no hay ninguna.
    ldx col_addr_b
    beq sin_columna_b
    stx tira_vram
    ldx #.loword(FAR_TIRA_COL)
    stx tira_de
    lda #^FAR_TIRA_COL
    sta tira_banco
    jsr push_una_columna
sin_columna_b:
    ldx col_addr
    beq sin_columna
    stx tira_vram
    ldx #.loword(tira_col)
    stx tira_de
    stz tira_banco
    jsr push_una_columna
sin_columna:

    ldx row_addr_b
    beq sin_fila_b
    stx tira_vram
    ldx #.loword(FAR_TIRA_ROW)
    stx tira_de
    lda #^FAR_TIRA_ROW
    sta tira_banco
    jsr push_una_fila
sin_fila_b:
    ldx row_addr
    beq sin_fila
    stx tira_vram
    ldx #.loword(tira_row)
    stx tira_de
    stz tira_banco
    jsr push_una_fila
sin_fila:
    ; Las cuatro consumidas, tirando también las que no se subieron por estar
    ; en cero: lo que no se armó en esta vuelta no se arma en la siguiente.
    rep #$20
.a16
    stz col_addr
    stz col_addr_b
    stz row_addr
    stz row_addr_b
    sep #$20
.a8
    rts
.endproc

; Una columna del tilemap a la VRAM: a la palabra `tira_vram`, desde `tira_de`
; en el banco `tira_banco`. Sale de un DMA por capa, porque el PPU puede
; avanzar de a 32 palabras tras cada escritura, que es justo lo que mide una
; fila del tilemap.
;
; Las dos variables **avanzan a medida que la tira se consume**, y no se usa
; `temp` para eso aunque esté a mano: `fill_window` guarda ahí el número de
; columna por la que va y lo lee **después** de llamar a `push_strips`, así que
; pisarlo le rompe el lazo. Costó una tanda entera con las 957 celdas visibles
; distintas, el 2026-09-22.
.proc push_una_columna
.a8
.i16
    lda #$81                    ; avanzar 32 palabras tras el byte alto
    sta VMAIN
    ldx tira_vram
    stx VMADDL
    ldx tira_de
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram

    ; La capa de encima: media ventana más adelante en la VRAM, y su tira
    ; pegada a la otra en la RAM.
    rep #$20
.a16
    lda tira_vram
    clc
    adc #(VRAM_ABOVE_MAP - VRAM_MAP)
    sta tira_vram
    lda tira_de
    clc
    adc #(WINDOW_ROWS * 2)
    sta tira_de
    sep #$20
.a8
    ldx tira_vram
    stx VMADDL
    ldx tira_de
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram
    rts
.endproc

; Y una fila, que sale de cuatro: las dos pantallas de 32x32 no son contiguas
; —la de la derecha vive 1024 palabras más adelante— y la capa de encima vive
; media ventana más allá. El orden es: fondo izquierda, fondo derecha, encima
; izquierda, encima derecha, y cada paso avanza las dos variables.
.proc push_una_fila
.a8
.i16
    lda #$80                    ; avanzar una palabra: la fila es contigua
    sta VMAIN
    ldx tira_vram
    stx VMADDL
    ldx tira_de
    ldy #WINDOW_COLS            ; las ranuras 0 a 31, la pantalla izquierda
    jsr dma_a_vram
    rep #$20
.a16
    lda #1024                   ; la pantalla de la derecha vive acá
    jsr fila_siguiente
    ; Y la capa de encima, media ventana más adelante: se descuenta el 1024 que
    ; el paso anterior ya sumó.
    lda #(VRAM_ABOVE_MAP - VRAM_MAP - 1024)
    jsr fila_siguiente
    lda #1024                   ; y su mitad derecha
    jsr fila_siguiente
    sep #$20
.a8
    rts
.endproc

; La media fila que sigue: corre la VRAM lo que diga A —en palabras— y la
; fuente los 64 bytes que mide media fila, y la sube. Entra y sale con A de
; dieciséis bits, que es lo que deja encadenar las tres llamadas de arriba.
.proc fila_siguiente
.a16
.i16
    clc
    adc tira_vram
    sta tira_vram
    lda tira_de
    clc
    adc #WINDOW_COLS
    sta tira_de
    sep #$20
.a8
    ldx tira_vram
    stx VMADDL
    ldx tira_de
    ldy #WINDOW_COLS
    jsr dma_a_vram
    rep #$20
.a16
    rts
.endproc

