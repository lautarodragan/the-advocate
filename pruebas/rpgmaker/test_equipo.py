"""El equipo: la pantalla de `Scene_Equip` desde el menú, pixel por pixel
contra `pantallas.pantalla_equipo`, y lo que equipar cambia en la RAM.

El inventario lo da la página de prueba con `ChangeItems` de verdad. Talan
arranca con su ropa de trabajo, que es el equipo inicial del LDB copiado a
`FAR_EQUIPO` en el reset.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
import pantallas                                        # noqa: E402

from consola import TITULO_AIRE
from test_menu import abrir, tocar

TALAN, KERSH = 14, 11
PALO, LANZA, ESCUDO = 17, 19, 44        # la lanza es a dos manos
# Lo que da la página de prueba `equipo-inventario`: tiene que decir lo mismo.
INVENTARIO = {PALO: 2, LANZA: 1, ESCUDO: 1}


def items_de(inventario):
    return tuple(x for par in sorted(inventario.items()) for x in par)


def db_y_skin():
    import lcf
    import ventana
    from render_map import GAME_DIR
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    return db, ventana.skin(GAME_DIR, db.system_name)


def equipo(una, actor):
    base = una.simbolos["FAR_EQUIPO"] + actor * 10
    datos = una.consola.ram(base, 10)
    return [datos[2 * r] | (datos[2 * r + 1] << 8) for r in range(5)]


def entrar(una):
    """Del mapa a la pantalla de equipo de Talan: B, Equipment, y A sobre la
    primera fila del grupo."""
    una.correr(5)
    una.poner_grupo(TALAN, KERSH)
    una.correr(25)
    abrir(una)
    tocar(una, "down")
    tocar(una, "down")
    tocar(una, "a", TITULO_AIRE)        # a quién
    tocar(una, "a", TITULO_AIRE)        # Talan
    return una


def comparar(una, esperada, nombre):
    from tanda import quince_bits
    captura = una.imagen().convert("RGB")
    distintos = sum(1 for x, y in zip(quince_bits(captura), quince_bits(esperada))
                    if x != y)
    if distintos:
        donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "rom", "shots")
        os.makedirs(donde, exist_ok=True)
        captura.save(os.path.join(donde, "prueba-%s.png" % nombre))
        esperada.save(os.path.join(donde, "prueba-%s.esperado.png" % nombre))
    assert distintos == 0, (
        "%s difiere de la referencia en %d pixeles; están en "
        "rom/shots/prueba-%s*.png" % (nombre, distintos, nombre))


def test_arranca_con_el_equipo_inicial(partida):
    una = partida()
    db, _ = db_y_skin()
    assert equipo(una, TALAN) == db.actors[TALAN].initial_equipment
    assert equipo(una, KERSH) == db.actors[KERSH].initial_equipment


def test_equipar_desde_el_menu(partida):
    """Las ranuras de Talan, la lista del arma con los parámetros que
    quedarían, y el palo puesto: sale del inventario y queda en la RAM."""
    db, skin = db_y_skin()
    una = entrar(partida(caso="equipo-inventario"))
    puesto = list(db.actors[TALAN].initial_equipment)
    inv = dict(INVENTARIO)
    comparar(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0)
             .render(skin, db.font_id), "equipo")
    tocar(una, "a", 10)
    comparar(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0, True,
                                            0).render(skin, db.font_id),
             "equipo-lista")
    tocar(una, "a", 10)                 # el palo
    pantallas.equipar(db, puesto, inv, 0, PALO)
    assert equipo(una, TALAN) == puesto
    assert una.item(PALO) == 1
    comparar(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0)
             .render(skin, db.font_id), "equipo-puesto")


def test_la_lanza_a_dos_manos_saca_el_escudo(partida):
    """Con el escudo puesto, ponerse la lanza lo devuelve al inventario."""
    db, skin = db_y_skin()
    una = entrar(partida(caso="equipo-inventario"))
    tocar(una, "down")                  # el escudo
    tocar(una, "a", 10)
    tocar(una, "a", 10)                 # el escudo, único en la lista
    assert equipo(una, TALAN)[1] == ESCUDO
    assert una.item(ESCUDO) == 0
    tocar(una, "up")                    # el arma
    tocar(una, "a", 10)
    tocar(una, "down")                  # la lanza, segunda en la lista
    puesto = list(db.actors[TALAN].initial_equipment)
    puesto[1] = ESCUDO
    inv = dict(INVENTARIO)
    inv[ESCUDO] = 0
    comparar(una, pantallas.pantalla_equipo(db, TALAN, puesto, inv, 0, True,
                                            1).render(skin, db.font_id),
             "equipo-lanza")
    tocar(una, "a", 10)
    assert equipo(una, TALAN)[:2] == [LANZA, 0]
    assert una.item(ESCUDO) == 1, "el escudo no volvió al inventario"
    assert una.item(LANZA) == 0


def test_la_linea_vacia_saca_lo_puesto(partida):
    """La ropa de trabajo de Talan: la lista de la armadura es sólo la línea
    vacía, y elegirla la devuelve al inventario."""
    una = entrar(partida(caso="equipo-inventario"))
    tocar(una, "down")
    tocar(una, "down")                  # la armadura
    tocar(una, "a", 10)
    tocar(una, "a", 10)
    assert equipo(una, TALAN)[2] == 0
    assert una.item(89) == 1


def test_el_equipo_viaja_en_la_partida(partida):
    una = partida(caso="guardar-198")
    una.consola.escribir_ram(una.simbolos["FAR_EQUIPO"] + TALAN * 10,
                             [PALO, 0])
    una.guardar_en(0)
    una.reiniciar()
    assert equipo(una, TALAN)[0] == PALO, "el equipo no volvió de la SRAM"
