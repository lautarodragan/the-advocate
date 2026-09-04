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

# Vuelca los .lmu a data/ como JSON + grillas de tiles en texto, versionables.
export:
  python3 tools/export_json.py --verify

# --- Super Nintendo --------------------------------------------------------
# El port. Todo el toolchain son dos cosas: python y un core de libretro. El
# ensamblador de 65816 es nuestro (tools/w65.py) y la ROM se corre desde Python
# cuadro a cuadro (tools/retro.py), sin emulador con ventana ni servidor X.
#
# El contenedor sigue existiendo para una sola cosa, snes-validar, que compara
# w65.py contra ca65. No se necesita para compilar.

# Una corrida aislada. `CORRIDA=algo just snes-hitos` deja el mapdata, la ROM y
# las capturas adentro de rom/build/algo/ y no toca nada de lo de siempre; sin
# CORRIDA, todo queda exactamente donde estaba, para que `mednafen
# rom/build/abl.sfc` y las rutas escritas en el LEEME sigan valiendo.
#
# Existe por dos cosas que hasta ahora hacían imposible compilar mientras algo
# corría: rom/src/mapdata.inc es estado global —lo pisa cualquier
# snes-convert— y la ROM tenía un solo nombre posible. La ROM además se llama
# como la corrida, que además la hace reconocible cuando se la abre a mano.
# Con qué grupo arrancan las pruebas. En RM2k el gráfico del héroe es el del
# primero del grupo, y este juego arranca con el actor 10 —`DummyHero`, cuyo
# sprite en Chubby2 es una celda **vacía a propósito**: la apertura es una
# cinemática y ahí no hay personaje que mostrar—. Fiel, pero con él ninguna
# prueba verificaría un solo sprite del héroe: se irían las poses, el ciclo de
# caminata y la prioridad de objeto contra la capa de encima.
#
# Así que las pruebas arrancan con Kersh, el actor 11, que es a quien el jugador
# maneja después de la cinemática. Es una decisión de banco de pruebas y por eso
# está acá y no escondida en un default: `GRUPO=10 just snes-hitos` corre con el
# grupo de verdad.
grupo    := env_var_or_default("GRUPO", "11")
# Con qué core de libretro se corre. snes9x es el de la tanda por una razón
# medida: bsnes emula 121 cuadros por segundo contra 2747 de snes9x, y con él
# los cuatro minutos de `snes-hitos` se irían a media hora. bsnes entra por
# `snes-bsnes`, que corre dos casos y cuesta veinte segundos. Para mirar
# cualquier otro caso con otro core: `CORE=bsnes just snes-heroe 7`. Los tres
# que hay instalados —snes9x, bsnes y mesen-s— dibujan el mismo cuadro a 15
# bits; ver `tools/retro.py`.
core     := env_var_or_default("CORE", "snes9x")
nucleo   := "/usr/lib/libretro/" + core + "_libretro.so"
corrida  := env_var_or_default("CORRIDA", "")
snes_dir := if corrida == "" { "rom/build" } else { "rom/build" / corrida }
snes_rom := snes_dir / (if corrida == "" { "abl.sfc" } else { corrida + ".sfc" })
snes_inc := if corrida == "" { "rom/src" } else { snes_dir }
snes_pngs := if corrida == "" { "rom/shots" } else { snes_dir / "shots" }

# ChipSet + mapa -> tiles de 8x8 a 8bpp, paleta de 15 bits y tilemap, más el
# render de Python contra el que se compara después.
snes-convert mapa="7":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc \
      --reference {{snes_pngs}}/python.png

snes-build:
  python3 tools/w65.py rom/src/main.s -I {{snes_inc}} -o {{snes_rom}}

# Corre la ROM sin pantalla y captura lo que dibuja. Las teclas se mantienen
# apretadas mientras corre, para capturar con la cámara movida.
snes-shot nombre="mapa" cuadros="240" teclas="":
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --cuadros {{cuadros}} --teclas $(echo "{{teclas}}" | tr 'A-Z' 'a-z')

# La captura contra el render de Python, pixel por pixel y a 15 bits.
snes-compare nombre="mapa" x="0" y="0":
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png {{snes_pngs}}/python.png \
      --camara {{x}} {{y}} -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Camina en una dirección hasta chocar contra el borde del mapa y compara lo que
# la consola muestra contra lo que Python calcula que tendría que mostrar:
# el mapa, la cámara siguiendo al héroe, y el héroe en su pose parada.
#
# El nombre de la captura lleva el mapa además de la dirección. Con sólo la
# dirección, una tanda escribía `none.png` nueve veces y `down.png` otras
# nueve: en serie es sobreescritura inofensiva, pero cuando algo falla el PNG
# que uno querría mirar ya lo pisó un mapa posterior. Quien tenga dos casos con
# el mismo mapa y la misma dirección —snes-varios contra snes-heroe— pasa el
# nombre a mano.
snes-walk mapa="7" direccion="none" mapas="" inicial="0" nombre=(mapa + "-" + direccion):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk {{direccion}} \
      --mapas {{mapas}} --inicial {{inicial}} \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Una puerta: el héroe camina, la pisa, y aparece en el otro mapa. Lo que se
# compara es la pantalla entera después de cruzar, así que cubre de una vez el
# cambio de mapa completo —tiles, paleta, capa de encima, sprites, NPCs— y que
# el héroe haya caído en la celda que la puerta dice.
#
# La referencia recibe la misma lista de mapas que la ROM: una puerta a un mapa
# que no entró en el cartucho no lleva a ningún lado, ni en la consola ni acá.
#
# El margen va en 16 y no en los 8 de siempre porque cruzar la puerta le cuesta
# a la ROM cargar el mapa entero, y eso son cuadros que la referencia no modela:
# ella cuenta celdas caminadas y nada más. Medido en este caso, la pantalla
# queda quieta en el cuadro 79 contra los 72 que dice el plan, o sea siete de
# carga; 16 es una celda más de aire sobre eso.
snes-puerta origen="30" destino="28" direccion="down" nombre=("puerta-" + origen + "-" + destino):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      --walk {{direccion}} --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      --margen 16
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# El tinte solo, contra la cuenta de Python y sin referencia de por medio: toma
# la misma pantalla capturada de la consola sin teñir y teñida, y pregunta si la
# transformación de una a la otra es exactamente canal * valor / 100 sobre los
# 15 bits. Es una segunda opinión sobre snes-evento, que compara un camino
# entero; si snes-evento falla y esto da cero, el tinte no es el problema.
#
# La captura sin teñir sale de plantar al héroe en el destino del
# teletransporte, que es la misma pantalla sin el evento:
#     just snes-parado 1 7 65 destino
snes-tinte sin="rom/shots/destino.png" con="rom/shots/evento.png" r="0" g="0" b="100":
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
# Después de esto, `just snes-play` lo muestra con sonido.
snes-evento origen="4" destino="1" nombre="evento":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 240 ""
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Varios mapas en la misma ROM. Lo que prueba no es que cada uno se vea bien
# —eso ya lo cubre snes-hitos— sino que se vea bien cuando su registro no está
# al principio de la tabla: con el índice 0 el desplazamiento es cero y
# cualquier cuenta mal hecha da el resultado correcto por casualidad.
snes-varios primero="18" otros="7 19" indice="2":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{primero}} --mapas {{otros}} \
      --inicial {{indice}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-walk {{primero}} none "{{otros}}" {{indice}} varios-{{primero}}-none
  just snes-walk {{primero}} down "{{otros}}" {{indice}} varios-{{primero}}-down

# Planta al héroe en una celda elegida y compara sin caminar. Llegar a un lugar
# puntual caminando depende de cuánto se mantenga la cruceta; acá la celda se
# fija y la captura no se negocia.
snes-parado mapa="1" tx="75" ty="88" nombre="parado":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} --inicio {{tx}} {{ty}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 240 ""
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --hero-tile {{tx}} {{ty}} \
      --dir down --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Lo mismo, pero con el héroe en prioridad 2 de objeto: la que llevan los
# eventos marcados "above", y que en el orden del modo 3 queda por encima de
# BG2. Es la única manera de ejercitarla. El juego tiene un solo evento "above"
# —el Package del mapa 261, en (59,1)— y la capa de encima de ese mapa llega
# hasta x=938 mientras que el sprite arranca en x=940: no se tocan por dos
# pixeles, así que con datos de verdad las prioridades 1 y 2 dan la misma
# pantalla y la comparación no las distingue.
#
# La celda por defecto se eligió midiendo: en (66,40) del mapa 1 la capa de
# encima tapa 512 de los 768 pixeles del sprite, así que el héroe queda partido
# y la silueta tiene que coincidir de los dos lados. Con la prioridad
# equivocada la comparación se va a 284 pixeles, que es lo que se midió
# poniendo #OBJ_PRIORITY_ABOVE a mano en place_hero.
snes-encima mapa="1" tx="66" ty="40" nombre="encima":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} --inicio {{tx}} {{ty}} \
      --heroe-encima -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 240 ""
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --hero-tile {{tx}} {{ty}} \
      --dir down --heroe-encima --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Corre los eventos automáticos de un mapa con un grupo dado y compara el cuadro
# ya asentado. Es la receta para las páginas cuyo efecto se ve en el héroe.
#
# El grupo se pide explícito y no sale del default de las pruebas porque en
# estos casos es parte del caso, no decoración:
#
#   121  `ChangePartyMembers` saca al actor 10 y agrega al 14 y al 28. En RM2k
#        el gráfico del héroe es el del primero del grupo —`AddActor` y
#        `RemoveActor` llaman los dos a `ResetGraphic`—, así que arrancando con
#        [10] el héroe pasa de `DummyHero`, que es una celda vacía y no se
#        dibuja, a Talan. Arrancando con [11] el 10 no está, sacarlo no hace
#        nada, Kersh sigue al frente y la prueba no probaría nada.
#
#   74   Una ruta forzada de `MoveEvent` sobre el héroe: `face_up` y una espera.
#        Su página pide al actor 21 en el grupo, así que sin arrancar con él no
#        corre. Es la única página del juego que compila y ejercita una ruta.
snes-pagina mapa="121" arranca="10" nombre=("pagina-" + mapa):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{arranca}} --map-id {{mapa}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{arranca}} --map-id {{mapa}} \
      --walk none --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --walk none --cuadros 240
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# La segunda opinión: los mismos casos, pero en mednafen y con ventana.
#
# La tanda corre en snes9x por libretro, y snes9x es permisivo en cosas donde la
# consola real no lo es. En un mismo día se colaron dos errores que sólo mednafen
# ve, los dos con la tanda en verde: `ruta_n`/`ruta_i` sin inicializar —snes9x
# deja siempre la misma basura y las dos quedaban iguales, así que no se notaba,
# y el héroe no respondía al control— y el tinte escribiendo CGRAM fuera del
# vblank, que snes9x acepta y mednafen no.
#
# Dos casos alcanzan porque cubren las dos clases: uno que tiñe desde un evento
# —CGRAM y el intérprete— y uno que camina —la RAM del control—. Cuesta como un
# minuto de reloj, que es el precio de mirar lo que el camino rápido no puede.
#
# Se compara contra las mismas referencias de Python que usa la tanda: lo que se
# cruza son dos emuladores contra un mismo tercero, no uno contra el otro.
snes-mednafen:
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}

  # 1) la apertura: dos switches, un tinte y un teletransporte.
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id 4 --mapas 1 \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id 4 --mapas 1 \
      --saltar {{snes_pngs}}/saltar-med-evento.txt \
      -o {{snes_pngs}}/esperado-med-evento.png
  rom/mednafen.sh {{snes_rom}} {{snes_pngs}}/med-evento.png 5 ""
  python3 tools/snes_compare.py {{snes_pngs}}/med-evento.png \
      {{snes_pngs}}/esperado-med-evento.png \
      --saltar {{snes_pngs}}/saltar-med-evento.txt \
      -o {{snes_pngs}}/comparacion-med-evento.png

  # 2) caminar: si el control no responde, acá se ve.
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id 73 \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id 73 --walk right \
      --saltar {{snes_pngs}}/saltar-med-walk.txt \
      -o {{snes_pngs}}/esperado-med-walk.png
  rom/mednafen.sh {{snes_rom}} {{snes_pngs}}/med-walk.png 8 "Right"
  python3 tools/snes_compare.py {{snes_pngs}}/med-walk.png \
      {{snes_pngs}}/esperado-med-walk.png \
      --saltar {{snes_pngs}}/saltar-med-walk.txt \
      -o {{snes_pngs}}/comparacion-med-walk.png

# La ventana de mensaje dibujada por la consola, contra la referencia.
#
# La ventana se dibuja al cargar el mapa y se queda: todavía no hay opcode ni
# espera de botón, así que el texto es sintético —como `--pagina-de-prueba`— y
# lo que se compara es el dibujo. Que es lo que hay que verificar primero: la
# fuente, el marco, la paleta y dónde caen las celdas en el tilemap.
#
# La cadena entera queda atada de punta a punta: la referencia en Python está
# verificada contra una captura de EasyRPG por `snes-oraculo`, y esto verifica
# la consola contra la referencia.
#
# Los mapas de la tanda no son varias veces lo mismo. La ventana se lleva la
# paleta que queda justo debajo de la capa de encima, y quién la paga cambia de
# mapa en mapa:
#
#     7 y 6    al fondo le sobran paletas: no fusiona nada
#     348      fusiona 16, el máximo posible, y se ve
#     269      el reparto para mapas con mucho fondo, y no entra en el tilemap
#              de 64x32: estampa la ventana sobre un mapa que la ROM redibuja
#
# El 348 está por eso: es el único donde la fusión llega a la pantalla. Con la
# referencia armada sin reservar la paleta, difiere en 45 pixeles. O sea que sin
# el 348 el reparto con ventana del lado de la referencia no lo ejercitaría nada.
#
# El mapa 1 estuvo acá —fue el que descubrió el reparto, porque el conversor
# cortaba, y fusionaba 2— y no está más desde el 2026-09-04: con ventana ya
# compila la escena de apertura, que hace caminar a cuatro personajes, y son
# 768 tiles de sprite contra los 512 que direcciona la PPU. El conversor corta,
# y con razón. Ver "Lo que falta" en rom/LEEME.md.
#
# El último caso es el 7 **con el 269 en la misma ROM**. La paleta de la
# ventana es una para toda la ROM —las celdas se emiten una sola vez con la
# paleta adentro— y cada mapa la pondría justo debajo de su capa de encima: el
# 7 en la 6 y el 269 en la 3. Gana la más baja, y el 7, que solo no fusiona
# nada, acá fusiona 13 colores para dejarle la 3. Se ve: entre el 7 solo y el 7
# apretado hay 72 pixeles, así que el cero mide que la ROM y la referencia
# apretaron igual. Es el reparto de la ROM del arranque —mapa 4 con los mapas 1
# y 2—, con un mapa que se puede mirar en vez de una habitación negra. Nació
# con el 1 de compañero, hasta que el 1 dejó de entrar.
snes-ventana mapa="7" nombre="ventana" mapas="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  linea1="SEWELL"
  linea2="There you are, Talan. Ready for"
  linea3="the big night?"
  mapas="{{mapas}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${mapas:+--mapas $mapas} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --mapas $mapas \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{nombre}}.png --walk none --cuadros 200
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

# Un mensaje de verdad: se abre desde el intérprete, bloquea la página, y se
# cierra cuando el jugador aprieta A.
#
# El nombre es por lo último, que es lo que no existía: `snes-ventana` ya
# dibujaba la ventana, pero no había forma de **cerrar** un mensaje.
#
# Es lo que `snes-ventana` no prueba. Allá la ventana se abre y se queda, así que
# lo único que se compara es el dibujo; acá se comparan las dos mitades que
# faltaban:
#
#   antes    la ventana en pantalla y **la página frenada**: el tinte que viene
#            después del mensaje todavía no se aplicó
#   después  la ventana borrada y el tinte puesto, o sea que apretar A la cerró
#            y la página siguió
#
# Ese segundo cuadro es el único que ejercita `redibujar_franja`, que hasta hoy
# no la llamaba nadie: si no corriera, la ventana seguiría ahí.
#
# Los cuadros se miran con margen y no en el borde, por lo mismo que
# `snes-espera`: el arranque de la ROM no lo modela la referencia. A los 60
# cuadros los dos lados tienen el mensaje abierto hace rato, y a los 400 hace
# rato que se cerró. A se aprieta en el 200 y se deja apretado: la ROM cierra
# con el flanco —`pad_a` contra `pad_a_ant`, que es el `IsTriggered` de RM2k—
# así que sostenerlo no dispara nada más, y la referencia modela ese mismo
# único flanco.
#
# El `--pagina-de-prueba 0 0 0 50` es el tinte de atrás del mensaje, con espera
# en cero: es lo que hace visible que la página siguió.
#
# Con una dirección en vez de `none` se prueba además que **el pad no mueva al
# héroe mientras hay un mensaje**, que es el guard de
# `Game_Player::UpdateNextMovementAction`: vuelve sin mirar el input si
# `Game_Message::IsMessageActive()`. La ruta forzada es otra cosa y sí camina,
# porque allá `UpdateMoveRoute` corre antes del guard.
#
# Con dirección el arranque no puede ser cero. La cruceta se mantiene apretada
# desde que termina, y si empezara antes de que la página abra el mensaje el
# héroe daría unos pasos que la referencia no modela. Treinta cuadros alcanzan
# de sobra —el mapa 7 es mudo y la ROM llega al primer cuadro del intérprete en
# diez— y no hace falta que el número sea exacto: lo que se compara es que el
# héroe no se haya movido **nada**.
snes-cerrar mapa="7" apretar="200" nombre="cerrar" direccion="none" arranque="30":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  linea1="SEWELL"
  linea2="There you are, Talan. Ready for"
  linea3="the big night?"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --pagina-de-prueba 0 0 0 50 -o {{snes_inc}}/mapdata.inc
  just snes-build
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

# Un evento caminando su ruta forzada, y la página esperándolo.
#
# Es lo que agrega `MoveEvent` sobre otro evento: hasta acá la única ruta
# forzada que la ROM sabía caminar era la del héroe. Se mueven los eventos **sin
# gráfico**, que son la mitad de las rutas del juego; de ellos no se ve nada en
# pantalla, así que lo único comparable es **cuánto tardan**, y eso es
# exactamente lo que espera el `ProceedWithMovement` que va detrás.
#
# La página es inventada, por lo mismo que `snes-espera` y `snes-encima`:
# ninguna página del juego que compile manda a caminar a un evento sin depender
# de un switch, así que este camino no lo correría nada. Lo sintético es la
# entrada, no la comparación.
#
# El mapa 6 tiene un solo evento sin gráfico —el índice 2, en (23,19)— y una
# pared a pocas celdas, que es lo que permite que la ruta pruebe las tres cosas
# que hay que probar:
#
#   0 x6      seis pasos hacia arriba, hasta (23,13)
#   3 x3      tres a la izquierda: los dos primeros entran, **el tercero da
#             contra la pared de (20,13) y se saltea sin gastar un cuadro**
#   23        una espera, que sí gasta uno
#   2 x2      dos hacia abajo
#   1         uno a la derecha
#   13        y girar, que es instantáneo y no gasta ninguno
#
# El tinte va detrás del ProceedWithMovement, así que el cuadro en que la
# pantalla cambia de color **es** el cuadro en que la ruta terminó. Los dos
# cuadros que se comparan lo abrazan: en el 89 todavía no tiñó y en el 91 ya
# tiñó. El 90 se saltea a propósito y no por comodidad: la ROM sube CGRAM en el
# vblank siguiente, así que ese cuadro sale partido —mitad con la paleta vieja y
# mitad con la nueva— y la referencia no modela eso. Un cuadro de más o de menos
# en la cuenta de la ruta corre el borde y el 89 o el 91 se caen.
snes-ruta-evento mapa="6" ruta="3 0 0 0 0 0 0 3 3 3 23 2 2 1 13" cuadros="89 91" arranque="10" nombre="ruta-evento":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --ruta-de-evento {{ruta}} --pagina-de-prueba 0 0 0 50 \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --ruta-de-evento {{ruta}} --pagina-de-prueba 0 0 0 50 \
      --cuadros {{cuadros}} --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Un evento **con gráfico** caminando en pantalla.
#
# Es la otra mitad de MoveEvent. `snes-ruta-evento` mueve a uno invisible y lo
# único que se ve de él es cuánto tarda; acá el evento se dibuja, así que se
# comparan tres cosas más que allá no existían:
#
#   la posición a mitad de paso   la celda se mueve al empezar el paso y los
#                                 pixeles van detrás, dos por cuadro
#   la pose del ciclo             la misma cuenta que `animate_hero`, con el
#                                 ciclo de cuatro sobre tres columnas
#   el orden de dibujado          al cambiar de fila cruza al héroe, y la tabla
#                                 de NPCs hay que reacomodarla
#
# El mapa 6 otra vez, por mudo y abierto, con el héroe puesto a mano en (22,12)
# —una celda debajo del evento 3, que arranca en (22,9)—. La ruta lo hace bajar
# cuatro celdas, o sea **pasarle por encima al héroe**, después ir dos a la
# derecha, y al final girar hacia arriba.
#
# Los cuatro cuadros están elegidos uno por cosa: en el 10 va bajando a mitad de
# celda, en el 27 ya cambió de columna del ciclo, en el 40 va hacia la derecha
# —otra dirección, otras poses— y en el 60 terminó y quedó parado mirando
# arriba, que es donde lo dejó el último comando.
#
# Tres casos más, desde el 2026-09-04:
#
# * `npc-lento`, la frecuencia 4 sobre un evento: dos pasos, un giro y un paso,
#   con el mismo ritmo que `ruta-lenta` en `snes-ruta`. Los cuadros 20 y 88 son
#   quieto después de un paso y de un giro, el 44 y el 100 a mitad de paso.
# * `npc-encara` y `npc-encara-lado`, `face_hero`: es
#   `GetDirectionToCharacter`, manda el eje con más distancia y en empate el
#   vertical. El evento 3 arranca en (22,9) mirando a la izquierda; con el
#   héroe en (22,12) gira hacia abajo, y con el héroe en (25,10) —tres a la
#   derecha y una abajo— gira a la derecha.
snes-npc mapa="6" ruta="4 2 2 2 2 1 1 12" celda="22 12" cuadros="10 27 40 60" arranque="10" nombre="npc" frecuencia="8":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --ruta-de-evento {{ruta}} --frecuencia {{frecuencia}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --ruta-de-evento {{ruta}} --frecuencia {{frecuencia}} \
      --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Plantar a un evento en una celda: ChangeEventLocation.
#
# Es `MoveTo`, y la vuelta que tiene está en lo que **no** hace: no toca la ruta
# ni hacia dónde mira, y corta el paso en curso —`SetRemainingStep(0)`—. Dos
# casos, en el mapa 6 de `snes-npc`, con el evento 3 que arranca en (22,9):
#
# * a mitad de su ruta: cuatro para abajo, y después de esperar 12 cuadros —a
#   mitad del segundo paso— lo plantan en (21,13). Se dibuja **exactamente**
#   sobre esa celda y sigue con los dos pasos que le quedaban, hasta (21,15).
#   Sin el corte del paso quedaría corrido los pixeles que le faltaban; con la
#   ruta cortada no llegaría.
# * sin ruta: lo plantan en (21,10) y nada más. Se dibuja ahí con la pose de su
#   página, y en la ROM sin llevarse ranura ni tocarle el tile.
#
# Las celdas son del piso marrón a la vista, y no da lo mismo: la primera
# versión lo plantaba en (20,14), que cae en la franja de la capa de encima, y
# los dos lados lo dibujaban tapado. La prueba daba cero con el corte del paso
# sacado, porque no veía al evento. Cada caso se rompió a propósito para saber
# que mira lo que dice.
#
# Los cuadros del primero no son los de la espera: `OP_ESPERAR 12` suelta la
# página en el cuadro **14**, no en el 12 —la espera cuenta cuadros enteros y
# el opcode se lee en el siguiente—, y elegidos a ojo los dos primeros caían
# antes del corte, así que la ROM sin el corte también daba cero. El 14 es el
# del corte —el evento arranca el tercer paso desde la celda nueva—, el 15 uno
# después, el 20 caminando, y el 60 terminó.
snes-lugar mapa="6" lugar="4 21 13 12" ruta="4 2 2 2 2" celda="22 12" cuadros="14 15 20 60" arranque="10" nombre="lugar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ruta="{{ruta}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} ${ruta:+--ruta-de-evento $ruta} \
      --lugar-de-prueba {{lugar}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} ${ruta:+--ruta-de-evento $ruta} \
      --lugar-de-prueba {{lugar}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Un destello sobre un personaje: FlashSprite.
#
# RM2k lo hace mezclando el dibujo del personaje hacia un color durante unos
# cuadros. Acá el dibujo es una paleta de CGRAM, así que destellar es subir esa
# paleta mezclada, y apagarlo es volver a subirla como estaba.
#
# Se compara cuadro por cuadro porque la fuerza baja en cada uno: del 31 al 0 en
# los 24 que dura. El 2 y el 12 la agarran alta y a la mitad, el 23 es el último
# con algo de destello y el 24 el primero que ya no tiene, o sea el que prueba
# que la paleta volvió.
#
# El evento 0 del mapa 6 y no el héroe, y no es un detalle: el héroe se dibuja
# con Future1[5] y el evento 3 del mismo mapa también, así que **comparten
# paleta** y destellarían los dos. El conversor lo corta con un error antes de
# armar la ROM, y `eventos.py` no compila una página que destelle a un evento
# que comparta gráfico con otro. Es la clase de cosa que la comparación no
# vería: los dos lados harían lo mismo mal.
#
# El tinte llega en el cuadro 13, con el destello a mitad de camino, y **tiene
# que estar**: las 23 páginas que este comando destraba tiñen todas, así que sin
# él la receta no cubriría ninguna de verdad.
#
# Tres cuadros quedan afuera y están medidos. El 13 es el del tinte, que la ROM
# aplica con la pantalla apagada y sale partido —55926 pixeles—: es el mismo
# borde que `snes-espera` mira con margen. El 14 es el que le sigue, con 71, y el
# 24 es el último del destello, con 55: los dos son el retraso de un cuadro que
# tiene subir la paleta en el vblank, que es lo que hay que hacer para que la
# pantalla no salga con media paleta vieja. Los demás dan cero, incluido el 15
# —o sea que el retraso dura un cuadro y no más— y el 25, que prueba que la
# paleta volvió a la normal.
# El cronómetro de RM2k: TimerOperation.
#
# Cinco glifos de la imagen de System —los diez dígitos y los dos puntos, en
# 8x16 a partir de (32,32)— dibujados arriba a la izquierda como diez objetos de
# 8x8, con la prioridad 3 que los pone adelante de las dos capas. La cuenta no
# se guarda en cuadros sino partida en segundos y resto, que es lo que evita
# dividir por 60 sesenta veces por segundo.
#
# **Este comando no destraba ninguna página**, y está medido: las seis del juego
# que lo usan están todas cortadas por otra cosa. La del despertador del pad
# —mapa 7, evento 4, la que prende el cronómetro de diez minutos— necesita
# además TintScreen con saturación, ChangeGold y cinco órdenes de ruta que no
# caminamos. Se hace igual porque es autocontenido y porque el cronómetro se ve
# en pantalla desde el minuto diez del juego.
#
# Por eso la página es sintética, como la de `snes-destello`: sin ella no
# habría con qué comparar.
#
# Dos cosas se prueban aparte y las dos son bordes:
#
# * **Los dos puntos parpadean.** `Sprite_Timer::Draw` los saltea cuando
#   `cuadros % 60 < 30`, así que el 2 y el 61 los tienen y el 31 y el 90 no. El
#   61 además cruza el segundo: 10:00 pasa a 09:59, que es lo que prueba que la
#   división da los cuatro dígitos y no sólo los minutos.
# * **El tinte no lo toca.** Llega en el cuadro 13, así que el 2 lo agarra sin
#   teñir y los otros tres teñidos, y los dígitos tienen que verse igual en los
#   cuatro. En RM2k es `Priority_Timer` = 140 contra el `Priority_Screen` = 90
#   del tinte: la pantalla se oscurece y el cronómetro no. Acá el tinte es una
#   transformación de CGRAM, que se lleva por delante todo lo que toca, así que
#   `aplicar_tinte` vuelve a subir la paleta del cronómetro sin teñir. La
#   ventana de mensaje no puede hacer lo mismo: su paleta está en la mitad del
#   mapa, y por eso ésa sí se tiñe.
# * **Al llegar a cero se apaga y se esconde.** `StopTimer` apaga las dos cosas,
#   así que el último valor que se ve es 00:01 y después no queda nada
#   dibujado. Con un segundo entero el corte cae en el cuadro 60, y el 61 lo
#   agarra ya vacío. Un 00:00 congelado sería lo que sale de modelarlo como "se
#   para", que es el error que este caso mira.
snes-timer mapa="6" timer="600 1" celda="2 10" cuadros="2 31 61 90" tinte="12 0 0 50" arranque="10" nombre="timer":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --timer-de-prueba {{timer}} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --timer-de-prueba {{timer}} \
      --pagina-de-prueba {{tinte}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La saturación del tinte de pantalla, y la mitad de arriba del hard light.
#
# `TintScreen` tiene cuatro parámetros y hasta ahora la ROM hacía tres: la
# saturación sólo se aceptaba neutra. Con ella compilan once páginas más —nueve
# automáticas y dos de contacto—, que es lo que más rinde de lo que quedaba.
#
# Dos cuentas nuevas, y las dos salen de leer easyrpg y no de mirar la pantalla:
#
# * **La saturación es una mezcla hacia el gris**, no un factor por canal:
#   `saturation_tone` calcula la luminancia Y' del color y acerca o aleja los
#   tres canales de ella. Por eso no entra en las tablas de 32 entradas que usa
#   el tinte —necesita los tres canales a la vez— y se hace color por color.
#   Con 0 todo queda gris, con 100 no pasa nada y con 200 la distancia al gris
#   se triplica.
# * **El tinte de color es un hard light**, no una multiplicación. Para los
#   valores que oscurecen las dos cosas coinciden —`2ab` con 100 neutro **es**
#   `canal * valor / 100`— y por eso nunca se notó, pero para los que aclaran
#   RM2k hace un screen y la ROM multiplicaba por dos y topaba en 31. La
#   diferencia llegaba a 31 de 31 con el valor 200, o sea la pantalla entera.
#   Ninguna página que compilara aclaraba, así que no lo cobró nadie; dos de las
#   once que destraba esto sí, con (0, 120, 120).
#
# Los tres casos que van en `snes-hitos` están elegidos por lo que miran:
#
#   0 0 0 0        el gris puro: sin color y sin saturación queda todo negro,
#                  que es lo que prueba que la luminancia no se cuela
#   100 100 100 0  gris de verdad: el color no se toca y la saturación se lleva
#                  todo al gris. Es el (60,60,60,0) del juego sin el oscurecido
#   0 120 120 200  el de los mapas 229 y 230: aclara **y** sobresatura, o sea
#                  las dos mitades nuevas a la vez
snes-saturar mapa="73" tinte="60 0 0 0 0" antes="30" despues="120" nombre="saturar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  for n in {{antes}} {{despues}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --pagina-de-prueba {{tinte}} --cuadros $n \
        --saltar $pre-$n.saltar.txt -o $pre-$n.esperado.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque 0
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

snes-destello mapa="6" flash="1 31 0 0 31 24" celda="2 10" cuadros="2 12 15 23 25" tinte="12 0 0 50" arranque="10" nombre="destello":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --flash-de-prueba {{flash}} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --flash-de-prueba {{flash}} \
      --pagina-de-prueba {{tinte}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Hablarle a algo, que es lo que convierte esto en un juego.
#
# Hasta acá la ROM sólo corría páginas **automáticas**: 110 de las 489 del
# juego. Las que se disparan con la tecla de acción son 1599, y 1006 ya
# compilan. Es, de lejos, la mayor cantidad de contenido que le faltaba.
#
# La regla sale de `Game_Player::CheckActionEvent`: se mira la celda del héroe y
# después la de adelante, y gana la página de número más alto que cumpla sus
# condiciones. Lo que allá va antes —los eventos que se disparan al tocarlos— y
# el lazo de hasta tres mostradores todavía no están.
#
# El pad de Talan, que es donde el jugador empieza a moverse. El héroe queda
# parado justo encima del evento 7, que son los caños, y mirando hacia abajo,
# que es como arranca.
#
# El `--switch 24` no es una licencia: **todas** las páginas del pad lo piden, y
# lo prende la cinemática de apertura. Ponerlo a mano es dejar el mundo en el
# estado al que el juego llega solo, igual que `--hero-tile` deja al héroe donde
# llegaría caminando.
#
# Los dos cuadros abrazan el momento: en el 20 todavía no se apretó nada y en el
# 60 el mensaje está abierto. La diferencia entre los dos son 19895 pixeles, así
# que si la tecla no disparara nada se vería.
#
# Y el segundo caso de `snes-hitos` prende el switch **25** en vez del 24, o sea
# que la página de los caños no queda activa y apretar A no tiene que hacer
# nada. Es lo único que ejercita que se miren las condiciones: con el 24 puesto
# se cumplen todas, así que una ROM que las ignorara daría lo mismo.
snes-hablar mapa="7" celda="3 7" switch="24" apretar="25" cuadros="20 60" arranque="30" nombre="hablar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana --switch {{switch}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --dir down --con-ventana --switch {{switch}} \
      --cuadros {{cuadros}} --apretar-a {{apretar}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}} --apretar-a {{apretar}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# El arranque son 70 cuadros y no 21 desde que la ROM lleva música: el mapa 4
# no tiene tema propio, así que el cartucho se lleva el que pide el `PlayBGM` de
# la cinemática —`escape_newyork`, 32 KB de muestras— y subirlas al SPC700 por
# el protocolo del IPL, byte por byte y con acuse, cuesta unos 49 cuadros antes
# de que el lazo principal empiece. Es tiempo que RM2k no gasta.
#
# La cinemática de apertura, entera.
#
# Es la puerta a los primeros diez minutos del juego: el mapa 4 prende dos
# switches, tiñe y teletransporta al 1; ahí arranca la lluvia, se espera, se
# salta dos veces **adentro del mismo mapa**, se manda a caminar al evento 8,
# cambia el grupo —sale el 10, que es DummyHero y no se dibuja, y entra Kersh— y
# el héroe sube tres celdas por una ruta forzada.
#
# Cuatro cosas tuvieron que existir para que esto corriera, y las cuatro estaban
# rotas o faltaban:
#
#   la página sobrevive al salto   RM2k hace `index++` y devuelve false, así que
#                                  la misma página retoma del otro lado
#   saltar al mismo mapa no recarga es el `map_changed` de `PerformTeleport`;
#                                  recargando, la cinemática se reiniciaba sola
#   el mapa de destino encola      nunca lo hacía: después de un teletransporte
#                                  los eventos del mapa nuevo no corrían jamás
#   quién puede ser líder          se miraba sin el contexto del mapa, así que
#                                  Kersh no entraba y el héroe salía invisible
#
# Los cuadros están elegidos afuera de las ventanas de los saltos, y eso está
# medido: la ROM se toma unos seis cuadros en cada teletransporte rellenando el
# tilemap de 64x32, y la referencia no modela ese costo —es lo mismo que pasa
# con el arranque, que incluye la subida al SPC700—. Entre el salto y unos
# treinta cuadros después los dos lados quedan a tres o seis cuadros de
# distancia, y como la cámara sigue al héroe, eso corre la pantalla entera.
#
# Afuera de esas ventanas dan cero, incluido el cuadro 900, que es la cinemática
# terminada: el héroe arriba de todo, mirando arriba, con la pantalla teñida.
snes-cinematica origen="4" destino="1" cuadros="100 400 600 900" arranque="70" nombre="cinematica":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo 10 --map-id {{origen}} \
      --mapas {{destino}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo 10 --map-id {{origen}} \
      --mapas {{destino}} --walk none --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Pisar un evento, que es el otro disparo que le faltaba a la ROM.
#
# Son 526 páginas del juego que ya compilan, la segunda cantidad de contenido
# después de la tecla de acción. La regla es `CheckEventTriggerHere` desde
# `Game_Player::UpdateMovement`: al terminar el paso se mira si en esa celda hay
# un evento de contacto.
#
# Y la capa es al revés que la de la tecla de acción, a propósito: acá tiene que
# ser **distinta** de la del héroe, porque un evento de su misma capa le
# bloquearía el paso y nunca llegaría a pisarlo. De las 983 páginas de contacto
# del juego, 978 son de la capa de abajo.
#
# Las puertas son un caso particular de esto —un teletransporte en una página de
# contacto— y siguen atendiéndose aparte, antes que esto: es un camino que ya
# está probado y no había razón para moverlo.
#
# El mapa 70 tiene uno en (12,4) sin condición de switch, así que caminando para
# arriba desde (12,8) se lo pisa a las cuatro celdas. La caminata **frena ahí**:
# mientras el intérprete tiene una página en el frente el pad no mueve, que es el
# `if (Game_Map::IsAnyEventStarting()) return;` de RM2k. Sin eso el héroe daba un
# paso de más mientras el mensaje se componía.
snes-pisar mapa="70" celda="12 8" direccion="up" cuadros="200" arranque="40" nombre="pisar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --walk {{direccion}} --hero-tile {{celda}} --con-ventana \
      --saltar $pre.saltar.txt -o $pre.esperado.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre.png \
      --walk {{direccion}} --cuadros {{cuadros}} --arranque {{arranque}}
  python3 tools/snes_compare.py $pre.png $pre.esperado.png \
      --saltar $pre.saltar.txt -o $pre.comparacion.png

# El texto del juego, no el que le dictamos a la ROM.
#
# Todo lo que hay arriba —`snes-ventana`, `snes-cerrar`, `snes-anclada`— usa
# `--mensaje-de-prueba`, o sea tres líneas inventadas que el conversor mete en
# una página que tampoco sale del juego. Eso probaba el dibujo, el bloqueo y el
# cierre, pero no el camino que ahora existe: que un `ShowMessage` de RM2k
# compile, que su texto entre en el bloque de la ROM y que el operando de
# `OP_MENSAJE` lo vuelva a encontrar. Sin este caso ese camino no lo corría
# **nada**, que es exactamente cómo sobrevivieron los tres errores del
# intérprete de eventos.
#
# El mapa 255 es el que sirve, y se eligió midiendo. Tiene una página automática
# **sin condición de switch** —o sea que corre al entrar— cuyo código entero es
# dos cuadros de texto seguidos y un switch:
#
#     07 0000   OP_MENSAJE @0     "BRIDGE OVER THE RIVER LASHE" y tres líneas
#     07 7c00   OP_MENSAJE @124   otras cuatro
#     01 5003 01  el switch 848
#
# De ahí salen tres cosas que ninguna otra receta mira. Los **desplazamientos**:
# el segundo mensaje está en el 124 y no en el 0, así que si el operando se
# ignorara se vería el primero dos veces. Los **cuatro renglones**: el mensaje de
# prueba tiene tres, y el cuarto es el que ejercita el `msg_lineas` completo.
# Y el **encadenado**: al apretar A el primero se cierra y el segundo se abre en
# el mismo cuadro, que es la regla que los dos lados escriben por separado
# —`eventos_tick` en la ROM, `Interprete.cuadro` en la referencia—.
#
# Los cuadros, con margen y no en el borde, por lo de siempre: a los 60 los dos
# lados tienen el primero abierto hace rato, y a los 400 el segundo. Entre esos
# dos cuadros la pantalla cambia 2869 pixeles, todos en las filas de la ventana:
# si el A no avanzara al segundo mensaje, serían cero y la receta daría verde sin
# probar nada.
snes-texto mapa="255" apretar="200" nombre="texto":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --con-ventana -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --con-ventana --cuadros 60 400 --apretar-a {{apretar}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in 60 400; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --apretar-a {{apretar}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La ventana quieta mientras la cámara se mueve.
#
# Es lo único que ni `snes-ventana` ni `snes-cerrar` pueden mirar: en los dos la
# cámara está parada. Y con el pad bloqueado durante un mensaje, lo único que la
# mueve es **una ruta forzada**, que es exactamente el caso de RM2k que obligó a
# esta arquitectura: `UpdateMoveRoute` corre antes del guard de
# `IsMessageActive`, y en este juego hay 186 páginas donde el héroe arranca a
# caminar y a los pocos comandos aparece un cuadro de texto.
#
# La página inventada es `ruta, mensaje`: el héroe se pone a caminar y enseguida
# se abre la ventana. La ventana se queda abierta —nadie aprieta A— así que
# todos los cuadros que se comparan la tienen en pantalla, con el mapa
# scrolleando por detrás.
#
# Los cuadros están elegidos por el resto de la cámara contra 8, que es lo que
# hundió al intento anterior: estampando la ventana en celdas del tilemap del
# mapa, sólo puede caer bien cuando `camara_x` y `camara_y` son múltiplos de 8,
# o sea un cuadro de cada cuatro por eje. Con el tilemap propio y el HDMA no
# depende del scroll y los cuatro dan cero.
#
#   cuadro  21   camara_x 722, resto 2   (antes: 2627 pixeles)
#   cuadro  23   camara_x 726, resto 6   (antes: 3198)
#   cuadro  50   camara_y 700, resto 4   (antes: 5964)
#   cuadro 130   la ruta ya bajó doce celdas   (antes: 11705)
#
# El mapa 6 por lo mismo que `snes-ruta`: es 100x100 y abierto, así que la ruta
# camina sin chocar, y es **mudo**, que es lo que hace usable el desfasaje de
# arranque —la ROM llega al primer cuadro del intérprete en 10, contra 44 en un
# mapa con música, y la referencia no modela nada de eso—.
snes-anclada mapa="6" ruta="1 1 1 1 1 1 2 2 2 2 2 2" cuadros="21 23 50 130" arranque="10" nombre="anclada":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  linea1="SEWELL"
  linea2="There you are, Talan. Ready for"
  linea3="the big night?"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --ruta-de-prueba {{ruta}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --ruta-de-prueba {{ruta}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Cuánto destraba cada comando de evento que todavía no hacemos.
#
# Es lo que decide por dónde seguir, y existe porque el número que este repo
# venía usando medía otra cosa: la tabla de "Lo que falta" del LEEME cuenta qué
# comando corta **primero** cada página, y una página cortada por un cuadro de
# texto puede estar cortada además por otras cuatro cosas. Lo que hay que contar
# es cuántas páginas pasan a compilar enteras, que es lo que hace esto.
#
# Se corre después de cada feature nueva: el orden cambia a medida que las
# páginas se van destrabando entre ellas.
snes-destraba:
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
# No entra en `snes-hitos` y es a propósito: levanta un Xvfb, corre el juego
# durante medio minuto y depende de EasyRPG bajado a /extras. Se corre a mano
# cuando se toca la ventana o la fuente. El detalle está en `rom/easyrpg.sh`.
#
# Lo único que puede diferir sin ser un error es la flecha roja de "seguir" que
# EasyRPG anima mientras espera al jugador, que nosotros no dibujamos.
snes-oraculo mapa="145" segundos="20":
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
#   just snes-mensaje 1        la primera página de mensaje del mapa 1
#   just snes-mensaje 1 4 4    la quinta, agrandada cuatro veces
snes-mensaje mapa="1" indice="0" escala="1":
  mkdir -p {{snes_pngs}}
  python3 tools/snes_mensaje.py --map-id {{mapa}} --indice {{indice}} \
      --escala {{escala}} -o {{snes_pngs}}/mensaje-{{mapa}}-{{indice}}.png

# Una ruta forzada sobre el héroe, con las órdenes que la ROM sabe caminar.
#
# Son quince de las cuarenta y dos de `rpg::MoveCommand::Code`: moverse en los
# cuatro sentidos, girar en los cuatro, esperar, saltar, atravesar paredes y
# parar o seguir la animación. El resto —las diagonales, cambiar el gráfico,
# la velocidad, girar sin moverse— sigue afuera.
#
# Cuatro casos, y cada uno mira una cosa que sale de leer easyrpg:
#
# * **El default**, con dos esperas en el medio. Un `wait` de ruta **no cuesta
#   un cuadro sino veinte**: es `SetMaxStopCountForWait`, que da
#   `20 + (1 << (8 - frecuencia))` y con la frecuencia 8 son veinte. Valía uno
#   de los dos lados a la vez, así que la comparación daba cero. Los cuadros 60
#   y 120 caen adentro de las esperas: con el valor viejo dan 12747 pixeles.
# * **El salto.** `begin_jump` … `end_jump`: lo que hay en el medio no se
#   camina, se suma, y el personaje aparece del otro lado en once cuadros, los
#   mismos salte una celda o cinco. Sube en arco —`GetJumpHeight`, que no es
#   lineal— y el arco mueve el **dibujo** y no el orden: `GetScreenZ` usa
#   `GetScreenY(false)`, así que quien está en el aire no se adelanta.
# * **Atravesar paredes.** La fila y = 4 del mapa 6 es pared salvo en x = 14, y
#   el héroe arranca en (10, 8) y camina seis para arriba: sin `walk_everywhere`
#   se frena contra ella. Es el `if (self.GetThrough()) return true;` de
#   `CheckOrMakeWayEx`.
# * **Parar la animación.** El ciclo de caminata se congela en la pose del
#   medio, pero el personaje sigue caminando. Es `ResetAnimation`, que RM2k
#   llama en cada cuadro mientras `IsAnimPaused()`.
#
# Una ruta forzada, comparada **mientras camina** y no sólo donde termina.
#
# Es el caso que faltaba para poder aceptar los `move_*` de MoveEvent. Lo que
# hay que verificar no es dónde queda el héroe —eso ya lo mira cualquier
# comparación del cuadro final— sino la trayectoria: la celda, la cámara y sobre
# todo **la columna del ciclo de caminata**, que es donde estaban los dos
# errores que esto destapó, los dos de la referencia y no de la ROM.
#
# El mapa por defecto es el 6 por dos razones concretas: es 100x100 y está
# abierto al 100%, así que una ruta camina en cualquier dirección sin chocar; y
# **es mudo**, que es lo que hace usable el desfasaje de arranque. La ROM no
# empieza a interpretar en el cuadro 0 —hay reset, carga de mapa y subida al
# SPC700— y la referencia no modela nada de eso, así que para comparar un cuadro
# intermedio hay que decir cuántos cuadros de más lleva la ROM. Medido: 10 en el
# mapa 6, contra 44 en el 73, que tiene música. Si algún día los tres cuadros
# dan rojo a la vez y el asentado no, es esto: volver a medirlo barriendo el
# desfasaje contra un cuadro cualquiera.
#
# Ni la ruta ni los cuadros son cualquiera, y elegirlos a ojo hacía que la
# prueba pasara con los errores adentro. La ruta son tres patas de cuatro celdas
# —derecha, abajo, arriba— con **dos cuadros de espera** entre pata y pata, o
# sea 100 cuadros. Los que se comparan son el 18 y el 86 —caminando, y a 18
# cuadros del arranque de su pata, que es múltiplo de ANIM_FRAMES = 6 y por lo
# tanto donde el ciclo cambia de columna—, el 34 —la primera espera, con el
# héroe quieto— y el 400, asentado.
#
# El porqué de que sean cuatro celdas por pata y no doce de corrido: los errores
# de contador sólo se ven si la columna en la que queda el ciclo **no** es la
# parada, y 8 cuadros por celda por 12 celdas da 96, que cae justo en la parada.
# Con cuatro celdas da 32, que cae en la columna 2. Elegido midiendo: los tres
# errores se volvieron a meter de a uno y los tres dan rojo. Ver ESTADO.md.
#
# * **La frecuencia.** Con una que no sea la 8 el personaje se queda quieto
#   entre orden y orden: es el contador de parada de RM2k, `1 << (9 - f)`
#   cuadros después de un paso y `1 << (8 - f)` después de un giro, y el `wait`
#   son 20 más eso. `ruta-lenta` es la 4 —la de la cinemática de apertura— con
#   dos pasos, un giro, un paso, un `wait` y un paso: el paso va del 1 al 8 y
#   el siguiente recién arranca en el 41, el giro cae en el 81 y suelta en el
#   97, y el `wait` del 137 dura 36. Los cuadros 20 y 88 son quieto después de
#   un paso y de un giro, el 44 y el 100 a mitad de paso, el 150 adentro del
#   `wait`, y el 400 asentado.
snes-ruta mapa="6" ruta="1 1 1 1 23 23 2 2 2 2 23 23 0 0 0 0" cuadros="18 60 120 400" arranque="10" nombre="ruta" inicio="" frecuencia="8":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  desde=""; celda=""
  if [ -n "{{inicio}}" ]; then desde="--inicio {{inicio}}"; celda="--hero-tile {{inicio}}"; fi
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} $desde \
      --ruta-de-prueba {{ruta}} --frecuencia {{frecuencia}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  # Las referencias de todos los cuadros salen de una sola conversión, por lo
  # mismo que las de los avances de snes-caminando.
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none $celda \
      --ruta-de-prueba {{ruta}} --frecuencia {{frecuencia}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Una ruta forzada que termina sobre un evento de contacto, y otra que pasa por
# encima de uno.
#
# Es el disparo que le faltaba a la cinemática de apertura: la página del mapa 1
# manda al héroe tres celdas para arriba y termina en el mismo cuadro, y el
# evento que apaga el tinte está en la tercera celda, con disparo por contacto.
# La regla es la de `Game_Player::UpdateMovement`: al terminar un paso se mira
# la celda **salvo que el héroe tenga una ruta forzada puesta**, y un movimiento
# que es la última orden de la ruta la cancela entera antes de ese chequeo. O
# sea: los pasos del medio no pisan nada, el último sí. La ROM tenía la mitad
# —miraba en todos— y la referencia la otra —no miraba en ninguno—.
#
# El mapa 70 es el de `snes-pisar`: la columna x = 12 es pasillo de (12,3) a
# (12,8) y el evento de contacto está en (12,4), con un cuadro de texto. Tres
# casos, todos con el héroe plantado en (12,8):
#
# * cuatro para arriba: termina sobre el evento y el mensaje se abre. Los
#   cuadros 16 y 24 son el paso del medio —sin ventana— y el 200 la ventana
#   abierta.
# * cinco para arriba: **pasa** por el evento en el cuarto paso y termina en
#   (12,3). No se abre nada; con la ROM vieja se abría en el cuarto paso.
# * cuatro para arriba con la página **esperando 60 cuadros y tiñendo** detrás:
#   la ruta termina en el 32 con la página todavía corriendo. RM2k no pierde el
#   contacto: lo deja esperando y lo corre cuando la página termina, o sea
#   después del tinte. La ROM lo descartaba; ahora lo encola.
#
# El desfasaje de arranque del mapa 70 es 43, medido barriendo contra la
# referencia del cuadro 16: con 40 —el de `snes-pisar`, que nunca lo necesitó
# exacto porque el pad sostenido llega igual— el héroe queda tres cuadros atrás
# y la pose no coincide.
snes-ruta-pisa mapa="70" celda="12 8" ruta="0 0 0 0" pagina="0" cuadros="16 24 200" arranque="43" nombre="ruta-pisa":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana \
      --ruta-de-prueba {{ruta}} --pagina-de-prueba {{pagina}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --con-ventana \
      --ruta-de-prueba {{ruta}} --pagina-de-prueba {{pagina}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La otra segunda opinión, la que sí sale gratis: los mismos casos en bsnes.
#
# bsnes es el emulador preciso, y sobre todo es el que **llena la WRAM de basura
# al encender** —`bsnes_entropy`, que acá va en "High"—, que es lo que hace la
# consola de verdad y lo que snes9x no hace: lo que snes9x deja es siempre lo
# mismo, y por eso la tanda entera daba verde con `ruta_n`/`ruta_i` sin
# inicializar, que sin inicializar quedan iguales entre sí. Con esto la tanda ve
# esa clase de error sola, sin que nadie tenga que jugar.
#
# Cuánto ve, medido y no supuesto: comentando esas dos líneas de `main.s`, sobre
# 20 corridas del mapa 7, con "None" difieren 0 cuadros, con "Low" 3 y con
# "High" 11. O sea que no lo agarra siempre —la basura tiene que caer en un
# valor que rompa—, pero lo agarra la mitad de las veces y no cuesta nada. Con
# la ROM sana, 20 de 20 dan el mismo cuadro.
#
# Son los mismos dos casos que `snes-mednafen` y por lo mismo: uno que tiñe
# desde un evento —CGRAM y el intérprete— y uno que camina —la RAM del control—.
# No la reemplaza: mednafen no es un core de libretro, así que también prueba
# que `tools/retro.py` no se esté equivocando parejo con los tres cores.
#
# El tercer caso es el mensaje, y no está de adorno. Es el código más nuevo y el
# que más CGRAM y VRAM toca con la pantalla apagada —`load_ventana` sube tiles y
# una paleta entera, `mensaje_de_evento` escribe el tilemap—, que es justo la
# clase de escritura que snes9x perdona; ahí ya nos mordió dos veces, con el
# tinte aplicado mientras el PPU dibujaba.
#
# Va `snes-cerrar` y no `snes-ventana` porque cubre lo mismo y algo más: su
# primer cuadro es la ventana dibujada, igual que allá, y el segundo es el
# cierre. De paso trae `msg_abierto`, que es una variable de RAM que si nadie
# pone en cero deja la página bloqueada para siempre —medido: sin su `stz`, el
# cuadro 400 se cae en las doce corridas—.
#
# Va por CORE y no por `just --set` porque las recetas se llaman entre ellas: la
# variable de entorno cruza a los `just` de adentro y el `--set` no.
snes-bsnes:
  #!/usr/bin/env bash
  set -euo pipefail
  CORE=bsnes just snes-evento 4 1 bsnes-evento
  CORE=bsnes just snes-caminando 73 right 60 bsnes-73-right
  CORE=bsnes just snes-cerrar 7 200 bsnes-cerrar

# Que una espera espere de verdad, con una página inventada.
#
# El intérprete corre cuadro a cuadro desde que dejó de colapsar el tiempo, pero
# **ninguna página del juego que compile tiene una espera**, así que ese camino
# —el corazón del cambio— no lo ejercitaba nada. Es el mismo caso que
# `snes-encima`, que existe porque ningún evento del juego llega a la prioridad
# 2: lo sintético es la entrada, no la comparación. Los dos lados corren el mismo
# bytecode y se comparan como siempre, la ROM contra la referencia.
#
# Se mira antes y después, no el cuadro exacto en que cambia. El arranque de la
# ROM incluye la subida al SPC700 —unos 42 cuadros cuando el mapa tiene música—
# y la referencia no modela eso, así que el borde cae en cuadros distintos de
# cada lado. Con margen a los dos lados eso no importa y la prueba sigue siendo
# filosa: si la espera no esperara, a los 60 cuadros ya estaría teñida. Entre las
# dos capturas hay 57247 pixeles de diferencia.
snes-espera mapa="73" espera="120" antes="60" despues="400" nombre="espera":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --pagina-de-prueba {{espera}} 0 0 50 -o {{snes_inc}}/mapdata.inc
  just snes-build
  for n in {{antes}} {{despues}}; do
    python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
        --pagina-de-prueba {{espera}} 0 0 50 --cuadros $n \
        --saltar {{snes_pngs}}/saltar-{{nombre}}-$n.txt \
        -o {{snes_pngs}}/esperado-{{nombre}}-$n.png
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}-$n.png \
        --walk none --cuadros $n --arranque 0
    python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-$n.png \
        {{snes_pngs}}/esperado-{{nombre}}-$n.png \
        --saltar {{snes_pngs}}/saltar-{{nombre}}-$n.txt \
        -o {{snes_pngs}}/comparacion-{{nombre}}-$n.png
  done

# El héroe a mitad de camino: se lo captura con N pixeles andados, en la pose
# de caminata que le toca, y se compara contra la referencia calculada para ese
# mismo avance.
#
# Es la única prueba que mira el movimiento en sí. Todas las demás comparan el
# cuadro final, y ahí el héroe está chocando contra una pared: `moving` vale
# cero, así que la pose es siempre la parada y las tres columnas del ciclo de
# caminata no las verificaba nada. Acá además se ejercitan la velocidad —dos
# pixeles por cuadro— y la cámara a mitad del scroll.
#
# Los avances por defecto caen en columnas distintas del ciclo: 40 px son 20
# cuadros moviéndose y da la columna 0, 60 da la 2 y 80 da la 1. Errarle por un
# solo cuadro mueve unos 25000 pixeles, así que la prueba es de las filosas.
snes-caminando mapa="73" direccion="right" avances="40 60 80" nombre=(mapa + "-" + direccion):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc
  just snes-build
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

# Pasa los 335 mapas por los límites del hardware sin armar ninguna ROM: dice
# cuáles no entran y por qué. Correr cuando se toque el conversor o el reparto
# de la VRAM.
snes-relevar desde="0":
  python3 tools/snes_survey.py --desde {{desde}}

# Cuánto llega a caminar el héroe en cada mapa, con las mismas reglas que la
# ROM. Sirve para elegir contra qué mapa probar el redibujado: uno enorme lleno
# de paredes frena en la tercera celda y no prueba nada.
snes-recorrido desde="66":
  python3 tools/snes_recorrido.py --desde {{desde}}

# La tanda de regresión: un mapa por cada cosa que puede romperse.
#
# Los tres primeros son los que cerraron los hitos anteriores y tienen que
# seguir en cero. Los tres últimos son los que ejercitan el redibujado: mapa 6
# recorre 100 celdas por los dos ejes, o sea que la ventana da la vuelta tres
# veces a lo alto; mapa 8 es Lashe City, que además necesita 512 tiles de
# sprite y por eso le toca el otro reparto de VRAM; y mapa 52 mide 1000x80
# celdas, con una grilla de 40 KB que cruza el corte de banco de LoROM.
#
# Los dos siguientes ejercitan el reparto de CGRAM: mapa 1 es el primero del
# juego y su capa de encima se lleva cuatro paletas, dejándole 63 colores al
# fondo; mapa 348 es el caso contrario, donde el fondo usa los 95 que puede y la
# capa de encima tiene que fusionar 27 colores para entrar en lo que sobra.
#
# Los dos últimos son el borde de abajo de la pantalla, y van de a pares porque
# se equivocan para lados opuestos. En (75,88) del mapa 1 hay cuatro NPCs justo
# debajo del borde, en la banda donde la Y de OAM es ambigua: con el descarte
# corrido para un lado reaparecen arriba. En (75,90) los mismos cuatro asoman
# apenas la cabeza: con el descarte corrido para el otro lado desaparecen. Uno
# solo de los dos casos deja pasar la mitad de los errores posibles.
#
# Ninguna caminata los tocaba: todas terminan contra un borde del mapa, y ahí la
# cámara queda pegada y los NPCs no caen nunca en esa banda.
#
# Y los dos del final son la ROM con varios mapas: que uno se vea bien cuando su
# registro no está al principio de la tabla, y que cruzar una puerta deje la
# pantalla donde tiene que quedar.
#
# Y el último es el intérprete de eventos: la ROM arranca en el mapa 4, corre
# la página que abre el juego —dos switches, un tinte y un teletransporte— y
# tiene que terminar en el mapa 1, teñida, con el héroe en la celda que dice el
# teletransporte y tapado por la capa de encima. La referencia corre el mismo
# bytecode, así que lo que se compara es que las dos implementaciones del
# intérprete estén de acuerdo, no que una de las dos ande.
#
# Ese mismo evento va dos veces, con una tabla de dos mapas y otra de cuatro.
# Un teletransporte compilado guarda el índice en la tabla, no el número de
# mapa, y con la tabla de dos el índice es 1: el desplazamiento es un solo
# MAPA_STRIDE y varias cuentas mal hechas dan bien igual. Con [4,7,19,1] el
# mismo salto compila a 3. Cambiarlo a mano a 2 —o sea, mandar la ROM al mapa
# 19— mueve 55336 de los 57344 pixeles, así que el caso no se puede pasar por
# casualidad.
#
# Los tres del final son las prioridades de objeto contra la capa de encima.
# `snes-evento` ya deja al héroe tapado, pero entero —768 de 768 pixeles—, y un
# héroe que no se dibujara en absoluto daría la misma pantalla. Los dos de la
# celda (66,40) del mapa 1 son la misma escena con un solo bit distinto: ahí la
# capa tapa 512 de 768, así que la silueta tiene que partirse en el lugar
# exacto, primero con el héroe en prioridad 1 —debajo— y después en prioridad 2
# —encima—. Entre las dos referencias hay 284 pixeles de diferencia, o sea que
# el par no puede dar cero por casualidad.
#
# El tercero es el único evento marcado "above" del juego: el Package del mapa
# 261. Su prioridad no se puede ejercitar ahí —la capa de encima de ese mapa no
# lo toca por dos pixeles, ver `snes-encima`—, pero sí el resto del camino: con
# el héroe en (59,2) los dos sprites se pisan, y el Package tiene que quedar
# adelante aunque el héroe esté más abajo en la pantalla. Tratarlo como un NPC
# común mueve 79 pixeles.
#
# Cuántos cuadros dura cada caminata no se elige: lo dice la referencia, que
# camina celda por celda y sabe cuántas son. Ver `snes-caminando`.
#
# La lista vive en rom/hitos.txt y no acá, para que ésta y snes-hitos-paralelo
# corran la misma: escrita dos veces, la que se olvide un caso sigue dando
# verde y nadie se entera.
snes-hitos:
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

# Los mismos casos, uno por proceso y cada uno en su propia corrida aislada.
# En serie son unos dos minutos y medio y repartida no llega al minuto; lo que
# domina ya no es el emulador sino convertir los mapas en Python.
#
# Un rojo acá se puede creer sin más. Cuando la tanda esperaba al reloj no: el
# emulador corría en tiempo real y una máquina sobresuscrita emulaba menos
# cuadros en los mismos segundos, el héroe quedaba corto de la pared y la
# comparación se disparaba sin que nada estuviera roto. Ahora N cuadros son N
# cuadros, con la carga que sea.
snes-hitos-paralelo trabajos="4":
  #!/usr/bin/env bash
  set -uo pipefail
  mkdir -p rom/build
  # Por xargs viajan números de línea y no los casos. xargs procesa comillas y
  # se come las de `snes-evento 4 "7 19 1" tabla`, que entonces le llega a just
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

# El héroe: parado y caminando en las cuatro direcciones.
#
# Las cinco referencias salen de una sola corrida de snes_expect.py y no de
# cinco. Convertir el mapa es lo más caro de toda la tanda —el 52 son 14
# segundos— y las cinco direcciones comparten todo eso: tiles, reparto de
# paletas, reuso y espejados. Lo único que cambia es dónde termina el héroe y
# dónde queda la cámara. Medido en el mapa 52: 71,6 s de a una contra 15,0 s
# todas juntas, con los PNG y los archivos de --saltar idénticos.
snes-heroe mapa="7":
  #!/usr/bin/env bash
  set -euo pipefail
  just snes-convert {{mapa}}
  just snes-build
  # La referencia va primero porque es la que dice cuántos cuadros dura cada
  # caminata: sabe cuántas celdas se recorren, y el paso son ocho cuadros. Antes
  # el orden daba igual, porque el emulador corría un número de segundos
  # elegido a ojo.
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none right left up down \
      --saltar {{snes_pngs}}/saltar-{{mapa}}-{}.txt \
      --plan {{snes_pngs}}/plan-{{mapa}}.txt \
      -o {{snes_pngs}}/esperado-{{mapa}}-{}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} \
      -o {{snes_pngs}}/{{mapa}}-{}.png --walk none right left up down \
      --plan {{snes_pngs}}/plan-{{mapa}}.txt
  for d in none right left up down; do
    python3 tools/snes_compare.py {{snes_pngs}}/{{mapa}}-$d.png \
        {{snes_pngs}}/esperado-{{mapa}}-$d.png \
        --saltar {{snes_pngs}}/saltar-{{mapa}}-$d.txt \
        -o {{snes_pngs}}/comparacion-{{mapa}}-$d.png
  done

_tecla direccion:
  @case {{direccion}} in up) echo Up;; down) echo Down;; left) echo Left;; right) echo Right;; *) echo "";; esac

# Todo el camino del mapa: convertir, compilar, y verificar la cámara en las
# cuatro esquinas a las que puede llegar.
#
# Cada dirección se mantiene apretada hasta que la cámara choca contra el borde
# del mapa, así que dónde tiene que quedar no se estima: es exactamente
# CAM_MAX_X y CAM_MAX_Y, que salen del tamaño del mapa. Si la ROM se moviera de
# más, de menos, o no frenara, la comparación falla.
snes-mapa mapa="7" cuadros="300":
  just snes-convert {{mapa}}
  just snes-build
  just snes-shot {{mapa}}-centro {{cuadros}}
  just snes-compare {{mapa}}-centro 0 0
  just snes-shot {{mapa}}-derecha {{cuadros}} "Right"
  just snes-compare {{mapa}}-derecha $(just _cam-x) 0
  just snes-shot {{mapa}}-abajo {{cuadros}} "Down"
  just snes-compare {{mapa}}-abajo 0 $(just _cam-y)
  just snes-shot {{mapa}}-esquina {{cuadros}} "Right Down"
  just snes-compare {{mapa}}-esquina $(just _cam-x) $(just _cam-y)

# Los topes de la cámara salen del .inc que generó el conversor, así que las
# recetas no repiten números que dependen del mapa.
_cam-x:
  @grep -oP 'CAM_MAX_X\s*=\s*\K\d+' {{snes_inc}}/mapdata.inc
_cam-y:
  @grep -oP 'CAM_MAX_Y\s*=\s*\K\d+' {{snes_inc}}/mapdata.inc

# --- verificación del ensamblador ------------------------------------------
# w65.py reemplaza a ca65 y ld65. Que se pueda confiar en él no es una promesa:
# se genera un fuente con cada mnemónico en cada modo de direccionamiento que la
# tabla declara, se ensambla con las dos cadenas y se comparan los bytes.
#
# Correr esto cada vez que se toquen las tablas de opcodes. Necesita podman, así
# que va desde el host, no desde adentro del contenedor.
#
# Lo que compara es el primer banco: w65.py arma el cartucho entero, 256 KB, y
# snes.cfg describe uno de 32. Del resto se comprueba que sea relleno.
#
# Lo que valida es la codificación de instrucciones, que es lo que se puede
# equivocar en silencio. El layout de la ROM —banqueo LoROM, 128 KB, checksum—
# ya no se compara: ca65 necesitaría una configuración bastante más compleja
# para expresarlo, y main.s dejó de entrar en los 32 KB de snes.cfg cuando el
# banco de muestras creció. A cambio, el layout sí se verifica de punta a punta
# cada vez que la ROM arranca y suena en el emulador.
#
# rom/snes.cfg y rom/Makefile existen sólo para esto.

snes-image:
  podman build -t abl-snes snes

snes-validar:
  python3 tools/w65_coverage.py -o rom/build/cobertura.s
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/snes abl-snes \
      sh -c 'ca65 --cpu 65816 -o build/cobertura.o build/cobertura.s \
             && ld65 -C snes.cfg -o build/cobertura-ca65.sfc build/cobertura.o'
  python3 tools/w65.py --sin-checksum rom/build/cobertura.s -o rom/build/cobertura-w65.sfc
  python3 tools/w65_check.py rom/build/cobertura-w65.sfc rom/build/cobertura-ca65.sfc

# El MIDI del mapa a muestras BRR y un stream para el DSP.
# La música de un mapa a mano. Normalmente no hace falta: `snes-convert` ya la
# genera junto con el mapdata, que es lo que garantiza que los dos describan la
# misma ROM. Esto queda para mirar un tema suelto sin armar nada más.
snes-music mapa="67":
  mkdir -p {{snes_inc}}
  python3 tools/snes_music.py --map-id {{mapa}} -o {{snes_inc}}/musicdata.inc

# Corre la ROM sin pantalla, graba el audio y compara lo que suena contra el
# MIDI. Sirve para verificar sin escuchar: para cada nota que debería estar
# sonando se mide su energía y la de un señuelo un cuarto de tono más arriba.
snes-check mapa="67" segundos="60" tema="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  cual=""
  if [ -n "{{tema}}" ]; then cual="--tema {{tema}}"; fi
  rom/record.sh {{snes_rom}} {{snes_pngs}}/tema.wav {{segundos}}
  python3 tools/snes_check.py {{snes_pngs}}/tema.wav --map-id {{mapa}} $cual

# El mismo MIDI tocado por FluidSynth en la PC, con el mismo SoundFont del que
# salen nuestras muestras, y medido con la misma vara. Es el techo: dice cuánto
# de lo que falta es culpa nuestra y cuánto es de la medición.
snes-referencia mapa="67" banco="/extras/soundfonts/Microsoft GS Wavetable Synth.sf2":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  fluidsynth -F rom/shots/referencia.wav -r 48000 \
      "{{banco}}" \
      "$(python3 tools/midi_path.py --map-id {{mapa}})"
  python3 tools/snes_check.py rom/shots/referencia.wav --map-id {{mapa}}

# Todo junto: convertir, compilar y verificar.
snes mapa="67": (snes-music mapa) snes-build (snes-check mapa)

# La ROM en una ventana, con sonido. Va en el host: acá adentro no hay
# dispositivo de audio, y el ALSA propio de mednafen abre hw:0.
snes-play:
  mednafen -command.exit "keyboard 0x0 20+ctrl" -sound.driver sdl {{snes_rom}}
