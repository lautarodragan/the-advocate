"""Las tablas de páginas, del lado de Python: lo que la ROM va a leer, así que
conviene mirar acá que digan lo que tienen que decir.

No corre ninguna ROM. Es la red para las decisiones de `map_pages` que
no cambian un pixel por sí solas pero deciden qué página está activa.
"""

import os
import re

from port import events
from port import snes_convert
from rpgmaker import lcf
from rpgmaker import rm2k
from rpgmaker.resources import GAME_DIR


def paginas_de(map_id, evento_id):
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    indices = {map_id: 0}
    numero = [n for n, e in enumerate(game_map.events) if e.id == evento_id][0]
    return [p for p in events.map_pages(game_map, indices.get,
                                        events.Messages())
            if p["evento"] == numero]


def test_la_pagina_con_item_lleva_el_item():
    """EV0041 del mapa 8: tres páginas, la tercera por switches **y por un
    ítem**, el 90. La tabla lleva el ítem y la ROM mira su cuenta en
    `FAR_ITEMS`. Que una elección por ítem se vea la cobra `cofre-llave` en
    `test_comandos_golden.py`.
    """
    paginas = paginas_de(8, 41)
    assert len(paginas) == 3, "EV0041 tiene tres páginas y la tabla trae %d" \
        % len(paginas)
    primera, segunda, tercera = paginas
    assert primera["switch_a"] == 24 and primera["codigo"] and not primera["item"]
    assert segunda["switch_a"] == 38 and segunda["codigo"] and not segunda["item"]
    assert tercera["switch_a"] == 53 and tercera["switch_b"] == 37
    assert tercera["item"] == 90
    assert tercera["codigo"], "la tercera compila: un mensaje y un MoveEvent"


def test_la_condicion_por_variable_va_en_la_pagina():
    """El KeyChest del mapa 133: la primera página pide la variable 123 >= 8,
    la segunda un switch y la tercera un ítem. La tabla lleva la ranura, la
    comparación y el valor de la primera, nada en la segunda, y el ítem en la
    tercera. Que la ROM elija con eso lo cobran `cofre` y `cofre-llave` en
    `test_comandos_golden.py`."""
    events.index_variables(GAME_DIR)
    paginas = paginas_de(133, 2)
    assert len(paginas) == 3
    primera, segunda, tercera = paginas
    assert primera["variable"] == (events.variable_slot(123),
                                   events.CMP_GREATER_EQUAL, 8)
    assert segunda["variable"] is None and segunda["switch_a"] == 411
    assert tercera["item"] == 151 and tercera["variable"] is None \
        and tercera["switch_a"] == 0
    assert events.SWITCH_IMPOSSIBLE not in range(1, 1004), (
        "el juego consulta switches hasta el 1003")


def test_las_ranuras_son_las_del_juego_entero():
    """Las mismas ranuras en cualquier ROM: una partida guardada con la demo
    tiene que valer para una ROM con más mapas.

    Eran 81 hasta el 2026-09-13: `variables_named` no miraba el `KeyInputProc`,
    que es el único comando de este juego que le escribe a una variable sin ser
    un `ControlVars`. Las dos que aparecieron son la 5 —el motor del minijuego
    de las piedras del mapa 11— y la 151, y a ninguna de las dos la nombra
    nadie más, así que sin esto sus tres páginas no compilaban por un motivo
    que no tenía nada que ver con el comando.

    Y desde el 2026-09-21 son 123: el índice mira también las páginas de las
    tropas, que corren en la pelea, y los sistemas de batalla de los personajes
    suman cuarenta variables que ningún mapa nombra —la 81 y la 106 de Talan
    cuentan cuántas veces absorbió cada técnica—. Ver `variables_named`.

    Y desde el 2026-09-27 son 132: `MemorizeLocation` y `RecallToLocation`
    nombran nueve que nadie más nombra —127 a 129, 158 a 160 y 169 a 171—, y
    con eso la ranura dejó de caber en siete bits: ver VAR_SLOT_MAX.

    Las cuatro de arriba de la 204 son nuestras y no del juego: las usa el
    evento paralelo que reemplazó a las 52 baldosas de luz del mapa 11 —ver
    `parches/manual/README.md`—. Están elegidas **por encima de la más alta que
    el juego nombra** justamente para que no le corran la ranura a ninguna: una
    partida guardada antes del rediseño sigue leyendo las mismas.
    """
    ranuras = events.index_variables(GAME_DIR)
    assert list(ranuras.values()) == list(range(len(ranuras)))
    assert 5 in ranuras and 151 in ranuras
    del_juego = [v for v in ranuras if v <= 204]
    assert len(del_juego) == 132, del_juego
    assert {127, 128, 129, 158, 159, 160, 169, 170, 171} <= set(del_juego)
    assert max(del_juego) == 201
    assert all(ranuras[v] == r for r, v in enumerate(sorted(del_juego)))
    # Las de la página de prueba se suman al final, sin correr a las demás.
    con_extra = events.index_variables(GAME_DIR, extra=(3000,))
    assert con_extra[3000] == len(ranuras)
    assert all(con_extra[v] == r for v, r in ranuras.items())


def test_el_tram_officer_compila_con_las_variables():
    """El Tram Officer del mapa 9 pide variables —azar, resta, los segundos del
    cronómetro, una rama por variable— y un CallEvent que se acepta sin hacer.
    Con las ranuras indexadas compila; sin ellas, no. Las suyas son la 17, la
    21 y de la 39 a la 42."""
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map0009.lmu"))
    del_mapa = events.MapEvents(game_map)
    oficial = [e for e in game_map.events if e.name == "Tram Officer"][0]
    # Vaciar el índice es global a todo el proceso: se repone aunque la
    # aserción falle, o la prueba que corra después en este proceso compila
    # sin variables.
    antes = dict(events.VARIABLE_SLOT)
    events.VARIABLE_SLOT.clear()
    try:
        assert events.compile_page(oficial.pages[0], {9: 0}.get,
                                   events.Messages(),
                                   del_mapa.for_event(oficial.id)) is None
    finally:
        events.VARIABLE_SLOT.update(antes)
    ranuras = events.index_variables(GAME_DIR)
    assert {17, 21, 39, 40, 41, 42} <= set(ranuras), ranuras
    codigo = events.compile_page(oficial.pages[0], {9: 0}.get,
                                 events.Messages(),
                                 del_mapa.for_event(oficial.id))
    assert codigo is not None and events.OP_VAR in codigo \
        and events.OP_IF_VAR in codigo


def _escritura_de_la_123(comandos, desde):
    """Compila `comandos` como una página del mapa `desde` y devuelve el byte
    de la operación del `OP_VAR` que escribe la variable 123, que es el que
    lleva el bit del refresco."""
    events.index_variables(GAME_DIR)
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % desde))
    codigo = events.compile_page(
        events._Commands(comandos), {desde: 0, 133: 1}.get,
        events.Messages(), events.MapEvents(game_map).for_event(0))
    assert codigo is not None, "la página no compila"
    operaciones = [c[i + 2] for i, c in events.walk_code(codigo)
                   if c[i] == events.OP_VAR]
    assert len(operaciones) == 1
    return operaciones[0]


def _comandos(*crudos):
    return [lcf.EventCommand(codigo, 0, "", list(p)) for codigo, p in crudos]


PONER_123_EN_8 = (events.CONTROL_VARS, (0, 123, 123, 0, 0, 8, 0))


def test_la_escritura_despues_de_saltar_a_otro_mapa_pide_refresco():
    """Una página que salta a otro mapa sigue corriendo allá, así que lo que
    escribe después lo miran las páginas **del destino**. El refresco se
    decide al compilar, con las variables que miran las páginas del mapa de la
    página, y el mapa de la página ya no es donde corre: la escritura tiene
    que pedirlo siempre, que es lo que se hace cuando no se sabe quién mira.

    Es el cofre del mapa 133 —su primera página pide la variable 123 >= 8—
    que en la medición del 9e no aparecía después de un `Teleport` desde el
    mapa 6 aunque la variable ya valía 8: el 6 no mira la 123.
    """
    operacion = _escritura_de_la_123(_comandos(
        (events.TELEPORT, (133, 4, 7)), PONER_123_EN_8), desde=6)
    assert operacion & events.VAR_REFRESH, \
        "después de saltar al 133 la escritura a la 123 no pide refresco"


def test_sin_saltar_la_escritura_mira_las_variables_del_mapa():
    """El control del anterior: en el mapa 6, que no mira la 123, escribirla
    no pide refresco; en el 133, que sí, lo pide. Y un salto **al mismo**
    mapa no cambia quién mira."""
    assert not _escritura_de_la_123(_comandos(PONER_123_EN_8), desde=6) \
        & events.VAR_REFRESH
    assert _escritura_de_la_123(_comandos(PONER_123_EN_8), desde=133) \
        & events.VAR_REFRESH
    assert not _escritura_de_la_123(_comandos(
        (events.TELEPORT, (6, 22, 12)), PONER_123_EN_8), desde=6) \
        & events.VAR_REFRESH


def test_la_ruta_propia_apunta_al_bloque_que_recibe():
    """Una página con ruta propia lleva dos punteros adentro del código de
    eventos del mapa —+8 su código, +16 las órdenes de su ruta— y los dos
    tienen que salir de la etiqueta que `page_table` recibe, no del
    número del mapa. La etiqueta la pone `Materials`, que numera por clase y
    comparte los bloques iguales: con un bloque de código compartido antes
    que el de este mapa, `evcodigo_<mapa>` es el de **otro** mapa, o no
    existe y `ca65` se cae con "Symbol 'evcodigo_82' is undefined".

    El +16 rearmaba el nombre hasta el 2026-09-27: la deduplicación del
    2026-09-07 arregló el +8 y no lo vio, porque ningún cartucho tenía un
    bloque de código compartido antes de un mapa con rutas propias. Lo
    destapó un `release` con los mapas hasta el 85. No corre ninguna ROM: la
    tabla es texto, y lo que importa es a qué símbolo nombra.
    """
    pagina = {
        "evento": 0, "pagina": 1, "trigger": events.TRIGGER_PARALLEL,
        "switch_a": 0, "switch_b": 0, "actor": 0, "capa": 1, "item": 0,
        "codigo": b"\x00", "offset": 0, "ruta_offset": 1,
        "frecuencia": 3, "velocidad": 4,
        "ruta_propia": {"repite": True, "saltable": False, "dir_fija": False,
                        "anim_continua": False, "frecuencia": 3,
                        "velocidad": 4, "ordenes": [0]},
    }
    tabla = snes_convert.page_table({"paginas": [pagina]}, 7,
                                    "evcodigo_3")
    nombrados = set(re.findall(r"evcodigo_\d+", tabla))
    assert nombrados == {"evcodigo_3"}, (
        "la tabla del mapa 7, cuyo código es el bloque evcodigo_3, nombra %s"
        % sorted(nombrados))


# "¿Está el héroe en la celda de las variables 34 y 35?", como lo escriben las
# páginas paralelas de RM2k: la y y la x del héroe a la 36 y la 37, y dos
# ramas anidadas que las comparan con la 34 y la 35. Es la forma de los
# cuarenta autos de cada vuelta de la carrera, con el héroe de blanco.
def _celda(*cuerpo):
    comandos = [
        lcf.EventCommand(events.CONTROL_VARS, 0, "",
                         [0, 36, 36, events.VAR_SET, events.VAR_CHARACTER,
                          events.ROUTE_HERO, events.CHARACTER_Y]),
        lcf.EventCommand(events.CONTROL_VARS, 0, "",
                         [0, 37, 37, events.VAR_SET, events.VAR_CHARACTER,
                          events.ROUTE_HERO, events.CHARACTER_X]),
        lcf.EventCommand(events.COND_BRANCH, 0, "",
                         [events.COND_VARIABLE, 36, 1, 34, events.CMP_EQUAL,
                          1]),
        lcf.EventCommand(events.COND_BRANCH, 1, "",
                         [events.COND_VARIABLE, 37, 1, 35, events.CMP_EQUAL,
                          1]),
    ]
    return comandos + [lcf.EventCommand(c, i, "", list(p))
                       for c, i, p in cuerpo]


PRENDER_172 = (events.CONTROL_SWITCHES, 2, (0, 172, 172, 0))


def _compilar_celda(comandos):
    events.index_variables(GAME_DIR)
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map0049.lmu"))
    codigo = events.compile_page(
        events._Commands(comandos), {49: 0}.get, events.Messages(),
        events.MapEvents(game_map).for_event(0))
    assert codigo is not None, "la página no compila"
    return codigo


def _palabra(codigo, i):
    return codigo[i] | codigo[i + 1] << 8


def test_las_cuatro_de_la_celda_van_en_un_opcode():
    """Las dos escrituras y las dos ramas salen en un solo `OP_CELL_TEST`,
    con lo mismo que llevarían sueltas: el blanco, las cuatro variables como
    desplazamientos —la ranura por dos—, cuál coordenada va a cada una y los
    dos destinos, que sin `else` son los dos el final de su rama."""
    codigo = _compilar_celda(_celda(
        PRENDER_172,
        (events.COND_END, 1, ()),
        (events.COND_END, 0, ())))
    ops = [c[i] for i, c in events.walk_code(codigo)]
    assert ops == [events.OP_CELL_TEST, events.OP_SWITCH, events.OP_DONE]
    r = events.variable_slot
    assert codigo[1] == 0, "el blanco es el héroe"
    assert _palabra(codigo, 2) & ~events.CELL_REFRESH \
        == r(36) * 2 | events.CELL_Y
    assert _palabra(codigo, 4) & ~events.CELL_REFRESH == r(37) * 2
    assert (_palabra(codigo, 6), _palabra(codigo, 8)) == (r(36) * 2, r(34) * 2)
    assert (_palabra(codigo, 12), _palabra(codigo, 14)) \
        == (r(37) * 2, r(35) * 2)
    fin = len(codigo) - 1                     # el OP_DONE
    assert _palabra(codigo, events.CELL_DEST_A) == fin
    assert _palabra(codigo, events.CELL_DEST_B) == fin


def test_el_else_de_la_rama_de_adentro_sale_de_su_destino():
    """Con un `else` en la rama de adentro, su destino es el cuerpo del
    `else` —después del `OP_GOTO` que saca a la de arriba—, y el de la de
    afuera sigue siendo su final. Es el mismo parche que el de una rama
    suelta, sobre el segundo destino del opcode."""
    codigo = _compilar_celda(_celda(
        PRENDER_172,
        (events.COND_ELSE, 1, ()),
        (events.CONTROL_SWITCHES, 2, (0, 173, 173, 0)),
        (events.COND_END, 1, ()),
        (events.COND_END, 0, ())))
    ops = [(i, c[i]) for i, c in events.walk_code(codigo)]
    assert [o for _, o in ops] == [
        events.OP_CELL_TEST, events.OP_SWITCH, events.OP_GOTO,
        events.OP_SWITCH, events.OP_DONE]
    goto, sino, fin = ops[2][0], ops[3][0], ops[4][0]
    assert _palabra(codigo, events.CELL_DEST_B) == sino
    assert _palabra(codigo, goto + 1) == fin
    assert _palabra(codigo, events.CELL_DEST_A) == fin


def test_sin_la_forma_exacta_no_se_funde():
    """Una comparación que no es por igualdad, o una rama que no es lo
    primero adentro de la otra, va como antes: cuatro opcodes sueltos."""
    distinta = _celda(PRENDER_172, (events.COND_END, 1, ()),
                      (events.COND_END, 0, ()))
    distinta[3].parameters[4] = events.CMP_GREATER_EQUAL
    ops = [c[i] for i, c in events.walk_code(_compilar_celda(distinta))]
    assert events.OP_CELL_TEST not in ops
    assert ops[:4] == [events.OP_VAR, events.OP_VAR, events.OP_IF_VAR,
                       events.OP_IF_VAR]

    afuera = _celda(PRENDER_172, (events.COND_END, 1, ()),
                    (events.COND_END, 0, ()))
    afuera[3].indent = 0                      # la segunda, al lado de la otra
    ops = [c[i] for i, c in events.walk_code(_compilar_celda(afuera))]
    assert events.OP_CELL_TEST not in ops
