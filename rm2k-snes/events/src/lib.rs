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

pub mod answer;
pub mod codes;
pub mod commons;
pub mod compile;
pub mod culprits;
pub mod fail;
pub mod game;
pub mod indices;
pub mod landings;
pub mod losses;
pub mod messages;
pub mod pages;
pub mod registry;
pub mod request;
pub mod route;
pub mod stage;
pub mod troops;
pub mod windows;

pub use fail::{Bad, Result};
pub use game::Game;

use crate::codes::*;
use crate::compile::{
    compile_page, encounter_backdrop, encounter_troop, Ctx, Indices, SoundSettings,
};
use crate::fail::Stop;
use crate::game::{Command, Event, Map, Patches};
use crate::landings::Landings;
use crate::losses::{Losses, Origin};
use crate::messages::{Messages, Window};
use crate::pages::{map_pages, MapEvents, SubstitutionTable, Substitutions};
use crate::registry::{BigPicture, Graphics, Package, Pictures, Songs, Troops};
use crate::troops::TroopPages;
use serde::Deserialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;
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
    /// The switch the harness's test pages would like to turn on: the
    /// answer says which one they can, `test_switch`. See
    /// [`indices::test_switch`].
    pub test_switch: Option<i32>,
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
    /// shared bodies and the parallel ones—: the big ones, which the
    /// cartridge carries once and the console shows the same on every map
    /// —see `runtime/big_picture.s`—, and the small ones of the cartridge's
    /// common table, by set, which it uploads beside the map's bank when
    /// shown —see [`registry::CommonPicture`]—. The scan gathers what they
    /// can show apart, as `commons_pictures` and `common_sets`.
    pub common_pictures: Pictures,
    /// Which set of the common pictures each body is compiled with, by
    /// whether it is a parallel one's and its number: see
    /// [`commons::picture_sets`]. The caller answers the sets the scan
    /// gave, those it kept, as `common_sets`.
    pub common_sets: BTreeMap<(bool, i32), usize>,
    /// Per map, the panoramas it carries, in the order the bytecode numbers
    /// them: its own first —or an empty name, if it starts with none— and
    /// the ones its `ChangePBG`s name after it. A map that is not here
    /// carries only its own, if it shows it. See `CHANGE_PBG` in
    /// `compile.rs`.
    pub panoramas: BTreeMap<i32, Vec<String>>,
    /// Per map, the ChipSets it can be drawn with, in the order the bytecode
    /// numbers them: its own first, then the variants the converter made of
    /// it over its grid. A map that is not here has none, and its
    /// `ChangeMapTileset`s do not compile. See `CHANGE_MAP_TILESET` in
    /// `compile.rs`.
    pub tilesets: BTreeMap<i32, Vec<i32>>,
    pub sound: SoundSettings,
    /// Each test page and the map it runs in, compiled with that map's
    /// context and as its event 0. What the caller puts in front of it —the
    /// switch a test page turns itself off with— comes in the commands.
    pub cases: Vec<(i32, Vec<Command>)>,
    /// Graphics the test pages ask for in the maps where they run.
    pub test_graphics: BTreeMap<i32, Vec<(String, i32)>>,
    /// Each map's table of route graphics as the scan numbered it, which
    /// the converter built its sprite bank with: the compilation numbers
    /// against it and does not add to it. See `Graphics::frozen`. Absent,
    /// the compilation numbers as the scan does.
    pub route_graphics: BTreeMap<i32, Vec<(String, i32)>>,
    /// How many bytes at a time `OP_MESSAGE`'s offset counts.
    pub messages_step: usize,
    /// The troops of the random encounters.
    pub encounter_troops: Vec<i32>,
}

/// A message window as a request carries it: see [`request::Window`]. A
/// window carries no letters until the compilation chooses: see
/// [`compile`].
fn window(w: &request::Window, whose: &str) -> Result<Window> {
    let lines = w.lines;
    let Some(width) = w.width else {
        let columns = w.columns.ok_or_else(|| {
            Bad::answer(format!("{whose}: a window with no `width` nor `columns`"))
        })?;
        return Ok(Window::columns(columns, lines));
    };
    let given = w
        .advances
        .as_ref()
        .ok_or_else(|| Bad::answer(format!("{whose}: a window with no `advances`")))?;
    let advances: [u8; rm2k_snes_text::font::CONSOLE_GLYPHS] =
        given.as_slice().try_into().map_err(|_| {
            Bad::answer(format!(
                "{whose}: the window's `advances` are {} and the console's font has {}",
                given.len(),
                rm2k_snes_text::font::CONSOLE_GLYPHS
            ))
        })?;
    let mut latin = [0u8; messages::LETTER_SLOTS];
    for &(letter, advance) in w.letters.iter().flatten() {
        let bad = || {
            Bad::answer(format!("{whose}: the window's `letters` are pairs of a Latin-1 letter or an icon's half and its advance: {letter:?}, {advance}"))
        };
        let advance = u8::try_from(advance)
            .ok()
            .filter(|&a| a > 0)
            .ok_or_else(bad)?;
        let slot = messages::latin_slot(letter).ok_or_else(bad)?;
        latin[slot] = advance;
    }
    Ok(Window {
        width,
        lines,
        advances,
        latin,
        carried: [0; messages::LETTER_SLOTS],
    })
}

/// A list of pictures as the caller answers them, sorted by where each is
/// carried: see [`request::Place`] and [`registry::CommonPicture`].
fn pictures_of(entries: &[request::Picture], whose: &str) -> Result<Pictures> {
    let mut pictures = Pictures::default();
    for e in entries {
        let key = e.key.key.clone();
        match e.place {
            request::Place::Background {
                image,
                center,
                texture,
                ..
            } => {
                // A byte, and $FF is the runtime's PIC_NONE: a number past
                // it would show another picture, so it is refused.
                if image == 0xFF {
                    return Err(Bad::answer(format!(
                        "{whose}: big picture {image}, and OP_BIG_SHOW's byte names 255"
                    )));
                }
                pictures.big.push(BigPicture {
                    key,
                    image,
                    center,
                    texture,
                });
            }
            request::Place::Common {
                slot, image, set, ..
            } => {
                // Bit 7 set and not $FF, PIC_NONE: see `CommonPicture`.
                if image & registry::PICTURE_COMMON == 0 || image == 0xFF {
                    return Err(Bad::answer(format!("{whose}: common picture {image}")));
                }
                pictures.common.push(registry::CommonPicture {
                    key,
                    image,
                    slot,
                    set,
                });
            }
            request::Place::Sprite { slot, .. } => {
                // See `Pictures::with_map` and `Pictures::screen_on_map`.
                if e.key.with_map {
                    pictures.with_map.push(pictures.table.len() as u8);
                }
                if e.key.screen_on_map {
                    pictures.screen_on_map.push(pictures.table.len() as u8);
                }
                pictures.table.push((key, slot));
            }
        }
    }
    Ok(pictures)
}

/// A request file: what [`Request::read`] makes into a request. A file
/// that is not there is the call being wrong; one that is not a request,
/// a no.
pub fn read_request(path: &Path) -> Result<request::Asked> {
    let text_ = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text_).map_err(|e| Bad::answer(format!("{}: {e}", path.display())))
}

impl Request {
    /// A request file. The fields only `compile` reads can be left out of
    /// a `scan`'s.
    pub fn read(path: &Path) -> Result<Request> {
        Request::from_asked(&read_request(path)?, &path.display().to_string())
    }

    /// A request as JSON, as [`Request::read`] reads it from a file.
    pub fn from_json(data: &Value, whose: &str) -> Result<Request> {
        let asked =
            request::Asked::deserialize(data).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        Request::from_asked(&asked, whose)
    }

    /// What the compiler makes of a request: the windows checked, the
    /// pictures by plane, the tables keyed for lookup.
    pub fn from_asked(a: &request::Asked, whose: &str) -> Result<Request> {
        let by_map = |m: &request::ByMap<Vec<i32>>| -> BTreeMap<i32, BTreeSet<i32>> {
            m.0.iter()
                .map(|(k, v)| (*k, v.iter().copied().collect()))
                .collect()
        };
        let mut patches = Patches {
            map_files: a.map_files.0.iter().cloned().collect(),
            dropped: by_map(&a.dropped),
            boxed_exits: by_map(&a.boxed_exits),
            boxes: a
                .boxes
                .iter()
                .map(|b| (b.from.clone(), b.to.clone()))
                .collect(),
            names: a
                .names
                .iter()
                .map(|(m, e, p, n)| ((*m, *e, *p), n.clone()))
                .collect(),
            systems: a.systems.clone(),
            counters: a
                .counters
                .iter()
                .map(|c| (c.common_event, c.variable))
                .collect(),
            ..Patches::default()
        };
        // Each custom menu, in the order the cartridge numbers them: the
        // common event it replaces, if any, and the ones it runs before a
        // page.
        for (k, m) in a.menus.iter().enumerate() {
            if let Some(n) = m.replaces_common {
                patches.menus.replaced.insert(n, k as u8);
            }
            patches.menus.before.extend(m.before.iter().copied());
        }
        let mut common_sets = BTreeMap::new();
        for (k, set) in a.common_sets.iter().enumerate() {
            for &n in &set.commons {
                common_sets.insert((set.parallel, n), k);
            }
        }
        let tables = |m: &Option<request::ByMap<Vec<(String, i32)>>>| {
            m.iter()
                .flat_map(|m| m.0.iter().cloned())
                .collect::<BTreeMap<_, _>>()
        };
        Ok(Request {
            patches,
            window: Some(window(&a.window, whose)?),
            troop_window: a
                .troop_window
                .as_ref()
                .map(|w| window(w, whose))
                .transpose()?,
            maps: a.maps.clone(),
            test_commands: a.test_commands.clone(),
            extra_variables: a.extra_variables.iter().copied().collect(),
            extra_switches: a.extra_switches.iter().copied().collect(),
            test_switch: a.test_switch,
            test_event_map: a.test_event_map,
            common_pages: a
                .common_pages
                .as_ref()
                .map(|c| c.commons.clone())
                .unwrap_or_default(),
            common_page_maps: a
                .common_pages
                .iter()
                .flat_map(|c| c.maps.iter().copied())
                .collect(),
            substitutions: a
                .substitutions
                .iter()
                .flat_map(|s| s.0.iter())
                .map(|(m, list)| {
                    let table: SubstitutionTable = list
                        .iter()
                        .map(|s| ((s.upper, s.old, s.new), s.pairs.clone()))
                        .collect();
                    (*m, table)
                })
                .collect(),
            pictures: a
                .pictures
                .iter()
                .flat_map(|p| p.0.iter())
                .map(|(m, list)| Ok((*m, pictures_of(list, whose)?)))
                .collect::<Result<_>>()?,
            common_pictures: pictures_of(&a.common_pictures, whose)?,
            common_sets,
            panoramas: a
                .panoramas
                .iter()
                .flat_map(|p| p.0.iter().cloned())
                .collect(),
            tilesets: a
                .tilesets
                .iter()
                .flat_map(|t| t.0.iter().cloned())
                .collect(),
            sound: a
                .sound_effects
                .as_ref()
                .map(|s| SoundSettings {
                    per_map: s
                        .per_map
                        .iter()
                        .map(|e| (e.effect.clone(), e.map, e.sample.clone()))
                        .collect(),
                    route_left_out: s
                        .route_effects_left_out
                        .iter()
                        .map(|r| {
                            let which = match &r.effects {
                                request::Effects::All(_) => None,
                                request::Effects::These(e) => Some(e.iter().cloned().collect()),
                            };
                            (r.map, which)
                        })
                        .collect(),
                    troop_in_package: s.troop_effects_in_package.iter().cloned().collect(),
                })
                .unwrap_or_default(),
            cases: a
                .cases
                .iter()
                .flatten()
                .map(|c| (c.map, c.commands.clone()))
                .collect(),
            test_graphics: tables(&a.test_graphics),
            route_graphics: tables(&a.route_graphics),
            messages_step: a.messages_step.unwrap_or(1),
            encounter_troops: a.encounter_troops.clone().unwrap_or_default(),
        })
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
/// shared body is compiled without a map, so without the map's pictures
/// —its small ones are the cartridge's, and go up beside the map's bank only
/// if they fit there—, and a menu built of `ShowPicture`s could work blind:
/// Frozen World's `BringUpMenu`, common 15. The copy is compiled with the
/// map, so its pictures go in the map's
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
            route_switches: Vec::new(),
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
fn indices_answer(indices: &Indices, associations: &[(String, i32)]) -> answer::Indices {
    answer::Indices {
        variables: indices
            .variables
            .iter()
            .map(|(&v, &s)| (v.into(), s as i64))
            // The high words of the wide variables, as the variable's
            // number negated: the caller counts the slots by this list
            // —`VARIABLES_N`— and looks a variable up by its number, which
            // is never negative. See `indices::wide`.
            .chain(
                indices
                    .wide
                    .iter()
                    .map(|(&v, &s)| (-i64::from(v), s as i64)),
            )
            .collect(),
        skills: indices
            .skills
            .iter()
            .map(|(&(a, h), &s)| (a.into(), h.into(), s as i64))
            .collect(),
        switch_top: indices.switch_top.into(),
        // And the one the test pages can turn on, if they asked.
        test_switch: indices.test_switch.map(i64::from),
        // The names `ChangeHeroName` gives, in the order `OP_CHANGE_NAME`
        // counts them: the converter writes their texts and the table of
        // the renamed actors from this.
        names: indices
            .renames
            .iter()
            .map(|(a, n)| (i64::from(*a), n.clone()))
            .collect(),
        // The faces the message window shows, in the order `OP_FACE`
        // counts them: the converter draws them from this.
        faces: indices
            .faces
            .iter()
            .map(|(f, i, m)| (f.clone(), i64::from(*i), *m))
            .collect(),
        associations: associations.to_vec(),
    }
}

/// The indices, the graphics actors can be given, the cartridge's maps, and
/// the graphics its pages give after jumping to each of them.
type Prepared = (Indices, Vec<(String, i32)>, Vec<Map>, Rc<Landings>);

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
    indices.wide = indices::wide(
        game,
        &every,
        &request.test_commands,
        &request.extra_variables,
        &indices.variables,
    );
    if let Some(wanted) = request.test_switch {
        let switch = indices::test_switch(game, &every, &extra_switches, wanted)?;
        indices.switch_top = indices.switch_top.max(switch);
        indices.test_switch = Some(switch);
    }
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
    // The common events that run on any map: the automatic ones, and the
    // ones the test pages call, which run where the harness puts them.
    let everywhere: BTreeSet<i32> = commons::automatic(game, &indices)
        .into_iter()
        .map(|(n, _)| n)
        .chain(commons::callees(game, &request.test_commands))
        .collect();
    let landings = Landings::gather(
        &maps,
        &game.common_events,
        &associations,
        &everywhere,
        |m| request.maps.iter().any(|&id| id as i64 == m),
    );
    Ok((indices, associations, maps, Rc::new(landings)))
}

/// The first call: the indices, which pages of each map compile, and each
/// map's pages compiled without songs, pictures or troops.
pub fn scan(game: &Game, request: &Request) -> Result<answer::Scan> {
    let (indices, associations, maps, landings) = prepare(game, request)?;
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
                    landings: Some(&*landings),
                    jump: None,
                    decision_key: compile::decision_key(page.trigger),
                };
                if let Some(code) =
                    compile_page(&mut ctx, &page.commands, Some(me.for_event(event.id)), 0, 0)?
                {
                    compiled.push((e, p, answer::Hex(code)));
                }
            }
        }
        // The pages as the map has them, with a text block of its own and
        // without songs: who walks and which graphics a route changes to.
        let map = with_test_event(map.clone(), request, game);
        let me = MapEvents::new(&map, None).numbered(&map, &indices);
        let mut messages = Messages::new(1, request.window());
        let mut graphics = landings.graphics(map.id);
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
            landings: Some(&*landings),
            jump: None,
            decision_key: None,
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
                    event.pages.iter().map(move |page| {
                        (
                            event.id,
                            compile::decision_key(page.trigger),
                            &page.commands,
                        )
                    })
                })
        };
        let cases = request
            .cases
            .iter()
            .filter(|(run_map, _)| *run_map == map.id)
            .map(|(_, case)| (0, None, case));
        let mut own = None;
        let copies = pages_of(true).map(Some);
        for event in pages_of(false)
            .chain(cases)
            .map(Some)
            .chain([None])
            .chain(copies)
        {
            let Some((event, key, commands)) = event else {
                own = Some(pictures.table.len());
                continue;
            };
            // Its texts are only measured, with the cartridge's step: a test
            // page can carry more than sixty-four kilobytes of them —the one
            // that pads the text block does—.
            let mut messages = Messages::measuring(request.messages_step, request.window());
            let mut songs = Songs::default();
            let mut graphics = landings.graphics(map.id);
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
                landings: Some(&*landings),
                jump: None,
                decision_key: key,
            };
            compile_page(&mut ctx, commands, Some(me.for_event(event)), 0, 0)?;
            on_events.extend(graphics.on_events);
        }
        out.push(answer::ScanMap {
            id: map.id,
            compiled,
            pages,
            graphics: pairs(&graphics.pairs),
            pictures: pictures.keys(),
            zooms: pictures.zooms.clone(),
            tinted: pictures.tinted.iter().map(|&n| n.into()).collect(),
            // Only on a map with copies, so the answer of the rest stays
            // the one it was.
            pictures_own: own.filter(|_| request.common_page_maps.contains(&map.id)),
            // Which of them a route gives an event, the test pages' too:
            // the rest only the hero shows.
            graphics_on_events: pairs(&on_events),
        });
    }
    // And the pictures the common events that run anywhere can show,
    // gathered the same way, as a real body is compiled —without a map—,
    // each one's apart: the caller keeps the big ones, which are the
    // cartridge's, and gives them back as `common_pictures`. Only a body
    // that compiles: one that does not never shows them, and each big
    // picture costs cartridge. Only when there are some, so the answer of a
    // cartridge without them stays the one it was.
    let mut gathered = Vec::new();
    for n in commons::running_anywhere(game, &indices) {
        let mut messages = Messages::measuring(request.messages_step, request.window());
        let mut songs = Songs::default();
        let mut troops = Troops::default();
        let mut pictures = Pictures::gathering();
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
            landings: Some(&*landings),
            jump: None,
            decision_key: Some(false),
        };
        let compiles = compile_page(&mut ctx, &game.common_events[&n].commands, None, 0, 0)?;
        if compiles.is_some() && !pictures.table.is_empty() {
            gathered.push(answer::CommonPictures {
                common: n,
                pictures: pictures.keys(),
                zooms: pictures.zooms.clone(),
            });
        }
    }
    // And their small ones, by set: see [`commons::picture_sets`]. Each
    // body gathered as it is compiled: a shared one with its calls as calls,
    // a parallel one with them pasted.
    let every: BTreeMap<i32, u8> = game.common_events.keys().map(|&n| (n, 0)).collect();
    let sets = commons::picture_sets(game, &indices, &mut |n, paste| {
        let mut messages = Messages::measuring(request.messages_step, request.window());
        let mut songs = Songs::default();
        let mut troops = Troops::default();
        let mut pictures = Pictures::gathering();
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
            commons: (!paste).then_some(&every),
            shared: None,
            losses: Losses::default(),
            face: None,
            landings: Some(&*landings),
            jump: None,
            decision_key: Some(false),
        };
        let compiles = compile_page(&mut ctx, &game.common_events[&n].commands, None, 0, 0)?;
        Ok(compiles.map(|_| pictures))
    })?;
    let common_sets = sets
        .iter()
        .map(|set| answer::CommonSet {
            parallel: set.parallel,
            commons: set.commons.clone(),
            pictures: set.pictures.keys(),
            tinted: set.pictures.tinted.iter().map(|&n| n.into()).collect(),
        })
        .collect();
    Ok(answer::Scan {
        indices: indices_answer(&indices, &associations),
        maps: out,
        commons_pictures: gathered,
        common_sets,
    })
}

/// `(name, index)` pairs as an answer carries them.
fn pairs<'a>(list: impl IntoIterator<Item = &'a (String, i32)>) -> Vec<(String, i64)> {
    list.into_iter()
        .map(|(g, i)| (g.clone(), (*i).into()))
        .collect()
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
pub fn compile(game: &Game, request: &Request) -> Result<answer::Compiled> {
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
/// there were pairs. No cartridge uses it: the tests compare against it
/// that the pairs write the same boxes.
pub fn compile_without_pairs(game: &Game, request: &Request) -> Result<answer::Compiled> {
    let messages = Messages::new(request.messages_step, request.window());
    Ok(compile_pass(game, request, messages)?.0)
}

fn compile_pass(
    game: &Game,
    request: &Request,
    mut messages: Messages,
) -> Result<(answer::Compiled, Messages)> {
    let (indices, associations, maps, landings) = prepare(game, request)?;
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
        sets: &request.common_sets,
        landings: Some(&*landings),
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
    // Which parallel common events' switches each map can turn on, and
    // which any map can: their effects go in those maps' packages, after
    // compiling them. See [`commons::turned_on`].
    let parallel_switches: BTreeSet<i32> = game
        .common_events
        .values()
        .filter(|c| c.trigger == COMMON_PARALLEL && c.switch_flag)
        .map(|c| c.switch_id)
        .collect();
    let mut switches_on: Vec<BTreeSet<i32>> = vec![BTreeSet::new(); maps.len()];
    for (k, m) in maps.iter().enumerate() {
        let pages = m
            .events
            .iter()
            .flat_map(|e| &e.pages)
            .map(|p| p.commands.as_slice());
        let turned = commons::turned_on(game, pages, &parallel_switches);
        switches_on[k].extend(turned.here);
        for (dest, on) in turned.at {
            if let Some(d) = map_index(dest as i64) {
                switches_on[d].extend(on);
            }
        }
    }
    let switches_anywhere = commons::turned_on_anywhere(game, &parallel_switches);

    let mut maps_out = Vec::new();
    let mut cases_out: Vec<Option<answer::Hex>> = vec![None; request.cases.len()];
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
        let tilesets = Rc::new(request.tilesets.get(&map.id).cloned().unwrap_or_default());
        let me = MapEvents::new(&map, Some(subs.clone()))
            .with_panoramas(panoramas.clone())
            .with_tilesets(tilesets.clone());
        // The scan's table, when the converter passes it: see
        // `Graphics::frozen`.
        let mut graphics = match request.route_graphics.get(&map.id) {
            Some(table) => Graphics {
                on_events: landings.graphics(map.id).on_events,
                ..Graphics::frozen(table)
            },
            None => landings.graphics(map.id),
        };
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
                landings: Some(&*landings),
                jump: None,
                decision_key: None,
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
                landings: Some(&*landings),
                jump: None,
                decision_key: None,
            };
            let code = compile_page(
                &mut ctx,
                case,
                Some(
                    MapEvents::new(&map, Some(subs.clone()))
                        .with_panoramas(panoramas.clone())
                        .with_tilesets(tilesets.clone())
                        .numbered(&map, &indices)
                        .for_event(0),
                ),
                0,
                0,
            )?;
            // One that does not compile is null: what to do about it is the
            // caller's.
            cases_out[c] = code.map(answer::Hex);
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
                    landings: Some(&*landings),
                    jump: None,
                    decision_key: Some(false),
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
        maps_out.push(answer::CompiledMap {
            id: map.id,
            pages,
            graphics: pairs(&numbered),
            debts,
            substitutions: subs.asked.borrow().clone(),
            graphics_dropped: pairs(&dropped),
        });
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
    let (parallel, parallel_sounds) = commons::parallel_commons(
        &setting,
        &mut messages,
        &mut songs,
        &mut troops,
        &mut losses,
    )?;
    for (switch, names) in &parallel_sounds {
        for (k, on) in switches_on.iter().enumerate() {
            if *switch == 0 || switches_anywhere.contains(switch) || on.contains(switch) {
                songs.note_sounds(Package::Map(k), names);
            }
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
        pictures: None,
        troops: None,
        commons: None,
        shared: None,
        losses: std::mem::take(&mut losses),
        face: None,
        landings: None,
        jump: None,
        decision_key: None,
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
    let answer = answer::Compiled {
        indices: indices_answer(&indices, &associations),
        degradations: degradations(game, &losses, &callers),
        maps: maps_out,
        cases: cases_out,
        messages: answer::Messages {
            data: answer::Hex(messages.bytes()),
            count: messages.count(),
            pairs: answer::Hex(messages.pairs.bytes()),
            pair_first: messages.window.pair_first(),
            // The screens stage puts their glyphs from index 96 on.
            letters: messages
                .window
                .letters()
                .iter()
                .map(char::to_string)
                .collect(),
        },
        songs: songs.answer(),
        troops: answer::Troops {
            ids: troops.ids.clone(),
            backdrops: troops
                .backdrops
                .iter()
                .map(|(n, b)| match b {
                    registry::Backdrop::Named(s) => (*n, Some(s.clone())),
                    registry::Backdrop::Place => (*n, None),
                })
                .collect(),
        },
        troop_pages: troop_pages.answer(),
        battle_audio,
        parallel_commons: parallel,
        // Only when there are some, like `troop_songs`.
        commons: (!commons.bodies.is_empty()).then(|| commons.answer()),
    };
    Ok((answer, messages))
}

/// Who calls each common event by number: the cartridge's maps' pages,
/// with their cell, and the other common events. It is what says where a
/// loss in a common event's shared body is met while playing.
fn callers(game: &Game, maps: &[Map]) -> BTreeMap<i32, Vec<losses::Where>> {
    let mut out: BTreeMap<i32, Vec<losses::Where>> = BTreeMap::new();
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
                    let page = Origin::Page {
                        map: map.id,
                        event: event.id,
                        page: Some(page.id),
                        x: event.x,
                        y: event.y,
                    };
                    out.entry(n).or_default().push(page.place());
                }
            }
        }
    }
    for (&number, common) in &game.common_events {
        for n in called(&common.commands) {
            out.entry(n)
                .or_default()
                .push(Origin::Common(number).place());
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
    callers: &BTreeMap<i32, Vec<losses::Where>>,
) -> answer::Degradations {
    let commons: BTreeSet<i32> = losses
        .iter()
        .filter_map(|l| match l.path.first() {
            Some((Origin::Common(n), _)) => Some(*n),
            _ => None,
        })
        .collect();
    answer::Degradations {
        losses: losses.iter().map(losses::Loss::entry).collect(),
        commons: commons
            .iter()
            .map(|n| {
                let c = game.common_events.get(n);
                let trigger = match c.map(|c| c.trigger) {
                    Some(TRIGGER_AUTOSTART) => "automatic",
                    Some(TRIGGER_PARALLEL) => "parallel",
                    _ => "called",
                };
                let run = losses::CommonRun {
                    trigger: trigger.to_string(),
                    switch: c.filter(|c| c.switch_flag).map(|c| c.switch_id),
                    called_from: callers.get(n).cloned().unwrap_or_default(),
                };
                (*n, run)
            })
            .collect(),
    }
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
