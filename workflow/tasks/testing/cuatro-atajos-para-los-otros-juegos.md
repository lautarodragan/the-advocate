---
name: "Cuatro atajos para los otros juegos"
description: "La condición por dirección, las órdenes de ruta que faltan, PlayerVisibility y los Comment en las páginas de las tropas: lo barato que más páginas destraba en los siete juegos"
type: feature
agents: [Chajá]
assignee: taro
---

Medido por Hornero el 2026-10-06 con `rm2k-snes-events culprits --every-map`
sobre los siete juegos, después del merge de los códigos de color. Las
páginas que **sólo** ese comando deja afuera:

* `ConditionalBranch` tipo 6, por la dirección de un personaje: Sunset 111,
  Vampires Dawn 37, El Dorado 23, Desert 21. Ya en
  `todo/los-comandos-sueltos-de-los-mapas.md`, para ABL (31 páginas).
* `MoveEvent` con órdenes que la ROM no entiende: el paso al azar (8) en
  Desert (39) y Vampires Dawn (16), alejarse del héroe (10) en Vampires Dawn
  (48) y El Dorado (9), y rutas de Sunset con 36/37 (unas 40; falta ver qué
  orden es la que traba). `wishlist/ruta-los-movimientos-que-faltan.md` dice
  que no rendían: en ABL era cierto, en estos juegos no.
* `PlayerVisibility`: El Dorado 170.
* `Comment` en las páginas de las tropas: The Book of Three 153. En los mapas
  ya se ignora.

taro, el 2026-10-06: "Dale!", con Sonnet.

## Chajá, 2026-10-06

Cuatro commits en las herramientas, uno por atajo, más uno que salió de
medirlos, y cuatro en ABL (rama `chaja-atajos` de su clon). Cada comando con
su prueba en el crate, mostrada en rojo antes del arreglo.

**Los opcodes que se tomaron**: `OP_IF_FACING = 0x47` y `OP_HERO_VISIBLE =
0x48`. El siguiente libre es el 0x49.

**1. La condición por dirección** (`OP_IF_FACING`: personaje, dirección,
destino). El personaje es el héroe, "este evento" o un evento por su número,
con el mismo `target_of` que las rutas. La dirección del héroe es `hero_dir`;
la de un evento, de donde la lee `face_diagonal`: la ranura de su ruta si ya
la giró, y si no la fila de la tabla de NPC. **Un evento sin fila contesta
abajo**, que es el valor por omisión de RM2k; difiere sólo para un evento
invisible cuya página mira a otro lado y al que una condición le pregunta.

**2. Las rutas.** Entran las órdenes 8 (paso al azar), 10 (alejarse del
héroe) y 22 (mirar para el otro lado), **sólo sobre eventos** y no adentro de
un salto, como 9 y 21. Alejarse es `toward_hero` dado vuelta medio círculo,
idéntico en todos los casos incluido el empate; el paso al azar toma dos bits
del xorshift del mapa, así que es al azar pero no es el generador de RM2k.

**Lo que traba las rutas de Sunset con 36/37 no son 36/37**, que ya
compilaban: son **las diagonales del héroe** (4 a 7), que el compilador
rechaza a propósito. Es lo que más páginas deja ahora: unas 51 en Sunset y 45
en Vampires Dawn, medido. **No se hizo**, y por qué está en
`wishlist/ruta-los-movimientos-que-faltan.md`: es un paso nuevo del héroe, no
cuatro rutinas copiadas, y no hay con qué compararlo. Los giros relativos (16
a 20) y avanzar (11) del héroe tampoco: unas 8 páginas en Sunset.

**3. `PlayerVisibility`** (`OP_HERO_VISIBLE`, un byte). El héroe escondido no
se dibuja y todo lo demás sigue igual. El estado es del jugador: sobrevive al
mapa, arranca visible en el boot y **viaja en la partida guardada** —una línea
de `save_table` y un byte de `SAVE_BYTES`—, así que **las partidas guardadas
con la ROM de antes dejan de cargar**.

**4. `Comment` en las páginas de las tropas**: dos líneas en
`TROOP_COMMANDS`. No emite un byte, así que no hay camino de ROM que ejecutar.

**Lo que salió de medir: `SUB_MAX` de 8 a 16.** Con todo lo anterior El
Dorado dejó de armar: el mapa 7 pide nueve bloques sustituidos y la tabla
llevaba ocho; el noveno lo trae una página que antes no compilaba. 32 bytes
de BSS del banco 0, que quedan con 1.995 B libres en `abl`. **Cada vez que
entren páginas va a poder pasar de nuevo**; nadie midió cuántos pide el mapa
que más pide de los siete.

### Páginas que compilan, antes y después

`culprits --every-map`, con el mismo request por juego y los binarios de
`main` contra los del worktree. Mapas, salvo donde dice.

| juego | antes | después | |
|---|---|---|---|
| The Book of Three | 206 de 746 (tropas) | 359 de 746 (tropas) | +153, las de los `Comment`; los mapas no cambian |
| Desert Nightmare | 7034 de 7340 | 7150 de 7340 | +116 |
| El Dorado | 710 de 972 | 963 de 972 | +253, y un común más (9 a 10 de 10) |
| Sunset Over Imdahl | 1151 de 1369 | 1266 de 1369 | +115 |
| Vampires Dawn | 21214 de 22977 | 21272 de 22977 | +58 |
| ABL | 5560 de 5601 | 5592 de 5601 | +32: las 31 de Eisen y una más |

Vampires Dawn **no termina de armar** por otra cosa —el mapa 1 y sus
imágenes de final, igual que antes de esto—, así que su número sale de
`scan`, no de un cartucho. Ahí quedan por debajo de lo esperado porque tiene
más de un comando trabando la misma página; lo que le queda en `MoveEvent` son
las diagonales del héroe.

Las ROMs de los juegos que arman —The Book of Three, Desert Nightmare, El
Dorado y Sunset— están en `/shared/builds/otros-juegos/<juego>.sfc`.

### ABL

**La tanda: 1147 en verde** con las herramientas del worktree (1136 de antes
y las 11 pruebas nuevas), y **ninguna golden cambió**. `abl.sfc` pasó de
`27e94e67039533a2…` a `602b60e0e0635bfb…`, y es reproducible: la misma con
`NO_CACHE=1`. Cambia por cuatro cosas, todas esperadas: el runtime lleva
rutinas y opcodes nuevos; las 32 páginas que ahora compilan; `hero_hidden`
en la partida guardada y `SUB_MAX`; y los siete casos de prueba nuevos, que
`release` lleva todos. **No se miró si las 32 páginas se pueden alcanzar
jugando**: son la simulación de Eisen, y ninguna golden las ve cambiar.

Rama `chaja-atajos` del clon `/extras/scratch/chaja/abl-atajos`: tres pruebas
(`test_condicional_por_direccion.py`, `test_rutas_que_se_alejan.py`,
`test_heroe_oculto.py`), sus casos, y dos arreglos que pidió la tanda sola:
el índice del README de las pruebas, y la resta de `test_la_musica_viaja_en_la_partida`,
que duplica `save_table` y avisa cada vez que la partida crece.

### Lo que la tanda no cubre

* **Que `hero_hidden` viaje en un guardado y se cargue.** Sólo se prueba que
  el formato cierra y que el estado vive en la RAM.
* **Un evento cuya dirección ya cambió una ruta**, en la condición por
  dirección: las pruebas miran la de su página, no la de la ranura. Lo mismo
  para un evento sin fila que mire a otro lado.
* **El empate de alejarse del héroe**: lo cubre sólo el razonamiento —es
  `toward_hero` dado vuelta—, no hay caso con el héroe en una diagonal
  exacta.
* **Que el paso al azar sea al azar**: la prueba mira que no vaya siempre para
  el mismo lado en dieciséis pasos, con la semilla del arranque.
* **Los juegos mismos**: ninguna de las páginas nuevas de los otros juegos se
  jugó; lo que se mira es que compilan y que los cartuchos arman.

## Al mergear

Reinstalar en el global `events cartridge convert`: el compilador, el runtime
y el bytecode, y el conversor por `SUB_MAX`. `bytecode` cambió, y lo compila
adentro `rm2k-snes-audio`: si algo de música se arma con esa herramienta,
también; el stream de música no cambió.

ABL: `git pull` de la rama `chaja-atajos` del clon de Chajá.
