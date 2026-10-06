---
name: "Fusionar tiles parecidos cuando el fondo no entra"
description: "Si el fondo de un mapa tiene más tiles distintos que los que entran en VRAM, se fusionan los más parecidos hasta que entre, con un aviso: un piso jugable algorítmico, sin intervenir a mano"
type: feature
agents: [Cardón]
assignee: Cardón
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
