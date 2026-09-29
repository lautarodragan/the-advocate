//! The random encounters of each map of a cartridge, as the tables the ROM
//! walks when the hero takes a step.
//!
//! The data lives in the map tree and not in the maps: each node brings its
//! list of troops, every how many steps, and —if it is an area— the
//! rectangle it covers.
//!
//! **The model is easyrpg's `Game_Player::UpdateEncounterSteps`, in
//! integers.** RM2k adds the terrain's `encounter_rate` to an accumulator
//! each step, walks a table of eight rows by `accumulated / steps`, and
//! rolls `pmod / steps`, where the row's `pmod` is a power of two. With a
//! fixed rate, the row a step is on is a threshold on the step count, and
//! `1 / steps` in 1/65536 is a number the console shifts: no division and
//! no float is left for the ROM. That the rate is fixed —the terrain
//! changes nothing— is an assumption of the engine: see [`RATE`].

use crate::asm;
use crate::fail::{Bad, Result};
use crate::game::{Game, AREA};

/// Every how many steps when the tree does not carry the node: RM2k's
/// default (liblcf's `rpg::MapInfo::encounter_steps`).
pub const DEFAULT_STEPS: i64 = 25;

/// The `encounter_rate` the accumulator goes up by. It is the terrain's,
/// and here it is fixed: on every map of the game it was measured against,
/// every terrain the hero can step on had 100, so the engine assumes it.
/// An assumption of the engine, not a fact of the format.
pub const RATE: i64 = 100;

/// The minimum `accumulated / steps` of each row of `UpdateEncounterSteps`'
/// table, past the first, which is zero.
pub const ROWS: [i64; 7] = [20, 40, 60, 100, 140, 160, 180];

/// What the formula divides by, `1 / encounter_steps`, in 1/65536: the ROM
/// shifts it by the row's `pmod` and compares it with a 16-bit random
/// number. **The truncation is part of the contract.** Zero is off, which
/// is what `encounter_steps` 0 means in RM2k.
pub fn base(steps: i64) -> i64 {
    if steps <= 0 {
        0
    } else {
        0x10000 / steps
    }
}

/// At which step each row past the first is reached, counting from zero:
/// `accumulated / steps >= row` with `accumulated = RATE * n` is
/// `n >= ceil(row * steps / RATE)`. Seven bytes per map, and no division on
/// the console.
pub fn step_thresholds(steps: i64) -> [i64; 7] {
    ROWS.map(|row| -((-row * steps).div_euclid(RATE)))
}

/// One place a map's encounters come from: the whole map, or an area.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Zone {
    /// Left, top, right, bottom, **half-open** —`Rect::IsOutOfBounds`:
    /// inside is `l <= x < r` and `t <= y < b`—.
    pub rect: [i64; 4],
    pub troops: Vec<i64>,
}

/// A map's zones: its own, covering it all, and one per area that hangs
/// from it, in the order of the tree.
///
/// The order is that of easyrpg's `GetEncountersAt`, which walks the tree
/// by index: in the game this was measured against no map has troops of its
/// own **and** areas, so putting its own first cannot change which troop
/// comes out.
pub fn zones(game: &Game, map: i64, width: i64, height: i64) -> Vec<Zone> {
    let mut zones = Vec::new();
    if let Some(node) = game.tree.get(&map).filter(|n| !n.troops.is_empty()) {
        zones.push(Zone {
            rect: [0, 0, width, height],
            troops: node.troops.clone(),
        });
    }
    for node in game.tree.values() {
        if node.kind == AREA && node.parent == map && !node.troops.is_empty() {
            zones.push(Zone {
                rect: node.rect,
                troops: node.troops.clone(),
            });
        }
    }
    zones
}

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
    /// Per map of the cartridge, in its order, its record, or `$FF` if
    /// nothing is met there.
    pub per_map: Vec<i64>,
    /// Per record: `base`, the step thresholds, and its zones.
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
            let theirs = zones(game, map.id, map.width, map.height);
            let steps = steps.unwrap_or_else(|| {
                game.tree
                    .get(&map.id)
                    .map_or(DEFAULT_STEPS, |n| n.encounter_steps)
            });
            if theirs.is_empty() || base(steps) == 0 {
                e.per_map.push(0xFF);
                continue;
            }
            e.per_map.push(e.bases.len() as i64);
            e.bases.push(base(steps));
            e.thresholds.push(step_thresholds(steps));
            e.zone_init.push(e.zones.len() as i64);
            e.zone_n.push(theirs.len() as i64);
            for zone in theirs {
                e.troops.extend(&zone.troops);
                e.zones.push(zone);
            }
        }
        // The three are indexed with one byte. With every map of the game
        // this was measured against it is 53 records, 56 zones and 322
        // troops, so the one that can go over is the last.
        if e.bases.len() > 0xFF || e.zones.len() > 0xFF || e.troops.len() > 0xFF {
            return Err(Bad::answer(format!(
                "the encounters don't fit in one-byte tables: {} record(s), {} zone(s), {} \
                 troop(s)",
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
    /// enc_map           per map, its record or $FF
    /// enc_base          per record, base()
    /// enc_threshold_n   per record, the seven thresholds and a $FF, so
    ///                   the record's index is a shift
    /// enc_zone_init     per record, its first zone
    /// enc_zone_n        per record, how many zones
    /// enc_left, enc_arr, enc_right, enc_down
    ///                   per zone, its rectangle
    /// enc_troop_init    per zone, its first troop in enc_troop
    /// enc_troop_n       per zone, how many troops
    /// enc_troop         the troops, by RM2k number
    /// ```
    pub fn tables(&self) -> String {
        let mut out = String::new();
        asm::bytes(&mut out, "enc_map", &self.per_map);
        asm::words(&mut out, "enc_base", &self.bases);
        let thresholds: Vec<i64> = self
            .thresholds
            .iter()
            .flat_map(|t| t.iter().copied().chain([0xFF]))
            .collect();
        asm::bytes(&mut out, "enc_threshold_n", &thresholds);
        asm::bytes(&mut out, "enc_zone_init", &self.zone_init);
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
        asm::bytes(&mut out, "enc_troop_init", &troop_init);
        let troop_n: Vec<i64> = self.zones.iter().map(|z| z.troops.len() as i64).collect();
        asm::bytes(&mut out, "enc_troop_n", &troop_n);
        asm::words(&mut out, "enc_troop", &self.troops);
        out
    }
}
