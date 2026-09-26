---
name: "Que armar los cartuchos tarde menos"
description: "Optimizar el tiempo de `just cartuchos` sin refactors: memoizar, paralelizar y numpy, con las ROMs byte por byte iguales"
type: refactor
---

Pedido de taro, el 2026-09-26: optimizar el tiempo de `snes_convert.py` y
de lo que lo llama, **sin refactors** y sin cambiar qué produce; Python,
paralelizar donde se pueda y numpy si aporta. El refactor del archivo es
otra tarea: `las-responsabilidades-de-snes-convert.md`.

Los números medidos, antes y después de cada paso, están en el mensaje de
cada commit, que es donde no envejecen. Lo que no se deduce de ellos:

## Dónde se iba el tiempo

Medido con `cProfile` sobre la conversión de `release` y cronometrando cada
subproceso de `cartuchos.py`:

* `lideres_posibles` corría una vez por cada caso de prueba que toca el
  grupo y cada vez cargaba y compilaba todos los mapas: la mitad del
  conversor en caliente.
* `getpixel` en `sprite_colors` y `pose_tiles`, por millones.
* En frío, o en caliente después de tocar `snes_convert.py` —que entra en
  la clave de las capas guardadas—, las capas de los mapas, en serie.
* Las pistas de MSU-1 normalizadas muestra por muestra en Python.
* Los cartuchos y las pistas, uno detrás del otro.
* Los subprocesos (`gunter`, `voodoo`, `lz2`, `ca65`, `ld65`) pesan poco:
  casi todo es Python puro.

## Lo hecho, un commit por cosa

1. `lideres_posibles`: los cambios de grupo por mapa, una vez por conversión.
2. Los pixeles de los CharSets por `load()`.
3. Las capas de todos los mapas en paralelo (`precalcular_capas`), con
   procesos bifurcados que devuelven lo calculado con la clave del caché.
4. `cartuchos.py` arma los cartuchos y las pistas a la vez, en hilos.
5. `msu.pista` con numpy.
6. `textos.reajustar` y `asignador.merge_least_visible` recordados.

Cada uno verificado igual: `cartuchos.py` en frío (`SIN_CACHE=1`), con el
caché borrado, en la corrida que lo llena y en caliente, y todo
`rom/build/release` y `rom/build/tests` comparado por sha256 contra lo que
armaba 8ffc2ce, salvo el `.o` y los `mtime` del `.dbg`, que cambian con
cada checkout. `just pruebas` en verde al final.

## Lo que queda, y por qué no se hizo

* **El piso de las capas en frío es el mapa más caro** (hoy el 2), que no
  se reparte. Bajarlo es cambiar el modelo de datos de `_convert_layers`
  —`quantize`, `cut_tiles`, `build_palette` trabajan con tuplas de Python
  por pixel— a numpy de punta a punta: un cambio grande, que ésta no era.
* **Paralelizar `convertir` por mapa** no: arrastra estado entre mapas
  (`args.imagenes`, el cartel del primer mapa que lo muestra, los índices
  que llenan las pasadas) y el orden importa. Las capas eran la parte pura.
* **Superponer las etapas del conversor** —la música, la escena, las
  capas— pide saber qué depende de qué en un `main` de mil líneas: es el
  inventario de la tarea de responsabilidades, no algo para hacer a ciegas.
* **Las `gunter sf2 --extract --json` de cada zona** (más de mil llamadas
  por conversión) se podrían guardar en el caché en disco; es poco tiempo
  y otra categoría de caché que mantener.
* **`fork.mapas()` valida el fork entero en cada `lcf.Map`**, a propósito
  según su docstring; recordarlo por proceso ahorraría poco.
* **`lcf.Map` cacheado** no: los mapas se modifican después de cargarlos
  (la página de prueba, el horneado, los translúcidos decorados).
* **Pistas en paralelo adentro de `msu.armar`**: con numpy tardan menos que
  el conversor de `release`, al lado del cual ya corren. Serviría sólo al
  rehacer las pistas solas.
