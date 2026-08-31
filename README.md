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
    tools/event_codes.py  nombres de los opcodes, generado desde liblcf

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
    data/chipsets.json   los chipsets con su passability y su terreno
    data/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/Map0001.tiles   las dos capas de tiles, una fila del mapa por línea

Son 9.6 MB para los 328 mapas, 4204 eventos y 46556 comandos.

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
hecho. Pero los datos están completos y son fieles: `--verify` relee los
`.tiles` y los compara contra los `.lmu`.

**Se omite lo que está en su valor por defecto**, para que el diff muestre sólo
lo que importa. Una página sin condiciones no tiene la clave `conditions`; un
evento quieto no tiene `move`. Y los enums salen como texto: `"trigger":
"auto_start"` en vez de `"trigger": 3`.

Por ahora es de ida nomás: `data/` se genera desde los `.lmu`, no al revés.

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
