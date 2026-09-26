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

## Hecho, 2026-09-26

Medido primero: con `Pelea.tocar` cambiado a llamar a `menu.tocar` —dos
cuadros apretado en vez de tantos como de aire—, las cinco pruebas que usan
`Pelea` (`test_batalla`, `test_tropa`, `test_victoria`,
`test_experiencia_dibujo`, `test_menu_hp_de_la_pelea_dibujo`: 45 casos)
siguieron en verde, y ninguna compara contra una golden. Así que esos dos se
unificaron; el de ticks no se puede, porque en una pantalla que congela el
reloj no termina nunca.

Quedaron dos, con el reloj en el nombre, y los dos en `Partida`:

* `Partida.tocar_ticks(*botones)`: el que era `Partida.tocar`.
* `Partida.tocar_cuadros(boton, aire=4)`: el que era `menu.tocar`.
  `Pelea.tocar_cuadros(boton="a", aire=3)` le pasa a éste.

Y dos locales que se quedan, con el nombre alineado: `Grabador.tocar_cuadros`
en `test_fundido_de_pelea.py` —el mismo toque, fotografiando cada cuadro— y
`_tocar_cuadros` en `test_pila.py` —sin `Partida`, un cuadro apretado—.
El `tocar=` de `Partida.correr` no se tocó: es una lista agendada, no un verbo.
