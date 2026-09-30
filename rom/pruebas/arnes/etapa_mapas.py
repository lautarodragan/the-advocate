"""Preguntarle a `rm2k-snes-maps` por un mapa del juego, como le pregunta el
conversor: con el volcado, los forks del proyecto, los nombres que el port
les da a los gráficos y los mismos directorios de búsqueda.

Existe para las pruebas que miran decisiones que no se ven en una captura
—qué eventos se hornean y por qué eso no cambia la pasabilidad, quién
comparte paleta con un líder—: desde el 2026-09-30 esas decisiones son de la
etapa, y ésta es la única manera de verlas. `bakeable` y `split` son las dos
preguntas que la etapa contesta para eso; ver `inspect.rs`.

Hay que importar `port.snes_convert` antes, por los ganchos que pone en
`lcf`: los nombres de los translúcidos salen de ahí.
"""

import json
import os

from port import compiler, stage
from render.render_map import Renderer
from rpgmaker import resources


def preguntar(comando, map_id, renderer=None, **pedido):
    """La respuesta de `rm2k-snes-maps <comando>` sobre ese mapa; `pedido`
    completa lo que la pregunta necesita, con los nombres del pedido."""
    renderer = renderer or Renderer()
    dump = compiler.dump_of(resources.GAME_DIR)
    game_map = renderer.load_map(
        os.path.join(resources.GAME_DIR, "Map%04d.lmu" % map_id))
    flags = ["--data", dump]
    for directory in renderer.search_dirs:
        flags += ["--search-dir", os.path.abspath(directory)]
    request = dict(pedido, map=map_id,
                   map_files=compiler.map_files(dump),
                   chipset_files=compiler.chipset_files(dump),
                   names=[entry[1:] for entry in compiler.names([game_map])])
    written = stage.run("rm2k-snes-maps", "maps", comando, request, *flags)
    return json.loads(written[comando + ".json"])
