"""RM2k's turn-based battle, modeled with the same rules as the ROM.

It is the sibling of `pantallas.py` for the battle: the formulas —damage,
hit, critical, variance, turn order, escape— and the turn machine live here,
and the ROM copies them. Both sides doing the same math is what lets
`rom/pruebas/rpgmaker/test_batalla.py` predict **the exact number** the
console is going to put in each HP, instead of settling for "it went down".

**None of the numbers here was written from memory.** They all come from
easyrpg-player, which is cloned in `/extras/ref`, and each one says where
from:

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
    src/game_battler.cpp        CanChangeAtkModifier and its siblings, AdjustParam
    src/game_actor.cpp          LearnSkill, LearnLevelSkills,
                                CalculateWeaponSpCost
    src/enemyai.cpp             SelectEnemyAiActionRpgRtCompat, MakeSkillAction,
                                IsSkillEffectiveOn

Three things are **not** RM2k's, and all three are on purpose:

* **The randomness.** RPG_RT draws from a generator we cannot reproduce.
  Here the randomness is the same sixteen-bit xorshift the port already uses
  for `ControlVars` —`events.next_random`—, but with **its own seed**:
  `BATALLA_SEMILLA`. Having its own and not sharing `FAR_AZAR` is what keeps
  a battle from advancing the map's randomness: a random `ControlVars` gives
  the same with or without a battle in between.

* **The divisions.** Where easyrpg does the math in floating point and
  truncates it on return, here it is integer. In the agility adjustment
  that matters, and so it uses **division rounding up**: truncating
  `100 - x` toward zero is the same as subtracting the ceiling of `x`, so
  the integer math gives exactly the same as the floating one. See
  `acierto_por_agilidad`.

* **What is missing.** States, attributes, rows and the double attack. And
  of the troop's event pages, which the ROM runs since 2026-09-21, the model
  knows **when they run and whom they bring into the battle**
  —`PaginaDeTropa`— and nothing else: the rest of what they do is checked by
  `rom/pruebas/rpgmaker/test_tropa.py` reading the page from the LDB, and
  none of the ones that compile draws battle randomness. What does change
  the randomness is who fights, and that is why it is here: an enemy that
  appears mid-battle chooses an action from the following turn on. What
  matters here is that the formulas that are here are the real ones and not
  an approximation.
"""

from port import events
from port import rules
from port.constants import ENEMIES_MAX

# The seed of the battle's randomness. It differs from `AZAR_SEMILLA` on
# purpose: see above. The value means nothing, it only has to be nonzero —the
# xorshift gets stuck at zero— and be the same on both sides.
BATALLA_SEMILLA = 0x2B1D

# How many fit in a battle. The party is RM2k's, four; the enemies,
# `constants.ENEMIES_MAX`.
GRUPO_MAX = 4

# The three outcomes, in the order the bytecode carries their destinations.
VICTORIA, HUIDA, DERROTA = 0, 1, 2

# The commands the player can give: `command_attack`, `command_defend` and
# `battle_escape` from the LDB. Attacking asks for a target; the other two do
# not.
#
# In RM2k escaping is a **party** command, from a menu that comes before
# handing out the commands; here it is a per-actor command and it is resolved
# the moment it is chosen. If it succeeds, the battle ends there; if not,
# that actor is left with `ORDEN_HUIR`, which in the turn does nothing but
# say so. It is a declared simplification: it saves a whole mode of the ROM's
# machine and leaves both sides with a single list of actions.
ORDEN_ATACAR, ORDEN_DEFENDER, ORDEN_HUIR = 0, 1, 2
# And using an item, since 2026-09-13: `Game_BattleAlgorithm::Item`. It goes
# fourth and not among the others so as not to renumber what was already
# there.
ORDEN_ITEM = 3
# And a skill, `Game_BattleAlgorithm::Skill`. It goes fifth for the same
# reason: on screen it shows second —the original puts it between Attack and
# Defend— but the number is the command's and not the column's.
ORDEN_HABILIDAD = 4


def item_usable_en_batalla(item):
    """Whether this item goes in the list the battle offers.

    `Game_Party::IsItemUsable` with `in_battle`: a medicine —`type` 0 in
    liblcf, which the JSON dump calls 6— can be used unless it is marked
    `occasion_field1`, "only outside battle".

    And of those, this port offers **only the ones that recover HP**, with
    one more condition for the `ko_only` ones: that they revive, that is,
    that they remove the dead state, because a `ko_only` that does not revive
    is of no use to anyone —see `efecto_de_item`—. What is left out and why:

    * the SP ones: **SP is already state since 2026-09-13**, so this went
      from impossible to debt —what is missing is `recover_sp` on the item
      side, which is the same math as HP's—;
    * the ones that raise a parameter permanently: there is no state for
      that.

    The `ko_only` ones —Phoenix Down, Pungent Elixir, Jumper Cable— are in
    since 2026-09-26: reviving is removing the dead state, and this port's
    battle has no other state than that one, which is having zero HP.
    """
    return (item.type == TIPO_MEDICINA and not item.occasion_field1
            and (item.recover_hp or item.recover_hp_rate)
            and (levanta(item) or not item.ko_only))


def levanta(item):
    """Whether the item removes the dead state: the first of its
    `state_set`, which is state 1. It is the `MED_LEVANTA` bit of
    `item_medicina`."""
    return item.state_set[:1] == [True]


def curacion(item, blanco):
    """How much this item heals on this target.

    `Game_BattleAlgorithm::Item::vExecute`:

        hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp

    and then `Game_Battler::ChangeHp` caps it at what is missing up to the
    maximum. The division is integer on both sides, like all of them here.
    """
    hp = item.recover_hp_rate * blanco.hp_max // 100 + item.recover_hp
    return max(0, min(hp, blanco.hp_max - blanco.hp))


def efecto_de_item(item, blanco):
    """The HP the target of a medicine is left with: `vExecute` and what
    `ApplyAll` does afterwards, branch by branch.

    * standing and `ko_only`: nothing —`SetIsSuccess` with no effect—;
    * standing: the `curacion`;
    * down and the item does not revive: nothing, because `ApplyHpEffect`
      does not touch a dead one. Until 2026-09-26 both sides revived it by
      adding the heal to the zero HP, and no test saw it because a downed
      one could not be chosen;
    * down and it revives: `RemoveStates`'s `SetHp(1)` and then
      `ApplyStateEffect`'s `ChangeHp(hp - 1)`, that is `max(1, curacion)`.
      It is the same as `Game_Battler::UseItem` from the menu.

    Returns `(hp, levantado)`.
    """
    if blanco.vivo:
        if item.ko_only:
            return blanco.hp, False
        return blanco.hp + curacion(item, blanco), False
    if not levanta(item):
        return blanco.hp, False
    return max(1, curacion(item, blanco)), True


# `Item::Type_medicine`, which in liblcf is 0. This repo's JSON dump numbers
# them differently —there medicines are 6— so the number comes from
# `lcf.Item.type`, which is the LDB's.
TIPO_MEDICINA = 6

# The cap of a parameter, like `Game_Actor::GetAtk` and its siblings.
PARAM_MAX = 999
# And the damage's: `Game_BattleAlgorithm::MaxDamageValue()` for RM2k.
DANO_MAX = 999


def habilidad_usable(skill):
    """Whether this battle knows how to offer this skill.

    It is the sibling of `item_usable_en_batalla` and, like that one, **cuts
    down to what this port does** and declares it instead of doing it wrong:

    * the type has to be `normal` or `switch`. `teleport` and `escape` do
      not exist here, and `subskill` is RM2k3's;
    * and the cost has to fit in two digits, which is what the list writes.
      None in the game reaches 100.

    **All five scopes are in since 2026-09-27** —milestone 4 of Lashe City:
    taro asked that AG7 not lose any of its skills—. The multi-target ones,
    `enemies` and `party`, repeat the effect on each living target on that
    side, in screen order, and `self` is the one using it: see
    `Batalla.blancos_de_la_habilidad`. Until that day they were left out, and
    with them `Gamble for Credits`, Arden's only one.
    """
    from rpgmaker import lcf
    return (skill.type in (lcf.SKILL_TYPE_NORMAL, lcf.SKILL_TYPE_SWITCH)
            and skill.sp_cost <= 99)


def pide_blanco(skill):
    """Whether the menu asks for whom when choosing it: only the
    single-target ones —`enemy` and `ally`— and not switch ones, which
    `Scene_Battle::AssignSkill` records on the one using it. Not the
    multi-target ones nor `self` either: their target is decided by the
    scope."""
    from rpgmaker import lcf
    return (skill.type != lcf.SKILL_TYPE_SWITCH
            and skill.scope in (lcf.SKILL_SCOPE_ENEMY,
                                lcf.SKILL_SCOPE_ALLY))


def habilidad_efectiva_sola(skill):
    """`EnemyAi::IsSkillEffectiveOn` for a living target, without states.

    One that targets enemies always is; one that targets its own side, only
    if it touches something that exists here: HP, SP or one of the four
    parameters. The ones that only heal or set states —`RemoveStatus`, AG7's—
    do nothing on anyone, because there are no states, and the enemy AI
    discards them.

    It does not depend on the target because a living one without states is
    the same as any other: that is why the converter answers it and the ROM
    does not look at it.
    """
    return (skill.targets_enemies
            or any((skill.affect_hp, skill.affect_sp, skill.affect_attack,
                    skill.affect_defense, skill.affect_spirit,
                    skill.affect_agility)))


# What an enemy can do: `lcf::rpg::EnemyAction`, one per row of its LDB list,
# as `(rating, habilidad, efectiva)`. The skill is the `lcf.Skill` or None for
# the basic attack; `efectiva` is `habilidad_efectiva_sola`, which the AI
# looks at **after** taking the maximum.
ACCION_KIND_BASICA, ACCION_KIND_HABILIDAD = 0, 1
ACCION_BASICA_ATACAR = 0
ACCION_CONDICION_SIEMPRE = 0
# How many actions an enemy can carry: the ROM weighs them in `BA_HAB_LISTA`,
# which is that long. The converter stops if one carries more.
ACCIONES_MAX = 16
# The rating of the action set when the enemy has none left: with a single
# one it does not matter which, because nothing is rolled.
ACCION_RATING_SOLA = 50


def acciones_de_enemigo(db, enemy_id):
    """The enemy's actions this port knows how to do, in LDB order.

    It is the list `EnemyAi::SelectEnemyAiActionRpgRtCompat` walks, **cut
    down to what exists here** —and what is cut is declared—:

    * the basic attack (`kind` 0, `basic` 0) and the skills the battle knows
      how to do (`kind` 1, see `habilidad_usable`), **except switch ones**:
      the AI rolls a target for them by their scope and the battle records
      them on the one using them, so two different paths for a single one in
      the game are not worth it;
    * with the "always" condition. The others —turn, HP, SP, number of
      enemies, party level and fatigue— are not looked at: the action drops
      out of the list, just as if its condition were not met;
    * without the switches it turns on or off when chosen (`switch_on`,
      `switch_off`): none in the game the cartridge carries uses them, and
      an action that has them drops out of the list.

    The rest —defending, charging, escaping, transforming, the double
    attack— drops out of the list. If none is left, the basic attack alone
    remains, which is what the battle did with every enemy until
    2026-09-27.
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
        if skill is None or skill.type != lcf.SKILL_TYPE_NORMAL \
                or not habilidad_usable(skill):
            continue
        lista.append((accion.rating, skill, habilidad_efectiva_sola(skill)))
    return lista or [(ACCION_RATING_SOLA, None, True)]


def sp_del_arma(db, equipo):
    """What attacking costs with what it has equipped:
    `CalculateWeaponSpCost`.

    It is the weapons' `sp_cost` —`ForEachEquipment<true, false>`, that is
    without the armor even if it carries one: AG7's NetLauncher shield says 4
    and does not charge it— and `Normal::vStart` deducts it before the hit
    roll, floored at zero. The only slot with a weapon is 0: the second
    weapon, in the shield slot, is RM2k3's. `half_sp_cost` is a state, and
    there are none.
    """
    from rpgmaker import lcf
    arma = db.items.get(equipo[0]) if equipo and equipo[0] else None
    if arma is None or arma.type != lcf.ITEM_TYPE_WEAPON:
        return 0
    return arma.sp_cost


def habilidades_de(db, numero, nivel=None):
    """The skills this actor knows, in the order the menu puts them.

    `Game_Actor::LearnLevelSkills` walks the LDB's learning table and learns
    the ones with a level lower than or equal to its own; `LearnSkill` puts
    them in `data.skills` and **sorts the list by number**, so that is the
    order the screen shows —and the one the capture of the original
    confirms: Manta sees Mental Hack, MindShield, MindProbe and MindBlast,
    that is 130, 143, 144, 150—.

    The level is the LDB's `initial_level`, like everything else since
    2026-09-13: with the 1 the port had mocked none was known, because the
    first one is learned at 3.

    The ones this port does not know how to offer are left out: see
    `habilidad_usable`.
    """
    return [s for s in rules.learned_skills(db, numero, nivel)
            if habilidad_usable(db.skills[s])]


def nivel_en_que_aprende(db, numero, skill):
    """At which level this actor learns this skill: the lowest of the rows
    of its table that name it. `LearnLevelSkills` learns it at the first one
    it reaches and `LearnSkill` does not repeat it. 0 if the table does not
    name it: that one is only taught by a `ChangeSkills`."""
    return min((nivel for nivel, s in db.actors[numero].skills if s == skill),
               default=0)


def nombre_de_orden_habilidad(db, numero):
    """What this actor's skill command is called in the menu.

    `Game_Actor::GetSkillName`: the actor's `skill_name` if it has
    `rename_skill` set, and otherwise the LDB's `command_skill` —"Tech
    Skill"—. The four actors of the intro have it set: "AgentTrain",
    "Telepathy", "Slicing" and "Special".
    """
    actor = db.actors[numero]
    if actor.rename_skill and actor.skill_name:
        return actor.skill_name
    return rules.battle_terms(db)["habilidad"]


def costo_de(skill):
    """`Algo::CalcSkillCost`: in RM2k, plain `sp_cost`.

    `sp_percent` is RM2k3's and `half_sp_cost` is a state, and there are no
    states.
    """
    return skill.sp_cost


def varianza_ajustar(base, var, azar):
    """`Algo::VarianceAdjustEffect`.

        adj = max(1, var * base / 10); base += rand(0, adj) - adj / 2

    **It only rolls if `var > 0` and `base > 0`**, which is what the `if`
    says; without that condition the two sides would drift out of phase on
    the next roll every time a switch skill or a zero hit went through here.
    """
    if var > 0 and base > 0:
        ajuste = max(1, var * base // 10)
        return base + azar.hasta(ajuste) - ajuste // 2
    return base


def efecto_habilidad(fuente, blanco, skill, critico=False):
    """`Algo::CalcSkillEffect` **without the variance**, which is applied
    separately.

        effect  = power
        effect += physical_rate * atk / 20
        effect += magical_rate  * spi / 40
        if it targets enemies and does not ignore defense:
            effect -= physical_rate * def / 40
            effect -= magical_rate  * target_spi / 80
        effect = max(0, effect)
        if critical: effect *= 3

    Rows and attributes are not here —this port has neither—. All the
    divisions are of non-negative numbers, so Python's integer division
    gives the same as C++'s.
    """
    efecto = skill.power
    efecto += skill.physical_rate * fuente.ataque // 20
    efecto += skill.magical_rate * fuente.espiritu // 40
    if skill.targets_enemies and not skill.ignore_defense:
        efecto -= skill.physical_rate * blanco.defensa // 40
        efecto -= skill.magical_rate * blanco.espiritu // 80
    efecto = max(0, efecto)
    if critico:
        efecto *= 3
    return efecto


def _mitad(n):
    """C++'s division by two, which **truncates toward zero**.

    It is needed because `AdjustDamageForDefend` divides a skill's effect,
    which can be negative: in C++ -25/2 is -12 and in Python -25 // 2 is -13.
    One point of damage of difference that only shows up when someone
    defends against a skill, that is, the kind of discrepancy that takes
    weeks to be seen.
    """
    return -((-n) // 2) if n < 0 else n // 2


def cambio_de_modificador(mod, base, delta):
    """`Game_Battler::CanChangeAtkModifier` and its three siblings.

        nuevo = clamp(mod + delta, -base / 2, base)

    and returns `nuevo - mod`, that is how much it actually moved. The floor
    is half the base parameter: an enemy cannot be left with less than half
    its attack no matter how many skills are thrown at it.
    """
    nuevo = max(-(base // 2), min(base, mod + delta))
    return nuevo - mod


class Azar:
    """The battle's xorshift, with its own seed.

    `hasta(n)` returns a number from 0 to n **inclusive**, which is the range
    of easyrpg's `Rand::GetRandomNumber(0, n)`. The remainder is not uniform
    and it does not matter that it is not: what matters is that the ROM gets
    exactly the same, and the ROM does this same math with the hardware
    divider.
    """

    def __init__(self, semilla=BATALLA_SEMILLA):
        self.estado = semilla

    def hasta(self, n):
        self.estado = events.next_random(self.estado)
        return self.estado % (n + 1) if n >= 0 else 0

    def porciento(self, tanto):
        """`Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.

        **It is always rolled**, even if `tanto` is zero: it is what
        `Normal::vExecute` does with the critical, and if it were not rolled
        here the two sides would drift out of phase on the next roll.
        """
        return self.hasta(99) < tanto


class Combatiente:
    """One of those who fight, on whichever side.

    `es_actor` decides two things and is not cosmetic: which side it counts
    on when choosing a target, and whether the critical exists
    —`CalcCriticalHitChance` sets it to zero when both are of the same
    kind—.
    """

    def __init__(self, nombre, hp_max, ataque, defensa, agilidad, acierto,
                 critico=0, es_actor=True, numero=0, espiritu=0, sp_max=0,
                 habilidades=(), acciones=None, sp_arma=0):
        self.nombre = nombre
        self.hp_max = hp_max
        self.hp = hp_max
        # The four **base** parameters: what a skill modifies is the
        # `*_modificador` next to them, and what the math uses is the sum of
        # both, clamped. See `Game_Battler::GetAtk` and `AdjustParam`.
        self.ataque_base = ataque
        self.defensa_base = defensa
        self.espiritu_base = espiritu
        self.agilidad_base = agilidad
        self.mod_ataque = 0
        self.mod_defensa = 0
        self.mod_espiritu = 0
        self.mod_agilidad = 0
        self.acierto = acierto
        self.critico = critico          # in percent, already an integer
        self.es_actor = es_actor
        self.numero = numero            # the LDB actor, or the place in the troop
        # The SP and what it knows how to do with them. The skills are those
        # of an actor's menu; an enemy's are in `acciones`, which is its LDB
        # list —see `acciones_de_enemigo`— and an actor's is not used.
        # Without a list, it attacks: it is what every enemy did until
        # 2026-09-27.
        self.sp_max = sp_max
        self.sp = sp_max
        self.habilidades = list(habilidades)
        self.acciones = (list(acciones) if acciones is not None
                         else [(ACCION_RATING_SOLA, None, True)])
        # What attacking costs it: `sp_del_arma`. Zero for an enemy.
        self.sp_arma = sp_arma
        self.defendiendo = False
        self.orden = 0
        # A hidden enemy —`invisible` in the troop— is there but does not
        # fight: `Exists()` is `!IsHidden() && !IsDead()`. A page's
        # `ShowHiddenMonster` brings it into the battle: see
        # `PaginaDeTropa`.
        self.oculto = False
        # What it gives when it dies: `Game_EnemyParty::GetExp` and
        # `GetMoney`.
        self.exp = 0
        self.oro = 0

    @property
    def vivo(self):
        """`Exists()`: it has HP left and is not hidden. Everything that
        chooses a target, hands out actions or decides victory looks at
        this, so a hidden one counts for nothing until it appears —which is
        what the ROM does by leaving it without `BAF_HAY`—."""
        return self.hp > 0 and not self.oculto

    # The four parameters as a computation sees them: `AdjustParam` from
    # game_battler.cpp, that is `clamp(base + modificador, 1, 999)`. Without
    # states there is neither half nor double.
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
    """The combatant of an LDB actor, with whatever it has equipped.

    The parameters come from `rules.equipped_params`, which is the same function
    the equipment screen uses: the level's plus what each piece adds,
    clamped to [1, 999]. The HP are the level's and carry no equipment, like
    `Game_Actor::GetMaxHp` in RM2k, where equipment does not touch HP.

    The hit chance is 90: `Game_Actor::GetHitChance` with a weapon without
    its own `hit`. **The weapon's `hit` is not read**, and it is declared
    debt: no weapon in ABL lowers it, but the day one does this will be
    wrong silently.

    The level is the LDB's `initial_level` and not 1: see `rules.level_of`.
    Until 2026-09-13 it was 1 and Kersh fought with 40 HP and attack 17
    instead of 168 and 80. With `nivel`, whatever it reached: see
    `port.experience`.
    """
    actor = db.actors[numero]
    if equipo is None:
        equipo = list(actor.initial_equipment)
    ataque, defensa, espiritu, agilidad = rules.equipped_params(db, numero,
                                                               equipo, nivel)
    critico = (100 // actor_critico_cada(db, numero)) \
        if actor_tiene_critico(db, numero) else 0
    quien = Combatiente(actor.name, rules.param_of(actor, "maxhp", nivel),
                        ataque, defensa, agilidad, 90, critico, True, numero,
                        espiritu, rules.param_of(actor, "maxsp", nivel),
                        habilidades_de(db, numero, nivel),
                        sp_arma=sp_del_arma(db, equipo))
    return quien


def actor_tiene_critico(db, numero):
    """The actor's `critical_hit`, from the LDB. In ABL none has it."""
    return bool(getattr(db.actors[numero], "critical_hit", False))


def actor_critico_cada(db, numero):
    return getattr(db.actors[numero], "critical_hit_chance", 30) or 30


def enemigo_de(db, enemy_id, lugar, oculto=False):
    """The combatant of an LDB enemy; `oculto` is the `invisible` of its
    place in the troop.

    The hit chance is `Game_Enemy::GetHitChance`: 70 for one with `miss` set
    and 90 otherwise. The critical, `GetCriticalHitChance` times a hundred
    and truncated, which with the default 30 gives 3.
    """
    e = db.enemies[enemy_id]
    critico = (100 // (e.critical_hit_chance or 30)) if e.critical_hit else 0
    quien = Combatiente(e.name, e.max_hp, e.attack, e.defense, e.agility,
                        e.hit, critico, False, lugar, e.spirit, e.max_sp,
                        acciones=acciones_de_enemigo(db, enemy_id))
    # What it drops when it dies: the item and its chance in percent. See
    # `botin`.
    quien.botin_item = e.drop_id
    quien.botin_chance = e.drop_prob
    quien.oculto = oculto
    quien.exp = e.exp
    quien.oro = e.gold
    return quien


def enemigos_de_la_tropa(db, tropa):
    """The combatants of a troop, in their order and with their hidden ones,
    up to `ENEMIES_MAX` like the battle."""
    t = db.troops[tropa]
    return [enemigo_de(db, e, n, oculto)
            for n, (e, oculto) in enumerate(
                list(zip(t.members, t.hidden))[:ENEMIES_MAX])]


def _turnos(turno, base, multiplo):
    """`Game_Battle::CheckTurns(turns, base, multiple)`."""
    if multiplo == 0:
        return turno >= base and turno == base
    return turno >= base and (turno - base) % multiplo == 0


class PaginaDeTropa:
    """An event page of the troop, **with what the model needs**: when it is
    met —`AreConditionsMet`, RM2k's six triggers— and whom it brings into
    the battle. Of its commands it runs only `ShowHiddenMonster`, the
    single-switch `ControlSwitches` and the battle branches on a switch,
    which is what is needed to know whether a `ShowHiddenMonster` inside a
    branch runs —the Rat King's is inside one, which the page itself
    closes—. The rest —messages, skills, variables, sounds— does not change
    who fights nor draws battle randomness, and is not modeled.

    The switches are the battle's, `Batalla.estado`, which starts with the
    ones passed in: the ROM reads them from the map.
    """

    def __init__(self, pagina):
        self.activos = list(pagina.active)
        self.c = pagina.condition
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
            raise NotImplementedError("a page on a variable: the model has no "
                                      "variables")
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
            # Only if it is in the party, like the ROM: see `ba_pag_cumple`.
            suyos = [a for a in batalla.actores if a.numero == c["actor_id"]]
            if not suyos:
                return False
            a = suyos[0]
            if not (c["actor_hp_min"] <= 100 * a.hp // a.hp_max
                    <= c["actor_hp_max"]):
                return False
        return True

    def correr(self, batalla):
        """The commands, with the switch branches resolved: a branch that is
        not taken skips everything nested deeper than it."""
        saltear_desde = None        # the indent of the branch not taken
        for cmd in self.comandos:
            if saltear_desde is not None:
                if cmd.indent > saltear_desde:
                    continue
                if cmd.code == 23310 and cmd.indent == saltear_desde:
                    saltear_desde = None    # the `else` of the one not taken
                    continue
                saltear_desde = None
            p = cmd.parameters
            if cmd.code == 13310:
                if p[0] != 0:
                    raise NotImplementedError("a battle branch that is not "
                                              "on a switch")
                prendido = bool(batalla.estado.get(p[1]))
                if prendido != (p[2] == 0):
                    saltear_desde = cmd.indent
            elif cmd.code == 23310:
                # The `else` of a branch that was taken: it is skipped.
                saltear_desde = cmd.indent
            elif cmd.code == events.CONTROL_SWITCHES:
                if p[0] != 0 or p[1] != p[2] or p[3] not in (0, 1):
                    raise NotImplementedError("a ControlSwitches the model "
                                              "does not know")
                batalla.estado[p[1]] = p[3] == 0
            elif cmd.code == events.SHOW_HIDDEN_MONSTER:
                if p[0] < len(batalla.enemigos):
                    batalla.enemigos[p[0]].oculto = False


def oro_de_la_tropa(db, tropa):
    """`Game_EnemyParty::GetMoney`: the `gold` of each **dead** enemy, which
    in a victory is all of them except those that stayed hidden —as in
    `experience.troop_exp`—, up to `ENEMIES_MAX`. It is the sum of
    the whole troop; the ROM subtracts the hidden ones' when winning. It
    rolls nothing."""
    return sum(db.enemies[e].gold for e in db.troops[tropa].members[:ENEMIES_MAX])


def acierto_por_agilidad(base, agi_fuente, agi_blanco):
    """`CalcToHitAgiAdjustment` from algo.cpp.

        to_hit = 100 - (100 - to_hit) * (1 + (tgt_agi / src_agi - 1) / 2)

    which is the same as subtracting from 100 the product by
    `(src + tgt) / (2 src)`. easyrpg does it in `float` and returns an
    `int`, that is, it truncates the result toward zero: `trunc(100 - x)` is
    `100 - ceil(x)` while the result is positive, and that is why the
    division here **rounds up**. Without that the two sides drift apart by
    one point of hit chance every so often, which is exactly the kind of
    difference that is not seen until a hit misses.
    """
    fuente = max(1, agi_fuente)
    resta = (100 - base) * (fuente + agi_blanco)
    return 100 - -(-resta // (2 * fuente))


def dano_normal(fuente, blanco, critico, azar):
    """`CalcNormalAttackEffect` and `VarianceAdjustEffect` with variance 4.

        dmg = max(0, atk / 2 - def / 4)
        critical: * 3
        variance: adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2

    Rows, weapon attributes and the charged attack are not here: this port
    has none of the three.
    """
    dano = max(0, fuente.ataque // 2 - blanco.defensa // 4)
    if critico:
        dano *= 3
    return varianza_ajustar(dano, 4, azar)


def ajustar_por_defensa(dano, blanco):
    """`AdjustDamageForDefend`: whoever defends takes half. The "strong
    defense" is a state and there are no states."""
    return _mitad(dano) if blanco.defendiendo else dano


class Batalla:
    """A battle, turn by turn. It is easyrpg's `Scene_Battle_Rpg2k` with
    what this port does.

    The loop of a turn, in the order it consumes randomness —and that order
    is the contract with the ROM—:

    1. the player chooses the command of each living actor (no roll);
    2. each living enemy chooses what to do and against whom
       —`CreateEnemyActions`, see `accion_del_enemigo`—: **one roll for the
       action if it has more than one possible, and one for the target if
       the action asks for one**;
    3. `CreateExecutionOrder`: **one roll per combatant that acts**, for its
       `agi + rand(0, agi / 4 + 3)`, and then they are sorted from highest
       to lowest with a stable order;
    4. they run in that order, skipping those that died along the way. Each
       attack rolls **three times**: hit, critical and variance, and the
       critical one is rolled even if the chance is zero;
    5. on winning, **one roll per enemy with an item**, in troop order: see
       `tirar_el_botin`.

    Step 2 going before step 3 is not a detail: it is the order of
    `SelectNextActor`, which calls `CreateEnemyActions()` and then
    `CreateExecutionOrder()`.
    """

    def __init__(self, actores, enemigos, semilla=BATALLA_SEMILLA,
                 paginas=(), switches=None):
        self.actores = list(actores)
        self.enemigos = list(enemigos)
        self.azar = Azar(semilla)
        self.turno = 0
        # The troop's pages —see `PaginaDeTropa`—, those that already ran
        # this turn —`executed`— and the switches they look at.
        self.paginas = list(paginas)
        self.hechas = set()
        self.estado = dict(switches or {})
        self.resultado = None
        self.huida_chance = self._chance_de_huir()
        self.registro = []          # what happened, for a test to count
        # The switches a `switch` skill turned on: `Skill::vExecute` does
        # `SetAffectedSwitch(skill.switch_id)` and `Scene_Battle` actually
        # turns it on. Here the number is collected, which is what the test
        # compares against the ROM's bit.
        self.switches = []
        # The items the enemies dropped on losing: see `tirar_el_botin`.
        self.botin = []

    # --- escaping --------------------------------------------------------
    def _promedio(self, quienes):
        vivos = [c for c in quienes if c.vivo] or list(quienes)
        return sum(c.agilidad for c in vivos) // max(1, len(vivos))

    def _chance_de_huir(self):
        """`Scene_Battle::InitEscapeChance`:

            base = round(100 * enemies_agi / party_agi)
            chance = clamp(150 - base, 0, 100)

        easyrpg's rounding is `RoundTo`, that is to the nearest integer; here
        it is `(2a + b) // (2b)`, which is the same with integers and without
        floats.
        """
        enemigos = self._promedio(self.enemigos)
        grupo = max(1, self._promedio(self.actores))
        base = (2 * 100 * enemigos + grupo) // (2 * grupo)
        return max(0, min(100, 150 - base))

    def huir(self):
        """`TryEscape`: it rolls against the chance and, if it fails, the
        chance goes up ten.

        Returns True if it escaped. `first_strike` is not here: the two
        battles of the intro have it at zero.
        """
        if self.azar.porciento(self.huida_chance):
            self.resultado = HUIDA
            return True
        self.huida_chance = min(100, self.huida_chance + 10)
        return False

    # --- the troop's pages ---------------------------------------------------
    def revisar_paginas(self):
        """`CheckBattleEndAndScheduleEvents` until none is left: with a whole
        side out nothing runs; otherwise, the first page that is met and has
        not run this turn, and then again from the first. The ROM does it in
        `ba_pag_probar`."""
        while self.vivos(self.enemigos) and self.vivos(self.actores):
            for i, pagina in enumerate(self.paginas):
                if i not in self.hechas and pagina.cumple(self):
                    self.hechas.add(i)
                    pagina.correr(self)
                    break
            else:
                return

    def empezar(self):
        """Before the first commands, on turn 0: the `eCheckEvents` of
        `ProcessSceneActionFightAutoEscape`."""
        self.revisar_paginas()

    # --- the turn ----------------------------------------------------------
    def vivos(self, quienes):
        return [c for c in quienes if c.vivo]

    def accion_del_enemigo(self, enemigo):
        """What this enemy does: `SelectEnemyAiActionRpgRtCompat`, with the
        list from `acciones_de_enemigo`. Returns `(rating, habilidad,
        efectiva)` or None if it has no possible one left.

        1. The possible ones are those `IsActionValid` allows: the attack
           always, a skill if it has enough SP (`IsSkillUsable`);
        2. each possible one weighs `max(0, rating - maximum + 10)`: **with
           ten points less than the best, an action never comes up**. That is
           why of the four plant enemies that carry `ShortCircuit` only the
           Tangle Wire uses it, which has it at 50 like the attack; the
           Scrapped Droid (10), the Trash Hauler and the Junkbot (30) never;
        3. and then the one that is not `efectiva` weighs zero —the maximum
           was already taken counting it, which is what easyrpg does—;
        4. `rand(0, sum - 1)` is rolled and one is chosen by weight, in list
           order.

        **With a single action of weight there is no roll**, and that is not
        RM2k's: it is the same distribution and it leaves the randomness of
        the battles that already existed —enemies that only attack— exactly
        as it was before enemies chose. RPG_RT draws from another generator
        anyway.
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
        raise AssertionError("cannot happen: `cual` is less than the sum")

    def acciones_de_los_enemigos(self):
        """`CreateEnemyActions`: each living enemy chooses its action
        —`accion_del_enemigo`— and then its target, which is the order of
        `MakeAttack` and `MakeSkillAction`:

        * attacking, or a skill with `enemy` scope: a random living actor,
          `GetRandomActiveBattler`, **one roll**;
        * one with `ally` scope: a random living enemy —`GetRandomSkillTarget`
          among the ones the skill affects, which without states are all of
          them—, **one roll**;
        * `self`, `enemies` and `party`: no roll, because the scope says the
          target. The one using it is recorded.

        If no living actor is left it stops and the remaining enemies are
        left without an action: without that the two sides would roll a
        different number of times."""
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
            if skill.scope == lcf.SKILL_SCOPE_ENEMY:
                blanco = blancos[self.azar.hasta(len(blancos) - 1)]
            elif skill.scope == lcf.SKILL_SCOPE_ALLY:
                # Among the ones the skill affects, which are all the living
                # ones: one that is not `efectiva` weighed zero and does not
                # get here.
                suyos = self.vivos(self.enemigos)
                blanco = suyos[self.azar.hasta(len(suyos) - 1)]
            else:
                blanco = enemigo
            acciones.append((enemigo, ORDEN_HABILIDAD, (skill, blanco)))
        return acciones

    def orden_de_ejecucion(self, acciones):
        """`CreateExecutionOrder`: `agi + rand(0, agi / 4 + 3)`, from highest
        to lowest and with a **stable** order, which is what `std::sort` does
        on a list that already comes in the order it was stacked."""
        for quien, _orden, _blanco in acciones:
            quien.orden = quien.agilidad + self.azar.hasta(
                quien.agilidad // 4 + 3)
        return sorted(range(len(acciones)),
                      key=lambda i: -acciones[i][0].orden)

    def atacar(self, fuente, blanco):
        """A normal attack, with its three rolls. Returns (hit, critical,
        damage).

        Before anything, and without rolling, it charges the weapon's SP:
        `Normal::vStart` —see `sp_del_arma`—. It is charged even if the hit
        misses, and with SP at zero it attacks anyway: RM2k does not gray out
        `Attack`."""
        fuente.sp = max(0, fuente.sp - fuente.sp_arma)
        acierto = acierto_por_agilidad(fuente.acierto, fuente.agilidad,
                                       blanco.agilidad)
        pego = self.azar.porciento(acierto)
        critico = self.azar.porciento(fuente.critico if pego else 0)
        if not pego:
            # The critical roll was made anyway, but the hit missed.
            return False, False, 0
        dano = dano_normal(fuente, blanco, critico, self.azar)
        dano = ajustar_por_defensa(dano, blanco)
        dano = max(-DANO_MAX, min(DANO_MAX, dano))
        blanco.hp = max(0, blanco.hp - dano)
        return True, critico, dano

    def usar_habilidad(self, fuente, skill, blanco):
        """`Game_BattleAlgorithm::Skill`, with what this port knows how to
        do.

        The order it consumes randomness in **is the contract with the ROM**,
        and it comes from `vExecute` read top to bottom:

        1. the cost is deducted **before anything** —`vStart`— and rolls
           nothing;
        2. a `switch` skill turns its switch on and **ends there**:
           `vExecute` returns before any roll;
        3. the critical: `Rand::PercentChance(crit_chance)`, **always**, even
           if the chance is zero. And for an LDB skill it always is, because
           `CalcCriticalHitChance` receives `easyrpg_critical_hit_chance`,
           which defaults to 0 and not -1;
        4. the variance, if the effect ended up greater than zero;
        5. one roll against the hit chance **for each thing the skill
           affects**, in the order HP, SP, attack, defense, spirit, agility.

        Steps 3 to 5 go **once per target**: see `blancos_de_la_habilidad`.

        What is not here: states, attributes, absorbing and reviving. Of
        AG7's, three touch states —BioWarfare, HeadButt and RemoveStatus—:
        the first and the last do nothing but charge their SP and roll the
        critical, and HeadButt hits without leaving the state.
        """
        from rpgmaker import lcf
        fuente.sp = max(0, fuente.sp - costo_de(skill))
        if skill.type == lcf.SKILL_TYPE_SWITCH:
            self.switches.append(skill.switch_id)
            self.registro.append((self.turno, fuente.nombre, fuente.nombre,
                                  True, False, 0, fuente.hp))
            return
        for uno in self.blancos_de_la_habilidad(fuente, skill, blanco):
            self._habilidad_sobre(fuente, skill, uno)

    def blancos_de_la_habilidad(self, fuente, skill, blanco):
        """Whom it falls on, in the order `vExecute` walks them:
        `AlgorithmBase::Start` with the scope's `party_target`, which is
        `GetBattlers` in screen order skipping the ones `IsTargetValid`
        discards —the dead—.

        `enemy` and `ally` fall on the one chosen; `self`, on the one using
        it; `enemies` and `party`, on each living one of the opposite side or
        its own, **each with its rolls**: the critical, the variance and the
        hit rolls are repeated per target."""
        from rpgmaker import lcf
        propios, contrarios = ((self.actores, self.enemigos) if fuente.es_actor
                               else (self.enemigos, self.actores))
        if skill.scope == lcf.SKILL_SCOPE_SELF:
            return [fuente]
        if skill.scope == lcf.SKILL_SCOPE_ENEMIES:
            return self.vivos(contrarios)
        if skill.scope == lcf.SKILL_SCOPE_PARTY:
            return self.vivos(propios)
        return [blanco]

    def _habilidad_sobre(self, fuente, skill, blanco):
        """`vExecute` on one target: see `usar_habilidad`."""
        # `CalcSkillToHit`: the skill's `hit`, which all seven have at 100.
        # The `failure_message == 3` path is not taken —none has it— and it
        # is declared as what is missing.
        acierto = skill.hit
        critico = self.azar.porciento(0)
        efecto = efecto_habilidad(fuente, blanco, skill, critico)
        efecto = varianza_ajustar(efecto, skill.variance, self.azar)
        efecto = max(-DANO_MAX, min(DANO_MAX, efecto))
        positivo = not skill.targets_enemies
        if not positivo:
            efecto = -efecto
        if skill.affect_hp and self.azar.porciento(acierto):
            if positivo:
                # A heal does not kill: `max(-(cur_hp - 1), hp_effect)`.
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

    # --- victory ---------------------------------------------------------
    def experiencia(self):
        """`Game_EnemyParty::GetExp` on winning: that of the dead, which are
        all except those that stayed hidden. The ROM subtracts these from the
        troop's: `ba_sin_ocultos`."""
        return sum(e.exp for e in self.enemigos if not e.oculto)

    def oro(self):
        """`GetMoney`, like `experiencia`."""
        return sum(e.oro for e in self.enemigos if not e.oculto)

    def tirar_el_botin(self):
        """`Game_EnemyParty::GenerateDrops`: for each enemy, in troop order,
        **one roll if it has an item** —`ChanceOf(drop_prob, 100)`, which is
        `GetRandomNumber(1, 100) <= rate` and with our randomness gives the
        same as `porciento`— and none if not. The one with chance 100 is
        rolled anyway. `jugar_turno` calls it on winning, which is when
        `ProcessSceneActionVictory` does it; returns the items won in order,
        one per enemy that dropped its own."""
        ganados = []
        for enemigo in self.enemigos:
            if enemigo.oculto:
                continue        # it did not die: `IsDead` is false
            item = getattr(enemigo, "botin_item", 0)
            if item > 0 and self.azar.porciento(enemigo.botin_chance):
                ganados.append(item)
        return ganados

    def jugar_turno(self, ordenes):
        """A whole turn. `ordenes` is, per living actor and in party order,
        `(ORDEN_ATACAR, lugar_del_enemigo)` or `(ORDEN_DEFENDER, 0)`.

        Returns the outcome if the battle ended, or None.

        The troop's pages run **before each action and after the last one**
        —`ePreAction`—, and the recorded ones are cleared at the start, which
        is `NextTurn`. The ones before the commands of the next turn are the
        same as those after the last action, so no extra pass is needed: see
        `empezar` for those of turn 0.
        """
        self.turno += 1
        self.hechas = set()
        for quien in self.actores + self.enemigos:
            quien.defendiendo = False
        acciones = []
        for actor, (orden, blanco) in zip(self.vivos(self.actores), ordenes):
            if orden == ORDEN_ITEM:
                # Here `blanco` is `(item, lugar_del_actor)`: the LDB item and
                # whom it is given to.
                item, quien = blanco
                acciones.append((actor, orden, (item, self.actores[quien])))
                continue
            if orden == ORDEN_HABILIDAD:
                # And here `(skill, lugar)`: the LDB skill and the target's
                # place, in the list of the side its `scope` points to.
                skill, quien = blanco
                lado = (self.enemigos if skill.targets_enemies
                        else self.actores)
                # A switch one asks for no target: `Scene_Battle::AssignSkill`
                # records it on the one using it, wherever its `scope`
                # points. The same for multi-target and self ones, whose
                # target the scope says: see `blancos_de_la_habilidad`.
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
                # `Defend` marks the defender **when its turn comes**, not when
                # choosing: an enemy that acts before hits it in full. It is
                # RM2k's behavior.
                quien.defendiendo = True
                continue
            if orden == ORDEN_HUIR:
                continue
            if orden == ORDEN_HABILIDAD:
                # A dead target **is not retargeted**, as with an item:
                # `Skill`'s `IsTargetValid` discards it and the action is
                # lost.
                skill, blanco = blanco
                if not blanco.vivo:
                    continue
                self.usar_habilidad(quien, skill, blanco)
                continue
            if orden == ORDEN_ITEM:
                # An item cannot miss and nobody dodges it: it rolls nothing.
                # The target is **not** retargeted, which is the opposite of
                # an attack: `Game_BattleAlgorithm::Item` goes to the one
                # chosen, and if it changed along the way the item is spent
                # anyway and does whatever `efecto_de_item` says with it as it
                # is now. A revived one does not act this turn —it had no
                # command— and next turn it asks again, which is `vivos` when
                # handing them out.
                item, blanco = blanco
                antes = blanco.hp
                blanco.hp, _levantado = efecto_de_item(item, blanco)
                self.registro.append((self.turno, quien.nombre, blanco.nombre,
                                      True, False, antes - blanco.hp,
                                      blanco.hp))
                continue
            if not blanco.vivo:
                # `Game_BattleAlgorithm` retargets another one on the same
                # side when the target died before its turn came.
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
