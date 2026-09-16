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

# De un PNG a tiles, paletas y tilemap, en Rust. **Todavía no reemplaza a
# nadie**: `tools/pixeles.py` y el empaquetado de `tools/snes_convert.py` siguen
# siendo los que arman la ROM, y ninguna receta de compilación llama a esto.
#
# Sus pruebas son imágenes generadas adentro de la prueba —una celda sólida, una
# espejada, una que hay que fusionar, una que no entra— más los mensajes de
# error, así que no necesitan el juego. Lo que sí lo necesita es la comparación
# contra el Python, que va por `TILES_CORPUS`: un directorio de llamadas
# grabadas, y sin la variable esas pruebas se saltean con un mensaje, igual que
# `DITTO_CORPUS`.
tiles-pruebas:
  cd tiles && cargo test

# El ensamblador de 65816, y **el único que arma las ROMs**: todas las recetas
# que ensamblan `main.s` lo llaman a él, y también `pruebas/consola.py`, que
# arma las suyas desde pytest. Se instala con `just herramientas` y se usa desde
# el PATH. Adentro de w65/ no hay una sola mención a este juego ni a la SNES,
# igual que en ditto/ y protocol/, y por eso sus flags están en inglés
# —`--include`, `--symbols`, `--no-checksum`—.
#
# Tiene fecha de vencimiento: el port va a pasar a `ca65` + `ld65`, por preferir
# un proyecto mantenido antes que sostener el nuestro. Lo que falta para eso es
# `.bloque` —el acomodo de bloques en bancos—, que cae en el asignador.
w65 := "w65"

# Dónde instala `just herramientas`. En el contenedor `/usr/local` está en el
# PATH; desde el host conviene `CARGO_ROOT=~/.cargo`, el default de cargo.
cargo_root := env_var_or_default("CARGO_ROOT", "/usr/local")
# --- Las herramientas de Rust ----------------------------------------------
# `w65/`, `protocol/`, `brr/` y `ditto/` son proyectos aparte, y el port los
# consume **desde el PATH**, como consume python3 o un core de libretro: ningún
# script ni prueba de este juego llama a `cargo`. Se instalan una vez y quedan.
herramientas:
  cargo install --locked --path w65 --root {{cargo_root}}
  cargo install --locked --path protocol --root {{cargo_root}}
  cargo install --locked --path brr --root {{cargo_root}}
  cargo install --locked --path ditto --root {{cargo_root}}

w65-pruebas:
  cd w65 && cargo test

# --- Super Nintendo --------------------------------------------------------
# El port. El toolchain son tres cosas: python, un core de libretro y las
# herramientas de Rust del PATH —`w65` arma la ROM y `brr` sus muestras—. La
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
# está acá y no escondida en un default: `GRUPO=10 just hitos` corre con el
# grupo de verdad.
grupo    := env_var_or_default("GRUPO", "11")
# Con qué core de libretro se corre. snes9x es el de la tanda porque emula
# muchísimos más cuadros por segundo que bsnes, que con la tanda entera es la
# diferencia entre minutos y media hora; bsnes entra por la receta `bsnes`, que
# corre unos pocos casos. Para mirar cualquier otro caso con otro core:
# `CORE=bsnes just evento 4 1 otro`. Los tres que hay instalados —snes9x,
# bsnes y
# mesen-s— dibujan el mismo cuadro a 15 bits; ver `tools/retro.py`. Para un
# caso que ya vive en pytest, el core sale de `NUCLEO`: ver `pruebas/consola.py`.
core     := env_var_or_default("CORE", "snes9x")
nucleo   := "/usr/lib/libretro/" + core + "_libretro.so"
# Una corrida aislada. `CORRIDA=algo just hitos` deja el mapdata, la ROM y las
# capturas adentro de `rom/build/algo/` y no toca nada de lo de siempre; sin
# CORRIDA, todo queda donde estaba, para que `mednafen rom/build/abl.sfc` y las
# rutas escritas en el README sigan valiendo. Existe porque
# `rom/src/mapdata.inc` es estado global —lo pisa cualquier `convert`— y sin
# esto no se puede compilar mientras algo corre.
corrida  := env_var_or_default("CORRIDA", "")
snes_dir := if corrida == "" { "rom/build" } else { "rom/build" / corrida }
snes_rom := snes_dir / (if corrida == "" { "abl.sfc" } else { corrida + ".sfc" })
snes_inc := if corrida == "" { "rom/src" } else { snes_dir }
snes_pngs := if corrida == "" { "rom/shots" } else { snes_dir / "shots" }

# ChipSet + mapa -> tiles de 8x8 a 8bpp, paleta de 15 bits y tilemap, más el
# render de Python contra el que se compara después.
# `--descartar-eventos` porque el mapa 8 tiene `PawnDoorTop`, que cambia de
# gráfico entre sus páginas y no entra en las ocho paletas de sprite: sin el
# flag el conversor corta, que es lo que se quiere en un build de verdad. Acá se
# está mirando cómo se dibuja el héroe y da lo mismo, así que se deja pasar.
convert mapa="7":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc \
      --descartar-eventos --reference {{snes_pngs}}/python.png

build:
  {{w65}} rom/src/main.s -I {{snes_inc}} -o {{snes_rom}} --symbols {{snes_rom}}.sym

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
# la arma con `--inicio 7 65` desde `pruebas/tanda.py`: la receta `parado` que
# la sacaba se fue con la mudanza a pytest.
tinte sin="rom/shots/destino.png" con="rom/shots/evento.png" r="0" g="0" b="100":
  python3 tools/snes_tinte.py {{sin}} {{con}} --tinte {{r}} {{g}} {{b}}

# El intérprete de eventos, para mirarlo con los ojos. El juego arranca en el
# mapa 4, una habitación vacía y negra cuyo único trabajo es prender dos
# switches, teñir la pantalla y teletransportar: es la página que abre A Blurred
# Line. Lo que se ve al arrancar es el mapa destino ya teñido, sin haber tocado
# una tecla.
#
# Los dos mapas tienen que estar en la ROM: un teletransporte a un mapa que no
# entró no se puede compilar, y entonces la página no se emite y el evento no
# hace nada. Con el mapa 4 solo, la pantalla se queda en negro y eso es correcto.
#
# Después de esto, `just play` lo muestra con sonido.
evento origen="4" destino="1" nombre="evento":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just build
  just shot {{nombre}} 240 ""
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Un mensaje de verdad: se abre desde el intérprete, bloquea la página, y se
# cierra cuando el jugador aprieta A. Es lo que `ventana` no prueba, que allá la
# ventana se abre y se queda, así que lo único que se compara es el dibujo.
#
# Los dos cuadros son la ventana en pantalla con la página frenada, y la ventana
# borrada con el tinte de atrás ya puesto, o sea que apretar A la cerró y la
# página siguió. Ese segundo es el único que ejercita `flush_video` apagando el
# HDMA de la ventana cuando `msg_abierto` vuelve a cero.
#
# A se deja apretado: la ROM cierra con el flanco —`pad_a` contra `pad_a_ant`,
# que es el `IsTriggered` de RM2k— y la referencia modela ese mismo único flanco.
#
# Con una dirección en vez de `none` se prueba además que **el pad no mueva al
# héroe mientras hay un mensaje**, que es el guard de
# `Game_Player::UpdateNextMovementAction`; la ruta forzada es otra cosa y sí
# camina, porque allá `UpdateMoveRoute` corre antes del guard. Con dirección el
# arranque no puede ser cero: la cruceta se mantiene apretada desde que termina,
# y antes de que la página abra el mensaje el héroe daría pasos que la referencia
# no modela. El 115 es el de todas las recetas desde que el arranque de la ROM es
# fijo —ver "El arranque dura siempre lo mismo" en el README—: el cuadro N de la
# captura es el tick N de la referencia, en cualquier mapa.
cerrar mapa="7" apretar="200" nombre="cerrar" direccion="none" arranque="115":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  linea1="SEWELL"
  linea2="There you are, Talan. Ready for"
  linea3="the big night?"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --pagina-de-prueba 0 0 0 50 -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --walk {{direccion}} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --pagina-de-prueba 0 0 0 50 --cuadros 60 400 --apretar-a {{apretar}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in 60 400; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk {{direccion}} --cuadros $n --arranque {{arranque}} \
        --apretar-a {{apretar}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La pantalla de batalla, contra `pantallas.py --batalla`. Es el hermano de
# `guardar` y de `menu`: la pelea bloquea adentro del intérprete y **no cuesta
# ningún tick**, así que no se puede comparar contra `snes_expect.py` —de ese lado
# no hay nada dibujado, a propósito: ver `OP_BATTLE` en tools/eventos.py—. Lo que
# se compara es la pantalla, contra la misma función que la modela.
#
# La pelea se abre desde la página de prueba y no desde un evento del juego: la
# única que el jugador alcanza hoy es la del droide del mapa 2, así que sin esta
# receta una tropa de más de un enemigo no la ejercitaría nada. Los dos casos son
# el menú de órdenes y el cursor de blanco sobre un enemigo, que ejercita el modo
# que el otro no toca.
#
# `relleno` son textos muertos delante del bloque de textos de las pantallas, que
# es lo que corre los índices de la batalla más allá del 255, donde la tabla
# `ba_orden_txt` los truncaba y el menú dibujaba textos encimados. **Va de un solo
# lado**, al revés que `--relleno-de-mensajes`: la referencia escribe caracteres y
# no modela ningún índice de texto.
batalla tropa="86" grupo="11 12 13" espera="20" cuadros="200" toques="" nombre="batalla" fondo="ABLBackdropSJ03" mapas="" items="" ref="--modo 1 --blanco 2" relleno="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  toques="{{toques}}"
  mapas="{{mapas}}"
  items="{{items}}"
  relleno="{{relleno}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id 6 --con-ventana \
      ${mapas:+--mapas $mapas} ${items:+--items-de-prueba $items} \
      ${relleno:+--relleno-de-textos $relleno} \
      --pagina-de-prueba {{espera}} 0 0 0 --batalla-de-prueba {{tropa}} \
      --fondo-de-prueba "{{fondo}}" \
      -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/pantallas.py -o $pre.esperado.png --batalla {{tropa}} \
      --fondo "{{fondo}}" \
      --grupo $(echo "{{grupo}}" | tr ' ' ',') \
      ${items:+--items $(echo "$items" | awk '{for(i=1;i<NF;i+=2) printf "%s%s:%s", (i>1?",":""), $i, $(i+1)}')} \
      ${toques:+{{ref}}}
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --cuadros {{cuadros}} --sin-contador --walk none \
      ${toques:+--toques-hardware {{toques}}}
  python3 tools/snes_compare.py $pre.png $pre.esperado.png \
      -o $pre.comparacion.png

# La pelea **peleada hasta el final**, y el mapa comparado al volver. Es lo que
# `batalla` no puede mirar: aquélla abre la pantalla y nunca sale de ahí. La
# escena de la batalla sube 32 KB de VRAM, así que volver al mapa es reponer todo
# lo que se llevó puesto; ver `volver_de_batalla` en main.s.
#
# Cómo se compara, que es lo que lo hace barato: **la pelea no cuesta ningún
# tick**. `batalla_correr` corre su propio lazo, `vueltas` no avanza mientras
# dura, y la referencia sale del `OP_BATTLE` por la rama de victoria en el mismo
# tick en que entró. O sea que el cuadro N es el mapa quieto, igual que si no
# hubiera habido pelea, y que la ROM dibuje eso mismo **es** la prueba.
#
# Los toques son los A que pelean, en cuadros de hardware porque adentro de la
# pelea no hay ticks. Con el azar clavado en `BATALLA_SEMILLA` la pelea es la
# misma todas las veces; si la ROM no saliera, `snes_correr.py` corta con "la ROM
# no llegó al tick".
#
# Los dos casos miran los **dos repartos de VRAM**, que es donde la pelea rompe
# cosas distintas: sin ventana —LAYOUT_ANCHO— la escena se lleva los sprites
# enteros, y con ventana —LAYOUT_VENTANA— los tiles de la ventana y los dos
# tilemaps.
vuelta mapa="6" tropa="82" fondo="SJBackdropABL04" espera="20" cuadros="30 100" ventana="" arranque="115" nombre="vuelta":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ventana="{{ventana}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${ventana:+--con-ventana} \
      --pagina-de-prueba {{espera}} --batalla-de-prueba {{tropa}} \
      --fondo-de-prueba "{{fondo}}" -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      ${ventana:+--con-ventana} \
      --pagina-de-prueba {{espera}} --batalla-de-prueba {{tropa}} \
      --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  toques=$(seq 140 9 3000 | sed 's/^/a:/')
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}} \
        --toques-hardware $toques
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Un encuentro al azar, de punta a punta: se camina hasta que sale y lo que se
# compara es **la pelea**.
#
# El caso es filoso por construcción, que es lo que le faltaba a la primera idea
# —comparar el mapa unos cuadros antes—: si la ROM no dispara el encuentro en el
# paso que dice la referencia, lo que hay en pantalla es el mapa y no la pantalla
# de batalla. Y si lo dispara con **otra tropa**, el nombre y los HP del enemigo
# son otros.
#
# Por qué el mapa 21 y por qué caminando para arriba: desde donde el héroe
# arranca es la única dirección con lugar para caminar, y su área lo tapa entero
# con cinco tropas.
#
# **`--encuentros-de-prueba 8` no es hacer trampa, es acortar el caso**: con los
# pasos que el árbol le da a este mapa el encuentro sale mucho más tarde y el
# caso duraría mil cuadros de emulador. Lo que se ejercita es exactamente lo
# mismo: la tabla de `pmod`, el acumulado, el azar y la elección de tropa. Los dos
# lados toman el mismo número por el mismo flag.
encuentro mapa="21" pasos="8" walk="up" grupo="11 12 13" cuadros="200" nombre="encuentro":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --con-ventana --encuentros-de-prueba {{pasos}} \
      -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  # La referencia dice en qué paso sale, contra qué tropa y con qué grupo se
  # pelea —que no es el del arranque: las páginas del mapa lo cambian mientras
  # se camina—. El PNG que saca es el mapa sin la pelea encima y no se compara
  # contra nada: lo que se compara es la pantalla de batalla.
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --con-ventana --encuentros-de-prueba {{pasos}} --walk {{walk}} \
      --encuentro $pre.tropa.txt -o $pre.mapa.png
  read -r tropa paso grupo_final < $pre.tropa.txt
  echo "  la referencia dice: tropa $tropa en el paso $paso, grupo $grupo_final"
  python3 tools/pantallas.py -o $pre.esperado.png --batalla $tropa \
      --grupo $grupo_final
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --cuadros {{cuadros}} --sin-contador --walk {{walk}}
  python3 tools/snes_compare.py $pre.png $pre.esperado.png \
      -o $pre.comparacion.png
  # Y una captura **antes** del último paso, que es lo que fija en qué paso
  # sale: con la pelea puesta ahí se vería la pantalla de batalla en vez del
  # mapa. Sin esto, un encuentro que saliera en el paso 3 daría la misma
  # comparación de arriba, porque la pantalla de batalla es la misma.
  avance=$(( (paso - 1) * 16 ))
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --con-ventana --encuentros-de-prueba {{pasos}} --walk {{walk}} \
      --avance $avance --saltar $pre.saltar.txt -o $pre.antes.esperado.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o $pre.antes.png --walk {{walk}} --avance $avance
  python3 tools/snes_compare.py $pre.antes.png $pre.antes.esperado.png \
      --saltar $pre.saltar.txt -o $pre.antes.comparacion.png

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
# No entra en `hitos` y es a propósito: levanta un Xvfb, corre el juego
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

# La otra segunda opinión, la que sí sale gratis: los mismos casos en bsnes.
#
# bsnes es el emulador preciso, y sobre todo es el que **llena la WRAM de basura
# al encender** —`bsnes_entropy`, que acá va en "High"—, que es lo que hace la
# consola de verdad y lo que snes9x no hace: lo que snes9x deja es siempre lo
# mismo, y por eso la tanda entera daba verde con `ruta_n`/`ruta_i` sin
# inicializar, que sin inicializar quedan iguales entre sí. Con esto la tanda ve
# esa clase de error sola, sin que nadie tenga que jugar. No lo agarra siempre
# —la basura tiene que caer en un valor que rompa— pero no cuesta nada.
#
# Los dos primeros casos son los que tenía `mednafen`, que se borró el
# 2026-09-16: uno que tiñe desde un evento —CGRAM y el intérprete— y uno que
# camina —la RAM del control—. Lo que se perdió con aquella receta está dicho
# en su commit: mednafen no era un core de libretro, así que además probaba que
# `tools/retro.py` no se equivocara parejo con los tres cores, y era el único
# que cobraba las escrituras a CGRAM fuera del vblank. Que bsnes las cobre o no
# no está medido.
#
# El tercer caso es el mensaje, y no está de adorno. Es el código que más CGRAM y
# VRAM toca con la pantalla apagada —`load_ventana` sube tiles y una paleta
# entera, y `estampar_ventana` escribe su tilemap—, que es justo la clase de
# escritura que snes9x perdona; ahí ya nos mordió dos veces. Va `cerrar` y no
# `ventana` porque cubre lo mismo y algo más: su primer cuadro es la ventana
# dibujada, igual que allá, y el segundo es el cierre. De paso trae
# `msg_abierto`, que es una variable de RAM que si nadie pone en cero deja la
# página bloqueada para siempre.
#
# Va por CORE y no por `just --set` porque las recetas se llaman entre ellas: la
# variable de entorno cruza a los `just` de adentro y el `--set` no.
bsnes:
  #!/usr/bin/env bash
  set -euo pipefail
  CORE=bsnes just evento 4 1 bsnes-evento
  CORE=bsnes just caminando 73 right 60 bsnes-73-right
  CORE=bsnes just cerrar 7 200 bsnes-cerrar

# Que una espera espere de verdad, con una página inventada.
#
# El intérprete corre cuadro a cuadro desde que dejó de colapsar el tiempo, pero
# **ninguna página del juego que compile tiene una espera**, así que ese camino
# —el corazón del cambio— no lo ejercitaba nada. Es el mismo caso que `encima`:
# lo sintético es la entrada, no la comparación. Los dos lados corren el mismo
# bytecode y se comparan como siempre, la ROM contra la referencia.
#
# Se mira antes y después, no el cuadro exacto en que cambia. El arranque de la
# ROM incluye la subida al SPC700 y la referencia no modela eso, así que el borde
# cae en cuadros distintos de cada lado. Con margen a los dos lados eso no
# importa y la prueba sigue siendo filosa: si la espera no esperara, el cuadro de
# antes ya estaría teñido.
espera mapa="73" espera="120" antes="60" despues="400" nombre="espera":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --pagina-de-prueba {{espera}} 0 0 50 -o {{snes_inc}}/mapdata.inc
  just build
  for n in {{antes}} {{despues}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --pagina-de-prueba {{espera}} 0 0 50 --cuadros $n \
        --saltar {{snes_pngs}}/saltar-{{nombre}}-$n.txt \
        -o {{snes_pngs}}/esperado-{{nombre}}-$n.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}-$n.png \
        --walk none --cuadros $n
    python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-$n.png \
        {{snes_pngs}}/esperado-{{nombre}}-$n.png \
        --saltar {{snes_pngs}}/saltar-{{nombre}}-$n.txt \
        -o {{snes_pngs}}/comparacion-{{nombre}}-$n.png
  done

# La pantalla de ranuras abierta por el save point —`OpenSaveMenu`— y el mapa de
# vuelta al cerrarla. La página de prueba es la de `espera` con
# `--guardar-de-prueba`: espera, abre la pantalla, y después tiñe.
#
#   guardar          la pantalla como se abre, contra `titulo.py --modo 1`.
#   guardar-2        el cursor dos ranuras más abajo: ejercita los DMA de las dos
#                    filas desde adentro del intérprete.
#   guardar-vuelve   B cancela, y el mapa del mismo tick contra la referencia. Es
#                    el que cobra la reposición de la VRAM y CGRAM
#                    —`volver_al_mapa`— y el tinte que la página aplica después.
#   guardar-elige    lo mismo eligiendo una ranura con A. Lo que quedó en la SRAM
#                    lo mira `pruebas/test_guardar.py`.
#
# Los dos primeros van con `--sin-contador`, como `titulo`: ahí no hay tick que
# esperar. Los otros dos aprietan con `--toques-hardware`, porque un toque por
# tick no puede caer adentro de una pantalla que no cuenta ticks.
#
# El mapa vuelve **dos cuadros negros después** de cerrar: reponer el banco de
# tiles no entra en un vblank, así que ese tick dura dos cuadros —`cuadros_perdidos`
# lo cuenta— y la pantalla se enciende en el que sigue. Por eso `vuelve` no es el
# cuadro del cierre: ése sale negro.
guardar mapa="73" espera="120" vuelve="122 200" nombre="guardar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --pagina-de-prueba {{espera}} 0 0 50 --guardar-de-prueba \
      -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  abre=$(( {{espera}} + 10 ))
  python3 tools/titulo.py -o $pre.esperado.png --ranuras 4 --modo 1
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --teclas --cuadros $abre --sin-contador
  python3 tools/snes_compare.py $pre.png $pre.esperado.png \
      -o $pre.comparacion.png
  python3 tools/titulo.py -o $pre-2.esperado.png --ranuras 4 --modo 1 \
      --elegida 2
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-2.png \
      --toques down:$abre down:$(( abre + 4 )) --cuadros $(( abre + 10 )) \
      --sin-contador
  python3 tools/snes_compare.py $pre-2.png $pre-2.esperado.png \
      -o $pre-2.comparacion.png
  for n in {{vuelve}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --pagina-de-prueba {{espera}} 0 0 50 --guardar-de-prueba --cuadros $n \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.esperado.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
        -o $pre-vuelve-$n.png --cuadros $n \
        --toques-hardware down:$abre down:$(( abre + 4 )) b:$(( abre + 8 ))
    python3 tools/snes_compare.py $pre-vuelve-$n.png $pre-vuelve-$n.esperado.png \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.comparacion.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
        -o $pre-elige-$n.png --cuadros $n \
        --toques-hardware down:$abre a:$(( abre + 4 ))
    python3 tools/snes_compare.py $pre-elige-$n.png $pre-vuelve-$n.esperado.png \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-elige-$n.comparacion.png
  done

# El menú de pausa, que se abre con B desde el mapa. Tres cosas:
#
#   menu            como se abre, contra `titulo.py --menu` con el grupo con el
#                   que arranca la ROM y cero de oro: las cinco órdenes —cuatro
#                   en gris, porque sólo guardar hace algo todavía—, el cursor
#                   en la primera, el oro y el grupo con su cara.
#   menu-2          el cursor dos órdenes más abajo: los dos pares de palabras
#                   que `menu_cursor_escribir` escribe en el vblank.
#   menu-vuelve-N   B lo cierra, y el mapa del tick N contra la referencia sin
#                   menú: el reloj no corre mientras se ve, así que para la
#                   referencia el menú no cuesta ningún tick. Cobra que
#                   `volver_al_mapa` reponga todo y que el B que cerró no lo
#                   vuelva a abrir.
#
# Las dos primeras con `--sin-contador`, como `guardar`: ahí no hay tick
# que esperar. Los toques van en cuadros de hardware. Lo que la tanda no puede
# —un grupo y oro puestos, guardar desde el menú, los permisos, B a mitad de
# un paso— lo mira `pruebas/test_menu.py`.
menu mapa="73" abre="40" vuelve="50 120" nombre="menu":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  grupo=$(echo {{grupo}} | tr ' ' ',')
  python3 tools/titulo.py -o $pre.esperado.png --menu $grupo
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --toques-hardware b:{{abre}} --cuadros $(( {{abre}} + 12 )) --sin-contador
  python3 tools/snes_compare.py $pre.png $pre.esperado.png -o $pre.comparacion.png
  python3 tools/titulo.py -o $pre-2.esperado.png --menu $grupo --elegida 2
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-2.png \
      --toques-hardware b:{{abre}} down:$(( {{abre}} + 12 )) down:$(( {{abre}} + 16 )) \
      --cuadros $(( {{abre}} + 22 )) --sin-contador
  python3 tools/snes_compare.py $pre-2.png $pre-2.esperado.png \
      -o $pre-2.comparacion.png
  for n in {{vuelve}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --cuadros $n --saltar $pre-vuelve-$n.saltar.txt \
        -o $pre-vuelve-$n.esperado.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
        -o $pre-vuelve-$n.png --cuadros $n \
        --toques-hardware b:{{abre}} b:$(( {{abre}} + 12 ))
    python3 tools/snes_compare.py $pre-vuelve-$n.png $pre-vuelve-$n.esperado.png \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.comparacion.png
  done

# La pantalla de ítems, desde el menú de pausa, con un inventario que da la
# página de prueba con `ChangeItems` de verdad: trece pociones, un arma y la
# Portable Console, que es el único ítem usable de la demo. Tres cosas:
#
#   items           como se entra —B y A sobre "Use Item"—, contra
#                   `titulo.py --items`: la descripción del primero arriba, la
#                   lista con las cantidades, y en gris lo que A no usa.
#   items-2         el cursor dos más abajo, sobre la consola: el cursor y la
#                   descripción que cambian adentro del vblank.
#   items-vuelve-N  A usa la consola, que prende el switch 710 y vuelve derecho
#                   al mapa, y el mapa del tick N contra la referencia. Que el
#                   switch quede prendido lo mira `pruebas/test_items_pantalla.py`.
items mapa="73" abre="40" vuelve="60 120" nombre="items":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  dar="81 1 1 13 17 1"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --items-de-prueba $dar -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/titulo.py -o $pre.esperado.png --items 1:13,17:1,81:1
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --toques-hardware b:{{abre}} a:$(( {{abre}} + 12 )) \
      --cuadros $(( {{abre}} + 24 )) --sin-contador
  python3 tools/snes_compare.py $pre.png $pre.esperado.png -o $pre.comparacion.png
  python3 tools/titulo.py -o $pre-2.esperado.png --items 1:13,17:1,81:1 --elegida 2
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-2.png \
      --toques-hardware b:{{abre}} a:$(( {{abre}} + 12 )) \
      down:$(( {{abre}} + 24 )) down:$(( {{abre}} + 28 )) \
      --cuadros $(( {{abre}} + 34 )) --sin-contador
  python3 tools/snes_compare.py $pre-2.png $pre-2.esperado.png \
      -o $pre-2.comparacion.png
  for n in {{vuelve}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --items-de-prueba $dar --cuadros $n \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.esperado.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
        -o $pre-vuelve-$n.png --cuadros $n \
        --toques-hardware b:{{abre}} a:$(( {{abre}} + 12 )) \
        down:$(( {{abre}} + 24 )) down:$(( {{abre}} + 28 )) a:$(( {{abre}} + 34 ))
    python3 tools/snes_compare.py $pre-vuelve-$n.png $pre-vuelve-$n.esperado.png \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.comparacion.png
  done

# La pantalla de equipo, desde el menú: Equipment, A sobre Kersh —el único del
# grupo con el que arranca la ROM—, y la lista del arma con dos que puede
# ponerse y que da la página de prueba. Tres cosas:
#
#   equipo          las ranuras de Kersh con su equipo inicial del LDB —el
#                   bláster y el sobretodo— y sus parámetros, contra
#                   `pantallas.py --equipo`.
#   equipo-lista    A sobre el arma: la lista con el cursor en el segundo, y
#                   los parámetros que quedarían con ése.
#   equipo-vuelve-N B tres veces —de la lista a las ranuras, de ahí al menú y
#                   del menú al mapa—, y el mapa del tick N contra la
#                   referencia. Lo que equipar cambia en la RAM lo mira
#                   `pruebas/test_equipo.py`.
equipo mapa="73" abre="40" vuelve="60 120" nombre="equipo":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  dar="17 1 20 1"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --items-de-prueba $dar -o {{snes_inc}}/mapdata.inc
  just build
  pre={{snes_pngs}}/{{nombre}}
  a=$(( {{abre}} + 12 ))
  python3 tools/pantallas.py -o $pre.esperado.png --equipo 11 --items 17:1,20:1
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --toques-hardware b:{{abre}} down:$a down:$(( a + 4 )) a:$(( a + 8 )) \
      a:$(( a + 20 )) --cuadros $(( a + 32 )) --sin-contador
  python3 tools/snes_compare.py $pre.png $pre.esperado.png -o $pre.comparacion.png
  python3 tools/pantallas.py -o $pre-lista.esperado.png --equipo 11 \
      --items 17:1,20:1 --eligiendo --elegido 1
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-lista.png \
      --toques-hardware b:{{abre}} down:$a down:$(( a + 4 )) a:$(( a + 8 )) \
      a:$(( a + 20 )) a:$(( a + 40 )) down:$(( a + 60 )) \
      --cuadros $(( a + 72 )) --sin-contador
  python3 tools/snes_compare.py $pre-lista.png $pre-lista.esperado.png \
      -o $pre-lista.comparacion.png
  for n in {{vuelve}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --items-de-prueba $dar --cuadros $n \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.esperado.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
        -o $pre-vuelve-$n.png --cuadros $n \
        --toques-hardware b:{{abre}} down:$a down:$(( a + 4 )) a:$(( a + 8 )) \
        a:$(( a + 20 )) a:$(( a + 40 )) b:$(( a + 60 )) b:$(( a + 80 )) \
        b:$(( a + 100 ))
    python3 tools/snes_compare.py $pre-vuelve-$n.png $pre-vuelve-$n.esperado.png \
        --saltar $pre-vuelve-$n.saltar.txt -o $pre-vuelve-$n.comparacion.png
  done

# El héroe a mitad de camino: se lo captura con N pixeles andados, en la pose de
# caminata que le toca, y se compara contra la referencia calculada para ese mismo
# avance.
#
# Es la única prueba que mira el movimiento en sí. Todas las demás comparan el
# cuadro final, y ahí el héroe choca contra una pared: `moving` vale cero, la pose
# es siempre la parada y las tres columnas del ciclo no las verificaba nada. Acá
# además se ejercitan la velocidad y la cámara a mitad del scroll, y errarle por
# un solo cuadro mueve media pantalla.
#
# Y por lo mismo es donde entra **la animación del ChipSet**: un avance de N px es
# el tick N/2 + 1, así que se puede pedir el cuadro exacto en que el agua o los
# tiles animados cambian de dibujo. Hacen falta los dos casos: el mapa del agua no
# tiene tiles animados, y el de los tiles animados no aporta agua.
caminando mapa="73" direccion="right" avances="40 60 80" nombre=(mapa + "-" + direccion):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc
  just build
  # Las referencias de todos los avances salen de una sola corrida, por lo
  # mismo que las de las cinco direcciones: convertir el mapa es lo caro y no
  # depende del avance.
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk {{direccion}} \
      --avance {{avances}} --saltar $pre-{}.saltar.txt \
      -o $pre-{}.esperado.png
  for px in {{avances}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$px.png \
        --walk {{direccion}} --avance $px
    python3 tools/snes_compare.py $pre-$px.png $pre-$px.esperado.png \
        --saltar $pre-$px.saltar.txt -o $pre-$px.comparacion.png
  done

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

# La tanda de regresión: un caso por cada cosa que puede romperse, comparando la
# pantalla de la consola contra la referencia de Python.
#
# La lista vive en `rom/hitos.txt` y no acá, para que ésta y `hitos-paralelo`
# corran la misma: escrita dos veces, la que se olvide un caso sigue dando verde
# y nadie se entera. Cuántos casos son y cuántos pasan lo dice correrla.
#
# Los casos están elegidos para que no puedan pasar por casualidad, y el porqué
# de cada uno está en el comentario de su receta. Cuántos cuadros dura cada
# caminata tampoco se elige: lo dice la referencia, que camina celda por celda y
# sabe cuántas son. Ver `caminando`.
hitos:
  #!/usr/bin/env bash
  set -uo pipefail
  # Sin tilde a propósito: bash no admite acentos en los nombres de variable,
  # así que `falló=1` no es una asignación sino un comando que no existe, y
  # `$falló` se lee como `$fall` seguido de una ó. Con `set -u` eso hacía que la
  # receta saliera con código 1 siempre, hubiera fallado algo o no.
  fallo=0
  while read -r caso; do
    echo "=== $caso ==="
    eval "just $caso" || fallo=1
  done < <(grep -v '^#' rom/hitos.txt | grep -v '^$')
  exit $fallo
# Cuánto ocuparía en el cartucho el arte del juego, por rubro. Sin argumento
# los lista.
#
# No es una prueba: no falla nunca. Es la medición de la que sale la estrategia
# de `assets/README.md`, y está acá para que se pueda repetir cuando el material
# o el criterio cambien. Tarda minutos: expandir los ChipSets a su atlas y
# recorrerlos pixel por pixel no es barato.
assets-medir que="todo":
  python3 assets/medir.py {{que}}

# Las pruebas de estado: se le pregunta a la ROM en qué mapa está, qué switch
# tiene prendido, qué evento corre. No miran la pantalla.
#
# Son la otra mitad de la red y no un reemplazo de `hitos`: ésta compara
# pixeles contra la referencia de Python y cobra los errores de PPU —una paleta
# mal repartida, una prioridad de OAM—; aquélla cobra los de lógica sin
# depender de que la referencia esté bien, que es donde la comparación de
# pixeles se queda ciega. El recuerdo de CORE y MANTA que no arrancaba daba
# verde en la tanda entera, porque los dos lados se equivocaban igual.
#
# Se apoyan en la tabla de símbolos que deja `w65 --symbols`, así que
# ninguna dirección de RAM está escrita a mano: renombrar una variable en
# `main.s` hace fallar la prueba diciendo qué símbolo falta.
pruebas *args:
  python3 -m pytest pruebas {{args}}

# La tanda sobre una **foto** del árbol, para poder seguir editando mientras
# corre.
#
# El problema que resuelve: cada receta recompila desde `rom/src/main.s`, así que
# tocar un fuente a mitad de una tanda mezcla dos versiones y el resultado no
# dice nada. La regla escrita —"mientras corre una tanda no se toca ningún
# fuente"— funciona hasta que alguien se olvida.
#
# `git stash create` deja un commit colgado con el árbol sucio **sin tocar el
# índice ni el stash**, y el worktree sale de ahí: la foto incluye lo que no está
# commiteado, que es justo lo que uno quiere probar. Al terminar imprime el hash
# de la foto, que es lo que permite después ver qué se probó y qué se agregó
# encima —`git diff <foto>`—.
#
# Dos cosas para tener presentes:
#
# * **Los archivos sin trackear no entran en la foto.** `git stash create` sólo
#   toma lo modificado. Un archivo nuevo que todavía no se hizo `git add` no
#   viaja, así que la receta avisa si ve alguno.
# * **Dos tandas a la vez se pelean por CPU.** Esto sirve para seguir editando,
#   no para que la tanda termine antes.
hitos-foto trabajos="4" donde="":
  #!/usr/bin/env bash
  set -uo pipefail
  # **Cada corrida en su propio directorio.** El default era uno fijo, y la
  # receta hace `git worktree remove --force` al empezar: dos tandas a la vez
  # —dos agentes, o un agente y yo— se arrancaban el árbol entre sí y el
  # resumen salía **verde sin haber medido nada**, que es la peor forma de
  # fallar que tiene esto; y a veces se ve al revés, como una corrida que
  # empieza bien y de golpe dice `getcwd: cannot access parent directories`
  # con casos en rojo que no lo están. El PID alcanza para que no se pisen, y
  # `pruebas/hitos/` está gitignorado.
  donde="{{donde}}"
  donde=${donde:-pruebas/hitos/$$}
  mkdir -p "$(dirname "$donde")"
  nuevos=$(git status --porcelain | grep "^??" | grep -E "tools/|rom/src/|justfile|rom/hitos.txt" || true)
  if [ -n "$nuevos" ]; then
    echo "ojo: estos archivos no están trackeados y NO entran en la foto:" >&2
    echo "$nuevos" >&2
  fi
  foto=$(git stash create)
  foto=${foto:-$(git rev-parse HEAD)}
  git worktree remove --force "$donde" 2>/dev/null || true
  git worktree add --detach "$donde" "$foto" >/dev/null
  echo "foto $foto -> $donde"
  ( cd "$donde" && just hitos-paralelo {{trabajos}} )
  estado=$?
  git worktree remove --force "$donde" 2>/dev/null || true
  rmdir "$(dirname "$donde")" 2>/dev/null || true
  echo "la foto era $foto; para ver qué se agregó encima: git diff $foto"
  exit $estado

hitos-paralelo trabajos="4":
  #!/usr/bin/env bash
  set -uo pipefail
  mkdir -p rom/build
  # Por xargs viajan números de línea y no los casos. xargs procesa comillas y
  # se come las de `evento 4 "7 19 1" tabla`, que entonces le llega a just
  # como seis argumentos sueltos; el caso se cae y la tanda sigue con uno menos.
  # Pasando el número y releyendo la línea adentro, el texto no cruza nunca el
  # quoting de xargs.
  casos=$(grep -v '^#' rom/hitos.txt | grep -v '^$')
  total=$(printf '%s\n' "$casos" | wc -l)
  # Los rojos se anotan en archivos y no en el código de salida del bash
  # interno. Si éste saliera con 1, xargs deja de largar trabajo nuevo y una
  # tanda con un caso roto no llega a correr los demás, que para una prueba de
  # regresión es justo al revés de lo que uno quiere: se corre todo y se
  # informa al final.
  rm -f rom/build/hito-*.rojo
  seq 1 "$total" | xargs -P {{trabajos}} -I{} bash -c '
      caso=$(grep -v "^#" rom/hitos.txt | grep -v "^$" | sed -n "{}p")
      salida=rom/build/hito-{}.log
      if CORRIDA=hito-{} eval "just $caso" >"$salida" 2>&1; then
        echo "ok    $caso"
      else
        echo "ROJO  $caso  -> $salida"
        : > rom/build/hito-{}.rojo
      fi'
  rojos=$(ls rom/build/hito-*.rojo 2>/dev/null | wc -l)
  if [ "$rojos" -gt 0 ]; then
    echo "$rojos caso(s) en rojo de $total"
    exit 1
  fi
  echo "$total casos, todos en verde"

_tecla direccion:
  @case {{direccion}} in up) echo Up;; down) echo Down;; left) echo Left;; right) echo Right;; *) echo "";; esac

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

# La pantalla de título: la imagen del LDB con su tema, y de ahí a la partida.
#
# Corre con `--sin-contador` y no como el resto: en la pantalla de título
# `vueltas` no avanza —es el reloj del juego, y el título no es el juego— así
# que el arnés no tiene a qué cuadro esperar y cuenta cuadros de hardware.
#
# El `--arranque` no es un número medido sino un piso: el título se dibuja en la
# vuelta siguiente al arranque, así que cualquier cosa desde ahí muestra lo
# mismo. La pantalla está quieta hasta que alguien apriete algo.
titulo nombre="titulo" mapa="4" mapas="1 2 3 5 6 7 8":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}} {{snes_dir}}/sintitulo
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mapas {{mapas}} --con-ventana --con-titulo \
      -o {{snes_inc}}/mapdata.inc
  just build
  # Dos cuadros: el menú como se entra, y el cursor una opción más abajo.
  # El segundo no es un adorno: es lo único que ejercita el DMA que sube el
  # otro tilemap, que es como está hecho el cursor. Y de paso cobra que
  # sostener abajo no baje un renglón por cuadro —se corre con el botón
  # apretado veinte cuadros y el cursor tiene que haberse movido una sola vez—.
  python3 tools/titulo.py -o {{snes_pngs}}/esperado-{{nombre}}.png --informe
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}.png --cuadros 20 --arranque 150 \
      --sin-contador
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png
  python3 tools/titulo.py -o {{snes_pngs}}/esperado-{{nombre}}-2.png --elegida 1
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}-2.png --teclas down --cuadros 20 \
      --arranque 150 --sin-contador
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-2.png \
      {{snes_pngs}}/esperado-{{nombre}}-2.png \
      -o {{snes_pngs}}/comparacion-{{nombre}}-2.png
  # La pantalla de ranuras, a la que se llega bajando el cursor a "Resume the
  # Story" y apretando A. Dos cuadros: como se entra, y con el cursor dos
  # ranuras más abajo. Van con --toques y no con --teclas porque el menú mira
  # **flancos**: sostener abajo mueve el cursor una sola vez.
  #
  # Las cuatro salen vacías porque la SRAM del emulador arranca virgen. La
  # variante "llena" no la cubre esta tanda —haría falta precargar un .srm— y
  # la cubren las pruebas de estado, que sí pueden guardar antes de mirar.
  python3 tools/titulo.py -o {{snes_pngs}}/esperado-{{nombre}}-ranuras.png \
      --ranuras 4
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}-ranuras.png --toques down:2 a:6 \
      --cuadros 20 --arranque 150 --sin-contador
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-ranuras.png \
      {{snes_pngs}}/esperado-{{nombre}}-ranuras.png \
      -o {{snes_pngs}}/comparacion-{{nombre}}-ranuras.png
  python3 tools/titulo.py -o {{snes_pngs}}/esperado-{{nombre}}-ranuras2.png \
      --ranuras 4 --elegida 2
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}-ranuras2.png \
      --toques down:2 a:6 down:10 down:14 --cuadros 20 --arranque 150 \
      --sin-contador
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-ranuras2.png \
      {{snes_pngs}}/esperado-{{nombre}}-ranuras2.png \
      -o {{snes_pngs}}/comparacion-{{nombre}}-ranuras2.png

  # Y un tercero: salir del título tiene que dejar el juego **idéntico** a la
  # misma ROM sin pantalla de título. Se pasa con START, que el juego no mira
  # para nada, así que sostenerlo no interfiere; y de ahí en más las dos ROMs
  # cuentan `vueltas` igual, que es lo que deja compararlas en el mismo cuadro.
  #
  # Esto compara ROM contra ROM y no contra la referencia, a diferencia del
  # resto de la tanda. Vale porque la ROM sin título ya está comparada contra
  # la referencia por todos los demás casos, y porque la pregunta es justamente
  # "¿son la misma?".
  #
  # **Lo que este caso no cubre**, y hay que decirlo: el PPU quedando con los
  # registros del título —lo que taro encontró en Mesen— **no lo ve**.
  # Verificado sacando el `jsr ppu_init` que lo arregla: snes9x sigue dando
  # cero. Lo que sí cobra es el reparto de la VRAM.
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mapas {{mapas}} --con-ventana \
      -o {{snes_dir}}/sintitulo/mapdata.inc
  {{w65}} rom/src/main.s -I {{snes_dir}}/sintitulo \
      -o {{snes_dir}}/sintitulo/sintitulo.sfc \
      --symbols {{snes_dir}}/sintitulo/sintitulo.sfc.sym
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}-juego.png --teclas start --cuadros 300 \
      --arranque 0
  python3 tools/snes_correr.py --core {{nucleo}} \
      {{snes_dir}}/sintitulo/sintitulo.sfc \
      -o {{snes_pngs}}/{{nombre}}-juego-sin.png --teclas start --cuadros 300 \
      --arranque 0
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-juego.png \
      {{snes_pngs}}/{{nombre}}-juego-sin.png \
      -o {{snes_pngs}}/comparacion-{{nombre}}-juego.png

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
      --con-ventana --con-timer ${titulo:+--con-titulo} \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
# **`--switch 171` es lo que la hace arrancar**, y hay que saber por qué. El
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
      --con-ventana --con-timer --switch 171 --inicio 1 26 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
      --con-ventana --con-timer \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
      --con-ventana --con-timer --inicio 26 52 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
      --con-ventana --con-timer --inicio 80 19 --ruta-de-prueba 36 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
      --con-ventana --con-timer --banco-sin-prioridad \
      {{ if banco == "" { "" } else { "--banco-entero" } }} \
      -o rom/build/$nombre/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/$nombre \
      -o rom/build/$nombre/$nombre.sfc \
      --symbols rom/build/$nombre/$nombre.sfc.sym

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
      --con-ventana --con-timer --inicio 22 36 \
      -o rom/build/{{nombre}}/mapdata.inc
  {{w65}} rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --symbols rom/build/{{nombre}}/{{nombre}}.sfc.sym

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
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} --con-ventana \
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
