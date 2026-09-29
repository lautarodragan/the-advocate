# Qué

`ChangeScreenTransitions` cambia con qué transición el teletransporte borra
la pantalla y con cuál la vuelve a mostrar. En RM2k son las veinte de la tabla
`fades` de `Game_System::GetTransition`; la ROM hace tres, y lo decide el
conversor —`CHANGE_SCREEN_TRANSITIONS` en `tools/port/eventos.py`—:

* **el mosaico** (17), con el registro MOSAIC del PPU, atado a la rampa del
  brillo. Ver `tools/runtime/teleport_transition.s`;
* **el fundido**, que es también lo que va para **las que la consola no
  hace**, como el zoom (16): acercar el mapa es modo 7, y el mapa está en modo
  3. Lo decidió taro el 2026-09-26, igual que para la pelea;
* **el corte** (19) para borrar: negro en un cuadro, como el `TransitionCutOut`
  de RM2k, y el mapa se carga ahí. Desde el 2026-09-27, por la historia de
  Eisen. "Ninguna" (20) para borrar compila también al corte.

Lo que queda distinto del original:

* **El mosaico oscurece.** En RM2k los bloques crecen sobre la imagen entera y
  al final se borra; acá el brillo baja a la vez, como en la pelea, porque la
  carga del mapa tiene que caer adentro del negro (ver `battle_fade.s`).
* **Los sprites no se pixelan.** El mosaico del PPU es de los fondos: el
  héroe y los eventos se ven enteros mientras el mapa se hace bloques.
* **El zoom es el fundido de siempre.**
* **La transición no viaja en la partida**, y en RM2k sí: ver
  `TRANSICION_BORRAR` en `tools/runtime/far_ram.s`.
* **Borrar con "ninguna" es el corte.** En RM2k no toca la pantalla, así que
  el fundido de vuelta funde del mapa viejo al nuevo (`screen1` y `screen2`
  de `Transition`); la consola no tiene con qué mezclar dos cuadros, y la
  carga del mapa escribe VRAM con la pantalla apagada. Lo pide el 93 al
  saltar al 95: allá se ve la sala de control deshacerse en el pasillo, acá
  un cuadro negro y el fundido de siempre.
* **El corte y "ninguna" para mostrar, y las de la pelea, no compilan**: la
  página que las pide no corre. Ninguna está en un mapa de la ROM hoy.

# Medido

El juego la usa en la guarida de Boss Wick: zoom para ir a los vidcasts (la
página 1 del evento 7 del 40), mosaico adentro (la 1 del 2 del 42), el borrar
de vuelta al fundido en el video (el 45) y todo al fundido en el favor (la 4
del 7 del 40). Y en la historia de Eisen: "ninguna" para borrar al bajar al
minijuego (la 1 del 4 del 93), el corte al salir de él (el 55 del 95), el
mosaico para entrar a la simulación del trono (el 1 del 101) y todo al fundido
de vuelta en Sorbe (la 5 del 6 del 81). En el juego entero la piden 15
páginas; las que usan el corte para mostrar o el 7 (de los bordes al centro)
están en mapas que no entran.

Lo cubren `test_transicion` en `rom/pruebas/rpgmaker/test_comandos_golden.py`
—goldens a mitad del mosaico y a mitad del zoom—, `test_borrar_con_el_corte`
en el mismo archivo —el brillo en cero y el mapa cargado en el primer tick del
fundido, contra la rampa entera del fundido—, el mosaico y el zoom también en
`test_cores.py`, y
`test_recorrido_lashe_wick_golden.py` y `test_recorrido_capitulo_golden.py`,
que cobran por la RAM lo que cada página deja elegido.

# Cómo se ve hoy

Entrar a los vidcasts es un fundido; de ahí hasta el video, cada salto se hace
bloques mientras se apaga y se deshace mientras se prende, con el héroe nítido
encima.

# Cuándo deja de alcanzar

Un juego que use las transiciones de bloques, persianas o barridos, o el zoom
como efecto que se tiene que ver: ver `tasks/wishlist/las-otras-transiciones-de-rm2k.md`.
