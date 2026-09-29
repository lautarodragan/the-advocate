.segment "FAR"

; --- the battle animation frame, rebuilt ------------------------------------
;
; The cartridge stores each frame **without its empty tiles**: a list of
; tiles, each with its number in the box in front —a byte from 0 to 63 and its
; 32 bytes— and $FF at the end. See `cuadro_sin_vacios` in snes_convert.py.
; Here the 2 KB are rebuilt in `ANIMB_BUF`, which is where vblank uploads them
; whole from: what ends up in VRAM is the same as when the cartridge carried
; them complete.
;
; The buffer is kept at zero except for the tiles of the last frame built,
; which `ANIMB_PREV` points to. So building a new one means clearing those and
; copying the new one's, and it costs what the two weigh, not the 2 KB: the
; frames are almost all transparency. It runs in the main loop, with the
; screen on, and that is why the CPU copies and not a DMA to $2180: a general
; DMA outside vblank collides with the HDMA of the message window, and on the
; console's first CPU revision that collision can hang it.
;
; It lives in bank 1 because there is no room in bank 0, and it is entered
; through its fast mirror, like the bank 0 code —see MEMSEL—. Each tile is
; copied unrolled, sixteen words in a row, because a word-at-a-time loop
; spends almost as much on counting and branching as on copying; that is why
; each loop ends in a `jmp`: the unrolled body leaves a `bra` without enough
; reach.

; The whole buffer at zero and no frame built. Called by `enter_map`, with
; the screen off; it is needed at least once after power-on, because WRAM
; starts out with garbage on the console —and in bsnes—.
.proc anim_buf_clear
.a8
.i16
    php
    rep #$20
.a16
    lda #0
    ldx #ANIM_B_BYTES - 2
erase:
    sta f:ANIMB_BUF, x
    dex
    dex
    bpl erase
    sep #$20
.a8
    sta f:ANIMB_PREV + 2        ; A is zero: no frame built
    plp
    rtl
.endproc

; Builds in `ANIMB_BUF` frame `ANIMB_FRAME` of the animation in row
; `ANIMB_ROW`. Clobbers A, X, Y and `temp`.
.proc anim_frame_build
.a8
.i16
    phb
    lda f:ANIMB_PREV + 2
    beq no_previous
    ora #^FAST                ; its fast mirror: see MEMSEL
    pha
    plb                         ; the previous frame's bank
    rep #$20
.a16
    lda f:ANIMB_PREV
    tay
    sep #$20
.a8
    ; Its tiles, to zero.
erase:
    lda a:0, y
    bmi no_previous            ; $FF: done. Tiles go from 0 to 63
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes per tile
    tax
    tya
    clc
    adc #33                     ; the number and its 32 bytes
    tay
    lda #0
.repeat 16, i
    sta f:ANIMB_BUF + i * 2, x
.endrepeat
    sep #$20
.a8
    jmp erase

no_previous:
    ; The new one's pointer: the animation's first plus the one that is due,
    ; four bytes per pointer. It is the same arithmetic vblank did when it
    ; uploaded the frame straight from the cartridge.
    rep #$20
.a16
    lda f:ANIMB_ROW
    tax
    lda f:anim_battle_table + 4, x
    clc
    adc f:ANIMB_FRAME
    asl a
    asl a
    tax
    lda f:anim_battle_frames, x
    sta f:ANIMB_PREV
    tay
    sep #$20
.a8
    lda f:anim_battle_frames + 2, x
    sta f:ANIMB_PREV + 2
    ora #^FAST
    pha
    plb                         ; the new frame's bank
copy:
    lda a:0, y
    bpl tile
    plb                         ; $FF: done
    rtl
tile:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    tax
.repeat 16, i
    lda a:1 + i * 2, y
    sta f:ANIMB_BUF + i * 2, x
.endrepeat
    tya
    clc
    adc #33
    tay
    sep #$20
.a8
    jmp copy
.endproc
