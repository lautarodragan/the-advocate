"""El inventario: que la ROM sume y quite ítems como `Game_Party::AddItem`,
los tope en 99 y en 0, y los guarde con la partida.

Lo que se ve de un ítem lo cobra `cofre-llave` en `test_comandos_golden.py`, el
KeyChest del mapa 133, cuya tercera página pide la llave 151 y gana cuando
está. Acá se le pregunta a la ROM por la RAM lejana, que es donde vive la
cuenta de cada ítem, con la página de prueba dando y quitando.
"""

from port import eventos

import datos


def test_items_n_es_el_del_ldb():
    """`ITEMS_N` está escrito a mano en eventos.py: que sea el del LDB."""
    db = datos.base()
    assert eventos.ITEMS_N == db.items_max + 1, (db.items_max, eventos.ITEMS_N)


def test_sumar_y_quitar_topan_como_rm2k(partida):
    # La página `inventario` da tres de la 151 y uno más (4); 120 de la 90,
    # que topa en 99; dos de la 17 y le saca cinco, que topa en 0; y la 200
    # no la toca.
    una = partida(caso="inventario")
    una.correr(30)
    assert una.item(151) == 4
    assert una.item(90) == eventos.ITEM_MAX
    assert una.item(17) == 0
    assert una.item(200) == 0


def test_el_inventario_viaja_en_la_partida(partida):
    una = partida(caso="inventario-guardar-198")
    una.guardar_en(0)
    assert una.item(151) == 4
    una.reiniciar()
    assert una.item(151) == 4, "el ítem 151 no volvió de la SRAM"
    assert una.item(90) == eventos.ITEM_MAX
