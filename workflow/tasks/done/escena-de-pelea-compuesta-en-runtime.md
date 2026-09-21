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

## El PoC, hecho (2026-09-21)

Anda en `abl`: la pelea del droide sobre `SJBackdropABL04` y los encuentros al
azar de Sector 30 y Sector 27 sobre `ABLBackdropSJ03`, heredado del mapa como
hace `Game_Map::SetupBattle`. Un enemigo muerto desaparece. El cómo está en
`tools/port/escena.py` y arriba de `escena_subir` en `main.s`; los quince
colores de cada battler, en `parches/battlers/`.

Las capturas que hay que mirar están en `/extras/capturas/escena-runtime/`
—antes y después, y un borrado cuadro por cuadro—, y las de las once goldens
que se movieron, al lado de cada una como `<nombre>.nueva.png`, sin
reemplazarla.

**Cómo se mide lo que decide si sirve**, que no se escribe acá porque cambia:

* cuántos cuadros lleva componer: `ESC_CUADROS`, en la RAM, apenas se abre la
  pelea. La más cargada del PoC es la tropa 100 —el encuentro de
  `test_escena.py`—.
* cuánto ocupa: la suma de los segmentos de la ROM en el `.dbg` del build de
  `abl`, contra el de antes.
* el banco 0: el método de `AGENTS.md`, en los cuatro cartuchos.

## Lo que falta para que sea el mecanismo de todas las peleas

* **Los demás fondos.** El juego nombra una quincena entre los
  `EnemyEncounter` y los mapas, a 32 KB cada uno sin comprimir. Comprimirlos
  es barato de este lado —el fondo limpio ya se arma en la WRAM, así que la
  descompresión va ahí y el búfer compuesto sale de él con un `mvn`—, y es lo
  que haría falta antes de sumarlos; o traerlos por MSU-1.
* **El fondo del mapa en un `EnemyEncounter` que no nombra ninguno**
  —`parameters[2] == 0`—. Hoy va liso; RM2k usa el del mapa, igual que un
  encuentro al azar. Y el del terreno, `background_type` 1, que el port no
  tiene.
* **Una tropa que dos `EnemyEncounter` piden con fondos distintos** se queda
  con el primero, como antes: el fondo es de la tropa y no de la pelea. Para
  eso el opcode tendría que llevarlo.
* **El borrado es de golpe**: RM2k funde al enemigo que muere. Acá se va en
  los cuadros que tarda en subir, de a filas de tiles, y la pelea se congela
  mientras la ROM recompone.
* **El fundido de entrada a la pelea no existe en el port**: la composición
  pasa con la pantalla negra. RM2k hace dos destellos y una transición de 41
  cuadros para salir del mapa y otra de 41 para entrar, así que el negro
  entraría adentro de la primera.
