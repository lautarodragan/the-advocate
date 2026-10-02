//! An actor's experience and level, its parameters at a level with its
//! equipment on, and the skills it knows, as RM2k computes them.
//!
//! easyrpg-player's `Game_Actor` —`CalculateExp`, `MakeExpList`,
//! `GetNextExp`, `GetMaxLevel`, `SetLevel`, `ChangeExp`, `GetAtk` and its
//! siblings, `LearnLevelSkills`— and its `MaxExpValue` and `MaxLevel`,
//! with the values an RM2k database gives them. easyrpg's `double` is
//! `f64` and C++'s `(int)` truncation is `as i64`, so there is no
//! approximation to declare.

use ditto::schema::{Actor, Item};

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

/// The cap of attack, defense, spirit and agility: `Game_Actor::GetAtk`
/// and its siblings clamp them to 1..`PARAM_MAX`.
pub const PARAM_MAX: i64 = 999;

/// The four curves equipment adds to, in the order of [`points`].
pub const EQUIPPED: [&str; 4] = ["attack", "defense", "spirit", "agility"];

/// The level an actor starts at, as the database says it:
/// `Game_Actor::Setup`, which calls `ChangeLevel(initial_level)`, with a 0
/// read as 1.
///
/// It is not [`initial_level`], which also caps it at [`max_level`]: the
/// parameters and the skills have always been read at this one, and the
/// two only differ in a database whose initial level passes its final one.
pub fn level_of(actor: &Actor) -> i64 {
    match actor.initial_level {
        0 => 1,
        level => level as i64,
    }
}

/// One of the six curves by its name in [`CURVES`]; `None` if no curve
/// has that name.
pub fn curve<'a>(actor: &'a Actor, which: &str) -> Option<&'a [i16]> {
    let at = CURVES.iter().position(|&c| c == which)?;
    Some(curves(actor)[at])
}

/// A curve at `level`: the database's table starts at level 1, so the
/// index is the level minus one, and past its end it is 0.
///
/// A level of 0 or less counts from the end, which is how the Python model
/// the callers replaced indexed it; it is not a level RM2k has, and `None`
/// is that count falling before the start.
pub fn curve_at(values: &[i16], level: i64) -> Option<i64> {
    let at = level - 1;
    if at >= values.len() as i64 {
        return Some(0);
    }
    let at = if at < 0 { values.len() as i64 + at } else { at };
    usize::try_from(at)
        .ok()
        .and_then(|at| values.get(at))
        .map(|&v| v as i64)
}

/// What an item adds when equipped: attack, defense, spirit, agility.
pub fn points(item: &Item) -> [i64; 4] {
    [
        item.atk_points1 as i64,
        item.def_points1 as i64,
        item.spi_points1 as i64,
        item.agi_points1 as i64,
    ]
}

/// The four [`EQUIPPED`] parameters of a level, `base`, with this
/// equipment on: what each item adds, and each clamped to 1..[`PARAM_MAX`]
/// like `Game_Actor::GetAtk` and its siblings.
pub fn with_equipment<'a>(
    base: [i64; 4],
    equipment: impl IntoIterator<Item = &'a Item>,
) -> [i64; 4] {
    let mut out = base;
    for item in equipment {
        for (o, p) in out.iter_mut().zip(points(item)) {
            *o += p;
        }
    }
    out.map(|o| o.clamp(1, PARAM_MAX))
}

/// An actor's starting equipment: weapon, shield, armor, helmet and
/// accessory, by item number, 0 for none.
pub fn initial_equipment(actor: &Actor) -> Vec<i32> {
    let e = &actor.initial_equipment;
    vec![
        e.weapon_id,
        e.shield_id,
        e.armor_id,
        e.helmet_id,
        e.accessory_id,
    ]
}

/// The skills this actor **knows**, usable or not, sorted and without
/// repeats: `Game_Actor::LearnLevelSkills`, the ones with a level lower
/// than or equal to its own. Without `level`, [`level_of`].
pub fn learned_skills(actor: &Actor, level: Option<i64>) -> Vec<i32> {
    let level = level.unwrap_or_else(|| level_of(actor));
    let mut out: Vec<i32> = actor
        .skills
        .iter()
        .filter(|l| l.skill_id != 0 && l.level as i64 <= level)
        .map(|l| l.skill_id)
        .collect();
    out.sort_unstable();
    out.dedup();
    out
}

/// At which level this actor learns this skill: the lowest of the rows of
/// its table that name it, or 0 if none does —that one only a
/// `ChangeSkills` teaches—.
pub fn level_learned(actor: &Actor, skill: i32) -> i64 {
    actor
        .skills
        .iter()
        .filter(|l| l.skill_id == skill)
        .map(|l| l.level as i64)
        .min()
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_curve_is_read_from_level_one_and_is_zero_past_its_end() {
        let values = [10, 20, 30];
        assert_eq!(curve_at(&values, 1), Some(10));
        assert_eq!(curve_at(&values, 3), Some(30));
        assert_eq!(curve_at(&values, 4), Some(0));
        assert_eq!(curve_at(&values, 0), Some(30));
        assert_eq!(curve_at(&[], 0), None);
    }

    #[test]
    fn equipment_adds_and_clamps() {
        let sword = Item {
            atk_points1: 1500,
            def_points1: -50,
            ..Default::default()
        };
        assert_eq!(
            with_equipment([10, 10, 10, 10], [&sword]),
            [PARAM_MAX, 1, 10, 10]
        );
    }
}
