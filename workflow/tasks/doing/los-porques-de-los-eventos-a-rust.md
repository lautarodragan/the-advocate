---
name: "Los porqués de los eventos, junto al código en Rust"
description: "Los comentarios largos de cada comando que quedaron en tools/port/events.py pasan al lado de la línea que protegen, en tools/rm2k-snes/events/"
type: docs
assignee: Tordo
---

Lo dejó anotado Guazú al pasar el compilador de eventos a Rust
(`testing/rust-el-compilador-de-eventos.md`): los porqués de cada comando
—cuánto destrabó, cuándo entró, qué se midió, qué error protege— siguen en
`tools/port/events.py`, pero el código que protegen está ahora en
`tools/rm2k-snes/events/`. La regla de AGENTS.md es que un porqué que
protege una línea va como comentario en esa línea, así que se mudan. Es
sólo prosa: la ROM no puede cambiar.
