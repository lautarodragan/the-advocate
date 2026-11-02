; In `FAR3`, like the other bodies that came after bank 0 filled up: each
; door in is a `jsl` from bank 0, and what it reads of far RAM and of the
; cartridge goes with `f:`. Low RAM and the registers go plain: every door
; but `sand_set` comes with the data bank at 0, and `sand_set` only touches
; the zero page and far RAM.
.segment "FAR3"
.a8
.i16

; --- the sandstorm ----------------------------------------------------------------
;
; `WeatherEffects` type 4: `Game_Screen::UpdateSandstorm` and
; `Weather::DrawSandstorm` in easyrpg, which are two things, and each goes
; its own way on the console.
;
; **The overlay.** RM2k pastes a 16x16 tile of three sand colours over the
; whole screen twice —the fog's `DrawFogOverlay` with the sand's colours—,
; at opacities that together cover 34%, 49% or 77% of the screen by
; strength. It is drawn over the map, its upper layer and every character
; and under the flash, the pictures, the windows and the timer, and it takes
; the screen's tone. That is the set of colours the tint already transforms
; —see `apply_tint`—, so the overlay is one more step of the tint's tables:
; each channel `i` goes to `i * (1 - a) + tone(sand) * a`, which is the same
; blend done on the palette instead of on the screen. It costs nothing per
; frame, and the colour math stays free. What is not drawn is the grain:
; the three colours of the tile are a step apart at five bits, so the
; overlay goes as their average, flat and still. `sand_tint`.
;
; **The particles.** 128, 191 or 255 of them, 1x2 pixels, in screen space:
; a dead one is born with a ten percent chance per frame and lives eighty;
; it starts on a half ellipse below the top-centre and accelerates outward,
; so it leaves the screen in ten to fifteen frames. Simulating 255 every
; frame does not pay for itself when some forty are seen, so the ones on
; screen are particles in `SAND_SLOTS` slots, and the rest are a count:
; `sand_ring` says how many come back to life on each of the next
; `SAND_RING` frames, and `sand_pool` how many are waiting to be born. Of
; those, `pool * SAND_BORN / 256` are born each frame, rounded at random
; —the expected count of RM2k's ten percent each, without paying for a
; random number per particle—, and each takes a free slot until it leaves
; the screen or its life runs out. Each grain is one 8x8 object with its
; two pixels in the top-left corner, with priority 2 and at the end of the
; OAM, like the rain's drops. `sand_tick`, `sand_oam`.
;
; What is ours, besides the flat overlay:
;
; * **The grains are opaque.** RM2k's start at alpha 180 and grow; the
;   console has no transparency per object.
; * **At most `SAND_SLOTS` on screen.** One born with every slot taken is
;   not drawn; at the strongest it is 1.4% of them, simulated.
; * **A grain whose life runs out goes away.** RM2k leaves it drawn where it
;   stopped until it is born again; the ones still on screen at eighty
;   frames are the ones born almost still, under one in a thousand.
; * **When the weather starts, its particles become alive over forty frames,
;   always.** That is RM2k's first time —each particle starts with a random
;   life from 0 to 39— and it is a burst: up to the slots, and the rest are
;   born off the screen. RM2k's later times continue where the previous
;   sandstorm froze them.
; * **The grains are tinted but not covered.** Their four colours go in a
;   sprite palette that the converter reserves —see `sand_grains` in
;   Wally—, and after the tint they are written again with the tint alone:
;   `sand_colors`. A map without room for them in its palettes draws the
;   overlay without grains, and says so when converting.
;
; All of it assembles only in a cartridge where some page asks for a
; sandstorm: the converter emits `sand_table` then, with each map's grains
; —first tile, palette and first entry—, and the six doors in bank 0 go
; inside `.ifdef sand_table`. A cartridge without it is byte for byte what
; it was. The weather does not travel in the save, as with the rain.
.ifdef sand_table

SAND_SLOTS   = 48               ; RM2k's strongest has 38 on screen on average:
                                ; with 48, 1.4% of its grains find no slot,
                                ; simulated. Each costs `SAND_STRIDE` of far RAM
SAND_LIFE    = 80
SAND_RING    = SAND_LIFE + 1    ; born on frame f, it can be born again on f + 81
SAND_BORN    = 26               ; the ten percent, out of 256, as the rain's
SAND_SPREAD  = 40               ; the frames over which a new sandstorm comes alive
SAND_SEED    = $5A1D

; A slot, one record so that a single index walks it: the life left (0 for
; a free slot), the distance from the centre column and the height, the
; cosine's angle with the side in bit 7 —set, left of the centre— and the
; sine's, and the two speeds, 8.8 and never negative: the side says where.
; The accelerations are not kept: they are `sand_accel` at the two angles.
SAND_T       = 0
SAND_X       = 1
SAND_Y       = 2
SAND_COS     = 3
SAND_SIN     = 4
SAND_VX      = 5
SAND_VY      = 7
SAND_STRIDE  = 9

.pushseg
.segment "FARBSS"
sand_seed:   .res 2
sand_pool:   .res 1             ; the particles waiting to be born
sand_at:     .res 1             ; this frame's entry in `sand_ring`
sand_free:   .res 2             ; the slot where the search for a free one starts
sand_ring:   .res SAND_RING     ; how many come back to life on each frame
sand_slots:  .res SAND_STRIDE * SAND_SLOTS
sand_tinted: .res 8             ; the grains' four colours, with the tint alone
.popseg

; The overlay: how much of the screen is sand by strength, out of 256. It is
; `1 - (1 - back / 255) * (1 - front / 255)` with the two layers' opacities
; of `fog_opacity` —32 and 64, 64 and 80, 96 and 160—.
sand_cover:
    .byte 88, 124, 197
; And the sand's colour: the average of `sand_overlay_colors`, (230, 230,
; 170), at five bits. Its place in each table of `pure`.
SAND_R = 230 >> 3
SAND_G = 230 >> 3
SAND_B = 170 >> 3

; The grains' four colours —yellow, orange, red and white, `CreateSandParticle`—,
; at five bits, as each channel's place in `pure`. Wally reserves the same
; four, in this order: its `SAND_COLORS`.
sand_grain_ofs:
    .word 255 >> 3, 32 + (255 >> 3), 64 + (32 >> 3)
    .word 255 >> 3, 32 + (180 >> 3), 64 + (32 >> 3)
    .word 255 >> 3, 32 + (32 >> 3),  64 + (32 >> 3)
    .word 255 >> 3, 32 + (255 >> 3), 64 + (240 >> 3)

; How many particles by strength: `num_sand_particles`.
sand_counts:
    .byte 128, 191, 255

; `sin(2 pi j / 256)` for j from 0 to 64, which is all a quarter needs: RM2k
; takes its angles as a byte, from 1 to 127, and the cosine of one is the
; sine of `64 - j`. Times 256 and capped at 255, a byte.
sand_sine:
    .byte 0, 6, 13, 19, 25, 31, 38, 44, 50, 56, 62, 68, 74, 80, 86, 92
    .byte 98, 104, 109, 115, 121, 126, 132, 137, 142, 147, 152, 157, 162, 167, 172, 177
    .byte 181, 185, 190, 194, 198, 202, 206, 209, 213, 216, 220, 223, 226, 229, 231, 234
    .byte 237, 239, 241, 243, 245, 247, 248, 250, 251, 252, 253, 254, 255, 255, 255, 255
    .byte 255
; The accelerations at each `j`, 8.8, across and down in pairs: `2 * sin *
; 256 / 320` and `2 * sin * 224 / 240`, which is RM2k's `2 * cos` and `2 *
; sin` scaled from its 320x240 to the console's 256x224, as easyrpg scales
; them. Rounded from `sin(2 pi j / 256)` in floating point.
sand_accel:
    .word 0, 0, 10, 12, 20, 23, 30, 35, 40, 47, 50, 58, 60, 70, 70, 82
    .word 80, 93, 90, 105, 100, 116, 109, 127, 119, 139, 128, 150, 138, 161, 147, 172
    .word 157, 183, 166, 194, 175, 204, 184, 215, 193, 225, 202, 236, 211, 246, 219, 256
    .word 228, 265, 236, 275, 244, 285, 252, 294, 260, 303, 268, 312, 275, 321, 282, 330
    .word 290, 338, 297, 346, 303, 354, 310, 362, 317, 369, 323, 377, 329, 384, 335, 391
    .word 341, 397, 346, 404, 351, 410, 356, 416, 361, 421, 366, 427, 370, 432, 374, 437
    .word 378, 441, 382, 446, 386, 450, 389, 454, 392, 457, 395, 461, 397, 464, 400, 466
    .word 402, 469, 404, 471, 405, 473, 407, 474, 408, 476, 408, 477, 409, 477, 409, 478
    .word 410, 478

; `SetWeatherEffect` changed the weather: from `weather_set`, with the data
; bank wherever the bytecode is. The tint goes again —the overlay comes or
; goes with it—, and a new sandstorm starts with every slot free and its
; particles coming alive over `SAND_SPREAD` frames.
.proc sand_set
.a8
.i16
    lda #1
    sta tint_pending
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq start
    rtl
start:
    rep #$20
.a16
    lda #SAND_SEED
    sta f:sand_seed
    lda #0
    sta f:sand_free
    sep #$20
.a8
    sta f:sand_at
    sta f:sand_pool
    ldx #0
slots:
    sta f:sand_slots + SAND_T, x
    inx
    cpx #SAND_STRIDE * SAND_SLOTS
    bne slots
    ldx #0
ring:
    sta f:sand_ring, x
    inx
    cpx #SAND_RING
    bne ring
    rep #$20
.a16
    lda f:WEATHER_L + 1
    and #$00FF
    tax
    sep #$20
.a8
    lda f:sand_counts, x
    sta temp + 2
    ; One more in each of the first `SAND_SPREAD` entries, round and round.
    ldx #0
spread:
    lda f:sand_ring, x
    inc a
    sta f:sand_ring, x
    inx
    cpx #SAND_SPREAD
    bne counted
    ldx #0
counted:
    dec temp + 2
    bne spread
    rtl
.endproc

; The sandstorm's randomness, in `comp_mask`: the same xorshift as
; `rain_random`, on its own seed. Returns with the new number in A, sixteen
; bits; does not touch X or Y.
.proc sand_random
    rep #$20
.a16
    lda comp_mask
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor comp_mask
    sta comp_mask
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor comp_mask
    sta comp_mask
    xba
    and #$FF00
    eor comp_mask
    sta comp_mask
    rts
.endproc

; One frame of the sandstorm, after the rain's: the particles that come back
; to life, the grains that move, and the ones born. The message composer's
; scratch, as in `rain_tick`: `comp_mask` carries the randomness, `comp_col`
; how many are born and `comp_glyph` points at `sand_accel`.
.proc sand_tick
.a8
.i16
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq go
    rtl
go:
    rep #$20
.a16
    lda f:sand_seed
    sta comp_mask
    lda #.loword(sand_accel)
    sta comp_glyph
    sep #$20
.a8
    lda #.bankbyte(sand_accel)
    sta comp_glyph + 2
    lda f:sand_at
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:sand_ring, x          ; the ones whose eighty frames ended
    clc
    adc f:sand_pool
    sta f:sand_pool
    sta WRMPYA
    lda #SAND_BORN
    sta WRMPYB                  ; the product takes eight cycles: the random
    jsr sand_random             ; number covers them
.a16
    and #$00FF
    clc
    adc RDMPYL
    xba
    and #$00FF                  ; pool * 26 / 256, rounded at random
    sta comp_col
    sep #$20
.a8
    sta f:sand_ring, x          ; and they come back in `SAND_RING` frames
    lda f:sand_pool
    sec
    sbc comp_col
    sta f:sand_pool
    inx
    cpx #SAND_RING
    bne at_kept
    ldx #0
at_kept:
    txa
    sta f:sand_at

    ; The grains on screen: `x += int(vx)`, `vx += ax`, and the same down.
    ldx #0
move:
    lda f:sand_slots + SAND_T, x
    beq next
    dec a
    beq gone
    sta f:sand_slots + SAND_T, x
    lda f:sand_slots + SAND_VX + 1, x
    clc                         ; the whole pixels: the speed is never negative,
    adc f:sand_slots + SAND_X, x ; and the distance under 128
    cmp #128
    bcs gone                    ; off a side
    sta f:sand_slots + SAND_X, x
    lda f:sand_slots + SAND_VY + 1, x
    clc
    adc f:sand_slots + SAND_Y, x
    bcs gone
    cmp #224
    bcs gone                    ; off the bottom
    sta f:sand_slots + SAND_Y, x
    lda f:sand_slots + SAND_COS, x
    and #$7F
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    lda [comp_glyph], y         ; across
    clc
    adc f:sand_slots + SAND_VX, x
    sta f:sand_slots + SAND_VX, x
    lda f:sand_slots + SAND_SIN, x
    and #$00FF
    asl a
    asl a
    tay
    iny
    iny
    lda [comp_glyph], y         ; down
    clc
    adc f:sand_slots + SAND_VY, x
    sta f:sand_slots + SAND_VY, x
    sep #$20
.a8
    bra next
gone:
    lda #0
    sta f:sand_slots + SAND_T, x
next:
    rep #$20
.a16
    txa
    clc
    adc #SAND_STRIDE
    tax
    sep #$20
.a8
    cpx #SAND_STRIDE * SAND_SLOTS
    bne move

    ; And the ones born, each into a free slot. With none, the rest are born
    ; off the screen: they are already in the ring.
    rep #$20
.a16
born:
    lda comp_col
    beq done
    dec comp_col
    lda f:sand_free
    tax
    ldy #SAND_SLOTS
seek:
    lda f:sand_slots + SAND_T, x
    and #$00FF
    beq found
    txa
    clc
    adc #SAND_STRIDE
    tax
    cpx #SAND_STRIDE * SAND_SLOTS
    bne seek_on
    ldx #0
seek_on:
    dey
    bne seek
    bra done
found:
    jsr sand_born
.a16
    txa
    clc
    adc #SAND_STRIDE
    tax
    cpx #SAND_STRIDE * SAND_SLOTS
    bne free_kept
    ldx #0
free_kept:
    txa
    sta f:sand_free
    bra born
done:
    lda comp_mask
    sta f:sand_seed
    sep #$20
.a8
    rtl
.endproc

; A particle is born into the slot at X —`UpdateSandstorm`'s `else`
; branch—: two angles from 1 to 127, one for the cosine and **another** for
; the sine, as RM2k draws them, and a distance from 16 to 95. It starts at
; `(d * cos * 2, d * sin)` from the top-centre and accelerates along `(cos,
; sin)`; both are scaled from 320x240 to 256x224 as easyrpg does, with the
; same integer divisions. The side is kept apart and everything else goes
; positive, so that `int()` of RM2k's floats, which truncates toward zero,
; is a byte. One born past a side does not take the slot. Enters and leaves
; with a 16-bit A and does not lose X.
.proc sand_born
.a16
.i16
    stx comp_char
    stz comp_dup                ; the side: right
angle_cos:
    jsr sand_random
    and #$007F
    beq angle_cos
    sec
    sbc #64
    bcc right
    sta comp_base               ; past 64 the cosine is negative: left
    lda #$80
    sta comp_dup
    bra cos_done
right:
    eor #$FFFF
    inc a                       ; 64 - k
    sta comp_base
cos_done:
angle_sin:
    jsr sand_random
    and #$007F
    beq angle_sin
    sec
    sbc #64
    bpl sin_folded
    eor #$FFFF
    inc a
sin_folded:
    eor #$FFFF
    sec
    adc #64                     ; 64 - |k - 64|: the sine of k
    sta comp_dup + 2
    jsr sand_random
    sep #$20
.a8
    sta WRMPYA
    lda #80
    sta WRMPYB
    nop
    nop
    nop
    nop
    lda RDMPYL + 1
    clc
    adc #16
    sta comp_row                ; d, from 16 to 95

    ; Across: `int(d * cos * 2) * 256 / 320`.
    ldx comp_base
    lda f:sand_sine, x
    sta WRMPYA
    lda comp_row
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    asl a                       ; times two, and the top byte drops the
    xba                         ; sine's eight bits
    and #$00FF
    asl a
    asl a
    sta WRDIVL
    sep #$20
.a8
    lda #5
    sta WRDIVB                  ; times four fifths
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDDIVL
    cmp #128
    bcs past_the_side
    sta temp
    ; Down: `int(d * sin) * 224 / 240`.
    sep #$20
.a8
    ldx comp_dup + 2
    lda f:sand_sine, x
    sta WRMPYA
    lda comp_row
    sta WRMPYB
    nop
    nop
    nop
    nop
    lda RDMPYL + 1
    sta WRMPYA
    lda #14
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
    lda #15
    sta WRDIVB                  ; times fourteen fifteenths
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL                  ; under 94: a byte
    ldx comp_char
    sta f:sand_slots + SAND_Y, x
    lda temp
    sta f:sand_slots + SAND_X, x
    lda comp_base
    ora comp_dup
    sta f:sand_slots + SAND_COS, x
    lda comp_dup + 2
    sta f:sand_slots + SAND_SIN, x
    lda #SAND_LIFE
    sta f:sand_slots + SAND_T, x
    rep #$20
.a16
    lda #0
    sta f:sand_slots + SAND_VX, x
    sta f:sand_slots + SAND_VY, x
    rts
past_the_side:
    ldx comp_char
    rts
.endproc

; The grains in OAM, after the rain's drops: one 8x8 object each, priority 2,
; until the OAM fills up —any character covers them, as the drops—. Slot
; `i` draws colour `i mod 4`, as RM2k's particle `i`: its tile is one of the
; four in a 2x2 square from the map's first, `sand_table`'s. It writes the
; objects directly as `rain_oam` does, X always between 0 and 255.
; `comp_row` counts the slots.
.proc sand_oam
.a8
.i16
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq go
    rtl
go:
    rep #$20
.a16
    lda map_ofs
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; from 128 bytes per map to four
    tax
    lda f:sand_table, x
    bne has
    sep #$20
.a8
    rtl
.a16
has:
    sta comp_base               ; the first tile
    sep #$20
.a8
    ; vhoopppN: priority 2 and the grains' palette, a step up in mode 1, as
    ; the drops: see `rain_oam`.
    lda f:sand_table + 2, x
    and #$07
    asl a
    ora #$20
    sta comp_color
.ifdef paint_table
    lda f:PAINT_ON
    bne sand_step
.endif
    lda f:PANO_ON
    cmp #1
    bne sand_priority
.ifdef paint_table
sand_step:
.endif
    lda #$10
    clc
    adc comp_color
    sta comp_color
sand_priority:
    stz comp_row
    ldx #0
grain:
    lda f:sand_slots + SAND_T, x
    beq next
    rep #$20
.a16
    lda oam_slot
    cmp #128
    bcs full
    asl a
    asl a
    tay
    ; The tile: the slot's colour, `(i & 1) + 16 * (i >> 1 & 1)`.
    lda comp_row
    and #$0001
    sta comp_dup
    lda comp_row
    and #$0002
    asl a
    asl a
    asl a
    ora comp_dup
    clc
    adc comp_base
    sep #$20
.a8
    sta oam + 2, y
    xba
    and #$01
    ora comp_color
    sta oam + 3, y
    lda f:sand_slots + SAND_COS, x
    bmi left
    lda f:sand_slots + SAND_X, x
    clc
    adc #128
    bra across
left:
    lda #128
    sec
    sbc f:sand_slots + SAND_X, x
across:
    sta oam, y
    lda f:sand_slots + SAND_Y, x
    sta oam + 1, y
    ; Its two bits in the small table, both zero: `push_high`, and
    ; `store_high` when the byte is complete.
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    lda oam_slot
    and #$03
    cmp #$03
    bne no_byte
    phx
    lda high_acc
    ldx high_ptr
    sta oam_high, x
    stz high_acc
    rep #$20
.a16
    inc high_ptr
    plx
    bra counted
no_byte:
    rep #$20
.a16
counted:
    inc oam_slot
    sep #$20
.a8
next:
    inc comp_row
    rep #$20
.a16
    txa
    clc
    adc #SAND_STRIDE
    tax
    sep #$20
.a8
    cpx #SAND_STRIDE * SAND_SLOTS
    beq all
    jmp grain                   ; `bne` does not reach
all:
    rtl
.a16
full:
    sep #$20
.a8
    rtl
.endproc

; The overlay, into the tint's tables: from `apply_tint`, right after
; `tint_tables`, when `pure` holds the tint alone. First the grains' colours
; are taken from there, tinted and nothing more; then each entry `i` of the
; three tables goes to `(i * (256 - a) + tone(sand) * a + 128) / 256`, in
; `pure` and in the working ones. The tint's saturation, which does not go
; in the tables, is not applied to the sand's colour or the grains': with
; the saturation at 100, which is how the desert is, it is exact.
;
; In `pure` too because that is what a character's flash goes back to —see
; `palette_with_flash`—: in the working tables alone, a character that
; flashes would come out of the storm.
.proc sand_tint
.a8
.i16
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq go
    rtl
go:
    rep #$20
.a16
    stz temp + 2                ; where the colour goes in `sand_tinted`
    ldx #0
grain:
    lda f:sand_grain_ofs + 4, x
    tay
    lda pure, y                 ; the blue, to bits 10 to 14
    and #$001F
    xba
    asl a
    asl a
    sta temp
    lda f:sand_grain_ofs + 2, x
    tay
    lda pure, y                 ; the green, to bits 5 to 9
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp
    sta temp
    lda f:sand_grain_ofs, x
    tay
    lda pure, y                 ; and the red
    and #$001F
    ora temp
    phx
    ldx temp + 2
    sta f:sand_tinted, x
    inx
    inx
    stx temp + 2
    plx
    txa
    clc
    adc #6
    tax
    cpx #6 * 4
    bne grain

    lda f:WEATHER_L + 1
    and #$00FF
    tax
    sep #$20
.a8
    lda f:sand_cover, x
    sta temp                    ; a
    lda #0
    sec
    sbc temp
    sta temp + 1                ; 256 - a
    ; The sand's colour, tinted, times a, plus the half for rounding: one
    ; word per channel.
    lda pure + SAND_R
    sta WRMPYA
    lda temp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc #128
    sta comp_or01
    sep #$20
.a8
    lda pure + 32 + SAND_G
    sta WRMPYA
    lda temp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc #128
    sta comp_or01 + 2
    sep #$20
.a8
    lda pure + 64 + SAND_B
    sta WRMPYA
    lda temp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc #128
    sta comp_or23
    sep #$20
.a8
    ldx #0
entry:
    lda pure, x
    sta WRMPYA
    lda temp + 1
    sta WRMPYB                  ; the product cooks while the channel is chosen
    rep #$20
.a16
    cpx #64
    bcs blue
    cpx #32
    bcs green
    lda comp_or01
    bra add
green:
    lda comp_or01 + 2
    bra add
blue:
    lda comp_or23
add:
    clc
    adc RDMPYL
    sep #$20
.a8
    xba                         ; the top byte: over 256
    sta pure, x
    sta table_r, x
    inx
    cpx #96
    bne entry
    rtl
.endproc
.assert table_g = table_r + 32 && table_b = table_r + 64, error, "sand_tint indexes all three from table_r"

; The grains' colours with the tint alone over the palette a character's
; flash just built in `pal_buf`, if it is theirs: from `palette_with_flash`.
; In RM2k a character's flash does not reach the weather, and the flash's
; last frame rebuilds the palette from `pure`, which has the overlay: without
; this, the grains that share a palette with Zounds' flashing stones would
; stay pale after the first flash.
.proc sand_flash
.a8
.i16
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq go
    rtl
go:
    rep #$20
.a16
    lda map_ofs
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tax
    lda f:sand_table, x
    beq none
    lda f:sand_table + 2, x     ; the palette, and the first entry above it
    and #$00FF
    cmp flash_slot
    bne none
    lda f:sand_table + 3, x
    and #$00FF
    asl a
    tay
    ldx #0
copy:
    lda f:sand_tinted, x
    sta pal_buf, y
    iny
    iny
    inx
    inx
    cpx #8
    bne copy
none:
    sep #$20
.a8
    rtl
.endproc

; The grains' colours with the tint alone, over the ones `apply_tint` just
; covered with sand: from its end, before the vblank uploads the shadow.
.proc sand_colors
.a8
.i16
    lda f:WEATHER_L
    cmp #WEATHER_SAND
    beq go
    rtl
go:
    rep #$20
.a16
    lda map_ofs
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tax
    lda f:sand_table, x
    bne has
    sep #$20
.a8
    rtl
.a16
has:
    sep #$20
.a8
    lda f:sand_table + 2, x     ; the palette
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:sand_table + 3, x     ; and the first entry in it
    rep #$20
.a16
    and #$00FF
    clc
    adc #128                    ; the sprites' half of CGRAM
    asl a
    tay
    ldx #0
copy:
    lda f:sand_tinted, x
    sta cgram_shadow, y
    iny
    iny
    inx
    inx
    cpx #8
    bne copy
    sep #$20
.a8
    rtl
.endproc

.endif
