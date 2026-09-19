# Renderiza un mapa a un PNG. Sin dependencias que instalar:
# usa Pillow, que ya está en el sistema.
#   just render        -> mapa 1
#   just render 8
render map_id="1":
  python3 tools/render_map.py --map-id {{map_id}}

# Lista los mapas del juego con su chipset, sus eventos y los assets que falten.
maps:
  python3 tools/list_maps.py

# Lo mismo, pero renderizando todo: verifica que ningún mapa rompa el pipeline.
check:
  python3 tools/list_maps.py --render

# Los opcodes de los eventos: su número y su layout. La declaración está en
# `protocol/events.toml` y no es ni del compilador ni del intérprete; de ahí
# salen generados los dos módulos de `tools/` y los dos `.inc` de `rom/src/`,
# todos commiteados. Hay dos declaraciones: el bytecode de los eventos y el
# stream de música que lee el SPC700.
#
# `--check` es lo que corre la tanda: falla si alguno quedó viejo.
protocolo *args:
  protocol protocol/events.toml \
      --python tools/event_opcodes.py --asm rom/src/event_opcodes.inc {{args}}
  protocol protocol/music.toml \
      --python tools/music_opcodes.py --asm rom/src/music_opcodes.inc {{args}}

# Las pruebas del generador: los errores que tiene que dar ante una declaración
# rota, y la forma exacta del texto que emite. No necesitan el juego ni la ROM.
protocolo-pruebas:
  cd protocol && cargo test

# El códec BRR y el lector de SoundFont, y **el que arma las muestras de la
# ROM**. Sus pruebas son muestras generadas adentro de la prueba —silencio,
# rampa, cuadrada, impulso, saturación— más los mensajes de error, así que no
# necesitan ni el juego ni un soundfont. Que las muestras de verdad salgan bien
# lo cobra cualquier demo, porque viajan adentro del `.sfc`.
brr-pruebas:
  cd brr && cargo test

# El .ldb/.lmu/.lmt ⇄ JSON en Rust. Todavía no reemplaza a `tools/lcf.py` ni al
# conversor: convive con ellos. Ver DITTO.md, que es lo que ata a Ditto con este
# port; adentro de ditto/ no hay ni una referencia a nosotros, a propósito.
#
# El juego con el que se mide **se lo pasa el repo**, no lo sabe la herramienta:
# sin DITTO_CORPUS las pruebas que lo necesitan se saltean con un mensaje.
#
# La tanda corta va sobre una muestra de mapas; `ditto-vuelta-entera` son todos
# los mapas, el LDB y el árbol, y mide lo único que hace útil a la herramienta:
# que el binario vuelva **byte por byte**. Va aparte porque es la que uno quiere
# ver con el número, no la que corre callada.
ditto-pruebas:
  cd ditto && DITTO_CORPUS="${ABL_GAME_DIR:-/extras/abl-rm}" cargo test

ditto-vuelta-entera:
  cd ditto && DITTO_CORPUS="${ABL_GAME_DIR:-/extras/abl-rm}" cargo test --release -- --include-ignored --nocapture

# **Regenera `data/`**: el juego entero como árbol de archivos, que es lo que
# lee `tools/lcf.py` y de ahí el conversor. Es derivado —se puede volver a
# sacar en cualquier momento— y va a git igual, porque es la única forma de
# *leer* el juego y de que un cambio se vea en un diff.
#
# `unpack` vacía `maps/` y `db/` antes de escribir —si no, un `Map0400.json`
# que sobró de un volcado viejo volvería a meter un mapa en el juego— y no toca
# nada más de `data/`, así que el README de ahí sobrevive.
#
# Después de correrlo, lo que manda es el `git diff`: si el juego no cambió,
# tiene que dar vacío.
datos DIR="data":
  ditto unpack "${ABL_GAME_DIR:-/extras/abl-rm}" {{DIR}}

# Lo mismo pero a otro lado, para mirarlo sin tocar el del repo.
ditto-volcado DIR="/extras/volcado-ditto":
  just datos {{DIR}}

# De un PNG indexado a tiles, tilemap y CGRAM, en Rust: es el que convierte las
# capas de los mapas, desde las imágenes que deja el asignador. No decide
# colores; ver AGENTS.md.
#
# Sus pruebas son imágenes generadas adentro de la prueba, más los mensajes de
# error, así que no necesitan el juego.
tiles-pruebas:
  cd tiles && cargo test

# Arma la ROM: `ca65` + `ld65`, más el checksum y la tabla de símbolos que
# leen las pruebas. Lo usan todas las recetas que ensamblan `main.s`, y también
# `pruebas/consola.py`. El mapa de memoria lo escribe el conversor al lado de
# los `.inc`. Ver tools/ensamblar.py.
ensamblar := "python3 tools/ensamblar.py"

# Dónde instala `just herramientas`. En el contenedor `/usr/local` está en el
# PATH; desde el host conviene `CARGO_ROOT=~/.cargo`, el default de cargo.
cargo_root := env_var_or_default("CARGO_ROOT", "/usr/local")
# --- Las herramientas de Rust ----------------------------------------------
# `protocol/`, `brr/`, `ditto/` y `tiles/` son proyectos aparte, y el port los
# consume **desde el PATH**, como consume python3 o un core de libretro: ningún
# script ni prueba de este juego llama a `cargo`. Se instalan una vez y quedan.
herramientas:
  cargo install --locked --path protocol --root {{cargo_root}}
  cargo install --locked --path brr --root {{cargo_root}}
  cargo install --locked --path ditto --root {{cargo_root}}
  cargo install --locked --path tiles --root {{cargo_root}}

# --- Super Nintendo --------------------------------------------------------
# El port. El toolchain son tres cosas: python, un core de libretro y las
# herramientas del PATH —`ca65` + `ld65` arman la ROM y `brr` sus muestras—. La
# ROM se corre desde Python cuadro a cuadro (tools/retro.py), sin emulador con
# ventana ni servidor X.
#
# Las herramientas se instalan con `just herramientas` y no se compilan acá;
# si falta alguna, el que la busca dice cuál y cómo tenerla.

# Con qué grupo arrancan las pruebas. En RM2k el gráfico del héroe es el del
# primero del grupo, y este juego arranca con el actor 10 —`DummyHero`, cuyo
# sprite en Chubby2 es una celda **vacía a propósito**: la apertura es una
# cinemática y ahí no hay personaje que mostrar—. Fiel, pero con él ninguna
# prueba verificaría un solo sprite del héroe: se irían las poses, el ciclo de
# caminata y la prioridad de objeto contra la capa de encima.
#
# Así que las pruebas arrancan con Kersh, el actor 11, que es a quien el jugador
# maneja después de la cinemática. Es una decisión de banco de pruebas y por eso
# está acá y no escondida en un default. Las pruebas de pytest lo arman con la
# página de prueba `pruebas/casos/grupo-11.json`: ver `pruebas/tanda.py`.
grupo    := env_var_or_default("GRUPO", "11")
# Con qué core de libretro corre `shot`, que es la única receta que corre la
# ROM: todo lo demás vive en pytest y toma el core de `NUCLEO`, ver
# `pruebas/consola.py`. snes9x es el de siempre porque emula muchísimos más
# cuadros por segundo que bsnes —2747 contra 121—, y para mirar una captura con
# otro core alcanza con `CORE=bsnes just shot ...`.
#
# Los tres que hay instalados —snes9x, bsnes y mesen-s— dibujan el mismo cuadro
# a 15 bits, y eso ya no es una afirmación de un comentario: lo comprueba
# `pruebas/test_cores.py`, que corre la misma ROM en snes9x y en bsnes y compara
# las dos pantallas entre sí. Ver `tools/retro.py` para lo que hay que forzarle
# a cada uno, y ese archivo para por qué mesen-s queda afuera.
core     := env_var_or_default("CORE", "snes9x")
nucleo   := "/usr/lib/libretro/" + core + "_libretro.so"
# Una corrida aislada. `CORRIDA=algo just <receta>` deja el mapdata, la ROM y las
# capturas adentro de `rom/build/algo/` y no toca nada de lo de siempre; sin
# CORRIDA, todo queda donde estaba, para que `mednafen rom/build/abl.sfc` y las
# rutas escritas en el README sigan valiendo. Existe porque
# `rom/build/inc/mapdata.inc` es de todos —lo pisa cualquier `convert`— y sin
# esto no se puede compilar mientras algo corre.
corrida  := env_var_or_default("CORRIDA", "")
snes_dir := if corrida == "" { "rom/build" } else { "rom/build" / corrida }
snes_rom := snes_dir / (if corrida == "" { "abl.sfc" } else { corrida + ".sfc" })
snes_inc := if corrida == "" { "rom/build/inc" } else { snes_dir }
snes_pngs := if corrida == "" { "rom/shots" } else { snes_dir / "shots" }

# ChipSet + mapa -> tiles de 8x8 a 8bpp, paleta de 15 bits y tilemap, más el
# render de Python contra el que se compara después.
convert mapa="7":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc \
      --reference {{snes_pngs}}/python.png

build:
  {{ensamblar}} rom/src/main.s -I {{snes_inc}} -o {{snes_rom}} --simbolos {{snes_rom}}.sym

# Corre la ROM sin pantalla y captura lo que dibuja. Las teclas se mantienen
# apretadas mientras corre, para capturar con la cámara movida.
shot nombre="mapa" cuadros="240" teclas="":
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --cuadros {{cuadros}} --teclas $(echo "{{teclas}}" | tr 'A-Z' 'a-z')

# La captura contra el render de Python, pixel por pixel y a 15 bits.
compare nombre="mapa" x="0" y="0":
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png {{snes_pngs}}/python.png \
      --camara {{x}} {{y}} -o {{snes_pngs}}/comparacion-{{nombre}}.png

# El tinte solo, contra la cuenta de Python y sin referencia de por medio: toma
# la misma pantalla capturada de la consola sin teñir y teñida, y pregunta si la
# transformación de una a la otra es exactamente canal * valor / 100 sobre los
# 15 bits. Es una segunda opinión sobre evento, que compara un camino
# entero; si evento falla y esto da cero, el tinte no es el problema.
#
# La captura sin teñir sale de plantar al héroe en el destino del
# teletransporte, que es la misma pantalla sin el evento. Quien la quiera hoy
# la arma desde `pruebas/tanda.py` con un caso que empiece con un `Teleport`
# a (7,65) del mapa 1: la receta `parado` que la sacaba se fue con la mudanza
# a pytest.
tinte sin="rom/shots/destino.png" con="rom/shots/evento.png" r="0" g="0" b="100":
  python3 tools/snes_tinte.py {{sin}} {{con}} --tinte {{r}} {{g}} {{b}}

# Cuánto destraba cada comando de evento que todavía no hacemos: cuántas páginas
# pasan a compilar **enteras** si se hiciera.
#
# Es lo que decide por dónde seguir, y no es lo mismo que la tabla de "Lo que
# falta" del README, que cuenta qué comando corta **primero** cada página: una
# cortada por un cuadro de texto puede estar cortada además por otras cuatro
# cosas.
#
# Se corre después de cada feature nueva: el orden cambia a medida que las
# páginas se van destrabando entre ellas.
#
# Al final imprime aparte **qué órdenes de `MoveCommand` faltan**, sobre todas
# las páginas del juego. Es la pregunta de adentro de `MoveEvent`, y está acá
# porque la respuesta cambia de signo de un día para el otro: un número viejo de
# esta pregunta ya mandó a hacer trabajo que no existía.
destraba:
  python3 tools/destraba.py

# El juego original corriendo en EasyRPG, capturado sin pantalla, y nuestra
# ventana comparada contra eso.
#
# Es el único oráculo externo del repo: todo lo demás compara la ROM contra
# nuestra propia referencia, y si las dos se equivocan igual da cero. Esto ya lo
# cobró: encontró que el índice 0 de la paleta del System es transparente —el
# marco salía naranja y macizo donde el juego lo tiene de 2 px— y que la fuente
# del juego es rmg2000 y no ttyp0, que era lo que decía el camino del código que
# leí. Las dos veces la ventana se veía perfectamente bien.
#
# No entra en `just pruebas` y es a propósito: levanta un Xvfb, corre el juego
# durante medio minuto y depende de EasyRPG bajado a /extras. Se corre a mano
# cuando se toca la ventana o la fuente. El detalle está en `rom/easyrpg.sh`.
#
# Lo único que puede diferir sin ser un error es la flecha roja de "seguir" que
# EasyRPG anima mientras espera al jugador, que nosotros no dibujamos.
oraculo mapa="145" segundos="20":
  #!/usr/bin/env bash
  set -euo pipefail
  rom/easyrpg.sh {{mapa}} {{segundos}}
  # De la tanda de capturas, la que tenga texto en la franja de la ventana.
  # La última con ventana, no la que más texto tenga: sin avanzar, el primer
  # mensaje se queda quieto esperando, así que las de más al final lo tienen
  # entero y ya terminó de escribirse letra por letra.
  #
  # Y "con ventana" se decide por la esquina del marco y no por cuánto blanco
  # hay abajo: en un mapa claro el piso solo pasaba cualquier umbral de brillo
  # y la comparación terminaba midiendo la ventana contra el suelo.
  mejor=$(python3 - <<'PY'
  import glob, sys
  sys.path.insert(0, "tools")
  from PIL import Image
  import lcf, ventana
  skin = ventana.skin("/extras/abl-rm",
                      lcf.Database("/extras/abl-rm/RPG_RT.ldb").system_name)
  esquina = ventana.ventana(skin, 320, 80).convert("RGB").crop((0, 0, 8, 8))
  patron = list(esquina.get_flattened_data())
  ultima = ""
  for f in sorted(glob.glob("/extras/capturas/easyrpg/*.png")):
      im = Image.open(f).convert("RGB")
      if list(im.crop((0, im.height - 80, 8, im.height - 72))
              .get_flattened_data()) == patron:
          ultima = f
  print(ultima)
  PY
  )
  test -n "$mejor" || { echo "ninguna captura tiene una ventana de mensaje"; exit 1; }
  echo "la captura con más texto: $mejor"
  python3 tools/snes_mensaje.py --map-id {{mapa}} --indice 0 --contra "$mejor" \
      -o {{snes_pngs}}/oraculo-{{mapa}}.png

# Una página de mensaje del juego, dibujada como la dibujaría RM2k.
#
# Todavía no hay nada del lado de la ROM, así que esto no compara nada: existe
# para poder poner nuestra ventana **al lado de una captura de EasyRPG** de esa
# misma página. Es la única forma de salir del agujero de siempre —si la
# referencia y la ROM se equivocan igual, la comparación da cero—, y acá el
# tercero en discordia es el juego original.
#
#   just mensaje 1        la primera página de mensaje del mapa 1
#   just mensaje 1 4 4    la quinta, agrandada cuatro veces
mensaje mapa="1" indice="0" escala="1":
  mkdir -p {{snes_pngs}}
  python3 tools/snes_mensaje.py --map-id {{mapa}} --indice {{indice}} \
      --escala {{escala}} -o {{snes_pngs}}/mensaje-{{mapa}}-{{indice}}.png

# Pasa todos los mapas del juego por los límites del hardware sin armar ninguna
# ROM: dice
# cuáles no entran y por qué. Correr cuando se toque el conversor o el reparto
# de la VRAM.
relevar desde="0":
  python3 tools/snes_survey.py --desde {{desde}}

# Cuánto llega a caminar el héroe en cada mapa, con las mismas reglas que la
# ROM. Sirve para elegir contra qué mapa probar el redibujado: uno enorme lleno
# de paredes frena en la tercera celda y no prueba nada.
recorrido desde="66":
  python3 tools/snes_recorrido.py --desde {{desde}}

# Cuánto ocuparía en el cartucho el arte del juego, por rubro. Sin argumento
# los lista.
#
# No es una prueba: no falla nunca. Es la medición de la que sale la estrategia
# de `assets/README.md`, y está acá para que se pueda repetir cuando el material
# o el criterio cambien. Tarda minutos: expandir los ChipSets a su atlas y
# recorrerlos pixel por pixel no es barato.
assets-medir que="todo":
  python3 assets/medir.py {{que}}

# **Todas las pruebas**, que desde el 2026-09-16 son las dos redes a la vez.
#
# Las de estado le preguntan a la ROM en qué mapa está, qué switch tiene
# prendido, qué evento corre, y no miran la pantalla. Las de la tanda
# —`pruebas/test_tanda*.py`— miran sólo la pantalla, contra las capturas
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
# se arman antes, en serie, y sólo si cambió algo de lo que los arma.
pruebas *args: cartuchos
  python3 -m pytest pruebas {{args}}

# Las mismas, de a una carpeta: `rpgmaker` —lo que el motor tiene que hacer
# igual que RM2k—, `abl` —lo propio del juego— y `herramientas` —las que no
# corren ninguna ROM—. Todas dependen de `cartuchos` porque una de
# herramientas, la de bancos, lee la tabla de símbolos del cartucho armado.
pruebas-rpgmaker *args: cartuchos
  python3 -m pytest pruebas/rpgmaker {{args}}

pruebas-abl *args: cartuchos
  python3 -m pytest pruebas/abl {{args}}

pruebas-herramientas *args: cartuchos
  python3 -m pytest pruebas/herramientas {{args}}

# Los cartuchos de prueba, en `rom/build/pruebas-unico/`: el de pruebas, que
# lleva todos los casos de `pruebas/casos/`, y los chicos, que llevan lo que
# no entra en él. Qué va en cada uno y por qué está en `pruebas/cartuchos.py`;
# `--lista` lo imprime.
cartuchos *args:
  python3 pruebas/arnes/cartuchos.py {{args}}

# Todo el camino del mapa: convertir, compilar, y verificar la cámara en las
# cuatro esquinas a las que puede llegar.
#
# Cada dirección se mantiene apretada hasta que la cámara choca contra el borde
# del mapa, así que dónde tiene que quedar no se estima: es exactamente
# CAM_MAX_X y CAM_MAX_Y, que salen del tamaño del mapa. Si la ROM se moviera de
# más, de menos, o no frenara, la comparación falla.
mapa mapa="7" cuadros="300":
  just convert {{mapa}}
  just build
  just shot {{mapa}}-centro {{cuadros}}
  just compare {{mapa}}-centro 0 0
  just shot {{mapa}}-derecha {{cuadros}} "Right"
  just compare {{mapa}}-derecha $(just _cam-x) 0
  just shot {{mapa}}-abajo {{cuadros}} "Down"
  just compare {{mapa}}-abajo 0 $(just _cam-y)
  just shot {{mapa}}-esquina {{cuadros}} "Right Down"
  just compare {{mapa}}-esquina $(just _cam-x) $(just _cam-y)

# Los topes de la cámara salen del .inc que generó el conversor, así que las
# recetas no repiten números que dependen del mapa.
_cam-x:
  @grep -oP 'CAM_MAX_X\s*=\s*\K\d+' {{snes_inc}}/mapdata.inc
_cam-y:
  @grep -oP 'CAM_MAX_Y\s*=\s*\K\d+' {{snes_inc}}/mapdata.inc

# Las dos ROMs que taro juega: `demo-ciudad`, la cadena entera de la apertura
# hasta Lashe City, y `demo-titulo`, la misma con pantalla de título. Van a
# `rom/build/<nombre>/`, que es donde él las busca.
#
# **Con el grupo de verdad, el 10**, y no con el 11 del banco de pruebas. El
# juego arranca con DummyHero y la apertura del mapa 1 lo da por sentado: con
# Kersh ya en el grupo la página automática no corre, y queda Kersh sobre negro,
# sin música y sin cámara. La referencia hace lo mismo, así que no sería un bug
# de la ROM: sería una demo mal armada. `cinematica` usa el 10 por la misma
# razón.
#
# Con cronómetro, para hacerle lugar al rojo de los dígitos; ver "Lashe City" en
# ESTADO.md. La lista de mapas es **el subárbol de "Lashe City" que entra**: el
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
demo nombre="demo-ciudad" titulo="":
  #!/usr/bin/env bash
  set -euo pipefail
  titulo="{{titulo}}"
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 10 --map-id 4 \
      --mapas 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 29 30 \
              32 33 34 36 \
      --con-timer ${titulo:+--con-titulo} \
      -o rom/build/{{nombre}}/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# La persecución en auto, que no entra en `demo-ciudad` y no hace falta que
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
  python3 tools/snes_convert.py --grupo 14 --map-id 49 \
      --mapas 50 51 52 53 54 \
      --con-timer --inicio 1 26 \
      -o rom/build/{{nombre}}/mapdata.inc \
      --comandos-de-prueba pruebas/casos/switch-171.json
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# La cinemática de los Neon Vipers. **El mapa es el 14, `NV Get Talan to Work`**,
# no el 11: la escena pasa en la calle de enfrente del escondite de los Lazer
# Teeth, y eso es lo que la hace parecer parte del HQ.
#
# Un solo mapa y sin nada que apretar para llegar: la página del `SceneDriver` es
# **automática y sin condición**, así que arranca sola al entrar. Lo único que
# hace el jugador es apretar A cuadro por cuadro.
#
# Sirve para ver la escena entera y no para reproducir el defecto del cuadro de
# texto que cae sobre el borde de banco del bloque de textos: **con un mapa solo
# el bloque no llega a cruzar**. Para eso están `demo-ciudad`, que es la que taro
# jugó, y el caso `texto-cruza` de la tanda.
#
# `--grupo 14` es Talan, igual que en la carrera y en las piedras.
demo-vipers nombre="demo-vipers":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 14 \
      --con-timer \
      -o rom/build/{{nombre}}/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# El minijuego de las piedras del `Lazer Teeth HQ`, para jugarlo sin caminar
# media Lashe City. Un solo mapa —el 11— y el héroe **parado abajo de la reja**.
#
# Cómo se juega, que es lo que el juego mismo explica en el cuadro de texto:
# apretar A mirando la reja —Talan agarra tres piedras y prende el switch 43,
# que es lo que activa el motor del minijuego—, y después **A y enseguida una
# dirección** para tirar una. La piedra vuela en esa dirección hasta chocar, y
# los cuatro `Block*` de (31..33, 55..56) son adonde va a parar.
#
# **`--inicio 26 52` es la celda de abajo de `Grate1`**, que está en (26,51) y
# es pared: al entrar, Talan mira para abajo, así que hay que tocar arriba una
# vez —que lo gira sin moverlo, porque la reja no se pisa— y después A.
#
# `--grupo 14` es Talan, que es con quien el juego llega hasta acá, igual que
# en `demo-carrera`. Con el grupo de pruebas el héroe sería Kersh.
#
# Aparte de `demo` por lo mismo que la carrera: el mapa inicial es otro y
# la lista de mapas no se parece en nada.
demo-piedras nombre="demo-piedras":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 11 \
      --con-timer --inicio 26 52 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# Los cofres del Sector 30 y de los Rat Tracks, para probar la colisión sin
# cruzar media Lashe City. Tres mapas —el 20, el 21 y el 26— y el héroe parado
# **al lado del Slum30Chest1c**, en (80,19).
#
# Lo que la hace distinta de entrar caminando: **arranca con la bandera de
# atravesar paredes prendida**, que es el estado en el que el Hover-Tram deja a
# la partida —ver "Atravesar paredes vale mientras dura la ruta" en README.md—.
# La página de prueba le fuerza al héroe una ruta de una sola orden, la 36, sin
# un solo paso; no se ve ni se oye nada. Con la ROM de antes del 2026-09-13, con
# esa bandera puesta se le camina por encima a todos los eventos del cartucho;
# con ésta, a ninguno.
#
# `--grupo 14` es Talan, que es con quien el juego llega hasta acá.
demo-cofres nombre="demo-cofres":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 20 --mapas 21 26 \
      --con-timer --inicio 80 19 \
      -o rom/build/{{nombre}}/mapdata.inc \
      --comandos-de-prueba pruebas/casos/atravesar-sin-paso.json
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# La misma demo que `demo-ciudad` pero **arrancando en el mapa que se le diga**,
# para escuchar su tema sin tener que caminar hasta ahí.
#
#   just musica 20 wb3shop
#   just musica 20 wb3shop banco-entero
#
# **El tema se pasa a mano y no sale del mapa**: la mayoría de esos mapas no
# tiene BGM propia en el LDB —la prende un `PlayBGM` de una de sus páginas— así
# que arrancar ahí sin `--tema-de-arranque` deja la ROM muda hasta que corra esa
# página, que suele pedir switches de la historia.
#
# **Lleva los mismos mapas que `demo-ciudad` a propósito, y
# `--banco-sin-prioridad`.** El tema suena distinto según con cuántos comparta el
# banco de muestras: una ROM de un mapa solo le da el banco entero y no reproduce
# lo que taro oye. Y arrancar en un mapa le daba **prioridad** a su tema
# —`build_varios` se la da al del mapa de arranque— así que sonaba entero, que es
# justo lo contrario de lo que hay que escuchar. Ver "El paquete de audio de cada
# mapa" en el README.
#
# `banco-entero` es la comparación que hay que hacer de oído: sin él los temas
# del final de la lista no aportan ninguna muestra y se les caen del stream las
# notas cuyo programa no está; con él no se le cae ninguna nota a nadie y lo que
# baja es la resolución de todas.
musica mapa tema banco="":
  #!/usr/bin/env bash
  set -euo pipefail
  nombre="musica-{{mapa}}-{{tema}}{{ if banco == "" { "" } else { "-banco-entero" } }}"
  # La tabla de mapas es **la de `demo-ciudad`, en su orden**, y el mapa donde
  # arranca se elige con `--inicial`, que es un índice en esa tabla. No con
  # `--map-id`: ése pone al mapa primero en la tabla, y el orden de la tabla es
  # el orden en que se numeran los temas, así que el tema del mapa elegido
  # quedaba **primero de la lista** y por lo tanto entre los que sí aportan al
  # banco. Medido: `musica-20` armada con `--map-id 20` daba `wb3shop` al 100%.
  tabla="4 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 29 30 32 33 34 36"
  inicial=$(echo $tabla | tr ' ' '\n' | grep -nx "{{mapa}}" | cut -d: -f1)
  if [ -z "$inicial" ]; then echo "el mapa {{mapa}} no está en demo-ciudad"; exit 1; fi
  inicial=$((inicial - 1))
  mkdir -p rom/build/$nombre
  python3 tools/snes_convert.py --grupo 10 --map-id 4 \
      --mapas 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 29 30 \
              32 33 34 36 \
      --inicial $inicial --tema-de-arranque {{tema}} \
      --con-timer --banco-sin-prioridad \
      {{ if banco == "" { "" } else { "--banco-entero" } }} \
      -o rom/build/$nombre/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/$nombre \
      -o rom/build/$nombre/$nombre.sfc \
      --simbolos rom/build/$nombre/$nombre.sfc.sym

# El cofre trampa de los Rat Tracks B1, al lado del héroe: la demo más corta
# posible para ver el Game Over de la pelea que ese cofre abre. Arranca pegado al
# `RatTrackChest6c`; con mirar hacia arriba y apretar A la pelea empieza, y con
# Talan solo —y la huida prohibida por la página— se pierde en unos segundos.
#
# Es lo que reprodujo el cuelgue de perder ahí, que dejaba la consola clavada en
# el arranque con el mapa dibujado y el juego muerto. El porqué está en `main.s`,
# en el `APU_CMD_IPL` que `reset` manda antes de `spc_upload`. Lleva también el
# mapa 26 para poder seguir a los Rat Tracks B2 y probar de paso el jefe, que
# pierde igual.
demo-trampa nombre="demo-trampa":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 21 --mapas 26 \
      --con-timer --inicio 22 36 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{ensamblar}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# Las dos de una vez.
demos:
  just demo demo-ciudad
  just demo demo-titulo 1

# Las pistas de MSU-1 al lado de una ROM ya armada: el `.msu` que lo enciende
# —puede estar vacío— y un `.pcm` por tema de `PISTAS_MSU`. No va adentro de
# `demo` porque no hace falta para jugar: sin estos archivos la ROM suena
# como siempre, por el SPC700. Y porque es cara —renderiza el MIDI con
# fluidsynth y normaliza en Python— y pesa: son 10,6 MB por minuto de música.
#
# En la tarjeta del FX Pak los tres van en el mismo directorio y con el mismo
# nombre base que la ROM: renombrar el `.sfc` obliga a renombrar los otros, o
# el MSU-1 no se enciende.
msu nombre="demo-ciudad":
  python3 tools/msu.py rom/build/{{nombre}}/{{nombre}}.sfc

# La música de un mapa a mano: el MIDI a muestras BRR y un stream para el DSP.
# Normalmente no hace falta —`convert` ya la genera junto con el mapdata, que es
# lo que garantiza que los dos describan la misma ROM—; esto queda para mirar un
# tema suelto sin armar nada más.
music mapa="67":
  mkdir -p {{snes_inc}}
  python3 tools/snes_music.py --map-id {{mapa}} -o {{snes_inc}}/musicdata.inc

# Corre la ROM sin pantalla, graba el audio y compara lo que suena contra el
# MIDI. Sirve para verificar sin escuchar: para cada nota que debería estar
# sonando se mide su energía y la de un señuelo un cuarto de tono más arriba.
audio-check mapa="67" segundos="60" tema="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  cual=""
  if [ -n "{{tema}}" ]; then cual="--tema {{tema}}"; fi
  rom/record.sh {{snes_rom}} {{snes_pngs}}/tema.wav {{segundos}}
  python3 tools/snes_check.py {{snes_pngs}}/tema.wav --map-id {{mapa}} $cual

# Cada tema del cartucho, escuchado desde el arranque.
#
# El cartucho lleva varios y todos comparten el banco de muestras, así que lo que
# hay que verificar de cada uno no es "suena algo" sino que **sus notas salgan
# del banco compartido**: los índices de muestra que su stream escribe son los
# del banco de todos, no los de uno propio.
#
# `--tema-de-arranque` está para esto: `audio-check` escucha desde el arranque, y
# los mapas de las primeras secuencias no traen música propia —la prende un
# `PlayBGM`—, así que sin el flag la ROM sale callada y no hay qué medir. El flag
# no toca el bytecode: es el mismo stream, prendido antes.
bgm tema="escape_newyork" mapa="4" mapas="1 2 3" segundos="40":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mapas {{mapas}} --tema-de-arranque {{tema}} -o {{snes_inc}}/mapdata.inc
  just build
  rom/record.sh {{snes_rom}} {{snes_pngs}}/bgm-{{tema}}.wav {{segundos}}
  python3 tools/snes_check.py {{snes_pngs}}/bgm-{{tema}}.wav \
      --map-id {{mapa}} --tema {{tema}}

# El mismo MIDI tocado por FluidSynth en la PC, con el mismo SoundFont del que
# salen nuestras muestras, y medido con la misma vara. Es el techo: dice cuánto
# de lo que falta es culpa nuestra y cuánto es de la medición.
referencia mapa="67" banco="/extras/soundfonts/Microsoft GS Wavetable Synth.sf2":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  fluidsynth -F rom/shots/referencia.wav -r 48000 \
      "{{banco}}" \
      "$(python3 tools/midi_path.py --map-id {{mapa}})"
  python3 tools/snes_check.py rom/shots/referencia.wav --map-id {{mapa}}

# Todo junto: convertir, compilar y verificar.
audio mapa="67": (music mapa) build (audio-check mapa)

# La ROM en una ventana, con sonido. Va en el host: acá adentro no hay
# dispositivo de audio, y el ALSA propio de mednafen abre hw:0.
play:
  mednafen -command.exit "keyboard 0x0 20+ctrl" -sound.driver sdl {{snes_rom}}
