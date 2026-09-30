---
name: "El teletransporte tarda tres cuadros de más"
description: "Contra el RPG_RT, cada Wait+Teleport de la escena del mapa 16 dura 161 ticks en la ROM y 158 en el original: dos en la espera y uno en el fundido"
type: bug
assignee: Benteveo
---

Apareció el 2026-09-29 midiendo contra el RPG_RT las tres divergencias que
venían de la referencia en Python (`testing/tres-divergencias-contra-rm2k.md`,
Caranday). La de `move-event-tras-teleport-interno.md` no se sostuvo, pero
midiéndola salió esto.

## Qué se midió

La escena del mapa 16 —la corrida al trabajo— son cuatro vueltas de
`MoveEvent` del héroe, `Wait 15` y `Teleport` al mismo mapa. En el RPG_RT de
2015 con Wine, sobre una copia del juego cuyo EV0001 del mapa 4 arranca con
`Teleport 16 (53,7)`, grabando el escritorio de Wine a 60 cuadros por segundo;
en la ROM (`release`), con `ir_al_mapa(16, 53, 7)` y una captura por tick. En
los dos se mide el corrimiento de la cámara cuadro a cuadro y el brillo medio,
y de ahí salen cuatro marcas por vuelta: **S**, el primer paso del héroe; **F**,
el primer cuadro más oscuro del fundido que borra; **J**, el último que se
aclara al mostrar.

|                         | RPG_RT | ROM |
|-------------------------|--------|-----|
| de J al primer paso (S) | 2      | 2   |
| del primer paso a F     | 89     | 91  |
| el fundido, de F a J    | 67     | 68  |
| la vuelta entera, S a S | 158    | 161 |

Igual en las tres vueltas internas y en dos grabaciones del RPG_RT. O sea: lo
que va de la llegada a los pasos es igual, y **la ROM se demora dos cuadros más
en pasar de la espera al teletransporte y uno más en el fundido**. Un efecto
visible: en la tercera vuelta la ruta dura más que la espera, y el héroe llega
a caminar un cuadro más —2 pixeles— antes de que se corte.

Del mismo lado puede estar esto otro, de la página `timer-cero`: el
`TintScreen` que va después de un `Wait 2` se ve **13** cuadros después de que
aparece el cronómetro en la ROM y **12** en el RPG_RT. Puede ser la espera, o
puede ser `divergencias/ticks-de-pantalla-despues-del-interprete.md`, que
describe justamente un cuadro de atraso en lo que la pantalla muestra; no se
separaron.

## Lo que no se sabe

Cuál de los dos cuadros es la espera y cuál el arranque del fundido: haría
falta una página que espere sin teletransportar, y ninguna de la tanda lo hace
sobre un mapa donde se vea. Y el RPG_RT medido es el de 2015, no el de 2000
que usó el autor (ver lo que dice de eso la receta de Wine).

Las capturas, con el número de cuadro relativo en el nombre, están en
`/shared/capturas/2026-09-29-divergencias/mapa16-*` y `cronometro-*`.

## Tomada el 2026-09-29

taro aceptó que la ROM cambie para igualar a RM2k. Si el arreglo mueve
goldens, **no se mergea hasta que taro las vea**, lado a lado.

## De dónde salían los tres (Benteveo, 2026-09-29)

Medido en la ROM tick por tick —posición del héroe, `ev_waiting`, `fade` y
`brightness` por la RAM— con la misma partida que Caranday (`en-5`,
`ir_al_mapa(16, 53, 7)`). En la vuelta de los números de arriba, la página
corre el `MoveEvent` y el `Wait` en el tick 71, el héroe da el primer paso en
el 72, el `Teleport` corre en el **162**, el primer tick más oscuro es el
163 y el brillo vuelve entero en el 231; la página sigue en el 232.

* **Uno es la espera.** `op_delay` guardaba en `ev_waiting` los noventa
  cuadros enteros y cortaba el tick, así que la orden siguiente corría 91
  después. En easyrpg `SetupWait` deja `wait_time` y el lazo del intérprete
  vuelve arriba **en el mismo cuadro**, donde `wait_time--; break;` ya gasta
  uno (`game_interpreter.cpp:447`): la siguiente corre 90 después. Es
  también el tinte de `timer-cero`: con la espera un tick más corta, sale un
  tick antes, que es el +12 del RPG_RT y no el +13 de la ROM.
* **Los otros dos son el fundido**, y no son la espera: con la espera ya
  arreglada quedan 90 del paso al fundido y 68 de fundido, contra 89 y 67.
  En el RPG_RT el primer cuadro oscuro **es el del salto** —el 90 después
  de la espera—, y el fundido entero, de ése al último, dura 68 cuadros
  contándolo; la página sigue en el siguiente. Acá el tick del salto se veía
  prendido, oscurecía el siguiente, y el fundido congelaba 69 más: 70 del
  salto a la página, contra 68.
* Que el primer cuadro oscuro sea el del salto lo confirma el agua: en el
  RPG_RT queda quieta desde el primer cuadro del fundido hasta el último,
  los dos incluidos (lo midió Caranday). Así que el tick del salto tampoco
  cuenta para las animaciones.

easyrpg no sirve de árbitro para el fundido: sus transiciones —35 cuadros de
`Update` más los de `AsyncNext`— tardan más que el RPG_RT medido. Lo que
manda es la medición.

## El arreglo

* `op_delay` guarda uno menos, salvo el cero (un `Wait 0` sigue cortando
  el tick, que es el "0.0 waits 1 frame" de easyrpg). Vale para toda
  espera que compila a `OP_DELAY`: `Wait`, y las de `TintScreen`,
  `FlashScreen`, `ShakeScreen`, `FlashSprite`, `MovePicture` y
  `ShowBattleAnimation` con "esperar".
* `start_fade` pinta el primer paso del fundido en el mismo tick del salto
  —el brillo y nada más: la carga sigue siendo de `fade_tick`— y suma ese
  tick a `frozen_ticks`.
* El fundido dura `FADE_TOTAL = 68` ticks contados desde el del salto; la
  rampa sigue siendo de 24 pasos para cada lado, y el negro del medio pierde
  dos. `FADE_FRAMES` y `FADE_BLACK` se fueron. El corte arranca en la mitad
  menos uno (`FADE_CUT`), así que el tick del salto ya es negro y el
  siguiente carga: antes el negro caía en el siguiente.

## Los números

Con la prueba nueva, `rpgmaker/test_teletransporte_contra_rm2k.py`, que
mide lo mismo por la RAM:

|                         | RPG_RT | ROM antes | ROM ahora |
|-------------------------|--------|-----------|-----------|
| del primer paso a F     | 89     | 91        | 89        |
| el fundido, de F a J    | 67     | 68        | 67        |
| de J al primer paso     | 2      | 2         | 2         |
| la vuelta entera        | 158    | 161       | 158       |

Y la tercera vuelta: por la imagen, con los scripts de Caranday, la cámara
se mueve **90 cuadros** (dx 96, dy -84), igual que en el RPG_RT; antes 91
(dy -86). El agua: `frozen_ticks` sube durante los 68 ticks de F a J,
incluidos.

## Lo que se movió de rebote

* **`Recorrido.esperar_el_control` ya no toca A con el control devuelto.**
  Con el fundido dos ticks más corto, al llegar al Sector 35 la página
  terminaba antes del A de la ventana de ocho ticks, y el A le hablaba al
  auto, que está enfrente: vuelta al 36 con la elección abierta, y diez
  pruebas trabadas ahí. El A de esa espera es para los mensajes; ahora se
  pregunta si hay una página corriendo justo antes de tocar. Con eso
  ninguna golden de las jugadas cambió.
* `test_borrar_con_el_corte` pide ahora el negro en el tick del salto (0) y
  la carga en el siguiente (1).
* **44 goldens de la tanda**, en un commit aparte y sólo de goldens. Todas
  son corrimientos en el tiempo: la espera un tick más corta, o todo lo que
  pasa después de un teletransporte dos ticks antes (y la animación del
  ChipSet dos pasos menos congelada, en las que llegan por `ir_al_mapa`).
  Separadas armando con la espera sola: la espera sola ya mueve `lugar`,
  `parar-rutas`, `savepoint-guarda`, `tram`, `autos9`, `core-puerta`,
  `sacudir`, `sacudir-borde`, `cinematica`, `apertura`, `8-left`, `manta` y
  `cartel`; sólo el fundido, `3-down-56`, `8-right`, `fuego-20`, `talan`,
  `puerta-8-9-120` y las cuatro de `transicion-*`, que son la rampa misma a
  mitad de camino. Lado a lado, con la diferencia en rojo, en
  `/shared/capturas/2026-09-29-teletransporte/`.

**El merge espera el visto bueno de taro sobre esas goldens.**

## Lo que queda

* `PanScreen` con espera tiene el mismo tick de más —`op_pan` guarda
  `GetPanWait()` entero y corta el tick— y no se tocó: no hay medición del
  RPG_RT que lo pida, y mueve otras goldens. El cero ya estaba bien.
* La partida de las pruebas que llega por `ir_al_mapa` sigue congelando un
  tick más que un `Teleport` de verdad (68 contra 67 más el del salto), como
  antes: es el arnés, que pide el fundido desde afuera.
* Lo que no cubre `just pruebas`: el corte medido contra el RPG_RT. Se
  movió por analogía con el fundido, no se grabó.
