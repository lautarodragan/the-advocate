.segment "CODE"

; --- music -------------------------------------------------------------------
; The stream is per note: notes, releases, volume or pitch changes of a voice
; that is playing, and waits; `music_frame` expands it into DSP writes. The
; opcodes are declared by `tools/protocol/music.toml` and the equate comes out
; generated: until 2026-09-15 they were written by hand here **and** in
; tools/audio/snes_music.py, which is what writes the stream, with nothing tying
; the two copies together.

; One music frame per video frame, plus an extra one every five if the console
; is PAL: six every five is exactly 60 per 50.
.proc irq_music
    jml f:rapida + RAPIDO       ; the vector lands in bank 0: see MEMSEL
rapida:
    ; Everything touched is saved, B and D included: this lands in the middle
    ; of anything, among them the interpreter with B pointing at the bytecode.
    rep #$30
.a16
.i16
    pha
    phx
    phy
    phb
    phd
    lda #0
    pha
    pld                         ; the direct page at zero
    sep #$20
.a8
    phk
    plb                         ; the music tables, in bank 0
    lda TIMEUP                  ; clears the flag: otherwise it comes back in
    jsr music_tick
    rep #$30
.a16
.i16
    pld
    plb
    ply
    plx
    pla
    rti
.endproc

.proc music_tick
.a8
.i16
    ; The `FadeOutBGM` first, and **outside** the `music_apagada` guard: it is
    ; what will set it when the volume reaches zero.
    lda bgm_fundido
    beq sin_fundido
    jsr bgm_fade_tick
sin_fundido:
    ; The sound effects wrap around the music, and run even when it is silent:
    ; see "sound effects" in `efectos_de_sonido.s`.
    jsr se_before
    lda music_apagada
    bne ready
    jsr music_frame
    lda es_pal
    beq ready
    inc pal_tick
    lda pal_tick
    cmp #5
    bcc ready
    stz pal_tick
    jsr music_frame             ; the frame PAL is missing
ready:
    jmp se_after
.endproc

; Starts from the beginning the song whose index is in A. The start of the
; stream carries the DSP setup —the volumes, the sample directory— so calling
; here again is exactly what a `PlayBGM` does: start from scratch.
;
; The cartridge has carried several songs since 2026-09-06 and **they all share
; the sample bank**, which is uploaded only once at boot: changing song is
; changing stream and nothing else, so it does not cost even a frame. Hence
; there is nothing to upload here. See `Banco` in tools/audio/snes_music.py.
;
; Which index is playing stays in `tema_actual`, which is what `music_frame`
; needs to start over when the stream ends: without it the loop always went
; back to the first one.
.proc music_start
.a8
.i16
    ; The main code calls it with the music running —`PlayBGM`, the title—,
    ; and changing the pointer halfway with `irq_music` reading it would be
    ; playing one song from the middle of another.
    pha
    jsr msu_stop               ; the previous track, if there was one
    pla
    pha
    jsr msu_start
    beq sin_pista
    ; With a track, the SPC700 goes silent: the stream does not run and the
    ; voices release.
    pla
    sta tema_actual
    stz tema_actual + 1
    php
    sei
    lda #1
    sta music_apagada
    stz bgm_fundido
    lda #$FF
    ldx #SE_KOF
    jsr dsp_pair                 ; the eight voices release, and KOF stays set
    ; And the DSP has to be set up here, which is what was missing: the start
    ; of the stream does it —FLG without the mute the SPC700 boots with, the
    ; master volume, and where the sample directory is— and with a track the
    ; stream never runs. Without this the sound effects fire against a mute
    ; DSP: measured in the opening, running with the sound effect and with it
    ; suppressed gave **zero** samples of difference.
    ;
    ; KOF stays at $FF, which is what keeps the music's voices silent;
    ; `se_after` clears it by itself when a sound effect starts.
    ldy #0
otro_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_listo
    tax                         ; dsp_pair looks only at X's low byte
    lda dsp_init_val, y
    jsr dsp_pair
    iny
    bra otro_init
init_listo:
    plp
    rts
sin_pista:
    ; The song stays on the stack: `song_ensure` clobbers the accumulator,
    ; and `music_start_done` needs it. Pulling it earlier left the song at $FF,
    ; the stream pointer outside its table and the ROM mute within ten frames.
    pla
    pha
    jsr song_ensure           ; that its samples are in the ARAM
    pla
    php
    sei
    ; Any fade in progress is cancelled, since otherwise it would keep lowering
    ; the song the `PlayBGM` just started. Here and not in `music_start_done`,
    ; which is also the loop back to the start of the song: a song that loops
    ; in the middle of a `FadeOutBGM` keeps fading out, as in RM2k. Until
    ; 2026-09-26 the loop cancelled it, because the start of the stream
    ; restored the master volume, which was what the fade lowered.
    stz bgm_fundido
    jsr music_start_done
    plp
    rts
.endproc

.proc music_start_done
.a8
.i16
    sta tema_actual
    stz tema_actual + 1
    ldx tema_actual
    lda tema_lo, x
    sta music
    lda tema_hi, x
    sta music + 1
    lda tema_bk, x
    sta music + 2
    ; The decoder from scratch: no wait, no pending key-ons, and with nothing
    ; valid in the cache —each voice's first note rewrites it—. This also
    ; happens when looping back to the start of the song, and it is what makes
    ; the second time around write the same as the first.
    lda #0
    sta f:MUS_KON
    sta f:MUS_SONANDO
    sta f:MUS_VISTAS
    sta f:MUS_GAINS
    rep #$20
.a16
    lda #0                      ; again: the 8-bit `lda #0` did not
    sta f:MUS_ESPERA            ; clear B, and the wait is sixteen bits
    lda tema_actual
    asl a
    tax
    lda f:tema_sonidos, x
    sta f:MUS_BASE
    sep #$20
.a8
    stz music_apagada
    rts
.endproc

; One frame of `FadeOutBGM`: lowers the song and, when it reaches zero, cuts
; it. It is `Game_System::BgmFade`, which in RM2k does not block the page that
; asked for it either.
;
; The level is sixteen bits and goes from 65535 to zero. The alternative
; —lowering a seven-bit register one at a time— would give ninety-six steps
; for a three-hundred-frame fade and it would be heard in steps.
;
; **What gets lowered is the song and nothing else**: without MSU-1, the volume
; of each music voice —see `volume_refresh`—, and with MSU-1, the track's.
; Until 2026-09-26, without MSU-1 it lowered the DSP's master volume, which is
; also the sound effects', and left it at zero until the next song: the
; thunder at the end of map 3 played silent. `test_fundido_del_tema.py`
; catches it.
.proc bgm_fade_tick
.a8
.i16
    rep #$20
.a16
    lda bgm_nivel
    jsr level_factor
    sta f:FUNDIDO_ANTES         ; the one the DSP has
    lda bgm_nivel
    sec
    sbc bgm_paso
    bcs baja                    ; still some left
    lda #0
baja:
    sta bgm_nivel
    jsr level_factor
    sta f:FUNDIDO_N             ; this frame's
    sep #$20
.a8
    lda bgm_nivel
    ora bgm_nivel + 1
    bne sigue
    stz bgm_fundido
    lda #1
    sta music_apagada           ; the song is cut, like `BgmFade`
sigue:
    lda f:MSU_PLAYING
    bne pista
    jmp voices_refresh
pista:
    ; With a track, the fade lowers **its** volume: MSU_VOLUME_MAX times the
    ; level, over 256. **Not with the CPU's multiplier**: this runs in
    ; `irq_music`, and the main code uses it in thirty places —the divider
    ; shares the result register—; an interrupt between its write and its read
    ; would change its result. Not with the PPU's either, which is eight-bit
    ; signed and MSU_VOLUME_MAX does not fit. So by hand, one bit of the level
    ; at a time, with `dsp_valor` as scratch: it belongs to the music only.
    rep #$20
.a16
    lda #MSU_VOLUME_MAX
    sta f:MSU_FACTOR            ; the loop adds it with `adc f:`: there is
    sep #$20                    ; nowhere to keep a partial, and no `,s` here
.a8
    lda bgm_nivel + 1
    sta dsp_valor
    ldx #8
    rep #$20
.a16
    lda #0
bit_del_nivel:
    asl a
    sep #$20
.a8
    asl dsp_valor               ; sep and rep do not touch carry
    rep #$20
.a16
    bcc sin_sumar
    clc
    adc f:MSU_FACTOR
sin_sumar:
    dex
    bne bit_del_nivel
    xba                         ; the product's high byte, that is, over 256
    sep #$20
.a8
    sta MSU_VOLUME
    cmp #0
    bne listo_msu
    jsr msu_stop               ; reached zero: the track is cut
listo_msu:
    rts
.endproc

; 16-bit A: the fade level. Returns with its factor, from 0 to 256: the high
; byte plus one, except for zero. That way the full level, $FFFF, is 256, which
; is the volume **untouched** —with 255 the first frame would already lower
; every voice by a step—, and zero is silence.
.proc level_factor
.a16
.i16
    cmp #0
    beq ready
    xba
    and #$00FF
    inc a
ready:
    rts
.endproc

; The volume of the music's voices, kept up to date with the fade: VOL_L and
; VOL_R of each voice that has already played in this song, scaled by
; FUNDIDO_N. Only the ones that changed since the previous frame are rewritten
; —the one scaled by FUNDIDO_ANTES is what the DSP already has—: a
; three-hundred-frame fade moves each volume once every so many frames, and
; each write waits on the SPC700.
;
; They go through `dsp_music`, so the voices that have a sound effect playing
; are not touched: the value goes to their shadow, and they get it back scaled
; when the sound effect ends.
.proc voices_refresh
.a8
.i16
    ldx #0                      ; the voice's VOL_L: the DSP register
    ldy #0                      ; the voice
otra_voz:
    lda f:MUS_VISTAS
    and voice_bit, y
    beq siguiente               ; did not play in this song: not sounding
    jsr volume_refresh
    inx
    jsr volume_refresh          ; VOL_R
    dex
siguiente:
    rep #$21                    ; and carry at zero
.a16
    txa
    adc #$10
    tax
    sep #$20
.a8
    iny
    cpy #8
    bcc otra_voz
    rts
.endproc

; A voice's volume register X, with what the stream wrote to it —MUS_SOMBRA—
; times FUNDIDO_N, over 256, if that changed with respect to FUNDIDO_ANTES.
; The product is done by the PPU's multiplier, which belongs to `irq_music`
; —see M7A—: signed, which is what a DSP volume is, and without waiting.
; Does not touch X or Y.
.proc volume_refresh
.a8
.i16
    lda f:MUS_SOMBRA, x
    sta M7B
    lda f:FUNDIDO_ANTES
    sta M7A
    lda f:FUNDIDO_ANTES + 1
    sta M7A
    lda MPYM
    pha                         ; what the DSP has
    lda f:FUNDIDO_N
    sta M7A
    lda f:FUNDIDO_N + 1
    sta M7A
    lda MPYM                    ; what it should have
    cmp 1, s
    beq igual
    jsr dsp_music
igual:
    pla
    rts
.endproc

; A: a voice volume the stream is about to write to the DSP. Returns with it
; times FUNDIDO_N, over 256. It is the same computation as `volume_refresh`,
; so what the music writes in the middle of a fade and what the fade rewrites
; afterwards match. Does not touch X, Y or V.
.proc volume_fade
.a8
.i16
    sta M7B
    lda f:FUNDIDO_N
    sta M7A
    lda f:FUNDIDO_N + 1
    sta M7A
    lda MPYM
    rts
.endproc

; The music when the ROM boots. `TEMA_ARRANQUE` is the song of the map the ROM
; boots into, or $FF if that map has none —which is the usual case in this
; game: the first maps carry no music and a `PlayBGM` turns it on—. Silent
; means nothing is written to the DSP, so there is nothing to silence.
.proc music_boot
.a8
.i16
    php
    sei
    jsr music_boot_done
    plp
    rts
.endproc

.proc music_boot_done
.a8
.i16
    ; A loaded save brings its own song —the one the event's `PlayBGM` turned
    ; on— and `load_game` already left it in `tema_actual` and
    ; `music_apagada`. Without this the save would start with the song of the
    ; ROM's starting map, which is the opening's and not the one of the place
    ; where the player saved.
    lda ranura
    cmp #$FF
    beq del_mapa                ; no slot loaded: the map's song
    lda music_apagada
    bne callado                 ; saved at a moment without music
    lda tema_actual
    jmp music_start
del_mapa:
    lda #TEMA_ARRANQUE
    cmp #$FF
    bne suena
callado:
    lda #1
    sta music_apagada
    ; And the MSU-1 track, which `music_apagada` does not silence: coming from
    ; the title its track kept playing inside the game until the first
    ; `PlayBGM`, and a battle in between recorded it as the song to restore.
    ; `test_con_msu_la_pista_del_titulo_no_sigue_en_la_partida` catches it.
    jmp msu_stop
suena:
    jmp music_start
.endproc

; Advances the music pointer by one byte, returning in A what was already read.
;
; In LoROM each bank exposes only its upper half, $8000-$FFFF, so the byte after
; $00FFFF is not $010000 but $018000. A plain 24-bit increment would land in
; bank 1's RAM and read garbage. With the whole song plus the samples going
; past 64 KB, this is not theoretical: it is crossed for sure.
.proc advance
.a8
.i16
; The accumulator holds the byte the caller just read, so it has to be
; returned intact: hence the pha/pla in the bank-crossing branch.
    inc music
    bne done
alto:                           ; where `READ` continues when the low byte wrapped
    inc music + 1
    bne done                    ; if the high part did not wrap, done
    pha
    lda #$80                    ; it wrapped: to the next bank, at $8000
    sta music + 1
    pla
    inc music + 2
done:
    rts
.endproc

; `lda [music]` and `jsr advance`, without the `jsr` in the common case: it is
; what repeats the most per event, and the pointer's low byte wraps once every
; 256.
.macro READ
    .local ready
    lda [music]
    inc music
    bne ready
    jsr advance::alto
ready:
.endmacro

; One frame of music. The stream is per note —see "el formato por nota" in
; tools/audio/snes_music.py and the header of tools/protocol/music.toml— and
; here it is expanded into the DSP writes that `dsp_music` sends: exactly
; those of `escrituras`, frame by frame, and
; rom/pruebas/rpgmaker/test_musica_escrituras.py checks it. It reads until it
; hits a wait, which closes the frame: it keys on the voices that got a note,
; and the next frame opens by clearing that key-on. On reaching the end it
; starts over.
;
; Starting over has a trap: an **empty** stream is a lone OP_END, so restarting
; leads to reading OP_END again and the loop never exits. The ROM hung on the
; first frame, with the screen already on and the map drawn —so it seemed to
; work—. It stayed hidden all this time because `musicdata.inc` was generated
; by a separate recipe and always had a real song; it showed up as soon as the
; converter started emitting the map's music, and most of the game's maps have
; none.
;
; The guard is not restarting twice in the same frame: if after going back to
; the start the first thing there is another end, there is nothing to play.
.proc music_frame
.a8
.i16
    stz reinicio
    lda f:MUS_BITACORA_SI
    beq sin_marca
    jsr log_frame
sin_marca:
    rep #$20
.a16
    lda f:MUS_ESPERA
    beq abrir
    dec a
    sta f:MUS_ESPERA
    sep #$20
.a8
    rts

abrir:
.a16
    sep #$20
.a8
    lda f:MUS_SONANDO           ; clear the previous frame's key-on
    beq leer
    lda #0
    sta f:MUS_SONANDO
    ldx #SE_KON
    jsr dsp_music

leer:
    READ
    cmp #OP_WAIT_1
    bcs no_es_de_voz
    jmp de_voz
no_es_de_voz:
    cmp #OP_WAIT
    bcc espera_corta
    beq espera_larga
    cmp #OP_DSP
    beq cruda
    cmp #OP_INIT
    bne no_init
    jmp arranque
no_init:
    cmp #OP_END
    bne mudo                    ; an opcode that does not exist: go silent
                                ; rather than write anything to the DSP
    lda reinicio
    bne mudo
    inc reinicio
    lda tema_actual             ; it ended: the same one, again from the top
    jsr music_start_done          ; inside the IRQ: no `sei` and no package
    bra leer
mudo:
    ; An empty stream: nothing to play, neither this frame nor the ones to
    ; come. And it has to be said with the flag, because `advance` left the
    ; pointer **one byte past the end** and coming back here the next frame
    ; read that byte as an opcode. It was $FF by chance —the first byte of the
    ; neighboring block— until the on-the-fly poses changed the ROM's layout
    ; and it became $00: a DSP write with its SPC700 wait, and another, and
    ; another, half a screen per frame, and the loop at half speed. Three cases
    ; in the suite gave it away with a repeated frame, and a scanline probe at
    ; the end of each phase of the loop.
    lda #1
    sta music_apagada
    rts

cruda:
    ; A register that does not belong to a voice, so it skips the cache.
    lda [music]
    jsr advance
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda [music]
    jsr advance
    jsr dsp_music
    bra leer

espera_corta:
    sec
    sbc #OP_WAIT_1 - 1          ; from 1 to ESPERA_CORTA
    rep #$20
.a16
    and #$00FF
    bra cerrar
espera_larga:
.a8
    lda [music]
    jsr advance
    xba
    lda [music]
    jsr advance
    xba                         ; 16-bit A: the two bytes, low first
    rep #$20
.a16
cerrar:
    ; The frame closes: the voices that got a note are keyed on together.
    pha
    sep #$20
.a8
    lda f:MUS_KON
    beq sin_kon
    sta f:MUS_SONANDO
    ldx #SE_KON
    jsr dsp_music
    lda #0
    sta f:MUS_KON
sin_kon:
    rep #$20
.a16
    ; The `pla` leaves Z from the value it pulls, and that is on purpose: a
    ; zero-frame wait keys on and keeps reading in the same frame, without
    ; opening another.
    pla
    beq sigue
    dec a
    sta f:MUS_ESPERA
    sep #$20
.a8
    rts
sigue:
.a16
    sep #$20
.a8
    jmp leer

arranque:
    ; The DSP setup: the same table the MSU-1 path uses, and after it KON and
    ; KOF at zero. See `escrituras_del_arranque`.
    ldy #0
otro_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_listo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda dsp_init_val, y
    jsr dsp_music              ; does not touch Y
    iny
    bra otro_init
init_listo:
    lda #0
    ldx #SE_KON
    jsr dsp_music
    lda #0
    ldx #SE_KOF
    jsr dsp_music
    jmp leer

de_voz:
    ; The voice in the three low bits and the family in the ones above: see
    ; the header of music.toml. Y ends up with the voice's VOL_L register.
    rep #$20
.a16
    and #$00FF
    pha
    and #$0007
    tax                         ; the voice
    asl a
    asl a
    asl a
    asl a
    tay
    sep #$20
.a8
    lda voice_bit, x
    sta f:MUS_BIT
    rep #$20
.a16
    pla
    and #$0038
    lsr a
    lsr a                       ; the family times two
    tax
    sep #$20
.a8
    jmp (families, x)
.endproc

; One per family, in the order of their numbers.
families:
    .addr ev_note, ev_note_vol, ev_note_pan, ev_release, ev_release_gain
    .addr ev_set_vol, ev_set_pan, ev_set_pitch
.assert OP_NOTE_V0 = 0, error, "music.toml: the families start at 0"
.assert OP_NOTE_VOL_V0 = OP_NOTE_V0 + 8, error, "music.toml: families out of order"
.assert OP_NOTE_PAN_V0 = OP_NOTE_VOL_V0 + 8, error, "music.toml: families out of order"
.assert OP_RELEASE_V0 = OP_NOTE_PAN_V0 + 8, error, "music.toml: families out of order"
.assert OP_RELEASE_GAIN_V0 = OP_RELEASE_V0 + 8, error, "music.toml: families out of order"
.assert OP_SET_VOL_V0 = OP_RELEASE_GAIN_V0 + 8, error, "music.toml: families out of order"
.assert OP_SET_PAN_V0 = OP_SET_VOL_V0 + 8, error, "music.toml: families out of order"
.assert OP_SET_PITCH_V0 = OP_SET_PAN_V0 + 8, error, "music.toml: families out of order"
.assert OP_WAIT_1 = OP_SET_PITCH_V0 + 8, error, "music.toml: the waits go after them"

voice_bit:
    .byte $01, $02, $04, $08, $10, $20, $40, $80

; Writes A to register Y, unless the cache says it already has it. With V set
; it writes without looking: that is how the first note of each voice since
; the song started goes, and the first GAIN, because the cache starts with
; whatever was left and has no way of saying "I don't know". Does not touch
; X, Y or V.
.proc mus_write
.a8
.i16
    phx
    tyx
    bvs escribir
    cmp f:MUS_SOMBRA, x
    beq igual
escribir:
    sta f:MUS_SOMBRA, x
    ; In the middle of a `FadeOutBGM`, the volume goes scaled: the shadow keeps
    ; the stream's, which is what the cache compares against and what
    ; `volume_refresh` derives each frame's from. VOL_L and VOL_R are the
    ; voice's first two registers.
    pha
    lda bgm_fundido
    beq tal_cual
    txa
    and #$0E
    bne tal_cual
    pla
    jsr volume_fade
    bra mandar
tal_cual:
    pla
mandar:
    jsr dsp_music
igual:
    plx
    rts
.endproc

; V set if the event's voice has not had a note yet, and marks it. Does not
; touch X or Y.
.proc first_note
.a8
.i16
    clv
    lda f:MUS_BIT
    and f:MUS_VISTAS
    bne already
    lda f:MUS_BIT
    ora f:MUS_VISTAS
    sta f:MUS_VISTAS
    sep #$40                    ; V
already:
    rts
.endproc

.proc ev_note_vol
.a8
.i16
    jsr first_note
    READ
    pha
    jsr mus_write            ; VOL_L
    iny
    pla
    jsr mus_write            ; VOL_R, the same one
    iny
    jmp note_sound
.endproc

.proc ev_note_pan
.a8
.i16
    jsr first_note
    READ
    jsr mus_write            ; VOL_L
    iny
    READ
    jsr mus_write            ; VOL_R
    iny
    jmp note_sound
.endproc

.proc ev_note
.a8
.i16
    jsr first_note
    iny
    iny
    ; falls through into note_sound
.endproc

; The note's sound: Y on the voice's PITCH_L and V as `first_note` left it.
; Its first five bytes go to PITCH_L, PITCH_H, SRCN, ADSR1 and ADSR2, in that
; order, and the sixth is the GAIN it will be released with.
.proc note_sound
.a8
.i16
    READ
    php                         ; the additions clobber V
    rep #$21                    ; 16-bit A and carry at zero
.a16
    and #$00FF
    sta f:MUS_T
    asl a
    adc f:MUS_T
    asl a                       ; times six
    adc f:MUS_BASE
    tax
    plp
.a8
    .repeat 5, k
    lda f:musica_sonidos + k, x
    jsr mus_write
    iny
    .endrepeat
    lda f:musica_sonidos + 5, x
    tyx                         ; the voice's register 8, which is ENVX
    sta f:MUS_SOMBRA + 1, x
    lda f:MUS_BIT
    ora f:MUS_KON
    sta f:MUS_KON
    jmp music_frame::leer
.endproc

.proc ev_release_gain
.a8
.i16
    lda [music]
    jsr advance
soltar:
    pha
    iny
    iny
    iny
    iny
    iny                         ; ADSR1
    clv
    lda #0
    jsr mus_write
    iny
    iny                         ; GAIN
    lda f:MUS_BIT
    and f:MUS_GAINS
    bne con_gain
    lda f:MUS_BIT
    ora f:MUS_GAINS
    sta f:MUS_GAINS
    sep #$40                    ; the first one goes without looking at the cache
con_gain:
    pla
    jsr mus_write
    jmp music_frame::leer
.endproc

.proc ev_release
.a8
.i16
    tyx
    lda f:MUS_SOMBRA + 8, x     ; the GAIN of the voice's sound
    bra ev_release_gain::soltar
.endproc

.proc ev_set_vol
.a8
.i16
    clv
    lda [music]
    jsr advance
    pha
    jsr mus_write
    iny
    pla
    jsr mus_write
    jmp music_frame::leer
.endproc

.proc ev_set_pan
.a8
.i16
    clv
    lda [music]
    jsr advance
    jsr mus_write
    iny
    lda [music]
    jsr advance
    jsr mus_write
    jmp music_frame::leer
.endproc

.proc ev_set_pitch
.a8
.i16
    clv
    iny
    iny                         ; PITCH_L
    lda [music]
    jsr advance
    jsr mus_write
    iny
    lda [music]
    jsr advance
    jsr mus_write
    jmp music_frame::leer
.endproc

; The decoder state at zero, and the log off. At reset: far RAM starts with
; garbage.
.proc music_clear
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:MUS_ESPERA, x
    inx
    cpx #MUS_ESTADO_BYTES
    bcc otro
    sta f:MUS_BITACORA_SI
    sta f:MUS_BITACORA_I
    sta f:MUS_BITACORA_I + 1
    rts
.endproc
