.segment "CODE"

; --- the MSU-1 --------------------------------------------------------------
;
; The MSU-1 is not console hardware: it is an extension supported by the FX
; Pak Pro and the emulators, with the music in PCM files next to the ROM. When
; the song being started has a track —`tema_msu`, emitted by the converter—,
; the SPC700 goes quiet and the track plays; sound effects stay on the SPC700
; as always. Without an MSU-1 nothing changes: the signature is not there and
; everything keeps coming out of the SPC700.
;
; The registers live at $2000..$2007 of any bank in the low area:
;
;   $2000  read: bit 7 data busy, 6 track loading, 5 repeating,
;          4 playing, 3 track missing, 2..0 revision
;   $2002..$2007  read: the signature "S-MSU1"
;   $2004  write: which track, two bytes
;   $2006  the volume, 0 to 255
;   $2007  bit 0 play, bit 1 repeat
MSU_ESTADO  = $2000
MSU_FIRMA   = $2002
MSU_PISTA   = $2004
MSU_VOLUMEN = $2006
MSU_CONTROL = $2007
MSU_HAY     = $7E30E8           ; whether the signature is there
MSU_SUENA   = $7E30E9           ; whether the track is playing right now

; The volume the track plays at, 0 to 255, and **it is not 255**: the MSU-1 is
; added to the SPC700's output instead of being mixed with it, so music at full
; volume leaves no headroom for the sound effects. With 255, in the opening, 42
; samples hit the ceiling —all 42 in frames with an effect playing—, while the
; same run through the SPC700 does not clip once. Also measured: the music
; from the track peaked at 28933 against 23867 from the SPC700, that is 1.21
; times louder, which is what taro heard as "the effects sound much quieter".
;
; $D8 is that 0.85. It brings the music down to where it was and gives back
; the headroom, without touching the tracks: normalizing them lower would mean
; 195 MB to redo per ROM, and on top of that it would lose the level reference
; between one song and another.
MSU_VOLUMEN_MAX = $D8

; And two bytes for the fade factor, in far RAM because bank 0's is full. The
; high byte always stays at zero: the loop adds it as sixteen bits. It lives
; here and not in `temp` because the fade runs inside `irq_musica`.
MSU_FACTOR  = $7E30EA

; The signature, once, at reset.
.proc msu_detectar
.a8
.i16
    lda #0
    sta f:MSU_SUENA
    ldx #$0000
limpiar:
    sta f:MSU_FALTA, x          ; no track has been missing yet
    inx
    cpx #MSU_FALTA_BYTES
    bcc limpiar
    ldx #$0000
mirar:
    lda MSU_FIRMA, x
    cmp msu_firma, x
    bne no_hay
    inx
    cpx #6
    bcc mirar
    lda #1
    sta f:MSU_HAY
    rts
no_hay:
    lda #0
    sta f:MSU_HAY
    rts
.endproc

msu_firma:
    .byte "S-MSU1"

; Silences the track, if there was one.
.proc msu_parar
.a8
.i16
    lda f:MSU_SUENA
    beq listo
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
listo:
    rts
.endproc

; Waits for the MSU-1 to release `AUDIO_BUSY`. Returns with carry clear if it
; released it and set if time ran out. Clobbers X.
;
; **No core in the test suite exercises this loop.** bsnes never sets
; `io.audioBusy` —it starts false in `power()` and is not written anywhere;
; it is in `/extras/ref/bsnes-libretro/bsnes/sfc/coprocessor/msu1/msu1.cpp`—,
; and neither does snes9x, so in the suite it exits on the first pass.
; **Mednafen does** (`-force_module snes_faust`): it sets bit 6 for 400,000
; master cycles when the track is chosen —`MSU1_WriteTrack` in
; `snes_faust/msu1.cpp`— and only clears it at the end of the frame in which
; they elapse, that is one or two frames. That the tracks play there is the
; proof that this loop waits. On the FX Pak the track comes off the SD card,
; and that is not measured.
;
; That is why the cap is generous and not tight: $FFFF passes of 96 master
; cycles —from the fast mirror—, about seventeen frames. It used to be $4000
; —seventy milliseconds— and the price of falling short is not a lost frame
; but the whole song playing through the SPC700.
MSU_ESPERA = $FFFF

.proc msu_esperar
.a8
.i16
    ldx #$0000
otra:
    lda MSU_ESTADO
    and #$40                    ; it is loading it
    beq listo
    inx
    cpx #MSU_ESPERA
    bcc otra
    sec
    rts
listo:
    clc
    rts
.endproc

; Starts the track for song A, if it has one and if there is an MSU-1. Returns
; with A nonzero if the track was left playing, and then the SPC700 music does
; not go.
.proc msu_arrancar
.a8
.i16
    pha
    lda f:MSU_HAY               ; one byte at a time: with `ldx` it read the
                                ; next byte too
    beq sin_msu1
    pla
    cmp #TEMA_TOTAL
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda tema_msu, x
    cmp #$FF
    beq no
    ; **Before writing the track, wait for the MSU-1 to be free.** With
    ; `AUDIO_BUSY` set the hardware ignores writes to the audio registers —in
    ; bsnes it shows in `writeIO`, `case 0x2007: if(io.audioBusy) break;`—,
    ; so a `PlayBGM` that arrives while the previous track is still opening is
    ; lost entirely. Here it really happens: with a title screen there are two
    ; tracks requested 1.8 s apart —the title's and the opening's—, and without
    ; a title screen the first one is the only one.
    ;
    ; The track is kept in Y meanwhile: the wait uses X. The song goes on the
    ; stack, to record it if the track fails.
    phx
    tay
    jsr msu_esperar
    bcs falla                   ; still busy: let the SPC700 play
    tya
    sta MSU_PISTA
    stz MSU_PISTA + 1
    jsr msu_esperar             ; and now, for it to finish opening it
    bcs falla
    lda MSU_ESTADO
    and #$08                    ; the track is not on the card
    bne falla
    plx
    lda #MSU_VOLUMEN_MAX
    sta MSU_VOLUMEN
    lda #$03                    ; play and repeat
    sta MSU_CONTROL
    lda #1
    sta f:MSU_SUENA
    rts
falla:
    ; The song plays through the SPC700 and needs its samples, which the
    ; package did not upload because it counted on the track —see
    ; `tema_por_msu`—: they are uploaded by `tema_asegurar`, which is what
    ; `music_start` calls next, and from now on this song's packages upload
    ; them from the start.
    plx
    rep #$20
.a16
    txa
    and #$0007
    tay                         ; the bit
    txa
    lsr a
    lsr a
    lsr a
    tax                         ; the byte
    sep #$20
.a8
    lda #1
correr:
    dey
    bmi corrido
    asl a
    bra correr
corrido:
    ora f:MSU_FALTA, x
    sta f:MSU_FALTA, x
    bra no
sin_msu1:
    pla
no:
    lda #0
    rts
.endproc
.assert TEMA_TOTAL <= 8 * MSU_FALTA_BYTES, error, "MSU_FALTA does not have a bit for every song"


; --- the data port ----------------------------------------------------------
;
; The `.msu` is not only what turns the MSU-1 on: it is a file the ROM reads
; as a stream. A 32-bit position is written to $2000..$2003 —the write to
; $2003 is the one that seeks—, you wait for bit 7 of $2000 to clear, and you
; read from $2001, which advances by itself. By DMA with the source fixed at
; $2001 it runs at the speed of any DMA: in bsnes the A-bus only excludes
; $2100..$21FF and the CPU registers (`validA`, in sfc/cpu/dma.cpp), and in
; snes9x page $2000 is `MAP_PPU`, with no direct pointer, so the DMA goes byte
; by byte through `S9xGetPPU`, which serves the MSU-1.
;
; What is inside and in what format is decided by the converter: see
; tools/port/msu_datos.py and docs/port/msu-datos.md. Today it is the battle
; backgrounds, and **the ROM still carries its own**: this replaces them only
; if there is an MSU-1 and the `.msu` is this cartridge's.
;
; It goes in bank 1 because it is called by the battle scene, which runs there
; with the data bank at $7E: that is why every register goes through `f:`. A
; bare `lda $2000` would read WRAM.
MSU_BUSCAR  = $2000             ; write: the position, four bytes
MSU_DATOS   = $2001             ; read: the next byte
.segment "FAR"

; Seeks in the `.msu` to the 32-bit position given in A —the low sixteen, with
; 16-bit A— and in Y —the high ones— and waits for the MSU-1 to have it.
; Returns with 8-bit A, carry clear if it was ready and set if time ran out.
; Clobbers X.
;
; Sixteen-bit writes go to the low byte first, so $2003, the one that seeks,
; is the last: that is the order the MSU-1 asks for.
;
; **No core in the test suite exercises the wait**, same as `msu_esperar`:
; bsnes, snes9x, mesen-s and ares never set `dataBusy` —they seek on the
; spot—. **Mednafen does**: `MSU1_WriteDataSeek` sets bit 7 for 400,000 master
; cycles, and since `MSU1_ReadStatus` does not catch up, it clears at the end
; of the frame in which they elapse: each seek costs one or two frames.
; Measured on 2026-09-26 in the droid battle playing from the title: the
; background comes from the `.msu`, with `ESC_CUADROS` at 11 against 4 in
; snes9x. See "Cuánto tarda" in docs/port/msu-datos.md.
;
; On the FX Pak, seeking outside its 16 KB buffer means reading the SD card
; —`prepare_data` in `/extras/ref/sd2snes/src/msu1.c`—, a few milliseconds.
; The cap is the same as the audio's and for the same reason: $FFFF passes of
; 114 master cycles —this runs in bank 1, slow—, about twenty-one frames, ten
; times what Mednafen takes. Falling short does not cost a frame but makes the
; battle use the ROM's background.
.proc msu_datos_buscar
.a16
.i16
    sta f:MSU_BUSCAR
    tya
    sta f:MSU_BUSCAR + 2
    sep #$20
.a8
    ldx #$0000
otra:
    lda f:MSU_ESTADO
    bpl listo                   ; bit 7: still seeking
    inx
    cpx #MSU_ESPERA
    bcc otra
    sec
    rts
listo:
    clc
    rts
.endproc

; Whether the `.msu` is this cartridge's: A at 1 if there is an MSU-1 and the
; first 8 bytes of the `.msu` are `msu_datos_firma`, which the converter
; derives from the contents. With another `.msu` —from another build, empty,
; truncated— or without an MSU-1, A at 0 and the ROM uses its own. A `.msu`
; shorter than the signature also gives 0: the three emulators return zero
; past the end, and the signature is not eight zeros except by a one in 2^64
; chance.
.proc msu_datos_validos
.a8
.i16
    lda f:MSU_HAY
    beq no
    rep #$20
.a16
    lda #0
    tay
    jsr msu_datos_buscar
.a8
    bcs no
    ldx #0
compara:
    lda f:MSU_DATOS
    cmp f:msu_datos_firma, x
    bne no
    inx
    cpx #8
    bcc compara
    lda #1
    rts
no:
    lda #0
    rts
.endproc
