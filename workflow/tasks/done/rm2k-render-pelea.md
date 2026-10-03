---
name: "rm2k-render dibuja la pelea"
description: "Otra parte de que rm2k-render dibuje todo lo de RPG Maker: las animaciones de pelea (battle_animations.py, animation.py), los enemigos y los fondos de batalla (battle_scenes.py, scene.py)"
type: refactor
assignee: taro
---

De taro, el 2026-09-30: "seguí con todos esos", después de los CharSets
(`testing/rm2k-render-los-charsets.md`, Yaguarundí). Es otra parte de
`todo/rm2k-render-dibuja-todo-rm2k.md`, en paralelo con la otra
(`rm2k-render-pelea.md` y `rm2k-render-pantallas.md`).

Alcance: las animaciones de pelea (battle_animations.py, animation.py), los enemigos y los fondos de batalla (battle_scenes.py, scene.py).

El criterio es el mismo que usó Yaguarundí: va a `rm2k-render` lo que un
visor de RM2k en una PC dibujaría igual; lo que el port decide por la
consola se queda del lado del conversor, o en Adeleine si es decidir
colores.

## Lo hecho (Coatí, 2026-09-30)

Dos subcomandos nuevos, con la forma de `charset`: un pedido JSON que es
una lista, y una salida por entrada.

* `rm2k-render battle-animation --request <json> --out <dir>`: cada
  entrada es `{"sheet_file": ruta, "animation": {...}}`, la animación con
  los nombres del volcado de Ditto (`large` y `frames` con sus `cells`).
  Para la animación `i` escribe `<i>.json` —`{"box": [x, y, ancho, alto],
  "frames": [[{"x", "y", "tone"}, …], …]}`, la caja relativa al ancla o
  `null` si no hay celdas— y cada celda que RM2k dibuja del cuadro `f`
  como `<i>-<f>-<k>.png`, ya recortada, con su zoom y su transparencia.
* `rm2k-render battle --request <json> --out <dir>`: cada entrada es
  `{"backdrop_file": ruta}` o `{"monster_file": ruta, "hue": grados}`, y
  sale `<i>.png`.

El código es `src/battle_animation.rs`, `src/battle.rs` y
`src/resample.rs`; la hoja de las animaciones (cinco celdas por fila, de 96
o de 128) fue a `rm2k-rules`, `battle_animation.rs`.

### Qué fue a cada lado, y por qué

A `rm2k-render`, porque un visor de RM2k en una PC lo haría igual:

* **Cargar la hoja de la animación, el Monster y el Backdrop** con lo que
  RM2k hace con cada uno: la hoja y el Monster con el color clave; **el
  fondo opaco**, porque RM2k no le aplica color clave (el `Cache` de
  easyrpg: `Backdrop` no es `transparent`). El Python lo lograba con el
  `convert("RGB")`; ahora es una regla dicha.
* **Las celdas de cada cuadro**: cuáles se dibujan (`valid`, y las que la
  hoja no tiene no), de dónde se recortan, el zoom —con el bilinear de
  Pillow copiado al bit, premultiplicando el alfa—, la transparencia, y
  **la caja de la animación**, la unión de todas las celdas de todos los
  cuadros, con la posición de cada celda adentro.
* **El tono del battler** (`battler_hue`, el `HueChangeBlit` de easyrpg):
  es lo que hace que un `BLmouse` sea tres enemigos.

Se quedó del lado del conversor, porque es del port:

* **El tono de cada celda, y por eso el apilado.** El Python tiñe con
  `color.apply_tint`, que es el tinte de pantalla **de la consola**: a 15
  bits y con la aritmética que puede hacer el 65816 (el truncado de la
  sobresaturación, por ejemplo). Un visor de PC teñiría a 8 bits. Y como
  RM2k tiñe cada celda **antes** de apilarla, no hay forma de dejarle el
  apilado a `rm2k-render` sin meterle la matemática de la consola: por eso
  sale **cada celda con su tono sin aplicar**, y el conversor tiñe y apila
  (`_paint_frame`, que quedó en diez líneas). Pensé en una tabla de colores
  por tono que el conversor le pasara a `rm2k-render`: la tabla tendría
  que estar indexada por los 15 bits, que es otra vez la consola adentro.
* **Achicar**: la animación a la caja de 64 de OAM (`fit_size`, LANCZOS),
  el fondo y los battlers al 80% de la pantalla de la SNES, y el respaldo
  liviano a 128x64.
* **Los colores**: la paleta de 15 de la animación (`palette.reduce`), los
  96 del fondo, los 16 del respaldo y los 15 de cada battler (Adeleine),
  el corte del alfa a la mitad.
* **El ancla de la ROM** (`rom_anchor`, con el corrimiento de
  `Animation::Position` horneado), los tiles, los bytes, las tablas.
* **Qué fondos y qué battlers lleva el cartucho** (`battle_scenes.py`), y
  dónde se para cada enemigo y quién tapa a quién (`position`,
  `drawing_order`): son para las tablas de la ROM, que compone sola. Nadie
  compone una tropa como la dibujaría RM2k —`compose` es de las pruebas, en
  índices de la consola—, así que `rm2k-render` no la compone: sería un
  camino que nadie ejecuta.

### Cuánto cuesta

Medido con un envoltorio que anotaba cada llamada, en `NO_CACHE=1 just
cartuchos`: **14 llamadas a `battle-animation`** (150 ms en total; una por
mapa que muestra animaciones nuevas, y una por lote en `rom_animations`) y
**204 a `battle`** (715 ms; una por fondo o battler, la mayoría en
paralelo). El build tardó 47 s, como antes (46 s). `by_numbers` pide por
lote; `battle` no, porque no se nota.

### La comparación

Descartable, en el scratchpad (`coati/comparar.py`): `animation.py` y
`scene.py` de `d4120186` copiados aparte contra los nuevos, byte por byte.
**Ninguna distinta**:

* **las 180 animaciones del LDB** (161 con hoja, 19 sin): los 3623
  cuadros en pixeles de RM2k (`_paint_frame`, RGBA) y la caja de cada una,
  y el `convert` entero —índices, paleta, ancla, tamaños— de las 180;
* **585 battlers**: cada Monster del juego con cada tono que le da un
  enemigo, y además con 0, 17, -45, 181, 359, 360 y 720; el RGBA y el
  `battler` entero;
* **los 70 fondos** del juego y del RTP: el RGB, `backdrop` y
  `light_backdrop` enteros.

Todo lo que entra en `release` y `test-special` está adentro.

Y las ROMs: `NO_CACHE=1 just cartuchos` antes y después, con el sha256 de
los 1032 archivos de `rom/build/` (menos caché, `.o`, `sello.txt` y el log;
el `.dbg` sin mtime): **todo igual**.

    905decd20b48411fb509d60ca7a61b3ddbfe1fd5fcf618519972ddba86b83cee  release/abl.msu
    d098a86fbd7fb9bd41b6ccbea3dba3d0ee2b214e1d7e75a911577b95f6b3be10  release/abl.sfc
    616d8bf8e1e9bebf4293bf39f5ddc4211df26f18fe62e2076470808966b1312b  tests/special/prueba.sfc

### La prueba del crate

`tests/battle.rs` guarda los sha256 de lo que dibujaba el Python sobre las
dos imágenes de `tests/common/` (una indexada y una RGBA con medias
transparencias): las celdas de dos animaciones —zoom para arriba, para
abajo y a un pixel, transparencias de 37, 100, -5 y 150, una inválida, una
que la hoja no tiene, una grande— con su posición y la caja; los battlers
con seis tonos; y el RGB de los fondos, además de que salen opacos. Los
hashes salieron del Python viejo (`coati/hashes_python.py`), que corre los
mismos pasos por celda del `_paint_frame` viejo, y dieron todos iguales.
Las pruebas del ejecutable —pedidos, rutas relativas, códigos de salida—
están en el mismo archivo, para no tocar `command_line.rs`, que tiene
Hurra.

### Lo que se borró

De `animation.py`: `sheet_of` (ahora `sheet_file`, que da la ruta),
`_live_cells`, `_side`, `rm_box`, `CELL`, `BIG_CELL`, `COLUMNS` y, de
`_paint_frame`, el recorte, el zoom y la transparencia. De `scene.py`:
`rotate_hue`, `_to_hsl`, `_from_hsl` y `_div`, y leer con `load_image`.
`load_image` se quedaba porque la usaban `snes_convert.py`, `window.py` y
`menus.py`; después del merge con Hurra ya no, y se borró: ver abajo.

**Los commits:** el cambio (`d8a56790`), con las ROMs byte por byte
iguales, y la prosa (`a13b4b6a`): README del crate, AGENTS.md,
`tools/README.md` y los docstrings de `animation.py` y `scene.py`. No toqué
`render_map.py`, `command_line.rs`, el `about` de `main.rs` ni la
descripción del `Cargo.toml`, que son de los dos lados: el mensaje de
`MISSING` en `render_map.py` sigue diciendo "las capas y los CharSets".

**Las tandas:** `just pruebas` 882 y `just -f tools/justfile test` 90, en
verde; `cargo test` de `rm2k-render` y de `rm2k-rules`, en verde, y
`rm2k-render` sin avisos de clippy (el de `rules/src/tree.rs` ya estaba).

**Al mergear:** `just -f tools/justfile install rm2k-render` (lleva
`rules` adentro). Nada de Python se renombró ni se agregó, así que
`install-scripts` no hace falta.

**Después del merge con Hurra** (`d23f52f4`, los dos lados en cada
choque): `battle` y `battle-animation` leen el pedido con su `request.rs`,
`scene._open` llama a `render_map.draw`, y **`load_image` se borró**, porque
ya no la usa nadie (`c523d9ff`). Sobre el árbol mergeado, otra vez: la
comparación sin diferencias, los 1032 sha256 iguales a los de antes de
todo, `just pruebas` 882 y `just -f tools/justfile test` 90 en verde.

**Para taro:** no hay nada que jugar, porque no cambia un pixel.
