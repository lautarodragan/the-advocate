---
name: "La partida lleva su versión"
description: "Que una partida de otro build se rechace limpia en vez de cargar corrupta"
type: bug
---

Desde que `release` y `test-main` son un solo cartucho (2026-09-25), la
partida guardada cambia de tamaño cada vez que un caso nombra una variable
nueva o trae una tropa nueva: los casos viajan en la ROM que se juega. Medido
al juntar: una partida del `release` de antes, cargada en el unido, **no
carga** si detrás quedó lo que deja snes9x en la SRAM, y **carga corrupta**
(inventario, HP, SP, equipo, gráficos de actor y habilidades corridos) si
detrás hay ceros, porque la suma de control igual cuadra.

Que la cabecera de la partida lleve su tamaño o una versión derivada del
formato (`partida_tabla`), y que una que no coincide se trate como "no hay
partida". Ver `workflow/tasks/testing/juntar-release-y-test-main.md`.

No urge: taro prueba siempre desde cero y no comparte partidas entre builds.
Importa el día que un `.srm` viaje para reproducir un bug, o para quien juegue
builds seguidos.
