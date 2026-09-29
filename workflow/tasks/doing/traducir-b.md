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
