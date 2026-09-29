---
name: "Desenredar el grafo de tools/"
description: "El paso 1 del plan del research: romper los ciclos y las violaciones de capa de tools/ moviendo funciones, sin cambiar lógica y con las ROMs byte por byte iguales"
type: refactor
assignee: Lapacho
---

Paso 1 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4), aprobado por taro el 2026-09-28. taro autorizó a Hornero a avanzar con
los pasos mecánicos sin esperar su feedback el 2026-09-29.

Entra: los ítems 1.1, 1.2, 1.3, 1.5 y 1.6 del research, y el 1.7 (partir
`titulo.py`) si todo lo anterior quedó mergeado y en verde.

No entra: el 1.4 (`cartuchos` deja de importar `port/` y `audio/`), porque
qué hacer con `cartuchos.py` es una pregunta abierta de taro (ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`).
