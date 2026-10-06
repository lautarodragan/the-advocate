---
name: "Cuatro atajos para los otros juegos"
description: "La condición por dirección, las órdenes de ruta que faltan, PlayerVisibility y los Comment en las páginas de las tropas: lo barato que más páginas destraba en los siete juegos"
type: feature
agents: [Chajá]
assignee: Chajá
---

Medido por Hornero el 2026-10-06 con `rm2k-snes-events culprits --every-map`
sobre los siete juegos, después del merge de los códigos de color. Las
páginas que **sólo** ese comando deja afuera:

* `ConditionalBranch` tipo 6, por la dirección de un personaje: Sunset 111,
  Vampires Dawn 37, El Dorado 23, Desert 21. Ya en
  `todo/los-comandos-sueltos-de-los-mapas.md`, para ABL (31 páginas).
* `MoveEvent` con órdenes que la ROM no entiende: el paso al azar (8) en
  Desert (39) y Vampires Dawn (16), alejarse del héroe (10) en Vampires Dawn
  (48) y El Dorado (9), y rutas de Sunset con 36/37 (unas 40; falta ver qué
  orden es la que traba). `wishlist/ruta-los-movimientos-que-faltan.md` dice
  que no rendían: en ABL era cierto, en estos juegos no.
* `PlayerVisibility`: El Dorado 170.
* `Comment` en las páginas de las tropas: The Book of Three 153. En los mapas
  ya se ignora.

taro, el 2026-10-06: "Dale!", con Sonnet.
