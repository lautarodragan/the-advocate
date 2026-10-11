.segment "FAR2"

; --- each map's audio package ------------------------------------------------
;
; ARAM is not enough for all the cartridge's samples —the music of the demo's
; songs is 53 KB and the sound effects maps 2 and 3 ask for, 43 and 55 more—,
; so they are uploaded per map: when one loads, the songs its pages can start
; and the sound effects they ask for, in the order they appear. It is the
; `packages` table the converter builds. The ones that do not fit do not
; play. With MSU-1, the songs that have a track are not uploaded: see
; `song_per_msu`.
;
; The music samples have a fixed number across the whole cartridge —the SRCN
; the stream already writes— and the SPC700's directory has one entry for
; each. **Sound effects do not**: they share the SE_PLACES at the end of the
; directory, from SE_FIRST on, because two that are never in the same
; package can go in the same place —see `effect_places` in
; rm2k-snes-audio—. The package lists carry them by number, `effect_place` says
; each one's place and `FAR_EFFECT_IN` which one was noted down in each place.
; An entry that is not in ARAM points to silence. `FAR_ARAM_OF` says where
; each one is, or 0, and is indexed by directory entry.
;
; **The samples of the song that is playing do not move**: the music goes on
; during the teleport's fade, and overwriting a sample that is playing would
; be noise. Everything else is rearranged again from the start of ARAM,
; skipping those. See "El paquete de audio de cada mapa" in
; tasks/audio-bgm.md.
FAR_ARAM_OF = $7E3100           ; one word per sample
FAR_WANTS   = $7E3300           ; one byte per sample: 2 for the ones that do not move
APU_READY   = $7E30D0           ; whether the driver is already running
PKG_EXTRA   = $7E30D1           ; a song that goes first, or $FF
PKG_COMPACT = $7E30D2           ; 1 if the package is being rearranged again
                                ; from scratch, 2 if that could not make it
                                ; fit: see `package_load_done`
PKG_LENGTH  = $7E30D4
PKG_DEST    = $7E30D6
PKG_S       = $7E30D8           ; the sample being placed
PKG_X7      = $7E30DA           ; its row in `sample_table`
PKG_A       = $7E30DC           ; where placing it is tried
PKG_MAP     = $7E30DE           ; the package's map, in a word since the
                                ; map index does not fit in a byte
INT_N       = $7E30E0           ; how many are occupied, in bytes: two for each
                                ; $30E2 to $30E6 belong to the battle animation
PKG_PARTIAL = $7E30E7           ; 1 if something of the package did not fit: see
                                ; `song_ensure`. What follows is MSU_HAS
INT_INIT    = $7E3400           ; what is occupied, in order: where it starts
INT_END     = $7E3500           ; and where it ends

; Nothing in ARAM. At reset: the driver is not running yet.
.proc aram_clear
.a8
.i16
    lda #0
    sta f:APU_READY
    sta f:PKG_PARTIAL
    lda #$FF
    sta f:PKG_EXTRA
    ldx #0
other:
    lda #0
    sta f:FAR_ARAM_OF, x
    inx
    cpx #(2 * SAMPLES_N)
    bcc other
    ldx #0
    lda #$FF
    bra none_more
none:
    sta f:FAR_EFFECT_IN, x      ; no sound effect noted down
    inx
none_more:
    cpx #SE_PLACES
    bcc none
    rts
.endproc

; The token: the command is already on the ports, and the driver takes it
; when it changes. The acknowledgment is awaited.
.proc apu_token
.a8
.i16
    inc token
    lda token
    sta APUIO3
wait:
    cmp APUIO3
    bne wait
    rts
.endproc

; The ARAM pointer, to PKG_DEST. With interrupts disabled: the music uses the
; same ports, and port 2 has to go back to 0 before it sends its next pair.
.proc aram_point
.a8
.i16
    php
    sei
    lda #2
    sta APUIO2
    lda f:PKG_DEST
    sta APUIO0
    lda f:PKG_DEST + 1
    sta APUIO1
    jsr apu_token
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
    jsr apu_token
    stz APUIO2
    plp
    rts
.endproc

; The sample in row PKG_X7 of `sample_table`, to PKG_DEST. In triplets via
; command 3, in batches of up to 128 with interrupts disabled —about five
; milliseconds: the music is delayed, not lost—, and whatever is left over
; one byte at a time.
.proc upload_sample
.a8
.i16
    rep #$30
.a16
    lda f:PKG_X7
    tax
    lda f:sample_table, x
    sta comp_glyph
    lda f:sample_table + 3, x
    sta f:PKG_LENGTH
    sep #$20
.a8
    lda f:sample_table + 2, x
    sta comp_glyph + 2
.ifdef MSU_REQUIRED
    cmp #MSU_SPILL_BANK
    bne in_rom
    jsl f:msu_sample_l          ; it travels in the `.msu`: see there
    rts
in_rom:
.endif
    ldy #0
suite:
    ; The pointer, to where the next triplet goes: the block does not advance
    ; it.
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
    sta temp + 2
    sep #$20
.a8
    jsr aram_point
    rep #$20
.a16
    lda temp + 2
    cmp #3
    bcs has_triplets
    jmp rest
has_triplets:
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
    bcc how_many
    lda #85                     ; the driver's index is one byte
how_many:
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
ack_block:
    cmp APUIO3
    bne ack_block
    ; The first triplet, read beforehand; the others are read while the
    ; SPC700 stores the previous one, which is what takes longest. Never one
    ; too many: past the end of the block there may be registers that change
    ; when read.
    lda [comp_glyph], y
    sta temp
    iny
    lda [comp_glyph], y
    sta temp + 1
    iny
    lda [comp_glyph], y
    sta temp + 3
    iny
triplet:
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
    beq last
    lda [comp_glyph], y
    sta temp
    iny
    lda [comp_glyph], y
    sta temp + 1
    iny
    lda [comp_glyph], y
    sta temp + 3
    iny
    lda token
ack:
    cmp APUIO3
    bne ack
    bra triplet
last:
    lda token
ack_last:
    cmp APUIO3
    bne ack_last
    stz APUIO2
    plp
    jmp suite
.a16
rest:
    sep #$20
.a8
    ; What is left, 0, 1 or 2, one byte at a time: the pointer is already
    ; where it goes.
    lda temp + 2
    beq ready
    sta temp
byte:
    lda [comp_glyph], y
    iny
    jsr aram_byte
    dec temp
    bne byte
ready:
    rts
.endproc

; Sample PKG_S, already uploaded to PKG_A: its directory entry, with where it
; starts and where it loops.
.proc write_directory
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
    sep #$20
.a8
    jsr aram_point
    lda f:PKG_A
    jsr aram_byte
    lda f:PKG_A + 1
    jsr aram_byte
    rep #$30
.a16
    lda f:PKG_X7
    tax
    lda f:sample_table + 5, x   ; the loop, from the start
    clc
    adc f:PKG_A
    sta temp
    sep #$20
.a8
    lda temp
    jsr aram_byte
    lda temp + 1
    jmp aram_byte
.endproc

; X7 of directory entry A: its row in `sample_table` times 7, in PKG_X7 and
; in X. For a music sample it is the entry itself; for a sound effect place,
; that of the effect noted down there —`FAR_EFFECT_IN`—, which goes after the
; music: SE_FIRST plus its number. That row can go past 255, so the
; arithmetic is sixteen bits.
.proc sample_row
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #SE_FIRST
    bcc from_music
    tax
    lda f:FAR_EFFECT_IN - SE_FIRST, x
    and #$00FF
    clc
    adc #SE_FIRST
from_music:
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp
    sta f:PKG_X7
    tax
    sep #$20
.a8
    rts
.endproc

; Finds a place for sample A, if it is not there: the first gap from
; ARAM_DATA on that does not overwrite any of the ones that already have a
; place. If it does not fit before ARAM_END, it is not uploaded and does not
; play. **It does not upload it**: it marks it with 3 in FAR_WANTS and
; `upload_placed` uploads it, once it is known the package fits; see
; `package_load_done`.
.proc place_sample
.a8
.i16
    sta f:PKG_S
    rep #$30
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_OF, x
    sep #$20
.a8
    beq no_is
    rts                         ; already there
no_is:
    lda f:PKG_S
    jsr sample_row
    rep #$30
.a16
    lda f:sample_table + 3, x
    sta f:PKG_LENGTH
    jsl se_msu_length           ; or what the one in the `.msu` measures: msu_effects.s
.a16
    ; The first gap where it fits: the occupied ones are walked in order,
    ; with PKG_A at the start of the gap being looked at.
    lda #ARAM_DATA
    sta f:PKG_A
    ldx #0
gap:
    txa
    cmp f:INT_N
    bcs to_final
    lda f:INT_INIT, x
    sec
    sbc f:PKG_A                 ; how much there is before this occupied one
    bcc continues               ; it starts before: no gap
    cmp f:PKG_LENGTH
    bcs here                    ; it fits
continues:
    lda f:INT_END, x
    cmp f:PKG_A
    bcc no_advances
    sta f:PKG_A                 ; the next gap starts after it
no_advances:
    inx
    inx
    bra gap
to_final:
    lda #ARAM_END
    sec
    sbc f:PKG_A
    bcc no_enters
    cmp f:PKG_LENGTH
    bcs here
no_enters:
    sep #$20
.a8
    lda #1
    sta f:PKG_PARTIAL           ; so the next `PlayBGM` completes it
    rts                         ; does not fit: does not play
.a16
here:
    ; It fits at PKG_A, before occupied X: room is made in the list.
    stx temp
    lda f:INT_N
    tax
run:
    cpx temp
    beq ran
    dex
    dex
    lda f:INT_INIT, x
    sta f:INT_INIT + 2, x
    lda f:INT_END, x
    sta f:INT_END + 2, x
    bra run
ran:
    lda f:PKG_A
    sta f:INT_INIT, x
    clc
    adc f:PKG_LENGTH
    sta f:INT_END, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    ; And where it goes is noted down, and that it still has to be uploaded.
    lda f:PKG_S
    and #$00FF
    tax
    sep #$20
.a8
    lda #3
    sta f:FAR_WANTS, x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:PKG_A
    sta f:FAR_ARAM_OF, x
    sep #$20
.a8
    rts
.endproc

; Uploads the samples `place_sample` marked with 3, each to its place, and
; writes their directory entry.
.proc upload_placed
.a8
.i16
    ldx #0
other:
    lda f:FAR_WANTS, x
    cmp #3
    bne continues
    phx
    txa
    sta f:PKG_S
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:FAR_ARAM_OF, x
    sta f:PKG_A
    sep #$20
.a8
    lda f:PKG_S
    jsr sample_row
    jsl se_msu_upload           ; a sound effect from the `.msu`: see msu_effects.s
    bcs upload
    jsr upload_sample
    jsr write_directory
upload:
    plx
continues:
    inx
    cpx #SAMPLES_N
    bcc other
    rts
.endproc

; The samples of song A: X at the start of its list in `song_samples`.
.proc song_list
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:song_samples, x
    tax
    sep #$20
.a8
    rts
.endproc

; Places the samples of song A.
.proc place_song
.a8
.i16
    jsr song_list
other:
    lda f:song_samples, x
    cmp #$FF
    beq ready
    phx
    jsr place_sample
    plx
    inx
    bra other
ready:
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
; is on the card until it asks for it. If it is missing, `msu_start` sets
; its bit in MSU_MISSING and `music_start` falls back to `song_ensure`, which
; sees the samples not uploaded and rebuilds the package with the song first:
; that time it freezes for however long the upload takes, and from then on
; this song is no longer skipped. For the same reason, the extra song of
; `package_load_done` does not go through here: it is the one being asked for.
;
; Saves A, X and Y: the package loops carry the index in X and `mark_song`
; the mark in Y.
.proc song_per_msu
.a8
.i16
    pha
    lda f:MSU_HAS
    beq no
    lda 1, s
    cmp #SONG_TOTAL
    bcs no
    phx
    phy
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:song_msu, x
    cmp #$FF
    beq no_xy                   ; it has no track
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    tax                         ; its byte in MSU_MISSING
    lda 5, s                    ; the song, behind Y and X
    and #$0007
    tay                         ; and its bit
    sep #$20
.a8
    lda f:MSU_MISSING, x
run:
    dey
    bmi ran
    lsr a
    bra run
ran:
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

; `mark_song` and `place_song` for the songs in the package list, which
; skip the ones that will play through the MSU-1.
.proc mark_package_song
.a8
.i16
    jsr song_per_msu
    bcs ready
    jmp mark_song
ready:
    rts
.endproc

.proc place_package_song
.a8
.i16
    jsr song_per_msu
    bcs ready
    jmp place_song
ready:
    rts
.endproc

; Silences the sound effects that are playing: their samples are about to
; move.
.proc se_mute
.a8
.i16
    php
    sei
    lda #0
    sta f:SE_FRAMES
    sta f:SE_FRAMES + 1
    sta f:SE_PENDING
    sta f:SE_LOWER
    sta f:SE2_FRAMES
    sta f:SE2_FRAMES + 1
    sta f:SE2_PENDING
    sta f:SE2_LOWER
    lda #1
    sta f:SE_RETURN             ; the music gets its voices back
    sta f:SE2_RETURN
    jsl se_extras_mute          ; and those of voices 0 to 5, in the same KOF
    ora #(SE_BIT | SE2_BIT)
    ldx #SE_KOF
    jsl f:dsp_pair_l
    plp
    rts
.endproc

; The package of `map_current`: see above. PKG_EXTRA is a song that goes
; before the map's —the one a `PlayBGM` asks for and was not there—, or $FF.
;
; The map comes from `map_current` and not from A since the index is sixteen
; bits: the three callers passed `map_current` in A, so no case was lost and
; the caller does not have to remember the width.
.proc package_load
.a8
.i16
    rep #$20
.a16
    lda map_current
    sta f:PKG_MAP
    sep #$20
.a8
    jmp package_load_done
.endproc

; And the package whose index is already written in `PKG_MAP`, which is how
; the battle comes in: its package is not any map's —it goes after all of
; them, see `BA_PACKAGE`— so it cannot come from `map_current`.
;
; It exists because there was a bug here that no git conflict flagged: when
; the index became sixteen bits, `package_load` stopped reading the package
; from A to read it from `map_current`, and `battle_audio_load` —which came
; from the other branch— kept passing it in A. The two branches merged clean
; because they touched different lines, and from then on the battle loaded
; the map's package: the battle song played with six samples not uploaded and
; the hit missed with sample 0. The two audio tests in `test_batalla.py`
; caught it.
.proc package_load_done
.a8
.i16
    lda f:APU_READY
    bne ready_apu
    rts                         ; at reset, before the driver runs
ready_apu:
    lda #0
    sta f:PKG_PARTIAL
    sta f:PKG_COMPACT
    jsr se_mute
    jsl se_msu_prepare          ; with the `.msu` sound effects, all are
                                ; uploaded again: see msu_effects.s
    ldx #0
clear:
    lda #0
    sta f:FAR_WANTS, x
    inx
    cpx #SAMPLES_N
    bcc clear
    ; The ones of the song playing do not move: 2.
    lda music_off
    bne no_fixed
    lda song_current
    cmp #SONG_TOTAL
    bcs no_fixed
    ldy #2
    jsr mark_song
no_fixed:
    ; The ones the package wants: 1, if they were not already 2. The extra's
    ; **even if it has a track**: if it is asked for, it is because it will
    ; play through the SPC700. The ones of the package's songs, not if they
    ; will play through the MSU-1: see `song_per_msu`.
    lda f:PKG_EXTRA
    cmp #$FF
    beq no_extra
    ldy #1
    jsr mark_song
no_extra:
    ; An exit song that its `PlayBGM` asks for goes alone: nothing else of the
    ; package stays. See `exit_extra`.
    jsr exit_extra
    bcc with_package
    jmp marked
with_package:
    ; A separate song that its `PlayBGM` asks for goes with the package's
    ; sound effects and without the other songs: see `extra_separate`.
    jsr package_list
    jsr extra_separate
    bcc songs_q
skip_q:
    lda f:packages, x
    cmp #$FF
    beq effects_q
    inx
    bra skip_q
songs_q:
    lda f:packages, x
    cmp #$FF
    beq effects_q
    phx
    ldy #1
    jsr mark_package_song
    plx
    inx
    bra songs_q
effects_q:
    inx
other_q:
    lda f:packages, x
    cmp #$FF
    beq exit_q
    phx
    jsr record_effect           ; from the sound effect's number to its place
    ldy #1
    jsr mark_sample
    plx
    inx
    bra other_q
exit_q:
    ; If what is marked so far —the song playing, the extra, the package's
    ; songs and its sound effects— does not fit in ARAM even empty,
    ; rebuilding from scratch cannot complete the package: it would only
    ; upload again, somewhere else, what was already there. 2 says so to
    ; `placed`, which then rebuilds only if one of the songs was left out.
    ; It is measured here, before the exit songs are marked, because those
    ; do not have to fit: see `from_exit`. The game's case is the `PlayBGM` of
    ; TF3_1_awe on map 3, which uploaded again what was there and more than
    ; doubled the time the picture stayed frozen and the music silent: see
    ; `test_el_paso_del_2_al_3_no_vuelve_a_subir_lo_que_estaba`.
    jsr wanted_fits
    bcs fits_q
    lda #2
    sta f:PKG_COMPACT
fits_q:
    ; And the exit songs, which are wanted anyway: if they were already there,
    ; they stay. With a separate song, not.
    jsr extra_separate
    bcs marked
    inx
other_s:
    lda f:packages, x
    cmp #$FF
    beq marked
    phx
    ldy #1
    jsr mark_package_song
    plx
    inx
    bra other_s
marked:
    ; The ones nobody wants are forgotten, and with the ones left the list of
    ; what is occupied is built, in order: it is where `place_sample` looks
    ; for the gaps.
    rep #$20
.a16
    lda #0
    sta f:INT_N
    sep #$20
.a8
    ldx #0
forget:
    lda f:FAR_WANTS, x
    phx
    rep #$20
.a16
    pha
    txa
    asl a
    tax
    pla
    and #$00FF
    bne wants
    sta f:FAR_ARAM_OF, x        ; nobody wants it: out
    bra next
wants:
    lda f:FAR_ARAM_OF, x
    beq next                    ; wanted but not there: the next step uploads it
    sta f:PKG_A
    txa
    lsr a
    sep #$20
.a8
    jsr sample_row
    rep #$20
.a16
    lda f:sample_table + 3, x
    sta f:PKG_LENGTH
    jsr sorted_interval
next:
    sep #$20
.a8
    plx
    inx
    cpx #SAMPLES_N
    bcc forget
    ; And the missing ones are placed, in order of priority: the extra song,
    ; the map's songs and its sound effects.
    lda f:PKG_EXTRA
    cmp #$FF
    beq no_extra2
    jsr place_song
no_extra2:
    jsr exit_extra
    bcc with_package2
    jmp placed
with_package2:
    jsr package_list
    jsr extra_separate
    bcc songs
skip:
    lda f:packages, x
    cmp #$FF
    beq effects
    inx
    bra skip
songs:
    lda f:packages, x
    cmp #$FF
    beq effects
    phx
    jsr place_package_song
    plx
    inx
    bra songs
effects:
    ; A song that did not fit, with a package that cannot fit whole: the
    ; rebuild does help, because it places the songs first and does not
    ; leave them out for a gap.
    lda f:PKG_PARTIAL
    beq songs_in
    lda f:PKG_COMPACT
    cmp #2
    bne songs_in
    lda #0
    sta f:PKG_COMPACT
songs_in:
    inx
other_effect:
    lda f:packages, x
    cmp #$FF
    beq from_exit
    phx
    jsr record_effect           ; already noted down: it only gives the place
    jsr place_sample
    plx
    inx
    bra other_effect
from_exit:
    ; The exit songs, after everything and **if there is room**: not fitting
    ; does not leave the package incomplete —their `PlayBGM` is not needed to
    ; complete it, nor to rebuild everything from scratch—, because their
    ; `PlayBGM` uploads them on their own. That is why PKG_PARTIAL is saved
    ; and restored around this. With a separate song none is uploaded.
    jsr extra_separate
    bcs placed
    inx
    lda f:PKG_PARTIAL
    pha
exit_other:
    lda f:packages, x
    cmp #$FF
    beq exit_set
    phx
    jsr place_package_song
    plx
    inx
    bra exit_other
exit_set:
    pla
    sta f:PKG_PARTIAL
placed:
    ; **If something did not fit, everything is placed again from scratch**,
    ; except the samples of the song playing, and only then uploaded. The
    ; ones the package wants and were already there stay where they were,
    ; which is what makes a map change that shares samples with the previous
    ; one cheap; but with the per-package budget each one fills almost all of
    ; ARAM, and those gaps were enough to leave out samples of a package that
    ; fits on its own: coming back from a battle, or from one map to another
    ; with the music silenced. That is why where each one goes is decided
    ; first and the upload is done at the end: redoing the whole upload would
    ; cost twice the frames. **Not when it cannot help** —PKG_COMPACT at 2,
    ; see `exit_q`—: the missing sound effects wait for the next `PlayBGM`.
    lda f:PKG_PARTIAL
    beq upload
    lda f:PKG_COMPACT
    bne upload                  ; 1: already redone, it is the song playing;
                                ; 2: it would not fit even so
    lda #1
    sta f:PKG_COMPACT
    lda #0
    sta f:PKG_PARTIAL
    ldx #0
compact:
    lda f:FAR_WANTS, x
    cmp #2
    beq still                   ; the ones of the song playing do not move
    cmp #0
    beq still                   ; and the ones nobody wants were already forgotten
    lda #1
    sta f:FAR_WANTS, x
    phx
    rep #$20
.a16
    txa
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_OF, x
    sep #$20
.a8
    plx
still:
    inx
    cpx #SAMPLES_N
    bcc compact
    jmp marked
upload:
    jsr upload_placed
    ; With an exit song uploaded alone, the rest of the package was let go:
    ; if the page does not leave the map, the next `PlayBGM` completes it. The
    ; same with a separate song, which goes up without the other songs.
    jsr exit_extra
    bcs partial
    jsr extra_separate
    bcc ready
partial:
    lda #1
    sta f:PKG_PARTIAL
ready:
    rts
.endproc

; C at 1 if PKG_EXTRA is one of the exit songs of PKG_MAP's package: the
; third list in `packages`. They are the ones the map starts only to leave
; —see `exit_songs` in rm2k-snes-audio's cartridge.rs—, and the game's case is
; `lufsorr` on map 3: it plays after the sequence of sound effects, so it has
; no reason to fit alongside them, and the converter gives it the rate of a
; song on its own. When its `PlayBGM` asks for it and it is not there, it is
; uploaded **alone**, letting go of the rest, and not the whole package with
; it first: that would not fit, and rebuilding it from scratch would be
; uploading the whole ARAM.
.proc exit_extra
.a8
.i16
    phy
    ldy #2
    jsr extra_in_list
    ply                         ; C survives the `ply`
    rts
.endproc

; C at 1 if PKG_EXTRA is one of the separate songs of PKG_MAP's package: the
; fourth list in `packages`. They are the ones in `[music] apart_themes` of
; the project file, and the game's case is `vswar` on 38 and 47: it plays in
; a scene, never at the same time as the map's other songs, and with them it
; did not fit at the rate it has on its own. When its `PlayBGM` asks for it
; and it is not there, it is uploaded **with the package's sound effects**
; —which can play in the meantime: the chests in the dump on 38—, and the
; other songs are let go until the next `PlayBGM`, as with an exit one. The
; converter counts on that: a separate song has to fit with those sound
; effects.
.proc extra_separate
.a8
.i16
    phy
    ldy #3
    jsr extra_in_list
    ply
    rts
.endproc

; C at 1 if PKG_EXTRA is in list Y of PKG_MAP's package: 2 the exit songs, 3
; the separate ones. Saves X, which is the index of the loops in
; `package_load_done`: `extra_separate` is asked in the middle of them. C
; survives the `plx`.
.proc extra_in_list
.a8
.i16
    phx
    lda f:PKG_EXTRA
    cmp #$FF
    beq no
    jsr package_list
jump:
    dey
    bmi look
other:
    lda f:packages, x
    inx
    cmp #$FF
    bne other
    bra jump
look:
    lda f:packages, x
    cmp #$FF
    beq no
    cmp f:PKG_EXTRA
    beq if
    inx
    bra look
if:
    plx
    sec
    rts
no:
    plx
    clc
    rts
.endproc

; X at the start of the list of PKG_MAP's package.
.proc package_list
.a8
.i16
    rep #$20
.a16
    lda f:PKG_MAP
    asl a
    tax
    lda f:packages, x
    tax
    sep #$20
.a8
    rts
.endproc

; Sound effect number A, noted down in its directory place: returns with the
; place in A, which is what `mark_sample` and `place_sample` use. If
; another sound effect was noted down there, that one is forgotten —its
; FAR_ARAM_OF to 0—, so its ARAM is freed and the new one is uploaded: with
; `se_mute` nothing is playing anymore. It is called with each sound effect
; of the package when marking and again when placing, and the second time
; changes nothing. Does not touch Y.
.proc record_effect
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:effect_place, x
    rep #$20
.a16
    and #$00FF
    tax                         ; the place, from zero
    sep #$20
.a8
    pla
    cmp f:FAR_EFFECT_IN, x
    beq recorded
    sta f:FAR_EFFECT_IN, x
    rep #$20
.a16
    txa
    clc
    adc #SE_FIRST
    asl a
    tax
    lda #0
    sta f:FAR_ARAM_OF, x        ; the one that was there goes
    txa
    lsr a                       ; X was the entry times two
    sep #$20
.a8
    rts
recorded:
    txa
    clc
    adc #SE_FIRST
    rts
.endproc

; Sample A, marked with Y in FAR_WANTS if it did not have something higher.
.proc mark_sample
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    tya
    cmp f:FAR_WANTS, x
    bcc ready
    sta f:FAR_WANTS, x
ready:
    rts
.endproc

; The samples of song A, marked with Y.
.proc mark_song
.a8
.i16
    phy
    jsr song_list
    ply
other:
    lda f:song_samples, x
    cmp #$FF
    beq ready
    phx
    jsr mark_sample
    plx
    inx
    bra other
ready:
    rts
.endproc

; C at 1 if the samples marked in FAR_WANTS, added up, fit between ARAM_DATA
; and ARAM_END: with the lengths `place_sample` gives them. What is left is
; carried on the stack, counting down, so a sum past sixteen bits is a
; borrow and not a wrap. Saves X, which is the index of the loops in
; `package_load_done`.
.proc wanted_fits
.a8
.i16
    phx
    rep #$20
.a16
    lda #(ARAM_END - ARAM_DATA)
    pha
    sep #$20
.a8
    ldx #0
other:
    lda f:FAR_WANTS, x
    beq next
    phx
    txa
    sta f:PKG_S
    jsr sample_row
    rep #$20
.a16
    lda f:sample_table + 3, x
    sta f:PKG_LENGTH
    jsl se_msu_length           ; PKG_S is what it reads
.a16
    lda 3, s                    ; what is left, behind X
    sec
    sbc f:PKG_LENGTH
    bcc over
    sta 3, s
    sep #$20
.a8
    plx
next:
    inx
    cpx #SAMPLES_N
    bcc other
    rep #$20
.a16
    pla
    sep #$20
.a8
    plx
    sec
    rts
.a16
over:
    pla                         ; the index
    pla                         ; and what was left
    sep #$20
.a8
    plx
    clc
    rts
.endproc

; Adds the interval [PKG_A, PKG_A + PKG_LENGTH) to the list of what is
; occupied, in order. 16-bit A.
.proc sorted_interval
.a16
.i16
    ldx #0
seek:
    txa
    cmp f:INT_N
    bcs place
    lda f:INT_INIT, x
    cmp f:PKG_A
    bcs place                   ; this one starts later: it goes in front
    inx
    inx
    bra seek
place:
    stx temp
    lda f:INT_N
    tax
run:
    cpx temp
    beq ran
    dex
    dex
    lda f:INT_INIT, x
    sta f:INT_INIT + 2, x
    lda f:INT_END, x
    sta f:INT_END + 2, x
    bra run
ran:
    lda f:PKG_A
    sta f:INT_INIT, x
    clc
    adc f:PKG_LENGTH
    sta f:INT_END, x
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
; playing: its samples do not move —see `package_load_done`— and what does
; not fit beside them is the last part of the package, the sound effects. A
; `PlayBGM` starts the song from zero and silences what was playing, so it is
; the first moment those samples can be let go: the package is loaded again
; with this song first, and only what was missing is uploaded.
;
; The game's case is the passage from map 2 to 3. What plays on map 2 is not
; a song of its own but `escape_newyork`, which comes from the opening on
; map 1; the elevator page jumps to 3 with it playing, and map 3 arrives
; without most of its sound effects. Right after, the same page starts
; TF3_1_awe, which is in no package: it goes up first, and what is still
; missing, because TF3 and the package do not fit together, waits for the
; `PlayBGM` of evilrhys, which completes it. None of the sound effects left
; out is asked for before that one.
.proc song_ensure
.a8
.i16
    sta temp + 1
    lda f:APU_READY
    beq ready
    lda temp + 1
    cmp #SONG_TOTAL
    bcs ready
    lda f:PKG_PARTIAL
    bne missing                 ; even if the song is missing nothing
    lda temp + 1                ; the song: `song_list` reads it from A
    jsr song_list
look:
    lda f:song_samples, x
    cmp #$FF
    beq ready                   ; they are all there
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_OF, x
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
    beq missing
    inx
    bra look
missing:
    php
    sei
    lda #1
    sta music_off
    lda #$FF
    ldx #SE_KOF
    jsl f:dsp_pair_l            ; all voices release
    plp
    lda temp + 1
    sta f:PKG_EXTRA
    jsr package_load
    lda #$FF
    sta f:PKG_EXTRA
ready:
    rts
.endproc

; The four ways in from bank 0, which reaches this bank only with `jsl`.
; Inside, the four are still called with `jsr`.
.proc aram_clear_l
.a8
.i16
    jsr aram_clear
    rtl
.endproc

.proc package_load_l
.a8
.i16
    jsr package_load
    rtl
.endproc

.proc package_load_done_l
.a8
.i16
    jsr package_load_done
    rtl
.endproc

.proc song_ensure_l
.a8
.i16
    jsr song_ensure
    rtl
.endproc
