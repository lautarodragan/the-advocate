# Qué

Un `EnemyEncounter` con `defeat_mode` 0 que se pierde, un encuentro al azar
perdido, o un `GameOver`, mandan en RM2k a `Scene_Gameover`: la imagen de Game
Over del proyecto, su tema, y al apretar una tecla la pantalla de título.

Desde el 2026-09-28 la ROM lo hace —ver `rom/src/game_over.s`—: la imagen que
nombra el `System` del LDB, buscada en `GameOver/` del juego y después en la
del RTP (`ABL_RTP_DIR`), el tema de Game Over del sistema, 80 cuadros de
fundido de entrada y 80 de salida, y la pantalla de título. Hasta ese día
volvía al arranque con un `jml reset`, sin imagen ni tema: era este archivo,
con otro nombre.

Lo que queda distinto:

* **El tema de Game Over no suena en el mensaje de la derrota.**
  `Scene_Battle_Rpg2k::ProcessSceneActionDefeat` lo prende antes de mostrar
  "defeat", **tenga o no la pelea manejador de derrota**; la ROM sigue con el
  tema de la pelea hasta la pantalla. Prenderlo ahí pediría su tema en el
  paquete de la pelea, que ya está lleno —ver `PAQUETE_BATALLA` en
  tools/port/eventos.py—.
* **La imagen se escala a 256x224**, igual que la de título: el aspecto no es
  el del original. Ver `titulo.py`.
* **START también la cierra**, además de A, como en la pantalla de título:
  en una consola la pantalla se pasa con START.
* **El mapa se funde en 32 cuadros y no en 35**: dos por nivel de brillo, que
  son dieciséis.

# Medido

La imagen: `System.gameover_name` en el ABL es `GameOver`, y el juego trae en
`GameOver/` un solo archivo, `ablgameover.png`, **que no nombra nadie**. Así
que RM2k muestra el `GameOver.png` del RTP: comprobado en el original con
Wine el 2026-09-28, con un mapa de arranque que llama a `GameOver` —la
captura del original se ve igual que la golden `game-over`, salvo el
escalado—.

El tema, `GameOver3`, también es del RTP: desde ese día la música se busca en
el juego y después en el RTP, como en RM2k, y las pistas de MSU-1 de los temas
del RTP que nombra el `System` van numeradas detrás de las del juego: ver
`numeros_de_pista` en tools/audio/snes_music.py.

Lo cubren `pruebas/rpgmaker/test_game_over.py` —los tres caminos, la golden,
la tecla y el título— y `test_game_over` en `test_cores.py`.

# Cuándo deja de alcanzar

Un juego donde perder sea parte de la trama con el tema de Game Over sonando
en la derrota y la historia siguiendo por el manejador: ahí el mensaje de la
derrota suena con el tema de la pelea.
