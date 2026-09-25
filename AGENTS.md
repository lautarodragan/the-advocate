# Cómo se trabaja en este repo

Esto es lo que **no** se deduce leyendo el código. Todo lo demás está en
fuentes mejores, y hay que ir a ellas antes que a este archivo:

    workflow/        dónde quedamos, y su README explica cada carpeta
    tasks/todo/      lo decidido y sin empezar; `wip/` lo que se está
                     haciendo, `testing/` lo hecho que taro tiene que jugar,
                     `done/` lo terminado
    decisiones/      las decisiones tomadas que siguen valiendo, una por
                     archivo: para no rehacerlas ni contradecirlas
    divergencias/    dónde la ROM no hace lo que RM2k hace, con lo medido
    tasks/wishlist/  lo que nos gustaría hacer y nadie está haciendo
    justfile         qué se puede correr; los comentarios explican el porqué
    README.md        el juego original, el volcado a JSON, y el port a SNES
                     entero con sus trampas y "Lo que falta"
    docs/            RM2k, la consola, cómo funciona el port hoy, y los
                     estudios fechados: su README dice qué va en cada carpeta
    data/README.md   el volcado a JSON visto desde adentro de data/
    DITTO.md         qué es Ditto, por qué existe acá y en qué estado está
                     la idea de que los JSON sean la fuente de verdad
    git log          los mensajes son largos a propósito: son el registro

Al empezar, mirar `workflow/tasks/wip/` y `testing/`, que es dónde quedamos. La
tarea se escribe **mientras se trabaja, no al final**, y al terminar se mueve de
carpeta.

## Dónde va cada cosa que uno quiere dejar escrita

Dos reglas, de taro, el 2026-09-15. Las dos salen del mismo problema: lo que se
escribe a mano en un documento envejece sin avisar, y lo que vive lejos del
código no lo lee nadie cuando hace falta.

**Un número se escribe sólo si es propiedad del hardware o del formato.** Los
32.704 bytes del banco 0, los tiles de 8x8, el color de 15 bits, los 64 KB de
ARAM: ésos no cambian. **Un número que describe el estado de nuestro trabajo no
va escrito en ningún lado, va el comando que lo imprime**: cuántos casos
pasan es `just pruebas`, cuánto pesa el cartucho lo dice el build.

El 2026-09-15 había **tres números distintos para la misma pregunta** —281, 314
y 332 de 489— en dos archivos, los tres viejos, y el real era 350. Uno de ésos
lo había escrito yo una hora antes.

**Un porqué se queda en el README sólo si es una decisión de arquitectura que
no tiene una línea de código donde vivir**: por qué modo 3 fijo, por qué LoROM,
por qué los translúcidos van horneados. **Un porqué que protege una línea
concreta va como comentario en esa línea.** El razonamiento es de taro y es
difícil de discutir: nadie que esté editando una rutina va a buscar la razón en
un README de cinco mil líneas, así que ahí no protege a nadie.

Y si el error no es de los que se vuelven a cometer, no va a ningún lado: el
`git log` ya lo tiene.

**Se asume que todo el código escrito es intencional**, sabiendo que puede no
serlo. No se documenta cada caso intencional, porque los no intencionales son
la excepción. Ante algo que parece un error, el primer paso es **`git blame`**:
sirve para separar "esto es a propósito" de "esto se rompió en algún cambio",
que es la diferencia entre tocarlo con confianza y tocarlo a ciegas. Recién con
la intención demostrada —y demostrada errónea, o parcialmente errónea— se
arregla.

Al revés también: **si uno escribe a propósito algo que se ve raro, lo aclara
ahí mismo.** El ejemplo de taro: "acá la variable que se llama NUMBER es de
tipo string y no number, por contraintuitivo que sea, pero no se puede arreglar
porque así lo espera una API que no controlamos". Eso es lo que un comentario
tiene que decir; lo que el código ya dice, no.

## Los proyectos independientes están en inglés

Todo este repo va en castellano —comentarios, documentación y mensajes de
commit—, **salvo los directorios que son proyectos aparte**, que van en inglés
de punta a punta: código, comentarios, nombres de pruebas y README. Al
2026-09-16 son cuatro, y desde el 2026-09-19 viven adentro de `tools/`, al lado
de los paquetes de Python del port —ver `tools/README.md`—:

    tools/ditto/     lee y escribe los formatos de RPG Maker 2000
    tools/protocol/  declara un bytecode y genera las constantes de sus dos lados
    tools/gunter/    Gunter: códec BRR y lector de SoundFont
    tools/voodoo/    Voodoo: de una imagen a tiles, paletas y tilemap

Hasta ese día había un quinto, `w65/`, el ensamblador de 65816. Lo reemplazaron
`ca65` y `ld65`, del proyecto cc65: ver "Dónde corre esto".

**Se consumen desde el PATH, no desde `target/release`.** Se instalan con
`just herramientas` —`cargo install --locked --path …`— y a partir de ahí son
herramientas del sistema, como `python3` o un core de libretro: **ningún script
ni prueba de este juego llama a `cargo`**. Es de taro, el 2026-09-15, y lo que
evita es que cada corrida de la tanda quede atada al toolchain de Rust.

`CARGO_ROOT` dice dónde instalan; por omisión `/usr/local`, que acá está en el
PATH. Desde el host, `CARGO_ROOT=~/.cargo`.

La regla para saber si algo va adentro de uno de ésos es una sola: **si no
necesita saber nada de este juego, es un proyecto aparte y va en inglés.**
Adentro no se nombra a ABL ni al port, y sus flags son ingleses aunque el
equivalente de `tools/` los tenga en castellano (`--include`, `--symbols`).
Hablar de la consola *como formato* —el SPC700, el 65816— sí está bien: eso es
el dominio, no el proyecto.

No es un descuido que corregir: si alguien lo "arregla" al castellano, deshace
la decisión. **Los mensajes de commit siguen en castellano también para esos
directorios**: son del repo.

Y **lo que esas herramientas generan va en inglés también**, aunque caiga en
`tools/` o en `rom/src/`: es su salida, no fuente de este árbol, y dice arriba
que es generada y de dónde. El 2026-09-14 la regla era la contraria —"el idioma
del árbol donde cae"— y duró un día: al generalizar el generador para el
segundo bytecode quedó claro que hacerlo hablar castellano lo ata a este repo.

Las pruebas de esos proyectos no dependen del juego. Ditto recibe el corpus por
`DITTO_CORPUS`, y sin esa variable las que lo necesitan se saltean con un
mensaje; `tools/protocol/`, `tools/gunter/` y `tools/voodoo/` no necesitan nada.

### `tools/voodoo/` no decide colores, y eso no se arregla

`tools/voodoo/` convierte una imagen **que ya entra**: recibe PNG indexados cuyos
índices son entradas de CGRAM, y si la imagen rompe el formato, dice dónde y no
la arregla. Qué colores se pierden y cómo se agrupan en paletas lo decide el
asignador, `tools/port/asignador.py`, que corre **antes** y deja lo que decidió como
imágenes en `rom/build/<cartucho>/asignador/`. La prueba para saber de qué lado
va algo es si cambia un pixel de lo que se ve.

Es de taro, el 2026-09-17. Voodoo tuvo un `--merge` que fusionaba colores; se
sacó para que haya una sola respuesta a "qué color se perdió". Devolverle
cualquier decisión de ésas deshace el diseño, aunque sea cómodo.

## El número de un opcode se elige en la declaración

En `tools/protocol/` y en ningún otro lado. Hay dos declaraciones:
`tools/protocol/events.toml`, el bytecode que interpreta `correr_codigo`, y
`tools/protocol/music.toml`, el stream que lee `irq_musica`. Los dos caen en el mismo
espacio de símbolos del ensamblador, así que dos opcodes de bytecodes distintos
pueden compartir **número** pero no **nombre** —por eso `OP_FIN` se llama
`OP_DONE`: `OP_END` ya era del stream de música—, y eso lo cuida una prueba.

Antes el de eventos lo declaraba `tools/port/eventos.py` y le llegaba al intérprete
adentro de `mapdata.inc`, que es cómo dos ramas pudieron elegir el mismo sin
que git viera nada; el de música estaba escrito a mano de los dos lados.
(`mapdata.inc` sigue existiendo y `main.s` lo sigue incluyendo: lo que salió de
ahí es el bytecode, no las tablas del mapa.) Al repartir trabajo entre
sub-agentes sigue valiendo repartir los números de antemano, pero ahora la
colisión es un conflicto de git en un archivo y no un bug que viaja adentro de
un merge.

## `git blame` y los cambios mecánicos

`.git-blame-ignore-revs` lista los commits que `git blame` tiene que saltear:
renombres masivos y reformateos, que sin esto contestan "fue el renombre" en
cada línea que tocaron. El criterio para meter uno es que su cambio **no pueda
alterar el comportamiento**, y en este repo eso se demuestra, no se supone: los
dos que hay adentro tienen las dos ROMs saliendo byte por byte iguales.

Si no funciona no esperado, podemos pasarlo como argumento: git blame --ignore-revs-file .git-blame-ignore-revs <archivo>.

Y lo que **no** arregla: sólo sirve para `blame`. Para `git log` y `git diff`
no hay equivalente, así que para rastrear cuándo cambió algo sigue valiendo
`git log -S '<texto>'`, que busca por contenido y por eso ignora el ruido solo.

**`rom/src/` atraviesa el corte de `main.s` sólo con
`git blame -C --diff-algorithm=histogram <archivo>`.** El 2026-09-25 `main.s`
se partió en un archivo por subsistema, y el corte **no** está en
`.git-blame-ignore-revs` porque no sirve: ignorar un commit le pasa la culpa
al mismo archivo en el padre, y ninguno de los nuevos existía. Sin opciones,
`blame` contesta "fue el corte" en cada línea; con `-C` solo, casi igual,
porque el diff por omisión (Myers) aparea las líneas repetidas —`rts`,
`.endproc`, blancos— con las primeras que encuentra en treinta mil líneas y
los trozos quedan más cortos que el mínimo de `-C`. Con histogram, que ancla
en las líneas únicas, **cada línea sale con el mismo commit que daba el
`main.s` de antes**: medido sobre las treinta y cuatro mil. `git log
--follow` no cruza el corte; `git log -S` sí, porque busca en todos los
archivos.

Los IDE que no dejan pasarle opciones a `blame` —el annotate de JetBrains—
lo hacen sólo si el git del host tiene `diff.algorithm=histogram` en su
configuración global (`git config --global diff.algorithm histogram`), y
con su opción de detectar movimientos entre archivos, que es la `-C`. Acá
adentro `.git/config` es de sólo lectura, así que eso lo configura taro del
lado del host.

## La regla que sostiene todo

Nada se da por bueno porque se vea bien: **se compara pixel por pixel, a 15
bits**, que es la profundidad real de la consola. Lo que cambió el 2026-09-16
es contra qué.

Hasta ese día se comparaba contra una **referencia en Python** que hacía lo
mismo que la ROM. Hoy se compara contra **capturas congeladas** —las goldens de
`pruebas/golden/tanda/`, que son lo que la ROM dibujaba el día que la tanda
estaba en verde—. De ahí salen tres obligaciones, y una de ellas es nueva.

**Cambiar una golden es un acto deliberado.** Va a git, se mira, y el commit
explica por qué el render cambió. Si regenerarlas fuera automático, o si la
tanda lo hiciera sola, dejarían de cumplir ninguna función. Es lo mismo que
cualquier snapshot testing.

**Una golden caza regresiones, no errores de nacimiento.** Una feature que sale
mal desde el día uno hornea el bug adentro de su golden y la prueba lo defiende
a partir de ahí. No es teórico: el 2026-09-15 aparecieron **tres goldens del
recorrido con un tinte pegado**, y dos de ellas **pasaban** —una con 10,3% de
diferencia bajo un tope del 15%—. Lo que contrapesa esto es que taro juega.

**Y hay una clase de error que ninguna golden puede ver, porque el emulador que
la sacó tampoco la ve.** Para eso está `pruebas/rpgmaker/test_cores.py`: corre el mismo
cartucho en **snes9x y en bsnes** y compara las dos capturas entre sí. bsnes
arranca la WRAM con basura y snes9x en cero, así que una diferencia significa
que la ROM depende de memoria sin inicializar. Da rojo **cuatro de cada cinco
corridas** con el error puesto —medido—, porque la basura tiene que caer en un
valor que rompa.

Lo que **se fue** con la referencia: la obligación de mover los dos lados
juntos, y el modo de falla de "si los dos lados se equivocan igual, la
comparación da cero" —que mordió dos veces, con los códigos de comando de las
puertas y con la prioridad de OAM—. Ya no hay dos lados.

Lo que **sigue entero** es su primo, y es el que más veces mordió: **un camino
que ninguna prueba ejecuta**. Así sobrevivieron los tres errores del intérprete
de eventos, así estuvo rota meses la receta que comparaba contra `ca65`, y así
una prueba de tropas leyó el chunk equivocado sin fallar nunca.

**Decir "verificado" obliga a nombrar qué se corrió.** El commit `c64e4d9`
decía "Verificado: mapas 7 y 4 en cero" sobre un camino que ninguna prueba
ejecutaba, y detrás había tres errores encadenados. Si un camino nuevo no lo
cubre `just pruebas`, el mensaje tiene que decirlo con todas las letras.

## Dónde corre esto

Adentro de un contenedor de podman que taro levanta con `box`, una función
suya de nushell: Arch —igual que el host— con el repo montado en
`/host/abl-sg`. **Los archivos del repo son los de verdad**: lo que se escribe
acá queda escrito en su disco. El resto del sistema es descartable, y por eso
él trabaja en auto mode y no aprueba comando por comando; lo que revisa es el
`git diff`.

Lo que el contenedor cambia en la práctica:

* **No hay podman adentro**, y desde el 2026-09-19 ninguna receta lo usa: el
  port a Mega Drive, `audio-validar` y el `rom/Containerfile` se fueron.
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
    /extras/ref/cc65    compilado acá: de ahí salen `ca65` y `ld65`

Las capturas van ahí y no a `/tmp` por una razón concreta: el contenedor corre
con `--rm --replace`, así que `/tmp` se muere con él y `/extras` no.

**`ca65` y `ld65` se compilan acá adentro, y eso fue una decisión.** No están
empaquetados en Arch, y hasta el 2026-09-15 la regla era no compilar fuentes de
internet en la misma caja donde vive el repo: `audio-validar` corría `ca65` en un
podman aparte, desde el host. taro dio esa regla por caduca —venía de cuando
cada comando se envolvía en su propio contenedor— así que `cc65` se clonó y se
compiló en `/extras/ref/cc65`, y los binarios están enlazados en
`/usr/local/bin`. Si el contenedor se recrea desde la imagen, se rearman con
`git clone --depth 1 https://github.com/cc65/cc65.git` y `make -j8 bin`.

Lo que se comprobó del clon antes de usarlo, para que el próximo no lo dé por
descuido ni lo repita: el repo **no trae binarios commiteados** —los de `bin/`
salen de sus 989 fuentes de C—, el build **no baja nada de internet** ni escribe
fuera de su directorio, y `ca65` usa **55 símbolos externos y ninguno es de red
ni de ejecución** —no importa `socket`, `connect`, `exec*`, `fork`, `system`,
`popen` ni `dlopen`—. Lo que **no** se comprobó: los tags del proyecto no están
firmados, el clon es `--depth 1` y no tiene historia, y nadie leyó los 989
archivos. Y el build corrió con red y como root: auditar después no deshace eso.

**La defensa que no dependía de la auditoría se fue con `w65`.** Mientras
existió, la salida de `ca65` se comparaba byte por byte contra la nuestra; el
2026-09-16 las dos ROMs de referencia salieron idénticas y `w65` se borró.
Desde ahí `ca65` y `ld65` son los que arman, y lo que cobraría un binario
alterado es lo mismo que cobra cualquier regresión: las goldens y
`test_cores.py`. Recompilarlos sin mirar deja de ser inocuo.

**Los repos de `/extras/ref` están clonados adentro y no son los del host.**
`liblcf` es de donde sale el esquema de Ditto —y con él los defaults que
`data/` trae ya aplicados— y de donde salen los códigos de comando de RM2k
(`tools/rpgmaker/event_codes.json`): salen de ahí y de ningún otro lado, porque la primera
versión del filtro de puertas los puso de memoria y tres estaban mal. Si hace
falta algo que no se consigue desde acá, se le pide a taro que lo copie a
`/extras`.

El host y el contenedor son casi simétricos a propósito, así que un comando
que se le pida a taro —`mednafen rom/build/release/abl.sfc`, una
receta de `just`— suele valer tal cual de los dos lados. Las versiones pueden driftear, porque
los paquetes no se comparten.

Lo que sí o sí es del host: el `git push`, cualquier cosa con podman, el
EverDrive por USB, y **ver y escuchar la ROM de verdad** — acá adentro se
captura con Xvfb y el audio se graba a un wav en vez de sonar.

## Recetas o scripts descartables

La decisión no es de seguridad: es el costo de mantener el script contra lo que
rinda tenerlo. Una receta por cada script convertiría al justfile en ruido.

**Receta de `just`** cuando se va a volver a correr: si entra en una cadena de
verificación, si conviene que quede escrito cómo se armó algo, o si taro lo va
a correr desde el host. `evento` nació así, y de paso dejó de existir la
ROM armada a mano que mandó a mirar el mapa equivocado.

**Script descartable** cuando contesta una pregunta de una sola vez: cuántos
mapas tienen tal cosa, en qué offset de la ROM cae tal byte. Va al scratchpad
y se tira.

## Trampas del entorno

**`rom/src/` es un solo ensamblado partido en muchos `.s`.** `main.s` los
pega con `.include`, y el orden de esa lista es el orden en la ROM: partir es
gratis, mover no. Lo que eso implica —cada archivo hereda los anchos y el
segmento del anterior, las anónimas se resuelven sobre el texto pegado— lo
dice el encabezado de `main.s`, que es donde lo va a ver quien agregue un
archivo. Hasta el 2026-09-25 era un solo archivo; se partió byte por byte
igual, y por eso hay rutinas que quedaron en el archivo del vecino: moverlas
es un cambio de ROM, y va en su propio commit.

**Un `.inc` generado nunca va en `rom/src/`.** `ca65` busca los
`.include` primero en el directorio del archivo que incluye y recién después en
los `-I`, así que un `mapdata.inc` en `rom/src/` taparía al del cartucho sin
avisar: la ROM saldría con los datos de otro. Hasta el 2026-09-16 la receta
`convert` escribía justo ahí —era "estado global", y así se terminó mirando el
mapa 6 creyendo que era la demo del hito 12—; hoy cada cartucho escribe el suyo
en su directorio de `rom/build/`, y `tools/ensamblado/ensamblar.py` se niega a armar si
encuentra uno en `rom/src/`. **Las
ROMs salen de una receta, no de un `ca65` suelto.**

**Cuánto le sobra al banco 0 depende de qué cartucho se arme.** Las tablas que
emite el conversor viven ahí, así que el número cambia con la lista de mapas:
el 2026-09-13 la misma pregunta se contestó **81**, **1** y **85** bytes en la
misma tarde, y las tres estaban bien —cada una con un `mapdata.inc` distinto—.
Así que al decir "quedan N bytes" hay que decir con cuál.

**El que manda es el más apretado, y no suele ser la demo**: los cartuchos
de prueba llevan más mapas que `abl`, así que medir sólo en ella dice que hay
lugar cuando no lo hay. Cuál es el más apretado cambia, y dos veces quedó
escrito acá y se quedó viejo: **no se escribe, se mide**, y hay que medirlos
todos: `abl` y los que arma `cartuchos`.

Medirlo no pide tocar ningún fuente: se ensambla un objeto aparte con un
`.res N` en el segmento que se quiere medir y se lo linkea junto al `.o` que
la receta ya dejó al lado de la ROM, y `ld65` avisa "Segment ‘TABLAS’
overflows memory area ‘ROM’ by 136 bytes", o sea que con `N = 200` sobraban
64. Ojo con dos cosas que hacen que la medición dé "no se pasó" siempre: en un
segmento `ro` el `.res` tiene que llevar valor de relleno —`.res N, $00`— o no
ocupa nada, y `ld65` escribe el mensaje con comillas tipográficas, no `'`.

Los tres segmentos que se llenan son **`TABLAS`** —el banco 0, que comparte
sus 32.704 bytes con `CODE`—, **`BSS`** y **`ZEROPAGE`**. El banco 1 es
`FAR`, y ahí el `.res` mide siempre 0 porque un `.align $8000` lo cierra hasta
el final del banco: lo que queda libre se lee mirando hasta dónde llega su
último símbolo en la tabla de símbolos.

**`rom/build/cache/` es un caché en disco del conversor** —muestras BRR,
muestras ya preparadas y capas convertidas— y su clave lleva el hash de los
fuentes **y el de los binarios que producen lo guardado**, así que no hay que
borrarlo al tocar código. Lo único que pide es que cualquier cambio en lo que
se cachea se verifique con `SIN_CACHE=1`: las dos ROMs tienen que ser byte por
byte iguales. Ver `tools/comun/cache_disco.py`.

**Mientras corren las pruebas no se toca ningún fuente.** `huella()` cubre
todo `rom/src/`, los `.py` de `tools/` y los binarios de `ca65` y `ld65`: tocar
cualquiera de ésos a mitad de una corrida mezcla dos versiones y el resultado no
dice nada.

Lo que **ya no hace falta** es aislarse en un worktree para eso. Hasta el
2026-09-16 existía `just hitos-foto`, que sacaba una foto del árbol con
`git stash create` porque la tanda corría recetas que pisaban
`rom/src/mapdata.inc`, que entonces era estado global. Desde el 9f las
pruebas no arman nada: corren contra los cartuchos que arma `just cartuchos`
antes —`release` y los de `rom/build/tests/`—, y el arnés se
niega a correr contra uno viejo. Dos corridas a la vez sólo se pisan si las
dos encuentran un cartucho viejo y lo rearman juntas: con `just cartuchos`
corrido una vez antes, lo único que se pelean es la CPU.

**Las tareas en segundo plano que lanzamos nosotros las podemos matar
nosotros.**

Lo que más se acumula son las **esperas armadas por los agentes** —`until !
pgrep -f "pytest"; do sleep 30; done`— y tienen dos vicios:

* **Nunca terminan solas**, porque su propia línea de comando contiene el texto
  que el `pgrep` busca, así que se encuentran a sí mismas.
* Cuando por fin despiertan, imprimen resultados de tandas que cerraron horas
  antes, y eso ya mandó a mirar números viejos más de una vez.

Al matarlas, ojo con el `pkill`: si el patrón aparece en la línea de comando
propia, se mata a sí mismo —código 144— y deja la mitad del trabajo hecho.
Partir el patrón alcanza: `pgrep -f 'un[t]il ! pgrep'`, y después `kill` uno
por uno salteando el `$$`.

## Sub-agentes

**Se usan, y son la forma preferida cuando dos trabajos no se pisan demasiado.**
Siempre con `isolation: "worktree"`: cada uno en su copia, así el `mapdata.inc`
—que es estado global— y las tandas no se mezclan.

Lo que hay que hacer siempre:

* **Traer los builds a `/shared`.** Los worktrees viven en `/extras`, que no
  está montado en el host, y `/shared` sí: es donde taro los encuentra. Van a
  `/shared/builds/<fecha>-<commit>/`, con un `LEEME.txt` que diga qué mirar y
  con qué limitaciones se chocó. Hasta el 2026-09-24 iban a
  `pruebas-manuales/`, adentro del repo.

  **Un solo `.sfc` por build, y se llama `abl.sfc`**: el cartucho con pantalla
  de título, que es el que taro juega. Las otras demos no se copian; el que las
  quiera las arma. Y **se dejan los dos últimos directorios y nada más**: el
  anterior sirve para comparar con lo que se venía jugando, y los de más atrás
  se rearman desde su commit. Es de taro, el 2026-09-20, después de que los
  builds llegaran a 4,3 GB en 51 directorios.

  **Las pistas de MSU-1 no van en el build: van a `/shared/msu/`**, un solo
  directorio que se actualiza sólo cuando cambian —su `LEEME.txt` dice con
  qué huella se comparan—. Pesan medio giga, y copiarlas en cada build las
  duplicaría por nada. taro copia el `abl.sfc` al lado. Es de taro, el
  2026-09-25, cuando `release` pasó a llevarlas siempre.
* **Y la ROM que se le da a probar sale de `main` mergeado, no de la rama del
  agente.** La del agente tiene su arreglo y **ninguno de los demás**. 
  La del agente sirve para aislar **su** cambio; la que se juega, no.
* **Decirle de qué commit sale, y que mergee `main` antes de entregar.** Un
  worktree se saca de donde esté `main` al lanzarlo, y `main` se mueve: el
  2026-09-15 uno trabajó cuatro horas sobre un README **doce commits viejo** y
  vio 5.499 líneas donde había 4.717. La reconciliación después es trabajo
  perdido que se evita con una línea en el encargo.
* **Pasarle al agente lo que ya está medido**, para que no lo vuelva a averiguar
  y para que no lo mida distinto.
* **Pedirle el límite medido y no la implementación forzada.** Cuando el punto
  es comparar dos caminos, saber dónde se rompe cada uno vale tanto como el
  código.
* **Avisarle que hay otros corriendo**: dos tandas a la vez se pelean por CPU y
  tardan, y matarlas por impaciencia arruina la corrida.
* **Repartirles los números de antemano.** Todo lo que se elige tomando "el
  siguiente libre" —un opcode, un índice en una tupla de
  `pruebas/*/test_*_golden.py`, una dirección de la RAM lejana— lo va a elegir cada agente
  mirando su copia, y dos van a elegir el mismo sin que git vea nada. Sale más
  barato decirle a cada uno cuál le toca al lanzarlo que descubrirlo mergeando:
  el 2026-09-13 pasó con las tres cosas a la vez, y una colisión de opcodes
  viajó adentro de un merge que ya se había dado por verificado.
* **Decirle que namespacee sus archivos temporales.** El scratchpad es
  **compartido entre agentes**, y dos que trabajan en paralelo eligen el mismo
  nombre obvio: el 2026-09-15 dos escribieron un `comparar.sh` cada uno en el
  mismo lugar. Uno pisa al otro y el pisado no se entera. `<scratchpad>/<lo que
  hace>/…` alcanza.
* **Pedirle que no deje nada esperando cuando termina.** Un sub-agente puede
  lanzar los suyos, y ésos **no aparecen** en la lista del que los mandó. 
  Lo mismo con los `sleep` largos para esperar
  una tanda: el 2026-09-12 uno dejó cinco armados y siguieron avisando que había
  terminado mucho después de haber entregado.

### Lo verificable y lo opinable no comparten commit

De taro, el 2026-09-16, y sirve para cualquier limpieza grande: **primero el
cambio mecánico solo, en su commit, verificado; después el de criterio, guiado
por el diff del anterior.**

El caso que lo mostró: borrar 784 líneas de código muerto y arreglar los
comentarios que lo citaban. El borrado lo verifican dos redes —`just pruebas` y
la ROM byte por byte—; arreglar la prosa no lo verifica nada. Mezclados, un
error de criterio viaja adentro de un cambio que "pasó las pruebas" y ahí ya no
lo mira nadie.

Y tiene un segundo beneficio que fue el que lo decidió: **el diff del primer
commit es la lista del segundo**, completa por construcción. La lista escrita a
mano que se iba a usar en cambio no tenía once citas colgando adentro del
propio archivo, ni dos definiciones muertas de otros, ni un parámetro muerto.

### Un merge sin conflictos no es un merge verificado

Dos ramas que cambian **la misma convención en archivos o líneas distintas**
mergean limpio y git no dice nada. Pasó el 2026-09-13: una rama hizo que
`paquete_cargar` leyera el mapa de `mapa_actual` en vez de A, la otra trajo un
llamador que se lo seguía pasando en A, y desde ese merge la pelea cargaba el
paquete de audio del mapa. Las dos pruebas que lo cobraban estuvieron en rojo
un día entero y **tres informes seguidos las dieron por "preexistentes"** —lo
eran, pero preexistente no quiere decir ajena—.

Y tiene una variante peor, que mordió dos veces el mismo día: **git resuelve
solo un extremo del cambio y deja el otro en conflicto.** Uno arregla lo que
git marcó, que es lo que se ve, y queda incoherente con lo que git ya decidió
callado treinta líneas más arriba. Las dos veces ensamblaba y corría:

* una rama dejó el índice en `Y` —`tay`— y la otra en `comp_and`; git se quedó
  con el `sta comp_and` de una, dejó en conflicto el `tyx` de la otra, y el
  código leía un registro que ya nadie cargaba;
* dos ramas agregaron un campo a una tupla posicional de prueba, así
  que los índices se corrieron; git marcó los usos de una zona y auto-mergeó
  los de otra, que quedaron leyendo el campo del vecino.

La regla práctica: **cuando un conflicto es por un cambio de convención, hay
que ir a buscar a mano los demás usos de esa convención**, con grep, en vez de
confiar en que git los haya marcado todos. Si git marcó uno, es probable que
haya resuelto mal otro.

Así que al mergear una rama de sub-agente:

* **Correr `just pruebas` y la tanda sobre el árbol mergeado**, no sobre las
  ramas. Que cada una viniera en verde no dice nada del merge.
* **Un rojo heredado se bisecta, no se hereda.** Si una prueba está en rojo y
  nadie la rompió, apareció en algún lado: `git log -S` para saber cuándo nació
  y correrla en los padres del merge sospechoso. Cuesta veinte minutos.
* **Mirar a mano las firmas que las dos ramas tocaron**: quién pasa qué a quién
  y con cuántos bits.
* **Y la prosa también colisiona, no sólo el código.** Al mergear documentación de
  dos ramas hay que **leerla**, no sólo resolver los conflictos que git marcó.
* **Y los números que cada rama eligió sola.** Un opcode nuevo, un índice en una tupla de prueba, una dirección de la RAM lejana: cada agente toma "el
  siguiente libre" mirando su copia, así que dos ramas eligen el mismo y git no
  ve nada. Pasó las tres cosas el mismo día. Lo de los opcodes lo cuida ahora
  `test_ningun_opcode_comparte_numero_con_otro`; lo demás hay que mirarlo.

### Cuando un sub-agente se corta

**Se le puede escribir, y con eso retoma desde su transcripción.** Cuando el
corte es por límite de sesión —el caso normal— alcanza con mandarle un mensaje
diciéndole dónde quedó y qué falta: sigue con su contexto entero. Pasarle lo
que cambió mientras no estaba —si `main` avanzó, si alguien tocó los mismos
archivos, qué números ya no valen— vale tanto como el pedido.

**Antes de escribirle, mirar si choca con lo que uno está haciendo.** Un agente
cuya rama se está mergeando en ese momento no se retoma, porque se pisan; uno
que quedó a mitad de medir o de escribir casos, sí.

Y en cualquier caso, al retomar conviene mirar, en este orden:

1. **Su rama y su worktree**: `git log --oneline worktree-agent-<id>`. Lo
   commiteado está entero; lo demás no existe.
2. **Los logs que haya dejado**, antes que su informe: una tanda en segundo
   plano puede haber terminado después del corte, así que su "quedó pendiente"
   puede ser viejo.
3. **Su transcripción**, en
   `~/.claude/projects/<proyecto>/<sesión>/subagents/agent-<id>.jsonl`. Son
   megas: se lee **del final hacia atrás, una entrada por vez**, mirando qué
   herramienta usó última. Nunca entero.
4. **Lo que dejó corriendo**: `pgrep -af "pytest|cartuchos"` y
   `git worktree list`.

Y para el agente nuevo que lo reemplace: pasarle lo que el anterior dejó escrito
—commits y su tarea— para que no vuelva a medir lo mismo.

## La trampa que más veces mordió

**`plx`, `ply` y `pla` dejan N y Z del valor que sacan de la pila**, y `sep`/`rep`
no tocan Z. Así que un `beq` o un `bpl` pegado a un `pl*` no está mirando lo que
uno cree: mira lo que salió de la pila.

Van cuatro veces, y las cuatro se veían como cualquier otra cosa menos como lo
que eran:

* ninguna ruta se movía nunca, porque la ranura 0 daba "bloqueado" siempre
  (el `cmp #0` de `cuadro_de_ruta_ev`, con su comentario);
* la pantalla de título se quedó sin música un día entero, porque la pregunta
  "¿esta muestra está en la ARAM?" contestaba siempre que sí;
* `ConditionalBranch` por variable **tomaba siempre la rama**, con la variable
  en 12 y la condición pidiendo `>= 99`;
* `IsActorInParty` daba que todos los actores están en el grupo.

El arreglo es siempre el mismo: un `cmp #0` explícito entre el `pl*` y el salto.
Vale la pena hacer `grep` de `pl[axy]` seguido de un salto condicional cada vez
que algo "contesta siempre lo mismo".

## Git

Los commits van directo a `main`. No hacemos `git push`. 
Los mensajes van en castellano y explican el porqué, no el qué —el diff ya dice el qué—.
