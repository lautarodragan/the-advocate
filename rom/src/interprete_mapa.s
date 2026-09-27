.segment "CODE"
.a8
.i16

; --- el intérprete: los tiles del mapa -------------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `TileSubstitution`: de ahora en más, donde la grilla diga tal bloque se
; dibuja tal otro. La instrucción trae **varios** pares porque RM2k sustituye
; por número de tile y acá la unidad es el bloque de 16x16, que lleva las dos
; capas juntas: un tile de RM2k puede estar en tantos bloques como
; combinaciones tenga con la otra capa. Cuáles son lo resolvió el conversor,
; ver `Sustituciones` en snes_convert.py.
;
; La tabla se aplica como `DoSubstitute` de easyrpg, que recorre la traducción
; entera y cambia **los valores** que sean el bloque viejo, no las claves:
;
;   * todo par que hoy apunte al que sale pasa a apuntar al que entra, que es
;     lo que hace que sustituir A→B y después B→A deshaga la primera en vez de
;     dejar dos reglas peleándose;
;   * y si ninguna clave es el que sale, se agrega el par, que es la entrada
;     identidad que la tabla no guarda por no ocupar lugar.
.proc op_tile_sub
.a8
.i16
    lda [cod_ptr], y            ; cuántos pares trae la instrucción
    iny
    sta sub_quedan
otro_par:
    sep #$20
.a8
    lda sub_quedan
    beq sub_listo
    dec a
    sta sub_quedan
    rep #$20
.a16
    lda [cod_ptr], y            ; el bloque que sale
    sta sub_de
    iny
    iny
    lda [cod_ptr], y            ; y el que entra
    sta sub_a
    iny
    iny
    stz sub_hay
    ldx #$0000
recorrer_sub:
    cpx sub_n
    beq agregar_sub
    lda sub_clave, x
    cmp sub_de
    bne no_es_clave
    inc sub_hay
no_es_clave:
    lda sub_valor, x
    cmp sub_de
    bne sigue_sub
    lda sub_a
    sta sub_valor, x
sigue_sub:
    inx
    inx
    bra recorrer_sub
agregar_sub:
    lda sub_hay
    bne otro_par                ; la clave ya estaba, y el lazo le puso el valor
    lda sub_n
    cmp #(SUB_MAX * 2)
    bcs otro_par                ; no entra. El conversor se niega a emitir un
    tax                         ; mapa que pueda llegar acá: ver SUB_MAX
    lda sub_de
    sta sub_clave, x
    lda sub_a
    sta sub_valor, x
    txa
    inc a
    inc a
    sta sub_n
    bra otro_par
sub_listo:
    rep #$20
.a16
    lda #WINDOW_COLS            ; y la ventana se rehace de a una columna por
    sta sub_refresco            ; cuadro: ver `sub_refresco`
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; `StoreTerrainID`: el terreno de una celda a una variable.
;
; **El terreno sale del tile de la capa de abajo**, no de la alta —"RPG_RT
; always uses the terrain of the first lower tile"—, así que acá sale del
; bloque, que es lo que la ROM tiene: el conversor ya metió el terreno en la
; clave del bloque, y emitió un byte por bloque. Y como sale del bloque, una
; `TileSubstitution` puesta lo cambia, que es lo que hace `GetTerrainTag` al
; pasar por `map_info.lower_tiles`.
;
; Un mapa con un solo terreno —los 328 de este juego— no lleva tabla: la
; contesta `TERRENO_PLANO`. Fuera del mapa contesta `TERRENO_FUERA`, que es el
; terreno del **primer tile del ChipSet** y no el de ninguna celda.
.proc op_terrain
.a8
.i16
    lda [cod_ptr], y            ; el modo: 0 la celda escrita, 1 por variable,
    iny                         ; con VAR_REFRESCO arriba
    sta temp
    rep #$20
.a16
    lda [cod_ptr], y
    sta celda_x
    iny
    iny
    lda [cod_ptr], y
    sta celda_y
    iny
    iny
    sep #$20
.a8
    lda [cod_ptr], y            ; la ranura donde se guarda
    iny
    sta temp + 1
    phy
    lda temp
    and #<~VAR_REFRESCO
    beq terreno_celda
    ; Por variable: lo que vino en el opcode son dos ranuras, y se leen ahora
    ; —es el `ValueOrVariable` de `CommandStoreTerrainID`—.
    lda celda_x
    jsr var_leer                ; vuelve con M en dieciséis
.a16
    sta celda_x
    sep #$20
.a8
    lda celda_y
    jsr var_leer
.a16
    sta celda_y
    sep #$20
.a8
terreno_celda:
    rep #$20
.a16
    lda celda_x                 ; `IsValid`: fuera del mapa contesta el del
    bmi terreno_afuera          ; primer tile, no el de la celda de al lado
    cmp mapa_ancho
    bcs terreno_afuera
    lda celda_y
    bmi terreno_afuera
    cmp mapa_alto
    bcs terreno_afuera
    sep #$20
.a8
    ldx mapa_ofs
    lda f:mapa_tabla + M_TERRENO_PLANO, x
    bne terreno_puesto          ; un solo terreno en todo el mapa
    jsr ptr_de_celda
    rep #$20
.a16
    lda [celdas_ptr]            ; qué bloque es la celda, ya sustituido
    jsr celda_sustituida
    sta temp + 2
    ; La tabla vive fuera del banco 0, así que se lee con un puntero de 24
    ; bits, y el único que hay libre acá es `celdas_ptr` —que ya se usó y es
    ; de todos modos temporario: cada quien lo reposiciona antes de leer—.
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_BLOQUE_TERRENO + 2, x
    sta celdas_ptr + 2
    ldy temp + 2
    lda [celdas_ptr], y
    bra terreno_puesto
terreno_afuera:
    sep #$20
.a8
    ldx mapa_ofs
    lda f:mapa_tabla + M_TERRENO_FUERA, x
terreno_puesto:
    sta temp + 2                ; de acá lo saca `var_escribir`
    stz temp + 3
    lda temp                    ; el modo, que trae el bit del refresco:
    xba                         ; `ptr_de_celda` y `celda_sustituida` no
    lda temp + 1                ; tocan `temp`
    jsr var_escribir            ; con su refresco, si el modo lo pide
    ply
    jmp correr_codigo::otro

.endproc

; `ChangeEncounterSteps`: sólo la entrada. El cuerpo es `encuentro_pasos`,
; fuera del banco 0, que lee sus operandos y avanza el cursor él mismo.
.proc op_encounter_steps
    jsl f:encuentro_pasos
    jmp correr_codigo::otro

.endproc
