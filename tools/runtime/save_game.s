.segment "CODE"

; --- saving and loading the game -------------------------------------------
;
; The cartridge carries battery-backed SRAM, with `SRAM_SLOTS` slots.
;
; What gets saved is said by `save_table` and nothing else: pairs of
; (address in bank 0 WRAM, how many bytes), terminated by a zero length.
; Having it in a table and not in code is what keeps saving and loading from
; drifting apart —both walk it— and makes adding a field one line.
;
; The copy goes by DMA in both directions, and the WRAM window is what makes it
; possible: the B bus does not reach SRAM, but it does reach `WMDATA`, so the
; SRAM goes on the A-bus side and the WRAM on the other. Saving is a DMA from B
; to A —bit 7 of DMAP— and loading the same one reversed.
;
; In ExHiROM the SRAM shows at $6000-$7FFF of banks $20-$3F and $A0-$BF, 8 KB
; in each, and **each bank shows the next 8 KB**: `$21:6000` is byte $2000 of
; the SRAM. Every constant below is the address the CPU uses, from
; `SRAM_WINDOW`; the test harness subtracts it to get the offset in the save
; file. Until 2026-10-01 it was LoROM, with the SRAM at $70:0000 and the saved
; game from $0100: at $0000 an `lda SRAM_MAGIC, x` would have been assembled
; as direct page.
SRAM_BANK = $20
SRAM_WINDOW = $6000
SRAM_SIZE = $8000

; **Four slots**, which is what taro asked for: RM2k opens a menu of fifteen
; and for this game that makes no sense. So the number does not come from the
; SRAM but from how many can be shown and picked without the screen turning
; into a list.
SRAM_SLOTS = 4

; **Each slot is a whole bank of the window**, 8 KB: slot N is bank
; `SRAM_BANK + N`, from `$6000`. See `slot_bank`.
;
; It is the fifth stride. It was 256 until the game's 81 variables went into
; the saved game, 512 until the inventory, 1024 until the equipment and 2048
; —four slots in one bank, 8 KB of SRAM— until 2026-10-04, when what the
; items that raise a parameter add to each actor did not fit: the saved game
; of the game this was written for was at 1983 of the 2038 bytes a slot of
; 2048 leaves.
; With a bank per slot, a slot's offset inside it is zero and nothing has to
; multiply; the price is 32 KB of SRAM instead of 8, which any cartridge and
; flash cart has.
;
; A saved game that went past the window would run into the ROM of the same
; bank, and saving would write nowhere: the `.assert` under `SRAM_DATA` stops
; the build, and the tests' `test_las_cuatro_ranuras_entran_en_la_sram`
; checks the same from outside.
SRAM_WINDOW_SIZE = $2000
SRAM_STRIDE = SRAM_WINDOW_SIZE

; And inside each slot, counting from its base, which is slot 0's. None of
; them fits in a byte, so the assembler cannot take one for direct page: in
; LoROM, with the SRAM from $0000, that bug cost the saved game not loading in
; mednafen, in Mesen or on the console.
SRAM_MAGIC = SRAM_WINDOW    ; four bytes: the game's signature,
                            ; `SRAM_MAGIC_TEXT`
SRAM_CHECKSUM = SRAM_WINDOW + 4 ; the sum of the saved game's bytes
; And which format it is: the magic and the sum say the slot is intact, not
; that it is from this build. Since the test cases travel in the ROM that gets
; played, the saved game changes shape every time a case names a variable or
; brings a troop, and one from another build **loaded corrupted** —with zeros
; behind it the sum still added up— or did not load, depending on what was in
; the SRAM. One that does not match is "no saved game": see
; `slot_of_this_format`.
;
; They are two words and neither is written by hand: the length comes from the
; same constants as `save_table`, and the signature is computed by the
; converter from which variable, actor and skill goes in each slot
; —`save_signature`—, which is what the length does not see.
SRAM_BYTES = SRAM_WINDOW + 6     ; SAVE_BYTES
SRAM_SIGNATURE = SRAM_WINDOW + 8 ; GAME_SIGNATURE
SRAM_DATA = SRAM_WINDOW + $0A
.assert SRAM_SLOTS * SRAM_STRIDE = SRAM_SIZE, error, "the slots are not the SRAM"
.assert SRAM_DATA + SAVE_BYTES <= SRAM_WINDOW + SRAM_WINDOW_SIZE, error, "a saved game does not fit in its slot"

; `save_table` lives in RODATA —see "what does not need to live in bank 0"
; in `bank1.s`— and is read with `lda f:save_table, x`.
; The same lengths, added up, so the saved game in the SRAM can be walked
; without looking at the table again. It is duplicated on purpose and **the
; ROM checks it**: `save_game` compares against what `save_copy`
; ended with and panics if they differ. Duplicating a number nobody verifies
; is the kind of bug this repo has already paid for three times.
SAVE_BYTES = 2 + 2 + 1 + 2 + 2 + 2 + 6 + 3 + 1 + 5 + 3 + SWITCH_BYTES + 1 + 2 + 1 + 1 + VARIABLES_N * 2 + 1 + ITEMS_N + 1 + 1 + ACTORS_N * 10 + ACTORS_N * 2 + ACTORS_N * 2 + ACTORS_N + SKILL_BYTES + EXP_K * GROWTH_BYTES + EXP_K * 4
; Where the party lands inside the saved game: after the position, the
; direction, the cell and the map. The slot screen reads it from the SRAM to
; show the leader's name and the faces. It is the same sum as above, cut at the
; table's sixth line; if `save_table` changes order, this changes with it.
SAVE_PARTY      = 2 + 2 + 1 + 2 + 2 + 2   ; the map takes two since its
                                          ; index is sixteen bits
SAVE_PARTY_N = SAVE_PARTY + 4

; Sets the slot `save_game` and `load_game` will work with. A brings the
; slot number.
.proc set_slot
.a8
.i16
    sta slot
    rts
.endproc

; The slot's bank of the SRAM window in A8, and in X its offset inside that
; bank, which is zero: see `SRAM_STRIDE`. The callers index with X as they
; did when four slots shared a bank, so a slot's fields are still
; `SRAM_MAGIC, x` and the like. `slot` is on the direct page, so any data
; bank will do.
.proc slot_bank
.a8
.i16
    ldx #$0000
    lda slot
    clc
    adc #SRAM_BANK
    rts
.endproc

; Walks `save_table` copying each stretch. A brings the DMAP: $80 saves
; —from the WRAM window to the SRAM— and $00 loads. Leaves in `temp` where the
; saved game ended inside the SRAM.
.proc save_copy
.a8
.i16
    sta DMAP0
    lda #$80
    sta BBAD0                   ; the other side is always WMDATA
    jsr slot_bank
    sta A1B0
    rep #$20
.a16
    lda #SRAM_DATA
    sta temp                    ; where the SRAM is at, inside its slot
    sep #$20
.a8
    ldx #$0000                  ; where the table is at
other:
    rep #$20
.a16
    lda f:save_table + 2, x
    beq ready                   ; zero length: the table is over
    sta DAS0L
    lda temp
    sta A1T0L
    clc
    adc DAS0L
    sta temp
    lda f:save_table, x
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
    bra other
ready:
.a16
    sep #$20
.a8
    rts
.endproc

; The sum of the saved game's bytes in the SRAM, in `temp + 2`. It needs the
; data bank already set to the SRAM and **X with the slot's offset**: it does
; not read it from `ranura_ofs`, which in LoROM —with the bank at $70— read
; the SRAM. Clobbers X.
;
; **The index goes from zero and the base supplies the address.** Written the
; other way round —`ldx #SRAM_DATA` and then `lda $0000, x`— it looks the
; same and it is not: the operand `$0000` fits in a byte, so the assembler
; picks direct page just like ca65, and the loop ended up adding **low WRAM**
; instead of the SRAM. It is exactly the trap the `SRAM_MAGIC` comment warns
; about twenty lines above, committed on the line next to it.
;
; What kept it hidden is that the bug is **symmetric**: saving and loading
; both add up the same garbage, so as long as the WRAM does not change between
; one and the other the numbers match and the saved game loads. That happens
; at snes9x's startup, which always fills RAM with the same thing and calls
; `load_game` microseconds after reset. With the WRAM of mednafen, of
; Mesen or of the real console, they do not match and the saved game never
; loads; and from the title menu neither, because by then the WRAM has already
; moved. Three reports from taro and an `xfail` were all this bug.
.proc save_checksum
.a8
.i16
    rep #$20
.a16
    lda #$0000
    sta temp + 2
    sep #$20
.a8
    ldy #$0000                  ; X already comes with the start of its slot
sum:
    lda SRAM_DATA, x            ; the base does not fit in a byte: absolute,
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
    cpy #SAVE_BYTES             ; not start at zero and the two are not the same
    bne sum
    rts
.endproc

; Saves the game. It is what `OP_SAVE` does, that is, the `OpenSaveMenu` of
; the Lashe City save point.
.proc save_game
.a8
.i16
    ; **The `music_off` that gets saved is "is it playing?", and not the
    ; one in RAM.** With an MSU-1 track playing the SPC700 is silent on
    ; purpose and `music_off` is 1, so saved as is the game loaded mute:
    ; `music_boot_done` reads it as "saved without music". It is set to zero
    ; while the copy lasts —the same question as `map_song_mute`— and so
    ; the saved game does not say where it was playing from: on loading it,
    ; `music_start` picks the track or the SPC700 depending on whether there
    ; is an MSU-1. With interrupts disabled, because `irq_music` would run the
    ; SPC700 stream on seeing it at zero. It is caught by
    ; `test_la_partida_guardada_vuelve_con_su_tema`.
    php
    sei
    lda music_off
    pha
    lda f:MSU_PLAYING
    beq copy
    stz music_off
copy:
    lda #$80                    ; from the WRAM window to the SRAM
    jsr save_copy
    pla
    sta music_off
    plp
    ; What was copied has to be what `SAVE_BYTES` says. Otherwise the sum
    ; would look at another stretch and the slot would stay invalid forever
    ; without saying why.
    rep #$20
.a16
    lda #(SRAM_DATA + SAVE_BYTES)
    cmp temp                    ; where the copy should have ended
    sep #$20
.a8
    beq square
    jmp enter_panic
square:
    ; The magic and the sum are what say the slot is valid. The data bank moves
    ; to the SRAM: it is the only way to address it without a pointer on the
    ; direct page, which is full.
    ;
    ; The slot's offset travels in X: in LoROM, with the bank at $70, `lda
    ; ranura_ofs` read the SRAM. In ExHiROM the SRAM's banks also have the
    ; low WRAM, and the offset is zero since each slot has its bank.
    jsr slot_bank
    phb
    pha
    plb
    phx
    jsr save_checksum           ; clobbers X
    plx
    rep #$20
.a16
    lda temp + 2
    sta SRAM_CHECKSUM, x
    lda #SAVE_BYTES
    sta SRAM_BYTES, x
    lda #GAME_SIGNATURE
    sta SRAM_SIGNATURE, x
    sep #$20
.a8
    lda #.strat(SRAM_MAGIC_TEXT, 0)
    sta SRAM_MAGIC, x
    lda #.strat(SRAM_MAGIC_TEXT, 1)
    sta SRAM_MAGIC + 1, x
    lda #.strat(SRAM_MAGIC_TEXT, 2)
    sta SRAM_MAGIC + 2, x
    lda #.strat(SRAM_MAGIC_TEXT, 3)
    sta SRAM_MAGIC + 3, x
    plb
    rts
.endproc

; If the SRAM has a saved game, loads it and returns A nonzero. It runs at
; startup, before loading the map: the switches decide which page is active in
; each event, so they have to be set before.
.proc load_game
.a8
.i16
    jsr slot_bank
    phb
    pha
    plb
    jsr slot_of_this_format
    beq none
    phx
    jsr save_checksum           ; clobbers X
    plx
    rep #$20
.a16
    lda temp + 2
    cmp SRAM_CHECKSUM, x
    sep #$20
.a8
    bne none
    plb
    lda #$00                    ; from the SRAM to the WRAM window
    jsr save_copy
    lda #$01
    rts
none:
    plb
    lda #$FF
    sta slot                    ; the sentinel: no saved game loaded
    lda #$00
    rts
.endproc

; Whether the slot holds a saved game **of this format**: the magic, the length
; and the signature. Returns A = 1 if so and 0 if not, with Z according to A
; —the final `lda #` leaves it—. It needs the data bank at the SRAM and X with
; the slot's offset, and does not touch X.
;
; It is used by the slot screen and by `load_game`, and it is a single
; routine so both answer the same: a saved game from another build looks empty
; and does not load. If only the load rejected it, the screen would show the
; name and level read from a format that is not its own —garbage— and picking
; it would start from scratch without saying why.
;
; The magic is compared against immediates and not against a ROM table
; because with the data bank at the SRAM there is no way to read the ROM: the
; assembler has no long addressing and the direct page is full.
.proc slot_of_this_format
.a8
.i16
    lda SRAM_MAGIC, x
    cmp #.strat(SRAM_MAGIC_TEXT, 0)
    bne no
    lda SRAM_MAGIC + 1, x
    cmp #.strat(SRAM_MAGIC_TEXT, 1)
    bne no
    lda SRAM_MAGIC + 2, x
    cmp #.strat(SRAM_MAGIC_TEXT, 2)
    bne no
    lda SRAM_MAGIC + 3, x
    cmp #.strat(SRAM_MAGIC_TEXT, 3)
    bne no
    rep #$20
.a16
    lda SRAM_BYTES, x
    cmp #SAVE_BYTES
    bne no_16
    lda SRAM_SIGNATURE, x
    cmp #GAME_SIGNATURE
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
; door tells `enter_map` where to place the hero. It is used by startup
; —when the ROM carries no title and the saved game loads by itself— and by
; the title menu when the player chooses to continue. It used to be written
; only in startup, and copying it to the menu would have been the second place
; to get it wrong.
.proc save_entry
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta entry_x
    lda tile_y
    sta entry_y
    sep #$20
.a8
    rts
.endproc
