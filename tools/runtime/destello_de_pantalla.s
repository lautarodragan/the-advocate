.segment "CODE"

; --- el destello de pantalla -------------------------------------------------
; Un cuadro del destello de pantalla: `Flash::Update` de easyrpg, con la cuenta
; entera que sigue. El nivel va a
; escala 256 y baja en `nivel / cuadros_que_quedan` por cuadro, con el divisor
; del hardware; en el último cuadro cae a cero.
;
; RM2k dibuja el destello como un rectángulo del color con alfa encima de la
; pantalla compuesta. Acá es una transformación de CGRAM, como el tinte: cada
; canal de cada color de las tres paletas del mapa se acerca al del destello en
; `nivel / 31` del camino —`destellar_canal`—, y el resultado va a
; `pal_buf`, que `flush_video` sube en el vblank en lugar de la sombra.
; La sombra queda como está: es el mapa teñido sin destello, y cuando el
; destello se apaga vuelve a subirse tal cual.
;
; Pasar las tres paletas —doscientas y pico entradas, a más de cien ciclos
; cada una— no entra en un cuadro junto con todo lo demás: medido con
; `cuadros_perdidos`, se perdía uno por cuadro, y el resto de la escena
; quedaba treinta cuadros atrasado. Así que va en dos cuadros:
; con la resta impar se arman las tablas y se pasan el fondo y la capa de
; encima; con la resta par se pasan los sprites y se sube todo. Lo que se ve
; cambia cuadro por medio. Un tinte que cambie en el cuadro impar pisa
; `pal_buf` con la paleta recién teñida, y además no puede subirse sin
; destello; en ese cuadro se hace todo de una, y en el par se rehace el fondo.
;
; La ventana de mensaje y el cronómetro no reciben el destello, y tampoco allá:
; `Priority_Screen` es 90 contra 130 de la ventana y 140 del cronómetro.
.proc destello_tick
.a8
.i16
    rep #$20
.a16
    lda destello_nivel
    bne hay
    sep #$20
.a8
    rts
.a16
hay:
    sep #$20
.a8
    lda destello_resta
    beq apagar
    rep #$20
.a16
    lda destello_nivel
    sta WRDIVL                  ; el dividendo, de 16 bits
    sep #$20
.a8
    lda destello_resta
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    dec destello_resta          ; seis ciclos, y los nops que faltan
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda destello_nivel
    sec
    sbc RDDIVL
    sta destello_nivel
    sep #$20
.a8
    lda destello_resta
    beq apagar
    and #$01
    beq fase_par
    jsr tablas_de_destello
    jsr destellar_fondo
    lda tinte_listo
    beq listo                   ; lo normal: los sprites van el cuadro que viene
    jsr destellar_sprites
    bra subir
fase_par:
    lda tinte_listo
    beq sprites
    jsr destellar_fondo         ; el tinte nuevo pisó el fondo ya pasado
sprites:
    jsr destellar_sprites
subir:
    lda #1
    sta destello_listo
listo:
    rts
apagar:
    ; Se terminó: el nivel cae a cero y la sombra sin destello vuelve a CGRAM.
    stz destello_nivel
    stz destello_nivel + 1
    stz destello_resta
    lda #1
    sta tinte_listo
    rts
.endproc

.proc destello_de_codigo
.a8
.i16
    lda [cod_ptr], y            ; r
    sta destello_rgb
    iny
    lda [cod_ptr], y            ; g
    sta destello_rgb + 1
    iny
    lda [cod_ptr], y            ; b
    sta destello_rgb + 2
    iny
    lda [cod_ptr], y            ; la fuerza, que es el nivel de arranque
    sta destello_nivel + 1
    stz destello_nivel
    iny
    lda [cod_ptr], y            ; cuadros
    sta destello_resta
    iny
    rts
.endproc

; Las tres tablas del destello, una por canal: qué queda de cada valor de
; cinco bits con el nivel de este cuadro. Son bytes y no palabras ya corridas
; a su lugar del color, que le ahorrarían los corrimientos a
; `destellar_rango`: la RAM del banco 0 no daba para los 96 bytes de más.
.proc tablas_de_destello
.a8
.i16
    lda destello_nivel + 1      ; la parte entera del nivel, de 0 a 31
    sta dest_nivel
    rep #$20
.a16
    lda #.loword(dest_tab_r)
    sta temp
    sep #$20
.a8
    lda destello_rgb
    jsr una_tabla_de_destello
    rep #$20
.a16
    lda #.loword(dest_tab_g)
    sta temp
    sep #$20
.a8
    lda destello_rgb + 1
    jsr una_tabla_de_destello
    rep #$20
.a16
    lda #.loword(dest_tab_b)
    sta temp
    sep #$20
.a8
    lda destello_rgb + 2
    jmp una_tabla_de_destello
.endproc

; Una tabla: A es el canal del color del destello y `temp` apunta a la tabla.
; Es `destellar_canal`:
;
;     hacia >= canal:  canal + (hacia - canal) * nivel / 31
;     hacia <  canal:  canal - (canal - hacia) * nivel / 31
;
; La resta va siempre del lado positivo, porque el divisor no tiene signo.
;
; Los productos salen de la fila del nivel en `prod31_tabla`, y la distancia
; al destino baja de a uno hasta el destino y después sube de a uno, así que
; en vez de calcular cada índice se lo camina: X baja por la fila en el
; primer tramo y sube en el segundo. Hasta el 2026-09-26 cada entrada
; comparaba, restaba y llamaba a una rutina que armaba el índice, a unos 70
; ciclos cada una; en la terraza del mapa 32 el cuadro impar del destello
; pasaba de las cien líneas y, junto con un `FlashSprite`, se pasaba del
; cuadro. Así son menos de 30.
;
; El destino es de cinco bits: el conversor no deja pasar otro, ni en
; `FlashScreen` ni en las animaciones de batalla.
.proc una_tabla_de_destello
.a8
.i16
    sta dest_hacia
    stz dest_hacia + 1
    lda dest_nivel
    rep #$20
.a16
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    sta temp + 2                ; la fila del nivel
    clc
    adc dest_hacia
    tax                         ; X: la fila, en la distancia del canal 0
    lda dest_hacia
    inc a
    sta dest_fin                ; el primer canal que queda arriba del destino
    sep #$20
.a8
    ldy #0
sube:
    tya                         ; el canal, que es Y
    clc
    adc f:prod31_tabla, x
    sta (temp), y
    dex
    iny
    cpy dest_fin
    bne sube
    cpy #32
    beq listo
    rep #$20
.a16
    lda temp + 2
    inc a
    tax                         ; y del otro lado la distancia arranca en uno
    sep #$20
.a8
baja:
    tya
    sec
    sbc f:prod31_tabla, x
    sta (temp), y
    inx
    iny
    cpy #32
    bne baja
listo:
    rts
.endproc


; Las paletas del fondo y de la capa de encima, de la sombra a `pal_buf`
; pasadas por las tablas. Son las mismas entradas y cuentas que `subir_tinte`.
.proc destellar_fondo
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    sta tin_count
    sep #$20
.a8
    ; Desde `CGRAM_BASE`, igual que `aplicar_tinte` y que `subir_paletas`: el
    ; fondo no arranca en la entrada 0 sino arriba de la ventana de mensaje.
    ; Acá decía 0, que era lo correcto hasta que la ventana se mudó a la paleta
    ; 0 y el fondo se corrió nueve entradas —ver el commit 5015868, que arregló
    ; los otros dos lugares y **se olvidó de éste**—. Con el 0, las últimas
    ; nueve entradas del fondo no se destellaban: se subían con lo que hubiera
    ; quedado en `pal_buf`, así que unos pocos tiles no se iluminaban y encima
    ; cambiaban de color. taro lo vio el 2026-09-08 en los relámpagos de la
    ; apertura —las vallas amarillas y negras, y los bordes del autotile 17 del
    ; ChipSet3—, que son el **primer** `FlashScreen` que corrió este port.
    ; Ninguna prueba lo cubría: la página de prueba de `destello` destella un
    ; sprite —`FlashSprite`—, nunca la pantalla, así que este camino no lo
    ; ejecutaba nadie.
    lda #CGRAM_BASE
    jsr destellar_rango
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    jmp destellar_rango
.endproc

; Y las de los sprites.
.proc destellar_sprites
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #128
    jmp destellar_rango
.endproc

; `tin_count` colores desde la entrada A: cada uno se parte en sus tres
; canales, cada canal pasa por su tabla, y las tres palabras se juntan.
.proc destellar_rango
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por color
    tax
    lda tin_count
    asl a
    beq nada
    sta dest_fin
    txa
    clc
    adc dest_fin
    sta dest_fin
color:
    lda cgram_sombra, x
    sta temp                    ; el color, y en temp + 2 lo que se va armando
    and #$001F
    tay
    lda dest_tab_r, y           ; y el byte que sigue, que se enmascara
    and #$00FF
    sta temp + 2
    lda temp
    and #$03E0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    lda dest_tab_g, y
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; el azul queda en los bits 2 a 6
    and #$007C
    lsr a
    lsr a
    tay
    lda dest_tab_b, y
    and #$00FF
    xba                         ; por 256, y dos más son los diez bits
    asl a
    asl a
    ora temp + 2
    sta pal_buf, x
    inx
    inx
    cpx dest_fin
    bne color
nada:
    sep #$20
.a8
    rts
.endproc

