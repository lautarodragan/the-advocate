.segment "FAR3"
.a8
.i16

; --- how loud and how fast the song plays -----------------------------------
;
; A `PlayBGM` asks for a song **and** a volume, a tempo, a balance and a
; fade-in, and until 2026-09-30 the ROM played every song as written. The
; level is four bytes —see `BGM_ASK` in far_ram.s— and the fade-in two more,
; `BGM_ASK_FADE`, which the tools already left in the console's units:
; `Level` in rm2k-snes-bytecode's level.rs is where what RM2k does with each
; is written down.
;
; **How to start a song at a level**, which is what the `PlayBGM`, the
; memorized song, the battle, a map's own song, the title and a loaded
; game do:
;
;   1. the four bytes in `BGM_ASK` and the fade-in's step in `BGM_ASK_FADE`
;      —zero is no fade—, or one of the procs below that fills them: the
;      battle's, the victory's, a map's, the one a save brought;
;   2. the song in A and `jsr music_play`, in bank 0: if it is already
;      playing only its level changes, as `Game_System::BgmPlay` does, and
;      otherwise it starts from the beginning at that level, fading in if
;      it was asked to. `music_start` starts it over even if it is
;      playing.
;
; `bgm_level_set` takes the fade-in out of `BGM_ASK_FADE` each time, so a
; caller that does not write it gets none. What plays —to put it back
; later, as the battle does with `BGM_BEFORE_BATTLE`— is `song_current`, or
; nothing if `music_off` is set and no MSU-1 track plays, and its level
; `BGM_NOW`. The Game Over and End Game screens play theirs as written,
; through `ba_t_bgm`.
;
; Without MSU-1 the gain scales each music voice's volume, which is
; `song_gain_scale`, and the step is how many music frames `music_tempo` runs
; per video frame. With MSU-1 the gain is the track's volume, and **the tempo
; is ignored**: a PCM track cannot change speed without changing pitch, and
; one track per tempo would be one more copy of each song that asks for one.
; Neither does the MSU-1 have a balance: it takes the louder side. The
; fade-in is `bgm_fade_tick` going up instead of down —`bgm_fade` at 2—,
; over the voices or over the track.
;
; All of it is outside bank 0 for space, like `remembered_song`, and in
; FAR3 —bank $C1—, where there is room.

.pushseg
.segment "FARBSS"
; The fade-in the next start asks for, as `OP_BGM` carries it, and the one
; `bgm_level_set` took from it for the start that follows: see
; `bgm_fade_in_start`.
BGM_ASK_FADE: .res 2
BGM_FADE_IN:  .res 2
; The songs `ChangeSystemBGM` gives the battle (first) and the victory, each
; the song —$FF silence— and the six bytes of its level: `SYS_SONG_BYTES`
; each, see far_ram.s. A new game starts with the database's, and they
; travel in the save, as RM2k's `Game_System` keeps them.
SYS_SONGS: .res 2 * 7
.popseg

; Reset: the song as written, nothing owed, nothing memorized, and the
; database's battle and victory songs. Far RAM starts with garbage, and a
; step of zero would leave the music stopped.
.proc bgm_level_reset
.a8
.i16
    jsl bgm_level_full
    php
    rep #$20
.a16
    lda #0
    sta f:TEMPO_ACC
    sta f:BGM_FADE_IN
    lda f:BGM_NOW
    sta f:BGM_REMEMBERED
    sta f:BGM_BEFORE_BATTLE
    lda f:BGM_NOW + 2
    sta f:BGM_REMEMBERED + 2
    sta f:BGM_BEFORE_BATTLE + 2
    lda #BA_SONG_GAINS
    sta f:SYS_SONGS + 1
    lda #BA_SONG_STEP
    sta f:SYS_SONGS + 3
    lda #BA_SONG_FADE
    sta f:SYS_SONGS + 5
    lda #BA_SONG_END_GAINS
    sta f:SYS_SONGS + SYS_SONG_BYTES + 1
    lda #BA_SONG_END_STEP
    sta f:SYS_SONGS + SYS_SONG_BYTES + 3
    lda #BA_SONG_END_FADE
    sta f:SYS_SONGS + SYS_SONG_BYTES + 5
    sep #$20
.a8
    lda #BA_SONG
    sta f:SYS_SONGS
    lda #BA_SONG_END
    sta f:SYS_SONGS + SYS_SONG_BYTES
    lda #0
    sta f:GAIN_DIRTY
    plp
    rtl
.endproc

; `bgm_level_whole`, and on to `bgm_level_set` without the MSU-1. Keeps A.
.proc bgm_level_full
.a8
.i16
    jsl bgm_level_whole
    clc
    jml bgm_level_set           ; its `rtl` returns to whoever called this one
.endproc

; `BGM_ASK` at the song as written, with no fade-in, and nothing else.
; Keeps A.
.proc bgm_level_whole
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda #$8080
    sta f:BGM_ASK
    lda #$0100
    sta f:BGM_ASK + 2
    lda #0
    sta f:BGM_ASK_FADE
    pla
    plp
    rtl
.endproc

; `BGM_ASK` becomes the level that plays. With C set the song is the one
; already playing —`music_play` asks `song_playing` first—, and then the
; MSU-1 track, if it is playing, changes volume right away; with C clear a
; song is about to start, and `msu_start` takes `MSU_BASE` itself. Keeps A
; and every register.
;
; The voices of a song that goes on are rewritten by `irq_music`, which is
; what `GAIN_DIRTY` asks for: their volume is the stream's times the gain,
; and the stream only says it again with the next note of each one. A song
; that is about to start has no voice playing yet, so the flag finds nothing
; to rewrite.
.proc bgm_level_set
.a8
.i16
    php
    sei                         ; `irq_music` reads all of it
    rep #$30
.a16
.i16
    pha
    phx
    lda f:BGM_ASK
    sta f:BGM_NOW
    lda f:BGM_ASK + 2
    sta f:BGM_NOW + 2
    lda f:BGM_ASK_FADE          ; the fade-in, for the start that follows
    sta f:BGM_FADE_IN
    lda #0
    sta f:BGM_ASK_FADE          ; and none for whoever does not ask again
    lda f:BGM_ASK
    and #$00FF
    asl a
    sta f:SONG_GAIN             ; from 128ths to the 256ths of the multiply
    lda f:BGM_ASK + 1
    and #$00FF
    asl a
    sta f:SONG_GAIN + 2
    ; The track's: MSU_VOLUME_MAX times the louder side, over 128. With the
    ; CPU's multiplier, which here is free: this is the main code, and
    ; `irq_music` does not use it.
    tax                         ; the right one, times two
    cmp f:SONG_GAIN
    bcs louder
    lda f:SONG_GAIN
    tax
louder:
    txa
    lsr a                       ; back to 128ths: at most 128, it fits
    sep #$20
.a8
    sta f:WRMPYA
    lda #MSU_VOLUME_MAX
    sta f:WRMPYB                ; the product takes eight cycles
    rep #$20
.a16
    nop
    nop
    nop
    lda f:RDMPYL
    asl a
    xba
    and #$00FF                  ; over 128
    sta f:MSU_BASE
    lda f:BGM_ASK
    cmp #$8080
    sep #$20
.a8
    beq whole                   ; `sep` does not touch Z
    lda #1
    bra scaled
whole:
    lda #0
scaled:
    sta f:SONG_SCALED
    lda #1
    sta f:GAIN_DIRTY
    ; C as it came in, from the P that `php` saved: under X and A.
    lda 5, s
    lsr a
    bcc ready
    lda f:MSU_PLAYING
    beq ready
    lda f:MSU_BASE
    sta f:MSU_VOLUME
ready:
    rep #$30
.a16
    plx
    pla
    plp
.a8
    rtl
.endproc

; Into a battle: the map's level is kept for the way back, and the battle's
; song comes with its level —the database's, or the last `ChangeSystemBGM`'s—
; in `BGM_ASK`, and goes first in the battle's package: see `battle_extra_l`,
; which the caller clears with `battle_extra_clear` once the package is up.
; Returns with the song in A: $FF is silence.
.proc bgm_level_battle_in
.a8
.i16
    php
    rep #$20
.a16
    lda f:BGM_NOW
    sta f:BGM_BEFORE_BATTLE
    lda f:BGM_NOW + 2
    sta f:BGM_BEFORE_BATTLE + 2
    plp
.a8
    phx
    ldx #0
    jsl system_song
    plx
    jml f:battle_extra_l        ; its `rtl` returns to whoever called this one
.endproc

; Winning: the victory's song and its level, the same way. Returns with the
; song in A.
.proc bgm_level_victory
.a8
.i16
    phx
    ldx #SYS_SONG_BYTES
    jsl system_song
    plx                         ; `plx` keeps A
    rtl
.endproc

; The system song at X in `SYS_SONGS`: its level to `BGM_ASK` and
; `BGM_ASK_FADE`, and the song in A.
.proc system_song
.a8
.i16
    php
    rep #$20
.a16
    lda f:SYS_SONGS + 1, x
    sta f:BGM_ASK
    lda f:SYS_SONGS + 3, x
    sta f:BGM_ASK + 2
    lda f:SYS_SONGS + 5, x
    sta f:BGM_ASK_FADE
    plp
.a8
    lda f:SYS_SONGS, x
    rtl
.endproc

; And out of it: the map's song comes back at the level it had. Keeps A.
.proc bgm_level_battle_out
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda f:BGM_BEFORE_BATTLE
    sta f:BGM_ASK
    lda f:BGM_BEFORE_BATTLE + 2
    sta f:BGM_ASK + 2
    pla
    plp
    rtl
.endproc

; `OP_FADE_BGM`'s body, Y on its operand, which it leaves Y after: see
; `op_fade_bgm` for why each case. A song that is fading in fades out from
; where it got to.
.proc fade_bgm_start
.a8
.i16
    lda f:MSU_PLAYING
    bne fade_step
    lda f:music_off
    bne nothing
fade_step:
    php
    sei                         ; `irq_music` reads it: all at once or nothing
    lda [code_ptr], y
    sta f:bgm_step
    iny
    lda [code_ptr], y
    sta f:bgm_step + 1
    iny
    lda f:bgm_fade
    cmp #2
    beq from_here               ; fading in: it drops from where it got to
    lda #$FF
    sta f:bgm_level             ; full volume, which is where it drops from
    sta f:bgm_level + 1
from_here:
    lda #1
    sta f:bgm_fade
    plp
    rtl
nothing:
    iny
    iny
    rtl
.endproc

; `OP_BGM`'s operands, Y on the first: the level to `BGM_ASK` and the
; fade-in to `BGM_ASK_FADE`, as they come, and the song in A. Leaves Y after
; them. Outside bank 0 for space, like the rest.
.proc bgm_operands
.a8
.i16
    lda [code_ptr], y
    iny
    pha
    rep #$20
.a16
    lda [code_ptr], y           ; left and right
    sta f:BGM_ASK
    iny
    iny
    lda [code_ptr], y           ; the step
    sta f:BGM_ASK + 2
    iny
    iny
    lda [code_ptr], y           ; the fade-in
    sta f:BGM_ASK_FADE
    iny
    iny
    sep #$20
.a8
    pla
    rtl
.endproc

; `OP_SYSTEM_BGM`: `ChangeSystemBGM` of the battle or the victory. Y on the
; slot; the song and its six bytes go to the slot's entry of `SYS_SONGS`,
; and Y is left after them. Nothing plays now: the next battle reads them.
.proc system_bgm_set
.a8
.i16
    lda [code_ptr], y           ; the slot: 0 the battle, 1 the victory
    iny
    cmp #0                      ; `iny` left Z of Y, not of the slot
    beq into
    lda #SYS_SONG_BYTES
into:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #SYS_SONG_BYTES
    sta f:SYS_COUNT
copy:
    lda [code_ptr], y           ; the song, then the level
    iny
    sta f:SYS_SONGS, x
    inx
    lda f:SYS_COUNT
    dec a
    sta f:SYS_COUNT
    bne copy
    rtl
.endproc
.pushseg
.segment "FARBSS"
SYS_COUNT: .res 1               ; `system_bgm_set`'s bytes left to copy
.popseg

; The level map X —the cartridge's index, sixteen bits— plays its own song
; at, which RM2k keeps in the map's properties: `map_song_level`, six bytes
; per map, to `BGM_ASK` and `BGM_ASK_FADE`. Keeps A and X.
.proc bgm_level_map
.a8
.i16
    php
    rep #$30
.a16
.i16
    pha
    phx
    txa
    asl a
    adc 1, s                    ; three times the map: `asl` left C at zero
    asl a                       ; and six
    tax
    lda f:map_song_level, x
    sta f:BGM_ASK
    lda f:map_song_level + 2, x
    sta f:BGM_ASK + 2
    lda f:map_song_level + 4, x
    sta f:BGM_ASK_FADE
    plx
    pla
    plp
    rtl
.endproc

; The title's song's level, which the music's stage emits from the
; database's `title_music`: to `BGM_ASK` and `BGM_ASK_FADE`. Keeps A.
.proc bgm_level_title
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda #SONG_TITLE_GAINS
    sta f:BGM_ASK
    lda #SONG_TITLE_STEP
    sta f:BGM_ASK + 2
    lda #SONG_TITLE_FADE
    sta f:BGM_ASK_FADE
    pla
    plp
    rtl
.endproc

; `bgm_level_map` of `map_current`: the map just entered, or the boot's.
; Keeps A and X.
.proc bgm_level_here
.a8
.i16
    php
    rep #$30
.a16
    pha
    phx
    lda f:map_current           ; long: whatever the data bank
    tax
    jsl bgm_level_map
    plx
    pla
    plp
.a8
    rtl
.endproc

; A map whose song is the one already playing: only its level changes, as
; `Game_System::BgmPlay` does with the same song —going from a map at 100
; to one at 70 with the same song lowers it—. X the map. Keeps A.
.proc bgm_level_map_on
.a8
.i16
    jsl bgm_level_map
    sec
    jml bgm_level_set           ; its `rtl` returns to whoever called this one
.endproc

; The level the loaded save was playing at —`BGM_NOW` travels in it—, to
; `BGM_ASK`: a save made in a map at 70 comes back at 70. No fade. Keeps A.
.proc bgm_level_saved
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda f:BGM_NOW
    sta f:BGM_ASK
    lda f:BGM_NOW + 2
    sta f:BGM_ASK + 2
    pla
    plp
    rtl
.endproc

; One frame of a fade-in, from `bgm_fade_tick` in `irq_music` —`bgm_fade` at
; 2—: the level goes up by the step, and `FADE_N` with it; at the top the
; fade ends, where the factor is 256 and the voices are what the stream
; says. It is `AudioDecoder::SetFade` from zero. `level_factor`'s arithmetic,
; which is in bank 0, written again here: the high byte plus one, zero at
; zero.
.proc bgm_fade_rise
.a8
.i16
    rep #$21                    ; and carry at zero
.a16
    lda f:bgm_level
    adc f:bgm_step
    bcc high                    ; still some to go
    lda #$FFFF
high:
    sta f:bgm_level
    beq factor                  ; zero is zero
    xba
    and #$00FF
    inc a
factor:
    sta f:FADE_N
    cmp #256
    sep #$20
.a8
    bne ready                   ; `sep` does not touch Z
    lda #0
    sta f:bgm_fade              ; at the top: the song plays at its level
ready:
    rtl
.endproc

; One frame of a fade over an MSU-1 track, from `bgm_fade_tick` in
; `irq_music`: the track's volume at the `PlayBGM`'s gain —`MSU_BASE`,
; MSU_VOLUME_MAX as written— times the level, over 256. Returns with C set
; if a fade-out reached zero and the track has to be cut, which
; `bgm_fade_tick` does in bank 0.
;
; **Not with the CPU's multiplier**: this runs in `irq_music`, and the main
; code uses it in thirty places —the divider shares the result register—;
; an interrupt between its write and its read would change its result. Not
; with the PPU's either, which is eight-bit signed and MSU_VOLUME_MAX does
; not fit. So by hand, one bit of the level at a time, with `dsp_value` as
; scratch: it belongs to the music only. It lived in `bgm_fade_tick` until
; 2026-10-19, and moved here when bank 0 ran short.
.proc bgm_fade_track
.a8
.i16
    rep #$20
.a16
    lda f:MSU_BASE
    sta f:MSU_FACTOR            ; the loop adds it with `adc f:`: there is
    sep #$20                    ; nowhere to keep a partial
.a8
    lda f:bgm_level + 1
    sta f:dsp_value
    ldx #8
    rep #$20
.a16
    lda #0
level_bit:
    asl a
    sep #$20
.a8
    pha
    lda f:dsp_value
    asl a                       ; the level's next bit, to carry
    sta f:dsp_value
    pla                         ; `pla` does not touch carry
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
    sta f:MSU_VOLUME
    cmp #0
    bne goes_on
    rep #$20
.a16
    lda f:bgm_level             ; a fade-in starts near zero too: only the
    sep #$20                    ; level at zero is the end of a fade-out
.a8
    bne goes_on                 ; `sep` does not touch Z
    sec
    rtl
goes_on:
    clc
    rtl
.endproc

; A song that just started: if `bgm_level_set` took a fade-in for it, the
; level goes up from zero by that step each frame —`bgm_fade` at 2, which
; `bgm_fade_tick` raises—, and otherwise no fade is left running. Called by
; `music_start_level` with interrupts off, after the stream or the track
; started; the voices' first notes come out at `FADE_N`, zero. Keeps every
; register.
;
; The fade is consumed here: `BGM_FADE_IN` back to zero, so a song that
; loops or comes back from a battle does not fade in again.
.proc bgm_fade_in_start
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda f:BGM_FADE_IN
    beq none
    sta f:bgm_step
    lda #0
    sta f:bgm_level
    sta f:FADE_N
    sta f:FADE_BEFORE
    sta f:BGM_FADE_IN
    sep #$20
.a8
    lda #2
    sta f:bgm_fade
    lda f:MSU_PLAYING
    beq ready
    lda #0
    sta f:MSU_VOLUME            ; `msu_start` left it at the level's, and the
    bra ready                   ; track started microseconds ago: inaudible
none:
.a16
    sep #$20
.a8
    lda #0
    sta f:bgm_fade
ready:
    rep #$20
.a16
    pla
    plp
    rtl
.endproc
