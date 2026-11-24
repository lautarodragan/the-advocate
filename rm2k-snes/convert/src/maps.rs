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
use rm2k_snes_events::answer::{OwnRoute, Page, Scan};
use rm2k_snes_events::codes::{FLASH_SPRITE, MOVE_EVENT, TILE_SUBSTITUTION};
use rm2k_snes_mapdata::vram;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use wally::answer;

/// Wally's one stage: a whole map, called once per map.
const WALLY_MAP: stage::Stage = stage::Stage {
    binary: "wally",
    command: "map",
};

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
    pub scan: &'a Scan,
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
    /// The maps that carry the sandstorm's grains —see
    /// `scan::sandstorm_reach`—, or `None` if no page starts one.
    pub sand_maps: Option<BTreeSet<i32>>,
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
    /// Where the hero can arrive on each map: see [`crate::reach`].
    pub arrivals: crate::reach::Arrivals,
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
                crate::text::quoted(name),
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
    let scanned = c
        .scan
        .map(map_id)
        .ok_or_else(|| Stop::new(format!("map {map_id} is not in the answer")))?;
    let mut route_graphics = scanned.graphics.clone();
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
    let on_events = &scanned.graphics_on_events;
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
    let mut keys = pictures::keys(&scanned.pictures);
    // The map's own come first, and then those only the copies of the
    // common events show, if the map carries them: the scan says how many
    // are its own. See [`crate::common_pages`].
    let mut own_keys: Option<Vec<pictures::Key>> = scanned
        .pictures_own
        .filter(|&n| n < keys.len())
        .map(|n| keys[..n].to_vec());
    // The ones that are part of a map are drawn into it, and their commands
    // are accepted without being done; but a drawing's part, which is
    // shown —see [`crate::map_pictures::Parts`]—: its name can be drawn in
    // under another number.
    let part = |k: &pictures::Key| c.map_pictures.part(map_id, k.number, &k.name);
    let kept = |k: &pictures::Key| part(k).is_some() || !c.map_pictures.done(map_id, &k.name);
    keys.retain(kept);
    if let Some(own) = own_keys.as_mut() {
        own.retain(kept);
    }
    // And the parts show only what is their own, from the file the rule
    // wrote, with the map.
    for k in keys.iter_mut().chain(own_keys.iter_mut().flatten()) {
        if let Some(path) = part(k) {
            k.path = Some(path.display().to_string());
            k.with_map = true;
        }
    }
    // And the ones under a lower number than one the map draws opaque,
    // which RM2k shows under it: see `behind_map` in
    // [`pictures::for_map`].
    let raised: Vec<i64> = c
        .map_pictures
        .of(map_id)
        .iter()
        .filter(|p| p.transparency <= 0)
        .map(|p| i64::from(p.number))
        .collect();
    for k in keys.iter_mut().chain(own_keys.iter_mut().flatten()) {
        if raised.iter().any(|&n| n > i64::from(k.number)) {
            k.behind_map = true;
        }
    }
    // And the ones with the screen that RM2k shows where its map is, which
    // go with the map: see [`pictures::screen_on_map`].
    let on_map = pictures::screen_on_map(&map);
    for k in keys.iter_mut().chain(own_keys.iter_mut().flatten()) {
        if pictures::screen_on_map_in(k, &on_map) {
            k.screen_on_map = true;
        }
    }
    // And the numbers the map tones, which do not share a palette.
    let tinted = &scanned.tinted;
    let whose = format!("map {map_id}");
    let pictures = pictures::for_map(&game.game_dir, &keys, tinted, &whose, &game.cropped)?;
    let pictures_own = match &own_keys {
        Some(own) => Some(pictures::for_map(
            &game.game_dir,
            own,
            tinted,
            &whose,
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
    let zooms = &scanned.zooms;
    // On a map of one screen, the ones shown still over its panorama go
    // with it under them: see [`pictures::still_over`].
    let panorama = game.screen_panorama(map_id)?;
    let still = pictures::still_over(&map);
    let big_pictures = pictures::big_for_map(
        &game.game_dir,
        &keys,
        zooms,
        &format!("map {map_id}"),
        &game.cropped,
        &|_| false,
        panorama.as_deref().map(|p| (p, &still)),
    )?;
    // And the small ones the map shows over a black screen, in the
    // background layer too: what goes in if the sprites have no room for
    // the map's pictures. See [`pictures::over_black`].
    let black = pictures::over_black(&map);
    let big_over_black = if black.is_empty() {
        Vec::new()
    } else {
        let already: Vec<&pictures::Key> = big_pictures.iter().map(|b| &b.key).collect();
        let small: Vec<pictures::Key> = keys
            .iter()
            .filter(|k| pictures::shown_in(k, &black) && !already.contains(k))
            .cloned()
            .collect();
        pictures::big_for_map(
            &game.game_dir,
            &small,
            zooms,
            &format!("map {map_id}"),
            &game.cropped,
            &|_| true,
            None,
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
        // The still walls left out, which Wally closes in the passability.
        "walls": game.walls_json_of(map_id),
        "chipset_files": compiler::chipset_files(game),
        "names": compiler::names([&map]).into_iter().map(|e| json!([e[1], e[2], e[3]])).collect::<Vec<_>>(),
        "test_event": test_event,
        "leaders": c.leaders,
        "pages": scanned.pages,
        "route_graphics": route_graphics.iter().map(|(g, i)| json!([g, i])).collect::<Vec<_>>(),
        "hero_graphics": hero_graphics,
        "also_walk": also_walk.into_iter().collect::<Vec<_>>(),
        // What the test pages name, so a decorative event is never one a
        // test moves: only when the project asks for them.
        "decorative": game.decorative,
        // And the still events that change pose, into the background: not
        // on a map that loops, whose cells the console builds elsewhere —see
        // `wrap.s`—.
        "posed_stills": game.posed.on(map_id) && map.scroll_type == 0,
        "baked_events_nudge": game.nudge,
        "test_commands": if game.decorative || game.posed.on(map_id) {
            case_commands.iter().map(|c| json!([c.code, c.parameters])).collect::<Vec<_>>()
        } else {
            Vec::new()
        },
        "timer": timer,
        "map_pictures": c.map_pictures.of(map_id).iter().map(|p| p.to_json()).collect::<Vec<_>>(),
        "rain": c.with_rain,
        "sand": c.sand_maps.as_ref().map(|m| m.contains(&map_id)),
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
    // A map whose still pieces are painted into it is one picture, and goes
    // painted even if the project does not ask it of the others; and what
    // the test pages name stays an object.
    let painting = game.painted_events.on(map_id);
    if game.painted_maps || painting {
        request["panorama"]["painted"] = json!(true);
    }
    if painting {
        request["painted_events"] = json!(true);
        request["test_commands"] = case_commands
            .iter()
            .map(|c| json!([c.code, c.parameters]))
            .collect();
    }
    // Where characters can be, with what the map does not say: Wally draws
    // below the tiles above the hero that none can ever cover. Only when
    // the project asks, as the painted maps. And where the still events go
    // into the background, for those drawn past their cells, without the
    // lowering if the project does not ask for it; and the pieces painted,
    // for what goes in front of the hero.
    if game.unreachable_above_below || game.posed.on(map_id) || painting {
        request["reach"] = c.arrivals.json_of(map_id, &case_commands);
        request["reach_lowers"] = json!(game.unreachable_above_below);
        request["boots_here"] = json!(map_id == c.order[c.start_index]);
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

/// Runs the stage on each `(map, request)` —every prepared map's, and the
/// ones of its ChipSet variants, see `variants.rs`—, in parallel, and hands
/// back what each wrote, in order.
pub fn run_requests(
    c: &Cartridge,
    prepared: &[(i32, &Value)],
) -> Result<Vec<BTreeMap<String, Vec<u8>>>> {
    let search_dirs: Vec<PathBuf> = c.search_dirs.iter().map(rm2k_project::absolute).collect();
    // What the binary was run with, which is what the cache key reads: the
    // call reads the same dump and search directories, and nothing else.
    let mut flags: Vec<OsString> = vec!["--data".into(), c.game.dump.clone().into_os_string()];
    for dir in &search_dirs {
        flags.push("--search-dir".into());
        flags.push(dir.clone().into_os_string());
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
                let request = prepared[k].1;
                let done = stage::call(WALLY_MAP, request, &flags, || {
                    wally::stage::map(&c.game.dump, &search_dirs, request)
                })
                .map_err(|e| e.in_map(prepared[k].0));
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
    pub switch_a: i32,
    pub switch_b: i32,
    pub actor: i32,
    pub variable: Option<(i64, i64, i64)>,
    pub item: i32,
    pub layer: i32,
    pub frequency: i32,
    pub speed: i32,
    pub code: Vec<u8>,
    pub has_code: bool,
    pub own_route: Option<OwnRoute>,
    pub graphic: Option<Graphic>,
    pub tile_pass: Option<i64>,
    pub turns: bool,
    pub fixed_direction: bool,
    /// `AnimType_fixed_graphic`: it shows its page's column always, even
    /// when a move route turns it or walks it. See `animate_ev_route`.
    pub fixed_graphic: bool,
    /// Whether the page is translucent: an event's transparency starts at 3
    /// on it, and a route's 40 and 41 count from there. See
    /// `ev_transparency` in runtime/far_npcs.s.
    pub translucent: bool,
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
    /// The events the RAM's trim left out that Wally painted into the map,
    /// by RM2k id: they lose nothing. See [`crate::trim::Loss::Painted`].
    pub painted_trimmed: BTreeSet<i64>,
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
    /// The still events drawn into the background, by event: their number
    /// in the map's table of them and the characters they draw, in the
    /// order a page's graphic is numbered. See `posed` in Wally.
    pub posed: BTreeMap<i64, (usize, Vec<(String, i64)>)>,
    /// What Wally answered of them, for the emission.
    pub posed_table: Value,
    pub outside: HashMap<i64, HashSet<(String, i64)>>,
    pub shared: HashMap<i64, (Value, Value)>,
    pub pictures: Option<(Value, Vec<Value>, Vec<Value>)>,
    /// Whether the pictures that went in are the copied common events'
    /// too, and not the map's own instead: a map keeps its copy only if it
    /// draws. See [`crate::common_pages`].
    pub copies_draw: bool,
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
    /// The ChipSets its pages swap in, each converted over its grid: see
    /// [`crate::variants`]. Empty for a map that swaps none.
    pub variants: Vec<crate::variants::Variant>,
    /// What its events came out as, to hold its variants against: see
    /// `variants::Drawn::events`.
    pub events_drawn: Value,
}

fn file<'a>(written: &'a BTreeMap<String, Vec<u8>>, name: &str) -> Result<&'a Vec<u8>> {
    written
        .get(name)
        .ok_or_else(|| Stop::new(format!("{} did not write {name}", WALLY_MAP.binary)))
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

/// The most tiles any of a map's panoramas takes: the layout holds the one
/// shown, and a `ChangePBG` uploads another over it.
fn panorama_tiles(pano: &answer::Panorama) -> usize {
    pano.images
        .iter()
        .map(|i| i.tiles)
        .fold(pano.tiles, usize::max)
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

/// What Wally answered of a map, read: its binaries stay in `written`, by
/// the names the answer gives them.
pub fn wally_answer(written: &stage::Files) -> Result<answer::Answer> {
    answer::Answer::read(written).map_err(|e| Stop::new(format!("{}: {e}", WALLY_MAP.binary)))
}

/// The background's ChipSet animation as the emission takes it: each run
/// with its drawings' bytes.
pub fn runs(bg: &answer::Background, written: &stage::Files) -> Result<Vec<Value>> {
    let mut runs = Vec::new();
    for run in &bg.runs {
        let mut drawings = Vec::new();
        for name in &run.drawings {
            drawings.push(crate::text::hex(file(written, name)?));
        }
        runs.push(json!({"family": run.family, "base": run.base, "tiles": run.tiles, "drawings": drawings}));
    }
    Ok(runs)
}

/// The words of a colour memory, as the bytes the console takes.
pub fn words(words: &[u16]) -> Vec<u8> {
    words.iter().flat_map(|w| w.to_le_bytes()).collect()
}

/// What the stage answered, as the rest of the conversion reads it, with
/// its messages printed in the order the conversion said them.
pub fn map_info(game: &Game, p: Prepared, written: BTreeMap<String, Vec<u8>>) -> Result<MapInfo> {
    let map_id = p.map.id;
    let answer::Answer {
        map: answer,
        layers,
    } = wally_answer(&written)?;
    let mut losses = Vec::new();
    for note in &answer.notes {
        let text = note.text.as_str();
        if let Some(loss) = &note.loss {
            let events = loss.events.iter().map(|&e| i64::from(e)).collect();
            losses.push((loss.loss.clone(), text.to_string(), events));
        }
        if note.kind == answer::Kind::Discard {
            discard_warning(text, note.stop)?;
        } else if note.stop {
            return Err(Stop::new(text));
        } else {
            println!("{text}");
        }
    }
    let (bg, above) = (&layers.background, &layers.above);
    let tile_data = file(&written, "background.bin")?.clone();
    let above_tiles = file(&written, "above.bin")?.clone();
    let above_cgram = file(&written, "above-cgram.bin")?.clone();
    let tilemap_dims = (bg.tilemap.first().map_or(0, Vec::len), bg.tilemap.len());
    let runs = runs(bg, &written)?;
    let mut pictures_bg = Vec::new();
    let mut above_png = Vec::new();
    for picture in &layers.pictures {
        let name = picture.name.as_str();
        let png = file(&written, &picture.file)?.clone();
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
    let s = answer
        .sprite
        .as_ref()
        .ok_or_else(|| Stop::new(format!("{} answered no objects", WALLY_MAP.binary)))?;
    let above_count = above_tiles.len() / 32;
    let tiles_count = tile_data.len() / BYTES_PER_TILE;
    if let Some(animation) = s.animation {
        // The VRAM **stops**: whether the box fits depends on the tile
        // layout and not on the palettes.
        let count = animation.count;
        let layout = match &layers.panorama {
            None => vram::vram_layout(tiles_count as u32, count as u32, above_count as u32).ok(),
            Some(pano) => vram::panorama_layout(
                pano.mode,
                tiles_count as u32,
                count as u32,
                above_count as u32,
                panorama_tiles(pano) as u32,
            )
            .ok(),
        };
        if layout.is_none() {
            // Not the box: the map's own tiles fit no layout, with or without it.
            crate::stop!(
                "map {map_id}: fits no VRAM layout: {tiles_count} background tiles, {count} sprite \
                 tiles (its animation box's {} included) and {above_count} upper tiles",
                animations::TILES
            );
        }
        if count as i64 > layout.unwrap().sprites.count as i64 {
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
            animation.base,
            animation.palette
        );
    }
    // The pictures, if the stage found room for them in the bank.
    // The map's own, without the copied common events', if Wally put those
    // in instead.
    let went_in = match &p.pictures_own {
        Some(own) if answer.pictures_own => own,
        _ => &p.pictures,
    };
    let pictures = match went_in {
        Some(f) if s.image.0 != 0 => Some((json!(s.image.0), f.table.clone(), f.images.clone())),
        _ => None,
    };
    // If it found none, the ones the map shows over a black screen go in
    // the background layer instead: see [`pictures::over_black`]. If that
    // is all of them, the map loses none.
    let mut big_pictures = p.big_pictures;
    if let (Some(asked), None, false) = (went_in, &pictures, p.big_over_black.is_empty()) {
        let names = |keys: &mut dyn Iterator<Item = &str>| -> BTreeSet<String> {
            keys.map(str::to_lowercase).collect()
        };
        let rescued = names(&mut p.big_over_black.iter().map(|b| b.key.name.as_str()));
        let lost = names(&mut asked.table.iter().filter_map(|k| k["name"].as_str()));
        println!(
            "  map {map_id}: the pictures {} are shown in the background layer instead, over the \
             black screen they are shown on",
            crate::text::quoted(&rescued.iter().cloned().collect::<Vec<_>>().join(", "))
        );
        if lost.is_subset(&rescued) {
            losses.retain(|(kind, text, _)| {
                kind != "pictures-not-drawn" || text.contains("the common events' pictures")
            });
        }
        big_pictures.extend(p.big_over_black);
    }
    // Where each still pose landed in the bank: the other slots are
    // someone's, not a graphic's.
    let mut where_ = HashMap::new();
    for (slot, block, palette) in &s.place {
        if let answer::Slot::Still {
            charset,
            index,
            pose,
        } = slot
        {
            let key = (charset.clone(), i64::from(*index), i64::from(*pose));
            where_.insert(key, (json!(block), json!(palette)));
        }
    }
    let mut cached = HashMap::new();
    for (v, still) in s.cache.iter().flat_map(|c| &c.stills).enumerate() {
        let key = (still.0.clone(), i64::from(still.1), i64::from(still.2));
        cached.insert(key, (json!(v), json!(still.4)));
    }
    let sprite_tiles = file(&written, &s.tiles)?.clone();
    let passable = &layers.passability;
    let start = (i64::from(answer.start.0), i64::from(answer.start.1));
    let name = game.tree.name(map_id).to_string();
    let cells_count = bg.cells;
    println!(
        "Map {map_id} {}: {}x{} cells of {}x{} px",
        crate::text::quoted(&name),
        tilemap_dims.0,
        tilemap_dims.1,
        8,
        8
    );
    println!(
        "  {} distinct colors, {} in CGRAM of {} available, {} merged",
        bg.colors,
        bg.used,
        bg.budget,
        bg.merges.len()
    );
    println!(
        "  {} unique tiles of {} cells ({:.0}% reuse)",
        bg.tiles,
        cells_count,
        100.0 * (1.0 - bg.tiles as f64 / cells_count as f64)
    );
    println!(
        "  sprites: {} characters, {} slots, {} tiles in VRAM, {} palettes; {} with their twelve poses in the cartridge",
        s.characters,
        s.place.iter().map(|(slot, _, _)| slot).collect::<HashSet<_>>().len(),
        sprite_tiles.len() / 32,
        s.palettes.len(),
        s.animated.len()
    );
    println!(
        "  {} NPCs with a CharSet out of {} events",
        answer.npcs.len(),
        p.map.events.len()
    );
    let open_ones = passable.iter().filter(|&&b| b == 0x0F).count();
    println!(
        "  collision: {} cells, {} open on all four sides ({:.0}%), the hero starts at ({},{})",
        passable.len(),
        open_ones,
        100.0 * open_ones as f64 / passable.len() as f64,
        start.0,
        start.1
    );
    let above_first = above.first as i64;
    println!(
        "  layer above the hero: {} tiles, {} colors in {} palette(s) from {}, {} merged",
        above_count,
        above_cgram.len() / 2,
        BG_PALETTES - above_first,
        above_first,
        above.merges.len()
    );
    let cells_list = &layers.blocks.cells;
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
    let chipset = game.chipset(p.map.chipset_id)?;
    if let Some(way) = &layers.panorama_way {
        if way == "flattened" {
            println!(
                "  map {map_id}: its panorama goes {way}, {} pixels on the wrong side of the hero",
                layers.panorama_above_lost
            );
        } else {
            println!("  map {map_id}: its panorama goes {way}");
        }
        for why in &layers.panorama_tried {
            println!("    not {why}");
        }
    }
    // What the map's pictures put in front of the hero: see
    // `map_pictures` in Wally.
    if let Some(front) = layers.pictures_in_front {
        println!(
            "  map {map_id}: its pictures put {} pixels in front of the hero, and {} go to the wrong side of him",
            front.pixels, front.wrong
        );
    }
    let sprite_count = (sprite_tiles.len() / 32) as u32;
    let layout = match &layers.panorama {
        None => vram::vram_layout(tiles_count as u32, sprite_count, above_count as u32)
            .map_err(|refused| Stop::new(format!("map {map_id}: {}", refused.message())))?,
        Some(pano) => {
            let layout = vram::panorama_layout(
                pano.mode,
                tiles_count as u32,
                sprite_count,
                above_count as u32,
                panorama_tiles(pano) as u32,
            )
            .map_err(|refused| Stop::new(format!("map {map_id}: {}", refused.message())))?;
            println!(
                "  panorama {}: mode {} in {}, a stretch of {}x{}, {} tiles of {} distinct, {} colors of {}, {} merged{}",
                pano.name,
                pano.mode,
                layout.name,
                pano.stretch.0,
                pano.stretch.1,
                pano.tiles,
                pano.distinct,
                pano.kept,
                pano.colors,
                pano.merges.len(),
                if pano.none_first { "; the map starts with none" } else { "" }
            );
            // The other pictures its `ChangePBG`s swap in, and what each
            // costs: the cartridge carries its tiles and its tilemap, and a
            // swap uploads the tiles and fills the tilemap's ring with the
            // screen off.
            let bytes_per_tile = if pano.mode == 1 { 16 } else { 32 };
            let rom =
                |tiles: usize, (w, h): (usize, usize)| tiles * bytes_per_tile + w / 8 * (h / 8) * 2;
            for image in &pano.images {
                println!(
                    "  panorama {} too, by a ChangePBG: a stretch of {}x{}, {} tiles of {} distinct, {} colors of {}, {} merged, {} bytes of ROM",
                    image.name,
                    image.stretch.0,
                    image.stretch.1,
                    image.tiles,
                    image.distinct,
                    image.kept,
                    image.colors,
                    image.merges.len(),
                    rom(image.tiles, image.stretch)
                );
            }
            if !pano.images.is_empty() {
                println!(
                    "  map {map_id}: {} panoramas, {} bytes of ROM, in {} palettes from entry {}",
                    pano.images.len() + 1,
                    rom(pano.tiles, pano.stretch)
                        + pano
                            .images
                            .iter()
                            .map(|i| rom(i.tiles, i.stretch))
                            .sum::<usize>(),
                    pano.cgram.len() / 16,
                    pano.first
                );
            }
            layout
        }
    };
    for (picture, why) in &layers.panorama_dropped {
        println!("  map {map_id}: its ChangePBG to {picture:?} keeps the panorama there is: {why}");
    }
    let panorama = match &layers.panorama {
        None => None,
        Some(pano) => {
            let mut record = json!(pano);
            record["tile_count"] = json!(pano.tiles);
            record["tiles"] = json!(crate::text::hex(file(&written, "panorama.bin")?));
            for (k, image) in pano.images.iter().enumerate() {
                record["images"][k]["tiles"] =
                    json!(crate::text::hex(file(&written, &image.file)?));
            }
            Some(record)
        }
    };
    let mut objects = json!(s);
    objects["tiles"] = json!(crate::text::hex(&sprite_tiles));
    let mut banks = Vec::new();
    for (charset, index, poses, shows) in &s.banks {
        // And which of its poses the map can show: mapdata emits only
        // those, joined over the maps.
        let data = crate::text::hex(file(&written, poses)?);
        banks.push(json!([charset, index, data, shows]));
    }
    objects["banks"] = Value::Array(banks);
    let mut changing = BTreeSet::new();
    let mut appearing = BTreeSet::new();
    let mut outside = HashMap::new();
    for answer::Row { npc: n, .. } in &answer.npcs {
        let event = n.event as i64;
        if n.changes {
            changing.insert(event);
        }
        if n.appears {
            appearing.insert(event);
        }
        let set = n.outside.iter().map(|(c, i)| (c.clone(), i64::from(*i)));
        outside.insert(event, set.collect());
    }
    let mut shared = HashMap::new();
    if let Some(sh) = &s.shared {
        for &(event, slot, _, palette) in &sh.events {
            shared.insert(event as i64, (json!(sh.slots.get(slot)), json!(palette)));
        }
    }
    let subs = &answer.substitutions;
    let substitution_table = subs
        .table
        .iter()
        .map(|(upper, old, new, pairs)| json!({"upper": upper, "old": old, "new": new, "pairs": pairs}))
        .collect();
    Ok(MapInfo {
        id: map_id,
        name,
        route_graphics: p.route_graphics,
        tile_data,
        cgram: words(&bg.cgram),
        tilemap: tilemap_dims,
        above_tiles,
        above_cgram,
        above_first,
        above_png,
        bpp: bg.bpp as i64,
        panorama,
        pictures_bg,
        runs,
        colors: json!(bg.colors),
        budget: json!(bg.budget),
        merges_background: json!(bg.merges),
        panorama_way: json!(layers.panorama_way),
        panorama_unseen: layers.panorama_unseen,
        merges_above: json!(above.merges),
        start,
        cells: cells_list.iter().flat_map(|c| c.to_le_bytes()).collect(),
        blocks,
        block_pass,
        block_terrain,
        // The terrain of a cell **outside the map**: `GetTerrainTag` uses
        // the ChipSet's index 0, that is the first autotile.
        terrain_outside: rm2k_rules::chipset::terrain_of(chipset, 0),
        layout_name: layout.name.to_string(),
        objects,
        npcs: json!(answer.npcs),
        movable: json!(answer.movable),
        animates_still: json!(answer.animates_still),
        animates_with: json!(answer.animates_with),
        where_,
        cached,
        substitution_table: Value::Array(substitution_table),
        missing_substitutions: subs
            .missing
            .iter()
            .map(|&(upper, old, new)| (upper, i64::from(old), i64::from(new)))
            .collect(),
        turning: answer.turning.iter().map(|(e, _)| *e as i64).collect(),
        changing,
        appearing,
        posed: answer
            .posed
            .iter()
            .enumerate()
            .map(|(k, p)| {
                let graphics = p.graphics.iter().map(|(c, i)| (c.clone(), i64::from(*i)));
                (p.event as i64, (k, graphics.collect()))
            })
            .collect(),
        posed_table: json!(answer.posed),
        outside,
        shared,
        copies_draw: pictures.is_some() && !answer.pictures_own,
        pictures,
        big_pictures,
        big_table: Vec::new(),
        decorative: answer.decorative.iter().map(|&d| d as i64).collect(),
        painted_trimmed: answer
            .painted_trimmed
            .iter()
            .map(|&e| i64::from(e))
            .collect(),
        pages: Vec::new(),
        sub_keys: BTreeSet::new(),
        evcode: Vec::new(),
        chipset_filename: p.chipset_filename,
        passability: p.passability,
        map: p.map,
        losses,
        variants: Vec::new(),
        events_drawn: crate::variants::map_events(&answer),
    })
}

/// The records the compiler answered for a map's pages, as the converter
/// keeps them, with what each page draws: that is the port's.
pub fn pages(records: &[Page], info: &MapInfo) -> Result<Vec<PageRecord>> {
    let mut out = Vec::new();
    for r in records {
        let event = r.event as i64;
        if info.decorative.contains(&event) {
            continue;
        }
        let page_index = r.page as i64;
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
        let code = r.code.as_ref().map(|c| c.0.clone());
        let tile_pass = graphic
            .as_ref()
            .and_then(|g| event_tile_passability(&info.passability, &g.0, page.layer));
        out.push(PageRecord {
            event,
            page: page_index,
            trigger: r.trigger.into(),
            switch_a: r.switch_a,
            switch_b: r.switch_b,
            actor: r.actor,
            variable: r.variable,
            item: r.item,
            layer: r.layer,
            frequency: r.frequency,
            speed: r.speed,
            has_code: code.as_ref().is_some_and(|c| !c.is_empty()),
            code: code.unwrap_or_default(),
            own_route: r.own_route.clone(),
            graphic,
            tile_pass,
            turns: r.turns,
            fixed_direction: matches!(page.animation_type, 2..=4),
            fixed_graphic: page.animation_type == 4,
            translucent: page.translucent,
            test: false,
            pure: r.pure,
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
