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

Commits: el workspace; la mudanza, sólo `git mv` y rutas; la prueba; la
prosa aparte.

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
