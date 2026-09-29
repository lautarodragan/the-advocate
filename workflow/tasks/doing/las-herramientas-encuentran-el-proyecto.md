---
name: "Las herramientas encuentran el proyecto"
description: "Las herramientas dejan de saber que ABL vive en rom/ y de leer ABL_*: buscan rm2k-snes.toml hacia arriba, sus rutas salen del archivo, y el ambiente llega por flags"
type: refactor
assignee: Timbó
---

Lo que queda para que `tools/` no sepa nada de dónde ni cómo está ABL, después
de `testing/el-archivo-de-proyecto.md` (Molle). Lo decidió Hornero, con la
autorización de taro del 2026-09-29 para decidir sin esperarlo:

- **Las herramientas encuentran el proyecto como cargo encuentra el suyo**:
  buscan `rm2k-snes.toml` hacia arriba desde el directorio actual, o lo
  reciben por `--proyecto <dir>`. `proyecto.abl()` desaparece.
- **Las rutas del proyecto** (`data/`, `parches/`, `build/`, lo que haga
  falta) **las declara el archivo**, relativas a él. El runtime no: es de
  las herramientas.
- **El ambiente llega por flags** (`--game-dir`, `--rtp-dir`,
  `--soundfont`…), como dejó escrito Molle en su tarea; `rom/justfile`
  traduce `$ABL_GAME_DIR` y las demás. Las herramientas no leen ninguna
  `ABL_*`.
