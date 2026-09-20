# abl-audio — A Blurred Line en Super Nintendo

Un port de *A Blurred Line*, un juego hecho en RPG Maker 2000, a la Super
Nintendo. Acá está todo: cómo se lee el juego original, cómo se lo vuelca a un
formato que se pueda mirar, y el port entero con sus trampas y lo que falta.

Hubo antes un port a Mega Drive. Se sacó de este repo cuando quedó claro que el
camino era la SNES —el audio del S-DSP convence y el del YM2612 no—, y vive
aparte en `abl-sega`. Lo que era compartido de verdad se quedó, con nombres que
no mienten: `tools/rpgmaker/rm2k.py` para las reglas de RPG Maker 2000,
`tools/port/asignador.py` —que se llamó `pixeles.py`— para decidir qué colores quedan
y cómo se agrupan, y `tools/audio/musica.py` para pasar de un MIDI a notas y voces.

Lo que **no** está acá: dónde quedamos —eso es `ESTADO.md`— y el relato de cómo
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

## Leer el juego original

Lo primero que hace el conversor es leer los datos de RPG Maker 2000 y
reconstruir lo que se ve: las dos capas de tiles de cada mapa, resueltas contra
su ChipSet, como imágenes que después se cortan en tiles. No hay nada que
instalar: es Python con Pillow, que ya está en el sistema.

El mapa de arranque del juego es el 4, "Blank (Leave START here)": un cuarto
vacío de 20x15 que sólo teletransporta. El primer mapa de verdad es el 1.

### Piezas

Cómo está repartido `tools/` en carpetas, y qué puede importar de qué, está en
`tools/README.md`.

    tools/rpgmaker/lcf.py               el juego, leído del volcado a JSON de data/
    tools/rpgmaker/ditto_schema.py      generado: los nombres, defaults y enums de ese JSON
    tools/rpgmaker/gen_ditto_schema.py  lo genera, desde el esquema de Ditto
    tools/render/chipset.py             expansión del ChipSet a un atlas de tiles resueltos
    tools/render/charset.py             recorte de sprites de personaje
    tools/render/render_map.py          las capas de un mapa como imagen, y los CharSets
    tools/rpgmaker/event_codes.py       generado: nombres de los opcodes de evento
    tools/protocol/                     el generador, en Rust: declaración -> constantes
    tools/port/event_opcodes.py         generado desde tools/protocol/events.toml
    tools/audio/music_opcodes.py        generado desde tools/protocol/music.toml

El formato binario de RM2k ya no lo lee ningún Python de acá: lo lee Ditto, una
sola vez, y lo deja en `data/`. Ver "Los datos en formato versionable".

Todo sale del juego original, que **no está en el repo**: vive en
`/extras/abl-rm` y de ahí salen los `.lmu`, la `RPG_RT.ldb` —qué chipset usa
cada mapa— y la `RPG_RT.lmt` —nombres y mapa inicial—. Se puede apuntar a otra
copia con `ABL_GAME_DIR`. Lo que el juego no trae lo pone el RTP: ver más
abajo.

### Lo que hay que saber del formato

**LCF** es TLV: un header con el nombre del formato, y después chunks de
`(id, largo, bytes)` terminados en id 0. Los enteros van en BER, 7 bits por
byte. Los campos que quedaron en su valor por defecto no se escriben — por eso
`Map` tiene que conocer los defaults (chipset 1, 20x15).

**Los ChipSets no son tilesets.** La mitad izquierda de la imagen de 480x256
son autotiles: bloques de bordes que el motor combina según los vecinos. El
editor guarda en el mapa el ID de la combinación ya calculada, así que para
renderizar hay que pre-generar las 1419 combinaciones posibles en un atlas de
32x45 e indexarlo por ID. `tools/render/chipset.py` es un puerto de
`lmu2png/src/chipset.cpp` de EasyRPG Tools, que es donde están todos los
offsets mágicos.

**Hay dos capas**, y el orden de dibujado entre ellas depende de los flags de
passability del chipset (`0x30` en la baja, `0x10` en la alta marcan lo que va
por encima del jugador). Los eventos se intercalan según su propia capa: tiles
bajos → eventos capa 0 y 1 → tiles altos → eventos capa 2.

**Un evento tiene varias páginas**, cada una con sus condiciones (switch,
variable, ítem, actor, timer) y su propia apariencia. El motor usa la de número
más alto cuyas condiciones se cumplen todas. Como no simulamos la lógica del
juego, usamos la última página sin ninguna condición: es exactamente el estado
de partida nueva. Un evento cuyas páginas tienen todas condiciones no se
dibuja, que es lo correcto — todavía no existe en pantalla.

Cada página trae dirección y frame explícitos, así que no hay que inventar una
pose. Y un evento **sin** CharSet se dibuja como un tile de la página alta del
chipset: así están hechas las puertas, los cofres y buena parte del decorado.

### El RTP

ABL usa recursos que no vienen con el juego: 5 chipsets (`ChipSet1/2/3`,
`Basis`, `Inner`) y 17 charsets (`Chara1-4`, `Crown*`, `Future1-3`, `Men1`,
`Women1`, `People7`, `Vehicle`). Están en el **RTP de Don Miguel** (junio de
2000), que es el que se usaba fuera de Japón: su traducción del RPG Maker 2000
traía su propio RTP traducido, con archivos agregados por él que no existen en
el japonés — `Future1-3`, por ejemplo. El RTP libre de EasyRPG **no sirve**: es
un reemplazo con arte distinto y otros nombres (`Actor1-4` en vez de
`Chara1-4`).

No está en el repo: vive en `/extras/rtp`, del mismo lado que el juego original
y por la misma razón —no es nuestro para redistribuir—. Para reponerlo, de
`RTPE.EXE` (un SFX de RAR):

    7z x -oRTP-tmp RTPE.EXE && mv RTP-tmp/Data/RTP /extras/rtp && rm -rf RTP-tmp

Se puede apuntar a otra copia con `ABL_RTP_DIR`.


## Los datos en formato versionable

    just datos         # el juego -> data/, con Ditto

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano. Y
**es de donde el port lee el juego**: `tools/rpgmaker/lcf.py` sale de acá, así que el
conversor y las pruebas están mirando estos archivos y no los binarios. Quién lo
escribe es **Ditto** (`tools/ditto/`), que además sabe volver: `ditto pack` rearma los
330 archivos byte por byte. El porqué de la decisión está en `DITTO.md` y lo que
hay adentro, en `data/README.md`.

    data/ditto.json           la versión del volcado y el header de cada archivo
    data/maps.json            el árbol de mapas y la posición inicial
    data/maps/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/maps/Map0001.tiles   las dos capas de tiles, una fila del mapa por línea
    data/db/*.json            la base de datos, una sección por archivo

Son 19,4 MB en 674 archivos: los 328 mapas con sus eventos y comandos, más la
base de datos entera — 60 actores, 400 skills, 450 ítems, 175 enemigos, 300
tropas, 180 animaciones, 60 eventos comunes, 1200 switches y 250 variables.

**Los tiles van en texto, no en binario.** En binario ocuparían la mitad, pero
serían opacos para git; en texto, cambiar un tile cambia una línea, en la fila
y la columna en que está en el mapa.

**Se omite lo que está en su valor por defecto**, que es exactamente lo que
hace el binario y con la misma tabla. Así que un campo ausente **no vale cero**:
vale lo que dice el formato. Esa tabla es `tools/rpgmaker/ditto_schema.py`, generada
desde el esquema de Ditto, que se genera desde liblcf. Es la respuesta al bug
que originó todo esto: el `max_hp` de un enemigo llegaba con 1 donde el formato
dice 10, porque el default estaba escrito a mano y estaba mal.

**Y los enums salen como texto**: `"trigger": "auto_start"` en vez de
`"trigger": 3`, `"code": "ShowMessage"` en vez de `10110`. Los nombres son los
de liblcf.

**Encoding.** El texto es cp1252, porque ABL se hizo con el RM2k de Don Miguel.
Quedan un par de mensajes del RTP japonés que el autor nunca tocó y siguen en
Shift-JIS: en el JSON salen como caracteres raros —decodificarlos adivinando le
costaría a Ditto la vuelta exacta— y el que los interpreta es `tools/rpgmaker/lcf.py`,
por los bytes que cp1252 no define.

## El port a Super Nintendo

Dibuja el mapa y reproduce su tema. Empezó como una rama aparte del port a Mega
Drive, para ver si la SNES se acercaba más al original; la respuesta fue que sí,
y el port a Mega Drive se mudó a su propio repo. Las comparaciones con él que
aparecen más abajo se quedan porque explican por qué las cosas son como son.

### Por qué

El sonido de la Mega Drive quedó lejos del MIDI de la PC, y no por falta de
voces sino por el método: el YM2612 es síntesis FM y el MIDI de Windows XP lo
tocaba un sintetizador **por muestras**. La SNES también es por muestras, así
que el problema deja de ser "imitar un piano con cuatro operadores" y pasa a ser
"comprimir estas muestras", que es mecánico.

De paso: 15 bits de color contra 9, y 8 paletas contra 4. Los 108 colores de los
seis CharSets del Auditorium entran sin fusionar ninguno.

### Veredicto

Probado en emulador: **suena mucho mejor que la Mega Drive y cerca del
original**. Esa era la pregunta que motivaba la rama, y la contesta a favor de
la SNES.

### El mapa

Va en **modo 3, con 8 bits por pixel**. Ahí cada pixel del fondo es un índice
directo a CGRAM y no hay paleta por tile, así que el problema que dominaba el
conversor de la Mega Drive —repartir los colores en grupos tales que ningún tile
necesite dos— simplemente no existe.

    modo 1 (4bpp, 8 paletas):  60 colores -> 28
    modo 3 (8bpp):             60 colores -> 60, sin fusionar

No era evitable de otra forma: Map0007 tiene tiles de 16, 17 y 19 colores, y
ésos no entran en una paleta de 15 por más paletas que haya. Cuesta el doble de
VRAM por tile, 64 bytes en vez de 32; con 92 tiles son 5,8 KB de los 64.

El resultado se verifica pixel por pixel a 15 bits, que es la profundidad real
de la consola, contra las capturas congeladas de la tanda.

En la Mega Drive esto no se podía hacer: los 9 bits obligaban a fusionar
colores, así que sólo se podía comparar por forma. Acá la comparación es exacta.

### La cámara

El scroll es por hardware: mover la cámara es escribir dos registros. Lo único
que hay que cuidar es no salirse del mapa.

El tilemap del PPU se arma con "pantallas" de 32×32 celdas encadenadas en VRAM,
y no van una al lado de la otra en memoria: cada una ocupa sus 1024 celdas
seguidas.

Dónde tiene que frenar no se estima: es exactamente el ancho del mapa menos el
de la pantalla, que el conversor emite como `CAM_MAX_X` y `CAM_MAX_Y`.

Que frene ahí lo cobran las caminatas de `test_heroe`, en
`pruebas/rpgmaker/test_tanda.py`: cada dirección se sostiene hasta chocar, y
una caminata termina contra un borde del mapa, que es donde la cámara queda
pegada. Las cuatro esquinas de un mismo mapa, en cambio, ya no las mira nadie:
eso era la receta `mapa`, que se fue el 2026-09-19.

Las cinco capturas de un mapa —la parada y las cuatro direcciones— las corre
`test_heroe` de `pruebas/rpgmaker/test_tanda.py`, sobre los mapas de `MAPAS_DE_HEROE`.
Que la cámara llegue justo al ancho del mapa menos el de la pantalla, y ni un
pixel más, prueba a la vez el movimiento y el tope.

### Los mapas que no entran

El tilemap del PPU no pasa de 64×64 celdas y encima hay que repartirle la VRAM
a los tiles, así que la ventana que le queda son **64×32 celdas: 512×256
pixeles**. Los mapas del juego llegan a 1000×80 celdas de 8. De los **328**
que tiene el juego, **148 no entran** en esa ventana.

La ventana no se desplaza: se la trata como un **toro**. La celda `(mx, my)` del
mapa vive siempre en la ranura `(mx mod 64, my mod 32)`, y el scroll por
hardware da la vuelta solo porque 1024 —el máximo del registro— es múltiplo de
los 512 que mide la ventana. Cuando la cámara cruza el borde de una celda, sólo
hay que reescribir la columna o la fila que acaba de entrar; la que sale está 32
columnas o 4 filas afuera de la pantalla y nadie la mira mientras se la pisa.

De ahí sale una propiedad cómoda: **no hace falta llevar la cuenta de qué parte
de la ventana está al día**. Como la ranura de cada celda es fija, escribir de
más nunca puede pisar algo que se esté viendo, y la inducción cierra sola desde
el llenado inicial.

Las tiras se arman en RAM fuera del vblank y se suben cuando empieza el
siguiente, igual que OAM. Una columna sale de un DMA por capa —el PPU puede
avanzar de a 32 palabras tras cada escritura, que es justo lo que mide una fila
del tilemap— y una fila sale de dos, porque las dos pantallas de 32×32 no son
contiguas en VRAM.

#### El mapa no se guarda como tilemap

Expandido no entraría en el cartucho: 1000×80 celdas por dos bytes son 156 KB,
más que la ROM entera. Lo que se guarda es la **celda de 16×16 de RM2k**, que es
la unidad con la que el juego fue dibujado y que se repite muchísimo.

    mapa 52, 1000x80 celdas    tilemap expandido   160.000 B
                               grilla de bloques    40.000 B + 1.744 B de tabla

El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa de encima y su
pasabilidad, todo junto. En todo el juego el máximo son 512 bloques distintos.

Que la pasabilidad viaje en el bloque **borró la tabla de colisión entera** —un
byte por celda, hasta 20 KB. Y no es un atajo: dos celdas que se dibujan igual
podrían tener permisos distintos si vinieran de tiles distintos del ChipSet, así
que la pasabilidad va en la clave con la que se deduplica y esas dos se separan
solas.

Dónde está el héroe dentro de la grilla tampoco es un índice sino un **puntero
que se mueve con él**, una celda o una fila por paso. Así nunca hay que
multiplicar ni armar una dirección de 24 bits desde cero, que en LoROM es
incómodo porque los bancos no son contiguos.

#### El reparto de la VRAM lo decide el conversor

Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites va
de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Con los
dos tilemaps clavados al final quedan 56 KB para los tres bancos de tiles, y las
granularidades dejan exactamente dos cortes posibles:

    ancho    fondo 512 tiles (32 KB) | sprites 512 (16 KB) | encima 256 (8 KB)
    fondo    fondo 640 tiles (40 KB) | encima 256 (8 KB)   | sprites 256 (8 KB)

Ninguno sirve para todos los mapas: el que más tiles de fondo gasta necesita
620, y Lashe City necesita 320 de sprite. Cuál toca lo decide el conversor
—junto con los valores ya armados de `OBSEL` y `BG12NBA`— y viaja en el `.inc`.
La ROM no elige nada.

Con la ventana de mensaje puesta hay que sacarle 8 KB de tiles y 2 KB de tilemap
a alguien, y eso da otros tres cortes. Son seis en total, y `vram_layout`
devuelve **el primero que entre**, así que agregar uno al final no le cambia el
reparto a ningún mapa que ya lo tenía:

    ancho          fondo 512 | sprites 384 | encima 256
    fondo          fondo 640 | encima 256  | sprites 256
    ancho+sprite   sprites 512 | fondo 448 | encima 256
    ventana        sprites 448 | ventana_map | fondo 448 | encima 128 | ventana 256
    ventana+fondo  sprites 256 | fondo 480  | ventana_map | encima 128 | ventana 256
    ventana+sprite sprites 512 | fondo 384  | ventana_map | encima 128 | ventana 256

Los dos "+sprite" los pide **Delcentric Factory**, el camino al auditorio:
gasta 217 tiles de fondo y **475 de sprite**
—26 NPCs con CharSet son 28 ranuras, o sea 448 tiles justos, y encima van los 8
glifos del cronómetro y las 19 gotas de lluvia—. Los 512 no son una elección:
son el tope del hardware, porque el campo de nombre de OAM tiene nueve bits y
con el name select de `OBSEL` en cero las dos tablas quedan pegadas.

**Lo que no entra en ninguno de los seis** es un mapa que gaste mucho de las dos
cosas a la vez. El caso medido es `Sector 34 With Car`, el mapa 38: 476 tiles de
fondo y 347 de sprite, que son 41 KB de tiles más los 10 de la ventana, los 8 de
la capa de encima y los 8 de los dos tilemaps. Son 67 de 64.

#### El reparto de CGRAM, también

Las 256 entradas de CGRAM se parten al medio: la mitad de arriba es de los
sprites. La de abajo la comparten el fondo, que va en 8 bits y direcciona CGRAM
en directo, y la capa de encima, que va en 4 bits y por lo tanto cuenta su
índice dentro de una paleta de 16.

Un corte fijo no sirve: con dos paletas clavadas para la capa de encima se caen
los mapas cuya capa de encima pide tres o más, que son varias decenas y entre
ellos los tres primeros del juego. Y hay una causa que **no la arregla ningún
reparto**: un tile suelto de 17 colores no entra en una paleta de 15 por muchas
que haya, y eso se arregla fusionando, que es lo que la Mega Drive ya hacía con
el fondo.

Así que el corte lo decide el conversor mapa por mapa, y **el fondo tiene la
primera opción**: se queda con las paletas que necesita para los colores que
realmente usa, y la capa de encima se lleva las que sobren —hasta las que pida,
nunca más— y fusiona si no le alcanzan. Va en ese orden porque son 300 mapas
cuya capa de encima pide una o dos paletas contra un puñado que pediría siete:
servir primero al de encima le sacaría colores al fondo en todos para que unos
pocos no fusionen.

El informe del conversor lo dice mapa por mapa: cuántos colores se quedó el
fondo de cuántos había, cuántas paletas se llevó la capa de encima, desde cuál,
y cuántos colores le tocó fusionar.

Que las dos capas se conviertan juntas no es comodidad: el corte no lo puede
decidir ninguna por su cuenta, así que `convert_layers()` es el único lugar
donde está escrito. Antes cada llamador convertía una y después la otra, y que
las tres copias del orden coincidieran era cuestión de suerte —justo la forma de
error que ya nos había aflojado la comparación una vez.

### El agua se mueve, y cuesta un DMA de 1664 bytes

RM2k anima dos familias de tiles del ChipSet, con relojes distintos y sin que
el mapa tenga nada que decir al respecto: los autotiles de agua A/B/C, que
recorren tres dibujos cada 24 cuadros en el ciclo 0,1,2,1, y los "tiles
animados", cuatro dibujos cada 6. Las dos cuentas son `TilemapLayer::Draw` de
easyrpg, `tilemap_layer.cpp:289`, y las dos cadencias por defecto —el
`animation_type` y el `animation_speed` del ChipSet— son las que tiene este
juego entero: de sus 52 ChipSets sólo dos las pisan, y ninguno de los dos lo usa
un mapa del port.

**Dónde se ve, medido antes de escribir una línea.** Renderizando cada mapa en
sus tres o cuatro dibujos y contando pixeles distintos:

    mapa 5  Core Retrospective   1.002.474 px de 1.920.000   52%
    mapa 2  Linkage Block            6.872 px de 2.560.000  0,3%
    mapa 3  Emitter Room               400 px de 1.440.000  0,0%
    mapa 6  CoreRetro II                53 px de 2.560.000  0,0%

El recuerdo de Core y Manta es el mapa donde esto se nota; el Emitter Room, casi
nada, y eso que tiene 4899 celdas de autotile de agua: en `Future1` los tres
dibujos de esa zona están pintados iguales, así que lo único que se mueve son
nueve tiles del grupo "animados".

**Cómo se hace: pisando el dato del tile, no el tilemap.** Un mapa de 100x75
celdas tiene 30000 entradas de tilemap y sólo unos pocos tiles distintos que se
mueven: en el mapa 5 son **26 tiles de 8x8** de los 157 del banco, en el 2 son
7 de agua más 12 animados, en el 3 son 8 y en el 6 son 2. Así que animar es
volver a subir esos tiles y no tocar nada más — y el conversor los deja **en una
corrida contigua al final del banco**, para que un paso sea un DMA solo: 1664
bytes en el mapa 5, 128 en el 6.

Para que eso sea correcto hacen falta dos cosas más, y las dos las decide
`convert()`:

* **Un tile que se anima no se comparte con una celda quieta.** Si se
  compartiera, pisarlo haría parpadear también a la quieta. Medido: en los
  cuatro mapas no hay una sola colisión, así que separarlos no cuesta tiles.
* **El espejado se prueba sobre los dibujos juntos.** El PPU espeja el tile, no
  cada dibujo por su cuenta, así que dos celdas comparten tile sólo si las
  cuatro orientaciones coinciden en *todos* los dibujos.

Y la paleta se reparte contando los colores de todos los dibujos: el agua del
mapa 5 trae tres colores que no están en el dibujo que se ve al entrar, y sin
ellos el paso 1 no se podría escribir.

**En la consola no gasta un byte de RAM.** No por elegancia: la BSS estaba en
7680 de 7680 y la página directa en 255 de 256, así que no había dónde poner ni
un contador ni un puntero para `lda [puntero], y`. En qué punto del ciclo va
cada familia sale de **dividir `vueltas` por su cadencia con el divisor del
hardware**, y el resto de esa misma división dice si este tick es el del cambio,
que es lo único que hay que preguntar para saber si hace falta el DMA. Dónde
están los tiles y los dibujos lo trae `anim_tabla`, que arma el conversor con
la dirección de VRAM ya resuelta.

Lo que se paga es que `vueltas` es de dieciséis bits: cada dieciocho minutos la
cuenta da la vuelta y el ciclo se saltea un dibujo. Está declarado en
`assets/LIMITACIONES.md`, y no lo alcanza ninguna prueba: dieciocho minutos son
mucho más de lo que corre el caso más largo.

**La decisión no entra en el vblank, y eso no es gusto.** El vblank del mapa 8
—el más cargado de sprites del port— no tiene un ciclo de sobra: **veinte `nop`
puestos ahí a propósito le cuestan 61 pixeles**, porque la cola de poses se le
va del vblank y las últimas escrituras caen con la pantalla ya encendida. Las
dos divisiones iban ahí en la primera versión y le costaban 313. Así que quien
decide es `anim_tick`, en el cuerpo del lazo, y deja **un byte** —el último
libre de la página directa— con tres bits por familia: cero es "nada", y si no
el dibujo más uno. En el vblank queda un `lda` y un `beq`.

**La fase se midió, no se razonó.** Aunque el DMA salga en el vblank siguiente,
igual que OAM, el dibujo que corresponde es el del tick tal cual y no el del
anterior: mirar el anterior da rojo en **un tick de cada 24** —el del cambio, y
nada más—, que en el mapa 5 son 18349 pixeles. El caso que lo cobra es
`caminando 5 left` con el avance 46, que es el tick 24 justo: un avance de
N pixeles es el tick N/2 + 1, así que se le puede pedir a la tanda el cuadro
exacto en que el agua cambia.

**Y el reloj de la ROM no es el tick de la partida.** Adentro del negro de un
teletransporte el mundo está congelado y el tick no avanza, pero la consola
sigue dando vueltas al lazo: son 70 por fundido. La cuenta que valía era el
tick más `FUNDIDO_TOTAL` por cada fundido, y sin eso la escena de Core y
Manta se iba un dibujo desde el primer teletransporte. Los dos contadores que
la llevaban eran de la referencia y se fueron con ella; del lado de la ROM
quedan `FUNDIDO_TOTAL` y `fundido_tick`, que es donde los 70 pasan.

Los dos casos nuevos de la tanda están medidos con la fase rota a propósito, que
es lo único que prueba que miran algo: `caminando 5 left "40 46 48 50"`
cobra 18349 pixeles y `caminando 3 down "54 56 58 60"` cobra 211. Hacen
falta los dos: el mapa 5 no tiene tiles animados y la corrida de agua del 3 sale
vacía.

### El save point: anima quieto y guarda a disco

`SaveByTalansPad0`, el evento 67 del mapa 8, son tres comandos —`PlaySound`,
`OpenSaveMenu`, `ChangeSaveAccess`— y una página con `animation_type` 3, que en
RM2k es "Fixed Dir/Continuous": recorre el ciclo de caminata **sin moverse**.

**La animación de un evento quieto no tiene dónde guardar su contador.** Los que
caminan lo llevan adentro de su ranura de ruta; los quietos no tienen ranura, la
fila del NPC no tiene un byte libre —el +11 es el alto del salto— y la BSS está
en 7680 de 7680. Así que la columna sale del reloj del juego, igual que el agua:
`vueltas` dividido por `ANIM_CONTINUA[velocidad]`, y el mismo ciclo de cuatro
pasos con el tercero repitiendo el primero. Lo que se pierde es la fase —en RM2k
cada personaje arranca su contador cuando el mapa lo crea— y está declarado en
`assets/LIMITACIONES.md`.

Lo que **sí** cuesta VRAM es que deje de compartir tiles: un evento quieto usa la
ranura de su (CharSet, índice, pose), y para animarse necesita las doce poses
suyas, como los que caminan. Son doce tiles de sprite por evento. El mapa 52
tiene **treinta** eventos así y pedía 572 tiles de sprite contra los 384 que
entran, así que hay un tope: **un mapa con más de cuatro no anima ninguno**, y no
unos sí y otros no —dos fuentes iguales, una moviéndose y la otra congelada, se
ve peor que las dos quietas—. Medido sobre los 328 mapas del juego: 312 tienen
cuatro o menos.

La fase se midió como la del agua, y la cobra
`escena 8 "9 55" 0 down "20 30 40 50"`: la celda (9,55) lo deja en pantalla
y los cuatro cuadros caen en tres columnas distintas del ciclo. Sin el `inc` que
corrige la fase se queda una columna atrás, que son 76 pixeles.

**Guardar abre la pantalla de ranuras, como en RM2k.** `OpenSaveMenu` apila
la misma pantalla que "Resume the Story" abre desde el título, en modo guardar
—"Save in which slot?", que es `save_game_message` del LDB—, con el cursor en
la ranura que la partida está usando, que es el `latest_slot` de
`Scene_File::Start` sin fechas. A elige y guarda ahí, B vuelve sin guardar, y
no se pregunta si la ranura estaba ocupada porque `Scene_Save::Action` tampoco
pregunta. El cartucho declara SRAM con batería en la cabecera —`$02` y 8 KB— y
en el EverDrive eso es una pila de verdad.

Tres cosas de cómo está hecho:

* **Bloquea adentro del intérprete y no cuesta ningún tick.** La pantalla corre
  su propio lazo de cuadros desde `op_save`, igual que desde el título, y
  `vueltas` no avanza mientras se ve. Es lo que hace RM2k: la escena apilada
  para el reloj del mapa, y la página sigue por el comando siguiente cuando se
  cierra. Por eso `OP_SAVE` ocupa su byte y no cuesta un cuadro, y
  después de cerrar el mapa sigue por el tick que le tocaba, tarde lo que tarde
  el jugador.
* **Al cerrar se repone sólo lo que la pantalla pisó**, y no el mapa entero:
  `volver_al_mapa` vuelve a subir el banco de tiles de BG1 con `load_map`, tiñe
  de nuevo, y repone los registros con `ppu_init`. Llamar a `cargar_mapa`
  reiniciaría los eventos, las rutas y las poses, que es justo lo que tiene que
  sobrevivir. Para que eso alcance, **la pantalla vive en `$2000`..`$3600` de
  la VRAM**, que es la intersección del banco de BG1 de los cuatro repartos de
  `vram_layout`, y el conversor lo comprueba. Con las direcciones del menú del
  título —`$4400` y `$5000`— pisaba los sprites del reparto ancho, que arrancan
  en `$4000`: 267 pixeles en el héroe del mapa 73, sólo con el grupo 11, porque
  el líder del grupo 10 cae en el bloque 0 y se salvaba. Cuesta dos cuadros
  negros al volver: 30 KB de DMA no entran en un vblank.
* **La pantalla va en toda ROM**, con título o sin él. Con sus tiles emitidos
  sólo bajo `--con-titulo`, abrirla desde una ROM sin título era un DMA de cero
  bytes —o sea de 65536— que llenaba la VRAM de basura.

**Cada ranura con partida muestra lo que muestra RM2k**, que es lo que
`Window_SaveFile::Refresh` dibuja por archivo: el nombre del archivo, el
nombre del líder, el nivel —`lvl_short` en el color 1 del sistema y el número
a dos cifras, "L  1", mockeado en 1 porque no hay actores con nivel— y las
**caras** del grupo, del FaceSet y a 48x48, que es por lo que la fila mide 48
pixeles.

Está mirado contra el juego original corriendo la misma escena en EasyRPG, y
no sólo leído del código. Lo que difiere a propósito: los puntos de vida
no van, porque este port no los tiene; entran tres caras y no cuatro, y
pegadas en vez de a 56 px, porque en 256 de ancho no hay más lugar sin comerse
el borde que un televisor de tubo no muestra; y el cursor es un ">" sobre
fondo negro y no la caja del skin, que es como estaba el menú desde el título.

Cómo está hecho, porque no es una variante más de la fila pre-renderizada: el
grupo lo dice **la partida guardada** —los seis bytes de `grupo` en la SRAM de
la ranura, en `PARTIDA_GRUPO`— y por cada actor que pueda entrar al grupo con
los mapas de la ROM, `miembros_posibles`, el conversor emite un bloque de 36
celdas con su cara y otro de 14 con su nombre. `ranura_pintar` sube la fila y
después, si tiene partida, `ranura_grupo_pintar` lee el grupo de la SRAM y
escribe encima los rectángulos que le tocan, con `ranura_rect_subir`: un DMA
por fila de celdas, con el puntero de origen que el DMA mismo va dejando donde
terminó. A dónde va cada cara y cada nombre lo dicen dos tablas del conversor
—`ranura_cara_vram`, de a cuatro por ranura para no multiplicar por tres, y
`ranura_nombre_vram`—, como `ranura_vram` para las filas. Cada cara lleva su
paleta, reducida a 15 colores con `reducir` como la imagen del título, en las
paletas 1 a 7 de BG2; en RM2k el índice 0 del FaceSet es transparente, igual
que en un CharSet, y `ABLFaces` lo usa: dibujado opaco cada cara era un
cuadrado rojo. Un actor sin cara —DummyHero— no dibuja nada, como `DrawFace`
con un nombre vacío.

La variante llena no la puede ver la tanda —la SRAM del emulador arranca
virgen— y la cobra `test_la_pantalla_de_ranuras_muestra_el_grupo_guardado`,
que guarda con Talan y DummyHero en el grupo, reinicia, entra por "Resume the
Story" y compara la pantalla **pixel por pixel** contra `titulo.render_ranuras`
con ese grupo, con el cursor en la primera fila y después sobre la de Talan,
que es lo que la repinta en el vblank. Contra una referencia sin grupo o con
Kersh son unos 400 pixeles, así que el cero no es vacío.

Lo cobran `test_guardar_pantalla` y `test_guardar_vuelve`, de
`pruebas/rpgmaker/test_tanda_pantallas.py`, en seis cuadros y todos en cero: la pantalla
al abrirse y con el cursor dos ranuras abajo, y el mapa de vuelta después de
cancelar y después de elegir, en dos ticks. Los toques de adentro de la
pantalla van con `toques_hardware`,
que cuenta cuadros de hardware desde el arranque: un toque por tick no puede
caer donde no hay ticks. Y lo que queda en la SRAM lo mira
`pruebas/rpgmaker/test_guardar.py`, que ahora **atraviesa la pantalla** —baja el cursor
y aprieta A— en vez de escribir `ranura` a mano; `menu_abierto` es el byte que
la ROM le deja para saber cuándo, porque esperar por ticks ahí se colgaría.

Qué se guarda lo dice **una tabla y nada más**, `partida_tabla` en `main.s`:
pares de (dirección en la WRAM, cuántos bytes). Guardar y cargar la recorren los
dos, así que no se pueden ir uno del otro, y agregar un campo es una línea. Hoy
son 154 bytes: dónde está el héroe, en qué mapa, el grupo, el tinte, el
cronómetro, el oro y los 128 bytes de switches.

La copia va **por DMA en las dos direcciones**, y lo que lo hace posible es la
ventana de la WRAM: el bus B no llega a la SRAM, pero sí a `WMDATA`, así que la
SRAM va del lado del bus A y la WRAM del otro. Guardar es un DMA de B a A —el
bit 7 de DMAP— y cargar el mismo al revés.

Dos detalles que costaron su rato y que están anotados donde muerden, arriba de
`SRAM_MAGIA` en `main.s`: que la partida viva en `$0100` y no en `$0000`, y que
la magia se compare contra inmediatos.

Una ranura vale si tiene la magia `ABLS` y la suma de sus bytes cuadra. Las dos
cosas hacen falta: la SRAM sin escribir trae basura —snes9x la llena de $60— y
una ROM de prueba que la tomara por buena cargaría una partida inventada.

**Lo que se escribe no lo puede cubrir la tanda de pixeles**, porque guardar
no cambia un pixel. Lo cubre `pruebas/rpgmaker/test_guardar.py`, que hace lo único que
prueba algo: va a otro mapa, prende un switch, guarda, **resetea la consola de
verdad** y mira dónde arranca. La SRAM sobrevive al reset y la WRAM no, así que
si la partida vuelve es porque salió del cartucho. Con `guardar_partida`
cortado a propósito, tres de sus cuatro pruebas dan rojo.

### El menú de pausa

**B abre el menú**, que es `Scene_Menu` de RM2k: las cinco
órdenes a la izquierda —`Use Item`, `Tech Skill`, `Equipment`, `Save`, `End
Game`, con los términos del LDB—, el oro abajo y el grupo a la derecha, con la
cara, el nombre, el nivel —mockeado en 1, como en las ranuras—, el estado y
los HP del nivel, llenos. Hoy **sólo guardar hace algo**: abre la pantalla de
ranuras en modo guardar y, elija o cancele, vuelve al menú con el cursor en
Save, como `Scene_Save` vuelve a `Scene_Menu`. Las otras cuatro van en el
color 3 del sistema, el de "no se puede", y A no hace nada con ellas: ítems,
técnicas y equipo son los pasos que siguen, y terminar el juego pide volver al
título sin reiniciar el SPC700.

**La geometría es nuestra**, no la de RM2k: allá son 320x240 con ventanas, acá
256x224 sobre fondo negro como la pantalla de ranuras, sin el título del
actor, la experiencia ni los SP, y el oro con una cifra por celda y no a los 6
pixeles de la fuente, para que la ROM las escriba de a una sin armar tiles. Es
cosmético y está declarado.

**Los HP de ahora se escriben corriendo, y el máximo va horneado.** La fila de
cada actor es un bloque de celdas que el conversor dibuja una vez, así que
cualquier número que lleve adentro es el del día que se convirtió: con los HP ahí
el menú muestra siempre el máximo del nivel por más que una pelea los baje, y la
comparación de pixeles no lo ve porque `render_menu` hornea el mismo número. Las
tres cifras las escribe `menu_hp_escribir` desde `FAR_HP`, con las mismas celdas de
una por cifra que el oro y por la misma razón; el "/máximo" de al lado sigue
horneado, que ése no cambia. Vale para las dos pantallas que comparten el
panel, el menú y la elección de actor, porque las dos pasan por
`menu_grupo_pintar`.

Las cifras caen alineadas con las del oro sin tocar nada: las dos líneas se
dibujan a dos pixeles del borde de arriba de su celda. Y el precio de las
celdas de 8 pixeles es el mismo que ya se paga en el oro. Todo lo demás sale de
`titulo.py`: `render_menu` es la referencia y el conversor emite **los mismos
bloques de celdas**, en el mismo banco de tiles y la misma paleta que la
pantalla de ranuras —las caras son las mismas y guardar se abre desde el menú—.
Las órdenes en gris llevan su propia paleta de BG2: el color 3 es un degradé y
con el del texto sumaban 18 colores, así que a las caras les quedan seis
paletas.

**La séptima cara se cuelga de una paleta prestada.** La lista de caras no es la
del grupo sino la de todos los que algún `ChangePartyMembers` de los mapas de la
ROM pueda meter, y con Lashe City entera son ocho: los cuatro de la intro más
Arden, Saldra, el Gang Member de los Rat Tracks y AG7-17. Cada color de la cara
que sobra va al más cercano por luma de la paleta a la que menos colores le
falte, que es lo que `cabe` hace con los sprites y por la misma razón: un
personaje con colores raros es un error visible y un mapa que no entra es un
mapa menos. Se ve en el informe del conversor, que las nombra.

**Cuándo se abre es lo de RM2k.** `Game_Player::Update` anota el pedido
—`menu_calling`— si B se aprieta con el menú permitido, sin mensaje y sin
página corriendo; `UpdateNextMovementAction` lo atiende con el héroe quieto:
con una página corriendo lo tira, con un mensaje lo deja esperando, y si no,
abre el menú antes de mirar la cruceta. O sea que B a mitad de un paso abre el
menú al terminarlo. En la ROM el pedido es el bit 7 de `FAR_ACCESO`,
`pedir_menu` lo anota después de `move_hero` y `move_hero` lo atiende; un
teletransporte lo tira, como `MoveTo`. Y el B que cancela una elección se
consume ahí mismo: en RM2k la ventana procesa la tecla después del héroe, y
acá la elección corre antes que `pedir_menu`. Lo mismo al cerrar el menú y la
pantalla de ranuras: el B que cerró no le llega a nadie más.

`ChangeSaveAccess` y `ChangeMainMenuAccess` **se honran**: dejaron de estar
entre los comandos ignorados, compilan a `OP_ACCESS` y apagan o prenden los
bits 0 y 1 de `FAR_ACCESO`, que viaja en la partida. Guardar prohibido pone
Save en gris; el menú prohibido hace que B no lo pida. El save point no mira
el permiso, como `OpenSaveMenu`.

Mientras el menú se ve **el reloj del juego no corre**, igual que con la
pantalla de ranuras, así que el menú no cuesta ningún tick y el mapa sigue por
el cuadro que le tocaba. Lo cobran `test_menu` y `test_menu_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py`: el menú como se abre, con el cursor movido, y
el mapa después de cerrar. Quien lo compara contra una referencia en Python
—`titulo.render_menu`, que sigue viva— es `pruebas/rpgmaker/test_menu.py`, y es además lo
que mira lo que la tanda no alcanza: el menú con un grupo y oro
puestos, guardar desde el menú, los dos permisos puestos por el bytecode, B a
mitad de un paso, y que los permisos vuelvan de la SRAM.

### La pantalla de ítems

"Use Item" abre `Scene_Item`: arriba la descripción del
ítem marcado y abajo la lista del inventario con cuántos hay de cada uno, en
orden de número como `Game_Party`. En gris va lo que A no usa, como
`Window_Item`. Hoy A usa **los ítems de switch**, que en la demo son uno solo,
la Portable Console: prende su switch —el 710—, gasta uno si tiene usos
—`uses` en cero es infinito—, pide el refresco de páginas y vuelve derecho al
mapa, que es el `PopUntil(Scene::Map)` de RM2k. B vuelve al menú. Las
medicinas quedan en gris: piden HP que cambien, y en los mapas de la demo la
única forma de perderlos es una pelea. El switch 710 dispara el evento común 39, "NewMenuActivated",
que es el menú propio del juego hecho con imágenes: 568 comandos, y los
eventos comunes todavía no corren.

**Las medicinas van en blanco y abren la elección de actor**, que es el panel
del grupo del menú con un cursor al costado —`render_objetivo`—. A no hace
nada, y eso **sí** es deuda: `UseItem` sólo gasta la medicina si sube algo, y
desde que hay peleas los HP bajan, así que usarla tendría algo que hacer.
Hasta el 2026-09-12 no la tenía, porque fuera de batalla nadie bajaba nunca de
los máximos y los tres comandos que tocan HP o estados compilaban a nada; hoy
`FullHeal` y el `ChangeHP` que suma son OP_HEAL y curan de verdad. Libros,
materiales y especiales siguen en gris.

**El texto va de a una letra por celda.** La pantalla tiene su propio banco de
tiles con cada carácter de la fuente en dos celdas, en blanco y en gris —307
tiles, que no dependen de cuántos ítems haya—, y los nombres y las descripciones
van en ASCII en el cartucho; escribir una letra son dos palabras del tilemap. Va
así y no con el texto de cada ítem ya dibujado, como las caras, porque eso crece
con el inventario y con una docena de ítems ya no entra en VRAM. El precio es
que las letras van a 8 pixeles y no a los 6 de la fuente, como las cifras del
oro. En RM2k la lista va en dos columnas de 144 pixeles; acá en una, con la
cantidad a la derecha, y la descripción en dos renglones de 30 letras. Es
cosmético y está declarado.

La descripción se compone en `texto_buf` —el búfer del compositor de
mensajes, libre con el menú abierto— y sube de un DMA al principio de cada
cuadro: escribirla letra por letra al mover el cursor no entraba en el vblank
y el segundo renglón salía cortado. Cuando el cursor se sale de las once
filas, la lista se repinta entera con la pantalla apagada, que es un cuadro
en negro.

Lo cobran `test_items` y `test_items_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py` —la pantalla como se entra, con el cursor
sobre la consola, y el mapa después de usarla— y
`pruebas/rpgmaker/test_items_pantalla.py`, que la compara contra `titulo.render_items`:
la consola prende el 710
y no se gasta, un ítem en gris no hace nada, catorce ítems en once filas se
corren y vuelven, y la lista vacía.

### El equipo, y las pantallas de texto

"Equipment" abre la elección de actor en modo elegir y después `Scene_Equip`
de ése: su nombre, los cuatro parámetros —los del nivel,
mockeado en 1, más lo que suma lo puesto—, y las cinco ranuras. A sobre una
ranura muestra la lista de lo que el actor puede ponerse ahí, con los
parámetros que quedarían; la línea vacía del final es sacarse lo que tiene. Lo
que se saca vuelve al inventario y lo nuevo sale de ahí; un arma a dos manos
saca el escudo y un escudo saca el arma a dos manos, que es
`Game_Actor::ChangeEquipment`. En RM2k la lista y las ranuras se ven a la vez;
acá la lista las reemplaza mientras se elige. Cosmético y declarado.

El equipo es estado: cinco palabras por actor del LDB en `FAR_EQUIPO`, que
arranca con el equipo inicial de la base —un DMA de la tabla del conversor en
el reset— y viaja en la partida. Son 610 bytes más, y con ellos la partida
pasó de los 1024 de la ranura: **la SRAM es de 32 KB** y
las ranuras van cada 2048. `ChangeEquipment` no compila todavía: el juego lo
usa en dos mapas que no están en la demo.

La pantalla de equipo —y la tienda, que sigue— son **pantallas de texto**: no
llevan bloques dibujados sino la fuente de la pantalla de ítems, y se componen
enteras en `texto_buf` —el tilemap de 32 por 28 celdas, 1792 bytes— que sube
de un DMA por cuadro. Componer no tiene apuro, y `pantallas.py` es la
referencia con el mismo compositor de celdas. El DMA va **después** de leer el
control: al revés, sus diez líneas hacían que `read_pad` llegara con la
lectura automática terminada, cada vuelta duraba dos cuadros y la mitad de los
toques se perdía. Lo cobró `equipo`.

Lo cobran `test_equipo` y `test_equipo_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py` —las ranuras de Kersh con su equipo inicial,
la lista del arma con los parámetros que quedarían, y el mapa después de
volver—
y `pruebas/rpgmaker/test_equipo.py`: el equipo inicial en la RAM, equipar desde el
menú, la lanza a dos manos que saca el escudo, la línea vacía, y el equipo en
la partida.

### La tienda

`OpenShop` abre `Scene_Shop`. Compila a `OP_SHOP` —el
tipo, el juego de mensajes y la lista de lo que vende, de largo variable como
`OP_CHOICE`— y, como guardar, la pantalla se abre adentro del intérprete y no
cuesta ningún tick: al salir el mapa vuelve y la página sigue. Es una pantalla
de texto, y cada modo es el de RM2k:

    principal       el saludo —o el resaludo al volver— y Buy, Sell, Leave
    comprar         lo que vende con su precio, en gris lo que no alcanza el
                    oro o ya se tiene 99; el oro, y cuántos se tienen y lleva
                    puestos el grupo del que marca el cursor
    cuántos         derecha e izquierda de a uno, arriba y abajo de a diez,
                    entre 1 y lo que se puede; el total
    listo           el "Done" o el "Thanks.", un segundo, y de vuelta
    vender          el inventario a mitad de precio, en gris lo que vale 0

Con una sola orden —sólo comprar o sólo vender— no hay principal. Los
mensajes salen de los tres juegos de términos del LDB, partidos en dos
renglones; las ramas de "compró" y "no compró" no compilan, y ninguna tienda
del juego las usa. El caso `tienda` de la tanda entra y sale de la del mapa
10, y `pruebas/rpgmaker/test_tienda.py` la recorre entera pixel por pixel contra
`pantallas.pantalla_tienda`: comprar, el tope del oro, vender, el oro y el
inventario que quedan.

### La batalla por turnos

`EnemyEncounter` abre una pelea. El alcance elegido fue la mecánica —turnos,
daño, HP, condición de victoria— antes que el dibujo, así que la pantalla es de
texto sobre negro, la misma grilla de 32 por 28 celdas del equipo y la tienda,
y el fondo con los battlers llegó después (ver más abajo).

Lo que sí es de RM2k son las palabras —todas del LDB— y **todas las cuentas**,
que salen de easyrpg-player y están escritas dos veces: en `main.s` y en
`tools/port/batalla.py`. Que las dos den lo mismo es lo que le permite a
`pruebas/rpgmaker/test_batalla.py` predecir **el número exacto** que cada HP va a tener
después de cada turno, en vez de conformarse con "bajó".

    daño            max(0, atk / 2 - def / 4), por 3 si es crítico, varianza
                    de 4 —`adj = max(1, 4 * dmg / 10)`— y la mitad al que se
                    defiende                        algo.cpp
    acierto         90 el actor, 70 u 90 el enemigo, ajustado por agilidad:
                    100 - (100 - hit) * (agiF + agiB) / (2 * agiF)
    orden de turnos agi + rand(0, agi / 4 + 3), de mayor a menor y estable
    huir            recortar(150 - redondear(100 * agiE / agiG), 0, 100), y
                    sube diez cada vez que falla

Tres tiros por golpe y **en este orden**: acierto, crítico y varianza, con el
del crítico hecho aunque la probabilidad sea cero, que es lo que hace
`Normal::vExecute`. Cambiar ese orden de un lado desfasa el azar del otro y no
se ve hasta que un golpe da distinto.

El azar es el xorshift de siempre —el de `ControlVars`— pero con **semilla
propia**: pelear no le corre el azar del mapa, que es lo que la referencia de
pixeles supone cuando dice que una batalla no cuesta ningún tick.

`OP_BATTLE` lleva la tropa y **los tres destinos**: victoria, huida y
derrota, absolutos dentro de la página y parcheados al cerrar el bloque, igual
que las opciones de un `ShowChoice`. El manejador que la página no tenga
apunta al final, que es lo que hace RM2k con un sub-índice sin rama. Como la
tienda y como guardar, la pantalla bloquea adentro del intérprete y `vueltas`
no avanza: los dos lados salen del opcode en el mismo tick tarde lo que tarde
el jugador.

#### La pelea sin manejadores, y el Game Over

Hay una forma de `EnemyEncounter` que no trae bloque de manejadores: RM2k no lo
emite cuando `defeat_mode` es 0, porque entonces perder no es una rama de la
página sino `Scene_Gameover`. Son **24 comandos en 15 páginas disparables** del
juego, tres de ellas el `EV0006` del mapa 26, o sea el jefe de los Rat Tracks.
Compilarlas fueron dos trabajos que sólo sirven juntos —el Game Over y el bloque
que sin `EndBattle` no cierra—: cualquiera de los dos solo destraba **+0**, y los
dos, **+15**.

El compilador mira adelante, como con las opciones de un `ShowChoice`: si
al `EnemyEncounter` no le sigue un manejador, emite el `OP_BATTLE` en el acto,
con victoria y huida en el comando de abajo y la derrota en `BATALLA_PERDER`.

**`BATALLA_PERDER` es $FFFF**, o sea un destino imposible —los tres son
absolutos adentro de la página y ninguna del juego llega a 64 KB—, así que el
Game Over no cuesta un opcode nuevo ni un byte más en las otras peleas. La ROM
lo mira en `op_battle` con un `iny`/`bne`, que es el `cmp #$FFFF` barato, y
responde con `jml reset`: **Game Over es volver al arranque**, o sea a la
pantalla de título si el cartucho la lleva, con la partida guardada esperando en
la SRAM. Es lo que `Scene_Gameover` hace al final, menos la imagen y menos el
tema; los dos están declarados en `assets/LIMITACIONES.md`.

Ese camino **la tanda de pixeles no lo puede ver**: una derrota reinicia la
consola, así que no hay cuadro que comparar contra una golden.
Lo cobra `pruebas/rpgmaker/test_game_over.py`, que pone el grupo entero en cero HP —con
nadie en pie `batalla_correr` contesta derrota sin abrir la pantalla— y exige
que la ROM se reinicie, con el control de la misma pelea apuntando a la página.

**Y el encuentro al azar pierde por el mismo camino.** Una pelea que arranca
del azar de los pasos no tiene bytecode detrás —la abre `pelea_arrancar` desde
`move_hero`— así que no hay destino que resolver ni manejadores que emitir:
perderla es siempre `Scene_Gameover`, y el llamador compara con `BA_DERROTA` y
hace el mismo `jml reset`. Sin eso la derrota devuelve el control al mapa y, como
`modo_fin` guarda los HP de la pelea en `FAR_HP`, el grupo queda en cero **para
siempre** y toda pelea siguiente se pierde sola antes de abrirse. Lo cobran dos
casos más de `test_game_over.py`, con el mapa 21 y `--encuentros-de-prueba`.

Y una aproximación declarada: las 24 peleas de esta forma traen `escape_mode` 0,
o sea huir prohibido, y la ROM deja huir igual porque el permiso no viaja en el
opcode. Huir sale por el mismo destino que ganar.

**El código de la pelea no vive en el banco 0.** Son unos tres kilobytes y ahí
quedaban trescientos bytes, así que vive en RODATA y se entra con `jsl`. De
allá no se puede volver con `jsr` —no cambia el banco de programa— así que las
rutinas del banco 0 que necesita se llaman por puentes de siete bytes que
además **reponen el banco de datos**: adentro de la pelea es $7E, para poder
usar direccionamiento absoluto sobre su estado, y en el banco 0 tiene que ser
el 0 o `eq_parametro` leería sus tablas de la WRAM.

**Los HP pasaron a ser estado.** Hasta ese día nadie bajaba de los máximos y
`ChangeHP` compilaba a nada; ahora viven en `FAR_HP`, arrancan llenos en el
reset como `Game_Actor::Setup` y **viajan en la partida**, detrás del equipo.

Lo que hay, y lo que no:

    atacar, con blanco elegible     sí
    defender                        sí, y vale sólo el turno en que le toca
    huir                            sí, pero es orden de cada actor y no del
                                    grupo, que es una simplificación declarada
    usar un ítem                    sí: ver abajo
    habilidades                     sí: ver abajo
    los estados                     no
    experiencia, oro, subir nivel   no: no hay niveles
    la música y los efectos         sí: ver abajo
    los battlers dibujados          sí, horneados en el fondo: ver abajo
    la imagen de fondo              sí
    las páginas de evento de tropa  no
    los encuentros aleatorios       sí: ver abajo

La pantalla muestra los HP de los enemigos, que RM2k no hace. Es a propósito:
lo que esta vuelta tiene que dejar ver es la mecánica, y sin eso un golpe que
pega y uno que falla se ven igual.

**De las 51 peleas del juego, la única que el jugador alcanza hoy es la del
droide del mapa 2.** La de los Lazer Teeth del mapa 9 —la tropa 86, cuatro
enemigos— no compila, y no por la batalla: la corta un `MoveEvent` con la
orden de ruta 9, "hacia el héroe", que la ROM no camina. Por eso la tropa de
cuatro la ejercita `test_batalla` con la página de prueba, que es el mismo
recurso que usan los casos de la pantalla de ranuras.

#### El menú: las cinco órdenes del ABL

Son las cinco del original, en los dos renglones del mensaje: tres arriba y dos
abajo, que mientras se elige está libre. Las palabras son las del LDB, y el ancho
es diez porque es lo que mide la orden más larga.

**El orden es el del original**: Attack, la habilidad, Defend, Use Item. Se ve
en `pruebas-manuales/capturas-batalla/auto_20260912_123013.png`, donde el menú
de Manta dice Attack / Slicing / Defend / Use Item. `Escape` no está allá —huir
es una orden del grupo, de un menú anterior— y acá va quinta, que es la
simplificación declarada.

**Y la segunda orden no dice "Tech Skill"**: dice el `skill_name` del actor que
está ordenando —"AgentTrain" con Kersh, "Telepathy" con Core, "Slicing" con
Manta, "Special" con Talan—, que es `Game_Actor::GetSkillName` con
`rename_skill` puesto. Su texto sale de `actor_hab_txt`, que es por número de
actor, y no de `ba_orden_txt`, que es fijo como el de las otras cuatro. La
columna en la que va tiene que dejarle **diez celdas libres**: "AgentTrain" y
"Tech Skill" miden diez justos y no le dejan lugar al cursor del que sigue, que
va una celda antes del texto.

**Las dos tablas son de dos bytes, y eso no es de adorno.** Un índice de texto
nombra un renglón del bloque que comparten las pantallas de ítems, equipo,
tienda y batalla, y ese bloque crece con el cartucho: con los 57 ítems de
`demo-ciudad` los textos de la batalla arrancan en el 273, que en un byte no
entra. El caso que lo cuida es `batalla-textos-lejos`, y `ca65` **rechaza** un
`.byte` que no entre en un byte en vez de truncarlo.

`Use Item` anda. Abre la lista de lo que se puede usar **donde va la de los
enemigos**, porque eligiendo qué usar lo que hace falta ver es el grupo; se
elige el ítem, después a quién, y con eso queda anotada la orden de ese actor,
que se ejecuta en su turno como cualquier otra. B vuelve un paso.

Qué entra en la lista y cuánto cura sale de easyrpg-player:

* **Qué entra**: `Game_Party::IsItemUsable` con la pelea abierta, o sea una
  medicina que no esté marcada "sólo fuera de batalla". De ésas, este port
  ofrece las que **recuperan HP y no son `ko_only`**: las de SP quedan afuera
  porque la lista todavía sólo sabe curar HP —los SP **sí** son estado, así que
  eso pasó de imposible a deuda—, y las de revivir porque revivir es sacar el
  estado de muerto y los estados no existen. Son 12 de las 22 medicinas del
  juego, de la Potion de 50 a la Miracle Drop, que cura todo.
* **Cuánto cura**: `Game_BattleAlgorithm::Item::vExecute`, o sea
  `recover_hp_rate * GetMaxHp() / 100 + recover_hp`, topado contra lo que le
  falta al blanco, que es el `ChangeHp`. La cuenta está escrita dos veces
  —`main.s` y `batalla.curacion`— como todo lo demás de la pelea, y por eso
  `test_batalla.py` puede exigir el número exacto. El producto entra en una
  palabra: el conversor corta si algún actor pasa de 655 HP.

Dos cosas que son de RM2k y conviene no "arreglar": **el ítem se gasta al
elegirlo** y no al usarlo —si no, el último de un ítem se podría repartir entre
dos actores en el mismo turno— y **el blanco muerto no se reapunta**, que es lo
contrario de lo que hace un ataque: el ítem se gasta igual.

Lo cobran cinco casos. Dos de la tanda —la lista de ítems y la elección del
blanco, pixel por pixel contra `pantallas.py`— y tres de estado: que la lista
sea la que corresponde (con un ítem inusable en el inventario, o no mediría
nada), que la poción deje el HP exacto que dice el modelo topando contra el
máximo, y que el menú recorra las cinco órdenes en el orden del original.
Todos verificados en rojo con su defecto puesto.

#### Las habilidades

Lo que las destraba no es la pantalla sino leer el `initial_level` del LDB en vez
de mockear el nivel en 1. Con los niveles de verdad —Kersh 20, Core y Manta 15—
los tres saben las suyas desde la primera pelea: siete entre los tres, 131 y 146
Kersh, 129 y 150 Core, y 130, 143, 144 y 150 Manta.

**Qué sabe cada uno**: `Game_Actor::LearnLevelSkills` recorre la tabla de
aprendizaje del actor y aprende las de nivel menor o igual al suyo, y
`LearnSkill` las mete en `data.skills` **ordenadas por número**. Ése es el orden
en que la lista las muestra, y la captura del original lo confirma: las cuatro
de Manta salen Mental Hack y MindShield arriba, MindProbe y MindBlast abajo, o
sea 130, 143, 144, 150 leídos **por filas** en dos columnas.

**Los SP son estado**, por lo mismo que los HP desde que hay batallas: cada
habilidad cuesta su `sp_cost` y `Skill::vStart` se lo descuenta al que la usa.
Viven en `FAR_SP`, arrancan llenos desde `actor_spmax` y viajan en la partida,
detrás de los HP.

**La pantalla** es la de la captura `auto_20260912_123023.png`: donde va la
lista de enemigos, la descripción de la que marca el cursor arriba de todo y
abajo dos columnas con el nombre a la izquierda y el costo en SP a la derecha,
con un guión delante. En gris la que no se alcanza a pagar, y la lista entera
en gris mientras se elige el blanco, que es lo que la de ítems ya hacía.

**Qué hace cada una**, de `Game_BattleAlgorithm::Skill::vExecute`:

* una de tipo `switch` prende su `switch_id` y **termina ahí**, sin tirar
  ningún dado. Tres de las siete son de ésas —MindShield, MindProbe y
  MindBlast— y en el juego original son las que abren rama de trama más
  adelante: acá prenden el switch y falta el evento que lo mire.
* las demás calculan `Algo::CalcSkillEffect`:
  `power + physical_rate * atk / 20 + magical_rate * spi / 40`, menos
  `physical_rate * def / 40 + magical_rate * spi / 80` del blanco cuando apunta
  a enemigos, y después la varianza con el `variance` de la habilidad.
* y lo aplican a lo que la habilidad marque: HP —Fury Punch y Healing Syringe—
  o **los modificadores de parámetro** del blanco —Agency Badge le baja ataque,
  defensa y agilidad; Mental Hack, defensa y espíritu—.

Los modificadores son lo único que pidió estado nuevo por combatiente, y no es
el modificador solo: `CanChangeAtkModifier` topa la bajada en la mitad del
parámetro **base**, así que hacen falta el base y el modificador por separado
—de la resta no se despeja un modificador que sobrevivió al recorte—. Por eso
`BA_BYTES` pasó de 18 a 40, con los cuatro bases, los cuatro modificadores y
los SP; el efectivo que las cuentas leen es `clamp(base + mod, 1, 999)`, que es
`AdjustParam` de game_battler.cpp.

**El orden en que consume azar es el contrato con `batalla.py`**, y sale de
leer `vExecute` de arriba abajo: el switch vuelve antes de cualquier tiro; el
crítico se tira **siempre**, aunque la chance sea cero —y para una habilidad
del LDB siempre lo es, porque `CalcCriticalHitChance` recibe
`easyrpg_critical_hit_chance`, que por defecto vale 0 y no -1—; después la
varianza; y después un tiro contra el acierto por cada cosa que la habilidad
afecta, en el orden HP, SP, ataque, defensa, espíritu, agilidad.

Lo que **no** está, declarado en `batalla.habilidad_usable`: los alcances de a
muchos —`enemies`, `party`, `self`—, que pedirían repetir el efecto sobre cada
blanco y con eso el orden del azar de los dos lados. En el grupo de la intro no
hay ninguna; en un cartucho con más actores cae `Gamble for Credits`, la única
de Arden, y Arden aparece sin habilidades. Tampoco hay animación de batalla al
usarlas: el `animation_id` viaja en el LDB y el port ya sabe dibujar
animaciones, pero nadie las conectó.

**Y los SP no se ven en la pantalla de la pelea.** Los renglones del grupo son
nombre, HP y máximo, y en las 32 celdas no entra además "SP nnn" sin achicar la
columna del nombre, que la comparten con los enemigos —"GangMember LT" mide
trece—. El original los muestra. Hoy lo único que avisa de que uno se quedó sin
SP es que la habilidad se pone en gris.

Lo cobran diez casos. Tres de la tanda —la lista, la lista con el cursor en
otra habilidad y la lista en gris mientras se elige a quién curar, pixel por
pixel contra `pantallas.py`— y siete de estado, que comparan contra
`batalla.Batalla.usar_habilidad` exigiendo el número exacto: los HP y los SP
turno por turno con Fury Punch, el switch que prende MindShield —y que el azar
**no** se haya movido—, la cura de Healing Syringe sobre un aliado lastimado,
los tres parámetros que Agency Badge le baja al droide, que la lista de cada
actor sea la que el LDB dice, que el menú recorra las cinco órdenes, y que un
actor sin ninguna —Talan, que es de nivel 1— no abra la lista.

#### El fondo y los monstruos: una sola imagen

El fondo y los battlers van juntos **porque son el mismo dibujo**: el conversor
compone el fondo de batalla con los battlers de la
tropa encima y el cartucho lleva el resultado como una capa de 8bpp de
256x128, los siete renglones de texto de arriba. La consola no dibuja
battlers: sube una imagen. El porqué largo, el presupuesto y lo que se pierde
están en `tools/port/escena.py`; el titular:

* **El fondo sale del propio `EnemyEncounter`**, que trae el nombre en su
  string: `SJBackdropABL04` para el droide del mapa 2 y `ABLBackdropSJ03` para
  los Lazer Teeth del 9.
* **Todo al 80%.** El fondo de RM2k mide 320x160 en una pantalla de 320x240 y
  acá la pantalla es de 256x224, así que entra escalado a 256x128. Los
  battlers van al mismo 80%, con lo cual las posiciones del LDB —que son las
  del centro de cada uno— se mapean multiplicando por lo mismo. Lo único que
  no es de RM2k es el recorte: un battler alto se topa adentro de la escena,
  porque allá abajo le quedan otros ochenta pixeles de pantalla y acá no.
* **512 tiles, 32.768 B de VRAM y 96 colores**, las entradas 32 a 127 de la
  CGRAM: las 0 a 31 son las dos paletas del texto y de 128 para arriba son las
  de los objetos. Los tiles no se deduplican —una foto no repite: 490 y 503 de
  512 en los dos fondos del juego— y por eso el número es fijo.
* **Entra sin pelearle a nada** porque la pelea se lleva por delante media VRAM
  del mapa y lo que se lleva se rehace al salir. El texto vive en $2000, su
  tilemap en $3C00, el de la escena en $3800 y los tiles de la escena en
  $4000, que son las últimas 16.384 palabras de la VRAM.

  **Rehacerla no es `volver_al_mapa`.** Aquél repone lo que pisan la tienda, el
  menú y las ranuras, que escriben nada más que `RANURA_VRAM` y `RANURA_MAP`
  —elegidos para caer adentro del banco de tiles de BG1 en los cuatro repartos,
  y el conversor lo comprueba—. Los 32 KB de la escena se salen de esa caja: se
  llevan además el tilemap del mapa ($5800), el de la capa de encima ($7800),
  los tiles de la ventana de mensaje ($6800) y el banco de sprites. Volver de
  una pelea es `volver_de_batalla`, que repone eso con `load_sprite`,
  `load_ventana` y `fill_window` antes de llamar al otro. Lo cobra
  `vuelta-ventana`; sin el arreglo, el 77% de los pixeles.

Dos cosas del PPU que no son obvias —el bit de prioridad del texto y el tile
512 con que se tapa lo que queda abajo— están anotadas arriba de `escena_subir`
en `main.s`, que es donde muerden.

**Lo que cuesta, declarado**: un enemigo muerto se sigue viendo. En RM2k
desaparece; acá lo que dice que murió es su renglón —el nombre en gris y los
HP en cero—, que es la misma razón por la que esta pantalla muestra los HP de
los enemigos y RM2k no. Y una escena es **por tropa** y no por fondo: dos
tropas con el mismo fondo llevan las dos escenas, a 32 KB cada una.

Lo cobra la tanda, con los dos fondos del juego: `batalla` con la tropa
86 —cuatro battlers iguales, uno de ellos topado contra el borde— y con la 82
—uno solo—, los dos en cero. Verificado que da rojo corriéndole a la ROM el
`BG1VOFS` un scanline.

Y hay un tercer caso que no mira el dibujo sino **el índice**: la misma tropa
86 en un cartucho que además lleva el mapa 2, o sea con dos tropas y dos
escenas. Es el único donde la pelea no es la tropa 0, y para que exista hubo
que mover una línea: la tropa de la página de prueba se pide **al final** y no
antes de compilar los mapas, igual que `temas_de_la_rom` agrega el tema del
mapa al final. Pidiéndola antes le tocaba siempre el índice 0 y `escena_de` y
`tropa_id` acertaban sin indexar nada. Verificado que da rojo —53% de los
pixeles— con `escena_subir` clavado en la escena 0.

#### Los encuentros al azar

**Los datos no están en el `.lmu`, están en el árbol.** `RPG_RT.lmt` guarda por
nodo —mapa o área— tres campos que este port no leía: `encounters`, la lista de
tropas; `encounter_steps`, cada cuántos pasos; y `area_rect`. Un **área** es un
nodo de tipo 2: no tiene `.lmu`, cuelga de un mapa y le tapa un rectángulo —no
es una carpeta del editor, que es lo que parece—.

Medido sobre el juego entero:

    23 áreas, colgando de 20 mapas
    33 mapas con tropas propias, ninguno de ellos con área
    53 mapas donde puede salir un encuentro, de 328
    5 de los 29 de `demo-ciudad`: el 20, el 21, el 26, el 28 y el 32
    129 tropas distintas

**Cómo se dispara**, de `Game_Player::UpdateEncounterSteps`. Cada paso del
héroe **con el pad** suma el `encounter_rate` del terreno a un acumulado; el
cociente entre el acumulado y `encounter_steps` elige una fila de una tabla de
ocho, y la fila da un multiplicador `pmod` que va de 1/16 a 16. La chance del
paso es `pmod / encounter_steps`, y la fila **no baja nunca** hasta que sale un
encuentro: por eso los primeros cincuenta pasos de un mapa casi no pasa nada y
después la cosa se acelera.

Los pasos de una **ruta forzada no cuentan**: allá `UpdateNextMovementAction`
vuelve antes de `IncSteps` si la ruta manda. Y todo teletransporte borra el
acumulado, porque `Game_Player::MoveTo` llama a `SetTotalEncounterRate(0)`.

Cuando sale, queda **pendiente** y se cobra en el cuadro siguiente, con el
héroe ya parado y sin página ni mensaje: ahí `PrepareEncounter` junta las
tropas del mapa más las de cada área que tape la celda y elige una al azar. Si
no lo tapa ninguna —el héroe está afuera del rectángulo— no pasa nada.

**Dos simplificaciones, las dos medidas y las dos cobradas por
`pruebas/herramientas/test_encuentros.py`:**

* **el terreno no cambia nada.** Los once tags que pisan los 53 mapas con
  encuentros tienen `encounter_rate` 100, así que el acumulado sube de a 100 y
  el factor `rate / 100` de la fórmula es 1. Leer el terreno celda por celda
  sería una capa más de datos por mapa para multiplicar siempre por uno;
* **ninguna tropa filtra por terreno.** Las 129 tienen el `terrain_set` vacío,
  y en RM2k vacío quiere decir "en todos".

Si alguna de las dos dejara de ser cierta, el modelo pasaría a ser mentira
**sin que ningún pixel se mueva**. Por eso lo cobra una prueba de datos y no la
tanda.

**Todas las cuentas son enteras**, que es lo que la consola puede hacer. El
conversor precalcula dos cosas por mapa: `1 / encounter_steps` en 1/65536
—`enc_base`— y en qué paso se cruza cada fila —`enc_umbral_n`—, que sale de
reescribir `acumulado / pasos >= fila` como `n >= ceil(fila * pasos / 100)`.
Con eso la consola no divide nunca: la chance es el corrimiento de una palabra
y la comparación contra un xorshift. `test_encuentros.py` comprueba las dos
reescrituras contra la cuenta de allá, para todos los `encounter_steps` del
juego.

**El azar es el de siempre pero con semilla propia** —`ENC_SEMILLA`—, como la
pelea con `BATALLA_SEMILLA`: caminar no le corre el azar al mapa, así que un
`ControlVars` al azar da lo mismo con encuentros y sin ellos, y
`eventos.Encuentros` sigue pudiendo predecir los dos. Se consume un número por
paso y uno más para elegir la tropa, y ése es el contrato con esa clase.

**Dónde vive cada cosa.** El estado son nueve bytes en la RAM lejana,
`FAR_ENCUENTRO` en `$7E3900`: en el banco 0 no entraban —la BSS está llena, y
medir cuánto falta es meterle un `.res N` y leer por cuánto se pasa, que `ld65`
lo dice—. Las tablas y las tres rutinas viven **fuera del banco 0**, en `FAR`, y
del lado de allá quedan nada más que cuatro `jsl` y el puente a la pelea, 43
bytes. Ni ésos entraban, así que bajó `item_switch` a RODATA —124 bytes, la
tabla más grande de las que se leen con X y no están en un lazo por cuadro—. Y
la pelea se arranca con `pelea_arrancar`, que es el cuerpo de `op_battle`
sacado a una rutina aparte: un encuentro al azar pelea **sin bytecode**, así
que no tiene cursor que guardar ni manejadores a los que saltar.

**Lo que cuesta, declarado:**

* **el fondo de batalla.** Un `EnemyEncounter` trae el nombre del suyo en el
  string del comando; un encuentro al azar no trae ninguno —en RM2k sale del
  terreno— así que se pelea sobre el color plano, como cualquier pelea sin
  fondo. Son 32 KB de cartucho por tropa los que se ahorran, y con 129 tropas
  eso no es un detalle.
* **perder no lleva a ninguna parte.** En RM2k un encuentro perdido es Game
  Over, y este port no tiene esa pantalla: la pelea vuelve al mapa. Es la misma
  deuda que ya tenía `EnemyEncounter` con `defeat_mode` 0.
* **el acumulado no viaja en la partida.** Al cargar arranca en cero, como al
  entrar a un mapa. En RM2k se guarda.
* **`ChangeEncounterSteps` sigue sin compilar.** Son 19 apariciones en nueve
  mapas —trece de ellas apagando los encuentros— y ninguno de esos mapas está
  cerca de los primeros diez minutos. Lo que lo frena no es la cuenta, que
  ahora está. Lo que lo frenaba era el cartucho de prueba del mapa 66, que se
  fue el 2026-09-17; ver el comentario de `ChangeEncounterSteps`, arriba de
  `ACEPTADOS_SIN_HACER` en eventos.py.

**Lo cobra `encuentro`**, el caso de la tanda: el mapa 21 —Rat Tracks B1—
caminando para arriba, con
`--encuentros-de-prueba 8` para que el encuentro salga en el paso 8 y no en el
130. Compara dos cuadros: el mapa un paso antes, y la pantalla de la pelea
contra `pantallas.py --batalla`, con la tropa que dice la referencia. Los dos
en cero. Verificado en rojo de tres maneras: con los encuentros apagados sólo
del lado de la ROM son el 100% de los pixeles; contra otra tropa de la misma
área, 338; y el cuadro de antes es el que no deja que salga antes de tiempo.

#### La música y los efectos de la pelea

Todo sale del LDB —`system.json`— y **quién suena en qué momento sale de
easyrpg-player**, no de memoria: está escrito con su función de
origen en `eventos.AUDIO_BATALLA`.

    battle_music      T_VGFighterMAX_Masako   `Scene_Battle`, al construirse
    battle_end_music  T_VGFighterMAX_Masako   `BGM_Victory`, al ganar
    dodge_se          Evasion1                `AlgorithmBase::GetFailureSe`
    enemy_attack_se   Attack2                 `Normal::GetStartSe`, fuente enemiga
    enemy_damaged_se  Damage1                 el mensaje del golpe, blanco enemigo
    actor_damaged_se  Bite                    ídem, blanco del grupo
    enemy_death_se    Monster1                `ProcessBattleActionDeath`
    escape_se         Escape                  cuando el grupo escapa

`battle_se` —el de empezar la pelea— está en `(OFF)` en este juego, así que no
se registra: sería una entrada muda para siempre.

Tres cosas que no son obvias:

* **El tema de batalla y el de victoria son el mismo**, y por eso ganar no
  cambia de tema sino que lo reinicia. Que sean dos constantes y no una es
  porque el dato es del juego: otro LDB podría tener dos.
* **Un golpe toca dos efectos y acá hay una sola voz.** RM2k pone el del
  ataque al empezar la acción y el del daño en el mensaje, con una espera en
  el medio. Acá el segundo queda pendiente en `BA_SE2` y sale veinticuatro
  cuadros más tarde; juntos serían uno solo, porque un efecto nuevo le pisa la
  voz al anterior. Cuando el que pega es del grupo no hay primero —RM2k no le
  pone efecto de ataque al actor— y el del daño sale en el acto.
* **La pelea tiene paquete de audio propio**, y eso está medido: el tema de
  batalla son 18 muestras y 51.480 B de los 64.512 de ARAM. Metiéndolo en el
  paquete del mapa 2, los 24 efectos de ese mapa —49.068 B, que hoy entran
  todos— se caían casi enteros. Con paquete aparte el mapa no paga nada
  mientras no se pelee: `op_battle` carga `BA_PAQUETE` al entrar y el del
  mapa al salir. Cuesta **65 cuadros medidos** de imagen congelada al volver,
  y otro tanto al entrar; es el mismo precio que paga cada cambio de mapa, con
  la diferencia de que allá lo tapa un fundido.

Lo que lo cobra es `pruebas/rpgmaker/test_batalla.py`, y **no la tanda de pixeles**: el
silencio no cambia un pixel, que es el mismo argumento de
`test_musica_paquete.py`. Son cuatro casos —el tema al entrar con sus muestras
en la ARAM, el de victoria, el del mapa al volver, y cuál de los cinco efectos
sale en cada golpe— y los cuatro están verificados en rojo con su defecto
puesto.

### La lluvia

`WeatherEffects` dibuja la lluvia —la apertura llueve, primero débil y después
media—. Compila a `OP_WEATHER` con el tipo y la
fuerza, y la regla es la de `Game_Screen::UpdateRain`: cada gota vive doce
cuadros, baja cuatro pixeles y corre uno a la izquierda por cuadro, y una
apagada nace con un diez por ciento de chance en un lugar al azar.

**La lluvia va pegada al mapa**, como en RM2k, y no a la pantalla. En RPG_RT las
gotas viven en
una superficie del tamaño de la pantalla que da la vuelta en los bordes, y se
pega corrida por el paneo, que es lo que la cámara se movió
(`Weather::DrawParticles`). Acá la superficie es de 256x256: la x y la y de
cada gota son bytes, el paso de cada cuadro da la vuelta solo, y para
dibujarlas se les resta el scroll del mapa —la sacudida incluida— en ocho
bits. De la superficie se ven 224 de las 256 líneas, así que en pantalla la
densidad es la de antes.

Cuatro cosas son nuestras y están declaradas:

* **La densidad, no la cantidad.** RM2k tiene 20, 60 y 100 gotas en 320x240;
  acá son 15, 45 y 75 en 256x224.
* **El azar es un xorshift propio**, sembrado cada vez que el clima cambia e
  igual de los dos lados: el de RM2k no se puede reproducir.
* **El diez por ciento es 26 de 256**, 10,2%: con `% 100` la ROM pagaba el
  divisor por cada gota apagada de cada cuadro.
* **La gota es una raya de 4x16** con la pendiente de la de 6x24 de RM2k, en
  tres grises opacos según le quede de vida, que es donde RM2k la desvanece
  con transparencia.

En la consola cada gota son dos objetos de 8x8 con prioridad 2, al final de la
OAM: pasan por delante de la capa de encima, cualquier personaje las tapa —en la
consola gana el objeto de índice más bajo—, y la ventana de mensaje las tapa con
la misma máscara que a los eventos "above". El tono de pantalla las tiñe, como a
todo, porque sus colores van en una paleta de personaje. Sus seis tiles y sus
tres colores se reservan como los dígitos del cronómetro, y **un mapa sin lugar
en las paletas de sprite no dibuja lluvia**: la ROM lleva `M_LLUVIA_BASE` en
cero, y quién lo decide es el conversor al repartir las paletas de sprite, en
`gotas_de_lluvia`. En la demo pasa en
los mapas 2, 8 y 10, que no la usan. La nieve, la niebla y la arena no se
dibujan y apagan la lluvia; el clima no viaja en la partida.

En OAM las gotas no pasan por `emit_object`: la X queda siempre entre 0 y
255, así que `lluvia_oam` las escribe directo, y de la Y descarta lo que cae
entre 224 y 247 —de 248 en adelante el PPU lo dibuja asomando por arriba—.
Con eso y el direccionamiento largo en vez de la ventana de WMADD, la lluvia
fuerte bajó de 58 a 24 líneas en `lluvia_tick` y `build_oam` de 130 a 84.

Lo cobran `pan-lluvia` y `sacudir-lluvia` en la tanda, que corren la cámara con
lluvia fuerte por la página de prueba —un `WeatherEffects` en su archivo de
`pruebas/casos/`—: en la apertura la cámara no se mueve, así que ella sola no
mira el scroll de las gotas. Y
`apertura` compara con lluvia, que es lo que exige que el caso cuente los ticks
hasta el final: la lluvia no se aquieta nunca, así que cortar cuando la escena
se ve quieta deja las gotas de veintipico de ticks antes.

### Los efectos de sonido

`PlaySound` suena. Compila a `OP_SOUND` con el índice del
efecto en `sonido_tabla`, que lleva por efecto la muestra, la altura, el
volumen de cada lado y cuántos cuadros dura: el tempo de RM2k estira la altura
y la duración, y el paneo baja el lado contrario.

Tres decisiones, las tres por la ARAM:

* **Van por mapa**: ver "El paquete de audio de cada mapa", más abajo. Hasta
  ahí se quedaban con lo que la música dejaba libre, y de los 38 que pide la
  demo entraban 5.
* **A 6 kHz y a lo sumo tres cuartos de segundo** —era uno hasta el paquete,
  que tiene que subirlos en el fundido de cada salto—. Uno más largo repite sus
  últimos 0,4 s hasta durar lo que dura en RM2k: la lluvia de la apertura son
  cinco segundos de ruido y así se la oye entera.
* **El efecto le roba la voz 7 a la música**, que es de percusión. La ROM
  guarda una sombra de los registros de esa voz que la música escribe
  (`dsp_musica`), y al terminar el efecto la devuelve tal cual; mientras suena,
  la música no la toca.

La tanda no mide audio: compara imágenes, y `OP_SOUND` no cuesta un tick. Lo
que se corrió fue una grabación de la apertura de
`demo-ciudad` con el núcleo de libretro, contra la misma ROM con el volumen de
los efectos en cero: los disparos caen en los cuadros 191, 433 y 576, y en el
hueco entre el fin del tercero y el siguiente (cuadros 890 a 920) las dos
salidas son idénticas muestra por muestra. Es decir, la música vuelve entera.
Si suenan bien lo dice el oído de taro.

`play_sound_effect` en las rutas sigue aceptándose sin hacerse.

### El paquete de audio de cada mapa

La ARAM son 64 KB, y los instrumentos de los ocho temas de la demo son 53: los
efectos que piden el Linkage Block y el Emitter Room —43 y 55 KB— no entran ni
cerca. Por eso hay **un paquete por mapa**: al cargar uno se suben **los temas
que sus páginas pueden prender y los efectos que piden**, en el orden en que
aparecen, que es la prioridad si no entran todos. Cada tema
por separado son de 8 a 32 KB, así que en el Emitter Room entran sus dos temas,
los catorce efectos y el tema del mapa anterior, que sigue sonando.

Cómo está hecho:

* **Las muestras tienen número fijo en todo el cartucho**: las de la música y,
  detrás, las de los efectos. Es el SRCN que el stream de la música ya
  escribía, así que ni un byte del stream cambió. El directorio del SPC700
  tiene una entrada por muestra y **las que no están apuntan al silencio**, un
  bloque BRR de nueve bytes.
* **Qué muestras usa un tema** lo dice su stream: los valores que escribe en
  los registros SRCN (`muestras_del_stream`). El conversor emite esa lista por
  tema, y por mapa sus temas y las muestras de sus efectos (`paquetes`).
* **Las del tema que está sonando no se mueven**: la música sigue durante el
  fundido, y pisarle una muestra que está tocando sería ruido. Las que el
  paquete nuevo también quiere se quedan donde están, y las demás se sueltan.
  Lo que falta se acomoda en el primer hueco donde entre, recorriendo la lista
  de lo ocupado en orden (`paquete_cargar`, `colocar_muestra`).
* **El driver del SPC700 aprendió a escribir la ARAM**: tres comandos más en
  el puerto 2 —un byte, el puntero y un bloque de ternas— al lado del par del
  DSP de siempre. La música sigue mandando pares con el puerto 2 en cero, y la
  subida va en tandas de 85 ternas con las interrupciones cortadas, así que
  la música se atrasa un poco y no se pierde. Son unos 55 KB por segundo.
* **Un `PlayBGM` de un tema que el mapa no traía** —el del título, o uno de un
  evento común— calla la música, suelta todo y rearma el paquete con ese tema
  adelante: congela la imagen lo que tarde. Un efecto que no entró no suena.

Lo que cuesta: el fundido de un salto dura lo que tarda la subida. Del mapa 1
al Emitter Room son 58 cuadros perdidos, de los que unos 14 son la carga del
mapa de siempre: unas siete décimas de segundo de negro más.

Cómo se verifica, porque la tanda no mide audio: la ARAM se lee del estado
guardado del core —`retro_serialize`, ubicando el driver— y cada muestra que la
ROM dice tener se compara con la del cartucho byte por byte, con su entrada del
directorio. Y `pruebas/rpgmaker/test_musica_paquete.py` lo cobra solo: para el tema que la
ROM dice estar tocando, que cada muestra de su `tema_muestras` tenga entrada en
`FAR_ARAM_DE`. Hace falta una prueba de estado porque **el silencio no cambia un
pixel**, y el tema de la pantalla de título es el más expuesto: es el único que
ningún paquete trae —sale de `title_music` del LDB y los paquetes se arman con
los `PlayBGM` de cada mapa— así que depende por entero de ese camino.

### El MSU-1

La música sintetizada suena fea, y la causa está medida: los ocho temas de la
demo comparten 53 KB de ARAM, así que cada instrumento es una muestra corta y
recortada. El **MSU-1** es la salida: no es hardware de la
consola sino una extensión que soportan el FX Pak Pro y los emuladores, con la
música en archivos PCM al lado de la ROM. El tema sale de un archivo de 44,1
kHz estéreo en vez de las ocho voces del SPC700.

Lo usan **los 21 temas que suenan hasta salir de Lashe City**, más el del
título: `PISTAS_MSU` en `snes_music.py` dice cuáles tienen pista y con qué
número, y el conversor emite `tema_msu`, un byte por tema —`$FF` el que no
tiene—. Los del juego entero son 43, noventa y un minutos, 923 MB de PCM;
entran el día que haya una ROM que los toque. Que los lleven todos importa
porque un tema sin pista suena por el SPC700 y ahí puede faltarle del 28% al 88%
de las notas: ver "Varios temas en el cartucho". **Los números del 1 al 8 no se
mueven nunca**: son los que ya están en la tarjeta, y renumerarlos obligaría a
renombrar archivos.

Dos de los temas **no son de ningún mapa** y por eso se escapan de cualquier
barrido de `PlayBGM`: salen del LDB. `title_music` es el de la pantalla de
título y `battle_music` el de **todas** las peleas —`T_VGFighterMAX_Masako`—.

Cuestan 10,6 MB por minuto, o sea unos **423 MB por cartucho** para los 21. Y
no hay atajo por el loop: de los 21 el único que repite exacto a la mitad es
`C3classi`, medido nota por nota sobre las dos mitades del MIDI, y son 8,6 MB
de 423.

Cómo funciona, del lado de la ROM:

* **La firma se mira una vez, en el reset** (`msu_detectar`): "S-MSU1" en
  `$2002..$2007`. Si no está —o sea, siempre que no haya MSU-1— `MSU_HAY` queda
  en cero y **nada más del sistema se enciende**: la música sigue saliendo del
  SPC700 como antes de todo esto. Esa es la propiedad que importa, porque la
  ROM tiene que andar igual en una consola sin tarjeta preparada.
* **`PlayBGM` prueba primero con la pista** (`msu_arrancar`): espera a que el
  MSU-1 esté libre, escribe el número, espera a que termine de cargarla, y si
  el MSU-1 dice que la pista no está en la tarjeta se vuelve sin hacer nada y
  suena el SPC700. Con pista, en cambio, el SPC700 **se calla**:
  `music_apagada` y un `KOF` de las ocho voces. Los efectos de sonido siguen en
  el SPC700, así que la ARAM les queda libre.
* **La espera de `AUDIO_BUSY` es un camino que ningún emulador ejecuta**, y
  conviene saberlo antes de tocarlo. bsnes no pone `io.audioBusy` nunca —nace
  en falso en `power()` y no se escribe en ningún lado:
  `bsnes/sfc/coprocessor/msu1/msu1.cpp`—, así que en toda la tanda y en todas
  las pruebas de estado el lazo sale en la primera vuelta. En el FX Pak la
  pista sale de la tarjeta SD y abrirla lleva tiempo de verdad. En el mismo
  archivo está el porqué de esperar **antes** de escribir y no sólo después:
  `case 0x2007: if(io.audioBusy) break;`, o sea que con `AUDIO_BUSY` puesto el
  hardware **ignora** las escrituras a los registros de audio, y un `PlayBGM`
  que llega mientras la pista anterior todavía se abre se pierde entero. Con
  pantalla de título eso pasa: se piden dos pistas con 1,8 s de diferencia.
  El tope de la espera son `$FFFF` vueltas, unas tres décimas de segundo, y
  quedarse corto no cuesta un cuadro sino el tema entero.
* **El `FadeOutBGM` baja el volumen del MSU-1**, no el del DSP: el nivel del
  fundido ya va de 255 a 0, que es justo la escala de `$2006`, y al llegar a
  cero se corta la pista. El volumen del DSP no se toca **porque es el que
  oyen los efectos de sonido**: bajarlo en el fundido los dejaba mudos hasta
  el `PlayBGM` siguiente, que es el único que lo repone. Y el comando tiene
  que dejarse arrancar con `music_apagada` puesto, que con pista vale 1: sin
  eso un `FadeOutBGM` no hacía nada y la pista seguía para siempre.
* **El DSP hay que ponerlo a punto igual**, aunque no lo use la música. Lo
  hacía el comienzo del stream —sacarlo del mute con que arranca el SPC700, el
  volumen general, y dónde está el directorio de muestras— y con pista el
  stream no corre nunca. Sin eso los efectos de sonido se disparan contra un
  DSP mudo, y el síntoma es música por MSU-1 y **ningún efecto**.
  El prólogo sale de `dsp_init_reg`/`dsp_init_val`, que el conversor emite de
  `init_writes`, o sea de la misma lista que ya escribía el stream; copiarla a
  mano en el 65816 serían dos lados que se pueden equivocar igual. KON y KOF
  quedan afuera: con pista, KOF se deja en `$FF` para que las voces de la
  música no suenen, y `se_despues` lo limpia solo al arrancar un efecto.

* **La pista no suena a fondo, y eso no es cautela: es aritmética.** El MSU-1
  se **suma** a la salida del SPC700 en vez de mezclarse con ella, así que una
  música que llega al techo no deja lugar para un efecto de sonido. Con el
  volumen en `$FF`, en la apertura, 42 muestras llegaban al tope —las 42 en
  cuadros con un efecto sonando— mientras que la misma corrida por el SPC700 no
  clavetea ni una vez; y la música por pista picaba 28933 contra 23867, o sea
  1,21 veces más alta, que es lo mismo escuchado al revés: "los efectos se oyen
  mucho más bajos". `MSU_VOLUMEN_MAX` es `$D8` —ese 0,85— y con eso el clipping
  se va a cero y la música queda en 24508, al lado de los 23867 del SPC700. Va
  en el registro y no en las pistas: normalizarlas más abajo sería rehacer todos
  los PCM del cartucho, y perdería la referencia de nivel entre un tema y otro.
  El fundido escala contra ese techo y no contra 255, o su primer cuadro
  **subiría** la música antes de bajarla.

Y del lado del cartucho, `tools/audio/msu.py` (receta `msu`): renderiza el MIDI
con fluidsynth y **con el mismo soundfont con el que el juego sonaba en la PC**
—el que ya usa `snes_samples.py` para sacar las muestras—, así que no cambia el
arreglo: cambia que no haya que reducirlo a ocho voces. La pista es "MSU1", el
punto de loop en muestras, y el audio crudo.

Una cosa más del lado del cartucho: **la pista se normaliza a 0,97 de la
escala**. fluidsynth se corre bajo, en 0,6, porque con 1,0 los temas de muchas
voces saturan, y sin normalizar después la pista sale a un cuarto del volumen de
la música del SPC700 —pico 4632 contra 17012— y el cambio de un tema al otro da
un salto.

Cómo se verifica, porque la tanda no escucha: primero el protocolo solo, con
una ROM mínima aparte que pide la pista y deja los registros en la RAM —la
firma, el estado antes y después, y cuántas vueltas tardó en cargar—. Y después
la ROM de verdad, corriendo 1800 cuadros con el núcleo de libretro y grabando
la salida:

* **el nivel**: picos de 17096 a 20118 en las ventanas de 300 cuadros, contra
  los 17012 de la música del SPC700;
* **que suene esa pista y no otra cosa**: la envolvente de energía del audio
  grabado contra la del WAV renderizado da una correlación de **0,927 con cero
  desfase**;
* **el fundido**: pinchando el pedido de `FadeOutBGM`, la pista se corta a los
  84 cuadros y el pico baja 19059 → 3464 → 0.

**Y para los efectos de sonido hay que aislarlos, porque la música los tapa.**
La forma que sirve es la misma ROM con los dos bytes de volumen de cada fila de
`sonido_tabla` puestos en cero, y comparar las dos salidas muestra por muestra:
lo que difiere **son** los efectos. Así se comprobó que el prólogo del DSP es lo
que los hace sonar con pista: con el prólogo puesto difieren 714382 muestras de
1027098 desde el cuadro 212, y con un `$FF` en el primer byte de `dsp_init_reg`
—que lo deshabilita— difieren **cero**.

Y la tanda entera sigue en verde **sin** los archivos de MSU-1, que es el
camino que recorre cualquier prueba de acá.

Lo que falta: el punto de loop. El MSU-1 vuelve al principio del archivo, así
que un tema con introducción la repite cada vuelta; hoy loopean enteros. Y los
temas que las demos no tocan.

### Las animaciones de batalla: el sonido y la luz

`ShowBattleAnimation` son dos mitades, y ésta es la del **sonido y la luz**: sus
efectos y sus destellos, en el cuadro en que RM2k los pone. El dibujo está en la
sección que sigue. Son once en la intro —tres en el Linkage Block, ocho en el
Emitter Room, todas de fuego— y sin ellas esas escenas son silencio y nada.

Compila a `OP_ANIMATION` con la línea de tiempo adentro: por cada `timing` de
la animación, en el cuadro par `2 * (frame - 1)`, su efecto y su destello, de
la pantalla o del evento objetivo. Hay una sola a la vez, como en
`Game_Screen::ShowBattleAnimation`, y avanza una vez por cuadro antes que los
destellos (`animacion_tick`). Con "esperar", la
página espera lo que dura. Tres cosas son nuestras:

* **El destello es un `FlashScreen` o un `FlashSprite`** que arranca en la
  fuerza que RM2k le da al primer cuadro y baja lineal en diez; allá baja a
  escalones. Diez, y par a propósito: el destello de pantalla trabaja en dos
  fases según la paridad de lo que le queda, y con once arrancaba por la que
  ninguna página del juego toma, que es la que quedó sin probar.
* **Al héroe no se lo destella.** Con quién comparte paleta depende del grupo,
  que el compilador no ve; para los `FlashSprite` el conversor lo mira y corta
  la ROM entera, y una animación no vale eso. Tampoco a un evento que comparta
  gráfico con otro, y eso **quedó conservador** desde que el destello pasó a ser
  por fila de paleta (ver abajo): hoy el del objetivo se podría emitir igual. No
  se hizo en la misma vuelta porque cambia qué se dibuja en los mapas donde dos
  eventos comparten gráfico, y eso pide medir la tanda de nuevo.
* **El dibujo no está.** Son celdas de 96x96 con zoom de hasta el doble y su
  propia paleta; es el sistema de al lado, y está abajo.

Lo cobra `animacion` en la tanda —la 82 sobre el héroe, que destella la
pantalla—, por la página de prueba de `pruebas/casos/animacion.json`: la escena
del Emitter Room no se puede disparar desde una prueba. Los efectos los cobra
el paquete de audio de cada mapa, que los cuenta como uno más.

### El dibujo de las animaciones de batalla

También se dibujan. El sistema entero está en
`tools/port/animacion.py`, que es el único lugar donde se decide dónde cae y de qué
color es cada pixel; la ROM no decide nada de eso.

**Una caja de 64x64, la misma para toda la ROM.** Son cuatro objetos de 32x32
en 64 tiles, que es una fila de bloques de la grilla de nombres de OAM: un
objeto de 32x32 lee cuatro tiles de cuatro filas seguidas, así que en una fila
entran cuatro objetos y ni uno más. Más que eso tampoco había: la VRAM de
sprites que le queda libre al mapa 2 son 101 tiles y una caja de 96x96 son 144.
Que la caja **no dependa del mapa** es lo que deja que los 388
`ShowBattleAnimation` de los 81 mapas del juego compartan los mismos cuadros ya
convertidos en el cartucho.

**La animación se achica entera hasta entrar**, con su proporción, y cuánto se
achicó lo emite el conversor animación por animación. Las de la intro:

| animación | de       | a     | cuadros | en el cartucho |
|-----------|----------|-------|---------|----------------|
| 77        | 192x192  | 64x64 | 20      | 40 KB          |
| 78        | 144x176  | 52x64 | 24      | 48 KB          |
| 79        | 512x384  | 64x48 | 28      | 56 KB          |
| 82        | 536x416  | 64x49 | 28      | 56 KB          |

Achicarlas es lo que hace que las grandes existan: al 11% la 82 es un brillo y
no un incendio, pero está, y la alternativa medida era que no estuviera.

**Los cuadros van prerenderizados en el cartucho y se suben por DMA.** Uno cada
dos cuadros de consola, que es lo que dura un cuadro de RM2k: 2 KB, o sea
cuatro de las cinco poses del presupuesto del vblank, y se le **descuentan** a
`vq_tope` en vez de fijarlo, igual que un paso de la animación del ChipSet. Van
uno por cuadro y no un bloque seguido por animación porque 28 cuadros son 57 KB
y un banco tiene 32.

**Una paleta de sprite entera para ella sola**, como el cartel: sus quince
colores son de la animación y se pisan cuando empieza otra, así que un
personaje metido ahí cambiaría de color con ella. Los mapas 2 y 3 llenaban las
ocho, así que en los mapas que muestran animaciones **los personajes se
reparten siete**; lo que eso fusiona está en `assets/LIMITACIONES.md`. Si con
siete no entra el cronómetro manda el cronómetro, se vuelve a ocho y ese mapa
no dibuja: le pasa al mapa 9, y lo dice.

**Dónde cae.** Con alcance "pantalla" va al centro de la de la consola, que es
`DrawAt(screen_width / 2, screen_height / 2)`; con el otro, sobre el objetivo,
que es `GetScreenX()` y `GetScreenY(false)` menos medio personaje y la corrida
de `Animation::Position`. Esa corrida va **horneada en el ancla** que lleva la
tabla, así que la consola sólo resta. Un objetivo sin fila de NPC, o escondido,
no tiene de dónde sacar la posición y la animación no se dibuja.

Lo que se pierde está en `assets/LIMITACIONES.md`: la transparencia de una
celda, el destello sobre la animación y las `global`.

En la tanda lo cobran `animacion-dibujo` —la 78 sobre el héroe, con uno de sus
cuadros vacíos y los tres más cargados— y `animacion-evento` —la misma sobre
Manta, pegada al borde izquierdo, donde `emit_object` recorta la caja—. Son dos
casos y no uno porque en la ROM son dos caminos: el héroe sale de `hero_x` y un
evento de su fila, por `npc_de_evento`.

### El cartel de "One year previously"

Es lo único que este port dibuja de `ShowPicture`, y el alcance está elegido a
propósito: **un cartel por ROM**. El de la intro aparece una sola vez, entre un
fundido y otro, sobre el mapa 4 —"Blank (Leave START here)", un mapa de un solo
tile— así que no le pelea nada a nadie, y eso lo hace el caso barato del sistema
de imágenes. Lo demás se sigue aceptando sin hacerse; cuánto cuesta el sistema
entero está más abajo.

**Va en objetos de OAM y no en una capa.** En modo 3 las dos capas son del mapa,
y prestarle una al cartel obliga a recargar el mapa al borrarlo: 30 KB de DMA y
dos cuadros negros, que es lo que cuesta `volver_al_mapa`. Con objetos se pone y
se saca sin tocar lo que hay debajo, que además es lo que hace RM2k —la imagen
se compone encima—. Se pagan dos cosas:

* **Quince colores**, los de una paleta de sprite, contra los 226 del PNG. Los
  elige `titulo.reducir`, el mismo de la pantalla de título y por lo mismo: no
  promedia, así que no inventa colores que haya que volver a cuantizar, y no
  depende de la versión de PIL. El degradé del resplandor rojo se escalona, se
  ve, y está declarado.
* **Veinticuatro de los treinta y cuatro tiles por línea** en las veintinueve
  líneas que ocupa: son seis objetos de 32x32 en fila. Ahí entran dos
  personajes más y no más. Cuál sprite descarta el PPU en esas líneas es
  justamente lo que ninguna referencia en Python podía modelar y una captura del
  emulador sí: es la razón por la que las goldens son capturas y no un render.

**La paleta es suya y no la comparte con nadie.** No es por falta de lugar: el
fundido es un tinte de esas quince entradas cuadro a cuadro, así que un
personaje metido ahí se apagaría y se prendería con el cartel. Y va **arriba de
`SPRITE_CGRAM`**, o sea afuera de los rangos que recorren `aplicar_tinte` y
`subir_paletas`: en RM2k las imágenes tienen `affected_by_tint` apagado de
fábrica —`Priority_PictureOld` es 120 contra los 90 de `Priority_Screen`— así
que el tinte de pantalla no las toca, y quedando fuera del rango no hay que
acordarse de saltearlas.

**El fundido es de tono, no de transparencia**, y eso hubo que ir a leerlo:
los dos `MovePicture` de la página dejan `top_trans` en cero y mueven
(r, g, b) entre 0 y 100 con la saturación quieta. La imagen aparece **negra**,
sube a su color y vuelve a negro. En la consola eso es exactamente la cuenta
que el tinte de pantalla ya hacía, `tabla_canal` más `armar_paleta`, sobre
dieciséis entradas en vez de doscientas.

Y **la duración viene en décimas**: `data.time_left = duration * DEFAULT_FPS /
10`. Los 35 del primer `MovePicture` son tres segundos y medio, no medio
segundo, y los 20 del segundo son dos. Hasta que esto se dibujó, esas 55
décimas no costaban nada —el comando se aceptaba sin hacerse y sin su espera—,
así que la página del "1 year earlier" pasó de 105 décimas a 160.

**La posición de RM2k es el centro de la imagen**, no su esquina
—`Sprite_Picture` hace `SetOx(width / 2)`—, y la pantalla de RM2k mide 320x240
contra las 256x224 de la consola. Las dos esquinas del rectángulo pasan por la
misma cuenta y la imagen se lleva al tamaño que queda; escalar el tamaño por su
lado daba 28 de alto donde las esquinas dan 29, y un pixel de diferencia entre
las dos puntas es una comparación que falla. El cartel del "One year
previously" queda entonces en (-13, 149) y mide 186x29: **se sale por la
izquierda**, y eso no es un error nuestro, es lo que el juego muestra.

**Los tiles son de un solo mapa.** Se ponen al final de su banco de sprites,
redondeando a una fila de bloques como los dígitos del cronómetro y las gotas
de lluvia, y por lo mismo: un objeto de 32x32 lee cuatro tiles de cuatro filas
seguidas de la grilla de dieciséis, así que en una fila de bloques entran cuatro
objetos y el quinto arranca 64 tiles más adelante. Seis objetos son dos filas,
128 tiles reservados de los cuales 96 se usan. Que el cartel viva en un mapa y
que se borre al cambiar de mapa son la misma cosa: sin sus tiles en VRAM no
habría qué dibujar, y `erase_on_map_change` viene prendido de fábrica en
`Game_Pictures`.

**Cuál cartel se queda con la ranura lo decide `Imagenes.elegir`**, mirando
todos los mapas del cartucho en el orden de la tabla y **antes de compilar una
sola página**. Con "el primero que pase" bastaba que dos carteles compitieran
para que la elección dependiera del orden en que se compilan los mapas, que a su
vez depende de si la ROM lleva ventana, y eso no se ve como un cartel equivocado
sino como dos streams de bytecode distintos.

**Y el estado vive en la RAM lejana**, quince bytes en `$7E30E8`, al lado del
de la animación de batalla. No es elegante: es que en el banco 0 no entraba
—la BSS estaba en 7680 de 7680— y esto se lee y se escribe unas pocas veces por
cuadro, así que el direccionamiento largo no se nota.

Lo cobra el caso `cartel` de `pruebas/abl/test_tanda_escenas.py`: cinco cuadros
contra su golden, **los cinco en cero**. El de la mitad de cada rampa no es
adorno: es el único que ejercita la interpolación cuadro a cuadro, que es donde
un valor de más o de menos no se vería a ojo.

#### Lo que costaría el sistema de imágenes entero

Medido sobre los 328 mapas del juego, no estimado:

    ShowPicture en el juego                    34, en 23 páginas
    carteles distintos                         20
    páginas que muestran 2, 3 y 4 a la vez     2, 3 y 1
    comandos que el modelo de hoy sabe hacer    7 de 34
    con la pantalla ya teñida a negro          10 de 34

Y lo que cada uno pediría, contado por comando —un mismo comando puede pedir
varias—:

    el color transparente del PNG              21
    pegada al mapa (fixed_to_map)               9
    translúcida (top_trans)                     8
    zoom distinto de 100                        7
    rotar u ondear                              6
    saturación distinta de 100                  5
    la posición desde una variable              2

Lo que esa tabla dice es que **la parte cara no son los carteles**. De los 20
distintos, seis son carteles de texto que entran en un objeto de alto
—`Oneyearprev`, `MeanwhileLashe`, `SevDaysPrev`, `Ready`, `Fortitude` y el
`9` de 16x16— y los otros catorce son ilustraciones grandes, cinco de ellas de
**320x240 exactos**, o sea la pantalla entera.

Una de 320x240 **no se puede hacer con objetos**: escalada son 256x224, que son
8x7 objetos de 32x32 —56 de los 128 de OAM, 896 tiles de 8x8, 28 KB de un banco
de sprites que mide 8 o 16— y en cada una de sus 224 líneas gasta 32 de los 34
tiles por línea, o sea que se lleva puestos a todos los personajes del mapa.
Para ésas hay que prestarle una capa al cartel, con lo que eso implica: el mapa
se recarga al borrarlo. Es exactamente el caso que la nota de `eventos.py` ya
anticipaba, y por eso el atajo de las cinemáticas —teñir a negro antes— vale
para diez de los 34 y no para los otros veinticuatro.

Si algún día se hace completo, el orden que sale de estos números es: primero
**el color transparente** (21 comandos, y es un color menos en la paleta),
después **más de un cartel a la vez** (seis páginas), después **la capa
prestada** para las ilustraciones, y al final el zoom, la rotación y la onda,
que son cinco o seis comandos cada uno y cada uno un sistema.

### Varios mapas en la ROM

Un mapa solo no es un juego. Todo lo que antes era una constante del `.inc` —el
tamaño, las bases de VRAM, dónde arranca el héroe, los punteros a cada tabla—
pasó a ser un campo del registro del mapa en `mapa_tabla`, y la ROM carga el que
le digan con `cargar_mapa`.

Los desplazamientos de cada campo los emite el conversor. La ROM sólo los
nombra, así que agregar un campo no deja ningún número que actualizar de este
lado.

**Las tablas del mapa ya no entran en el banco 0.** La de bloques llega a 8 KB
—512 bloques por 16 bytes— y con varios mapas no hay dónde ponerlas. Se leen
desde donde estén con un puntero de 24 bits, o sea `lda [ptr],y`.

La de NPCs es la excepción y se copia a la RAM: `build_oam` la recorre con un
índice y en cinco desplazamientos distintos, así que con un puntero saldría el
triple de instrucciones en el lazo que se ejecuta 128 veces por cuadro. Copiarla
cuesta un lazo por carga de mapa y entran 127, que es el tope que impone OAM; el
mapa con más NPCs del juego tiene 89.

Y en el mapa donde el juego arranca la posición del héroe sale del LCF y no de
la heurística del "tile abierto más cercano al centro": `Map0004`, que es donde
el juego empieza, es una habitación vacía sin una sola celda abierta por los
cuatro lados. A los demás se llega por teletransporte, y ahí sigue mandando la
heurística. La regla vive en `inicio_del_mapa()`, en el conversor, y es el
único lugar donde está escrita: mientras existió la referencia en Python los dos
la llamaban, porque si cada uno eligiera por su cuenta la comparación habría
estado midiendo dos cosas distintas.

#### Las tres piezas del intérprete de eventos

Cada página de evento que se puede compilar viaja en el cartucho como
**bytecode**, y ese bytecode tiene tres dueños que no se pisan:

    tools/protocol/events.toml  lo declara: cada opcode, su número y los bytes que lleva
    tools/port/eventos.py       lo emite: `_compilar`, un caso por comando de RM2k
    rom/src/main.s              lo ejecuta: `correr_codigo` y un `op_*` por opcode

Hasta el 2026-09-16 `tools/port/eventos.py` llevaba además un **modelo** del
intérprete, que corría el mismo bytecode cuadro a cuadro y contra el cual la
tanda comparaba cada pantalla. Ya no está: el bytecode lo ejecuta sólo la ROM, y
lo que quedaba del modelo era código que nadie llamaba —documentación con forma
de código, que envejece sin que ninguna prueba lo note—. De `eventos.py` queda
lo que el conversor usa al compilar.

De `tools/protocol/events.toml` salen generados `tools/port/event_opcodes.py` y
`rom/src/event_opcodes.inc`; ver `tools/protocol/README.md`, que está en inglés porque
ahí adentro no se sabe nada de este juego. **Un opcode nuevo se declara ahí y en
ningún otro lado**: antes el número lo elegía el compilador y le llegaba al
intérprete adentro de `mapdata.inc`, y así dos ramas eligieron el mismo sin que
git viera nada.

**Una página se emite sólo si todos sus comandos se pueden ejecutar.**
`compilar_pagina` corta con `NoSePuede` y el evento se queda sin código:
ejecutar la mitad de un script dejaría al juego en un estado que no existe, y la
comparación no lo vería: la golden es una captura de la propia ROM. Por lo
mismo, un evento con una condición que no sabemos evaluar queda entero afuera:
sin saber qué página está activa, correr la equivocada es peor que no correr
ninguna.

De ahí sale la única clase de error que se arregla **desde afuera** y no tocando
código: una página que teletransporta a un mapa que el cartucho no lleva no se
emite, y el evento se dibuja, se pisa y no hace nada. Por eso el conversor
nombra los mapas que le faltan a cada página que se cae por esto: es la única
razón de las veinte que se arregla sumando el mapa a la ROM.

Y la lista de qué comandos puede acompañar a un teletransporte sin que deje de
ser una puerta —o sea, sin intérprete— sale de `tools/rpgmaker/event_codes.py`, que se
genera desde liblcf y de ningún otro lado. Puestos de memoria, tres estaban mal,
y dos de ésos eran `PlayBGM` y `ChangeSpriteAssociation`: el filtro aceptaba
como puertas eventos que cambian la música y el sprite del héroe. **La
comparación no puede ver ese error**, porque una lista equivocada compila una
ROM equivocada y la golden es la captura de esa ROM. Esa clase de error se
revisa leyendo contra liblcf, no corriendo.

#### Un opcode por comando

Qué hace cada uno, y por qué está escrito como está, vive en el comentario de su
manejador. El conversor lo emite en `_compilar`, en el caso del comando de RM2k
de la primera columna; a los que la página espera y el opcode no corta —la
sacudida, los destellos, la imagen, la animación— el conversor les pone un
`OP_DELAY` detrás.

| Comando de RM2k | opcode | manejador en `rom/src/main.s` |
| --- | --- | --- |
| `ControlSwitches` | `OP_SWITCH` | `op_switch` → `poner_switch` |
| `ControlVars` | `OP_VAR` | `op_var` → `var_leer`, `var_escribir` |
| `ConditionalBranch` | `OP_IF`, `OP_IF_VAR`, `OP_IF_ACTOR` | `op_if`, `op_if_var`, `op_if_actor` |
| el `else` de una rama | `OP_GOTO` | `op_goto` |
| `ShowChoice` | `OP_CHOICE` | `op_choice` → `eleccion_tick` |
| `Wait` | `OP_DELAY` | `op_delay` |
| `Teleport` | `OP_TELEPORT` | `op_teleport` → `cargar_mapa` |
| `TintScreen` | `OP_TINT` | `op_tint` → `aplicar_tinte`, `subir_tinte` |
| `ShakeScreen` | `OP_SHAKE` | `op_shake` → `sacudida_tick` |
| `FlashScreen` | `OP_FLASH_SCREEN` | `op_flash_screen` → `destello_tick`, `tablas_de_destello` |
| `FlashSprite` | `OP_FLASH` | `op_flash` → `flashes_tick`, `pintar_flash` |
| `PanScreen` | `OP_PAN` | `op_pan` → `pan_tick`, `pan_cuadros` |
| `WeatherEffects` | `OP_WEATHER` | `op_weather` → `lluvia_tick` |
| `ShowMessage` | `OP_MESSAGE` | `op_message` → `msg_empezar`, `mensaje_tick` |
| `MoveEvent` | `OP_ROUTE` | `op_route` → `poner_ranura`, `paso_de_ruta` |
| `ProceedWithMovement` | `OP_WAIT_ROUTES` | `op_wait_routes` → `hay_rutas` |
| `HaltAllMovement` | `OP_STOP_ROUTES` | `op_stop_routes` → `retomar_pagina` |
| `ChangeEventLocation` | `OP_PLACE`, `OP_PLACE_VAR` | `op_place`, `op_place_var` |
| `TradeEventLocations` | `OP_SWAP` | `op_swap` |
| `ChangePartyMembers` | `OP_PARTY` | `op_party` → `cambiar_grupo` |
| `ChangeSpriteAssociation` | `OP_ACTOR_SPRITE` | `op_actor_sprite` → `elegir_grafico_heroe` |
| `TimerOperation` | `OP_TIMER` | `op_timer` → `timer_tick`, `timer_digitos`, `timer_oam` |
| `PlayBGM` | `OP_BGM` | `op_bgm` → `music_start` |
| `FadeOutBGM` | `OP_FADE_BGM` | `op_fade_bgm` → `bgm_fundido_tick` |
| `PlaySound` | `OP_SOUND` | `op_sound` → `music_tick` |
| `ShowBattleAnimation` | `OP_ANIMATION` | `op_animation` → `animacion_tick`, `animacion_dibujo_tick` |
| `ShowPicture`, `MovePicture`, `ErasePicture` | `OP_PICTURE`, `OP_PICTURE_MOVE`, `OP_PICTURE_ERASE` | `op_picture`, `op_picture_move`, `op_picture_erase` → `imagen_tick` |
| `ChangeGold` | `OP_GOLD` | `op_gold` |
| `ChangeItems` | `OP_ITEM` | `op_item` |
| `OpenShop` | `OP_SHOP` | `op_shop` |
| `EnemyEncounter` | `OP_BATTLE` | `op_battle` → `pelea_arrancar` |
| `OpenSaveMenu` | `OP_SAVE` | `op_save` → `ranuras_pantalla` |
| `ChangeSaveAccess` y sus dos hermanas | `OP_ACCESS` | `op_access` |
| `FullHeal`, y `ChangeHP` cuando suma | `OP_HEAL` | `op_heal` → `curar`, `curar_actor` |
| `KeyInputProc` | `OP_KEY` | `op_key` → `tecla_de` |
| el final de la página | `OP_DONE` | `correr_codigo` |

#### Las mecánicas que no son un opcode

Lo que el intérprete necesita alrededor: quién dispara una página, cuál está
activa, quién le cierra el paso a quién, y qué pasa mientras la pantalla está en
negro. Otra vez, el porqué está en el comentario de cada rutina.

**La mecánica la hace la ROM, y la tabla dice dónde.** Hubo un tiempo en que
cada una de estas líneas estaba escrita dos veces, en ensamblador y en Python,
y la segunda columna era el otro programa; ese programa ya no existe. Lo que
queda del lado de Python es el conversor, que compila lo que la rutina después
lee: las páginas, las rutas, las paletas, los glifos. Cuando hay algo así, la
tercera columna lo nombra; cuando la mecánica es entera de la consola, no hay
nada que nombrar y va un guión.

Y lo que **no** va más acá: una función de Python que no llame nadie, dejada
como "la definición escrita" de lo que hace la ROM. Es documentación con forma
de código, no se ejecuta, ninguna prueba la toca, y envejece sin que nadie se
entere. El porqué de cada mecánica va en el comentario de su rutina.

| Mecánica | en `rom/src/main.s` | quién la compila, o quién la mide |
| --- | --- | --- |
| Las puertas: un teletransporte sin intérprete, al **terminar** el paso | `cruzar_puerta` | `collect_doors` en `tools/rpgmaker/rm2k.py` |
| Pisar un evento, y pisarlo al final de una ruta forzada | `probar_contacto`, `accion_en_celda` | — |
| Hablarle a un evento con la tecla de acción | `probar_accion`, `encolar_por_accion` | — |
| Una página esperando turno es un bit por evento, no una cola | `marcar_esperando` | — |
| Qué página está activa, congelada hasta el refresco | `elegir_paginas`, `aplicar_paginas` | — |
| Las rutas propias de la página, y la velocidad que traen | `rutas_de_pagina`, `animar_ruta_ev` | `Ruta.cargar_pagina` |
| La frecuencia de la ruta, y encarar al héroe | `paso_de_ruta`, `hacia_el_heroe`, `tras_paso`, `tras_giro` | `espera_tras_paso`, `espera_tras_giro` |
| La frecuencia se sube y se baja a mitad de una ruta (las órdenes 30 y 31) | `paso_de_ruta` | `frecuencia_minima` |
| Las diagonales, y hacia dónde dejan mirando | `puede_celda_diag`, `encarar_diagonal` | `puede_en_diagonal`, `encarar_en_diagonal` |
| Cambiar el gráfico a mitad de una ruta (la orden 34) | `load_ruta_graficos`, `refrescar_npc` | `Graficos` |
| La colisión con los eventos | `celda_bloqueada`, `atraviesa_el_evento` | — |
| El gráfico sigue a la página, y el tile manda sobre el terreno | `grafico_de_pagina`, `pasa_con_evento`, `acomodar_npc` | `npcs_dibujables` |
| Los eventos dibujados con un tile del chipset | `load_npcs` | `npcs_dibujables`, `Charsets` en `tools/render/render_map.py` |
| El fundido de los teletransportes, con el mapa cargando adentro del negro | `empezar_fundido`, `fundido_tick` | `rampa_de_fundido`, y las constantes `FUNDIDO_*` |
| El tope de teletransportes encadenados | `SALTOS_MAX` y sus usos | lo cobra `pruebas/rpgmaker/test_saltos.py` |
| La pantalla se prende en el vblank y en ningún otro lado | `flush_video` | — |
| La ventana de mensaje, clavada abajo por HDMA | `armar_hdma`, `msg_empezar`, `msg_ptr_sig` | `tools/port/ventana.py`, `Mensajes` |
| El texto compuesto en caliente, con los glifos ya pre-renderizados | `mensaje_tick`, `componer_char`, `cebar_linea` | `fuente_prerender` en `tools/port/snes_convert.py` |
| El arranque dura siempre lo mismo | `BOOT_CUADROS` | lo corre `Partida` en `pruebas/arnes/consola.py` |
| Los cuadros perdidos se cuentan | `contar_perdidos` | los lee `Partida.cuadros_perdidos` de la WRAM |
| La música no espera al lazo: va en una IRQ vertical | `irq_musica`, `IRQ_LINEA` | — |

Lo que hace que el lazo entre en un cuadro —FastROM, los glifos precompuestos,
la tabla de productos del destello, la lluvia más barata— no cambia qué se
dibuja ni cuándo, y por eso se comprueba sin tocar nada más: las goldens y las
pruebas dan igual.

##### Atravesar paredes vale mientras dura la ruta

La divergencia deliberada con RM2k que este lado se permite, y la que hace que
los cofres del Sector 30 se puedan pisar o no. La orden 36 de una ruta
—`walk_everywhere_on`— es **pegajosa** en RM2k: escribe `move_route_through` de
`Game_Player`, que es un campo de la partida guardada —`SaveMapEventBase` en
liblcf— y que no repone nadie, ni `CancelMoveRoute`, ni `ForceMoveRoute`, ni
`MoveTo` al cambiar de mapa. Así que una página que la prenda y no la apague
deja al héroe atravesándolo todo hasta el final de la partida. Medido sobre el
juego entero: de las 153 páginas que la mueven, **4 la dejan prendida**, y dos
de esas cuatro —el Hover-Tram del mapa 13, `EV0028`, y el mapa 14— están en el
camino principal, así que el defecto lo tiene cualquiera que llegue caminando al
Sector 30.

Acá la bandera vale **sólo mientras el paso lo dé la ruta forzada**. El porqué,
con el síntoma que lo delató, está en `celda_bloqueada`, que es donde se lee
`atravesando` y no la pegajosa `ruta_atraviesa`.

Para la pregunta al revés —un evento que camina contra el héroe— se sigue
mirando la pegajosa, `ruta_atraviesa`. Es una asimetría, y se deja porque
ninguna ruta del juego la ejercita: haría falta un evento caminando encima del
héroe justo después de una página que dejó la 36 prendida.

#### Varios temas en el cartucho

Al principio la ROM llevaba **un** tema. Los `PlayBGM` de las páginas
compilaban igual —el bytecode lleva el índice del tema en `Temas`— pero la ROM
tocaba sólo el que le había tocado llevar y con cualquier otro índice no hacía
nada. Ahora lleva todos los que entren.

**Lo que los limita no es el cartucho: es la ARAM.** Las muestras viven en los
64 KB del SPC700 y se suben una sola vez al arrancar, con el protocolo del IPL,
que después de saltar al driver ya no está. De streams sobra lugar —tres temas
son 95 KB de los 480 que quedan— pero de bancos de muestras entra uno solo, y
el de `escape_newyork` son 32 KB.

Las dos salidas eran un driver que sepa recibir datos —o sea rebootear el
SPC700 y volver a subir— o **un solo banco compartido**. Gana el compartido, y
lo que lo decide no es el trabajo: subir 32 KB byte a byte con acuse es del
orden de medio segundo, o sea que cada `PlayBGM` frenaría el juego treinta
cuadros. Mientras hubo referencia en Python eso además había que modelarlo para
que la comparación cuadro a cuadro siguiera valiendo, y modelar cuánto tarda una
transferencia es exactamente lo que no se puede medir honestamente. La
referencia ya no está, así que hoy lo que decide es sólo el medio segundo.

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

Lo que se paga, y está declarado en `assets/LIMITACIONES.md`:

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
principal y la subpantalla— y **está implementado y verificado**, en la rama
`color-math-translucidos` (commit `6e0e355`). No se usa: taro lo probó el
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
    tools/brr/                   códec BRR y lector de SoundFont, en Rust
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
herramientas de Rust del repo —`brr` para las muestras, `ditto` y
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

### Lo que falta

**Está en `ESTADO.md`**, que es el archivo de lo que está a medias: acá
envejecía sin que nadie lo notara. Y lo que se puede preguntar en vez de leer,
se pregunta:

* qué comandos se aceptan y no se hacen lo dice `ACEPTADOS_SIN_HACER`, en
  `tools/port/eventos.py`, que es una lista ejecutable y no puede desincronizarse;
* qué órdenes de ruta no sabemos caminar, también.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
