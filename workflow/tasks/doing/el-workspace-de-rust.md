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
