---
name: "Mundo 4: Tasgarde, Eisen y el puente"
description: "El hito 4 de el-mundo-y-lo-que-sigue: el camino principal del capítulo del mundo en release, el alternar switches, el corte para borrar, y el fin de la demo en la entrada de Tangle Forest"
type: feature
---

# Qué

El hito 4 de `todo/el-mundo-y-lo-que-sigue.md`. Sale de `3c16a17`, con los
hitos 1 a 3 (`testing/mundo-1-*`, `mundo-2-sorbe`, `mundo-3-el-espacio`), y
mergea `main` con el mapa de debug (`455f9fc`).

* **La regla de mapas pasa a `MENOR_A = 105`**, por id, como contestó taro
  (pregunta 5). La exclusión crece a dieciséis —65 carpeta, 75 96 97 98
  inalcanzables, 104 de otro capítulo, y lo opcional: 67 71 72 de Yun Town,
  68 103 de Drust Camp— y los agregados quedan en 164, 259, 255 y, detrás de
  `CON_MAPA_DE_DEBUG`, el 900. El 70, el 73 y el 74, que eran mapas de prueba,
  pasan a ser del juego por la regla; el 255, por agregado. El 348 sigue de
  prueba: es la tienda opcional del mundo.
* **`ControlSwitches` que alterna**: sin opcode, una rama por switch con lo
  que ya hay (`_compilar_alternar`). El juego alterna uno solo, el 286, doce
  veces, en el 89 y el 93.
* **`ChangeScreenTransitions` al corte para borrar** (19, el 95 ev55) y a
  "ninguna" (20, el 93 ev4), que compila al corte: `TRANSICION_CORTE`, y
  `fundido_desde` arranca el fundido en su último cuadro de ida. El corte y
  "ninguna" para mostrar siguen sin compilar: nadie los pide.
* **El fin de la demo** pasa del 66 ev13 (vuelve al original: lleva a
  Tasgarde) al **66 ev19, la entrada de Tangle Forest**, y no al 18 como
  decía el encargo: ver abajo.
* **El contador de Fortitude** queda como deuda
  (`todo/el-contador-de-fortitude-no-se-ve.md`, con lo medido: el minijuego
  se puede perder). El minijuego se juega hasta el final sin él.

No hizo falta ningún opcode ni RAM lejana nueva: el 0x33 y $7E7A10-$7E7A2F
quedan libres. Ningún índice nuevo en tuplas de pruebas.

# El túnel está del otro lado del bosque

El plan daba a Tangle Forest por opcional porque ningún switch del camino
principal depende de él (`dependencias.py`). Pero depende el mapa: del lado
oeste del puente, el 66 es una isla que llega a la entrada de Tangle Forest
(43, 57) y a ningún lado más, y el túnel a Paradise (el 18, en (5, 64)) está
en otra, la del sudoeste, que sólo se alcanza por el bosque: 310 → 311 → 313
→ 312, que sale al 66 en (34, 56). Lo dice también el juego: al entrar,
Talan dice "If Vago's right, Paradise should be just a short journey to the
west, on the other side of this forest."

Así que la demo termina al entrar al bosque: el fork del 66 le saca el
`Teleport` al 310 a la página 1 del 19 y le pone el cartel del fin detrás de
los dos mensajes de Talan. El 18 quedó como el original (su `Teleport` al 105
no compila y la página no hace nada). **Tangle Forest es el hito siguiente del
camino principal**, no lo opcional; lo que pide está en el plan (el
`EraseEvent` del 311, las condiciones de cronómetro del 312). Anotado en
`todo/el-mundo-y-lo-que-sigue.md`, hito 4.

# Hecho y comprobado

* **Todas las páginas disparables de los mapas nuevos compilan**, contadas
  con `culpables.py` de `mundo-plan` contra la lista de `release`: 74, 85 a
  95, 99 a 102, 259 y 255. En el 66 no compilan cinco, las de los destinos
  que no están: el 67, el 68, el 105 (el 18, el túnel) y dos al 312.
* **`test_recorrido_capitulo_golden.py`**, nueva: de la entrada de Tasgarde
  al título. El guardia, el laboratorio, la historia de Eisen, **el minijuego
  del 95 jugado entero** —tres palancas y la escotilla, con saltos (eventos
  de acción que mueven al héroe) y escaleras (de contacto); la ruta termina
  con 4 de 99 de fortaleza—, la vuelta a Sorbe, el puente, el plan de Arden,
  debajo del puente con la pelea del séptimo crujido (con los HP en 999; los
  diez crujidos que hay que pisar salen de un BFS que los minimiza) y el fin
  de la demo. Cobra en la RAM los grupos de cada tramo y lo que dejan las
  transiciones: el corte al llegar al 95, el mosaico al volver a Sorbe y el
  fundido después de Vago. Sus capturas no están bendecidas.
* **`test_capitulo.py`**, nueva: goldens de la llegada al 74, al 85, al 95,
  al 259 y al 255, con `celdas_mal_dibujadas` en cero.
* **`test_borrar_con_el_corte`** (casos `transicion-corte` y
  `transicion-ninguna`): el brillo en cero y el mapa cargado en el primer
  tick del fundido, contra la rampa entera del zoom. **Se vio fallar** con
  `fundido_desde` ignorando el corte: llega a cero en el tick 23.
* **`test_recorrido_sorbe_golden.py`** termina ahora al entrar Dalia a
  Tasgarde, sola, al final de la ruta del auto.
* **Al mergear `main`** (el mapa de debug) chocó `AGREGADOS`: quedó
  `(164, 259, 255)` más el 900 detrás del flag. `just techos` otra vez sobre
  el árbol mergeado, por los cinco temas nuevos del capítulo.
* **El directorio del SPC700 se llena** con los temas del capítulo: la
  segunda tanda de `snes_music.copias` para por falta de entradas.
  `test_los_efectos_comparten_lugares_y_a_las_copias_les_sobran_entradas`
  pedía que no pasara; ahora es `test_los_efectos_comparten_lugares_del_directorio`
  y pide que los efectos ocupen menos entradas que las de siempre. Es un
  límite de cuánto se puede mejorar la música, y va a volver con cada tema.
* **`just cartuchos` y `just pruebas` en verde** sobre el árbol mergeado.

# Espacio

`just espacio release` sobre el árbol mergeado (con el mapa de debug):
115 de 124 bancos de datos, 9 libres; banco 0 137 B; banco 1 7.722 B; BSS 138
y ZEROPAGE 4; textos 142.138 de 262.144 B. Antes del merge, sin el mapa de
debug, eran 114 bancos, que es lo que el hito 3 midió para este camino.

# La música de antes, sin MSU-1

Medido par por par con `Banco`, como en `done/el-audio-despues-de-lashe-city.md`
(los argumentos de `build_varios` capturados de cada árbol y el reparto
rearmado; baja = más de 0,5 kHz), contra `main` 455f9fc1: **bajan 43 pares
(tema, instrumento) de 15 temas que ya estaban, y suben 51.** Los peores, golpes
de batería y algún instrumento de ~22 a ~14,4 kHz (Lunar_Pyramid, wb3shop,
escape_newyork, Deflector1, bubstix…). La lista entera está en el `LEEME.txt`
de las grabaciones.

No es el directorio lleno: la causa son los cinco temas nuevos, que comparten
muestras con los de antes y cambian qué copias hace `snes_music.copias`
(sacándolos de la captura, bajan 0; con sólo jackalstg2, 36; con sólo Story
Music, 26). Sin dejar que la segunda tanda copie para los temas nuevos queda
lugar en el directorio y bajan igual 42. Probado sin recuperarlos:
`TEMAS_APARTE` no aplica (cada tema nuevo ya va solo en su paquete); la
primera tanda más corta o más larga (`SE_DE_SIEMPRE` de 70 a 130: lo mejor
son 29, y cambia la tanda que taro aprobó); `COPIA_HASTA` 0,85 y 0,95; sin la
herencia de jackalstg2 ni el paquete del 259. **No se cambió nada**: por la
regla de taro, los quince temas están grabados antes y después, sin MSU-1, en
el directorio de audio del 2026-09-27 para el mundo 4, con un `LEEME.txt` que
dice qué escuchar. Recuperarlos pediría tocar cómo `copias` elige, que es su
propia tarea.

# Deuda

* **Los panoramas no se dibujan**: el puente (259), debajo (255), el 95, el
  94 y el 99 tienen uno y se ven en negro detrás del mapa, como todo panorama
  del port (`wishlist/panorama-del-mapa-2.md`).
* **El contador de Fortitude no se ve**: `todo/el-contador-de-fortitude-no-se-ve.md`.
* Borrar con "ninguna" es un cuadro negro y no el fundido del mapa viejo al
  nuevo: `divergencias/las-transiciones-del-teletransporte.md`.
* Una partida guardada en el save point del minijuego vuelve con el fundido
  en vez del corte (la transición no viaja en la partida): sólo se nota en el
  salto al principio cuando se acaba la fortaleza. Ver `TRANSICION_BORRAR` en
  `rom/src/ram_lejana.s`.
* El mapa de debug no tiene una puerta a Tasgarde ni al puente.

# Lo que no cubre `just pruebas`

* La rama de Saldra y la de AG7 en el puente: el plan de Arden es la página
  del 54; con Saldra (56) o AG7 (150) corren las del 13-14 y el 15-16 del
  259, que ninguna prueba juega.
* Las demás elecciones: "Not yet" en el puente (vuelve al 66 y prende el 851,
  con otra página después) y el camino por debajo con otros crujidos (hay
  peleas en 13, 20, 26…: la prueba juega sólo la del 7).
* Perder el minijuego del 95 (la paralela 56) y volver a empezarlo.
* Los save points del 74 y del 95.

# Qué tiene que probar taro

* **Escuchar los wav de antes y después** de los quince temas cuya música
  baja sin MSU-1 (ver "La música de antes"), y decir si se acepta.

* Desde el viaje de Dalia: Tasgarde, el guardia, el laboratorio, Eisen y el
  interruptor, y la historia de Eisen entera (86 a 94): que los mensajes y
  las cinemáticas se vean bien, y el salto del 93 al 95 (un cuadro negro en
  vez del fundido cruzado del original).
* **El minijuego del 95, sin ver la fortaleza**: se puede perder, y con la
  ruta directa sobran 4 de 99. ¿Se entiende qué hacer? ¿Y qué pasa al
  perder?
* La salida del minijuego (el corte), la simulación del trono (el mosaico) y
  la vuelta a Sorbe con Talan.
* El puente: la charla de los guardias, el plan de Arden, y **debajo del
  puente**: los crujidos, las peleas (¿se ganan con el grupo de una partida
  jugada?) y la salida del otro lado. El fondo del puente es negro
  (panorama).
* La entrada al bosque: los dos mensajes de Talan, el cartel del fin y la
  vuelta al título.
