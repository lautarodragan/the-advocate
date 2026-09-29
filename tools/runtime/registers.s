; --- ports ------------------------------------------------------------------
INIDISP  = $2100        ; brightness and blanking
NMITIMEN = $4200        ; NMI and joypad enable
RDNMI    = $4210        ; reading it clears the NMI flag
TIMEUP   = $4211        ; reading it clears the IRQ flag
VTIMEL   = $4209        ; which line the music IRQ falls on
VTIMEH   = $420A
; The music IRQ's line: far from vblank, which is where the loop does its DMA
; on a tight time budget, and in the middle of the visible part, where
; whatever is running can wait as long as a music frame takes.
IRQ_LINE = 112
HVBJOY   = $4212        ; bit 7: we are in vblank
MEMSEL   = $420D        ; bit 0: the ROM from bank $80 onwards, fast
; The code runs from the bank $80 mirror, not from bank 0. Banks $80 to $BF
; are the same as $00 to $3F —low RAM, the registers and the ROM in the same
; places—, but with MEMSEL at 1 the ROM there is read at 3.58 MHz instead of
; 2.68: everything the CPU fetches from the cartridge, starting with the
; instructions, goes a third faster. It is the header's FastROM. All that has
; to be done is get in: reset and the interrupts arrive through sixteen-bit
; vectors, that is, into bank 0, and jump to the mirror with a `jml`; from
; there on every `jsr` and every `rts` stays in the bank it is in. Since
; 2026-09-11, because the opening with rain, thunder and text dropped one
; frame out of three.
FAST     = $800000
STAT78   = $213F        ; bit 4: 0 = NTSC console, 1 = PAL
HDMAEN   = $420C        ; per-scanline DMA channels
APUIO0   = $2140        ; the four ports to the SPC700
APUIO1   = $2141
APUIO2   = $2142
APUIO3   = $2143

; The SPC700 driver command that sends it back to the IPL ROM. See `DRIVER`
; in tools/rm2k-snes-audio/src/spc700.rs and the `reset` loop that uses it.
APU_CMD_IPL = 4

; The console multiplies and divides in hardware, which is all the screen
; tint needs: it scales each channel by a value from 0 to 200 with 100 as
; neutral, that is, multiply and divide by a hundred. Both are exact and on
; integers, so the same computation in Python —`color.apply_tint`— always gives
; the same result.
;
; The product takes 8 cycles to be ready and the quotient 16. There is no need
; to wait for them in a loop: it is enough not to read the result right away,
; and the code in between already covers it.
WRMPYA   = $4202        ; 8-bit multiplicand
WRMPYB   = $4203        ; multiplier: writing it starts the computation
RDMPYL   = $4216        ; the 16-bit product
WRDIVL   = $4204        ; 16-bit dividend
WRDIVH   = $4205
WRDIVB   = $4206        ; 8-bit divisor: writing it starts the computation
RDDIVL   = $4214        ; the 16-bit quotient

; The other multiplier, the PPU's: the one of the mode 7 matrix, which
; multiplies M7A —sixteen bits signed, two writes— by the last byte written
; to M7B —eight signed— and leaves the 24-bit product in $2134-$2136
; **instantly**. It works outside mode 7, and this port is fixed in mode 3.
;
; **It belongs to `irq_music` and nobody else**: the song fade scales each
; voice's volume with it —see `volume_refresh`—. The one above cannot be used
; there, because the main code uses it in thirty places and an interrupt
; between its write and its read would change its result. With this one the
; same happens the other way round: if the main code ever uses it, it has to
; do so with interrupts disabled.
M7A      = $211B
M7B      = $211C
MPYM     = $2135        ; the middle byte of the product: divided by 256

; --- the PPU ----------------------------------------------------------------
BGMODE   = $2105        ; which graphics mode and how many bits per pixel
BG1SC    = $2107        ; where BG1's tilemap lives and what size it is
BG2SC    = $2108        ; the same for BG2, the layer that covers the hero
BG2HOFS  = $210F        ; its scroll, which has to go along with BG1's
BG2VOFS  = $2110
BG12NBA  = $210B        ; where the BG1 and BG2 tiles live
BG1HOFS  = $210D        ; BG1 horizontal scroll (written twice)
BG1VOFS  = $210E        ; vertical scroll
VMAIN    = $2115        ; how the VRAM pointer advances after each write
VMADDL   = $2116        ; VRAM address, in words
VMDATAL  = $2118        ; and the data, one word at a time with VMAIN at $80
CGADD    = $2121        ; CGRAM index
CGDATA   = $2122        ; and the color, a byte at a time: low byte first
TM       = $212C        ; which layers show on the main screen
MOSAIC   = $2106        ; the mosaic: size in the high nibble, layers in the low
CGWSEL   = $2130        ; where color math applies and against which color
CGADSUB  = $2131        ; add or subtract, and on which layers
COLDATA  = $2132        ; the fixed color: three channel bits and the intensity
OBSEL    = $2101        ; sprite size and where their tiles live
OAMADDL  = $2102        ; index into OAM, in words
OAMDATA  = $2104        ; the next OAM byte, which advances by itself
OBJSEL_TM = $212C
JOY1H    = $4219        ; pad 1: up, down, left, right and more
JOY1L    = $4218        ; and the other byte, where A, X, L and R live

; The pad bits we care about, as they appear in JOY1H.
PAD_RIGHT = $01
PAD_LEFT  = $02
PAD_DOWN  = $04
PAD_UP    = $08
; And start, which nobody looked at until the title screen: the game is
; walked with the d-pad and talked with A.
PAD_START = $10

; A lives in the other byte. The pad's sixteen bits are, from high to low,
; B Y select start up down left right A X L R and four of padding; JOY1H
; carries the eight high ones and JOY1L the eight low ones, so A is bit 7 of
; JOY1L.
PAD_A     = $80
; And X, the next one: RM2k does not use it, and here it is A's autofire. See `read_pad`.
PAD_X     = $40

; B lives with the others in JOY1H, and it is the highest of the sixteen. The
; choice uses it to cancel; walking does not look at it.
PAD_B     = $80

; --- DMA, channel 0 ---------------------------------------------------------
DMAP0    = $4300        ; transfer mode
BBAD0    = $4301        ; PPU register it goes to
A1T0L    = $4302        ; source: address and bank
A1B0     = $4304
DAS0L    = $4305        ; how many bytes
MDMAEN   = $420B        ; start

; --- DMA, channel 7 ---------------------------------------------------------
; The second general-purpose DMA channel, for when a copy interleaves two
; sources and it is not worth reprogramming channel 0 between them: see
; `scn_fill`. Channels 1 to 3 belong to HDMA, below.
DMAP7    = $4370
BBAD7    = $4371
A1T7L    = $4372
A1B7     = $4374
DAS7L    = $4375

; --- HDMA, channels 1 and 2 -------------------------------------------------
; Ordinary DMA transfers everything in one go, with the screen off or in
; vblank. HDMA is something else: the same hardware, but fired **once per
; scanline**, so a PPU register can hold one value at the top of the screen
; and another at the bottom. It is what games use for status bars and sky
; gradients, and here it is what pins the message window in place.
;
; Each channel reads a table in RAM with `[how many lines][value...]` entries
; and ends with a zero. The counter is 7 bits, that is, 127 lines at most.
DMAP1    = $4310
BBAD1    = $4311
A1T1L    = $4312
A1B1     = $4314
DMAP2    = $4320
BBAD2    = $4321
A1T2L    = $4322
A1B2     = $4324
DMAP3    = $4330
BBAD3    = $4331
A1T3L    = $4332
A1B3     = $4334
HDMA_WINDOW = $0E       ; channels 1, 2 and 3 on at once
; PPU window 1, which is not the message window: it is the mask that hides
; the objects under it. See `build_hdma`.
WOBJSEL  = $2125        ; which PPU windows mask objects
WH0      = $2126        ; window 1's left edge
WH1      = $2127        ; and the right one
TMW      = $212E        ; which main-screen layers it applies to

; The WRAM port. It is for what plain DMA cannot do on its own: copy from ROM
; to RAM. DMA always goes from bus A to bus B, and WRAM has its window on bus
; B, so pointing WMADD at where you want to write and sending to $2180 copies
; ROM -> RAM at the same speed as any other DMA.
WMDATA   = $2180
