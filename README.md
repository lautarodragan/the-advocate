# A Blurred Line en Super Nintendo

Un port de *A Blurred Line*, un juego hecho en RPG Maker 2000, a la Super
Nintendo. Acá está todo: cómo se lee el juego original, cómo se lo vuelca a un
formato que se pueda mirar, y el port entero con sus trampas y lo que falta.

Lo que **no** está acá: dónde quedamos —eso es `workflow/`— y el relato de cómo
se llegó, que está en `git log`.

## Índice

* [Leer el juego original](#leer-el-juego-original)
    * [Piezas](#piezas)
    * [Lo que hay que saber del formato](#lo-que-hay-que-saber-del-formato)
    * [El RTP](#el-rtp)
* [Los datos en formato versionable](#los-datos-en-formato-versionable)
* [El port a Super Nintendo](#el-port-a-super-nintendo)
    * [Por qué](#por-qué)
    * [Veredicto](#veredicto)
    * [El mapa](#el-mapa)
    * [La cámara](#la-cámara)
    * [Los mapas que no entran](#los-mapas-que-no-entran)
        * [El mapa no se guarda como tilemap](#el-mapa-no-se-guarda-como-tilemap)
        * [El reparto de la VRAM lo decide el conversor](#el-reparto-de-la-vram-lo-decide-el-conversor)
        * [El reparto de CGRAM, también](#el-reparto-de-cgram-también)
    * [El agua se mueve, y cuesta un DMA de 1664 bytes](#el-agua-se-mueve-y-cuesta-un-dma-de-1664-bytes)
    * [El save point: anima quieto y guarda a disco](#el-save-point-anima-quieto-y-guarda-a-disco)
    * [El menú de pausa](#el-menú-de-pausa)
    * [La pantalla de ítems](#la-pantalla-de-ítems)
    * [El equipo, y las pantallas de texto](#el-equipo-y-las-pantallas-de-texto)
    * [La tienda](#la-tienda)
    * [La batalla por turnos](#la-batalla-por-turnos)
        * [La pelea sin manejadores, y el Game Over](#la-pelea-sin-manejadores-y-el-game-over)
        * [El menú: las cinco órdenes del ABL](#el-menú-las-cinco-órdenes-del-abl)
        * [Las habilidades](#las-habilidades)
        * [El fondo y los monstruos: una sola imagen](#el-fondo-y-los-monstruos-una-sola-imagen)
        * [Los encuentros al azar](#los-encuentros-al-azar)
        * [La música y los efectos de la pelea](#la-música-y-los-efectos-de-la-pelea)
    * [La lluvia](#la-lluvia)
    * [Los efectos de sonido](#los-efectos-de-sonido)
    * [El paquete de audio de cada mapa](#el-paquete-de-audio-de-cada-mapa)
    * [El MSU-1](#el-msu-1)
    * [Las animaciones de batalla: el sonido y la luz](#las-animaciones-de-batalla-el-sonido-y-la-luz)
    * [El dibujo de las animaciones de batalla](#el-dibujo-de-las-animaciones-de-batalla)
    * [El cartel de "One year previously"](#el-cartel-de-one-year-previously)
        * [Lo que costaría el sistema de imágenes entero](#lo-que-costaría-el-sistema-de-imágenes-entero)
    * [Varios mapas en la ROM](#varios-mapas-en-la-rom)
        * [Las tres piezas del intérprete de eventos](#las-tres-piezas-del-intérprete-de-eventos)
        * [Un opcode por comando](#un-opcode-por-comando)
        * [Las mecánicas que no son un opcode](#las-mecánicas-que-no-son-un-opcode)
            * [Atravesar paredes vale mientras dura la ruta](#atravesar-paredes-vale-mientras-dura-la-ruta)
        * [Varios temas en el cartucho](#varios-temas-en-el-cartucho)
        * [Cómo se verifica](#cómo-se-verifica)
    * [El personaje](#el-personaje)
        * [Las poses se suben en caliente](#las-poses-se-suben-en-caliente)
        * [Los eventos translúcidos van horneados](#los-eventos-translúcidos-van-horneados)
        * [El color math, implementado y descartado](#el-color-math-implementado-y-descartado)
        * [Los quince colores de un sprite](#los-quince-colores-de-un-sprite)
        * [El giro hacia el héroe](#el-giro-hacia-el-héroe)
    * [La colisión](#la-colisión)
    * [La pila y la BSS comparten los ocho kilos](#la-pila-y-la-bss-comparten-los-ocho-kilos)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
    * [Cómo está armado](#cómo-está-armado)
    * [El banco de muestras](#el-banco-de-muestras)
    * [Cómo se suelta una nota](#cómo-se-suelta-una-nota)
    * [La percusión](#la-percusión)
    * [Toolchain](#toolchain)
    * [Cómo se verifica el ensamblador](#cómo-se-verifica-el-ensamblador)
    * [Cómo se verificaba el audio](#cómo-se-verificaba-el-audio)
    * [El parche de bsnes](#el-parche-de-bsnes)
    * [Trampas del hardware](#trampas-del-hardware)
    * [El inventario, y lo que una condición de ítem hace](#el-inventario-y-lo-que-una-condición-de-ítem-hace)
    * [Las dos preguntas de actor de una rama](#las-dos-preguntas-de-actor-de-una-rama)
    * [Las variables de RM2k](#las-variables-de-rm2k)
    * [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## Los datos en formato versionable

    just datos         # el juego -> data/ y rom/build/ditto-exacto/, con Ditto

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano. Y
**es de donde el port lee el juego**: `tools/rpgmaker/lcf.py` sale de acá, así que el
conversor y las pruebas están mirando estos archivos y no los binarios. Quién lo
escribe es **Ditto** (`tools/ditto/`), que además sabe volver: `ditto pack` rearma los
330 archivos byte por byte —desde el volcado exacto, que la misma corrida deja
en `rom/build/ditto-exacto/` y que no se versiona—. El porqué de la decisión
está en `DITTO.md` y lo que hay adentro, en `data/README.md`.

#### Varios temas en el cartucho

**Lo que los limita no es el cartucho: es la ARAM.** Las muestras viven en los
64 KB del SPC700 y se suben una sola vez al arrancar, con el protocolo del IPL,
que después de saltar al driver ya no está. De streams sobra lugar —tres temas
son 95 KB de los 480 que quedan— pero de bancos de muestras entra uno solo, y
el de `escape_newyork` son 32 KB.

Gana **un solo banco compartido**, y lo que lo decide es el tiempo: subir
32 KB byte a byte con acuse es del orden de medio segundo, o sea que un
`PlayBGM` frenaría el juego treinta cuadros. Volver a subir se puede —la ROM
manda el SPC700 de vuelta al IPL en cada cambio de mapa, ver
`paquete_cargar`—, así que lo que queda por resolver es dónde se paga ese
freno: `workflow/wishlist/presupuesto-de-muestras-por-paquete.md`.

Compartir sale casi gratis porque **el banco es por programa de General MIDI**:
dos temas que tocan piano usan la misma muestra. Lo que crece es la cantidad de
programas distintos, y ahí estaba la trampa: `build_bank` repartía el
presupuesto en partes iguales, así que doce programas recibían la mitad que
cinco y el piano de `escape_newyork` bajaba de 22,1 a 12,6 kHz. **Lo que lo
arregla es repartir lo que sobra**: un instrumento corto, o uno que topa en
`MAX_RATE`, no gasta su parte —con cinco programas sobraban 10 de los 40 KB— y
devolvérsela a los que sí la gastaron los deja a todos donde estaban. Está
medido y es exacto, no aproximado: las escrituras melódicas al DSP del stream
de `evilrhys` con el banco compartido son **las mismas 8627** que con un banco
propio, byte por byte.

Lo que sí cambia es la percusión. Ahí no hay programas que compartir: cada
tecla es un golpe distinto, así que dieciocho golpes se reparten lo que ocho
tenían. Se le da lo que sobre de ARAM en vez de un presupuesto fijo, que
alcanza para que los platos vuelvan a su tasa nativa, pero un bombo de tres
temas juntos igual queda más grueso que solo. Es el precio de compartir.

**Y un tema que no entra en el banco no se cae del cartucho.** Sacar temas de la
lista entera cuando el banco no entra en la ARAM cuesta dos cosas distintas, y la
segunda es la cara: un `PlayBGM` de ese tema no hace nada, y **su pista de MSU-1
queda inalcanzable**, porque una pista no gasta un byte de ARAM y lo único que
necesita es que el tema tenga número. Con los 29 mapas de Lashe City la ROM pide
19 temas y el banco se llena —89 muestras y 66353 B contra los 64512 de ARAM—;
entre los que se caían estaba el del título, que va último porque agregarlo al
final es lo único que no renumera el bytecode.

La lista es completa siempre —un índice y su stream cuestan cartucho, y
de eso sobra— y lo que se recorta es **quién aporta programas al banco**, en
orden de prioridad: primero el del título, después el del mapa donde la ROM
arranca, y detrás la lista tal cual. Un tema que no aporta suena con lo que
otros ya pusieron, porque el banco es por programa de General MIDI. Antes no
sonaba ninguno.

**Lo que cuesta, contado en notas.** Una nota cuyo programa no está en el banco
no suena más bajo: **se cae del stream** —el `continue` de `build_events`— y la
voz desaparece. Los primeros de la lista quedan enteros y los últimos mutilados;
cuáles y cuánto lo dice el informe del conversor, tema por tema.

Jugando no se oye como un deterioro progresivo aunque lo parezca: es un tema
distinto por mapa, y el recorte se lleva a los últimos de la lista, que es más o
menos el orden en que se visitan los mapas. Y **no lo tapa el MSU-1**: los temas
que el recorte alcanza son justamente los que no tienen pista.

**El lever para decidirlo de oído es `--banco-entero`**, que le saca el tope a
`build_varios`. Corriendo el conversor con y sin el flag se ve el canje en sus
dos líneas —cuántas muestras entran, cuántos bytes ocupan, la tasa mediana y
cuántos temas quedan mutilados—: o los primeros perfectos y los últimos con la
mitad de las notas, o todos enteros y todos bastante más chillones. Con
`--banco-entero` el banco deja de entrar en la ARAM de una vez, y eso está
bien: ahí vive **un paquete de mapa por vez**. Cuál de las dos suena peor no lo
contesta un número.

**Por qué el límite sigue estando, ahora que el audio sube por paquetes de
mapa.** En la ARAM no vive el banco entero sino el directorio y **un** paquete,
así que el hardware aguanta de sobra: el conversor imprime el directorio y el
peor paquete, y entran. Lo que no aguanta es el oído: los mismos 40 KB
melódicos repartidos entre casi el doble de programas bajan la tasa mediana a
la mitad, y eso se lo cobran los temas que hoy suenan bien. El límite se queda
hasta que haya un presupuesto **por paquete** en vez de por banco; está en "Lo
que falta".

**En la ROM cambia poco.** Tres tablas de un byte —`tema_lo`, `tema_hi`,
`tema_bk`— en el banco 0, porque se leen con un índice; `music_start` toma el
índice en A y arma el puntero; `tema_actual` recuerda cuál está sonando, que es
lo que `music_frame` necesita para volver a empezar el mismo cuando el stream
termina. Cambiar de tema **no cuesta un cuadro**: no hay nada que subir.

De paso se fue el `.bloque` de los tres bloques de música. Eso es relleno para
que un DMA no cruce de banco, y nada de acá va por DMA: el driver y las
muestras se mandan byte a byte —`spc_block` hace el salto de banco a mano— y el
stream lo recorre `advance`, que hace el mismo salto. Puesto igual, un stream
de más de 32 KB alineaba a banco **y cruzaba lo mismo**: eran hasta 32 KB de
relleno por bloque a cambio de nada.

**Lo que sí cuesta caro es el arranque.** La subida al SPC700 va byte a byte con
acuse, unos 1,4 cuadros por kilobyte, así que un banco de 62 KB tarda el doble
que uno de 32, y `BOOT_CUADROS` está dimensionado sobre el techo por eso: ver
"El arranque dura siempre lo mismo".

**Que las notas de cada tema salgan de los índices de muestra del banco de
todos no lo verifica ninguna prueba**: lo medía `just bgm`, que se fue el
2026-09-19 —ver "Cómo se verificaba el audio"—. Las pruebas son visuales.

**`evilrhys` está al límite, y no por el banco compartido**: las escrituras
melódicas de su stream son las mismas con banco propio y con banco compartido.
Lo que lo tiene al límite es que tiene ocho canales melódicos para seis voces,
así que dos no suenan nunca y los seis que quedan son monofónicos.

### El personaje

Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño de objeto: el más
chico que las cubre es 32x32, así que se rellena con transparente a los costados
y se pierde una cuarta parte de los tiles. Son 192 tiles, 6 KB, las doce poses
de un personaje.

#### Las poses se suben en caliente

**En VRAM vive una pose por personaje**, y las doce de
cada uno que cambia de pose viven en el cartucho. Antes iban todas a VRAM, y
el día que compiló la escena de apertura —Core, Manta, el droide y Kersh
caminando en el mismo mapa— pidió 768 tiles de objeto contra los 512 que
direcciona la PPU, que son los dos bancos de nombres y no un reparto. Es lo
que hacen los RPG de la consola con más de dos personajes animados; con todas
las poses residentes, 512 tiles son dos personajes y medio. Lo eligió taro
frente a la otra salida, que era armar cada personaje con doce objetos de 8x8
para compartir tiles y reventar los 128 lugares de OAM en cualquier mapa con
gente.

#### Los eventos translúcidos van horneados

El "Trans" de una página —`translucent`— en RM2k dibuja el evento con
opacidad 160 de 255. La consola tiene transparencia de verdad, el color math,
pero la aplica a todos los sprites de las paletas 4 a 7 a la vez: un mapa con
translúcidos tendría que dejarles esas cuatro paletas solas, y el 9 —donde están
los fuegos de los barriles— lleva once personajes en las ocho.

Tramarlos —dejar caer parte de sus pixeles, que es lo que hacían los juegos de la
época— tampoco alcanza en este juego. **Los fuegos del mapa 9 están sobre negro
casi puro**: no hay nada que asomarse por los huecos, así que la trama no simula
transparencia, agujerea la llama. Ningún patrón lo arregla, porque el problema no
es la densidad.

Así que la mezcla **se calcula en el conversor y queda horneada en el
gráfico**. Lo que lo permite es una medición: las 70 páginas translúcidas del
juego —35 mapas— son todas estáticas, `move_type` 0 y sin ruta propia. Si ni el
objeto ni el fondo se mueven, la mezcla al 160/255 contra el fondo real da
siempre lo mismo y se puede calcular una vez: sale exacta, sin trama y sin
gastar color math ni paletas reservadas. El fondo es la **capa de abajo** del
mapa en la celda donde el evento está parado —la de encima se dibuja después y
tapa al sprite, así que donde el sprite se ve el fondo es la de abajo—, tomado
en `(x*16 - 4, y*16 - 16)`, que es donde `charset.draw` apoya el cuadro de
24x32. Las doce poses caen en el mismo lugar de la pantalla, así que todas se
mezclan contra el mismo pedazo: el save point del mapa 8, que anima quieto,
sale bien cuadro por cuadro.

#### El color math, implementado y descartado

La consola sabe hacer transparencia de verdad —suma y mitad entre la pantalla
principal y la subpantalla— y **está implementado y verificado**, en el tag
`color-math` (commit `6e0e355`). No se usa: taro lo probó el
2026-09-12 y lo rechazó por dos cosas que no tienen vuelta, ninguna de ellas un
defecto de la implementación.

* **El objeto deja de animar.** El translúcido sale de OAM y pasa a ser tiles
  de BG2, que se suben una vez al entrar al mapa. De los 39 translúcidos que
  dibujan algo, **35 animan, y 33 de ésos son el save point**. Revivirlo pide
  subirle los tiles por DMA con la cadencia del evento, que es la máquina que
  ya existe para los tiles animados del ChipSet.
* **El héroe se ve a través.** No es una elección: el orden del modo 3 no deja
  ninguna ranura de capa de fondo entre el piso y el héroe, así que la única
  disponible queda por encima. Es lo de FF5, y a taro no le gustó.

Cómo estaba hecho, para quien lo retome: `ppu_init` fija `TS` y `CGWSEL` para
siempre y **`CGADSUB` solo** prende y apaga la mezcla, escrito desde
`flush_video` con el valor por mapa que emite el conversor;
`render_map.dibujar_translucidos` mete el objeto adentro de la capa de encima,
así que no hubo que tocar el reparto de VRAM ni el de CGRAM.

Y dejó dos cosas que valen aunque la rama no entre:

* **La ventana de mensaje también es BG2**, así que prender la mezcla la volvía
  semitransparente y el mapa se asomaba por debajo de las letras. Se arregla
  con un canal de HDMA que pone `CGADSUB` en cero en las 80 líneas de la
  ventana. Verificado con el control corrido: sin ese canal, `bum-vuelve` da
  17.586 pixeles de diferencia.
* **snes9x redondea distinto que el hardware en la suma de color math**: con la
  misma ROM, bsnes y mesen-s coinciden entre ellos —truncan, que es lo que hace
  el chip—, y snes9x redondea para arriba cuando la suma de un canal es impar.
  Son trece pixeles y no se ven, pero es **la primera vez que el emulador con el
  que se capturan las goldens se aparta de la consola**: si algún día se compara
  color math, el caso va a `pruebas/rpgmaker/test_cores.py`.

### Las tablas van en el banco 0

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 al arrancar y nunca lo tocamos, así que una
tabla en otro banco se lee del lugar equivocado — sin ningún error, con bytes
que casualmente están ahí.

Y se arregla a medias con facilidad, porque lo que sigue funcionando son las
escrituras directas —apagar el HDMA, los scrolls— y los borrados por DMA, que
llevan el banco explícito: alcanza para que la corrupción de pantalla
desaparezca y el error de fondo quede.

Hay un segmento `TABLAS` que el enlazador pone en el banco 0. Todo lo que
la CPU recorra con un índice tiene que estar ahí.

**Y el banco 0 son 32 K, así que la que crece con el contenido se muda.** Van
tres: la tabla de bloques, la de textos y `mapa_tabla`, el registro de 144
bytes por mapa —con los 28 mapas de Lashe City son 4 KB—. Una tabla mudada se
lee con `lda f:tabla, x`, que lleva el banco en la instrucción y no en el
registro de banco de datos; cuesta un byte por instrucción y **obliga a que el
índice sea X**, porque el direccionamiento absoluto largo indexado con Y no
existe. Los dos usos de `mapa_tabla` con Y pasaron a X, con X yendo y volviendo
por la pila.

Y una tabla mudada necesita su `.bloque` igual que las de acá abajo, o se parte
contra el final del banco. Es exactamente la clase de error que aparece o
desaparece al agregar un byte en cualquier otra parte del cartucho, y que un
solo caso de la tanda cobra mientras los demás no lo ven, porque depende de
dónde caiga la tabla.

Y lo que no entre en un banco no puede recorrerse con un índice, punto: la
grilla de celdas llega a 40 KB. Ésa se lee con un puntero de 24 bits, y ahí
aparece la otra cara de LoROM: **un banco sólo tiene sus 32 K de arriba**, así
que pasarse del `$FFFF` no lleva al `$0000` del banco siguiente sino a su
`$8000`. Dos rutinas de diez líneas, `ptr_mas` y `ptr_menos`, son las únicas que
saben eso; todo lo demás las usa y se olvida del tema.

Y una tabla que se recorra con `[ptr], y` sin cruzar de banco **tiene que
declararse con `.bloque`**, que es lo que le dice al enlazador que la ponga
entera de un lado. Que sus punteros sean simbólicos no alcanza: la tabla de
páginas de evento quedó a caballo de `$02FFFF` el día que los sprites de un mapa
crecieron, y de ahí para adelante la ROM la leyó desde `$03:0000`, que es el
espejo de la WRAM. La tanda lo cobra con un fondo corrido seis pixeles y nada
que diga por qué; lo dice la RAM, con `pg_evento` en `$5555`, que es con lo que
snes9x llena la memoria.

### Cómo está armado

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB. El
65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro puertos. Al
encender, el SPC700 corre una ROM interna con un protocolo de carga; se lo usa
para meterle las muestras y un driver, y después ese driver se queda esperando
pares (registro, valor) que le pasa el 65816.

Eso deja el mismo reparto que en la Mega Drive: **toda la lógica en Python, y en
la consola sólo un intérprete de un stream de escrituras.** El driver del SPC700
son **20 bytes**.

    rom/src/spc700.s             65816: la carga al SPC700
    rom/src/musica.s             65816: el reproductor del stream
    tools/audio/spc700.py        ensamblador de SPC700, porque no hay uno empaquetado
    tools/gunter/                Gunter: códec BRR y lector de SoundFont, en Rust
    tools/audio/muestras_brr.py  el puente entre el conversor y ese binario
    tools/audio/sdsp.py          registros del DSP y el banco de timbres
    tools/audio/snes_music.py    el MIDI del mapa a muestras y stream

El valor por familia está en `sdsp.py` y se elige de oído, como el resto del
banco: el piano y la campana resuenan (11 y 9, unos 300-400 ms), el órgano y los
vientos cortan casi con la nota (17, unos 130 ms).

### La percusión

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

### Toolchain

**Tres cosas: `python`, un core de libretro y `ca65` + `ld65`**, más las
herramientas de Rust del repo —`gunter` para las muestras, `ditto` y
`protocol`—, que **se consumen desde el PATH**: se instalan una vez con `just
herramientas` y ningún script ni prueba de este juego llama a `cargo`. El
porqué de eso está en `AGENTS.md`, y cómo se compila `cc65`, que no viene
empaquetado en Arch, también. Nada de esto pide un contenedor.

La ROM la arma `tools/ensamblado/ensamblar.py`: `ca65`, después `ld65` con el mapa de
memoria que escribe el conversor —un área por banco, ver `tools/ensamblado/bancos.py`—, y
encima el checksum de la cabecera y la tabla de símbolos que leen las pruebas.

### Lo que se perdió con el ensamblador propio

**`ca65` no comprueba el ancho del acumulador en una etiqueta a la que se
llega saltando**, y es el error más difícil de encontrar a mano. El ensamblador lleva el ancho en
orden de lectura, así que en

    bne baja
    rep #$20
    .a16
    lda tira_paso_col
    bra entra
    baja:            <- se llega acá en ocho bits
    cmp #DIR_DOWN    <- pero el ensamblador cree que en dieciséis

el `cmp` se emite con un inmediato de **dos** bytes, la CPU en ocho lee uno
solo, y el segundo —el $00 del byte alto— se ejecuta como `BRK`: la ROM se va
por la ventana y dibuja cualquier cosa. No lo ve el diff, no lo ve la
comparación pixel a pixel, y bisecar con `rts` tampoco sirve, porque desbalancea
la pila y uno termina midiendo eso.

Hoy todas las etiquetas a las que se llega saltando con otro ancho lo declaran
con `.a8`/`.a16`/`.i8`/`.i16`, pero **no lo comprueba nadie**: una etiqueta
nueva que lo necesite y no lo diga es un `BRK` que aparece lejos. Si
una ROM se va por la ventana sin razón aparente, mirar primero ahí.

### Cómo se verificaba el audio

Lo que sí queda de ellas son los números de `sdsp.py`: el DSP suma las ocho
voces y recién después aplica el volumen general, sin limitar en el medio; la
primera versión saturaba (pico 32768 clavado) y el techo por voz salió de medir
el pico del WAV, no de la teoría, porque la teoría supone que todas las voces
pican juntas y en fase y eso no pasa nunca.

### El parche de bsnes

`tools/emulador/bsnes-wram.patch` es un parche para **bsnes-libretro**, no para este
repo, y **desde que las goldens son capturas de snes9x importa más que antes**:
sin bsnes no hay con qué contestar "anda en el emulador y no en la consola", que
es lo único que `pruebas/rpgmaker/test_cores.py` existe para contestar.

Existe porque el reloj de las pruebas le pregunta a la ROM en qué vuelta del
lazo va —lo lleva en `vueltas`, en la WRAM— y bsnes no expone la WRAM:
`retro_get_memory_data` devuelve nulo para **todos** los ids. Sin el parche, los
casos que corren bajo bsnes caen al camino viejo de contar cuadros de hardware,
que sirve mientras la ROM no se atrase.

El comentario que hay arriba de esa función en bsnes dice por qué está así, y es
razonable: la interfaz de memoria de libretro se usa para cargar y guardar la
**SRAM**, y bsnes prefiere hacerlo él. Pero `RETRO_MEMORY_SYSTEM_RAM` es otra
cosa —la RAM de trabajo, la que los frontends leen para cheats, logros y
depuración— y no participa de nada de eso. El parche expone sólo ésa y deja el
resto igual, que es lo que lo hace defendible río arriba.

Para armarlo hace falta `gcc` y `make`, y nada más: el target unix de libretro
tiene `LIBS =` vacío.

    git clone https://github.com/libretro/bsnes-libretro
    cd bsnes-libretro
    git am < .../tools/emulador/bsnes-wram.patch
    make -j$(nproc)
    cp bsnes_libretro.so /usr/lib/libretro/

### Trampas del hardware

Las del 65816 y las del PPU viven en el código, pegadas a la instrucción o al
registro que muerden: se llega a ellas desde ahí, no desde acá. Lo que queda son
las dos que no tienen una línea donde vivir, porque valen para `rom/src/` entero.

**Un `jsr` te devuelve `X` e `Y` como se le da la gana.** No hay convención de
llamada acá: cada rutina usa los índices para lo suyo. Cuando un registro es un
cursor que tiene que sobrevivir a una llamada —el del bytecode del intérprete lo
es— hay que guardarlo con `phy` en el que llama, y el que llama es el único que
sabe que hace falta.

**El ancho de A y de X/Y es estado, y el ensamblador lo cree.** Las directivas
`.a8` y `.a16` no describen: mandan. Toda etiqueta a la que se salte desde otro
ancho tiene que declarar el suyo, y toda transferencia entre registros de ancho
distinto —`tax` con X de 16 bits, `ldx` con un índice de un solo byte— se lleva
el byte de al lado. Nada de esto da error: sale una instrucción de un largo
distinto del que el CPU lee, o un índice con basura en el byte alto.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
