# Renderiza un mapa a render/MapXXXX.png. Sin dependencias que instalar:
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

# --- Mega Drive ------------------------------------------------------------
# El cross-compiler de m68k y el emulador viven en un contenedor: no se instala
# nada en el sistema. La imagen base va pinneada por digest.

# edlink es de krikzz y vive en el repo de recursos del EverDrive; no lo
# copiamos a git, se toma de ahí al armar la imagen.
edlink := "/home/taro/git/gaming/mega-ed-pub/edlink.exe"

md-image:
  cp {{edlink}} md/edlink.exe
  podman build -t abl-md md

# ChipSet + mapa -> tiles de 8x8 a 4bpp, paletas de 9 bits y tilemap, más el
# render de Python contra el que se compara después.
md-convert map_id="8":
  mkdir -p md/shots
  python3 tools/md_convert.py --map-id {{map_id}} -o md/src/mapdata \
      --reference md/shots/reference.png
  python3 tools/md_music.py --map-id {{map_id}} -o md/src/musicdata
  python3 tools/render_map.py --map-id {{map_id}} --no-events -o md/shots/python.png

md-build:
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/md abl-md make

# Corre la ROM sin pantalla y saca un screenshot. Las teclas son la cruceta del
# control 1: se mantienen apretadas para mover la cámara antes de capturar.
md-shot region="E" nombre="origen" teclas="" segundos="4":
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/screenshot.sh /abl/md/build/abl.bin \
      /abl/md/shots/{{region}}-{{nombre}}.png 3 {{region}} "{{teclas}}" {{segundos}}

# Simula la caminata con las mismas reglas que la ROM para saber en qué tile
# tuvo que frenar, y de ahí saca la cámara y el rectángulo del sprite.
md-compare region="E" nombre="parado" map_id="8" walk="none":
  python3 tools/md_compare.py md/shots/{{region}}-{{nombre}}.png \
      md/shots/reference.png md/shots/python.png \
      --map-id {{map_id}} --walk {{walk}} \
      -o md/shots/comparacion-{{region}}-{{nombre}}.png

# Todo el camino. El personaje arranca en el tile abierto más cercano al centro
# y se lo camina en cada dirección sin soltar, hasta que choca. Dónde frena se
# calcula en Python con las mismas reglas de colisión: si la ROM y la
# simulación no coinciden, queda en otro tile y la comparación falla. O sea que
# esto verifica la colisión, no sólo el render.
#
# `segundos` es cuánto se mantiene la cruceta: tiene que alcanzar para cruzar
# el mapa a 2 px por cuadro. Para mapas grandes, subilo.
md map_id="8" segundos="12":
  just md-convert {{map_id}}
  just md-build
  just md-shot E parado
  just md-compare E parado {{map_id}} none
  just md-shot E derecha "Right" {{segundos}}
  just md-compare E derecha {{map_id}} right
  just md-shot E izquierda "Left" {{segundos}}
  just md-compare E izquierda {{map_id}} left
  just md-shot E arriba "Up" {{segundos}}
  just md-compare E arriba {{map_id}} up
  just md-shot E abajo "Down" {{segundos}}
  just md-compare E abajo {{map_id}} down
  just md-shot U parado
  just md-compare U parado {{map_id}} none
  just md-shot U derecha "Right" {{segundos}}
  just md-compare U derecha {{map_id}} right

# --- EverDrive por USB -----------------------------------------------------
# El cartucho aparece como un puerto serie. Si no es /dev/ttyACM0, pasale otro.
# Hace falta permiso sobre el dispositivo: normalmente, estar en el grupo
# `uucp` o `dialout`.

# Sube la ROM al EverDrive y la arranca. Sin sacar la SD.
md-upload dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} --mount=type=bind,src=.,dst=/abl \
      abl-md mono /opt/edlink/edlink.exe run --file /abl/md/build/abl.bin

# Escucha lo que la ROM escriba en el FIFO del cartucho: un printf por USB.
md-usb dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe usbrd --len -1 --tout -1 --print

# Datos del cartucho, para verificar que el USB conecta.
md-devinfo dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe devinf

# Graba lo que la ROM le escribe al PSG y lo compara con lo que pidió el
# conversor de música. Si coinciden, suena exactamente lo que se generó.
md-music map_id="8" segundos="12":
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/vgmlog.sh /abl/md/build/abl.bin /abl/md/shots/musica.vgm {{segundos}}
  python3 tools/md_music_check.py md/shots/musica.vgm --map-id {{map_id}}

# La ROM en una ventana de verdad, para moverla con las flechas.
#
# Esta corre en el host, no en un contenedor, y es a propósito. Para abrir una
# ventana había que compartirle /tmp/.X11-unix, y eso le da al contenedor un
# cliente X con acceso al servidor entero: puede leer el teclado de todas las
# ventanas e inyectar eventos en otras. Con ese agujero abierto el contenedor ya
# no aislaba nada, así que no valía lo que costaba.
#
# El emulador es mednafen, de pacman. blastem sería más fiel para Mega Drive,
# pero el único que hay es un binario precompilado bajado de la web en 2019, y
# eso no se corre en el host. Sigue usándose para verificar (md-shot, md-music),
# donde va adentro del contenedor, sin red y sin sockets.
#
# -sound.driver sdl es obligatorio: el driver ALSA propio de mednafen abre el
# dispositivo crudo hw:0, que PipeWire tiene tomado en exclusiva, y falla con
# "Device or resource busy". Por SDL sale por PipeWire y convive con todo.
md-play region="overseas_pal":
  mednafen -command.exit "keyboard 0x0 20+ctrl" -force_module md -md.region {{region}} -sound.driver sdl \
      md/build/abl.bin

# Lo mismo pero mudo.
md-play-mudo region="overseas_pal":
  mednafen -command.exit "keyboard 0x0 20+ctrl" -force_module md -md.region {{region}} -sound 0 md/build/abl.bin

# --- Super Nintendo --------------------------------------------------------
# Rama aparte, para ver si la SNES se acerca más al original que la Mega Drive.
# No toca nada del port a Mega Drive.
#
# Ya no hace falta ningún contenedor acá. El ensamblador de 65816 es nuestro
# (tools/w65.py) y el emulador es mednafen, que está en pacman. Todo el
# toolchain son dos cosas: python y mednafen.
#
# El contenedor sigue existiendo para una sola cosa, snes-validar, que compara
# w65.py contra ca65. No se necesita para compilar.

# Una corrida aislada. `CORRIDA=algo just snes-hitos` deja el mapdata, la ROM y
# las capturas adentro de snes/build/algo/ y no toca nada de lo de siempre; sin
# CORRIDA, todo queda exactamente donde estaba, para que `mednafen
# snes/build/abl.sfc` y las rutas escritas en el LEEME sigan valiendo.
#
# Existe por dos cosas que hasta ahora hacían imposible compilar mientras algo
# corría: snes/src/mapdata.inc es estado global —lo pisa cualquier
# snes-convert— y la ROM tenía un solo nombre posible. La ROM además se llama
# como la corrida porque screenshot.sh busca la ventana del emulador por el
# basename del archivo: dos ROMs llamadas las dos `abl` no se distinguen.
# Con qué se corre la ROM. `libretro` maneja el core desde Python cuadro por
# cuadro —sin X, sin reloj, sin sleeps— y es lo verificado bit-exacto contra el
# otro. `MOTOR=mednafen` vuelve al camino viejo, el de screenshot.sh; existe
# para poder correr la misma tanda de las dos formas y compararlas, que es como
# se está haciendo la migración.
motor    := env_var_or_default("MOTOR", "libretro")
corrida  := env_var_or_default("CORRIDA", "")
snes_dir := if corrida == "" { "snes/build" } else { "snes/build" / corrida }
snes_rom := snes_dir / (if corrida == "" { "abl.sfc" } else { corrida + ".sfc" })
snes_inc := if corrida == "" { "snes/src" } else { snes_dir }
snes_pngs := if corrida == "" { "snes/shots" } else { snes_dir / "shots" }

# ChipSet + mapa -> tiles de 8x8 a 8bpp, paleta de 15 bits y tilemap, más el
# render de Python contra el que se compara después.
snes-convert mapa="7":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --map-id {{mapa}} -o {{snes_inc}}/mapdata.inc \
      --reference {{snes_pngs}}/python.png

snes-build:
  python3 tools/w65.py snes/src/main.s -I {{snes_inc}} -o {{snes_rom}}

# Corre la ROM sin pantalla y captura lo que dibuja. Las teclas se mantienen
# apretadas mientras corre, para capturar con la cámara movida.
snes-shot nombre="mapa" segundos="4" teclas="":
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}}
  if [ "{{motor}}" = "libretro" ]; then
    python3 tools/snes_correr.py {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
        --cuadros $(( {{segundos}} * 60 )) \
        --teclas $(echo "{{teclas}}" | tr 'A-Z' 'a-z')
  else
    snes/screenshot.sh {{snes_rom}} {{snes_pngs}}/{{nombre}}.png {{segundos}} "{{teclas}}"
  fi

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
snes-walk mapa="7" direccion="none" segundos="8" mapas="" inicial="0" nombre=(mapa + "-" + direccion):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}}
  python3 tools/snes_expect.py --map-id {{mapa}} --walk {{direccion}} \
      --mapas {{mapas}} --inicial {{inicial}} \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  if [ "{{motor}}" = "libretro" ]; then
    python3 tools/snes_correr.py {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
        --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt
  else
    just snes-shot {{nombre}} {{segundos}} "$(just _tecla {{direccion}})"
  fi
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
snes-puerta origen="30" destino="28" direccion="down" segundos="8" nombre=("puerta-" + origen + "-" + destino):
  #!/usr/bin/env bash
  set -euo pipefail
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  python3 tools/snes_expect.py --map-id {{origen}} --mapas {{destino}} \
      --walk {{direccion}} --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      --plan {{snes_pngs}}/plan-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  if [ "{{motor}}" = "libretro" ]; then
    python3 tools/snes_correr.py {{snes_rom}} -o {{snes_pngs}}/{{nombre}}.png \
        --walk {{direccion}} --plan {{snes_pngs}}/plan-{{nombre}}.txt \
        --margen 16
  else
    just snes-shot {{nombre}} {{segundos}} "$(just _tecla {{direccion}})"
  fi
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
snes-tinte sin="snes/shots/destino.png" con="snes/shots/evento.png" r="0" g="0" b="100":
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
  python3 tools/snes_convert.py --map-id {{origen}} --mapas {{destino}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 4 ""
  python3 tools/snes_expect.py --map-id {{origen}} --mapas {{destino}} \
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
  python3 tools/snes_convert.py --map-id {{primero}} --mapas {{otros}} \
      --inicial {{indice}} -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-walk {{primero}} none 8 "{{otros}}" {{indice}} varios-{{primero}}-none
  just snes-walk {{primero}} down 8 "{{otros}}" {{indice}} varios-{{primero}}-down

# Planta al héroe en una celda elegida y compara sin caminar. Llegar a un lugar
# puntual caminando depende de cuántos segundos se mantenga la cruceta, que es
# frágil; acá la cámara queda donde uno quiere y la captura no se negocia.
snes-parado mapa="1" tx="75" ty="88" nombre="parado":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  python3 tools/snes_convert.py --map-id {{mapa}} --inicio {{tx}} {{ty}} \
      -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 4 ""
  python3 tools/snes_expect.py --map-id {{mapa}} --hero-tile {{tx}} {{ty}} \
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
  python3 tools/snes_convert.py --map-id {{mapa}} --inicio {{tx}} {{ty}} \
      --heroe-encima -o {{snes_inc}}/mapdata.inc
  just snes-build
  just snes-shot {{nombre}} 4 ""
  python3 tools/snes_expect.py --map-id {{mapa}} --hero-tile {{tx}} {{ty}} \
      --dir down --heroe-encima --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/esperado-{{nombre}}.png
  python3 tools/snes_compare.py {{snes_pngs}}/{{nombre}}.png \
      {{snes_pngs}}/esperado-{{nombre}}.png \
      --saltar {{snes_pngs}}/saltar-{{nombre}}.txt \
      -o {{snes_pngs}}/comparacion-{{nombre}}.png

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
# Los segundos son cuánto se mantiene la cruceta: tiene que alcanzar para
# cruzar el mapa a 2 pixeles por cuadro.
#
# La lista vive en snes/hitos.txt y no acá, para que ésta y snes-hitos-paralelo
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
  done < <(grep -v '^#' snes/hitos.txt | grep -v '^$')
  exit $fallo

# Los mismos casos, uno por proceso y cada uno en su propia corrida aislada.
# Con la tanda en serie son unos 16 minutos de reloj de los cuales casi todo es
# el emulador durmiendo: 49 capturas y 738 segundos de sleep pedido. El piso
# acá es el caso más largo —los 45 segundos por dirección del mapa 52, o sea
# unos 4 minutos— así que de cuatro trabajadores para arriba no baja mucho más.
#
# Un rojo acá se vuelve a correr solo antes de creerle. Mednafen emula en
# tiempo real: si la máquina se sobresuscribe emula menos cuadros en los mismos
# segundos de reloj, el héroe queda corto de la pared y la comparación se va a
# miles de pixeles. Falla ruidosamente, que es lo importante, pero se parece
# demasiado a una regresión de verdad.
snes-hitos-paralelo trabajos="4":
  #!/usr/bin/env bash
  set -uo pipefail
  mkdir -p snes/build
  # Por xargs viajan números de línea y no los casos. xargs procesa comillas y
  # se come las de `snes-evento 4 "7 19 1" tabla`, que entonces le llega a just
  # como seis argumentos sueltos; el caso se cae y la tanda sigue con uno menos.
  # Pasando el número y releyendo la línea adentro, el texto no cruza nunca el
  # quoting de xargs.
  casos=$(grep -v '^#' snes/hitos.txt | grep -v '^$')
  total=$(printf '%s\n' "$casos" | wc -l)
  # Los rojos se anotan en archivos y no en el código de salida del bash
  # interno. Si éste saliera con 1, xargs deja de largar trabajo nuevo y una
  # tanda con un caso roto no llega a correr los demás, que para una prueba de
  # regresión es justo al revés de lo que uno quiere: se corre todo y se
  # informa al final.
  rm -f snes/build/hito-*.rojo
  seq 1 "$total" | xargs -P {{trabajos}} -I{} bash -c '
      caso=$(grep -v "^#" snes/hitos.txt | grep -v "^$" | sed -n "{}p")
      salida=snes/build/hito-{}.log
      if CORRIDA=hito-{} eval "just $caso" >"$salida" 2>&1; then
        echo "ok    $caso"
      else
        echo "ROJO  $caso  -> $salida"
        : > snes/build/hito-{}.rojo
      fi'
  rojos=$(ls snes/build/hito-*.rojo 2>/dev/null | wc -l)
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
snes-heroe mapa="7" segundos="8":
  #!/usr/bin/env bash
  set -euo pipefail
  just snes-convert {{mapa}}
  just snes-build
  # La referencia va primero porque es la que dice cuántos cuadros dura cada
  # caminata: sabe cuántas celdas se recorren, y el paso son ocho cuadros. Antes
  # el orden daba igual, porque el emulador corría un número de segundos
  # elegido a ojo.
  python3 tools/snes_expect.py --map-id {{mapa}} --walk none right left up down \
      --saltar {{snes_pngs}}/saltar-{{mapa}}-{}.txt \
      --plan {{snes_pngs}}/plan-{{mapa}}.txt \
      -o {{snes_pngs}}/esperado-{{mapa}}-{}.png
  if [ "{{motor}}" = "libretro" ]; then
    python3 tools/snes_correr.py {{snes_rom}} \
        -o {{snes_pngs}}/{{mapa}}-{}.png --walk none right left up down \
        --plan {{snes_pngs}}/plan-{{mapa}}.txt
  else
    for d in none right left up down; do
      just snes-shot {{mapa}}-$d {{segundos}} "$(just _tecla $d)"
    done
  fi
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
snes-mapa mapa="7" segundos="5":
  just snes-convert {{mapa}}
  just snes-build
  just snes-shot {{mapa}}-centro {{segundos}}
  just snes-compare {{mapa}}-centro 0 0
  just snes-shot {{mapa}}-derecha {{segundos}} "Right"
  just snes-compare {{mapa}}-derecha $(just _cam-x) 0
  just snes-shot {{mapa}}-abajo {{segundos}} "Down"
  just snes-compare {{mapa}}-abajo 0 $(just _cam-y)
  just snes-shot {{mapa}}-esquina {{segundos}} "Right Down"
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
# snes/snes.cfg y snes/Makefile existen sólo para esto.

snes-image:
  podman build -t abl-snes snes

snes-validar:
  python3 tools/w65_coverage.py -o snes/build/cobertura.s
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/snes abl-snes \
      sh -c 'ca65 --cpu 65816 -o build/cobertura.o build/cobertura.s \
             && ld65 -C snes.cfg -o build/cobertura-ca65.sfc build/cobertura.o'
  python3 tools/w65.py --sin-checksum snes/build/cobertura.s -o snes/build/cobertura-w65.sfc
  python3 tools/w65_check.py snes/build/cobertura-w65.sfc snes/build/cobertura-ca65.sfc

# El MIDI del mapa a muestras BRR y un stream para el DSP.
snes-music mapa="67":
  python3 tools/snes_music.py --map-id {{mapa}}

# Corre la ROM sin pantalla, graba el audio y compara lo que suena contra el
# MIDI. Sirve para verificar sin escuchar: para cada nota que debería estar
# sonando se mide su energía y la de un señuelo un cuarto de tono más arriba.
snes-check mapa="67" segundos="60":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  snes/record.sh {{snes_rom}} {{snes_pngs}}/tema.wav {{segundos}}
  python3 tools/snes_check.py {{snes_pngs}}/tema.wav --map-id {{mapa}}

# El mismo MIDI tocado por FluidSynth en la PC, con el mismo SoundFont del que
# salen nuestras muestras, y medido con la misma vara. Es el techo: dice cuánto
# de lo que falta es culpa nuestra y cuánto es de la medición.
snes-referencia mapa="67" banco="/extras/soundfonts/Microsoft GS Wavetable Synth.sf2":
  mkdir -p {{snes_pngs}} {{snes_inc}}
  fluidsynth -F snes/shots/referencia.wav -r 48000 \
      "{{banco}}" \
      "$(python3 tools/midi_path.py --map-id {{mapa}})"
  python3 tools/snes_check.py snes/shots/referencia.wav --map-id {{mapa}}

# Todo junto: convertir, compilar y verificar.
snes mapa="67": (snes-music mapa) snes-build (snes-check mapa)

# La ROM en una ventana, con sonido. Corre en el host por lo mismo que md-play.
snes-play:
  mednafen -command.exit "keyboard 0x0 20+ctrl" -sound.driver sdl {{snes_rom}}
