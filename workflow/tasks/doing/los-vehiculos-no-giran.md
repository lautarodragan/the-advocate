---
name: "Los vehículos giran cuando no tienen que girar"
description: "El hover tram, las naves de la agencia y el auto de la carrera tienen charsets hechos para no rotar, y en la ROM miran hacia donde caminan"
type: bug
assignee: Coipo
---

De taro, el 2026-09-30, jugando en la SNES: "los vehículos, al moverse, se
ven rotos porque los charsets están editados a medias, diseñados para que
ciertos vehículos no puedan rotar. Creo que hay una opción de los eventos
que les fuerza cierta dirección, y, al estar activada, no miran hacia donde
caminan". Se ve en:

- el hover tram del inicio;
- las naves de la agencia, cuando empieza a sonar Lunar Pyramid;
- el auto de la carrera: "por momentos, puedo cambiarle el color al auto, o
  convertirlo en otro vehículo, apretando las teclas direccionales".

Pista de Hornero: `tools/runtime/oam.s` dice que para el héroe "no
`lock_facing` to look at: `step_route` ignores 26 and 27", es decir que las
órdenes de ruta que traban la dirección no se cumplen sobre el héroe.
