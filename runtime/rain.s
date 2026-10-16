.segment "CODE"

; --- the rain -------------------------------------------------------------------
;
; `Game_Screen::UpdateRain` and `Weather::DrawRain`, with RM2k's rule applied
; to the 256x224 screen: see OP_WEATHER in events.py, which has the why. The
; state lives in far RAM: the weather's type and strength, how many drops
; there are and the rain's randomness —its own xorshift, seeded every time
; the weather changes— in `FAR_WEATHER`, and three bytes per drop —x, y and its
; life— in `FAR_RAIN`. The x and the y are on the 256x256 surface stuck to
; the map, so one byte is enough and each frame's step wraps around by
; itself; on screen it is that minus the scroll. The weather does not travel
; in the save: after loading it does not rain.
;
; `rain_tick` and `rain_oam` run on every frame it rains and read with
; long addressing, which is one instruction per byte: with the WMADD window
; every drop paid for pointing at it.
.pushseg
.segment "FARBSS"
far_weather: .res 5
.popseg
FAR_WEATHER = .loword(far_weather)
.pushseg
.segment "FARBSS"
far_rain: .res 3 * RAIN_DROPS_MAX
.popseg
FAR_RAIN = .loword(far_rain)
WEATHER_L  = $7E0000 + FAR_WEATHER
RAIN_L     = $7E0000 + FAR_RAIN

; The weather at zero: no rain. On reset.
.proc weather_clear
.a8
.i16
    rep #$20
.a16
    lda #FAR_WEATHER
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #5
other:
    stz WMDATA
    dex
    bne other
    rts
.endproc

; `SetWeatherEffect`: `temp` the type, `temp + 1` the strength. If nothing
; changes it touches nothing; if it changes, the drops start off and the
; randomness goes back to its seed. It is called from the interpreter, with
; the data bank wherever the bytecode is: it only touches registers and low
; RAM.
.proc weather_set
.a8
.i16
    rep #$20
.a16
    lda #FAR_WEATHER
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    cmp temp
    bne changes
    lda WMDATA
    cmp temp + 1
    bne changes
    rts
changes:
    rep #$20
.a16
    lda #FAR_WEATHER
    sta WMADDL
    sep #$20
.a8
    lda temp
    sta WMDATA
    lda temp + 1
    sta WMDATA
    lda temp
    cmp #WEATHER_RAIN
    bne none
    lda temp + 1
    beq weak
    cmp #1
    beq half
    lda #RAIN_DROPS_2
    bra how_many
half:
    lda #RAIN_DROPS_1
    bra how_many
weak:
    lda #RAIN_DROPS_0
    bra how_many
none:
    lda #0
how_many:
    sta WMDATA
    lda #<RAIN_SEED
    sta WMDATA
    lda #>RAIN_SEED
    sta WMDATA
    ; All off.
    rep #$20
.a16
    lda #FAR_RAIN
    sta WMADDL
    sep #$20
.a8
    ldx #(RAIN_DROPS_MAX * 3)
off:
    stz WMDATA
    dex
    bne off
    rts
.endproc

; The rain's randomness, in `comp_mask`: the same xorshift as
; `events.next_random`. Returns with the new number in A, sixteen bits.
.proc rain_random
.a8
.i16
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

; One frame of rain —`Game_Screen::UpdateRain`—: a live drop falls and
; drifts, and one that ran out of life is born again wherever the randomness
; says. `comp_col` counts the drops and `comp_mask` carries the randomness;
; they belong to the message composer, which recomputes them on every
; character. X is the drop, three bytes at a time.
.proc rain_tick
.a8
.i16
    lda f:WEATHER_L + 2
    bne has
    rts
has:
    sta comp_col                ; how many
    rep #$20
.a16
    lda f:WEATHER_L + 3
    sta comp_mask
    sep #$20
.a8
    ldx #0
drop:
    lda f:RAIN_L + 2, x         ; its life
    beq off
    ; Alive: down four, one to the left, and one less life left.
    dec a
    sta f:RAIN_L + 2, x
    lda f:RAIN_L, x
    dec a
    sta f:RAIN_L, x
    lda f:RAIN_L + 1, x
    clc
    adc #4
    sta f:RAIN_L + 1, x
    bra next
off:
    ; It is born with a RAIN_BORN in 256 chance, at a random place.
    ; `rain_random` returns with a 16-bit A and does not touch X.
    jsr rain_random
    sep #$20
.a8
    cmp #RAIN_BORN
    bcs next
    lda #RAIN_LIFE
    sta f:RAIN_L + 2, x
    jsr rain_random
    sep #$20
.a8
    sta f:RAIN_L, x
    jsr rain_random
    sep #$20
.a8
    sta f:RAIN_L + 1, x
next:
    inx
    inx
    inx
    dec comp_col
    bne drop
    rep #$20
.a16
    lda comp_mask
    sta f:WEATHER_L + 3         ; the randomness, back in its place
    sep #$20
.a8
    rts
.endproc

; The drops in OAM: two 8x8 objects per live drop, with priority 2, at the
; very end —any character covers them— and until the OAM fills up. A map
; with no room for their colors has `M_RAIN_BASE` at zero and draws no
; rain. See `gotas_en_oam` in snes_expect.py, which has the rule for what is
; dropped.
;
; It does not go through `emit_object`, which for 150 objects was more than
; half a screen: a drop's X always stays between 0 and 255 —the ninth bit and
; the size are zero—, so it is written directly. X is the drop and Y the
; object.
.proc rain_oam
.a8
.i16
    ldx map_ofs
    lda f:map_table + M_RAIN_BASE, x
    ora f:map_table + M_RAIN_BASE + 1, x
    bne with_drops
    rts
with_drops:
    lda f:WEATHER_L + 2
    bne has
    rts
has:
    sta comp_col                ; how many
    rep #$20
.a16
    lda f:map_table + M_RAIN_BASE, x
    sta comp_base               ; the first tile
    sep #$20
.a8
    ; vhoopppN: priority 2 and the drops' palette; the ninth bit goes apart.
    lda f:map_table + M_RAIN_PAL, x
    and #$07
    asl a
    ora #$20
    sta comp_color
    ; A step up in mode 1, like every object: see `emit_object`.
.ifdef paint_table
    lda f:PAINT_ON
    bne rain_step
.endif
    lda f:PANO_ON
    cmp #1
    bne rain_priority
.ifdef paint_table
rain_step:
.endif
    lda #$10
    clc
    adc comp_color
    sta comp_color
rain_priority:
    stz comp_dup + 3
    ldx #0
drop:
    lda f:RAIN_L + 2, x
    bne alive
    jmp next
alive:
    ; The shade: 0 with nine or more life, 1 with five or more, 2 otherwise.
    cmp #9
    bcs tone0
    cmp #5
    bcs tone1
    lda #2
    bra tone
tone0:
    lda #0
    bra tone
tone1:
    lda #1
tone:
    sta comp_dup + 2
    ; On screen: minus the map's scroll, in eight bits.
    lda f:RAIN_L, x
    sec
    sbc screen_x
    sta comp_dup
    lda f:RAIN_L + 1, x
    sec
    sbc camera_y
    sta comp_dup + 1
    stz comp_row                ; the half: 0 top, 1 bottom
half:
    lda comp_dup + 1
    cmp #224
    bcc se_sees
    cmp #248
    bcs se_sees                 ; peeks in from the top
    jmp other_half
se_sees:
    rep #$20
.a16
    lda oam_slot
    cmp #128
    bcc remains_place
    sep #$20
.a8
    rts
.a16
remains_place:
    asl a
    asl a
    tay
    ; The tile: base + 16 * half + shade, nine bits.
    lda comp_row
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc comp_dup + 2
    clc
    adc comp_base
    sep #$20
.a8
    sta oam + 2, y
    xba
    and #$01
    ora comp_color
    sta oam + 3, y
    lda comp_dup
    sta oam, y
    lda comp_dup + 1
    sta oam + 1, y
    ; Its two bits in the small table, both zero: `push_high`.
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    lda oam_slot
    and #$03
    cmp #$03
    bne no_byte
    phx
    jsr store_high
    plx
no_byte:
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
other_half:
    lda comp_dup + 1
    clc
    adc #8
    sta comp_dup + 1
    inc comp_row
    lda comp_row
    cmp #2
    bcs next
    jmp half
next:
    inx
    inx
    inx
    dec comp_col
    beq ready
    jmp drop
ready:
    rts
.endproc


