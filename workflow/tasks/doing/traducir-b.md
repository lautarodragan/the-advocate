---
name: "Traducir las herramientas al inglés, fase 1: el resto de port"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/port/, todo menos snes_convert.py"
type: refactor
assignee: Cina
---

De taro, el 2026-09-29: "traducir las herramientas a inglés". Es la regla de
AGENTS.md para los proyectos aparte, que ahora alcanza a todo `tools/`
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

**Fase 1**, repartida entre cuatro agentes por área: comentarios, docstrings,
mensajes de error, `help=` y prosa. **Los nombres de código no se tocan** —
módulos, funciones, variables, símbolos del runtime, flags—: eso es la fase
2, de a un área por vez, porque un nombre cambia en todos los que lo
importan. Los términos salen de `tools/GLOSSARY.md`.

Alcance de esta parte: tools/port/, todo menos snes_convert.py.

## Cómo se verifica

Cada grupo de archivos va en su commit, y se verifica con tres cosas:

* el AST de cada archivo contra `66152183`, sin docstrings: sólo pueden
  cambiar strings, y cada string que cambió se mira a mano —mensaje o
  dato—;
* `SIN_CACHE=1 just cartuchos` y el sha256 de todos los `.sfc`, `.msu` y
  `.pcm` de `rom/build/` contra los de antes de empezar;
* los `.inc` generados, con un diff que sólo puede mostrar comentarios.

## Hecho

* Los módulos chicos: `animacion`, `asignador`, `color`, `comprimir`,
  `constantes`, `experiencia`, `fin_del_juego`, `formato_snes`, `fuente`,
  `imagen`, `msu_datos`, `paleta`, `pantalla_completa`, `reglas`, `textos`,
  `tiles_bin`, `titulo`, `ventana`. `event_opcodes.py` es generado y ya
  estaba en inglés.
