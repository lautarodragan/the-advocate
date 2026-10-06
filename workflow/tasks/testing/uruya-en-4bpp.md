---
name: "Experimento: Uruya en 4bpp"
description: "Una ROM descartable que sólo muestra Uruya (Vampires Dawn, mapa 165) en modo 1, con sus dos capas a 4bpp, para ver cuánto se pierde de color a cambio de entrar en VRAM"
type: research
agents: [Calandria]
assignee: taro
---

Medido por Hornero el 2026-10-06 con `wally layers`: Uruya son 817 tiles
de fondo de 8x8 a 8bpp (60x60 celdas, 95 en la capa de arriba), y el reparto
más grande de VRAM da 544. A 4bpp entran unos 2000. Es descartable: lo
que vale es la ROM para mirar y lo medido, no el código.

taro, el 2026-10-06: "a modo 100% experimento descartable, podrías armarme
un rom que solo tenga ese mapa, en modo 4bpp".

## Hecho, el 2026-10-06 (Calandria)

Dos ROMs en `/shared/builds/otros-juegos/`, para mirar en un emulador, y
capturas lado a lado en `/shared/capturas/2026-10-06-uruya-4bpp/`: cada hoja
trae el original de RM2k, el 8bpp de wally, y las dos ROMs. El código del
experimento (conversión, `uruya.s`, la cfg de `ld65`, las capturas) quedó en
el scratch, fuera del repo, a propósito.

- `uruya-4bpp.sfc`: modo 1, BG1 la capa de abajo, BG2 la de arriba (con la
  prioridad de tile en 1, que es lo que la pone delante), 8 paletas de 15
  colores decididas por `adeleine reduce` tal cual, sobre los conjuntos de
  colores de cada tile de 8x8 de las dos capas juntas.
- `uruya-4bpp-clustered.sfc`: los mismos tiles, pero las paletas salen de
  agrupar los tiles en 8 por cercanía de color y quedarse en cada grupo con los
  15 colores que menos error cuestan; cada píxel va al más cercano de la
  paleta de su tile. No es Adeleine: es un script de 150 líneas, para ver
  cuánto de lo perdido era del algoritmo y cuánto del formato.

Cruz del pad para recorrerlo (2 px por cuadro; con B, 5). El mapa de 120x120
tiles se scrollea con una ventana de 64x64 por capa en VRAM, y el NMI escribe la
columna o la fila que entra (≈124 palabras en el peor caso, diagonal, en
vblank). Funciona en snes9x, bsnes y mesen-s con el mismo cuadro.

### Lo medido

- **Tiles de 8x8 a 4bpp**: 878 con Adeleine, 896 con el agrupamiento (contando
  el vacío; las dos capas comparten el juego de tiles). Buscar espejos no
  encontró ni uno. Con el 8bpp de wally eran 817, que son tiles de otro tamaño
  y color: ver abajo. A 4bpp ocupan 28 KB de los 64 KB de VRAM; con los dos
  tilemaps de 64x64 (8 KB cada uno) quedan unos 20 KB libres, o sea, otros 600
  tiles. Entra de sobra y sobra para animaciones.
- **Colores**: el mapa tiene 157 colores a 15 bits (los 157 están en la capa de
  abajo; la de arriba usa 74, todos entre los mismos). El 8bpp de wally ya
  los había bajado a 98. Las 8 paletas de 15 son 120 casillas.
  - Adeleine: quedan **19 colores distintos** (las 119 casillas llenas, pero
    casi todas repiten los mismos), 138 fusiones, el 33,5 % de los píxeles
    cambia de color. Se ve: el techo rojo de la casa pierde sus rosados y sus
    claros, el agua y el empedrado quedan planos.
  - Agrupamiento: quedan **73 colores distintos**, el 17,7 % de los píxeles
    cambia de color, y el rojo del techo, el verde de las copas y el azul del
    agua se mantienen casi como el original; el techo es lo que más se nota.
- **Por qué Adeleine deja tan pocos**: `reduce` fusiona globalmente, un color a
  la vez, hasta que `try_pack` (un best-fit codicioso) acomoda todos los tiles;
  no puede elegir que dos tiles vecinos se pinten con paletas distintas la misma
  tonalidad. La paleta es por tile, y la fusión es por color de todo el mapa: ahí
  se pierde. Una elección por paleta, como la del agrupamiento, conserva cuatro veces más
  colores. Sería una mejora de `adeleine` si se
  siguiera con esto; no se tocó.
- **Chequeo**: la ROM contra el render que sus propias paletas prometen, a 15
  bits, en 9 posiciones de cámara (impares, diagonales, bordes): 0 píxeles de
  diferencia en las tres emulaciones. Lo único que no es exacto es la última
  línea del borde sur, que el PPU dibuja una fila más abajo de lo que el mapa
  tiene.

### Lo que no hace

Sin héroe, sin eventos, sin animaciones de agua o de tile, sin los
eventos-tile horneados (no los intenté: con 20 KB libres de VRAM y la capa de
arriba ya en BG2, entran sin pedir nada nuevo). Sin ventana de mensajes: la
paleta 0 que el motor reserva para ella acá es una más del fondo.
