.segment "CODE"

; --- the MSU-1 --------------------------------------------------------------
;
; The MSU-1 is not console hardware: it is an extension supported by the FX
; Pak Pro and the emulators, with the music in PCM files next to the ROM. When
; the song being started has a track —`song_msu`, emitted by the converter—,
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
MSU_STATE   = $2000
MSU_SIGNATURE = $2002
MSU_TRACK   = $2004
MSU_VOLUME = $2006
MSU_CONTROL = $2007
MSU_HAS     = $7E30E8           ; whether the signature is there
MSU_PLAYING = $7E30E9           ; whether the track is playing right now

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
MSU_VOLUME_MAX = $D8

; And two bytes for the fade factor, in far RAM because bank 0's is full. The
; high byte always stays at zero: the loop adds it as sixteen bits. It lives
; here and not in `temp` because the fade runs inside `irq_music`.
MSU_FACTOR  = $7E30EA

; The signature, once, at reset.
.proc msu_detect
.a8
.i16
    lda #0
    sta f:MSU_PLAYING
    ldx #$0000
clear:
    sta f:MSU_MISSING, x        ; no track has been missing yet
    inx
    cpx #MSU_MISSING_BYTES
    bcc clear
    ldx #$0000
look:
    lda MSU_SIGNATURE, x
    cmp msu_signature, x
    bne none
    inx
    cpx #6
    bcc look
    lda #1
    sta f:MSU_HAS
    rts
none:
    lda #0
    sta f:MSU_HAS
    rts
.endproc

msu_signature:
    .byte "S-MSU1"

; Silences the track, if there was one.
.proc msu_stop
.a8
.i16
    lda f:MSU_PLAYING
    beq ready
    lda #0
    sta f:MSU_PLAYING
    sta MSU_CONTROL
ready:
    rts
.endproc

; Waits for the MSU-1 to release `AUDIO_BUSY`. Returns with carry clear if it
; released it and set if time ran out. Clobbers X.
;
; **No core in the test suite exercises this loop.** bsnes never sets
; `io.audioBusy` —it starts false in `power()` and is not written anywhere;
; it is in bsnes's `sfc/coprocessor/msu1/msu1.cpp`—,
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
MSU_WAIT = $FFFF

.proc msu_wait
.a8
.i16
    ldx #$0000
other:
    lda MSU_STATE
    and #$40                    ; it is loading it
    beq ready
    inx
    cpx #MSU_WAIT
    bcc other
    sec
    rts
ready:
    clc
    rts
.endproc

; Starts the track for song A, if it has one and if there is an MSU-1. Returns
; with A nonzero if the track was left playing, and then the SPC700 music does
; not go.
.proc msu_start
.a8
.i16
    pha
    lda f:MSU_HAS               ; one byte at a time: with `ldx` it read the
                                ; next byte too
    beq no_msu1
    pla
    cmp #SONG_TOTAL
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:song_msu, x            ; outside bank 0, like `song_lo`
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
    jsr msu_wait
    bcs fails                   ; still busy: let the SPC700 play
    tya
    sta MSU_TRACK
    stz MSU_TRACK + 1
    jsr msu_wait                ; and now, for it to finish opening it
    bcs fails
    lda MSU_STATE
    and #$08                    ; the track is not on the card
    bne fails
    plx
    lda f:MSU_BASE              ; MSU_VOLUME_MAX at the `PlayBGM`'s volume
    sta MSU_VOLUME
    lda #$03                    ; play and repeat
    sta MSU_CONTROL
    lda #1
    sta f:MSU_PLAYING
    rts
fails:
    ; The song plays through the SPC700 and needs its samples, which the
    ; package did not upload because it counted on the track —see
    ; `song_per_msu`—: they are uploaded by `song_ensure`, which is what
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
run:
    dey
    bmi ran
    asl a
    bra run
ran:
    ora f:MSU_MISSING, x
    sta f:MSU_MISSING, x
    bra no
no_msu1:
    pla
no:
    lda #0
    rts
.endproc
.assert SONG_TOTAL <= 8 * MSU_MISSING_BYTES, error, "MSU_MISSING does not have a bit for every song"


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
; msu_data.rs in rm2k-snes-audio and internals/the-msu-file.md in the book. Today it is the battle
; backgrounds, and **the ROM still carries its own**: this replaces them only
; if there is an MSU-1 and the `.msu` is this cartridge's.
;
; It goes in bank 1 because it is called by the battle scene, which runs with
; the data bank at $7E: that is why every register goes through `f:`. A bare
; `lda $2000` would read WRAM. The scene now lives in `FAR2`, and reaches
; these through `msu_data_seek_l` and `msu_data_valid_l`.
MSU_SEEK    = $2000             ; write: the position, four bytes
MSU_DATA    = $2001             ; read: the next byte
.segment "FAR"

; Seeks in the `.msu` to the 32-bit position given in A —the low sixteen, with
; 16-bit A— and in Y —the high ones— and waits for the MSU-1 to have it.
; Returns with 8-bit A, carry clear if it was ready and set if time ran out.
; Clobbers X.
;
; Sixteen-bit writes go to the low byte first, so $2003, the one that seeks,
; is the last: that is the order the MSU-1 asks for.
;
; **No core in the test suite exercises the wait**, same as `msu_wait`:
; bsnes, snes9x, mesen-s and ares never set `dataBusy` —they seek on the
; spot—. **Mednafen does**: `MSU1_WriteDataSeek` sets bit 7 for 400,000 master
; cycles, and since `MSU1_ReadStatus` does not catch up, it clears at the end
; of the frame in which they elapse: each seek costs one or two frames.
; Measured on 2026-09-26 in the droid battle playing from the title: the
; background comes from the `.msu`, with `SCN_FRAMES` at 11 against 4 in
; snes9x. See "How long it takes" in `internals/the-msu-file.md` in the book.
;
; On the FX Pak, seeking outside its 16 KB buffer means reading the SD card
; —`prepare_data` in sd2snes's `src/msu1.c`—, a few milliseconds.
; The cap is the same as the audio's and for the same reason: $FFFF passes of
; 114 master cycles —this runs in bank 1, slow—, about twenty-one frames, ten
; times what Mednafen takes. Falling short does not cost a frame but makes the
; battle use the ROM's background.
.proc msu_data_seek
.a16
.i16
    sta f:MSU_SEEK
    tya
    sta f:MSU_SEEK + 2
    sep #$20
.a8
    ldx #$0000
other:
    lda f:MSU_STATE
    bpl ready                   ; bit 7: still seeking
    inx
    cpx #MSU_WAIT
    bcc other
    sec
    rts
ready:
    clc
    rts
.endproc

; Whether the `.msu` is this cartridge's: A at 1 if there is an MSU-1 and the
; first 8 bytes of the `.msu` are `msu_data_signature`, which the converter
; derives from the contents. With another `.msu` —from another build, empty,
; truncated— or without an MSU-1, A at 0 and the ROM uses its own. A `.msu`
; shorter than the signature also gives 0: the three emulators return zero
; past the end, and the signature is not eight zeros except by a one in 2^64
; chance.
.proc msu_data_valid
.a8
.i16
    lda f:MSU_HAS
    beq no
    rep #$20
.a16
    lda #0
    tay
    jsr msu_data_seek
.a8
    bcs no
    ldx #0
compares:
    lda f:MSU_DATA
    cmp f:msu_data_signature, x
    bne no
    inx
    cpx #8
    bcc compares
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; `msu_data_seek` and `msu_data_valid` for the battle scene, which lives in
; another bank —`FAR2`— and cannot reach them with `jsr`. They stay here and
; not there because `msu_effects.s` calls them too.
.proc msu_data_seek_l
.a16
    jsr msu_data_seek
.a8
    rtl
.endproc

.proc msu_data_valid_l
.a8
    jsr msu_data_valid
    rtl
.endproc

; --- a cartridge that needs the MSU-1 -------------------------------------------
;
; A game whose ROM does not reach carries in the `.msu` what does not fit
; —`[rom] msu = "required"` in its project file; see `lz2_msu` in
; decompress.s—, and without it there is nothing to fall back on. So the
; boot asks, once, before loading anything: whether there is an MSU-1, whether
; the `.msu` is this cartridge's —its signature, `msu_data_valid`— and whether
; the region of what did not fit is this build's —its own signature, at unit
; 0 of the region, against `msu_spill_signature`, which the packing emits—.
; If any of the three fails, the screen that says so (`SCREEN_MSU_MISSING`,
; drawn by the converter: see `msu_missing.rs` in rm2k-snes-convert), and
; nothing else: it does not return.
;
; Only in a cartridge that needs it: the rest neither ask nor carry the
; screen, and without MSU-1 they are the same game.
.ifdef MSU_REQUIRED
.proc msu_required
.a8
.i16
    lda f:MSU_HAS
    beq missing
    jsr msu_data_valid
    cmp #1
    bne missing
    ldx #0
    jsr msu_spill_seek
    ldx #0
compares:
    lda f:MSU_DATA
    cmp f:msu_spill_signature, x
    bne missing
    inx
    cpx #8
    bcc compares
    rtl
missing:
    ldx #(SCREEN_MSU_MISSING * SCREEN_ROW)
    jsl f:screen_decompress
    jsl f:screen_upload
    lda #$0F
    sta f:INIDISP
stays:
    bra stays
.endproc
.endif
