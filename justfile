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
  podman run --rm --mount=type=bind,src=.,dst=/abl -w /abl/md abl-md make

# Corre la ROM sin pantalla y saca un screenshot. Las teclas son la cruceta del
# control 1: se mantienen apretadas para mover la cámara antes de capturar.
md-shot region="E" nombre="origen" teclas="" segundos="4":
  podman run --rm --mount=type=bind,src=.,dst=/abl abl-md \
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
  podman run --rm --device {{dev}} --mount=type=bind,src=.,dst=/abl \
      abl-md mono /opt/edlink/edlink.exe run --file /abl/md/build/abl.bin

# Escucha lo que la ROM escriba en el FIFO del cartucho: un printf por USB.
md-usb dev="/dev/ttyACM0":
  podman run --rm --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe usbrd --len -1 --tout -1 --print

# Datos del cartucho, para verificar que el USB conecta.
md-devinfo dev="/dev/ttyACM0":
  podman run --rm --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe devinf

# Graba lo que la ROM le escribe al PSG y lo compara con lo que pidió el
# conversor de música. Si coinciden, suena exactamente lo que se generó.
md-music map_id="8" segundos="12":
  podman run --rm --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/vgmlog.sh /abl/md/build/abl.bin /abl/md/shots/musica.vgm {{segundos}}
  python3 tools/md_music_check.py md/shots/musica.vgm --map-id {{map_id}}

# La ROM en una ventana de verdad, para moverla con las flechas. Necesita un
# `xhost +local:` antes; en Wayland sale por XWayland.
#
# El audio sale por el socket de compatibilidad PulseAudio de PipeWire. -g apaga
# OpenGL: sin /dev/dri adentro no hay driver, y para 320x240 el render por
# software sobra. Si querés GL, agregale --device /dev/dri y sacale el -g.
md-play region="E" audio="/run/user/1000/pulse":
  podman run --rm \
      -e DISPLAY \
      -e SDL_AUDIODRIVER=pulseaudio \
      -e PULSE_SERVER=unix:{{audio}}/native \
      -v /tmp/.X11-unix:/tmp/.X11-unix \
      -v {{audio}}:{{audio}} \
      --mount=type=bind,src=.,dst=/abl \
      abl-md blastem -g -r {{region}} /abl/md/build/abl.bin

# Lo mismo pero mudo, por si el socket de audio no está donde md-play espera.
md-play-mudo region="E":
  podman run --rm \
      -e DISPLAY \
      -e SDL_AUDIODRIVER=dummy \
      -v /tmp/.X11-unix:/tmp/.X11-unix \
      --mount=type=bind,src=.,dst=/abl \
      abl-md blastem -g -r {{region}} /abl/md/build/abl.bin
