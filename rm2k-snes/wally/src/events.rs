//! A map's events as the port sees them, and the ones that are drawn.
//!
//! The events come from the dump in id order, with their pages in id order;
//! with the names the port gives some graphics —a translucent one baked
//! against its cell, one drawn apart from the hero—, which arrive in the
//! request; and, in the map where a test starts, an empty event first.

use crate::sprites::npc::{Graphic, Npc};
use crate::sprites::split::TILE_PREFIX;
use ditto::schema::{Event as DumpEvent, EventPage};
use rm2k_rules::passability::{ABOVE, ALL};
use std::collections::BTreeMap;

/// The suffix a translucent CharSet baked against its cell carries, with
/// the map and the cell after it.
pub const BAKED_SUFFIX: &str = "~horneado";

/// The first tile id of the upper layer.
pub const UPPER_BASE: i32 = 10000;

/// An event's three layers: only the hero's collides with him.
pub const LAYER_BELOW: i32 = 0;
pub const LAYER_SAME: i32 = 1;

/// The conditions the console checks. The timer travels in the variable's
/// place in the page record, so a page that asks for both leaves its event
/// out of the page table —see `map_pages` in rm2k-snes-events— and its
/// graphic does not follow its pages.
const SUPPORTED: [&str; 6] = ["switch_a", "switch_b", "actor", "variable", "item", "timer"];

/// An event page, with what the port reads of it.
#[derive(Clone, Debug)]
pub struct Page {
    pub name: String,
    pub index: i32,
    pub pose: i32,
    pub layer: i32,
    pub speed: i32,
    pub animation: i32,
    pub move_type: i32,
    pub own_route: bool,
    /// The conditions it asks for, by name.
    pub conditions: Vec<&'static str>,
    /// The commands, as `(code, parameters)`.
    pub commands: Vec<(i32, Vec<i32>)>,
}

#[derive(Clone, Debug)]
pub struct Event {
    pub id: i32,
    pub x: i32,
    pub y: i32,
    pub pages: Vec<Page>,
}

fn conditions(page: &EventPage) -> Vec<&'static str> {
    let f = &page.condition.flags;
    [
        ("switch_a", f.switch_a),
        ("switch_b", f.switch_b),
        ("variable", f.variable),
        ("item", f.item),
        ("actor", f.actor),
        ("timer", f.timer),
    ]
    .into_iter()
    .filter(|(_, on)| *on)
    .map(|(n, _)| n)
    .collect()
}

/// The map's events: sorted by id, their pages too, each graphic with the
/// name the port gives it —`names`, by `(event id, page id)`—, and an empty
/// one first if a test starts here.
pub fn events(
    dump: &[DumpEvent],
    names: &BTreeMap<(i32, i32), String>,
    test_event: bool,
) -> Vec<Event> {
    let mut sorted: Vec<&DumpEvent> = dump.iter().collect();
    sorted.sort_by_key(|e| e.id);
    let mut out = Vec::with_capacity(sorted.len() + 1);
    if test_event {
        // It goes first because the console walks the events from the lowest
        // to the highest, and the test's page has to run before the game's.
        // It has no pages: it only takes index 0.
        out.push(Event {
            id: 0,
            x: 0,
            y: 0,
            pages: Vec::new(),
        });
    }
    for e in sorted {
        let mut pages: Vec<&EventPage> = e.pages.iter().collect();
        pages.sort_by_key(|p| p.id);
        out.push(Event {
            id: e.id,
            x: e.x,
            y: e.y,
            pages: pages
                .into_iter()
                .map(|p| Page {
                    name: names
                        .get(&(e.id, p.id))
                        .cloned()
                        .unwrap_or_else(|| p.character_name.clone()),
                    index: p.character_index,
                    pose: rm2k_rules::charset::pose(p.character_direction, p.character_pattern),
                    layer: p.layer.to_i32(),
                    speed: p.move_speed.to_i32(),
                    animation: p.animation_type.to_i32(),
                    move_type: p.move_type.to_i32(),
                    own_route: !p.move_route.move_commands.is_empty(),
                    conditions: conditions(p),
                    commands: p
                        .event_commands
                        .iter()
                        .map(|c| (c.code.to_i32(), c.parameters.clone()))
                        .collect(),
                })
                .collect(),
        });
    }
    out
}

/// The name of the made-up sheet of an event drawn with upper-layer tile
/// `index` of this ChipSet.
pub fn tile_name(chipset: &str, index: i32) -> String {
    format!("{TILE_PREFIX}{chipset}:{index}")
}

/// A baked CharSet's name without where it stands: what it draws.
pub fn unbaked(name: &str) -> &str {
    match name.find(&format!("{BAKED_SUFFIX}:")) {
        Some(at) => &name[..at],
        None => name,
    }
}

/// What a page draws: its CharSet, or the sheet of its tile; `None` without
/// a CharSet and with tile 0.
pub fn page_graphic(page: &Page, chipset: &str) -> Option<Graphic> {
    if page.name.is_empty() && page.index == 0 {
        return None;
    }
    Some(if page.name.is_empty() {
        (tile_name(chipset, page.index), 0, page.pose)
    } else {
        (page.name.clone(), page.index, page.pose)
    })
}

/// The passage bits an event drawn with `charset` on `layer` imposes on
/// its cell: a tile on the lower layer imposes its own, unless it goes
/// above the hero.
pub fn tile_passability(flags: &[u8], charset: &str, layer: i32) -> Option<u8> {
    let base = unbaked(charset);
    if layer != LAYER_BELOW || !base.starts_with(TILE_PREFIX) {
        return None;
    }
    let index: i32 = base.rsplit(':').next()?.parse().ok()?;
    let value = flags[(UPPER_BASE + index) as usize];
    (value & ABOVE == 0).then_some(value & ALL)
}

/// Whether the console understands the conditions of all the event's pages,
/// which is what lets its graphic follow them.
fn supported(event: &Event) -> bool {
    event.pages.iter().all(|p| {
        p.conditions.iter().all(|c| SUPPORTED.contains(c))
            && !(p.conditions.contains(&"timer") && p.conditions.contains(&"variable"))
    })
}

/// The page RM2k shows in a freshly started game: the last one without a
/// condition.
fn active_page(event: &Event) -> Option<&Page> {
    event.pages.iter().rev().find(|p| p.conditions.is_empty())
}

/// The events that are drawn, with their pose and whether they block.
///
/// Every event with a graphic on **some** page gets in, even if the page
/// active at load has none: a door is a page without a graphic and another
/// with the rubble tile. `visible` says whether it is seen at load, and
/// `changes` whether the graphic follows the active page —only for events
/// whose conditions the console understands—. If the first page has a
/// condition, there may be none active: drawing nothing is one more state.
pub fn collect_npcs(events: &[Event], chipset: &str, flags: &[u8]) -> Vec<Npc> {
    let mut npcs = Vec::new();
    for (number, event) in events.iter().enumerate() {
        let graphics: Vec<Option<Graphic>> = event
            .pages
            .iter()
            .map(|p| page_graphic(p, chipset))
            .collect();
        if graphics.iter().all(Option::is_none) {
            continue;
        }
        let mut possible: Vec<&Option<Graphic>> = Vec::new();
        for g in &graphics {
            if !possible.contains(&g) {
                possible.push(g);
            }
        }
        let none = None;
        if event
            .pages
            .first()
            .is_some_and(|p| !p.conditions.is_empty())
            && !possible.contains(&&none)
        {
            possible.push(&none);
        }
        let supported = supported(event);
        let changes = possible.len() > 1 && supported;
        let active = active_page(event);
        let visible = active.is_some_and(|p| page_graphic(p, chipset).is_some());
        if !visible && !changes {
            continue;
        }
        let page = if visible {
            active.unwrap()
        } else {
            event
                .pages
                .iter()
                .zip(&graphics)
                .find(|(_, g)| g.is_some())
                .map(|(p, _)| p)
                .unwrap()
        };
        let (charset, index, pose) = page_graphic(page, chipset).unwrap();
        let tile_pass = if visible {
            tile_passability(flags, &charset, page.layer)
        } else {
            None
        };
        npcs.push(Npc {
            event: number,
            x: event.x,
            y: event.y,
            charset,
            index,
            pose,
            layer: page.layer,
            blocks: page.layer == LAYER_SAME,
            speed: page.speed,
            animates: matches!(page.animation, 1 | 3),
            visible,
            changes,
            graphics,
            layers: event.pages.iter().map(|p| p.layer).collect(),
            tile_pass,
            outside: Default::default(),
            appears: false,
        });
    }
    npcs
}

/// The rows of the events whose pages draw nothing and that a route dresses
/// —command 34—: `dressing` says, by event index, the graphics its routes
/// give it that draw something, in the map's order.
///
/// [`collect_npcs`] leaves out an event without a graphic on any page, and
/// without a row the ROM's `change_graphic` drops the change: in The Book of
/// Three a cutscene places such an event with `ChangeEventLocation`, dresses
/// it with a route and has it talk, and the scene went on with nobody. The
/// row starts hidden, with the first graphic a route gives it, and its
/// graphic follows the page: a page that becomes active draws nothing and
/// hides it again, which is `SetupFromPage` taking the page's empty
/// graphic. The rest —its layer, its speed, its pose— is the page active at
/// load's, or the first one's.
pub fn dressed_by_routes(
    events: &[Event],
    chipset: &str,
    drawn: &std::collections::BTreeSet<usize>,
    dressing: &BTreeMap<usize, Vec<(String, i32)>>,
) -> Vec<Npc> {
    let mut out = Vec::new();
    for (&number, graphics) in dressing {
        let Some(event) = events.get(number) else {
            continue;
        };
        let Some((charset, index)) = graphics.first().cloned() else {
            continue;
        };
        if drawn.contains(&number)
            || event.pages.is_empty()
            || event
                .pages
                .iter()
                .any(|p| page_graphic(p, chipset).is_some())
        {
            continue;
        }
        let supported = supported(event);
        let page = active_page(event).unwrap_or(&event.pages[0]);
        out.push(Npc {
            event: number,
            x: event.x,
            y: event.y,
            charset,
            index,
            pose: page.pose,
            layer: page.layer,
            blocks: page.layer == LAYER_SAME,
            speed: page.speed,
            animates: matches!(page.animation, 1 | 3),
            visible: false,
            changes: supported,
            graphics: vec![None; event.pages.len()],
            layers: event.pages.iter().map(|p| p.layer).collect(),
            tile_pass: None,
            outside: Default::default(),
            appears: false,
        });
    }
    out
}

/// Where a route command sends: 0 the hero, an event's index plus one, and
/// `None` for "this event" without an owner and an id the map lacks.
pub fn route_target(events: &[Event], who: i32) -> Option<usize> {
    const HERO: i32 = 10001;
    const THIS_EVENT: i32 = 10005;
    if who == HERO {
        return Some(0);
    }
    if who == THIS_EVENT {
        return None;
    }
    events.iter().position(|e| e.id == who).map(|n| n + 1)
}

/// Whether some page of the event draws something different from another:
/// what separates a decoration that is lost from a mechanism —a door that
/// opens— that breaks.
pub fn changes_graphic(event: &Event) -> bool {
    let mut graphics: Vec<(&str, i32)> = event
        .pages
        .iter()
        .map(|p| (p.name.trim(), p.index))
        .collect();
    graphics.sort();
    graphics.dedup();
    graphics.len() > 1
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn page(name: &str, conditions: Vec<&'static str>) -> Page {
        Page {
            name: name.into(),
            index: 0,
            pose: 7,
            layer: LAYER_SAME,
            speed: 3,
            animation: 0,
            move_type: 0,
            own_route: false,
            conditions,
            commands: Vec::new(),
        }
    }

    fn event(id: i32, pages: Vec<Page>) -> Event {
        Event {
            id,
            x: 4,
            y: 5,
            pages,
        }
    }

    #[test]
    fn an_event_a_route_dresses_gets_a_hidden_row_that_follows_its_pages() {
        // The Book of Three's map 32: the visitor in the cell has pages
        // without a graphic, and the scene's route dresses it.
        let events = vec![
            event(1, vec![page("Guard", vec![])]),
            event(2, vec![page("", vec![]), page("", vec!["switch_a"])]),
            event(3, vec![page("", vec![])]),
        ];
        let npcs = collect_npcs(&events, "tiles", &[0; 10200]);
        assert_eq!(npcs.iter().map(|n| n.event).collect::<Vec<_>>(), [0]);
        let drawn: BTreeSet<usize> = npcs.iter().map(|n| n.event).collect();
        let dressing = BTreeMap::from([
            (0, vec![("Other".to_string(), 1)]),
            (
                1,
                vec![("Visitor".to_string(), 2), ("Other".to_string(), 1)],
            ),
            (2, vec![]),
        ]);
        let rows = dressed_by_routes(&events, "tiles", &drawn, &dressing);
        // Not the one already drawn, nor the one only dressed blank.
        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!((row.event, row.x, row.y), (1, 4, 5));
        assert_eq!((row.charset.as_str(), row.index), ("Visitor", 2));
        assert!(!row.visible && row.changes);
        assert_eq!(row.graphics, vec![None, None]);
    }
}
