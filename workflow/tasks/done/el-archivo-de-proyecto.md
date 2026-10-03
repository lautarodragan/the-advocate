---
name: "El archivo de proyecto de ABL"
description: "Los pasos 3 y 4 del plan: las perillas de ABL salen del código a rom/rm2k-snes.toml, y cartuchos.py queda como el mecanismo que lo lee"
type: refactor
assignee: taro
---

Pasos 3 y 4 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4, y la tabla de §3 con los ganchos). taro autorizó el 2026-09-29 a
Hornero a decidir lo abierto sin esperarlo. Lo decidido:

- **El archivo es `rom/rm2k-snes.toml`**: se llama como la suite que lo lee,
  igual que `Cargo.toml`, y vive en la raíz de ABL.
- **Las claves van en inglés** —son la interfaz de las herramientas, que van
  a ir en inglés, y renombrarlas después rompería el archivo de cada juego—;
  **los comentarios van en castellano**, porque el archivo es de ABL.
- **Una perilla por commit, con el mismo valor**, y la ROM byte por byte
  igual en cada uno.
- **`cartuchos.py` se queda como el mecanismo** que lee el archivo y arma
  (`rm2k-snes-cartridges`); lo de ABL —qué mapas, qué cartuchos, qué casos—
  pasa al archivo. La clave del caché sigue siendo el hash de los binarios
  hasta que haya versiones de verdad.
- **Los límites del motor medidos sobre ABL** (clase c del research) **no**
  van al archivo: se quedan en el código con un comentario que diga que se
  midieron contra A Blurred Line (decisión de taro).

## Lo hecho

La red de cada perilla: `SIN_CACHE=1 just cartuchos` antes de tocar nada y
después de cada una, con los sha256 de todo `rom/build/` menos `cache/`, los
`.o`, `sello.txt` y `conversor.log`, y los `.dbg` sin `mtime`. **Los `.sfc`,
`.sym`, `.msu`, `.pcm` y `musicdata.inc` no cambiaron nunca.** Lo único que
se movió: los dos `mapdata.inc`, por el bloque de la identidad (seis líneas,
dos `.define`), y por eso los `.dbg`, en números de línea y tamaños de
archivo; los símbolos, con sus valores, son los mismos.

1. **El archivo y su lector.** `rom/rm2k-snes.toml` y `tools/comun/perillas.py`:
   `perillas.valor("maps", "below", tipo=int)` falla con el nombre de la
   clave si falta, o si el tipo no es; `perillas.ascii` mide los textos que
   van a la ROM. El archivo entra entero en la huella de los cartuchos y en
   lo que `entregar` exige commiteado.
2. **Los cartuchos.** `[maps]`, `[debug]`, `[cases]` y `[cartridges.*]`.
   cartuchos.py lee el archivo y arma los flags en el orden de siempre, así
   que el sello sale igual. El 900 sale de `fork.nuevos()`: el de debug es
   el único mapa nuevo, y si hubiera otro se niega. Un cartucho nuevo es una
   tabla más.
3. **La identidad.** `[rom]`: `name`, `title`, `sram_signature`,
   `msu_data_signature`. El conversor emite `ROM_TITULO` y `SRAM_MAGIA_TEXTO`
   como `.define` al principio del `mapdata.inc` —fuera de `RODATA`, que el
   acomodo de bancos mueve—, y `cabecera.s` y `partida.s` los usan con
   `.byte` y `.strat`. La firma sigue siendo `ABLS`. `entregar.HUELLA_MSU`
   sale igual, letra por letra.
4. **Gráficos, pelea, saltos y `--map-id`.** `[graphics]`, `[battle]` y
   `[music] jumps_that_never_happen`. `--map-id` ya no tiene default: lo
   cobra `main` y no `required`, porque el parser se reusa para cada `--caso`.
5. **Las tablas de audio.** `[sound_effects]` y `[music]`. snes_music las
   expone como funciones —`se_enteros()`, `temas_aparte()`…— y las leen
   también eventos.py y snes_convert.py.
6. **Los límites del motor** (clase c): un comentario que dice que se
   midieron contra A Blurred Line en cada constante de Python. Los tres del
   runtime ya lo decían y no se tocaron, para no mover el `.dbg`.

**Se lee al usar, no al importar**, salvo en cartuchos.py, que es el
orquestador del juego: `test_las_herramientas_se_importan_sin_un_juego`
importa el conversor con el archivo apuntando a uno que no existe. Y
`rom/pruebas/herramientas/test_perillas_repetidas.py` falla si un `.py` de
las herramientas vuelve a escribir un texto del archivo: sobre el árbol de
antes de esto encontraba las tablas de efectos, `vswar`, `ABLBackdropSJ08`,
`savept`, `Future1`, `nobodyhere`, `test-special` y `mapa-de-debug`.

## Lo que no se hizo: el ambiente (el paso 7 del encargo)

Las herramientas siguen leyendo `ABL_GAME_DIR`, `ABL_RTP_DIR` y
`ABL_SOUNDFONT` por `comun/proyecto.py`. Cómo lo haría:

* `recursos.GAME_DIR`, `recursos.RTP_DIR` y `snes_samples.SOUNDFONT` son
  globales de módulo que se usan **adentro** de funciones, no sólo como
  defaults: `escena.py` y `snes_music.py` leen `recursos.RTP_DIR` sin que se
  lo pasen, y `snes_music` lee `snes_samples.SOUNDFONT` en tres lugares. Pasar
  el valor por parámetro toca unas cuarenta firmas. Lo más barato que
  respeta la regla es **un solo lugar que se configura**: `recursos` y
  `snes_samples` sin valor hasta que el `main` de cada ejecutable los fija
  desde `--game-dir`, `--rtp-dir` y `--soundfont`, y que fallen claro si
  alguien los lee sin fijar. Después, si vale la pena, se convierten en
  parámetros de a uno.
* Los ejecutables que los necesitan: `rm2k-snes-convert` (ya tiene
  `--game-dir`), `rm2k-snes-msu` (ya tiene `--soundfont`),
  `rm2k-snes-cartridges`, que se los pasa al conversor, y
  `rm2k-snes-volume-ceilings`.
* `rom/justfile` traduce: `--game-dir "${ABL_GAME_DIR:-…}"` y compañía, en
  las recetas que llaman a esos cuatro. El default de la máquina se queda en
  el justfile de ABL, que ya lo repite (`datos`, `ditto-*`).
* Las pruebas de ABL que leen `GAME_DIR` (unas veinte) leen la variable
  ellas: son del lado de ABL. `tanda` y `conftest.py` son el lugar.
* `huella` del cartucho no cubre dónde está el juego —no lo cubre hoy
  tampoco—, así que cambiar `--game-dir` no deja viejo a un cartucho: igual
  que ahora.
* `test_proyecto.py` pasa a prohibir `os.environ` de esas tres en todo
  `tools/`, `proyecto.py` incluido.

## Lo que queda abierto

* **La versión de la suite** que el juego declara en el archivo, y la receta
  `verificar-herramientas`: son de la decisión, pero no de este encargo.
* **`release` es un nombre que las herramientas exigen**: es el cartucho que
  lleva el nombre de la ROM, las pistas de MSU-1 y todos los casos.
  Podría ser una clave (`[rom] played_cartridge`), pero hoy lo nombran
  también `entregar`, `parches` y la tanda.
* **Los nombres de módulo de cartuchos.py** —`MENOR_A`, `CARTUCHOS`,
  `FUERA`— se quedaron por la tanda, que los lee. Renombrarlos o que la
  tanda lea el archivo es otro cambio.
