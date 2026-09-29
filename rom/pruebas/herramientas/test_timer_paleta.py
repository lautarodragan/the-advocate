"""El cronómetro no puede costarle eventos a un mapa.

Sus dígitos son **dos colores** —negro y rojo puro— y entran en la paleta de
cualquier personaje que tenga trece o menos. Reservarle una de las ocho paletas
de sprite no era contabilidad: `drawable_npcs` decide con ese número **qué
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

import pytest

from render import render_map
from rpgmaker import resources
from port import snes_convert

from datos import DEMO

# El juego original, del mismo lugar que el conversor: `ABL_GAME_DIR`.
JUEGO = resources.GAME_DIR
MAPA = 2
PUERTA = 30 - 1          # `drawable_npcs` numera los eventos desde cero

# Los mapas son `DEMO`, los de la apertura, con el mismo grupo inicial. Los
# líderes posibles no son un detalle: cada uno se lleva su paleta de sprite,
# así que preguntar con una lista corta da un mapa que entra holgado y una
# prueba que no mide nada —la primera versión de esto daba "no se descarta
# ninguno" con siete paletas—.
GRUPO = [10]


def descartados(paletas):
    """Qué eventos del mapa 2 no se dibujan con tantas paletas de sprite."""
    ren = render_map.Renderer(JUEGO)
    lideres = snes_convert.possible_leaders(ren, DEMO, GRUPO)
    game_map = ren.load_map(os.path.join(JUEGO, "Map%04d.lmu" % MAPA))
    _npcs, fuera, _reparto = snes_convert.drawable_npcs(
        ren, game_map, lideres, paletas, [])
    return {evento for evento, _tile in fuera}


def test_no_se_descarta_ningun_grafico(partida=None):
    """El invariante que pidió taro: **todos los eventos se dibujan**.

    Su argumento cierra la discusión: si no podemos incluir todos los eventos,
    el proyecto entero se cae. Así que el que no consigue paleta propia se
    dibuja con una ajena —cada color al más cercano de los que hay— y se ve mal
    en vez de no verse. Un sprite con colores raros es un error visible; uno
    invisible es una trampa, y ya costó una tarde con la puerta que Core rompe.

    Se mira con **seis** paletas y no con ocho para que el mapa se quede corto
    de verdad: con ocho entra casi todo y la prueba no diría nada.
    """
    assert descartados(snes_convert.OBJ_PALETTES - 2) == set(), \
        "el mapa 2 descarta gráficos en vez de prestarles una paleta"


def test_la_puerta_que_core_rompe_tiene_paleta(partida=None):
    """Y en particular la del evento 30, que es la que taro perdió jugando."""
    ren = render_map.Renderer(JUEGO)
    lideres = snes_convert.possible_leaders(ren, DEMO, GRUPO)
    game_map = ren.load_map(os.path.join(JUEGO, "Map%04d.lmu" % MAPA))
    npcs, _fuera, reparto = snes_convert.drawable_npcs(
        ren, game_map, lideres, snes_convert.OBJ_PALETTES - 2, [])
    paleta_de = reparto[1]
    suyos = [n for n in npcs if n["evento"] == PUERTA]
    assert suyos, "el evento 30 del mapa 2 no tiene fila de NPC"
    clave = (suyos[0]["charset"], suyos[0]["index"])
    assert clave in paleta_de, \
        "el medio de la puerta que Core rompe se quedó sin paleta"


def paletas_de(cuantos_colores, cuantas=snes_convert.OBJ_PALETTES):
    """Paletas inventadas, con colores que el cronómetro no usa."""
    return [[(1, i, k) for k in range(cuantos_colores)] for i in range(cuantas)]


def test_los_digitos_entran_en_una_paleta_que_ya_existe():
    """Con las ocho paletas ocupadas pero con lugar, no se agrega ninguna."""
    from port import window as ventana_mod
    ren = render_map.Renderer(JUEGO)
    sys_img = ventana_mod.skin(JUEGO, ren.database.system_name)
    palettes = paletas_de(13)
    _tiles, _base, cual = snes_convert.timer_digits(
        sys_img, bytes(32 * 64), palettes)
    assert len(palettes) == snes_convert.OBJ_PALETTES, \
        "el cronómetro se agregó una paleta teniendo dónde entrar"
    assert cual < snes_convert.OBJ_PALETTES
    assert len(palettes[cual]) <= 15, "la paleta que eligió se pasó de 15"


def test_si_de_verdad_no_entra_lo_dice():
    """Con las ocho llenas no hay magia posible, y tiene que cortar."""
    from port import window as ventana_mod
    ren = render_map.Renderer(JUEGO)
    sys_img = ventana_mod.skin(JUEGO, ren.database.system_name)
    with pytest.raises(SystemExit):
        snes_convert.timer_digits(sys_img, bytes(32 * 64), paletas_de(15))


def test_el_cronometro_no_cae_en_la_ranura_de_un_lider():
    """Esa ranura la pisa la ROM, así que un dígito ahí pierde su color.

    Los líderes posibles comparten una paleta y la ROM le sube los quince
    colores del que esté liderando cada vez que cambia el grupo o se carga un
    mapa. Un dígito del cronómetro metido ahí se quedaría sin su rojo en cuanto
    Talan le pase el liderazgo a Kersh.

    **Va con paletas inventadas y no con un mapa del juego, y eso es a
    propósito.** Se buscó en los 328 mapas que convierten y en **ninguno** el
    primer-ajuste del cronómetro cae en una ranura de líder: con datos reales
    este camino no se puede ejercitar, así que una prueba sobre un mapa pasaría
    igual con el guard sacado —se probó, y pasaba—. Lo que se prueba acá es el
    mecanismo: si la primera paleta con lugar es de un líder, hay que saltearla.
    """
    from port import window as ventana_mod
    ren = render_map.Renderer(JUEGO)
    sys_img = ventana_mod.skin(JUEGO, ren.database.system_name)
    # Dos paletas con lugar de sobra; la primera es la del líder.
    palettes = [[(1, 1, k) for k in range(4)], [(2, 2, k) for k in range(4)]]
    _tiles, _base, cual = snes_convert.timer_digits(
        sys_img, bytes(32 * 64), palettes, leader_owned={0})
    assert cual == 1, \
        "el cronómetro se metió en la paleta %d, que es de un líder: la ROM " \
        "se la pisa al subir los colores del que lidera" % cual


def test_las_gotas_no_caen_en_la_paleta_del_cronometro():
    """La otra ranura que la ROM pisa: la del cronómetro, y sin teñir.

    `subir_timer_pal` vuelve a subir esos dieciséis colores tal cual están en
    la ROM, a propósito —en RM2k los dígitos van **encima** del tinte de
    pantalla: `Priority_Timer` es 140 y `Priority_Screen` 90—. La lluvia va
    debajo —`Priority_Weather`, 80—, así que una gota metida en esa paleta se
    queda gris mientras todo lo demás se tiñe. Lo destapó juntar `pan-lluvia`
    con un caso de cronómetro en el mapa 6: 584 pixeles de diferencia en el
    cuadro 66 y 679 en `sacudir-lluvia-60`.

    Va con paletas inventadas y no con un mapa, por lo mismo que la de arriba:
    lo que se prueba es el mecanismo.
    """
    palettes = [[(1, 1, k) for k in range(4)], [(2, 2, k) for k in range(4)]]
    _tiles, base, cual = snes_convert.rain_drops(
        bytes(32 * 64), palettes, timer_base=64, timer_pal=0)
    assert base, "las gotas no entraron en ninguna paleta"
    assert cual != 0, \
        "las gotas cayeron en la paleta del cronómetro, que la ROM vuelve " \
        "a subir sin teñir: se quedarían grises en una pantalla teñida"
