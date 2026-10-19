//! The route graphics that are numbered somewhere else than in the table of
//! the map whose page gives them.
//!
//! **After a jump to another map.** A foreground page that `Teleport`s keeps
//! running on the other side —see [`MapEvents::after_jump`]—, and a route's
//! command 34 there runs on the destination's table of graphics, which the
//! console loaded with its map: the index it carries has to be the
//! destination's. Until 2026-10-19 the compiler numbered it in the table of
//! the map the page is on, and The Frozen World's battle showed it: the
//! command grid, map 3, jumps to the battle, map 1, and gives the hero the
//! plate picked, `Plates1 6`, index 1 of map 3's table; index 1 of map 1's
//! is Borto. So before compiling any map, every page of the cartridge is
//! walked as the compiler will walk it, and each graphic it gives after a
//! jump is noted for the destination. A common event's body is walked too,
//! as the shared body the cartridge compiles —a call from a page is an
//! `OP_CALL` to it, not its commands pasted—: a body that jumps runs there.
//! They are the battle's turns in The Frozen World, common events 3, 4 and
//! 8, which jump to the command grid and give the hero the graphic of
//! whoever picks next.
//!
//! **In a common event's body, before any jump.** The body is compiled once
//! and runs on whatever map calls it, so its graphic is numbered at the
//! same index in the table of **every** map that may run it: the bodies'
//! graphics go right after the associations, in the maps whose pages call
//! one of those bodies —or all of them, if an automatic common event or a
//! test page reaches one—. It is the associations' way, see [`Graphics`].
//! The Frozen World's item screen, map 14, calls common event 18 to give the
//! hero the graphic of whoever uses the item.
//!
//! Each map's table starts so: the associations, the bodies' graphics if
//! the map carries them, and the graphics the pages give after jumping
//! there. Their indices are known before any page is compiled, and the
//! sprite bank of the map gets them like any other of its graphics: the
//! converter asks Wally for the table.
//!
//! What is left loses the change with a warning instead of drawing another
//! graphic: a jump whose destination is not a constant —a
//! `RecallToLocation`—. A **parallel** page or common event is not walked:
//! it does not keep running there, it goes on in the same frame on its own
//! map —see `op_teleport` in the runtime—, and its graphics are its own
//! map's, or dropped in a parallel common event, as before.
//!
//! [`MapEvents::after_jump`]: crate::pages::MapEvents::after_jump

use crate::codes::{CALL_EVENT, MOVE_EVENT, ROUTE_CHANGE_GRAPHIC, TELEPORT, TRIGGER_PARALLEL};
use crate::compile::{CALL_MAX, ROUTE_HERO};
use crate::game::{Command, CommonEvent, Map};
use crate::registry::Graphics;
use crate::route;
use std::collections::{BTreeMap, BTreeSet};

type Pair = (String, i32);

/// Where the commands being walked run.
#[derive(Clone, Copy)]
enum Place<'m> {
    /// A map's page.
    Page(&'m Map),
    /// A common event's body, by number.
    Body(i32),
}

/// Each map's table of route graphics as it starts: see the module.
#[derive(Debug, Clone, Default)]
pub struct Landings {
    associations: Vec<Pair>,
    /// The graphics the common events' bodies give before any jump, in the
    /// order of their numbers.
    bodies: Vec<Pair>,
    /// The maps that carry `bodies`, and whether all of them do.
    carriers: BTreeSet<i32>,
    everywhere: bool,
    /// What the pages give after jumping to each map.
    landed: BTreeMap<i32, Vec<Pair>>,
    /// Those of them a route gives an event and not the hero: see
    /// [`Graphics::on_events`].
    on_events: BTreeMap<i32, BTreeSet<Pair>>,
}

/// What a walk gathers besides the graphics: which common events run where.
#[derive(Default)]
struct Calls {
    /// By map: the common events called there —from its pages, or after a
    /// jump to it—.
    on_map: BTreeMap<i32, BTreeSet<i32>>,
    /// By common event: the ones its body calls before jumping.
    by_body: BTreeMap<i32, BTreeSet<i32>>,
    /// The graphics each body gives before jumping.
    graphics: BTreeMap<i32, Vec<Pair>>,
}

impl Landings {
    /// Walks the pages of `maps` —the cartridge's— and the `commons`;
    /// `in_cartridge` says whether a map id is one of them, which is when a
    /// `Teleport` keeps the page running there and not as a message (see
    /// `TELEPORT` in compile.rs). `everywhere` are the common events that
    /// run on any map: the automatic ones and the ones the test pages call.
    pub fn gather(
        maps: &[Map],
        commons: &BTreeMap<i32, CommonEvent>,
        associations: &[Pair],
        everywhere: &BTreeSet<i32>,
        in_cartridge: impl Fn(i64) -> bool,
    ) -> Landings {
        let mut landings = Landings {
            associations: associations.to_vec(),
            ..Default::default()
        };
        let mut calls = Calls::default();
        for map in maps {
            for event in &map.events {
                for page in &event.pages {
                    if page.trigger != TRIGGER_PARALLEL {
                        landings.walk(
                            Place::Page(map),
                            &page.commands,
                            None,
                            &in_cartridge,
                            &mut calls,
                            0,
                        );
                    }
                }
            }
        }
        for (&n, common) in commons {
            if common.trigger != TRIGGER_PARALLEL {
                landings.walk(
                    Place::Body(n),
                    &common.commands,
                    None,
                    &in_cartridge,
                    &mut calls,
                    0,
                );
            }
        }
        for graphics in calls.graphics.values() {
            for g in graphics {
                if !landings.associations.contains(g) && !landings.bodies.contains(g) {
                    landings.bodies.push(g.clone());
                }
            }
        }
        // Who may run a body that gives a graphic: through the calls of the
        // bodies, down to the ones that give one.
        let giving: BTreeSet<i32> = calls.graphics.keys().copied().collect();
        let reaches = |starts: &BTreeSet<i32>| {
            let mut seen = BTreeSet::new();
            let mut pending: Vec<i32> = starts.iter().copied().collect();
            while let Some(n) = pending.pop() {
                if seen.insert(n) {
                    pending.extend(calls.by_body.get(&n).into_iter().flatten().copied());
                }
            }
            !seen.is_disjoint(&giving)
        };
        landings.everywhere = reaches(everywhere);
        landings.carriers = calls
            .on_map
            .iter()
            .filter(|(_, called)| reaches(called))
            .map(|(&map, _)| map)
            .collect();
        landings
    }

    /// Commands that run at `place`, `there` the map they already jumped
    /// to. Linear, as `compile_page` follows the jump: a `Teleport` inside a
    /// branch counts for every command after it. A page of the map called
    /// after the jump is pasted there —see `compile_call`—, so it is walked
    /// with the jump; one called before is a call, compiled as itself.
    fn walk(
        &mut self,
        place: Place,
        commands: &[Command],
        mut there: Option<i32>,
        in_cartridge: &impl Fn(i64) -> bool,
        calls: &mut Calls,
        depth: usize,
    ) {
        let map = match place {
            Place::Page(map) => Some(map),
            Place::Body(_) => None,
        };
        for cmd in commands {
            let p = &cmd.parameters;
            if cmd.code == TELEPORT {
                if let Some(to) = cmd.p(0) {
                    if in_cartridge(to) && Some(to) != map.map(|m| m.id as i64) {
                        there = Some(to as i32);
                    }
                }
            }
            if cmd.code == CALL_EVENT && p.len() >= 2 && p[0] == 0 {
                match (there, place) {
                    (Some(to), _) => calls.on_map.entry(to).or_default().insert(p[1]),
                    (None, Place::Page(map)) => {
                        calls.on_map.entry(map.id).or_default().insert(p[1])
                    }
                    (None, Place::Body(n)) => calls.by_body.entry(n).or_default().insert(p[1]),
                };
                continue;
            }
            if cmd.code == CALL_EVENT && p.len() >= 3 && p[0] == 1 && depth < CALL_MAX {
                let Some(to) = there else { continue };
                let called = map
                    .and_then(|m| m.events.iter().find(|e| e.id == p[1]))
                    .and_then(|e| e.pages.get((p[2] as usize).wrapping_sub(1)));
                if let Some(page) = called {
                    self.walk(
                        place,
                        &page.commands,
                        Some(to),
                        in_cartridge,
                        calls,
                        depth + 1,
                    );
                }
                continue;
            }
            if cmd.code != MOVE_EVENT || p.len() < 4 {
                continue;
            }
            let on_event = p[0] as i64 != ROUTE_HERO;
            let Ok(route) = route::decode(&p[4..]) else {
                continue;
            };
            for (code, extras) in route {
                if code != ROUTE_CHANGE_GRAPHIC || extras.len() < 2 {
                    continue;
                }
                let graphic = (extras[0].text().to_string(), extras[1].int() as i32);
                match (there, place) {
                    (Some(to), _) => self.note(to, graphic, on_event),
                    // A page's own, numbered in its map as always.
                    (None, Place::Page(_)) => {}
                    // A body's on the hero: numbered in every map that runs
                    // it. On an event, a body has none to give it to.
                    (None, Place::Body(n)) if !on_event => {
                        let given = calls.graphics.entry(n).or_default();
                        if !given.contains(&graphic) {
                            given.push(graphic);
                        }
                    }
                    (None, Place::Body(_)) => {}
                }
            }
        }
    }

    fn note(&mut self, map: i32, graphic: Pair, on_event: bool) {
        let landed = self.landed.entry(map).or_default();
        if !landed.contains(&graphic) {
            landed.push(graphic.clone());
        }
        if on_event {
            self.on_events.entry(map).or_default().insert(graphic);
        }
    }

    /// Whether the map's table carries the bodies' graphics.
    fn carries(&self, map: i32) -> bool {
        self.everywhere || self.carriers.contains(&map)
    }

    /// The start of the map's table: see the module.
    fn table(&self, map: i32) -> Vec<Pair> {
        let mut table = self.associations.clone();
        let bodies = if self.carries(map) {
            &self.bodies[..]
        } else {
            &[]
        };
        for g in bodies
            .iter()
            .chain(self.landed.get(&map).into_iter().flatten())
        {
            if !table.contains(g) {
                table.push(g.clone());
            }
        }
        table
    }

    /// The table a map's pages start numbering from.
    pub fn graphics(&self, map: i32) -> Graphics {
        let mut graphics = Graphics::new(&self.table(map));
        if let Some(on) = self.on_events.get(&map) {
            graphics.on_events.extend(on.iter().cloned());
        }
        graphics
    }

    /// The index of a graphic in the table of the map a page jumped to, if
    /// it was gathered there.
    pub fn index(&self, map: i32, charset: &str, index: i32) -> Option<usize> {
        self.table(map)
            .iter()
            .position(|(c, i)| c == charset && *i == index)
    }

    /// The index of a graphic a common event's body gives before jumping:
    /// the same in every map that runs the body.
    pub fn index_in_bodies(&self, charset: &str, index: i32) -> Option<usize> {
        self.associations
            .iter()
            .chain(&self.bodies)
            .position(|(c, i)| c == charset && *i == index)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::{Condition, Event, Page};

    fn page(trigger: i32, commands: Vec<Command>) -> Page {
        Page {
            trigger,
            layer: 1,
            move_type: 0,
            move_frequency: 3,
            move_speed: 3,
            animation_type: 0,
            character_name: String::new(),
            character_index: 0,
            character_pattern: 1,
            commands,
            route: vec![],
            route_repeat: false,
            route_skippable: false,
            condition: Condition::default(),
            id: 1,
            translucent: false,
            overlap_forbidden: false,
        }
    }

    fn map(id: i32, pages: Vec<Page>) -> Map {
        Map {
            id,
            events: vec![Event {
                id: 1,
                x: 0,
                y: 0,
                pages,
                starting: None,
            }],
        }
    }

    /// `MoveEvent` on `target` with command 34 to that CharSet and index.
    fn graphic(target: i32, name: &str, index: i32) -> Command {
        let mut p = vec![target, 8, 0, 0, ROUTE_CHANGE_GRAPHIC, name.len() as i32];
        p.extend(name.bytes().map(i32::from));
        p.push(index);
        Command::new(MOVE_EVENT, 0, "", p)
    }

    fn teleport(to: i32) -> Command {
        Command::new(TELEPORT, 0, "", vec![to, 1, 1])
    }

    fn call(common: i32) -> Command {
        Command::new(CALL_EVENT, 0, "", vec![0, common, 0])
    }

    fn body(commands: Vec<Command>) -> CommonEvent {
        CommonEvent {
            trigger: 5,
            switch_flag: false,
            switch_id: 1,
            commands,
        }
    }

    fn pair(name: &str, index: i32) -> Pair {
        (name.to_string(), index)
    }

    fn gather(
        maps: &[Map],
        commons: &BTreeMap<i32, CommonEvent>,
        associations: &[Pair],
    ) -> Landings {
        Landings::gather(maps, commons, associations, &BTreeSet::new(), |m| {
            m == 1 || m == 3
        })
    }

    #[test]
    fn a_graphic_after_a_jump_goes_to_the_destination_after_the_associations() {
        let grid = map(
            3,
            vec![page(0, vec![teleport(1), graphic(10001, "Plates1", 6)])],
        );
        let battle = map(1, vec![]);
        let l = gather(&[battle, grid], &BTreeMap::new(), &[pair("CarRED", 0)]);
        assert_eq!(l.index(1, "Plates1", 6), Some(1));
        assert_eq!(
            l.index(3, "Plates1", 6),
            None,
            "the grid's own pages number it there"
        );
        assert_eq!(
            l.graphics(1).pairs,
            vec![pair("CarRED", 0), pair("Plates1", 6)]
        );
        assert!(
            l.graphics(1).on_events.is_empty(),
            "the hero's: only he shows it"
        );
    }

    #[test]
    fn neither_before_the_jump_nor_on_the_same_map_nor_from_a_parallel() {
        let m = map(
            3,
            vec![
                page(
                    0,
                    vec![graphic(10001, "A", 0), teleport(3), graphic(10001, "B", 0)],
                ),
                page(TRIGGER_PARALLEL, vec![teleport(1), graphic(10001, "C", 0)]),
                page(0, vec![teleport(9), graphic(10001, "D", 0)]),
            ],
        );
        let l = gather(&[m], &BTreeMap::new(), &[]);
        assert_eq!(l.graphics(1).pairs, vec![]);
        assert_eq!(l.graphics(3).pairs, vec![]);
        assert_eq!(l.index(9, "D", 0), None, "map 9 is not in the cartridge");
    }

    #[test]
    fn a_page_called_after_the_jump_is_walked_with_it() {
        let mut m = map(
            3,
            vec![page(
                0,
                vec![teleport(1), Command::new(CALL_EVENT, 0, "", vec![1, 1, 2])],
            )],
        );
        m.events[0]
            .pages
            .push(page(0, vec![graphic(10001, "F", 1)]));
        let l = gather(&[m], &BTreeMap::new(), &[]);
        assert_eq!(l.index(1, "F", 1), Some(0));
    }

    #[test]
    fn a_common_event_that_jumps_numbers_there() {
        let commons = BTreeMap::from([(4, body(vec![teleport(3), graphic(10001, "G", 0)]))]);
        let l = gather(&[], &commons, &[]);
        assert_eq!(l.graphics(3).pairs, vec![pair("G", 0)]);
    }

    #[test]
    fn a_body_s_graphic_goes_after_the_associations_where_it_is_called() {
        // Common event 18 is called from map 3 through common event 17; map
        // 1 calls neither. The body's graphic is index 1 in map 3, as
        // `index_in_bodies` says, and map 1 does not carry it.
        let commons = BTreeMap::from([
            (17, body(vec![call(18)])),
            (18, body(vec![graphic(10001, "Lutine", 0)])),
        ]);
        let item_screen = map(
            3,
            vec![page(0, vec![call(17), teleport(1), graphic(10001, "X", 0)])],
        );
        let other = map(1, vec![page(0, vec![graphic(10001, "Own", 0)])]);
        let l = gather(&[other, item_screen], &commons, &[pair("Car", 0)]);
        assert_eq!(l.index_in_bodies("Lutine", 0), Some(1));
        assert_eq!(l.graphics(3).pairs, vec![pair("Car", 0), pair("Lutine", 0)]);
        assert_eq!(l.graphics(1).pairs, vec![pair("Car", 0), pair("X", 0)]);
    }

    #[test]
    fn a_body_an_automatic_one_reaches_is_carried_by_every_map() {
        let commons = BTreeMap::from([(18, body(vec![graphic(10001, "Lutine", 0)]))]);
        let l = Landings::gather(
            &[map(1, vec![])],
            &commons,
            &[],
            &BTreeSet::from([18]),
            |m| m == 1,
        );
        assert_eq!(l.graphics(1).pairs, vec![pair("Lutine", 0)]);
        assert_eq!(l.graphics(5).pairs, vec![pair("Lutine", 0)]);
    }

    #[test]
    fn one_given_to_an_event_is_noted_as_such() {
        let m = map(3, vec![page(0, vec![teleport(1), graphic(4, "E", 2)])]);
        let l = gather(&[m], &BTreeMap::new(), &[]);
        assert!(l.graphics(1).on_events.contains(&pair("E", 2)));
    }
}
