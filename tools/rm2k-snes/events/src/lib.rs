//! An RPG Maker 2000 game's event pages, compiled to the bytecode a Super
//! Nintendo cartridge runs: the pages of each map, the troops' pages, the
//! test pages a cartridge carries, and everything the compiler numbers
//! while it goes —the text block, the songs and effects, the graphics, the
//! troops—.
//!
//! It reads the game from a Ditto dump —see [`game`]— and what the
//! cartridge decided from a [`Request`]. It compiles in two calls, because
//! the caller needs the first answer to build the maps and the maps to ask
//! for the second:
//!
//! * [`scan`]: the indices of the whole game —variable slots, skill bits,
//!   the graphics actors can be given—, which pages of each map compile
//!   and to what, each on its own —for the party—, and each map's pages
//!   compiled without songs —for who walks and which graphics a route
//!   changes to—;
//! * [`compile()`]: the real thing, with everything.
//!
//! The opcodes' numbers are not here: they come from the protocol's
//! declaration, `events.toml`, generated into [`opcodes`].

pub mod codes;
pub mod compile;
pub mod fail;
pub mod game;
pub mod indices;
pub mod messages;
#[rustfmt::skip]
pub mod opcodes;
pub mod pages;
pub mod registry;
pub mod route;
pub mod troops;

pub use fail::{Bad, Result};
pub use game::Game;

use crate::codes::*;
use crate::compile::{
    compile_page, encounter_backdrop, encounter_troop, Ctx, Indices, SoundSettings,
};
use crate::fail::Stop;
use crate::game::{Command, Event, Map, Patches};
use crate::messages::{Messages, Window};
use crate::pages::{hex, map_pages, MapEvents, SubstitutionTable, Substitutions};
use crate::registry::{Graphics, Package, Picture, Songs, Troops};
use crate::troops::TroopPages;
use serde_json::{json, Map as JsonMap, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::{Path, PathBuf};
use std::rc::Rc;

/// The file the answer is written to.
pub const ANSWER_FILE: &str = "events.json";

/// What the cartridge decided, and what the project changed on top of the
/// dump.
#[derive(Debug, Clone, Default)]
pub struct Request {
    pub patches: Patches,
    pub window: Option<Window>,
    /// The cartridge's maps, in its order.
    pub maps: Vec<i32>,
    /// The commands of every test page, one after the other: they name
    /// variables, pairs and graphics too, and their texts go first.
    pub test_commands: Vec<Command>,
    /// Variables no page names that need a slot anyway.
    pub extra_variables: BTreeSet<i32>,
    /// The map the test pages boot in, which carries an event without pages
    /// at index 0 so that they run before the game's.
    pub test_event_map: Option<i32>,
    // What only `compile` reads.
    pub substitutions: BTreeMap<i32, SubstitutionTable>,
    pub picture: Option<Picture>,
    pub sound: SoundSettings,
    /// Each test page and the map it runs in, compiled with that map's
    /// context and as its event 0. What the caller puts in front of it —the
    /// switch a test page turns itself off with— comes in the commands.
    pub cases: Vec<(i32, Vec<Command>)>,
    /// Graphics the test pages ask for in the maps where they run.
    pub test_graphics: BTreeMap<i32, Vec<(String, i32)>>,
    /// How many bytes at a time `OP_MESSAGE`'s offset counts.
    pub messages_step: usize,
    /// The troops of the random encounters.
    pub encounter_troops: Vec<i32>,
}

fn field<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Value> {
    data.get(name)
        .ok_or_else(|| Bad::answer(format!("{whose}: no `{name}`")))
}

fn list<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Vec<Value>> {
    field(data, name, whose)?
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not a list")))
}

fn int(v: &Value, whose: &str) -> Result<i64> {
    v.as_i64()
        .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a whole number")))
}

fn text(v: &Value, whose: &str) -> Result<String> {
    v.as_str()
        .map(str::to_string)
        .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a text")))
}

fn strings(v: &Value, whose: &str) -> Result<Vec<String>> {
    v.as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a list")))?
        .iter()
        .map(|s| text(s, whose))
        .collect()
}

/// A command as the caller writes it: `{"code", "indent", "string",
/// "parameters"}`.
fn command(v: &Value, whose: &str) -> Result<Command> {
    Ok(Command {
        code: int(field(v, "code", whose)?, whose)? as i32,
        indent: int(field(v, "indent", whose)?, whose)? as i32,
        string: text(field(v, "string", whose)?, whose)?,
        parameters: list(v, "parameters", whose)?
            .iter()
            .map(|p| int(p, whose).map(|x| x as i32))
            .collect::<Result<_>>()?,
    })
}

fn commands(v: &Value, whose: &str) -> Result<Vec<Command>> {
    v.as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: the commands are not a list")))?
        .iter()
        .map(|c| command(c, whose))
        .collect()
}

fn pair(v: &Value, whose: &str) -> Result<(String, i32)> {
    let a = v
        .as_array()
        .filter(|a| a.len() == 2)
        .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a pair")))?;
    Ok((text(&a[0], whose)?, int(&a[1], whose)? as i32))
}

fn by_map<T>(
    v: &Value,
    whose: &str,
    each: impl Fn(&Value) -> Result<T>,
) -> Result<BTreeMap<i32, T>> {
    let obj = v
        .as_object()
        .ok_or_else(|| Bad::answer(format!("{whose}: not an object")))?;
    obj.iter()
        .map(|(k, v)| {
            let id = k
                .parse::<i32>()
                .map_err(|_| Bad::answer(format!("{whose}: {k} is not a map")))?;
            Ok((id, each(v)?))
        })
        .collect()
}

impl Request {
    /// A request file. Every field is required; the ones only `compile`
    /// reads can be left out of a `scan`'s.
    pub fn read(path: &Path) -> Result<Request> {
        let text_ = std::fs::read_to_string(path)
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        let whose = path.display().to_string();
        let data: Value =
            serde_json::from_str(&text_).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        Request::from_json(&data, &whose)
    }

    pub fn from_json(data: &Value, whose: &str) -> Result<Request> {
        let mut r = Request {
            messages_step: 1,
            ..Default::default()
        };
        r.patches.map_files = by_map(field(data, "map_files", whose)?, whose, |v| {
            Ok(PathBuf::from(text(v, whose)?))
        })?;
        for b in list(data, "boxes", whose)? {
            let from = strings(field(b, "from", whose)?, whose)?;
            let to = field(b, "to", whose)?
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: a box's `to` is not a list")))?
                .iter()
                .map(|f| strings(f, whose))
                .collect::<Result<_>>()?;
            r.patches.boxes.insert(from, to);
        }
        for n in list(data, "names", whose)? {
            let a = n
                .as_array()
                .filter(|a| a.len() == 4)
                .ok_or_else(|| Bad::answer(format!("{whose}: a name is {n}")))?;
            r.patches.names.insert(
                (
                    int(&a[0], whose)? as i32,
                    int(&a[1], whose)? as i32,
                    int(&a[2], whose)? as i32,
                ),
                text(&a[3], whose)?,
            );
        }
        let w = field(data, "window", whose)?;
        r.window = Some(Window {
            columns: int(field(w, "columns", whose)?, whose)? as usize,
            lines: int(field(w, "lines", whose)?, whose)? as usize,
        });
        r.maps = list(data, "maps", whose)?
            .iter()
            .map(|m| int(m, whose).map(|x| x as i32))
            .collect::<Result<_>>()?;
        r.test_commands = commands(field(data, "test_commands", whose)?, whose)?;
        r.extra_variables = list(data, "extra_variables", whose)?
            .iter()
            .map(|m| int(m, whose).map(|x| x as i32))
            .collect::<Result<_>>()?;
        let t = field(data, "test_event_map", whose)?;
        r.test_event_map = if t.is_null() {
            None
        } else {
            Some(int(t, whose)? as i32)
        };

        if let Some(subs) = data.get("substitutions") {
            r.substitutions = by_map(subs, whose, |v| {
                let mut table = HashMap::new();
                for s in v
                    .as_array()
                    .ok_or_else(|| Bad::answer(format!("{whose}: substitutions")))?
                {
                    let upper = field(s, "upper", whose)?.as_bool().unwrap_or(false);
                    let old = int(field(s, "old", whose)?, whose)?;
                    let new = int(field(s, "new", whose)?, whose)?;
                    let pairs = field(s, "pairs", whose)?;
                    let pairs = if pairs.is_null() {
                        None
                    } else {
                        Some(
                            pairs
                                .as_array()
                                .unwrap_or(&vec![])
                                .iter()
                                .map(|p| {
                                    let p = p
                                        .as_array()
                                        .filter(|p| p.len() == 2)
                                        .ok_or_else(|| Bad::answer(format!("{whose}: a pair")))?;
                                    Ok((int(&p[0], whose)?, int(&p[1], whose)?))
                                })
                                .collect::<Result<_>>()?,
                        )
                    };
                    table.insert((upper, old, new), pairs);
                }
                Ok(table)
            })?;
        }
        if let Some(counters) = data.get("counters") {
            for c in counters
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: `counters` is not a list")))?
            {
                r.patches.counters.insert(
                    int(field(c, "common_event", whose)?, whose)? as i32,
                    int(field(c, "variable", whose)?, whose)? as i32,
                );
            }
        }
        if let Some(p) = data.get("picture") {
            if !p.is_null() {
                r.picture = Some(Picture {
                    name: text(field(p, "name", whose)?, whose)?,
                    number: int(field(p, "number", whose)?, whose)? as i32,
                    x: int(field(p, "x", whose)?, whose)? as i32,
                    y: int(field(p, "y", whose)?, whose)? as i32,
                });
            }
        }
        if let Some(s) = data.get("sound_effects") {
            for a in list(s, "per_map", whose)? {
                r.sound.per_map.push((
                    text(field(a, "effect", whose)?, whose)?,
                    int(field(a, "map", whose)?, whose)?,
                    text(field(a, "sample", whose)?, whose)?,
                ));
            }
            for m in list(s, "route_effects_left_out", whose)? {
                let effects = field(m, "effects", whose)?;
                let which = if effects.as_str() == Some("all") {
                    None
                } else {
                    Some(strings(effects, whose)?.into_iter().collect())
                };
                r.sound
                    .route_left_out
                    .push((int(field(m, "map", whose)?, whose)?, which));
            }
            r.sound.troop_in_package =
                strings(field(s, "troop_effects_in_package", whose)?, whose)?
                    .into_iter()
                    .collect();
        }
        if let Some(cases) = data.get("cases") {
            for c in cases
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: `cases` is not a list")))?
            {
                r.cases.push((
                    int(field(c, "map", whose)?, whose)? as i32,
                    commands(field(c, "commands", whose)?, whose)?,
                ));
            }
        }
        if let Some(g) = data.get("test_graphics") {
            r.test_graphics = by_map(g, whose, |v| {
                v.as_array()
                    .ok_or_else(|| Bad::answer(format!("{whose}: test_graphics")))?
                    .iter()
                    .map(|p| pair(p, whose))
                    .collect()
            })?;
        }
        if let Some(s) = data.get("messages_step") {
            r.messages_step = int(s, whose)? as usize;
        }
        if let Some(t) = data.get("encounter_troops") {
            r.encounter_troops = t
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: encounter_troops")))?
                .iter()
                .map(|m| int(m, whose).map(|x| x as i32))
                .collect::<Result<_>>()?;
        }
        Ok(r)
    }

    fn window(&self) -> Window {
        self.window.unwrap()
    }
}

/// The map with an event without pages at index 0, if it is the one the
/// test pages boot in: it takes that index so that everything that numbers
/// events numbers the same.
fn with_test_event(mut map: Map, request: &Request) -> Map {
    if request.test_event_map == Some(map.id) {
        map.events.insert(
            0,
            Event {
                id: 0,
                pages: vec![],
                starting: None,
            },
        );
    }
    map
}

/// The indices, as the caller keeps them.
fn indices_json(indices: &Indices, associations: &[(String, i32)]) -> JsonMap<String, Value> {
    let mut out = JsonMap::new();
    out.insert(
        "variables".into(),
        json!(indices
            .variables
            .iter()
            .map(|(v, s)| json!([v, s]))
            .collect::<Vec<_>>()),
    );
    out.insert(
        "skills".into(),
        json!(indices
            .skills
            .iter()
            .map(|((a, h), s)| json!([a, h, s]))
            .collect::<Vec<_>>()),
    );
    out.insert("associations".into(), json!(associations));
    out.insert(
        "party_common_events".into(),
        json!(indices
            .party_common_events
            .iter()
            .map(|(sw, n)| json!([sw, n]))
            .collect::<Vec<_>>()),
    );
    out
}

/// The indices, the graphics actors can be given, and the cartridge's maps.
type Prepared = (Indices, Vec<(String, i32)>, Vec<Map>);

fn prepare(game: &Game, request: &Request) -> Result<Prepared> {
    let every = indices::every_map(game)?;
    let mut extra_variables = request.extra_variables.clone();
    extra_variables.extend(indices::command_variables(&request.test_commands));
    let extra_pairs = indices::command_skill_pairs(&request.test_commands);
    let indices = indices::build(game, &every, &extra_variables, &extra_pairs)?;
    let by_id: HashMap<i32, &Map> = every.iter().map(|m| (m.id, m)).collect();
    let maps = request
        .maps
        .iter()
        .map(|&id| match by_id.get(&id) {
            Some(m) => Ok((*m).clone()),
            None => game.map(id),
        })
        .collect::<Result<Vec<_>>>()?;
    let associations = indices::associations(&maps, &request.test_commands);
    Ok((indices, associations, maps))
}

/// The first call: the indices, which pages of each map compile, and each
/// map's pages compiled without songs, pictures or troops.
pub fn scan(game: &Game, request: &Request) -> Result<Value> {
    let (indices, associations, maps) = prepare(game, request)?;
    let order: HashMap<i64, usize> = request
        .maps
        .iter()
        .enumerate()
        .map(|(i, &m)| (m as i64, i))
        .collect();
    let map_index = |m: i64| order.get(&m).copied();
    let sound = SoundSettings::default();
    let mut out = Vec::new();
    for map in &maps {
        // Which pages compile, and to what, each on its own: with a text
        // block, songs and graphics of its own. Every page, whatever
        // triggers it: it is what the party's scan asks, and what a test
        // asks about one page of the game.
        let me = MapEvents::new(map, None);
        let mut compiled = Vec::new();
        for (e, event) in map.events.iter().enumerate() {
            for (p, page) in event.pages.iter().enumerate() {
                let mut messages = Messages::new(1, request.window());
                let mut songs = Songs::default();
                let mut graphics = Graphics::default();
                let mut ctx = Ctx {
                    game,
                    indices: &indices,
                    sound: &sound,
                    map_index: &map_index,
                    messages: Some(&mut messages),
                    songs: Some(&mut songs),
                    graphics: Some(&mut graphics),
                    picture: None,
                    troops: None,
                };
                if let Some(code) =
                    compile_page(&mut ctx, &page.commands, Some(me.for_event(event.id)), 0, 0)?
                {
                    compiled.push(json!([e, p, hex(&code)]));
                }
            }
        }
        // The pages as the map has them, with a text block of its own and
        // without songs: who walks and which graphics a route changes to.
        let map = with_test_event(map.clone(), request);
        let me = MapEvents::new(&map, None);
        let mut messages = Messages::new(1, request.window());
        let mut graphics = Graphics::new(&associations);
        let mut ctx = Ctx {
            game,
            indices: &indices,
            sound: &sound,
            map_index: &map_index,
            messages: Some(&mut messages),
            songs: None,
            graphics: Some(&mut graphics),
            picture: None,
            troops: None,
        };
        let pages = map_pages(&mut ctx, &map, &me)?;
        out.push(json!({
            "id": map.id,
            "compiled": compiled,
            "pages": pages,
            "graphics": graphics.pairs,
        }));
    }
    let mut answer = indices_json(&indices, &associations);
    answer.insert("maps".into(), json!(out));
    Ok(Value::Object(answer))
}

/// The second call: every page of the cartridge, compiled with everything.
///
/// **Twice**, and the first one only to gather the texts. The pair table of
/// the text block —see `messages::Pairs`— is chosen over the boxes that go
/// into the cartridge, and which ones those are is known only after
/// compiling every page: the ones that do not compile take theirs back. But
/// the offset of each box is already written into the bytecode when it is
/// compiled, and with pairs every box measures something else. So the first
/// pass gathers, and the second one compiles with the table: the same pages
/// compile in both, because whether one compiles never depends on its texts'
/// bytes.
pub fn compile(game: &Game, request: &Request) -> Result<Value> {
    let window = request.window();
    let (_, gathered) = compile_pass(
        game,
        request,
        Messages::measuring(request.messages_step, window),
    )?;
    let pairs = gathered.choose_pairs()?;
    let (answer, _) = compile_pass(
        game,
        request,
        Messages::with_pairs(request.messages_step, window, pairs),
    )?;
    Ok(answer)
}

/// The same, with one byte per letter: what the compiler answered before
/// there were pairs. No cartridge uses it; the tests compare against it,
/// because the hashes of `tests/python.rs` are of an answer without pairs.
pub fn compile_without_pairs(game: &Game, request: &Request) -> Result<Value> {
    let messages = Messages::new(request.messages_step, request.window());
    Ok(compile_pass(game, request, messages)?.0)
}

fn compile_pass(
    game: &Game,
    request: &Request,
    mut messages: Messages,
) -> Result<(Value, Messages)> {
    let (indices, associations, maps) = prepare(game, request)?;
    let order: HashMap<i64, usize> = request
        .maps
        .iter()
        .enumerate()
        .map(|(i, &m)| (m as i64, i))
        .collect();
    let map_index = |m: i64| order.get(&m).copied();
    let window = request.window();
    let mut songs = Songs::default();
    let mut troops = Troops::default();
    let picture = request.picture.as_ref();

    // The test pages' texts go first, so their offsets depend on nothing.
    let tc = &request.test_commands;
    let mut i = 0;
    while i < tc.len() {
        let mut j = i + 1;
        if tc[i].code == SHOW_MESSAGE {
            while j < tc.len() && tc[j].code == SHOW_MESSAGE_2 {
                j += 1;
            }
            let lines: Vec<String> = tc[i..j].iter().map(|c| c.string.clone()).collect();
            match messages.add(&lines) {
                Ok(_) => {}
                Err(Stop::Fatal(b)) => return Err(b),
                Err(Stop::Cannot) => {
                    return Err(Bad::answer(format!(
                        "a test page's text box does not compile: {lines:?}"
                    )))
                }
            }
        }
        i = j;
    }

    let mut maps_out = Vec::new();
    let mut cases_out: Vec<Option<String>> = vec![None; request.cases.len()];
    for (k, map) in maps.into_iter().enumerate() {
        let map = with_test_event(map, request);
        let subs = Rc::new(Substitutions {
            table: request
                .substitutions
                .get(&map.id)
                .cloned()
                .unwrap_or_default(),
            ..Default::default()
        });
        let me = MapEvents::new(&map, Some(subs.clone()));
        let mut graphics = Graphics::new(&associations);
        songs.current = Some(Package::Map(k));
        let pages = {
            let mut ctx = Ctx {
                game,
                indices: &indices,
                sound: &request.sound,
                map_index: &map_index,
                messages: Some(&mut messages),
                songs: Some(&mut songs),
                graphics: Some(&mut graphics),
                picture,
                troops: Some(&mut troops),
            };
            map_pages(&mut ctx, &map, &me)?
        };
        songs.current = None;
        for (charset, index) in request.test_graphics.get(&map.id).into_iter().flatten() {
            graphics.index(charset, *index);
        }
        // The table the map's pages number against, which the caller checks
        // against the one it built the sprite bank with. A test page that
        // runs here numbers after it.
        let numbered = graphics.pairs.clone();
        // The test pages that run here, with this map's context.
        for (c, (run_map, case)) in request.cases.iter().enumerate() {
            if *run_map != map.id {
                continue;
            }
            let mut ctx = Ctx {
                game,
                indices: &indices,
                sound: &request.sound,
                map_index: &map_index,
                messages: Some(&mut messages),
                songs: Some(&mut songs),
                graphics: Some(&mut graphics),
                picture,
                troops: None,
            };
            let code = compile_page(
                &mut ctx,
                case,
                Some(MapEvents::new(&map, Some(subs.clone())).for_event(0)),
                0,
                0,
            )?;
            // One that does not compile is null: what to do about it is the
            // caller's.
            cases_out[c] = code.map(|code| hex(&code));
        }
        // The debts: what the automatic pages that compile accept without
        // doing. With the text block and nothing else.
        let mut debts = BTreeSet::new();
        for event in &map.events {
            for page in &event.pages {
                if page.trigger != TRIGGER_AUTOSTART {
                    continue;
                }
                let mut ctx = Ctx {
                    game,
                    indices: &indices,
                    sound: &request.sound,
                    map_index: &map_index,
                    messages: Some(&mut messages),
                    songs: None,
                    graphics: None,
                    picture: None,
                    troops: None,
                };
                if compile_page(&mut ctx, &page.commands, None, 0, 0)?.is_none() {
                    continue;
                }
                debts.extend(compile::page_debts(game, &page.commands, picture)?);
            }
        }
        let asked: Vec<Value> = subs
            .asked
            .borrow()
            .iter()
            .map(|(u, o, n)| json!([u, o, n]))
            .collect();
        maps_out.push(json!({
            "id": map.id,
            "pages": pages,
            "graphics": numbered,
            "debts": debts,
            "substitutions": asked,
        }));
    }

    // The troops: the maps' battles, the random encounters' and the test
    // pages', in that order.
    for &t in &request.encounter_troops {
        troops.request(t, None);
    }
    for cmd in &request.test_commands {
        if cmd.code == ENEMY_ENCOUNTER {
            let troop = encounter_troop(cmd)
                .map_err(|_| Bad::answer("a test page's EnemyEncounter does not compile"))?;
            troops.request(troop as i32, encounter_backdrop(cmd));
        }
    }
    let mut ctx = Ctx {
        game,
        indices: &indices,
        sound: &request.sound,
        map_index: &|_| None,
        messages: None,
        songs: Some(&mut songs),
        graphics: None,
        picture: None,
        troops: None,
    };
    let battle_audio = if troops.ids.is_empty() {
        None
    } else {
        compile::battle_audio(&mut ctx)
    };
    let mut troop_pages = TroopPages::new(Messages::new(1, window));
    for &number in &troops.ids {
        if let Some(pages) = game.troops.get(&number) {
            troop_pages.compile(&mut ctx, number, pages)?;
        }
    }
    // The equipment common events, which the ROM runs when the menu closes:
    // each body as a loose page, with its `OP_DONE`. It needs no map nor
    // texts —it does not use them—, and if it does not compile it is a
    // compiler bug: `party_common_events` only lets through what always
    // compiles.
    let mut party = Vec::new();
    for (&switch, &number) in &indices.party_common_events {
        let body = game.common_events[&number].commands.clone();
        let mut ctx = Ctx {
            game,
            indices: &indices,
            sound: &request.sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            picture: None,
            troops: None,
        };
        let Some(code) = compile_page(&mut ctx, &body, None, 0, 0)? else {
            return Err(Bad::answer(format!(
                "common event {number} is an equipment one and does not compile"
            )));
        };
        party.push(json!([switch, number, hex(&code)]));
    }

    let mut answer = indices_json(&indices, &associations);
    answer.insert("maps".into(), json!(maps_out));
    answer.insert("cases".into(), json!(cases_out));
    answer.insert(
        "messages".into(),
        json!({
            "data": hex(&messages.bytes()),
            "count": messages.count(),
            "pairs": hex(&messages.pairs.bytes()),
            "pair_first": messages::PAIR_FIRST,
        }),
    );
    answer.insert("songs".into(), songs.to_json());
    answer.insert(
        "troops".into(),
        json!({
            "ids": troops.ids,
            "backdrops": troops.backdrops.iter().map(|(n, b)| json!([n, match b {
                registry::Backdrop::Named(s) => json!(s),
                registry::Backdrop::Place => Value::Null,
            }])).collect::<Vec<_>>(),
        }),
    );
    answer.insert("troop_pages".into(), troop_pages.to_json());
    answer.insert(
        "battle_audio".into(),
        match battle_audio {
            None => Value::Null,
            Some(a) => Value::Object(a.into_iter().map(|(k, v)| (k, json!(v))).collect()),
        },
    );
    answer.insert("party_common_events".into(), json!(party));
    Ok((Value::Object(answer), messages))
}

/// Writes the answer into `dir`, which is created if it is not there.
pub fn write(answer: &Value, dir: &Path) -> Result<()> {
    let io = |path: &Path, e: std::io::Error| Bad::usage(format!("{}: {e}", path.display()));
    std::fs::create_dir_all(dir).map_err(|e| io(dir, e))?;
    let path = dir.join(ANSWER_FILE);
    std::fs::write(&path, serde_json::to_string(answer).unwrap() + "\n").map_err(|e| io(&path, e))
}
