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
# rom/build/abl.sfc` y las rutas escritas en el README sigan valiendo.
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
# `--descartar-eventos` porque el mapa 8 tiene `PawnDoorTop`, que cambia de
# gráfico entre sus páginas y no entra en las ocho paletas de sprite: sin el
# flag el conversor corta, que es lo que se quiere en un build de verdad. Acá se
# está mirando cómo se dibuja el héroe y da lo mismo, así que se deja pasar.
snes-convert mapa="7":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc \
      --descartar-eventos --reference {{snes_pngs}}/python.png

snes-build:
  python3 tools/w65.py rom/src/main.s -I {{snes_inc}} -o {{snes_rom}} --simbolos {{snes_rom}}.sym

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
      --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt --margen 0
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
# El plan cuenta ahora los 70 cuadros del fundido de la puerta además de los
# ocho por celda: en este caso son 142 y no 72, y la pantalla queda quieta
# exactamente en el 142. Eso es un dato en sí mismo —la carga del mapa pasa
# adentro del negro y no corre el reloj—; el margen de 16 quedó de cuando la
# ROM se tomaba siete cuadros de más que nadie contaba, y ahora es aire nomás.
snes-puerta origen="30" destino="28" direccion="down" nombre=("puerta-" + origen + "-" + destino):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{origen}} --mapas {{destino}} \
      --walk {{direccion}} --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      --plan {{snes_pngs}}/plan-{{nombre}}.txt --margen 16 \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
      --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      --margen 0
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
  # Siete segundos, que con el arranque de mednafen son unos cuatro y medio de
  # emulación: el fundido del teletransporte termina a los 3,8 y el relámpago
  # del mapa 1 cae a los 7,85, medidos en el core. Eran seis hasta el
  # 2026-09-11; el paquete de audio del mapa 1 alarga el fundido unas
  # décimas, y a los seis quedaba a mitad de camino. Antes fueron cinco, y el
  # fundido de 70 **ticks** los pasó a seis. Esta captura es por reloj de
  # pared —mednafen de verdad, no un core— así que no se puede alinear por
  # tick.
  rom/mednafen.sh {{snes_rom}} {{snes_pngs}}/med-evento.png 7 ""
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
# El mapa 1 —el que descubrió el reparto, porque el conversor cortaba, y
# fusiona 2— estuvo afuera un día: con ventana compila la escena de apertura,
# que hace caminar a cuatro personajes, y con todas las poses residentes eran
# 768 tiles de sprite contra los 512 que direcciona la PPU. Volvió el
# 2026-09-05 con las poses en caliente: son 120.
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
# héroe daría unos pasos que la referencia no modela. El 115 es el de todas las
# recetas desde que el arranque de la ROM es fijo —ver "El arranque dura
# siempre lo mismo" en el README—: el cuadro N de la captura es el tick N de
# la referencia, en cualquier mapa.
snes-cerrar mapa="7" apretar="200" nombre="cerrar" direccion="none" arranque="115":
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

# Los dos escapes de texto de RM2k: `\|`, que pausa el cuadro, y `\^`, que lo
# cierra sin que el jugador apriete nada. Es `snes-cerrar` sin la A.
#
# Lo que compara, y por qué son estos dos cuadros:
#
#   antes    la ventana en pantalla y la página frenada, con la pausa corriendo:
#            el tinte que va detrás del mensaje todavía no se aplicó
#   después  la ventana cerrada **sola** y el tinte puesto
#
# El segundo es el que no existía: hasta el 2026-09-13 la única forma de cerrar
# un mensaje era el flanco de A, así que una página con `\^` habría quedado
# esperando para siempre. Y la elección de los cuadros no es cosmética: el de
# "antes" va pegado al cierre para que **61 y 60 no den lo mismo** —con 60 la
# ventana ya se cerró ahí y la comparación se dispara—, que es el número que
# easyrpg tiene comentado como distinto de lo que dice la documentación.
#
# La cuenta de los dos lados arranca en el cuadro en que la página pide el
# mensaje y no en el que la ventana termina de componerse: la referencia dibuja
# la ventana de golpe y la ROM tarda entre nueve y diecinueve cuadros, así que
# contar desde el final de la composición dejaría a la ROM cerrando tarde para
# siempre. Con la pausa de 61 la composición termina mucho antes y en pantalla
# se ve lo mismo.
#
# `pausas` son cuántos `\|` lleva la cola, que es lo que el juego varía: 25
# cuadros usan `\|\^`, diez `\|\|\^` y dos `\|\|\|\^`.
snes-autocierre pausas="1" cuadros="62 63" nombre="autocierre" mapa="7" arranque="115":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  linea1="SEWELL"
  linea2="There you are, Talan. Ready for"
  cola=""
  for _ in $(seq 1 {{pausas}}); do cola="$cola\\|"; done
  linea3="the big night?$cola\\^"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --pagina-de-prueba 0 0 0 50 -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --mensaje-de-prueba "$linea1" "$linea2" "$linea3" \
      --pagina-de-prueba 0 0 0 50 --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
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
snes-ruta-evento mapa="6" ruta="3 0 0 0 0 0 0 3 3 3 23 2 2 1 13" cuadros="89 91" arranque="115" nombre="ruta-evento":
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
#
# Y dos de diagonales, desde el 2026-09-06. Las camina sólo un evento: de las
# 26 rutas del juego que las usan ninguna es del héroe, y el conversor rechaza
# la que lo intente.
#
# * `npc-diagonal` es la **regla de paso**, y por eso no corre en el mapa 6,
#   que está abierto por los cuatro lados. Va en el mapa 10, donde el evento 0
#   está en (3,10) con una pared pegada a la derecha y otra justo abajo, y las
#   tres respuestas posibles salen de esa sola celda: arriba-derecha no se
#   puede por ninguna de las dos eles y se saltea sin costar un cuadro,
#   abajo-izquierda **sólo** se puede rodeando primero por la izquierda —o
#   sea que es la segunda ele la que lo salva—, y arriba-izquierda se puede
#   por las dos. Medido contra un control: la ruta que baja en diagonal
#   mueve al evento 340 pixeles respecto de una que espera, y la trabada da
#   cero contra ella.
# * `npc-diagonal-gira` es hacia dónde queda mirando, que no es hacia el
#   rincón: el charset tiene cuatro poses. El evento mira a la izquierda y
#   camina abajo-derecha, así que se da vuelta 180° y termina mirando a la
#   derecha. Comprobado por los dos lados: el caso da idéntico a mirar a la
#   derecha desde el principio, y distinto a mirar hacia abajo.
#
# Y `npc-hacia-heroe`, desde el 2026-09-12: la orden 9, `move_towards_hero`,
# que es la que destraba la pelea de los Lazer Teeth. No es una orden nueva
# sino dos que ya estaban pegadas —encarar al héroe y dar el paso—, y el caso
# mira justamente la costura. El evento 3 arranca en (22,9) y el héroe está en
# (25,10): tres a la derecha y una abajo, así que manda el eje horizontal y el
# evento camina a la derecha; al llegar a (25,9) el héroe le queda **abajo** y
# la cuarta orden lo gira hacia abajo, donde ya no puede avanzar —el héroe
# ocupa la celda— y se saltea. O sea que el cuadro 70 prueba lo que ninguna
# posición prueba: que la dirección se recalcula en cada orden y que **girar
# pasa antes de mirar si se puede**, que es el orden de `UpdateMoveRoute`.
# Verificado en rojo con el defecto puesto: sin el desvío de la 9 en
# `cuadro_de_ruta_ev` la ROM la manda a `mover` con una dirección que no es
# 0..3, y el cuadro 5 ya da 479 pixeles.
snes-npc mapa="6" ruta="4 2 2 2 2 1 1 12" celda="22 12" cuadros="10 27 40 60" arranque="115" nombre="npc" frecuencia="8":
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

# Un evento que cambia de gráfico a mitad de una ruta: la orden 34.
#
# Es la última de `MoveCommand` que faltaba de las que este juego usa, y la
# única con **operando**: detrás del 34 va el índice del gráfico, que
# `--grafico-de-prueba` registra acá y las páginas del juego registran solas.
#
# Dos cosas que hay que mirar y no son la misma:
#
#   que cambie          el evento camina con un gráfico y sigue caminando con
#                       otro, con la pose del ciclo donde estaba y la paleta
#                       del gráfico nuevo
#   que desaparezca     185 de las 437 órdenes 34 del juego cambian a
#                       `nobodyhere`, un CharSet sin un solo pixel opaco. Ahí
#                       la fila se esconde y deja de ocupar un objeto
#
# El mapa 6 otra vez, con el evento 3 —blanco 4— bajando cuatro celdas y
# cambiando de gráfico en el medio: los cuadros de antes lo miran con el suyo y
# los de después con el nuevo, **caminando**, que es lo que separa "cambió el
# gráfico" de "cambió y se quedó quieto".
#
# Y desde el 2026-09-12 la misma orden **sobre el héroe** —el blanco 0—, que es
# lo que destraba el `EV0047` del mapa 8. Dos casos, uno por rama:
#
#   `grafico-heroe`     cambia a `Future1 0` mientras baja. El líder de estas
#                       ROMs es `Future1 5`, así que el cambio se ve: contra la
#                       misma ruta sin la 34 son 233 pixeles en el cuadro 40
#   `heroe-invisible`   cambia a `nobodyhere`, el CharSet sin un solo pixel
#                       opaco, y el héroe **deja de dibujarse**: 311 pixeles
#                       contra el control
#
# Verificado en rojo con el defecto puesto: sin el desvío de la 34 en
# `paso_de_ruta` el operando se lee como una orden y el cuadro 20 da 11128
# pixeles distintos.
#
# Los cuadros llegan hasta el 40 y no hasta el 70 por algo **anterior a esto**:
# una ruta forzada del héroe que baja cuatro celdas desde (22,12) en el mapa 6
# da diez pixeles de diferencia a partir del cuadro 47, con la 34 y sin ella
# —el control `2 2 2 2` da lo mismo—. Son dos tiles animados del chipset
# cambiando de paso un cuadro antes de un lado que del otro. Está anotado en
# ESTADO.md; no es de esta vuelta y no se investigó.
snes-grafico mapa="6" ruta="4 2 2 34 0 2 2" grafico="Future1 0" celda="22 12" cuadros="10 25 40 70" arranque="115" nombre="grafico":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --ruta-de-evento {{ruta}} \
      --grafico-de-prueba {{grafico}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --ruta-de-evento {{ruta}} \
      --grafico-de-prueba {{grafico}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# El caso `talan` es la escena entera del Emitter Room, y es el más largo de la
# tanda: mil doscientos cuadros de los 233 comandos de la página de contacto del
# evento 5 del mapa 3, la que se destrabó con los seis puntos del 2026-09-06.
# Pide `--mapas 1 2 4 5` porque termina teletransportando al 4, y el switch 13
# para que la página de contacto esté activa: en el juego lo prende la puerta al
# hablarle, y acá se pone de entrada para no gastar cuatrocientos cuadros en
# abrirla. La ruta es `23 0`: esperar y subir, y lo de esperar no es decorativo
# —lo que abre la puerta es el refresco, que corre al cuadro siguiente—.
#
# Este caso ya estuvo una vez y **estaba en verde por la razón equivocada**: la
# página no compilaba, los dos lados no hacían nada y la comparación daba cero.
# Ahora sí ejercita, y lo prueba que haya dado rojo: el cuadro 120 daba 60% por
# el cuadro que la referencia le regalaba a cada fundido.

# La cámara corrida sin el héroe: PanScreen.
#
# Es `Game_Player::StartPan` y `UpdatePan` de easyrpg: el destino se corre
# tantas celdas en una dirección y la cámara se le acerca `2 << velocidad`
# **dieciseisavos de pixel** por cuadro. La velocidad 2 son medio pixel por
# cuadro, y por eso los dos lados llevan la cámara en dieciseisavos y no en
# pixeles enteros: en pixeles ese caso no se puede contar.
#
# La página de prueba corre la cámara **y espera**, y después tiñe, como la de
# `snes-sacudir`: los cuadros del medio miran la cámara a mitad de camino, y el
# último mira que llegó y que el tinte se aplicó. Ese tinte es lo que hace
# filoso al caso: si los cuadros que espera la página salieran mal, aparecería
# en otro cuadro.
#
# El caso de la tanda es el del juego: dos celdas para arriba a velocidad 2, o
# sea 64 cuadros, que es el PanScreen de la escena de Talan en el mapa 3.
snes-pan mapa="6" pan="2 0 2 2 1" cuadros="16 32 48 64 65 66" arranque="115" nombre="pan" celda="" lluvia="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  celda="{{celda}}"
  lluvia="{{lluvia}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${celda:+--inicio $celda} \
      --pan-de-prueba {{pan}} --pagina-de-prueba 0 0 0 50 \
      ${lluvia:+--lluvia-de-prueba $lluvia} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      ${celda:+--hero-tile $celda} \
      --pan-de-prueba {{pan}} --pagina-de-prueba 0 0 0 50 \
      ${lluvia:+--lluvia-de-prueba $lluvia} \
      --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La sacudida de pantalla: ShakeScreen.
#
# Es `ShakeOnce` de easyrpg: la cámara se corre en X unos pixeles por cuadro
# siguiendo un seno, con la amplitud de la fuerza y el paso acotado por la
# velocidad, durante las décimas que diga, y la ventana de mensaje no se mueve.
# La cuenta es entera de los dos lados —ver `sacudida_siguiente` en eventos.py—
# así que puede diferir de RPG_RT en un pixel en algún cuadro, pero la ROM y la
# referencia coinciden exacto.
#
# La página de prueba sacude **y espera**, y después tiñe: los cuadros del
# medio miran la pantalla corrida, y el último mira que la sacudida terminó,
# la pantalla volvió a su lugar y el tinte se aplicó. El mapa 7 tiene la cámara
# en el borde izquierdo, así que la sacudida asoma lo que hay a la izquierda
# del mapa; el segundo caso, en el 6, tiene la cámara en el medio.
snes-sacudir mapa="7" sacudida="3 3 2 1" cuadros="3 6 9 11 13 60" arranque="115" nombre="sacudir" celda="" lluvia="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  celda="{{celda}}"
  lluvia="{{lluvia}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${celda:+--inicio $celda} \
      --sacudida-de-prueba {{sacudida}} --pagina-de-prueba 0 0 0 50 \
      ${lluvia:+--lluvia-de-prueba $lluvia} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      ${celda:+--hero-tile $celda} \
      --sacudida-de-prueba {{sacudida}} --pagina-de-prueba 0 0 0 50 \
      ${lluvia:+--lluvia-de-prueba $lluvia} \
      --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# La animación de batalla: ShowBattleAnimation, sus sonidos y sus destellos.
#
# Es la 82 del LDB —"Whole Magic Flame C"— sobre el héroe y esperando, que
# destella a los dos: la pantalla y el objetivo. La página de prueba la
# muestra **y espera**, y después tiñe: los cuadros del medio miran los
# destellos del tick 34 al 50 y el último que la espera fue la de los 56
# cuadros de la animación. Ver OP_ANIMACION en eventos.py.
snes-animacion mapa="6" animacion="82 10001 1" cuadros="1 3 35 37 43 60" arranque="115" nombre="animacion" celda="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  celda="{{celda}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${celda:+--inicio $celda} \
      --animacion-de-prueba {{animacion}} --pagina-de-prueba 0 0 0 50 \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      ${celda:+--hero-tile $celda} \
      --animacion-de-prueba {{animacion}} --pagina-de-prueba 0 0 0 50 \
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
snes-lugar mapa="6" lugar="4 21 13 12" ruta="4 2 2 2 2" celda="22 12" cuadros="14 15 20 60" arranque="115" nombre="lugar":
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

# La rama por objeto: `ConditionalBranch` de clase 4.
#
# La página de prueba le da —o no— un ítem al grupo y después pregunta si lo
# tiene; si sí, tiñe la pantalla. Los dos casos son la misma ROM con y sin el
# `ChangeItems`, así que la diferencia entre uno y otro **es** la respuesta de
# la rama: teñida contra sin teñir, que son 50 mil pixeles.
#
# Existe porque la clase 4 no la ejercita ninguna otra página que compile: las
# que preguntan por un objeto son de mapas que las pruebas no llevan, y la del
# Hover-Tram —la única de los mapas de la demo— pregunta por el Idol después de
# media hora de juego.
#
# El ítem es el 90, el Idol, que es justamente el que pregunta el Hover-Tram.
snes-rama-item mapa="6" item="90 12 0 0 100" items="90 1" celda="22 12" cuadros="2 30" arranque="115" nombre="rama-item":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  items="{{items}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} ${items:+--items-de-prueba $items} \
      --rama-item-de-prueba {{item}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} ${items:+--items-de-prueba $items} \
      --rama-item-de-prueba {{item}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Las dos ramas de actor con dos operandos: "sabe esta habilidad" —sub 4— y
# "tiene puesto este objeto" —sub 5—. La página de prueba tiñe la pantalla sólo
# si la rama se cumple, igual que `snes-rama-item`, así que la diferencia entre
# el caso que se cumple y el que no **es** la respuesta de la rama.
#
# Existe porque ninguna página del juego que compile las usa: las 36 que
# preguntan por el equipo y las 10 que preguntan por una habilidad viven en
# mapas que ninguna demo lleva —el 20, el 38, el 47, el 48 y el 151, entre
# otros—. Sin esto, `OP_SI_ACTOR` sería un camino que no ejercita nadie.
#
# `rama` son siete números: SUB ACTOR DATO R G B SAT. Los datos de referencia,
# del LDB: Kersh es el actor 11, lleva puesto el ítem 82 —Modified Blaster— y
# el 85, no lleva el 84 —que es de Core—, y a nivel 20 sabe las habilidades 131
# y 146 y no la 152.
snes-rama-actor mapa="6" rama="5 11 82 12 0 0 100" celda="22 12" cuadros="2 30" arranque="115" nombre="rama-equipo":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} \
      --rama-actor-de-prueba {{rama}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} \
      --rama-actor-de-prueba {{rama}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# `HaltAllMovement`: todas las rutas forzadas se abandonan de golpe.
#
# En el mapa 6, con el evento 3 —blanco 4— caminando cuatro celdas para abajo
# desde (22,9) y el héroe caminando cuatro para abajo desde (22,12). A los
# `parar` cuadros la página corta las dos, y recién ahí el `ProceedWithMovement`
# que va detrás la suelta y el tinte se aplica.
#
# Existe porque **el único `HaltAllMovement` del juego** está en la página del
# mapa 11 que reordena el escondite de los Lazer Teeth cuando te descubren, y
# esa página termina teletransportando: no hay dónde mirar lo que el comando
# hizo. Acá se ve solo, y es filoso por construcción: sin el comando las dos
# rutas siguen hasta el final y el tinte llega decenas de cuadros más tarde.
#
# Los cuadros: el 20 con las dos caminando, el 26 —la espera de 24 suelta la
# página en el 26, no en el 24— con las dos ya paradas y el tinte puesto, y el
# 60 y el 120 de control, donde sin el corte las rutas habrían terminado en
# otra celda.
snes-parar mapa="6" parar="24" ruta="4 2 2 2 2" heroe="2 2 2 2" celda="22 12" cuadros="20 26 60 120" arranque="115" nombre="parar-rutas":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ruta="{{ruta}}"
  heroe="{{heroe}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} ${ruta:+--ruta-de-evento $ruta} \
      ${heroe:+--ruta-de-prueba $heroe} \
      --parar-de-prueba {{parar}} --pagina-de-prueba 0 12 0 0 \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} ${ruta:+--ruta-de-evento $ruta} \
      ${heroe:+--ruta-de-prueba $heroe} \
      --parar-de-prueba {{parar}} --pagina-de-prueba 0 12 0 0 \
      --cuadros {{cuadros}} \
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
snes-timer mapa="6" timer="600 1" celda="2 10" cuadros="2 31 61 90" tinte="12 0 0 50" arranque="115" nombre="timer":
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

# Las variables de RM2k, vistas por el cronómetro: la página pone el cronómetro
# en `timer` segundos, lee esos segundos a la variable 17 —"otro 1" de
# ControlVars—, le resta `resta` y vuelve a poner el cronómetro desde la
# variable. Lo que se ve son los dígitos, que cambian cada segundo, así que un
# cuadro mal elegido se nota. Es la misma cuenta del Tram Officer del mapa 9
# —"lo que le queda al cronómetro, menos sesenta"— con números más cortos.
#
# `vars` van de a cinco con los números de RM2k —variable, operación, clase,
# a, b— y las operaciones 9 y 10 son las inventadas de la página de prueba: la
# 9 pone el cronómetro desde la variable, que en RM2k es un TimerOperation, y
# la 10 planta un evento en la celda que dicen **dos** variables, que es el
# `ChangeEventLocation` por variables —`OP_LUGAR_VAR`—: ahí `a` es el blanco y
# `b` la variable de la y, mientras que la variable del renglón es la de la x.
#
# Las dos están en esta lista y no en un flag propio por lo mismo: la página de
# prueba emite `--vars-de-prueba` **después** de `--lugar-de-prueba` y del
# cronómetro, así que es el único lugar desde donde se puede escribir una
# variable y usarla en el mismo renglón siguiente. El caso `lugar-var` de la
# tanda es exactamente eso: dos escrituras y un plantado.
#
# `ruta` es opcional y es la misma de `snes-npc` —blanco y órdenes, con el
# blanco el índice del evento más uno—. Existe para la clase 6, las coordenadas
# de un personaje: leer la celda de un evento **quieto** no distingue la celda
# viva de la que trae el mapa, y es justo esa diferencia la que importa. Con la
# ruta puesta el evento ya se movió cuando la página lee, así que el número que
# muestra el cronómetro sólo sale si los dos lados lo movieron igual.
snes-vars mapa="6" timer="60 1" vars="17 0 7 1 0 17 2 0 25 0 17 9 0 0 0" celda="2 10" cuadros="2 31 61 90" tinte="12 0 0 50" arranque="115" nombre="vars" items="" ruta="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  items="{{items}}"
  ruta="{{ruta}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --timer-de-prueba {{timer}} --vars-de-prueba {{vars}} \
      ${items:+--items-de-prueba $items} ${ruta:+--ruta-de-evento $ruta} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --timer-de-prueba {{timer}} --vars-de-prueba {{vars}} \
      ${items:+--items-de-prueba $items} ${ruta:+--ruta-de-evento $ruta} \
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
snes-saturar mapa="73" tinte="60 0 0 0 0" antes="30" despues="120" nombre="saturar" arranque="115":
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
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# El destello de **pantalla**: FlashScreen, que no es el de abajo.
#
# `snes-destello` destella a un personaje —tiñe su paleta de sprite— y esto
# destella la pantalla entera, o sea las tres paletas del mapa. Son caminos
# distintos en la ROM —`destellar_fondo` contra `destellar_sprites`— y hasta el
# 2026-09-08 el de la pantalla **no lo corría ninguna prueba**: ninguna página
# del juego que compilara lo usaba. Así sobrevivió un `lda #0` donde va
# `lda #CGRAM_BASE`, que dejaba las últimas nueve entradas del fondo sin
# destellar.
#
# La celda no es cualquiera: (22,56) del mapa 1 es donde más pixeles de esas
# nueve entradas hay en pantalla, 401 de 57344. Con el bug puesto da 387 de
# diferencia; en otras partes del mismo mapa da **cero**, que es por lo que un
# caso mal ubicado no habría probado nada.
snes-relampago mapa="1" destello="31 31 31 31 12" celda="22 56" cuadros="2 5 9" arranque="115" nombre="relampago":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --destello-de-prueba {{destello}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --destello-de-prueba {{destello}} \
      --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# `ChangeSpriteAssociation`: el CharSet de un **actor**, cambiado en caliente.
#
# Es lo que traba la persecución en auto: 102 de las 134 páginas disparables de
# los mapas 49, 52 y 54 se caen en este comando, y con él compilan 130. En el
# juego el héroe *es* el auto —los mapas de la carrera sacan a todo el grupo y
# meten a `CarRED` o `CarBLUE`, cuyo CharSet es `BLVehicles:2`— y cada choque lo
# devuelve a `Future3:0` justo antes de teletransportar al 50.
#
# Acá la página de prueba le cambia el CharSet al actor que lidera **después de
# la espera**, así que los cuadros de antes lo miran con el gráfico del LDB y
# los de después con el nuevo. El líder de estas ROMs es Kersh, `Future1:5`; se
# le pone `Future1:0`, que es el de Core.
#
# `--grafico-de-prueba` va junto y no es redundante: el `--sprite-de-prueba`
# reserva la ranura de la tabla de gráficos en **todos** los mapas —es lo que
# hace que el índice signifique lo mismo después de un salto— y el otro es el
# que le mete las doce poses al banco de sprites del mapa.
#
# Lo que este caso **no** mira, y hay que decirlo con todas las letras: que el
# cambio sobreviva al teletransporte. Lo que sí mira es la mitad que importa,
# porque es la misma función: el que decide con qué se dibuja el héroe es
# `elegir_grafico_heroe`, y lo llaman los dos —el opcode acá y `cargar_mapa`
# allá—. Que el byte sobreviva al salto y a guardar lo cobra
# `pruebas/test_sprite_actor.py`.
snes-sprite-actor mapa="6" sprite="11 Future1 0" grafico="Future1 0" celda="22 12" cuadros="10 30" tinte="20 100 100 100" arranque="115" nombre="sprite-actor":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --sprite-de-prueba {{sprite}} \
      --grafico-de-prueba {{grafico}} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --sprite-de-prueba {{sprite}} \
      --grafico-de-prueba {{grafico}} \
      --pagina-de-prueba {{tinte}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# `KeyInputProc`: esperar una tecla y guardar cuál fue.
#
# Medido sobre las 5603 páginas disparables del juego: **+30** si se acepta el
# comando entero y **+23** con lo que este port hace, que es la forma que
# **espera la tecla de acción** y nada más. Las 23 páginas son casi todas lo
# mismo: un cartel y un "apretá para seguir".
#
# **Esperar una dirección o cancelar entró el 2026-09-13**, y lo que lo tenía
# afuera era esta receta y no la ROM: la tanda sostenía una dirección desde el
# arranque con `--walk`, así que un flanco de cruceta a mitad de una escena no
# lo podía producir ningún caso, y escribir el camino sin nada que lo corriera
# es exactamente cómo sobrevivieron los tres errores del intérprete. Lo produce
# ahora `tocar`, que es `--tocar BOTON:CUADRO` de las dos mitades: el mismo
# número de cuadro que `apretar`, para cualquier botón.
#
# La forma que queda afuera está medida, y el porqué está en `KEY_INPUT_PROC`
# en eventos.py:
#
#   leer sin esperar                   +5 del juego y 3 de la persecución en
#                                      auto. La traba no es el comando sino con
#                                      qué viene: las cuatro páginas que la usan
#                                      son el volante del auto, y además de leer
#                                      el pad **le fuerzan la ruta al héroe en
#                                      todos los cuadros**. Ahí aparece una
#                                      divergencia anterior a todo esto: en la
#                                      ROM la ruta forzada manda sobre el pad y
#                                      en la referencia la caminata del arnés no
#                                      la mira. Medido: `just snes-heroe 52` da
#                                      **55,42%** caminando a la izquierda —la
#                                      única dirección que pelea contra el
#                                      empujón— y cero en las otras cuatro.
#
# Los dos casos, que son los que se pueden ver:
#
#   `tecla-espera`   la página **se para** hasta que el jugador apriete A y
#                    recién ahí tiñe. El cuadro en que la pantalla cambia de
#                    color es el cuadro en que se apretó: con `--apretar-a 40`,
#                    el 20 sale sin teñir y el 60 teñido, y entre los dos hay
#                    69,78% de pixeles de diferencia, o sea que el caso
#                    ejercita. Verificado en rojo: con la ROM sin esperar, el
#                    cuadro 20 da 69,78%.
#
#   `tecla-dir`      lo mismo pero con la **cruceta**, que es lo que le faltaba
#                    al minijuego de las piedras del mapa 11. Espera un flanco
#                    de dirección, lo toca `--tocar down:40`, y la variable se
#                    vuelca al cronómetro con la operación 9 de `vars`: así el
#                    número que leyó el comando **se ve**, que es lo único que
#                    un pixel puede decir de él. Abajo es 1 en `CheckInput`, así
#                    que el cronómetro pasa de 0:60 a 0:01 y la pantalla se tiñe.
#                    Verificado en rojo: con el `and #TECLA_DIRS` de
#                    `tecla_valor` puesto en `and #0` —o sea la ROM de antes,
#                    que sólo leía la tecla de acción— el cuadro 41 da **68,25%**
#                    de pixeles distintos.
#
#                    **La celda es (22,8) y el toque es hacia abajo a propósito,
#                    y ésa es la parte delicada.** Un toque de dirección en el
#                    mapa no lo lee sólo `KeyInputProc`: lo lee también el héroe,
#                    que gira y da un paso, y eso la referencia no lo modela —su
#                    caminata va por `--walk`, de a celdas enteras—. En (22,8)
#                    **abajo está cerrado** y el héroe ya mira para abajo, así
#                    que el flanco existe y no mueve ni gira a nadie. Con la
#                    celda de siempre, (22,12), el mismo caso da 30% a 41%: es
#                    el héroe caminando de un lado y quieto del otro, o sea la
#                    misma divergencia que tiene afuera a la forma que no espera.
#
# Qué número quedó en la variable lo dice además `pruebas/test_tecla.py`, contra
# `eventos.tecla_de`, que es la misma función que corre la referencia, y para
# las cuatro direcciones y cancelar: el cronómetro sólo muestra una por caso.
snes-tecla mapa="6" tecla="88 1 0 1 0" celda="22 12" cuadros="20 60" tinte="0 100 0 0" apretar="40" walk="none" vars="" timer="" arranque="115" nombre="tecla-espera" tocar="":
  #!/usr/bin/env bash
  set -euo pipefail
  # Los dos opcionales, como variables de bash: `${x:+...}` necesita una
  # variable de verdad, y con la sustitución de just adentro se expande a la
  # cadena vacía sin poner el flag **y sin decir nada**. Costó un caso en
  # verde que no apretaba A y por lo tanto no probaba nada.
  apretar="{{apretar}}"
  vars="{{vars}}"
  timer="{{timer}}"
  tocar="{{tocar}}"
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --tecla-de-prueba {{tecla}} \
      ${vars:+--vars-de-prueba {{vars}}} \
      ${timer:+--timer-de-prueba {{timer}}} \
      --pagina-de-prueba {{tinte}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --walk {{walk}} $([ "{{walk}}" = none ] || echo --dir {{walk}}) \
      --hero-tile {{celda}} --tecla-de-prueba {{tecla}} \
      ${vars:+--vars-de-prueba {{vars}}} \
      ${timer:+--timer-de-prueba {{timer}}} \
      ${apretar:+--apretar-a {{apretar}}} \
      ${tocar:+--tocar {{tocar}}} \
      --pagina-de-prueba {{tinte}} --cuadros {{cuadros}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk {{walk}} --cuadros $n --arranque {{arranque}} \
        ${apretar:+--apretar-a {{apretar}}} \
        ${tocar:+--tocar {{tocar}}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

snes-destello mapa="6" flash="1 31 0 0 31 24" celda="2 10" cuadros="2 12 15 23 25" tinte="12 0 0 50" arranque="115" nombre="destello":
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
#
# `mapas` son los mapas de más que la ROM tiene que llevar, y existe por el
# caso `tram`: sin el 13 adentro, el `Teleport` del Hover-Tram no compila, con
# él no compila el Hover-Tram entero, y entonces el `CallEvent` que lo llama se
# saltea. O sea que la lista de mapas decide si el caso prueba algo.
#
# **`tram` es el caso de `CallEvent`**, y es la escena entera: el héroe le
# habla al Tram Officer del mapa 9, elige la primera opción —la tanda sólo
# aprieta A—, espera el minuto, sale "It's here!" y ahí el `CallEvent` mete el
# cuerpo del `Hover-Tram`, que le cambia el gráfico al héroe con la orden 34,
# lo sube y lo teletransporta al mapa 13. Los cinco cuadros miran las tres
# partes: la elección abierta, el mensaje de que llegó, la escena del tram
# corriendo, y dos cuadros ya en el mapa 13.
#
# Verificado en rojo **de un solo lado**, que es lo que hay que hacer con una
# pieza que vive entera en el conversor: con `eventos.LLAMADA_MAX = 0` puesto
# sólo en `snes_expect.py` la referencia se saltea la llamada, la ROM la hace,
# y el cuadro 620 da 95,30% de pixeles distintos. Romper los dos lados a la vez
# no probaría nada —los dos corren el mismo bytecode—, pero de paso dijo algo:
# con la llamada salteada en los dos, ese mismo cuadro da 34,64%, o sea que la
# escena **ya divergía** cuando el comando se aceptaba sin hacerse. Queda
# anotado en ESTADO.md.
snes-hablar mapa="7" celda="3 7" switch="24" apretar="25" cuadros="20 60" arranque="115" nombre="hablar" ruta="" mapas="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ruta="{{ruta}}"
  mapas="{{mapas}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana --switch {{switch}} \
      ${ruta:+--ruta-de-evento $ruta} ${mapas:+--mapas $mapas} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --dir down --con-ventana --switch {{switch}} \
      ${ruta:+--ruta-de-evento $ruta} ${mapas:+--mapas $mapas} \
      --cuadros {{cuadros}} --apretar-a {{apretar}} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}} --apretar-a {{apretar}}
    python3 tools/snes_compare.py $pre-$n.png $pre-$n.esperado.png \
        --saltar $pre-$n.saltar.txt -o $pre-$n.comparacion.png
  done

# Una escena del juego disparada por el héroe, con los toques de A que la
# cierran.
#
# Es la forma general de lo que `snes-hablar` y `snes-pisar` hacen de a una
# cosa: el héroe arranca en una celda con una ruta forzada de la página de
# prueba —`12` es girar hacia arriba, `0` es dar un paso hacia arriba— y con
# eso dispara la página que está enfrente con A o la que pisa, y de ahí en
# adelante la escena se compara entera con `--apretar-a`, igual que la
# apertura en `snes-cinematica`. Los cuadros de los toques salen de correr la
# referencia sola y anotar dónde abre cada mensaje; hay que rehacerlos si cambia
# lo que la página tarda.
#
# Los dos casos de la tanda, del mapa 2, son lo que taro vio faltar jugando:
#
#   puerta-izq   la puerta de arriba a la izquierda, evento 2 en (4,53): el
#                héroe en (4,54) gira hacia arriba y le habla. Es la única
#                página del juego que la tanda compara con
#                `TradeEventLocations`: Manta la vuela y la puerta se cambia
#                de lugar con el evento 21.
#   pantalla     la pantalla grande, eventos 15 y 16 en (35,73) y (35,74), que
#                son de contacto y se pisan desde la derecha —la columna 35 es
#                pared arriba y abajo de ellos—: el héroe en (36,74) da un paso
#                a la izquierda y pisa el 16. Es la escena de Manta hackeando,
#                y compila porque las ocho rutas que atenúan las pantallas se
#                tiran enteras: ver RUTA_TRANSPARENCIA en eventos.py.
#   puerta-emisor la puerta del Emitter Room, evento 5 del mapa 3 en (38,68):
#                el héroe en (38,69) mira arriba y le habla. Es la que taro no
#                podía abrir hasta que `FadeOutBGM` se hizo, y es filosa por
#                construcción: el cuadro 10 la tiene cerrada y el 40 abierta, y
#                entre los dos hay 300 pixeles. Si la página no compilara, los
#                dos lados dibujarían la puerta cerrada y darían cero —es la
#                trampa de siempre—, así que lo que la sostiene es esa
#                diferencia de 300 y no el cero.
#
# Dos trampas que ya cobraron. Un cuadro elegido pocos cuadros después de que
# abre un mensaje da miles de pixeles sin que nada esté mal: la ROM tarda unos
# veinte en componer el texto y la referencia no modela eso —el 900 de
# `pantalla`, a doce cuadros de abrir, daba 19963; el 930 da cero—. Y `--dir`
# es sólo hacia dónde mira el héroe **al arrancar**: si la página lo gira con
# un `face_*`, gana la página, como en la ROM. Antes `--dir` pisaba el giro al
# dibujar y el cuadro 230 de `puerta-izq` daba 117 pixeles, todos en el héroe.
# Y con esta misma receta entra el **save point animado** del mapa 8: la celda
# (9,55) lo deja en pantalla, la ruta 0 no mueve a nadie, y los cuadros 20, 30,
# 40 y 50 caen en tres columnas distintas del ciclo —a velocidad 3 cambia cada
# diez—. Sin el `inc` de la fase en `animar_quietos` son 76 pixeles.
#
# Y **usarlo**: `savepoint-guarda` arranca **parado encima** del evento 67, en
# (9,56), y aprieta A en el tick 10. Encima y no enfrente: el save point está
# en la capa de abajo, y a un evento de esa capa se le habla desde su celda
# —`CheckEventTriggerHere`— y no desde la de al lado, que es sólo para los de
# la misma capa. De frente, desde (9,55), la página no corre y el caso pasa en
# vacío; medido con `menu_abierto`. Su página es `PlaySound`, `OpenSaveMenu`,
# `ChangeSaveAccess`. La pantalla de ranuras se abre adentro del intérprete y
# congela el reloj, así que `toques` la cierra con B por **cuadros de
# hardware** —`--toques-hardware`, que es lo único que puede caer ahí— y de ahí
# en más los dos lados van por el mismo tick. Es el caso que ESTADO.md pedía:
# el save point de verdad y no la página de prueba de `snes-guardar`. No es
# vacío: sin el B la ROM se queda en la pantalla y el arnés no llega al tick 60
# —"la ROM no llegó al tick 60"—, verificado el 2026-09-10.
#
# **Esa verificación engañaba**, y se supo el 2026-09-11: sacar el B sacaba
# también `--toques-hardware`, y eso cambiaba de camino a `snes_correr.py`.
# Con toques, el camino ignoraba `--apretar-a`, así que en la tanda el A nunca
# se apretó, el save point nunca se abrió, y el caso pasaba porque guardar no
# cambia un pixel. Lo destapó el menú de pausa: el B del cuadro 40 caía en el
# mapa y lo abría. Ahora los dos caminos aprietan A, y con el A en el tick 10
# el cuadro de hardware 30 es "Save in which slot?", en cero contra
# `titulo.py --ranuras 4 --modo 1`.
snes-escena mapa="2" celda="4 54" ruta="12" dir="up" cuadros="60" arranque="115" nombre="escena" apretar="" switch="" mapas="" toques="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  apretar="{{apretar}}"
  switch="{{switch}}"
  mapas="{{mapas}}"
  toques="{{toques}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana --ruta-de-prueba {{ruta}} \
      ${switch:+--switch $switch} ${mapas:+--mapas $mapas} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      --hero-tile {{celda}} --dir {{dir}} --con-ventana --ruta-de-prueba {{ruta}} \
      ${switch:+--switch $switch} ${mapas:+--mapas $mapas} \
      --cuadros {{cuadros}} ${apretar:+--apretar-a $apretar} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}} \
        ${apretar:+--apretar-a $apretar} \
        ${toques:+--toques-hardware $toques}
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
# **Los cuadros se corrieron 70 por cada teletransporte** el 2026-09-05, que es
# lo que ahora dura el fundido: 170, 370, 750 y 1110 son los viejos 100, 300,
# 540 y 900 más 70 por cada salto anterior —la referencia salta en el 1, en el
# 363 y en el 485 contando cuadros sin fundir—. La cinemática dura tres
# fundidos, uno por salto, porque RM2k funde también los que no cambian de mapa.
#
# Y los dos primeros son nuevos: **el 50 y el 68 caen adentro de la rampa de
# vuelta del primer fundido**, con el mapa 1 subiendo de brillo, y son lo único
# de la tanda que compara la rampa misma. Aguantan que la ROM pierda cuadros
# —acá pierde siete, los de la carga— porque el fundido se cuenta en cuadros de
# hardware y no en vueltas del lazo: el brillo del cuadro N es el mismo aunque
# el lazo haya dado menos vueltas. Lo que sí los rompería es que la ROM perdiera
# un cuadro **antes** del salto, y eso sería un rojo legítimo.
#
# Del atraso que había antes queda esto: la carga del mapa cuesta seis o siete
# cuadros que la referencia no modela, y hasta el 2026-09-05 dejaba a los dos
# lados desalineados desde el salto en adelante. Ahora esos cuadros pasan
# adentro del negro del fundido y no corren ningún reloj. El arranque tampoco es
# de esa familia: dura siempre lo mismo y el 115 alinea el cuadro N con el tick N.
#
# El 1110 es la cinemática terminada: el héroe arriba de todo, mirando arriba,
# con la pantalla teñida. El 370 fue 480 y después 300 —hasta que los eventos
# caminan a la velocidad de su página, 3 y no 4— y es antes del primer salto de
# los dos que la referencia hace adentro del mapa 1.
#
# **Con ventana** —el caso `apertura`, desde el 2026-09-05— la cinemática no
# termina ahí: el último paso pisa el evento 2, que es la escena de apertura
# entera. Sus cuadros también se corrieron 70 por salto: el 370 —era 300— es la
# cinemática a mitad de camino, teñida; en el 770 —era 560— el tinte ya se apagó
# y Core y Manta están plantados al lado del héroe; en el 830 —era 620— está
# abierto el primer mensaje de Core. Son cuatro personajes caminando en el mismo
# mapa, o sea las poses en caliente en su caso real.
#
# Y desde ahí la escena se lee **entera**, con los quince toques de A que la
# cierran: `apretar` lista los cuadros, uno por mensaje, sesenta después de que
# cada uno abre en la referencia —la ROM tarda unos cuadros en componerlo y la
# referencia no modela eso, así que el toque no puede caer antes—. Los cuadros
# salieron de correr la referencia sola y anotar dónde abre cada mensaje; hay
# que rehacerlos si cambia lo que la página tarda. El 1000 es el droide a mitad
# de un paso, después del cuarto mensaje; es el único tramo entre mensajes en
# que alguien camina —los demás son esperas— y fue el que delató que la ROM
# cerraba el mensaje un cuadro tarde: ver RETRASO_DE_PANTALLA en snes_correr.py.
# Con el fundido pasó a ser el 1210.
# El 1980 es el noveno mensaje abierto, y el 2910 es la escena terminada.
#
# Lo que **no** se compara: nada en movimiento en un cuadro en que la ROM venga
# atrasada. El atraso ya no lo produce el teletransporte —el fundido se lo
# come— sino los picos del lazo, que en esta ROM son siete cuadros repartidos
# por el camino; el toque de A los resincroniza, porque de ahí en adelante los
# dos lados cuentan desde el mismo cuadro.
snes-cinematica origen="4" destino="1" cuadros="50 68 170 370 750 1110" arranque="115" nombre="cinematica" ventana="" apretar="" switch="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ventana="{{ventana}}"
  apretar="{{apretar}}"
  # `switch` prende switches desde la página de prueba, que es cómo se pone al
  # mundo en un estado al que el juego llega más tarde. Acá hace falta porque
  # el recuerdo de CORE y MANTA lo destraba el 16, que lo prende una página de
  # un mapa que no está en la ROM del caso.
  switch="{{switch}}"
  python3 tools/snes_convert.py --grupo 10 --map-id {{origen}} \
      --mapas {{destino}} ${ventana:+--con-ventana} ${switch:+--switch $switch} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo 10 --map-id {{origen}} \
      --mapas {{destino}} ${ventana:+--con-ventana} ${switch:+--switch $switch} \
      --walk none --cuadros {{cuadros}} \
      ${apretar:+--apretar-a $apretar} \
      --saltar $pre-{}.saltar.txt -o $pre-{}.esperado.png
  for n in {{cuadros}}; do
    python3 tools/snes_correr.py --core {{nucleo}} {{snes_rom}} -o $pre-$n.png \
        --walk none --cuadros $n --arranque {{arranque}} \
        ${apretar:+--apretar-a $apretar}
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
#
# El caso `bloqueo` —desde el 2026-09-05— es lo contrario: que un evento de la
# capa del héroe **no** se pueda pisar. Nació acá, con `snes-pisar 2 "7 76" up`
# y el droide del mapa 2 quieto en (7,72); desde que el droide camina solo vive
# en `snes-escena`, con una ruta forzada de cuatro pasos hacia arriba que se
# frena contra él, porque la caminata colapsada de esta receta no puede
# describir un mapa donde alguien se mueve mientras tanto. Es `WouldCollide`:
# ver `bloqueada` en eventos.py y `celda_bloqueada` en main.s. Antes lo
# atravesaba y seguía hasta la pared, y taro lo vio jugando.
# `ruta` es opcional y sirve para lo contrario: una ruta forzada sobre el héroe
# que corre **antes** de que el pad empiece a caminar, para dejarlo en un estado
# y recién ahí caminar. Hoy la usan los dos casos de `atravesar`, con la orden
# 36 —`walk_everywhere_on`— puesta y la ruta sin un solo paso: lo que se mira es
# que la bandera que deja no siga valiendo para la caminata con el pad. Ver
# "Atravesar paredes vale mientras dura la ruta" en README.md.
snes-pisar mapa="70" celda="12 8" direccion="up" cuadros="200" arranque="115" nombre="pisar" ruta="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ruta="{{ruta}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --inicio {{celda}} --con-ventana ${ruta:+--ruta-de-prueba $ruta} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} \
      --walk {{direccion}} --hero-tile {{celda}} --con-ventana \
      ${ruta:+--ruta-de-prueba $ruta} \
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
#
# Y `relleno` son bytes muertos delante del bloque de textos, que es lo que
# corre los desplazamientos más allá de los 32 KB que mide la ventana de un
# banco de LoROM. Ahí `msg_empezar` sumaba de a dieciséis bits y perdía el
# acarreo, así que **todo cuadro de texto pasado el primer banco leía de otro
# lado**: la cabecera y los largos de renglón salían de cualquier cosa, y con un
# largo de 70 el compositor escribía fuera de `texto_buf` y se llevaba puesto
# `vq_n`, el contador de la cola de poses, que a partir de ahí subía bloques de
# 128 bytes a direcciones cualquiera de la VRAM. Eso es lo que taro veía como la
# pantalla hecha basura en Delcentric Factory. Reproducirlo de verdad pide un
# cartucho de diez mapas hablados —minutos por caso—; con el relleno lo hace uno
# de un mapa. Ver `Mensajes.__init__`.
snes-texto mapa="255" apretar="200" nombre="texto" relleno="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  relleno="{{relleno}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${relleno:+--relleno-de-mensajes $relleno} \
      --con-ventana -o {{snes_inc}}/mapdata.inc
  just snes-build
  pre={{snes_pngs}}/{{nombre}}
  python3 tools/snes_expect.py --grupo {{grupo}} --map-id {{mapa}} --walk none \
      ${relleno:+--relleno-de-mensajes $relleno} \
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
snes-anclada mapa="6" ruta="1 1 1 1 1 1 2 2 2 2 2 2" cuadros="21 23 50 130" arranque="115" nombre="anclada":
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

# La pantalla de batalla, contra `pantallas.py --batalla`.
#
# Es el hermano de `snes-guardar` y de `snes-tienda`: la pelea bloquea adentro
# del intérprete y **no cuesta ningún tick**, así que no se puede comparar
# contra `snes_expect.py` —de ese lado no hay nada dibujado, a propósito: ver
# `OP_BATALLA` en tools/eventos.py—. Lo que se compara es la pantalla, contra
# la misma función que la modela.
#
# La pelea se abre desde la página de prueba y no desde un evento del juego, y
# el porqué está medido: de las 51 peleas del juego, la única que el jugador
# alcanza hoy es la del droide del mapa 2. La de los Lazer Teeth del mapa 9
# —la tropa 86, cuatro enemigos— **no compila**, y no por la batalla: la corta
# un `MoveEvent` con la orden de ruta 9, "hacia el héroe", que la ROM no
# camina. Sin esta receta, una tropa de más de un enemigo no la ejercitaría
# nada.
#
# Los dos casos de la tanda:
#
#   batalla        la tropa 86 con el grupo de verdad: cuatro enemigos, tres
#                  actores con sus HP y el menú de órdenes. Mira los dos lazos
#                  de la pantalla —la lista de enemigos y la del grupo— y que
#                  los parámetros de cada actor salgan de `eq_parametro`.
#   batalla-blanco lo mismo con dos toques de abajo: el cursor de blanco sobre
#                  el tercer enemigo, y las órdenes en gris. Ejercita el modo
#                  que el otro no toca.
#
# **Verificado que dan rojo con un defecto puesto**: corriendo una celda el
# `BA_HP_NUM_DX` que emite el conversor —o sea los HP en la columna de al
# lado, y **sólo del lado de la ROM**, que es lo que hace que la comparación
# mida algo— los dos dan 556 pixeles. Un caso que no falla con algo roto no
# prueba nada.
snes-batalla tropa="86" grupo="11 12 13" espera="20" cuadros="200" toques="" nombre="batalla" fondo="ABLBackdropSJ03" mapas="" items="" ref="--modo 1 --blanco 2":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  toques="{{toques}}"
  mapas="{{mapas}}"
  items="{{items}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id 6 --con-ventana \
      ${mapas:+--mapas $mapas} ${items:+--items-de-prueba $items} \
      --pagina-de-prueba {{espera}} 0 0 0 --batalla-de-prueba {{tropa}} \
      --fondo-de-prueba "{{fondo}}" \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
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

# La pelea **peleada hasta el final**, y el mapa comparado al volver.
#
# Es lo que `snes-batalla` no puede mirar: aquélla abre la pantalla de la pelea
# y la compara contra `pantallas.py`, pero nunca sale de ahí. Lo que llegó a la
# SD de taro el 2026-09-13 estaba justo del otro lado: la escena de la batalla
# sube 32 KB de VRAM —las palabras $4000 a $8000— y `volver_al_mapa` reponía
# nada más que el banco de tiles de BG1 y el de la capa de encima, así que el
# mapa volvía con los dos tilemaps, los tiles de la ventana y el banco de
# sprites hechos basura. Ver `volver_de_batalla` en main.s.
#
# Cómo se compara, que es lo que lo hace barato: **la pelea no cuesta ningún
# tick**. `batalla_correr` corre su propio lazo y `vueltas` no avanza mientras
# dura, y la referencia sale del `OP_BATALLA` por la rama de victoria en el
# mismo tick en que entró. O sea que del otro lado no hay nada que modelar: el
# cuadro N es el mapa quieto, igual que si no hubiera habido pelea. Que la ROM
# dibuje eso mismo **es** la prueba.
#
# Los toques son los A que pelean: uno cada nueve cuadros de hardware desde que
# la pelea abre, en cuadros de hardware porque adentro de la pelea no hay ticks.
# Con el azar clavado en `BATALLA_SEMILLA` la pelea es la misma todas las veces.
# Si la ROM no saliera, `snes_correr.py` corta con "la ROM no llegó al tick".
#
# Los dos casos de la tanda miran los **dos repartos de VRAM**, que es donde la
# pelea rompe cosas distintas:
#
#   vuelta          sin ventana, o sea LAYOUT_ANCHO: los sprites viven en $4000
#                   y la escena se los lleva enteros. Es el único caso que
#                   cobra el `load_sprite` de la vuelta.
#   vuelta-ventana  con ventana, o sea LAYOUT_VENTANA: los sprites arrancan en
#                   0 y lo que se lleva la escena son los tiles de la ventana
#                   en $6800 y los dos tilemaps.
#
# **Verificado que dan rojo** sacando `volver_de_batalla` y dejando el
# `volver_al_mapa` de antes: 74,30% de los pixeles el primero y 77,49% el
# segundo, en los dos cuadros de cada uno.
snes-vuelta mapa="6" tropa="82" fondo="SJBackdropABL04" espera="20" cuadros="30 100" ventana="" arranque="115" nombre="vuelta":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  ventana="{{ventana}}"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      ${ventana:+--con-ventana} \
      --pagina-de-prueba {{espera}} --batalla-de-prueba {{tropa}} \
      --fondo-de-prueba "{{fondo}}" -o {{snes_inc}}/mapdata.inc
  just snes-build
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
# El caso es filoso por construcción, que es lo que le faltaba a la primera
# idea —comparar el mapa unos cuadros antes—: si la ROM no dispara el encuentro
# en el paso que dice la referencia, lo que hay en pantalla es el mapa y no la
# pantalla de batalla, y la comparación no da 0,6% sino 90%. Y si lo dispara
# con **otra tropa**, el nombre y los HP del enemigo son otros. Está verificado
# en rojo de las dos maneras: ver ESTADO.md.
#
# Por qué el mapa 21 y por qué caminando para arriba: es Rat Tracks B1, uno de
# los tres lugares donde taro reportó que no había encuentros, y desde donde el
# héroe arranca es la única dirección con lugar para caminar —quince celdas—.
# Su área es la 25, "Rat Tracks B1 Monsters", que lo tapa entero con cinco
# tropas.
#
# **`--encuentros-de-prueba 8` no es hacer trampa, es acortar el caso**: con
# los setenta pasos que el árbol le da a este mapa, el encuentro sale recién en
# el paso ~130 y el caso duraría mil cuadros de emulador. Con ocho sale en el
# paso 8, y lo que se ejercita es exactamente lo mismo: la tabla de `pmod`, el
# acumulado, el azar y la elección de tropa. Los dos lados toman el mismo
# número por el mismo flag.
snes-encuentro mapa="21" pasos="8" walk="up" grupo="11 12 13" cuadros="200" nombre="encuentro":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --con-ventana --encuentros-de-prueba {{pasos}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
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

# Cuánto destraba cada comando de evento que todavía no hacemos.
#
# Es lo que decide por dónde seguir, y existe porque el número que este repo
# venía usando medía otra cosa: la tabla de "Lo que falta" del README cuenta qué
# comando corta **primero** cada página, y una página cortada por un cuadro de
# texto puede estar cortada además por otras cuatro cosas. Lo que hay que contar
# es cuántas páginas pasan a compilar enteras, que es lo que hace esto.
#
# Se corre después de cada feature nueva: el orden cambia a medida que las
# páginas se van destrabando entre ellas.
#
# Al final imprime aparte **qué órdenes de `MoveCommand` faltan**, sobre todas
# las páginas del juego. Es la pregunta de adentro de `MoveEvent`, y está acá
# porque la respuesta cambió de signo en un día: el 2026-09-12 faltaban diez
# órdenes y la 9 sola valía +33 páginas; hecha ésa, las nueve que quedan valen
# +0 y una sola aparece —la 10, una vez, en una página que ni siquiera se
# dispara—. Un número viejo de esta pregunta mandó a hacer trabajo que no
# existía; ahora se vuelve a sacar en un segundo.
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
# errores se volvieron a meter de a uno y los tres dan rojo.
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
snes-ruta mapa="6" ruta="1 1 1 1 23 23 2 2 2 2 23 23 0 0 0 0" cuadros="18 60 120 400" arranque="115" nombre="ruta" inicio="" frecuencia="8":
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
snes-ruta-pisa mapa="70" celda="12 8" ruta="0 0 0 0" pagina="0" cuadros="16 24 200" arranque="115" nombre="ruta-pisa":
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
        --walk none --cuadros $n
    python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}-$n.png \
        {{snes_pngs}}/esperado-{{nombre}}-$n.png \
        --saltar {{snes_pngs}}/saltar-{{nombre}}-$n.txt \
        -o {{snes_pngs}}/comparacion-{{nombre}}-$n.png
  done

# La pantalla de ranuras abierta por el save point —`OpenSaveMenu`— y el mapa
# de vuelta al cerrarla. La página de prueba es la de `snes-espera` con
# `--guardar-de-prueba`: espera, abre la pantalla, y después tiñe.
#
# Cuatro cuadros:
#
#   guardar             la pantalla como se abre, contra `titulo.py --modo 1`:
#                       "Save in which slot?" y las cuatro ranuras vacías.
#   guardar-2           el cursor dos ranuras más abajo: ejercita los DMA de
#                       las dos filas desde adentro del intérprete, que es lo
#                       que el 2026-09-10 "no se movía".
#   guardar-vuelve      B cancela, y el cuadro `vuelve` del mapa contra la
#                       referencia del mismo tick. Es el que cobra la
#                       reposición de la VRAM y CGRAM —`volver_al_mapa`— y el
#                       tinte que la página aplica justo después. Compara en
#                       ticks: el reloj del juego no corre mientras la pantalla
#                       se ve, así que después de cerrarla los dos lados van
#                       por el mismo cuadro, como con `OpenSaveMenu` en RM2k.
#   guardar-elige       lo mismo eligiendo la ranura 1 con A: la partida se
#                       guarda y el mapa vuelve igual. Lo que quedó en la SRAM
#                       lo mira `pruebas/test_guardar.py`, no esto.
#
# Los dos primeros van con `--sin-contador`, como `snes-titulo`: ahí no hay
# tick que esperar. Los otros dos aprietan con `--toques-hardware`, que cuenta
# cuadros de hardware desde el arranque, porque un toque por tick no puede caer
# adentro de una pantalla que no cuenta ticks. La pantalla se abre en el cuadro
# `espera`, y los toques van diez y pico después para no depender del cuadro
# exacto.
#
# El mapa vuelve **dos cuadros negros después** de cerrar: reponer el banco de
# tiles son 30 KB de DMA y no entran en un vblank, así que ese tick dura dos
# cuadros —`cuadros_perdidos` lo cuenta— y la pantalla se enciende en el que
# sigue. Por eso `vuelve` es 122 y no 121: el 121 sale negro. En RM2k el cierre
# de la escena lleva una transición, así que no desentona.
snes-guardar mapa="73" espera="120" vuelve="122 200" nombre="guardar":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --pagina-de-prueba {{espera}} 0 0 50 --guardar-de-prueba \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
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
# Las dos primeras con `--sin-contador`, como `snes-guardar`: ahí no hay tick
# que esperar. Los toques van en cuadros de hardware. Lo que la tanda no puede
# —un grupo y oro puestos, guardar desde el menú, los permisos, B a mitad de
# un paso— lo mira `pruebas/test_menu.py`.
snes-menu mapa="73" abre="40" vuelve="50 120" nombre="menu":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
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
snes-items mapa="73" abre="40" vuelve="60 120" nombre="items":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  dar="81 1 1 13 17 1"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --items-de-prueba $dar -o {{snes_inc}}/mapdata.inc
  just snes-build
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
snes-equipo mapa="73" abre="40" vuelve="60 120" nombre="equipo":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  dar="17 1 20 1"
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --items-de-prueba $dar -o {{snes_inc}}/mapdata.inc
  just snes-build
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
#
# Y por lo mismo es donde entra **la animación del ChipSet**: un avance de N px
# es el tick N/2 + 1, así que se puede pedir el cuadro exacto en que el agua o
# los tiles animados cambian de dibujo. La tanda lleva dos casos así, y los dos
# están medidos con la fase rota a propósito, que es lo único que prueba que
# miran algo:
#
#   snes-caminando 5 left "40 46 48 50"   el agua, que cambia en el tick 24 (46
#                                         px): 18349 pixeles, 32% de la pantalla
#   snes-caminando 3 down "54 56 58 60"   los tiles animados, que cambian en el
#                                         tick 30 (58 px): 211 pixeles
#
# El mapa 3 no aporta agua aunque tenga 4899 celdas de autotile de agua: en
# `Future1` los tres dibujos de esa zona son iguales, así que su corrida sale
# vacía. Y el mapa 5 no aporta tiles animados porque no tiene ninguno. Hacen
# falta los dos casos.
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
# Son la otra mitad de la red y no un reemplazo de `snes-hitos`: ésta compara
# pixeles contra la referencia de Python y cobra los errores de PPU —una paleta
# mal repartida, una prioridad de OAM—; aquélla cobra los de lógica sin
# depender de que la referencia esté bien, que es donde la comparación de
# pixeles se queda ciega. El recuerdo de CORE y MANTA que no arrancaba daba
# verde en la tanda entera, porque los dos lados se equivocaban igual.
#
# Se apoyan en la tabla de símbolos que deja `w65.py --simbolos`, así que
# ninguna dirección de RAM está escrita a mano: renombrar una variable en
# `main.s` hace fallar la prueba diciendo qué símbolo falta.
pruebas *args:
  python3 -m pytest pruebas {{args}}


# Los mismos casos, uno por proceso y cada uno en su propia corrida aislada.
# En serie son unos dos minutos y medio y repartida no llega al minuto; lo que
# domina ya no es el emulador sino convertir los mapas en Python.
#
# Un rojo acá se puede creer sin más. Cuando la tanda esperaba al reloj no: el
# emulador corría en tiempo real y una máquina sobresuscrita emulaba menos
# cuadros en los mismos segundos, el héroe quedaba corto de la pared y la
# comparación se disparaba sin que nada estuviera roto. Ahora N cuadros son N
# cuadros, con la carga que sea.
# La tanda sobre una **foto** del árbol, para poder seguir editando mientras
# corre.
#
# El problema que resuelve: cada receta recompila desde `rom/src/main.s`, así
# que tocar un fuente a mitad de una tanda mezcla dos versiones y el resultado
# no dice nada. La regla escrita —"mientras corre una tanda no se toca ningún
# fuente"— funciona hasta que alguien se olvida, y eso ya costó dos tandas.
#
# `git stash create` deja un commit colgado con el árbol sucio **sin tocar el
# índice ni el stash**, y el worktree sale de ahí: la foto incluye lo que no
# está commiteado, que es justo lo que uno quiere probar. Medido: 0,034 s y
# 19 MB. Al terminar imprime el hash de la foto, que es lo que permite después
# ver qué se probó y qué se agregó encima —`git diff <foto>`—.
#
# Dos cosas para tener presentes:
#
# * **Los archivos sin trackear no entran en la foto.** `git stash create` sólo
#   toma lo modificado. Un archivo nuevo que todavía no se hizo `git add` no
#   viaja, así que la receta avisa si ve alguno.
# * **Dos tandas a la vez se pelean por CPU.** Esto sirve para seguir editando,
#   no para que la tanda termine antes.
snes-hitos-foto trabajos="4" donde="":
  #!/usr/bin/env bash
  set -uo pipefail
  # **Cada corrida en su propio directorio.** El default era uno fijo, y la
  # receta hace `git worktree remove --force` al empezar: dos tandas a la vez
  # —dos agentes, o un agente y yo— se arrancaban el árbol entre sí y el
  # resumen salía **verde sin haber medido nada**, que es la peor forma de
  # fallar que tiene esto; y a veces se ve al revés, como una corrida que
  # empieza bien y de golpe dice `getcwd: cannot access parent directories`
  # con casos en rojo que no lo están. Pasó dos veces el 2026-09-13, con dos
  # agentes trabajando en paralelo. El PID alcanza para que no se pisen, y
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
  ( cd "$donde" && just snes-hitos-paralelo {{trabajos}} )
  estado=$?
  git worktree remove --force "$donde" 2>/dev/null || true
  rmdir "$(dirname "$donde")" 2>/dev/null || true
  echo "la foto era $foto; para ver qué se agregó encima: git diff $foto"
  exit $estado

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
      --plan {{snes_pngs}}/plan-{{mapa}}.txt --margen 0
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

# La pantalla de título: la imagen del LDB con su tema, y de ahí a la partida.
#
# Corre con `--sin-contador` y no como el resto: en la pantalla de título
# `vueltas` no avanza —es el reloj del juego, y el título no es el juego— así
# que el arnés no tiene a qué cuadro esperar y cuenta cuadros de hardware.
#
# El `--arranque 150` no es un número medido sino un piso: BOOT_CUADROS son 112
# y el título se dibuja en la vuelta siguiente, así que cualquier cosa desde
# ahí muestra lo mismo. La pantalla está quieta hasta que alguien apriete algo.
snes-titulo nombre="titulo" mapa="4" mapas="1 2 3 5 6 7 8":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}} {{snes_dir}}/sintitulo
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mapas {{mapas}} --con-ventana --con-titulo \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
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
  # la referencia por los otros 96 casos, y porque la pregunta es justamente
  # "¿son la misma?".
  #
  # **Lo que este caso no cubre**, y hay que decirlo: el defecto que taro
  # encontró en Mesen el 2026-09-10 —el PPU quedando con los registros del
  # título— **no lo ve**. Verificado sacando el `jsr ppu_init` que lo arregla:
  # snes9x sigue dando cero. Lo que sí cobra es el reparto de la VRAM.
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} \
      --mapas {{mapas}} --con-ventana \
      -o {{snes_dir}}/sintitulo/mapdata.inc
  python3 tools/w65.py rom/src/main.s -I {{snes_dir}}/sintitulo \
      -o {{snes_dir}}/sintitulo/sintitulo.sfc \
      --simbolos {{snes_dir}}/sintitulo/sintitulo.sfc.sym
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
# sin música y sin cámara. La referencia hace lo mismo, así que no es un bug de
# la ROM: es una demo mal armada. Pasó el 2026-09-10, armándolas a mano con el
# `grupo` del justfile; por eso ahora son una receta y el número está escrito
# acá. `snes-cinematica` usa el 10 por la misma razón.
#
# Con cronómetro, para hacerle lugar al rojo de los dígitos; ver "Lashe City" en
# ESTADO.md. Desde el 2026-09-10 llevan también Lashe City Interiors (10) y
# Lashe City 33,36 (9), que taro pidió: con ellos compilan los cinco
# teletransportes que salen del 8 hacia ahí y los que vuelven. El 9 trae a
# Chara2:0 cuantizado distinto que el 8 —allá con paleta prestada— y por eso
# el banco de poses dejó de ser uno por ROM y pasó a ser uno por cuantización.
#
# Desde el 2026-09-12 lleva **el subárbol entero de "Lashe City" que entra**: el
# camino a la fábrica (16, 17), el auditorio y el Director (18, 19), Sector 30 y
# los Rat Tracks (20, 21, 23, 26), Sector 27 con sus dos negocios y el galpón
# (28, 29, 30, 32), la fuga del 27 y el auto (33, 34, 36), y de paso la misión
# de los Neon Viper (11, 12, 13, 14). Son 28 mapas contra los 10 de antes.
#
# **Lo que quedó afuera, y por qué**, porque acá es donde se va a mirar:
#
#   49 52 54 51 50 53 64   la persecución en auto. 42 de las 44 páginas
#                          automáticas de cada mapa de la carrera no compilan:
#                          leen la posición del auto con un `ControlVars` de
#                          clase 6 —coordenadas de un personaje—, que la ROM no
#                          hace, y el 49 además tiene un `KeyInputProc`. Sin
#                          eso el auto no dobla y el tráfico no aparece. De
#                          paso: los tres mapas de 500x40 son 186 KB y el
#                          cartucho se pasaba de los 2 MB por 88 KB.
#   37 38 47 48            los sectores con auto, que son a dónde lleva la
#                          elección del mapa 36. El **38 no entra en ningún
#                          reparto de VRAM**: 476 tiles de fondo y 347 de
#                          sprite, y los 64 KB no alcanzan para los dos más la
#                          ventana. Y la elección del 36 es una sola página:
#                          o compilan los cuatro destinos o no compila ninguno.
snes-demo nombre="demo-ciudad" titulo="":
  #!/usr/bin/env bash
  set -euo pipefail
  titulo="{{titulo}}"
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 10 --map-id 4 \
      --mapas 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 29 30 \
              32 33 34 36 \
      --con-ventana --con-timer ${titulo:+--con-titulo} \
      -o rom/build/{{nombre}}/mapdata.inc
  python3 tools/w65.py rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# La persecución en auto, que no entra en `demo-ciudad` y no hace falta que
# entre: **arranca en el mapa 49**, que es donde empieza la carrera, así que se
# juega desde el primer cuadro sin tener que recorrer Lashe City.
#
# Los siete mapas son los de la escena: el 49, el 52 y el 54 son las tres
# vueltas —500x40 celdas cada una—, el 50 es la sala de choque con el "vamos de
# nuevo", el 51 el puente levantado, y el 53 el final.
#
# **Con `--grupo 14`, Talan, que es con quien el juego llega hasta acá.** Al
# entrar al 49, `RaceController1` saca del grupo a los siete actores que pueden
# estar ahí —10, 14, 15, 17, 18, 19 y 20— y mete a `CarRED` o a `CarBLUE` según
# el switch que él mismo prende, así que el héroe **es el auto**. Con el grupo
# de pruebas puesto, Kersh quedaría adentro —no está en esa lista— y el gráfico
# saldría mal.
#
# Hasta el 2026-09-13 esto decía `--grupo 10`, el grupo inicial de la base, y
# el precio era un síntoma que taro reportó jugando: **el auto tardaba un
# segundo en aparecer y hasta ahí el héroe se dibujaba sin gráfico**. El actor
# 10 es `DummyHero`, cuyo sprite es una celda vacía a propósito, y lo que pasa
# en el medio está medido: el `PanScreen` de `RaceController1` es de 7 celdas a
# velocidad 4, o sea **56 cuadros** —`2 << 4` por cuadro sobre `7 * 256`— y
# **espera**, así que los `ChangePartyMembers` que meten al auto corren recién
# después. Medido en snes9x: el auto aparece en el cuadro 60. Con Talan adentro
# el héroe se ve desde el primero, que es lo que se ve en el original.
#
# **`--inicio 1 26` es la celda por la que se entra en el juego**, y no es
# cosmético. Sin ella el conversor planta al héroe en el tile abierto más
# cercano al centro, que en este mapa cae en la fila 20, y **en la fila 20 no
# hay ni un obstáculo**: los 40 autos del tráfico están entre las filas 23 y 28
# —medido evento por evento— y la meta del nivel, los cinco eventos que saltan
# al mapa 52, entre la 23 y la 27. O sea que el auto podía cruzar las 500
# celdas del mapa sin chocar con nada y sin llegar a ninguna parte. La celda
# sale del `Teleport [49, 1, 26]` del evento 3 del mapa 36, que es por donde el
# juego entra.
#
# Y de paso, el otro número que explica lo que taro no vio: **el primer
# obstáculo está en la columna 70**, y una pantalla son 16 celdas. En las dos
# primeras pantallas no hay ninguno tampoco en el original.
#
# **`--switch 171` es lo que la hace arrancar**, y hay que saber por qué. El
# evento 1 del mapa 49 tiene dos páginas automáticas: la 0 pide el switch 171 y
# es la que arma el auto, y la 1 pide el 170. Con los dos apagados **ninguna es
# la activa** y el evento no hace nada, así que el héroe se queda siendo
# `DummyHero`, cuyo sprite es una celda vacía a propósito: pantalla sin auto.
#
# Quien prende el 171 en el juego es `RaceControllerZERO`, la intro de Talan
# con el cartel de los controles. Esa página **compila desde el 2026-09-13**:
# termina en un `KeyInputProc` que espera cualquier tecla, que era una de las
# formas que este port no hacía y que entró con el minijuego de las piedras
# —ver `KEY_INPUT_PROC` en eventos.py—. El switch sigue puesto a mano igual,
# porque nadie volvió a mirar esa escena desde entonces: sacarlo es una prueba
# a mano de toda la intro, no un cambio de un argumento.
#
# **Y la carrera no corre sola**, que es lo primero que se nota jugando: el
# héroe camina libre y a la velocidad que le dejó `RaceController1`. Quien la
# corre es `RaceController2`, la única página paralela del 49 que no compila,
# y lo que la corta es el `KeyInputProc` **sin espera**. El porqué de que ese
# comando siga sin aceptarse —y cuánto falta para aceptarlo, con el número
# medido hoy— está en `KEY_INPUT_PROC` en eventos.py. De las 46 páginas del
# mapa 49 compilan **45** desde el 2026-09-13: la única que no es ésa.
#
# Aparte de `snes-demo` porque el mapa inicial es otro y porque no comparte un
# solo mapa con ella: juntarlas sería un `if` en el medio de una receta que ya
# tiene la lista escrita a mano.
snes-demo-carrera nombre="demo-carrera":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 49 \
      --mapas 50 51 52 53 54 \
      --con-ventana --con-timer --switch 171 --inicio 1 26 \
      -o rom/build/{{nombre}}/mapdata.inc
  python3 tools/w65.py rom/src/main.s -I rom/build/{{nombre}} \
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
# en `snes-demo-carrera`. Con el grupo de pruebas el héroe sería Kersh.
#
# Aparte de `snes-demo` por lo mismo que la carrera: el mapa inicial es otro y
# la lista de mapas no se parece en nada.
snes-demo-piedras nombre="demo-piedras":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 11 \
      --con-ventana --con-timer --inicio 26 52 \
      -o rom/build/{{nombre}}/mapdata.inc
  python3 tools/w65.py rom/src/main.s -I rom/build/{{nombre}} \
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
snes-demo-cofres nombre="demo-cofres":
  mkdir -p rom/build/{{nombre}}
  python3 tools/snes_convert.py --grupo 14 --map-id 20 --mapas 21 26 \
      --con-ventana --con-timer --inicio 80 19 --ruta-de-prueba 36 \
      -o rom/build/{{nombre}}/mapdata.inc
  python3 tools/w65.py rom/src/main.s -I rom/build/{{nombre}} \
      -o rom/build/{{nombre}}/{{nombre}}.sfc \
      --simbolos rom/build/{{nombre}}/{{nombre}}.sfc.sym

# Las dos de una vez.
snes-demos:
  just snes-demo demo-ciudad
  just snes-demo demo-titulo 1

# Las pistas de MSU-1 al lado de una ROM ya armada: el `.msu` que lo enciende
# —puede estar vacío— y un `.pcm` por tema de `PISTAS_MSU`. No va adentro de
# `snes-demo` porque no hace falta para jugar: sin estos archivos la ROM suena
# como siempre, por el SPC700. Y porque es cara —renderiza el MIDI con
# fluidsynth y normaliza en Python— y pesa: son 10,6 MB por minuto de música.
#
# En la tarjeta del FX Pak los tres van en el mismo directorio y con el mismo
# nombre base que la ROM: renombrar el `.sfc` obliga a renombrar los otros, o
# el MSU-1 no se enciende.
snes-msu nombre="demo-ciudad":
  python3 tools/msu.py rom/build/{{nombre}}/{{nombre}}.sfc

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

# Cada tema del cartucho, escuchado desde el arranque.
#
# El cartucho lleva varios desde el 2026-09-06 y todos comparten el banco de
# muestras, así que lo que hay que verificar de cada uno no es "suena algo"
# sino que **sus notas salgan del banco compartido**: los índices de muestra
# que su stream escribe son los del banco de todos, no los de uno propio.
#
# `--tema-de-arranque` está para esto: `snes-check` escucha desde el arranque,
# y los mapas de las primeras secuencias no traen música propia —la prende un
# `PlayBGM`—, así que sin el flag la ROM sale callada y no hay qué medir. El
# flag no toca el bytecode: es el mismo stream, prendido antes.
snes-bgm tema="escape_newyork" mapa="4" mapas="1 2 3" segundos="40":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --grupo {{grupo}} --map-id {{mapa}} --con-ventana \
      --mapas {{mapas}} --tema-de-arranque {{tema}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  rom/record.sh {{snes_rom}} {{snes_pngs}}/bgm-{{tema}}.wav {{segundos}}
  python3 tools/snes_check.py {{snes_pngs}}/bgm-{{tema}}.wav \
      --map-id {{mapa}} --tema {{tema}}

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
