# El juego en JSON

Esto es *A Blurred Line* volcado de los formatos binarios de RPG Maker 2000 a
JSON y a texto plano. Lo genera `just export`, que corre `tools/export_json.py`,
y **se puede regenerar entero en cualquier momento**: es derivado, no fuente. Si
algo de acá no coincide con los `.lmu`, el que está mal es esto.

    maps/Map0001.json    metadata, chipset, y los eventos con sus scripts
    maps/Map0001.tiles   las dos capas de tiles, una fila por línea
    maps.json            el árbol de mapas y dónde arranca la partida
    db/                  RPG_RT.ldb abierto: actores, chipsets, items, switches…

## Por qué está en el repo si es derivado

Porque es la única forma de **leer el juego**. Un `.lmu` es un formato binario
con chunks de largo variable: no se puede mirar, no se puede buscar con grep, y
un `git diff` de dos versiones no dice nada. En JSON sí. Cuando hubo que
averiguar qué comandos tiene la cinemática de apertura, o qué actores mete un
`ChangePartyMembers`, la respuesta salió de acá.

Los tiles van aparte y en texto, una fila por línea, porque son lo único
voluminoso: meterlos en el JSON haría los diffs ilegibles justo donde más
importa mirarlos.

## De dónde salen los structs

De **liblcf y easyrpg-player**, que están clonados en `/extras/ref`. Ningún
número de este directorio se escribió de memoria: los ids de chunk salen de
`src/generated/lcf/rpg/*.h` y la semántica, de cómo los usa el intérprete de
easyrpg-player. Ya pasó una vez que tres códigos de comando se pusieron de
memoria y estaban mal, y de ahí salió la regla.

`tools/gen_schema.py` genera `tools/lcf_schema.py` desde liblcf; `tools/lcf.py`
es el lector.

## Esto no es de A Blurred Line

El lector y el exportador no saben nada de este juego en particular: leen
RPG Maker 2000. Sirven para cualquier juego de RM2k con cambiarle el
`--game-dir`, y ésa es la razón de que estén separados del port —viven en
`tools/`, no en `rom/`—.

La idea es que en algún momento esto se mude a Rust, como proyecto aparte y
reusable. Mientras tanto vive acá, que es donde se usa.
