---
name: "Las herramientas sin datos ni código de ABL"
description: "Lo que en tools/ nombra o trae algo de ABL fuera de los comentarios: datos de prueba, fixtures copiados del juego, defaults y literales en el código; los comentarios se quedan por la decisión de las herramientas"
type: refactor
assignee: taro
---

De taro, el 2026-10-02, al ver que una prueba del compilador de eventos usa
`PhoneCallDiff` como dato: "dale". Un `grep` de nombres de ABL (personajes,
lugares, imágenes, la sigla) da 125 líneas en unos 50 archivos de `tools/`.

**Los comentarios del motor que nombran a ABL se quedan**, como dice
`decisiones/las-herramientas-se-separan-de-abl.md` ("por ahora, por
cuidado"), y los límites medidos contra ABL siguen con su comentario. Lo que
se limpia es lo otro: datos de prueba y fixtures, defaults, literales en el
código. Y hace falta para el juego de pruebas: este repo no tiene que
llevar nada de ABL (`testing/el-juego-de-pruebas.md`).

# Lo que se encontró (Monterita, 2026-10-02)

El `grep` del encargo da, sobre `3bf9aaf5`, 125 líneas en 53 archivos. Se
clasificaron sacándole a cada archivo los comentarios con las mismas reglas
de la guarda (abajo):

| clase | líneas | archivos | qué se hizo |
|---|---|---|---|
| comentarios del runtime (`;`) | 41 | 26 | se quedan, por la decisión |
| comentarios y docstrings de los crates y del Python | 53 | 17 | se quedan; salvo los de pruebas del compilador que citaban mapas de ABL |
| prosa de `.md` | 14 | 3 | se quedan como contexto, menos una que estaba vieja |
| datos de prueba y literales en pruebas | 15 | 9 | cambiados |
| literales en código | 2 | 2 | se quedan: son comentarios del `.inc` que se emite |

Pero el `grep` no veía todo. Para encontrar lo demás se cruzó cada literal
de `tools/` fuera de los comentarios contra todos los textos del volcado de
ABL y los nombres de sus archivos que no son del RTP (un script
descartable), y aparecieron: oradores en mayúsculas (`KERSH`, `MANTA`,
`TALAN`, `CONDA`, `CORE`), líneas de diálogo sin ningún nombre, el término
de victoria, un battler (`sentry drone`, `BLmouse`), un CharSet (`Future2`),
imágenes (`AdvoInstr`, `smoke1`), "What's the password?", y el `abl-*` del
`justfile`. Lo que coincidía era casi siempre palabra común (`Sword`,
`Potion`, `Sign`, `Thunder`, `Attack`): eso se quedó.

**Los fixtures que eran copia del juego**, todos texto —las imágenes de
prueba son de fórmula, se miraron—:

* `rm2k-snes-text`: las cajas de `tests/refit.rs` (todas diálogo de ABL
  menos una), dos casos de `tests/escapes.json`, y en `tests/python.rs` un nombre
  y dos oradores;
* `rm2k-snes-screens`: los cuadros de `tests/game/` (mapa 1 y evento
  común 1), las mismas líneas;
* `rm2k-snes-events`: el orador de la caja que se rearma, en
  `compile.json`, `scan.json` y el mapa 1 del juego chico;
* `rm2k-snes-mapdata`: los nombres "Talan's Pad" y "Lashe City - 34,35" de
  `tests/maps.json` (el resto del fixture es inventado);
* `rm2k-snes-patches`: el battler con un espacio.

Se reemplazaron por texto inventado **del mismo largo palabra por palabra**,
con la misma puntuación y oradores de la misma forma, porque eso es lo que
miran el reparto y los escapes. Los hashes contra el Python que cambiaron
(nueve: dos de text, cuatro de mapdata, uno de events, uno de screens, uno
de patches) se cambiaron a propósito, comprobando que la respuesta nueva,
con los nombres viejos de vuelta, es la vieja byte por byte; en screens,
que cada caja corta en los mismos lugares. Lo dice el comentario de cada
prueba y el commit.

Los comentarios de prueba que se reescribieron son los del compilador
(`compile.rs`), que decían de qué mapa de ABL salía cada caso. Los de la
prueba de `mapdata/src/vram.rs` se quedan: son un límite medido.

**La guarda** es `tools/tests/test_no_game_names.py`: saca los comentarios
de cada archivo de `tools/` (`;`, `//`, `/* */`, `#`, docstrings), saltea
los `.md` y busca una lista de palabras de ABL. Excepciones: el propio
archivo, `test_project.py` (escribe `ABL_*` a propósito) y las dos líneas
del `.inc` emitido, por pedazo de texto y con una prueba que falla si ya
no coinciden. Un `const _RED: &str = "PhoneCallDiff";` en
`rm2k-snes/text/src/refit.rs` la pone en rojo. Sobre `3bf9aaf5`
encontraba 64 apariciones en 15 archivos. Lo que **no** ve: una línea
copiada sin ningún nombre adentro.

Las tandas: `just -f tools/justfile test` pasó de 32 a 52 (la guarda, la
de las excepciones y dieciocho casos de la red); `cargo test -p` de los
ocho crates tocados, en verde. Ningún binario cambia —los `.rs` tocados lo
son en sus pruebas—, así que la ROM no se puede mover; igual se corrió la
tanda de ABL en un clon, con estas herramientas adelante en el PATH.

**Al mergear no hay que instalar nada**: no cambia ningún binario ni el
nombre de ningún script.

La tanda de ABL, en un clon de `/shared/abl-snes` (`a942b02`) con el
`bin/` local de este worktree adelante en el PATH: 993 en verde antes y
después, y `abl.sfc` `8c9e670f8c86d7c4…` las dos veces. No dice mucho, y
está bien que no: no hay nada en la ROM que esto pueda mover.
