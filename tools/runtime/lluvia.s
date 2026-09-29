.segment "CODE"

; --- la lluvia ------------------------------------------------------------------
;
; `Game_Screen::UpdateRain` y `Weather::DrawRain`, con la regla de RM2k sobre
; la pantalla de 256x224: ver OP_WEATHER en eventos.py, que tiene el porqué. El
; estado vive en la RAM lejana: el tipo y la fuerza del clima, cuántas gotas
; hay y el azar de la lluvia —un xorshift propio, sembrado cada vez que el
; clima cambia— en `FAR_CLIMA`, y tres bytes por gota —x, y y la vida— en
; `FAR_LLUVIA`. La x y la y son de la superficie de 256x256 que va pegada al
; mapa, así que un byte alcanza y el paso de cada cuadro da la vuelta solo; en
; pantalla es eso menos el scroll. El clima no viaja en la partida: al cargar
; no llueve.
;
; `lluvia_tick` y `lluvia_oam` corren en cada cuadro que llueve y leen con el
; direccionamiento largo, que va de a una instrucción por byte: con la
; ventana de WMADD cada gota pagaba apuntarla.
FAR_CLIMA  = $2EF0
FAR_LLUVIA = $2F00
CLIMA_L    = $7E0000 + FAR_CLIMA
LLUVIA_L   = $7E0000 + FAR_LLUVIA

; El clima en cero: sin lluvia. En el reset.
.proc clima_limpiar
.a8
.i16
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #5
otro:
    stz WMDATA
    dex
    bne otro
    rts
.endproc

; `SetWeatherEffect`: `temp` el tipo, `temp + 1` la fuerza. Si no cambia nada
; no toca nada; si cambia, las gotas arrancan apagadas y el azar vuelve a su
; semilla. Se llama desde el intérprete, con el banco de datos donde esté el
; bytecode: sólo toca registros y la RAM baja.
.proc clima_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    cmp temp
    bne cambia
    lda WMDATA
    cmp temp + 1
    bne cambia
    rts
cambia:
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    lda temp
    sta WMDATA
    lda temp + 1
    sta WMDATA
    lda temp
    cmp #CLIMA_LLUVIA
    bne ninguna
    lda temp + 1
    beq debil
    cmp #1
    beq media
    lda #LLUVIA_GOTAS_2
    bra cuantas
media:
    lda #LLUVIA_GOTAS_1
    bra cuantas
debil:
    lda #LLUVIA_GOTAS_0
    bra cuantas
ninguna:
    lda #0
cuantas:
    sta WMDATA
    lda #<LLUVIA_SEMILLA
    sta WMDATA
    lda #>LLUVIA_SEMILLA
    sta WMDATA
    ; Todas apagadas.
    rep #$20
.a16
    lda #FAR_LLUVIA
    sta WMADDL
    sep #$20
.a8
    ldx #(LLUVIA_GOTAS_MAX * 3)
apagar:
    stz WMDATA
    dex
    bne apagar
    rts
.endproc

; El azar de la lluvia, en `comp_mask`: el mismo xorshift que
; `eventos.azar_siguiente`. Vuelve con el número nuevo en A, de dieciséis.
.proc lluvia_azar
.a8
.i16
    rep #$20
.a16
    lda comp_mask
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor comp_mask
    sta comp_mask
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor comp_mask
    sta comp_mask
    xba
    and #$FF00
    eor comp_mask
    sta comp_mask
    rts
.endproc

; Un cuadro de la lluvia —`Game_Screen::UpdateRain`—: la gota viva baja y se
; corre, y la que se quedó sin vida vuelve a nacer donde diga el azar. `comp_col`
; cuenta las gotas y `comp_mask` lleva el azar; son del compositor de
; mensajes, que las recalcula en cada carácter. X es la gota, de a tres bytes.
.proc lluvia_tick
.a8
.i16
    lda f:CLIMA_L + 2
    bne hay
    rts
hay:
    sta comp_col                ; cuántas
    rep #$20
.a16
    lda f:CLIMA_L + 3
    sta comp_mask
    sep #$20
.a8
    ldx #0
gota:
    lda f:LLUVIA_L + 2, x       ; la vida
    beq apagada
    ; Viva: baja cuatro, corre uno a la izquierda, y le queda uno menos.
    dec a
    sta f:LLUVIA_L + 2, x
    lda f:LLUVIA_L, x
    dec a
    sta f:LLUVIA_L, x
    lda f:LLUVIA_L + 1, x
    clc
    adc #4
    sta f:LLUVIA_L + 1, x
    bra siguiente
apagada:
    ; Nace con LLUVIA_NACE de 256 de chance, en un lugar al azar.
    ; `lluvia_azar` vuelve con A de dieciséis y no toca X.
    jsr lluvia_azar
    sep #$20
.a8
    cmp #LLUVIA_NACE
    bcs siguiente
    lda #LLUVIA_VIDA
    sta f:LLUVIA_L + 2, x
    jsr lluvia_azar
    sep #$20
.a8
    sta f:LLUVIA_L, x
    jsr lluvia_azar
    sep #$20
.a8
    sta f:LLUVIA_L + 1, x
siguiente:
    inx
    inx
    inx
    dec comp_col
    bne gota
    rep #$20
.a16
    lda comp_mask
    sta f:CLIMA_L + 3           ; el azar, de vuelta a su lugar
    sep #$20
.a8
    rts
.endproc

; Las gotas en OAM: dos objetos de 8x8 por gota viva, con prioridad 2, al
; final de todo —cualquier personaje las tapa— y hasta que se llene la OAM.
; Un mapa sin lugar para sus colores tiene `M_LLUVIA_BASE` en cero y no dibuja
; lluvia. Ver `gotas_en_oam` en snes_expect.py, que tiene la regla de qué se
; descarta.
;
; No pasa por `emit_object`, que para 150 objetos era más de media pantalla:
; la X de una gota queda siempre entre 0 y 255 —el noveno bit y el tamaño son
; cero—, así que se escribe directo. X es la gota y Y el objeto.
.proc lluvia_oam
.a8
.i16
    ldx mapa_ofs
    lda f:mapa_tabla + M_LLUVIA_BASE, x
    ora f:mapa_tabla + M_LLUVIA_BASE + 1, x
    bne con_gotas
    rts
con_gotas:
    lda f:CLIMA_L + 2
    bne hay
    rts
hay:
    sta comp_col                ; cuántas
    rep #$20
.a16
    lda f:mapa_tabla + M_LLUVIA_BASE, x
    sta comp_base               ; el primer tile
    sep #$20
.a8
    ; vhoopppN: prioridad 2 y la paleta de las gotas; el noveno bit va aparte.
    lda f:mapa_tabla + M_LLUVIA_PAL, x
    and #$07
    asl a
    ora #$20
    sta comp_color
    stz comp_dup + 3
    ldx #0
gota:
    lda f:LLUVIA_L + 2, x
    bne viva
    jmp siguiente
viva:
    ; El tono: 0 con nueve o más de vida, 1 con cinco o más, 2 si no.
    cmp #9
    bcs tono0
    cmp #5
    bcs tono1
    lda #2
    bra tono
tono0:
    lda #0
    bra tono
tono1:
    lda #1
tono:
    sta comp_dup + 2
    ; En pantalla: menos el scroll del mapa, en ocho bits.
    lda f:LLUVIA_L, x
    sec
    sbc pantalla_x
    sta comp_dup
    lda f:LLUVIA_L + 1, x
    sec
    sbc camara_y
    sta comp_dup + 1
    stz comp_fila               ; la mitad: 0 arriba, 1 abajo
mitad:
    lda comp_dup + 1
    cmp #224
    bcc se_ve
    cmp #248
    bcs se_ve                   ; asoma por arriba
    jmp otra_mitad
se_ve:
    rep #$20
.a16
    lda oam_slot
    cmp #128
    bcc queda_lugar
    sep #$20
.a8
    rts
.a16
queda_lugar:
    asl a
    asl a
    tay
    ; El tile: base + 16 * mitad + tono, de nueve bits.
    lda comp_fila
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc comp_dup + 2
    clc
    adc comp_base
    sep #$20
.a8
    sta oam + 2, y
    xba
    and #$01
    ora comp_color
    sta oam + 3, y
    lda comp_dup
    sta oam, y
    lda comp_dup + 1
    sta oam + 1, y
    ; Sus dos bits en la tabla chica, los dos en cero: `push_high`.
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    lda oam_slot
    and #$03
    cmp #$03
    bne sin_byte
    phx
    jsr store_high
    plx
sin_byte:
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
otra_mitad:
    lda comp_dup + 1
    clc
    adc #8
    sta comp_dup + 1
    inc comp_fila
    lda comp_fila
    cmp #2
    bcs siguiente
    jmp mitad
siguiente:
    inx
    inx
    inx
    dec comp_col
    beq listo
    jmp gota
listo:
    rts
.endproc


