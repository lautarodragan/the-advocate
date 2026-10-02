"""Preguntarle a `wally` por un mapa del juego, como le pregunta el
conversor: con el volcado, los forks del proyecto, los nombres que el port
les da a los gráficos y los mismos directorios de búsqueda.

Existe para las pruebas que miran decisiones que no se ven en una captura
—qué eventos se hornean y por qué eso no cambia la pasabilidad, quién
comparte paleta con un líder—: desde el 2026-09-30 esas decisiones son de la
etapa, y ésta es la única manera de verlas. `bakeable` y `split` son las dos
preguntas que la etapa contesta para eso; ver `inspect.rs`.

Lo que no es la pregunta —el volcado, los forks, los nombres, dónde se
buscan las imágenes— se lo pide al conversor (`conversor.contexto_de_mapa`),
que es el que se lo da a la etapa al convertir.
"""

import json

import conversor
import stage


def preguntar(comando, map_id, **pedido):
    """La respuesta de `wally <comando>` sobre ese mapa; `pedido`
    completa lo que la pregunta necesita, con los nombres del pedido."""
    contexto = conversor.contexto_de_mapa(map_id)
    flags = ["--data", contexto["data"]]
    for directorio in contexto["search_dirs"]:
        flags += ["--search-dir", directorio]
    request = dict(pedido, map=map_id,
                   map_files=contexto["map_files"],
                   chipset_files=contexto["chipset_files"],
                   names=contexto["names"])
    written = stage.run("wally", "maps", comando, request, *flags)
    return json.loads(written[comando + ".json"])
