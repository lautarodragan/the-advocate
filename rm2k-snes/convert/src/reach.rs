//! Where the hero can arrive on each map from outside its pages: what Wally
//! needs, besides the map, to know which cells no character can ever cover
//! —see `rm2k_rules::reach` and `layers::below` in Wally—.
//!
//! The hero gets onto a map by the game's start, a `Teleport` of any page or
//! common event of the cartridge or of its tests, a teleport skill's or an
//! escape's destination —`TeleportTargets`, `EscapeTarget`—, or riding a
//! vehicle. What cannot be told puts him anywhere, on every map: an
//! airship, which flies over everything, or a `SetVehicleLocation` by
//! variables.
//!
//! And a `RecallToLocation`: with only `MemorizeLocation` writing its
//! variables, a recalled place is one where the hero already stood. When
//! something else writes them —ABL recalls the hero's own cell five rows
//! up, Zounds' map 2 takes him to a map typed in—, he can be on any cell of
//! any map one can step on: that a game recalls a place it means for the
//! hero to stand on is taken on trust —see `Outside::any_open` in
//! rm2k-rules—. Without the trust no game here would keep anything below:
//! every one but two recalls a place it works out.
//!
//! A boat or a ship carries the hero over the water its terrain lets it
//! through, which Wally adds to where he can walk: here only whether there
//! is one.

use crate::fail::Result;
use crate::game::{Command, Game, GameMap};
use rm2k_snes_events::codes::*;
use std::collections::{BTreeMap, BTreeSet};

/// The commands this reads that `codes` does not name.
const TELEPORT_TARGETS: i32 = 11810;
const ESCAPE_TARGET: i32 = 11830;
const SET_VEHICLE_LOCATION: i32 = 10850;
const STORE_EVENT_ID: i32 = 10920;
/// `TeleportTargets`' first parameter when it adds one.
const TARGET_ADD: i32 = 0;
/// `ControlVariables`' first parameter when the variable is another
/// variable's value: any of them.
const VARIABLE_INDIRECT: i32 = 2;
const VARIABLE_RANGE: i32 = 1;
/// `ControlVariables`' operation that sets, and its operand that is a
/// number.
const VARIABLE_SET: i32 = 0;
const OPERAND_NUMBER: i32 = 0;
/// `ControlSwitches`' first parameter —one switch, a range— and its
/// operations that turn a switch off or may.
const SWITCH_SINGLE: i32 = 0;
const SWITCH_RANGE: i32 = 1;
const SWITCH_OFF: i32 = 1;
const SWITCH_TOGGLE: i32 = 2;
/// The vehicles, as `SetVehicleLocation` numbers them.
const VEHICLES: [&str; 3] = ["boat", "ship", "airship"];

/// What the cartridge as a whole says of where the hero can arrive.
#[derive(Debug, Default)]
pub struct Arrivals {
    /// By map, the cells.
    cells: BTreeMap<i32, BTreeSet<(i32, i32)>>,
    /// Why he can be anywhere on every map, if he can.
    anywhere: Option<String>,
    /// Why he can be on any cell one can step on, if he can.
    any_open: Option<String>,
    /// On which maps, if only on some: the recalls whose map is a variable
    /// only ever set to a number go only to those maps.
    any_open_on: Option<BTreeSet<i32>>,
    /// The vehicles he can ride.
    vehicles: BTreeSet<&'static str>,
    /// The switches a command of the game can turn off, as inclusive
    /// ranges; `None` if any can be, one picked by a variable.
    off: Option<Vec<(i32, i32)>>,
}

impl Arrivals {
    /// Walks every command of `maps` —the cartridge's—, of the common
    /// events and of the test `cases`.
    pub fn gather(
        game: &Game,
        maps: &[&GameMap],
        cases: &[(i32, Vec<Command>)],
    ) -> Result<Arrivals> {
        let mut out = Arrivals::default();
        let tree = ditto::dump::Dump::open(&game.dump)?.tree()?;
        let s = &tree.start;
        out.add(s.party_map_id, s.party_x, s.party_y);
        for (k, (map, x, y)) in [
            (s.boat_map_id, s.boat_x, s.boat_y),
            (s.ship_map_id, s.ship_x, s.ship_y),
            (s.airship_map_id, s.airship_x, s.airship_y),
        ]
        .into_iter()
        .enumerate()
        {
            if map > 0 {
                out.vehicle(k);
                out.add(map, x, y);
            }
        }
        let commands = maps
            .iter()
            .flat_map(|m| m.all_commands())
            .chain(game.db.common_events.values().flatten())
            .chain(cases.iter().flat_map(|(_, c)| c));
        let mut recalls: BTreeSet<(i32, i32, i32)> = BTreeSet::new();
        let mut written: BTreeSet<i32> = BTreeSet::new();
        // The numbers each variable is set to, `None` if something else
        // writes it too.
        let mut numbers: BTreeMap<i32, Option<BTreeSet<i32>>> = BTreeMap::new();
        let mut any_written = false;
        let mut off: Option<Vec<(i32, i32)>> = Some(Vec::new());
        for c in commands {
            let p = &c.parameters;
            let get = |k: usize| p.get(k).copied();
            match (c.code, get(0), get(1), get(2), get(3)) {
                (TELEPORT, Some(m), Some(x), Some(y), _) => out.add(m, x, y),
                (TELEPORT_TARGETS, Some(TARGET_ADD), Some(m), Some(x), Some(y)) => out.add(m, x, y),
                (ESCAPE_TARGET, Some(m), Some(x), Some(y), _) => out.add(m, x, y),
                (SET_VEHICLE_LOCATION, Some(v), Some(0), Some(m), Some(x)) => {
                    out.vehicle(v as usize);
                    out.add(m, x, get(4).unwrap_or(0));
                }
                (SET_VEHICLE_LOCATION, Some(v), ..) => {
                    out.vehicle(v as usize);
                    out.anywhere.get_or_insert_with(|| {
                        "a vehicle is put somewhere by variables".to_string()
                    });
                }
                (RECALL_TO_LOCATION, Some(m), Some(x), Some(y), _) => {
                    recalls.insert((m, x, y));
                }
                (CONTROL_SWITCHES, Some(mode), Some(first), Some(last), Some(op))
                    if op == SWITCH_OFF || op == SWITCH_TOGGLE =>
                {
                    match (mode, off.as_mut()) {
                        (SWITCH_SINGLE, Some(o)) => o.push((first, first)),
                        (SWITCH_RANGE, Some(o)) => o.push((first, last.max(first))),
                        _ => off = None,
                    }
                }
                (CONTROL_VARS, Some(VARIABLE_INDIRECT), ..) => any_written = true,
                (CONTROL_VARS, Some(mode), Some(first), Some(last), _) => {
                    let last = if mode == VARIABLE_RANGE { last } else { first };
                    written.extend(first..=last.max(first));
                    // `Set` to a number: operation 0, operand 0, the number.
                    let number = match (get(3), get(4), get(5)) {
                        (Some(VARIABLE_SET), Some(OPERAND_NUMBER), Some(n)) => Some(n),
                        _ => None,
                    };
                    for v in first..=last.max(first) {
                        let entry = numbers.entry(v).or_insert_with(|| Some(BTreeSet::new()));
                        match (entry.as_mut(), number) {
                            (Some(set), Some(n)) => {
                                set.insert(n);
                            }
                            _ => *entry = None,
                        }
                    }
                }
                (INPUT_NUMBER, _, Some(v), ..) => {
                    written.insert(v);
                    numbers.insert(v, None);
                }
                (STORE_TERRAIN_ID | STORE_EVENT_ID, _, _, _, Some(v)) => {
                    written.insert(v);
                    numbers.insert(v, None);
                }
                (KEY_INPUT_PROC, Some(v), ..) => {
                    written.insert(v);
                    numbers.insert(v, None);
                }
                (MEMORIZE_LOCATION, ..) => {
                    for &v in p.iter().take(3) {
                        numbers.insert(v, None);
                    }
                }
                _ => {}
            }
        }
        // A recall whose variables something else than `MemorizeLocation`
        // writes can put him on any cell one can step on: of any map, or,
        // if its map's variable is only ever set to numbers, of those.
        let mut on: Option<BTreeSet<i32>> = Some(BTreeSet::new());
        for &(m, x, y) in &recalls {
            if !any_written && ![m, x, y].iter().any(|v| written.contains(v)) {
                continue;
            }
            out.any_open.get_or_insert_with(|| {
                "a RecallToLocation's variables are written by something else than MemorizeLocation"
                    .to_string()
            });
            match (on.as_mut(), numbers.get(&m)) {
                (Some(maps), Some(Some(set))) if !any_written => maps.extend(set),
                _ => on = None,
            }
        }
        if out.any_open.is_some() {
            out.any_open_on = on;
        }
        out.off = off;
        if out.vehicles.contains("airship") {
            out.anywhere
                .get_or_insert_with(|| "an airship flies over everything".to_string());
        }
        Ok(out)
    }

    fn add(&mut self, map: i32, x: i32, y: i32) {
        self.cells.entry(map).or_default().insert((x, y));
    }

    fn vehicle(&mut self, k: usize) {
        if let Some(v) = VEHICLES.get(k) {
            self.vehicles.insert(v);
        } else {
            self.vehicles.insert("airship");
        }
    }

    /// Why the hero can be anywhere on every map, if he can.
    pub fn anywhere(&self) -> Option<&str> {
        self.anywhere.as_deref()
    }

    /// Why the hero can be on any cell one can step on, if he can, and on
    /// which maps if not on all.
    pub fn any_open(&self) -> Option<(&str, Option<&BTreeSet<i32>>)> {
        self.any_open
            .as_deref()
            .map(|why| (why, self.any_open_on.as_ref()))
    }

    /// Map `id`'s `reach` for Wally: where the hero arrives —none if he
    /// can be anywhere—, whether also on any cell one can step on, the
    /// vehicles he can ride, `commands`, what else runs there: its test
    /// pages, as `(code, parameters)`; and the switches the game can turn
    /// off, which say whether a scene runs once.
    pub fn reach(&self, id: i32, commands: &[(i32, Vec<i32>)]) -> wally::request::Reach {
        wally::request::Reach {
            entries: match self.anywhere {
                Some(_) => None,
                None => Some(self.cells.get(&id).into_iter().flatten().copied().collect()),
            },
            any_open: self.any_open.is_some()
                && self
                    .any_open_on
                    .as_ref()
                    .is_none_or(|maps| maps.contains(&id)),
            vehicles: self.vehicles.iter().map(|v| v.to_string()).collect(),
            commands: commands.to_vec(),
            off: self.off.clone(),
        }
    }
}
