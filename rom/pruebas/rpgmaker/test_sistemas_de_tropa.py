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
  Talan;
* **`Play Radio`** (`pelea-radio`, el 809 con la cinta del 806): pone el
  tema de la cinta, y le pone a Emily un accesorio o la cura, según el azar.

Las tres primeras prueban también lo del mapa que las páginas usan: el
`ChangeHP` que resta, el `ControlVars` con los HP de un actor y el
`ChangeCondition` que revive.
"""

import pytest

from batalla import Pelea, grupo_de, mensaje_en_pantalla, modelo_de
from consola import indice_del_tema
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
    vuelven a la partida.

    Para ver eso último, la prueba apaga el 498 antes de cerrar: si no, la
    automática del mapa llama al común 35 en cuanto el mapa vuelve, y el
    común cura al droide y lo saca del grupo. Eso lo mira
    `test_despues_de_la_pelea_lerle_vuelve_al_grupo`."""
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
    una.apagar(498)
    pelea.cerrar()
    assert grupo_de(una) == [KERSH, DROIDE]
    assert una.hp(DROIDE) == esperado.actors[1].hp


def test_despues_de_la_pelea_lerle_vuelve_al_grupo(partida):
    """Lo que hace el común 35, `ResetAfterBattles`, en RM2k: la página de
    turno 0 de la tropa prende el 498 al abrir la pelea, y al volver al mapa
    la automática `AfterBattleMint` del 60 —hay una en cada mapa con
    encuentros— lo llama. El común cura a las invocaciones, saca del grupo a
    la que esté y devuelve a Lerle al final, y apaga el 498. Así que después
    de ganar con el droide, el grupo es otra vez Kersh y Lerle, y el droide
    quedó con todos sus HP para la próxima."""
    una = partida(caso="pelea-invocacion")
    pelea = a_la_pelea(una).esperar("COMMAND")
    assert pelea.switch(498), "la página de turno 0 prende el 498"
    pasar_turno(una, pelea, [("defender",), ("habilidad", 0)])
    assert grupo_de(una) == [KERSH, DROIDE]
    for _ in range(30):
        if pelea.modo() == "END":
            break
        pasar_turno(una, pelea, [("atacar", 0), ("atacar", 0)])
    assert pelea.modo() == "END"
    pelea.cerrar()
    for _ in range(600):
        if not pelea.switch(498):
            break
        una.consola.run(1)
    assert not pelea.switch(498), "el común 35 apaga el 498 al terminar"
    assert grupo_de(una) == [KERSH, LERLE]
    assert una.hp(DROIDE) == datos.maximos()[DROIDE][0]


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


# --- la radio -----------------------------------------------------------------

EMILY = 25
# Lo que cada número de la variable 163 pone con la cinta del 806: los tres
# caminos de la página del 809, en el orden de sus ramas.
RADIO_806 = {1: 386, 2: None, 3: 387}


def semilla_para(cual):
    """Una semilla del azar del mapa con la que el `ControlVars` de 1 a 3 de
    la página da `cual`: el xorshift de `random_next` y el resto de la
    división por 3 que hace OP_VAR. Si esta cuenta no fuera la de la ROM, la
    prueba lo cobra al leer la variable."""
    for semilla in range(1, 0x10000):
        x = semilla
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        if 1 + x % 3 == cual:
            return semilla
    raise AssertionError("ninguna semilla da %d" % cual)


@pytest.mark.parametrize("cual", sorted(RADIO_806))
def test_la_radio_equipa_a_emily_o_la_cura(partida, cual):
    """Con la cinta del 806 y el 809 prendidos, la página de `Play Radio`
    corre al abrir la pelea: saca un número de 1 a 3 en la variable 163 y,
    según cuál, le pone a Emily un accesorio —el 386 o el 387— o le suma 60
    HP. El tema que pone la cinta lo mira `test_la_radio_pone_el_tema_de_la_cinta`.
    El número sale del azar del mapa, y la prueba le pone la semilla justo
    cuando la pelea arranca para pasar por los tres caminos.

    **Emily no pelea**, a propósito: la página la nombra a ella, y ponerla
    en el grupo del caso la vuelve un actor del cartucho, con sus ítems y su
    nivel en las tablas del banco 0, que no tiene lugar —medido, 15 B contra
    13 libres—. Así se prueba lo que la página le hace en la partida; lo que
    la pelea toma de un equipo nuevo, `ba_reparam`, corre en cada tramo de
    página de las demás pruebas, y un parámetro mal recalculado cambiaría el
    daño que el modelo predice."""
    una = partida(caso="pelea-radio")
    s = una.simbolos
    antes = una.equipo(EMILY)
    for _ in range(600):
        if pelea_de(una) == TROPA_GIGANTE:
            break
        una.consola.run(1)
    else:
        raise AssertionError("la pelea no arrancó")
    semilla = semilla_para(cual)
    una.consola.write_ram(s["FAR_RANDOM"], bytes([semilla & 0xFF, semilla >> 8]))
    pelea = a_la_pelea(una)
    pelea.esperar("PAGE")
    assert una.variable(datos.ranuras_de_variable()[163]) == cual
    item = RADIO_806[cual]
    # El mensaje va antes de lo que hace: A, hasta que la página termina.
    for n in range(600):
        if pelea.modo() == "COMMAND":
            break
        una.consola.hold(*(("a",) if n % 6 < 2 else ()))
        una.consola.run(1)
    assert pelea.modo() == "COMMAND"
    # El caso le resta 100 sin matarla, así que se ve si suma.
    maximo = datos.maximos()[EMILY][0]
    restados = max(1, maximo - 100)
    if item is None:
        assert una.hp(EMILY) == min(maximo, restados + 60)
        assert una.equipo(EMILY) == antes
        return
    assert una.hp(EMILY) == restados
    assert una.equipo(EMILY) == antes[:4] + [item]
    # Lo que tenía vuelve al inventario, y del nuevo no había ninguno.
    if antes[4]:
        assert una.item(antes[4]) == 1
    assert una.item(item) == 0


# El tema que pone cada cinta: la página del 809 lo prende antes de mirar la
# variable, así que suena en los tres caminos.
TEMA_DE_LA_CINTA = {806: "dd2shad2", 807: "patchb",
                    808: "Ryan_Bury_-_Eternal_Champions_Theme_-_Club_Mix"}


@pytest.mark.parametrize("cinta", sorted(TEMA_DE_LA_CINTA))
def test_la_radio_pone_el_tema_de_la_cinta(partida, cinta):
    """El `PlayBGM` de la página de `Play Radio` se hace: con la cinta
    puesta, en cuanto la página corre suena su tema, y con sus muestras en
    la ARAM.

    Los tres temas van **aparte** en el paquete de la pelea —ver `plan`, en
    el `cartridge.rs` de `rm2k-snes-audio`—: no suben con el tema de la
    pelea, los sube su `PlayBGM` solos con los efectos del paquete, que es
    lo que hace que el de la pelea no tenga que bajar la tasa para dejarles
    lugar. Lo que se mira es lo mismo que en `test_tema_del_mapa.py`:
    `song_current`, que la música no esté callada, y que las muestras que el
    tema usa estén subidas.

    El caso prende la cinta del 806; para las otras dos, la prueba la cambia
    justo cuando la pelea arranca, antes de que la página corra."""
    una = partida(caso="pelea-radio")
    for _ in range(600):
        if pelea_de(una) == TROPA_GIGANTE:
            break
        una.consola.run(1)
    else:
        raise AssertionError("la pelea no arrancó")
    if cinta != 806:
        una.apagar(806).prender(cinta)
    tema = indice_del_tema(una, TEMA_DE_LA_CINTA[cinta])
    pelea = a_la_pelea(una)
    pelea.esperar("PAGE")
    for _ in range(600):
        if una.palabra("song_current") == tema:
            break
        una.consola.run(1)
    assert una.palabra("song_current") == tema, (
        "la radio con la cinta del %d tenía que poner %s, y suena el tema %d"
        % (cinta, TEMA_DE_LA_CINTA[cinta], una.palabra("song_current")))
    assert not una.byte("music_off"), "la radio prendió su tema y está callado"
    # Las muestras llegan al terminar de subir: se espera a que estén.
    assert una.muestras_del_tema(tema), "el tema no usa ninguna muestra"
    for _ in range(600):
        faltan = set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram()
        if not faltan:
            break
        una.consola.run(1)
    assert not faltan, (
        "el tema de la radio suena y le faltan en la ARAM las muestras %s"
        % sorted(faltan))


def pelea_de(una):
    """La tropa que `op_battle` dejó en `BA_TROOP`: la pelea ya arrancó
    aunque todavía no se vea."""
    bajo, alto = una.consola.ram(una.simbolos["BA_TROOP"], 2)
    return bajo | alto << 8
