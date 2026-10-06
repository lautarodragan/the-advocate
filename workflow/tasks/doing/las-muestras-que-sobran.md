---
name: "Las muestras que sobran no suenan"
description: "Cuando un cartucho pide más de 255 muestras (SRCN es un byte), las que sobran se dejan afuera con un aviso, en vez de cortar el armado"
type: feature
agents: [Mulita]
assignee: Mulita
---

De taro, el 2026-10-06: "en vez de lograr que entren las muestras, estaría
bueno no necesitar excluir a esos mapas, y simplemente droppear las muestras
> 255 y ya. Que el juego no falle — simplemente, que no emita sonido, donde
no puede." Dooms 2 hoy arma sólo excluyendo los mapas 40 a 93.
