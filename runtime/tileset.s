; --- ChangeMapTileset: the map with another ChipSet ---------------------------
;
; RPG_RT's `Game_Map::SetChipset`: from here on, and until the next map is
; loaded, the same cells are drawn and walked with another ChipSet —its
; graphics, its passability, its terrain and its animation—. The converter
; made each ChipSet a map's own pages swap in into a **variant** of the map,
; and the bytecode names it by its place: 0 the map's own, 1 on its others.
; See `variants.rs` in rm2k-snes-convert.
;
; **A variant is a whole record of `map_table`**, behind the maps', a copy
; of the map's with what the ChipSet changes pointing to its own blocks, and
; an entry of `anim_table` in the same place. So swapping one in is pointing
; `map_ofs` at it: everything that reads the record —the window's strips,
; the animation, `back_to_map` after a menu and `back_from_battle`, which
; decompresses the grid and the record's block table again— follows without
; knowing. `enter_map` points it back at the map's own record, which is
; RM2k's "until the next map is loaded"; a saved game does not keep it —see
; the divergence in the book—.
;
; **The grid does not change**: the converter numbered the map's blocks by
; every ChipSet at once, so each variant's block table has the map's size,
; and goes where the map's does, behind the grid with the bytecode behind
; it. Swapping is decompressing it over the map's —its own stream,
; `tileset_table`'s pointer—, and, for a variant that draws otherwise,
; uploading its tiles, colours and animation and filling the window again,
; with the screen off for the tick, as `big_load` does. One whose ChipSet
; draws the map the same —Vampires Dawn's bat, which only opens every cell—
; swaps its blocks alone, with the screen on: nothing reaches VRAM.
;
; Asking for the one that is already in does nothing: Vampires Dawn's bat
; asks for it every frame its switch is on.
;
; Only assembled in a cartridge with a map that swaps its ChipSet:
; `tileset_variants` comes in the `.inc`. In the rest `op_change_tileset`
; skips its operand, and the ROM is what it was.
.ifdef tileset_variants
.pushseg
.segment "FAR3"
.a8
.i16

; From `op_change_tileset`, with Y on its operand: the variant. Leaves Y past
; it.
;
; **What is uploaded depends on both ends**: a variant that does not draw
; otherwise than the map leaves VRAM as it is only if the one it replaces
; does not either. From a variant that draws, coming back to the map's own
; or going to one that does not draw is uploading the map's drawing again.
.proc tileset_change
.a8
.i16
    lda [code_ptr], y
    iny
    phy
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
.assert TILESET_STRIDE = 8, error, "the three shifts above are TILESET_STRIDE"
    pha                         ; the variant's place in the map's entries
    lda map_current
    asl a
    tax
    lda f:tileset_maps, x
    cmp #$FFFF
    bne has_variants
    jmp none                    ; a map with no variants
has_variants:
    sta temp                    ; where its entries start
    tax
    lda f:tileset_table + 6, x  ; how many: the byte, and a zero
    and #$00FF
    asl a
    asl a
    asl a
    cmp 1, s
    beq past                    ; a variant past the map's: the converter does
    bcs within                  ; not compile one, but a page carried from
past:                           ; another map could get here
    jmp none
within:
    clc
    adc temp
    sta temp + 2                ; where they end
    ; Whether the one in now draws otherwise: its entry, by its record.
    ldx temp
find:
    lda f:tileset_table, x
    cmp map_ofs
    beq found
    txa
    clc
    adc #TILESET_STRIDE
    tax
    cpx temp + 2
    bcc find
    lda #1                      ; none of the map's: upload, to be sure
    bra old_known
found:
    lda f:tileset_table + 5, x
    and #$00FF
old_known:
    sta temp + 2
    lda temp
    clc
    adc 1, s
    tax
    pla
    lda f:tileset_table, x      ; the record's offset in `map_table`
    cmp map_ofs
    beq same                    ; the one that is in
    sta map_ofs
    ; Whether to upload, for after the blocks.
    sep #$20
.a8
    lda f:tileset_table + 5, x
    ora temp + 2
    pha
    ; The block table and its passability alone, where the record says they
    ; live: behind the grid, in $7F.
    phx
    ldx map_ofs
    lda f:map_table + M_PTR_MAP_BLOCKS + 2, x
    sta f:LZ2_BANK
    rep #$20
.a16
    lda f:map_table + M_PTR_MAP_BLOCKS, x
    tay
    plx
    lda f:tileset_table + 2, x
    pha
    sep #$20
.a8
    lda f:tileset_table + 4, x
    plx
    jsl f:lz2_decompress + FAST
    pla                         ; whether to upload
    beq done                    ; goombario: pull-branch: the pulled byte is whether to upload
    ; The drawing: what `back_to_map` uploads, from the record now current,
    ; and the window filled from the grid with the new blocks.
    lda #$80
    sta f:INIDISP               ; what follows writes VRAM by DMA
    CALL0 load_map
    CALL0 load_above
    CALL0 fill_window
    CALL0 apply_tint
    lda #0
    sta f:flash_ready           ; `pal_buf` was the other ChipSet's colours
    CALL0 upload_tint
    ; `load_map` and `load_above` went through `LZ2_BUFFER`: the battle
    ; animation's last frame and a page carried from another map —maybe the
    ; one running this— are rebuilt as `back_to_map` does.
    jsl f:anim_buf_clear
    jsl f:code_carry_after + FAST
    bra done
.a16
none:
    pla                         ; the variant's place, still on the stack
same:
    sep #$20
.a8
done:
    ply
    rtl
.endproc

.popseg
.endif
