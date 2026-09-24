"""Los cuadros de texto rearmados para el ancho de la SNES: `port.textos`.

No corre ninguna ROM. La función todavía no la llama el conversor, así que lo
que cubre esto es la función y nada más: que lo que devuelve entra, que no
pierde palabras, y que no toca lo que ya entraba. Si se lee bien lo dice taro
jugando.
"""

import glob
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from port import eventos                                # noqa: E402
from port import textos                                 # noqa: E402
from port import ventana                                # noqa: E402


def _palabras(cuadros, con_hablante):
    desde = 1 if con_hablante else 0
    return " ".join(" ".join(c[desde:]) for c in cuadros).split()


def test_un_cuadro_que_entra_no_se_toca():
    """Ni los espacios de adentro: son del autor."""
    cuadro = ["                  < Kiss >"]
    assert textos.reajustar(cuadro) == [cuadro]


def test_se_rearma_y_conserva_al_que_habla():
    cuadro = ["KERSH", "I have pressing business within the Linkage",
              "Block. No turning back."]
    salida = textos.reajustar(cuadro)
    assert len(salida) == 1
    assert salida[0][0] == "KERSH"
    assert all(len(t) <= ventana.COLUMNAS for t in salida[0])
    assert _palabras(salida, True) == _palabras([cuadro], True)


def test_lo_que_no_entra_se_parte_y_repite_al_que_habla():
    """Como hace el juego con los cuadros seguidos del mismo personaje."""
    cuadro = ["MANTA",
              "According to this, the Catch Colony is connected",
              "to the Block by an electromagnetic Link, which",
              "keeps the Colony from drifting into space."]
    salida = textos.reajustar(cuadro)
    assert len(salida) == 2
    assert all(c[0] == "MANTA" for c in salida)
    assert all(len(c) <= ventana.LINEAS for c in salida)
    assert _palabras(salida, True) == _palabras([cuadro], True)


def test_la_cola_va_al_final_del_ultimo_cuadro():
    cuadro = ["CORE", "Thank you, Manta. And maybe... after all this,",
              "you'll be able to tell me the answer to the",
              "question none of my abilities... can.\\|\\^"]
    salida = textos.reajustar(cuadro)
    assert len(salida) > 1
    assert salida[-1][-1].endswith("can.\\|\\^")
    assert not any("\\" in t for c in salida[:-1] for t in c)


@pytest.mark.parametrize("linea, es", [
    ("KERSH", True),
    ("TRAM OFFICER", True),
    ("?????", True),
    ("WHAT?", False),
    ("NO!", False),
    ("Kersh", False),
])
def test_quien_habla(linea, es):
    assert textos.es_hablante(linea) is es


def _cuadros_del_juego():
    rutas = sorted(glob.glob(os.path.join(RAIZ, "data", "maps", "Map*.json")))
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


def test_los_comandos_que_no_cambian_son_los_mismos_objetos():
    cuadro_que_entra = {"code": eventos.SHOW_MESSAGE, "indent": 1,
                        "parameters": [], "string": "Hi."}
    otro = {"code": 10310, "indent": 1, "parameters": [0, 0], "string": ""}
    largo = [{"code": eventos.SHOW_MESSAGE, "indent": 2, "parameters": [],
              "string": "MANTA"},
             {"code": eventos.SHOW_MESSAGE_2, "indent": 2, "parameters": [],
              "string": "I already told you. He didn't go this way. Twice."}]
    salida = textos.reajustar_comandos([cuadro_que_entra, otro] + largo)
    assert salida[0] is cuadro_que_entra and salida[1] is otro
    nuevos = salida[2:]
    assert nuevos[0]["code"] == eventos.SHOW_MESSAGE
    assert all(c["code"] == eventos.SHOW_MESSAGE_2 for c in nuevos[1:])
    assert all(c["indent"] == 2 for c in nuevos)
