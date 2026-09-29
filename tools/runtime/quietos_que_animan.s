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
    ; El tick que se dibuja es `vueltas + 1` visto desde acá, que es el mismo
    ; número que mira la animación del ChipSet —ella lo lee después del `inc
    ; vueltas`—. Medido: sin el `inc`, el save point del mapa 8 se
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

