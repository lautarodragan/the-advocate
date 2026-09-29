"""RM2k rules that several port modules use: what an actor knows, which
parameters it has at its level and what the battle terms are called.

They belong to `Game_Actor` and the LDB, not to any screen.
"""


def learned_skills(db, number, level=None):
    """The skills this actor **knows**, usable or not, sorted.

    It is plain `Game_Actor::LearnLevelSkills`: the ones with a level lower
    than or equal to its own. It is separate from `skills_of` because
    they are two different questions and mixing them up is paid on one side
    only: the battle menu can only offer the ones this port knows how to run
    —that is the `skill_usable` filter— but `IsSkillLearned`, which is
    what the `ConditionalBranch` branch asks, filters nothing.

    Both come from here so they cannot drift apart: the branch and the menu
    have to agree on what each one knows.
    """
    actor = db.actors[number]
    if level is None:
        level = actor.initial_level
    return sorted({s for at_level, s in actor.skills
                   if s and at_level <= level})


# Each actor's level comes from the LDB since 2026-09-13: it is its
# `initial_level`, which in ABL is not 1 —Kersh starts at 20, Core and Manta
# at 15— and the HP, the SP and the four parameters come from it.
#
# Until that day there was a mocked `NIVEL = 1` here, and **it was not just
# cosmetic**: with it Kersh showed 40 HP instead of 168 and fought with attack
# 17 instead of 80, so the whole balance of the battle was different. And it
# also led to the wrong conclusion that nobody knew any skill: all of them are
# learned at level 3 or higher, and with the real initial level all three
# know them from the first battle.
#
# Leveling up still does not exist, and that one is a decision: there is no
# experience. The level is a static fact of the LDB.


def level_of(actor):
    """The level an actor starts at: `Game_Actor::Setup`, which calls
    `ChangeLevel(initial_level)` when the field is there."""
    return actor.initial_level


def param_of(actor, which, level=None):
    """A parameter of the actor at its level: `maxhp`, `maxsp`, `attack`,
    `defense`, `spirit` or `agility`.

    The LDB table starts at level 1, so the index is the level minus one. An
    actor without the table —or with one shorter than its level, which does
    not happen in this game— gives zero, which is what the old code did.

    Without `level` it is the starting one; with it, whatever it reached by
    fighting: see `port.experience`.
    """
    values = actor.params.get(which) or []
    if level is None:
        level = level_of(actor)
    return values[level - 1] if level - 1 < len(values) else 0


PARAM_MAX = 999


def equipped_params(db, actor, equipment, level=None):
    """Attack, defense, spirit and agility: the level's plus what the
    equipment adds, clamped to [1, 999] like `Game_Actor::GetAtk` and its
    siblings. Without `level`, the starting one."""
    base = [param_of(db.actors[actor], k, level)
            for k in ("attack", "defense", "spirit", "agility")]
    for item in equipment:
        if item:
            base = [b + p for b, p in zip(base, db.items[item].points)]
    return [max(1, min(PARAM_MAX, b)) for b in base]


# The LDB terms the screen uses, in the order the converter emits them. The
# names are liblcf's —`fields.csv`, struct `Terms`— and not from memory: see
# rom/data/README.md. Until 2026-09-20 they were the chunk numbers from
# `ldb/chunks.h`, with the name beside them in a comment; today the name is
# the data and the comment is what the term says in the game.
BATTLE_TERMS = (
    ("attack", "command_attack"),        # "Attack"
    ("defend", "command_defend"),      # "Defend"
    ("escape", "battle_escape"),           # "Escape"
    ("hp", "hp_short"),                  # "HP"
    ("attacks", "attacking"),              # " attacks the enemy"
    ("defends", "defending"),
    ("critical", "actor_critical"),
    ("damage_enemy", "enemy_damaged"),   # " health lost."
    ("no_damage_enemy", "enemy_undamaged"),
    ("damage_actor", "actor_damaged"),
    ("no_damage_actor", "actor_undamaged"),
    ("victory", "victory"),
    ("defeat", "defeat"),
    ("fled", "escape_success"),
    ("no_fled", "escape_failure"),
    # The four from 2026-09-13: the two missing commands and the two lines
    # of the use-an-item message.
    ("use", "command_item"),            # "Use Item"
    ("skill", "command_skill"),      # "Tech Skill"
    ("uses", "use_item"),                 # " used."
    ("recovered", "hp_recovery"),         # " Recovered"
    # The four of what the victory reports, since 2026-09-26: see
    # `ba_vic_message` in battle_victory.s.
    ("exp_received", "exp_received"),    # " EXP"
    ("level", "level"),                  # "LEVEL"
    ("level_up", "level_up"),               # " achieved!"
    ("learned", "skill_learned"),       # " acquired!"
    # And those of the gold and items won, since 2026-09-27.
    ("gold_a", "gold_recieved_a"),        # " You found"
    ("currency", "gold"),                  # "Cr"
    ("gold_b", "gold_recieved_b"),        # " credits!"
    ("obtained", "item_recieved"),       # " obtained!"
)


def battle_terms(db):
    from rpgmaker import lcf
    return {n: lcf.to_string(db.terms[t]) for n, t in BATTLE_TERMS}
