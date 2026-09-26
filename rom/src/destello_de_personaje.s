.segment "CODE"

; --- los destellos ----------------------------------------------------------
;
; RM2k destella un personaje mezclando su dibujo hacia un color durante unos
; cuadros. Acá el dibujo es una paleta de CGRAM, así que destellar es subir esa
; paleta mezclada, y apagarlo es volver a subirla como estaba.
;
; La mezcla se hace **antes** de que el color llegue a CGRAM, con las mismas
; tablas de canal que el tinte de pantalla: se arman con el tinte y el destello
; juntos, se sube la paleta del personaje, y se vuelven a armar como estaban. Así
; el camino de la paleta es uno solo y no hay dos lugares que puedan diferir.

; Guarda el destello que traen los seis operandos que siguen a Y.
.proc flash_empezar
.a8
.i16
    ldx #$0000
buscar:
    lda flash_ev, x
    cmp #FLASH_LIBRE
    beq puesta
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc buscar
    rts                         ; no hay ranura: este destello se pierde

puesta:
    lda [cod_ptr], y            ; el blanco
    sta flash_ev + 0, x
    iny
    lda [cod_ptr], y
    sta flash_ev + 1, x         ; r
    iny
    lda [cod_ptr], y
    sta flash_ev + 2, x         ; g
    iny
    lda [cod_ptr], y
    sta flash_ev + 3, x         ; b
    iny
    lda [cod_ptr], y
    sta flash_ev + 4, x         ; potencia
    iny
    lda [cod_ptr], y
    sta flash_ev + 5, x         ; cuántos cuadros
    stz flash_ev + 6, x         ; recién empieza
    rts
.endproc

; En qué paleta de sprite se dibuja el blanco que trae A, o $FF si no se
; dibuja. El héroe la lleva en `hero_pal`, ya corrida; un evento, en el byte de
; atributos de su fila.
.proc paleta_del_blanco
.a8
.i16
    cmp #$00
    bne de_evento
    lda hero_pal
    lsr a                       ; hero_pal viene corrido un lugar
    and #$07
    rts
de_evento:
    dec a
    jsr npc_de_evento
    cpy #$FFFF
    bne hay
    lda #$FF
    rts
hay:
    lda npc_buf + 7, y
    lsr a
    and #$07
    rts
.endproc

; Un cuadro de todos los destellos.
.proc flashes_tick
.a8
.i16
    ldx #$0000
otra:
    lda flash_ev, x
    cmp #FLASH_LIBRE
    beq siguiente
    phx
    jsr un_flash
    plx
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc otra
    rts
.endproc

; Un cuadro del destello de la ranura X: avanza, calcula con cuánta fuerza toca
; y sube la paleta. Cuando se pasa de los cuadros que dura, la ranura se libera:
; el cuadro anterior ya la subió con fuerza cero, o sea como estaba.
.proc un_flash
.a8
.i16
    lda flash_ev + 6, x
    inc a
    sta flash_ev + 6, x
    cmp flash_ev + 5, x
    bcc todavia
    beq todavia                 ; el último cuadro va con fuerza cero
    lda #FLASH_LIBRE
    sta flash_ev + 0, x
    rts

todavia:
    ; La fuerza: potencia * (cuadros - k) / cuadros, que es la forma cerrada de
    ; la cuenta que easyrpg hace cuadro a cuadro.
    lda flash_ev + 5, x
    sec
    sbc flash_ev + 6, x
    sta WRMPYA
    lda flash_ev + 4, x
    sta WRMPYB                  ; el producto tarda ocho ciclos
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
    lda flash_ev + 5, x
    sta WRDIVB                  ; el cociente tarda dieciséis
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    asl a
    asl a
    asl a                       ; el alfa de easyrpg es la fuerza por ocho
    sta flash_alfa
    jmp pintar_flash
.endproc

; Sube la paleta del blanco de la ranura X con la fuerza que ya está en
; `flash_alfa`.
.proc pintar_flash
.a8
.i16
    lda flash_ev + 0, x
    jsr paleta_del_blanco
    cmp #$FF
    beq listo                   ; no se dibuja: no hay paleta que tocar
    rep #$20
.a16
    and #$00FF
    sta flash_slot
    sep #$20
.a8
    jsr paleta_con_destello
listo:
    rts
.endproc

; Sube la paleta del personaje `flash_slot` con el tinte y el destello puestos.
; Los colores del destello salen de la ranura X.
.proc paleta_con_destello
.a8
.i16
    stx flash_ranura            ; `tabla_canal_flash` usa X para la tabla
    lda flash_ev + 1, x
    sta flash_dest
    ldy #0                      ; el rojo de `puro` y de las de trabajo
    jsr tabla_canal_flash
    ldx flash_ranura
    lda flash_ev + 2, x
    sta flash_dest
    ldy #32                     ; el verde
    jsr tabla_canal_flash
    ldx flash_ranura
    lda flash_ev + 3, x
    sta flash_dest
    ldy #64                     ; el azul
    jsr tabla_canal_flash

    ; La paleta del personaje: dieciséis colores de dos bytes, y en CGRAM la
    ; mitad de arriba arranca en el color 128.
    rep #$20
.a16
    lda flash_slot
    asl a
    asl a
    asl a
    asl a
    asl a                       ; treinta y dos bytes por paleta
    sta temp
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_SPRITE_CGRAM, x
    clc
    adc temp
    sta tin_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_SPRITE_CGRAM + 2, x
    sta tin_ptr + 2
    rep #$20
.a16
    lda #16
    sta tin_count
    lda flash_slot
    asl a
    asl a
    asl a
    asl a                       ; dieciséis colores por paleta
    clc
    adc #128
    sep #$20
.a8
    sta tin_cgadd
    jsr armar_paleta

    ; La paleta armada se guarda aparte y se sube en el vblank que viene, no
    ; acá. Escribir CGRAM en mitad del cuadro deja la mitad de arriba de la
    ; pantalla con la paleta vieja y la de abajo con la nueva: el sprite sale
    ; con un nivel y el resto con otro. Es la misma razón por la que el tinte
    ; apaga la pantalla para aplicarse. Cada ranura en su lugar de
    ; FAR_FLASH_PAL: ver ahí.
    rep #$20
.a16
    lda flash_ranura
    asl a
    asl a                       ; de ocho bytes por ranura a treinta y dos
    tax
    sep #$20
.a8
    ldy #$0000
copiar:
    lda pal_buf, y
    sta f:FAR_FLASH_PAL, x
    inx
    iny
    cpy #32
    bne copiar
    ldx flash_ranura
    lda tin_cgadd
    sta flash_ev + 7, x         ; y queda esperando el vblank

    ; Y las tablas vuelven a ser las del tinte solo, que es lo que espera todo
    ; el resto. Copiando, no rehaciéndolas: ver `tablas_de_tinte`.
    jmp restaurar_tablas
.endproc

; Las tres tablas de canal del tinte, sin destello, y su copia en `puro`.
;
; La copia existe por el presupuesto de cuadro. `paleta_con_destello` corre en
; todos los cuadros mientras dura un destello y antes terminaba rehaciendo estas
; tres tablas —noventa y seis productos y noventa y seis divisiones—; ahora
; `restaurar_tablas` copia noventa y seis bytes. Y de paso `tabla_canal_flash`
; se ahorra la cuenta del tinte por entrada: la busca acá.
.proc tablas_de_tinte
.a8
.i16
    lda tinte_r
    ldx #.loword(puro)
    jsr tabla_canal
    lda tinte_g
    ldx #.loword(puro) + 32
    jsr tabla_canal
    lda tinte_b
    ldx #.loword(puro) + 64
    jsr tabla_canal
    ; fallthrough
.endproc

; Las tablas de trabajo, tal cual quedaron las del tinte solo.
.proc restaurar_tablas
.a8
.i16
    ldx #$0000
copiar:
    lda puro + 0, x
    sta tabla_r, x
    lda puro + 32, x
    sta tabla_g, x
    lda puro + 64, x
    sta tabla_b, x
    inx
    cpx #32
    bne copiar
    rts
.endproc

; Como `tabla_canal`, pero mezclando antes hacia el color del destello. Y trae
; qué canal: 0, 32 o 64, que es a la vez el desplazamiento en `puro` y en las
; tablas de trabajo —`tabla_r`, `tabla_g` y `tabla_b` van pegadas, igual que
; las tres de `puro`—; `flash_dest` el canal del destello y `flash_alfa` con
; cuánta fuerza.
;
; La mezcla es la de easyrpg puesta en cinco bits: `destino * a + canal *
; (255 - a)` sobre 255, con `a` el nivel por ocho —`Flash::MakeColor` y el
; `PIXMAN_OP_OVER` de `BlendBlit`—. Que el espacio sea de cinco y no de ocho es
; lo que hace que el resultado no sea el de RM2k sino el que da la misma cuenta
; con cinco bits. Es una deuda declarada, y de las que no se pueden medir con
; una comparación: hace falta una captura de EasyRPG tomada durante un destello.
;
; **Y va antes del tinte, no después.** easyrpg hace al revés —`ToneBlit` y
; después `BlendBlit`— pero allá el tono es del sprite y acá el tinte es de la
; pantalla entera. Con el tinte neutro da lo mismo; con tinte, la ROM hace
; `tinte(destello(c))` y RM2k `destello(tono(c))`. Es otra deuda declarada del
; mismo tipo que la de los cinco bits, y la única que se ve es en una página
; que tiña y destelle a la vez.
;
; **La saturación va antes de esta mezcla**: `armar_paleta` satura el color
; crudo, porque la saturación necesita los tres canales juntos y esta tabla es
; de a uno. Es el orden de RM2k, donde saturar es parte de `ToneBlit`.
.proc tabla_canal_flash
.a8
.i16
    ; La mezcla de la entrada c es `(destino * a + c * (255 - a)) / 255`, y de
    ; una entrada a la que sigue el numerador crece siempre lo mismo: 255 - a.
    ; Así que la división se hace una vez, para c = 0, y después se lleva el
    ; resto: cada vez que pasa de 254 se le restan 255 y el cociente sube uno.
    ; Da el mismo cociente que dividir cada vez, porque 255 - a no llega a
    ; 255 * 2 y el resto no puede pasarse dos veces en un paso.
    ;
    ; Hasta el 2026-09-26 cada una de las 96 entradas hacía dos productos y
    ; una división con sus esperas, a unos 150 ciclos por entrada: un destello
    ; de personaje se comía ~94 líneas por cuadro, y en la terraza del mapa 32,
    ; sumado a un `FlashScreen`, la vuelta se pasaba del cuadro. Así son unos
    ; 30 ciclos por entrada.
    ;
    ; No hace falta topar el cociente en 31, como hacía la división suelta:
    ; el destino y el canal son de cinco bits —el conversor no deja pasar
    ; otra cosa, ni en los eventos ni en las animaciones de batalla—, así que
    ; la mezcla tampoco se pasa.
    lda flash_dest
    sta WRMPYA
    lda flash_alfa
    sta WRMPYB                  ; el producto tarda ocho ciclos
    rep #$20
.a16
    tya
    clc
    adc #32
    sta puro_ofs                ; dónde termina este canal
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #255
    sta WRDIVB                  ; el cociente tarda dieciséis
    sec
    sbc flash_alfa
    sta flash_parcial           ; el paso del numerador, 255 - a
    nop
    nop
    nop
    nop
    rep #$20
.a16
    tya
    clc
    adc RDDIVL                  ; X: el cociente, en el canal de `puro`
    tax
    sep #$20
.a8
    ; El resto va corrido uno arriba —de 1 a 255 en vez de 0 a 254— para que
    ; "se pasó de 254" sea el acarreo de la suma de ocho bits; y al pasarse,
    ; restar 255 es quedarse con el byte y sumarle uno. Vive en B mientras A
    ; lee `puro`.
    lda RDMPYL
    inc a
cada:
    xba
    ; Y el tinte, que ya está resuelto: buscar el canal mezclado en la tabla
    ; del tinte solo **es** el hard light, y saca del lazo un producto y una
    ; división por entrada.
    lda puro, x
    sta tabla_r, y
    xba
    clc
    adc flash_parcial
    bcc :+
    inc a
    inx
:   iny
    cpy puro_ofs
    bne cada
    rts
.endproc
.assert tabla_g = tabla_r + 32 && tabla_b = tabla_r + 64, error, "tabla_canal_flash indexa las tres desde tabla_r"


