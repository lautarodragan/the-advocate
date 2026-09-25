# Qué

La ROM no lleva a VRAM el ChipSet entero, como RM2k, sino **los tiles únicos
de lo que el mapa dibuja**: el conversor renderiza el mapa y saca de ahí los
tiles. Un chipset de RM2k expandido son cientos de tiles de 8x8, y no entran en
lo que le queda al fondo con la ventana de mensaje puesta.

Lo que se pierde es que **dos mapas del mismo chipset compartan sus tiles**,
que ahorraría bytes de cartucho y la recarga de VRAM al cruzar de uno al otro.

# Medido

El 2026-09-07, contando sólo los ids que algún mapa del juego usa: el
`ChipSet3` da 420 tiles y el `BLchp1` 523. El mapa 1 dibuja 341 y el 2, 278,
contra los 420 del chipset que comparten; el pool compartido de los dos son 437
y no entraba en ningún reparto de VRAM de ese día. La cuenta entera está en
`docs/research/graficos-de-rm2k-a-snes.md`, "Compartir tiles entre mapas".

# Cómo se ve hoy

No se ve: cada mapa dibuja lo mismo que en RM2k. El reparto de cada mapa lo
elige `vram_layout` en `tools/port/snes_convert.py`, y `docs/port/vram.md`
explica de dónde salen los posibles.

# Cuándo deja de alcanzar

Un juego cuyos mapas usen más tiles distintos de fondo de los que entran en
cualquier reparto. Ahí no hay reparto que lo salve: hay que recargar VRAM
mientras el mapa scrollea, que es un motor distinto del que hay.
