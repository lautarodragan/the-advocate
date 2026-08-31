# abl-sg — A Blurred Line en Sega Mega Drive

## Paso 1: render de mapas

Lee los datos originales de RPG Maker 2000 y saca un PNG del mapa entero.
Sólo las dos capas de tiles: sin eventos, sin sprites, sin panorama.

    just render        # mapa 7, "Talan's Pad" -> render/Map0007.png
    just render 8      # "Lashe City - 34,35"
    just maps          # todos los mapas, su chipset, y si se puede renderizar

No hay nada que instalar: es Python con Pillow, que ya está en el sistema.

### Piezas

    tools/lcf.py         lector de .lmu/.ldb/.lmt (el formato binario de RM2k)
    tools/chipset.py     expansión del ChipSet a un atlas de tiles resueltos
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
por encima del jugador).

### Limitación conocida

Los mapas 1 a 6 (intro y flashbacks) y otros 42 usan chipsets del RTP oficial
de RM2k (`ChipSet1/2/3`, `Basis`, `inner`), que no vienen con el juego ni están
en el RTP libre de EasyRPG. 280 de 328 mapas renderizan; el resto necesita esos
archivos. Si aparecen, van en `--rtp-dir`.

### Referencias

* `/home/taro/git/gaming/easyrpg/liblcf` — el formato LCF
* `/home/taro/git/gaming/easyrpg/Tools/lmu2png` — el render de referencia

## Paso 0 (previo): `poc/`

PoC de "hola mundo" en Mega Drive y SNES con assets placeholder. Ver
`poc/README.md`.
