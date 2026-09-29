"""Una puerta al mismo mapa no recarga el mapa.

Recargar vuelve a leer del cartucho las posiciones de los eventos, y con eso se
pierde todo lo que los haya movido —un `ChangeEventLocation`, un
`TradeEventLocations`— aunque el jugador nunca haya salido del mapa. Es el
`map_changed` de `Game_Player::PerformTeleport`: sin cambio de mapa no hay
`Setup`.

El banco es la puerta de arriba a la izquierda del mapa 2, que taro reportó el
2026-09-07. Abrirla hace tres cosas: prende el switch 5, truequea el
`LBDoorBottom` (evento 2) con el `MovinDoor` (evento 21) —que es el hueco negro—
y **manda el `LBDoorTop` (evento 5) a (94,97)**, que es lo que hace desaparecer
las franjas amarillas de arriba.

Los dos cuartos que uno percibe como mapas distintos son el mismo mapa 2,
separados lo suficiente como para que jugando no se note; se cruzan con
teletransportes internos. El de ida sale de un `Teleport` y andaba: `hubo_salto`
comparaba con `mapa_actual`. El de vuelta es una **puerta** —el evento 20, una
página de contacto cuyo único comando es el teletransporte— y ése recargaba
siempre. Al volver, las franjas reaparecían.
"""

from tanda import LINKAGE

MAPA = 2
PUERTA_X, PUERTA_Y = 4, 54      # la celda de abajo de la puerta
EV_TOP, EV_BOTTOM, EV_MOVIN = 4, 1, 20      # índices, desde cero
LEJOS = (94, 97)                # a donde va el `LBDoorTop` al abrirse


def caminar(una, tecla, destino, vueltas=80):
    """Camina apretando `tecla` hasta llegar, pasando los mensajes con A."""
    for _ in range(vueltas):
        if una.heroe() == destino:
            return True
        una.consola.apretar(tecla)
        una.consola.correr(8)
        una.cuadro += 8
        una.consola.apretar()
        una.consola.correr(2)
        una.cuadro += 2
        if una.byte("msg_abierto"):
            una.tocar_ticks("a")
    return una.heroe() == destino


def abierta(partida):
    """Una partida con la puerta ya abierta, parada delante de ella."""
    una = partida(caso=LINKAGE)
    una.ir_al_mapa(MAPA, PUERTA_X, PUERTA_Y)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    for _ in range(40):
        if una.switch(5):
            break
        una.tocar_ticks("a")
        for _ in range(60):
            if una.byte("msg_abierto"):
                break
            una.correr(1)
    else:
        raise AssertionError("no se abrió la puerta")
    return una


def test_abrirla_mueve_los_eventos(partida):
    """Primero lo que tiene que pasar al abrirla, o el resto no prueba nada."""
    una = abierta(partida)
    assert una.evento(EV_TOP) == LEJOS, \
        "el `LBDoorTop` no se fue: las franjas de arriba no desaparecen"
    assert una.evento(EV_MOVIN) == (PUERTA_X, PUERTA_Y - 1), \
        "el `MovinDoor` no vino a la puerta"


def test_cruzarla_y_volver_la_deja_abierta(partida):
    """El caso de taro, entero."""
    una = abierta(partida)
    assert caminar(una, "up", (87, 88)), "no se pudo cruzar la puerta"
    assert una.evento(EV_TOP) == LEJOS, \
        "cruzar ya resetea los eventos; el `Teleport` de ida debería conservarlos"
    assert caminar(una, "down", (PUERTA_X, PUERTA_Y)), "no se pudo volver"
    assert una.evento(EV_TOP) == LEJOS, \
        "volver por la puerta recargó el mapa: el `LBDoorTop` volvió a %s y la " \
        "puerta se ve a medio abrir" % (una.evento(EV_TOP),)
