.segment "CODE"

; --- the message window ----------------------------------------------------
; Its tiles and palette are uploaded only once, with the screen off, like
; those of the layer above. They live behind the ones of the layer above, and
; BG2 reaches them with the same base: depending on the layout, the layer
; above has 128 or 256 tiles and the window starts at that index. That is why
; the converter emits two planes of cells, one with each offset added, and
; `estampar_ventana` picks one.
;
; Its palette is palette **0**, that is the entries below the background, and
; `cargar_mapa_sin_eventos` uploads it together with the screen's backdrop
; color.
.proc load_ventana
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(ventana_tiles)
    sta A1T0L
    lda #(VENTANA_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; The window's palette is not uploaded here: it is palette **0**, that is
    ; the entries `cargar_mapa_sin_eventos` already uploaded together with the
    ; backdrop color. It used to float below the lowest layer above in the
    ; ROM and got uploaded on its own; with that, every map's background was
    ; squeezed below it —47 colors— even when they had half of CGRAM free
    ; above.

    ; The window's own tilemap and the HDMA tables, which belong to this map:
    ; the window lives at a VRAM location that depends on the layout.
    jsr estampar_ventana
    jsr armar_hdma
    rts
.endproc

; Writes the window's own tilemap: 320 contiguous cells, a single DMA.
;
; Here is the whole difference with what there was before. The window is no
; longer stamped onto the map's tilemap —which scrolls— but onto one of its
; own, 32x32, that it shares with no one. Since it is its own, its ten rows
; of 32 cells are 320 contiguous words: there are no stretches, no wrapping,
; no column 32 to dodge. And since nobody else touches it, this runs **only
; once per map**, from `load_ventana` and with the screen already off.
;
; Who shows it and where is decided by HDMA; see `armar_hdma`.
.proc estampar_ventana
.a8
.i16
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    ; Which plane: the one that has baked in the index where the window
    ; starts, which is the distance between it and BG2's base —the high
    ; nibble of BG12NBA—. The layouts put it 128 tiles behind or, the one with
    ; a 256-tile layer above, 256: 256 tiles of 4bpp are $1000 words, $10 in
    ; the high byte. See `VENTANA_BASES` in the converter.
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    and #$F0
    sta temp
    lda f:mapa_tabla + M_VRAM_VENTANA + 1, x
    sec
    sbc temp
    cmp #$10                    ; the carry survives the `rep` and the `lda`
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP, x
    sta VMADDL
    lda #(VENTANA_FILAS * VENTANA_COLS * 2)
    sta DAS0L
    bcs plano_256
    lda #.loword(ventana_celdas)
    sta A1T0L
    sep #$20
.a8
    lda #^ventana_celdas
    bra con_plano
plano_256:
.a16
    lda #.loword(ventana_celdas_256)
    sta A1T0L
    sep #$20
.a8
    lda #^ventana_celdas_256
con_plano:
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Sets up the two HDMA tables and programs their channels. Runs once per map,
; together with the rest of the load.
;
; What HDMA achieves, and no amount of stamping achieved: BG2 changes tilemap
; and scroll **mid-frame**. From line 0 to 143 it is still the map's layer
; above, with the camera; from 144 to 223 it is the window's own tilemap, with
; the scroll pinned. That is why the window does not move even though the
; camera does, and why there is not a single VRAM write while a message is on
; screen.
;
; The first two entries carry exactly what `flush_video` was already writing
; to the registers, so above line 144 nothing changes. They go in two
; stretches because an entry's line counter is 7 bits and 144 does not fit.
.proc armar_hdma
.a8
.i16
    lda #127
    sta hdma_sc
    sta hdma_ofs
    lda #(VENTANA_LINEA - 127)
    sta hdma_sc + 2
    sta hdma_ofs + 5
    lda #(LINEAS - VENTANA_LINEA)
    sta hdma_sc + 4
    sta hdma_ofs + 10

    ; The map's tilemap on top and the window's below. BG2SC carries the
    ; address in the high byte; the window's size is 0, which is 32x32.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1
    sta hdma_sc + 3
    ldx mapa_ofs
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP + 1, x
    sta hdma_sc + 5
    stz hdma_sc + 6             ; end of table

    ; And the pinned scroll of the window's lines. The two stretches above are
    ; filled by `flush_video` with each frame's camera.
    stz hdma_ofs + 11
    stz hdma_ofs + 12
    lda #<VENTANA_VOFS
    sta hdma_ofs + 13
    lda #>VENTANA_VOFS
    sta hdma_ofs + 14
    stz hdma_ofs + 15           ; end of table

    lda #$00                    ; one register, one write per stretch
    sta DMAP1
    lda #<BG2SC
    sta BBAD1
    ldx #hdma_sc
    stx A1T1L
    stz A1B1                    ; the tables live in bank 0

    lda #$03                    ; two registers, two writes each, which
    sta DMAP2                   ; is what BG2HOFS and BG2VOFS ask for
    lda #<BG2HOFS
    sta BBAD2
    ldx #hdma_ofs
    stx A1T2L
    stz A1B2

    ; And the third channel hides the objects under the window. In RM2k the
    ; message window covers everything —`Priority_Window` is 130 and the
    ; characters go below it—, but here it is BG2 with priority 1, and an
    ; event marked "above" goes in objects with priority 2, which in mode 3
    ; sits *in front* of BG2: it showed through the window. The suite caught
    ; it with the door on map 7 as soon as events drawn with a tile moved to
    ; sprites. The mask is the PPU's window 1, edge to edge, enabled for
    ; objects only on the lines of the message window: `hdma_mascara`, which
    ; never changes and lives in the ROM.
    lda #$00
    sta DMAP3
    lda #<WOBJSEL
    sta BBAD3
    ldx #.loword(hdma_mascara)
    stx A1T3L
    lda #^hdma_mascara          ; no longer bank 0: it lives in RODATA
    sta A1B3
    rts
.endproc

; --- the text composer -----------------------------------------------------
;
; What makes this fit in a 65816. RM2k draws each glyph using its pixels as a
; **mask** over a 16x16 block of the System, and read that way it asks for
; sampling the block pixel by pixel. Measured, that is not needed: each row of
; the glyph takes a single color —the gradient is vertical— and the shadow is
; a flat color. So all the color comes down to twelve bytes, `fuente_color`,
; plus `FUENTE_SOMBRA`. That is the measurement that made this cheap.
;
; The text area is 30 cells wide by 8 tall and its 240 tiles **are not
; deduplicated**: each cell has its own, fixed, so composing is writing a
; buffer and uploading it. It is done one line at a time —two cell rows, 60
; tiles, 1920 bytes— and uploaded in the next vblank.
;
; A line is primed with the window's background before the text is written
; on it, because glyphs are not drawn on black but on the skin's gradient.
; That is a DMA from ROM to RAM, which normal DMA cannot do: it goes through
; the window WRAM has on bus B, that is WMADD plus $2180.

; How many characters per pass of the loop. The number is **measured**, not
; chosen: composing the `snes-anclada` message over map 6, with 5 no frame is
; lost, with 6 neither, and with 8 one is lost. It is 5 and not 7 for margin,
; because a pass costs differently on each map —the background streaming, the
; NPCs, the music— and losing frames does not show by looking: what happens is
; that the hero walks slower than in RM2k.
;
; What it costs: the three-line, 51-character message of `snes-ventana` takes
; about 15 frames to appear, and one with four full lines would take about 36.
; That is a quarter of a second, which does not stand out in RM2k either:
; there the window opens with an animation.
MSG_CHARS = 5

; Where the text starts inside the window, in pixels. It is `Window`'s
; `border_x`, the same one `tools/port/window.py` uses.
VENTANA_BORDE = 8

; The glyph's row falls two pixels below the cell's edge, and that does not
; depend on the line: all four start at 10, 26, 42 and 58, which modulo 8 are
; all 2. That is why a twelve-row glyph always fits in the same two cell rows
; and the buffer can be two rows tall.
TEXTO_OFS_Y = 2

; One byte further in the text block, crossing the bank window.
;
; `msg_ptr` is a long pointer but the composer advanced it with a 16-bit
; `inc`, so on going past $FFFF it went back to $0000 of the **same** bank.
; In LoROM there is no ROM there: what follows $FFFF is $8000 of the next
; bank, which is what `ptr_mas` and `msg_empezar` already knew.
;
; It is not theoretical and fixing `msg_empezar` was not enough: `abl`'s text
; block is 56 KB, so it crosses, and **a box whose bytes fall across the
; edge** starts fine and goes on reading garbage. It is the Neon Vipers
; cutscene on map 14: out of the garbage came a line length of 76 characters
; and with it the whole screen turned to garbage, along the path that the cap
; in `mensaje_tick` now cuts off.
.proc msg_ptr_sig
.a16
.i16
    inc msg_ptr
    bne listo
    lda #$8000
    sta msg_ptr
    sep #$20
.a8
    inc msg_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

; Starts a message: leaves the pointer on its first line and the composer
; running. The window does not appear until it finishes.
;
; **A carries the box's offset within `mensajes`, in 16 bits**, and it has to
; be added to a long pointer crossing banks: see the loop below and
; `msg_ptr_sig`, which is the same arithmetic for advancing one byte at a
; time.
.assert MENSAJES_TOPE = 4 * $10000, error, "msg_empezar multiplies the offset by four: it is MENSAJES_PASO in eventos.py"
.proc msg_empezar
.a16
.i16
    ; The offset is sixteen bits and the text block can be **larger than a
    ; LoROM bank's window**: with the 29 maps of `abl` it is 48972 bytes and
    ; starts at $46:8000, so from offset $8000 on the sum goes past $FFFF.
    ; What follows $FFFF is not $0000 of the next bank but its $8000, which
    ; is the same thing `ptr_mas` already knew for the map grid; here it was
    ; added sixteen bits at a time and the carry was lost, so **every text box
    ; past the first bank read from somewhere else**: the header and the line
    ; lengths came out of anything. The loop adds one bank per pass because a
    ; 64 KB block crosses up to twice.
    ;
    ; And the offset counts in steps of four bytes —`MENSAJES_PASO` in
    ; eventos.py—, so the block reaches 256 KB: the two bits that fall out of
    ; the `asl`s go to `temp`, and each unit of what it gathers is 64 KB, that
    ; is two LoROM banks. With `rol` and not with a branch per bit on purpose:
    ; that way the top bit —more than 128 KB, which no cartridge in the suite
    ; reaches— runs the same instructions as the bottom one, which does.
    phx
    stz temp
    asl a
    rol temp
    asl a
    rol temp
    pha
    lda temp
    asl a                       ; two banks per 64 KB
    clc
    adc #^mensajes
    tax
    pla
    clc
    adc #.loword(mensajes)
otro_banco:
    bcc en_el_banco
    inx
    clc
    adc #$8000
    bra otro_banco
en_el_banco:
    sta msg_ptr
    sep #$20
.a8
    txa
    sta msg_ptr + 2
    rep #$20
.a16
    plx
    ; The escape queue starts clean before reading the header: a garbage pause
    ; there would leave the page stuck forever.
    lda #0
    sta f:FAR_MSG_PAUSA         ; `stz` has no long mode
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ldy #0
    lda [msg_ptr], y            ; the header: the lines in the bottom three
    sta msg_lineas              ; bits, the auto-close in bit 3 and the pauses
                                ; in the top nibble. It is stored whole and
                                ; whoever reads it masks it; one more byte in
                                ; bank 0 is exactly what there is not.
    and #CABECERA_AUTOCIERRE
    sta f:FAR_MSG_AUTO
    lda msg_lineas
    lsr
    lsr
    lsr
    lsr                         ; how many pauses it carries
    beq sin_pausa
    ; And how long they last: `CUADROS_DE_PAUSA` each, which is 61 and not 60.
    ; The product is 16 bits because fifteen pauses are 915 frames, so the
    ; hardware does it, as with the tint.
    sta WRMPYA
    lda #CUADROS_DE_PAUSA
    sta WRMPYB                  ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta f:FAR_MSG_PAUSA
    sep #$20
.a8
sin_pausa:
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
    stz msg_linea
    stz msg_cebada
    stz msg_subir
    lda #1
    sta msg_estado
    rts
.endproc

; One frame of the composer, from the main loop.
.proc mensaje_tick
.a8
.i16
    lda msg_estado
    cmp #1
    beq trabajando
    rts
trabajando:
    lda msg_subir
    beq sin_subir
    rts                         ; the previous line has not been uploaded yet
sin_subir:
    lda msg_cebada
    bne componiendo

    ; New line: the background is copied into it and its length is read. The
    ; lines the message does not carry are primed and uploaded anyway: VRAM
    ; holds the previous message's text and it has to be covered.
    jsr cebar_linea
    stz msg_largo
    lda msg_lineas
    and #CABECERA_LINEAS        ; the header also carries the escape queue
    sta temp
    lda msg_linea
    cmp temp
    bcs vacio
    ldy #0
    lda [msg_ptr], y
    sta msg_largo
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
vacio:
    stz msg_col
    lda #1
    sta msg_cebada

componiendo:
    ldx #MSG_CHARS
otro:
    lda msg_col
    cmp msg_largo
    bcs fin_linea
    ldy #0
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sta comp_char
    lda msg_col
    and #$00FF
    sta comp_col
    jsr msg_ptr_sig
    sep #$20
.a8
    inc msg_col
    ; The column cap. The byte is consumed anyway —otherwise the pointer
    ; would be out of step and the next line would read from the middle of
    ; this one— but it is not drawn: `componer_char` writes into `texto_buf`
    ; with an offset that comes from the column, and from 39 on that lands
    ; **outside** the buffer, on top of the window's HDMA, the OAM image and
    ; `vq_n`. See the comment on `componer_char`, further down.
    ;
    ; And the cap goes here even though the converter never emits a longer
    ; line, because **the symptom does not point at the text**: with `vq_n`
    ; overwritten, `vram_drenar` uploads 128-byte blocks to arbitrary VRAM
    ; addresses, so a bad line length shows up as the whole screen turned to
    ; garbage a few frames later and on another map.
    lda comp_col
    cmp #MENSAJE_COLS
    bcs sin_dibujar
    phx
    jsr componer_char
    plx
sin_dibujar:
    dex
    bne otro
    rts

fin_linea:
    ; The line is ready: it goes up in the next vblank and we move on to the
    ; next one. The next one's background is not primed in this same frame on
    ; purpose: the buffer still holds what has to be uploaded.
    lda #1
    sta msg_subir
    stz msg_cebada
    inc msg_linea
    lda msg_linea
    cmp #VENTANA_LINEAS_TEXTO
    bcc mas
    lda #2
    sta msg_estado              ; done: `flush_video` turns on the HDMA
mas:
    rts
.endproc

; Copies into the buffer the background of the two cell rows of the current
; line. It is the only way for the glyphs to sit on the skin's gradient and
; not on black, and it goes by DMA from ROM to RAM.
.proc cebar_linea
.a8
.i16
    rep #$20
.a16
    ; The destination: always the start of the buffer.
    lda #.loword(texto_buf)
    sta WMADDL
    sep #$20
.a8
    stz WMADDH                  ; the buffer lives in WRAM bank 0

    rep #$20
.a16
    ; The source: two cell rows per line, 60 tiles of 32 bytes.
    lda msg_linea
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; line * 64
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; line * 60, that is the tiles already past
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 bytes each
    clc
    adc #.loword(ventana_fondo)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_fondo
    sta A1B0
    lda #$00                    ; one register, one byte at a time
    sta DMAP0
    lda #<WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Uploads the composed line to the window's tile bank. It goes in the vblank,
; from `flush_video`, and it is 1920 bytes in a single DMA.
.proc subir_linea
.a8
.i16
    stz msg_subir
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    rep #$20
.a16
    ; The tile where this line starts, in VRAM words. The line to upload is
    ; the previous one: `mensaje_tick` already moved on to the next.
    lda msg_linea
    and #$00FF
    dec a
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; line * 60 tiles
    clc
    adc #VENTANA_TEXTO_BASE
    asl a
    asl a
    asl a
    asl a                       ; times 16 words per tile
    clc
    adc f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the buffer lives in bank 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; One character, from its already composed data: `fuente_pre0` to
; `fuente_pre3`, one table per phase, built by `fuente_prerender` in the
; converter. For each of the FUENTE_PRE_FILAS rows and each of the two cells
; it can touch come three words —what is kept from the buffer, and what is
; set in planes 0-1 and in 2-3—, so painting is read, mask and write. A cell
; that touches nothing comes with the mask at $FFFF and is skipped.
;
; **The column is capped by `mensaje_tick`**, not by this: here `comp_col`
; has already arrived as good and the offset that comes from it is used
; without checking. The cap is there because the byte has to be consumed
; anyway even if it is not drawn.
;
; Until 2026-09-11 this painted each row twice —the shadow and then the
; glyph, with a `pintar` routine that built the masks on each call— and
; shifted the row one bit at a time up to its phase: about 25 lines per
; character, and with MSG_CHARS at 5 it was the most expensive thing in the
; frame while a message was being built. taro noticed it in the opening, with
; rain. The result is the same byte for byte: the order of `Font::Render`
; —the shadow of a row is overwritten by the glyph of the next— already comes
; resolved in the tables.
.proc componer_char
.a8
.i16
    lda comp_char
    sta WRMPYA
    lda #FUENTE_PRE_CHAR
    sta WRMPYB                  ; starts: what follows gives it the eight cycles

    ; Where it lands: x = border + 6 per column, and from that the cell and
    ; the phase.
    rep #$20
.a16
    lda comp_col
    sta temp
    asl a
    clc
    adc temp
    asl a                       ; times 6
    clc
    adc #VENTANA_BORDE
    sta temp                    ; x inside the window
    and #$0007
    sta comp_fase               ; 0, 2, 4 or 6
    lda temp
    lsr a
    lsr a
    lsr a
    sec
    sbc #VENTANA_TEXTO_COL      ; the cell column, counted from the text
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times 32 bytes per tile
    sta comp_base

    ; Its data: its phase's table, plus the character times FUENTE_PRE_CHAR.
    ldx comp_fase
    lda f:fuente_pre_lo, x
    clc
    adc RDMPYL
    sta comp_glifo
    sep #$20
.a8
    lda f:fuente_pre_bk, x
    sta comp_glifo + 2

    ldy #0
    lda #(TEXTO_OFS_Y * 2)
    sta comp_fila               ; two at a time: it is the index into `tabla_fila_buf`
fila:
    rep #$20
.a16
    lda comp_fila
    and #$00FF
    tax
    lda f:tabla_fila_buf, x
    clc
    adc comp_base
    tax                         ; X = the buffer byte where the row starts
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_primera
    sta comp_and
    iny
    iny
    lda texto_buf, x            ; planes 0 and 1 of the first cell
    and comp_and
    ora [comp_glifo], y
    sta texto_buf, x
    iny
    iny
    lda texto_buf + 16, x       ; planes 2 and 3
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 16, x
    iny
    iny
    bra segunda
sin_primera:
    tya
    clc
    adc #6
    tay
segunda:
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_segunda
    sta comp_and
    iny
    iny
    lda texto_buf + 32, x       ; the neighboring cell, one tile further
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 32, x
    iny
    iny
    lda texto_buf + 48, x
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 48, x
    iny
    iny
    bra otra_fila
sin_segunda:
    tya
    clc
    adc #6
    tay
otra_fila:
    sep #$20
.a8
    lda comp_fila
    clc
    adc #2
    sta comp_fila
    cmp #((TEXTO_OFS_Y + FUENTE_PRE_FILAS) * 2)
    bcc fila
    rts
.endproc

