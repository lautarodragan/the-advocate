//! Who moves in a map: the events that walk, the still ones that animate,
//! and the ones that turn toward the hero.
//!
//! It is needed before building the sprite bank: the ones that move get
//! **the twelve poses** of the walking cycle, and the others the single one
//! they declare. Giving them to anyone that shows up in a MoveEvent would be
//! simpler and does not fit: there are maps with seven, and that is 1232
//! sprite tiles.
//!
//! What walks is what the compiled bytecode sends walking, and that is the
//! event compiler's to know: its scan answers, for each page of the map,
//! whether it compiled, the events its code sends a route to, whether it
//! walks a route of its own and whether it turns. Those records come in the
//! request as they came out of the compiler; what they draw is read here,
//! from the map.

use crate::events::{page_graphic, Event};
use crate::sprites::character::Key;
use crate::sprites::npc::Npc;
use std::collections::{BTreeMap, BTreeSet};

/// A page as the event compiler's scan answered it, with what this stage
/// reads of it.
#[derive(Clone, Debug, Default)]
pub struct ScannedPage {
    /// The event's index in the map's table —not its RM2k id— and the
    /// page's among the event's.
    pub event: usize,
    pub page: usize,
    pub trigger: i32,
    /// Whether it compiled.
    pub compiles: bool,
    /// The events its code sends a route to, by index.
    pub route_targets: Vec<usize>,
    /// Whether it walks a route of its own.
    pub own_route: bool,
    /// Whether it turns toward the hero when triggered.
    pub turns: bool,
}

/// RM2k's triggers that turn an event toward the hero: the action key, the
/// hero's touch and the event's —`ScheduleForegroundExecution` with
/// `face_player` on all three—.
const TRIGGER_ACTION: i32 = 0;
const TRIGGER_TOUCH_HERO: i32 = 1;
const TRIGGER_COLLISION: i32 = 2;

/// How many still events with continuous animation a map animates. See the
/// reason —and the measured number— inside [`moves`].
///
/// Measured against the game the port was built for: an assumption of the
/// engine, not a piece of the game's data.
pub const ANIMATES_STILL_MAX: usize = 4;

/// What moves in a map.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Moves {
    /// The events that get the twelve poses: the ones that walk and the
    /// still ones that animate.
    pub movable: BTreeSet<usize>,
    /// Of those, the still ones that animate.
    pub animates_still: BTreeSet<usize>,
    /// The ones that turn toward the hero, with the graphics of all their
    /// pages that turn.
    pub turning: BTreeMap<usize, BTreeSet<Key>>,
    /// The still ones that animate in RM2k and here stand on one column:
    /// all of them, on a map with more than `ANIMATES_STILL_MAX`. Only to
    /// say it.
    pub still_not_animated: BTreeSet<usize>,
}

/// Who moves, from the compiler's `pages`, the map's `events` and the ones
/// that are drawn, `npcs`. `also_walk` are the ones someone else sends
/// walking —a test page, which is not the map's—.
pub fn moves(pages: &[ScannedPage], events: &[Event], npcs: &[Npc], chipset: &str, also_walk: &BTreeSet<usize>) -> Moves {
    let drawn: BTreeSet<usize> = npcs.iter().map(|n| n.event).collect();
    // The ones some compiled page sends a route to, and the ones that walk
    // on their own with some page's own route, which need the twelve poses
    // just the same.
    let with_route: BTreeSet<usize> = pages
        .iter()
        .filter(|p| p.compiles)
        .flat_map(|p| p.route_targets.iter().copied())
        .chain(pages.iter().filter(|p| p.own_route).map(|p| p.event))
        .filter(|e| drawn.contains(e))
        .collect();
    // And the still ones with continuous animation —a save point—, which
    // do not walk but **change column all the same**. Without the twelve
    // poses their VRAM slot would carry a single one and there would be
    // nothing to animate them with: the still ones share a slot by
    // (CharSet, index, pose) and do not have one of their own.
    let mut animated: BTreeSet<usize> = npcs
        .iter()
        .filter(|n| n.animates && !with_route.contains(&n.event))
        .map(|n| n.event)
        .collect();
    // And the cap: a still event that animates **costs a whole VRAM slot**
    // —twelve tiles— because it stops sharing that of its (CharSet, index,
    // pose) and gets the twelve poses of its own, like the walking ones. A
    // map with thirty asks for 572 sprite tiles and 384 fit.
    //
    // So a map with more than `ANIMATES_STILL_MAX` animates **none**, and
    // not some yes and some no: two equal fountains, one moving and the
    // other frozen, looks worse than both still. Measured over the 328 maps
    // of the game this was built for: 312 have four or fewer.
    let mut still_not_animated = BTreeSet::new();
    if animated.len() > ANIMATES_STILL_MAX {
        still_not_animated = std::mem::take(&mut animated);
    }
    // And the ones that turn toward the hero when it talks to them: the
    // events with some action or touch page that compiled and turns, with
    // the graphics of **all** their pages that turn. The twelve poses of
    // each go to the cartridge, which is where the console takes the one
    // facing the hero from.
    let mut turning: BTreeMap<usize, BTreeSet<Key>> = BTreeMap::new();
    for p in pages {
        if p.compiles && p.turns && matches!(p.trigger, TRIGGER_ACTION | TRIGGER_TOUCH_HERO | TRIGGER_COLLISION) {
            turning.entry(p.event).or_default();
        }
    }
    for p in pages.iter().filter(|p| p.turns) {
        let Some(graphics) = turning.get_mut(&p.event) else {
            continue;
        };
        let graphic = events.get(p.event).and_then(|e| e.pages.get(p.page)).and_then(|page| page_graphic(page, chipset));
        if let Some((charset, index, _)) = graphic {
            graphics.insert((charset, index));
        }
    }
    let mut movable: BTreeSet<usize> = with_route.union(&animated).copied().collect();
    movable.extend(also_walk);
    Moves { movable, animates_still: animated, turning, still_not_animated }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::{collect_npcs, Page};

    fn page(name: &str, animation: i32) -> Page {
        Page {
            name: name.into(),
            index: 0,
            pose: 7,
            layer: 1,
            speed: 3,
            animation,
            move_type: 0,
            own_route: false,
            conditions: Vec::new(),
            commands: Vec::new(),
        }
    }

    fn event(id: i32, pages: Vec<Page>) -> Event {
        Event { id, x: 0, y: 0, pages }
    }

    fn scanned(event: usize, trigger: i32, compiles: bool) -> ScannedPage {
        ScannedPage { event, page: 0, trigger, compiles, ..Default::default() }
    }

    fn who(pages: &[ScannedPage], events: &[Event]) -> Moves {
        let npcs = collect_npcs(events, "tiles", &[0; 10200]);
        moves(pages, events, &npcs, "tiles", &BTreeSet::new())
    }

    #[test]
    fn a_route_moves_only_what_is_drawn_and_only_from_code_that_compiled() {
        let events = [event(1, vec![page("A", 0)]), event(2, vec![page("", 0)]), event(3, vec![page("C", 0)])];
        let routes = ScannedPage { route_targets: vec![1, 2], ..scanned(0, 3, true) };
        let dead = ScannedPage { route_targets: vec![0], ..scanned(0, 3, false) };
        // Event 1 draws nothing, and the page that routes 0 did not compile.
        assert_eq!(who(&[routes, dead], &events).movable, [2].into());
        // Its own route walks it whether or not its code compiled.
        let own = ScannedPage { own_route: true, ..scanned(0, 3, false) };
        assert_eq!(who(&[own], &events).movable, [0].into());
    }

    #[test]
    fn up_to_four_still_ones_animate_and_one_more_stops_them_all() {
        let mut events: Vec<Event> = (0..4).map(|i| event(i + 1, vec![page("A", 1)])).collect();
        let four = who(&[], &events);
        assert_eq!(four.animates_still, (0..4).collect());
        assert_eq!(four.movable, (0..4).collect());
        events.push(event(5, vec![page("A", 3)]));
        let five = who(&[], &events);
        assert!(five.animates_still.is_empty() && five.movable.is_empty());
        // One that walks is not a still one, and does not count.
        let walks = ScannedPage { route_targets: vec![4], ..scanned(0, 3, true) };
        let four = who(&[walks], &events);
        assert_eq!(four.animates_still, (0..4).collect());
        assert_eq!(four.movable, (0..5).collect());
    }

    #[test]
    fn who_turns_is_an_action_or_touch_page_that_compiled_with_all_its_turning_graphics() {
        let events = [
            event(1, vec![page("A", 0), page("B", 0), page("C", 0)]),
            event(2, vec![page("D", 0)]),
            event(3, vec![page("E", 0)]),
        ];
        let turns = |event, page, trigger, compiles| ScannedPage { turns: true, page, ..scanned(event, trigger, compiles) };
        let pages = [
            turns(0, 0, 0, true),
            turns(0, 1, 3, false),
            ScannedPage { page: 2, ..scanned(0, 0, true) },
            turns(1, 0, 3, true),
            turns(2, 0, 1, false),
        ];
        let expected: BTreeMap<usize, BTreeSet<Key>> =
            [(0, [("A".to_string(), 0), ("B".to_string(), 0)].into())].into();
        assert_eq!(who(&pages, &events).turning, expected);
    }
}
