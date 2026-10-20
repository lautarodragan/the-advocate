//! The events that do not fit in the console's RAM: a map with more than
//! `EV_MAX` —each event is a row of `ev_pos_buf`, `ev_flags` and
//! `pick_by_ev`, in bank 0— keeps the ones that matter and the cartridge
//! is built anyway, with a WARNING that names the ones left out.
//!
//! An event left out **stops existing** for the cartridge: it is taken out
//! of the map as it is read, here and in every stage that reads the map
//! —the compiler and Wally get the list in their requests, `dropped_events`—,
//! so the indices are the same everywhere. A page that names one does not
//! compile, as with any event that does not exist.
//!
//! Before losing anything, the **twins** go in a row they share: see
//! [`twins`]. That is what most of those maps have too many of —a strip
//! of seventy invisible touch events along an edge, each a `Teleport` to
//! the same place; a grid of invisible signs on the hero's layer, each the
//! same message—, and it costs nothing that can be seen.
//!
//! Then the order is by what is lost, the least first; within each class,
//! the highest id first, which is the last one placed: a rule anyone can
//! redo by reading the map. An exit goes after every other page that runs:
//! a sign left out is a sign less, an exit left out can leave the player
//! with no way on.

use crate::game::Command;
use ditto::schema;
use std::collections::{BTreeMap, BTreeSet};

/// ShowBattleAnimation, ChangeEventLocation, TradeEventLocations,
/// FlashSprite, MoveEvent, ConditionalBranch, ControlVariables and
/// CallEvent, liblcf's codes: the commands that can name a map event.
const SHOW_BATTLE_ANIMATION: i32 = 11210;
const CHANGE_EVENT_LOCATION: i32 = 10860;
const TRADE_EVENT_LOCATIONS: i32 = 10870;
const FLASH_SPRITE: i32 = 11320;
const MOVE_EVENT: i32 = 11330;
const COND_BRANCH: i32 = 12010;
const CONTROL_VARIABLES: i32 = 10220;
const CALL_EVENT: i32 = 12330;
/// A `ConditionalBranch` that asks where an event looks.
const BRANCH_EVENT_FACING: i32 = 6;
/// A `ControlVariables` whose operand is a character's cell or direction.
const OPERAND_CHARACTER: i32 = 6;
/// A `CallEvent` of a map event, by its id.
const CALL_MAP_EVENT: i32 = 1;
/// The hero's layer: an event there blocks.
const LAYER_SAME: i32 = 1;
/// `Teleport`: a page that carries one is an exit.
const TELEPORT: i32 = 10810;

/// What the map loses with an event, from the least to the most: the
/// order they are left out in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Loss {
    /// It does nothing: no page has a command, nobody names it, it draws
    /// nothing and does not block.
    Nothing,
    /// A wall and nothing else that never stops being one —[`still_wall`]—:
    /// its cell goes closed in the map's passability, so nothing is lost.
    StillWall,
    /// Only its looks: a drawing, walking or not, that does not block.
    Looks,
    /// A drawing and a wall that never stops being one: the drawing is
    /// lost, the wall goes to the map's passability as a [`Loss::StillWall`]
    /// does.
    LooksAndStillWall,
    /// Only a wall: nothing drawn, on the hero's layer, and one that may
    /// stop blocking —see [`still_wall`]—, so it cannot be baked.
    Wall,
    /// Its looks and a wall, one that may stop blocking.
    LooksAndWall,
    /// Pages that run, but nobody names it.
    Pages,
    /// Pages that run and one of them a `Teleport`: an exit, which the
    /// player may have no other way through. Above the other pages since
    /// 2026-10-17: Zounds' map 47 lost its east edge's six exits before
    /// its info signs, and the story goes through there.
    Exit,
    /// Somebody names it: the pages that do, do not compile either.
    Named,
}

impl Loss {
    pub fn describe(self) -> &'static str {
        match self {
            Loss::Nothing => "nothing",
            Loss::StillWall => "nothing: a still wall, closed in the map's passability",
            Loss::Looks => "only their looks",
            Loss::LooksAndStillWall => {
                "only their looks: their wall stays, closed in the map's passability"
            }
            Loss::Wall => "an invisible wall",
            Loss::LooksAndWall => "their looks and a wall",
            Loss::Pages => "pages that run",
            Loss::Exit => "pages that run, with a Teleport: a box says so on their cells",
            Loss::Named => "pages that run, and the pages that name them",
        }
    }
}

/// The map event ids a command names, if it names any. "This event" and
/// the hero are not ids, and come out as they are: nobody has them.
pub fn names(code: i32, p: &[i32]) -> Vec<i32> {
    let at = |i: usize| p.get(i).copied();
    match code {
        SHOW_BATTLE_ANIMATION => at(1).into_iter().collect(),
        FLASH_SPRITE | MOVE_EVENT | CHANGE_EVENT_LOCATION => at(0).into_iter().collect(),
        TRADE_EVENT_LOCATIONS => p.iter().take(2).copied().collect(),
        COND_BRANCH if at(0) == Some(BRANCH_EVENT_FACING) => at(1).into_iter().collect(),
        CONTROL_VARIABLES if at(4) == Some(OPERAND_CHARACTER) => at(5).into_iter().collect(),
        CALL_EVENT if at(0) == Some(CALL_MAP_EVENT) => at(1).into_iter().collect(),
        _ => Vec::new(),
    }
}

/// The ids named by the map's pages and by `others`: the common events,
/// which a `CallEvent` brings into any map, and the test pages.
pub fn named<'a>(
    events: &[schema::Event],
    others: impl IntoIterator<Item = &'a Command>,
) -> BTreeSet<i32> {
    let own = events
        .iter()
        .flat_map(|e| &e.pages)
        .flat_map(|p| &p.event_commands)
        .flat_map(|c| names(c.code.to_i32(), &c.parameters));
    own.chain(
        others
            .into_iter()
            .flat_map(|c| names(c.code, &c.parameters)),
    )
    .collect()
}

/// What the map loses with event `e`.
pub fn loss(e: &schema::Event, named: &BTreeSet<i32>) -> Loss {
    if named.contains(&e.id) {
        return Loss::Named;
    }
    let pages = &e.pages;
    // The terminating command, code 0, is not a command.
    if pages
        .iter()
        .any(|p| p.event_commands.iter().any(|c| c.code.to_i32() == TELEPORT))
    {
        return Loss::Exit;
    }
    if pages
        .iter()
        .any(|p| p.event_commands.iter().any(|c| c.code.to_i32() != 0))
    {
        return Loss::Pages;
    }
    // A graphic: a CharSet, or a tile of the upper layer, which has no
    // name and an index other than 0.
    let drawn = pages
        .iter()
        .any(|p| !p.character_name.is_empty() || p.character_index != 0);
    let blocks = pages.iter().any(|p| p.layer.to_i32() == LAYER_SAME);
    match (drawn, blocks, blocks && still_wall(e)) {
        (false, false, _) => Loss::Nothing,
        (true, false, _) => Loss::Looks,
        (false, true, true) => Loss::StillWall,
        (true, true, true) => Loss::LooksAndStillWall,
        (false, true, false) => Loss::Wall,
        (true, true, false) => Loss::LooksAndWall,
    }
}

/// Whether `e`, which runs nothing and nobody names, blocks its cell all
/// the time and in the same cell: every page on the hero's layer, none
/// that walks —no move type, no route of its own, which could also make it
/// pass through things—, and one page with no conditions, so a page is
/// always active. Conditions are not read: any page can be the active one,
/// so all of them have to be walls, and the worst is assumed. Erasing it, or
/// moving it, would take a command of its own or one that names it, and
/// [`loss`] only asks this of an event without either.
///
/// Such a wall left out is not lost: its cell goes closed in the map's
/// passability, as Wally does with a decorative event on that layer —see
/// [`crate::game::Game::walls`]—. Desert Nightmare's maps 4 and 14 and
/// their night copies have more than a hundred of them.
pub fn still_wall(e: &schema::Event) -> bool {
    let pages = &e.pages;
    !pages.is_empty()
        && pages.iter().all(|p| {
            p.layer.to_i32() == LAYER_SAME
                && p.move_type.to_i32() == 0
                && p.move_route.move_commands.is_empty()
                && p.event_commands.iter().all(|c| c.code.to_i32() == 0)
        })
        && pages.iter().any(|p| {
            let f = &p.condition.flags;
            !(f.switch_a || f.switch_b || f.variable || f.item || f.actor || f.timer || f.timer2)
        })
}

/// "This event", in the commands that name one.
const THIS_EVENT: i32 = 10005;
/// `EraseEvent`: it erases the event that runs it, and a twin would erase
/// the whole family.
const ERASE_EVENT: i32 = 12320;
/// Autostart and parallel: they run once per event, and a family would run
/// once.
const TRIGGER_AUTOSTART: i32 = 3;
const TRIGGER_PARALLEL: i32 = 4;

/// Whether `e` can be a twin: an event the console can keep as nothing but
/// a cell that leads to another's pages. It has pages that run, or it is
/// an invisible wall —one that does nothing at all is better left out—;
/// nobody names it, it draws nothing, it never moves, and no page of its
/// own is autostart or parallel, erases itself or names "this event": all
/// of that would be done on the one whose row it shares, and in RM2k it is
/// its own.
///
/// It may be on the hero's layer, since 2026-10-17: `hero_blocked` looks
/// at the twins after the rows, with the active page of the one whose row
/// it shares, so it blocks the hero if its pages say so. Not an event that
/// walks into it, which RM2k would stop: see `hero_blocked`. Zounds' maps 47 and 51
/// are grids of invisible signs on that layer, two hundred the same
/// message, and before that they were left out by the hundred.
fn can_be_twin(e: &schema::Event, named: &BTreeSet<i32>) -> bool {
    matches!(
        loss(e, named),
        Loss::Wall | Loss::StillWall | Loss::Pages | Loss::Exit
    ) && e.pages.iter().all(|p| {
        p.character_name.is_empty()
            && p.character_index == 0
            && p.move_type.to_i32() == 0
            && p.move_route.move_commands.is_empty()
            && !matches!(p.trigger.to_i32(), TRIGGER_AUTOSTART | TRIGGER_PARALLEL)
            && p.event_commands.iter().all(|c| {
                c.code.to_i32() != ERASE_EVENT
                    && !names(c.code.to_i32(), &c.parameters).contains(&THIS_EVENT)
            })
    })
}

/// The twins: events whose pages are the same as another's —every field
/// but the cell—, as `(twin, the one with the lowest id)`, by id. The
/// console keeps only the first, and each twin is a cell in a table behind
/// the map's positions that `event_in_cell` and `hero_blocked` look at
/// after the rows: the action button or a step on that cell runs the first
/// one's page, which is the same page, and the hero's step into it is
/// refused if that page is on his layer. Its id is not in the cartridge any more, but nobody
/// names it, and nothing in its pages tells one twin from another.
pub fn twins(events: &[schema::Event], named: &BTreeSet<i32>) -> Vec<(i32, i32)> {
    let mut first: BTreeMap<String, i32> = BTreeMap::new();
    let mut out = Vec::new();
    let mut sorted: Vec<&schema::Event> = events.iter().filter(|e| can_be_twin(e, named)).collect();
    sorted.sort_by_key(|e| e.id);
    for e in sorted {
        // The pages as text: `EventPage` has no `Ord` nor `Hash`, and the
        // dump's own form is the one that says two are the same.
        let key = format!("{:?}", e.pages);
        match first.get(&key) {
            Some(&owner) => out.push((e.id, owner)),
            None => {
                first.insert(key, e.id);
            }
        }
    }
    out
}

/// The events left out so that `cap` remain, as `(id, what is lost)`, by
/// id. None if they fit.
pub fn left_out(events: &[schema::Event], named: &BTreeSet<i32>, cap: usize) -> Vec<(i32, Loss)> {
    if events.len() <= cap {
        return Vec::new();
    }
    let mut order: Vec<(Loss, i32)> = events.iter().map(|e| (loss(e, named), e.id)).collect();
    order.sort_by_key(|&(l, id)| (l, std::cmp::Reverse(id)));
    let mut out: Vec<(i32, Loss)> = order[..events.len() - cap]
        .iter()
        .map(|&(l, id)| (id, l))
        .collect();
    out.sort();
    out
}

/// The WARNING of map `map`, which had `total` events and keeps `cap`.
pub fn warning(map: i32, total: usize, cap: usize, out: &[(i32, Loss)]) -> String {
    let mut classes: Vec<Loss> = out.iter().map(|&(_, l)| l).collect();
    classes.sort();
    classes.dedup();
    let parts: Vec<String> = classes
        .iter()
        .map(|&class| {
            let ids: Vec<String> = out
                .iter()
                .filter(|&&(_, l)| l == class)
                .map(|(id, _)| id.to_string())
                .collect();
            format!(
                "{} lose {} ({})",
                ids.len(),
                class.describe(),
                ids.join(" ")
            )
        })
        .collect();
    format!(
        "  map {map}: WARNING, {total} events and the console's RAM holds {cap}: {} are left out: {}",
        out.len(),
        parts.join("; ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// An event of one page: `commands` as codes, a CharSet or not, on
    /// the hero's layer or below.
    fn event(id: i32, commands: &[(i32, Vec<i32>)], charset: &str, layer: i32) -> schema::Event {
        let commands: Vec<_> = commands
            .iter()
            .map(|(c, p)| json!({"code": c, "parameters": p}))
            .collect();
        serde_json::from_value(json!({
            "id": id, "x": id, "y": 0,
            "pages": [{"id": 1, "character_name": charset, "character_index": 0, "layer": layer,
                       "move_type": 0, "trigger": 0, "event_commands": commands}]
        }))
        .unwrap()
    }

    #[test]
    fn a_map_that_fits_loses_nothing() {
        let events: Vec<_> = (1..=3).map(|i| event(i, &[], "", 0)).collect();
        assert!(left_out(&events, &BTreeSet::new(), 3).is_empty());
    }

    /// A wall that may stop blocking: a second page, under a switch, below
    /// the hero.
    fn conditional(mut e: schema::Event) -> schema::Event {
        let mut page = e.pages[0].clone();
        page.id = 2;
        page.layer = serde_json::from_value(json!(0)).unwrap();
        page.condition.flags.switch_a = true;
        e.pages.push(page);
        e
    }

    #[test]
    fn the_ones_that_do_nothing_go_first_then_looks_walls_and_pages() {
        let events = vec![
            event(1, &[(TELEPORT, vec![1, 2, 3])], "", 0),
            event(2, &[], "Chara1", 0),
            event(3, &[], "", 0),
            conditional(event(4, &[], "", LAYER_SAME)),
            conditional(event(5, &[], "Chara1", LAYER_SAME)),
            event(6, &[(TELEPORT, vec![1, 2, 3])], "", 0),
            event(7, &[], "", 0),
        ];
        let named = BTreeSet::new();
        let ids = |cap| {
            left_out(&events, &named, cap)
                .into_iter()
                .map(|(id, _)| id)
                .collect::<Vec<_>>()
        };
        // The two that do nothing, the highest first.
        assert_eq!(ids(6), [7]);
        assert_eq!(ids(5), [3, 7]);
        assert_eq!(ids(4), [2, 3, 7]);
        assert_eq!(ids(3), [2, 3, 4, 7]);
        assert_eq!(ids(2), [2, 3, 4, 5, 7]);
        // And of the two with pages, the last one placed.
        assert_eq!(ids(1), [2, 3, 4, 5, 6, 7]);
        assert_eq!(
            left_out(&events, &named, 5),
            [(3, Loss::Nothing), (7, Loss::Nothing)]
        );
    }

    #[test]
    fn a_still_wall_loses_nothing_and_one_that_can_stop_blocking_a_wall() {
        let wall = |id| event(id, &[], "", LAYER_SAME);
        let drawn = |id| event(id, &[], "Chara1", LAYER_SAME);
        let named = BTreeSet::new();
        assert_eq!(loss(&wall(1), &named), Loss::StillWall);
        assert_eq!(loss(&drawn(1), &named), Loss::LooksAndStillWall);
        // Any page can be the active one: one below the hero, under a
        // switch, is enough to make it a wall that can go away.
        assert_eq!(loss(&conditional(wall(1)), &named), Loss::Wall);
        assert_eq!(loss(&conditional(drawn(1)), &named), Loss::LooksAndWall);
        // Its only page under a switch: with the switch off it is not
        // there.
        let mut off = wall(1);
        off.pages[0].condition.flags.variable = true;
        assert_eq!(loss(&off, &named), Loss::Wall);
        // A wall that walks, at random or by a route of its own.
        let mut walks = wall(1);
        walks.pages[0].move_type = serde_json::from_value(json!(1)).unwrap();
        assert_eq!(loss(&walks, &named), Loss::Wall);
        let mut routed = wall(1);
        routed.pages[0].move_route.move_commands =
            serde_json::from_value(json!([{"command_id": 0}])).unwrap();
        assert_eq!(loss(&routed, &named), Loss::Wall);
        // Two pages, both walls, one under a switch: still.
        let mut two = wall(1);
        let mut second = two.pages[0].clone();
        second.condition.flags.switch_a = true;
        two.pages.push(second);
        assert_eq!(loss(&two, &named), Loss::StillWall);
        // Named, it can be moved: what it is, it loses all of.
        assert_eq!(loss(&wall(1), &BTreeSet::from([1])), Loss::Named);
    }

    #[test]
    fn a_still_wall_goes_before_a_drawing_and_one_that_can_stop_blocking_after() {
        // Desert Nightmare's map 14: still walls by the dozen, and four
        // that a switch takes down. Those are kept while anything else can
        // go.
        let events = vec![
            event(1, &[], "", LAYER_SAME),
            conditional(event(2, &[], "", LAYER_SAME)),
            event(3, &[], "Chara1", 0),
            event(4, &[], "Chara1", LAYER_SAME),
            event(5, &[(10110, vec![])], "", 0),
        ];
        let named = BTreeSet::new();
        assert_eq!(left_out(&events, &named, 4), [(1, Loss::StillWall)]);
        assert_eq!(
            left_out(&events, &named, 2),
            [
                (1, Loss::StillWall),
                (3, Loss::Looks),
                (4, Loss::LooksAndStillWall)
            ]
        );
        assert_eq!(left_out(&events, &named, 1)[1], (2, Loss::Wall));
    }

    #[test]
    fn one_that_is_named_goes_last() {
        // Event 2 is moved by event 1's page, and a variable reads where 3
        // is: neither does anything by itself, and both are kept.
        let events = vec![
            event(
                1,
                &[
                    (MOVE_EVENT, vec![2]),
                    (CONTROL_VARIABLES, vec![0, 1, 1, 0, OPERAND_CHARACTER, 3, 0]),
                ],
                "",
                0,
            ),
            event(2, &[], "", 0),
            event(3, &[], "", 0),
            event(4, &[(TELEPORT, vec![1, 2, 3])], "", 0),
        ];
        let named = named(&events, &[]);
        assert_eq!(named, BTreeSet::from([2, 3]));
        assert_eq!(
            left_out(&events, &named, 2),
            [(1, Loss::Pages), (4, Loss::Exit)]
        );
        assert_eq!(
            left_out(&events, &named, 1),
            [(1, Loss::Pages), (3, Loss::Named), (4, Loss::Exit)]
        );
    }

    #[test]
    fn an_exit_stays_over_a_sign_placed_before_it() {
        // Zounds' map 47: the signs have the low ids and the exits on the
        // edge the high ones, and the highest id went first.
        let sign = [(10110, vec![])];
        let events = vec![
            event(1, &sign, "", LAYER_SAME),
            event(2, &sign, "Chara1", LAYER_SAME),
            event(3, &[(TELEPORT, vec![51, 1, 25, 0])], "", 0),
        ];
        let named = BTreeSet::new();
        assert_eq!(left_out(&events, &named, 2), [(2, Loss::Pages)]);
        assert_eq!(
            left_out(&events, &named, 1),
            [(1, Loss::Pages), (2, Loss::Pages)]
        );
    }

    #[test]
    fn a_common_event_names_too() {
        let events = vec![event(1, &[], "", 0), event(2, &[], "", 0)];
        let call = Command {
            code: FLASH_SPRITE,
            indent: 0,
            string: String::new(),
            parameters: vec![2, 31, 31, 31, 31, 5, 0],
        };
        let named = named(&events, [&call]);
        assert_eq!(left_out(&events, &named, 1), [(1, Loss::Nothing)]);
    }

    /// The same, with its page's trigger.
    fn with_trigger(mut e: schema::Event, trigger: i32) -> schema::Event {
        e.pages[0].trigger = serde_json::from_value(json!(trigger)).unwrap();
        e
    }

    #[test]
    fn the_same_pages_invisible_and_still_share_the_first_ones_row() {
        let door = [(TELEPORT, vec![1, 2, 3])];
        let events = vec![
            event(1, &door, "", 0),
            event(2, &door, "", 0),
            event(3, &[(TELEPORT, vec![1, 9, 9])], "", 0),
            event(4, &door, "", 0),
            // On the hero's layer it blocks, and it is a page of its own:
            // the first of another family, with 9.
            event(5, &door, "", LAYER_SAME),
            // Drawn: a cell of its own.
            event(6, &door, "Chara1", 0),
            // Named: whoever names it would find the first one.
            event(7, &door, "", 0),
            event(8, &[(MOVE_EVENT, vec![7])], "", 0),
            event(9, &door, "", LAYER_SAME),
            // Invisible walls are twins too, and two that do nothing
            // are not: they are left out first.
            event(10, &[], "", LAYER_SAME),
            event(11, &[], "", LAYER_SAME),
            event(12, &[], "", 0),
            event(13, &[], "", 0),
        ];
        let named = named(&events, &[]);
        assert_eq!(twins(&events, &named), [(2, 1), (4, 1), (9, 5), (11, 10)]);
    }

    #[test]
    fn what_a_page_does_to_its_own_event_keeps_it_apart() {
        let erase = [(ERASE_EVENT, vec![])];
        let flash = [(FLASH_SPRITE, vec![THIS_EVENT, 31, 31, 31, 31, 5, 0])];
        let wait = [(11410, vec![1])];
        let events = vec![
            event(1, &erase, "", 0),
            event(2, &erase, "", 0),
            event(3, &flash, "", 0),
            event(4, &flash, "", 0),
            with_trigger(event(5, &wait, "", 0), TRIGGER_PARALLEL),
            with_trigger(event(6, &wait, "", 0), TRIGGER_PARALLEL),
            with_trigger(event(7, &wait, "", 0), TRIGGER_AUTOSTART),
            with_trigger(event(8, &wait, "", 0), TRIGGER_AUTOSTART),
            // Touch, by the hero: twins.
            with_trigger(event(9, &wait, "", 0), 1),
            with_trigger(event(10, &wait, "", 0), 1),
        ];
        assert_eq!(twins(&events, &BTreeSet::new()), [(10, 9)]);
    }
}
