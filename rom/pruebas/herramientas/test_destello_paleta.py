"""Nadie comparte la paleta de sprite de un líder posible.

El destello de un evento —`FlashSprite`, la orden 11320— en la consola es un
tinte de CGRAM: `pintar_flash` sube la paleta del personaje con el color
mezclado, así que **tiñe la paleta entera** y con ella todo lo que la comparta.
RM2k no: aplica el destello sobre la imagen del sprite.

O sea que compartir la paleta del héroe no es un detalle de empaquetado: es una
diferencia real con RM2k que la tanda de pixeles **no puede ver**, porque
ninguno de sus casos tiene un segundo sprite visible compartiendo la paleta
del que destella.

taro lo encontró jugando el 2026-09-07: en el Emitter Room, cuando Talan absorbe
el enojo de Core y destella en rojo, dos tiles encima de unos cofres —negros y
por lo tanto invisibles— se ponían rojos con él. Compartían la paleta 0 con
`Future1:0`.

Se protege al líder y no a "el que destella" porque el blanco de un destello
puede ser cualquier evento y se decide corriendo; el héroe es el que destella en
este juego y es el único que se puede saber al convertir.
"""

import collections
import os

import pytest

from render import render_map
from rpgmaker import resources
from port import snes_convert

from datos import DEMO

# El juego original, del mismo lugar que el conversor: `ABL_GAME_DIR`.
JUEGO = resources.GAME_DIR
GRUPO = [10]

# El Emitter Room, que es donde taro lo vio, y los dos mapas grandes de la
# apertura, que son los que aprietan las paletas.
MAPAS = [3, 2, 1]


@pytest.mark.parametrize("map_id", MAPAS)
def test_ningun_tile_entra_en_la_paleta_de_un_lider(map_id):
    ren = render_map.Renderer(JUEGO)
    lideres = snes_convert.lideres_posibles(ren, DEMO, GRUPO)
    game_map = ren.load_map(os.path.join(JUEGO, "Map%04d.lmu" % map_id))
    _npcs, _fuera, reparto = snes_convert.npcs_dibujables(
        ren, game_map, lideres, snes_convert.OBJ_PALETTES, [])
    paletas, paleta_de = reparto[0], reparto[1]

    de_lider = set()
    for actor in lideres:
        a = ren.database.actors[actor]
        clave = (a.charset, a.charset_index)
        if clave in paleta_de:
            de_lider.add(paleta_de[clave])

    por_paleta = collections.defaultdict(list)
    for clave, numero in paleta_de.items():
        por_paleta[numero].append(clave)

    claves_lider = {(ren.database.actors[a].charset,
                     ren.database.actors[a].charset_index) for a in lideres}
    assert de_lider, "este mapa no reparte ninguna paleta a un líder"
    for numero in sorted(de_lider):
        # **Los líderes entre sí sí comparten**: comparten una ranura, porque
        # lidera uno a la vez y la ROM le sube los colores del que toque. Lo que
        # no puede haber ahí es nadie más, que es lo que estaría en pantalla al
        # mismo tiempo que el héroe.
        intrusos = [k for k in por_paleta[numero] if k not in claves_lider]
        assert not intrusos, (
            "el mapa %d mete %s en la paleta %d, que es de un líder: cuando el "
            "héroe destelle, eso destella con él"
            % (map_id, ", ".join("%s:%d" % k for k in intrusos), numero))
