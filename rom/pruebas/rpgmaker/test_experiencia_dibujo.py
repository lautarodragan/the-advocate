"""La experiencia y el nivel: lo que la pelea deja al terminar.

Como `test_batalla.py`, no se conforma con "subió": `tools/port/experience.py`
es `Game_Actor::CalculateExp`, `ChangeExp` y `ChangeLevel` de easyrpg, y la
prueba exige que la consola quede con **el mismo número** de experiencia y el
mismo nivel. La curva la calcula el conversor en punto flotante y viaja en el
cartucho, así que lo que se cobra acá es que la ROM la lea bien, sume bien y
suba cuando tiene que subir.
"""

from port import battle as modelo
from port import experience

from batalla import (ARDEN, GRUPO, TROPA_DROIDE, Pelea, en_el_droide,
                     exp_y_nivel, poner_exp, ranura_exp)
import datos
from dibujo import diferencia


def ganar_al_droide(una, caidos=(), niveles=None, grupo=GRUPO):
    """La pelea del droide entera, atacando, y cerrada. Devuelve el modelo
    ya jugado, para saber quién quedó vivo.

    Los de `caidos` entran a la pelea con cero HP, de los dos lados, y los de
    `niveles` pelean en ese nivel en el modelo —en la ROM ya se lo puso
    `poner_exp`—. Los HP de la partida son los del reset, que son los del
    nivel de arranque, así que a los de `niveles` se les topan en el máximo
    del nivel nuevo, de los dos lados: es el `SetHp(GetHp())` de `SetLevel`,
    que la ROM no necesita porque nunca baja a nadie de nivel.
    """
    niveles = niveles or {}
    base = datos.base()
    esperado = modelo.Battle(
        [modelo.actor_of(base, a, level=niveles.get(a)) for a in grupo],
        [modelo.enemy_of(base, e, n)
         for n, e in enumerate(base.troops[TROPA_DROIDE].members)])
    for quien in esperado.actors:
        quien.hp = min(quien.hp_max, modelo.actor_of(base, quien.number).hp)
        if quien.number in caidos:
            quien.hp = 0
        una.poner_hp(quien.number, quien.hp)
    pelea = Pelea(una).abrir()
    while esperado.result is None:
        pelea.turno(len(esperado.living(esperado.actors)))
        esperado.play_turn(
            [(modelo.COMMAND_ATTACK, 0)] * len(esperado.living(esperado.actors)))
    assert esperado.result == modelo.VICTORY
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
    base = datos.base()
    for actor in GRUPO:
        esperado = (experience.initial_exp(base.actors[actor]),
                    experience.initial_level(base.actors[actor]))
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
    base = datos.base()
    antes = {a: exp_y_nivel(una, a) for a in GRUPO}
    esperado = ganar_al_droide(una, caidos=(GRUPO[1],))
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    assert ganada > 0
    vivos = {c.number for c in esperado.actors if c.alive}
    assert vivos and vivos != set(GRUPO), \
        "el caso necesita que alguien caiga y alguien quede en pie"
    for actor in GRUPO:
        nivel, exp = antes[actor][1], antes[actor][0]
        if actor in vivos:
            nivel, exp = experience.add_exp(base.actors[actor], nivel, exp,
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
    base = datos.base()
    actor = GRUPO[0]
    nivel = experience.max_level(base.actors[actor])
    poner_exp(una, actor, experience.EXP_MAX - 10, nivel)
    ganar_al_droide(una)
    assert exp_y_nivel(una, actor) == (experience.EXP_MAX, nivel)


def test_la_experiencia_viaja_en_la_partida(partida):
    """`FAR_EXP` en `save_table`, al final. Resetea la consola de verdad
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


# --- la subida de nivel -----------------------------------------------------

def test_ganar_sube_de_nivel_y_puede_subir_varios(partida):
    """El lazo de `ChangeExp`: sube mientras `GetNextExp(nivel)` alcance.

    Manta entra en el nivel 2 con 83 de experiencia, uno menos de lo que pide
    el 3, y el droide da 90: tiene que quedar en el 4, **dos niveles de una
    vez**, porque 173 pasa también los 172 del 4. Kersh entra a 50 de su
    siguiente nivel, que es la subida de a uno. Los dos números salen de
    `experience.add_exp` y no de acá.

    De paso, Manta pelea en el nivel 2 y el modelo también: si la ROM armara
    la pelea con los parámetros del nivel de arranque, los turnos no
    coincidirían con los del modelo.
    """
    una = en_el_droide(partida)
    base = datos.base()
    kersh, manta = GRUPO[0], GRUPO[2]
    lista = experience.exp_list(base.actors[kersh])
    nivel_k = experience.initial_level(base.actors[kersh])
    poner_exp(una, kersh, lista[nivel_k] - 50, nivel_k)
    poner_exp(una, manta, 83, 2)
    esperado = ganar_al_droide(una, niveles={manta: 2})
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    assert {kersh, manta} <= {c.number for c in esperado.actors if c.alive}
    assert experience.add_exp(base.actors[manta], 2, 83, ganada)[0] == 4, \
        "el caso quiere dos niveles de una vez para Manta"
    for actor, nivel, exp in ((kersh, nivel_k, lista[nivel_k] - 50),
                              (manta, 2, 83)):
        nivel, exp = experience.add_exp(base.actors[actor], nivel, exp, ganada)
        assert exp_y_nivel(una, actor) == (exp, nivel), \
            "el actor %d quedó con %r y tendría que ser %r" % (
                actor, exp_y_nivel(una, actor), (exp, nivel))


def test_en_el_tope_no_sube_mas(partida):
    """`GetMaxLevel()`: con el `final_level` del LDB alcanzado, la experiencia
    se suma y el nivel no se mueve."""
    una = en_el_droide(partida)
    base = datos.base()
    actor = GRUPO[0]
    tope = experience.max_level(base.actors[actor])
    lista = experience.exp_list(base.actors[actor])
    poner_exp(una, actor, lista[tope - 1] + 5, tope)
    ganar_al_droide(una, niveles={actor: tope})
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    assert exp_y_nivel(una, actor) == (lista[tope - 1] + 5 + ganada, tope)


def test_la_pelea_usa_los_parametros_del_nivel_de_ahora(partida):
    """`GetBaseMaxHp` y sus hermanas leen la curva del LDB **en el nivel que
    tiene**, no en el de arranque.

    Se le pone el nivel 30 a Kersh y se abre la pelea: los seis parámetros que
    la pelea arma —HP y SP máximos, ataque, defensa, espíritu y agilidad—
    tienen que ser los de `battle.actor_of` con ese nivel, y distintos de
    los del 20, que si no el caso no distingue nada. Los cuatro del medio
    pasan por `eq_parameter`, que es también la de la pantalla de equipo.
    """
    una = en_el_droide(partida)
    base = datos.base()
    kersh = GRUPO[0]
    poner_exp(una, kersh, experience.exp_list(base.actors[kersh])[29], 30)
    pelea = Pelea(una).abrir()
    s = una.simbolos
    d = s["BA_ONE"]
    campos = {"hp_max": d + s["BA_HPMAX"], "sp_max": d + s["BA_SPMAX"],
              "attack": d + s["BA_ATK"], "defense": d + s["BA_DEF"],
              "spirit": d + s["BA_SPI"], "agility": d + s["BA_AGI"]}
    de_la_rom = {k: pelea.palabra(v) for k, v in campos.items()}
    en_30 = modelo.actor_of(base, kersh, level=30)
    en_20 = modelo.actor_of(base, kersh)
    esperado = {k: getattr(en_30, k) for k in campos}
    assert de_la_rom == esperado
    assert all(esperado[k] != getattr(en_20, k) for k in campos), \
        "los seis parámetros del 30 tendrían que ser otros que los del 20"


def test_full_heal_llena_hasta_el_maximo_del_nivel_de_ahora(partida):
    """`FullHeal` es `SetHp(GetMaxHp())`, y el máximo es el del nivel que el
    actor tiene. Es el camino de `test_curar.py`, con un nivel que no es el
    de arranque."""
    from batalla import DESPUES_DE_PERDER, grupo_de, sin_hp
    una = partida(caso="pelea-82-curar")
    base = datos.base()
    sin_hp(una)
    actor = next(a for a in grupo_de(una) if ranura_exp(una, a) is not None)
    poner_exp(una, actor, experience.exp_list(base.actors[actor])[29], 30)
    una.correr(DESPUES_DE_PERDER)
    en_30 = modelo.actor_of(base, actor, level=30)
    assert (una.hp(actor),
            una.sp(actor)) == (en_30.hp_max, en_30.sp_max)
    assert en_30.hp_max != modelo.actor_of(base, actor).hp_max


# --- las habilidades del nivel ----------------------------------------------
#
# Lo que un actor sabe es un bit por par (actor, habilidad) en `FAR_SKILL` —ver
# `test_equipo_y_habilidades.py`—, y subir de nivel prende los de los pares que
# la tabla de aprendizaje del LDB enseña en cada nivel que pasa:
# `LearnLevelSkills(old_level + 1, new_level)`.
#
# El que sirve es Arden: ver `ARDEN` en `arnes/batalla.py`.


def test_subir_de_nivel_ensena_las_habilidades_de_cada_nivel_que_pasa(partida):
    """Arden entra en el 3 a 50 de lo que pide el 6 y el droide da 90: sube
    **tres niveles de una vez** y aprende lo del 4, el 5 y el 6, y no lo del
    7. Kersh pelea al lado para que la pelea se gane, y **detrás** de Arden:
    con el orden al revés el droide le pega a Arden hasta tirarlo, y lo que
    decide eso es el azar de la pelea, que el modelo juega igual."""
    from batalla import sabe
    base = datos.base()
    arden = base.actors[ARDEN]
    assert experience.initial_level(arden) == 3
    ensena = {nivel: s for nivel, s in arden.skills}
    assert {4, 5, 6, 7} <= set(ensena)
    lista = experience.exp_list(arden)
    una = en_el_droide(partida)
    grupo = (ARDEN, GRUPO[0])
    una.poner_grupo(*grupo)
    poner_exp(una, ARDEN, lista[5] - 50, 3)
    for nivel in (4, 5, 6, 7):
        assert not sabe(una, ARDEN, ensena[nivel]), \
            "Arden no tendría que saber todavía la %d" % ensena[nivel]
    esperado = ganar_al_droide(una, grupo=grupo, niveles={ARDEN: 3})
    assert ARDEN in {c.number for c in esperado.actors if c.alive}
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    assert experience.add_exp(arden, 3, lista[5] - 50, ganada) \
        == (6, lista[5] - 50 + ganada)
    assert exp_y_nivel(una, ARDEN) == (lista[5] - 50 + ganada, 6)
    for nivel in (4, 5, 6):
        assert sabe(una, ARDEN, ensena[nivel]), \
            "al pasar el %d Arden tendría que haber aprendido la %d" % (
                nivel, ensena[nivel])
    assert not sabe(una, ARDEN, ensena[7]), \
        "la %d es del 7, y Arden quedó en el 6" % ensena[7]


# --- lo que se ve -----------------------------------------------------------
#
# El nivel y los HP máximos del menú los compone la ROM de la partida, y se
# comparan pixel por
# pixel contra `menus.render_menu` y `menus.render_slots` con el mismo
# nivel. Los niveles son distintos entre sí y de los de arranque, y hay uno
# de una cifra y otro de dos, que es donde "%2d" y "/%d" se equivocan.
NIVELES_DEL_MENU = {14: 9, 11: 30}


def test_el_menu_muestra_el_nivel_y_el_maximo_de_ahora(partida):
    import pantallas
    from menu import GRUPO as GRUPO_MENU, ORO, abrir, con_grupo
    base = datos.base()
    assert set(NIVELES_DEL_MENU) == set(GRUPO_MENU)
    una = con_grupo(partida())
    exps = {}
    for actor, nivel in NIVELES_DEL_MENU.items():
        exps[actor] = experience.exp_list(base.actors[actor])[nivel - 1]
        poner_exp(una, actor, exps[actor], nivel)
    abrir(una)
    ahora = pantallas.menu(una.simbolos["SRAM_SLOTS"], GRUPO_MENU, ORO,
                           niveles=NIVELES_DEL_MENU, exps=exps)
    antes = pantallas.menu(una.simbolos["SRAM_SLOTS"], GRUPO_MENU, ORO)
    assert diferencia(una, ahora) == 0
    assert diferencia(una, antes) > 20, \
        "con los niveles de arranque el menú tendría que verse distinto"


def test_el_menu_muestra_guiones_en_el_nivel_tope(partida):
    """`DrawActorExp` en el nivel máximo: `GetNextExp` da -1 y el RPG_RT
    escribe guiones en las dos mitades. Es el otro camino de
    `menu_exp_paint`, que ningún nivel de arranque recorre: se pone a un
    actor en el tope y al otro un nivel antes, que todavía muestra números."""
    import pantallas
    from menu import GRUPO as GRUPO_MENU, ORO, abrir, con_grupo
    base = datos.base()
    una = con_grupo(partida())
    niveles, exps = {}, {}
    for n, actor in enumerate(GRUPO_MENU):
        tope = experience.max_level(base.actors[actor])
        niveles[actor] = tope - n
        exps[actor] = experience.exp_list(base.actors[actor])[tope - n - 1]
        poner_exp(una, actor, exps[actor], niveles[actor])
    abrir(una)
    ahora = pantallas.menu(una.simbolos["SRAM_SLOTS"], GRUPO_MENU, ORO,
                           niveles=niveles, exps=exps)
    # En el tope `GetNextExp` da -1, que es lo que escribe los guiones.
    assert experience.next_exp(base.actors[GRUPO_MENU[0]],
                               niveles[GRUPO_MENU[0]]) == -1
    assert diferencia(una, ahora) == 0


def test_la_ranura_muestra_el_nivel_que_tenia_esa_partida(partida):
    """`Window_SaveFile`: el nivel del líder **de la partida guardada**. Se
    guarda con Talan en el 9 y se lo baja al 5 antes de volver a abrir la
    pantalla, así que un 9 en la ranura sólo puede haber salido de la SRAM."""
    import pantallas
    from consola import TITULO_AIRE
    from menu import GRUPO as GRUPO_MENU, abrir, con_grupo
    base = datos.base()
    lider = GRUPO_MENU[0]
    una = con_grupo(partida())
    poner_exp(una, lider, experience.exp_list(base.actors[lider])[8], 9)
    abrir(una)
    for _ in range(3):                  # hasta Save
        una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)  # la pantalla de ranuras
    una.tocar_cuadros("a", TITULO_AIRE)  # guarda en la primera
    assert una.hay_partida(), "la partida no se guardó"
    poner_exp(una, lider, experience.exp_list(base.actors[lider])[4], 5)
    una.tocar_cuadros("a", TITULO_AIRE)  # y la vuelve a abrir
    ranuras = una.simbolos["SRAM_SLOTS"]
    llenas = [True] + [False] * (ranuras - 1)
    grupos = {0: GRUPO_MENU}
    ahora = pantallas.pantalla_de_ranuras(ranuras, llenas, 0, 1, grupos,
                                          {0: 9})
    assert diferencia(una, ahora) == 0
    otra = pantallas.pantalla_de_ranuras(ranuras, llenas, 0, 1, grupos,
                                         {0: 5})
    assert diferencia(una, otra) > 0
