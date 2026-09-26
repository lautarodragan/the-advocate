.segment "CODE"

; Deja en A1T0L/A1B0 el puntero de 24 bits que el registro del mapa guarda en el
; campo que venga en Y. Los tres bytes del puntero están seguidos, así que la
; parte baja sale de una lectura de 16 bits y el banco de la de al lado.
; La cuenta va con el acumulador en 16 bits de punta a punta. Hacerla en 8 y
; después `tax` no sirve: el acumulador del 65816 son 16 bits siempre, y `tax`
; con X ancho transfiere los dos bytes, incluido el alto que quedó de la
; operación anterior. Con el mapa 7 daba cero de casualidad para los tiles y
; basura para la paleta.
.proc dma_origen
.a8
.i16
    rep #$20
.a16
    tya                         ; el desplazamiento del campo
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta A1T0L
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta A1B0
    rts
.endproc

.proc load_map
.a8
.i16
    ldx mapa_ofs
    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_TILES, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_MAP_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 64 bytes por tile de 8 bits
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- la animación del ChipSet ---
    ; El mapa trae en la VRAM el dibujo 0 de cada corrida y el reloj puede estar
    ; en cualquier otro: es un reloj de la partida y no del mapa. Acá se sube el
    ; que toca, sin presupuesto de vblank porque la pantalla está apagada.
    jsr anim_cargar

    ; --- los colores ---
    ;
    ; Primero lo de abajo, que es de toda la ROM y no de este mapa: el color de
    ; fondo de la pantalla y la paleta de la ventana de mensaje. Va acá y no en
    ; `load_ventana` porque `load_ventana` se saltea entera cuando la ROM no
    ; lleva ventana, y el color de fondo hace falta igual.
    stz CGADD
    rep #$20
.a16
    lda #.loword(ventana_cgram)
    sta A1T0L
    lda #(CGRAM_BASE * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_cgram
    sta A1B0
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; Y encima el mapa, que arranca donde termina lo reservado.
    lda #CGRAM_BASE
    sta CGADD
    ldy #M_PTR_MAP_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    asl a                       ; dos bytes por color
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; El tilemap no se sube acá: no existe uno entero para subir. Lo arma
    ; fill_window a partir de los bloques, y desde ahí lo mantiene el streaming.
    rts
.endproc

; --- los sprites -----------------------------------------------------------
.proc load_sprite
.a8
.i16
    ; El banco que sube acá trae una pose por ranura. La cola de subidas
    ; arranca vacía, y la pose del héroe en VRAM es la que puso el conversor
    ; —mirando abajo— salvo que mire a otro lado: `place_hero` lo resuelve en
    ; el primer cuadro, con la pantalla todavía apagada.
    stz vq_n
    lda #$FF
    sta hero_pose_vram
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_SPRITE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_SPRITE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por tile de 4 bits
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; La paleta va a la mitad de arriba de CGRAM, que es la de los sprites: la
    ; 8 arranca en el color 128.
    lda #128
    sta CGADD
    ldy #M_PTR_SPRITE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    lda f:mapa_tabla + M_OBSEL_VALUE, x
    sta OBSEL
    rts
.endproc

; --- OAM -------------------------------------------------------------------
; Todos los objetos arrancan escondidos. Un objeto de 32 de alto en la fila 224
; ocupa de la 224 a la 255, o sea entero fuera de las 224 que se ven, y sin
; darle la vuelta al contador.
.proc clear_oam
.a8
.i16
    ldx #$0000
borrar:
    lda #$E0
    sta oam + 1, x              ; la Y de cada objeto
    inx
    inx
    inx
    inx
    cpx #512
    bne borrar

    ; La tabla chica: dos bits por objeto, el alto dice si es grande. Sólo el
    ; objeto 0 lo es; el resto quedan chicos y escondidos igual.
    ldx #$0000
chica:
    stz oam_high, x
    inx
    cpx #32
    bne chica
    lda #$02
    sta oam_high                ; objeto 0: tamaño grande
    rts
.endproc

.proc push_oam
.a8
.i16
    stz OAMADDL
    stz OAMADDL + 1
    ldx #.loword(oam)
    stx A1T0L
    lda #^oam
    sta A1B0
    ldy #544                    ; los 512 de la tabla grande más los 32 chicos
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$04
    sta BBAD0                   ; destino: OAMDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; --- las poses en caliente ---------------------------------------------------
; En VRAM vive una pose por personaje: el héroe en el bloque 0 y cada NPC que
; camina en su ranura. Las doce poses de cada uno están en el cartucho, y
; cuando alguien quiere dibujarse con otra, la encola acá y sube en el vblank
; que viene, en el mismo `flush_video` que sube la OAM que ya cuenta con ella.
; Es lo que hacen los RPG de la consola con más de dos personajes animados:
; con todas las poses residentes, 512 tiles son dos personajes y medio.
;
; Encola la pose que está en `vq_src` (24 bits, en el cartucho) para la
; ranura que arranca en la palabra `vq_dest`. Devuelve A distinto de cero si
; entró; si la cola está llena, quien llama tiene que volver a pedirla.
.proc vram_encolar
.a8
.i16
    lda vq_n
    cmp #VQ_MAX
    bcc hay_lugar
    lda #0
    rts
hay_lugar:
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; por cinco
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda vq_src
    sta vq + 0, x
    lda vq_src + 1
    sta vq + 1, x
    lda vq_src + 2
    sta vq + 2, x
    lda vq_dest
    sta vq + 3, x
    lda vq_dest + 1
    sta vq + 4, x
    inc vq_n
    lda #1
    rts
.endproc

; Sube hasta VQ_POR_CUADRO poses de la cola y deja las demás al principio.
; Cada pose son cuatro DMA de 128 bytes: las cuatro filas del bloque de 4x4,
; que en la grilla de nombres están a 256 palabras una de otra.
.proc vram_drenar
.a8
.i16
    lda vq_n
    bne hay
    rts
hay:
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    stz vq_hechas
    ldx #$0000                  ; la entrada, en bytes
otra:
    lda vq_hechas
    cmp vq_n
    beq fin
    cmp vq_tope
    beq fin
    lda vq + 2, x
    sta A1B0                    ; el banco del origen
    rep #$20
.a16
    lda vq + 0, x
    sta vq_src
    lda vq + 3, x
    sta vq_dest
    sep #$20
.a8
    lda #4
    sta vq_filas
fila:
    rep #$20
.a16
    lda vq_dest
    sta VMADDL
    lda vq_src
    sta A1T0L
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda vq_src
    clc
    adc #128
    sta vq_src
    lda vq_dest
    clc
    adc #256                    ; la fila que sigue de la grilla de nombres
    sta vq_dest
    sep #$20
.a8
    dec vq_filas
    bne fila
    inc vq_hechas
    rep #$20
.a16
    txa
    clc
    adc #VQ_STRIDE
    tax
    sep #$20
.a8
    bra otra
fin:
    ; Lo que no entró, al principio de la cola. X apunta a la primera entrada
    ; que quedó.
    lda vq_n
    sec
    sbc vq_hechas
    sta vq_n
    beq listo
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; los bytes que quedan: entradas por cinco
    sta temp + 2
    ldy #$0000
mover:
    lda vq, x
    sta vq, y
    inx
    iny
    dec temp + 2
    bne mover
listo:
    rts
.endproc

; --- la capa que va por encima del héroe -----------------------------------
; Sus tiles y su paleta se suben una sola vez, con la pantalla apagada. Su
; tilemap no: va en la misma ventana móvil que el del fondo, y lo llena el
; streaming.
.proc load_above
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    ; La base de BG2 no tiene campo propio en el registro, que está lleno: es
    ; el nibble alto de BG12NBA, en pasos de 4096 palabras. El byte de arriba
    ; que trae la lectura de dieciséis bits es ABOVE_FIRST, y se tira.
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    and #$00F0
    xba
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_ABOVE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; son de 4 bits: 32 bytes por tile
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Su paleta va en las últimas paletas de la mitad baja de CGRAM, que el
    ; fondo de 8 bits deja libres. Cuántas y desde dónde lo decidió el
    ; conversor mapa por mapa, así que viene en el registro.
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    sta CGADD
    ldy #M_PTR_ABOVE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; La tabla de NPCs a la RAM, que es de donde build_oam la lee.
;
; Con un lazo y no con un DMA: para llegar a la WRAM el DMA tiene que pasar por
; el puerto $2180 y dejar la dirección puesta en $2181-$2183, que son tres
; registros más que acordarse de cargar. Son mil bytes como mucho y esto corre
; una vez por mapa, así que el lazo no le cuesta nada a nadie y no puede
; escribir en el lugar equivocado.
.proc load_npcs
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_NPC_TABLE
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x           ; los 16 bits bajos del puntero
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x       ; y su banco
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; por dieciséis: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "la cuenta de arriba multiplica por dieciséis a mano"
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq listo
    lda [npc_ptr], y
    sta npc_buf, y
    iny
    bra copiar
listo:
    rts
.endproc

; Y la tabla de gráficos de la orden 34, con el mismo lazo y el mismo puntero
; prestado. Son dieciséis bytes como mucho.
.proc load_ruta_graficos
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_RUTA_GRAFICO
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_RUTA_GRAFICO_COUNT, x
    asl a                       ; dos bytes por gráfico
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq listo
    lda [npc_ptr], y
    sta ruta_graf_buf, y
    iny
    bra copiar
listo:
    rts
.endproc

; La tabla de posiciones de eventos a la RAM, y las rutas que hubiera corriendo
; a la basura.
;
; Lo segundo es lo que hace RM2k al cambiar de mapa: las rutas forzadas son de
; los eventos del mapa que se deja, y allá no queda nadie caminando.
;
; Reusa `npc_ptr`, que sólo vive mientras se copia una tabla y nunca las dos a
; la vez.
.proc load_ev_pos
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_EV_POS
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x           ; los 16 bits bajos del puntero
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x       ; y su banco
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_EV_COUNT, x
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq tablas
    lda [npc_ptr], y
    sta ev_pos_buf, y
    iny
    bra copiar

tablas:
    stz ruta_ev_tope            ; ninguna ranura usada todavía en este mapa
    ldx #$0000
libre:
    lda #RUTA_EV_LIBRE
    sta ruta_ev, x
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc libre

    ; Y los destellos, que también son de los eventos del mapa que se deja.
    ldx #$0000
sin_flash:
    lda #FLASH_LIBRE
    sta flash_ev, x
    stz flash_ev + 7, x         ; ninguna paleta pendiente: la RAM arranca con
                                ; basura y el vblank lee esto
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc sin_flash
    stz ruta_paso
    rts
.endproc

