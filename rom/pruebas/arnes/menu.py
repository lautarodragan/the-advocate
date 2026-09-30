"""El menú de pausa, manejado desde afuera: abrirlo y tocarle botones.

Lo usan las pruebas de todo lo que se abre desde el menú —ítems, equipo,
curar, guardar— y la de la tienda, que es otra pantalla con el mismo reloj.

**Todo en cuadros de hardware**: mientras el menú está abierto `ticks` no
avanza, así que `Partida.correr` esperaría un tick que no llega. Los toques son
`Partida.tocar_cuadros`, y no `Partida.tocar_ticks`, por lo mismo.
"""

from dibujo import comparar_pantalla
import pantallas

# El grupo y el oro con que se abre el menú en las pruebas que lo comparan
# contra `pantallas.menu`: tienen que ser los mismos de los dos lados.
GRUPO = (14, 11)
ORO = 1234


def abrir(una, tope=60):
    """B, y los cuadros que haga falta hasta que el menú esté a la vista."""
    una.tocar_cuadros("b", 0)
    for _ in range(tope):
        if una.menu_abierto():
            una.consola.run(3)
            return una
        una.consola.run(1)
    raise AssertionError("B no abrió el menú en %d cuadros" % tope)


def con_grupo(una):
    """La partida con `GRUPO` y `ORO` escritos en la RAM."""
    una.correr(5)
    una.poner_grupo(*GRUPO)
    una.poner_oro(ORO)
    return una


def comparar(una, elegida, guardar=True, nombre="menu", hp=None):
    """El menú en pantalla contra `pantallas.menu` con `GRUPO` y `ORO`,
    y el cursor en `elegida`. Vivía en `test_menu_dibujo.py` hasta el
    2026-09-29; lo usa también End Game, que vuelve al menú."""
    esperada = pantallas.menu(una.simbolos["SRAM_SLOTS"], GRUPO, ORO,
                              elegida, guardar, hp=hp)
    comparar_pantalla(una, esperada, nombre,
                      "el menú con el cursor en la %d" % elegida)
