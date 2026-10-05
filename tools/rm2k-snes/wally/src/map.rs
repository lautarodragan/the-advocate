//! A whole map, as the cartridge carries it: its layers, the events baked
//! into them, its characters as objects and the extras at the end of their
//! bank, its blocks and where the hero starts.
//!
//! It is the one place that needs both halves of colour memory at once:
//! baking an event takes a sprite into the upper layer, and it is only
//! done if the layers' split of colour memory does not move —and undone if
//! the object palettes had to lend that event someone else's colours—.

use crate::baking::{self, bakeable};
use crate::events::{changes_graphic, collect_npcs, events, Event};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::layers::{self as stage_layers, draw, Drawn};
use crate::moves::{moves, Moves, ScannedPage};
use crate::request::LayersRequest;
use crate::sheets::Drawer;
use crate::substitutions::{substitute, Answer as SubstitutionAnswer, Triple};
use adeleine::Color;
use rm2k_render::picture;
use rm2k_rules::chipset::passability_table;
use rm2k_rules::passability::ALL;
use crate::background::blocks::Blocks;
use crate::background::Converted;
use crate::sprites::bank::{build_characters, pose_bank, Slot, SlotPose};
use crate::sprites::cache::{peak, Wants, BLOCKS, CACHE_MAX, STILLS_MAX};
use crate::sprites::character::{
    block_tile, character_palette, sprite_colors, Key, INITIAL_POSE, OBJ_PALETTES, OBJ_ROW,
};
use crate::sprites::extras::{
    first_place, map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, timer_mask,
    Image,
};
use crate::sprites::npc::{map_poses, pin_walkers, Graphic, Npc};
use crate::sprites::share::{share_slots, Sharer, SHARED_MAX};
use crate::sprites::split::{drawable_npcs, Ask, TILE_PREFIX};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};

/// The `ShowPicture` pictures this map carries, already decided and cut:
/// their names, for the notes; how many objects; their tiles; and how many
/// slots the console keeps them in, each of which takes a palette.
#[derive(Clone, Debug, Default)]
pub struct PictureAsked {
    pub name: String,
    pub objects: usize,
    pub image: Image,
    pub slots: usize,
}

/// What the cartridge decided about a map, and what other domains answered
/// about it.
#[derive(Clone, Debug, Default)]
pub struct MapRequest {
    pub map: i32,
    /// The names the port gives some graphics, by `(event id, page id)`.
    pub names: BTreeMap<(i32, i32), String>,
    /// Whether a test starts in this map: an empty event goes first.
    pub test_event: bool,
    /// The actors that can lead the party, in order: the first is who
    /// leads when the game starts.
    pub leaders: Vec<i32>,
    /// What the event compiler's scan answered of this map: its pages
    /// —who walks and who turns comes from them, see [`crate::moves`]—
    /// and the graphics routes change to, in the order the bytecode
    /// numbers them.
    pub pages: Vec<ScannedPage>,
    pub route_graphics: Vec<Key>,
    /// The events someone other than the map's pages sends walking: a test
    /// page's route.
    pub also_walk: BTreeSet<usize>,
    /// The System picture, if the cartridge carries the timer in this map.
    pub timer: Option<PathBuf>,
    pub rain: bool,
    pub picture: Option<PictureAsked>,
    /// Whether some page of the map can draw a battle animation.
    pub battle_animation: bool,
    /// The characters that appear in no other map of the cartridge.
    pub singles: HashSet<Key>,
    pub weights: BTreeMap<String, i64>,
    /// Which dither a translucent CharSet is drawn with, if one is.
    pub dither: String,
    /// The `TileSubstitution`s that can run in this map —its events' and
    /// its test pages'—, whose blocks are built before any page compiles;
    /// and the common events', which are only translated: a `CallEvent`
    /// can bring them into any map. See [`crate::substitutions`].
    pub substitutions: Vec<Triple>,
    pub common_substitutions: Vec<Triple>,
    /// The VRAM layouts the cartridge can give a map, as `(background
    /// tiles, sprite tiles, upper tiles)`. A map that fits none of them is
    /// converted again with still events sharing slots; empty, never.
    pub layouts: Vec<(usize, usize, usize)>,
    /// The colour-memory entries the message window takes after the
    /// backdrop: the background starts after them. See
    /// [`crate::background::layers::cgram_reserved`].
    pub window_colors: usize,
}

/// Something the conversion says, in order. A `stop` ends it there.
#[derive(Clone, Debug)]
pub struct Note {
    pub kind: &'static str,
    pub text: String,
    pub stop: bool,
}

fn note(text: String) -> Note {
    Note { kind: "note", text, stop: false }
}

/// A Python-like quoted name, as the messages have always shown them.
fn quoted(name: &str) -> String {
    format!("'{name}'")
}

/// The layers of one baking.
struct Layered {
    drawn: Drawn,
    converted: Converted,
}

fn layered(game: &Game, id: i32, window_colors: usize, baked: &BTreeMap<usize, (usize, i32)>) -> Result<Layered> {
    let mut cells: Vec<(usize, i16)> = baked.values().map(|&(c, t)| (c, t as i16)).collect();
    cells.sort();
    let drawn = draw(game, &LayersRequest { map: id, baked: cells, window_colors })?;
    let converted = crate::background::convert(&drawn.layers, window_colors)?;
    Ok(Layered { drawn, converted })
}

/// Whether baking left everybody else's colours where they were: the layer
/// above identical, the background with the same budget and merging no
/// more. The background's palette having new colours is not a change.
fn same_split(without: &Converted, with: &Converted) -> bool {
    let (a, b) = (&without.above, &with.above);
    let picture = |c: &Converted| c.pictures.iter().find(|p| p.name == "above").map(|p| p.picture.pixels.clone());
    a.tiles == b.tiles
        && a.cgram == b.cgram
        && a.tilemap == b.tilemap
        && a.first == b.first
        && a.merges.len() == b.merges.len()
        && picture(without) == picture(with)
        && without.background.budget == with.background.budget
        && without.background.merges.len() == with.background.merges.len()
}

/// The events baked into the map: by event, its cell and its tile id.
type Baked = BTreeMap<usize, (usize, i32)>;

/// Bakes `baked` unless it moves the split: the layers and what was baked.
fn bake_unless_split_moves(
    game: &Game,
    id: i32,
    window_colors: usize,
    without: Layered,
    baked: Baked,
    notes: &mut Vec<Note>,
) -> Result<(Layered, Baked)> {
    let with = layered(game, id, window_colors, &baked)?;
    if same_split(&without.converted, &with.converted) {
        return Ok((with, baked));
    }
    notes.push(note(format!(
        "  map {id}: baking {} event(s) moved its CGRAM split, so they are drawn",
        baked.len()
    )));
    Ok((without, BTreeMap::new()))
}

/// The open cell nearest the centre of the map —open on all four sides and
/// without an event—; the geometric centre in a map with none, which is a
/// cutscene room always reached by teleport.
fn hero_start(passable: &[u8], width: usize, height: usize, used: &HashSet<(i32, i32)>) -> (i32, i32) {
    let (cx, cy) = ((width / 2) as i64, (height / 2) as i64);
    let mut best: Option<(i64, usize, usize)> = None;
    for y in 0..height {
        for x in 0..width {
            if passable[y * width + x] & ALL == ALL && !used.contains(&(x as i32, y as i32)) {
                let d = (x as i64 - cx).pow(2) + (y as i64 - cy).pow(2);
                if best.is_none_or(|(b, ..)| d < b) {
                    best = Some((d, x, y));
                }
            }
        }
    }
    match best {
        Some((_, x, y)) => (x as i32, y as i32),
        None => ((width / 2) as i32, (height / 2) as i32),
    }
}

/// The objects of the map: what `sprite` in the answer says.
#[derive(Default)]
pub struct Objects {
    pub tiles: Vec<u8>,
    pub palettes: Vec<Vec<Color>>,
    pub place: Vec<(Slot, usize, usize)>,
    /// Per leader candidate: its palette, its pose bank and its colours,
    /// or nothing for one without a graphic.
    pub actors: Vec<(i32, usize, Option<usize>, Vec<u16>)>,
    pub timer: Option<(usize, usize)>,
    /// Which entries of its palette the timer's digits take: see
    /// `timer_mask`. 0 without a timer.
    pub timer_mask: u16,
    pub animated: Vec<Key>,
    pub banks: Vec<(Key, Vec<u8>)>,
    pub route_gfx: Vec<(usize, usize)>,
    pub rain: (usize, usize),
    pub turn_block: Option<usize>,
    pub image: (usize, usize),
    pub animation: Option<(usize, usize, usize)>,
    pub characters: usize,
    /// The still events that take turns in shared slots, if the map needed
    /// them.
    pub shared: Option<SharedObjects>,
    /// The cache of slots, if the map needed one.
    pub cache: Option<CacheObjects>,
}

/// The cache of slots, as the console reads it: see
/// [`crate::sprites::cache`].
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CacheObjects {
    /// Each event drawn: the still pose it starts with —an index into
    /// `stills`, which is what its row carries instead of a tile—, or
    /// `None` if it walks and has a slot of its own; and its palette.
    pub events: Vec<(usize, Option<usize>, usize)>,
    /// The still poses there can be, in the order they are numbered: the
    /// graphic, its character's entry in the pose table and its palette.
    pub stills: Vec<(Graphic, usize, usize)>,
    /// Each slot's block in the sprite bank.
    pub slots: Vec<usize>,
}

/// The slots still events take turns in, as the console reads them.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SharedObjects {
    /// Each event that takes turns: its slot, its pose —an index into
    /// `poses`— and the palette its character got.
    pub events: Vec<(usize, usize, usize, usize)>,
    /// The poses they show, as `(entry in the pose table, pose)`: the twelve
    /// poses of each character are in the cartridge, and the console uploads
    /// the one that comes into view.
    pub poses: Vec<(usize, i32)>,
    /// Each slot's block in the sprite bank.
    pub slots: Vec<usize>,
}

/// Everything the map came out as.
pub struct Whole {
    pub layers: Final,
    pub baked: BTreeMap<usize, (usize, i32)>,
    pub notes: Vec<Note>,
    pub npcs: Vec<Npc>,
    pub palette_cap: usize,
    pub objects: Option<Objects>,
    pub start: (i32, i32),
    /// Who walks, animates still and turns: what the page table is built
    /// with, so the caller gets it back.
    pub moves: Moves,
    /// Each substitution the map can run, with its block pairs, and the
    /// ones whose blocks could not be built.
    pub substitutions: SubstitutionAnswer,
}

/// The final layers and their blocks.
pub struct Final {
    pub converted: Converted,
    pub passability: Vec<u8>,
    pub blocks: Blocks,
}

/// The map `request.map`, whole.
///
/// As it always was, unless that fits none of `request.layouts`: then it is
/// converted again with the still events that are never on screen together
/// taking turns in the same slots —see [`plan_sharing`]—, and that one goes,
/// fitting or not. Only a map that does not fit changes: every other map
/// comes out byte for byte the same as without sharing.
pub fn convert(game: &Game, request: &MapRequest) -> Result<Whole> {
    let plain = convert_with(game, request, Mode::Plain)?;
    if request.layouts.is_empty() || fits(&plain, &request.layouts) {
        return Ok(plain);
    }
    // A map that fits no layout **with its pictures** is converted again
    // without them, before anything else: the pictures are what came last,
    // and they are the one thing whose absence the map survives —their
    // commands are accepted without being done—.
    if let Some(asked) = &request.picture {
        let without = MapRequest {
            picture: None,
            ..request.clone()
        };
        let mut done = convert(game, &without)?;
        done.notes.push(note(format!(
            "  map {}: WARNING, the pictures {} aren't drawn here: with their {} tiles the map \
             fits no VRAM layout",
            request.map,
            quoted(&asked.name),
            asked.image.tiles
        )));
        return Ok(done);
    }
    let shared = convert_with(game, request, Mode::Share)?;
    let shares = shared.objects.as_ref().is_some_and(|o| o.shared.is_some());
    if shares && fits(&shared, &request.layouts) {
        return Ok(shared);
    }
    // And a map that does not fit even so gets a cache of slots —see
    // `sprites::cache`—, if one fits.
    let cached = convert_with(game, request, Mode::Cache)?;
    if cached.objects.as_ref().is_some_and(|o| o.cache.is_some()) && fits(&cached, &request.layouts) {
        return Ok(cached);
    }
    Ok(if shares { shared } else { plain })
}

/// How a conversion lays out the slots: one per pose or walker, as always;
/// with the still ones that are never seen together taking turns —see
/// [`plan_sharing`]—; or with a cache —see [`crate::sprites::cache`]—.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Mode {
    Plain,
    Share,
    Cache,
}

/// What a cache conversion asks of the bank, before knowing how many slots
/// fit: the still poses there can be, who asks for what and how many can
/// be on screen at once by where they start.
struct CacheAsked {
    /// The still poses, sorted: an event showing one asks for its index.
    stills: Vec<Graphic>,
    /// By event drawn: the still pose it starts with, or `None` if it has
    /// a slot of its own while in view.
    events: Vec<(usize, Option<usize>)>,
    peak: usize,
    /// More slots than this are never used at once: one per still pose and
    /// one per event of its own.
    wanted: usize,
}

/// Whether the map fits some layout: what `rm2k-snes-mapdata` will ask
/// of it. A map that stopped fits: what it says is the stop.
fn fits(done: &Whole, layouts: &[(usize, usize, usize)]) -> bool {
    let Some(objects) = &done.objects else {
        return true;
    };
    let converted = &done.layers.converted;
    let background = converted.background.tiles.len() / 64;
    let above = converted.above.tiles.len() / 32;
    fits_in(background, above, objects.tiles.len() / 32, layouts)
}

fn fits_in(background: usize, above: usize, sprites: usize, layouts: &[(usize, usize, usize)]) -> bool {
    layouts.iter().any(|&(b, s, a)| background <= b && sprites <= s && above <= a)
}

/// `SetEventLocation` and `SwapEventLocations`: they move an event without
/// a route, so one moved by them is not still where it stands.
const SET_EVENT_LOCATION: i32 = 10860;
const SWAP_EVENT_LOCATIONS: i32 = 10870;
/// "This event" in a command's event parameter.
const THIS_EVENT: i32 = 10005;

/// The events something can place elsewhere: the map's pages' and the
/// common events' `SetEventLocation` and `SwapEventLocations`. `None` if a
/// common event places "this event", which can be anyone that calls it.
fn placed(events: &[Event], common: &[(i32, Vec<i32>)]) -> Option<BTreeSet<usize>> {
    let targets = |code: i32, params: &[i32]| -> Vec<i32> {
        match code {
            SET_EVENT_LOCATION => params.iter().take(1).copied().collect(),
            SWAP_EVENT_LOCATIONS => params.iter().take(2).copied().collect(),
            _ => Vec::new(),
        }
    };
    let by_id = |id: i32| events.iter().position(|e| e.id == id);
    let mut out = BTreeSet::new();
    for (k, event) in events.iter().enumerate() {
        for page in &event.pages {
            for (code, params) in &page.commands {
                for t in targets(*code, params) {
                    out.extend(if t == THIS_EVENT { Some(k) } else { by_id(t) });
                }
            }
        }
    }
    for (code, params) in common {
        for t in targets(*code, params) {
            if t == THIS_EVENT {
                return None;
            }
            out.extend(by_id(t));
        }
    }
    Some(out)
}

/// Which still events take turns in shared slots.
#[derive(Default)]
struct Plan {
    /// By event: its slot and the pose it shows.
    of: BTreeMap<usize, (usize, Graphic)>,
    /// Each slot's poses, in order: the first is the one the bank starts
    /// with.
    slots: Vec<Vec<Graphic>>,
}

/// The still events that take turns in shared slots, or `None` if no slot
/// would hold two different poses.
///
/// One takes turns if nothing moves it —no route, no animation in place,
/// no `SetEventLocation`—, it is not baked into the map, and every page that
/// draws it draws the same pose: the console uploads the pose of whoever
/// comes into view, and that is only right if where it stands and what it
/// shows never change. One whose pose a still event that does not take
/// turns already shows keeps that one's slot, as always. The rest are
/// coloured by [`share_slots`]; a slot where everyone shows the same pose
/// is an ordinary still slot, and only those with more than one go to the
/// console.
fn plan_sharing(npcs: &[Npc], movable: &BTreeSet<usize>, baked: &Baked, placed: &BTreeSet<usize>) -> Option<Plan> {
    let shows = |npc: &Npc| -> BTreeSet<Graphic> {
        let mut out = BTreeSet::from([(npc.charset.clone(), npc.index, npc.pose)]);
        if npc.changes {
            out.extend(npc.graphics.iter().flatten().filter(|g| !npc.outside.contains(&(g.0.clone(), g.1))).cloned());
        }
        out
    };
    let mut fixed: BTreeSet<Graphic> = BTreeSet::new();
    let mut candidates = Vec::new();
    for npc in npcs.iter().filter(|n| !movable.contains(&n.event)) {
        let poses = shows(npc);
        let takes_turns = poses.len() == 1 && !baked.contains_key(&npc.event) && !placed.contains(&npc.event);
        if takes_turns {
            candidates.push(Sharer { event: npc.event, x: npc.x, y: npc.y, pose: poses.into_iter().next()? });
        } else {
            fixed.extend(poses);
        }
    }
    let sharers: Vec<Sharer> = candidates.into_iter().filter(|c| !fixed.contains(&c.pose)).collect();
    let mut plan = Plan::default();
    for group in share_slots(&sharers) {
        let poses: Vec<Graphic> =
            group.iter().map(|&i| sharers[i].pose.clone()).collect::<BTreeSet<_>>().into_iter().collect();
        if poses.len() < 2 {
            continue;
        }
        let slot = plan.slots.len();
        for &i in &group {
            plan.of.insert(sharers[i].event, (slot, sharers[i].pose.clone()));
        }
        plan.slots.push(poses);
    }
    (!plan.slots.is_empty()).then_some(plan)
}

fn convert_with(game: &Game, request: &MapRequest, mode: Mode) -> Result<Whole> {
    let id = request.map;
    let raw = game.map(id)?;
    let chipset = game.chipset(raw.chipset_id)?;
    let flags = passability_table(&chipset.passable_data_lower, &chipset.passable_data_upper);
    let events: Vec<Event> = events(&raw.events, &request.names, request.test_event);
    let mut drawer = Drawer::new(game, &request.dither);
    let chipset_name = chipset.chipset_name.clone();
    let mut npcs0 = collect_npcs(&events, &chipset_name, &flags);
    let mut notes = Vec::new();

    // The layers, and again with the opaque events baked in. **Both** are
    // converted and compared, because baking adds colours to the
    // background: if that moved the split, cells that have nothing to do
    // with the baking would change, and the map goes unbaked.
    let lower: Vec<i32> = raw.lower_layer.iter().map(|&t| t as i32).collect();
    let upper: Vec<i32> = raw.upper_layer.iter().map(|&t| t as i32).collect();
    let map = baking::Map {
        width: raw.width as usize,
        lower: &lower,
        upper: &upper,
        flags: &flags,
        chipset: &chipset_name,
    };
    let mut baked = bakeable(&mut drawer, &map, &events, &npcs0)?;
    let without = layered(game, id, request.window_colors, &BTreeMap::new())?;
    let mut layers = if baked.is_empty() {
        without
    } else {
        let (layers, kept) = bake_unless_split_moves(game, id, request.window_colors, without, baked, &mut notes)?;
        baked = kept;
        layers
    };

    // The characters.
    let actors = game.actors()?;
    let leader = |actor: &i32| -> Result<Key> {
        actors
            .get(actor)
            .cloned()
            .ok_or_else(|| Bad::answer(format!("actor {actor} is not in the database")))
    };
    let leaders: Vec<Key> = request.leaders.iter().map(leader).collect::<Result<_>>()?;
    let who = moves(&request.pages, &events, &npcs0, &chipset_name, &request.also_walk);
    let turning = &who.turning;
    let mut wanted: Vec<String> = leaders.iter().map(|k| k.0.clone()).collect();
    for npc in &npcs0 {
        wanted.extend(npc.keys().into_iter().map(|k| k.0));
    }
    wanted.extend(request.route_graphics.iter().map(|k| k.0.clone()));
    wanted.extend(turning.values().flatten().map(|k| k.0.clone()));
    for name in &wanted {
        drawer.draw(name)?;
    }
    // Before anything counts poses or palettes: a walker pinned to a blank
    // slot of its CharSet walks unseen. See `pin_walkers`.
    let blank_pages = {
        let sheets = drawer.sheets();
        pin_walkers(&mut npcs0, &who.movable, |key| {
            sheets
                .get(&key.0)
                .and_then(Option::as_ref)
                .is_some_and(|s| sprite_colors(s, key.1, None).is_empty())
        })
    };
    let glyphs = match &request.timer {
        Some(path) => Some(rm2k_render::system::timer(&picture::read_rm2k(path)?)),
        None => None,
    };
    let timer = glyphs.as_ref().map(timer_colors).unwrap_or_default();
    let poses = map_poses(
        &leaders,
        &npcs0,
        &who.movable,
        turning,
        &request.route_graphics,
        &who.animates_still,
    );

    let sheets = drawer.sheets().clone();
    let ask = |cap: usize| Ask {
        sheets: &sheets,
        leaders: &leaders,
        cap,
        route_graphics: &request.route_graphics,
        timer_colors: &timer,
        only_here: &request.singles,
        poses: &poses,
        weights: &request.weights,
    };
    // All eight palettes, or seven in a map that shows battle animations:
    // the box needs a whole one. Unless the timer does not fit with seven.
    let palette_cap = if !request.battle_animation {
        OBJ_PALETTES
    } else if timer.is_empty() {
        OBJ_PALETTES - 1
    } else {
        let d = drawable_npcs(&ask(OBJ_PALETTES - 1), npcs0.clone()).map_err(|b| Bad::answer(b.0))?;
        notes.extend(d.notes.into_iter().map(note));
        let mut clone = d.split.palettes.clone();
        if first_place(&mut clone, &d.split.leader_owned, &timer, OBJ_PALETTES - 1).is_none() {
            OBJ_PALETTES
        } else {
            OBJ_PALETTES - 1
        }
    };
    let d = drawable_npcs(&ask(palette_cap), npcs0.clone()).map_err(|b| Bad::answer(b.0))?;
    notes.extend(d.notes.iter().cloned().map(note));
    let split = d.split;
    let mut npcs = d.npcs;
    if !split.lent.is_empty() {
        let mut names: Vec<String> = split.lent.iter().map(|k| format!("{}:{}", k.0, k.1)).collect();
        names.sort();
        notes.push(note(format!(
            "  map {id}: {} graphic(s) without a palette of their own, drawn with someone else's: {}",
            split.lent.len(),
            names.join(", ")
        )));
    }
    // A baked event drawn with someone else's palette can't be hidden: the
    // sprite and the tile would show different colours. It goes back to
    // being a sprite.
    let lent_baked: Vec<usize> = baked
        .keys()
        .copied()
        .filter(|e| {
            npcs.iter()
                .any(|n| n.event == *e && split.lent.contains(&(n.charset.clone(), n.index)))
        })
        .collect();
    if !lent_baked.is_empty() {
        notes.push(note(format!(
            "  map {id}: event {} is drawn with someone else's palette, so it isn't baked",
            lent_baked.iter().map(|e| (e + 1).to_string()).collect::<Vec<_>>().join(", ")
        )));
        for e in &lent_baked {
            baked.remove(e);
        }
        layers = layered(game, id, request.window_colors, &BTreeMap::new())?;
        if !baked.is_empty() {
            let (again, kept) = bake_unless_split_moves(game, id, request.window_colors, layers, baked, &mut notes)?;
            layers = again;
            baked = kept;
        }
    }
    if !baked.is_empty() {
        notes.push(note(format!(
            "  map {id}: {} opaque event(s) baked into the map: {}",
            baked.len(),
            baked.keys().map(|e| (e + 1).to_string()).collect::<Vec<_>>().join(", ")
        )));
    }

    let (passability, mut blocks) = stage_layers::blocks(&layers.drawn, &layers.converted)?;
    let substituted = substitute(
        id,
        &mut blocks,
        &flags,
        &chipset,
        &request.substitutions,
        &request.common_substitutions,
    )?;
    let used: HashSet<(i32, i32)> = npcs0.iter().map(|n| (n.x, n.y)).collect();
    let (start_map, start_x, start_y) = game.start()?;
    let start = if id == start_map {
        (start_x, start_y)
    } else {
        hero_start(&passability, raw.width as usize, raw.height as usize, &used)
    };
    let mut done = Whole {
        layers: Final {
            converted: layers.converted,
            passability,
            blocks,
        },
        baked: baked.clone(),
        notes,
        npcs: Vec::new(),
        palette_cap,
        objects: None,
        start,
        moves: who.clone(),
        substitutions: substituted,
    };

    for (event, tile) in &d.discarded {
        let text = format!(
            "map {id}: event {}, drawn with tile {}, doesn't fit in the {palette_cap} sprite palettes and \
             isn't drawn",
            event + 1,
            tile.get(TILE_PREFIX.len()..).unwrap_or("")
        );
        let stop = changes_graphic(&events[*event]);
        done.notes.push(Note { kind: "discard", text, stop });
        if stop {
            return Ok(done);
        }
    }

    // Who changes pose, and carries their twelve to the cartridge: the
    // leader candidates with a graphic —the first leader first— and the
    // events that walk; the graphics routes change to; and the ones that
    // turn toward the hero.
    let mut with_graphic = Vec::new();
    for (actor, key) in request.leaders.iter().zip(&leaders) {
        let Some(image) = sheets.get(&key.0).and_then(Option::as_ref) else {
            done.notes.push(Note { kind: "stop", text: format!("can't find CharSet {}", quoted(&key.0)), stop: true });
            return Ok(done);
        };
        if !sprite_colors(image, key.1, None).is_empty() {
            with_graphic.push(*actor);
        }
    }
    let first = leaders
        .first()
        .cloned()
        .ok_or_else(|| Bad::answer("the party is empty: there is nothing to draw the hero with"))?;
    let mut animated: Vec<Key> = Vec::new();
    for actor in &with_graphic {
        let key = leader(actor)?;
        if !animated.contains(&key) {
            animated.push(key);
        }
    }
    animated.sort_by_key(|k| *k != first);
    for npc in &npcs {
        let key = (npc.charset.clone(), npc.index);
        if who.movable.contains(&npc.event) && !animated.contains(&key) {
            animated.push(key);
        }
    }
    let mut visible = Vec::new();
    for key in &request.route_graphics {
        let colors = sheets.get(&key.0).and_then(Option::as_ref).map(|s| sprite_colors(s, key.1, None));
        let shows = colors.as_ref().is_some_and(|c| !c.is_empty()) && split.palette_of.contains(key);
        visible.push(shows);
        if shows && !animated.contains(key) {
            animated.push(key.clone());
        }
    }
    for pairs in turning.values() {
        for pair in pairs {
            if split.palette_of.contains(pair) && !animated.contains(pair) {
                animated.push(pair.clone());
            }
        }
    }
    for (key, shows) in request.route_graphics.iter().zip(&visible) {
        let opaque = sheets
            .get(&key.0)
            .and_then(Option::as_ref)
            .is_some_and(|s| !sprite_colors(s, key.1, None).is_empty());
        if !shows && opaque {
            done.notes.push(Note {
                kind: "discard",
                text: format!(
                    "map {id}: graphic {}:{}, which a route changes to, doesn't fit in the {palette_cap} \
                     sprite palettes: that command hides the event instead of changing it",
                    key.0, key.1
                ),
                stop: true,
            });
            return Ok(done);
        }
    }

    // The still ones that take turns, if this conversion is the one that
    // shares: see `plan_sharing`.
    let plan = if mode == Mode::Share {
        match placed(&events, &game.common_commands()?) {
            None => {
                done.notes.push(note(format!(
                    "  map {id}: a common event places \"this event\", so no still event takes turns in a slot"
                )));
                None
            }
            Some(placed) => plan_sharing(&npcs, &who.movable, &baked, &placed),
        }
    } else {
        None
    };
    let plan = match plan {
        Some(p) if p.slots.len() > SHARED_MAX => {
            done.notes.push(note(format!(
                "  map {id}: still events would take turns in {} slots and the console keeps {SHARED_MAX}",
                p.slots.len()
            )));
            None
        }
        p => p,
    };

    // The slots of the VRAM bank, one pose each: the hero in block 0, each
    // event that walks with its own, the still ones shared by (CharSet,
    // index, pose), and the ones they take turns in.
    let mut slots: Vec<SlotPose> = Vec::new();
    if !with_graphic.is_empty() {
        let (charset, index) = animated[0].clone();
        slots.push(SlotPose { slot: Slot::Hero, charset, index, pose: INITIAL_POSE });
    }
    for npc in npcs.iter_mut() {
        if who.movable.contains(&npc.event) {
            if npc.changes {
                // Walking wins over the page's graphic; whether the row is
                // visible still follows the page.
                npc.appears = true;
                npc.changes = false;
            }
            // Its pages with a blank slot hide the row, like a page without
            // a graphic: the row now walks with another one's poses.
            if let Some(blanks) = blank_pages.get(&npc.event) {
                npc.outside.extend(blanks.iter().cloned());
            }
            if mode == Mode::Cache {
                continue; // a slot of the cache's while it is in view
            }
            slots.push(SlotPose {
                slot: Slot::Event(npc.event),
                charset: npc.charset.clone(),
                index: npc.index,
                pose: npc.pose,
            });
        } else if plan.as_ref().is_some_and(|p| p.of.contains_key(&npc.event)) {
            // It takes turns in a shared slot, which goes after the turn's.
        } else if mode == Mode::Cache {
            // Its pose goes to a slot of the cache's while it is in view.
        } else {
            let mut poses = vec![(npc.charset.clone(), npc.index, npc.pose)];
            if npc.changes {
                poses.extend(
                    npc.graphics
                        .iter()
                        .flatten()
                        .filter(|g| !npc.outside.contains(&(g.0.clone(), g.1)))
                        .cloned(),
                );
            }
            for (charset, index, pose) in poses {
                let slot = Slot::Still(charset.clone(), index, pose);
                if !slots.iter().any(|s| s.slot == slot) {
                    slots.push(SlotPose { slot, charset, index, pose });
                }
            }
        }
    }
    // The turn slot: one more pose, for the still one that turns toward the
    // hero; only the event the hero triggered turns, one at a time.
    let still_turning = npcs.iter().find(|n| {
        turning.contains_key(&n.event)
            && !who.movable.contains(&n.event)
            && turning[&n.event].iter().any(|p| split.palette_of.contains(p))
    });
    if let Some(n) = still_turning {
        slots.push(SlotPose { slot: Slot::Turn, charset: n.charset.clone(), index: n.index, pose: n.pose });
    }
    // The shared ones start with their first pose: the console does not
    // trust it anyway and uploads whichever comes into view. Their twelve
    // poses go to the cartridge, which is where it uploads them from.
    let mut shared_poses: Vec<Graphic> = Vec::new();
    if let Some(plan) = &plan {
        for (s, poses) in plan.slots.iter().enumerate() {
            let (charset, index, pose) = poses[0].clone();
            slots.push(SlotPose { slot: Slot::Shared(s), charset, index, pose });
            for p in poses {
                let key = (p.0.clone(), p.1);
                if !animated.contains(&key) {
                    animated.push(key);
                }
                if !shared_poses.contains(p) {
                    shared_poses.push(p.clone());
                }
            }
        }
        shared_poses.sort();
        done.notes.push(note(format!(
            "  map {id}: {} still events take turns in {} slots, never two of them on screen at once",
            plan.of.len(),
            plan.slots.len()
        )));
    }
    // The cache's still poses —every graphic a still event can show—, with
    // their characters' twelve poses in the cartridge, which is where the
    // console uploads them from; and how many slots can be wanted at once.
    let cache_asked = if mode == Mode::Cache {
        let shows = |npc: &Npc| -> BTreeSet<Graphic> {
            let mut out = BTreeSet::from([(npc.charset.clone(), npc.index, npc.pose)]);
            if npc.changes {
                out.extend(npc.graphics.iter().flatten().filter(|g| !npc.outside.contains(&(g.0.clone(), g.1))).cloned());
            }
            out
        };
        let mut stills = BTreeSet::new();
        for npc in npcs.iter().filter(|n| !who.movable.contains(&n.event)) {
            stills.extend(shows(npc));
        }
        let stills: Vec<Graphic> = stills.into_iter().collect();
        if stills.len() > STILLS_MAX {
            done.notes.push(note(format!(
                "  map {id}: its still events show {} poses and a cache names {STILLS_MAX}",
                stills.len()
            )));
            None
        } else {
            for g in &stills {
                let key = (g.0.clone(), g.1);
                if !animated.contains(&key) {
                    animated.push(key);
                }
            }
            let mut events = Vec::new();
            let mut wants = Vec::new();
            for npc in &npcs {
                let walks = who.movable.contains(&npc.event);
                let start = if walks {
                    None
                } else {
                    stills.iter().position(|g| *g == (npc.charset.clone(), npc.index, npc.pose))
                };
                let want = match start {
                    Some(v) if shows(npc).len() == 1 => Wants::Still(v),
                    _ => Wants::Own(npc.event),
                };
                events.push((npc.event, start));
                wants.push((npc.x, npc.y, want));
            }
            let own = wants.iter().filter(|(_, _, w)| matches!(w, Wants::Own(_))).count();
            Some(CacheAsked {
                peak: peak(&wants, raw.width as i32, raw.height as i32),
                wanted: stills.len() + own,
                stills,
                events,
            })
        }
    } else {
        None
    };
    let mut characters = animated.clone();
    for s in &slots {
        let key = (s.charset.clone(), s.index);
        if !characters.contains(&key) {
            characters.push(key);
        }
    }
    let mut seen_names = HashSet::new();
    for (charset, _) in &characters {
        if !seen_names.insert(charset.clone()) {
            continue;
        }
        if drawer_missing(&sheets, charset) {
            done.notes.push(Note { kind: "stop", text: format!("can't find CharSet {}", quoted(charset)), stop: true });
            return Ok(done);
        }
    }

    let bank = match build_characters(&sheets, &characters, &slots, &split) {
        Ok(b) => b,
        Err(b) => {
            done.notes.push(Note { kind: "stop", text: b.0, stop: true });
            return Ok(done);
        }
    };
    if bank.palettes.len() > palette_cap {
        done.notes.push(Note {
            kind: "stop",
            text: format!(
                "the map uses {} characters in {} palettes and there are {palette_cap} sprite ones",
                characters.len(),
                bank.palettes.len()
            ),
            stop: true,
        });
        return Ok(done);
    }
    let banks = pose_bank(&sheets, &animated, &bank.colors).map_err(|b| Bad::answer(b.0))?;
    let animated_index: HashMap<Key, usize> = animated.iter().enumerate().map(|(k, p)| (p.clone(), k)).collect();
    let route_gfx: Vec<(usize, usize)> = request
        .route_graphics
        .iter()
        .zip(&visible)
        .map(|(pair, shows)| {
            if *shows {
                (animated_index[pair], split.palette_of.get(pair).unwrap_or(0))
            } else {
                (0xFF, 0)
            }
        })
        .collect();

    let mut place = bank.place;
    let mut bank_tiles = bank.tiles;
    // The cache's slots go blank after the fixed ones, as many as fit: see
    // `cache_slots`.
    let mut cache = None;
    if let Some(asked) = &cache_asked {
        let fixed = place.len();
        let converted = &done.layers.converted;
        let (background, above) = (converted.background.tiles.len() / 64, converted.above.tiles.len() / 32);
        let fit = |slots: usize| -> bool {
            let mut tiles = bank_tiles.clone();
            grow_blocks(&mut tiles, fixed + slots);
            extras(id, request, glyphs.as_ref(), tiles, bank.palettes.clone(), &split.leader_owned, palette_cap)
                .is_ok_and(|e| fits_in(background, above, e.tiles.len() / 32, &request.layouts))
        };
        let most = asked.wanted.min(BLOCKS.saturating_sub(fixed)).min(CACHE_MAX);
        if let Some(slots) = (1..=most).rev().find(|&n| fit(n)) {
            grow_blocks(&mut bank_tiles, fixed + slots);
            place.extend((0..slots).map(|k| (Slot::Cache(k), fixed + k, 0)));
            done.notes.push(note(format!(
                "  map {id}: {} events take a slot of a cache of {slots} when they come into view, \
                 {} still poses among them; by where they start, up to {} are on screen at once",
                asked.events.len(),
                asked.stills.len(),
                asked.peak
            )));
            if asked.peak > slots {
                done.notes.push(note(format!(
                    "  map {id}: WARNING, by where they start up to {} events are on screen at once and \
                     the cache has {slots} slots: the ones drawn last wait for one",
                    asked.peak
                )));
            }
            cache = Some(slots);
        }
    }
    let Extras { tiles, palettes, timer_at, rain, image, animation, notes: extra_notes } =
        match extras(id, request, glyphs.as_ref(), bank_tiles, bank.palettes, &split.leader_owned, palette_cap) {
            Ok(e) => e,
            Err(stop) => {
                done.notes.push(stop);
                return Ok(done);
            }
        };
    done.notes.extend(extra_notes);
    // The baked events' rows start hidden: their tile is already in the
    // map. The row is still whole for its logic.
    for npc in npcs.iter_mut() {
        if baked.contains_key(&npc.event) {
            npc.visible = false;
        }
    }
    // Each leader candidate's palette, pose bank and colours, in the order
    // its poses were packed with.
    let mut actor_rows = Vec::new();
    for (actor, key) in request.leaders.iter().zip(&leaders) {
        if !with_graphic.contains(actor) {
            actor_rows.push((*actor, 0, None, Vec::new()));
            continue;
        }
        let image = crate::sprites::character::sheet(&sheets, &key.0).map_err(|b| Bad::answer(b.0))?;
        let (own, _, _) = character_palette(image, key.1, None, None).map_err(|b| Bad::answer(b.0))?;
        actor_rows.push((
            *actor,
            bank.palette_of.get(key).unwrap_or(0),
            Some(animated_index[key]),
            own.iter().map(|&[r, g, b]| voodoo::cgram_word((r, g, b))).collect(),
        ));
    }
    let turn_block = place.iter().find(|(s, ..)| *s == Slot::Turn).map(|(_, b, _)| *b);
    let shared = plan.as_ref().map(|plan| SharedObjects {
        events: plan
            .of
            .iter()
            .map(|(event, (slot, pose))| {
                let key = (pose.0.clone(), pose.1);
                (
                    *event,
                    *slot,
                    shared_poses.iter().position(|p| p == pose).unwrap(),
                    bank.palette_of.get(&key).unwrap_or(0),
                )
            })
            .collect(),
        poses: shared_poses.iter().map(|p| (animated_index[&(p.0.clone(), p.1)], p.2)).collect(),
        slots: (0..plan.slots.len())
            .map(|s| place.iter().find(|(slot, ..)| *slot == Slot::Shared(s)).map(|(_, b, _)| *b).unwrap())
            .collect(),
    });
    let cache = match (cache, &cache_asked) {
        (Some(_), Some(asked)) => {
            let palette = |charset: &str, index: i32| bank.palette_of.get(&(charset.to_string(), index)).unwrap_or(0);
            Some(CacheObjects {
                events: asked
                    .events
                    .iter()
                    .map(|&(event, start)| {
                        let npc = npcs.iter().find(|n| n.event == event).expect("the cache's events are drawn");
                        (event, start, palette(&npc.charset, npc.index))
                    })
                    .collect(),
                stills: asked
                    .stills
                    .iter()
                    .map(|g| (g.clone(), animated_index[&(g.0.clone(), g.1)], palette(&g.0, g.1)))
                    .collect(),
                slots: place.iter().filter(|(s, ..)| matches!(s, Slot::Cache(_))).map(|(_, b, _)| *b).collect(),
            })
        }
        _ => None,
    };
    done.baked = baked;
    done.npcs = npcs;
    // On the palettes as they end: the rain may still have grown the
    // timer's, and a colour's first entry is where the glyphs have it.
    let timer_mask = timer_at.map_or(0, |(_, palette)| timer_mask(&timer, &palettes[palette]));
    done.objects = Some(Objects {
        tiles,
        palettes,
        place,
        actors: actor_rows,
        timer: timer_at,
        timer_mask,
        animated,
        banks,
        route_gfx,
        rain,
        turn_block,
        image,
        animation,
        characters: characters.len(),
        shared,
        cache,
    });
    Ok(done)
}

/// What goes at the end of the bank, after the slots: the timer's digits,
/// the raindrops, the pictures and the battle animation's box, and what the
/// conversion says of them.
struct Extras {
    tiles: Vec<u8>,
    palettes: Vec<Vec<Color>>,
    timer_at: Option<(usize, usize)>,
    rain: (usize, usize),
    image: (usize, usize),
    animation: Option<(usize, usize, usize)>,
    notes: Vec<Note>,
}

/// The extras after `tiles`. The timer's digits not fitting stops the
/// conversion: that is the error.
fn extras(
    id: i32,
    request: &MapRequest,
    glyphs: Option<&rm2k_render::Picture>,
    mut tiles: Vec<u8>,
    mut palettes: Vec<Vec<Color>>,
    leader_owned: &BTreeSet<usize>,
    palette_cap: usize,
) -> std::result::Result<Extras, Note> {
    let mut notes = Vec::new();
    let mut timer_at = None;
    if let Some(glyphs) = glyphs {
        match timer_digits(glyphs, &mut tiles, &mut palettes, leader_owned, palette_cap) {
            Ok(at) => timer_at = Some(at),
            Err(b) => return Err(Note { kind: "stop", text: b.0, stop: true }),
        }
    }
    let mut rain = (0, 0);
    if request.rain {
        match rain_drops(&mut tiles, &mut palettes, leader_owned, timer_at, palette_cap) {
            Some(at) => rain = at,
            None => notes.push(note(format!(
                "  map {id}: WARNING, the raindrops don't fit in the sprite palettes and it doesn't rain here"
            ))),
        }
    }
    // The pictures, with a palette per slot from the top. They yield to the
    // battle animation's box, which was there first: a map whose palettes
    // leave room for one of the two keeps the animation, and its pictures
    // are not drawn —the caller sees `image` at zero and compiles none—.
    let mut image = (0, 0);
    if let Some(asked) = &request.picture {
        let previous = if rain.0 != 0 { rain.0 } else { timer_at.map_or(0, |t| t.0) };
        let box_palette = usize::from(request.battle_animation);
        let mut trial = tiles.clone();
        let placed = if palettes.len() + box_palette + asked.slots <= OBJ_PALETTES {
            picture_of_image(&asked.image, &mut trial, &palettes, previous, asked.slots)
        } else {
            None
        };
        match placed {
            Some(at) => {
                image = at;
                tiles = trial;
                notes.push(note(format!(
                    "  map {id}: the pictures {}, {} objects in {} tiles from {}, {} palette(s) from the top",
                    quoted(&asked.name),
                    asked.objects,
                    asked.image.tiles,
                    at.0,
                    at.1
                )));
            }
            None => notes.push(note(format!(
                "  map {id}: WARNING, the pictures {} aren't drawn here: the map uses {} sprite \
                 palettes{} and they need {} more",
                quoted(&asked.name),
                palettes.len(),
                if box_palette != 0 { " and the battle animation's box one" } else { "" },
                asked.slots
            ))),
        }
    }
    let mut animation = None;
    if request.battle_animation {
        let mut trial = tiles.clone();
        match map_animation(&mut trial, &palettes, image.1) {
            None => notes.push(note(format!(
                "  map {id}: WARNING, battle animations aren't drawn here: the map already uses the \
                 {OBJ_PALETTES} sprite palettes and the box needs a whole one"
            ))),
            Some((base, pal)) => {
                animation = Some((trial.len() / 32, base, pal));
                tiles = trial;
            }
        }
    }
    Ok(Extras { tiles, palettes, timer_at, rain, image, animation, notes })
}

/// `tiles` long enough to hold `blocks` blocks of 32x32, the new ones blank.
fn grow_blocks(tiles: &mut Vec<u8>, blocks: usize) {
    if blocks == 0 {
        return;
    }
    let needed = (block_tile(blocks - 1) + 3 * OBJ_ROW + 4) * 32;
    if tiles.len() < needed {
        tiles.resize(needed, 0);
    }
}

fn drawer_missing(sheets: &crate::sprites::character::Sheets, name: &str) -> bool {
    !matches!(sheets.get(name), Some(Some(_)))
}

fn key_json(k: &Key) -> Value {
    json!([k.0, k.1])
}

fn slot_json(s: &Slot) -> Value {
    match s {
        Slot::Hero => json!({"hero": true}),
        Slot::Event(e) => json!({"event": e}),
        Slot::Still(c, i, p) => json!({"charset": c, "index": i, "pose": p}),
        Slot::Turn => json!({"turn": true}),
        Slot::Shared(s) => json!({"shared": s}),
        Slot::Cache(s) => json!({"cache": s}),
    }
}

fn npc_json(n: &Npc) -> Value {
    json!({
        "event": n.event, "x": n.x, "y": n.y,
        "charset": n.charset, "index": n.index, "pose": n.pose,
        "layer": n.layer, "blocks": n.blocks, "speed": n.speed,
        "animates": n.animates, "visible": n.visible, "changes": n.changes,
        "graphics": n.graphics.iter().map(|g| g.as_ref().map(|(c, i, p)| json!([c, i, p]))).collect::<Vec<_>>(),
        "layers": n.layers,
        "tile_pass": n.tile_pass,
        "outside": n.outside.iter().map(key_json).collect::<Vec<_>>(),
        "appears": n.appears,
    })
}

/// The file the answer is written to.
pub const ANSWER_FILE: &str = "map.json";
/// The sprite bank's tiles.
pub const SPRITE_TILES: &str = "sprites.bin";

/// Writes the map into `out`: the layers as `layers` writes them, the
/// sprite bank and each pose bank as binaries, and the rest in `map.json`.
pub fn write(out: &Path, done: &Whole) -> Result<()> {
    let layers = &done.layers;
    stage_layers::write(out, &layers.converted, &layers.passability, &layers.blocks)?;
    let file = |name: &str, bytes: &[u8]| {
        std::fs::write(out.join(name), bytes).map_err(|e| Bad::usage(format!("{}: {e}", out.join(name).display())))
    };
    let objects = match &done.objects {
        None => Value::Null,
        Some(o) => {
            file(SPRITE_TILES, &o.tiles)?;
            let mut banks = Vec::new();
            for (k, (key, data)) in o.banks.iter().enumerate() {
                let name = format!("poses-{k}.bin");
                file(&name, data)?;
                banks.push(json!([key.0, key.1, name]));
            }
            json!({
                "tiles": SPRITE_TILES,
                "palettes": o.palettes,
                "place": o.place.iter().map(|(s, b, p)| json!([slot_json(s), b, p])).collect::<Vec<_>>(),
                "actors": o.actors.iter().map(|(a, p, k, w)| json!([a, p, k, w])).collect::<Vec<_>>(),
                "timer": o.timer.map(|(b, p)| json!([b, p])),
                "timer_mask": o.timer_mask,
                "animated": o.animated.iter().map(key_json).collect::<Vec<_>>(),
                "banks": banks,
                "route_gfx": o.route_gfx.iter().map(|(k, p)| json!([k, p])).collect::<Vec<_>>(),
                "rain": [o.rain.0, o.rain.1],
                "turn_block": o.turn_block,
                "image": [o.image.0, o.image.1],
                "animation": o.animation.map(|(c, b, p)| json!({"count": c, "base": b, "palette": p})),
                "characters": o.characters,
                "shared": o.shared.as_ref().map(|sh| json!({
                    "events": sh.events.iter().map(|(e, s, p, pal)| json!([e, s, p, pal])).collect::<Vec<_>>(),
                    "poses": sh.poses.iter().map(|(k, p)| json!([k, p])).collect::<Vec<_>>(),
                    "slots": sh.slots,
                })),
                "cache": o.cache.as_ref().map(|c| json!({
                    "events": c.events.iter().map(|(e, v, pal)| json!([e, v, pal])).collect::<Vec<_>>(),
                    "stills": c.stills.iter().map(|((cs, i, p), k, pal)| json!([cs, i, p, k, pal])).collect::<Vec<_>>(),
                    "slots": c.slots,
                })),
            })
        }
    };
    let answer = json!({
        "baked": done.baked.iter().map(|(e, (c, t))| json!([e, c, t])).collect::<Vec<_>>(),
        "notes": done.notes.iter().map(|n| json!({"kind": n.kind, "text": n.text, "stop": n.stop})).collect::<Vec<_>>(),
        "npcs": done.npcs.iter().map(npc_json).collect::<Vec<_>>(),
        "palette_cap": done.palette_cap,
        "start": [done.start.0, done.start.1],
        "sprite": objects,
        "movable": done.moves.movable,
        "animates_still": done.moves.animates_still,
        "substitutions": {
            "table": done.substitutions.table.iter().map(|((u, o, n), pairs)| {
                json!([u, o, n, pairs.as_ref().map(|p| p.iter().map(|(a, b)| json!([a, b])).collect::<Vec<_>>())])
            }).collect::<Vec<_>>(),
            "missing": done.substitutions.missing.iter().map(|(u, o, n)| json!([u, o, n])).collect::<Vec<_>>(),
        },
        "turning": done.moves.turning.iter().map(|(e, pairs)| json!([e, pairs.iter().map(key_json).collect::<Vec<_>>()])).collect::<Vec<_>>(),
    });
    file(ANSWER_FILE, answer.to_string().as_bytes())
}
