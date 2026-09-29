# Qué

RM2k lleva un `press_time` por botón —easyrpg, `src/input.cpp`—, así que
cada flecha tiene su propia espera de repetición. La ROM lleva **uno solo para
las cuatro**, `arrows_frames` en `arrows_repeat` (`tools/runtime/control.s`):
apretar una flecha nueva lo pone en cero aunque otra siga sostenida.

Lo que se ve distinto: sosteniendo abajo, con la repetición ya andando, tocar
derecha le reinicia la espera a abajo, que vuelve a tardar 23 cuadros en
repetir. En RM2k abajo seguiría cada 4 sin enterarse.

# Por qué

En los menús de una columna, que son casi todos, derecha e izquierda no hacen
nada, y nadie sostiene dos flechas a la vez para recorrer una lista. Uno por
botón son tres bytes más de RAM y un lazo en `read_pad`, que corre cada
cuadro en todas las pantallas.

# Medido

Nada: no hay prueba que sostenga dos flechas, ni caso del juego donde se
note. Si alguien lo nota jugando, el arreglo es un contador por flecha en
`arrows_repeat`; las pantallas no se enteran.
