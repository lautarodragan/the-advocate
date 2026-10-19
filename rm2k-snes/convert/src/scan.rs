//! What the converter deduces from the whole cartridge before converting
//! any map: which actors can end up leading the party, which items and
//! members can be in it, where the timer can run, and whether some map
//! sets rain. The input is the cartridge's maps and the database; the
//! output, sets of ids.

use crate::compiler;
use crate::fail::Result;
use crate::game::{Command, Database, GameMap};
use rm2k_snes_events::codes::*;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

/// `ChangePartyMembers`' first parameter: add or remove; and its second:
/// the actor's id is the third parameter itself.
pub const PARTY_ADD: i32 = 0;
pub const PARTY_REMOVE: i32 = 1;
pub const PARTY_FIXED_ID: i32 = 0;
/// `WeatherEffects`' rain, and `TimerOperation`'s stop.
const WEATHER_RAIN: i32 = rm2k_snes_mapdata::engine::WEATHER_RAIN as i32;
const TIMER_START: i32 = rm2k_snes_mapdata::engine::TIMER_START as i32;
const TIMER_STOP: i32 = 2;
/// `CallEvent`'s first parameter when it calls a common event.
const CALL_COMMON: i32 = 0;

/// The party, to simulate its changes when converting. `Game_Party::
/// AddActor`/`RemoveActor`: adding one who is already there does not
/// duplicate it nor move it, adding with a full party does nothing, and
/// removing one who is not there does nothing either. The order decides
/// who the leader is, that is, which sprite is drawn.
#[derive(Debug, Clone)]
pub struct PartyState {
    pub party: Vec<i32>,
}

impl PartyState {
    pub fn new(party: &[i32]) -> PartyState {
        PartyState {
            party: party.to_vec(),
        }
    }

    pub fn change_party(&mut self, operation: i32, actor: i32) {
        if operation == PARTY_REMOVE {
            if let Some(at) = self.party.iter().position(|&a| a == actor) {
                self.party.remove(at);
            }
        } else if !self.party.contains(&actor)
            && self.party.len() < rm2k_snes_mapdata::engine::PARTY_MAX as usize
        {
            self.party.push(actor);
        }
    }

    pub fn leader(&self) -> Option<i32> {
        self.party.first().copied()
    }
}

/// A fixed-id `ChangePartyMembers`, as `(operation, actor)`.
fn party_change(cmd: &Command) -> Option<(i32, i32)> {
    let p = &cmd.parameters;
    (cmd.code == CHANGE_PARTY_MEMBERS && p.len() >= 3 && p[1] == PARTY_FIXED_ID)
        .then(|| (p[0], p[2]))
}

/// Whether some page of these maps sets rain: then every map of the ROM
/// carries the drops, because the weather persists across map changes.
/// `extra` are the commands of the test pages.
pub fn has_rain<'a>(maps: impl IntoIterator<Item = &'a GameMap>, extra: &[Command]) -> bool {
    let rains =
        |c: &Command| c.code == WEATHER_EFFECTS && c.parameters.first() == Some(&WEATHER_RAIN);
    extra.iter().any(rains) || maps.into_iter().any(|m| m.all_commands().any(rains))
}

/// The maps of the ROM where the timer can be running: the ones that carry
/// its digits, which cost a sprite palette.
///
/// In RM2k the timer is global: once started it is seen in any map it is
/// carried to. So it is the maps where a page that compiles starts it,
/// plus the ones a `Teleport` takes it to while it runs, until a page
/// stops it. Each page is walked **in order and without looking at its
/// branches**, following the map it is on: a start after a `Teleport` is
/// the destination's, and a `Teleport` after a stop does not carry it. A
/// page of a map the timer reaches starts with it running. A `CallEvent` to
/// a common event walks its commands in place.
///
/// It is an approximation, and **it can only fail by leaving a map without
/// digits**, which then do not show: which page runs depends on switches
/// nobody knows here. That is what `never` is for: the maps the game says
/// the timer never runs in although a page takes it there —`[graphics]
/// timer_never_runs_in`, each with its reason—. And `stays`, the maps it
/// does run in but the walk does not carry it out of —`[graphics]
/// timer_stays_in`—: their pages start with it stopped. A hub of the story
/// needs it, because the walk follows every cutscene that leaves it, and
/// from ABL's Paradise (108) that is the rest of the game.
///
/// **And the maps with a counter**, which draws a variable with the same
/// digits: a page that calls one of `counters` asks for them whether the
/// timer runs there or not. It is the call and not the bytecode because
/// the compiler's first answer does not know the counters.
pub fn timer_reach(
    maps: &[&GameMap],
    scan: &Value,
    common_events: &BTreeMap<i32, Vec<Command>>,
    never: &BTreeSet<i32>,
    stays: &BTreeSet<i32>,
    counters: &BTreeSet<i32>,
) -> Result<BTreeSet<i32>> {
    let in_rom: BTreeSet<i32> = maps.iter().map(|m| m.id).collect();
    let mut pages: Vec<(i32, &[Command])> = Vec::new();
    for map in maps {
        let compiling = compiler::compiling_pages(scan, map.id)?;
        for (e, event) in map.events.iter().enumerate() {
            for (k, page) in event.pages.iter().enumerate() {
                if compiling.contains(&(e as i64, k as i64)) {
                    pages.push((map.id, &page.commands));
                }
            }
        }
    }

    fn walk<'c>(
        commands: &'c [Command],
        common_events: &'c BTreeMap<i32, Vec<Command>>,
        depth: u32,
        out: &mut Vec<&'c Command>,
    ) {
        for cmd in commands {
            out.push(cmd);
            let p = &cmd.parameters;
            if cmd.code == CALL_EVENT && p.len() >= 2 && p[0] == CALL_COMMON && depth < 8 {
                if let Some(body) = common_events.get(&p[1]) {
                    walk(body, common_events, depth + 1, out);
                }
            }
        }
    }
    let walked: Vec<(i32, Vec<&Command>)> = pages
        .iter()
        .map(|(m, commands)| {
            let mut out = Vec::new();
            walk(commands, common_events, 0, &mut out);
            (*m, out)
        })
        .collect();

    let mut reach = BTreeSet::new();
    let mut counted = BTreeSet::new();
    let mut grew = true;
    while grew {
        grew = false;
        for (map_id, commands) in &walked {
            let mut here = *map_id;
            let mut running = reach.contains(map_id) && !stays.contains(map_id);
            for cmd in commands {
                let p = &cmd.parameters;
                if cmd.code == CALL_EVENT
                    && p.len() >= 2
                    && p[0] == CALL_COMMON
                    && counters.contains(&p[1])
                {
                    counted.insert(here);
                    continue;
                }
                if cmd.code == TELEPORT && !p.is_empty() {
                    here = p[0];
                } else if cmd.code == TIMER_OPERATION && !p.is_empty() {
                    if p[0] == TIMER_START {
                        running = true;
                    } else if p[0] == TIMER_STOP {
                        running = false;
                    } else {
                        continue;
                    }
                } else {
                    continue;
                }
                if never.contains(&here) {
                    running = false;
                }
                if running && in_rom.contains(&here) && !reach.contains(&here) {
                    reach.insert(here);
                    grew = true;
                }
            }
        }
    }
    Ok(reach
        .union(&counted.intersection(&in_rom).copied().collect())
        .copied()
        .collect())
}

/// A batch of consecutive `ChangePartyMembers`, as `(operation, actor)`.
pub type Batch = Vec<(i32, i32)>;

/// The `ChangePartyMembers` of the pages that compile, map by map, page by
/// page and in order: **in batches of consecutive commands**, and the
/// leader is looked at the end of each one. `ChangePartyMembers` stuck
/// together run in the same frame, so the hero is not drawn with the
/// mid-batch leader: looking after each command, a page that removes
/// everyone before adding someone back left three possible leaders more,
/// with their poses and colors in every map of the cartridge. A page
/// without any is not listed.
pub fn party_changes(maps: &[&GameMap], scan: &Value) -> Result<Vec<Vec<Vec<Batch>>>> {
    let mut out = Vec::new();
    for map in maps {
        let compiling = compiler::compiling_pages(scan, map.id)?;
        let mut pages: Vec<Vec<Batch>> = Vec::new();
        for (e, event) in map.events.iter().enumerate() {
            for (k, page) in event.pages.iter().enumerate() {
                if !compiling.contains(&(e as i64, k as i64)) {
                    continue;
                }
                let mut batches: Vec<Batch> = Vec::new();
                let mut open = false;
                for cmd in &page.commands {
                    match party_change(cmd) {
                        None => open = false,
                        Some(change) => {
                            if !open {
                                batches.push(Vec::new());
                                open = true;
                            }
                            batches.last_mut().unwrap().push(change);
                        }
                    }
                }
                if !batches.is_empty() {
                    pages.push(batches);
                }
            }
        }
        out.push(pages);
    }
    Ok(out)
}

/// The actors that can end up drawn as the hero in this ROM: the party it
/// starts with, plus the ones some `ChangePartyMembers` of a page that
/// compiles puts first. **The party is reset in each map**: the actor table
/// is per map, so the question is who can lead while that map is loaded,
/// and not what happened in the directory's previous maps.
///
/// Each map is played three ways, and every leader any of them leaves after
/// a batch counts: all its pages in file order on one party, as always;
/// **each page on its own** from the cartridge's party; and each page on
/// its own from an **empty party**, if some page, played on its own, ends
/// with nobody in it. The pages of a map's events are alternatives as often
/// as a sequence, and which one runs —and with which party the map was
/// entered— depends on switches that are not known here. Dooms 2 is both:
/// map 1 is a row of candidates, each one's page taking the narrator out
/// and putting its character in, and some take him out alone and teleport,
/// so the party arrives empty at the map where the story's hero joins.
/// Played only in file order, every candidate after the first went in
/// behind them, the hero who joined an empty party went in behind the
/// narrator, and none was in any map's actor table: they walked undrawn.
///
/// The empty start asks for a page that **ends** empty, and not a batch: a
/// page that empties the party and fills it again in the same run —ABL's
/// car chase— does not leave a map to be entered with nobody, and taking
/// it as one made every actor some page adds a leader, with a palette of
/// their own on each map that shows them as an event.
pub fn possible_leaders(changes: &[Vec<Vec<Batch>>], party: &[i32]) -> Vec<i32> {
    let play = |state: &mut PartyState, batch: &[(i32, i32)]| {
        for &(operation, actor) in batch {
            state.change_party(operation, actor);
        }
    };
    let ends_empty = |page: &[Batch]| {
        let mut state = PartyState::new(party);
        page.iter().for_each(|batch| play(&mut state, batch));
        state.leader().is_none()
    };
    let mut starts = vec![party.to_vec()];
    if changes.iter().flatten().any(|page| ends_empty(page)) {
        starts.push(Vec::new());
    }
    let mut actors = leaders_in_file_order(changes, party);
    let mut add = |state: &PartyState| {
        if let Some(leader) = state.leader() {
            if !actors.contains(&leader) {
                actors.push(leader);
            }
        }
    };
    for pages in changes {
        for start in &starts {
            for page in pages {
                let mut state = PartyState::new(start);
                for batch in page {
                    play(&mut state, batch);
                    add(&state);
                }
            }
        }
    }
    actors
}

/// The first of [`possible_leaders`]' three ways alone: each map's pages
/// in file order on one party, reset to `party` at each map. It is what
/// the parties the test pages start with are played with —see the
/// converter—: those parties are the tests', not the game's, and played
/// page by page or emptied they made leaders of actors the game never puts
/// first, with a palette of their own on every map that shows them.
pub fn leaders_in_file_order(changes: &[Vec<Vec<Batch>>], party: &[i32]) -> Vec<i32> {
    let mut actors: Vec<i32> = party.iter().take(1).copied().collect();
    for pages in changes {
        let mut state = PartyState::new(party);
        for batch in pages.iter().flatten() {
            for &(operation, actor) in batch {
                state.change_party(operation, actor);
            }
            if let Some(leader) = state.leader() {
                if !actors.contains(&leader) {
                    actors.push(leader);
                }
            }
        }
    }
    actors
}

/// The items that can be in the inventory with these maps in the ROM: the
/// ones some `ChangeItems` of any page gives, whether it compiles or not,
/// the ones some `OpenShop` sells, the equipment the `actors` start with
/// and the ones the test pages give. A superset: one item too many costs
/// its text in the cartridge, one too few is not seen in the list.
pub fn possible_items<'a>(
    maps: impl IntoIterator<Item = &'a GameMap>,
    actors: &[i32],
    db: &Database,
    extra: &[Command],
) -> Vec<i32> {
    let mut items = BTreeSet::new();
    for actor in actors {
        if let Some(a) = db.actors.get(actor) {
            let e = &a.initial_equipment;
            for i in [
                e.weapon_id,
                e.shield_id,
                e.armor_id,
                e.helmet_id,
                e.accessory_id,
            ] {
                if i != 0 {
                    items.insert(i);
                }
            }
        }
    }
    let mut sweep = |cmd: &Command| {
        let p = &cmd.parameters;
        if cmd.code == CHANGE_ITEMS && p.len() >= 5 && p[0] == 0 && p[1] == 0 {
            items.insert(p[2]);
        } else if cmd.code == OPEN_SHOP {
            items.extend(p.iter().skip(4).copied());
        }
    };
    for map in maps {
        map.all_commands().for_each(&mut sweep);
    }
    extra.iter().for_each(&mut sweep);
    // One the database does not have —deleted after it was used— is
    // nothing in RM2k: it has no name to carry.
    items
        .into_iter()
        .filter(|&i| {
            0 < i && (i as usize) < rm2k_snes_mapdata::engine::ITEMS_N && db.items.contains_key(&i)
        })
        .collect()
}

/// The items some enemy of these troops can drop —its `drop_id`—, so the
/// cartridge carries their name: the victory tells it and the menu's list
/// shows it. All the members, like the battle's tables.
pub fn drop_items(db: &Database, troops: &[i32]) -> BTreeSet<i32> {
    let mut out = BTreeSet::new();
    for n in troops {
        if let Some(troop) = db.troops.get(n) {
            for e in &troop.members {
                let drop = db.enemies.get(e).map_or(0, |e| e.drop_id);
                if 0 < drop
                    && (drop as usize) < rm2k_snes_mapdata::engine::ITEMS_N
                    && db.items.contains_key(&drop)
                {
                    out.insert(drop);
                }
            }
        }
    }
    out
}

/// The actors that can be in the party with these maps in the ROM: the
/// starting ones plus the ones any `ChangePartyMembers` of any page adds,
/// whether it compiles or not —the slots screen needs the face and the
/// name of whoever can show up in a saved game—. `party` can bring repeats
/// and they are counted once.
pub fn possible_members<'a>(
    maps: impl IntoIterator<Item = &'a GameMap>,
    party: &[i32],
    extra: &[Command],
) -> Vec<i32> {
    let mut actors: Vec<i32> = Vec::new();
    for a in party {
        if !actors.contains(a) {
            actors.push(*a);
        }
    }
    let mut sweep = |cmd: &Command| {
        if let Some((operation, actor)) = party_change(cmd) {
            if operation == PARTY_ADD && !actors.contains(&actor) {
                actors.push(actor);
            }
        }
    };
    for map in maps {
        map.all_commands().for_each(&mut sweep);
    }
    extra.iter().for_each(&mut sweep);
    actors.sort();
    actors
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::{Event, Page};
    use serde_json::json;

    fn cmd(code: i32, parameters: &[i32]) -> Command {
        Command {
            code,
            indent: 0,
            string: String::new(),
            parameters: parameters.to_vec(),
        }
    }

    fn page(commands: Vec<Command>) -> Page {
        Page {
            id: 1,
            character_name: String::new(),
            dump_name: String::new(),
            character_index: 0,
            direction: 2,
            pattern: 1,
            layer: 0,
            animation_type: 0,
            commands,
        }
    }

    fn map(id: i32, pages: Vec<Vec<Command>>) -> GameMap {
        GameMap {
            id,
            chipset_id: 1,
            width: 20,
            height: 15,
            events: pages
                .into_iter()
                .enumerate()
                .map(|(k, c)| Event {
                    id: k as i32 + 1,
                    x: 0,
                    y: 0,
                    pages: vec![page(c)],
                })
                .collect(),
            lower_layer: Vec::new(),
            upper_layer: Vec::new(),
            twins: Vec::new(),
        }
    }

    /// A scan where every page of these maps compiles.
    fn everything_compiles(maps: &[&GameMap]) -> Value {
        json!({"maps": maps.iter().map(|m| json!({
            "id": m.id,
            "compiled": m.events.iter().enumerate().map(|(e, _)| json!([e, 0, ""])).collect::<Vec<_>>(),
        })).collect::<Vec<_>>()})
    }

    fn party(op: i32, actor: i32) -> Command {
        cmd(CHANGE_PARTY_MEMBERS, &[op, PARTY_FIXED_ID, actor])
    }

    #[test]
    fn the_party_follows_rm2k_rules() {
        let mut state = PartyState::new(&[1, 2]);
        state.change_party(PARTY_ADD, 2);
        assert_eq!(
            state.party,
            [1, 2],
            "adding one who is there neither duplicates nor moves"
        );
        state.change_party(PARTY_REMOVE, 9);
        assert_eq!(state.party, [1, 2]);
        state.change_party(PARTY_REMOVE, 1);
        assert_eq!(state.leader(), Some(2));
        for actor in [3, 4, 5, 6] {
            state.change_party(PARTY_ADD, actor);
        }
        assert_eq!(state.party, [2, 3, 4, 5], "a full party takes nobody");
    }

    #[test]
    fn the_leader_is_looked_at_after_each_batch_and_the_party_resets_per_map() {
        // Removing everyone and adding someone back, in one batch, leaves no
        // leader in between; and map 2 starts again from the cartridge's
        // party, not from what map 1 left.
        let one = map(
            1,
            vec![vec![
                party(PARTY_REMOVE, 10),
                party(PARTY_ADD, 11),
                cmd(WAIT, &[1]),
                party(PARTY_ADD, 12),
            ]],
        );
        let two = map(2, vec![vec![party(PARTY_ADD, 13), party(PARTY_REMOVE, 10)]]);
        let maps = [&one, &two];
        let changes = party_changes(&maps, &everything_compiles(&maps)).unwrap();
        assert_eq!(
            changes[0],
            vec![vec![
                vec![(PARTY_REMOVE, 10), (PARTY_ADD, 11)],
                vec![(PARTY_ADD, 12)]
            ]]
        );
        assert_eq!(possible_leaders(&changes, &[10]), [10, 11, 13]);
    }

    #[test]
    fn each_choice_of_a_map_and_a_party_emptied_elsewhere_bring_their_leader() {
        // Dooms 2's map 1: Will (5) tells the story, and each candidate is an
        // event whose page takes him out and puts its character in. Pages of
        // different events are alternatives, not a sequence: Bryan (3) leads
        // after his own page, even if Jonathan's (7) ran first in the file.
        // And Bob's (2) takes Will out alone and teleports: the party arrives
        // empty at map 3, where Bob joins and leads.
        let one = map(
            1,
            vec![
                vec![party(PARTY_REMOVE, 5), party(PARTY_ADD, 7)],
                vec![party(PARTY_REMOVE, 5), party(PARTY_ADD, 3)],
                vec![party(PARTY_REMOVE, 5)],
            ],
        );
        let three = map(3, vec![vec![party(PARTY_ADD, 2)]]);
        let maps = [&one, &three];
        let changes = party_changes(&maps, &everything_compiles(&maps)).unwrap();
        assert_eq!(possible_leaders(&changes, &[5]), [5, 7, 3, 2]);
        // Without a page that ends with the party empty, an actor who joins
        // goes behind the one leading: the empty party is not supposed. Not
        // even if a page empties it and fills it again, like ABL's car
        // chase.
        let three_alone = [&three];
        let changes = party_changes(&three_alone, &everything_compiles(&three_alone)).unwrap();
        assert_eq!(possible_leaders(&changes, &[5]), [5]);
        let chase = map(
            4,
            vec![
                vec![
                    party(PARTY_REMOVE, 5),
                    cmd(WAIT, &[1]),
                    party(PARTY_ADD, 20),
                ],
                vec![party(PARTY_ADD, 16)],
            ],
        );
        let maps = [&chase];
        let changes = party_changes(&maps, &everything_compiles(&maps)).unwrap();
        assert_eq!(possible_leaders(&changes, &[5]), [5, 20]);
    }

    #[test]
    fn a_page_that_does_not_compile_adds_no_leader_but_adds_a_member() {
        let one = map(1, vec![vec![party(PARTY_REMOVE, 10), party(PARTY_ADD, 11)]]);
        let scan = json!({"maps": [{"id": 1, "compiled": []}]});
        let changes = party_changes(&[&one], &scan).unwrap();
        assert_eq!(possible_leaders(&changes, &[10]), [10]);
        // The slots screen counts every page, and a repeat once.
        assert_eq!(possible_members([&one], &[10, 10], &[]), [10, 11]);
    }

    #[test]
    fn rain_and_items_are_swept_over_every_page_and_the_test_pages() {
        let one = map(
            1,
            vec![vec![
                cmd(CHANGE_ITEMS, &[0, 0, 7, 0, 1]),
                cmd(OPEN_SHOP, &[0, 0, 0, 0, 3, 450, 451]),
            ]],
        );
        assert!(!has_rain([&one], &[]));
        assert!(has_rain(
            [&one],
            &[cmd(WEATHER_EFFECTS, &[WEATHER_RAIN, 2])]
        ));
        // 451 is past the inventory, which goes up to `ITEMS_N`; and 5 is
        // not in the database —RM2k shows nothing for it—, like the weapon
        // an actor starts with in a game that deleted it.
        let mut db = Database::default();
        for i in [3, 7, 9, 450, 451] {
            db.items.insert(i, Default::default());
        }
        db.actors.insert(1, Default::default());
        db.actors.get_mut(&1).unwrap().initial_equipment.weapon_id = 5;
        assert_eq!(
            possible_items([&one], &[1], &db, &[cmd(CHANGE_ITEMS, &[0, 0, 9, 0, 1])]),
            [3, 7, 9, 450]
        );
    }

    #[test]
    fn the_timer_reaches_the_maps_a_teleport_takes_it_to_until_it_stops() {
        // Map 1 starts it and goes to 2; 2 goes to 3 and stops it there, so
        // 3 is reached and 4 is not; 3 starts it again and goes to 5, which
        // the game says never runs it.
        let one = map(
            1,
            vec![vec![
                cmd(TIMER_OPERATION, &[TIMER_START]),
                cmd(TELEPORT, &[2, 0, 0]),
            ]],
        );
        let two = map(
            2,
            vec![vec![
                cmd(TELEPORT, &[3, 0, 0]),
                cmd(TIMER_OPERATION, &[TIMER_STOP]),
                cmd(TELEPORT, &[4, 0, 0]),
            ]],
        );
        let three = map(
            3,
            vec![vec![
                cmd(TIMER_OPERATION, &[TIMER_START]),
                cmd(TELEPORT, &[5, 0, 0]),
            ]],
        );
        let four = map(4, vec![]);
        let five = map(5, vec![]);
        let maps = [&one, &two, &three, &four, &five];
        let scan = everything_compiles(&maps);
        let reach = timer_reach(
            &maps,
            &scan,
            &BTreeMap::new(),
            &BTreeSet::from([5]),
            &BTreeSet::new(),
            &BTreeSet::new(),
        )
        .unwrap();
        assert_eq!(reach, BTreeSet::from([1, 2, 3]));
    }

    #[test]
    fn a_map_the_timer_stays_in_is_reached_and_not_left() {
        // Map 1 starts it and goes to 2, a hub: 2 is reached, and its page
        // that goes on to 3 does not carry it, unless it starts it itself,
        // as the one that goes to 4 does.
        let one = map(
            1,
            vec![vec![
                cmd(TIMER_OPERATION, &[TIMER_START]),
                cmd(TELEPORT, &[2, 0, 0]),
            ]],
        );
        let two = map(
            2,
            vec![
                vec![cmd(TELEPORT, &[3, 0, 0])],
                vec![
                    cmd(TIMER_OPERATION, &[TIMER_START]),
                    cmd(TELEPORT, &[4, 0, 0]),
                ],
            ],
        );
        let (three, four) = (map(3, vec![]), map(4, vec![]));
        let maps = [&one, &two, &three, &four];
        let scan = everything_compiles(&maps);
        let reach = timer_reach(
            &maps,
            &scan,
            &BTreeMap::new(),
            &BTreeSet::new(),
            &BTreeSet::from([2]),
            &BTreeSet::new(),
        )
        .unwrap();
        assert_eq!(reach, BTreeSet::from([1, 2, 4]));
    }

    #[test]
    fn a_counter_asks_for_the_digits_where_it_is_called() {
        let one = map(1, vec![vec![cmd(CALL_EVENT, &[CALL_COMMON, 7])]]);
        let maps = [&one];
        let reach = timer_reach(
            &maps,
            &everything_compiles(&maps),
            &BTreeMap::new(),
            &BTreeSet::new(),
            &BTreeSet::new(),
            &BTreeSet::from([7]),
        )
        .unwrap();
        assert_eq!(reach, BTreeSet::from([1]));
    }
}
