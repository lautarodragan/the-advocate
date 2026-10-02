---
name: "Un menú custom propio, no hecho de imágenes"
description: "Un agregado que RM2k no tiene: describir un menú custom como datos (texto, listas, una cara) en vez de imágenes de texto sobre blanco, para que pese mucho menos, se alinee bien y se vea mejor; probablemente en modo 5 con una fuente propia"
type: feature
---

De taro, el 2026-10-01, al hablar de la portable console de ABL
(`NewMenuActivated`, `ManageAuraMenu`, `CustomMenu*`, `DisplayNameMenu`):
"muchas de estas imágenes son texto sobre fondo blanco, y, a lo sumo, una
imagen de un personaje. Podríamos reducirlo inmensamente en tamaño y a la vez
mejorarlo en UX y estética —el menú custom con imágenes de ABL no está bien
alineado y estéticamente bastante feo—". Y "ahí sí usaría el modo 5 y armaría
una tipografía específica para eso".

Es un agregado del port, no algo de RM2k: el juego describe su menú con
imágenes y lógica de eventos, y esto lo reemplazaría por una descripción
propia. Serviría para otros juegos con menús hechos de imágenes, que son
muchos. Lo de la fuente y el modo 5 sale de
`testing/una-fuente-para-la-alta-resolucion.md` (Espinillo) y de la ROM de
prueba de Carancho; taro dijo que en la tele de tubo el texto estirado se ve
raro, así que la fuente tendría que pensarse para eso.

Primero va el sistema de imágenes tal como lo usa RM2k
(`doing/el-sistema-de-imagenes.md`): esto viene después, sobre eso.
