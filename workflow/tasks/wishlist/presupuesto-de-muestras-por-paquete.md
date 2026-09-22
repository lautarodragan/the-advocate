---
name: "Muestras por paquete"
description: "Repartir la ARAM por paquete de mapa y no por banco"
---

# Qué

Que el presupuesto de ARAM se reparta **por paquete y no por banco**: darle a
cada programa lo que su peor paquete puede pagar, en vez de una parte del banco
entero.

Hoy los 40 KB de `ARAM_BUDGET` se reparten entre **todos** los programas del
cartucho, así que sumar temas le baja la tasa a los que ya sonaban bien: con
diecinueve temas en vez de once, la mediana pasa de 12,5 a 8,4 kHz. Y los temas
que no alcanzan a aportar programas suenan incompletos —en `abl` son nueve, con
entre el 12% y el 72% de sus notas.

# Blockers

* **El tiempo de transferencia.** Subir un banco de 32 KB por el protocolo del
  IPL es del orden de medio segundo, o sea unos treinta cuadros de juego
  frenado. Hoy se paga en cada cambio de mapa, adentro del fundido; en un
  `PlayBGM` a mitad de una escena se vería.
* **Los efectos de sonido comparten la ARAM** y tienen que sobrevivir al
  cambio de paquete.

No es un blocker, aunque estuvo escrito como tal: **el mecanismo ya existe**.
`paquete_cargar` manda el SPC700 de vuelta al IPL (`APU_CMD_IPL`) y sube el
paquete de audio del mapa.

# Decisiones a tomar

* **Cuál es la unidad del paquete**: el mapa, como hoy, o el tema.
* **Dónde se paga el freno**, y si hay `PlayBGM` fuera de un fundido que no lo
  tolere.
* **Qué pasa con un tema que suena en varios paquetes**: se duplica su muestra
  o se comparte un piso común.
