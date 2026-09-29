"""Experience and level of the actors, as RM2k does them.

It is the sibling of `batalla.py` for what happens **after** the battle: how
much experience it gives, when a level goes up and which parameters are
left. The ROM does the same math, and the tests demand the same number on
both sides.

**None of the numbers here are ours.** They come from easyrpg-player, cloned
in `/extras/ref`:

    src/game_actor.cpp          CalculateExp, MakeExpList, GetNextExp,
                                GetMaxLevel, ChangeExp, ChangeLevel,
                                GetBaseMaxHp and its siblings
    src/game_constants.cpp      MaxExpValue, MaxLevel
    src/game_enemyparty.cpp     GetExp
    src/scene_battle_rpg2k.cpp  ProcessSceneActionVictory

What the ROM **does not** do in floating point is compute the curve: the
converter computes it, here, and it travels in the cartridge as a table per
level. That way easyrpg's `double` is Python's `float`, which is the same
64-bit IEEE 754, and the truncation of C++'s `(int)` is Python's `int()`.
There is no approximation to declare.
"""

from port.constants import ENEMIES_MAX

# RM2k's `MaxExpValue()` and `MaxLevel()`: `easyrpg_max_exp` and
# `easyrpg_max_level` come as -1 in an RM2k LDB, and with that these apply.
EXP_MAX = 999999
LEVEL_MAX = 50


def max_level(actor):
    """`Game_Actor::GetMaxLevel`: RM2k's, capped by `final_level`."""
    return max(1, min(LEVEL_MAX, actor.final_level))


def exp_for(actor, level):
    """`Game_Actor::CalculateExp` with RM2k's curve (`exp_curve == 1`).

    It is the **accumulated** experience needed to go from level `level` to
    the next. The loop runs from the level downward, and the inflation is
    recomputed with a fixed `level + 1` —the argument's, not the loop's—:
    that is what is written in easyrpg and not a typo here.
    """
    base = float(actor.exp_base)
    inflation = 1.5 + actor.exp_inflation * 0.01
    correction = float(actor.exp_correction)
    result = 0
    for _ in range(level, 0, -1):
        result = result + int(correction + base)
        base = base * inflation
        inflation = ((level + 1) * 0.002 + 0.8) * (inflation - 1) + 1
    return min(result, EXP_MAX)


def exp_list(actor):
    """`Game_Actor::MakeExpList`: `lista[n]` is what it takes to go from `n`
    to `n + 1`, and `lista[0]` stays at zero. Its length is `GetMaxLevel()`."""
    return [0] + [exp_for(actor, n) for n in range(1, max_level(actor))]


def next_exp(actor, level):
    """`Game_Actor::GetNextExp(level)`: -1 at the cap."""
    if level >= max_level(actor) or level <= -1:
        return -1
    if level == 0:
        return 0
    return exp_list(actor)[level]


def initial_exp(actor):
    """How much experience it starts with: the `Game_Actor` constructor sets
    the level to 0 and calls `ChangeLevel(initial_level)`, which leaves the
    experience at `GetBaseExp()`, that is `GetNextExp(level - 1)`."""
    return max(0, next_exp(actor, initial_level(actor) - 1))


def initial_level(actor):
    """`SetLevel` clamps `initial_level` between 1 and the maximum."""
    return max(1, min(max_level(actor), actor.initial_level))


def add_exp(actor, level, exp, amount):
    """`Game_Actor::ChangeExp(GetExp() + cantidad)` for an amount that does
    not subtract, which is the only kind a battle gives. Returns
    `(nivel, exp)`.

    easyrpg's loop goes up while `GetNextExp(level)` is not -1 and does not
    exceed the new experience; with -1 —the cap— it keeps adding, but the
    `for` runs out of turns and `SetLevel` caps it anyway. The adjustment
    experience of `ChangeLevel` —`max(GetBaseExp(), GetExp())`— moves nothing
    when going up, because the base of the new level never exceeds what one
    has.
    """
    new_exp = max(0, min(EXP_MAX, exp + amount))
    if new_exp > exp:
        for _ in range(level + 1, max_level(actor) + 1):
            next_level_exp = next_exp(actor, level)
            if next_level_exp != -1 and next_level_exp > new_exp:
                break
            level += 1
    return min(level, max_level(actor)), new_exp


def troop_exp(db, troop):
    """`Game_EnemyParty::GetExp`: that of each **dead** enemy. A victory has
    them all dead except the ones that stayed hidden, so this is the sum of
    the whole troop, up to `ENEMIES_MAX` like the battle, and the ROM
    subtracts the hidden ones' when winning: see `ba_sin_ocultos` and
    `batalla.Batalla.experiencia`."""
    return sum(db.enemies[e].exp
               for e in db.troops[troop].members[:ENEMIES_MAX])
