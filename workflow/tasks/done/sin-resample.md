---
name: "Sin resample: el escalado con una biblioteca de Rust"
description: "resample (el LANCZOS de Pillow bit por bit) y el bilineal de rm2k-render imitaban a Pillow para que la migración no moviera la ROM; con el Python ido, los dos pasan a una biblioteca estándar de Rust, aunque eso mueva píxeles"
type: refactor
assignee: taro
---

De taro, el 2026-10-02: "me gustaría eliminar resample. No hay necesidad de
mantener compatibilidad con Python. Estuvo bien para la migración, pero
prefiero simplificar el pipeline y que los binarios que necesiten aplicar
transformaciones de imágenes usen alguna librería estándar o popular de
Rust".

Lo usan `rm2k-snes-images` (`pixels.rs`: título, Game Over, imágenes
grandes, fondos y battlers, animaciones, `ShowPicture` con zoom) y, con su
propio escalador bilineal, `rm2k-render` (`src/resample.rs`,
`battle_animation.rs`). Cambiar el escalador mueve goldens de ABL, que desde
hoy viven en su propio repo.

## La biblioteca: `image`, sólo `imageops`

Medido el 2026-10-02 con tres binarios de juguete idénticos salvo el
escalador —leen un PNG con `png 0.17`, escalan y escriben—, compilados con
el perfil `release` del workspace (`lto`, una unidad, `strip`):

| escalador | binario | crates |
|---|---|---|
| `resample` (el de hoy) | 524.056 B | 13 |
| `image 0.25`, `default-features = false` | 529.392 B (+5 KB) | 18 |
| `fast_image_resize 6`, sólo `std` | 3.528.416 B (+3 MB) | 24 |

`fast_image_resize` trae una variante SIMD por cada tipo de pixel y cada
extensión de la CPU, y el `lto` no las saca porque se eligen en tiempo de
ejecución: tres megas por escalar unas pocas imágenes. Suma además
`thiserror`, `syn` y `document-features` para compilar. `image` sin
features compila `moxcms` y `pxfm` —el manejo de color que `imageops` no
usa— y el `lto` los tira enteros.

Cómo se ven, contra Pillow —que es lo que `resample` daba bit por bit—, en
diferencia por canal sobre 8 bits y en pixeles que cambian ya pasados a los
15 bits de la consola:

| caso | `image` | `fast_image_resize` |
|---|---|---|
| título 320x240 → 256x224, LANCZOS | máx 37, 1,5% de pixeles | máx 35, 1,9% |
| Game Over, ídem | máx 18, 0,4% | máx 23, 0,6% |
| fondo 320x160 → 256x128, LANCZOS con alfa | máx 6, 3,9% | máx 8, 5,4% |
| hoja de animación 480x192 → 320x128, LANCZOS con alfa | máx 18, 0,7% | máx 18, 1,0% |
| hoja de animación, bilineal achicando y agrandando | máx 1, 0,3% | máx 1, 0,2–0,3% |

Ninguno da vuelta la máscara de transparencia. Las dos se ven igual a ojo,
y las dos difieren de Pillow en lo mismo: los bordes duros, donde los
lóbulos negativos del LANCZOS pasan de 0 o de 255. Pillow recorta a un byte
después de **cada** pasada; `image` hace las dos en `f32` y recorta al
final, y por eso los máximos de 37 y 18 caen en un puñado de pixeles de
contorno. **Se elige `image`**: el mismo resultado por cinco kilobytes en
vez de tres megas.

Lo que `image` no hace y `fast_image_resize` sí: **premultiplicar el alfa**.
`imageops::resize` dice que lo supone hecho, así que se hace de los dos
lados de la llamada, en `f32` —sin el redondeo a byte que hacía Pillow con
`RGBa`—, para que un pixel transparente no tiña a sus vecinos.

Los dos usos quedan con el filtro que tenían: `Lanczos3` donde había
LANCZOS y `Triangle` —el bilineal de `image`— donde había BILINEAR.

## Lo hecho

Tres commits, en el orden que pide "lo verificable y lo opinable":

* **el cambio**: `Picture::resized` en `rm2k-render` —`imageops::resize`
  con el alfa premultiplicado en `f32`—, que usan el zoom de las celdas
  (`Triangle`) y `pixels.rs` de `rm2k-snes-images` (`Lanczos3`); y las
  pruebas que comparaban contra el Python, cambiadas a propósito: en
  `rm2k-render` las celdas con zoom se comparan por dónde caen y su
  tamaño, y el zoom por propiedades en `picture.rs`; en
  `rm2k-snes-images`, `python.rs` pasa a `answers.rs`, fijado con lo que
  contesta hoy, y dice que es una red de regresión y no una respuesta
  independiente;
* **los borrados**: `tools/snes/resample/`, `rm2k-render/src/resample.rs`,
  el miembro del workspace, `rust_projects` y `resample-test`.
  `test_layers.py` no lo nombraba;
* **la prosa**: `AGENTS.md`, `tools/README.md`, los README de
  `rm2k-snes-images` y `rm2k-render`, y el encabezado de
  `rm2k-snes-images`. Las tareas de `testing/` y los estudios fechados
  que lo citan quedan como estaban.

Los binarios, en `release`, antes y después: `rm2k-render` 1.458.328 →
1.460.176 B (+1,8 KB), `rm2k-snes-images` 1.351.240 → 1.349.128 B
(−2,1 KB).

## En ABL

En un clon de ABL fuera de `/shared`, rama `sin-resample` sobre
`d6053f5`, con las herramientas de esta rama adelante en el PATH:

* `abl.sfc` pasa de `35c76500…` a `0072d314…`, igual con `NO_CACHE=1` que
  con el caché;
* **37 parches de battlers** cambian (`just parches-check` lo dijo, color
  por color): los battlers se reducen fusionando lo que menos se ve, y un
  tono distinto cambia las fusiones. Regenerados con `just parches`, en su
  propio commit. Los de animaciones y mapas no cambian;
* **68 goldens** cambian, en un commit sólo de goldens. Ninguna se corre
  ni se recorta —un corrimiento de un pixel no explica ninguna—. Casi
  todas son uno o dos pasos de 5 bits en los bordes: el título 1,5% de los
  pixeles, el Game Over 1,5%, las animaciones menos del 0,1%, las imágenes
  chicas menos del 1%. **Dos cambian más que el redondeo**: las fotos
  grandes (60–80% de los pixeles; antes y después comparten 4 de 17
  colores, y el verde oscuro del árbol pasó a azul oscuro) y la pelea con
  su fondo, por la ROM y por el MSU-1 (12–18%; el cartel verde del fondo
  quedó más saturado). Las dos son el escalado amplificado por la
  reducción de colores —`keep_most_used` en las fotos,
  `merge_least_visible` en el fondo—, no un error del escalado, pero se
  ven. Hay una que mejoró: `imagen-grande-nave-40` perdió los pixeles
  negros sueltos que el LANCZOS de Pillow dejaba en los bordes duros (por
  qué, no lo medí);
* `just pruebas`: **993** en verde con las goldens nuevas, incluida
  `test_musica_techos.py`.

Lado a lado, con recortes x4 y un resumen por golden, en
`/shared/capturas/2026-10-02-sin-resample/`. **El merge espera el visto
bueno de taro**, sobre todo por las fotos y la pelea.

Acá: `just -f tools/justfile test` 32, `just -f tools/justfile rust-test`
sin fallas.

## Al mergear

* Instalar `rm2k-render` e `images`: `just -f tools/justfile install
  rm2k-render images`. Nada de Python cambió.
* Traer a `/shared/abl-snes` los dos commits de la rama `sin-resample` del
  clon (`/extras/scratch/corbatita/abl`): los parches de battlers y las
  goldens.
