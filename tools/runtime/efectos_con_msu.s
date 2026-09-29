.segment "FAR"

; --- sound effects with MSU-1 --------------------------------------------------
;
; With MSU-1 the song plays from its track and the SPC700 plays no music, so
; the sound effects can have what used to be the music's. There are two
; things, and **without MSU-1 neither of them does anything**: `MSU_HAS` at
; zero turns both off, and what is left is the usual —voices 7 and 6, the ROM's
; sound effects—.
;
; **Voices 0 to 5.** While the SPC700 plays no music —there is MSU-1 and
; `music_off` is set: a track plays, or nothing—, a sound effect that
; does not fit in 7 or in 6 takes one of those. In RM2k sound effects add up,
; and `evilrhys`'s scene on map 3 has a moment with three at once. Their state
; lives in `EX_*` (ram_lejana.s), smaller than that of 7 and 6: instead of the
; copy of the `sonido_tabla` row, its index, and the interrupt reads it when
; starting it.
;
; If a song starts playing through the SPC700 while a sound effect plays on
; one of those —a missing track, or a `PlayBGM` of a song with no track—,
; **the sound effect goes on**: what the music writes to that voice stays in
; MUS_SHADOW and is not sent (`dsp_music`), and when the sound effect ends it
; is given back from there (`se_extras_before`). It is the same as what happens
; with 7 and 6, only the shadow is the music's and not one of its own: there
; was no RAM for six more.
;
; **The quality sound effects from the `.msu`.** If the `.msu` is this
; cartridge's —the signature, `msu_data_valid`—, each package's sound effects
; are uploaded to ARAM from there and not from ROM: whole, and at the rate
; they fit at now that the music takes no room. Each package has its version of
; each sound effect —the rate depends on how heavy the package is, see
; tools/audio/efectos_msu.py— and the ROM does not keep which version was
; left in ARAM, so **on every package they are all uploaded again**, even if they
; were already there. Each sound's pitch comes from `se_msu_altura`, which the
; converter builds per package, and not from `sonido_tabla`. With another
; `.msu`, or without one, everything comes from ROM as always.
;
; It lives in bank 1 because bank 0 has no room: it is reached with `jsl`,
; and what is read or written goes with `f:`, so the data bank does not
; matter. What runs inside `irq_music` —`se_extras_before` and
; `se_extras_after`— does not use `temp`, for the same reason
; `efectos_de_sonido.s` does not.

EX_VOICES = 6                    ; from 0 to 5
.assert SE_BIT = $80 && SE2_BIT = $40, error, "the usual sound effect voices are no longer 7 and 6"

; The bit of each voice, and that of the voice of each DSP register: that of
; voices 0 to 5 on their registers 0 to 7 and zero on the rest, so that
; `dsp_music` asks with a single `and`.
ex_bit:
    .byte $01, $02, $04, $08, $10, $20
ex_register_bit:
.repeat 128, r
  .if (r >> 4) < EX_VOICES && (r & $0F) < 8
    .byte 1 << (r >> 4)
  .else
    .byte 0
  .endif
.endrepeat

; All at zero, on reset: far RAM starts with garbage on bsnes.
.proc se_extras_clear
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:EX_FRAMES, x
    inx
    cpx #(EX_END - EX_FRAMES)
    bcc otro
    rtl
.endproc

; C at 1 if voices 0 to 5 belong to the sound effects: there is MSU-1 and the
; SPC700 plays no music.
.proc ex_allowed
.a8
.i16
    lda f:MSU_HAS
    beq no
    lda f:music_off
    beq no
    sec
    rts
no:
    clc
    rts
.endproc

; The sample of the sound effect on the voice whose double X carries, in A.
; Clobbers X.
.proc ex_srcn
.a8
.i16
    rep #$20
.a16
    lda f:EX_IDX, x
    pha
    asl a
    asl a
    asl a
    sec
    sbc 1, s                    ; times seven
    tax
    pla
    sep #$20
.a8
    lda f:sonido_tabla, x
    rts
.endproc

; The sound effect of index A, sixteen bits, to voice Y. Returns with 8-bit A.
.proc ex_take
.a16
.i16
    pha
    tya
    asl a
    tax
    pla
    sta f:EX_IDX, x
    sep #$20
.a8
    tyx
    lda f:ex_bit, x
    pha
    ora f:EX_PEND
    sta f:EX_PEND
    lda 1, s
    ora f:EX_BUSY
    sta f:EX_BUSY
    ; If it was being given back, not anymore: it goes straight to the new
    ; sound effect.
    pla
    eor #$FF
    and f:EX_RETURN
    sta f:EX_RETURN
    rts
.endproc

; For `sound_play`, with interrupts disabled: if one of voices 0 to 5 is
; playing the same sample as the sound effect of index A —sixteen bits— and
; row X, it is given to that one, as 7 and 6 do with the rain. C at 1 if it
; took it. Returns with 8-bit A, and with X as it came.
.proc se_extra_same
.a16
.i16
    phx
    pha                         ; [index][row]
    sep #$20
.a8
    jsr ex_allowed
    bcc no
    lda f:sonido_tabla, x
    pha                         ; [srcn][index][row]
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_BUSY
    beq sigue
    rep #$20
.a16
    tya
    asl a
    tax
    sep #$20
.a8
    jsr ex_srcn
    cmp 1, s
    beq tomar
sigue:
    iny
    cpy #EX_VOICES
    bcc otra
    pla
no:
    rep #$20
.a16
    pla
    plx
    sep #$20
.a8
    clc
    rtl
tomar:
    pla
    rep #$20
.a16
    pla
    jsr ex_take
.a8
    plx
    sec
    rtl
.endproc

; And if 7 and 6 are busy, one of voices 0 to 5 that is free.
.proc se_extra_free
.a16
.i16
    phx
    pha
    sep #$20
.a8
    jsr ex_allowed
    bcc no
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_BUSY
    beq tomar
    iny
    cpy #EX_VOICES
    bcc otra
no:
    rep #$20
.a16
    pla
    plx
    sep #$20
.a8
    clc
    rtl
tomar:
    rep #$20
.a16
    pla
    jsr ex_take
.a8
    plx
    sec
    rtl
.endproc

; The pitch of the sound of index A —sixteen bits— with the `.msu` version of
; the package that is in ARAM, or 0 if its sound effect is not from that package. Z
; according to the pitch. Clobbers X.
;
; The package's list is (index, pitch) pairs sorted by index and terminated with
; $FFFF, only with the sounds whose sound effect is from there: see
; `escribir_msu` in tools/port/snes_convert.py. It is walked whole at most
; —a few dozen pairs—, and since they are sorted, it stops on going past; the
; $FFFF stops it too, because no index gets there.
.proc msu_pitch
.a16
.i16
    pha                         ; the index being searched for
    lda f:PKG_MAP
    asl a
    tax
    lda f:se_msu_altura_paq, x
    tax
buscar:
    lda f:se_msu_altura, x      ; the pair's index
    cmp 1, s
    beq esta
    bcs no_esta                 ; already went past: it is not from this package
    inx
    inx
    inx
    inx
    bra buscar
esta:
    pla
    ; The `lda` goes after the `pla`, which leaves Z from the index: the caller
    ; looks at Z of the pitch.
    lda f:se_msu_altura + 2, x
    rts
no_esta:
    pla
    lda #0
    rts
.endproc

; For `sound_play`, after copying the pending one of the voice whose offset
; X carries: with the `.msu` sound effects, the pitch of its version. A
; carries the index, sixteen bits. Returns with 8-bit A.
.proc se_msu_pitch_set
.a16
.i16
    phx
    pha                         ; [index][offset]
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    rep #$20
.a16
    bne ready
    lda 1, s
    jsr msu_pitch
    beq ready
    tay
    lda 3, s
    tax
    tya
    sta f:SE_NEW + 1, x       ; the low pitch and the high one
ready:
    pla
    plx
    sep #$20
.a8
    rtl
.endproc

; --- inside `irq_music` -------------------------------------------------------

; Before the music: the voices whose sound effect ended on the previous frame
; go back to it. KOF as the music had it, except whatever is still busy, and
; their eight registers from MUS_SHADOW, which is what the stream wrote to
; them in the meantime.
.proc se_extras_before
.a8
.i16
    lda f:EX_RETURN
    bne hay
    rtl
hay:
    eor #$FF
    and f:EX_BUSY
    sta f:EX_BUSY
    jsl se_kof_music_l
    ldx #SE_KOF
    jsl dsp_pair_l
    ldy #0
voz:
    tyx
    lda f:ex_bit, x
    and f:EX_RETURN
    beq sigue
    tya
    asl a
    asl a
    asl a
    asl a
    rep #$20
.a16
    and #$00FF
    tax                         ; its first register
    sep #$20
.a8
register:
    lda f:MUS_SHADOW, x
    jsl dsp_pair_l
    inx
    txa
    and #$07
    bne register
sigue:
    iny
    cpy #EX_VOICES
    bcc voz
    lda #0
    sta f:EX_RETURN
    rtl
.endproc

; After the music: start the pending ones, and count the ones playing and
; turn off the ones ending. Returns with A holding the bits of the voices to
; key on: `se_after` does the key-on, once for all of them.
;
; **A single KOF for the ones ending, and after the ones starting**: each KOF
; overwrites the previous one, and if two land before the DSP reads it, the
; first one never existed. The one starting writes the music's without the
; busy voices; if the one ending wrote first, its own would be lost, and a
; looping ROM sound effect would keep playing.
.proc se_extras_after
.a8
.i16
    lda f:EX_BUSY
    bne hay
    rtl                         ; A at zero: nothing to key on
hay:
    lda f:EX_PEND
    pha                         ; [the ones starting]
    beq contar_todas
    lda #0
    sta f:EX_PEND
    jsl se_kof_music_l
    ldx #SE_KOF
    jsl dsp_pair_l
    ldy #0
start:
    tyx
    lda f:ex_bit, x
    and 1, s
    beq no_arranca
    jsr ex_start
no_arranca:
    iny
    cpy #EX_VOICES
    bcc start
    lda #1
    sta f:SE_LOWER              ; the next frame the key-on is lowered
contar_todas:
    lda #0
    pha                         ; [the ones ending][the ones starting]
    ldy #0
count_up:
    tyx
    lda f:ex_bit, x
    and 2, s
    bne sigue                   ; just started: counted from the next one
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:EX_FRAMES, x
    beq nothing
    dec a
    sta f:EX_FRAMES, x
    bne nothing
    sep #$20
.a8
    tyx
    lda f:ex_bit, x
    ora 1, s
    sta 1, s
    bra sigue
.a16
nothing:
    sep #$20
.a8
sigue:
    iny
    cpy #EX_VOICES
    bcc count_up
    pla                         ; the ones ending
    beq ninguno
    pha
    ora f:EX_RETURN
    sta f:EX_RETURN
    jsl se_kof_music_l
    ora 1, s
    ldx #SE_KOF
    jsl dsp_pair_l
    pla
ninguno:
    pla                         ; the ones starting: the key-on
    rtl
.endproc

; Starts the sound effect of voice Y: its sample, its pitch, its volume and
; the envelope, and its frames. Does not touch Y.
.proc ex_start
.a8
.i16
    phy
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:EX_IDX, x
    pha                         ; [index][voice]
    asl a
    asl a
    asl a
    sec
    sbc 1, s
    tax                         ; its row
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    rep #$20
.a16
    bne de_la_tabla
    lda 1, s
    phx
    jsr msu_pitch
    plx
    cmp #0                      ; `plx` leaves Z from X, not from the pitch
    bne tengo
de_la_tabla:
    lda f:sonido_tabla + 1, x
tengo:
    sta 1, s                    ; [pitch][voice]
    lda f:sonido_tabla + 5, x
    pha                         ; [frames][pitch][voice]
    sep #$20
.a8
    lda f:sonido_tabla + 0, x   ; SRCN
    pha
    lda f:sonido_tabla + 3, x   ; VOLL
    pha
    lda f:sonido_tabla + 4, x   ; VOLR
    pha                         ; [volr][voll][srcn][frames][pitch][voice]
    lda 8, s                    ; the voice
    asl a
    asl a
    asl a
    asl a
    rep #$20
.a16
    and #$00FF
    tax                         ; its first register
    sep #$20
.a8
    pla
    inx
    jsl dsp_pair_l               ; VOLR
    dex
    pla
    jsl dsp_pair_l               ; VOLL
    inx
    inx
    inx
    lda 5, s
    jsl dsp_pair_l               ; the high pitch
    dex
    lda 4, s
    jsl dsp_pair_l               ; and the low
    inx
    inx
    pla
    jsl dsp_pair_l               ; SRCN
    inx
    lda #$FF                    ; ADSR on, attack and decay at maximum
    jsl dsp_pair_l
    inx
    lda #$E0                    ; sustain at maximum and no release
    jsl dsp_pair_l
    lda 5, s                    ; the voice, behind [frames][pitch]
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    pla
    sta f:EX_FRAMES, x
    pla                         ; the pitch
    sep #$20
.a8
    ply
    rts
.endproc

; --- the `.msu` sound effects, when loading the package --------------------------

; At the start of each package: if it is not known yet, whether the `.msu` is
; this cartridge's —once per power-on: the file does not change—; and if it
; is, the sound effects are all forgotten, so that the package uploads them again
; with its version. See above.
.proc se_msu_prepare
.a8
.i16
    lda f:MSU_SE
    bne mirado
    jsr msu_data_valid
    cmp #1
    beq valido
    lda #2
valido:
    sta f:MSU_SE
mirado:
    cmp #1
    bne ready
    ldx #(2 * SE_PRIMERA)
    lda #0
olvidar:
    cpx #(2 * MUESTRAS_N)
    bcs olvidados
    sta f:FAR_ARAM_OF, x
    inx
    bra olvidar
olvidados:
    lda #$FF                    ; the stream, nowhere: the first one seeks
    sta f:MSU_SE_NEXT
    sta f:MSU_SE_NEXT + 1
    sta f:MSU_SE_NEXT + 2
ready:
    rtl
.endproc

; The `se_msu_filas` row of sound effect number A in PKG_MAP's package, in X,
; and C at 1; C at 0 if the package does not carry it. Each package has one row per
; sound effect in its list in `paquetes`, in the same order. Does not touch Y.
.proc se_msu_row
.a8
.i16
    phy
    pha                         ; [sound effect number]
    rep #$20
.a16
    lda f:PKG_MAP
    asl a
    tax
    lda f:paquetes, x           ; like `package_list`
    tax
    sep #$20
.a8
temas:
    lda f:paquetes, x
    inx
    cmp #$FF
    bne temas
    ldy #0                      ; the row, eight at a time
efectos:
    lda f:paquetes, x
    cmp #$FF
    beq no
    cmp 1, s
    beq si
    inx
    rep #$20
.a16
    tya
    clc
    adc #8
    tay
    sep #$20
.a8
    bra efectos
si:
    rep #$20
.a16
    lda f:PKG_MAP
    asl a
    tax
    tya
    clc
    adc f:se_msu_paq, x
    tax
    sep #$20
.a8
    pla
    ply
    sec
    rts
no:
    pla
    ply
    clc
    rts
.endproc

; For `place_sample`, with 16-bit A: if sample PKG_S is a sound effect
; that is going to come from the `.msu`, PKG_LENGTH is its size there.
.proc se_msu_length
.a16
.i16
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PKG_S
    cmp #SE_PRIMERA
    bcc no
    jsr place_effect
    jsr se_msu_row
    bcc no
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PKG_LENGTH
    rtl
no:
    rep #$20
.a16
    rtl
.endproc

; For `upload_placed`: if sample PKG_S is a sound effect that is going to
; come from the `.msu`, uploads it from there to PKG_A and writes its
; directory entry, and returns with C at 1. If not, C at 0 and the ROM
; uploads it.
;
; A package's sound effects are in the `.msu` one after the other, in the order
; they are uploaded, so a seek is done only if the stream was not already
; left where it goes: once per package. Seeking costs Mednafen one or two
; frames; see `msu_data_seek`. If the seek does not arrive in time, the
; sound effect is not uploaded and does not play —its place stays reserved
; all the same—: the ROM has no way to fall back to its own version, which
; has another pitch.
.proc se_msu_upload
.a8
.i16
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PKG_S
    cmp #SE_PRIMERA
    bcc no
    jsr place_effect
    jsr se_msu_row
    bcs hay
no:
    clc
    rtl
hay:
    lda f:se_msu_filas, x
    cmp f:MSU_SE_NEXT
    bne buscar
    lda f:se_msu_filas + 1, x
    cmp f:MSU_SE_NEXT + 1
    bne buscar
    lda f:se_msu_filas + 2, x
    cmp f:MSU_SE_NEXT + 2
    beq en_su_lugar
buscar:
    phx
    rep #$20
.a16
    lda f:se_msu_filas + 2, x
    tay
    lda f:se_msu_filas, x
    jsr msu_data_seek        ; returns with 8-bit A
.a8
    plx
    bcc en_su_lugar
    lda #$FF
    sta f:MSU_SE_NEXT
    sta f:MSU_SE_NEXT + 1
    sta f:MSU_SE_NEXT + 2
    rep #$20
.a16
    lda f:PKG_S
    and #$00FF
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_OF, x
    sep #$20
.a8
    sec
    rtl
en_su_lugar:
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PKG_LENGTH
    clc
    adc f:se_msu_filas, x
    sta f:MSU_SE_NEXT            ; where it will be left
    sep #$20
.a8
    lda f:se_msu_filas + 2, x
    adc #0
    sta f:MSU_SE_NEXT + 2
    phx
    jsr msu_a_aram
    plx
    jsr msu_directory
    sec
    rtl
.endproc

; PKG_LENGTH bytes of the `.msu` stream to ARAM, from PKG_A. It is
; `upload_sample` with another source: in triplets through the driver's
; command 3, in batches of up to 85 with interrupts disabled, and whatever is
; left one byte at a time. The next triplet is read while the SPC700 stores
; the previous one.
.proc msu_a_aram
.a8
.i16
    ldy #0                      ; what has been uploaded
tanda:
    rep #$20
.a16
    tya
    clc
    adc f:PKG_A
    sta f:PKG_DEST
    sty temp
    lda f:PKG_LENGTH
    sec
    sbc temp                    ; what is left
    cmp #3
    bcs hay_ternas
    jmp resto
hay_ternas:
    ldx #85                     ; the driver's index is one byte
    cmp #255
    bcs cuantas
    ldx #0
dividir:
    cmp #3
    bcc cuantas
    sbc #3                      ; C set by the `cmp`
    inx
    bra dividir
cuantas:
    sep #$20
.a8
    jsr msu_point
    php
    sei
    txa
    sta f:APUIO0
    lda #3
    sta f:APUIO2
    inc token
    lda token
    sta f:APUIO3
acuse_bloque:
    cmp f:APUIO3
    bne acuse_bloque
    lda f:MSU_DATA
    sta temp
    lda f:MSU_DATA
    sta temp + 1
    lda f:MSU_DATA
    sta temp + 3
terna:
    lda temp
    sta f:APUIO0
    lda temp + 1
    sta f:APUIO1
    lda temp + 3
    sta f:APUIO2
    inc token
    lda token
    sta f:APUIO3
    iny
    iny
    iny
    dex
    beq ultima
    lda f:MSU_DATA
    sta temp
    lda f:MSU_DATA
    sta temp + 1
    lda f:MSU_DATA
    sta temp + 3
    lda token
acuse:
    cmp f:APUIO3
    bne acuse
    bra terna
ultima:
    lda token
acuse_ultima:
    cmp f:APUIO3
    bne acuse_ultima
    lda #0
    sta f:APUIO2
    plp
    jmp tanda
.a16
resto:
    sep #$20
.a8
    ; What is left, 0, 1 or 2, one byte at a time: the pointer is already
    ; where it goes.
    sta temp
    cmp #0                      ; `sta` does not touch Z, and a sound effect is nine
                                ; bytes per block: it is almost always zero
    beq ready
    jsr msu_point
un_byte:
    lda f:MSU_DATA
    jsr msu_byte
    dec temp
    bne un_byte
ready:
    rts
.endproc

; The number of the sound effect noted in directory entry A, which is a sound
; effect place —SE_PRIMERA or above—, in A: see `FAR_EFFECT_IN`. Clobbers X.
.proc place_effect
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:FAR_EFFECT_IN - SE_PRIMERA, x
    rts
.endproc

; The directory entry of sample PKG_S, already uploaded to PKG_A: the loop
; point is the start plus whatever its row X says, which for a whole sound
; effect is 0.
.proc msu_directory
.a8
.i16
    rep #$20
.a16
    lda f:PKG_S
    and #$00FF
    asl a
    asl a
    clc
    adc #SPC_SAMPLES_ADDR
    sta f:PKG_DEST
    lda f:se_msu_filas + 6, x
    clc
    adc f:PKG_A
    sta temp
    sep #$20
.a8
    jsr msu_point
    lda f:PKG_A
    jsr msu_byte
    lda f:PKG_A + 1
    jsr msu_byte
    lda temp
    jsr msu_byte
    lda temp + 1
    jmp msu_byte
.endproc

; `aram_point`, `aram_byte` and `apu_token`, with the ports through `f:`.
.proc msu_point
.a8
.i16
    php
    sei
    lda #2
    sta f:APUIO2
    lda f:PKG_DEST
    sta f:APUIO0
    lda f:PKG_DEST + 1
    sta f:APUIO1
    jsr msu_token
    lda #0
    sta f:APUIO2
    plp
    rts
.endproc

.proc msu_byte
.a8
.i16
    php
    sei
    sta f:APUIO0
    lda #1
    sta f:APUIO2
    jsr msu_token
    lda #0
    sta f:APUIO2
    plp
    rts
.endproc

.proc msu_token
.a8
.i16
    inc token
    lda token
    sta f:APUIO3
espera:
    cmp f:APUIO3
    bne espera
    rts
.endproc

; For `se_mute`, with interrupts disabled: nothing pending or playing on
; voices 0 to 5, and on the next frame the music gets them back. Returns with
; A holding their bits, for `se_mute`'s KOF.
.proc se_extras_mute
.a8
.i16
    lda #0
    sta f:EX_PEND
    ldx #0
frames:
    sta f:EX_FRAMES, x
    inx
    cpx #(2 * EX_VOICES)
    bcc frames
    lda f:EX_BUSY
    ora f:EX_RETURN
    sta f:EX_RETURN
    rtl
.endproc
