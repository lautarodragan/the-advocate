.segment "CODE"
.a8
.i16

; --- the interpreter: the map's tiles --------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; `TileSubstitution`: from now on, where the grid says such-and-such block,
; another one is drawn. The instruction carries **several** pairs because RM2k
; substitutes by tile number and here the unit is the 16x16 block, which
; carries both layers together: an RM2k tile can be in as many blocks as it
; has combinations with the other layer. Which ones was worked out by the
; converter, see `Sustituciones` in snes_convert.py.
;
; The table is applied like easyrpg's `DoSubstitute`, which walks the whole
; translation and changes **the values** that are the old block, not the keys:
;
;   * every pair that today points to the outgoing one now points to the
;     incoming one, which is what makes substituting A→B and then B→A undo
;     the first instead of leaving two rules fighting;
;   * and if no key is the outgoing one, the pair is added, which is the
;     identity entry the table does not store so as not to take up room.
.proc op_tile_sub
.a8
.i16
    lda [cod_ptr], y            ; how many pairs the instruction carries
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
    lda [cod_ptr], y            ; the outgoing block
    sta sub_de
    iny
    iny
    lda [cod_ptr], y            ; and the incoming one
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
    bne otro_par                ; the key was already there, and the loop set its value
    lda sub_n
    cmp #(SUB_MAX * 2)
    bcs otro_par                ; it does not fit. The converter refuses to emit
    tax                         ; a map that could get here: see SUB_MAX
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
    lda #WINDOW_COLS            ; and the window is redrawn one column per
    sta sub_refresco            ; frame: see `sub_refresco`
    sep #$20
.a8
    jmp run_code::otro

.endproc

; `StoreTerrainID`: a cell's terrain into a variable.
;
; **The terrain comes from the lower layer's tile**, not the upper one's
; —"RPG_RT always uses the terrain of the first lower tile"—, so here it comes
; from the block, which is what the ROM has: the converter already put the
; terrain into the block's key, and emitted one byte per block. And since it
; comes from the block, a `TileSubstitution` in effect changes it, which is
; what `GetTerrainTag` does by going through `map_info.lower_tiles`.
;
; A map with a single terrain —all 328 in this game— carries no table:
; `TERRENO_PLANO` answers. Outside the map `TERRENO_FUERA` answers, which is
; the terrain of the **first tile of the ChipSet** and not that of any cell.
.proc op_terrain
.a8
.i16
    lda [cod_ptr], y            ; the mode: 0 the written cell, 1 by variable,
    iny                         ; with VAR_REFRESCO on top
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
    lda [cod_ptr], y            ; the slot where it is stored
    iny
    sta temp + 1
    phy
    lda temp
    and #<~VAR_REFRESCO
    beq terreno_celda
    ; By variable: what came in the opcode is two slots, and they are read now
    ; —it is the `ValueOrVariable` of `CommandStoreTerrainID`—.
    lda celda_x
    jsr var_read                ; returns with M at sixteen
.a16
    sta celda_x
    sep #$20
.a8
    lda celda_y
    jsr var_read
.a16
    sta celda_y
    sep #$20
.a8
terreno_celda:
    rep #$20
.a16
    lda celda_x                 ; `IsValid`: outside the map it answers the
    bmi terreno_afuera          ; first tile's, not the neighboring cell's
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
    bne terreno_puesto          ; a single terrain in the whole map
    jsr ptr_de_celda
    rep #$20
.a16
    lda [celdas_ptr]            ; which block the cell is, already substituted
    jsr celda_sustituida
    sta temp + 2
    ; The table lives outside bank 0, so it is read with a 24-bit pointer, and
    ; the only free one here is `celdas_ptr` —which has already been used and
    ; is temporary anyway: everyone repositions it before reading—.
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
    sta temp + 2                ; `var_write` takes it from here
    stz temp + 3
    lda temp                    ; the mode, which carries the refresh bit:
    xba                         ; `ptr_de_celda` and `celda_sustituida` do
    lda temp + 1                ; not touch `temp`
    jsr var_write            ; with its refresh, if the mode asks for it
    ply
    jmp run_code::otro

.endproc

; `ChangeEncounterSteps`: only the entry point. The body is `encounter_steps`,
; outside bank 0, which reads its operands and advances the cursor itself.
.proc op_encounter_steps
    jsl f:encounter_steps
    jmp run_code::otro

.endproc
