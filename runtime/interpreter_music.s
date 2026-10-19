.segment "CODE"
.a8
.i16

; --- the interpreter: music and sound effects ------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `PlayBGM`. The first operand is the song's index in `Songs`, and the
; cartridge carries the ones that fit in ARAM: the first `SONG_TOTAL`. A higher
; index is a song that did not fit and does not play, which is what happened
; to all but one of them until 2026-09-06. See `plan` in rm2k-snes-audio's
; cartridge.rs. The other four are its level —volume, balance and tempo—,
; which go to `BGM_ASK` as they come: see bgm_level.s.
.proc op_bgm
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
    sep #$20
.a8
    pla
touch:
    cmp #SONG_TOTAL
    bcs other_song
    phy
    jsr music_play              ; the one playing goes on: see `song_playing`
    ply
other_song:
    jmp run_code::other

.endproc

; `MemorizeBGM` and `PlayMemorizedBGM`: only the entry point. The body is
; `remembered_song`, outside bank 0, and it returns with carry set and the song
; in A if it has to be played, which is the same thing a `PlayBGM` would do.
.proc op_memorized_bgm
    jsl f:remembered_song
    bcs touch
    jmp run_code::other
touch:
    jmp op_bgm::touch

.endproc

; `OP_INN`: only the entry, like `op_memorized_bgm`. The body is `inn_phase`,
; in inn.s, which returns with V set when the page has to end the frame here
; —the wait for the inn's music begins on the next one—, and with carry set
; and the song in A when the song before the inn goes back on, which is a
; `PlayBGM`.
.proc op_inn
    jsl f:inn_phase
    bvs wait
    bcs op_memorized_bgm::touch
    jmp run_code::other
wait:
    sty ev_cur
    rts

.endproc

; `FadeOutBGM`. The operand is how much the volume drops per frame; it is
; lowered by `bgm_fade_tick`, not here, and the page carries on in this same
; frame, which is what `CommandFadeOutBGM` does by returning true.
;
; With the song off nothing is started: the fade would write the volume of a
; song that is not playing, and on top of that leave it at zero for the
; `PlayBGM` that comes next.
;
; With an MSU-1 track playing, on the other hand, there is something to fade:
; `music_off` is 1 —the SPC700 is silent on purpose— and what drops is the
; MSU-1 volume. Without this exit, a `FadeOutBGM` did nothing and the track
; kept playing forever.
.proc op_fade_bgm
    lda f:MSU_PLAYING
    bne fade_step
    lda music_off
    bne fade_nothing
fade_step:
    php
    sei                         ; `irq_music` reads it: all at once or nothing
    lda [code_ptr], y
    sta bgm_step
    iny
    lda [code_ptr], y
    sta bgm_step + 1
    iny
    lda #$FF
    sta bgm_level               ; full volume, which is where it drops from
    sta bgm_level + 1
    lda #1
    sta bgm_fade
    plp
    jmp run_code::other
fade_nothing:
    iny
    iny
    jmp run_code::other

.endproc

; `OP_SOUND`: the index into `sound_table`. It stays pending and starts at the
; end of `music_tick`, after whatever the music writes in the frame.
.proc op_sound
    jsr sound_from_code
    jmp run_code::other

.endproc
