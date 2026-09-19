"""La pantalla de ítems del menú de pausa: que se vea como
`titulo.render_items` pixel por pixel, que la lista se corra cuando el cursor
se sale, y que usar un ítem de switch lo prenda y vuelva al mapa.

El inventario lo da la página de prueba con `ChangeItems` de verdad, así que
la ROM lo tiene por el mismo camino que el juego. La tanda mira el mapa
después de usar la consola —`items` en `pruebas/*/test_tanda*.py`—.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
from port import titulo                                 # noqa: E402

from consola import TITULO_AIRE
from test_menu import abrir, tocar

# Una poción de más de diez, un arma y la consola: el arma va en gris. Es lo
# que da la página de prueba `items-pantalla`, y `MUCHOS` lo que da
# `items-pantalla-muchos`: los dos tienen que decir lo mismo que su archivo.
INVENTARIO = {1: 13, 17: 1, 81: 1}
# Catorce distintos, para que la lista no entre en las once filas. La primera
# versión llevaba el texto de cada ítem ya dibujado y éstos no entraban en el
# banco —700 tiles de 448—; con la fuente de a una letra por celda el banco es
# el mismo para cualquier inventario.
MUCHOS = {n: 1 for n in range(1, 15)}


def items_de(inventario):
    return tuple(x for par in sorted(inventario.items()) for x in par)


def entrar(una):
    """Del mapa a la pantalla de ítems: B, y A sobre la primera orden."""
    una.correr(30)
    abrir(una)
    tocar(una, "a", TITULO_AIRE)
    assert una.menu_abierto()
    return una


def comparar(una, inventario, elegida, arriba=0, nombre="items"):
    from rpgmaker import lcf
    from port import ventana
    from render.render_map import GAME_DIR
    from tanda import quince_bits
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    captura = una.imagen().convert("RGB")
    esperada = titulo.render_items(skin, db, inventario, elegida, arriba,
                                   db.font_id)
    distintos = sum(1 for x, y in zip(quince_bits(captura), quince_bits(esperada))
                    if x != y)
    if distintos:
        donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "rom", "shots")
        os.makedirs(donde, exist_ok=True)
        captura.save(os.path.join(donde, "prueba-%s.png" % nombre))
        esperada.save(os.path.join(donde, "prueba-%s.esperado.png" % nombre))
    assert distintos == 0, (
        "la pantalla de ítems con el cursor en %d difiere de la referencia en "
        "%d pixeles; están en rom/shots/prueba-%s*.png"
        % (elegida, distintos, nombre))


def test_la_pantalla_se_ve_como_la_referencia(partida):
    """Como se entra, y con el cursor dos más abajo: el cursor y la
    descripción cambian adentro del vblank. B vuelve al menú."""
    una = entrar(partida(caso="items-pantalla"))
    comparar(una, INVENTARIO, 0)
    tocar(una, "down")
    tocar(una, "down")
    comparar(una, INVENTARIO, 2, nombre="items-2")
    tocar(una, "b", TITULO_AIRE)
    assert una.menu_abierto(), "B tenía que volver al menú, no al mapa"


def test_usar_la_consola_prende_su_switch_y_vuelve_al_mapa(partida):
    """La Portable Console es de switch: prende el 710, no se gasta —tiene
    cero usos, que en RM2k es "infinitos"— y RM2k vuelve derecho al mapa."""
    una = entrar(partida(caso="items-pantalla"))
    assert not una.switch(710)
    tocar(una, "down")
    tocar(una, "down")                  # la consola, tercera en la lista
    tocar(una, "a", 20)
    assert not una.menu_abierto(), "usar la consola tenía que volver al mapa"
    assert una.switch(710), "la consola no prendió su switch"
    assert una.item(81) == 1, "la consola se gastó y tiene usos infinitos"


def test_un_item_en_gris_no_hace_nada(partida):
    una = entrar(partida(caso="items-pantalla"))
    tocar(una, "down")
    tocar(una, "a", 20)                 # el arma, en gris
    assert una.menu_abierto()
    assert una.item(17) == 1
    comparar(una, INVENTARIO, 1, nombre="items-gris")


def test_la_medicina_abre_la_eleccion_de_actor_y_no_se_gasta(partida):
    """La poción va en blanco y abre `Scene_ActorTarget`. A no tiene efecto
    —nadie tiene los HP por debajo del máximo fuera de batalla— y la poción
    no se gasta; B vuelve a la lista con el cursor donde estaba."""
    from rpgmaker import lcf
    from port import ventana
    from render.render_map import GAME_DIR
    from tanda import quince_bits
    una = partida(caso="items-pantalla")
    una.correr(5)
    una.poner_grupo(14, 11)
    entrar(una)
    tocar(una, "a", TITULO_AIRE)        # la poción
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    for elegida in (0, 1):
        captura = una.imagen().convert("RGB")
        esperada = titulo.render_objetivo(skin, db, 4, (14, 11), elegida,
                                          db.font_id, None, GAME_DIR)
        distintos = sum(1 for x, y in zip(quince_bits(captura),
                                          quince_bits(esperada)) if x != y)
        assert distintos == 0, (
            "la elección de actor con el cursor en %d difiere de la "
            "referencia en %d pixeles" % (elegida, distintos))
        tocar(una, "down")
    tocar(una, "a", 20)
    assert una.item(1) == 13, "la poción se gastó sin tener efecto"
    tocar(una, "b", TITULO_AIRE)
    comparar(una, INVENTARIO, 0, nombre="items-vuelve")


def test_la_lista_se_corre_cuando_el_cursor_se_sale(partida):
    """Catorce ítems en once filas: bajando hasta el último la lista se corre
    tres, y subiendo hasta el primero vuelve."""
    una = entrar(partida(caso="items-pantalla-muchos"))
    for _ in range(13):
        tocar(una, "down")
    comparar(una, MUCHOS, 13, arriba=3, nombre="items-abajo")
    tocar(una, "down")                  # no hay más: se queda
    comparar(una, MUCHOS, 13, arriba=3, nombre="items-abajo")
    for _ in range(13):
        tocar(una, "up")
    comparar(una, MUCHOS, 0, arriba=0, nombre="items-arriba")


def test_la_lista_vacia(partida):
    una = entrar(partida())
    comparar(una, {}, 0, nombre="items-vacia")
    tocar(una, "a", 20)
    tocar(una, "down")
    assert una.menu_abierto()
    tocar(una, "b", TITULO_AIRE)
    assert una.menu_abierto()
