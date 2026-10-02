"""Las tablas de páginas: lo que la ROM va a leer, así que conviene mirar
acá que digan lo que tienen que decir.

No corre ninguna ROM. Es la red para las decisiones del compilador
—`rm2k-snes-events`, al que se le pregunta como le pregunta el conversor:
`conversor.py`— que no cambian un pixel por sí solas pero deciden qué página
está activa.
"""

import os
import re

import conversor
from datos import pagina_de
import events
import stage
import lcf
from resources import GAME_DIR


def paginas_de(map_id, evento_id):
    """Las páginas del evento como las contesta la primera llamada del
    compilador en un cartucho de ese mapa solo: con un bloque de textos
    propio y sin temas. De cada una, sus condiciones y su código."""
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    numero = [n for n, e in enumerate(game_map.events) if e.id == evento_id][0]
    registros = conversor.entrada(conversor.escaneo([map_id]),
                                  map_id)["pages"]
    return [dict(r, codigo=r["code"] and bytes.fromhex(r["code"]),
                 variable=tuple(r["variable"]) if r["variable"] else None)
            for r in registros if r["event"] == numero]


def ranuras_del_juego(extra=()):
    """{variable: ranura} del juego entero, con `extra`."""
    return conversor.ranuras(conversor.escaneo([], extra=extra))[0]


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
    paginas = paginas_de(133, 2)
    assert len(paginas) == 3
    primera, segunda, tercera = paginas
    assert primera["variable"] == (ranuras_del_juego()[123],
                                   events.CMP_GREATER_EQUAL, 8)
    assert segunda["variable"] is None and segunda["switch_a"] == 411
    assert tercera["item"] == 151 and tercera["variable"] is None \
        and tercera["switch_a"] == 0
    assert events.SWITCH_IMPOSSIBLE not in range(1, 1004), (
        "el juego consulta switches hasta el 1003")


def test_las_ranuras_son_las_del_juego_entero():
    """Las mismas ranuras en cualquier ROM: una partida guardada con la demo
    tiene que valer para una ROM con más mapas.

    Eran 81 hasta el 2026-09-13: el barrido no miraba el `KeyInputProc`,
    que es el único comando de este juego que le escribe a una variable sin ser
    un `ControlVars`. Las dos que aparecieron son la 5 —el motor del minijuego
    de las piedras del mapa 11— y la 151, y a ninguna de las dos la nombra
    nadie más, así que sin esto sus tres páginas no compilaban por un motivo
    que no tenía nada que ver con el comando.

    Y desde el 2026-09-21 son 123: el índice mira también las páginas de las
    tropas, que corren en la pelea, y los sistemas de batalla de los personajes
    suman cuarenta variables que ningún mapa nombra —la 81 y la 106 de Talan
    cuentan cuántas veces absorbió cada técnica—. Ver `variables`, en los
    índices de `rm2k-snes-events`.

    Y desde el 2026-09-27 son 132: `MemorizeLocation` y `RecallToLocation`
    nombran nueve que nadie más nombra —127 a 129, 158 a 160 y 169 a 171—, y
    con eso la ranura dejó de caber en siete bits: ver VAR_SLOT_MAX.

    Y desde el 2026-09-30 son 169: el índice mira también los eventos comunes,
    que un `CallEvent` compila en el lugar. El 35, `ResetAfterBattles`, nombra
    53 que nadie más nombra —cuántas veces se usó cada invocación, los HP de
    Talan—, y sin ranura el común entero se salteaba. Corrió las ranuras de
    las demás, y eso rompe las partidas de los cartuchos de antes: está
    aprobado, ver `decisiones/primero-el-juego-entero-despues-la-calidad.md`.
    Con ellos la más alta que el juego nombra pasó a ser la 204.

    Las cuatro de arriba de la 204 son nuestras y no del juego: las usa el
    evento paralelo que reemplazó a las 52 baldosas de luz del mapa 11 —ver
    `parches/manual/README.md`—. Están elegidas **por encima de la más alta que
    el juego nombra** justamente para que no le corran la ranura a ninguna: una
    partida guardada antes del rediseño sigue leyendo las mismas.
    """
    ranuras = ranuras_del_juego()
    assert list(ranuras.values()) == list(range(len(ranuras)))
    assert 5 in ranuras and 151 in ranuras
    del_juego = [v for v in ranuras if v <= 204]
    assert len(del_juego) == 169, del_juego
    assert {127, 128, 129, 158, 159, 160, 169, 170, 171} <= set(del_juego)
    assert max(del_juego) == 204
    assert all(ranuras[v] == r for r, v in enumerate(sorted(del_juego)))
    # Las de la página de prueba se suman al final, sin correr a las demás.
    con_extra = ranuras_del_juego(extra=(3000,))
    assert con_extra[3000] == len(ranuras)
    assert all(con_extra[v] == r for v, r in ranuras.items())


def test_el_tram_officer_compila_con_las_variables():
    """El Tram Officer del mapa 9 pide variables —azar, resta, los segundos del
    cronómetro, una rama por variable— y un CallEvent que se acepta sin hacer.
    Compila, y las suyas tienen ranura: la 17, la 21 y de la 39 a la 42.

    Hasta el 2026-09-29 esta prueba miraba también que **sin** las ranuras
    no compilara: el índice era un global de `events.py` que el conversor
    tenía que llenar antes de compilar, y dos veces lo llenó tarde. Desde que
    compila `rm2k-snes-events`, el compilador arma el índice él mismo antes
    de la primera página, y ese orden ya no se puede equivocar."""
    game_map = lcf.Map(os.path.join(GAME_DIR, "Map0009.lmu"))
    oficial = [e for e in game_map.events if e.name == "Tram Officer"][0]
    assert {17, 21, 39, 40, 41, 42} <= set(ranuras_del_juego())
    assert pagina_de(9, oficial.id, 0) is not None


# El refresco que pide cada escritura —el del cofre del mapa 133, que no
# aparecía después de un `Teleport` desde el 6 aunque la variable ya valía
# 8— lo miran desde el 2026-10-02 las pruebas del compilador:
# `a_write_after_jumping_to_another_map_asks_for_the_refresh` y su control,
# en `compile.rs` de `rm2k-snes-events`. Leían el bytecode, y el bytecode es
# del compilador.


def test_la_ruta_propia_apunta_al_bloque_que_recibe():
    """Una página con ruta propia lleva dos punteros adentro del código de
    eventos del mapa —+8 su código, +16 las órdenes de su ruta— y los dos
    tienen que salir de la etiqueta que `page_table` recibe, no del
    número del mapa. La etiqueta la pone `Materials`, que numera por clase y
    comparte los bloques iguales: con un bloque de código compartido antes
    que el de este mapa, `evcode_<mapa>` es el de **otro** mapa, o no
    existe y `ca65` se cae con "Symbol 'evcode_82' is undefined".

    El +16 rearmaba el nombre hasta el 2026-09-27: la deduplicación del
    2026-09-07 arregló el +8 y no lo vio, porque ningún cartucho tenía un
    bloque de código compartido antes de un mapa con rutas propias. Lo
    destapó un `release` con los mapas hasta el 85. No corre ninguna ROM: la
    tabla es texto, y lo que importa es a qué símbolo nombra.
    """
    pagina = {
        "event": 0, "page": 1, "trigger": events.TRIGGER_PARALLEL,
        "switch_a": 0, "switch_b": 0, "actor": 0, "layer": 1, "item": 0,
        "has_code": True, "offset": 0, "route_offset": 1,
        "frequency": 3, "speed": 4,
        "own_route": {"repeats": True, "skippable": False,
                      "fixed_direction": False, "animation_continues": False,
                      "frequency": 3, "speed": 4, "orders": 1},
    }
    # La tabla la escribe `rm2k-snes-mapdata`, que es la emisión: se le
    # pide la de un mapa solo.
    tabla = stage.run("rm2k-snes-mapdata", "mapdata", "pages",
                      {"number": 7, "evcode": "evcode_3",
                       "pages": [pagina]})["pages.inc"]
    nombrados = set(re.findall(r"evcode_\d+", tabla))
    assert nombrados == {"evcode_3"}, (
        "la tabla del mapa 7, cuyo código es el bloque evcode_3, nombra %s"
        % sorted(nombrados))


# "¿Está el héroe en la celda de las variables 34 y 35?", las dos
# escrituras y las dos ramas fundidas en un opcode: también son del
# compilador desde el 2026-10-02, `the_four_of_the_cell_go_in_one_opcode` y
# sus dos vecinas en `compile.rs`.
