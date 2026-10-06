# Qué

`EraseEvent` **está** —`OP_ERASE_EVENT`, con `FLAG_ERASED` en `ev_flags`—: el
evento que lo corre no se dibuja, no bloquea y ninguna de sus páginas arranca,
hasta que el mapa se vuelve a cargar; si el que lo corre es una página
paralela, ahí termina. Y deja afuera lo que RM2k sí hace o sí cuida:

* **No viaja en la partida.** El borrado vive en `ev_flags`, que
  `clear_waits` limpia en cada carga de mapa, y cargar una partida carga el
  mapa: un evento borrado vuelve. Es el mismo hueco que
  `divergencias/la-partida-no-guarda-los-eventos.md`.
* **Una ruta forzada que ya lo mueve no se corta.** Se le saca la ruta de su
  página y se esconde su fila, pero un `MoveEvent` forzado que estuviera
  caminando sigue en su ranura y la dibuja de nuevo.
* **Un evento sin gráfico no deja de ocupar su celda** para quien mira
  `ev_pos_buf` —el botón de acción mira la celda y no encuentra página—; no
  hay ninguno en el juego que lo necesite.
* **Se borra "este evento" y nada más.** `EraseEvent` en RM2k no lleva
  parámetros, así que es lo único que hay; en un común no hace nada, igual que
  allá, y después de un salto a otro mapa tampoco.

# Medido

`rm2k-snes-events culprits --every-map` sobre Desert Nightmare: `EraseEvent`
era el comando que más páginas dejaba afuera solo (127 de las 157 que lo
usan), y ya no deja ninguna. Las 157 son paralelas sin gráfico.

# Cómo se ve hoy

No se ve. `pruebas/rpgmaker/test_borrar_evento_de_verdad.py`, en ABL, cobra lo
que el evento de prueba permite mirar —que una página de primer plano sigue,
que las otras no arrancan, y que recargar el mapa lo trae de vuelta—; lo que
se dibuja, lo que bloquea y la paralela que se corta lo cubre jugar el
cartucho de un juego que borra eventos con gráfico.
