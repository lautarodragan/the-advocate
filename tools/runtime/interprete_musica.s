.segment "CODE"
.a8
.i16

; --- the interpreter: music and sound effects ------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps
; to each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.

; `PlayBGM`. The operand is the song's index in `Temas`, and the cartridge
; carries the ones that fit in ARAM: the first `TEMA_TOTAL`. A higher index is
; a song that did not fit and does not play, which is what happened to all but
; one of them until 2026-09-06. See `temas_de_la_rom` in the converter.
.proc op_bgm
    lda [cod_ptr], y
    iny
tocar:
    cmp #TEMA_TOTAL
    bcs otro_tema
    phy
    jsr music_start
    ply
otro_tema:
    jmp run_code::otro

.endproc

; `MemorizeBGM` and `PlayMemorizedBGM`: only the entry point. The body is
; `remembered_song`, outside bank 0, and it returns with carry set and the song
; in A if it has to be played, which is the same thing a `PlayBGM` would do.
.proc op_memorized_bgm
    jsl f:remembered_song
    bcs tocar
    jmp run_code::otro
tocar:
    jmp op_bgm::tocar

.endproc

; `FadeOutBGM`. The operand is how much the volume drops per frame; it is
; lowered by `bgm_fundido_tick`, not here, and the page carries on in this same
; frame, which is what `CommandFadeOutBGM` does by returning true.
;
; With the song off nothing is started: the fade would write the volume of a
; song that is not playing, and on top of that leave it at zero for the
; `PlayBGM` that comes next.
;
; With an MSU-1 track playing, on the other hand, there is something to fade:
; `music_apagada` is 1 —the SPC700 is silent on purpose— and what drops is the
; MSU-1 volume. Without this exit, a `FadeOutBGM` did nothing and the track
; kept playing forever.
.proc op_fade_bgm
    lda f:MSU_SUENA
    bne fundir
    lda music_apagada
    bne fundir_nada
fundir:
    php
    sei                         ; `irq_musica` reads it: all at once or nothing
    lda [cod_ptr], y
    sta bgm_paso
    iny
    lda [cod_ptr], y
    sta bgm_paso + 1
    iny
    lda #$FF
    sta bgm_nivel               ; full volume, which is where it drops from
    sta bgm_nivel + 1
    lda #1
    sta bgm_fundido
    plp
    jmp run_code::otro
fundir_nada:
    iny
    iny
    jmp run_code::otro

.endproc

; `OP_SOUND`: the index into `sonido_tabla`. It stays pending and starts at the
; end of `music_tick`, after whatever the music writes in the frame.
.proc op_sound
    jsr sonido_de_codigo
    jmp run_code::otro

.endproc
