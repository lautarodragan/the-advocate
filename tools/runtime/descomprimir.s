.segment "FAR"

; --- LZ2: what the cartridge carries compressed -------------------------------
;
; The tiles of the map, of the sprites, of the upper layer, of the ChipSet
; animation, and the grid travel in the cartridge in LC_LZ2, Nintendo's format,
; and are decompressed into WRAM when the map loads, with the screen off inside
; the fade. The format and the reason for this one and not another are in
; tools/port/compress.py; the compressor is `tools/lz2/`.
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
; and this way it is read from the ROM's fast mirror. The stream's changes from
; block to block, so the literal's `mvn` is built in RAM at the start
; —`LZ2_TRAMPA_LIT`— and called with `jsl`; running from WRAM costs it a few
; cycles per byte, because `mvn` reads its code again for each one.
;
; The stream is read with the data bank set to its own and `lda a:0, x`, through
; the fast mirror: the direct page is full and there is nowhere to put a 24-bit
; pointer. That is why each compressed block fits whole in one bank —the
; converter declares it with `.bloque`—: X cannot go past $FFFF.

; Decompresses a stream. Enters with an 8-bit A and 16-bit X and Y: X and A
; where the stream is —address and bank—, Y where the output goes inside bank
; `LZ2_BANCO`, which the caller sets and is $7E or $7F. Leaves with X on the
; byte after the $FF —the next stream starts there, if another one follows
; right after— and Y on the byte after the last one it wrote. Clobbers A;
; leaves P and the data bank as they were.
;
; The output cannot cross a bank: Y wraps at $FFFF and the converter watches
; for it, with streams of up to 32 KB.
.proc lz2_descomprimir
.a8
.i16
    php
    phb
    ora #^RAPIDO                ; the stream, through the fast mirror
    pha
    ; The literal's trampoline. In `mvn`'s machine code the destination bank
    ; goes first and the source bank after.
    sta f:LZ2_TRAMPA_LIT + 2
    lda #$54                    ; mvn
    sta f:LZ2_TRAMPA_LIT
    lda #$6B                    ; rtl
    sta f:LZ2_TRAMPA_LIT + 3
    lda f:LZ2_BANCO
    sta f:LZ2_TRAMPA_LIT + 1
    plb                         ; the stream's bank
    rep #$20
.a16
    tya
    pha                         ; 3,s: the output's base
    pha                         ; 1,s: the command's length, minus one
    sep #$20
.a8
    lda f:LZ2_BANCO
    cmp #^GRILLA_ALTA
    bne en_el_7e
    jmp lz2_cuerpo_7f
en_el_7e:
    jmp lz2_cuerpo_7e
.endproc

; The body, for output in bank `salida`. It is entered from
; `lz2_descomprimir` with the stream's bank set and the length and base on the
; stack, and it returns from right there.
.macro LZ2_CUERPO salida
comando:
    sep #$20
.a8
    lda a:0, x
    cmp #$E0
    bcs largo
    ; `CCCLLLLL`: up to 32 bytes.
    rep #$20
.a16
    and #$001F
    sta 1, s
    sep #$20
.a8
    lda a:0, x                  ; and again, to dispatch
    inx
    bra despachar
largo:
    cmp #$FF
    beq fin
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
despachar:
    asl a
    bcs repeticion              ; 4: 5 and 6 do not exist
    asl a
    bcs palabra                 ; 2; 3, the increasing fill, never arrives
    asl a
    bcs relleno
    ; 0: the bytes, from the stream to the output.
    rep #$20
.a16
    lda 1, s
    phb
    jsl f:LZ2_TRAMPA_LIT
    plb
    bra comando

fin:
.a8
    inx                         ; the $FF
    rep #$20
.a16
    pla
    pla
    plb
    plp
    rtl

relleno:
.a8
    ; 1: the byte to the output, and it is repeated shifted by one.
    lda a:0, x
    inx
    phx                         ; the stream, while X points at the output
    tyx
    sta f:salida << 16, x
    iny
    rep #$20
.a16
    lda 3, s                    ; the length minus one, moved by the `phx`
    beq listo                   ; it was just one
    dec a                       ; the ones left, minus one
    bra en_la_salida

palabra:
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
    sta f:salida << 16, x
    iny
    iny
    lda 3, s                    ; the length minus one, moved by the `phx`
    dec a
    beq listo                   ; it was two
    dec a
    bra en_la_salida

repeticion:
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
en_la_salida:
    ; With X inside the output, A the length minus one and the stream pointer
    ; on the stack. The `mvn` leaves the data bank at the output's.
    phb
    mvn #salida, #salida
    plb
listo:
    plx
    jmp comando

.endmacro

.proc lz2_cuerpo_7e
    LZ2_CUERPO ^GRILLA
.endproc

.proc lz2_cuerpo_7f
    LZ2_CUERPO ^GRILLA_ALTA
.endproc

; X and A of the stream that field Y of the map record points to: its address
; and its bank, ready for `lz2_descomprimir`.
.proc lz2_del_campo
.a8
.i16
    rep #$20
.a16
    tya
    clc
    adc mapa_ofs
    tax
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    pha
    rep #$20
.a16
    lda f:mapa_tabla, x
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; The block that field Y of the map record points to, decompressed into
; `LZ2_BUFFER`, and DMA channel 0 pointing there: it replaces `dma_origen` in
; `load_map`, `load_above` and `load_sprite`, which still set the length and
; the destination as before. The length comes from the record and not from
; what the decompressor wrote, so what reaches VRAM is the same as when the
; cartridge carried the tiles whole.
.proc lz2_campo
.a8
.i16
    jsr lz2_del_campo
    pha
    lda #^LZ2_BUFFER
    sta f:LZ2_BANCO
    pla
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_descomprimir + RAPIDO
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
; `LZ2_TOPE_FONDO` bytes —map 66's, with the 544-tile layout— comes in two
; streams back to back, and the second is decompressed **after** uploading the
; first, in the same place: decompressed whole it does not fit in the buffer,
; and whatever overflowed landed in the upper half of the grid. The converter
; splits into stretches of exactly `LZ2_TOPE_FONDO` —see `partes_comprimidas`—,
; so how many tiles each stream carries follows from how many tiles the map has
; and there is no need to record it.
;
; Enters with VMAIN and VMADD set; the DMA carries the VRAM address on from one
; stream to the next. Leaves the tile bank uploaded and clobbers A, X and Y.
FONDO_TILES_POR_FLUJO = LZ2_TOPE_FONDO / 64     ; 64 bytes per 8-bit tile
.proc lz2_fondo
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_TILES, x
    pha                         ; the tiles still to upload
    sep #$20
.a8
    ldy #M_PTR_MAP_TILES
    jsr lz2_del_campo
    pha                         ; 1,s: the stream's bank; 2,s: the ones left
flujo:
    lda #^LZ2_BUFFER
    sta f:LZ2_BANCO
    lda 1, s
    ldy #.loword(LZ2_BUFFER)
    jsl f:lz2_descomprimir + RAPIDO     ; leaves X on the next stream
    rep #$20
.a16
    ; The ones that will be left after this one: zero if this is the last.
    lda 2, s
    sec
    sbc #FONDO_TILES_POR_FLUJO
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
    bne flujo
    pla
    rep #$20
.a16
    pla
    sep #$20
.a8
    rtl
.endproc

; The drawings of the map's ChipSet animation, into `ANIM_DIBUJOS`, from where
; `anim_subir` uploads them each time the clock changes. They have to stay
; there while on the map, so they go in a place of their own and not in
; `LZ2_BUFFER`, which the upper layer and the sprites overwrite afterwards: see
; the reservation in `ram_lejana.s`.
.proc lz2_anim
.a8
.i16
    ldy #M_PTR_ANIM_TILES
    jsr lz2_del_campo
    pha
    lda #^ANIM_DIBUJOS
    sta f:LZ2_BANCO
    pla
    ldy #.loword(ANIM_DIBUJOS)
    jsl f:lz2_descomprimir + RAPIDO
    rtl
.endproc

; The map's grid, decompressed into `GRILLA`: its first 32 KB in the upper half
; of bank $7E and the rest in $7F's, which is the shape `ptr_mas` and
; `ptr_menos` expect. The converter splits it into two streams, one per half,
; so no output crosses a bank; the second comes right after the first, and may
; have nothing more than its $FF.
;
; Battle overwrites $7F's half —it is `ESC_ESCENA`—, so `volver_de_batalla`
; decompresses it again. See the decision in
; workflow/decisiones/la-grilla-vive-en-la-wram.md.
.proc lz2_grilla
.a8
.i16
    ldy #M_PTR_MAP_CELDAS
    jsr lz2_del_campo
    pha                         ; the stream's bank, for the second one
    lda #^GRILLA
    sta f:LZ2_BANCO
    pla
    pha
    ldy #.loword(GRILLA)
    jsl f:lz2_descomprimir + RAPIDO     ; leaves X on the second stream
    lda #^GRILLA_ALTA
    sta f:LZ2_BANCO
    pla
    ldy #.loword(GRILLA_ALTA)
    jsl f:lz2_descomprimir + RAPIDO
    rtl
.endproc

; Each block's caps come from the reservation in ram_lejana.s and the converter
; enforces them when compressing: if either side moves on its own, the build
; must fail.
.assert LZ2_BUFFER + LZ2_TOPE_FONDO <= ANIM_DIBUJOS_FIN, error, "the background tiles do not fit in the load buffer"
.assert LZ2_BUFFER + LZ2_TOPE_ENCIMA_Y_SPRITES <= ANIM_DIBUJOS, error, "the upper layer or the sprites would overwrite the animation drawings"
.assert ANIM_DIBUJOS + LZ2_TOPE_ANIM <= ANIM_DIBUJOS_FIN, error, "the animation drawings do not fit in their place"
.assert GRILLA_ALTA = GRILLA + $10000, error, "the two halves of the grid must be the same address in two consecutive banks: that is how `ptr_mas` walks them"
.assert LZ2_TOPE_GRILLA <= 2 * (GRILLA_FIN - GRILLA), error, "the largest grid does not fit in the two upper halves of WRAM"
