.segment "FAR"
.a8
.i16

; --- how loud and how fast the song plays -----------------------------------
;
; A `PlayBGM` asks for a song **and** a volume, a tempo and a balance, and
; until 2026-09-30 the ROM played every song as written. The level is four
; bytes —see `BGM_ASK` in far_ram.s— that the event compiler already left in
; the console's units, `bgm_level` in its compile.rs: that is where what RM2k
; does with each of the three is written down.
;
; Whoever calls `music_play` leaves the level in `BGM_ASK` first: the
; `PlayBGM`, the memorized song, the battle. `music_start` —the title, a loaded
; game, a map's own song— plays the song as written.
;
; Without MSU-1 the gain scales each music voice's volume, which is
; `song_gain_scale`, and the step is how many music frames `music_tempo` runs
; per video frame. With MSU-1 the gain is the track's volume, and **the tempo
; is ignored**: a PCM track cannot change speed without changing pitch, and
; one track per tempo would be one more copy of each song that asks for one.
; Neither does the MSU-1 have a balance: it takes the louder side.
;
; All of it is outside bank 0 for space, like `remembered_song`.

; Reset: the song as written, nothing owed, nothing memorized. Far RAM starts
; with garbage, and a step of zero would leave the music stopped.
.proc bgm_level_reset
.a8
.i16
    jsl bgm_level_full
    php
    rep #$20
.a16
    lda #0
    sta f:TEMPO_ACC
    lda f:BGM_NOW
    sta f:BGM_REMEMBERED
    sta f:BGM_BEFORE_BATTLE
    lda f:BGM_NOW + 2
    sta f:BGM_REMEMBERED + 2
    sta f:BGM_BEFORE_BATTLE + 2
    sep #$20
.a8
    lda #0
    sta f:GAIN_DIRTY
    plp
    rtl
.endproc

; `BGM_ASK` at the song as written, and on to `bgm_level_set` without the
; MSU-1: it is what `music_start` does before starting a song. Keeps A.
.proc bgm_level_full
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
    pla
    plp
.a8
    clc
    ; falls through into bgm_level_set
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
; song plays as written —the LDB's battle music says 100, 100 and 50—.
; Keeps A.
.proc bgm_level_battle_in
.a8
.i16
    php
    rep #$20
.a16
    pha
    lda f:BGM_NOW
    sta f:BGM_BEFORE_BATTLE
    lda f:BGM_NOW + 2
    sta f:BGM_BEFORE_BATTLE + 2
    lda #$8080
    sta f:BGM_ASK
    lda #$0100
    sta f:BGM_ASK + 2
    pla
    plp
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
