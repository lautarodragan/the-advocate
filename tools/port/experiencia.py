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

from port.constantes import ENEMIGOS_MAX

# RM2k's `MaxExpValue()` and `MaxLevel()`: `easyrpg_max_exp` and
# `easyrpg_max_level` come as -1 in an RM2k LDB, and with that these apply.
EXP_MAX = 999999
NIVEL_MAX = 50


def nivel_max(actor):
    """`Game_Actor::GetMaxLevel`: RM2k's, capped by `final_level`."""
    return max(1, min(NIVEL_MAX, actor.final_level))


def exp_para(actor, nivel):
    """`Game_Actor::CalculateExp` with RM2k's curve (`exp_curve == 1`).

    It is the **accumulated** experience needed to go from level `nivel` to
    the next. The loop runs from the level downward, and the inflation is
    recomputed with a fixed `level + 1` —the argument's, not the loop's—:
    that is what is written in easyrpg and not a typo here.
    """
    base = float(actor.exp_base)
    inflacion = 1.5 + actor.exp_inflation * 0.01
    correccion = float(actor.exp_correction)
    resultado = 0
    for _ in range(nivel, 0, -1):
        resultado = resultado + int(correccion + base)
        base = base * inflacion
        inflacion = ((nivel + 1) * 0.002 + 0.8) * (inflacion - 1) + 1
    return min(resultado, EXP_MAX)


def lista_de(actor):
    """`Game_Actor::MakeExpList`: `lista[n]` is what it takes to go from `n`
    to `n + 1`, and `lista[0]` stays at zero. Its length is `GetMaxLevel()`."""
    return [0] + [exp_para(actor, n) for n in range(1, nivel_max(actor))]


def siguiente(actor, nivel):
    """`Game_Actor::GetNextExp(level)`: -1 at the cap."""
    if nivel >= nivel_max(actor) or nivel <= -1:
        return -1
    if nivel == 0:
        return 0
    return lista_de(actor)[nivel]


def exp_inicial(actor):
    """How much experience it starts with: the `Game_Actor` constructor sets
    the level to 0 and calls `ChangeLevel(initial_level)`, which leaves the
    experience at `GetBaseExp()`, that is `GetNextExp(nivel - 1)`."""
    return max(0, siguiente(actor, nivel_inicial(actor) - 1))


def nivel_inicial(actor):
    """`SetLevel` clamps `initial_level` between 1 and the maximum."""
    return max(1, min(nivel_max(actor), actor.initial_level))


def sumar(actor, nivel, exp, cantidad):
    """`Game_Actor::ChangeExp(GetExp() + cantidad)` for an amount that does
    not subtract, which is the only kind a battle gives. Returns
    `(nivel, exp)`.

    easyrpg's loop goes up while `GetNextExp(nivel)` is not -1 and does not
    exceed the new experience; with -1 —the cap— it keeps adding, but the
    `for` runs out of turns and `SetLevel` caps it anyway. The adjustment
    experience of `ChangeLevel` —`max(GetBaseExp(), GetExp())`— moves nothing
    when going up, because the base of the new level never exceeds what one
    has.
    """
    nueva = max(0, min(EXP_MAX, exp + cantidad))
    if nueva > exp:
        for _ in range(nivel + 1, nivel_max(actor) + 1):
            proximo = siguiente(actor, nivel)
            if proximo != -1 and proximo > nueva:
                break
            nivel += 1
    return min(nivel, nivel_max(actor)), nueva


def exp_de_la_tropa(db, tropa):
    """`Game_EnemyParty::GetExp`: that of each **dead** enemy. A victory has
    them all dead except the ones that stayed hidden, so this is the sum of
    the whole troop, up to `ENEMIGOS_MAX` like the battle, and the ROM
    subtracts the hidden ones' when winning: see `ba_sin_ocultos` and
    `batalla.Batalla.experiencia`."""
    return sum(db.enemies[e].exp
               for e in db.troops[tropa].members[:ENEMIGOS_MAX])
