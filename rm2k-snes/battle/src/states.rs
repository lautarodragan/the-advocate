//! What a condition's chance of taking hold is, on whom: the odds a skill
//! or a weapon rolls after its hit, `GetStateProbability`.
//!
//! Each condition of the database has a rate per rank —`a_rate` to
//! `e_rate`—, and each actor and enemy has a rank per condition, its
//! `state_ranks`: an actor's `C` where it says none, an enemy's `B`. An
//! actor's armor —shield, armor, helmet, accessory— with the condition in
//! its `state_set` lowers it to `100 - state_chance` percent, the strongest
//! of them. Everything here is easyrpg-player's:
//!
//! ```text
//! src/state.cpp       GetStateRate
//! src/game_actor.cpp  GetStateProbability
//! src/game_enemy.cpp  GetStateProbability
//! ```

use crate::db::{Db, ITEM_WEAPON};
use crate::fail::Result;

/// An actor's rank where its `state_ranks` says none, `C`.
pub const ACTOR_RANK: i64 = 2;
/// An enemy's, `B`: "Enemies have only B as the default state rank".
pub const ENEMY_RANK: i64 = 1;

/// The item types that resist: shield, armor, helmet and accessory.
const ITEM_SHIELD: i32 = 2;
const ITEM_ACCESSORY: i32 = 5;

/// `GetStateRate`: condition `id`'s rate at `rank`, 0 for one the database
/// lacks.
pub fn rate(db: &Db, id: i64, rank: i64) -> i64 {
    db.states.get(&(id as i32)).map_or(0, |s| {
        i64::from(match rank {
            0 => s.a_rate,
            1 => s.b_rate,
            2 => s.c_rate,
            3 => s.d_rate,
            _ => s.e_rate,
        })
    })
}

fn rank_in(ranks: &[u8], id: i64, default: i64) -> i64 {
    usize::try_from(id - 1)
        .ok()
        .and_then(|k| ranks.get(k))
        .map_or(default, |&r| i64::from(r).clamp(0, 4))
}

/// An actor's own rank in condition `id`, before its armor.
pub fn actor_rank(db: &Db, actor: i32, id: i64) -> Result<i64> {
    Ok(rank_in(&db.actor(actor)?.state_ranks, id, ACTOR_RANK))
}

/// An enemy's rank in condition `id`.
pub fn enemy_rank(db: &Db, enemy: i32, id: i64) -> Result<i64> {
    Ok(rank_in(&db.enemy(enemy)?.state_ranks, id, ENEMY_RANK))
}

/// What an actor's armor leaves of a condition's chance, in percent: the
/// lowest `100 - state_chance` of what it wears with `id` in its
/// `state_set`, 100 with none. `equipment` by item number, 0 for empty; a
/// weapon —also a second one, in the shield's slot— does not count.
pub fn armor_keeps(db: &Db, equipment: &[i32], id: i64) -> Result<i64> {
    let mut keeps = 100;
    for &n in equipment {
        if n <= 0 {
            continue;
        }
        let item = db.item(n)?;
        let kind = item.r#type.to_i32();
        if kind == ITEM_WEAPON || !(ITEM_SHIELD..=ITEM_ACCESSORY).contains(&kind) {
            continue;
        }
        let has = usize::try_from(id - 1)
            .ok()
            .and_then(|k| item.state_set.get(k))
            .copied()
            .unwrap_or(false);
        if has {
            keeps = keeps.min(100 - i64::from(item.state_chance));
        }
    }
    Ok(keeps)
}

/// `Game_Actor::GetStateProbability`: the chance condition `id` takes hold
/// of `actor` wearing `equipment`.
pub fn actor_odds(db: &Db, actor: i32, equipment: &[i32], id: i64) -> Result<i64> {
    let rank = actor_rank(db, actor, id)?;
    Ok(rate(db, id, rank) * armor_keeps(db, equipment, id)? / 100)
}

/// `Game_Enemy::GetStateProbability`.
pub fn enemy_odds(db: &Db, enemy: i32, id: i64) -> Result<i64> {
    Ok(rate(db, id, enemy_rank(db, enemy, id)?))
}

/// Every condition's odds on an actor, by number —0 is nobody's—.
pub fn actor_all(db: &Db, actor: i32, equipment: &[i32]) -> Result<Vec<i64>> {
    let top = db.states.keys().max().copied().unwrap_or(0) as i64;
    (0..=top)
        .map(|id| actor_odds(db, actor, equipment, id))
        .collect()
}

/// And on an enemy.
pub fn enemy_all(db: &Db, enemy: i32) -> Result<Vec<i64>> {
    let top = db.states.keys().max().copied().unwrap_or(0) as i64;
    (0..=top).map(|id| enemy_odds(db, enemy, id)).collect()
}

/// The conditions a skill gives —or, on its own side, takes—: the ones of
/// its `state_effects`, by number.
pub fn of_skill(effects: &[bool]) -> Vec<i64> {
    effects
        .iter()
        .enumerate()
        .filter(|(_, &on)| on)
        .map(|(k, _)| k as i64 + 1)
        .collect()
}
