# Los opcodes de los eventos: su número y su layout. La declaración está en
# `tools/protocol/events.toml` y no es ni del compilador ni del intérprete; de ahí
# salen generados los dos módulos de `tools/` y los dos `.inc` de `rom/src/`,
# todos commiteados. Hay dos declaraciones: el bytecode de los eventos y el
# stream de música que lee el SPC700.
#
# `--check` es lo que corre la tanda: falla si alguno quedó viejo.
protocolo *args:
  protocol tools/protocol/events.toml \
      --python tools/port/event_opcodes.py --asm rom/src/event_opcodes.inc {{args}}
  protocol tools/protocol/music.toml \
      --python tools/audio/music_opcodes.py --asm rom/src/music_opcodes.inc {{args}}

# Las pruebas del generador: los errores que tiene que dar ante una declaración
# rota, y la forma exacta del texto que emite. No necesitan el juego ni la ROM.
protocolo-pruebas:
  cd tools/protocol && cargo test

# Gunter: el códec BRR y el lector de SoundFont, y **el que arma las muestras
# de la ROM**. Sus pruebas son muestras generadas adentro de la prueba —silencio,
# rampa, cuadrada, impulso, saturación— más los mensajes de error, así que no
# necesitan ni el juego ni un soundfont. Que las muestras de verdad salgan bien
# lo cobra cualquier demo, porque viajan adentro del `.sfc`.
gunter-pruebas:
  cd tools/gunter && cargo test

# El .ldb/.lmu/.lmt ⇄ JSON en Rust. Todavía no reemplaza a
# `tools/rpgmaker/lcf.py` ni al conversor: convive con ellos. Ver DITTO.md, que
# es lo que ata a Ditto con este port; adentro de tools/ditto/ no hay ni una
# referencia a nosotros, a propósito.
#
# El juego con el que se mide **se lo pasa el repo**, no lo sabe la herramienta:
# sin DITTO_CORPUS las pruebas que lo necesitan se saltean con un mensaje.
#
# La tanda corta va sobre una muestra de mapas; `ditto-vuelta-entera` son todos
# los mapas, el LDB y el árbol, y mide lo único que hace útil a la herramienta:
# que el binario vuelva **byte por byte**. Va aparte porque es la que uno quiere
# ver con el número, no la que corre callada.
ditto-pruebas:
  cd tools/ditto && DITTO_CORPUS="${ABL_GAME_DIR:-/extras/abl-rm}" cargo test

ditto-vuelta-entera:
  cd tools/ditto && DITTO_CORPUS="${ABL_GAME_DIR:-/extras/abl-rm}" cargo test --release -- --include-ignored --nocapture

# **Regenera `data/`**: el juego entero como árbol de archivos, que es lo que
# lee `tools/rpgmaker/lcf.py` y de ahí el conversor. Es derivado —se puede volver a
# sacar en cualquier momento— y va a git igual, porque es la única forma de
# *leer* el juego y de que un cambio se vea en un diff.
#
# **`unpack` escribe las dos vistas y no una**, en la misma corrida: `data/` es
# la *vista resuelta* —todos los campos escritos, los defaults ya aplicados y
# los enums en número—, y el *volcado exacto* —defaults omitidos, enums por
# nombre, la forma del binario— sale a `rom/build/ditto-exacto/`, que no se
# versiona. El exacto es el único que `ditto pack` puede volver a escribir, y
# es el que hay que mirar para ver el juego con los nombres puestos.
#
# Que las dos salgan juntas no es comodidad: generadas por separado, es
# cuestión de tiempo que una sea de una corrida y la otra de otra, y
# compararlas deje de significar algo.
#
# `unpack` vacía `maps/` y `db/` antes de escribir —si no, un `Map0400.json`
# que sobró de un volcado viejo volvería a meter un mapa en el juego— y no toca
# nada más de `data/`, así que el README de ahí sobrevive.
#
# Después de correrlo, lo que manda es el diff: si el juego no cambió, tiene
# que dar vacío.
datos DIR="data" EXACTO="rom/build/ditto-exacto":
  ditto unpack "${ABL_GAME_DIR:-/extras/abl-rm}" {{EXACTO}} {{DIR}}

# Lo mismo pero a otro lado, para mirarlo sin tocar el del repo.
ditto-volcado DIR="/extras/volcado-ditto":
  just datos {{DIR}} "{{DIR}}-exacto"

# Voodoo: de un PNG indexado a tiles, tilemap y CGRAM, en Rust. Es el que
# convierte las capas de los mapas, desde las imágenes que deja el asignador.
# No decide colores; ver AGENTS.md.
#
# Sus pruebas son imágenes generadas adentro de la prueba, más los mensajes de
# error, así que no necesitan el juego.
voodoo-pruebas:
  cd tools/voodoo && cargo test

# Arma la ROM: `ca65` + `ld65`, más el checksum y la tabla de símbolos que
# leen las pruebas. Lo usan todas las recetas que ensamblan `main.s`, y también
# `pruebas/arnes/consola.py`. El mapa de memoria lo escribe el conversor al lado de
# los `.inc`. Ver tools/ensamblado/ensamblar.py.
ensamblar := "python3 tools/ensamblado/ensamblar.py"

# Dónde instala `just herramientas`. En el contenedor `/usr/local` está en el
# PATH; desde el host conviene `CARGO_ROOT=~/.cargo`, el default de cargo.
cargo_root := env_var_or_default("CARGO_ROOT", "/usr/local")
# --- Las herramientas de Rust ----------------------------------------------
# `tools/protocol/`, `tools/gunter/`, `tools/ditto/` y `tools/voodoo/` son
# proyectos aparte, y el port los consume **desde el PATH**, como consume
# python3 o un core de libretro: ningún script ni prueba de este juego llama a
# `cargo`. Se instalan una vez y quedan.
herramientas:
  cargo install --locked --path tools/protocol --root {{cargo_root}}
  cargo install --locked --path tools/gunter --root {{cargo_root}}
  cargo install --locked --path tools/ditto --root {{cargo_root}}
  cargo install --locked --path tools/voodoo --root {{cargo_root}}

# --- Super Nintendo --------------------------------------------------------
# El port. El toolchain son tres cosas: python, un core de libretro y las
# herramientas del PATH —`ca65` + `ld65` arman la ROM y `gunter` sus muestras—. La
# ROM se corre desde Python cuadro a cuadro (tools/emulador/retro.py), sin emulador con
# ventana ni servidor X.
#
# Las herramientas se instalan con `just herramientas` y no se compilan acá;
# si falta alguna, el que la busca dice cuál y cómo tenerla.

# **Todas las pruebas**, que desde el 2026-09-16 son las dos redes a la vez.
#
# Las de estado le preguntan a la ROM en qué mapa está, qué switch tiene
# prendido, qué evento corre, y no miran la pantalla. Las de la tanda
# —`pruebas/*/test_tanda*.py`— miran sólo la pantalla, contra las capturas
# congeladas de `pruebas/golden/tanda/`. Son dos redes distintas y se
# complementan: una cobra los errores de PPU —una paleta mal repartida, una
# prioridad de OAM—, la otra los de lógica, que es donde la comparación de
# pixeles se queda ciega. El recuerdo de CORE y MANTA que no arrancaba daba
# verde en la tanda entera, porque los dos lados se equivocaban igual.
#
# Las de estado se apoyan en la tabla de símbolos que deja `ensamblar`, así
# que ninguna dirección de RAM está escrita a mano: renombrar una variable en
# `main.s` hace fallar la prueba diciendo qué símbolo falta.
#
# Las pruebas no arman nada: corren contra los cartuchos de `cartuchos`, que
# se arman antes, en serie, y sólo si cambió algo de lo que los arma. **Después
# corren en paralelo**, con pytest-xdist: ver `procesos`.
pruebas *args: _xdist cartuchos
  python3 -m pytest pruebas {{xdist}} {{args}}

# Las mismas, de a una carpeta: `rpgmaker` —lo que el motor tiene que hacer
# igual que RM2k—, `abl` —lo propio del juego— y `herramientas` —las que no
# corren ninguna ROM—. Todas dependen de `cartuchos` porque una de
# herramientas, la de bancos, lee la tabla de símbolos del cartucho armado.
# Van en paralelo igual que `pruebas`: hasta `herramientas`, que no corre
# ninguna ROM, gana.
pruebas-rpgmaker *args: _xdist cartuchos
  python3 -m pytest pruebas/rpgmaker {{xdist}} {{args}}

pruebas-abl *args: _xdist cartuchos
  python3 -m pytest pruebas/abl {{xdist}} {{args}}

pruebas-herramientas *args: _xdist cartuchos
  python3 -m pytest pruebas/herramientas {{xdist}} {{args}}

# Cuántos procesos de pytest corren las pruebas a la vez. **`PROCESOS=0` es en
# serie**, en un solo proceso y sin xdist: es lo que hay que usar para depurar
# con `--pdb`, con `-s`, o para leer la salida de una prueba en orden. `just
# pruebas -n 0` hace lo mismo, porque el `-n` que llega último es el que vale.
#
# Son 8 porque son los núcleos **físicos** de esta máquina —16 hilos, 8
# núcleos—, y está medido que más no rinde: lo que tarda es el core de
# libretro emulando, que usa la CPU entera, así que el segundo hilo de cada
# núcleo no suma y cada proceso de más es memoria de más. `auto` sería 16 acá:
# sin `psutil`, xdist cuenta hilos y no núcleos.
#
# `worksteal` y no el reparto por omisión porque las pruebas duran muy
# distinto —de milisegundos a varios segundos— y con el reparto fijo la
# corrida la termina un proceso solo con la cola.
procesos := env_var_or_default("PROCESOS", "8")
xdist := if procesos == "0" { "" } else { "-n " + procesos + " --dist worksteal" }

# Si falta xdist, se corta acá, antes de armar los cartuchos, y dice qué
# instalar. **No cae a serie**, a propósito: la tanda en serie tarda varias
# veces más, y el aviso de que cayó quedaría arriba de cuatrocientas líneas de
# pytest, donde nadie lo lee. Sin el chequeo, pytest diría "unrecognized
# arguments: -n", que no dice qué falta.
_xdist:
  #!/usr/bin/env sh
  [ "{{procesos}}" = 0 ] && exit 0
  python3 -c 'import xdist' 2>/dev/null && exit 0
  echo "las pruebas corren en paralelo con pytest-xdist, y este python3 no lo tiene." >&2
  echo "en Arch: pacman -S python-pytest-xdist; con pip: pip install pytest-xdist." >&2
  echo "para correrlas en serie sin instalarlo: PROCESOS=0 just pruebas" >&2
  exit 1

# Los cartuchos de prueba, en `rom/build/pruebas-unico/`: el de pruebas, que
# lleva todos los casos de `pruebas/casos/`, y los chicos, que llevan lo que
# no entra en él. Qué va en cada uno y por qué está en `pruebas/arnes/cartuchos.py`;
# `--lista` lo imprime.
cartuchos *args:
  python3 pruebas/arnes/cartuchos.py {{args}}

# **Las decisiones artísticas del conversor, versionadas**: qué color se
# fusionó con cuál en cada mapa porque la CGRAM no daba para los dos, y a qué
# tamaño se dibuja cada animación de batalla para entrar en la caja. Los
# escribe el conversor al lado de cada ROM que arma, y esto copia a `parches/`
# —que es lo que va a git— **los de `abl` y de ningún otro**: la decisión
# versionada es la del ROM jugable, y los cartuchos de prueba se adaptan como
# puedan. Regla de taro, 2026-09-21; el porqué está en `tools/port/parches.py`.
#
# Regenerarlos es deliberado, igual que con las goldens: si fuera automático o
# lo hiciera la tanda, dejarían de avisar nada. Lo que se mira es el diff.
parches: demo
  python3 tools/port/parches.py rom/build/abl

# Y la verificación, que es lo que corre la tanda: falla diciendo **qué
# decisión cambió** —"la animación 82 se dibujaba a 64x50 y ahora se dibuja a
# 64x49"—, no que el archivo difiere. Mira todos los cartuchos que haya
# armados, porque lo versionado tiene que salir igual en todos.
parches-check *builds="rom/build/pruebas-unico rom/build/abl":
  python3 tools/port/parches.py {{builds}} --check

# **La ROM que taro juega**: la cadena entera de la apertura hasta Lashe City,
# con pantalla de título, en `rom/build/abl/abl.sfc`, que es donde él la busca.
#
# Es una sola y **siempre con título**: hasta el 2026-09-20 eran dos, con y sin,
# y la de sin no la jugaba nadie —la pantalla de título la cubren por su lado
# los cartuchos de `cartuchos`—. Es la misma decisión que dejó un solo `.sfc` en
# `pruebas-manuales/`; está en AGENTS.md.
#
# **Con el grupo de verdad, el 10**, y no con el 11 del banco de pruebas. El
# juego arranca con DummyHero y la apertura del mapa 1 lo da por sentado: con
# Kersh ya en el grupo la página automática no corre, y queda Kersh sobre negro,
# sin música y sin cámara. La referencia hace lo mismo, así que no sería un bug
# de la ROM: sería una demo mal armada. La familia `cinematica` de la tanda usa
# el 10 por la misma razón.
#
# Con cronómetro, para hacerle lugar al rojo de los dígitos. La lista de mapas es **el subárbol de "Lashe City" que entra**: el
# camino a la fábrica, el auditorio y el Director, Sector 30 y los Rat Tracks,
# Sector 27 con sus dos negocios y el galpón, la fuga del 27 y el auto, y la
# misión de los Neon Viper.
#
# **Lo que quedó afuera, y por qué**, porque acá es donde se va a mirar:
#
#   la persecución en auto   casi ninguna de sus páginas automáticas compila:
#                            leen la posición del auto con un `ControlVars` de
#                            clase 6 —coordenadas de un personaje—, que la ROM no
#                            hace, y el 49 además tiene un `KeyInputProc`. Sin
#                            eso el auto no dobla y el tráfico no aparece. De
#                            paso, sus tres mapas de 500x40 no entraban en los
#                            2 MB del cartucho. Está aparte, en `demo-carrera`.
#   los sectores con auto    a dónde lleva la elección del mapa 36. El **38 no
#                            entra en ningún reparto de VRAM**: sus tiles de
#                            fondo y de sprite más la ventana no entran en los
#                            64 KB. Y la elección del 36 es una sola página: o
#                            compilan los cuatro destinos o no compila ninguno.
demo nombre="abl":
  mkdir -p rom/build/{{nombre}}
  python3 tools/port/snes_convert.py --grupo 10 --map-id 4 \
      --mapas 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 29 30 \
              32 33 34 36 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# Es para que taro vea y escuche un build sin correrlo. Las jugadas son partes
# del nombre de las pruebas de `pruebas/abl/test_recorrido.py` —`apertura`,
# `talan`— o `quieto:N`, N ticks sin tocar nada; `--leer 150` aprieta A más
# despacio para que se lean los textos. Por qué `-O`, en `video.py`.
#
#     just video abl /shared/apertura.mp4 quieto:6000 apertura
#     just video abl /shared/textos.mp4 apertura talan --leer 150
#
# Un video con sonido de una ROM ya armada, jugando las jugadas del recorrido.
video nombre salida +jugadas:
  python3 -O pruebas/arnes/video.py rom/build/{{nombre}} {{salida}} {{jugadas}}

# La persecución en auto, que no entra en `abl` y no hace falta que
# entre: **arranca en el mapa 49**, que es donde empieza la carrera, así que se
# juega desde el primer cuadro sin tener que recorrer Lashe City.
#
# Los siete mapas son los de la escena: el 49, el 52 y el 54 son las tres
# vueltas, el 50 es la sala de choque con el "vamos de nuevo", el 51 el puente
# levantado, y el 53 el final.
#
# **Con `--grupo 14`, Talan, que es con quien el juego llega hasta acá.** Al
# entrar al 49, `RaceController1` saca del grupo a los actores que pueden estar
# ahí y mete a `CarRED` o a `CarBLUE` según el switch que él mismo prende, así
# que el héroe **es el auto**. Con el grupo de pruebas puesto, Kersh quedaría
# adentro —no está en esa lista— y el gráfico saldría mal; con el grupo inicial
# de la base, el héroe se dibuja **sin gráfico** hasta que el `PanScreen` de
# `RaceController1` termina y recién ahí entra el auto, que es un síntoma que
# taro reportó jugando.
#
# **`--inicio 1 26` es la celda por la que se entra en el juego**, y no es
# cosmético. Sin ella el conversor planta al héroe en el tile abierto más cercano
# al centro, que en este mapa cae en una fila donde **no hay ni un obstáculo** ni
# ninguno de los eventos que saltan al mapa siguiente: el auto podía cruzar las
# 500 celdas del mapa sin chocar con nada y sin llegar a ninguna parte. La celda
# sale del `Teleport [49, 1, 26]` del evento 3 del mapa 36, que es por donde el
# juego entra.
#
# **El switch 171 es lo que la hace arrancar** —lo prende la página de prueba
# `pruebas/casos/switch-171.json`—, y hay que saber por qué. El
# evento 1 del mapa 49 tiene dos páginas automáticas, una por switch, y la que
# arma el auto pide el 171. Con los dos apagados **ninguna es la activa** y el
# evento no hace nada, así que el héroe se queda siendo `DummyHero`, cuyo sprite
# es una celda vacía a propósito: pantalla sin auto. Quien lo prende en el juego
# es `RaceControllerZERO`, la intro de Talan con el cartel de los controles; esa
# página compila, y el switch sigue puesto a mano sólo porque nadie volvió a
# mirar esa escena desde entonces: sacarlo es una prueba a mano de toda la intro.
#
# **Y la carrera no corre sola**, que es lo primero que se nota jugando: el héroe
# camina libre y a la velocidad que le dejó `RaceController1`. Quien la corre es
# `RaceController2`, la única página paralela del 49 que no compila, y lo que la
# corta es el `KeyInputProc` **sin espera**; el porqué de que ese comando siga
# sin aceptarse está en `KEY_INPUT_PROC` en eventos.py.
#
# Aparte de `demo` porque el mapa inicial es otro y porque no comparte un solo
# mapa con ella: juntarlas sería un `if` en el medio de una receta que ya tiene
# la lista escrita a mano.
demo-carrera nombre="demo-carrera":
  mkdir -p rom/build/{{nombre}}
  python3 tools/port/snes_convert.py --grupo 14 --map-id 49 \
      --mapas 50 51 52 53 54 \
      --sin-titulo --inicio 1 26 \
      -o rom/build/{{nombre}}/mapdata.inc \
      --comandos-de-prueba pruebas/casos/switch-171.json
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# Las pistas de MSU-1 al lado de una ROM ya armada: el `.msu` que lo enciende
# —puede estar vacío— y un `.pcm` por tema de `PISTAS_MSU`. No va adentro de
# `demo` porque no hace falta para jugar: sin estos archivos la ROM suena
# como siempre, por el SPC700. Y porque es cara —renderiza el MIDI con
# fluidsynth y normaliza en Python— y pesa: son 10,6 MB por minuto de música.
#
# En la tarjeta del FX Pak los tres van en el mismo directorio y con el mismo
# nombre base que la ROM: renombrar el `.sfc` obliga a renombrar los otros, o
# el MSU-1 no se enciende.
#
# **Correrla de nuevo no rehace lo que no cambió**: una pista depende del MIDI,
# del soundfont, de fluidsynth y de cómo se normaliza, nada de eso es del
# cartucho, y todo eso está en la clave. Ver `clave_de_la_pista` en msu.py.
# Con `SIN_CACHE=1` se rehacen todas.
msu nombre="abl":
  python3 tools/audio/msu.py rom/build/{{nombre}}/{{nombre}}.sfc
