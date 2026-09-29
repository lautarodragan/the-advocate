//! Experience and level of the actors, as RM2k does them, and the tables
//! the cartridge carries them in.
//!
//! **None of the numbers here are ours.** They are easyrpg-player's:
//! `Game_Actor::CalculateExp`, `MakeExpList`, `GetNextExp`, `GetMaxLevel`
//! and `SetLevel` in `src/game_actor.cpp`, and `MaxExpValue` and `MaxLevel`
//! in `src/game_constants.cpp`.
//!
//! The console does no floating point: the curve is computed here and
//! travels as a table per level. easyrpg's `double` is `f64`, and the
//! truncation of C++'s `(int)` is `as i64`, so there is no approximation to
//! declare.

use crate::asm;
use crate::fail::{Bad, Result};
use crate::game::{Actor, Game, CURVES};
use std::collections::BTreeMap;

/// RM2k's `MaxExpValue()`.
pub const EXP_MAX: i64 = 999_999;
/// RM2k's `MaxLevel()`.
pub const LEVEL_MAX: i64 = 50;
/// The bytes of the save that hold the experience: four per slot.
pub const SAVE_BYTES: usize = 0x200;

/// `Game_Actor::GetMaxLevel`: RM2k's, capped by `final_level`.
pub fn max_level(actor: &Actor) -> i64 {
    actor.final_level.clamp(1, LEVEL_MAX)
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
        exp_list(actor)[level as usize]
    }
}

/// `SetLevel` clamps the initial level between 1 and the maximum.
pub fn initial_level(actor: &Actor) -> i64 {
    actor.initial_level.clamp(1, max_level(actor))
}

/// The experience it starts with: the `Game_Actor` constructor sets the
/// level to 0 and calls `ChangeLevel(initial_level)`, which leaves it at
/// `GetBaseExp()`, that is `GetNextExp(level - 1)`.
pub fn initial_exp(actor: &Actor) -> i64 {
    next_exp(actor, initial_level(actor) - 1).max(0)
}

/// The actors that carry experience and level, in the order of their slot:
/// those of `party` the game has, sorted. `None` is a slot nobody owns:
/// **there is always at least one**, because with zero the ROM's reset
/// would copy a zero-length block, and a DMA of zero bytes copies 64 KB.
///
/// `party` is the actors that can fight —only they gain experience—, which
/// is the caller's to know: a slot per actor that fights and not per actor
/// in the database is what keeps the save small.
pub fn slots(game: &Game, party: &[i64]) -> Vec<Option<i64>> {
    let mut slots: Vec<Option<i64>> = party
        .iter()
        .filter(|a| game.actors.contains_key(a))
        .map(|&a| Some(a))
        .collect();
    slots.sort();
    if slots.is_empty() {
        slots.push(None);
    }
    slots
}

/// The experience and level tables, in `RODATA`, which is where the text
/// leaves the segment. Per slot of [`slots`]:
///
/// ```text
/// exp_initial    four bytes: the starting experience, 24 bits, and the
///                level. It is what the reset copies to the save.
/// exp_level_max  GetMaxLevel(), one byte.
/// exp_curve      where its row starts in exp_table, a word.
/// level_row      six words: where each parameter curve starts in
///                level_params, in the order of CURVES.
/// ```
///
/// `actor_exp_k` is the slot of each actor, from 0 to the database's last,
/// or `$FF`; `exp_table` is `MakeExpList` of each distinct curve —four
/// bytes per level, `LEVEL_MAX` levels— and `level_params` the six curves
/// of each slot, `LEVEL_MAX` words each. `EXP_K` is how many slots, and
/// `EXP_LEVEL_MAX` the levels of a row.
pub fn tables(game: &Game, party: &[i64]) -> Result<String> {
    let slots = slots(game, party);
    let n_actors = game
        .actors
        .keys()
        .next_back()
        .map(|last| last + 1)
        .ok_or_else(|| Bad::answer("the game has no actors"))?;
    // A duplicate keeps the last of its slots, which is where the reset
    // leaves it: each slot is copied in order.
    let mut k_of: BTreeMap<i64, i64> = BTreeMap::new();
    for (k, a) in slots.iter().enumerate() {
        if let Some(a) = a {
            k_of.insert(*a, k as i64);
        }
    }
    let levels = LEVEL_MAX as usize;
    let mut curves: Vec<Vec<i64>> = Vec::new();
    let (mut curve_of, mut initial, mut max_levels) = (Vec::new(), Vec::new(), Vec::new());
    let (mut rows, mut params) = (Vec::new(), Vec::new());
    for a in &slots {
        let actor = a.map(|a| &game.actors[&a]);
        let mut curve = actor.map(exp_list).unwrap_or_else(|| vec![0]);
        curve.resize(levels, 0);
        let index = match curves.iter().position(|c| *c == curve) {
            Some(index) => index,
            None => {
                curves.push(curve);
                curves.len() - 1
            }
        };
        curve_of.push((4 * levels * index) as i64);
        let exp = actor.map(initial_exp).unwrap_or(0);
        initial.extend([
            exp & 0xFF,
            (exp >> 8) & 0xFF,
            exp >> 16,
            actor.map(initial_level).unwrap_or(1),
        ]);
        max_levels.push(actor.map(max_level).unwrap_or(1));
        for c in 0..CURVES.len() {
            rows.push(2 * params.len() as i64);
            let values = actor.map(|a| a.params[c].as_slice()).unwrap_or(&[]);
            params
                .extend((0..levels).map(|level| values.get(level).copied().unwrap_or(0) & 0xFFFF));
        }
    }
    if 4 * slots.len() > SAVE_BYTES {
        return Err(Bad::answer(format!(
            "{} actors with experience don't fit in the {SAVE_BYTES} bytes of FAR_EXP",
            slots.len()
        )));
    }
    let mut out = format!(
        ".segment \"RODATA\"\nEXP_K = {}\nEXP_LEVEL_MAX = {LEVEL_MAX}\n",
        slots.len()
    );
    let actor_k: Vec<i64> = (0..n_actors)
        .map(|a| k_of.get(&a).copied().unwrap_or(0xFF))
        .collect();
    asm::table(&mut out, "actor_exp_k", ".byte", 1, &actor_k);
    asm::table(&mut out, "exp_initial", ".byte", 1, &initial);
    asm::table(&mut out, "exp_level_max", ".byte", 1, &max_levels);
    asm::table(&mut out, "exp_curve", ".word", 2, &curve_of);
    asm::table(&mut out, "exp_table", ".dword", 4, &curves.concat());
    asm::table(&mut out, "level_row", ".word", 2, &rows);
    asm::table(&mut out, "level_params", ".word", 2, &params);
    Ok(out)
}
