"""Los sistemas de los personajes que corren en una pelea: las páginas de tropa
que cambian el grupo, los HP del grupo y los del enemigo. Es lo de
`workflow/tasks/*/eventos-de-tropa-en-la-pelea.md`.

Cada página de tropa corre en la consola con los opcodes de los mapas, y cada
tramo pasa por `ba_sync_out` y `ba_sync_in` —ver `battle_troop.s`— para que
esos opcodes vean y cambien los HP de la pelea. Lo que se compara es contra
el modelo de la pelea, `modelo.Battle`, que corre las mismas páginas del LDB:

* **una invocación** (`pelea-invocacion`): Lerle usa `Droid`, que prende el
  814, y la página de la tropa la saca del grupo y pone al droide, que pelea
  desde el turno siguiente;
* **`LifeForStrength`** (`pelea-vida-por-fuerza`, el 801 prendido antes,
  contra el Gigante): guarda los HP de Talan en una variable, y con 40 o más
  lo mata y le saca 70 al enemigo; con menos, lo dice
  (`pelea-vida-por-fuerza-sin-hp`);
* **`Sacrifice`** (`pelea-sacrificio`, el 802): revive al grupo y mata a
  Talan.

Las tres primeras prueban también lo del mapa que las páginas usan: el
`ChangeHP` que resta, el `ControlVars` con los HP de un actor y el
`ChangeCondition` que revive.
"""

from batalla import Pelea, grupo_de, mensaje_en_pantalla, modelo_de
import datos
import modelo

KERSH, TALAN, LERLE, DROIDE = 11, 14, 26, 36
INVOCAR_DROIDE = 268
TROPA_GIGANTE, TROPA_VAGO = 128, 178
SIN_HP = ["TALAN does not have enough HP to",
          "sacrifice it in this way!"]


def a_la_pelea(una, tope=600):
    for _ in range(tope):
        una.consola.run(1)
        if una.menu_abierto():
            return Pelea(una)
    raise AssertionError("la página no abrió la pelea")


def lugar(una, k, campo):
    s = una.simbolos
    return una.consola.ram(s["BA_ONE"] + k * s["BA_BYTES"] + s[campo], 1)[0]


def quienes(una):
    """Los actores que pelean, por lugar: su número, o None en un lugar vacío
    —uno que una página sacó, o uno que nunca tuvo a nadie—."""
    s = una.simbolos
    return [lugar(una, k, "BA_NUMBER")
            if lugar(una, k, "BA_FLAGS") & s["BAF_HAS"] else None
            for k in range(s["BA_PARTY_MAX"])]


def del_modelo(esperado):
    """Lo mismo, del modelo: un actor que una página sacó queda oculto."""
    return [a.number if not a.hidden else None for a in esperado.actors]


def hp_de_todos(una, pelea, esperado):
    g = una.simbolos["BA_PARTY_MAX"]
    actores = [pelea.hp_del_combatiente(k)
               for k in range(len(esperado.actors))]
    enemigos = [pelea.hp_del_combatiente(g + k)
                for k in range(len(esperado.enemies))]
    return actores + enemigos


def hp_del_modelo(esperado):
    return [a.hp for a in esperado.actors] + [e.hp for e in esperado.enemies]


def pasar_turno(una, pelea, ordenes, tope=3000):
    """Da las órdenes y toca A hasta que vuelve a pedir órdenes o termina."""
    for orden in ordenes:
        pelea.ordenar(orden)
    for n in range(tope):
        if pelea.modo() in ("COMMAND", "END"):
            return
        una.consola.hold(*(("a",) if n % 6 < 2 else ()))
        una.consola.run(1)
    raise AssertionError("el turno no terminó")


def test_las_paginas_son_las_que_se_espera():
    """Si el juego cambiara, los casos de abajo pasarían por otro camino: la
    página del 814 saca a Lerle y pone al droide, la del 801 mira la
    variable que carga con los HP de Talan, y `Droid` prende el 814. La del
    802 del Dr. Vago es la misma que la del Gigante; la del 801, no: con el
    jefe sólo dice que no sirve, y por eso `LifeForStrength` se prueba con
    el Gigante."""
    base = datos.base()
    habilidad = base.skills[INVOCAR_DROIDE]
    assert habilidad.switch_id == 814

    def paginas(tropa):
        return {p.condition["switch_a_id"]: p
                for p in base.troops[tropa].pages
                if p.active == ["switch_a"]}

    def comandos(pagina):
        return [(c.code, list(c.parameters)) for c in pagina.commands]

    gigante, vago = paginas(TROPA_GIGANTE), paginas(TROPA_VAGO)
    assert comandos(gigante[814])[:2] == [(10330, [1, 0, LERLE]),
                                          (10330, [0, 0, DROIDE])]
    assert comandos(gigante[801])[0] == (10220, [0, 161, 161, 0, 5, TALAN, 2])
    assert comandos(vago[802]) == comandos(gigante[802])


def test_la_invocacion_cambia_a_lerle_por_el_droide(partida):
    """Kersh defiende y Lerle usa `Droid` en el turno 1. Después de su
    acción, antes de la siguiente, la página del 814 la saca y pone al
    droide **en su lugar** —el primero vacío—: el grupo queda Kersh y el
    droide, en ese orden, como en RM2k. Desde el turno 2 el droide recibe
    órdenes. Cada turno, los HP de todos y quién está en cada lugar son los
    del modelo, hasta que la pelea termina; y al cerrarla, los HP del droide
    vuelven a la partida."""
    una = partida(caso="pelea-invocacion")
    pelea = a_la_pelea(una).esperar("COMMAND")
    lerle = modelo.actor_of(LERLE)
    lerle.skills = [INVOCAR_DROIDE]
    esperado = modelo.Battle([modelo.actor_of(KERSH), lerle],
                             troop=TROPA_GIGANTE, pages=TROPA_GIGANTE)
    esperado.start()
    assert quienes(una)[:2] == [KERSH, LERLE]

    pasar_turno(una, pelea, [("defender",), ("habilidad", 0)])
    esperado.play_turn([(modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_SKILL, (INVOCAR_DROIDE, 0))])
    assert grupo_de(una) == [KERSH, DROIDE]
    assert quienes(una)[:2] == del_modelo(esperado) == [KERSH, DROIDE]
    assert hp_de_todos(una, pelea, esperado) == hp_del_modelo(esperado)
    assert not pelea.switch(814), "la página apaga su switch"

    for turno in range(2, 30):
        if pelea.modo() == "END":
            break
        pasar_turno(una, pelea, [("atacar", 0), ("atacar", 0)])
        esperado.play_turn([(modelo.COMMAND_ATTACK, 0),
                            (modelo.COMMAND_ATTACK, 0)])
        assert quienes(una)[:2] == del_modelo(esperado), "turno %d" % turno
        assert hp_de_todos(una, pelea, esperado) == \
            hp_del_modelo(esperado), "turno %d" % turno
    assert pelea.modo() == "END"
    pelea.cerrar()
    assert grupo_de(una) == [KERSH, DROIDE]
    assert una.hp(DROIDE) == esperado.actors[1].hp


def test_vida_por_fuerza_mata_a_talan_y_hiere_al_enemigo(partida):
    """Con el 801 prendido, la página corre antes de las primeras órdenes:
    Talan tiene 40 HP, que es lo que pide, así que muere —el `ChangeHP` que
    resta 999, letal— y el Gigante pierde 70. Después Talan no recibe
    órdenes: el turno es de Kersh solo."""
    una = partida(caso="pelea-vida-por-fuerza")
    pelea = a_la_pelea(una).esperar("COMMAND")
    esperado = modelo_de((KERSH, TALAN), TROPA_GIGANTE, pages=TROPA_GIGANTE,
                         switches={801: True})
    esperado.start()
    assert esperado.actors[1].hp == 0
    assert esperado.enemies[0].hp == esperado.enemies[0].hp_max - 70
    assert hp_de_todos(una, pelea, esperado) == hp_del_modelo(esperado)
    assert not pelea.switch(801)
    pasar_turno(una, pelea, [("defender",)])
    esperado.play_turn([(modelo.COMMAND_DEFEND, 0)])
    assert hp_de_todos(una, pelea, esperado) == hp_del_modelo(esperado)


def test_vida_por_fuerza_sin_hp_no_hace_nada(partida):
    """Con Talan en 30 —el caso le resta 10 en el mapa, sin matar— la
    variable no llega a 40 y la página sólo lo dice: nadie pierde HP."""
    una = partida(caso="pelea-vida-por-fuerza-sin-hp")
    pelea = a_la_pelea(una)
    pelea.esperar("PAGE")
    for _ in range(60):
        if mensaje_en_pantalla(una, pelea):
            break
        una.consola.run(1)
    assert mensaje_en_pantalla(una, pelea) == SIN_HP
    g = una.simbolos["BA_PARTY_MAX"]
    assert pelea.hp_del_combatiente(1) == 30
    hpmax = pelea.palabra(una.simbolos["BA_ONE"]
                          + g * una.simbolos["BA_BYTES"]
                          + una.simbolos["BA_HPMAX"])
    assert pelea.hp_del_combatiente(g) == hpmax


def test_el_sacrificio_revive_al_grupo_y_mata_a_talan(partida):
    """Kersh llega caído —el caso le resta 999 en el mapa, letal— y el 802
    prendido: la página revive al grupo con 1 HP —el `ChangeCondition` que
    saca la muerte— y mata a Talan. La pelea sigue con Kersh."""
    una = partida(caso="pelea-sacrificio")
    pelea = a_la_pelea(una).esperar("COMMAND")
    esperado = modelo_de((KERSH, TALAN), TROPA_VAGO, pages=TROPA_VAGO,
                         switches={802: True})
    esperado.actors[0].hp = 0
    esperado.start()
    assert [a.hp for a in esperado.actors] == [1, 0]
    assert hp_de_todos(una, pelea, esperado) == hp_del_modelo(esperado)
    pasar_turno(una, pelea, [("defender",)])
    esperado.play_turn([(modelo.COMMAND_DEFEND, 0)])
    assert hp_de_todos(una, pelea, esperado) == hp_del_modelo(esperado)
