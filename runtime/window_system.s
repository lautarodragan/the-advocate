; --- the System of the message window ------------------------------------------
; `ChangeSystemGraphics`: the message window from then on with another
; System. The converter carries one window per System the cartridge's pages
; switch to —`WINDOW_SYSTEMS`, the starting one first— and `window_systems`
; points at each one's pieces: its tiles, its palette, its two planes of
; cells, its arrow's cells, the text area's background, the bar over it and
; its arrow's tiles as objects.
; What does **not** change is the font's composed tables: the converter
; gives the text the same palette entries in every System —see `text_rows`
; in `rm2k-snes-screens window`—, so a System is a palette and a few tiles,
; and the eight tables, some 116 KB, are carried once.
;
; **Only the message window follows the change.** The menus, the slot
; screen, the battle and the title keep the System the cartridge starts
; with: their windows are drawn into their banks once, by the converter.
;
; The code that reads a piece does it through `WINDOW_NOW`, a copy of the
; current System's entry that `window_select` makes, with the macros below;
; a cartridge with one System —`WINDOW_SYSTEMS` 1— assembles them as the
; plain labels it always read, and none of this costs it a byte.

; The offset of each piece's 24-bit pointer in an entry of `window_systems`:
; the order of `window_systems_table` in rm2k-snes-mapdata's emission.
WS_TILES     = 0
WS_CGRAM     = 3
WS_CELLS     = 6
WS_CELLS_256 = 9
WS_ARROW     = 12
WS_BACKDROP  = 15
WS_BAR       = 18
WS_BAR_BARE  = 21
WS_ARROW_OBJ = 24
WS_GOLD      = 27
.if ::WINDOW_SYSTEMS > 1
.assert WINDOW_SYSTEM_BYTES = WS_GOLD + 3, error, "window_systems has another number of pieces than WS_ says"
.endif

; What the System adds to a saved game: `WINDOW_SYSTEM`'s byte, in a
; cartridge that switches. `SAVE_BYTES` adds it.
WINDOW_SAVE_BYTES = WINDOW_SYSTEMS > 1

.if ::WINDOW_SYSTEMS > 1
.pushseg
.segment "FARBSS"
; Which System, 0 the starting one. It travels in the save: see `save_table`.
WINDOW_SYSTEM: .res 1
; Set by `op_change_system`: the window's tiles, palette and tilemap go up in
; the next vblank —see `flush_video`—.
WINDOW_SWAP:   .res 1
; The current System's entry of `window_systems`.
WINDOW_NOW:    .res WINDOW_SYSTEM_BYTES
.popseg
.endif

; A16: A to the low word of the current System's `piece`, or of `label`.
.macro win_lo label, piece
.if ::WINDOW_SYSTEMS > 1
    lda f:WINDOW_NOW + piece
.else
    lda #.loword(label)
.endif
.endmacro

; A8: A to its bank.
.macro win_bank label, piece
.if ::WINDOW_SYSTEMS > 1
    lda f:WINDOW_NOW + piece + 2
.else
    lda #^label
.endif
.endmacro

; A16: its low word added to A.
.macro win_adc label, piece
.if ::WINDOW_SYSTEMS > 1
    adc f:WINDOW_NOW + piece
.else
    adc #.loword(label)
.endif
.endmacro

.if ::WINDOW_SYSTEMS > 1
.pushseg
.segment "FAR2"

; The current System's entry to `WINDOW_NOW`: at every map's load, which is
; also how a loaded save gets its own, and when the command runs. Keeps X
; and Y.
.proc window_select
.a8
.i16
    phx
    phy
    phb
    php
    rep #$30
.a16
    lda f:WINDOW_SYSTEM
    and #$00FF
    cmp #WINDOW_SYSTEMS         ; a save of another build: the starting one
    bcc known
    lda #0
known:
    pha
    asl a                       ; times 2
    clc
    adc 1, s                    ; times 3
    sta 1, s
    asl a
    asl a
    asl a                       ; times 24
    clc
    adc 1, s                    ; times 27
    clc
    adc #.loword(window_systems)
    tax
    pla
    ldy #.loword(WINDOW_NOW)
    lda #WINDOW_SYSTEM_BYTES - 1
    mvn #^window_systems, #^WINDOW_NOW
    plp
    plb
    ply
    plx
    rtl
.endproc

; In the vblank after a `ChangeSystemGraphics`: the window's tiles and its
; palette from the new System. Its tilemap is `stamp_window`'s, which the
; caller runs after this. The palette goes from entry 1: 0 is the screen's
; backdrop, which a panorama's tint may have changed. Some 550 bytes; with
; the tilemap's 1280, about one line of the window, and `flush_video`
; budgets it like one.
.proc window_swap_upload
.a8
.i16
    lda #0
    sta f:WINDOW_SWAP
    ldx map_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:map_table + M_VRAM_WINDOW, x
    sta VMADDL
    lda f:WINDOW_NOW + WS_TILES
    sta A1T0L
    lda #(WINDOW_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    lda f:WINDOW_NOW + WS_TILES + 2
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    lda #1
    sta CGADD
    rep #$20
.a16
    lda f:WINDOW_NOW + WS_CGRAM
    inc a
    inc a
    sta A1T0L
    lda #((CGRAM_BASE - 1) * 2)
    sta DAS0L
    sep #$20
.a8
    lda f:WINDOW_NOW + WS_CGRAM + 2
    sta A1B0
    stz DMAP0                   ; one register, byte by byte
    lda #$22
    sta BBAD0                   ; CGDATA
    lda #$01
    sta MDMAEN
    jml f:arrow_obj_load_l      ; and the arrow's objects, if it has them up
.endproc

.popseg
.endif

; The rest of the file assembles nothing; the widths go back to how the
; assembler starts, which is what the next file found before this one.
.a8
.i8
