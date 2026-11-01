//! The random encounters of each map of a cartridge, as the tables the ROM
//! walks when the hero takes a step.
//!
//! The data lives in the map tree and not in the maps: each node brings its
//! list of troops, every how many steps, and —if it is an area— the
//! rectangle it covers.
//!
//! **The model is easyrpg's `Game_Player::UpdateEncounterSteps`, in
//! integers.** RM2k adds the `encounter_rate` of the terrain the hero steps
//! onto to an accumulator each step, walks a table of eight rows by
//! `accumulated / steps`, and rolls `pmod / steps * rate / 100`, where the
//! row's `pmod` is a power of two. On the console the row is a threshold on
//! the accumulator —`accumulated / steps >= row` is `accumulated >= row *
//! steps`, see [`rate_thresholds`]—, `1 / steps` in 1/65536 is a number the
//! ROM shifts —[`base`]— and `rate / 100` is a factor in 1/256 it multiplies
//! by —[`factor`]—: no division and no float is left for the ROM. The
//! chance is [`chance`], the same arithmetic as `encounter_step` in
//! `runtime/encounters.s`.

use crate::asm;
use crate::fail::{Bad, Result};
use crate::game::Game;
pub use rm2k_rules::tree::Zone;

/// The most `encounter_steps` the ROM can count: the accumulator and the
/// thresholds are words, and the last row's is `180 * steps`. RM2k's editor
/// goes higher; the nine games this was measured against go up to 100.
pub const STEPS_MAX: i64 = 0xFFFF / 180;

/// The minimum `accumulated / steps` of each row of `UpdateEncounterSteps`'
/// table, past the first, which is zero.
pub const ROWS: [i64; 7] = [20, 40, 60, 100, 140, 160, 180];

/// What the formula divides by, `1 / encounter_steps`, in 1/65536: the ROM
/// shifts it by the row's `pmod` and compares it with a 16-bit random
/// number. **The truncation is part of the contract.** Zero is off, which
/// is what `encounter_steps` 0 means in RM2k.
///
/// **One step saturates at `$FFFF`**: `$10000` does not fit in the word the
/// ROM keeps it in. It is still "an encounter on every step" on a terrain
/// worth 100, which is what RM2k does with 1: the first step already reaches
/// row 4 —`100 * 1 / 1` is 100—, whose `pmod` is 2, so the chance is 2, and
/// the ROM's product goes past a word, which is its "always". On a terrain
/// worth less the first steps are on rows 0 to 3, and there `$FFFF >> k` is
/// `$10000 >> k` less one part in 65536.
pub fn base(steps: i64) -> i64 {
    if steps <= 0 {
        0
    } else {
        (0x10000 / steps).min(0xFFFF)
    }
}

/// The accumulated rate at which each row past the first is reached:
/// `accumulated / steps >= row`, both integers, is `accumulated >= row *
/// steps`. Seven words per map, and no division on the console. Only for
/// `steps` up to [`STEPS_MAX`], which keeps them in a word.
pub fn rate_thresholds(steps: i64) -> [i64; 7] {
    ROWS.map(|row| row * steps)
}

/// A terrain's `encounter_rate` as the ROM multiplies by it: `rate / 100`
/// in 1/256, truncated. 100 is 256, which leaves the chance as it was
/// before terrains counted; 0 is no encounter at all. **The truncation is
/// part of the contract**, like [`base`]'s: 70 is 179, not 179.2.
pub fn factor(rate: i64) -> i64 {
    (rate.max(0) * 256 / 100).min(0xFFFF)
}

/// The chance of a step on row `row` (0 to 7) of a terrain whose factor is
/// `factor`, in 1/65536 against a sixteen-bit random number, or `None` if it
/// is a certainty —`PercentChance` with 1 or more—, in which case the ROM
/// does not roll. It is `base * factor * pmod / 256`, with the `pmod`
/// shift applied to the product and the `/ 256` last:
///
/// ```text
/// rows 0 to 3:  (base * factor) >> (4 - row) >> 8
/// rows 4 to 7:  (base * factor) << (row - 3) >> 8
/// ```
///
/// With `factor` 256 it is `base >> (4 - row)` and `base << (row - 3)`,
/// what the ROM did while it assumed every terrain was worth 100.
pub fn chance(base: i64, row: usize, factor: i64) -> Option<i64> {
    let product = base * factor;
    let shifted = if row < 4 {
        product >> (4 - row)
    } else {
        product << (row - 3)
    };
    let chance = shifted >> 8;
    (chance <= 0xFFFF).then_some(chance)
}

/// A map with no encounters, in `per_map`; the ROM's `ENC_NONE`. **A word**:
/// the indexes of the three tables are two bytes, since a game can have more
/// than 255 troops —Vampires Dawn has 779—.
pub const NONE: i64 = 0xFFFF;

/// The most records: the ROM reads a record's thresholds at `record * 16`,
/// in a 16-bit offset, and `ENC_NONE` has to stay out of reach.
const MAX_RECORDS: usize = 0x0FFF;

/// The most troops: the ROM reads troop `n` at `2 * n`, in a 16-bit offset.
const MAX_TROOPS: usize = 0x7FFF;

/// A map of the cartridge: its number and its size, in cells.
#[derive(Debug, Clone, Copy)]
pub struct Map {
    pub id: i64,
    pub width: i64,
    pub height: i64,
}

/// The encounters of a cartridge.
#[derive(Debug, Clone, Default)]
pub struct Encounters {
    /// Per map of the cartridge, in its order, its record, or [`NONE`] if
    /// nothing is met there.
    pub per_map: Vec<i64>,
    /// Per record: `base`, the rows' thresholds, and its zones.
    pub bases: Vec<i64>,
    pub thresholds: Vec<[i64; 7]>,
    pub zone_init: Vec<i64>,
    pub zone_n: Vec<i64>,
    /// Per zone: its rectangle and its troops.
    pub zones: Vec<Zone>,
    /// Every zone's troops, one after the other, by RM2k number: **the
    /// troops the cartridge has to carry** for its encounters, in the order
    /// they are met.
    pub troops: Vec<i64>,
}

impl Encounters {
    /// Those of `maps`. `steps`, if given, replaces every map's
    /// `encounter_steps`: it is for test cartridges, where an encounter
    /// every hundred steps is not what a test wants.
    pub fn of(game: &Game, maps: &[Map], steps: Option<i64>) -> Result<Encounters> {
        let mut e = Encounters::default();
        for map in maps {
            // In the game this was measured against no map has troops of
            // its own **and** areas, so the order of the zones —the map's
            // own first, see `encounter_zones`— cannot change which troop
            // comes out.
            let theirs = game
                .tree
                .encounter_zones(map.id as i32, map.width, map.height);
            let steps = steps.unwrap_or_else(|| game.tree.encounter_steps(map.id as i32) as i64);
            if theirs.is_empty() || base(steps) == 0 {
                e.per_map.push(NONE);
                continue;
            }
            if steps > STEPS_MAX {
                return Err(Bad::answer(format!(
                    "map {} has an encounter every {steps} steps, and the console counts up \
                     to {STEPS_MAX}: the accumulated rate of the last row would not fit in a word",
                    map.id
                )));
            }
            e.per_map.push(e.bases.len() as i64);
            e.bases.push(base(steps));
            e.thresholds.push(rate_thresholds(steps));
            e.zone_init.push(e.zones.len() as i64);
            e.zone_n.push(theirs.len() as i64);
            for zone in theirs {
                e.troops.extend(&zone.troops);
                e.zones.push(zone);
            }
        }
        // The indexes are words, so the cap is the tables' own offsets. What
        // stays a byte is a count *within* a map or a zone: how many zones
        // a record has and how many troops a zone has.
        if e.bases.len() > MAX_RECORDS
            || e.zones.len() > 0xFFFF
            || e.troops.len() > MAX_TROOPS
            || e.zone_n.iter().any(|&n| n > 0xFF)
            || e.zones.iter().any(|z| z.troops.len() > 0xFF)
        {
            return Err(Bad::answer(format!(
                "the encounters don't fit in the tables: {} record(s) of at most {MAX_RECORDS}, \
                 {} zone(s), {} troop(s) of at most {MAX_TROOPS}, and at most 255 zones in a \
                 record and 255 troops in a zone",
                e.bases.len(),
                e.zones.len(),
                e.troops.len()
            )));
        }
        Ok(e)
    }

    /// The tables, in whatever segment the text lands in: the ROM reads
    /// them with `lda f:table, x`, so anywhere outside bank 0 does.
    ///
    /// ```text
    /// enc_map           per map, its record or $FFFF (words)
    /// enc_base          per record, base()
    /// enc_threshold     per record, the seven thresholds and a $FFFF,
    ///                   words, so the record's index is a shift
    /// enc_zone_init     per record, its first zone (words)
    /// enc_zone_n        per record, how many zones (bytes)
    /// enc_left, enc_arr, enc_right, enc_down
    ///                   per zone, its rectangle
    /// enc_troop_init    per zone, its first troop in enc_troop (words)
    /// enc_troop_n       per zone, how many troops (bytes)
    /// enc_troop         the troops, by RM2k number
    /// ```
    pub fn tables(&self) -> String {
        let mut out = String::new();
        asm::words(&mut out, "enc_map", &self.per_map);
        asm::words(&mut out, "enc_base", &self.bases);
        let thresholds: Vec<i64> = self
            .thresholds
            .iter()
            .flat_map(|t| t.iter().copied().chain([0xFFFF]))
            .collect();
        asm::words(&mut out, "enc_threshold", &thresholds);
        asm::words(&mut out, "enc_zone_init", &self.zone_init);
        asm::bytes(&mut out, "enc_zone_n", &self.zone_n);
        for (k, label) in ["enc_left", "enc_arr", "enc_right", "enc_down"]
            .iter()
            .enumerate()
        {
            let side: Vec<i64> = self.zones.iter().map(|z| z.rect[k]).collect();
            asm::words(&mut out, label, &side);
        }
        let mut first = 0;
        let mut troop_init = Vec::new();
        for z in &self.zones {
            troop_init.push(first);
            first += z.troops.len() as i64;
        }
        asm::words(&mut out, "enc_troop_init", &troop_init);
        let troop_n: Vec<i64> = self.zones.iter().map(|z| z.troops.len() as i64).collect();
        asm::bytes(&mut out, "enc_troop_n", &troop_n);
        asm::words(&mut out, "enc_troop", &self.troops);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_step_saturates_and_still_always_fights() {
        assert_eq!(base(1), 0xFFFF);
        assert_eq!(base(2), 0x8000);
        assert_eq!(base(0), 0);
        // On a terrain worth 100 the first step is already row 4, whose
        // chance is past a word: "always".
        assert!(rate_thresholds(1)[3] <= 100);
        assert_eq!(chance(base(1), 4, factor(100)), None);
    }

    #[test]
    fn a_hundred_is_the_shift_it_always_was() {
        for steps in [1, 2, 8, 25, 85, STEPS_MAX] {
            let b = base(steps);
            for row in 0..8 {
                let shifted = if row < 4 {
                    b >> (4 - row)
                } else {
                    b << (row - 3)
                };
                let old = (shifted <= 0xFFFF).then_some(shifted);
                assert_eq!(chance(b, row, factor(100)), old, "{steps} steps, row {row}");
            }
        }
    }

    #[test]
    fn a_terrain_worth_nothing_never_fights() {
        assert_eq!(factor(0), 0);
        for row in 0..8 {
            assert_eq!(chance(base(1), row, factor(0)), Some(0));
        }
    }

    #[test]
    fn the_rows_are_the_division() {
        // `accumulated / steps >= row` against the threshold, for every
        // accumulated rate a word holds.
        for steps in [1, 8, 25, 70, 100, STEPS_MAX] {
            let t = rate_thresholds(steps);
            assert!(t.iter().all(|&x| x <= 0xFFFF));
            for acc in 0..=0xFFFF {
                for (k, &row) in ROWS.iter().enumerate() {
                    assert_eq!(acc / steps >= row, acc >= t[k], "{steps} {acc} {row}");
                }
            }
        }
    }
}
