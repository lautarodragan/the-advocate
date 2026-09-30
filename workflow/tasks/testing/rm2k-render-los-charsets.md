---
name: "rm2k-render dibuja los CharSets"
description: "La primera parte de que rm2k-render dibuje todo lo de RPG Maker: las poses de un CharSet y los hechos con un tile, que hoy dibuja el conversor en Python"
type: refactor
assignee: taro
---

De taro, el 2026-09-30: "vamos a por los CharSets en rm2k-render". Es la
primera parte de `todo/rm2k-render-dibuja-todo-rm2k.md`, y va después de
Adeleine en Rust porque los CharSets pasan por Adeleine antes de llegar a
Voodoo.

El criterio de qué va a `rm2k-render` sale de la decisión
(`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): dibujar lo
que dibujaría RPG Maker, sin saber de la SNES. Lo que el port decide por la
consola —la trama o el horneado de los translúcidos, que la SNES no tiene,
los CharSets opacos— no es de `rm2k-render`: se queda del lado del
conversor, o de Adeleine si es decidir colores. La prueba para saber de qué
lado va algo: ¿lo haría igual un visor de RM2k en una PC?

## Lo hecho (Yaguarundí, 2026-09-30)

Dos commits: el cambio (`c455677e`), con las ROMs byte por byte
iguales, y la prosa (`a418f6d3`): README del crate, AGENTS.md,
`tools/README.md`, el justfile y `docs/port/events.md`.

`rm2k-render charset --request <json> --out <dir>`: un pedido es una lista
de hojas de CharSet, y la hoja `i` sale como `<i>.png`, RGBA. Cada entrada
es `{"charset_file": ruta}` o `{"chipset_file": ruta, "tile": n}`, y
cualquiera de las dos puede llevar `"translucent": {"behind": png, "x": x,
"y": y}`. Las rutas son relativas al pedido. Lo cuenta el README del crate,
"What an event is drawn with"; el código es `src/charset.rs`.

### Qué fue a cada lado, y por qué

A `rm2k-render`, porque un visor de RM2k en una PC lo haría igual:

* **Cargar un CharSet con su color clave** —el índice 0 de uno indexado—.
  Ya lo hacía `picture::read_rm2k` para los ChipSets.
* **La hoja de un evento hecho con un tile** (`_from_tile` y
  `upper_tile`): RM2k dibuja el tile `n` de la capa alta donde está el
  evento, mire para donde mire. La hoja con el tile en las doce poses del
  personaje 0, parado en su celda, es la forma de que se recorte como
  cualquier otra; la doble copia por el alfa, que en uno indexado es una
  copia, viene de cuando el tile salía del atlas, y está en la prueba.
* **La mezcla de un translúcido a 160/255 sobre lo que tiene detrás**
  (lo que hacía `_baked`): es el dibujo de RM2k en esa celda. La opacidad y
  la geometría de las poses son de `rm2k-rules` (`event`, `charset`); no se
  duplicaron. Fuera del fondo es negro, que es lo que RM2k muestra fuera
  del mapa.

Se quedó en `render_map.Charsets`, porque es del port:

* **La trama** (`~trama`, `DITHERS`): existe porque la SNES no tiene
  transparencia de sobra.
* **Hornear** —dejar la mezcla metida en el gráfico, opaca— y **contra qué
  fondo**: la capa baja del mapa, porque la alta se dibuja después y tapa.
  `rm2k-render` recibe el fondo como imagen y no sabe de capas.
* **La copia `~aparte`**, que es el mismo dibujo con otra paleta.
* **Los nombres** (`@tile:`, `~horneado:…`): son cómo el port llama a cada
  gráfico. `Charsets` traduce el nombre al pedido.
* **Recortar la pose y todo lo que viene después** —los 32x32 del OBJ, los
  colores, los tiles de 8x8— es de `sprites.py` y Adeleine, como antes.

Los opacos (`[graphics] opaque`) ni pasan por acá: los decide
`rm2k.decorate_translucent` al leer, y ya llegan como un CharSet común.

### Por lote, y cuánto cuesta

`Charsets.draw(nombres)` pide una lista en una sola llamada; `get` de un
nombre que nadie pidió cuesta una llamada propia. Medido con un envoltorio
que anotaba cada llamada, en `NO_CACHE=1 just cartuchos`: **186 llamadas a
`charset`** (y 106 a `layers`), una por CharSet que se pide suelto. Una
llamada de un CharSet cuesta 3,7 ms, contra 2,1 ms por CharSet en lote y
0,3 ms de leerlo con Pillow: en total, menos de un segundo en un build de
46 s, que tardó lo mismo antes y después. Por eso no se pide todo el
cartucho de una vez: armar la lista entera obligaría a adelantar decisiones
de `drawable_npcs`. Probé un lote por mapa en `convert_map` y bajó a 163
llamadas; no lo dejé, porque no se nota. El único lote que quedó es el de
`baking.bakeable_events`, que pregunta por el alfa de varios tiles por mapa.

`baking._tile_alphas` ahora mira el tile en la hoja del evento —la pose 0,
donde está la celda— en lugar de recortarlo del ChipSet: es el mismo
dibujo, y así `upper_tile` se va. Cambió su firma, y con ella
`rom/pruebas/herramientas/test_horneados.py`.

### La comparación

Descartable, en el scratchpad (`yaguarundi/comparar.py`): el `render_map.py`
de `a369a538` copiado aparte contra el `Renderer` nuevo, RGBA byte por
byte, sobre **los 328 mapas del juego** (los de `release` y `test-special`
están adentro). **Ninguna distinta**:

* 1930 hojas de los CharSets que dibujan los eventos, con la copia
  `~aparte` de cada una;
* los 6 translúcidos horneados que hay, y su versión de trama (5
  distintas);
* los 144 tiles de la capa alta de cada uno de los 36 ChipSets, como hoja
  de evento (5184), y su alfa por `_tile_alphas` contra el `upper_tile`
  viejo (5184);
* los CharSets de los 17 actores.

Y las ROMs: `NO_CACHE=1 just cartuchos` antes y después, con el sha256 de
los 1032 archivos de `rom/build/` (menos caché, `.o`, `sello.txt` y el log;
el `.dbg` sin mtime): **todo igual**.

    d098a86fbd7fb9bd41b6ccbea3dba3d0ee2b214e1d7e75a911577b95f6b3be10  release/abl.sfc
    616d8bf8e1e9bebf4293bf39f5ddc4211df26f18fe62e2076470808966b1312b  tests/special/prueba.sfc
    8e85c21b4de4bda9aea90e7061386e7b56a731b245ab039a975eed021f32df6c  tests/encounter-every-step/prueba.sfc

### La prueba del crate

`tests/charsets.rs` guarda los sha256 de lo que dibujaba el Python para un
CharSet indexado y uno RGBA con medias transparencias, tiles de un ChipSet
indexado y de uno RGBA, y translúcidos en celdas del medio y de los bordes
de un fondo: todo generado adentro de la prueba. Los hashes salieron del
Python viejo sobre los mismos archivos (`yaguarundi/hashes_python.py`), y
dieron los doce iguales a los de Rust. `tests/command_line.rs` prueba el
subcomando: las tres clases de entrada, las rutas relativas, y los códigos
de salida. Los generadores de ChipSets que ya usaba `tests/python.rs`
pasaron a `tests/common/`.

### Lo que se borró

De `render_map.py`: `upper_tile`, `Charsets._from_tile`, la mezcla de
`Charsets._baked` y `Renderer.chipset_by_name` —con su caché de imágenes de
ChipSets—, que sólo usaban `_from_tile` y `baking`. Su lugar lo toma
`Renderer.chipset_file`, que da la ruta. **`load_image` se queda**: la usan
`scene.py`, `window.py`, `menus.py`, `animation.py` y `snes_convert.py`.

**Las tandas:** `just pruebas` 882 y `just -f tools/justfile test` 90, en
verde; `cargo test` de `rm2k-render`, en verde y sin avisos de clippy.

**Al mergear:** `just -f tools/justfile install rm2k-render`. Nada de
Python se renombró ni se agregó, así que `install-scripts` no hace falta.

**Para taro:** no hay nada que jugar, porque no cambia un pixel.
