; ---------------------------------------------------------------------------
; PoC de audio en Super Nintendo: reproduce un tema en loop, sin dibujar nada.
;
; El audio de la SNES lo maneja el SPC700, un procesador aparte con su propia
; memoria de 64 KB. El 65816 no puede tocar el DSP directamente: sólo puede
; hablarle al SPC700 por cuatro puertos.
;
; Al encender, el SPC700 corre una ROM interna que implementa un protocolo de
; carga. Lo usamos para meterle en memoria las muestras y un driver mínimo, y
; después ese driver se queda esperando pares (registro, valor) del DSP que le
; manda el 65816. O sea que toda la música la sigue manejando el 65816, igual
; que en la Mega Drive.
; ---------------------------------------------------------------------------

.p816
.smart

; --- puertos ---------------------------------------------------------------
INIDISP  = $2100        ; brillo y blanking
NMITIMEN = $4200        ; habilitación de NMI y joypads
RDNMI    = $4210        ; leerlo baja la bandera de NMI
HVBJOY   = $4212        ; bit 7: estamos en vblank
STAT78   = $213F        ; bit 4: 0 = consola NTSC, 1 = PAL
HDMAEN   = $420C        ; canales de DMA por scanline
APUIO0   = $2140        ; los cuatro puertos hacia el SPC700
APUIO1   = $2141
APUIO2   = $2142
APUIO3   = $2143

; --- el PPU ----------------------------------------------------------------
BGMODE   = $2105        ; qué modo gráfico y con cuántos bits por pixel
BG1SC    = $2107        ; dónde vive el tilemap de BG1 y de qué tamaño es
BG2SC    = $2108        ; lo mismo para BG2, la capa que tapa al héroe
BG2HOFS  = $210F        ; su scroll, que tiene que ir con el de BG1
BG2VOFS  = $2110
BG12NBA  = $210B        ; dónde viven los tiles de BG1 y BG2
BG1HOFS  = $210D        ; scroll horizontal de BG1 (se escribe dos veces)
BG1VOFS  = $210E        ; scroll vertical
VMAIN    = $2115        ; cómo avanza el puntero de VRAM tras cada escritura
VMADDL   = $2116        ; dirección de VRAM, en palabras
CGADD    = $2121        ; índice de CGRAM
TM       = $212C        ; qué capas se ven en la pantalla principal
OBSEL    = $2101        ; tamaño de los sprites y dónde viven sus tiles
OAMADDL  = $2102        ; índice dentro de OAM, en palabras
OBJSEL_TM = $212C
JOY1H    = $4219        ; control 1: arriba, abajo, izquierda, derecha y más

; Los bits del control que nos interesan, tal como aparecen en JOY1H.
PAD_RIGHT = $01
PAD_LEFT  = $02
PAD_DOWN  = $04
PAD_UP    = $08

; --- DMA, canal 0 ----------------------------------------------------------
DMAP0    = $4300        ; modo de transferencia
BBAD0    = $4301        ; registro del PPU al que va
A1T0L    = $4302        ; origen: dirección y banco
A1B0     = $4304
DAS0L    = $4305        ; cuántos bytes
MDMAEN   = $420B        ; arrancar

; La VRAM se direcciona por palabras. Los tiles arrancan en la 0 y el tilemap
; en la $6000, que deja 24K palabras para tiles: mucho más de las 1024 que el
; tilemap puede nombrar.
VRAM_TILES = $0000
VRAM_ABOVE = $1000      ; los tiles de la capa de encima, que son de 4 bits
VRAM_SPRITE = $2000     ; los tiles de los sprites, en su propia página
VRAM_MAP   = $6000
VRAM_ABOVE_MAP = $6800

; El orden de prioridades del modo 3, de adelante hacia atrás, es
;   objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 / BG1 0 / objetos 0
; así que con el mapa en BG1 prioridad 0, el héroe en objetos prioridad 1 y la
; capa de encima en BG2 prioridad 1, el orden de RM2k sale del hardware sin
; ningún truco. Los eventos marcados "above" van en objetos prioridad 2, que es
; lo único que queda por encima de BG2.
OBJ_PRIORITY = $20      ; prioridad 1 en el byte de atributos
OBJ_PRIORITY_ABOVE = $30

; OBSEL: tamaño 8x8/32x32 en los bits altos, y la página de arriba en los bajos.
; Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño, así que se usa
; el objeto de 32x32 y sobra un poco a los costados.
OBSEL_VALUE = $21

; Las 12 poses: 3 frames de caminata por 4 direcciones. En RM2k las direcciones
; van 0=arriba, 1=derecha, 2=abajo, 3=izquierda, y el frame del medio es la
; pose parada.
DIR_UP    = 0
DIR_RIGHT = 1
DIR_DOWN  = 2
DIR_LEFT  = 3

; A velocidad 4, que es la del héroe, se avanzan dos pixeles por cuadro y la
; animación cambia de frame cada seis.
WALK_SPEED = 2
ANIM_FRAMES = 6

; El sprite se dibuja centrado sobre su celda de 16x16 y apoyado por los pies.
; Al objeto de 32 hay que restarle además los 4 que sobran de cada lado.
SPRITE_OFF_X = 8
SPRITE_OFF_Y = 16

; Filas visibles. La pantalla muestra 28 de las 32 del tilemap.
SCREEN_ROWS = 28

.include "musicdata.inc"
.include "mapdata.inc"

.segment "ZEROPAGE"
source:     .res 3      ; puntero al bloque que estamos subiendo
music:      .res 3      ; puntero dentro del stream de música
camara_x:   .res 2      ; dónde está mirando la cámara, en pixeles
camara_y:   .res 2
scroll_y:   .res 2      ; lo mismo menos uno, que es lo que el PPU quiere
pad:        .res 1      ; lo que el control tenía apretado este cuadro
temp:       .res 4      ; cuentas intermedias
hero_x:     .res 2      ; dónde está el héroe en el mapa, en pixeles
hero_y:     .res 2
hero_dir:   .res 1      ; hacia dónde mira
tile_x:     .res 1      ; y en qué celda de 16x16 está
tile_y:     .res 1
tile_index: .res 2      ; su posición dentro de la tabla de pasabilidad
target_index: .res 2    ; la de la celda a la que quiere ir
step_left:  .res 1      ; pixeles que faltan del paso en curso, 0 si no hay
step_dx:    .res 2      ; cuánto avanza por cuadro, con signo
step_dy:    .res 2
anim_step:  .res 1      ; en qué punto del ciclo de caminata va
anim_timer: .res 1      ; cuántos cuadros faltan para el frame siguiente
moving:     .res 1      ; si se movió este cuadro
oam_slot:   .res 2      ; en qué objeto de OAM vamos
npc_ofs:    .res 2      ; desplazamiento dentro de la tabla de NPCs
hero_key:   .res 2      ; la clave de orden del héroe
hero_drawn: .res 1      ; si ya se lo intercaló
high_acc:   .res 1      ; los bits de la tabla chica que se van juntando
high_ptr:   .res 2      ; y en qué byte de ella van. Dos bytes porque se usa
                        ; como índice, y `ldx` con X de 16 bits lee dos: con uno
                        ; solo tomaría de basura el byte alto.
obj_x:      .res 2      ; posición en pantalla del objeto que se está armando
obj_y:      .res 2
obj_tile:   .res 1
obj_attr:   .res 1
wait_frames: .res 1     ; cuántos cuadros faltan para el próximo evento
token:      .res 1      ; testigo del handshake con el SPC700
es_pal:     .res 1      ; 1 si la consola corre a 50 cuadros por segundo
pal_tick:   .res 1      ; para meter el cuadro de música que falta

.segment "CODE"

; --- arranque --------------------------------------------------------------
.proc reset
    sei
    clc
    xce                         ; a modo nativo del 65816
    rep #$30                    ; A, X e Y de 16 bits
.a16
.i16
    ldx #$1FFF
    txs

    sep #$20
.a8
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    ; La región no es un detalle cosmético: el stream de música está armado en
    ; cuadros, y una consola PAL da 50 por segundo en vez de 60. Sin corregirlo
    ; el tema suena un 17% lento.
    lda STAT78
    and #$10
    sta es_pal
    stz pal_tick

    jsr ppu_reset               ; la consola no arranca limpia; el emulador sí

    ; Después del reset, no antes: ppu_reset apaga NMITIMEN junto con todo lo
    ; demás, así que habilitarlo primero no serviría de nada.
    lda #$01
    sta NMITIMEN                ; que la consola lea los controles sola

    jsr ppu_init
    jsr load_map

    jsr load_sprite
    jsr clear_oam

    rep #$20
.a16
    lda #HERO_START_X
    sta hero_x
    lda #HERO_START_Y
    sta hero_y
    lda #HERO_START_TILE
    sta tile_index
    sep #$20
.a8
    lda #(HERO_START_X / 16)
    sta tile_x
    lda #(HERO_START_Y / 16)
    sta tile_y
    stz step_left               ; parado, sin paso en curso
    stz pad                     ; la RAM arranca con basura y move_hero la lee
    lda #DIR_DOWN
    sta hero_dir                ; mirando a cámara, como arranca RM2k
    lda #1
    sta anim_step               ; el frame del medio: la pose parada
    lda #ANIM_FRAMES
    sta anim_timer

    jsr follow_camera           ; deja el scroll en su lugar antes de encender
    jsr build_oam
    jsr flush_video

    lda #$0F
    sta INIDISP                 ; pantalla encendida, brillo al máximo

    ; La subida al SPC700 va después de prender la pantalla, no antes: son casi
    ; siete décimas de segundo, y así el mapa aparece de entrada en vez de
    ; hacerte mirar una pantalla negra hasta que termine.
    jsr spc_upload
    jsr music_start

loop:
    jsr wait_vblank
    ; El control primero: la consola lo lee sola al empezar el vblank y hay que
    ; esperar a que arranque. Si antes se hiciera algo largo —el DMA de OAM, por
    ; ejemplo— se llegaría con la lectura ya terminada, y esperar su arranque
    ; significaría esperar al cuadro siguiente: medio cuadro por vuelta.
    jsr read_pad
    jsr flush_video             ; lo del cuadro anterior, todavía en vblank
    jsr move_hero
    jsr animate_hero
    jsr follow_camera
    jsr build_oam               ; y se arma el siguiente, ya fuera del vblank
    jsr music_tick
    bra loop
.endproc

; --- espera de vblank ------------------------------------------------------
; Sin NMI habilitada, se mira la bandera de HVBJOY: primero que salga del
; vblank anterior y después que entre al siguiente.
.proc wait_vblank
.a8
.i16
out:
    lda HVBJOY
    bmi out
in:
    lda HVBJOY
    bpl in
    rts
.endproc

; --- puesta a cero del PPU -------------------------------------------------
; El emulador arranca con todos los registros en cero. La consola real no: se
; queda con lo que dejó el programa anterior, que en un EverDrive es su menú.
; Si ese menú dejó encendido el color math, el sub-screen, una ventana o un
; canal de HDMA, todo eso sigue funcionando debajo de nuestro mapa aunque
; nosotros no lo hayamos pedido.
;
; Por eso no alcanza con escribir los registros que usamos: hay que escribir
; todos. Es la misma lección que el registro 23 del VDP en la Mega Drive, donde
; también andaba en emulador y no en consola.
.proc ppu_reset
.a8
.i16
    lda #$80
    sta INIDISP                 ; blanking forzado antes de tocar nada

    ; Lo primero es cortar el DMA por scanline: si quedó un canal activo, sigue
    ; escribiendo registros del PPU en cada línea y nada de lo que hagamos acá
    ; se sostiene.
    stz HDMAEN
    stz MDMAEN
    stz NMITIMEN

    ; Los registros del PPU con valores conocidos, en dos tramos: los de scroll
    ; quedan en el medio y necesitan otro tratamiento.
    ldx #$0000
bajos:
    lda ppu_bajos, x
    sta $2101, x
    inx
    cpx #(ppu_bajos_end - ppu_bajos)
    bne bajos

    ldx #$0000
altos:
    lda ppu_altos, x
    sta $2115, x
    inx
    cpx #(ppu_altos_end - ppu_altos)
    bne altos

    ; Los ocho registros de scroll: cada uno se escribe dos veces, byte bajo y
    ; byte alto, o el latch queda a medias.
    ldx #$0000
scrolls:
    stz $210D, x
    stz $210D, x
    inx
    cpx #8
    bne scrolls

    ; La VRAM entera a cero, por DMA con la fuente fija en un byte nulo. Sin
    ; esto quedan los tiles del menú donde no llegan los nuestros.
    lda #$80
    sta VMAIN
    ldx #$0000
    stx VMADDL
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #$0000                  ; 0 significa 65536: la VRAM completa
    stx DAS0L
    lda #$09                    ; dos registros, de a palabras, fuente fija
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Y CGRAM, que si no deja la paleta del menú en los colores que no usamos.
    stz CGADD
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #512
    stx DAS0L
    lda #$08                    ; un registro, de a bytes, fuente fija
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; De $2101 a $210C: objetos, modo, mosaico y dónde vive cada capa. Todo en
; cero, que es "nada encendido".
.segment "TABLAS"
ppu_bajos:
    .byte $00,$00,$00,$00       ; $2101 OBSEL, $2102-3 OAMADD, $2104 OAMDATA
    .byte $00,$00,$00,$00       ; $2105 BGMODE, $2106 MOSAIC, $2107-8 BG1-2SC
    .byte $00,$00,$00,$00       ; $2109-A BG3-4SC, $210B-C BGxNBA
ppu_bajos_end:

; De $2115 a $2133: VRAM, modo 7, CGRAM, ventanas, capas visibles y color math.
; Los tres que no son cero son los que importan.
ppu_altos:
    .byte $80,$00,$00           ; $2115 VMAIN: avanzar tras el byte alto
    .byte $00,$00               ; $2118-9 VMDATA
    .byte $00,$00,$00,$00,$00   ; $211A-E modo 7
    .byte $00,$00               ; $211F-20 modo 7
    .byte $00,$00               ; $2121 CGADD, $2122 CGDATA
    .byte $00,$00,$00           ; $2123-5 selección de ventanas
    .byte $00,$00,$00,$00       ; $2126-9 posiciones de ventanas
    .byte $00,$00               ; $212A-B lógica de ventanas
    .byte $00,$00               ; $212C TM, $212D TS: ninguna capa visible
    .byte $00,$00               ; $212E TMW, $212F TSW
    .byte $30,$00               ; $2130 CGWSEL: color math apagado. $2131
    .byte $E0,$00               ; $2132 COLDATA: color fijo negro. $2133
ppu_altos_end:
cero:
    .byte $00,$00

.segment "CODE"

; --- el PPU ----------------------------------------------------------------
; Modo 3: BG1 con 8 bits por pixel. Ahí cada pixel es un índice directo a CGRAM
; y no hay paleta por tile, así que el mapa entra con sus 60 colores sin
; fusionar ninguno. Cuesta el doble de VRAM por tile y sobra lugar de todas
; formas.
.proc ppu_init
.a8
.i16
    lda #$03
    sta BGMODE
    ; BG1SC lleva la dirección del tilemap en el byte alto y el tamaño en los
    ; dos bits bajos; con VRAM_MAP en $6000 y tamaño 0 queda $60.
    lda #>VRAM_MAP | MAP_LAYOUT
    sta BG1SC                   ; tilemap acá, del tamaño que pida el mapa
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC                   ; y el tilemap de la capa de encima acá
    ; BG12NBA lleva las direcciones de los tiles de BG1 y BG2 en cada nibble, en
    ; unidades de 4K palabras: BG1 en la 0, BG2 en la $1000.
    lda #$10
    sta BG12NBA
    stz BG1HOFS                 ; el scroll es de dos escrituras, byte bajo
    stz BG1HOFS                 ; y byte alto
    ; El PPU muestra la línea vofs+1 en el primer scanline visible, no la vofs.
    ; Con 0 el mapa queda corrido una línea hacia arriba; con -1 cae en su
    ; lugar. Lo destapó la comparación pixel a pixel contra el render de Python:
    ; a ojo las dos imágenes se veían idénticas.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$13
    sta TM                      ; las dos capas del mapa y los sprites
    rts
.endproc

; --- volcado del mapa a la VRAM --------------------------------------------
; Todo por DMA y con la pantalla apagada, que es cuando se puede escribir la
; VRAM sin pelearle al PPU.
.proc load_map
.a8
.i16
    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    ldx #VRAM_TILES
    stx VMADDL
    ldx #.loword(map_tiles)
    stx A1T0L
    lda #^map_tiles
    sta A1B0
    ldy #(MAP_TILES * 64)
    sty DAS0L
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    stz CGADD
    ldx #.loword(map_cgram)
    stx A1T0L
    lda #^map_cgram
    sta A1B0
    ldy #(MAP_CGRAM * 2)
    sty DAS0L
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; --- el tilemap ---
    ; Viene del conversor ya acomodado como lo quiere la VRAM: las pantallas de
    ; 32x32 una detrás de la otra, no el mapa fila por fila. Por eso entra en un
    ; solo DMA en vez de treinta.
    ldx #VRAM_MAP
    stx VMADDL
    ldx #.loword(map_tilemap)
    stx A1T0L
    lda #^map_tilemap
    sta A1B0
    ldy #(MAP_CELLS * 2)
    sty DAS0L
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; --- los sprites -----------------------------------------------------------
.proc load_sprite
.a8
.i16
    lda #$80
    sta VMAIN
    ldx #VRAM_SPRITE
    stx VMADDL
    ldx #.loword(sprite_tiles)
    stx A1T0L
    lda #^sprite_tiles
    sta A1B0
    ldy #(SPRITE_TILES * 32)
    sty DAS0L
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; La paleta va a la mitad de arriba de CGRAM, que es la de los sprites: la
    ; 8 arranca en el color 128.
    lda #128
    sta CGADD
    ldx #.loword(sprite_cgram)
    stx A1T0L
    lda #^sprite_cgram
    sta A1B0
    ldy #(SPRITE_CGRAM * 2)
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    lda #OBSEL_VALUE
    sta OBSEL
    rts
.endproc

; --- OAM -------------------------------------------------------------------
; Todos los objetos arrancan escondidos. Un objeto de 32 de alto en la fila 224
; ocupa de la 224 a la 255, o sea entero fuera de las 224 que se ven, y sin
; darle la vuelta al contador.
.proc clear_oam
.a8
.i16
    ldx #$0000
borrar:
    lda #$E0
    sta oam + 1, x              ; la Y de cada objeto
    inx
    inx
    inx
    inx
    cpx #512
    bne borrar

    ; La tabla chica: dos bits por objeto, el alto dice si es grande. Sólo el
    ; objeto 0 lo es; el resto quedan chicos y escondidos igual.
    ldx #$0000
chica:
    stz oam_high, x
    inx
    cpx #32
    bne chica
    lda #$02
    sta oam_high                ; objeto 0: tamaño grande
    rts
.endproc

.proc push_oam
.a8
.i16
    stz OAMADDL
    stz OAMADDL + 1
    ldx #.loword(oam)
    stx A1T0L
    lda #^oam
    sta A1B0
    ldy #544                    ; los 512 de la tabla grande más los 32 chicos
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$04
    sta BBAD0                   ; destino: OAMDATA
    lda #$01
    sta MDMAEN

    ; --- la capa que va por encima del héroe ---
    ldx #VRAM_ABOVE
    stx VMADDL
    ldx #.loword(above_tiles)
    stx A1T0L
    lda #^above_tiles
    sta A1B0
    ldy #(ABOVE_TILES * 32)     ; son de 4 bits: 32 bytes por tile
    sty DAS0L
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ldx #VRAM_ABOVE_MAP
    stx VMADDL
    ldx #.loword(above_tilemap)
    stx A1T0L
    lda #^above_tilemap
    sta A1B0
    ldy #(MAP_CELLS * 2)
    sty DAS0L
    lda #$01
    sta MDMAEN

    ; Su paleta va en las dos últimas de la mitad baja de CGRAM, que el fondo
    ; de 8 bits deja libres a propósito.
    lda #ABOVE_FIRST
    sta CGADD
    ldx #.loword(above_cgram)
    stx A1T0L
    lda #^above_cgram
    sta A1B0
    ldy #(ABOVE_CGRAM * 2)
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; --- la cámara -------------------------------------------------------------
; Sigue al héroe: lo deja en el centro de la pantalla salvo cerca de los bordes
; del mapa, donde se queda pegada para no mostrar el vacío de afuera.
;
; El scroll es por hardware, así que esto son dos restas y dos escrituras. No
; hay que redibujar nada: el mapa entero ya está en el tilemap.
.proc follow_camera
.a8
.i16
    rep #$20
.a16
    lda hero_x
    clc
    adc #8                      ; el centro de su celda de 16x16
    sec
    sbc #128                    ; media pantalla de ancho
    bpl limite_x
    lda #0                      ; el héroe está cerca del borde izquierdo
limite_x:
    cmp #CAM_MAX_X
    bcc guarda_x
    lda #CAM_MAX_X
guarda_x:
    sta camara_x

    lda hero_y
    clc
    adc #8
    sec
    sbc #112                    ; media pantalla de alto
    bpl limite_y
    lda #0
limite_y:
    cmp #CAM_MAX_Y
    bcc guarda_y
    lda #CAM_MAX_Y
guarda_y:
    sta camara_y

    ; El PPU muestra la línea vofs+1 en el primer scanline, así que lo que se le
    ; escribe es siempre uno menos que dónde queremos mirar.
    dec a
    sta scroll_y
    sep #$20
.a8
    rts
.endproc

; --- lo que va sí o sí dentro del vblank -----------------------------------
; OAM sólo se puede escribir mientras el PPU no la está leyendo, o sea en el
; vblank. Armarla lleva su tiempo —con treinta y pico de personajes, más de un
; milisegundo— así que armarla y subirla en el mismo vblank no entra: la subida
; termina cayendo afuera y los objetos salen en cualquier lado.
;
; Por eso se sube lo del cuadro anterior apenas empieza el vblank, y recién
; después se arma la del siguiente. El scroll va junto, para que el fondo y los
; sprites correspondan al mismo momento.
.proc flush_video
.a8
.i16
    jsr push_oam

    ; Los dos registros de scroll son de escritura doble: primero el byte bajo
    ; y después el alto.
    ; Cada registro se completa antes de pasar al siguiente. Los de scroll
    ; comparten un único latch entre todos los planos, así que intercalar las
    ; escrituras —BG1 bajo, BG2 bajo, BG1 alto, BG2 alto— mezcla los valores y
    ; el plano queda desplazado dentro de su celda, moviéndose en el lugar.
    lda camara_x
    sta BG1HOFS
    lda camara_x + 1
    sta BG1HOFS
    lda camara_x
    sta BG2HOFS
    lda camara_x + 1
    sta BG2HOFS

    lda scroll_y
    sta BG1VOFS
    lda scroll_y + 1
    sta BG1VOFS
    lda scroll_y
    sta BG2VOFS
    lda scroll_y + 1
    sta BG2VOFS
    rts
.endproc

; --- el héroe --------------------------------------------------------------
; RM2k no mueve al personaje libremente: se compromete a una celda vecina y
; recorre los 16 pixeles hasta ella sin poder frenar. Por eso el estado es la
; celda donde está más cuántos pixeles le faltan del paso en curso, y mientras
; falten no se acepta otra dirección.
;
; Los cuatro bits de pasabilidad son: abajo $01, izquierda $02, derecha $04,
; arriba $08. Cruzar de una celda a la de al lado pide permiso a las dos: la de
; origen tiene que dejar salir por ese lado y la de destino dejar entrar por el
; opuesto. Todo lo demás —que la capa alta manda salvo que sea decorado, que las
; caras de pared se cruzan siempre— ya lo resolvió el conversor.

PASS_DOWN  = $01
PASS_LEFT  = $02
PASS_RIGHT = $04
PASS_UP    = $08

.proc move_hero
.a8
.i16
    ; Si hay un paso en curso, se termina: no se puede frenar a mitad de celda.
    lda step_left
    beq quieto
    jsr advance_step
    rts

quieto:
    stz moving
    lda pad
    and #PAD_UP
    beq no_arriba
    lda #DIR_UP
    sta hero_dir
    jsr try_up
    rts
no_arriba:
    lda pad
    and #PAD_DOWN
    beq no_abajo
    lda #DIR_DOWN
    sta hero_dir
    jsr try_down
    rts
no_abajo:
    lda pad
    and #PAD_LEFT
    beq no_izquierda
    lda #DIR_LEFT
    sta hero_dir
    jsr try_left
    rts
no_izquierda:
    lda pad
    and #PAD_RIGHT
    beq no_derecha
    lda #DIR_RIGHT
    sta hero_dir
    jsr try_right
no_derecha:
    rts
.endproc

; Cada intento comprueba el borde del mapa, después los dos permisos, y recién
; ahí arranca el paso.
.proc try_up
.a8
.i16
    lda tile_y
    beq no                      ; ya está en la fila de arriba
    lda #PASS_UP
    jsr can_leave
    beq no
    rep #$20
.a16
    lda tile_index
    sec
    sbc #PASS_WIDTH
    sta target_index
    sep #$20
.a8
    lda #PASS_DOWN              ; la celda de arriba tiene que dejar entrar
    jsr can_enter
    beq no
    dec tile_y
    rep #$20
.a16
    lda #0
    sta step_dx
    lda #-WALK_SPEED
    sta step_dy
    sep #$20
.a8
    jsr begin_step
no:
    rts
.endproc

.proc try_down
.a8
.i16
    lda tile_y
    inc a
    cmp #PASS_HEIGHT
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    rep #$20
.a16
    lda tile_index
    clc
    adc #PASS_WIDTH
    sta target_index
    sep #$20
.a8
    lda #PASS_UP
    jsr can_enter
    beq no
    inc tile_y
    rep #$20
.a16
    lda #0
    sta step_dx
    lda #WALK_SPEED
    sta step_dy
    sep #$20
.a8
    jsr begin_step
no:
    rts
.endproc

.proc try_left
.a8
.i16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    rep #$20
.a16
    lda tile_index
    dec a
    sta target_index
    sep #$20
.a8
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    dec tile_x
    rep #$20
.a16
    lda #-WALK_SPEED
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
no:
    rts
.endproc

.proc try_right
.a8
.i16
    lda tile_x
    inc a
    cmp #PASS_WIDTH
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    rep #$20
.a16
    lda tile_index
    inc a
    sta target_index
    sep #$20
.a8
    lda #PASS_LEFT
    jsr can_enter
    beq no
    inc tile_x
    rep #$20
.a16
    lda #WALK_SPEED
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
no:
    rts
.endproc

; A = el bit que hace falta. Devuelve con Z apagado si la celda lo tiene.
.proc can_leave
.a8
.i16
    sta temp
    ldx tile_index
    lda map_pass, x
    and temp
    rts
.endproc

.proc can_enter
.a8
.i16
    sta temp
    ldx target_index
    lda map_pass, x
    and temp
    rts
.endproc

; Arranca el paso: dieciséis pixeles por recorrer y el índice ya en la celda
; nueva, que es como RM2k lleva la cuenta.
.proc begin_step
.a8
.i16
    lda #16
    sta step_left
    rep #$20
.a16
    lda target_index
    sta tile_index              ; RM2k cuenta desde la celda de destino
    sep #$20
.a8
    jsr advance_step
    rts
.endproc

; Avanza los pixeles de este cuadro y, si con eso se completa el paso, deja al
; personaje exactamente sobre la celda.
.proc advance_step
.a8
.i16
    lda #$01
    sta moving
    rep #$20
.a16
    lda hero_x
    clc
    adc step_dx
    sta hero_x
    lda hero_y
    clc
    adc step_dy
    sta hero_y
    sep #$20
.a8
    lda step_left
    sec
    sbc #WALK_SPEED
    sta step_left
    rts
.endproc

; --- animación de caminata -------------------------------------------------
; El ciclo son cuatro pasos sobre tres frames del CharSet: 0, 1, 2, 1. El del
; medio es la pose parada, y es a la que se vuelve al soltar la cruceta.
.proc animate_hero
.a8
.i16
    lda moving
    bne caminando
    lda #1                      ; quieto: el frame del medio
    sta anim_step
    lda #ANIM_FRAMES
    sta anim_timer
    rts

caminando:
    dec anim_timer
    bne listo
    lda #ANIM_FRAMES
    sta anim_timer
    lda anim_step
    inc a
    and #$03                    ; el ciclo son cuatro pasos
    sta anim_step
listo:
    rts
.endproc

; --- armado de OAM ---------------------------------------------------------
; Un objeto por NPC más uno para el héroe, en el orden en que RM2k los dibuja:
; primero por capa y recién después por Y. En la consola el objeto con índice
; más bajo de OAM es el que se ve encima, así que se recorre del frente hacia el
; fondo — que es como el conversor dejó ordenada la tabla.
;
; El héroe se intercala donde le toca por su clave, no va siempre primero ni
; siempre último: un evento "below" tiene que quedar debajo de él aunque esté
; más adelante en pantalla, y uno "above" taparlo siempre.
.proc build_oam
.a8
.i16
    ; Todo escondido antes de empezar. Esconder sólo la cola al terminar deja
    ; los objetos que este cuadro no usó con los datos del anterior, y basta con
    ; que la cámara se mueva para que la cuenta cambie y alguno reaparezca donde
    ; no va. Son 128 escrituras y sacan de encima toda esa clase de error.
    jsr clear_oam
    stz high_acc
    stz hero_drawn
    rep #$20
.a16
    stz high_ptr
    stz oam_slot
    stz npc_ofs
    ; La clave del héroe: su capa arriba y su Y abajo, igual que en la tabla.
    lda hero_y
    and #$0FFF
    ora #(HERO_LAYER * 4096)
    sta hero_key
    sep #$20
.a8

recorrer:
    rep #$20
.a16
    lda npc_ofs
    cmp #(NPC_COUNT * NPC_STRIDE)
    sep #$20
.a8
    beq ultimos

    lda hero_drawn
    bne toca_npc
    ; ¿Va el héroe antes que este NPC? Sí si su clave es mayor o igual, porque
    ; la tabla va de mayor a menor.
    ldx npc_ofs
    rep #$20
.a16
    lda hero_key
    cmp npc_table + 4, x
    sep #$20
.a8
    bcc toca_npc
    jsr place_hero
    bra recorrer

toca_npc:
    jsr place_npc
    rep #$20
.a16
    lda npc_ofs
    clc
    adc #NPC_STRIDE
    sta npc_ofs
    sep #$20
.a8
    bra recorrer

ultimos:
    lda hero_drawn
    bne cerrar
    jsr place_hero
cerrar:
    jsr flush_high
    rts
.endproc

; --- un NPC ----------------------------------------------------------------
.proc place_npc
.a8
.i16
    ldx npc_ofs
    rep #$20
.a16
    lda npc_table + 0, x        ; su posición en el mapa
    sec
    sbc camara_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda npc_table + 2, x
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    sep #$20
.a8
    lda npc_table + 6, x
    sta obj_tile
    lda npc_table + 7, x
    sta obj_attr
    jsr emit_object
    rts
.endproc

; --- el héroe --------------------------------------------------------------
.proc place_hero
.a8
.i16
    inc hero_drawn

    ; El frame del CharSet: los pasos 0 y 2 son los de los costados, y los
    ; pasos 1 y 3 son los dos la pose del medio.
    lda anim_step
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    sta temp

    ; La pose es dirección*3 + frame, y cada una ocupa un bloque de 4x4 tiles
    ; dentro de una grilla de 16 de ancho: cuatro por fila de bloques.
    lda hero_dir
    asl a
    clc
    adc hero_dir                ; dirección * 3
    clc
    adc temp                    ; más el frame
    sta temp

    lsr a
    lsr a                       ; pose / 4 = fila de bloques
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; * 64 tiles por fila de bloques
    sta temp + 1
    lda temp
    and #$03                    ; pose módulo 4 = columna de bloques
    asl a
    asl a                       ; * 4 tiles
    clc
    adc temp + 1
    sta obj_tile
    lda #OBJ_PRIORITY           ; por debajo de la capa que lo tapa
    sta obj_attr

    rep #$20
.a16
    lda hero_x
    sec
    sbc camara_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda hero_y
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    sep #$20
.a8
    jsr emit_object
    rts
.endproc

; --- un objeto en OAM ------------------------------------------------------
; Descarta lo que caiga fuera de la pantalla: la X del objeto tiene nueve bits y
; la Y sólo ocho, así que un objeto lejano daría la vuelta y aparecería del otro
; lado. Se corren los rangos 32 pixeles para poder compararlos sin signo.
.proc emit_object
.a8
.i16
    rep #$20
.a16
    lda obj_x
    clc
    adc #32
    cmp #(256 + 64)
    sep #$20
.a8
    bcs fuera
    rep #$20
.a16
    lda obj_y
    clc
    adc #32
    cmp #(224 + 64)
    sep #$20
.a8
    bcs fuera

    rep #$20
.a16
    lda oam_slot
    asl a
    asl a
    tax                         ; cuatro bytes por objeto
    sep #$20
.a8
    lda obj_x
    sta oam, x
    lda obj_y
    sta oam + 1, x
    lda obj_tile
    sta oam + 2, x
    lda obj_attr
    sta oam + 3, x

    ; Sus dos bits en la tabla chica: el noveno de la X y el tamaño.
    lda obj_x + 1
    and #$01
    ora #$02                    ; todos los objetos son de 32x32
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
fuera:
    rts
.endproc

; Mete dos bits arriba del acumulador y lo corre. Después de cuatro objetos el
; byte queda armado en el orden que la consola espera.
.proc push_high
.a8
.i16
    pha
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    pla
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    ora high_acc
    sta high_acc

    lda oam_slot
    and #$03
    cmp #$03
    bne listo                   ; todavía no se completó el byte
    jsr store_high
listo:
    rts
.endproc

.proc store_high
.a8
.i16
    lda high_acc
    ldx high_ptr
    sta oam_high, x
    stz high_acc
    rep #$20
.a16
    inc high_ptr
    sep #$20
.a8
    rts
.endproc

; Al cerrar puede quedar un byte a medias. Se completa con objetos escondidos,
; que igual van a quedar con la Y fuera de pantalla.
.proc flush_high
.a8
.i16
completar:
    lda oam_slot
    and #$03
    beq listo
    lda #$02
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
    bra completar
listo:
    rts
.endproc

; --- lectura del control ---------------------------------------------------
; La consola lee los controles sola al empezar el vblank, pero tarda unos
; scanlines. El bit 0 de HVBJOY dice si todavía está en eso: leer antes devuelve
; basura a medio armar.
; La consola lee los controles sola al empezar el vblank, pero no arranca en el
; mismo ciclo en que el vblank empieza: tarda unas decenas de ciclos, y después
; unos cuatro scanlines en terminar. El bit 0 de HVBJOY vale 1 mientras está en
; eso.
;
; Preguntar sólo "¿terminó?" tiene una carrera: como wait_vblank devuelve justo
; al empezar el vblank, la lectura todavía no arrancó, el bit vale 0, y se pasa
; de largo leyendo los registros mientras la consola está por pisarlos. Cada
; tanto sale un valor a medio armar y ese cuadro se pierde el movimiento, que se
; ve como un tirón. Por eso hay que esperar primero a que empiece.
.proc read_pad
.a8
.i16
arranca:
    lda HVBJOY
    and #$01
    beq arranca                 ; todavía no empezó
termina:
    lda HVBJOY
    and #$01
    bne termina                 ; sigue leyendo
    lda JOY1H
    sta pad
    rts
.endproc

; --- carga al SPC700 -------------------------------------------------------
; El protocolo de la ROM interna del SPC700:
;
;   1. Espera a que salude con $AA en el puerto 0 y $BB en el 1.
;   2. Se le manda la dirección de destino por los puertos 2 y 3, un valor
;      distinto de cero por el 1, y $CC por el 0. Contesta con el mismo $CC.
;   3. Cada byte va por el puerto 1 y su índice por el 0; contesta el índice.
;   4. Para empezar otro bloque: la dirección nueva, algo distinto de cero por
;      el puerto 1, y el último índice más dos por el 0.
;   5. Para terminar: la dirección de entrada, un cero por el puerto 1, y el
;      último índice más dos por el 0. Ahí salta y arranca el driver.
;
; El $CC del paso 2 va sólo la primera vez; después manda el índice más dos.
.proc spc_upload
.a8
.i16
wait_ready:
    lda APUIO0
    cmp #$AA
    bne wait_ready
    lda APUIO1
    cmp #$BB
    bne wait_ready

    lda #$CC                    ; el arranque del primer bloque es fijo
    sta port0

    ; --- el driver ---
    ldx #.loword(spc_driver)
    stx source
    lda #^spc_driver
    sta source + 2
    ldx #SPC_DRIVER_ADDR
    ldy #SPC_DRIVER_SIZE
    jsr spc_block

    ; --- las muestras y su directorio ---
    ldx #.loword(spc_samples)
    stx source
    lda #^spc_samples
    sta source + 2
    ldx #SPC_SAMPLES_ADDR
    ldy #SPC_SAMPLES_SIZE
    jsr spc_block

    ; --- cerrar y saltar al driver ---
    ldx #SPC_DRIVER_ADDR
    stx APUIO2
    stz APUIO1                  ; cero por el puerto 1 = ejecutar
    lda port0
    sta APUIO0
wait_jump:
    cmp APUIO0
    bne wait_jump

    stz token
    rts
.endproc

; --- un bloque de la carga -------------------------------------------------
; X = dirección de destino, Y = cuántos bytes, source = de dónde salen.
; port0 trae con qué valor arrancar y queda listo para el bloque siguiente.
.proc spc_block
.a8
.i16
    stx APUIO2                  ; dirección de destino
    lda #$01
    sta APUIO1                  ; distinto de cero = seguir transfiriendo
    lda port0
    sta APUIO0
wait_start:
    cmp APUIO0
    bne wait_start

    ldx #$0000                  ; el índice arranca en cero en cada bloque
send:
    cpy #$0000
    beq done
    lda [source]
    sta APUIO1
    txa
    sta APUIO0
wait_byte:
    cmp APUIO0
    bne wait_byte

    inx
    dey
    ; El mismo salto de banco que en `advance`: las muestras pasan de 32 KB,
    ; así que la subida al SPC700 también cruza de un banco de LoROM al otro.
    inc source
    bne send
    inc source + 1
    bne send
    lda #$80
    sta source + 1
    inc source + 2
    bra send

done:
    ; El próximo bloque arranca con el último índice más dos.
    txa
    inc a
    inc a
    sta port0
    rts
.endproc

.segment "BSS"
port0: .res 1

; OAM se arma en RAM y se manda entero por DMA cada cuadro. Es más simple que
; escribir entradas sueltas, y es lo que va a hacer falta cuando haya NPCs.
; Son 128 objetos de cuatro bytes más una tabla chica de dos bits por objeto.
oam:      .res 512
oam_high: .res 32

.segment "CODE"

; --- música ----------------------------------------------------------------
; El stream son opcodes: escribir un registro del DSP, esperar cuadros, o fin.
OP_DSP  = $00
OP_WAIT = $01
OP_END  = $FF

; Un cuadro de música por cuadro de video, más uno extra cada cinco si la
; consola es PAL: seis cada cinco son exactamente 60 por cada 50.
.proc music_tick
.a8
.i16
    jsr music_frame
    lda es_pal
    beq listo
    inc pal_tick
    lda pal_tick
    cmp #5
    bcc listo
    stz pal_tick
    jsr music_frame             ; el cuadro que le falta a PAL
listo:
    rts
.endproc

.proc music_start
.a8
.i16
    ldx #.loword(md_music)
    stx music
    lda #^md_music
    sta music + 2
    stz wait_frames
    rts
.endproc

.proc music_frame
.a8
.i16
    lda wait_frames
    beq run
    dec wait_frames
    rts

run:
    lda [music]
    jsr advance
    cmp #OP_END
    bne check_wait
    jsr music_start             ; se terminó: de nuevo desde arriba
    bra run

check_wait:
    cmp #OP_WAIT
    bne write_dsp
    lda [music]
    jsr advance
    sta wait_frames
    beq run
    dec wait_frames
    rts

write_dsp:
    lda [music]                 ; registro del DSP
    jsr advance
    sta APUIO0
    lda [music]                 ; valor
    jsr advance
    sta APUIO1
    inc token                   ; el testigo le avisa al SPC700 que hay algo
    lda token
    sta APUIO3
wait_ack:
    cmp APUIO3
    bne wait_ack
    bra run
.endproc

; Avanza el puntero de música un byte, devolviendo en A lo que ya se leyó.
;
; En LoROM cada banco expone sólo su mitad alta, $8000-$FFFF, así que el byte
; que sigue a $00FFFF no es $010000 sino $018000. Un incremento común de 24 bits
; caería en la RAM del banco 1 y leería basura. Con el tema entero más las
; muestras pasando los 64 KB, esto no es teórico: se cruza sí o sí.
.proc advance
.a8
.i16
; El acumulador trae el byte que el llamador acaba de leer, así que hay que
; devolverlo intacto: por eso el pha/pla en la rama del salto de banco.
    inc music
    bne done
    inc music + 1
    bne done                    ; si la parte alta no dio la vuelta, listo
    pha
    lda #$80                    ; dio la vuelta: al banco siguiente, en $8000
    sta music + 1
    pla
    inc music + 2
done:
    rts
.endproc

; --- cabecera y vectores ---------------------------------------------------
.segment "HEADER"
    .byte "ABL SNES MUSIC POC   "  ; 21 caracteres
    .byte $20                      ; LoROM, velocidad lenta
    .byte $00                      ; sólo ROM, sin RAM ni chips extra
    .byte $07                      ; tamaño: 128 KB (el byte es log2 de los KB)
    .byte $00                      ; sin SRAM
    .byte $01                      ; región
    .byte $00                      ; desarrollador
    .byte $00                      ; versión
    .word $FFFF                    ; complemento del checksum
    .word $0000                    ; checksum

.segment "VECTORS"
; De $FFE0 a $FFFF. Los primeros ocho son los vectores del modo nativo y los
; otros ocho los del modo emulación, que es en el que arranca la consola. El
; que importa es RESET, en $FFFC.
    .word $0000     ; $FFE0  sin usar
    .word $0000     ; $FFE2  sin usar
    .word $0000     ; $FFE4  COP nativo
    .word $0000     ; $FFE6  BRK nativo
    .word $0000     ; $FFE8  ABORT nativo
    .word $0000     ; $FFEA  NMI nativo
    .word $0000     ; $FFEC  sin usar
    .word $0000     ; $FFEE  IRQ nativo
    .word $0000     ; $FFF0  sin usar
    .word $0000     ; $FFF2  sin usar
    .word $0000     ; $FFF4  COP en emulación
    .word $0000     ; $FFF6  sin usar
    .word $0000     ; $FFF8  ABORT en emulación
    .word $0000     ; $FFFA  NMI en emulación
    .word reset     ; $FFFC  RESET
    .word $0000     ; $FFFE  IRQ y BRK en emulación
