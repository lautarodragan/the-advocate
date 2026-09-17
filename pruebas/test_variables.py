"""Las variables de RM2k: que la ROM las calcule, las compare y las guarde.

Lo que se ve de una variable lo cobra la tanda —el cronómetro puesto desde una
variable, `vars`—; acá se le pregunta a la ROM por su RAM lejana, que es
donde viven, y por los switches que una rama por variable prendió.

La página de prueba las escribe con los mismos números que RM2k: variable,
operación (0 pone, 1 suma, 2 resta), clase del operando (0 constante, 1 otra
variable, 3 azar, 7 otro) y dos números. Las ranuras las da
`eventos.indexar_variables`, que es el índice del juego entero.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import eventos                                          # noqa: E402
from render_map import GAME_DIR                         # noqa: E402


ESPERA = 200
# var 17 = 5; var 17 += 7 (12); var 21 = azar entre 0 y 100; var 39 = var 17;
# var 40 = 3; var 40 -= 10 (-7, con signo); var 41 = otro 0, el oro.
VARIABLES = (17, 0, 0, 5, 0,
             17, 1, 0, 7, 0,
             21, 0, 3, 0, 100,
             39, 0, 1, 17, 0,
             40, 0, 0, 3, 0,
             40, 2, 0, 10, 0,
             41, 0, 7, 0, 0)
# Y una rama: si var 17 >= 12, prende el 200; el 201 se prende siempre.
RAMA = (17, 1, 12, 200, 201)


def ranuras():
    # El índice es del juego entero desde el 2026-09-10 a la noche: las cinco
    # de la página de prueba ya son del juego, así que no agregan ninguna.
    return eventos.variables_de(GAME_DIR, None, {17, 21, 39, 40, 41})


@pytest.fixture
def con_variables(partida):
    # Sin `guardar`: con él la página espera ESPERA ticks antes de tocar nada.
    una = partida(variables=VARIABLES, rama_var=RAMA)
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
    `eventos.py` desde la misma semilla. Si no fuera el mismo, una página con
    azar daría pixeles distintos sin que ninguno de los dos lados esté mal."""
    una, r = con_variables, ranuras()
    esperado = eventos.azar_siguiente(eventos.AZAR_SEMILLA) % 101
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
    `comparar_var` dejaba la respuesta en las banderas y el `ply` que restaura
    el cursor las pisaba con el cursor, que nunca es cero. Todo lo que había
    acá miraba la rama que sí se cumple, así que pasaba en verde, y la tanda
    tampoco lo veía: ningún caso de la tanda toma una rama por variable
    que no se cumpla. Es el mismo defecto que dejó muda la pantalla de título,
    en otro lado.

    Verificado que **da rojo con el defecto puesto**: sin el `cmp` el switch
    200 queda prendido igual.
    """
    una = partida(variables=VARIABLES, rama_var=(17, 1, 99, 200, 201))
    una.correr(30)
    assert not una.switch(200), (
        "var 17 vale 12, la rama pedía >= 99, y entró igual")
    assert una.switch(201), (
        "la página no llegó al final: el caso no probó nada")


def test_las_variables_viajan_en_la_partida(partida):
    """Se guardan con la partida y vuelven después del reset, que las pone
    en cero antes de cargar."""
    una = partida(guardar=ESPERA, variables=VARIABLES, rama_var=RAMA)
    r = ranuras()
    una.guardar_en(0)
    assert una.variable(r[17]) == 12
    una.reiniciar()
    assert una.variable(r[17]) == 12, "la variable 17 no volvió de la SRAM"
    assert una.variable(r[40]) == -7
