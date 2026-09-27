.segment "FAR"

; --- los efectos de sonido con MSU-1 ------------------------------------------
;
; Con MSU-1 el tema suena por su pista y el SPC700 no toca música, así que los
; efectos de sonido pueden tener lo que era de ella. Son dos cosas, y **sin
; MSU-1 ninguna de las dos hace nada**: `MSU_HAY` en cero apaga las dos, y lo
; que queda es lo de siempre —las voces 7 y 6, los efectos de la ROM—.
;
; **Las voces 0 a 5.** Mientras el SPC700 no toca música —hay MSU-1 y
; `music_apagada` está prendido: suena una pista, o nada—, un efecto que no
; entra en la 7 ni en la 6 toma una de ésas. En RM2k los efectos se suman, y
; la escena de `evilrhys` del mapa 3 tiene un momento con tres a la vez. Su
; estado vive en `EX_*` (ram_lejana.s), más chico que el de la 7 y la 6: en
; vez de la copia de la fila de `sonido_tabla`, su índice, y la interrupción
; la lee al arrancarlo.
;
; Si un tema empieza a sonar por el SPC700 mientras un efecto suena en una de
; ésas —una pista que falta, o un `PlayBGM` de un tema sin pista—, **el efecto
; sigue**: lo que la música le escribe a esa voz queda en MUS_SOMBRA y no se
; manda (`dsp_musica`), y al terminar el efecto se le devuelve desde ahí
; (`se_extras_antes`). Es lo mismo que pasa con la 7 y la 6, sólo que la
; sombra es la de la música y no una propia: no había RAM para seis más.
;
; **Los efectos de calidad del `.msu`.** Si el `.msu` es el de este cartucho
; —la firma, `msu_datos_validos`—, los efectos de cada paquete se suben a la
; ARAM desde ahí y no desde la ROM: enteros, y a la tasa que les entra ahora
; que la música no ocupa lugar. Cada paquete tiene su versión de cada efecto
; —la tasa depende de cuánto pesa el paquete, ver tools/audio/efectos_msu.py—
; y la ROM no guarda qué versión quedó en la ARAM, así que **en cada paquete
; se vuelven a subir todos**, aunque ya estuvieran. La altura de cada sonido
; sale de `se_msu_altura`, que el conversor arma por paquete, y no de
; `sonido_tabla`. Con otro `.msu`, o sin él, todo sale de la ROM como
; siempre.
;
; Vive en el banco 1 porque el banco 0 no tiene lugar: se llega con `jsl`, y
; lo que se lee o escribe va con `f:`, así que el banco de datos no importa.
; Lo que corre adentro de `irq_musica` —`se_extras_antes` y
; `se_extras_despues`— no usa `temp`, por lo mismo que no lo usa
; `efectos_de_sonido.s`.

EX_VOCES = 6                    ; de la 0 a la 5
.assert SE_BIT = $80 && SE2_BIT = $40, error, "las voces de efectos de siempre dejaron de ser la 7 y la 6"

; El bit de cada voz, y el de la voz de cada registro del DSP: el de las voces
; 0 a 5 en sus registros 0 a 7 y cero en el resto, para que `dsp_musica`
; pregunte con un solo `and`.
ex_bit:
    .byte $01, $02, $04, $08, $10, $20
ex_bit_de_registro:
.repeat 128, r
  .if (r >> 4) < EX_VOCES && (r & $0F) < 8
    .byte 1 << (r >> 4)
  .else
    .byte 0
  .endif
.endrepeat

; Todo en cero, en el reset: la RAM lejana arranca con basura en bsnes.
.proc se_extras_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:EX_CUADROS, x
    inx
    cpx #(EX_FIN - EX_CUADROS)
    bcc otro
    rtl
.endproc

; C en 1 si las voces 0 a 5 son de los efectos: hay MSU-1 y el SPC700 no toca
; música.
.proc ex_permitidas
.a8
.i16
    lda f:MSU_HAY
    beq no
    lda f:music_apagada
    beq no
    sec
    rts
no:
    clc
    rts
.endproc

; La muestra del efecto de la voz cuyo doble trae X, en A. Se lleva X.
.proc ex_srcn
.a8
.i16
    rep #$20
.a16
    lda f:EX_IDX, x
    pha
    asl a
    asl a
    asl a
    sec
    sbc 1, s                    ; por siete
    tax
    pla
    sep #$20
.a8
    lda f:sonido_tabla, x
    rts
.endproc

; El efecto de índice A, de dieciséis bits, a la voz Y. Vuelve con A de ocho.
.proc ex_tomar
.a16
.i16
    pha
    tya
    asl a
    tax
    pla
    sta f:EX_IDX, x
    sep #$20
.a8
    tyx
    lda f:ex_bit, x
    pha
    ora f:EX_PEND
    sta f:EX_PEND
    lda 1, s
    ora f:EX_OCUP
    sta f:EX_OCUP
    ; Si se estaba devolviendo, ya no: pasa derecho al efecto nuevo.
    pla
    eor #$FF
    and f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    rts
.endproc

; Para `sonido_tocar`, con las interrupciones cortadas: si una de las voces 0
; a 5 está tocando la misma muestra que el efecto de índice A —de dieciséis
; bits— y fila X, se lo da a ésa, como la 7 y la 6 hacen con la lluvia. C en
; 1 si lo tomó. Vuelve con A de ocho, y con X como vino.
.proc se_extra_misma
.a16
.i16
    phx
    pha                         ; [índice][fila]
    sep #$20
.a8
    jsr ex_permitidas
    bcc no
    lda f:sonido_tabla, x
    pha                         ; [srcn][índice][fila]
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_OCUP
    beq sigue
    rep #$20
.a16
    tya
    asl a
    tax
    sep #$20
.a8
    jsr ex_srcn
    cmp 1, s
    beq tomar
sigue:
    iny
    cpy #EX_VOCES
    bcc otra
    pla
no:
    rep #$20
.a16
    pla
    plx
    sep #$20
.a8
    clc
    rtl
tomar:
    pla
    rep #$20
.a16
    pla
    jsr ex_tomar
.a8
    plx
    sec
    rtl
.endproc

; Y si la 7 y la 6 están ocupadas, una de las voces 0 a 5 que esté libre.
.proc se_extra_libre
.a16
.i16
    phx
    pha
    sep #$20
.a8
    jsr ex_permitidas
    bcc no
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_OCUP
    beq tomar
    iny
    cpy #EX_VOCES
    bcc otra
no:
    rep #$20
.a16
    pla
    plx
    sep #$20
.a8
    clc
    rtl
tomar:
    rep #$20
.a16
    pla
    jsr ex_tomar
.a8
    plx
    sec
    rtl
.endproc

; La altura del sonido de índice A —dieciséis bits— con la versión del `.msu`
; del paquete que está en la ARAM, o 0 si su efecto no es de ese paquete. Z
; según la altura. Se lleva X.
.proc altura_msu
.a16
.i16
    asl a
    pha
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:se_msu_altura_paq, x
    clc
    adc 1, s
    tax
    pla
    lda f:se_msu_altura, x
    rts
.endproc

; Para `sonido_tocar`, después de copiar el pendiente de la voz cuyo
; desplazamiento trae X: con los efectos del `.msu`, la altura de su versión.
; A trae el índice, de dieciséis bits. Vuelve con A de ocho.
.proc se_msu_altura_poner
.a16
.i16
    phx
    pha                         ; [índice][desplazamiento]
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    rep #$20
.a16
    bne listo
    lda 1, s
    jsr altura_msu
    beq listo
    tay
    lda 3, s
    tax
    tya
    sta f:SE_NUEVO + 1, x       ; la altura baja y la alta
listo:
    pla
    plx
    sep #$20
.a8
    rtl
.endproc

; --- adentro de `irq_musica` ------------------------------------------------

; Antes de la música: las voces cuyo efecto terminó en el cuadro anterior
; vuelven a ser de ella. KOF como la música lo tenía, salvo lo que siga
; ocupado, y sus ocho registros desde MUS_SOMBRA, que es lo que el stream les
; escribió mientras tanto.
.proc se_extras_antes
.a8
.i16
    lda f:EX_DEVOLVER
    bne hay
    rtl
hay:
    eor #$FF
    and f:EX_OCUP
    sta f:EX_OCUP
    jsl se_kof_musica_l
    ldx #SE_KOF
    jsl dsp_par_l
    ldy #0
voz:
    tyx
    lda f:ex_bit, x
    and f:EX_DEVOLVER
    beq sigue
    tya
    asl a
    asl a
    asl a
    asl a
    rep #$20
.a16
    and #$00FF
    tax                         ; su primer registro
    sep #$20
.a8
registro:
    lda f:MUS_SOMBRA, x
    jsl dsp_par_l
    inx
    txa
    and #$07
    bne registro
sigue:
    iny
    cpy #EX_VOCES
    bcc voz
    lda #0
    sta f:EX_DEVOLVER
    rtl
.endproc

; Después de la música: arrancar los pendientes, y contar los que suenan y
; apagar los que terminan. Vuelve con A en los bits de las voces que hay que
; disparar: el disparo lo hace `se_despues`, una sola vez para todas.
;
; **Un solo KOF para los que terminan, y después de los que arrancan**: cada
; KOF pisa al anterior, y si dos caen antes de que el DSP lo lea, el primero
; no existió. El que arranca escribe el de la música sin las voces ocupadas;
; si el que termina escribiera antes, el suyo se perdería, y un efecto de la
; ROM con bucle seguiría sonando.
.proc se_extras_despues
.a8
.i16
    lda f:EX_OCUP
    bne hay
    rtl                         ; A en cero: nada que disparar
hay:
    lda f:EX_PEND
    pha                         ; [los que arrancan]
    beq contar_todas
    lda #0
    sta f:EX_PEND
    jsl se_kof_musica_l
    ldx #SE_KOF
    jsl dsp_par_l
    ldy #0
arrancar:
    tyx
    lda f:ex_bit, x
    and 1, s
    beq no_arranca
    jsr ex_arrancar
no_arranca:
    iny
    cpy #EX_VOCES
    bcc arrancar
    lda #1
    sta f:SE_BAJAR              ; el cuadro que viene se baja el disparo
contar_todas:
    lda #0
    pha                         ; [los que terminan][los que arrancan]
    ldy #0
contar:
    tyx
    lda f:ex_bit, x
    and 2, s
    bne sigue                   ; recién arrancado: se cuenta desde el que viene
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:EX_CUADROS, x
    beq nada
    dec a
    sta f:EX_CUADROS, x
    bne nada
    sep #$20
.a8
    tyx
    lda f:ex_bit, x
    ora 1, s
    sta 1, s
    bra sigue
.a16
nada:
    sep #$20
.a8
sigue:
    iny
    cpy #EX_VOCES
    bcc contar
    pla                         ; los que terminan
    beq ninguno
    pha
    ora f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    jsl se_kof_musica_l
    ora 1, s
    ldx #SE_KOF
    jsl dsp_par_l
    pla
ninguno:
    pla                         ; los que arrancan: el disparo
    rtl
.endproc

; Arranca el efecto de la voz Y: su muestra, su altura, su volumen y la
; envolvente, y sus cuadros. No toca Y.
.proc ex_arrancar
.a8
.i16
    phy
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:EX_IDX, x
    pha                         ; [índice][voz]
    asl a
    asl a
    asl a
    sec
    sbc 1, s
    tax                         ; su fila
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    rep #$20
.a16
    bne de_la_tabla
    lda 1, s
    phx
    jsr altura_msu
    plx
    cmp #0                      ; `plx` deja Z de X, no de la altura
    bne tengo
de_la_tabla:
    lda f:sonido_tabla + 1, x
tengo:
    sta 1, s                    ; [altura][voz]
    lda f:sonido_tabla + 5, x
    pha                         ; [cuadros][altura][voz]
    sep #$20
.a8
    lda f:sonido_tabla + 0, x   ; SRCN
    pha
    lda f:sonido_tabla + 3, x   ; VOLL
    pha
    lda f:sonido_tabla + 4, x   ; VOLR
    pha                         ; [volr][voll][srcn][cuadros][altura][voz]
    lda 8, s                    ; la voz
    asl a
    asl a
    asl a
    asl a
    rep #$20
.a16
    and #$00FF
    tax                         ; su primer registro
    sep #$20
.a8
    pla
    inx
    jsl dsp_par_l               ; VOLR
    dex
    pla
    jsl dsp_par_l               ; VOLL
    inx
    inx
    inx
    lda 5, s
    jsl dsp_par_l               ; la altura alta
    dex
    lda 4, s
    jsl dsp_par_l               ; y la baja
    inx
    inx
    pla
    jsl dsp_par_l               ; SRCN
    inx
    lda #$FF                    ; ADSR prendido, ataque y caída al máximo
    jsl dsp_par_l
    inx
    lda #$E0                    ; sostenido al máximo y sin caer
    jsl dsp_par_l
    lda 5, s                    ; la voz, detrás de [cuadros][altura]
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    pla
    sta f:EX_CUADROS, x
    pla                         ; la altura
    sep #$20
.a8
    ply
    rts
.endproc

; --- los efectos del `.msu`, al cargar el paquete ---------------------------

; Al empezar cada paquete: si todavía no se sabe, si el `.msu` es el de este
; cartucho —una vez por encendido: el archivo no cambia—; y si lo es, los
; efectos se olvidan todos, para que el paquete los vuelva a subir con su
; versión. Ver arriba.
.proc se_msu_preparar
.a8
.i16
    lda f:MSU_SE
    bne mirado
    jsr msu_datos_validos
    cmp #1
    beq valido
    lda #2
valido:
    sta f:MSU_SE
mirado:
    cmp #1
    bne listo
    ldx #(2 * SE_PRIMERA)
    lda #0
olvidar:
    cpx #(2 * MUESTRAS_N)
    bcs olvidados
    sta f:FAR_ARAM_DE, x
    inx
    bra olvidar
olvidados:
    lda #$FF                    ; el flujo, en ningún lado: la primera busca
    sta f:MSU_SE_SIG
    sta f:MSU_SE_SIG + 1
    sta f:MSU_SE_SIG + 2
listo:
    rtl
.endproc

; La fila de `se_msu_filas` del efecto de muestra A en el paquete de
; PAQ_MAPA, en X, y C en 1; C en 0 si el paquete no lo lleva. Cada paquete
; tiene una fila por efecto de su lista en `paquetes`, en el mismo orden. No
; toca Y.
.proc se_msu_fila
.a8
.i16
    phy
    pha                         ; [srcn]
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:paquetes, x           ; como `lista_del_paquete`
    tax
    sep #$20
.a8
temas:
    lda f:paquetes, x
    inx
    cmp #$FF
    bne temas
    ldy #0                      ; la fila, de a ocho
efectos:
    lda f:paquetes, x
    cmp #$FF
    beq no
    cmp 1, s
    beq si
    inx
    rep #$20
.a16
    tya
    clc
    adc #8
    tay
    sep #$20
.a8
    bra efectos
si:
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    tya
    clc
    adc f:se_msu_paq, x
    tax
    sep #$20
.a8
    pla
    ply
    sec
    rts
no:
    pla
    ply
    clc
    rts
.endproc

; Para `colocar_muestra`, con A de dieciséis: si la muestra PAQ_S es un
; efecto que va a salir del `.msu`, PAQ_LARGO es lo que mide allá.
.proc se_msu_largo
.a16
.i16
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PAQ_S
    cmp #SE_PRIMERA
    bcc no
    jsr se_msu_fila
    bcc no
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PAQ_LARGO
    rtl
no:
    rep #$20
.a16
    rtl
.endproc

; Para `subir_colocadas`: si la muestra PAQ_S es un efecto que va a salir del
; `.msu`, la sube de ahí a PAQ_A y escribe su entrada del directorio, y
; vuelve con C en 1. Si no, C en 0 y la sube la ROM.
;
; Los efectos de un paquete están en el `.msu` uno detrás del otro, en el
; orden en que se suben, así que se busca sólo si el flujo no quedó ya donde
; va: una vez por paquete. Buscar le cuesta a Mednafen uno o dos cuadros; ver
; `msu_datos_buscar`. Si la búsqueda no llega a tiempo, el efecto no se sube
; y no suena —su lugar queda reservado igual—: la ROM no tiene cómo caer a su
; versión, que tiene otra altura.
.proc se_msu_subir
.a8
.i16
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PAQ_S
    cmp #SE_PRIMERA
    bcc no
    jsr se_msu_fila
    bcs hay
no:
    clc
    rtl
hay:
    lda f:se_msu_filas, x
    cmp f:MSU_SE_SIG
    bne buscar
    lda f:se_msu_filas + 1, x
    cmp f:MSU_SE_SIG + 1
    bne buscar
    lda f:se_msu_filas + 2, x
    cmp f:MSU_SE_SIG + 2
    beq en_su_lugar
buscar:
    phx
    rep #$20
.a16
    lda f:se_msu_filas + 2, x
    tay
    lda f:se_msu_filas, x
    jsr msu_datos_buscar        ; vuelve con A de ocho
.a8
    plx
    bcc en_su_lugar
    lda #$FF
    sta f:MSU_SE_SIG
    sta f:MSU_SE_SIG + 1
    sta f:MSU_SE_SIG + 2
    rep #$20
.a16
    lda f:PAQ_S
    and #$00FF
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    sec
    rtl
en_su_lugar:
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PAQ_LARGO
    clc
    adc f:se_msu_filas, x
    sta f:MSU_SE_SIG            ; donde va a quedar
    sep #$20
.a8
    lda f:se_msu_filas + 2, x
    adc #0
    sta f:MSU_SE_SIG + 2
    phx
    jsr msu_a_aram
    plx
    jsr msu_directorio
    sec
    rtl
.endproc

; PAQ_LARGO bytes del flujo del `.msu` a la ARAM, desde PAQ_A. Es
; `subir_muestra` con otro origen: de a ternas por el comando 3 del driver,
; en tandas de hasta 85 con las interrupciones cortadas, y lo que sobra de a
; un byte. La terna que sigue se lee mientras el SPC700 guarda la anterior.
.proc msu_a_aram
.a8
.i16
    ldy #0                      ; lo subido
tanda:
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
    cmp #3
    bcs hay_ternas
    jmp resto
hay_ternas:
    ldx #85                     ; el índice del driver es de un byte
    cmp #255
    bcs cuantas
    ldx #0
dividir:
    cmp #3
    bcc cuantas
    sbc #3                      ; C prendido por el `cmp`
    inx
    bra dividir
cuantas:
    sep #$20
.a8
    jsr msu_apuntar
    php
    sei
    txa
    sta f:APUIO0
    lda #3
    sta f:APUIO2
    inc token
    lda token
    sta f:APUIO3
acuse_bloque:
    cmp f:APUIO3
    bne acuse_bloque
    lda f:MSU_DATOS
    sta temp
    lda f:MSU_DATOS
    sta temp + 1
    lda f:MSU_DATOS
    sta temp + 3
terna:
    lda temp
    sta f:APUIO0
    lda temp + 1
    sta f:APUIO1
    lda temp + 3
    sta f:APUIO2
    inc token
    lda token
    sta f:APUIO3
    iny
    iny
    iny
    dex
    beq ultima
    lda f:MSU_DATOS
    sta temp
    lda f:MSU_DATOS
    sta temp + 1
    lda f:MSU_DATOS
    sta temp + 3
    lda token
acuse:
    cmp f:APUIO3
    bne acuse
    bra terna
ultima:
    lda token
acuse_ultima:
    cmp f:APUIO3
    bne acuse_ultima
    lda #0
    sta f:APUIO2
    plp
    jmp tanda
.a16
resto:
    sep #$20
.a8
    ; Lo que falta, 0, 1 o 2, de a un byte: el puntero ya está donde va.
    sta temp
    cmp #0                      ; `sta` no toca Z, y un efecto mide nueve
                                ; bytes por bloque: casi siempre es cero
    beq listo
    jsr msu_apuntar
un_byte:
    lda f:MSU_DATOS
    jsr msu_byte
    dec temp
    bne un_byte
listo:
    rts
.endproc

; La entrada del directorio de la muestra PAQ_S, ya subida a PAQ_A: vuelve
; al principio más lo que diga su fila X, que para un efecto entero es 0.
.proc msu_directorio
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
    lda f:se_msu_filas + 6, x
    clc
    adc f:PAQ_A
    sta temp
    sep #$20
.a8
    jsr msu_apuntar
    lda f:PAQ_A
    jsr msu_byte
    lda f:PAQ_A + 1
    jsr msu_byte
    lda temp
    jsr msu_byte
    lda temp + 1
    jmp msu_byte
.endproc

; `aram_apuntar`, `aram_byte` y `apu_testigo`, con los puertos en `f:`.
.proc msu_apuntar
.a8
.i16
    php
    sei
    lda #2
    sta f:APUIO2
    lda f:PAQ_DEST
    sta f:APUIO0
    lda f:PAQ_DEST + 1
    sta f:APUIO1
    jsr msu_testigo
    lda #0
    sta f:APUIO2
    plp
    rts
.endproc

.proc msu_byte
.a8
.i16
    php
    sei
    sta f:APUIO0
    lda #1
    sta f:APUIO2
    jsr msu_testigo
    lda #0
    sta f:APUIO2
    plp
    rts
.endproc

.proc msu_testigo
.a8
.i16
    inc token
    lda token
    sta f:APUIO3
espera:
    cmp f:APUIO3
    bne espera
    rts
.endproc

; Para `se_callar`, con las interrupciones cortadas: nada pendiente ni
; sonando en las voces 0 a 5, y en el cuadro que viene la música las
; recupera. Vuelve con A en sus bits, para el KOF de `se_callar`.
.proc se_extras_callar
.a8
.i16
    lda #0
    sta f:EX_PEND
    ldx #0
cuadros:
    sta f:EX_CUADROS, x
    inx
    cpx #(2 * EX_VOCES)
    bcc cuadros
    lda f:EX_OCUP
    ora f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    rtl
.endproc
