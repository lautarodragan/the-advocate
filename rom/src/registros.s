; --- puertos ---------------------------------------------------------------
INIDISP  = $2100        ; brillo y blanking
NMITIMEN = $4200        ; habilitación de NMI y joypads
RDNMI    = $4210        ; leerlo baja la bandera de NMI
TIMEUP   = $4211        ; leerlo baja la bandera de la IRQ
VTIMEL   = $4209        ; en qué línea cae la IRQ de la música
VTIMEH   = $420A
; La línea de la IRQ de la música: lejos del vblank, que es donde el lazo
; hace sus DMA con el tiempo contado, y en el medio de la parte visible, donde
; lo que haya corriendo puede esperar lo que tarde un cuadro de música.
IRQ_LINEA = 112
HVBJOY   = $4212        ; bit 7: estamos en vblank
MEMSEL   = $420D        ; bit 0: la ROM de los bancos $80 en adelante, rápida
; El código corre desde el espejo del banco $80, no desde el banco 0. Los
; bancos $80 a $BF son los mismos que $00 a $3F —la RAM baja, los registros y
; la ROM en los mismos lugares—, pero con MEMSEL en 1 la ROM de allá se lee a
; 3,58 MHz en vez de 2,68: todo lo que la CPU saca del cartucho, empezando por
; las instrucciones, va un tercio más rápido. Es el FastROM de la cabecera.
; Lo único que hay que hacer es entrar: el reset y las interrupciones llegan
; por vectores de dieciséis bits, o sea al banco 0, y saltan al espejo con un
; `jml`; de ahí en más cada `jsr` y cada `rts` se quedan en el banco en el que
; están. Desde el 2026-09-11, porque la apertura con lluvia, trueno y texto
; perdía un cuadro de cada tres.
RAPIDO   = $800000
STAT78   = $213F        ; bit 4: 0 = consola NTSC, 1 = PAL
HDMAEN   = $420C        ; canales de DMA por scanline
APUIO0   = $2140        ; los cuatro puertos hacia el SPC700
APUIO1   = $2141
APUIO2   = $2142
APUIO3   = $2143

; El comando del driver del SPC700 que lo manda de vuelta a la ROM del IPL.
; Ver `DRIVER` en tools/audio/snes_music.py y el lazo de `reset` que lo usa.
APU_CMD_IPL = 4

; La consola multiplica y divide por hardware, que es lo único que hace falta
; para el tinte de pantalla: escala cada canal por un valor de 0 a 200 con 100
; como neutro, o sea multiplicar y dividir por cien. Las dos son exactas y con
; enteros, así que la misma cuenta en Python —`eventos.tenir`— da siempre lo
; mismo.
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
VMDATAL  = $2118        ; y el dato, de a una palabra con VMAIN en $80
CGADD    = $2121        ; índice de CGRAM
CGDATA   = $2122        ; y el color, de a byte: primero el de abajo
TM       = $212C        ; qué capas se ven en la pantalla principal
MOSAIC   = $2106        ; el mosaico: tamaño en el nibble alto, capas en el bajo
CGWSEL   = $2130        ; dónde vale el color math y contra qué color
CGADSUB  = $2131        ; sumar o restar, y a qué capas
COLDATA  = $2132        ; el color fijo: tres bits de canal y la intensidad
OBSEL    = $2101        ; tamaño de los sprites y dónde viven sus tiles
OAMADDL  = $2102        ; índice dentro de OAM, en palabras
OBJSEL_TM = $212C
JOY1H    = $4219        ; control 1: arriba, abajo, izquierda, derecha y más
JOY1L    = $4218        ; y el otro byte, donde viven A, X, L y R

; Los bits del control que nos interesan, tal como aparecen en JOY1H.
PAD_RIGHT = $01
PAD_LEFT  = $02
PAD_DOWN  = $04
PAD_UP    = $08
; Y start, que hasta la pantalla de título no lo miraba nadie: el juego se
; camina con la cruceta y se habla con A.
PAD_START = $10

; A vive en el otro byte. Los dieciséis bits del control son, de arriba hacia
; abajo, B Y select start arriba abajo izquierda derecha A X L R y cuatro de
; relleno; JOY1H trae los ocho de más peso y JOY1L los ocho de menos, así que
; A es el bit 7 de JOY1L.
PAD_A     = $80
; Y X, el que le sigue: RM2k no lo usa, y acá es el autofire de A. Ver `read_pad`.
PAD_X     = $40

; B vive con los otros en JOY1H, y es el de más peso de los dieciséis. Lo usa
; la elección para cancelar; caminar no lo mira.
PAD_B     = $80

; --- DMA, canal 0 ----------------------------------------------------------
DMAP0    = $4300        ; modo de transferencia
BBAD0    = $4301        ; registro del PPU al que va
A1T0L    = $4302        ; origen: dirección y banco
A1B0     = $4304
DAS0L    = $4305        ; cuántos bytes
MDMAEN   = $420B        ; arrancar

; --- DMA, canal 7 ----------------------------------------------------------
; El segundo canal de DMA común, para cuando una copia intercala dos orígenes
; y no vale la pena rearmar el canal 0 entre uno y otro: ver `esc_llenar`. Los
; canales 1 a 3 son del HDMA, abajo.
DMAP7    = $4370
BBAD7    = $4371
A1T7L    = $4372
A1B7     = $4374
DAS7L    = $4375

; --- HDMA, canales 1 y 2 ---------------------------------------------------
; El DMA de siempre transfiere todo de una, con la pantalla apagada o en el
; vblank. El HDMA es otra cosa: el mismo hardware, pero disparado **una vez por
; scanline**, así que un registro del PPU puede valer una cosa arriba de la
; pantalla y otra abajo. Es lo que usan los juegos para las barras de estado y
; los degradés de cielo, y acá es lo que clava la ventana de mensaje.
;
; Cada canal lee una tabla de la RAM con entradas `[cuántas líneas][valor...]`
; y termina con un cero. El contador es de 7 bits, o sea 127 líneas como mucho.
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
HDMA_VENTANA = $0E      ; los canales 1, 2 y 3 prendidos a la vez
; La ventana 1 del PPU, que no es la de mensaje: es la máscara con la que se
; esconden los objetos debajo de ella. Ver `armar_hdma`.
WOBJSEL  = $2125        ; qué ventanas del PPU enmascaran objetos
WH0      = $2126        ; el borde izquierdo de la ventana 1
WH1      = $2127        ; y el derecho
TMW      = $212E        ; a qué capas de la pantalla principal se les aplica

; El puerto de la WRAM. Sirve para lo que el DMA normal no puede hacer solo:
; copiar de la ROM a la RAM. El DMA va siempre del bus A al bus B, y la WRAM
; tiene su ventana en el bus B, así que apuntando WMADD a dónde se quiere
; escribir y mandando a $2180 se copia ROM -> RAM a la misma velocidad que
; cualquier otro DMA.
WMDATA   = $2180
