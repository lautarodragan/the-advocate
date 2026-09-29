---
name: "El justfile de las herramientas"
description: "Las recetas que son de las herramientas se mudan a tools/justfile; el justfile de la raíz queda para ABL"
type: refactor
assignee: Espinillo
---

De taro, el 2026-09-29: el primer paso antes de mover `data/`, `parches/`,
`pruebas/` y el motor (ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).
Un `tools/justfile` con lo que es de las herramientas, y el de la raíz
acotado a ABL. Se acerca a tener dos repos sin mover todavía ninguna ruta.

Lo que va a `tools/justfile`, según lo charlado: `protocolo`,
`protocolo-pruebas`, `gunter-pruebas`, `ditto-pruebas`,
`ditto-vuelta-entera`, `voodoo-pruebas`, `lz2-pruebas`, `herramientas`,
`herramientas-locales`, `_instalar` y `cuales`. Lo que pone el `bin/` local
adelante en el `PATH` y la guarda se quedan en el de la raíz. También se
quedan `datos` y `ditto-volcado`, que vuelcan este juego.

De `pruebas/herramientas/`, sólo se mudan a `tools/` las que no necesitan
el juego ni una ROM, confirmado prueba por prueba.
