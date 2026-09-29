.segment "CODE"

; --- sound effects ----------------------------------------------------------------
;
; `PlaySound`, on two voices stolen from the music while they last: SE_VOICE
; and SE2_VOZ, the ones the music's voice allocation fills first with
; percussion (`EFFECT_VOICES` in snes_music.py). See `build_sound_effects`
; there. In RM2k sound effects add up —EasyRPG has 31 channels—, and with a
; single voice the opening's rain cut the thunder in half: measured, 73 of
; its 144 frames, and once 7. With MSU-1 and the SPC700 without music, voices
; 0 to 5 as well: see msu_effects.s.
;
; Each voice's state lives in far RAM, because the direct page and the BSS
; are full. The second one's is SE2_OFS higher up, with the same shape, so
; `sound_play` picks the voice with an offset:
;
;   SE_FRAMES   how many frames the effect has left, two bytes
;   SE_PENDING there is one pending start
;   SE_RETURN  the voice has to be given back to the music this frame
;   SE_LOWER     the KON trigger has to be lowered this frame
;   SE_NEW     the pending one: the sample, the pitch (two), the volume of
;                each side and the frames (two), seven bytes. After starting
;                it stays there, and that is how we know which sample is
;                playing
;   SE_SHADOW    the last thing the music wrote to the voice's eight
;                registers: that is what it is given back with
;   SE_KOF_SHADOW  the last thing the music wrote to KOF, one for both
;
; The music keeps writing to each voice while its effect plays: it is kept
; in the shadow and not sent, and its KON and KOF get the bits of the voices
; that have an effect removed (`se_mask`).
;
; All of this runs inside `irq_music`, so **it uses neither the WMADD
; window nor `temp`**: the interrupt lands at any point of the main code,
; and if that was walking far RAM or using `temp`, this would clobber it. It
; gets there with long addressing, which carries the bank in the
; instruction. The only thing the main code writes here is the pending one,
; in `sound_play`, and it does so with interrupts disabled.
FAR_SE       = $30A0
SE_FRAMES    = $7E0000 + FAR_SE
SE_PENDING = SE_FRAMES + 2
SE_RETURN    = SE_FRAMES + 3
SE_LOWER     = SE_FRAMES + 4
SE_NEW       = SE_FRAMES + 5
SE_SHADOW    = $7E0000 + $30B0
SE_KOF_SHADOW = SE_SHADOW + 8
; The second voice, at $3D00: the far RAM map above ends at the battle,
; which does not go past $3CFF, and the next thing is `FAR_SKILL`, at $6000. It
; uses $3D00 to $3D17.
SE2_OFS      = $3D00 - FAR_SE
SE2_FRAMES   = SE_FRAMES + SE2_OFS
SE2_PENDING = SE_PENDING + SE2_OFS
SE2_RETURN = SE_RETURN + SE2_OFS
SE2_LOWER    = SE_LOWER + SE2_OFS
SE2_NEW      = SE_NEW + SE2_OFS
SE2_SHADOW   = SE_SHADOW + SE2_OFS
SE_BYTES     = 12               ; from SE_FRAMES to SE_NEW, inclusive
; SE_BIT and SE_REG —the voice's bit in KON and KOF, and its first
; register— and the second one's are emitted by snes_music.py together with
; SE_VOICE.
SE_KON     = $4C
SE_KOF     = $5C

; Z=0 if the voice has an effect playing, pending or being given back. Does
; not touch B.
.proc se_busy
.a8
.i16
    lda f:SE_FRAMES
    ora f:SE_FRAMES + 1
    ora f:SE_PENDING
    ora f:SE_RETURN
    rts
.endproc

.proc se2_busy
.a8
.i16
    lda f:SE2_FRAMES
    ora f:SE2_FRAMES + 1
    ora f:SE2_PENDING
    ora f:SE2_RETURN
    rts
.endproc

; A: the KON and KOF bits of the busy voices. Touches neither B nor X.
.proc se_mask
.a8
.i16
    jsr se_busy
    beq no_7                    ; A was left at zero
    lda #SE_BIT
no_7:
    pha
    jsr se2_busy
    beq no_6
    lda #SE2_BIT
no_6:
    ora 1, s
    ora f:EX_BUSY               ; and those of voices 0 to 5: see msu_effects.s
    sta 1, s
    pla                         ; Z from the whole mask
    rts
.endproc

; `dsp_pair` and `se_kof_music` for `msu_effects.s`, which lives in bank
; 1 and cannot reach them with `jsr`.
.proc dsp_pair_l
    jsr dsp_pair
    rtl
.endproc

.proc se_kof_music_l
    jsr se_kof_music
    rtl
.endproc

; A: what the music left in KOF, without the bits of the busy voices.
.proc se_kof_music
.a8
.i16
    jsr se_mask
    eor #$FF
    and f:SE_KOF_SHADOW
    rts
.endproc

; A pair to the DSP: X the register, A the value, and the wait for the
; SPC700's acknowledgment.
.proc dsp_pair
.a8
.i16
    xba
    txa
    sta APUIO0
    xba
    sta APUIO1
    inc token
    lda token
    sta APUIO3
wait:
    cmp APUIO3
    bne wait
    rts
.endproc

; One write from the music stream: X the register —sixteen bits, with the
; high part at zero—, A the value. If it belongs to an effect voice, it goes
; to its shadow, and if the voice has an effect it is not sent; KON and KOF
; go out without the bits of the busy voices. Touches neither Y nor V:
; `music_frame` keeps the voice's register in Y and in V whether the note is
; written without looking at the cache.
.proc dsp_music
.a8
.i16
    xba                         ; B = the value
    lda f:MUS_LOG_YES
    beq no_log
    jsr log
no_log:
    txa
    and #$F0
    cmp #SE_REG
    beq voice_7
    cmp #SE2_REG
    beq voice_6
    bra no_voice
voice_7:
    txa
    and #$0F
    cmp #8
    bcs no_voice                ; ENVX and OUTX are never written
    ; The shadow is indexed with the whole register, which is already in X,
    ; and the value does not leave B. Until 2026-09-26 the index was built in
    ; A with a `sep #$10` / `tax`, which wiped the high part of Y; and before
    ; that, with a sixteen-bit `and #$000F` that wiped B, and since 854dba9
    ; (voice 7) and 8c9c182 (voice 6) every music write to the drum voices
    ; reached the DSP as zero. rom/pruebas/rpgmaker/test_bateria_suena.py
    ; catches it.
    xba
    sta f:SE_SHADOW - SE_REG, x ; to the shadow
    xba                         ; B = the value, for `send`
    jsr se_busy
    beq send
    rts                         ; the voice belongs to the effect
voice_6:
    txa
    and #$0F
    cmp #8
    bcs no_voice
    xba                         ; as in voice_7
    sta f:SE2_SHADOW - SE2_REG, x
    xba
    jsr se2_busy
    beq send
    rts
no_voice:
    ; Voices 0 to 5, if they have an effect —only with MSU-1, see
    ; msu_effects.s—: what is written stays in MUS_SHADOW and is not
    ; sent, and when the effect ends it is given back from there. With no
    ; effects on them, one `lda` and one branch: the table holds zero for
    ; everything that is not theirs.
    lda f:EX_BUSY
    beq no_extra
    and f:ex_register_bit, x
    beq no_extra
    rts                         ; the voice belongs to the effect
no_extra:
    txa
    cmp #SE_KOF
    bne no_kof
    ; KOF: to the shadow always, and without the bits of the busy voices.
    xba
    sta f:SE_KOF_SHADOW
    xba
    bra mask
no_kof:
    cmp #SE_KON
    bne send
mask:
    jsr se_mask
    beq send
    eor #$FF
    pha                         ; the inverted mask
    xba
    and 1, s                    ; the value without those bits
    xba
    pla
send:
    xba                         ; A = the value, and X still holds the register
    jmp dsp_pair
.endproc

; Records in MUS_LOG the pair `dsp_music` is about to send: X the
; register, B the value. Does not touch X, Y, B or V.
.proc log
.a8
.i16
    xba
    pha                         ; the value
    phx                         ; the register, two bytes
    ; **First the pair and then the index**: the test reads the log between
    ; two emulator frames, and a heavy music frame is still running when the
    ; emulator delivers its own. With the index first, a cut right in the
    ; middle showed it a new pair with the bytes of the previous round
    ; —it happened on 2026-09-26 with the battle one, when the code shifted—.
    rep #$20
.a16
    lda f:MUS_LOG_I
    tax
    sep #$20
.a8
    lda 1, s                    ; the register's low byte
    sta f:MUS_LOG, x
    lda 3, s                    ; the value
    sta f:MUS_LOG + 1, x
    rep #$20
.a16
    txa
    inc a
    inc a
    and #MUS_LOG_LENGTH - 1
    sta f:MUS_LOG_I
    sep #$20
.a8
    plx
    pla
    xba                         ; B = the value, as it came
    rts
.endproc

; The mark each music frame starts with in the log.
.proc log_frame
.a8
.i16
    lda #0
    xba
    ldx #MUS_LOG_MARK
    jmp log
.endproc

; Before the music, on every frame: lower the trigger an effect left, and
; give the music back its voice if the effect ended on the previous frame.
.macro SE_BEFORE_VOICE lower, return, shadow, reg
    .local no_lower, ready, register
    lda f:lower
    beq no_lower
    lda #0
    sta f:lower
    ldx #SE_KON
    jsr dsp_pair
no_lower:
    lda f:return
    beq ready
    lda #0
    sta f:return
    ; KOF as the music had it, except for the other voice if it still has
    ; its effect, and this one's eight registers.
    jsr se_kof_music
    ldx #SE_KOF
    jsr dsp_pair
    ldy #0
register:
    tyx
    lda f:shadow, x
    pha
    rep #$20
.a16
    tya
    clc
    adc #reg
    tax
    sep #$20
.a8
    pla
    jsr dsp_pair
    iny
    cpy #8
    bcc register
ready:
.endmacro

.proc se_before
.a8
.i16
    SE_BEFORE_VOICE SE_LOWER, SE_RETURN, SE_SHADOW, SE_REG
    SE_BEFORE_VOICE SE2_LOWER, SE2_RETURN, SE2_SHADOW, SE2_REG
    jsl se_extras_before        ; and voices 0 to 5: see msu_effects.s
    rts
.endproc

; After the music, for one voice: start its pending one, or count down the
; one playing and turn it off when it ends. Leaves in A the voice's bit if it
; has to be triggered, or zero: `se_after` does the trigger only once for
; both, because two KON writes in a row can land in the same DSP sample and
; the second erase the first.
.macro SE_AFTER_VOICE frames, pending, return, lower, new, bit, reg
    .local start, count_up, nothing, end
    lda f:pending
    bne start
    jmp count_up
start:
    ; KOF without the bits of the busy voices —this one included, since it
    ; is still pending—, which the music may have left set.
    jsr se_kof_music
    ldx #SE_KOF
    jsr dsp_pair
    lda #0
    sta f:pending               ; no longer pending
    ; The sample, the pitch, the volume and the envelope, from the pending one.
    lda f:new + 4
    ldx #(reg + 1)
    jsr dsp_pair                ; VOLR
    lda f:new + 3
    ldx #(reg + 0)
    jsr dsp_pair                ; VOLL
    lda f:new + 2
    ldx #(reg + 3)
    jsr dsp_pair                ; pitch high
    lda f:new + 1
    ldx #(reg + 2)
    jsr dsp_pair                ; and low
    lda f:new
    ldx #(reg + 4)
    jsr dsp_pair                ; SRCN
    lda #$FF                    ; ADSR on, attack and decay at maximum
    ldx #(reg + 5)
    jsr dsp_pair
    lda #$E0                    ; sustain at maximum and no release
    ldx #(reg + 6)
    jsr dsp_pair
    rep #$20
.a16
    lda f:new + 5
    sta f:frames
    sep #$20
.a8
    lda #1
    sta f:lower                 ; the next frame lowers the trigger
    lda #bit
    bra end
count_up:
    rep #$20
.a16
    lda f:frames
    beq nothing
    dec a
    sta f:frames
    bne nothing
    sep #$20
.a8
    ; It ended: KOF with the voice's bit, and on the next frame the music
    ; gets it back. This one no longer counts as busy, so `se_kof_music`
    ; leaves out only the other one.
    jsr se_kof_music
    ora #bit
    ldx #SE_KOF
    jsr dsp_pair
    lda #1
    sta f:return
    lda #0
    bra end
.a16
nothing:
    sep #$20
.a8
    lda #0
end:
.endmacro

.proc se_after
.a8
.i16
    SE_AFTER_VOICE SE_FRAMES, SE_PENDING, SE_RETURN, SE_LOWER, SE_NEW, SE_BIT, SE_REG
    pha
    SE_AFTER_VOICE SE2_FRAMES, SE2_PENDING, SE2_RETURN, SE2_LOWER, SE2_NEW, SE2_BIT, SE2_REG
    ora 1, s
    sta 1, s
    jsl se_extras_after         ; those of voices 0 to 5, in the same trigger
    ora 1, s
    sta 1, s
    pla
    beq ready
    ldx #SE_KON
    jsr dsp_pair                ; and the trigger, for both together
ready:
    rts
.endproc

; The state at zero: nothing playing. On reset.
.proc se_clear
.a8
.i16
    ldx #0
    lda #0
other:
    sta f:SE_FRAMES, x
    sta f:SE2_FRAMES, x
    inx
    cpx #SE_BYTES
    bcc other
    jsl se_extras_clear         ; and the msu_effects.s part
    rts
.endproc

.proc sound_from_code
.a8
.i16
    rep #$20
.a16
    lda [code_ptr], y           ; the index
    iny
    iny
    phy
    jsr sound_play              ; with a 16-bit A; returns with an 8-bit A
.a8
    ply
    rts
.endproc

; The effect whose index in `sound_table` comes in a 16-bit A, or nothing
; if it is $FFFF. It was split from `sound_from_code` when the battle
; started playing sound effects: its ones do not come from the bytecode but
; from the `BA_SE_*` constants the converter emits, so the index arrives in
; the accumulator.
;
; It enters with a 16-bit A and leaves with an 8-bit A, which is how it left
; it before. The data bank does not matter: everything it reads goes with
; `f:`.
.proc sound_play
.a16
.i16
    cmp #$FFFF
    bne has
    sep #$20
.a8
    rts
has:
.a16
    phb
    pha                         ; the index, on the stack until `ready`:
                                ; msu_effects.s needs it
    sep #$20
.a8
    phk
    plb                         ; the table lives in the code's bank
    rep #$20
.a16
    lda 1, s
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp                    ; times seven
    tax
    sep #$20
.a8
    lda f:sound_table, x
    cmp #$FF
    bne has_effect
    jmp ready         ; there is no effect
has_effect:
    ; And only if its sample is in ARAM: the map's package may not have
    ; uploaded it. See `package_load`.
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_OF, x
    sep #$20
.a8
    plx
    cmp #0
    bne is
    xba
    cmp #0
    bne is
    jmp ready
is:
    ; And that it is **its own**: the place is shared by effects from
    ; different packages —see `effect_places` in snes_music.py—, and
    ; the one there is the one recorded in `FAR_EFFECT_IN`. Without this, an
    ; effect from another map —a common event's— would play with the
    ; neighbor's sample.
    lda f:sound_table, x
    sec
    sbc #SE_FIRST
    bcc is_own                  ; not one of the effects' places
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; the place, from zero
    lda 3, s                    ; the index, behind X
    sta temp
    sep #$20
.a8
    lda f:FAR_EFFECT_IN, x
    ldx temp
    eor f:sound_effect, x       ; zero if it is its own
    plx
    cmp #0                      ; `plx`'s Z is X's, not the `eor`'s
    beq is_own
    jmp ready
is_own:
    ; No interrupts while copying: `irq_music` reads the pending one, and
    ; one half written would start with one's sample and another's pitch.
    ; The interrupt is not lost, it is delayed until the `plp`.
    php
    sei
    ; The voice: Y ends up at 0 for SE_VOICE or at SE2_OFS for the other.
    ; First the one already playing this same sample —the rain triggers again
    ; before ending, and this way it does not steal the other voice from the
    ; thunder—, then a free one, and otherwise the one that ends sooner. A
    ; pending one is not overwritten if the other one can be: nothing of it
    ; has played yet.
    ldy #0
    lda f:SE_NEW
    cmp f:sound_table, x
    bne no_same_7
    jsr se_busy
    bne chosen
no_same_7:
    ldy #SE2_OFS
    lda f:SE2_NEW
    cmp f:sound_table, x
    bne no_same_6
    jsr se2_busy
    bne chosen
no_same_6:
    ; With MSU-1 and the SPC700 without music, voices 0 to 5: the one already
    ; playing this sample, and then, if 7 and 6 are not free, one of those.
    ; See msu_effects.s. Without MSU-1 they take nothing.
    rep #$20
.a16
    lda 2, s                    ; the index, behind P
    jsl se_extra_same
.a8
    bcs set
    ldy #0
    jsr se_busy
    beq chosen
    ldy #SE2_OFS
    jsr se2_busy
    beq chosen
    rep #$20
.a16
    lda 2, s
    jsl se_extra_free
.a8
    bcs set
    ldy #0
    lda f:SE2_PENDING
    bne chosen
    lda f:SE_PENDING
    bne pick_6
    rep #$20
.a16
    lda f:SE_FRAMES
    cmp f:SE2_FRAMES
    sep #$20                    ; does not touch C
.a8
    bcc chosen
    beq chosen
pick_6:
    ldy #SE2_OFS
chosen:
    rep #$20
.a16
    tya
    clc
    adc #7
    sta temp                    ; where the copy ends
    sep #$20
.a8
copy:
    lda f:sound_table, x
    phx
    tyx
    sta f:SE_NEW, x
    plx
    inx
    iny
    cpy temp
    bcc copy
    rep #$20
.a16
    tya
    sec
    sbc #7
    tax
    sep #$20
.a8
    lda #1
    sta f:SE_PENDING, x
    ; With the `.msu` sound effects, the pitch is that of its version in the
    ; package that is in ARAM.
    rep #$20
.a16
    lda 2, s
    jsl se_msu_pitch_set
.a8
set:
    plp
ready:
    rep #$20
.a16
    pla                         ; the index: with A and not with Y, which the
                                ; no-effect path returned as it came
    sep #$20
.a8
    plb
    rts
.endproc

