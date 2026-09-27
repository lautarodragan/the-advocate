# Qué

`ChangeScreenTransitions` cambia con qué transición el teletransporte borra
la pantalla y con cuál la vuelve a mostrar. En RM2k son las veinte de la tabla
`fades` de `Game_System::GetTransition`; la ROM hace dos, y lo decide el
conversor —`CHANGE_SCREEN_TRANSITIONS` en `tools/port/eventos.py`—:

* **el mosaico** (17), con el registro MOSAIC del PPU, atado a la rampa del
  brillo. Ver `rom/src/transicion_del_teletransporte.s`;
* **el fundido**, que es también lo que va para **las que la consola no
  hace**, como el zoom (16): acercar el mapa es modo 7, y el mapa está en modo
  3. Lo decidió taro el 2026-09-26, igual que para la pelea.

Lo que queda distinto del original:

* **El mosaico oscurece.** En RM2k los bloques crecen sobre la imagen entera y
  al final se borra; acá el brillo baja a la vez, como en la pelea, porque la
  carga del mapa tiene que caer adentro del negro (ver `fundido_de_pelea.s`).
* **Los sprites no se pixelan.** El mosaico del PPU es de los fondos: el
  héroe y los eventos se ven enteros mientras el mapa se hace bloques.
* **El zoom es el fundido de siempre.**
* **La transición no viaja en la partida**, y en RM2k sí: ver
  `TRANSICION_BORRAR` en `rom/src/ram_lejana.s`.
* **El corte (19), "ninguna" (20) y las de la pelea no compilan**: la página
  que las pide no corre. Ninguna está en un mapa de la ROM hoy.

# Medido

El juego la usa en la guarida de Boss Wick y en ningún lugar de `release`
más: zoom para ir a los vidcasts (la página 1 del evento 7 del 40), mosaico
adentro (la 1 del 2 del 42), el borrar de vuelta al fundido en el video (el 45)
y todo al fundido en el favor (la 4 del 7 del 40). En el juego entero la piden
15 páginas; las que usan el corte, "ninguna" o el 7 (de los bordes al
centro) están en mapas que no entran.

Lo cubren `test_transicion` en `pruebas/rpgmaker/test_comandos_golden.py`
—goldens a mitad del mosaico y a mitad del zoom—, los mismos casos en
`test_cores.py`, y `pruebas/abl/test_recorrido_lashe_wick_golden.py`, que cobra
por la RAM lo que cada página deja elegido.

# Cómo se ve hoy

Entrar a los vidcasts es un fundido; de ahí hasta el video, cada salto se hace
bloques mientras se apaga y se deshace mientras se prende, con el héroe nítido
encima.

# Cuándo deja de alcanzar

Un juego que use las transiciones de bloques, persianas o barridos, o el zoom
como efecto que se tiene que ver: ver `tasks/wishlist/las-otras-transiciones-de-rm2k.md`.
