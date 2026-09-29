.segment "CODE"

; --- the screen flash ---------------------------------------------------------
; One frame of the screen flash: easyrpg's `Flash::Update`, with the integer
; count that follows. The level is on a
; 256 scale and drops by `level / frames_left` each frame, with the hardware
; divider; on the last frame it falls to zero.
;
; RM2k draws the flash as a rectangle of the color with alpha on top of the
; composited screen. Here it is a CGRAM transform, like the tint: each channel
; of each color in the map's three palettes moves toward the flash's by
; `level / 31` of the way —`destellar_canal`—, and the result goes to
; `pal_buf`, which `flush_video` uploads in vblank instead of the shadow.
; The shadow stays as it is: it is the tinted map without the flash, and when
; the flash goes off it is uploaded again as is.
;
; Running the three palettes —two hundred-odd entries, at over a hundred
; cycles each— does not fit in a frame together with everything else: measured
; with `lost_frames`, one was lost per frame, and the rest of the scene
; ended up thirty frames behind. So it takes two frames:
; with an odd countdown the tables are built and the background and the upper
; layer are run; with an even countdown the sprites are run and everything is
; uploaded. What is seen changes every other frame. A tint that changes on the
; odd frame overwrites `pal_buf` with the freshly tinted palette, and besides
; cannot be uploaded without the flash; on that frame everything is done at
; once, and on the even one the background is redone.
;
; The message window and the timer do not get the flash, and they don't there
; either: `Priority_Screen` is 90 against 130 for the window and 140 for the
; timer.
.proc flash_tick
.a8
.i16
    rep #$20
.a16
    lda flash_level
    bne has
    sep #$20
.a8
    rts
.a16
has:
    sep #$20
.a8
    lda flash_remain
    beq off
    rep #$20
.a16
    lda flash_level
    sta WRDIVL                  ; the dividend, 16 bits
    sep #$20
.a8
    lda flash_remain
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    dec flash_remain            ; six cycles, and the nops still needed
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda flash_level
    sec
    sbc RDDIVL
    sta flash_level
    sep #$20
.a8
    lda flash_remain
    beq off
    and #$01
    beq phase_pair
    jsr flash_tables
    jsr flash_backdrop
    lda tint_ready
    beq ready                   ; the usual case: the sprites go next frame
    jsr flash_sprites
    bra upload
phase_pair:
    lda tint_ready
    beq sprites
    jsr flash_backdrop          ; the new tint overwrote the background already run
sprites:
    jsr flash_sprites
upload:
    lda #1
    sta flash_ready
ready:
    rts
off:
    ; It is over: the level falls to zero and the unflashed shadow goes back
    ; to CGRAM.
    stz flash_level
    stz flash_level + 1
    stz flash_remain
    lda #1
    sta tint_ready
    rts
.endproc

.proc flash_from_code
.a8
.i16
    lda [code_ptr], y           ; r
    sta flash_rgb
    iny
    lda [code_ptr], y           ; g
    sta flash_rgb + 1
    iny
    lda [code_ptr], y           ; b
    sta flash_rgb + 2
    iny
    lda [code_ptr], y           ; the strength, which is the starting level
    sta flash_level + 1
    stz flash_level
    iny
    lda [code_ptr], y           ; frames
    sta flash_remain
    iny
    rts
.endproc

; The three flash tables, one per channel: what each five-bit value becomes
; at this frame's level. They are bytes and not words already shifted into
; their place in the color, which would save `flash_range` the shifts:
; bank 0's RAM did not have room for the extra 96 bytes.
.proc flash_tables
.a8
.i16
    lda flash_level + 1         ; the integer part of the level, 0 to 31
    sta flash_tab_level
    rep #$20
.a16
    lda #.loword(flash_tab_r)
    sta temp
    sep #$20
.a8
    lda flash_rgb
    jsr one_flash_table
    rep #$20
.a16
    lda #.loword(flash_tab_g)
    sta temp
    sep #$20
.a8
    lda flash_rgb + 1
    jsr one_flash_table
    rep #$20
.a16
    lda #.loword(flash_tab_b)
    sta temp
    sep #$20
.a8
    lda flash_rgb + 2
    jmp one_flash_table
.endproc

; One table: A is the flash color's channel and `temp` points to the table.
; It is `destellar_canal`:
;
;     toward >= channel:  channel + (toward - channel) * level / 31
;     toward <  channel:  channel - (channel - toward) * level / 31
;
; The subtraction is always on the positive side, because the divider is
; unsigned.
;
; The products come from the level's row in `prod31_table`, and the distance
; to the target drops by one down to the target and then rises by one, so
; instead of computing each index it is walked: X goes down the row in the
; first stretch and up in the second. Until 2026-09-26 each entry compared,
; subtracted and called a routine that built the index, at about 70 cycles
; each; on the terrace of map 32 the odd flash frame went past a hundred
; lines and, together with a `FlashSprite`, ran over the frame. This way it
; is under 30.
;
; The target is five bits: the converter lets nothing else through, neither
; in `FlashScreen` nor in the battle animations.
.proc one_flash_table
.a8
.i16
    sta flash_tab_toward
    stz flash_tab_toward + 1
    lda flash_tab_level
    rep #$20
.a16
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    sta temp + 2                ; the level's row
    clc
    adc flash_tab_toward
    tax                         ; X: the row, at channel 0's distance
    lda flash_tab_toward
    inc a
    sta flash_tab_end           ; the first channel above the target
    sep #$20
.a8
    ldy #0
uploads:
    tya                         ; the channel, which is Y
    clc
    adc f:prod31_table, x
    sta (temp), y
    dex
    iny
    cpy flash_tab_end
    bne uploads
    cpy #32
    beq ready
    rep #$20
.a16
    lda temp + 2
    inc a
    tax                         ; and on the other side the distance starts at one
    sep #$20
.a8
low:
    tya
    sec
    sbc f:prod31_table, x
    sta (temp), y
    inx
    iny
    cpy #32
    bne low
ready:
    rts
.endproc


; The palettes of the background and the upper layer, from the shadow to
; `pal_buf` through the tables. Same entries and counts as `upload_tint`.
.proc flash_backdrop
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_MAP_CGRAM, x
    sta tint_count
    sep #$20
.a8
    ; From `CGRAM_BASE`, the same as `apply_tint` and `upload_palettes`: the
    ; background does not start at entry 0 but above the message window.
    ; This said 0, which was right until the window moved to palette 0 and the
    ; background shifted by nine entries —see commit 5015868, which fixed the
    ; other two places and **forgot this one**—. With 0, the background's last
    ; nine entries were not flashed: they were uploaded with whatever was left
    ; in `pal_buf`, so a few tiles did not light up and changed color on top
    ; of that. taro saw it on 2026-09-08 in the lightning of the opening —the
    ; yellow and black fences, and the edges of autotile 17 in ChipSet3—,
    ; which is the **first** `FlashScreen` this port ran. No test covered it:
    ; the `flash` test page flashes a sprite —`FlashSprite`—, never the
    ; screen, so nobody ran this path.
    lda #CGRAM_BASE
    jsr flash_range
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_ABOVE_CGRAM, x
    sta tint_count
    sep #$20
.a8
    lda f:map_table + M_ABOVE_FIRST, x
    jmp flash_range
.endproc

; And the sprites' ones.
.proc flash_sprites
.a8
.i16
    ldx map_ofs
    rep #$20
.a16
    lda f:map_table + M_SPRITE_CGRAM, x
    sta tint_count
    sep #$20
.a8
    lda #128
    jmp flash_range
.endproc

; `tint_count` colors from entry A: each one is split into its three channels,
; each channel goes through its table, and the three words are joined.
.proc flash_range
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per color
    tax
    lda tint_count
    asl a
    beq nothing
    sta flash_tab_end
    txa
    clc
    adc flash_tab_end
    sta flash_tab_end
color:
    lda cgram_shadow, x
    sta temp                    ; the color, and in temp + 2 what is being built
    and #$001F
    tay
    lda flash_tab_r, y          ; and the next byte, which gets masked
    and #$00FF
    sta temp + 2
    lda temp
    and #$03E0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    lda flash_tab_g, y
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; blue ends up in bits 2 to 6
    and #$007C
    lsr a
    lsr a
    tay
    lda flash_tab_b, y
    and #$00FF
    xba                         ; times 256, and two more make the ten bits
    asl a
    asl a
    ora temp + 2
    sta pal_buf, x
    inx
    inx
    cpx flash_tab_end
    bne color
nothing:
    sep #$20
.a8
    rts
.endproc

