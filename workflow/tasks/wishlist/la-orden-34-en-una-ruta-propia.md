---
name: "La orden 34 en la ruta propia de una página"
description: "change_graphic adentro de la ruta propia de una página, que hoy rechaza el compilador"
type: feature
---

# Qué

**`change_graphic` —la orden 34— en la ruta propia de una página.** El
compilador de eventos la rechaza (`route::own`): una ruta propia es una
lista de códigos sin lugar para el operando. Ninguna de las rutas propias de
ABL la usa.

Hasta el 2026-10-05 esto era "un evento que camina y cambia de gráfico con
la página", y ganaba caminar: la fila se quedaba con el gráfico de su
primera página. Eso ya está —cada página le da a la fila su banco de poses y
su paleta, ver `walker_graphic` en `tools/runtime/event_pages.s`—, y queda
esto, que era lo que arrastraba.

# Status

Anotado, sin empezar.

# Por qué

La orden 34 adentro de una ruta *forzada* sí se hace —sobre eventos y sobre
el héroe—: ver "Cambiar el gráfico a mitad de una ruta (la orden 34)" en
`docs/port/events.md` y `decisiones/la-orden-34-sobre-el-heroe.md`.
