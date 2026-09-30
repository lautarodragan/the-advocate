---
name: "Rust: el dominio de las imágenes"
description: "El escalado y la reducción de colores de las imágenes (palette, picture, title, Game Over, fondos de batalla) y, sobre eso, los dibujos de la pelea (scene, battle_scenes, animation, battle_animations) a Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: Lapacho
---

De taro, el 2026-09-30, en la migración del conversor a Rust. Es lo que
dejaron afuera las pantallas (Tataupá) y la pelea (Cardón), por la misma
razón: el escalado LANCZOS de Pillow, `palette.reduce` y `color.apply_tint`
los comparten las imágenes de los mapas (`picture.py`), el título, el Game
Over, los fondos de batalla que van por MSU-1 (`msu_data.py`), las escenas
de la pelea (`scene.py`, `battle_scenes.py`) y sus animaciones
(`animation.py`, `battle_animations.py`). Se mudan juntos, empezando por el
escalado.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `241dc9ad2bf8b43c…`, `special` `63779e111ee18923…`,
`encounter-every-step` `200a0b7355289700…`; `just pruebas` 882,
`just -f tools/justfile test` 49.

## El piloto: el LANCZOS de Pillow en Rust

**Dio idéntico.** `tools/snes/resample/` es `libImaging/Resample.c` de
Pillow 12.3.0 —el instalado— copiado hasta el orden de las operaciones: los
pesos en `double` con el `sin` de la libc, normalizados, a enteros de 22
bits fraccionarios, dos pasadas (a lo ancho sólo sobre las filas que la
pasada vertical va a leer) y el `clip8` después de cada una; y lo de
`Image.resize` alrededor: el mismo tamaño es una copia, RGBA se
premultiplica (`MULDIV255`) y se divide de vuelta como `Convert.c`, y la
imagen cien veces más alta que ancha va en dos llamados.

Medido el 2026-09-30 contra **todo lo que el conversor escala**: un
`sitecustomize` que envuelve `Image.resize` capturó cada llamado con LANCZOS
de `NO_CACHE=1 just cartuchos` —entrada, tamaño y salida de Pillow—. Son
**377 escalados distintos** (64 RGB: el título, el Game Over, la imagen de
`ShowPicture` y los fondos de pelea, enteros y livianos; 313 RGBA: los
battlers y los cuadros de las animaciones), **2.826.049 píxeles**, y **no
difiere ninguno**. Los scripts, en `<scratchpad>/lapacho/` (`hook/`,
`piloto/`).

## La frontera

**Lo que pasa a Rust son los píxeles**: de la imagen —el archivo, o lo que
dibuja RM2k— a índices y paleta. **Lo que se queda en Python** es qué
imágenes lleva el cartucho y los bytes que las llevan: la emisión.

Tres bibliotecas y una etapa:

* **`tools/snes/resample/`** (`resample`, biblioteca nueva): el LANCZOS
  de Pillow, RGB y RGBA. No sabe de la consola ni de RPG Maker. Va en
  `snes/` porque es la capa que no depende de nada y la pueden usar las
  etapas; no en Adeleine porque escalar no es decidir qué color se pierde,
  aunque cambie píxeles. `rm2k-render` tiene su propio bilineal de Pillow
  (`resample.rs`, el zoom de las celdas) y no puede usar éste: `rm2k/` no
  depende de `snes/`. Quedan dos copias de la misma convolución con dos
  filtros; anotado en "Lo que falta".
* **`adeleine`** suma **`keep_most_used`**, que es `palette.reduce`: se
  quedan los más usados y cada uno de los demás va a su vecino más cercano.
  **Va en Adeleine porque decide qué colores se pierden**, que es la
  definición de AGENTS.md ("si cambia un pixel de lo que se ve"): es la
  misma pregunta que `merge_least_visible` contesta de otra manera. Lo que
  Adeleine no sabe es que el negro es el color de fondo de la PPU: el color
  que va primero lo pasa quien llama.
* **El tinte de la consola** (`color.apply_tint`, el `ToneBlit` de RM2k en
  quince bits) va a la etapa: es de RM2k y de la consola a la vez, y hoy
  lo usan sólo las celdas de las animaciones. `color.py` se queda con las
  constantes que emite `mapdata` —el runtime hace la misma cuenta—.
* **`tools/rm2k-snes/images/`** (`rm2k-snes-images`, la etapa): lee las
  imágenes con `rm2k-render` como biblioteca —el fondo opaco, el battler
  con su tono, las celdas de una animación, la imagen de `ShowPicture`—, y
  hace lo que hoy hacen `palette.convert`, `picture.convert`,
  `scene.backdrop`, `scene.light_backdrop`, `scene.battler` y
  `animation.convert`: escalar, tintar, apilar las celdas
  (`alpha_composite` de Pillow, también a mano), reducir los colores y
  devolver índices y paleta. Un subcomando por pieza —`fullscreen`,
  `picture`, `backdrops`, `battlers`, `animations`—, porque el conversor
  las pide en momentos distintos: la imagen al elegir qué `ShowPicture`
  entra, antes de compilar; el título y el Game Over, las animaciones y la
  escena, después.

**Lo que la etapa recibe**: las rutas de las imágenes —las busca
`resources.find_resource` en el juego y en el RTP, como hoy, y la etapa no
tiene una segunda copia de esa búsqueda—, y **la geometría**: el tamaño de
la escena, cuántos colores y desde qué entrada de CGRAM, la caja de las
animaciones. Son números de la ROM que Python emite al `.inc`; viajan en
el pedido para que sigan escritos una sola vez.

**Lo que se queda en Python**, y por qué:

* **Qué imágenes lleva el cartucho**: `rom_scene`, `patch_uses`,
  `rom_animations`, `events.Pictures.choose`, `game_backdrops`. Dependen de
  los mapas elegidos, los encuentros, las tropas y el bytecode emitido: son
  del orquestador.
* **Los bytes y el `.inc`**: `backdrop_bytes`, `fallback_bytes`,
  `battler_bytes`, `scenes_asm`, `animations_asm`, `fullscreen.compressed`
  (empaquetar y LZ2), `picture.cells`, `animation.cells`, `rom_anchor`. Es
  la emisión, que el encargo deja en Python.
* **Lo que usan las pruebas de ABL para saber qué esperar**:
  `scene.position`, `drawing_order`, `compose`; son geometría de la ROM y no
  tocan píxeles del juego.
* **`msu_data.py`**: el formato del `.msu`, que no toca píxeles.

## Diario

* **La etapa, entera de una vez.** Las cinco piezas salieron iguales en la
  primera corrida: `NO_CACHE=1 just cartuchos`, 1032 archivos de
  `rom/build/` iguales a la base —con `cartridge` en el `bin/` local
  también para la base, por la trampa del `.dbg` que anotó Mara—; `just
  pruebas` 882, `just -f tools/justfile test` 49. Las pruebas del crate
  comparan contra los sha256 del Python viejo (`<scratchpad>/lapacho/
  referencia.py`, que corre el `tools/` de `1a827260` sacado con `git
  archive`) sobre un juego chico que arma `juego_chico.py`; las de
  `keep_most_used`, en Adeleine, contra `palette.reduce` igual.
* **Las animaciones se leen del volcado**, por número, y no del pedido
  como las recibía `rm2k-render battle-animation`: es la forma de una
  etapa. Salió igual, así que el volcado y lo que armaba
  `events.ANIMATIONS` dicen lo mismo.
* **Lo que el conversor imprime** no se comparó contra la base: la base
  corrió antes de guardar los `conversor.log`. Los de la etapa están en
  `<scratchpad>/lapacho/logs-etapa/`.
