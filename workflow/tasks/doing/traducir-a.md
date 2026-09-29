---
name: "Traducir las herramientas al inglés, fase 1: snes_convert"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/port/snes_convert.py, entero"
type: refactor
assignee: Aromo
---

De taro, el 2026-09-29: "traducir las herramientas a inglés". Es la regla de
AGENTS.md para los proyectos aparte, que ahora alcanza a todo `tools/`
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

**Fase 1**, repartida entre cuatro agentes por área: comentarios, docstrings,
mensajes de error, `help=` y prosa. **Los nombres de código no se tocan** —
módulos, funciones, variables, símbolos del runtime, flags—: eso es la fase
2, de a un área por vez, porque un nombre cambia en todos los que lo
importan. Los términos salen de `tools/GLOSSARY.md`.

Alcance de esta parte: tools/port/snes_convert.py, entero.

## Cómo se hace

Por tramos del archivo, cada uno en su commit. Para cada tramo se compara el
AST del archivo viejo contra el nuevo, con los docstrings y los strings
sacados: tiene que dar igual, y los strings que cambian se listan y se miran
a mano uno por uno. Después `SIN_CACHE=1 just cartuchos` y el sha256 de todo
`rom/build/` menos el caché, los `.o` y el sello, contra la base tomada antes
de tocar nada.

## Avance

- Líneas 1–2580 (de la cabecera hasta la ventana de mensaje): hecho. Los
  `.sfc`, `.msu`, `.pcm`, `.inc` y `.dbg` salen iguales: en este tramo no hay
  comentarios que vayan al `.inc`.
