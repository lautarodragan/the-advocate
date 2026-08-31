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

md-image:
  podman build -t abl-md md

# ChipSet + mapa -> tiles de 8x8 a 4bpp, paletas de 9 bits y tilemap, más el
# render de Python contra el que se compara después.
md-convert map_id="8":
  mkdir -p md/shots
  python3 tools/md_convert.py --map-id {{map_id}} -o md/src/mapdata \
      --reference md/shots/reference.png
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

# La ROM en una ventana de verdad, para moverla con las flechas. Necesita un
# `xhost +local:` antes; en Wayland sale por XWayland.
#
# SDL_AUDIODRIVER=dummy porque el contenedor no tiene tarjeta de sonido y
# blastem aborta si no puede abrir audio. -g apaga OpenGL: sin /dev/dri adentro
# no hay driver, y para 320x240 el render por software sobra. Si querés GL,
# agregale --device /dev/dri y sacale el -g.
md-play region="E":
  podman run --rm \
      -e DISPLAY \
      -e SDL_AUDIODRIVER=dummy \
      -v /tmp/.X11-unix:/tmp/.X11-unix \
      --mount=type=bind,src=.,dst=/abl \
      abl-md blastem -g -r {{region}} /abl/md/build/abl.bin
