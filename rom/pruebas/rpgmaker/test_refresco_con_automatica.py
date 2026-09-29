"""El refresco completo, con una automática corriendo, mira todas las páginas.

`pick_with_filter` hace las dos pasadas del refresco: la corta, que mira sólo
los eventos con automáticas, y la completa, que mira además los que tienen ruta
propia o gráfico por página. Decidía cuál era con un `ldx solo_auto` con X en
16 bits, que se llevaba también `auto_n`, el byte de al lado. Con alguna
automática activa `auto_n` no es cero, así que la completa filtraba como la
corta, y los eventos sin automáticas no elegían página mientras la automática
durara.

taro lo vio en la huida del techo: después de elegir el auto, la cinemática del
mapa 4 —la página 4 de `EV0001`, una automática— corría con la pantalla negra, y
en RM2k el auto está. Nació con el refresco partido, en `348cf58`.
"""


def test_el_auto_elegido_aparece_en_la_huida(partida):
    """Los autos son los eventos 2 y 3 del mapa 4: el rojo en la celda (9,7)
    pide los switches 130 y 132, el azul en la (10,7) 131 y 132, y el 132 es
    también el que arranca la cinemática. Con el rojo elegido, el rojo se ve y
    el azul no.

    Las filas se buscan por la X —el byte +0 de `npc_buf`, en pixeles— porque
    el conversor no las ordena como los eventos. El +14 es si se dibuja. Sin
    el arreglo las dos quedan en cero, y `eleg_por_ev` de los dos eventos en
    $FFFF: ninguna pasada miró sus páginas.
    """
    una = partida(switch=[130, 132], caso="en-4")
    una.correr(30)
    filas = una.consola.ram(una.simbolos["npc_buf"],
                            2 * una.simbolos["NPC_STRIDE"])
    paso = una.simbolos["NPC_STRIDE"]
    visible = {filas[k * paso] | filas[k * paso + 1] << 8: filas[k * paso + 14]
               for k in range(2)}
    assert una.mapa() == 4
    assert una.corriendo_una_pagina()       # la cinemática, que es la automática
    assert visible == {9 * 16: 1, 10 * 16: 0}
