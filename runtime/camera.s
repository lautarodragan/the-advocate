.segment "CODE"

; --- the camera panned away from the hero ----------------------------------
; `Game_Player::UpdatePan`: each axis approaches its destination by
; the step `OP_PAN` carries, in 1/16 px, without overshooting. And along the way it
; is brought down to whole pixels, which is what `follow_camera` adds: the
; division is **floored** and signed, which is what `Spriteset_Map` does by
; dividing `GetDisplayX()` by 16.
;
; It is stored in pixels instead of dividing on every use because
; `follow_camera` runs once per frame and so does this, but here the
; arithmetic is done only once per axis.
.proc pan_tick
.a8
.i16
    rep #$20
.a16
    ldx #0                      ; the axis: 0 is x, 2 is y
other_axis:
    lda pan_dest_x, x
    sec
    sbc pan_x, x
    beq in_place                ; already there
    bpl toward_ahead
    ; Remaining distance is backwards: subtract the step, or what is left if
    ; that is less.
    eor #$FFFF
    inc a                       ; the absolute value of what is left
    cmp pan_step
    bcc short
    lda pan_step
short:
    eor #$FFFF
    inc a                       ; and back to signed
    bra add
toward_ahead:
    cmp pan_step
    bcc add
    lda pan_step
add:
    clc
    adc pan_x, x
    sta pan_x, x
in_place:
    ; To pixels: four arithmetic shifts, which keep the sign.
    lda pan_x, x
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    sta pan_px, x
    inx
    inx
    cpx #4
    bcc other_axis
    sep #$20
.a8
    rts
.endproc

; How many frames the page that asked for the pan waits: what the axis with
; the most left to go still needs, divided by the step and rounded up. It is
; `GetPanWait`. Returns the number in a 16-bit A.
;
; What is left goes up to fifteen cells —3840 sixteenths— and the step does
; not go past 128, so they fit exactly in the hardware's 16-bit dividend and
; 8-bit divisor.
.proc pan_frames
.a8
.i16
    rep #$20
.a16
    lda pan_dest_x
    sec
    sbc pan_x
    bpl missing_x
    eor #$FFFF
    inc a
missing_x:
    sta temp
    lda pan_dest_y
    sec
    sbc pan_y
    bpl missing_y
    eor #$FFFF
    inc a
missing_y:
    cmp temp
    bcs greater
    lda temp
greater:
    ; Rounding up is adding the step minus one before dividing.
    clc
    adc pan_step
    sec
    sbc #1
    sta WRDIVL                  ; the dividend, in one 16-bit write
    sep #$20
.a8
    lda pan_step
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
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
    sep #$20
.a8
    rts
.endproc

; --- the camera ------------------------------------------------------------
; It follows the hero: keeps it in the center of the screen except near the
; map's edges, where it stays stuck so as not to show the void outside.
;
; Scrolling is done by hardware, so this is two subtractions and two writes.
; Nothing has to be redrawn: the whole map is already in the tilemap.
; One frame of the screen shake: easyrpg's `Shake::Update` and
; `NextPosition`, with the whole computation as follows:
;
;     amplitude = 1 + 2 * strength
;     new       = -amplitude * sine[(remaining * 4 * (speed + 2)) % 256] / 127
;     cut       = speed * amplitude / 8 + 1
;     position  = clamp(new, position - cut, position + cut)
;
; The products go through the hardware multiplier and the division through
; the divider, which are the ones `apply_tint` already uses. The sine is
; `sine_shake`, in bank 0, signed and scaled to 127; the sign is taken off
; before multiplying and put back afterwards, which is truncating toward zero
; like `int` does.
.proc shake_tick
.a8
.i16
    rep #$20
.a16
    lda shake_remain
    beq nothing16
    dec a
    sta shake_remain
    bne continues
    stz shake_pos               ; the last frame: the screen goes back
nothing16:
    sep #$20
.a8
    rts
.a16
continues:
    ; t = (remaining * 4 * (speed + 2)) % 256: the low byte of remaining * 4
    ; is enough, because whatever is above 256 goes away anyway.
    asl a
    asl a
    sep #$20
.a8
    sta WRMPYA
    lda shake_speed
    inc a
    inc a
    sta WRMPYB                  ; starts it: the product takes eight cycles
    lda shake_force             ; meanwhile, the amplitude
    asl a
    inc a
    sta shake_amp
    nop
    nop
    lda RDMPYL                  ; the low byte of the product is t
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:sine_shake, x         ; outside bank 0: see `sine_table`
    sta shake_sine
    bpl positive
    eor #$FF
    inc a                       ; |sine|
positive:
    sta WRMPYA
    lda shake_amp
    sta WRMPYB                  ; |sine| * amplitude
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
    lda #127
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
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
    sta shake_new               ; |new|
    sep #$20
.a8
    lda shake_sine
    bmi with_sign               ; negative sine: new stays positive
    rep #$20
.a16
    lda shake_new
    eor #$FFFF
    inc a
    sta shake_new               ; positive sine: new is negative
    sep #$20
.a8
with_sign:
    ; cut = speed * amplitude / 8 + 1
    lda shake_speed
    sta WRMPYA
    lda shake_amp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    lsr a
    lsr a
    lsr a
    inc a
    sta shake_cutoff
    lda shake_pos
    sec
    sbc shake_cutoff
    sta shake_lo
    lda shake_pos
    clc
    adc shake_cutoff
    sta shake_hi
    ; The numbers are small —the amplitude does not go past 19— so the sign
    ; of the subtraction is enough for a signed comparison.
    lda shake_new
    sec
    sbc shake_lo
    bmi use_lo
    lda shake_hi
    sec
    sbc shake_new
    bmi use_hi
    lda shake_new
    bra save
use_lo:
    lda shake_lo
    bra save
use_hi:
    lda shake_hi
save:
    sta shake_pos
    sep #$20
.a8
    rts
.endproc

; --- the camera locked: `PanScreen`'s lock and unlock ----------------------
; `Game_Player::LockPan` stops the camera following the hero —`UpdateScroll`
; returns at once— and `UnlockPan` lets it follow again **from where it
; is**: RM2k's camera does not jump back to the hero. It scrolls only when
; the hero walks away from its centre, at his pace, so the gap the lock left
; is kept while he walks away and closes while he walks back, until it is
; gone. A pan —`pan_x`— still moves a locked camera: `UpdatePan` does not
; look at the lock.
;
; Here that is a point the camera centres on before the pan, `PAN_BASE`:
; the hero plus `PAN_GAP` while it follows, `PAN_ANCHOR` while locked. The
; lock **survives a map change**, as `pan_state` does in RM2k, and the gap
; does not: arriving, the camera is centred on the hero —`MoveTo`—, and a
; locked one stays there. It does not travel in the save, which RM2k's
; does: a game saved with the camera locked loads with it free.
.pushseg
.segment "FARBSS"
PAN_LOCKED: .res 1              ; 1 while the camera does not follow the hero
PAN_ANCHOR: .res 4              ; x, y: where a locked camera centres
PAN_GAP:    .res 4              ; x, y: the camera's centre minus the hero, after an unlock
PAN_LAST:   .res 4              ; x, y: the hero on the last frame
PAN_BASE:   .res 4              ; x, y: where the camera centres this frame, before the pan
PAN_D:      .res 2              ; scratch: how far the hero moved on an axis
.popseg

; `OP_PAN`'s lock (A = PAN_LOCK) and unlock (A = PAN_UNLOCK). Keeps X and Y.
.proc pan_lock_set
.a8
.i16
    phx
    cmp #PAN_UNLOCK
    beq unlock
    lda f:PAN_LOCKED
    bne done                    ; locked again: it stays where it is
    lda #1
    sta f:PAN_LOCKED
    rep #$20
.a16
    ldx #0
anchor:
    lda hero_x, x               ; where it was centring, gap included
    clc
    adc f:PAN_GAP, x
    sta f:PAN_ANCHOR, x
    inx
    inx
    cpx #4
    bne anchor
    sep #$20
.a8
    bra done
unlock:
    lda f:PAN_LOCKED
    beq done
    lda #0
    sta f:PAN_LOCKED
    rep #$20
.a16
    ldx #0
gap:
    lda f:PAN_ANCHOR, x         ; the camera stays: the gap is what the hero left
    sec
    sbc hero_x, x
    sta f:PAN_GAP, x
    lda hero_x, x
    sta f:PAN_LAST, x
    inx
    inx
    cpx #4
    bne gap
    sep #$20
.a8
done:
    plx
    rts
.endproc

; The camera centred on the hero, as a map change or a jump to the same map
; leaves it —`Game_Player::MoveTo`—: no gap, and a locked one anchored where
; he arrived. From `enter_map` and `move_hero_to`, with the hero already
; there. Keeps X.
.proc pan_recentre
.a8
.i16
    phx
    rep #$20
.a16
    ldx #0
axis:
    lda #0
    sta f:PAN_GAP, x
    lda hero_x, x
    sta f:PAN_ANCHOR, x
    sta f:PAN_LAST, x
    inx
    inx
    cpx #4
    bne axis
    sep #$20
.a8
    plx
    rts
.endproc

; `PAN_BASE` for this frame, and the gap closed by what the hero walked
; towards the camera's centre. Keeps X.
.proc pan_follow
.a8
.i16
    phx
    lda f:PAN_LOCKED
    rep #$20
.a16
    ldx #0
    and #$00FF
    bne locked
axis:
    lda f:PAN_GAP, x
    beq follows                 ; the usual case: centred on the hero
    lda hero_x, x
    sec
    sbc f:PAN_LAST, x           ; how far he moved
    beq follows
    sta f:PAN_D
    eor f:PAN_GAP, x
    bmi follows                 ; away from the centre: the camera goes with him
    lda f:PAN_GAP, x            ; towards it: the camera stays, the gap closes
    sec
    sbc f:PAN_D
    eor f:PAN_GAP, x
    bmi closed                  ; it went past the centre: closed
    eor f:PAN_GAP, x
    bra keep
closed:
    lda #0
keep:
    sta f:PAN_GAP, x
follows:
    lda hero_x, x
    sta f:PAN_LAST, x
    clc
    adc f:PAN_GAP, x
    sta f:PAN_BASE, x
    inx
    inx
    cpx #4
    bne axis
    sep #$20
.a8
    plx
    rts
.a16
locked:
    lda f:PAN_ANCHOR, x
    sta f:PAN_BASE, x
    lda hero_x, x
    sta f:PAN_LAST, x
    inx
    inx
    cpx #4
    bne locked
    sep #$20
.a8
    plx
    rts
.endproc

.proc follow_camera
.a8
.i16
    jsr pan_follow
    rep #$20
.a16
    lda f:PAN_BASE              ; the hero, unless the camera was locked
    clc
    adc #8                      ; the center of its 16x16 cell
    sec
    sbc #128                    ; half a screen wide
    clc
    ; And the camera panned away from the hero. **The pan is added every
    ; frame, not once**: in RM2k the camera keeps carrying it while the hero
    ; walks —`Game_Player::UpdateScroll`— and only a map change clears it.
    ; That is why a `PanScreen` that nobody returns leaves the screen off
    ; center forever, and that **is faithful**: it happens on leaving through
    ; the gate of map 12 and happens the same in the original RPG_RT. See
    ; `ports/abl/decisions/the-camera-offset-after-the-gate-is-the-games.md` in the
; book.
    adc pan_px
    bpl limit_x
    lda #0                      ; the hero is near the left edge
limit_x:
    cmp cam_max_x
    bcc saves_x
    lda cam_max_x
saves_x:
    sta camera_x

    lda f:PAN_BASE + 2
    clc
    adc #8
    sec
    sbc #112                    ; half a screen high
    clc
    adc pan_py
    bpl limit_y
    lda #0
limit_y:
    cmp cam_max_y
    bcc saves_y
    lda cam_max_y
saves_y:
    sta camera_y

    ; The PPU shows line vofs+1 on the first scanline, so what gets written
    ; to it is always one less than where we want to look.
    dec a
    sta scroll_y
    ; And what the drawing sees: the camera plus the screen shake.
    lda camera_x
    clc
    adc shake_pos
    sta screen_x
    sep #$20
.a8
    rts
.endproc
