"""Los cuadros de texto rearmados para el ancho de la SNES, sobre los de
`data/`: que todos entren sin perder palabras, y que el conversor los rearme
al leer los mapas.

No corre ninguna ROM. Lo que la función hace con cuadros armados a mano son
pruebas de las herramientas, y viven con ellas.
"""

import glob
import json
import os

from comun import proyecto                               # noqa: E402
from port import eventos                                # noqa: E402
from port import textos                                 # noqa: E402
from port import constantes                             # noqa: E402


def _palabras(cuadros, con_hablante):
    desde = 1 if con_hablante else 0
    return " ".join(" ".join(c[desde:]) for c in cuadros).split()


def _cuadros_del_juego():
    rutas = sorted(glob.glob(os.path.join(proyecto.data(), "maps", "Map*.json")))
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as handle:
            datos = json.load(handle)
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                comandos = pagina["event_commands"]
                i = 0
                while i < len(comandos):
                    j = i + 1
                    if comandos[i]["code"] == eventos.SHOW_MESSAGE:
                        while (j < len(comandos) and comandos[j]["code"]
                               == eventos.SHOW_MESSAGE_2):
                            j += 1
                        yield [c["string"] for c in comandos[i:j]]
                    i = j


def test_todo_el_juego_entra_sin_perder_palabras():
    """Sobre todos los cuadros de `data/`: lo que sale entra, tiene las mismas
    palabras en el mismo orden, y rearmarlo otra vez no lo cambia."""
    vistos = 0
    for cuadro in _cuadros_del_juego():
        salida = textos.reajustar(cuadro)
        if salida == [cuadro]:
            continue
        vistos += 1
        hablante = len(cuadro) > 1 and textos.es_hablante(cuadro[0])
        sin_cola = [eventos.cola_de_escapes(c)[0] for c in salida]
        original = eventos.cola_de_escapes(cuadro)[0]
        assert _palabras(sin_cola, hablante) == _palabras([original], hablante)
        for c in salida:
            assert textos.entra(c), c
            assert textos.reajustar(c) == [c]
    assert vistos, "ningún cuadro se rearmó: la prueba no está mirando nada"


def test_el_conversor_rearma_los_textos_al_leer_los_mapas():
    """El reajuste es un paso del pipeline: el conversor lo pone en el lector,
    y un mapa leído después ya no trae renglones que no entren. Sin esto la
    función podría estar perfecta y no correr nunca, que es el camino que
    ninguna prueba ejecuta."""
    from port import snes_convert                       # noqa: F401
    from rpgmaker import lcf
    assert lcf.REAJUSTAR_TEXTOS is textos.reajustar_comandos
    mapa = lcf.Map(os.path.join(proyecto.data(), "maps", "Map0002.json"))
    largos = [c.string for evento in mapa.events
              for pagina in evento.pages for c in pagina.commands
              if c.code in (eventos.SHOW_MESSAGE, eventos.SHOW_MESSAGE_2)
              and len(eventos.cola_de_escapes([c.string])[0][0])
              > constantes.COLUMNAS]
    assert not largos, largos
