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
- Líneas 2581–4042 (de `convert_ventana` a `bloque`): hecho. `.sfc`, `.msu`
  y `.pcm` iguales; cambian los dos `mapdata.inc` —sólo en comentarios— y
  los `.dbg` —sólo en números de línea y tamaños—.
- **Un comentario del `.inc` queda en castellano porque es dato**: el
  `; --- N: mapa M 'nombre' ---` de `mapa_tabla`, que `mapas_de` en
  `rom/pruebas/arnes/consola.py` lee con una regex que espera "mapa". Lo
  dice un comentario al lado.
- Líneas 4043–5419 (de `tabla_de_paginas` a la mitad de `emit`, con la
  cabecera del `.inc`): hecho. `.sfc`, `.msu` y `.pcm` iguales. Los
  `mapdata.inc` sin comentarios dan igual salvo el texto del `.assert` de
  `TITULO_MENU_CGRAM`, que es un mensaje del ensamblador. Los `.dbg` cambian
  de ids además de líneas —ld65 numera las `line` en orden de línea—, así
  que se comparan resolviendo ids: iguales.
- Líneas 5420–6768 (el resto de `emit`: tienda, fin del juego, textos,
  ítems, equipo, habilidades, tropas, encuentros, batalla): hecho, con las
  mismas comprobaciones.
- Términos: se alinean con los que eligió Coronillo
  (`scratchpad/glosario-coronillo.md`): "hornear" es *bake*, "aire"
  *headroom*, "cuadro de texto" *text box*, "cobrar" una regla *enforce*.
  "La tanda lo cobró" quedó *the suite caught it*.
