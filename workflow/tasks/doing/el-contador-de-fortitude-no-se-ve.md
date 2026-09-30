---
name: "El contador de Fortitude no se ve"
description: "El minijuego de Eisen (mapa 95) lleva la cuenta en la variable 48 y la muestra con una imagen que la ROM no dibuja"
type: bug
assignee: Chimango
---

Del plan `el-mundo-y-lo-que-sigue.md` (pregunta 4). El minijuego del 95 compila
y se juega, pero sin ver cuánto aguanta Eisen: el contador de Fortitude es una
imagen que la ROM no dibuja. taro lo dejó como deuda el 2026-09-27.

Los caminos que estaban sobre la mesa: mostrar la variable 48 con los dígitos
del cronómetro, que ya están en la ROM; un mensaje cuando baja. Antes de elegir
hay que mirar si el minijuego se puede perder: si no, el contador es sólo
información.

**Se puede perder**, mirado en el hito 4 (`testing/mundo-4-el-capitulo.md`):
cada salto y cada escalera del 95 restan 5 a la variable 48, que arranca en
99, y con la variable en cero la paralela 56 dice "So... tired... can't go
on...", devuelve a Eisen a la entrada, apaga las tres palancas y la repone en
99. La ruta de
`test_recorrido_capitulo_golden.py`, que va derecho a las tres palancas y a la
escotilla, termina con 4: sin ver el contador, cualquier rodeo obliga a
empezar de nuevo sin que el jugador lo vea venir. Así que el contador no es
sólo información.

## Tomada el 2026-09-30

Decidido por Hornero, con la autorización de taro para decidir sin
esperarlo: el camino es **mostrar la variable 48 con los dígitos del
cronómetro**, que ya están en la ROM, en el lugar y en el momento en que el
original muestra su imagen —medirlo con el RPG_RT en Wine—. Un mensaje
cuando baja no avisa antes de perder, que es lo que importa. Cambia lo que
se ve: las goldens que se muevan esperan el visto bueno de taro.
