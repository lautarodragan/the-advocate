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
    ; With a big picture up, BG1 and the sprites' VRAM are its own and the
    ; map is not on screen: none of what follows down to the message window
    ; goes up —poses, strips, the ChipSet's animation, palettes— and its own
    ; does instead. See big_picture.s.
    lda f:BIG_FLAGS
    lsr a                       ; BIG_ON
    bcc map_up
    jsl f:big_vblank + FAST
    jmp big_up
map_up:
    lda flash_ready
    beq no_flash2
    jsr upload_flash            ; the flash, or the tint, go before the
    lda #2                      ; poses and eat into their budget in this
    sta vq_cap                  ; same vblank
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
.if ::WINDOW_SYSTEMS > 1
    ora f:WINDOW_SWAP           ; a System's window weighs about a line
.endif
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
    ; **But not in a vblank the window takes**: a line of a box —the last
    ; one comes with the box's appearance— or a System's window, which are
    ; 1920 bytes and the HDMA's tables on their own. With the frame on top
    ; the vblank ran ten lines past its end, and the window's HDMA was turned
    ; on there, mid-frame: on the console and in bsnes its face channel ran
    ; that frame from a stale table and wrote garbage into the map's
    ; palettes, which stayed. taro saw it on 2026-10-19 in Zounds' map 89,
    ; whose tower plays an animation and opens a box while it draws. The
    ; frame waits for the next vblank, `ANIMB_UPLOAD` still set: what goes
    ; up then is the newest one built.
    lda msg_upload
.if ::WINDOW_SYSTEMS > 1
    ora f:WINDOW_SWAP
.endif
    bne no_anim_frame
    lda #0
    sta f:ANIMB_UPLOAD
    jsr anim_drawing_dma
no_anim_frame:
.ifdef paint_table
    jsl f:paint_flush           ; a painted map's slots, before the poses
.endif
    jsl f:vram_drain + FAST     ; the poses this OAM already takes as uploaded
    lda #VQ_PER_FRAME
    sta vq_cap                  ; the coming vblank starts with everything

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

    ; And the pictures' palettes, if a picture was put up or a ramp rebuilt
    ; one this frame: see `pic_flush`.
    jsr pic_flush

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
    lda screen_x                ; the camera plus the shake, if any
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
    jsl f:pano_vblank           ; the panorama's scroll and strips, if any
big_up:

    ; And the message window's HDMA: on while there is one on screen, off when
    ; not. That is **all** it costs to open and close it; its own tilemap is
    ; already written since the map was loaded.
    ;
    ; The map's stretches of the scroll table carry this frame's camera, the
    ; same one just written to the registers: the HDMA writes them again and
    ; nothing changes. What changes is on the window's lines.
    ; First the compositor: the line it left ready, and the whole window when
    ; none are left.
    lda msg_upload
    beq no_upload
    jsr upload_line
    ; And, while a box asks for it, one step per line's vblank: the face's
    ; cells in the window's tilemap and the HDMA table of its palette, if it
    ; has one. See message_face.s.
    jsl f:msg_face_vblank
.if ::WINDOW_SYSTEMS > 1
    bra no_swap
no_upload:
    ; Or the window of the System a `ChangeSystemGraphics` switched to, in a
    ; vblank without a line: both would not fit. Not with a big picture up,
    ; which has the window's tilemap elsewhere and puts it back with the
    ; current System's tiles when it ends: it waits for then.
    lda f:WINDOW_SWAP
    beq no_swap
    lda f:BIG_FLAGS
    lsr a                       ; BIG_ON
    bcs no_swap
    jsl f:window_swap_upload
    jsr stamp_window
no_swap:
.else
no_upload:
.endif
    lda msg_state
    cmp #2
    bne no_finished
    ; Only while the vblank lasts: what follows builds the tables the HDMA
    ; reads while it draws, and a window without its background writes its
    ; arrow's colours into CGRAM, which past the vblank land on whatever
    ; entry the PPU is reading. If this vblank ran out the window appears
    ; on the next one. See the battle animation's frame, above.
    bit HVBJOY
    bpl no_finished
    stz msg_state
    lda #1
    sta msg_open
    ; The tables for where this window goes, which `msg_start` decided: here
    ; and not there because the previous window may still be on screen this
    ; frame, and the HDMA reads its tables while it draws.
    jsl msg_hdma_build
no_finished:

    lda msg_open
    beq no_window
    jsl msg_arrow               ; the arrow of a message waiting for a key
    ; The camera, which every stretch of the map points at; the window's
    ; own scroll does not move, and `msg_hdma_build` wrote it.
    rep #$20
.a16
    lda screen_x
    sta hdma_ofs_map
    lda scroll_y
    sta hdma_ofs_map + 2
    sep #$20
.a8
    jsl f:pano_hdma             ; BG2 is the panorama's in mode 3
    ; And the big picture's wave, if there is one: its flag is its channel.
    lda f:BIG_FLAGS
    and #BIG_WAVE_ON
    ora #HDMA_WINDOW
    ora f:PANO_HDMA             ; and BG1's mask, in a flattened map
    ora f:MSG_FACE_HDMA         ; and a face's palette, on the window's lines
    ; And only while the vblank lasts, too: a channel is set up at the top
    ; of the frame, and one turned on after it runs that frame from
    ; wherever its table was left. The face's writes CGRAM, and what it
    ; wrote stayed. Past the vblank HDMAEN stays as it was for one more
    ; frame, and the next vblank writes it.
    bit HVBJOY
    bpl on
    sta HDMAEN
    bra on
no_window:
    lda f:BIG_FLAGS
    and #BIG_WAVE_ON
    sta HDMAEN
    ; Without HDMA the object mask stays as the last line left it, which is
    ; on: it is turned off by hand, like BG2SC down here.
    stz WOBJSEL
    stz W12SEL                  ; and BG1's, in a flattened map
    ; BG2SC has to be restored by hand: the HDMA left it with the window's
    ; tilemap on the last line it wrote, and without HDMA nobody touches it
    ; again. It costs two instructions and saves having to remember this when
    ; closing a message.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC
    ; And BG1's tilemap and the two bases, if the window that closed traded
    ; BG1 and BG2 over a painting: see `msg_swap_build`.
    lda f:MSG_SWAP
    beq not_traded
    lda #0
    sta f:MSG_SWAP
    lda f:BIG_FLAGS
    lsr a                       ; a big picture put up since owns BG1: leave it
    bcs not_traded
    phx
    ldx map_ofs
    lda f:map_table + M_VRAM_MAP + 1, x
    ora #MAP_LAYOUT
    sta BG1SC
    lda f:map_table + M_BG12NBA_VALUE, x
    sta BG12NBA
    plx
not_traded:

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
    jsl f:fade_mosaic           ; the teleport's, if it asks for it
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
    ; Not in a map whose panorama is BG2: its tilemap is the panorama's.
    lda f:PANO_ON
    cmp #3
    bne upper_column
    rts
upper_column:

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
    ; Not in a map whose panorama is BG2: its tilemap is the panorama's.
    sep #$20
.a8
    lda f:PANO_ON
    cmp #3
    bne upper_row
    rts
upper_row:
    rep #$20
.a16
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
