"""La pantalla de ítems del menú de pausa: que se vea como
`pantallas.items` pixel por pixel, que la lista se corra cuando el cursor
se sale, y que usar un ítem de switch lo prenda y vuelva al mapa.

El inventario lo da la página de prueba con `ChangeItems` de verdad, así que
la ROM lo tiene por el mismo camino que el juego. El mapa después de usar la
consola lo mira `items` en `test_menu_golden.py`.
"""


from consola import TITULO_AIRE
import pantallas
from dibujo import comparar_pantalla
from menu import abrir

# Una poción de más de diez, un arma y la consola: el arma va en gris. Es lo
# que da la página de prueba `items-pantalla`, y `MUCHOS` lo que da
# `items-pantalla-muchos`: los dos tienen que decir lo mismo que su archivo.
INVENTARIO = {1: 13, 17: 1, 81: 1}
# Catorce distintos, para que la lista no entre en sus `ITEM_ROWS` filas.
MUCHOS = {n: 1 for n in range(1, 15)}


def items_de(inventario):
    return tuple(x for par in sorted(inventario.items()) for x in par)


def entrar(una):
    """Del mapa a la pantalla de ítems: B, y A sobre la primera orden."""
    una.correr(30)
    abrir(una)
    una.tocar_cuadros("a", TITULO_AIRE)
    assert una.menu_abierto()
    return una


def comparar(una, inventario, elegida, arriba=0, nombre="items"):
    esperada = pantallas.items(inventario, elegida, arriba)
    comparar_pantalla(una, esperada, nombre,
                      "la pantalla de ítems con el cursor en %d" % elegida)


def test_la_pantalla_se_ve_como_la_referencia(partida):
    """Como se entra, y con el cursor dos más abajo: el cursor y la
    descripción cambian adentro del vblank. B vuelve al menú."""
    una = entrar(partida(caso="items-pantalla"))
    comparar(una, INVENTARIO, 0)
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")
    comparar(una, INVENTARIO, 2, nombre="items-2")
    una.tocar_cuadros("b", TITULO_AIRE)
    assert una.menu_abierto(), "B tenía que volver al menú, no al mapa"


def test_usar_la_consola_prende_su_switch_y_vuelve_al_mapa(partida):
    """La Portable Console es de switch: prende el 710, no se gasta —tiene
    cero usos, que en RM2k es "infinitos"— y RM2k vuelve derecho al mapa."""
    una = entrar(partida(caso="items-pantalla"))
    assert not una.switch(710)
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")           # la consola, tercera en la lista
    una.tocar_cuadros("a", 20)
    assert not una.menu_abierto(), "usar la consola tenía que volver al mapa"
    assert una.switch(710), "la consola no prendió su switch"
    assert una.item(81) == 1, "la consola se gastó y tiene usos infinitos"


def test_un_item_en_gris_no_hace_nada(partida):
    una = entrar(partida(caso="items-pantalla"))
    una.tocar_cuadros("down")
    una.tocar_cuadros("a", 20)          # el arma, en gris
    assert una.menu_abierto()
    assert una.item(17) == 1
    comparar(una, INVENTARIO, 1, nombre="items-gris")


def test_la_medicina_abre_la_eleccion_de_actor_y_no_se_gasta(partida):
    """La poción va en blanco y abre `Scene_ActorTarget`. Los dos tienen los
    HP llenos, así que A no le sirve a nadie y la poción no se gasta —curar de
    verdad es `test_menu_curar_dibujo.py`—; B vuelve a la lista con el cursor
    donde estaba."""
    una = partida(caso="items-pantalla")
    una.correr(5)
    una.poner_grupo(14, 11)
    entrar(una)
    una.tocar_cuadros("a", TITULO_AIRE)  # la poción
    for elegida in (0, 1):
        esperada = pantallas.objetivo(4, (14, 11), elegida, item=1,
                                      cantidad=INVENTARIO[1])
        comparar_pantalla(una, esperada,
                          que="la elección de actor con el cursor en %d"
                          % elegida)
        una.tocar_cuadros("down")
    una.tocar_cuadros("a", 20)
    assert una.item(1) == 13, "la poción se gastó sin tener efecto"
    una.tocar_cuadros("b", TITULO_AIRE)
    comparar(una, INVENTARIO, 0, nombre="items-vuelve")


def test_la_lista_se_corre_cuando_el_cursor_se_sale(partida):
    """Catorce ítems en `ITEM_ROWS` filas: bajando hasta el último la lista
    se corre lo que sobra, y subiendo hasta el primero vuelve."""
    una = entrar(partida(caso="items-pantalla-muchos"))
    for _ in range(13):
        una.tocar_cuadros("down")
    comparar(una, MUCHOS, 13, arriba=14 - pantallas.disposicion().ITEM_ROWS,
             nombre="items-abajo")
    una.tocar_cuadros("down")           # no hay más: se queda
    comparar(una, MUCHOS, 13, arriba=14 - pantallas.disposicion().ITEM_ROWS,
             nombre="items-abajo")
    for _ in range(13):
        una.tocar_cuadros("up")
    comparar(una, MUCHOS, 0, arriba=0, nombre="items-arriba")


def test_la_lista_vacia(partida):
    una = entrar(partida())
    comparar(una, {}, 0, nombre="items-vacia")
    una.tocar_cuadros("a", 20)
    una.tocar_cuadros("down")
    assert una.menu_abierto()
    una.tocar_cuadros("b", TITULO_AIRE)
    assert una.menu_abierto()
