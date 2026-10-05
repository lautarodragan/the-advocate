---
name: "La ventana en el banco de tiles"
description: "Un System con el fondo en degradé estirado pide un tile por tono: la ventana de mensajes pasa de 256 tiles y la elección de actor de su rango de VRAM"
type: feature
agents: [Tijereta]
---

Lo que quedó detrás de `la-ventana-con-mas-colores` (Tijereta, 2026-10-05).
Con el System original y los colores ya reducidos por Adeleine, la ventana
de mensajes de The Frozen World pide 266 tiles de 256 y la de The Book of
Three 267; la elección de actor de Dooms 2 se pasa de `$4800`.

Fusionar más colores hasta que entren (`adeleine::merge_until` con los tiles
como condición) se probó y no sirve: Frozen queda en 4 colores y Book of
Three en 2. Lo que hace falta es del lado de los tiles —agrupar los
parecidos, como `adeleine::group_tiles` con los panoramas, o un fondo
repetido en vez de estirado—, y es de criterio: taro tiene que verlo.
