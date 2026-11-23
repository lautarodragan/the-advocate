.segment "CODE"
.a8
.i16

; --- the interpreter: the map's tiles --------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `TileSubstitution`: from now on, where the grid says such-and-such block,
; another one is drawn. The instruction carries **several** pairs because RM2k
; substitutes by tile number and here the unit is the 16x16 block, which
; carries both layers together: an RM2k tile can be in as many blocks as it
; has combinations with the other layer. Which ones was worked out by the
; converter, see `Substitutions` in Wally's substitutions.rs.
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
    lda [code_ptr], y           ; how many pairs the instruction carries
    iny
    sta sub_remain
other_pair:
    sep #$20
.a8
    lda sub_remain
    beq sub_ready
    dec a
    sta sub_remain
    rep #$20
.a16
    lda [code_ptr], y           ; the outgoing block
    sta sub_of
    iny
    iny
    lda [code_ptr], y           ; and the incoming one
    sta sub_a
    iny
    iny
    jsr sub_layers              ; which of the window's layers this changes
    stz sub_has
    ldx #$0000
walk_sub:
    cpx sub_n
    beq add_sub
    lda sub_key, x
    cmp sub_of
    bne not_key
    inc sub_has
not_key:
    lda sub_value, x
    cmp sub_of
    bne continues_sub
    lda sub_a
    sta sub_value, x
continues_sub:
    inx
    inx
    bra walk_sub
add_sub:
    lda sub_has
    bne other_pair              ; the key was already there, and the loop set its value
    lda sub_n
    cmp #(SUB_MAX * 2)
    bcs other_pair              ; it does not fit. The converter refuses to emit
    tax                         ; a map that could get here: see SUB_MAX
    lda sub_of
    sta sub_key, x
    lda sub_a
    sta sub_value, x
    txa
    inc a
    inc a
    sta sub_n
    bra other_pair
sub_ready:
    ; And the window is redrawn by `sub_bulk`, at the end of this tick,
    ; with the layers `sub_layers` marked in `SUB_WANT`.
    jmp run_code::other

.endproc

; Which of the window's layers a pair changes: wherever the outgoing block
; shows, the incoming one will —see `op_tile_sub`—, so the layer of the
; tilemap changes if one of its four words differs between the two blocks'
; records. A bit in `SUB_WANT` per layer, which `sub_bulk` builds and the
; vblank uploads: a substitution of a lower tile usually leaves the upper
; layer's words as they were, and then only half the window goes up. A
; block substituted for itself —the control of `test_substitution.py`—
; marks none.
;
; The records are read with the data bank at theirs, `blocks_ptr`'s: a
; record does not cross a bank —the table lives behind the grid, in one—.
; A16 in and out; Y, the operand's cursor, comes back as it was.
.proc sub_layers
.a16
.i16
    phy
    lda sub_of
    cmp sub_a
    beq done
    asl a
    asl a
    asl a
    asl a                       ; 16 bytes a record: see `build_column`
    clc
    adc blocks_ptr
    tax
    lda sub_a
    asl a
    asl a
    asl a
    asl a
    clc
    adc blocks_ptr
    tay
    phb
    sep #$20
.a8
    lda blocks_ptr + 2
    pha
    plb
    rep #$20
.a16
    ; Bytes 0 to 7 are the background's four words, 8 to 15 the upper
    ; layer's: `blocks8_ptr` is this same table eight bytes on.
    lda a:0, x
    cmp a:0, y
    bne background
    lda a:2, x
    cmp a:2, y
    bne background
    lda a:4, x
    cmp a:4, y
    bne background
    lda a:6, x
    cmp a:6, y
    beq upper
background:
    sep #$20
.a8
    lda f:SUB_WANT
    ora #SUB_BG
    sta f:SUB_WANT
    rep #$20
.a16
upper:
    lda a:8, x
    cmp a:8, y
    bne above
    lda a:10, x
    cmp a:10, y
    bne above
    lda a:12, x
    cmp a:12, y
    bne above
    lda a:14, x
    cmp a:14, y
    beq compared
above:
    sep #$20
.a8
    lda f:SUB_WANT
    ora #SUB_ABOVE
    sta f:SUB_WANT
    rep #$20
.a16
compared:
    plb
done:
    ply
    rts
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
; `TERRAIN_PLANE` answers. Outside the map `TERRAIN_OUTSIDE` answers, which is
; the terrain of the **first tile of the ChipSet** and not that of any cell.
.proc op_terrain
.a8
.i16
    lda [code_ptr], y           ; the mode: 0 the written cell, 1 by variable,
    iny                         ; with VAR_REFRESH on top
    sta temp
    rep #$20
.a16
    lda [code_ptr], y
    sta cell_x
    iny
    iny
    lda [code_ptr], y
    sta cell_y
    iny
    iny
    sep #$20
.a8
    lda [code_ptr], y           ; the slot where it is stored
    iny
    sta temp + 1
    phy
    lda temp
    and #<~VAR_REFRESH
    beq terrain_cell
    ; By variable: what came in the opcode is two slots, and they are read now
    ; —it is the `ValueOrVariable` of `CommandStoreTerrainID`—.
    lda cell_x
    jsr var_read                ; returns with M at sixteen
.a16
    sta cell_x
    sep #$20
.a8
    lda cell_y
    jsr var_read
.a16
    sta cell_y
    sep #$20
.a8
terrain_cell:
    rep #$20
.a16
    lda cell_x                  ; `IsValid`: outside the map it answers the
    bmi terrain_outside         ; first tile's, not the neighboring cell's
    cmp map_width
    bcs terrain_outside
    lda cell_y
    bmi terrain_outside
    cmp map_height
    bcs terrain_outside
    sep #$20
.a8
    ldx map_ofs
    lda f:map_table + M_TERRAIN_PLANE, x
    bne terrain_set             ; a single terrain in the whole map
    jsr cell_ptr
    rep #$20
.a16
    lda [cells_ptr]             ; which block the cell is, already substituted
    and cell_mask
    jsr cell_replaced
    sta temp + 2
    ; The table lives outside bank 0, so it is read with a 24-bit pointer, and
    ; the only free one here is `cells_ptr` —which has already been used and
    ; is temporary anyway: everyone repositions it before reading—.
    ldx map_ofs
    lda f:map_table + M_PTR_BLOCK_TERRAIN, x
    sta cells_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_BLOCK_TERRAIN + 2, x
    sta cells_ptr + 2
    ldy temp + 2
    lda [cells_ptr], y
    bra terrain_set
terrain_outside:
    sep #$20
.a8
    ldx map_ofs
    lda f:map_table + M_TERRAIN_OUTSIDE, x
terrain_set:
    sta temp + 2                ; `var_write` takes it from here
    stz temp + 3
    lda temp                    ; the mode, which carries the refresh bit:
    xba                         ; `cell_ptr` and `cell_replaced` do
    lda temp + 1                ; not touch `temp`
    jsr var_write               ; with its refresh, if the mode asks for it
    ply
    jmp run_code::other

.endproc

; `ChangeEncounterSteps`: only the entry point. The body is `encounter_steps`,
; outside bank 0, which reads its operands and advances the cursor itself.
.proc op_encounter_steps
    jsl f:encounter_steps
    jmp run_code::other

.endproc

; `ChangePBG`: only the entry point, like the one above. The body is
; `pano_change`, in pano.s, which reads the rest of its operands.
.proc op_panorama
    lda [code_ptr], y
    iny
    jsl f:pano_change
    jmp run_code::other
.endproc

; `ChangeMapTileset`: only the entry point. The body is `tileset_change`, in
; tileset.s, which reads its operand; a cartridge with no map that swaps its
; ChipSet assembles none, and the operand is skipped here.
.proc op_change_tileset
.ifdef tileset_variants
    jsl f:tileset_change
.else
    iny                         ; the variant
.endif
    jmp run_code::other
.endproc
