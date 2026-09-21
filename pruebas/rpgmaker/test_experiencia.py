"""La experiencia y el nivel: lo que la pelea deja al terminar.

Como `test_batalla.py`, no se conforma con "subió": `tools/port/experiencia.py`
es `Game_Actor::CalculateExp`, `ChangeExp` y `ChangeLevel` de easyrpg, y la
prueba exige que la consola quede con **el mismo número** de experiencia y el
mismo nivel. La curva la calcula el conversor en punto flotante y viaja en el
cartucho, así que lo que se cobra acá es que la ROM la lea bien, sume bien y
suba cuando tiene que subir.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))

from port import batalla as modelo                          # noqa: E402
from port import experiencia                                # noqa: E402

from consola import en_la_rom                               # noqa: E402
from test_batalla import (GRUPO, TROPA_DROIDE, Pelea, db,   # noqa: E402
                          en_el_droide, modelo_de)


def rom_de(una):
    with open(una.sfc, "rb") as archivo:
        return archivo.read()


def ranura_exp(una, actor):
    """La ranura de `FAR_EXP` del actor, leída de `actor_exp_k`, o None.

    Se lee del cartucho y no se recalcula con `experiencia_ranuras`: depende
    de qué actores pueden entrar al grupo en **este** cartucho, y rehacer esa
    cuenta acá sería una segunda manera de contestar lo mismo.
    """
    k = rom_de(una)[en_la_rom(una.simbolos["actor_exp_k"]) + actor]
    return None if k == 0xFF else k


def exp_y_nivel(una, actor):
    k = ranura_exp(una, actor)
    assert k is not None, "el actor %d no tiene ranura de experiencia" % actor
    b = una.consola.ram(una.simbolos["FAR_EXP"] + 4 * k, 4)
    return b[0] | (b[1] << 8) | (b[2] << 16), b[3]


def poner_exp(una, actor, exp, nivel):
    k = ranura_exp(una, actor)
    una.consola.escribir_ram(una.simbolos["FAR_EXP"] + 4 * k,
                             [exp & 0xFF, (exp >> 8) & 0xFF, exp >> 16, nivel])


def ganar_al_droide(una, caidos=()):
    """La pelea del droide entera, atacando, y cerrada. Devuelve el modelo
    ya jugado, para saber quién quedó vivo.

    Los de `caidos` entran a la pelea con cero HP, de los dos lados.
    """
    for actor in caidos:
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor, [0, 0])
    pelea = Pelea(una).abrir()
    esperado = modelo_de(db())
    for quien in esperado.actores:
        if quien.numero in caidos:
            quien.hp = 0
    while esperado.resultado is None:
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
    assert esperado.resultado == modelo.VICTORIA
    pelea.cerrar()
    return esperado


def test_cada_actor_arranca_con_la_experiencia_de_su_nivel(partida):
    """El constructor de `Game_Actor`: `ChangeLevel(initial_level)` deja la
    experiencia en `GetBaseExp()`.

    Kersh arranca en el 20 y Core y Manta en el 15, así que el número no es
    cero y tampoco es el mismo para los tres: con un reset que copiara la
    tabla corrida, o la del nivel 1, esto se ve.
    """
    una = partida()
    base = db()
    for actor in GRUPO:
        esperado = (experiencia.exp_inicial(base.actors[actor]),
                    experiencia.nivel_inicial(base.actors[actor]))
        assert esperado[0] > 0
        assert exp_y_nivel(una, actor) == esperado, \
            "el actor %d arranca con %r y tendría que ser %r" % (
                actor, exp_y_nivel(una, actor), esperado)


def test_ganar_da_la_experiencia_de_la_tropa_a_los_vivos(partida):
    """`ProcessSceneActionVictory`: la suma de la tropa **a cada** actor vivo,
    y nada al que cayó.

    Core entra caído: con los actores en su nivel del LDB el droide no llega
    a matar a nadie, y sin un caído el caso no distinguiría "a todos" de "a
    los vivos".
    """
    una = en_el_droide(partida)
    base = db()
    antes = {a: exp_y_nivel(una, a) for a in GRUPO}
    esperado = ganar_al_droide(una, caidos=(GRUPO[1],))
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    assert ganada > 0
    vivos = {c.numero for c in esperado.actores if c.vivo}
    assert vivos and vivos != set(GRUPO), \
        "el caso necesita que alguien caiga y alguien quede en pie"
    for actor in GRUPO:
        nivel, exp = antes[actor][1], antes[actor][0]
        if actor in vivos:
            nivel, exp = experiencia.sumar(base.actors[actor], nivel, exp,
                                           ganada)
        assert exp_y_nivel(una, actor) == (exp, nivel), \
            "el actor %d quedó con %r y tendría que ser %r" % (
                actor, exp_y_nivel(una, actor), (exp, nivel))


def test_la_experiencia_se_topa_en_la_de_rm2k(partida):
    """`MaxExpValue()` de RM2k, 999999: sumar arriba de eso lo deja ahí.

    Es una suma de 24 bits con acarreo entre dos mitades y un tope partido en
    dos comparaciones, que es exactamente donde una cuenta de la ROM se
    equivoca por uno. Se arranca a menos de lo que da el droide del tope.
    """
    una = en_el_droide(partida)
    base = db()
    actor = GRUPO[0]
    nivel = experiencia.nivel_max(base.actors[actor])
    poner_exp(una, actor, experiencia.EXP_MAX - 10, nivel)
    ganar_al_droide(una)
    assert exp_y_nivel(una, actor) == (experiencia.EXP_MAX, nivel)


def test_la_experiencia_viaja_en_la_partida(partida):
    """`FAR_EXP` en `partida_tabla`, al final. Resetea la consola de verdad
    —la SRAM sobrevive— y pisa la RAM antes, porque snes9x no la borra."""
    una = partida(caso="guardar-198")
    actor = GRUPO[1]
    poner_exp(una, actor, 123456, 33)
    una.guardar_en()
    poner_exp(una, actor, 7, 2)
    una.reiniciar()
    assert exp_y_nivel(una, actor) == (123456, 33), \
        "la experiencia no volvió de la SRAM: quedó en %r" \
        % (exp_y_nivel(una, actor),)
