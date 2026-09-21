# `juego/`: lo nuestro, que manda sobre `data/`

`data/` es *A Blurred Line* tal como lo escribió su autor: el volcado de Ditto,
que es **derivado** —`just datos` lo rehace entero— y del que nada de acá sale.
Esto es lo contrario: entrada escrita por nosotros que el pipeline usa **en
lugar** de la de `data/`.

Un fork **no describe cambios: es el archivo entero.** Eso es a propósito y lo
que lo separa de `parches/`, que es salida generada por el conversor —las
fusiones de color que decidió el asignador—. Dos direcciones opuestas en un
mismo directorio son lo que alguien regenera sin mirar.

El diff contra el original no se pierde: `data/` sigue versionado y `unpack`
escribe ahí y nunca acá, así que se computa cuando haga falta.

    mapas/Map0011.json     el mapa forkeado
    mapas/Map0011.tiles    y sus dos capas, que viven afuera del JSON
    chipsets/0053.json     un ChipSet que se **suma** a la base, con la receta
                           de su imagen

Lo que lo hace cumplir es `tools/rpgmaker/fork.py`, y lo miran las pruebas
`pruebas/herramientas/test_fork_mapas.py`.

## Las tres reglas, que son el mismo miedo

**Un mapa forkeado es todo o nada.** Las capas de tiles viven afuera del JSON,
así que un `.json` sin su `.tiles` dejaría el build con las capas viejas y los
eventos nuevos: **se ve bien hasta que no**. Falta una pieza, el build se
niega.

**El id de adentro es el del nombre.** Por eso —y sólo por eso— el JSON de un
mapa forkeado lleva un campo `id` que el volcado de Ditto no tiene: el
pipeline elige el mapa por el **nombre del archivo** y los teleports lo nombran
por su **id**, así que un fork copiado de otro mapa y renombrado a medias no
falla, pisa el mapa equivocado y manda al jugador adentro de una pared.

**Un fork de mapa reemplaza a uno que existe.** Un nombre mal escrito no hace
nada, en silencio, y eso es peor que un error.

## Los ChipSets se suman, no reemplazan

Un id que ya esté en `data/db/chipsets.json` es un error. Un fork que pisa una
entrada de la base envejece sin avisar el día que `just datos` la cambie;
agregando una entrada nueva no hay nada que pueda quedar viejo.

**Y su imagen no se versiona: se arma.** El arte del juego no es nuestro para
redistribuir —vive en `/extras`, ver `assets/README.md`—, así que el fork
guarda la **receta**: qué bloque de autotile y qué tile alto se copian adónde.
El PNG sale a `rom/build/juego/ChipSet/`, que es un directorio de build como
cualquier otro.

Duplicar un tile del ChipSet **no cuesta tiles en el cartucho**: Voodoo
deduplica a nivel 8x8 y reusa el espejado, así que un tile repetido son cuatro
celdas que ya estaban.

## Qué hay forkeado hoy, y por qué

El **mapa 11**, el HQ de los Lazer Teeth, con el minijuego de las piedras
rediseñado: sus 52 baldosas de luz dejaron de ser eventos y pasaron a ser tiles
del mapa. El porqué, con todo lo medido, está en
`workflow/tareas/el-mapa-11-no-entra-en-el-cuadro.md`.

Y lo que el rediseño **no** conserva, que es una sola cosa y conviene tenerla
escrita: las baldosas atrapaban al héroe con un trigger de **contacto**, que
dispara en el paso, y ahora lo atrapa un **proceso paralelo**, que mira en qué
celda está. Es un cuadro de diferencia en cuándo salta, no en si salta. No está
medido: se ve jugando, y hasta que `TileSubstitution` y `StoreTerrainID` estén
en el motor no se puede jugar.
