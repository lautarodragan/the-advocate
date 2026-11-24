//! The event compiler, which is `rm2k-snes-events`: what goes into its two
//! requests and what comes back.
//!
//! It reads the game from the dump itself. What it is told is what the
//! dump does not say: the cartridge's maps and test pages, and what the
//! project changed on top of the dump —the forks' files, the text boxes
//! rebuilt for the console's window (`rm2k-snes-screens boxes`), the names
//! the port gives some graphics, how a `TileSubstitution` translates to the
//! map's blocks, which pictures each map carries, the sound effects decided
//! by ear—. See the crate's README.
//!
//! Two calls, because the converter needs the first answer to build the
//! maps and the maps to ask for the second: `scan` before converting any
//! map, and `compile` after.

use crate::fail::{Result, Stop};
use crate::font::FontChoice;
use crate::game::{Command, Game, GameMap};
use crate::screens;
use crate::settings::Settings;
use crate::stage;
use rm2k_snes_events::answer::{Compiled, Indices, Scan};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;

/// The compiler's two calls: see the module's comment.
const SCAN: stage::Stage = stage::Stage {
    binary: "rm2k-snes-events",
    command: "scan",
};
const COMPILE: stage::Stage = stage::Stage {
    binary: "rm2k-snes-events",
    command: "compile",
};

/// How many lines of text fit in the message window: the cartridge's
/// window, which the compiler cuts the boxes for and the screens draw.
pub const LINES: u32 = 4;

/// The switch the harness's test pages turn on to stop repeating, and the
/// variable it writes the case number into: conventions of the test
/// harness, which every test page of a cartridge carries. The switch is the
/// one they ask for: a game that names it gets the first above it that it
/// does not name, which the scan answers —see `test_switch` in
/// `rm2k-snes-events`— and the cartridge says as `TEST_SWITCH`.
pub const TEST_SWITCH: i32 = 1023;
pub const CASE_VARIABLE: i32 = 1000;
/// The `>=` of RM2k's page conditions.
pub const COMPARE_AT_LEAST: i32 = 1;

/// `ControlSwitches`' single switch, and its "on".
const SWITCH_SINGLE: i32 = 0;
const SWITCH_ON: i32 = 0;

/// A command as the requests carry it.
pub fn command(c: &Command) -> Value {
    json!({"code": c.code, "indent": c.indent, "string": c.string, "parameters": c.parameters})
}

fn commands(list: &[Command]) -> Value {
    Value::Array(list.iter().map(command).collect())
}

/// The maps read from the project's files and not from the dump, by map
/// number as text.
pub fn map_files(game: &Game) -> Value {
    let mut out = Map::new();
    for (m, path) in game.forks.map_files() {
        out.insert(m.to_string(), json!(path.to_string_lossy()));
    }
    Value::Object(out)
}

/// The ChipSets the project adds to the database, by the file each one is
/// in.
pub fn chipset_files(game: &Game) -> Value {
    let mut out = Map::new();
    for (m, (path, _)) in &game.forks.chipsets {
        out.insert(m.to_string(), json!(path.to_string_lossy()));
    }
    Value::Object(out)
}

/// The graphics the port calls by another name than the dump's, in these
/// maps: `[map, event, page, name]`.
pub fn names<'a>(maps: impl IntoIterator<Item = &'a GameMap>) -> Vec<Value> {
    let mut out = Vec::new();
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                if page.character_name != page.dump_name {
                    out.push(json!([map.id, event.id, page.id, page.character_name]));
                }
            }
        }
    }
    out
}

/// The common events the project declares as the display of a variable in
/// two digit pictures: `[events] counters`, which the compiler turns into
/// one opcode each instead of their bodies.
pub fn counters(settings: &Settings) -> Result<Vec<Counter>> {
    settings
        .list(&["events", "counters"])?
        .iter()
        .map(|c| Counter::deserialize(c).map_err(|e| Stop::new(format!("[events] counters: {e}"))))
        .collect()
}

/// One of `[events] counters`: the common event, and the variable its
/// digits show. The compile requests take them as they are.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Counter {
    pub common_event: i32,
    pub variable: i32,
}

/// What the compiler is asked for and keeps: the boxes and the battle's
/// window are asked once.
pub struct Compiler<'a> {
    pub game: &'a Game,
    pub settings: &'a Settings<'a>,
    /// What the custom menus ask of the events, one entry per menu: see
    /// `CustomMenu::hooks`.
    menus: Value,
    boxes: Value,
    window: Value,
    troop_window: Value,
    /// The Systems the cartridge carries a message window for, in its
    /// order: see `systems::names`. Empty if it does not switch.
    pub systems: Vec<String>,
    /// Where to leave the `compile` request, if anywhere: `rm2k-snes-events
    /// culprits` takes the same request, and it is otherwise written to a
    /// temporary directory and deleted.
    pub keep_request: Option<std::path::PathBuf>,
    /// Switches no page names that the ROM's table has to hold anyway:
    /// the test pages', in a cartridge with them.
    pub extra_switches: BTreeSet<i32>,
    /// The switch the test pages turn on: `TEST_SWITCH` until the scan
    /// answers, and what it answers after.
    pub test_switch: i32,
    /// The automatic common events copied into the maps, and into which:
    /// see [`crate::common_pages`]. None in a cartridge without them.
    pub common_pages: Option<Value>,
    /// The big pictures the common events without a map can show, as a
    /// map's big table: see `common_pictures` in `rm2k-snes-events`. Empty
    /// in a cartridge whose common events show none.
    pub common_pictures: Vec<Value>,
    /// The sets of the common events' small pictures, by their index: see
    /// [`crate::common_pictures`]. Empty in a cartridge without them.
    pub common_sets: Vec<Value>,
}

impl<'a> Compiler<'a> {
    pub fn new(game: &'a Game, settings: &'a Settings<'a>) -> Result<Compiler<'a>> {
        // Every text box of the game the port rebuilds for the console's
        // window, with the boxes that go in its place. A line is measured in
        // pixels, with the font the project file names.
        let font = FontChoice::of(settings)?;
        let width = rm2k_snes_screens::layout::MESSAGE_WIDTH;
        let boxes = screens::boxes(game, &font, width, LINES)?;
        let window = font.window(width, LINES);
        // And the battle's, where the troops' pages show theirs: as many
        // lines as the map's, and narrower —`BA_PAGE_MSG_WIDTH` cells, in
        // pixels, which is how the console cuts them too—. The compiler
        // reflows those itself, because it is the one that knows which pages
        // a troop brings.
        let troop_window = font.window(rm2k_snes_battle::screen::BA_PAGE_MSG_WIDTH * 8, LINES);
        let menus = Value::Array(settings.menus()?.iter().map(|m| m.hooks()).collect());
        Ok(Compiler {
            game,
            settings,
            menus,
            boxes,
            window,
            troop_window,
            systems: Vec::new(),
            keep_request: None,
            extra_switches: BTreeSet::new(),
            test_switch: TEST_SWITCH,
            common_pages: None,
            common_pictures: Vec::new(),
            common_sets: Vec::new(),
        })
    }

    fn data(&self) -> Vec<OsString> {
        vec!["--data".into(), self.game.dump.clone().into_os_string()]
    }

    /// What both calls carry.
    fn request(
        &self,
        maps: &[i32],
        test_commands: &[Command],
        extra_variables: &BTreeSet<i32>,
        test_event_map: Option<i32>,
    ) -> Map<String, Value> {
        let mut r = Map::new();
        r.insert("map_files".into(), map_files(self.game));
        r.insert("dropped_events".into(), self.game.dropped_json());
        if !self.game.boxed_exits.is_empty() {
            r.insert(
                "boxed_exits".into(),
                Value::Object(
                    self.game
                        .boxed_exits
                        .iter()
                        .map(|(m, ids)| (m.to_string(), json!(ids)))
                        .collect(),
                ),
            );
        }
        r.insert("boxes".into(), self.boxes.clone());
        r.insert("names".into(), json!([]));
        r.insert("window".into(), self.window.clone());
        r.insert("troop_window".into(), self.troop_window.clone());
        r.insert("maps".into(), json!(maps));
        r.insert("test_commands".into(), commands(test_commands));
        r.insert(
            "extra_variables".into(),
            json!(extra_variables.iter().collect::<Vec<_>>()),
        );
        r.insert(
            "extra_switches".into(),
            json!(self.extra_switches.iter().collect::<Vec<_>>()),
        );
        r.insert("test_event_map".into(), json!(test_event_map));
        r.insert("menus".into(), self.menus.clone());
        if let Some(c) = &self.common_pages {
            r.insert("common_pages".into(), c.clone());
        }
        if !self.common_pictures.is_empty() {
            r.insert("common_pictures".into(), json!(self.common_pictures));
        }
        if !self.common_sets.is_empty() {
            r.insert("common_sets".into(), json!(self.common_sets));
        }
        if !self.systems.is_empty() {
            r.insert("systems".into(), json!(self.systems));
        }
        r
    }

    /// The answer to `request`, from the cache if it is there: kept as the
    /// file the binary writes.
    fn run<A: Serialize + DeserializeOwned>(
        &self,
        stage: stage::Stage,
        answer: fn(&std::path::Path, &Value) -> rm2k_snes_events::Result<A>,
        request: Value,
    ) -> Result<A> {
        let written = stage::call(stage, &request, &self.data(), || {
            answer(&self.game.dump, &request).map(|a| rm2k_snes_events::stage::files(&a))
        })?;
        let file = rm2k_snes_events::ANSWER_FILE;
        serde_json::from_str(&stage::text(&written, file)?)
            .map_err(|e| Stop::new(format!("{}'s {file}: {e}", stage.binary)))
    }

    /// The first call: the indices, which pages of each map compile, each
    /// map's pages compiled without songs, and the pictures each map can
    /// show —its pages' and those of `cases`, `(map, commands)`, that run
    /// on it—.
    pub fn scan(
        &self,
        maps: &[i32],
        test_commands: &[Command],
        extra_variables: &BTreeSet<i32>,
        test_event_map: Option<i32>,
        cases: &[(i32, Vec<Command>)],
    ) -> Result<Scan> {
        let mut r = self.request(maps, test_commands, extra_variables, test_event_map);
        if !cases.is_empty() {
            r.insert(
                "cases".into(),
                Value::Array(
                    cases
                        .iter()
                        .map(|(m, c)| json!({"map": m, "commands": commands(c)}))
                        .collect(),
                ),
            );
            r.insert(
                "messages_step".into(),
                json!(rm2k_snes_mapdata::engine::MESSAGES_STEP),
            );
            // Which switch they can turn on: the scan sees every switch the
            // game names.
            r.insert("test_switch".into(), json!(TEST_SWITCH));
        }
        // And the counters, so a counter's digits are its and not
        // pictures: without them its body is pasted where it is called,
        // and its twenty `ShowPicture`s of a digit would ask for a place
        // in the sprites.
        r.insert("counters".into(), json!(counters(self.settings)?));
        self.run(SCAN, rm2k_snes_events::stage::scan, Value::Object(r))
    }

    /// The second call: every page of the cartridge. `maps` are the
    /// cartridge's, in its order, with what each one carries; `cases`,
    /// `(map, commands)`. A test page that does not compile comes back as
    /// null.
    #[allow(clippy::too_many_arguments)]
    pub fn compile(
        &self,
        maps: &[CompileMap],
        cases: &[(i32, Vec<Command>)],
        test_commands: &[Command],
        extra_variables: &BTreeSet<i32>,
        test_event_map: Option<i32>,
        test_graphics: &BTreeMap<i32, Vec<(String, i32)>>,
        encounter_troops: &Value,
    ) -> Result<Compiled> {
        let ids: Vec<i32> = maps.iter().map(|m| m.id).collect();
        let mut r = self.request(&ids, test_commands, extra_variables, test_event_map);
        r.insert(
            "names".into(),
            Value::Array(maps.iter().flat_map(|m| m.names.clone()).collect()),
        );
        let mut substitutions = Map::new();
        for m in maps {
            let table = m.substitution_table.iter().map(|(upper, old, new, pairs)| {
                json!({"upper": upper, "old": old, "new": new, "pairs": pairs})
            });
            substitutions.insert(m.id.to_string(), table.collect());
        }
        r.insert("substitutions".into(), Value::Object(substitutions));
        // The pictures each map carries, with their slots: see `pictures`.
        let mut pictures = Map::new();
        for m in maps {
            if m.pictures.is_some() || !m.big_table.is_empty() {
                let mut list: Vec<Value> = m.pictures.clone().unwrap_or_default();
                list.extend(m.big_table.iter().cloned());
                pictures.insert(m.id.to_string(), Value::Array(list));
            }
        }
        r.insert("pictures".into(), Value::Object(pictures));
        let route_graphics: Map<String, Value> = maps
            .iter()
            .map(|m| {
                let list = m
                    .route_graphics
                    .iter()
                    .map(|(c, i)| json!([c, i]))
                    .collect();
                (m.id.to_string(), Value::Array(list))
            })
            .collect();
        r.insert("route_graphics".into(), Value::Object(route_graphics));
        // The panoramas a `ChangePBG` can swap in, by map: only the maps
        // that carry more than their own, so a cartridge without any asks
        // what it always asked.
        let panoramas: Map<String, Value> = maps
            .iter()
            .filter(|m| !m.panoramas.is_empty())
            .map(|m| (m.id.to_string(), json!(m.panoramas)))
            .collect();
        if !panoramas.is_empty() {
            r.insert("panoramas".into(), Value::Object(panoramas));
        }
        // And the ChipSets a `ChangeMapTileset` can swap in, the same way.
        let tilesets: Map<String, Value> = maps
            .iter()
            .filter(|m| !m.tilesets.is_empty())
            .map(|m| (m.id.to_string(), json!(m.tilesets)))
            .collect();
        if !tilesets.is_empty() {
            r.insert("tilesets".into(), Value::Object(tilesets));
        }
        r.insert("counters".into(), json!(counters(self.settings)?));
        r.insert("sound_effects".into(), self.sound_effects()?);
        // Each test page turns itself off first: it is a convention of the
        // harness and not of the case —see `TEST_SWITCH`—, and an automatic
        // page that does not turn off repeats forever. With the switch the
        // scan answered.
        let turn_off = Command {
            code: rm2k_snes_events::codes::CONTROL_SWITCHES,
            indent: 0,
            string: String::new(),
            parameters: vec![SWITCH_SINGLE, self.test_switch, self.test_switch, SWITCH_ON],
        };
        r.insert(
            "cases".into(),
            Value::Array(
                cases
                    .iter()
                    .map(|(m, c)| {
                        let mut all = vec![turn_off.clone()];
                        all.extend(c.iter().cloned());
                        json!({"map": m, "commands": commands(&all)})
                    })
                    .collect(),
            ),
        );
        let mut graphics = Map::new();
        for (m, list) in test_graphics {
            graphics.insert(
                m.to_string(),
                Value::Array(list.iter().map(|(c, i)| json!([c, i])).collect()),
            );
        }
        r.insert("test_graphics".into(), Value::Object(graphics));
        r.insert(
            "messages_step".into(),
            json!(rm2k_snes_mapdata::engine::MESSAGES_STEP),
        );
        r.insert("encounter_troops".into(), encounter_troops.clone());
        if let Some(path) = &self.keep_request {
            let text = serde_json::to_string(&r).expect("a request is JSON");
            std::fs::write(path, text).map_err(|e| crate::fail::io(path, e))?;
        }
        self.run(COMPILE, rm2k_snes_events::stage::compile, Value::Object(r))
    }

    /// A compile of a cartridge of `maps` built without converting them: no
    /// picture, no graphic renamed, no substitution resolved —without the
    /// maps' blocks a page that asks for one does not compile—, and `cases`
    /// as they are, with nothing put in front. It is how a test asks what
    /// the compiler does with one page, or with a troop's.
    pub fn loose(
        &self,
        maps: &[i32],
        cases: &[(i32, Vec<Command>)],
        encounter_troops: &[i32],
    ) -> Result<Compiled> {
        let test_commands: Vec<Command> =
            cases.iter().flat_map(|(_, c)| c.iter().cloned()).collect();
        let mut r = self.request(maps, &test_commands, &BTreeSet::new(), None);
        let common = crate::maps::common_substitutions(self.game);
        let mut substitutions = Map::new();
        for m in maps {
            let mut mine = common.clone();
            crate::maps::substitution_triples(self.game.map(*m)?.all_commands(), &mut mine);
            substitutions.insert(
                m.to_string(),
                Value::Array(
                    mine.iter()
                        .map(|(u, o, n)| json!({"upper": u, "old": o, "new": n, "pairs": null}))
                        .collect(),
                ),
            );
        }
        r.insert("substitutions".into(), Value::Object(substitutions));
        r.insert("pictures".into(), json!({}));
        r.insert("counters".into(), json!(counters(self.settings)?));
        r.insert("sound_effects".into(), self.sound_effects()?);
        r.insert(
            "cases".into(),
            Value::Array(
                cases
                    .iter()
                    .map(|(m, c)| json!({"map": m, "commands": commands(c)}))
                    .collect(),
            ),
        );
        r.insert("test_graphics".into(), json!({}));
        r.insert(
            "messages_step".into(),
            json!(rm2k_snes_mapdata::engine::MESSAGES_STEP),
        );
        r.insert("encounter_troops".into(), json!(encounter_troops));
        if let Some(path) = &self.keep_request {
            let text = serde_json::to_string(&r).expect("a request is JSON");
            std::fs::write(path, text).map_err(|e| crate::fail::io(path, e))?;
        }
        self.run(COMPILE, rm2k_snes_events::stage::compile, Value::Object(r))
    }

    /// The boxes the compiler is handed: every text box of the game the
    /// port rebuilds for the console's window.
    pub fn boxes(&self) -> &Value {
        &self.boxes
    }

    /// The map's message window, as the compiler is told it: `width`,
    /// `lines` and `advances`.
    pub fn window(&self) -> &Value {
        &self.window
    }

    fn sound_effects(&self) -> Result<Value> {
        let mut out = Map::new();
        for name in [
            "per_map",
            "route_effects_left_out",
            "troop_effects_in_package",
        ] {
            out.insert(
                name.into(),
                Value::Array(self.settings.list(&["sound_effects", name])?),
            );
        }
        Ok(Value::Object(out))
    }
}

/// What a map takes to the second call.
pub struct CompileMap {
    pub id: i32,
    pub names: Vec<Value>,
    pub substitution_table: Vec<(bool, i32, i32, Option<Vec<(u16, u16)>>)>,
    pub pictures: Option<Vec<Value>>,
    pub big_table: Vec<Value>,
    /// The panoramas it carries, in the order the bytecode numbers them:
    /// see `maps::panorama_names`.
    pub panoramas: Vec<String>,
    /// The ChipSets it can be drawn with, its own first, in the order the
    /// bytecode numbers them: see `variants.rs`. Empty if it swaps none.
    pub tilesets: Vec<i32>,
    /// Its table of route graphics as the scan numbered it, the one its
    /// sprite bank was built with: the compilation numbers against it and
    /// does not add to it. See `route_graphics` in the events compiler's
    /// request.
    pub route_graphics: Vec<(String, i64)>,
}

/// `(event, page)` of the pages of that map that compile, by index.
pub fn compiling_pages(answer: &Scan, map_id: i32) -> Result<BTreeSet<(i64, i64)>> {
    let map = answer
        .map(map_id)
        .ok_or_else(|| Stop::new(format!("map {map_id} is not in the answer")))?;
    Ok(map
        .compiled
        .iter()
        .map(|(e, p, _)| (*e as i64, *p as i64))
        .collect())
}

/// The slot of `variable` in `indices`, or why it has none that fits in a
/// byte.
pub fn variable_slot(indices: &Indices, variable: i64) -> Result<i64> {
    let slot = indices
        .variables
        .iter()
        .find(|(v, _)| *v == variable)
        .map(|(_, s)| *s)
        .ok_or_else(|| Stop::new(format!("variable {variable} has no slot in this ROM")))?;
    if slot > rm2k_snes_mapdata::engine::VAR_SLOT_MAX as i64 {
        crate::stop!("slot {slot} does not fit in a byte: see VAR_SLOT_MAX");
    }
    Ok(slot)
}

/// The songs the compilation numbered, as the music stage asks for them:
/// the same lists, with its packages keyed for lookup.
pub fn songs(answer: &rm2k_snes_events::answer::Songs) -> rm2k_snes_audio::cartridge::Songs {
    use rm2k_snes_audio::cartridge::{Key, Wants};
    use rm2k_snes_events::registry::Package;
    fn by_package<V, W>(
        list: &[(Package, V)],
        value: impl Fn(&V) -> W,
    ) -> std::collections::HashMap<Key, W> {
        list.iter()
            .map(|(package, v)| {
                let key = match *package {
                    Package::Map(i) => Key::Map(i),
                    Package::Battle => Key::Battle,
                };
                (key, value(v))
            })
            .collect()
    }
    rm2k_snes_audio::cartridge::Songs {
        names: answer.names.clone(),
        sounds: answer
            .sounds
            .iter()
            .map(|(name, volume, tempo, pan)| {
                (
                    name.clone(),
                    (*volume).into(),
                    (*tempo).into(),
                    (*pan).into(),
                )
            })
            .collect(),
        per_package: by_package(&answer.per_package, |w| Wants {
            songs: w.songs.clone(),
            sounds: w.sounds.clone(),
            destinations: w.destinations.clone(),
        }),
        exits: by_package(&answer.exits, Clone::clone),
        jumps: by_package(&answer.jumps, Clone::clone),
        troop_songs: answer.troop_songs.clone(),
    }
}
