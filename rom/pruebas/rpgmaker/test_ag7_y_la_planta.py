"""El hito 4 de Lashe City: AG7-17 en la pelea, y los enemigos de la planta.

Tres cosas que la pelea no hacía hasta el 2026-09-27, y las tres se miran
acá contra el número exacto del modelo, como el resto de las peleas:

* **los enemigos eligen qué hacer** —`EnemyAi`, con el `rating` de cada
  acción— y usan habilidades: el Tangle Wire de la tropa 113 tira
  `ShortCircuit` la mitad de las veces;
* **atacar con un arma cobra su `sp_cost`**, que en AG7 es de todas las
  piezas: ArmCannon 1, GrenadeLauncher 4;
* **las habilidades de a muchos**, que hasta ese día quedaban afuera del
  menú: BombsAway pega a los dos enemigos, cada uno con sus tiros.

Y lo que no es de la pelea pero es lo que le da sus habilidades a AG7: el
evento común 37, `UpdateAG7 Skills`, paralelo con el switch 150, que la ROM
corre al prenderse el switch y al cerrar el menú —ver
`events.PARTY_COMMON_EVENTS`—.

Las dos páginas de prueba arman el grupo de la rama sin compañero —Talan y
AG7— en el piso 1 de la planta, y prenden el 150 con el `ControlSwitches` de
siempre: `ag7-componentes` para lo del menú y `pelea-113` para pelear.
"""


from batalla import Pelea, hab_id, sabe
import datos
import modelo
import menu

TALAN, AG7 = 14, 18
# La tropa 113: el Tangle Wire, que trae `ShortCircuit` en 50 como el ataque,
# y una GiantRat, que sólo ataca.
TROPA = 113
TANGLE_WIRE, GIANT_RAT = 67, 64
SHORT_CIRCUIT = 188
# Las piezas y lo que da cada una, del evento común 37.
ARM_CANNON, ARM_LAUNCHER, GRENADE_LAUNCHER = 269, 270, 277
CONCENTRATED_SPRAY, ARM_MISSILE, BOMBS_AWAY = 237, 238, 245
# Lo que dura la página de prueba: el `Wait` de diez —un segundo— y lo que
# sigue, con margen.
HASTA_EL_SWITCH = 150


def habilidades_del_evento_37():
    """{pieza: habilidad}, leído del evento común 37 y no copiado a mano: las
    ramas "tiene puesto" y el `ChangeSkills` que sigue a cada una."""
    comandos = datos.base().common_events[37]
    pares = {}
    for i, cmd in enumerate(comandos):
        if cmd.code == 12010:
            siguiente = comandos[i + 1]
            pares[cmd.parameters[3]] = siguiente.parameters[4]
    return pares


def todas_las_de_ag7():
    return sorted(set(habilidades_del_evento_37().values()))


def poner_arma(una, item):
    """El arma de AG7 en `FAR_EQUIPMENT`, como la dejaría la pantalla de
    equipo."""
    una.consola.write_ram(una.simbolos["FAR_EQUIPMENT"] + AG7 * 10,
                          [item & 0xFF, item >> 8])


def las_que_sabe(una):
    return [h for h in todas_las_de_ag7() if sabe(una, AG7, h)]


def test_el_evento_37_da_la_habilidad_de_cada_pieza():
    """Lo que las demás pruebas suponen del LDB: la ArmCannon da
    ConcentratedSpray, el ArmLauncher ArmMissile y el GrenadeLauncher
    BombsAway, que es de a muchos."""
    pares = habilidades_del_evento_37()
    assert pares[ARM_CANNON] == CONCENTRATED_SPRAY
    assert pares[ARM_LAUNCHER] == ARM_MISSILE
    assert pares[GRENADE_LAUNCHER] == BOMBS_AWAY
    assert len(pares) == 17


# --- las habilidades de AG7: el evento común 37 ------------------------------

def test_al_entrar_al_grupo_sabe_la_de_su_arma(partida):
    """El 150 se prende y AG7 sabe ConcentratedSpray, la de la ArmCannon con
    la que llega, **y ninguna otra**: el evento empieza por sacarle las
    diecisiete. Sin el cuerpo pegado detrás del `ControlSwitches` no sabría
    ninguna, que es como entraba en el hito 3."""
    una = partida(caso="ag7-componentes")
    assert una.equipo(AG7)[0] == ARM_CANNON
    assert las_que_sabe(una) == []
    una.correr(HASTA_EL_SWITCH)
    assert not una.corriendo_una_pagina(), "la página de prueba no terminó"
    assert las_que_sabe(una) == [CONCENTRATED_SPRAY]


def test_cambiar_el_arma_y_cerrar_el_menu_cambia_la_habilidad(partida):
    """"These abilities become available once you equip a particular
    component and exit the menu", dice el tutorial. Con el ArmLauncher puesto
    **no cambia nada hasta cerrar el menú**; al cerrarlo sabe ArmMissile y
    perdió ConcentratedSpray."""
    una = partida(caso="ag7-componentes")
    una.correr(HASTA_EL_SWITCH)
    assert not una.corriendo_una_pagina(), "la página de prueba no terminó"
    poner_arma(una, ARM_LAUNCHER)
    menu.abrir(una)
    assert las_que_sabe(una) == [CONCENTRATED_SPRAY], \
        "con el menú abierto el evento no tiene por qué haber corrido"
    una.tocar_cuadros("b")
    for _ in range(120):
        if not una.menu_abierto():
            break
        una.consola.run(1)
    assert not una.menu_abierto()
    assert las_que_sabe(una) == [ARM_MISSILE]


def test_con_el_switch_apagado_cerrar_el_menu_no_toca_nada(partida):
    """El evento es paralelo **con el switch 150**: apagado no corre, y cerrar
    el menú no le cambia nada a nadie. Es lo que distingue al camino de
    `equipment_commons` de uno que corriera el cuerpo siempre."""
    una = partida(caso="ag7-componentes")
    una.correr(HASTA_EL_SWITCH)
    assert not una.corriendo_una_pagina(), "la página de prueba no terminó"
    s = una.simbolos
    donde = s["switches"] + 150 // 8
    byte = una.consola.ram(donde, 1)[0]
    una.consola.write_ram(donde, [byte & ~(1 << (150 % 8)) & 0xFF])
    poner_arma(una, ARM_LAUNCHER)
    menu.abrir(una)
    una.tocar_cuadros("b")
    for _ in range(120):
        if not una.menu_abierto():
            break
        una.consola.run(1)
    assert las_que_sabe(una) == [CONCENTRATED_SPRAY]


# --- la pelea de la planta -----------------------------------------------------

def a_la_pelea(una, tope=600):
    """Corre la página hasta que abre la pelea."""
    for _ in range(tope):
        una.consola.run(1)
        if una.menu_abierto():
            return Pelea(una)
    raise AssertionError("la página no abrió la pelea")


def modelo_de_la_planta(base, equipo_de_ag7=None):
    """Talan y AG7 contra la tropa 113, con las habilidades que el evento 37
    le da a AG7 por lo que tiene puesto."""
    equipo = list(base.actors[AG7].initial_equipment)
    if equipo_de_ag7:
        equipo[0] = equipo_de_ag7
    ag7 = modelo.actor_of(AG7, equipo)
    pares = habilidades_del_evento_37()
    ag7.skills = sorted(pares[p] for p in equipo if p in pares)
    return modelo.Battle(
        [modelo.actor_of(TALAN), ag7],
        [modelo.enemy_of(e, n)
         for n, e in enumerate(base.troops[TROPA].members)])


def estado(pelea, una):
    """Los HP de los cuatro y los SP de AG7 y del Tangle Wire, de la RAM."""
    g = una.simbolos["BA_PARTY_MAX"]
    return ([pelea.hp_del_combatiente(k) for k in (0, 1, g, g + 1)]
            + [pelea.sp_del_combatiente(1), pelea.sp_del_combatiente(g)])


def estado_del_modelo(m):
    return ([c.hp for c in m.actors + m.enemies]
            + [m.actors[1].sp, m.enemies[0].sp])


def test_la_tropa_es_la_que_se_espera():
    """Lo que las pruebas de abajo suponen del LDB, para que un cambio de datos
    no las deje pasando por el camino equivocado."""
    base = datos.base()
    assert base.troops[TROPA].members == [TANGLE_WIRE, GIANT_RAT]
    acciones = modelo.actions_of_enemy(TANGLE_WIRE)
    assert [(r, s) for r, s, _ef in acciones] == [
        (50, None), (50, SHORT_CIRCUIT)]
    # Y los tres de la planta que la traen con menos rating no la usan nunca:
    # diez puntos por debajo de la mejor pesan cero.
    for enemigo in (62, 65, 66):
        batalla = modelo.Battle([], [modelo.enemy_of(enemigo, 0)])
        for _ in range(20):
            _r, skill, _ef = batalla.enemy_action(batalla.enemies[0])
            assert skill is None


def test_el_tangle_wire_usa_short_circuit_y_deja_el_hp_del_modelo(partida):
    """Turno por turno contra `modelo.Battle`: los dos se defienden dos
    turnos —para darle tiempo al Tangle Wire— y después AG7 le pega a la rata,
    y muerta ella, al Tangle Wire. Adentro están la elección del enemigo —un
    tiro para la acción, porque el Tangle Wire tiene dos de peso, y otro para
    el blanco—, `ShortCircuit` con `CalcSkillEffect` y los SP que le cuesta, y
    el SP de la ArmCannon en cada ataque de AG7. **El caso exige que el Tangle
    Wire la haya usado** —sus SP bajaron— y que AG7 haya pagado su arma: si
    no, pasaría mirando sólo ataques."""
    una = partida(caso="pelea-113")
    pelea = a_la_pelea(una)
    base = datos.base()
    esperado = modelo_de_la_planta(base)
    assert esperado.actors[1].weapon_sp == 1
    for turno in range(1, 12):
        ordenes, del_modelo = [], []
        for quien in esperado.living(esperado.actors):
            if quien.number == AG7 and turno > 2:
                # El blanco es el lugar en la tropa para el modelo y en la
                # lista de los vivos para el cursor.
                vivos = [n for n, e in enumerate(esperado.enemies) if e.alive]
                blanco = 1 if esperado.enemies[1].alive else 0
                ordenes.append(("atacar", vivos.index(blanco)))
                del_modelo.append((modelo.COMMAND_ATTACK, blanco))
            else:
                ordenes.append(("defender",))
                del_modelo.append((modelo.COMMAND_DEFEND, 0))
        for orden in ordenes:
            pelea.ordenar(orden)
        pelea.correr_turno()
        esperado.play_turn(del_modelo)
        assert estado(pelea, una) == estado_del_modelo(esperado), \
            "turno %d: la consola dejó %r y el modelo %r" % (
                turno, estado(pelea, una), estado_del_modelo(esperado))
        if esperado.result is not None:
            break
    assert esperado.enemies[0].sp < esperado.enemies[0].sp_max, \
        "el Tangle Wire no usó ShortCircuit: el caso no mide la habilidad"
    assert esperado.actors[1].sp < esperado.actors[1].sp_max, \
        "AG7 no pagó el SP del arma: el caso no mide el costo"


def test_la_lista_de_ag7_en_la_pelea_es_la_de_su_arma(partida):
    """El menú de "Components" con la ArmCannon: ConcentratedSpray sola."""
    una = partida(caso="pelea-113")
    pelea = a_la_pelea(una)
    pelea.ordenar(("defender",))
    pelea.esperar("COMMAND")
    assert pelea.byte("BA_ACTOR") == 1
    pelea.tocar_cuadros("right")
    pelea.tocar_cuadros()
    pelea.esperar("SKILL")
    lista = una.consola.ram(una.simbolos["BA_SKILL_LIST"],
                            pelea.byte("BA_SKILL_N"))
    assert [hab_id(una, k) for k in lista] == [CONCENTRATED_SPRAY]


def test_bombs_away_pega_a_los_dos_enemigos(partida):
    """Con el GrenadeLauncher puesto antes de que se prenda el 150, AG7 sabe
    BombsAway, de alcance `enemies`: **no pide blanco** y le pega a los dos,
    cada uno con su crítico, su varianza y su acierto, en el orden de la
    pantalla. Se cobra el SP de la habilidad y no el del arma, porque no
    ataca."""
    una = partida(caso="pelea-113")
    poner_arma(una, GRENADE_LAUNCHER)
    pelea = a_la_pelea(una)
    base = datos.base()
    esperado = modelo_de_la_planta(base, GRENADE_LAUNCHER)
    bombs = base.skills[BOMBS_AWAY]
    assert esperado.actors[1].skills == [BOMBS_AWAY]
    antes = [c.hp for c in esperado.enemies]
    pelea.ordenar(("defender",))
    pelea.ordenar(("habilidad", 0))
    pelea.correr_turno()
    esperado.play_turn([(modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_SKILL, (BOMBS_AWAY, 0))])
    assert estado(pelea, una) == estado_del_modelo(esperado), \
        "la consola dejó %r y el modelo %r" % (estado(pelea, una),
                                               estado_del_modelo(esperado))
    assert all(c.hp < hp for c, hp in zip(esperado.enemies, antes)), \
        "BombsAway tenía que pegarle a los dos"
    assert esperado.actors[1].sp == 60 - bombs.sp_cost
