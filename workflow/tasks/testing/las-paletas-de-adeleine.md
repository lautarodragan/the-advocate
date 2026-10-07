---
name: "Las paletas de Adeleine"
description: "Adeleine fusiona colores globalmente, de a uno, hasta que su best-fit acomoda los tiles: en Uruya a 4bpp deja 19 colores donde agrupar tiles y elegir 15 por paleta deja 73. Que elija por paleta"
type: feature
agents: [Codex, Hornero]
assignee: taro
---

Medido por Calandria el 2026-10-06, en `testing/uruya-en-4bpp.md`: con las
8 paletas de 15 que decide `adeleine reduce`, Uruya (Vampires Dawn, mapa
165) queda con 19 colores distintos y el 33,5% de los píxeles cambiados;
con un agrupamiento de tiles y 15 colores por grupo, 73 colores y 17,7%.
Su script, `build2.py`, está en `/extras/scratch/calandria/uruya/`.

Rinde en todo lo que Adeleine reparte en paletas: sprites, las imágenes,
los mapas en modo 1, los panoramas, la pelea.

taro, el 2026-10-06: "vamos con las paletas de Adeleine", a Codex.

## En curso, el 2026-10-06 (Codex)

La base de ABL, armada con los binarios locales de `9283f47f`, conserva la
huella esperada `aaae70c2e48661836186411d77d407c14776ecdafb8234f0ec42a83525531243`.

La prueba de juguete ya se vio roja antes del cambio: tres tiles de tres
grises, en dos paletas de dos colores, quedan con dos colores por la fusión
global aunque una elección por grupo puede conservar cuatro. El contrato cambió:
`reduce` devuelve, además de las paletas, la paleta y el mapeo de cada tile.

## Hecho, el 2026-10-07

A Codex lo cortó dos veces el límite de uso, con el código commiteado
(27a28646) y la tanda de ABL en verde en su clon; Hornero cerró la tarea.

- Uruya a 4bpp: **64 colores** distintos, contra 19 del algoritmo anterior y
  73 del script de Calandria.
- ABL: cambian 319 goldens, todas de color en fondos, panoramas e imágenes;
  lado a lado en `/shared/capturas/2026-10-06-paletas-adeleine/`. Hornero miró
  las hojas y una muestra al tamaño real: ninguna se ve peor.
- No se midió el porcentaje de píxeles cambiados en ABL ni el modo 3, que el
  encargo pedía; la tarea queda sin esa tabla.

Al mergear: reinstalar `adeleine wally images screens battle convert patches`.
