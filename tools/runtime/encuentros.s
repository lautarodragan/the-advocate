.segment "FAR"

; --- los encuentros al azar, fuera del banco 0 -------------------------------
;
; Lo que RM2k hace, de `Game_Player::UpdateEncounterSteps`, `GetEncountersAt` y
; `PrepareEncounter`, y escrito igual en `eventos.Encuentros`, que es contra lo
; que se compara:
;
;   * cada paso del héroe **con el pad** —una ruta forzada sale antes, por
;     `IsMoveRouteOverwritten`— suma el `encounter_rate` del terreno y mira si
;     salió un encuentro;
;   * la chance es `pmod / encounter_steps`, con `pmod` una potencia de dos que
;     sube a medida que se camina sin que salga nada;
;   * si sale, queda pendiente y se cobra en el cuadro siguiente, con el héroe
;     ya parado: se juntan las tropas del mapa y las de cada área que tape su
;     celda, y se elige una al azar.
;
; **Todas las cuentas son enteras**, que es lo que la consola puede hacer: el
; conversor precalcula `1 / encounter_steps` en 1/65536 —`enc_base`— y en qué
; paso se cruza cada fila de la tabla —`enc_umbral_n`—, así que acá no hay ni
; una división. Ver `eventos.enc_base` y `eventos.enc_umbrales_de_paso`, que son
; las mismas cuentas del otro lado.
;
; Vive acá y no en el banco 0 porque allá quedaban ochenta y cinco bytes: lo
; único que queda del otro lado son los cuatro `jsl` y el puente a la pelea.
; **El banco de datos es $7E mientras esto corre**, como en la batalla: así el
; estado de $3900 se lee con direccionamiento absoluto y la RAM baja —`temp`,
; `tile_x`, `mapa_actual`— se sigue leyendo igual, porque en el banco $7E las
; direcciones de $0000 a $1FFF **son** las del banco 0.

; La semilla del azar de los encuentros, en el reset. Es otra que la del mapa y
; otra que la de la pelea: ver `enc_azar`.
.proc encuentro_arranque
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda #ENC_SEMILLA
    sta ENC_SEM
    sep #$20
.a8
    plb
    rtl
.endproc

; El registro del mapa actual, o que este mapa no tiene encuentros.
.proc encuentro_mapa
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    ldx mapa_actual
    lda f:enc_mapa, x
    sta ENC_REG
    cmp #ENC_SIN
    beq sin_encuentros
    rep #$20
.a16
    and #$00FF
    pha
    ; Los umbrales del registro, a la RAM: los siete bytes y el de relleno.
    asl a
    asl a
    asl a
    tax
    ldy #0
copiar:
.a16
    lda f:enc_umbral_n, x
    sta ENC_UMB, y
    inx
    inx
    iny
    iny
    cpy #ENC_STRIDE
    bcc copiar
    pla
    asl a
    tax
    lda f:enc_base, x
    bra con_base
sin_encuentros:
.a8
    rep #$20
.a16
    lda #0
con_base:
.a16
    sta ENC_BASE
    sep #$20
.a8
    ; Y el acumulado en cero, como en todo `MoveTo`: entrar a un mapa es uno.
    stz ENC_N
    stz ENC_IDX
    stz ENC_PIDE
    plb
    ply
    plx
    rtl
.endproc

; `ChangeEncounterSteps`, el cuerpo de OP_ENCOUNTER_STEPS: el `1 / pasos` nuevo
; y los siete umbrales que salen de los mismos pasos, que el conversor ya
; calculó —ver `eventos.enc_base` y `eventos.enc_umbrales_de_paso`—. Cero es
; apagarlos, que es lo que pide el viaje de Dalia a Tasgarde. No toca lo
; caminado: `SetEncounterSteps` de easyrpg tampoco.
;
; En un mapa sin tropas ni áreas no hace nada, que es lo que hace
; `eventos.Encuentros.poner_pasos`: sin zonas no hay encuentro que prender.
; Tampoco dura más que el mapa, como en RM2k: `encuentro_mapa` vuelve a poner
; los del mapa en cada carga.
;
; Se entra con `jsl` desde el intérprete, con Y en el operando y el banco de
; datos del bytecode; se vuelve con Y después de los diez bytes.
.proc encuentro_pasos
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda ENC_REG
    cmp #ENC_SIN
    beq saltear
    rep #$20
.a16
    lda [cod_ptr], y
    sta ENC_BASE
    iny
    iny
    ldx #0
umbral:
.a16
    lda [cod_ptr], y            ; de a dos: los siete y el relleno
    sta ENC_UMB, x
    iny
    iny
    inx
    inx
    cpx #ENC_STRIDE
    bcc umbral
    sep #$20
.a8
    plb
    rtl
saltear:
.a8
    rep #$20
.a16
    tya
    clc
    adc #(2 + ENC_STRIDE)
    tay
    sep #$20
.a8
    plb
    rtl
.endproc

; El `SetTotalEncounterRate(0)` de `Game_Player::MoveTo`: un teletransporte
; —una puerta, un `Teleport`, un `ChangeEventLocation` sobre el héroe— borra lo
; caminado. No toca `ENC_BASE`: el mapa puede ser el mismo.
.proc encuentro_mover
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    stz ENC_N
    stz ENC_IDX
    stz ENC_PIDE
    plb
    rtl
.endproc

; Un paso del héroe. Entra y sale con el acumulador en ocho bits.
.proc encuentro_paso
.a8
.i16
    phx
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda ENC_BASE
    bne hay
    ; Apagados: `encounter_steps` en cero, o un mapa sin tropas ni áreas.
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    bra fin
hay:
.a16
    sep #$20
.a8
    lda ENC_N
    inc a
    beq sigue_arriba            ; 255 pasos sin encuentro: no da la vuelta
    sta ENC_N
sigue_arriba:
.a8
    ; La fila de la tabla, que **no baja nunca**: es el `last_encounter_idx` de
    ; allá. X apunta al umbral de la fila que sigue, en `ENC_UMB`.
    rep #$20
.a16
    lda ENC_IDX
    and #$00FF
    tax
    sep #$20
.a8
sube:
.a8
    lda ENC_IDX
    cmp #(ENC_FILAS - 1)
    bcs con_fila                ; la última fila no sube más
    lda ENC_N
    cmp ENC_UMB, x              ; ¿llegó al umbral de la que sigue?
    bcc con_fila
    inx
    lda ENC_IDX
    inc a
    sta ENC_IDX
    bra sube
con_fila:
.a8
    ; El umbral del azar: `base` corrido por el `pmod` de la fila. Las filas 0
    ; a 3 son 1/16, 1/8, 1/4 y 1/2; las 4 a 7 son 2, 4, 8 y 16.
    rep #$20
.a16
    lda ENC_IDX
    and #$00FF
    tax
    lda ENC_BASE
    cpx #4
    bcs a_la_izquierda
derecha:
.a16
    lsr a
    inx
    cpx #4
    bcc derecha
    bra con_umbral
a_la_izquierda:
.a16
    dex
    dex
    dex
izquierda:
.a16
    asl a
    bcs siempre                 ; pasó de 1: es certeza, como `PercentChance`
    dex
    bne izquierda
con_umbral:
.a16
    sta temp
    jsr enc_azar
    cmp temp
    bcc salio
    sep #$20
.a8
    bra fin
siempre:
.a16
salio:
.a16
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    lda #1
    sta ENC_PIDE
fin:
.a8
    plb
    plx
    rtl
.endproc

; ¿Hay un encuentro pendiente que pelear acá? Vuelve con A en ocho bits: 1 si
; hay que pelear, y con la tropa ya puesta en `BA_TROPA`.
;
; Es `PrepareEncounter`: si en la celda no tapa ninguna zona, el pendiente se
; consume y no pasa nada, que es lo que hace allá al volver `false`.
.proc encuentro_probar
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    lda ENC_PIDE
    bne pendiente
    jmp no_hay
pendiente:
.a8
    stz ENC_PIDE
    lda ENC_REG
    cmp #ENC_SIN
    bne con_registro
    jmp no_hay
con_registro:
.a8
    ; El rango de zonas del mapa: la suya y una por área.
    jsr enc_zonas
    ; Primera pasada: cuántas tropas tapan la celda del héroe.
    rep #$20
.a16
    lda #0
    sta comp_and
contar:
.a16
    lda temp
    cmp temp + 2
    bcs contadas
    jsr enc_tapa
    bcc sin_tapar
    sep #$20
.a8
    lda f:enc_tropa_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    sta comp_and
sin_tapar:
.a16
    inc temp
    bra contar
contadas:
.a16
    lda comp_and
    bne hay_tropas
    sep #$20
.a8
    bra no_hay
hay_tropas:
.a16
    ; Una al azar, `Rand::GetRandomNumber(0, n - 1)`: el resto de dividir el
    ; azar por cuántas hay. La división es la de toda la vida, a mano, porque
    ; el 65816 no divide y la de la pelea vive en otro banco.
    sta comp_and + 2
    jsr enc_azar
    sta comp_or23
    lda #0
    sta comp_or23 + 2
    ldy #16
divide:
.a16
    asl comp_or23
    rol comp_or23 + 2
    lda comp_or23 + 2
    cmp comp_and + 2
    bcc sin_restar
    sec
    sbc comp_and + 2
    sta comp_or23 + 2
sin_restar:
.a16
    dey
    bne divide
    lda comp_or23 + 2
    sta comp_and                ; cuántas hay que saltear
    ; Segunda pasada: la que le toca.
    sep #$20
.a8
    jsr enc_zonas
    rep #$20
.a16
elegir:
.a16
    lda temp
    cmp temp + 2
    bcs no_hay16                ; no puede pasar: el total salió de estas zonas
    jsr enc_tapa
    bcc sigue_eligiendo
    sep #$20
.a8
    lda f:enc_tropa_n, x
    rep #$20
.a16
    and #$00FF
    sta comp_or23
    lda comp_and
    cmp comp_or23
    bcc es_de_esta
    sec
    sbc comp_or23
    sta comp_and
sigue_eligiendo:
.a16
    inc temp
    bra elegir
es_de_esta:
.a16
    sep #$20
.a8
    lda f:enc_tropa_ini, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    asl a
    tax
    lda f:enc_tropa, x
    sta BA_TROPA
    sep #$20
.a8
    lda #1
    sta ESC_ORIGEN              ; el fondo de la pelea, el del mapa
    bra fin
no_hay16:
.a16
    sep #$20
.a8
no_hay:
.a8
    lda #0
fin:
.a8
    plb
    ply
    plx
    rtl
.endproc

; De qué zona a qué zona son las del mapa: `temp` la primera y `temp + 2` una
; más que la última. Entra con el acumulador en ocho bits y sale igual.
.proc enc_zonas
.a8
.i16
    lda ENC_REG
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enc_zona_ini, x
    rep #$20
.a16
    and #$00FF
    sta temp
    sta temp + 2
    sep #$20
.a8
    lda f:enc_zona_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    rts
.endproc

; ¿La zona `temp` tapa la celda donde está parado el héroe? Vuelve con el
; acarreo puesto si sí, y con X en el número de zona, que es lo que indexan las
; tablas de un byte. El rectángulo es **semiabierto** —`l <= x < r`—, que es lo
; que dice `Rect::IsOutOfBounds` de easyrpg con el héroe como un rectángulo de
; una celda.
.proc enc_tapa
.a16
.i16
    lda temp
    asl a
    tax
    lda tile_x
    cmp f:enc_izq, x
    bcc afuera
    cmp f:enc_der, x
    bcs afuera
    lda tile_y
    cmp f:enc_arr, x
    bcc afuera
    cmp f:enc_aba, x
    bcs afuera
    ldx temp
    sec
    rts
afuera:
.a16
    ldx temp
    clc
    rts
.endproc

; El paso del xorshift de los encuentros: el mismo de `azar_siguiente` y de
; `ba_azar`, sobre `ENC_SEM`, que tiene **semilla propia**. Caminar no le corre
; el azar al mapa: un `ControlVars` al azar tiene que dar lo mismo con
; encuentros y sin ellos. Es `eventos.Encuentros._azar`.
.proc enc_azar
.a16
.i16
    lda ENC_SEM
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor ENC_SEM
    sta ENC_SEM
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor ENC_SEM
    sta ENC_SEM
    xba
    and #$FF00
    eor ENC_SEM
    sta ENC_SEM
    rts
.endproc

