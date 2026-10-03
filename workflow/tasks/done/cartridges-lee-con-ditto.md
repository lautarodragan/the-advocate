---
name: "rm2k-snes-cartridges lee el volcado con Ditto"
description: "El tercer lector del volcado a mano: cartridges.rs lee maps.json por su cuenta para el tipo de cada nodo; que use la biblioteca de Ditto, y una prueba que impida un cuarto"
type: refactor
assignee: taro
---

Lo dejó anotado Zorzal el 2026-09-29 (`testing/rust-ditto-como-biblioteca.md`):
desde que la biblioteca de Ditto es el único lugar en Rust que sabe leer el
volcado, queda un lector a mano en `tools/rm2k-snes/cartridge/src/cartridges.rs`,
que lee `maps.json` para saber el tipo de cada nodo del árbol. Que pase a
`ditto::dump::Dump`, y una prueba (en `tools/tests/`, como la de capas) que
falle si un crate que no es Ditto lee un `.json` del volcado por su cuenta.

## Lo que se hizo (Cardenal, 2026-09-29)

**`cartridges.rs`** leía `data/maps.json` con `serde_json` y armaba un
`HashMap<id, tipo>` a mano; el tipo 1 era "mapa". Ahora abre el volcado con
`ditto::dump::Dump`, lee el árbol con `dump.tree()` y lo guarda como el
`Tree` de `rm2k-rules` —el mismo que usa `battle`—; "es un mapa" es
`TreeMapMapType::Map`. El nodo `arbol` de los mapas nuevos de
`parches/manual/nuevos/` se sigue leyendo del JSON del parche (es del
proyecto, no del volcado), pero se convierte con el tipo de Ditto, `MapInfo`,
y pisa al del juego con `Tree::insert`, como antes. La prueba de
`cartridge` tuvo que escribir un `ditto.json` en su volcado de juguete.

**Un cuarto lector que no estaba en la tarea**: `rm2k-snes-events`
(`game.rs`, `Game::map`) armaba la ruta `maps/MapNNNN.json` del volcado a
mano para dársela a `read_map`. No parseaba a mano, pero copiaba el layout;
ahora es `Dump::map`. Es una línea en el crate de Churrinche.

**La prueba**: `tools/tests/test_dump_readers.py`. El criterio está arriba de
ella: ningún `src/` de un crate que no sea Ditto nombra el layout del
volcado —`"ditto.json"`, `"maps.json"`, `"database.json"`, `.join("db")`,
`.join("maps")`, `"Map….json"`, `.tiles"`— fuera de comentarios. Los
`tests/` de los crates quedan afuera (escriben volcados de juguete), y los
pedidos `--request` y los parches no usan esos nombres. Es un grep: un
nombre armado por partes pasa.

Vista fallar: con un `read_json(&p.data()?.join("maps.json"))` metido a
propósito en `cartridges.rs` dio rojo nombrando la línea; sacado, verde.
Sobre el `main` de partida (`5dc54ff7`) habría marcado tres líneas: las dos
de `cartridges.rs` y la de `events`.

**Al mergear hay que instalar** `cartridge` y `events`:
`just -f tools/justfile install cartridge events`.

**Verificado**, con `NO_CACHE=1 just cartuchos` y el sha256 de los 999
archivos de `rom/build/` (sin caché, `.o`, `sello.txt`, `conversor.log`, y
el `.dbg` sin `mtime`): con los binarios de este cambio, con los del `main`
de partida compilados igual (instalados en el `bin/` local desde `5dc54ff7`)
y sobre el merge con `main`, las tres corridas dan **todo igual**. Contra
la corrida con los binarios globales difieren sólo los dos `.dbg`, y
difieren igual con los binarios locales de `5dc54ff7`: es el global contra
el local, no este cambio. `just pruebas` y `just -f tools/justfile test` en
verde sobre el merge; `cargo test -p` de `cartridge` y `events`, también.
