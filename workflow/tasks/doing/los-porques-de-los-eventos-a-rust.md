---
name: "Los porqués de los eventos, junto al código en Rust"
description: "Los comentarios largos de cada comando que quedaron en tools/port/events.py pasan al lado de la línea que protegen, en tools/rm2k-snes/events/"
type: docs
assignee: Churrinche
---

Lo dejó anotado Guazú al pasar el compilador de eventos a Rust
(`testing/rust-el-compilador-de-eventos.md`): los porqués de cada comando
—cuánto destrabó, cuándo entró, qué se midió, qué error protege— siguen en
`tools/port/events.py`, pero el código que protegen está ahora en
`tools/rm2k-snes/events/`. La regla de AGENTS.md es que un porqué que
protege una línea va como comentario en esa línea, así que se mudan. Es
sólo prosa: la ROM no puede cambiar.

## Retomada el 2026-09-29

Tordo arrancó y se cortó: un clasificador de seguridad interrumpió su
respuesta mientras escribía los comentarios de `branch_bytes` en
`compile.rs` (el bloque de las condiciones: ítems, preguntas sobre actores,
habilidades, equipo), sin commitear nada. Lo decidido con taro:

- se sigue con **todo lo demás**, incluidos los ~1.027 renglones de porqués
  que el borrado de Guazú (`1487129f`) se llevó junto con el compilador de
  Python: están en `git show 1487129f^:tools/port/events.py`;
- **el bloque de `branch_bytes` no se escribe**: queda con los comentarios
  cortos de Guazú y un puntero a ese commit;
- si el clasificador vuelve a cortar, el agente no busca la vuelta: avisa, y
  Hornero —con aviso a taro— aplica a mano el comentario en el worktree.

Lo que dejó Tordo, sin commitear, está en su worktree
(`agent-a3eccaf0086f4b17e`): comentarios ya mudados a constantes y
bloques de `compile.rs`. Su mapeo de qué se queda en Python, qué va a los
dos lados y qué va sólo a Rust está en su informe, copiado abajo por
Hornero.
