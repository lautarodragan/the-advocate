.segment "CODE"

; --- the screen tint --------------------------------------------------------
;
; RM2k scales each channel by a value from 0 to 200, with 100 as neutral. On a
; console with a palette that is not a screen effect but a transformation of
; the palette: the colors are scaled when uploaded and the background, which
; is 8 bits per pixel and addresses CGRAM directly, ends up tinted exactly.
;
; The computation is `i * value / 100` on integers. The hardware does both
; operations and they are exact, so the same computation in Python always
; gives the same result. An approximation with shifts would not do: the
; comparison is pixel by pixel.

; t[i] = i * value / 100 for i from 0 to 31, capped at 31. A = value, X = table.
.proc channel_table
.a8
.i16
    ; RM2k's tint does not scale the channel: it composes it with a *hard
    ; light*, which is `2ab` for the lower half and the screen
    ; `1-2(1-a)(1-b)` for the upper one. In RM2k units, with 100 neutral, the
    ; two halves are the same computation mirrored on both axes:
    ;
    ;     value <= 100:  channel * value / 100
    ;     value  > 100:  31 - (200 - value) * (31 - channel) / 100
    ;
    ; So the lower one is always built —which is what this code had been
    ; doing, meaning the tints that darken give exactly the same as before—
    ; and if the value brightens the finished table is mirrored:
    ; `t'[j] = 31 - t[31 - j]`.
    ;
    ; The upper half was wrong: it multiplied by two and capped at 31, and the
    ; difference from RM2k reached 31 of 31 with the value 200. Nobody caught
    ; it because no page that compiled brightened the screen; two of the eleven
    ; that saturation unlocks do, with (0, 120, 120).
    ;
    ; The mirror goes outside the loop on purpose. Doing it per entry —with
    ; the computation put in a subroutine— is ninety-six extra `jsr` and `rts`
    ; per tint, and that was enough for `apply_tint` to go from one frame
    ; to two: it showed as `snes-timer` losing one timer tick.
    sta temp                    ; the channel's value
    stx temp + 2                ; where the table goes
    stz tint_mirror
    cmp #(TINT_NEUTRAL + 1)
    bcc start
    lda #(2 * TINT_NEUTRAL)
    sec
    sbc temp
    sta temp                    ; 200 - value
    inc tint_mirror
start:
    ldy #$0000
each:
    tya
    sta WRMPYA
    lda temp
    sta WRMPYB                  ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; the dividend, in a single 16-bit write
    sep #$20
.a8
    lda #TINT_NEUTRAL
    sta WRDIVB                  ; starts: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc fits
    lda #31                     ; the channel has five bits and no more
fits:
    sta (temp + 2), y
    iny
    cpy #32
    bne each

    lda tint_mirror
    bne mirror
    rts

    ; The mirror goes in two passes, with a copy in between, because
    ; `(dp), y` addresses with Y and here two indices are needed at once: `j`
    ; and `31 - j`.
mirror:
    ldy #$0000
copy:
    lda (temp + 2), y
    sta tint_tmp, y
    iny
    cpy #32
    bne copy
    ldy #$0000
go_back:
    rep #$20
.a16
    tya
    eor #$001F                  ; with five bits, the complement is 31 - j
    tax
    sep #$20
.a8
    lda #31
    sec
    sbc tint_tmp, x
    sta (temp + 2), y
    iny
    cpy #32
    bne go_back
    rts
.endproc

; Reads a palette from ROM, tints it color by color and uploads it to CGRAM.
.proc tint_palette
.a8
.i16
    jsr build_palette
    jmp copy_to_shadow
.endproc
; Copies the palette just built in `pal_buf` to its place in `cgram_shadow`,
; and leaves the tint ready for `flush_video` to upload in the vblank.
.proc copy_to_shadow
.a8
.i16
    lda tint_cgadd
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per color
    tay
    sep #$20
.a8
    ldx #$0000
    cpx tint_end
    beq ready                   ; a palette with no colors
copy:
    lda pal_buf, x
    sta cgram_shadow, y
    inx
    iny
    cpx tint_end
    bne copy
ready:
    lda #1
    sta tint_ready
    rts
.endproc

; Builds the tinted palette in `pal_buf`, without uploading it.
.proc build_palette
.a8
.i16
    ; The count goes in Y and not in X: inside the loop X is the index into the
    ; three channel tables, so on getting here it holds the previous color's
    ; blue and not how many colors there are. Y does survive: it is the
    ; palette's cursor.
    rep #$20
.a16
    lda tint_count
    asl a                       ; two bytes per color
    sta tint_end
    sep #$20
.a8
    ; Neither `sta` nor `sep` touch Z, so this looks at the `asl`. A palette
    ; with no colors leaves without doing anything: the DMA below would
    ; measure zero bytes, which on the hardware is 64 KB, and would fill CGRAM
    ; with garbage.
    bne has_colors
    rts
has_colors:
    ldy #$0000
    ; With neutral saturation —which is almost always— the color needs neither
    ; the three channels together nor to leave sixteen bits, and there the
    ; short loop pays for itself. The numbers: `apply_tint` walks the map's
    ; colors, the upper layer's, those of the eight sprite palettes and the
    ; leader's —in CoreRetro II that is 151— and the long loop cost 205 cycles
    ; each. With that the iteration of the frame where the tint runs ended on
    ; line 224 of 262: **one** of margin. The first extra event that asked for
    ; a palette blew it, and the screen stayed untinted for a frame. Measured
    ; with the `count_lost` probe.
    lda tint_s
    cmp #TINT_NEUTRAL
    bne each_color
    rep #$20
.a16
    jmp each_color_neutral

each_color:
.a8
    cpy tint_end
    bne continues_color
    rts
continues_color:
    rep #$20
.a16
    lda [tint_ptr], y
    sta temp                    ; the original color, 15 bits
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
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_b
    sep #$20
.a8
    ; Saturation goes **before** color, which is `ToneBlit`'s order: there
    ; `saturation_tone` runs before `color_tone`. The other way round the gray
    ; would be computed on the already tinted color, and it is one of those a
    ; golden would not see: it would be taken with the error in and would
    ; defend it.
    ;
    ; And only when needed, same as easyrpg's `apply_sat`: it cannot be done
    ; channel by channel —it needs the gray of the whole color, that is, all
    ; three at once— so it does not go into the tables and it is the expensive
    ; part of all this.
    lda tint_s
    cmp #TINT_NEUTRAL
    beq no_saturate
    jsr saturate_color
no_saturate:
    ldx sat_r
    lda table_r, x
    sta temp + 2
    ldx sat_g
    lda table_g, x
    sta temp + 3
    ldx sat_b
    lda table_b, x
    rep #$20
.a16
    and #$001F
    xba                         ; blue goes in bits 10 to 14: eight places
    asl a                       ; come from the byte swap and the two missing
    asl a                       ; ones, two shifts. Ten `asl` in a row are
                                ; easy to miscount, and that is how five came out
    sta temp
    lda temp + 2
    and #$001F                  ; the red, without the green left next to it
    ora temp
    sta temp
    lda temp + 3
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a                       ; and the green in bits 5 to 9
    ora temp
    sta pal_buf, y

    iny
    iny
    sep #$20
.a8
    bra each_color

    ; The same color, without saturation and without leaving sixteen bits. The
    ; `lda table_x, x` also read the byte next to it —the three tables are
    ; contiguous and `pure` comes after—; the `and` throws it away.
each_color_neutral:
.a16
    cpy tint_end
    beq upload_neutral
    lda [tint_ptr], y
    sta temp
    and #$001F                  ; the red
    tax
    lda table_r, x
    and #$001F
    sta temp + 2
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; the green
    tax
    lda table_g, x
    and #$001F
    xba                         ; times eight
    lsr a
    lsr a
    lsr a                       ; minus three: to bits 5 to 9
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; the high byte down
    lsr a
    lsr a
    and #$001F                  ; the blue, which was in bits 10 to 14
    tax
    lda table_b, x
    and #$001F
    xba                         ; times eight
    asl a
    asl a                       ; and two more: to bits 10 to 14
    ora temp + 2
    sta pal_buf, y
    iny
    iny
    bra each_color_neutral
upload_neutral:
    sep #$20
.a8
upload:
    rts
.endproc

; --- the tint's saturation --------------------------------------------------
; Moves the three channels left in `sat_r`, `sat_g` and `sat_b` toward or away
; from gray. It is easyrpg's `saturation_tone` put into five bits and into
; RM2k units: there the factor comes from `gray = s * 128 / 100` and is
; `gray * 8` or `1024 + (gray - 128) * 16` over 1024, which worked out is
; `s / 100` below 100 and `(2s - 100) / 100` above. That is, 0 takes
; everything to gray, 100 does nothing and 200 triples the distance.
.proc saturate_color
.a8
.i16
    ; First the gray. The weights are those of Y' in Y'CbCr and add up to
    ; exactly 65536, so on five-bit channels they give a five-bit luminance:
    ; it is enough to keep the top byte of the 24-bit sum.
    stz sat_acc + 0
    stz sat_acc + 1
    stz sat_acc + 2
    lda sat_r
    sta weight_ch
    lda #<LIGHT_R
    sta weight_lo
    lda #>LIGHT_R
    sta weight_hi
    jsr add_weight
    lda sat_g
    sta weight_ch
    lda #<LIGHT_G
    sta weight_lo
    lda #>LIGHT_G
    sta weight_hi
    jsr add_weight
    lda sat_b
    sta weight_ch
    lda #<LIGHT_B
    sta weight_lo
    lda #>LIGHT_B
    sta weight_hi
    jsr add_weight
    lda sat_acc + 2             ; the sum divided by 65536
    sta sat_light

    lda sat_r
    jsr saturate_channel
    rep #$20
.a16
    and #$00FF
    sta sat_r
    sep #$20
.a8
    lda sat_g
    jsr saturate_channel
    rep #$20
.a16
    and #$00FF
    sta sat_g
    sep #$20
.a8
    lda sat_b
    jsr saturate_channel
    rep #$20
.a16
    and #$00FF
    sta sat_b
    sep #$20
.a8
    rts
.endproc

; `sat_acc += weight * weight_ch`, in 24 bits. The weight is sixteen bits and the
; console's unit multiplies eight at a time, so it goes in two products: the
; low one as is and the high one shifted a byte.
.proc add_weight
.a8
.i16
    lda weight_lo
    sta WRMPYA
    lda weight_ch
    sta WRMPYB                  ; starts: the product takes eight cycles
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda sat_acc + 2
    adc #0                      ; neither `sta` nor `sep` touch the carry
    sta sat_acc + 2

    lda weight_hi
    sta WRMPYA
    lda weight_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp                    ; the high product, which goes shifted eight bits
    and #$00FF
    xba                         ; its low byte, already in the upper place
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda temp + 1                ; and the product's high byte
    adc sat_acc + 2
    sta sat_acc + 2
    rts
.endproc

; A channel moved toward or away from `sat_light`. Enters and leaves in A.
.proc saturate_channel
.a8
.i16
    sta sat_ch
    lda tint_s
    cmp #(TINT_NEUTRAL + 1)
    bcs over

    ; Up to 100 it is an interpolation between the gray and the color, with
    ; both terms positive: it is the form the 65816 can do unsigned.
    ;
    ;     (luma * (100 - s) + channel * s) / 100
    lda #TINT_NEUTRAL
    sec
    sbc tint_s
    sta WRMPYA
    lda sat_light
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp + 2
    sep #$20
.a8
    lda tint_s
    sta WRMPYA
    lda sat_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc temp + 2
    sta WRDIVL
    sep #$20
.a8
    jmp divide_and_cap

    ; Above 100 the channel moves away from gray: `channel +- |channel - luma|
    ; * (s - 100) / 100`, with the sign kept apart so as not to have to do a
    ; signed subtraction. easyrpg does it with an arithmetic shift, which
    ; rounds down also with negatives; here it truncates. The difference is
    ; one value out of 31 and only when oversaturating.
over:
    lda tint_s
    sec
    sbc #TINT_NEUTRAL
    sta WRMPYA
    lda sat_ch
    cmp sat_light
    bcc low
    inc sat_upload_mark
    sec
    sbc sat_light
    bra multiply
low:
    stz sat_upload_mark
    lda sat_light
    sec
    sbc sat_ch
multiply:
    sta WRMPYB
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
    lda #TINT_NEUTRAL
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta temp + 2
    lda sat_upload_mark
    beq subtract
    lda sat_ch
    clc
    adc temp + 2
    cmp #32
    bcc ready_over
    lda #31
ready_over:
    rts
subtract:
    lda sat_ch
    sec
    sbc temp + 2
    bcs ready_over
    lda #0
    rts
.endproc

; The divisor and the wait, which are the same on both paths.
.proc divide_and_cap
.a8
.i16
    lda #TINT_NEUTRAL
    sta WRDIVB                  ; starts: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc fits
    lda #31
fits:
    rts
.endproc

; And uploads it from `pal_buf` to CGRAM entry `tint_cgadd`.

; The tint the event left, applied to the map's three palettes.
.proc apply_tint
.a8
.i16
    jsr tint_tables

    ; The background, from where it starts: below it are the screen's
    ; backdrop color and the window's palette, which **are not tinted**. That
    ; they stay out comes from where the range starts and not from
    ; remembering to skip them.
    ldx #M_PTR_MAP_CGRAM
    ldy #M_MAP_CGRAM
    lda #CGRAM_BASE
    jsr one_palette

    ; The upper layer, at whatever entry this map got. It has to be read from
    ; the record before loading X with the field, because the record is
    ; addressed precisely with X.
    ldx map_ofs
    lda f:map_table + M_ABOVE_FIRST, x
    pha
    ldx #M_PTR_ABOVE_CGRAM
    ldy #M_ABOVE_CGRAM
    pla
    jsr one_palette

    ; And the sprites, in the upper half of CGRAM.
    ldx #M_PTR_SPRITE_CGRAM
    ldy #M_SPRITE_CGRAM
    lda #128
    jsr one_palette

    ; On top, the leader's colors in its slot. The possible leaders share one,
    ; so the block that came from the cartridge carries those of the one the
    ; converter put first, and the one leading may be another. It goes
    ; **here** and not apart so that it is tinted with everything else:
    ; uploading them afterwards would leave the hero untinted, which is the
    ; inverse of the timer's error.
    lda hero_cgram + 2
    beq no_leader_pal           ; no leader with a graphic: nothing to upload
    rep #$20
.a16
    lda hero_cgram
    sta tint_ptr
    lda #OBJ_COLORS
    sta tint_count
    sep #$20
.a8
    lda hero_cgram + 2
    sta tint_ptr + 2
    lda hero_pal                ; it comes shifted one place, that is palette times two
    asl a
    asl a
    asl a                       ; and this takes it to palette times sixteen
    clc
    adc #129                    ; the sprite half, plus index 0 which is not
    sta tint_cgadd              ; drawn
    jsr tint_palette
no_leader_pal:

    ; The timer goes **untinted**, on top of what was just uploaded. In RM2k
    ; the tint is a property of the map's drawables —`Priority_Screen` is 90
    ; and `Priority_Timer` 140—, so the screen darkens and the digits do not.
    ; Here the tint is a CGRAM transformation and runs over everything it
    ; touches, so `upload_timer_pal` uploads the digits' entries again from
    ; ROM, and only those: they share the palette with a character.
    ;
    ; The message window is not tinted either, and without doing anything: it
    ; lives in the entries at the very bottom and the background starts at
    ; `CGRAM_BASE`, so it stays out of the range. It is what RM2k does —the
    ; tone applies to the map, the characters and the panorama, not to the
    ; window— and here it used to say it could not be done.
    ;
    ; None of this touched CGRAM: the three palettes were left in
    ; `cgram_shadow` and `upload_tint` uploads them, in the vblank.
    rts
.endproc

; The tint an event may have requested, with the screen off while it lasts.
;
; CGRAM does not accept writes with the PPU drawing, so this cannot run at
; just any moment. It was first tried inside `flush_video`, which runs in
; vblank, and it does not fit: `apply_tint` builds three channel tables of
; thirty-two entries and uploads three palettes by DMA. What overran the
; vblank landed with the PPU drawing, and the result was a half-done tint
; different each time —once the upper layer and a sprite, another time the
; background with the hero in black and the NPCs untinted—.
;
; And the suite does not catch this: snes9x **accepts** CGRAM writes with the
; PPU drawing and mednafen does not, so a broken tint can be green on the
; sixty comparisons and look wrong on the console. When something about CGRAM
; or VRAM works in here and not on the hardware, this is the first suspect.
;
; The other way out that was tried —turning the screen off in the middle of
; the frame, writing the tint and turning it back on— is another trap the
; emulator covers up: on the console it is black lines while the computation
; lasts, and on the emulator a frame tinted from the middle down. The screen
; shake saw it, being the first recipe that compares frame by frame.
;
; Turning the screen off is what the teleport already does —`load_requested`—
; for the same reason. It costs one black frame, which does not look out of
; place in RM2k either: the original engine fades to black on transitions.
.proc event_tint
.a8
.i16
    lda tint_pending
    beq nothing
    stz tint_pending
    jsr apply_tint              ; to the shadow; CGRAM is written in the vblank
nothing:
    rts
.endproc

; Uploads to CGRAM the three tinted palettes from `cgram_shadow`, and the
; untinted timer entries after them. It is for the vblank, or for
; `enter_map` with the screen off. The three DMAs together are 544 bytes at
; most.
.proc upload_tint
.a8
.i16
    stz tint_ready
    rep #$20
.a16
    lda #.loword(cgram_shadow)
    sta shadow_origin
    sep #$20
.a8
    jmp upload_palettes
.endproc
; The same from `pal_buf`, which is where the shadow sits with the screen
; flash on top. It takes the pending tint along, if there was one: the flash
; was already built on the freshly tinted shadow.
.proc upload_flash
.a8
.i16
    stz flash_ready
    stz tint_ready
    rep #$20
.a16
    lda #.loword(pal_buf)
    sta shadow_origin
    sep #$20
.a8
    jmp upload_palettes
.endproc
.proc upload_palettes
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_MAP_CGRAM, x
    sta tint_count
    sep #$20
.a8
    lda #CGRAM_BASE             ; the background starts shifted: below is the
    jsr dma_shadow              ; window, which is neither tinted nor re-uploaded
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ABOVE_CGRAM, x
    sta tint_count
    sep #$20
.a8
    lda f:map_table + M_ABOVE_FIRST, x
    jsr dma_shadow
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_SPRITE_CGRAM, x
    sta tint_count
    sep #$20
.a8
    lda #128
    jsr dma_shadow
    jmp upload_timer_pal
.endproc
; A DMA of `tint_count` colors from `shadow_origin` to CGRAM entry A.
.proc dma_shadow
.a8
.i16
    sta CGADD
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc shadow_origin
    sta A1T0L
    lda tint_count
    asl a                       ; two bytes per color
    beq nothing                 ; zero bytes would be 64 KB
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; the shadow lives in bank 0
    lda #$00
    sta DMAP0                   ; one register, byte at a time
    lda #$22
    sta BBAD0                   ; destination: CGDATA
    lda #$01
    sta MDMAEN
    rts
.a16
nothing:
    sep #$20
.a8
    rts
.endproc

; The timer digits' entries, untinted, on top of what was just uploaded.
; **Only those entries and not the whole palette**: since `034d721` the
; digits share the palette with a character —whichever has room for their two
; colors—, and that character is tinted. Uploading the whole palette left it
; untinted on any tinted screen, with the timer on or not: `release` carries
; the digits on every map.
;
; And only **with the timer on screen**. With no digits to draw those entries
; belong to the character alone and are tinted like the others; when it is
; turned on or off, `timer_repaint` asks for a re-upload. What stays unfixed
; is an entry the character and the digits share —black, almost always, and
; the save point's red—: while the timer is visible, that one stays untinted
; for both, because the digits win. The black only shows with a tint that
; brightens: darkening and desaturating leave it black.
;
; Which entries they are is said by `timer_mask`, one bit per entry and one
; word per map, which the converter emits.
.proc upload_timer_pal
.a8
.i16
    lda timer_visible
    bne visible
    rts
visible:
    rep #$20
.a16
    lda map_ofs
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; from 128 bytes per map to two
    tax
    lda f:timer_mask, x
    bne has
    sep #$20
.a8
    rts                         ; this map does not carry the digits
.a16
has:
    sta tint_count              ; the bits left: not `temp`, which in the
                                ; vblank may be busy
    ; The palette in ROM, and the CGRAM entry 0 it gets.
    ldx map_ofs
    lda f:map_table + M_TIMER_PAL, x
    and #$0007
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per palette
    clc
    adc f:map_table + M_PTR_SPRITE_CGRAM, x
    sta tint_ptr                ; the block fits whole in one bank: one
    sep #$20                    ; DMA uploads it
.a8
    lda f:map_table + M_PTR_SPRITE_CGRAM + 2, x
    sta tint_ptr + 2
    lda f:map_table + M_TIMER_PAL, x
    asl a
    asl a
    asl a
    asl a                       ; sixteen colors per palette
    clc
    adc #128
    sta tint_cgadd
    ldy #$0000
each:
    rep #$20
.a16
    lsr tint_count
    sep #$20
.a8
    bcc next
    lda tint_cgadd
    sta CGADD
    lda [tint_ptr], y
    sta CGDATA                  ; low byte first
    iny
    lda [tint_ptr], y
    sta CGDATA
    dey
next:
    inc tint_cgadd
    iny
    iny
    lda tint_count
    ora tint_count + 1
    bne each                    ; with no more bits, the rest is already tinted
    rts
.endproc

; The timer was just turned on or off, and its entries change owner: untinted
; if it is visible, tinted with the character if not. They are uploaded again
; in the next vblank, with everything else, from the shadow.
;
; With a neutral tint it is not needed: tinted or not they are the same color.
; And asking is not to save the DMA but the budget: the frame that uploads
; the tint uploads fewer poses —see `flush_video`—, and that would move
; whoever is walking right when a timer starts with no tint.
.proc timer_repaint
.a8
.i16
    lda tint_r
    cmp #TINT_NEUTRAL
    bne request
    lda tint_g
    cmp #TINT_NEUTRAL
    bne request
    lda tint_b
    cmp #TINT_NEUTRAL
    bne request
    lda tint_s
    cmp #TINT_NEUTRAL
    bne request
    rts
request:
    lda #1
    sta tint_ready
    rts
.endproc

; Tints and uploads one of the map's palettes. X = the pointer's field, Y = the
; count's field, A = which CGRAM entry it starts at.
.proc one_palette
.a8
.i16
    sta tint_cgadd
    stx temp
    sty temp + 2

    rep #$20
.a16
    lda temp
    clc
    adc map_ofs
    tax
    lda f:map_table, x
    sta tint_ptr
    sep #$20
.a8
    lda f:map_table + 2, x
    sta tint_ptr + 2

    rep #$20
.a16
    lda temp + 2
    clc
    adc map_ofs
    tax
    lda f:map_table, x
    sta tint_count
    sep #$20
.a8
    jsr tint_palette
    rts
.endproc
