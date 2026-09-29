---
name: "El workspace de Rust"
description: "Los nueve crates de tools/ en un workspace de Cargo: un Cargo.lock y un target/, sin cambiar lo que hace ningún binario"
type: refactor
assignee: Pirincho
---

De taro, el 2026-09-29: "dale, armá el workspace". Charlado antes: los
crates siguen siendo proyectos separados —`cargo install --path` instala
cada uno por su cuenta, y cada uno se publica solo—; el workspace sólo hace
que las dependencias compartidas se compilen una vez y que haya un solo
`Cargo.lock`.

Lo que Hornero ya decidió: los perfiles de compilación van arriba, porque
el workspace ignora los de cada crate. `ditto` y `protocol` optimizaban por
tamaño (`opt-level = "z"`, `panic = "abort"`): el `opt-level` se conserva
por paquete, y `panic = "abort"` se pierde, porque no se puede fijar por
paquete. Cambia el tamaño de esos dos binarios, no lo que hacen.

## Sumado el 2026-09-29, de taro

Dos cosas más, en la misma tarea:

1. **Los crates se agrupan en carpetas por capa**, adentro del mismo
   workspace y con `git mv`: `tools/snes/` —formato de SNES, sin saber de
   RPG Maker: `voodoo`, `lz2`, `gunter` y `protocol`, que es genérico pero
   genera constantes para el ensamblador de 65816—; `tools/rm2k/` —RPG
   Maker, sin saber de la SNES: `ditto` y `rm2k-render`—; y
   `tools/rm2k-snes/` —lo que une las dos: `project`, `cartridge`,
   `rm2k-snes-audio`, y los crates del conversor que vienen—. Los nombres
   de crates y binarios no cambian; el `Cargo.toml` del workspace queda en
   `tools/`. Los paquetes de Python de `tools/` no se mueven.
2. **Una prueba que haga cumplir la dirección de las capas**, leyendo
   `cargo metadata`: `snes/` y `rm2k/` no dependen de `rm2k-snes/`, y
   `snes/` y `rm2k/` no dependen uno del otro.

3. **`rm2k-render` deja de leer `rm2k-snes.toml`.** Va a `rm2k/`, pero
   `layers --map N` buscaba el archivo del proyecto hacia arriba y leía
   `[paths] data` para encontrar el volcado: saber de la capa de arriba
   copiando su formato en vez de depender de un crate, que la prueba de
   capas por `cargo metadata` no ve. Ahora recibe `--data <dir>`, el
   directorio del volcado de Ditto, y la prueba de capas mira también que
   nada de `snes/` ni de `rm2k/` nombre `rm2k-snes.toml`.

Commits: el workspace; la mudanza, sólo `git mv` y rutas; la prueba; lo de
`rm2k-render`; la prosa aparte.

## Lo hecho

### El workspace

- `tools/Cargo.toml`, virtual, con los nueve crates y `ditto/xtask`:
  Ditto tenía su propio workspace para el generador del esquema, y un
  workspace no puede anidar otro, así que `xtask` pasó a miembro del de
  arriba. `cargo xtask` sigue andando parado en `ditto/`, porque el alias
  está en `ditto/.cargo/config.toml` y cargo lo lee desde el directorio
  donde se lo corre.
- `resolver = "2"`: un manifiesto virtual no tiene edición de dónde
  sacarlo y caería en el 1; "2" es lo que cada miembro, en edición 2021,
  usaba solo.
- Perfiles arriba, `opt-level = "z"` por paquete para `ditto` y
  `protocol`; `panic = "abort"` se pierde. Medido: `ditto` pasa de 2,21 a
  3,01 MB y `protocol` de 0,77 a 1,07 MB.
- Un `Cargo.lock`: armado **juntando los nueve** —los paquetes del
  registro de todos, deduplicados— para que cargo parta de versiones que ya
  se usaban, y después, donde dos crates tenían versiones distintas, subido
  a la más nueva con `cargo update --precise`. Ninguna versión es nueva:
  todas estaban en algún lock. Las que se unificaron, con quién tenía la
  vieja:
  - `clap` y `clap_builder` 4.6.6 → 4.6.7, `clap_derive` 4.6.4 → 4.6.7,
    `clap_lex` 1.1.0 → 1.1.1: `protocol`.
  - `syn` 3.0.5 → 3.0.6 y `unicode-ident` 1.0.24 → 1.0.26: `ditto`,
    `gunter`, `protocol` y `voodoo`.
  - `cfg-if` 1.0.4 → 1.0.5 y `zlib-rs` 0.6.7 → 0.6.8: `voodoo`.
- **`cargo install --locked --path <crate>` usa el lock del workspace**:
  comprobado bajando `clap` a 4.6.6 en el lock del workspace e instalando
  `protocol`, que compiló `clap v4.6.6`. Y usa el `target/` del workspace.
- `CARGO_MANIFEST_DIR` sigue siendo el directorio del paquete: los `.dbg`
  que arman los binarios nuevos nombran los fuentes relativos a la raíz del
  worktree, igual que antes.
- Un solo `target/`, en `tools/target/`; se borraron los `.gitignore` de
  cada crate, que sólo decían `target/`.
- `tools/justfile`: las recetas de probar siguen paradas en cada crate
  (`cargo test` en un miembro prueba sólo ése), y hay una nueva,
  `rust-test`, que prueba el workspace entero en debug.

### Las capas

- La mudanza fue un commit de sólo `git mv` y las rutas que dejaban de
  valer: los miembros, la dependencia de `rm2k-snes-audio` en `gunter`,
  los `cd` de las recetas, las rutas de `protocol`, `test_protocol.py` y el
  `.idea/` de ditto. `_install` busca cada proyecto por su nombre en las
  carpetas de `rust_layers`, así que `install lz2` sigue siendo `install
  lz2`.
- `suite::tools()` de `project` contaba un directorio hacia arriba desde el
  crate y ahora cuenta dos. Es el único `CARGO_MANIFEST_DIR` que llega a
  `tools/`; los demás usos de `env!` son `CARGO_BIN_EXE_*` y
  `CARGO_TARGET_TMPDIR`, que no dependen de dónde esté el crate. Como una
  mudanza más lo rompería sin error de compilación, lleva una prueba: que
  desde ahí se llegue a `runtime/main.s`.
- `tools/tests/test_layers.py` lee `cargo metadata --no-deps`. Probado que
  falla con `rm2k-project = { workspace = true }` en `gunter` —heredada del
  workspace, para ver que `cargo metadata` le da la ruta igual— y `lz2`
  como dev-dependency de `ditto`; y el grep de `rm2k-snes.toml`, con el
  `source.rs` de `rm2k-render` de antes.
- `rm2k-render layers --map N` pide `--data <dir>`; nadie usaba `--map`
  —el conversor usa `--request`, `render/render_map.py`—. Con el `toml`
  del crate salen del lock `toml` 0.9, `toml_datetime` 0.7 y `winnow` 0.7.

### Verificación

- `cargo build --release` y `cargo test` del workspace: 251 pruebas, las
  mismas que daban los nueve por separado en `main`, más la de
  `suite::tools()`, 252; 3 ignoradas en los dos casos.
- `NO_CACHE=1 just cartuchos` con los nueve instalados en el `bin/` local:
  los 999 archivos de `rom/build/` —`.sfc`, `.msu`, `.pcm`, `.inc`, `.sym`
  y demás— iguales a los que salen acá con los binarios de `main`. Los dos
  `.dbg` difieren, y sólo en dos cosas medidas: los binarios de `main`
  estaban instalados desde otro árbol y nombran los `.inc` con ruta
  absoluta, y los comentarios que la prosa cambió en `tools/runtime/*.s`
  cambian el tamaño que el `.dbg` anota de cada fuente.
- `just -f tools/justfile test`, `rust-test` y `protocol --check`.

### Tiempos

Compilar e instalar en limpio los ocho crates con binario, con el loop de
`_install`, en esta máquina y con el registro ya bajado:

- antes, nueve proyectos con su `target/` cada uno: 188 s;
- después, el workspace: 172 s.

Poco, porque lo que cuesta es el `lto` con una sola unidad de código, que
se hace por binario igual; lo que se ahorra es recompilar las
dependencias: se compilan 80 crates en vez de 206. Y no todas se
comparten, porque `cargo install --path` compila un paquete por vez y las
features se unifican por paquete: `clap` con y sin `derive`, `toml` y
`serde_json` con y sin `preserve_order`. Recompilar después de tocar un
crate es lo que más baja: las dependencias ya están en `tools/target/`.
