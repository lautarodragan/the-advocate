; --- the common events' small pictures -----------------------------------------
;
; A common event compiled once, without a map —an automatic one and the
; bodies it calls, a parallel one— shows its small pictures from **one table
; the whole cartridge shares**, after the maps' in `picture_data`: its
; `OP_PICTURE` names the entry with bit 7 set, which no map's own table
; reaches, so `pic_entry` sends it here. Their tiles are not in any map's
; bank: they are in the cartridge once, by **sets** —what one common event
; shows with every body it calls—, and the set of a picture that is shown
; goes up to VRAM then, past the loaded map's bank, its message arrow and
; its gold window, a few blocks per vblank through `vram_drain`'s budget.
; Until it is all up the set's pictures are not drawn. One set at a time:
; showing another's takes down what the first had up, whose tiles it
; covers.
;
; **Where they go is each map's**: the tile and VRAM word past its bank and
; the first sprite palette from the top past its own pictures' and the
; arrow's, and **which sets fit there**, a bit each —the emission measured
; each one alone against what the map leaves—: `picture_common_maps`. A
; picture whose set does not fit the loaded map is not shown, as a map's
; that does not fit its bank. The entry keeps the base tile at 0 and the
; palette counted from the set's first; `picc_base` and `picc_show` add the
; map's. See `picture_common_section` in rm2k-snes-mapdata and
; rm2k-snes/convert/src/common_pictures.rs.
;
; The set in VRAM is forgotten on a map change —`pic_clear`— and goes up
; again after anything that reloads the sprite bank —a battle, the menu, a
; big picture—: `load_sprite` calls `picc_reload`.
;
; In `FAR3`: every door in is a `jsl`, from bank 1's picture code, from
; `vram_drain` and from `load_sprite`. The data bank is the caller's: what
; is in RAM goes with `f:`, and the registers with the data bank at 0.

.segment "FAR3"
.a8
.i16

.pushseg
.segment "FARBSS"
PICC_SET:   .res 1              ; the set in VRAM, or PIC_NONE
PICC_LEFT:  .res 2              ; its bytes still to go up
PICC_SRC:   .res 3              ; where they go up from
PICC_DEST:  .res 2              ; and to: a VRAM word
PICC_MASK:  .res 1              ; scratch: the sets that fit the map
.popseg

; The bytes of an entry of `picture_sets` and of `picture_common_maps`:
; `COMMON_SET_ENTRY` and `COMMON_MAP_ENTRY` in rm2k-snes-mapdata.
PICC_SET_ENTRY = 8
PICC_MAP_ENTRY = 8
; Where the entry keeps its set, and the bit of the byte after it that
; makes it a common one.
PICC_ENTRY_SET = 12
PICC_ENTRY_COMMON = $80
; A pose of `vram_drain`'s queue: a 32x32 block, the unit of its budget.
PICC_POSE_BYTES = 512

; Nothing in VRAM and nothing going up: from `pic_clear`, on every map
; change and on reset.
.proc picc_clear
.a8
.i16
    lda #PIC_NONE
    sta f:PICC_SET
    lda #0
    sta f:PICC_LEFT
    sta f:PICC_LEFT + 1
    rtl
.endproc

; X: the loaded map's entry in `picture_common_maps`. A8.
.proc picc_map_x
.a8
.i16
    rep #$20
.a16
    lda map_current
    asl a
    asl a
    asl a                       ; PICC_MAP_ENTRY bytes each
    tax
    sep #$20
.a8
    rts
.endproc

; X: the entry of common picture A8 —bit 7 set— in `picture_data`. A8.
.proc picc_entry_x
.a8
.i16
    rep #$20
.a16
    and #$007F
    asl a
    asl a
    asl a
    asl a                       ; PICTURE_ENTRY bytes each
    clc
    adc #PICTURE_COMMON
    tax
    sep #$20
.a8
    rts
.endproc

; `pic_entry` for a common picture: X its entry, the carry set if its set
; does not fit the loaded map —then it is not shown—. Enters with A8 the
; image. Keeps Y; leaves A at eight bits.
.proc picc_entry
.a8
.i16
.if ::PICTURE_SETS = 0
    sec
    rtl
.else
    cmp #PIC_NONE
    bne some
    sec                         ; no picture at all
    rtl
some:
    phy
    pha
    jsr picc_map_x
    lda f:picture_common_maps + 5, x
    sta f:PICC_MASK
    pla
    jsr picc_entry_x
    rep #$20
.a16
    lda f:picture_data + PICC_ENTRY_SET, x
    and #$00FF
    tay                         ; the set, as many shifts
    sep #$20
.a8
    lda f:PICC_MASK
shift:
    cpy #0
    beq tested
    lsr a
    dey
    bra shift
tested:
    eor #$01
    lsr a                       ; its bit, inverted, in the carry
    ply
    rtl
.endif
.endproc

; `OP_PICTURE` of a common picture, once placed: slot X's palette counted
; from the map's first for the sets, and its set up to VRAM if it is not
; there —taking down the pictures of the one that was—. Keeps X and Y.
.proc picc_show
.a8
.i16
    phy
    phx
    jsr picc_map_x
    lda f:picture_common_maps + 4, x
    plx
    phx
    clc
    adc f:PIC_PAL, x
    sta f:PIC_PAL, x
    lda f:PIC_IMG, x
    jsr picc_entry_x
    lda f:picture_data + PICC_ENTRY_SET, x
    cmp f:PICC_SET
    beq there
    sta f:PICC_SET
    jsr picc_drop_others
    jsr picc_start
there:
    plx
    ply
    rtl
.endproc

; Every slot showing a common picture of another set than PICC_SET: down.
.proc picc_drop_others
.a8
.i16
    ldy #0
each:
    tyx
    lda f:PIC_IMG, x
    cmp #PIC_NONE
    beq next
    cmp #$80
    bcc next                    ; the map's own
    jsr picc_entry_x
    lda f:picture_data + PICC_ENTRY_SET, x
    cmp f:PICC_SET
    beq next
    tyx
    lda #PIC_NONE
    sta f:PIC_IMG, x
    lda #0
    sta f:PIC_R_STEPS, x        ; and its ramp, as `pic_erase`
next:
    iny
    cpy #PIC_SLOTS
    bne each
    rts
.endproc

; PICC_SET's tiles, from its first, to go up to the loaded map's place for
; them.
.proc picc_start
.a8
.i16
    rep #$20
.a16
    lda f:PICC_SET
    and #$00FF
    asl a
    asl a
    asl a                       ; PICC_SET_ENTRY bytes each
    tax
    lda f:picture_sets + 0, x   ; the tiles' address
    sta f:PICC_SRC
    lda f:picture_sets + 3, x   ; their bytes
    sta f:PICC_LEFT
    sep #$20
.a8
    lda f:picture_sets + 2, x   ; and bank
    sta f:PICC_SRC + 2
    jsr picc_map_x
    rep #$20
.a16
    lda f:picture_common_maps + 2, x
    sta f:PICC_DEST
    sep #$20
.a8
    rts
.endproc

; `pic_draw`'s base tile for an entry: A16 the entry's own, X the entry.
; A common one's is the loaded map's for the sets, and the carry set says
; not to draw it while its set is not all up. Keeps X and Y.
.proc picc_base
.a16
.i16
    pha
    lda f:picture_data + PICC_ENTRY_SET, x
    bit #PICC_ENTRY_COMMON << 8
    bne common
    pla
    clc
    rtl
common:
    sep #$20
.a8
    cmp f:PICC_SET
    bne not_up
    rep #$20
.a16
    lda f:PICC_LEFT
    bne not_up
    pla
    phx
    sep #$20
.a8
    jsr picc_map_x
    rep #$20
.a16
    lda f:picture_common_maps + 0, x
    plx
    clc
    rtl
not_up:
    rep #$20
.a16
    pla
    sec
    rtl
.endproc

; After `load_sprite` uploads the map's bank over whatever was there: the
; set that was in VRAM, if any, goes up again.
.proc picc_reload
.a8
.i16
    lda f:PICC_SET
    cmp #PIC_NONE
    beq none
    phx
    phy
    jsr picc_start
    ply
    plx
none:
    rtl
.endproc

; From `vram_drain`, inside the vblank: a piece of the set going up, a
; pose's worth of bytes for each pose of the vblank's budget but one —the
; hero's—, which are taken from it. Nothing while the budget is that one.
.proc picc_drain
.a8
.i16
    rep #$20
.a16
    lda f:PICC_LEFT
    bne going
    sep #$20
.a8
    rtl
.a16
going:
    sep #$20
.a8
    lda f:vq_cap
    cmp #2
    bcs room
    rtl
room:
    dec a
    phb
    pha                         ; the poses it takes
    lda #1
    sta f:vq_cap
    lda #0
    pha
    plb                         ; the registers
    pla
    rep #$20
.a16
    and #$00FF
    xba
    asl a                       ; times PICC_POSE_BYTES
    cmp f:PICC_LEFT
    bcc fits
    lda f:PICC_LEFT
fits:
    sta DAS0L
    pha
    lda f:PICC_DEST
    sta VMADDL
    lda f:PICC_SRC
    sta A1T0L
    sep #$20
.a8
    lda f:PICC_SRC + 2
    sta A1B0
    lda #$80
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    ; What went up: the source on, the destination on by words, the rest
    ; down.
    lda f:PICC_SRC
    clc
    adc 1, s
    sta f:PICC_SRC
    lda 1, s
    lsr a
    clc
    adc f:PICC_DEST
    sta f:PICC_DEST
    lda f:PICC_LEFT
    sec
    sbc 1, s
    sta f:PICC_LEFT
    pla
    sep #$20
.a8
    plb
    rtl
.endproc
