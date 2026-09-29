---
name: "Rust: la biblioteca del proyecto y el armado de cartuchos"
description: "El primer paso a Rust: tools/project/ (encontrar el proyecto, las perillas, el ambiente, la clave del caché) y tools/cartridge/ con rm2k-snes-assemble, rm2k-snes-space y rm2k-snes-cartridges, reemplazando a tools/assembly/ con las ROMs byte por byte iguales"
type: refactor
assignee: Carancho
---

De taro, el 2026-09-29: encarar las herramientas nuevas en Rust en el orden
de `docs/research/las-herramientas-hoy.md`. Éste es el primero: la
biblioteca común y `rm2k-snes-build` (que Hornero decidió partir en los tres
ejecutables que ya existen, con los mismos nombres, para que nadie que los
llama tenga que cambiar).

- `tools/project/`: crate de biblioteca, `rm2k-project`.
- `tools/cartridge/`: crate con los tres ejecutables. Reemplaza a
  `tools/assembly/{assemble,banks,space,cartridges}.py`; `entregar.py` es de
  ABL y queda.
