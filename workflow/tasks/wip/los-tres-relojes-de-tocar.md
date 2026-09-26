---
name: "Los tres relojes de tocar"
description: "Partida.tocar cuenta en ticks, menu.tocar y Pelea.tocar en cuadros: tres verbos iguales con relojes distintos"
type: refactor
---

En el arnés de `pruebas/` hay tres `tocar`: `Partida.tocar` en ticks, y
`menu.tocar` y `Pelea.tocar` en cuadros, con distinto aire entre toques. El
mismo nombre para tres relojes confunde a quien escribe una prueba nueva.
Quedó sin unificar en `ordenar-pruebas` (2026-09-25) porque unificarlos
**cambia cuándo cae cada toque**, y eso puede cambiar lo que ven las pruebas.
El docstring de `menu.tocar` explica los tres.

Lo barato es renombrar para que el nombre diga el reloj; lo caro, unificar y
volver a medir cada prueba que los usa. Medir primero cuántas pruebas dependen
del aire exacto.
