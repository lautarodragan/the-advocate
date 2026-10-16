//! A whole map, as the cartridge carries it: its layers, the events baked
//! into them, its characters as objects and the extras at the end of their
//! bank, its blocks and where the hero starts.
//!
//! It is the one place that needs both halves of colour memory at once:
//! baking an event takes a sprite into the upper layer, and it is only
//! done if the layers' split of colour memory does not move —and undone if
//! the object palettes had to lend that event someone else's colours—.

use crate::baking::{self, bakeable};
use crate::decor::{self, Decoration};
use crate::events::{changes_graphic, collect_npcs, events, Event};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::layers::{self as stage_layers, draw, Drawn};
use crate::moves::{moves, Animate, Moves, ScannedPage};
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
    block_tile, character_palette, nearest, sprite_colors, Key, INITIAL_POSE, OBJ_PALETTES, OBJ_ROW,
};
use crate::sprites::extras::{
    first_place, map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, timer_mask,
    Image,
};
use crate::sprites::npc::{map_poses, pin_walkers, Graphic, Npc, NPC_MAX};
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
    /// Those of `route_graphics` that only the hero ever shows —no route
    /// gives them to an event—: they can share the leaders' palette with
    /// colours of their own, like a leader. See `drawable_npcs`.
    pub hero_graphics: BTreeSet<Key>,
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
    /// Whether the map's panorama is shown, and in how many tiles: see
    /// [`crate::request::LayersRequest`].
    pub panorama: Option<crate::request::PanoramaBudget>,
    /// Set by the conversion itself, never by the caller: the background
    /// is drawn with at most this many tiles. See [`convert`].
    pub fuse_tiles: Option<usize>,
    /// Whether the events that are only a drawing are painted into the
    /// background: see [`crate::decor`]. A project's choice, off unless it
    /// says so.
    pub decorative: bool,
    /// The commands of the test pages that run in this map, as `(code,
    /// parameters)`: only for what they name, so nobody that a test moves
    /// is taken for decoration. Only read if `decorative`.
    pub test_commands: Vec<(i32, Vec<i32>)>,
}

/// Something the conversion says, in order. A `stop` ends it there.
///
/// `loss` is set when what it says is the map drawn with less than RM2k
/// draws it: a stable slug the converter lists in the cartridge's
/// degradations, with the events it is about, by RM2k id, if it is about
/// some.
#[derive(Clone, Debug, Default)]
pub struct Note {
    pub kind: &'static str,
    pub text: String,
    pub stop: bool,
    pub loss: Option<&'static str>,
    pub events: Vec<i32>,
}

fn note(text: String) -> Note {
    Note { kind: "note", text, ..Default::default() }
}

/// A note that says a loss: see [`Note`].
fn lost(loss: &'static str, events: Vec<i32>, text: String) -> Note {
    Note { kind: "note", text, loss: Some(loss), events, ..Default::default() }
}

/// A note as the answer carries it: the loss only on the ones that say one.
fn note_json(n: &Note) -> Value {
    let mut out = json!({"kind": n.kind, "text": n.text, "stop": n.stop});
    if let Some(loss) = n.loss {
        out["loss"] = json!(loss);
        out["events"] = json!(n.events);
    }
    out
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

fn layered(
    game: &Game,
    id: i32,
    window_colors: usize,
    panorama: Option<crate::request::PanoramaBudget>,
    baked: &BTreeMap<usize, (usize, i32)>,
    decor: &[Decoration],
    fuse_tiles: Option<usize>,
) -> Result<Layered> {
    let mut cells: Vec<(usize, i16)> = baked.values().map(|&(c, t)| (c, t as i16)).collect();
    cells.sort();
    let request = LayersRequest { map: id, baked: cells, window_colors, panorama, fuse_tiles, decor: decor.to_vec() };
    let drawn = draw(game, &request)?;
    let converted = stage_layers::convert(&drawn, &request)?;
    Ok(Layered { drawn, converted })
}

/// Whether baking left everybody else's colours where they were: the layer
/// above identical, the background with the same budget and merging no
/// more. The background's palette having new colours is not a change.
///
/// With `decor` the background may merge colours too, but only as many of
/// the ground's as [`GROUND_LOST_MAX`] pixels: the decoration brings
/// colours —a translucent water blended over every ground it stands on is
/// a hundred of them—, the palette has what it has, and Adeleine merges the
/// least visible. A ground that had merged colours already is not touched.
fn same_split(without: &Converted, with: &Converted, decor: bool) -> bool {
    let (a, b) = (&without.above, &with.above);
    let picture = |c: &Converted| c.pictures.iter().find(|p| p.name == "above").map(|p| p.picture.pixels.clone());
    // And the panorama's way: an event baked above the hero takes a map out
    // of mode 3, and flattened it would be drawn under him.
    without.way == with.way
        && a.tiles == b.tiles
        && a.cgram == b.cgram
        && a.tilemap == b.tilemap
        && a.first == b.first
        && a.merges.len() == b.merges.len()
        && picture(without) == picture(with)
        && without.background.budget == with.background.budget
        && if decor {
            // The ground's colours, as 5-bit channels, are all still there.
            let ground: std::collections::HashSet<[u8; 3]> = without
                .background
                .cgram
                .iter()
                .map(|w| [(w & 31) as u8, (w >> 5 & 31) as u8, (w >> 10 & 31) as u8])
                .collect();
            without.background.merges.is_empty()
                && with.background.merges.iter().filter(|m| ground.contains(&m.victim)).map(|m| m.pixels).sum::<u64>()
                    <= GROUND_LOST_MAX
        } else {
            without.background.merges.len() == with.background.merges.len()
        }
}

/// The most pixels of the ground's own colours that painting decoration into
/// the background may merge into others, and still go: four RM2k cells, the
/// same "little" as [`crate::layers::ABOVE_LOST_MAX`]. Measured on Vampires
/// Dawn's map 95 on 2026-10-06: the river, opaque, costs 204 pixels of its
/// ground; blended against its cells, 1557, so it does not go blended.
pub const GROUND_LOST_MAX: u64 = 4 * 16 * 16;

/// The events baked into the map: by event, its cell and its tile id.
type Baked = BTreeMap<usize, (usize, i32)>;

/// Bakes `baked` unless it moves the split: the layers and what was baked.
fn bake_unless_split_moves(
    game: &Game,
    id: i32,
    window_colors: usize,
    panorama: Option<crate::request::PanoramaBudget>,
    without: Layered,
    baked: Baked,
    decor: &[Decoration],
    fuse_tiles: Option<usize>,
    notes: &mut Vec<Note>,
) -> Result<(Layered, Baked)> {
    let with = layered(game, id, window_colors, panorama.clone(), &baked, decor, fuse_tiles)?;
    if same_split(&without.converted, &with.converted, false) {
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
    /// Each one's palette, for a page that gives an event that walks
    /// another graphic: see `page_graphic` in the runtime.
    pub animated_palettes: Vec<usize>,
    pub banks: Vec<(Key, Vec<u8>)>,
    /// Each graphic of command 34: its entry in the pose table or $FF, its
    /// palette, and the colours the console uploads into it when the hero
    /// takes it —for one in a leaders' palette, empty otherwise—.
    pub route_gfx: Vec<(usize, usize, Vec<u16>)>,
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
    /// How many can be on screen at once by where they start: see
    /// `sprites::cache::peak`.
    pub peak: usize,
}

/// How many events can wait for a slot of the cache, by where they start:
/// what `events-wait-for-a-slot` warns about. None without a cache.
fn waiting(done: &Whole) -> usize {
    done.objects
        .as_ref()
        .and_then(|o| o.cache.as_ref())
        .map_or(0, |c| c.peak.saturating_sub(c.slots.len()))
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
    /// The decorative events painted into the background, by index: they
    /// are no longer events, so the caller leaves them out of its page
    /// table. See [`crate::decor`].
    pub decorative: Vec<usize>,
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
    /// The stretch of the panorama the map shows, if it shows one.
    pub panorama: Option<stage_layers::Panorama>,
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
    let plain = convert_with(game, request, Mode::Plain, None)?;
    if request.layouts.is_empty() || fits(&plain, &layouts_for(&plain.layers.converted, request)) {
        return Ok(plain);
    }
    let looks = plain.moves.looks;
    // A map that fits no layout **with its pictures** is converted again
    // without them, before anything else: the pictures are what came last,
    // and they are the one thing whose absence the map survives —their
    // commands are accepted without being done—. Anything but fewer still
    // events animating, which is only looks.
    if let Some(asked) = &request.picture {
        if let Some(done) = fewer_still_animations(game, request, looks)? {
            return Ok(done);
        }
        let without = MapRequest {
            picture: None,
            ..request.clone()
        };
        let mut done = convert(game, &without)?;
        done.notes.push(lost("pictures-not-drawn", vec![], format!(
            "  map {}: WARNING, the pictures {} aren't drawn here: with their {} tiles the map \
             fits no VRAM layout",
            request.map,
            quoted(&asked.name),
            asked.image.tiles
        )));
        return Ok(done);
    }
    let shared = convert_with(game, request, Mode::Share, None)?;
    let shares = shared.objects.as_ref().is_some_and(|o| o.shared.is_some());
    if shares && fits(&shared, &layouts_for(&shared.layers.converted, request)) {
        return Ok(shared);
    }
    // And a map that does not fit even so gets a cache of slots —see
    // `sprites::cache`—, if one fits.
    let cached = convert_with(game, request, Mode::Cache, None)?;
    if cached.objects.as_ref().is_some_and(|o| o.cache.is_some()) && fits(&cached, &layouts_for(&cached.layers.converted, request)) {
        // A cache where events can wait for a slot loses more than a torch
        // that stands still: in a cache each one that animates wants a slot
        // of its own while in view. Fewer of them first, and if events wait
        // even with none, none if that is fewer waiting. Vampires Dawn's
        // 236 and 240 went from no wait to waiting when they animated.
        if looks == 0 || waiting(&cached) == 0 {
            return Ok(cached);
        }
        if let Some(done) = fewer_still_animations(game, request, looks)? {
            return Ok(done);
        }
        let none = convert_with(game, request, Mode::Cache, Some(0))?;
        let fits_none = none.objects.as_ref().is_some_and(|o| o.cache.is_some())
            && fits(&none, &layouts_for(&none.layers.converted, request));
        return Ok(if fits_none && waiting(&none) < waiting(&cached) { none } else { cached });
    }
    // Then fewer still events animating, before anything that loses more
    // than looks: see `fewer_still_animations`.
    if let Some(done) = fewer_still_animations(game, request, looks)? {
        return Ok(done);
    }
    // Last, the battle animation's box, which is 64 tiles of sprites and,
    // unlike the poses, has no way of taking less: a map that fits nothing
    // with it loses the animations —the ROM draws none where the box is
    // not— and not the conversion. After sharing slots and the cache, which
    // keep it: the animations are lost only if nothing else fits.
    if request.battle_animation {
        let without = MapRequest {
            battle_animation: false,
            ..request.clone()
        };
        let mut done = convert(game, &without)?;
        if fits(&done, &layouts_for(&done.layers.converted, &without)) {
            done.notes.push(lost("battle-animations-not-drawn", vec![], format!(
                "  map {}: WARNING, battle animations aren't drawn here: their box's {} tiles \
                 don't fit in the sprite bank",
                request.map,
                crate::sprites::extras::ANIMATION_TILES
            )));
            return Ok(done);
        }
    }
    let worst = if shares { shared } else { plain };
    // The very last: the background has more distinct tiles than any layout
    // holds, and the cells most alike are fused until it does. After all the
    // rest, because every one of them changes less of what is seen. Only
    // where a layout would hold the map's sprites and upper tiles: fusing
    // does nothing for a map that is over on those.
    //
    // Those of the conversion with a cache too, which are the fewest: with
    // walkers enough, the slots of the other two hold no layout and only
    // the cache fits, once the background is fused. Vampires Dawn's 163
    // is that since its walkers by a movement type walk, 2026-10-14.
    if request.fuse_tiles.is_none() {
        if let Some(room) = fusable(&worst, request).or_else(|| fusable(&cached, request)) {
            let mut cap = room;
            for _ in 0..FUSE_TRIES {
                let asked = MapRequest {
                    fuse_tiles: Some(cap),
                    ..request.clone()
                };
                let done = convert(game, &asked)?;
                if fits(&done, &layouts_for(&done.layers.converted, request)) {
                    return Ok(done);
                }
                // The count the fusion aims at is not the console's to the
                // tile —the animated families' come after it, and Voodoo
                // keeps a blank one—: it asks for as many fewer as it was
                // over by.
                let spent = done.layers.converted.background.tiles.len() / 64;
                if spent <= room || cap <= spent - room {
                    break;
                }
                cap -= spent - room;
            }
        }
    }
    Ok(worst)
}

/// How many times the fusion asks for fewer tiles before giving up.
const FUSE_TRIES: usize = 4;

/// The map with the most looks of its still events animating that fits a
/// layout the way `convert` would have fitted it with all of them —plain,
/// or sharing slots or with a cache nobody waits for when it has no
/// pictures—, or `None` if
/// it does not fit that way even with none: then what goes is something
/// else, and the animations are kept as long as they can be.
///
/// A still event that animates costs a slot —see `moves`—, and it is the
/// cheapest thing to lose: it only changes how something looks, where the
/// pictures, the battle animations or the fused ground lose what is shown.
/// So it goes before them, and not as a fixed number per map: until
/// 2026-10-15 it was four events, all or none, and The Book of Three's
/// opening hall, whose six torches take four slots, animated none.
///
/// It searches by halves, as if each look more never made the map fit
/// better. It is not exactly so —a look's three poses can move the
/// palette split—, and the cost of being wrong is animating one look
/// fewer than could: not worth a conversion per look on maps with dozens.
fn fewer_still_animations(game: &Game, request: &MapRequest, looks: usize) -> Result<Option<Whole>> {
    if looks == 0 {
        return Ok(None);
    }
    let fitting = |k: usize| -> Result<Option<Whole>> {
        let plain = convert_with(game, request, Mode::Plain, Some(k))?;
        if fits(&plain, &layouts_for(&plain.layers.converted, request)) {
            return Ok(Some(plain));
        }
        if request.picture.is_some() {
            return Ok(None);
        }
        let shared = convert_with(game, request, Mode::Share, Some(k))?;
        if shared.objects.as_ref().is_some_and(|o| o.shared.is_some()) && fits(&shared, &layouts_for(&shared.layers.converted, request)) {
            return Ok(Some(shared));
        }
        let cached = convert_with(game, request, Mode::Cache, Some(k))?;
        // A cache only if nobody waits for a slot: see `convert`.
        if cached.objects.as_ref().is_some_and(|o| o.cache.is_some())
            && waiting(&cached) == 0
            && fits(&cached, &layouts_for(&cached.layers.converted, request))
        {
            return Ok(Some(cached));
        }
        Ok(None)
    };
    let Some(mut best) = fitting(0)? else {
        return Ok(None);
    };
    // `low` fits and `high` —all of them, which `convert` already tried— does not.
    let (mut low, mut high) = (0, looks);
    while high - low > 1 {
        let middle = (low + high) / 2;
        match fitting(middle)? {
            Some(done) => {
                low = middle;
                best = done;
            }
            None => high = middle,
        }
    }
    Ok(Some(best))
}

/// The most background tiles a layout that holds the map's sprites and
/// upper tiles gives it, if the background is what it is over on.
fn fusable(done: &Whole, request: &MapRequest) -> Option<usize> {
    let objects = done.objects.as_ref()?;
    let converted = &done.layers.converted;
    let (sprites, above) = (objects.tiles.len() / 32, converted.above.tiles.len() / 32);
    layouts_for(converted, request)
        .into_iter()
        .filter(|&(_, s, a)| sprites <= s && above <= a)
        .map(|(b, _, _)| b)
        .max()
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

/// The layouts a converted map can get: a map that shows its panorama
/// gets one of the panorama's for its mode that hold its panorama's tiles;
/// any other, the request's.
fn layouts_for(converted: &Converted, request: &MapRequest) -> Vec<(usize, usize, usize)> {
    match (&converted.panorama, &request.panorama) {
        (Some(p), Some(budget)) => {
            let bytes = if p.mode.number() == 1 { 16 } else { 32 };
            budget
                .of_mode(p.mode.number())
                .filter(|l| p.tiles.len() / bytes <= l.panorama)
                .map(|l| (l.background, l.sprites, l.above))
                .collect()
        }
        _ => request.layouts.clone(),
    }
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

/// Leaves [`NPC_MAX`] drawn events and returns the indices of the ones that
/// lost their row, in order. Their event stays —its pages run, it blocks on
/// the hero's layer and it triggers, which the console reads from the page
/// tables and not from the row—, like one whose page draws nothing; what is
/// lost is seeing it, and the passage bits a tile it is drawn with imposes.
///
/// The first to go are the ones whose loss is only that: no page has a
/// command or a way of moving, nobody names them —`decor::named`—, nobody
/// walks them and they impose no passage. Then the rest. Within each, the
/// highest index first: a rule anyone can redo by reading the map, and RM2k
/// numbers events in the order they were placed, so the last ones placed go.
fn over_the_table(npcs: &mut Vec<Npc>, events: &[Event], named: &BTreeSet<i32>, also_walk: &BTreeSet<usize>) -> Vec<usize> {
    let does_something = |n: &Npc| {
        let event = &events[n.event];
        n.tile_pass.is_some()
            || named.contains(&event.id)
            || also_walk.contains(&n.event)
            || event.pages.iter().any(|p| !p.commands.is_empty() || p.move_type != 0 || p.own_route)
    };
    let mut order: Vec<(bool, usize)> = npcs.iter().map(|n| (does_something(n), n.event)).collect();
    order.sort_by_key(|&(does, event)| (does, std::cmp::Reverse(event)));
    let mut out: Vec<usize> = order.iter().take(npcs.len() - NPC_MAX).map(|&(_, e)| e).collect();
    out.sort();
    npcs.retain(|n| out.binary_search(&n.event).is_err());
    out
}

/// The map converted in `mode`, animating the first `looks` looks of its
/// still events that animate —all of them with `None`—: see [`Animate`].
fn convert_with(game: &Game, request: &MapRequest, mode: Mode, looks: Option<usize>) -> Result<Whole> {
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
    let wanted_decor = if request.decorative {
        let common = game.common_commands()?;
        let named = decor::named(&events, &common, &request.test_commands);
        decor::select(
            &mut drawer,
            &events,
            &decor::Wants { named: &named, also_walk: &request.also_walk, baked: &baked },
        )?
    } else {
        Vec::new()
    };
    let panorama = request.panorama.clone().map(|mut b| {
        b.extra = crate::substitutions::unseen(&lower, &upper, &request.substitutions);
        b
    });
    let without = layered(game, id, request.window_colors, panorama.clone(), &BTreeMap::new(), &[], request.fuse_tiles)?;
    // The tiles first, as they always were. Then the decoration, all of it
    // if the split holds, and if not group by group —every CharSet is
    // one—, the most numerous first, keeping what fits: each CharSet brings
    // its own colours into the background's palette, and what costs the
    // ground a colour is not worth an object.
    let mut layers = if baked.is_empty() {
        without
    } else {
        let (layers, kept) = bake_unless_split_moves(game, id, request.window_colors, panorama.clone(), without, baked, &[], request.fuse_tiles, &mut notes)?;
        baked = kept;
        layers
    };
    let mut kept_decor: Vec<Decoration> = Vec::new();
    if !wanted_decor.is_empty() {
        let reference = layered(game, id, request.window_colors, panorama.clone(), &BTreeMap::new(), &[], request.fuse_tiles)?;
        let attempt = |decor: &[Decoration], baked: &Baked| -> Result<Option<Layered>> {
            let with = layered(game, id, request.window_colors, panorama.clone(), baked, decor, request.fuse_tiles)?;
            Ok(same_split(&reference.converted, &with.converted, true).then_some(with))
        };
        // Translucent ones blended first, and if that does not fit, dithered
        // as the sprites would be: the colours of the ground and the water
        // and none between.
        let dithered: Vec<Decoration> = wanted_decor.iter().map(Decoration::dithered).collect();
        let stages: Vec<&Vec<Decoration>> = if dithered.iter().zip(&wanted_decor).any(|(a, b)| a.translucent != b.translucent) {
            vec![&wanted_decor, &dithered]
        } else {
            vec![&wanted_decor]
        };
        let mut done = false;
        for (k, stage) in stages.iter().enumerate() {
            if let Some(with) = attempt(stage, &baked)? {
                if k > 0 {
                    notes.push(lost("translucent-dithered", vec![], format!(
                        "  map {id}: the translucent decorative events are dithered: blended against their cells they cost the ground too many colours"
                    )));
                }
                kept_decor = (*stage).clone();
                layers = with;
                done = true;
                break;
            }
        }
        let wanted_decor = stages[stages.len() - 1].clone();
        if !done {
            let mut groups: BTreeMap<&str, Vec<&Decoration>> = BTreeMap::new();
            for d in &wanted_decor {
                groups.entry(d.sheet.as_str()).or_default().push(d);
            }
            let mut order: Vec<(&str, Vec<&Decoration>)> = groups.into_iter().collect();
            order.sort_by_key(|(name, ds)| (std::cmp::Reverse(ds.len()), *name));
            for (_, group) in order {
                let mut trial = kept_decor.clone();
                trial.extend(group.into_iter().cloned());
                trial.sort_by_key(|d| (d.layer, d.y, d.x, d.id));
                if let Some(with) = attempt(&trial, &baked)? {
                    kept_decor = trial;
                    layers = with;
                }
            }
        }
        if kept_decor.len() < wanted_decor.len() {
            notes.push(note(format!(
                "  map {id}: {} of {} decorative event(s) moved the background's CGRAM split, so they are drawn",
                wanted_decor.len() - kept_decor.len(),
                wanted_decor.len()
            )));
        }
    }
    // They are not events any more: no row, no slot, no sprite tiles, and
    // no walking or turning of their own for the page scan to count. The
    // cells still count as taken for where the hero starts.
    let used: HashSet<(i32, i32)> = npcs0.iter().map(|n| (n.x, n.y)).collect();
    let gone: BTreeSet<usize> = kept_decor.iter().map(|d| d.event).collect();
    npcs0.retain(|n| !gone.contains(&n.event));
    // More than the console's table holds: some lose their row. Before
    // anything counts poses, slots or palettes, so what is not drawn costs
    // nothing in the sprite bank either.
    if npcs0.len() > NPC_MAX {
        let named = decor::named(&events, &game.common_commands()?, &request.test_commands);
        let out = over_the_table(&mut npcs0, &events, &named, &request.also_walk);
        let ids: Vec<i32> = out.iter().map(|e| events[*e].id).collect();
        notes.push(lost("events-not-drawn", ids, format!(
            "  map {id}: WARNING, {} drawn events and the console's table holds {NPC_MAX}: events {} \
             aren't drawn, and still run, block and trigger",
            npcs0.len() + out.len(),
            out.iter().map(|e| events[*e].id.to_string()).collect::<Vec<_>>().join(", ")
        )));
    }
    let pages: Vec<ScannedPage> = request.pages.iter().filter(|p| !gone.contains(&p.event)).cloned().collect();

    // The characters.
    let actors = game.actors()?;
    let leader = |actor: &i32| -> Result<Key> {
        actors
            .get(actor)
            .cloned()
            .ok_or_else(|| Bad::answer(format!("actor {actor} is not in the database")))
    };
    let leaders: Vec<Key> = request.leaders.iter().map(leader).collect::<Result<_>>()?;
    let animate = Animate { looks, share: mode != Mode::Cache };
    let who = moves(&pages, &events, &npcs0, &chipset_name, &request.also_walk, animate);
    if !who.still_not_animated.is_empty() {
        let ids: Vec<i32> = who.still_not_animated.iter().map(|&e| events[e].id).collect();
        notes.push(lost("still-animation-dropped", ids, format!(
            "  map {id}: {} still events animate in RM2k and stand still here: their slots don't fit in \
             the sprite bank ({} of {} looks animate)",
            who.still_not_animated.len(),
            looks.unwrap_or(who.looks).min(who.looks),
            who.looks
        )));
    }
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
        hero_graphics: &request.hero_graphics,
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
        notes.push(lost("palette-lent", vec![], format!(
            "  map {id}: {} graphic(s) without a palette of their own, drawn with someone else's: {}",
            split.lent.len(),
            names.join(", ")
        )));
    }
    if !split.shared_leaders.is_empty() {
        let mut names: Vec<String> = split.shared_leaders.iter().map(|k| format!("{}:{}", k.0, k.1)).collect();
        names.sort();
        notes.push(note(format!(
            "  map {id}: {} leader candidate(s) that are also events here share a palette with other \
             characters: {}",
            split.shared_leaders.len(),
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
        layers = layered(game, id, request.window_colors, panorama.clone(), &BTreeMap::new(), &kept_decor, request.fuse_tiles)?;
        if !baked.is_empty() {
            let (again, kept) = bake_unless_split_moves(game, id, request.window_colors, panorama.clone(), layers, baked, &kept_decor, request.fuse_tiles, &mut notes)?;
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

    if let (fused @ 1.., Some(cap)) = (layers.drawn.fused, request.fuse_tiles) {
        notes.push(lost("background-tiles-fused", vec![], format!(
            "  map {id}: WARNING, {fused} distinct background tiles were fused into the ones most like \
             them to fit the {cap} the layouts leave: the ground is drawn worse, not walked differently"
        )));
    }
    let (passability, mut blocks) = stage_layers::blocks(&layers.drawn, &mut layers.converted)?;
    let substituted = substitute(
        id,
        &mut blocks,
        &flags,
        &chipset,
        &request.substitutions,
        &request.common_substitutions,
        layers.converted.way == Some(crate::background::panorama::Way::Flattened),
    )?;
    let (start_map, start_x, start_y) = game.start()?;
    let start = if id == start_map {
        (start_x, start_y)
    } else {
        hero_start(&passability, raw.width as usize, raw.height as usize, &used)
    };
    let mut done = Whole {
        layers: Final {
            panorama: layers.drawn.panorama.clone(),
            converted: layers.converted,
            passability,
            blocks,
        },
        baked: baked.clone(),
        decorative: gone.iter().copied().collect(),
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
        done.notes.push(Note {
            kind: "discard",
            text,
            stop,
            loss: Some("event-not-drawn"),
            events: vec![events[*event].id],
        });
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
            done.notes.push(Note { kind: "stop", text: format!("can't find CharSet {}", quoted(&key.0)), stop: true, ..Default::default() });
            return Ok(done);
        };
        if !sprite_colors(image, key.1, None).is_empty() {
            with_graphic.push(*actor);
        }
    }
    // None when the game starts with the party empty and nobody in these
    // maps joins it: RM2k draws no hero then, and there are no leader poses.
    let first = leaders.first().cloned();
    let mut animated: Vec<Key> = Vec::new();
    for actor in &with_graphic {
        let key = leader(actor)?;
        if !animated.contains(&key) {
            animated.push(key);
        }
    }
    animated.sort_by_key(|k| Some(k) != first.as_ref());
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
                ..Default::default()
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
            // The ones animating in another one's slot are not still: they
            // take no turns.
            Some(placed) => {
                let mut taken = who.movable.clone();
                taken.extend(who.follows.keys());
                plan_sharing(&npcs, &taken, &baked, &placed)
            }
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
                // Its row walks in one slot, with its own pose bank; each
                // page's graphic reaches that slot from its own bank at run
                // time —`walker_graphic` in the runtime—, and whether the
                // row is visible follows the page too.
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
        } else if who.follows.contains_key(&npc.event) {
            // It is drawn with the slot of the one it animates with.
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
            done.notes.push(Note { kind: "stop", text: format!("can't find CharSet {}", quoted(charset)), stop: true, ..Default::default() });
            return Ok(done);
        }
    }

    let bank = match build_characters(&sheets, &characters, &slots, &split) {
        Ok(b) => b,
        Err(b) => {
            done.notes.push(Note { kind: "stop", text: b.0, stop: true, ..Default::default() });
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
            ..Default::default()
        });
        return Ok(done);
    }
    let banks = pose_bank(&sheets, &animated, &bank.colors).map_err(|b| Bad::answer(b.0))?;
    let animated_index: HashMap<Key, usize> = animated.iter().enumerate().map(|(k, p)| (p.clone(), k)).collect();
    let animated_palettes: Vec<usize> = animated.iter().map(|k| split.palette_of.get(k).unwrap_or(0)).collect();
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
                .is_ok_and(|e| fits_in(background, above, e.tiles.len() / 32, &layouts_for(converted, request)))
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
                done.notes.push(lost("events-wait-for-a-slot", vec![], format!(
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
        let palette = bank.palette_of.get(key).unwrap_or(0);
        // One that shares a palette of the map brings that palette's colours,
        // as they end: the console uploads the leader's into its row, and
        // its own would repaint whoever shares it. See `shared_leaders`.
        let own = if split.shared_leaders.contains(key) {
            palettes[palette].clone()
        } else {
            character_palette(image, key.1, None, None).map_err(|b| Bad::answer(b.0))?.0
        };
        actor_rows.push((
            *actor,
            palette,
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
                peak: asked.peak,
            })
        }
        _ => None,
    };
    done.baked = baked;
    done.npcs = npcs;
    // On the palettes as they end: the rain may still have grown the
    // timer's, and a colour's first entry is where the glyphs have it.
    let timer_mask = timer_at.map_or(0, |(_, palette)| timer_mask(&timer, &palettes[palette]));
    // A graphic in a leaders' palette brings the colours its pose bank was
    // drawn with: the console uploads them there when the hero takes it, as
    // it does with a leader's. Its own, for one that shares the slot like a
    // leader; the palette's, for one that went into it whole.
    let mut route_gfx_colored = Vec::with_capacity(route_gfx.len());
    for (pair, (k, palette)) in request.route_graphics.iter().zip(route_gfx) {
        let mut words = Vec::new();
        if k != 0xFF && split.leader_owned.contains(&palette) && !split.lent.contains(pair) {
            let colors = if split.own.contains(pair) {
                let image = crate::sprites::character::sheet(&sheets, &pair.0).map_err(|b| Bad::answer(b.0))?;
                character_palette(image, pair.1, None, None).map_err(|b| Bad::answer(b.0))?.0
            } else {
                palettes[palette].clone()
            };
            words = colors.iter().map(|&[r, g, b]| voodoo::cgram_word((r, g, b))).collect();
        }
        route_gfx_colored.push((k, palette, words));
    }
    let route_gfx = route_gfx_colored;
    done.objects = Some(Objects {
        tiles,
        palettes,
        place,
        actors: actor_rows,
        timer: timer_at,
        timer_mask,
        animated,
        animated_palettes,
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
/// conversion: that is the error. Since 2026-10-14 they only do not fit
/// when every palette is a leader's: otherwise they are lent one.
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
            Ok(at) => {
                let missing: Vec<Color> =
                    timer_colors(glyphs).into_iter().filter(|c| !palettes[at.1].contains(c)).collect();
                if !missing.is_empty() {
                    let drawn: Vec<String> = missing
                        .iter()
                        .map(|c| format!("{c:?} as {:?}", nearest(&palettes[at.1], *c)))
                        .collect();
                    notes.push(lost("timer-colors-lent", vec![], format!(
                        "  map {id}: WARNING, the timer has no palette with room and is lent {}, \
                         drawn with its nearest colors: {}",
                        at.1,
                        drawn.join(", ")
                    )));
                }
                timer_at = Some(at);
            }
            Err(b) => return Err(Note { kind: "stop", text: b.0, stop: true, ..Default::default() }),
        }
    }
    let mut rain = (0, 0);
    if request.rain {
        match rain_drops(&mut tiles, &mut palettes, leader_owned, timer_at, palette_cap) {
            Some(at) => rain = at,
            None => notes.push(lost("rain-not-drawn", vec![], format!(
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
            None => notes.push(lost("pictures-not-drawn", vec![], format!(
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
            None => notes.push(lost("battle-animations-not-drawn", vec![], format!(
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
    stage_layers::write(out, &layers.converted, layers.panorama.as_ref(), &layers.passability, &layers.blocks)?;
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
                "animated_palettes": o.animated_palettes,
                "banks": banks,
                "route_gfx": o
                    .route_gfx
                    .iter()
                    .map(|(k, p, c)| if c.is_empty() { json!([k, p]) } else { json!([k, p, c]) })
                    .collect::<Vec<_>>(),
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
        "decorative": done.decorative,
        "baked": done.baked.iter().map(|(e, (c, t))| json!([e, c, t])).collect::<Vec<_>>(),
        "notes": done.notes.iter().map(note_json).collect::<Vec<_>>(),
        "npcs": done.npcs.iter().map(npc_json).collect::<Vec<_>>(),
        "palette_cap": done.palette_cap,
        "start": [done.start.0, done.start.1],
        "sprite": objects,
        "movable": done.moves.movable,
        "animates_still": done.moves.animates_still,
        "animates_with": done.moves.follows.iter().map(|(e, l)| json!([e, l])).collect::<Vec<_>>(),
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
