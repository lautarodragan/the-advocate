"""`KeyInputProc`: la página se para hasta que el jugador aprieta la tecla.

La tanda de pixeles lo cubre en `tecla`, que es lo que vale: ahí el cuadro
en que la pantalla se tiñe es el cuadro en que se apretó. Lo que se mira acá es
lo que un pixel no dice: **qué número quedó en la variable**, que es lo que las
páginas del juego leen después con un `ConditionalBranch`, y que la variable
quede en cero mientras se espera.

El valor esperado sale de `eventos.tecla_de`, que es la misma función que corre
la referencia: si alguien le cambia el número a la tecla de acción, esto se cae
aunque los dos lados sigan coincidiendo entre ellos.

**La cruceta y cancelar se prueban acá y no en la tanda**, salvo una dirección:
el cronómetro del caso `tecla-dir` muestra un número por ROM, así que cubrir las
cuatro y B por pixeles serían cinco casos para medir lo mismo. Acá cuesta un
toque cada uno. La que sigue afuera es la forma que **no espera**, y el porqué,
con el número, está en `KEY_INPUT_PROC` en `eventos.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "tools"))

from port import eventos                                     # noqa: E402
from render.render_map import GAME_DIR                              # noqa: E402

# La variable de RM2k donde el comando guarda lo que leyó. Cualquiera sirve: el
# conversor le da ranura porque la nombra la página de prueba.
VARIABLE = 88
# Lo que esperan las páginas de prueba `tecla-esperar-*` antes del
# `KeyInputProc`, en ticks. Las tres guardan en `VARIABLE` y esperan la tecla:
# `-a` la de acción, que es la forma que usan 23 de las 32 apariciones del
# juego; `-dir` la cruceta, que es el motor del minijuego de las piedras del
# mapa 11 —`(8, 1, 1, 0, 0)` en RM2k—; y `-todo` las tres cosas, que es el
# `(151, 1, 1, 1, 1)` de las otras dos páginas del juego.
ESPERA = 30


def ranura():
    """La ranura de la variable, con el mismo índice que armó el conversor.

    Hay que armarlo acá: `VARIABLE_SLOT` lo llena `indexar_variables`, y el que
    lo llamó fue el conversor, en otro proceso.
    """
    if VARIABLE not in eventos.VARIABLE_SLOT:
        eventos.indexar_variables(GAME_DIR, {VARIABLE})
    return eventos.VARIABLE_SLOT[VARIABLE]


def leer(una):
    return una.variable(ranura())


def test_mientras_nadie_aprieta_la_variable_queda_en_cero(partida):
    """Y la página no sigue: es la mitad que hace significar a la de abajo.

    Sin esto, un comando que no esperara nada daría el mismo verde al final: la
    variable terminaría en el valor de la tecla igual, sólo que sin haber
    esperado a nadie.
    """
    una = partida(caso="tecla-esperar-a")
    una.correr(ESPERA + 60)
    assert leer(una) == 0, (
        "la variable quedó en %d sin que nadie apretara nada" % leer(una))


def test_al_apretar_guarda_el_numero_de_la_tecla_de_accion(partida):
    """Cinco, que es lo que dice `CheckInput` y lo que dice el modelo."""
    una = partida(caso="tecla-esperar-a")
    una.correr(ESPERA + 10)
    assert leer(una) == 0, "se adelantó: la variable ya tenía %d" % leer(una)
    una.tocar("a")
    una.correr(5)
    esperado = eventos.tecla_de(eventos.TECLA_DECISION, {"a"})
    assert esperado == eventos.TECLA_VALOR_DECISION == 5
    assert leer(una) == esperado, (
        "con A apretada la variable quedó en %d y el modelo dice %d"
        % (leer(una), esperado))


def test_sostener_la_tecla_no_contesta(partida):
    """Lo que el comando mira es el **flanco**, no que el botón esté puesto.

    Es `Input::IsTriggered`, lo mismo con lo que se cierra un mensaje, y es lo
    que hace que el comando no se coma la misma A que acaba de cerrar el
    cartel: en el juego las 23 esperas vienen justo detrás de un `ShowMessage`.

    Verificado en rojo cambiando `tecla_valor` para que mire el estado en vez
    del flanco: ahí la variable queda en 5 sin que nadie haya apretado nada
    nuevo.
    """
    una = partida(caso="tecla-esperar-a")
    una.correr(ESPERA + 20, sosteniendo=("a",))
    assert leer(una) == 0, (
        "el comando contestó con A sostenida desde antes de arrancar: la "
        "variable quedó en %d" % leer(una))


def test_la_cruceta_guarda_el_numero_de_cada_direccion(partida):
    """Las cuatro, con los números de `CheckInput`: 4 arriba, 3 derecha, 2
    izquierda, 1 abajo.

    Son cuatro ROMs y no cuatro toques sobre una: el comando contesta una vez y
    la página sigue, así que el segundo toque ya no lo mira nadie.
    """
    for boton, direccion in (("up", 0), ("right", 1), ("down", 2), ("left", 3)):
        una = partida(caso="tecla-esperar-dir")
        una.correr(ESPERA + 10)
        assert leer(una) == 0, (
            "se adelantó con %s: la variable ya tenía %d" % (boton, leer(una)))
        una.tocar(boton)
        una.correr(5)
        esperado = eventos.tecla_de(eventos.TECLA_DIRS, {direccion})
        assert esperado == eventos.TECLA_VALOR_DIR[direccion]
        assert leer(una) == esperado, (
            "con %s la variable quedó en %d y el modelo dice %d"
            % (boton, leer(una), esperado))


def test_cancelar_guarda_seis(partida):
    """B, que en RM2k vale 6.

    **El mismo B abre además el menú de pausa, y está bien que lo abra**: el
    comando no se come nada, y `Game_Player::Update` mira `IsTriggered(CANCEL)`
    igual. Lo único que lo frena es que haya una página corriendo —el
    `ev_activo` de `pedir_menu`, que es el
    `Game_Map::GetInterpreter().IsRunning()` de allá— y en este cuadro la
    página **termina**: el comando era su último. Por eso el toque es un tick y
    no `tocar`, que son dos: con la pantalla de pausa abierta `vueltas` no
    avanza y el segundo tick no llega nunca.

    Y por eso B no entra en la tanda de pixeles: el menú de pausa la referencia
    no lo modela, así que un caso que lo abriera mediría dos programas
    distintos.
    """
    una = partida(caso="tecla-esperar-todo")
    una.correr(ESPERA + 10)
    una.sostener(1, "b")
    esperado = eventos.tecla_de(eventos.TECLA_CANCELAR, {"b"})
    assert esperado == eventos.TECLA_VALOR_CANCELAR == 6
    assert leer(una) == esperado, (
        "con B la variable quedó en %d y el modelo dice %d"
        % (leer(una), esperado))


def test_con_las_tres_pedidas_gana_cancelar(partida):
    """El orden de `CheckInput` es de mayor valor a menor —"RPG processes keys
    from highest variable value to lowest"— así que B le gana a A y A a la
    cruceta. Los dos lados lo miran con el mismo orden."""
    una = partida(caso="tecla-esperar-todo")
    una.correr(ESPERA + 10)
    una.sostener(1, "b", "a", "up")
    assert leer(una) == eventos.TECLA_VALOR_CANCELAR, (
        "con B, A y arriba a la vez la variable quedó en %d y tendría que "
        "decir cancelar" % leer(una))


def test_sostener_una_direccion_no_contesta(partida):
    """Lo mismo que con A: es el **flanco**, `Input::IsTriggered`.

    Sin esto, una dirección sostenida desde el arranque —que es lo único que
    `--walk` sabe hacer— contestaría en el primer cuadro de un lado y en otro
    del otro, y el caso `tecla-dir` de la tanda no mediría nada.
    """
    una = partida(caso="tecla-esperar-dir")
    una.correr(ESPERA + 20, sosteniendo=("left",))
    assert leer(una) == 0, (
        "el comando contestó con izquierda sostenida desde antes de arrancar: "
        "la variable quedó en %d" % leer(una))
