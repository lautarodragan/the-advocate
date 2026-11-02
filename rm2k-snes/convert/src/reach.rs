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
use serde_json::{json, Value};
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
    /// The vehicles he can ride.
    vehicles: BTreeSet<&'static str>,
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
        let mut recalled: BTreeSet<i32> = BTreeSet::new();
        let mut written: BTreeSet<i32> = BTreeSet::new();
        let mut any_written = false;
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
                (RECALL_TO_LOCATION, ..) => recalled.extend(p.iter().take(3)),
                (CONTROL_VARS, Some(VARIABLE_INDIRECT), ..) => any_written = true,
                (CONTROL_VARS, Some(mode), Some(first), Some(last), _) => {
                    let last = if mode == VARIABLE_RANGE { last } else { first };
                    written.extend(first..=last.max(first));
                }
                (INPUT_NUMBER, _, Some(v), ..) => {
                    written.insert(v);
                }
                (STORE_TERRAIN_ID | STORE_EVENT_ID, _, _, _, Some(v)) => {
                    written.insert(v);
                }
                (KEY_INPUT_PROC, Some(v), ..) => {
                    written.insert(v);
                }
                _ => {}
            }
        }
        if !recalled.is_empty() && (any_written || recalled.iter().any(|v| written.contains(v))) {
            out.any_open.get_or_insert_with(|| {
                "a RecallToLocation's variables are written by something else than MemorizeLocation"
                    .to_string()
            });
        }
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

    /// Why the hero can be on any cell one can step on, if he can.
    pub fn any_open(&self) -> Option<&str> {
        self.any_open.as_deref()
    }

    /// Map `id`'s `reach` for Wally: where the hero arrives —null if he can
    /// be anywhere—, whether also on any cell one can step on, the vehicles
    /// he can ride, and `commands`, what else runs there: its test pages.
    pub fn json_of(&self, id: i32, commands: &[Command]) -> Value {
        json!({
            "entries": match self.anywhere {
                Some(_) => Value::Null,
                None => json!(self.cells.get(&id).into_iter().flatten().map(|&(x, y)| json!([x, y])).collect::<Vec<_>>()),
            },
            "any_open": self.any_open.is_some(),
            "vehicles": self.vehicles.iter().collect::<Vec<_>>(),
            "commands": commands.iter().map(|c| json!([c.code, c.parameters])).collect::<Vec<_>>(),
        })
    }
}
