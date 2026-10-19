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
//! The opcodes' numbers are not here: they are declared, once, in
//! `rm2k-snes-bytecode`.

pub mod codes;
pub mod commons;
pub mod compile;
pub mod culprits;
pub mod fail;
pub mod game;
pub mod indices;
pub mod losses;
pub mod messages;
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
use crate::losses::{Losses, Origin};
use crate::messages::{Messages, Window};
use crate::pages::{hex, map_pages, MapEvents, SubstitutionTable, Substitutions};
use crate::registry::{BigPicture, Graphics, Package, PictureKey, Pictures, Songs, Troops};
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
    /// The battle's message window, which the troops' pages show their
    /// boxes in: narrower than the map's, so they are reflowed for it. Only
    /// a compilation that has troops needs it.
    pub troop_window: Option<Window>,
    /// The cartridge's maps, in its order.
    pub maps: Vec<i32>,
    /// The commands of every test page, one after the other: they name
    /// variables, pairs and graphics too, and their texts go first.
    pub test_commands: Vec<Command>,
    /// Variables no page names that need a slot anyway.
    pub extra_variables: BTreeSet<i32>,
    /// And switches no page names that the table has to hold anyway: the
    /// harness's `TEST_SWITCH`, which every test page turns on.
    pub extra_switches: BTreeSet<i32>,
    /// The map the test pages boot in, which carries an event without pages
    /// at index 0 so that they run before the game's.
    pub test_event_map: Option<i32>,
    /// The automatic common events whose body shows pictures, and the maps
    /// that carry a copy of them as automatic pages of an added last event:
    /// see [`with_test_event`]. Empty in a cartridge that has none.
    pub common_pages: Vec<i32>,
    pub common_page_maps: BTreeSet<i32>,
    // What only `compile` reads.
    pub substitutions: BTreeMap<i32, SubstitutionTable>,
    /// Per map, the pictures it carries and each one's slot: see
    /// [`Pictures`]. A map that is not here carries none.
    pub pictures: BTreeMap<i32, Pictures>,
    /// The pictures the common events compiled without a map can show —the
    /// shared bodies and the parallel ones—: only big ones, which the
    /// cartridge carries once and the console shows the same on every map
    /// —see `runtime/big_picture.s`—. A small one lives in a map's sprite
    /// bank, so a body without a map has none. The scan gathers what they
    /// can show apart, as `commons_pictures`.
    pub common_pictures: Pictures,
    /// Per map, the panoramas it carries, in the order the bytecode numbers
    /// them: its own first —or an empty name, if it starts with none— and
    /// the ones its `ChangePBG`s name after it. A map that is not here
    /// carries only its own, if it shows it. See `CHANGE_PBG` in
    /// `compile.rs`.
    pub panoramas: BTreeMap<i32, Vec<String>>,
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

/// A message window as a request carries it: `width`, a line's pixels,
/// `lines`, and `advances`, the advance of each glyph of the console's font
/// from the space on; or, without `width`, `columns` letters of RM2k's
/// fixed-width font, which is how it was asked until 2026-10-03. And,
/// optional, `letters`: the Latin-1 letters the font draws, each a pair of
/// the letter and its advance —see `Font::latin_letters`—. A window carries
/// none of them until the compilation chooses: see [`compile`].
fn window(w: &Value, whose: &str) -> Result<Window> {
    let lines = int(field(w, "lines", whose)?, whose)? as usize;
    if w.get("width").is_none() {
        return Ok(Window::columns(
            int(field(w, "columns", whose)?, whose)? as usize,
            lines,
        ));
    }
    let given = list(w, "advances", whose)?;
    let mut advances = [0u8; rm2k_snes_text::font::CONSOLE_GLYPHS];
    if given.len() != advances.len() {
        return Err(Bad::answer(format!(
            "{whose}: the window's `advances` are {} and the console's font has {}",
            given.len(),
            advances.len()
        )));
    }
    for (a, g) in advances.iter_mut().zip(given) {
        *a = int(g, whose)? as u8;
    }
    let mut latin = [0u8; rm2k_snes_text::font::LATIN_GLYPHS];
    for pair in w
        .get("letters")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let bad = || {
            Bad::answer(format!("{whose}: the window's `letters` are pairs of a Latin-1 letter and its advance: {pair}"))
        };
        let letter = pair
            .get(0)
            .and_then(Value::as_str)
            .and_then(|s| s.chars().next())
            .ok_or_else(bad)?;
        let advance = pair
            .get(1)
            .and_then(Value::as_u64)
            .filter(|&a| a > 0 && a < 256)
            .ok_or_else(bad)?;
        let slot = (letter as u32)
            .checked_sub(rm2k_snes_text::font::LATIN_FIRST)
            .filter(|&i| (i as usize) < latin.len())
            .ok_or_else(bad)?;
        latin[slot as usize] = advance as u8;
    }
    Ok(Window {
        width: int(field(w, "width", whose)?, whose)? as usize,
        lines,
        advances,
        latin,
        carried: [0; rm2k_snes_text::font::LATIN_GLYPHS],
    })
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

/// A picture as the scan answers it and the caller sends it back: see
/// [`PictureKey::to_json`].
fn picture_key(v: &Value, whose: &str) -> Result<PictureKey> {
    let flag = |name: &str| -> Result<bool> {
        field(v, name, whose)?
            .as_bool()
            .ok_or_else(|| Bad::answer(format!("{whose}: a picture's `{name}` is not a flag")))
    };
    let at = field(v, "at", whose)?;
    Ok(PictureKey {
        number: int(field(v, "number", whose)?, whose)? as i32,
        name: text(field(v, "name", whose)?, whose)?,
        zoom: int(field(v, "zoom", whose)?, whose)? as i32,
        transparent_color: flag("transparent_color")?,
        map_fixed: flag("map_fixed")?,
        by_variable: flag("by_variable")?,
        at: if at.is_null() {
            None
        } else {
            let a = at
                .as_array()
                .filter(|a| a.len() == 2)
                .ok_or_else(|| Bad::answer(format!("{whose}: a picture's `at` is {at}")))?;
            Some((int(&a[0], whose)? as i32, int(&a[1], whose)? as i32))
        },
    })
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

/// A list of pictures as the caller answers them: each entry a picture in
/// the map's sprite bank, with its slot, or —with `"plane": "background"`— a
/// big one, with its entry in the cartridge's table and half its size.
fn pictures_of(v: &Value, whose: &str) -> Result<Pictures> {
    let mut pictures = Pictures::default();
    for e in v
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: a list of pictures is not a list")))?
    {
        let key = picture_key(e, whose)?;
        if e.get("plane").and_then(Value::as_str) == Some("background") {
            let pair = |name: &str| -> Result<(i32, i32)> {
                let a = field(e, name, whose)?
                    .as_array()
                    .filter(|a| a.len() == 2)
                    .ok_or_else(|| Bad::answer(format!("{whose}: a big picture's `{name}`")))?;
                Ok((int(&a[0], whose)? as i32, int(&a[1], whose)? as i32))
            };
            pictures.big.push(BigPicture {
                key,
                image: int(field(e, "image", whose)?, whose)? as u8,
                center: pair("center")?,
                texture: e.get("texture").and_then(Value::as_bool).unwrap_or(false),
            });
        } else {
            pictures
                .table
                .push((key, int(field(e, "slot", whose)?, whose)? as u8));
        }
    }
    Ok(pictures)
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
        // Not required: a request that leaves nothing out does not have to
        // say it, and the ones written before it existed stay as they were.
        if let Some(d) = data.get("dropped_events") {
            r.patches.dropped = by_map(d, whose, |v| {
                v.as_array()
                    .ok_or_else(|| {
                        Bad::answer(format!("{whose}: a map's `dropped_events` is not a list"))
                    })?
                    .iter()
                    .map(|e| int(e, whose).map(|x| x as i32))
                    .collect()
            })?;
        }
        if let Some(d) = data.get("boxed_exits") {
            r.patches.boxed_exits = by_map(d, whose, |v| {
                v.as_array()
                    .ok_or_else(|| {
                        Bad::answer(format!("{whose}: a map's `boxed_exits` is not a list"))
                    })?
                    .iter()
                    .map(|e| int(e, whose).map(|x| x as i32))
                    .collect()
            })?;
        }
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
        r.window = Some(window(field(data, "window", whose)?, whose)?);
        if let Some(w) = data.get("troop_window") {
            r.troop_window = Some(window(w, whose)?);
        }
        r.maps = list(data, "maps", whose)?
            .iter()
            .map(|m| int(m, whose).map(|x| x as i32))
            .collect::<Result<_>>()?;
        r.test_commands = commands(field(data, "test_commands", whose)?, whose)?;
        r.extra_variables = list(data, "extra_variables", whose)?
            .iter()
            .map(|m| int(m, whose).map(|x| x as i32))
            .collect::<Result<_>>()?;
        if let Some(s) = data.get("extra_switches") {
            r.extra_switches = s
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: `extra_switches` is not a list")))?
                .iter()
                .map(|m| int(m, whose).map(|x| x as i32))
                .collect::<Result<_>>()?;
        }
        let t = field(data, "test_event_map", whose)?;
        r.test_event_map = if t.is_null() {
            None
        } else {
            Some(int(t, whose)? as i32)
        };
        if let Some(c) = data.get("common_pages").filter(|c| !c.is_null()) {
            let numbers = |name: &str| -> Result<Vec<i32>> {
                list(c, name, whose)?
                    .iter()
                    .map(|m| int(m, whose).map(|x| x as i32))
                    .collect()
            };
            r.common_pages = numbers("commons")?;
            r.common_page_maps = numbers("maps")?.into_iter().collect();
        }

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
        if let Some(systems) = data.get("systems").filter(|s| !s.is_null()) {
            for s in systems
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: `systems` is not a list")))?
            {
                let name = s
                    .as_str()
                    .ok_or_else(|| Bad::answer(format!("{whose}: a System is {s}")))?;
                r.patches.systems.push(name.to_string());
            }
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
        if let Some(menus) = data.get("menus").filter(|m| !m.is_null()) {
            // Each custom menu, in the order the cartridge numbers them:
            // the common event it replaces, if any, and the ones it runs
            // before a page.
            for (k, m) in menus
                .as_array()
                .ok_or_else(|| Bad::answer(format!("{whose}: `menus` is not a list")))?
                .iter()
                .enumerate()
            {
                if let Some(n) = m.get("replaces_common").and_then(Value::as_i64) {
                    r.patches.menus.replaced.insert(n as i32, k as u8);
                }
                for b in m
                    .get("before")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
                {
                    r.patches.menus.before.insert(int(&b, whose)? as i32);
                }
            }
        }
        if let Some(p) = data.get("panoramas") {
            r.panoramas = by_map(p, whose, |v| {
                v.as_array()
                    .ok_or_else(|| {
                        Bad::answer(format!("{whose}: a map's panoramas are not a list"))
                    })?
                    .iter()
                    .map(|n| text(n, whose))
                    .collect()
            })?;
        }
        if let Some(p) = data.get("pictures") {
            r.pictures = by_map(p, whose, |v| pictures_of(v, whose))?;
        }
        if let Some(p) = data.get("common_pictures") {
            r.common_pictures = pictures_of(p, whose)?;
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

/// The map with the events the cartridge adds to it, if any.
///
/// **The map the test pages boot in** gets one without pages at index 0: it
/// takes that index so that everything that numbers events numbers the
/// same, and the console walks the events from the lowest, so its pages
/// run before the game's. The caller puts the test pages on it.
///
/// **A map of `common_page_maps`** gets one **last**, with the id after the
/// highest —see [`copy_event`]—, whose pages are the automatic common
/// events of `common_pages`, each an automatic page on the common event's
/// switch: last, so no event of the game changes its index. RM2k runs an automatic common event on whatever map, and
/// the cartridge already does, from the shared body —see [`commons`]—; but a
/// shared body is compiled without a map, so without pictures, and a menu
/// built of `ShowPicture`s works blind: Frozen World's `BringUpMenu`, common
/// 15. The copy is compiled with the map, so its pictures go in the map's
/// sprite bank like the map's own. It runs instead of the shared body,
/// which does not start on a map with a copy: see `switch_of` in the
/// runtime's `common_events.s`. The shared body stays, for the maps that
/// carry no copy. The pages go from the highest number to the lowest: the
/// active page is the last whose condition holds, and RM2k starts the
/// lowest-numbered common event first.
fn with_test_event(mut map: Map, request: &Request, game: &Game) -> Map {
    if request.test_event_map == Some(map.id) {
        map.events.insert(
            0,
            Event {
                id: 0,
                x: 0,
                y: 0,
                pages: vec![],
                starting: None,
            },
        );
    }
    if request.common_page_maps.contains(&map.id) {
        let id = map.events.iter().map(|e| e.id).max().unwrap_or(0) + 1;
        map.events.push(Event {
            id,
            x: 0,
            y: 0,
            pages: common_pages(game, &request.common_pages),
            starting: None,
        });
    }
    map
}

/// The id of the event with the copies of the common events, on a map
/// [`with_test_event`] gave one: the last.
fn copy_event(map: &Map, request: &Request) -> Option<i32> {
    request
        .common_page_maps
        .contains(&map.id)
        .then(|| map.events.last().map(|e| e.id))
        .flatten()
}

/// The automatic common events `numbers` as pages of a map's event: see
/// [`with_test_event`]. One that is not automatic with a switch is not
/// taken, nor one a custom menu replaces, whose body is the menu's opcode.
fn common_pages(game: &Game, numbers: &[i32]) -> Vec<crate::game::Page> {
    let mut numbers: Vec<i32> = numbers.to_vec();
    numbers.sort_by(|a, b| b.cmp(a));
    numbers
        .into_iter()
        .filter(|n| !game.patches.menus.replaced.contains_key(n))
        .filter_map(|n| game.common_events.get(&n))
        .filter(|c| c.trigger == TRIGGER_AUTOSTART && c.switch_flag && !c.commands.is_empty())
        .enumerate()
        .map(|(k, c)| crate::game::Page {
            trigger: TRIGGER_AUTOSTART,
            layer: 0,
            move_type: 0,
            move_frequency: 3,
            move_speed: 3,
            animation_type: 0,
            character_name: String::new(),
            character_index: 0,
            character_pattern: 1,
            commands: c.commands.clone(),
            route: Vec::new(),
            route_repeat: true,
            route_skippable: false,
            condition: crate::game::Condition {
                switch_a: Some(c.switch_id),
                ..Default::default()
            },
            id: k as i32 + 1,
            translucent: false,
            overlap_forbidden: false,
        })
        .collect()
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
    // The highest switch the game names: the cartridge's table holds it.
    out.insert("switch_top".into(), json!(indices.switch_top));
    // The names `ChangeHeroName` gives, in the order `OP_CHANGE_NAME` counts
    // them: the converter writes their texts and the table of the renamed
    // actors from this.
    out.insert(
        "names".into(),
        json!(indices
            .renames
            .iter()
            .map(|(a, n)| json!([a, n]))
            .collect::<Vec<_>>()),
    );
    // The faces the message window shows, as [FaceSet, index, mirrored], in
    // the order `OP_FACE` counts them: the converter draws them from this.
    out.insert(
        "faces".into(),
        json!(indices
            .faces
            .iter()
            .map(|(f, i, m)| json!([f, i, m]))
            .collect::<Vec<_>>()),
    );
    out.insert("associations".into(), json!(associations));
    out
}

/// The indices, the graphics actors can be given, and the cartridge's maps.
type Prepared = (Indices, Vec<(String, i32)>, Vec<Map>);

pub(crate) fn prepare(game: &Game, request: &Request) -> Result<Prepared> {
    let every = indices::every_map(game)?;
    let mut extra_variables = request.extra_variables.clone();
    extra_variables.extend(indices::command_variables(&request.test_commands));
    let mut extra_switches = request.extra_switches.clone();
    extra_switches.extend(indices::command_switches(&request.test_commands));
    let extra_pairs = indices::command_skill_pairs(&request.test_commands);
    let mut indices = indices::build(
        game,
        &every,
        &extra_variables,
        &extra_pairs,
        &extra_switches,
    )?;
    // And the names the test pages give, after the game's: a renamed actor's
    // name is not baked into any text.
    for pair in indices::command_renames(&request.test_commands) {
        indices.hero_names.remove(&pair.0);
        if !indices.renames.contains(&pair) {
            indices.renames.push(pair);
        }
    }
    // And the faces the test pages show, after the game's.
    for face in indices::command_faces(&request.test_commands) {
        if !indices.faces.contains(&face) {
            indices.faces.push(face);
        }
    }
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
        let me = MapEvents::new(map, None).numbered(map, &indices);
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
                    pictures: None,
                    troops: None,
                    commons: None,
                    shared: None,
                    losses: Losses::default(),
                    face: None,
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
        let map = with_test_event(map.clone(), request, game);
        let me = MapEvents::new(&map, None).numbered(&map, &indices);
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
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
            losses: Losses::default(),
            face: None,
        };
        let pages = map_pages(&mut ctx, &map, &me)?;
        // And the pictures the map can show, gathered apart: its pages' first
        // and then the test pages' that run here, which is the order the
        // caller converts them in. Each page with everything a real
        // compilation has —without songs, the pages above stop at the first
        // `PlayBGM`, and the "Meanwhile" sign of map 81 comes after one—.
        let mut pictures = Pictures::gathering();
        let mut on_events = graphics.on_events.clone();
        //
        // **The copies of the automatic common events go last** —the pages of
        // the added last event, see [`with_test_event`]—, and the answer says
        // how many pictures came before them, `pictures_own`: a map that has
        // no room for theirs keeps its own.
        let copy = copy_event(&map, request);
        let pages_of = |copies: bool| {
            map.events
                .iter()
                .filter(move |event| (Some(event.id) == copy) == copies)
                .flat_map(|event| {
                    event
                        .pages
                        .iter()
                        .map(move |page| (event.id, &page.commands))
                })
        };
        let cases = request
            .cases
            .iter()
            .filter(|(run_map, _)| *run_map == map.id)
            .map(|(_, case)| (0, case));
        let mut own = None;
        let copies = pages_of(true).map(Some);
        for event in pages_of(false)
            .chain(cases)
            .map(Some)
            .chain([None])
            .chain(copies)
        {
            let Some((event, commands)) = event else {
                own = Some(pictures.table.len());
                continue;
            };
            // Its texts are only measured, with the cartridge's step: a test
            // page can carry more than sixty-four kilobytes of them —the one
            // that pads the text block does—.
            let mut messages = Messages::measuring(request.messages_step, request.window());
            let mut songs = Songs::default();
            let mut graphics = Graphics::new(&associations);
            let mut ctx = Ctx {
                game,
                indices: &indices,
                sound: &sound,
                map_index: &map_index,
                messages: Some(&mut messages),
                songs: Some(&mut songs),
                graphics: Some(&mut graphics),
                pictures: Some(&mut pictures),
                troops: None,
                commons: None,
                shared: None,
                losses: Losses::default(),
                face: None,
            };
            compile_page(&mut ctx, commands, Some(me.for_event(event)), 0, 0)?;
            on_events.extend(graphics.on_events);
        }
        let mut entry = json!({
            "id": map.id,
            "compiled": compiled,
            "pages": pages,
            "graphics": graphics.pairs,
            "pictures": pictures.keys_json(),
            "zooms": pictures.zooms_json(),
            "tinted": pictures.tinted,
        });
        // Only on a map with copies, so the answer of the rest stays the one
        // it was.
        if request.common_page_maps.contains(&map.id) {
            entry["pictures_own"] = json!(own);
        }
        // Which of them a route gives an event, the test pages' too: the
        // rest only the hero shows. Only when there are some, like
        // `graphics_dropped`.
        if !on_events.is_empty() {
            entry["graphics_on_events"] = json!(on_events);
        }
        out.push(entry);
    }
    // And the pictures the common events that run anywhere can show,
    // gathered the same way, as a real body is compiled —without a map—:
    // the caller keeps the big ones, which are the cartridge's, and gives
    // them back as `common_pictures`. Only when there are some, so the
    // answer of a cartridge without them stays the one it was.
    let mut pictures = Pictures::gathering();
    for n in commons::running_anywhere(game, &indices) {
        let mut messages = Messages::measuring(request.messages_step, request.window());
        let mut songs = Songs::default();
        let mut troops = Troops::default();
        let mut ctx = Ctx {
            game,
            indices: &indices,
            sound: &sound,
            map_index: &map_index,
            messages: Some(&mut messages),
            songs: Some(&mut songs),
            graphics: None,
            pictures: Some(&mut pictures),
            troops: Some(&mut troops),
            commons: None,
            shared: None,
            losses: Losses::default(),
            face: None,
        };
        compile_page(&mut ctx, &game.common_events[&n].commands, None, 0, 0)?;
    }
    let mut answer = indices_json(&indices, &associations);
    answer.insert("maps".into(), json!(out));
    if !pictures.table.is_empty() {
        answer.insert(
            "commons_pictures".into(),
            json!({"pictures": pictures.keys_json(), "zooms": pictures.zooms_json()}),
        );
    }
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
///
/// The first pass also says **which Latin-1 letters** the cartridge draws:
/// it draws every one the font has, and the boxes that are left say which
/// they use —`Messages::letters_used`—. Those go into the console's font
/// after its 96 glyphs, and the second pass draws only them; a game in
/// English carries none, and its cartridge is the same as before there were
/// any. Whether a page compiles does not depend on it either: a letter not
/// drawn is shown as its plain stand-in.
pub fn compile(game: &Game, request: &Request) -> Result<Value> {
    let window = request.window();
    let (_, gathered) = compile_pass(
        game,
        request,
        Messages::measuring(request.messages_step, window.carrying_all()),
    )?;
    let window = window.carrying(&gathered.letters_used());
    let pairs = gathered.choose_pairs_for(window)?;
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
    // What the cartridge's pages do with less than RM2k: the maps', the
    // shared bodies', the parallel common events' and the troops'. Not the
    // test pages': they are the harness's.
    let mut losses = Losses::default();

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
            // Through the same `\V[n]` and the same waits as the page will,
            // so both find the same box: see `with_variables`.
            match compile::with_variables(&compile::with_names(&lines, &indices), &indices)
                .and_then(|l| messages.add_waiting(&l))
            {
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
    // What the test pages' boxes drop or show plain is the harness's, like
    // their other losses: the page notes it again when it compiles the same
    // box.
    messages.take_dropped();
    messages.take_plain();

    // Which common events get a shared body: the automatic ones, the ones
    // the pages that run in the foreground call —the maps' and the test
    // pages'—, and what those call. Before any page, because a page that
    // calls one carries its index: see [`commons`].
    let setting = commons::Setting {
        game,
        indices: &indices,
        sound: &request.sound,
        map_index: &map_index,
        pictures: &request.common_pictures,
    };
    let from_pages: BTreeSet<i32> = maps
        .iter()
        .flat_map(|m| m.events.iter())
        .flat_map(|e| e.pages.iter())
        .filter(|p| p.trigger != TRIGGER_PARALLEL)
        .map(|p| p.commands.as_slice())
        .chain(request.cases.iter().map(|(_, c)| c.as_slice()))
        .flat_map(|commands| commons::callees(game, commands))
        .collect();
    let plan = commons::plan(&setting, from_pages, &messages, &songs)?;
    let callers = callers(game, &maps);

    let mut maps_out = Vec::new();
    let mut cases_out: Vec<Option<String>> = vec![None; request.cases.len()];
    for (k, map) in maps.into_iter().enumerate() {
        let map = with_test_event(map, request, game);
        let subs = Rc::new(Substitutions {
            table: request
                .substitutions
                .get(&map.id)
                .cloned()
                .unwrap_or_default(),
            ..Default::default()
        });
        let panoramas = Rc::new(request.panoramas.get(&map.id).cloned().unwrap_or_default());
        let me = MapEvents::new(&map, Some(subs.clone())).with_panoramas(panoramas.clone());
        let mut graphics = Graphics::new(&associations);
        let mut pictures = request.pictures.get(&map.id).cloned().unwrap_or_default();
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
                pictures: Some(&mut pictures),
                troops: Some(&mut troops),
                commons: None,
                shared: Some(&plan.index),
                losses: std::mem::take(&mut losses),
                face: None,
            };
            let pages = map_pages(&mut ctx, &map, &me);
            losses = ctx.losses;
            pages?
        };
        songs.current = None;
        for (charset, index) in request.test_graphics.get(&map.id).into_iter().flatten() {
            graphics.index(charset, *index);
        }
        // The table the map's pages number against, which the caller checks
        // against the one it built the sprite bank with. A test page that
        // runs here numbers after it.
        let numbered = graphics.pairs.clone();
        let dropped = graphics.dropped.clone();
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
                pictures: Some(&mut pictures),
                troops: None,
                commons: None,
                shared: Some(&plan.index),
                losses: Losses::default(),
                face: None,
            };
            let code = compile_page(
                &mut ctx,
                case,
                Some(
                    MapEvents::new(&map, Some(subs.clone()))
                        .with_panoramas(panoramas.clone())
                        .numbered(&map, &indices)
                        .for_event(0),
                ),
                0,
                0,
            )?;
            // One that does not compile is null: what to do about it is the
            // caller's.
            cases_out[c] = code.map(|code| hex(&code));
        }
        // The debts: what the automatic pages that compile accept without
        // doing. With the text block and nothing else.
        // Not the copies of the automatic common events, whose shared body
        // is not looked at either: see [`with_test_event`].
        let mut debts = BTreeSet::new();
        let copy = copy_event(&map, request);
        for event in map.events.iter().filter(|e| Some(e.id) != copy) {
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
                    pictures: None,
                    troops: None,
                    commons: None,
                    shared: None,
                    losses: Losses::default(),
                    face: None,
                };
                if compile_page(&mut ctx, &page.commands, None, 0, 0)?.is_none() {
                    continue;
                }
                debts.extend(compile::page_debts(
                    game,
                    &indices,
                    &page.commands,
                    Some(&pictures),
                )?);
            }
        }
        let asked: Vec<Value> = subs
            .asked
            .borrow()
            .iter()
            .map(|(u, o, n)| json!([u, o, n]))
            .collect();
        let mut entry = json!({
            "id": map.id,
            "pages": pages,
            "graphics": numbered,
            "debts": debts,
            "substitutions": asked,
        });
        // Only when there are some, so the answer stays the one the test
        // that holds its hashes expects.
        if !dropped.is_empty() {
            entry["graphics_dropped"] = json!(dropped);
        }
        maps_out.push(entry);
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
    // The shared common event bodies themselves. After everything else, so
    // what they number goes at the end of each registry and moves nobody's
    // index.
    let commons = commons::compile(
        &setting,
        &plan,
        &mut messages,
        &mut songs,
        &mut troops,
        &mut losses,
    )?;
    // The parallel common events, each compiled once without a map, after
    // the shared bodies so what they number moves nobody's index. See
    // [`commons::parallel_commons`].
    let parallel = commons::parallel_commons(
        &setting,
        &mut messages,
        &mut songs,
        &mut troops,
        &mut losses,
    )?;
    let mut ctx = Ctx {
        game,
        indices: &indices,
        sound: &request.sound,
        map_index: &|_| None,
        messages: None,
        songs: Some(&mut songs),
        graphics: None,
        pictures: None,
        troops: None,
        commons: None,
        shared: None,
        losses: std::mem::take(&mut losses),
        face: None,
    };
    let battle_audio = if troops.ids.is_empty() {
        None
    } else {
        compile::battle_audio(&mut ctx)
    };
    let troop_window = match (request.troop_window, troops.ids.is_empty()) {
        (Some(w), _) => w,
        (None, true) => window,
        (None, false) => {
            return Err(Bad::answer(
                "the request has troops and no troop_window: their boxes are reflowed for it",
            ))
        }
    };
    let mut troop_pages = TroopPages::new(Messages::new(1, troop_window));
    for &number in &troops.ids {
        if let Some(pages) = game.troops.get(&number) {
            troop_pages.compile(&mut ctx, number, pages)?;
        }
    }
    let losses = ctx.losses.take();
    let mut answer = indices_json(&indices, &associations);
    answer.insert("degradations".into(), degradations(game, &losses, &callers));
    answer.insert("maps".into(), json!(maps_out));
    answer.insert("cases".into(), json!(cases_out));
    answer.insert(
        "messages".into(),
        json!({
            "data": hex(&messages.bytes()),
            "count": messages.count(),
            "pairs": hex(&messages.pairs.bytes()),
            "pair_first": messages.window.pair_first(),
            // The Latin-1 letters the boxes draw, in the order of their
            // indices from 96 on: the screens stage puts their glyphs there.
            "letters": messages.window.letters().iter().map(|c| c.to_string()).collect::<Vec<_>>(),
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
    answer.insert("parallel_commons".into(), json!(parallel));
    // Only when there are some, like `troop_songs`: without them the answer
    // stays the one `tests/python.rs` holds the hashes of.
    if !commons.bodies.is_empty() {
        answer.insert("commons".into(), commons.to_json());
    }
    Ok((Value::Object(answer), messages))
}

/// Who calls each common event by number: the cartridge's maps' pages,
/// with their cell, and the other common events. It is what says where a
/// loss in a common event's shared body is met while playing.
fn callers(game: &Game, maps: &[Map]) -> BTreeMap<i32, Vec<Value>> {
    let mut out: BTreeMap<i32, Vec<Value>> = BTreeMap::new();
    let called = |commands: &[Command]| -> BTreeSet<i32> {
        commands
            .iter()
            .filter(|c| c.code == CALL_EVENT && c.p(0) == Some(0))
            .filter_map(|c| c.p(1).map(|n| n as i32))
            .collect()
    };
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                for n in called(&page.commands) {
                    out.entry(n).or_default().push(json!({
                        "map": map.id, "event": event.id, "page": page.id, "x": event.x, "y": event.y,
                    }));
                }
            }
        }
    }
    for (&number, common) in &game.common_events {
        for n in called(&common.commands) {
            out.entry(n).or_default().push(json!({"common": number}));
        }
    }
    out
}

/// The answer's `degradations`: every loss, in the order the compiler met
/// them, and for each common event a loss is placed in, how it runs —its
/// trigger and switch— and who calls it. The caller sorts and writes them.
fn degradations(
    game: &Game,
    losses: &[losses::Loss],
    callers: &BTreeMap<i32, Vec<Value>>,
) -> Value {
    let commons: BTreeSet<i32> = losses
        .iter()
        .filter_map(|l| match l.path.first() {
            Some((Origin::Common(n), _)) => Some(*n),
            _ => None,
        })
        .collect();
    json!({
        "losses": losses.iter().map(losses::Loss::to_json).collect::<Vec<_>>(),
        "commons": commons
            .iter()
            .map(|n| {
                let c = game.common_events.get(n);
                let trigger = match c.map(|c| c.trigger) {
                    Some(TRIGGER_AUTOSTART) => "automatic",
                    Some(TRIGGER_PARALLEL) => "parallel",
                    _ => "called",
                };
                let switch = c.filter(|c| c.switch_flag).map(|c| c.switch_id);
                let entry = json!({
                    "trigger": trigger,
                    "switch": switch,
                    "called_from": callers.get(n).cloned().unwrap_or_default(),
                });
                (n.to_string(), entry)
            })
            .collect::<JsonMap<String, Value>>(),
    })
}

/// Writes the answer into `dir`, which is created if it is not there.
pub fn write(answer: &Value, dir: &Path) -> Result<()> {
    let io = |path: &Path, e: std::io::Error| Bad::usage(format!("{}: {e}", path.display()));
    std::fs::create_dir_all(dir).map_err(|e| io(dir, e))?;
    let path = dir.join(ANSWER_FILE);
    std::fs::write(&path, serde_json::to_string(answer).unwrap() + "\n").map_err(|e| io(&path, e))
}

#[cfg(test)]
mod common_page_tests {
    use super::*;
    use crate::game::{CommonEvent, Game};

    fn automatic(switch: i32) -> CommonEvent {
        CommonEvent {
            trigger: TRIGGER_AUTOSTART,
            switch_flag: true,
            switch_id: switch,
            commands: vec![Command::new(SHOW_PICTURE, 0, "Menu", vec![1; 14])],
        }
    }

    /// The copies of the automatic common events go in a last event of
    /// the maps that carry them, the highest number first, each on its
    /// switch; not one a custom menu replaces. On the map the test pages
    /// boot in, after theirs, which is first.
    #[test]
    fn a_map_with_copies_gets_a_last_event_with_their_pages() {
        let mut game = Game::default();
        game.common_events.insert(15, automatic(220));
        game.common_events.insert(16, automatic(221));
        game.common_events.insert(17, automatic(222));
        game.patches.menus.replaced.insert(17, 0);
        let request = Request {
            common_pages: vec![15, 16, 17],
            common_page_maps: [3, 4].into_iter().collect(),
            test_event_map: Some(4),
            ..Default::default()
        };
        let map = |id| Map {
            id,
            events: vec![Event {
                id: 1,
                x: 2,
                y: 2,
                pages: vec![],
                starting: None,
            }],
        };
        let three = with_test_event(map(3), &request, &game);
        assert_eq!(three.events.len(), 2);
        assert_eq!((three.events[0].id, three.events[1].id), (1, 2));
        assert_eq!(copy_event(&three, &request), Some(2));
        let switches: Vec<Option<i32>> = three.events[1]
            .pages
            .iter()
            .map(|p| p.condition.switch_a)
            .collect();
        assert_eq!(switches, [Some(221), Some(220)]);
        assert!(three.events[1]
            .pages
            .iter()
            .all(|p| p.trigger == TRIGGER_AUTOSTART));
        let four = with_test_event(map(4), &request, &game);
        let ids: Vec<i32> = four.events.iter().map(|e| e.id).collect();
        assert_eq!(
            ids,
            [0, 1, 2],
            "the test pages' event first, the copies' last"
        );
        assert!(four.events[0].pages.is_empty());
        assert_eq!(four.events[2].pages.len(), 2);
        assert_eq!(with_test_event(map(5), &request, &game).events.len(), 1);
    }
}
