# El port a Super Nintendo

Dibuja el mapa y reproduce su tema. No reemplaza nada del port a Mega Drive: es
una rama aparte que se abrió para ver si la SNES se acerca más al original, y la
respuesta fue que sí.

## Por qué

El sonido de la Mega Drive quedó lejos del MIDI de la PC, y no por falta de
voces sino por el método: el YM2612 es síntesis FM y el MIDI de Windows XP lo
tocaba un sintetizador **por muestras**. La SNES también es por muestras, así
que el problema deja de ser "imitar un piano con cuatro operadores" y pasa a ser
"comprimir estas muestras", que es mecánico.

De paso: 15 bits de color contra 9, y 8 paletas contra 4. Los 108 colores de los
seis CharSets del Auditorium entran sin fusionar ninguno.

## Veredicto

Probado en emulador: **suena mucho mejor que la Mega Drive y cerca del
original**, con muestras que todavía son ondas de un ciclo generadas en Python.
Esa era la pregunta que motivaba la rama, y la contesta a favor de la SNES.

## El mapa

Va en **modo 3, con 8 bits por pixel**. Ahí cada pixel del fondo es un índice
directo a CGRAM y no hay paleta por tile, así que el problema que dominaba el
conversor de la Mega Drive —repartir los colores en grupos tales que ningún tile
necesite dos— simplemente no existe.

    modo 1 (4bpp, 8 paletas):  60 colores -> 28
    modo 3 (8bpp):             60 colores -> 60, sin fusionar

No era evitable de otra forma: Map0007 tiene tiles de 16, 17 y 19 colores, y
ésos no entran en una paleta de 15 por más paletas que haya. Cuesta el doble de
VRAM por tile, 64 bytes en vez de 32; con 92 tiles son 5,8 KB de los 64.

El resultado se verifica pixel por pixel contra el render de Python, a 15 bits,
que es la profundidad real de la consola:

    Map0007: 0 pixeles distintos de 57344

En la Mega Drive esto no se podía hacer: los 9 bits obligaban a fusionar
colores, así que sólo se podía comparar por forma. Acá la comparación es exacta.

Eso destapó un detalle del hardware que a ojo era invisible: **el PPU muestra la
línea `vofs+1` en el primer scanline**, no la `vofs`. Con el scroll en 0 el mapa
quedaba corrido una línea. Las dos imágenes se veían idénticas y diferían en el
50% de los pixeles.

## La cámara

El scroll es por hardware: mover la cámara es escribir dos registros. Lo único
que hay que cuidar es no salirse del mapa.

El tilemap del PPU se arma con "pantallas" de 32×32 celdas encadenadas en VRAM,
y no van una al lado de la otra en memoria: cada una ocupa sus 1024 celdas
seguidas. El conversor entrega el mapa ya acomodado así, con lo que la ROM lo
sube en **un solo DMA** en vez de copiar fila por fila.

Eso alcanza hasta 64×64 celdas, o sea 512×512 pixeles. Map0007 son 40×30. Para
mapas más grandes —Lashe City son 300×300 celdas— va a haber que redibujar filas
y columnas mientras la cámara se mueve, que es el hito siguiente.

**Cómo se verifica.** Cada dirección se mantiene apretada hasta que la cámara
choca contra el borde. Dónde tiene que quedar no se estima: es exactamente el
ancho del mapa menos el de la pantalla, que el conversor emite como `CAM_MAX_X`
y `CAM_MAX_Y`. Si la ROM se moviera de más, de menos, o no frenara, la
comparación falla.

    centro   (0,0)    0 pixeles distintos de 57344
    derecha  (64,0)   0
    abajo    (0,16)   0
    esquina  (64,16)  0

Que llegue justo a 64 y 16 prueba a la vez el movimiento y el tope.

## El personaje

Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño de objeto: el más
chico que las cubre es 32x32, así que se rellena con transparente a los costados
y se pierde una cuarta parte de los tiles. Son 192 tiles, 6 KB.

Y los sprites son **siempre de 4 bits por pixel**: no hay un modo 3 para ellos
como para el fondo. Talan tiene 36 colores y entran 15, así que acá sí hay que
fusionar. Cambia el 9,7% de sus pixeles, con un desvío máximo de 9,9 sobre 31
por canal.

**Cómo se verifica.** Se camina en cada dirección hasta chocar contra el borde
del mapa, y ahí la posición es exactamente el tamaño del mapa menos una celda.
La animación también queda predecible porque la ROM sólo anima cuando la
posición realmente cambia: contra el borde el personaje mira hacia allá pero no
camina en el lugar, que además es lo que hace RM2k.

`snes_expect.py` arma en Python lo que la consola debería mostrar —el mapa, la
cámara siguiendo al héroe, y el héroe en su pose parada con los colores ya
fusionados— y se compara pixel por pixel.

    parado    héroe en (160,112)  cámara (40,8)    0 pixeles distintos
    derecha   héroe en (304,112)  cámara (64,8)    0
    izquierda héroe en   (0,112)  cámara  (0,8)    0
    arriba    héroe en   (160,0)  cámara (40,0)    0
    abajo     héroe en (160,224)  cámara (40,16)   0

Encontró dos cosas que a ojo no se veían:

**Una entrada de CGRAM de menos.** El sprite emite 16 colores —el transparente
más los 15— pero la constante decía 15, así que el último nunca se subía y
quedaba en negro. Eran 14 pixeles de un gris apenas distinto.

**El noveno bit de la X.** La X de un objeto tiene nueve bits y el noveno vive
en la tabla chica de OAM. Sin él, el héroe pegado al borde izquierdo —que en
pantalla queda en -8— se leía como positivo y el sprite saltaba al otro lado de
la pantalla.

## Cómo está armado

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB. El
65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro puertos. Al
encender, el SPC700 corre una ROM interna con un protocolo de carga; se lo usa
para meterle las muestras y un driver, y después ese driver se queda esperando
pares (registro, valor) que le pasa el 65816.

Eso deja el mismo reparto que en la Mega Drive: **toda la lógica en Python, y en
la consola sólo un intérprete de un stream de escrituras.** El driver del SPC700
son **20 bytes**.

    snes/src/main.s      65816: arranque, carga al SPC700, reproductor
    snes/snes.cfg        enlazado LoROM de 32 KB
    snes/record.sh       corre la ROM sin pantalla y graba el audio a WAV
    tools/spc700.py      ensamblador de SPC700, porque no hay uno empaquetado
    tools/brr.py         codificador del formato de muestras de la SNES
    tools/sdsp.py        registros del DSP y el banco de timbres
    tools/snes_music.py  el MIDI del mapa a muestras y stream
    tools/snes_check.py  compara lo que suena contra el MIDI
    tools/wavtone.py     mide la frecuencia de un WAV, para un tono suelto

## El banco de muestras

Que la SNES reproduzca muestras cambia el problema por completo. En el YM2612
cada timbre había que construirlo con cuatro operadores y nueve parámetros cada
uno, a ciegas. Acá el timbre **es** una grabación.

Y las grabaciones salen del **Microsoft GS Wavetable Synth**, que es el
sintetizador con el que este juego se compuso y se escuchó. Microsoft le licenció
a Roland un subconjunto reducido del Sound Canvas en 1996; no es un SC-55, es
exactamente esto. O sea que el port no se aproxima a un banco parecido: muestrea
del que produjo el sonido original.

Eso encaja exacto con el problema: los MIDIs de ABL especifican programas de
General MIDI y el SoundFont tiene una grabación por programa. Mapeo directo, sin
elegir nada a ojo.

Y que sea un banco *reducido* resulta ser una ventaja técnica grande. Sus
muestras son diez veces más cortas que las de un SoundFont completo como FluidR3
y ya vienen a 22 kHz, así que **el banco entero entra en ARAM sin remuestrear
nada** — y remuestrear era, por lejos, lo que más calidad costaba. Con FluidR3
el piano había que bajarlo de 32 kHz a 8230; ahora no se toca.

    PIANO64      5940 B      STRNG71B     6417 B      RDCYM60B     5076 B
    HARP_57A     2142 B      SOLKK60A     1386 B      CHH__60A       756 B
    CABA_60       621 B      MARCS60        648 B

Los ocho a 22 kHz, su tasa original. En total **23 KB de los 64**, con 42 libres.
El banco anterior usaba 52 KB y remuestreaba todo.

Tres detalles que deciden si suena bien o suena mal:

* **El loop tiene que caer justo en un bloque de BRR.** El DSP vuelve al
  principio de un bloque de nueve bytes, o sea cada 16 muestras. No se redondea
  y se espera: se elige primero cuántas muestras va a tener el loop y de ahí sale
  la tasa real.
* **El loop no se acorta.** FluidR3 los elige largos (casi un segundo en el
  piano) porque adentro hay batido entre cuerdas. Cortarlo mete una periodicidad
  audible, así que cuando falta lugar se baja la tasa, no el largo.
* **Los cuatro filtros de predicción del BRR**, que con las ondas de un ciclo
  daban igual y con audio real no:

        instrumento     sólo filtro 0        los cuatro
        piano          12,2% / 0,6%        10,4% / 0,3%
        arpa           12,6% / 2,1%         1,7% / 0,0%
        cuerdas        15,5% / 1,5%         3,6% / 0,4%

  (error de pico y medio, en porcentaje de la amplitud). Al piano lo que le
  queda es el ataque, que por definición no se predice.

## Cómo se suelta una nota

El release del ADSR del DSP **no se puede configurar**: al escribir KOF la
envolvente cae a cero en unos 8 ms. Eso se oye como un corte seco, y era lo que
más llamaba la atención una vez que las muestras fueron reales — sobre todo en
el piano, que debería resonar.

Así que las notas no se sueltan con KOF. Se apaga el bit de ADSR del registro
$x5, con lo que pasa a mandar GAIN, y a GAIN se le pide una caída exponencial
cuya velocidad sí se elige. La envolvente sigue desde donde estaba, así que la
nota se apaga en vez de cortarse. Es la técnica estándar de la consola.

El valor por familia está en `sdsp.py` y se elige de oído, como el resto del
banco: el piano y la campana resuenan (11 y 9, unos 300-400 ms), el órgano y los
vientos cortan casi con la nota (17, unos 130 ms).

El orden en el stream es lo que evita un caso especial: el release se escribe
**antes** que la preparación de la nota siguiente. Si en el mismo cuadro la voz
vuelve a arrancar, su setup pisa el ADSR1 y el GAIN queda sin efecto, que es
exactamente lo que corresponde.

KOF queda usado una sola vez en todo el tema: para callar todo al final.

## La percusión

Era lo que peor sonaba, y por lejos: el generador de ruido del DSP con la
frecuencia cambiada por golpe. Ahora cada golpe tiene su grabación, del kit
estándar de General MIDI —banco 128 del SoundFont, donde cada tecla es un
instrumento distinto en vez de una altura distinta—. El tema de prueba usa
cinco: bombo, charles cerrado, ride, cabasa y maracas.

Dos decisiones acá:

**Se recorta a medio segundo.** El ride de FluidR3 dura 2,6 segundos y el
charles cerrado 0,7, casi todo cola que se apaga. Enteros costarían más que
todos los melódicos juntos; se cortan y el resto lo hace la envolvente del DSP,
que es para lo que sirve.

**El presupuesto se reparte por brillo, no por uso.** El primer intento repartió
por cuántas veces suena cada golpe, y salió al revés de lo que hacía falta: el
bombo suena cien veces y no tiene un solo agudo, se llevó 24 kHz; el ride suena
dieciséis y es todo agudo, quedó en 4 kHz y sonaba a lata. Ahora se le mide el
centroide espectral a cada muestra —la energía de las diferencias entre muestras
consecutivas contra la energía total, que es la misma cuenta sin necesidad de
una FFT— y la tasa sale de ahí:

    bombo       brillo    473 Hz  ->   4000 Hz
    charles     brillo   9218 Hz  ->  17002 Hz
    ride        brillo   8012 Hz  ->  14780 Hz
    cabasa      brillo  11012 Hz  ->  18448 Hz

Con el mismo total de bytes. La percusión se lleva además una segunda voz del
DSP: con una sola, un bombo y un charles que caen en el mismo cuadro se pisan, y
en un patrón de batería eso pasa todo el tiempo. Cuesta un punto de cobertura
melódica (90% a 89%) y se nota mucho menos que perder la mitad de los golpes.

Ocho voces, todas iguales, contra las nueve de la Mega Drive —seis de FM
decentes y tres de onda cuadrada—. Con el reparto de voces por cobertura, que es
el mismo código de `md_music.py`, se reproduce el **90%** del tiempo-nota del
tema de prueba contra el 95% de la Mega Drive.

## Toolchain

**Dos cosas: `python` y `mednafen`.** Las dos están en pacman y en apt. No hace
falta ningún contenedor para compilar ni para verificar.

Llegar ahí costó escribir dos ensambladores propios, y por la misma razón las
dos veces: **nada clonado de internet ni compilado de fuentes sin revisar.**

    tools/spc700.py   el SPC700 no tiene ensamblador empaquetado en ningún lado
    tools/w65.py      el 65816 sí (cc65), pero no en los repos de Arch

El segundo es el interesante, porque había alternativa: clonar cc65 y
compilarlo. Se descartó porque eso mete código sin auditar en la misma caja
donde viven el repo y las credenciales, que es justo lo que se quería evitar.
`w65.py` reemplaza a `ca65` **y** a `ld65` — el layout de la ROM es fijo, así
que emite el binario directo, sin enlazador.

Que se pueda confiar en él no es una promesa. Ver más abajo.

## Cómo se verifica el ensamblador

`just snes-validar` ensambla el mismo fuente con las dos cadenas y compara los
32.768 bytes. Es la única cosa que todavía usa el contenedor, y sólo para eso:
`ca65` es el patrón contra el que se mide.

    main.s:     271 bytes de instrucciones — idénticas
    cobertura:  281 bytes de instrucciones — idénticas

Lo segundo hace falta porque lo primero no alcanza. La ROM del proyecto tiene
271 bytes de instrucciones y 32 KB de datos y relleno: un empate ahí prueba poco,
y sobre todo no toca las sesenta entradas de la tabla de opcodes que `main.s`
nunca usa. Una entrada sin probar es una trampa para el día que alguien la use.
Así que `tools/w65_coverage.py` genera un fuente sintético con **cada mnemónico
en cada modo de direccionamiento que la tabla declara** — 71 mnemónicos, 143
instrucciones — y se compara eso también.

Correrlo cada vez que se toquen las tablas. Mientras dé idéntico, `w65.py` es
correcto para todo lo que el proyecto puede expresar.

## Cómo se verifica la ROM

`mednafen -soundrecord` vuelca lo que sale del DSP a un WAV. Sobre eso hay dos
medidas, ninguna de las cuales necesita escuchar.

Para un tono suelto alcanza con la frecuencia: `wavtone.py` la saca por
autocorrelación, y si se pidió un La de 440 tiene que dar 440.

    tono de prueba: 440.4 Hz medidos contra 440 pedidos, 1 cent de diferencia

Para un tema entero eso no sirve, porque suenan varias notas a la vez. Así que
`snes_check.py` lo hace al revés: del MIDI ya sabemos qué notas deberían estar
sonando en cada momento, así que en vez de preguntarle al audio qué frecuencia
tiene se le pregunta cuánta energía tiene en esa frecuencia. La prueba está en
que además se mide un **señuelo** un cuarto de tono más arriba, que no cae en
ninguna nota: si el mapeo de alturas estuviera mal, el señuelo tendría tanta
energía como la nota buena.

    tema 11h035: 57 de 60 ventanas con la nota por encima de su señuelo (95%)

Cuánto de lo que falta es culpa nuestra lo dice `just snes-referencia`, que
toca el mismo MIDI con FluidSynth en la PC —el mismo SoundFont del que salen
nuestras muestras— y lo mide con la misma vara:

    FluidSynth en la PC:  59 de 60 ventanas (98%)
    nuestra SNES:         57 de 59 ventanas (97%)

O sea que estamos **a una ventana de la referencia**, contra el mismo
sintetizador y con el mismo banco. Sin ese número un 97% no significa nada:
podría ser el máximo alcanzable o podría faltar mucho.

La medida es ciega en los graves, y conviene saberlo: a 87 Hz el señuelo cae a
1,3 Hz de la nota y la ventana de análisis resuelve 11,7 Hz, así que ahí empatan.
Sirve de los medios para arriba.

Y hay un corrimiento que no se puede suponer: la ROM tarda **1,31 s** en
arrancar, porque sube el banco entero al SPC700 por el protocolo de la ROM
interna, que va byte por byte con acuse. Hoy son 0,64 s con el banco de 23 KB;
con el de 48 KB que usábamos antes era 1,40. La primera vez que se midió con muestras reales el puntaje bajó a 80%,
y no era el audio: era la búsqueda de corrimiento, que sólo miraba el primer
segundo y alineaba las ventanas con las notas equivocadas. Ahora se busca dónde
empieza a haber señal y se afina alrededor.

También se controla el pico del WAV. El DSP suma las ocho voces y recién después
aplica el volumen general, sin limitar en el medio: la primera versión saturaba
(pico 32768 clavado) y hubo que bajar el techo por voz. Los números de `sdsp.py`
salen de medir, no de la teoría, porque la teoría supone que todas las voces
pican juntas y en fase y eso no pasa nunca.

## Lo que falta

* **El ataque y el decaimiento** siguen saliendo de las ocho familias de
  `sdsp.py`, elegidas a ojo cuando el banco era sintético. El SoundFont trae los
  suyos por instrumento y todavía no se leen. (El release ya no: ver arriba.)
* **Una muestra por instrumento.** Un piano real está multi-muestreado cada
  pocas notas; nosotros tomamos la del do central y transponemos. En los
  extremos del teclado eso se nota.
