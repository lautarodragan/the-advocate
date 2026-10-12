.segment "FAR"

; --- LZ2: what the cartridge carries compressed -------------------------------
;
; The tiles of the map, of the sprites, of the upper layer, of the ChipSet
; animation, and the grid travel in the cartridge in LC_LZ2, Nintendo's format,
; and are decompressed into WRAM when the map loads, with the screen off inside
; the fade. The format and the reason for this one and not another are in
; tools/port/compress.py; the compressor is `snes/lz2/`.
;
; Each command in the stream is a header —what it is and how many bytes it
; makes— and its operand. Almost everything is done with `mvn`:
;
;   literal      `mvn` from the stream to the output
;   fill         the byte to the output, and an `mvn` of the output onto
;                itself shifted by one, which repeats it: `mvn` copies one byte
;                at a time forward, so each byte it reads is the one it just
;                wrote
;   word         the same with the two bytes, shifted by two
;   repeat       `mvn` from the output to the output: the address it carries
;                is absolute —it counts from the start of the output— and the
;                base is added to it
;
; The increasing fill (3), which is the only one an `mvn` does not do, and the
; one-byte word **are not read**: the converter does not emit them and checks
; it —see `what_the_rom_does_not_read` in tools/port/compress.py—. Reading them
; would be a path no test runs.
;
; `mvn` carries both banks **inside the instruction**. The output's is one of
; two —$7E or $7F—, so the body is written twice, once per bank, with the
; output-onto-itself `mvn` inside: that is where almost all the bytes go
; through —the tiles and even more so the grid are mostly repeats and fills—
; and this way it is read from the ROM's fast half. The stream's changes from
; block to block, so the literal's `mvn` is built in RAM at the start
; —`LZ2_TRAMPOLINE_LIT`— and called with `jsl`; running from WRAM costs it a few
; cycles per byte, because `mvn` reads its code again for each one.
;
; The stream is read with the data bank set to its own and `lda a:0, x`: the
; direct page is full and there is nowhere to put a 24-bit pointer. In ExHiROM
; its bank is already the one it is read from —fast in the first 4 MB—; in
; LoROM it was ORed with `^FAST`, which in ExHiROM would take a bank of the
; second 4 MB to the first. That is why each compressed block fits whole in one bank —the
; converter declares it with `.block`—: X cannot go past $FFFF.

; Decompresses a stream. Enters with an 8-bit A and 16-bit X and Y: X and A
; where the stream is —address and bank—, Y where the output goes inside bank
; `LZ2_BANK`, which the caller sets and is $7E or $7F. Leaves with X on the
; byte after the $FF —the next stream starts there, if another one follows
; right after— and Y on the byte after the last one it wrote. Clobbers A;
; leaves P and the data bank as they were.
;
; The output cannot cross a bank: Y wraps at $FFFF and the converter watches
; for it, with streams of up to 32 KB.
;
; In a cartridge that needs the MSU-1 the stream may be in the `.msu`
; instead: then A is `MSU_SPILL_BANK` and `lz2_msu` reads it. See there.
.proc lz2_decompress
.a8
.i16
    php
.ifdef MSU_REQUIRED
    cmp #MSU_SPILL_BANK
    bne in_rom
    jmp lz2_msu
in_rom:
.endif
    phb
    pha
    ; The literal's trampoline. In `mvn`'s machine code the destination bank
    ; goes first and the source bank after.
    sta f:LZ2_TRAMPOLINE_LIT + 2
    lda #$54                    ; mvn
    sta f:LZ2_TRAMPOLINE_LIT
    lda #$6B                    ; rtl
    sta f:LZ2_TRAMPOLINE_LIT + 3
    lda f:LZ2_BANK
    sta f:LZ2_TRAMPOLINE_LIT + 1
    plb                         ; the stream's bank
    rep #$20
.a16
    tya
    pha                         ; 3,s: the output's base
    pha                         ; 1,s: the command's length, minus one
    sep #$20
.a8
    lda f:LZ2_BANK
    cmp #^GRID_HIGH
    bne in_7e
    jmp lz2_body_7f
in_7e:
    jmp lz2_body_7e
.endproc

; The body, for output in bank `exit`. It is entered from
; `lz2_decompress` with the stream's bank set and the length and base on the
; stack, and it returns from right there.
.macro LZ2_BODY exit
cmd:
    sep #$20
.a8
    lda a:0, x
    cmp #$E0
    bcs length
    ; `CCCLLLLL`: up to 32 bytes.
    rep #$20
.a16
    and #$001F
    sta 1, s
    sep #$20
.a8
    lda a:0, x                  ; and again, to dispatch
    inx
    bra dispatch
length:
    cmp #$FF
    beq end
    ; `111CCCLL LLLLLLLL`: up to 1024. The command is shifted to the top three
    ; bits, which is where the short header has it.
    rep #$20
.a16
    lda a:0, x
    xba
    and #$03FF
    sta 1, s
    sep #$20
.a8
    lda a:0, x
    inx
    inx
    asl a
    asl a
    asl a
dispatch:
    asl a
    bcs repeat                  ; 4: 5 and 6 do not exist
    asl a
    bcs word                    ; 2; 3, the increasing fill, never arrives
    asl a
    bcs padding
    ; 0: the bytes, from the stream to the output.
    rep #$20
.a16
    lda 1, s
    phb
    jsl f:LZ2_TRAMPOLINE_LIT
    plb
    bra cmd

end:
.a8
    inx                         ; the $FF
    rep #$20
.a16
    pla
    pla
    plb
    plp
    rtl

padding:
.a8
    ; 1: the byte to the output, and it is repeated shifted by one.
    lda a:0, x
    inx
    phx                         ; the stream, while X points at the output
    tyx
    sta f:exit << 16, x
    iny
    rep #$20
.a16
    lda 3, s                    ; the length minus one, moved by the `phx`
    beq ready                   ; it was just one
    dec a                       ; the ones left, minus one
    bra in_output

word:
.a8
    ; 2: the two bytes to the output, and they are repeated shifted by two.
    ; It is always two or more: see above.
    rep #$20
.a16
    lda a:0, x
    inx
    inx
    phx
    tyx
    sta f:exit << 16, x
    iny
    iny
    lda 3, s                    ; the length minus one, moved by the `phx`
    dec a
    beq ready                   ; it was two
    dec a
    bra in_output

repeat:
.a8
    ; 4: from the output to the output. The address comes high byte first.
    rep #$20
.a16
    lda a:0, x
    xba
    inx
    inx
    phx
    clc
    adc 5, s                    ; plus the base, which the `phx` moved to 5,s
    tax
    lda 3, s                    ; and the length minus one, to 3,s
in_output:
    ; With X inside the output, A the length minus one and the stream pointer
    ; on the stack. The `mvn` leaves the data bank at the output's.
    phb
    mvn #exit, #exit
    plb
ready:
    plx
    jmp cmd

.endmacro

.proc lz2_body_7e
    LZ2_BODY ^GRID
.endproc

.proc lz2_body_7f
    LZ2_BODY ^GRID_HIGH
.endproc

; --- a stream that travels in the `.msu` ---------------------------------------
;
; A cartridge whose ROM does not reach carries in the `.msu` the streams the
; bank packing could not fit —`pack_with_msu` in rm2k-snes-cartridge—, and
; their label is not an address but bank `MSU_SPILL_BANK`, which no data of
; the cartridge is in, and the unit the stream starts at in the `.msu`'s
; region: `MSU_SPILL_AT` plus the unit, times 256. Who asks for one does not
; know: it passes the bank and the address it read from its table, as with
; any other, and `lz2_decompress` sends it here.
;
; It is the same LZ2 read from `MSU_DATA` instead of from the ROM, a byte at
; a time: the port advances by itself, so there is no stream pointer and X is
; free. The literals go by the CPU and not by `mvn` —the source is a port,
; not memory—: about twice the cycles per byte of the ROM's, with the screen
; off inside the fade. The repeats and the fills are the ROM's, output onto
; output.
;
; **Two streams in a row**: `lz2_grid` and `lz2_backdrop` decompress the
; second where the first ended, passing back the X it left. Here it leaves
; X at $FFFF, and a stream asked for with X at $FFFF does not seek: it goes
; on from where the port was left, which is right behind the first, because
; the packing sends a piece whole. That is why no stream starts at unit
; $FFFF.
;
; Only assembled in a cartridge that needs the MSU-1, which is the only one
; the packing sends anything to the `.msu` in: in the rest this does not
; exist and the ROM is the same as before there was a way to need it. That
; the boot already checked that the MSU-1 is there and the `.msu` is this
; build's is what lets this not look at either: see `msu_required`.
.ifdef MSU_REQUIRED
.proc lz2_msu
.a8
.i16
    ; Entered from `lz2_decompress` after its `php`, with the frame its bodies
    ; expect built here the same way: the data bank, and on top the base and
    ; the length.
    phb
    ; The sound effects of the `.msu` remember where they left the port so
    ; as not to seek twice —see `se_msu_upload`—, and this moves it.
    lda #$FF
    sta f:MSU_SE_NEXT
    sta f:MSU_SE_NEXT + 1
    sta f:MSU_SE_NEXT + 2
    cpx #$FFFF
    beq sought                  ; right behind the one before
    phy
    jsr msu_spill_seek
    ply
sought:
    rep #$20
.a16
    tya
    pha                         ; 3,s: the output's base
    pha                         ; 1,s: the command's length, minus one
    sep #$20
.a8
    lda f:LZ2_BANK
    cmp #^GRID_HIGH
    bne in_7e
    jmp lz2_msu_7f
in_7e:
    jmp lz2_msu_7e
.endproc

; Seeks the `.msu` to unit X of the region and waits for the port to have
; it. Clobbers A and X.
;
; **The wait has no cap**, unlike `msu_data_seek`'s: what is read here has no
; other source, and running out of time would decompress garbage instead
; of waiting. The boot already checked that the MSU-1 answers.
.proc msu_spill_seek
.a8
.i16
    rep #$20
.a16
    txa
    clc
    adc #.loword(MSU_SPILL_AT)
    tax                         ; bytes 1 and 2 of the position
    sep #$20                    ; `sep` keeps the carry
.a8
    lda #^MSU_SPILL_AT
    adc #0
    pha                         ; byte 3: a `txa` of sixteen bits would take B
    lda #0
    sta f:MSU_SEEK              ; byte 0: the units are of 256
    rep #$20
.a16
    txa
    sta f:MSU_SEEK + 1
    sep #$20
.a8
    pla
    sta f:MSU_SEEK + 3          ; the one that seeks, last
wait:
    lda f:MSU_STATE
    bmi wait                    ; bit 7: still seeking
    rts
.endproc

; DMA channel 0 set up from a block that may travel in the `.msu`: if A1B0
; is `MSU_SPILL_BANK`, A1T0L is not an address but the block's unit —or
; $FFFF, right behind what was read last—, and this seeks there and points
; the channel at the port, with the source fixed: the port advances by
; itself. From a block in the ROM it touches nothing. The caller sets the
; rest —DMAP0 before this, which ORs into it— and starts the DMA.
;
; Only for what is uploaded whole and in order, and with the screen off: the
; panorama's tiles (`pano_load`) and a big picture's (`big_dma_vram`). Each
; block that may go is marked so by its emitter: see `msu_block` in
; rm2k-snes-mapdata.
.proc msu_dma0
.a8
.i16
    lda f:A1B0
    cmp #MSU_SPILL_BANK
    bne in_rom
    phx
    lda #$FF                    ; see `lz2_msu`
    sta f:MSU_SE_NEXT
    sta f:MSU_SE_NEXT + 1
    sta f:MSU_SE_NEXT + 2
    rep #$20
.a16
    lda f:A1T0L
    tax
    sep #$20
.a8
    cpx #$FFFF
    beq sought
    jsr msu_spill_seek
sought:
    rep #$20
.a16
    lda #MSU_DATA
    sta f:A1T0L
    sep #$20
.a8
    lda #0
    sta f:A1B0
    lda f:DMAP0
    ora #$08                    ; the source, fixed
    sta f:DMAP0
    plx
in_rom:
    rts
.endproc

; `msu_dma0` for `pano_load`, which lives in `FAR2`.
.proc msu_dma0_l
.a8
    jsr msu_dma0
    rtl
.endproc

; `LZ2_BODY` reading the stream from `MSU_DATA`. Same frame, same exit; X is
; free inside, and it leaves with X at $FFFF.
.macro LZ2_BODY_MSU exit
cmd:
    sep #$20
.a8
    lda f:MSU_DATA
    cmp #$E0
    bcs length
    ; `CCCLLLLL`: up to 32 bytes. The header waits in X to dispatch.
    rep #$20
.a16
    and #$00FF
    tax
    and #$001F
    sta 1, s
    txa
    sep #$20
.a8
    bra dispatch
length:
    cmp #$FF
    beq end
    ; `111CCCLL LLLLLLLL`: up to 1024.
    rep #$20
.a16
    and #$00FF
    tax
    xba
    sep #$20
.a8
    lda f:MSU_DATA              ; the second byte, under the first
    rep #$20
.a16
    and #$03FF
    sta 1, s
    txa
    sep #$20
.a8
    asl a
    asl a
    asl a
dispatch:
    asl a
    bcs repeat
    asl a
    bcs word
    asl a
    bcs padding
    ; 0: the bytes, from the port to the output: X the output and Y how many
    ; are left, minus one.
    rep #$20
.a16
    lda 1, s
    tyx
    tay
    sep #$20
.a8
literal:
    lda f:MSU_DATA
    sta f:exit << 16, x
    inx
    dey
    bpl literal
    txy
    jmp cmd

end:
.a8
    ldx #$FFFF                  ; the next stream, right behind this one
    rep #$20
.a16
    pla
    pla
    plb
    plp
    rtl

padding:
.a8
    ; 1: the byte, and it is repeated shifted by one. The `phx` keeps the
    ; frame of `LZ2_BODY`, where X is the stream: here it is nothing.
    lda f:MSU_DATA
    phx
    tyx
    sta f:exit << 16, x
    iny
    rep #$20
.a16
    lda 3, s
    beq ready
    dec a
    bra in_output

word:
.a8
    ; 2: the two bytes, and they are repeated shifted by two.
    lda f:MSU_DATA
    xba
    lda f:MSU_DATA
    xba                         ; the first in A, the second in B
    rep #$20
.a16
    phx
    tyx
    sta f:exit << 16, x
    iny
    iny
    lda 3, s
    dec a
    beq ready
    dec a
    bra in_output

repeat:
.a8
    ; 4: from the output to the output. The address comes high byte first.
    lda f:MSU_DATA
    xba
    lda f:MSU_DATA
    rep #$20
.a16
    phx
    clc
    adc 5, s                    ; plus the base
    tax
    lda 3, s
in_output:
    phb
    mvn #exit, #exit
    plb
ready:
    plx
    jmp cmd

.endmacro

.proc lz2_msu_7e
    LZ2_BODY_MSU ^GRID
.endproc

.proc lz2_msu_7f
    LZ2_BODY_MSU ^GRID_HIGH
.endproc
.endif

; X and A of the stream that field Y of the map record points to: its address
; and its bank, ready for `lz2_decompress`.
.proc lz2_from_field
.a8
.i16
    rep #$20
.a16
    tya
    clc
    adc map_ofs
    tax
    sep #$20
.a8
    lda f:map_table + 2, x
    pha
    rep #$20
.a16
    lda f:map_table, x
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; The block that field Y of the map record points to, decompressed into
; `LZ2_BUFFER`, and DMA channel 0 pointing there: it replaces `dma_origin` in
; `load_map`, `load_above` and `load_sprite`, which still set the length and
; the destination as before. The length comes from the record and not from
; what the decompressor wrote, so what reaches VRAM is the same as when the
; cartridge carried the tiles whole.
.proc lz2_field
.a8
.i16
    jsr lz2_from_field
    pha
    lda #^LZ2_BUFFER
    sta f:LZ2_BANK
    pla
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_decompress + FAST
    rep #$20
.a16
    lda #.loword(LZ2_BUFFER)
    sta f:A1T0L
    sep #$20
.a8
    lda #^LZ2_BUFFER
    sta f:A1B0
    rtl
.endproc

; The map's background tiles, to VRAM: they are decompressed into `LZ2_BUFFER`
; and uploaded by DMA one stream at a time. A background of more than
; `LZ2_CAP_BACKDROP` bytes —map 66's, with the 544-tile layout— comes in two
; streams back to back, and the second is decompressed **after** uploading the
; first, in the same place: decompressed whole it does not fit in the buffer,
; and whatever overflowed landed in the upper half of the grid. The converter
; splits into stretches of exactly `LZ2_CAP_BACKDROP` —see `compressed_parts`—,
; so how many tiles each stream carries follows from how many tiles the map has
; and there is no need to record it.
;
; Enters with VMAIN and VMADD set; the DMA carries the VRAM address on from one
; stream to the next. Leaves the tile bank uploaded and clobbers A, X and Y.
BACKDROP_TILES_PER_STREAM = LZ2_CAP_BACKDROP / 64 ; 64 bytes per 8-bit tile
.proc lz2_backdrop
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_MAP_TILES, x
    pha                         ; the tiles still to upload
    sep #$20
.a8
    ldy #M_PTR_MAP_TILES
    jsr lz2_from_field
    pha                         ; 1,s: the stream's bank; 2,s: the ones left
stream:
    lda #^LZ2_BUFFER
    sta f:LZ2_BANK
    lda 1, s
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_decompress + FAST         ; leaves X on the next stream
    rep #$20
.a16
    ; The ones that will be left after this one: zero if this is the last.
    lda 2, s
    sec
    sbc #BACKDROP_TILES_PER_STREAM
    bcs :+
    lda #0
:   pha                         ; 1,s: the ones that will be left; 3,s: the bank
    lda 4, s
    sec
    sbc 1, s                    ; this stream's
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 64 bytes per 8-bit tile
    sta f:DAS0L
    pla
    sta 2, s
    lda #.loword(LZ2_BUFFER)
    sta f:A1T0L
    sep #$20
.a8
    lda #^LZ2_BUFFER
    sta f:A1B0
    lda #$01
    sta f:DMAP0                 ; two registers, word at a time
    lda #$18
    sta f:BBAD0                 ; destination: VMDATAL
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    lda 2, s                    ; `sep` does not touch Z: the `bne` looks at this
    sep #$20
.a8
    bne stream
    pla
    rep #$20
.a16
    pla
    sep #$20
.a8
    rtl
.endproc

; The drawings of the map's ChipSet animation, into `ANIM_DRAWINGS`, from where
; `anim_upload` uploads them each time the clock changes. They have to stay
; there while on the map, so they go in a place of their own and not in
; `LZ2_BUFFER`, which the upper layer and the sprites overwrite afterwards: see
; the reservation in `far_ram.s`.
.proc lz2_anim
.a8
.i16
    ldy #M_PTR_ANIM_TILES
    jsr lz2_from_field
    pha
    lda #^ANIM_DRAWINGS
    sta f:LZ2_BANK
    pla
    ldy #.loword(ANIM_DRAWINGS)
    jsl f:lz2_decompress + FAST
    rtl
.endproc

; The map's grid, decompressed into `GRID`: its first 32 KB in the upper half
; of bank $7E and the rest in $7F's, which is the shape `ptr_more` and
; `ptr_minus` expect. The converter splits it into two streams, one per half,
; so no output crosses a bank; the second comes right after the first, and may
; have nothing more than its $FF.
;
; And what of the map the CPU reads while it is played —the block table and
; its passability, in a third stream right after those two, and then the
; event bytecode, in a stream that `map_code` names—, which goes **right
; where the grid ended**, in $7F's half. It is that Y the decompressor
; leaves, so this does not compute the addresses: the converter does, and
; puts them in the record's `M_PTR_MAP_BLOCKS` and `M_PTR_BLOCK_PASS`, in the
; page table and in `map_code` —see `map_ram_pointers` in
; `rm2k-snes-mapdata`—. It caps them so that they do not cross the bank.
;
; Battle overwrites $7F's half —it is `SCN_SCENE`—, so `back_from_battle`
; decompresses it all again. See the decision in
; decisions/the-grid-lives-in-wram.md.
.proc lz2_grid
.a8
.i16
    ldy #M_PTR_MAP_CELLS
    jsr lz2_from_field
    pha                         ; the stream's bank, for the third one
    pha                         ; and the second
    lda #^GRID
    sta f:LZ2_BANK
    pla
    pha
    ldy #.loword(GRID)
    jsl f:lz2_decompress + FAST         ; leaves X on the second stream
    lda #^GRID_HIGH
    sta f:LZ2_BANK
    pla
    ldy #.loword(GRID_HIGH)
    jsl f:lz2_decompress + FAST         ; X on the third, Y where the grid ended
    pla
    jsl f:lz2_decompress + FAST         ; the blocks and their passability
    ; The bytecode goes in a block of its own and not after these three, so
    ; that two maps with the same grid and different events still share
    ; theirs: its stream is the one `map_code` names.
    phy                         ; where it goes: where the passability ended
    rep #$20
.a16
    lda map_current
    asl a
    asl a
    asl a                       ; times MAP_CODE_STRIDE
    tax
    lda f:map_code, x
    pha
    sep #$20
.a8
    lda f:map_code + 2, x
    plx
    ply
    jsl f:lz2_decompress + FAST
    rtl
.endproc

; --- a page that goes on running on another map ------------------------------
;
; The bytecode lives behind the grid, and loading another map puts that
; map's in its place. RM2k lets a page go on after a `Teleport` —the
; interpreter keeps its list and its index—, and the game does it all the
; time: a cutscene jumps and keeps talking, and every test case of the
; harness starts with a jump and goes on. Here that page's bytecode is
; carried: `code_carry_before`, with the old map still loaded, moves the
; cursor to `CODE_CARRY`, and `code_carry_after`, with the new one loaded,
; decompresses the old map's bytecode there, alone —it is a stream of its
; own: see `map_code`—. The page's jumps are relative to where it starts,
; so moving the pointer is enough. `back_to_map` —after the menu, the shop,
; the slots or a battle— uploads the map's tiles through `LZ2_BUFFER` again,
; and calls `code_carry_after` again too.
;
; And the same with the hero's move route, which points into the bytecode
; of the page that gave it and goes on walking on the new map, as in
; `Game_Player::PerformTeleport`: it is copied whole to `ROUTE_CARRY`.
;
; The rest of what points into the bytecode does not survive a map change:
; the parallel pages, the events' routes and the battle animation's
; timeline start over with the new map.

; With the map that is being left still loaded and still in `map_current`:
; `enter_map_no_events` calls it before anything else.
.proc code_carry_before
.a8
.i16
    ; --- the hero's move route ---
    lda route_i
    cmp route_n
    bcs route_done              ; none, or it ended
    lda f:hero_route + 2
    cmp #^GRID_HIGH
    bne route_done              ; from the cartridge, or already carried
    rep #$20
.a16
    lda f:hero_route
    sta route_ptr
    sep #$20
.a8
    lda f:hero_route + 2
    sta route_ptr + 2
    ldy #0
route_copy:
    tya                         ; Y's low byte: `route_n` is a byte
    cmp route_n
    bcs route_copied
    lda [route_ptr], y
    tyx
    sta f:ROUTE_CARRY, x
    iny
    bra route_copy
route_copied:
    rep #$20
.a16
    lda #.loword(ROUTE_CARRY)
    sta f:hero_route
    sep #$20
.a8
    lda #^ROUTE_CARRY
    sta f:hero_route + 2
route_done:

    ; --- the foreground page ---
    ;
    ; Its cursor and, if it is inside a shared common event body, every
    ; frame below it on the call stack —see common_events.s—: the page that
    ; called is the one in this map's bytecode, and it goes on when the body
    ; returns. Each pointer goes through `carry_one`, which leaves in
    ; `temp + 3` whether it moved one (bit 0) or found one already carried
    ; (bit 1).
    stz temp + 3
    lda ev_active
    beq none
    rep #$20
.a16
    lda code_ptr
    sta temp
    sep #$20
.a8
    lda code_ptr + 2
    sta temp + 2
    jsr carry_one
    rep #$20
.a16
    lda temp
    sta code_ptr
    sep #$20
.a8
    lda f:CALL_DEPTH
    beq frames_done
    rep #$20
.a16
    and #$00FF
    tay                         ; how many frames: `carry_one` keeps Y
    sep #$20
.a8
    ldx #0
frame:
    rep #$20
.a16
    lda f:CALL_STACK, x
    sta temp
    sep #$20
.a8
    lda f:CALL_STACK + 2, x
    sta temp + 2
    phx
    jsr carry_one
    plx
    rep #$20
.a16
    lda temp
    sta f:CALL_STACK, x
    txa
    clc
    adc #CALL_ENTRY
    tax
    sep #$20
.a8
    dey
    bne frame
frames_done:
    lda temp + 3
    lsr a
    bcc not_moved
    ; One moved now: the map being left is the one to carry.
    rep #$20
.a16
    lda map_current
    sta f:CARRY_MAP
    sep #$20
.a8
    rtl
not_moved:
    lsr a
    bcc none
    ; Or it was already carried, from an earlier jump: it stays where it is,
    ; and `CARRY_MAP` too.
    rtl
none:
    rep #$20
.a16
    lda #$FFFF
    sta f:CARRY_MAP
    sep #$20
.a8
    rtl
.endproc

; One pointer into a page's bytecode, in `temp` to `temp + 2`: if it is in
; the bytecode of the map being left, it moves to the same byte where it
; will be carried —the page's jumps are relative to where it starts, so
; moving the pointer is enough— and bit 0 of `temp + 3` goes up; if it is
; already where a carried map lives, bit 1. One in the cartridge does not
; move.
.proc carry_one
.a8
.i16
    lda temp + 2
    cmp #^GRID_HIGH
    bne done                    ; from the cartridge, where it does not move
    rep #$20
.a16
    lda map_current
    asl a
    asl a
    asl a                       ; times MAP_CODE_STRIDE
    tax
    lda temp
    sec
    sbc f:map_code + 4, x       ; where this map's bytecode starts
    bcc not_this_one
    cmp f:map_code + 6, x       ; and how long it is
    bcs not_this_one
    clc
    adc #.loword(CODE_CARRY)
    sta temp                    ; the same byte, where it will be carried
    sep #$20
.a8
    lda temp + 3
    ora #1
    sta temp + 3
    rts
not_this_one:
.a16
    lda temp
    cmp #.loword(CODE_CARRY)
    bcc done_16
    cmp #.loword(CODE_CARRY + LZ2_CAP_CODE)
    bcs done_16
    sep #$20
.a8
    lda temp + 3
    ora #2
    sta temp + 3
    rts
done_16:
    sep #$20
.a8
done:
    rts
.endproc

; With the new map loaded —`LZ2_BUFFER` already used— or after the battle:
; the carried map's bytecode, if there is one, into `CODE_CARRY`.
.proc code_carry_after
.a8
.i16
    rep #$20
.a16
    lda f:CARRY_MAP
    cmp #$FFFF
    beq none
    asl a
    asl a
    asl a                       ; times MAP_CODE_STRIDE
    tax
    lda f:map_code, x
    pha
    sep #$20
.a8
    lda #^CODE_CARRY
    sta f:LZ2_BANK
    lda f:map_code + 2, x
    plx
    ldy #.loword(CODE_CARRY)
    jsl f:lz2_decompress + FAST
    rtl
none:
    sep #$20
.a8
    rtl
.endproc

; Each block's caps come from the reservation in far_ram.s and the converter
; enforces them when compressing: if either side moves on its own, the build
; must fail.
.assert LZ2_BUFFER + LZ2_CAP_BACKDROP <= ANIM_DRAWINGS_END, error, "the background tiles do not fit in the load buffer"
.assert LZ2_BUFFER + LZ2_CAP_ABOVE_Y_SPRITES <= ANIM_DRAWINGS, error, "the upper layer or the sprites would overwrite the animation drawings"
.assert ANIM_DRAWINGS + LZ2_CAP_ANIM <= ANIM_DRAWINGS_END, error, "the animation drawings do not fit in their place"
.assert GRID_HIGH = GRID + $10000, error, "the two halves of the grid must be the same address in two consecutive banks: that is how `ptr_more` walks them"
.assert LZ2_CAP_GRID <= 2 * (GRID_END - GRID), error, "the largest grid does not fit in the two upper halves of WRAM"
.assert MAP_CODE_STRIDE = 8, error, "code_carry_before and code_carry_after multiply by eight"
.assert LZ2_BUFFER + 2 * ANIM_B_FRAME_MAX <= CODE_CARRY, error, "the carried bytecode would overwrite the battle animation's frames"
.assert CODE_CARRY + LZ2_CAP_CODE <= ANIM_DRAWINGS, error, "the carried bytecode would overwrite the ChipSet animation's drawings"
