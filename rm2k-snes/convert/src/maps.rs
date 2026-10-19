//! A whole map, converted: its layers, its sprites, its blocks and its VRAM
//! layout, gathered into what the emission reads.
//!
//! **The conversion is `wally map`'s**, one call per map: it reads the map
//! from the dump, draws and converts its layers, bakes the opaque events
//! into them, splits the object palettes and builds the sprite bank. What
//! is here is what the stage gets from other domains —the event compiler's
//! scan of the map's pages, from which the stage says who walks, and which
//! graphics the routes change to; the test cases; the timer's System, the
//! pictures and whether a battle animation is drawn; the
//! `TileSubstitution`s that can run in the map— and what the rest of the
//! conversion reads back of its answer.

use crate::animations::{self, Animations};
use crate::compiler;
use crate::fail::{Result, Stop};
use crate::game::{Command, Event, Game, GameMap, COPY_SUFFIX, TILE_PREFIX};
use crate::pictures::{self, Big, ForMap};
use crate::settings::Settings;
use crate::stage;
use crate::text::round0;
use rm2k_snes_events::codes::{FLASH_SPRITE, MOVE_EVENT, TILE_SUBSTITUTION};
use rm2k_snes_mapdata::vram;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::ffi::OsString;
use std::path::{Path, PathBuf};

const STAGE: &str = "wally";

/// `MoveEvent`'s targets that are not an event: the hero, and "this
/// event", the page's owner.
pub const ROUTE_HERO: i32 = 10001;
pub const ROUTE_THIS_EVENT: i32 = 10005;

/// The background layers' palettes: the lower half of CGRAM. How many
/// the upper layer takes comes from what the background does not need.
pub const BG_PALETTES: i64 = 8;

/// The tiles of the 8bpp background, 64 bytes each, and of the 4bpp layers,
/// 32.
const BYTES_PER_TILE: usize = rm2k_snes_mapdata::snes::BYTES_PER_TILE;

/// What a graphic is: a CharSet, its character and its pose.
pub type Graphic = (String, i64, i64);

/// The name of the made-up sheet of an event drawn with upper-layer tile
/// `index` of a ChipSet.
pub fn tile_name(chipset: &str, index: i32) -> String {
    format!("{TILE_PREFIX}{chipset}:{index}")
}

/// What a page draws: `(CharSet, index, pose)`, or None if nothing. Those
/// drawn with a ChipSet tile go with a made-up CharSet; tile 0 is "no
/// graphic". The walk is four phases over three columns: the fourth draws
/// the second.
pub fn page_graphic(page: &crate::game::Page, chipset: &str) -> Option<Graphic> {
    if page.character_name.is_empty() && page.character_index == 0 {
        return None;
    }
    let column = if page.pattern == 3 { 1 } else { page.pattern };
    Some(if page.character_name.is_empty() {
        (
            tile_name(chipset, page.character_index),
            0,
            (page.direction * 3 + column) as i64,
        )
    } else {
        (
            page.character_name.clone(),
            page.character_index as i64,
            (page.direction * 3 + column) as i64,
        )
    })
}

/// The four passage bits an event drawn with `charset` on `layer` imposes
/// on its cell, or None: `Game_Map::IsPassableTile`'s rule —an event on
/// the lower layer drawn with a tile replaces the terrain's passability
/// with its tile's, unless the tile goes above—.
pub fn event_tile_passability(flags: &[u8], charset: &str, layer: i32) -> Option<i64> {
    let base = match charset.find(&format!("{}:", crate::game::BAKED_SUFFIX)) {
        Some(at) => &charset[..at],
        None => charset,
    };
    if layer != 0 || !base.starts_with(TILE_PREFIX) {
        return None;
    }
    let index: usize = base.rsplit(':').next()?.parse().ok()?;
    let value = flags[rm2k_rules::chipset::UPPER as usize + index];
    if value & rm2k_rules::passability::ABOVE != 0 {
        return None;
    }
    Some((value & rm2k_rules::passability::ALL) as i64)
}

/// The translation of a map's event ids to the ROM's table: **RM2k's
/// event id is not the index**, there are maps with gaps in the numbering.
pub fn route_target(events: &[Event], who: i32) -> Option<usize> {
    if who == ROUTE_HERO {
        return Some(0);
    }
    if who == ROUTE_THIS_EVENT {
        return None;
    }
    events.iter().position(|e| e.id == who).map(|n| n + 1)
}

/// How many maps of the ROM each (CharSet, index) appears in. The palette
/// split uses it to choose who can lose a colour without breaking
/// anything: the pose bank is the whole ROM's, so a character that is in
/// two maps has to be quantized the same in both.
pub fn maps_per_character(maps: &[&GameMap]) -> BTreeMap<(String, i32), usize> {
    let mut counts = BTreeMap::new();
    for map in maps {
        let mut theirs = BTreeSet::new();
        for event in &map.events {
            for page in &event.pages {
                let name = page.character_name.trim();
                if !name.is_empty() {
                    theirs.insert((name.to_string(), page.character_index));
                }
            }
        }
        for c in theirs {
            *counts.entry(c).or_insert(0) += 1;
        }
    }
    counts
}

/// If something flashes the hero, the NPCs with a leader's graphic go with
/// another palette. On the console the flash is done on the character's
/// palette, and a leader that is also an NPC in the map shares a palette
/// with that NPC, so both flashed. It is solved by counting those NPCs'
/// graphic as another one, with `COPY_SUFFIX`: the same drawing, with its
/// own palette. `commands` are those of the test pages that run here.
pub fn separate_from_hero(
    game: &Game,
    map: &mut GameMap,
    leaders: &[i32],
    commands: &[Command],
) -> Result<()> {
    let flashes = commands
        .iter()
        .chain(map.all_commands())
        .any(|c| c.code == FLASH_SPRITE && c.parameters.first() == Some(&ROUTE_HERO));
    if !flashes {
        return Ok(());
    }
    let mut owned = HashSet::new();
    for actor in leaders {
        let a = game.db.actor(*actor)?;
        owned.insert((a.character_name.clone(), a.character_index));
    }
    for event in &mut map.events {
        for page in &mut event.pages {
            if owned.contains(&(page.character_name.clone(), page.character_index)) {
                page.character_name.push_str(COPY_SUFFIX);
            }
        }
    }
    Ok(())
}

/// The `(upper layer, old, new)` of the `TileSubstitution`s in `lists`,
/// each once, in the order they are met.
pub fn substitution_triples<'a>(
    lists: impl IntoIterator<Item = &'a Command>,
    into: &mut Vec<(bool, i32, i32)>,
) {
    for cmd in lists {
        if cmd.code != TILE_SUBSTITUTION || cmd.parameters.len() < 3 {
            continue;
        }
        let p = &cmd.parameters;
        let triple = (p[0] != 0, p[1], p[2]);
        if !into.contains(&triple) {
            into.push(triple);
        }
    }
}

/// The common events' `TileSubstitution`s, which a `CallEvent` can bring
/// into any map.
pub fn common_substitutions(game: &Game) -> Vec<(bool, i32, i32)> {
    let mut out = Vec::new();
    for commands in game.db.common_events.values() {
        substitution_triples(commands.iter(), &mut out);
    }
    out
}

/// What the cartridge as a whole decided before converting its maps: what
/// every map's request carries.
pub struct Cartridge<'a> {
    pub game: &'a Game,
    pub settings: &'a Settings<'a>,
    pub scan: &'a Value,
    pub order: Vec<i32>,
    pub start_index: usize,
    pub has_cases: bool,
    /// The test cases, as `(map where it runs, commands)`.
    pub cases: Vec<(i32, Vec<Command>)>,
    pub test_graphics: Option<Vec<(String, i32)>>,
    pub test_maps: BTreeSet<i32>,
    pub leaders: Vec<i32>,
    pub timer_maps: BTreeSet<i32>,
    pub with_rain: bool,
    /// The maps whose way of showing their panorama the project forces:
    /// `[maps] panorama_ways`, which can be missing. Every other map's is
    /// Wally's to decide: see `Way` in its `background::panorama`.
    pub panorama_ways: BTreeMap<i32, String>,
    pub maps_per_character: BTreeMap<(String, i32), usize>,
    pub search_dirs: Vec<PathBuf>,
    pub common_substitutions: Vec<(bool, i32, i32)>,
    /// The pictures that are part of each map: see [`crate::map_pictures`].
    pub map_pictures: crate::map_pictures::MapPictures,
    /// The colour-memory entries the message window takes: see
    /// [`crate::screens::window_colors`].
    pub window_colors: u32,
    /// The automatic common events copied into the maps: see
    /// [`crate::common_pages`].
    pub common_pages: crate::common_pages::CommonPages,
}

impl Cartridge<'_> {
    /// The commands of the test pages that run in `map_id`.
    fn case_commands(&self, map_id: i32) -> Vec<Command> {
        self.cases
            .iter()
            .filter(|(m, _)| *m == map_id)
            .flat_map(|(_, c)| c.iter().cloned())
            .collect()
    }
}

/// A map as it goes to the stage.
pub struct Prepared {
    pub map: GameMap,
    pub chipset_filename: String,
    pub passability: Vec<u8>,
    pub route_graphics: Vec<(String, i64)>,
    pub pictures: Option<ForMap>,
    /// The map's own pictures, without those of the common events copied
    /// into it, when those have some: what goes in if theirs do not fit.
    /// See [`crate::common_pages`].
    pub pictures_own: Option<Option<ForMap>>,
    pub big_pictures: Vec<Big>,
    /// The small pictures the map shows over a black screen, as big ones:
    /// what goes in the background layer if the sprites have no room for the
    /// map's pictures. See [`pictures::over_black`].
    pub big_over_black: Vec<Big>,
    pub request: Value,
}

/// The game's System, for the timer's digits: in the game's `System/`,
/// then in the game's folder itself, and then in the RTP's `System/`;
/// without regard to case, as RPG_RT finds it. The project's
/// `[graphics] system` comes before the database's, and if it is a picture
/// of its own —see `system_choice`— it is not looked for.
fn system_path(game: &Game) -> Result<PathBuf> {
    let name = game.system.as_ref().unwrap_or(&game.db.system_name);
    let own = PathBuf::from(name);
    if own.is_absolute() {
        return Ok(own);
    }
    let rtp: Vec<PathBuf> = game.rtp_dir.iter().cloned().collect();
    crate::resources::find(&[&game.game_dir], "System", name, &[".png", ".bmp"])
        .or_else(|| Some(game.game_dir.join(format!("{name}.png"))).filter(|p| p.exists()))
        .or_else(|| crate::resources::find(&rtp, "System", name, &[".png", ".bmp"]))
        .map(|p| rm2k_project::absolute(&p))
        .ok_or_else(|| {
            Stop::new(format!(
                "System {} is not in {}",
                crate::text::repr(name),
                game.game_dir.display()
            ))
        })
}

pub fn prepare(c: &Cartridge, animations: &mut Animations, map_id: i32) -> Result<Prepared> {
    let game = c.game;
    let mut map = game.map(map_id)?;
    let chipset = game.chipset(map.chipset_id)?;
    let chipset_filename = chipset.chipset_name.clone();
    let passability = rm2k_rules::chipset::passability_table(
        &chipset.passable_data_lower,
        &chipset.passable_data_upper,
    );
    let test_event = c.has_cases && map_id == c.order[c.start_index];
    if test_event {
        // The test page's event goes **first**: the ROM walks the events
        // from lowest to highest, and the test page has to run before the
        // game's. It has no pages: it only takes index 0 so that
        // everything that numbers events after reading the map numbers
        // the same. The stage puts its own.
        map.events.insert(
            0,
            Event {
                id: 0,
                x: 0,
                y: 0,
                pages: Vec::new(),
            },
        );
    }
    // And the one with the copies of the automatic common events, last:
    // see [`crate::common_pages`]. Wally does not know it, as it does not
    // know a page the compiler adds: it has no graphic and walks nowhere.
    if let Some(event) = c.common_pages.event(game, &map) {
        map.events.push(event);
    }
    let case_commands = c.case_commands(map_id);
    separate_from_hero(game, &mut map, &c.leaders, &case_commands)?;

    // Who is going to walk and which graphics the routes change to: it
    // comes from the compiler's first call, which walked the bytecode.
    // **The order has to be the same as the real compilation's**, because
    // the bytecode carries the index.
    let scanned = compiler::map_entry(c.scan, map_id)?;
    let mut route_graphics: Vec<(String, i64)> = scanned["graphics"]
        .as_array()
        .map(|list| {
            list.iter()
                .map(|g| {
                    (
                        g[0].as_str().unwrap_or("").to_string(),
                        g[1].as_i64().unwrap_or(0),
                    )
                })
                .collect()
        })
        .unwrap_or_default();
    // And the ones from `--test-graphic`, only in the maps where some case
    // runs, **after** the game's, which is the order the real compilation
    // numbers them in.
    if let Some(graphics) = &c.test_graphics {
        if c.test_maps.contains(&map_id) {
            for (charset, index) in graphics {
                let g = (charset.clone(), *index as i64);
                if !route_graphics.contains(&g) {
                    route_graphics.push(g);
                }
            }
        }
    }
    // The ones no route gives an event —the scan says which ones some
    // does, the test pages' too—: only the hero shows them, and Wally can
    // draw them in the leaders' palette, like a leader.
    let on_events: Vec<(String, i64)> = scanned
        .get("graphics_on_events")
        .and_then(Value::as_array)
        .map(|list| {
            list.iter()
                .map(|g| {
                    (
                        g[0].as_str().unwrap_or("").to_string(),
                        g[1].as_i64().unwrap_or(0),
                    )
                })
                .collect()
        })
        .unwrap_or_default();
    let hero_graphics: Vec<Value> = route_graphics
        .iter()
        .filter(|g| !on_events.contains(g))
        .map(|(g, i)| json!([g, i]))
        .collect();
    // And the ones the test pages send walking, which don't come from the
    // map's pages: they have to be added by hand or the NPC would walk
    // with a single pose.
    let mut also_walk = BTreeSet::new();
    for cmd in &case_commands {
        if cmd.code == MOVE_EVENT && !cmd.parameters.is_empty() && cmd.parameters[0] != ROUTE_HERO {
            if let Some(target) = route_target(&map.events, cmd.parameters[0]) {
                if target > 0 {
                    also_walk.insert(target - 1);
                }
            }
        }
    }

    let timer = if c.timer_maps.contains(&map_id) {
        Value::String(system_path(game)?.to_string_lossy().to_string())
    } else {
        Value::Null
    };
    // The `ShowPicture` pictures this map's pages and test pages can show,
    // which the scan gathered.
    let mut keys: Vec<Value> = scanned
        .get("pictures")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    // The map's own come first, and then those only the copies of the
    // common events show, if the map carries them: the scan says how many
    // are its own. See [`crate::common_pages`].
    let mut own_keys: Option<Vec<Value>> = scanned
        .get("pictures_own")
        .and_then(Value::as_u64)
        .filter(|&n| (n as usize) < keys.len())
        .map(|n| keys[..n as usize].to_vec());
    // The ones that are part of a map are drawn into it, and their commands
    // are accepted without being done.
    keys.retain(|k| {
        !c.map_pictures
            .done(map_id, k["name"].as_str().unwrap_or(""))
    });
    if let Some(own) = own_keys.as_mut() {
        own.retain(|k| {
            !c.map_pictures
                .done(map_id, k["name"].as_str().unwrap_or(""))
        });
    }
    // And the numbers the map tones, which do not share a palette.
    let tinted: Vec<i64> = scanned
        .get("tinted")
        .and_then(Value::as_array)
        .map(|t| t.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default();
    let pictures = pictures::for_map(&game.game_dir, &keys, &tinted, map_id, &game.cropped)?;
    let pictures_own = match &own_keys {
        Some(own) => Some(pictures::for_map(
            &game.game_dir,
            own,
            &tinted,
            map_id,
            &game.cropped,
        )?),
        None => None,
    };
    let singles: Vec<Value> = c
        .maps_per_character
        .iter()
        .filter(|(_, n)| **n == 1)
        .map(|((name, index), _)| json!([name, index]))
        .collect();
    let zooms: Vec<Value> = scanned
        .get("zooms")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let big_pictures = pictures::big_for_map(
        &game.game_dir,
        &keys,
        &zooms,
        &format!("map {map_id}"),
        &game.cropped,
        &|_| false,
    )?;
    // And the small ones the map shows over a black screen, in the
    // background layer too: what goes in if the sprites have no room for
    // the map's pictures. See [`pictures::over_black`].
    let black = pictures::over_black(&map);
    let big_over_black = if black.is_empty() {
        Vec::new()
    } else {
        let already: Vec<&Value> = big_pictures.iter().map(|b| &b.key).collect();
        let small: Vec<Value> = keys
            .iter()
            .filter(|k| pictures::shown_over_black(k, &black) && !already.contains(k))
            .cloned()
            .collect();
        pictures::big_for_map(
            &game.game_dir,
            &small,
            &zooms,
            &format!("map {map_id}"),
            &game.cropped,
            &|_| true,
        )?
    };
    let shows_animation =
        animations.map_shows_animation(game, map.all_commands(), &case_commands)?;
    let mut triples = Vec::new();
    let mut lists: Vec<&Command> = map.all_commands().collect();
    for (m, cmds) in &c.cases {
        if *m == map_id {
            lists.extend(cmds.iter());
        }
    }
    substitution_triples(lists, &mut triples);
    let mut request = json!({
        "map": map_id,
        "map_files": compiler::map_files(game),
        "dropped_events": game.dropped_json_of(map_id),
        "chipset_files": compiler::chipset_files(game),
        "names": compiler::names([&map]).into_iter().map(|e| json!([e[1], e[2], e[3]])).collect::<Vec<_>>(),
        "test_event": test_event,
        "leaders": c.leaders,
        "pages": scanned["pages"],
        "route_graphics": route_graphics.iter().map(|(g, i)| json!([g, i])).collect::<Vec<_>>(),
        "hero_graphics": hero_graphics,
        "also_walk": also_walk.into_iter().collect::<Vec<_>>(),
        // What the test pages name, so a decorative event is never one a
        // test moves: only when the project asks for them.
        "decorative": game.decorative,
        "test_commands": if game.decorative {
            case_commands.iter().map(|c| json!([c.code, c.parameters])).collect::<Vec<_>>()
        } else {
            Vec::new()
        },
        "timer": timer,
        "map_pictures": c.map_pictures.of(map_id).iter().map(|p| p.to_json()).collect::<Vec<_>>(),
        "rain": c.with_rain,
        "picture": pictures.as_ref().map(|p| p.asked.clone()),
        "battle_animation": shows_animation,
        "singles": singles,
        "palette_weight": c.settings.table(&["graphics", "palette_weight"])?,
        "dither": std::env::var("DITHER_PATTERN").unwrap_or_else(|_| "five_of_eight".to_string()),
        // The `TileSubstitution`s that can run here, whose blocks the stage
        // builds before any page compiles, and the common events', which it
        // only translates.
        "substitutions": triples.iter().map(|(u, o, n)| json!([u, o, n])).collect::<Vec<_>>(),
        "common_substitutions": c.common_substitutions.iter().map(|(u, o, n)| json!([u, o, n])).collect::<Vec<_>>(),
        // The VRAM layouts a map can get, and the ones for a map that shows
        // its panorama, which Wally decides.
        "layouts": vram::LAYOUTS
            .iter()
            .filter(|l| l.panorama.is_none())
            .map(|l| json!([l.tiles.count, l.sprites.count, l.above.count]))
            .collect::<Vec<_>>(),
        "panorama": {
            "layouts": vram::LAYOUTS
                .iter()
                .filter_map(|l| l.panorama.map(|p| json!([p.mode, l.tiles.count, l.sprites.count, l.above.count, p.count()])))
                .collect::<Vec<_>>(),
            "baked_tiles": vram::LAYOUTS.iter().filter(|l| l.panorama.is_none()).map(|l| l.tiles.count).max(),
            "way": c.panorama_ways.get(&map_id),
        },
        // Where the background starts: after the backdrop and the window.
        "window_colors": c.window_colors,
    });
    // Only when the project asks: a request without the key is the one a
    // game always got.
    if game.painted_maps {
        request["panorama"]["painted"] = json!(true);
    }
    // Only on a map whose copies of common events show pictures of their
    // own: see `picture_own` in Wally.
    if let Some(own) = &pictures_own {
        request["picture_own"] = own.as_ref().map_or(Value::Null, |p| p.asked.clone());
    }
    Ok(Prepared {
        map,
        chipset_filename,
        passability,
        route_graphics,
        pictures,
        pictures_own,
        big_pictures,
        big_over_black,
        request,
    })
}

/// Runs the stage on every prepared map, in parallel, and hands back what
/// each wrote, in order.
pub fn run_all(c: &Cartridge, prepared: &[Prepared]) -> Result<Vec<BTreeMap<String, Vec<u8>>>> {
    let mut flags: Vec<OsString> = vec!["--data".into(), c.game.dump.clone().into_os_string()];
    for dir in &c.search_dirs {
        flags.push("--search-dir".into());
        flags.push(rm2k_project::absolute(dir).into_os_string());
    }
    let workers = std::thread::available_parallelism()
        .map_or(1, |n| n.get())
        .min(prepared.len())
        .max(1);
    let next = std::sync::atomic::AtomicUsize::new(0);
    let results: Vec<std::sync::Mutex<Option<Result<BTreeMap<String, Vec<u8>>>>>> = prepared
        .iter()
        .map(|_| std::sync::Mutex::new(None))
        .collect();
    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| loop {
                let k = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                if k >= prepared.len() {
                    break;
                }
                let done = stage::run(STAGE, "wally", "map", &prepared[k].request, &flags)
                    .map_err(|e| e.in_map(prepared[k].map.id));
                *results[k].lock().unwrap() = Some(done);
            });
        }
    });
    results
        .into_iter()
        .map(|r| r.into_inner().unwrap().unwrap())
        .collect()
}

/// A page as the converter keeps it: the compiler's record, with what it
/// draws, and what the second round puts in.
#[derive(Debug, Clone)]
pub struct PageRecord {
    pub event: i64,
    pub page: i64,
    pub trigger: i64,
    pub switch_a: Value,
    pub switch_b: Value,
    pub actor: Value,
    pub variable: Value,
    pub item: Value,
    pub layer: Value,
    pub frequency: Value,
    pub speed: Value,
    pub code: Vec<u8>,
    pub has_code: bool,
    pub own_route: Option<Value>,
    pub graphic: Option<Graphic>,
    pub tile_pass: Option<i64>,
    pub turns: bool,
    pub fixed_direction: bool,
    /// `AnimType_fixed_graphic`: it shows its page's column always, even
    /// when a move route turns it or walks it. See `animate_ev_route`.
    pub fixed_graphic: bool,
    /// A test page: it does not come from the game.
    pub test: bool,
    /// A parallel page that runs only when what it reads changes: see
    /// `pure_page` in the events compiler.
    pub pure: bool,
    pub offset: usize,
    pub route_offset: usize,
    pub draws: Option<Value>,
}

/// A converted map, as the rest of the conversion reads it.
pub struct MapInfo {
    pub id: i32,
    /// The events Wally painted into the background: they are no events,
    /// so they have no page in the table. Their indices, not their ids.
    pub decorative: BTreeSet<i64>,
    pub name: String,
    pub map: GameMap,
    pub route_graphics: Vec<(String, i64)>,
    pub tile_data: Vec<u8>,
    pub cgram: Vec<u8>,
    /// The background's tilemap, columns by rows.
    pub tilemap: (usize, usize),
    pub above_tiles: Vec<u8>,
    pub above_cgram: Vec<u8>,
    pub above_first: i64,
    pub above_png: Vec<u8>,
    /// The background's depth: 8, or 4 in a map whose panorama goes in
    /// mode 1.
    pub bpp: i64,
    /// The panorama, as the emission takes it, if the map shows it.
    pub panorama: Option<Value>,
    /// Each background picture Adeleine decided, by name.
    pub pictures_bg: Vec<(String, Vec<u8>)>,
    pub runs: Vec<Value>,
    pub colors: Value,
    pub budget: Value,
    pub merges_background: Value,
    /// How it shows its panorama, Wally's name for it, if it has one.
    pub panorama_way: Value,
    /// Whether no panorama of the map is ever seen: a `ChangePBG` there
    /// that keeps the picture loses nothing. See `unseen` in Wally.
    pub panorama_unseen: bool,
    pub merges_above: Value,
    pub start: (i64, i64),
    pub cells: Vec<u8>,
    pub blocks: Vec<u8>,
    pub block_pass: Vec<u8>,
    pub block_terrain: Vec<u8>,
    pub terrain_outside: i32,
    pub layout_name: String,
    pub objects: Value,
    pub npcs: Value,
    pub movable: Value,
    pub animates_still: Value,
    /// The still ones that animate in another one's slot: `[event, whose]`.
    pub animates_with: Value,
    /// Where each (CharSet, index, pose) ended up in the sprite bank.
    pub where_: HashMap<Graphic, (Value, Value)>,
    /// In a map with a cache of slots, each still pose's number and its
    /// palette: what a page carries instead of a block. See
    /// `sprites::cache` in Wally.
    pub cached: HashMap<Graphic, (Value, Value)>,
    pub substitution_table: Value,
    pub missing_substitutions: Vec<(bool, i64, i64)>,
    pub turning: BTreeSet<i64>,
    pub changing: BTreeSet<i64>,
    pub appearing: BTreeSet<i64>,
    pub outside: HashMap<i64, HashSet<(String, i64)>>,
    pub shared: HashMap<i64, (Value, Value)>,
    pub pictures: Option<(Value, Vec<Value>, Vec<Value>)>,
    pub big_pictures: Vec<Big>,
    pub big_table: Vec<Value>,
    pub pages: Vec<PageRecord>,
    pub sub_keys: BTreeSet<i64>,
    pub evcode: Vec<u8>,
    pub chipset_filename: String,
    pub passability: Vec<u8>,
    /// What Wally's notes said the map lost: `(kind, text, events)`, for
    /// the cartridge's degradations.
    pub losses: Vec<(String, String, Vec<i64>)>,
}

fn file<'a>(written: &'a BTreeMap<String, Vec<u8>>, name: &str) -> Result<&'a Vec<u8>> {
    written
        .get(name)
        .ok_or_else(|| Stop::new(format!("{STAGE} did not write {name}")))
}

fn family(name: &str) -> &str {
    match name {
        "water" => "agua",
        "animated" => "animado",
        other => other,
    }
}

/// The note of a mechanism that is not drawn stops the build: it was a
/// line among fifty, and on 2026-09-07 it cost an afternoon —a door that
/// did not change tile, and the player could not get through—. A
/// decorative one only says so.
fn discard_warning(text: &str, dangerous: bool) -> Result<()> {
    if !dangerous {
        println!("  {text}");
        return Ok(());
    }
    Err(Stop::new(format!(
        "{text}\n\nThe ROM is not built: that event **changes graphic between its pages**,\nthat \
         is, it is a mechanism and not decoration. Without being drawn, the\nchange is never \
         seen, and since the event still blocks the way and\ntriggers, what is left is an \
         invisible wall where the game expected a door."
    )))
}

fn int(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

/// The most tiles any of a map's panoramas takes: the layout holds the one
/// shown, and a `ChangePBG` uploads another over it.
fn panorama_tiles(pano: &Value) -> i64 {
    pano["images"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|i| int(&i["tiles"]))
        .fold(int(&pano["tiles"]), i64::max)
}

/// The panoramas a map carries, in the order the bytecode numbers them —
/// its own, or an empty name if it starts with none, and the ones its
/// `ChangePBG`s name—; empty if it carries one at most. See
/// `Request::panoramas` in rm2k-snes-events.
pub fn panorama_names(panorama: Option<&Value>) -> Vec<String> {
    let Some(p) = panorama else { return Vec::new() };
    let images = p["images"].as_array().cloned().unwrap_or_default();
    if images.is_empty() && p["none_first"].as_bool() != Some(true) {
        return Vec::new();
    }
    let name = |v: &Value| v["name"].as_str().unwrap_or("").to_string();
    let mut out = Vec::new();
    if p["none_first"].as_bool() == Some(true) {
        out.push(String::new());
    }
    out.push(name(p));
    out.extend(images.iter().map(name));
    out
}

fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(_) => true,
    }
}

/// A slot of the sprite bank by the key it is known by: the hero's, the
/// turn's, an event's, a shared one, or a graphic's.
fn slot_key(slot: &Value) -> String {
    if truthy(slot.get("hero")) {
        "heroe".to_string()
    } else if truthy(slot.get("turn")) {
        "giro".to_string()
    } else if let Some(e) = slot.get("event") {
        format!("ev {e}")
    } else if let Some(s) = slot.get("shared") {
        format!("compartida {s}")
    } else if let Some(s) = slot.get("cache") {
        format!("cache {s}")
    } else {
        json!([slot["charset"], slot["index"], slot["pose"]]).to_string()
    }
}

/// What the stage answered, as the rest of the conversion reads it, with
/// its messages printed in the order the conversion said them.
pub fn map_info(game: &Game, p: Prepared, written: BTreeMap<String, Vec<u8>>) -> Result<MapInfo> {
    let map_id = p.map.id;
    let answer = stage::json(&written, "map.json")?;
    let mut losses = Vec::new();
    for note in answer["notes"].as_array().cloned().unwrap_or_default() {
        let text = note["text"].as_str().unwrap_or("");
        let stop = note["stop"].as_bool().unwrap_or(false);
        if let Some(loss) = note["loss"].as_str() {
            let events = note["events"]
                .as_array()
                .map(|a| a.iter().map(int).collect())
                .unwrap_or_default();
            losses.push((loss.to_string(), text.to_string(), events));
        }
        if note["kind"] == "discard" {
            discard_warning(text, stop)?;
        } else if stop {
            return Err(Stop::new(text));
        } else {
            println!("{text}");
        }
    }
    let layers = stage::json(&written, "layers.json")?;
    let (bg, above) = (&layers["background"], &layers["above"]);
    let tile_data = file(&written, "background.bin")?.clone();
    let above_tiles = file(&written, "above.bin")?.clone();
    let above_cgram = file(&written, "above-cgram.bin")?.clone();
    let tilemap = bg["tilemap"].as_array().cloned().unwrap_or_default();
    let tilemap_dims = (
        tilemap
            .first()
            .and_then(Value::as_array)
            .map_or(0, Vec::len),
        tilemap.len(),
    );
    let mut runs = Vec::new();
    for run in bg["runs"].as_array().cloned().unwrap_or_default() {
        let mut drawings = Vec::new();
        for name in run["drawings"].as_array().cloned().unwrap_or_default() {
            drawings.push(json!(crate::text::hex(file(
                &written,
                name.as_str().unwrap_or("")
            )?)));
        }
        runs.push(json!({"family": run["family"], "base": run["base"], "tiles": run["tiles"], "drawings": drawings}));
    }
    let mut pictures_bg = Vec::new();
    let mut above_png = Vec::new();
    for picture in layers["pictures"].as_array().cloned().unwrap_or_default() {
        let name = picture["name"].as_str().unwrap_or("");
        let png = file(&written, picture["file"].as_str().unwrap_or(""))?.clone();
        if name == "above" {
            above_png = png;
            continue;
        }
        let name = if name == "background" {
            "fondo".to_string()
        } else if name == "panorama" {
            "panorama".to_string()
        } else {
            let (fam, drawing) = name.rsplit_once('-').unwrap_or((name, ""));
            format!("{}-{drawing}", family(fam))
        };
        pictures_bg.push((name, png));
    }
    let s = &answer["sprite"];
    let above_count = above_tiles.len() / 32;
    let tiles_count = tile_data.len() / BYTES_PER_TILE;
    if !s["animation"].is_null() {
        // The VRAM **stops**: whether the box fits depends on the tile
        // layout and not on the palettes.
        let count = int(&s["animation"]["count"]);
        let layout = if layers["panorama"].is_null() {
            vram::vram_layout(tiles_count as u32, count as u32, above_count as u32).ok()
        } else {
            vram::panorama_layout(
                int(&layers["panorama"]["mode"]) as u8,
                tiles_count as u32,
                count as u32,
                above_count as u32,
                panorama_tiles(&layers["panorama"]) as u32,
            )
            .ok()
        };
        if layout.is_none() {
            // Not the box: the map's own tiles fit no layout, with or without it.
            crate::stop!(
                "map {map_id}: fits no VRAM layout: {tiles_count} background tiles, {count} sprite \
                 tiles (its animation box's {} included) and {above_count} upper tiles",
                animations::TILES
            );
        }
        if count > layout.unwrap().sprites.count as i64 {
            crate::stop!(
                "map {map_id}: shows battle animations and the {} tiles of its box don't fit in \
                 the sprite bank: it spends {count} of {}. See `map_shows_animation`.",
                animations::TILES,
                layout.map_or(0, |l| l.sprites.count)
            );
        }
        println!(
            "  map {map_id}: battle animations are drawn in {} tiles from {}, palette {}",
            animations::TILES,
            int(&s["animation"]["base"]),
            int(&s["animation"]["palette"])
        );
    }
    // The pictures, if the stage found room for them in the bank.
    // The map's own, without the copied common events', if Wally put those
    // in instead.
    let went_in = match &p.pictures_own {
        Some(own) if truthy(answer.get("pictures_own")) => own,
        _ => &p.pictures,
    };
    let pictures = match went_in {
        Some(f) if int(&s["image"][0]) != 0 => {
            Some((s["image"][0].clone(), f.table.clone(), f.images.clone()))
        }
        _ => None,
    };
    // If it found none, the ones the map shows over a black screen go in
    // the background layer instead: see [`pictures::over_black`]. If that
    // is all of them, the map loses none.
    let mut big_pictures = p.big_pictures;
    if let (Some(asked), None, false) = (went_in, &pictures, p.big_over_black.is_empty()) {
        let names = |keys: &mut dyn Iterator<Item = &Value>| -> BTreeSet<String> {
            keys.filter_map(|k| k["name"].as_str())
                .map(str::to_lowercase)
                .collect()
        };
        let rescued = names(&mut p.big_over_black.iter().map(|b| &b.key));
        let lost = names(&mut asked.table.iter());
        println!(
            "  map {map_id}: the pictures {} are shown in the background layer instead, over the \
             black screen they are shown on",
            crate::text::repr(&rescued.iter().cloned().collect::<Vec<_>>().join(", "))
        );
        if lost.is_subset(&rescued) {
            losses.retain(|(kind, text, _)| {
                kind != "pictures-not-drawn" || text.contains("the common events' pictures")
            });
        }
        big_pictures.extend(p.big_over_black);
    }
    let npcs = answer["npcs"].clone();
    let mut where_ = HashMap::new();
    for entry in s["place"].as_array().cloned().unwrap_or_default() {
        let slot = &entry[0];
        if truthy(slot.get("hero"))
            || truthy(slot.get("turn"))
            || slot.get("event").is_some()
            || slot.get("shared").is_some()
            || slot.get("cache").is_some()
        {
            continue;
        }
        let key = (
            slot["charset"].as_str().unwrap_or("").to_string(),
            int(&slot["index"]),
            int(&slot["pose"]),
        );
        where_.insert(key, (entry[1].clone(), entry[2].clone()));
    }
    let mut cached = HashMap::new();
    for (v, still) in s["cache"]["stills"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .enumerate()
    {
        let key = (
            still[0].as_str().unwrap_or("").to_string(),
            int(&still[1]),
            int(&still[2]),
        );
        cached.insert(key, (json!(v), still[4].clone()));
    }
    let tiles_name = s["tiles"].as_str().unwrap_or("").to_string();
    let sprite_tiles = file(&written, &tiles_name)?.clone();
    let passable: Vec<u8> = layers["passability"]
        .as_array()
        .map(|a| a.iter().map(|v| int(v) as u8).collect())
        .unwrap_or_default();
    let start = (int(&answer["start"][0]), int(&answer["start"][1]));
    let name = game.tree.name(map_id).to_string();
    let cells_count = int(&bg["cells"]);
    println!(
        "Map {map_id} {}: {}x{} cells of {}x{} px",
        crate::text::repr(&name),
        tilemap_dims.0,
        tilemap_dims.1,
        8,
        8
    );
    println!(
        "  {} distinct colors, {} in CGRAM of {} available, {} merged",
        int(&bg["colors"]),
        int(&bg["used"]),
        int(&bg["budget"]),
        bg["merges"].as_array().map_or(0, Vec::len)
    );
    println!(
        "  {} unique tiles of {} cells ({}% reuse)",
        int(&bg["tiles"]),
        cells_count,
        round0(100.0 * (1.0 - int(&bg["tiles"]) as f64 / cells_count as f64))
    );
    let animated: Vec<Value> = s["animated"].as_array().cloned().unwrap_or_default();
    println!(
        "  sprites: {} characters, {} slots, {} tiles in VRAM, {} palettes; {} with their twelve poses in the cartridge",
        int(&s["characters"]),
        s["place"].as_array().map_or(0, |p| {
            // The slots by the key the rest of the conversion knows them by.
            let keys: HashSet<String> = p.iter().map(|e| slot_key(&e[0])).collect();
            keys.len()
        }),
        sprite_tiles.len() / 32,
        s["palettes"].as_array().map_or(0, Vec::len),
        animated.len()
    );
    let npc_list = npcs.as_array().cloned().unwrap_or_default();
    println!(
        "  {} NPCs with a CharSet out of {} events",
        npc_list.len(),
        p.map.events.len()
    );
    let open_ones = passable.iter().filter(|&&b| b == 0x0F).count();
    println!(
        "  collision: {} cells, {} open on all four sides ({}%), the hero starts at ({},{})",
        passable.len(),
        open_ones,
        round0(100.0 * open_ones as f64 / passable.len() as f64),
        start.0,
        start.1
    );
    let above_first = int(&above["first"]);
    let above_merges = above["merges"].as_array().map_or(0, Vec::len);
    println!(
        "  layer above the hero: {} tiles, {} colors in {} palette(s) from {}, {} merged",
        above_count,
        above_cgram.len() / 2,
        BG_PALETTES - above_first,
        above_first,
        above_merges
    );
    let cells_list: Vec<i64> = layers["blocks"]["cells"]
        .as_array()
        .map(|a| a.iter().map(int).collect())
        .unwrap_or_default();
    let blocks = file(&written, "blocks.bin")?.clone();
    let block_pass = file(&written, "block-passability.bin")?.clone();
    let block_terrain = file(&written, "block-terrain.bin")?.clone();
    // One byte a cell or two, as the emission will carry it; a grid that
    // fits neither way is said as two, and the map is left out.
    let cell_bytes = rm2k_snes_mapdata::materials::cell_bytes(
        cells_list.len(),
        blocks.len() / rm2k_snes_mapdata::materials::BLOCK_BYTES,
        blocks.len() + block_pass.len(),
    )
    .unwrap_or(2);
    println!(
        "  the map fits in {} 16x16 blocks for {} cells: {} B of grid plus {} B of table, against the {} B of the expanded tilemap",
        block_pass.len(),
        cells_list.len(),
        cell_bytes * cells_list.len(),
        blocks.len(),
        2 * cells_count
    );
    let windows_x = (tilemap_dims.0 as u32).div_ceil(vram::WINDOW_W);
    let windows_y = (tilemap_dims.1 as u32).div_ceil(vram::WINDOW_H);
    if windows_x > 1 || windows_y > 1 {
        println!(
            "  it doesn't fit in the {}x{} window: the ROM is going to redraw",
            vram::WINDOW_W,
            vram::WINDOW_H
        );
    }
    let mut cells = Vec::with_capacity(cells_list.len() * 2);
    for cell in &cells_list {
        cells.extend_from_slice(&(*cell as u16).to_le_bytes());
    }
    let mut cgram = Vec::new();
    for word in bg["cgram"].as_array().cloned().unwrap_or_default() {
        cgram.extend_from_slice(&(int(&word) as u16).to_le_bytes());
    }
    let chipset = game.chipset(p.map.chipset_id)?;
    let pano = &layers["panorama"];
    if let Some(way) = layers["panorama_way"].as_str() {
        if way == "flattened" {
            println!(
                "  map {map_id}: its panorama goes {way}, {} pixels on the wrong side of the hero",
                int(&layers["panorama_above_lost"])
            );
        } else {
            println!("  map {map_id}: its panorama goes {way}");
        }
        for why in layers["panorama_tried"].as_array().into_iter().flatten() {
            println!("    not {}", why.as_str().unwrap_or(""));
        }
    }
    // What the map's pictures put in front of the hero: see
    // `map_pictures` in Wally.
    if let Some(front) = layers.get("pictures_in_front").filter(|v| !v.is_null()) {
        println!(
            "  map {map_id}: its pictures put {} pixels in front of the hero, and {} go to the wrong side of him",
            int(&front["pixels"]),
            int(&front["wrong"])
        );
    }
    let layout = if pano.is_null() {
        vram::vram_layout(
            tiles_count as u32,
            (sprite_tiles.len() / 32) as u32,
            above_count as u32,
        )
        .map_err(|refused| Stop::new(format!("map {map_id}: {}", refused.message())))?
    } else {
        let layout = vram::panorama_layout(
            int(&pano["mode"]) as u8,
            tiles_count as u32,
            (sprite_tiles.len() / 32) as u32,
            above_count as u32,
            panorama_tiles(pano) as u32,
        )
        .map_err(|refused| Stop::new(format!("map {map_id}: {}", refused.message())))?;
        println!(
            "  panorama {}: mode {} in {}, a stretch of {}x{}, {} tiles of {} distinct, {} colors of {}, {} merged{}",
            pano["name"].as_str().unwrap_or(""),
            int(&pano["mode"]),
            layout.name,
            int(&pano["stretch"][0]),
            int(&pano["stretch"][1]),
            int(&pano["tiles"]),
            int(&pano["distinct"]),
            int(&pano["kept"]),
            int(&pano["colors"]),
            pano["merges"].as_array().map_or(0, Vec::len),
            if pano["none_first"].as_bool() == Some(true) { "; the map starts with none" } else { "" }
        );
        // The other pictures its `ChangePBG`s swap in, and what each costs:
        // the cartridge carries its tiles and its tilemap, and a swap
        // uploads the tiles and fills the tilemap's ring with the screen off.
        let images = pano["images"].as_array().cloned().unwrap_or_default();
        let bytes_per_tile = if int(&pano["mode"]) == 1 { 16 } else { 32 };
        let rom = |p: &Value| {
            int(&p["tiles"]) * bytes_per_tile
                + int(&p["stretch"][0]) / 8 * (int(&p["stretch"][1]) / 8) * 2
        };
        for image in &images {
            println!(
                "  panorama {} too, by a ChangePBG: a stretch of {}x{}, {} tiles of {} distinct, {} colors of {}, {} merged, {} bytes of ROM",
                image["name"].as_str().unwrap_or(""),
                int(&image["stretch"][0]),
                int(&image["stretch"][1]),
                int(&image["tiles"]),
                int(&image["distinct"]),
                int(&image["kept"]),
                int(&image["colors"]),
                image["merges"].as_array().map_or(0, Vec::len),
                rom(image)
            );
        }
        if !images.is_empty() {
            println!(
                "  map {map_id}: {} panoramas, {} bytes of ROM, in {} palettes from entry {}",
                images.len() + 1,
                rom(pano) + images.iter().map(rom).sum::<i64>(),
                pano["cgram"].as_array().map_or(0, Vec::len) / 16,
                int(&pano["first"])
            );
        }
        layout
    };
    for dropped in layers["panorama_dropped"].as_array().into_iter().flatten() {
        println!(
            "  map {map_id}: its ChangePBG to {:?} keeps the panorama there is: {}",
            dropped[0].as_str().unwrap_or(""),
            dropped[1].as_str().unwrap_or("")
        );
    }
    let panorama = if pano.is_null() {
        None
    } else {
        let mut record = pano.clone();
        record["tile_count"] = pano["tiles"].clone();
        record["tiles"] = json!(crate::text::hex(file(&written, "panorama.bin")?));
        for (k, image) in pano["images"].as_array().into_iter().flatten().enumerate() {
            record["images"][k]["tiles"] = json!(crate::text::hex(file(
                &written,
                image["file"].as_str().unwrap_or("")
            )?));
        }
        Some(record)
    };
    let mut objects = s.clone();
    objects["tiles"] = json!(crate::text::hex(&sprite_tiles));
    let mut banks = Vec::new();
    for bank in s["banks"].as_array().cloned().unwrap_or_default() {
        let data = file(&written, bank[2].as_str().unwrap_or(""))?;
        banks.push(json!([bank[0], bank[1], crate::text::hex(data)]));
    }
    objects["banks"] = Value::Array(banks);
    let mut changing = BTreeSet::new();
    let mut appearing = BTreeSet::new();
    let mut outside = HashMap::new();
    for n in &npc_list {
        let event = int(&n["event"]);
        if n["changes"].as_bool().unwrap_or(false) {
            changing.insert(event);
        }
        if n["appears"].as_bool().unwrap_or(false) {
            appearing.insert(event);
        }
        let set: HashSet<(String, i64)> = n["outside"]
            .as_array()
            .map(|a| {
                a.iter()
                    .map(|k| (k[0].as_str().unwrap_or("").to_string(), int(&k[1])))
                    .collect()
            })
            .unwrap_or_default();
        outside.insert(event, set);
    }
    let mut shared = HashMap::new();
    if let Some(sh) = s["shared"].as_object() {
        for e in sh
            .get("events")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
        {
            let slot = int(&e[1]) as usize;
            shared.insert(int(&e[0]), (sh["slots"][slot].clone(), e[3].clone()));
        }
    }
    let substitution_table = Value::Array(
        answer["substitutions"]["table"]
            .as_array()
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(|t| json!({"upper": t[0], "old": t[1], "new": t[2], "pairs": t[3]}))
            .collect(),
    );
    let missing_substitutions = answer["substitutions"]["missing"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|t| (t[0].as_bool().unwrap_or(false), int(&t[1]), int(&t[2])))
        .collect();
    let turning = answer["turning"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|t| int(&t[0]))
        .collect();
    Ok(MapInfo {
        id: map_id,
        name,
        route_graphics: p.route_graphics,
        tile_data,
        cgram,
        tilemap: tilemap_dims,
        above_tiles,
        above_cgram,
        above_first,
        above_png,
        bpp: bg["bpp"].as_i64().unwrap_or(8),
        panorama,
        pictures_bg,
        runs,
        colors: bg["colors"].clone(),
        budget: bg["budget"].clone(),
        merges_background: bg["merges"].clone(),
        panorama_way: layers["panorama_way"].clone(),
        panorama_unseen: layers["panorama_unseen"].as_bool().unwrap_or(false),
        merges_above: above["merges"].clone(),
        start,
        cells,
        blocks,
        block_pass,
        block_terrain,
        // The terrain of a cell **outside the map**: `GetTerrainTag` uses
        // the ChipSet's index 0, that is the first autotile.
        terrain_outside: rm2k_rules::chipset::terrain_of(chipset, 0),
        layout_name: layout.name.to_string(),
        objects,
        npcs,
        movable: answer["movable"].clone(),
        animates_still: answer["animates_still"].clone(),
        animates_with: answer["animates_with"].clone(),
        where_,
        cached,
        substitution_table,
        missing_substitutions,
        turning,
        changing,
        appearing,
        outside,
        shared,
        pictures,
        big_pictures,
        big_table: Vec::new(),
        decorative: answer["decorative"]
            .as_array()
            .map(|a| a.iter().map(int).collect())
            .unwrap_or_default(),
        pages: Vec::new(),
        sub_keys: BTreeSet::new(),
        evcode: Vec::new(),
        chipset_filename: p.chipset_filename,
        passability: p.passability,
        map: p.map,
        losses,
    })
}

/// The records the compiler answered for a map's pages, as the converter
/// keeps them, with what each page draws: that is the port's.
pub fn pages(records: &Value, info: &MapInfo) -> Result<Vec<PageRecord>> {
    let mut out = Vec::new();
    for r in records.as_array().cloned().unwrap_or_default() {
        let event = int(&r["event"]);
        if info.decorative.contains(&event) {
            continue;
        }
        let page_index = int(&r["page"]);
        let page = info
            .map
            .events
            .get(event as usize)
            .and_then(|e| e.pages.get(page_index as usize))
            .ok_or_else(|| {
                Stop::new(format!(
                    "map {}: no page {page_index} of event {event}",
                    info.id
                ))
            })?;
        let graphic = page_graphic(page, &info.chipset_filename);
        let code = r["code"].as_str().map(crate::text::unhex);
        let tile_pass = graphic
            .as_ref()
            .and_then(|g| event_tile_passability(&info.passability, &g.0, page.layer));
        out.push(PageRecord {
            event,
            page: page_index,
            trigger: int(&r["trigger"]),
            switch_a: r["switch_a"].clone(),
            switch_b: r["switch_b"].clone(),
            actor: r["actor"].clone(),
            variable: r["variable"].clone(),
            item: r["item"].clone(),
            layer: r["layer"].clone(),
            frequency: r["frequency"].clone(),
            speed: r["speed"].clone(),
            has_code: code.as_ref().is_some_and(|c| !c.is_empty()),
            code: code.unwrap_or_default(),
            own_route: (!r["own_route"].is_null()).then(|| r["own_route"].clone()),
            graphic,
            tile_pass,
            turns: r["turns"].as_bool().unwrap_or(false),
            fixed_direction: matches!(page.animation_type, 2..=4),
            fixed_graphic: page.animation_type == 4,
            test: false,
            pure: r["pure"].as_bool().unwrap_or(false),
            offset: 0,
            route_offset: 0,
            draws: None,
        });
    }
    Ok(out)
}

/// Writes what Adeleine decided of each map as images, next to the
/// output: indexed, their indices CGRAM entries.
pub fn write_adeleine(dir: &Path, maps: &[MapInfo]) -> Result<()> {
    std::fs::create_dir_all(dir).map_err(|e| crate::fail::io(dir, e))?;
    for m in maps {
        let mut pictures: Vec<(&str, &Vec<u8>)> =
            m.pictures_bg.iter().map(|(n, p)| (n.as_str(), p)).collect();
        pictures.push(("encima", &m.above_png));
        for (name, png) in pictures {
            let path = dir.join(format!("{:04}-{name}.png", m.id));
            std::fs::write(&path, png).map_err(|e| crate::fail::io(&path, e))?;
        }
    }
    Ok(())
}
