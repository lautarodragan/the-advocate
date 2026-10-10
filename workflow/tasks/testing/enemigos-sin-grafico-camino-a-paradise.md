---
name: "Enemigos sin gráfico en el camino a Paradise"
description: "En los mapas más nuevos, del camino a Paradise, algunos enemigos de la pelea no se dibujan (o no existen), jugando con MSU-1"
type: bug
agents: [Chajá]
assignee: taro
---

De taro, el 2026-10-05: "cuando probé los mapas más nuevos (camino a
Paradise), noté que algunos enemigos no tienen gráfico (no se renderiza o no
existe). Esto fue con el msu." Jugado con el build
`2026-10-04-83e4886-3e0b7b59` o el anterior, en la consola o el emulador,
con las pistas y el `.msu` al lado. Después precisó: "en el bosque, apenas
entrás desde el mapa del mundo, el que te lleva a Paradise, antes de que
aparezcan los agentes con el hover tram. Creo que el nombre de los enemigos
era Ogre o algo así", y "puede que sea el Rogue Bandit".

## Qué era

**Los Oblings.** Su battler es del RTP —el `Troll` y el `Hog`—, y el
conversor buscaba los battlers **sólo en el juego**: `find_file` de
`scene.rs` en `rm2k-snes-convert` les pasaba `with_rtp = false`, que venía
del Python (`_file` de `tools/port/scene.py`, 9cae36fc) con el porqué "so as
not to change which ones get in without looking at it". Los fondos sí lo
buscaban desde el 2026-09-27. Sin archivo, el enemigo quedaba con battler
`$FF` en `member_battler` y la ROM no dibujaba nada, sin una línea en
`conversor.log`.

No es del `.msu`: pasa igual con MSU-1 y sin él. Ni de las otras causas que
el encargo listaba —el límite de siete battlers por tropa, las paletas, la
VRAM, un battler grande—: medido abajo.

**El Rogue Bandit no tiene el problema**: es la tropa 120, con `newbie`, que
es del juego, y se dibuja con y sin MSU-1, en snes9x y en bsnes, antes y
después del arreglo. En el original (BattleTest) es el mismo dibujo.

## Lo medido

Las tropas de los mapas del encargo —105 a 108, 109 a 128, la granja— **son
una sola**: la 184 del 105, el guardia de la Agencia, con `Sagencyg`, que se
dibuja. Ninguno de esos mapas tiene encuentros al azar. El bosque (310 a 313)
y el mundo (66) son donde están las peleas del camino.

De las 80 tropas de `release`, **siete** peleaban sin dibujo —todas por
esto—: la 118 (Oblingx2) y la 126 (Obling y Green Wylden) del 310, que es lo
que vio taro; la 136, 137, 138 y 139 de los Oblings del mundo (66, y el 158
fuera de `release`); y la 178, Dr. Vago en el 76, que es el `Man5`.

Cada tropa de `release`, abierta en Sector 27 cambiando su lugar en
`troop_id` por el de la 100, comparada pixel por pixel contra la composición
del juego (WRAM y pantalla), en **snes9x y bsnes, con y sin MSU-1**: las 80
bien con el arreglo, en las cuatro combinaciones. Y las nueve tropas del 310
abiertas en el 310 de verdad, con su fondo, en las mismas cuatro: bien.
mesen-s no se pudo sumar: arrastra estado de una consola a la siguiente en el
mismo proceso (lo que dice `test_cores.py`), y corta en el segundo
`Teleport`.

**El juego entero**: de las 152 tropas que nombra algún mapa o evento común,
14 tienen algún battler del RTP —las 7 de arriba y la 163, 164, 180, 182,
183, 186 y 188, de mapas que `release` no lleva—. De las 300 de la base, 86;
son 171 miembros de 442, con 42 imágenes del RTP. **Ningún battler del juego
falta en los dos lados**: con el arreglo, todos se encuentran. Y ninguna
tropa del juego pasa de tres battlers distintos ni de cuatro miembros.

## El arreglo

* `rm2k-snes-convert`: `find_file` busca en el juego y después en el RTP,
  para fondos y battlers —el parámetro se fue—; y si un battler no está en
  ninguno de los dos, `conversor.log` lo dice.
* `pruebas/arnes/scene.py`: lo mismo en `_file`, que es la composición
  esperada de las pruebas.
* `parches/auto/battlers/`: los cinco nuevos (`Troll`, `Troll-20`, `Hog-20`,
  `Hog-340`, `Man5-320`), de `just parches`.

## La prueba

`test_escena_cada_tropa_del_cartucho_dibuja_a_todos`, en
`pruebas/rpgmaker/test_batalla_escena_dibujo.py`: cada tropa de `release`
contra la composición del juego, en la WRAM y en la pantalla. Unos 25
segundos. Sin el arreglo, roja con las siete:

    la 178 ['Man5']: 1065 pixeles en la WRAM y 1065 en la pantalla
    la 136 ['Hog']: 2024 pixeles en la WRAM y 2024 en la pantalla
    la 137 ['Hog']: 2024 pixeles en la WRAM y 2024 en la pantalla
    la 138 ['Hog', 'Hog']: 4048 pixeles en la WRAM y 4048 en la pantalla
    la 139 ['Troll', 'Hog', 'Hog']: 5182 pixeles en la WRAM y 5152 en la pantalla
    la 126 ['Troll', 'Orc']: 2626 pixeles en la WRAM y 2626 en la pantalla
    la 118 ['Troll', 'Troll']: 3306 pixeles en la WRAM y 3306 en la pantalla

Corre sin MSU-1, como la tanda: el camino con MSU-1 se midió aparte (arriba)
y no queda en la tanda, porque el bug no era de ese camino.

## Dr. Vago

taro: "El Dr Vago tampoco aparece en su batalla". Es la misma causa: la
tropa 178, la única con él, pelea en el 76 con el `Man5` del RTP. El
recorrido de Sorbe juega esa pelea y le saca una foto,
`sorbe-y-la-curacion/05-la-pelea-con-vago`, pero estaba en
`pendientes.txt`, sin golden: nadie miraba si Vago estaba. Con el arreglo
está, y la foto pasa a ser golden (commit aparte).

## Para comparar con el original

El RPG_RT de Wine abre una pelea suelta con `RPG_RT_2015.exe BattleTest 0 0
<tropa>`: la tropa va en el tercer argumento (`player.cpp` de easyrpg). Así
salieron las capturas del original, sin jugar hasta la pelea.

## Al mergear

Herramientas: el commit `1241e7de` sobre `01f84afd`, en la rama del worktree
de Chajá. Sólo toca `rm2k-snes-convert`: reinstalar `convert` en el global
(`just -f tools/justfile install convert`) y rearmar `release`, que pasa a
llevar cinco battlers más. ABL: rama `chaja-enemigos-sin-grafico`.

Qué jugar: una pelea con Oblings en Tangle Forest o en el mundo, y la de
Vago en la montaña de Sorbe.
