"""Las tablas de páginas, del lado de Python: lo que la ROM y la referencia van
a leer igual, así que conviene mirar acá que digan lo que tienen que decir.

No corre ninguna ROM. Es la red para las decisiones de `paginas_del_mapa` que
no cambian un pixel por sí solas pero deciden qué página está activa.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import eventos                                          # noqa: E402
import lcf                                              # noqa: E402
import rm2k                                             # noqa: E402
from render_map import GAME_DIR                         # noqa: E402


def paginas_de(map_id, evento_id):
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    indices = {map_id: 0}
    numero = [n for n, e in enumerate(game_map.events) if e.id == evento_id][0]
    return [p for p in eventos.paginas_del_mapa(game_map, indices.get,
                                                eventos.Mensajes())
            if p["evento"] == numero]


def test_la_pagina_con_item_nunca_esta_activa_y_las_otras_si():
    """EV0041 del mapa 8: tres páginas, la tercera por switches **y por un
    ítem**. El port no tiene inventario, así que esa página no puede estar
    activa nunca; antes eso tiraba el evento entero y el jugador no podía
    hablarle.

    Lo que se mira: la tercera lleva el switch que no se prende y ningún
    código, y las dos primeras llevan su switch y su código. La ROM y la
    referencia leen esta misma tabla, así que con esto alcanza para que las
    dos elijan igual; que la elección se vea la cobra `snes-escena ... ev41`.
    """
    paginas = paginas_de(8, 41)
    assert len(paginas) == 3, "EV0041 tiene tres páginas y la tabla trae %d" \
        % len(paginas)
    primera, segunda, tercera = paginas
    assert primera["switch_a"] == 24 and primera["codigo"]
    assert segunda["switch_a"] == 38 and segunda["codigo"]
    assert tercera["switch_a"] == eventos.SWITCH_IMPOSIBLE
    assert tercera["switch_b"] == 0 and tercera["actor"] == 0
    assert tercera["codigo"] is None and tercera["grafico"] is None


def test_la_condicion_por_variable_va_en_la_pagina():
    """El KeyChest del mapa 133: la primera página pide la variable 123 >= 8,
    la segunda un switch y la tercera un ítem. La tabla lleva la ranura, la
    comparación y el valor de la primera, nada en la segunda, y la tercera
    sigue siendo la que no se activa nunca. Que la ROM elija con eso lo cobra
    `snes-vars 133 ... cofre` en rom/hitos.txt."""
    eventos.indexar_variables(GAME_DIR)
    paginas = paginas_de(133, 2)
    assert len(paginas) == 3
    primera, segunda, tercera = paginas
    assert primera["variable"] == (eventos.ranura_de_variable(123),
                                   eventos.CMP_MAYOR_IGUAL, 8)
    assert segunda["variable"] is None and segunda["switch_a"] == 411
    assert tercera["switch_a"] == eventos.SWITCH_IMPOSIBLE \
        and tercera["variable"] is None
    assert eventos.SWITCH_IMPOSIBLE not in range(1, 1004), (
        "el juego consulta switches hasta el 1003")


def test_las_ranuras_son_las_del_juego_entero():
    """Ochenta y una variables, las mismas ranuras en cualquier ROM: una
    partida guardada con la demo tiene que valer para una ROM con más mapas."""
    ranuras = eventos.indexar_variables(GAME_DIR)
    assert len(ranuras) == 81, len(ranuras)
    assert max(ranuras) == 201
    assert list(ranuras.values()) == list(range(81))
    # Las de la página de prueba se suman al final, sin correr a las demás.
    con_extra = eventos.indexar_variables(GAME_DIR, extra=(3000,))
    assert con_extra[3000] == 81
    assert all(con_extra[v] == r for v, r in ranuras.items())


def test_el_tram_officer_compila_con_las_variables():
    """El Tram Officer del mapa 9 pide variables —azar, resta, los segundos del
    cronómetro, una rama por variable— y un CallEvent que se acepta sin hacer.
    Con las ranuras indexadas compila; sin ellas, no. Las suyas son la 17, la
    21 y de la 39 a la 42."""
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map0009.lmu"))
    del_mapa = eventos.Eventos(game_map)
    oficial = [e for e in game_map.events if e.name == "Tram Officer"][0]
    eventos.VARIABLE_SLOT.clear()
    assert eventos.compilar_pagina(oficial.pages[0], {9: 0}.get,
                                   eventos.Mensajes(),
                                   del_mapa.para(oficial.id)) is None
    ranuras = eventos.indexar_variables(GAME_DIR)
    assert {17, 21, 39, 40, 41, 42} <= set(ranuras), ranuras
    codigo = eventos.compilar_pagina(oficial.pages[0], {9: 0}.get,
                                     eventos.Mensajes(),
                                     del_mapa.para(oficial.id))
    assert codigo is not None and eventos.OP_VAR in codigo \
        and eventos.OP_SI_VAR in codigo
