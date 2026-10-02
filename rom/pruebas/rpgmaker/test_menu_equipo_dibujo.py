"""El equipo: a quién equipar, sobre el menú mismo, y la pantalla de
`Scene_Equip`, pixel por pixel contra `pantallas.menu` y `pantallas.equipo`,
y lo que equipar cambia en la RAM.

El inventario lo da la página de prueba con `ChangeItems` de verdad. Talan
arranca con su ropa de trabajo, que es el equipo inicial del LDB copiado a
`FAR_EQUIPMENT` en el reset.
"""

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla
from menu import GRUPO, abrir, comparar, con_grupo
import pantallas

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


def test_a_quien_equipar_se_elige_en_el_menu(partida):
    """`Scene_Menu` con Equipment: A deja el menú como está, con el cursor
    en la orden, y pone la barra sobre el primero del grupo; abajo la pasa
    al segundo, arriba desde el primero da la vuelta, B vuelve a las
    órdenes sin barra, y A abre el equipo del de la barra. Al volver del
    equipo, el cursor está en las órdenes, sobre Equipment. Lo mismo en el
    RPG_RT, capturado con Wine: ver la tarea `a-quien-equipar-desde-el-menu`.
    """
    una = con_grupo(partida())
    abrir(una)
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)
    comparar(una, 2, nombre="menu-a-quien", eligiendo=0)
    una.tocar_cuadros("down")
    comparar(una, 2, nombre="menu-a-quien-2", eligiendo=1)
    una.tocar_cuadros("up")
    una.tocar_cuadros("up")             # desde el primero, da la vuelta
    comparar(una, 2, nombre="menu-a-quien-vuelta", eligiendo=1)
    una.tocar_cuadros("b", TITULO_AIRE)
    comparar(una, 2, nombre="menu-a-quien-b")
    assert una.menu_abierto(), "B en la elección cerró el menú"
    una.tocar_cuadros("a", TITULO_AIRE)  # arranca otra vez en el primero
    comparar(una, 2, nombre="menu-a-quien-otra-vez", eligiendo=0)
    una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)  # el segundo: Kersh
    assert una.byte("comp_char") == GRUPO[1], "el equipo no es del segundo"
    comparar_pantalla(una, pantallas.equipo(
        GRUPO[1], datos.base().actors[GRUPO[1]].initial_equipment, {}, 0),
        "equipo-del-segundo")
    una.tocar_cuadros("b", TITULO_AIRE)
    comparar(una, 2, nombre="menu-vuelta-del-equipo")


def test_arranca_con_el_equipo_inicial(partida):
    una = partida()
    db = datos.base()
    assert una.equipo(TALAN) == db.actors[TALAN].initial_equipment
    assert una.equipo(KERSH) == db.actors[KERSH].initial_equipment


def test_equipar_desde_el_menu(partida):
    """Las ranuras de Talan, la lista del arma con los parámetros que
    quedarían, y el palo puesto: sale del inventario y queda en la RAM."""
    db = datos.base()
    una = entrar(partida(caso="equipo-inventario"))
    puesto = list(db.actors[TALAN].initial_equipment)
    inv = dict(INVENTARIO)
    comparar_pantalla(una, pantallas.equipo(TALAN, puesto, inv, 0), "equipo")
    una.tocar_cuadros("a", 10)
    comparar_pantalla(una, pantallas.equipo(TALAN, puesto, inv, 0, True, 0),
                      "equipo-lista")
    una.tocar_cuadros("a", 10)          # el palo
    pantallas.equipar(puesto, inv, 0, PALO)
    assert una.equipo(TALAN) == puesto
    assert una.item(PALO) == 1
    comparar_pantalla(una, pantallas.equipo(TALAN, puesto, inv, 0),
                      "equipo-puesto")


def test_la_lanza_a_dos_manos_saca_el_escudo(partida):
    """Con el escudo puesto, ponerse la lanza lo devuelve al inventario."""
    db = datos.base()
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
    comparar_pantalla(una, pantallas.equipo(TALAN, puesto, inv, 0, True, 1),
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
    una.consola.write_ram(una.simbolos["FAR_EQUIPMENT"] + TALAN * 10,
                          [PALO, 0])
    una.guardar_en(0)
    una.reiniciar()
    assert una.equipo(TALAN)[0] == PALO, "el equipo no volvió de la SRAM"
