---
name: "Herramientas locales por worktree"
description: "Un bin/ propio de cada worktree, adelante en el PATH de just, en lugar de ejecutable.py; Rust se compila sólo si el agente toca ese proyecto"
type: refactor
assignee: Espinillo
---

De taro, el 2026-09-29, después del paso 1 (`testing/el-justfile-no-sabe-que-existe-python.md`):
el problema es el que `npm link` intenta resolver, con N sub-agentes en
paralelo que modifican las herramientas seguido. Lo acordado:

- cada worktree tiene un `bin/` propio, ignorado por git, que el `justfile`
  pone adelante en el `PATH` si existe: lo que no está ahí sale del global;
- Python se linkea entero (los ocho ejecutables), porque no cuesta nada y
  cada script resuelve sus módulos desde su checkout real;
- Rust se instala ahí **sólo para el proyecto que el agente modifica**. De
  taro: "es importante que ningún subagente corra una compilación de Rust
  innecesaria. Son costosas";
- `tools/comun/ejecutable.py` se va: resolvía lo mismo de forma implícita;
- al mergear, el que mergea vuelve a instalar en el global sólo lo de Rust
  que la rama tocó.
