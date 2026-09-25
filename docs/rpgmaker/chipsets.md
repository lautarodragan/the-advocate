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
