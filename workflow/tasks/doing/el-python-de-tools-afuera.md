---
name: "El Python de tools/, afuera: common/ a Rust y el arnés a tests/"
assignee: Tero
---

# El Python de `tools/`, afuera

De taro, el 2026-10-02. En `tools/` quedan dos paquetes de Python que el
conversor ya no usa: los importa el arnés de pruebas de ABL —unos 24
archivos— a través de `rm2k-snes-python-path`.

- `common/` (`project.py`, `settings.py`, `environment.py`): un segundo
  lector del `rm2k-snes.toml` y de los flags de la máquina, al lado de
  `rm2k-project`, que es el de Rust. Dos modelos del mismo formato es lo que
  la guarda de Ditto prohíbe para el volcado.
- `emulator/retro.py`: el que maneja un core de libretro cuadro por cuadro.
  Es de las pruebas y nada más.

## Lo decidido

- **`common/` se va.** El arnés le pregunta a un binario de Rust lo que hoy
  le pregunta a `common/` —por ejemplo `rm2k-snes-project`, que imprime la
  configuración resuelta en JSON—, y `rm2k-project` es el único que lee el
  `rm2k-snes.toml`. Se van también sus pruebas, `test_project.py` y
  `test_settings.py`, o lo que cubrían pasa a pruebas del crate.
- **Las pruebas se quedan en Python.** Lo que es sólo de pruebas **se
  mueve, no se migra**: sale de `tools/` a una carpeta de pruebas, sin
  reescribirlo. `retro.py` es el caso.

## Qué le pedía el arnés a `common/`

Medido con grep sobre ABL en `a942b02`, los 24 archivos:

- **`project`**: rutas del juego —`data()` catorce veces, `build()`,
  `patches()`, `manual_patches()`, `auto_patches()`, `project_file()`,
  `directory()`—, rutas de la suite —`root()`, `tools()`, `runtime()`, en
  `entregar.py`, `render_map.py` y `test_perillas_repetidas.py`— y
  `use`/`from_command_line`/`add_argument` para elegir el proyecto.
- **`settings`**: tres perillas —`[rom] name`, `[rom] sram_signature`,
  `[battle] fallback_backdrop`— y el archivo entero, en
  `test_perillas_repetidas.py`.
- **`environment`**: nada que salga del archivo. El arnés lo usaba como
  caja de valores de la máquina: `lugares.py` lo llenaba con `ABL_GAME_DIR`
  y las demás, y `conversor.py` y `musica.py` le pedían los flags para
  pasárselos a una herramienta; `entregar.py`, su `--shared`.

Todo lo que es regla —que `[paths]` es relativo al archivo, que los
parches a mano están en `manual/`, dónde está el runtime— ya estaba en
`rm2k-project`; lo único que no exponía era el archivo entero
(`Project::settings`).

## Cómo lo contesta ahora

- **`rm2k-snes-project`**, un `[[bin]]` del crate `rm2k-project`
  (`src/main.rs`, y lo que imprime en `src/resolved.rs`): un JSON con
  `project` —las rutas del juego ya resueltas—, `suite` —`tools`, `root`,
  `runtime`, del checkout del que se instaló— y `settings` —el archivo
  entero, en orden—. Chequea lo que la biblioteca chequea para cualquier
  herramienta y nada más: que `sram_signature` sean cuatro letras ASCII lo
  exige el conversor al armar, no éste.
- En ABL, **`pruebas/arnes/proyecto.py`** lo llama una vez por proceso
  (con `lru_cache`) y da `ruta(...)`, `de_la_suite(...)`, `ajuste(...)` y
  `ajustes()`. `lugares.py` le dice cuál es el proyecto, como antes a
  `common.project.use`.
- Lo de la máquina **no pasó a Rust**: no es una regla del formato sino de
  qué flag recibe cada herramienta, que el arnés ya sabe para todas las
  demás (`--project`, `--maps`…). `lugares.py` guarda los valores —`JUEGO`,
  `RTP`, `SOUNDFONT`, `CACHE`— y `lugares.banderas(...)` los da como flags.
  `entregar.py` tiene su `--shared` en su propio `argparse`, y dejó de
  aceptar `--project`: es de ABL y el proyecto es ABL.

## Adónde fue cada cosa, y por qué

- **`tools/emulator/` —`retro.py` y `bsnes-wram.patch`— a ABL, a
  `pruebas/arnes/emulator/`.** Lo importa sólo el arnés de ABL, y con eso
  el arnés deja de importar nada de las herramientas: se van
  `rm2k-snes-python-path` y `pruebas/arnes/suite.py`, y ABL vuelve a
  conocer sólo ejecutables del PATH, que es la regla de
  `decisiones/las-herramientas-se-separan-de-abl.md`. La otra opción era
  una carpeta de pruebas en la raíz de este repo, donde vuelven las
  pruebas de ROM en la fase 2; pero hasta entonces su único usuario sería
  ABL, y habría que mantener un mecanismo para que otro repo la importe
  —un ejecutable que diga la ruta— por un solo archivo. Cuando en la fase
  2 se parta el arnés, `retro.py` vuelve con el resto de lo genérico, y el
  cómo lo importa ABL se decide ahí, con el arnés entero y un segundo
  usuario de verdad. Como paquete y no como módulo suelto, para que
  `from emulator import retro` siga igual en los nueve que lo importan. La
  copia es byte por byte la de `3bddfeb8`, en su propio commit; los dos
  comentarios que nombraban `tools/runtime/` se tocaron en el siguiente,
  porque `test_lado_de_abl.py` no deja que una prueba nombre `tools/`.
- **`tools/tests/` se queda.** Miran el árbol de `tools/` —las capas, quién
  lee el volcado, que nada nombre a ABL, el índice— y no necesitan nada
  de afuera: son de la suite como las pruebas de un crate lo son del
  crate, y las corre `tools/justfile`. La carpeta de pruebas de la fase 2
  es para pruebas de ROM con un juego, que es otra cosa. Dejan de importar
  `common`: sacan `tools/` de `__file__`, dos carpetas arriba.
- **`test_project.py` y `test_settings.py` se van con `common/`.** Lo de
  `test_settings.py` —clave que falta, tipo equivocado, `true` no es `1`,
  `ascii`— ya lo cubrían `tests/project.rs` del crate. `test_project.py`
  miraba que ningún `.py` de `tools/` armara rutas a mano ni leyera
  `ABL_*`: sin Python en `tools/` no tiene qué mirar, y que nada nombre a
  ABL lo sigue cuidando `test_no_game_names.py`, también en Rust y en el
  `justfile`. Llegaron tres pruebas al crate: lo resuelto, el error sin
  `[paths]` y el binario corriendo de verdad.

- **De paso, la huella de `rm2k-snes-cartridges`** dejó de leer los `.py`
  de `tools/`: era de cuando el conversor era Python, y con `common/` y
  `emulator/` afuera no quedaba ninguno. Cambia la huella, así que el
  primer `just cartuchos` después de instalarlo rearma todo, igual byte
  por byte.

## Lo que queda flojo

- `test_perillas_repetidas.py`, en ABL, busca valores del archivo de
  proyecto repetidos en los `.py` de las herramientas: hoy sólo quedan los
  de `tools/tests/`, así que mira casi nada. Lo que protegía —un default
  del juego escrito en una herramienta— hoy viviría en Rust. Se deja
  andando; extenderlo a los `.rs` o borrarlo es de taro.
- La clave de la suite en el JSON se llama `directory` y no `tools`:
  `test_lado_de_abl.py` no deja que una prueba de ABL escriba `"tools"`.

## Hecho

Herramientas, en la rama del worktree:

- `9d015fb4` `rm2k-snes-project`, con tres pruebas nuevas en el crate.
- `8b2d796e` `git rm` de `tools/emulator/`, solo.
- el de criterio: `common/` y sus dos pruebas afuera, `tools/tests/` sin
  importar nada, el `justfile` sin scripts ni `install-scripts`, la
  huella, los README y `AGENTS.md`.

ABL, rama `tero-python-afuera` en `/extras/scratch/tero/abl`:

- `bf22a0d` la copia del emulador, byte por byte.
- `dc3a817` el arnés le pregunta a `rm2k-snes-project`; afuera `suite.py`.

Verificado:

- `just -f tools/justfile test`: de 52 a 27; se fueron las 25 de
  `test_project.py` (20) y `test_settings.py` (5).
- `cargo test -p rm2k-project`: 18 (eran 15); `-p rm2k-snes-cartridge` en
  verde.
- La tanda de ABL con `project` y `cartridge` del worktree adelante en el
  PATH: 993 en verde, y `abl.sfc` `8c9e670f8c86d7c4…` igual, rearmado
  por la huella nueva.
- Con un `rm2k-snes-project` que contesta un `data` que no existe: 124
  fallan y 74 dan error, todos leyendo `/no/existe`.

## Al mergear

- **El orden importa**: el arnés nuevo de ABL necesita `rm2k-snes-project`
  instalado, y el `directory` de su JSON. Primero este merge e instalar;
  después el `git pull` de la rama de ABL.
- Instalar en el global `project` y `cartridge`: `just -f tools/justfile
  install project cartridge`. Como `project` es la biblioteca de todos,
  lo prolijo es `just -f tools/justfile install` entero; para la ROM
  alcanza con esos dos, porque los demás binarios no cambiaron de
  comportamiento.
- El `_install` borra solo el symlink viejo `rm2k-snes-python-path`, que
  quedaría apuntando a nada.
