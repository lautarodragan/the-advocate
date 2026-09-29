---
name: "Un solo lugar que sabe dónde está cada cosa"
description: "El paso 2 del plan: comun/proyecto.py junta los once cálculos de la raíz y las rutas derivadas, sin cambiar ningún valor"
type: refactor
assignee: Tipa
---

Paso 2 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4). Va antes de la mudanza de `data/`, `parches/`, `pruebas/` y el motor
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`): con esto
hecho, mudar una carpeta es cambiar una línea.

Lo decidió Hornero, con la autorización de taro del 2026-09-29 para decidir
sin esperarlo: un módulo `tools/comun/proyecto.py` con una función por
lugar, que devuelve hoy exactamente lo mismo que los cálculos dispersos. El
motor ya se llama `runtime()` ahí, aunque siga en `rom/src/`, para que la
mudanza no tenga que renombrar llamadas.
