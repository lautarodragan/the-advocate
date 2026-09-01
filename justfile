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
  mednafen -force_module md -md.region {{region}} -sound.driver sdl \
      md/build/abl.bin

# Lo mismo pero mudo.
md-play-mudo region="overseas_pal":
  mednafen -force_module md -md.region {{region}} -sound 0 md/build/abl.bin

# --- Super Nintendo --------------------------------------------------------
# Rama aparte, para ver si la SNES se acerca más al original que la Mega Drive.
# No toca nada del port a Mega Drive. Todo el toolchain sale de paquetes de
# Debian: cc65 para el 65816 y mednafen para emular.

snes-image:
  podman build -t abl-snes snes

snes-build:
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/snes abl-snes make

# El MIDI del mapa a muestras BRR y un stream para el DSP.
snes-music mapa="67":
  python3 tools/snes_music.py --map-id {{mapa}}

# Corre la ROM sin pantalla, graba el audio y compara lo que suena contra el
# MIDI. Sirve para verificar sin escuchar: para cada nota que debería estar
# sonando se mide su energía y la de un señuelo un cuarto de tono más arriba.
snes-check mapa="67" segundos="60":
  mkdir -p snes/shots
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl abl-snes \
      /abl/snes/record.sh /abl/snes/build/abl.sfc /abl/snes/shots/tema.wav {{segundos}}
  python3 tools/snes_check.py snes/shots/tema.wav --map-id {{mapa}}

# Todo junto: convertir, compilar y verificar.
snes mapa="67": (snes-music mapa) snes-build (snes-check mapa)

# La ROM en una ventana, con sonido. Corre en el host por lo mismo que md-play.
snes-play:
  mednafen -sound.driver sdl snes/build/abl.sfc
