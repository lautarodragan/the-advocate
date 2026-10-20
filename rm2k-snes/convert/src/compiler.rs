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
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;

const BINARY: &str = "rm2k-snes-events";
const PROJECT: &str = "events";

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
pub fn counters(settings: &Settings) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for c in settings.list(&["events", "counters"])? {
        out.push(json!({"common_event": c["common_event"], "variable": c["variable"]}));
    }
    Ok(out)
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
}

impl<'a> Compiler<'a> {
    pub fn new(game: &'a Game, settings: &'a Settings<'a>) -> Result<Compiler<'a>> {
        // Every text box of the game the port rebuilds for the console's
        // window, with the boxes that go in its place. A line is measured in
        // pixels, with the font the project file names.
        let font = FontChoice::of(settings)?;
        let width = screens::message_width()?;
        let boxes = screens::boxes(game, &font, width, LINES)?;
        let window = font.window(width, LINES);
        // And the battle's, where the troops' pages show theirs: as many
        // lines as the map's, and narrower —`BA_PAGE_MSG_WIDTH` cells, in
        // pixels, which is how the console cuts them too—. The compiler
        // reflows those itself, because it is the one that knows which pages
        // a troop brings.
        let layout = stage::json(
            &stage::run("rm2k-snes-battle", "battle", "layout", &json!({}), &[])?,
            "layout.json",
        )?;
        let cells = layout["BA_PAGE_MSG_WIDTH"]
            .as_u64()
            .ok_or_else(|| Stop::new("the battle's layout has no BA_PAGE_MSG_WIDTH"))?;
        let troop_window = font.window(cells as usize * 8, LINES);
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
        if !self.systems.is_empty() {
            r.insert("systems".into(), json!(self.systems));
        }
        r
    }

    fn run(&self, command_name: &str, request: Value) -> Result<Value> {
        let written = stage::run(BINARY, PROJECT, command_name, &request, &self.data())?;
        stage::json(&written, "events.json")
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
    ) -> Result<Value> {
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
        r.insert("counters".into(), Value::Array(counters(self.settings)?));
        self.run("scan", Value::Object(r))
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
    ) -> Result<Value> {
        let ids: Vec<i32> = maps.iter().map(|m| m.id).collect();
        let mut r = self.request(&ids, test_commands, extra_variables, test_event_map);
        r.insert(
            "names".into(),
            Value::Array(maps.iter().flat_map(|m| m.names.clone()).collect()),
        );
        let mut substitutions = Map::new();
        for m in maps {
            substitutions.insert(m.id.to_string(), m.substitution_table.clone());
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
        r.insert("counters".into(), Value::Array(counters(self.settings)?));
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
        self.run("compile", Value::Object(r))
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
    ) -> Result<Value> {
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
        r.insert("counters".into(), Value::Array(counters(self.settings)?));
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
        self.run("compile", Value::Object(r))
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
    pub substitution_table: Value,
    pub pictures: Option<Vec<Value>>,
    pub big_table: Vec<Value>,
    /// The panoramas it carries, in the order the bytecode numbers them:
    /// see `maps::panorama_names`.
    pub panoramas: Vec<String>,
    /// Its table of route graphics as the scan numbered it, the one its
    /// sprite bank was built with: the compilation numbers against it and
    /// does not add to it. See `route_graphics` in the events compiler's
    /// request.
    pub route_graphics: Vec<(String, i64)>,
}

/// A map's entry in an answer.
pub fn map_entry(answer: &Value, map_id: i32) -> Result<&Value> {
    answer["maps"]
        .as_array()
        .and_then(|maps| {
            maps.iter()
                .find(|e| e["id"].as_i64() == Some(map_id as i64))
        })
        .ok_or_else(|| Stop::new(format!("map {map_id} is not in the answer")))
}

/// `(event, page)` of the pages of that map that compile, by index.
pub fn compiling_pages(answer: &Value, map_id: i32) -> Result<BTreeSet<(i64, i64)>> {
    Ok(map_entry(answer, map_id)?["compiled"]
        .as_array()
        .map(|list| {
            list.iter()
                .map(|e| (e[0].as_i64().unwrap_or(-1), e[1].as_i64().unwrap_or(-1)))
                .collect()
        })
        .unwrap_or_default())
}

/// `{variable: slot}` and `{(actor, skill): slot}` of the scan's answer.
pub struct Indices {
    pub variables: Vec<(i64, i64)>,
    pub skills: Vec<((i64, i64), i64)>,
    /// The highest switch the game names: the ROM's table holds 0 to it.
    pub switch_top: i64,
    /// The switch the test pages can turn on, if the scan was asked.
    pub test_switch: Option<i64>,
    /// Every (actor, name) a `ChangeHeroName` gives, in the order
    /// `OP_CHANGE_NAME` counts them: the screens and the emission write
    /// their texts in it.
    pub names: Vec<(i64, String)>,
    /// Every face a `ChangeFaceGraphic` names, as (FaceSet, index,
    /// mirrored), in the order `OP_FACE` counts them: the screens draw them
    /// in it, for the emission.
    pub faces: Vec<(String, i64, bool)>,
}

impl Indices {
    pub fn from_answer(answer: &Value) -> Indices {
        let pairs = |key: &str| -> Vec<Vec<i64>> {
            answer[key]
                .as_array()
                .map(|list| {
                    list.iter()
                        .map(|e| {
                            e.as_array()
                                .map(|v| v.iter().filter_map(Value::as_i64).collect())
                                .unwrap_or_default()
                        })
                        .collect()
                })
                .unwrap_or_default()
        };
        // A dictionary keeps the last value of a repeated key in the place
        // of the first: what the Python's `{v: s for v, s in …}` did.
        fn dict<K: PartialEq + Clone>(entries: Vec<(K, i64)>) -> Vec<(K, i64)> {
            let mut out: Vec<(K, i64)> = Vec::new();
            for (k, v) in entries {
                match out.iter_mut().find(|(o, _)| *o == k) {
                    Some(slot) => slot.1 = v,
                    None => out.push((k, v)),
                }
            }
            out
        }
        Indices {
            variables: dict(
                pairs("variables")
                    .into_iter()
                    .map(|e| (e[0], e[1]))
                    .collect(),
            ),
            skills: dict(
                pairs("skills")
                    .into_iter()
                    .map(|e| ((e[0], e[1]), e[2]))
                    .collect(),
            ),
            switch_top: answer["switch_top"].as_i64().unwrap_or(0),
            test_switch: answer["test_switch"].as_i64(),
            names: answer["names"]
                .as_array()
                .map(|list| {
                    list.iter()
                        .filter_map(|e| Some((e[0].as_i64()?, e[1].as_str()?.to_string())))
                        .collect()
                })
                .unwrap_or_default(),
            faces: answer["faces"]
                .as_array()
                .map(|list| {
                    list.iter()
                        .filter_map(|e| {
                            Some((e[0].as_str()?.to_string(), e[1].as_i64()?, e[2].as_bool()?))
                        })
                        .collect()
                })
                .unwrap_or_default(),
        }
    }

    /// The slot of `variable`, or why it has none that fits in a byte.
    pub fn variable_slot(&self, variable: i64) -> Result<i64> {
        let slot = self
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
}
