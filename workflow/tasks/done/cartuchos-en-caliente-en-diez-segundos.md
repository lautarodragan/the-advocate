---
name: "Cartuchos en caliente en diez segundos"
description: "Segunda vuelta de optimizar `just cartuchos`: el objetivo de taro era menos de 10 s en caliente, sin refactors y con todo rom/build byte por byte igual"
type: refactor
---

Pedido de taro, el 2026-09-26, después de `que-armar-los-cartuchos-tarde-menos.md`:
`just cartuchos` en caliente por debajo de 10 s, y bajar también el camino
en frío. Mismas reglas que la vuelta anterior: sin refactors innecesarios,
sin cambiar qué produce el conversor, y todo `rom/build/release` y
`rom/build/tests` byte por byte igual y determinista.

**No se llegó a 10 s.** Los números de cada paso, antes y después, están en
el mensaje de cada commit, que es donde no envejecen; `just cartuchos` los
imprime.

## Dónde se iba el tiempo, después de la vuelta anterior

En caliente, casi todo es el conversor de `release`, y adentro no había una
etapa que dominara: la música (`build_varios`), el `convertir` de cada mapa, la
escena de batalla, los barridos que cargan todos los mapas del juego para
indexar variables y habilidades, y un reguero de etapas chicas. Detrás del
conversor va el `ca65` de `release`, que no se puede apurar sin cambiar lo
que el conversor emite.

En frío, las capas del mapa 2 eran el piso: las capas van un proceso por
mapa, así que el build no termina antes que el mapa más caro. Con ese piso
bajado, el camino crítico pasó a ser las pistas de MSU-1, una detrás de la
otra.

## Lo hecho, un commit por cosa

1. Los colores y los tiles de las poses de los CharSets con numpy.
2. `merge_least_visible` con numpy.
3. `fork.mapas` recuerda lo validado mientras el directorio no cambie.
4. Las zonas del SoundFont, pedidas a `gunter` en hilos.
5. Los temas de `build_varios`, en paralelo.
6. Los barridos de variables y habilidades, en paralelo.
7. `comun/paralelo.en_paralelo`, uno solo para todo lo anterior, y con él
   los MIDI y los efectos.
8. Las capas se cuantizan y se cortan en celdas con numpy (el piso en frío).
9. Las pistas de MSU-1, a la vez.
10. Los `indexar_*` y los barridos leen un solo LDB.
11. La pantalla de ítems cuenta los colores con numpy.
12. Las muestras de cada tema, decodificando en paralelo.
13. `en_paralelo` corre en serie si el proceso ya tiene hilos: en un worker
    de pytest con un core cargado, bifurcar puede trabar al hijo.

Cada uno verificado igual: `cartuchos.py` en frío (`SIN_CACHE=1`), con el
caché borrado —la corrida que lo llena— y en caliente, comparando el sha256
de todo `rom/build/release` y `rom/build/tests`, salvo el `.o` y los
`mtime` del `.dbg`, contra lo que armaba el `main` de partida; y lo mismo
después de mergear `main`, contra lo que arma ese `main`. `just pruebas` en
verde al final.

## Lo que queda

* **Un sello partido en dos: el del conversor y el del ensamblado.** Es lo
  que llevaría a menos de 10 s el caso más común, que es tocar `rom/src/`.
  Hoy la huella de `cartuchos.py` mete todo `rom/src/` en el mismo sello que
  los `.py` de `tools/`, así que tocar una línea de ensamblador vuelve a
  convertir todo. El conversor lee de `rom/src/` un solo archivo,
  `ram_lejana.s` —lo comprobé con un audit hook sobre la conversión de
  `release`—, así que con un sello para el conversor (flags, casos, `tools/`,
  binarios del conversor, `parches/manual/`, techos y `ram_lejana.s`) y otro
  para el ensamblado (`rom/src/`, `ca65`, `ld65`), tocar ensamblador sería
  sólo `ca65` y `ld65`. Es un cambio de estructura en `cartuchos.py` y no se
  hizo.
* **El conversor en caliente sigue siendo un reguero**: `convertir` (los
  atlas de los ChipSets para decidir qué se hornea, `build_blocks`, las
  poses), lo que queda en serie de la música, las dos `emit`, la escena,
  la compresión, el acomodo de bancos. Ninguna pasa de un par de décimas
  sola; bajarlas todas juntas pide paralelizar `convertir` por mapa o
  superponer etapas del `main`, que es la tarea de responsabilidades
  (`las-responsabilidades-de-snes-convert.md`).
* **El `ca65` de `release` es un piso**: arma el `mapdata.inc` entero, que
  son megas de `.byte` en texto. Bajarlo es emitir los bloques grandes como
  binario (`.incbin`), que cambia lo que produce el conversor.
* **En frío**, con las capas del mapa 2 bajadas, lo que queda de él es sobre
  todo el dibujo con Pillow (`render_layers`, una pegada por tile) y
  `imagen()` en `convert`, que arma los pixeles de cada dibujo en Python;
  esta segunda se podría hacer con las celdas compartidas de
  `tiles_cuantizados`, como `_colores_de`.
