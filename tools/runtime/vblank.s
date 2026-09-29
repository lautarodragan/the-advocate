.segment "CODE"

; --- what has to go inside the vblank, no matter what ----------------------
; OAM can only be written while the PPU is not reading it, that is, in the
; vblank. Building it takes its time —with thirty-odd characters, more than a
; millisecond— so building it and uploading it in the same vblank does not fit:
; the upload ends up falling outside and the objects show up anywhere.
;
; That is why the previous frame's is uploaded as soon as the vblank starts, and
; only afterwards is the next one built. The scroll goes along with it, so the
; background and the sprites correspond to the same moment.
.proc flush_video
.a8
.i16
    jsr push_oam
    lda flash_ready
    beq no_flash2
    jsr upload_flash          ; the flash, or the tint, go before the
    lda #2                      ; poses and eat into their budget in this
    sta vq_cap                 ; same vblank
    bra no_tint
no_flash2:
    lda tint_ready
    beq no_tint
    jsr upload_tint
    lda #2
    sta vq_cap
no_tint:
    ; And a window line waiting also eats into their budget: it is 1920 bytes
    ; in a single DMA, almost four poses. With the usual five the vblank ends
    ; in the middle and the rest of the line is written with the screen on,
    ; that is, it is not written: a band of garbage is left in the window,
    ; **fixed**, and only on a map with many events moving. taro saw it in
    ; Lashe City on 2026-09-08 talking to the mechanic and the hobo; it showed
    ; up with the parallel events, which added nine characters that move and
    ; therefore nine poses to upload.
    lda msg_upload
    beq no_line
    lda #1
    sta vq_cap
no_line:
    ; And a map strip waiting —the row or column the camera uncovered— too:
    ; `push_strips` runs after the poses and until 2026-09-10 it did not
    ; subtract anything, so in a vblank with all five poses its DMAs landed
    ; with the screen on and VRAM ignored them. The row was left undrawn until
    ; the camera went over it again. taro saw it playing on 2026-09-09, "sort
    ; of random", and EV0041 of map 8 reproduces it: the hero's jump queues new
    ; poses right when the camera crosses a row. A row is four 64-byte DMAs,
    ; half a pose: a whole one is subtracted so as not to go measuring the
    ; edge.
    lda row_addr
    ora row_addr + 1
    ora col_addr
    ora col_addr + 1
    beq no_strip
    lda vq_cap
    beq no_strip
    dec a
    sta vq_cap
no_strip:
    ; And a step of the ChipSet animation, which also comes out of this vblank:
    ; up to 26 background tiles, that is 1664 bytes, which is more than three
    ; poses. It is subtracted from the budget instead of setting it, so it adds
    ; to whatever the tint or a window line already took.
    jsr anim_flush
    ; And the 2 KB of the battle animation's frame, if the tick asked for a
    ; new one. It is the most expensive thing uploaded in a vblank —four poses
    ; of the five— and it happens once every two frames. It goes **before**
    ; `vram_drain` for the same reason as `anim_flush`: what it takes has to
    ; come out of this vblank's budget, and three lines further down `vq_cap`
    ; is already reset for the next one. See `anim_drawing_dma`.
    lda f:ANIMB_UPLOAD
    beq no_anim_frame
    lda #0
    sta f:ANIMB_UPLOAD
    jsr anim_drawing_dma
no_anim_frame:
    jsr vram_drain             ; the poses this OAM already takes as uploaded
    lda #VQ_PER_FRAME
    sta vq_cap                 ; the coming vblank starts with everything

    ; The flash palettes left pending from the previous frame, **all of
    ; them**: one per slot. See FAR_FLASH_PAL.
    ldx #$0000
other_flash:
    lda flash_ev + 7, x
    beq no_flash
    stz flash_ev + 7, x
    sta CGADD
    rep #$20
.a16
    txa
    asl a
    asl a                       ; from eight bytes per slot to thirty-two
    clc
    adc #.loword(FAR_FLASH_PAL)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^FAR_FLASH_PAL
    sta A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_flash:
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc other_flash

    ; And the picture's palette, if the ramp rebuilt it this frame. It is
    ; thirty-two bytes and goes separately from the map's three: the picture's
    ; entry falls above `SPRITE_CGRAM`, that is, outside what `upload_palettes`
    ; uploads.
    lda f:PICTURE_READY
    beq no_picture
    lda #0
    sta f:PICTURE_READY
    lda #(128 + 16 * PICTURE_PAL)
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_shadow + 2 * (128 + 16 * PICTURE_PAL))
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_picture:

    ; And the battle animation's palette, if one just started. It is the same
    ; thirty-two bytes as the picture's and for the same reason: its entry falls
    ; above `SPRITE_CGRAM` and `upload_palettes` does not touch it.
    lda f:ANIMB_PAL
    beq no_anim_pal
    lda #0
    sta f:ANIMB_PAL
    lda f:ANIMB_CGADD
    sta CGADD
    rep #$20
.a16
    lda f:ANIMB_SHADOW
    clc
    adc #.loword(cgram_shadow)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
no_anim_pal:

    ; The two scroll registers are write-twice: first the low byte and then
    ; the high one.
    ; Each register is completed before moving on to the next. The scroll ones
    ; share a single latch among all planes, so interleaving the writes —BG1
    ; low, BG2 low, BG1 high, BG2 high— mixes the values and the plane ends up
    ; shifted within its cell, moving in place.
    lda screen_x              ; the camera plus the shake, if any
    sta BG1HOFS
    lda screen_x + 1
    sta BG1HOFS
    lda screen_x
    sta BG2HOFS
    lda screen_x + 1
    sta BG2HOFS

    lda scroll_y
    sta BG1VOFS
    lda scroll_y + 1
    sta BG1VOFS
    lda scroll_y
    sta BG2VOFS
    lda scroll_y + 1
    sta BG2VOFS

    jsr push_strips

    ; And the message window's HDMA: on while there is one on screen, off when
    ; not. That is **all** it costs to open and close it; its own tilemap is
    ; already written since the map was loaded.
    ;
    ; The two top stretches of the scroll table carry this frame's camera, the
    ; same one just written to the registers: the HDMA writes them again on
    ; line 0 and nothing changes. What changes is from line 144 down.
    ; First the compositor: the line it left ready, and the whole window when
    ; none are left.
    lda msg_upload
    beq no_upload
    jsr upload_line
no_upload:
    lda msg_state
    cmp #2
    bne no_finished
    stz msg_state
    lda #1
    sta msg_open
no_finished:

    lda msg_open
    beq no_window
    lda screen_x
    sta hdma_ofs + 1
    sta hdma_ofs + 6
    lda screen_x + 1
    sta hdma_ofs + 2
    sta hdma_ofs + 7
    lda scroll_y
    sta hdma_ofs + 3
    sta hdma_ofs + 8
    lda scroll_y + 1
    sta hdma_ofs + 4
    sta hdma_ofs + 9
    lda #HDMA_WINDOW
    sta HDMAEN
    bra on
no_window:
    stz HDMAEN
    ; Without HDMA the object mask stays as the last line left it, which is
    ; on: it is turned off by hand, like BG2SC down here.
    stz WOBJSEL
    ; BG2SC has to be restored by hand: the HDMA left it with the window's
    ; tilemap on the last line it wrote, and without HDMA nobody touches it
    ; again. It costs two instructions and saves having to remember this when
    ; closing a message.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC

    ; And last of all, the master brightness.
    ;
    ; **INIDISP is written only here**, and that is not neatness: it is what
    ; makes the brightness change between two frames and not in the middle of
    ; one. Writing it from the loop draws the frame split —the top with the old
    ; brightness and the bottom with the new—, which is exactly the defect seen
    ; on every teleport: the screen came back on when the load finished, that
    ; is, mid-frame, and on top of that with the old map's scroll and OAM,
    ; because those are also written here and only in the vblank.
    ;
    ; Whoever wants to change the brightness writes `brightness` and waits for the
    ; next vblank, just as whoever moves a sprite writes OAM and waits. The only
    ; exception is a load's forced blank, which `fade_tick` writes by hand:
    ; there the screen is already black and the change does not show.
on:
    jsl f:fade_mosaic       ; the teleport's, if it asks for it
    lda brightness
    sta INIDISP
    rts
.endproc

; Uploads Y bytes from RAM address X to VRAM, which has already been pointed.
.proc dma_a_vram
.a8
.i16
    stx A1T0L
    lda strip_bank              ; 0 this pass's strip, $7E the spare one
    sta A1B0
    sty DAS0L
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0                   ; destination: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

; The strips stream_map left built. They go here and not where they are built
; because VRAM can only be written in the vblank; building them inside would
; not fit.
.proc push_strips
.a8
.i16
    ; Four strips at most: the column and row this pass built, and the spare
    ; ones it left saved if the camera uncovered two on one axis. Each one is
    ; uploaded on its own, and an address at zero means there is none.
    ldx col_addr_b
    beq no_column_b
    stx strip_vram
    ldx #.loword(FAR_STRIP_COL)
    stx strip_of
    lda #^FAR_STRIP_COL
    sta strip_bank
    jsr push_one_column
no_column_b:
    ldx col_addr
    beq no_column
    stx strip_vram
    ldx #.loword(strip_col)
    stx strip_of
    stz strip_bank
    jsr push_one_column
no_column:

    ldx row_addr_b
    beq no_row_b
    stx strip_vram
    ldx #.loword(FAR_STRIP_ROW)
    stx strip_of
    lda #^FAR_STRIP_ROW
    sta strip_bank
    jsr push_one_row
no_row_b:
    ldx row_addr
    beq no_row
    stx strip_vram
    ldx #.loword(strip_row)
    stx strip_of
    stz strip_bank
    jsr push_one_row
no_row:
    ; All four consumed, also discarding the ones that were not uploaded for
    ; being at zero: what was not built this pass is not built on the next.
    rep #$20
.a16
    stz col_addr
    stz col_addr_b
    stz row_addr
    stz row_addr_b
    sep #$20
.a8
    rts
.endproc

; One tilemap column to VRAM: to word `strip_vram`, from `strip_of` in bank
; `strip_bank`. It takes one DMA per layer, because the PPU can advance by 32
; words after each write, which is exactly what a tilemap row measures.
;
; The two variables **advance as the strip is consumed**, and `temp` is not
; used for that even though it is at hand: `fill_window` keeps there the
; column number it is on and reads it **after** calling `push_strips`, so
; overwriting it breaks its loop. It cost a whole suite run with all 957
; visible cells different, on 2026-09-22.
.proc push_one_column
.a8
.i16
    lda #$81                    ; advance 32 words after the high byte
    sta VMAIN
    ldx strip_vram
    stx VMADDL
    ldx strip_of
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram

    ; The upper layer: the same slot in its tilemap, and its strip right after
    ; the other in RAM. The slot comes from masking and not from adding a fixed
    ; distance because the background's tilemap is not always in the same
    ; place —see LAYOUT_VENTANA_AMBOS—; it is enough that both start at
    ; multiples of 2048 words, which the converter checks for the background's.
    rep #$20
.a16
    lda strip_vram
    and #(WINDOW_COLS * WINDOW_ROWS - 1)
    ora #VRAM_ABOVE_MAP
    sta strip_vram
    lda strip_of
    clc
    adc #(WINDOW_ROWS * 2)
    sta strip_of
    sep #$20
.a8
    ldx strip_vram
    stx VMADDL
    ldx strip_of
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram
    rts
.endproc

; And a row, which takes four: the two 32x32 screens are not contiguous —the
; right one lives 1024 words further on— and the upper layer lives in its own
; tilemap. The order is: background left, background right, upper left, upper
; right, and each step advances both variables.
;
; The upper layer is reached by masking the address, here and in
; `push_one_column`, and that requires its tilemap to start at a multiple of
; the window's size.
.assert VRAM_ABOVE_MAP .mod (WINDOW_COLS * WINDOW_ROWS) = 0, error, "the upper tilemap cannot be masked"
.proc push_one_row
.a8
.i16
    lda #$80                    ; advance one word: the row is contiguous
    sta VMAIN
    ldx strip_vram
    stx VMADDL
    ldx strip_of
    ldy #WINDOW_COLS            ; slots 0 to 31, the left screen
    jsr dma_a_vram
    rep #$20
.a16
    lda #1024                   ; the right screen lives here
    jsr row_next
    ; And the upper layer: the same row on its tilemap's left screen. It is
    ; masked with ten bits and not eleven to take off the 1024 the previous
    ; step already added.
    lda strip_vram
    and #(WINDOW_COLS * WINDOW_ROWS / 2 - 1)
    ora #VRAM_ABOVE_MAP
    jsr row_in_a
    lda #1024                   ; and its right half
    jsr row_next
    sep #$20
.a8
    rts
.endproc

; The next half row: moves VRAM by what A says —in words— and the source by the
; 64 bytes half a row measures, and uploads it. It enters and leaves with a
; sixteen-bit A, which is what lets the three calls above be chained.
.proc row_next
.a16
.i16
    clc
    adc strip_vram
    ; And it falls through into `row_in_a`, which is the same step with the
    ; address already done.
.endproc
.proc row_in_a
.a16
.i16
    sta strip_vram
    lda strip_of
    clc
    adc #WINDOW_COLS
    sta strip_of
    sep #$20
.a8
    ldx strip_vram
    stx VMADDL
    ldx strip_of
    ldy #WINDOW_COLS
    jsr dma_a_vram
    rep #$20
.a16
    rts
.endproc
