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
; **Este lazo no lo ejercita ningún emulador.** bsnes no pone `io.audioBusy`
; nunca —arranca en falso en `power()` y no se escribe en ningún lado; está en
; `/extras/ref/bsnes-libretro/bsnes/sfc/coprocessor/msu1/msu1.cpp`—, así que en
; la tanda, en las pruebas de estado y en cualquier corrida de acá adentro sale
; en la primera vuelta. En el FX Pak la pista sale de la tarjeta SD y abrirla
; lleva tiempo de verdad, así que **el único lugar donde esto corre es el
; hardware**, que es la definición de camino sin red.
;
; Por eso el tope es generoso y no ajustado: son $FFFF vueltas de unos dieciséis
; ciclos, del orden de tres décimas de segundo. Antes eran $4000 —setenta
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

