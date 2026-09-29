"""El presupuesto de teletransportes encadenados: que se reponga, y que no se
gaste en silencio.

`saltos_restantes` existe para que dos mapas que se teletransporten entre sí no
cuelguen a la consola. Lo que cuenta son los saltos **encadenados**, o sea los
que pasan sin que el jugador recupere el control; los de una partida son todos
los que quieran ser.

Estaba mal de las dos maneras posibles. Sólo lo reponía `cargar_mapa`, y a un
comando `Teleport` lo atiende `cargar_mapa_sin_eventos`: el presupuesto se
gastaba para toda la partida. Y cuando se acababa, el salto se **descartaba**
sin decir nada, así que el juego seguía andando en el mapa equivocado.

taro lo encontró jugando el 2026-09-07: llegaba al despachante del mapa 4 —que
es un mapa vacío a propósito, "Blank (Leave START here)"— y su página automática
no lograba sacarlo de ahí. Como la página es automática y su switch sigue
prendido, volvía a arrancar sola en ciclo: pantalla sin nada más que el héroe,
sin control, y `hzstream` fundiéndose y volviendo a empezar.
"""


def test_el_presupuesto_vuelve_cuando_el_jugador_tiene_el_control(partida):
    """La cadena termina cuando el jugador puede moverse, y ahí se repone."""
    una = partida()
    for _ in range(3000):
        una.correr(1)
        if not una.corriendo_una_pagina() and not una.byte("esperando_n"):
            break
    else:
        raise AssertionError("la partida nunca soltó el control")
    una.poner_byte("saltos_restantes", 0)
    una.correr(1)
    assert una.byte("saltos_restantes") == una.simbolos["SALTOS_MAX"], \
        "el presupuesto no se repuso con el jugador en control: una partida " \
        "larga se queda sin teletransportes"


def test_el_despachante_del_mapa_4_saca_de_ahi(partida):
    """El caso de taro, entero: entrar al mapa 4 con el 21 prendido y salir.

    El mapa 4 es "Blank (Leave START here)", un mapa vacío a propósito cuyo
    evento 1 tiene cinco páginas automáticas, una por switch, cada una
    teletransportando a otro lado; la del 21 va al pad de Talan. Es el
    despachante al que la escena del escape devuelve al jugador.

    Si ese teletransporte se pierde, la página termina, el 21 sigue prendido y
    —siendo automática— vuelve a arrancar sola: el jugador queda encerrado en un
    mapa sin nada que dibujar, sin control, con la música fundiéndose y
    empezando de nuevo en ciclo. Es lo que taro reportó el 2026-09-07.

    Este caso no falla por sí solo con el presupuesto roto —entra por una
    puerta, que lo repone—: lo que cubre es que el camino exista y termine
    donde tiene que terminar. El que agarra el presupuesto es el de arriba.
    """
    una = partida(switch=[21])
    una.ir_al_mapa(4, 11, 9)
    for _ in range(1200):
        una.correr(1)
        if una.mapa() == 7:
            break
    else:
        raise AssertionError(
            "el despachante no sacó del mapa 4: quedó en el %d" % una.mapa())


def test_nadie_entra_en_panico(partida):
    """El tope no se alcanza jugando. Si esto falla, la ROM se paró sola."""
    una = partida()
    una.correr(600)
    assert not una.byte("panico"), \
        "la ROM entró en pánico con el código %d" % una.byte("panico")
