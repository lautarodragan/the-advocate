# abl-sg — A Blurred Line en Sega Mega Drive

## Paso 1: render de mapas

Lee los datos originales de RPG Maker 2000 y saca un PNG del mapa entero: las
dos capas de tiles más los eventos en su posición inicial, como se verían al
empezar una partida nueva. Sin panorama y sin el héroe.

    just render        # mapa 1, "Introduction" -> render/Map0001.png
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

Los datos salen de dos lados: los `.lmu` están copiados acá en `Maps/`, pero
`RPG_RT.ldb` (qué chipset usa cada mapa) y `RPG_RT.lmt` (nombres y mapa
inicial) se leen del juego original en `/home/taro/git/gaming/abl-rm`. Los
chipsets se buscan primero en `Chipset/` de este repo y después en el juego.

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

## Paso 2: los datos en formato versionable

    just export        # .lmu -> data/, y verifica releyendo

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano.

    data/maps.json       el árbol de mapas y la posición inicial
    data/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/Map0001.tiles   las dos capas de tiles, una fila del mapa por línea
    data/db/*.json       la base de datos, una sección por archivo

Son 16 MB: los 328 mapas con sus 4204 eventos y 46556 comandos, más la base de
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

## Paso 3: el mapa corriendo en una Mega Drive

    just md-image      # una sola vez: arma el contenedor con el toolchain
    just md            # convierte, compila, emula y compara
    just md 7          # otro mapa
    just md-play       # la ROM en una ventana, para moverla con las flechas
                       # (necesita un `xhost +local:` antes)

Sale una ROM donde se camina por el mapa con Talan, con colisión y con los NPCs
del mapa en sus puestos, más los screenshots del emulador y los
`md/shots/comparacion-*.png` con el render de Python al lado.

### Cómo se mueve el personaje

RM2k no mueve a los personajes en píxeles: la posición "real" es **el tile
destino**, que se fija apenas arranca el paso, y un contador de 256 unidades
por tile dice cuánto falta para llegar. El sprite se dibuja interpolado entre
el tile anterior y el destino, y hasta que no llega no se acepta otra
dirección. Por eso en RM2k no se puede parar a mitad de camino entre dos tiles.

Los números salen de EasyRPG (`game_character.cpp`): el contador baja
`1 << (1 + velocidad)` por cuadro, así que a la velocidad 4 —la normal— son 32
por cuadro, o sea ocho cuadros por tile, 2 px por cuadro. La animación avanza
cada 6 cuadros, y son **cuatro fases sobre tres columnas del CharSet: 0, 1, 2,
1** — la del medio se usa dos veces por ciclo. Parado se queda en la del medio,
y contra un borde sigue moviendo las piernas aunque no avance, como en RM2k.

### Los NPCs

Son los eventos del mapa que tienen CharSet, en la página que el motor
mostraría al empezar una partida: la de número más alto sin condiciones, el
mismo criterio que usa el renderer de Python. **No se evalúan sus scripts**, así
que cada uno se queda quieto en la pose que declara su página — dirección y
frame vienen de ahí, no hay que inventarlos. Los eventos sin CharSet (puertas,
cofres, disparadores) quedan afuera por ahora.

Un evento le tapa el paso al héroe si su página está en la capa "same", que es
la del héroe; los de capa "below" —alfombras, marcas en el piso— y los de
"above" no.

El VDP admite 80 sprites encadenados en una lista, y los primeros tapan a los
últimos. **El orden de RM2k es primero por capa y recién después por Y**: un
evento de capa "below" —un punto de guardado en el piso, una alfombra— queda
siempre debajo del héroe aunque esté más adelante en pantalla, y uno de capa
"above" lo tapa siempre. Sale de `Game_Character::GetScreenZ`, donde el z es
`L- YY XX II` con la capa en el byte más alto.

Los NPCs se emiten ya ordenados así, y el héroe —que está en la capa "same"— se
mete donde le toca por su Y dentro de esa banda. Lo que queda fuera de pantalla
se descarta y no gasta entrada.

El límite que aprieta no es el de 80 sino **20 sprites por scanline, o 320
píxeles, lo que llegue primero**: con personajes de 24 px de ancho son 13. El
peor caso del juego es el Auditorium, donde el Director da su discurso: 34 NPCs
en pantalla, pero como máximo 11 comparten scanline, más el héroe. Entra.

Y la VRAM no es problema porque cada NPC estático necesita una sola pose, no
las 12: los 34 del Auditorium usan 6 poses distintas, 72 tiles.

### Colisión

Cada tile de RM2k tiene cuatro bits que dicen por qué lados se lo puede cruzar,
y moverse pide permiso a los dos tiles: el de origen tiene que dejar salir por
ese lado y el destino dejar entrar por el opuesto. La capa alta manda sobre la
baja, salvo que tenga el bit `Above` —que significa "se dibuja por encima del
héroe", o sea decorado— en cuyo caso decide la baja. Hay además un caso
especial: los autotiles de terreno con el bit `Wall` son siempre transitables
en las combinaciones que son la cara de una pared.

Todo eso se resuelve en el conversor y sale como **un byte por tile**; la ROM
sólo mira la tabla. En Lashe City son 5625 bytes y el 73% de los tiles tiene
algún lado cerrado.

La cámara lo sigue centrada, con clamp contra los bordes, y va directo a los
registros de scroll: el horizontal a la tabla de hscroll en VRAM y el vertical
a VSRAM. Se escriben en vblank para que no se parta la imagen.

    md/Containerfile     el cross-compiler de m68k y blastem, aislados
    md/screenshot.sh     corre la ROM sin pantalla y captura el framebuffer
    md/src/boot.S        vectores, cabecera de cartucho y arranque
    md/src/main.c        init del VDP y carga de paletas, tiles y tilemap
    tools/md_convert.py  ChipSet + mapa -> tiles 4bpp, paletas y tilemap
    tools/md_compare.py  screenshot del emulador vs render de Python

**Nada se instala en el sistema.** El cross-compiler y el emulador viven en un
contenedor con la imagen base pinneada por digest. `md/src/mapdata.c` es
generado y no está en git.

### El plano como ventana móvil

El plano del VDP mide **64x64 celdas de 8x8** y se repite cada 512 píxeles, así
que un mapa grande no entra de una: Lashe City son 1200x1200. Lo que se hace es
tenerlo poblado sólo alrededor de la cámara —41 columnas por 31 filas, una más
que lo visible en cada eje por el scroll sub-celda— y redibujar la columna o la
fila que va entrando a medida que la cámara se mueve.

El plano se comporta como un anillo: la celda del mapa `(x, y)` siempre cae en
la posición `(x mod 64, y mod 64)`, y el registro de scroll se encarga del
resto — no hay que corregir nada, `-cam_x` y `cam_y` alcanzan. Redibujar una
columna son 31 escrituras y una fila 41, que entran de sobra en el vblank.

Para escribir una columna de corrido se le pone al VDP el **autoincremento en
una fila entera del plano** (128 bytes) en vez de reposicionarlo celda por
celda. Las tiras se parten en dos cuando cruzan el borde del plano, que es
donde el anillo da la vuelta.

Lo único que sigue acotado es la VRAM de tiles: 1024. No es problema, porque
los mapas de RM2k repiten muchísimo — Lashe City son 363 tiles distintos para
22500 celdas, y el mapa de la persecución, de 8000x640 píxeles, son 173 para
80000 celdas.

### Las tres restricciones del hardware

**El color es de 9 bits**, 3 por canal. Los 74 colores del render de Map0007
quedan en 33.

**Hay 4 paletas de 16 colores y cada tile de 8x8 usa una sola.** Los sprites
también: uno usa una paleta entera para sus 12 celdas. Así que las cuatro se
reparten entre el fondo y los personajes, y **el reparto se decide por mapa**.

Se prueban todos los repartos y gana el que minimiza el peor de los dos
errores. Se comparan *fracciones* de píxeles, no cantidades: el fondo tiene mil
veces más píxeles que un sprite, y sumar píxeles pelados haría que los sprites
nunca pesaran en la decisión. Además, el fondo suele usar menos paletas de las
que se le permiten, y lo que sobra se lo quedan los sprites.

El resultado varía mucho y es justo donde hace falta:

    Lashe City        2 para el fondo, 2 para sprites
    ParadiseFarmland  3 para el fondo, 1 para sprites
    Auditorium        1 para el fondo, 3 para sprites

El Auditorium es el que importa: su fondo usa 11 colores y entra en una sola
paleta sin fusionar nada, y es justamente el mapa con 34 NPCs. Para sus 6
CharSets, pasar de una paleta a tres baja el error del 23% al 11.9%. El índice 0 es
transparente, así que quedan 15 útiles. Esto es lo que aprieta de verdad: no es
la cantidad de colores sino cómo se reparten. Con 32 colores, Map0007 necesita
6 paletas, porque un tile con 14 colores obliga a que esos 14 estén juntos.
Los colores sí pueden repetirse entre paletas, así que el problema es agrupar
de forma que el conjunto de cada tile caiga entero en algún grupo. El conversor
hace best-fit y, si no entra, fusiona el color menos usado con su vecino más
cercano y reintenta. Para Map0007 alcanza con fusionar 9 colores, que entre
todos son 68 píxeles de 76800: **0.089%**. Quedan 3 paletas usadas y una libre.

**Los tiles son de 8x8**, no de 16x16 como los de RM2k, y se pueden reusar
espejados. Map0007 son 1200 celdas de 8x8 que se reducen a **88 tiles
distintos**: 4% de la VRAM de tiles.

### El modo de video, y correrlo en hardware real

Map0007 mide 20x15 celdas de RM2k, o sea 320x240 píxeles exactos. Eso no entra
en los 224 renglones del modo NTSC, pero sí en los 240 del modo V30 de PAL.

**V30 sólo funciona a 50 Hz**: en una consola NTSC el VDP no lo muestra. Así que
la ROM lee el bit 6 del registro de versión (`0xA10001`) al arrancar y elige el
modo según la consola en la que está: en PAL entra el mapa entero, en NTSC se
ven los primeros 224 renglones. `just md` verifica las dos regiones.

Probado en una consola de verdad con un EverDrive, además del emulador. Lo que
hace falta para que ande ahí:

* **TMSS.** Las consolas modelo 1 tardías y el modelo 2 no dejan tocar el VDP
  hasta que el cartucho escribe "SEGA" en `0xA14000`.
* **No escribir los registros 19 a 23 del VDP, los de DMA.** Escribirlos —aun
  con el bit de DMA apagado y sin disparar ninguna— deja la consola en negro,
  aunque en el emulador no cambie nada. El resto de los registros que faltaban
  (el 8, el 9, el 14) y leer el puerto de control antes de empezar son
  inofensivos: se probaron uno por uno en hardware. `VDP_EXTRA` en `main.c`
  deja volver a activarlos si algún día hace falta usar DMA.

  Esto costó cinco tandas de bisección y vale la pena decir por qué: lo agregué
  yo, convencido de que dejar registros sin escribir era lo peligroso, y era al
  revés. Peor: como todas las ROMs de las primeras tandas llevaban ese init,
  "descarté" el tamaño de la ROM, la FIFO del VDP y los sprites cuando en
  realidad fallaban todas por la misma causa oculta. La lección de método es
  incluir siempre un control conocido-bueno en cada tanda; en cuanto lo puse, la
  respuesta salió en una ronda.
* **Callar el PSG.** En un emulador los canales arrancan en silencio; una
  consola de verdad puede zumbar apenas se enciende si nadie les pone la
  atenuación al máximo.
* **Sin bloqueo de región.** La cabecera dice `JUE` y la ROM no chequea la
  consola, así que bootea en cualquiera.
* **Display apagado mientras se carga**, para no mostrar la VRAM sin
  inicializar. De paso el VDP acepta escrituras más rápido.

### Cómo se verifica

El screenshot y el render de Python **no** se comparan por valores RGB: el
emulador y nosotros convertimos los 9 bits del VDP a RGB con tablas de niveles
distintas (blastem usa 49 donde nosotros 52). Lo que se compara es la forma:
dos píxeles tienen el mismo color en el emulador si y sólo si lo tienen en la
referencia. Eso da **idénticos, píxel por píxel** — la ROM dibuja exactamente
lo que el conversor calculó.

El costo real de la conversión se mide aparte, entre la referencia y el render
de Python: error promedio de 13.5/255 (la cuantización a 9 bits) y sólo 21
píxeles de 76800 con error mayor a 32 (los colores fusionados).

El movimiento se verifica mandándole teclas al emulador con xdotool. El
personaje arranca en el tile abierto más cercano al centro y se lo camina en
cada dirección sin soltar, hasta que choca. **Dónde frena se calcula en Python
con las mismas reglas de colisión**, así que si la ROM y la simulación no
coinciden, el personaje queda en otro tile y la comparación falla: esto
verifica la colisión, no sólo el render. Y es determinista por más que el
emulador corra rápido o lento, porque lo que importa es contra qué choca, no
cuánto tardó.

Los NPCs **sí** se verifican: la referencia los dibuja, con sus tiles, su
paleta y su orden, así que la comparación los cubre píxel por píxel.

El héroe también, cuando no se caminó: la referencia lo dibuja en su tile de
arranque con su pose parada, así que el chequeo compara la pantalla entera sin
enmascarar nada — **incluido en qué orden se dibuja respecto de los NPCs**. En
los chequeos con caminata su pose depende de cuántos cuadros corrió el
emulador, así que ahí se tapan los dos lugares donde puede estar.

Esa cobertura no estaba y costó un bug: el punto de guardado del sector 30 se
dibujaba encima del héroe en vez de debajo. Con el héroe enmascarado, ningún
chequeo podía verlo. Ahora el chequeo sin caminata falla con el código viejo:
157 píxeles de diferencia.

Son cinco chequeos por mapa entre las dos regiones. Probado en Lashe City, en
ParadiseFarmland y en Talan's Pad, que es del tamaño exacto de la pantalla y
por lo tanto el caso donde la cámara no se puede mover.

Para recortar el área activa, el conversor pone magenta en el **índice 0 de las
cuatro paletas**, que es el color transparente y que ningún tile usa, y la ROM
lo elige como color de fondo. El framebuffer que guarda blastem incluye el
overscan, y el hueco que dejan las bandas magenta es exactamente la pantalla.
De paso sirve de canario: si aparece magenta adentro de la imagen, algún tile
está usando el índice 0 y hay un bug.

### El RTP

ABL usa recursos que no vienen con el juego: 5 chipsets (`ChipSet1/2/3`,
`Basis`, `Inner`) y 17 charsets (`Chara1-4`, `Crown*`, `Future1-3`, `Men1`,
`Women1`, `People7`, `Vehicle`). Están en el **RTP de Don Miguel** (junio de
2000), que es el que se usaba fuera de Japón: su traducción del RPG Maker 2000
traía su propio RTP traducido, con archivos agregados por él que no existen en
el japonés — `Future1-3`, por ejemplo. El RTP libre de EasyRPG **no sirve**: es
un reemplazo con arte distinto y otros nombres (`Actor1-4` en vez de
`Chara1-4`).

`RTP/` no está en git. Para reponerlo, de `RTPE.EXE` (un SFX de RAR):

    7z x -oRTP-tmp RTPE.EXE && mv RTP-tmp/Data/RTP RTP && rm -rf RTP-tmp

Con eso, los 328 mapas renderizan sin faltantes. `just maps` avisa si falta
algo. Se puede apuntar a otra copia con `--rtp-dir`.

### Referencias

* `/home/taro/git/gaming/easyrpg/liblcf` — el formato LCF
* `/home/taro/git/gaming/easyrpg/Tools/lmu2png` — el render de referencia

## Paso 0 (previo): `poc/`

PoC de "hola mundo" en Mega Drive y SNES con assets placeholder. Ver
`poc/README.md`.
