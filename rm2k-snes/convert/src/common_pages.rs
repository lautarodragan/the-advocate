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
//! Each map of the cartridge with room for one more event gets an event 0
//! —the place the test pages' event takes— whose pages are those common
//! events, each on its switch: compiled with the map, their pictures are
//! the map's like any page's. The map's events start before the common
//! events, so on a map with the copy the shared body never runs; on one
//! without it —no room for the event, or the map the test pages boot in,
//! whose event 0 is theirs— it runs as before, blind. Which of the copies'
//! pictures fit is Wally's to say: they go in only if they cost the map
//! nothing —see `picture_own` in its `map::convert`—.
//!
//! The event compiler builds the same pages from the same list: see
//! `with_test_event` in it.

use crate::game::{Event, Game, Page};
use rm2k_snes_events::codes::SHOW_PICTURE;
use serde_json::{json, Value};
use std::collections::BTreeSet;

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
    /// replaces and the counters, whose bodies are not their commands—; and
    /// the maps of `order` that have room for one more event than they keep,
    /// `events_max`, but `test_event_map`.
    pub fn decide(
        game: &Game,
        left_out: &BTreeSet<i32>,
        order: &[i32],
        test_event_map: Option<i32>,
        events_max: usize,
    ) -> crate::fail::Result<CommonPages> {
        let mut commons: Vec<i32> = game
            .db
            .autostart_commons
            .keys()
            .copied()
            .filter(|n| !left_out.contains(n))
            .filter(|n| game.db.common_events.get(n).is_some_and(|c| c.iter().any(|c| c.code == SHOW_PICTURE)))
            .collect();
        commons.sort_by(|a, b| b.cmp(a));
        let mut maps = BTreeSet::new();
        if !commons.is_empty() {
            for &id in order {
                if Some(id) != test_event_map && game.map(id)?.events.len() < events_max {
                    maps.insert(id);
                }
            }
        }
        Ok(CommonPages { commons, maps })
    }

    /// What the event compiler's requests carry: nothing in a cartridge
    /// without copies.
    pub fn to_json(&self) -> Option<Value> {
        (!self.maps.is_empty()).then(|| json!({"commons": self.commons, "maps": self.maps}))
    }

    /// The event 0 of map `id`, if it gets one.
    pub fn event(&self, game: &Game, id: i32) -> Option<Event> {
        if !self.maps.contains(&id) {
            return None;
        }
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
        Some(Event { id: 0, x: 0, y: 0, pages })
    }
}
