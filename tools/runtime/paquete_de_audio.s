.segment "CODE"

; --- each map's audio package ------------------------------------------------
;
; ARAM is not enough for all the cartridge's samples —the music of the demo's
; songs is 53 KB and the sound effects maps 2 and 3 ask for, 43 and 55 more—,
; so they are uploaded per map: when one loads, the songs its pages can start
; and the sound effects they ask for, in the order they appear. It is the
; `paquetes` table the converter builds. The ones that do not fit do not
; play. With MSU-1, the songs that have a track are not uploaded: see
; `tema_por_msu`.
;
; The music samples have a fixed number across the whole cartridge —the SRCN
; the stream already writes— and the SPC700's directory has one entry for
; each. **Sound effects do not**: they share the SE_LUGARES at the end of the
; directory, from SE_PRIMERA on, because two that are never in the same
; package can go in the same place —see `lugares_de_efectos` in
; snes_music.py—. The package lists carry them by number, `efecto_lugar` says
; each one's place and `FAR_EFECTO_EN` which one was noted down in each place.
; An entry that is not in ARAM points to silence. `FAR_ARAM_DE` says where
; each one is, or 0, and is indexed by directory entry.
;
; **The samples of the song that is playing do not move**: the music goes on
; during the teleport's fade, and overwriting a sample that is playing would
; be noise. Everything else is rearranged again from the start of ARAM,
; skipping those. See "El paquete de audio de cada mapa" in
; workflow/tasks/done/audio-bgm.md.
FAR_ARAM_DE = $7E3100           ; one word per sample
FAR_QUIERE  = $7E3300           ; one byte per sample: 2 for the ones that do not move
APU_LISTO   = $7E30D0           ; whether the driver is already running
PAQ_EXTRA   = $7E30D1           ; a song that goes first, or $FF
PAQ_COMPACTAR = $7E30D2         ; 1 if the package is being rearranged again
                                ; from scratch: see `paquete_cargar_ya`
PAQ_LARGO   = $7E30D4
PAQ_DEST    = $7E30D6
PAQ_S       = $7E30D8           ; the sample being placed
PAQ_X7      = $7E30DA           ; its row in `muestra_tabla`
PAQ_A       = $7E30DC           ; where placing it is tried
PAQ_MAPA    = $7E30DE           ; the package's map, in a word since the
                                ; map index does not fit in a byte
INT_N       = $7E30E0           ; how many are occupied, in bytes: two for each
                                ; $30E2 to $30E6 belong to the battle animation
PAQ_INCOMPLETO = $7E30E7        ; 1 if something of the package did not fit: see
                                ; `tema_asegurar`. What follows is MSU_HAY
INT_INI     = $7E3400           ; what is occupied, in order: where it starts
INT_FIN     = $7E3500           ; and where it ends

; Nothing in ARAM. At reset: the driver is not running yet.
.proc aram_limpiar
.a8
.i16
    lda #0
    sta f:APU_LISTO
    sta f:PAQ_INCOMPLETO
    lda #$FF
    sta f:PAQ_EXTRA
    ldx #0
otra:
    lda #0
    sta f:FAR_ARAM_DE, x
    inx
    cpx #(2 * MUESTRAS_N)
    bcc otra
    ldx #0
    lda #$FF
    bra ninguno_mas
ninguno:
    sta f:FAR_EFECTO_EN, x      ; no sound effect noted down
    inx
ninguno_mas:
    cpx #SE_LUGARES
    bcc ninguno
    rts
.endproc

; The token: the command is already on the ports, and the driver takes it
; when it changes. The acknowledgment is awaited.
.proc apu_testigo
.a8
.i16
    inc token
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; The ARAM pointer, to PAQ_DEST. With interrupts disabled: the music uses the
; same ports, and port 2 has to go back to 0 before it sends its next pair.
.proc aram_apuntar
.a8
.i16
    php
    sei
    lda #2
    sta APUIO2
    lda f:PAQ_DEST
    sta APUIO0
    lda f:PAQ_DEST + 1
    sta APUIO1
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; One byte, the one in A, where the pointer points; the pointer advances.
.proc aram_byte
.a8
.i16
    php
    sei
    sta APUIO0
    lda #1
    sta APUIO2
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; The sample in row PAQ_X7 of `muestra_tabla`, to PAQ_DEST. In triplets via
; command 3, in batches of up to 128 with interrupts disabled —about five
; milliseconds: the music is delayed, not lost—, and whatever is left over
; one byte at a time.
.proc subir_muestra
.a8
.i16
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla, x
    sta comp_glifo
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    sep #$20
.a8
    lda f:muestra_tabla + 2, x
    sta comp_glifo + 2
    ldy #0
tanda:
    ; The pointer, to where the next triplet goes: the block does not advance
    ; it.
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
    sta temp + 2
    sep #$20
.a8
    jsr aram_apuntar
    rep #$20
.a16
    lda temp + 2
    cmp #3
    bcs hay_ternas
    jmp resto
hay_ternas:
    sta WRDIVL
    sep #$20
.a8
    lda #3
    sta WRDIVB                  ; starts: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL                  ; how many triplets are left, if they fit in a byte
    ldx RDDIVL
    cpx #85
    bcc cuantas
    lda #85                     ; the driver's index is one byte
cuantas:
    rep #$20
.a16
    and #$00FF                  ; the count, in X
    tax
    sep #$20
.a8
    php
    sei
    sta APUIO0
    lda #3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
acuse_bloque:
    cmp APUIO3
    bne acuse_bloque
    ; The first triplet, read beforehand; the others are read while the
    ; SPC700 stores the previous one, which is what takes longest. Never one
    ; too many: past the end of the block there may be registers that change
    ; when read.
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
terna:
    lda temp
    sta APUIO0
    lda temp + 1
    sta APUIO1
    lda temp + 3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    dex
    beq ultima
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
    lda token
acuse:
    cmp APUIO3
    bne acuse
    bra terna
ultima:
    lda token
acuse_ultima:
    cmp APUIO3
    bne acuse_ultima
    stz APUIO2
    plp
    jmp tanda
.a16
resto:
    sep #$20
.a8
    ; What is left, 0, 1 or 2, one byte at a time: the pointer is already
    ; where it goes.
    lda temp + 2
    beq listo
    sta temp
un_byte:
    lda [comp_glifo], y
    iny
    jsr aram_byte
    dec temp
    bne un_byte
listo:
    rts
.endproc

; Sample PAQ_S, already uploaded to PAQ_A: its directory entry, with where it
; starts and where it loops.
.proc escribir_directorio
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
    sep #$20
.a8
    jsr aram_apuntar
    lda f:PAQ_A
    jsr aram_byte
    lda f:PAQ_A + 1
    jsr aram_byte
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla + 5, x  ; the loop, from the start
    clc
    adc f:PAQ_A
    sta temp
    sep #$20
.a8
    lda temp
    jsr aram_byte
    lda temp + 1
    jmp aram_byte
.endproc

; X7 of directory entry A: its row in `muestra_tabla` times 7, in PAQ_X7 and
; in X. For a music sample it is the entry itself; for a sound effect place,
; that of the effect noted down there —`FAR_EFECTO_EN`—, which goes after the
; music: SE_PRIMERA plus its number. That row can go past 255, so the
; arithmetic is sixteen bits.
.proc fila_de_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #SE_PRIMERA
    bcc de_musica
    tax
    lda f:FAR_EFECTO_EN - SE_PRIMERA, x
    and #$00FF
    clc
    adc #SE_PRIMERA
de_musica:
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp
    sta f:PAQ_X7
    tax
    sep #$20
.a8
    rts
.endproc

; Finds a place for sample A, if it is not there: the first gap from
; ARAM_DATOS on that does not overwrite any of the ones that already have a
; place. If it does not fit before ARAM_FIN, it is not uploaded and does not
; play. **It does not upload it**: it marks it with 3 in FAR_QUIERE and
; `subir_colocadas` uploads it, once it is known the package fits; see
; `paquete_cargar_ya`.
.proc colocar_muestra
.a8
.i16
    sta f:PAQ_S
    rep #$30
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    beq no_esta
    rts                         ; already there
no_esta:
    lda f:PAQ_S
    jsr fila_de_muestra
    rep #$30
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    jsl se_msu_largo            ; or what the one in the `.msu` measures: efectos_con_msu.s
.a16
    ; The first gap where it fits: the occupied ones are walked in order,
    ; with PAQ_A at the start of the gap being looked at.
    lda #ARAM_DATOS
    sta f:PAQ_A
    ldx #0
hueco:
    txa
    cmp f:INT_N
    bcs al_final
    lda f:INT_INI, x
    sec
    sbc f:PAQ_A                 ; how much there is before this occupied one
    bcc sigue                   ; it starts before: no gap
    cmp f:PAQ_LARGO
    bcs aca                     ; it fits
sigue:
    lda f:INT_FIN, x
    cmp f:PAQ_A
    bcc no_avanza
    sta f:PAQ_A                 ; the next gap starts after it
no_avanza:
    inx
    inx
    bra hueco
al_final:
    lda #ARAM_FIN
    sec
    sbc f:PAQ_A
    bcc no_entra
    cmp f:PAQ_LARGO
    bcs aca
no_entra:
    sep #$20
.a8
    lda #1
    sta f:PAQ_INCOMPLETO        ; so the next `PlayBGM` completes it
    rts                         ; does not fit: does not play
.a16
aca:
    ; It fits at PAQ_A, before occupied X: room is made in the list.
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    ; And where it goes is noted down, and that it still has to be uploaded.
    lda f:PAQ_S
    and #$00FF
    tax
    sep #$20
.a8
    lda #3
    sta f:FAR_QUIERE, x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:PAQ_A
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    rts
.endproc

; Uploads the samples `colocar_muestra` marked with 3, each to its place, and
; writes their directory entry.
.proc subir_colocadas
.a8
.i16
    ldx #0
otra:
    lda f:FAR_QUIERE, x
    cmp #3
    bne sigue
    phx
    txa
    sta f:PAQ_S
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sta f:PAQ_A
    sep #$20
.a8
    lda f:PAQ_S
    jsr fila_de_muestra
    jsl se_msu_subir            ; a sound effect from the `.msu`: see efectos_con_msu.s
    bcs subida
    jsr subir_muestra
    jsr escribir_directorio
subida:
    plx
sigue:
    inx
    cpx #MUESTRAS_N
    bcc otra
    rts
.endproc

; The samples of song A: X at the start of its list in `tema_muestras`.
.proc lista_del_tema
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tema_muestras, x
    tax
    sep #$20
.a8
    rts
.endproc

; Places the samples of song A.
.proc colocar_tema
.a8
.i16
    jsr lista_del_tema
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr colocar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; C at 1 if song A will play through the MSU-1 and not through the SPC700:
; there is an MSU-1, the song has a track and that track was never missing.
; Those are samples the package does not upload, because with a track the
; SPC700 does not play the music —see `music_start`—: the load is shorter and
; ARAM is left for the sound effects. Without MSU-1 it always answers no, and
; the package is the usual one.
;
; **Counting on the track is a bet**, because the ROM does not know whether it
; is on the card until it asks for it. If it is missing, `msu_arrancar` sets
; its bit in MSU_FALTA and `music_start` falls back to `tema_asegurar`, which
; sees the samples not uploaded and rebuilds the package with the song first:
; that time it freezes for however long the upload takes, and from then on
; this song is no longer skipped. For the same reason, the extra song of
; `paquete_cargar_ya` does not go through here: it is the one being asked for.
;
; Saves A, X and Y: the package loops carry the index in X and `marcar_tema`
; the mark in Y.
.proc tema_por_msu
.a8
.i16
    pha
    lda f:MSU_HAY
    beq no
    lda 1, s
    cmp #TEMA_TOTAL
    bcs no
    phx
    phy
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tema_msu, x
    cmp #$FF
    beq no_xy                   ; it has no track
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    tax                         ; its byte in MSU_FALTA
    lda 5, s                    ; the song, behind Y and X
    and #$0007
    tay                         ; and its bit
    sep #$20
.a8
    lda f:MSU_FALTA, x
correr:
    dey
    bmi corrido
    lsr a
    bra correr
corrido:
    and #1
    bne no_xy                   ; the track was missing: it plays through the SPC700
    ply
    plx
    pla
    sec
    rts
no_xy:
    ply
    plx
no:
    pla
    clc
    rts
.endproc

; `marcar_tema` and `colocar_tema` for the songs in the package list, which
; skip the ones that will play through the MSU-1.
.proc marcar_tema_del_paquete
.a8
.i16
    jsr tema_por_msu
    bcs listo
    jmp marcar_tema
listo:
    rts
.endproc

.proc colocar_tema_del_paquete
.a8
.i16
    jsr tema_por_msu
    bcs listo
    jmp colocar_tema
listo:
    rts
.endproc

; Silences the sound effects that are playing: their samples are about to
; move.
.proc se_callar
.a8
.i16
    php
    sei
    lda #0
    sta f:SE_CUADROS
    sta f:SE_CUADROS + 1
    sta f:SE_PENDIENTE
    sta f:SE_BAJAR
    sta f:SE2_CUADROS
    sta f:SE2_CUADROS + 1
    sta f:SE2_PENDIENTE
    sta f:SE2_BAJAR
    lda #1
    sta f:SE_DEVOLVER           ; the music gets its voices back
    sta f:SE2_DEVOLVER
    jsl se_extras_callar        ; and those of voices 0 to 5, in the same KOF
    ora #(SE_BIT | SE2_BIT)
    ldx #SE_KOF
    jsr dsp_par
    plp
    rts
.endproc

; The package of `mapa_actual`: see above. PAQ_EXTRA is a song that goes
; before the map's —the one a `PlayBGM` asks for and was not there—, or $FF.
;
; The map comes from `mapa_actual` and not from A since the index is sixteen
; bits: the three callers passed `mapa_actual` in A, so no case was lost and
; the caller does not have to remember the width.
.proc paquete_cargar
.a8
.i16
    rep #$20
.a16
    lda mapa_actual
    sta f:PAQ_MAPA
    sep #$20
.a8
    jmp paquete_cargar_ya
.endproc

; And the package whose index is already written in `PAQ_MAPA`, which is how
; the battle comes in: its package is not any map's —it goes after all of
; them, see `BA_PAQUETE`— so it cannot come from `mapa_actual`.
;
; It exists because there was a bug here that no git conflict flagged: when
; the index became sixteen bits, `paquete_cargar` stopped reading the package
; from A to read it from `mapa_actual`, and `batalla_audio_cargar` —which came
; from the other branch— kept passing it in A. The two branches merged clean
; because they touched different lines, and from then on the battle loaded
; the map's package: the battle song played with six samples not uploaded and
; the hit missed with sample 0. The two audio tests in `test_batalla.py`
; caught it.
.proc paquete_cargar_ya
.a8
.i16
    lda f:APU_LISTO
    bne listo_apu
    rts                         ; at reset, before the driver runs
listo_apu:
    lda #0
    sta f:PAQ_INCOMPLETO
    sta f:PAQ_COMPACTAR
    jsr se_callar
    jsl se_msu_preparar         ; with the `.msu` sound effects, all are
                                ; uploaded again: see efectos_con_msu.s
    ldx #0
limpiar:
    lda #0
    sta f:FAR_QUIERE, x
    inx
    cpx #MUESTRAS_N
    bcc limpiar
    ; The ones of the song playing do not move: 2.
    lda music_apagada
    bne sin_fijas
    lda tema_actual
    cmp #TEMA_TOTAL
    bcs sin_fijas
    ldy #2
    jsr marcar_tema
sin_fijas:
    ; The ones the package wants: 1, if they were not already 2. The extra's
    ; **even if it has a track**: if it is asked for, it is because it will
    ; play through the SPC700. The ones of the package's songs, not if they
    ; will play through the MSU-1: see `tema_por_msu`.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra
    ldy #1
    jsr marcar_tema
sin_extra:
    ; An exit song that its `PlayBGM` asks for goes alone: nothing else of the
    ; package stays. See `extra_de_salida`.
    jsr extra_de_salida
    bcc con_paquete
    jmp marcadas
con_paquete:
    ; A separate song that its `PlayBGM` asks for goes with the package's
    ; sound effects and without the other songs: see `extra_aparte`.
    jsr lista_del_paquete
    jsr extra_aparte
    bcc temas_q
saltear_q:
    lda f:paquetes, x
    cmp #$FF
    beq efectos_q
    inx
    bra saltear_q
temas_q:
    lda f:paquetes, x
    cmp #$FF
    beq efectos_q
    phx
    ldy #1
    jsr marcar_tema_del_paquete
    plx
    inx
    bra temas_q
efectos_q:
    inx
otro_q:
    lda f:paquetes, x
    cmp #$FF
    beq salida_q
    phx
    jsr anotar_efecto           ; from the sound effect's number to its place
    ldy #1
    jsr marcar_muestra
    plx
    inx
    bra otro_q
salida_q:
    ; And the exit songs, which are wanted anyway: if they were already there,
    ; they stay. With a separate song, not.
    jsr extra_aparte
    bcs marcadas
    inx
otro_s:
    lda f:paquetes, x
    cmp #$FF
    beq marcadas
    phx
    ldy #1
    jsr marcar_tema_del_paquete
    plx
    inx
    bra otro_s
marcadas:
    ; The ones nobody wants are forgotten, and with the ones left the list of
    ; what is occupied is built, in order: it is where `colocar_muestra` looks
    ; for the gaps.
    rep #$20
.a16
    lda #0
    sta f:INT_N
    sep #$20
.a8
    ldx #0
olvidar:
    lda f:FAR_QUIERE, x
    phx
    rep #$20
.a16
    pha
    txa
    asl a
    tax
    pla
    and #$00FF
    bne quiere
    sta f:FAR_ARAM_DE, x        ; nobody wants it: out
    bra proxima
quiere:
    lda f:FAR_ARAM_DE, x
    beq proxima                 ; wanted but not there: the next step uploads it
    sta f:PAQ_A
    txa
    lsr a
    sep #$20
.a8
    jsr fila_de_muestra
    rep #$20
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    jsr intervalo_ordenado
proxima:
    sep #$20
.a8
    plx
    inx
    cpx #MUESTRAS_N
    bcc olvidar
    ; And the missing ones are placed, in order of priority: the extra song,
    ; the map's songs and its sound effects.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra2
    jsr colocar_tema
sin_extra2:
    jsr extra_de_salida
    bcc con_paquete2
    jmp colocadas
con_paquete2:
    jsr lista_del_paquete
    jsr extra_aparte
    bcc temas
saltear:
    lda f:paquetes, x
    cmp #$FF
    beq efectos
    inx
    bra saltear
temas:
    lda f:paquetes, x
    cmp #$FF
    beq efectos
    phx
    jsr colocar_tema_del_paquete
    plx
    inx
    bra temas
efectos:
    inx
otro_efecto:
    lda f:paquetes, x
    cmp #$FF
    beq de_salida
    phx
    jsr anotar_efecto           ; already noted down: it only gives the place
    jsr colocar_muestra
    plx
    inx
    bra otro_efecto
de_salida:
    ; The exit songs, after everything and **if there is room**: not fitting
    ; does not leave the package incomplete —their `PlayBGM` is not needed to
    ; complete it, nor to rebuild everything from scratch—, because their
    ; `PlayBGM` uploads them on their own. That is why PAQ_INCOMPLETO is saved
    ; and restored around this. With a separate song none is uploaded.
    jsr extra_aparte
    bcs colocadas
    inx
    lda f:PAQ_INCOMPLETO
    pha
otro_de_salida:
    lda f:paquetes, x
    cmp #$FF
    beq salida_puesta
    phx
    jsr colocar_tema_del_paquete
    plx
    inx
    bra otro_de_salida
salida_puesta:
    pla
    sta f:PAQ_INCOMPLETO
colocadas:
    ; **If something did not fit, everything is placed again from scratch**,
    ; except the samples of the song playing, and only then uploaded. The
    ; ones the package wants and were already there stay where they were,
    ; which is what makes a map change that shares samples with the previous
    ; one cheap; but with the per-package budget each one fills almost all of
    ; ARAM, and those gaps were enough to leave out samples of a package that
    ; fits on its own: coming back from a battle, or from one map to another
    ; with the music silenced. That is why where each one goes is decided
    ; first and the upload is done at the end: redoing the whole upload would
    ; cost twice the frames.
    lda f:PAQ_INCOMPLETO
    beq subir
    lda f:PAQ_COMPACTAR
    bne subir                   ; already redone: it is the song playing
    lda #1
    sta f:PAQ_COMPACTAR
    lda #0
    sta f:PAQ_INCOMPLETO
    ldx #0
compactar:
    lda f:FAR_QUIERE, x
    cmp #2
    beq quieta                  ; the ones of the song playing do not move
    cmp #0
    beq quieta                  ; and the ones nobody wants were already forgotten
    lda #1
    sta f:FAR_QUIERE, x
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_DE, x
    sep #$20
.a8
    plx
quieta:
    inx
    cpx #MUESTRAS_N
    bcc compactar
    jmp marcadas
subir:
    jsr subir_colocadas
    ; With an exit song uploaded alone, the rest of the package was let go:
    ; if the page does not leave the map, the next `PlayBGM` completes it. The
    ; same with a separate song, which goes up without the other songs.
    jsr extra_de_salida
    bcs incompleto
    jsr extra_aparte
    bcc listo
incompleto:
    lda #1
    sta f:PAQ_INCOMPLETO
listo:
    rts
.endproc

; C at 1 if PAQ_EXTRA is one of the exit songs of PAQ_MAPA's package: the
; third list in `paquetes`. They are the ones the map starts only to leave
; —see `Temas.de_salida` in tools/port/events.py—, and the game's case is
; `lufsorr` on map 3: it plays after the sequence of sound effects, so it has
; no reason to fit alongside them, and the converter gives it the rate of a
; song on its own. When its `PlayBGM` asks for it and it is not there, it is
; uploaded **alone**, letting go of the rest, and not the whole package with
; it first: that would not fit, and rebuilding it from scratch would be
; uploading the whole ARAM.
.proc extra_de_salida
.a8
.i16
    phy
    ldy #2
    jsr extra_en_lista
    ply                         ; C survives the `ply`
    rts
.endproc

; C at 1 if PAQ_EXTRA is one of the separate songs of PAQ_MAPA's package: the
; fourth list in `paquetes`. They are the ones in `[music] apart_themes` of
; the project file, and the game's case is `vswar` on 38 and 47: it plays in
; a scene, never at the same time as the map's other songs, and with them it
; did not fit at the rate it has on its own. When its `PlayBGM` asks for it
; and it is not there, it is uploaded **with the package's sound effects**
; —which can play in the meantime: the chests in the dump on 38—, and the
; other songs are let go until the next `PlayBGM`, as with an exit one. The
; converter counts on that: a separate song has to fit with those sound
; effects.
.proc extra_aparte
.a8
.i16
    phy
    ldy #3
    jsr extra_en_lista
    ply
    rts
.endproc

; C at 1 if PAQ_EXTRA is in list Y of PAQ_MAPA's package: 2 the exit songs, 3
; the separate ones. Saves X, which is the index of the loops in
; `paquete_cargar_ya`: `extra_aparte` is asked in the middle of them. C
; survives the `plx`.
.proc extra_en_lista
.a8
.i16
    phx
    lda f:PAQ_EXTRA
    cmp #$FF
    beq no
    jsr lista_del_paquete
saltar:
    dey
    bmi mirar
otra:
    lda f:paquetes, x
    inx
    cmp #$FF
    bne otra
    bra saltar
mirar:
    lda f:paquetes, x
    cmp #$FF
    beq no
    cmp f:PAQ_EXTRA
    beq si
    inx
    bra mirar
si:
    plx
    sec
    rts
no:
    plx
    clc
    rts
.endproc

; X at the start of the list of PAQ_MAPA's package.
.proc lista_del_paquete
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:paquetes, x
    tax
    sep #$20
.a8
    rts
.endproc

; Sound effect number A, noted down in its directory place: returns with the
; place in A, which is what `marcar_muestra` and `colocar_muestra` use. If
; another sound effect was noted down there, that one is forgotten —its
; FAR_ARAM_DE to 0—, so its ARAM is freed and the new one is uploaded: with
; `se_callar` nothing is playing anymore. It is called with each sound effect
; of the package when marking and again when placing, and the second time
; changes nothing. Does not touch Y.
.proc anotar_efecto
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:efecto_lugar, x
    rep #$20
.a16
    and #$00FF
    tax                         ; the place, from zero
    sep #$20
.a8
    pla
    cmp f:FAR_EFECTO_EN, x
    beq anotado
    sta f:FAR_EFECTO_EN, x
    rep #$20
.a16
    txa
    clc
    adc #SE_PRIMERA
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_DE, x        ; the one that was there goes
    txa
    lsr a                       ; X was the entry times two
    sep #$20
.a8
    rts
anotado:
    txa
    clc
    adc #SE_PRIMERA
    rts
.endproc

; Sample A, marked with Y in FAR_QUIERE if it did not have something higher.
.proc marcar_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    tya
    cmp f:FAR_QUIERE, x
    bcc listo
    sta f:FAR_QUIERE, x
listo:
    rts
.endproc

; The samples of song A, marked with Y.
.proc marcar_tema
.a8
.i16
    phy
    jsr lista_del_tema
    ply
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr marcar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; Adds the interval [PAQ_A, PAQ_A + PAQ_LARGO) to the list of what is
; occupied, in order. 16-bit A.
.proc intervalo_ordenado
.a16
.i16
    ldx #0
buscar:
    txa
    cmp f:INT_N
    bcs lugar
    lda f:INT_INI, x
    cmp f:PAQ_A
    bcs lugar                   ; this one starts later: it goes in front
    inx
    inx
    bra buscar
lugar:
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    rts
.endproc

; Before starting song A: if it is missing any sample, the music is silenced,
; everything is let go and the map's package is rebuilt with it first. It
; happens with a `PlayBGM` of a song the map did not bring —the title's, or
; one from a common event— and it freezes the picture for however long the
; upload takes.
;
; And the same if the map's package **was left incomplete**, even if the song
; is missing nothing. It happens when entering a map with another's song
; playing: its samples do not move —see `paquete_cargar_ya`— and what does
; not fit beside them is the last part of the package, the sound effects. The
; game's case is the passage from map 2 to 3, which happens with map 2's song
; playing and left out some of map 3's sound effects until the next map
; change, even though its page started its own song right away. A `PlayBGM`
; starts the song from zero and silences what was playing, so it is the first
; moment those samples can be let go: it is rebuilt, and only what was
; missing is uploaded. If the package does not fit even so, the rebuild
; uploads nothing and costs less than a frame.
.proc tema_asegurar
.a8
.i16
    sta temp + 1
    lda f:APU_LISTO
    beq listo
    lda temp + 1
    cmp #TEMA_TOTAL
    bcs listo
    lda f:PAQ_INCOMPLETO
    bne falta                   ; even if the song is missing nothing
    lda temp + 1                ; the song: `lista_del_tema` reads it from A
    jsr lista_del_tema
mirar:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo                   ; they are all there
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    plx
    cmp #0                      ; **Z here is set by `plx`, not by the `lda`**:
                                ; PLX leaves N and Z of the value it pulls from
                                ; the stack, which is the list index and is
                                ; never zero. Without this `cmp` the answer was
                                ; always "they are all there" and the title
                                ; song played against a directory of silences.
                                ; It is sixteen bits, like the address: the
                                ; same care `op_sound` takes with `xba`.
    sep #$20
.a8
    beq falta
    inx
    bra mirar
falta:
    php
    sei
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; all voices release
    plp
    lda temp + 1
    sta f:PAQ_EXTRA
    jsr paquete_cargar
    lda #$FF
    sta f:PAQ_EXTRA
listo:
    rts
.endproc

