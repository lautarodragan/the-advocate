---
name: "Experimento: Uruya en 4bpp"
description: "Una ROM descartable que sólo muestra Uruya (Vampires Dawn, mapa 165) en modo 1, con sus dos capas a 4bpp, para ver cuánto se pierde de color a cambio de entrar en VRAM"
type: research
agents: [Calandria]
assignee: Calandria
---

Medido por Hornero el 2026-10-06 con `wally layers`: Uruya son 817 tiles
de fondo de 8x8 a 8bpp (60x60 celdas, 95 en la capa de arriba), y el reparto
más grande de VRAM da 544. A 4bpp entran unos 2000. Es descartable: lo
que vale es la ROM para mirar y lo medido, no el código.

taro, el 2026-10-06: "a modo 100% experimento descartable, podrías armarme
un rom que solo tenga ese mapa, en modo 4bpp".
