---
name: "Los justfile, más chicos"
description: "Sacar de los dos justfile —el de las herramientas y el de ABL— las recetas que ya no se usan, y simplificar las que quedaron complicadas después de la migración a Rust y la separación en dos repos"
type: refactor
agents: [Calandria]
assignee: Calandria
---

De taro, el 2026-10-05: "creo que podemos eliminar cosas del `justfile`,
no? Y simplificar otras?".

## El inventario (Calandria, 2026-10-04)

Sobre `main` en `c8d5064f` y ABL en `c76157d`.

"Usuarios" es dónde se nombra fuera del propio `justfile`, en los dos
repos y sin contar las tareas terminadas; "última" es el último commit que
agregó o sacó una invocación suya fuera de los `justfile` —`git log -G
'just… <receta>'`—, y "en `done/`" cuántas tareas terminadas cuentan
haberla corrido. En ABL los commits del 2026-10-02 son el nacimiento del
repo, y en éste `d356bfb7` es el borrado de lo que se fue: los dos dicen
"se mudó", no "se usó". Y pesa una cosa que no está en git: **taro no
corre recetas a mano** (lo dijo el 2026-09-06), así que su único usuario
somos nosotros, y lo que se pesa es el costo de mantenerlas.

Los scripts que hicieron las cuentas, por si hay que rehacerlas, en
`/extras/scratch/calandria/tmp/` (`usos.sh`, `ultimo.sh`, `done.sh`,
`huerfanas.sh`).

### `tools/justfile`

| receta | qué hace | usuarios | última | propuesta |
|---|---|---|---|---|
| `test` | `pytest` de `tools/tests/`: capas, lectores del volcado, índices, nombres de juegos | README, `tools/tests/README.md`, AGENTS.md, la verificación de cada merge | 2026-10-04 | dejar |
| `rust-test` | `cargo test --workspace`, en debug | README, `tools/README.md` | 2026-10-02 | dejar |
| `gunter-test`, `rules-test`, `adeleine-test`, `voodoo-test`, `goombario-test`, `project-test`, `cartridge-test`, `patches-test`, `battle-test`, `bytecode-test`, `events-test`, `wally-test`, `screens-test`, `images-test`, `mapdata-test`, `convert-test` | `cd <crate> && cargo test` | ninguno | nunca | **pregunta 1** |
| `lz2-test`, `render-test`, `audio-test` | lo mismo, en `--release` | `lz2-test` como ejemplo en `tools/README.md`; `audio-test` en AGENTS.md y `docs/port/audio.md`, con `SOUNDFONT` | 2026-10-02 | **pregunta 1** |
| `ditto-test` | `cargo test` de Ditto, con `DITTO_CORPUS` | DITTO.md | 2026-09-29 | **pregunta 1** |
| `ditto-round-trip` | Ditto en release con `--include-ignored`, y se niega sin `DITTO_CORPUS` | DITTO.md | 2026-09-29 | dejar: no es un `cargo test` pelado |
| `install` | `cargo install` de los proyectos nombrados, o de todos, en `CARGO_ROOT` | AGENTS.md, `tools/README.md`, el error de `stage.rs` del conversor | 2026-10-04 | dejar |
| `install-local` | lo mismo en un `bin/` de un worktree; se niega en el checkout principal | AGENTS.md, `.claude/agentes.md`, `tools/README.md` | 2026-10-04 | dejar |
| `_not_in_main_checkout`, `_install` | privadas de las dos de arriba | `install`, `install-local` | — | dejar; la limpieza de symlinks de `_install`, **pregunta 2** |
| `which` | qué binario resuelve este checkout para cada herramienta | una tarea (`los-bytecodes-en-rust`) | 2026-10-02 | dejar, y **arreglar**: le faltaban `rm2k-snes-mapdata` y `rm2k-snes-audio` |

### `justfile` de ABL

| receta | qué hace | usuarios | última | propuesta |
|---|---|---|---|---|
| `datos` | `ditto unpack` del juego a `data/` y `build/ditto-exacto/` | `rm2k-snes.toml`, `docs/port/pipeline.md`, `parches/manual/README.md`, el arnés, DITTO.md | 2026-10-02 (3 en `done/`) | dejar |
| `ditto-volcado` | `just datos` a `/extras/volcado-ditto` | **ninguno**: ni docs, ni pruebas, ni una tarea, en ninguno de los dos repos | nunca | **borrar**: es `just datos <dir> <dir>-exacto` |
| `datos-vuelta` | `unpack` + `pack` del juego, byte por byte contra el original | DITTO.md | 2026-09-29 (2 en `done/`) | dejar |
| `pruebas` | la tanda, en paralelo, después de `cartuchos` | todo | 2026-10-03 | dejar |
| `pruebas-rpgmaker`, `pruebas-abl`, `pruebas-herramientas` | la tanda de una carpeta | `pruebas/README.md` | 2026-10-02 (ninguna en `done/`) | **pregunta 3** |
| `_xdist` | se niega si falta pytest-xdist | las cuatro de arriba | — | dejar |
| `cartuchos` | `rm2k-snes-cartridges` con los flags de la máquina | `pruebas`, AGENTS.md, estudios | 2026-10-02 | dejar |
| `espacio` | `rm2k-snes-space`, armando antes lo viejo | AGENTS.md, `main.s`, `emit.rs`, estudios | 2026-10-04 | dejar |
| `parches` | copia a `parches/` las decisiones de `release` | `rm2k-snes-patches` (sus mensajes), `parches/README.md` | 2026-10-03 | dejar |
| `parches-check` | `rm2k-snes-patches --check` | `test_parches.py`, `parches/README.md` | 2026-10-02 (7 en `done/`) | dejar; ver **pregunta 5** |
| `techos` | `rm2k-snes-volume-ceilings` | `test_musica_techos.py`, `techos.toml`, `ceilings.rs` | 2026-10-03 | dejar |
| `build` | `rm2k-snes-cartridges` con un nombre: **lo mismo que `cartuchos <nombre>`** | `parches`, `entregar`, `video`; `test_msu.py`, `docs/port/pipeline.md`, una tarea de la wishlist | 2026-10-02 | **pregunta 4** |
| `entregar` | `entregar.py` después de armar `release` | AGENTS.md de los dos repos, `docs/snes/emulators.md` | 2026-10-02 | dejar |
| `video` | `pruebas/arnes/video.py` | `test_video.py`, `pruebas/README.md` | 2026-10-02 (6 en `done/`) | dejar |
| `menu-modo-5`, `fuentes` | ROM de prueba del menú en modo 5 y de las fuentes, y su verificación | `experimentos/` | 2026-10-02 (`una-fuente-para-la-alta-resolucion`) | **pregunta 6** |
| `msu-puerto` | ROM de prueba del puerto de datos del MSU-1 | el estudio de los mapas por el MSU-1 (su fase 0 es medir el FX Pak) | 2026-10-02 | **pregunta 6** |
| `exhirom` | ROM de prueba de ExHiROM | `docs/snes/emulators.md`, `experimentos/` | 2026-10-02 | **pregunta 6** |
| `zoom-modo-7`, `zoom-modo-7-videos` | ROM de prueba del zoom en modo 7, y sus videos al lado del original | `experimentos/` | 2026-10-02 (`el-piloto-del-modo-7`) | **pregunta 6** |

Lo que **no** encontré: ninguna receta de Python que envuelva un script
que ya no existe, ninguna de `rom/`, y ninguna invocación `just X` en los
docs que nombre una receta que no existe, fuera de las históricas
(`hitos-foto`, en los dos AGENTS.md, y `diagnostico`, en un estudio
fechado de ABL). La migración a Rust y la separación ya habían limpiado lo
grueso.

## Lo aplicado

* `which` lista también `rm2k-snes-mapdata` y `rm2k-snes-audio`, que se
  instalan y no listaba.
* Se va `ditto-volcado`, de ABL.
* Una línea de resumen al final del comentario de cada receta, en los dos
  `justfile`: es la que muestra `just --list`, que hasta ahora mostraba la
  cola de una frase. En ABL ya era la convención de la mitad de las
  recetas.
* La prosa del `tools/justfile` que había envejecido, en su commit: que
  `rm2k-rules` todavía tiene una copia en Python (el conversor ya es Rust,
  y `tests/test_rm2k_rules.py` no existe), que los nombres siguen "el repo
  en que van a vivir cuando las herramientas se separen" y los `abl-`, y
  que el `justfile` del juego "se niega" sin su `bin/` local (desde el
  2026-10-02 usa el global).

## Preguntas para taro

1. **Las veinte `<crate>-test`.** Cada una es `cd <crate> && cargo
   test` —tres en `--release`—, y casi ninguna la nombra nadie. Se podrían
   reemplazar por una sola, `just crate-test lz2`, que haga `cargo test -p`
   con el nombre del crate (y `--release` para los tres que lo piden), más
   `rust-test` para todos. Lo que se perdería es el lugar de los
   comentarios —"sus pruebas no necesitan el juego"—, que se mudarían al
   `Cargo.toml` o al `lib.rs` de cada uno, donde los lee quien toca el
   crate. Cambia nombres que nombran AGENTS.md, DITTO.md y
   `docs/port/audio.md` (`audio-test`, `ditto-test`, `lz2-test`), y por
   eso no lo apliqué. Mi propuesta: hacerlo.
2. **La limpieza de symlinks de `_install`**: borra los `rm2k-snes-*` que
   sean symlinks, que eran los scripts de Python hasta el 2026-10-02. En
   `/usr/local/bin` ya no queda ninguno; en el `~/.cargo/bin` del host no
   lo sé. Si ahí tampoco, sobra.
3. **`pruebas-rpgmaker`, `-abl` y `-herramientas`**: tres recetas para una
   carpeta cada una, que nadie corrió en ninguna tarea terminada. `just
   pruebas` no sirve para eso porque le pasa `pruebas` a pytest siempre;
   si en vez recibiera la carpeta —`just pruebas pruebas/abl`, y sin nada,
   `pruebas`—, las tres se irían. Mi propuesta: hacerlo.
4. **`build` es `cartuchos` con un argumento**: `just build release` y
   `just cartuchos release` corren lo mismo. Se podría ir, con `parches`,
   `entregar` y `video` dependiendo de `(cartuchos "release")`, y el
   comentario largo de las pistas de MSU-1 mudándose a `cartuchos`. Cambia
   un nombre que nombran `test_msu.py` y `docs/port/pipeline.md`. Mi
   propuesta: hacerlo.
5. **Las herramientas nombran recetas de ABL**: `rm2k-snes-patches` dice
   "run `just parches`" y escribe en el encabezado de cada `parches/auto/`
   "`just parches --check`" —que además no existe: es `just
   parches-check`—, y `rm2k-snes-volume-ceilings` dice "`just techos`".
   AGENTS.md dice que adentro de esos proyectos no se nombra el juego.
   Arreglarlo cambia la salida de la herramienta y los archivos
   versionados de `parches/` de ABL, así que no es de esta tarea: ¿va
   una aparte?
6. **Las seis recetas de los experimentos** (`menu-modo-5`, `fuentes`,
   `msu-puerto`, `exhirom`, `zoom-modo-7`, `zoom-modo-7-videos`): son
   ROMs de prueba de decisiones ya tomadas —el modo 5 y las fuentes, los
   8 MB, el piloto del modo 7—, salvo `msu-puerto`, cuya fase 0 (medir el
   FX Pak) sigue abierta. Cada script de `experimentos/` ya dice en su
   encabezado cómo se corre. Se podrían ir del `justfile` y correrse
   directo (`experimentos/exhirom/armar.py build/exhirom/exhirom.sfc && …`),
   que es lo que hacen las recetas. Son media pantalla de `just --list`.
   Mi propuesta: sacarlas, dejando en cada `experimentos/<x>/` las dos
   líneas que corría la receta.

Fuera del `justfile`, visto de paso: el encabezado de
`tools/rm2k/rules/tests/python.rs` dice todavía que "las reglas existen
también en Python, en el conversor que las sigue usando", y nombra
`tests/test_rm2k_rules.py`, que no existe. No lo toqué: es del crate.

## Verificado

Con las herramientas globales: ninguna de las dos ramas toca Rust, así que
al mergear no hay nada que instalar.

* `just -f tools/justfile test`: 27 pasan.
* La tanda de ABL en mi clon, con su rama (`calandria-justfile`): 1094
  pasan. `abl.sfc` es `924c33ea3b51c958…`, la de antes.
* `just --list` de los dos lados: veintiséis recetas en las herramientas y
  veinte en ABL, cada una con su resumen.
* `just entregar` con `SHARED=/extras/scratch/calandria/shared`: deja el
  build con `abl.sfc`, `.dbg`, `abl.msu`, `tools/` y `LEEME.txt`. La
  carpeta tiene que existir: `entregar.py` se niega si no, a propósito.
* `cargo test --workspace --no-fail-fast`: **un rojo, que no es de esta
  rama**: `the_layers_are_the_ones_the_python_made`, en
  `wally/tests/background_python.rs` ("plain: the tiles"). Nació en
  `bfa2e1c4` (la flecha del System): en su padre pasa, en él y en
  `c8d5064f` falla —`cargo test -p wally --test background_python` en
  cada uno—. Lo demás pasa.

Lo que no corrí: las recetas de los experimentos, y `datos` y
`datos-vuelta`, que sólo cambiaron su comentario.

# Lo que decidió taro

El 2026-10-05: "Me gustan todas tus propuestas para el justfile! Y la verdad
que no instalo nada de esto ni lo corro en el host, así que no lo tengas en
cuenta por ese lado. Si corro algo a mano, lo haré dentro del contenedor, y
te preguntaré primero". O sea, las seis preguntas, sí: las `<crate>-test`
en una, sin la limpieza de symlinks de `_install`, un solo `pruebas` con la
carpeta, sin `build`, las herramientas que nombran recetas de ABL (que acá
iban como tarea aparte y van en ésta), y sin las recetas de los
experimentos cerrados, salvo `msu-puerto`.
