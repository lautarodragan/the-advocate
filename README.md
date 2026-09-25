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

    data/ditto.json           la versión del volcado, cuál vista es, y los headers
    data/maps.json            el árbol de mapas y la posición inicial
    data/maps/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/maps/Map0001.tiles   las dos capas de tiles, una fila del mapa por línea
    data/db/*.json            la base de datos, una sección por archivo

Son 30,9 MB en 674 archivos: los 328 mapas con sus eventos y comandos, más la
base de datos entera — 60 actores, 400 skills, 450 ítems, 175 enemigos, 300
tropas, 180 animaciones, 60 eventos comunes, 1200 switches y 250 variables.

**Los tiles van en texto, no en binario.** En binario ocuparían la mitad, pero
serían opacos para git; en texto, cambiar un tile cambia una línea, en la fila
y la columna en que está en el mapa.

**Está todo escrito, con los defaults ya aplicados.** El binario omite lo que
vale su valor por defecto, y `data/` **no**: desde el 2026-09-20 es la *vista
resuelta* que emite Ditto, así que un `max_hp` que el archivo no guardaba
aparece acá en 10 y no hay tabla que consultar. Es la respuesta al bug que
originó todo esto: llegaba con 1 porque el default estaba escrito a mano y
estaba mal.

**Y los enums son números**: `"trigger": 3`, `"code": 10110`, que es lo que el
port espera. El nombre —`"auto_start"`, `"ShowMessage"`, los de liblcf— está en
el *volcado exacto*, el otro árbol que la misma corrida de `just datos` deja en
`rom/build/ditto-exacto/` y que no se versiona: es el que tiene la forma del
binario, el único que `ditto pack` puede volver a escribir, y el que hay que
abrir para leer el juego. Ver `DITTO.md`.

**Encoding.** El texto es cp1252, porque ABL se hizo con el RM2k de Don Miguel.
Quedan un par de mensajes del RTP japonés que el autor nunca tocó y siguen en
Shift-JIS: en el JSON salen como caracteres raros —decodificarlos adivinando le
costaría a Ditto la vuelta exacta— y el que los interpreta es `tools/rpgmaker/lcf.py`,
por los bytes que cp1252 no define.


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

#### Cómo se verifica

La ROM la corre un core de libretro manejado desde Python con `ctypes`
—`tools/emulador/retro.py`—, no un emulador con ventana. `retro_run()` avanza **un cuadro
exacto**, la cruceta se contesta cuadro por cuadro y el framebuffer sale del
callback ya en 256x224. No hay servidor X, ni capturas de pantalla, ni recortes,
ni un solo `sleep`.

Eso no es sólo velocidad —cuánto tarda la tanda entera lo imprime
`just pruebas`—, es lo que hace que la prueba signifique algo: **N cuadros son N
cuadros**. Manejando un emulador por segundos de reloj, cuántos cuadros entran
en esos segundos depende de la carga de la máquina, y una máquina ocupada deja al héroe corto de la pared y
dispara la comparación sin que nada esté roto.

Y los cuadros tampoco se eligen: los dice el **plan** de cada mapa y dirección,
cuántas celdas se caminan y cuántos ticks dura. El paso del héroe son 256
unidades de RM2k por celda a `PASO_POR_VELOCIDAD` por cuadro —ocho cuadros por
celda a la velocidad 4, la de arranque; una ruta con 28 o 29 la cambia y queda
cambiada, como en RM2k—, así que caminar hasta chocar contra la pared es una
cuenta y no una estimación.

**Esos planes están congelados en `pruebas/golden/tanda/plan-*.txt`, y son lo
último que queda de la referencia**: los escribió ella cuando existía, caminando
el mapa celda por celda con las reglas de RM2k. Hoy no los escribe nadie —se
leen— y por eso un caso de caminata dejó de necesitarla. Si alguna vez hay que
rehacer uno, es un acto deliberado como el de rehacer una golden.

**Andan los tres cores instalados —snes9x, bsnes y mesen-s— y los tres dibujan
el mismo cuadro a 15 bits**, que es la precisión a la que se compara. Que tres
emuladores independientes coincidan es lo que vuelve creíble a cualquiera de
ellos, y desde que las goldens son capturas de snes9x es además la única defensa
que queda contra un error que snes9x no ve: de eso vive `pruebas/rpgmaker/test_cores.py`,
que corre el mismo cartucho en snes9x y en bsnes y compara **las dos capturas
entre sí**. bsnes llena la WRAM de basura al encender y snes9x no, así que una
diferencia significa que la ROM depende de memoria que nadie escribió. Los
tres tardaron en andar por errores del frontend y no de ellos —bsnes ignora los
datos de la ROM y abre el archivo él mismo, mesen-s quiere los callbacks después
de `retro_init` y un directorio de sistema—; el detalle de qué pedía cada uno
está en el docstring de `tools/emulador/retro.py`.

**Con el brillo maestro a medias dejan de coincidir**, y es el único lugar donde
pasa: snes9x y bsnes redondean `canal * brillo / 15` y **mesen-s trunca**, o sea
que con brillo 6 un canal de 7 le da 2 donde los otros dan 3. Acá se sigue a
bsnes, que es de donde sale la tabla y el que mide contra hardware, y a
snes9x, que es el core con el que se capturaron las goldens; ninguna prueba usa
mesen-s, y por qué queda afuera está en el docstring de `pruebas/rpgmaker/test_cores.py`.
Lo desempata la SNES de taro.

Casi todo corre en snes9x porque emula un orden de magnitud más rápido que
bsnes; bsnes entra sólo por `test_cores.py`, con un puñado de casos elegidos por
lo que tocan —el intérprete y la CGRAM, la RAM del control mientras se camina, y
la ventana de mensaje, que es lo que más VRAM escribe con la pantalla apagada—.

`test_heroe` camina las cuatro direcciones y se queda parado en un mapa, y la
lista de cuáles vive en `MAPAS_DE_HEROE`, en `pruebas/rpgmaker/test_tanda.py`. Por qué
está cada uno, para los que se eligieron por una razón concreta:

    73, 18, 119   los que cerraron los hitos anteriores: tienen que seguir en cero
    6             recorre 100 celdas por los dos ejes: la ventana da tres vueltas
    8             Lashe City, que además pide el otro reparto de VRAM
    52            1000x80, con 40 KB de grilla que cruzan el corte de banco
    1             el primero del juego: la capa de encima se lleva 4 paletas
    348           el caso opuesto: el fondo usa 95 y encima fusiona 27
    21            Rat Tracks B1, el que destapó la página automática vacía

Más dos paradas quietas en el borde de abajo del mapa 1, que van de a pares
porque se equivocan para lados opuestos, y dos casos de varios mapas: uno que se
carga desde un registro que no es el primero de la tabla —con el índice 0 el
desplazamiento es cero y cualquier cuenta mal hecha da bien por casualidad— y
una puerta cruzada de punta a punta.

El evento del mapa 4 va dos veces, con una tabla de dos mapas y otra de cuatro.
Un teletransporte compilado guarda **el índice en la tabla**, no el número de
mapa, y con la tabla de dos ese índice es 1: el desplazamiento es un solo
`MAPA_STRIDE`, que es la cuenta que más fácil sale bien por casualidad. Con la
tabla `[4,7,19,1]` el mismo salto compila a 3. Bajarlo a mano a 2 —o sea,
mandar la ROM al mapa 19— mueve 55336 de los 57344 pixeles.

Lo que eso **no** prueba es la convención con la que se arma la tabla: el mapa
de `--map-id` primero y después los de `--mapas` sin repetir. Equivocarla
equivoca a la vez el cartucho y la golden que se sacó de él, así que la
comparación sigue dando cero. Ese lado se revisa leyendo, no corriendo.

Y tres más para las prioridades de objeto contra la capa de encima, que es por
donde ya se coló el cuarto error. `evento` deja al héroe tapado, pero
entero: los 768 pixeles de su sprite están debajo de la capa, así que un héroe
que directamente no se dibujara daría la misma pantalla. Las dos paradas en la
celda (66,40) del mapa 1 son la misma escena con un solo bit distinto —ahí la
capa tapa 512 de 768 y la silueta tiene que partirse en el lugar exacto—:
primero con el héroe en prioridad 1, debajo, y después con `encima`, que lo
sube a prioridad 2 y lo pone adelante. Entre las dos pantallas hay 284 pixeles
de diferencia, así que el par no puede dar cero por casualidad.

Y una ruta forzada, `ruta`, que es la única prueba que compara al héroe
**mientras** camina un guión y no donde termina. La diferencia importa: los dos
errores que destapó cuando se escribió eran del contador de cuadros del ciclo de
animación, y ninguno de los dos se ve en el cuadro final, donde el héroe ya está
parado. Compara cuatro cuadros de una ruta de doce
celdas con esperas en el medio, elegidos de modo que cada error conocido dé
rojo; el docstring del caso dice cuáles y por qué. Corre en el mapa 6 porque es
mudo, que cuando se eligió importaba: el arranque duraba distinto con música y
sin ella. Ahora dura siempre lo mismo y eso dejó de pesar.

La prioridad 2 es la que llevan los eventos marcados "above", y no hay forma de
ejercitarla con los eventos del juego. Se relevaron los 328 mapas: **hay
exactamente uno con gráfico en esa capa**, el Package del mapa 261 en la celda
(59,1), y la capa de encima de ese mapa termina en x=938 mientras que su sprite
arranca en x=940. Por dos pixeles no se tocan, y donde no hay capa de encima las
prioridades 1 y 2 dibujan lo mismo. Por eso la prueba pasa por el héroe, que es
el mismo byte de atributos y el mismo `emit_object`: lo que se verifica es el
orden del hardware, no quién lo pide.

El Package igual entra en la tanda, con el héroe en (59,2). Ahí los dos sprites
se pisan y el Package tiene que quedar adelante aunque el héroe esté más abajo
en la pantalla, que es la regla de RM2k de ordenar primero por capa y recién
después por Y. Tratarlo como un NPC común mueve 79 pixeles.

Qué mapa elegir para eso no se adivina mirando el tamaño: uno enorme lleno de
paredes frena en la tercera celda.

Y no todo se llega caminando. Una caminata termina siempre contra un borde del
mapa, que es justo donde la cámara queda pegada; hay estados que sólo se ven en
el medio. Para eso el caso de la prueba empieza con un `Teleport` de RM2k a una
celda elegida, y se compara sin caminar —lo usa `test_parado` en
`pruebas/rpgmaker/test_tanda.py`—, sin depender de cuántos ticks se sostenga la
cruceta. Así se reprodujo el error de la banda de OAM. (Hasta el paso 9e era
el `--inicio TX TY` del conversor, que sigue existiendo para las recetas.)

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

El banco que sube `load_sprite` sigue siendo una imagen armada por el
conversor, pero con **un bloque de 16 tiles por ranura**: el héroe en el
bloque 0, cada NPC que camina en el suyo, y los quietos compartidos por
(CharSet, índice, pose) como siempre, porque no cambian. Un NPC que camina no
comparte ni con otro igual: cambian de pose cada uno por su cuenta. El mapa 1
con ventana pasó de 768 tiles a 120.

Las doce poses de cada personaje que cambia van al cartucho **una vez por
ROM** —los mapas 1 y 2 comparten a Core, a Manta y a Kersh, y con una copia
por mapa la ROM del arranque se pasaba por 19 KB—, en un bloque de 6 KB por
personaje con `.bloque`, así que ningún DMA cruza de banco. `npc_poses` y
`actor_table` llevan punteros de 24 bits a esas poses en vez de tiles, y cada
fila de NPC guarda en +12 la pose que hay en su ranura.

**La cola de VRAM.** `vram_encolar` guarda un origen de 24 bits y un destino
en palabras; `flush_video` la drena después de `push_oam`, hasta cinco poses
por vblank, y lo que sobra espera al siguiente. Una pose son cuatro DMA de 128
bytes, porque un objeto de 32x32 son cuatro filas de la grilla de nombres a
256 palabras una de otra. Quien la encoló —`refrescar_npc` para un evento,
`place_hero` para el héroe— sólo lo hace cuando la pose que quiere no es la
que está, y si la cola estaba llena se entera y la vuelve a pedir. La OAM ya
no cambia de tile nunca: el tile de cada fila es su ranura.

Y va **en el mismo vblank que la OAM que ya cuenta con la pose nueva**, que es
lo que mantiene el ritmo de antes: la OAM que se arma en el cuadro N sube en
el vblank N+1, y las poses que ese armado encoló suben ahí mismo, antes que
ella. Subirlas en el vblank N las mostraría un cuadro antes, y la tanda lo
vería. Es una pieza reusable: por acá pasan las poses hoy, y mañana una imagen
de `ShowPicture` o lo que haga falta.

Lo prueba toda la tanda —cada caso con alguien caminando pasa por acá— y en
su caso real, `apertura`: los cuatro de la escena caminando, el tinte apagado
y el primer mensaje abierto, cero pixeles.

Y los sprites son **siempre de 4 bits por pixel**: no hay un modo 3 para ellos
como para el fondo. Talan tiene 36 colores y entran 15, así que acá sí hay que
fusionar. Cambia el 9,7% de sus pixeles, con un desvío máximo de 9,9 sobre 31
por canal.

**Cómo se verifica.** Se camina en cada dirección hasta chocar contra el borde
del mapa, y ahí la posición es exactamente el tamaño del mapa menos una celda.
La animación también queda predecible porque la ROM sólo anima cuando la
posición realmente cambia: contra el borde el personaje mira hacia allá pero no
camina en el lugar, que además es lo que hace RM2k.

Son los cinco casos de `test_heroe`: la parada y las cuatro direcciones, hoy
contra la captura congelada de cada uno.

**Hasta el 2026-09-16 se comparaban contra una referencia en Python**,
`tools/snes_expect.py`, que armaba lo que la consola debería mostrar —el mapa,
la cámara siguiendo al héroe, y el héroe en su pose parada con los colores ya
fusionados— siguiendo las mismas reglas que la ROM. Se fue cuando quedó claro
que en el pixel la captura del emulador es mejor referencia, y que los errores
que la referencia no cazaba —los de nacimiento— los encontraba taro jugando.
Vale saber qué encontró mientras existió, porque es de ahí que salen dos de las
constantes de este lado, y ninguna de las dos se veía a ojo:

**Una entrada de CGRAM de menos.** El sprite emite 16 colores —el transparente
más los 15— pero la constante decía 15, así que el último nunca se subía y
quedaba en negro. Eran 14 pixeles de un gris apenas distinto.

**El noveno bit de la X.** La X de un objeto tiene nueve bits y el noveno vive
en la tabla chica de OAM. Sin él, el héroe pegado al borde izquierdo —que en
pantalla queda en -8— se leía como positivo y el sprite saltaba al otro lado de
la pantalla.

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

Para el port un CharSet horneado es **otro CharSet**, con
`~horneado:<mapa>:<x>:<y>` pegado al nombre: lo pega el lector en las páginas
translúcidas —`lcf` lo hace sólo si alguien prende `DECORAR_TRANSLUCIDO`, que
es el conversor, para que el volcado a JSON siga viendo el nombre de verdad— y
`render_map.Charsets` fabrica la imagen. Todo lo demás —paletas, ranuras de
VRAM, poses— lo trata como a cualquier gráfico. Quien mire
**qué** dibuja un nombre y no dónde está parado tiene que pasar por
`rm2k.sin_horneado`: la pasabilidad de un evento dibujado con un tile lo hace.
El camino viejo sigue estando, con `MODO_TRANSLUCIDO=trama`, para poder
comparar los dos sobre el mismo árbol.

Lo que se paga, y está declarado en
`workflow/divergencias/los-translucidos-quedan-opacos.md`:

* **El sprite queda opaco.** Nadie que pase por detrás se ve. Para un fuego
  sobre un barril y para un save point da igual —nada camina por ahí—, pero el
  Kersh translúcido del mapa 305 se superpone con un Guard, y ahí sí taparía.
* **Dos eventos con el mismo CharSet sobre fondos distintos son dos
  gráficos**, y por lo tanto dos paletas. Medido sobre los 35 mapas con
  translúcidos: sólo se mueven tres y **ninguno se cae**. El 9 pasa de siete
  paletas a ocho —los dos fuegos de los barriles están sobre fondos distintos—,
  el 117 de seis a siete, y el 37 suma un gráfico dibujado con una paleta ajena
  (de cinco a seis). Los otros 32 quedan igual; el 8, que ya usaba las ocho,
  también, porque su `savept` es uno solo.
* **Si detrás hay un tile animado, el horneado vale para un dibujo solo.**
  Pasa en dos de las 39: los save points de los mapas 59 y 178 están sobre
  agua, y adentro de su cuadro de 24x32 el agua va a quedar quieta.
* **El fondo son los tiles, no los otros eventos.** Cuatro de las 39 se
  superponen con el sprite de otro evento —los mapas 74, 152 y 305—: ahí la
  mezcla es contra el piso y no contra el vecino.

De las 70 páginas translúcidas, las que se hornean son **39**: las otras 31 se
dibujan con un tile del chipset y todas llevan el tile 0, que en RM2k es "sin
gráfico", así que no se dibujan ni en el original. El `EV0068` del mapa 8 es
una de ésas. Lo cobra `fuego` en la tanda.

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

**Menos el save point**, que va **opaco**: está en
`rm2k.SIN_TRAMA` y `lcf` no le pega el sufijo. Es una divergencia deliberada de
RM2k, declarada acá y no descubierta mirando una pantalla. Se
probaron los otros dos caminos y los dos se cayeron: con la trama, en una
pantalla moderna se ve el damero y la llama queda agujereada; con el color math
—que es transparencia de verdad— el objeto deja de animar y el héroe se ve **a
través** del save point. Lo que hace que el tercero valga es que ahora tiene
sus colores: contando sólo las poses que muestra son 13 y le sobra lugar en una
paleta propia, contra los 41 del bloque entero y la paleta prestada de antes.

#### Los quince colores de un sprite

Un sprite va siempre a 4 bits, o sea 15 colores y el 0 transparente, y los
CharSets de este juego tienen entre 20 y 48. Así que se fusiona, y **lo que
importa no es cuántos entran sino cuáles 15**: mal elegidos, las caras del menú y
los personajes del mapa salen grises. Son tres reglas distintas.

**El criterio de fusión.** `merge_least_used`, en el `pixeles.py` de entonces, mataba al color con
menos píxeles y lo mandaba a su vecino más cercano. Eso es exactamente al
revés de lo que uno quiere: un color puede cubrir pocos píxeles y aun así
definir el dibujo —un brillo, un ojo, el borde de un casco— y mandarlo a diez
de distancia se ve, mientras que dos grises casi iguales que cubren media
lámina sobrevivían los dos porque ninguno era el menos usado. Ahora es
`merge_least_visible` y el costo de mandar `a` a `b` es
`píxeles(a) * luma_distance(a, b)`, o sea el error que el cambio agrega: se
fusiona el par más barato. No inventa colores —el que queda es uno de los que
ya estaban, así que no hay que recuantizar a 15 bits y no depende de la versión
de PIL— y es determinista, porque `luma_distance` pasó a ser entera. Medido
como error por píxel opaco: Talan -61%, Core -63%, Kersh -23%, Manta -33%.

Las caras del FaceSet usaban `titulo.reducir`, que se queda con los 15 más
usados y manda el resto al más cercano. En 48x48 píxeles eso arrasa: los 15
ganadores eran 15 variantes del mismo tono de piel. Ahora usan el mismo
`merge_least_visible`, y el error por píxel baja 92% en la cara de Talan y 88%
en la de Core. La pantalla de título sigue con `reducir`: son 240 colores de
369 y ahí la diferencia no existe.

**Y queda escrito qué se fusionó con qué.** Fusionar dos colores no es una
optimización: se pierde algo y alguien eligió qué, así que es una *decisión
artística* y no puede tomarse sin dejar rastro —si mañana un cambio le hace
perder dos colores más a un mapa, hay que verlo en un diff y no mirando la
ROM—. Las de las dos capas de cada mapa salen a `parches/auto/mapas/<id>.toml`, y
**a qué tamaño se dibuja cada animación de batalla** a
`parches/auto/animaciones/<n>.toml`; la tanda falla si lo commiteado no coincide,
como `just protocolo --check` con los opcodes. Lo versionado es lo que decide
**`abl`**, el ROM jugable; los cartuchos de prueba deciden solos para lo que el
juego no lleva. Se escribe el estado deseado —qué color se va a cuál y en qué
orden, a qué rectángulo va la animación— y no un informe, porque el paso
siguiente es que el conversor **lea** esos archivos en vez de volver a
decidir. La clave nombra
siempre una situación del juego —el mapa, el número de animación de RM2k— y
nunca el cartucho. Ver `tools/port/parches.py`.

**Contar sólo las poses que se ven.** `sprite_colors` recorría siempre el
bloque de doce poses, aunque el evento muestre una. La deduplicación ya existía
en tiles y en VRAM y nunca había bajado al conteo de
colores. Ahora `poses_del_mapa` dice qué puede mostrar cada gráfico —las doce
para el que camina, el que gira hacia el héroe y el que cambia de gráfico con
la 34; los **tres cuadros de su fila** para el que anima quieto, que cambia de
columna y no de fila; la que declara su página para el resto— y `sprite_colors`
cuenta sólo eso. El `mapping` que sale cubre igual todos los colores del
bloque, mandando los de afuera al más cercano de los que quedaron, para que
pedir una pose de más no sea un KeyError.

Donde se gana es en los CharSets **editados**: los que conservan el gráfico
original de RPG Maker en casi todo el bloque y tienen un dibujo nuevo, con
colores ajenos, en un rincón. `savept` es eso, y por eso pasa de 41 colores a
13. En un CharSet normal las doce poses son el mismo dibujo movido y comparten
paleta, así que contar doce o contar tres da casi lo mismo.

**El peso.** Un mapa con más gráficos que paletas no deja a nadie sin dibujar:
al que llega último se le presta una ajena. Quién llegaba último era el orden
de los eventos del mapa, o sea el azar, y en Lashe City el save point es el
evento 66 de 68. Ahora un CharSet puede pesar —`PESO_DE_GRAFICO`— y el que pesa
se sirve primero. Es una tabla escrita a mano y corta a propósito: no hay medida
automática de "cuánto se ve" que no sea inventada, y la llena lo que taro
reporta jugando.

Medido sobre los 328 mapas del juego, contra el criterio viejo: los colores
fusionados bajan de 45564 a 43237 (-5,1%), los gráficos que fusionan algo de
2102 a 2036, **ningún gráfico fusiona más que antes**, ningún mapa se cae, no
se descarta ni un evento de tile más, y las paletas de sprite usadas bajan de
1274 a 1272. Los préstamos pasan de 101 a 102 y se mueven en tres mapas: el 8
le da la suya al save point y se la saca a `People1:0`.

**Y el cronómetro va antes que los eventos de tile.** Sus dos colores se meten
ahora en la primera paleta con lugar **antes** de repartir los gráficos
dibujados con un tile del chipset, que entran "mientras quepan". El orden era el
revés por accidente: en el mapa 8 el tile 118, que son dos colores, se metía en
la paleta del save point y la dejaba en catorce, y después había que bajarle un
color a un personaje entero para hacerle lugar al cronómetro. Sirviéndolo antes
no se fusiona nada.

#### El giro hacia el héroe

El NPC que el héroe dispara —con A o por contacto— se da
vuelta hacia él mientras dura su página, como en RM2k. Las reglas están en
GIRO, en `tools/port/eventos.py`, y la ROM las sigue en `giro_disparar`.

Lo difícil era la VRAM: los quietos comparten ranura por (CharSet, índice,
pose), así que subirle otra pose a uno giraría a todos sus gemelos. El
conversor le reserva a cada mapa que lo necesite **una ranura de giro**, un
bloque de 16 tiles más, y le pone al cartucho las doce poses de cada gráfico
que puede girar. El quieto que gira se muda ahí y se le sube la pose que mira
al héroe; al terminar vuelve a su ranura compartida. Uno que camina o anima
quieto gira en la suya. El estado vive en la RAM lejana y la página lleva dos
bytes más —ahora son 32— con la entrada de sus poses y su pose, que es lo que
un refresco compara para saber si el giro sobrevive a un cambio de página.

La fila del NPC **se busca por evento cada vez** y no se guarda: las filas se
reordenan cuando alguien camina, así que una guardada le devuelve el tile al
evento que haya quedado en ella. Lo cobran `bum-vuelve` y `gemelo`, que mira el
quieto con un gemelo al lado.

### La colisión

Toda la lógica de RM2k vive en `tools/rpgmaker/rm2k.py`, fuera del conversor y de esta
consola: que
cruzar de una celda a la de al lado pide permiso a las dos —la de origen tiene
que dejar salir por ese lado y la de destino dejar entrar por el opuesto—, que
la capa alta manda sobre la baja salvo que sea decorado, y que las caras de
pared se cruzan siempre. La consola sólo lee los cuatro bits ya resueltos, que
desde el hito del redibujado viajan adentro del bloque de 16×16 en vez de en una
tabla aparte.

El movimiento también cambia: **RM2k no mueve al personaje libremente.** Se
compromete a una celda vecina y recorre sus 16 pixeles sin poder frenar. Por eso
el estado es la celda más cuántos pixeles faltan del paso en curso, y mientras
falten no se acepta otra dirección.

Caminando en cada dirección hasta que la tabla lo frene, el héroe para en la
celda 14 de 19 yendo a la derecha, en la 3 a la izquierda, en la 5 para arriba
y en la 10 para abajo.

Que frene en celdas interiores y no en los bordes del mapa es lo que dice que la
tabla se está mirando de verdad.

### La pila y la BSS comparten los ocho kilos

El banco 0 de RAM son ocho kilos: la página directa, la BSS y **la pila**, que
arranca en `$1FFF` y crece hacia abajo, contra la BSS. No hay más: la pila del
65816 vive en el banco 0 y ese banco es el espejo de `$7E0000`-`$7E1FFF`, así
que los `$7E2000` para arriba no le sirven.

Comprobar que la BSS entre en los 7936 bytes del área no alcanza: si los ocupa
exactos, el primer `jsr` escribe arriba de `pal_buf`, que es lo último que hay.
Eso no se ve al armar ni al arrancar sino cuatrocientos cuadros adentro de una
escena y con la RAM entera pisada, así que hay dos reglas y van juntas:

* **El mapa de memoria reserva la pila, y una prueba mide cuánta se usa.**
  `PILA`, en `tools/ensamblado/bancos.py`, son bytes que la BSS no puede tocar:
  el área `RAM` del `.cfg` termina antes, y pasarse es un error de `ld65` al
  armar. Es el mismo agujero que ya había tenido el ZEROPAGE, y la misma cura:
  un área que no se controla se desborda en silencio.

  Pero reservar sola no alcanza, porque **lo que se desborda es la pila y no la
  BSS**, y eso `ld65` no lo puede ver: pasarse no falla al armar, pisa la BSS
  corriendo, y ahí no lo cobra ninguna de las dos redes —las goldens no lo
  distinguen y `test_cores.py` tampoco, porque snes9x y bsnes se corromperían
  igual—. Por eso el margen se mide: `pruebas/herramientas/test_pila.py` llena
  la zona de la pila con centinelas **antes del primer cuadro** y lee el byte
  más bajo que dejó de ser el suyo, o sea hasta dónde bajó de verdad, en los
  caminos más hondos que conocemos. Avisa a la mitad de `PILA` y no al borde,
  para que quede lugar para decidir.

  La marca la pone el arnés y no la ROM a propósito, y no pierde nada: corre
  después de `retro_load_game` y antes del primer `retro_run`, o sea con el
  cartucho cargado y sin una instrucción ejecutada, así que el `reset` queda
  adentro. Hacerlo desde la ROM costaría banco 0 —lo que se está tratando de
  liberar— y, peor, inicializaría esa memoria para todas las pruebas, que es
  exactamente lo que `test_cores.py` necesita que no pase.
* **Se aflojaron dos topes, con la medida al lado.** `NPC_MAX` pasó de 127 a
  104 y `EV_MAX` de 128 a 120. El techo de `NPC_MAX` lo pone OAM —128 objetos,
  uno es el héroe— pero el mapa con más filas de todo el juego tiene **99**, y
  el que más eventos tiene, **114**; los dos medidos sobre los 328. Son 416
  bytes, y ninguno puede quedar corto en silencio porque el conversor corta si
  un mapa se pasa.

Cuánto queda hoy entre el final de la BSS y la pila no se escribe acá: se mide,
con el `.res` que explica AGENTS.md, y hay que decir con qué cartucho. La BSS
estuvo llena hasta el 2026-09-20, y lo que le dio aire fue bajar `PILA`: es el
único lugar de donde salía RAM sin reescribir nada. Lo que siga pidiendo tiene
que aflojar algo, y `ld65` lo va a decir al armar en vez de dejarlo pasar.

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

    rom/src/main.s               65816: arranque, carga al SPC700, reproductor
    tools/audio/spc700.py        ensamblador de SPC700, porque no hay uno empaquetado
    tools/gunter/                Gunter: códec BRR y lector de SoundFont, en Rust
    tools/audio/muestras_brr.py  el puente entre el conversor y ese binario
    tools/audio/sdsp.py          registros del DSP y el banco de timbres
    tools/audio/snes_music.py    el MIDI del mapa a muestras y stream

### El banco de muestras

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
el piano había que bajarlo de 32 kHz a 8230; ahora no se toca. Cuántas muestras
entran y cuántos bytes ocupan lo imprime el conversor.

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

### Cómo se suelta una nota

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

Hasta el 2026-09-16 hubo un ensamblador propio, `w65/`, escrito por una regla
—no compilar fuentes de internet en esta caja— que taro dio por caduca. Se
borró cuando las dos ROMs de referencia salieron byte por byte iguales con las
dos cadenas. El del SPC700, `tools/audio/spc700.py`, sigue: ése no tiene ensamblador
empaquetado en ningún lado.

### Lo que se perdió con el ensamblador propio

Los controles que `w65` fue ganando a medida que un error costaba una tarde
—etiqueta repetida, constante redefinida con otro valor, el área de RAM que no
entra, el operando que no entra en su ancho— los hace también `ca65` + `ld65`.
**Uno no, y es el más difícil de encontrar a mano: el ancho del acumulador en
una etiqueta a la que se llega saltando.** El ensamblador lleva el ancho en
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

`w65` comparaba el ancho declarado en cada salto relativo con el de su etiqueta
y fallaba con nombre y línea. La primera vez encontró 24 casos en `main.s`, y
hoy todas las etiquetas a las que se llega saltando con otro ancho lo declaran
con `.a8`/`.a16`/`.i8`/`.i16`. **Lo que ya no hay es quien lo compruebe**: una
etiqueta nueva que lo necesite y no lo diga es un `BRK` que aparece lejos. Si
una ROM se va por la ventana sin razón aparente, mirar primero ahí.

### Cómo se verificaba el audio

**Hoy no lo verifica nada automático**, y conviene tenerlo a la vista: el audio
de la ROM lo cobra el oído de taro y nada más.

Hasta el 2026-09-19 había dos medidas sobre un WAV grabado con `mednafen
-soundrecord` —la frecuencia de un tono suelto por autocorrelación, y para un
tema entero la energía de cada nota del MIDI contra un **señuelo** un cuarto de
tono más arriba, con FluidSynth tocando el mismo MIDI como techo— y las
recetas que las corrían (`audio-check`, `bgm`, `referencia`). Se fueron con
todo lo que no era ni pipeline ni pruebas: no estaban en `just pruebas` y nadie
las corría. Están en el `git log` para quien las quiera volver a traer.

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

Probado leyendo `vueltas` con el core parcheado: bsnes declara 131072 bytes y
da los mismos números que snes9x, cuadro por cuadro. Cuántas comparaciones pasan
lo dice `just pruebas`.

### Trampas del hardware

Las del 65816 y las del PPU viven en el código, pegadas a la instrucción o al
registro que muerden: se llega a ellas desde ahí, no desde acá. Lo que queda son
las dos que no tienen una línea donde vivir, porque valen para `main.s` entero.

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

### El inventario, y lo que una condición de ítem hace

RM2k elige la página de número más alto cuyas condiciones se cumplen. Las de
switch y de actor en el grupo la ROM las evalúa desde siempre; las de **ítem**
aparecieron con el inventario. Un byte por ítem del LDB —450, `ITEMS_N` los
cuenta con el 0 que no se usa— en la RAM lejana, `FAR_ITEMS`, indexado por el
número de RM2k; `ChangeItems` compila a `OP_ITEM` con el ítem y cuánto se suma,
con signo, y la cuenta queda en [0, 99] como `Game_Party::AddItem`. El juego lo
usa 509 veces, siempre con ítem y cantidad constantes. Cambiar un ítem pide el
refresco de páginas, como `CommandChangeItems`. La página lleva el ítem que
pide en +28 y `condiciones_ok` mira que la cuenta no sea cero —`GetItemCount`,
sin equipo todavía—. El inventario viaja en la partida, que por eso mide 773
bytes y las ranuras de SRAM van cada 1024.

Durante un día, antes de eso, la página con ítem se emitía con `switch_a =
SWITCH_IMPOSIBLE` —un switch que nadie prende— porque `ChangeItems` se
aceptaba sin hacer nada y el grupo no tenía ítems jamás; la máquina quedó en
`rm2k.CONDICIONES_IMPOSIBLES`, vacía. Y antes de eso el evento entero quedaba
afuera: no se dibujaba, no frenaba y no disparaba. Son 45 eventos; EV0041 del
mapa 8 es uno.

**Y la rama por objeto.** Es la misma pregunta que la
condición de página —`GetItemCount(id) > 0`, sin `GetEquippedItemCount` porque
no hay equipo— pero adentro de un `ConditionalBranch`, la clase 4. Compila al
mismo `OP_IF` que el switch, con el número de RM2k adelante y la polaridad tal
cual —0 es "tiene que tenerlo"—, así que la ROM la decide con el mismo `eor` y
sin una rama de más; lee el byte de `FAR_ITEMS` por el mismo camino que
`condiciones_ok`. Son **+20 páginas del juego entero**, y estuvo sin hacerse
más tiempo del que hacía falta: figuraba como "pide inventario, que no hay" en
un comentario que quedó viejo el día que el inventario apareció.

### Las dos preguntas de actor de una rama

`ConditionalBranch` clase 5 es "el héroe", y adentro lleva siete preguntas
distintas —el `switch (com.parameters[2])` del caso 5 de
`Game_Interpreter::CommandConditionalBranch`—. La ROM contesta tres: **está en
el grupo** (la 0, que ya estaba), **sabe esta habilidad** (la 4) y **tiene
puesto este objeto** (la 5). Son **+28 páginas del juego entero**, de 5170 a
5198 de las 5603 disparables, y van juntas porque van juntas en el juego: las
10 páginas que preguntan por una habilidad preguntan además por el equipo, así
que la 4 sola destraba cero y la 5 sola +18.

Las dos nuevas no entran en `OP_IF`, que tiene un solo operando: llevan el
actor **y** el ítem o la habilidad. Por eso hay un opcode aparte, `OP_IF_ACTOR`
—sub, actor en un byte, dato en una palabra, destino— con el destino último,
como todos, porque es lo que el conversor parchea al cerrar la rama. Ninguna de
las dos tiene polaridad: RM2k no se la da, la rama de abajo es el `else`.

El **equipo** es estado de verdad: `FAR_EQUIPO`, cinco palabras por actor, que
arranca del `initial_equipment` del LDB, que la pantalla de equipo escribe y
que viaja en la partida. La ROM lee las cinco ranuras por el puerto de la WRAM
y se da por cumplida con que el ítem esté en cualquiera, que es el `||` de los
cinco `Get*Id()` de easyrpg.

La **habilidad** no lo es, y conviene saberlo antes de apoyarse en ella: sale de
una tabla del cartucho —`sabe_hab`, 81 entradas para los 60 actores del LDB— que
arma `batalla.aprendidas_de`, que es la misma función con la que el modelo de la
pelea contesta. Es `Game_Actor::LearnLevelSkills` a secas: las de nivel menor o
igual al `initial_level`. **Va aparte de `actor_hab`**, que es la lista del menú
de la pelea: ésa lleva sólo las que este port sabe ejecutar y sólo de los
actores que pueden entrar al grupo, y `IsSkillLearned` no filtra ninguna de las
dos cosas. Lo que falta para que sea estado es `ChangeSkills` —20 comandos en el
juego, y uno de ellos le enseña la 152 a Arden, que es justo la que preguntan
los mapas 47 y 48—; mientras no compile, la respuesta es la del LDB y nada la
mueve. Las páginas que enseñan no compilan, así que no hay media implementación
corriendo: hay una deuda con su número.

Lo cubren cuatro casos de la tanda —`rama-equipo`, `rama-equipo-no`,
`rama-hab` y `rama-hab-no`—, que son la página de prueba tiñendo la pantalla
sólo si la rama se cumple. Existen porque **ninguna página del juego que
compile las usa**: las 36 del equipo y las 10 de la habilidad viven en los
mapas 20, 38, 47, 48, 151, 278, 279, 343 y 344, y ninguna demo los lleva.

Las otras cuatro preguntas de actor —el nombre, el nivel, los HP y el estado—
no las usa ninguna página del juego. Y de las otras clases de condición que
faltan, las dos que aparecen están medidas y **no valen nada**: la 6, la
orientación de un personaje, son 124 comandos en 31 páginas y destraba **cero**
—esas páginas están frenadas por otra cosa igual— y la 2, el cronómetro, es un
comando en una página y también cero.

**La condición por variable se evalúa**: la
página lleva la ranura, la comparación y el valor (+24 a +27, `PAGINA_BYTES`
28), `condiciones_ok` los lee de la tabla y los compara con `comparar_var`,
la misma comparación con signo de `ConditionalBranch` —RM2k usa
`CheckOperator` para las dos—. Y escribir una variable pide un refresco de
páginas, como `SetNeedRefreshForVarChange`: sin eso el cofre del mapa 133,
cuya primera página pide la variable 123 >= 8, no aparecía de ningún lado. La
condición por cronómetro sigue tirando el evento: la pide una sola página del
juego.

### Las variables de RM2k

El juego declara cinco mil y usa 81. La ROM lleva **esas 81**, con una ranura
cada una: el conversor las cuenta en los 328 mapas antes de compilar nada
—`indexar_variables`, un tercio de segundo— y el bytecode habla de ranuras, así
que cuestan 162 bytes de RAM y no diez kilobytes. El índice es del juego entero
y no del cartucho, y eso importa: antes el
índice era de los mapas de cada ROM y una partida guardada con una ROM no valía
para otra con más mapas: las ranuras se corrían. Viven en la RAM lejana
—`FAR_VARIABLES`, por la ventana de `WMDATA`, como el estado de los paralelos—
y viajan en la partida guardada, que por eso pasó de 256 a 512 bytes de SRAM
por ranura.

Son de **dieciséis bits con signo**. RM2k las lleva a 32 y las topa en ±999999,
pero ninguna del juego pasa de unos cientos —segundos del cronómetro, un azar de
0 a 100, contadores— y lo que no entra en el word no compila, que es más
honesto que truncar. Lo que compila: `ControlVars` de a una variable, con poner,
sumar y restar, y el operando constante, otra variable, un azar entre a y b,
"otro" —el oro y los segundos del cronómetro— o **las coordenadas de un
personaje**; `ConditionalBranch` por variable con las seis comparaciones; y
`TimerOperation` con los segundos desde una variable. Los rangos y el indirecto
no los usa ninguna página.

**Las coordenadas de un personaje** son la clase 6 de `ControlVars`, y es de
lejos la que más destraba de lo que quedaba: **+119 páginas sobre el juego
entero**, de 5016 a 5135 de las 5603 disparables. Es lo que leen los mapas 49,
52 y 54 para seguir al auto de Lashe City. Los sub-operandos son los de
`ControlVariables::Event` de easyrpg-player y de ahí salen, no de memoria: de
las 829 veces que el juego la usa, 412 piden la **x** y 413 la **y**, y las
otras cuatro las coordenadas **en pantalla**, que no se hacen —la nuestra mide
256x224 contra los 320x240 de RM2k, así que el número no sería el del original,
y valen una página—. El id del mapa, la mirada y el id del evento no los pide
nadie. El personaje puede ser el héroe, el dueño de la página o cualquier
evento del mapa, y la celda que se lee es la **viva**: `tile_x`/`tile_y` y
`ev_pos_buf` en la ROM, `Estado.heroe` y `Estado.pos_ev` en el modelo de
`eventos.py`, o sea adonde una ruta forzada o un `ChangeEventLocation` dejaron
al personaje.

Cuál celda es ésa depende de dónde cae el intérprete en el lazo, y desde el
2026-09-20 cae **al final**: `move_hero` corre antes que `eventos_tick`, que es
el orden de `Game_Map::Update`, así que la página de un cuadro ve la celda con
la que el héroe termina **ese** cuadro y no el anterior. En el modelo
`Estado.heroe` ya no la escribe nadie —el lazo de cuadros se fue con la
referencia—: la pone quien arma el `Estado`, y el día que vuelva a haber un
lazo tiene que escribirla en ese mismo lugar.

**Escribir una variable casi nunca pide el refresco de páginas, y eso vale
media Lashe City.** `ControlVars` termina en
`Game_Map::SetNeedRefreshForVarChange`, que **no** marca el refresco por
cualquier escritura: le pregunta antes al `map_cache`, que tiene las variables
que alguna condición de página del **mapa cargado** mira. Acá esa pregunta no
hace falta correrla en la consola: quién mira qué es estático por mapa y el
bytecode de una página se compila para su mapa, así que la contesta el
conversor. Es `VAR_REFRESCO`, el bit de arriba de la ranura de `OP_VAR` y de
`OP_KEY`: `var_apuntar` lo enmascara con `VAR_RANURA` y `var_escribir` lo
mira, que es el único lugar por donde pasan las tres escrituras que hay. Sale
gratis en bytes —cuatro menos de banco 0, porque el `lda #1 / sta refresco`
estaba repetido tres veces— y por eso la ranura tiene que entrar en siete bits:
son 81 variables y `ranura_de_variable` se rompe si alguna pasara de 127.

Lo que cuesta no tenerlo, medido: el mapa 8 tiene una página paralela que escribe
cuatro variables por cuadro —las coordenadas del héroe contra las de otro
evento— y con el refresco pedido en cada una `rutas_de_pagina` recorre sus 68
eventos y sus 106 páginas una vez por cuadro. La vuelta del lazo mide unas 388
líneas de las 262 de un cuadro, así que `wait_vblank` espera siempre al vblank
siguiente y **el juego entero corre a 30 cuadros por segundo**, la mitad exacta.
Con el filtro puesto, 60. Ninguna de esas cuatro variables la mira ninguna
condición de página del juego; sobre los 328 mapas, **14 tienen una condición por
variable y ninguno tiene dos**.

**Y la otra mitad de la misma idea: la página activa de un paralelo tampoco se
recalcula por cuadro.** El HQ de los Lazer Teeth —el mapa 11, once eventos con
página paralela— se cae a 30 cuadros por segundo por una causa parecida y
distinta: sin refresco pendiente, `un_paralelo` igual llama a `pagina_desde_eleg`
una vez por paralelo y por cuadro, que resuelve qué página está activa y le lee
del cartucho los veinticuatro bytes de la cabecera por la ventana de banco. Once
veces por cuadro, para contestar siempre lo mismo. Con el décimo el lazo se pasa
del cuadro, y pasarse no cuesta un poco: se pierde el vblank entero y se cae a la
mitad exacta.

En RM2k la respuesta se calcula una sola vez: `Game_Event::page` es una
instantánea y sólo la reescribe `Game_Map::Refresh`. Acá la instantánea ya
existía —`eleg_por_ev`— y `aplicar_paginas` ya armaba con ella la lista de
eventos con página paralela del mapa; lo que faltaba era que la lista se llevara
**la página** y no sólo el número de evento. Son ocho bytes por ranura en la RAM
lejana —el evento y el puntero a su bytecode, más de qué página salió— escritos
en `anotar_paralelo`, o sea adentro del mismo refresco que ya la tiene leída.

**Y no alcanzaba con eso.** Había una segunda cuenta que se rehacía por
paralelo y por cuadro: `un_paralelo` le da su paso al evento pegado a su
intérprete —es el orden de `Game_Event::Update`, y es lo que hace que los
cuatro autos de Lashe City anden— y para eso busca su ranura de ruta con
`ranura_del_evento`, que recorría **las doce siempre**. En el mapa 11 hay once
paralelos y una sola ranura usada. Ahora `ruta_ev_tope` dice cuántas vale la
pena mirar —la más alta que se llegó a tomar desde que se cargó el mapa, más
una— y la búsqueda va de ahí para abajo, que es lo que deja el corte en `X ==
0` y ahorra el segundo byte de RAM que el banco 0 no tenía. El tope no baja al
liberarse una ranura y no hace falta que baje: una que nunca se tomó tiene $FF
en +0.

Lo medido, contando `vueltas` contra cuadros de hardware en el mapa 11:
**cada arreglo solo deja los 30,00 cuadros por segundo, y los dos juntos dan
59,80**. No es raro y conviene entenderlo: pasarse del cuadro no cuesta un
poco, se pierde el vblank entero, así que quedarse cerca del borde mide igual
que estar lejos. Un número de fps de este mapa vale sobre el árbol donde se
midió y sobre ningún otro.

Con eso `un_paralelo` se queda además sin dos preguntas que no podían dar otra
respuesta —si la página es paralela y si compiló—, porque si no lo fuera el
evento no estaría en la lista. **Eso era una red**, y al sacarla la lista pasó a
ser la única verdad: si un refresco dejara de rehacerla, un evento que ya no
tiene página paralela seguiría corriendo la vieja para siempre. Lo cuida
`pruebas/rpgmaker/test_paralelos.py`, que exige que un switch que cambia la página activa
lo saque de la lista y que apagarlo lo vuelva a meter.

**El azar es el mismo de los dos lados.** Un xorshift de dieciséis bits —`x ^=
x << 7; x ^= x >> 9; x ^= x << 8`—, sembrado en el reset, instrucción por
instrucción en `azar_siguiente` de `main.s` y de `eventos.py`. Por eso una
página con azar se compara pixel por pixel: el Tram Officer del mapa 9 tira un
número de 0 a 100 y dice "It's here!" si sale 90 o más; los dos lados sacan 97.
No hay entropía, y a los efectos de la comparación tampoco la hay en RPG_RT.

`CallEvent` —la página de otro evento, en el lugar— **se compila en línea**: el
cuerpo del llamado se emite donde está la llamada, y no hace falta ninguna pila
de intérpretes porque el llamado corre entero antes de que siga el que llamó.
No toca al intérprete de la ROM: el bytecode que le llega es el mismo. Si el
llamado **no** compila, la llamada se saltea, que es lo que el port venía
haciendo con el comando entero; exigir que compilara costaría 183 de las 221
páginas que compilan y llaman. Con eso el Tram Officer del mapa 9 sube al
Hover-Tram, que es lo único que lo usaba en los mapas 1 a 10.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
