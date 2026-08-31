# Renderiza un mapa a render/MapXXXX.png. Sin dependencias que instalar:
# usa Pillow, que ya está en el sistema.
#   just render        -> mapa 7
#   just render 8
render map_id="7":
  python3 tools/render_map.py --map-id {{map_id}}

# Lista los mapas del juego con su chipset, y si el chipset está disponible.
maps:
  python3 tools/list_maps.py
