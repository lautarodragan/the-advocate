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
    jsr palette_with_flash
ready:
    rts
.endproc

; Uploads the palette of character `flash_slot` with the tint and the flash
; applied. The flash colors come from slot X.
.proc palette_with_flash
.a8
.i16
    stx flash_slot_ofs          ; `flash_channel_table` uses X for the table
    lda flash_ev + 1, x
    sta flash_dest
    ldy #0                      ; the red of `pure` and of the working ones
    jsr flash_channel_table
    ldx flash_slot_ofs
    lda flash_ev + 2, x
    sta flash_dest
    ldy #32                     ; the green
    jsr flash_channel_table
    ldx flash_slot_ofs
    lda flash_ev + 3, x
    sta flash_dest
    ldy #64                     ; the blue
    jsr flash_channel_table

    ; The character's palette: sixteen two-byte colors, and in CGRAM the upper
    ; half starts at color 128.
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
    jsr build_palette

    ; The built palette is stored aside and uploaded in the next vblank, not
    ; here. Writing CGRAM in the middle of the frame leaves the top half of
    ; the screen with the old palette and the bottom with the new one: the
    ; sprite comes out at one level and the rest at another. It is the same
    ; reason the tint turns the screen off to apply itself. Each slot in its
    ; place in FAR_FLASH_PAL: see there.
    rep #$20
.a16
    lda flash_slot_ofs
    asl a
    asl a                       ; from eight bytes per slot to thirty-two
    tax
    sep #$20
.a8
    ldy #$0000
copy:
    lda pal_buf, y
    sta f:FAR_FLASH_PAL, x
    inx
    iny
    cpy #32
    bne copy
    ldx flash_slot_ofs
    lda tint_cgadd
    sta flash_ev + 7, x         ; and it is left waiting for the vblank

    ; And the tables go back to being the tint-only ones, which is what
    ; everything else expects. By copying, not rebuilding them: see
    ; `tint_tables`.
    jmp restore_tables
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

; Like `channel_table`, but blending toward the flash color first. Y carries
; which channel: 0, 32 or 64, which is both the offset into `pure` and into
; the working tables —`table_r`, `table_g` and `table_b` are contiguous, like
; the three of `pure`—; `flash_dest` the flash channel and `flash_alpha` how
; strong.
;
; The blend is easyrpg's put into five bits: `dest * a + channel * (255 - a)`
; over 255, with `a` the level times eight —`Flash::MakeColor` and the
; `PIXMAN_OP_OVER` of `BlendBlit`—. That the space is five bits and not eight
; is what makes the result not RM2k's but the one the same computation gives
; with five bits. It is a declared debt, and one of those that cannot be
; measured with a comparison: it needs an EasyRPG capture taken during a
; flash.
;
; **And it goes before the tint, not after.** easyrpg does it the other way
; round —`ToneBlit` and then `BlendBlit`— but there the tone belongs to the
; sprite and here the tint belongs to the whole screen. With a neutral tint it
; makes no difference; with a tint, the ROM does `tint(flash(c))` and RM2k
; `flash(tone(c))`. It is another declared debt of the same kind as the
; five-bit one, and the only place it shows is in a page that tints and
; flashes at the same time.
;
; **Saturation goes before this blend**: `build_palette` saturates the raw
; color, because saturation needs the three channels together and this table
; is one at a time. It is RM2k's order, where saturating is part of
; `ToneBlit`.
.proc flash_channel_table
.a8
.i16
    ; The blend of entry c is `(dest * a + c * (255 - a)) / 255`, and from one
    ; entry to the next the numerator always grows by the same amount:
    ; 255 - a. So the division is done once, for c = 0, and after that the
    ; remainder is carried: every time it goes past 254, 255 is subtracted and
    ; the quotient goes up by one. It gives the same quotient as dividing each
    ; time, because 255 - a does not reach 255 * 2 and the remainder cannot
    ; overflow twice in one step.
    ;
    ; Until 2026-09-26 each of the 96 entries did two products and a division
    ; with their waits, at about 150 cycles per entry: a character flash ate
    ; ~94 lines per frame, and on the terrace of map 32, added to a
    ; `FlashScreen`, the tick overran the frame. This way it is about 30
    ; cycles per entry.
    ;
    ; There is no need to cap the quotient at 31, as the standalone division
    ; did: the destination and the channel are five bits —the converter lets
    ; nothing else through, neither in the events nor in the battle
    ; animations—, so the blend does not overflow either.
    lda flash_dest
    sta WRMPYA
    lda flash_alpha
    sta WRMPYB                  ; the product takes eight cycles
    rep #$20
.a16
    tya
    clc
    adc #32
    sta pure_ofs                ; where this channel ends
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #255
    sta WRDIVB                  ; the quotient takes sixteen
    sec
    sbc flash_alpha
    sta flash_partial           ; the numerator's step, 255 - a
    nop
    nop
    nop
    nop
    rep #$20
.a16
    tya
    clc
    adc RDDIVL                  ; X: the quotient, in `pure`'s channel
    tax
    sep #$20
.a8
    ; The remainder is shifted up by one —from 1 to 255 instead of 0 to 254—
    ; so that "went past 254" is the carry of the eight-bit add; and when it
    ; goes past, subtracting 255 is keeping the byte and adding one. It lives
    ; in B while A reads `pure`.
    lda RDMPYL
    inc a
each:
    xba
    ; And the tint, which is already resolved: looking up the blended channel
    ; in the tint-only table **is** the hard light, and it takes a product and
    ; a division per entry out of the loop.
    lda pure, x
    sta table_r, y
    xba
    clc
    adc flash_partial
    bcc :+
    inc a
    inx
:   iny
    cpy pure_ofs
    bne each
    rts
.endproc
.assert table_g = table_r + 32 && table_b = table_r + 64, error, "flash_channel_table indexes all three from table_r"

