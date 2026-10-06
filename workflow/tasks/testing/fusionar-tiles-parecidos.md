---
name: "Fusionar tiles parecidos cuando el fondo no entra"
description: "Si el fondo de un mapa tiene más tiles distintos que los que entran en VRAM, se fusionan los más parecidos hasta que entre, con un aviso: un piso jugable algorítmico, sin intervenir a mano"
type: feature
agents: [Cardón]
assignee: taro
---

18 mapas de Vampires Dawn pasan el tope de unos 544 tiles de fondo (el
mayor, Uruya, 817; el mundo, 597): medido por Hornero el 2026-10-06 con
`wally layers` sobre los 440 mapas, en `/extras/scratch/hornero/vd-tiles/`.

taro, el 2026-10-06: "tal vez fusionar tiles sea un buen feature para tener,
en general. incluso si queda feo, nos permite tener un lower bound jugable
de forma algorítmica".

## Hecho (Cardón, 2026-10-06)

Va en `wally`, no en Adeleine ni en Voodoo: la decisión de qué se parece a
qué es de Adeleine (`group_tiles`, el k-means de los fondos de modo 7) y
se usa tal cual; lo que hay en `wally/src/background/fuse.rs` es el
cableado —contar tiles como los cuenta Voodoo, con los espejos, y reescribir
las celdas elegidas en la imagen del piso antes de que nadie la lea—.

Es el **último paso** de `map::convert`, después de las imágenes, las
ranuras compartidas, el caché y la caja de animaciones: sólo se pide si el
mapa no entra en ningún reparto, y sólo si algún reparto aguanta sus sprites
y su capa de arriba (si lo que sobra son sprites, fusionar no sirve). El tope
es el fondo del reparto más grande que los aguanta; las animaciones de agua
suman tiles después, así que si pasa se reintenta con menos (hasta 4 veces).
Un mapa que ya entra no pasa por acá: byte por byte igual.

## Medido en Vampires Dawn (2026-10-06)

Con la fusión, **no arma**: se corta por otra cosa antes de llegar a los
mapas que la necesitan, y no es del mismo tipo.

* El fondo ya no es lo que traba a ninguno de los 18 mapas grandes: con el
  tope de 544 baja cada uno a 544 (53 menos en el 1, 273 en Uruya, 260 en el
  338; el 249 sólo 9). Capturas en `/shared/capturas/2026-10-06-fusionar-tiles/`.
  En la conversión entera sólo se fusionaron el mapa 1 (68 tiles, al tope del
  reparto que sus sprites dejan) y el 118 (134, a 480).
* Lo que corta es **el banco de sprites y la capa de arriba**: mapa 15
  (436 sprites con 576 de fondo), 57 (768), 95 (4096), 99 (832), 150 (436 con
  609 y 130 arriba), 165 Uruya (768 con 817), 225 (832), 399 (512 con 136
  arriba): ningún reparto aguanta esos sprites, y fusionar fondo no lo
  arregla. Los paneles de modo 1 de los mapas 28 (3411 sprites), 402 y 403
  tampoco entran. Y con esos afuera, `rm2k-snes-battle` se corta por una cosa
  global: los encuentros no entran en tablas de un byte (121 registros, 136
  zonas, 779 tropas).
* El siguiente paso, si se quiere, es degradar los sprites con el mismo
  criterio (otro tipo de fusión, más caro: son poses y paletas).

Instalar al mergear: `wally` (`just -f tools/justfile install wally`).
Tanda de ABL con `wally` local: 1150 verdes, `abl.sfc` `8bb36b99…` sin cambios.
