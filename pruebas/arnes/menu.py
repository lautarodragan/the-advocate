"""El menú de pausa, manejado desde afuera: abrirlo y tocarle botones.

Lo usan las pruebas de todo lo que se abre desde el menú —ítems, equipo,
curar, guardar— y la de la tienda, que es otra pantalla con el mismo reloj.

**Todo en cuadros de hardware**: mientras el menú está abierto `vueltas` no
avanza, así que `Partida.correr` esperaría un tick que no llega.
"""

# El grupo y el oro con que se abre el menú en las pruebas que lo comparan
# contra `titulo.render_menu`: tienen que ser los mismos de los dos lados.
GRUPO = (14, 11)
ORO = 1234


def tocar(una, boton, cuadros=4):
    """Un toque en cuadros de hardware: el menú no cuenta ticks.

    Dos cuadros apretado, uno suelto y `cuadros` de aire. No es
    `Partida.tocar`, que cuenta en ticks, ni `Pelea.tocar`, que deja
    apretado lo mismo que deja de aire: son tres relojes para tres pantallas,
    y las pruebas que usan cada uno están afinadas a él.
    """
    una.consola.apretar(boton)
    una.consola.correr(2)
    una.consola.apretar()
    una.consola.correr(cuadros)


def abrir(una, tope=60):
    """B, y los cuadros que haga falta hasta que el menú esté a la vista."""
    tocar(una, "b", 0)
    for _ in range(tope):
        if una.menu_abierto():
            una.consola.correr(3)
            return una
        una.consola.correr(1)
    raise AssertionError("B no abrió el menú en %d cuadros" % tope)


def con_grupo(una):
    """La partida con `GRUPO` y `ORO` escritos en la RAM."""
    una.correr(5)
    una.poner_grupo(*GRUPO)
    una.poner_oro(ORO)
    return una
