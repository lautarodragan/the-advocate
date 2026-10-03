---
name: "La caché de ranuras de sprites"
description: "Cada evento pide una ranura de VRAM al entrar en pantalla y la suelta al salir, en vez de tener una fija por el mapa entero; con ayudas para achicar el pico, y la granja (127) de ABL como primer caso"
type: feature
assignee: Yaguareté
---

De taro, el 2026-10-03: "vamos con la 1", entre los caminos para la granja
de ABL (`workflow/tasks/testing/mundo-8-paradise.md` y
`mundo-7-camino-a-paradise.md`, opción D, en ABL). Es del motor: sirve para
cualquier mapa con mucha gente, de cualquier juego.

Lo medido (Puma, 2026-10-01) sobre el 127: 22 eventos que caminan y 18
poses quietas; en pantalla a la vez, 30 ranuras distintas sin margen y 36
con 2 celdas, contra 32 de "+sprite". La caché sola entra justa: hacen falta
ayudas que achiquen el pico (compartir quietos como en el 108, espejados en
una ranura, …).

Primero se mide sobre todos los mapas del juego —cuántos destraba la caché
sola y cuántos con cada ayuda—, y después se implementa.

Para después (taro): ver si vale hornear NPCs en el 127 —los de la escena
de bandidos que se queden quietos—, una vez que esto esté.
