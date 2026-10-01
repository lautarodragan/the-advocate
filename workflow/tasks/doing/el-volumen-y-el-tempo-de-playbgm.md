---
name: "El volumen y el tempo de PlayBGM"
description: "La ROM ignora el volumen y el tempo que pide un PlayBGM: 69 de los 168 del juego piden otro volumen y 13 otro tempo"
type: feature
assignee: Chingolo
---

De taro, el 2026-09-30, como siguiente tarea después de
`testing/la-musica-que-ya-suena-sigue.md` (Yacaré), que lo dejó medido: de
los 168 `PlayBGM` del juego, 69 piden un volumen distinto del de por omisión
y 13 un tempo distinto, y la ROM no usa ninguno de los dos. Además, en
RM2k, un `PlayBGM` del tema que ya suena con otro volumen o tempo los ajusta
sin reiniciar (`Game_System::BgmPlay`), y eso Yacaré ya lo dejó preparado.
