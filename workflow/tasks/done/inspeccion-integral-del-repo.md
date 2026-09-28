---
name: "Inspección integral del repo"
description: "Evaluar arquitectura, calidad, pruebas, documentación, riesgos y mantenibilidad del proyecto"
type: docs
assignee: Sol
---

Pedido del 2026-09-28: hacer una inspección y evaluación completa del repo.

La evaluación se apoya en las fuentes del propio árbol, los comandos del
`justfile`, el estado de las tareas y comprobaciones ejecutadas sobre el código.
El resultado quedará en `docs/research/`, con hallazgos verificables, riesgos y
prioridades concretas, sin fijar métricas de estado que envejezcan: cada una se
expresa mediante el comando que la reproduce.

Terminada el 2026-09-28. El resultado está en
`docs/research/2026-09-28-inspeccion-integral.md`: el repo tiene una arquitectura
y una estrategia de pruebas fuertes; las prioridades son hacer reproducible el
ambiente, bajar el radio de impacto del conversor y aclarar licencia y
procedencia. La tanda de ROM no pudo correrse: en este ambiente faltaban `just`,
Pillow, cc65 y los cores de libretro; sí pasaron la sintaxis de Python, las
pruebas de los cinco proyectos Rust y `git diff --check`. `cargo fmt --check`
marca diferencias en los cinco proyectos con el formateador de este ambiente;
no se mezcló ese cambio mecánico con el estudio.
