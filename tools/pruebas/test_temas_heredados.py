"""Which song may be playing when each map's package is loaded.

`temas_heredados`, in tools/port/snes_convert.py, follows the jumps of the
compiled pages without looking at conditions, and what it does not see gets
no room reserved: the song that arrives playing at a map whose package does
not count it leaves the sound effects waiting for the next `PlayBGM`, and on
top of that the layout ignores it. It happened with `Kfmus5`, which enters
41 from 37's page and goes on through 40 and the vidcasts: 41 and 40 only
start songs in order to leave, and the rule "a map with `PlayBGM` leaves with
one of its own" carried those to all its destinations instead of what was
playing.

It is built by hand, without a ROM: the song table of five maps shaped like
the game's. What the pages compile —`Temas.salto` and `Temas.salida`— is
covered by `test_un_salto_anota_el_tema_que_se_lleva`.
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
    """37 (1) starts K and jumps to 41 (2). 41 starts G only to go back to
    37, and with no song jumps to 40 (3); 40 starts T only to go back to 41,
    and with no song jumps to the vidcasts (4), which go back to 40.

    K arrives playing at 40 and at the vidcasts; G leaves 41 only for 37; T
    arrives at 41."""
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
            "K is playing on arrival at map %d and the package does not count it" % mapa)
    assert (3, G) not in herencia, (
        "G only plays to go back to 37 and 40 inherits it anyway")
    assert (2, T) in herencia and (1, G) in herencia


def test_el_de_arranque_sigue_con_la_regla_de_siempre():
    """The same 41 as the starting map —the router— leaves only with its exit
    song: whatever enters there would go out anywhere."""
    temas = _temas(
        por_mapa={0: {"temas": [G], "destinos": [1, 2]},
                  1: {"temas": [K], "destinos": [0]},
                  2: {"temas": [], "destinos": []}},
        salidas={0: {G: True}},
        saltos={0: {1: {G}, 2: {None}}, 1: {0: {None}}})
    herencia = _herencia(temas, 3)
    assert (2, K) not in herencia and (2, G) in herencia


def test_un_tema_aparte_no_sale_de_su_mapa():
    """38 (1) starts V in a scene and G before leaving: with V separate, G
    and not V reaches the maps it exits to."""
    temas = _temas(
        por_mapa={0: {"temas": [], "destinos": [1]},
                  1: {"temas": [V, G], "destinos": [2]},
                  2: {"temas": [], "destinos": []}},
        salidas={}, saltos={1: {2: {None}}})
    assert (2, V) in _herencia(temas, 3)
    herencia = _herencia(temas, 3, apartes=[[], [V], []])
    assert (2, V) not in herencia and (2, G) in herencia


def test_un_salto_anota_el_tema_que_se_lleva():
    """What `temas_heredados` reads is noted by the page when it compiles: the
    jump right after a `PlayBGM` takes that song along, and the one that is
    not, None."""
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
