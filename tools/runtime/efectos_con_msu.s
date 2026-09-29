.segment "FAR"

; --- sound effects with MSU-1 --------------------------------------------------
;
; With MSU-1 the song plays from its track and the SPC700 plays no music, so
; the sound effects can have what used to be the music's. There are two
; things, and **without MSU-1 neither of them does anything**: `MSU_HAY` at
; zero turns both off, and what is left is the usual —voices 7 and 6, the ROM's
; sound effects—.
;
; **Voices 0 to 5.** While the SPC700 plays no music —there is MSU-1 and
; `music_apagada` is set: a track plays, or nothing—, a sound effect that
; does not fit in 7 or in 6 takes one of those. In RM2k sound effects add up,
; and `evilrhys`'s scene on map 3 has a moment with three at once. Their state
; lives in `EX_*` (ram_lejana.s), smaller than that of 7 and 6: instead of the
; copy of the `sonido_tabla` row, its index, and the interrupt reads it when
; starting it.
;
; If a song starts playing through the SPC700 while a sound effect plays on
; one of those —a missing track, or a `PlayBGM` of a song with no track—,
; **the sound effect goes on**: what the music writes to that voice stays in
; MUS_SOMBRA and is not sent (`dsp_musica`), and when the sound effect ends it
; is given back from there (`se_extras_antes`). It is the same as what happens
; with 7 and 6, only the shadow is the music's and not one of its own: there
; was no RAM for six more.
;
; **The quality sound effects from the `.msu`.** If the `.msu` is this
; cartridge's —the signature, `msu_datos_validos`—, each package's sound effects
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
; matter. What runs inside `irq_musica` —`se_extras_antes` and
; `se_extras_despues`— does not use `temp`, for the same reason
; `efectos_de_sonido.s` does not.

EX_VOCES = 6                    ; from 0 to 5
.assert SE_BIT = $80 && SE2_BIT = $40, error, "the usual sound effect voices are no longer 7 and 6"

; The bit of each voice, and that of the voice of each DSP register: that of
; voices 0 to 5 on their registers 0 to 7 and zero on the rest, so that
; `dsp_musica` asks with a single `and`.
ex_bit:
    .byte $01, $02, $04, $08, $10, $20
ex_bit_de_registro:
.repeat 128, r
  .if (r >> 4) < EX_VOCES && (r & $0F) < 8
    .byte 1 << (r >> 4)
  .else
    .byte 0
  .endif
.endrepeat

; All at zero, on reset: far RAM starts with garbage on bsnes.
.proc se_extras_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:EX_CUADROS, x
    inx
    cpx #(EX_FIN - EX_CUADROS)
    bcc otro
    rtl
.endproc

; C at 1 if voices 0 to 5 belong to the sound effects: there is MSU-1 and the
; SPC700 plays no music.
.proc ex_permitidas
.a8
.i16
    lda f:MSU_HAY
    beq no
    lda f:music_apagada
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
.proc ex_tomar
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
    ora f:EX_OCUP
    sta f:EX_OCUP
    ; If it was being given back, not anymore: it goes straight to the new
    ; sound effect.
    pla
    eor #$FF
    and f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    rts
.endproc

; For `sonido_tocar`, with interrupts disabled: if one of voices 0 to 5 is
; playing the same sample as the sound effect of index A —sixteen bits— and
; row X, it is given to that one, as 7 and 6 do with the rain. C at 1 if it
; took it. Returns with 8-bit A, and with X as it came.
.proc se_extra_misma
.a16
.i16
    phx
    pha                         ; [index][row]
    sep #$20
.a8
    jsr ex_permitidas
    bcc no
    lda f:sonido_tabla, x
    pha                         ; [srcn][index][row]
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_OCUP
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
    cpy #EX_VOCES
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
    jsr ex_tomar
.a8
    plx
    sec
    rtl
.endproc

; And if 7 and 6 are busy, one of voices 0 to 5 that is free.
.proc se_extra_libre
.a16
.i16
    phx
    pha
    sep #$20
.a8
    jsr ex_permitidas
    bcc no
    ldy #0
otra:
    tyx
    lda f:ex_bit, x
    and f:EX_OCUP
    beq tomar
    iny
    cpy #EX_VOCES
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
    jsr ex_tomar
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
.proc altura_msu
.a16
.i16
    pha                         ; the index being searched for
    lda f:PAQ_MAPA
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

; For `sonido_tocar`, after copying the pending one of the voice whose offset
; X carries: with the `.msu` sound effects, the pitch of its version. A
; carries the index, sixteen bits. Returns with 8-bit A.
.proc se_msu_altura_poner
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
    bne listo
    lda 1, s
    jsr altura_msu
    beq listo
    tay
    lda 3, s
    tax
    tya
    sta f:SE_NUEVO + 1, x       ; the low pitch and the high one
listo:
    pla
    plx
    sep #$20
.a8
    rtl
.endproc

; --- inside `irq_musica` -------------------------------------------------------

; Before the music: the voices whose sound effect ended on the previous frame
; go back to it. KOF as the music had it, except whatever is still busy, and
; their eight registers from MUS_SOMBRA, which is what the stream wrote to
; them in the meantime.
.proc se_extras_antes
.a8
.i16
    lda f:EX_DEVOLVER
    bne hay
    rtl
hay:
    eor #$FF
    and f:EX_OCUP
    sta f:EX_OCUP
    jsl se_kof_musica_l
    ldx #SE_KOF
    jsl dsp_par_l
    ldy #0
voz:
    tyx
    lda f:ex_bit, x
    and f:EX_DEVOLVER
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
registro:
    lda f:MUS_SOMBRA, x
    jsl dsp_par_l
    inx
    txa
    and #$07
    bne registro
sigue:
    iny
    cpy #EX_VOCES
    bcc voz
    lda #0
    sta f:EX_DEVOLVER
    rtl
.endproc

; After the music: start the pending ones, and count the ones playing and
; turn off the ones ending. Returns with A holding the bits of the voices to
; key on: `se_despues` does the key-on, once for all of them.
;
; **A single KOF for the ones ending, and after the ones starting**: each KOF
; overwrites the previous one, and if two land before the DSP reads it, the
; first one never existed. The one starting writes the music's without the
; busy voices; if the one ending wrote first, its own would be lost, and a
; looping ROM sound effect would keep playing.
.proc se_extras_despues
.a8
.i16
    lda f:EX_OCUP
    bne hay
    rtl                         ; A at zero: nothing to key on
hay:
    lda f:EX_PEND
    pha                         ; [the ones starting]
    beq contar_todas
    lda #0
    sta f:EX_PEND
    jsl se_kof_musica_l
    ldx #SE_KOF
    jsl dsp_par_l
    ldy #0
arrancar:
    tyx
    lda f:ex_bit, x
    and 1, s
    beq no_arranca
    jsr ex_arrancar
no_arranca:
    iny
    cpy #EX_VOCES
    bcc arrancar
    lda #1
    sta f:SE_BAJAR              ; the next frame the key-on is lowered
contar_todas:
    lda #0
    pha                         ; [the ones ending][the ones starting]
    ldy #0
contar:
    tyx
    lda f:ex_bit, x
    and 2, s
    bne sigue                   ; just started: counted from the next one
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:EX_CUADROS, x
    beq nada
    dec a
    sta f:EX_CUADROS, x
    bne nada
    sep #$20
.a8
    tyx
    lda f:ex_bit, x
    ora 1, s
    sta 1, s
    bra sigue
.a16
nada:
    sep #$20
.a8
sigue:
    iny
    cpy #EX_VOCES
    bcc contar
    pla                         ; the ones ending
    beq ninguno
    pha
    ora f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    jsl se_kof_musica_l
    ora 1, s
    ldx #SE_KOF
    jsl dsp_par_l
    pla
ninguno:
    pla                         ; the ones starting: the key-on
    rtl
.endproc

; Starts the sound effect of voice Y: its sample, its pitch, its volume and
; the envelope, and its frames. Does not touch Y.
.proc ex_arrancar
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
    jsr altura_msu
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
    jsl dsp_par_l               ; VOLR
    dex
    pla
    jsl dsp_par_l               ; VOLL
    inx
    inx
    inx
    lda 5, s
    jsl dsp_par_l               ; the high pitch
    dex
    lda 4, s
    jsl dsp_par_l               ; and the low
    inx
    inx
    pla
    jsl dsp_par_l               ; SRCN
    inx
    lda #$FF                    ; ADSR on, attack and decay at maximum
    jsl dsp_par_l
    inx
    lda #$E0                    ; sustain at maximum and no release
    jsl dsp_par_l
    lda 5, s                    ; the voice, behind [frames][pitch]
    asl a
    rep #$20
.a16
    and #$00FF
    tax
    pla
    sta f:EX_CUADROS, x
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
.proc se_msu_preparar
.a8
.i16
    lda f:MSU_SE
    bne mirado
    jsr msu_datos_validos
    cmp #1
    beq valido
    lda #2
valido:
    sta f:MSU_SE
mirado:
    cmp #1
    bne listo
    ldx #(2 * SE_PRIMERA)
    lda #0
olvidar:
    cpx #(2 * MUESTRAS_N)
    bcs olvidados
    sta f:FAR_ARAM_DE, x
    inx
    bra olvidar
olvidados:
    lda #$FF                    ; the stream, nowhere: the first one seeks
    sta f:MSU_SE_SIG
    sta f:MSU_SE_SIG + 1
    sta f:MSU_SE_SIG + 2
listo:
    rtl
.endproc

; The `se_msu_filas` row of sound effect number A in PAQ_MAPA's package, in X,
; and C at 1; C at 0 if the package does not carry it. Each package has one row per
; sound effect in its list in `paquetes`, in the same order. Does not touch Y.
.proc se_msu_fila
.a8
.i16
    phy
    pha                         ; [sound effect number]
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:paquetes, x           ; like `lista_del_paquete`
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
    lda f:PAQ_MAPA
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

; For `colocar_muestra`, with 16-bit A: if sample PAQ_S is a sound effect
; that is going to come from the `.msu`, PAQ_LARGO is its size there.
.proc se_msu_largo
.a16
.i16
    sep #$20
.a8
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PAQ_S
    cmp #SE_PRIMERA
    bcc no
    jsr efecto_del_lugar
    jsr se_msu_fila
    bcc no
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PAQ_LARGO
    rtl
no:
    rep #$20
.a16
    rtl
.endproc

; For `subir_colocadas`: if sample PAQ_S is a sound effect that is going to
; come from the `.msu`, uploads it from there to PAQ_A and writes its
; directory entry, and returns with C at 1. If not, C at 0 and the ROM
; uploads it.
;
; A package's sound effects are in the `.msu` one after the other, in the order
; they are uploaded, so a seek is done only if the stream was not already
; left where it goes: once per package. Seeking costs Mednafen one or two
; frames; see `msu_datos_buscar`. If the seek does not arrive in time, the
; sound effect is not uploaded and does not play —its place stays reserved
; all the same—: the ROM has no way to fall back to its own version, which
; has another pitch.
.proc se_msu_subir
.a8
.i16
    lda f:MSU_SE
    cmp #1
    bne no
    lda f:PAQ_S
    cmp #SE_PRIMERA
    bcc no
    jsr efecto_del_lugar
    jsr se_msu_fila
    bcs hay
no:
    clc
    rtl
hay:
    lda f:se_msu_filas, x
    cmp f:MSU_SE_SIG
    bne buscar
    lda f:se_msu_filas + 1, x
    cmp f:MSU_SE_SIG + 1
    bne buscar
    lda f:se_msu_filas + 2, x
    cmp f:MSU_SE_SIG + 2
    beq en_su_lugar
buscar:
    phx
    rep #$20
.a16
    lda f:se_msu_filas + 2, x
    tay
    lda f:se_msu_filas, x
    jsr msu_datos_buscar        ; returns with 8-bit A
.a8
    plx
    bcc en_su_lugar
    lda #$FF
    sta f:MSU_SE_SIG
    sta f:MSU_SE_SIG + 1
    sta f:MSU_SE_SIG + 2
    rep #$20
.a16
    lda f:PAQ_S
    and #$00FF
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    sec
    rtl
en_su_lugar:
    rep #$20
.a16
    lda f:se_msu_filas + 4, x
    sta f:PAQ_LARGO
    clc
    adc f:se_msu_filas, x
    sta f:MSU_SE_SIG            ; where it will be left
    sep #$20
.a8
    lda f:se_msu_filas + 2, x
    adc #0
    sta f:MSU_SE_SIG + 2
    phx
    jsr msu_a_aram
    plx
    jsr msu_directorio
    sec
    rtl
.endproc

; PAQ_LARGO bytes of the `.msu` stream to ARAM, from PAQ_A. It is
; `subir_muestra` with another source: in triplets through the driver's
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
    adc f:PAQ_A
    sta f:PAQ_DEST
    sty temp
    lda f:PAQ_LARGO
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
    jsr msu_apuntar
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
    lda f:MSU_DATOS
    sta temp
    lda f:MSU_DATOS
    sta temp + 1
    lda f:MSU_DATOS
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
    lda f:MSU_DATOS
    sta temp
    lda f:MSU_DATOS
    sta temp + 1
    lda f:MSU_DATOS
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
    beq listo
    jsr msu_apuntar
un_byte:
    lda f:MSU_DATOS
    jsr msu_byte
    dec temp
    bne un_byte
listo:
    rts
.endproc

; The number of the sound effect noted in directory entry A, which is a sound
; effect place —SE_PRIMERA or above—, in A: see `FAR_EFECTO_EN`. Clobbers X.
.proc efecto_del_lugar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:FAR_EFECTO_EN - SE_PRIMERA, x
    rts
.endproc

; The directory entry of sample PAQ_S, already uploaded to PAQ_A: the loop
; point is the start plus whatever its row X says, which for a whole sound
; effect is 0.
.proc msu_directorio
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_S
    and #$00FF
    asl a
    asl a
    clc
    adc #SPC_SAMPLES_ADDR
    sta f:PAQ_DEST
    lda f:se_msu_filas + 6, x
    clc
    adc f:PAQ_A
    sta temp
    sep #$20
.a8
    jsr msu_apuntar
    lda f:PAQ_A
    jsr msu_byte
    lda f:PAQ_A + 1
    jsr msu_byte
    lda temp
    jsr msu_byte
    lda temp + 1
    jmp msu_byte
.endproc

; `aram_apuntar`, `aram_byte` and `apu_testigo`, with the ports through `f:`.
.proc msu_apuntar
.a8
.i16
    php
    sei
    lda #2
    sta f:APUIO2
    lda f:PAQ_DEST
    sta f:APUIO0
    lda f:PAQ_DEST + 1
    sta f:APUIO1
    jsr msu_testigo
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
    jsr msu_testigo
    lda #0
    sta f:APUIO2
    plp
    rts
.endproc

.proc msu_testigo
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

; For `se_callar`, with interrupts disabled: nothing pending or playing on
; voices 0 to 5, and on the next frame the music gets them back. Returns with
; A holding their bits, for `se_callar`'s KOF.
.proc se_extras_callar
.a8
.i16
    lda #0
    sta f:EX_PEND
    ldx #0
cuadros:
    sta f:EX_CUADROS, x
    inx
    cpx #(2 * EX_VOCES)
    bcc cuadros
    lda f:EX_OCUP
    ora f:EX_DEVOLVER
    sta f:EX_DEVOLVER
    rtl
.endproc
