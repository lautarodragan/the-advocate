.segment "CODE"

; --- el paquete de audio de cada mapa ----------------------------------------
;
; La ARAM no alcanza para todas las muestras del cartucho —la música de los
; temas de la demo son 53 KB y los efectos que piden los mapas 2 y 3, 43 y
; 55 más—, así que se suben por mapa: al cargar uno, los temas que sus páginas
; pueden prender y los efectos que piden, en el orden en que aparecen. Es la
; tabla `paquetes` que arma el conversor. Los que no entran no suenan. Con
; MSU-1, los temas que tienen pista no: ver `tema_por_msu`.
;
; Las muestras tienen número fijo en todo el cartucho —el SRCN que el stream
; de la música ya escribe— y el directorio del SPC700 tiene una entrada por
; cada una. La que no está en la ARAM apunta al silencio. `FAR_ARAM_DE` dice
; dónde está cada una, o 0.
;
; **Las del tema que está sonando no se mueven**: la música sigue durante el
; fundido del salto, y pisarle una muestra que está tocando sería ruido. Todo
; lo demás se vuelve a acomodar desde el principio de la ARAM, saltando esas.
; Ver "El paquete de audio de cada mapa" en workflow/tasks/done/audio-bgm.md.
FAR_ARAM_DE = $7E3100           ; una palabra por muestra
FAR_QUIERE  = $7E3300           ; un byte por muestra: 2 las que no se mueven
APU_LISTO   = $7E30D0           ; si el driver ya corre
PAQ_EXTRA   = $7E30D1           ; un tema que va primero, o $FF
PAQ_COMPACTAR = $7E30D2         ; 1 si el paquete se está acomodando de nuevo
                                ; desde cero: ver `paquete_cargar_ya`
PAQ_LARGO   = $7E30D4
PAQ_DEST    = $7E30D6
PAQ_S       = $7E30D8           ; la muestra que se acomoda
PAQ_X7      = $7E30DA           ; su fila en `muestra_tabla`
PAQ_A       = $7E30DC           ; dónde se prueba ponerla
PAQ_MAPA    = $7E30DE           ; el mapa del paquete, en un word desde que
                                ; el índice de mapa no entra en un byte
INT_N       = $7E30E0           ; cuántos ocupados, en bytes: dos por cada uno
                                ; $30E2 a $30E6 son de la animación de batalla
PAQ_INCOMPLETO = $7E30E7        ; 1 si algo del paquete no entró: ver
                                ; `tema_asegurar`. Lo que sigue es MSU_HAY
INT_INI     = $7E3400           ; lo ocupado, en orden: dónde empieza
INT_FIN     = $7E3500           ; y dónde termina

; Nada en la ARAM. En el reset: el driver todavía no corre.
.proc aram_limpiar
.a8
.i16
    lda #0
    sta f:APU_LISTO
    sta f:PAQ_INCOMPLETO
    lda #$FF
    sta f:PAQ_EXTRA
    ldx #0
otra:
    lda #0
    sta f:FAR_ARAM_DE, x
    inx
    cpx #(2 * MUESTRAS_N)
    bcc otra
    rts
.endproc

; El testigo: el comando ya está en los puertos, y el driver lo toma cuando
; cambia. Se espera el acuse.
.proc apu_testigo
.a8
.i16
    inc token
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; El puntero de la ARAM, a PAQ_DEST. Con las interrupciones cortadas: la
; música usa los mismos puertos, y el puerto 2 tiene que volver a 0 antes de
; que ella mande su próximo par.
.proc aram_apuntar
.a8
.i16
    php
    sei
    lda #2
    sta APUIO2
    lda f:PAQ_DEST
    sta APUIO0
    lda f:PAQ_DEST + 1
    sta APUIO1
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; Un byte, el de A, donde apunta el puntero; el puntero avanza.
.proc aram_byte
.a8
.i16
    php
    sei
    sta APUIO0
    lda #1
    sta APUIO2
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; La muestra de la fila PAQ_X7 de `muestra_tabla`, a PAQ_DEST. De a ternas
; por el comando 3, en tandas de hasta 128 con las interrupciones cortadas
; —unos cinco milisegundos: la música se atrasa, no se pierde—, y lo que
; sobra de a un byte.
.proc subir_muestra
.a8
.i16
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla, x
    sta comp_glifo
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    sep #$20
.a8
    lda f:muestra_tabla + 2, x
    sta comp_glifo + 2
    ldy #0
tanda:
    ; El puntero, a donde va la terna que sigue: el bloque no lo avanza.
    rep #$20
.a16
    tya
    clc
    adc f:PAQ_A
    sta f:PAQ_DEST
    sty temp
    lda f:PAQ_LARGO
    sec
    sbc temp                    ; lo que falta
    sta temp + 2
    sep #$20
.a8
    jsr aram_apuntar
    rep #$20
.a16
    lda temp + 2
    cmp #3
    bcs hay_ternas
    jmp resto
hay_ternas:
    sta WRDIVL
    sep #$20
.a8
    lda #3
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL                  ; cuántas ternas quedan, si entran en un byte
    ldx RDDIVL
    cpx #85
    bcc cuantas
    lda #85                     ; el índice del driver es de un byte
cuantas:
    rep #$20
.a16
    and #$00FF                  ; la cuenta, en X
    tax
    sep #$20
.a8
    php
    sei
    sta APUIO0
    lda #3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
acuse_bloque:
    cmp APUIO3
    bne acuse_bloque
    ; La primera terna, leída antes; las demás se leen mientras el SPC700
    ; guarda la anterior, que es lo que más tarda. Nunca una de más: pasado el
    ; final del bloque puede haber registros que se alteran al leerlos.
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
terna:
    lda temp
    sta APUIO0
    lda temp + 1
    sta APUIO1
    lda temp + 3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    dex
    beq ultima
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
    lda token
acuse:
    cmp APUIO3
    bne acuse
    bra terna
ultima:
    lda token
acuse_ultima:
    cmp APUIO3
    bne acuse_ultima
    stz APUIO2
    plp
    jmp tanda
.a16
resto:
    sep #$20
.a8
    ; Lo que falta, 0, 1 o 2, de a un byte: el puntero ya está donde va.
    lda temp + 2
    beq listo
    sta temp
un_byte:
    lda [comp_glifo], y
    iny
    jsr aram_byte
    dec temp
    bne un_byte
listo:
    rts
.endproc

; La muestra PAQ_S, ya subida a PAQ_A: su entrada del directorio, con dónde
; empieza y dónde vuelve.
.proc escribir_directorio
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_S
    and #$00FF
    asl a
    asl a
    clc
    adc #SPC_SAMPLES_ADDR
    sta f:PAQ_DEST
    sep #$20
.a8
    jsr aram_apuntar
    lda f:PAQ_A
    jsr aram_byte
    lda f:PAQ_A + 1
    jsr aram_byte
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla + 5, x  ; el loop, desde el principio
    clc
    adc f:PAQ_A
    sta temp
    sep #$20
.a8
    lda temp
    jsr aram_byte
    lda temp + 1
    jmp aram_byte
.endproc

; X7 de la muestra A: A * 7, en PAQ_X7 y en X.
.proc fila_de_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp
    sta f:PAQ_X7
    tax
    sep #$20
.a8
    rts
.endproc

; Le busca lugar a la muestra A, si no está: el primer hueco desde ARAM_DATOS
; que no pise a ninguna de las que ya tienen lugar. Si no entra antes de
; ARAM_FIN, no sube y no suena. **No la sube**: la anota con 3 en FAR_QUIERE y
; la sube `subir_colocadas`, cuando ya se sabe que el paquete entra; ver
; `paquete_cargar_ya`.
.proc colocar_muestra
.a8
.i16
    sta f:PAQ_S
    rep #$30
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    beq no_esta
    rts                         ; ya está
no_esta:
    lda f:PAQ_S
    jsr fila_de_muestra
    rep #$30
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    ; El primer hueco donde entre: se recorren los ocupados en orden, con
    ; PAQ_A en el principio del hueco que se mira.
    lda #ARAM_DATOS
    sta f:PAQ_A
    ldx #0
hueco:
    txa
    cmp f:INT_N
    bcs al_final
    lda f:INT_INI, x
    sec
    sbc f:PAQ_A                 ; cuánto hay antes de este ocupado
    bcc sigue                   ; empieza antes: no hay hueco
    cmp f:PAQ_LARGO
    bcs aca                     ; entra
sigue:
    lda f:INT_FIN, x
    cmp f:PAQ_A
    bcc no_avanza
    sta f:PAQ_A                 ; el hueco que sigue empieza detrás
no_avanza:
    inx
    inx
    bra hueco
al_final:
    lda #ARAM_FIN
    sec
    sbc f:PAQ_A
    bcc no_entra
    cmp f:PAQ_LARGO
    bcs aca
no_entra:
    sep #$20
.a8
    lda #1
    sta f:PAQ_INCOMPLETO        ; que el próximo `PlayBGM` lo complete
    rts                         ; no entra: no suena
.a16
aca:
    ; Entra en PAQ_A, delante del ocupado X: se hace lugar en la lista.
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    ; Y se anota dónde va, y que falta subirla.
    lda f:PAQ_S
    and #$00FF
    tax
    sep #$20
.a8
    lda #3
    sta f:FAR_QUIERE, x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:PAQ_A
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    rts
.endproc

; Sube las muestras que `colocar_muestra` anotó con 3, cada una a su lugar, y
; les escribe la entrada del directorio.
.proc subir_colocadas
.a8
.i16
    ldx #0
otra:
    lda f:FAR_QUIERE, x
    cmp #3
    bne sigue
    phx
    txa
    sta f:PAQ_S
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sta f:PAQ_A
    sep #$20
.a8
    lda f:PAQ_S
    jsr fila_de_muestra
    jsr subir_muestra
    jsr escribir_directorio
    plx
sigue:
    inx
    cpx #MUESTRAS_N
    bcc otra
    rts
.endproc

; Las muestras del tema A: X al principio de su lista en `tema_muestras`.
.proc lista_del_tema
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tema_muestras, x
    tax
    sep #$20
.a8
    rts
.endproc

; Acomoda las muestras del tema A.
.proc colocar_tema
.a8
.i16
    jsr lista_del_tema
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr colocar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; C en 1 si el tema A va a sonar por el MSU-1 y no por el SPC700: hay MSU-1,
; el tema tiene pista y esa pista no faltó nunca. Ésas son muestras que el
; paquete no sube, porque con pista el SPC700 no toca la música —ver
; `music_start`—: la carga es más corta y la ARAM queda para los efectos. Sin
; MSU-1 contesta siempre que no, y el paquete es el de siempre.
;
; **Contar con la pista es una apuesta**, porque la ROM no sabe si está en la
; tarjeta hasta que la pide. Si falta, `msu_arrancar` prende su bit en
; MSU_FALTA y `music_start` cae a `tema_asegurar`, que ve las muestras sin
; subir y rearma el paquete con el tema adelante: esa vez congela lo que tarde
; en subir, y de ahí en más este tema ya no se saltea. Por lo mismo, el tema
; extra de `paquete_cargar_ya` no pasa por acá: es el que se está pidiendo.
;
; Guarda A, X e Y: los lazos del paquete llevan el índice en X y `marcar_tema`
; la marca en Y.
.proc tema_por_msu
.a8
.i16
    pha
    lda f:MSU_HAY
    beq no
    lda 1, s
    cmp #TEMA_TOTAL
    bcs no
    phx
    phy
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tema_msu, x
    cmp #$FF
    beq no_xy                   ; no tiene pista
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    tax                         ; su byte de MSU_FALTA
    lda 5, s                    ; el tema, detrás de Y y de X
    and #$0007
    tay                         ; y su bit
    sep #$20
.a8
    lda f:MSU_FALTA, x
correr:
    dey
    bmi corrido
    lsr a
    bra correr
corrido:
    and #1
    bne no_xy                   ; la pista faltó: suena por el SPC700
    ply
    plx
    pla
    sec
    rts
no_xy:
    ply
    plx
no:
    pla
    clc
    rts
.endproc

; `marcar_tema` y `colocar_tema` para los temas de la lista del paquete, que
; se saltean los que van a sonar por el MSU-1.
.proc marcar_tema_del_paquete
.a8
.i16
    jsr tema_por_msu
    bcs listo
    jmp marcar_tema
listo:
    rts
.endproc

.proc colocar_tema_del_paquete
.a8
.i16
    jsr tema_por_msu
    bcs listo
    jmp colocar_tema
listo:
    rts
.endproc

; Calla los efectos de sonido que estén sonando: sus muestras se van a mover.
.proc se_callar
.a8
.i16
    php
    sei
    lda #0
    sta f:SE_CUADROS
    sta f:SE_CUADROS + 1
    sta f:SE_PENDIENTE
    sta f:SE_BAJAR
    sta f:SE2_CUADROS
    sta f:SE2_CUADROS + 1
    sta f:SE2_PENDIENTE
    sta f:SE2_BAJAR
    lda #1
    sta f:SE_DEVOLVER           ; la música recupera las voces
    sta f:SE2_DEVOLVER
    lda #(SE_BIT | SE2_BIT)
    ldx #SE_KOF
    jsr dsp_par
    plp
    rts
.endproc

; El paquete de `mapa_actual`: ver arriba. PAQ_EXTRA es un tema que va antes
; que los del mapa —el que un `PlayBGM` pide y no estaba—, o $FF.
;
; El mapa sale de `mapa_actual` y no de A desde que el índice es de dieciséis
; bits: los tres que llamaban acá le pasaban `mapa_actual` en A, así que no se
; perdió ningún caso y el que llama no tiene que acordarse del ancho.
.proc paquete_cargar
.a8
.i16
    rep #$20
.a16
    lda mapa_actual
    sta f:PAQ_MAPA
    sep #$20
.a8
    jmp paquete_cargar_ya
.endproc

; Y el paquete cuyo índice ya está escrito en `PAQ_MAPA`, que es por donde
; entra la pelea: el suyo no es el de ningún mapa —va detrás de todos, ver
; `BA_PAQUETE`— así que no puede salir de `mapa_actual`.
;
; Existe porque acá hubo un error que ningún conflicto de git marcó: cuando el
; índice pasó a dieciséis bits, `paquete_cargar` dejó de leer el paquete de A
; para leerlo de `mapa_actual`, y `batalla_audio_cargar` —que venía de la otra
; rama— siguió pasándoselo en A. Las dos ramas mergearon limpio porque tocaban
; líneas distintas, y desde entonces la pelea cargaba el paquete del mapa: el
; tema de batalla sonaba con seis muestras sin subir y el golpe erraba con la
; muestra 0. Lo cobraron las dos pruebas de audio de `test_batalla.py`.
.proc paquete_cargar_ya
.a8
.i16
    lda f:APU_LISTO
    bne listo_apu
    rts                         ; en el reset, antes de que corra el driver
listo_apu:
    lda #0
    sta f:PAQ_INCOMPLETO
    sta f:PAQ_COMPACTAR
    jsr se_callar
    ldx #0
limpiar:
    lda #0
    sta f:FAR_QUIERE, x
    inx
    cpx #MUESTRAS_N
    bcc limpiar
    ; Las del tema que suena no se mueven: 2.
    lda music_apagada
    bne sin_fijas
    lda tema_actual
    cmp #TEMA_TOTAL
    bcs sin_fijas
    ldy #2
    jsr marcar_tema
sin_fijas:
    ; Las que el paquete quiere: 1, si no eran ya 2. Las del extra **aunque
    ; tenga pista**: si se pide es porque va a sonar por el SPC700. Las de los
    ; temas del paquete, no si van a sonar por el MSU-1: ver `tema_por_msu`.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra
    ldy #1
    jsr marcar_tema
sin_extra:
    ; Un tema de salida que pide su `PlayBGM` va solo: nada más del paquete
    ; se queda. Ver `extra_de_salida`.
    jsr extra_de_salida
    bcc con_paquete
    jmp marcadas
con_paquete:
    jsr lista_del_paquete
temas_q:
    lda f:paquetes, x
    cmp #$FF
    beq efectos_q
    phx
    ldy #1
    jsr marcar_tema_del_paquete
    plx
    inx
    bra temas_q
efectos_q:
    inx
otro_q:
    lda f:paquetes, x
    cmp #$FF
    beq salida_q
    phx
    ldy #1
    jsr marcar_muestra
    plx
    inx
    bra otro_q
salida_q:
    ; Y los temas de salida, que se quieren igual: si ya estaban, quedan.
    inx
otro_s:
    lda f:paquetes, x
    cmp #$FF
    beq marcadas
    phx
    ldy #1
    jsr marcar_tema_del_paquete
    plx
    inx
    bra otro_s
marcadas:
    ; Las que nadie quiere se olvidan, y con las que quedan se arma la lista
    ; de lo ocupado, en orden: es donde `colocar_muestra` busca los huecos.
    rep #$20
.a16
    lda #0
    sta f:INT_N
    sep #$20
.a8
    ldx #0
olvidar:
    lda f:FAR_QUIERE, x
    phx
    rep #$20
.a16
    pha
    txa
    asl a
    tax
    pla
    and #$00FF
    bne quiere
    sta f:FAR_ARAM_DE, x        ; nadie la quiere: afuera
    bra proxima
quiere:
    lda f:FAR_ARAM_DE, x
    beq proxima                 ; la quieren pero no está: la sube el paso que sigue
    sta f:PAQ_A
    txa
    lsr a
    sep #$20
.a8
    jsr fila_de_muestra
    rep #$20
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    jsr intervalo_ordenado
proxima:
    sep #$20
.a8
    plx
    inx
    cpx #MUESTRAS_N
    bcc olvidar
    ; Y se acomodan las que faltan, en orden de prioridad: el tema extra, los
    ; del mapa y sus efectos.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra2
    jsr colocar_tema
sin_extra2:
    jsr extra_de_salida
    bcc con_paquete2
    jmp colocadas
con_paquete2:
    jsr lista_del_paquete
temas:
    lda f:paquetes, x
    cmp #$FF
    beq efectos
    phx
    jsr colocar_tema_del_paquete
    plx
    inx
    bra temas
efectos:
    inx
otro_efecto:
    lda f:paquetes, x
    cmp #$FF
    beq de_salida
    phx
    jsr colocar_muestra
    plx
    inx
    bra otro_efecto
de_salida:
    ; Los temas de salida, detrás de todo y **si hay lugar**: que no entren
    ; no deja el paquete incompleto —no hace falta su `PlayBGM` para
    ; completarlo, ni rearmar todo desde cero—, porque su `PlayBGM` los sube
    ; solos. Por eso PAQ_INCOMPLETO se guarda y se repone alrededor.
    inx
    lda f:PAQ_INCOMPLETO
    pha
otro_de_salida:
    lda f:paquetes, x
    cmp #$FF
    beq salida_puesta
    phx
    jsr colocar_tema_del_paquete
    plx
    inx
    bra otro_de_salida
salida_puesta:
    pla
    sta f:PAQ_INCOMPLETO
colocadas:
    ; **Si algo no entró, se acomoda todo de nuevo desde cero**, salvo las
    ; del tema que suena, y recién después se sube. Las que el paquete quiere
    ; y ya estaban se quedan donde estaban, que es lo que hace barato un
    ; cambio de mapa que comparte muestras con el anterior; pero con el
    ; presupuesto por paquete cada uno llena la ARAM casi entera, y esos
    ; huecos alcanzaban para dejar afuera muestras de un paquete que entra
    ; solo: volviendo de una pelea, o de un mapa a otro con la música
    ; callada. Por eso se decide primero dónde va cada una y se sube al
    ; final: rehacer la subida entera costaría el doble de cuadros.
    lda f:PAQ_INCOMPLETO
    beq subir
    lda f:PAQ_COMPACTAR
    bne subir                   ; ya se rehízo: es el tema que suena
    lda #1
    sta f:PAQ_COMPACTAR
    lda #0
    sta f:PAQ_INCOMPLETO
    ldx #0
compactar:
    lda f:FAR_QUIERE, x
    cmp #2
    beq quieta                  ; las del tema que suena no se mueven
    cmp #0
    beq quieta                  ; y las que nadie quiere ya se olvidaron
    lda #1
    sta f:FAR_QUIERE, x
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    plx
quieta:
    inx
    cpx #MUESTRAS_N
    bcc compactar
    jmp marcadas
subir:
    jsr subir_colocadas
    ; Con un tema de salida subido solo, lo demás del paquete se soltó: si la
    ; página no se va del mapa, el próximo `PlayBGM` lo completa.
    jsr extra_de_salida
    bcc listo
    lda #1
    sta f:PAQ_INCOMPLETO
listo:
    rts
.endproc

; C en 1 si PAQ_EXTRA es uno de los temas de salida del paquete de PAQ_MAPA:
; la tercera lista de `paquetes`. Son los que el mapa prende sólo para irse
; —ver `Temas.de_salida` en tools/port/eventos.py—, y el caso del juego es
; `lufsorr` en el mapa 3: suena después de la secuencia de efectos, así que
; no tiene por qué caber con ellos, y el conversor le da la tasa de un tema
; solo. Cuando su `PlayBGM` lo pide y no está, se sube **él solo**, soltando
; lo demás, y no el paquete entero con él adelante: eso último no entraría,
; y rearmarlo desde cero sería subir la ARAM entera.
.proc extra_de_salida
.a8
.i16
    lda f:PAQ_EXTRA
    cmp #$FF
    beq no
    jsr lista_del_paquete
temas:
    lda f:paquetes, x
    inx
    cmp #$FF
    bne temas
efectos:
    lda f:paquetes, x
    inx
    cmp #$FF
    bne efectos
salida:
    lda f:paquetes, x
    cmp #$FF
    beq no
    cmp f:PAQ_EXTRA
    beq si
    inx
    bra salida
si:
    sec
    rts
no:
    clc
    rts
.endproc

; X al principio de la lista del paquete de PAQ_MAPA.
.proc lista_del_paquete
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:paquetes, x
    tax
    sep #$20
.a8
    rts
.endproc

; La muestra A, marcada con Y en FAR_QUIERE si no tenía algo mayor.
.proc marcar_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    tya
    cmp f:FAR_QUIERE, x
    bcc listo
    sta f:FAR_QUIERE, x
listo:
    rts
.endproc

; Las muestras del tema A, marcadas con Y.
.proc marcar_tema
.a8
.i16
    phy
    jsr lista_del_tema
    ply
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr marcar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; Agrega a la lista de lo ocupado el intervalo [PAQ_A, PAQ_A + PAQ_LARGO),
; en orden. A de dieciséis.
.proc intervalo_ordenado
.a16
.i16
    ldx #0
buscar:
    txa
    cmp f:INT_N
    bcs lugar
    lda f:INT_INI, x
    cmp f:PAQ_A
    bcs lugar                   ; éste empieza después: va delante
    inx
    inx
    bra buscar
lugar:
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    rts
.endproc

; Antes de prender el tema A: si le falta alguna muestra, se calla la música,
; se suelta todo y se rearma el paquete del mapa con él adelante. Pasa con un
; `PlayBGM` de un tema que el mapa no traía —el del título, o uno de un evento
; común— y congela la imagen lo que tarde en subir.
;
; Y lo mismo si el paquete del mapa **quedó incompleto**, aunque al tema no le
; falte nada. Pasa al entrar a un mapa con el tema de otro sonando: sus
; muestras no se mueven —ver `paquete_cargar_ya`— y lo que no entra al lado
; es lo último del paquete, los efectos. El caso del juego es el paso del
; mapa 2 al 3, que se hace con el tema del 2 sonando y dejaba afuera algunos
; efectos del 3 hasta el próximo cambio de mapa, aunque su página prendiera
; enseguida su propio tema. Un `PlayBGM` arranca el tema de cero y calla lo que sonaba, así que
; es el primer momento en que esas muestras se pueden soltar: se rearma, y
; sube sólo lo que faltaba. Si el paquete no entra ni así, el rearmado no
; sube nada y cuesta menos de un cuadro.
.proc tema_asegurar
.a8
.i16
    sta temp + 1
    lda f:APU_LISTO
    beq listo
    lda temp + 1
    cmp #TEMA_TOTAL
    bcs listo
    lda f:PAQ_INCOMPLETO
    bne falta                   ; aunque al tema no le falte nada
    lda temp + 1                ; el tema: `lista_del_tema` lo lee de A
    jsr lista_del_tema
mirar:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo                   ; están todas
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    plx
    cmp #0                      ; **la Z de acá la pone `plx`, no el `lda`**:
                                ; PLX deja N y Z del valor que saca de la pila,
                                ; que es el índice de la lista y nunca es cero.
                                ; Sin este `cmp` la respuesta era siempre
                                ; "están todas" y el tema del título sonaba
                                ; contra un directorio de silencios. Es de
                                ; dieciséis bits, como la dirección: el mismo
                                ; cuidado que `op_sound` se toma con `xba`.
    sep #$20
.a8
    beq falta
    inx
    bra mirar
falta:
    php
    sei
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; todas las voces sueltan
    plp
    lda temp + 1
    sta f:PAQ_EXTRA
    jsr paquete_cargar
    lda #$FF
    sta f:PAQ_EXTRA
listo:
    rts
.endproc

