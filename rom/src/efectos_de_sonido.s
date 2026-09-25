; --- los efectos de sonido -------------------------------------------------------
;
; `PlaySound`, en dos voces que se le roban a la música mientras duran: SE_VOZ
; y SE2_VOZ, las dos de percusión. Ver `build_efectos` en snes_music.py. En
; RM2k los efectos se suman —EasyRPG tiene 31 canales—, y con una sola voz la
; lluvia de la apertura le cortaba el trueno a la mitad: medido, 73 de sus 144
; cuadros, y una vez 7.
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
    sta 1, s
    pla                         ; Z según la máscara entera
    rts
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

; Un par al DSP: X el registro, A el valor. Es lo que hace `write_dsp`.
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

; Una escritura del stream de la música: X el registro, A el valor. Si es de
; una voz de efecto, va a su sombra, y si la voz tiene efecto no se manda; KON
; y KOF salen sin los bits de las voces ocupadas.
.proc dsp_musica
.a8
.i16
    xba                         ; B = el valor
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
    phx
    rep #$20
.a16
    and #$000F
    tax
    sep #$20
.a8
    xba
    sta f:SE_SOMBRA, x          ; a la sombra
    xba
    plx
    jsr se_ocupada
    beq enviar
    rts                         ; la voz es del efecto
voz_6:
    txa
    and #$0F
    cmp #8
    bcs no_voz
    phx
    rep #$20
.a16
    and #$000F
    tax
    sep #$20
.a8
    xba
    sta f:SE2_SOMBRA, x
    xba
    plx
    jsr se2_ocupada
    beq enviar
    rts
no_voz:
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
    rts
.endproc

