.segment "CODE"

; Leaves in A1T0L/A1B0 the 24-bit pointer that the map's record keeps in the
; field given in Y. The pointer's three bytes are contiguous, so the low part
; comes from a 16-bit read and the bank from the neighboring one.
; The arithmetic is done with a 16-bit accumulator from end to end. Doing it
; in 8 and then `tax` does not work: the 65816's accumulator is always 16
; bits, and `tax` with a wide X transfers both bytes, including the high one
; left over from the previous operation. With map 7 it gave zero by chance for
; the tiles and garbage for the palette.
.proc dma_origin
.a8
.i16
    rep #$20
.a16
    tya                         ; the field's offset
    clc
    adc map_ofs
    tax
    lda f:map_table, x
    sta A1T0L
    sep #$20
.a8
    lda f:map_table + 2, x
    sta A1B0
    rts
.endproc

.proc load_map
.a8
.i16
    ldx map_ofs
    ; --- the tiles ---
    lda #$80
    sta VMAIN                   ; increment one word after the high byte
    rep #$20
.a16
    lda f:map_table + M_VRAM_TILES, x
    sta VMADDL
    sep #$20
.a8
    jsl f:lz2_backdrop + FAST   ; compressed, in streams: see decompress.s

    ; --- the ChipSet animation ---
    ; The map brings drawing 0 of each run into VRAM, and the clock can be on
    ; any other: it is a clock of the saved game and not of the map. The one
    ; due is uploaded here, with no vblank budget because the screen is off.
    ; Its drawings come compressed and are decompressed to WRAM, from where
    ; `anim_upload` uploads them for as long as the map lasts. They go after
    ; the background tiles, which use the same WRAM bank: see `ANIM_DRAWINGS`.
    jsl f:lz2_anim + FAST
    jsr anim_load

    ; --- the colors ---
    ;
    ; First the bottom part, which belongs to the whole ROM and not to this
    ; map: the screen's backdrop color and the message window's palette. It
    ; goes here and not in `load_window` because `load_window` is skipped
    ; entirely when the ROM has no window, and the backdrop color is needed
    ; anyway.
    stz CGADD
    rep #$20
.a16
    lda #.loword(window_cgram)
    sta A1T0L
    lda #(CGRAM_BASE * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^window_cgram
    sta A1B0
    lda #$00
    sta DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN

    ; And on top of it the map, which starts where the reserved part ends.
    lda #CGRAM_BASE
    sta CGADD
    ldy #M_PTR_MAP_CGRAM
    jsr dma_origin
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_MAP_CGRAM, x
    asl a                       ; two bytes per color
    sta DAS0L
    sep #$20
.a8
    ; **A count of zero is not a DMA of zero bytes: it is one of 65536.** A
    ; background that is all panorama —ABL's 94 and 99, Vampires Dawn's
    ; intro— has no colors, and the DMA ran 128 times over the whole CGRAM,
    ; the window's palette included. Z is the `asl`'s: `sta` and `sep` do
    ; not touch it. The same in `load_sprite` and `load_above`.
    beq no_colors
    lda #$00
    sta DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN
no_colors:

    ; The tilemap is not uploaded here: there is no whole one to upload.
    ; fill_window builds it from the blocks, and from then on the streaming
    ; keeps it.
    rts
.endproc

; --- the sprites -----------------------------------------------------------
.proc load_sprite
.a8
.i16
    ; The bank uploaded here brings one pose per slot. The upload queue
    ; starts empty, and the hero's pose in VRAM is the one the converter put
    ; there —facing down— unless he faces elsewhere: `place_hero` resolves it
    ; on the first frame, with the screen still off.
    stz vq_n
    lda #$FF
    sta hero_pose_vram
    ldx map_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:map_table + M_VRAM_SPRITE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_SPRITE_TILES
    jsl f:lz2_field + FAST
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_SPRITE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per 4-bit tile
    sta DAS0L
    sep #$20
.a8
    ; None, in a map where nobody is drawn —an empty party and no NPC with a
    ; CharSet—: 65536 bytes of the buffer would cover the whole VRAM.
    beq no_tiles
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
no_tiles:
    jsl f:share_load + FAST     ; and nobody knows what the shared slots hold
    jsl f:cache_load + FAST     ; nor what the cache's do

    ; The palette goes to the upper half of CGRAM, which is the sprites': 8
    ; starts at color 128.
    lda #128
    sta CGADD
    ldy #M_PTR_SPRITE_CGRAM
    jsr dma_origin
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_SPRITE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    beq no_palette              ; nobody drawn, no palette: see `load_map`
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_palette:

    lda f:map_table + M_OBSEL_VALUE, x
    sta OBSEL
    rts
.endproc

; --- OAM -------------------------------------------------------------------
; All objects start hidden: see `oam_hide`, which lives in bank 1.
.proc clear_oam
.a8
.i16
    jsl f:oam_hide + FAST ; see MEMSEL
    rts
.endproc

.proc push_oam
.a8
.i16
    stz OAMADDL
    stz OAMADDL + 1
    ldx #.loword(oam)
    stx A1T0L
    lda #^oam
    sta A1B0
    ldy #544                    ; the 512 of the big table plus the 32 small ones
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$04
    sta BBAD0                   ; destination: OAMDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; --- poses on the fly ------------------------------------------------------
; VRAM holds one pose per character: the hero in block 0 and each walking NPC
; in its slot. The twelve poses of each one are in the cartridge, and when
; someone wants to be drawn with another, it queues it here and it goes up in
; the next vblank, in the same `flush_video` that uploads the OAM already
; counting on it. It is what the console's RPGs do with more than two animated
; characters: with every pose resident, 512 tiles are two and a half
; characters.
;
; Queues the pose at `vq_src` (24 bits, in the cartridge) for the slot that
; starts at word `vq_dest`. Returns A nonzero if it got in; if the queue is
; full, the caller has to ask for it again.
.proc vram_queue
.a8
.i16
    lda vq_n
    cmp #VQ_MAX
    bcc has_place
    lda #0
    rts
has_place:
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; times five
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda vq_src
    sta vq + 0, x
    lda vq_src + 1
    sta vq + 1, x
    lda vq_src + 2
    sta vq + 2, x
    lda vq_dest
    sta vq + 3, x
    lda vq_dest + 1
    sta vq + 4, x
    inc vq_n
    lda #1
    rts
.endproc

; Uploads up to VQ_PER_FRAME poses from the queue and leaves the rest at the
; start. Each pose is four DMAs of 128 bytes: the four rows of the 4x4 block,
; which in the name grid are 256 words apart from each other.
.proc vram_drain
.a8
.i16
    lda vq_n
    bne has
    rts
has:
    lda #$80
    sta VMAIN                   ; increment one word after the high byte
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    stz vq_done
    ldx #$0000                  ; the entry, in bytes
other:
    lda vq_done
    cmp vq_n
    beq end
    cmp vq_cap
    beq end
    lda vq + 2, x
    sta A1B0                    ; the source's bank
    rep #$20
.a16
    lda vq + 0, x
    sta vq_src
    lda vq + 3, x
    sta vq_dest
    sep #$20
.a8
    lda #4
    sta vq_rows
row:
    rep #$20
.a16
    lda vq_dest
    sta VMADDL
    lda vq_src
    sta A1T0L
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda vq_src
    clc
    adc #128
    sta vq_src
    lda vq_dest
    clc
    adc #256                    ; the next row of the name grid
    sta vq_dest
    sep #$20
.a8
    dec vq_rows
    bne row
    inc vq_done
    rep #$20
.a16
    txa
    clc
    adc #VQ_STRIDE
    tax
    sep #$20
.a8
    bra other
end:
    ; What did not fit, to the start of the queue. X points to the first
    ; entry left.
    lda vq_n
    sec
    sbc vq_done
    sta vq_n
    beq ready
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; the bytes left: entries times five
    sta temp + 2
    ldy #$0000
move:
    lda vq, x
    sta vq, y
    inx
    iny
    dec temp + 2
    bne move
ready:
    rts
.endproc

; --- the layer that goes above the hero ------------------------------------
; Its tiles and palette are uploaded only once, with the screen off. Its
; tilemap is not: it goes in the same moving window as the background's, and
; the streaming fills it.
.proc load_above
.a8
.i16
    ; A map whose panorama goes in mode 3 has no upper layer: BG2 is the
    ; panorama, which `pano_load` uploads below. Nothing goes to BG2's base,
    ; which in `VENTANA_PANORAMA_FONDO_TECHO` is inside the background's
    ; tiles. See `vram.rs` in rm2k-snes-mapdata.
    lda f:PANO_ON
    cmp #3
    beq palette
    ldx map_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    ; BG2's base has no field of its own in the record, which is full: it is
    ; the high nibble of BG12NBA, in steps of 4096 words. The top byte that
    ; the sixteen-bit read brings is ABOVE_FIRST, and it is discarded.
    lda f:map_table + M_BG12NBA_VALUE, x
    and #$00F0
    xba
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_ABOVE_TILES
    jsl f:lz2_field + FAST
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ABOVE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; they are 4-bit: 32 bytes per tile
    sta DAS0L
    sep #$20
.a8
    beq palette                 ; none: see `load_map`
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Its palette goes in the last palettes of the lower half of CGRAM, which
    ; the 8-bit background leaves free. How many and from where was decided by
    ; the converter map by map, so it comes in the record.
palette:
    ldx map_ofs
    lda f:map_table + M_ABOVE_FIRST, x
    sta CGADD
    ldy #M_PTR_ABOVE_CGRAM
    jsr dma_origin
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ABOVE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    beq no_colors               ; none: see `load_map`
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_colors:
    ; And the panorama's tiles, if the map shows it: every load and every
    ; return from a screen comes through here. See pano.s.
    jsl f:pano_load
    rts
.endproc

; The NPC table to RAM, which is where build_oam reads it from.
;
; With a loop and not a DMA: to reach WRAM the DMA has to go through port
; $2180 and leave the address set in $2181-$2183, which are three more
; registers to remember to load. It is a thousand bytes at most and this runs
; once per map, so the loop costs nobody anything and cannot write to the
; wrong place.
.proc load_npcs
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_NPC_TABLE
    clc
    adc map_ofs
    tax
    lda f:map_table, x            ; the low 16 bits of the pointer
    sta npc_ptr
    sep #$20
.a8
    lda f:map_table + 2, x        ; and its bank
    sta npc_ptr + 2

    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; times sixteen: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "the arithmetic above multiplies by sixteen by hand"
    sta temp
    sep #$20
.a8
    ldy #$0000
copy:
    cpy temp
    beq ready
    lda [npc_ptr], y
    sta npc_buf, y
    iny
    bra copy
ready:
    jsl f:pass_look + FAST      ; ver `pass_has`
    rts
.endproc

; And the table of graphics for move command 34, with the same loop and the
; same borrowed pointer. It is sixteen bytes at most.
.proc load_route_graphics
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_ROUTE_GRAPHIC
    clc
    adc map_ofs
    tax
    lda f:map_table, x
    sta npc_ptr
    sep #$20
.a8
    lda f:map_table + 2, x
    sta npc_ptr + 2

    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ROUTE_GRAPHIC_COUNT, x
    asl a                       ; two bytes per graphic
    sta temp
    sep #$20
.a8
    ldy #$0000
copy:
    cpy temp
    beq ready
    lda [npc_ptr], y
    sta route_gfx_buf, y
    iny
    bra copy
ready:
    rts
.endproc

; The table of event positions to RAM, and whatever routes were running to the
; trash.
;
; The second part is what RM2k does when changing maps: forced routes belong
; to the events of the map being left, and there is nobody left walking
; there.
;
; Reuses `npc_ptr`, which only lives while a table is being copied and never
; both at once.
.proc load_ev_pos
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_EV_POS
    clc
    adc map_ofs
    tax
    lda f:map_table, x            ; the low 16 bits of the pointer
    sta npc_ptr
    sep #$20
.a8
    lda f:map_table + 2, x        ; and its bank
    sta npc_ptr + 2

    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_EV_COUNT, x
    asl a
    asl a                       ; EV_STRIDE bytes per event
    sta temp
    sep #$20
.a8
    ldy #$0000
copy:
    cpy temp
    beq tables
    lda [npc_ptr], y
    sta ev_pos_buf, y
    iny
    bra copy

tables:
    stz route_ev_cap            ; no slot used yet on this map
    ldx #$0000
free:
    lda #ROUTE_EV_FREE
    sta route_ev, x
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #ROUTE_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc free

    ; And the flashes, which also belong to the events of the map being left.
    ldx #$0000
no_flash:
    lda #FLASH_FREE
    sta flash_ev, x
    stz flash_ev + 7, x         ; no pending palette: RAM starts with
                                ; garbage and the vblank reads this
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc no_flash
    stz route_step
    rts
.endproc

