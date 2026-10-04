---
name: "La ventana de mensajes se queda arriba"
description: "Jugando, la ventana pasó a quedar siempre arriba —y el cronómetro abajo— con NPCs de Lashe City que en el original hablan abajo"
type: bug
assignee: Calancate
---

De taro, el 2026-10-04, con el build `2026-10-04-5b29ba9-f6a44973`: "en algún
momento pasó a quedarse permanentemente arriba, y el cronómetro, abajo.
Creo que debería haber vuelto a estar abajo en algún momento". El Bum al
lado de la casa de Talan, el worried worker, el oficial del hover tram,
varios NPCs del lado izquierdo de Lashe City, los Neon Vipers: todos arriba.

Es de `la-ventana-arriba-al-medio-y-sin-fondo.md` (Quirquincho). Un
candidato, sin confirmar: el común 15, `CustomMenuSideQuests`, termina con
`MessageOptions [0,0,0,0]` —arriba— y los otros menús de la consola con
`[0,2,0,0]`.
