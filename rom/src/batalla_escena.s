; --- la escena de la pelea --------------------------------------------------
;
; El fondo de batalla con los monstruos encima: una sola capa de 8bpp de
; 256x128 en BG1, que son los siete renglones de texto de arriba. **Se compone
; acá, al empezar la pelea**, desde un fondo y los battlers de la tropa, que el
; cartucho lleva cada uno una vez. El porqué, el formato y el presupuesto están
; en tools/port/escena.py.
;
; Corre desde `batalla_correr` con el banco de datos en $7E, así que los
; registros del PPU y las tablas del cartucho van todos con `f:`, y el estado
; de acá se nombra con dirección de dieciséis bits, como `FAR_BATALLA`.
;
; **$7E6600 a $7E67FF es de esto**: el tramo se reservó de antemano el
; 2026-09-21, al repartir entre trabajos que tocaban la RAM lejana.
ESC_ORIGEN   = $6600    ; 1: la pelea la arrancó un encuentro al azar
ESC_FONDO    = $6601    ; el fondo de esta pelea, o $FF: el liso
ESC_VIS      = $6602    ; un bit por enemigo: todavía está dibujado
ESC_PAL_N    = $6603    ; cuántas paletas de battler se repartieron
ESC_PAL_BAT  = $6604    ; 8 bytes: qué battler lleva cada una
ESC_E_BAT    = $6610    ; 8 bytes: el battler de cada enemigo, o $FF
ESC_E_PAL    = $6618    ; 8 bytes: su paleta, de 0 a 7
ESC_E_X      = $6620    ; 8 bytes: su esquina en la escena
ESC_E_Y      = $6628
; Lo que falta subir a la VRAM de un enemigo que se acaba de borrar: filas de
; tiles enteras de la escena, de a `ESC_SUB_BUDGET` bytes por vblank.
ESC_SUB_N    = $6630    ; palabra: cuántas filas de tiles faltan; 0 es nada
ESC_SUB_FILA = $6632    ; palabra: la próxima
ESC_SUB_COL  = $6634    ; palabra: la primera columna de tiles
ESC_SUB_LARGO = $6636   ; palabra: cuántos bytes mide cada fila
; Cuántos cuadros llevó componer, contados con `boot_cuadros`: no lo lee la
; ROM, lo leen las pruebas y el que quiera medirlo con el emulador.
ESC_CUADROS  = $6638
ESC_T0       = $663A    ; de paso
ESC_E        = $663C    ; el enemigo que se está poniendo o borrando
ESC_I        = $663D
; El rectángulo al que se recorta un battler al ponerlo: filas de pixeles
; [Y0, Y1) y columnas de tiles [C0, C1) de la escena, en palabras.
ESC_CLIP_Y0  = $6640
ESC_CLIP_Y1  = $6642
ESC_CLIP_C0  = $6644
ESC_CLIP_C1  = $6646
; Por cuál va el recorrido en el orden de dibujo, y dónde empieza la tropa en
; las tablas `miembro_*`. Ver `esc_por_orden`.
ESC_K        = $6648
ESC_INI      = $6649
; Lo que había en la página directa que se toma prestada: ver `esc_dp_tomar`.
ESC_DP_GUARDA = $6680
ESC_DP_BYTES = 48

; El fondo limpio y la escena compuesta, 32 KB cada uno, en el banco $7F de la
; WRAM, que no usaba nadie: todo lo demás de la ROM vive en el $7E —la RAM
; lejana llega hasta $7E67FF— y ningún `WMADDH` se escribe con otra cosa que
; cero. El limpio es lo que deja borrar a un enemigo sin volver a leer nada del
; cartucho: ver `escena_tick`.
ESC_LIMPIO   = $7F0000
ESC_ESCENA   = $7F8000
; Cuántos bytes de escena se suben por vblank cuando se borra un enemigo. El
; vblank de NTSC da para unos seis kilobytes de DMA y `pant_subir` ya se lleva
; los 1.792 del texto en el mismo vblank; dos más dejan margen.
ESC_SUB_BUDGET = 2048

; --- la página directa prestada ---
;
; El lazo de `escena_poner` lee el battler con `[puntero], y` —su banco cambia
; con cada battler— y eso sólo existe con la página directa. La del juego está
; llena, así que se toma prestada una página de `pal_buf`, que la pelea no
; usa, y **se guarda y se repone** lo que tenía: la pelea no la toca, pero
; volver de ella con el destello a medio armar no tiene por qué encontrarla
; pisada. Ni la NMI ni `irq_musica` leen `pal_buf`, y la IRQ pone su propia
; página directa en cero.
;
; La página va alineada a 256: una página directa corrida cuesta un ciclo de
; más en cada acceso, y el lazo hace diez por columna. `pal_buf` mide 512, así
; que siempre tiene una página alineada adentro.
ED_M   = $00    ; los cinco punteros de 24 bits, uno por plano
ED_P0  = $03
ED_P1  = $06
ED_P2  = $09
ED_P3  = $0C
ED_TM  = $10    ; la máscara, y un cero al lado
ED_T0  = $12    ; los cuatro planos, de a byte: ED_T0 y ED_T2 se leen de a
ED_T1  = $13    ; palabra, que son los pares 0/1 y 2/3 del tile
ED_T2  = $14
ED_T3  = $15
ED_MM  = $18    ; la máscara en los dos bytes
ED_NM  = $1A    ; y negada
ED_P45 = $1C    ; los planos 4 a 7, que dependen de la paleta
ED_P67 = $1E
ED_FX  = $20    ; dónde empieza la fila en la escena
ED_FY  = $22    ; y en el battler
ED_COLS = $24   ; cuántas columnas de tiles
ED_CUENTA = $26
ED_FILAS = $28
ED_YY  = $2A    ; la fila de pixeles de la escena
ED_PASO = $2C   ; cuánto mide una fila de un plano
ED_N   = $2E    ; cuántas columnas tiene el battler

.proc esc_dp_tomar
.a8
.i16
    rep #$20
.a16
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tax
    ldy #0
guarda:
    lda a:$0000, x              ; la RAM baja: en el banco $7E es la misma
    sta ESC_DP_GUARDA, y
    inx
    inx
    iny
    iny
    cpy #ESC_DP_BYTES
    bcc guarda
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tcd
    sep #$20
.a8
    rts
.endproc

.proc esc_dp_devolver
.a8
.i16
    rep #$20
.a16
    lda #0
    tcd
    lda #.loword(pal_buf + $FF)
    and #$FF00
    tax
    ldy #0
repone:
    lda ESC_DP_GUARDA, y
    sta a:$0000, x
    inx
    inx
    iny
    iny
    cpy #ESC_DP_BYTES
    bcc repone
    sep #$20
.a8
    rts
.endproc

; --- poner un battler ---
;
; El lazo de adentro, una vez por cada corrimiento: un battler que no empieza
; en el borde de un tile se corre `CORRE` bits a la derecha, y los `lsr` van
; desenrollados porque son la mitad del costo. Por columna de tiles y fila de
; pixeles: cinco lecturas del battler —la máscara y cuatro planos—, cada una
; de dieciséis bits para traer también la columna de la izquierda, y cuatro
; palabras de la escena, que son los ocho planos del tile de a pares. Una
; columna sin nada del battler se saltea entera.
;
; Con A, X e Y de dieciséis bits: X es el desplazamiento en la escena e Y en
; el battler. Ver `escena_poner`, que es quien arma todo esto.
.macro ESC_LAZO CORRE
.local fila, col, vacia, otro_tile, puesta
fila:
    ldx ED_FX
    ldy ED_FY
    lda ED_COLS
    sta ED_CUENTA
col:
    lda [ED_M], y
    .repeat CORRE
    lsr a
    .endrepeat
    and #$00FF
    beq vacia
    sta ED_TM
    xba
    ora ED_TM
    sta ED_MM
    eor #$FFFF
    sta ED_NM
    ; Cada plano se guarda de a palabra y el siguiente pisa el byte alto, que
    ; es basura del corrimiento: así ED_T0 queda con los planos 0 y 1 juntos y
    ; ED_T2 con el 2 y el 3.
    lda [ED_P0], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T0
    lda [ED_P1], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T1
    lda [ED_P2], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T2
    lda [ED_P3], y
    .repeat CORRE
    lsr a
    .endrepeat
    sta ED_T3
    ; fondo AND NOT máscara OR battler, en los planos del dibujo
    lda f:ESC_ESCENA, x
    and ED_NM
    ora ED_T0
    sta f:ESC_ESCENA, x
    lda f:ESC_ESCENA + 16, x
    and ED_NM
    ora ED_T2
    sta f:ESC_ESCENA + 16, x
    ; y en los de la paleta, que son la máscara o nada:
    ; ((fondo ^ paleta) & máscara) ^ fondo
    lda f:ESC_ESCENA + 32, x
    eor ED_P45
    and ED_MM
    eor f:ESC_ESCENA + 32, x
    sta f:ESC_ESCENA + 32, x
    lda f:ESC_ESCENA + 48, x
    eor ED_P67
    and ED_MM
    eor f:ESC_ESCENA + 48, x
    sta f:ESC_ESCENA + 48, x
vacia:
    dey                         ; la columna de la derecha: ver `battler_bytes`
    txa
    clc
    adc #64                     ; el tile de al lado
    tax
    dec ED_CUENTA
    beq :+
    jmp col                     ; con siete `lsr` el cuerpo no entra en un `bne`
:
    ; La fila siguiente: en el battler, lo que mide una fila de un plano; en
    ; la escena, dos bytes, salvo que se cambie de fila de tiles.
    lda ED_FY
    clc
    adc ED_PASO
    sta ED_FY
    lda ED_YY
    and #7
    cmp #7
    beq otro_tile
    lda ED_FX
    inc a
    inc a
    bra puesta
otro_tile:
    lda ED_FX
    clc
    adc #(ESCENA_COLUMNAS * 64 - 14)
puesta:
    sta ED_FX
    inc ED_YY
    dec ED_FILAS
    beq :+
    jmp fila
:   rts
.endmacro

.a16
.i16
esc_lazo_0: ESC_LAZO 0
esc_lazo_1: ESC_LAZO 1
esc_lazo_2: ESC_LAZO 2
esc_lazo_3: ESC_LAZO 3
esc_lazo_4: ESC_LAZO 4
esc_lazo_5: ESC_LAZO 5
esc_lazo_6: ESC_LAZO 6
esc_lazo_7: ESC_LAZO 7
esc_lazos:
    .addr esc_lazo_0, esc_lazo_1, esc_lazo_2, esc_lazo_3
    .addr esc_lazo_4, esc_lazo_5, esc_lazo_6, esc_lazo_7
; El bit de cada enemigo en `ESC_VIS`.
esc_bits:
    .byte $01, $02, $04, $08, $10, $20, $40, $80
.a8

; `ESC_E` = el enemigo que va `ESC_K`-ésimo en el orden de dibujo, que es el
; de RM2k y no el de la tropa: `Sprite_Battler::ResetZ` de easyrpg ordena por
; el borde de abajo del battler, y a igual borde queda arriba el de menor
; lugar. El orden lo calcula el conversor: `miembro_orden`. Se lleva X.
.proc esc_por_orden
.a8
.i16
    rep #$20
.a16
    lda ESC_K
    clc
    adc ESC_INI
    and #$00FF
    tax
    sep #$20
.a8
    lda f:miembro_orden, x
    sta ESC_E
    rts
.endproc

; A8: el bit de `ESC_E` en `ESC_VIS`. Se lleva X.
.proc esc_bit
.a8
.i16
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    sep #$20
.a8
    lda f:esc_bits, x
    rts
.endproc

; El enemigo `ESC_E` sobre la escena de `ESC_ESCENA`, recortado a
; `ESC_CLIP_*`. Con la página directa ya prestada. Si no tiene battler, o si el
; recorte lo deja afuera, no hace nada.
.proc escena_poner
.a8
.i16
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    sep #$20
.a8
    lda ESC_E_BAT, x
    cmp #$FF
    bne hay
    rts
hay:
    ; --- el battler: sus medidas y sus cinco punteros ---
    rep #$20
.a16
    and #$00FF
    tay                         ; Y: el battler
    asl a
    asl a
    tax                         ; X: su puntero de 24 bits
    lda f:battler_dir, x
    sta ED_M
    sep #$20
.a8
    lda f:battler_dir + 2, x
    sta ED_M + 2
    sta ED_P0 + 2
    sta ED_P1 + 2
    sta ED_P2 + 2
    sta ED_P3 + 2
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:battler_plano, x
    sta ESC_T0
    lda ED_M
    clc
    adc ESC_T0
    sta ED_P0
    adc ESC_T0                  ; no hay acarreo: el battler no cruza de banco
    sta ED_P1
    adc ESC_T0
    sta ED_P2
    adc ESC_T0
    sta ED_P3
    tyx
    lda f:battler_n, x
    and #$00FF
    sta ED_N
    inc a
    sta ED_PASO
    lda f:battler_alto, x
    and #$00FF
    sta ED_FILAS                ; todavía sin recortar

    ; --- la paleta: los planos 4 a 7 de cada pixel del battler ---
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_PAL, x
    and #$0007
    sta ESC_T0
    lda #0
    lsr ESC_T0
    bcc :+
    ora #$00FF                  ; el bit 0 es el plano 4
:   lsr ESC_T0
    bcc :+
    ora #$FF00                  ; el 1, el 5
:   sta ED_P45
    lda #$FF00                  ; el plano 7 es la paleta 8 en adelante
    lsr ESC_T0
    bcc :+
    ora #$00FF                  ; y el 2, el 6
:   sta ED_P67

    ; --- las columnas: cuántas, desde cuál, y hasta dónde deja el recorte ---
    lda ESC_E_X, x
    and #$00FF
    sta ESC_T0
    and #7
    sta ED_CUENTA               ; el corrimiento, prestado un momento
    lda ED_N
    ldy ED_CUENTA
    beq :+
    inc a                       ; corrido, ocupa una columna más
:   sta ED_COLS
    lda ESC_T0
    lsr a
    lsr a
    lsr a
    sta ESC_T0                  ; la primera columna de tiles del battler
    ; La de la derecha, topada en la clip y en el borde de la escena.
    clc
    adc ED_COLS
    cmp ESC_CLIP_C1
    bcc :+
    lda ESC_CLIP_C1
:   sta ED_COLS                 ; ahora es la columna final, no cuántas
    ; La de la izquierda: la del battler o la del recorte.
    lda ESC_T0
    cmp ESC_CLIP_C0
    bcs :+
    lda ESC_CLIP_C0
:   sta ED_FX                   ; la primera columna que se toca, prestada
    lda ED_COLS
    sec
    sbc ED_FX
    bcs :+
    jmp afuera
:   bne :+
    jmp afuera
:   sta ED_COLS                 ; cuántas
    ; La columna del battler en que se empieza, que es la que da Y.
    lda ED_FX
    sec
    sbc ESC_T0
    sta ESC_T0                  ; columnas que se saltean del battler
    lda ED_N
    sec
    sbc ESC_T0
    sta ED_FY                   ; su lugar en la fila: ver `battler_bytes`

    ; --- las filas ---
    lda ESC_E_Y, x
    and #$00FF
    sta ED_YY
    clc
    adc ED_FILAS
    cmp ESC_CLIP_Y1
    bcc :+
    lda ESC_CLIP_Y1
:   sta ED_FILAS                ; la fila final
    lda ED_YY
    cmp ESC_CLIP_Y0
    bcs :+
    lda ESC_CLIP_Y0
:   sta ESC_T0                  ; la primera
    lda ED_FILAS
    sec
    sbc ESC_T0
    bcs :+
    jmp afuera
:   bne :+
    jmp afuera
:   sta ED_FILAS
    ; Las filas del battler que se saltean, por lo que mide cada una.
    lda ESC_T0
    sec
    sbc ED_YY
    tay
    lda ESC_T0
    sta ED_YY
    lda ED_FY
salta_fila:
    cpy #0
    beq filas_listas
    clc
    adc ED_PASO
    dey
    bra salta_fila
filas_listas:
    sta ED_FY
    ; Y en la escena: (fila / 8) * 2048 + columna * 64 + (fila % 8) * 2.
    lda ED_FX
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ED_FX
    lda ED_YY
    and #7
    asl a
    clc
    adc ED_FX
    sta ED_FX
    lda ED_YY
    and #$00F8
    xba                         ; por 256, o sea (fila / 8) * 2048
    clc
    adc ED_FX
    sta ED_FX

    ; --- el lazo que toca, que vuelve con todo en dieciséis bits ---
    lda ESC_E
    and #$00FF
    tay
    lda ESC_E_X, y
    and #7
    asl a
    tax
    jsr (esc_lazos, x)
    sep #$20
.a8
    rts
afuera:
.a16
    sep #$20
.a8
    rts
.endproc

; --- componer la escena entera, al empezar la pelea ---
;
; Con la pantalla apagada. Llena los dos búferes con el fondo —o con ceros—,
; pone los battlers de la tropa en orden y sube todo: los 32 KB de tiles, el
; tilemap, los colores del fondo y una paleta por battler distinto. Deja en
; `BA_ESCENA` un 0 si hay algo que mostrar y $FF si no.
.proc escena_subir
.a8
.i16
    lda f:boot_cuadros
    sta ESC_CUADROS
    lda #0
    sta ESC_CUADROS + 1
    sta ESC_VIS
    sta ESC_PAL_N
    rep #$20
.a16
    lda #0
    sta ESC_SUB_N
    sep #$20
.a8

    ; --- qué fondo: el del mapa si fue un encuentro, el de la tropa si no ---
    lda #$FF
    sta ESC_FONDO
    lda ESC_ORIGEN
    beq de_la_tropa
    rep #$20
.a16
    lda mapa_actual
    tax
    sep #$20
.a8
    lda f:escena_mapa_fondo, x
    bra fondo_elegido
de_la_tropa:
    lda BA_TROPA_K
    cmp #$FF
    beq sin_fondo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:escena_tropa_fondo, x
fondo_elegido:
    cmp #ESCENA_FONDOS
    bcs sin_fondo               ; $FF, o un cartucho sin fondos
    sta ESC_FONDO
sin_fondo:
    lda #0
    sta ESC_ORIGEN              ; lo prende sólo `encuentro_probar`

    ; --- los battlers de la tropa, y una paleta por cada uno distinto ---
    lda #0
    sta ESC_E
    lda BA_TROPA_K
    cmp #$FF
    bne con_tropa
    jmp repartidos
con_tropa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_ini, x
    sta ESC_I                   ; el primer miembro
    sta ESC_INI                 ; y de nuevo, para `esc_por_orden`
otro_enemigo:
    lda ESC_E
    cmp BA_NENE
    bcc :+
    jmp repartidos
:   rep #$20
.a16
    lda ESC_E
    and #$00FF
    tay                         ; Y: el enemigo
    clc
    adc ESC_I
    and #$00FF
    tax                         ; X: el miembro
    sep #$20
.a8
    lda f:miembro_x, x
    sta ESC_E_X, y
    lda f:miembro_y, x
    sta ESC_E_Y, y
    lda f:miembro_battler, x
    sta ESC_E_BAT, y
    cmp #$FF
    beq siguiente
    ; ¿Ya tiene paleta ese battler? El tope, de a palabra para `cpx`.
    pha
    rep #$20
.a16
    lda ESC_PAL_N
    and #$00FF
    sta ESC_T0
    sep #$20
.a8
    pla
    ldx #0
busca_pal:
    cpx ESC_T0
    beq pal_nueva
    cmp ESC_PAL_BAT, x
    beq pal_lista
    inx
    bra busca_pal
pal_nueva:
    sta ESC_PAL_BAT, x
    inc ESC_PAL_N
pal_lista:
    txa
    sta ESC_E_PAL, y
    ; Y el bit de dibujado, que es lo que `escena_tick` mira.
    jsr esc_bit
    ora ESC_VIS
    sta ESC_VIS
siguiente:
    inc ESC_E
    jmp otro_enemigo
repartidos:
    lda ESC_FONDO
    cmp #$FF
    bne hay_escena
    lda ESC_VIS
    bne hay_escena
    jmp sin_escena              ; ni fondo ni battlers: sobre negro, como antes
hay_escena:
    lda #0
    sta BA_ESCENA

    ; --- el fondo, a los dos búferes ---
    lda #0
    jsr esc_llenar
    lda #$80
    jsr esc_llenar

    ; --- los battlers, en el orden de dibujo: el de después tapa ---
    rep #$20
.a16
    lda #0
    sta ESC_CLIP_Y0
    sta ESC_CLIP_C0
    lda #ESCENA_ALTO
    sta ESC_CLIP_Y1
    lda #ESCENA_COLUMNAS
    sta ESC_CLIP_C1
    sep #$20
.a8
    jsr esc_dp_tomar
    lda #0
    sta ESC_K
poner:
    lda ESC_K
    cmp BA_NENE
    bcs puestos
    jsr esc_por_orden
    jsr escena_poner
    inc ESC_K
    bra poner
puestos:
    jsr esc_dp_devolver

    ; --- la escena compuesta, a la VRAM ---
    lda #$80
    sta f:VMAIN                 ; una palabra por escritura
    rep #$20
.a16
    lda #ESCENA_VRAM
    sta f:VMADDL
    lda #.loword(ESC_ESCENA)
    sta f:A1T0L
    lda #(ESCENA_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^ESC_ESCENA
    sta f:A1B0
    lda #$01                    ; dos registros: VMDATAL y VMDATAH
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN

    ; --- el tile transparente, en la palabra 0 ---
    rep #$20
.a16
    lda #0
    sta f:VMADDL
    lda #64
    sta f:DAS0L
    lda #.loword(escena_cero)
    sta f:A1T0L
    sep #$20
.a8
    lda #^escena_cero
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN

    ; --- el tilemap: los 512 tiles en orden y el resto tapado ---
    ;
    ; Se escribe a mano y no por DMA: son los números 0, 1, 2... y emitirlos
    ; serían dos kilobytes de cartucho para decir eso.
    rep #$20
.a16
    lda #ESCENA_MAPA
    sta f:VMADDL
    lda #0
    sta ESC_T0                  ; el tile que va en la celda
    ldx #0
celda:
    cpx #ESCENA_TILES
    bcc celda_escena
    lda #ESCENA_BLANCO
    bra celda_pone
celda_escena:
.a16
    lda ESC_T0
celda_pone:
.a16
    sta f:VMDATAL
    inc ESC_T0
    inx
    cpx #(32 * 32)
    bcc celda
    sep #$20
.a8

    ; --- los 96 colores del fondo, desde la entrada ESCENA_CGRAM ---
    lda ESC_FONDO
    cmp #$FF
    beq colores_battlers
    lda #ESCENA_CGRAM
    sta f:CGADD
    rep #$20
.a16
    lda ESC_FONDO
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 64
    sta ESC_T0
    asl a                       ; por 128
    clc
    adc ESC_T0                  ; y por 192, que son ESCENA_COLORES * 2
    clc
    adc #.loword(fondo_cgram)
    sta f:A1T0L
    lda #(ESCENA_COLORES * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #^fondo_cgram
    jsr esc_dma_cgram

    ; --- y una paleta de dieciséis por battler, desde la 8 ---
colores_battlers:
    lda #0
    sta ESC_I
otra_paleta:
    lda ESC_I
    cmp ESC_PAL_N
    bcs listo
    asl a
    asl a
    asl a
    asl a
    clc
    adc #(ESCENA_BAT_PALETA * 16)
    sta f:CGADD
    rep #$20
.a16
    lda ESC_I
    and #$00FF
    tax
    lda ESC_PAL_BAT, x
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32
    clc
    adc #.loword(battler_cgram)
    sta f:A1T0L
    lda #32
    sta f:DAS0L
    sep #$20
.a8
    lda #^battler_cgram
    jsr esc_dma_cgram
    inc ESC_I
    bra otra_paleta
listo:
    lda f:boot_cuadros
    sec
    sbc ESC_CUADROS
    sta ESC_CUADROS
    rts
sin_escena:
.a8
    lda #$FF
    sta BA_ESCENA
    rts
.endproc

; El DMA a la CGRAM con origen y largo ya puestos: A el banco del origen.
.proc esc_dma_cgram
.a8
.i16
    sta f:A1B0
    lda #0
    sta f:DMAP0                 ; `stz` no tiene modo largo
    lda #$22
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rts
.endproc

; Uno de los dos búferes de la escena, con el fondo de `ESC_FONDO` o con ceros:
; A es el byte del medio de su dirección, 0 el limpio y $80 el compuesto.
; Por la ventana de la WRAM, que es la única forma de copiar de la ROM a la RAM
; por DMA; el banco es el $7F, así que WMADDH va en 1.
.proc esc_llenar
.a8
.i16
    sta f:WMADDM
    lda #0
    sta f:WMADDL
    lda #1
    sta f:WMADDH
    lda #$80                    ; WMDATA
    sta f:BBAD0
    lda ESC_FONDO
    cmp #$FF
    bne con_fondo
    ; El fondo liso: el mismo cero 32.768 veces, con el origen fijo.
    rep #$20
.a16
    lda #.loword(escena_cero)
    sta f:A1T0L
    lda #(ESCENA_TILES * 64)
    sta f:DAS0L
    sep #$20
.a8
    lda #^escena_cero
    sta f:A1B0
    lda #$08
    sta f:DMAP0
    lda #$01
    sta f:MDMAEN
    rts
con_fondo:
    ; Los cuatro trozos del fondo, uno detrás del otro: la dirección de la
    ; WRAM sigue sola.
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a                       ; por ESCENA_TROZOS * 4: la fila de punteros
    tax
    sep #$20
.a8
    lda #0
    sta ESC_I
trozo:
    rep #$20
.a16
    lda f:fondo_trozo, x
    sta f:A1T0L
    lda #ESCENA_TROZO
    sta f:DAS0L
    sep #$20
.a8
    lda f:fondo_trozo + 2, x
    sta f:A1B0
    lda #0
    sta f:DMAP0
    lda #$01
    sta f:MDMAEN
    inx
    inx
    inx
    inx
    inc ESC_I
    lda ESC_I
    cmp #ESCENA_TROZOS
    bcc trozo
    rts
.endproc

; --- borrar a un enemigo muerto ---
;
; Una vez por cuadro, desde el lazo de la pelea y **adentro del vblank**, justo
; después de `ba_t_subir`. Si quedaron filas de un enemigo recién borrado sin
; subir, sube las que entran y vuelve. Si no, busca uno muerto que todavía se
; vea y lo borra: las celdas que tapaba vuelven a ser las del fondo limpio, se
; le vuelven a poner encima los que siguen vivos —recortados a esas celdas y
; en el orden de dibujo, para que no cambie quién tapa a quién— y queda
; encolado para los vblanks que siguen. Uno por cuadro: dos que mueren en el
; mismo turno se borran uno detrás del otro.
;
; RM2k lo hace desaparecer con un fundido; acá se va de golpe, en los cuadros
; que tarda en subir.
.proc escena_tick
.a8
.i16
    lda BA_ESCENA
    cmp #$FF
    bne hay
    rts
hay:
    rep #$20
.a16
    lda ESC_SUB_N
    beq buscar
    jmp subir
buscar:
    sep #$20
.a8
    lda #0
    sta ESC_E
otro:
    lda ESC_E
    cmp BA_NENE
    bcc :+
    rts
:   ; ¿Está dibujado?
    jsr esc_bit
    sta ESC_T0
    and ESC_VIS
    beq siguiente
    ; ¿Y muerto?
    lda ESC_E
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sep #$20
.a8
    beq borrar
siguiente:
    inc ESC_E
    bra otro

borrar:
    lda ESC_T0
    eor #$FF
    and ESC_VIS
    sta ESC_VIS
    ; El rectángulo, en tiles: las columnas que toca y las filas enteras.
    rep #$20
.a16
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_BAT, x
    and #$00FF
    tay
    lda ESC_E_X, x
    and #$00FF
    sta ESC_T0
    lsr a
    lsr a
    lsr a
    sta ESC_CLIP_C0
    sta ESC_SUB_COL
    tyx
    lda f:battler_n, x
    and #$00FF
    sta ESC_CLIP_C1             ; de paso
    lda ESC_T0
    and #7
    beq :+
    inc ESC_CLIP_C1             ; corrido, ocupa una más
:   lda ESC_CLIP_C1
    clc
    adc ESC_CLIP_C0
    cmp #ESCENA_COLUMNAS
    bcc :+
    lda #ESCENA_COLUMNAS
:   sta ESC_CLIP_C1
    sec
    sbc ESC_CLIP_C0
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sta ESC_SUB_LARGO           ; bytes por fila de tiles
    lda f:battler_alto, x
    and #$00FF
    sta ESC_T0
    lda ESC_E
    and #$00FF
    tax
    lda ESC_E_Y, x
    and #$00FF
    pha
    and #$00F8
    sta ESC_CLIP_Y0             ; desde la primera fila de su primer tile
    lsr a
    lsr a
    lsr a
    sta ESC_SUB_FILA
    pla
    clc
    adc ESC_T0
    clc
    adc #7
    and #$00F8
    sta ESC_CLIP_Y1             ; hasta la última de su último tile
    sec
    sbc ESC_CLIP_Y0
    lsr a
    lsr a
    lsr a
    sta ESC_SUB_N

    ; --- las celdas, desde el fondo limpio ---
    ; Fila por fila de tiles con `mvn`, que copia adentro del banco $7F y deja
    ; el banco de datos en él: se guarda y se repone.
    lda ESC_SUB_FILA
    sta ESC_T0
    lda ESC_SUB_N
    sta ESC_I                   ; y ESC_I + 1: se usa de palabra acá
copia:
    lda ESC_T0
    xba                         ; fila * 256...
    lsr a
    lsr a
    lsr a                       ; ...entre ocho: fila * 32 tiles
    clc
    adc ESC_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 64 bytes
    tax
    clc
    adc #.loword(ESC_ESCENA)
    tay
    lda ESC_SUB_LARGO
    dec a                       ; `mvn` copia A + 1
    phb
    mvn #^ESC_LIMPIO, #^ESC_ESCENA
    plb
    inc ESC_T0
    dec ESC_I
    bne copia

    ; --- y los que siguen vivos encima, recortados a esas celdas ---
    sep #$20
.a8
    lda ESC_E
    pha
    jsr esc_dp_tomar
    lda #0
    sta ESC_K
reponer:
    lda ESC_K
    cmp BA_NENE
    bcs repuestos
    jsr esc_por_orden
    jsr esc_bit
    and ESC_VIS
    beq :+
    jsr escena_poner
:   inc ESC_K
    bra reponer
repuestos:
    jsr esc_dp_devolver
    pla
    sta ESC_E
    rts

    ; --- subir lo que entra en este vblank ---
subir:
.a16
    lda #0
    sta ESC_T0                  ; cuántos bytes van
fila:
    lda ESC_T0
    clc
    adc ESC_SUB_LARGO
    cmp #(ESC_SUB_BUDGET + 1)
    bcc :+
    lda ESC_T0
    bne listo                   ; ya subió una y la que sigue no entra
    lda ESC_SUB_LARGO
:   sta ESC_T0
    ; La fila de tiles: `(fila * 32 + columna)` tiles desde la base.
    lda ESC_SUB_FILA
    xba
    lsr a
    lsr a
    lsr a
    clc
    adc ESC_SUB_COL
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32 palabras
    pha
    clc
    adc #ESCENA_VRAM
    sta f:VMADDL
    pla
    asl a                       ; por 64 bytes
    clc
    adc #.loword(ESC_ESCENA)
    sta f:A1T0L
    lda ESC_SUB_LARGO
    sta f:DAS0L
    sep #$20
.a8
    lda #$80
    sta f:VMAIN
    lda #^ESC_ESCENA
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    inc ESC_SUB_FILA
    dec ESC_SUB_N
    bne fila
listo:
    sep #$20
.a8
    rts
.endproc

; BG1 con la escena, después de que `ranura_ppu_prender` haya puesto BG2 y
; prendido la pantalla. Si esta pelea no tiene escena no toca nada y la
; pantalla queda sobre negro, como antes del 2026-09-13.
.proc escena_prender
.a8
.i16
    lda BA_ESCENA
    cmp #$FF
    beq listo
    lda #((ESCENA_MAPA / 1024) * 4)
    sta f:BG1SC                 ; 32x32, que es lo que tapa la pantalla entera
    lda #((RANURA_VRAM / 4096) * 16 + (ESCENA_VRAM / 4096))
    sta f:BG12NBA               ; el texto en BG2 y la escena en BG1
    lda #0
    sta f:BG1HOFS               ; `stz` no tiene modo largo
    sta f:BG1HOFS
    lda #$FF
    sta f:BG1VOFS               ; el PPU muestra vofs+1: con -1 cae en su lugar
    sta f:BG1VOFS
    lda #$03
    sta f:TM                    ; BG1 y BG2
listo:
    rts
.endproc

; Al volver al mapa, las ocho paletas de arriba desde `cgram_sombra`, antes que
; nada: los battlers se las llevaron, y lo que el mapa repone solo son las de
; sus objetos —`SPRITE_CGRAM` colores— y la del cronómetro. El cartel y la
; animación de batalla suben su paleta sólo cuando cambia, así que sin esto
; volverían con los colores de un battler. Con la pantalla apagada: la llama
; `volver_de_batalla`, del banco 0, con el banco de datos en 0.
.proc escena_cgram_reponer
.a8
.i16
    lda #128
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * 128)
    sta A1T0L
    lda #256
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; la sombra vive en el banco 0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

