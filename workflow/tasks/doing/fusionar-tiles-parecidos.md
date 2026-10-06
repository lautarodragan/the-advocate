---
name: "Fusionar tiles parecidos cuando el fondo no entra"
description: "Si el fondo de un mapa tiene más tiles distintos que los que entran en VRAM, se fusionan los más parecidos hasta que entre, con un aviso: un piso jugable algorítmico, sin intervenir a mano"
type: feature
agents: [Cardón]
assignee: Cardón
---

18 mapas de Vampires Dawn pasan el tope de unos 544 tiles de fondo (el
mayor, Uruya, 817; el mundo, 597): medido por Hornero el 2026-10-06 con
`wally layers` sobre los 440 mapas, en `/extras/scratch/hornero/vd-tiles/`.

taro, el 2026-10-06: "tal vez fusionar tiles sea un buen feature para tener,
en general. incluso si queda feo, nos permite tener un lower bound jugable
de forma algorítmica".
