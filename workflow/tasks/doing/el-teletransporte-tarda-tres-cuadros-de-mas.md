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
