---
name: "Maqueta: el menú en alta resolución"
description: "Antes de tocar la ROM, cómo se vería el menú de pausa en modo 5 (512 de ancho) con la fuente de RM2k escalada ×1,6, al lado de dos alternativas baratas, para que taro elija mirando"
type: research
assignee: Ñacurutú
---

De taro, el 2026-09-30. El menú original muestra, por actor, el **título**
(`title` en el LDB: "Agency Capt.", "Fugitive"…) y los **SP**, y el nuestro
no, porque a 256 de ancho no entran. Sumar filas estira cada entrada, puede
pedir scroll y queda feo.

La idea de taro: el modo 5 de la PPU da 512 de ancho. El menú original mide
320, y 320 × 1,6 = 512, así que entraría el menú de RM2k entero al 80 % del
ancho. Lo que no se sabe es cómo se ve la fuente escalada ×1,6: unas
columnas de cada letra salen dobles y otras simples. En modo 5 el texto va
en 4 bits, y las caras irían como sprites, que ya son de 15 colores.

Esto es sólo la maqueta: imágenes para mirar, sin cambiar la ROM.
