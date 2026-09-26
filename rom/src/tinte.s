.segment "CODE"

; --- el tinte de pantalla --------------------------------------------------
;
; RM2k escala cada canal por un valor de 0 a 200, con 100 como neutro. En una
; consola con paleta eso no es un efecto de pantalla sino una transformación de
; la paleta: se escalan los colores al subirlos y el fondo, que va en 8 bits por
; pixel y direcciona CGRAM en directo, queda teñido exactamente.
;
; La cuenta es `i * valor / 100` con enteros. Las dos operaciones las hace el
; hardware y son exactas, así que la referencia en Python hace la misma cuenta
; y da siempre lo mismo. Una aproximación con corrimientos no serviría: la
; comparación es pixel por pixel.

; t[i] = i * valor / 100 para i de 0 a 31, topado en 31. A = valor, X = tabla.
.proc tabla_canal
.a8
.i16
    ; El tinte de RM2k no escala el canal: lo compone con un *hard light*, que
    ; es `2ab` para la mitad de abajo y el screen `1-2(1-a)(1-b)` para la de
    ; arriba. En las unidades de RM2k, con 100 neutro, las dos mitades son la
    ; misma cuenta espejada en los dos ejes:
    ;
    ;     valor <= 100:  canal * valor / 100
    ;     valor  > 100:  31 - (200 - valor) * (31 - canal) / 100
    ;
    ; Así que se arma siempre la de abajo —que es lo que este código venía
    ; haciendo, o sea que los tintes que oscurecen dan exactamente lo mismo que
    ; antes— y si el valor aclara se espeja la tabla terminada:
    ; `t'[j] = 31 - t[31 - j]`.
    ;
    ; La mitad de arriba estaba mal: multiplicaba por dos y topaba en 31, y la
    ; diferencia con RM2k llegaba a 31 de 31 con el valor 200. No lo cobró nadie
    ; porque ninguna página que compilara aclaraba la pantalla; dos de las once
    ; que destraba la saturación sí, con (0, 120, 120).
    ;
    ; El espejo va afuera del lazo a propósito. Hacerlo por entrada —con la
    ; cuenta metida en una subrutina— son noventa y seis `jsr` y `rts` de más
    ; por tinte, y eso alcanzó para que `aplicar_tinte` pasara de un cuadro a
    ; dos: se vio como `snes-timer` perdiendo un tic del cronómetro.
    sta temp                    ; el valor del canal
    stx temp + 2                ; dónde va la tabla
    stz tinte_espejo
    cmp #(TINTE_NEUTRO + 1)
    bcc arrancar
    lda #(2 * TINTE_NEUTRO)
    sec
    sbc temp
    sta temp                    ; 200 - valor
    inc tinte_espejo
arrancar:
    ldy #$0000
cada:
    tya
    sta WRMPYA
    lda temp
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
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
    lda #TINTE_NEUTRO
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc cabe
    lda #31                     ; el canal tiene cinco bits y no más
cabe:
    sta (temp + 2), y
    iny
    cpy #32
    bne cada

    lda tinte_espejo
    bne espejar
    rts

    ; El espejo va en dos pasadas, con una copia en el medio, porque `(dp), y`
    ; direcciona con Y y acá hacen falta dos índices a la vez: `j` y `31 - j`.
espejar:
    ldy #$0000
copiar:
    lda (temp + 2), y
    sta tinte_tmp, y
    iny
    cpy #32
    bne copiar
    ldy #$0000
volver:
    rep #$20
.a16
    tya
    eor #$001F                  ; con cinco bits, el complemento es 31 - j
    tax
    sep #$20
.a8
    lda #31
    sec
    sbc tinte_tmp, x
    sta (temp + 2), y
    iny
    cpy #32
    bne volver
    rts
.endproc

; Lee una paleta de la ROM, la tiñe color por color y la sube a CGRAM.
.proc tenir_paleta
.a8
.i16
    jsr armar_paleta
    jmp copiar_a_sombra
.endproc
; Copia la paleta recién armada en `pal_buf` a su lugar de `cgram_sombra`, y
; deja el tinte listo para que `flush_video` lo suba en el vblank.
.proc copiar_a_sombra
.a8
.i16
    lda tin_cgadd
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por color
    tay
    sep #$20
.a8
    ldx #$0000
    cpx tin_fin
    beq listo                   ; una paleta sin colores
copia:
    lda pal_buf, x
    sta cgram_sombra, y
    inx
    iny
    cpx tin_fin
    bne copia
listo:
    lda #1
    sta tinte_listo
    rts
.endproc

; Arma la paleta teñida en `pal_buf`, sin subirla.
.proc armar_paleta
.a8
.i16
    ; La cuenta va en Y y no en X: adentro del lazo X es el índice de las tres
    ; tablas de canal, así que al llegar acá vale el azul del color anterior y
    ; no cuántos colores van. Y sí sobrevive: es el cursor de la paleta.
    rep #$20
.a16
    lda tin_count
    asl a                       ; dos bytes por color
    sta tin_fin
    sep #$20
.a8
    ; Ni `sta` ni `sep` tocan Z, así que esto mira el `asl`. Una paleta sin
    ; colores se va sin hacer nada: el DMA de abajo mediría cero bytes, que en
    ; el hardware son 64 KB, y llenaría CGRAM de basura.
    bne hay_colores
    rts
hay_colores:
    ldy #$0000
    ; Con la saturación neutra —que es casi siempre— el color no necesita ni
    ; los tres canales juntos ni salir de los dieciséis bits, y ahí el lazo
    ; corto se paga solo. La cuenta: `aplicar_tinte` recorre los colores del
    ; mapa, los de la capa de encima, los de las ocho paletas de sprite y los
    ; del líder —en CoreRetro II son 151— y el lazo largo salía 205 ciclos cada
    ; uno. Con eso la vuelta del cuadro en que corre el tinte terminaba en la
    ; línea 224 de 262: **una** de margen. El primer evento de más que pidió
    ; una paleta la voló, y la pantalla quedó un cuadro sin teñir contra la
    ; referencia. Medido con la sonda de `contar_perdidos`.
    lda tinte_s
    cmp #TINTE_NEUTRO
    bne cada_color
    rep #$20
.a16
    jmp cada_color_neutro

cada_color:
.a8
    cpy tin_fin
    bne sigue_color
    rts
sigue_color:
    rep #$20
.a16
    lda [tin_ptr], y
    sta temp                    ; el color original, de 15 bits
    and #$001F
    sta sat_r
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_g
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_b
    sep #$20
.a8
    ; La saturación va **antes** del color, que es el orden de `ToneBlit`: allá
    ; `saturation_tone` corre antes que `color_tone`. Al revés el gris se
    ; calcularía sobre el color ya teñido, y es de las que la comparación no
    ; vería porque los dos lados harían lo mismo mal.
    ;
    ; Y sólo cuando hace falta, igual que el `apply_sat` de easyrpg: no se puede
    ; hacer canal por canal —necesita el gris del color entero, o sea los tres a
    ; la vez— así que no entra en las tablas y es lo caro de todo esto.
    lda tinte_s
    cmp #TINTE_NEUTRO
    beq sin_saturar
    jsr saturar_color
sin_saturar:
    ldx sat_r
    lda tabla_r, x
    sta temp + 2
    ldx sat_g
    lda tabla_g, x
    sta temp + 3
    ldx sat_b
    lda tabla_b, x
    rep #$20
.a16
    and #$001F
    xba                         ; el azul va en los bits 10 a 14: ocho lugares
    asl a                       ; los da el intercambio de bytes y los dos que
    asl a                       ; faltan, dos corrimientos. Diez `asl` seguidos
                                ; se cuentan mal, y así fue como salieron cinco
    sta temp
    lda temp + 2
    and #$001F                  ; el rojo, sin el verde que quedó al lado
    ora temp
    sta temp
    lda temp + 3
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a                       ; y el verde en los bits 5 a 9
    ora temp
    sta pal_buf, y

    iny
    iny
    sep #$20
.a8
    bra cada_color

    ; El mismo color, sin saturación y sin salir de los dieciséis bits. Los
    ; `lda tabla_x, x` leen de paso el byte de al lado —las tres tablas están
    ; pegadas y después viene `puro`—; el `and` lo tira.
cada_color_neutro:
.a16
    cpy tin_fin
    beq subir_neutro
    lda [tin_ptr], y
    sta temp
    and #$001F                  ; el rojo
    tax
    lda tabla_r, x
    and #$001F
    sta temp + 2
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; el verde
    tax
    lda tabla_g, x
    and #$001F
    xba                         ; por ocho
    lsr a
    lsr a
    lsr a                       ; menos tres: a los bits 5 a 9
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; el byte de arriba abajo
    lsr a
    lsr a
    and #$001F                  ; el azul, que estaba en los bits 10 a 14
    tax
    lda tabla_b, x
    and #$001F
    xba                         ; por ocho
    asl a
    asl a                       ; y dos más: a los bits 10 a 14
    ora temp + 2
    sta pal_buf, y
    iny
    iny
    bra cada_color_neutro
subir_neutro:
    sep #$20
.a8
subir:
    rts
.endproc

; --- la saturación del tinte -----------------------------------------------
; Acerca o aleja del gris los tres canales que quedaron en `sat_r`, `sat_g` y
; `sat_b`. Es `saturation_tone` de easyrpg puesto en cinco bits y en las
; unidades de RM2k: allá el factor sale de `gray = s * 128 / 100` y vale
; `gray * 8` o `1024 + (gray - 128) * 16` sobre 1024, que hecha la cuenta es
; `s / 100` por debajo de 100 y `(2s - 100) / 100` por arriba. O sea que 0
; lleva todo al gris, 100 no hace nada y 200 triplica la distancia.
.proc saturar_color
.a8
.i16
    ; Primero el gris. Los pesos son los de Y' del Y'CbCr y suman 65536
    ; exactos, así que sobre canales de cinco bits dan una luminancia de cinco
    ; bits: alcanza con quedarse con el byte de arriba de la suma de 24.
    stz sat_acc + 0
    stz sat_acc + 1
    stz sat_acc + 2
    lda sat_r
    sta peso_ch
    lda #<LUZ_R
    sta peso_lo
    lda #>LUZ_R
    sta peso_hi
    jsr sumar_peso
    lda sat_g
    sta peso_ch
    lda #<LUZ_G
    sta peso_lo
    lda #>LUZ_G
    sta peso_hi
    jsr sumar_peso
    lda sat_b
    sta peso_ch
    lda #<LUZ_B
    sta peso_lo
    lda #>LUZ_B
    sta peso_hi
    jsr sumar_peso
    lda sat_acc + 2             ; la suma sobre 65536
    sta sat_luz

    lda sat_r
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_r
    sep #$20
.a8
    lda sat_g
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_g
    sep #$20
.a8
    lda sat_b
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_b
    sep #$20
.a8
    rts
.endproc

; `sat_acc += peso * peso_ch`, en 24 bits. El peso es de dieciséis y la unidad
; de la consola multiplica de a ocho, así que va en dos productos: el bajo tal
; cual y el alto corrido un byte.
.proc sumar_peso
.a8
.i16
    lda peso_lo
    sta WRMPYA
    lda peso_ch
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda sat_acc + 2
    adc #0                      ; ni `sta` ni `sep` tocan el acarreo
    sta sat_acc + 2

    lda peso_hi
    sta WRMPYA
    lda peso_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp                    ; el producto alto, que va corrido ocho bits
    and #$00FF
    xba                         ; su byte bajo, ya en el lugar de arriba
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda temp + 1                ; y el byte alto del producto
    adc sat_acc + 2
    sta sat_acc + 2
    rts
.endproc

; Un canal acercado o alejado de `sat_luz`. Entra y sale en A.
.proc saturar_canal
.a8
.i16
    sta sat_ch
    lda tinte_s
    cmp #(TINTE_NEUTRO + 1)
    bcs sobre

    ; Hasta 100 es una interpolación entre el gris y el color, con los dos
    ; términos positivos: es la forma que el 65816 puede hacer sin signo.
    ;
    ;     (luz * (100 - s) + canal * s) / 100
    lda #TINTE_NEUTRO
    sec
    sbc tinte_s
    sta WRMPYA
    lda sat_luz
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp + 2
    sep #$20
.a8
    lda tinte_s
    sta WRMPYA
    lda sat_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc temp + 2
    sta WRDIVL
    sep #$20
.a8
    jmp dividir_y_topar

    ; Por arriba de 100 el canal se aleja del gris: `canal +- |canal - luz| *
    ; (s - 100) / 100`, con el signo aparte para no tener que restar con signo.
    ; easyrpg lo hace con un desplazamiento aritmético, que redondea hacia abajo
    ; también con negativos; acá se trunca. La diferencia es de un valor de 31 y
    ; sólo cuando sobresatura.
sobre:
    lda tinte_s
    sec
    sbc #TINTE_NEUTRO
    sta WRMPYA
    lda sat_ch
    cmp sat_luz
    bcc baja
    inc sat_sube_marca
    sec
    sbc sat_luz
    bra multiplicar
baja:
    stz sat_sube_marca
    lda sat_luz
    sec
    sbc sat_ch
multiplicar:
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #TINTE_NEUTRO
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta temp + 2
    lda sat_sube_marca
    beq restar
    lda sat_ch
    clc
    adc temp + 2
    cmp #32
    bcc listo_sobre
    lda #31
listo_sobre:
    rts
restar:
    lda sat_ch
    sec
    sbc temp + 2
    bcs listo_sobre
    lda #0
    rts
.endproc

; El divisor y la espera, que son los mismos en los dos caminos.
.proc dividir_y_topar
.a8
.i16
    lda #TINTE_NEUTRO
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc cabe
    lda #31
cabe:
    rts
.endproc

; Y la sube desde `pal_buf` a la entrada `tin_cgadd` de CGRAM.

; El tinte que dejó el evento, aplicado a las tres paletas del mapa.
.proc aplicar_tinte
.a8
.i16
    jsr tablas_de_tinte

    ; El fondo, desde donde arranca: debajo de él están el color de fondo de la
    ; pantalla y la paleta de la ventana, que **no se tiñen**. Que queden afuera
    ; sale de dónde empieza el rango y no de acordarse de saltearlas.
    ldx #M_PTR_MAP_CGRAM
    ldy #M_MAP_CGRAM
    lda #CGRAM_BASE
    jsr una_paleta

    ; La capa de encima, en la entrada que le haya tocado a este mapa. Hay que
    ; leerla del registro antes de cargar X con el campo, porque el registro se
    ; direcciona justamente con X.
    ldx mapa_ofs
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    pha
    ldx #M_PTR_ABOVE_CGRAM
    ldy #M_ABOVE_CGRAM
    pla
    jsr una_paleta

    ; Y los sprites, en la mitad de arriba de CGRAM.
    ldx #M_PTR_SPRITE_CGRAM
    ldy #M_SPRITE_CGRAM
    lda #128
    jsr una_paleta

    ; Encima, los colores del líder en su ranura. Los líderes posibles comparten
    ; una, así que el bloque que vino del cartucho trae los del que el conversor
    ; puso primero, y el que está liderando puede ser otro. Va **acá** y no
    ; aparte para que se tiña con todo lo demás: subirlos después dejaría al
    ; héroe sin teñir, que es el error inverso del cronómetro.
    lda hero_cgram + 2
    beq sin_lider_pal           ; ningún líder con gráfico: nada que subir
    rep #$20
.a16
    lda hero_cgram
    sta tin_ptr
    lda #OBJ_COLORS
    sta tin_count
    sep #$20
.a8
    lda hero_cgram + 2
    sta tin_ptr + 2
    lda hero_pal                ; viene corrido un lugar, o sea paleta por dos
    asl a
    asl a
    asl a                       ; y esto lo lleva a paleta por dieciséis
    clc
    adc #129                    ; la mitad de sprites, más el índice 0 que no se
    sta tin_cgadd               ; dibuja
    jsr tenir_paleta
sin_lider_pal:

    ; El cronómetro va **sin teñir**, encima de lo que acaba de subir. En RM2k
    ; el tinte es una propiedad de los dibujables del mapa —`Priority_Screen`
    ; es 90 y `Priority_Timer` 140—, así que la pantalla se oscurece y los
    ; dígitos no. Acá el tinte es una transformación de CGRAM y se lleva por
    ; delante todo lo que toca, así que `subir_timer_pal` vuelve a subir de la
    ; ROM las entradas de los dígitos, y sólo ésas: la paleta la comparten con
    ; un personaje.
    ;
    ; La ventana de mensaje tampoco se tiñe, y sin hacer nada: vive en las
    ; entradas de abajo de todo y el fondo arranca en `CGRAM_BASE`, así que
    ; queda fuera del rango. Es lo que hace RM2k —el tono se aplica al mapa, a
    ; los personajes y al panorama, no a la ventana— y acá decía que no se
    ; podía.
    ;
    ; Nada de esto tocó CGRAM: las tres paletas quedaron en `cgram_sombra` y
    ; las sube `subir_tinte`, en el vblank.
    rts
.endproc

; Sube a CGRAM las tres paletas teñidas de `cgram_sombra`, y las entradas del
; cronómetro sin teñir detrás. Es para el vblank, o para `cargar_mapa` con la pantalla
; apagada. Los tres DMA juntos son a lo sumo 544 bytes.
.proc subir_tinte
.a8
.i16
    stz tinte_listo
    rep #$20
.a16
    lda #.loword(cgram_sombra)
    sta sombra_origen
    sep #$20
.a8
    jmp subir_paletas
.endproc
; Lo mismo desde `pal_buf`, que es donde queda la sombra con el destello de
; pantalla encima. Se lleva el tinte pendiente, si lo había: el destello ya
; se armó sobre la sombra recién teñida.
.proc subir_destello
.a8
.i16
    stz destello_listo
    stz tinte_listo
    rep #$20
.a16
    lda #.loword(pal_buf)
    sta sombra_origen
    sep #$20
.a8
    jmp subir_paletas
.endproc
.proc subir_paletas
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #CGRAM_BASE             ; el fondo arranca corrido: abajo está la
    jsr dma_sombra              ; ventana, que no se tiñe ni se vuelve a subir
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    jsr dma_sombra
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #128
    jsr dma_sombra
    jmp subir_timer_pal
.endproc
; Un DMA de `tin_count` colores desde `sombra_origen` a la entrada A de CGRAM.
.proc dma_sombra
.a8
.i16
    sta CGADD
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc sombra_origen
    sta A1T0L
    lda tin_count
    asl a                       ; dos bytes por color
    beq nada                    ; cero bytes serían 64 KB
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; la sombra vive en el banco 0
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN
    rts
.a16
nada:
    sep #$20
.a8
    rts
.endproc

; Las entradas de los dígitos del cronómetro, sin teñir, encima de lo que
; acaba de subir. **Sólo esas entradas y no la paleta entera**: desde
; `034d721` los dígitos comparten la paleta con un personaje —el que tenga
; lugar para sus dos colores—, y ese personaje sí se tiñe. Subir la paleta
; entera lo dejaba sin teñir en cualquier pantalla teñida, con el cronómetro
; prendido o no: `release` lleva los dígitos en todos los mapas.
;
; Y sólo **con el cronómetro en pantalla**. Sin dígitos que dibujar esas
; entradas son del personaje nada más y van teñidas como las demás; al
; prenderlo o apagarlo, `timer_repintar` pide volver a subir. Lo que queda
; sin arreglo es una entrada que el personaje y los dígitos comparten —el
; negro, casi siempre, y el rojo del save point—: mientras el cronómetro se ve,
; ésa queda sin teñir para los dos, porque los dígitos mandan. El negro sólo
; se nota con un tinte que aclara: oscurecer y desaturar lo dejan negro.
;
; Qué entradas son lo dice `timer_mascara`, un bit por entrada y una palabra
; por mapa, que emite el conversor.
.proc subir_timer_pal
.a8
.i16
    lda timer_visible
    bne visible
    rts
visible:
    rep #$20
.a16
    lda mapa_ofs
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; de 128 bytes por mapa a dos
    tax
    lda f:timer_mascara, x
    bne hay
    sep #$20
.a8
    rts                         ; este mapa no lleva los dígitos
.a16
hay:
    sta tin_count               ; los bits que faltan: ni `temp`, que en el
                                ; vblank puede estar ocupado
    ; La paleta en la ROM, y la entrada 0 de CGRAM que le toca.
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_PAL, x
    and #$0007
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por paleta
    clc
    adc f:mapa_tabla + M_PTR_SPRITE_CGRAM, x
    sta tin_ptr                 ; el bloque entra entero en un banco: lo
    sep #$20                    ; sube un DMA
.a8
    lda f:mapa_tabla + M_PTR_SPRITE_CGRAM + 2, x
    sta tin_ptr + 2
    lda f:mapa_tabla + M_TIMER_PAL, x
    asl a
    asl a
    asl a
    asl a                       ; dieciséis colores por paleta
    clc
    adc #128
    sta tin_cgadd
    ldy #$0000
cada:
    rep #$20
.a16
    lsr tin_count
    sep #$20
.a8
    bcc siguiente
    lda tin_cgadd
    sta CGADD
    lda [tin_ptr], y
    sta CGDATA                  ; primero el byte de abajo
    iny
    lda [tin_ptr], y
    sta CGDATA
    dey
siguiente:
    inc tin_cgadd
    iny
    iny
    lda tin_count
    ora tin_count + 1
    bne cada                    ; sin más bits, lo demás ya quedó teñido
    rts
.endproc

; El cronómetro se acaba de prender o de apagar, y sus entradas cambian de
; dueño: sin teñir si se ve, teñidas con el personaje si no. Se vuelven a
; subir en el vblank que viene, con todo lo demás, desde la sombra.
;
; Con el tinte neutro no hace falta: teñidas o no son el mismo color. Y
; preguntarlo no es por ahorrar el DMA sino el presupuesto: el cuadro que sube
; el tinte sube menos poses —ver `flush_video`—, y eso movería al que camina
; justo cuando arranca un cronómetro sin tinte.
.proc timer_repintar
.a8
.i16
    lda tinte_r
    cmp #TINTE_NEUTRO
    bne pedir
    lda tinte_g
    cmp #TINTE_NEUTRO
    bne pedir
    lda tinte_b
    cmp #TINTE_NEUTRO
    bne pedir
    lda tinte_s
    cmp #TINTE_NEUTRO
    bne pedir
    rts
pedir:
    lda #1
    sta tinte_listo
    rts
.endproc

; Tiñe y sube una de las paletas del mapa. X = el campo del puntero, Y = el
; campo de la cantidad, A = en qué entrada de CGRAM arranca.
.proc una_paleta
.a8
.i16
    sta tin_cgadd
    stx temp
    sty temp + 2

    rep #$20
.a16
    lda temp
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta tin_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta tin_ptr + 2

    rep #$20
.a16
    lda temp + 2
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta tin_count
    sep #$20
.a8
    jsr tenir_paleta
    rts
.endproc

