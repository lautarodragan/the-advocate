"""RM2k's turn-based battle, modeled with the same rules as the ROM.

It is the sibling of `screens.py` for the battle: the formulas —damage,
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
  `BATTLE_SEED`. Having its own and not sharing `FAR_RANDOM` is what keeps
  a battle from advancing the map's randomness: a random `ControlVars` gives
  the same with or without a battle in between.

* **The divisions.** Where easyrpg does the math in floating point and
  truncates it on return, here it is integer. In the agility adjustment
  that matters, and so it uses **division rounding up**: truncating
  `100 - x` toward zero is the same as subtracting the ceiling of `x`, so
  the integer math gives exactly the same as the floating one. See
  `hit_rate_by_agility`.

* **What is missing.** States, attributes, rows and the double attack. And
  of the troop's event pages, which the ROM runs since 2026-09-21, the model
  knows **when they run and whom they bring into the battle**
  —`TroopPage`— and nothing else: the rest of what they do is checked by
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

# The seed of the battle's randomness. It differs from `RANDOM_SEED` on
# purpose: see above. The value means nothing, it only has to be nonzero —the
# xorshift gets stuck at zero— and be the same on both sides.
BATTLE_SEED = 0x2B1D

# How many fit in a battle. The party is RM2k's, four; the enemies,
# `constants.ENEMIES_MAX`.
PARTY_MAX = 4

# The three outcomes, in the order the bytecode carries their destinations.
VICTORY, ESCAPE, DEFEAT = 0, 1, 2

# The commands the player can give: `command_attack`, `command_defend` and
# `battle_escape` from the LDB. Attacking asks for a target; the other two do
# not.
#
# In RM2k escaping is a **party** command, from a menu that comes before
# handing out the commands; here it is a per-actor command and it is resolved
# the moment it is chosen. If it succeeds, the battle ends there; if not,
# that actor is left with `COMMAND_ESCAPE`, which in the turn does nothing but
# say so. It is a declared simplification: it saves a whole mode of the ROM's
# machine and leaves both sides with a single list of actions.
COMMAND_ATTACK, COMMAND_DEFEND, COMMAND_ESCAPE = 0, 1, 2
# And using an item, since 2026-09-13: `Game_BattleAlgorithm::Item`. It goes
# fourth and not among the others so as not to renumber what was already
# there.
COMMAND_ITEM = 3
# And a skill, `Game_BattleAlgorithm::Skill`. It goes fifth for the same
# reason: on screen it shows second —the original puts it between Attack and
# Defend— but the number is the command's and not the column's.
COMMAND_SKILL = 4


def item_usable_in_battle(item):
    """Whether this item goes in the list the battle offers.

    `Game_Party::IsItemUsable` with `in_battle`: a medicine —`type` 0 in
    liblcf, which the JSON dump calls 6— can be used unless it is marked
    `occasion_field1`, "only outside battle".

    And of those, this port offers **only the ones that recover HP**, with
    one more condition for the `ko_only` ones: that they revive, that is,
    that they remove the dead state, because a `ko_only` that does not revive
    is of no use to anyone —see `item_effect`—. What is left out and why:

    * the SP ones: **SP is already state since 2026-09-13**, so this went
      from impossible to debt —what is missing is `recover_sp` on the item
      side, which is the same math as HP's—;
    * the ones that raise a parameter permanently: there is no state for
      that.

    The `ko_only` ones —Phoenix Down, Pungent Elixir, Jumper Cable— are in
    since 2026-09-26: reviving is removing the dead state, and this port's
    battle has no other state than that one, which is having zero HP.
    """
    return (item.type == KIND_MEDICINE and not item.occasion_field1
            and (item.recover_hp or item.recover_hp_rate)
            and (revives(item) or not item.ko_only))


def revives(item):
    """Whether the item removes the dead state: the first of its
    `state_set`, which is state 1. It is the `MED_RAISES` bit of
    `item_medicina`."""
    return item.state_set[:1] == [True]


def healing(item, target):
    """How much this item heals on this target.

    `Game_BattleAlgorithm::Item::vExecute`:

        hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp

    and then `Game_Battler::ChangeHp` caps it at what is missing up to the
    maximum. The division is integer on both sides, like all of them here.
    """
    hp = item.recover_hp_rate * target.hp_max // 100 + item.recover_hp
    return max(0, min(hp, target.hp_max - target.hp))


def item_effect(item, target):
    """The HP the target of a medicine is left with: `vExecute` and what
    `ApplyAll` does afterwards, branch by branch.

    * standing and `ko_only`: nothing —`SetIsSuccess` with no effect—;
    * standing: the `healing`;
    * down and the item does not revive: nothing, because `ApplyHpEffect`
      does not touch a dead one. Until 2026-09-26 both sides revived it by
      adding the heal to the zero HP, and no test saw it because a downed
      one could not be chosen;
    * down and it revives: `RemoveStates`'s `SetHp(1)` and then
      `ApplyStateEffect`'s `ChangeHp(hp - 1)`, that is `max(1, healing)`.
      It is the same as `Game_Battler::UseItem` from the menu.

    Returns `(hp, levantado)`.
    """
    if target.alive:
        if item.ko_only:
            return target.hp, False
        return target.hp + healing(item, target), False
    if not revives(item):
        return target.hp, False
    return max(1, healing(item, target)), True


# `Item::Type_medicine`, which in liblcf is 0. This repo's JSON dump numbers
# them differently —there medicines are 6— so the number comes from
# `lcf.Item.type`, which is the LDB's.
KIND_MEDICINE = 6

# The cap of a parameter, like `Game_Actor::GetAtk` and its siblings.
PARAM_MAX = 999
# And the damage's: `Game_BattleAlgorithm::MaxDamageValue()` for RM2k.
DAMAGE_MAX = 999


def skill_usable(skill):
    """Whether this battle knows how to offer this skill.

    It is the sibling of `item_usable_in_battle` and, like that one, **cuts
    down to what this port does** and declares it instead of doing it wrong:

    * the type has to be `normal` or `switch`. `teleport` and `escape` do
      not exist here, and `subskill` is RM2k3's;
    * and the cost has to fit in two digits, which is what the list writes.
      None in the game reaches 100.

    **All five scopes are in since 2026-09-27** —milestone 4 of Lashe City:
    taro asked that AG7 not lose any of its skills—. The multi-target ones,
    `enemies` and `party`, repeat the effect on each living target on that
    side, in screen order, and `self` is the one using it: see
    `Battle.skill_targets`. Until that day they were left out, and
    with them `Gamble for Credits`, Arden's only one.
    """
    from rpgmaker import lcf
    return (skill.type in (lcf.SKILL_TYPE_NORMAL, lcf.SKILL_TYPE_SWITCH)
            and skill.sp_cost <= 99)


def needs_target(skill):
    """Whether the menu asks for whom when choosing it: only the
    single-target ones —`enemy` and `ally`— and not switch ones, which
    `Scene_Battle::AssignSkill` records on the one using it. Not the
    multi-target ones nor `self` either: their target is decided by the
    scope."""
    from rpgmaker import lcf
    return (skill.type != lcf.SKILL_TYPE_SWITCH
            and skill.scope in (lcf.SKILL_SCOPE_ENEMY,
                                lcf.SKILL_SCOPE_ALLY))


def skill_works_alone(skill):
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
# the basic attack; `efectiva` is `skill_works_alone`, which the AI
# looks at **after** taking the maximum.
ACTION_KIND_BASIC, ACTION_KIND_SKILL = 0, 1
ACTION_BASIC_ATTACK = 0
ACTION_CONDITION_ALWAYS = 0
# How many actions an enemy can carry: the ROM weighs them in `BA_SKILL_LIST`,
# which is that long. The converter stops if one carries more.
ACTIONS_MAX = 16
# The rating of the action set when the enemy has none left: with a single
# one it does not matter which, because nothing is rolled.
ACTION_RATING_ALONE = 50


def actions_of_enemy(db, enemy_id):
    """The enemy's actions this port knows how to do, in LDB order.

    It is the list `EnemyAi::SelectEnemyAiActionRpgRtCompat` walks, **cut
    down to what exists here** —and what is cut is declared—:

    * the basic attack (`kind` 0, `basic` 0) and the skills the battle knows
      how to do (`kind` 1, see `skill_usable`), **except switch ones**:
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
    values = []
    for action in db.enemies[enemy_id].actions:
        if action.condition_type != ACTION_CONDITION_ALWAYS \
                or action.switch_on or action.switch_off:
            continue
        if action.kind == ACTION_KIND_BASIC \
                and action.basic == ACTION_BASIC_ATTACK:
            values.append((action.rating, None, True))
            continue
        if action.kind != ACTION_KIND_SKILL:
            continue
        skill = db.skills.get(action.skill_id)
        if skill is None or skill.type != lcf.SKILL_TYPE_NORMAL \
                or not skill_usable(skill):
            continue
        values.append((action.rating, skill, skill_works_alone(skill)))
    return values or [(ACTION_RATING_ALONE, None, True)]


def weapon_sp_of(db, equipment):
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
    weapon = db.items.get(equipment[0]) if equipment and equipment[0] else None
    if weapon is None or weapon.type != lcf.ITEM_TYPE_WEAPON:
        return 0
    return weapon.sp_cost


def skills_of(db, number, level=None):
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
    `skill_usable`.
    """
    return [s for s in rules.learned_skills(db, number, level)
            if skill_usable(db.skills[s])]


def level_learned(db, number, skill):
    """At which level this actor learns this skill: the lowest of the rows
    of its table that name it. `LearnLevelSkills` learns it at the first one
    it reaches and `LearnSkill` does not repeat it. 0 if the table does not
    name it: that one is only taught by a `ChangeSkills`."""
    return min((level for level, s in db.actors[number].skills if s == skill),
               default=0)


def skill_command_name(db, number):
    """What this actor's skill command is called in the menu.

    `Game_Actor::GetSkillName`: the actor's `skill_name` if it has
    `rename_skill` set, and otherwise the LDB's `command_skill` —"Tech
    Skill"—. The four actors of the intro have it set: "AgentTrain",
    "Telepathy", "Slicing" and "Special".
    """
    actor = db.actors[number]
    if actor.rename_skill and actor.skill_name:
        return actor.skill_name
    return rules.battle_terms(db)["habilidad"]


def cost_of(skill):
    """`Algo::CalcSkillCost`: in RM2k, plain `sp_cost`.

    `sp_percent` is RM2k3's and `half_sp_cost` is a state, and there are no
    states.
    """
    return skill.sp_cost


def apply_variance(base, var, rng):
    """`Algo::VarianceAdjustEffect`.

        adj = max(1, var * base / 10); base += rand(0, adj) - adj / 2

    **It only rolls if `var > 0` and `base > 0`**, which is what the `if`
    says; without that condition the two sides would drift out of phase on
    the next roll every time a switch skill or a zero hit went through here.
    """
    if var > 0 and base > 0:
        adjust = max(1, var * base // 10)
        return base + rng.up_to(adjust) - adjust // 2
    return base


def skill_effect(source, target, skill, critical=False):
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
    effect = skill.power
    effect += skill.physical_rate * source.attack // 20
    effect += skill.magical_rate * source.spirit // 40
    if skill.targets_enemies and not skill.ignore_defense:
        effect -= skill.physical_rate * target.defense // 40
        effect -= skill.magical_rate * target.spirit // 80
    effect = max(0, effect)
    if critical:
        effect *= 3
    return effect


def _half(n):
    """C++'s division by two, which **truncates toward zero**.

    It is needed because `AdjustDamageForDefend` divides a skill's effect,
    which can be negative: in C++ -25/2 is -12 and in Python -25 // 2 is -13.
    One point of damage of difference that only shows up when someone
    defends against a skill, that is, the kind of discrepancy that takes
    weeks to be seen.
    """
    return -((-n) // 2) if n < 0 else n // 2


def modifier_change(mod, base, delta):
    """`Game_Battler::CanChangeAtkModifier` and its three siblings.

        nuevo = clamp(mod + delta, -base / 2, base)

    and returns `nuevo - mod`, that is how much it actually moved. The floor
    is half the base parameter: an enemy cannot be left with less than half
    its attack no matter how many skills are thrown at it.
    """
    new = max(-(base // 2), min(base, mod + delta))
    return new - mod


class Rng:
    """The battle's xorshift, with its own seed.

    `last(n)` returns a number from 0 to n **inclusive**, which is the range
    of easyrpg's `Rand::GetRandomNumber(0, n)`. The remainder is not uniform
    and it does not matter that it is not: what matters is that the ROM gets
    exactly the same, and the ROM does this same math with the hardware
    divider.
    """

    def __init__(self, seed=BATTLE_SEED):
        self.state = seed

    def up_to(self, n):
        self.state = events.next_random(self.state)
        return self.state % (n + 1) if n >= 0 else 0

    def percent(self, percent):
        """`Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.

        **It is always rolled**, even if `percent` is zero: it is what
        `Normal::vExecute` does with the critical, and if it were not rolled
        here the two sides would drift out of phase on the next roll.
        """
        return self.up_to(99) < percent


class Combatant:
    """One of those who fight, on whichever side.

    `is_actor` decides two things and is not cosmetic: which side it counts
    on when choosing a target, and whether the critical exists
    —`CalcCriticalHitChance` sets it to zero when both are of the same
    kind—.
    """

    def __init__(self, name, hp_max, attack, defense, agility, hit_rate,
                 critical=0, is_actor=True, number=0, spirit=0, sp_max=0,
                 skills=(), actions=None, weapon_sp=0):
        self.name = name
        self.hp_max = hp_max
        self.hp = hp_max
        # The four **base** parameters: what a skill modifies is the
        # `*_modificador` next to them, and what the math uses is the sum of
        # both, clamped. See `Game_Battler::GetAtk` and `AdjustParam`.
        self.base_attack = attack
        self.base_defense = defense
        self.base_spirit = spirit
        self.base_agility = agility
        self.mod_attack = 0
        self.mod_defense = 0
        self.mod_spirit = 0
        self.mod_agility = 0
        self.hit_rate = hit_rate
        self.critical = critical          # in percent, already an integer
        self.is_actor = is_actor
        self.number = number            # the LDB actor, or the place in the troop
        # The SP and what it knows how to do with them. The skills are those
        # of an actor's menu; an enemy's are in `actions`, which is its LDB
        # list —see `actions_of_enemy`— and an actor's is not used.
        # Without a list, it attacks: it is what every enemy did until
        # 2026-09-27.
        self.sp_max = sp_max
        self.sp = sp_max
        self.skills = list(skills)
        self.actions = (list(actions) if actions is not None
                        else [(ACTION_RATING_ALONE, None, True)])
        # What attacking costs it: `weapon_sp_of`. Zero for an enemy.
        self.weapon_sp = weapon_sp
        self.defending = False
        self.command = 0
        # A hidden enemy —`invisible` in the troop— is there but does not
        # fight: `Exists()` is `!IsHidden() && !IsDead()`. A page's
        # `ShowHiddenMonster` brings it into the battle: see
        # `TroopPage`.
        self.hidden = False
        # What it gives when it dies: `Game_EnemyParty::GetExp` and
        # `GetMoney`.
        self.exp = 0
        self.gold = 0

    @property
    def alive(self):
        """`Exists()`: it has HP left and is not hidden. Everything that
        chooses a target, hands out actions or decides victory looks at
        this, so a hidden one counts for nothing until it appears —which is
        what the ROM does by leaving it without `BAF_HAS`—."""
        return self.hp > 0 and not self.hidden

    # The four parameters as a computation sees them: `AdjustParam` from
    # game_battler.cpp, that is `clamp(base + modificador, 1, 999)`. Without
    # states there is neither half nor double.
    @property
    def attack(self):
        return max(1, min(PARAM_MAX, self.base_attack + self.mod_attack))

    @property
    def defense(self):
        return max(1, min(PARAM_MAX, self.base_defense + self.mod_defense))

    @property
    def spirit(self):
        return max(1, min(PARAM_MAX, self.base_spirit + self.mod_spirit))

    @property
    def agility(self):
        return max(1, min(PARAM_MAX, self.base_agility + self.mod_agility))


def actor_of(db, number, equipment=None, level=None):
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
    instead of 168 and 80. With `level`, whatever it reached: see
    `port.experience`.
    """
    actor = db.actors[number]
    if equipment is None:
        equipment = list(actor.initial_equipment)
    attack, defense, spirit, agility = rules.equipped_params(db, number,
                                                               equipment, level)
    critical = (100 // actor_critical_every(db, number)) \
        if actor_has_critical(db, number) else 0
    who = Combatant(actor.name, rules.param_of(actor, "maxhp", level),
                    attack, defense, agility, 90, critical, True, number,
                    spirit, rules.param_of(actor, "maxsp", level),
                    skills_of(db, number, level),
                    weapon_sp=weapon_sp_of(db, equipment))
    return who


def actor_has_critical(db, number):
    """The actor's `critical_hit`, from the LDB. In ABL none has it."""
    return bool(getattr(db.actors[number], "critical_hit", False))


def actor_critical_every(db, number):
    return getattr(db.actors[number], "critical_hit_chance", 30) or 30


def enemy_of(db, enemy_id, place, hidden=False):
    """The combatant of an LDB enemy; `hidden` is the `invisible` of its
    place in the troop.

    The hit chance is `Game_Enemy::GetHitChance`: 70 for one with `miss` set
    and 90 otherwise. The critical, `GetCriticalHitChance` times a hundred
    and truncated, which with the default 30 gives 3.
    """
    e = db.enemies[enemy_id]
    critical = (100 // (e.critical_hit_chance or 30)) if e.critical_hit else 0
    who = Combatant(e.name, e.max_hp, e.attack, e.defense, e.agility,
                    e.hit, critical, False, place, e.spirit, e.max_sp,
                    actions=actions_of_enemy(db, enemy_id))
    # What it drops when it dies: the item and its chance in percent. See
    # `drops`.
    who.drop_item = e.drop_id
    who.drop_chance = e.drop_prob
    who.hidden = hidden
    who.exp = e.exp
    who.gold = e.gold
    return who


def troop_enemies(db, troop):
    """The combatants of a troop, in their order and with their hidden ones,
    up to `ENEMIES_MAX` like the battle."""
    t = db.troops[troop]
    return [enemy_of(db, e, n, hidden)
            for n, (e, hidden) in enumerate(
                list(zip(t.members, t.hidden))[:ENEMIES_MAX])]


def _turns(turn, base, multiple):
    """`Game_Battle::CheckTurns(turns, base, multiple)`."""
    if multiple == 0:
        return turn >= base and turn == base
    return turn >= base and (turn - base) % multiple == 0


class TroopPage:
    """An event page of the troop, **with what the model needs**: when it is
    met —`AreConditionsMet`, RM2k's six triggers— and whom it brings into
    the battle. Of its commands it runs only `ShowHiddenMonster`, the
    single-switch `ControlSwitches` and the battle branches on a switch,
    which is what is needed to know whether a `ShowHiddenMonster` inside a
    branch runs —the Rat King's is inside one, which the page itself
    closes—. The rest —messages, skills, variables, sounds— does not change
    who fights nor draws battle randomness, and is not modeled.

    The switches are the battle's, `Battle.state`, which starts with the
    ones passed in: the ROM reads them from the map.
    """

    def __init__(self, page):
        self.active = list(page.active)
        self.c = page.condition
        self.commands = list(page.commands)

    def met(self, battle):
        if not self.active:
            return False
        c = self.c
        if "switch_a" in self.active and not battle.state.get(
                c["switch_a_id"]):
            return False
        if "switch_b" in self.active and not battle.state.get(
                c["switch_b_id"]):
            return False
        if "variable" in self.active:
            raise NotImplementedError("a page on a variable: the model has no "
                                      "variables")
        if "turn" in self.active and not _turns(
                battle.turn, c["turn_b"], c["turn_a"]):
            return False
        if "enemy_hp" in self.active:
            if c["enemy_id"] >= len(battle.enemies):
                return False
            e = battle.enemies[c["enemy_id"]]
            if not (c["enemy_hp_min"] <= 100 * e.hp // e.hp_max
                    <= c["enemy_hp_max"]):
                return False
        if "actor_hp" in self.active:
            # Only if it is in the party, like the ROM: see `ba_page_met`.
            matching = [a for a in battle.actors if a.number == c["actor_id"]]
            if not matching:
                return False
            a = matching[0]
            if not (c["actor_hp_min"] <= 100 * a.hp // a.hp_max
                    <= c["actor_hp_max"]):
                return False
        return True

    def run(self, battle):
        """The commands, with the switch branches resolved: a branch that is
        not taken skips everything nested deeper than it."""
        skip_from = None        # the indent of the branch not taken
        for cmd in self.commands:
            if skip_from is not None:
                if cmd.indent > skip_from:
                    continue
                if cmd.code == 23310 and cmd.indent == skip_from:
                    skip_from = None    # the `else` of the one not taken
                    continue
                skip_from = None
            p = cmd.parameters
            if cmd.code == 13310:
                if p[0] != 0:
                    raise NotImplementedError("a battle branch that is not "
                                              "on a switch")
                lit = bool(battle.state.get(p[1]))
                if lit != (p[2] == 0):
                    skip_from = cmd.indent
            elif cmd.code == 23310:
                # The `else` of a branch that was taken: it is skipped.
                skip_from = cmd.indent
            elif cmd.code == events.CONTROL_SWITCHES:
                if p[0] != 0 or p[1] != p[2] or p[3] not in (0, 1):
                    raise NotImplementedError("a ControlSwitches the model "
                                              "does not know")
                battle.state[p[1]] = p[3] == 0
            elif cmd.code == events.SHOW_HIDDEN_MONSTER:
                if p[0] < len(battle.enemies):
                    battle.enemies[p[0]].hidden = False


def troop_gold(db, troop):
    """`Game_EnemyParty::GetMoney`: the `gold` of each **dead** enemy, which
    in a victory is all of them except those that stayed hidden —as in
    `experience.troop_exp`—, up to `ENEMIES_MAX`. It is the sum of
    the whole troop; the ROM subtracts the hidden ones' when winning. It
    rolls nothing."""
    return sum(db.enemies[e].gold for e in db.troops[troop].members[:ENEMIES_MAX])


def hit_rate_by_agility(base, agi_source, agi_target):
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
    source = max(1, agi_source)
    subtract = (100 - base) * (source + agi_target)
    return 100 - -(-subtract // (2 * source))


def normal_damage(source, target, critical, rng):
    """`CalcNormalAttackEffect` and `VarianceAdjustEffect` with variance 4.

        dmg = max(0, atk / 2 - def / 4)
        critical: * 3
        variance: adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2

    Rows, weapon attributes and the charged attack are not here: this port
    has none of the three.
    """
    damage = max(0, source.attack // 2 - target.defense // 4)
    if critical:
        damage *= 3
    return apply_variance(damage, 4, rng)


def adjust_for_defense(damage, target):
    """`AdjustDamageForDefend`: whoever defends takes half. The "strong
    defense" is a state and there are no states."""
    return _half(damage) if target.defending else damage


class Battle:
    """A battle, turn by turn. It is easyrpg's `Scene_Battle_Rpg2k` with
    what this port does.

    The loop of a turn, in the order it consumes randomness —and that order
    is the contract with the ROM—:

    1. the player chooses the command of each living actor (no roll);
    2. each living enemy chooses what to do and against whom
       —`CreateEnemyActions`, see `enemy_action`—: **one roll for the
       action if it has more than one possible, and one for the target if
       the action asks for one**;
    3. `CreateExecutionOrder`: **one roll per combatant that acts**, for its
       `agi + rand(0, agi / 4 + 3)`, and then they are sorted from highest
       to lowest with a stable order;
    4. they run in that order, skipping those that died along the way. Each
       attack rolls **three times**: hit, critical and variance, and the
       critical one is rolled even if the chance is zero;
    5. on winning, **one roll per enemy with an item**, in troop order: see
       `roll_drops`.

    Step 2 going before step 3 is not a detail: it is the order of
    `SelectNextActor`, which calls `CreateEnemyActions()` and then
    `CreateExecutionOrder()`.
    """

    def __init__(self, actors, enemies, seed=BATTLE_SEED,
                 pages=(), switches=None):
        self.actors = list(actors)
        self.enemies = list(enemies)
        self.rng = Rng(seed)
        self.turn = 0
        # The troop's pages —see `TroopPage`—, those that already ran
        # this turn —`executed`— and the switches they look at.
        self.pages = list(pages)
        self.done_pages = set()
        self.state = dict(switches or {})
        self.result = None
        self.escape_chance = self._escape_chance()
        self.log = []          # what happened, for a test to count
        # The switches a `switch` skill turned on: `Skill::vExecute` does
        # `SetAffectedSwitch(skill.switch_id)` and `Scene_Battle` actually
        # turns it on. Here the number is collected, which is what the test
        # compares against the ROM's bit.
        self.switches = []
        # The items the enemies dropped on losing: see `roll_drops`.
        self.drops = []

    # --- escaping --------------------------------------------------------
    def _average(self, whom):
        n_alive = [c for c in whom if c.alive] or list(whom)
        return sum(c.agility for c in n_alive) // max(1, len(n_alive))

    def _escape_chance(self):
        """`Scene_Battle::InitEscapeChance`:

            base = round(100 * enemies_agi / party_agi)
            chance = clamp(150 - base, 0, 100)

        easyrpg's rounding is `RoundTo`, that is to the nearest integer; here
        it is `(2a + b) // (2b)`, which is the same with integers and without
        floats.
        """
        enemies = self._average(self.enemies)
        party = max(1, self._average(self.actors))
        base = (2 * 100 * enemies + party) // (2 * party)
        return max(0, min(100, 150 - base))

    def flee(self):
        """`TryEscape`: it rolls against the chance and, if it fails, the
        chance goes up ten.

        Returns True if it escaped. `first_strike` is not here: the two
        battles of the intro have it at zero.
        """
        if self.rng.percent(self.escape_chance):
            self.result = ESCAPE
            return True
        self.escape_chance = min(100, self.escape_chance + 10)
        return False

    # --- the troop's pages ---------------------------------------------------
    def check_pages(self):
        """`CheckBattleEndAndScheduleEvents` until none is left: with a whole
        side out nothing runs; otherwise, the first page that is met and has
        not run this turn, and then again from the first. The ROM does it in
        `ba_page_test`."""
        while self.living(self.enemies) and self.living(self.actors):
            for i, page in enumerate(self.pages):
                if i not in self.done_pages and page.met(self):
                    self.done_pages.add(i)
                    page.run(self)
                    break
            else:
                return

    def start(self):
        """Before the first commands, on turn 0: the `eCheckEvents` of
        `ProcessSceneActionFightAutoEscape`."""
        self.check_pages()

    # --- the turn ----------------------------------------------------------
    def living(self, whom):
        return [c for c in whom if c.alive]

    def enemy_action(self, enemy):
        """What this enemy does: `SelectEnemyAiActionRpgRtCompat`, with the
        list from `actions_of_enemy`. Returns `(rating, habilidad,
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
        weights = [(r, s, ef) for r, s, ef in enemy.actions
                   if s is None or enemy.sp >= cost_of(s)]
        if not weights:
            return None
        top = max(r for r, _s, _ef in weights)
        weights = [(max(0, r - top + 10) if ef else 0, (r, s, ef))
                   for r, s, ef in weights]
        weights = [(p, a) for p, a in weights if p > 0]
        if not weights:
            return None
        if len(weights) == 1:
            return weights[0][1]
        which = self.rng.up_to(sum(p for p, _a in weights) - 1)
        for weight, action in weights:
            which -= weight
            if which < 0:
                return action
        raise AssertionError("cannot happen: `cual` is less than the sum")

    def enemy_actions(self):
        """`CreateEnemyActions`: each living enemy chooses its action
        —`enemy_action`— and then its target, which is the order of
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
        actions = []
        for enemy in self.living(self.enemies):
            targets = self.living(self.actors)
            if not targets:
                break
            action = self.enemy_action(enemy)
            if action is None:
                continue
            _rating, skill, _ef = action
            if skill is None:
                target = targets[self.rng.up_to(len(targets) - 1)]
                actions.append((enemy, COMMAND_ATTACK, target))
                continue
            if skill.scope == lcf.SKILL_SCOPE_ENEMY:
                target = targets[self.rng.up_to(len(targets) - 1)]
            elif skill.scope == lcf.SKILL_SCOPE_ALLY:
                # Among the ones the skill affects, which are all the living
                # ones: one that is not `efectiva` weighed zero and does not
                # get here.
                matching = self.living(self.enemies)
                target = matching[self.rng.up_to(len(matching) - 1)]
            else:
                target = enemy
            actions.append((enemy, COMMAND_SKILL, (skill, target)))
        return actions

    def execution_order(self, actions):
        """`CreateExecutionOrder`: `agi + rand(0, agi / 4 + 3)`, from highest
        to lowest and with a **stable** order, which is what `std::sort` does
        on a list that already comes in the order it was stacked."""
        for who, _command, _target in actions:
            who.command = who.agility + self.rng.up_to(
                who.agility // 4 + 3)
        return sorted(range(len(actions)),
                      key=lambda i: -actions[i][0].command)

    def attack(self, source, target):
        """A normal attack, with its three rolls. Returns (hit, critical,
        damage).

        Before anything, and without rolling, it charges the weapon's SP:
        `Normal::vStart` —see `weapon_sp_of`—. It is charged even if the hit
        misses, and with SP at zero it attacks anyway: RM2k does not gray out
        `Attack`."""
        source.sp = max(0, source.sp - source.weapon_sp)
        hit_rate = hit_rate_by_agility(source.hit_rate, source.agility,
                                       target.agility)
        hit = self.rng.percent(hit_rate)
        critical = self.rng.percent(source.critical if hit else 0)
        if not hit:
            # The critical roll was made anyway, but the hit missed.
            return False, False, 0
        damage = normal_damage(source, target, critical, self.rng)
        damage = adjust_for_defense(damage, target)
        damage = max(-DAMAGE_MAX, min(DAMAGE_MAX, damage))
        target.hp = max(0, target.hp - damage)
        return True, critical, damage

    def use_skill(self, source, skill, target):
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

        Steps 3 to 5 go **once per target**: see `skill_targets`.

        What is not here: states, attributes, absorbing and reviving. Of
        AG7's, three touch states —BioWarfare, HeadButt and RemoveStatus—:
        the first and the last do nothing but charge their SP and roll the
        critical, and HeadButt hits without leaving the state.
        """
        from rpgmaker import lcf
        source.sp = max(0, source.sp - cost_of(skill))
        if skill.type == lcf.SKILL_TYPE_SWITCH:
            self.switches.append(skill.switch_id)
            self.log.append((self.turn, source.name, source.name,
                             True, False, 0, source.hp))
            return
        for one in self.skill_targets(source, skill, target):
            self._skill_on(source, skill, one)

    def skill_targets(self, source, skill, target):
        """Whom it falls on, in the order `vExecute` walks them:
        `AlgorithmBase::Start` with the scope's `party_target`, which is
        `GetBattlers` in screen order skipping the ones `IsTargetValid`
        discards —the dead—.

        `enemy` and `ally` fall on the one chosen; `self`, on the one using
        it; `enemies` and `party`, on each living one of the opposite side or
        its own, **each with its rolls**: the critical, the variance and the
        hit rolls are repeated per target."""
        from rpgmaker import lcf
        own, opponents = ((self.actors, self.enemies) if source.is_actor
                          else (self.enemies, self.actors))
        if skill.scope == lcf.SKILL_SCOPE_SELF:
            return [source]
        if skill.scope == lcf.SKILL_SCOPE_ENEMIES:
            return self.living(opponents)
        if skill.scope == lcf.SKILL_SCOPE_PARTY:
            return self.living(own)
        return [target]

    def _skill_on(self, source, skill, target):
        """`vExecute` on one target: see `use_skill`."""
        # `CalcSkillToHit`: the skill's `hit`, which all seven have at 100.
        # The `failure_message == 3` path is not taken —none has it— and it
        # is declared as what is missing.
        hit_rate = skill.hit
        critical = self.rng.percent(0)
        effect = skill_effect(source, target, skill, critical)
        effect = apply_variance(effect, skill.variance, self.rng)
        effect = max(-DAMAGE_MAX, min(DAMAGE_MAX, effect))
        positive = not skill.targets_enemies
        if not positive:
            effect = -effect
        if skill.affect_hp and self.rng.percent(hit_rate):
            if positive:
                # A heal does not kill: `max(-(cur_hp - 1), hp_effect)`.
                hp = max(-(target.hp - 1), effect)
            else:
                hp = adjust_for_defense(effect, target)
            target.hp = max(0, min(target.hp_max, target.hp + hp))
        if skill.affect_sp and self.rng.percent(hit_rate):
            target.sp = max(0, min(target.sp_max, target.sp + effect))
        for affects, mod, base in (
                (skill.affect_attack, "mod_attack", "base_attack"),
                (skill.affect_defense, "mod_defense", "base_defense"),
                (skill.affect_spirit, "mod_spirit", "base_spirit"),
                (skill.affect_agility, "mod_agility", "base_agility")):
            if not affects:
                continue
            if not self.rng.percent(hit_rate):
                continue
            delta = modifier_change(getattr(target, mod),
                                    getattr(target, base), effect)
            setattr(target, mod, getattr(target, mod) + delta)
        self.log.append((self.turn, source.name, target.name,
                         True, critical, -effect, target.hp))

    # --- victory ---------------------------------------------------------
    def experience(self):
        """`Game_EnemyParty::GetExp` on winning: that of the dead, which are
        all except those that stayed hidden. The ROM subtracts these from the
        troop's: `ba_no_hidden`."""
        return sum(e.exp for e in self.enemies if not e.hidden)

    def gold(self):
        """`GetMoney`, like `experience`."""
        return sum(e.gold for e in self.enemies if not e.hidden)

    def roll_drops(self):
        """`Game_EnemyParty::GenerateDrops`: for each enemy, in troop order,
        **one roll if it has an item** —`ChanceOf(drop_prob, 100)`, which is
        `GetRandomNumber(1, 100) <= rate` and with our randomness gives the
        same as `percent`— and none if not. The one with chance 100 is
        rolled anyway. `play_turn` calls it on winning, which is when
        `ProcessSceneActionVictory` does it; returns the items won in order,
        one per enemy that dropped its own."""
        earned = []
        for enemy in self.enemies:
            if enemy.hidden:
                continue        # it did not die: `IsDead` is false
            item = getattr(enemy, "drop_item", 0)
            if item > 0 and self.rng.percent(enemy.drop_chance):
                earned.append(item)
        return earned

    def play_turn(self, commands):
        """A whole turn. `commands` is, per living actor and in party order,
        `(COMMAND_ATTACK, lugar_del_enemigo)` or `(COMMAND_DEFEND, 0)`.

        Returns the outcome if the battle ended, or None.

        The troop's pages run **before each action and after the last one**
        —`ePreAction`—, and the recorded ones are cleared at the start, which
        is `NextTurn`. The ones before the commands of the next turn are the
        same as those after the last action, so no extra pass is needed: see
        `start` for those of turn 0.
        """
        self.turn += 1
        self.done_pages = set()
        for who in self.actors + self.enemies:
            who.defending = False
        actions = []
        for actor, (command, target) in zip(self.living(self.actors), commands):
            if command == COMMAND_ITEM:
                # Here `target` is `(item, lugar_del_actor)`: the LDB item and
                # whom it is given to.
                item, who = target
                actions.append((actor, command, (item, self.actors[who])))
                continue
            if command == COMMAND_SKILL:
                # And here `(skill, lugar)`: the LDB skill and the target's
                # place, in the list of the side its `scope` points to.
                skill, who = target
                side = (self.enemies if skill.targets_enemies
                        else self.actors)
                # A switch one asks for no target: `Scene_Battle::AssignSkill`
                # records it on the one using it, wherever its `scope`
                # points. The same for multi-target and self ones, whose
                # target the scope says: see `skill_targets`.
                dest = side[who] if needs_target(skill) else actor
                actions.append((actor, command, (skill, dest)))
                continue
            actions.append((actor, command,
                            self.enemies[target] if command == COMMAND_ATTACK
                            else None))
        actions += self.enemy_actions()
        for i in self.execution_order(actions):
            self.check_pages()
            who, command, target = actions[i]
            if not who.alive:
                continue
            if command == COMMAND_DEFEND:
                # `Defend` marks the defender **when its turn comes**, not when
                # choosing: an enemy that acts before hits it in full. It is
                # RM2k's behavior.
                who.defending = True
                continue
            if command == COMMAND_ESCAPE:
                continue
            if command == COMMAND_SKILL:
                # A dead target **is not retargeted**, as with an item:
                # `Skill`'s `IsTargetValid` discards it and the action is
                # lost.
                skill, target = target
                if not target.alive:
                    continue
                self.use_skill(who, skill, target)
                continue
            if command == COMMAND_ITEM:
                # An item cannot miss and nobody dodges it: it rolls nothing.
                # The target is **not** retargeted, which is the opposite of
                # an attack: `Game_BattleAlgorithm::Item` goes to the one
                # chosen, and if it changed along the way the item is spent
                # anyway and does whatever `item_effect` says with it as it
                # is now. A revived one does not act this turn —it had no
                # command— and next turn it asks again, which is `n_alive` when
                # handing them out.
                item, target = target
                before = target.hp
                target.hp, _revived = item_effect(item, target)
                self.log.append((self.turn, who.name, target.name,
                                 True, False, before - target.hp,
                                 target.hp))
                continue
            if not target.alive:
                # `Game_BattleAlgorithm` retargets another one on the same
                # side when the target died before its turn came.
                side = self.enemies if not target.is_actor else self.actors
                candidates = self.living(side)
                if not candidates:
                    continue
                target = candidates[0]
            hit, critical, damage = self.attack(who, target)
            self.log.append((self.turn, who.name, target.name,
                             hit, critical, damage, target.hp))
        self.check_pages()
        if not self.living(self.enemies):
            self.result = VICTORY
            self.drops = self.roll_drops()
        elif not self.living(self.actors):
            self.result = DEFEAT
        return self.result
