---
name: "El audio después de Lashe City"
description: "Recuperar la calidad que los paquetes de los mapas nuevos de Lashe City le bajan a los instrumentos sin MSU-1"
type: bug
---

El hito 1 de Lashe City (2026-09-27) sumó paquetes de audio nuevos (el 38 y
el 47 con `vswar` y `golden_axe-turtlevillage2`; el `38+cd4`, con tres temas
juntos y 1267 B libres), y sin MSU-1 **bajan 47 pares (tema, instrumento)** y
suben 26; la mediana pasa de 18,9 a 16,5 kHz. `vswar` es el más afectado
(polysynth 21,1 → 12,6, platillos y toms 22 → 14,1); `escape_newyork` vuelve a
perder el polysynth (21,1 → 12,6) que el directorio le había devuelto. Parte es
el paquete de tres temas; parte son copias que la segunda tanda de
`snes_music.copias` dejó de hacer (el banco pasa de 221 a 212 muestras).

Con MSU-1 no se oye (todos los temas tienen pista). Se encara **cuando
terminen los mapas de Lashe City** (cada hito suma paquetes y lo vuelve a
mover), con el mismo método que `testing/el-directorio-de-los-efectos.md`:
medir par por par con `Banco` contra el `main` de antes de los mapas nuevos,
y buscar que ningún instrumento de los temas que ya estaban quede peor.

**Del hito 2 (2026-09-27):** el conversor no sabe que `Kfmus5` sigue sonando del 41 al 45 (`temas_heredados` corta en el 41), así que esos paquetes no le reservan lugar. No se escuchó sin MSU-1: mirarlo en la misma pasada.
