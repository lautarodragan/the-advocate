//! The attributes: what a weakness or a resistance does to a hit. Each
//! attribute of the database has a rate per rank —`a_rate` to `e_rate`—,
//! whoever receives a hit has a rank per attribute, and whatever hits
//! carries a set of them: a skill its `attribute_effects`, an actor's
//! normal attack the `attribute_set` of its weapons.
//!
//! Everything here is easyrpg-player's, RPG Maker 2000's path:
//!
//! ```text
//! src/attribute.cpp   GetAttributeRateModifier, ApplyAttributeMultiplier,
//!                     ApplyAttributeNormalAttackMultiplier,
//!                     ApplyAttributeSkillMultiplier
//! src/game_actor.cpp  GetBaseAttributeRate
//! src/game_enemy.cpp  GetBaseAttributeRate
//! src/game_battler.cpp  GetAttributeRate, ShiftAttributeRate,
//!                       CanShiftAttributeRate
//! ```
//!
//! A skill with `affect_attr_defence` shifts its target's rank in each
//! attribute it carries one step for the rest of the battle —see
//! [`Received::shift_by`]; the roll is `Battle::skill_on`'s, in
//! `simulate.rs`—.
//!
//! **What is not here**: RM2k's rule that an actor cannot use a skill with
//! a physical attribute unless a weapon carries it; see the divergence
//! `what-attributes-do-not-model` in the book.

use crate::db::{Db, ITEM_WEAPON};
use crate::fail::Result;
use ditto::schema::{Attribute, AttributeType};

/// The neutral rank, `C`: the one who has none in the database has this.
pub const RANK_NEUTRAL: i64 = 2;
/// The highest rank, `E`.
pub const RANK_MAX: i64 = 4;

/// What one attribute does to whoever receives it: whether it is physical
/// —`Type_physical`; anything else counts as magical, as in easyrpg— and
/// the rate of the rank this one has in it now, in percent.
///
/// The rank is the database's —with an actor's armor— and a **shift** of
/// one step at most either way, which a skill with `affect_attr_defence`
/// gives and which lasts the battle: easyrpg's `attribute_shift`, added to
/// the base rank by `GetAttributeRate` and clamped to `A`..`E`. That is why
/// the five rates travel with it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Received {
    pub physical: bool,
    /// `rates[rank + shift]`, the rank clamped to `A`..`E`.
    pub rate: i64,
    /// The rank before the shift, already within `A`..`E`.
    pub rank: i64,
    /// -1, 0 or +1: +1 is one step more resistant.
    pub shift: i64,
    /// The attribute's rates for `A` to `E`.
    pub rates: [i64; 5],
}

impl Received {
    /// `attribute` at `rank`, unshifted.
    pub fn new(attribute: &Attribute, rank: i64) -> Received {
        let rates = [0, 1, 2, 3, 4].map(|r| rate_of(attribute, r));
        let rank = rank.clamp(0, RANK_MAX);
        Received {
            physical: physical(attribute),
            rate: rates[rank as usize],
            rank,
            shift: 0,
            rates,
        }
    }

    /// `CanShiftAttributeRate`: how much a shift of `by` would actually move
    /// it —`clamp(shift + by, -1, 1) - shift`—, 0 at the bound. easyrpg
    /// asks this **before** rolling, so a rank already at the bound rolls
    /// nothing.
    pub fn can_shift(&self, by: i64) -> i64 {
        (self.shift + by).clamp(-1, 1) - self.shift
    }

    /// `ShiftAttributeRate`: the shift moved by what [`Self::can_shift`]
    /// allows, and the rate read again at the new rank.
    pub fn shift_by(&mut self, by: i64) {
        self.shift += self.can_shift(by);
        self.rate = self.rates[(self.rank + self.shift).clamp(0, RANK_MAX) as usize];
    }
}

/// `GetAttributeRateModifier`: the attribute's rate for `rank`, 0 to 4.
pub fn rate_of(attribute: &Attribute, rank: i64) -> i64 {
    match rank {
        0 => attribute.a_rate as i64,
        1 => attribute.b_rate as i64,
        2 => attribute.c_rate as i64,
        3 => attribute.d_rate as i64,
        4 => attribute.e_rate as i64,
        _ => 0,
    }
}

/// Whether an attribute is physical.
pub fn physical(attribute: &Attribute) -> bool {
    attribute.r#type == AttributeType::Physical
}

/// A rank of the database's, `ranks[id - 1]`, or `C` when the list is
/// shorter.
fn rank_in(ranks: &[u8], index: usize) -> i64 {
    ranks.get(index).map_or(RANK_NEUTRAL, |&r| r as i64)
}

fn received(db: &Db, rank: impl Fn(usize) -> i64) -> Vec<Received> {
    db.attributes
        .values()
        .enumerate()
        .map(|(k, a)| Received::new(a, rank(k)))
        .collect()
}

/// `Game_Enemy::GetBaseAttributeRate`: the enemy's own rank, unclamped
/// —what `GetAttributeRate` clamps, `rate_of` reads as 0—.
pub fn enemy_rank(db: &Db, enemy: i32, index: usize) -> Result<i64> {
    Ok(rank_in(&db.enemy(enemy)?.attribute_ranks, index).clamp(0, RANK_MAX))
}

/// What each attribute does to enemy `enemy`, in the database's order.
pub fn received_by_enemy(db: &Db, enemy: i32) -> Result<Vec<Received>> {
    let ranks = db.enemy(enemy)?.attribute_ranks.clone();
    Ok(received(db, |k| rank_in(&ranks, k).clamp(0, RANK_MAX)))
}

/// The actor's rank in the database, before what its armor adds.
pub fn actor_own_rank(db: &Db, actor: i32, index: usize) -> Result<i64> {
    Ok(rank_in(&db.actor(actor)?.attribute_ranks, index).clamp(0, RANK_MAX))
}

/// Whether an item is armor —shield, armor, helmet or accessory—: what
/// `ForEachEquipment<false, true>` walks.
pub fn armor(kind: i32) -> bool {
    (2..=5).contains(&kind)
}

/// `Game_Actor::GetBaseAttributeRate`: the actor's own rank, **one higher**
/// —one step more resistant— if any armor it wears carries the attribute,
/// and clamped to `E`. One step however many pieces carry it.
pub fn actor_rank(db: &Db, actor: i32, equipment: &[i32], index: usize) -> Result<i64> {
    let own = actor_own_rank(db, actor, index)?;
    let mut boost = false;
    for &n in equipment {
        if n <= 0 {
            continue;
        }
        let item = db.item(n)?;
        if armor(item.r#type.to_i32()) && item.attribute_set.get(index).copied().unwrap_or(false) {
            boost = true;
        }
    }
    Ok((own + i64::from(boost)).clamp(0, RANK_MAX))
}

/// What each attribute does to actor `actor` wearing `equipment`.
pub fn received_by_actor(db: &Db, actor: i32, equipment: &[i32]) -> Result<Vec<Received>> {
    let mut out = Vec::new();
    for (k, a) in db.attributes.values().enumerate() {
        out.push(Received::new(a, actor_rank(db, actor, equipment, k)?));
    }
    Ok(out)
}

/// The attributes an actor's normal attack carries: those of the weapons
/// in its first two slots —the second holds one only with `two_weapon`—,
/// together. Unarmed it carries none: `easyrpg_unarmed_attribute_set` is
/// 2003's, empty in a 2000 game. An enemy's attack carries none either.
pub fn weapon_attributes(db: &Db, equipment: &[i32]) -> Result<Vec<bool>> {
    let mut out: Vec<bool> = Vec::new();
    for &n in equipment.iter().take(2) {
        if n <= 0 {
            continue;
        }
        let item = db.item(n)?;
        if item.r#type.to_i32() != ITEM_WEAPON {
            continue;
        }
        if out.len() < item.attribute_set.len() {
            out.resize(item.attribute_set.len(), false);
        }
        for (k, &has) in item.attribute_set.iter().enumerate() {
            out[k] |= has;
        }
    }
    Ok(out)
}

/// `ApplyAttributeMultiplier` with RPG Maker 2000's limit. Of the
/// attributes `carried` has —by index, `id - 1`— the best rate among the
/// physical ones and the best among the magical ones; with both, the effect
/// goes through the two —`magical * (physical * effect / 100) / 100`—, with
/// one, through that one, and with none it stays. **A negative rate does
/// not count** in 2000 —the limit is -1—, so it is as if it were not there.
///
/// An attribute past the end of the database stops the walk, which is
/// easyrpg's `break` with its warning.
pub fn apply(effect: i64, target: &[Received], carried: &[bool]) -> i64 {
    let (mut phys, mut mag) = (i64::MIN, i64::MIN);
    for (k, _) in carried.iter().enumerate().filter(|(_, &has)| has) {
        let Some(r) = target.get(k) else { break };
        if r.physical {
            phys = phys.max(r.rate);
        } else {
            mag = mag.max(r.rate);
        }
    }
    // C++'s division truncates toward zero; every product here is
    // nonnegative, so it is the plain one.
    let limit = -1;
    match (phys > limit, mag > limit) {
        (true, true) => mag * (phys * effect / 100) / 100,
        (true, false) => phys * effect / 100,
        (false, true) => mag * effect / 100,
        (false, false) => effect,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(physical: bool, rate: i64) -> Received {
        Received {
            physical,
            rate,
            rank: RANK_NEUTRAL,
            shift: 0,
            rates: [rate; 5],
        }
    }

    #[test]
    fn a_weakness_doubles_and_a_resistance_halves() {
        let target = [r(true, 100), r(false, 200), r(false, 50)];
        assert_eq!(apply(37, &target, &[false, true]), 74);
        assert_eq!(apply(37, &target, &[false, false, true]), 18);
        assert_eq!(apply(37, &target, &[]), 37);
    }

    #[test]
    fn of_one_kind_the_best_counts_and_the_two_kinds_multiply() {
        let target = [r(true, 50), r(true, 150), r(false, 200), r(false, 0)];
        // The best physical, 150, and not the product with the 50.
        assert_eq!(apply(40, &target, &[true, true]), 60);
        // The best magical is 200 even if the other is immune.
        assert_eq!(apply(40, &target, &[false, false, true, true]), 80);
        // Both kinds: 200 * (150 * 41 / 100) / 100 = 200 * 61 / 100.
        assert_eq!(apply(41, &target, &[false, true, true]), 122);
        // An immunity of one kind zeroes it, whatever the other says.
        assert_eq!(apply(41, &target, &[true, true, false, true]), 0);
    }

    #[test]
    fn a_negative_rate_does_not_count_in_2000() {
        let target = [r(true, -50), r(false, 150)];
        assert_eq!(apply(10, &target, &[true]), 10);
        assert_eq!(apply(10, &target, &[true, true]), 15);
    }

    #[test]
    fn an_attribute_past_the_database_stops_the_walk() {
        let target = [r(false, 200)];
        assert_eq!(apply(10, &target, &[false, true, true]), 10);
    }

    fn flame() -> Attribute {
        Attribute {
            a_rate: 200,
            b_rate: 150,
            c_rate: 100,
            d_rate: 50,
            e_rate: 0,
            ..Default::default()
        }
    }

    #[test]
    fn a_shift_moves_the_rank_one_step_and_no_further() {
        let mut flame = Received::new(&flame(), RANK_NEUTRAL);
        assert_eq!(flame.rate, 100);
        flame.shift_by(1);
        assert_eq!((flame.shift, flame.rate), (1, 50), "C and a step up: D");
        // At the bound a second one does not move it, and says so before
        // anyone rolls.
        assert_eq!(flame.can_shift(1), 0);
        flame.shift_by(1);
        assert_eq!((flame.shift, flame.rate), (1, 50));
        // The other way goes back to C and then to B, and stops there.
        assert_eq!(flame.can_shift(-1), -1);
        flame.shift_by(-1);
        assert_eq!(flame.rate, 100);
        flame.shift_by(-1);
        flame.shift_by(-1);
        assert_eq!((flame.shift, flame.rate), (-1, 150));
    }

    #[test]
    fn a_shift_past_the_ends_of_the_ranks_is_clamped_to_them() {
        // `GetAttributeRate` clamps base plus shift to A..E: an E that is
        // shifted up stays E, and its shift is still recorded, so a shift
        // down afterwards only brings it back to E.
        let mut immune = Received::new(&flame(), RANK_MAX);
        assert_eq!(immune.can_shift(1), 1);
        immune.shift_by(1);
        assert_eq!((immune.shift, immune.rate), (1, 0));
        immune.shift_by(-1);
        assert_eq!((immune.shift, immune.rate), (0, 0));
        immune.shift_by(-1);
        assert_eq!(immune.rate, 50, "E and a step down: D");
        let mut weak = Received::new(&flame(), 0);
        weak.shift_by(-1);
        assert_eq!(weak.rate, 200);
    }
}
