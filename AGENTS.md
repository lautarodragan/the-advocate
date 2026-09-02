# Cómo se trabaja en este repo

Esto es lo que **no** se deduce leyendo el código. Todo lo demás está en
fuentes mejores, y hay que ir a ellas antes que a este archivo:

    ESTADO.md        dónde quedamos: lo que está a medias y lo que se supone
    justfile         qué se puede correr; los comentarios explican el porqué
    snes/LEEME.md    el port a SNES entero, con sus trampas y "Lo que falta"
    README.md        el juego original y el port a Mega Drive
    git log          los mensajes son largos a propósito: son el registro

Al empezar, leer `ESTADO.md`. Al terminar algo, actualizarlo —y mientras se
trabaja, no al final—.

## La regla que sostiene todo

Nada se da por bueno porque se vea bien: se compara pixel por pixel, a 15 bits,
contra una referencia en Python que sigue las mismas reglas. De ahí salen dos
obligaciones:

**Un cambio en la ROM y su cambio en la referencia van juntos.** Si sólo se
toca un lado, la comparación mide dos programas distintos.

Y ojo con el modo en que esto falla en silencio: **si los dos lados se
equivocan igual, la comparación da cero.** Ya pasó dos veces —los códigos de
comando de las puertas puestos de memoria, y la prioridad de OAM escrita mal
tanto en la ROM como en el conversor—. Su primo cercano es un camino que
ninguna prueba ejecuta, que es como sobrevivieron los tres errores del
intérprete de eventos: ahí no había con qué comparar.

**Decir "verificado" obliga a nombrar qué se corrió.** El commit `c64e4d9`
decía "Verificado: mapas 7 y 4 en cero" sobre un camino que ninguna prueba
ejecutaba, y detrás había tres errores encadenados. Si un camino nuevo no lo
cubre `snes-hitos`, el mensaje tiene que decirlo con todas las letras.

## Trampas del entorno

**`snes/src/mapdata.inc` es estado global.** Lo pisa cualquier `snes-convert`,
y no está en git. Una ROM ensamblada a mano se lleva los datos del último mapa
que se haya convertido, aunque el código sea el correcto: así se terminó
mirando el mapa 6 creyendo que era la demo del hito 12. **Las ROMs salen de una
receta, no de un `w65.py` suelto.**

**Mientras corre una tanda de regresión no se toca ningún fuente.** Cada receta
recompila desde `main.s`, así que editarlo a mitad de camino mezcla dos
versiones y el resultado no dice nada. Si hay que cambiar algo, se corta la
tanda y se vuelve a largar.

**Las tareas en segundo plano las mata taro.** Se pueden dejar corriendo; lo
que no hay que hacer es matarlas por cuenta propia. Si estorban, preguntar.

## Git

Los commits van directo a `main`. **El push lo hace taro**, con su YubiKey: no
intentarlo. Los mensajes van en castellano y explican el porqué, no el qué —el
diff ya dice el qué—.
