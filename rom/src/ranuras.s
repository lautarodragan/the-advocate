.segment "CODE"

; --- la pantalla de ranuras ------------------------------------------------
;
; La usan las dos puntas: "Resume the Story" en el título, y el save point de
; Lashe City. Es una pantalla propia y no una capa encima del título, así que
; **comparte la VRAM del menú**: cuando una se ve la otra no, y las dos se
; suben enteras cada vez que se entra.
;
; Todo el texto viene pre-renderizado del conversor, incluidas las dos
; variantes de cada ranura —vacía y llena—. Lo único que se decide en caliente
; es qué bloque de celdas le toca a cada fila, y **de qué bloque se trata lo
; dice una tabla de punteros**, no una multiplicación: calcular el
; desplazamiento con corrimientos habría puesto la misma cuenta acá y en el
; conversor, que es la forma de error que este repo ya pagó tres veces.
;
; Mover el cursor reescribe **dos filas** de 96 celdas, no el tilemap entero.

; Si la ranura que viene en A tiene una partida. Devuelve A distinto de cero, y
; **se lleva `ranura`**: `ranuras_pantalla` la guarda al entrar y la repone al
; salir.
;
; Mira sólo la magia y no la suma: es para pintar la lista, y recorrer los 159
; bytes de cada ranura para dibujar una pantalla sería pagar de más. La suma la
; comprueba `cargar_partida` cuando el jugador elige, que es donde importa.
.proc ranura_llena
.a8
.i16
    jsr poner_ranura
    jsr ranura_en_x             ; con el banco de datos todavía normal
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_MAGIA, x
    cmp #$41
    bne no
    lda SRAM_MAGIA + 1, x
    cmp #$42
    bne no
    lda SRAM_MAGIA + 2, x
    cmp #$4C
    bne no
    lda SRAM_MAGIA + 3, x
    cmp #$53
    bne no
    plb
    lda #$01
    rts
no:
    plb
    lda #$00
    rts
.endproc

; Sube un bloque de celdas al tilemap. X trae el índice del bloque en
; `ranura_bloque_lo/hi/bk`, Y la dirección de VRAM en palabras y `temp` cuántas
; celdas son.
;
; Con la pantalla apagada al entrar y adentro del vblank al mover el cursor:
; 192 bytes por DMA entran de sobra en un vblank que no tiene nada más que
; hacer.
.proc ranura_bloque_subir
.a8
.i16
    sty VMADDL
    lda #$80
    sta VMAIN
    lda ranura_bloque_lo, x
    sta A1T0L
    lda ranura_bloque_hi, x
    sta A1T0L + 1
    lda ranura_bloque_bk, x
    sta A1B0
    rep #$20
.a16
    lda temp
    asl a                       ; celdas a bytes
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Pinta la fila de la ranura que viene en A: con cursor si `titulo_sel` la
; señala, y llena si la SRAM dice que lo está.
;
; El estado de llenado se vuelve a preguntar en cada repintado en vez de
; guardarse: son cuatro bytes de la SRAM y pasa sólo cuando el cursor se mueve.
; Guardarlo pediría RAM que no hay —ver `ranura`— y una forma de invalidarlo
; después de guardar.
.proc ranura_pintar
.a8
.i16
    pha
    jsr ranura_llena
    asl a                       ; llena vale 2 en el índice de variante
    sta temp + 2
    pla
    pha
    cmp titulo_sel
    bne sin_cursor
    inc temp + 2                ; y el cursor, 1
sin_cursor:
    ; El índice del bloque: las dos cabeceras primero, y después cuatro
    ; variantes por ranura.
    pla
    pha
    asl a
    asl a
    clc
    adc temp + 2
    clc
    adc #RANURA_BLOQUE_FILAS
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; Y a dónde va, que lo dice la tabla y no una cuenta.
    pla
    pha                         ; la ranura, para el grupo de después
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por entrada
    tay
    lda ranura_vram, y
    tay
    lda #RANURA_CELDAS
    sta temp
    sep #$20
.a8
    jsr ranura_bloque_subir
    ; Y encima de la fila, si tiene partida, el nombre del líder y las caras
    ; del grupo que guardó. `temp + 2` quedó con la variante: llena vale 2 o 3.
    pla
    lda temp + 2
    cmp #2
    bcc sin_grupo
    jmp ranura_grupo_pintar
sin_grupo:
    rts
.endproc

; Sube un rectángulo de celdas al tilemap, fila por fila. X trae el índice del
; bloque en `ranura_bloque_lo/hi/bk`, Y la dirección de VRAM de su primera
; celda, `temp` cuántos bytes tiene cada fila y `temp + 2` cuántas filas son.
;
; **`temp` es un byte**, y el alto del DMA se pone en cero acá: una fila del
; tilemap son 32 celdas, 64 bytes. Hasta el 2026-09-21 se leía de a dieciséis
; bits, y los dos llamadores de `menu_grupo_pintar` le escriben sólo el bajo:
; el alto quedaba con lo que hubiera, que viniendo de la pantalla de ítems es
; la variante de su última letra —`temp + 1`, 1 si es gris—. Con un ítem en
; gris al final de la lista, la primera fila del panel subía 256 bytes de más
; encima del tilemap: es el "se rompen los gráficos al volver a entrar" de
; taro. Lo cobra `test_la_eleccion_se_ve_igual_al_volver_a_entrar`.
;
; Un solo puntero de origen para todas las filas: el DMA deja `A1T0` apuntando
; a donde terminó, así que la fila siguiente arranca de ahí sin volver a
; cargarlo. Lo que cambia por fila es el destino, que baja 32 celdas.
.proc ranura_rect_subir
.a8
.i16
    lda #$80
    sta VMAIN
    lda ranura_bloque_lo, x
    sta A1T0L
    lda ranura_bloque_hi, x
    sta A1T0L + 1
    lda ranura_bloque_bk, x
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
fila:
    sty VMADDL
    lda temp
    sta DAS0L
    stz DAS0L + 1
    rep #$20
.a16
    tya
    clc
    adc #32
    tay
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    dec temp + 2
    bne fila
    rts
.endproc

; --- el texto que depende del actor -----------------------------------------
;
; El nombre, el nivel y los HP máximos **no vienen horneados** en un bloque de
; celdas por actor: se componen de a una letra por celda, con los glifos de
; `ranura_glifo_celdas`. El porqué está en "lo que depende del actor" de
; titulo.py y es el mismo que ya vale para el oro y para la pantalla de
; ítems: el banco de tiles es uno solo y está deduplicado, así que un bloque
; por actor lo hacía crecer con cada uno que pudiera estar en el grupo.

; `msg_ptr` apuntando a una de las tiras del actor que trae A, corrida los X
; bytes de `RANURA_TEXTO_NOMBRE`, `_NIVEL` o `_MAX`. Se lleva A y X, y **Y
; queda como estaba**: el que llama la trae con la celda donde va a escribir.
;
; Usa `msg_ptr` de puntero por lo mismo que la pantalla de ítems: ninguna de
; estas pantallas se abre con un mensaje en pantalla, así que el compositor no
; lo tiene ocupado. Y tiene que ser él o alguno de la página directa, porque
; `lda [dp], y` sólo direcciona ahí.
.proc ranura_texto_de
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; RANURA_TEXTO_ANCHO bytes por actor
    sta msg_ptr
    txa
    clc
    adc msg_ptr
    clc
    adc #.loword(ranura_actor_texto)
    sta msg_ptr
    sep #$20
.a8
    lda #^ranura_actor_texto
    sta msg_ptr + 2
    rts
.endproc

; Un texto del banco de las ranuras, de a una letra por celda: `msg_ptr` la
; primera letra, Y la celda de arriba de la primera y A cuántas letras. Se
; lleva A, X, `temp` y `temp + 2`, y **deja Y como estaba**: el que llama
; escribe varias tiras de la misma fila corriéndola.
;
; Primero las celdas de arriba de todas las letras, que van seguidas en la
; VRAM y aprovechan el autoincremento, y después las de abajo. Es
; `texto_escribir` de la pantalla de ítems con la otra tabla de glifos: son
; dos bancos distintos y cada uno tiene el suyo.
.proc ranura_texto_escribir
.a8
.i16
    sta temp                    ; cuántas letras
    lda #$80
    sta VMAIN
    phy                         ; la celda, para la segunda pasada
    rep #$20
.a16
    lda #0
    sta temp + 2                ; las celdas de arriba
    sty VMADDL
    sep #$20
.a8
    jsr renglon
    rep #$20
.a16
    lda 1, s                    ; la misma celda, que `renglon` se llevó Y
    clc
    adc #32                     ; y las de abajo, una fila más abajo
    sta VMADDL
    lda #2
    sta temp + 2
    sep #$20
.a8
    jsr renglon
    ply
    rts

renglon:
    ldy #0
letra:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; cuatro bytes por glifo
    clc
    adc temp + 2                ; la celda de arriba o la de abajo
    tax
    lda f:ranura_glifo_celdas, x
    sta VMDATAL                 ; y la VRAM avanza una palabra
    sep #$20
.a8
    iny
    tya                         ; de a una letra: son menos de 256
    cmp temp
    bcc letra
    rts
.endproc

; El grupo de la partida de la ranura que está en `ranura`: las caras de los
; primeros RANURA_CARAS_MAX, y el nombre del primero. Es lo que
; `Window_SaveFile::Refresh` dibuja por archivo, menos los puntos de vida, que
; este port no tiene.
;
; El grupo se lee de la SRAM de la ranura, con el banco de datos en $70 el
; tiempo justo de leer un byte: las tablas de bloques y los registros del DMA
; direccionan el banco 0. Un actor sin cara —DummyHero— no dibuja nada, que es
; lo que hace `DrawFace` con un nombre vacío. Y a dónde va cada cara y cada
; nombre lo dicen dos tablas del conversor, `ranura_cara_vram` y
; `ranura_nombre_vram`, como `ranura_vram` para las filas: la cuenta vive en
; un solo lado.
;
; La cara es un bloque horneado y el nombre y el nivel **no**: ésos se
; componen con glifos, ver `ranura_texto_escribir`.
;
; El escritorio, que está justo: `temp` y `temp + 2` son del rectángulo,
; `temp + 3` guarda cuántos son, y **`titulo_flancos` hace de índice de
; miembro**. En la página directa no hay otro byte, y los flancos ya se miraron
; cuando se llega acá.
.proc ranura_grupo_pintar
.a8
.i16
    jsr ranura_en_x
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_DATOS + PARTIDA_GRUPO_N, x
    plb
    cmp #RANURA_CARAS_MAX
    bcc caben
    lda #RANURA_CARAS_MAX
caben:
    sta temp + 3
    stz titulo_flancos
otro_miembro:
    lda titulo_flancos
    cmp temp + 3
    bcs las_caras_listas
    jsr actor_del_miembro
    cmp #RANURA_ACTORES_N
    bcs siguiente               ; un actor que esta ROM no conoce
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ranura_cara_bloque, x
    cmp #$FF
    beq siguiente               ; sin cara
    pha                         ; el bloque, mientras se arma el destino
    ; La tabla va de a cuatro por ranura: la ranura por cuatro más el lugar.
    lda ranura
    asl a
    asl a
    ora titulo_flancos
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por entrada
    tax
    lda ranura_cara_vram, x
    tay
    lda #(RANURA_CARA_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #RANURA_CARA_FILAS
    sta temp + 2
    pla
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr ranura_rect_subir
siguiente:
    inc titulo_flancos
    bra otro_miembro
las_caras_listas:
    ; El nombre del líder, que es el primero, y su nivel: los dos compuestos
    ; con glifos encima de la fila. `temp + 3` ya no hace falta, así que
    ; `ranura_texto_escribir` puede usar `temp`.
    lda temp + 3
    beq listo                   ; un grupo vacío no tiene líder
    stz titulo_flancos
    jsr actor_del_miembro
    cmp #RANURA_ACTORES_N
    bcs listo                   ; un actor que esta ROM no conoce
    pha                         ; el actor, para las dos tiras
    lda ranura
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda ranura_nombre_vram, x
    tay                         ; la celda del nombre
    sep #$20
.a8
    pla
    pha
    ldx #RANURA_TEXTO_NOMBRE
    jsr ranura_texto_de
    lda #RANURA_NOMBRE_COLS
    jsr ranura_texto_escribir
    ; Y el nivel, que cae unas celdas más abajo de la misma fila. Y quedó
    ; donde estaba: `ranura_texto_escribir` la conserva.
    rep #$20
.a16
    tya
    clc
    adc #RANURA_NIVEL_DESPL
    tay
    sep #$20
.a8
    pla
    jsl f:texto_nivel_guardado  ; el de la partida de la ranura, no el de ahora
    lda #RANURA_NIVEL_CIFRAS
    jsr ranura_texto_escribir
listo:
    rts

; El actor que está en el lugar `titulo_flancos` del grupo de la ranura, leído
; de la SRAM. Devuelve A y se lleva X. El desplazamiento es la ranura por 1024
; —`SRAM_STRIDE`— más el lugar, armado con dos `xba` y sin tocar los vecinos
; de la página directa: leer `titulo_flancos` a dieciséis bits se llevaría
; `menu_abierto`. El byte alto es la ranura por cuatro, que entra: son cuatro
; ranuras.
actor_del_miembro:
    lda titulo_flancos
    xba
    lda ranura
    asl a
    asl a
    asl a
    xba                         ; C = ranura * 2048 + lugar
    rep #$20
.a16
    tax
    sep #$20
.a8
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_DATOS + PARTIDA_GRUPO, x
    plb
    rts
.endproc

; La pantalla entera: la sube, la muestra y la maneja hasta que el jugador
; elija o cancele. A trae el modo —0 cargar, 1 guardar— y vuelve con la ranura
; elegida, o **$FF si canceló con B**.
;
; Deja la VRAM y CGRAM pisadas, así que el llamador repone lo suyo: el título
; vuelve a subir su imagen y su menú, y el save point recarga el mapa. Es lo
; mismo que hace `pantalla_titulo` al salir, y por la misma razón: mientras esta
; pantalla se ve no hay ni mapa ni título que preservar.
.proc ranuras_pantalla
.a8
.i16
    ; El banco de datos, al 0. **Desde el título ya lo es; desde el save point
    ; no tiene por qué**: el intérprete corre con el banco puesto donde vive el
    ; bytecode del evento. Y todo lo de acá abajo escribe los registros del PPU
    ; y del DMA con direccionamiento absoluto, que usa el banco de datos, así
    ; que con el banco corrido la pantalla se dibujaba en negro con basura
    ; arriba.
    phb
    phk
    plb
    ; Y el tamaño de los registros, explícito. Desde el título se llega con A
    ; de ocho bits y X/Y de dieciséis; **desde el intérprete no hay tal
    ; promesa**, y una `lda #$80` interpretada como de dieciséis bits se come el
    ; byte siguiente y descoloca todo lo que sigue.
    sep #$20
    rep #$10
    pha                         ; el modo, hasta que se dibuje la cabecera
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM                      ; nada a la vista mientras se arma

    jsr ranura_banco_subir

    ; --- la cabecera, según el modo ---
    pla
    pha                         ; el modo, otra vez: decide dónde arranca el cursor
    rep #$20
.a16
    and #$00FF
    tax                         ; los dos primeros bloques son las cabeceras
    lda #RANURA_CAB_CELDAS
    sta temp
    ldy #(RANURA_MAP + RANURA_CAB_VRAM)
    sep #$20
.a8
    jsr ranura_bloque_subir

    ; --- dónde arranca el cursor ---
    ; Cargando, en la primera. Guardando, en la ranura que se está usando —de
    ; la que se cargó, o en la que se guardó la última vez—: es el
    ; `index = latest_slot` de `Scene_File::Start`, que allá es la de fecha más
    ; nueva y acá, sin fechas, la que está en uso. Sin partida cargada, la
    ; primera.
    pla
    beq primera
    lda ranura
    cmp #$FF
    bne arranca_ahi
primera:
    lda #0
arranca_ahi:
    sta titulo_sel

    ; `ranura` a la pila. Pintar una fila la pisa —`ranura_llena` la escribe
    ; para direccionar la SRAM— y al salir tiene que valer lo que valía, elija
    ; el jugador o cancele: quien elige la pone después con `poner_ranura`.
    ; Desde el título daba lo mismo porque valía $FF y se ponía al elegir;
    ; desde el save point, cancelar dejaría a la partida "cargada" de la última
    ; fila pintada.
    lda ranura
    pha

    ; --- y las cuatro filas ---
    lda #0
pintar_todas:
    pha
    jsr ranura_pintar
    pla
    inc a
    cmp #SRAM_RANURAS_N
    bcc pintar_todas

    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto

espera:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube
    lda #SRAM_RANURAS_N         ; desde la primera, arriba da la vuelta
sube:
    dec a
    jsr mover_cursor
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #SRAM_RANURAS_N
    bcc baja
    lda #0
baja:
    jsr mover_cursor
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    jsr cerrar
    lda #$FF                    ; cancelar
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    jsr cerrar
    lda titulo_sel
    rts

; Lo que las dos salidas tienen en común: `ranura` como estaba, el banco de
; datos como estaba, el testigo abajo. Y `nmi_visto` al día, para que
; `contar_perdidos` no cuente como perdidos los cuadros que el jugador pasó
; eligiendo: desde el save point esto corre adentro de una vuelta del lazo, y
; sin esto la vuelta mediría cientos de cuadros y saturaría el contador.
;
; La pila trae, de arriba abajo: la dirección de vuelta de este `jsr`, `ranura`
; y el banco. Se saca la de vuelta primero para llegar a los otros dos.
cerrar:
    plx                         ; la dirección de vuelta, aparte
    pla
    sta ranura
    plb
    phx
    ; Y los flancos de B y de A, consumidos: el que cerró la pantalla es de
    ; ella. Sin esto, desde el save point, el B de cancelar le llegaba a
    ; `pedir_menu` en la misma vuelta —si la página terminaba ahí— y abría el
    ; menú de pausa; y el A de elegir podía hablarle a un evento.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    rts

; El cursor a la ranura que trae A: se repintan **las dos filas que cambian** y
; ninguna más. Adentro del vblank, que es donde estamos al salir de
; `wait_vblank`.
mover_cursor:
    sta temp + 3                ; la nueva
    lda titulo_sel
    pha                         ; y la vieja, a la pila
    lda temp + 3
    sta titulo_sel
    pla
    jsr ranura_pintar           ; se despinta el cursor de donde estaba
    lda titulo_sel
    jmp ranura_pintar           ; y se pinta donde va
.endproc

; Sube el banco de tiles de la pantalla de ranuras y del menú, deja el tilemap
; en blanco y sube sus colores. Con la pantalla apagada. Salió de
; `ranuras_pantalla` el día que el menú de pausa empezó a usar el mismo banco.
.proc ranura_banco_subir
.a8
.i16
    ; --- los tiles ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(RANURA_TILES * 32)
    sta DAS0L
    lda #<(ranura_tiles)
    ora #(>(ranura_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; --- el tilemap, en blanco ---
    ; Un DMA con la dirección de origen **fija** —el bit 3 de DMAP— repitiendo
    ; una palabra en cero. El origen es el primer tile del banco, que es el
    ; transparente y por lo tanto son 32 bytes de cero: no hace falta un bloque
    ; aparte para tener dos ceros a mano.
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(ranura_tiles)
    ora #(>(ranura_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_tiles)
    sta A1B0
    lda #$09                    ; dos registros, sin avanzar el origen
    sta DMAP0
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    ; La paleta 0 del texto y una por cara: RANURA_CGRAM_N entradas, seguidas.
    stz CGADD
    rep #$20
.a16
    lda #(RANURA_CGRAM_N * 2)
    sta DAS0L
    lda #<(ranura_cgram)
    ora #(>(ranura_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    rts
.endproc

; BG2 con el tilemap de la pantalla de ranuras, y la pantalla prendida.
.proc ranura_ppu_prender
.a8
.i16
    ; --- el PPU ---
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(RANURA_VRAM / 4096 * 16)
    sta BG12NBA                 ; sólo BG2; BG1 no se dibuja
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    lda #$02
    sta TM
    lda #$0F
    sta INIDISP
    rts
.endproc

