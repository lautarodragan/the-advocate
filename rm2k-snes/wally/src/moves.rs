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

/// Which of the still events that animate in RM2k animate here.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Animate {
    /// How many of the map's *looks* —see [`Moves::looks`]— animate, the
    /// first ones in their order; `None`, all of them. The conversion
    /// starts with all and gives up looks from the last only when the map
    /// does not fit: see `fewer_still_animations` in `map`.
    pub looks: Option<usize>,
    /// Whether the map has a cache of slots. There a twin's row walks like
    /// a walker's —its own poses, a key in the cache, see
    /// `cache_slots.s`—, so one that only appears and disappears with its
    /// page shares too: the page shows or hides the row and touches nothing
    /// else. Elsewhere it is a still row, which a page points at a still
    /// slot of its own.
    pub cache: bool,
}

impl Animate {
    pub const ALL: Animate = Animate { looks: None, cache: false };
}

/// What moves in a map.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Moves {
    /// The events that get a VRAM slot of their own and change pose on the
    /// fly: the ones that walk and the still ones that animate, except the
    /// ones in `follows`.
    pub movable: BTreeSet<usize>,
    /// The still ones that animate **and upload their pose**: bit 7 of
    /// their row in the console.
    pub animates_still: BTreeSet<usize>,
    /// The still ones that animate in another one's slot, with whose: they
    /// upload nothing, and are drawn with the slot it keeps up to date.
    pub follows: BTreeMap<usize, usize>,
    /// The ones that turn toward the hero, with the graphics of all their
    /// pages that turn.
    pub turning: BTreeMap<usize, BTreeSet<Key>>,
    /// The still ones that animate in RM2k and here stand on one column,
    /// because their look did not fit. Only to say it.
    pub still_not_animated: BTreeSet<usize>,
    /// How many looks the still ones that animate in RM2k come in: a look
    /// is a (CharSet, index, pose), whatever the speed. What
    /// [`Animate::looks`] counts.
    pub looks: usize,
}

/// Who moves, from the compiler's `pages`, the map's `events` and the ones
/// that are drawn, `npcs`. `also_walk` are the ones someone else sends
/// walking —a test page, which is not the map's—; `animate`, which of the
/// still ones that animate do.
pub fn moves(
    pages: &[ScannedPage],
    events: &[Event],
    npcs: &[Npc],
    chipset: &str,
    also_walk: &BTreeSet<usize>,
    animate: Animate,
) -> Moves {
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
    let animating: Vec<&Npc> = npcs
        .iter()
        .filter(|n| n.animates && !with_route.contains(&n.event))
        .collect();
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
    // A still event that animates costs a VRAM slot —a 32x32 block, sixteen
    // object tiles— because its pose changes on the fly and it cannot share
    // the slot of its (CharSet, index, pose) with the still ones that do not
    // animate. Its twelve poses go to the cartridge, once per character.
    //
    // **Unless it shares it with its twins.** The column comes from the
    // game clock and the speed —`animate_still` in the runtime—, not from
    // a counter of its own, so all the ones with the same (CharSet, index,
    // pose) and the same speed show the same pose on every frame: the first
    // one uploads it and the rest point at its slot. Six torches cost one
    // slot, or one per speed. Not one that turns toward the hero, whose
    // facing is its own; nor one whose graphic follows its page, which
    // takes it into its slot; nor one that someone else sends walking.
    //
    // And what does not fit is given up by **look** —(CharSet, index,
    // pose), all its speeds at once— and not event by event: two equal
    // fountains, one moving and the other frozen, looks worse than both
    // still, even if one flickers faster. The looks with the most events go
    // first, then the ones that take the fewest slots, then the first one
    // in the map: whoever gives them up goes from the last.
    type Look = (String, i32, i32);
    let mut looks: BTreeMap<Look, Vec<&Npc>> = BTreeMap::new();
    for n in &animating {
        looks.entry((n.charset.clone(), n.index, n.pose)).or_default().push(n);
    }
    let only_appears = |n: &Npc| n.graphics.iter().flatten().all(|g| *g == (n.charset.clone(), n.index, n.pose));
    let shares = |n: &Npc| (!n.changes || animate.cache && only_appears(n)) && !turning.contains_key(&n.event) && !also_walk.contains(&n.event);
    let slots_of = |members: &[&Npc]| -> Vec<Vec<usize>> {
        let mut by_speed: BTreeMap<i32, Vec<usize>> = BTreeMap::new();
        let mut alone = Vec::new();
        for n in members {
            if shares(n) {
                by_speed.entry(n.speed).or_default().push(n.event);
            } else {
                alone.push(vec![n.event]);
            }
        }
        by_speed.into_values().chain(alone).collect()
    };
    let mut ordered: Vec<Vec<Vec<usize>>> = looks.into_values().map(|members| slots_of(&members)).collect();
    ordered.sort_by_key(|slots| {
        let events: usize = slots.iter().map(Vec::len).sum();
        let first = slots.iter().flatten().min().copied();
        (std::cmp::Reverse(events), slots.len(), first)
    });
    let kept = animate.looks.unwrap_or(ordered.len()).min(ordered.len());
    let mut animated = BTreeSet::new();
    let mut follows = BTreeMap::new();
    let mut still_not_animated = BTreeSet::new();
    for (k, slots) in ordered.iter().enumerate() {
        for slot in slots {
            if k >= kept {
                still_not_animated.extend(slot.iter().copied());
                continue;
            }
            // The first by event index uploads.
            let leader = *slot.iter().min().unwrap();
            animated.insert(leader);
            follows.extend(slot.iter().filter(|&&e| e != leader).map(|&e| (e, leader)));
        }
    }
    let mut movable: BTreeSet<usize> = with_route.union(&animated).copied().collect();
    movable.extend(also_walk);
    Moves { movable, animates_still: animated, follows, turning, still_not_animated, looks: ordered.len() }
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
        animating(pages, events, Animate::ALL)
    }

    fn animating(pages: &[ScannedPage], events: &[Event], animate: Animate) -> Moves {
        let npcs = collect_npcs(events, "tiles", &[0; 10200]);
        moves(pages, events, &npcs, "tiles", &BTreeSet::new(), animate)
    }

    fn torch(name: &str, speed: i32) -> Page {
        Page { speed, ..page(name, 1) }
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
    fn twins_share_a_slot_one_per_speed() {
        // The Book of Three's opening hall: six equal torches at four speeds.
        let events: Vec<Event> =
            [6, 5, 6, 2, 6, 4].iter().enumerate().map(|(i, &s)| event(i as i32 + 1, vec![torch("A", s)])).collect();
        let all = who(&[], &events);
        assert_eq!(all.animates_still, [0, 1, 3, 5].into());
        assert_eq!(all.movable, [0, 1, 3, 5].into());
        assert_eq!(all.follows, [(2, 0), (4, 0)].into());
        assert!(all.still_not_animated.is_empty());
        assert_eq!(all.looks, 1);
    }

    #[test]
    fn in_a_cache_twins_that_only_appear_with_their_page_share_too() {
        // Sunset Over Imdahl's 15: eight lamps with a blank first page and
        // the lamp on a switch.
        let lamp = || vec![page("", 0), Page { conditions: vec!["switch_a"], ..torch("A", 3) }];
        let events: Vec<Event> = (0..3).map(|i| event(i + 1, lamp())).collect();
        let plain = who(&[], &events);
        assert_eq!(plain.animates_still, [0, 1, 2].into());
        assert!(plain.follows.is_empty());
        let cached = animating(&[], &events, Animate { looks: None, cache: true });
        assert_eq!(cached.animates_still, [0].into());
        assert_eq!(cached.follows, [(1, 0), (2, 0)].into());
        // Not one whose pages show two different looks.
        let mut two = events.clone();
        two[2].pages.push(Page { conditions: vec!["switch_b"], ..torch("B", 3) });
        let cached = animating(&[], &two, Animate { looks: None, cache: true });
        assert_eq!(cached.follows, [(1, 0)].into());
    }

    #[test]
    fn looks_are_given_up_whole_from_the_last() {
        // A three times, C twice at two speeds, B once.
        let events = [
            event(1, vec![torch("A", 3)]),
            event(2, vec![torch("B", 3)]),
            event(3, vec![torch("C", 3)]),
            event(4, vec![torch("A", 3)]),
            event(5, vec![torch("C", 5)]),
            event(6, vec![torch("A", 3)]),
        ];
        let some = |looks| animating(&[], &events, Animate { looks: Some(looks), cache: false });
        assert_eq!(who(&[], &events).looks, 3);
        let one = some(1);
        assert_eq!(one.animates_still, [0].into());
        assert_eq!(one.follows, [(3, 0), (5, 0)].into());
        assert_eq!(one.still_not_animated, [1, 2, 4].into());
        let two = some(2);
        assert_eq!(two.animates_still, [0, 2, 4].into());
        assert_eq!(two.still_not_animated, [1].into());
        let none = some(0);
        assert!(none.animates_still.is_empty() && none.movable.is_empty() && none.follows.is_empty());
        assert_eq!(none.still_not_animated, (0..6).collect());
    }

    #[test]
    fn one_that_walks_or_turns_does_not_share() {
        let events: Vec<Event> = (0..3).map(|i| event(i + 1, vec![torch("A", 3)])).collect();
        // One that walks is not a still one.
        let walks = ScannedPage { route_targets: vec![1], ..scanned(0, 3, true) };
        let w = who(&[walks], &events);
        assert_eq!(w.animates_still, [0].into());
        assert_eq!(w.follows, [(2, 0)].into());
        assert_eq!(w.movable, [0, 1].into());
        // One that turns toward the hero faces its own way.
        let turns = ScannedPage { turns: true, ..scanned(1, 0, true) };
        let t = who(&[turns], &events);
        assert_eq!(t.animates_still, [0, 1].into());
        assert_eq!(t.follows, [(2, 0)].into());
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
