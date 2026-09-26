.segment "CODE"

; --- el MSU-1 ---------------------------------------------------------------
;
; El MSU-1 no es hardware de la consola: es una extensión que soportan el FX
; Pak Pro y los emuladores, con la música en archivos PCM al lado de la ROM.
; Cuando el tema que se prende tiene pista —`tema_msu`, que emite el
; conversor—, el SPC700 se calla y suena la pista; los efectos de sonido
; siguen en el SPC700 como siempre. Sin MSU-1 no cambia nada: la firma no
; está y todo sigue saliendo del SPC700.
;
; Los registros viven en $2000..$2007 de cualquier banco del área baja:
;
;   $2000  leer: bit 7 datos ocupados, 6 pista cargando, 5 repitiendo,
;          4 tocando, 3 pista ausente, 2..0 revisión
;   $2002..$2007  leer: la firma "S-MSU1"
;   $2004  escribir: qué pista, dos bytes
;   $2006  el volumen, de 0 a 255
;   $2007  bit 0 tocar, bit 1 repetir
MSU_ESTADO  = $2000
MSU_FIRMA   = $2002
MSU_PISTA   = $2004
MSU_VOLUMEN = $2006
MSU_CONTROL = $2007
MSU_HAY     = $7E30E8           ; si la firma está
MSU_SUENA   = $7E30E9           ; si la pista está tocando ahora

; El volumen con que suena la pista, de 0 a 255, y **no es 255**: el MSU-1 se
; suma a la salida del SPC700 en vez de mezclarse con ella, así que la música a
; fondo no deja margen para los efectos de sonido. Con 255, en la apertura, 42
; muestras llegaban al tope —y las 42 en cuadros con un efecto sonando—,
; mientras que la misma corrida por el SPC700 no clavetea ni una vez. Medido
; también: la música por pista picaba 28933 contra 23867 del SPC700, o sea
; 1,21 veces más alta, que es lo que taro escuchó como "los efectos se oyen
; mucho más bajos".
;
; $D8 es ese 0,85. Baja la música hasta donde estaba y devuelve el margen, sin
; tocar las pistas: normalizarlas más abajo serían 195 MB a rehacer por ROM y
; encima perdería la referencia de nivel entre un tema y otro.
MSU_VOLUMEN_MAX = $D8

; Y dos bytes para el factor del fundido, en la RAM lejana porque la del banco 0
; está llena. El byte alto queda siempre en cero: el lazo lo suma de a dieciséis
; bits. Vive acá y no en `temp` porque el fundido corre adentro de `irq_musica`.
MSU_FACTOR  = $7E30EA

; La firma, una vez, en el reset.
.proc msu_detectar
.a8
.i16
    lda #0
    sta f:MSU_SUENA
    ldx #$0000
mirar:
    lda MSU_FIRMA, x
    cmp msu_firma, x
    bne no_hay
    inx
    cpx #6
    bcc mirar
    lda #1
    sta f:MSU_HAY
    rts
no_hay:
    lda #0
    sta f:MSU_HAY
    rts
.endproc

msu_firma:
    .byte "S-MSU1"

; Calla la pista, si había una.
.proc msu_parar
.a8
.i16
    lda f:MSU_SUENA
    beq listo
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
listo:
    rts
.endproc

; Espera a que el MSU-1 suelte `AUDIO_BUSY`. Vuelve con el acarreo limpio si lo
; soltó y puesto si se acabó el tiempo. Se lleva X.
;
; **Este lazo no lo ejercita ningún core de la tanda.** bsnes no pone
; `io.audioBusy` nunca —arranca en falso en `power()` y no se escribe en ningún
; lado; está en `/extras/ref/bsnes-libretro/bsnes/sfc/coprocessor/msu1/msu1.cpp`—,
; y snes9x tampoco, así que en la tanda sale en la primera vuelta. **Mednafen
; sí** (`-force_module snes_faust`): prende el bit 6 por 400.000 ciclos maestros
; al elegir la pista —`MSU1_WriteTrack` en `snes_faust/msu1.cpp`— y recién lo
; apaga al final del cuadro en que se cumplen, o sea uno o dos cuadros. Que las
; pistas suenen ahí es la prueba de que este lazo espera. En el FX Pak la pista
; sale de la tarjeta SD, y eso no está medido.
;
; Por eso el tope es generoso y no ajustado: $FFFF vueltas de 96 ciclos maestros
; —desde el espejo rápido—, unos diecisiete cuadros. Antes eran $4000 —setenta
; milisegundos— y el precio de quedarse corto no es un cuadro perdido sino que
; el tema entero suene por el SPC700.
MSU_ESPERA = $FFFF

.proc msu_esperar
.a8
.i16
    ldx #$0000
otra:
    lda MSU_ESTADO
    and #$40                    ; la está cargando
    beq listo
    inx
    cpx #MSU_ESPERA
    bcc otra
    sec
    rts
listo:
    clc
    rts
.endproc

; Arranca la pista del tema A, si tiene y si hay MSU-1. Vuelve con A distinto
; de cero si la pista quedó sonando, y ahí la música del SPC700 no va.
.proc msu_arrancar
.a8
.i16
    pha
    lda f:MSU_HAY               ; de a un byte: con `ldx` se leía el de al lado
    beq sin_msu1
    pla
    cmp #TEMA_TOTAL
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda tema_msu, x
    cmp #$FF
    beq no
    ; **Antes de escribir la pista, esperar a que el MSU-1 esté libre.** Con
    ; `AUDIO_BUSY` puesto el hardware ignora las escrituras a los registros de
    ; audio —en bsnes se ve en `writeIO`, `case 0x2007: if(io.audioBusy)
    ; break;`—, así que un `PlayBGM` que llega mientras la pista anterior
    ; todavía se está abriendo se pierde entero. Acá pasa de verdad: con
    ; pantalla de título hay dos pistas pedidas con 1,8 s de diferencia —la del
    ; título y la de la apertura—, y sin pantalla de título la primera es la
    ; única.
    ;
    ; La pista se guarda en Y mientras tanto: la espera usa X.
    tay
    jsr msu_esperar
    bcs no                      ; sigue ocupado: que suene el SPC700
    tya
    sta MSU_PISTA
    stz MSU_PISTA + 1
    jsr msu_esperar             ; y ahora, que termine de abrirla
    bcs no
    lda MSU_ESTADO
    and #$08                    ; la pista no está en la tarjeta
    bne no
    lda #MSU_VOLUMEN_MAX
    sta MSU_VOLUMEN
    lda #$03                    ; tocar y repetir
    sta MSU_CONTROL
    lda #1
    sta f:MSU_SUENA
    rts
sin_msu1:
    pla
no:
    lda #0
    rts
.endproc


; --- el puerto de datos -----------------------------------------------------
;
; El `.msu` no es sólo lo que enciende el MSU-1: es un archivo que la ROM lee
; como un flujo. Se escribe una posición de 32 bits en $2000..$2003 —la
; escritura a $2003 es la que busca—, se espera a que se apague el bit 7 de
; $2000 y se lee de $2001, que avanza solo. Por DMA con el origen fijo en
; $2001 sale a la velocidad de cualquier DMA: en bsnes el A-bus sólo excluye
; $2100..$21FF y los registros de la CPU (`validA`, en sfc/cpu/dma.cpp), y en
; snes9x la página $2000 es `MAP_PPU`, sin puntero directo, así que el DMA va
; byte por byte por `S9xGetPPU`, que atiende al MSU-1.
;
; Qué hay adentro y en qué formato lo decide el conversor: ver
; tools/port/msu_datos.py y docs/port/msu-datos.md. Hoy son los fondos de
; batalla, y **la ROM sigue llevando los suyos**: esto los reemplaza sólo si
; hay MSU-1 y el `.msu` es el de este cartucho.
;
; Va en el banco 1 porque lo llama la escena de la pelea, que corre ahí y con
; el banco de datos en $7E: por eso cada registro va con `f:`. Un `lda $2000`
; suelto leería la WRAM.
MSU_BUSCAR  = $2000             ; escribir: la posición, cuatro bytes
MSU_DATOS   = $2001             ; leer: el byte que sigue
.segment "FAR"

; Busca en el `.msu` la posición de 32 bits que viene en A —los dieciséis de
; abajo, con A de dieciséis bits— y en Y —los de arriba— y espera a que el
; MSU-1 la tenga. Vuelve con A de ocho bits, el acarreo limpio si quedó lista y
; puesto si se acabó el tiempo. Se lleva X.
;
; Las escrituras de dieciséis bits van primero al byte bajo, así que $2003, la
; que busca, es la última: es el orden que pide el MSU-1.
;
; **La espera no la ejercita ningún core de la tanda**, igual que
; `msu_esperar`: bsnes, snes9x, mesen-s y ares no ponen nunca `dataBusy` —buscan
; en el acto—. **Mednafen sí**: `MSU1_WriteDataSeek` prende el bit 7 por 400.000
; ciclos maestros, y como `MSU1_ReadStatus` no se pone al día, se apaga al final
; del cuadro en que se cumplen: cada búsqueda cuesta uno o dos cuadros. Medido
; el 2026-09-26 en la pelea del droide jugando desde el título: el fondo sale
; del `.msu`, con `ESC_CUADROS` en 11 contra 4 de snes9x. Ver "Cuánto tarda"
; en docs/port/msu-datos.md.
;
; En el FX Pak buscar fuera de su búfer de 16 KB es leer la tarjeta SD
; —`prepare_data` en `/extras/ref/sd2snes/src/msu1.c`—, unos milisegundos. El
; tope es el mismo que el del audio y por lo mismo: $FFFF vueltas de 114 ciclos
; maestros —esto corre en el banco 1, lento—, unos veintiún cuadros, diez veces
; lo que tarda Mednafen. Quedarse corto no cuesta un cuadro sino que la pelea
; use el fondo de la ROM.
.proc msu_datos_buscar
.a16
.i16
    sta f:MSU_BUSCAR
    tya
    sta f:MSU_BUSCAR + 2
    sep #$20
.a8
    ldx #$0000
otra:
    lda f:MSU_ESTADO
    bpl listo                   ; el bit 7: todavía buscando
    inx
    cpx #MSU_ESPERA
    bcc otra
    sec
    rts
listo:
    clc
    rts
.endproc

; Si el `.msu` es el de este cartucho: A en 1 si hay MSU-1 y los 8 primeros
; bytes del `.msu` son `msu_datos_firma`, que el conversor saca del contenido.
; Con otro `.msu` —de otro build, vacío, cortado— o sin MSU-1, A en 0 y la ROM
; usa lo suyo. Un `.msu` más corto que la firma también da 0: los tres
; emuladores devuelven cero pasado el final, y la firma no es ocho ceros más
; que por un azar de uno en 2^64.
.proc msu_datos_validos
.a8
.i16
    lda f:MSU_HAY
    beq no
    rep #$20
.a16
    lda #0
    tay
    jsr msu_datos_buscar
.a8
    bcs no
    ldx #0
compara:
    lda f:MSU_DATOS
    cmp f:msu_datos_firma, x
    bne no
    inx
    cpx #8
    bcc compara
    lda #1
    rts
no:
    lda #0
    rts
.endproc
