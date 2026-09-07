"""El cronómetro no puede costarle eventos a un mapa.

Sus dígitos son **dos colores** —negro y rojo puro— y entran en la paleta de
cualquier personaje que tenga trece o menos. Reservarle una de las ocho paletas
de sprite no era contabilidad: `npcs_dibujables` decide con ese número **qué
eventos se dibujan**, y un evento que no se dibuja igual ocupa, así que la
pérdida no es visual sino jugable.

Lo encontró taro el 2026-09-07 jugando el build del día: llegó a la cinemática
en la que Core rompe la puerta del mapa 2, la puerta no cambió de tile y no pudo
pasar. El evento 30 es la celda del medio de esa puerta —(71,69), de tile 25 a
28— y con siete paletas se caía.

Ninguna de estas pruebas arranca una ROM: le preguntan al conversor, que es
donde está la decisión.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import render_map                                            # noqa: E402
import snes_convert                                          # noqa: E402

JUEGO = os.environ.get("GAME_DIR", "/extras/abl-rm")
MAPA = 2
PUERTA = 30 - 1          # `npcs_dibujables` numera los eventos desde cero

# Los mismos que `demo-apertura`, y el mismo grupo inicial. Los líderes posibles
# no son un detalle: cada uno se lleva su paleta de sprite, así que preguntar
# con una lista corta da un mapa que entra holgado y una prueba que no mide nada
# —la primera versión de esto daba "no se descarta ninguno" con siete paletas—.
DEMO = [4, 1, 2, 3, 5, 6, 7]
GRUPO = [10]


def descartados(paletas):
    """Qué eventos del mapa 2 no se dibujan con tantas paletas de sprite."""
    ren = render_map.Renderer(JUEGO)
    lideres = snes_convert.lideres_posibles(ren, DEMO, GRUPO, True)
    game_map = ren.cargar_mapa(os.path.join(JUEGO, "Map%04d.lmu" % MAPA))
    _npcs, fuera, _reparto = snes_convert.npcs_dibujables(
        ren, game_map, lideres, paletas, [])
    return {evento for evento, _tile in fuera}


def test_la_puerta_que_core_rompe_se_dibuja_con_las_ocho():
    assert PUERTA not in descartados(snes_convert.OBJ_PALETTES), \
        "el evento 30 del mapa 2 —el medio de la puerta que Core rompe— no se " \
        "dibuja, así que la puerta no cambia de tile y no se puede pasar"


def test_con_menos_paletas_la_puerta_se_cae():
    """Lo que pasaba, escrito: es lo que hace que la prueba de arriba valga.

    Sin esto, la de arriba pasaría también en un mundo donde el cronómetro
    volviera a reservarse una paleta, porque no habría nada que dijera que el
    tope importa.

    Eran siete hasta que los líderes pasaron a compartir una ranura: eso le
    devolvió una paleta al mapa 2, que con siete ya no descarta la puerta —sólo
    sus costados, los eventos 31 y 32—. Con seis vuelve a caerse.
    """
    assert PUERTA in descartados(snes_convert.OBJ_PALETTES - 2), \
        "con seis paletas la puerta entra igual: este mapa ya no sirve de " \
        "banco para esta prueba"


def paletas_de(cuantos_colores, cuantas=snes_convert.OBJ_PALETTES):
    """Paletas inventadas, con colores que el cronómetro no usa."""
    return [[(1, i, k) for k in range(cuantos_colores)] for i in range(cuantas)]


def test_los_digitos_entran_en_una_paleta_que_ya_existe():
    """Con las ocho paletas ocupadas pero con lugar, no se agrega ninguna."""
    import ventana as ventana_mod
    ren = render_map.Renderer(JUEGO)
    sys_img = ventana_mod.skin(JUEGO, ren.database.system_name)
    palettes = paletas_de(13)
    _tiles, _base, cual = snes_convert.digitos_del_timer(
        sys_img, bytes(32 * 64), palettes)
    assert len(palettes) == snes_convert.OBJ_PALETTES, \
        "el cronómetro se agregó una paleta teniendo dónde entrar"
    assert cual < snes_convert.OBJ_PALETTES
    assert len(palettes[cual]) <= 15, "la paleta que eligió se pasó de 15"


def test_si_de_verdad_no_entra_lo_dice():
    """Con las ocho llenas no hay magia posible, y tiene que cortar."""
    import ventana as ventana_mod
    ren = render_map.Renderer(JUEGO)
    sys_img = ventana_mod.skin(JUEGO, ren.database.system_name)
    with pytest.raises(SystemExit):
        snes_convert.digitos_del_timer(sys_img, bytes(32 * 64), paletas_de(15))
