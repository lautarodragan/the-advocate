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
use rm2k_snes_events::request::{self, Asked, ByMap, Counter};
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
pub fn command(c: &Command) -> rm2k_snes_events::game::Command {
    rm2k_snes_events::game::Command {
        code: c.code,
        indent: c.indent,
        string: c.string.clone(),
        parameters: c.parameters.clone(),
    }
}

fn commands(list: &[Command]) -> Vec<rm2k_snes_events::game::Command> {
    list.iter().map(command).collect()
}

/// The test pages, each with the map it runs in.
fn cases(list: &[(i32, Vec<Command>)]) -> Vec<request::Case> {
    list.iter()
        .map(|(map, c)| request::Case {
            map: *map,
            commands: commands(c),
        })
        .collect()
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
/// maps: `(map, event, page, name)`.
pub fn names<'a>(maps: impl IntoIterator<Item = &'a GameMap>) -> Vec<(i32, i32, i32, String)> {
    let mut out = Vec::new();
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                if page.character_name != page.dump_name {
                    out.push((map.id, event.id, page.id, page.character_name.clone()));
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

/// What the compiler is asked for and keeps: the boxes and the battle's
/// window are asked once.
pub struct Compiler<'a> {
    pub game: &'a Game,
    pub settings: &'a Settings<'a>,
    /// What the custom menus ask of the events, one entry per menu: see
    /// `CustomMenu::hooks`.
    menus: Vec<request::MenuHooks>,
    boxes: Vec<request::MessageBox>,
    window: request::Window,
    troop_window: request::Window,
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
    pub common_pages: Option<request::CommonPages>,
    /// The pictures the common events without a map can show: the big
    /// ones, as a map's big table —see `common_pictures` in
    /// `rm2k-snes-events`—, and after them the small ones of the common
    /// table —see [`crate::common_pictures`]—. Empty in a cartridge whose
    /// common events show none.
    pub common_pictures: Vec<request::Picture>,
    /// The sets of the common events' small pictures, by their index: see
    /// [`crate::common_pictures`]. Empty in a cartridge without them.
    pub common_sets: Vec<request::CommonSet>,
}

impl<'a> Compiler<'a> {
    pub fn new(game: &'a Game, settings: &'a Settings<'a>) -> Result<Compiler<'a>> {
        // Every text box of the game the port rebuilds for the console's
        // window, with the boxes that go in its place. A line is measured in
        // pixels, with the font the project file names.
        let font = FontChoice::of(settings)?;
        let width = rm2k_snes_screens::layout::MESSAGE_WIDTH;
        let boxes = screens::boxes(game, &font, width, LINES)?
            .into_iter()
            .map(|b| request::MessageBox {
                from: b.from,
                to: b.to,
            })
            .collect();
        let window = font.window(width, LINES);
        // And the battle's, where the troops' pages show theirs: as many
        // lines as the map's, and narrower —`BA_PAGE_MSG_WIDTH` cells, in
        // pixels, which is how the console cuts them too—. The compiler
        // reflows those itself, because it is the one that knows which pages
        // a troop brings.
        let troop_window = font.window(rm2k_snes_battle::screen::BA_PAGE_MSG_WIDTH * 8, LINES);
        let menus = settings.menus()?.iter().map(|m| m.hooks()).collect();
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
    ) -> Result<Asked> {
        let ids = |m: &BTreeMap<i32, BTreeSet<i32>>| -> ByMap<Vec<i32>> {
            m.iter()
                .map(|(m, ids)| (*m, ids.iter().copied().collect()))
                .collect()
        };
        Ok(Asked {
            map_files: self.game.forks.map_files().into_iter().collect(),
            dropped: ids(&self.game.dropped),
            boxed_exits: ids(&self.game.boxed_exits),
            boxes: self.boxes.clone(),
            names: Vec::new(),
            window: self.window.clone(),
            troop_window: Some(self.troop_window.clone()),
            maps: maps.to_vec(),
            test_commands: commands(test_commands),
            extra_variables: extra_variables.iter().copied().collect(),
            extra_switches: self.extra_switches.iter().copied().collect(),
            test_event_map,
            menus: self.menus.clone(),
            common_pages: self.common_pages.clone(),
            common_pictures: self.common_pictures.clone(),
            common_sets: self.common_sets.clone(),
            systems: self.systems.clone(),
            // And the counters, so a counter's digits are its and not
            // pictures: without them its body is pasted where it is
            // called, and its twenty `ShowPicture`s of a digit would ask
            // for a place in the sprites.
            counters: counters(self.settings)?,
            ..Asked::default()
        })
    }

    /// The answer to `request`, from the cache if it is there: kept as the
    /// file the binary writes.
    fn run<A: Serialize + DeserializeOwned>(
        &self,
        stage: stage::Stage,
        answer: fn(&std::path::Path, &Asked) -> rm2k_snes_events::Result<A>,
        request: &Asked,
    ) -> Result<A> {
        let value = serde_json::to_value(request).expect("a request is JSON");
        let written = stage::call(stage, &value, &self.data(), || {
            answer(&self.game.dump, request).map(|a| rm2k_snes_events::stage::files(&a))
        })?;
        let file = rm2k_snes_events::ANSWER_FILE;
        serde_json::from_str(&stage::text(&written, file)?)
            .map_err(|e| Stop::new(format!("{}'s {file}: {e}", stage.binary)))
    }

    /// Leaves `request` where `keep_request` says, if anywhere.
    fn keep(&self, request: &Asked) -> Result<()> {
        if let Some(path) = &self.keep_request {
            let text = serde_json::to_string(request).expect("a request is JSON");
            std::fs::write(path, text).map_err(|e| crate::fail::io(path, e))?;
        }
        Ok(())
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
        let mut r = self.request(maps, test_commands, extra_variables, test_event_map)?;
        if !cases.is_empty() {
            r.cases = Some(self::cases(cases));
            r.messages_step = Some(rm2k_snes_mapdata::engine::MESSAGES_STEP);
            // Which switch they can turn on: the scan sees every switch the
            // game names.
            r.test_switch = Some(TEST_SWITCH);
        }
        self.run(SCAN, rm2k_snes_events::stage::scan, &r)
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
        encounter_troops: &[i32],
    ) -> Result<Compiled> {
        let ids: Vec<i32> = maps.iter().map(|m| m.id).collect();
        let mut r = self.request(&ids, test_commands, extra_variables, test_event_map)?;
        r.names = maps.iter().flat_map(|m| m.names.clone()).collect();
        r.substitutions = Some(
            maps.iter()
                .map(|m| {
                    let table = m.substitution_table.iter().map(|(upper, old, new, pairs)| {
                        request::Substitution {
                            upper: *upper,
                            old: (*old).into(),
                            new: (*new).into(),
                            pairs: pairs
                                .as_ref()
                                .map(|p| p.iter().map(|&(a, b)| (a.into(), b.into())).collect()),
                        }
                    });
                    (m.id, table.collect())
                })
                .collect(),
        );
        // The pictures each map carries, with their slots: see `pictures`.
        r.pictures = Some(
            maps.iter()
                .filter(|m| m.pictures.is_some() || !m.big_table.is_empty())
                .map(|m| {
                    let mut list = m.pictures.clone().unwrap_or_default();
                    list.extend(m.big_table.iter().cloned());
                    (m.id, list)
                })
                .collect(),
        );
        r.route_graphics = Some(
            maps.iter()
                .map(|m| (m.id, m.route_graphics.clone()))
                .collect(),
        );
        // The panoramas a `ChangePBG` can swap in, by map: only the maps
        // that carry more than their own, so a cartridge without any asks
        // what it always asked.
        let panoramas: ByMap<Vec<String>> = maps
            .iter()
            .filter(|m| !m.panoramas.is_empty())
            .map(|m| (m.id, m.panoramas.clone()))
            .collect();
        r.panoramas = (!panoramas.is_empty()).then_some(panoramas);
        // And the ChipSets a `ChangeMapTileset` can swap in, the same way.
        let tilesets: ByMap<Vec<i32>> = maps
            .iter()
            .filter(|m| !m.tilesets.is_empty())
            .map(|m| (m.id, m.tilesets.clone()))
            .collect();
        r.tilesets = (!tilesets.is_empty()).then_some(tilesets);
        r.sound_effects = Some(self.sound_effects()?);
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
        let cases: Vec<(i32, Vec<Command>)> = cases
            .iter()
            .map(|(m, c)| {
                let mut all = vec![turn_off.clone()];
                all.extend(c.iter().cloned());
                (*m, all)
            })
            .collect();
        r.cases = Some(self::cases(&cases));
        r.test_graphics = Some(
            test_graphics
                .iter()
                .map(|(m, list)| (*m, list.clone()))
                .collect(),
        );
        r.messages_step = Some(rm2k_snes_mapdata::engine::MESSAGES_STEP);
        r.encounter_troops = Some(encounter_troops.to_vec());
        self.keep(&r)?;
        self.run(COMPILE, rm2k_snes_events::stage::compile, &r)
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
        let mut r = self.request(maps, &test_commands, &BTreeSet::new(), None)?;
        let common = crate::maps::common_substitutions(self.game);
        let mut substitutions = ByMap::default();
        for m in maps {
            let mut mine = common.clone();
            crate::maps::substitution_triples(self.game.map(*m)?.all_commands(), &mut mine);
            let table = mine.iter().map(|&(upper, old, new)| request::Substitution {
                upper,
                old: old.into(),
                new: new.into(),
                pairs: None,
            });
            substitutions.insert(*m, table.collect());
        }
        r.substitutions = Some(substitutions);
        r.pictures = Some(ByMap::default());
        r.sound_effects = Some(self.sound_effects()?);
        r.cases = Some(self::cases(cases));
        r.test_graphics = Some(ByMap::default());
        r.messages_step = Some(rm2k_snes_mapdata::engine::MESSAGES_STEP);
        r.encounter_troops = Some(encounter_troops.to_vec());
        self.keep(&r)?;
        self.run(COMPILE, rm2k_snes_events::stage::compile, &r)
    }

    /// The boxes the compiler is handed: every text box of the game the
    /// port rebuilds for the console's window.
    pub fn boxes(&self) -> &[request::MessageBox] {
        &self.boxes
    }

    /// The map's message window, as the compiler is told it: `width`,
    /// `lines` and `advances`.
    pub fn window(&self) -> &request::Window {
        &self.window
    }

    /// `[sound_effects]`, what of it the compiler reads.
    fn sound_effects(&self) -> Result<request::SoundEffects> {
        fn read<T: DeserializeOwned>(settings: &Settings, name: &str) -> Result<Vec<T>> {
            settings
                .list(&["sound_effects", name])?
                .into_iter()
                .map(|v| {
                    serde_json::from_value(v)
                        .map_err(|e| Stop::new(format!("[sound_effects] {name}: {e}")))
                })
                .collect()
        }
        Ok(request::SoundEffects {
            per_map: read(self.settings, "per_map")?,
            route_effects_left_out: read(self.settings, "route_effects_left_out")?,
            troop_effects_in_package: read(self.settings, "troop_effects_in_package")?,
        })
    }
}

/// What a map takes to the second call.
pub struct CompileMap {
    pub id: i32,
    pub names: Vec<(i32, i32, i32, String)>,
    pub substitution_table: Vec<(bool, i32, i32, Option<Vec<(u16, u16)>>)>,
    pub pictures: Option<Vec<request::Picture>>,
    pub big_table: Vec<request::Picture>,
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
    pub route_graphics: Vec<(String, i32)>,
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
