# abl-sg — A Blurred Line en Sega Mega Drive

## Paso 1: render de mapas

Lee los datos originales de RPG Maker 2000 y saca un PNG del mapa entero: las
dos capas de tiles más los eventos en su posición inicial, como se verían al
empezar una partida nueva. Sin panorama y sin el héroe.

    just render        # mapa 7, "Talan's Pad" -> render/Map0007.png
    just render 8      # "Lashe City - 34,35"
    just maps          # todos los mapas, su chipset, y qué se puede renderizar

No hay nada que instalar: es Python con Pillow, que ya está en el sistema.

### Piezas

    tools/lcf.py         lector de .lmu/.ldb/.lmt (el formato binario de RM2k)
    tools/chipset.py     expansión del ChipSet a un atlas de tiles resueltos
    tools/charset.py     recorte de sprites de personaje
    tools/render_map.py  el render en sí
    tools/list_maps.py   inventario de mapas

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

### Limitación conocida

El juego usa recursos del RTP oficial de RM2k que no vienen con él ni están en
el RTP libre de EasyRPG: 5 chipsets (`ChipSet1/2/3`, `Basis`, `inner`) y 17
charsets (`Chara1-4`, `Crown*`, `Future1-3`, `Men1`, `Women1`, `People7`,
`Vehicle`). 280 de 328 mapas renderizan — entre los que faltan están el 1 al 6,
la intro y los flashbacks. Los mapas que sí renderizan igual pierden algunos
NPCs. Si conseguís el RTP, va en `--rtp-dir` y se arregla solo.

### Referencias

* `/home/taro/git/gaming/easyrpg/liblcf` — el formato LCF
* `/home/taro/git/gaming/easyrpg/Tools/lmu2png` — el render de referencia

## Paso 0 (previo): `poc/`

PoC de "hola mundo" en Mega Drive y SNES con assets placeholder. Ver
`poc/README.md`.
