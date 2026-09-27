.segment "CODE"

; --- los efectos de sonido -------------------------------------------------------
;
; `PlaySound`, en dos voces que se le roban a la música mientras duran: SE_VOZ
; y SE2_VOZ, las que el reparto de la música llena primero con la percusión
; (`VOCES_DE_EFECTOS` en snes_music.py). Ver `build_efectos` allá. En
; RM2k los efectos se suman —EasyRPG tiene 31 canales—, y con una sola voz la
; lluvia de la apertura le cortaba el trueno a la mitad: medido, 73 de sus 144
; cuadros, y una vez 7. Con MSU-1 y el SPC700 sin música, además las voces 0 a
; 5: ver efectos_con_msu.s.
;
; El estado de cada voz vive en la RAM lejana, porque la página directa y la
; BSS están llenas. El de la segunda está SE2_DESPL más arriba, con la misma
; forma, así que `sonido_tocar` elige la voz con un desplazamiento:
;
;   SE_CUADROS   cuántos cuadros le quedan al efecto, dos bytes
;   SE_PENDIENTE hay uno pendiente de arrancar
;   SE_DEVOLVER  hay que devolverle la voz a la música en este cuadro
;   SE_BAJAR     hay que bajar el disparo de KON en este cuadro
;   SE_NUEVO     el pendiente: la muestra, la altura (dos), el volumen de
;                cada lado y los cuadros (dos), siete bytes. Después de
;                arrancar queda ahí, y así se sabe qué muestra suena
;   SE_SOMBRA    lo último que la música le escribió a los ocho registros de
;                la voz: con eso se le devuelve
;   SE_KOF_SOMBRA  lo último que la música escribió en KOF, uno para las dos
;
; La música sigue escribiéndole a cada voz mientras su efecto suena: se guarda
; en la sombra y no se manda, y a sus KON y KOF se les sacan los bits de las
; voces que tienen efecto (`se_mascara`).
;
; Todo esto corre adentro de `irq_musica`, así que **no usa la ventana de
; WMADD ni `temp`**: la interrupción cae en cualquier punto del código
; principal, y si ése estaba recorriendo la RAM lejana o usando `temp`, se lo
; pisaría. Se llega con el direccionamiento largo, que lleva el banco en la
; instrucción. Lo único que escribe acá el código principal es el pendiente,
; en `sonido_tocar`, y lo hace con las interrupciones cortadas.
FAR_SE       = $30A0
SE_CUADROS   = $7E0000 + FAR_SE
SE_PENDIENTE = SE_CUADROS + 2
SE_DEVOLVER  = SE_CUADROS + 3
SE_BAJAR     = SE_CUADROS + 4
SE_NUEVO     = SE_CUADROS + 5
SE_SOMBRA    = $7E0000 + $30B0
SE_KOF_SOMBRA = SE_SOMBRA + 8
; La segunda voz, en $3D00: el mapa de la RAM lejana de arriba termina en la
; pelea, que no pasa de $3CFF, y lo siguiente es `FAR_HAB`, en $6000. Usa
; $3D00 a $3D17.
SE2_DESPL    = $3D00 - FAR_SE
SE2_CUADROS  = SE_CUADROS + SE2_DESPL
SE2_PENDIENTE = SE_PENDIENTE + SE2_DESPL
SE2_DEVOLVER = SE_DEVOLVER + SE2_DESPL
SE2_BAJAR    = SE_BAJAR + SE2_DESPL
SE2_NUEVO    = SE_NUEVO + SE2_DESPL
SE2_SOMBRA   = SE_SOMBRA + SE2_DESPL
SE_BYTES     = 12               ; de SE_CUADROS a SE_NUEVO, inclusive
; SE_BIT y SE_REG —el bit de la voz en KON y KOF, y su primer registro— y
; los de la segunda los emite snes_music.py junto con SE_VOZ.
SE_KON     = $4C
SE_KOF     = $5C

; Z=0 si la voz tiene un efecto sonando, pendiente o devolviéndose. No toca B.
.proc se_ocupada
.a8
.i16
    lda f:SE_CUADROS
    ora f:SE_CUADROS + 1
    ora f:SE_PENDIENTE
    ora f:SE_DEVOLVER
    rts
.endproc

.proc se2_ocupada
.a8
.i16
    lda f:SE2_CUADROS
    ora f:SE2_CUADROS + 1
    ora f:SE2_PENDIENTE
    ora f:SE2_DEVOLVER
    rts
.endproc

; A: los bits de KON y KOF de las voces ocupadas. No toca B ni X.
.proc se_mascara
.a8
.i16
    jsr se_ocupada
    beq sin_7                   ; A quedó en cero
    lda #SE_BIT
sin_7:
    pha
    jsr se2_ocupada
    beq sin_6
    lda #SE2_BIT
sin_6:
    ora 1, s
    ora f:EX_OCUP               ; y las de las voces 0 a 5: ver efectos_con_msu.s
    sta 1, s
    pla                         ; Z según la máscara entera
    rts
.endproc

; `dsp_par` y `se_kof_musica` para `efectos_con_msu.s`, que vive en el banco 1
; y no puede llegar con `jsr`.
.proc dsp_par_l
    jsr dsp_par
    rtl
.endproc

.proc se_kof_musica_l
    jsr se_kof_musica
    rtl
.endproc

; A: lo que la música dejó en KOF, sin los bits de las voces ocupadas.
.proc se_kof_musica
.a8
.i16
    jsr se_mascara
    eor #$FF
    and f:SE_KOF_SOMBRA
    rts
.endproc

; Un par al DSP: X el registro, A el valor, y la espera del acuse del SPC700.
.proc dsp_par
.a8
.i16
    xba
    txa
    sta APUIO0
    xba
    sta APUIO1
    inc token
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; Una escritura del stream de la música: X el registro —de dieciséis bits, con
; la parte alta en cero—, A el valor. Si es de una voz de efecto, va a su
; sombra, y si la voz tiene efecto no se manda; KON y KOF salen sin los bits de
; las voces ocupadas. No toca Y ni V: `music_frame` lleva en Y el registro de
; la voz y en V si la nota se escribe sin mirar el caché.
.proc dsp_musica
.a8
.i16
    xba                         ; B = el valor
    lda f:MUS_BITACORA_SI
    beq sin_bitacora
    jsr bitacora
sin_bitacora:
    txa
    and #$F0
    cmp #SE_REG
    beq voz_7
    cmp #SE2_REG
    beq voz_6
    bra no_voz
voz_7:
    txa
    and #$0F
    cmp #8
    bcs no_voz                  ; ENVX y OUTX no se escriben nunca
    ; La sombra se indexa con el registro entero, que ya está en X, y el valor
    ; no sale de B. Hasta el 2026-09-26 el índice se armaba en A con un
    ; `sep #$10` / `tax`, que le borraba la parte alta a Y; y antes, con un
    ; `and #$000F` de dieciséis bits que borraba B, y desde 854dba9 (la voz 7)
    ; y 8c9c182 (la 6) toda escritura de la música a las voces de la batería
    ; llegaba al DSP como cero. Lo cobra pruebas/rpgmaker/test_bateria_suena.py.
    xba
    sta f:SE_SOMBRA - SE_REG, x ; a la sombra
    xba                         ; B = el valor, para `enviar`
    jsr se_ocupada
    beq enviar
    rts                         ; la voz es del efecto
voz_6:
    txa
    and #$0F
    cmp #8
    bcs no_voz
    xba                         ; como en voz_7
    sta f:SE2_SOMBRA - SE2_REG, x
    xba
    jsr se2_ocupada
    beq enviar
    rts
no_voz:
    ; Las voces 0 a 5, si tienen un efecto —sólo con MSU-1, ver
    ; efectos_con_msu.s—: lo escrito queda en MUS_SOMBRA y no se manda, y
    ; cuando el efecto termina se le devuelve desde ahí. Sin efectos en ellas,
    ; un `lda` y un salto: la tabla lleva cero en todo lo que no es de ésas.
    lda f:EX_OCUP
    beq no_extra
    and f:ex_bit_de_registro, x
    beq no_extra
    rts                         ; la voz es del efecto
no_extra:
    txa
    cmp #SE_KOF
    bne no_kof
    ; KOF: a la sombra siempre, y sin los bits de las voces ocupadas.
    xba
    sta f:SE_KOF_SOMBRA
    xba
    bra mascara
no_kof:
    cmp #SE_KON
    bne enviar
mascara:
    jsr se_mascara
    beq enviar
    eor #$FF
    pha                         ; la máscara invertida
    xba
    and 1, s                    ; el valor sin esos bits
    xba
    pla
enviar:
    xba                         ; A = el valor, y X sigue con el registro
    jmp dsp_par
.endproc

; Anota en MUS_BITACORA el par que `dsp_musica` está por mandar: X el
; registro, B el valor. No toca X, Y, B ni V.
.proc bitacora
.a8
.i16
    xba
    pha                         ; el valor
    phx                         ; el registro, dos bytes
    ; **Primero el par y después el índice**: la prueba lee la bitácora entre
    ; dos cuadros del emulador, y un cuadro de música pesado sigue corriendo
    ; cuando el emulador entrega el suyo. Con el índice adelante, un corte
    ; justo en el medio le mostraba un par nuevo con los bytes de la vuelta
    ; anterior —pasó el 2026-09-26 con el de batalla, al correrse el código—.
    rep #$20
.a16
    lda f:MUS_BITACORA_I
    tax
    sep #$20
.a8
    lda 1, s                    ; el byte bajo del registro
    sta f:MUS_BITACORA, x
    lda 3, s                    ; el valor
    sta f:MUS_BITACORA + 1, x
    rep #$20
.a16
    txa
    inc a
    inc a
    and #MUS_BITACORA_LARGO - 1
    sta f:MUS_BITACORA_I
    sep #$20
.a8
    plx
    pla
    xba                         ; B = el valor, como vino
    rts
.endproc

; La marca con que empieza cada cuadro de música en la bitácora.
.proc bitacora_cuadro
.a8
.i16
    lda #0
    xba
    ldx #MUS_BITACORA_MARCA
    jmp bitacora
.endproc

; Antes de la música, en cada cuadro: bajar el disparo que dejó un efecto, y
; devolverle su voz a la música si el efecto terminó en el cuadro anterior.
.macro SE_ANTES_VOZ bajar, devolver, sombra, reg
    .local sin_bajar, listo, registro
    lda f:bajar
    beq sin_bajar
    lda #0
    sta f:bajar
    ldx #SE_KON
    jsr dsp_par
sin_bajar:
    lda f:devolver
    beq listo
    lda #0
    sta f:devolver
    ; KOF como lo tenía la música, salvo lo de la otra voz si sigue con su
    ; efecto, y los ocho registros de esta.
    jsr se_kof_musica
    ldx #SE_KOF
    jsr dsp_par
    ldy #0
registro:
    tyx
    lda f:sombra, x
    pha
    rep #$20
.a16
    tya
    clc
    adc #reg
    tax
    sep #$20
.a8
    pla
    jsr dsp_par
    iny
    cpy #8
    bcc registro
listo:
.endmacro

.proc se_antes
.a8
.i16
    SE_ANTES_VOZ SE_BAJAR, SE_DEVOLVER, SE_SOMBRA, SE_REG
    SE_ANTES_VOZ SE2_BAJAR, SE2_DEVOLVER, SE2_SOMBRA, SE2_REG
    jsl se_extras_antes         ; y las voces 0 a 5: ver efectos_con_msu.s
    rts
.endproc

; Después de la música, para una voz: arrancar su pendiente, o contar el que
; suena y apagarlo cuando termina. Deja en A el bit de la voz si hay que
; dispararla, o cero: el disparo lo hace `se_despues` una sola vez para las
; dos, porque dos escrituras de KON seguidas pueden caer en la misma muestra
; del DSP y la segunda borrar a la primera.
.macro SE_DESPUES_VOZ cuadros, pendiente, devolver, bajar, nuevo, bit, reg
    .local arrancar, contar, nada, fin
    lda f:pendiente
    bne arrancar
    jmp contar
arrancar:
    ; KOF sin los bits de las voces ocupadas —esta incluida, que sigue
    ; pendiente—, que la música pudo haber dejado puestos.
    jsr se_kof_musica
    ldx #SE_KOF
    jsr dsp_par
    lda #0
    sta f:pendiente             ; ya no está pendiente
    ; La muestra, la altura, el volumen y la envolvente, desde el pendiente.
    lda f:nuevo + 4
    ldx #(reg + 1)
    jsr dsp_par                 ; VOLR
    lda f:nuevo + 3
    ldx #(reg + 0)
    jsr dsp_par                 ; VOLL
    lda f:nuevo + 2
    ldx #(reg + 3)
    jsr dsp_par                 ; la altura alta
    lda f:nuevo + 1
    ldx #(reg + 2)
    jsr dsp_par                 ; y la baja
    lda f:nuevo
    ldx #(reg + 4)
    jsr dsp_par                 ; SRCN
    lda #$FF                    ; ADSR prendido, ataque y caída al máximo
    ldx #(reg + 5)
    jsr dsp_par
    lda #$E0                    ; sostenido al máximo y sin caer
    ldx #(reg + 6)
    jsr dsp_par
    rep #$20
.a16
    lda f:nuevo + 5
    sta f:cuadros
    sep #$20
.a8
    lda #1
    sta f:bajar                 ; el cuadro que viene se baja el disparo
    lda #bit
    bra fin
contar:
    rep #$20
.a16
    lda f:cuadros
    beq nada
    dec a
    sta f:cuadros
    bne nada
    sep #$20
.a8
    ; Terminó: KOF con el bit de la voz, y en el cuadro que viene la música
    ; la recupera. Esta ya no cuenta como ocupada, así que `se_kof_musica`
    ; deja afuera sólo a la otra.
    jsr se_kof_musica
    ora #bit
    ldx #SE_KOF
    jsr dsp_par
    lda #1
    sta f:devolver
    lda #0
    bra fin
.a16
nada:
    sep #$20
.a8
    lda #0
fin:
.endmacro

.proc se_despues
.a8
.i16
    SE_DESPUES_VOZ SE_CUADROS, SE_PENDIENTE, SE_DEVOLVER, SE_BAJAR, SE_NUEVO, SE_BIT, SE_REG
    pha
    SE_DESPUES_VOZ SE2_CUADROS, SE2_PENDIENTE, SE2_DEVOLVER, SE2_BAJAR, SE2_NUEVO, SE2_BIT, SE2_REG
    ora 1, s
    sta 1, s
    jsl se_extras_despues       ; las de las voces 0 a 5, en el mismo disparo
    ora 1, s
    sta 1, s
    pla
    beq listo
    ldx #SE_KON
    jsr dsp_par                 ; y el disparo, de las dos juntas
listo:
    rts
.endproc

; El estado en cero: nada sonando. En el reset.
.proc se_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:SE_CUADROS, x
    sta f:SE2_CUADROS, x
    inx
    cpx #SE_BYTES
    bcc otro
    jsl se_extras_limpiar       ; y lo de efectos_con_msu.s
    rts
.endproc

.proc sonido_de_codigo
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el índice
    iny
    iny
    phy
    jsr sonido_tocar            ; con A de dieciséis; vuelve con A de ocho
.a8
    ply
    rts
.endproc

; El efecto cuyo índice en `sonido_tabla` trae A de dieciséis bits, o nada si
; trae $FFFF. Se separó de `sonido_de_codigo` cuando la batalla empezó a tocar
; efectos: los suyos no salen del bytecode sino de las constantes `BA_SE_*`
; que emite el conversor, así que el índice llega en el acumulador.
;
; Entra con A de dieciséis bits y sale con A de ocho, que es como la dejaba
; antes. El banco de datos no importa: todo lo que lee va con `f:`.
.proc sonido_tocar
.a16
.i16
    cmp #$FFFF
    bne hay
    sep #$20
.a8
    rts
hay:
.a16
    phb
    pha                         ; el índice, en la pila hasta `listo`: lo
                                ; necesita efectos_con_msu.s
    sep #$20
.a8
    phk
    plb                         ; la tabla vive en el banco del código
    rep #$20
.a16
    lda 1, s
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp                    ; por siete
    tax
    sep #$20
.a8
    lda f:sonido_tabla, x
    cmp #$FF
    bne hay_efecto
    jmp listo         ; no hay efecto
hay_efecto:
    ; Y sólo si su muestra está en la ARAM: el paquete del mapa puede no
    ; haberla subido. Ver `paquete_cargar`.
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    plx
    cmp #0
    bne esta
    xba
    cmp #0
    bne esta
    jmp listo
esta:
    ; Sin interrupciones mientras se copia: `irq_musica` lee el pendiente, y
    ; uno a medio escribir arrancaría con la muestra de uno y la altura de
    ; otro. La interrupción no se pierde, se atrasa hasta el `plp`.
    php
    sei
    ; La voz: Y queda en 0 para SE_VOZ o en SE2_DESPL para la otra. Primero la
    ; que ya está tocando esta misma muestra —la lluvia se vuelve a disparar
    ; antes de terminar, y así no le roba la otra voz al trueno—, después una
    ; libre, y si no, la que termina antes. Una pendiente no se pisa si la
    ; otra se puede: todavía no sonó nada de ella.
    ldy #0
    lda f:SE_NUEVO
    cmp f:sonido_tabla, x
    bne no_misma_7
    jsr se_ocupada
    bne elegida
no_misma_7:
    ldy #SE2_DESPL
    lda f:SE2_NUEVO
    cmp f:sonido_tabla, x
    bne no_misma_6
    jsr se2_ocupada
    bne elegida
no_misma_6:
    ; Con MSU-1 y el SPC700 sin música, las voces 0 a 5: la que ya toca esta
    ; muestra, y después, si la 7 y la 6 no están libres, una de ésas. Ver
    ; efectos_con_msu.s. Sin MSU-1 no toman nada.
    rep #$20
.a16
    lda 2, s                    ; el índice, detrás de P
    jsl se_extra_misma
.a8
    bcs puesto
    ldy #0
    jsr se_ocupada
    beq elegida
    ldy #SE2_DESPL
    jsr se2_ocupada
    beq elegida
    rep #$20
.a16
    lda 2, s
    jsl se_extra_libre
.a8
    bcs puesto
    ldy #0
    lda f:SE2_PENDIENTE
    bne elegida
    lda f:SE_PENDIENTE
    bne la_6
    rep #$20
.a16
    lda f:SE_CUADROS
    cmp f:SE2_CUADROS
    sep #$20                    ; no toca C
.a8
    bcc elegida
    beq elegida
la_6:
    ldy #SE2_DESPL
elegida:
    rep #$20
.a16
    tya
    clc
    adc #7
    sta temp                    ; dónde termina la copia
    sep #$20
.a8
copiar:
    lda f:sonido_tabla, x
    phx
    tyx
    sta f:SE_NUEVO, x
    plx
    inx
    iny
    cpy temp
    bcc copiar
    rep #$20
.a16
    tya
    sec
    sbc #7
    tax
    sep #$20
.a8
    lda #1
    sta f:SE_PENDIENTE, x
    ; Con los efectos del `.msu`, la altura es la de su versión en el
    ; paquete que está en la ARAM.
    rep #$20
.a16
    lda 2, s
    jsl se_msu_altura_poner
.a8
puesto:
    plp
listo:
    rep #$20
.a16
    pla                         ; el índice: con A y no con Y, que el camino
                                ; sin efecto devolvía como vino
    sep #$20
.a8
    plb
    rts
.endproc

