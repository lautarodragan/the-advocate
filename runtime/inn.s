; In `FAR3`, like the other bodies that came after bank 0 filled up: its
; door in is a `jsl`, and everything it reads goes with `f:`, so it runs
; whatever the data bank.
.segment "FAR3"
.a8
.i16

; --- the inn's staging --------------------------------------------------------
;
; `ShowInn` is RM2k's `Scene_Map::CallInn` once it has decided to stay: the
; song fades out over 800 ms while the screen goes to black, the System's inn
; music plays once —`BGM_PlayedOnce`, or ten seconds at most—, and the screen
; comes back with the party healed and the song that was playing before
; started again. The event compiler builds it out of what the page already
; does —`OP_FADE_BGM`, `OP_ERASE_SCREEN`, `OP_BGM`, `OP_HEAL`,
; `OP_SHOW_SCREEN`— and of the three phases of `OP_INN`, which are the two
; things a page cannot say: which song was playing, and waiting for a song
; to come round once. See `compile_inn` in rm2k-snes-events.
;
; The song before goes in a slot of its own, and not in `MemorizeBGM`'s: it
; is `music_before_inn`, apart from the game's `memorized_bgm`. "Playing" is
; what the battle asks —see `battle_start`—: a song that a fade already cut,
; or a map with none, leaves silence after the inn, not the last song.
;
; While the inn's music plays the world is frozen, as in RM2k, where
; `Scene_Map::vUpdate` only runs `UpdateInn`: `fade_tick` asks `inn_tick`
; each frame it has no fade of its own, and the frame goes as a fade's.

.pushseg
.segment "FARBSS"
INN_WAIT:   .res 1              ; 1 while the inn's music is waited for
INN_FRAMES: .res 2              ; how many frames it has left, at most
INN_LAPS:   .res 1              ; `SONG_LAPS` when it started
INN_SONG:   .res 1              ; the song before, or $FF for silence
INN_LEVEL:  .res 4              ; and its level, as `BGM_NOW` carries it
.popseg

; Ten seconds: `UpdateInn` gives up on a song that has not come round by
; then —`Game_Clock::GetFrameTime() - inn_timer < 10s`—, which a looping
; WAV would never do.
INN_LONGEST = 10 * 60

; MSU-1's `$2007`: playing, without the repeat bit. With it off the track
; ends by itself, and `MSU_STATE` says so.
MSU_PLAY_ONCE = $01
MSU_AUDIO_PLAYING = $10

; `OP_INN`, from `op_inn` with Y on the phase; it leaves Y after it. It
; returns three ways: V set if the page ends the frame here (phase 1), carry
; set with the song to put on in A (phase 2, which `op_inn` plays as a
; `PlayBGM`), and both clear to go on.
.proc inn_phase
.a8
.i16
    lda [code_ptr], y
    iny
    cmp #3
    bcc staging
    jmp inn_gold                ; 3 and 4, the inn's choice: see gold_window.s
staging:
    cmp #1
    beq wait
    bcs put
    ; 0: which song is playing, and at what level.
    lda f:MSU_PLAYING
    bne playing
    lda f:music_off
    bne silent
playing:
    lda f:song_current
    bra noted
silent:
    lda #$FF
noted:
    sta f:INN_SONG
    rep #$20
.a16
    lda f:BGM_NOW
    sta f:INN_LEVEL
    lda f:BGM_NOW + 2
    sta f:INN_LEVEL + 2
    sep #$20
.a8
    clv
    clc
    rtl

wait:
    ; 1: from the next frame the world waits for the song playing —the inn's,
    ; which the `OP_BGM` before this one put on— to come round once.
    lda #1
    sta f:INN_WAIT
    lda f:SONG_LAPS
    sta f:INN_LAPS
    rep #$20
.a16
    lda #INN_LONGEST
    sta f:INN_FRAMES
    sep #$20
.a8
    ; An MSU-1 track repeats from its loop point and never ends: this one is
    ; told to play once. Not if what plays is the song before, still fading
    ; —the inn's did not start—: `inn_tick` lets that one go at once.
    lda f:bgm_fade
    bne frame_ends
    lda f:MSU_PLAYING
    beq frame_ends
    lda #MSU_PLAY_ONCE
    sta f:MSU_CONTROL
frame_ends:
    sep #$40                    ; V: the frame ends here
    rtl

put:
    ; 2: the song before, from the top —`inn_tick` stopped the inn's—, at
    ; its level. With $FF `op_bgm` plays nothing, and the silence stays.
    rep #$20
.a16
    lda f:INN_LEVEL
    sta f:BGM_ASK
    lda f:INN_LEVEL + 2
    sta f:BGM_ASK + 2
    sep #$20
.a8
    lda f:INN_SONG
    clv
    sec
    rtl
.endproc

; From `fade_tick`, every frame without a fade: A at 1 and Z clear if the
; world stays frozen this frame, A at 0 and Z set if not. The frame the wait
; ends is not frozen: the page goes on in it, with the heal.
;
; The wait ends as `UpdateInn` does: when nothing plays —`BGM_IsPlaying`—,
; when the song has come round once, or after ten seconds. With nothing
; playing the song before is the one a fade is still cutting, and the inn's
; never started: the `OP_BGM` was a song the cartridge does not carry.
.proc inn_tick
.a8
.i16
    lda f:INN_WAIT
    bne waiting
    lda #0
    rtl
waiting:
    rep #$20
.a16
    lda f:INN_FRAMES
    dec a
    sta f:INN_FRAMES
    sep #$20                    ; `sep` keeps the Z of the `dec`
.a8
    beq done
    lda f:bgm_fade
    bne done                    ; the song before: the inn's did not start
    lda f:MSU_PLAYING
    beq spc
    lda f:MSU_STATE
    and #MSU_AUDIO_PLAYING
    beq done                    ; the track ended
    bra frozen
spc:
    lda f:music_off
    bne done
    lda f:SONG_LAPS
    cmp f:INN_LAPS
    bne done                    ; `music_frame` started it over: it came round
frozen:
    lda #1
    rtl
done:
    ; `BgmStop`: the MSU-1 and the SPC700, as `battle_bgm` silences them.
    lda #0
    sta f:INN_WAIT
    lda f:MSU_PLAYING
    beq no_track
    lda #0
    sta f:MSU_PLAYING
    sta f:MSU_CONTROL
no_track:
    php
    sei
    lda #1
    sta f:music_off
    lda #$FF
    ldx #SE_KOF
    jsl f:dsp_pair_l            ; the eight voices release
    plp
    lda #0
    rtl
.endproc
