"""El inventario: que la ROM sume y quite ítems como `Game_Party::AddItem`,
los tope en 99 y en 0, y los guarde con la partida.

Lo que se ve de un ítem lo cobra la tanda: `cofre-llave` en `pruebas/*/test_tanda*.py`, el
KeyChest del mapa 133, cuya tercera página pide la llave 151 y gana cuando
está. Acá se le pregunta a la ROM por la RAM lejana, que es donde vive la
cuenta de cada ítem, con la página de prueba dando y quitando.
"""

import os

from port import eventos
from rpgmaker import lcf
from render.render_map import GAME_DIR

# Lo que da la página de prueba `inventario`, de a dos —ítem y cuánto—: tres de
# la 151, uno más (4); 120 de la 90, que topa en 99; dos de la 17 y cinco
# menos, que topa en 0; y la 200 queda en cero. Es con lo que se calcula lo que
# tiene que dar, así que tiene que decir lo mismo que el archivo.
ITEMS = (151, 3, 151, 1, 90, 120, 17, 2, 17, -5)


def test_items_n_es_el_del_ldb():
    """`ITEMS_N` está escrito a mano en eventos.py: que sea el del LDB."""
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    assert eventos.ITEMS_N == db.items_max + 1, (db.items_max, eventos.ITEMS_N)


def test_sumar_y_quitar_topan_como_rm2k(partida):
    una = partida(caso="inventario")
    una.correr(30)
    assert una.item(151) == 4
    assert una.item(90) == eventos.ITEM_MAX
    assert una.item(17) == 0
    assert una.item(200) == 0
    # Y la referencia dice lo mismo con el mismo bytecode.
    estado = eventos.Estado()
    for k in range(0, len(ITEMS), 2):
        n, cuanto = ITEMS[k:k + 2]
        estado.items[n] = max(0, min(eventos.ITEM_MAX,
                                     estado.item(n) + cuanto))
    assert (estado.item(151), estado.item(90), estado.item(17)) == (4, 99, 0)


def test_el_inventario_viaja_en_la_partida(partida):
    una = partida(caso="inventario-guardar-198")
    una.guardar_en(0)
    assert una.item(151) == 4
    una.reiniciar()
    assert una.item(151) == 4, "el ítem 151 no volvió de la SRAM"
    assert una.item(90) == eventos.ITEM_MAX
