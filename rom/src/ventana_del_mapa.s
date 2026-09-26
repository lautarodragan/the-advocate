.segment "CODE"

; --- la ventana móvil del mapa ---------------------------------------------
; El tilemap del PPU son 64x32 celdas y los mapas del juego llegan a 1000x80:
; el mapa entero nunca está en la VRAM. Lo que hay es una ventana que se trata
; como un toro —la celda (mx,my) vive siempre en la ranura (mx mod 64, my mod
; 32)— y que se mantiene reescribiendo la columna o la fila que acaba de entrar
; en pantalla. La que sale queda 32 columnas o 4 filas afuera, así que nadie la
; ve mientras se la pisa.
;
; El scroll por hardware hace la vuelta solo: el registro son 10 bits, o sea
; 1024 pixeles, y 1024 es múltiplo de los 512 que mide la ventana a lo ancho.
; Se le escribe la posición de la cámara tal cual y cae donde tiene que caer.
;
; De la ROM no sale un tilemap sino una grilla de bloques: la celda de 16x16 de
; RM2k, que es la unidad con la que el juego fue dibujado y que se repite
; muchísimo. El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa
; de encima y su pasabilidad, todo junto. Guardarlo así es lo que hace que el
; mapa más grande pase de 175 KB —más que la ROM entera— a 40.

; La grilla llega a 40 KB y no entra en un banco, así que se recorre con un
; puntero de 24 bits. En LoROM un banco sólo tiene sus 32 K de arriba: pasarse
; del $FFFF no lleva al $0000 del banco siguiente sino a su $8000, y estas dos
; rutinas son las únicas que saben eso.
.proc ptr_mas
.a16
.i16
    clc
    adc celdas_ptr
    sta celdas_ptr
    bcc listo
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    inc a
    sta celdas_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

.proc ptr_menos
.a16
.i16
    eor #$FFFF                  ; restar es sumar el complemento
    sec
    adc celdas_ptr
    cmp #$8000
    bcs guarda                  ; sigue dentro de la mitad alta del banco
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    dec a
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
guarda:
    sta celdas_ptr
    rts
.endproc

.proc ptr_desde_celdas
.a16
.i16
    lda celdas
    sta celdas_ptr
    sep #$20
.a8
    lda celdas + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_celdas
.a16
.i16
    lda celdas_ptr
    sta celdas
    sep #$20
.a8
    lda celdas_ptr + 2
    sta celdas + 2
    rep #$20
.a16
    rts
.endproc

; A = el bloque que dice la grilla; vuelve con el que hay que usar, que es otro
; sólo si alguna `TileSubstitution` lo cambió. Pasa por acá **todo** el que lea
; una celda: las dos tiras y la pasabilidad, que en este port viaja adentro del
; bloque. Que la pasabilidad siga a la sustitución es lo que hace RM2k:
; `IsPassableLowerTile` mira `map_info.lower_tiles` antes de `passages_down`.
;
; Usa Y, que en los tres llamadores está libre: los dos que arman tiras la
; cargan justo después con el desplazamiento del bloque, y `pass_del_ptr`
; también. X no se toca, y ahí sí importa: es la ranura de la tira.
;
; Sin sustituciones puestas —los 328 mapas del juego de hoy— son cuatro ciclos
; y una rama, que es lo que costó ponerla en el camino caliente.
.proc celda_sustituida
.a16
.i16
    ldy sub_n
    beq listo
buscar:
    dey
    dey
    cmp sub_clave, y
    beq hallado
    cpy #$0000
    bne buscar
    rts
hallado:
    lda sub_valor, y
listo:
    rts
.endproc

; Arma la columna X del mapa —en celdas de 8x8— y deja en col_addr dónde va.
;
; Se llenan las 32 filas de la ventana, no las 29 que se ven. La ranura de cada
; fila es fija, fila mod 32, así que escribir de más no puede pisar nada que se
; esté mirando, y ahorra tener que llevar la cuenta de qué parte de la columna
; ya estaba bien.
.proc build_column
.a16
.i16
    stz col_addr
    cpx mapa_cw
    bcc dentro
    rts                         ; más allá del borde: no hay nada que dibujar
dentro:

    ; Dónde cae en la VRAM. La ventana son dos pantallas de 32x32 pegadas, y la
    ; de la derecha vive 1024 palabras más adelante, no al lado.
    txa
    and #(WINDOW_COLS - 1)
    sta temp
    and #$001F
    clc
    adc f:FAR_VRAM_MAPA         ; lo elige el reparto: ver LAYOUT_VENTANA_AMBOS
    sta col_addr
    lda temp
    and #$0020
    beq izquierda
    lda col_addr
    clc
    adc #1024
    sta col_addr
izquierda:

    ; El bloque mide 16x16: la columna de bloques es la mitad de la de celdas y
    ; el bit que sobra dice cuál de sus dos mitades toca.
    txa
    and #$0001
    asl a                       ; 0 la mitad izquierda, 2 la derecha
    sta tira_ofs
    txa
    lsr a
    asl a                       ; la columna de bloques, en bytes
    sta temp

    jsr ptr_desde_celdas
    lda temp
    jsr ptr_mas

    ; La fila de arriba de la ventana decide la ranura donde arranca y en qué
    ; mitad del bloque cae.
    lda win_row
    and #$0001
    beq desde_arriba
    lda tira_ofs
    ora #$0004                  ; arranca por la mitad de abajo del bloque
    sta tira_ofs
desde_arriba:
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax                         ; la ranura, en bytes

    ; Cuántas filas hay por delante: la ventana entera, o lo que quede de mapa.
    lda mapa_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcc corta
    lda #WINDOW_ROWS
corta:
    sta tira_resta

    ; El índice del bloque va en Y y la ranura en X, y no al revés: la tabla de
    ; bloques ya no vive en el banco 0 —con varios mapas no entra— así que se
    ; lee con un puntero de 24 bits, y ese modo sólo indexa por Y.
fila:
    lda [celdas_ptr]            ; el bloque de esta celda
    jsr celda_sustituida
    asl a
    asl a
    asl a
    asl a                       ; su registro mide 16 bytes
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_col, x             ; la celda del fondo
    lda [bloques8_ptr], y
    sta tira_col2, x            ; y la de la capa de encima

    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)  ; la ventana da la vuelta
    tax

    lda tira_ofs
    eor #$0004                  ; la otra mitad del bloque
    sta tira_ofs
    and #$0004
    bne misma                   ; sigue en el mismo bloque
    lda tira_paso_col
    jsr ptr_mas                 ; a la fila de bloques siguiente
misma:
    dec tira_resta
    bne fila
    rts
.endproc

; La imagen espejada de la anterior: arma la fila X del mapa en tira_row. Lo
; único que cambia es cuál de los dos ejes alterna dentro del bloque y cuánto
; avanza el puntero al pasar de uno al siguiente.
.proc build_row
.a16
.i16
    stz row_addr
    cpx mapa_ch
    bcc dentro
    rts                         ; más allá del borde de abajo
dentro:
    txa
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a                       ; cada fila de la pantalla mide 32 palabras
    clc
    adc f:FAR_VRAM_MAPA
    sta row_addr

    txa
    and #$0001
    asl a
    asl a                       ; 0 la mitad de arriba del bloque, 4 la de abajo
    sta tira_ofs
    txa
    lsr a
    sta temp                    ; la fila de bloques que entra

    ; El ancla apunta a la fila de bloques de arriba de la ventana; la que entra
    ; puede estar hasta catorce filas más abajo, si es la del pie de la pantalla.
    jsr ptr_desde_celdas
    lda temp
    sec
    sbc win_block
    beq en_la_fila
    tax
baja:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne baja
en_la_fila:
    ; La fila arranca MARGEN_COLS columnas antes de la ventana, que es el mismo
    ; rango que cargan `fill_window` y `stream_map`: [win_col - MARGEN_COLS,
    ; win_col + 60). Si arrancara en win_col, las cuatro últimas columnas de la
    ; fila —win_col + 60 a 63— pisarían en el toro las ranuras del margen de la
    ; izquierda, y eso se vio: la esquina de la pantalla del mapa 2 mostraba
    ; columnas de 64 más adelante. Las columnas negativas y las que caen más
    ; allá del borde derecho van vacías, como en `build_column`.
    lda win_col
    sec
    sbc #MARGEN_COLS
    sta fila_col
    and #(WINDOW_COLS - 1)
    asl a
    tax                         ; la ranura de la primera columna, en bytes
    lda #WINDOW_COLS
    sta tira_total
vacias_izq:
    lda fila_col
    bpl con_mapa
    stz tira_row, x
    stz tira_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    inc fila_col
    dec tira_total
    bra vacias_izq
con_mapa:
    lda fila_col
    and #$0001
    beq desde_izquierda
    lda tira_ofs
    ora #$0002
    sta tira_ofs
desde_izquierda:
    lda fila_col
    lsr a
    asl a                       ; la columna de bloques de la izquierda, en bytes
    jsr ptr_mas
    lda mapa_cw
    sec
    sbc fila_col
    cmp tira_total
    bcc corta
    lda tira_total
corta:
    sta tira_resta
    lda tira_resta
    beq vacias_der              ; toda la fila cae fuera del mapa
columna:
    lda [celdas_ptr]
    jsr celda_sustituida
    asl a
    asl a
    asl a
    asl a
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_row, x
    lda [bloques8_ptr], y
    sta tira_row2, x

    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax

    lda tira_ofs
    eor #$0002                  ; la otra mitad del bloque, ahora a lo ancho
    sta tira_ofs
    and #$0002
    bne mismo
    lda #2
    jsr ptr_mas                 ; al bloque de al lado
mismo:
    dec tira_total
    dec tira_resta
    bne columna
vacias_der:
    lda tira_total
    beq listo
    stz tira_row, x
    stz tira_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    dec tira_total
    bra vacias_der
listo:
    rts
.endproc

; Qué hay que redibujar este cuadro: las filas y las columnas que la cámara
; acaba de destapar.
;
; **Son hasta dos de cada eje por vuelta, y eso está medido.** En el mismo eje
; se suman dos cosas: el héroe a velocidad 6 camina 8 px por cuadro
; —`paso_medio_por_vel` llega a 64 octavos— y un `PanScreen` a velocidad 6
; corre la cámara otros 8 —`2 << 6` dieciseisavos—. Dieciséis pixeles son dos
; celdas de 8. El salto del héroe no llega: el más largo del juego es de cinco
; celdas en once cuadros, 7,3 px por cuadro.
;
; Hasta el 2026-09-22 esto dibujaba **una sola** y anotaba `win_row` como si
; hubiera dibujado todas las que la cámara saltó, con un comentario que decía
; que la cámara no se movía más de dos pixeles. La fila salteada quedaba mal
; **para siempre**, porque la ventana es un toro y nadie vuelve a pisar esa
; ranura hasta 32 filas después: el mapa se veía corrido una o dos celdas
; respecto de la colisión, y cualquier teletransporte lo arreglaba porque
; rellena la ventana entera. taro lo encontró jugando, después de la cinemática
; de los Neon Vipers.
;
; Y si la cámara llegara a saltar más de dos —hoy no pasa—, `win_row` **se
; queda atrás** en vez de mentir: lo que falta se dibuja en las vueltas
; siguientes y el desfase se cura solo. Lo que se ve mientras tanto es el borde
; de la pantalla atrasado, que dura lo que dure el salto y no para siempre.
.proc stream_map
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    stz col_addr_b
    stz row_addr_b
    ; Dos llamadas y no un lazo con contador: `build_row` y `build_column` usan
    ; Y para leer los bloques, así que el contador tendría que vivir en la RAM,
    ; y "dos por vuelta" se lee mejor acá que en una constante.
    jsr una_fila
    jsr una_fila
    jsr una_columna
    jsr una_columna
    ; Lo que dejó pendiente una `TileSubstitution`: una columna de la ventana,
    ; y sólo si la cámara no se llevó ninguna de este cuadro —las dos
    ; direcciones en cero es que no hay ninguna armada—. Ver `sub_refresco`.
    lda sub_refresco
    beq sin_refresco
    lda col_addr
    ora col_addr_b
    bne sin_refresco
    dec sub_refresco
    lda win_col
    sec
    sbc #MARGEN_COLS            ; el mismo rango que arma `fill_window`
    clc
    adc sub_refresco
    tax
    jsr build_column
sin_refresco:
    sep #$20
.a8
    rts
.endproc

; Una fila más, si la cámara dejó alguna sin dibujar. `win_col` y `win_row`
; avanzan **de a una** aunque la cámara haya saltado más: así el ancla de
; bloques de `build_row` sigue valiendo paso a paso, y lo que no se alcanzó a
; dibujar queda pendiente en vez de perderse.
.proc una_fila
.a16
.i16
    lda camara_y
    lsr a
    lsr a
    lsr a
    cmp win_row
    beq listo
    ; El `jsr` va **después** del `bcs` y en las dos ramas: puesto antes, la
    ; rama miraría un acarreo que pasó por una llamada. Es barato no tener que
    ; demostrar que `guardar_fila` no lo toca.
    bcs bajando
    jsr guardar_fila            ; la tira de antes, si hay, al repuesto
    lda win_row
    dec a
    sta win_row
    tax                         ; sube: entra la fila de arriba de la pantalla
    bra con_fila
bajando:
    jsr guardar_fila
    lda win_row
    inc a
    sta win_row
    clc
    adc #(VIEW_ROWS - 1)
    tax                         ; baja: entra la del pie
con_fila:
    ; El ancla de bloques sigue a la fila de arriba de la ventana.
    phx
    lda win_row
    lsr a
    cmp win_block
    beq mismo_bloque
    pha
    bcs baja_bloque
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_menos
    jsr ptr_a_celdas
    bra guarda_bloque
baja_bloque:
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_mas
    jsr ptr_a_celdas
guarda_bloque:
    pla
    sta win_block
mismo_bloque:
    plx
    jsr build_row               ; X es la fila que entra
listo:
    rts
.endproc

; La imagen espejada, para el otro eje.
.proc una_columna
.a16
.i16
    lda camara_x
    lsr a
    lsr a
    lsr a
    cmp win_col
    beq listo
    bcs derecha                 ; el `jsr` después del salto: ver `una_fila`
    jsr guardar_columna
    lda win_col
    dec a
    sta win_col
    sec
    sbc #MARGEN_COLS            ; sube: entra la del margen de la izquierda
    tax
    bra armar
derecha:
    jsr guardar_columna
    lda win_col
    inc a
    sta win_col
    clc
    adc #(VIEW_COLS - 1 + MARGEN_COLS)
    tax
armar:
    jsr build_column
listo:
    rts
.endproc

; La tira de fila que quedó armada, al repuesto de la RAM lejana, para que
; `build_row` pueda volver a usar el buffer en esta misma vuelta.
;
; Se copia en vez de tener dos juegos de tiras y que `build_row` elija: el lazo
; de `build_row` escribe con `sta tira_row, x` y `stz tira_row, x`, y `stz` no
; tiene modo largo indexado, así que mudarlas a la RAM lejana le costaría un
; `lda #0` por celda en el lazo caliente. El `mvn` son 256 bytes a siete ciclos
; y se paga **sólo** cuando la cámara saltó dos filas, que es raro.
.proc guardar_fila
.a16
.i16
    lda row_addr
    beq listo                   ; no hay ninguna armada
    sta row_addr_b
    ; Las dos tiras de la fila son contiguas —ver su `.res`—, así que van en un
    ; solo `mvn`, que copia A + 1 bytes y deja el banco de datos en el destino.
    ldx #.loword(tira_row)
    ldy #.loword(FAR_TIRA_ROW)
    lda #(WINDOW_COLS * 2 * 2 - 1)
    phb
    mvn #$00, #^FAR_TIRA_ROW    ; la BSS se ve desde el banco 0: es el espejo
    plb                         ; de la WRAM de abajo del $2000
    stz row_addr                ; el buffer queda libre
listo:
    rts
.endproc

.proc guardar_columna
.a16
.i16
    lda col_addr
    beq listo
    sta col_addr_b
    ldx #.loword(tira_col)
    ldy #.loword(FAR_TIRA_COL)
    lda #(WINDOW_ROWS * 2 * 2 - 1)
    phb
    mvn #$00, #^FAR_TIRA_COL
    plb
    stz col_addr
listo:
    rts
.endproc

; Llena la ventana entera desde cero: las 64 columnas, una por una. Va con la
; pantalla apagada, al arrancar, y es el único momento en que se escribe tanto
; tilemap de una vez.
; Los dos tilemaps del mapa —el fondo y la capa de encima— en cero, y las
; cuatro tiras con que se llenan.
;
; `build_column` y `build_row` **saltean** lo que cae afuera del mapa, y las
; tiras sólo se escriben hasta donde el mapa llega. En el arranque eso deja
; ceros, que es la celda vacía y se ve negro, porque el reset limpió la VRAM
; entera. Después de un teletransporte o de una puerta, en cambio, dejaba lo
; que hubiera puesto el mapa anterior: lo destapa `ShakeScreen` contra el
; borde, que corre la pantalla más allá de la primera columna. Lo encontró el
; paso 9e, cuando los casos de `sacudir-borde` y `tram-viaje` pasaron a
; llegar a su mapa con un `Teleport` en vez de arrancar ahí.
;
; Corre con la pantalla en blanking forzado, que es como corre toda carga de
; mapa: son dos DMA de 4 KB a la VRAM.
.proc limpiar_tilemaps
.a8
.i16
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda f:FAR_VRAM_MAPA
    tax
    sep #$20
.a8
    jsr cero_a_tilemap
    ldx #VRAM_ABOVE_MAP
    jsr cero_a_tilemap
    ldx #$0000
tiras:
    stz tira_col, x             ; las cuatro son contiguas: ver su .res
    inx
    cpx #(WINDOW_ROWS * 2 * 2 + WINDOW_COLS * 2 * 2)
    bne tiras
    rts
.endproc

; Un tilemap de dos pantallas de 32x32, desde la palabra X de la VRAM, en cero.
.proc cero_a_tilemap
.a8
.i16
    stx VMADDL
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #(32 * 32 * 2 * 2)      ; dos pantallas, de a palabras
    stx DAS0L
    lda #$09                    ; dos registros, de a palabras, fuente fija
    sta DMAP0
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

.proc fill_window
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    stz col_addr_b              ; y las de repuesto: acá se llena todo de cero,
    stz row_addr_b              ; así que lo que quedara a medio armar no sirve
    lda mapa_ancho
    asl a
    sta tira_paso_col           ; lo que mide una fila de bloques, en bytes

    lda camara_x
    lsr a
    lsr a
    lsr a
    sta win_col
    lda camara_y
    lsr a
    lsr a
    lsr a
    sta win_row
    lsr a
    sta win_block

    ; celdas = la grilla del mapa + win_block filas. Se suma de a una en vez de
    ; multiplicar: pasa una sola vez y el 65816 no multiplica.
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_MAP_CELDAS, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_CELDAS + 2, x
    sta celdas_ptr + 2
    rep #$20
.a16
    ldx win_block
    beq sin_filas
suma:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne suma
sin_filas:
    jsr ptr_a_celdas

    lda win_col
    sec
    sbc #MARGEN_COLS            ; con el margen de la izquierda; las columnas
    sta temp + 2                ; negativas las saltea `build_column`
    ldy #WINDOW_COLS
columna:
    phy
    ldx temp + 2
    jsr build_column
    sep #$20
.a8
    jsr push_strips
    rep #$20
.a16
    inc temp + 2
    ply
    dey
    bne columna
    sep #$20
.a8
    rts
.endproc

; `hdma_mascara` y `tabla_fila_buf` **vivían acá** y bajaron a RODATA el
; 2026-09-13, las dos por separado y el mismo día: ver `banco1.s`. El HDMA lee
; de donde diga `A1B3`, así que no necesita banco 0, y el compositor la indexa
; con X, que sí tiene modo largo.

