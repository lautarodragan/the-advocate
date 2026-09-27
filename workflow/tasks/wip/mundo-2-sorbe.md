---
name: "Mundo 2: Sorbe y la curación"
description: "El hito 2 de el-mundo-y-lo-que-sigue: el reparto con la capa de encima de 256 tiles, ChangeEncounterSteps, los mapas 69 y 76 a 84 en release, el cartel del 81 y el fin de la demo en la entrada de Tasgarde"
type: feature
---

# Qué

El hito 2 de `todo/el-mundo-y-lo-que-sigue.md`, que tiene todo lo medido
antes. Sale de `3aac634`, con el hito 1 (`testing/mundo-1-el-66-entra.md`).

* **El sexto reparto**, `LAYOUT_VENTANA_ENCIMA`: la base de BG2 en `$5000`,
  la capa de encima en 256 tiles, 384 de fondo y 384 de sprite, para el 69
  (329 de fondo, 157 de encima, 283 de sprite). La ventana arranca en el índice
  256 de BG2 y no en el 128, así que el cartucho lleva un segundo plano de sus
  celdas, `ventana_celdas_256` (640 B), y `estampar_ventana` elige por la
  distancia entre la ventana y la base de BG2. `vram_layout` mira ahora
  también la capa de encima.
* **`ChangeEncounterSteps`**: OP_ENCOUNTER_STEPS (0x32) lleva el `1 / pasos`
  y los siete umbrales de las filas, calculados en el conversor. Los umbrales
  del mapa pasaron a copiarse a la RAM al entrar (`ENC_UMB`, $7E79C0), para
  que el comando cambie la chance y las filas juntas, como
  `Encuentros.poner_pasos`. En un mapa sin encuentros no hace nada; cargar
  otro mapa vuelve a los del mapa.
* **69 y 76 a 84 en `release`**, por `AGREGADOS`: entre el 66 y el 84 están
  Yun Town y Drust Camp, que no entran todavía, y el 74, que ya estaba como
  mapa de prueba.
* **El cartel "Meanwhile, in Lashe City"** del 81: un fork que cambia el
  `ShowPicture` de `MeanwhileLashe` por un `ShowMessage` con el mismo texto y
  saca los `MovePicture`, la espera y el `ErasePicture`. El texto sale de
  leer la imagen del juego.
* **El fin de la demo** pasa del 66 ev10 (Sorbe) al 66 ev13 (Tasgarde): el
  ev10 volvió a ser el del original.

# Hecho y comprobado

* **Ningún mapa que ya estaba cambia de reparto**: con el conversor del
  primer commit, el `mapdata.inc` de `release` y el de `test-special` salen
  iguales a los de `3aac634` salvo el bloque nuevo de `ventana_celdas_256`
  (diff de los dos `.inc`, que traen el registro de cada mapa: reparto,
  `BG12NBA`, direcciones de la ventana).
* **El 69 entra en el reparto nuevo** y la ventana sale bien: golden
  `sorbe-69-mensaje` (`test_sorbe.py`). **Se vio fallar con el error puesto**:
  forzando a `estampar_ventana` a usar siempre el plano de 128, esa golden
  difiere en el 26 % de los pixeles.
* **Todas las páginas disparables de los mapas nuevos compilan** (con
  `culpables.py` de `mundo-plan`): 69, 76 a 84. En el 66 no compilan siete,
  las de los destinos que no están (67, 68, 105, 259, 310, 312).
* **`test_pasos_de_encuentro.py`**, nueva: 10 pasos en el 66 (chance y
  umbrales), cero en el 66, 10 en el 5 (sin encuentros: no escribe nada), y
  la vuelta a los 65 del 66 al recargarlo. `test_batalla_golden.py::
  test_encuentro` cobra que el paso en que sale el encuentro de
  `test-special` no se movió al leer los umbrales de la RAM.
* **`test_recorrido_sorbe_golden.py`**, nueva: del mundo (rama de "no" a
  Wick, el 162, que es la del tobillo) a Sorbe, la vieja y el guardia, la
  montaña y la pelea con Vago, la curación, la historia y el cartel, la
  oficina, la fábrica, afuera, el transporte, y el viaje de Dalia hasta el
  fin de la demo y el título. **La pelea con Vago se gana con los HP del
  grupo puestos en 999** desde el arnés: Talan en nivel 1 y Arden en 3, que
  es lo que da una partida nueva, pierden. Sus capturas no están bendecidas.
* **`test_sorbe.py`**, nueva: goldens de la llegada al 69, al 76 y al 81, con
  `celdas_mal_dibujadas` en cero, y la del mensaje en el 69.
* **El viaje de Dalia termina solo en el fin de la demo**, sin caminar: la
  ruta del auto termina justo sobre la entrada de Tasgarde, y RPG_RT, al dar
  el último paso de una ruta, la cancela y mira el evento bajo el héroe
  (`Game_Character::UpdateMovement` y `Game_Player::UpdateMovement` de
  easyrpg); el evento queda esperando a que termine la página del viaje. La
  ROM hace lo mismo.
* **La carrera** termina ahora al entrar a Sorbe Village (el 69).

# Espacio

(al final, con el método de `AGENTS.md`)

# Deuda

* **La pelea en el mundo y la de Vago salen sin fondo.** Es de
  `todo/todos-los-fondos-en-el-msu-1.md`, que va en paralelo.
* **El cartel sale en la ventana de siempre**, abajo: el `MessageOptions`
  del original (transparente y al medio) no lo hace la ROM, igual que en el
  resto del juego.
* La rama de Wick (el 164, el tobillo curado por su cirujano) no la juega
  ninguna prueba: en Sorbe, Vago espera en la puerta de su casa (69 ev18) y
  lleva directo al 81.
* Yun Town, Drust Camp y Tangle Forest siguen afuera: sus entradas del mundo
  no hacen nada.

# Qué tiene que probar taro

(al final)
