**La escena de la pelea, compuesta en la consola y no en el conversor.**

Hoy `tools/port/escena.py` hornea fondo y monstruos en una imagen por tropa, a
32 KB cada una (seis en `abl`). Eso multiplica imágenes por combinación, y un
enemigo muerto se sigue viendo.

La idea, de taro el 2026-09-21: guardar **cada fondo una vez y cada enemigo una
vez**, y componer al empezar la pelea.

- El fondo limpio va a la WRAM; los battlers se superponen con `AND`/`OR` por
  plano de bits —el 8bpp es planar—, y la escena sube a la VRAM como hoy.
- Cada battler tiene **15 colores más el transparente**: sus 4 bits bajos salen
  de su dibujo y los 4 altos son la paleta que le toca en esta pelea. Es una
  decisión artística —se pierden colores respecto de hoy— y va a `parches/`.
- Cuando un enemigo muere, se recomponen sus celdas desde el fondo limpio y se
  suben por DMA. Sin versiones precalculadas.
- Sin fondo —o sin MSU-1, más adelante— es el mismo código sobre un fondo liso.

PoC: dos fondos en la ROM, `SJBackdropABL04` (la pelea del droide, tropa 82) y
`ABLBackdropSJ03` (los encuentros al azar de los Back Alleys: tropas 88–93 y
99–101). Si no entran los dos, sólo el de los Back Alleys.

Lo que decide si sirve: **cuánto tarda componer la escena más cargada** y **cómo
se ven los battlers a 15 colores**.
