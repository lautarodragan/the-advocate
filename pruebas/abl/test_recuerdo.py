"""El recuerdo de CORE y MANTA, sin mirar la pantalla.

El caso `manta` de `pruebas/test_tanda*.py` compara esta misma escena pixel por pixel
contra la referencia, en ocho cuadros elegidos a mano esquivando la animación
de la ventana de mensaje. Esto pregunta otra cosa, más chica y más directa: si
la partida **llegó** a donde tenía que llegar.

Vale la pena tener las dos. El bug que taro encontró jugando el 2026-09-06 —el
recuerdo que no arrancaba— se veía en una línea acá; en la tanda de pixeles no
se veía en ninguna parte, porque la referencia tenía el mismo error y los dos
lados no hacían nada.
"""

# Los cuadros en que hay que apretar A para que la escena avance sola. Salieron
# de correr la referencia e ir agregando un toque treinta cuadros después de
# cada mensaje que la frena; ver `ESTADO.md`, "los primeros veinte cuadros de un
# mensaje". Es la misma lista que usa el caso `manta`.
TOQUES = [212, 243, 394, 515, 727, 758, 789, 820, 971, 1517, 1548, 1699, 1790,
          1911, 1942, 2033, 2125, 2156, 2247, 2338, 2399, 2460, 2570, 2674,
          2987, 3018, 3079, 3110, 3141, 3214, 3510, 3541, 3723, 3826]


def test_el_recuerdo_arranca(partida):
    """La página del recuerdo pide el switch 16 y arranca sola al entrar."""
    una = partida(switch=[16])
    una.correr(400, apretar_a=TOQUES)
    assert una.corriendo_una_pagina(), \
        "la página automática del mapa 5 nunca arrancó"


def test_el_recuerdo_cruza_a_la_ciudad(partida):
    """De la casa a la isla: la mitad que estuvo muerta hasta el 2026-09-06.

    El mapa 5 salta primero dentro de sí mismo y después al 6, y **prende el
    switch 17 recién después de aterrizar**. Que el 6 arranque su cinemática
    depende de que una página automática que se vuelve activa con el mapa ya
    cargado dispare igual; mientras eso no funcionó, acá se quedaba en el 5.
    """
    una = partida(switch=[16])
    una.correr(3900, apretar_a=TOQUES)
    assert una.mapa() == 6
    assert una.switch(17), "el recuerdo del mapa 6 no se destrabó"
    assert not una.switch(16), "el 16 tenía que apagarse al empezar la escena"
