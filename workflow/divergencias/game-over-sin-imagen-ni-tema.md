# Qué

Un `EnemyEncounter` con `defeat_mode` 0, o un `GameOver`, manda en RM2k a
`Scene_Gameover`: la imagen de Game Over del proyecto, su tema, y al apretar una
tecla la pantalla de título.

La ROM hace la última parte y no las dos primeras: vuelve al arranque con un
`jml reset` —ver `BATALLA_PERDER` en `tools/port/eventos.py` y `op_battle` en
`rom/src/interprete.s`—, o sea a la pantalla de título si el cartucho la lleva, con
la partida guardada esperando en la SRAM.

* **La imagen no se dibuja**: una de 320x240 pediría prestarle una capa al
  cartel, ver `tasks/wishlist/sistema-de-imagenes.md`.
* **El tema de Game Over no suena**: sería un tema más en la lista de todos los
  cartuchos con pelea, y lo que se gana es el silencio de un segundo antes del
  arranque.

# Medido

Son **15 páginas del juego** con `defeat_mode` 0, entre ellas las tres del jefe
de los Rat Tracks; todas son peleas normales, ninguna se tiene que perder para
que la escena siga. Lo cubre `pruebas/rpgmaker/test_game_over.py`.

El reinicio cuesta los casi dos segundos del arranque, porque vuelve a subir el
driver y las muestras al SPC700, y no es prolijidad: el `jml reset` no resetea
al SPC700, así que sin volver a arrancarlo del todo el juego se colgaba.

# Cómo se ve hoy

Perder lleva al título. Se pierde el progreso desde el último guardado, que es
lo mismo que en RM2k con "Continue"; lo que no hay es seguir desde el título
con "New Game" sabiendo que perdiste.

# Cuándo deja de alcanzar

Un juego donde perder sea parte de la trama: una pelea que se tiene que perder
para que la escena siga.
