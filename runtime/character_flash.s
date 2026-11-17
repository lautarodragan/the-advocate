.segment "CODE"

; --- the flashes ------------------------------------------------------------
;
; RM2k flashes a character by blending its drawing toward a color for a few
; frames. Here the drawing is a CGRAM palette, so flashing is uploading that
; palette blended, and turning it off is uploading it again as it was.
;
; The blend is done **before** the color reaches CGRAM, with the same channel
; tables as the screen tint: they are built with the tint and the flash
; together, the character's palette is uploaded, and they are built again as
; they were. That way the palette's path is a single one and there are no two
; places that can differ.

; The flash palettes, in far RAM: one per flash slot, thirty-two bytes each,
; and the vblank uploads all the ones left pending. It has to be one per
; slot: with a single one, two live flashes in the same frame overwrote each
; other, the last one's was uploaded, and the frame that turns off the first
; never reached CGRAM. They do not fit in the BSS. **They do not travel in
; the save**: they last one frame.
.pushseg
.segment "FARBSS"
FAR_FLASH_PAL: .res FLASH_MAX * 32
.popseg

; Stores the flash carried by the six operands that follow Y.
.proc flash_start
.a8
.i16
    ldx #$0000
seek:
    lda flash_ev, x
    cmp #FLASH_FREE
    beq set2
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc seek
    rts                         ; no slot: this flash is lost

set2:
    lda [code_ptr], y           ; the target
    sta flash_ev + 0, x
    iny
    lda [code_ptr], y
    sta flash_ev + 1, x         ; r
    iny
    lda [code_ptr], y
    sta flash_ev + 2, x         ; g
    iny
    lda [code_ptr], y
    sta flash_ev + 3, x         ; b
    iny
    lda [code_ptr], y
    sta flash_ev + 4, x         ; strength
    iny
    lda [code_ptr], y
    sta flash_ev + 5, x         ; how many frames
    stz flash_ev + 6, x         ; just starting
    rts
.endproc

; Which sprite palette the target in A is drawn with, or $FF if it is not
; drawn. The hero carries it in `hero_pal`, already shifted; an event, in the
; attribute byte of its row.
.proc target_palette
.a8
.i16
    cmp #$00
    bne from_event
    lda hero_pal
    lsr a                       ; hero_pal comes shifted one place
    and #$07
    rts
from_event:
    dec a
    jsr event_npc
    cpy #$FFFF
    bne has
    lda #$FF
    rts
has:
    lda npc_buf + 7, y
    lsr a
    and #$07
    rts
.endproc

; One frame of all the flashes.
.proc flashes_tick
.a8
.i16
    ldx #$0000
other:
    lda flash_ev, x
    cmp #FLASH_FREE
    beq next
    phx
    jsr one_flash
    plx
next:
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc other
    rts
.endproc

; One frame of the flash in slot X: advances, computes how strong it should be
; and uploads the palette. When it goes past the frames it lasts, the slot is
; freed: the previous frame already uploaded it with zero strength, that is,
; as it was.
.proc one_flash
.a8
.i16
    lda flash_ev + 6, x
    inc a
    sta flash_ev + 6, x
    cmp flash_ev + 5, x
    bcc still
    beq still                   ; the last frame goes with zero strength
    lda #FLASH_FREE
    sta flash_ev + 0, x
    rts

still:
    ; The strength: power * (frames - k) / frames, which is the closed form of
    ; the computation easyrpg does frame by frame.
    lda flash_ev + 5, x
    sec
    sbc flash_ev + 6, x
    sta WRMPYA
    lda flash_ev + 4, x
    sta WRMPYB                  ; the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda flash_ev + 5, x
    sta WRDIVB                  ; the quotient takes sixteen
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    asl a
    asl a
    asl a                       ; easyrpg's alpha is the strength times eight
    sta flash_alpha
    jmp paint_flash
.endproc

; Uploads the palette of the target of slot X with the strength already in
; `flash_alpha`.
.proc paint_flash
.a8
.i16
    lda flash_ev + 0, x
    jsr target_palette
    cmp #$FF
    beq ready                   ; not drawn: no palette to touch
    rep #$20
.a16
    and #$00FF
    sta flash_slot
    sep #$20
.a8
    ; In `FAR3` and without the tables: see `flash_direct`.
    jsl f:flash_direct
ready:
    rts
.endproc

; The tint's three channel tables, without flash, and their copy in `pure`.
;
; The copy exists because of the frame budget. `palette_with_flash` runs on
; every frame while a flash lasts and it used to end by rebuilding these
; three tables —ninety-six products and ninety-six divisions—; now
; `restore_tables` copies ninety-six bytes. And on the way
; `flash_channel_table` saves the tint computation per entry: it looks it up
; here.
.proc tint_tables
.a8
.i16
    lda tint_r
    ldx #.loword(pure)
    jsr channel_table
    lda tint_g
    ldx #.loword(pure) + 32
    jsr channel_table
    lda tint_b
    ldx #.loword(pure) + 64
    jsr channel_table
    ; fallthrough
.endproc

; The working tables, exactly as the tint-only ones were left.
.proc restore_tables
.a8
.i16
    ldx #$0000
copy:
    lda pure + 0, x
    sta table_r, x
    lda pure + 32, x
    sta table_g, x
    lda pure + 64, x
    sta table_b, x
    inx
    cpx #32
    bne copy
    rts
.endproc

; --- the flash without the tables, in FAR3 -----------------------------------
;
; `palette_with_flash` without the tables. It gives exactly what the tables
; give —each channel is `pure[(dest * a + c * (255 - a)) / 255]`, the
; quotient floored, which is what `flash_channel_table` leaves in entry c
; and `build_palette` looks up—, but only for the sixteen colors' 48
; channels, with the console's multiplier and divider, and the working
; tables are neither built nor restored. The tables did the 96 entries of
; the three channels, then the palette through them, then put the tint-only
; ones back: ~40 of the frame's 262 lines per flash and per frame, and a
; battle animation on an event flashes it ten frames, three times —"Hit
; A", on the lamps of map 11—. See tasks/abl-lazer-teeth-s-rock-lags.md.
;
; **With saturation too.** `build_palette` saturates the raw color before
; looking it up in the tables, so here c is the saturated channel: the
; sixteen colors saturated once, kept per flash slot in `FAR_FLASH_SAT`, and
; read instead of the ROM's. Saturating is the expensive part —three
; products and a division per channel, ~90 lines for a palette— and with
; the tables it ran on every frame of the flash: 124 lines, and the tick
; overran the frame for the whole of "Hit A". It is not rare: the opening
; leaves the screen at saturation 40 (maps 4 and 7, `TintScreen` 100, 100,
; 100, 40) and the tint survives the doors, so taro's game reached map 11
; like that and lost ~33 frames per stone where the harness, with a neutral
; tint, lost 2-7.
;
; In `FAR3` because bank 0 has no room and bank 1 had too little in ABL's
; MSU test cartridge; the low RAM and the registers with absolute
; addressing, as `sand_flash` does, because the data bank is the main
; loop's. Enters from `paint_flash` with X on the flash slot and
; `flash_slot`, `flash_alpha` set; does all of `palette_with_flash` —points
; the palette, builds it, leaves it in `FAR_FLASH_PAL` waiting for the
; vblank— and returns with carry at 1.
.pushseg
.segment "FARBSS"
; The saturated colors of each slot's palette, and what they were saturated
; from: `tint_s` and the palette's three-byte address, which is ROM. Equal
; key, same colors: a tint that changes the saturation mid-flash is seen.
FAR_FLASH_SAT: .res FLASH_MAX * 32
FAR_FLASH_SAT_KEY: .res FLASH_MAX * 4
.popseg
.pushseg
.segment "FAR3"

; One channel of the color in `temp`, already shifted down and masked in A
; (sixteen bits): blended toward the flash, looked up in `pure` at `table`,
; and put into `temp + 2` shifted left by `up`.
.macro FLASH_CHANNEL dest_times_a, table, up
    sep #$20
.a8
    sta WRMPYB                  ; c * (255 - a): eight cycles
    rep #$20
.a16
    lda dest_times_a
    clc
    adc RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #255
    sta WRDIVB                  ; over 255: sixteen cycles
    rep #$20
.a16
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL                  ; at most 31: the high byte is zero
    tax
    lda pure + table, x
    and #$001F
.if up = 5
    xba
    lsr a
    lsr a
    lsr a
.elseif up = 10
    xba
    asl a
    asl a
.endif
    ora temp + 2
    sta temp + 2
.endmacro

.proc flash_direct
.a8
.i16
    stx flash_slot_ofs
    ; The character's palette, pointed as `palette_with_flash` does: sixteen
    ; colors, and in CGRAM the upper half starts at color 128.
    rep #$20
.a16
    lda flash_slot
    asl a
    asl a
    asl a
    asl a
    asl a                       ; thirty-two bytes per palette
    sta temp
    ldx map_ofs
    lda f:map_table + M_PTR_SPRITE_CGRAM, x
    clc
    adc temp
    sta tint_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_SPRITE_CGRAM + 2, x
    sta tint_ptr + 2
    rep #$20
.a16
    lda #16
    sta tint_count
    lda flash_slot
    asl a
    asl a
    asl a
    asl a                       ; sixteen colors per palette
    clc
    adc #128
    sep #$20
.a8
    sta tint_cgadd
    lda tint_s
    cmp #TINT_NEUTRAL
    beq unsaturated
    jsr saturated_colors        ; `tint_ptr` to them
unsaturated:
    ; dest * a for each channel, once: `sat_r`, `sat_g` and `sat_b` are
    ; `build_palette`'s, which does not run on this path.
    ldx flash_slot_ofs
    lda flash_ev + 1, x
    sta WRMPYA
    lda flash_alpha
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta sat_r
    sep #$20
.a8
    lda flash_ev + 2, x
    sta WRMPYA
    lda flash_alpha
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta sat_g
    sep #$20
.a8
    lda flash_ev + 3, x
    sta WRMPYA
    lda flash_alpha
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta sat_b
    sep #$20
.a8
    ; And 255 - a, which stays in the multiplier for the 48 channels: the
    ; divider does not touch it.
    lda #255
    sec
    sbc flash_alpha
    sta WRMPYA
    rep #$20
.a16
    ldy #$0000
each:
    lda [tint_ptr], y
    sta temp                    ; the original color
    stz temp + 2
    and #$001F
    FLASH_CHANNEL sat_r, 0, 0
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    FLASH_CHANNEL sat_g, 32, 5
    lda temp
    xba
    lsr a
    lsr a
    and #$001F
    FLASH_CHANNEL sat_b, 64, 10
    lda temp + 2
    sta pal_buf, y
    iny
    iny
    cpy #32
    beq built
    jmp each
built:
    sep #$20
.a8
.ifdef sand_table
    jsl f:sand_flash            ; the sandstorm's grains do not flash
.endif
    ; To its place in FAR_FLASH_PAL, as `palette_with_flash` does.
    rep #$20
.a16
    lda flash_slot_ofs
    asl a
    asl a                       ; from eight bytes per slot to thirty-two
    tax
    ldy #$0000
copy:
    lda pal_buf, y
    sta f:FAR_FLASH_PAL, x
    inx
    inx
    iny
    iny
    cpy #32
    bne copy
    sep #$20
.a8
    ldx flash_slot_ofs
    lda tint_cgadd
    sta flash_ev + 7, x         ; and it is left waiting for the vblank
    sec
    rtl
.endproc

; The sixteen colors at `tint_ptr` saturated as `build_palette` does it,
; and `tint_ptr` pointed at them: from any slot's cache that holds them, and
; if none does, saturated into this slot's. Any slot's and not only its own
; because a "Hit A" flashes the same palette three times and each flash may
; take another slot: with only its own, each one saturated again, ~125 lines.
.proc saturated_colors
.a8
.i16
    ldx #(FLASH_MAX - 1) * 4
look:
    lda tint_s
    cmp f:FAR_FLASH_SAT_KEY, x
    bne other
    lda tint_ptr
    cmp f:FAR_FLASH_SAT_KEY + 1, x
    bne other
    lda tint_ptr + 1
    cmp f:FAR_FLASH_SAT_KEY + 2, x
    bne other
    lda tint_ptr + 2
    cmp f:FAR_FLASH_SAT_KEY + 3, x
    bne other
    jmp found
other:
    dex
    dex
    dex
    dex
    bpl look
    rep #$20
.a16
    lda flash_slot_ofs
    lsr a                       ; from eight bytes per slot to four
    tax
    sep #$20
.a8
    lda tint_s
    sta f:FAR_FLASH_SAT_KEY, x
    lda tint_ptr
    sta f:FAR_FLASH_SAT_KEY + 1, x
    lda tint_ptr + 1
    sta f:FAR_FLASH_SAT_KEY + 2, x
    lda tint_ptr + 2
    sta f:FAR_FLASH_SAT_KEY + 3, x
    rep #$20
.a16
    lda flash_slot_ofs
    asl a
    asl a                       ; from eight bytes per slot to thirty-two
    tax
    ldy #$0000
each:
    ; The channels as `build_palette` leaves them for `saturate_color`.
    lda [tint_ptr], y
    sta temp
    and #$001F
    sta sat_r
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_g
    lda temp
    xba
    lsr a
    lsr a
    and #$001F
    sta sat_b
    sep #$20
.a8
    phx
    phy
    CALL0 saturate_color        ; at most 31 each, the high bytes at zero
    ply
    plx
    rep #$20
.a16
    lda sat_g
    asl a
    asl a
    asl a
    asl a
    asl a
    ora sat_r
    sta temp
    lda sat_b
    xba
    asl a
    asl a                       ; to bits 10 to 14
    ora temp
    sta f:FAR_FLASH_SAT, x
    inx
    inx
    iny
    iny
    cpy #32
    bne each
    sep #$20
.a8
    rep #$20
.a16
    lda flash_slot_ofs
    lsr a                       ; back to the key's offset
    tax
    sep #$20
.a8
found:
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; from four bytes per key to thirty-two
    clc
    adc #.loword(FAR_FLASH_SAT)
    sta tint_ptr
    sep #$20
.a8
    lda #^FAR_FLASH_SAT
    sta tint_ptr + 2
    rts
.endproc
.popseg
