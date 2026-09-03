# Cómo se trabaja en este repo

Esto es lo que **no** se deduce leyendo el código. Todo lo demás está en
fuentes mejores, y hay que ir a ellas antes que a este archivo:

    ESTADO.md        dónde quedamos: lo que está a medias y lo que se supone
    justfile         qué se puede correr; los comentarios explican el porqué
    rom/LEEME.md     el port a SNES entero, con sus trampas y "Lo que falta"
    data/README.md   el volcado a JSON: qué es y de dónde sale
    README.md        el juego original y cómo se lo lee
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

## Dónde corre esto

Adentro de un contenedor de podman que taro levanta con `box`, una función
suya de nushell: Arch —igual que el host— con el repo montado en
`/host/abl-sg`. **Los archivos del repo son los de verdad**: lo que se escribe
acá queda escrito en su disco. El resto del sistema es descartable, y por eso
él trabaja en auto mode y no aprueba comando por comando; lo que revisa es el
`git diff`.

Lo que el contenedor cambia en la práctica:

* **No hay podman adentro.** Las recetas que lo usan —todo el port a Mega
  Drive, y `snes-validar`— van desde el host. El justfile lo aclara en cada
  una.
* **`.git/config` y `.git/info` están montados de sólo lectura**, y
  `.git/hooks` es un tmpfs vacío: `git config` falla y ningún hook corre.
* **No hay puertos publicados.** Nada que se sirva acá adentro se ve desde el
  host.
* **`/extras` sobrevive a la sesión**, igual que los paquetes instalados:
  `/root`, `/usr`, `/var` y `/etc` son volúmenes con nombre, no capas de la
  imagen.

`/extras` es de **uso libre**, y ésa es la manera de conseguir material de
referencia: se clona o se descarga acá adentro en vez de montar algo del host,
que revela menos y da más margen. Hoy tiene:

    /extras/abl-rm      el juego original. Es lo que lee GAME_DIR
    /extras/rtp         el RTP de Don Miguel, sin el cual faltan 22 assets
    /extras/ref         liblcf, easyrpg-player y Game-Decompilations
    /extras/soundfonts  de donde salen las muestras
    /extras/capturas    donde taro deja capturas para que yo las mire

Las capturas van ahí y no a `/tmp` por una razón concreta: el contenedor corre
con `--rm --replace`, así que `/tmp` se muere con él y `/extras` no. Antes esto
era un directorio `screenshots-manuales/` adentro del repo, que ensuciaba el
árbol con archivos que nunca fueron del proyecto.

**Los repos de `/extras/ref` están clonados adentro y no son los del host.**
`liblcf` es de donde se genera `tools/event_codes.py`: los códigos de comando
de RM2k salen de ahí y de ningún otro lado, porque la primera versión del
filtro de puertas los puso de memoria y tres estaban mal. Si hace falta algo
que no se consigue desde acá, se le pide a taro que lo copie a `/extras`.

El host y el contenedor son casi simétricos a propósito, así que un comando
que se le pida a taro —`mednafen rom/build/abl.sfc`, una receta de `just`—
suele valer tal cual de los dos lados. Las versiones pueden driftear, porque
los paquetes no se comparten.

Lo que sí o sí es del host: el `git push`, cualquier cosa con podman, el
EverDrive por USB, y **ver y escuchar la ROM de verdad** — acá adentro se
captura con Xvfb y el audio se graba a un wav en vez de sonar.

## Recetas o scripts descartables

La decisión no es de seguridad: es el costo de mantener el script contra lo que
rinda tenerlo. Una receta por cada script convertiría al justfile en ruido.

**Receta de `just`** cuando se va a volver a correr: si entra en una cadena de
verificación, si conviene que quede escrito cómo se armó algo, o si taro lo va
a correr desde el host. `snes-evento` nació así, y de paso dejó de existir la
ROM armada a mano que mandó a mirar el mapa equivocado.

**Script descartable** cuando contesta una pregunta de una sola vez: cuántos
mapas tienen tal cosa, en qué offset de la ROM cae tal byte. Va al scratchpad
y se tira.

## Trampas del entorno

**`rom/src/mapdata.inc` es estado global.** Lo pisa cualquier `snes-convert`,
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
