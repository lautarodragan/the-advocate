---
name: "Traducir las herramientas, fase 2: el audio y el ensamblado"
description: "Los nombres de código de tools/audio y tools/ensamblado al inglés, y las recetas de tools/justfile"
type: refactor
assignee: Pindó
---

Fase 2 de la traducción de `tools/` al inglés, segunda área: `tools/audio/`,
`tools/ensamblado/` (que pasa a llamarse `tools/build/` o parecido) y las
recetas de `tools/justfile`, con todos sus usos. Van juntas porque
`cartuchos.py` importa del audio.

`ensamblado/entregar.py` (`abl-entregar`) es de ABL y queda en castellano.

Hace falta además una forma de instalar sólo los scripts de Python en el
PATH, sin compilar ni reinstalar Rust: hoy `herramientas` sin argumentos
reinstala los cinco proyectos, y cada renombre de un script pide volver a
enlazar.
