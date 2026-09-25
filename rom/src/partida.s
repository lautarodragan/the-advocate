; --- guardar y cargar la partida -------------------------------------------
;
; El cartucho lleva SRAM con batería, con las ranuras de `SRAM_RANURAS`.
;
; Qué se guarda lo dice `partida_tabla` y nada más: pares de (dirección en la
; WRAM del banco 0, cuántos bytes), terminados en un largo cero. Tenerlo en una
; tabla y no en código es lo que hace que guardar y cargar no se puedan ir uno
; del otro —los dos la recorren— y que agregar un campo sea una línea.
;
; La copia va por DMA en las dos direcciones, y la ventana de la WRAM es la que
; lo hace posible: el bus B no llega a la SRAM, pero sí a `WMDATA`, así que la
; SRAM va del lado del bus A y la WRAM del otro. Guardar es un DMA de B a A —el
; bit 7 de DMAP— y cargar el mismo al revés.
;
; La partida arranca en $0100 y no en $0000 por el ensamblador: `ca65` elige
; página directa cuando la dirección entra en un byte, así que
; con la partida en $0000 un `lda SRAM_MAGIA, x` leería la página directa en vez
; de la SRAM. Los 256 bytes que quedan abajo no los usa nadie.
SRAM_BANCO = $70            ; en LoROM la SRAM se ve desde $70:0000

; **Cuatro ranuras**, que es lo que pidió taro: RM2k abre un menú de quince y
; para este juego no tiene sentido. En la SRAM entrarían muchas más —son 8 KB y
; una ranura ocupa 165 bytes— así que el número no sale de acá sino de cuántas
; se pueden mostrar y elegir sin que la pantalla se vuelva una lista.
SRAM_RANURAS = 4

; Cada ranura arranca en un múltiplo de 256, que es lo que hace que su
; desplazamiento sea la ranura por 256 —un `xba`— y no una multiplicación. Se
; pagan 91 bytes de relleno por ranura y sobra SRAM de todas formas: cuatro
; ranuras terminan en $0500 de los $2000 que hay.
;
; **Si `PARTIDA_BYTES` pasara de 250, esto se rompe en silencio**: la ranura
; siguiente empieza a pisar el final de la anterior. Hoy son 159, y crecen cada
; vez que se agrega un campo a la partida —ya pasó con la música—. El
; ensamblador no lo puede cortar, así que lo cuida
; `pruebas/rpgmaker/test_guardar.py::test_las_cuatro_ranuras_entran_en_la_sram`.
SRAM_STRIDE = 2048

; Y dentro de cada ranura, contando desde su base. `SRAM_MAGIA` sigue siendo
; $0100 y no $0000 por lo de siempre: un operando que entra en un byte lo
; resuelve el ensamblador como página directa y leería la WRAM. Ese error costó
; que la partida no cargara en mednafen, en Mesen ni en la consola.
SRAM_MAGIA = $0100          ; cuatro bytes: "ABLS", $41 $42 $4C $53
SRAM_SUMA  = $0104          ; la suma de los bytes de la partida
SRAM_DATOS = $0106

; `partida_tabla` vive en RODATA —ver "lo que no hace falta que viva en el
; banco 0"— y se lee con `lda f:partida_tabla, x`.
; Los mismos largos, sumados, para poder recorrer la partida en la SRAM sin
; volver a mirar la tabla. Está duplicado a propósito y **la ROM lo comprueba**:
; `guardar_partida` compara con lo que le quedó a `partida_copiar` y si no dan
; iguales entra en pánico. Duplicar un número que nadie verifica es la forma de
; error que este repo ya pagó tres veces.
PARTIDA_BYTES = 2 + 2 + 1 + 2 + 2 + 2 + 6 + 3 + 1 + 5 + 3 + SWITCH_BYTES + 1 + 2 + VARIABLES_N * 2 + 1 + ITEMS_N + 1 + ACTORES_N * 10 + ACTORES_N * 2 + ACTORES_N * 2 + ACTORES_N + HAB_BYTES + EXP_K * 4
; Dónde cae el grupo adentro de la partida: después de la posición, la
; dirección, la celda y el mapa. Lo lee la pantalla de ranuras desde la SRAM
; para poner el nombre del líder y las caras. Es la misma suma que arriba,
; cortada en el sexto renglón de la tabla; si `partida_tabla` cambia de orden,
; esto cambia con ella.
PARTIDA_GRUPO   = 2 + 2 + 1 + 2 + 2 + 2   ; el mapa ocupa dos desde que su
                                          ; índice es de dieciséis bits
PARTIDA_GRUPO_N = PARTIDA_GRUPO + 4

; Pone la ranura con la que van a trabajar `guardar_partida` y `cargar_partida`,
; y calcula su desplazamiento. A trae el número de ranura.
;
; El desplazamiento es la ranura por 2048, o sea un `xba` y tres `asl`: de ahí
; sale que `SRAM_STRIDE` valga 2048 y no el largo justo de una partida.
; Multiplicar por ese largo pediría el multiplicador del hardware y ocho
; ciclos de espera, para ahorrar unos bytes de una SRAM que sobra. Era 256
; hasta que las 81 variables del juego entraron en la partida, 512 hasta el
; inventario y 1024 hasta el equipo, que son 610 bytes más. Con 2048 cuatro
; ranuras no entran en 8 KB, y el cartucho declara 32 KB, que en LoROM es un
; banco entero de SRAM en $70.
.proc poner_ranura
.a8
.i16
    sta ranura
    rts
.endproc

; El desplazamiento de la ranura en la SRAM, en X. **Pide el banco de datos
; normal**: lee `ranura`, que vive en la WRAM.
;
; Es la ranura por 2048, o sea un `xba` y tres `asl`: ver `poner_ranura`.
.proc ranura_en_x
.a8
.i16
    rep #$20
.a16
    lda ranura
    and #$00FF
    xba                         ; por 256...
    asl a
    asl a
    asl a                       ; ...y por ocho: SRAM_STRIDE, que es 2048
    tax
    sep #$20
.a8
    rts
.endproc

; Recorre `partida_tabla` copiando cada tramo. A trae el DMAP: $80 guarda —de la
; ventana de la WRAM a la SRAM— y $00 carga. Deja en `temp` dónde terminó la
; partida adentro de la SRAM.
.proc partida_copiar
.a8
.i16
    sta DMAP0
    lda #$80
    sta BBAD0                   ; el otro lado es siempre WMDATA
    lda #SRAM_BANCO
    sta A1B0
    ldx #$0000                  ; por dónde va la tabla
    phx
    jsr ranura_en_x             ; banco de datos normal: acá todavía lo es
    rep #$20
.a16
    txa
    clc
    adc #SRAM_DATOS
    sta temp                    ; y por dónde va la SRAM, dentro de su ranura
    sep #$20
.a8
    plx
    rep #$20
.a16
    sep #$20
.a8
otra:
    rep #$20
.a16
    lda f:partida_tabla + 2, x
    beq listo                   ; largo cero: se terminó la tabla
    sta DAS0L
    lda temp
    sta A1T0L
    clc
    adc DAS0L
    sta temp
    lda f:partida_tabla, x
    sta WMADDL                  ; la WRAM, que va siempre en el banco 0
    sep #$20
.a8
    stz WMADDH
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #4
    tax
    sep #$20
.a8
    bra otra
listo:
.a16
    sep #$20
.a8
    rts
.endproc

; La suma de los bytes de la partida que hay en la SRAM, en `temp + 2`. Pide el
; banco de datos ya puesto en la SRAM y **X con el desplazamiento de la
; ranura**: no lo lee de `ranura_ofs` porque con el banco en $70 eso leería la
; SRAM. Se lleva X.
;
; **El índice va desde cero y la dirección la pone la base.** Escrito al revés
; —`ldx #SRAM_DATOS` y después `lda $0000, x`— parece lo mismo y no lo es: el
; operando `$0000` entra en un byte, así que el ensamblador elige página
; directa igual que ca65, y el bucle terminaba sumando **la WRAM baja** en vez
; de la SRAM. Es exactamente la trampa que el comentario de `SRAM_MAGIA`
; advierte veinte líneas más arriba, cometida en la línea de al lado.
;
; Lo que lo mantuvo escondido es que el error es **simétrico**: guardar y
; cargar suman los dos la misma basura, así que mientras la WRAM no cambie
; entre una cosa y la otra los números coinciden y la partida carga. Eso pasa
; en el arranque de snes9x, que llena la RAM siempre con lo mismo y llama a
; `cargar_partida` a los microsegundos del reset. Con la WRAM de mednafen, de
; Mesen o de la consola de verdad, no coinciden y la partida no carga nunca;
; y desde el menú del título tampoco, porque para entonces la WRAM ya se movió.
; Tres reportes de taro y un `xfail` eran todos este bug.
.proc partida_suma
.a8
.i16
    rep #$20
.a16
    lda #$0000
    sta temp + 2
    sep #$20
.a8
    ldy #$0000                  ; X ya viene con el principio de su ranura
suma:
    lda SRAM_DATOS, x           ; la base no entra en un byte: absoluto, y el
                                ; banco de datos es la SRAM
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    inx
    iny                         ; X anda por la SRAM e Y cuenta: la ranura no
    cpy #PARTIDA_BYTES          ; arranca en cero y las dos cosas no son la misma
    bne suma
    rts
.endproc

; Guarda la partida. Es lo que hace `OP_SAVE`, o sea el `OpenSaveMenu` del
; save point de Lashe City.
.proc guardar_partida
.a8
.i16
    lda #$80                    ; de la ventana de la WRAM a la SRAM
    jsr partida_copiar
    ; Lo que se copió tiene que ser lo que `PARTIDA_BYTES` dice. Si no, la suma
    ; miraría otro tramo y la ranura quedaría inválida para siempre sin decir
    ; por qué.
    rep #$20
.a16
    sep #$20
.a8
    jsr ranura_en_x
    rep #$20
.a16
    txa
    clc
    adc #(SRAM_DATOS + PARTIDA_BYTES)
    cmp temp                    ; dónde tendría que haber terminado la copia
    sep #$20
.a8
    beq cuadra
    jmp entrar_en_panico
cuadra:
    ; La magia y la suma son lo que dice que la ranura vale. El banco de datos
    ; se muda a la SRAM: es la única forma de direccionarla sin un puntero en la
    ; página directa, que está llena.
    ;
    ; El desplazamiento de la ranura se lee **antes** de mudarlo, y de ahí en
    ; más viaja en X: con el banco en $70, `lda ranura_ofs` leería la SRAM.
    jsr ranura_en_x
    phb
    lda #SRAM_BANCO
    pha
    plb
    phx
    jsr partida_suma            ; se lleva X
    plx
    rep #$20
.a16
    lda temp + 2
    sta SRAM_SUMA, x
    sep #$20
.a8
    lda #$41
    sta SRAM_MAGIA, x
    lda #$42
    sta SRAM_MAGIA + 1, x
    lda #$4C
    sta SRAM_MAGIA + 2, x
    lda #$53
    sta SRAM_MAGIA + 3, x
    plb
    rts
.endproc

; Si la SRAM tiene una partida, la carga y devuelve A distinto de cero. Corre en
; el arranque, antes de cargar el mapa: los switches deciden qué página está
; activa en cada evento, así que tienen que estar puestos antes.
;
; La magia se compara contra inmediatos y no contra una tabla de la ROM porque
; con el banco de datos en la SRAM no hay cómo leer la ROM: el ensamblador no
; tiene direccionamiento largo y la página directa está llena.
.proc cargar_partida
.a8
.i16
    jsr ranura_en_x             ; antes de mudar el banco: ver `guardar_partida`
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_MAGIA, x
    cmp #$41
    bne no_hay
    lda SRAM_MAGIA + 1, x
    cmp #$42
    bne no_hay
    lda SRAM_MAGIA + 2, x
    cmp #$4C
    bne no_hay
    lda SRAM_MAGIA + 3, x
    cmp #$53
    bne no_hay
    phx
    jsr partida_suma            ; se lleva X
    plx
    rep #$20
.a16
    lda temp + 2
    cmp SRAM_SUMA, x
    sep #$20
.a8
    bne no_hay
    plb
    lda #$00                    ; de la SRAM a la ventana de la WRAM
    jsr partida_copiar
    lda #$01
    rts
no_hay:
    plb
    lda #$FF
    sta ranura                  ; el centinela: no hay partida cargada
    lda #$00
    rts
.endproc

; La celda donde quedó guardada la partida, puesta como entrada del mapa: es
; como una puerta le dice a `cargar_mapa` dónde plantar al héroe. Lo usan el
; arranque —cuando la ROM no lleva título y la partida se carga sola— y el menú
; del título cuando el jugador elige seguir. Estaba escrito en el arranque nomás
; y copiarlo al menú habría sido el segundo lugar donde equivocarse.
.proc entrada_de_la_partida
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta entrada_x
    lda tile_y
    sta entrada_y
    sep #$20
.a8
    rts
.endproc

