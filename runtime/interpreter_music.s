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
; cartridge.rs. The other six are its level —volume, balance, tempo and
; fade-in—, which `bgm_operands` copies to `BGM_ASK` and `BGM_ASK_FADE`
; outside bank 0: see bgm_level.s.
.proc op_bgm
    jsl f:bgm_operands          ; the song in A, and Y after the operands
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

; `FadeOutBGM`: only the entry. The body is `fade_bgm_start`, outside bank 0.
; The operand is how much the volume drops per frame; it is
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
    jsl f:fade_bgm_start        ; Y after the operand
    jmp run_code::other

.endproc

; `ChangeSystemBGM` of the battle or the victory: only the entry. The body is
; `system_bgm_set`, outside bank 0, which leaves Y after the operands.
.proc op_system_bgm
    jsl f:system_bgm_set
    jmp run_code::other

.endproc

; `OP_SOUND`: the index into `sound_table`. It stays pending and starts at the
; end of `music_tick`, after whatever the music writes in the frame.
.proc op_sound
    jsr sound_from_code
    jmp run_code::other

.endproc
