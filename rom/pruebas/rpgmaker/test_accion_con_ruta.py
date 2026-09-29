"""Con una ruta forzada del héroe viva, la tecla de acción no le habla a nadie.

Es el `IsMoveRouteOverwritten()` de `Game_Player::UpdateNextMovementAction`
(`game_player.cpp:297`), que vuelve antes de mirar el botón. El `IsStopping()`
de más abajo no alcanza: entre dos pasos de una ruta, en un `wait` y en el aire
el héroe no está dando un paso, pero la ruta sigue siendo suya.

Se ve cuando la página termina antes que su ruta. El caño de Lashe City, mapa 8:

    EV0042 (51,22)  capa de abajo, acción: sube. Deja al héroe en el EV0043.
    EV0043 (55,18)  capa de abajo, acción: baja. Su página es **un `MoveEvent`
                    solo**, así que termina en el cuadro en que arranca y el
                    héroe baja el caño sin página. Lo deja en el EV0042.
    EV0052 (52,21)  capa del héroe, acción: sube, encarándolo desde (51,21).

Bajando, en (52,20) mirando abajo entre dos pasos, el EV0052 queda enfrente. Sin
la regla, un A ahí lo dispara y su ruta —pensada para arrancar en (51,21)—
deja al héroe en (56,19), arriba del edificio. taro lo encontró con el
autofire del emulador, que aprieta cada uno o dos cuadros y cae siempre en ese
cuadro; el de la ROM, de cuatro y cuatro, cae según la fase.
"""

import pytest

MAPA = 8
ARRIBA = (55, 18)       # el EV0043, donde el héroe se para para bajar
ABAJO = (51, 22)        # el EV0042, donde lo deja la bajada
LISTO = 24              # el switch de la página 1 del EV0052 y del EV0042

# Índices de la tabla de eventos de la ROM: desde cero, en el orden de ids.
EV0042, EV0043, EV0052 = 41, 42, 51
TOPE = 300              # cuadros; la bajada entera tarda unos ochenta


def arrancados(p, periodo, cuadros):
    """A apretado `periodo` cuadros y suelto otros tantos, cuadro de hardware
    por cuadro. Devuelve la lista de (cuadro, evento, celda del héroe) de cada
    página que arrancó."""
    lista = []
    antes = (p.byte("ev_activo"), p.byte("ev_corriendo"))
    for k in range(cuadros):
        p.consola.hold(*(("a",) if (k // periodo) % 2 == 0 else ()))
        p._un_cuadro()
        ahora = (p.byte("ev_activo"), p.byte("ev_corriendo"))
        # Una página de un solo `MoveEvent` arranca y termina en el mismo
        # cuadro, así que `ev_activo` no llega a verse prendido: lo que queda
        # es `ev_corriendo`, que dice cuál fue la última.
        if ahora[1] != antes[1] or (ahora[0] and not antes[0]):
            lista.append((k, ahora[1], p.heroe()))
        antes = ahora
    p.soltar()
    return lista


@pytest.mark.parametrize("periodo", [1, 2, 4])
def test_bajando_el_cano_la_a_no_dispara_el_de_enfrente(partida, periodo):
    una = partida(switch=[LISTO])
    una.ir_al_mapa(MAPA, *ARRIBA)
    una.correr(20)
    assert una.evento(EV0052) == (52, 21) and una.evento(EV0043) == ARRIBA, \
        "la tabla de eventos del mapa 8 no es la que esta prueba supone"
    lista = arrancados(una, periodo, TOPE)
    assert lista and lista[0][1] == EV0043, \
        "el primer A no disparó la bajada: %s" % lista
    # Lo que arranca después de la bajada tiene que ser el EV0042, y recién
    # en su celda: terminada la ruta el héroe está parado encima, es de otra
    # capa y de acción, así que el A siguiente lo sube otra vez —en RM2k
    # también: es `CheckEventTriggerHere`—. Eso es la otra mitad de la
    # prueba: una regla que se tragara la A para siempre pasaría la primera.
    assert len(lista) > 1, (
        "terminada la bajada, en %s sobre el EV0042, la A no disparó nada"
        % (ABAJO,))
    assert lista[1][1:] == (EV0042, ABAJO), (
        "con la ruta de la bajada todavía viva la A disparó el evento de "
        "índice %d con el héroe en %s. En RM2k `IsMoveRouteOverwritten` no "
        "deja mirar el botón: %s" % (lista[1][1], lista[1][2], lista))
