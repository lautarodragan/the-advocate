---
name: "Todos los temas tienen pista de MSU-1"
description: "Hoy sólo algunos temas tienen pista (PISTAS_MSU); taro quiere que todos, siempre"
type: feature
---

taro, el 2026-09-26: **todos los temas siempre deberían tener su versión
MSU-1**. Hoy la tienen los de `PISTAS_MSU` (`tools/audio/snes_music.py`), y
los informes de audio de estos días hablaban de "los temas que tienen pista"
como si fuera normal que algunos no.

Qué implica:

* Renderizar la pista de cada tema que no la tiene (`tools/audio/msu.py`, con
  fluidsynth y el SoundFont, o el reemplazo de audio si hay), y que la lista
  deje de escribirse a mano: **todo tema que entra en el cartucho tiene pista**,
  y una prueba (o una aserción del conversor) que falle si alguno no la tiene.
* El número de pista de cada tema lo decide hoy `PISTAS_MSU`; con todos, la
  numeración puede salir del índice del tema.
* Consecuencias en la ROM: con MSU-1 **ninguna** muestra de música se sube
  (`done/` o `testing/con-msu-1-no-se-suben-las-muestras-del-tema.md`), así
  que la ARAM entera queda para los efectos; conviene hacerlo **después** de la
  tarea de los efectos con MSU-1, o coordinado con ella.
* Las pistas van a `/shared/msu/` con `just entregar --actualizar-msu`
  (cambia la huella).
* Tocar `msu.py` rehace todas las pistas: se hace una vez.
