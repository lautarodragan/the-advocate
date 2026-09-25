.segment "CODE"

; --- los eventos quietos que animan igual ---------------------------------
;
; `animation_type` 1 y 3 de RM2k —"Continuous" y "Fixed Dir/Continuous"— hacen
; que el evento recorra el ciclo de caminata **sin moverse**. El save point de
; Lashe City es del segundo tipo, y taro lo pidió el 2026-09-07.
;
; Los que caminan ya lo hacen: su ranura de ruta lleva el contador y `.proc
; animar_ruta_ev` lo avanza. Los quietos no tienen ranura, y no hay dónde
; guardarles un contador: la fila del NPC no tiene un byte libre —el +11 es el
; alto del salto— y la BSS está llena. Así que la columna sale del reloj del
; juego, igual que la animación del ChipSet: `vueltas` dividido por cada cuántos
; cuadros cambia, que es `anim_continua` por velocidad, y el ciclo de cuatro
; pasos con el tercero repitiendo el primero.
;
; **La fase no es la de RM2k**, que arranca el contador de cada personaje cuando
; el mapa lo crea; acá es global. Está declarado en
; workflow/divergencias/la-fase-de-los-quietos-que-animan.md, y lo único que
; cambia es en cuál de los cuatro pasos del ciclo entra cada evento.
;
; Va antes de `mover_eventos` a propósito: si una ruta forzada agarra a uno de
; éstos, la ranura le pisa la pose después y gana ella, que es la que lleva el
; contador de verdad.
.proc animar_quietos
.a8
.i16
    ; ¿Este mapa tiene alguno? Lo dice el relleno de la última familia de
    ; `anim_tabla`; sin esto habría que recorrer las cuarenta filas siempre.
    ldy #(ANIM_FAMILIAS - 1)
    jsr anim_donde
    lda f:anim_tabla + 7, x
    bne hay
    rts
hay:
    ldy #$0000
otra:
    cpy npc_total
    beq listo
    lda npc_buf + 14, y
    beq siguiente               ; escondido: no se dibuja
    lda npc_buf + 13, y
    bpl siguiente               ; el bit 7 es "quieto y animando"
    and #$7F
    dec a                       ; la velocidad, de 0 a 5
    phy
    rep #$20
.a16
    and #$00FF
    tax
    ; El tick que dibuja la referencia es `vueltas + 1` visto desde acá, que es
    ; el mismo número que mira la animación del ChipSet —ella lo lee después
    ; del `inc vueltas`—. Medido: sin el `inc`, el save point del mapa 8 se
    ; queda una columna atrás y son 76 pixeles. Sin los ticks congelados, como
    ; ella: ver `vueltas_congeladas`.
    lda vueltas
    sec
    sbc f:vueltas_congeladas
    inc a
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda anim_continua, x        ; cada cuántos cuadros cambia de columna
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
    and #(AGUA_CICLO_N - 1)
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ciclo_tres, x           ; la columna: 0, 1, 2 o de vuelta la 1
    ply
    sta temp + 3
    ; La pose: hacia dónde mira su página por tres, más la columna. Con la
    ; mirada fija —que es lo que pide `animation_type` 3— nadie la gira.
    jsr mirada_de_fila          ; la de su página, o la del giro
    sta temp + 2
    asl a
    clc
    adc temp + 2
    clc
    adc temp + 3
    sty npc_fila
    jsr subir_pose_npc
    ldy npc_fila
siguiente:
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
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
    pha
    sep #$20
.a8
    phk
    plb                         ; la tabla vive en el banco del código
    rep #$20
.a16
    pla
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
    ldy #0
    jsr se_ocupada
    beq elegida
    ldy #SE2_DESPL
    jsr se2_ocupada
    beq elegida
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
    plp
listo:
    plb
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

