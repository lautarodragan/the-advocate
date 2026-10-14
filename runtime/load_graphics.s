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
.if ::WINDOW_SYSTEMS > 1
    ; The System the window is drawn with, which a loaded save brings: every
    ; piece of the window is read from this copy.
    jsl f:window_select
.endif
    stz CGADD
    rep #$20
.a16
    win_lo window_cgram, WS_CGRAM
    sta A1T0L
    lda #(CGRAM_BASE * 2)
    sta DAS0L
    sep #$20
.a8
    win_bank window_cgram, WS_CGRAM
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
    ; And which tiles of each slot the bank leaves holding something, which
    ; the converter worked out from the bank itself: `vram_drain` zeroes
    ; those a new pose leaves empty. See `pose_masks_table` in
    ; rm2k-snes-mapdata.
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:pose_masks_maps, x
    tax
    ldy #$0000
mask:
    lda f:pose_masks_data, x
    sta pose_slot_masks, y
    inx
    inx
    iny
    iny
    cpy #64
    bne mask
    sep #$20
.a8
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
;
; **The last entry is not for it: it is the hero's**, who queues with
; `vram_queue_hero`. The hero is drawn last of all, and when the NPCs filled
; the queue every frame he never got in: in The Book of Three's Caer Dallben
; East he walked with no walking animation and facing the way he came in.
.proc vram_queue
.a8
.i16
    lda vq_n
    cmp #VQ_MAX - 1
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

; The hero's pose, at `vq_src`, for his block at `vq_dest`: like
; `vram_queue`, but **at the front of the queue**, so it goes up in the next
; vblank whatever the NPCs asked for —`vram_drain` always uploads at least
; one, see `vq_cap`—, and with the last entry, which `vram_queue` leaves
; free for him. If the front entry is already his —he changed pose again
; before a vblank— the new pose replaces it: queued behind, the old one
; would go up after and stay. It is told apart by its destination, block 0
; of the bank, which is nobody else's. Returns A nonzero, like
; `vram_queue`.
.proc vram_queue_hero
.a8
.i16
    lda vq_n
    beq first                   ; empty: it is entry 0
    rep #$20
.a16
    lda vq + 3
    cmp vq_dest
    sep #$20                    ; `sep` does not touch Z: the `beq` looks at the `cmp`
.a8
    beq write                   ; his pose is already in front: it is replaced
    lda vq_n
    cmp #VQ_MAX
    bcc has_place
    lda #0                      ; cannot happen while the NPCs leave him the last
    rts
has_place:
    ; Each entry one place back, from the last one, byte by byte.
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; the bytes in use: entries times five
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
back:
    dex
    lda vq, x
    sta vq + VQ_STRIDE, x
    cpx #$0000
    bne back
first:
    inc vq_n
write:
    lda vq_src
    sta vq + 0
    lda vq_src + 1
    sta vq + 1
    lda vq_src + 2
    sta vq + 2
    lda vq_dest
    sta vq + 3
    lda vq_dest + 1
    sta vq + 4
    lda #1
    rts
.endproc

; Uploads up to VQ_PER_FRAME poses from the queue and leaves the rest at the
; start.
;
; **A pose comes without its empty tiles**: a mask of the sixteen that draw
; something —bit i is tile i of the 4x4, by rows— and only those, in order
; (`pose_record` in rm2k-snes-mapdata). Half of the poses' tiles are fully
; transparent, and they were half of the poses' bytes. But a 32x32 object
; reads its sixteen tiles whatever they hold, so an empty one has to be
; zero **in the slot**: the slot remembers in `pose_slot_masks` which of its
; tiles may hold something, and this zeroes those the slot drew and the new
; pose does not, from a fixed zero on channel 7.
;
; Each row of the 4x4 —256 words apart in the name grid— goes in runs: a
; row's four bits are an index into `pose_runs`, at most two runs each. The
; source is set once per pose: a DMA leaves its A-bus address past what it
; read, and the drawn tiles are stored one behind the other.
;
; **It cannot cost more than uploading the poses whole did**, because the
; vblank was already measured to the edge with five whole poses: on
; 2026-10-14, with five of Lashe City's walkers stepping on the same frame,
; the window's line ended 0.1 lines before the screen came back. So the
; rows are unrolled —`POSE_ROW`, no shifting a mask a row at a time— and
; the code lives in bank 1, out of bank 0's way, with the data bank at its
; own so that its tables, low RAM and the registers are all one absolute
; read away. Measured in the task `poses-without-their-empty-tiles`.
.pushseg
.segment "FAR"
.a8
.i16

; One row of a pose: the runs of `row`'s four bits of the 16-bit `mask`, in
; the direct page, to the row of the slot at `vq_dest`, through the channel
; whose byte count is `das` and whose bit in MDMAEN is `bit`. A at 16 bits,
; X and Y free; it goes on to `done`, which follows it. The carry is clear
; on every `adc`: the shifts that make the index leave it so, and a VRAM
; word address plus an offset does not overflow.
.macro POSE_ROW row, mask, das, bit, done
    lda mask
.if row = 0
    and #$000F
    beq done
    asl a
    asl a
    asl a
.elseif row = 1
    and #$00F0
    beq done
    lsr a
.elseif row = 2
    and #$0F00
    beq done
    xba
    asl a
    asl a
    asl a
.else
    and #$F000
    beq done
    xba
    lsr a
.endif
    tay                         ; the four bits times eight: their runs
    lda pose_runs, y
    adc vq_dest
.if row > 0
    adc #row * 256
.endif
    sta VMADDL
    ldx pose_runs + 2, y
    stx das
    sep #$20
.a8
    lda #bit
    sta MDMAEN
    rep #$20
.a16
    ldx pose_runs + 6, y        ; a second run, after a gap
    beq done
    stx das
    lda pose_runs + 4, y
    clc
    adc vq_dest
.if row > 0
    adc #row * 256
.endif
    sta VMADDL
    sep #$20
.a8
    lda #bit
    sta MDMAEN
    rep #$20
.a16
.endmacro

.proc vram_drain
.a8
.i16
    lda vq_n
    bne has
    rtl
has:
    phb
    phk
    plb                         ; the data bank at this code's
    lda #$80
    sta VMAIN                   ; increment one word after the high byte
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$09
    sta DMAP7                   ; the same, from a source that does not advance
    lda #$18
    sta BBAD7
    ldx #.loword(pose_zero)
    stx A1T7L
    lda #^pose_zero
    sta A1B7
    stz vq_done
    ldx #$0000                  ; the entry, in bytes
other:
    lda vq_done
    cmp vq_n
    beq to_end
    cmp vq_cap
    bne next_pose
to_end:
    jmp end                     ; too far for a branch
next_pose:
    phx
    lda vq + 2, x
    sta A1B0                    ; the source's bank
    pha
    rep #$20
.a16
    lda vq + 3, x
    sta vq_dest
    lda vq + 0, x
    tay
    inc a
    inc a
    sta A1T0L                   ; the tiles, behind the mask
    sep #$20
.a8
    ; The mask, read with the data bank at the source's: there is no direct
    ; page pointer to spare in here, and it is one read.
    plb
    rep #$20
.a16
    lda a:$0000, y
    phk
    plb                         ; and back at this code's
    tay                         ; the mask, while the slot is worked out
    ; The slot, from the destination: the tile times sixteen words from the
    ; bank's start, which is a multiple of 8K words —OBSEL's—, so its low
    ; thirteen bits are the tile's. A slot is a 32x32 block of
    ; `block_tile`'s layout, four across the sixteen-tile row, and two
    ; bytes per block: (tile / 64) * 8 + ((tile / 4) % 4) * 2.
    lda vq_dest
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the tile over two
    sta temp + 2
    and #$0006
    sta temp
    lda temp + 2
    lsr a
    lsr a
    and #$0038
    ora temp
    tax
    ; What to zero: what the slot may hold and this pose does not draw.
    ; From here on `temp` is the mask and `temp + 2` the tiles to zero.
    lda pose_slot_masks, x
    sta temp + 2
    tya
    sta pose_slot_masks, x
    sta temp
    eor #$FFFF
    and temp + 2
    sta temp + 2
    bne zero
    jmp upload                  ; the usual: nothing to zero
zero:
    POSE_ROW 0, temp + 2, DAS7L, $80, zero1
zero1:
    POSE_ROW 1, temp + 2, DAS7L, $80, zero2
zero2:
    POSE_ROW 2, temp + 2, DAS7L, $80, zero3
zero3:
    POSE_ROW 3, temp + 2, DAS7L, $80, upload
upload:
    POSE_ROW 0, temp, DAS0L, $01, up1
up1:
    POSE_ROW 1, temp, DAS0L, $01, up2
up2:
    POSE_ROW 2, temp, DAS0L, $01, up3
up3:
    POSE_ROW 3, temp, DAS0L, $01, pose_done
pose_done:
    pla                         ; the entry, which `phx` left
    clc
    adc #VQ_STRIDE
    tax
    sep #$20
.a8
    inc vq_done
    jmp other
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
    plb
    rtl
.endproc

; The runs of a row of a pose, by its four bits —bit c is column c—: two at
; most, each its offset in VRAM words from the row's start and its length in
; bytes, and a second run of zero bytes is none. See `vram_drain`.
pose_runs:
    ;     first run     second run    the row, column 0 at the left
    .word 0, 0,      0, 0     ; ....
    .word 0, 32,     0, 0     ; #...
    .word 16, 32,    0, 0     ; .#..
    .word 0, 64,     0, 0     ; ##..
    .word 32, 32,    0, 0     ; ..#.
    .word 0, 32,     32, 32   ; #.#.
    .word 16, 64,    0, 0     ; .##.
    .word 0, 96,     0, 0     ; ###.
    .word 48, 32,    0, 0     ; ...#
    .word 0, 32,     48, 32   ; #..#
    .word 16, 32,    48, 32   ; .#.#
    .word 0, 64,     48, 32   ; ##.#
    .word 32, 64,    0, 0     ; ..##
    .word 0, 32,     32, 64   ; #.##
    .word 16, 96,    0, 0     ; .###
    .word 0, 128,    0, 0     ; ####

; What channel 7 zeroes the empty tiles from: the source does not advance.
pose_zero: .word 0
.popseg

.pushseg
.segment "BSS"
; Which of each slot's sixteen tiles may hold something, a 32x32 block of the
; sprite bank each, two bytes per block: the PPU addresses 512 tiles, 32
; blocks. `load_sprite` sets them to what the bank it uploads leaves there
; —the map's `pose_masks_data`, which the converter works out from the
; bank—, and `vram_drain` keeps them.
;
; In bank 0 and not in `FARBSS`, which is full on purpose: what it has left
; is the materials' table's room for every actor of the whole game —see
; ABL's `test_wram_reservations.py`—.
pose_slot_masks: .res 64
.popseg

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
.ifdef paint_table
    ; And a painted map's slots, which the screens overwrite: see painted.s.
    jsl f:paint_load
.endif
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
    jsl f:pass_look + FAST      ; see `pass_has`
    rts
.endproc

; And the table of graphics for move command 34, with the same loop and the
; same borrowed pointer. It is sixteen bytes at most, and behind them one
; byte per graphic to `route_gfx_colors`.
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
    sta temp + 2                ; and one colour byte per graphic
    asl a                       ; two bytes per graphic
    sta temp
    sep #$20
.a8
    ldy #$0000
copy:
    cpy temp
    beq colors
    lda [npc_ptr], y
    sta route_gfx_buf, y
    iny
    bra copy
colors:
    ldx #$0000
each_color:
    cpx temp + 2
    beq ready
    lda [npc_ptr], y
    sta route_gfx_colors, x
    iny
    inx
    bra each_color
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

