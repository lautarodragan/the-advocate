"""Qué tema puede venir sonando al cargar el paquete de cada mapa.

`temas_heredados`, en tools/port/snes_convert.py, sigue los saltos de las
páginas compiladas sin mirar condiciones, y lo que no ve no le reserva lugar
a nadie: el tema que llega sonando a un mapa cuyo paquete no lo cuenta deja
los efectos esperando al próximo `PlayBGM`, y encima el reparto lo ignora.
Pasó con `Kfmus5`, que entra al 41 desde la página del 37 y sigue por el 40 y
los vidcasts: el 41 y el 40 sólo prenden temas para irse, y la regla de "un
mapa con `PlayBGM` se va con uno de los suyos" se los llevaba a todos sus
destinos en vez de lo que venía sonando.

Se arma a mano, sin ROM: la tabla de temas de cinco mapas con la forma de los
del juego. Lo que compilan las páginas —`Temas.salto` y `Temas.salida`— lo
cubre `test_un_salto_anota_el_tema_que_se_lleva`.
"""

from port import eventos                                      # noqa: E402
from port.snes_convert import temas_heredados                 # noqa: E402

K, G, T, V = 0, 1, 2, 3            # Kfmus5, golden_axe, tsmedit, vswar
SIN = 0xFF


def _temas(por_mapa, salidas, saltos):
    temas = eventos.Temas()
    temas.nombres = ["K", "G", "T", "V"]
    temas.por_mapa = por_mapa
    temas.salidas = salidas
    temas.saltos = saltos
    return temas


def _herencia(temas, n, inicial=0, apartes=None):
    nombres = [str(i) for i in range(n)]
    return {(int(nombre), t) for nombre, t in temas_heredados(
        temas, [SIN] * n, inicial, SIN, nombres, apartes=apartes)}


def test_un_mapa_que_solo_prende_temas_para_irse_deja_pasar_lo_que_venia():
    """El 37 (1) prende K y salta al 41 (2). El 41 prende G sólo para volver
    al 37, y sin tema salta al 40 (3); el 40 prende T sólo para volver al 41,
    y sin tema salta a los vidcasts (4), que vuelven al 40.

    K llega sonando al 40 y a los vidcasts; G no sale del 41 más que al 37; T
    llega al 41."""
    temas = _temas(
        por_mapa={0: {"temas": [], "destinos": [1]},
                  1: {"temas": [K], "destinos": [2]},
                  2: {"temas": [G], "destinos": [1, 3]},
                  3: {"temas": [T], "destinos": [2, 4]},
                  4: {"temas": [], "destinos": [3]}},
        salidas={2: {G: True}, 3: {T: True}},
        saltos={2: {1: {G}, 3: {None}}, 3: {2: {T, None}, 4: {None}},
                4: {3: {None}}})
    herencia = _herencia(temas, 5)
    for mapa in (3, 4):
        assert (mapa, K) in herencia, (
            "K suena al llegar al mapa %d y el paquete no lo cuenta" % mapa)
    assert (3, G) not in herencia, (
        "G sólo suena para volver al 37 y el 40 lo hereda igual")
    assert (2, T) in herencia and (1, G) in herencia


def test_el_de_arranque_sigue_con_la_regla_de_siempre():
    """El mismo 41 como mapa de arranque —el enrutador— se va sólo con su
    tema de salida: lo que entra ahí saldría para cualquier lado."""
    temas = _temas(
        por_mapa={0: {"temas": [G], "destinos": [1, 2]},
                  1: {"temas": [K], "destinos": [0]},
                  2: {"temas": [], "destinos": []}},
        salidas={0: {G: True}},
        saltos={0: {1: {G}, 2: {None}}, 1: {0: {None}}})
    herencia = _herencia(temas, 3)
    assert (2, K) not in herencia and (2, G) in herencia


def test_un_tema_aparte_no_sale_de_su_mapa():
    """El 38 (1) prende V en una escena y G antes de irse: con V aparte, a
    los mapas a los que se sale llega G y no V."""
    temas = _temas(
        por_mapa={0: {"temas": [], "destinos": [1]},
                  1: {"temas": [V, G], "destinos": [2]},
                  2: {"temas": [], "destinos": []}},
        salidas={}, saltos={1: {2: {None}}})
    assert (2, V) in _herencia(temas, 3)
    herencia = _herencia(temas, 3, apartes=[[], [V], []])
    assert (2, V) not in herencia and (2, G) in herencia


def test_un_salto_anota_el_tema_que_se_lleva():
    """Lo que `temas_heredados` lee lo anota la página al compilar: el salto
    que va pegado a un `PlayBGM` se lleva ese tema, y el que no, None."""
    temas = eventos.Temas()
    temas.nombres = ["K"]
    temas.mapa = 0

    class Cmd:
        def __init__(self, code, parameters=(), string=""):
            self.code, self.parameters, self.string = code, list(parameters), \
                string
    bgm = [None, [], []]
    for cmd in (Cmd(eventos.TELEPORT, [20, 1, 1]),
                Cmd(eventos.PLAY_BGM, [0, 100, 100, 50], "K"),
                Cmd(eventos.TELEPORT, [30, 1, 1])):
        eventos._seguir_la_salida(cmd, bgm, temas,
                                  lambda mapa: {20: 1, 30: 2}.get(mapa),
                                  False)
    assert bgm[2] == [(1, None), (2, 0)]
