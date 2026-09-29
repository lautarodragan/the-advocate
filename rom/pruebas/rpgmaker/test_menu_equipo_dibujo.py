"""El equipo: la pantalla de `Scene_Equip` desde el menú, pixel por pixel
contra `pantallas.pantalla_equipo`, y lo que equipar cambia en la RAM.

El inventario lo da la página de prueba con `ChangeItems` de verdad. Talan
arranca con su ropa de trabajo, que es el equipo inicial del LDB copiado a
`FAR_EQUIPO` en el reset.
"""

from port import pantallas

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla
from menu import abrir

TALAN, KERSH = 14, 11
PALO, LANZA, ESCUDO = 17, 19, 44        # la lanza es a dos manos
# Lo que da la página de prueba `equipo-inventario`: tiene que decir lo mismo.
INVENTARIO = {PALO: 2, LANZA: 1, ESCUDO: 1}


def items_de(inventario):
    return tuple(x for par in sorted(inventario.items()) for x in par)


def entrar(una):
    """Del mapa a la pantalla de equipo de Talan: B, Equipment, y A sobre la
    primera fila del grupo."""
    una.correr(5)
    una.poner_grupo(TALAN, KERSH)
    una.correr(25)
    abrir(una)
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)  # a quién
    una.tocar_cuadros("a", TITULO_AIRE)  # Talan
    return una


def test_arranca_con_el_equipo_inicial(partida):
    una = partida()
    db = datos.base()
    assert una.equipo(TALAN) == db.actors[TALAN].initial_equipment
    assert una.equipo(KERSH) == db.actors[KERSH].initial_equipment


def test_equipar_desde_el_menu(partida):
    """Las ranuras de Talan, la lista del arma con los parámetros que
    quedarían, y el palo puesto: sale del inventario y queda en la RAM."""
    db, skin = datos.base(), datos.skin()
    una = entrar(partida(caso="equipo-inventario"))
    puesto = list(db.actors[TALAN].initial_equipment)
    inv = dict(INVENTARIO)
    comparar_pantalla(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0)
             .render(skin, db.font_id), "equipo")
    una.tocar_cuadros("a", 10)
    comparar_pantalla(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0, True,
                                            0).render(skin, db.font_id),
             "equipo-lista")
    una.tocar_cuadros("a", 10)          # el palo
    pantallas.equipar(db, puesto, inv, 0, PALO)
    assert una.equipo(TALAN) == puesto
    assert una.item(PALO) == 1
    comparar_pantalla(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0)
             .render(skin, db.font_id), "equipo-puesto")


def test_la_lanza_a_dos_manos_saca_el_escudo(partida):
    """Con el escudo puesto, ponerse la lanza lo devuelve al inventario."""
    db, skin = datos.base(), datos.skin()
    una = entrar(partida(caso="equipo-inventario"))
    una.tocar_cuadros("down")           # el escudo
    una.tocar_cuadros("a", 10)
    una.tocar_cuadros("a", 10)          # el escudo, único en la lista
    assert una.equipo(TALAN)[1] == ESCUDO
    assert una.item(ESCUDO) == 0
    una.tocar_cuadros("up")             # el arma
    una.tocar_cuadros("a", 10)
    una.tocar_cuadros("down")           # la lanza, segunda en la lista
    puesto = list(db.actors[TALAN].initial_equipment)
    puesto[1] = ESCUDO
    inv = dict(INVENTARIO)
    inv[ESCUDO] = 0
    comparar_pantalla(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0, True,
                                            1).render(skin, db.font_id),
             "equipo-lanza")
    una.tocar_cuadros("a", 10)
    assert una.equipo(TALAN)[:2] == [LANZA, 0]
    assert una.item(ESCUDO) == 1, "el escudo no volvió al inventario"
    assert una.item(LANZA) == 0


def test_la_linea_vacia_saca_lo_puesto(partida):
    """La ropa de trabajo de Talan: la lista de la armadura es sólo la línea
    vacía, y elegirla la devuelve al inventario."""
    una = entrar(partida(caso="equipo-inventario"))
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")           # la armadura
    una.tocar_cuadros("a", 10)
    una.tocar_cuadros("a", 10)
    assert una.equipo(TALAN)[2] == 0
    assert una.item(89) == 1


def test_el_equipo_viaja_en_la_partida(partida):
    una = partida(caso="guardar-198")
    una.consola.escribir_ram(una.simbolos["FAR_EQUIPO"] + TALAN * 10,
                             [PALO, 0])
    una.guardar_en(0)
    una.reiniciar()
    assert una.equipo(TALAN)[0] == PALO, "el equipo no volvió de la SRAM"
