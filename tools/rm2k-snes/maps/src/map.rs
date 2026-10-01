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
use adeleine::Color;
use rm2k_render::picture;
use rm2k_rules::chipset::passability_table;
use rm2k_rules::passability::ALL;
use rm2k_snes_map_background::blocks::Blocks;
use rm2k_snes_map_background::Converted;
use rm2k_snes_map_sprites::bank::{build_characters, pose_bank, Slot, SlotPose};
use rm2k_snes_map_sprites::character::{
    character_palette, sprite_colors, Key, INITIAL_POSE, OBJ_PALETTES,
};
use rm2k_snes_map_sprites::extras::{
    first_place, map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, timer_mask,
    Image,
};
use rm2k_snes_map_sprites::npc::{map_poses, pin_walkers, Npc};
use rm2k_snes_map_sprites::split::{drawable_npcs, Ask, TILE_PREFIX};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};

/// A `ShowPicture` picture this map owns, already decided and cut.
#[derive(Clone, Debug, Default)]
pub struct PictureAsked {
    pub name: String,
    pub objects: usize,
    pub image: Image,
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

fn layered(game: &Game, id: i32, baked: &BTreeMap<usize, (usize, i32)>) -> Result<Layered> {
    let mut cells: Vec<(usize, i16)> = baked.values().map(|&(c, t)| (c, t as i16)).collect();
    cells.sort();
    let drawn = draw(game, &LayersRequest { map: id, baked: cells })?;
    let converted = rm2k_snes_map_background::convert(&drawn.layers)?;
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
    without: Layered,
    baked: Baked,
    notes: &mut Vec<Note>,
) -> Result<(Layered, Baked)> {
    let with = layered(game, id, &baked)?;
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
}

/// The final layers and their blocks.
pub struct Final {
    pub converted: Converted,
    pub passability: Vec<u8>,
    pub blocks: Blocks,
}

/// The map `request.map`, whole.
pub fn convert(game: &Game, request: &MapRequest) -> Result<Whole> {
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
    let without = layered(game, id, &BTreeMap::new())?;
    let mut layers = if baked.is_empty() {
        without
    } else {
        let (layers, kept) = bake_unless_split_moves(game, id, without, baked, &mut notes)?;
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
        layers = layered(game, id, &BTreeMap::new())?;
        if !baked.is_empty() {
            let (again, kept) = bake_unless_split_moves(game, id, layers, baked, &mut notes)?;
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

    let (passability, blocks) = stage_layers::blocks(&layers.drawn, &layers.converted)?;
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

    // The slots of the VRAM bank, one pose each: the hero in block 0, each
    // event that walks with its own, and the still ones shared by
    // (CharSet, index, pose).
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
            slots.push(SlotPose {
                slot: Slot::Event(npc.event),
                charset: npc.charset.clone(),
                index: npc.index,
                pose: npc.pose,
            });
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

    let mut tiles = bank.tiles;
    let mut palettes = bank.palettes;
    let mut timer_at = None;
    if let Some(glyphs) = &glyphs {
        match timer_digits(glyphs, &mut tiles, &mut palettes, &split.leader_owned, palette_cap) {
            Ok(at) => timer_at = Some(at),
            Err(b) => {
                done.notes.push(Note { kind: "stop", text: b.0, stop: true });
                return Ok(done);
            }
        }
    }
    let mut rain = (0, 0);
    if request.rain {
        match rain_drops(&mut tiles, &mut palettes, &split.leader_owned, timer_at, palette_cap) {
            Some(at) => rain = at,
            None => done.notes.push(note(format!(
                "  map {id}: WARNING, the raindrops don't fit in the sprite palettes and it doesn't rain here"
            ))),
        }
    }
    let mut image = (0, 0);
    if let Some(asked) = &request.picture {
        let previous = if rain.0 != 0 { rain.0 } else { timer_at.map_or(0, |t| t.0) };
        match picture_of_image(&asked.image, &mut tiles, &palettes, previous) {
            Some(at) => {
                image = at;
                done.notes.push(note(format!(
                    "  map {id}: the picture {}, {} objects in {} tiles from {}, palette {}",
                    quoted(&asked.name),
                    asked.objects,
                    asked.image.tiles,
                    at.0,
                    at.1
                )));
            }
            None => {
                done.notes.push(Note {
                    kind: "stop",
                    text: format!(
                        "map {id}: the picture {} doesn't fit: the map already uses the {OBJ_PALETTES} \
                         sprite palettes and the fade needs a whole one. See `cartel_de_imagen`.",
                        quoted(&asked.name)
                    ),
                    stop: true,
                });
                return Ok(done);
            }
        }
    }
    let mut animation = None;
    if request.battle_animation {
        let mut trial = tiles.clone();
        match map_animation(&mut trial, &palettes, usize::from(image.0 != 0)) {
            None => done.notes.push(note(format!(
                "  map {id}: WARNING, battle animations aren't drawn here: the map already uses the \
                 {OBJ_PALETTES} sprite palettes and the box needs a whole one"
            ))),
            Some((base, pal)) => {
                animation = Some((trial.len() / 32, base, pal));
                tiles = trial;
            }
        }
    }
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
        let image = rm2k_snes_map_sprites::character::sheet(&sheets, &key.0).map_err(|b| Bad::answer(b.0))?;
        let (own, _, _) = character_palette(image, key.1, None, None).map_err(|b| Bad::answer(b.0))?;
        actor_rows.push((
            *actor,
            bank.palette_of.get(key).unwrap_or(0),
            Some(animated_index[key]),
            own.iter().map(|&[r, g, b]| voodoo::cgram_word((r, g, b))).collect(),
        ));
    }
    let turn_block = bank.place.iter().find(|(s, ..)| *s == Slot::Turn).map(|(_, b, _)| *b);
    done.baked = baked;
    done.npcs = npcs;
    // On the palettes as they end: the rain may still have grown the
    // timer's, and a colour's first entry is where the glyphs have it.
    let timer_mask = timer_at.map_or(0, |(_, palette)| timer_mask(&timer, &palettes[palette]));
    done.objects = Some(Objects {
        tiles,
        palettes,
        place: bank.place,
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
    });
    Ok(done)
}

fn drawer_missing(sheets: &rm2k_snes_map_sprites::character::Sheets, name: &str) -> bool {
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
        "turning": done.moves.turning.iter().map(|(e, pairs)| json!([e, pairs.iter().map(key_json).collect::<Vec<_>>()])).collect::<Vec<_>>(),
    });
    file(ANSWER_FILE, answer.to_string().as_bytes())
}
