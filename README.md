# abl-snes — A Blurred Line en Super Nintendo

Un port de *A Blurred Line*, un juego hecho en RPG Maker 2000, a la Super
Nintendo. Acá está todo: cómo se lee el juego original, cómo se lo vuelca a un
formato que se pueda mirar, y el port entero con sus trampas y lo que falta.

Hubo antes un port a Mega Drive. Se sacó de este repo cuando quedó claro que el
camino era la SNES —el audio del S-DSP convence y el del YM2612 no—, y vive
aparte en `abl-sega`. Lo que era compartido de verdad se quedó, con nombres que
no mienten: `tools/rm2k.py` para las reglas de RPG Maker 2000,
`tools/pixeles.py` para pasar de una imagen a tiles y paletas, y
`tools/musica.py` para pasar de un MIDI a notas y voces.

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
    * [El cartel de "One year previously"](#el-cartel-de-one-year-previously)
        * [Lo que costaría el sistema de imágenes entero](#lo-que-costaría-el-sistema-de-imágenes-entero)
    * [Varios mapas en la ROM](#varios-mapas-en-la-rom)
        * [Las puertas](#las-puertas)
        * [El fundido de los teletransportes](#el-fundido-de-los-teletransportes)
        * [La pantalla se prende en el vblank, no donde se carga el mapa](#la-pantalla-se-prende-en-el-vblank-no-donde-se-carga-el-mapa)
        * [Pisar un evento, y pisarlo al final de una ruta forzada](#pisar-un-evento-y-pisarlo-al-final-de-una-ruta-forzada)
        * [La colisión con los eventos](#la-colisión-con-los-eventos)
        * [Plantar un evento en una celda](#plantar-un-evento-en-una-celda)
        * [Los eventos dibujados con un tile del chipset](#los-eventos-dibujados-con-un-tile-del-chipset)
        * [El gráfico sigue a la página, y el tile manda sobre el terreno](#el-gráfico-sigue-a-la-página-y-el-tile-manda-sobre-el-terreno)
        * [El ascensor no llevaba a ningún lado](#el-ascensor-no-llevaba-a-ningún-lado)
        * [Las rutas propias de las páginas](#las-rutas-propias-de-las-páginas)
        * [La frecuencia de la ruta, y encarar al héroe](#la-frecuencia-de-la-ruta-y-encarar-al-héroe)
        * [El arranque de verdad](#el-arranque-de-verdad)
        * [El intérprete de eventos](#el-intérprete-de-eventos)
        * [La ventana de mensaje](#la-ventana-de-mensaje)
        * [El texto se compone en caliente](#el-texto-se-compone-en-caliente)
        * [La sacudida de pantalla](#la-sacudida-de-pantalla)
        * [El destello de pantalla](#el-destello-de-pantalla)
        * [El arranque dura siempre lo mismo](#el-arranque-dura-siempre-lo-mismo)
        * [La cámara corrida sin el héroe](#la-cámara-corrida-sin-el-héroe)
        * [Varios temas en el cartucho](#varios-temas-en-el-cartucho)
        * [El `FadeOutBGM`](#el-fadeoutbgm)
        * [La frecuencia se sube y se baja a mitad de una ruta](#la-frecuencia-se-sube-y-se-baja-a-mitad-de-una-ruta)
        * [Cambiar el gráfico a mitad de una ruta](#cambiar-el-gráfico-a-mitad-de-una-ruta)
        * [Las diagonales de ruta](#las-diagonales-de-ruta)
        * [El cronómetro](#el-cronómetro)
        * [Cómo se verifica](#cómo-se-verifica)
        * [Los cuadros perdidos se cuentan](#los-cuadros-perdidos-se-cuentan)
    * [El personaje](#el-personaje)
        * [Las poses se suben en caliente](#las-poses-se-suben-en-caliente)
    * [La colisión](#la-colisión)
    * [La pila y la BSS comparten los ocho kilos](#la-pila-y-la-bss-comparten-los-ocho-kilos)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
    * [Cómo está armado](#cómo-está-armado)
    * [El banco de muestras](#el-banco-de-muestras)
    * [Cómo se suelta una nota](#cómo-se-suelta-una-nota)
    * [La percusión](#la-percusión)
    * [Toolchain](#toolchain)
    * [Cómo se verifica el ensamblador](#cómo-se-verifica-el-ensamblador)
    * [Cómo se verifica la ROM](#cómo-se-verifica-la-rom)
    * [El parche de bsnes](#el-parche-de-bsnes)
    * [Trampas del hardware](#trampas-del-hardware)
    * [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## Leer el juego original

Lee los datos originales de RPG Maker 2000 y saca un PNG del mapa entero: las
dos capas de tiles más los eventos en su posición inicial, como se verían al
empezar una partida nueva. Sin panorama y sin el héroe.

    just render        # mapa 1, "Introduction" -> un PNG del mapa entero
    just render 8      # "Lashe City - 34,35"
    just maps          # todos los mapas, su chipset, eventos y assets faltantes
    just check         # renderiza los 328 sin guardar, para ver si algo rompe

No hay nada que instalar: es Python con Pillow, que ya está en el sistema.

El mapa de arranque del juego es el 4, "Blank (Leave START here)": un cuarto
vacío de 20x15 que sólo teletransporta. El primer mapa de verdad es el 1.

### Piezas

    tools/lcf.py          lector de .lmu/.ldb/.lmt (el formato binario de RM2k)
    tools/chipset.py      expansión del ChipSet a un atlas de tiles resueltos
    tools/charset.py      recorte de sprites de personaje
    tools/render_map.py   el render en sí
    tools/list_maps.py    inventario de mapas
    tools/export_json.py  volcado a data/
    tools/gen_schema.py   genera el esquema de los formatos LCF desde liblcf
    tools/lcf_schema.py   generado: 63 structs, 1268 campos
    tools/event_codes.py  generado: nombres de los opcodes de evento

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
32x45 e indexarlo por ID. `tools/chipset.py` es un puerto de
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
dibuja, que es lo correcto — todavía no existe en pantalla. `--first-page`
fuerza la página 1 para ver el estado "de autor".

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

Se puede apuntar a otra copia con `--rtp-dir` o con `ABL_RTP_DIR`.

Con eso, los 328 mapas renderizan sin faltantes. `just maps` avisa si falta
algo.


## Los datos en formato versionable

    just export        # .lmu -> data/, y verifica releyendo

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano.

    data/maps.json            el árbol de mapas y la posición inicial
    data/maps/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/maps/Map0001.tiles   las dos capas de tiles, una fila del mapa por línea
    data/db/*.json            la base de datos, una sección por archivo

Son 17 MB: los 328 mapas con sus 4204 eventos y 46556 comandos, más la base de
datos entera — 60 actores, 400 skills, 450 ítems, 175 enemigos, 300 tropas, 180
animaciones, 60 eventos comunes, 1200 switches y 250 variables.

**Los tiles van en texto, no en binario.** En binario ocuparían la mitad, pero
serían opacos para git; en texto, cambiar un tile cambia una línea. A 5
caracteres por tile las columnas quedan alineadas y la grilla se lee como lo
que es. El costo real son unos pocos MB que comprimen muy bien.

**Los scripts de los eventos van enteros.** El formato de los ~130 comandos de
RM2k es uniforme — código, sangría, un string y una lista de enteros — así que
se pueden leer todos sin saber qué hace cada uno. Los nombres de los opcodes
salen de liblcf, y cada comando ocupa una línea:

    "script": [
      [0, "ShowMessage", "SHOPKEEPER", []],
      [0, "ShowMessage_2", "I have a wide range of useful items.", []],
      [0, "OpenShop", "", [0, 1, 0, 0, 97, 299, 300, 301, 302, 103, 114, 115]]
    ]

Interpretar los parámetros de cada comando es otro tema, y todavía no está
hecho.

**El esquema de la base de datos se genera, no se escribe.** La `RPG_RT.ldb`
tiene 63 structs y 1268 campos tipados; escribir eso a mano sería tedioso y
quedaría desactualizado. Pero liblcf ya lo tiene declarado en su código
generado, así que `tools/gen_schema.py` cruza los IDs de chunk de `chunks.h`
con los tipos de las declaraciones `TypedField` y escupe `tools/lcf_schema.py`.
El decodificador de `lcf.py` es genérico y se guía por eso. Resultado: los 15
grupos de la base salen enteros, sin un solo chunk que el esquema no cubra.

**Verificación.** `--verify` relee los `.tiles` y los compara contra los `.lmu`,
y revisa que ningún string tenga caracteres de control ni de reemplazo — que es
como se ve un parseo desfasado. Los chunks que el esquema no conozca se
exportan en hexa con su ID a la vista y se reportan al final: nada se pierde en
silencio.

**Encoding.** El texto es cp1252, porque ABL se hizo con el RM2k de Don Miguel.
Quedan un par de mensajes del RTP japonés que el autor nunca tocó y siguen en
Shift-JIS; se detectan por los bytes que cp1252 no define.

**Se omite lo que está en su valor por defecto**, para que el diff muestre sólo
lo que importa. Una página sin condiciones no tiene la clave `conditions`; un
evento quieto no tiene `move`. Y los enums salen como texto: `"trigger":
"auto_start"` en vez de `"trigger": 3`.

Por ahora es de ida nomás: `data/` se genera desde los `.lmu`, no al revés.

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
la SNES. Cuando se escribió esto las muestras eran ondas de un ciclo generadas
en Python; hoy salen de un SoundFont y van en BRR, y el veredicto sólo mejoró.

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

El resultado se verifica pixel por pixel contra el render de Python, a 15 bits,
que es la profundidad real de la consola:

    Map0007: 0 pixeles distintos de 57344

En la Mega Drive esto no se podía hacer: los 9 bits obligaban a fusionar
colores, así que sólo se podía comparar por forma. Acá la comparación es exacta.

Eso destapó un detalle del hardware que a ojo era invisible: **el PPU muestra la
línea `vofs+1` en el primer scanline**, no la `vofs`. Con el scroll en 0 el mapa
quedaba corrido una línea. Las dos imágenes se veían idénticas y diferían en el
50% de los pixeles.

### La cámara

El scroll es por hardware: mover la cámara es escribir dos registros. Lo único
que hay que cuidar es no salirse del mapa.

El tilemap del PPU se arma con "pantallas" de 32×32 celdas encadenadas en VRAM,
y no van una al lado de la otra en memoria: cada una ocupa sus 1024 celdas
seguidas.

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

Los dos "+sprite" son del 2026-09-12 y los pidió el mismo mapa: **Delcentric
Factory**, el camino al auditorio. Gasta 217 tiles de fondo y **475 de sprite**
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

Ese corte estaba clavado en dos paletas para la capa de encima y 95 colores para
el fondo, y **27 mapas no entraban** —los tres primeros del juego entre ellos—
mientras el fondo dejaba colores sin usar. Al medirlo aparecieron dos causas que
se veían como una sola:

    la capa de encima pide 3 paletas    7 mapas
                            4           5
                            5           1
                            6           2
                            7           6
    un tile suelto con más de 15 colores   1 mapa

La segunda no la arregla ningún reparto: un tile de 17 colores no entra en una
paleta de 15 por muchas que haya. Se arregla fusionando, que es lo que la Mega
Drive ya hacía con el fondo.

Ahora el corte lo decide el conversor mapa por mapa, y **el fondo tiene la
primera opción**: se queda con las paletas que necesita para los colores que
realmente usa, y la capa de encima se lleva las que sobren —hasta las que pida,
nunca más— y fusiona si no le alcanzan. Va en ese orden porque son 300 mapas
cuya capa de encima pide una o dos paletas contra un puñado que pediría siete:
servir primero al de encima le sacaría colores al fondo en todos para que unos
pocos no fusionen.

    Map0007   fondo 60 de 111 disponibles | encima 1 paleta desde la 7
    Map0001   fondo 49 de  63             | encima 4 paletas desde la 4
    Map0348   fondo 95 de  95             | encima 2 desde la 6, 27 fusionados

Los tres primeros mapas del juego entran ahora sin fusionar un solo color.

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
`assets/LIMITACIONES.md` y la referencia da la misma vuelta, así que los dos
lados siguen dibujando lo mismo.

**La decisión no entra en el vblank, y eso no es gusto.** El vblank del mapa 8
—el más cargado de sprites del port— no tiene un ciclo de sobra: **veinte `nop`
puestos ahí a propósito le cuestan 61 pixeles**, porque la cola de poses se le
va del vblank y las últimas escrituras caen con la pantalla ya encendida. Las
dos divisiones iban ahí en la primera versión y le costaban 313. Así que quien
decide es `anim_tick`, en el cuerpo del lazo, y deja **un byte** —el último
libre de la página directa— con tres bits por familia: cero es "nada", y si no
el dibujo más uno. En el vblank queda un `lda` y un `beq`.

**La fase se midió, no se razonó.** Como el DMA sale en el vblank siguiente,
igual que OAM, la primera versión miraba el tick anterior "por el cuadro que el
video va atrasado". Con eso la tanda da rojo en **un tick de cada 24** —el del
cambio, y nada más— que en el mapa 5 son 18349 pixeles, el 32% de la pantalla.
Con el tick tal cual, cero. El caso que lo cobra es `snes-caminando 5 left` con
el avance 46, que es el tick 24 justo: un avance de N pixeles es el tick N/2 + 1,
así que se le puede pedir a la tanda el cuadro exacto en que el agua cambia.

**Y el reloj de la ROM no es `estado.ticks`.** Adentro del negro de un
teletransporte el mundo está congelado y la referencia no cuenta el cuadro, pero
la consola sigue dando vueltas al lazo: son 70 por fundido. La referencia ya
tenía esa cuenta hecha para el plan de la caminata —`estado.ticks + fundidos *
FUNDIDO_TOTAL`— y le faltaba usarla acá. Sin eso, la escena de Core y Manta se
iba un dibujo desde el primer teletransporte: 7284 pixeles en el cuadro 1200, y
verde en el 300 y el 600, que son los de antes del salto.

Los dos errores tienen la misma forma y por eso vale escribirlos juntos: **los
dos lados contando ticks distintos**. El primero se veía en un cuadro de cada
24 y el segundo sólo después de un fundido.

**Y tres del 65816, todos el mismo.** Un `ldx` o un `ldy` con los índices anchos
se lleva **el byte de al lado**, y un `sta` con el acumulador ancho **lo pisa**.
Las tres veces fue sobre `temp`, que son cuatro bytes:

* `ldx temp + 3` para preguntar "¿este tick es el del cambio?" se llevaba
  `temp + 4`, que es el byte bajo de `hero_x`. Todos los ticks parecían el del
  cambio. **No se ve en la pantalla** —subir el dibujo que ya está subido no
  cambia nada— así que la comparación de pixeles daba cero; lo que se veía era
  el presupuesto de poses bajando en todos los cuadros.
* `ldy temp + 2` para pasar el dibujo se llevaba `temp + 3`, y con eso el DMA
  leía de cualquier lado.
* `sta temp + 2` adentro de `anim_subir`, con el acumulador ancho, pisaba
  `temp + 3`, donde el vblank guardaba lo que le quedaba pendiente a la segunda
  familia. Se perdía **sólo cuando las dos cambiaban en el mismo tick** —cada
  24, que es múltiplo de 6— y el tile animado se quedaba con el dibujo viejo
  hasta el cambio siguiente: **8 pixeles** en el mapa 2, en la celda (5,53).

El tercero es el que mejor muestra para qué sirve la tanda: ocho pixeles, en un
caso que no tiene nada que ver con la animación —una puerta del mapa 2— y en
cuatro cuadros elegidos hace semanas.

Los dos casos nuevos de la tanda están medidos con la fase rota a propósito, que
es lo único que prueba que miran algo: `snes-caminando 5 left "40 46 48 50"`
cobra 18349 pixeles y `snes-caminando 3 down "54 56 58 60"` cobra 211. Hacen
falta los dos: el mapa 5 no tiene tiles animados y la corrida de agua del 3 sale
vacía.

### El save point: anima quieto y guarda a disco

`SaveByTalansPad0`, el evento 67 del mapa 8, son tres comandos —`PlaySound`,
`OpenSaveMenu`, `ChangeSaveAccess`— y una página con `animation_type` 3, que en
RM2k es "Fixed Dir/Continuous": recorre el ciclo de caminata **sin moverse**.
taro pidió las dos cosas.

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

La fase se midió como la del agua: sin el `inc` que la corrige, el save point del
mapa 8 se queda una columna atrás y son 76 pixeles. Lo cobra
`snes-escena 8 "9 55" 0 down "20 30 40 50"`, que es un caso nuevo de la tanda:
la celda (9,55) lo deja en pantalla y los cuatro cuadros caen en tres columnas
distintas del ciclo.

**Guardar abre la pantalla de ranuras, como en RM2k.** `OpenSaveMenu` apila
la misma pantalla que "Resume the Story" abre desde el título, en modo guardar
—"Save in which slot?", que es `save_game_message` del LDB—, con el cursor en
la ranura que la partida está usando, que es el `latest_slot` de
`Scene_File::Start` sin fechas. A elige y guarda ahí, B vuelve sin guardar, y
no se pregunta si la ranura estaba ocupada porque `Scene_Save::Action` tampoco
pregunta. El cartucho declara SRAM con batería en la cabecera —`$02` y 8 KB— y
en el EverDrive eso es una pila de verdad. Empezó siendo una sola ranura sin
menú, que fue el alcance de la primera vuelta.

Tres cosas de cómo está hecho, porque las tres costaron un día:

* **Bloquea adentro del intérprete y no cuesta ningún tick.** La pantalla corre
  su propio lazo de cuadros desde `op_guardar`, igual que desde el título, y
  `vueltas` no avanza mientras se ve. Es lo que hace RM2k: la escena apilada
  para el reloj del mapa, y la página sigue por el comando siguiente cuando se
  cierra. Por eso la referencia no modela nada —`OP_GUARDAR` ocupa su byte y no
  cuesta un cuadro— y después de cerrar los dos lados van por el mismo tick,
  tarde lo que tarde el jugador.
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
* **La pantalla va en toda ROM**, con título o sin él. Hasta el 2026-09-10 salía
  sólo con `--con-titulo` y sin él era un byte de relleno con `RANURA_TILES` en
  cero, y un DMA de cero bytes son 65536: abrirla desde una ROM sin título
  llenaba la VRAM de basura. Ésa era la "pantalla negra con basura arriba" del
  primer intento, que ESTADO.md atribuía al contexto del intérprete. Y el
  testigo que "entraba 85 veces" leía RAM sin inicializar: snes9x la llena de
  `$55`, que es 85.

**Cada ranura con partida muestra lo que muestra RM2k**, que es lo que
`Window_SaveFile::Refresh` dibuja por archivo: el nombre del archivo, el
nombre del líder, el nivel —`lvl_short` en el color 1 del sistema y el número
a dos cifras, "L  1", mockeado en 1 porque no hay actores con nivel— y las
**caras** del grupo, del FaceSet y a 48x48. taro lo pidió el 2026-09-10 al ver
que EasyRPG mostraba la cara de Talan. La fila mide 48 pixeles por eso.

Está mirado contra el oráculo y no sólo leído del código: `rom/easyrpg.sh`
con `REPLAY` guardó sobre el save point del mapa 8 en el juego original y
abrió el menú de cargar desde el título, y la captura está en
`/extras/capturas/erpg-cargar`. Lo que difiere a propósito: los puntos de vida
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

Lo cobra `just snes-guardar` en seis cuadros, todos en cero: la pantalla al
abrirse y con el cursor dos ranuras abajo, contra `titulo.py --modo 1`; y el
mapa de vuelta después de cancelar y después de elegir, en dos ticks, contra la
referencia. Los toques de adentro de la pantalla van con `--toques-hardware`,
que cuenta cuadros de hardware desde el arranque: un toque por tick no puede
caer donde no hay ticks. Y lo que queda en la SRAM lo mira
`pruebas/test_guardar.py`, que ahora **atraviesa la pantalla** —baja el cursor
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

Dos detalles que costaron su rato:

* **La partida vive en $0100 y no en $0000.** `w65.py` elige página directa
  cuando la dirección entra en un byte, igual que ca65, así que con la partida
  al principio del banco un `lda SRAM_MAGIA, x` leería la página directa en vez
  de la SRAM. Los 256 bytes de abajo no los usa nadie.
* **La magia se compara contra inmediatos**, no contra una tabla de la ROM: con
  el banco de datos apuntando a la SRAM no hay cómo leer el cartucho —el
  ensamblador no tiene direccionamiento largo y la página directa está llena—.

Una ranura vale si tiene la magia `ABLS` y la suma de sus bytes cuadra. Las dos
cosas hacen falta: la SRAM sin escribir trae basura —snes9x la llena de $60— y
una ROM de prueba que la tomara por buena cargaría una partida inventada.

**Lo que se escribe no lo puede cubrir la tanda de pixeles**, porque guardar
no cambia un pixel. Lo cubre `pruebas/test_guardar.py`, que hace lo único que
prueba algo: va a otro mapa, prende un switch, guarda, **resetea la consola de
verdad** y mira dónde arranca. La SRAM sobrevive al reset y la WRAM no, así que
si la partida vuelve es porque salió del cartucho. Con `guardar_partida`
cortado a propósito, tres de sus cuatro pruebas dan rojo.

### El menú de pausa

Desde el 2026-09-11 **B abre el menú**, que es `Scene_Menu` de RM2k: las cinco
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
cosmético y está declarado. Todo lo demás sale de `titulo.py`: `render_menu`
es la referencia y el conversor emite **los mismos bloques de celdas**, en el
mismo banco de tiles y la misma paleta que la pantalla de ranuras —las caras
son las mismas y guardar se abre desde el menú—. Las órdenes en gris llevan su
propia paleta de BG2: el color 3 es un degradé y con el del texto sumaban 18
colores, así que a las caras les quedan seis paletas.

**Y desde el 2026-09-12, la séptima cara se cuelga de una prestada.** La lista
de caras no es la del grupo sino la de todos los que algún `ChangePartyMembers`
de los mapas de la ROM pueda meter, y con Lashe City entera son ocho: los cuatro
de la intro más Arden, Saldra, el Gang Member de los Rat Tracks y AG7-17. Antes
eso era un corte —`SystemExit`— y ahora cada color de la cara que sobra va al
más cercano por luma de la paleta a la que menos colores le falte, que es
exactamente lo que `cabe` hace con los sprites y la misma razón de taro: un
personaje con colores raros es un error visible, y un cuarto mapa que no entra
no lo es. Se ve en el informe del conversor, que las nombra.

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
entre los comandos ignorados, compilan a `OP_ACCESO` y apagan o prenden los
bits 0 y 1 de `FAR_ACCESO`, que viaja en la partida. Guardar prohibido pone
Save en gris; el menú prohibido hace que B no lo pida. El save point no mira
el permiso, como `OpenSaveMenu`.

Mientras el menú se ve **el reloj del juego no corre**, igual que con la
pantalla de ranuras, así que para la referencia el menú no cuesta ningún tick
y después de cerrarlo los dos lados van por el mismo cuadro. Lo cobra
`just snes-menu`: el menú como se abre y con el cursor movido contra
`titulo.py --menu`, y el mapa después de cerrar contra `snes_expect.py`. Lo que
la tanda no alcanza lo mira `pruebas/test_menu.py`: el menú con un grupo y oro
puestos, guardar desde el menú, los dos permisos puestos por el bytecode, B a
mitad de un paso, y que los permisos vuelvan de la SRAM.

### La pantalla de ítems

"Use Item" abre `Scene_Item` desde el 2026-09-11: arriba la descripción del
ítem marcado y abajo la lista del inventario con cuántos hay de cada uno, en
orden de número como `Game_Party`. En gris va lo que A no usa, como
`Window_Item`. Hoy A usa **los ítems de switch**, que en la demo son uno solo,
la Portable Console: prende su switch —el 710—, gasta uno si tiene usos
—`uses` en cero es infinito—, pide el refresco de páginas y vuelve derecho al
mapa, que es el `PopUntil(Scene::Map)` de RM2k. B vuelve al menú. Las
medicinas quedan en gris: piden HP que cambien, y en los mapas de la demo no
hay cómo conseguir una ni nadie baja los HP —`ChangeHP` suma 1 a un grupo con
la vida llena—. El switch 710 dispara el evento común 39, "NewMenuActivated",
que es el menú propio del juego hecho con imágenes: 568 comandos, y los
eventos comunes todavía no corren.

**Las medicinas van en blanco y abren la elección de actor**, que es el panel
del grupo del menú con un cursor al costado —`render_objetivo`—. A no hace
nada, y es exacto: `UseItem` sólo gasta la medicina si sube algo, y en este
juego **fuera de batalla nadie baja nunca de los HP ni de los SP máximos**.
Medido sobre los 328 mapas: los 11 `ChangeHP` suman, los 16 `ChangeCondition`
quitan un estado y los 54 `FullHeal` llenan. Por eso esos tres comandos
compilan a nada —el que reste o ponga un estado no compila— y los HP que
muestra el menú son siempre los del máximo. El día que haya batallas, los HP
pasan a ser estado del juego y a viajar en la partida. Libros, materiales y
especiales siguen en gris.

**El texto va de a una letra por celda.** La pantalla tiene su propio banco
de tiles con cada carácter de la fuente en dos celdas, en blanco y en gris
—307 tiles, que no dependen de cuántos ítems haya—, y los nombres y las
descripciones van en ASCII en el cartucho; escribir una letra son dos
palabras del tilemap. El primer intento llevaba el texto de cada ítem ya
dibujado en el banco de las ranuras y el menú, como las caras, y con una
docena de ítems no entraba: cuatro ROMs de la tanda dejaron de armarse. El
precio es que las letras van a 8 pixeles y no a los 6 de la fuente, como las
cifras del oro. En RM2k la lista va en dos columnas de 144 pixeles; acá en una,
con la cantidad a la derecha, y la descripción en dos renglones de 30 letras.
Es cosmético y está declarado.

La descripción se compone en `texto_buf` —el búfer del compositor de
mensajes, libre con el menú abierto— y sube de un DMA al principio de cada
cuadro: escribirla letra por letra al mover el cursor no entraba en el vblank
y el segundo renglón salía cortado. Cuando el cursor se sale de las once
filas, la lista se repinta entera con la pantalla apagada, que es un cuadro
en negro.

Lo cobran `just snes-items` —la pantalla como se entra y con el cursor sobre
la consola contra `titulo.py --items`, y el mapa después de usarla contra
`snes_expect.py`— y `pruebas/test_items_pantalla.py`: la consola prende el 710
y no se gasta, un ítem en gris no hace nada, catorce ítems en once filas se
corren y vuelven, y la lista vacía.

### El equipo, y las pantallas de texto

"Equipment" abre la elección de actor en modo elegir y después `Scene_Equip`
de ése, desde el 2026-09-11: su nombre, los cuatro parámetros —los del nivel,
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
pasó de los 1024 de la ranura: **la SRAM es de 32 KB** desde el 2026-09-11 y
las ranuras van cada 2048. `ChangeEquipment` no compila todavía: el juego lo
usa en dos mapas que no están en la demo.

La pantalla de equipo —y la tienda, que sigue— son **pantallas de texto**: no
llevan bloques dibujados sino la fuente de la pantalla de ítems, y se componen
enteras en `texto_buf` —el tilemap de 32 por 28 celdas, 1792 bytes— que sube
de un DMA por cuadro. Componer no tiene apuro, y `pantallas.py` es la
referencia con el mismo compositor de celdas. El DMA va **después** de leer el
control: al revés, sus diez líneas hacían que `read_pad` llegara con la
lectura automática terminada, cada vuelta duraba dos cuadros y la mitad de los
toques se perdía. Lo cobró `snes-equipo`.

Lo cobran `just snes-equipo` —las ranuras de Kersh con su equipo inicial, la
lista del arma con los parámetros que quedarían, y el mapa después de volver—
y `pruebas/test_equipo.py`: el equipo inicial en la RAM, equipar desde el
menú, la lanza a dos manos que saca el escudo, la línea vacía, y el equipo en
la partida.

### La tienda

`OpenShop` abre `Scene_Shop` desde el 2026-09-11. Compila a `OP_TIENDA` —el
tipo, el juego de mensajes y la lista de lo que vende, de largo variable como
`OP_ELEGIR`— y, como guardar, la pantalla se abre adentro del intérprete y no
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
10, y `pruebas/test_tienda.py` la recorre entera pixel por pixel contra
`pantallas.pantalla_tienda`: comprar, el tope del oro, vender, el oro y el
inventario que quedan.

### La batalla por turnos

`EnemyEncounter` abre una pelea desde el 2026-09-12. Es la primera versión y
taro la pidió así, con todas las letras: *"podemos ignorar desafíos
relacionados con la imagen de fondo y usar versiones de menor resolución,
menor paleta de colores o incluso un color plano y ya, así nos podemos enfocar
en la mecánica de la batalla por turnos, daño, hp, win condition, etc"*. Así
que **no hay fondo ni battlers dibujados**: la pantalla es de texto sobre
negro, la misma grilla de 32 por 28 celdas del equipo y la tienda.

Lo que sí es de RM2k son las palabras —todas del LDB— y **todas las cuentas**,
que salen de easyrpg-player y están escritas dos veces: en `main.s` y en
`tools/batalla.py`. Que las dos den lo mismo es lo que le permite a
`pruebas/test_batalla.py` predecir **el número exacto** que cada HP va a tener
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

`OP_BATALLA` lleva la tropa y **los tres destinos**: victoria, huida y
derrota, absolutos dentro de la página y parcheados al cerrar el bloque, igual
que las opciones de un `ShowChoice`. El manejador que la página no tenga
apunta al final, que es lo que hace RM2k con un sub-índice sin rama. Como la
tienda y como guardar, la pantalla bloquea adentro del intérprete y `vueltas`
no avanza: los dos lados salen del opcode en el mismo tick tarde lo que tarde
el jugador.

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
    usar un ítem                    sí, desde el 2026-09-13: ver abajo
    habilidades                     sí, desde el 2026-09-13: ver abajo
    los estados                     no
    experiencia, oro, subir nivel   no: no hay niveles
    la música y los efectos         sí, desde el 2026-09-13: ver abajo
    los battlers dibujados          sí, horneados en el fondo: ver abajo
    la imagen de fondo              sí, desde el 2026-09-13
    las páginas de evento de tropa  no
    los encuentros aleatorios       no: ver "Lo que falta"

La pantalla muestra los HP de los enemigos, que RM2k no hace. Es a propósito:
lo que esta vuelta tiene que dejar ver es la mecánica, y sin eso un golpe que
pega y uno que falla se ven igual.

**De las 51 peleas del juego, la única que el jugador alcanza hoy es la del
droide del mapa 2.** La de los Lazer Teeth del mapa 9 —la tropa 86, cuatro
enemigos— no compila, y no por la batalla: la corta un `MoveEvent` con la
orden de ruta 9, "hacia el héroe", que la ROM no camina. Por eso la tropa de
cuatro la ejercita `just snes-batalla` con la página de prueba, que es el
mismo recurso que usa `snes-guardar` con la pantalla de ranuras.

#### El menú: las cinco órdenes del ABL

Hasta el 2026-09-13 eran tres en un renglón —`Attack`, `Defend`, `Escape`— y
taro pidió el menú del original, que además tiene `Use Item` y la habilidad.
Ahora son las cinco, en los dos renglones del mensaje: tres arriba y dos abajo,
que mientras se elige está libre. Las palabras son las del LDB, y el ancho es
diez porque es lo que mide la orden más larga.

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

Lo que hasta el 2026-09-13 decía acá era que esa orden iba en gris porque a
este nivel nadie sabía ninguna habilidad, y **eso era falso**: salía de leer los
parámetros con el nivel mockeado en 1. Ver "Las habilidades", más abajo.

`Use Item` sí anda. Abre la lista de lo que se puede usar **donde va la de los
enemigos**, porque eligiendo qué usar lo que hace falta ver es el grupo; se
elige el ítem, después a quién, y con eso queda anotada la orden de ese actor,
que se ejecuta en su turno como cualquier otra. B vuelve un paso.

Qué entra en la lista y cuánto cura sale de easyrpg-player:

* **Qué entra**: `Game_Party::IsItemUsable` con la pelea abierta, o sea una
  medicina que no esté marcada "sólo fuera de batalla". De ésas, este port
  ofrece las que **recuperan HP y no son `ko_only`**: las de SP quedan afuera
  porque la lista todavía sólo sabe curar HP —los SP **sí** son estado desde el
  2026-09-13, así que eso pasó de imposible a deuda—, y las de revivir porque
  revivir es sacar el estado de muerto y los estados no existen. Son 12 de las 22 medicinas del
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

Entraron el 2026-09-13, y lo que las destrabó no fue la pantalla: fue leer el
`initial_level` del LDB en vez de mockear el nivel en 1. Con los niveles de
verdad —Kersh 20, Core y Manta 15— los tres saben las suyas desde la primera
pelea: siete entre los tres, 131 y 146 Kersh, 129 y 150 Core, y 130, 143, 144 y
150 Manta.

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

taro pidió las dos cosas el 2026-09-13 —*"La batalla no tiene ni imagen de
fondo ni imagen del monstruo"*— y acá van juntas **porque son el mismo
dibujo**: el conversor compone el fondo de batalla con los battlers de la
tropa encima y el cartucho lleva el resultado como una capa de 8bpp de
256x128, los siete renglones de texto de arriba. La consola no dibuja
battlers: sube una imagen. El porqué largo, el presupuesto y lo que se pierde
están en `tools/escena.py`; el titular:

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
* **Entra sin pelearle a nada** porque la pelea no comparte VRAM con el mapa:
  `volver_al_mapa` la rehace entera al salir. El texto vive en $2000, su
  tilemap en $3C00, el de la escena en $3800 y los tiles de la escena en
  $4000, que son las últimas 16.384 palabras de la VRAM.

Dos cosas que costaron y conviene no volver a descubrir:

* **El texto lleva el bit de prioridad.** En modo 3 el orden del PPU deja BG1
  de prioridad 0 **arriba** de BG2 de prioridad 0, así que sin eso la escena
  tapa las letras. Lo pone el conversor en `item_glifo_celdas`; en las otras
  pantallas que usan esos glifos —ítems, equipo, tienda— BG1 está apagado y el
  bit no cambia un pixel.
* **El tile con que se tapa lo que queda abajo de la escena es el 512**, y cae
  fuera del bloque: 512 tiles de 8bpp son exactamente las palabras que van de
  `ESCENA_VRAM` al final de la VRAM, así que el 512 da la vuelta y queda en la
  palabra 0, que mientras dura la pelea es VRAM del mapa y no la usa nadie.

**Lo que cuesta, declarado**: un enemigo muerto se sigue viendo. En RM2k
desaparece; acá lo que dice que murió es su renglón —el nombre en gris y los
HP en cero—, que es la misma razón por la que esta pantalla muestra los HP de
los enemigos y RM2k no. Y una escena es **por tropa** y no por fondo: dos
tropas con el mismo fondo llevan las dos escenas, a 32 KB cada una.

Lo cobra la tanda, con los dos fondos del juego: `snes-batalla` con la tropa
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

#### La música y los efectos de la pelea

Desde el 2026-09-13. Todo sale del LDB —`system.json`— y **quién suena en qué
momento sale de easyrpg-player**, no de memoria: está escrito con su función de
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
  mientras no se pelee: `op_batalla` carga `BA_PAQUETE` al entrar y el del
  mapa al salir. Cuesta **65 cuadros medidos** de imagen congelada al volver,
  y otro tanto al entrar; es el mismo precio que paga cada cambio de mapa, con
  la diferencia de que allá lo tapa un fundido.

Lo que lo cobra es `pruebas/test_batalla.py`, y **no la tanda de pixeles**: el
silencio no cambia un pixel, que es el mismo argumento de
`test_musica_paquete.py`. Son cuatro casos —el tema al entrar con sus muestras
en la ARAM, el de victoria, el del mapa al volver, y cuál de los cinco efectos
sale en cada golpe— y los cuatro están verificados en rojo con su defecto
puesto.

Y de ahí salió un defecto que no era del audio: **el banco de datos de
`op_batalla` no es el 0**, así que `music_apagada` y `tema_actual`, que son
absolutos de la BSS, se leían del banco del cartucho donde vive la página. Es
la misma trampa que ya tenían los puentes `ba_t_*` del otro lado.

### La lluvia

`WeatherEffects` dibuja la lluvia desde el 2026-09-11 —la apertura llueve,
primero débil y después media—. Hasta ahí se aceptaba sin hacer nada porque
era lo único que trababa la cinemática. Compila a `OP_CLIMA` con el tipo y la
fuerza, y la regla es la de `Game_Screen::UpdateRain`: cada gota vive doce
cuadros, baja cuatro pixeles y corre uno a la izquierda por cuadro, y una
apagada nace con un diez por ciento de chance en un lugar al azar.

**La lluvia va pegada al mapa**, como en RM2k, desde el 2026-09-11: antes iba
pegada a la pantalla, y taro lo vio al caminar. En RPG_RT las gotas viven en
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

En la consola cada gota son dos objetos de 8x8 con prioridad 2, al final de
la OAM: pasan por delante de la capa de encima, cualquier personaje las tapa
—en la consola gana el objeto de índice más bajo—, y la ventana de mensaje las
tapa con la misma máscara que a los eventos "above". El tono de pantalla las
tiñe, como a todo, porque sus colores van en una paleta de personaje. Sus
seis tiles y sus tres colores se reservan como los dígitos del cronómetro, y
**un mapa sin lugar en las paletas de sprite no dibuja lluvia**: la ROM lleva
`M_LLUVIA_BASE` en cero y la referencia lo sabe con la misma cuenta,
`lluvia_cabe`. En la demo pasa en los mapas 2, 8 y 10, que no la usan. La
nieve, la niebla y la arena no se dibujan y apagan la lluvia; el clima no
viaja en la partida.

En OAM las gotas no pasan por `emit_object`: la X queda siempre entre 0 y
255, así que `lluvia_oam` las escribe directo, y de la Y descarta lo que cae
entre 224 y 247 —de 248 en adelante el PPU lo dibuja asomando por arriba—.
Con eso y el direccionamiento largo en vez de la ventana de WMADD, la lluvia
fuerte bajó de 58 a 24 líneas en `lluvia_tick` y `build_oam` de 130 a 84.

Lo cobran `pan-lluvia` y `sacudir-lluvia` en la tanda, que corren la cámara
con lluvia fuerte por la página de prueba (`--lluvia-de-prueba`): en la
apertura la cámara no se mueve, así que ella sola no miraba el scroll de las
gotas. `pan-lluvia` encontró además un error de la referencia: entre dos
gotas encimadas pintaba arriba la última, y en el PPU gana la de índice más
bajo de OAM.

Costó un detalle de la referencia: el lazo con presupuesto cortaba cuando la
escena se quedaba quieta, y la lluvia no se aquieta nunca. Al final de la
apertura la referencia dibujaba las gotas de 26 ticks antes; ahora las gotas
sostienen el lazo, como el cronómetro. Lo encontró la comparación de la
secuencia de estados de la lluvia de los dos lados, actualización por
actualización: las primeras 2626 eran idénticas. Lo cobra `apertura` en la
tanda, que desde ahora compara con lluvia.

### Los efectos de sonido

`PlaySound` suena desde el 2026-09-11. Compila a `OP_SONIDO` con el índice del
efecto en `sonido_tabla`, que lleva por efecto la muestra, la altura, el
volumen de cada lado y cuántos cuadros dura: el tempo de RM2k estira la altura
y la duración, y el paneo baja el lado contrario.

Tres decisiones, las tres por la ARAM:

* **Van por mapa**, desde la noche del 2026-09-11: ver "El paquete de audio de
  cada mapa", más abajo. Hasta ahí se quedaban con lo que la música dejaba
  libre, y de los 38 que pide la demo entraban 5.
* **A 6 kHz y a lo sumo tres cuartos de segundo** —era uno hasta el paquete,
  que tiene que subirlos en el fundido de cada salto—. Uno más largo repite sus últimos 0,4 s
  hasta durar lo que dura en RM2k: la lluvia de la apertura son cinco segundos
  de ruido y así se la oye entera.
* **El efecto le roba la voz 7 a la música**, que es de percusión. La ROM
  guarda una sombra de los registros de esa voz que la música escribe
  (`dsp_musica`), y al terminar el efecto la devuelve tal cual; mientras suena,
  la música no la toca.

La tanda no mide audio: compara imágenes, y `OP_SONIDO` no cuesta tiempo en
la referencia. Lo que se corrió fue una grabación de la apertura de
`demo-ciudad` con el núcleo de libretro, contra la misma ROM con el volumen de
los efectos en cero: los disparos caen en los cuadros 191, 433 y 576, y en el
hueco entre el fin del tercero y el siguiente (cuadros 890 a 920) las dos
salidas son idénticas muestra por muestra. Es decir, la música vuelve entera.
Si suenan bien lo dice el oído de taro.

`play_sound_effect` en las rutas sigue aceptándose sin hacerse.

### El paquete de audio de cada mapa

La ARAM son 64 KB, y los instrumentos de los ocho temas de la demo son 53: los
efectos que piden el Linkage Block y el Emitter Room —43 y 55 KB— no entraban
ni cerca. taro eligió, el 2026-09-11, un paquete por mapa: al cargar uno, se
suben **los temas que sus páginas pueden prender y los efectos que piden**, en
el orden en que aparecen, que es la prioridad si no entran todos. Cada tema
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
mapa de siempre: unas siete décimas de segundo de negro más. El bucle de subida
del 65816 lee la terna que sigue mientras el SPC700 guarda la anterior, y
nunca una de más: pasado el final de un bloque puede haber registros que se
alteran al leerlos.

Cómo se verificó, porque la tanda no mide audio: la ARAM se lee del estado
guardado del core —`retro_serialize`, ubicando el driver—, y cada muestra que
la ROM dice tener se compara con la del cartucho byte por byte, con su entrada
del directorio. Así se revisó el arranque, la apertura entera y un salto del
mapa 1 al Emitter Room con el tema del mapa 1 sonando —provocado escribiendo
el pedido de fundido en la WRAM—: todas bien, y la música sin cortarse. Contra
la ROM anterior, alineadas en el primer sonido, la salida es idéntica muestra
por muestra durante tres segundos y difiere desde la primera nota de la voz 0,
con las muestras y los disparos iguales en los dos lados; la sospecha es el
instante en que cae ese KON dentro del cuadro, que no quedó demostrada.

Y desde el 2026-09-12 hay una prueba de estado que lo cobra sola,
`pruebas/test_musica_paquete.py`: para el tema que la ROM dice estar tocando,
que cada muestra de su `tema_muestras` tenga entrada en `FAR_ARAM_DE`. Nació de
un defecto que **la tanda no podía ver** —el silencio no cambia un pixel— y que
encima el MSU-1 tapaba: `tema_asegurar` miraba la Z que le dejaba el `plx` en
vez de la del `lda`, así que contestaba siempre "están todas" y no subía nada.
El tema de la pantalla de título es el único que ningún paquete trae —sale de
`title_music` del LDB y los paquetes se arman con los `PlayBGM` de cada mapa—,
así que era el único que dependía por entero de ese camino, y estuvo mudo un
día.

### El MSU-1

La música sintetizada suena fea, y taro lo dijo el 2026-09-11 escuchándola: los
ocho temas de la demo comparten 53 KB de ARAM, así que cada instrumento es una
muestra corta y recortada. El **MSU-1** es la salida: no es hardware de la
consola sino una extensión que soportan el FX Pak Pro y los emuladores, con la
música en archivos PCM al lado de la ROM. El tema sale de un archivo de 44,1
kHz estéreo en vez de las ocho voces del SPC700.

Lo usan **los ocho temas de las demos**: `PISTAS_MSU` en `snes_music.py` dice
cuáles tienen pista y con qué número, y el conversor emite `tema_msu`, un byte
por tema —`$FF` el que no tiene—. Los del juego entero son 43, noventa y un
minutos, 923 MB de PCM; entran el día que haya una ROM que los toque.

Cómo funciona, del lado de la ROM:

* **La firma se mira una vez, en el reset** (`msu_detectar`): "S-MSU1" en
  `$2002..$2007`. Si no está —o sea, siempre que no haya MSU-1— `MSU_HAY` queda
  en cero y **nada más del sistema se enciende**: la música sigue saliendo del
  SPC700 como antes de todo esto. Esa es la propiedad que importa, porque la
  ROM tiene que andar igual en una consola sin tarjeta preparada.
* **`PlayBGM` prueba primero con la pista** (`msu_arrancar`): escribe el número,
  espera a que deje de estar cargando, y si el MSU-1 dice que la pista no está
  en la tarjeta se vuelve sin hacer nada y suena el SPC700. Con pista, en
  cambio, el SPC700 **se calla**: `music_apagada` y un `KOF` de las ocho voces.
  Los efectos de sonido siguen en el SPC700, así que la ARAM les queda libre.
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
  DSP mudo, que es lo que taro escuchó: música por MSU-1 y **ningún efecto**.
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
  en el registro y no en las pistas: normalizarlas más abajo serían 195 MB a
  rehacer por ROM, y perdería la referencia de nivel entre un tema y otro.
  El fundido escala contra ese techo y no contra 255, o su primer cuadro
  **subiría** la música antes de bajarla.

Y del lado del cartucho, `tools/msu.py` (receta `snes-msu`): renderiza el MIDI
con fluidsynth y **con el mismo soundfont con el que el juego sonaba en la PC**
—el que ya usa `snes_samples.py` para sacar las muestras—, así que no cambia el
arreglo: cambia que no haya que reducirlo a ocho voces. La pista es "MSU1", el
punto de loop en muestras, y el audio crudo.

Dos cosas que costaron:

* **La pista salía a un cuarto del volumen de la música del SPC700** —pico 4632
  contra 17012— y el cambio de un tema al otro daba un salto. fluidsynth se
  corre bajo, en 0,6, porque con 1,0 los temas de muchas voces saturan, y
  después la pista **se normaliza** a 0,97 de la escala.
* **`ldx f:MSU_HAY` leía el byte de al lado.** Es la trampa de siempre de este
  repo con los índices de 16 bits; acá el efecto era que el MSU-1 parecía estar
  sin estar.
* **Y la ROM se quedó muda sin archivos de MSU-1**, que es el caso que tiene
  que andar. `tema_asegurar` vuelve con `$FF` en el acumulador, y al llamarlo
  después de sacar el tema de la pila el tema quedaba en `$FF`: el puntero del
  stream se iba de su tabla y la música moría a los diez cuadros. El tema ahora
  se queda en la pila mientras dura esa llamada.

Cómo se verificó, porque la tanda no escucha: primero el protocolo solo, con
una ROM mínima aparte que pide la pista y deja los registros en la RAM —la
firma, el estado antes y después, y cuántas vueltas tardó en cargar—. Y después
la ROM de verdad, corriendo 1800 cuadros con el núcleo de libretro y grabando
la salida:

**Y para los efectos de sonido hay que aislarlos, porque la música los tapa.**
La forma que sirve es la misma ROM con los dos bytes de volumen de cada fila de
`sonido_tabla` puestos en cero, y comparar las dos salidas muestra por muestra:
lo que difiere **son** los efectos. Con pista, y con el prólogo del DSP puesto,
difieren 714382 muestras de 1027098 desde el cuadro 212; con el prólogo
deshabilitado —un `$FF` en el primer byte de `dsp_init_reg`, que es exactamente
la ROM de antes— difieren **cero**. Ese par es lo que prueba que el arreglo es
lo que los hace sonar, y no el emulador.

Y queda escrito el intento que no servía, porque es la trampa que este repo ya
conoce: la primera medición ponía `SE_CUADROS` en cero desde el arnés para
"suprimir" el efecto, y daba cero diferencias **también sin MSU-1**, donde los
efectos se oyen perfectamente. No suprimía nada —la voz ya había arrancado en
el KON de ese cuadro—, así que los dos lados salían iguales por la misma razón
equivocada. Un control por el camino conocido es lo que lo delató; sin él,
habría "verificado" un arreglo sin evidencia.

* **el nivel**: picos de 17096 a 20118 en las ventanas de 300 cuadros, contra
  los 17012 de la música del SPC700;
* **que suene esa pista y no otra cosa**: la envolvente de energía del audio
  grabado contra la del WAV renderizado da una correlación de **0,927 con cero
  desfase**;
* **el fundido**: pinchando el pedido de `FadeOutBGM`, la pista se corta a los
  84 cuadros y el pico baja 19059 → 3464 → 0.

Y la tanda entera —123 casos— sigue en verde **sin** los archivos de MSU-1, que
es el camino que recorre cualquier prueba de acá.

Lo que falta: el punto de loop. El MSU-1 vuelve al principio del archivo, así
que un tema con introducción la repite cada vuelta; hoy los ocho loopean
enteros. Y los 35 temas que las demos no tocan.

Lo que pesa: los ocho son 195 MB por ROM, de 62 a 215 segundos cada uno. La
normalización se nota acá —`lufsorr` sube 1,35 y `cd4` baja a 0,97—, que es lo
que evita el salto de volumen al cambiar de tema.

### Las animaciones de batalla: el sonido y la luz

`ShowBattleAnimation` se aceptaba sin hacer. Desde el 2026-09-11 hace **todo
menos el dibujo**: sus efectos de sonido y sus destellos, en el cuadro en que
RM2k los pone. Son once en la intro —tres en el Linkage Block, ocho en el
Emitter Room, todas de fuego— y sin ellas esas escenas eran silencio y nada.

Compila a `OP_ANIMACION` con la línea de tiempo adentro: por cada `timing` de
la animación, en el cuadro par `2 * (frame - 1)`, su efecto y su destello, de
la pantalla o del evento objetivo. Hay una sola a la vez, como en
`Game_Screen::ShowBattleAnimation`, y avanza una vez por cuadro antes que los
destellos (`animacion_tick`, `Estado.cuadro_de_animacion`). Con "esperar", la
página espera lo que dura. Tres cosas son nuestras:

* **El destello es un `FlashScreen` o un `FlashSprite`** que arranca en la
  fuerza que RM2k le da al primer cuadro y baja lineal en diez; allá baja a
  escalones. Diez, y par a propósito: el destello de pantalla trabaja en dos
  fases según la paridad de lo que le queda, y con once arrancaba por la que
  ninguna página del juego toma, donde la ROM y la referencia no coinciden.
* **Al héroe no se lo destella.** Con quién comparte paleta depende del grupo,
  que el compilador no ve; para los `FlashSprite` el conversor lo mira y corta
  la ROM entera, y una animación no vale eso. Tampoco a un evento que comparta
  gráfico con otro.
* **El dibujo no está.** Son celdas de 96x96 con zoom de hasta el doble y su
  propia paleta; es el sistema de al lado, y está abajo.

Lo cobra `animacion` en la tanda —la 82 sobre el héroe, que destella la
pantalla—, por la página de prueba (`--animacion-de-prueba`): la escena del
Emitter Room no se puede disparar desde una prueba. Los efectos los cobra el
paquete de audio de cada mapa, que los cuenta como uno más.

### El dibujo de las animaciones de batalla

Desde el 2026-09-12 también se dibujan. El sistema entero está en
`tools/animacion.py`, que es el único lugar donde se decide dónde cae y de qué
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

taro aceptó el precio el 2026-09-12 —*"deberíamos poder lograrlo si reducimos
el tamaño de algunos de los efectos"*— y es lo que hace que las grandes
existan: al 11% la 82 es un brillo y no un incendio, pero está, y la alternativa
medida era que no estuviera.

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
  personajes más y no más, y la referencia declara las líneas donde no alcanza,
  como con cualquier otro sprite.

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
para que los dos lados eligieran distinto —la referencia compila los mapas en
un orden que depende de si la ROM lleva ventana— y eso no se vería como un
cartel equivocado sino como dos streams de bytecode distintos.

**Y el estado vive en la RAM lejana**, quince bytes en `$7E30E8`, al lado del
de la animación de batalla. No es elegante: es que en el banco 0 no entraba
—la BSS estaba en 7680 de 7680— y esto se lee y se escribe unas pocas veces por
cuadro, así que el direccionamiento largo no se nota.

Lo cobra `snes-cinematica 4 7 ... cartel` en `rom/hitos.txt`: cinco cuadros
contra la referencia, **los cinco en cero**. El de la mitad de cada rampa no es
adorno: es el único que ejercita la interpolación cuadro a cuadro, que es donde
la ROM y la referencia pueden separarse en un valor sin que se vea.

Un rojo que costó y queda escrito: **`armar_paleta` usa Y de cursor** y la deja
en 32, y quien la llama desde un opcode la tiene apuntando al bytecode. Sin un
`phy` el intérprete seguía leyendo treinta y dos bytes más adelante y corría lo
que hubiera ahí. No se veía como un cartel roto: se veía como que la página
seguía, sólo que otra.

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
desde donde estén con un puntero de 24 bits, o sea `lda [ptr],y`, que fue lo que
obligó a agregarle direccionamiento indirecto indexado a `w65.py`. Buscando
dónde meterlo apareció que `lda [ptr],y` se ensamblaba como `lda [ptr]` sin
avisar: el sufijo se separaba y la rama de los corchetes lo descartaba.

La de NPCs es la excepción y se copia a la RAM: `build_oam` la recorre con un
índice y en cinco desplazamientos distintos, así que con un puntero saldría el
triple de instrucciones en el lazo que se ejecuta 128 veces por cuadro. Copiarla
cuesta un lazo por carga de mapa y entran 127, que es el tope que impone OAM; el
mapa con más NPCs del juego tiene 89.

#### Las puertas

De los 959 teletransportes del juego, **265 son puertas**: una página cuyo único
trabajo es mudarte, sin variables ni condiciones ni diálogo. De ésas, 263 se
disparan con "toca el héroe" y son las que la ROM usa. Se pueden hacer sin
intérprete de eventos, y son las que convierten un mapa suelto en un mundo.

Las otras 694 están adentro de cinemáticas y piden el intérprete.

**A qué mapa lleva, en dos bytes.** Tanto `OP_TELEPORT` como el registro de una
puerta guardaban el índice del mapa destino en **un byte**, y eso le ponía al
formato un techo de 256 mapas cuando el juego tiene 328. Las demos llevan 29,
así que no molestaba; se sacó igual, porque un techo escrito en el formato sale
más barato ahora que el día que una demo se pase. Adentro de la ROM el índice
viaja de dieciséis bits desde `salto_mapa` hasta `mapa_actual`, y el techo que
queda es el de `mapa_ofs`: 512 mapas, que es lo que entra en un word a
`MAPA_STRIDE` de 128 bytes. Los tres bytes de RAM que costó salieron de tres
declaraciones que no leía nadie —`ev_actual`, `ruta_salto_dx` y
`ruta_salto_dy`—, porque la RAM baja estaba en 7680 de 7680 y la página directa
en 256 de 256. **La partida guardada cambió de tamaño**: una partida vieja no
carga, la suma no le cuadra.

Qué comandos pueden acompañar a un teletransporte sin que deje de ser una
puerta se decide con un criterio, no a ojo: **que no ejecutarlos no se vea en la
pantalla que comparamos**. Un fundido, una espera y un sonido se saltean y la
imagen final es la misma; un cambio de música o del gráfico del héroe, no.

La primera versión de esa lista puso los códigos de memoria y tres estaban mal.
Dos de los que creía inofensivos eran `PlayBGM` y `ChangeSpriteAssociation`, así
que el filtro aceptaba como puertas eventos que cambian la música y el sprite
del héroe. **La comparación no puede ver ese error**, porque la referencia usa
la misma lista: las dos partes coinciden en hacer lo mismo mal. Los códigos
salen de `tools/event_codes.py`, que se genera desde liblcf, y de ningún otro
lado.

La ROM mira la tabla de puertas al **terminar** el paso, no al empezarlo, que es
lo que hace RM2k: el evento se dispara cuando el héroe ocupa la celda. Si hay
puerta, se apaga la pantalla, se carga el mapa entero y se lo deja donde la
puerta dice. RM2k también funde a negro al cruzar, así que el parpadeo no
desentona.

Una puerta a un mapa que no entró en el cartucho se descarta en la conversión.
En la consola sería un salto al vacío, y es mejor que no haga nada a que haga
cualquier cosa; el conversor dice cuántas quedaron afuera.

Lo mismo vale para las **páginas** que teletransportan, sólo que ahí no se
descarta el salto sino la página entera: `compilar_pagina` corta con
`NoSePuede`, la página se queda sin código y el evento no hace nada —ni el
salto, ni lo que venía antes—. Desde el 2026-09-05 el conversor también lo
dice, con los mapas que faltan nombrados, porque el conteo de "N ejecutables"
no distinguía esta razón de las otras veinte y ésta es la única que se arregla
desde afuera, sumando el mapa. Ver "El ascensor no llevaba a ningún lado".

#### El fundido de los teletransportes

RM2k funde a negro y vuelve en **cada** teletransporte, cambie de mapa o no.
Sale de easyrpg-player: `Scene_Map::UpdateStage2` arma el `TeleportParams` con
`erase_screen = true` siempre, `StartPendingTeleport` pide la transición que
diga la base —la de A Blurred Line es `transition_out = 0` y `transition_in =
0`, o sea `TransitionFadeOut` y `TransitionFadeIn`— y `GetDefaultFrames` les da
**35 cuadros a cada una**. Mientras la transición corre, el juego está
congelado: `Scene::MainFunction` ve `IsAsyncPending()` y llama a
`Player::Update(false)`, que no actualiza la escena.

Así que son 70 cuadros por salto, y en esos 70 no pasa nada más que el brillo.
La ROM hace lo mismo por omisión: `fundido_tick` devuelve "congelado" y el lazo
principal se saltea el intérprete, al héroe, los eventos, el cronómetro, la
sacudida y `build_oam`. Lo único que sigue es la música, que en RM2k tampoco se
corta.

**El brillo es el maestro de INIDISP, y son dieciséis pasos.** No hay otra
manera barata: fundir por CGRAM es lo que hace el tinte, y `aplicar_tinte` sola
ya cuesta un cuadro entero. Con dieciséis pasos, estirar la rampa sobre los 35
cuadros no da un fundido más fino, sólo repite pasos —así que la rampa son 24 y
los 11 que quedan son negro liso—. La cuenta del PPU es
`round(canal * brillo / 15)` sobre los cinco bits, que es la tabla que arma
`PPU::PPU()` en bsnes, y la referencia la repite en `eventos.oscurecer`.

**Los 11 cuadros de negro no son relleno: ahí se carga el mapa.** Es la parte
que arregla un problema viejo. La carga escribe VRAM y CGRAM por DMA y cuesta
seis o siete cuadros que la referencia no modela, y hasta ahora eso dejaba a
los dos lados desalineados desde el salto en adelante —está contado en "Cómo se
verifica"—. El fundido se cuenta en **cuadros de hardware** y no en vueltas del
lazo: `fundido_tick` hace `boot_cuadros - fundido_base`, así que la carga se
come cuadros del negro y el fundido igual mide 70. Entre el cuadro 24, que es
donde carga, y el 47, que es donde la rampa de vuelta sale del cero, hay 23
cuadros de margen para una carga que tarda siete.

De ahí salieron dos cosas más, las dos verificadas contra la referencia:

* **OAM se rearma al cargar.** El lazo no la arma mientras el fundido dura, así
  que la rampa de vuelta iba dibujando el mapa nuevo con los sprites del
  viejo. Son los 1031 pixeles que la referencia cobró la primera vez que se
  comparó adentro de un fundido; `cargar_lo_pedido` llama a `build_oam`.
* **La rampa la emite el conversor**, en `mapdata.inc`, desde
  `eventos.rampa_de_fundido()`. Escribirla también en `main.s` sería la
  duplicación de siempre: dos lados que se pueden equivocar igual.

**Los tres cores dejaron de coincidir acá, y es la primera vez.** snes9x y
bsnes dan exactamente `round(canal * brillo / 15)`; **mesen-s trunca** en vez
de redondear, y con brillo 6 un canal de 7 le da 2 donde los otros dan 3.
Seguimos a bsnes, que es de donde sale la tabla y el que mide contra hardware,
y a snes9x, que es el core de la tanda. Ninguna receta usa mesen-s. Lo
desempata la SNES de taro.

**Lo que esto cambió de la tanda.** Los cuadros comparados de `snes-cinematica`
se corrieron 70 por cada teletransporte anterior —la cinemática tiene tres— y
los quince toques de A de `apertura` también. `snes-puerta` no cambió de
números porque el plan de la caminata ahora cuenta el fundido: 142 cuadros en
vez de 72, y la pantalla queda quieta exactamente en el 142.

**Cómo se verifica.** Los cuadros **50 y 68 de `snes-cinematica`** caen adentro
de la rampa de vuelta del primer fundido, con el mapa 1 subiendo de brillo, y
dan cero: son lo único de la tanda que compara la rampa misma. Que aguanten es
el diseño funcionando —esa ROM pierde siete cuadros en la carga y el brillo del
cuadro N sigue siendo el mismo, porque se cuenta en cuadros de hardware—. Los
otros cuatro cuadros del caso, y los seis de `apertura` con sus quince toques,
verifican que el fundido dura exactamente 70 y que el juego queda congelado
adentro: si durara otra cosa, todos correrían de lugar.

A mano, y contra el PPU en vez de contra la referencia: se capturó cuadro por
cuadro el fundido de `snes-puerta 30 28 down` y se buscó, para cada uno, qué
brillo de `eventos.oscurecer` lleva el cuadro quieto al capturado. **Los 27
cuadros de la rampa de vuelta dan cero pixeles**, y la secuencia de brillos es
la rampa emitida, corrida un cuadro —el mismo cuadro de retraso que tiene OAM,
porque `brillo` se escribe en el vblank siguiente—.

Y la escena del ascensor, que es lo que motivó todo esto, ahora compara: el
héroe entra, el fundido corre, y los cuadros 20 y 40 dan cero contra la
referencia. Lo que le sigue faltando para tener caso propio en la tanda está en
"Lo que falta".

#### La cola de páginas no era circular

Las páginas que un evento dispara van a una cola de ocho —`cola`, con `cola_n`
para las que entraron y `cola_i` para las que salieron— y el lazo las come de a
una. **`cola_n` nunca volvía a bajar**, así que no era un anillo sino un buffer
que se llena una sola vez por visita al mapa: llegado a ocho, `encolar_elegida`
descartaba todo y el mapa se quedaba sin disparar nada —ni una puerta, ni un
cartel—.

El comentario que estaba puesto decía "ningún mapa del juego llega a ocho
páginas automáticas", y es cierto **al cargar**. Lo que no vio es que la misma
cola atiende todos los disparos de la visita: cada tecla de acción, cada
contacto. Una cinemática larga deja el contador cerca del tope y después el
mapa acepta una interacción y ni una más.

Se arregla poniendo los dos punteros en cero cuando la cola queda vacía, que es
lo que la vuelve circular de verdad. Medido con dieciocho toques de A sobre el
mismo evento: antes `cola_n` llegaba a 8 y se quedaba ahí, ahora el pico es 2.

Lo encontró taro jugando, y la firma fue lo que lo delató: **"me deja
interactuar una vez y después nada"**. Salir del mapa y volver lo arreglaba
porque `encolar_eventos` pone los punteros en cero.

#### La página automática vacía congelaba el mapa

En RM2k una página sin un solo comando **no arranca el intérprete**:
`Game_Interpreter::Push` vuelve en seguida cuando la lista viene vacía, así que
el intérprete no queda corriendo y el jugador camina. Acá esa página se volvía
la activa, se ejecutaba en un tick, terminaba, y como una automática se repite
mientras siga siendo la activa, volvía a arrancar en el tick siguiente. El mapa
quedaba congelado para siempre.

No es un caso raro: **es el idioma con el que RM2k desactiva un evento**. Una
página de abajo prende el switch que activa una de arriba, y ésa está vacía y
sin gráfico. Medido sobre los 328 mapas: **45 páginas en 35 mapas**, y en Rat
Tracks B1 son dos que se vuelven activas en el primer cuadro, o sea que el mapa
era injugable.

Lo delató el caso nuevo `snes-heroe 21` **tardando catorce minutos**: la
referencia se comía los 100.000 ticks de `correr_automaticos` antes de empezar a
caminar y el emulador después corría esos 100.000 cuadros por dirección. Con el
arreglo son nueve ticks. Y es un buen ejemplo de la forma de falla que este repo
persigue: los dos lados hacían lo mismo, así que la comparación daba cero; lo
único que gritaba era el reloj.

El arreglo es una línea en el filtro de páginas —una automática o paralela sin
comandos se emite con el código en `None`—, y lo miran los dos lados por el
mismo lado, que es lo que ya consultaban para decidir si una automática cuenta:
`eventos_auto` en la referencia y el bit 7 de la página en el conversor.

#### El presupuesto de saltos se drenaba solo

Hay un tope de ocho teletransportes encadenados —`saltos_restantes`— para que
dos mapas que se apunten entre sí no cuelguen la ROM. Se reponía en
`cargar_mapa` y se cobraba en **todo** salto, y ahí estaba el error: **un salto
al mismo mapa no llama a `cargar_mapa`** —a propósito, para no reencolar los
eventos automáticos— así que gastaba presupuesto y no lo reponía nunca.

La escena de Talan salta tres veces adentro del mapa 3 y la apertura dos adentro
del 1. Después de ocho, **todo teletransporte se descartaba en silencio**: las
puertas se abren y no llevan a ningún lado. taro lo vio como algo que "a veces
pasa y a veces no", y lo era: dependía de cuántos saltos llevara esa partida.

Encima el tope fallaba **una sola vez**. Era `dec` y después `beq`, así que con
el contador en cero el byte daba la vuelta a 255 y los siguientes doscientos
cincuenta y cinco saltos pasaban. De ahí que salir del mapa y volver a entrar lo
"arreglara": ese salto era el que daba la vuelta.

Ahora se cobra sólo al cambiar de mapa, que es lo que hace la referencia
—`saltos` es local a `entrar_al_mapa` y sólo lo baja el lazo que entra a un mapa
nuevo—, y se mira antes de bajarlo.

Queda una asimetría anotada: la ROM repone en cada `cargar_mapa` y la referencia
sólo al entrar desde afuera de la cadena, así que un ping-pong A→B→A agotaría el
tope de un lado y no del otro. **Con los datos de este juego no puede pasar** y
está medido —un solo mapa teletransporta al entrar, la cadena más larga es de un
salto y no hay ciclos—, pero si alguna vez aparece uno, es acá.

**Cómo se encontró.** No lo encontró la tanda: lo encontró taro jugando, y lo
cerró un volcado de memoria de mesen. Con el `.sym` del build —el dump del PRG
coincidía byte a byte con la ROM— se leyó `saltos_restantes = 0` en la WRAM, y
de ahí salió todo. Vale la pena recordar el camino: **un dump de memoria más el
`.sym` contesta en un minuto lo que a ojo son horas.**

#### El cuadro que el fundido regalaba al terminar

Un teletransporte congela el juego setenta cuadros. Los dos lados contaban
setenta, y la referencia gastaba **uno más**: el cuadro en que el contador llega
al final lo consumía sin hacer nada, mientras que en la ROM `fundido_tick`
devuelve cero y el lazo sigue con `eventos_tick`, `move_hero` y todo lo demás.

Es la misma trampa que ya se había arreglado del lado de la ida —ahí está
escrito "el cuadro **sigue**: la ROM pide el fundido desde `eventos_tick` y
después corre `move_hero` igual"— y había quedado sin arreglar del lado de la
vuelta.

No lo cobraba ninguna prueba porque los casos de teletransporte comparan el
cuadro final, cuando ya se acomodó todo. Lo destapó la escena de Talan, que
empieza teletransportándose adentro del mapa y sigue caminando al héroe: un
cuadro de más son **dos pixeles**, la cámara lo sigue, y con la cámara corrida
difiere media pantalla. De ahí el 60% del cuadro 120 contra ceros a los dos
lados.

#### La pantalla se prende en el vblank, no donde se carga el mapa

Cargar un mapa apaga la pantalla: `cargar_mapa` escribe VRAM y CGRAM por DMA y
con el PPU dibujando esas escrituras se pierden. Prenderla de vuelta, en
cambio, **no** se hace ahí. **`INIDISP` lo escribe únicamente `flush_video`**,
al final del vblank, desde la variable `brillo`; quien quiera cambiar el brillo
la escribe y espera al vblank siguiente, igual que quien mueve un sprite
escribe OAM y espera. La única excepción es el blanking forzado de una carga,
que `fundido_tick` escribe a mano porque ahí la pantalla ya está en negro.

El motivo son dos defectos que se veían en todos los teletransportes, y que
taro reportó por separado sin saber que eran el mismo:

* medio cuadro dibujado desde el borde de abajo, "como si el mapa estuviera
  cargando", y en un lugar distinto cada vez;
* un cuadro entero de basura —él lo describió como un flash del cuarto
  anterior— antes de que apareciera el mapa nuevo.

Los dos salen de dónde caía el `INIDISP = $0F`. La carga tarda seis o siete
cuadros de CPU, así que terminaba **a mitad de un cuadro**: lo que el haz
todavía no había pintado se pintaba, y eso es la franja de abajo. Y lo que
pintaba estaba mal, porque el scroll y OAM los escribe `flush_video` y sólo en
el vblank: al volver de `cargar_mapa` los registros del PPU siguen apuntando a
donde miraba la cámara antes del salto y OAM sigue siendo la del mapa anterior.
El tilemap nuevo leído con el scroll viejo no es el cuarto viejo ni el nuevo:
es la ventana de 64x32 leída con el corrimiento equivocado.

Prendiéndola en `flush_video` el primer cuadro que se ve ya tiene el scroll,
OAM y las paletas del mapa nuevo, y empieza donde empieza el cuadro. Cuesta un
cuadro más de negro.

**Cómo se verifica.** Se midió a mano sobre `snes-puerta 30 28 down`,
capturando los cuadros de a uno alrededor del cruce y contando pixeles negros.
Antes: siete cuadros negros, uno con las 22 primeras filas en negro y el resto
dibujado —y ese resto a 47.277 pixeles de 51.712 del cuadro que sigue, o sea
distinto de todo—, y recién después el mapa nuevo. Después: ocho cuadros
negros y el mapa nuevo, con el primer cuadro visible idéntico bit a bit al que
daba antes. Desde que hay fundido esto además lo cubre la tanda de costado: los
cuadros de rampa de `snes-cinematica` sólo dan cero si el brillo cambia entre
cuadros y no a mitad de uno.

#### Pisar un evento, y pisarlo al final de una ruta forzada

El otro disparo por contacto es el general: al terminar un paso, si la celda
tiene un evento cuya página activa se dispara con "toca el héroe", se encola.
Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`, y va **después**
de mirar la tabla de puertas: si hubo puerta el mapa ya cambió y la celda de
llegada no se pisa, igual que en RM2k.

Con una ruta forzada la regla tiene una vuelta, y desde el 2026-09-04 está de
los dos lados. RM2k no mira el contacto mientras `IsMoveRouteOverwritten()`,
pero **el último paso sí cuenta**: un movimiento que es la última orden cancela
la ruta entera antes del chequeo —`Game_Character::UpdateMovement`, comentado
ahí mismo—. Con órdenes por leer, aunque sean giros o esperas, la ruta sigue
puesta y no se mira nada. La ROM tenía la mitad —miraba en todos los pasos— y
la referencia la otra —no miraba en ninguno—, y no se veía porque ninguna
página de contacto compilaba sin ventana. Es lo que deja a la cinemática de
apertura pisar el evento que apaga el tinte: tres celdas para arriba y el
evento en la tercera.

Y si al terminar la ruta hay una página corriendo, el contacto **no se
pierde**: va a la cola detrás de ella, que es lo que hace RM2k con
`ScheduleForegroundExecution`. La ROM lo descartaba con un guard escrito para
el pad, que para el pad sobra porque `move_hero` no arranca un paso con una
página en el frente.

Lo prueba `just snes-ruta-pisa`, en el mapa 70 de `snes-pisar`: la ruta que
termina sobre el evento abre su mensaje, la que pasa por encima y sigue no abre
nada, y la que termina con la página todavía esperando lo abre después del
tinte. Cada caso se rompió a propósito para saber que mira lo que dice: sin el
guard de la ruta el segundo se va a 20470 pixeles, y con el guard viejo del pad
el tercero a 20261.

Lo que no se modela, de ningún lado y con todas las letras: una ruta que
termine **saltando** sobre un evento de contacto —RM2k lo dispara, ni la ROM ni
la referencia lo miran—, una puerta al final de una ruta —la ROM la cruza y la
referencia no la mira—, y un evento disparado dos veces antes de correr, que
entra dos veces en la cola y una sola en RM2k. Ninguna ruta del juego hace
ninguna de las tres.

#### La colisión con los eventos

Desde el 2026-09-05 un evento parado en una celda le cierra el paso a quien
quiera entrar, y el héroe se lo cierra a los eventos. Es `WouldCollide` de
`game_map.cpp` con lo que este repo modela: dos personajes chocan si están en
la **misma capa** —la del héroe es la del medio, `CAPA_HEROE`— y no chocan si
alguno de los dos atraviesa paredes. Un evento sin página activa no está
—`IsActive()`— y no choca con nadie. La celda de cada uno es la de destino
mientras camina, que es `GetX()` en RM2k y `ev_pos_buf` o `tile_x` acá: las
dos se mueven al empezar el paso. Y el salto también mira: aterrizar sobre
alguien es un salto que no sale.

Para saber la capa de la página activa **la tabla de páginas lleva todos los
eventos**, no sólo los que tienen código, y cada página lleva su capa en el
byte +12. Es lo que hace que el droide de la batalla del mapa 2, cuya página
no compila, frene igual. Un evento con una condición que la ROM no evalúa
sigue afuera entero, y tampoco frena: su capa es tan desconocida como su
código.

De los dos lados es la misma pasada: `bloqueada` en eventos.py y
`celda_bloqueada` en main.s recorren los eventos parados en la celda y le
piden la capa a la página activa de cada uno; `movil` y `movil_capa` dicen
quién se está moviendo, para no chocar consigo mismo y para saber si el héroe
le estorba. Cuesta una pasada por la tabla de páginas por cada evento parado
en la celda de destino, o sea nada en la práctica: casi nunca hay uno.

**Cómo se verifica.** El caso `bloqueo` —`snes-pisar 2 "7 76" up 60 30
bloqueo`—: el héroe sube hacia el droide de (7,72) y se frena en (7,73). Y el
`snes-npc` de siempre cambió de resultado sin cambiar de receta: Kersh baja
cuatro celdas desde (22,9) y el héroe está parado en (22,12), así que los dos
pasos que caen ahí se saltean y termina en (24,11), donde antes terminaba en
(24,13). Lo que no se modela está en "Lo que falta".

#### Plantar un evento en una celda

`ChangeEventLocation` es `Game_Character::MoveTo`, y lo que importa es lo que
**no** hace: pone la celda y deja el paso en cero —`SetRemainingStep(0)`—, y
no toca la ruta, que sigue con la orden siguiente desde ahí, ni hacia dónde
mira, que en RM2k sólo lo cambia la variante de RM2k3. El juego lo usa 680
veces con la celda escrita y 129 leyéndola de variables; las segundas no
compilan, como todo lo indirecto. Sale de la cinemática de apertura, que lo
usa seis veces para traer a Core, a Manta y al droide a escena, y destraba
además cinco páginas automáticas, las cinco que decía `snes-destraba`.

En la ROM es `OP_LUGAR`: la celda va a `ev_pos_buf`, que es lo que miran las
rutas, la tecla de acción y el contacto, y el dibujo la sigue de dos maneras.
Un evento con ranura de ruta sólo necesita que se le corte el paso y el salto:
`mover_eventos` lo refresca en el mismo cuadro. Uno sin ranura **no se lleva
una**: su fila de NPC se mueve a mano, sin tocarle el tile —la pose de su
página— y se reacomoda en el orden de dibujado. La referencia hace lo mismo
desde `pos_ev`, que ahora es de donde se dibuja todo NPC, tenga ruta o no.

Lo prueba `just snes-lugar`, en el mapa 6 de `snes-npc`: un evento plantado a
mitad de un paso queda **exactamente** sobre la celda y sigue con los pasos
que le faltaban, y uno sin ruta aparece en otra celda con su pose de siempre.
Los dos se rompieron a propósito: sin el corte del paso el primero da unos 370
pixeles en los tres cuadros del medio, y sin mover la fila el segundo da 511.
Y una trampa que costó una vuelta: la primera versión lo plantaba en una celda
tapada por la capa de encima, y los dos lados lo dibujaban tapado. La prueba
daba cero con el corte sacado, porque no veía al evento.

**Y dos eventos que se cambian de lugar.** `TradeEventLocations` es
`OP_TRUEQUE` desde el 2026-09-05: los dos blancos, y cada uno va con el mismo
`MoveTo` de `OP_LUGAR` a la celda del otro, con las dos celdas leídas antes de
escribir ninguna. Lo usa una sola escena de las que se miran: la puerta de
arriba a la izquierda del mapa 2, donde Manta la vuela y la puerta se cambia
de lugar con el evento 21. Es el caso `puerta-izq` de `snes-escena`.

#### Los eventos dibujados con un tile del chipset

Una página puede no tener CharSet y dibujarse con un tile de la capa de arriba
del chipset: así son las puertas y las pantallas del mapa 2, y 22 de sus 42
eventos. Hasta el 2026-09-05 la ROM no los dibujaba —taro vio la puerta de
arriba a la izquierda como "un portal negro" con el que igual se podía
interactuar— porque `collect_npcs` sólo juntaba los que tenían CharSet.

Ahora son un personaje más, con un CharSet inventado que no existe en disco:
`@tile:<chipset>:<índice>`, que `render_map.Charsets` fabrica desde el atlas
del chipset —el tile `UPPER + índice` puesto en el lugar del sprite de cada
una de las doce poses de un CharSet de 24x32—. Con eso el resto no se entera:
el conversor lo empaqueta y la referencia lo dibuja por el mismo camino que un
CharSet común. El tile 0 es "sin gráfico" y no cuenta.

Lo que sí se entera son **las paletas de sprite**. Un CharSet del juego usa
sus quince colores y no comparte ninguna con otro; un tile usa nueve o diez, y
las puertas del mapa 2 comparten casi todos. Por eso `build_characters`
empaqueta: un personaje cuyos colores caben en una paleta ya armada va ahí,
con la unión, y ningún color se fusiona por esto. Sin eso el mapa 2 pedía nueve
paletas de las ocho. Y donde ni empaquetando alcanza —el mapa 8, siete
personajes de CharSet más dos tiles que no comparten colores— decide
`npcs_dibujables`, que corren **los dos lados con la misma función**: los
CharSets van sí o sí, y los tiles entran en el orden del mapa mientras quepan;
el que no entra no se dibuja y el conversor lo dice. El evento sigue ahí,
cierra el paso y dispara igual. Antes de esto no se dibujaba ninguno, así que
es estrictamente mejor.

Dos cosas salieron de dibujarlos, y las dos las cobró la tanda:

* **La ventana de mensaje no tapaba a los eventos "above".** En RM2k tapa
  todo —`Priority_Window` es 130—, pero acá es BG2 con prioridad 1 y un
  evento "above" va en objetos con prioridad 2, que en el modo 3 queda
  adelante de BG2. Ningún evento con CharSet del juego usa esa capa, así que
  nunca se había visto; el evento 3 del mapa 7, un tile "above" al lado de la
  puerta, apareció a través de la ventana en seis casos. Se arregla con la
  **ventana 1 del PPU** como máscara de objetos, de punta a punta, prendida
  por un tercer canal de HDMA sólo en las líneas de la ventana de mensaje
  —`hdma_mascara`, en `armar_hdma`—, y apagada a mano al cerrar, como
  `BG2SC`. Es exacto: los objetos desaparecen debajo de la ventana y en
  ninguna otra parte.
* **La tabla de páginas cruzaba de banco.** Ver "Las tablas van en el banco
  0".

#### El gráfico sigue a la página, y el tile manda sobre el terreno

Las puertas de este juego no se abren: **cambian de página**. La de seguridad
del mapa 2 es el evento 23 en (83,71), una celda que el chipset dice pared;
su página 1 no dibuja nada y la 2, con el switch 10 que pone el puñetazo de
Core, dibuja el tile 111 —escombros— en la capa de abajo. Y RM2k tiene una
regla para eso, en `Game_Map::IsPassableTile`: **un evento de la capa de
abajo con gráfico de tile reemplaza la pasabilidad del terreno por la de su
tile**, salvo que el tile sea de los que van por encima; de los que haya en
la celda gana el de id más alto, y uno que atraviesa paredes no cuenta. Los
escombros se pisan, así que la pared se pisa. taro lo vio como "la cinemática
va perfecto pero el mapa no cambia": ni el gráfico ni la regla existían de
ningún lado. El ascensor es lo mismo por seis: el evento 30 cambia del tile
25 al 28 y baja de capa con el switch 11, y los 31 a 35 aparecen alrededor.

Desde el 2026-09-05 los dos lados hacen las dos cosas, y con los mismos
datos:

* **`collect_npcs` da una fila por evento con gráfico en alguna página**,
  no sólo en la activa al cargar: la fila existe escondida —`visible`— y
  `cambia` dice si el gráfico sigue a la página activa, que vale sólo para
  eventos cuyas condiciones la ROM entiende, porque sin sus páginas en la
  tabla no hay cómo saber cuál gana. El mapa 2 tiene nueve así, todos tiles
  quietos. **Un evento que camina y cambia de gráfico no se puede**: son dos
  mecanismos sobre la misma fila —las doce poses del cartucho y el gráfico de
  la página— y el conversor corta con el nombre del evento el día que uno lo
  pida.
* **La tabla de páginas lleva lo que dibuja cada página**, +20 a +23: el
  tile, los atributos con la paleta y la prioridad de su capa, la pose con el
  bit 7 si hay gráfico, y los bits de paso de su tile o $FF. Cada
  (CharSet, índice, pose) de esas páginas tiene su ranura en la VRAM desde la
  carga, así que cambiar es copiar. La fila lleva además +14 si se ve y +15
  los bits de paso del tile que muestra ahora.
* **El refresco los copia.** `rutas_de_pagina` ya volvía a mirar la página
  activa de los eventos con rutas propias al cargar y al cambiar un switch;
  ahora mira también los del bit 5 —`grafico_de_pagina`— y copia a la fila
  el gráfico de la página que ganó, o la esconde si ninguna gana o la que
  gana no dibuja. La clave de dibujado toma la capa de la página, y la fila
  se reacomoda con `acomodar_npc` como la de uno que camina: el ascensor
  abierto está en la capa de abajo y el héroe lo pisa. `build_oam` saltea
  las filas escondidas. La referencia dibuja cada fila con el gráfico de su
  página activa, `pagina_activa`, que es la misma pasada.
* **Las paletas se reparten una sola vez.** Con las páginas contando, el
  mapa 8 tiene dos eventos de CharSet que cambian de pose con la página, y
  ésos se llevan paletas antes que los tiles: los eventos 6, 7 y 12 —dos
  puertas y unos escombros— quedan sin dibujar, donde antes era sólo el 12.
  Y `build_characters` ya no reparte por su cuenta: usa el reparto que hizo
  `npcs_dibujables`, porque el mismo primer-lugar-que-entre en otro orden dio
  otra cuenta —ocho paletas acá, nueve allá— y la ROM del mapa 8 no se armaba.
* **Las tres comprobaciones de terreno** —`can_leave` y `can_enter` del
  héroe, `puede_celda` de las rutas— pasan lo que dice el chipset por
  `pasa_con_evento`, que recorre la tabla de NPCs buscando una fila visible
  con +15 puesto parada en esa celda; el último que encuentra gana, que es el
  de id más alto. Es un recorrido por paso y no una pasada por las páginas,
  porque los bits ya los dejó el refresco. La referencia hace lo mismo en
  `pasabilidad_de_evento`, que `puede_pasar` recibe como `pasa_evento`.
  Lo que no se modela: el "conflicto consigo mismo" de un evento de tile que
  camina, que ninguno hace.

**Cómo se verifica.** `escombros`: el héroe en (85,71) camina tres a la
izquierda con el switch 10 y llega a (82,71) pasando por la pared, cuatro
cuadros en cero; `escombros-cerrados`, lo mismo sin el switch, y se queda en
(84,71); `ascensor`, el héroe quieto delante del ascensor con el switch 11,
que lo dibuja abierto; y `core-puerta` desde el cuadro 470 muestra los
escombros apareciendo en la escena de verdad. Y una trampa de la primera
versión, que la tanda cobró: el lazo de dibujo de la referencia pisó la
variable `charset` que el héroe usa después, y el héroe salía dibujado con el
tile de la última puerta.

#### El ascensor no llevaba a ningún lado

El ascensor del mapa 2 se abría, se dejaba pisar, y pisarlo no hacía nada.
taro lo reportó así: "puedo interactuar con la puerta del ascensor, y se abre,
pero entrar al tile del portal no triggerea ningún teleport".

No faltaba nada de la ROM. La página del switch 11 del evento 30 es de
contacto, arranca con un `Teleport` al (77,31) del mismo mapa —el interior de
la cabina— y **termina con otro al mapa 3**, que es a donde lleva el ascensor.
`demo-apertura` tenía los mapas 4, 1 y 2, así que ese último salto no se podía
compilar, y una página que no compila se emite sin código: el evento existe, se
dibuja, se pisa, y no hace nada. Los dos lados coincidían —la referencia compila
con la misma función— así que la tanda daba cero y el caso `ascensor`, que mira
la puerta abierta con el héroe quieto delante, seguía en verde.

El arreglo es de afuera: `demo-apertura` se arma con **`--mapas 1 2 3`**. El
mapa 2 pasa de 40 páginas ejecutables a 41 y el cartucho sigue entrando en los
512 KB. Y para que no se vuelva a callar, el conversor ahora nombra los mapas
que le faltan a las páginas que se caen por eso: ver "Las puertas".

**Cómo se verifica.** No lo cubre `snes-hitos`. La razón cambió el 2026-09-05:
ya no es la carga del mapa —el fundido se la come, ver "El fundido de los
teletransportes"— sino los **picos del lazo**. Esta ROM pierde un cuadro en su
primera vuelta y otro en la vuelta en que el fundido termina y la página
retoma, y con un `ShakeScreen` de mil cuadros moviendo la cámara no hay un solo
cuadro quieto donde ese atraso no se vea. Lo que sí se midió, con una ROM
descartable de los mapas 2 y 3 y el héroe en (71,70) con el switch 11 y un paso
hacia arriba:

* la ROM teletransporta al héroe a (77,31) en el cuadro 9, y la referencia en
  el 9 también;
* corriendo la escena entera —diez mensajes— la ROM termina en el **mapa 3**,
  celda (67,69), y la referencia termina en el mapa 3, celda (67,69);
* los cuadros 20 y 40 —el fundido de la entrada a la cabina— dan **0 pixeles
  de 53.248 y de 57.344** contra la referencia, ya sin desfase;
* más allá del fundido hace falta correr la ROM un cuadro más adelante que la
  referencia por cada cuadro que perdió, y ahí sí dan cero: los cuadros 13, 71,
  83 y 101 de la ROM contra el 12, el 70, el 82 y el 100 de la referencia.

Que la tanda pueda mirar esto sola pide que la ROM deje de perder cuadros en
sus picos, o que la referencia los cobre; está en "Lo que falta".

#### Las rutas propias de las páginas

Desde el 2026-09-05 un evento cuya página activa tiene `move_type` 6 —una ruta
propia, la que camina sola— la camina en la ROM y en la referencia, con lo que
eso arrastra. Son 38 páginas en 13 mapas, y en el mapa 2 son los dos droides:
el de (7,72) sube una celda a velocidad 4, suena, salta de vuelta y espera
tres veces, y roto gira con cuatro `face_*`; el de (30,55) camina un cuadrado
a velocidad 2, medio pixel por cuadro.

* **La ranura de ruta** lleva ahora la velocidad (+17), las banderas (+18: de
  página, se repite, saltea lo bloqueado, mira siempre igual, animación
  continua, recargada este cuadro), la página con que se cargó (+20), lo que
  falta del paso de 256 por celda (+22), la ruta de la página para volver a
  ella cuando una forzada termina (+24 a +29), hacia dónde va el paso (+30,
  que con la mirada fija no es hacia donde mira) y su capa (+31). Son doce
  ranuras, no ocho: el mapa 127 tiene ocho páginas con ruta propia.
* **La velocidad** es `PASO_POR_VELOCIDAD`: `1 << (1 + velocidad)` de 256 por
  celda y por cuadro, y los pixeles son la resta tirando los dieciseisavos, de
  los dos lados. **Una ruta forzada sobre un evento camina a la velocidad de
  su página**, que por defecto es 3 —dieciséis cuadros por celda— y no la 4
  del héroe: `SetupFromPage` la pone y `ForceMoveRoute` no la toca. Hasta acá
  los dos lados caminaban a todos a 4, y por eso nadie lo vio; la fila del NPC
  la trae en +13 y la referencia la saca de `collect_npcs`, de la misma página.
  Las órdenes 28 y 29 la suben y la bajan, 26 y 27 fijan y sueltan la mirada.
* **La animación es la de RM2k**, `Game_Character::UpdateAnimation`: un
  frame de 0 a 3 y cuántos cuadros lleva en él, que sube caminando, siempre
  con la animación continua, y quieto sólo hasta llegar al del medio; cambia
  cada `ANIM_PARADO` cuadros caminando y cada `ANIM_CONTINUA` quieto, por
  velocidad. El cuadro en que un salto termina ya cuenta: `UpdateAnimation`
  corre después de que `UpdateMovement` bajó la bandera. Los tipos 2, 3 y 4
  no giran al caminar pero sí con `face_*`, que es el `SetFacing` directo de
  `UpdateMoveRoute`, y por eso el droide roto gira.
* **Lo bloqueado se reintenta** si la ruta no es `skippable`: la orden no
  avanza y se vuelve a probar cada cuadro, y es lo que deja plantarse delante
  del droide y que se quede empujando. **El salto también**, desde el
  2026-09-05: `BeginMoveRouteJump` fallido con `skippable` apagado vuelve el
  cursor al `begin_jump` —`current_index = saved_index`— y corta el cuadro. Es
  lo que hace el droide de (7,72) cuando el jugador se le planta en la celda
  a la que vuelve saltando: se queda animando contra la pared, y salta apenas
  el jugador se corre. Antes el salto se salteaba y la ruta seguía, y taro lo
  vio como "deja de ejecutar su animación". Sin `end_jump` no hay a qué
  volver y se saltea siempre. Es el caso `droide-tapado`. Las forzadas se
  saltean lo bloqueado, como hasta ahora, pidan lo que pidan: ver "Lo que
  falta".
* **Se repite** volviendo al principio en el mismo cuadro, una vez por cuadro.
  **No lee órdenes nuevas mientras el intérprete tiene una página corriendo**
  —`IsRunning()` en `UpdateNextMovementAction`—, pero el paso en curso se
  termina y las esperas siguen contando. Y **no la espera `OP_RUTAS`**:
  `ProceedWithMovement` mira sólo las forzadas.
* **El refresco.** `Game_Map::Refresh`: al cargar el mapa y al empezar el
  cuadro siguiente a un cambio de switch o de grupo, cada evento con rutas
  propias vuelve a mirar cuál es su página activa; si cambió, carga la ruta
  nueva desde el principio con la espera del giro, y si la nueva no tiene
  ruta se queda sin órdenes. Es `rutas_de_pagina`, en dos pasadas y sólo
  sobre las páginas de los eventos marcados por el conversor —bit 6 de +13—:
  con todas las páginas costaba más de un cuadro, el lazo perdía uno, y se
  vio como el droide roto girando un cuadro tarde. Por lo mismo la capa del
  que se mueve va en la ranura y no se busca en cada paso: buscarla era otro
  cuadro perdido, cada tanto, con el droide empujando contra el héroe.

**Cómo se verifica.** Cuatro casos de `snes-escena` en el mapa 2, con el héroe
quieto: `droide`, seis cuadros del ciclo; `droide-roto`, con el switch 22
puesto, girando; `droide-frenado`, con el héroe en (7,71) tapándole el paso; y
`droide-cuadrado`, el de arriba a la derecha caminando a medio pixel por
cuadro. Más `bloqueo`, que ahora es una ruta forzada del héroe contra el droide
en movimiento. Y todos los casos viejos con rutas forzadas cambiaron de
resultado sin cambiar de receta, por la velocidad 3.

**Lo que no se modela.** Los otros tipos de movimiento —al azar, vertical,
horizontal, hacia el héroe: 133 páginas, 106 de ellas hacia el héroe—; el giro
en el lugar (`AnimType_spin`, dos páginas); moverse hacia o desde el héroe
dentro de una ruta; que una forzada retome la de la página **por donde iba**
—acá arranca de nuevo—; y `skippable` en las forzadas.

#### La frecuencia de la ruta, y encarar al héroe

Hasta el 2026-09-04 una ruta con frecuencia distinta de 8 no compilaba, y el
modelo era "girar es gratis, los pasos van seguidos y el `wait` son veinte
cuadros". Era exacto sin saberlo: es el contador de parada de RM2k con la
frecuencia 8. Después de cada orden el personaje se queda quieto
`max_stop_count` cuadros —`SetMaxStopCountForStep` tras un paso,
`ForTurn` tras un giro, `ForWait` en un `wait`— y valen `1 << (9 - f)`,
`1 << (8 - f)` y `20 + (1 << (8 - f))`, con las dos primeras en cero para la
8. El juego usa la 2, la 3, la 4, la 7 y la 8; la 1 daría 256 cuadros tras
cada paso, no entra en el byte de espera y no la usa nadie: se rechaza.

Las dos tablas las emite el conversor con las mismas funciones que usa la
referencia, y la ROM las indexa con la frecuencia tal cual. Hay una vuelta que
importa: **después del último paso no se espera nada**, porque la ruta se
cancela ahí mismo —ver "Pisar un evento"— y `ProceedWithMovement` no la tiene
que esperar. Un giro como última orden sí deja la ruta puesta los cuadros del
giro, que es lo que hace RM2k dentro de un cuadro de diferencia.

**`HaltAllMovement` las cancela todas de golpe**, desde el 2026-09-13. Es
`Game_Map::RemoveAllPendingMoves`: un `CancelMoveRoute` sobre el héroe y sobre
cada evento del mapa. Lo que cancelar quiere decir está escrito **una sola vez
de cada lado** —`retomar_pagina` en la ROM y `Ruta.cancelar` en la referencia,
las dos reusando el camino de "la forzada terminó sola"— para que cancelarla y
terminarla no se puedan separar, que es justo la clase de diferencia que nadie
ve hasta que la escena sale distinta. Y lo que **no** toca es lo mismo que allá:
el paso o el salto en curso se terminan —`IsAnyMovePending` no los mira— y
hacia dónde mira cada uno queda donde la ruta lo dejó, así que un
`ProceedWithMovement` pegado atrás todavía espera los cuadros que le falten al
paso. Hay **un solo** `HaltAllMovement` en todo el juego —la página del mapa 11
que reordena el escondite de los Lazer Teeth cuando te descubren, y que termina
teletransportando— así que lo que lo mide es un caso sintético, `parar-rutas`.

`face_hero` es `GetDirectionToCharacter`: manda el eje con más distancia, en
empate el vertical, y sobre la misma celda se mira abajo. Sólo sobre eventos;
el héroe encarándose a sí mismo no lo usa ninguna página y no compila. Lo que
lo tenía afuera no era el giro sino lo que pasaba al **pisar una ruta con
otra**: la ROM reseteaba la ranura entera, y el evento volvía a mirar adonde
decía su página hasta que la ruta nueva lo girara. Ahora al reusar la ranura
se conserva lo que `ForceMoveRoute` conserva —el paso o el salto en curso se
terminan, hacia dónde mira queda, atravesar paredes y la animación parada
siguen— y se cortan la espera y las órdenes. El héroe igual: acá se le cortaba
el salto y la referencia no.

Lo prueban cuatro casos de la tanda: `ruta-lenta` y `npc-lento`, la frecuencia
4 sobre el héroe y sobre un evento —dos pasos, un giro y un paso; el paso va
del cuadro 1 al 8 y el siguiente recién arranca en el 41, el giro suelta a los
16—, y `npc-encara` y `npc-encara-lado`, con el héroe abajo y a la derecha del
evento. Rotos a propósito: sin la espera tras el paso, `ruta-lenta` se va a
281 pixeles en el cuadro 20 y a 12757 en el 44; sin `face_hero`, `npc-encara`
a 274.

Lo que no se modela, de ningún lado: un movimiento **bloqueado** con una
frecuencia baja. RM2k le pone el tope del paso sin reiniciar el contador, así
que espera lo que le falte de la orden anterior; acá se saltea y sigue, como
con la 8. Ninguna ruta lenta del juego choca contra nada.

#### El arranque de verdad

El juego no empieza donde las pruebas lo ponían. Empieza en **Map0004, `Blank
(Leave START here)`**, una habitación vacía cuyo único trabajo es disparar un
evento y teletransportar —el patrón clásico de RM2k—. Esa habitación no tiene ni
una celda abierta por los cuatro lados, así que la heurística que elegía "el
tile abierto más cercano al centro" no tenía dónde poner a nadie.

Ahora, en el mapa donde el juego arranca, la posición sale del LCF. En los demás
sigue saliendo de la heurística, porque a ésos se llega por teletransporte y de
dónde entrás depende de por dónde viniste. La regla vive en `inicio_del_mapa()`
y la usan el conversor y la referencia: si cada uno eligiera por su cuenta, la
comparación estaría midiendo dos cosas distintas.

#### La página activa se congela hasta el refresco

Qué página de un evento está activa **no se recalcula cada vez que alguien
pregunta**. En RM2k es `Game_Event::page`, y sólo la reescribe
`Game_Map::Refresh()`, que corre al principio de `Game_Map::Update`:

    if (GetNeedRefresh()) Refresh();
    ...
    UpdateMapEvents(actx);        // acá los intérpretes prenden switches
    game_player->Update();        // y el héroe se mueve con la página VIEJA

La ROM ya lo hacía sin proponérselo: la página activa vive en la fila del NPC
—la capa, el gráfico, lo que el tile le impone a la celda— y sólo la reescribe
el refresco, que `eventos_tick` atiende arriba de todo. **La referencia la
calculaba viva**, con los switches del momento, y eso son dos lados haciendo
cosas distintas.

La diferencia no es de un cuadro. Un switch prendido por una página le abría el
paso al héroe en ese mismo cuadro del lado de la referencia y en el siguiente
del lado de la ROM; y como **una orden de ruta bloqueada se saltea y no se
reintenta**, lo que se veía no era un cuadro de atraso sino que el héroe nunca
cruzaba la puerta del Emitter Room. La escena de Talan entera colgaba de eso.

Arreglarlo pidió tres cosas, y las tres hacen falta:

* **La instantánea**, `Estado.paginas_activas`, que rehace `rutas_de_pagina` y
  nadie más.
* **El refresco en un solo lugar**: arriba de `Interprete.cuadro`, que es por
  donde pasa todo cuadro. Estaba repartido en los lazos que llaman ahí, y uno
  de ellos no lo llamaba nunca después de prender un switch.
* **No cortar el lazo con un refresco pendiente.** Ésta fue la que costó: la
  página que abre la puerta es un `ControlSwitches` y nada más, así que el
  intérprete terminaba en el mismo cuadro, el lazo cortaba —"ya no pasa nada"—
  y la instantánea quedaba vieja para siempre. Con la página calculada viva eso
  no se notaba; con la instantánea, `puerta-emisor` dibujaba la puerta cerrada
  después de abrirla.

**Cómo se verifica.** Lo cobra `puerta-emisor`, que abre la puerta del Emitter
Room apretando A y mira el cuadro 40: con la página activa calculada viva daba
300 pixeles de diferencia y con la instantánea da cero. Se le hizo además un
caso de la escena de Talan entera, `talan`.

#### El intérprete de eventos

RM2k tiene unos 130 comandos de evento. La ROM entiende diez —prender y apagar
switches, esperar, teñir la pantalla, teletransportar, cambiar el grupo, caminar
una ruta forzada, esperar a que las rutas terminen, mostrar un mensaje,
destellar a un personaje y el cronómetro— y resuelve las páginas como RM2k: de
cada evento gana **la de número más alto cuyas condiciones se cumplen todas**.

La regla que hace que eso sea seguro es una sola: **una página se emite sólo si
todos sus comandos se pueden ejecutar**. Si aparece uno que no modelamos, la
página no se emite y el evento no hace nada. Ejecutar la mitad de un script
dejaría al juego en un estado que no existe, y la comparación no lo vería porque
la referencia haría lo mismo mal. Por lo mismo, un evento con una condición que
no sabemos evaluar —hoy sólo el cronómetro, una página en todo el juego— queda
entero afuera: sin saber qué página está activa, correr la equivocada es peor
que no correr ninguna. Las de switch, actor y variable se evalúan; la de ítem
se sabe que nunca se cumple.

De las 519 páginas automáticas del juego, 42 se compilan enteras con este juego
de comandos, y 31 sobreviven además al filtro por evento. Pero **29 de esas 31
no hacen nada**: todos sus comandos son de los que se aceptan sin ejecutar
porque no ejecutarlos no se ve. Las que hoy hacen algo son dos, y conviene
tenerlo presente antes de creerle a un número grande:

    mapa 3  Emitter Room               prende dos switches
    mapa 4  Blank (Leave START here)   dos switches, tinte y teletransporte

La segunda es la que abre el juego, y es la única del juego entero que ejercita
el tinte y el teletransporte por evento.

El tinte de pantalla no se podía saltear. En las puertas el fundido termina y la
pantalla vuelve; acá se tiñe y después se teletransporta, así que el mapa de
destino se ve teñido. En una consola con paleta eso no es un efecto de pantalla
sino una transformación de la paleta, que la consola hace con sus unidades de
multiplicación y división y Python repite igual. Y como el tinte es estado del
juego y no del mapa, se vuelve a aplicar cada vez que se carga uno; con el tinte
neutro la cuenta deja los colores donde estaban, así que el camino es siempre el
mismo.

**La cuenta son dos, y las dos salen de leer `ToneBlit` en easyrpg.** Primero la
saturación y después el color, en ese orden.

**El color es un hard light**, no una multiplicación: `2ab` para la mitad de
abajo y el screen `1-2(1-a)(1-b)` para la de arriba. En las unidades de RM2k,
con 100 neutro, eso es

    valor <= 100:  canal * valor / 100
    valor  > 100:  31 - (200 - valor) * (31 - canal) / 100

o sea la misma cuenta espejada en los dos ejes, y por eso `tabla_canal` arma
siempre la de abajo y espeja la tabla terminada si el valor aclara. La mitad de
abajo es lo que este repo venía haciendo desde el principio; la de arriba
**estaba mal** —multiplicaba por dos y topaba en 31— y la diferencia con RM2k
llegaba a 31 de 31 con el valor 200, o sea la pantalla entera. No lo cobró nadie
porque ninguna página que compilara aclaraba la pantalla; dos de las once que
destraba la saturación sí, con `(0, 120, 120)`.

**La saturación es una mezcla hacia el gris**, no un factor por canal:
`saturation_tone` saca la luminancia Y' del color —los pesos 19595, 38470 y
7471, que suman 65536 exactos y por eso valen igual sobre canales de cinco
bits— y acerca o aleja los tres canales de ella. Con 0 todo queda gris, con 100
no pasa nada y con 200 la distancia al gris se triplica. Como necesita los tres
canales a la vez, **no entra en las tablas de 32 entradas** y hay que hacerla
color por color; por eso se saltea entera cuando el valor es el neutro, que es
lo que hace el `apply_sat` de easyrpg.

Medida contra la cuenta de easyrpg sobre ocho bits, esta versión difiere en **un
valor de 31 como mucho**, para todos los tintes que el juego usa. Viene de que
RM2k hace la cuenta con ocho bits y la consola tiene cinco, y es la misma
tolerancia que la mitad de abajo ya tenía.

El intérprete está escrito dos veces —en `main.s` y en `tools/eventos.py`— pero
el bytecode es uno solo, así que lo que se ejecuta de los dos lados es el mismo
programa.

**Cómo se lo mira:**

    just snes-evento     # mapas 4 y 1 en la ROM, arrancando en el 4
    just snes-play       # y con sonido, en una ventana

El mapa 4 es una habitación negra y vacía cuyo único trabajo es prender dos
switches, teñir la pantalla y teletransportar. Lo que se ve al arrancar es el
mapa 1 ya teñido de azul, sin haber tocado una tecla: el tinte es `(0, 0, 100)`,
o sea rojo y verde a cero y azul intacto.

Los dos mapas tienen que estar en la ROM. Un teletransporte a un mapa que no
entró no se puede compilar, y entonces la página entera no se emite: con el mapa
4 solo, la pantalla se queda en negro, y eso es correcto.

**Cómo se verifica.** La referencia entra a los mapas como entra la ROM: para
al héroe donde lo dejó la puerta o el teletransporte que lo trajo, le corre los
eventos automáticos del mapa, y si una página pide mudarse repite el ciclo con
el mismo tope de ocho vueltas que la consola. Los switches y el tinte viven en
un estado que sobrevive a los mapas, porque de eso depende qué página queda
activa en el siguiente.

El tinte se aplica al final, sobre la imagen ya compuesta. En la consola no es
un efecto de pantalla sino una transformación de CGRAM, y como cada pixel del
fondo, de la capa de encima y de los sprites sale de una entrada de CGRAM,
teñir cada color del render da lo mismo —siempre que la cuenta se haga sobre
los 15 bits y no sobre los 24 del PNG, que redondearían distinto—.

Eso es `just snes-evento`, y está en `snes-hitos`:

    mapas 4 y 1 en la ROM, arrancando en el 4
    la consola contra la referencia: 0 pixeles distintos de 57344

En una sola comparación entran la selección de página, los dos switches, el
tinte, el teletransporte, y que el héroe quede tapado por la capa de encima en
la celda donde lo deja.

Antes de que existiera, este camino no lo ejecutaba **ninguna** prueba, y tenía
cuatro errores. Los tres primeros encadenados, cada uno tapando al siguiente:

1. `poner_switch` pisaba `Y`, que es el cursor del bytecode del intérprete. Las
   dos páginas que hacen algo empiezan prendiendo switches, así que el bucle
   leía el opcode siguiente de un byte cualquiera del medio de la página y
   cortaba ahí. Ninguna de las dos pasaba de su primer comando.
2. El lazo de `tenir_paleta` llevaba la cuenta de colores en `X`, que adentro
   del lazo es el índice de las tres tablas de canal. Al llegar al `cpx` valía
   el azul del color anterior, así que el lazo no terminaba y la consola se
   colgaba.
3. El azul se corría cinco lugares en vez de diez, y salía en los bits del
   verde. La pantalla se teñía de verde en lugar de azul.

Y el cuarto, que apareció recién cuando hubo una referencia contra la cual
comparar: el héroe se dibujaba **por encima** de la capa que tiene que taparlo.
La prioridad de un objeto son los bits 5 y 4 del byte de atributos, así que el
valor va corrido cuatro lugares, y `$20` no es prioridad 1 sino 2 —que en el
orden del modo 3 está adelante de BG2 1 y no atrás—. Estaba escrito igual de
mal en el conversor y en la ROM, o sea que las dos partes coincidían y sólo se
veía parándose debajo de la capa de encima. Ninguna caminata lo hacía: todas
terminan contra un borde del mapa.

Los cuatro se ven apenas se corre la página, y no se ven de ninguna otra forma.
La lección es la de siempre en este repo, pero al revés: acá el problema no fue
que la referencia y la ROM se equivocaran igual, sino que **no había ninguna
referencia que ejecutar**.

#### La ventana de mensaje

La ventana vive en BG2, en la mitad de arriba del banco de tiles que comparte
con la capa de encima: del índice 0 al 255 cae el de encima y del 256 al 511 la
ventana. Su paleta es la que queda justo debajo de la de encima, y se la paga el
fondo: se lo aprieta en las que quedan y fusiona lo que no entre. Relevados los
328 mapas, 290 no fusionan nada y los 38 que sí van de 1 a 16 colores, que es el
techo —una paleta—.

**Y en una ROM de varios mapas esa paleta es una sola, la de la ROM.** Las
celdas de la ventana se emiten una sola vez, con los tres bits de paleta ya
adentro, y cada mapa la pondría justo debajo de su capa de encima, que no
coincide: en la ROM del arranque el mapa 4 la pondría en la 6 y los mapas 1 y
2 en la 3. Gana la más baja —`paleta_de_la_ventana`, la misma función en el
conversor y en la referencia— y los mapas que la tenían más arriba se vuelven a
convertir con el fondo apretado debajo de ella; la capa de encima no se mueve,
porque dónde arranca ya se guarda mapa por mapa. Cuesta lo de siempre de la
ventana, sólo que en mapas que solos no pagaban: el 7 con el 269 en la misma
ROM fusiona 13 colores de 60, y se ve. Ése es el caso `snes-ventana 7
ventana-7-y-269 269` de la tanda: el mismo reparto que la ROM del arranque, con
un mapa que se puede mirar en vez de una habitación negra. Nació con el 1 de
compañero, hasta que el 1 con ventana dejó de entrar en VRAM: ver "Lo que
falta".

**El tilemap de BG2 se scrollea con la cámara, y la ventana no puede.** No es un
caso raro: en `game_player.cpp` de easyrpg `UpdateMoveRoute` corre **antes** del
guard de `IsMessageActive`, o sea que una ruta forzada del héroe sigue caminando
con el mensaje en pantalla y la cámara lo sigue. En este juego hay 186 páginas
donde eso pasa y la primera está en el mapa 1; y hay 25 páginas paralelas con
`PanScreen`, que también corren.

Se probó primero **seguir el scroll** —escribir las celdas de la ventana en las
posiciones que en *ese* cuadro corresponden a la franja de abajo— y **no
funciona**, por una razón que no es de implementación: el tilemap se dibuja en
celdas de 8 pixeles y la cámara se mueve de a 2, así que una ventana estampada
en celdas cae a `camara_x mod 8` pixeles de donde va. Medido con la cámara
moviéndose sólo en horizontal, y comprobado corriendo la referencia esos mismos
pixeles:

    camara_x 720, resto 0    238 pixeles de diferencia
    camara_x 722, resto 2   2627
    camara_x 724, resto 4   2717
    camara_x 726, resto 6   3198

O sea: **un cuadro de cada cuatro por eje**. Y aparecían dos problemas más —la
franja hay que reestamparla entera en cada cruce, no la columna que entra, y la
fila que sale de la franja no la redibujaba nadie—. El intento vivió tres
commits; está en `git log`.

**Lo que sí funciona es HDMA**, que era la opción que se había descartado por
2 KB de VRAM que no había. El DMA de siempre transfiere todo de una; el HDMA es
el mismo hardware disparado **una vez por scanline**, así que un registro del
PPU puede valer una cosa arriba de la pantalla y otra abajo. De la línea 0 a la
143 BG2 es la capa de encima del mapa, con la cámara; de la 144 a la 223 es un
tilemap propio de la ventana, de 32x32, con el scroll clavado:

    canal 1   BG2SC          qué tilemap dibuja BG2
    canal 2   BG2HOFS/VOFS   con qué scroll

Cada canal lee una tabla de la RAM con entradas `[cuántas líneas][valor]`. Las
144 líneas de arriba van en dos tramos porque el contador de una entrada es de
7 bits y no llega a 144, y las dos llevan justo lo que `flush_video` ya escribía
en los registros, así que arriba de la ventana no cambia nada.

Lo que esto compra, además de que sea exacto: el tilemap de la ventana **no lo
toca nadie más**, así que se escribe una sola vez al cargar el mapa —320 celdas
seguidas, un solo DMA— y abrir un mensaje es prender el HDMA y cerrarlo es
apagarlo. Ni una escritura de VRAM en el medio, ni un cuadro en negro, y
`redibujar_franja` dejó de existir.

El único cuidado: al apagar el HDMA hay que devolverle a `BG2SC` el tilemap del
mapa, porque el HDMA lo dejó apuntando al de la ventana en la última línea que
escribió.

**Los 2 KB salen de los sprites.** Relevados los 318 mapas que convierten, el
que más gasta usa 380 tiles de sprite de los 512 que el reparto le da, así que
bajarlos a 448 no le saca nada a nadie y deja libre la palabra $1C00, que es
múltiplo de 1024 y por lo tanto una base válida de tilemap. En el reparto para
mapas con mucho fondo los 2 KB no pueden salir de ahí —esos mapas usan hasta
320 tiles de sprite— y salen del fondo: 480 tiles en vez de 512.

#### El texto se compone en caliente

Una página de mensaje ya compuesta son unos 240 tiles de 4bpp, o sea 7,5 KB, y
el juego tiene 18.808 líneas de texto: emitir una ventana por mensaje no entra
ni cerca en 256 KB. Así que la ROM lleva la fuente y arma los tiles ella, que es
lo que hace FF6 con su `InitDlgVWF` y su buffer de diálogo en la WRAM.

**La medición que lo volvió barato.** RM2k dibuja cada glifo usando sus pixeles
como máscara sobre un bloque de 16x16 del System —de ahí el degradé de las
letras— y leído así pide muestrear el bloque pixel por pixel. Medido, no: **cada
fila del glifo toma un solo color**, y la sombra es un color plano. O sea que
todo el color se reduce a doce bytes, uno por fila, más uno para la sombra.

El banco de tiles de la ventana se reparte así:

    0 .. 11     la ventana vacía, deduplicada: marco y fondo estirado
    12 .. 251   el área de texto, 30 celdas de ancho por 8 de alto

Las 240 del área de texto **no se deduplican**: cada celda tiene su tile fijo,
porque la ROM las reescribe y no puede andar buscando repetidos. De ahí sale el
tope de **39 caracteres por línea**: con 40 la sombra del último se pasa a la
celda 31 y harían falta ocho tiles más de los que hay. Truncar a 39 pierde el
1,58% de los caracteres del juego, contra el 1,09% de truncar a 40.

Componer un renglón es cebar el buffer con el fondo de la ventana —un DMA de la
ROM a la RAM, que va por la ventana que la WRAM tiene en el bus B— y escribirle
los glifos encima. Lo que hace rápida la escritura es que los planos 0 y 1 de
una fila son **bytes vecinos** en el formato de la consola, y los 2 y 3 también:
duplicando la máscara a los dos bytes de la palabra, cada par de planos sale de
una sola escritura de dieciséis bits, y son cuatro por fila de glifo en vez de
dieciséis. Y la celda que la máscara no toca se saltea entera, que en la mitad
de las fases es la mitad del trabajo.

**El presupuesto por cuadro está medido y no elegido.** Se componen 5
caracteres por vuelta del lazo. No es una optimización: si una vuelta se pasara
del cuadro, `wait_vblank` agarraría el siguiente y el héroe caminaría más lento
que en la referencia, que es una diferencia que ninguna captura muestra. Medido
sobre `snes-anclada`, que es el único caso donde el héroe camina con un mensaje
abierto: con 5 y con 6 no se pierde ningún cuadro, con 8 se pierde uno. Va en 5
por margen, porque la vuelta cuesta distinto en cada mapa.

Lo que cuesta: un mensaje de 51 caracteres tarda unos 15 cuadros en aparecer y
uno de cuatro renglones llenos tardaría unos 36. En RM2k tampoco desentona: allá
la ventana se abre con una animación.

**De dónde sale el texto: el operando del opcode.** `OP_MENSAJE` lleva un
desplazamiento de 16 bits dentro del bloque `mensajes`, que es de la ROM entera
y no del mapa. El conversor lo arma mientras compila las páginas —cada
`ShowMessage` deja su texto y se lleva su desplazamiento— y lo deduplica, que en
el juego entero son 2477 cuadros distintos de 2895.

Dieciséis bits alcanzan porque el bloque tiene que entrar **entero en un banco**
de 32 KB, y eso no es una casualidad de tamaño: lo lee `lda [msg_ptr], y` con un
puntero que el compositor incrementa de a un byte y que **no arrastra al byte de
banco**. Por eso el conversor lo emite con `.bloque`, que rellena hasta el banco
siguiente si no entra, y por eso `msg_empezar` puede sumarle el desplazamiento
al byte bajo y nada más. Si algún día no entra, lo que hay que agrandar es el
puntero, no el operando.

**Y lo mismo vale para las tablas que se leen con `lda f:tabla, x`**, aunque el
modo largo sí sume los 24 bits: en LoROM, lo que sigue a `$15:FFFF` no es la ROM
del banco 16 sino un espejo de la WRAM, así que una tabla a caballo de dos
bancos se lee basura de la mitad para adelante. Las nueve que viven fuera del
banco 0 —`item_k`, las cuatro de `item_txt`, `item_puntos`, `actor_params`,
`equipo_inicial` y `item_glifo_celdas`— no lo declaraban, y era un error
**latente que dependía de dónde cayeran**: apareció el 2026-09-12 al entrar los
cuadros de las animaciones de batalla, que corren 200 KB de RODATA hacia
adelante y dejaron `item_glifo_celdas` arrancando en `$15:FF0D`. Se veía como la
pantalla de ítems con las letras cambiadas, y sólo al correr la lista, que es
cuando el índice pasa de los 243 bytes que quedaban hasta el fin del banco.

**Lo que no compila y por qué.** El texto de este juego usa dos códigos de
escape de RM2k: `\|`, que es una pausa de un segundo, y `\^`, que cierra el
cuadro sin esperar a que el jugador apriete nada. Son 35 líneas en 17 páginas, y
las dos cosas son tiempo, no texto. Una página que los use **no compila**:
dibujarlos como dos letras se vería, y borrarlos calladito sería peor, porque
con `\^` la ROM quedaría esperando un A que RM2k nunca pidió y la página
pasaría a durar lo que tarde el jugador. Cuando el compositor sepa pausar y
autocerrar, esto se cae solo.

Y llevar ventana es una decisión explícita del conversor, **`--con-ventana`**,
que `--mensaje-de-prueba` implica. Cuesta 8 KB de VRAM y una paleta, así que una
ROM que no la lleve no tiene dónde dibujar un mensaje y sus `ShowMessage` no
compilan: el opcode lo habilita la ventana, no al revés.

El ciclo son tres piezas y ninguna corre donde uno esperaría:

* `op_mensaje` deja el pedido y **corta el cuadro**. La página queda bloqueada:
  `eventos_tick` ve `msg_abierto` y vuelve sin ejecutar nada.
* El flanco de A la desbloquea —`pad_a` contra `pad_a_ant`, que es el
  `Input::IsTriggered` de RM2k: sostener el botón no dispara de nuevo— y la
  página sigue **en ese mismo cuadro**.
* `mensaje_de_evento` atiende el pedido al final del cuadro, con la pantalla
  apagada. Tiene que ser así: estampar la ventana son 640 bytes de tilemap y
  redibujar la franja al cerrar son 2560, y eso no entra en un vblank. Está
  medido, llamando a `redibujar_franja` de más a propósito sobre `snes-heroe 7`:
  cada cuadro deja 532 pixeles de basura, cada 8 cuadros 262, cada 64 cuadros 0
  y una sola vez 0. Que la basura escale con la frecuencia y no con el contenido
  es lo que dice que el problema es el presupuesto del vblank.

Y hay un detalle que cuesta descubrir: `mensaje_de_evento` empieza vaciando las
tiras que dejó `stream_map` en ese mismo cuadro. `redibujar_franja` arranca
poniendo `col_addr` y `row_addr` en cero, así que sin eso la columna o la fila
que la cámara acababa de destapar se perdería.

**Con un mensaje en pantalla el pad no mueve al héroe**, y la ruta forzada sí.
No es una inconsistencia: son dos lugares distintos de easyrpg.
`UpdateNextMovementAction` llama primero a `UpdateMoveRoute` y recién después
vuelve si `Game_Message::IsMessageActive()`, así que la ruta camina y el input
no. Un paso ya empezado se termina igual, porque en RM2k no se frena a mitad de
celda.

**Cómo se verifica.** `just snes-ventana` compara el dibujo —marco, fondo,
fuente, sombra y paleta— contra la referencia, en cinco mapas elegidos por
cómo les pega el reparto de paletas y de VRAM; el 269 está porque es el único de
la tanda que usa el reparto para mapas con mucho fondo, o sea el que pone el
tilemap de la ventana en otro lado. `just snes-cerrar` compara todo lo demás,
con la misma forma que `snes-espera`: dos cuadros con margen, uno antes y uno
después de apretar A.

    cuadro  60   la ventana en pantalla y la página frenada: sin teñir
    cuadro 400   la ventana borrada y el tinte puesto

**El toque de A cae un cuadro antes del número.** `--apretar-a N` es el cuadro
en que la referencia cierra el mensaje y lo dibuja cerrado. La ROM dibuja lo
que armó la vuelta anterior —el mismo `RETRASO_DE_PANTALLA` de la caminata—,
así que `snes_correr.py` aprieta en el N-1 para que su cuadro N salga cerrado
también. Con los dos cuadros quietos de `snes-cerrar` esto no se veía: lo
delató la apertura, con el droide caminando después del cuarto mensaje un
cuadro atrás de la referencia, y la traza de los dos intérpretes cuadro a
cuadro —ranura de ruta contra `Ruta`, cursor contra `ev_cur`— diciendo que el
estado era el mismo y sólo el dibujo iba atrás. Y son **varios** toques, no
uno: cada número es un flanco, la ROM lo suelta al cuadro siguiente para que
el próximo también lo sea, y la referencia cuenta los cuadros a través de los
teletransportes, que es como los cuenta el emulador.

**La ventana no se tiñe.** Es lo que hace RM2k —en `Spriteset_Map::Update` el
tono se le aplica al tilemap, a los personajes, al panorama y a las sombras, y
la ventana no está entre ellos— y es lo que hace la ROM sin proponérselo:
`aplicar_tinte` vuelve a subir las tres paletas del mapa desde el cartucho, y
la de la ventana no es ninguna de ellas. La referencia decía lo contrario,
"como en la consola", y ninguna prueba abría un mensaje sobre una pantalla ya
teñida —`snes-cerrar` tiñe recién después de cerrarlo—. La primera que lo hizo,
el tercer caso de `snes-ruta-pisa`, dio 4122 pixeles, todos en la ventana.

Los dos cuadros difieren en 52637 pixeles de 57344, así que la prueba tiene de
dónde agarrarse. Con una dirección —`snes-cerrar 7 200 cerrar-right right`—
además se mantiene la cruceta apretada, y el cuadro 60 mide que el héroe no se
haya movido ni girado.

Cada mitad se verificó rompiéndola a propósito, que es la única forma de saber
que la prueba mira lo que dice mirar:

    sin `redibujar_franja` al cerrar   el cuadro 400 se va a 15789 pixeles
    sin bloquear la página             el cuadro 60 se va a 36848
    sin el guard del pad               el cuadro 60 de `right` se va a 22658

Es la única prueba que ejercita `redibujar_franja`, que hasta que existió el
opcode era el único pedazo de código del repo que no corría nadie.

Y que la ventana no se mueva con la cámara lo prueba `just snes-anclada`: una
ruta forzada en el mapa 6 con el mensaje abierto, que es el único caso en que la
cámara se mueve durante un mensaje —con el pad bloqueado, lo otro no existe—.
Los cuatro cuadros están elegidos por el resto de la cámara contra 8, que es
justo lo que hundía al intento anterior:

    cuadro  21   camara_x 722, resto 2   antes 2627 pixeles, ahora 0
    cuadro  23   camara_x 726, resto 6   antes 3198, ahora 0
    cuadro  50   camara_y 700, resto 4   antes 5964, ahora 0
    cuadro 130   la ruta ya bajó doce celdas   antes 11705, ahora 0

Y que el texto salga **del juego** y no de un flag lo prueba `just snes-texto`,
que es lo único que corre ese camino. Todo lo demás de la ventana usa
`--mensaje-de-prueba`: tres líneas inventadas en una página inventada, que
prueban el dibujo, el bloqueo y el cierre pero no que un `ShowMessage` compile
ni que el operando encuentre su texto.

El mapa 255 se eligió midiendo. Tiene una página automática **sin condición de
switch** —o sea que corre al entrar— cuyo código entero es esto:

    07 0000     OP_MENSAJE @0     "BRIDGE OVER THE RIVER LASHE" y tres líneas
    07 7c00     OP_MENSAJE @124   otras cuatro
    01 5003 01  el switch 848

De ahí salen las tres cosas que ninguna otra receta mira. El **desplazamiento**:
el segundo mensaje está en el 124, así que si el operando se ignorara se vería el
primero dos veces. Los **cuatro renglones**, contra los tres del mensaje de
prueba. Y el **encadenado**: al apretar A el primero se cierra y el segundo se
abre en el mismo cuadro, que es la regla que los dos lados escriben por separado.

Los cuadros 60 y 400 dan 0 de 57344, y **entre ellos difieren en 2869 pixeles**,
todos en las filas de la ventana: si el A no avanzara al segundo mensaje serían
cero y la receta daría verde sin probar nada.

#### La sacudida de pantalla

`ShakeScreen` es `OP_SACUDIR` desde el 2026-09-05: fuerza, velocidad y cuadros,
y con cero cuadros es `ShakeEnd`. Es `ShakeOnce` de easyrpg, que no reinicia la
posición para que dos sacudidas seguidas se encadenen, y con `wait` el
conversor le pone un `OP_ESPERAR` detrás, como a los destellos. La cuenta por
cuadro es `Shake::NextPosition`:

    amplitud = 1 + 2 * fuerza
    nuevo    = -amplitud * sin((resta * 4 * (velocidad + 2)) % 256 * pi / 128)
    corte    = velocidad * amplitud / 8 + 1
    posicion = clamp(nuevo, posicion - corte, posicion + corte)

RPG_RT la hace en punto flotante y trunca. Acá el seno es una tabla de 256
bytes a escala 127, que el conversor emite al `mapdata.inc` desde la misma
lista que usa la referencia —`SENO_SACUDIDA`—, y la división es entera, con el
multiplicador y el divisor del hardware; el signo se saca antes y se vuelve a
poner después, que es truncar hacia cero. **Los dos lados hacen la misma cuenta
entera**, así que coinciden exacto entre ellos y los dos pueden diferir de
RPG_RT en un pixel en algún cuadro. Las 29 sacudidas del juego son de la forma
de RM2k, con fuerza hasta 9 y velocidad hasta 8: 19 pixeles de amplitud como
mucho.

La posición se le suma a la cámara **sólo al dibujar**: es `GetDisplayX`, y en
la ROM es `pantalla_x`, que ven el scroll, la tabla HDMA de la ventana y la OAM.
El streaming del tilemap sigue mirando `camara_x`, porque la sacudida no cambia
lo que hay que tener cargado. La ventana de mensaje no se mueve.

Cuatro cosas salieron de compararla cuadro por cuadro, que es lo que ninguna
receta hacía hasta ahora —las esperas se miraban con margen—:

* **El tinte se escribía a mitad del cuadro.** `tinte_de_evento` apagaba la
  pantalla, recalculaba las tres paletas en CGRAM y la volvía a prender, en el
  lazo principal: un cuadro teñido a medias en el emulador y una franja negra
  en el hardware. Ahora `aplicar_tinte` deja las paletas en `cgram_sombra` y
  `subir_tinte` las sube por DMA en el vblank —544 bytes como mucho, y ese
  vblank sube dos poses en vez de cinco—; `cargar_mapa`, que tiene la pantalla
  apagada, lo llama enseguida.
* **El streaming carga con margen.** El toro de 64 columnas tenía al día
  exactamente las 33 de la pantalla, y la sacudida en negativo mostraba la de
  la izquierda, que era una ranura que nadie había escrito. `MARGEN_COLS` son
  cuatro columnas de más a cada lado, 32 pixeles: `fill_window`, `stream_map`
  y `build_row` cargan el mismo rango, `[win_col - 4, win_col + 60)`. Lo
  último costó un rojo: la fila se armaba desde `win_col`, y sus cuatro
  columnas finales pisaban en el toro las ranuras del margen de la izquierda,
  así que la esquina de la pantalla del mapa 2 mostraba columnas de 64 más
  adelante.
* **Fuera del mapa hay negro.** RM2k dibuja negro más allá de los bordes, y
  la referencia también —PIL rellena con negro—, pero la ROM no escribía las
  columnas que caían fuera del mapa y la ranura mostraba lo que tuviera.
  `build_column` y `build_row` escriben ahora tile 0 para lo que cae fuera,
  que el conversor reserva vacío en el banco del fondo como ya lo reservaba
  en el de la capa de encima; y el color de fondo —el 0 de CGRAM, el que se
  ve donde ninguna capa dibuja— es negro y no magenta. El magenta hacía dos
  cosas: centinela para el ojo, y **clave de recorte** de la capa de encima en
  `render_above`, que dibuja la capa sobre ese color y después lo vuelve
  transparente. Con negro se recortaban también los pixeles negros de los
  tiles de encima —la sombra de una máquina del mapa 6 se volvió un tramado
  gris—, así que la clave sigue siendo magenta, `CLAVE_RECORTE`, pero sólo
  adentro del render.
* **El cronómetro se dibuja con la cuenta de antes del cuadro.** La consola
  muestra en cada cuadro la OAM que armó la vuelta anterior. Con la caminata
  eso lo compensa la referencia por cómo modela el paso —el `hero_y` de la
  ROM después del cuadro N es el pixel de la referencia en el N+1—, y con los
  dígitos no había con qué: el parpadeo de los dos puntos cambiaba un cuadro
  antes en la referencia, con el mismo estado de los dos lados. `timer_texto`
  usa ahora la cuenta de antes de descontar el cuadro.

#### El destello de pantalla

`FlashScreen` (11040) es `OP_DESTELLO` desde el 2026-09-05: color, fuerza y
cuadros, y un `OP_ESPERAR` detrás si la página espera, como la sacudida. Lo
pide la escena en que Core rompe la puerta de seguridad del mapa 2 —evento 22,
página del switch 7, la que abre el pasillo al ascensor—, y era lo que la
cortaba junto con `ShowBattleAnimation` (11210), que desde el 2026-09-11 suena
y destella y desde el 2026-09-12 **también se dibuja**, achicado a una caja de
64x64: ver "El dibujo de las animaciones de batalla". El
juego tiene 62 destellos, 29 de ellos blancos; ninguno dura más de veinte
décimas.

**La cuenta.** `Flash::Update` baja el nivel en `nivel / cuadros_que_quedan`
por cuadro, con `double`: de 31 en treinta cuadros es 29.97, 28.93, ... hasta
cero en el último. Acá el nivel va a escala 256 y la resta es entera, con el
divisor del hardware; lo que se dibuja es la parte entera, y contra la cuenta
con `double` difiere en uno como mucho. RM2k lo dibuja como un rectángulo del
color con alfa `nivel * 8` sobre la pantalla compuesta —`Screen::Draw`—, y
acá es lo mismo que el tinte: **una transformación de CGRAM**. Cada canal de
cada color de las tres paletas del mapa se acerca al del destello en
`nivel / 31` del camino (`destellar_canal_pantalla` en eventos.py, con la
resta del lado positivo porque el divisor no tiene signo), el resultado va a
`pal_buf` y `flush_video` lo sube en el vblank en lugar de la sombra. La sombra
queda como está: es el mapa teñido sin destello, y cuando el destello se apaga
vuelve a subirse tal cual. La ventana y el cronómetro no lo reciben, y tampoco
allá: `Priority_Screen` es 90 contra 130 y 140.

**Va en dos cuadros, y eso se midió.** Pasar las doscientas y pico entradas
de las tres paletas —a más de cien ciclos cada una, porque cada color se parte
en tres canales y se vuelve a armar— no entra en un cuadro junto con todo lo
demás. La primera versión lo hacía en uno y **perdía un cuadro por cuadro**:
el destello bajaba a la mitad de velocidad y la escena terminaba treinta
cuadros atrás de la referencia, con el cuadro 600 en rojo y los de antes en
cero. Lo dijo `cuadros_perdidos` —ver "Los cuadros perdidos se cuentan"—, y
con un lazo de retardo calibrado en lugar del recoloreo salió que en esos
cuadros hay unos 11 ms de margen, y que el recoloreo entero costaba más. Así
que con la resta impar se arman las tablas del nivel y se pasan el fondo y la
capa de encima, y con la par se pasan los sprites y se sube todo. Lo que se
ve cambia cuadro por medio, un destello de treinta cuadros son quince
escalones, y la referencia hace exactamente lo mismo —`destello_mostrado` en
`Estado.cuadro_de_destello`—. Un tinte que cambie en el cuadro impar pisa
`pal_buf` con la paleta recién teñida y además no puede subirse sin destello,
así que ese cuadro se hace de una y el par rehace el fondo; la referencia
mira `tinte_cambio` para lo mismo.

**Y la RAM.** `pal_buf` es a la vez donde se arma la paleta teñida y donde
queda la sombra con destello: la primera se copia a la sombra en el mismo
cuadro, antes de que `destello_tick` escriba, y lo que hay se sube en el
vblank que sigue. Las tablas son bytes y no palabras ya corridas —que le
ahorrarían los corrimientos al recoloreo— porque **el banco 0 quedó en 7905
bytes de 7936**, con la pila arriba de todo: quedan unas decenas de bytes de
pila más lo que `pal_buf` no use. Es lo primero que hay que aflojar si algo
más pide RAM.

Dos trampas de nombres que costaron una vuelta cada una: el destello de
**un personaje** (`FlashSprite`) ya tenía `destellar` y `destellar_imagen` en
la referencia, con otra cuenta, y la primera versión de esto se llamó igual y
las tapó —un color de diferencia en toda la pantalla—; y `pal_buf` no puede
declararse con otro nombre por `=`, porque `w65.py` resuelve los `=` antes que
las etiquetas.

**Cómo se verifica.** El caso `core-puerta` de `snes-escena`: el héroe pisa
el evento 22 desde (87,76) con el switch 7 puesto, seis toques de A y seis
cuadros en cero, dos de ellos —407 y 425— con el destello a la mitad. Los
cuadros del destello se eligieron con el nivel de cada uno leído de la
referencia y de la ROM en un pixel negro, que es como se vio que iba a la
mitad de velocidad.

#### El arranque dura siempre lo mismo

Para comparar un cuadro en movimiento el cuadro N de la captura tiene que
mostrar el tick N de la referencia, y eso depende de en qué cuadro la ROM llega
al primer tick del intérprete. Hasta el 2026-09-05 eso dependía del mapa —la
subida de poses, la música— y **de cada cambio de código o de datos**: un
bucle más en `cargar_mapa` y el lazo arrancaba un cuadro después, y cada receta
llevaba un número medido a mano, 10 en el mapa 6, 41 en el 7, 43 en el 70, 70
con música. Se midió, y no era uniforme: el tinte en el vblank corrió un
cuadro a los mapas con más carga y no a los otros, y el tile 0 reservado podía
correr otro que esa medición no veía.

Ahora el arranque **espera hasta el cuadro `BOOT_CUADROS`**, contado por una
NMI mínima que sólo suma un cuadro y baja la bandera; el lazo principal corre
su primer cuadro tres cuadros después, y todas las recetas pasan ese número
como `--arranque`, que es el default de `snes_correr.py`. Una ROM cuyo arranque
tarde más que eso sale sin esperar, más tarde, pero igual de fijo para ella.

Eran **64 y 67** hasta el 2026-09-06, y son **112 y 115** desde que el cartucho
lleva varios temas: el banco de muestras es uno solo para todos, creció, y
subirlo al SPC700 va byte a byte con acuse —unos 1,4 cuadros por kilobyte—. El
112 no sale del banco de hoy sino del techo: con la ARAM llena, 62310 B, la ROM
llega al lazo en el cuadro 101. Sacarlo del techo tiene una ventaja que no es
sólo margen: **llenar la ARAM deja de costar nada**, porque el arranque ya está
pagado. El costo son ocho décimas más de mapa congelado al encender, casi todas
en la subida al SPC700; lo que las compraría de vuelta es un driver que reciba
por los cuatro puertos en vez del protocolo del IPL, que manda uno.

Con la ROM y la referencia alineadas exacto aparecieron tres cosas que el
margen escondía: el cuadro 400 de `snes-cinematica`, que caía con el héroe
caminando dentro de la ventana de un teletransporte —es 480 ahora—; el
cronómetro, de arriba; y `snes-saturar`, que pasaba `--arranque 0` fijo.

**Cómo se verifica.** `snes-sacudir`, tres casos: el mapa 7 con `3 3 2 1`,
que es la de la puerta del mapa 2; el 6 con `9 8 3 1`, la más fuerte y rápida
que admite RM2k; y el 2 con el héroe en (4,54) y la cámara en el borde
izquierdo, donde la sacudida asoma lo que hay fuera del mapa. La página de
prueba sacude, espera y tiñe: los cuadros del medio miran la pantalla corrida y
el último mira que volvió a su lugar y el tinte llegó entero. Lo que no se
modela es la sacudida continua de RM2k3, que este juego no usa.

#### La cámara corrida sin el héroe

`PanScreen`. De sus cuatro operaciones el juego usa dos —112 `pan` y 21
`reset`, y ni un `lock` ni un `unlock`— así que ésas son las que compilan.

La cámara se corre tantas celdas en una dirección y se le acerca al destino
`2 << velocidad` **dieciseisavos de pixel** por cuadro: es `pan_speed` de
`Game_Player::StartPan` y el `dx = min(step, |remain|)` de `UpdatePan`. Las
unidades no son un capricho heredado: la velocidad 2 —la que usa la escena de
Talan— mueve la cámara **medio pixel por cuadro**, y en pixeles enteros eso no
se puede contar. Así que los dos lados llevan la cámara corrida en
dieciseisavos y la bajan a pixeles con una división **al piso**, que es lo que
hace `Spriteset_Map` dividiendo `GetDisplayX()` por 16.

Tres cosas que decidir, y por qué:

* **El desplazamiento lo resuelve el conversor.** El bytecode lleva cuánto se
  corre el destino en x y en y, con signo, y el paso por cuadro; la dirección y
  la velocidad no llegan a la ROM. Son cuentas fijas.
* **Los cuadros que la página espera, no.** Ésos salen de **lo que le falta** al
  pan cuando el comando corre, y con uno todavía en curso eso no es lo que este
  comando pidió: es el `GetPanWait` de RM2k y el comentario de
  `CommandPanScreen` sobre el máximo. Los cuenta la ROM, con el divisor del
  hardware.
* **El pan entra antes del acote y no después**, al revés que la sacudida: RM2k
  corre la posición del mapa y el borde la frena, mientras que la sacudida
  asoma lo que hay del otro lado. Lo que **no** se modela es que en el borde
  RM2k frena el pan y lo deja pendiente; acá el acote es de la cámara y el pan
  sigue contando. Ninguna de las páginas que hoy compilan lo pide.

Y al cambiar de mapa la cámara vuelve a cero de golpe, que es lo que hace
`PerformTeleport` con `map_changed`. Un salto al mismo mapa no la toca.

**Cómo se verifica.** Dos casos, los dos con la página de prueba corriendo la
cámara **y esperando**, y un tinte detrás: los cuadros del medio miran la cámara
a mitad de camino y el tinte pincha el largo de la espera al cuadro.

* `pan`: dos celdas para arriba a velocidad 2 —el PanScreen de la escena de
  Talan—, o sea 64 cuadros. La cámara baja de a ocho pixeles cada dieciséis
  cuadros y el tinte aparece en el 66 y no en el 65.
* `pan-vuelve`: lo mismo y después `reset` a velocidad 4, que la trae de vuelta
  en dieciséis cuadros; el tinte cae en el 83 y no en el 82.

#### Varios temas en el cartucho

Hasta el 2026-09-06 la ROM llevaba **un** tema. Los `PlayBGM` de las páginas
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
cuadros, y eso habría que modelarlo en la referencia para que la comparación
cuadro a cuadro siga valiendo. Modelar cuánto tarda una transferencia es
exactamente lo que no se puede medir honestamente.

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

**Y un tema que no entra en el banco no se cae del cartucho**, desde el
2026-09-12. Hasta ese día, cuando el banco de todos no entraba en la ARAM el
conversor sacaba temas **de la lista entera**, desde el final. Al pasar la demo
a los 29 mapas de Lashe City la ROM pidió 19 temas, el banco se llenó —89
muestras y 66353 B contra los 64512 de ARAM— y se cayeron ocho. Uno era el del
título, que va último porque agregarlo al final es lo único que no renumera el
bytecode: `TEMA_TITULO` salió `$FF` y la pantalla de título no intentaba ni
arrancar música.

Que se cayera de la lista y no sólo del banco cuesta dos cosas distintas, y la
segunda es la cara: un `PlayBGM` de ese tema no hace nada, y **la pista de
MSU-1 queda inalcanzable**. `Fantasia_Of_The_Wind` tiene la pista 8; una pista
no gasta ni un byte de ARAM y lo único que necesita es que el tema tenga
número. Medido: con los archivos al lado, `MSU_HAY=1`, `MSU_SUENA=0` y el pico
del audio en cero.

Ahora la lista es completa siempre —un índice y su stream cuestan cartucho, y
de eso sobra— y lo que se recorta es **quién aporta programas al banco**, en
orden de prioridad: primero el del título, después el del mapa donde la ROM
arranca, y detrás la lista tal cual. Un tema que no aporta suena con lo que
otros ya pusieron, porque el banco es por programa de General MIDI: de los
siete que hoy quedan afuera, sus notas con muestra van del 8% de
`golden_axe-turtlevillage2` al 70% de `Lunar_Pyramid`. Antes no sonaba ninguno.

**Por qué el límite sigue estando, ahora que el audio sube por paquetes de
mapa.** En la ARAM no vive el banco entero sino el directorio y **un** paquete,
así que el hardware aguanta bastante más: con los diecinueve temas aportando,
el directorio son 617 B y el peor paquete 54945 de 63831, o sea que entra. Lo
que no aguanta es el oído: los mismos 40 KB melódicos repartidos entre
diecinueve programas en vez de once bajan la tasa mediana de 12,5 a 8,4 kHz, y
eso se lo cobran los once temas que hoy suenan bien. El límite se queda hasta
que haya un presupuesto **por paquete** en vez de por banco; está en "Lo que
falta".

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

**Lo que sí costó caro es el arranque.** La subida al SPC700 va byte a byte con
acuse, unos 1,4 cuadros por kilobyte, así que un banco de 62 KB tarda el doble
que uno de 32. Con `BOOT_CUADROS` en 64 la ROM se pasaba y el lazo arrancaba en
el cuadro 101 en vez del 67: dos casos de la tanda se pusieron rojos con el
mapa 18 y 85 cuadros perdidos, que eran RAM sin inicializar. Ahora
`BOOT_CUADROS` son 112, medidos **sobre el techo y no sobre el banco de hoy**
—con la ARAM llena la ROM llega al lazo en el 101—, y las recetas pasan
`--arranque 115`. Cuesta ocho décimas más de arranque y a cambio llenar la ARAM
ya no cuesta nada. Ver "El arranque dura siempre lo mismo".

**Cómo se verifica.** `just snes-bgm <tema>`, que arma la ROM de las primeras
secuencias con `--tema-de-arranque`, la corre sin pantalla, graba el audio y se
lo pasa a `snes_check`. El flag existe porque `snes-check` escucha desde el
arranque y los mapas de estas secuencias no traen música propia —la prende un
`PlayBGM`—, así que sin él la ROM sale callada; no toca el bytecode, es el
mismo stream prendido antes. Lo que la prueba mira es justamente lo del banco
compartido: que las notas de cada tema salgan de los índices de muestra del
banco de todos.

**`snes-bgm` no está en `snes-hitos`**, y conviene tenerlo presente: la tanda
es visual y esto pide grabar cuarenta segundos de audio por tema. O sea que
este camino no lo corre nadie salvo que se lo pida a mano.

Los cuatro pasan: `escape_newyork` 96%, `TF3_1_awe` 98%, `evilrhys` 83% y
`hzstream` 90% —éste con el banco de los cuatro, 62310 B, o sea la ARAM casi
llena—.

**`evilrhys` es el ruidoso y conviene saberlo antes de asustarse**: en tres
corridas dio 66%, 75% y 83%, contra un techo de 95% que le da FluidSynth
tocando el mismo MIDI. La medida se toma sobre sesenta ventanas de una
grabación que arranca donde haya señal, así que en un tema con poca nota
sostenida el corrimiento elegido cambia bastante el número. Lo que **no**
cambia es el banco compartido: las escrituras melódicas de su stream son las
mismas con banco propio y con banco compartido. Lo que sí lo tiene al límite es
que tiene ocho canales melódicos para seis voces, así que dos no suenan nunca y
los seis que quedan son monofónicos.

#### El `FadeOutBGM`

Apaga el tema que esté sonando en los milisegundos que pida. Es lo único que
separaba a taro de la puerta del Emitter Room: la página de tecla del evento 5
del mapa 3 son tres comandos —un sonido, este fundido y el switch que abre la
puerta— y sin él no compilaba ninguna, así que apretar A no hacía nada.

No cuesta un cuadro: `Game_Interpreter::CommandFadeOutBGM` llama a `BgmFade` y
devuelve **true** en el mismo, o sea que la página sigue de largo. Así que no
mueve un solo cuadro de los que la tanda compara, y la referencia sólo tiene
que saltear sus tres bytes.

Lo que hace la ROM es bajar el **volumen general del DSP**, MVOL de los dos
canales, y cortar el tema cuando llega a cero. Tres decisiones:

* **El paso lo emite el conversor**, no la ROM: el bytecode lleva cuánto baja
  el nivel por cuadro y no los milisegundos de RM2k. El 65816 no divide, y el
  divisor del hardware es de ocho bits: los 5000 ms de esa puerta son 300
  cuadros y no entran. Es `eventos.paso_de_fundido`, y es la misma clase de
  número que el índice de mapa de un teletransporte.
* **El nivel es de dieciséis bits** y de él sale el volumen multiplicando por
  `TEMA_VOLUMEN` con el multiplicador del hardware. Bajar el registro de siete
  bits de a uno daría noventa y seis escalones para trescientos cuadros, y eso
  se oye.
* **`TEMA_VOLUMEN` y los dos registros los emite `sdsp.py`** en
  `musicdata.inc`, porque el stream ya los escribe al arrancar: tenerlos
  además a mano en `main.s` serían dos lados que se pueden equivocar igual.

Un `PlayBGM` cancela el fundido —el stream vuelve a escribir el volumen al
arrancar—, y un `FadeOutBGM` con el tema ya apagado no hace nada.

**Cómo se verifica.** La tanda lo cubre por donde puede, que es la pantalla: el
caso `puerta-emisor` habla con esa puerta y compara el cuadro 10 con la puerta
cerrada y el 40 con la puerta abierta. Es filoso por construcción —entre los dos
cuadros hay 300 pixeles— y por eso no cae en la trampa de los dos lados
equivocados igual: si la página no compilara, los dos dibujarían la puerta
cerrada y el caso daría cero.

El audio no lo compara nadie, así que el fundido en sí se midió a mano, con una
ROM del mapa 16 —que sí tiene tema propio y suena desde el arranque— y la
página de prueba con `--fundir-bgm 1000`:

    python3 tools/snes_convert.py --grupo 11 --map-id 16 --fundir-bgm 1000 \
        --pagina-de-prueba 240 100 100 0 -o rom/build/fb/mapdata.inc

`bgm_nivel` baja de a 1093 por cuadro, que es lo que dice `paso_de_fundido`
para 1000 ms, y el pico del audio del emulador acompaña: 16174, 9859, 5476,
1737 y cero a los sesenta cuadros. La misma ROM sin `--fundir-bgm` sigue entre
12000 y 24000 en el cuadro 130, o sea que lo que baja es el fundido y no el
tema.

#### La frecuencia se sube y se baja a mitad de una ruta

Las órdenes 30 y 31 —`increase/decrease_movement_frequence`— mueven la
frecuencia de la ruta de a uno, topando en 8 y en 1. De la frecuencia salen los
cuadros quieto después de cada orden, así que cambiarla a mitad de camino
cambia el ritmo de lo que queda.

**Las usa una sola ruta de todo el juego**: la que sacude a Manta en la escena
del Emitter Room, que baja de 8 a 6 y no vuelve a subir. Sin ellas esa página
no compila, y por eso entraron.

Lo único que no es mecánico es el tope de abajo. **Con la frecuencia 1 la
espera tras un paso son 256 cuadros** y no entran en el byte de
`ruta_tras_paso`, así que una ruta que llegue ahí no se puede correr. La salida
no fue topar en 2 —eso sería que los dos lados se equivoquen igual el día que
alguna ruta lo pidiera— sino **rechazar la ruta al compilarla**:
`eventos.frecuencia_minima` recorre las órdenes desde la frecuencia inicial y
devuelve la más baja por la que pasa, y si es menor que `RUTA_FRECUENCIA_MIN`
la ruta no se emite. Con una ruta que se repite se recorre nueve veces y no
una: la frecuencia se topa en los dos extremos, así que una que baje más de lo
que sube termina en 1 sí o sí. Ninguna ruta del juego cae en el guard hoy.

Con eso, la ROM y la referencia topan las dos en 1, como RM2k, y el camino que
la ROM no sabe recorrer simplemente no se compila.

**Cómo se verifica.** Dos casos nuevos, y los dos son filosos por construcción
—se midió contra la misma ruta sin las órdenes—:

* `ruta-frec`: el héroe camina seis celdas con un 31 y un 30 en el medio. En el
  cuadro 30 la referencia lo deja ocho pixeles más arriba que sin las órdenes,
  y en el 40, dieciséis; como la cámara lo sigue, eso corre la pantalla entera.
* `npc-frec`: lo mismo sobre un evento, donde la diferencia es sólo el sprite:
  271 pixeles en el cuadro 40 y 448 en el 60.

#### Cambiar el gráfico a mitad de una ruta

La orden 34, `change_graphic`, que 437 rutas de este juego usan y que "Lo que
falta" venía anotando como lo más caro que quedaba. Es la última de `MoveCommand` de
las que este juego usa, y la única con **operando**: detrás del 34 va el índice
del gráfico. Todo lo demás del bytecode de una ruta es un byte por orden, así
que el que recorra una ruta ya compilada tiene que pasar por `recorrer_ruta` —
plano, el operando se leería como una orden, y con un 30 o un 31 ahí adentro
cambiaría la frecuencia sin que nadie lo pidiera.

**El caso más común es desaparecer.** De las 437 órdenes, **185 cambian a
`nobodyhere`**, un CharSet sin un solo pixel opaco. Ahí no hay nada que subir a
la VRAM: la fila se esconde, que es lo que ya hacía `esconder_npc`. Verlo
primero cambió el tamaño del problema.

**Lo caro es la paleta, no el cartucho.** Un gráfico al que una ruta cambia es
un personaje más para la consola: pide una de las ocho paletas de sprite y sus
doce poses en el cartucho, porque después de cambiar el evento **sigue
caminando** y el ciclo tiene que salir de algún lado. Las doce poses son seis
kilobytes y de eso sobra; las paletas no. Forzarlas rompía tres mapas —el 108,
el 114 y el 207 pedían nueve de las ocho—, así que entran **mientras quepan**,
que es la misma regla que ya corría para los eventos dibujados con un tile del
chipset. El que no entra no se dibuja: la orden lo esconde en vez de cambiarlo,
los dos lados hacen lo mismo y el conversor lo dice al convertir. Pasa en esos
tres mapas y con un solo gráfico, `ABLDalia:3`.

Que el reparto de paletas lo decida `npcs_dibujables` **con los gráficos de
ruta adentro** no es un detalle de orden: esa función es la regla única que
corren los dos lados, así que si el conversor contara un personaje más que la
referencia, un evento de tile podría entrar de un lado y no del otro.

**Cómo viaja el índice.** `Graficos` numera los gráficos por mapa —hermano de
`Temas` y de `Mensajes`, pero por mapa, porque el banco de sprites es por
mapa— y la ROM lo resuelve con `ruta_grafico`, dos bytes por gráfico: de qué
personaje salen sus doce poses y con qué paleta. Esa tabla se copia a la RAM al
cargar el mapa, como la de NPCs, y por una razón concreta: leerla del cartucho
pediría un puntero largo en la página directa, y **la página directa está
llena** —259 bytes de los 256 al intentarlo—. Copiarla cuesta dieciséis bytes
de RAM y el mapa que más gráficos pide de todo el juego pide seis.

Hay un invariante del que esto depende y conviene tenerlo escrito: **el blanco
de una orden 34 siempre tiene ranura propia en la VRAM**. La orden sólo existe
adentro de un `MoveEvent`, así que su blanco está en `blancos_de_ruta` y por lo
tanto en `movibles`, y un evento que camina no comparte ranura ni con otro
igual. Sin eso, subir la pose nueva pisaría la de los NPCs quietos que
compartieran esa ranura.

Aplicarla es escribir tres campos de la fila: de qué personaje salen las poses,
la paleta —bits 1 a 3 de los atributos, sin tocar el resto— y $FF en la pose
que hay en la VRAM, que es lo que hace que `refrescar_npc` la vuelva a subir.
La pose del ciclo **no se toca**: el evento sigue caminando donde estaba, que
es lo que hace `SetSpriteGraphic`. Y no cuesta un cuadro: en `UpdateMoveRoute`
cae en la rama que no toca el contador de parada.

**Sobre el héroe no se compila**, como las diagonales. Su gráfico sale de la
tabla de actores —`place_hero` lo busca por el id del líder— y una ruta que se
lo cambie tendría que pisar ese mecanismo. Son 89 rutas de páginas automáticas
y diez páginas más; queda en "Lo que falta". El corte importa más acá que con
las diagonales: si una 34 llegara al héroe, `paso_de_ruta` la saltearía y
leería el operando **como si fuera una orden**.

Adentro de un salto la orden se consume y **no se ejecuta**: el lazo de
`BeginMoveRouteJump` sólo mira los `move_*`, los que giran y el `end_jump`.
Ninguna ruta del juego tiene una ahí adentro —medido, cero—, así que eso está
por corrección y no porque pase.

Con esto **la escena de Talan compila y corre**, y tiene caso propio: `talan`,
el más largo de la tanda —mil doscientos cuadros de los 233 comandos—.

**Cómo se verifica.** Dos casos, y son la misma ruta con distinto destino: el
evento 3 del mapa 6 baja dos celdas, cambia de gráfico y sigue bajando dos. Los
cuadros 10 y 25 lo miran con el suyo y el 40 y el 70 con el nuevo, **caminando**,
que es lo que separa "cambió el gráfico" de "cambió y se quedó quieto". El
primero cambia a `Future1:0` y el segundo a `nobodyhere`, o sea que desaparece.
Los dos medidos contra la misma ruta sin la orden: 146 pixeles de diferencia el
primero y 207 el segundo —el sprite entero—, y cero en los cuadros de antes del
cambio.

#### Las diagonales de ruta

Las órdenes 4 a 7 —`move_upright`, `move_downright`, `move_downleft`,
`move_upleft`—, que 26 rutas de este juego usan.

**Las camina sólo un evento.** De esas 26 rutas ninguna es del héroe, y por eso
la ROM no las tiene sobre él: el paso del héroe está escrito una vez por
dirección —`try_up` y sus tres hermanas, cada una con su borde de mapa, sus dos
permisos y su `step_dx`/`step_dy`— y darle diagonales sería duplicarlas para
cero rutas. El conversor rechaza la página que le dé una al héroe, igual que
rechaza al héroe encarándose a sí mismo. Sin ese corte los dos lados se
separan en silencio: la referencia camina la diagonal y la ROM se va hacia la
izquierda, que es donde cae el descarte de `paso_de_ruta`. No es hipotético
—pasó escribiendo las pruebas de esto—, así que `--ruta-de-evento` lleva el
mismo corte: ahí el blanco 0 es el héroe y un evento es su índice **más uno**.

**Nadie mira la celda diagonal.** `Game_Character::Move` prueba dos eles:
primero vertical y después horizontal, y si ésa no sale, primero horizontal y
después vertical. Alcanza con que **una** esté libre entera, codo incluido, y
cada pata se consulta como un paso derecho —las dos caras, la que se deja y la
que se entra, y quién está parado dónde—. La consecuencia visible es que no se
cruza el vértice de dos paredes en diagonal, pero sí se pasa si hay por dónde
rodear. En la ROM es `puede_celda_diag`, que llama dos veces a `puede_celda`
corriendo `celda_x`/`celda_y` hasta el codo y devolviéndolas; del lado de
Python es `eventos.puede_en_diagonal`, con la misma forma.

**No se gira hacia el rincón.** El charset tiene cuatro poses y ninguna apunta
a un rincón, así que `UpdateFacing` hace otra cosa: si la pose de antes es una
de las dos componentes del paso se queda como está, y si no se da vuelta 180°.
Caminar arriba-derecha mirando abajo deja mirando arriba; mirando arriba no
cambia nada.

Y eso obliga a saber la pose de **antes**, que no siempre está puesta: en
veinte de las veintiséis rutas la diagonal es la primera orden, así que en la
ranura todavía está `RUTA_EV_SIN_MIRAR` y la pose de verdad es la de la página
del evento —`npc_buf + 10`, la misma que usa el dibujo—. `encarar_diagonal` la
resuelve ahí y la escribe; del lado de Python es `Ruta.mirando_pagina`, que
`Estado.ruta_de_evento` saca de `collect_npcs` igual que la velocidad.

Ahí hay una asimetría que conviene tener anotada: **la ROM lee esa pose viva**
—el refresco reescribe `npc_buf + 10` cuando un evento cambia de página— y la
referencia se queda con la del mapa recién cargado. Que las dos coincidan no es
suerte: los 21 eventos del juego que caminan una diagonal **miran para el mismo
lado en todas sus páginas**, así que no hay refresco que las separe. El día que
eso deje de ser cierto, `miradas` tiene que pasar a leerse de la página activa.

Lo demás sale por tabla y no por comparaciones: `paso_dx`/`paso_dy` pasaron a
ocho entradas, y con eso mover la celda, descontar los pixeles que le faltan al
paso —en diagonal hay que descontar en los **dos** ejes— y sumar el
desplazamiento adentro de un salto quedaron escritos una sola vez cada uno.

**Cómo se verifica.** Dos casos, `npc-diagonal` y `npc-diagonal-gira`.

El primero no corre en el mapa 6, que es el de siempre y está abierto por los
cuatro lados: ahí la regla de paso no se ejerce. Va en el **mapa 10**, donde el
evento 0 está en (3,10) con una pared pegada a la derecha y otra justo abajo, y
las tres respuestas posibles salen de esa sola celda: arriba-derecha no se
puede por ninguna de las dos eles y se saltea sin costar un cuadro,
abajo-izquierda **sólo** se puede rodeando primero por la izquierda —o sea que
la salva la segunda ele— y arriba-izquierda se puede por las dos. Medido contra
un control: la ruta que baja en diagonal mueve al evento 340 pixeles respecto
de una que espera, y la trabada da cero contra ella.

El segundo es el giro de 180°: el evento mira a la izquierda y camina
abajo-derecha. Da idéntico a mirar a la derecha desde el principio y distinto a
mirar hacia abajo, que es lo que separa la regla de RM2k de "no girar nunca".

#### El cronómetro

`TimerOperation`, con sus tres operaciones: poner, arrancar y parar. Se dibuja
arriba a la izquierda con cinco glifos de la imagen de System —los diez dígitos
y los dos puntos, de 8x16 a partir de (32,32)— como diez objetos de 8x8 con
prioridad 3, que es la que los pone adelante de las dos capas. Los glifos van al
final del banco de sprites, en una fila de dieciséis: el glifo `i` ocupa el tile
`TIMER_BASE + i` y el `TIMER_BASE + 16 + i`, o sea su mitad de arriba y la de
abajo. Se llevan una de las ocho paletas de sprite, así que en una ROM con
cronómetro un mapa puede usar siete personajes y no ocho.

Tres cosas salen de leer RM2k y no de mirar la pantalla:

* **Al llegar a cero desaparece.** `Game_Party::UpdateTimers` llama a
  `StopTimer` cuando los segundos dan cero, y `StopTimer` apaga la cuenta **y la
  visibilidad**: el último valor que se ve es 00:01, no un 00:00 congelado.
* **El tinte no lo toca.** `Priority_Timer` es 140 y `Priority_Screen` 90: en
  RM2k la pantalla se oscurece y el cronómetro no. Acá el tinte es una
  transformación de CGRAM, así que `aplicar_tinte` vuelve a subir la paleta del
  cronómetro sin teñir. Puede hacerlo porque los dígitos tienen paleta propia;
  la ventana de mensaje no puede, porque la suya está en la mitad del mapa, y
  por eso ésa sí se tiñe.
* **Los dos puntos parpadean** medio segundo sí y medio no, que es el
  `frames % 60 < 30 -> continue` de `Sprite_Timer::Draw`.

La cuenta no se guarda en cuadros sino partida en segundos y resto, y eso no es
una optimización sino lo que evita dividir por 60 sesenta veces por segundo:
bajar un cuadro es restarle uno al resto, y cuando da la vuelta baja un segundo.
Los cuatro dígitos se recalculan ahí, una vez por segundo. El tope son 1092
segundos —dieciocho minutos—, que es lo que entra en la cuenta de cuadros de
dieciséis bits; el cronómetro más largo del juego son diez minutos.

**No destraba ninguna página**, y está medido: las seis del juego que usan
`TimerOperation` están todas cortadas por otra cosa. La que interesa es el
despertador del pad de Talan —mapa 7, evento 4—, que necesita además
`TintScreen` con saturación, `ChangeGold` y cinco órdenes de ruta que no
caminamos.

**Cómo se lo mira:**

    just snes-timer                                  # diez minutos
    just snes-timer 6 "1 1" "2 10" "2 40 59 61" "12 0 0 50" 10 timer-cero

Los dos casos corren con la pantalla teñida desde el cuadro 13, que es lo que
prueba que los dígitos no se tiñen. El primero mira el parpadeo y el cambio de
segundo —el 61 lleva 10:00 a 09:59— y el segundo, la desaparición.

#### Cómo se verifica

La ROM la corre un core de libretro manejado desde Python con `ctypes`
—`tools/retro.py`—, no un emulador con ventana. `retro_run()` avanza **un cuadro
exacto**, la cruceta se contesta cuadro por cuadro y el framebuffer sale del
callback ya en 256x224. No hay servidor X, ni capturas de pantalla, ni recortes,
ni un solo `sleep`.

Eso no es sólo velocidad —la tanda pasó de 19m30s a medio minuto—, es lo que
hace que la prueba signifique algo. Antes decía "apretá derecha ocho segundos,
seguro alcanza": cuántos cuadros se emulaban en esos segundos dependía de la
carga de la máquina, y una máquina ocupada dejaba al héroe corto de la pared y
disparaba la comparación sin que nada estuviera roto. Ahora N cuadros son N
cuadros.

Y los cuadros tampoco se eligen. La referencia camina celda por celda hasta
chocar, así que sabe cuántas son; el paso del héroe son 256 unidades de RM2k
por celda a `PASO_POR_VELOCIDAD` por cuadro —ocho cuadros por celda a la
velocidad 4, la de arranque; desde el 2026-09-10 una ruta con 28 o 29 la
cambia y queda cambiada, como en RM2k, y `cuadros_por_celda(estado)` la
sigue—. `snes_expect.py` escribe ese plan y `snes_correr.py` lo lee. El único número puesto a mano es el
margen: ocho cuadros, una celda, porque la ROM llega uno o dos después —el pad
se lee una vez por cuadro y el primero se pierde—. Cruzar una puerta lleva
dieciséis, porque obliga a cargar el mapa entero y eso la referencia no lo
modela: medido, siete cuadros.

**Andan los tres cores instalados —snes9x, bsnes y mesen-s— y los tres dibujan
el mismo cuadro a 15 bits**, que es la precisión a la que se compara: 0 pixeles
de 57344, medido en el mapa 7 a los 180 cuadros. Que tres emuladores
independientes coincidan es lo que vuelve creíble a cualquiera de ellos. Los
tres tardaron en andar por errores del frontend y no de ellos —bsnes ignora los
datos de la ROM y abre el archivo él mismo, mesen-s quiere los callbacks después
de `retro_init` y un directorio de sistema—; el detalle de qué pedía cada uno
está en el docstring de `tools/retro.py`.

Se elige con `CORE`: `CORE=bsnes just snes-heroe 7`. La tanda corre en snes9x
porque es 23 veces más rápido —2747 cuadros por segundo contra 121—, y bsnes
entra por `snes-bsnes`, dos casos que cuestan veinte segundos. Antes de todo
esto había un `MOTOR=mednafen` que corría la tanda por el camino viejo, y se
sacó: mantenía cinco ramas y los segundos elegidos a ojo, y no lo corría nadie.
Un camino que ninguna prueba ejecuta es, en este repo, la manera en que
sobreviven los errores.

`just snes-hitos` corre seis mapas, uno por cada cosa que puede romperse:

    73, 18, 119   los que cerraron los hitos anteriores: tienen que seguir en cero
    6             recorre 100 celdas por los dos ejes: la ventana da tres vueltas
    8             Lashe City, que además pide el otro reparto de VRAM
    52            1000x80, con 40 KB de grilla que cruzan el corte de banco
    1             el primero del juego: la capa de encima se lleva 4 paletas
    348           el caso opuesto: el fondo usa 95 y encima fusiona 27

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
de `--map-id` primero y después los de `--mapas` sin repetir. Está escrita igual
en el conversor y en la referencia a propósito, porque si no compararían dos
mundos distintos, y por eso mismo equivocarla los equivoca a los dos juntos y la
comparación sigue dando cero. Ese lado se revisa leyendo, no corriendo.

Y tres más para las prioridades de objeto contra la capa de encima, que es por
donde ya se coló el cuarto error. `snes-evento` deja al héroe tapado, pero
entero: los 768 pixeles de su sprite están debajo de la capa, así que un héroe
que directamente no se dibujara daría la misma pantalla. Las dos paradas en la
celda (66,40) del mapa 1 son la misma escena con un solo bit distinto —ahí la
capa tapa 512 de 768 y la silueta tiene que partirse en el lugar exacto—:
primero con el héroe en prioridad 1, debajo, y después con `snes-encima`, que lo
sube a prioridad 2 y lo pone adelante. Entre las dos referencias hay 284 pixeles
de diferencia, así que el par no puede dar cero por casualidad.

Y una ruta forzada, `snes-ruta`, que es la única prueba que compara al héroe
**mientras** camina un guión y no donde termina. La diferencia importa: los dos
errores que destapó —los dos de la referencia, no de la ROM— eran del contador
de cuadros del ciclo de animación, y ninguno de los dos se ve en el cuadro
final, donde el héroe ya está parado. Compara cuatro cuadros de una ruta de doce
celdas con esperas en el medio, elegidos de modo que cada error conocido dé rojo;
el comentario de la receta dice cuáles y por qué. Corre en el mapa 6 porque es
mudo, que cuando se eligió importaba: el arranque duraba distinto con música y
sin ella. Desde el 2026-09-05 dura siempre lo mismo y eso dejó de pesar.

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

Qué mapa elegir para eso no se adivina mirando el tamaño —uno enorme lleno de
paredes frena en la tercera celda—, así que `tools/snes_recorrido.py` camina
todos los mapas con las mismas reglas que la ROM y dice cuánto se recorre en
cada dirección.

Y no todo se llega caminando. Una caminata termina siempre contra un borde del
mapa, que es justo donde la cámara queda pegada; hay estados que sólo se ven en
el medio. `just snes-parado MAPA TX TY` planta al héroe en una celda elegida y
compara sin caminar, que además no depende de cuántos segundos se mantenga la
cruceta. Así se reprodujo el error de la banda de OAM.

**Dónde recortar la captura se le pregunta a X, no a los pixeles.** Se captura
el display entero de Xvfb y hay que quedarse con los 256x224 de la consola. La
primera versión buscaba el primer pixel distinto del fondo del servidor, que es
negro —y el mapa 1 es casi todo negro. En cuanto los sprites dejaron de
dibujarse envueltos arriba, el recorte se deslizó 93 líneas y la comparación
falló por algo que no tenía nada que ver con la ROM. Ahora `screenshot.sh` le
pide la geometría de la ventana a X y se la pasa a `snes_crop.py`.

Buscar esa ventana tiene su propia trampa: `xdotool search --name` no la
encuentra, porque sin gestor de ventanas mednafen publica `_NET_WM_NAME` y
`search` mira `WM_NAME`. Hay que enumerar y preguntarle el nombre a cada una.

#### Los cuadros perdidos se cuentan

Desde el 2026-09-05 la NMI queda prendida después del arranque y `boot_cuadros`
sigue contando vblanks. Al final de cada vuelta del lazo principal,
`contar_perdidos` mira cuántos pasaron desde la vuelta anterior: uno es lo
normal, y cada uno de más es un cuadro que la vuelta se comió, porque tardó
más que un cuadro y `wait_vblank` tuvo que esperar al siguiente. Se mira al
final de la vuelta y no a la salida de `wait_vblank`, donde la NMI de ese
cuadro puede no haber corrido todavía. `cuadros_perdidos` satura en 255.

Lo lee `snes_correr.py` de la WRAM del emulador, por la tabla de símbolos que
`w65.py --simbolos` deja al lado de la ROM —`<rom>.sym`, que `snes-build`
pide siempre—, y lo imprime en la línea de cada captura cuando no es cero. Es
un dato, no una aserción: **los saltos de mapa pierden cuadros hoy** —la
cinemática de apertura suma 8 en los primeros 300 y 20 al final, todos en
teletransportes— y la comparación ya los cobra donde importan. Lo demás que
se midió el 2026-09-05: abrir un mensaje pierde uno cada tanto, el cronómetro
uno, `saturar` cuatro. Ninguno cambia un pixel de los que se comparan.

Sirve para dos cosas. Para saber **por qué** una comparación da rojo —un
droide un cuadro corrido puede ser un lazo lento, y hasta ahora la única forma
de verlo era trazar la WRAM cuadro a cuadro— y para medir cuánto margen hay:
un lazo de retardo de N ciclos en el lazo principal, y ver desde qué N empieza
a perder. Así salió que el destello de pantalla no entraba en un cuadro y
cuántos milisegundos había, ver "El destello de pantalla". Y de paso, con
`retro.Consola.ram()` y la tabla de símbolos, cualquier variable de la ROM se
lee por nombre: fue lo que dijo que la tabla de páginas se leía de la WRAM.

#### La música no espera al lazo

Hasta el 2026-09-11 la música avanzaba un cuadro por vuelta del lazo, así
que una vuelta de dos cuadros la tocaba a la mitad de velocidad. taro lo
escuchó en la apertura: la lluvia, el tinte, el trueno y el mensaje juntos
pierden cuadro por medio —71 de 140, medido— y el tema se arrastraba. Pidió
que el audio ande siempre, aunque cueste más atraso en la imagen y en los
controles.

Ahora la toca **`irq_musica`, una IRQ vertical en la línea `IRQ_LINEA`**
(112), una vez por cuadro de hardware, tarde lo que tarde el lazo. Va en el
medio de la parte visible y no en la NMI porque el vblank es del DMA del
lazo: el cuadro de música tarda hasta veinte líneas, y en el vblank no sobra
eso. Ninguna pantalla llama más a `music_tick`.

Una interrupción cae en cualquier punto del código principal, y eso pide tres
cuidados:

* **Nada de lo que corre adentro usa la ventana de WMADD ni `temp`.** El
  estado de los efectos de sonido vive en la RAM lejana y se lee con el
  direccionamiento largo, que `w65.py` aprendió para esto (`lda f:$7E30A0`).
* **El fundido del tema multiplica a mano.** El multiplicador y el divisor
  comparten el registro del resultado, y el código principal los usa en
  treinta lugares: una interrupción entre la escritura y la lectura le
  cambiaría la cuenta.
* **Lo que el código principal le escribe a la música va con `sei`**:
  `music_start`, `music_boot`, el `FadeOutBGM`, el pendiente de `PlaySound` y
  el volumen que baja el título. La IRQ no se pierde: se atrasa hasta el
  `plp`.

Lo medido: la demo con un lazo de retardo agregado, que pierde 255 cuadros
contra 108 en 1500, recorre el stream exactamente igual cuadro por cuadro
desde que el tema arranca —1307 cuadros, cero distintos—. `snes-check` sobre
el mapa 67 sigue diciendo que coincide con el MIDI (58 de 60 ventanas). El
atraso de la imagen se trabajó aparte: ver "El costo de la apertura".

#### El costo de la apertura

La otra mitad del pedido de taro: que la escena con lluvia, tinte, trueno y
texto no se arrastre. Medido con una sonda de línea de barrido —una copia de
`main.s` que anota la línea después de cada llamada del lazo—, la apertura
perdía **181 cuadros en 3000**, casi todos en los tres tramos del trueno y en
los mensajes. Ahora pierde **20**, todos sueltos: teletransportes y el cambio
de tinte. Lo que se hizo, en orden de lo que rindió:

* **FastROM.** La cabecera decía `$20`, ROM lenta: cada byte que la CPU saca
  del cartucho —las instrucciones, para empezar— a 2,68 MHz. El código corre
  ahora desde el espejo del banco $80 con `MEMSEL` en 1, que va a 3,58. Los
  bancos $80 a $BF son los mismos que $00 a $3F, así que no se mueve nada: el
  reset y la IRQ entran con un `jml` (que `w65.py` aprendió) y de ahí cada
  `jsr` y `rts` se queda donde está. Es lo que se llevó los tramos del trueno.
* **El compositor de mensajes con los glifos ya compuestos.** Pintaba cada
  fila del glifo dos veces —la sombra y el glifo— y la corría de a un bit hasta
  su fase: unas 25 líneas por carácter, 125 por cuadro con `MSG_CHARS` en 5.
  La x de un carácter es `8 + 6 * columna`, así que cae en cuatro fases y no
  en ocho, y el conversor emite los 95 glifos ya compuestos en las cuatro
  —`fuente_prerender`, con la sombra y el glifo combinados en el orden de
  `Font::Render`—: componer es leer, enmascarar y escribir. El cuadro de un
  mensaje bajó de 134 líneas a 73. Son 59 KB de tablas, y por eso el cartucho
  pasó a 2 MB.
* **La lluvia**: ver "La lluvia", de 58 a 24 líneas en `lluvia_tick` y de 130
  a 84 en `build_oam`.
* **El destello lee sus productos de una tabla** (`prod31_tabla`, 1 KB) en vez
  del multiplicador y el divisor con sus esperas: 20 líneas de 150.

Nada de esto cambia qué se dibuja ni cuándo: la referencia no se tocó, y la
tanda y las pruebas dan igual. La tanda no mide cuadros perdidos —compara por
tick, ver `snes_correr.py`—, así que los números de arriba son de la sonda y
de `cuadros_perdidos`, no de un caso.

### El personaje

Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño de objeto: el más
chico que las cubre es 32x32, así que se rellena con transparente a los costados
y se pierde una cuarta parte de los tiles. Son 192 tiles, 6 KB, las doce poses
de un personaje.

#### Las poses se suben en caliente

Desde el 2026-09-05 **en VRAM vive una pose por personaje**, y las doce de
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
vería. Es la pieza reusable que taro pidió: por acá pasan las poses hoy, y
mañana una imagen de `ShowPicture` o lo que haga falta.

Lo prueba toda la tanda —cada caso con alguien caminando pasa por acá— y en
su caso real, `apertura`: los cuatro de la escena caminando, el tinte apagado
y el primer mensaje abierto, cero pixeles.

Dos cosas se rompieron al hacerlo, y vale la pena tenerlas escritas. Los
glifos del cronómetro se ponían al final de la imagen de VRAM redondeando a
una fila de la grilla; con la imagen chica caían adentro de la última fila del
bloque del héroe, y la primera pose que subía pisaba el 0 y los dos puntos.
Ahora redondean a una fila de bloques. Y la segunda es de la música y está en
"Trampas del hardware": un stream vacío leía un byte más allá del final.

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

#### Los eventos translúcidos van horneados

El "Trans" de una página —`translucent`— en RM2k dibuja el evento con
opacidad 160 de 255. La consola tiene transparencia de verdad, el color math,
pero la aplica a todos los sprites de las paletas 4 a 7 a la vez: un mapa con
translúcidos tendría que dejarles esas cuatro paletas solas, y el 9 —donde
están los fuegos de los barriles que taro pidió el 2026-09-11— lleva once
personajes en las ocho.

Hasta el 2026-09-12 iban **tramados**: parte de sus pixeles se caían, que es lo
que hacían los juegos de la época. Y ahí se vio que en este juego eso no
alcanza. **Los fuegos del mapa 9 están sobre negro casi puro**: no hay nada que
asomarse por los huecos, así que la trama no simula transparencia, agujerea la
llama. Ningún patrón lo arregla, porque el problema no es la densidad.

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
VRAM, poses, la referencia— lo trata como a cualquier gráfico. Quien mire
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
  misma ROM, bsnes y mesen-s coinciden entre ellos y con la referencia
  —truncan—, y snes9x redondea para arriba cuando la suma de un canal es impar.
  Son trece pixeles y no se ven, pero es **la primera vez que el emulador de la
  tanda se aparta de la consola**: si algún día se compara color math, el caso
  va a `snes-bsnes`.

**Menos el save point**, que desde el 2026-09-12 va **opaco**: está en
`rm2k.SIN_TRAMA` y `lcf` no le pega el sufijo. Es una divergencia deliberada de
RM2k y la referencia hace lo mismo, así que la comparación sigue midiendo. Se
probaron los otros dos caminos y los dos se cayeron: con la trama, en una
pantalla moderna se ve el damero y la llama queda agujereada; con el color math
—que es transparencia de verdad— el objeto deja de animar y el héroe se ve **a
través** del save point. Lo que hace que el tercero valga es que ahora tiene
sus colores: contando sólo las poses que muestra son 13 y le sobra lugar en una
paleta propia, contra los 41 del bloque entero y la paleta prestada de antes.

#### Los quince colores de un sprite

Un sprite va siempre a 4 bits, o sea 15 colores y el 0 transparente, y los
CharSets de este juego tienen entre 20 y 48. Así que se fusiona, y **lo que
importa no es cuántos entran sino cuáles 15**. taro lo reportó el 2026-09-12 en
tres lugares a la vez: las caras de Talan y de Core grises en el menú, Talan
gris en el mapa, y el save point "que en algún momento perdió uno o dos colores
y pasó de azul/celeste/blanco a gris". Eran tres causas distintas.

**El criterio de fusión.** `pixeles.merge_least_used` mataba al color con
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
en tiles y en VRAM desde el 2026-09-05 y nunca había bajado al conteo de
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

Desde el 2026-09-11 el NPC que el héroe dispara —con A o por contacto— se da
vuelta hacia él mientras dura su página, como en RM2k. Las reglas están en
GIRO, en `tools/eventos.py`, y la ROM las sigue en `giro_disparar`.

Lo difícil era la VRAM: los quietos comparten ranura por (CharSet, índice,
pose), así que subirle otra pose a uno giraría a todos sus gemelos. El
conversor le reserva a cada mapa que lo necesite **una ranura de giro**, un
bloque de 16 tiles más, y le pone al cartucho las doce poses de cada gráfico
que puede girar. El quieto que gira se muda ahí y se le sube la pose que mira
al héroe; al terminar vuelve a su ranura compartida. Uno que camina o anima
quieto gira en la suya. El estado vive en la RAM lejana y la página lleva dos
bytes más —ahora son 32— con la entrada de sus poses y su pose, que es lo que
un refresco compara para saber si el giro sobrevive a un cambio de página.

Un error que valió un caso: el giro guardaba la **fila** del NPC, y las filas
se reordenan cuando alguien camina. Al terminar le devolvía el tile al evento
que había quedado en esa fila. Ahora se la busca por evento cada vez. Lo
encontró `bum-vuelve`; `gemelo` mira el quieto con un gemelo al lado.

### La colisión

Toda la lógica de RM2k vive en `tools/rm2k.py`, fuera del conversor y de esta
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

    parado     héroe en (160,112)   0 pixeles distintos de 57344
    derecha    héroe en (224,112)   0     frena en la celda 14 de 19
    izquierda  héroe en  (48,112)   0     en la 3
    arriba     héroe en  (160,80)   0     en la 5
    abajo      héroe en (160,160)   0     en la 10

Que frene en celdas interiores y no en los bordes del mapa es lo que dice que la
tabla se está mirando de verdad.

### La pila y la BSS comparten los ocho kilos

El banco 0 de RAM son ocho kilos: la página directa, la BSS y **la pila**, que
arranca en `$1FFF` y crece hacia abajo, contra la BSS. No hay más: la pila del
65816 vive en el banco 0 y ese banco es el espejo de `$7E0000`-`$7E1FFF`, así
que los `$7E2000` para arriba no le sirven.

Hasta el 2026-09-06 nadie contaba ese choque. `w65.py` comprobaba que la BSS
entrara en los 7936 bytes del área, y entraba: llegó a ocuparlos **exactos**, y
entonces el primer `jsr` empezó a escribir arriba de `pal_buf`, que es lo último
que hay. Y así estuvo un rato, porque la BSS venía dejando catorce bytes y la
pila más honda medida son veinticuatro: le pisaba diez bytes a la cola de la
paleta y no se notaba.

Lo que sí se notó: catorce bytes más de BSS —los del `PanScreen`— y el caso
`core-puerta` se caía en el cuadro 406 con **la RAM entera pisada**. No al
armarse, no al arrancar: cuatrocientos cuadros adentro de una escena. Costó una
tarde llegar, y lo que la cerró fue reproducirlo con el `main.s` de antes más
catorce bytes de relleno: ahí quedó claro que no era el código nuevo sino el
lugar donde caían las variables.

Dos cosas salieron de eso, y las dos van juntas:

* **`w65.py` reserva la pila.** `PILA_RESERVADA` son 256 bytes que la BSS no
  puede tocar, y pasarse es un error al armar. El número está medido: la pila
  más honda de la tanda —`core-puerta`, con el intérprete adentro de una NMI—
  baja 24 bytes, y la cinemática de apertura entera, 28. Es el mismo agujero
  que ya había tenido el ZEROPAGE, y la misma cura: un área que no se controla
  se desborda en silencio.
* **Se aflojaron dos topes, con la medida al lado.** `NPC_MAX` pasó de 127 a
  104 y `EV_MAX` de 128 a 120. El techo de `NPC_MAX` lo pone OAM —128 objetos,
  uno es el héroe— pero el mapa con más filas de todo el juego tiene **99**, y
  el que más eventos tiene, **114**; los dos medidos sobre los 328. Son 416
  bytes, y ninguno puede quedar corto en silencio porque el conversor corta si
  un mapa se pasa.

Hoy la BSS termina en `$1E5F` y quedan **417 bytes** hasta la pila, de los
cuales 256 son la reserva. Lo que siga pidiendo RAM tiene que aflojar algo, y
ahora `w65.py` lo va a decir en vez de dejarlo pasar.

### Las tablas van en el banco 0

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 al arrancar y nunca lo tocamos, así que una
tabla en otro banco se lee del lugar equivocado — sin ningún error, con bytes
que casualmente están ahí.

Pasó con la tabla de colisión: la ROM leía su propio código como si fuera
pasabilidad, y el personaje no se movía. Y pasaba desde antes con las tablas de
`ppu_reset`, que viven en el mismo segmento: **ese arreglo estaba funcionando a
medias.** Lo que sí funcionaba eran las escrituras directas —apagar el HDMA, los
scrolls— y los borrados por DMA, que llevan el banco explícito. Alcanzó para que
la corrupción de pantalla desapareciera, y por eso no se notó.

Ahora hay un segmento `TABLAS` que el enlazador pone en el banco 0. Todo lo que
la CPU recorra con un índice tiene que estar ahí.

**Y el banco 0 son 32 K, así que la que crece con el contenido se muda.** Van
tres: la tabla de bloques, la de textos y, desde el 2026-09-12, `mapa_tabla` —el
registro de 144 bytes por mapa—. Con los 28 mapas de Lashe City eran 4 KB sobre
los 530 que quedaban libres. Una tabla mudada se lee con `lda f:tabla, x`, que
lleva el banco en la instrucción y no en el registro de banco de datos; cuesta
un byte por instrucción y **obliga a que el índice sea X**, porque el
direccionamiento absoluto largo indexado con Y no existe. Los dos usos de
`mapa_tabla` con Y pasaron a X, con X yendo y volviendo por la pila.

Y una tabla mudada necesita su `.bloque` igual que las de acá abajo: la primera
versión de esto no lo tenía, `mapa_tabla` cayó en `$03FFB1` y sus 144 bytes se
partieron contra el final del banco. Lo cobró un solo caso de la tanda —el mapa
5 arrancando en negro—, y los demás no lo vieron porque su tabla caía en otro
lado. Es exactamente la clase de error que aparece o desaparece al agregar un
byte en cualquier otra parte del cartucho.

Y lo que no entre en un banco no puede recorrerse con un índice, punto: la
grilla de celdas llega a 40 KB. Ésa se lee con un puntero de 24 bits, y ahí
aparece la otra cara de LoROM: **un banco sólo tiene sus 32 K de arriba**, así
que pasarse del `$FFFF` no lleva al `$0000` del banco siguiente sino a su
`$8000`. Dos rutinas de diez líneas, `ptr_mas` y `ptr_menos`, son las únicas que
saben eso; todo lo demás las usa y se olvida del tema.

Y una tabla que se recorra con `[ptr], y` sin cruzar de banco **tiene que
declararse con `.bloque`**, que es lo que le dice al enlazador que la ponga
entera de un lado. La tabla de páginas de evento no lo hacía —"sus punteros son
simbólicos", decía el comentario, que es verdad y no tiene nada que ver— y
sobrevivió hasta el 2026-09-05, cuando los sprites del mapa 2 crecieron con
los eventos de tile y la tabla quedó a caballo de `$02FFFF`: la ROM leyó las
últimas páginas desde `$03:0000`, que es el espejo de la WRAM, y con ellas la
página de prueba de la sacudida al borde, que nunca arrancó. La tanda lo cobró
con un fondo corrido seis pixeles y nada que dijera por qué; lo dijo la RAM:
`pg_evento` valía `$5555`, que es con lo que snes9x llena la memoria.

### Cómo está armado

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB. El
65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro puertos. Al
encender, el SPC700 corre una ROM interna con un protocolo de carga; se lo usa
para meterle las muestras y un driver, y después ese driver se queda esperando
pares (registro, valor) que le pasa el 65816.

Eso deja el mismo reparto que en la Mega Drive: **toda la lógica en Python, y en
la consola sólo un intérprete de un stream de escrituras.** El driver del SPC700
son **20 bytes**.

    rom/src/main.s      65816: arranque, carga al SPC700, reproductor
    rom/snes.cfg        enlazado LoROM de 32 KB
    rom/record.sh       corre la ROM sin pantalla y graba el audio a WAV
    tools/spc700.py      ensamblador de SPC700, porque no hay uno empaquetado
    tools/brr.py         codificador del formato de muestras de la SNES
    tools/sdsp.py        registros del DSP y el banco de timbres
    tools/snes_music.py  el MIDI del mapa a muestras y stream
    tools/snes_check.py  compara lo que suena contra el MIDI
    tools/wavtone.py     mide la frecuencia de un WAV, para un tono suelto

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

### Cómo se verifica el ensamblador

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

**Y además hace cuatro controles que ca65 no hace**, los cuatro agregados
después de que el error correspondiente costara una tarde: etiqueta repetida,
constante redefinida con otro valor, el área de RAM que no entra, y el operando
que no entra en su ancho —que es cómo se descubrió que `lda [dp], y` con la
variable fuera de la página directa emitía el byte bajo y leía de otro lado—.

El quinto es el más difícil de encontrar a mano: **el ancho del acumulador en
una etiqueta a la que se llega saltando**. El ensamblador lleva el ancho en
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
la pila y uno termina midiendo eso. Ahora `w65.py` compara el ancho declarado en
cada salto relativo con el de su etiqueta y falla con nombre y línea.

Puesto a andar la primera vez encontró 24 casos en `main.s`, todos
declaraciones que mentían. Once eran viejos y no rompían nada —etiquetas que
arrancan con un `sep`, que llega antes que cualquier inmediato— pero la
declaración era falsa igual; ahora dice la verdad.

### Cómo se verifica la ROM

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

Y hay un corrimiento que no se puede suponer: la ROM tarda casi dos segundos en
llegar a su primer cuadro, porque sube el banco entero al SPC700 por el
protocolo de la ROM interna, que va byte por byte con acuse —ver "El arranque
dura siempre lo mismo"—. La primera vez que se midió con muestras reales el
puntaje bajó a 80%, y no era el audio: era la búsqueda de corrimiento, que sólo
miraba el primer segundo y alineaba las ventanas con las notas equivocadas.
Ahora se busca dónde empieza a haber señal y se afina alrededor.

También se controla el pico del WAV. El DSP suma las ocho voces y recién después
aplica el volumen general, sin limitar en el medio: la primera versión saturaba
(pico 32768 clavado) y hubo que bajar el techo por voz. Los números de `sdsp.py`
salen de medir, no de la teoría, porque la teoría supone que todas las voces
pican juntas y en fase y eso no pasa nunca.

### El parche de bsnes

`tools/bsnes-wram.patch` es un parche para **bsnes-libretro**, no para este
repo. Existe porque el reloj de la tanda le pregunta a la ROM en qué vuelta del
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
    git am < .../tools/bsnes-wram.patch
    make -j$(nproc)
    cp bsnes_libretro.so /usr/lib/libretro/

Probado leyendo `vueltas` con el core parcheado: bsnes declara 131072 bytes y
da los mismos números que snes9x, cuadro por cuadro. `just snes-bsnes` pasa sus
cuatro comparaciones.

### Trampas del hardware

Todas éstas costaron horas y ninguna da error: la consola hace algo distinto de
lo que uno pidió, en silencio. Están acá porque van a volver.

**Un DMA de tamaño cero transfiere 65536 bytes, no ninguno.** Un mapa sin capa
de encima mandaba una paleta vacía y arrasaba CGRAM entera, paletas de sprites
incluidas. Cualquier tamaño que salga de un conteo tiene que garantizarse
distinto de cero.

**CGRAM y VRAM sólo aceptan escrituras con el PPU sin dibujar.** Obvio dicho
así, y sin embargo mordió dos veces el mismo día, las dos cuando el intérprete
de eventos se mudó de `cargar_mapa` —donde la pantalla estaba apagada— al lazo
principal, donde no. Un teletransporte cargaba el mapa nuevo y no llegaba nada a
la VRAM: se seguía viendo el viejo, como si el salto no hubiera ocurrido. Y un
tinte entraba **a medias**: quedaban teñidos la capa de encima y un sprite, y el
resto no, según qué escritura pescara el vblank.

Lo segundo no lo vio la tanda: snes9x acepta esas escrituras y mednafen no. Lo
encontró taro jugando, dos veces seguidas.

Y la salida que se le dio entonces —apagar la pantalla a mitad del cuadro para
escribir el tinte— era otra trampa: en el hardware son líneas negras mientras
dura la cuenta, y en el emulador un cuadro teñido de la mitad para abajo. Lo
vio la sacudida de pantalla, la primera receta que compara cuadro por cuadro.
Desde el 2026-09-05 el tinte se arma en RAM y se sube en el vblank, como todo
lo demás: ver "La sacudida de pantalla".

**Un byte más allá del final es de otro.** `music_frame`, con un stream
vacío —un `OP_END` solo—, volvía al principio, leía el `OP_END` otra vez y se
iba, dejando el puntero un byte después del final por el `advance`. Al cuadro
siguiente leía **ese** byte como opcode. Fue `$FF` desde siempre, de casualidad
—el primer byte del bloque de al lado—, hasta que las poses en caliente
cambiaron el reparto de la ROM y pasó a ser `$00`: "escribí un registro del DSP
y esperá el eco del SPC700", y otro, y otro, media pantalla por cuadro, y el
lazo principal a la mitad de velocidad. Ningún mapa con música lo tiene, y los
mudos son casi todos. Lo delataron tres casos de la tanda con un cuadro
repetido, y lo ubicó una sonda: la línea de barrido al final de cada fase del
lazo, leída de la WRAM con `retro.py`. Ahora un stream vacío apaga la música.

**La RAM arranca con basura, y el emulador rápido la arranca de otra manera.**
Ésta es la trampa que hace invisibles a las otras: una variable que nadie
inicializa puede dar verde en las 60 comparaciones y fallar en hardware real.
Pasó con `ruta_n`/`ruta_i`, que sin poner en cero hacían creer a `move_hero`
que había una ruta forzada pendiente, y el héroe no leía el pad nunca. La tanda
entera estaba verde.

Acá decía "snes9x llena la WRAM de ceros al encender", y **no es cierto**. Se
midió el 2026-09-04 con `msg_abierto`: sin su `stz`, `snes-cerrar` se cae en las
doce corridas de snes9x, y da igual dónde caiga la variable —se probó pegada a
`port0` y al final de BSS—. O sea que snes9x tampoco deja esos bytes en cero.

Lo que sí se sostiene es más fino, y conviene tenerlo escrito porque cambia
cuándo hay que desconfiar: lo que snes9x deja es **siempre lo mismo**, así que
esconde los errores que un patrón fijo esconde y no los otros. Medido el mismo
día, con el error de `ruta_n`/`ruta_i` puesto de vuelta a mano y diez corridas
por core:

    snes9x   0 de 10 en rojo
    bsnes    2 de 10

O sea que sea cual sea el valor que snes9x deja ahí, hace que `ruta_i < ruta_n`
dé falso las diez veces, y el error desaparece. `msg_abierto` no tiene con quién
empatar: alcanza con que no sea cero y se ve siempre. La regla práctica no
cambia —toda variable se inicializa— pero la razón sí: no es que snes9x sea
benévolo, es que es previsible.

Contra eso está `snes-bsnes`, que corre dos casos con `bsnes_entropy=High`:
bsnes llena la WRAM de basura, como la consola. Comentando esas dos líneas de
`main.s` y corriendo veinte veces el mapa 7, la basura rompe el cuadro 11 veces
de 20 —con `Low`, 3; con `None`, ninguna—. O sea que no lo agarra siempre, pero
lo agarra la mitad de las veces y sin que nadie tenga que jugar. Con la ROM sana
las veinte corridas dan el mismo cuadro, así que esto no vuelve inestable a la
tanda.

La carga de mapa se arregla apagando la pantalla, como ya hacía `cruzar_puerta`.
Para el tinte se intentó primero diferirlo a `flush_video`, que corre en el
vblank, **y no alcanza**: `aplicar_tinte` arma tres tablas de canal de treinta y
dos entradas y sube tres paletas por DMA, y eso se pasa del vblank. El resultado
era un tinte a medias distinto en cada intento —una vez la capa de encima y un
sprite; otra el fondo teñido, el héroe en negro y los NPCs sin tocar—. La única
forma que aguanta es apagar la pantalla, igual que para cargar un mapa: cuesta
un cuadro en negro, que en RM2k tampoco desentona porque el motor original funde
a negro en las transiciones.

**Un bloque de cero bytes no es un bloque.** La subida al SPC700 va por el
protocolo del IPL —dirección, un puerto en no-cero, el índice—, y con cero bytes
del otro lado nadie contesta: la ROM se queda esperando el handshake. Pasaba con
cualquier mapa sin música, que son la mayoría. Lo peor era el síntoma: el
cuelgue es *después* de encender la pantalla y dibujar el mapa, así que la ROM
tenía toda la pinta de andar y lo único raro era que el héroe no se movía. Es la
misma familia que el DMA de tamaño cero, y la misma lección: cualquier cantidad
que salga de un conteo hay que garantizarla distinta de cero antes de usarla.

Su primo: **un stream de música vacío colgaba `music_frame`**, porque al llegar
al final vuelve a empezar y lo primero que encuentra es otro final. Los dos
estuvieron escondidos mientras `musicdata.inc` lo generaba una receta aparte y
siempre tenía un tema de verdad; aparecieron el mismo día, apenas el conversor
empezó a emitir la música del mapa.

**Un DMA no sigue el mapeo de LoROM.** Su dirección de origen se incrementa
linealmente, y el byte que sigue a `$02FFFF` no es la ROM del banco 3 sino la
RAM. Un bloque que cruce ese límite se sube bien hasta ahí y basura después.
`w65.py` tiene `.bloque N` para rellenar hasta el banco siguiente, y el
conversor lo declara antes de cada bloque. Ese relleno es lo que terminó
obligando a pasar el cartucho de 128 a 256 KB: los datos entran, lo que no entra
es el acolchado de bloques de 25 y 42 KB.

**Un puntero de 24 bits tampoco lo sigue.** El byte que sigue a `$01FFFF` está
en `$028000`, no en `$020000`: un banco de LoROM sólo tiene sus 32 K de arriba.
Cualquier tabla que no entre en un banco —la grilla de celdas llega a 40 KB—
tiene que avanzarse con esa corrección. Está en `ptr_mas` y `ptr_menos`.

**`lda tabla, x` direcciona el banco de datos, no el banco de la tabla.** Ese
registro vale 0 y no lo tocamos, así que todo lo que la CPU recorra con un
índice tiene que estar en el banco 0 — de ahí el segmento `TABLAS`.

**Los registros de scroll comparten un único latch entre todos los planos.**
Escribir BG1 bajo, BG2 bajo, BG1 alto, BG2 alto mezcla los valores. Hay que
completar cada registro antes de pasar al siguiente.

**El PPU muestra la línea `vofs+1` en el primer scanline**, no la `vofs`. Con el
scroll en 0 el mapa queda corrido una línea.

**La X de un objeto tiene nueve bits**, y el noveno vive en la tabla chica de
OAM. Sin él, un sprite en `-8` se lee como positivo y salta al otro lado.

**La Y de un objeto tiene ocho, y la pantalla 224 líneas.** Los valores 224 a
255 quedan ambiguos, y el PPU los resuelve siempre para el mismo lado: los lee
como "un poco más arriba del borde de arriba" y dibuja el objeto envuelto. Un
NPC que se iba por abajo se guardaba con una Y de esa banda y reaparecía arriba
—primero los pies, después entero— antes de desaparecer.

La ambigüedad no se puede sacar, y encima hace falta: es la que hace que un
objeto en `y = -31` muestre su última línea en la línea 0. Lo que no puede pasar
es que le llegue un objeto que de verdad está abajo, así que el descarte de
`emit_object` va en 224 y no en 256. La cuenta de la X es la misma y va en 256.

Ninguna de las caminatas del arnés lo tocaba: todas terminan contra un borde del
mapa, y ahí la cámara está pegada y los NPCs no quedan nunca en esa banda. Por
eso `snes-hitos` ahora incluye una parada quieta en (75,88) del mapa 1, donde
hay cuatro NPCs justo debajo del borde.

**La consola lee los controles sola al empezar el vblank, pero no arranca en el
mismo ciclo.** Preguntar sólo "¿terminó?" pasa de largo y lee registros a medio
armar; hay que esperar a que empiece. Y si antes se hace algo largo —el DMA de
OAM— se llega con la lectura ya terminada y esperar su arranque cuesta el cuadro
siguiente entero.

**OAM sólo se puede escribir en el vblank, y armarla lleva tiempo.** Con treinta
personajes no entra armarla y subirla en el mismo vblank: se sube la del cuadro
anterior apenas abre, y se arma la del siguiente después.

**El ancho de A y de X/Y es estado, y el ensamblador lo cree.** Las directivas
`.a8` y `.a16` no describen: mandan. Un `cruzar:` puesto justo debajo de un
camino que terminaba en `.a8` hereda ese estado aunque se llegue ahí por un
salto con A en 16 bits, y entonces un `and #$00FF` sale con un byte de operando,
el CPU lee dos, y se come la instrucción siguiente. La pantalla queda negra y no
hay ningún error. Toda etiqueta a la que se salte desde otro ancho tiene que
declararlo.

Y la misma trampa del otro lado: `tax` con X de 16 bits transfiere los dos bytes
del acumulador, incluido el alto, que con A en 8 bits nadie tocó y trae lo que
dejó la operación anterior. Una cuenta de direcciones hecha en 8 bits y cerrada
con `tax` funciona mientras ese byte alto sea cero.

**La prioridad de un objeto son los bits 5 y 4 del byte de atributos**, no los
0 y 1: `vhoopppN`. Escribir `$20` creyendo que es prioridad 1 da prioridad 2, y
en el modo 3 el orden es `objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 /
BG1 0 / objetos 0`, así que ese lugar de más cruza justo la capa de encima. El
sprite se sigue viendo, sólo que del lado equivocado de una capa.

Los dos valores viven en un solo lugar, `tools/snes_convert.py`: el de cada NPC
va armado dentro de su byte de atributos y el del héroe llega a la ROM como
`HERO_PRIORITY` en `mapdata.inc`. Tenerlos también escritos en `main.s` era la
duplicación de siempre —dos lados que se pueden equivocar igual— y así fue como
este error sobrevivió a la primera comparación.

**Un `jsr` te devuelve `X` e `Y` como se le da la gana.** No hay convención de
llamada acá: cada rutina usa los índices para lo suyo. Cuando un registro es un
cursor que tiene que sobrevivir a una llamada —el del bytecode del intérprete lo
es— hay que guardarlo con `phy` en el que llama, y el que llama es el único que
sabe que hace falta.

**La consola arranca con lo que dejó el programa anterior.** El emulador arranca
en cero. Hay que escribir los 43 registros del PPU, no sólo los que se usan, y
cortar el HDMA antes que nada.

**En una línea no entran más de 34 tiles de 8x8 de sprite.** Un objeto de 32x32
aporta cuatro, así que a partir de nueve personajes juntos se pierden los
últimos. No tiene arreglo; se declara y se excluyen esas líneas de la
comparación.

### El inventario, y lo que una condición de ítem hace

RM2k elige la página de número más alto cuyas condiciones se cumplen. Las de
switch y de actor en el grupo la ROM las evalúa desde siempre; las de **ítem**
desde el 2026-09-10 a la noche, cuando apareció el inventario. Un byte por
ítem del LDB —450, `ITEMS_N` los cuenta con el 0 que no se usa— en la RAM
lejana, `FAR_ITEMS`, indexado por el número de RM2k; `ChangeItems` compila a
`OP_ITEM` con el ítem y cuánto se suma, con signo, y la cuenta queda en
[0, 99] como `Game_Party::AddItem`. El juego lo usa 509 veces, siempre con
ítem y cantidad constantes. Cambiar un ítem pide el refresco de páginas, como
`CommandChangeItems`. La página lleva el ítem que pide en +28 y
`condiciones_ok` mira que la cuenta no sea cero —`GetItemCount`, sin equipo
todavía—. El inventario viaja en la partida, que por eso mide 773 bytes y las
ranuras de SRAM van cada 1024.

Durante un día, antes de eso, la página con ítem se emitía con `switch_a =
SWITCH_IMPOSIBLE` —un switch que nadie prende— porque `ChangeItems` se
aceptaba sin hacer nada y el grupo no tenía ítems jamás; la máquina quedó en
`rm2k.CONDICIONES_IMPOSIBLES`, vacía. Y antes de eso el evento entero quedaba
afuera: no se dibujaba, no frenaba y no disparaba. Son 45 eventos; EV0041 del
mapa 8 es uno.

**Y la rama por objeto, desde el 2026-09-13.** Es la misma pregunta que la
condición de página —`GetItemCount(id) > 0`, sin `GetEquippedItemCount` porque
no hay equipo— pero adentro de un `ConditionalBranch`, la clase 4. Compila al
mismo `OP_SI` que el switch, con el número de RM2k adelante y la polaridad tal
cual —0 es "tiene que tenerlo"—, así que la ROM la decide con el mismo `eor` y
sin una rama de más; lee el byte de `FAR_ITEMS` por el mismo camino que
`condiciones_ok`. Son **+20 páginas del juego entero**, y estuvo sin hacerse
más tiempo del que hacía falta: figuraba como "pide inventario, que no hay" en
un comentario que quedó viejo el día que el inventario apareció.

### Las dos preguntas de actor de una rama

`ConditionalBranch` clase 5 es "el héroe", y adentro lleva siete preguntas
distintas —el `switch (com.parameters[2])` del caso 5 de
`Game_Interpreter::CommandConditionalBranch`—. La ROM contesta tres desde el
2026-09-13: **está en el grupo** (la 0, que ya estaba), **sabe esta
habilidad** (la 4) y **tiene puesto este objeto** (la 5). Son **+28 páginas
del juego entero**, de 5170 a 5198 de las 5603 disparables, y van juntas
porque van juntas en el juego: las 10 páginas que preguntan por una habilidad
preguntan además por el equipo, así que la 4 sola destraba cero y la 5 sola
+18.

Las dos nuevas no entran en `OP_SI`, que tiene un solo operando: llevan el
actor **y** el ítem o la habilidad. Por eso hay un opcode aparte, `OP_SI_ACTOR`
—sub, actor en un byte, dato en una palabra, destino— con el destino último,
como todos, porque es lo que el conversor parchea al cerrar la rama. Ninguna de
las dos tiene polaridad: RM2k no se la da, la rama de abajo es el `else`.

El **equipo** es estado de verdad: `FAR_EQUIPO`, cinco palabras por actor, que
arranca del `initial_equipment` del LDB, que la pantalla de equipo escribe y
que viaja en la partida. La ROM lee las cinco ranuras por el puerto de la WRAM
y se da por cumplida con que el ítem esté en cualquiera, que es el `||` de los
cinco `Get*Id()` de easyrpg.

La **habilidad** no lo es, y conviene saberlo antes de apoyarse en ella: sale
de una tabla del cartucho —`sabe_hab`, 81 entradas para los 60 actores del
LDB— que arma `batalla.aprendidas_de`, la misma función con la que contesta la
referencia. Es `Game_Actor::LearnLevelSkills` a secas: las de nivel menor o
igual al `initial_level`. **Va aparte de `actor_hab`**, que es la lista del
menú de la pelea: ésa lleva sólo las que este port sabe ejecutar y sólo de los
actores que pueden entrar al grupo, y `IsSkillLearned` no filtra ninguna de las
dos cosas. Lo que falta para que sea estado es `ChangeSkills` —20 comandos en
el juego, y uno de ellos le enseña la 152 a Arden, que es justo la que
preguntan los mapas 47 y 48—; mientras no compile, la respuesta es la del LDB y
nada la mueve. Las páginas que enseñan no compilan, así que no hay media
implementación corriendo: hay una deuda con su número.

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

**La condición por variable se evalúa** desde el 2026-09-10 a la noche: la
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
—`indexar_variables`, un tercio de segundo— y el bytecode habla de ranuras,
así que cuestan 162 bytes de RAM y no diez kilobytes. La referencia arma el
mismo índice, que es lo que hace que los dos lados lean el mismo stream. Hasta
el 2026-09-10 a la noche el índice era de los mapas de cada ROM y una partida
guardada con una ROM no valía para otra con más mapas: las ranuras se
corrían. Viven en la RAM lejana —`FAR_VARIABLES`, por la ventana de `WMDATA`,
como el estado de los paralelos— y viajan en la partida guardada, que por eso
pasó de 256 a 512 bytes de SRAM por ranura.

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
`ev_pos_buf` en la ROM, `Estado.heroe` y `Estado.pos_ev` en la referencia, o sea
adonde una ruta forzada o un `ChangeEventLocation` dejaron al personaje.

Con qué se compara: en la ROM el intérprete corre en `eventos_tick` y el héroe
se mueve después, en `move_hero`, así que la página de un cuadro ve la celda con
la que terminó el cuadro anterior. La referencia hace lo mismo porque quien
escribe `Estado.heroe` es `cuadro_de_eventos`, que va en el mismo lugar del
lazo.

**El azar es el mismo de los dos lados.** Un xorshift de dieciséis bits —`x ^=
x << 7; x ^= x >> 9; x ^= x << 8`—, sembrado en el reset, instrucción por
instrucción en `azar_siguiente` de `main.s` y de `eventos.py`. Por eso una
página con azar se compara pixel por pixel: el Tram Officer del mapa 9 tira un
número de 0 a 100 y dice "It's here!" si sale 90 o más; los dos lados sacan 97.
No hay entropía, y a los efectos de la comparación tampoco la hay en RPG_RT.

`CallEvent` —la página de otro evento, en el lugar— **se compila en línea**
desde el 2026-09-12: el cuerpo del llamado se emite donde está la llamada, y no
hace falta ninguna pila de intérpretes porque el llamado corre entero antes de
que siga el que llamó. No toca ni la ROM ni la referencia: las dos corren el
mismo bytecode. Si el llamado **no** compila, la llamada se saltea, que es lo
que el port venía haciendo con el comando entero; exigir que compilara costaría
183 de las 221 páginas que compilan y llaman. Con eso el Tram Officer del mapa
9 sube al Hover-Tram, que es lo único que lo usaba en los mapas 1 a 10.

### Lo que falta

* **El presupuesto de muestras, por paquete y no por banco.** Hoy el banco
  compartido entero tiene que entrar en los 64 KB de ARAM, y eso era el límite
  de verdad **antes** del paquete de audio por mapa: ahora en la ARAM viven el
  directorio y un paquete, no el banco. Medido con los diecinueve temas de la
  demo aportando: directorio 617 B, peor paquete 54945 de 63831, o sea que el
  hardware entra de sobra. Lo que no entra es la calidad: repartir los 40 KB de
  `ARAM_BUDGET` entre 45 programas en vez de 27 baja la tasa mediana de 12,5 a
  8,4 kHz **para todos**, incluidos los once que hoy suenan bien. Lo que lo
  resuelve es darle a cada programa lo que su peor paquete puede pagar en vez
  de una parte del banco entero; mientras no esté, los temas que no aportan
  suenan incompletos —del 8% al 70% de sus notas— y el recorte va por
  prioridad: ver "Varios temas en el cartucho".
* **La música, del lado del SPC700.** Hoy la toca el 65816 desde una IRQ
  —ver "La música no espera al lazo"—, y funciona, pero cuesta hasta veinte
  líneas por cuadro y obliga a las reglas de la interrupción. El paso que
  sigue, acordado con taro el 2026-09-11, **no** es un secuenciador en el
  SPC700 como los de los juegos comerciales, sino uno chico que lea el mismo
  stream de hoy desde un buffer circular en la ARAM, a su propio ritmo, y que
  el 65816 sólo mantenga lleno. El conversor y `snes-check` no cambian, y los
  efectos de sonido pasarían allá también. Se encara cuando haga falta el
  margen del lazo, o si en la consola el audio muestra algo que el emulador
  no.
* **El sistema de imágenes, más allá del cartel.** Desde el 2026-09-12 la ROM
  dibuja **un** `ShowPicture` por cartucho: ver "El cartel de 'One year
  previously'", y ahí están los números de lo que costaría el resto —34
  comandos en el juego, 20 carteles distintos, y cinco de ellos de 320x240
  exactos, que con objetos no se pueden hacer—. Los que no entran se siguen
  aceptando sin hacerse.
* **Las órdenes de ruta que faltan.** Son quince las que la ROM entiende
  —mover en los cuatro sentidos, girar en los cuatro, esperar, saltar,
  atravesar paredes y parar o seguir la animación— y `play_sound_effect` se
  acepta sin hacerlo, y la **transparencia** también, desde
  el 2026-09-05: subirla y bajarla de a un octavo son las órdenes 40 y 41, y
  las ocho rutas del juego que las usan son las cuatro pantallas del mapa 2
  atenuándose mientras Manta hackea, que sin eso dejaban afuera la escena
  entera; se pierde el fundido, que sobre tiles de fondo la SNES no hace
  barato. Una ruta que se queda sin órdenes por esto no se emite: RM2k la
  consume entera en el cuadro y no deja nada que esperar. Falta **fijar la
  mirada** —las órdenes 26 y 27, que sobre el héroe se aceptan y se tiran por
  decisión y no por olvido: ver ESTADO.md—. **Moverse hacia el héroe** —la
  orden 9, +33 páginas— y **cambiar el gráfico del héroe** —la 34, +29— se
  hacen desde el 2026-09-12; las otras nueve órdenes de movimiento que faltan
  suman +1 entre todas, medido, y por eso siguen afuera. La
  velocidad ya está, desde el 2026-09-05, con las rutas propias de las
  páginas; **subir y bajar la frecuencia** —las órdenes 30 y 31— desde el
  2026-09-06, ver "La frecuencia se sube y se baja a mitad de una ruta"; las
  **diagonales** —las órdenes 4 a 7, +7 páginas— desde ese mismo día; y
  **cambiar el gráfico sobre un evento** —+25 páginas—, ver "Cambiar el
  gráfico a mitad de una ruta". Las tres últimas van sobre eventos y no sobre
  el héroe. Sigue siendo lo que más corta, aunque bastante menos.

  Y una que apareció midiendo lo anterior, el 2026-09-06: **sobre el héroe, la
  ROM ignora las órdenes 26 a 29** —fijar y soltar la mirada, subir y bajar la
  velocidad— y **la referencia no**. `paso_de_ruta` las saltea con un "acá no
  llegan" que dejó de ser cierto: `Ruta` es la misma clase para el héroe y para
  los eventos, así que la referencia le cambia la velocidad y la ROM lo deja
  caminando igual. En el juego hay 163 rutas sobre el héroe con la orden 28 y
  148 con la 29; **de las páginas que hoy compilan, siete tienen una**, y una
  de ésas es el evento 1 del **mapa 7, Talan's Pad**, que es adonde va el juego
  después del Emitter Room. No lo cobra ninguna prueba porque ningún caso mira
  una de esas páginas, y no es lo mismo que lo de arriba: no es un comando que
  falte sino dos lados que ya no hacen lo mismo. **Las 28 y 29 sobre el héroe
  se hacen desde el 2026-09-10**: su paso dejó de ser fijo —`step_left` cuenta
  medias unidades de RM2k, 128 por celda, y baja `paso_medio_por_vel` por
  cuadro— y la velocidad vive en `FAR_HERO_VEL`, viaja en la partida y queda
  como la dejó la última ruta, que es lo que hace RM2k: sólo la frecuencia se
  repone. Las 26 y 27 se siguen tirando.

  Y aparte, **girar sin moverse** (`turn_90_degree_right` y sus hermanas): no
  está afuera por costo sino por dónde arranca el giro. RM2k gira sobre la
  dirección que el personaje ya tenía, y para un evento que todavía no giró
  ésa es la que trae su página, que la ruta no lee. **Encarar al héroe** y la
  **frecuencia** ya están, desde el 2026-09-04: ver "La frecuencia de la ruta,
  y encarar al héroe".
* **El cartucho es de 512 KB desde el 2026-09-05.** Con las poses en el
  cartucho una vez por ROM, la del arranque con los mapas 4, 1 y 2, ventana y
  música se armaba con 1,6 KB libres de los 224 de datos —el "22 KB" que
  decía esto era de antes de los droides—, y los sprites de los eventos de
  tile la pasaron por 3,7 KB. Así que `ROM_BANKS` es 16, el área de datos
  480 KB y la cabecera dice `$09`. **Es un cambio de mapeo que ningún caso de
  la tanda ve**: los tres emuladores cargan el archivo del doble sin
  preguntar, y el cartucho real lo lee taro con el FX Pak. Y no es la única
  salida: el acolchado de bloques es de **20 KB** en esa ROM —un bloque de
  18 KB que no entra en lo que queda del banco deja 12 KB vacíos—, y un
  enlazador que acomode los bloques en los huecos los recuperaría. No se hizo
  porque el crecimiento sigue: cada personaje que cambia de pose son 6 KB.

  Y dos ideas de taro para cuando haga falta apretar assets, anotadas para no
  perderlas: **paletas calculadas sobre todas las imágenes del juego** a la
  vez —CharSets, ChipSets y texto—, unificando los negros y grises casi
  iguales entre imágenes, con un impacto visual mínimo; y **hornear en un
  ChipSet propio a los sprites que son decoración**, como el público del
  Auditorio, que no se mueve nunca. Ninguna de las dos se encara ahora.
* **Lo que la colisión con los eventos no modela.** Está desde el 2026-09-05
  —ver "La colisión con los eventos"— y deja afuera `overlap_forbidden`, 17
  páginas del juego; el conflicto de un evento con gráfico de tile contra su
  propio bloque; que un evento de contacto de la capa del héroe dispare al
  chocar con él —`CheckCollisonOnMoveFailure`—; y que una ruta forzada que
  no se puede saltear **reintente** el paso bloqueado en vez de saltearlo,
  que es lo que hace `UpdateMoveRoute` con `skippable` apagado. Lo último es
  lo que más cerca está de verse: en la apertura la colisión no frena ningún
  paso, medido, pero el droide del mapa 2 vive de eso.
* **El cartucho es de 4 MB desde el 2026-09-13**: `ROM_BANKS` es 128 y la
  cabecera dice `$0C`. Antes fue de 2 MB, y lo pidieron los glifos ya compuestos
  del compositor de mensajes; los 4 MB los pidieron las tres vueltas del
  2026-09-12 juntas —Lashe City, las animaciones dibujadas y la batalla—, que se
  pasaban por 218 KB.

  **Los dos últimos bancos del archivo no se usan**, y ésa es la parte que hay
  que entender antes de tocar esto. `lorom_address` le da a cada byte del
  archivo la dirección `banco:8000`, y en la consola **los bancos $7E y $7F son
  la WRAM**: un dato ubicado ahí se leería como memoria de trabajo. Se llega a
  ellos por el espejo $FE/$FF, pero entonces un puntero de 24 bits que cruce de
  $7D:FFFF al siguiente —lo que hace `advance`— aterrizaría en la WRAM en vez de
  saltar al espejo, y sería un error silencioso en el peor lugar: un stream de
  música o una tira de mapa leyendo basura a mitad de camino. Así que el archivo
  mide 4 MB justos, que es lo que la cabecera declara y lo que el FX Pak espera,
  y `BANCOS_PROHIBIDOS` hace que el asignador se detenga 64 KB antes.

  La SRAM no se entera de nada: en LoROM vive en la **mitad baja** de los bancos
  $70 a $7D, y el cartucho usa la alta.
* **Los cuadros que el lazo pierde en sus picos.** Ya no los produce el
  teletransporte —el fundido se come la carga, ver "El fundido de los
  teletransportes"— pero siguen: la primera vuelta de una ROM con muchas
  páginas se pasa del cuadro, y también la vuelta en que un fundido termina y
  la página retoma. La referencia no los modela, así que a partir de ahí la ROM
  va N cuadros atrás y sólo se la puede comparar donde la pantalla esté quieta.
  Eso es lo único que le falta a la escena del ascensor para tener caso propio
  en la tanda. La salida no es un desfase a mano en las recetas —eso es un
  número que se ajusta hasta que dé verde— sino aflojar los picos, o que la
  receta lea `cuadros_perdidos`, que ya viaja en la salida de cada captura.
* **Las otras transiciones de RM2k.** El fundido está, que es la que este juego
  usa —`transition_out` y `transition_in` valen 0 en su base—, pero
  `Transition::Type` tiene 38 y un evento puede pedir cualquiera con
  `EraseScreen`/`ShowScreen`. Las de bloques, persianas y barridos no son un
  brillo maestro: piden tapar la pantalla por regiones, que en la consola es
  otra máquina.
* **Los teletransportes que siguen sin resolverse.** Los que están adentro de
  cinemáticas con variables y condiciones que todavía no modelamos. El del mapa
  donde el juego arranca ya no: es automático, entra con los cinco comandos que
  la ROM entiende, y `Blank (Leave START here)` ahora se sale solo.
* **El resto de los temas.** Desde el 2026-09-06 el cartucho lleva **varios**:
  los que pidan los `PlayBGM` compilados, compartiendo un solo banco de
  muestras. Con las primeras secuencias son tres o cuatro y usan 62310 de los
  64512 B de ARAM. El techo no es la cantidad de temas —el banco se achica
  solo— sino la resolución: con los treinta y pico del juego entero cada
  instrumento quedaría en una miga, y sin aviso. Ver "Varios temas en el
  cartucho".

  Lo que subiría ese techo es un **driver que sepa recibir datos**: hoy las
  muestras se suben una sola vez al arrancar con el protocolo del IPL, que manda
  un byte por acuse y desaparece al saltar al driver. Con un banco por tema el
  costo sería medio segundo de transferencia en cada `PlayBGM` —y habría que
  modelarlo en la referencia, que es lo que lo descartó—; con los cuatro
  puertos en vez de uno, en cambio, se acorta el arranque, que hoy son 112
  cuadros dimensionados para una ARAM llena.

  Y un efecto que conviene tener presente: `snes-check` compara el audio contra
  el MIDI **del mapa**, así que donde el tema lo pone un evento hay que
  nombrarlo. Para eso está `just snes-bgm <tema>`.

* **La cinemática de apertura, entera.** Corre con ventana desde el
  2026-09-05 —`rom/build/demo-apertura/`, con los mapas 4, 1, 2 y 3 y
  `escape_newyork` sonando; el 3 entró para que el ascensor lleve a algún
  lado, ver "El ascensor no llevaba a ningún lado"—, y el caso `apertura` de la tanda la compara hasta
  el final con los quince toques de A que la cierran: el tinte se apaga, Core y
  Manta aparecen, el droide camina, Kersh explica su alias, y la página termina
  con dos `ChangeEventLocation` y un switch. De ahí el juego sigue con el
  jugador al mando, y eso ya no lo mira ninguna receta. Lo que la comparación
  **no** cubre es nada en movimiento en un cuadro en que la ROM venga atrasada;
  el toque de A resincroniza los dos lados.
* **Lo que le falta al juego entero, medido.** De las 489 páginas automáticas
  con comandos, hoy compilan enteras **209**. Eran 16 antes de los cuadros de
  texto, 71 con ellos, 87 con las rutas forzadas sobre eventos, 110 con
  FlashSprite, 117 aceptando `PlaySound`, 126 con la saturación del tinte, 137
  con los saltos y las demás órdenes de ruta, 142 con `ChangeEventLocation`,
  177 con `FadeOutBGM`, `PanScreen` y las órdenes 30 y 31 del 2026-09-06, 184
  con las diagonales del mismo día, y **209 con la orden 34** sobre eventos. El
  cronómetro no cambió el número: suma cero, y está medido. Y esto es cuántas
  pasarían a compilar con cada comando que falta —`just snes-destraba`—:

      ConditionalBranch         +27      FullHeal               +1
      ControlVars                +4      FlashSprite            +0
      ChangeItems                +3      CallEvent              +0

  Y aparte, `MoveEvent` con las órdenes de ruta que todavía no sabemos caminar:
  +10 de techo, que es lo que quedaba dándole la 34 y las diagonales **al
  héroe**. La 34 al héroe se hizo el 2026-09-12; quedan las diagonales. Puestos todos juntos se llega a **281 de 489**, y lo que seguiría
  cortando después sigue siendo `MoveEvent`, ahora con 49 páginas —rutas con
  saltos, apuntadas a un vehículo, o de las que le cambian el gráfico al
  héroe—. Después vienen los 16 cuadros de texto con códigos de escape y
  `ShowChoice` con 12.

  Y dos trampas más de las de medir, las dos del mismo día y las dos con la
  misma forma: la columna realista de `MoveEvent` daba **menos** que la base.
  La lista de órdenes de `destraba.py` no tenía la **transparencia**, y su
  filtro pedía que la ruta tuviera al menos una orden; `traducir` acepta las
  dos cosas —la transparencia la tira, y una ruta vacía no la emite—. Ninguna
  de las dos se había visto porque hasta ese día ninguna página tenía a la vez
  una de ésas y algo más que la trabara.

  **Dos veces se corrigió este número, y las dos por lo mismo: medía un techo.**
  La primera versión contaba qué comando corta **primero** cada página
  —ShowMessage 144, CallEvent 98, MoveEvent 60—, y eso no es lo que se destraba:
  una página cortada por un cuadro de texto puede estar cortada además por otras
  cuatro cosas. Corregido eso, quedaba la otra mitad del problema: aceptar un
  código entero cuenta lo que se destrabaría si el comando estuviera hecho **para
  todos los casos que el juego usa**, y una implementación real cubre menos.
  `MoveEvent` sobre otro evento daba +40 contando rutas que la ROM no va a saber
  caminar y blancos que no existen; con las órdenes que ya hace son +16, y con
  todas +31. Por eso `destraba.py` ahora muestra las dos columnas, y los
  candidatos que todavía no tienen filtro hay que leerlos como el techo que son.

  Los cuadros de texto, en cambio, aguantaron las dos correcciones: eran +55 y
  hechos dieron exactamente 55.

  Dos trampas que costaron una medición mal hecha cada una, y que están
  anotadas en `tools/destraba.py` para no volver a pisarlas:

  * RM2k emite un `ShowMessage` y después un **`ShowMessage_2` por cada línea
    de más** del mismo cuadro. Contándolos aparte, los cuadros de texto
    parecían destrabar tres páginas y no cincuenta y cinco.
  * `CallEvent` aceptado sin hacerlo daba **+97**, que es falso: el evento
    común llamado tiene que compilar él también, y los de este juego se cortan
    casi todos en `FullHeal` y en `ControlVars`. Hecho de verdad destraba cero
    hasta que esos dos existan.

  Puestas todas juntas se llega a 314 de 489, y lo que sigue cortando después
  es una cola larga: `ShowBattleAnimation` 23, `ShowChoice` 13,
  `ChangeScreenTransitions` 10, `JumpToLabel` 8.

  Y una nota que sigue valiendo: de las páginas con `MoveEvent`, la mayoría
  mueve **otro evento** y no al héroe, o sea que piden que los NPCs caminen, que
  es una feature aparte de la ruta forzada que ya anda.
* **Componer el texto del mensaje en caliente.** Es lo que separa al opcode que
  ya existe de que esas 144 páginas compilen: hoy la ROM lleva una sola ventana
  ya compuesta por el conversor, porque una por mensaje son 7,5 KB y no entran.
  Hace falta la fuente en la ROM y armar los 240 tiles desde el 65816, como hace
  FF6 con su `InitDlgVWF` y su buffer de diálogo en la WRAM. Ver "La ventana de
  mensaje".
* **El mapa entero en un cartucho.** Los 328 mapas suman 3,7 MB y LoROM llega a
  4, así que hoy entra un puñado por ROM y se elige al compilar. La salida
  probable es compartir los tiles entre los mapas que usan el mismo chipset:
  son 43 chipsets para 328 mapas.
* **Mapas con más de ocho personajes distintos.** Los sprites van en 4 bits y
  hay ocho paletas para ellos, una por CharSet. Yun Town usa diez y Sorbe
  Village once, así que no convierten. Los dos venían tapados detrás del
  problema de las paletas de la capa de encima, que ya está resuelto. Los
  eventos dibujados con un tile del chipset se empaquetan desde el 2026-09-05
  y los que no entran se dejan de dibujar en vez de cortar el mapa: ver "Los
  eventos dibujados con un tile del chipset".
* **Un evento que camina y cambia de gráfico con la página.** Ver "El
  gráfico sigue a la página": el conversor corta. Y con eso, `change_graphic`
  en una ruta sigue afuera.
* **El panorama.** El mapa 2 tiene uno —`screen`, puntitos sobre azul que
  desplaza en diagonal solo— y es lo que taro vio faltar cuando la pantalla
  grande se enciende. El modo 3 tiene dos capas de fondo y las dos están
  tomadas, el mapa y la capa de encima con la ventana; un panorama pide una
  tercera o el modo 1, que la conversión no usa. No es prioridad.

  De ahí sale que **`ChangePBG` se acepte y se tire** desde el 2026-09-13: si
  no hay panorama, no hay nada que cambiarle. Se tira al compilar, como las
  órdenes de ruta 26 y 27, así que la referencia tampoco lo modela y los dos
  lados quedan iguales por construcción. Aparece **una sola vez en todo el
  juego** —siete comandos en la página del viaje en el Hover-Tram, donde el
  paisaje de la tarde corre por detrás y cambia de velocidad al arrancar y al
  frenar— y sin él esa página no compila: o sea que lo que esto compra es el
  viaje entero, y lo que cuesta es que las ventanillas se vean quietas.
* **El ataque y el decaimiento** siguen saliendo de las ocho familias de
  `sdsp.py`, elegidas a ojo cuando el banco era sintético. El SoundFont trae los
  suyos por instrumento y todavía no se leen. (El release ya no: ver arriba.)
* **Una muestra por instrumento.** Un piano real está multi-muestreado cada
  pocas notas; nosotros tomamos la del do central y transponemos. En los
  extremos del teclado eso se nota.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
