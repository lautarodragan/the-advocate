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
md-convert map_id="127":
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

md-compare region="E" nombre="origen" camara="0 0":
  python3 tools/md_compare.py md/shots/{{region}}-{{nombre}}.png \
      md/shots/reference.png md/shots/python.png --camera {{camara}} \
      -o md/shots/comparacion-{{region}}-{{nombre}}.png

# Todo el camino. Se verifica la cámara en el origen y contra el tope, en las
# dos regiones: PAL muestra 240 renglones y NTSC 224, así que topan distinto.
md map_id="127":
  just md-convert {{map_id}}
  just md-build
  just md-shot E origen
  just md-compare E origen "0 0"
  just md-shot E tope "Right Down" 6
  just md-compare E tope "max max"
  just md-shot U origen
  just md-compare U origen "0 0"
  just md-shot U tope "Right Down" 6
  just md-compare U tope "max max"

# La ROM en una ventana de verdad, para moverla con el teclado. Necesita X y un
# `xhost +local:` antes.
md-play:
  podman run --rm -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
      --mount=type=bind,src=.,dst=/abl abl-md blastem -r E /abl/md/build/abl.bin
