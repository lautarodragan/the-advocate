---
name: "Las paletas de Adeleine"
description: "Adeleine fusiona colores globalmente, de a uno, hasta que su best-fit acomoda los tiles: en Uruya a 4bpp deja 19 colores donde agrupar tiles y elegir 15 por paleta deja 73. Que elija por paleta"
type: feature
agents: [Codex]
assignee: Codex
---

Medido por Calandria el 2026-10-06, en `testing/uruya-en-4bpp.md`: con las
8 paletas de 15 que decide `adeleine reduce`, Uruya (Vampires Dawn, mapa
165) queda con 19 colores distintos y el 33,5% de los píxeles cambiados;
con un agrupamiento de tiles y 15 colores por grupo, 73 colores y 17,7%.
Su script, `build2.py`, está en `/extras/scratch/calandria/uruya/`.

Rinde en todo lo que Adeleine reparte en paletas: sprites, las imágenes,
los mapas en modo 1, los panoramas, la pelea.

taro, el 2026-10-06: "vamos con las paletas de Adeleine", a Codex.
