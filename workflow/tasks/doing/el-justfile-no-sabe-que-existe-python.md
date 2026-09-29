---
name: "El justfile no sabe que existe Python"
description: "El justfile llama sólo ejecutables del PATH; los .py que se ejecutan pasan a ser ejecutables de verdad, y una prueba con grep cuida que el lado de ABL no nombre tools/"
type: refactor
assignee: Espinillo
---

De taro, el 2026-09-28, como primer paso para separar las herramientas de
ABL (ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md` y
`docs/research/el-mapa-de-las-herramientas-de-python.md`):

> Se me ocurre un primer paso: que justfile no sepa que existe python. ABL
> no puede saber que existe el directorio de tools — solo sabe que existe
> una suite de herramientas disponible en el path. Los archivos de Python
> que son ejecutables se convierten en ejecutables de verdad, con hashbang y
> chmod +x.
>
> Luego podemos tener un test muy simple con grep: si algo en abl matchea el
> path de tools, falla el pipeline.

Medido antes de empezar: el `justfile` tiene 50 líneas que nombran
`python3` o `tools/` (`grep -c "python3\|tools/" justfile`), y 63 archivos de
`pruebas/` importan módulos de `tools/` directamente. Por eso la prueba del
grep arranca con una lista de excepciones para `pruebas/` que sólo puede
achicarse.
