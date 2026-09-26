---
name: "Compresión"
description: "Comprimir lo que viaja en la ROM: medido, un 75% menos"
type: feature
---

Lo que se puede esperar de comprimir, medido: la parte usada de
`abl` —3,12 MB cuando se midió; hoy es menos, desde que la escena de la pelea
guarda cada fondo una vez— deflatea a **791 KB, un 75% menos**. El grueso del
cartucho son gráficos, que es lo compresible, y descomprimir al cargar un
mapa es la técnica de la consola. 

Ojo con medirlo mal: el `.sfc` entero da
97% porque el millón de ceros de relleno comprime a nada, y el `mapdata.inc`
da 89% porque es **texto** —números decimales con comas—, no los bytes que
viajan en la ROM.

Lo que el mapa ya ahorra sin comprimir, para no rehacerlo: no se guarda el
tilemap sino la **celda de 16×16 de RM2k**, con sus cuatro celdas de fondo,
sus cuatro de la capa de encima y su pasabilidad juntas —512 bloques
distintos en todo el juego—. En el mapa 52 eso es 40.000 B contra 160.000, y
**borró la tabla de colisión entera**. Medido aparte: **el 85,3% de la capa
de encima es el tile vacío**, así que si hiciera falta más, el primer lugar
donde mirar es un RLE sobre la grilla de bloques, no los ceros de la capa.

Comprimir mapas tiene un desafío extra, porque los stremeamos en vivo del
cartucho, y cambiarles el formato afectaría el acceso aleatorio.

**Medido por clase y algoritmo, con el costo de descomprimir cada cosa y el
orden en que conviene hacerlo**: `tasks/testing/la-compresion-de-mapas-y-graficos.md`,
del 2026-09-26. Las animaciones de batalla ya se guardan sin sus tiles vacíos,
los tiles y las grillas de los mapas van en LZ2 —la grilla se descomprime
entera a la WRAM, así que el acceso aleatorio siguió igual— y las poses
iguales se guardan una vez.
