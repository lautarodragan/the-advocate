//! An actor's experience and level, as RM2k computes them.
//!
//! easyrpg-player's `Game_Actor` —`CalculateExp`, `MakeExpList`,
//! `GetNextExp`, `GetMaxLevel`, `SetLevel`, `ChangeExp`— and its
//! `MaxExpValue` and `MaxLevel`, with the values an RM2k database gives
//! them. easyrpg's `double` is `f64` and C++'s `(int)` truncation is `as
//! i64`, so there is no approximation to declare.

use ditto::schema::Actor;

/// RM2k's `MaxExpValue()`.
pub const EXP_MAX: i64 = 999_999;
/// RM2k's `MaxLevel()`.
pub const LEVEL_MAX: i64 = 50;

/// The six parameter curves of `Parameters`, in the format's order.
pub const CURVES: [&str; 6] = ["maxhp", "maxsp", "attack", "defense", "spirit", "agility"];

/// Each parameter per level, from level 1, in the order of [`CURVES`].
pub fn curves(actor: &Actor) -> [&[i16]; 6] {
    let p = &actor.parameters;
    [&p.maxhp, &p.maxsp, &p.attack, &p.defense, &p.spirit, &p.agility]
}

/// `Game_Actor::GetMaxLevel`: RM2k's, capped by `final_level`.
pub fn max_level(actor: &Actor) -> i64 {
    (actor.final_level as i64).clamp(1, LEVEL_MAX)
}

/// `SetLevel` clamps the initial level between 1 and the maximum; that is
/// also what a 0 in the database reads as.
pub fn initial_level(actor: &Actor) -> i64 {
    (actor.initial_level as i64).clamp(1, max_level(actor))
}

/// `Game_Actor::CalculateExp` with RM2k's curve: the **accumulated**
/// experience it takes to go from `level` to the next.
///
/// The loop runs from the level downward, and the inflation is recomputed
/// with a fixed `level + 1` —the argument's, not the loop's—: that is what
/// easyrpg does, and not a typo here.
pub fn exp_for(actor: &Actor, level: i64) -> i64 {
    let mut base = actor.exp_base as f64;
    let mut inflation = 1.5 + actor.exp_inflation as f64 * 0.01;
    let correction = actor.exp_correction as f64;
    let mut result: i64 = 0;
    for _ in 0..level.max(0) {
        result = result.saturating_add((correction + base) as i64);
        base *= inflation;
        inflation = ((level + 1) as f64 * 0.002 + 0.8) * (inflation - 1.0) + 1.0;
    }
    result.min(EXP_MAX)
}

/// `Game_Actor::MakeExpList`: `list[n]` is what it takes to go from `n` to
/// `n + 1`, and `list[0]` is zero. Its length is [`max_level`].
pub fn exp_list(actor: &Actor) -> Vec<i64> {
    std::iter::once(0)
        .chain((1..max_level(actor)).map(|n| exp_for(actor, n)))
        .collect()
}

/// `Game_Actor::GetNextExp(level)`: -1 at the cap.
pub fn next_exp(actor: &Actor, level: i64) -> i64 {
    if level >= max_level(actor) || level <= -1 {
        -1
    } else if level == 0 {
        0
    } else {
        exp_for(actor, level)
    }
}

/// The experience it starts with: the `Game_Actor` constructor sets the
/// level to 0 and calls `ChangeLevel(initial_level)`, which leaves it at
/// `GetBaseExp()`, that is `GetNextExp(level - 1)`.
pub fn initial_exp(actor: &Actor) -> i64 {
    next_exp(actor, initial_level(actor) - 1).max(0)
}

/// `Game_Actor::ChangeExp(exp + amount)` for an amount that does not take
/// away, which is the only kind a battle or an event that adds gives:
/// `(level, exp)` after it.
///
/// easyrpg's loop goes up while `GetNextExp(level)` is not -1 and does not
/// pass the new experience; at the cap it keeps going until its turns run
/// out, and `SetLevel` caps the level anyway.
pub fn add_exp(actor: &Actor, mut level: i64, exp: i64, amount: i64) -> (i64, i64) {
    let new_exp = (exp + amount).clamp(0, EXP_MAX);
    if new_exp > exp {
        for _ in level + 1..=max_level(actor) {
            let next = next_exp(actor, level);
            if next != -1 && next > new_exp {
                break;
            }
            level += 1;
        }
    }
    (level.min(max_level(actor)), new_exp)
}
