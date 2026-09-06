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
no sabemos evaluar —un ítem, un cronómetro— queda entero afuera: sin saber qué
página está activa, correr la equivocada es peor que no correr ninguna.

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
cortaba junto con `ShowBattleAnimation` (11210), que ahora **se acepta y no se
hace**: la ROM no lleva animaciones de batalla, y lo que se pierde es la
explosión dibujada sobre Core; el destello rojo que viene detrás sí se ve. El
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
chocar, así que sabe cuántas son; el paso del héroe son dieciséis pixeles a
`WALK_SPEED = 2` por cuadro, o sea ocho cuadros por celda. `snes_expect.py`
escribe ese plan y `snes_correr.py` lo lee. El único número puesto a mano es el
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

### Lo que falta

* **Las órdenes de ruta que faltan.** Son quince las que la ROM entiende
  —mover en los cuatro sentidos, girar en los cuatro, esperar, saltar,
  atravesar paredes y parar o seguir la animación— y `play_sound_effect` se
  acepta sin hacerlo, como PlaySound, y la **transparencia** también, desde
  el 2026-09-05: subirla y bajarla de a un octavo son las órdenes 40 y 41, y
  las ocho rutas del juego que las usan son las cuatro pantallas del mapa 2
  atenuándose mientras Manta hackea, que sin eso dejaban afuera la escena
  entera; se pierde el fundido, que sobre tiles de fondo la SNES no hace
  barato. Una ruta que se queda sin órdenes por esto no se emite: RM2k la
  consume entera en el cuadro y no deja nada que esperar. Faltan **cambiar el
  gráfico** —la orden 34— **sobre el héroe**, **fijar la mirada y cambiarle la
  velocidad** —las órdenes 26 a 29, que sobre él se aceptan y se tiran por
  decisión y no por olvido: ver ESTADO.md—, y **moverse hacia el héroe**. La
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
  falte sino dos lados que ya no hacen lo mismo. La velocidad del héroe pide
  además que su paso deje de ser fijo, que hoy son `WALK_SPEED` y ocho cuadros
  por celda.

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
  +10 de techo, que es lo que quedaría dándole la 34 y las diagonales **al
  héroe**. Puestos todos juntos se llega a **281 de 489**, y lo que seguiría
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
* **La animación de batalla sobre el mapa.** `ShowBattleAnimation` se acepta y
  no se hace desde el 2026-09-05: la explosión con la que Core rompe la puerta
  de seguridad no se dibuja, y el destello que la sigue sí. Ver "El destello
  de pantalla".
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
