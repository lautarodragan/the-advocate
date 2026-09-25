.segment "CODE"

; --- la cámara corrida sin el héroe ----------------------------------------
; `Game_Player::UpdatePan`: cada eje se acerca a su destino de a `pan_paso`
; dieciseisavos de pixel, sin pasarse. Y de paso se baja a pixeles enteros, que
; es lo que `follow_camera` suma: la división es **al piso** y con signo, que es
; lo que hace `Spriteset_Map` dividiendo `GetDisplayX()` por 16.
;
; Se guarda en pixeles en vez de dividir en cada uso porque `follow_camera`
; corre una vez por cuadro y esto también, pero acá la cuenta se hace una sola
; vez por eje.
.proc pan_tick
.a8
.i16
    rep #$20
.a16
    ldx #0                      ; el eje: 0 es la x, 2 la y
otro_eje:
    lda pan_dest_x, x
    sec
    sbc pan_x, x
    beq en_su_lugar             ; ya llegó
    bpl hacia_adelante
    ; Falta hacia atrás: se resta el paso, o lo que quede si es menos.
    eor #$FFFF
    inc a                       ; el valor absoluto de lo que falta
    cmp pan_paso
    bcc corto
    lda pan_paso
corto:
    eor #$FFFF
    inc a                       ; y de vuelta con signo
    bra sumar
hacia_adelante:
    cmp pan_paso
    bcc sumar
    lda pan_paso
sumar:
    clc
    adc pan_x, x
    sta pan_x, x
en_su_lugar:
    ; A pixeles: cuatro corrimientos aritméticos, que conservan el signo.
    lda pan_x, x
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    sta pan_px, x
    inx
    inx
    cpx #4
    bcc otro_eje
    sep #$20
.a8
    rts
.endproc

; --- la cámara -------------------------------------------------------------
; Sigue al héroe: lo deja en el centro de la pantalla salvo cerca de los bordes
; del mapa, donde se queda pegada para no mostrar el vacío de afuera.
;
; El scroll es por hardware, así que esto son dos restas y dos escrituras. No
; hay que redibujar nada: el mapa entero ya está en el tilemap.
; Un cuadro de la sacudida de pantalla: `Shake::Update` y `NextPosition` de
; easyrpg, con la cuenta entera que sigue:
;
;     amplitud = 1 + 2 * fuerza
;     nuevo    = -amplitud * seno[(resta * 4 * (velocidad + 2)) % 256] / 127
;     corte    = velocidad * amplitud / 8 + 1
;     posicion = clamp(nuevo, posicion - corte, posicion + corte)
;
; Los productos van por el multiplicador del hardware y la división por el
; divisor, que son los que ya usa `aplicar_tinte`. El seno es `seno_sacudida`,
; en el banco 0, con signo y a escala 127; el signo se saca antes de multiplicar
; y se vuelve a poner después, que es truncar hacia cero como hace `int`.
.proc sacudida_tick
.a8
.i16
    rep #$20
.a16
    lda sacudida_resta
    beq nada16
    dec a
    sta sacudida_resta
    bne sigue
    stz sacudida_pos            ; el último cuadro: la pantalla vuelve
nada16:
    sep #$20
.a8
    rts
.a16
sigue:
    ; t = (resta * 4 * (velocidad + 2)) % 256: alcanza con el byte bajo de
    ; resta * 4, porque lo que sobra de 256 se va igual.
    asl a
    asl a
    sep #$20
.a8
    sta WRMPYA
    lda sacudida_vel
    inc a
    inc a
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    lda sacudida_fuerza         ; mientras tanto, la amplitud
    asl a
    inc a
    sta sac_amp
    nop
    nop
    lda RDMPYL                  ; el byte bajo del producto es t
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:seno_sacudida, x      ; fuera del banco 0: ver `tabla_de_senos`
    sta sac_seno
    bpl positivo
    eor #$FF
    inc a                       ; |seno|
positivo:
    sta WRMPYA
    lda sac_amp
    sta WRMPYB                  ; |seno| * amplitud
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #127
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDDIVL
    sta sac_nuevo               ; |nuevo|
    sep #$20
.a8
    lda sac_seno
    bmi con_signo               ; seno negativo: nuevo queda positivo
    rep #$20
.a16
    lda sac_nuevo
    eor #$FFFF
    inc a
    sta sac_nuevo               ; seno positivo: nuevo es negativo
    sep #$20
.a8
con_signo:
    ; corte = velocidad * amplitud / 8 + 1
    lda sacudida_vel
    sta WRMPYA
    lda sac_amp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    lsr a
    lsr a
    lsr a
    inc a
    sta sac_corte
    lda sacudida_pos
    sec
    sbc sac_corte
    sta sac_lo
    lda sacudida_pos
    clc
    adc sac_corte
    sta sac_hi
    ; Los números son chicos —la amplitud no pasa de 19— así que el signo de
    ; la resta alcanza para comparar con signo.
    lda sac_nuevo
    sec
    sbc sac_lo
    bmi usar_lo
    lda sac_hi
    sec
    sbc sac_nuevo
    bmi usar_hi
    lda sac_nuevo
    bra guardar
usar_lo:
    lda sac_lo
    bra guardar
usar_hi:
    lda sac_hi
guardar:
    sta sacudida_pos
    sep #$20
.a8
    rts
.endproc

.proc follow_camera
.a8
.i16
    rep #$20
.a16
    lda hero_x
    clc
    adc #8                      ; el centro de su celda de 16x16
    sec
    sbc #128                    ; media pantalla de ancho
    clc
    ; Y la cámara corrida sin el héroe. **El pan se suma en cada cuadro, no
    ; una vez**: en RM2k la cámara se lo sigue llevando mientras el héroe
    ; camina —`Game_Player::UpdateScroll`— y sólo lo borra un cambio de mapa.
    ; Por eso un `PanScreen` que nadie devuelve deja la pantalla descentrada
    ; para siempre, y eso **es fiel**: pasa al salir por la reja del mapa 12 y
    ; pasa igual en el RPG_RT original. Ver
    ; `workflow/decisiones/la-camara-corrida-de-la-reja-es-del-juego.md`.
    adc pan_px
    bpl limite_x
    lda #0                      ; el héroe está cerca del borde izquierdo
limite_x:
    cmp cam_max_x
    bcc guarda_x
    lda cam_max_x
guarda_x:
    sta camara_x

    lda hero_y
    clc
    adc #8
    sec
    sbc #112                    ; media pantalla de alto
    clc
    adc pan_py
    bpl limite_y
    lda #0
limite_y:
    cmp cam_max_y
    bcc guarda_y
    lda cam_max_y
guarda_y:
    sta camara_y

    ; El PPU muestra la línea vofs+1 en el primer scanline, así que lo que se le
    ; escribe es siempre uno menos que dónde queremos mirar.
    dec a
    sta scroll_y
    ; Y lo que ve el dibujo: la cámara más la sacudida de pantalla.
    lda camara_x
    clc
    adc sacudida_pos
    sta pantalla_x
    sep #$20
.a8
    rts
.endproc

