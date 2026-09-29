.segment "CODE"

; --- saving and loading the game -------------------------------------------
;
; The cartridge carries battery-backed SRAM, with `SRAM_RANURAS` slots.
;
; What gets saved is said by `partida_tabla` and nothing else: pairs of
; (address in bank 0 WRAM, how many bytes), terminated by a zero length.
; Having it in a table and not in code is what keeps saving and loading from
; drifting apart —both walk it— and makes adding a field one line.
;
; The copy goes by DMA in both directions, and the WRAM window is what makes it
; possible: the B bus does not reach SRAM, but it does reach `WMDATA`, so the
; SRAM goes on the A-bus side and the WRAM on the other. Saving is a DMA from B
; to A —bit 7 of DMAP— and loading the same one reversed.
;
; The saved game starts at $0100 and not at $0000 because of the assembler:
; `ca65` picks direct page when the address fits in a byte, so
; with the saved game at $0000 an `lda SRAM_MAGIA, x` would read the direct
; page instead of the SRAM. Nobody uses the 256 bytes left below.
SRAM_BANCO = $70            ; in LoROM the SRAM shows at $70:0000

; **Four slots**, which is what taro asked for: RM2k opens a menu of fifteen
; and for this game that makes no sense. Many more would fit in the SRAM —it
; is 8 KB and a slot takes 165 bytes— so the number does not come from there
; but from how many can be shown and picked without the screen turning into a
; list.
SRAM_RANURAS = 4

; Each slot starts at a multiple of 256, which is what makes its offset the
; slot times 256 —an `xba`— and not a multiplication. It costs 91 bytes of
; padding per slot and there is SRAM to spare anyway: four slots end at $0500
; of the $2000 there are.
;
; **If `PARTIDA_BYTES` went past 250, this breaks silently**: the next slot
; starts overwriting the end of the previous one. Today it is 159, and it grows
; every time a field is added to the saved game —it already happened with the
; music—. The assembler cannot stop it, so it is guarded by
; `rom/pruebas/rpgmaker/test_guardar.py::test_las_cuatro_ranuras_entran_en_la_sram`.
SRAM_STRIDE = 2048

; And inside each slot, counting from its base. `SRAM_MAGIA` is still $0100
; and not $0000 for the usual reason: an operand that fits in a byte gets
; resolved by the assembler as direct page and would read WRAM. That bug cost
; the saved game not loading in mednafen, in Mesen or on the console.
SRAM_MAGIA = $0100          ; four bytes: the game's signature,
                            ; `SRAM_MAGIA_TEXTO`
SRAM_SUMA  = $0104          ; the sum of the saved game's bytes
; And which format it is: the magic and the sum say the slot is intact, not
; that it is from this build. Since the test cases travel in the ROM that gets
; played, the saved game changes shape every time a case names a variable or
; brings a troop, and one from another build **loaded corrupted** —with zeros
; behind it the sum still added up— or did not load, depending on what was in
; the SRAM. One that does not match is "no saved game": see
; `ranura_de_este_formato`.
;
; They are two words and neither is written by hand: the length comes from the
; same constants as `partida_tabla`, and the signature is computed by the
; converter from which variable, actor and skill goes in each slot
; —`firma_de_la_partida`—, which is what the length does not see.
SRAM_BYTES = $0106          ; PARTIDA_BYTES
SRAM_FIRMA = $0108          ; PARTIDA_FIRMA
SRAM_DATOS = $010A

; `partida_tabla` lives in RODATA —see "what does not need to live in bank 0"
; in `banco1.s`— and is read with `lda f:partida_tabla, x`.
; The same lengths, added up, so the saved game in the SRAM can be walked
; without looking at the table again. It is duplicated on purpose and **the
; ROM checks it**: `guardar_partida` compares against what `partida_copiar`
; ended with and panics if they differ. Duplicating a number nobody verifies
; is the kind of bug this repo has already paid for three times.
PARTIDA_BYTES = 2 + 2 + 1 + 2 + 2 + 2 + 6 + 3 + 1 + 5 + 3 + SWITCH_BYTES + 1 + 2 + VARIABLES_N * 2 + 1 + ITEMS_N + 1 + ACTORES_N * 10 + ACTORES_N * 2 + ACTORES_N * 2 + ACTORES_N + HAB_BYTES + EXP_K * 4
; Where the party lands inside the saved game: after the position, the
; direction, the cell and the map. The slot screen reads it from the SRAM to
; show the leader's name and the faces. It is the same sum as above, cut at the
; table's sixth line; if `partida_tabla` changes order, this changes with it.
PARTIDA_GRUPO   = 2 + 2 + 1 + 2 + 2 + 2   ; the map takes two since its
                                          ; index is sixteen bits
PARTIDA_GRUPO_N = PARTIDA_GRUPO + 4

; Sets the slot `guardar_partida` and `cargar_partida` will work with, and
; computes its offset. A brings the slot number.
;
; The offset is the slot times 2048, that is one `xba` and three `asl`: that
; is why `SRAM_STRIDE` is 2048 and not the exact length of a saved game.
; Multiplying by that length would need the hardware multiplier and eight
; cycles of waiting, to save a few bytes of an SRAM that has room to spare. It
; was 256 until the game's 81 variables went into the saved game, 512 until the
; inventory and 1024 until the equipment, which is 610 bytes more. With 2048
; four slots do not fit in 8 KB, and the cartridge declares 32 KB, which in
; LoROM is a whole bank of SRAM at $70.
.proc poner_ranura
.a8
.i16
    sta ranura
    rts
.endproc

; The slot's offset in the SRAM, in X. **It needs the normal data bank**: it
; reads `ranura`, which lives in WRAM.
;
; It is the slot times 2048, that is one `xba` and three `asl`: see
; `poner_ranura`.
.proc ranura_en_x
.a8
.i16
    rep #$20
.a16
    lda ranura
    and #$00FF
    xba                         ; times 256...
    asl a
    asl a
    asl a                       ; ...and times eight: SRAM_STRIDE, which is 2048
    tax
    sep #$20
.a8
    rts
.endproc

; Walks `partida_tabla` copying each stretch. A brings the DMAP: $80 saves
; —from the WRAM window to the SRAM— and $00 loads. Leaves in `temp` where the
; saved game ended inside the SRAM.
.proc partida_copiar
.a8
.i16
    sta DMAP0
    lda #$80
    sta BBAD0                   ; the other side is always WMDATA
    lda #SRAM_BANCO
    sta A1B0
    ldx #$0000                  ; where the table is at
    phx
    jsr ranura_en_x             ; normal data bank: here it still is
    rep #$20
.a16
    txa
    clc
    adc #SRAM_DATOS
    sta temp                    ; and where the SRAM is at, inside its slot
    sep #$20
.a8
    plx
    rep #$20
.a16
    sep #$20
.a8
otra:
    rep #$20
.a16
    lda f:partida_tabla + 2, x
    beq listo                   ; zero length: the table is over
    sta DAS0L
    lda temp
    sta A1T0L
    clc
    adc DAS0L
    sta temp
    lda f:partida_tabla, x
    sta WMADDL                  ; the WRAM, which is always in bank 0
    sep #$20
.a8
    stz WMADDH
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #4
    tax
    sep #$20
.a8
    bra otra
listo:
.a16
    sep #$20
.a8
    rts
.endproc

; The sum of the saved game's bytes in the SRAM, in `temp + 2`. It needs the
; data bank already set to the SRAM and **X with the slot's offset**: it does
; not read it from `ranura_ofs` because with the bank at $70 that would read
; the SRAM. Clobbers X.
;
; **The index goes from zero and the base supplies the address.** Written the
; other way round —`ldx #SRAM_DATOS` and then `lda $0000, x`— it looks the
; same and it is not: the operand `$0000` fits in a byte, so the assembler
; picks direct page just like ca65, and the loop ended up adding **low WRAM**
; instead of the SRAM. It is exactly the trap the `SRAM_MAGIA` comment warns
; about twenty lines above, committed on the line next to it.
;
; What kept it hidden is that the bug is **symmetric**: saving and loading
; both add up the same garbage, so as long as the WRAM does not change between
; one and the other the numbers match and the saved game loads. That happens
; at snes9x's startup, which always fills RAM with the same thing and calls
; `cargar_partida` microseconds after reset. With the WRAM of mednafen, of
; Mesen or of the real console, they do not match and the saved game never
; loads; and from the title menu neither, because by then the WRAM has already
; moved. Three reports from taro and an `xfail` were all this bug.
.proc partida_suma
.a8
.i16
    rep #$20
.a16
    lda #$0000
    sta temp + 2
    sep #$20
.a8
    ldy #$0000                  ; X already comes with the start of its slot
suma:
    lda SRAM_DATOS, x           ; the base does not fit in a byte: absolute,
                                ; and the data bank is the SRAM
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    inx
    iny                         ; X walks the SRAM and Y counts: the slot does
    cpy #PARTIDA_BYTES          ; not start at zero and the two are not the same
    bne suma
    rts
.endproc

; Saves the game. It is what `OP_SAVE` does, that is, the `OpenSaveMenu` of
; the Lashe City save point.
.proc guardar_partida
.a8
.i16
    ; **The `music_apagada` that gets saved is "is it playing?", and not the
    ; one in RAM.** With an MSU-1 track playing the SPC700 is silent on
    ; purpose and `music_apagada` is 1, so saved as is the game loaded mute:
    ; `music_boot_ya` reads it as "saved without music". It is set to zero
    ; while the copy lasts —the same question as `mapa_tema_callar`— and so
    ; the saved game does not say where it was playing from: on loading it,
    ; `music_start` picks the track or the SPC700 depending on whether there
    ; is an MSU-1. With interrupts disabled, because `irq_musica` would run the
    ; SPC700 stream on seeing it at zero. It is caught by
    ; `test_la_partida_guardada_vuelve_con_su_tema`.
    php
    sei
    lda music_apagada
    pha
    lda f:MSU_SUENA
    beq copiar
    stz music_apagada
copiar:
    lda #$80                    ; from the WRAM window to the SRAM
    jsr partida_copiar
    pla
    sta music_apagada
    plp
    ; What was copied has to be what `PARTIDA_BYTES` says. Otherwise the sum
    ; would look at another stretch and the slot would stay invalid forever
    ; without saying why.
    rep #$20
.a16
    sep #$20
.a8
    jsr ranura_en_x
    rep #$20
.a16
    txa
    clc
    adc #(SRAM_DATOS + PARTIDA_BYTES)
    cmp temp                    ; where the copy should have ended
    sep #$20
.a8
    beq cuadra
    jmp entrar_en_panico
cuadra:
    ; The magic and the sum are what say the slot is valid. The data bank moves
    ; to the SRAM: it is the only way to address it without a pointer on the
    ; direct page, which is full.
    ;
    ; The slot's offset is read **before** moving it, and from then on it
    ; travels in X: with the bank at $70, `lda ranura_ofs` would read the SRAM.
    jsr ranura_en_x
    phb
    lda #SRAM_BANCO
    pha
    plb
    phx
    jsr partida_suma            ; clobbers X
    plx
    rep #$20
.a16
    lda temp + 2
    sta SRAM_SUMA, x
    lda #PARTIDA_BYTES
    sta SRAM_BYTES, x
    lda #PARTIDA_FIRMA
    sta SRAM_FIRMA, x
    sep #$20
.a8
    lda #.strat(SRAM_MAGIA_TEXTO, 0)
    sta SRAM_MAGIA, x
    lda #.strat(SRAM_MAGIA_TEXTO, 1)
    sta SRAM_MAGIA + 1, x
    lda #.strat(SRAM_MAGIA_TEXTO, 2)
    sta SRAM_MAGIA + 2, x
    lda #.strat(SRAM_MAGIA_TEXTO, 3)
    sta SRAM_MAGIA + 3, x
    plb
    rts
.endproc

; If the SRAM has a saved game, loads it and returns A nonzero. It runs at
; startup, before loading the map: the switches decide which page is active in
; each event, so they have to be set before.
.proc cargar_partida
.a8
.i16
    jsr ranura_en_x             ; before moving the bank: see
                                ; `guardar_partida`
    phb
    lda #SRAM_BANCO
    pha
    plb
    jsr ranura_de_este_formato
    beq no_hay
    phx
    jsr partida_suma            ; clobbers X
    plx
    rep #$20
.a16
    lda temp + 2
    cmp SRAM_SUMA, x
    sep #$20
.a8
    bne no_hay
    plb
    lda #$00                    ; from the SRAM to the WRAM window
    jsr partida_copiar
    lda #$01
    rts
no_hay:
    plb
    lda #$FF
    sta ranura                  ; the sentinel: no saved game loaded
    lda #$00
    rts
.endproc

; Whether the slot holds a saved game **of this format**: the magic, the length
; and the signature. Returns A = 1 if so and 0 if not, with Z according to A
; —the final `lda #` leaves it—. It needs the data bank at the SRAM and X with
; the slot's offset, and does not touch X.
;
; It is used by the slot screen and by `cargar_partida`, and it is a single
; routine so both answer the same: a saved game from another build looks empty
; and does not load. If only the load rejected it, the screen would show the
; name and level read from a format that is not its own —garbage— and picking
; it would start from scratch without saying why.
;
; The magic is compared against immediates and not against a ROM table
; because with the data bank at the SRAM there is no way to read the ROM: the
; assembler has no long addressing and the direct page is full.
.proc ranura_de_este_formato
.a8
.i16
    lda SRAM_MAGIA, x
    cmp #.strat(SRAM_MAGIA_TEXTO, 0)
    bne no
    lda SRAM_MAGIA + 1, x
    cmp #.strat(SRAM_MAGIA_TEXTO, 1)
    bne no
    lda SRAM_MAGIA + 2, x
    cmp #.strat(SRAM_MAGIA_TEXTO, 2)
    bne no
    lda SRAM_MAGIA + 3, x
    cmp #.strat(SRAM_MAGIA_TEXTO, 3)
    bne no
    rep #$20
.a16
    lda SRAM_BYTES, x
    cmp #PARTIDA_BYTES
    bne no_16
    lda SRAM_FIRMA, x
    cmp #PARTIDA_FIRMA
    bne no_16
    sep #$20
.a8
    lda #$01
    rts
no_16:
.a16
    sep #$20
.a8
no:
    lda #$00
    rts
.endproc

; The cell where the saved game was left, set as the map's entry: it is how a
; door tells `cargar_mapa` where to place the hero. It is used by startup
; —when the ROM carries no title and the saved game loads by itself— and by
; the title menu when the player chooses to continue. It used to be written
; only in startup, and copying it to the menu would have been the second place
; to get it wrong.
.proc entrada_de_la_partida
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta entrada_x
    lda tile_y
    sta entrada_y
    sep #$20
.a8
    rts
.endproc
