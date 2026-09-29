---
name: "La mudanza: el runtime a tools/, ABL adentro de rom/"
description: "rom/src pasa a tools/runtime; data/, parches/, pruebas/, pytest.ini y el justfile de ABL pasan adentro de rom/, con las ROMs byte por byte iguales"
type: refactor
assignee: Algarrobo
---

Decidido por taro el 2026-09-29 (ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): se distingue
el runtime genérico del proyecto A Blurred Line. La raíz queda con `rom/`,
`tools/`, `docs/` y `workflow/` (más los archivos sueltos de siempre:
`AGENTS.md`, `CLAUDE.md`, `README.md`, `DITTO.md`, `.gitignore`…).

Va después del paso 2 del plan (`comun/proyecto.py`, Tipa, `e257bca3`), así
que mover cada carpeta es cambiar una línea ahí. Hornero decide los detalles
con la autorización de taro para decidir sin esperarlo.

- `rom/src/` → `tools/runtime/`
- `data/` → `rom/data/`, `parches/` → `rom/parches/`, `pruebas/` →
  `rom/pruebas/`, `pytest.ini` → `rom/pytest.ini`
- el `justfile` de la raíz → `rom/justfile`
- `rom/build/` se queda donde está.
