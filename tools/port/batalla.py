"""La batalla por turnos de RM2k, modelada con las mismas reglas que la ROM.

Es el hermano de `pantallas.py` para la pelea: acá viven las fórmulas —daño,
acierto, crítico, varianza, orden de turnos, huida— y la máquina de turnos, y
la ROM las copia. Que los dos lados hagan la misma cuenta es lo que le permite
a `pruebas/rpgmaker/test_batalla.py` predecir **el número exacto** que la consola va a
poner en cada HP, en vez de conformarse con "bajó".

**Ningún número de acá se escribió de memoria.** Todos salen de
easyrpg-player, que está clonado en `/extras/ref`, y cada uno dice de dónde:

    src/algo.cpp                CalcNormalAttackEffect, CalcNormalAttackToHit,
                                CalcCriticalHitChance, VarianceAdjustEffect,
                                AdjustDamageForDefend
    src/scene_battle_rpg2k.cpp  CreateExecutionOrder, CreateEnemyActions
    src/scene_battle.cpp        InitEscapeChance, TryEscape
    src/game_enemy.cpp          GetHitChance, GetCriticalHitChance
    src/game_actor.cpp          GetHitChance, GetCriticalHitChance
    src/rand.cpp                PercentChance
    src/algo.cpp                CalcSkillEffect, CalcSkillToHit, CalcSkillCost,
                                VarianceAdjustEffect
    src/game_battlealgorithm.cpp  Skill::vStart, Skill::vExecute
    src/game_battler.cpp        CanChangeAtkModifier y sus hermanas, AdjustParam
    src/game_actor.cpp          LearnSkill, LearnLevelSkills,
                                CalculateWeaponSpCost
    src/enemyai.cpp             SelectEnemyAiActionRpgRtCompat, MakeSkillAction,
                                IsSkillEffectiveOn

Tres cosas **no** son de RM2k, y las tres son a propósito:

* **El azar.** RPG_RT tira de un generador que no podemos reproducir. Acá el
  azar es el mismo xorshift de dieciséis bits que el port ya usa para
  `ControlVars` —`eventos.azar_siguiente`—, pero con **semilla propia**:
  `BATALLA_SEMILLA`. Tener la suya y no compartir `FAR_AZAR` es lo que hace que
  pelear no le corra el azar al mapa: un `ControlVars` al azar da lo mismo
  con una pelea en el medio y sin ella.

* **Las divisiones.** Donde easyrpg hace la cuenta en punto flotante y la
  trunca al devolverla, acá es entera. En el ajuste por agilidad eso importa y
  por eso va con **división hacia arriba**: truncar `100 - x` hacia cero es lo
  mismo que restarle el techo de `x`, así que la cuenta entera da exactamente
  lo mismo que la flotante. Ver `acierto_por_agilidad`.

* **Lo que no está.** Estados, atributos, filas y el ataque doble. Y de las
  páginas de evento de la tropa, que la ROM corre desde el 2026-09-21, el
  modelo sabe **cuándo corren y a quién sacan a la pelea** —`PaginaDeTropa`—
  y nada más: lo demás que hacen lo cobra `pruebas/rpgmaker/test_tropa.py`
  leyendo la página del LDB, y ninguna de las que compilan tira azar de la
  pelea. Lo que sí cambia el azar es quién pelea, y por eso está: un enemigo
  que aparece a mitad de pelea elige acción desde el turno que sigue. Acá lo
  que importa es que las fórmulas que sí están son las de verdad y no una
  aproximación.
"""

from port import eventos

# La semilla del azar de la batalla. Es otra que `AZAR_SEMILLA` a propósito:
# ver arriba. El valor no significa nada, sólo tiene que ser distinto de cero
# —el xorshift se queda clavado en el cero— y ser el mismo de los dos lados.
BATALLA_SEMILLA = 0x2B1D

# Cuántos caben en una pelea. El grupo es el de RM2k, cuatro; los enemigos, lo
# que entra en la pantalla de texto sin taparle nada al grupo. La tropa más
# grande del juego tiene ocho miembros, así que con ocho no se pierde ninguna.
GRUPO_MAX = 4
ENEMIGOS_MAX = 8

# Los tres resultados, en el orden en que el bytecode lleva sus destinos.
VICTORIA, HUIDA, DERROTA = 0, 1, 2

# Las órdenes que el jugador puede dar: `command_attack`, `command_defend` y
# `battle_escape` del LDB. Atacar pide blanco; las otras dos, no.
#
# En RM2k huir es una orden **del grupo**, de un menú que va antes de repartir
# las órdenes; acá es una orden de cada actor y se resuelve en el momento en
# que se elige. Si sale, la pelea termina ahí; si no, ese actor se queda con
# `ORDEN_HUIR`, que en el turno no hace nada más que decirlo. Es una
# simplificación declarada: ahorra un modo entero de la máquina de la ROM y
# deja a los dos lados con una sola lista de acciones.
ORDEN_ATACAR, ORDEN_DEFENDER, ORDEN_HUIR = 0, 1, 2
# Y usar un ítem, desde el 2026-09-13: `Game_BattleAlgorithm::Item`. Va como
# cuarta y no entre las otras para no renumerar lo que ya estaba.
ORDEN_ITEM = 3
# Y una habilidad, `Game_BattleAlgorithm::Skill`. Va quinta por lo mismo: en la
# pantalla aparece segunda —el original la pone entre Attack y Defend— pero el
# número es el de la orden y no el de la columna.
ORDEN_HABILIDAD = 4


def item_usable_en_batalla(item):
    """Si este ítem entra en la lista que la pelea ofrece.

    `Game_Party::IsItemUsable` con `in_battle`: una medicina —`type` 0 en
    liblcf, que el volcado a JSON llama 6— se puede usar salvo que esté
    marcada `occasion_field1`, "sólo fuera de batalla".

    Y de esas, este port ofrece **sólo las que recuperan HP**, con una
    condición más para las `ko_only`: que levanten, o sea que saquen el estado
    de muerto, porque una `ko_only` que no levanta no le sirve a nadie —ver
    `efecto_de_item`—. Lo que queda afuera y por qué:

    * las de SP: **los SP ya son estado desde el 2026-09-13**, así que esto
      pasó de imposible a deuda —falta el `recover_sp` del lado del ítem, que
      es la misma cuenta que la de HP—;
    * las que suben un parámetro para siempre: no hay estados de eso.

    Las `ko_only` —Phoenix Down, Pungent Elixir, Jumper Cable— entran desde el
    2026-09-26: levantar es sacar el estado de muerto, y la pelea de este port
    no tiene más estados que ése, que es tener cero HP.
    """
    return (item.type == TIPO_MEDICINA and not item.occasion_field1
            and (item.recover_hp or item.recover_hp_rate)
            and (levanta(item) or not item.ko_only))


def levanta(item):
    """Si el ítem saca el estado de muerto: el primero de su `state_set`, que
    es el estado 1. Es el bit `MED_LEVANTA` de `item_medicina`."""
    return item.state_set[:1] == [True]


def curacion(item, blanco):
    """Cuánto cura este ítem sobre este blanco.

    `Game_BattleAlgorithm::Item::vExecute`:

        hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp

    y después `Game_Battler::ChangeHp` lo topa contra lo que falta para el
    máximo. La división es entera de los dos lados, como todas las de acá.
    """
    hp = item.recover_hp_rate * blanco.hp_max // 100 + item.recover_hp
    return max(0, min(hp, blanco.hp_max - blanco.hp))


def efecto_de_item(item, blanco):
    """Los HP con los que queda el blanco de una medicina: `vExecute` y lo que
    `ApplyAll` hace después, rama por rama.

    * en pie y `ko_only`: nada —`SetIsSuccess` sin efecto—;
    * en pie: la `curacion`;
    * caído y el ítem no levanta: nada, porque `ApplyHpEffect` no toca a un
      muerto. Hasta el 2026-09-26 los dos lados lo levantaban sumándole la
      cura a los cero HP, y ninguna prueba lo veía porque no se podía elegir a
      un caído;
    * caído y levanta: el `SetHp(1)` de `RemoveStates` y después el
      `ChangeHp(hp - 1)` de `ApplyStateEffect`, o sea `max(1, curacion)`. Es lo
      mismo que `Game_Battler::UseItem` desde el menú.

    Devuelve `(hp, levantado)`.
    """
    if blanco.vivo:
        if item.ko_only:
            return blanco.hp, False
        return blanco.hp + curacion(item, blanco), False
    if not levanta(item):
        return blanco.hp, False
    return max(1, curacion(item, blanco)), True


# `Item::Type_medicine`, que en liblcf es el 0. El volcado a JSON de este repo
# numera distinto —ahí las medicinas son el 6— así que el número sale de
# `lcf.Item.type`, que es el del LDB.
TIPO_MEDICINA = 6

# El tope de un parámetro, como `Game_Actor::GetAtk` y sus hermanas.
PARAM_MAX = 999
# Y el del daño: `Game_BattleAlgorithm::MaxDamageValue()` para RM2k.
DANO_MAX = 999


def habilidad_usable(skill):
    """Si esta pelea sabe ofrecer esta habilidad.

    Es el hermano de `item_usable_en_batalla` y, como aquél, **recorta a lo que
    este port hace** y lo declara en vez de hacerlo mal:

    * el tipo tiene que ser `normal` o `switch`. `teleport` y `escape` no
      existen acá, y `subskill` es de RM2k3;
    * y el costo tiene que entrar en dos cifras, que es lo que la lista
      escribe. Ninguna del juego llega a 100.

    **Los cinco alcances entran desde el 2026-09-27** —el hito 4 de Lashe
    City: taro pidió que AG7 no perdiera ninguna de sus habilidades—. Los de a
    muchos, `enemies` y `party`, repiten el efecto sobre cada blanco vivo del
    lado, en el orden de la pantalla, y `self` es el que la usa: ver
    `Batalla.blancos_de_la_habilidad`. Hasta ese día quedaban afuera, y con
    ellos `Gamble for Credits`, la única de Arden.
    """
    from rpgmaker import lcf
    return (skill.type in (lcf.SKILL_TIPO_NORMAL, lcf.SKILL_TIPO_SWITCH)
            and skill.sp_cost <= 99)


def pide_blanco(skill):
    """Si al elegirla el menú pide a quién: sólo las de a uno —`enemy` y
    `ally`— y que no sean de switch, que `Scene_Battle::AssignSkill` anota
    sobre el que la usa. Las de a muchos y `self` tampoco: su blanco lo
    decide el alcance."""
    from rpgmaker import lcf
    return (skill.type != lcf.SKILL_TIPO_SWITCH
            and skill.scope in (lcf.SKILL_SCOPE_ENEMIGO,
                                lcf.SKILL_SCOPE_ALIADO))


def habilidad_efectiva_sola(skill):
    """`EnemyAi::IsSkillEffectiveOn` para un blanco vivo, sin estados.

    Una que apunta a enemigos siempre lo es; una que apunta al propio bando,
    sólo si toca algo que exista acá: HP, SP o alguno de los cuatro
    parámetros. Las que sólo curan o ponen estados —`RemoveStatus`, de AG7—
    no hacen nada sobre nadie, porque no hay estados, y la IA del enemigo las
    descarta.

    No depende del blanco porque un vivo sin estados es igual a cualquier
    otro: por eso lo contesta el conversor y la ROM no lo mira.
    """
    return (skill.apunta_a_enemigos
            or any((skill.affect_hp, skill.affect_sp, skill.affect_attack,
                    skill.affect_defense, skill.affect_spirit,
                    skill.affect_agility)))


# Lo que un enemigo puede hacer: `lcf::rpg::EnemyAction`, de a uno por renglón
# de su lista del LDB, como `(rating, habilidad, efectiva)`. La habilidad es
# el `lcf.Skill` o None para el ataque básico; `efectiva` es
# `habilidad_efectiva_sola`, que la IA mira **después** de sacar el máximo.
ACCION_KIND_BASICA, ACCION_KIND_HABILIDAD = 0, 1
ACCION_BASICA_ATACAR = 0
ACCION_CONDICION_SIEMPRE = 0
# Cuántas acciones puede traer un enemigo: la ROM las pesa en `BA_HAB_LISTA`,
# que mide eso. El conversor corta si alguno trae más.
ACCIONES_MAX = 16
# El rating de la acción que se pone cuando al enemigo no le queda ninguna:
# con una sola da igual cuál, porque no se tira nada.
ACCION_RATING_SOLA = 50


def acciones_de_enemigo(db, enemy_id):
    """Las acciones del enemigo que este port sabe hacer, en el orden del LDB.

    Es la lista que `EnemyAi::SelectEnemyAiActionRpgRtCompat` recorre,
    **recortada a lo que existe acá** —y lo que se recorta, se declara—:

    * el ataque básico (`kind` 0, `basic` 0) y las habilidades que la pelea
      sabe hacer (`kind` 1, ver `habilidad_usable`), **menos las de switch**:
      la IA les tira un blanco por su alcance y la pelea las anota sobre el
      que las usa, así que dos caminos distintos para una sola del juego no
      valen la pena;
    * con la condición "siempre". Las demás —turno, HP, SP, cantidad de
      enemigos, nivel y cansancio del grupo— no se miran: la acción sale de la
      lista, igual que si su condición no se cumpliera;
    * sin los switches que prende o apaga al elegirse (`switch_on`,
      `switch_off`): ninguna del juego que el cartucho lleva los usa, y la
      acción que los trae sale de la lista.

    Lo demás —defenderse, cargar, huir, transformarse, el ataque doble— sale
    de la lista. Si no queda ninguna, queda el ataque básico solo, que es lo
    que la pelea hacía con todos hasta el 2026-09-27.
    """
    from rpgmaker import lcf
    lista = []
    for accion in db.enemies[enemy_id].actions:
        if accion.condition_type != ACCION_CONDICION_SIEMPRE \
                or accion.switch_on or accion.switch_off:
            continue
        if accion.kind == ACCION_KIND_BASICA \
                and accion.basic == ACCION_BASICA_ATACAR:
            lista.append((accion.rating, None, True))
            continue
        if accion.kind != ACCION_KIND_HABILIDAD:
            continue
        skill = db.skills.get(accion.skill_id)
        if skill is None or skill.type != lcf.SKILL_TIPO_NORMAL \
                or not habilidad_usable(skill):
            continue
        lista.append((accion.rating, skill, habilidad_efectiva_sola(skill)))
    return lista or [(ACCION_RATING_SOLA, None, True)]


def sp_del_arma(db, equipo):
    """Lo que cuesta atacar con lo que tiene puesto: `CalculateWeaponSpCost`.

    Es el `sp_cost` de las armas —`ForEachEquipment<true, false>`, o sea sin
    las armaduras aunque traigan uno: el escudo NetLauncher de AG7 dice 4 y
    no lo cobra— y `Normal::vStart` lo descuenta antes del acierto, topado en
    cero. La única ranura con arma es la 0: la segunda arma, en la del
    escudo, es de RM2k3. `half_sp_cost` es un estado, y no hay.
    """
    from rpgmaker import lcf
    arma = db.items.get(equipo[0]) if equipo and equipo[0] else None
    if arma is None or arma.type != lcf.ITEM_TIPO_ARMA:
        return 0
    return arma.sp_cost


def habilidades_de(db, numero, nivel=None):
    """Las habilidades que este actor sabe, en el orden en que el menú las pone.

    `Game_Actor::LearnLevelSkills` recorre la tabla de aprendizaje del LDB y
    aprende las de nivel menor o igual al suyo; `LearnSkill` las mete en
    `data.skills` y **ordena la lista por número**, así que ése es el orden que
    la pantalla muestra —y el que la captura del original confirma: Manta ve
    Mental Hack, MindShield, MindProbe y MindBlast, o sea 130, 143, 144, 150—.

    El nivel es el `initial_level` del LDB, como todo lo demás desde el
    2026-09-13: con el 1 que el port tenía mockeado no se sabía ninguna, porque
    la primera se aprende en el 3.

    Las que este port no sabe ofrecer no entran: ver `habilidad_usable`.
    """
    return [s for s in aprendidas_de(db, numero, nivel)
            if habilidad_usable(db.skills[s])]


def aprendidas_de(db, numero, nivel=None):
    """Las habilidades que este actor **sabe**, usables o no, ordenadas.

    Es `Game_Actor::LearnLevelSkills` a secas: las de nivel menor o igual al
    suyo. Va aparte de `habilidades_de` porque son dos preguntas distintas y
    confundirlas se paga de un solo lado: el menú de la pelea sólo puede
    ofrecer las que este port sabe ejecutar —ése es el filtro de
    `habilidad_usable`— pero `IsSkillLearned`, que es lo que pregunta la rama
    de `ConditionalBranch`, no filtra nada.

    Las dos salen de acá para que no puedan separarse: la rama y el menú tienen
    que estar de acuerdo en qué sabe cada uno.
    """
    actor = db.actors[numero]
    if nivel is None:
        nivel = actor.initial_level
    return sorted({s for aprende, s in actor.skills
                   if s and aprende <= nivel})


def nivel_en_que_aprende(db, numero, skill):
    """En qué nivel aprende este actor esta habilidad: el más bajo de los
    renglones de su tabla que la nombran. `LearnLevelSkills` la aprende en el
    primero que alcanza y `LearnSkill` no la repite. 0 si la tabla no la
    nombra: ésa sólo la enseña un `ChangeSkills`."""
    return min((nivel for nivel, s in db.actors[numero].skills if s == skill),
               default=0)


def nombre_de_orden_habilidad(db, numero):
    """Cómo se llama la orden de habilidades de este actor en el menú.

    `Game_Actor::GetSkillName`: el `skill_name` del actor si tiene puesto
    `rename_skill`, y si no el `command_skill` del LDB —"Tech Skill"—. Los
    cuatro actores de la intro lo tienen puesto: "AgentTrain", "Telepathy",
    "Slicing" y "Special".
    """
    from port import pantallas
    actor = db.actors[numero]
    if actor.rename_skill and actor.skill_name:
        return actor.skill_name
    return pantallas.terminos_batalla(db)["habilidad"]


def costo_de(skill):
    """`Algo::CalcSkillCost`: en RM2k el `sp_cost` a secas.

    El `sp_percent` es de RM2k3 y `half_sp_cost` es un estado, y no hay
    estados.
    """
    return skill.sp_cost


def varianza_ajustar(base, var, azar):
    """`Algo::VarianceAdjustEffect`.

        adj = max(1, var * base / 10); base += rand(0, adj) - adj / 2

    **Sólo tira si `var > 0` y `base > 0`**, que es lo que dice el `if`; sin
    esa condición los dos lados se irían de fase en el tiro siguiente cada vez
    que una habilidad de switch o un golpe de cero pasara por acá.
    """
    if var > 0 and base > 0:
        ajuste = max(1, var * base // 10)
        return base + azar.hasta(ajuste) - ajuste // 2
    return base


def efecto_habilidad(fuente, blanco, skill, critico=False):
    """`Algo::CalcSkillEffect` **sin la varianza**, que se aplica aparte.

        effect  = power
        effect += physical_rate * atk / 20
        effect += magical_rate  * spi / 40
        si apunta a enemigos y no ignora la defensa:
            effect -= physical_rate * def / 40
            effect -= magical_rate  * spi_del_blanco / 80
        effect = max(0, effect)
        si es crítico: effect *= 3

    Las filas y los atributos no están —este port no tiene ninguno de los
    dos—. Todas las divisiones son de números no negativos, así que la entera
    de Python da lo mismo que la de C++.
    """
    efecto = skill.power
    efecto += skill.physical_rate * fuente.ataque // 20
    efecto += skill.magical_rate * fuente.espiritu // 40
    if skill.apunta_a_enemigos and not skill.ignore_defense:
        efecto -= skill.physical_rate * blanco.defensa // 40
        efecto -= skill.magical_rate * blanco.espiritu // 80
    efecto = max(0, efecto)
    if critico:
        efecto *= 3
    return efecto


def _mitad(n):
    """La división por dos de C++, que **trunca hacia cero**.

    Hace falta porque `AdjustDamageForDefend` divide el efecto de una
    habilidad, que puede ser negativo: en C++ -25/2 es -12 y en Python
    -25 // 2 es -13. Un punto de daño de diferencia que sólo aparece cuando
    alguien se defiende de una habilidad, o sea la clase de discrepancia que
    tarda semanas en verse.
    """
    return -((-n) // 2) if n < 0 else n // 2


def cambio_de_modificador(mod, base, delta):
    """`Game_Battler::CanChangeAtkModifier` y sus tres hermanas.

        nuevo = clamp(mod + delta, -base / 2, base)

    y devuelve `nuevo - mod`, o sea cuánto se movió de verdad. El tope de
    bajada es la mitad del parámetro base: un enemigo no puede quedar con
    menos de la mitad de su ataque por más habilidades que le tiren.
    """
    nuevo = max(-(base // 2), min(base, mod + delta))
    return nuevo - mod


class Azar:
    """El xorshift de la batalla, con su propia semilla.

    `hasta(n)` devuelve un número de 0 a n **inclusive**, que es el rango de
    `Rand::GetRandomNumber(0, n)` de easyrpg. El resto no es uniforme y no
    importa que no lo sea: lo que importa es que la ROM saque exactamente lo
    mismo, y la ROM hace esta misma cuenta con el divisor del hardware.
    """

    def __init__(self, semilla=BATALLA_SEMILLA):
        self.estado = semilla

    def hasta(self, n):
        self.estado = eventos.azar_siguiente(self.estado)
        return self.estado % (n + 1) if n >= 0 else 0

    def porciento(self, tanto):
        """`Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.

        **Se tira siempre**, aunque `tanto` sea cero: es lo que hace
        `Normal::vExecute` con el crítico, y si acá no se tirara los dos lados
        se irían de fase en el tiro siguiente.
        """
        return self.hasta(99) < tanto


class Combatiente:
    """Uno de los que pelean, del lado que sea.

    `es_actor` decide dos cosas y no es cosmético: de qué lado cuenta para
    elegir blanco, y que el crítico exista —`CalcCriticalHitChance` lo pone en
    cero cuando los dos son del mismo tipo—.
    """

    def __init__(self, nombre, hp_max, ataque, defensa, agilidad, acierto,
                 critico=0, es_actor=True, numero=0, espiritu=0, sp_max=0,
                 habilidades=(), acciones=None, sp_arma=0):
        self.nombre = nombre
        self.hp_max = hp_max
        self.hp = hp_max
        # Los cuatro parámetros **base**: lo que una habilidad modifica es el
        # `*_modificador` de al lado, y lo que las cuentas usan es la suma de
        # los dos, topada. Ver `Game_Battler::GetAtk` y `AdjustParam`.
        self.ataque_base = ataque
        self.defensa_base = defensa
        self.espiritu_base = espiritu
        self.agilidad_base = agilidad
        self.mod_ataque = 0
        self.mod_defensa = 0
        self.mod_espiritu = 0
        self.mod_agilidad = 0
        self.acierto = acierto
        self.critico = critico          # en por ciento, ya entero
        self.es_actor = es_actor
        self.numero = numero            # el actor del LDB, o el lugar en la tropa
        # Los SP y lo que sabe hacer con ellos. Las habilidades son las del
        # menú de un actor; las de un enemigo están en `acciones`, que es su
        # lista del LDB —ver `acciones_de_enemigo`— y la de un actor no se
        # usa. Sin lista, ataca: es lo que hacía todo enemigo hasta el
        # 2026-09-27.
        self.sp_max = sp_max
        self.sp = sp_max
        self.habilidades = list(habilidades)
        self.acciones = (list(acciones) if acciones is not None
                         else [(ACCION_RATING_SOLA, None, True)])
        # Lo que le cuesta atacar: `sp_del_arma`. Cero para un enemigo.
        self.sp_arma = sp_arma
        self.defendiendo = False
        self.orden = 0
        # Un enemigo oculto —`invisible` en la tropa— está pero no pelea:
        # `Exists()` es `!IsHidden() && !IsDead()`. Lo saca a la pelea el
        # `ShowHiddenMonster` de una página: ver `PaginaDeTropa`.
        self.oculto = False
        # Lo que da al morir: `Game_EnemyParty::GetExp` y `GetMoney`.
        self.exp = 0
        self.oro = 0

    @property
    def vivo(self):
        """`Exists()`: le quedan HP y no está oculto. Todo lo que elige blanco,
        reparte acciones o decide la victoria mira esto, así que un oculto no
        cuenta para nada hasta que aparece —que es lo que hace la ROM al
        dejarlo sin `BAF_HAY`—."""
        return self.hp > 0 and not self.oculto

    # Los cuatro parámetros como los ve una cuenta: `AdjustParam` de
    # game_battler.cpp, o sea `clamp(base + modificador, 1, 999)`. Sin estados
    # no hay ni mitad ni doble.
    @property
    def ataque(self):
        return max(1, min(PARAM_MAX, self.ataque_base + self.mod_ataque))

    @property
    def defensa(self):
        return max(1, min(PARAM_MAX, self.defensa_base + self.mod_defensa))

    @property
    def espiritu(self):
        return max(1, min(PARAM_MAX, self.espiritu_base + self.mod_espiritu))

    @property
    def agilidad(self):
        return max(1, min(PARAM_MAX, self.agilidad_base + self.mod_agilidad))


def actor_de(db, numero, equipo=None, nivel=None):
    """El combatiente de un actor del LDB, con lo que tenga puesto.

    Los parámetros salen de `pantallas.parametros`, que es la misma función que
    usa la pantalla de equipo: el del nivel más lo que suma cada pieza, topado
    en [1, 999]. Los HP son los del nivel y no llevan equipo, como
    `Game_Actor::GetMaxHp` en RM2k, donde el equipo no toca los HP.

    El acierto es 90: `Game_Actor::GetHitChance` con un arma sin `hit` propio.
    **El `hit` del arma no se lee**, y es deuda declarada: ningún arma del ABL
    lo baja, pero el día que una lo haga esto se equivoca en silencio.

    El nivel es el `initial_level` del LDB y no el 1: ver `titulo.nivel_de`.
    Hasta el 2026-09-13 era el 1 y Kersh peleaba con 40 HP y ataque 17 en vez
    de 168 y 80. Con `nivel`, el que haya subido: ver `port.experiencia`.
    """
    from port import pantallas
    from port import titulo
    actor = db.actors[numero]
    if equipo is None:
        equipo = list(actor.initial_equipment)
    ataque, defensa, espiritu, agilidad = pantallas.parametros(db, numero,
                                                               equipo, nivel)
    critico = (100 // actor_critico_cada(db, numero)) \
        if actor_tiene_critico(db, numero) else 0
    quien = Combatiente(actor.name, titulo.parametro_de(actor, "maxhp", nivel),
                        ataque, defensa, agilidad, 90, critico, True, numero,
                        espiritu, titulo.parametro_de(actor, "maxsp", nivel),
                        habilidades_de(db, numero, nivel),
                        sp_arma=sp_del_arma(db, equipo))
    return quien


def actor_tiene_critico(db, numero):
    """`critical_hit` del actor, del LDB. En el ABL ninguno lo tiene."""
    return bool(getattr(db.actors[numero], "critical_hit", False))


def actor_critico_cada(db, numero):
    return getattr(db.actors[numero], "critical_hit_chance", 30) or 30


def enemigo_de(db, enemy_id, lugar, oculto=False):
    """El combatiente de un enemigo del LDB; `oculto` es el `invisible` de su
    lugar en la tropa.

    El acierto es `Game_Enemy::GetHitChance`: 70 el que tiene `miss` puesto y
    90 el que no. El crítico, `GetCriticalHitChance` por cien y truncado, que
    con el 30 de fábrica da 3.
    """
    e = db.enemies[enemy_id]
    critico = (100 // (e.critical_hit_chance or 30)) if e.critical_hit else 0
    quien = Combatiente(e.name, e.max_hp, e.attack, e.defense, e.agility,
                        e.hit, critico, False, lugar, e.spirit, e.max_sp,
                        acciones=acciones_de_enemigo(db, enemy_id))
    # Lo que deja al morir: el ítem y su chance en por ciento. Ver `botin`.
    quien.botin_item = e.drop_id
    quien.botin_chance = e.drop_prob
    quien.oculto = oculto
    quien.exp = e.exp
    quien.oro = e.gold
    return quien


def enemigos_de_la_tropa(db, tropa):
    """Los combatientes de una tropa, en su orden y con sus ocultos, hasta
    `ENEMIGOS_MAX` como la pelea."""
    t = db.troops[tropa]
    return [enemigo_de(db, e, n, oculto)
            for n, (e, oculto) in enumerate(
                list(zip(t.members, t.ocultos))[:ENEMIGOS_MAX])]


def _turnos(turno, base, multiplo):
    """`Game_Battle::CheckTurns(turns, base, multiple)`."""
    if multiplo == 0:
        return turno >= base and turno == base
    return turno >= base and (turno - base) % multiplo == 0


class PaginaDeTropa:
    """Una página de evento de la tropa, **con lo que el modelo necesita**:
    cuándo se cumple —`AreConditionsMet`, los seis disparadores de RM2k— y a
    quién saca a la pelea. De sus comandos corre sólo `ShowHiddenMonster`, los
    `ControlSwitches` de un switch y las ramas de pelea por switch, que es lo
    que hace falta para saber si un `ShowHiddenMonster` adentro de una rama
    corre —el del Rat King va adentro de una, que la propia página cierra—.
    Lo demás —mensajes, habilidades, variables, sonidos— no cambia quién pelea
    ni tira azar de la pelea, y no se modela.

    Los switches son los de la batalla, `Batalla.estado`, que empieza con los
    que se le pasen: la ROM los lee del mapa.
    """

    def __init__(self, pagina):
        self.activos = list(pagina.activos)
        self.c = pagina.condicion
        self.comandos = list(pagina.commands)

    def cumple(self, batalla):
        if not self.activos:
            return False
        c = self.c
        if "switch_a" in self.activos and not batalla.estado.get(
                c["switch_a_id"]):
            return False
        if "switch_b" in self.activos and not batalla.estado.get(
                c["switch_b_id"]):
            return False
        if "variable" in self.activos:
            raise NotImplementedError("una página por variable: el modelo no "
                                      "lleva variables")
        if "turn" in self.activos and not _turnos(
                batalla.turno, c["turn_b"], c["turn_a"]):
            return False
        if "enemy_hp" in self.activos:
            if c["enemy_id"] >= len(batalla.enemigos):
                return False
            e = batalla.enemigos[c["enemy_id"]]
            if not (c["enemy_hp_min"] <= 100 * e.hp // e.hp_max
                    <= c["enemy_hp_max"]):
                return False
        if "actor_hp" in self.activos:
            # Sólo si está en el grupo, como la ROM: ver `ba_pag_cumple`.
            suyos = [a for a in batalla.actores if a.numero == c["actor_id"]]
            if not suyos:
                return False
            a = suyos[0]
            if not (c["actor_hp_min"] <= 100 * a.hp // a.hp_max
                    <= c["actor_hp_max"]):
                return False
        return True

    def correr(self, batalla):
        """Los comandos, con las ramas por switch resueltas: una rama que no
        se toma saltea todo lo que tiene más adentro que ella."""
        saltear_desde = None        # la sangría de la rama que no se tomó
        for cmd in self.comandos:
            if saltear_desde is not None:
                if cmd.indent > saltear_desde:
                    continue
                if cmd.code == 23310 and cmd.indent == saltear_desde:
                    saltear_desde = None    # el `else` de la que no se tomó
                    continue
                saltear_desde = None
            p = cmd.parameters
            if cmd.code == 13310:
                if p[0] != 0:
                    raise NotImplementedError("una rama de pelea que no es "
                                              "por switch")
                prendido = bool(batalla.estado.get(p[1]))
                if prendido != (p[2] == 0):
                    saltear_desde = cmd.indent
            elif cmd.code == 23310:
                # El `else` de una rama que sí se tomó: se saltea.
                saltear_desde = cmd.indent
            elif cmd.code == eventos.CONTROL_SWITCHES:
                if p[0] != 0 or p[1] != p[2] or p[3] not in (0, 1):
                    raise NotImplementedError("un ControlSwitches que el "
                                              "modelo no sabe")
                batalla.estado[p[1]] = p[3] == 0
            elif cmd.code == eventos.SHOW_HIDDEN_MONSTER:
                if p[0] < len(batalla.enemigos):
                    batalla.enemigos[p[0]].oculto = False


def oro_de_la_tropa(db, tropa):
    """`Game_EnemyParty::GetMoney`: el `gold` de cada enemigo **muerto**, que
    en una victoria son todos menos los que siguieron ocultos —como en
    `experiencia.exp_de_la_tropa`—, hasta `ENEMIGOS_MAX`. Es la suma de la
    tropa entera; lo de los ocultos lo resta la ROM al ganar. No tira azar."""
    return sum(db.enemies[e].gold for e in db.troops[tropa].members[:ENEMIGOS_MAX])


def acierto_por_agilidad(base, agi_fuente, agi_blanco):
    """`CalcToHitAgiAdjustment` de algo.cpp.

        to_hit = 100 - (100 - to_hit) * (1 + (tgt_agi / src_agi - 1) / 2)

    que es lo mismo que restarle a 100 el producto por `(src + tgt) / (2 src)`.
    easyrpg lo hace en `float` y devuelve un `int`, o sea que trunca hacia cero
    el resultado entero: `trunc(100 - x)` es `100 - ceil(x)` mientras el
    resultado sea positivo, y por eso acá la división es **hacia arriba**. Sin
    eso los dos lados se separan en un punto de acierto cada tanto, que es
    justo la clase de diferencia que no se ve hasta que un golpe falla.
    """
    fuente = max(1, agi_fuente)
    resta = (100 - base) * (fuente + agi_blanco)
    return 100 - -(-resta // (2 * fuente))


def dano_normal(fuente, blanco, critico, azar):
    """`CalcNormalAttackEffect` y `VarianceAdjustEffect` con varianza 4.

        dmg = max(0, atk / 2 - def / 4)
        crítico: * 3
        varianza: adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2

    Las filas, los atributos del arma y el ataque cargado no están: este port
    no tiene ninguna de las tres.
    """
    dano = max(0, fuente.ataque // 2 - blanco.defensa // 4)
    if critico:
        dano *= 3
    return varianza_ajustar(dano, 4, azar)


def ajustar_por_defensa(dano, blanco):
    """`AdjustDamageForDefend`: el que se defiende recibe la mitad. La "defensa
    fuerte" es un estado y no hay estados."""
    return _mitad(dano) if blanco.defendiendo else dano


class Batalla:
    """Una pelea, turno por turno. Es `Scene_Battle_Rpg2k` de easyrpg con lo
    que este port hace.

    El lazo de un turno, en el orden en que consume azar —y ese orden es el
    contrato con la ROM—:

    1. el jugador elige la orden de cada actor vivo (no tira azar);
    2. cada enemigo vivo elige qué hacer y contra quién —`CreateEnemyActions`,
       ver `accion_del_enemigo`—: **un tiro para la acción si tiene más de
       una posible, y uno para el blanco si la acción lo pide**;
    3. `CreateExecutionOrder`: **un tiro por combatiente que actúa**, para su
       `agi + rand(0, agi / 4 + 3)`, y después se ordena de mayor a menor con
       un orden estable;
    4. se ejecutan en ese orden, salteando a los que hayan muerto en el
       camino. Cada ataque tira **tres veces**: acierto, crítico y varianza, y
       el del crítico se tira aunque la probabilidad sea cero;
    5. al ganar, **un tiro por enemigo con ítem**, en el orden de la tropa:
       ver `tirar_el_botin`.

    Que el punto 2 vaya antes que el 3 no es un detalle: es el orden de
    `SelectNextActor`, que llama a `CreateEnemyActions()` y después a
    `CreateExecutionOrder()`.
    """

    def __init__(self, actores, enemigos, semilla=BATALLA_SEMILLA,
                 paginas=(), switches=None):
        self.actores = list(actores)
        self.enemigos = list(enemigos)
        self.azar = Azar(semilla)
        self.turno = 0
        # Las páginas de la tropa —ver `PaginaDeTropa`—, las que ya corrieron
        # en este turno —`executed`— y los switches que miran.
        self.paginas = list(paginas)
        self.hechas = set()
        self.estado = dict(switches or {})
        self.resultado = None
        self.huida_chance = self._chance_de_huir()
        self.registro = []          # lo que pasó, para que una prueba lo cuente
        # Los switches que una habilidad de tipo `switch` prendió:
        # `Skill::vExecute` hace `SetAffectedSwitch(skill.switch_id)` y
        # `Scene_Battle` lo prende de verdad. Acá se junta el número, que es lo
        # que la prueba compara contra el bit de la ROM.
        self.switches = []
        # Los ítems que soltaron los enemigos al perder: ver `tirar_el_botin`.
        self.botin = []

    # --- la huida ---------------------------------------------------------
    def _promedio(self, quienes):
        vivos = [c for c in quienes if c.vivo] or list(quienes)
        return sum(c.agilidad for c in vivos) // max(1, len(vivos))

    def _chance_de_huir(self):
        """`Scene_Battle::InitEscapeChance`:

            base = redondear(100 * agi_enemigos / agi_grupo)
            chance = recortar(150 - base, 0, 100)

        El redondeo de easyrpg es `RoundTo`, o sea al entero más cercano; acá
        es `(2a + b) // (2b)`, que es lo mismo con enteros y sin flotantes.
        """
        enemigos = self._promedio(self.enemigos)
        grupo = max(1, self._promedio(self.actores))
        base = (2 * 100 * enemigos + grupo) // (2 * grupo)
        return max(0, min(100, 150 - base))

    def huir(self):
        """`TryEscape`: se tira contra la chance y, si falla, sube diez.

        Devuelve True si se escapó. `first_strike` no está: las dos peleas de
        la intro lo traen en cero.
        """
        if self.azar.porciento(self.huida_chance):
            self.resultado = HUIDA
            return True
        self.huida_chance = min(100, self.huida_chance + 10)
        return False

    # --- las páginas de la tropa ----------------------------------------------
    def revisar_paginas(self):
        """`CheckBattleEndAndScheduleEvents` hasta que no quede ninguna: con
        un lado entero afuera no corre nada; si no, la primera página que se
        cumpla y no haya corrido en este turno, y después otra vez desde la
        primera. La ROM lo hace en `ba_pag_probar`."""
        while self.vivos(self.enemigos) and self.vivos(self.actores):
            for i, pagina in enumerate(self.paginas):
                if i not in self.hechas and pagina.cumple(self):
                    self.hechas.add(i)
                    pagina.correr(self)
                    break
            else:
                return

    def empezar(self):
        """Antes de las primeras órdenes, en el turno 0: el `eCheckEvents` de
        `ProcessSceneActionFightAutoEscape`."""
        self.revisar_paginas()

    # --- el turno ---------------------------------------------------------
    def vivos(self, quienes):
        return [c for c in quienes if c.vivo]

    def accion_del_enemigo(self, enemigo):
        """Qué hace este enemigo: `SelectEnemyAiActionRpgRtCompat`, con la
        lista de `acciones_de_enemigo`. Devuelve `(rating, habilidad,
        efectiva)` o None si no le queda ninguna posible.

        1. Son posibles las que `IsActionValid` deja: el ataque siempre, una
           habilidad si le alcanzan los SP (`IsSkillUsable`);
        2. cada posible pesa `max(0, rating - máximo + 10)`: **con diez puntos
           menos que la mejor, una acción no sale nunca**. Por eso de los
           cuatro enemigos de la planta que traen `ShortCircuit` sólo la usa
           el Tangle Wire, que la tiene en 50 como el ataque; el Scrapped
           Droid (10), el Trash Hauler y el Junkbot (30) nunca;
        3. y después pesa cero la que no es `efectiva` —el máximo ya se sacó
           contándola, que es lo que hace easyrpg—;
        4. se tira `rand(0, suma - 1)` y se elige por pesos, en el orden de la
           lista.

        **Con una sola acción de peso no se tira**, y eso no es de RM2k: es
        la misma distribución y deja el azar de las peleas que ya estaban
        —enemigos que sólo atacan— exactamente como era antes de que los
        enemigos eligieran. RPG_RT tira de otro generador de todos modos.
        """
        pesos = [(r, s, ef) for r, s, ef in enemigo.acciones
                 if s is None or enemigo.sp >= costo_de(s)]
        if not pesos:
            return None
        maximo = max(r for r, _s, _ef in pesos)
        pesos = [(max(0, r - maximo + 10) if ef else 0, (r, s, ef))
                 for r, s, ef in pesos]
        pesos = [(p, a) for p, a in pesos if p > 0]
        if not pesos:
            return None
        if len(pesos) == 1:
            return pesos[0][1]
        cual = self.azar.hasta(sum(p for p, _a in pesos) - 1)
        for peso, accion in pesos:
            cual -= peso
            if cual < 0:
                return accion
        raise AssertionError("no puede pasar: `cual` es menor que la suma")

    def acciones_de_los_enemigos(self):
        """`CreateEnemyActions`: cada enemigo vivo elige su acción
        —`accion_del_enemigo`— y después su blanco, que es el orden de
        `MakeAttack` y `MakeSkillAction`:

        * atacar, o una habilidad de alcance `enemy`: un actor vivo al azar,
          `GetRandomActiveBattler`, **un tiro**;
        * una de alcance `ally`: un enemigo vivo al azar —`GetRandomSkillTarget`
          entre los que la habilidad afecta, que sin estados son todos—, **un
          tiro**;
        * `self`, `enemies` y `party`: sin tiro, porque el blanco lo dice el
          alcance. Se anota el que la usa.

        Si no queda ningún actor vivo se corta y los enemigos que faltaban se
        quedan sin acción: sin eso los dos lados tirarían distinta cantidad
        de veces."""
        from rpgmaker import lcf
        acciones = []
        for enemigo in self.vivos(self.enemigos):
            blancos = self.vivos(self.actores)
            if not blancos:
                break
            accion = self.accion_del_enemigo(enemigo)
            if accion is None:
                continue
            _rating, skill, _ef = accion
            if skill is None:
                blanco = blancos[self.azar.hasta(len(blancos) - 1)]
                acciones.append((enemigo, ORDEN_ATACAR, blanco))
                continue
            if skill.scope == lcf.SKILL_SCOPE_ENEMIGO:
                blanco = blancos[self.azar.hasta(len(blancos) - 1)]
            elif skill.scope == lcf.SKILL_SCOPE_ALIADO:
                # Entre los que la habilidad afecta, que son todos los vivos:
                # una que no es `efectiva` pesó cero y no llega acá.
                suyos = self.vivos(self.enemigos)
                blanco = suyos[self.azar.hasta(len(suyos) - 1)]
            else:
                blanco = enemigo
            acciones.append((enemigo, ORDEN_HABILIDAD, (skill, blanco)))
        return acciones

    def orden_de_ejecucion(self, acciones):
        """`CreateExecutionOrder`: `agi + rand(0, agi / 4 + 3)`, de mayor a
        menor y con un orden **estable**, que es lo que hace `std::sort` sobre
        una lista que ya viene en el orden en que se apiló."""
        for quien, _orden, _blanco in acciones:
            quien.orden = quien.agilidad + self.azar.hasta(
                quien.agilidad // 4 + 3)
        return sorted(range(len(acciones)),
                      key=lambda i: -acciones[i][0].orden)

    def atacar(self, fuente, blanco):
        """Un ataque normal, con sus tres tiros. Devuelve (pegó, crítico,
        daño).

        Antes de todo, y sin tirar, cobra el SP del arma: `Normal::vStart`
        —ver `sp_del_arma`—. Se cobra aunque el golpe falle, y con los SP en
        cero se ataca igual: RM2k no pone en gris el `Attack`."""
        fuente.sp = max(0, fuente.sp - fuente.sp_arma)
        acierto = acierto_por_agilidad(fuente.acierto, fuente.agilidad,
                                       blanco.agilidad)
        pego = self.azar.porciento(acierto)
        critico = self.azar.porciento(fuente.critico if pego else 0)
        if not pego:
            # El tiro del crítico se hizo igual, pero el golpe falló.
            return False, False, 0
        dano = dano_normal(fuente, blanco, critico, self.azar)
        dano = ajustar_por_defensa(dano, blanco)
        dano = max(-DANO_MAX, min(DANO_MAX, dano))
        blanco.hp = max(0, blanco.hp - dano)
        return True, critico, dano

    def usar_habilidad(self, fuente, skill, blanco):
        """`Game_BattleAlgorithm::Skill`, con lo que este port sabe hacer.

        El orden en que consume azar **es el contrato con la ROM**, y sale de
        `vExecute` leído de arriba abajo:

        1. el costo se descuenta **antes de todo** —`vStart`— y no tira azar;
        2. una habilidad de tipo `switch` prende su switch y **termina ahí**:
           `vExecute` devuelve antes de cualquier tiro;
        3. el crítico: `Rand::PercentChance(crit_chance)`, **siempre**, aunque
           la chance sea cero. Y para una habilidad del LDB siempre lo es,
           porque `CalcCriticalHitChance` recibe `easyrpg_critical_hit_chance`,
           que por defecto vale 0 y no -1;
        4. la varianza, si el efecto quedó mayor que cero;
        5. un tiro contra el acierto **por cada cosa que la habilidad afecta**,
           en el orden HP, SP, ataque, defensa, espíritu, agilidad.

        Del 3 al 5 van **una vez por blanco**: ver `blancos_de_la_habilidad`.

        Lo que no está: los estados, los atributos, el absorber y revivir. De
        las de AG7, tres tocan estados —BioWarfare, HeadButt y RemoveStatus—:
        la primera y la última no hacen nada más que cobrar sus SP y tirar el
        crítico, y HeadButt pega sin dejar el estado.
        """
        from rpgmaker import lcf
        fuente.sp = max(0, fuente.sp - costo_de(skill))
        if skill.type == lcf.SKILL_TIPO_SWITCH:
            self.switches.append(skill.switch_id)
            self.registro.append((self.turno, fuente.nombre, fuente.nombre,
                                  True, False, 0, fuente.hp))
            return
        for uno in self.blancos_de_la_habilidad(fuente, skill, blanco):
            self._habilidad_sobre(fuente, skill, uno)

    def blancos_de_la_habilidad(self, fuente, skill, blanco):
        """Sobre quiénes cae, en el orden en que `vExecute` los recorre:
        `AlgorithmBase::Start` con el `party_target` del alcance, que es
        `GetBattlers` en el orden de la pantalla salteando a los que
        `IsTargetValid` descarta —los muertos—.

        `enemy` y `ally` caen sobre el que se eligió; `self`, sobre el que la
        usa; `enemies` y `party`, sobre cada vivo del lado contrario o del
        propio, **cada uno con sus tiros**: el crítico, la varianza y los del
        acierto se repiten por blanco."""
        from rpgmaker import lcf
        propios, contrarios = ((self.actores, self.enemigos) if fuente.es_actor
                               else (self.enemigos, self.actores))
        if skill.scope == lcf.SKILL_SCOPE_UNO_MISMO:
            return [fuente]
        if skill.scope == lcf.SKILL_SCOPE_ENEMIGOS:
            return self.vivos(contrarios)
        if skill.scope == lcf.SKILL_SCOPE_GRUPO:
            return self.vivos(propios)
        return [blanco]

    def _habilidad_sobre(self, fuente, skill, blanco):
        """`vExecute` sobre un blanco: ver `usar_habilidad`."""
        # `CalcSkillToHit`: el `hit` de la habilidad, que las siete traen en
        # 100. El camino del `failure_message == 3` no se toma —ninguna lo
        # tiene— y está declarado como lo que falta.
        acierto = skill.hit
        critico = self.azar.porciento(0)
        efecto = efecto_habilidad(fuente, blanco, skill, critico)
        efecto = varianza_ajustar(efecto, skill.variance, self.azar)
        efecto = max(-DANO_MAX, min(DANO_MAX, efecto))
        positivo = not skill.apunta_a_enemigos
        if not positivo:
            efecto = -efecto
        if skill.affect_hp and self.azar.porciento(acierto):
            if positivo:
                # Una cura no mata: `max(-(cur_hp - 1), hp_effect)`.
                hp = max(-(blanco.hp - 1), efecto)
            else:
                hp = ajustar_por_defensa(efecto, blanco)
            blanco.hp = max(0, min(blanco.hp_max, blanco.hp + hp))
        if skill.affect_sp and self.azar.porciento(acierto):
            blanco.sp = max(0, min(blanco.sp_max, blanco.sp + efecto))
        for afecta, mod, base in (
                (skill.affect_attack, "mod_ataque", "ataque_base"),
                (skill.affect_defense, "mod_defensa", "defensa_base"),
                (skill.affect_spirit, "mod_espiritu", "espiritu_base"),
                (skill.affect_agility, "mod_agilidad", "agilidad_base")):
            if not afecta:
                continue
            if not self.azar.porciento(acierto):
                continue
            delta = cambio_de_modificador(getattr(blanco, mod),
                                          getattr(blanco, base), efecto)
            setattr(blanco, mod, getattr(blanco, mod) + delta)
        self.registro.append((self.turno, fuente.nombre, blanco.nombre,
                              True, critico, -efecto, blanco.hp))

    # --- la victoria ------------------------------------------------------
    def experiencia(self):
        """`Game_EnemyParty::GetExp` al ganar: la de los muertos, que son
        todos menos los que siguieron ocultos. La ROM le resta éstos a la de
        la tropa: `ba_sin_ocultos`."""
        return sum(e.exp for e in self.enemigos if not e.oculto)

    def oro(self):
        """`GetMoney`, igual que `experiencia`."""
        return sum(e.oro for e in self.enemigos if not e.oculto)

    def tirar_el_botin(self):
        """`Game_EnemyParty::GenerateDrops`: por cada enemigo, en el orden de
        la tropa, **un tiro si tiene ítem** —`ChanceOf(drop_prob, 100)`, que
        es `GetRandomNumber(1, 100) <= rate` y con nuestro azar da lo mismo
        que `porciento`— y ninguno si no. El de chance 100 se tira igual. Lo
        llama `jugar_turno` al ganar, que es cuando lo hace
        `ProcessSceneActionVictory`; devuelve los ítems ganados en orden, uno
        por enemigo que soltó el suyo."""
        ganados = []
        for enemigo in self.enemigos:
            if enemigo.oculto:
                continue        # no murió: `IsDead` es falso
            item = getattr(enemigo, "botin_item", 0)
            if item > 0 and self.azar.porciento(enemigo.botin_chance):
                ganados.append(item)
        return ganados

    def jugar_turno(self, ordenes):
        """Un turno entero. `ordenes` es, por actor vivo y en el orden del
        grupo, `(ORDEN_ATACAR, lugar_del_enemigo)` o `(ORDEN_DEFENDER, 0)`.

        Devuelve el resultado si la pelea terminó, o None.

        Las páginas de la tropa corren **antes de cada acción y después de la
        última** —`ePreAction`—, y las anotadas se borran al empezar, que es
        `NextTurn`. Las de antes de las órdenes del turno que viene son las
        mismas que las de después de la última, así que no hace falta otra
        vuelta: ver `empezar` para las del turno 0.
        """
        self.turno += 1
        self.hechas = set()
        for quien in self.actores + self.enemigos:
            quien.defendiendo = False
        acciones = []
        for actor, (orden, blanco) in zip(self.vivos(self.actores), ordenes):
            if orden == ORDEN_ITEM:
                # Acá `blanco` es `(item, lugar_del_actor)`: el ítem del LDB y
                # a quién se le da.
                item, quien = blanco
                acciones.append((actor, orden, (item, self.actores[quien])))
                continue
            if orden == ORDEN_HABILIDAD:
                # Y acá `(skill, lugar)`: la habilidad del LDB y el lugar del
                # blanco, en la lista del lado al que apunta su `scope`.
                skill, quien = blanco
                lado = (self.enemigos if skill.apunta_a_enemigos
                        else self.actores)
                # Una de switch no pide blanco: `Scene_Battle::AssignSkill` la
                # anota sobre el que la usa, apunte a donde apunte su `scope`.
                # Lo mismo las de a muchos y las de uno mismo, cuyo blanco lo
                # dice el alcance: ver `blancos_de_la_habilidad`.
                destino = lado[quien] if pide_blanco(skill) else actor
                acciones.append((actor, orden, (skill, destino)))
                continue
            acciones.append((actor, orden,
                             self.enemigos[blanco] if orden == ORDEN_ATACAR
                             else None))
        acciones += self.acciones_de_los_enemigos()
        for i in self.orden_de_ejecucion(acciones):
            self.revisar_paginas()
            quien, orden, blanco = acciones[i]
            if not quien.vivo:
                continue
            if orden == ORDEN_DEFENDER:
                # `Defend` marca al que se defiende **cuando le toca**, no al
                # elegir: un enemigo que actúe antes le pega entero. Es lo de
                # RM2k.
                quien.defendiendo = True
                continue
            if orden == ORDEN_HUIR:
                continue
            if orden == ORDEN_HABILIDAD:
                # El blanco muerto **no se reapunta**, como con un ítem: el
                # `IsTargetValid` de `Skill` lo descarta y la acción se pierde.
                skill, blanco = blanco
                if not blanco.vivo:
                    continue
                self.usar_habilidad(quien, skill, blanco)
                continue
            if orden == ORDEN_ITEM:
                # Un ítem no puede fallar ni lo esquiva nadie: no tira azar.
                # El blanco **no** se reapunta, que es lo contrario de un
                # ataque: `Game_BattleAlgorithm::Item` va al que se eligió, y
                # si cambió en el camino el ítem se gasta igual y hace lo que
                # `efecto_de_item` diga con él como esté ahora. Un levantado
                # no actúa en este turno —no tenía orden— y en el que viene
                # vuelve a pedir, que es `vivos` al repartirlas.
                item, blanco = blanco
                antes = blanco.hp
                blanco.hp, _levantado = efecto_de_item(item, blanco)
                self.registro.append((self.turno, quien.nombre, blanco.nombre,
                                      True, False, antes - blanco.hp,
                                      blanco.hp))
                continue
            if not blanco.vivo:
                # `Game_BattleAlgorithm` reapunta a otro del mismo lado cuando
                # el blanco murió antes de que le tocara.
                lado = self.enemigos if not blanco.es_actor else self.actores
                candidatos = self.vivos(lado)
                if not candidatos:
                    continue
                blanco = candidatos[0]
            pego, critico, dano = self.atacar(quien, blanco)
            self.registro.append((self.turno, quien.nombre, blanco.nombre,
                                  pego, critico, dano, blanco.hp))
        self.revisar_paginas()
        if not self.vivos(self.enemigos):
            self.resultado = VICTORIA
            self.botin = self.tirar_el_botin()
        elif not self.vivos(self.actores):
            self.resultado = DERROTA
        return self.resultado
