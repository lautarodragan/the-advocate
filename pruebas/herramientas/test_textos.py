"""Los cuadros de texto rearmados para el ancho de la SNES: `port.textos`.

No corre ninguna ROM. La función todavía no la llama el conversor, así que lo
que cubre esto es la función y nada más: que lo que devuelve entra, que no
pierde palabras, y que no toca lo que ya entraba. Si se lee bien lo dice taro
jugando.
"""

import glob
import json
import os

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# Un renglón que no es el último y ocupa menos de esto se ve interrumpido.
CORTO = 2 * ventana.COLUMNAS // 3


@pytest.mark.parametrize("cuadro", [
    # Los dos que peor se veían en lo que taro jugó el 2026-09-24: "Remember,"
    # y "Well," solos en su renglón, para que los de abajo terminaran en punto.
    ["?????", "Remember, my alias for this operation is",
     '"Kersh." We should have the element of', "surprise."],
    ["TALAN", "Well, this decision won't get any easier.",
     "I've got to make up my mind and go!"],
    # Los otros de sus capturas que tenían el mismo problema.
    ["?????", "That security droid has been deactivated.",
     "Its attack mode has been switched off."],
    ["TALAN", "...but the Hover-Trams don't always run on",
     "time, and I might get stuck waiting for one."],
    ["TALAN", "It's Trash Dump 004 - right near my apartment.",
     "I'm not getting anywhere!"],
    ["TALAN", "Maybe there'll be another one along",
     "really soon... at least, I hope there will!"],
    ["CONDA", "Do you think he's one of the Lazer Teeth?",
     "Maybe they found out about our spy..."],
    ["CORE", "Thank you, Manta. And maybe... after all this,",
     "you'll be able to tell me the answer to the",
     "question none of my abilities... can."],
])
def test_ningun_renglon_se_interrumpe_antes_de_tiempo(cuadro):
    """Salvo el último de cada cuadro, ningún renglón queda más corto que
    `CORTO`. Todos éstos tienen una forma de cortarse que lo cumple."""
    salida = textos.reajustar(cuadro)
    for c in salida:
        assert c[0] == cuadro[0]
        cortos = [t for t in c[1:-1] if len(t) < CORTO]
        assert not cortos, c
    assert _palabras(salida, True) == _palabras([cuadro], True)


def test_un_renglon_con_oraciones_enteras_puede_quedar_corto():
    """El otro lado de la regla: cortar entre dos oraciones cortas se lee
    como un salto del autor, y no se cambia por llenar el renglón."""
    assert textos.reajustar(
        ["KERSH", "Time is running out. There's no turning back."]) == [
        ["KERSH", "Time is running out.", "There's no turning back."]]
    assert textos.reajustar(
        ["TALAN", "Ten minutes... I'm not sure I can make it."]) == [
        ["TALAN", "Ten minutes...", "I'm not sure I can make it."]]


def test_no_se_separa_un_nombre_de_su_numero():
    salida = textos.reajustar(
        ["TALAN", "I'd better not go back through Sector 33. The Lazer",
         "Teeth wouldn't be happy to see me..."])
    renglones = [t for c in salida for t in c]
    assert not any(t.endswith("Sector") for t in renglones), salida


def test_no_se_agrega_un_cuadro_por_gusto():
    """Si el texto entra en un cuadro, no se parte en dos para que se vea
    mejor: un cuadro de más es una tecla de más."""
    cuadro = ["TALAN", "Well... time to get away from the Agency. Now I've",
              "got an entire world to hide in..."]
    assert len(textos.reajustar(cuadro)) == 1


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


def test_el_conversor_rearma_los_textos_al_leer_los_mapas():
    """El reajuste es un paso del pipeline: el conversor lo pone en el lector,
    y un mapa leído después ya no trae renglones que no entren. Sin esto la
    función podría estar perfecta y no correr nunca, que es el camino que
    ninguna prueba ejecuta."""
    from port import snes_convert                       # noqa: F401
    from rpgmaker import lcf
    assert lcf.REAJUSTAR_TEXTOS is textos.reajustar_comandos
    mapa = lcf.Map(os.path.join(RAIZ, "data", "maps", "Map0002.json"))
    largos = [c.string for evento in mapa.events
              for pagina in evento.pages for c in pagina.commands
              if c.code in (eventos.SHOW_MESSAGE, eventos.SHOW_MESSAGE_2)
              and len(eventos.cola_de_escapes([c.string])[0][0])
              > ventana.COLUMNAS]
    assert not largos, largos
