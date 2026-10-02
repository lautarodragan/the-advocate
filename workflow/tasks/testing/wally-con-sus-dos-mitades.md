---
name: "Wally con sus dos mitades adentro"
description: "map-background y map-sprites dejan de ser crates: pasan a ser módulos de Wally, con una prueba que cuide que el fondo no use los sprites ni al revés; mapdata pasa a usar la biblioteca de Wally"
type: refactor
assignee: taro
---

De taro, el 2026-10-02: "map-background podría pasar a ser parte de wally y
ya, no?" y, para las dos, "dale". Mara los separó en tres crates para que
Cargo cuidara que el fondo no sabe de los objetos y al revés
(`testing/rust-el-dominio-de-los-mapas.md`, "Un crate o varios"); esa
frontera pasa a cuidarla una prueba.

## Cómo quedó

* `tools/rm2k-snes/wally/src/background/`: lo que era
  `rm2k-snes-map-background` —`mod.rs` (era `lib.rs`), `layers.rs`,
  `grid.rs`, `blocks.rs`, `fail.rs`—, y su prueba contra el Python en
  `wally/tests/background_python.rs`, porque Wally ya tenía un `python.rs`.
* `tools/rm2k-snes/wally/src/sprites/`: lo que era `rm2k-snes-map-sprites`
  —`mod.rs`, `character.rs`, `npc.rs`, `split.rs`, `bank.rs`, `share.rs`,
  `extras.rs`, `fail.rs`—.
* Cada mitad conserva su `Bad`: `wally::Bad` sigue convirtiendo el del
  fondo, y el de los sprites lo sigue pasando `map.rs` a mano.
* `rm2k-snes-mapdata` depende de `wally` en vez de `rm2k-snes-map-sprites`
  (`wally::sprites::character`, `wally::sprites::extras`). Lo que suma
  Wally a mapdata —`ditto`, `rm2k-rules`, `clap`, `serde_json`— ya lo tenía
  o es del workspace: nada pesado. Las capas no cambian: los dos están en
  `rm2k-snes/`, y `test_layers.py` no los nombraba.

**La frontera** la cuida `wally/tests/halves.rs`, leyendo el fuente: en
`src/background/` y `src/sprites/`, todo `crate::` tiene que seguir con el
nombre de esa mitad, y ningún `super::` puede salir de ella. Es lo mismo que
cuidaba Cargo: tampoco usan el resto de Wally. Lee los comentarios también.
Rojo visto: con `use crate::sprites::npc::Npc;` en `background/layers.rs`
y `use crate::background::Converted;` en `sprites/npc.rs` falla nombrando
las dos líneas —y el crate compila igual, con un warning de no usado, que
es justamente por qué hace falta—; sin ellas, verde.

## Commits

| commit | qué |
|---|---|
| `94ef6b19` | la mudanza: `git mv` y los `use`, los manifiestos, y las dos líneas del `justfile` que nombraban los crates (la lista de proyectos y `wally-test`), que si no se rompen |
| `e72bd778` | `tests/halves.rs`, y `94ef6b19` a `.git-blame-ignore-revs` |
| `6ae5111a` | la prosa: README de Wally, `tools/README.md`, `AGENTS.md`, comentarios de mapdata, del `justfile`, de `docs/port/vram.md` y de tres `.s` del runtime |

Las líneas del `justfile` fueron al commit mecánico y no al de la prosa
porque sin ellas `wally-test` hace `cd` a directorios que no existen.

`blame` sigue la mudanza sin opciones (`layers.rs` del fondo: 498 de 505
líneas en `7db8c984`, 2 en la mudanza), y con `--ignore-rev` las dos
vuelven a su commit.

## Verificación

En un clon de ABL fuera de `/shared`, con `wally`, `rm2k-snes-mapdata` y
`rm2k-snes-convert` de este worktree adelante en el PATH:

* `NO_CACHE=1 just cartuchos`: los 1424 archivos de `build/` (sin caché,
  `.o`, sellos ni log; el `.dbg` sin mtime) iguales a los de la base,
  armada antes con las herramientas globales. `abl.sfc` en `35c76500`.
* `just pruebas`: 993, como la base.
* `just -f tools/justfile test`: 32, como la base.
* `cargo test -p wally -p rm2k-snes-mapdata`: 93, verde, sin tocar un hash
  (incluye las dos de `halves.rs`).

## Al mergear

* Instalar en el global `wally`, `mapdata` y `convert`: `just -f
  tools/justfile install wally mapdata convert`. `convert` porque enlaza
  mapdata, que ahora enlaza Wally; el código es el mismo, pero así el
  global sale de un árbol que existe.
* No hay nada que desinstalar: `map-background` y `map-sprites` eran
  bibliotecas y nunca dejaron un binario en el global.
* Los tres `.s` del runtime cambian sólo comentarios: la ROM sale igual,
  pero el `.dbg` anota el tamaño de cada fuente y ése cambia.
