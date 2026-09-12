"""`KeyInputProc`: la página se para hasta que el jugador aprieta la tecla.

La tanda de pixeles lo cubre en `snes-tecla`, que es lo que vale: ahí el cuadro
en que la pantalla se tiñe es el cuadro en que se apretó. Lo que se mira acá es
lo que un pixel no dice: **qué número quedó en la variable**, que es lo que las
páginas del juego leen después con un `ConditionalBranch`, y que la variable
quede en cero mientras se espera.

El valor esperado sale de `eventos.tecla_de`, que es la misma función que corre
la referencia: si alguien le cambia el número a la tecla de acción, esto se cae
aunque los dos lados sigan coincidiendo entre ellos.

**Lo que no se prueba acá, porque no se puede**: la cruceta y cancelar. Este
port acepta una sola forma del comando —esperar la tecla de acción— y el porqué,
con el número, está en `KEY_INPUT_PROC` en `eventos.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))

import eventos                                               # noqa: E402
from render_map import GAME_DIR                              # noqa: E402

# La variable de RM2k donde el comando guarda lo que leyó. Cualquiera sirve: el
# conversor le da ranura porque la nombra la página de prueba.
VARIABLE = 88
ESPERA = 30
# Los cinco parámetros de RM2k: variable, esperar, la cruceta, la tecla de
# acción, cancelar. Es la forma que usan 23 de las 32 apariciones del juego.
ESPERAR_A = (VARIABLE, 1, 0, 1, 0)


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
    una = partida(tecla=ESPERAR_A, espera=ESPERA)
    una.correr(ESPERA + 60)
    assert leer(una) == 0, (
        "la variable quedó en %d sin que nadie apretara nada" % leer(una))


def test_al_apretar_guarda_el_numero_de_la_tecla_de_accion(partida):
    """Cinco, que es lo que dice `CheckInput` y lo que dice el modelo."""
    una = partida(tecla=ESPERAR_A, espera=ESPERA)
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
    una = partida(tecla=ESPERAR_A, espera=ESPERA)
    una.correr(ESPERA + 20, sosteniendo=("a",))
    assert leer(una) == 0, (
        "el comando contestó con A sostenida desde antes de arrancar: la "
        "variable quedó en %d" % leer(una))
