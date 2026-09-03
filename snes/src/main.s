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

; La consola multiplica y divide por hardware, que es lo único que hace falta
; para el tinte de pantalla: escala cada canal por un valor de 0 a 200 con 100
; como neutro, o sea multiplicar y dividir por cien. Las dos son exactas y con
; enteros, así que la referencia en Python puede hacer la misma cuenta y dar
; siempre lo mismo.
;
; El producto tarda 8 ciclos en estar listo y el cociente 16. No hay que
; esperarlos con un lazo: alcanza con no leer el resultado enseguida, y el
; código que hay en el medio ya alcanza.
WRMPYA   = $4202        ; multiplicando de 8 bits
WRMPYB   = $4203        ; multiplicador: escribirlo arranca la cuenta
RDMPYL   = $4216        ; el producto de 16 bits
WRDIVL   = $4204        ; dividendo de 16 bits
WRDIVH   = $4205
WRDIVB   = $4206        ; divisor de 8: escribirlo arranca la cuenta
RDDIVL   = $4214        ; el cociente de 16 bits

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

; La VRAM se direcciona por palabras y son 64 K en total. Cómo se reparte entre
; los tiles del fondo, los de la capa de encima, los de los sprites y los dos
; tilemaps no está acá: lo decide el conversor mapa por mapa y llega en
; mapdata.inc, junto con los valores ya armados de OBSEL y BG12NBA.
;
; No es una comodidad: el mapa que más tiles de fondo gasta necesita 620, y otro
; con muchos personajes necesita 512 de sprite. Los dos juntos no entran, y
; ninguno de los dos repartos sirve para todos los mapas.

; El orden de prioridades del modo 3, de adelante hacia atrás, es
;   objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 / BG1 0 / objetos 0
; así que con el mapa en BG1 prioridad 0, el héroe en objetos prioridad 1 y la
; capa de encima en BG2 prioridad 1, el orden de RM2k sale del hardware sin
; ningún truco. Los eventos marcados "above" van en objetos prioridad 2, que es
; lo único que queda por encima de BG2.
; En el byte de atributos de OAM —vhoopppN— la prioridad son los bits 5 y 4, o
; sea que el valor va corrido cuatro lugares: prioridad 1 es $10 y no $20. Con
; $20 el héroe quedaba en prioridad 2, que en este orden está *adelante* de
; BG2 1, y entonces se dibujaba encima de la capa que tenía que taparlo.
;
; Los dos valores los arma el conversor —la de cada NPC ya viene en su byte de
; atributos— y la del héroe llega como HERO_PRIORITY en mapdata.inc. Tenerlos
; acá además era la duplicación de siempre: dos lados que se pueden equivocar
; igual y una comparación que da cero. La del héroe es $10 en toda ROM que no
; sea la de `snes-encima`, que la sube a $20 para ejercitar la prioridad 2.

; Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño, así que se usa
; el objeto de 32x32 y sobra un poco a los costados. El valor de OBSEL, que
; lleva ese tamaño y la página de los tiles, lo arma el conversor.

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

; --- la ventana del mapa ---------------------------------------------------
; El tilemap del PPU son 64x32 celdas, o sea 512x256 pixeles, y la pantalla son
; 256x224. El mapa entero no entra: los del juego llegan a 1000x80 celdas. Lo
; que hay en la VRAM es una ventana que se mueve con la cámara.
;
; La ventana no se desplaza: se la trata como un toro. La celda (mx,my) del mapa
; vive siempre en la ranura (mx mod 64, my mod 32), y el scroll por hardware ya
; hace la vuelta sola porque 1024 —el máximo del registro— es múltiplo de 512.
; Así, cuando la cámara cruza el borde de una celda, sólo hay que reescribir la
; columna o la fila que acaba de entrar: la que sale está 32 columnas o 4 filas
; afuera de la pantalla y nadie la mira mientras tanto.
WINDOW_COLS = 64
WINDOW_ROWS = 32

; Cuántas celdas de 8x8 llega a tocar la pantalla. Son 32 y 28 justas más una,
; porque el scroll casi nunca cae parado sobre una celda.
VIEW_COLS = 33
VIEW_ROWS = 29

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
tile_x:     .res 2      ; y en qué celda de 16x16 está. Dos bytes: hay mapas de
tile_y:     .res 2      ; 500 celdas de ancho y en uno no entrarían
celdas:     .res 3      ; puntero a la fila de bloques donde arranca la ventana
celdas_ptr: .res 3      ; el mismo, mientras se recorre para armar una tira
win_col:    .res 2      ; la celda de 8x8 que quedó en el borde de la ventana
win_row:    .res 2      ; el cuadro pasado, para saber si la cámara la cruzó
win_block:  .res 2      ; y la fila de bloques a la que apunta `celdas`
col_addr:   .res 2      ; dónde va en la VRAM la columna recién armada
row_addr:   .res 2      ; ídem la fila; $0000 en las dos si no hay nada
tira_ofs:   .res 2      ; desplazamiento dentro del bloque, mientras se arma
tira_paso_col: .res 2   ; lo que mide una fila de bloques, en bytes
tira_resta: .res 2      ; cuántas celdas faltan por armar
hero_ptr:   .res 3      ; y en qué celda de la grilla, como puntero: se mueve
                        ; con él en vez de recalcularse
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

; El mapa que está cargado. Todo esto salía de constantes del .inc cuando había
; un mapa solo; ahora sale de su registro en `mapa_tabla` y vive acá mientras
; dure. Lo que se usa una sola vez —los tamaños de los DMA, las bases de VRAM—
; no se copia: se lee del registro en el momento.
mapa_ofs:    .res 2     ; el desplazamiento del registro del mapa actual
mapa_ancho:  .res 2     ; su ancho en celdas de 16x16
mapa_alto:   .res 2
mapa_cw:     .res 2     ; y en celdas de 8x8, que es el doble. Se guarda hecho
mapa_ch:     .res 2     ; porque el redibujado lo mira en cada columna y fila
npc_total:   .res 2     ; cuántos bytes ocupa la tabla de NPCs de este mapa
cam_max_x:   .res 2     ; hasta dónde puede llegar la cámara sin salirse
cam_max_y:   .res 2
bloques_ptr: .res 3     ; la tabla de bloques, que ya no entra en el banco 0
bloques8_ptr: .res 3    ; la misma corrida ocho bytes, que es donde arranca la
                        ; capa de encima dentro del bloque. Dos punteros salen
                        ; más baratos que ocho `iny` en el lazo más caliente.
pass_ptr:    .res 3     ; la pasabilidad, un byte por bloque
npc_ptr:     .res 3     ; y la de NPCs, sólo mientras se la copia a la RAM
puerta_ptr:  .res 3     ; la de puertas, mientras se la busca
entrada_x:   .res 2     ; por dónde entrar al mapa que se está por cargar, en
entrada_y:   .res 2     ; celdas. $FFFF quiere decir "donde diga el registro"

; El intérprete de eventos.
pag_ptr:     .res 3     ; la tabla de páginas del mapa cargado
cod_ptr:     .res 3     ; el código de la página que se está ejecutando
elegida:     .res 3     ; el código de la página que ganó, mientras se decide
elegida_hay: .res 1     ; si alguna página del evento en curso ganó
elegida_trigger: .res 1 ; y qué la dispara, para correr sólo las automáticas
ev_actual:   .res 2     ; qué evento se está resolviendo
salto_mapa:  .res 1     ; un Teleport pedido por un evento: a qué mapa
salto_x:     .res 2     ; y a qué celda. salto_hay dice si hay uno pendiente
salto_y:     .res 2
salto_hay:   .res 1
saltos_restantes: .res 1 ; cuántas cadenas de teletransporte quedan permitidas
; El grupo, en orden. El gráfico del héroe es el del primero —RM2k lo decide
; así, y `AddActor`/`RemoveActor` llaman los dos a `ResetGraphic`—, o sea que
; esto no es contabilidad: se ve en la pantalla. `hero_poses` apunta a las doce
; palabras de la tabla de actores del mapa que dicen qué tile es cada pose, y
; `hero_pal` a con qué paleta se dibuja.
grupo:       .res 4
grupo_n:     .res 2
hero_poses:  .res 3
hero_pal:    .res 1
; La página que se está mirando, ya leída de la tabla. Se copia en vez de
; leerse en el lugar porque Y hace de cursor de la tabla, y usarlo además para
; indexar el bitmap de switches vuelve el código imposible de seguir.
pag_ofs:     .res 2
pag_restan:  .res 2
pg_evento:   .res 2
pg_trigger:  .res 1
pg_sa:       .res 2
pg_sb:       .res 2
pg_cod:      .res 3
pg_actor:    .res 1     ; el actor que pide en el grupo, o 0
act_ptr:     .res 3     ; cursor de la tabla de actores del mapa
tinte_r:     .res 1     ; el tinte de pantalla, de 0 a 200 con 100 neutro
tinte_g:     .res 1
tinte_b:     .res 1
tin_ptr:     .res 3     ; la paleta que se está tiñendo, en la ROM
tin_count:   .res 2     ; cuántos colores tiene
tin_cgadd:   .res 1     ; y en qué entrada de CGRAM va
tin_fin:     .res 2     ; cuántos bytes mide, que es el tope del lazo

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

    ; Sin entrada puesta: el primer mapa arranca donde diga su registro.
    rep #$20
.a16
    lda #$FFFF
    sta entrada_x
    sep #$20
.a8

    ; Los switches arrancan todos apagados, como una partida nueva de RM2k, y
    ; la pantalla sin teñir.
    ldx #$0000
borrar_switches:
    stz switches, x
    inx
    cpx #SWITCH_BYTES
    bne borrar_switches
    lda #TINTE_NEUTRO
    sta tinte_r
    sta tinte_g
    sta tinte_b
    stz salto_hay
    ; El grupo va antes de cargar el primer mapa: `cargar_mapa` elige con
    ; qué se dibuja el héroe, y sin esto leería la basura con la que
    ; arranca la RAM. El grupo con el que arranca la partida la partida, de la base del juego. El gráfico
    ; del héroe sale del primero, así que esto decide qué sprite se ve; que en
    ; este juego el actor 10 sea invisible es dato del juego, no un error.
    ldx #$0000
copiar_grupo:
    cpx #GRUPO_INICIAL_N
    beq grupo_listo
    lda grupo_inicial, x
    sta grupo, x
    inx
    bra copiar_grupo
grupo_listo:
    rep #$20
.a16
    lda #GRUPO_INICIAL_N
    sta grupo_n                 ; de 16 bits: X e Y lo comparan enteros
    sep #$20
.a8

    ; Mirando a cámara, como arranca RM2k. Va antes de cargar el primer mapa
    ; porque ahí corren sus eventos, y una ruta forzada puede girarlo: si esto
    ; quedara después, pisaría lo que la ruta acaba de decidir.
    lda #DIR_DOWN
    sta hero_dir

    lda #MAPA_INICIAL
    jsr cargar_mapa
    jsr clear_oam

    stz step_left               ; parado, sin paso en curso
    stz pad                     ; la RAM arranca con basura y move_hero la lee
    lda #1
    sta anim_step               ; el frame del medio: la pose parada
    lda #ANIM_FRAMES
    sta anim_timer

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
    jsr stream_map              ; la columna o la fila que la cámara destapó
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
; Un bit por posición, para el bitmap de switches. Sale más barata que ocho
; corrimientos y se lee con el índice que ya tenemos.
mascara:
    .byte $01,$02,$04,$08,$10,$20,$40,$80

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
    ; dos bits bajos; con VRAM_MAP en $7000 y el tamaño 1 —dos pantallas de
    ; 32x32 una al lado de la otra, o sea 64x32— queda $71.
    lda #>VRAM_MAP | MAP_LAYOUT
    sta BG1SC                   ; la ventana del mapa, siempre de 64x32
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC                   ; y la de la capa de encima, del mismo tamaño
    ; BG12NBA sale del mapa, así que lo pone cargar_mapa. Acá quedaría con el
    ; valor del mapa anterior en cuanto haya más de uno.
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
; Carga entero el mapa cuyo índice viene en A: sus datos a la VRAM y a CGRAM,
; sus tablas a donde la ROM las busca, la cámara donde arranca el héroe y la
; ventana del tilemap llena. Es todo lo que hay que hacer para cambiar de mapa.
;
; Con la pantalla encendida esto no se puede llamar: escribe VRAM y CGRAM por
; DMA, que fuera del vblank el PPU no deja.
.proc cargar_mapa_sin_eventos
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por MAPA_STRIDE, que es 128
    sta mapa_ofs
    tax

    ; Lo que se mira seguido se copia; lo que se usa una vez se lee en el lugar.
    lda mapa_tabla + M_MAP_BW, x
    sta mapa_ancho
    asl a
    sta mapa_cw                 ; el ancho en celdas de 8x8 es el doble
    lda mapa_tabla + M_MAP_BH, x
    sta mapa_alto
    asl a
    sta mapa_ch
    lda mapa_tabla + M_CAM_MAX_X, x
    sta cam_max_x
    lda mapa_tabla + M_CAM_MAX_Y, x
    sta cam_max_y
    lda mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a                       ; NPC_STRIDE bytes por NPC
    sta npc_total

    ; Los punteros a las dos tablas que se leen desde la ROM. El segundo apunta
    ; ocho bytes más adelante, que es donde cada bloque guarda su capa de
    ; encima; sumar ocho no puede desbordar el banco porque `.bloque` garantiza
    ; que la tabla entera entra en uno.
    lda mapa_tabla + M_PTR_MAP_BLOQUES, x
    sta bloques_ptr
    clc
    adc #8
    sta bloques8_ptr
    lda mapa_tabla + M_PTR_BLOQUE_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda mapa_tabla + M_PTR_MAP_BLOQUES + 2, x
    sta bloques_ptr + 2
    sta bloques8_ptr + 2
    lda mapa_tabla + M_PTR_BLOQUE_PASS + 2, x
    sta pass_ptr + 2

    ; Dónde arranca el héroe: donde diga el registro, salvo que quien llamó haya
    ; dejado una entrada puesta, que es lo que hace una puerta. La cámara se
    ; acomoda antes de llenar la ventana, porque la ventana se llena alrededor
    ; de ella.
    rep #$20
.a16
    lda entrada_x
    cmp #$FFFF
    bne desde_puerta
    lda mapa_tabla + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda mapa_tabla + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra puesto

desde_puerta:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida: la próxima carga vuelve al registro

puesto:
    sep #$20
.a8
    lda mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA

    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    ; La tabla de actores es de este mapa, así que dónde caen las poses del
    ; líder cambia al cambiar de mapa aunque el grupo sea el mismo.
    jsr elegir_grafico_heroe
    jsr fill_window             ; deja listo tira_paso_col, que el otro usa
    jsr init_hero_ptr

    ; El tinte es estado del juego, no del mapa: sobrevive al teletransporte.
    ; Las paletas que se acaban de subir son las del cartucho, sin teñir, así
    ; que se vuelven a teñir acá. Con el tinte neutro la cuenta es i*100/100 y
    ; deja los colores donde estaban, así que no hace falta preguntar si hay
    ; tinte: el camino es siempre el mismo.
    jsr aplicar_tinte
    rts
.endproc

; Y esto es lo que hay que llamar: carga el mapa y le corre los eventos
; automáticos.
;
; Si un evento pide un teletransporte, el ciclo se repite acá y no adentro del
; intérprete. Llamar a cargar_mapa desde el intérprete sería recursión, y dos
; mapas que se apuntan entre sí la harían infinita: la pila se va al fondo y la
; consola hace cualquier cosa. El tope de vueltas está por la misma razón, para
; el caso en que se apunten con un ciclo más largo.
.proc cargar_mapa
.a8
.i16
    pha                         ; el índice del mapa, que lo de abajo pisaría
    lda #8
    sta saltos_restantes        ; con stx serían dos bytes y pisaría el de al lado
    pla
    jsr cargar_mapa_sin_eventos
otra_vez:
    jsr correr_eventos
    lda salto_hay
    beq listo
    stz salto_hay
    rep #$20
.a16
    lda salto_x
    sta entrada_x
    lda salto_y
    sta entrada_y
    sep #$20
.a8
    dec saltos_restantes
    beq listo                   ; demasiadas vueltas: se queda en este mapa
    lda salto_mapa
    jsr cargar_mapa_sin_eventos
    bra otra_vez
listo:
    rts
.endproc

; --- el intérprete de eventos ----------------------------------------------
;
; RM2k se queda con la página de número más alto cuyas condiciones se cumplen
; todas. Las páginas vienen agrupadas por evento y en orden, así que alcanza una
; sola pasada: se recuerda la última que cumplió, y al cambiar de evento se
; ejecuta la que haya quedado.
;
; Sólo se corren las automáticas. Las de contacto ya las cubren las puertas, y
; las de botón necesitan que haya un botón que apretar.
.proc correr_eventos
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_PAGINA_COUNT, x
    bne hay_paginas
    ; Salir por acá sin volver a 8 bits dejaría al que llama con el acumulador
    ; del ancho equivocado. El ancho es estado y se escapa de las rutinas.
    sep #$20
.a8
    rts
hay_paginas:
    rep #$20
.a16
    sta pag_restan
    lda mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz elegida_hay

    jsr leer_pagina
    rep #$20
.a16
    lda pg_evento
    sta ev_actual
    sep #$20
.a8

recorrer:
    jsr leer_pagina
    rep #$20
.a16
    lda pg_evento
    cmp ev_actual
    sep #$20
.a8
    beq mismo_evento

    jsr ejecutar_elegida
    lda salto_hay
    bne nada                    ; un teletransporte corta el resto
    rep #$20
.a16
    lda pg_evento
    sta ev_actual
    sep #$20
.a8
    stz elegida_hay

mismo_evento:
    jsr condiciones_ok
    beq siguiente               ; no se cumplen: esta página no compite
    ; Gana, por ahora: es la de número más alto que cumplió hasta acá.
    lda pg_trigger
    sta elegida_trigger
    rep #$20
.a16
    lda pg_cod
    sta elegida
    sep #$20
.a8
    lda pg_cod + 2
    sta elegida + 2
    lda #1
    sta elegida_hay

siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    bne recorrer

    jsr ejecutar_elegida
nada:
    rts
.endproc

; Los campos de la página que está en pag_ofs, a variables.
.proc leer_pagina
.a8
.i16
    ldy pag_ofs
    rep #$20
.a16
    lda [pag_ptr], y            ; +0  a qué evento pertenece
    sta pg_evento
    sep #$20
.a8
    iny
    iny
    iny
    lda [pag_ptr], y            ; +3  qué la dispara. De a un byte: leerlo de a
    sta pg_trigger              ;     dos se llevaría puesto el switch de al lado
    iny
    rep #$20
.a16
    lda [pag_ptr], y            ; +4  el switch que pide, o 0
    sta pg_sa
    iny
    iny
    lda [pag_ptr], y            ; +6  el segundo, o 0
    sta pg_sb
    iny
    iny
    lda [pag_ptr], y            ; +8  su código: los 16 bits bajos
    sta pg_cod
    sep #$20
.a8
    iny
    iny
    lda [pag_ptr], y            ; +10 y su banco
    sta pg_cod + 2
    iny
    lda [pag_ptr], y            ; +11 el actor que pide en el grupo, o 0
    sta pg_actor
    rts
.endproc

; ¿Se cumplen las condiciones de la página leída? Vuelve con Z=0 si sí.
; Un switch en 0 quiere decir "esta página no lo pide".
.proc condiciones_ok
.a8
.i16
    rep #$20
.a16
    lda pg_sa
    beq mirar_b
    jsr switch_encendido
    beq falla
mirar_b:
    lda pg_sb
    beq cumple
    jsr switch_encendido
    beq falla
cumple:
    sep #$20
.a8
    ; Y la condición de grupo: un 0 quiere decir "esta página no pide a nadie".
    lda pg_actor
    beq cumple8
    jsr en_el_grupo
    beq falla8
cumple8:
    lda #1                      ; Z=0
    rts
falla8:
    lda #0                      ; Z=1
    rts
sin_usar:
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
falla:
    sep #$20
.a8
    lda #0                      ; Z=1
    rts
.endproc

; ¿Está encendido el switch cuyo número viene en A? Vuelve con Z=0 si sí.
.proc switch_encendido
.a16
.i16
    pha
    and #$0007
    tax                         ; el bit dentro del byte
    pla
    lsr a
    lsr a
    lsr a
    tay                         ; y qué byte del bitmap
    sep #$20
.a8
    lda switches, y
    and mascara, x
    rep #$20
.a16
    rts                         ; rep no toca Z, así que el and sigue valiendo
.endproc

; Corre la página que ganó, si ganó alguna, es automática y tiene código.
.proc ejecutar_elegida
.a8
.i16
    lda elegida_hay
    beq no
    lda elegida_trigger
    cmp #TRIGGER_AUTOMATICO
    bne no
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq no                      ; sin código: no se pudo compilar
    rep #$20
.a16
    lda elegida
    sta cod_ptr
    sep #$20
.a8
    lda elegida + 2
    sta cod_ptr + 2
    stz elegida_hay             ; que no se ejecute dos veces
    jsr correr_codigo
no:
    rts
.endproc

; El bucle del intérprete: un opcode por vuelta hasta el FIN.
;
; Y es el cursor del bytecode y tiene que sobrevivir a todo el bucle, así que
; cada `jsr` que sale de acá lo guarda antes de irse. Las rutinas que se llaman
; usan X e Y para lo suyo —poner_switch indexa el bitmap de switches,
; aplicar_tinte recorre tres paletas— y ninguna tiene por qué saber que acá
; significan otra cosa. Sin esto, el primer OP_SWITCH dejaba a Y valiendo el
; número del switch dividido ocho, y lo que se leía como opcode siguiente era
; un byte cualquiera del medio de la página: el bucle cortaba ahí y el resto no
; corría.
.proc correr_codigo
.a8
.i16
    ldy #$0000
otro:
    lda [cod_ptr], y
    iny
    cmp #OP_SWITCH
    beq op_switch
    cmp #OP_TELEPORT
    beq op_teleport
    cmp #OP_ESPERAR
    beq op_esperar
    cmp #OP_TINTE
    beq op_tinte
    cmp #OP_GRUPO
    beq op_grupo
    cmp #OP_RUTA
    beq op_ruta
    rts                         ; OP_FIN, o algo que no conocemos: se corta

op_switch:
    rep #$20
.a16
    lda [cod_ptr], y            ; el número, de 16 bits
    sta temp
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y si va encendido o apagado
    iny
    phy
    jsr poner_switch
    ply
    bra otro

; Una ruta forzada de MoveEvent, siempre sobre el héroe. De todos los comandos
; de ruta de RM2k acá se aceptan sólo los cuatro de girar y la espera: el
; conversor no emite ningún otro. Moverse por una ruta forzada no está, porque
; ninguna página del juego que compile lo ejercita —y sin con qué compararlo, ya
; se sabe cómo termina—.
;
; face_up/right/down/left son 12, 13, 14 y 15, y nuestras direcciones son
; 0, 1, 2 y 3 en el mismo orden, así que restar doce alcanza. La espera, 23, no
; hace nada: la página corre entera de una, igual que con OP_ESPERAR.
op_ruta:
    lda [cod_ptr], y            ; cuántos comandos trae
    sta temp
    iny
cada_orden:
    lda temp
    beq fin_ruta
    dec temp
    lda [cod_ptr], y
    iny
    sec
    sbc #12
    cmp #4
    bcs cada_orden              ; no es un face_*: se saltea
    sta hero_dir
    bra cada_orden
fin_ruta:
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

op_grupo:
    lda [cod_ptr], y            ; 0 = agregar, 1 = sacar
    sta temp
    iny
    lda [cod_ptr], y            ; el actor
    iny
    phy
    jsr cambiar_grupo
    ply
    bra otro

op_esperar:
    ; La espera se saltea. No tenemos cuadros que dejar pasar acá: esto corre
    ; con la pantalla apagada mientras se carga el mapa, y lo que se compara es
    ; la pantalla ya asentada. Lo que se pierde es el tiempo, no la imagen.
    iny
    bra otro

op_tinte:
    lda [cod_ptr], y
    sta tinte_r
    iny
    lda [cod_ptr], y
    sta tinte_g
    iny
    lda [cod_ptr], y
    sta tinte_b
    iny
    iny                         ; la saturación: el conversor sólo deja pasar
                                ; la neutra, así que no hay nada que hacer
    phy
    jsr aplicar_tinte
    ply
    bra otro

op_teleport:
    lda [cod_ptr], y
    sta salto_mapa
    iny
    rep #$20
.a16
    lda [cod_ptr], y
    sta salto_x
    iny
    iny
    lda [cod_ptr], y
    sta salto_y
    sep #$20
.a8
    lda #1
    sta salto_hay
    iny                         ; los dos bytes de la Y, que se leyeron sin
    iny                         ; avanzar el cursor
    ; Y se sigue con el resto de la página. Acá había un `rts` que decía "el
    ; resto no corre: RM2k tampoco", y era falso: en
    ; `Game_Interpreter_Map::CommandTeleport` el motor *reserva* el
    ; teletransporte, hace `index++` y devuelve false, o sea que corta el cuadro
    ; pero retoma en el comando siguiente una vez hecho el cambio de mapa.
    ;
    ; Acá la página entera corre de una, así que "retomar después" y "seguir" es
    ; lo mismo, y con dos teletransportes gana el último —que es también dónde
    ; RM2k deja al héroe—. Ninguna página del juego que hoy compile tiene
    ; comandos después de un teletransporte, así que este camino todavía no lo
    ; ejercita ninguna prueba: está en la lista de ESTADO.md. Lo va a ejercitar
    ; la cinemática de apertura, que tiene once comandos después del primero.
    jmp otro                    ; `bra` no llega: el lazo quedó lejos
.endproc

; --- el tinte de pantalla --------------------------------------------------
;
; RM2k escala cada canal por un valor de 0 a 200, con 100 como neutro. En una
; consola con paleta eso no es un efecto de pantalla sino una transformación de
; la paleta: se escalan los colores al subirlos y el fondo, que va en 8 bits por
; pixel y direcciona CGRAM en directo, queda teñido exactamente.
;
; La cuenta es `i * valor / 100` con enteros. Las dos operaciones las hace el
; hardware y son exactas, así que la referencia en Python hace la misma cuenta
; y da siempre lo mismo. Una aproximación con corrimientos no serviría: la
; comparación es pixel por pixel.

; t[i] = i * valor / 100 para i de 0 a 31, topado en 31. A = valor, X = tabla.
.proc tabla_canal
.a8
.i16
    sta temp                    ; el valor del canal
    stx temp + 2                ; dónde va la tabla
    ldy #$0000
cada:
    tya
    sta WRMPYA
    lda temp
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #100
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc cabe
    lda #31                     ; el canal tiene cinco bits y no más
cabe:
    sta (temp + 2), y
    iny
    cpy #32
    bne cada
    rts
.endproc

; Lee una paleta de la ROM, la tiñe color por color y la sube a CGRAM.
.proc tenir_paleta
.a8
.i16
    ; La cuenta va en Y y no en X: adentro del lazo X es el índice de las tres
    ; tablas de canal, así que al llegar acá vale el azul del color anterior y
    ; no cuántos colores van. Y sí sobrevive: es el cursor de la paleta.
    rep #$20
.a16
    lda tin_count
    asl a                       ; dos bytes por color
    sta tin_fin
    sep #$20
.a8
    ; Ni `sta` ni `sep` tocan Z, así que esto mira el `asl`. Una paleta sin
    ; colores se va sin hacer nada: el DMA de abajo mediría cero bytes, que en
    ; el hardware son 64 KB, y llenaría CGRAM de basura.
    bne hay_colores
    rts
hay_colores:
    ldy #$0000
cada_color:
    cpy tin_fin
    beq subir
    rep #$20
.a16
    lda [tin_ptr], y
    sta temp                    ; el color original, de 15 bits

    and #$001F                  ; rojo
    tax
    sep #$20
.a8
    lda tabla_r, x
    sta temp + 2
    rep #$20
.a16
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; verde
    tax
    sep #$20
.a8
    lda tabla_g, x
    sta temp + 3
    rep #$20
.a16
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; azul
    tax
    sep #$20
.a8
    lda tabla_b, x
    rep #$20
.a16
    and #$001F
    xba                         ; el azul va en los bits 10 a 14: ocho lugares
    asl a                       ; los da el intercambio de bytes y los dos que
    asl a                       ; faltan, dos corrimientos. Diez `asl` seguidos
                                ; se cuentan mal, y así fue como salieron cinco
    sta temp
    lda temp + 2
    and #$001F                  ; el rojo, sin el verde que quedó al lado
    ora temp
    sta temp
    lda temp + 3
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a                       ; y el verde en los bits 5 a 9
    ora temp
    sta pal_buf, y

    iny
    iny
    sep #$20
.a8
    bra cada_color

subir:
    lda tin_cgadd
    sta CGADD
    rep #$20
.a16
    lda #.loword(pal_buf)
    sta A1T0L
    lda tin_count
    asl a                       ; dos bytes por color
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; pal_buf vive en el banco 0
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; El tinte que dejó el evento, aplicado a las tres paletas del mapa.
.proc aplicar_tinte
.a8
.i16
    lda tinte_r
    ldx #.loword(tabla_r)
    jsr tabla_canal
    lda tinte_g
    ldx #.loword(tabla_g)
    jsr tabla_canal
    lda tinte_b
    ldx #.loword(tabla_b)
    jsr tabla_canal

    ; El fondo, desde la entrada 0.
    ldx #M_PTR_MAP_CGRAM
    ldy #M_MAP_CGRAM
    lda #0
    jsr una_paleta

    ; La capa de encima, en la entrada que le haya tocado a este mapa. Hay que
    ; leerla del registro antes de cargar X con el campo, porque el registro se
    ; direcciona justamente con X.
    ldx mapa_ofs
    lda mapa_tabla + M_ABOVE_FIRST, x
    pha
    ldx #M_PTR_ABOVE_CGRAM
    ldy #M_ABOVE_CGRAM
    pla
    jsr una_paleta

    ; Y los sprites, en la mitad de arriba de CGRAM.
    ldx #M_PTR_SPRITE_CGRAM
    ldy #M_SPRITE_CGRAM
    lda #128
    jsr una_paleta
    rts
.endproc

; Tiñe y sube una de las paletas del mapa. X = el campo del puntero, Y = el
; campo de la cantidad, A = en qué entrada de CGRAM arranca.
.proc una_paleta
.a8
.i16
    sta tin_cgadd
    stx temp
    sty temp + 2

    rep #$20
.a16
    lda temp
    clc
    adc mapa_ofs
    tax
    lda mapa_tabla, x
    sta tin_ptr
    sep #$20
.a8
    lda mapa_tabla + 2, x
    sta tin_ptr + 2

    rep #$20
.a16
    lda temp + 2
    clc
    adc mapa_ofs
    tax
    lda mapa_tabla, x
    sta tin_count
    sep #$20
.a8
    jsr tenir_paleta
    rts
.endproc

; ¿Está el actor de A en el grupo? Vuelve con Z=0 si sí.
.proc en_el_grupo
.a8
.i16
    ldx #$0000
busca:
    cpx grupo_n                 ; grupo_n es de 16 bits a propósito: con .i16
    beq no_esta                 ; esta comparación lee dos bytes igual
    cmp grupo, x
    beq esta
    inx
    bra busca
esta:
    lda #1                      ; Z=0
    rts
no_esta:
    lda #0                      ; Z=1
    rts
.endproc

; Agrega o saca un actor del grupo y recalcula con qué se dibuja el héroe.
; A = el actor, temp = 0 para agregar y 1 para sacar.
;
; Las reglas son las de `Game_Party::AddActor` y `RemoveActor`: agregar a
; alguien que ya está no lo duplica ni lo mueve de lugar, agregar con el grupo
; lleno no hace nada, y sacar a alguien que no está tampoco. El orden importa
; porque el primero es el que se dibuja.
.proc cambiar_grupo
.a8
.i16
    ldx #$0000
buscar:
    cpx grupo_n
    beq no_estaba
    cmp grupo, x
    beq estaba
    inx
    bra buscar

estaba:
    ; `temp` se mira con A y no con `ldy temp`: con .i16 eso leería dos bytes y
    ; el de al lado no es nuestro. Es la trampa del ancho de los índices, que ya
    ; está anotada en el LEEME, y acá dio exactamente el síntoma que promete:
    ; ningún cambio de grupo tenía efecto y no había ningún error.
    pha
    lda temp
    beq era_agregar             ; agregar uno que ya está: nada que hacer
    pla
    ; Sacarlo: se corren los de atrás un lugar.
correr:
    inx
    cpx grupo_n
    beq acortar
    lda grupo, x
    sta grupo - 1, x
    bra correr
acortar:
    rep #$20
.a16
    dec grupo_n
    sep #$20
.a8
    bra listo
era_agregar:
    pla
    bra listo

no_estaba:
    pha
    lda temp
    bne era_sacar               ; sacar uno que no está: nada que hacer
    pla
    cpx #GRUPO_MAX
    beq listo                   ; lleno: RM2k tampoco lo agrega
    sta grupo, x
    rep #$20
.a16
    inc grupo_n
    sep #$20
.a8
    bra listo
era_sacar:
    pla

listo:
    jsr elegir_grafico_heroe
    rts
.endproc

; Con qué se dibuja el héroe: se busca al primero del grupo en la tabla de
; actores del mapa y se guardan sus doce poses y su paleta.
;
; Antes esto no existía: el héroe era siempre el personaje 0 del banco de
; sprites y el tile de cada pose salía de una cuenta. Con el grupo cambiando en
; caliente ya no alcanza, y además el tile puede pasar de ocho bits cuando hay
; varios personajes, así que se lee de una tabla.
.proc elegir_grafico_heroe
.a8
.i16
    stz hero_pal
    rep #$20
.a16
    stz hero_poses
    sep #$20
.a8
    stz hero_poses + 2
    lda grupo_n
    beq sin_lider               ; grupo vacío: no se dibuja nada

    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_ACTOR_COUNT, x
    beq sin_lider16
    sta temp + 2
    lda mapa_tabla + M_PTR_ACTOR_TABLE, x
    sta act_ptr
    sep #$20
.a8
    lda mapa_tabla + M_PTR_ACTOR_TABLE + 2, x
    sta act_ptr + 2

    ldy #$0000
    lda grupo                   ; el líder
    sta temp
cada_actor:
    lda [act_ptr], y
    cmp temp
    beq lo_encontre
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_BYTES
    tay
    dec temp + 2
    sep #$20
.a8
    bne cada_actor
    bra sin_lider

lo_encontre:
    iny
    lda [act_ptr], y            ; su paleta, ya corrida a su lugar en vhoopppN
    asl a
    and #$0E
    sta hero_pal
    iny                         ; y acá arrancan las doce palabras
    rep #$20
.a16
    tya
    clc
    adc act_ptr
    sta hero_poses
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_poses + 2
    rts

sin_lider16:
    sep #$20
.a8
sin_lider:
    rts
.endproc

; Enciende o apaga el switch de temp según A.
.proc poner_switch
.a8
.i16
    pha
    rep #$20
.a16
    lda temp
    and #$0007
    tax
    lda temp
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
.a8
    pla
    beq apagar
    lda switches, y
    ora mascara, x
    sta switches, y
    rts
apagar:
    lda mascara, x
    eor #$FF
    and switches, y
    sta switches, y
    rts
.endproc

; Deja en A1T0L/A1B0 el puntero de 24 bits que el registro del mapa guarda en el
; campo que venga en Y. Los tres bytes del puntero están seguidos, así que la
; parte baja sale de una lectura de 16 bits y el banco de la de al lado.
; La cuenta va con el acumulador en 16 bits de punta a punta. Hacerla en 8 y
; después `tax` no sirve: el acumulador del 65816 son 16 bits siempre, y `tax`
; con X ancho transfiere los dos bytes, incluido el alto que quedó de la
; operación anterior. Con el mapa 7 daba cero de casualidad para los tiles y
; basura para la paleta.
.proc dma_origen
.a8
.i16
    rep #$20
.a16
    tya                         ; el desplazamiento del campo
    clc
    adc mapa_ofs
    tax
    lda mapa_tabla, x
    sta A1T0L
    sep #$20
.a8
    lda mapa_tabla + 2, x
    sta A1B0
    rts
.endproc

.proc load_map
.a8
.i16
    ldx mapa_ofs
    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda mapa_tabla + M_VRAM_TILES, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_MAP_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_MAP_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 64 bytes por tile de 8 bits
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    stz CGADD
    ldy #M_PTR_MAP_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_MAP_CGRAM, x
    asl a                       ; dos bytes por color
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; El tilemap no se sube acá: no existe uno entero para subir. Lo arma
    ; fill_window a partir de los bloques, y desde ahí lo mantiene el streaming.
    rts
.endproc

; --- los sprites -----------------------------------------------------------
.proc load_sprite
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda mapa_tabla + M_VRAM_SPRITE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_SPRITE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_SPRITE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por tile de 4 bits
    sta DAS0L
    sep #$20
.a8
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
    ldy #M_PTR_SPRITE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_SPRITE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    lda mapa_tabla + M_OBSEL_VALUE, x
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
    rts
.endproc

; --- la capa que va por encima del héroe -----------------------------------
; Sus tiles y su paleta se suben una sola vez, con la pantalla apagada. Su
; tilemap no: va en la misma ventana móvil que el del fondo, y lo llena el
; streaming.
.proc load_above
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda mapa_tabla + M_VRAM_ABOVE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_ABOVE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_ABOVE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; son de 4 bits: 32 bytes por tile
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Su paleta va en las últimas paletas de la mitad baja de CGRAM, que el
    ; fondo de 8 bits deja libres. Cuántas y desde dónde lo decidió el
    ; conversor mapa por mapa, así que viene en el registro.
    lda mapa_tabla + M_ABOVE_FIRST, x
    sta CGADD
    ldy #M_PTR_ABOVE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_ABOVE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; La tabla de NPCs a la RAM, que es de donde build_oam la lee.
;
; Con un lazo y no con un DMA: para llegar a la WRAM el DMA tiene que pasar por
; el puerto $2180 y dejar la dirección puesta en $2181-$2183, que son tres
; registros más que acordarse de cargar. Son mil bytes como mucho y esto corre
; una vez por mapa, así que el lazo no le cuesta nada a nadie y no puede
; escribir en el lugar equivocado.
.proc load_npcs
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_NPC_TABLE
    clc
    adc mapa_ofs
    tax
    lda mapa_tabla, x           ; los 16 bits bajos del puntero
    sta npc_ptr
    sep #$20
.a8
    lda mapa_tabla + 2, x       ; y su banco
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a                       ; NPC_STRIDE bytes por NPC
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq listo
    lda [npc_ptr], y
    sta npc_buf, y
    iny
    bra copiar
listo:
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
    cmp cam_max_x
    bcc guarda_x
    lda cam_max_x
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
    cmp cam_max_y
    bcc guarda_y
    lda cam_max_y
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

; --- la ventana móvil del mapa ---------------------------------------------
; El tilemap del PPU son 64x32 celdas y los mapas del juego llegan a 1000x80:
; el mapa entero nunca está en la VRAM. Lo que hay es una ventana que se trata
; como un toro —la celda (mx,my) vive siempre en la ranura (mx mod 64, my mod
; 32)— y que se mantiene reescribiendo la columna o la fila que acaba de entrar
; en pantalla. La que sale queda 32 columnas o 4 filas afuera, así que nadie la
; ve mientras se la pisa.
;
; El scroll por hardware hace la vuelta solo: el registro son 10 bits, o sea
; 1024 pixeles, y 1024 es múltiplo de los 512 que mide la ventana a lo ancho.
; Se le escribe la posición de la cámara tal cual y cae donde tiene que caer.
;
; De la ROM no sale un tilemap sino una grilla de bloques: la celda de 16x16 de
; RM2k, que es la unidad con la que el juego fue dibujado y que se repite
; muchísimo. El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa
; de encima y su pasabilidad, todo junto. Guardarlo así es lo que hace que el
; mapa más grande pase de 175 KB —más que la ROM entera— a 40.

; La grilla llega a 40 KB y no entra en un banco, así que se recorre con un
; puntero de 24 bits. En LoROM un banco sólo tiene sus 32 K de arriba: pasarse
; del $FFFF no lleva al $0000 del banco siguiente sino a su $8000, y estas dos
; rutinas son las únicas que saben eso.
.proc ptr_mas
.a16
.i16
    clc
    adc celdas_ptr
    sta celdas_ptr
    bcc listo
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    inc a
    sta celdas_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

.proc ptr_menos
.a16
.i16
    eor #$FFFF                  ; restar es sumar el complemento
    sec
    adc celdas_ptr
    cmp #$8000
    bcs guarda                  ; sigue dentro de la mitad alta del banco
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    dec a
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
guarda:
    sta celdas_ptr
    rts
.endproc

.proc ptr_desde_celdas
.a16
.i16
    lda celdas
    sta celdas_ptr
    sep #$20
.a8
    lda celdas + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_celdas
.a16
.i16
    lda celdas_ptr
    sta celdas
    sep #$20
.a8
    lda celdas_ptr + 2
    sta celdas + 2
    rep #$20
.a16
    rts
.endproc

; Arma la columna X del mapa —en celdas de 8x8— y deja en col_addr dónde va.
;
; Se llenan las 32 filas de la ventana, no las 29 que se ven. La ranura de cada
; fila es fija, fila mod 32, así que escribir de más no puede pisar nada que se
; esté mirando, y ahorra tener que llevar la cuenta de qué parte de la columna
; ya estaba bien.
.proc build_column
.a16
.i16
    stz col_addr
    cpx mapa_cw
    bcc dentro
    rts                         ; más allá del borde: no hay nada que dibujar
dentro:

    ; Dónde cae en la VRAM. La ventana son dos pantallas de 32x32 pegadas, y la
    ; de la derecha vive 1024 palabras más adelante, no al lado.
    txa
    and #(WINDOW_COLS - 1)
    sta temp
    and #$001F
    clc
    adc #VRAM_MAP
    sta col_addr
    lda temp
    and #$0020
    beq izquierda
    lda col_addr
    clc
    adc #1024
    sta col_addr
izquierda:

    ; El bloque mide 16x16: la columna de bloques es la mitad de la de celdas y
    ; el bit que sobra dice cuál de sus dos mitades toca.
    txa
    and #$0001
    asl a                       ; 0 la mitad izquierda, 2 la derecha
    sta tira_ofs
    txa
    lsr a
    asl a                       ; la columna de bloques, en bytes
    sta temp

    jsr ptr_desde_celdas
    lda temp
    jsr ptr_mas

    ; La fila de arriba de la ventana decide la ranura donde arranca y en qué
    ; mitad del bloque cae.
    lda win_row
    and #$0001
    beq desde_arriba
    lda tira_ofs
    ora #$0004                  ; arranca por la mitad de abajo del bloque
    sta tira_ofs
desde_arriba:
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax                         ; la ranura, en bytes

    ; Cuántas filas hay por delante: la ventana entera, o lo que quede de mapa.
    lda mapa_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcc corta
    lda #WINDOW_ROWS
corta:
    sta tira_resta

    ; El índice del bloque va en Y y la ranura en X, y no al revés: la tabla de
    ; bloques ya no vive en el banco 0 —con varios mapas no entra— así que se
    ; lee con un puntero de 24 bits, y ese modo sólo indexa por Y.
fila:
    lda [celdas_ptr]            ; el bloque de esta celda
    asl a
    asl a
    asl a
    asl a                       ; su registro mide 16 bytes
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_col, x             ; la celda del fondo
    lda [bloques8_ptr], y
    sta tira_col2, x            ; y la de la capa de encima

    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)  ; la ventana da la vuelta
    tax

    lda tira_ofs
    eor #$0004                  ; la otra mitad del bloque
    sta tira_ofs
    and #$0004
    bne misma                   ; sigue en el mismo bloque
    lda tira_paso_col
    jsr ptr_mas                 ; a la fila de bloques siguiente
misma:
    dec tira_resta
    bne fila
    rts
.endproc

; La imagen espejada de la anterior: arma la fila X del mapa en tira_row. Lo
; único que cambia es cuál de los dos ejes alterna dentro del bloque y cuánto
; avanza el puntero al pasar de uno al siguiente.
.proc build_row
.a16
.i16
    stz row_addr
    cpx mapa_ch
    bcc dentro
    rts                         ; más allá del borde de abajo
dentro:
    txa
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a                       ; cada fila de la pantalla mide 32 palabras
    clc
    adc #VRAM_MAP
    sta row_addr

    txa
    and #$0001
    asl a
    asl a                       ; 0 la mitad de arriba del bloque, 4 la de abajo
    sta tira_ofs
    txa
    lsr a
    sta temp                    ; la fila de bloques que entra

    ; El ancla apunta a la fila de bloques de arriba de la ventana; la que entra
    ; puede estar hasta catorce filas más abajo, si es la del pie de la pantalla.
    jsr ptr_desde_celdas
    lda temp
    sec
    sbc win_block
    beq en_la_fila
    tax
baja:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne baja
en_la_fila:

    lda win_col
    and #$0001
    beq desde_izquierda
    lda tira_ofs
    ora #$0002
    sta tira_ofs
desde_izquierda:
    lda win_col
    lsr a
    asl a                       ; la columna de bloques de la izquierda, en bytes
    jsr ptr_mas

    lda win_col
    and #(WINDOW_COLS - 1)
    asl a
    tax

    lda mapa_cw
    sec
    sbc win_col
    cmp #WINDOW_COLS
    bcc corta
    lda #WINDOW_COLS
corta:
    sta tira_resta

columna:
    lda [celdas_ptr]
    asl a
    asl a
    asl a
    asl a
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_row, x
    lda [bloques8_ptr], y
    sta tira_row2, x

    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax

    lda tira_ofs
    eor #$0002                  ; la otra mitad del bloque, ahora a lo ancho
    sta tira_ofs
    and #$0002
    bne mismo
    lda #2
    jsr ptr_mas                 ; al bloque de al lado
mismo:
    dec tira_resta
    bne columna
    rts
.endproc

; Qué hay que redibujar este cuadro. La cámara se mueve como mucho dos pixeles
; por vuelta y sólo por un eje, así que cruza a lo sumo el borde de una celda:
; alcanza con mirar si la esquina de la ventana cambió de celda. Si algún día
; la cámara pudiera saltar —un teleport, un cambio de mapa— eso no es un ajuste
; de esta rutina sino un fill_window entero, con la pantalla apagada.
.proc stream_map
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr

    lda camara_y
    lsr a
    lsr a
    lsr a
    cmp win_row
    beq sin_fila
    bcs bajando
    tax                         ; sube: entra la fila de arriba de la pantalla
    bra guarda_fila
bajando:
    pha
    clc
    adc #(VIEW_ROWS - 1)
    tax                         ; baja: entra la del pie
    pla
guarda_fila:
    sta win_row

    ; El ancla de bloques sigue a la fila de arriba de la ventana.
    lsr a
    cmp win_block
    beq mismo_bloque
    pha
    bcs baja_bloque
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_menos
    jsr ptr_a_celdas
    bra guarda_bloque
baja_bloque:
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_mas
    jsr ptr_a_celdas
guarda_bloque:
    pla
    sta win_block
mismo_bloque:
    jsr build_row               ; X sigue siendo la fila que entra

sin_fila:
    lda camara_x
    lsr a
    lsr a
    lsr a
    cmp win_col
    beq sin_columna
    bcs derecha
    tax
    bra guarda_col
derecha:
    pha
    clc
    adc #(VIEW_COLS - 1)
    tax
    pla
guarda_col:
    sta win_col
    jsr build_column
sin_columna:
    sep #$20
.a8
    rts
.endproc

; Llena la ventana entera desde cero: las 64 columnas, una por una. Va con la
; pantalla apagada, al arrancar, y es el único momento en que se escribe tanto
; tilemap de una vez.
.proc fill_window
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    lda mapa_ancho
    asl a
    sta tira_paso_col           ; lo que mide una fila de bloques, en bytes

    lda camara_x
    lsr a
    lsr a
    lsr a
    sta win_col
    lda camara_y
    lsr a
    lsr a
    lsr a
    sta win_row
    lsr a
    sta win_block

    ; celdas = la grilla del mapa + win_block filas. Se suma de a una en vez de
    ; multiplicar: pasa una sola vez y el 65816 no multiplica.
    ldx mapa_ofs
    lda mapa_tabla + M_PTR_MAP_CELDAS, x
    sta celdas_ptr
    sep #$20
.a8
    lda mapa_tabla + M_PTR_MAP_CELDAS + 2, x
    sta celdas_ptr + 2
    rep #$20
.a16
    ldx win_block
    beq sin_filas
suma:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne suma
sin_filas:
    jsr ptr_a_celdas

    lda win_col
    sta temp + 2
    ldy #WINDOW_COLS
columna:
    phy
    ldx temp + 2
    jsr build_column
    sep #$20
.a8
    jsr push_strips
    rep #$20
.a16
    inc temp + 2
    ply
    dey
    bne columna
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

    jsr push_strips
    rts
.endproc

; Sube Y bytes desde la dirección X de la RAM a la VRAM, que ya quedó apuntada.
.proc dma_a_vram
.a8
.i16
    stx A1T0L
    stz A1B0                    ; las tiras viven en el banco 0
    sty DAS0L
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

; Las tiras que dejó armadas stream_map. Van acá y no donde se arman porque la
; VRAM sólo se puede escribir en el vblank; armarlas adentro no entraría.
;
; Una columna sale de un DMA por capa: el PPU puede avanzar de a 32 palabras
; tras cada escritura, que es justo lo que mide una fila del tilemap. Una fila
; sale de dos, porque las dos pantallas de 32x32 no son contiguas.
.proc push_strips
.a8
.i16
    ldx col_addr
    beq sin_columna
    lda #$81                    ; avanzar 32 palabras tras el byte alto
    sta VMAIN
    stx VMADDL
    ldx #.loword(tira_col)
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram

    rep #$20
.a16
    lda col_addr
    clc
    adc #(VRAM_ABOVE_MAP - VRAM_MAP)
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_col2)
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram
    stz col_addr
    stz col_addr + 1
sin_columna:

    ldx row_addr
    beq sin_fila
    lda #$80                    ; avanzar una palabra: la fila es contigua
    sta VMAIN
    stx VMADDL
    ldx #.loword(tira_row)
    ldy #(WINDOW_COLS)          ; las ranuras 0 a 31, la pantalla izquierda
    jsr dma_a_vram

    rep #$20
.a16
    lda row_addr
    clc
    adc #1024                   ; la pantalla de la derecha vive acá
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row + WINDOW_COLS)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram

    ; Y lo mismo para la capa de encima, media ventana más adelante.
    rep #$20
.a16
    lda row_addr
    clc
    adc #(VRAM_ABOVE_MAP - VRAM_MAP)
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row2)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram

    rep #$20
.a16
    lda temp
    clc
    adc #1024
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row2 + WINDOW_COLS)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram
    stz row_addr
    stz row_addr + 1
sin_fila:
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
; Los cuatro trabajan con el acumulador de 16 bits: la celda del héroe ya no
; entra en un byte —hay mapas de 500 celdas de ancho— y los permisos se buscan
; con índices de 16.
.proc try_up
.a8
.i16
    rep #$20
.a16
    lda tile_y
    beq no                      ; ya está en la fila de arriba
    lda #PASS_UP
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_menos               ; el destino: una fila de bloques más arriba
    lda #PASS_DOWN              ; y esa celda tiene que dejar entrar
    jsr can_enter
    beq no
    dec tile_y
    lda #0
    sta step_dx
    lda #-WALK_SPEED
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
    sep #$20
.a8
    rts
.endproc

.proc try_down
.a8
.i16
    rep #$20
.a16
    lda tile_y
    inc a
    cmp mapa_alto
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_mas                 ; una fila de bloques más abajo
    lda #PASS_UP
    jsr can_enter
    beq no
    inc tile_y
    lda #0
    sta step_dx
    lda #WALK_SPEED
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
    sep #$20
.a8
    rts
.endproc

.proc try_left
.a8
.i16
    rep #$20
.a16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_menos               ; la celda de al lado
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    dec tile_x
    lda #-WALK_SPEED
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
    sep #$20
.a8
    rts
.endproc

.proc try_right
.a8
.i16
    rep #$20
.a16
    lda tile_x
    inc a
    cmp mapa_ancho
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_mas
    lda #PASS_LEFT
    jsr can_enter
    beq no
    inc tile_x
    lda #WALK_SPEED
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
    sep #$20
.a8
    rts
.endproc

; --- la pasabilidad --------------------------------------------------------
; Ya no hay una tabla con un byte por celda: los permisos viajan en el bloque.
; Son dos saltos —la celda dice qué bloque es, el bloque dice qué permisos
; tiene— y a cambio el mapa más grande se ahorra veinte kilobytes. Que dos
; celdas dibujadas igual pero con permisos distintos no se confundan lo
; garantiza el conversor, que mete la pasabilidad en la clave del bloque.
;
; Dónde está el héroe dentro de la grilla tampoco es un índice: es un puntero
; que se mueve con él, una celda o una fila por paso. Así nunca hay que
; multiplicar ni recalcular una dirección de 24 bits desde cero, que en LoROM
; es incómodo porque los bancos no son contiguos.

; A = el bit que hace falta. Devuelve con Z apagado si la celda lo tiene.
.proc can_leave
.a16
.i16
    sta temp
    jsr ptr_desde_hero
    jsr pass_del_ptr
    and temp
    rts
.endproc

; Igual, pero sobre la celda a la que celdas_ptr ya quedó apuntando: cada
; dirección lo corre por su cuenta antes de llamar, y si el paso se acepta
; begin_step lo copia a hero_ptr. Así el destino se calcula una sola vez.
.proc can_enter
.a16
.i16
    sta temp
    jsr pass_del_ptr
    and temp
    rts
.endproc

.proc pass_del_ptr
.a16
.i16
    lda [celdas_ptr]            ; qué bloque es esta celda
    tay
    sep #$20
.a8
    lda [pass_ptr], y
    rep #$20
.a16
    and #$00FF
    rts
.endproc

.proc ptr_desde_hero
.a16
.i16
    lda hero_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda hero_ptr + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_hero
.a16
.i16
    lda celdas_ptr
    sta hero_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    sta hero_ptr + 2
    rep #$20
.a16
    rts
.endproc

; Dónde arranca el héroe dentro de la grilla. Se camina hasta ahí sumando: una
; fila de bloques por cada fila que baja y después las columnas de una vez.
.proc init_hero_ptr
.a8
.i16
    rep #$20
.a16
    ldx mapa_ofs
    lda mapa_tabla + M_PTR_MAP_CELDAS, x
    sta celdas_ptr
    sep #$20
.a8
    lda mapa_tabla + M_PTR_MAP_CELDAS + 2, x
    sta celdas_ptr + 2
    rep #$20
.a16
    ldx tile_y
    beq sin_filas
filas:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne filas
sin_filas:
    lda tile_x
    asl a                       ; cada celda ocupa dos bytes
    jsr ptr_mas
    jsr ptr_a_hero
    sep #$20
.a8
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
    jsr ptr_a_hero              ; RM2k cuenta desde la celda de destino, que es
    sep #$20                    ; adonde can_enter dejó apuntado el puntero
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
    bne sigue                   ; el paso todavía no terminó
    jsr cruzar_puerta           ; recién parado en la celda: ¿había puerta?
sigue:
    rts
.endproc

; Si la celda donde el héroe acaba de pararse tiene una puerta, cargar el mapa
; al que lleva. Se mira al terminar el paso y no al empezarlo, que es lo que
; hace RM2k: el evento se dispara cuando el héroe ocupa la celda, no cuando la
; encara.
;
; La tabla se recorre entera comparando. Son pocas —el mapa con más puertas del
; juego tiene un puñado— y esto corre una vez cada dieciséis pixeles.
.proc cruzar_puerta
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda mapa_tabla + M_PUERTA_COUNT, x
    beq no_hay
    sta temp                    ; cuántas quedan por mirar
    lda mapa_tabla + M_PTR_PUERTAS, x
    sta temp + 2
    sep #$20
.a8
    lda mapa_tabla + M_PTR_PUERTAS + 2, x
    sta puerta_ptr + 2
    rep #$20
.a16
    lda temp + 2
    sta puerta_ptr

    ldy #$0000
buscar:
    lda [puerta_ptr], y
    cmp tile_x
    bne siguiente
    iny
    iny
    lda [puerta_ptr], y
    dey
    dey
    cmp tile_y
    beq cruzar
siguiente:
    tya
    clc
    adc #PUERTA_BYTES
    tay
    dec temp
    bne buscar
no_hay:
    sep #$20
.a8
    rts

cruzar:
.a16
    ; Acá se llega con A en 16 bits, desde el `beq` de arriba. El `.a16` no es
    ; decoración: sin él el ensamblador viene creyendo lo que dejó dicho `no_hay`
    ; y le pone un solo byte al `and #$00FF`, que el CPU lee como dos y se come
    ; la instrucción siguiente.
    ;
    ; El destino está en el mismo registro: primero a dónde, después a qué mapa.
    iny
    iny
    iny
    iny
    lda [puerta_ptr], y         ; la celda de destino, en X
    sta entrada_x
    iny
    iny
    lda [puerta_ptr], y         ; y en Y
    sta entrada_y
    iny
    iny
    lda [puerta_ptr], y
    and #$00FF                  ; el índice del mapa al que lleva
    sep #$20
.a8

    ; La pantalla se apaga mientras se carga: cargar_mapa escribe VRAM y CGRAM
    ; por DMA, y con el PPU dibujando eso sale basura. RM2k también funde a
    ; negro al cruzar una puerta, así que el parpadeo no desentona.
    pha
    lda #$80
    sta INIDISP
    pla
    jsr cargar_mapa
    stz step_left               ; el paso que se estaba dando quedó allá
    stz moving
    lda #$0F
    sta INIDISP
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
    cmp npc_total
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
    cmp npc_buf + 4, x
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
    lda npc_buf + 0, x        ; su posición en el mapa
    sec
    sbc camara_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda npc_buf + 2, x
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    sep #$20
.a8
    lda npc_buf + 6, x
    sta obj_tile
    lda npc_buf + 7, x
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

    ; La pose es dirección*3 + frame, y qué tile le toca lo dice la tabla del
    ; actor que está al frente del grupo. Antes se calculaba —el héroe era
    ; siempre el personaje 0 del banco, así que su bloque salía de una cuenta—,
    ; y eso dejó de valer cuando `ChangePartyMembers` puede cambiar el líder en
    ; caliente. La tabla además da lugar a tiles de más de ocho bits, que es lo
    ; que pasa en cuanto hay unos cuantos personajes en el banco.
    lda hero_dir
    asl a
    clc
    adc hero_dir                ; dirección * 3
    clc
    adc temp                    ; más el frame
    asl a                       ; dos bytes por pose
    rep #$20
.a16
    and #$00FF
    tay
    lda [hero_poses], y
    sta temp
    sep #$20
.a8
    ; $FFFF es el centinela de "este actor no tiene gráfico". Le pasa al actor
    ; 10, DummyHero, que es con el que el juego arranca: RM2k tampoco dibuja
    ; nada. Sin grupo el puntero queda en cero y también se sale por acá.
    lda temp
    and temp + 1
    cmp #$FF
    beq sin_dibujar
    lda hero_poses + 2
    beq sin_dibujar

    lda temp
    sta obj_tile
    lda #HERO_PRIORITY          ; por debajo de la capa que lo tapa
    ora hero_pal
    ora temp + 1                ; el bit 8 del tile, que va en el bit 0
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
sin_dibujar:
    rts
.endproc

; --- un objeto en OAM ------------------------------------------------------
; Descarta lo que caiga fuera de la pantalla: la X del objeto tiene nueve bits y
; la Y sólo ocho, así que un objeto lejano daría la vuelta y aparecería del otro
; lado. Se corren los rangos 32 pixeles para poder compararlos sin signo.
; El +32 de las dos comparaciones corre el origen para que un objeto que asoma
; por arriba o por la izquierda —y que llega acá con la coordenada negativa— dé
; un número chico en vez de uno gigante, y una sola comparación sin signo
; resuelva los dos bordes.
.proc emit_object
.a8
.i16
    rep #$20
.a16
    lda obj_x
    clc
    adc #32
    cmp #(256 + 32)
    sep #$20
.a8
    bcs fuera
    rep #$20
.a16
    lda obj_y
    clc
    adc #32
    ; El borde de abajo no se descarta en 256 sino en 224, y no es lo mismo. La
    ; Y de OAM tiene 8 bits y la pantalla 224 líneas, así que los valores 224 a
    ; 255 quedan ambiguos: el PPU los lee siempre como "un poco más arriba del
    ; borde de arriba" y dibuja el objeto envuelto. Con el corte en 256, un NPC
    ; que se iba por abajo se guardaba con una Y de esa banda y reaparecía
    ; arriba, mostrando primero los pies y después entero.
    ;
    ; La ambigüedad hace falta y no se puede sacar: es la que hace que un objeto
    ; en y = -31 muestre su última línea en la línea 0. Lo que no puede pasar es
    ; que le llegue un objeto que de verdad está abajo.
    cmp #(224 + 32)
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

; Las tiras del mapa se arman acá fuera del vblank y se suben desde acá cuando
; empieza el siguiente, igual que OAM. Armarlas dentro del vblank no entraría, y
; escribirlas a la VRAM fuera de él las mostraría a medio hacer.
;
; Una columna son las 32 celdas de la ventana; una fila, las 64. Se indexan por
; la ranura, no por la celda del mapa: así el orden del buffer es exactamente el
; orden en que la VRAM las quiere y cada tira sale de un DMA.
tira_col:   .res WINDOW_ROWS * 2
tira_col2:  .res WINDOW_ROWS * 2
tira_row:   .res WINDOW_COLS * 2
tira_row2:  .res WINDOW_COLS * 2

; La tabla de NPCs del mapa cargado. Es la única de las tablas del mapa que se
; copia a RAM en vez de leerse con un puntero, y por una razón concreta:
; build_oam la recorre con un índice y en cinco desplazamientos distintos, así
; que con `lda tabla, x` sale una instrucción por campo y con un puntero salen
; tres. Copiarla cuesta un DMA por carga de mapa y entra de sobra: el mapa con
; más NPCs de todo el juego tiene 89, y acá entran 127, que es el tope que
; impone OAM.
npc_buf:  .res NPC_MAX * NPC_STRIDE

; Un bit por switch de RM2k. El juego consulta hasta el 1003 en las condiciones
; de página, así que con 1024 alcanza. Se limpian una sola vez al arrancar: en
; RM2k una partida nueva empieza con todos apagados.
switches: .res SWITCH_BYTES

; El tinte de pantalla escala cada canal por el mismo factor para todos los
; colores, así que en vez de hacer la cuenta 256 veces se hace 32: una tabla por
; canal, indexada por el valor de 5 bits que tenía.
tabla_r:  .res 32
tabla_g:  .res 32
tabla_b:  .res 32

; Y la paleta teñida se arma acá antes de subirla. No se puede teñir en CGRAM
; leyéndola y volviéndola a escribir: un segundo tinte se compondría con el
; primero. Siempre se parte de la paleta original, que está en la ROM.
pal_buf:  .res 512

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
    .byte $08                      ; tamaño: 256 KB (el byte es log2 de los KB)
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
