"""Los cuadros de texto rearmados para el ancho de la SNES, sobre los de
`data/`: que todos entren sin perder palabras, y que el conversor los rearme
al leer los mapas.

No corre ninguna ROM. Lo que la función hace con cuadros armados a mano son
pruebas de las herramientas, y viven con ellas.
"""

import glob
import json
import os
import re

from common import project                               # noqa: E402
from port import events                                # noqa: E402
from port import screen_stage                          # noqa: E402
from port import constants                             # noqa: E402

# La cola de escapes de un cuadro —`\|` y `\^` al final del último
# renglón—, que no ocupa columnas: ver `escape_tail` en `rm2k-snes-text`.
COLA = re.compile(r"(\\[|^] *)+$")


def _sin_cola(cuadro):
    return cuadro[:-1] + [COLA.sub("", cuadro[-1])] if cuadro else cuadro


def _palabras(cuadros, con_hablante):
    desde = 1 if con_hablante else 0
    return " ".join(" ".join(c[desde:]) for c in cuadros).split()


def _cuadros_del_juego():
    rutas = sorted(glob.glob(os.path.join(project.data(), "maps", "Map*.json")))
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as handle:
            datos = json.load(handle)
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                comandos = pagina["event_commands"]
                i = 0
                while i < len(comandos):
                    j = i + 1
                    if comandos[i]["code"] == events.SHOW_MESSAGE:
                        while (j < len(comandos) and comandos[j]["code"]
                               == events.SHOW_MESSAGE_2):
                            j += 1
                        yield [c["string"] for c in comandos[i:j]]
                    i = j


def test_todo_el_juego_entra_sin_perder_palabras():
    """Sobre todos los cuadros de `data/`: lo que sale entra, tiene las mismas
    palabras en el mismo orden, y rearmarlo otra vez no lo cambia."""
    vistos = 0
    cuadros = list(_cuadros_del_juego())
    rearmados = screen_stage.refit(cuadros)
    salidas = []
    for cuadro, rearmado in zip(cuadros, rearmados):
        salida = rearmado["to"]
        if salida == [cuadro]:
            continue
        vistos += 1
        hablante = rearmado["speaker"]
        sin_cola = [_sin_cola(c) for c in salida]
        original = _sin_cola(cuadro)
        assert _palabras(sin_cola, hablante) == _palabras([original], hablante)
        for c in sin_cola:
            assert len(c) <= constants.LINES, c
            assert all(len(t) <= constants.COLUMNS for t in c), c
        salidas.extend(salida)
    assert vistos, "ningún cuadro se rearmó: la prueba no está mirando nada"
    # Y rearmar lo que salió no lo cambia.
    for c, otra_vez in zip(salidas, screen_stage.refit(salidas)):
        assert otra_vez["to"] == [c], c


def test_el_conversor_rearma_los_textos_al_leer_los_mapas():
    """El reajuste es un paso del pipeline: el conversor lo pone en el lector,
    y un mapa leído después ya no trae renglones que no entren. Sin esto la
    función podría estar perfecta y no correr nunca, que es el camino que
    ninguna prueba ejecuta."""
    from port import snes_convert                       # noqa: F401
    from rpgmaker import lcf
    assert lcf.REFIT_TEXTS is screen_stage.refit_commands
    mapa = lcf.Map(os.path.join(project.data(), "maps", "Map0002.json"))
    largos = [c.string for evento in mapa.events
              for pagina in evento.pages for c in pagina.commands
              if c.code in (events.SHOW_MESSAGE, events.SHOW_MESSAGE_2)
              and len(_sin_cola([c.string])[0]) > constants.COLUMNS]
    assert not largos, largos
