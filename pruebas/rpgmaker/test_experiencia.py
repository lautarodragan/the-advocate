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
                          en_el_droide)


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
    base = db()
    esperado = modelo.Batalla(
        [modelo.actor_de(base, a, nivel=niveles.get(a)) for a in grupo],
        [modelo.enemigo_de(base, e, n)
         for n, e in enumerate(base.troops[TROPA_DROIDE].members)])
    for quien in esperado.actores:
        quien.hp = min(quien.hp_max, modelo.actor_de(base, quien.numero).hp)
        if quien.numero in caidos:
            quien.hp = 0
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * quien.numero,
                                 [quien.hp & 0xFF, quien.hp >> 8])
    pelea = Pelea(una).abrir()
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


# --- la subida de nivel -----------------------------------------------------

def test_ganar_sube_de_nivel_y_puede_subir_varios(partida):
    """El lazo de `ChangeExp`: sube mientras `GetNextExp(nivel)` alcance.

    Manta entra en el nivel 2 con 83 de experiencia, uno menos de lo que pide
    el 3, y el droide da 90: tiene que quedar en el 4, **dos niveles de una
    vez**, porque 173 pasa también los 172 del 4. Kersh entra a 50 de su
    siguiente nivel, que es la subida de a uno. Los dos números salen de
    `experiencia.sumar` y no de acá.

    De paso, Manta pelea en el nivel 2 y el modelo también: si la ROM armara
    la pelea con los parámetros del nivel de arranque, los turnos no
    coincidirían con los del modelo.
    """
    una = en_el_droide(partida)
    base = db()
    kersh, manta = GRUPO[0], GRUPO[2]
    lista = experiencia.lista_de(base.actors[kersh])
    nivel_k = experiencia.nivel_inicial(base.actors[kersh])
    poner_exp(una, kersh, lista[nivel_k] - 50, nivel_k)
    poner_exp(una, manta, 83, 2)
    esperado = ganar_al_droide(una, niveles={manta: 2})
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    assert {kersh, manta} <= {c.numero for c in esperado.actores if c.vivo}
    assert experiencia.sumar(base.actors[manta], 2, 83, ganada)[0] == 4, \
        "el caso quiere dos niveles de una vez para Manta"
    for actor, nivel, exp in ((kersh, nivel_k, lista[nivel_k] - 50),
                              (manta, 2, 83)):
        nivel, exp = experiencia.sumar(base.actors[actor], nivel, exp, ganada)
        assert exp_y_nivel(una, actor) == (exp, nivel), \
            "el actor %d quedó con %r y tendría que ser %r" % (
                actor, exp_y_nivel(una, actor), (exp, nivel))


def test_en_el_tope_no_sube_mas(partida):
    """`GetMaxLevel()`: con el `final_level` del LDB alcanzado, la experiencia
    se suma y el nivel no se mueve."""
    una = en_el_droide(partida)
    base = db()
    actor = GRUPO[0]
    tope = experiencia.nivel_max(base.actors[actor])
    lista = experiencia.lista_de(base.actors[actor])
    poner_exp(una, actor, lista[tope - 1] + 5, tope)
    ganar_al_droide(una, niveles={actor: tope})
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    assert exp_y_nivel(una, actor) == (lista[tope - 1] + 5 + ganada, tope)


def test_la_pelea_usa_los_parametros_del_nivel_de_ahora(partida):
    """`GetBaseMaxHp` y sus hermanas leen la curva del LDB **en el nivel que
    tiene**, no en el de arranque.

    Se le pone el nivel 30 a Kersh y se abre la pelea: los seis parámetros que
    la pelea arma —HP y SP máximos, ataque, defensa, espíritu y agilidad—
    tienen que ser los de `batalla.actor_de` con ese nivel, y distintos de
    los del 20, que si no el caso no distingue nada. Los cuatro del medio
    pasan por `eq_parametro`, que es también la de la pantalla de equipo.
    """
    una = en_el_droide(partida)
    base = db()
    kersh = GRUPO[0]
    poner_exp(una, kersh, experiencia.lista_de(base.actors[kersh])[29], 30)
    pelea = Pelea(una).abrir()
    s = una.simbolos
    d = s["BA_UNO"]
    campos = {"hp_max": d + s["BA_HPMAX"], "sp_max": d + s["BA_SPMAX"],
              "ataque": d + s["BA_ATK"], "defensa": d + s["BA_DEF"],
              "espiritu": d + s["BA_SPI"], "agilidad": d + s["BA_AGI"]}
    de_la_rom = {k: pelea.palabra(v) for k, v in campos.items()}
    en_30 = modelo.actor_de(base, kersh, nivel=30)
    en_20 = modelo.actor_de(base, kersh)
    esperado = {k: getattr(en_30, k) for k in campos}
    assert de_la_rom == esperado
    assert all(esperado[k] != getattr(en_20, k) for k in campos), \
        "los seis parámetros del 30 tendrían que ser otros que los del 20"


def test_full_heal_llena_hasta_el_maximo_del_nivel_de_ahora(partida):
    """`FullHeal` es `SetHp(GetMaxHp())`, y el máximo es el del nivel que el
    actor tiene. Es el camino de `test_curar.py`, con un nivel que no es el
    de arranque."""
    from test_curar import DESPUES_DE_PERDER, grupo_de, palabra_de, sin_hp
    una = partida(caso="pelea-82-curar")
    base = db()
    sin_hp(una)
    actor = next(a for a in grupo_de(una) if ranura_exp(una, a) is not None)
    poner_exp(una, actor, experiencia.lista_de(base.actors[actor])[29], 30)
    una.correr(DESPUES_DE_PERDER)
    en_30 = modelo.actor_de(base, actor, nivel=30)
    assert (palabra_de(una, "FAR_HP", actor),
            palabra_de(una, "FAR_SP", actor)) == (en_30.hp_max, en_30.sp_max)
    assert en_30.hp_max != modelo.actor_de(base, actor).hp_max


# --- las habilidades del nivel ----------------------------------------------
#
# Lo que un actor sabe es un bit por par (actor, habilidad) en `FAR_HAB` —ver
# `test_equipo_y_habilidades.py`—, y subir de nivel prende los de los pares que
# la tabla de aprendizaje del LDB enseña en cada nivel que pasa:
# `LearnLevelSkills(old_level + 1, new_level)`.
#
# El que sirve es Arden, el actor 15: arranca en el 3 y aprende la 148 en el 4,
# la 140 en el 5, la 139 en el 6 y la 255 en el 7. De los tres de la intro
# ninguno aprende nada nuevo después de su nivel de arranque.
ARDEN = 15


def test_subir_de_nivel_ensena_las_habilidades_de_cada_nivel_que_pasa(partida):
    """Arden entra en el 3 a 50 de lo que pide el 6 y el droide da 90: sube
    **tres niveles de una vez** y aprende lo del 4, el 5 y el 6, y no lo del
    7. Kersh pelea al lado para que la pelea se gane, y **detrás** de Arden:
    con el orden al revés el droide le pega a Arden hasta tirarlo, y lo que
    decide eso es el azar de la pelea, que el modelo juega igual."""
    from test_equipo_y_habilidades import sabe
    base = db()
    arden = base.actors[ARDEN]
    assert experiencia.nivel_inicial(arden) == 3
    ensena = {nivel: s for nivel, s in arden.skills}
    assert {4, 5, 6, 7} <= set(ensena)
    lista = experiencia.lista_de(arden)
    una = en_el_droide(partida)
    grupo = (ARDEN, GRUPO[0])
    una.poner_grupo(*grupo)
    poner_exp(una, ARDEN, lista[5] - 50, 3)
    for nivel in (4, 5, 6, 7):
        assert not sabe(una, ARDEN, ensena[nivel]), \
            "Arden no tendría que saber todavía la %d" % ensena[nivel]
    esperado = ganar_al_droide(una, grupo=grupo, niveles={ARDEN: 3})
    assert ARDEN in {c.numero for c in esperado.actores if c.vivo}
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    assert experiencia.sumar(arden, 3, lista[5] - 50, ganada) \
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
# El nivel y los HP máximos del menú eran tiras del cartucho con el nivel de
# arranque. Ahora los compone la ROM de la partida, y se comparan pixel por
# pixel contra `titulo.render_menu` y `titulo.render_ranuras` con el mismo
# nivel. Los niveles son distintos entre sí y de los de arranque, y hay uno
# de una cifra y otro de dos, que es donde "%2d" y "/%d" se equivocan.
NIVELES_DEL_MENU = {14: 9, 11: 30}


def diferencia(una, esperada):
    from tanda import quince_bits
    captura = una.imagen().convert("RGB")
    return sum(1 for x, y in zip(quince_bits(captura), quince_bits(esperada))
               if x != y)


def referencias():
    from port import ventana
    from render.render_map import GAME_DIR
    base = db()
    return base, ventana.skin(GAME_DIR, base.system_name), GAME_DIR


def test_el_menu_muestra_el_nivel_y_el_maximo_de_ahora(partida):
    from port import titulo
    from test_menu import GRUPO as GRUPO_MENU, ORO, abrir, con_grupo
    base, skin, game_dir = referencias()
    assert set(NIVELES_DEL_MENU) == set(GRUPO_MENU)
    una = con_grupo(partida())
    for actor, nivel in NIVELES_DEL_MENU.items():
        poner_exp(una, actor,
                  experiencia.lista_de(base.actors[actor])[nivel - 1], nivel)
    abrir(una)
    ahora = titulo.render_menu(skin, base, una.simbolos["SRAM_RANURAS"],
                               GRUPO_MENU, ORO, 0, True, base.font_id, None,
                               game_dir, niveles=NIVELES_DEL_MENU)
    antes = titulo.render_menu(skin, base, una.simbolos["SRAM_RANURAS"],
                               GRUPO_MENU, ORO, 0, True, base.font_id, None,
                               game_dir)
    assert diferencia(una, ahora) == 0
    assert diferencia(una, antes) > 20, \
        "con los niveles de arranque el menú tendría que verse distinto"


def test_la_ranura_muestra_el_nivel_que_tenia_esa_partida(partida):
    """`Window_SaveFile`: el nivel del líder **de la partida guardada**. Se
    guarda con Talan en el 9 y se lo baja al 5 antes de volver a abrir la
    pantalla, así que un 9 en la ranura sólo puede haber salido de la SRAM."""
    from port import titulo
    from consola import TITULO_AIRE
    from test_menu import GRUPO as GRUPO_MENU, abrir, con_grupo, tocar
    base, skin, game_dir = referencias()
    lider = GRUPO_MENU[0]
    una = con_grupo(partida())
    poner_exp(una, lider, experiencia.lista_de(base.actors[lider])[8], 9)
    abrir(una)
    for _ in range(3):                  # hasta Save
        tocar(una, "down")
    tocar(una, "a", TITULO_AIRE)        # la pantalla de ranuras
    tocar(una, "a", TITULO_AIRE)        # guarda en la primera
    assert una.sram(0x100, 4) == b"ABLS", "la partida no se guardó"
    poner_exp(una, lider, experiencia.lista_de(base.actors[lider])[4], 5)
    tocar(una, "a", TITULO_AIRE)        # y la vuelve a abrir
    ranuras = una.simbolos["SRAM_RANURAS"]
    llenas = [True] + [False] * (ranuras - 1)
    grupos = {0: GRUPO_MENU}
    ahora = titulo.render_ranuras(skin, base, ranuras, llenas, 0, 1,
                                  base.font_id, grupos, game_dir, {0: 9})
    assert diferencia(una, ahora) == 0
    otra = titulo.render_ranuras(skin, base, ranuras, llenas, 0, 1,
                                 base.font_id, grupos, game_dir, {0: 5})
    assert diferencia(una, otra) > 0
