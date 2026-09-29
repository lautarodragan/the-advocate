---
name: "Rust: el render de mapas"
description: "tools/render en Rust: rm2k-render dibuja las capas de un mapa desde el volcado y el ChipSet, y el conversor lo llama por el PATH en lugar de importar Renderer, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

Segundo paso del camino a Rust de `docs/research/las-herramientas-hoy.md`,
en paralelo con Carancho (`rust-el-armado-de-cartuchos.md`). Lo decidió
Hornero: el conversor usa el render para dos cosas, `Renderer` (las capas de
cada mapa, que se cachean) y `load_image` (cargar una imagen con su color
clave, desde varios módulos). Pasa a Rust lo primero, como un ejecutable
que el conversor llama por el PATH; `load_image` se queda en Python mientras
el conversor lo sea.

## Lo hecho (Hurón)

**`tools/rm2k-render/`**, biblioteca y ejecutable. El directorio se llama
como el binario: `render/` sigue siendo el Python que se queda (CharSets,
`load_image`, la receta de los ChipSets del fork), y con el nombre del
binario la receta `which` de `tools/justfile` lo encuentra como a los demás.

    rm2k-render layers --map N [--project DIR] --game-dir G --rtp-dir R --out DIR
    rm2k-render layers --request map.json --chipset-file X.png --out DIR
    rm2k-render atlas (--chipset NOMBRE | --chipset-file X.png) -o atlas.png

Escribe `lower.png`, `upper.png` y, por familia que el mapa usa,
`water-1.png`, `water-2.png`, `animated-1.png` a `animated-3.png`; borra
los de una familia que no usa. El README del crate lo dice entero.

### Las decisiones

* **`png` solo, no `image`.** Los ChipSets son PNG indexados y el índice 0
  es el color clave diga lo que diga el archivo: hace falta leer los
  índices crudos, que es lo que `image` esconde. Ninguno del juego ni del
  RTP es BMP, así que un BMP se rechaza con un mensaje en vez de cargar un
  decodificador sin nada contra qué verificarlo. Se leen también gris, RGB
  y RGBA a 8 bits con su tRNS, como Pillow.
* **Lo que escribe: PNG RGBA**, con compresión rápida. Se pueden abrir para
  mirar, Pillow los lee sin más, y son sin pérdida. Un volcado crudo se
  ahorraría la compresión, pero no hizo falta: ver los tiempos abajo.
* **Cómo le llega el mapa: un `--request`** en JSON con los nombres de campo
  del volcado de Ditto (`width`, `height`, `lower_layer`, `upper_layer`,
  `chipset` con `chipset_name` y las dos pasabilidades). No `--map N`
  porque el mapa que dibuja el conversor no es el del volcado: lleva el fork
  de `rom/parches/manual/` y los eventos horneados en la capa alta, y la
  lógica del fork se queda en Python. `--map N` existe igual —lee el volcado
  tal cual, con `--project`— y la prueba del crate verifica que da lo mismo
  que el pedido equivalente.
* **El ChipSet por `--chipset-file`**, resuelto en Python con
  `find_resource`: es el mismo archivo que `chipset_fingerprint` hashea para
  la clave del caché, así que no pueden divergir. `--game-dir`/`--rtp-dir`
  quedan para la búsqueda por nombre, con las mismas reglas (sin distinguir
  mayúsculas, `.png`/`.bmp`, en orden).
* **Sin atlas en Python.** Lo que lo usaba sin ser una capa —el alfa de un
  tile para hornear (`_tile_alphas`) y el CharSet inventado de un evento
  dibujado con un tile (`Charsets._from_tile`)— mira sólo tiles de la capa
  alta, que son copias sin combinar del ChipSet: lo hace
  `render_map.upper_tile`, diez líneas, copiando dos veces por el alfa como
  llegaba pasando por el atlas.
* **La mezcla por alfa como la de Pillow**, con su redondeo: con los
  ChipSets indexados es una copia, pero con medias transparencias no, y la
  prueba del crate cubre ese caso con un ChipSet RGBA.
* **La clave del caché de capas** lleva `render_map.version()` —el hash del
  binario— en lugar de `render/chipset.py`. `render/render_map.py` se queda
  en la clave, porque es el que arma el pedido; Pillow también, porque
  sigue leyendo los PNG y es sobre lo que trabaja la conversión.

### La comparación completa

Descartable, en el scratchpad (`rust-huron/comparar.py`): el Python de
`f19b27ec` copiado aparte contra el `Renderer` nuevo, en los 93 mapas de
`release` y `test-special`, RGBA byte por byte. Cubre:

* las capas y los dibujos de la animación de cada mapa, con el fork: 142
  imágenes;
* lo mismo con los eventos horneados metidos en la capa alta: los 4 mapas
  que hornean;
* los 352 CharSets que dibujan sus eventos, incluidos los translúcidos
  horneados contra la capa baja y los hechos con un tile del ChipSet;
* los 144 tiles altos de cada uno de los 24 ChipSets, y el atlas entero de
  cada uno, que cubre también las combinaciones que ningún mapa usa.

**Ninguna distinta.** Dibujar las capas sin hornear de los 93 mapas: 5,3 s
el Python, 3,7 s `rm2k-render` contando el subproceso, escribir y leer los
PNG (en serie, fuera del conversor).

### La prueba del crate

`just -f tools/justfile render-test`: `tests/python.rs` guarda los sha256 de
lo que dibujaba el Python para un ChipSet indexado y uno RGBA con medias
transparencias, y un mapa de 48x32 que toca todas las aguas, terrenos,
animados, los ids de combinación 47 a 49, tiles pasados del final de la
página y tiles de los dos lados del héroe; todo generado adentro de la
prueba, sin juego ni RTP. `tests/command_line.rs` prueba el ejecutable: las
dos entradas, los archivos de familias que se borran, y los códigos de
salida.

### Lo que se borró y lo que quedó

Se borró `render/chipset.py` entero (el atlas) y, de `render_map.py`,
`draw_tiles`, `render_layers`, `atlas`/`atlas_by_name` y el dibujo de
`animated_layers`. Quedan en `render_map.py`: `load_image`,
`build_passability` (la usan el conversor y las pruebas), `DITHERS`,
`Charsets`, `upper_tile` y `Renderer` como contexto (base de datos, árbol,
`load_map`, CharSets, huellas de ChipSet, `layer_inputs`). Queda entero
`render/chipset_recipe.py`: arma las imágenes de los ChipSets del fork, que
es del conversor y no del formato.

### Para el que mergee

* **Desde el checkout principal: `just -f tools/justfile install
  rm2k-render`.** Sin él en el PATH el conversor se corta con el mensaje.
  No cambió ningún script, así que `install-scripts` no hace falta.
* **`rm2k-render` tiene que entrar en la huella de los cartuchos**:
  `cartridges.fingerprint_files` lista `tiles_bin.binary()` y los otros
  binarios; falta `render_map.binary()`. Sin eso, recompilarlo no deja
  viejos los cartuchos. No lo toqué: `tools/assembly/` es de Carancho.
* `tools/justfile`: `rm2k-render` al final de `rust_projects` y la receta
  `render-test`, al lado de `lz2-test`.

### Verificado

* `NO_CACHE=1 just cartuchos` en `f19b27ec`, después del cambio y después
  del borrado: los 987 archivos de `rom/build` (sin `.o`, `.sym`, `.inc`,
  `.dbg`) byte por byte iguales las tres veces. `abl.sfc`
  `7a3c64834f783ae0fad34eb9f814801916be00aa962d0ca78c1a215ce6a66552`,
  `prueba.sfc` (`test-special`)
  `fb6db844580e74097af5d500be85dbab3f88e888e27743b457167a97ad9e0617`.
* `just pruebas`: 874 pasan. `just -f tools/justfile test`: 132 pasan, 2 se
  saltean (las del SoundFont). `render-test`: 6 pasan.
* Lo que **no** se corrió: la tanda de ABL después del último commit, que
  sólo cambia comentarios; y `cargo test` de los otros proyectos de Rust,
  que no se tocaron.

Commits: `7b49ad2a` (el crate), `c7d2fe84` (el conversor lo usa),
`2ffc6152` (el borrado, mecánico), `a0968a38` (las citas en prosa).
