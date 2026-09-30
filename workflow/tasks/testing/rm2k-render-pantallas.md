---
name: "rm2k-render dibuja las pantallas"
description: "Otra parte de que rm2k-render dibuje todo lo de RPG Maker: las FaceSets (menus.py), el System de las ventanas (window.py) y el cartel de ShowPicture (picture.py)"
type: refactor
assignee: taro
---

De taro, el 2026-09-30: "seguí con todos esos", después de los CharSets
(`testing/rm2k-render-los-charsets.md`, Yaguarundí). Es otra parte de
`todo/rm2k-render-dibuja-todo-rm2k.md`, en paralelo con la otra
(`rm2k-render-pelea.md` y `rm2k-render-pantallas.md`).

Alcance: las FaceSets (menus.py), el System de las ventanas (window.py) y el cartel de ShowPicture (picture.py).

El criterio es el mismo que usó Yaguarundí: va a `rm2k-render` lo que un
visor de RM2k en una PC dibujaría igual; lo que el port decide por la
consola se queda del lado del conversor, o en Adeleine si es decidir
colores.

## Lo hecho (Hurra, 2026-09-30)

Dos commits, como el precedente: el cambio (`0b65a702`), con las ROMs byte por byte
iguales, y la prosa (`b8c180f2`: README del crate, `tools/README.md`, AGENTS.md,
`docs/port/events.md`).

Tres subcomandos nuevos con la forma de `charset`: `--request <json>
--out <dir>`, el pedido es una lista, la entrada `i` sale como `<i>.png`
RGBA, las rutas son relativas al pedido y un archivo que comparten varias
entradas se lee una vez. Se revisan y dibujan todas antes de escribir la
primera: un pedido con una entrada mala no deja nada a medias. Lo cuenta el
README del crate, "What the screens are drawn with".

* `face`: `{"faceset_file", "index"}`, la cara 48x48 con su color clave
  (`src/face.rs`).
* `system`: `{"system_file", "draw"}` con `draw` = `window` (`width`,
  `height`, `message_stretch` tal como lo trae la base), `cursor`
  (`width`, `height`, `drawing` 0 ó 1), `text_color` (`color`), `shadow` y
  `timer` (`src/system.rs`).
* `picture`: `{"picture_file", "use_transparent_color", "top_trans"}`,
  nombrados como el `Picture` guardado de liblcf (`src/show_picture.rs`:
  `picture.rs` ya era el de leer PNG).

Lo común de los tres pedidos está en `src/request.rs`. En `main.rs`,
`lib.rs` y `picture.rs` lo mínimo: los subcomandos, los `mod`, y en
`picture.rs` un `crop` y un `read_unkeyed` —el índice 0 opaco, que es cómo
se dibuja un cartel sin su color transparente—.

A `rm2k-rules`, en archivos nuevos: `faceset.rs` (48x48, cuatro por fila),
`system.rs` (dónde está cada pieza del System, los veinte colores, el
cronómetro, y `message_stretch` → estirado o mosaico; el tercer valor es de
EasyRPG y se niega) y `picture.rs` (la opacidad de `top_trans`).

Del lado de Python, `render_map.draw(command, entries)` es la llamada que
usan los tres. `window.skin(game_dir, database)` —antes recibía el nombre—
devuelve un `Skin` con la ruta del System y su `message_stretch`, que pide
lo que haga falta y lo recuerda: ventanas y cursores por tamaño, y los
veinte colores, la sombra y el cronómetro juntos en una llamada. Las
funciones `window`, `cursor`, `text_color` y `shadow_color` de `window.py`
siguen, así que los que dibujan menús no cambiaron. `lcf.Database` lee
`message_stretch`.

### Qué fue a cada lado, y por qué

A `rm2k-render`, porque un visor de RM2k en una PC lo haría igual:

* **Recortar la cara** de su FaceSet, con el color clave.
* **La ventana vacía**: el fondo estirado o en mosaico según
  `message_stretch`, el marco encima; **el cursor**; **los bloques** de los
  colores del texto y de la sombra; **los glifos del cronómetro**. El
  cronómetro no estaba en el encargo, pero `obj_extras` leía el System
  pixel por pixel para sacarlos, y dejarlo así obligaba a seguir leyendo la
  hoja entera en Python con `load_image`.
* **El cartel tal como RM2k lo pone en pantalla**: el archivo, con el
  índice 0 transparente sólo si el comando lo pide, y a la opacidad de su
  transparencia.

Se quedó del lado del conversor, porque es del port:

* **Dónde va cada ventana** en una pantalla de 256 de ancho, el mensaje de
  256x80, el texto cortado a lo que entra, y las ventanas armadas por capa
  (`menus.py`, `screens.py`, `end_game.py`, `title.py`).
* **Escribir el texto** con los bloques (`window.draw_line`): la regla de
  `Font::Render` es de RM2k, pero la fuente es la de 8 pixeles del port
  (`font.py`), y un visor de PC usaría otra.
* **De la cara en adelante**: sus quince colores (`_face_palette`, con
  Adeleine), las paletas prestadas, las celdas.
* **Todo `picture.py`** salvo leer el archivo: escalar de 320x240 a
  256x224, reducir a quince colores, cortar en objetos de 32x32, el tono
  aplicado a la paleta. El centrado —`ShowPicture` da el centro, no la
  esquina— es de RM2k, pero está pegado a la cuenta del escalado (`box`
  escala las dos esquinas); moverlo solo no le sirve a nadie.
* **Qué `ShowPicture` entra** (`picture_fits`, `Pictures.choose`): el
  conversor sigue rechazando los que piden color transparente o
  transparencia. Ahora se los pasa a `rm2k-render` igual, con sus
  parámetros, así que el día que el port los acepte el dibujo ya está.

### Lo que la comparación con easyrpg encontró, y no se tocó

El Python decía seguir a easyrpg al pie de la letra, y en dos cosas no:

* **Los bordes del marco y del cursor se repiten desde donde empiezan**, al
  lado de la esquina. easyrpg los `TiledBlit`ea desde la esquina de la
  ventana, así que su dibujo está corrido 8 pixeles, medio borde. Medido:
  en los tres System del juego (`ablskin`, `BLSys`, `BLHigh`) todos los
  bordes se repiten cada 8 pixeles, así que **en ABL no cambia un pixel**.
* **El estirado elige el pixel como Pillow** (`NEAREST`, sumando la escala
  columna por columna en un double), no como pixman. No lo medí contra
  easyrpg.

Se portaron tal cual, porque arreglarlos es un cambio de criterio y no va
en el mismo commit que una mudanza verificada. Están dichos en el
encabezado de `src/system.rs` y en el README del crate. Si taro quiere el
de easyrpg, es cambiar el origen de `tiled` en `frame` y regenerar los
hashes de las pruebas que usan un System que no se repite cada 8.

### La comparación

Descartable, en el scratchpad (`hurra/comparar.py`): el Python de
`d4120186` contra `rm2k-render`, RGBA byte por byte, sobre **todas las
FaceSets, System y Pictures del juego y del RTP**, que es más que lo que
entra en `release` y `test-special`. **Ninguna distinta**:

* las 16 caras de las 13 FaceSets (208), y `face_of` de los 17 actores con
  cara; los 8 cuya FaceSet no está en el juego (`chara1`, del RTP) hacen
  que el viejo y el nuevo se nieguen los dos;
* de los 5 System, la ventana estirada y el cursor en 3959 tamaños cada
  uno —todos los anchos de 16 a 320 con ocho altos, y todos los altos de 16
  a 240 con siete anchos— (19.795 de cada uno), y el cursor en los 80
  tamaños chicos que el viejo sabía dibujar;
* la ventana en mosaico en los mismos tamaños, contra el `_tiled` viejo con
  el marco encima (19.795): el Python no la dibujaba nunca, pero sus piezas
  sí;
* los 20 colores, la sombra y el cronómetro de cada System;
* la ventana y una página de texto por el camino del conversor (`Skin`);
* las 112 Pictures: el RGB contra el `Image.open(...).convert("RGB")` de
  antes —todas opacas—, con el color clave contra `load_image`, y 111 por
  `Pictures._read`.

Y las ROMs: `NO_CACHE=1 just cartuchos` antes y después, con el sha256 de
los 1032 archivos de `rom/build/` (menos caché, `.o`, `sello.txt` y el log;
el `.dbg` sin mtime): **todo igual**.

    d098a86fbd7fb9bd41b6ccbea3dba3d0ee2b214e1d7e75a911577b95f6b3be10  release/abl.sfc
    616d8bf8e1e9bebf4293bf39f5ddc4211df26f18fe62e2076470808966b1312b  tests/special/prueba.sfc
    8e85c21b4de4bda9aea90e7061386e7b56a731b245ab039a975eed021f32df6c  tests/encounter-every-step/prueba.sfc

**Cuánto cuesta**: medido con un envoltorio que anotaba cada llamada, un
`NO_CACHE=1 just cartuchos` hace 19 llamadas a `face`, 57 a `system` y 1 a
`picture` (y las 185 a `charset` y 104 a `layers` de antes). A unos 4 ms
cada una, menos de medio segundo en un build de 46 a 52 s, que es lo que
varía de una corrida a otra.

### Las pruebas del crate

`tests/screens.rs` guarda los sha256 de lo que dibujaba el Python para un
System indexado con bordes que **no** se repiten cada 8 y uno RGBA con
medias transparencias —ventanas en seis tamaños, cursores en cuatro, tres
colores, la sombra y el cronómetro—, una FaceSet y otra más chica que las
caras que se le piden, y un cartel: todo generado adentro de la prueba. Los
hashes salieron del Python viejo sobre las mismas fórmulas
(`hurra/hashes_python.py`), y dieron los 37 iguales a los de Rust. Lo que
el Python nunca dibujó —el mosaico, el segundo cursor, la transparencia de
un cartel— se prueba contra la regla. `tests/screens_command_line.rs`
prueba los tres subcomandos: rutas relativas, cada clase de entrada, y los
códigos de salida. `rules/tests/screens.rs`, las posiciones y la opacidad.

### Lo que se borró

De `window.py`: `_tiled`, `_paste`, el armado de `window` y de `cursor`,
los recortes de `text_color` y `shadow_color` y `SHADOW_ORIGIN`. De
`menus.face_of`, el recorte. De `events.Pictures._read`, el `Image.open`.
De `obj_extras`, `TIMER_ORIGIN` y la lectura del System. El import sin uso
de `load_image` en `snes_convert.py`.

**`load_image` se queda**: la usan `scene.py` y `animation.py`, que son de
la pelea (Coatí, `rm2k-render-pelea.md`). Si esa tarea las pasa a
`rm2k-render`, se puede borrar.

**Muerto y no mío**: `picture.render` y `picture.report` no los llama nadie.
No los toqué.

**Las tandas:** `just pruebas` 882 y `just -f tools/justfile test` 90, en verde;
`cargo test` de `rm2k-render` y
`rm2k-rules`, en verde y sin avisos de clippy en lo nuevo.

**Al mergear:** `just -f tools/justfile install rm2k-render`. Nada de
Python se renombró ni se agregó, así que `install-scripts` no hace falta.

**Para taro:** no hay nada que jugar, porque no cambia un pixel.
