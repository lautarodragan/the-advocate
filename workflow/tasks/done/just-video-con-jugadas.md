---
name: "just video con jugadas"
description: "just video está roto con jugadas desde 991bf935: la fábrica de recorrido de video.py no acepta caso, y sin el mapa de debug talan se traba en el 900"
type: bug
assignee: taro
---

Lo encontró Irupé el 2026-09-29 (`testing/las-pruebas-sin-agujeros-callados.md`):
desde `991bf935` (2026-09-27), `just video … apertura` da `TypeError`
porque la fábrica de `recorrido` de `rom/pruebas/arnes/video.py` no acepta
`caso`, y `talan` se traba en el mapa 900 porque no elige la página sin el
mapa de debug. `quieto:120` graba bien. taro usa `just video` para pedir
videos de un build.

Se arregla la regresión. Sacar `video.py` de las pruebas —que las jugadas
sean funciones de un módulo de escenarios que llaman las pruebas y el
video— es otra tarea, más grande.

## Qué estaba roto

Las dos cosas son la misma: `video.py` armaba la `Partida` a mano, con una
fábrica que copiaba la del conftest de antes del mapa de debug.

* La firma era `(_nombre, switch=())`. La apertura pide
  `recorrido("apertura", caso=ENTRADA_AL_MAPA_DE_DEBUG)` desde `991bf935`:
  `TypeError`.
* Elegía siempre la página 0. Desde `991bf935`, en `release` la 0 es la
  entrada al mapa de debug, y el conftest pide `LA_PARTIDA_DE_VERDAD` por su
  número —lo hace `tanda.partida(None)`—. `talan` prendía el switch del año
  antes y esperaba el mapa 7 parado en el 900. `quieto:N` "grababa bien"
  porque no espera nada, pero grababa el mapa de debug y no la apertura con
  la lluvia que dice su ayuda.

## Cómo se arregló

`video.fabrica(cartucho, msu)` es la fábrica, a nivel de módulo, con la firma
del fixture y la partida de `tanda.partida(caso, en=cartucho, …)`: la página
la elige el mismo código que en las pruebas. `tanda.partida` pasa `msu` a la
`Partida`. `video.py` recibe el nombre del cartucho y no su directorio
—`tanda.cartucho` sabe dónde está y se niega si está viejo—, y `just video`
depende de `build`, como `entregar`, así que un checkout cambiado se arma
antes de grabar.

La red es `rom/pruebas/abl/test_video.py`: misma firma que el fixture, y que
las dos fábricas arranquen en la misma página, mapa y celda para cada forma
de pedir que usan las jugadas (nada, switches, caso). No graba ni juega.
Con la fábrica vieja pegada adentro de `fabrica`, las cuatro dan rojo: la
firma, `caso` con `TypeError`, y las otras dos por página 0 contra 111
—el mapa y la celda coinciden en el tick 0, así que mirar sólo el mapa no
lo habría visto—.

## Cómo sería sacar `video.py` de las pruebas

Lo que queda feo es que un script del arnés importe un `test_*` y dependa de
un fixture de pytest reimplementado. Lo otro: un módulo `pruebas/arnes/`
de escenarios —`escenarios.apertura(r)`, `escenarios.talan(r)`— que reciben
un `Recorrido` ya armado, con las fotos y los `assert` como ganchos que la
prueba pasa y el video no; la prueba sería "armar el recorrido con el
fixture y llamar al escenario", y el video "armar con `fabrica` y llamar al
mismo". Con eso `-O` deja de hacer falta —el video no tendría los `assert`
de velocidad—, `IMPORTAN_PRUEBAS` de `test_indice.py` queda vacío, y
`just video` podría jugar también los tramos de `tramo_*.py` y los otros
`test_recorrido_*`, que hoy no alcanza porque sólo busca en
`test_recorrido_golden.py`.

Y de paso, que no es de esta tarea: un `video.py` que se corta deja su
`video.mkv` crudo en el temporal —unos 200 MB por minuto—, porque los
`os.remove` del final no están en el `finally`.
