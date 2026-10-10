# Cómo se trabaja en este repo

Esto es lo que **no** se deduce leyendo el código. Todo lo demás está en
fuentes mejores, y hay que ir a ellas antes que a este archivo:

    snes-rm2k-work   otro repo: dónde quedamos —las tareas, las decisiones
                     y las divergencias de todos los repos—; su README
                     explica cada carpeta
    tools/justfile   qué se puede correr —probar e instalar las
                     herramientas—; los comentarios explican el porqué. Se
                     corre con `just -f tools/justfile`, o con `just`
                     parado en `tools/`
    README.md        qué es el proyecto, cómo se instala, y los porqués de
                     arquitectura que no tienen línea de código donde vivir
    tools/README.md  qué hace cada carpeta de `tools/`
    docs/            RM2k, la consola, cómo funciona el port hoy, y los
                     estudios fechados: su README dice qué va en cada carpeta
    DITTO.md         qué es Ditto, por qué existe acá y en qué estado está
                     la idea de que los JSON sean la fuente de verdad
    git log          los mensajes son largos a propósito: son el registro

**A Blurred Line no está en este repo.** Desde el 2026-10-02 vive en el
suyo, con sus datos, sus parches, sus pruebas y sus goldens, y consume
estas herramientas desde el PATH; la historia de lo que era suyo se quedó
acá. Dónde está ese repo, y cómo se corre ABL con las herramientas de un
checkout de éste, en "Dónde corre esto".

**Las tareas, las decisiones y las divergencias tampoco están acá**: desde
el 2026-10-10 viven en su propio repo, `snes-rm2k-work`, las de todos los
repos —ésta, los ports y el libro—. Hasta ese día eran la carpeta
`workflow/` de éste, y salieron con su historia; **un `workflow/…` citado
en un comentario de este repo es la misma ruta allá**, sin el prefijo. **Y sus pruebas son, hasta que
exista el juego de pruebas, las únicas pruebas de ROM del motor**: ver "La
regla que sostiene todo".

Al empezar, mirar `tasks/doing/` y `testing/` de `snes-rm2k-work`, que es dónde quedamos. La
tarea se escribe **mientras se trabaja, no al final**, y al terminar se mueve de
carpeta.

**Tomar una tarea es pasarla a `doing/` con su `assignee`, antes que nada.** Con
sub-agentes lo hace el que los lanza, en `main` y antes de lanzarlos, así el
worktree ya sale con la tarea tomada y dos agentes no agarran la misma. El
`assignee` es el nombre del agente: el que los lanza les pone uno —una palabra,
no el código de la herramienta— y se lo dice en el encargo. Una tarea que el
agente abre por su cuenta nace en `doing/` con su nombre. Es de taro, el
2026-09-28; hasta ese día la carpeta se llamaba `wip/` y casi no se usaba.

## Dónde va cada cosa que uno quiere dejar escrita

Dos reglas, de taro, el 2026-09-15. Las dos salen del mismo problema: lo que se
escribe a mano en un documento envejece sin avisar, y lo que vive lejos del
código no lo lee nadie cuando hace falta.

**Un número se escribe sólo si es propiedad del hardware o del formato.** Los
32.704 bytes del banco 0, los tiles de 8x8, el color de 15 bits, los 64 KB de
ARAM: ésos no cambian. **Un número que describe el estado de nuestro trabajo no
va escrito en ningún lado, va el comando que lo imprime**: cuántos casos
pasan lo dice la tanda, cuánto pesa el cartucho lo dice el build.

El 2026-09-15 había **tres números distintos para la misma pregunta** —281, 314
y 332 de 489— en dos archivos, los tres viejos, y el real era 350. Uno de ésos
lo había escrito yo una hora antes.

**Un porqué se queda en el README sólo si es una decisión de arquitectura que
no tiene una línea de código donde vivir**: por qué modo 3 fijo, por qué
LoROM. **Un porqué que protege una línea concreta va como comentario en esa
línea.** El razonamiento es de taro y es difícil de discutir: nadie que esté
editando una rutina va a buscar la razón en un README de cinco mil líneas, así
que ahí no protege a nadie.

Y si el error no es de los que se vuelven a cometer, no va a ningún lado: el
`git log` ya lo tiene.

**La documentación no nombra el ambiente donde corremos esto**: ni el
contenedor, ni `box`, ni `/extras`, ni `/shared`, ni rutas de esta máquina.
Dice qué variable o qué flag lo apunta —`ABL_GAME_DIR`, `ABL_RTP_DIR`—, y el
ambiente queda en este archivo, que es el único que lo describe. Es de taro,
el 2026-09-26; las tareas y los defaults del código no cuentan.

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
de punta a punta: código, comentarios, nombres de pruebas y README. Desde el
2026-09-19 viven adentro de `tools/` —ver `tools/README.md`—:

    tools/snes/        los formatos de la consola, sin saber de RPG Maker
      gunter/          Gunter: códec BRR y lector de SoundFont
      goombario/       Goombario: el linter de 65816, lo que ensambla bien y
                       está mal; lee la ROM, el `.dbg` de `ld65` y el fuente
      adeleine/        Adeleine: qué colores se pierden y cómo se agrupan en paletas
      voodoo/          Voodoo: de una imagen a tiles, paletas y tilemap
      lz2/             el LC_LZ2 de Nintendo, con el que se comprimen los mapas
    tools/rm2k/        los de RPG Maker 2000, sin saber de la consola
      ditto/           lee y escribe sus formatos; como biblioteca, el único
                       lugar en Rust que lee el volcado
      rules/           rm2k-rules: lo que el formato significa —pasabilidad,
                       páginas, experiencia—
      rm2k-render/     las capas de un mapa, sus CharSets, lo de la pelea y las
                       caras, ventanas y carteles de las pantallas, dibujados
                       como RM2k
    tools/rm2k-snes/   los que unen las dos cosas
      project/         la biblioteca: qué juego, sus perillas, los flags de la
                       máquina; y `rm2k-snes-project`, que se lo dice en JSON
                       a las pruebas de un juego
      bytecode/        los dos bytecodes del cartucho, declarados una vez: las
                       constantes de Rust y los `.inc` del ensamblador
      cartridge/       los cartuchos: el reparto en bancos, ca65 + ld65, el espacio
      patches/         los parches: lo que el conversor decide perder, en TOML
      rm2k-snes-audio/ la música: del MIDI y el SoundFont a musicdata.inc
      battle/          la pelea: experiencia y encuentros, el modelo y su
                       pantalla de texto, y la pelea jugada para las pruebas
      events/          el compilador de eventos: de las páginas de RM2k al bytecode
      wally/           Wally: un mapa entero —capas, horneado, sprites—, con
                       sus dos mitades como módulos que no se conocen: el
                       fondo y sus bloques de 16x16, y los personajes como
                       objetos
      text/            la fuente, una línea de texto sobre el System y el
                       reparto de las cajas al ancho de la ventana
      screens/         las pantallas: la ventana de mensajes, el título, las
                       ranuras, el menú, las pantallas de texto, End Game
      images/          las imágenes: el título y el Game Over, la de
                       `ShowPicture`, los fondos y battlers de la pelea y sus
                       animaciones, escalados y con sus paletas
      mapdata/         la emisión: el `.inc` del cartucho con lo que contestó
                       cada etapa, los flujos de LZ2 y los repartos de VRAM
      convert/         el conversor: le pregunta a cada etapa, en orden, lo que
                       el cartucho necesita, y le da lo que contestaron las otras

Las capas sólo dependen hacia abajo —`rm2k-snes/` de las otras dos, y
ésas de nada de las demás—, y lo cuida `tools/tests/test_layers.py`. Todos
son un solo workspace de Cargo, con el `Cargo.lock` y el `target/`
en `tools/`.

Hasta el 2026-09-16 hubo otro más, `w65/`, el ensamblador de 65816. Lo reemplazaron
`ca65` y `ld65`, del proyecto cc65: ver "Dónde corre esto".

**Se consumen desde el PATH, no desde `target/release`.** Se instalan con
`just -f tools/justfile install` —`cargo install --locked --path …`— y a
partir de ahí son herramientas del sistema, como `python3` o un core de
libretro: **ningún script ni prueba de este juego llama a `cargo`**. Es de taro, el 2026-09-15, y lo que
evita es que cada corrida de la tanda quede atada al toolchain de Rust.

`CARGO_ROOT` dice dónde instalan; por omisión `/usr/local`, que acá está en el
PATH.

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
`tools/` o en `tools/runtime/`: es su salida, no fuente de este árbol, y dice arriba
que es generada y de dónde. El 2026-09-14 la regla era la contraria —"el idioma
del árbol donde cae"— y duró un día: al generalizar el generador para el
segundo bytecode quedó claro que hacerlo hablar castellano lo ata a este repo.

Las pruebas de esos proyectos no dependen del juego. Ditto recibe el corpus por
`DITTO_CORPUS`, y sin esa variable las que lo necesitan se saltean con un
mensaje; `tools/rm2k-snes/rm2k-snes-audio/` recibe el SoundFont por `SOUNDFONT`, igual;
`tools/snes/goombario/` ensambla programas de juguete y necesita `ca65` y
`ld65` en el PATH, y sin ellos se saltea igual;
y `tools/snes/gunter/`, `tools/snes/voodoo/`, `tools/snes/lz2/`,
`tools/snes/adeleine/`, `tools/rm2k/rules/`, `tools/rm2k/rm2k-render/`, `tools/rm2k-snes/battle/`,
`tools/rm2k-snes/bytecode/`, `tools/rm2k-snes/events/`, `tools/rm2k-snes/patches/`, `tools/rm2k-snes/wally/` y
los dos de las pantallas, `tools/rm2k-snes/images/`,
`tools/rm2k-snes/mapdata/` y `tools/rm2k-snes/convert/` no necesitan nada.

### `tools/snes/voodoo/` no decide colores, y eso no se arregla

`tools/snes/voodoo/` convierte una imagen **que ya entra**: recibe PNG indexados cuyos
índices son entradas de CGRAM, y si la imagen rompe el formato, dice dónde y no
la arregla. Qué colores se pierden y cómo se agrupan en paletas lo decide
Adeleine, `tools/snes/adeleine/` —`wally`, `rm2k-snes-screens`
y `rm2k-snes-images` lo usan como biblioteca—, que corre
**antes**; lo que decidió de cada mapa queda como imágenes en
`build/<cartucho>/adeleine/`, en el proyecto del juego. La prueba para saber de qué lado
va algo es si cambia un pixel de lo que se ve.

Es de taro, el 2026-09-17. Voodoo tuvo un `--merge` que fusionaba colores; se
sacó para que haya una sola respuesta a "qué color se perdió". Devolverle
cualquier decisión de ésas deshace el diseño, aunque sea cómodo.

## El número de un opcode se elige en la declaración

En `tools/rm2k-snes/bytecode/` y en ningún otro lado. Hay dos declaraciones,
cada una una invocación de la macro `bytecode!`: `src/events.rs`, el bytecode
que interpreta `run_code`, y `src/music.rs`, el stream que lee `irq_music`. El
lado de Rust toma las constantes con un `use`, y `rm2k-snes-assemble` escribe
el del 65816 —`event_opcodes.inc` y `music_opcodes.inc`— en el directorio
del cartucho en cada build: no hay generado commiteado que pueda quedar
viejo. Los dos caen en el mismo espacio de símbolos del ensamblador, así que
dos opcodes de bytecodes distintos pueden compartir **número** pero no
**nombre** —por eso `OP_FIN` se llama `OP_DONE`: `OP_END` ya era del stream
de música—, y eso, como un número repetido o un hueco en el despacho, **no
compila**: son `const` asserts del crate, con el opcode en el mensaje.

Hasta el 2026-10-02 los declaraban dos TOML de `tools/snes/protocol/`, un
generador que escribía los dos lados y los commiteaba, y una prueba que
cuidaba que no envejecieran.

Antes el de eventos lo declaraba `tools/port/events.py` y le llegaba al intérprete
adentro de `mapdata.inc`, que es cómo dos ramas pudieron elegir el mismo sin
que git viera nada; el de música estaba escrito a mano de los dos lados.
(`mapdata.inc` sigue existiendo y `main.s` lo sigue incluyendo: lo que salió de
ahí es el bytecode, no las tablas del mapa.) Al repartir trabajo entre
sub-agentes sigue valiendo repartir los números de antemano, pero ahora la
colisión es un conflicto de git en un archivo y no un bug que viaja adentro de
un merge.

Del de eventos sale también **la tabla del despacho** de `run_code` (la
macro `EVENT_HANDLERS`), así que un opcode nuevo es su entrada en
`src/events.rs` y su `.proc op_x`, con el nombre del opcode en minúsculas; el
despacho no se toca. Eso pide **números contiguos desde 0**: si se saca un
opcode, el hueco hay que cerrarlo —renumerando, o dándole el número al
próximo que se agregue—, porque la declaración no compila con huecos.

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

**`tools/runtime/` atraviesa el corte de `main.s` sólo con
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

**La mudanza de `rom/src/` a `tools/runtime/`, el 2026-09-29, no cuesta
nada**: fue un commit de `git mv` solo, sin tocar una línea, y `blame` sigue
los renombres sin opciones. Con las de arriba, cada línea de
`tools/runtime/` sale con el mismo commit que daba en `rom/src/` antes de
mudarse: medido sobre `main.s`, `hero.s`, `interpreter.s`, `battle.s`,
`registers.s`, `audio_package.s` y `event_opcodes.inc`, cuatro mil
líneas. Con `data/`, `parches/` y `pruebas/`, que se mudaron adentro de
`rom/` en el mismo commit, alcanzaba el `blame` sin opciones: medido sobre
`rom/pruebas/arnes/consola.py`.

**Lo de ABL se fue a su propio repo el 2026-10-02, sin historia**: allá
cada archivo nace en un solo commit. Su `blame` se pide acá, sobre la ruta
que tenía y en el padre del commit que lo borró —`git blame
d356bfb7^ -- rom/pruebas/arnes/consola.py`—, y `git log -S` sigue
encontrando todo lo que pasó antes de esa fecha, de los dos lados.

Los IDE que no dejan pasarle opciones a `blame` —el annotate de JetBrains—
necesitan configuración del lado del host: ver `docs/jetbrains.md`.

## La regla que sostiene todo

Nada se da por bueno porque se vea bien: **se compara pixel por pixel, a 15
bits**, que es la profundidad real de la consola. Lo que cambió el 2026-09-16
es contra qué.

Hasta ese día se comparaba contra una **referencia en Python** que hacía lo
mismo que la ROM. Hoy se compara contra **capturas congeladas** —las goldens de
la tanda de ABL, en `pruebas/golden/tanda/` de su repo, que son lo que la ROM
dibujaba el día que la tanda estaba en verde—. De ahí salen tres
obligaciones, y una de ellas es nueva.

**Las pruebas de ROM del motor viven en ABL, por ahora.** Se fueron con el
juego el 2026-10-02, porque necesitan uno, y vuelven a este repo de a poco
cuando exista el juego de pruebas —la fase 2 de
`docs/research/2026-10-02-el-juego-de-pruebas.md`—. Hasta entonces **un
cambio en `tools/` se verifica corriendo la tanda de ABL con las
herramientas del cambio**, como dice "Dónde corre esto"; `just -f
tools/justfile test` y las de cada crate no corren ninguna ROM. Es el riesgo
que el estudio señaló, y es el argumento para no demorar la fase 2.

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
la sacó tampoco la ve.** Para eso está `pruebas/rpgmaker/test_cores.py`, en ABL: corre el mismo
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
cubre la tanda, el mensaje tiene que decirlo con todas las letras.

## Dónde corre esto

Adentro de un contenedor de podman que taro levanta con `box`, una función
suya de nushell: Arch —igual que el host— con este repo montado en
`/host/abl-snes`. **Los archivos del repo son los de verdad**: lo que se escribe
acá queda escrito en su disco.

**ABL está en `/abl-snes`**, su propio repo, desde el 2026-10-02, montado
de un disco local del host. Hasta el 2026-10-03 vivía en `/shared/abl-snes`,
y la copia vieja sigue ahí pero **no se usa**: `/shared` es un CIFS sobre el
disco mecánico de un NAS, lento, sin symlinks, sin bits de ejecución y sin
distinguir mayúsculas.

**Para correr ABL con las herramientas de un checkout de éste** —un
worktree que cambia el runtime o el conversor—: `just -f tools/justfile
install-local tools/.local-tools <proyectos de Rust>` en el worktree, y
desde ABL `PATH=<worktree>/tools/.local-tools/bin:$PATH just pruebas`. El
`justfile` de ABL arma su PATH desde el que recibe, y lo que no esté en ese
`bin/` sale del global. **Pero arma en el `build/` del checkout de ABL donde
corre**: el de `/abl-snes` es el que se juega y el de la tanda principal,
así que un agente que lo necesite se saca su propio clon o worktree de ABL
(`git -C /abl-snes worktree add <dir>`). El resto del sistema es descartable, y por eso
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

Las herramientas llegan a `/extras` y a `/shared` por flags —`--game-dir`,
`--rtp-dir`, `--soundfont`, `--replacements`, `--shared`—, y no saben de
ningún valor de esta máquina. Los pone el `justfile` de ABL, en su repo, que
traduce `ABL_GAME_DIR`, `ABL_RTP_DIR`, `ABL_SOUNDFONT` y `SHARED` con los
valores de acá por omisión. Si el ambiente cambia, se cambia allá.

Las dos pruebas de las herramientas que leen un SoundFont de verdad —las
de `rm2k-snes-audio`— lo reciben en `SOUNDFONT`, como Ditto su corpus en
`DITTO_CORPUS`: sin la variable se saltean. Para correrlas acá,
`SOUNDFONT="/extras/soundfonts/Microsoft GS Wavetable Synth.sf2" just -f
tools/justfile crate-test rm2k-snes-audio`.

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
el `data/` de un juego trae ya aplicados y los nombres de los comandos de RM2k, contra los
que se sostiene `codes.rs` del compilador de eventos—: salen de ahí y de ningún
otro lado, porque la primera versión del filtro de puertas los puso de memoria
y tres estaban mal. Si hace
falta algo que no se consigue desde acá, se le pide a taro que lo copie a
`/extras`.

**taro no corre nada en el host**: si corre algo a mano, lo hace acá
adentro, y lo pregunta antes. Es suyo, el 2026-10-05. Lo único que es del
host es el `git push`, el EverDrive por USB, y **ver y escuchar la ROM de
verdad** — acá adentro se captura con Xvfb y el audio se graba a un wav en
vez de sonar.

## Recetas o scripts descartables

La decisión no es de seguridad: es el costo de mantener el script contra lo que
rinda tenerlo. Una receta por cada script convertiría al justfile en ruido.

**Receta de `just`** cuando se va a volver a correr: si entra en una cadena de
verificación, o si conviene que quede escrito cómo se armó algo. `evento`
nació así, y de paso dejó de existir la
ROM armada a mano que mandó a mirar el mapa equivocado.

**Script descartable** cuando contesta una pregunta de una sola vez: cuántos
mapas tienen tal cosa, en qué offset de la ROM cae tal byte. Va al scratchpad
y se tira.

## Trampas del entorno

**`tools/runtime/` es un solo ensamblado partido en muchos `.s`.** `main.s` los
pega con `.include`, y el orden de esa lista es el orden en la ROM: partir es
gratis, mover no. Lo que eso implica —cada archivo hereda los anchos y el
segmento del anterior, las anónimas se resuelven sobre el texto pegado— lo
dice el encabezado de `main.s`, que es donde lo va a ver quien agregue un
archivo. Hasta el 2026-09-25 era un solo archivo; se partió byte por byte
igual, y por eso hay rutinas que quedaron en el archivo del vecino: moverlas
es un cambio de ROM, y va en su propio commit.

**Un `.inc` generado nunca va en `tools/runtime/`.** `ca65` busca los
`.include` primero en el directorio del archivo que incluye y recién después en
los `-I`, así que un `mapdata.inc` en `tools/runtime/` taparía al del cartucho sin
avisar: la ROM saldría con los datos de otro. Hasta el 2026-09-16 la receta
`convert` escribía justo ahí —en `rom/src/`, donde vivía el runtime hasta el
2026-09-29; era "estado global", y así se terminó mirando el
mapa 6 creyendo que era la demo del hito 12—; hoy cada cartucho escribe el suyo
en su directorio del `build/` del proyecto, y `rm2k-snes-assemble` se niega a armar si
encuentra uno en `tools/runtime/`. **Las
ROMs salen de una receta, no de un `ca65` suelto.**

**Cuánto le sobra al banco 0 depende de qué cartucho se arme.** Las tablas que
emite el conversor viven ahí, así que el número cambia con la lista de mapas:
el 2026-09-13 la misma pregunta se contestó **81**, **1** y **85** bytes en la
misma tarde, y las tres estaban bien —cada una con un `mapdata.inc` distinto—.
Así que al decir "quedan N bytes" hay que decir con cuál.

**El que manda es el más apretado**: hasta el 2026-09-25 los cartuchos de
prueba llevaban más mapas que `abl`, y medir sólo en ella decía que había
lugar cuando no lo había. Desde que `abl` es también el cartucho de la tanda
lleva todos, pero `test-special` tiene sus flags propios. Cuál es el más
apretado cambia, y dos veces quedó
escrito acá y se quedó viejo: **no se escribe, se mide**, y hay que medirlos
todos: `abl` y los que arma `cartuchos`.

**Se mide con `just espacio`, en ABL**, que corre `rm2k-snes-space` e imprime para cada cartucho los bancos de
datos libres y los huecos, el banco 0, el banco 1, `BSS`, `ZEROPAGE` y el
bloque de textos; con la ruta de una ROM armada aparte, mide ésa. Lo que
cuenta es **cuántos bancos quedan**, no un porcentaje: los bancos `$7E` y
`$7F` no son ROM. Hasta el 2026-09-27 se medía a mano, linkeando un `.res N`
contra el `.o` de la receta; eso sigue sirviendo para lo único que la receta
no puede, que es una ROM que no linkea: ahí `ld65` dice por cuánto se pasa.

**`build/cache/`, en el proyecto, es un caché en disco** —qué pistas de MSU-1 ya están—
y su clave lleva el hash de los fuentes **y el de los binarios que producen lo
guardado**, así que no hay que borrarlo al tocar código. Lo único que pide es
que cualquier cambio en lo que se cachea se verifique con `NO_CACHE=1`: las
dos ROMs tienen que ser byte por byte iguales. Ver `cache.rs` en
`rm2k-project`.

**Mientras corren las pruebas no se toca ningún fuente**, tampoco desde el
otro repo. La huella de `rm2k-snes-cartridges` cubre todo `tools/runtime/`
del checkout desde el que se instalaron las herramientas y los binarios
que arman —`ca65`, `ld65`, `rm2k-snes-assemble` y
los que corre el conversor—: tocar cualquiera de ésos mientras corre la
tanda de ABL, o reinstalar uno, mezcla dos versiones y el resultado no dice
nada.

Lo que **ya no hace falta** es aislarse en un worktree para eso. Hasta el
2026-09-16 existía `just hitos-foto`, que sacaba una foto del árbol con
`git stash create` porque la tanda corría recetas que pisaban
`rom/src/mapdata.inc` —el runtime vivía ahí—, que entonces era estado global. Desde el 9f las
pruebas no arman nada: corren contra los cartuchos que arma `just cartuchos`
antes —`release` y los de `build/tests/`—, y el arnés se
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

**Son un plantel fijo, desde el 2026-10-04**: un archivo por agente en
`.claude/agents/`, con un nombre de la flora o la fauna argentina, y lo que
vale para todos en `.claude/agentes.md` —lo que antes se repetía en cada
encargo—. Se lanzan por su nombre, no como `general-purpose`, así el mismo
agente vuelve y se encuentra a sí mismo: cada tarea lleva en `agents` a
todos los que trabajaron en ella —el `assignee` pasa a taro en
`testing/`—, que `snes-rm2k-work/tasks/tasks.nu ls -a <nombre>` filtra, y cada
commit suyo termina con `Agente: <nombre>`, que `git log --grep` encuentra.
Lo pidió taro, el 2026-10-04. Siguen arrancando de cero cada vez: la
continuidad es lo que dejan escrito.

Lo que hay que hacer siempre:

* **Traer los builds a `/shared`, con `just entregar "<qué mirar>"`, desde
  ABL.** Los worktrees viven en `/extras`, que no está montado en el host, y
  `/shared` sí: es donde taro los encuentra. Van a
  `/shared/builds/<fecha>-<commit de ABL>-<commit de las herramientas>/`, y
  el texto que se le pasa a la receta va al `LEEME.txt`: qué cambió, qué
  mirar y con qué limitaciones se chocó. Hasta el 2026-09-24 iban a
  `pruebas-manuales/`, adentro del repo, y hasta el 2026-09-25 se armaban a
  mano, que se repetía seguido y se equivocaba.

  **Un solo `.sfc` por build, y se llama `abl.sfc`**: el cartucho con pantalla
  de título, que es el que taro juega. Las otras demos no se copian; el que las
  quiera las arma. Y **se dejan los dos últimos directorios y nada más**: el
  anterior sirve para comparar con lo que se venía jugando, y los de más atrás
  se rearman desde su commit. Es de taro, el 2026-09-20, después de que los
  builds llegaran a 4,3 GB en 51 directorios. La receta borra los demás y no
  toca lo que taro deja adentro, como la partida de su emulador.

  **Al lado va `abl.sfc.dbg`**, con el que Mesen2 muestra nuestros nombres de
  rutina en el depurador, **y el `tools/runtime/` del commit**, sacado con `git
  archive`: Mesen2 busca el fuente subiendo de carpeta desde el `.dbg`, así
  que con `tools/runtime/` al lado lo muestra también desde `/shared/builds/`. Los
  `.inc` que genera el conversor no van —pesan ~15 MB— y lo que cae en ellos
  se ve sólo desensamblado. Por eso la receta **se niega con cambios sin
  commitear** en lo que entra en la ROM: el build se nombra por un commit y
  tiene que ser ése. Ver "Debugging with Mesen2" en `docs/snes/emulators.md`.

  **Lo demás que taro tiene que mirar o escuchar va a dos carpetas y no a la
  raíz de `/shared`**: capturas y goldens a `/shared/capturas/<fecha>-<tema>/`,
  audio a `/shared/audio/<fecha>-<tema>/`. Es de taro, el 2026-09-27, después
  de limpiar una docena de carpetas sueltas (`capturas-lashe-3`,
  `goldens-textos`…) y 2 GB de audio viejo. Lo que ya está en git o se rearma
  desde un commit se puede borrar cuando taro lo dio por mirado.

  **Las pistas de MSU-1 no van en el build: van a `/shared/msu/`**, un solo
  directorio que se actualiza sólo cuando cambian —su `LEEME.txt` dice con
  qué huella se comparan—. Pesan medio giga, y copiarlas en cada build las
  duplicaría por nada. taro copia el `abl.sfc` al lado. Es de taro, el
  2026-09-25, cuando `release` pasó a llevarlas siempre. `just entregar`
  avisa si no coinciden con las del build, y las copia sólo con
  `--actualizar-msu`.

  **El `abl.msu` sí va en el build, y además a `/shared/msu/` siempre.**
  Desde el 2026-09-25 no está vacío: lleva los fondos de batalla que la ROM
  lee por el MSU-1 —ver `docs/port/msu-datos.md`—, así que cambia con el
  conversor y es del build, no de las pistas; y pesa 32 KB por fondo. Con el
  `abl.sfc` de otro build no se rompe nada: la ROM no encuentra su firma en
  el `.msu` y usa los fondos que lleva.
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
  `pruebas/*/test_*_golden.py` de ABL, una dirección de la RAM lejana— lo va a elegir cada agente
  mirando su copia, y dos van a elegir el mismo sin que git vea nada. Sale más
  barato decirle a cada uno cuál le toca al lanzarlo que descubrirlo mergeando:
  el 2026-09-13 pasó con las tres cosas a la vez, y una colisión de opcodes
  viajó adentro de un merge que ya se había dado por verificado.
* **Decirle que namespacee sus archivos temporales.** El scratchpad es
  **compartido entre agentes**, y dos que trabajan en paralelo eligen el mismo
  nombre obvio: el 2026-09-15 dos escribieron un `comparar.sh` cada uno en el
  mismo lugar. Uno pisa al otro y el pisado no se entera. `<scratchpad>/<lo que
  hace>/…` alcanza.
* **Que corra `just -f tools/justfile install-local tools/.local-tools`
  al empezar, si va a modificar las herramientas**, desde la raíz del
  worktree. El global —`just -f tools/justfile install`— sale del
  checkout principal, y esto arma un `bin/` en el destino con los
  proyectos de Rust que se le nombren —scripts de Python no queda
  ninguno, desde el 2026-10-02—; `tools/justfile` lo pone adelante en el
  PATH de sus recetas, y ABL lo usa si se le pone adelante en el suyo (ver "Dónde corre esto").
  **Un proyecto de Rust se le pasa sólo si el agente lo va a modificar**
  —`… install-local tools/.local-tools lz2`—: compilar cuesta, y sin
  nombres no compila nada. Y **todo se corre por `just`**: un comando
  suelto no ve ese `bin/` y usa el global. Es de taro, el 2026-09-29, y
  reemplazó a un re-exec implícito que los scripts hacían solos.
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
`package_load` leyera el mapa de `map_current` en vez de A, la otra trajo un
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

* **Correr `just -f tools/justfile test` y la tanda de ABL sobre el árbol
  mergeado**, con las herramientas del merge instaladas, no sobre las ramas.
  Que cada una viniera en verde no dice nada del merge.
* **Reinstalar en el global sólo lo de Rust que la rama tocó**: `just -f
  tools/justfile install lz2`, desde el checkout principal. Una rama que
  toca `rm2k-project` —`project`— cambia todos los binarios que lo
  compilan adentro, y se reinstala todo. Hasta el 2026-10-02 había
  también scripts de Python, instalados como symlinks, y una receta
  `install-scripts` para rearmarlos: se fueron con el último script.
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
  la declaración, que no compila con un número repetido; lo demás hay que
  mirarlo.

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
  (el `cmp #0` de `ev_route_frame`, con su comentario);
* la pantalla de título se quedó sin música un día entero, porque la pregunta
  "¿esta muestra está en la ARAM?" contestaba siempre que sí;
* `ConditionalBranch` por variable **tomaba siempre la rama**, con la variable
  en 12 y la condición pidiendo `>= 99`;
* `IsActorInParty` daba que todos los actores están en el grupo.

El arreglo es siempre el mismo: un `cmp #0` explícito entre el `pl*` y el salto.
Desde el 2026-10-02 lo busca Goombario —`tools/snes/goombario/`— sobre cada
cartucho armado, en `pruebas/herramientas/test_linter.py` de ABL: un salto
condicional sobre una bandera que dejó un `pl*` es rojo, salvo los que miran
a propósito lo que se sacó, que están en `excepciones-del-linter.txt` de ABL,
con su porqué. Uno nuevo de ésos va ahí, diciendo qué es lo sacado.

## Git

Los commits van directo a `main`. No hacemos `git push`. 
Los mensajes van en castellano y explican el porqué, no el qué —el diff ya dice el qué—.
