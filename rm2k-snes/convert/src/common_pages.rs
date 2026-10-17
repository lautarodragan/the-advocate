//! The automatic common events that show pictures, copied into each map as
//! the automatic pages of an event of their own.
//!
//! RM2k runs an automatic common event on whatever map its switch is turned
//! on in, and the cartridge does too, from a body compiled once without a
//! map —`commons.rs` in the event compiler—. Without a map there are no
//! pictures: they go in the map's sprite bank, and their entries in the
//! map's table. So a menu built of `ShowPicture`s, like Frozen World's
//! `BringUpMenu` (common 15, which the B button opens on almost every map),
//! ran blind: its keys and its jumps worked and nothing was drawn.
//!
//! Each map of the cartridge that can turn on one of their switches —see
//! [`CommonPages::decide`]—, with room for one more event, gets one more
//! event, last —so no event of the game changes its index—, whose pages
//! are those common events, each on its switch: compiled with the map, their pictures are
//! the map's like any page's. On a map with the copy the shared body does
//! not start —`switch_of` in the runtime's `common_events.s` reads its
//! switch as off there—; on one without it —no room for the event— it
//! runs as before, blind. Which of the copies'
//! pictures fit is Wally's to say: they go in only if they cost the map
//! nothing —see `picture_own` in its `map::convert`—.
//!
//! The event compiler builds the same pages from the same list: see
//! `with_test_event` in it.

use crate::game::{Command, Event, Game, GameMap, Page};
use rm2k_snes_events::codes::{CALL_EVENT, CONTROL_SWITCHES, SHOW_PICTURE};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// `ControlSwitches`' operation that turns them off: the others turn them
/// on or flip them.
const SWITCH_OFF: i32 = 1;

/// Which common events are copied, and into which maps.
#[derive(Debug, Clone, Default)]
pub struct CommonPages {
    /// From the highest number to the lowest, which is the order of the
    /// pages: the active one is the last whose switch is on, and RM2k
    /// starts the lowest-numbered common event first.
    pub commons: Vec<i32>,
    pub maps: BTreeSet<i32>,
}

impl CommonPages {
    /// The automatic common events of `game` with a switch and a
    /// `ShowPicture` of their own, but `left_out` —the ones a custom menu
    /// replaces and the counters, whose bodies are not their commands—, and
    /// only those whose switch something can turn on; and the maps of
    /// `order` that can turn one of those switches on, with room for one more
    /// event than they keep, `events_max` —one less on `test_event_map`,
    /// whose first event is the test pages'—.
    ///
    /// **What can turn a switch on** is a `ControlSwitches` that turns it on
    /// or flips it —or that picks it by a variable— in a map's pages, in the
    /// common events they call, and, for every map at once, in the parallel
    /// and automatic common events and the ones they call, but those copied.
    /// Not following the copies is what leaves out a menu that only opens
    /// itself again: A Blurred Line has two automatic ones with pictures
    /// that nothing starts, and copying them into its three hundred maps did
    /// not fit the cartridge.
    pub fn decide(
        game: &Game,
        left_out: &BTreeSet<i32>,
        order: &[i32],
        test_event_map: Option<i32>,
        events_max: usize,
    ) -> crate::fail::Result<CommonPages> {
        let candidates: BTreeMap<i32, i32> = game
            .db
            .autostart_commons
            .iter()
            .map(|(&n, &s)| (n, s))
            .filter(|(n, _)| !left_out.contains(n))
            .filter(|(n, _)| game.db.common_events.get(n).is_some_and(|c| c.iter().any(|c| c.code == SHOW_PICTURE)))
            .collect();
        if candidates.is_empty() {
            return Ok(CommonPages::default());
        }
        let switches: BTreeSet<i32> = candidates.values().copied().collect();
        // The common events that run on any map, and what they call.
        let global: Vec<i32> = game
            .db
            .autostart_commons
            .keys()
            .chain(game.db.parallel_commons.iter())
            .copied()
            .filter(|n| !candidates.contains_key(n))
            .collect();
        let turned = |roots: &mut dyn Iterator<Item = &Command>| -> BTreeSet<i32> {
            let mut on = BTreeSet::new();
            let mut seen = BTreeSet::new();
            let mut stack: Vec<&Command> = roots.collect();
            while let Some(c) = stack.pop() {
                let p = &c.parameters;
                if c.code == CONTROL_SWITCHES && p.len() >= 4 && p[3] != SWITCH_OFF {
                    match p[0] {
                        0 => on.extend(switches.iter().filter(|&&s| s == p[1])),
                        1 => on.extend(switches.iter().filter(|&&s| p[1] <= s && s <= p[2])),
                        _ => on.extend(switches.iter()),
                    }
                }
                if c.code == CALL_EVENT && p.len() >= 2 && p[0] == 0 && !candidates.contains_key(&p[1]) && seen.insert(p[1]) {
                    stack.extend(game.db.common_events.get(&p[1]).into_iter().flatten());
                }
            }
            on
        };
        let everywhere = turned(&mut global.iter().flat_map(|n| game.db.common_events.get(n).into_iter().flatten()));
        let mut on_some = everywhere.clone();
        let mut maps = BTreeSet::new();
        for &id in order {
            let map = game.map(id)?;
            let here = turned(&mut map.all_commands());
            if !here.is_empty() || !everywhere.is_empty() {
                on_some.extend(here);
                let room = events_max - usize::from(Some(id) == test_event_map);
                if map.events.len() < room {
                    maps.insert(id);
                }
            }
        }
        let mut commons: Vec<i32> =
            candidates.iter().filter(|(_, s)| on_some.contains(s)).map(|(&n, _)| n).collect();
        commons.sort_by(|a, b| b.cmp(a));
        if commons.is_empty() {
            maps.clear();
        }
        Ok(CommonPages { commons, maps })
    }

    /// What the event compiler's requests carry: nothing in a cartridge
    /// without copies.
    pub fn to_json(&self) -> Option<Value> {
        (!self.maps.is_empty()).then(|| json!({"commons": self.commons, "maps": self.maps}))
    }

    /// The event with the copies that `map` gets, if it gets one: with the
    /// id after its highest, as the event compiler gives it —see
    /// `with_test_event` there—, to go last.
    pub fn event(&self, game: &Game, map: &GameMap) -> Option<Event> {
        if !self.maps.contains(&map.id) {
            return None;
        }
        let id = map.events.iter().map(|e| e.id).max().unwrap_or(0) + 1;
        let pages = self
            .commons
            .iter()
            .enumerate()
            .map(|(k, n)| Page {
                id: k as i32 + 1,
                character_name: String::new(),
                dump_name: String::new(),
                character_index: 0,
                direction: 2,
                pattern: 1,
                layer: 0,
                animation_type: 0,
                commands: game.db.common_events[n].clone(),
            })
            .collect();
        Some(Event { id, x: 0, y: 0, pages })
    }
}
