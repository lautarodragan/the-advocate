"""`KeyInputProc`: la página se para hasta que el jugador aprieta la tecla.

La tanda de pixeles lo cubre en `tecla`, que es lo que vale: ahí el cuadro
en que la pantalla se tiñe es el cuadro en que se apretó. Lo que se mira acá es
lo que un pixel no dice: **qué número quedó en la variable**, que es lo que las
páginas del juego leen después con un `ConditionalBranch`, y que la variable
quede en cero mientras se espera.

El valor esperado sale de `events.key_value`, que es `CheckInput` escrito de
este lado: si la ROM y esa tabla dejan de coincidir en el número de una tecla,
esto se cae.

**La cruceta y cancelar se prueban acá y no en la tanda**, salvo una dirección:
el cronómetro del caso `tecla-dir` muestra un número por ROM, así que cubrir las
cuatro y B por pixeles serían cinco casos para medir lo mismo. Acá cuesta un
toque cada uno. La que sigue afuera es la forma que **no espera**, y el porqué,
con el número, está en `KEY_WAIT` en `events.py`.
"""

from port import events

import datos

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
    """La ranura de la variable, con el mismo índice que armó el conversor."""
    return datos.ranuras_de_variable()[VARIABLE]


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
    una.tocar_ticks("a")
    una.correr(5)
    esperado = events.key_value(events.KEY_DECISION, {"a"})
    assert esperado == events.KEY_VALUE_DECISION == 5
    assert leer(una) == esperado, (
        "con A apretada la variable quedó en %d y el modelo dice %d"
        % (leer(una), esperado))


def test_sostener_la_tecla_no_contesta(partida):
    """Lo que el comando mira es el **flanco**, no que el botón esté puesto.

    Es `Input::IsTriggered`, lo mismo con lo que se cierra un mensaje, y es lo
    que hace que el comando no se coma la misma A que acaba de cerrar el
    cartel: en el juego las 23 esperas vienen justo detrás de un `ShowMessage`.

    Verificado en rojo cambiando `key_value` para que mire el estado en vez
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
        una.tocar_ticks(boton)
        una.correr(5)
        esperado = events.key_value(events.KEY_DIRS, {direccion})
        assert esperado == events.KEY_VALUE_DIR[direccion]
        assert leer(una) == esperado, (
            "con %s la variable quedó en %d y el modelo dice %d"
            % (boton, leer(una), esperado))


def test_cancelar_guarda_seis(partida):
    """B, que en RM2k vale 6.

    **El mismo B abre además el menú de pausa, y está bien que lo abra**: el
    comando no se come nada, y `Game_Player::Update` mira `IsTriggered(CANCEL)`
    igual. Lo único que lo frena es que haya una página corriendo —el
    `ev_active` de `request_menu`, que es el
    `Game_Map::GetInterpreter().IsRunning()` de allá— y en este cuadro la
    página **termina**: el comando era su último. Por eso el toque es un tick y
    no `tocar_ticks`, que son dos: con la pantalla de pausa abierta `ticks` no
    avanza y el segundo tick no llega nunca.
    """
    una = partida(caso="tecla-esperar-todo")
    una.correr(ESPERA + 10)
    una.sostener(1, "b")
    esperado = events.key_value(events.KEY_CANCEL, {"b"})
    assert esperado == events.KEY_VALUE_CANCEL == 6
    assert leer(una) == esperado, (
        "con B la variable quedó en %d y el modelo dice %d"
        % (leer(una), esperado))


def test_con_las_tres_pedidas_gana_cancelar(partida):
    """El orden de `CheckInput` es de mayor valor a menor —"RPG processes keys
    from highest variable value to lowest"— así que B le gana a A y A a la
    cruceta."""
    una = partida(caso="tecla-esperar-todo")
    una.correr(ESPERA + 10)
    una.sostener(1, "b", "a", "up")
    assert leer(una) == events.KEY_VALUE_CANCEL, (
        "con B, A y arriba a la vez la variable quedó en %d y tendría que "
        "decir cancelar" % leer(una))


def test_sostener_una_direccion_no_contesta(partida):
    """Lo mismo que con A: es el **flanco**, `Input::IsTriggered`.

    Sin esto, una dirección sostenida desde el arranque contestaría en el
    primer cuadro, y el caso `tecla-dir` de la tanda no mediría nada.
    """
    una = partida(caso="tecla-esperar-dir")
    una.correr(ESPERA + 20, sosteniendo=("left",))
    assert leer(una) == 0, (
        "el comando contestó con izquierda sostenida desde antes de arrancar: "
        "la variable quedó en %d" % leer(una))
