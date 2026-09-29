.segment "CODE"

; --- sound effects ----------------------------------------------------------------
;
; `PlaySound`, on two voices stolen from the music while they last: SE_VOZ
; and SE2_VOZ, the ones the music's voice allocation fills first with
; percussion (`VOCES_DE_EFECTOS` in snes_music.py). See `build_efectos`
; there. In RM2k sound effects add up —EasyRPG has 31 channels—, and with a
; single voice the opening's rain cut the thunder in half: measured, 73 of
; its 144 frames, and once 7. With MSU-1 and the SPC700 without music, voices
; 0 to 5 as well: see efectos_con_msu.s.
;
; Each voice's state lives in far RAM, because the direct page and the BSS
; are full. The second one's is SE2_DESPL higher up, with the same shape, so
; `sonido_tocar` picks the voice with an offset:
;
;   SE_CUADROS   how many frames the effect has left, two bytes
;   SE_PENDIENTE there is one pending start
;   SE_DEVOLVER  the voice has to be given back to the music this frame
;   SE_BAJAR     the KON trigger has to be lowered this frame
;   SE_NUEVO     the pending one: the sample, the pitch (two), the volume of
;                each side and the frames (two), seven bytes. After starting
;                it stays there, and that is how we know which sample is
;                playing
;   SE_SOMBRA    the last thing the music wrote to the voice's eight
;                registers: that is what it is given back with
;   SE_KOF_SOMBRA  the last thing the music wrote to KOF, one for both
;
; The music keeps writing to each voice while its effect plays: it is kept
; in the shadow and not sent, and its KON and KOF get the bits of the voices
; that have an effect removed (`se_mascara`).
;
; All of this runs inside `irq_musica`, so **it uses neither the WMADD
; window nor `temp`**: the interrupt lands at any point of the main code,
; and if that was walking far RAM or using `temp`, this would clobber it. It
; gets there with long addressing, which carries the bank in the
; instruction. The only thing the main code writes here is the pending one,
; in `sonido_tocar`, and it does so with interrupts disabled.
FAR_SE       = $30A0
SE_CUADROS   = $7E0000 + FAR_SE
SE_PENDIENTE = SE_CUADROS + 2
SE_DEVOLVER  = SE_CUADROS + 3
SE_BAJAR     = SE_CUADROS + 4
SE_NUEVO     = SE_CUADROS + 5
SE_SOMBRA    = $7E0000 + $30B0
SE_KOF_SOMBRA = SE_SOMBRA + 8
; The second voice, at $3D00: the far RAM map above ends at the battle,
; which does not go past $3CFF, and the next thing is `FAR_HAB`, at $6000. It
; uses $3D00 to $3D17.
SE2_DESPL    = $3D00 - FAR_SE
SE2_CUADROS  = SE_CUADROS + SE2_DESPL
SE2_PENDIENTE = SE_PENDIENTE + SE2_DESPL
SE2_DEVOLVER = SE_DEVOLVER + SE2_DESPL
SE2_BAJAR    = SE_BAJAR + SE2_DESPL
SE2_NUEVO    = SE_NUEVO + SE2_DESPL
SE2_SOMBRA   = SE_SOMBRA + SE2_DESPL
SE_BYTES     = 12               ; from SE_CUADROS to SE_NUEVO, inclusive
; SE_BIT and SE_REG —the voice's bit in KON and KOF, and its first
; register— and the second one's are emitted by snes_music.py together with
; SE_VOZ.
SE_KON     = $4C
SE_KOF     = $5C

; Z=0 if the voice has an effect playing, pending or being given back. Does
; not touch B.
.proc se_ocupada
.a8
.i16
    lda f:SE_CUADROS
    ora f:SE_CUADROS + 1
    ora f:SE_PENDIENTE
    ora f:SE_DEVOLVER
    rts
.endproc

.proc se2_ocupada
.a8
.i16
    lda f:SE2_CUADROS
    ora f:SE2_CUADROS + 1
    ora f:SE2_PENDIENTE
    ora f:SE2_DEVOLVER
    rts
.endproc

; A: the KON and KOF bits of the busy voices. Touches neither B nor X.
.proc se_mascara
.a8
.i16
    jsr se_ocupada
    beq sin_7                   ; A was left at zero
    lda #SE_BIT
sin_7:
    pha
    jsr se2_ocupada
    beq sin_6
    lda #SE2_BIT
sin_6:
    ora 1, s
    ora f:EX_OCUP               ; and those of voices 0 to 5: see efectos_con_msu.s
    sta 1, s
    pla                         ; Z from the whole mask
    rts
.endproc

; `dsp_par` and `se_kof_musica` for `efectos_con_msu.s`, which lives in bank
; 1 and cannot reach them with `jsr`.
.proc dsp_par_l
    jsr dsp_par
    rtl
.endproc

.proc se_kof_musica_l
    jsr se_kof_musica
    rtl
.endproc

; A: what the music left in KOF, without the bits of the busy voices.
.proc se_kof_musica
.a8
.i16
    jsr se_mascara
    eor #$FF
    and f:SE_KOF_SOMBRA
    rts
.endproc

; A pair to the DSP: X the register, A the value, and the wait for the
; SPC700's acknowledgment.
.proc dsp_par
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
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; One write from the music stream: X the register —sixteen bits, with the
; high part at zero—, A the value. If it belongs to an effect voice, it goes
; to its shadow, and if the voice has an effect it is not sent; KON and KOF
; go out without the bits of the busy voices. Touches neither Y nor V:
; `music_frame` keeps the voice's register in Y and in V whether the note is
; written without looking at the cache.
.proc dsp_musica
.a8
.i16
    xba                         ; B = the value
    lda f:MUS_BITACORA_SI
    beq sin_bitacora
    jsr bitacora
sin_bitacora:
    txa
    and #$F0
    cmp #SE_REG
    beq voz_7
    cmp #SE2_REG
    beq voz_6
    bra no_voz
voz_7:
    txa
    and #$0F
    cmp #8
    bcs no_voz                  ; ENVX and OUTX are never written
    ; The shadow is indexed with the whole register, which is already in X,
    ; and the value does not leave B. Until 2026-09-26 the index was built in
    ; A with a `sep #$10` / `tax`, which wiped the high part of Y; and before
    ; that, with a sixteen-bit `and #$000F` that wiped B, and since 854dba9
    ; (voice 7) and 8c9c182 (voice 6) every music write to the drum voices
    ; reached the DSP as zero. rom/pruebas/rpgmaker/test_bateria_suena.py
    ; catches it.
    xba
    sta f:SE_SOMBRA - SE_REG, x ; to the shadow
    xba                         ; B = the value, for `enviar`
    jsr se_ocupada
    beq enviar
    rts                         ; the voice belongs to the effect
voz_6:
    txa
    and #$0F
    cmp #8
    bcs no_voz
    xba                         ; as in voz_7
    sta f:SE2_SOMBRA - SE2_REG, x
    xba
    jsr se2_ocupada
    beq enviar
    rts
no_voz:
    ; Voices 0 to 5, if they have an effect —only with MSU-1, see
    ; efectos_con_msu.s—: what is written stays in MUS_SOMBRA and is not
    ; sent, and when the effect ends it is given back from there. With no
    ; effects on them, one `lda` and one branch: the table holds zero for
    ; everything that is not theirs.
    lda f:EX_OCUP
    beq no_extra
    and f:ex_bit_de_registro, x
    beq no_extra
    rts                         ; the voice belongs to the effect
no_extra:
    txa
    cmp #SE_KOF
    bne no_kof
    ; KOF: to the shadow always, and without the bits of the busy voices.
    xba
    sta f:SE_KOF_SOMBRA
    xba
    bra mascara
no_kof:
    cmp #SE_KON
    bne enviar
mascara:
    jsr se_mascara
    beq enviar
    eor #$FF
    pha                         ; the inverted mask
    xba
    and 1, s                    ; the value without those bits
    xba
    pla
enviar:
    xba                         ; A = the value, and X still holds the register
    jmp dsp_par
.endproc

; Records in MUS_BITACORA the pair `dsp_musica` is about to send: X the
; register, B the value. Does not touch X, Y, B or V.
.proc bitacora
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
    lda f:MUS_BITACORA_I
    tax
    sep #$20
.a8
    lda 1, s                    ; the register's low byte
    sta f:MUS_BITACORA, x
    lda 3, s                    ; the value
    sta f:MUS_BITACORA + 1, x
    rep #$20
.a16
    txa
    inc a
    inc a
    and #MUS_BITACORA_LARGO - 1
    sta f:MUS_BITACORA_I
    sep #$20
.a8
    plx
    pla
    xba                         ; B = the value, as it came
    rts
.endproc

; The mark each music frame starts with in the log.
.proc bitacora_cuadro
.a8
.i16
    lda #0
    xba
    ldx #MUS_BITACORA_MARCA
    jmp bitacora
.endproc

; Before the music, on every frame: lower the trigger an effect left, and
; give the music back its voice if the effect ended on the previous frame.
.macro SE_ANTES_VOZ bajar, devolver, sombra, reg
    .local sin_bajar, listo, registro
    lda f:bajar
    beq sin_bajar
    lda #0
    sta f:bajar
    ldx #SE_KON
    jsr dsp_par
sin_bajar:
    lda f:devolver
    beq listo
    lda #0
    sta f:devolver
    ; KOF as the music had it, except for the other voice if it still has
    ; its effect, and this one's eight registers.
    jsr se_kof_musica
    ldx #SE_KOF
    jsr dsp_par
    ldy #0
registro:
    tyx
    lda f:sombra, x
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
    jsr dsp_par
    iny
    cpy #8
    bcc registro
listo:
.endmacro

.proc se_antes
.a8
.i16
    SE_ANTES_VOZ SE_BAJAR, SE_DEVOLVER, SE_SOMBRA, SE_REG
    SE_ANTES_VOZ SE2_BAJAR, SE2_DEVOLVER, SE2_SOMBRA, SE2_REG
    jsl se_extras_antes         ; and voices 0 to 5: see efectos_con_msu.s
    rts
.endproc

; After the music, for one voice: start its pending one, or count down the
; one playing and turn it off when it ends. Leaves in A the voice's bit if it
; has to be triggered, or zero: `se_despues` does the trigger only once for
; both, because two KON writes in a row can land in the same DSP sample and
; the second erase the first.
.macro SE_DESPUES_VOZ cuadros, pendiente, devolver, bajar, nuevo, bit, reg
    .local arrancar, contar, nada, fin
    lda f:pendiente
    bne arrancar
    jmp contar
arrancar:
    ; KOF without the bits of the busy voices —this one included, since it
    ; is still pending—, which the music may have left set.
    jsr se_kof_musica
    ldx #SE_KOF
    jsr dsp_par
    lda #0
    sta f:pendiente             ; no longer pending
    ; The sample, the pitch, the volume and the envelope, from the pending one.
    lda f:nuevo + 4
    ldx #(reg + 1)
    jsr dsp_par                 ; VOLR
    lda f:nuevo + 3
    ldx #(reg + 0)
    jsr dsp_par                 ; VOLL
    lda f:nuevo + 2
    ldx #(reg + 3)
    jsr dsp_par                 ; pitch high
    lda f:nuevo + 1
    ldx #(reg + 2)
    jsr dsp_par                 ; and low
    lda f:nuevo
    ldx #(reg + 4)
    jsr dsp_par                 ; SRCN
    lda #$FF                    ; ADSR on, attack and decay at maximum
    ldx #(reg + 5)
    jsr dsp_par
    lda #$E0                    ; sustain at maximum and no release
    ldx #(reg + 6)
    jsr dsp_par
    rep #$20
.a16
    lda f:nuevo + 5
    sta f:cuadros
    sep #$20
.a8
    lda #1
    sta f:bajar                 ; the next frame lowers the trigger
    lda #bit
    bra fin
contar:
    rep #$20
.a16
    lda f:cuadros
    beq nada
    dec a
    sta f:cuadros
    bne nada
    sep #$20
.a8
    ; It ended: KOF with the voice's bit, and on the next frame the music
    ; gets it back. This one no longer counts as busy, so `se_kof_musica`
    ; leaves out only the other one.
    jsr se_kof_musica
    ora #bit
    ldx #SE_KOF
    jsr dsp_par
    lda #1
    sta f:devolver
    lda #0
    bra fin
.a16
nada:
    sep #$20
.a8
    lda #0
fin:
.endmacro

.proc se_despues
.a8
.i16
    SE_DESPUES_VOZ SE_CUADROS, SE_PENDIENTE, SE_DEVOLVER, SE_BAJAR, SE_NUEVO, SE_BIT, SE_REG
    pha
    SE_DESPUES_VOZ SE2_CUADROS, SE2_PENDIENTE, SE2_DEVOLVER, SE2_BAJAR, SE2_NUEVO, SE2_BIT, SE2_REG
    ora 1, s
    sta 1, s
    jsl se_extras_despues       ; those of voices 0 to 5, in the same trigger
    ora 1, s
    sta 1, s
    pla
    beq listo
    ldx #SE_KON
    jsr dsp_par                 ; and the trigger, for both together
listo:
    rts
.endproc

; The state at zero: nothing playing. On reset.
.proc se_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:SE_CUADROS, x
    sta f:SE2_CUADROS, x
    inx
    cpx #SE_BYTES
    bcc otro
    jsl se_extras_limpiar       ; and the efectos_con_msu.s part
    rts
.endproc

.proc sonido_de_codigo
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; the index
    iny
    iny
    phy
    jsr sonido_tocar            ; with a 16-bit A; returns with an 8-bit A
.a8
    ply
    rts
.endproc

; The effect whose index in `sonido_tabla` comes in a 16-bit A, or nothing
; if it is $FFFF. It was split from `sonido_de_codigo` when the battle
; started playing sound effects: its ones do not come from the bytecode but
; from the `BA_SE_*` constants the converter emits, so the index arrives in
; the accumulator.
;
; It enters with a 16-bit A and leaves with an 8-bit A, which is how it left
; it before. The data bank does not matter: everything it reads goes with
; `f:`.
.proc sonido_tocar
.a16
.i16
    cmp #$FFFF
    bne hay
    sep #$20
.a8
    rts
hay:
.a16
    phb
    pha                         ; the index, on the stack until `listo`:
                                ; efectos_con_msu.s needs it
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
    lda f:sonido_tabla, x
    cmp #$FF
    bne hay_efecto
    jmp listo         ; there is no effect
hay_efecto:
    ; And only if its sample is in ARAM: the map's package may not have
    ; uploaded it. See `paquete_cargar`.
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    plx
    cmp #0
    bne esta
    xba
    cmp #0
    bne esta
    jmp listo
esta:
    ; And that it is **its own**: the place is shared by effects from
    ; different packages —see `lugares_de_efectos` in snes_music.py—, and
    ; the one there is the one recorded in `FAR_EFECTO_EN`. Without this, an
    ; effect from another map —a common event's— would play with the
    ; neighbor's sample.
    lda f:sonido_tabla, x
    sec
    sbc #SE_PRIMERA
    bcc es_suyo                 ; not one of the effects' places
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; the place, from zero
    lda 3, s                    ; the index, behind X
    sta temp
    sep #$20
.a8
    lda f:FAR_EFECTO_EN, x
    ldx temp
    eor f:sonido_efecto, x      ; zero if it is its own
    plx
    cmp #0                      ; `plx`'s Z is X's, not the `eor`'s
    beq es_suyo
    jmp listo
es_suyo:
    ; No interrupts while copying: `irq_musica` reads the pending one, and
    ; one half written would start with one's sample and another's pitch.
    ; The interrupt is not lost, it is delayed until the `plp`.
    php
    sei
    ; The voice: Y ends up at 0 for SE_VOZ or at SE2_DESPL for the other.
    ; First the one already playing this same sample —the rain triggers again
    ; before ending, and this way it does not steal the other voice from the
    ; thunder—, then a free one, and otherwise the one that ends sooner. A
    ; pending one is not overwritten if the other one can be: nothing of it
    ; has played yet.
    ldy #0
    lda f:SE_NUEVO
    cmp f:sonido_tabla, x
    bne no_misma_7
    jsr se_ocupada
    bne elegida
no_misma_7:
    ldy #SE2_DESPL
    lda f:SE2_NUEVO
    cmp f:sonido_tabla, x
    bne no_misma_6
    jsr se2_ocupada
    bne elegida
no_misma_6:
    ; With MSU-1 and the SPC700 without music, voices 0 to 5: the one already
    ; playing this sample, and then, if 7 and 6 are not free, one of those.
    ; See efectos_con_msu.s. Without MSU-1 they take nothing.
    rep #$20
.a16
    lda 2, s                    ; the index, behind P
    jsl se_extra_misma
.a8
    bcs puesto
    ldy #0
    jsr se_ocupada
    beq elegida
    ldy #SE2_DESPL
    jsr se2_ocupada
    beq elegida
    rep #$20
.a16
    lda 2, s
    jsl se_extra_libre
.a8
    bcs puesto
    ldy #0
    lda f:SE2_PENDIENTE
    bne elegida
    lda f:SE_PENDIENTE
    bne la_6
    rep #$20
.a16
    lda f:SE_CUADROS
    cmp f:SE2_CUADROS
    sep #$20                    ; does not touch C
.a8
    bcc elegida
    beq elegida
la_6:
    ldy #SE2_DESPL
elegida:
    rep #$20
.a16
    tya
    clc
    adc #7
    sta temp                    ; where the copy ends
    sep #$20
.a8
copiar:
    lda f:sonido_tabla, x
    phx
    tyx
    sta f:SE_NUEVO, x
    plx
    inx
    iny
    cpy temp
    bcc copiar
    rep #$20
.a16
    tya
    sec
    sbc #7
    tax
    sep #$20
.a8
    lda #1
    sta f:SE_PENDIENTE, x
    ; With the `.msu` sound effects, the pitch is that of its version in the
    ; package that is in ARAM.
    rep #$20
.a16
    lda 2, s
    jsl se_msu_altura_poner
.a8
puesto:
    plp
listo:
    rep #$20
.a16
    pla                         ; the index: with A and not with Y, which the
                                ; no-effect path returned as it came
    sep #$20
.a8
    plb
    rts
.endproc

