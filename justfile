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

# ChipSet + mapa -> tiles de 8x8 a 4bpp, paletas de 9 bits y tilemap.
md-convert map_id="7":
  mkdir -p md/shots
  python3 tools/md_convert.py --map-id {{map_id}} -o md/src/mapdata \
      --reference md/shots/reference.png

md-build:
  podman run --rm --mount=type=bind,src=.,dst=/abl -w /abl/md abl-md make

# Corre la ROM sin pantalla y saca un screenshot del framebuffer.
md-shot region="E":
  podman run --rm --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/screenshot.sh /abl/md/build/abl.bin \
      /abl/md/shots/emulador-{{region}}.png 5 {{region}}

md-compare map_id="7" region="E":
  python3 tools/render_map.py --map-id {{map_id}} --no-events -o md/shots/python.png
  python3 tools/md_compare.py md/shots/emulador-{{region}}.png \
      md/shots/reference.png md/shots/python.png \
      -o md/shots/comparacion-{{region}}.png

# Todo el camino, en las dos regiones: PAL muestra el mapa entero, NTSC los
# primeros 224 renglones.
md map_id="7":
  just md-convert {{map_id}}
  just md-build
  just md-shot E
  just md-compare {{map_id}} E
  just md-shot U
  just md-compare {{map_id}} U

# La ROM en una ventana de verdad, para jugarla. Necesita X y un
# `xhost +local:` antes.
md-play:
  podman run --rm -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
      --mount=type=bind,src=.,dst=/abl abl-md blastem -r E /abl/md/build/abl.bin
