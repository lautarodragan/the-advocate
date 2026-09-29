"""La batalla por turnos: los HP, el daño, el orden de turnos y por dónde sigue
la página.

Es la mitad de la red que la tanda de pixeles no puede cubrir. Los casos
de `test_batalla_golden.py` comparan **la pantalla** contra su
golden y no pueden hacer más: la pelea bloquea adentro del intérprete y no
cuesta ningún tick —ver `OP_BATTLE` en tools/port/events.py—. Lo que pasa adentro
se mira desde acá.

**Lo que hace fuerte a este archivo** es que no se conforma con "bajó": el
modelo de `tools/port/battle.py` juega la misma pelea con el mismo azar y las
mismas fórmulas, y la prueba exige que la consola dé **el número exacto** en
cada HP, turno por turno. Si la ROM y el modelo se separan en un tiro de dado
o en una división, el primer turno ya no coincide.

Las dos peleas de la intro:

    mapa 2  FightableDroid  tropa 82  Sentry Drone x1
    mapa 9  EV0004          tropa 86  GangMember LT x4

Acá se pelea la primera. La tropa de cuatro enemigos la ejercitan los casos
`batalla` de `test_batalla_golden.py`, con la página de prueba.
"""

from port import rules
from port import battle as modelo

from batalla import (DROIDE, GRUPO, TROPA_DROIDE, Pelea, en_el_droide, hab_id,
                     modelo_de)
from consola import en_la_rom, en_la_wram
import datos
from tanda import LINKAGE

# Las habilidades que el grupo de la intro sabe, por si alguna prueba quiere
# nombrarlas. Salen de `battle.skills_of`, que es lo que decide el orden.
FURY_PUNCH, MINDSHIELD, HEALING_SYRINGE, AGENCY_BADGE = 129, 143, 131, 146
# La Potion del LDB: cincuenta HP planos, que es el ítem de curar más barato
# y el único que hace falta para cobrar la cuenta.
POCION = 1
# Y uno que **no** se puede usar en una pelea: el Theatre Key, un ítem de
# trama. Va en el inventario a propósito, para que la lista tenga algo que
# dejar afuera; sin él, ofrecer todo y ofrecer lo correcto dan lo mismo.
LLAVE = 151
# El nombre de la constante de la ROM para cada caso del reparto.
PENDIENTE_DE = {"errar": "BA_SE_ERRAR",
                "dano_actor": "BA_SE_DANO_ACTOR",
                "dano_enemigo": "BA_SE_DANO_ENEMIGO",
                "muerte": "BA_SE_MUERTE"}


# --- los HP como estado ----------------------------------------------------

def test_los_hp_arrancan_llenos(partida):
    """`Game_Actor::Setup`: un actor nuevo arranca con los HP del nivel."""
    una = partida()
    base = datos.base()
    for actor in GRUPO:
        esperado = rules.param_of(base.actors[actor], "maxhp")
        assert esperado > 40, (
            "el actor %d tendría que tener los HP de su nivel inicial y no "
            "los del 1: si son 40 el caso no distingue nada" % actor)
        assert una.hp(actor) == esperado, \
            "el actor %d no arranca con los HP de su nivel" % actor


def test_los_hp_viajan_en_la_partida(partida):
    """Bajarlos, guardar y volver a cargar tiene que devolver los mismos.

    Es lo que obliga a que `FAR_HP` esté en `partida_tabla`: sin eso una
    partida cargada después de una pelea volvería con todos llenos.

    La prueba **resetea la consola de verdad**, como `test_guardar.py`: la
    SRAM sobrevive al reset y por eso lo que vuelve salió del cartucho. Se
    pisan los HP en la RAM antes de reiniciar porque snes9x no la borra, así
    que sin eso el 7 podría ser el de antes.
    """
    una = partida(caso="guardar-198")
    una.poner_hp(GRUPO[0], 7)
    una.guardar_en()
    una.poner_hp(GRUPO[0], 99)
    una.reiniciar()
    assert una.hp(GRUPO[0]) == 7, \
        "los HP no volvieron de la SRAM: quedaron en %d" \
        % una.hp(GRUPO[0])


# --- los SP como estado ----------------------------------------------------

def test_los_sp_arrancan_llenos(partida):
    """Lo mismo que los HP, y por el mismo `Game_Actor::Setup`.

    Los SP son estado desde que una habilidad cuesta su `sp_cost`: sin esto
    todas saldrían gratis siempre.

    **Se miran todos los actores del LDB y no sólo los tres del grupo**, y el
    caso lo exige: los tres de la intro tienen los mismos HP que SP —Kersh
    168/168, Core y Manta 127/127— así que llenar `FAR_SP` desde `actor_hpmax`
    pasaría desapercibido. Comprobado en rojo con ese defecto puesto: con el
    grupo solo daba verde. Los que sí distinguen son los otros, como el actor 2
    —52 HP y 0 SP— o el 38, 193 contra 79.
    """
    una = partida()
    base = datos.base()
    distintos = 0
    for actor in sorted(base.actors):
        esperado = rules.param_of(base.actors[actor], "maxsp")
        distintos += (esperado
                      != rules.param_of(base.actors[actor], "maxhp"))
        assert una.sp(actor) == esperado, \
            "el actor %d no arranca con los SP de su nivel" % actor
    assert distintos > 10, (
        "si ningún actor tuviera SP distintos de sus HP este caso no "
        "distinguiría de qué tabla se llenó FAR_SP")
    for actor in GRUPO:
        assert rules.param_of(base.actors[actor], "maxsp") > 40, (
            "el actor %d tendría que tener los SP de su nivel inicial: con "
            "los del 1 no alcanzan para ninguna habilidad" % actor)


def test_los_sp_viajan_en_la_partida(partida):
    """`FAR_SP` en `partida_tabla`, como `FAR_HP`.

    Gastar SP en una pelea y guardar tiene que devolver los mismos al cargar;
    sin el renglón de la tabla volverían llenos. Resetea la consola de verdad
    —la SRAM sobrevive— y pisa la RAM antes, porque snes9x no la borra.
    """
    una = partida(caso="guardar-198")
    una.poner_sp(GRUPO[0], 7)
    una.guardar_en()
    una.poner_sp(GRUPO[0], 99)
    una.reiniciar()
    assert una.sp(GRUPO[0]) == 7, \
        "los SP no volvieron de la SRAM: quedaron en %d" \
        % una.sp(GRUPO[0])


# --- la pelea del droide ---------------------------------------------------

def test_la_pelea_del_droide_se_abre_con_la_tropa_del_juego(partida):
    """El `EnemyEncounter` del `FightableDroid`: tropa 82, un Sentry Drone.

    Los parámetros del enemigo salen del LDB y los del grupo de
    `eq_parametro`, la misma función que la pantalla de equipo. Que coincidan
    con `battle.py` es lo que hace que el resto de este archivo signifique
    algo: si la ROM peleara con otros números, los turnos también darían otra
    cosa y no se sabría cuál de las dos está mal.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    esperado = modelo_de(base)
    assert pelea.byte("BA_NACT") == 3
    assert pelea.byte("BA_NENE") == 1
    for k, quien in enumerate(esperado.actors + [None] + esperado.enemies):
        if quien is None:
            continue
        d = una.simbolos["BA_UNO"] + k * una.simbolos["BA_BYTES"]
        assert pelea.palabra(d + 0) == quien.hp, "los HP del %d" % k
        assert pelea.palabra(d + 4) == quien.attack, "el ataque del %d" % k
        assert pelea.palabra(d + 6) == quien.defense, "la defensa del %d" % k
        assert pelea.palabra(d + 8) == quien.agility, "la agilidad del %d" % k


def test_la_chance_de_huir_es_la_de_rm2k(partida):
    """`Scene_Battle::InitEscapeChance`, con la división entera de los dos
    lados. Con el droide da cero: es cinco veces más ágil que el grupo."""
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    assert pelea.byte("BA_HUIDA") == modelo_de(datos.base()).escape_chance


def test_la_pelea_entera_da_los_mismos_hp_que_el_modelo(partida):
    """El corazón de todo esto: turno por turno, el mismo número.

    Los tres actores atacan al droide y la consola tiene que llegar al mismo HP
    que `battle.Battle` en cada uno de los doce valores. Ahí adentro están el
    orden de turnos, los tres tiros de cada golpe —acierto, crítico y
    varianza—, el daño con `atk / 2 - def / 4`, la mitad del que se defiende y
    el reapuntado del blanco muerto. **Si cualquiera de esos se separa, el
    primer turno ya no coincide.**

    Con estos números la pelea la gana el grupo en tres turnos y Core cae en el
    segundo, así que el caso además pasa por un actor muerto —que no actúa y al
    que el droide ya no puede elegir— sin tener que forzarlo.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(datos.base())
    for turno in range(1, 8):
        pelea.turno(len(esperado.living(esperado.actors)))
        esperado.play_turn(
            [(modelo.COMMAND_ATTACK, 0)] * len(esperado.living(esperado.actors)))
        de_la_rom = ([pelea.hp_del_combatiente(k)
                      for k in range(len(GRUPO))]
                     + [pelea.hp_del_combatiente(
                         una.simbolos["BA_GRUPO_MAX"])])
        del_modelo = [c.hp for c in esperado.actors] + [esperado.enemies[0].hp]
        assert de_la_rom == del_modelo, \
            "turno %d: la consola dejó %r y el modelo %r" % (
                turno, de_la_rom, del_modelo)
        if esperado.result is not None:
            break
    assert esperado.result == modelo.VICTORY, \
        "la pelea de banco tendría que terminar en victoria"
    assert pelea.modo() == "FIN"
    assert pelea.byte("BA_RESULT") == modelo.VICTORY


# --- las habilidades ---------------------------------------------------------
#
# Todas comparan contra `battle.Battle.use_skill`, que es
# `Game_BattleAlgorithm::Skill` de easyrpg. Lo que hace fuerte a esta tanda es
# lo mismo que al resto del archivo: no se conforma con "bajó", exige **el
# número exacto**, y el número sale de un modelo que consume el azar en el
# mismo orden que la ROM. Si la ROM tirara un dado de más o de menos, el primer
# turno ya no coincidiría.


def habilidades(base, actor):
    return modelo.skills_of(base, actor)


def test_cada_actor_sabe_las_habilidades_de_su_nivel(partida):
    """`actor_hab`, contra `battle.skills_of`.

    Kersh 131 y 146, Core 129 y 150, Manta 130, 143, 144 y 150: las que el LDB
    dice que se aprenden en un nivel menor o igual al suyo. Con nivel 1 **las
    tres listas estarían vacías**, porque la primera se aprende en el 3; el
    caso exige que no lo estén para no pasar mirando ceros.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    esperado = {11: [131, 146], 12: [129, 150], 13: [130, 143, 144, 150]}
    for actor, cuales in esperado.items():
        assert habilidades(base, actor) == cuales, (
            "el modelo dice que el actor %d sabe %r y el LDB %r"
            % (actor, habilidades(base, actor), cuales))
    # Y la ROM, que arma la lista al entrar al menú de cada actor.
    for k, actor in enumerate(GRUPO):
        pelea.esperar("ORDEN")
        assert pelea.byte("BA_ACTOR") == k
        pelea.tocar_cuadros("right")
        pelea.tocar_cuadros()
        pelea.esperar("HAB")
        assert pelea.byte("BA_HAB_N") == len(esperado[actor]), (
            "la ROM le dio %d habilidades al actor %d y sabe %d"
            % (pelea.byte("BA_HAB_N"), actor, len(esperado[actor])))
        # Y que sean **las mismas y en el mismo orden**: `BA_HAB_LISTA` lleva
        # el `k` del cartucho y `hab_id` lo traduce al número de RM2k.
        lista = una.consola.ram(una.simbolos["BA_HAB_LISTA"],
                                pelea.byte("BA_HAB_N"))
        numeros = [hab_id(una, n) for n in lista]
        assert numeros == esperado[actor], (
            "la ROM le dio %r al actor %d" % (numeros, actor))
        pelea.tocar_cuadros("b")
        pelea.ordenar(("defender",))    # para pasar al que sigue
    pelea.correr_turno()


def test_una_habilidad_de_dano_da_el_mismo_hp_y_los_mismos_sp(partida):
    """Fury Punch de Core contra el droide, turno por turno.

    Es el caso central de las habilidades: adentro están `CalcSkillEffect`
    —`power + physical_rate * atk / 20 + magical_rate * spi / 40` menos la
    defensa y el espíritu del blanco—, el tiro del crítico que se hace aunque
    la chance sea cero, la varianza con el `variance` de la habilidad y el
    costo en SP, que se descuenta al ejecutarla y no al elegirla.

    Los otros dos se defienden, así que lo único que le pega al droide es la
    habilidad: si la cuenta se separara en un punto, el HP del droide lo dice.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    esperado = modelo_de(base)
    fury = base.skills[FURY_PUNCH]
    assert habilidades(base, GRUPO[1])[0] == FURY_PUNCH
    for turno in range(1, 4):
        pelea.ordenar(("defender",))
        pelea.ordenar(("habilidad", 0, 0))
        pelea.ordenar(("defender",))
        pelea.correr_turno()
        esperado.play_turn([(modelo.COMMAND_DEFEND, 0),
                            (modelo.COMMAND_SKILL, (fury, 0)),
                            (modelo.COMMAND_DEFEND, 0)])
        de_la_rom = ([pelea.hp_del_combatiente(k)
                      for k in range(len(GRUPO))]
                     + [pelea.hp_del_combatiente(
                         una.simbolos["BA_GRUPO_MAX"])])
        del_modelo = [c.hp for c in esperado.actors] + [
            esperado.enemies[0].hp]
        assert de_la_rom == del_modelo, \
            "turno %d: la consola dejó %r y el modelo %r" % (
                turno, de_la_rom, del_modelo)
        assert pelea.sp_del_combatiente(1) == esperado.actors[1].sp, \
            "turno %d: los SP de Core, %d contra %d" % (
                turno, pelea.sp_del_combatiente(1), esperado.actors[1].sp)
        if esperado.result is not None:
            break
    assert esperado.actors[1].sp < esperado.actors[1].sp_max, \
        "si la habilidad no costara SP este caso no distinguiría el costo"


def test_una_habilidad_de_switch_prende_su_switch(partida):
    """`Skill::vExecute` con `type == switch`: `SetAffectedSwitch(switch_id)`.

    MindShield, la segunda de Manta, prende el switch 136 y no hace nada más
    —ni daño, ni tiros de azar—. Es lo que hace que tres de las siete
    habilidades del grupo sean baratas de portar.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    assert habilidades(base, GRUPO[2])[1] == MINDSHIELD
    switch = base.skills[MINDSHIELD].switch_id
    assert not pelea.switch(switch), \
        "el switch tenía que arrancar apagado: si ya estuviera prendido el " \
        "caso no distinguiría nada"
    pelea.ordenar(("defender",))
    pelea.ordenar(("defender",))
    pelea.ordenar(("habilidad", 1))
    pelea.correr_turno()
    assert pelea.switch(switch), \
        "MindShield tenía que prender el switch %d" % switch
    esperado = modelo_de(base)
    esperado.play_turn([(modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_SKILL,
                         (base.skills[MINDSHIELD], 0))])
    assert esperado.switches == [switch]
    assert pelea.sp_del_combatiente(2) == esperado.actors[2].sp, \
        "los SP de Manta, %d contra %d" % (pelea.sp_del_combatiente(2),
                                           esperado.actors[2].sp)
    # Y el azar **no se movió**: una de switch vuelve antes de cualquier tiro.
    # Si la ROM tirara un dado de más, los HP del turno siguiente no darían.
    de_la_rom = ([pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
                 + [pelea.hp_del_combatiente(una.simbolos["BA_GRUPO_MAX"])])
    del_modelo = [c.hp for c in esperado.actors] + [esperado.enemies[0].hp]
    assert de_la_rom == del_modelo, \
        "la consola dejó %r y el modelo %r" % (de_la_rom, del_modelo)


def test_una_habilidad_que_cura_apunta_al_grupo(partida):
    """Healing Syringe, la primera de Kersh: `scope` 3, o sea un aliado.

    Se le da a Core, que arranca con la mitad de los HP para que la cura tenga
    dónde entrar; sin eso `ChangeHp` la topa contra el máximo y el caso no
    distinguiría entre curar bien y no curar nada.
    """
    una = en_el_droide(partida)
    base = datos.base()
    assert habilidades(base, GRUPO[0])[0] == HEALING_SYRINGE
    lastimado = rules.param_of(base.actors[GRUPO[1]], "maxhp") // 2
    una.poner_hp(GRUPO[1], lastimado)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(base)
    esperado.actors[1].hp = lastimado
    assert pelea.hp_del_combatiente(1) == lastimado, \
        "la pelea tenía que arrancar con Core lastimado"
    pelea.ordenar(("habilidad", 0, 1))
    pelea.ordenar(("defender",))
    pelea.ordenar(("defender",))
    pelea.correr_turno()
    esperado.play_turn([(modelo.COMMAND_SKILL,
                         (base.skills[HEALING_SYRINGE], 1)),
                        (modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_DEFEND, 0)])
    assert pelea.hp_del_combatiente(1) == esperado.actors[1].hp, \
        "los HP de Core: la consola %d y el modelo %d" % (
            pelea.hp_del_combatiente(1), esperado.actors[1].hp)
    assert esperado.actors[1].hp > lastimado, \
        "si la habilidad no curara nada el caso no distinguiría"
    assert pelea.sp_del_combatiente(0) == esperado.actors[0].sp


def test_una_habilidad_modifica_los_parametros_del_blanco(partida):
    """Agency Badge, la segunda de Kersh: baja ataque, defensa y agilidad.

    Es lo único de las siete que pide estado nuevo por combatiente —el
    modificador de cada parámetro y su base, que es lo que
    `CanChangeAtkModifier` necesita para topar la bajada en la mitad del base—
    y por eso agranda `BA_BYTES`.

    Se compara el parámetro **efectivo** del droide contra el del modelo, que
    es `AdjustParam`: `clamp(base + modificador, 1, 999)`.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    assert habilidades(base, GRUPO[0])[1] == AGENCY_BADGE
    esperado = modelo_de(base)
    # La ranura del droide: la primera de enemigos, detrás de las del grupo.
    s = una.simbolos
    del_droide = s["BA_UNO"] + s["BA_GRUPO_MAX"] * s["BA_BYTES"]
    antes = pelea.palabra(del_droide + s["BA_ATK"])
    pelea.ordenar(("habilidad", 1, 0))
    pelea.ordenar(("defender",))
    pelea.ordenar(("defender",))
    pelea.correr_turno()
    esperado.play_turn([(modelo.COMMAND_SKILL,
                         (base.skills[AGENCY_BADGE], 0)),
                        (modelo.COMMAND_DEFEND, 0),
                        (modelo.COMMAND_DEFEND, 0)])
    droide = esperado.enemies[0]
    for nombre, campo, valor in (("ataque", "BA_ATK", droide.attack),
                                 ("defensa", "BA_DEF", droide.defense),
                                 ("agilidad", "BA_AGI", droide.agility)):
        de_la_rom = pelea.palabra(del_droide + s[campo])
        assert de_la_rom == valor, \
            "el %s del droide: la consola %d y el modelo %d" % (
                nombre, de_la_rom, valor)
    assert droide.attack < antes, \
        "Agency Badge tiene que bajarle el ataque: si no, el caso no " \
        "distingue entre aplicar el modificador y no aplicarlo"


def test_ganar_sigue_por_el_victory_handler(partida):
    """`VictoryHandler`: los dos cuadros de texto de CORE y KERSH.

    Es lo que cobra el parcheo de los tres destinos del opcode: si el cursor
    volviera al comando siguiente en vez de saltar al manejador, la página
    terminaría ahí y no se vería ningún mensaje. Y los HP con los que se salió
    de la pelea tienen que quedar en la partida.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(datos.base())
    while esperado.result is None:
        pelea.turno(len(esperado.living(esperado.actors)))
        esperado.play_turn(
            [(modelo.COMMAND_ATTACK, 0)] * len(esperado.living(esperado.actors)))
    quedaron = [pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
    pelea.cerrar()
    assert [una.hp(a) for a in GRUPO] == quedaron, \
        "los HP de la pelea no quedaron en la partida"
    mensajes = 0
    for _ in range(600):
        if una.byte("msg_abierto"):
            mensajes += 1
            una.tocar_ticks("a")
        else:
            una.correr(1)
        if mensajes and not una.corriendo_una_pagina():
            break
    assert mensajes == 2, \
        "el VictoryHandler abre dos cuadros de texto y abrió %d" % mensajes
    assert una.mapa() == 2, "la pelea tiene que volver al mapa donde estaba"


def test_perder_sigue_por_el_defeat_handler(partida):
    """`DefeatHandler`: con `defeat_mode` 1 no hay Game Over, sigue la página.

    Se llega poniéndole un HP a cada uno antes de pelear, que es lo que hace
    comprobable un camino que jugando cuesta media hora de mala suerte.
    """
    una = en_el_droide(partida)
    for actor in GRUPO:
        una.poner_hp(actor, 1)
    pelea = Pelea(una).abrir()
    # **Se defienden en vez de atacar**: con su nivel del LDB los actores
    # matan al droide en tres golpes, antes de que él mate a nadie, y la pelea
    # terminaría en victoria. Con
    # `Defend` el único que actúa es él.
    for _ in range(12):
        if pelea.modo() == "FIN":
            break
        for _ in range(3):
            for _ in range(400):
                if pelea.modo() != "ORDEN":
                    break
                # **Dos derechas**: el menú tiene el orden del original y
                # `Defend` es la tercera orden.
                pelea.tocar_cuadros("right")
                pelea.tocar_cuadros("right")
                pelea.tocar_cuadros()
        for _ in range(400):
            if pelea.modo() in ("ORDEN", "FIN"):
                break
            pelea.tocar_cuadros()
    assert pelea.byte("BA_RESULT") == modelo.DEFEAT, \
        "con un HP cada uno la pelea se pierde"
    pelea.cerrar()
    mensajes = 0
    for _ in range(600):
        if una.byte("msg_abierto"):
            mensajes += 1
            una.tocar_ticks("a")
        else:
            una.correr(1)
        if mensajes and not una.corriendo_una_pagina():
            break
    assert mensajes == 1, \
        "el DefeatHandler abre un cuadro de texto y abrió %d" % mensajes


def test_la_pelea_no_gasta_ningun_tick(partida):
    """La regla que sostiene la comparación de pixeles: `vueltas` no avanza
    mientras se ve la pantalla.

    Es lo mismo que la pantalla de ranuras y la tienda, y es lo que deja que
    la pelea salga del opcode en el mismo tick tarde lo que tarde el jugador:
    lo que la tanda ve después de una pelea no depende de cuánto duró.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    antes = una.palabra("vueltas")
    una.consola.run(240)
    assert una.palabra("vueltas") == antes, \
        "el reloj del juego corrió durante la batalla"


# --- el audio de la pelea --------------------------------------------------
#
# Esto es lo que ninguna prueba de pixeles puede ver: **el silencio no cambia
# un pixel**. El caso `batalla` de `test_batalla_golden.py` compara la
# pantalla y da cero con la pelea muda.
#
# Lo que se pregunta acá es lo mismo que en `test_musica_paquete.py`: qué dice
# la ROM estar tocando, y si lo que dice tocar tiene sus muestras arriba.

def sonido_muestra(una, indice):
    """La muestra que le toca a una fila de `sonido_tabla`, leída del
    cartucho: siete bytes por entrada y la muestra es el primero.

    Se lee de la ROM y no se recalcula, por lo mismo que `muestras_del_tema`:
    recalcularla sería una segunda manera de contestar la pregunta, y las dos
    se pueden equivocar igual.
    """
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    return rom[en_la_rom(una.simbolos["sonido_tabla"]) + 7 * indice]


def se_disparado(una):
    """La muestra del efecto que la ROM acaba de dejar pendiente.

    `op_sound` y `sound_play` copian los siete bytes de la fila a `SE_NEW`
    y prenden `SE_PENDING`; `irq_music` lo levanta en el cuadro siguiente y
    a partir de ahí lo que queda es `SE_FRAMES`. Acá se mira `SE_NEW`, que
    es lo que sobrevive a leer la RAM entre cuadro y cuadro.

    Hay dos voces de efectos, y el nuevo cae en la que `sound_play` elija,
    así que se mira el más reciente de las dos: el pendiente, o si no el que
    lleva menos cuadros sonando —los que pide la fila, en `SE_NEW + 5`,
    menos los que le quedan—. Mirar sólo la primera voz daba rojo cuando la
    tenía ocupada un efecto anterior.
    """
    def estado(prefijo):
        ram = una.consola.ram
        nuevo = ram(en_la_wram(una.simbolos[prefijo + "NEW"]), 7)
        quedan = ram(en_la_wram(una.simbolos[prefijo + "FRAMES"]), 2)
        pendiente = ram(en_la_wram(una.simbolos[prefijo + "PENDING"]), 1)[0]
        quedan = quedan[0] | quedan[1] << 8
        sonando = (nuevo[5] | nuevo[6] << 8) - quedan
        # Una voz callada va última, sonara o no alguna vez; si las dos lo
        # están, gana la primera, que es la que se miraba con una sola voz.
        callada = not pendiente and not quedan
        return callada, (-1 if pendiente else sonando), nuevo[0]
    return min(estado("SE_"), estado("SE2_"))[-1]


def test_la_pelea_prende_el_tema_de_batalla_del_ldb(partida):
    """`Scene_Battle`, al construirse: `BgmPlay(GetSystemBGM(BGM_Battle))`.

    El tema sale del LDB —`battle_music`, que en el ABL es
    T_VGFighterMAX_Masako— y no de una elección nuestra, igual que el de la
    pantalla de título. Y no alcanza con que `tema_actual` lo diga: las
    muestras que su stream escribe en SRCN tienen que estar en la ARAM, o son
    notas contra el bloque de silencio. Por eso el tema se anota en el paquete
    de audio **del mapa que tiene la pelea**, que es lo que hace
    `events.battle_audio`.
    """
    una = en_el_droide(partida)
    tema = una.simbolos["BA_TEMA"]
    assert tema != 0xFF, "esta ROM no lleva tema de batalla: el caso no mide nada"
    Pelea(una).abrir()
    assert una.palabra("tema_actual") == tema, (
        "la pelea dice estar tocando el tema %d y el de batalla es el %d"
        % (una.palabra("tema_actual"), tema))
    assert not una.byte("music_apagada"), \
        "la pelea arrancó callada: `battle_bgm` no llegó a prender el tema"
    faltan = sorted(set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema de batalla suena con las muestras %s sin subir de las %s que "
        "usa" % (faltan, sorted(una.muestras_del_tema(tema))))


def cursor_del_stream(una):
    """Por dónde va el stream de música: los tres bytes de `music`.

    Avanza solo y nunca vuelve atrás mientras dure un tema —el de batalla son
    226 segundos y ninguna de estas peleas llega—, así que verlo **bajar** es
    ver un `music_start`.
    """
    bajo, alto, banco = una.consola.ram(una.simbolos["music"], 3)
    return bajo | (alto << 8) | (banco << 16)


def test_ganar_prende_el_tema_de_la_victoria(partida):
    """El `BGM_Victory` de `Scene_Battle_Rpg2k`, al quedarse sin enemigos.

    En el ABL `battle_end_music` es **el mismo** que `battle_music`, así que
    mirar `tema_actual` no distingue nada: ya vale eso desde que la pelea
    empezó, y sacarle el `music_start` del final da verde igual. Lo que sí se
    ve es que el stream **vuelve a empezar**, que es lo que `music_start`
    hace: el cursor de `music` avanza solo y nunca retrocede.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(datos.base())
    antes = None
    while esperado.result is None:
        antes = cursor_del_stream(una)
        pelea.turno(len(esperado.living(esperado.actors)))
        esperado.play_turn(
            [(modelo.COMMAND_ATTACK, 0)] * len(esperado.living(esperado.actors)))
    assert pelea.byte("BA_RESULT") == modelo.VICTORY
    assert una.palabra("tema_actual") == una.simbolos["BA_TEMA_FIN"], \
        "al ganar tiene que sonar el battle_end_music del LDB"
    assert not una.byte("music_apagada")
    assert cursor_del_stream(una) < antes, (
        "el tema de la victoria tiene que arrancar de cero: el cursor del "
        "stream quedó en $%06X y antes del último turno estaba en $%06X"
        % (cursor_del_stream(una), antes))


def test_al_terminar_vuelve_lo_que_sonaba_en_el_mapa(partida, con_musica):
    """El `before_battle_music` de RM2k: `Scene_Battle` lo anota al entrar y
    `Game_Map` lo repone al volver.

    El mapa 2 **no trae música**, así que sin un tema sonando lo que
    tiene que volver es el silencio —y eso no distingue nada: al salir se
    recarga el paquete del mapa, y recargarlo ya calla—. Con un tema puesto el
    caso mide de verdad: si el `battle_bgm` del final no estuviera, el mapa
    quedaría mudo después de cada pelea.

    Y además el tema del mapa tiene que volver **con sus muestras**: el
    paquete de la pelea las desaloja, así que salir sin recargar el del mapa
    dejaría el tema sonando contra el bloque de silencio.
    """
    una = en_el_droide(partida, con_musica)
    tema = una.palabra("tema_actual")
    assert not una.byte("music_apagada"), \
        "el mapa tenía que arrancar con su tema: el caso no mide nada"
    pelea = Pelea(una).abrir()
    assert una.palabra("tema_actual") == una.simbolos["BA_TEMA"], \
        "la pelea tiene que tapar el tema del mapa"
    esperado = modelo_de(datos.base())
    while esperado.result is None:
        pelea.turno(len(esperado.living(esperado.actors)))
        esperado.play_turn(
            [(modelo.COMMAND_ATTACK, 0)] * len(esperado.living(esperado.actors)))
    pelea.cerrar()
    # Y hay que dejarla terminar: reponer el paquete del mapa son **65 cuadros
    # medidos**, porque son cincuenta kilobytes que viajan al SPC700 por los
    # cuatro puertos. `cerrar` vuelve en cuanto `menu_abierto` se apaga, que es
    # antes; sin esperar, lo que se mira es una ARAM a medio llenar.
    for _ in range(300):
        if una.palabra("tema_actual") == tema and not una.byte("music_apagada"):
            break
        una.consola.run(1)
    assert not una.byte("music_apagada"), \
        "al salir de la pelea el mapa se quedó mudo"
    assert una.palabra("tema_actual") == tema, (
        "al salir de la pelea tenía que volver el tema %d y quedó el %d"
        % (tema, una.palabra("tema_actual")))
    faltan = sorted(set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema del mapa volvió con las muestras %s sin subir: el paquete de "
        "la pelea las desalojó y nadie recargó el del mapa" % faltan)


def mirar_los_golpes(una, pelea, esperados):
    """Va por los mensajes de un turno mirando qué efecto salió en cada golpe.

    Devuelve qué casos del reparto se vieron, para que la prueba pueda exigir
    que alguno se haya visto: un turno que no llegue a ningún golpe no
    probaría nada.
    """
    vistos = set()
    for _ in range(30):
        if pelea.modo() != "MENSAJE":
            break
        if pelea.byte("BA_MTIPO") != una.simbolos["BA_MSG_ATAQUE"]:
            pelea.tocar_cuadros()
            continue
        dano = pelea.palabra(una.simbolos["BA_MDANO"])
        blanco = pelea.byte("BA_MBLA")
        quien = pelea.byte("BA_MQUIEN")
        if dano == 0xFFFF:
            cual = "errar"
        elif blanco < una.simbolos["BA_GRUPO_MAX"]:
            cual = "dano_actor"
        elif pelea.hp_del_combatiente(blanco) == 0:
            cual = "muerte"
        else:
            cual = "dano_enemigo"
        if quien >= una.simbolos["BA_GRUPO_MAX"]:
            # Pega un enemigo: primero el suyo, y el del daño espera su turno.
            primero, pendiente = "ataque", cual
        else:
            primero, pendiente = cual, None
        assert se_disparado(una) == esperados[primero], (
            "el golpe tenía que sonar con %s —la muestra %d— y sonó con la %d"
            % (primero, esperados[primero], se_disparado(una)))
        sigue = pelea.palabra(una.simbolos["BA_SE2"])
        if pendiente is None:
            assert sigue == 0xFFFF, \
                "un golpe del grupo no deja ningún efecto pendiente"
        else:
            assert sigue == una.simbolos[PENDIENTE_DE[pendiente]], (
                "el golpe de un enemigo tenía que dejar %s pendiente y dejó "
                "$%04X" % (pendiente, sigue))
        vistos.add(primero)
        pelea.tocar_cuadros()
    return vistos


def test_el_golpe_suena_con_el_efecto_que_le_toca(partida):
    """Cuál de los cinco efectos del LDB sale en cada golpe.

    El reparto es el de easyrpg-player y está escrito en
    `events.BATTLE_AUDIO`: errar es `GetFailureSe` —dodge_se—, pegarle a un
    actor es actor_damaged_se, y a un enemigo enemy_damaged_se salvo que lo
    mate, que es el enemy_death_se de `ProcessBattleActionDeath`. Cuando el que
    pega es un enemigo, primero suena su enemy_attack_se y el del daño queda
    pendiente en `BA_SE2`: RM2k los hace sonar juntos, y acá el segundo
    espera su turno.

    Lo que se compara no es circular: `BA_MDANO` y `BA_MBLA` son la mecánica,
    que el resto de este archivo ya cobra contra `battle.py` número por
    número; lo que se mide acá es la elección del efecto, que es lo nuevo.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperados = {
        "errar": sonido_muestra(una, una.simbolos["BA_SE_ERRAR"]),
        "ataque": sonido_muestra(una, una.simbolos["BA_SE_ATAQUE"]),
        "dano_enemigo": sonido_muestra(una, una.simbolos["BA_SE_DANO_ENEMIGO"]),
        "dano_actor": sonido_muestra(una, una.simbolos["BA_SE_DANO_ACTOR"]),
        "muerte": sonido_muestra(una, una.simbolos["BA_SE_MUERTE"]),
    }
    vistos = set()
    for _ in range(8):
        if pelea.modo() == "FIN":
            break
        vivos = len([k for k in range(len(GRUPO))
                     if pelea.hp_del_combatiente(k)])
        for _ in range(vivos):
            for _ in range(400):
                if pelea.modo() != "ORDEN":
                    break
                pelea.tocar_cuadros()
            for _ in range(400):
                if pelea.modo() != "BLANCO":
                    break
                pelea.tocar_cuadros()
        vistos |= mirar_los_golpes(una, pelea, esperados)
    assert vistos, "ningún golpe llegó a sonar: la prueba no midió nada"


# --- usar un ítem ----------------------------------------------------------
#
# `Use Item`. Lo que se mide acá es lo mismo que en el
# resto del archivo: **el número exacto**. `battle.healing` dice cuánto
# tendría que curar y la consola tiene que dejar ese HP, ni uno más.

def en_el_droide_con_pocion(partida):
    """La pelea del droide con pociones en el inventario y el grupo herido.

    Las pone la página de prueba `pociones-y-llave`: tres `POCION` y una
    `LLAVE`.

    Herido a mano y no peleando: pelear hasta que a alguien le falten HP
    depende del azar, y lo que este caso mide es la cura.
    """
    una = partida(caso="pociones-y-llave")
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    # Heridos en **veinte**, que es menos de lo que cura una poción: es lo que
    # hace que el tope contra el máximo se vea. Con un HP no se vería: desde
    # que el nivel sale del LDB, Kersh tiene 168 de máximo y cincuenta no lo
    # llenan.
    for actor in GRUPO:
        maximo = rules.param_of(datos.base().actors[actor], "maxhp")
        falta = maximo - 20
        una.poner_hp(actor, falta)
    return una


def test_la_lista_de_items_es_la_que_se_puede_usar(partida):
    """`Game_Party::IsItemUsable` con la pelea abierta, más lo que este port
    sabe hacer: ver `battle.item_usable_in_battle`.

    La lista la arma la ROM recorriendo el inventario, y lo que se compara es
    contra la misma regla en Python. Si la ROM ofreciera un ítem que no cura
    —un arma, un libro— el jugador podría gastarlo sin que pasara nada.
    """
    una = en_el_droide_con_pocion(partida)
    pelea = Pelea(una).abrir()
    for _ in range(pelea.orden("USAR")):
        pelea.tocar_cuadros("right")
    assert pelea.byte("BA_ORDEN") == pelea.orden("USAR")
    pelea.tocar_cuadros()
    assert pelea.modo() == "ITEM", "A sobre `Use Item` abre la lista"
    base = datos.base()
    esperados = [n for n in sorted(base.items)
                 if modelo.item_usable_in_battle(base.items[n])]
    # De ésos, los que hay en el inventario.
    hay = [n for n in esperados if una.item(n)]
    assert hay, "el caso no puso ningún ítem usable: no mide nada"
    assert una.item(LLAVE), (
        "el caso no puso ningún ítem inusable: ofrecer todo y ofrecer lo que "
        "corresponde darían lo mismo y no mediría nada")
    assert pelea.byte("BA_ITEM_N") == len(hay), (
        "la ROM ofrece %d ítems y los usables que hay son %d: %s"
        % (pelea.byte("BA_ITEM_N"), len(hay), hay))


def test_usar_una_pocion_cura_lo_que_dice_el_modelo(partida):
    """`Game_BattleAlgorithm::Item`: `rate * hp_max / 100 + hp`, topado contra
    lo que falta.

    Con la Potion —cincuenta planos— y un actor en 1 HP de 40, lo que tiene
    que quedar son los 40: el tope es lo que falta y no lo que el ítem cura.
    Eso es justamente lo que se equivoca solo si uno suma sin topar.
    """
    una = en_el_droide_con_pocion(partida)
    pelea = Pelea(una).abrir()
    base = datos.base()
    esperado = modelo_de(base)
    for quien in esperado.actors:
        quien.hp = quien.hp_max - 20
    antes = una.item(POCION)
    # El primer actor usa la poción sobre sí mismo; los otros dos atacan.
    for _ in range(pelea.orden("USAR")):
        pelea.tocar_cuadros("right")
    pelea.tocar_cuadros()               # abre la lista
    pelea.tocar_cuadros()               # elige el primero
    assert pelea.modo() == "ACTOR"
    pelea.tocar_cuadros()               # sobre el primer actor
    assert una.item(POCION) == antes - 1, (
        "la poción se gasta al elegirla, como en RM2k")
    for _ in range(2):
        for _ in range(400):
            if pelea.modo() != "ORDEN":
                break
            pelea.tocar_cuadros()
        for _ in range(400):
            if pelea.modo() != "BLANCO":
                break
            pelea.tocar_cuadros()
    for _ in range(400):
        if pelea.modo() in ("ORDEN", "FIN"):
            break
        pelea.tocar_cuadros()
    esperado.play_turn(
        [(modelo.COMMAND_ITEM, (base.items[POCION], 0)),
         (modelo.COMMAND_ATTACK, 0), (modelo.COMMAND_ATTACK, 0)])
    de_la_rom = [pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
    del_modelo = [c.hp for c in esperado.actors]
    assert de_la_rom == del_modelo, (
        "la consola dejó %r y el modelo %r" % (de_la_rom, del_modelo))
    assert de_la_rom[0] == esperado.actors[0].hp_max, (
        "la poción cura cincuenta sobre cuarenta de máximo: tiene que topar")


# --- levantar a un caído ----------------------------------------------------
#
# El `Pungent Elixir-LIFE`: `ko_only`, con el estado de muerto en su
# `state_set` y el 25% de los HP. Lo que se cobra es la tarea entera —
# workflow/tasks/*/el-elixir-en-la-pelea.md—: que el cursor se pare en el
# caído, que el HP sea el de `battle.item_effect`, que el levantado vuelva
# a pedir órdenes y que cobre la experiencia al ganar.

ELIXIR = 115


def test_el_elixir_levanta_a_un_caido_en_la_pelea(partida):
    """Core entra caído y Kersh le da el elixir; Manta ataca.

    Kersh y Manta están en pie, así que el cursor de a quién **tiene que
    arrancar en Core**, que es al único que el elixir le sirve. Después, turno
    por turno, el mismo HP que el modelo, con Core pidiendo órdenes desde el
    segundo, y al ganar Core cobra la experiencia de la tropa entera, que es lo
    que `bt_exp_allocate` le da a los que quedaron en pie.
    """
    from port import experience
    from batalla import exp_y_nivel
    una = partida(caso="elixir-en-la-pelea")
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    base = datos.base()
    una.poner_hp(GRUPO[1], 0)
    esperado = modelo_de(base)
    esperado.actors[1].hp = 0
    antes = exp_y_nivel(una, GRUPO[1])
    assert una.item(ELIXIR) == 1, "el caso no puso el elixir"
    assert modelo.item_usable_in_battle(base.items[ELIXIR])
    pelea = Pelea(una).abrir()
    assert pelea.hp_del_combatiente(1) == 0, "Core tenía que entrar caído"
    # Kersh: `Use Item`, el elixir —el único de la lista— y a quién.
    for _ in range(pelea.orden("USAR")):
        pelea.tocar_cuadros("right")
    pelea.tocar_cuadros()
    assert pelea.modo() == "ITEM"
    assert pelea.byte("BA_ITEM_N") == 1
    pelea.tocar_cuadros()
    assert pelea.modo() == "ACTOR", (
        "A sobre el elixir tiene que pedir a quién, con un caído en el grupo")
    assert pelea.byte("BA_ITEM_BLA") == 1, (
        "el cursor tenía que arrancar en Core, el único al que el elixir le "
        "sirve, y arrancó en %d" % pelea.byte("BA_ITEM_BLA"))
    pelea.tocar_cuadros("down")
    pelea.tocar_cuadros("up")
    assert pelea.byte("BA_ITEM_BLA") == 1, (
        "el cursor no se para en uno en pie con un elixir")
    pelea.tocar_cuadros()
    assert una.item(ELIXIR) == 0, "el elixir se gasta al elegirlo"
    pelea.ordenar(("atacar", 0))
    pelea.correr_turno()
    esperado.play_turn([(modelo.COMMAND_ITEM, (base.items[ELIXIR], 1)),
                        (modelo.COMMAND_ATTACK, 0)])
    levantado = max(1, 25 * esperado.actors[1].hp_max // 100)
    assert esperado.actors[1].hp == levantado or not esperado.actors[1].alive
    de_la_rom = [pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
    del_modelo = [c.hp for c in esperado.actors]
    assert de_la_rom == del_modelo, (
        "turno 1: la consola dejó %r y el modelo %r" % (de_la_rom, del_modelo))
    assert de_la_rom[1] > 0, "el elixir no levantó a Core"
    # Desde acá, los tres atacan: Core tiene que pedir orden.
    turno = 1
    while esperado.result is None:
        turno += 1
        vivos = esperado.living(esperado.actors)
        if turno == 2:
            assert len(vivos) == 3
            pelea.ordenar(("atacar", 0))
            assert pelea.modo() == "ORDEN" and pelea.byte("BA_ACTOR") == 1, (
                "después de Kersh la orden la tenía que pedir Core, que se "
                "levantó: la pide %d en el modo %s"
                % (pelea.byte("BA_ACTOR"), pelea.modo()))
            pelea.turno(len(vivos) - 1)
        else:
            pelea.turno(len(vivos))
        esperado.play_turn([(modelo.COMMAND_ATTACK, 0)] * len(vivos))
        de_la_rom = [pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
        del_modelo = [c.hp for c in esperado.actors]
        assert de_la_rom == del_modelo, (
            "turno %d: la consola dejó %r y el modelo %r"
            % (turno, de_la_rom, del_modelo))
    assert esperado.result == modelo.VICTORY
    assert esperado.actors[1].alive, (
        "el caso necesita a Core en pie al ganar: si no, no mide la experiencia")
    pelea.cerrar()
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    nivel, exp = experience.add_exp(base.actors[GRUPO[1]], antes[1], antes[0],
                                    ganada)
    assert exp_y_nivel(una, GRUPO[1]) == (exp, nivel), (
        "Core, levantado, quedó con %r y tendría que cobrar la experiencia: %r"
        % (exp_y_nivel(una, GRUPO[1]), (exp, nivel)))


def test_el_segundo_elixir_sobre_el_mismo_caido_no_hace_nada(partida):
    """Kersh y Manta le dan un elixir cada uno a Core, en el mismo turno.

    Al elegir, Core está caído para los dos, así que los dos cursores se
    paran en él. Al ejecutar, el primero lo levanta y el segundo encuentra a
    uno en pie: `ko_only`, y `vExecute` sale sin efecto. El blanco no se
    reapunta y el elixir se gasta igual —se gastó al elegirlo—. Es la rama
    "en pie y `ko_only`" de `bt_item_use`, que jugando sólo pasa así.
    """
    una = partida(caso="elixir-en-la-pelea")
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    una.consola.write_ram(una.simbolos["FAR_ITEMS"] + ELIXIR, [2])
    base = datos.base()
    una.poner_hp(GRUPO[1], 0)
    esperado = modelo_de(base)
    esperado.actors[1].hp = 0
    pelea = Pelea(una).abrir()
    for quien in (0, 2):
        pelea.esperar("ORDEN")
        assert pelea.byte("BA_ACTOR") == quien
        for _ in range(5):
            pelea.tocar_cuadros("left")
        for _ in range(pelea.orden("USAR")):
            pelea.tocar_cuadros("right")
        pelea.tocar_cuadros()
        pelea.tocar_cuadros()
        assert pelea.modo() == "ACTOR"
        assert pelea.byte("BA_ITEM_BLA") == 1, (
            "el cursor de %d tenía que arrancar en Core, caído" % quien)
        pelea.tocar_cuadros()
    assert una.item(ELIXIR) == 0, "los dos elixires se gastan al elegirlos"
    pelea.correr_turno()
    esperado.play_turn([(modelo.COMMAND_ITEM, (base.items[ELIXIR], 1)),
                        (modelo.COMMAND_ITEM, (base.items[ELIXIR], 1))])
    de_la_rom = [pelea.hp_del_combatiente(k) for k in range(len(GRUPO))]
    del_modelo = [c.hp for c in esperado.actors]
    assert de_la_rom == del_modelo, (
        "la consola dejó %r y el modelo %r" % (de_la_rom, del_modelo))
    levantado = max(1, 25 * esperado.actors[1].hp_max // 100)
    assert del_modelo[1] in (levantado, 0) and de_la_rom[1] != 2 * levantado, (
        "el segundo elixir no tiene que curar al que el primero levantó")


def test_el_menu_va_en_el_orden_del_original(partida):
    """Las cinco órdenes, en el orden de la captura del juego de verdad.

    Una captura del juego de verdad, del 2026-09-12, muestra el menú de Manta:
    Attack / Slicing / Defend / Use Item. La habilidad va
    **segunda**. `Escape` no
    está en el original —huir es una orden del grupo— y acá va quinta, que es
    la simplificación que `battle.py` declara.

    Lo que se cobra es el recorrido del cursor: que llegue hasta la quinta, que
    vuelva, y que A sobre la segunda abra la lista de habilidades y B la
    cierre.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    for _ in range(4):
        pelea.tocar_cuadros("right")
    assert pelea.byte("BA_ORDEN") == pelea.orden("HUIR"), \
        "el cursor tiene que llegar hasta `Escape`, que es la quinta"
    pelea.tocar_cuadros("right")
    assert pelea.byte("BA_ORDEN") == pelea.orden("HUIR"), \
        "y no pasarse de la quinta"
    for _ in range(3):
        pelea.tocar_cuadros("left")
    assert pelea.byte("BA_ORDEN") == pelea.orden("HABILIDAD")
    pelea.tocar_cuadros()
    assert pelea.modo() == "HAB", \
        "A sobre la habilidad tiene que abrir su lista"
    pelea.tocar_cuadros("b")
    assert pelea.modo() == "ORDEN", "y B tiene que volver al menú"
    assert pelea.byte("BA_ORDEN") == pelea.orden("HABILIDAD"), \
        "volviendo con B el cursor se queda donde estaba"


def test_un_actor_sin_habilidades_no_abre_la_lista(partida):
    """Talan es de nivel 1 y no aprendió ninguna: la suya se queda en gris.

    Es el mismo trato que el menú de pausa le da a una orden que no lleva a
    ningún lado, y el camino que los otros tres no ejercitan. El caso pide que
    Talan siga sin saber ninguna, porque si algún día aprendiera una dejaría de
    probar lo que dice probar.
    """
    base = datos.base()
    assert not modelo.skills_of(base, 14), \
        "Talan tenía que no saber ninguna: si supiera, este caso no distingue"
    una = partida(caso=LINKAGE)
    una.poner_grupo(14, 12, 13)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    pelea = Pelea(una).abrir()
    assert pelea.byte("BA_ACTOR") == 0
    pelea.tocar_cuadros("right")
    assert pelea.byte("BA_ORDEN") == pelea.orden("HABILIDAD")
    pelea.tocar_cuadros()
    assert pelea.modo() == "ORDEN", \
        "sin ninguna habilidad, A no tiene que llevar a ningún lado"
    assert pelea.byte("BA_HAB_N") == 0


def test_con_una_pista_de_msu_la_pelea_anota_el_tema_del_mapa(partida,
                                                                con_musica):
    """Con MSU-1, el tema del mapa también tiene que volver al terminar.

    Con una pista de CD sonando, `music_start` deja el SPC700 callado a
    propósito —`music_apagada` en 1—, y una pelea que mirara sólo eso anotaría
    $FF, "no sonaba nada", y al volver al mapa lo callaría en vez de
    reponerlo. Las pruebas corren sin MSU-1 —la consola le esconde las pistas
    al core, ver `retro.Console`—.

    Así que acá se pone el estado que deja una pista sonando —las dos banderas,
    escritas a mano— y se mira qué anota la pelea. Sin el arreglo de
    `battle_start` anota $FF.
    """
    una = en_el_droide(partida, con_musica)
    tema = una.palabra("tema_actual")
    assert tema < 0xFF, "el mapa tenía que arrancar con su tema: no mide nada"
    # `MSU_PLAYING` se declara con el banco adelante, y la RAM del core se
    # direcciona desde $7E:0000.
    una.consola.write_ram(una.simbolos["MSU_PLAYING"] & 0xFFFF, [1])
    una.poner_byte("music_apagada", 1)
    pelea = Pelea(una).abrir()
    assert pelea.byte("BA_TEMA_ANT") == tema, (
        "con una pista de MSU-1 sonando la pelea anotó $%02X como el tema del "
        "mapa, y era el %d: al volver lo va a callar"
        % (pelea.byte("BA_TEMA_ANT"), tema))
