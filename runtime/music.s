.segment "CODE"

; --- music -------------------------------------------------------------------
; The stream is per note: notes, releases, volume or pitch changes of a voice
; that is playing, and waits; `music_frame` expands it into DSP writes. The
; opcodes are declared in `rm2k-snes/bytecode/src/music.rs` and the equates
; come out generated: until 2026-09-15 they were written by hand here **and** in the
; compiler that writes the stream —today rm2k-snes/rm2k-snes-audio/—, with nothing
; tying the two copies together.

; One music frame per video frame, plus an extra one every five if the console
; is PAL: six every five is exactly 60 per 50.
.proc irq_music
    jml f:fast + FAST           ; the vector lands in bank 0: see MEMSEL
fast:
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
    ; The `FadeOutBGM` first, and **outside** the `music_off` guard: it is
    ; what will set it when the volume reaches zero.
    lda bgm_fade
    beq no_fade
    jsr bgm_fade_tick
no_fade:
    ; A `PlayBGM` of the song that plays with another volume: after the fade,
    ; which may have rewritten some voices with the gain already new.
    lda f:GAIN_DIRTY
    beq no_gain
    jsr gain_refresh
no_gain:
    ; The sound effects wrap around the music, and run even when it is silent:
    ; see "sound effects" in `sound_effects.s`.
    jsr se_before
    lda music_off
    bne ready
    jsr music_tempo
    lda is_pal
    beq ready
    inc pal_tick
    lda pal_tick
    cmp #5
    bcc ready
    stz pal_tick
    jsr music_tempo             ; the frame PAL is missing
ready:
    jmp se_after
.endproc

; The music frames this video frame owes, at the `PlayBGM`'s tempo: the step
; —256ths of a frame, 256 at tempo 100— goes into `TEMPO_ACC`, and a frame
; runs for each whole one. At 100 that is one and the same frame as before
; the tempo existed; at 150, two every other one; at 50, one every two. It is
; the tempo of a MIDI —RM2k's for these songs—: the stream goes faster and
; each note keeps its pitch.
.proc music_tempo
.a8
.i16
    rep #$21                    ; and carry at zero
.a16
    lda f:TEMPO_ACC
    adc f:BGM_NOW + 2           ; the step
    sta f:TEMPO_ACC
    sep #$20
.a8
other:
    lda f:TEMPO_ACC + 1
    beq ready
    dec a
    sta f:TEMPO_ACC + 1
    jsr music_frame
    lda music_off
    beq other
    lda #0                      ; it went silent: nothing is owed to the next
    sta f:TEMPO_ACC + 1
ready:
    rts
.endproc

; Every voice of the song at the gain that just changed: `voices_refresh`
; with `GAIN_DIRTY` set writes them all, without asking what the DSP has.
; Its factor is the fade's, which without one is 256.
.proc gain_refresh
.a8
.i16
    lda music_off
    bne clean                   ; the SPC700 is silent: nothing to rewrite
    lda bgm_fade
    bne fading
    rep #$20
.a16
    lda #256
    sta f:FADE_N
    sep #$20
.a8
fading:
    jsr voices_refresh
clean:
    lda #0
    sta f:GAIN_DIRTY
    rts
.endproc

; C at 1 if song A is the one playing and is not fading out; A is kept. It is
; the question `Game_System::BgmPlay` asks before touching anything: with the
; same name and no `FadeOutBGM` in between —its `music_stopping`— the song
; goes on where it was. A `FadeOutBGM` that already reached zero left
; `music_off` at 1, so that one starts over too, as in RM2k.
;
; "Is playing" is not only `music_off` at zero: with an MSU-1 track the
; SPC700 is silent on purpose and `music_off` is 1. That is why `MSU_PLAYING`
; is checked first, which is the same thing `op_fade_bgm` does.
.proc song_playing
.a8
.i16
    pha
    lda bgm_fade
    bne no                      ; it was fading out: it starts over
    lda f:MSU_PLAYING
    bne plays
    lda music_off
    bne no
plays:
    lda song_current + 1
    bne no
    pla
    cmp song_current
    bne other                   ; C is not the answer when they differ
    rts                         ; equal: `cmp` left C at 1
no:
    pla
other:
    clc
    rts
.endproc

; What a `PlayBGM` of song A does: if it is already playing —see
; `song_playing`— only its level changes, and otherwise it starts from the
; beginning at that level. The level is the one in `BGM_ASK`: see
; bgm_level.s. The battle's songs come through here too, because RM2k asks
; for them with the same `BgmPlay`: in ABL the victory's is the battle's, and
; it did start over until 2026-09-30. `test_tema_que_ya_suena.py` catches
; both, and `test_volumen_y_tempo.py` the level.
.proc music_play
.a8
.i16
    jsr song_playing
    jsl f:bgm_level_set         ; with C as `song_playing` left it
    bcc music_start_level
    rts
.endproc

; Starts from the beginning the song whose index is in A, even if it is the
; one playing, and as written: the title, a loaded game and a map's own song
; want that. A `PlayBGM` goes through `music_play`, which starts it at its
; level with `music_start_level`. The start of the stream carries the DSP
; setup —the volumes, the sample directory—.
;
; The cartridge has carried several songs since 2026-09-06 and **they all share
; the sample bank**, which is uploaded only once at boot: changing song is
; changing stream and nothing else, so it does not cost even a frame. Hence
; there is nothing to upload here. See `Bank` in rm2k-snes/rm2k-snes-audio/src/bank.rs.
;
; Which index is playing stays in `song_current`, which is what `music_frame`
; needs to start over when the stream ends: without it the loop always went
; back to the first one.
.proc music_start
.a8
.i16
    jsl f:bgm_level_full
    ; falls through into music_start_level
.endproc

.proc music_start_level
.a8
.i16
    ; The main code calls it with the music running —`PlayBGM`, the title—,
    ; and changing the pointer halfway with `irq_music` reading it would be
    ; playing one song from the middle of another.
    pha
    jsr msu_stop                ; the previous track, if there was one
    pla
    pha
    jsr msu_start
    beq no_track
    ; With a track, the SPC700 goes silent: the stream does not run and the
    ; voices release.
    pla
    sta song_current
    stz song_current + 1
    php
    sei
    lda #1
    sta music_off
    stz bgm_fade
    lda #$FF
    ldx #SE_KOF
    jsr dsp_pair                ; the eight voices release, and KOF stays set
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
other_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_ready
    tax                         ; dsp_pair looks only at X's low byte
    lda dsp_init_val, y
    jsr dsp_pair
    iny
    bra other_init
init_ready:
    plp
    rts
no_track:
    ; The song stays on the stack: `song_ensure` clobbers the accumulator,
    ; and `music_start_done` needs it. Pulling it earlier left the song at $FF,
    ; the stream pointer outside its table and the ROM mute within ten frames.
    pla
    pha
    jsl f:song_ensure_l         ; that its samples are in the ARAM
    pla
    php
    sei
    ; Any fade in progress is cancelled, since otherwise it would keep lowering
    ; the song the `PlayBGM` just started. Here and not in `music_start_done`,
    ; which is also the loop back to the start of the song: a song that loops
    ; in the middle of a `FadeOutBGM` keeps fading out, as in RM2k. Until
    ; 2026-09-26 the loop cancelled it, because the start of the stream
    ; restored the master volume, which was what the fade lowered.
    stz bgm_fade
    jsr music_start_done
    plp
    rts
.endproc

.proc music_start_done
.a8
.i16
    sta song_current
    stz song_current + 1
    ldx song_current
    lda f:song_lo, x             ; outside bank 0: see `song_lo` in musicdata.inc
    sta music
    lda f:song_hi, x
    sta music + 1
    lda f:song_bk, x
    sta music + 2
    ; The decoder from scratch: no wait, no pending key-ons, and with nothing
    ; valid in the cache —each voice's first note rewrites it—. This also
    ; happens when looping back to the start of the song, and it is what makes
    ; the second time around write the same as the first.
    lda #0
    sta f:MUS_KON
    sta f:MUS_PLAYING
    sta f:MUS_VIEWS
    sta f:MUS_GAINS
    sta f:MUS_LEFT              ; a `PlayBGM` can land in the middle of a repeat
    rep #$20
.a16
    lda #0                      ; again: the 8-bit `lda #0` did not
    sta f:MUS_WAIT              ; clear B, and the wait is sixteen bits
    lda song_current
    asl a
    tax
    lda f:song_sounds, x
    sta f:MUS_BASE
    sep #$20
.a8
    stz music_off
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
    lda bgm_level
    jsr level_factor
    sta f:FADE_BEFORE           ; the one the DSP has
    lda bgm_level
    sec
    sbc bgm_step
    bcs low                     ; still some left
    lda #0
low:
    sta bgm_level
    jsr level_factor
    sta f:FADE_N                ; this frame's
    sep #$20
.a8
    lda bgm_level
    ora bgm_level + 1
    bne continues
    stz bgm_fade
    lda #1
    sta music_off               ; the song is cut, like `BgmFade`
continues:
    lda f:MSU_PLAYING
    bne track
    jmp voices_refresh
track:
    ; With a track, the fade lowers **its** volume: the track's volume at the
    ; `PlayBGM`'s gain —`MSU_BASE`, MSU_VOLUME_MAX as written— times the
    ; level, over 256. **Not with the CPU's multiplier**: this runs in
    ; `irq_music`, and the main code uses it in thirty places —the divider
    ; shares the result register—; an interrupt between its write and its read
    ; would change its result. Not with the PPU's either, which is eight-bit
    ; signed and MSU_VOLUME_MAX does not fit. So by hand, one bit of the level
    ; at a time, with `dsp_value` as scratch: it belongs to the music only.
    rep #$20
.a16
    lda f:MSU_BASE
    sta f:MSU_FACTOR            ; the loop adds it with `adc f:`: there is
    sep #$20                    ; nowhere to keep a partial, and no `,s` here
.a8
    lda bgm_level + 1
    sta dsp_value
    ldx #8
    rep #$20
.a16
    lda #0
level_bit:
    asl a
    sep #$20
.a8
    asl dsp_value               ; sep and rep do not touch carry
    rep #$20
.a16
    bcc no_add
    clc
    adc f:MSU_FACTOR
no_add:
    dex
    bne level_bit
    xba                         ; the product's high byte, that is, over 256
    sep #$20
.a8
    sta MSU_VOLUME
    cmp #0
    bne ready_msu
    jsr msu_stop                ; reached zero: the track is cut
ready_msu:
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
; FADE_N. Only the ones that changed since the previous frame are rewritten
; —the one scaled by FADE_BEFORE is what the DSP already has—: a
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
other_voice:
    lda f:MUS_VIEWS
    and voice_bit, y
    beq next                    ; did not play in this song: not sounding
    jsr volume_refresh
    inx
    jsr volume_refresh          ; VOL_R
    dex
next:
    rep #$21                    ; and carry at zero
.a16
    txa
    adc #$10
    tax
    sep #$20
.a8
    iny
    cpy #8
    bcc other_voice
    rts
.endproc

; A voice's volume register X, with what the stream wrote to it —MUS_SHADOW—
; times FADE_N, over 256, if that changed with respect to FADE_BEFORE.
; The product is done by the PPU's multiplier, which belongs to `irq_music`
; —see M7A—: signed, which is what a DSP volume is, and without waiting.
; Does not touch X or Y.
.proc volume_refresh
.a8
.i16
    lda f:MUS_SHADOW, x
    sta f:MUS_MPY_B
    rep #$20
.a16
    lda f:FADE_BEFORE
    jsr mpym
.a8
    jsr song_gain_scale
    pha                         ; what the DSP has
    lda f:MUS_SHADOW, x         ; again: the gain wrote over MUS_MPY_B
    sta f:MUS_MPY_B
    rep #$20
.a16
    lda f:FADE_N
    jsr mpym
.a8
    jsr song_gain_scale         ; what it should have
    cmp 1, s
    bne write
    ; Equal, unless the gain just changed: then what the DSP has is the
    ; previous gain's, and every voice is written. See `gain_refresh`.
    lda f:GAIN_DIRTY
    beq equal
    lda 1, s
write:
    jsr dsp_music
equal:
    pla
    rts
.endproc

; A: a voice volume the stream is about to write to the DSP, and X its
; register. Returns with it times FADE_N, over 256, if a fade is going on,
; and then times the song's gain. It is the same computation as
; `volume_refresh`, so what the music writes in the middle of a fade and what
; the fade rewrites afterwards match. Does not touch X, Y or V.
.proc volume_fade
.a8
.i16
    pha
    lda bgm_fade
    beq whole
    pla
    sta f:MUS_MPY_B
    rep #$20
.a16
    lda f:FADE_N
    jsr mpym
.a8
    pha
whole:
    pla
    ; falls through into song_gain_scale
.endproc

; A: a voice volume, and X its register: VOL_L if even, VOL_R if odd. Returns
; with it times that side's `SONG_GAIN`, over 256, which is the `PlayBGM`'s
; volume and balance; as written, it does not multiply. With the PPU's
; multiplier, like the fade. Does not touch X, Y or V.
.proc song_gain_scale
.a8
.i16
    pha
    lda f:SONG_SCALED
    beq as_written
    pla
    sta f:MUS_MPY_B
    txa
    lsr a                       ; the side, in carry
    rep #$20
.a16
    bcs right
    lda f:SONG_GAIN
    jmp mpym
right:
.a16
    lda f:SONG_GAIN + 2
    jmp mpym
as_written:
.a8
    pla
    rts
.endproc

; MUS_MPY_B —eight bits signed— times A16, over 256: what the PPU's
; multiplier leaves in MPYM. Returns with A at eight bits and its flags.
; Does not touch X or Y.
;
; **In mode 7 that multiplier is the matrix the screen is being drawn
; with**, and this lands on line `IRQ_LINE`, in the middle of it: writing
; M7A and M7B there would draw the rest of the frame with another matrix.
; So while a big picture zooms —BIG_M7, which the vblank sets when it puts
; mode 7 on screen— it multiplies by hand, with a table of squares, and
; only then. The factors are
; FADE_N and SONG_GAIN, at most 256, so the product of a byte fits in
; sixteen bits, and its two's complement has the same middle byte as the
; PPU's twenty-four.
.proc mpym
.a16
.i16
    pha                         ; the factor
    sep #$20
.a8
    lda f:BIG_FLAGS
    and #BIG_M7
    bne by_hand
    lda f:MUS_MPY_B
    sta M7B
    pla
    sta M7A
    pla
    sta M7A
    lda MPYM
    rts
by_hand:
    php                         ; the caller counts on V, and C costs the same
    phx
    lda f:MUS_MPY_B
    bpl positive
    eor #$FF
    inc a                       ; -128 is 128, unsigned
positive:
    rep #$20
.a16
    and #$00FF
    pha                         ; m; X, P and the factor above it
    ; m × f = q(m + f) − q(|f − m|), q(n) = n² / 4 rounded down: two
    ; lookups, because a loop of shifts and adds took longer than the music
    ; has before the vblank.
    clc
    adc 6, s
    asl a
    tax
    lda f:quarter_squares, x
    pha                         ; q(m + f), above m
    lda 8, s
    sec
    sbc 3, s
    bpl difference
    eor #$FFFF
    inc a
difference:
    asl a
    tax
    lda 1, s
    sec
    sbc f:quarter_squares, x
    sta 1, s                    ; the product
    sep #$20
.a8
    lda f:MUS_MPY_B
    rep #$20
.a16
    bpl sign                    ; the flags of the byte: `rep` leaves them
    lda 1, s
    eor #$FFFF
    inc a
    sta 1, s
sign:
    sep #$20
.a8
    lda 2, s                    ; the product's high byte: MPYM
    sta f:MUS_MPY_M
    rep #$20
.a16
    pla
    pla
    plx
    plp                         ; eight bits again, as `php` found it
.a8
    rep #$20                    ; and the factor: neither touches V nor C
.a16
    pla
    sep #$20
.a8
    lda f:MUS_MPY_M
    rts
.endproc

; `mpym`'s squares: n² / 4, rounded down, for n up to 128 + 256, the
; largest byte and the largest factor. In the far bank: bank 0 is full.
.pushseg
.segment "FAR"
quarter_squares:
.repeat 385, n
    .word n * n / 4
.endrepeat
.popseg

; The music when the ROM boots. `SONG_BOOT` is the song of the map the ROM
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
    ; on— and `load_game` already left it in `song_current` and
    ; `music_off`. Without this the save would start with the song of the
    ; ROM's starting map, which is the opening's and not the one of the place
    ; where the player saved.
    lda slot
    cmp #$FF
    beq from_map                ; no slot loaded: the map's song
    lda music_off
    bne muted                   ; saved at a moment without music
    lda song_current
    jmp music_start
from_map:
    lda #SONG_BOOT
    cmp #$FF
    bne plays
muted:
    lda #1
    sta music_off
    ; And the MSU-1 track, which `music_off` does not silence: coming from
    ; the title its track kept playing inside the game until the first
    ; `PlayBGM`, and a battle in between recorded it as the song to restore.
    ; `test_con_msu_la_pista_del_titulo_no_sigue_en_la_partida` catches it.
    jmp msu_stop
plays:
    jmp music_start
.endproc

; Advances the music pointer by one byte, returning in A what was already read.
;
; The pointer is 24 bits and the 65816 only increments 16 at a time: when they
; wrap, the bank goes up by hand. In ExHiROM the next bank follows from its
; $0000 —the packing only lets a stream cross between two banks that continue
; each other—; in LoROM it followed from $8000, and this set it. With the
; whole song plus the samples going past 64 KB, this is not theoretical: it is
; crossed for sure.
.proc advance
.a8
.i16
; The accumulator holds the byte the caller just read, so it has to be
; returned intact.
    inc music
    bne done
height:                         ; where `READ` continues when the low byte wrapped
    inc music + 1
    bne done                    ; if the high part did not wrap, done
    inc music + 2               ; it wrapped: to the next bank, at $0000
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
    jsr advance::height
ready:
.endmacro

; One frame of music. The stream is per note —see "the per-note format" in
; rm2k-snes/rm2k-snes-audio/src/stream.rs and the header of
; rm2k-snes/bytecode/src/music.rs— and here it is expanded into the DSP writes that
; `dsp_music` sends: exactly those of `writes` in stream.rs, frame by frame,
; and
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
    stz restart
    lda f:MUS_LOG_ON
    beq no_mark
    jsr log_frame
no_mark:
    rep #$20
.a16
    lda f:MUS_WAIT
    beq open
    dec a
    sta f:MUS_WAIT
    sep #$20
.a8
    rts

open:
.a16
    sep #$20
.a8
    lda f:MUS_PLAYING           ; clear the previous frame's key-on
    beq read
    lda #0
    sta f:MUS_PLAYING
    ldx #SE_KON
    jsr dsp_music

read:
    ; Every event comes through here, so this is where an `OP_REPEAT` counts
    ; them: MUS_LEFT is one more than what it has left, and reaching zero
    ; means the last one was already read. Outside one it is zero, and that
    ; is all an event pays: a load and a branch.
    lda f:MUS_LEFT
    beq plain
    dec a
    sta f:MUS_LEFT
    bne plain
    rep #$20                    ; the repeat is over: back after it
.a16
    lda f:MUS_BACK_TO
    sta music
    sep #$20
.a8
    lda f:MUS_BACK_TO + 2
    sta music + 2
plain:
    READ
    cmp #OP_WAIT_1
    bcs not_voice
    jmp from_voice
not_voice:
    cmp #OP_WAIT
    bcc wait_short
    beq wait_long
    cmp #OP_DSP
    beq raw
    cmp #OP_REPEAT
    bne no_repeat
    jmp ev_repeat
no_repeat:
    cmp #OP_SOUND_PAGE
    beq sound_page
    cmp #OP_INIT
    bne no_init
    jmp boot
no_init:
    cmp #OP_END
    bne mute                    ; an opcode that does not exist: go silent
                                ; rather than write anything to the DSP
    lda restart
    bne mute
    inc restart
    lda song_current            ; it ended: the same one, again from the top
    jsr music_start_done        ; inside the IRQ: no `sei` and no package
    bra read
mute:
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
    sta music_off
    rts

raw:
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
    bra read

wait_short:
    sec
    sbc #OP_WAIT_1 - 1          ; from 1 to ESPERA_CORTA
    rep #$20
.a16
    and #$00FF
    bra close
wait_long:
.a8
    lda [music]
    jsr advance
    xba
    lda [music]
    jsr advance
    xba                         ; 16-bit A: the two bytes, low first
    rep #$20
.a16
close:
    ; The frame closes: the voices that got a note are keyed on together.
    pha
    sep #$20
.a8
    lda f:MUS_KON
    beq no_kon
    sta f:MUS_PLAYING
    ldx #SE_KON
    jsr dsp_music
    lda #0
    sta f:MUS_KON
no_kon:
    rep #$20
.a16
    ; The `pla` leaves Z from the value it pulls, and that is on purpose: a
    ; zero-frame wait keys on and keeps reading in the same frame, without
    ; opening another.
    pla
    beq continues
    dec a
    sta f:MUS_WAIT
    sep #$20
.a8
    rts
continues:
.a16
    sep #$20
.a8
    jmp read

sound_page:
    ; The notes from here on name the song's sounds from page × 256 on: the
    ; song's base, as `music_start_done` leaves it, plus page × 1536 bytes.
    ; Only a song with more than 256 sounds says it. The table fits in one
    ; bank —see `emit.rs`—, so neither addition carries.
    READ
    rep #$21                    ; 16-bit A and carry at zero
.a16
    and #$00FF
    xba                         ; × 256
    sta f:MUS_T
    asl a
    adc f:MUS_T                 ; × 768
    asl a                       ; × 1536
    sta f:MUS_T
    lda song_current
    asl a
    tax
    lda f:song_sounds, x
    clc
    adc f:MUS_T
    sta f:MUS_BASE
    sep #$20
.a8
    jmp read

boot:
    ; The DSP setup: the same table the MSU-1 path uses, and after it KON and
    ; KOF at zero. See `boot_writes`.
    ldy #0
other_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_ready
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda dsp_init_val, y
    jsr dsp_music               ; does not touch Y
    iny
    bra other_init
init_ready:
    lda #0
    ldx #SE_KON
    jsr dsp_music
    lda #0
    ldx #SE_KOF
    jsr dsp_music
    jmp read

from_voice:
    ; The voice in the three low bits and the family in the ones above: see
    ; the header of music.rs. Y ends up with the voice's VOL_L register.
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
.assert OP_NOTE_V0 = 0, error, "music.rs: the families start at 0"
.assert OP_NOTE_VOL_V0 = OP_NOTE_V0 + 8, error, "music.rs: families out of order"
.assert OP_NOTE_PAN_V0 = OP_NOTE_VOL_V0 + 8, error, "music.rs: families out of order"
.assert OP_RELEASE_V0 = OP_NOTE_PAN_V0 + 8, error, "music.rs: families out of order"
.assert OP_RELEASE_GAIN_V0 = OP_RELEASE_V0 + 8, error, "music.rs: families out of order"
.assert OP_SET_VOL_V0 = OP_RELEASE_GAIN_V0 + 8, error, "music.rs: families out of order"
.assert OP_SET_PAN_V0 = OP_SET_VOL_V0 + 8, error, "music.rs: families out of order"
.assert OP_SET_PITCH_V0 = OP_SET_PAN_V0 + 8, error, "music.rs: families out of order"
.assert OP_WAIT_1 = OP_SET_PITCH_V0 + 8, error, "music.rs: the waits go after them"

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
    bvs write
    cmp f:MUS_SHADOW, x
    beq equal
write:
    sta f:MUS_SHADOW, x
    ; In the middle of a `FadeOutBGM`, the volume goes scaled: the shadow keeps
    ; the stream's, which is what the cache compares against and what
    ; `volume_refresh` derives each frame's from. VOL_L and VOL_R are the
    ; voice's first two registers.
    pha
    lda bgm_fade
    ora f:SONG_SCALED
    beq such_which
    txa
    and #$0E
    bne such_which
    pla
    jsr volume_fade
    bra send
such_which:
    pla
send:
    jsr dsp_music
equal:
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
    and f:MUS_VIEWS
    bne already
    lda f:MUS_BIT
    ora f:MUS_VIEWS
    sta f:MUS_VIEWS
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
    jsr mus_write               ; VOL_L
    iny
    pla
    jsr mus_write               ; VOL_R, the same one
    iny
    jmp note_sound
.endproc

.proc ev_note_pan
.a8
.i16
    jsr first_note
    READ
    jsr mus_write               ; VOL_L
    iny
    READ
    jsr mus_write               ; VOL_R
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
    lda f:music_sounds + k, x
    jsr mus_write
    iny
    .endrepeat
    lda f:music_sounds + 5, x
    tyx                         ; the voice's register 8, which is ENVX
    sta f:MUS_SHADOW + 1, x
    lda f:MUS_BIT
    ora f:MUS_KON
    sta f:MUS_KON
    jmp music_frame::read
.endproc

.proc ev_release_gain
.a8
.i16
    lda [music]
    jsr advance
release:
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
    bne with_gain
    lda f:MUS_BIT
    ora f:MUS_GAINS
    sta f:MUS_GAINS
    sep #$40                    ; the first one goes without looking at the cache
with_gain:
    pla
    jsr mus_write
    jmp music_frame::read
.endproc

.proc ev_release
.a8
.i16
    tyx
    lda f:MUS_SHADOW + 8, x     ; the GAIN of the voice's sound
    bra ev_release_gain::release
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
    jmp music_frame::read
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
    jmp music_frame::read
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
    jmp music_frame::read
.endproc

.proc ev_repeat
.a8
.i16
    ; `events` events from `back` bytes before the end of this one: the
    ; stream says again something it already said, as written. See "repeats"
    ; in stream.rs. It is one level —what it reads is never another repeat—,
    ; so a single return address is enough.
    ;
    ; The pointer goes back with a 24-bit subtraction: a stream is only split
    ; between two banks that continue each other —`.crossbank`—, so going
    ; back over the start of a bank lands at the end of the previous one, in
    ; the same stream.
    READ
    sta f:MUS_T
    READ
    sta f:MUS_T + 1
    READ
    inc a                       ; one more: see `read`
    sta f:MUS_LEFT
    lda music + 2
    sta f:MUS_BACK_TO + 2
    rep #$20
.a16
    lda music
    sta f:MUS_BACK_TO
    sec
    sbc f:MUS_T
    sta music
    sep #$20                    ; does not touch the borrow
.a8
    lda music + 2
    sbc #0
    sta music + 2
    jmp music_frame::read
.endproc

; The decoder state at zero, and the log off. At reset: far RAM starts with
; garbage.
.proc music_clear
.a8
.i16
    ldx #0
    lda #0
other:
    sta f:MUS_WAIT, x
    inx
    cpx #MUS_STATE_BYTES
    bcc other
    sta f:MUS_LOG_ON
    sta f:MUS_LOG_I
    sta f:MUS_LOG_I + 1
    jsl f:bgm_level_reset
    rts
.endproc
