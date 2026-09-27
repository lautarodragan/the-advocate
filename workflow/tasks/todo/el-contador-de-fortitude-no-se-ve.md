---
name: "El contador de Fortitude no se ve"
description: "El minijuego de Eisen (mapa 95) lleva la cuenta en la variable 48 y la muestra con una imagen que la ROM no dibuja"
type: bug
---

Del plan `el-mundo-y-lo-que-sigue.md` (pregunta 4). El minijuego del 95 compila
y se juega, pero sin ver cuánto aguanta Eisen: el contador de Fortitude es una
imagen que la ROM no dibuja. taro lo dejó como deuda el 2026-09-27.

Los caminos que estaban sobre la mesa: mostrar la variable 48 con los dígitos
del cronómetro, que ya están en la ROM; un mensaje cuando baja. Antes de elegir
hay que mirar si el minijuego se puede perder: si no, el contador es sólo
información.
