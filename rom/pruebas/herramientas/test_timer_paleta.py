"""El cronómetro no puede costarle eventos a un mapa.

Sus dígitos son **dos colores** —negro y rojo puro— y entran en la paleta de
cualquier personaje que tenga trece o menos. Reservarle una de las ocho paletas
de sprite no era contabilidad: el reparto de paletas decide con ese número
**qué eventos se dibujan**, y un evento que no se dibuja igual ocupa, así que
la pérdida no es visual sino jugable.

Lo encontró taro el 2026-09-07 jugando el build del día: llegó a la cinemática
en la que Core rompe la puerta del mapa 2, la puerta no cambió de tile y no pudo
pasar. El evento 30 es la celda del medio de esa puerta —(71,69), de tile 25 a
28— y con siete paletas se caía.

Ninguna de estas pruebas arranca una ROM: le preguntan a la etapa del
conversor, `wally split`, que es donde está la decisión. Las del
mecanismo —que los dígitos entren en una paleta que ya existe, que corte si
de verdad no entran, que no caigan en la ranura de un líder ni las gotas en
la del cronómetro— no necesitan el juego y están con él, en `extras.rs` de
`rm2k-snes-map-sprites`.
"""

from render import render_map
from rpgmaker import resources
# Por los ganchos que pone en `lcf` al importarse: los mapas se leen como
# los lee el conversor.
from port import snes_convert                            # noqa: F401
from port import game_scan

from datos import DEMO
from etapa_mapas import preguntar

# El juego original, del mismo lugar que el conversor: `ABL_GAME_DIR`.
JUEGO = resources.GAME_DIR
MAPA = 2
PUERTA = 30 - 1          # la etapa numera los eventos desde cero

# Los mapas son `DEMO`, los de la apertura, con el mismo grupo inicial. Los
# líderes posibles no son un detalle: cada uno se lleva su paleta de sprite,
# así que preguntar con una lista corta da un mapa que entra holgado y una
# prueba que no mide nada —la primera versión de esto daba "no se descarta
# ninguno" con siete paletas—.
GRUPO = [10]

# **Seis** paletas y no ocho, para que el mapa se quede corto de verdad: con
# ocho entra casi todo y la prueba no diría nada.
PALETAS = 6


def reparto():
    """El reparto del mapa 2 con seis paletas de sprite."""
    ren = render_map.Renderer(JUEGO)
    lideres = game_scan.possible_leaders(ren, DEMO, GRUPO)
    return preguntar("split", MAPA, ren, leaders=lideres, palettes=PALETAS)


def test_no_se_descarta_ningun_grafico(partida=None):
    """El invariante que pidió taro: **todos los eventos se dibujan**.

    Su argumento cierra la discusión: si no podemos incluir todos los eventos,
    el proyecto entero se cae. Así que el que no consigue paleta propia se
    dibuja con una ajena —cada color al más cercano de los que hay— y se ve mal
    en vez de no verse. Un sprite con colores raros es un error visible; uno
    invisible es una trampa, y ya costó una tarde con la puerta que Core rompe.
    """
    assert reparto()["discarded"] == [], \
        "el mapa 2 descarta gráficos en vez de prestarles una paleta"


def test_la_puerta_que_core_rompe_tiene_paleta(partida=None):
    """Y en particular la del evento 30, que es la que taro perdió jugando."""
    respuesta = reparto()
    paleta_de = {(c, i) for c, i, _n in respuesta["palette_of"]}
    suyos = [n for n in respuesta["npcs"] if n["event"] == PUERTA]
    assert suyos, "el evento 30 del mapa 2 no tiene fila de NPC"
    clave = (suyos[0]["charset"], suyos[0]["index"])
    assert clave in paleta_de, \
        "el medio de la puerta que Core rompe se quedó sin paleta"
