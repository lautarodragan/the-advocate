# Cómo se trabaja en este repo

Esto es lo que **no** se deduce leyendo el código. Todo lo demás está en
fuentes mejores, y hay que ir a ellas antes que a este archivo:

    ESTADO.md        dónde quedamos: lo que está a medias y lo que se supone
    justfile         qué se puede correr; los comentarios explican el porqué
    README.md        el juego original, el volcado a JSON, y el port a SNES
                     entero con sus trampas y "Lo que falta"
    data/README.md   el volcado a JSON visto desde adentro de data/
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

**`rom/build/cache/` es un caché en disco del conversor** —muestras BRR y
capas convertidas— y su clave lleva el hash de los fuentes, así que no hay que
borrarlo al tocar código. Lo único que pide es que cualquier cambio en lo que
se cachea se verifique con `SIN_CACHE=1`: las dos ROMs tienen que ser byte por
byte iguales. Ver `tools/cache_disco.py`.

**Mientras corre una tanda de regresión no se toca ningún fuente.** Cada receta
recompila desde `main.s`, así que editarlo a mitad de camino mezcla dos
versiones y el resultado no dice nada.

Para no tener que acordarse, está **`just snes-hitos-foto`**: saca una foto del
árbol con `git stash create` —incluye lo que no está commiteado—, la pone en un
worktree en `/extras` y corre la tanda ahí, así que se puede seguir editando.
Cuesta 0,034 s y 19 MB, y al terminar imprime el hash de la foto, que es lo que
después dice qué se probó y qué se agregó encima. Tres avisos: los archivos sin
trackear **no** entran en la foto —la receta avisa si ve alguno—, dos tandas a
la vez se pelean por CPU, y **se pelean por el directorio**: la receta arranca
borrando el worktree, así que una segunda tanda le borra el árbol a la primera
mientras corre y la deja con casos en rojo que no lo están. Con más de un
agente, cada uno con el suyo: `just snes-hitos-foto 4 /extras/hitos-foto-<quien>`.

**Las tareas en segundo plano las mata taro.** Se pueden dejar corriendo; lo
que no hay que hacer es matarlas por cuenta propia. Si estorban, preguntar.

## Sub-agentes

**Se usan, y son la forma preferida cuando dos trabajos no se pisan demasiado.**
Siempre con `isolation: "worktree"`: cada uno en su copia, así el `mapdata.inc`
—que es estado global— y las tandas no se mezclan.

Hasta el 2026-09-12 la regla era la contraria, y el porqué sigue valiendo como
advertencia: los hitos tocan `snes_convert.py`, `main.s` y `snes_expect.py`, que
son justo donde un merge mal hecho no se ve. Lo que cambió es que el trabajo se
volvió paralelizable de verdad —dos maneras distintas de resolver lo mismo, para
comparar— y que el setup ya está armado: worktrees y `pruebas-manuales/`. taro
aceptó el costo de los conflictos de git a cambio de eso.

Lo que hay que hacer siempre:

* **Traerle los builds al repo principal.** Los worktrees viven en `/extras`, que
  él no tiene montado en el host: una ROM que quede ahí adentro no la puede
  probar. Van a `pruebas-manuales/<nombre>/`, con un `LEEME.txt` que diga qué
  mirar y con qué limitaciones se chocó.
* **Pasarle al agente lo que ya está medido**, para que no lo vuelva a averiguar
  y para que no lo mida distinto.
* **Pedirle el límite medido y no la implementación forzada.** Cuando el punto
  es comparar dos caminos, saber dónde se rompe cada uno vale tanto como el
  código.
* **Avisarle que hay otros corriendo**: dos tandas a la vez se pelean por CPU y
  tardan, y matarlas por impaciencia arruina la corrida.
* **Pedirle que no deje nada esperando cuando termina.** Un sub-agente puede
  lanzar los suyos, y ésos **no aparecen** en la lista del que los mandó —sí en
  la interfaz de taro—, así que un ayudante colgado queda sin dueño: él lo ve y
  yo no puedo decirle de quién era. Lo mismo con los `sleep` largos para esperar
  una tanda: el 2026-09-12 uno dejó cinco armados y siguieron avisando que había
  terminado mucho después de haber entregado.

### Un merge sin conflictos no es un merge verificado

Dos ramas que cambian **la misma convención en archivos o líneas distintas**
mergean limpio y git no dice nada. Pasó el 2026-09-13: una rama hizo que
`paquete_cargar` leyera el mapa de `mapa_actual` en vez de A, la otra trajo un
llamador que se lo seguía pasando en A, y desde ese merge la pelea cargaba el
paquete de audio del mapa. Las dos pruebas que lo cobraban estuvieron en rojo
un día entero y **tres informes seguidos las dieron por "preexistentes"** —lo
eran, pero preexistente no quiere decir ajena—.

Así que al mergear una rama de sub-agente:

* **Correr `just pruebas` y la tanda sobre el árbol mergeado**, no sobre las
  ramas. Que cada una viniera en verde no dice nada del merge.
* **Un rojo heredado se bisecta, no se hereda.** Si una prueba está en rojo y
  nadie la rompió, apareció en algún lado: `git log -S` para saber cuándo nació
  y correrla en los padres del merge sospechoso. Cuesta veinte minutos.
* **Mirar a mano las firmas que las dos ramas tocaron**: quién pasa qué a quién
  y con cuántos bits.

### Cuando un sub-agente se corta

No se reanuda ni se le puede escribir. Al retomar, en este orden:

1. **Su rama y su worktree**: `git log --oneline worktree-agent-<id>`. Lo
   commiteado está entero; lo demás no existe.
2. **Los logs que haya dejado**, antes que su informe: una tanda en segundo
   plano puede haber terminado después del corte, así que su "quedó pendiente"
   puede ser viejo.
3. **Su transcripción**, en
   `~/.claude/projects/<proyecto>/<sesión>/subagents/agent-<id>.jsonl`. Son
   megas: se lee **del final hacia atrás, una entrada por vez**, mirando qué
   herramienta usó última. Nunca entero.
4. **Lo que dejó corriendo**: `pgrep -af "snes_correr|snes-hitos"` y
   `git worktree list`.

Y para el agente nuevo que lo reemplace: pasarle lo que el anterior dejó escrito
—commits y ESTADO.md— para que no vuelva a medir lo mismo.

## La trampa que más veces mordió

**`plx`, `ply` y `pla` dejan N y Z del valor que sacan de la pila**, y `sep`/`rep`
no tocan Z. Así que un `beq` o un `bpl` pegado a un `pl*` no está mirando lo que
uno cree: mira lo que salió de la pila.

Van cuatro veces, y las cuatro se veían como cualquier otra cosa menos como lo
que eran:

* ninguna ruta se movía nunca, porque la ranura 0 daba "bloqueado" siempre
  (el `cmp #0` de `main.s:7997`, con su comentario);
* la pantalla de título se quedó sin música un día entero, porque la pregunta
  "¿esta muestra está en la ARAM?" contestaba siempre que sí;
* `ConditionalBranch` por variable **tomaba siempre la rama**, con la variable
  en 12 y la condición pidiendo `>= 99`;
* `IsActorInParty` daba que todos los actores están en el grupo.

El arreglo es siempre el mismo: un `cmp #0` explícito entre el `pl*` y el salto.
Vale la pena hacer `grep` de `pl[axy]` seguido de un salto condicional cada vez
que algo "contesta siempre lo mismo".

## Git

Los commits van directo a `main`. **El push lo hace taro**, con su YubiKey: no
intentarlo. Los mensajes van en castellano y explican el porqué, no el qué —el
diff ya dice el qué—.
