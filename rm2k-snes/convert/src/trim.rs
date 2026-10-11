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
//! The order is by what is lost, the least first; within each class, the
//! highest id first, which is the last one placed: a rule anyone can redo by
//! reading the map.

use crate::game::Command;
use ditto::schema;
use std::collections::BTreeSet;

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

/// What the map loses with an event, from the least to the most: the
/// order they are left out in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Loss {
    /// It does nothing: no page has a command, nobody names it, it draws
    /// nothing and does not block.
    Nothing,
    /// Only its looks: a drawing, walking or not, that does not block.
    Looks,
    /// Only a wall: nothing drawn, on the hero's layer.
    Wall,
    /// Its looks and a wall.
    LooksAndWall,
    /// Pages that run, but nobody names it.
    Pages,
    /// Somebody names it: the pages that do, do not compile either.
    Named,
}

impl Loss {
    pub fn describe(self) -> &'static str {
        match self {
            Loss::Nothing => "nothing",
            Loss::Looks => "only their looks",
            Loss::Wall => "an invisible wall",
            Loss::LooksAndWall => "their looks and a wall",
            Loss::Pages => "pages that run",
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
pub fn named<'a>(events: &[schema::Event], others: impl IntoIterator<Item = &'a Command>) -> BTreeSet<i32> {
    let own = events
        .iter()
        .flat_map(|e| &e.pages)
        .flat_map(|p| &p.event_commands)
        .flat_map(|c| names(c.code.to_i32(), &c.parameters));
    own.chain(others.into_iter().flat_map(|c| names(c.code, &c.parameters))).collect()
}

/// What the map loses with event `e`.
pub fn loss(e: &schema::Event, named: &BTreeSet<i32>) -> Loss {
    if named.contains(&e.id) {
        return Loss::Named;
    }
    let pages = &e.pages;
    // The terminating command, code 0, is not a command.
    if pages.iter().any(|p| p.event_commands.iter().any(|c| c.code.to_i32() != 0)) {
        return Loss::Pages;
    }
    // A graphic: a CharSet, or a tile of the upper layer, which has no
    // name and an index other than 0.
    let drawn = pages.iter().any(|p| !p.character_name.is_empty() || p.character_index != 0);
    let blocks = pages.iter().any(|p| p.layer.to_i32() == LAYER_SAME);
    match (drawn, blocks) {
        (false, false) => Loss::Nothing,
        (true, false) => Loss::Looks,
        (false, true) => Loss::Wall,
        (true, true) => Loss::LooksAndWall,
    }
}

/// The events left out so that `cap` remain, as `(id, what is lost)`, by
/// id. None if they fit.
pub fn left_out(events: &[schema::Event], named: &BTreeSet<i32>, cap: usize) -> Vec<(i32, Loss)> {
    if events.len() <= cap {
        return Vec::new();
    }
    let mut order: Vec<(Loss, i32)> = events.iter().map(|e| (loss(e, named), e.id)).collect();
    order.sort_by_key(|&(l, id)| (l, std::cmp::Reverse(id)));
    let mut out: Vec<(i32, Loss)> = order[..events.len() - cap].iter().map(|&(l, id)| (id, l)).collect();
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
            let ids: Vec<String> = out.iter().filter(|&&(_, l)| l == class).map(|(id, _)| id.to_string()).collect();
            format!("{} lose {} ({})", ids.len(), class.describe(), ids.join(" "))
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
        let commands: Vec<_> = commands.iter().map(|(c, p)| json!({"code": c, "parameters": p})).collect();
        serde_json::from_value(json!({
            "id": id, "x": id, "y": 0,
            "pages": [{"id": 1, "character_name": charset, "character_index": 0, "layer": layer,
                       "move_type": 0, "trigger": 0, "event_commands": commands}]
        }))
        .unwrap()
    }

    const TELEPORT: i32 = 10810;

    #[test]
    fn a_map_that_fits_loses_nothing() {
        let events: Vec<_> = (1..=3).map(|i| event(i, &[], "", 0)).collect();
        assert!(left_out(&events, &BTreeSet::new(), 3).is_empty());
    }

    #[test]
    fn the_ones_that_do_nothing_go_first_then_looks_walls_and_pages() {
        let events = vec![
            event(1, &[(TELEPORT, vec![1, 2, 3])], "", 0),
            event(2, &[], "Chara1", 0),
            event(3, &[], "", 0),
            event(4, &[], "", LAYER_SAME),
            event(5, &[], "Chara1", LAYER_SAME),
            event(6, &[(TELEPORT, vec![1, 2, 3])], "", 0),
            event(7, &[], "", 0),
        ];
        let named = BTreeSet::new();
        let ids = |cap| left_out(&events, &named, cap).into_iter().map(|(id, _)| id).collect::<Vec<_>>();
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
    fn one_that_is_named_goes_last() {
        // Event 2 is moved by event 1's page, and a variable reads where 3
        // is: neither does anything by itself, and both are kept.
        let events = vec![
            event(1, &[(MOVE_EVENT, vec![2]), (CONTROL_VARIABLES, vec![0, 1, 1, 0, OPERAND_CHARACTER, 3, 0])], "", 0),
            event(2, &[], "", 0),
            event(3, &[], "", 0),
            event(4, &[(TELEPORT, vec![1, 2, 3])], "", 0),
        ];
        let named = named(&events, &[]);
        assert_eq!(named, BTreeSet::from([2, 3]));
        assert_eq!(left_out(&events, &named, 2), [(1, Loss::Pages), (4, Loss::Pages)]);
        assert_eq!(left_out(&events, &named, 1), [(1, Loss::Pages), (3, Loss::Named), (4, Loss::Pages)]);
    }

    #[test]
    fn a_common_event_names_too() {
        let events = vec![event(1, &[], "", 0), event(2, &[], "", 0)];
        let call = Command { code: FLASH_SPRITE, indent: 0, string: String::new(), parameters: vec![2, 31, 31, 31, 31, 5, 0] };
        let named = named(&events, [&call]);
        assert_eq!(left_out(&events, &named, 1), [(1, Loss::Nothing)]);
    }
}
