; ----------------------------------------------------------------------------
; "hola mundo" de RPG Maker 2000 en Super Nintendo
; ensamblar con wla-65816 + wlalink
; ----------------------------------------------------------------------------

.MEMORYMAP
  DEFAULTSLOT 0
  SLOTSIZE $8000
  SLOT 0 $8000
.ENDME

.ROMBANKSIZE $8000
.ROMBANKS 2

.SNESHEADER
  ID "SNES"
  NAME "RM2K PoC             "
  LOROM
  SLOWROM
  CARTRIDGETYPE $00
  ROMSIZE $06
  SRAMSIZE $00
  COUNTRY $01
  LICENSEECODE $00
  VERSION $00
.ENDSNES

.SNESNATIVEVECTOR
  COP EmptyIRQ
  BRK EmptyIRQ
  ABORT EmptyIRQ
  NMI EmptyIRQ
  UNUSED EmptyIRQ
  IRQ EmptyIRQ
.ENDNATIVEVECTOR

.SNESEMUVECTOR
  COP EmptyIRQ
  UNUSED EmptyIRQ
  ABORT EmptyIRQ
  NMI EmptyIRQ
  RESET Start
  IRQBRK EmptyIRQ
.ENDEMUVECTOR

.INCLUDE "assets/snes/sizes.inc"

; --- mapa de la VRAM (en direcciones de palabra) -----------------------------
.DEFINE VRAM_BG_TILES   $0000     ; 384 tiles x 16 palabras
.DEFINE VRAM_TILEMAP    $2000     ; 64x32 entradas
.DEFINE VRAM_OBJ_TILES  $4000     ; 192 tiles, base de OBSEL = 2

.DEFINE WORLD_W  512
.DEFINE WORLD_H  256
.DEFINE SCR_W    256
.DEFINE SCR_H    224
.DEFINE SPR_W    32
.DEFINE SPR_H    32

; --- variables en RAM baja ---------------------------------------------------
.ENUM $0000
  player_x    dw
  player_y    dw
  cam_x       dw
  cam_y       dw
  facing      dw          ; 0 abajo, 1 izq, 2 der, 3 arriba
  anim_step   dw
  anim_timer  dw
  pad         dw
  tmp         dw
.ENDE

.BANK 0 SLOT 0
.ORG 0
.SECTION "Main"

; ----------------------------------------------------------------------------
Start:
    sei
    clc
    xce                     ; modo nativo del 65816
    rep #$38                ; A/X/Y de 16 bits, sin decimal
    ldx #$1FFF
    txs
    jsr InitPPU

    ; ---- paletas ----
    ; CGRAM 0: 8 paletas de fondo
    sep #$20
    lda #$00
    sta $2121
    rep #$20
    lda #BgPal
    ldx #:BgPal
    ldy #256
    jsr DmaCgram

    ; CGRAM 128: paleta de sprites
    sep #$20
    lda #$80
    sta $2121
    rep #$20
    lda #ObjPal
    ldx #:ObjPal
    ldy #32
    jsr DmaCgram

    ; ---- graficos ----
    lda #VRAM_BG_TILES
    sta $2116
    lda #BgTiles
    ldx #:BgTiles
    ldy #BG_TILES_BYTES
    jsr DmaVram

    lda #VRAM_TILEMAP
    sta $2116
    lda #TileMap
    ldx #:TileMap
    ldy #4096
    jsr DmaVram

    lda #VRAM_OBJ_TILES
    sta $2116
    lda #ObjTiles
    ldx #:ObjTiles
    ldy #OBJ_TILES_BYTES
    jsr DmaVram

    jsr InitOam

    ; ---- registros de pantalla ----
    sep #$20
    lda #$01
    sta $2105               ; modo 1
    lda #$21                ; tilemap en palabra $2000, tamano 64x32
    sta $2107
    lda #$00                ; base de tiles de BG1 = palabra $0000
    sta $210B
    lda #$62                ; sprites 32x32, base en palabra $4000
    sta $2101
    lda #$11                ; main screen: BG1 + OBJ
    sta $212C
    lda #$01                ; lectura automatica de joypad
    sta $4200
    lda #$0F                ; brillo maximo, sale del force blank
    sta $2100
    rep #$20

    ; ---- estado inicial ----
    lda #48
    sta player_x
    lda #96
    sta player_y
    stz facing
    lda #1
    sta anim_step
    stz anim_timer

; ----------------------------------------------------------------------------
MainLoop:
    jsr WaitVBlank
    jsr PushScroll
    jsr PushSprite
    jsr ReadPad
    jsr MovePlayer
    jsr UpdateCamera
    bra MainLoop

; ----------------------------------------------------------------------------
WaitVBlank:
    sep #$20
-   lda $4212
    and #$80
    bne -                   ; esperar a salir del vblank anterior
-   lda $4212
    and #$80
    beq -                   ; esperar a entrar en el proximo
    rep #$20
    rts

; ----------------------------------------------------------------------------
ReadPad:
    sep #$20
-   lda $4212
    and #$01
    bne -                   ; esperar a que termine la lectura automatica
    rep #$20
    lda $4218
    sta pad
    rts

; ----------------------------------------------------------------------------
; bits de $4218: Up=$0800 Down=$0400 Left=$0200 Right=$0100
MovePlayer:
    stz tmp                 ; tmp = 1 si se movio

    lda pad
    and #$0200
    beq +
    lda player_x
    sec
    sbc #2
    sta player_x
    lda #1
    sta facing
    lda #1
    sta tmp
    bra ++
+   lda pad
    and #$0100
    beq +
    lda player_x
    clc
    adc #2
    sta player_x
    lda #2
    sta facing
    lda #1
    sta tmp
+
++
    lda pad
    and #$0800
    beq +
    lda player_y
    sec
    sbc #2
    sta player_y
    lda #3
    sta facing
    lda #1
    sta tmp
    bra ++
+   lda pad
    and #$0400
    beq +
    lda player_y
    clc
    adc #2
    sta player_y
    stz facing
    lda #1
    sta tmp
+
++
    ; limitar a los bordes del mapa
    lda player_x
    bpl +
    stz player_x
+   lda player_x
    cmp #(WORLD_W - SPR_W + 1)
    bcc +
    lda #(WORLD_W - SPR_W)
    sta player_x
+   lda player_y
    bpl +
    stz player_y
+   lda player_y
    cmp #(WORLD_H - SPR_H + 1)
    bcc +
    lda #(WORLD_H - SPR_H)
    sta player_y
+
    ; animacion
    lda tmp
    bne +
    lda #1                  ; quieto: frame del medio
    sta anim_step
    stz anim_timer
    rts
+   lda anim_timer
    inc a
    sta anim_timer
    cmp #7
    bcc +
    stz anim_timer
    lda anim_step
    inc a
    and #3
    sta anim_step
+   rts

; ----------------------------------------------------------------------------
UpdateCamera:
    lda player_x
    clc
    adc #(SPR_W/2)
    sec
    sbc #(SCR_W/2)
    bpl +
    lda #0
+   cmp #(WORLD_W - SCR_W + 1)
    bcc +
    lda #(WORLD_W - SCR_W)
+   sta cam_x

    lda player_y
    clc
    adc #(SPR_H/2)
    sec
    sbc #(SCR_H/2)
    bpl +
    lda #0
+   cmp #(WORLD_H - SCR_H + 1)
    bcc +
    lda #(WORLD_H - SCR_H)
+   sta cam_y
    rts

; ----------------------------------------------------------------------------
; los registros de scroll son de escritura doble, byte bajo y despues alto
PushScroll:
    sep #$20
    lda cam_x
    sta $210D
    lda cam_x+1
    sta $210D
    lda cam_y
    sta $210E
    lda cam_y+1
    sta $210E
    rep #$20
    rts

; ----------------------------------------------------------------------------
; un solo sprite de 32x32. numero de tile = (frame/4)*64 + (frame%4)*4
PushSprite:
    ; frame = facing*3 + ciclo[anim_step]
    lda anim_step
    and #$0003
    tax
    lda.l WalkCycle,x
    and #$00FF
    sta tmp
    lda facing
    asl a
    clc
    adc facing              ; facing*3
    clc
    adc tmp
    sta tmp                 ; tmp = indice de frame 0..11

    sep #$20
    stz $2102
    stz $2103               ; direccion de OAM = 0

    rep #$20
    lda player_x
    sec
    sbc cam_x
    sep #$20
    sta $2104               ; X en pantalla
    rep #$20
    lda player_y
    sec
    sbc cam_y
    sep #$20
    sta $2104               ; Y en pantalla

    ; numero de tile
    rep #$20
    lda tmp
    lsr a
    lsr a                   ; fila de la grilla = frame/4
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                   ; *64
    sta tmp+0
    lda tmp
    and #$0003              ; columna = frame%4
    asl a
    asl a                   ; *4
    clc
    adc tmp+0
    sep #$20
    sta $2104               ; byte bajo del numero de tile
    lda #$20                ; prioridad 2, paleta 0 de sprites
    sta $2104
    rep #$20
    rts

WalkCycle:
    .db 0, 1, 2, 1

; ----------------------------------------------------------------------------
InitOam:
    sep #$20
    stz $2102
    stz $2103
    ldx #128
-   lda #$00
    sta $2104               ; X
    lda #$E0
    sta $2104               ; Y fuera de pantalla
    lda #$00
    sta $2104
    sta $2104
    dex
    bne -
    ; tabla alta: sprite 0 grande, el resto chico, X alto en 0
    lda #$02
    sta $2104
    ldx #31
-   lda #$00
    sta $2104
    dex
    bne -
    rep #$20
    rts

; ----------------------------------------------------------------------------
; A = direccion fuente, X = banco fuente, Y = cantidad de bytes
DmaVram:
    sta $4302
    sep #$20
    txa
    sta $4304
    lda #$80
    sta $2115               ; incremento de palabra despues de $2119
    lda #$01
    sta $4300               ; modo 1: escribe $2118/$2119 alternando
    lda #$18
    sta $4301
    rep #$20
    tya
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    rts

DmaCgram:
    sta $4302
    sep #$20
    txa
    sta $4304
    lda #$00                ; modo 0: un solo registro
    sta $4300
    lda #$22
    sta $4301
    rep #$20
    tya
    sta $4305
    sep #$20
    lda #$01
    sta $420B
    rep #$20
    rts

; ----------------------------------------------------------------------------
InitPPU:
    sep #$20
    lda #$8F
    sta $2100               ; force blank
    stz $2101
    stz $2102
    stz $2103
    stz $2105
    stz $2106
    stz $2107
    stz $2108
    stz $2109
    stz $210A
    stz $210B
    stz $210C
    stz $210D
    stz $210D
    stz $210E
    stz $210E
    stz $2123
    stz $2124
    stz $2125
    stz $2126
    stz $2127
    stz $2128
    stz $2129
    stz $212A
    stz $212B
    stz $212C
    stz $212D
    stz $212E
    stz $212F
    lda #$30
    sta $2130
    stz $2131
    lda #$E0
    sta $2132
    stz $2133
    stz $4200
    lda #$FF
    sta $4201
    stz $420C
    rep #$20
    rts

EmptyIRQ:
    rti

.ENDS

; ----------------------------------------------------------------------------
.BANK 1 SLOT 0
.ORG 0
.SECTION "GfxData"
BgPal:    .INCBIN "assets/snes/bg_pal.bin"
ObjPal:   .INCBIN "assets/snes/obj_pal.bin"
TileMap:  .INCBIN "assets/snes/tilemap.bin"
BgTiles:  .INCBIN "assets/snes/bg_tiles.bin"
ObjTiles: .INCBIN "assets/snes/obj_tiles.bin"
.ENDS
