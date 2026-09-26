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
    src/game_actor.cpp          LearnSkill, LearnLevelSkills

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

* **Lo que no está.** Estados, atributos, filas y el ataque doble. Y las
  páginas de evento de la tropa, que la ROM corre desde el 2026-09-21, **no
  están en este modelo**: lo que hacen lo cobra `pruebas/rpgmaker/test_tropa.py`
  leyendo la página del LDB, y ninguna de las que compilan tira azar de la
  pelea. Acá lo que importa es que las fórmulas que sí están son las de verdad
  y no una aproximación.
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

    Y de esas, este port ofrece **sólo las que recuperan HP y no son
    `ko_only`**. Lo que queda afuera y por qué:

    * las de SP: **los SP ya son estado desde el 2026-09-13**, así que esto
      pasó de imposible a deuda —falta el `recover_sp` del lado del ítem, que
      es la misma cuenta que la de HP—;
    * las `ko_only` —Phoenix Down, Pungent Elixir, Jumper Cable— porque
      revivir es sacar el estado de muerto y los estados no existen;
    * las que suben un parámetro para siempre, por lo mismo.

    Está declarado en workflow/tasks/done/battle.md. Lo que sí entra son las veinte medicinas de
    HP del juego, de la Potion de 50 a la Miracle Drop, que cura todo.
    """
    return (item.type == TIPO_MEDICINA and not item.occasion_field1
            and not item.ko_only
            and (item.recover_hp or item.recover_hp_rate))


def curacion(item, blanco):
    """Cuánto cura este ítem sobre este blanco.

    `Game_BattleAlgorithm::Item::vExecute`:

        hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp

    y después `Game_Battler::ChangeHp` lo topa contra lo que falta para el
    máximo. La división es entera de los dos lados, como todas las de acá.
    """
    hp = item.recover_hp_rate * blanco.hp_max // 100 + item.recover_hp
    return max(0, min(hp, blanco.hp_max - blanco.hp))


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
    * el alcance tiene que ser **de a uno**: `enemy` o `ally`, salvo en una de
      switch, que no pide blanco. Los de a muchos
      —`enemies`, `party`, `self`— pedirían repetir el efecto sobre cada
      blanco, y con eso el orden del azar de los dos lados;
    * y el costo tiene que entrar en dos cifras, que es lo que la lista
      escribe. Ninguna del juego llega a 100.

    De las siete que el grupo de la intro sabe **no se cae ninguna**. En un
    cartucho con más actores sí: `Gamble for Credits`, la única de Arden, tiene
    alcance `enemies` y queda afuera, y por eso Arden aparece sin ninguna.
    """
    from rpgmaker import lcf
    if skill.type == lcf.SKILL_TIPO_SWITCH:
        # Una de switch no pide blanco —ver `jugar_turno`—, así que su alcance
        # no importa. Son 6 de las 52 del juego las que no son de a uno.
        return skill.sp_cost <= 99
    return (skill.type == lcf.SKILL_TIPO_NORMAL
            and skill.scope in (lcf.SKILL_SCOPE_ENEMIGO,
                                lcf.SKILL_SCOPE_ALIADO)
            and skill.sp_cost <= 99)


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
                 habilidades=()):
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
        # Los SP y lo que sabe hacer con ellos. Un enemigo de este port no usa
        # habilidades —`CreateEnemyActions` sólo le da el ataque básico— así
        # que su lista va vacía.
        self.sp_max = sp_max
        self.sp = sp_max
        self.habilidades = list(habilidades)
        self.defendiendo = False
        self.orden = 0

    @property
    def vivo(self):
        return self.hp > 0

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
                        habilidades_de(db, numero, nivel))
    return quien


def actor_tiene_critico(db, numero):
    """`critical_hit` del actor, del LDB. En el ABL ninguno lo tiene."""
    return bool(getattr(db.actors[numero], "critical_hit", False))


def actor_critico_cada(db, numero):
    return getattr(db.actors[numero], "critical_hit_chance", 30) or 30


def enemigo_de(db, enemy_id, lugar):
    """El combatiente de un enemigo del LDB.

    El acierto es `Game_Enemy::GetHitChance`: 70 el que tiene `miss` puesto y
    90 el que no. El crítico, `GetCriticalHitChance` por cien y truncado, que
    con el 30 de fábrica da 3.
    """
    e = db.enemies[enemy_id]
    critico = (100 // (e.critical_hit_chance or 30)) if e.critical_hit else 0
    return Combatiente(e.name, e.max_hp, e.attack, e.defense, e.agility,
                       e.hit, critico, False, lugar, e.spirit, e.max_sp)


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
    2. cada enemigo vivo elige atacar a un actor vivo al azar
       —`CreateEnemyActions`—: **un tiro por enemigo**;
    3. `CreateExecutionOrder`: **un tiro por combatiente que actúa**, para su
       `agi + rand(0, agi / 4 + 3)`, y después se ordena de mayor a menor con
       un orden estable;
    4. se ejecutan en ese orden, salteando a los que hayan muerto en el
       camino. Cada ataque tira **tres veces**: acierto, crítico y varianza, y
       el del crítico se tira aunque la probabilidad sea cero.

    Que el punto 2 vaya antes que el 3 no es un detalle: es el orden de
    `SelectNextActor`, que llama a `CreateEnemyActions()` y después a
    `CreateExecutionOrder()`.
    """

    def __init__(self, actores, enemigos, semilla=BATALLA_SEMILLA):
        self.actores = list(actores)
        self.enemigos = list(enemigos)
        self.azar = Azar(semilla)
        self.turno = 0
        self.resultado = None
        self.huida_chance = self._chance_de_huir()
        self.registro = []          # lo que pasó, para que una prueba lo cuente
        # Los switches que una habilidad de tipo `switch` prendió:
        # `Skill::vExecute` hace `SetAffectedSwitch(skill.switch_id)` y
        # `Scene_Battle` lo prende de verdad. Acá se junta el número, que es lo
        # que la prueba compara contra el bit de la ROM.
        self.switches = []

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

    # --- el turno ---------------------------------------------------------
    def vivos(self, quienes):
        return [c for c in quienes if c.vivo]

    def acciones_de_los_enemigos(self):
        """`CreateEnemyActions`: cada enemigo vivo ataca a un actor vivo al
        azar. Sólo la acción "básica: atacar" —`kind` 0, `basic` 0—, que es la
        única que tienen los enemigos de las dos peleas de la intro."""
        acciones = []
        for enemigo in self.vivos(self.enemigos):
            blancos = self.vivos(self.actores)
            if not blancos:
                break
            blanco = blancos[self.azar.hasta(len(blancos) - 1)]
            acciones.append((enemigo, ORDEN_ATACAR, blanco))
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
        daño)."""
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

        Lo que no está, y ninguna de las siete que el grupo de la intro sabe lo
        pide: los estados, los atributos, el absorber, revivir y el `affect_sp`
        —el tiro está igual, por el orden del azar, pero nadie lo usa—.
        """
        from rpgmaker import lcf
        fuente.sp = max(0, fuente.sp - costo_de(skill))
        if skill.type == lcf.SKILL_TIPO_SWITCH:
            self.switches.append(skill.switch_id)
            self.registro.append((self.turno, fuente.nombre, fuente.nombre,
                                  True, False, 0, fuente.hp))
            return
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

    def jugar_turno(self, ordenes):
        """Un turno entero. `ordenes` es, por actor vivo y en el orden del
        grupo, `(ORDEN_ATACAR, lugar_del_enemigo)` o `(ORDEN_DEFENDER, 0)`.

        Devuelve el resultado si la pelea terminó, o None.
        """
        self.turno += 1
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
                from rpgmaker import lcf
                destino = (actor if skill.type == lcf.SKILL_TIPO_SWITCH
                           else lado[quien])
                acciones.append((actor, orden, (skill, destino)))
                continue
            acciones.append((actor, orden,
                             self.enemigos[blanco] if orden == ORDEN_ATACAR
                             else None))
        acciones += self.acciones_de_los_enemigos()
        for i in self.orden_de_ejecucion(acciones):
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
                # El blanco muerto **no** se reapunta, que es lo contrario de
                # un ataque: `Game_BattleAlgorithm::Item` cura al que se
                # eligió, y si se murió en el camino el ítem se gasta igual.
                item, blanco = blanco
                cura = curacion(item, blanco)
                blanco.hp = min(blanco.hp_max, blanco.hp + cura)
                self.registro.append((self.turno, quien.nombre, blanco.nombre,
                                      True, False, -cura, blanco.hp))
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
        if not self.vivos(self.enemigos):
            self.resultado = VICTORIA
        elif not self.vivos(self.actores):
            self.resultado = DERROTA
        return self.resultado
