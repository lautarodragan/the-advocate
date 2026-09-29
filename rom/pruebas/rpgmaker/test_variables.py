"""Las variables de RM2k: que la ROM las calcule, las compare y las guarde.

Lo que se ve de una variable lo cobra la tanda —el cronómetro puesto desde una
variable, `vars`—; acá se le pregunta a la ROM por su RAM lejana, que es
donde viven, y por los switches que una rama por variable prendió.

La página de prueba las escribe con los mismos números que RM2k: variable,
operación (0 pone, 1 suma, 2 resta), clase del operando (0 constante, 1 otra
variable, 3 azar, 7 otro) y dos números. Las ranuras las da
`events.index_variables`, que es el índice del juego entero.
"""

import pytest

from port import events

import datos

# La página de prueba `variables` hace: var 17 = 5; var 17 += 7 (12); var 21 =
# azar entre 0 y 100; var 39 = var 17; var 40 = 3; var 40 -= 10 (-7, con
# signo); var 41 = otro 0, el oro. Y una rama: si var 17 >= 12, prende el 200;
# el 201 se prende siempre. `variables-rama-no` pide >= 99, y
# `variables-guardar-198` es la primera esperando 198 ticks y guardando.


def ranuras():
    # El índice es del juego entero: las cinco de la página de prueba ya son
    # del juego, así que no agregan ninguna.
    return datos.ranuras_de_variable()


@pytest.fixture
def con_variables(partida):
    # Sin guardar: con eso la página espera 198 ticks antes de tocar nada.
    una = partida(caso="variables")
    una.correr(30)          # la página corre en el primer tick; treinta de aire
    return una


def test_las_operaciones_dan_lo_que_dan_en_python(con_variables):
    """Poner, sumar, restar con signo, copiar de otra y leer el oro."""
    una, r = con_variables, ranuras()
    assert una.variable(r[17]) == 12
    assert una.variable(r[39]) == 12
    assert una.variable(r[40]) == -7, "la resta con signo no dio -7"
    assert una.variable(r[41]) == 0, "el oro de arranque es cero"


def test_el_azar_es_el_mismo_de_los_dos_lados(con_variables):
    """El primer número al azar de la ROM es el primero del xorshift de
    `events.py` desde la misma semilla. Es el generador del modelo de
    `port/battle.py`, así que si se separaran, las pruebas que comparan una
    pelea número por número se separarían con él."""
    una, r = con_variables, ranuras()
    esperado = events.next_random(events.RANDOM_SEED) % 101
    assert una.variable(r[21]) == esperado, (
        "la ROM sacó %d y el xorshift de Python %d" % (una.variable(r[21]),
                                                        esperado))


def test_la_rama_por_variable_decide(con_variables):
    una = con_variables
    assert una.switch(200), "var 17 vale 12 y la rama >= 12 no entró"
    assert una.switch(201)


def test_la_rama_por_variable_que_no_se_cumple_no_corre(partida):
    """Y la otra mitad, que es la que se puede romper sin que nada se entere.

    Hasta el 2026-09-12 el `ConditionalBranch` por variable entraba **siempre**:
    `compare_var` dejaba la respuesta en las banderas y el `ply` que restaura
    el cursor las pisaba con el cursor, que nunca es cero. Todo lo que había
    acá miraba la rama que sí se cumple, así que pasaba en verde, y la tanda
    tampoco lo veía: ningún caso de la tanda toma una rama por variable
    que no se cumpla. Es el mismo defecto que dejó muda la pantalla de título,
    en otro lado.

    Verificado que **da rojo con el defecto puesto**: sin el `cmp` el switch
    200 queda prendido igual.
    """
    una = partida(caso="variables-rama-no")
    una.correr(30)
    assert not una.switch(200), (
        "var 17 vale 12, la rama pedía >= 99, y entró igual")
    assert una.switch(201), (
        "la página no llegó al final: el caso no probó nada")


def test_las_variables_viajan_en_la_partida(partida):
    """Se guardan con la partida y vuelven después del reset, que las pone
    en cero antes de cargar."""
    una = partida(caso="variables-guardar-198")
    r = ranuras()
    una.guardar_en(0)
    assert una.variable(r[17]) == 12
    una.reiniciar()
    assert una.variable(r[17]) == 12, "la variable 17 no volvió de la SRAM"
    assert una.variable(r[40]) == -7
