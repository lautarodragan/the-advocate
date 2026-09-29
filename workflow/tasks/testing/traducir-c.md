---
name: "Traducir las herramientas al inglés, fase 1: las capas de abajo y la prosa"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/audio, rpgmaker, render, comun, ensamblado, emulador, pruebas, justfile, README.md y los README de cada carpeta"
type: refactor
assignee: taro
---

De taro, el 2026-09-29: "traducir las herramientas a inglés". Es la regla de
AGENTS.md para los proyectos aparte, que ahora alcanza a todo `tools/`
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

**Fase 1**, repartida entre cuatro agentes por área: comentarios, docstrings,
mensajes de error, `help=` y prosa. **Los nombres de código no se tocan** —
módulos, funciones, variables, símbolos del runtime, flags—: eso es la fase
2, de a un área por vez, porque un nombre cambia en todos los que lo
importan. Los términos salen de `tools/GLOSSARY.md`.

Alcance de esta parte: tools/audio, rpgmaker, render, comun, ensamblado, emulador, pruebas, justfile, README.md y los README de cada carpeta.

## Avance

- Base: `SIN_CACHE=1 just cartuchos` sobre `66152183`, 47 `.sfc`/`.msu`/`.pcm`
  hasheados; los `.inc` guardados para diffear comentarios.
- `tools/README.md` y `tools/justfile`: traducidos.
- `tools/rpgmaker/README.md` y `tools/pruebas/README.md`: traducidos. El
  encabezado "Qué prueba cubre qué" es un dato que lee `test_indice.py`, así
  que cambia junto con él.
- Los `.py`, repartidos en cinco tandas por carpeta.
- Hechos los cinco grupos de `.py`, cada uno en su commit. `SIN_CACHE=1 just
  cartuchos`: los 47 `.sfc`/`.msu`/`.pcm` iguales a la base; de los `.inc`
  cambia sólo `musicdata.inc` (release y special), sólo en comentarios.
- `ensamblado/entregar.py` no se traduce: es `abl-entregar`, que según el
  justfile se queda con el juego y en castellano. Lo decide taro.
- Quedan en castellano por ser datos: la línea `; Temas:` de `musicdata.inc`
  y su "sin música" (los lee `techos.py` y `rom/pruebas/arnes/consola.py`),
  `b"mapa %dx%d"` (clave del caché), las claves de la receta del fork, de
  `collect_npcs`, de `espacio.medir`, de `techos.toml` y `musica.json`, los
  sufijos de los CharSets y `RESERVADO` del `.cfg`.
- Menciones del ambiente que ya estaban y sólo se tradujeron (fuera de la
  fase 1): `/extras/...` en `retro.py`, `ensamblar.py`, `msu.py` y
  `chipset_del_fork.py`.
- Mergeado `main` (`106484ea`, sólo un doc). Sobre el árbol mergeado:
  `just -f tools/justfile pruebas` 132 y 2 salteadas; `just pruebas` 874.

Para taro: mirar el diff por carpeta; lo que no verifica ninguna prueba es la
calidad del inglés. Y decidir si `entregar.py` entra en la traducción.
