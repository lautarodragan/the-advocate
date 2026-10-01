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
