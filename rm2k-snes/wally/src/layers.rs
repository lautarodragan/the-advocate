//! A map's two background layers: drawn by `rm2k-render`, converted by
//! [`crate::background`], and written for the caller; and the map as
//! blocks of 16x16, which are made of what the two layers were converted to.

use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::request::LayersRequest;
use ditto::schema::Chipset;
use rm2k_render::{picture, Atlas, Layers, Map};
use rm2k_rules::chipset::{passability_table, terrain_of};
use crate::background::blocks::{self, Blocks};
use crate::background::panorama::{Mode, Way};
use crate::background::{Converted, Merge, Run};
use serde_json::{json, Value};
use std::path::Path;

/// The file what the caller needs to know is written to.
pub const ANSWER_FILE: &str = "layers.json";
/// The background's tiles.
pub const BACKGROUND_TILES: &str = "background.bin";
/// The layer above's tiles and its colour-memory words.
pub const ABOVE_TILES: &str = "above.bin";
pub const ABOVE_CGRAM: &str = "above-cgram.bin";
/// The panorama's tiles, if the map shows it.
pub const PANORAMA_TILES: &str = "panorama.bin";
/// The block table, and each block's passability and terrain.
pub const BLOCK_TABLE: &str = "blocks.bin";
pub const BLOCK_PASSABILITY: &str = "block-passability.bin";
pub const BLOCK_TERRAIN: &str = "block-terrain.bin";

/// The file drawing `d` of a family's run is written to.
pub fn run_file(run: &Run, d: usize) -> String {
    format!("run-{}-{d}.bin", run.family.name())
}

/// A map as it is drawn: the dump's, or the project's file, with the baked
/// cells painted into its upper layer; its ChipSet entry; and, if the
/// cartridge shows its panorama, the stretch of it the console can show.
pub struct Drawn {
    pub map: Map,
    pub chipset: Chipset,
    pub layers: Layers,
    /// How many distinct cells of the background were fused into others to
    /// fit `request.fuse_tiles`; zero if it was not asked or already fit.
    pub fused: usize,
    pub panorama: Option<Panorama>,
    /// The map with rows added below it that draw the `(lower, upper)`
    /// pairs a `TileSubstitution` will need and the map does not draw, if
    /// there are any and the map has a panorama. A flattened map draws the
    /// two layers into one, so a substitution can build no block out of
    /// halves: the blocks it needs have to be drawn, and they are drawn
    /// here, converted with the map and cut off after the blocks are made.
    pub extended: Option<(Map, Layers)>,
    /// The cells a decorative event on the hero's layer closes: the map's
    /// passability says it, since the event is not in the table any more.
    pub blocked: Vec<usize>,
    /// The map's pixels that its pictures put in front of the hero, if they
    /// are drawn into a panorama fixed to the map: see
    /// [`crate::map_pictures`].
    pub front: Option<Vec<bool>>,
}

/// The stretch of a panorama the console can show, and how it moves: what
/// the map says of it, as RM2k reads it —`Game_Map::Parallax`—.
#[derive(Clone, Debug)]
pub struct Panorama {
    pub name: String,
    /// The whole picture's size; the stretch is `picture`.
    pub size: (usize, usize),
    pub picture: picture::Picture,
    /// The whole picture: what is baked into a map that does not move.
    pub whole: picture::Picture,
    /// Whether it loops on each axis, and by how much a frame it moves on
    /// its own: RM2k's speed, 0 if it does not.
    pub looped: (bool, bool),
    pub auto: (i32, i32),
    /// Whether a `ChangePBG` of the map's own pages changes how it moves.
    pub changes: bool,
    /// Whether one of those makes it loop, on each axis.
    pub changed_loops: (bool, bool),
    /// The other pictures a `ChangePBG` of the map's own pages names, in
    /// the order they are first named, each with the stretch of it the
    /// console can show: the console carries them too if the map shows its
    /// panorama on a layer of its own, and swaps them —see `pano_image` in
    /// `runtime/pano.s`—.
    pub extras: Vec<Extra>,
    /// Whether the map has no panorama of its own and starts with none, as
    /// RM2k shows it: then `name` and `picture` are the first picture a
    /// `ChangePBG` names, and the console's first record is an empty one.
    pub none_first: bool,
    /// Why it carries none of [`Panorama::extras`], if it names some and
    /// they are left out before converting.
    pub extras_left: Option<String>,
}

/// A picture other than the map's own that a `ChangePBG` names: see
/// [`Panorama::extras`].
#[derive(Clone, Debug)]
pub struct Extra {
    pub name: String,
    pub size: (usize, usize),
    pub picture: picture::Picture,
}

/// The pictures the `ChangePBG`s of a map's own pages name, once each
/// —RM2k finds them by name, as Windows does, whatever the case— and in
/// the order they are first named, leaving out `own` and the empty name,
/// which keeps the picture there is. Not the ones after a `Teleport` to
/// another map or a `RecallToLocation` in their page: those change the
/// panorama of the map the page jumped to —The Frozen World's encounters
/// jump to its battle map and then name its backdrop—, and the compiler
/// keeps the picture on them, as `MapEvents::jumped` says.
pub fn named_panoramas(map: &ditto::schema::Map, own: Option<&str>, id: i32) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for page in map.events.iter().flat_map(|e| &e.pages) {
        let mut jumped = false;
        for c in &page.event_commands {
            match c.code.to_i32() {
                TELEPORT if c.parameters.first() != Some(&id) => jumped = true,
                RECALL_TO_LOCATION => jumped = true,
                CHANGE_PBG if !jumped && !c.string.is_empty() => {
                    if own.is_some_and(|o| o.eq_ignore_ascii_case(&c.string))
                        || out.iter().any(|n| n.eq_ignore_ascii_case(&c.string))
                    {
                        continue;
                    }
                    out.push(c.string.clone());
                }
                _ => {}
            }
        }
    }
    out
}

/// `Teleport`'s and `RecallToLocation`'s event command codes.
const TELEPORT: i32 = 10810;
const RECALL_TO_LOCATION: i32 = 10830;

/// The RM2k screen, and the console's, in pixels; and where each puts the
/// hero's cell, from the screen's corner. RM2k's is
/// `Game_Player::GetDefaultPanX`: half the screen in cells, rounded up, less
/// one. The console's is `follow_camera`'s: the cell's centre on the
/// screen's.
const RM2K_SCREEN: (usize, usize) = (320, 240);
/// `ChangePBG`'s event command code.
const CHANGE_PBG: i32 = 11720;
const RM2K_HERO: (usize, usize) = (9 * 16, 7 * 16);
const CONSOLE_SCREEN: (usize, usize) = (256, 224);
const CONSOLE_HERO: (usize, usize) = (128 - 8, 112 - 8);

/// How far into the panorama the console can look along one axis: all of
/// it if it loops, and if it does not, as far as `Game_Map::Parallax`
/// takes it with RM2k's camera, plus how far the console's camera, which
/// shows less, is from that one. That is the whole map walked a pixel at a
/// time. A `PanScreen` can take the camera further, and that is not
/// counted.
pub fn reach(map: usize, (rm2k, rm2k_hero): (usize, usize), (console, console_hero): (usize, usize), pano: usize, looped: bool) -> usize {
    if looped {
        return pano;
    }
    let camera = |h: usize, screen: usize, hero: usize| -> usize {
        h.saturating_sub(hero).min(map.saturating_sub(screen))
    };
    let tiles = map / 16;
    let per_screen = rm2k.div_ceil(16);
    let mut far = 0;
    for h in 0..map {
        let rc = camera(h, rm2k, rm2k_hero);
        let oc = camera(h, console, console_hero);
        let off = if tiles > per_screen && pano > rm2k {
            let w = (tiles - per_screen) * 16;
            w.min(pano - rm2k) * rc / w
        } else {
            0
        };
        far = far.max(off + oc - rc + console);
    }
    far.next_multiple_of(8).min(pano)
}

/// Reads the request's map and draws it.
pub fn draw(game: &Game, request: &LayersRequest) -> Result<Drawn> {
    draw_with(game, request, true)
}

/// [`draw`], and with `named` false without the pictures the map's
/// `ChangePBG`s name: the map as it was drawn before those were carried.
fn draw_with(game: &Game, request: &LayersRequest, named: bool) -> Result<Drawn> {
    let id = request.map;
    let map = game.map(id)?;
    let chipset = game.chipset(map.chipset_id)?;
    let mut upper = map.upper_layer.clone();
    for &(cell, tile) in &request.baked {
        let slot = upper.get_mut(cell).ok_or_else(|| {
            Bad::answer(format!(
                "map {id}: baked cell {cell} is past its {} cells",
                map.upper_layer.len()
            ))
        })?;
        *slot = tile;
    }
    let path = game
        .resource("ChipSet", &chipset.chipset_name)
        .ok_or_else(|| {
            Bad::answer(format!(
                "can't find the chipset of map {id}: {:?} is in none of the search directories",
                chipset.chipset_name
            ))
        })?;
    let atlas = Atlas::new(&picture::read_rm2k(&path)?);
    let size = |name: &str, v: i32| {
        usize::try_from(v).map_err(|_| Bad::answer(format!("map {id}: `{name}` is {v}")))
    };
    let drawn = Map {
        width: size("width", map.width)?,
        height: size("height", map.height)?,
        lower_layer: map.lower_layer.iter().map(|&t| t as i64).collect(),
        upper_layer: upper.iter().map(|&t| t as i64).collect(),
        passable_lower: chipset.passable_data_lower.clone(),
        passable_upper: chipset.passable_data_upper.clone(),
    };
    let own = map.parallax_flag.then(|| map.parallax_name.clone());
    // The pictures its `ChangePBG`s name, unless the caller asks for the
    // map as it was before they were carried: see [`draw_converted`].
    let named = if named { named_panoramas(&map, own.as_deref(), id) } else { Vec::new() };
    let mut panorama = match &request.panorama {
        Some(_) if own.is_some() || !named.is_empty() => {
            let (mw, mh) = (drawn.width * 16, drawn.height * 16);
            // An axis a `ChangePBG` of the map's own pages makes loop needs
            // the whole picture too, in every picture it may show. One in a
            // common event is not seen.
            let changed = map
                .events
                .iter()
                .flat_map(|e| &e.pages)
                .flat_map(|p| &p.event_commands)
                .filter(|c| c.code.to_i32() == CHANGE_PBG && c.parameters.len() >= 2)
                .fold((false, false), |(x, y), c| (x || c.parameters[0] != 0, y || c.parameters[1] != 0));
            let (lx, ly) = if own.is_some() { (map.parallax_loop_x, map.parallax_loop_y) } else { (false, false) };
            let read = |name: &str| -> Result<(picture::Picture, picture::Picture)> {
                let path = game.resource("Panorama", name).ok_or_else(|| {
                    Bad::answer(format!(
                        "can't find the panorama of map {id}: {name:?} is in none of the search directories"
                    ))
                })?;
                // Opaque: RM2k gives a panorama no colour key.
                let whole = picture::read_unkeyed(&path)?;
                let w = reach(mw, (RM2K_SCREEN.0, RM2K_HERO.0), (CONSOLE_SCREEN.0, CONSOLE_HERO.0), whole.width, lx || changed.0);
                let h = reach(mh, (RM2K_SCREEN.1, RM2K_HERO.1), (CONSOLE_SCREEN.1, CONSOLE_HERO.1), whole.height, ly || changed.1);
                Ok((whole.crop(0, 0, w, h), whole))
            };
            // A named picture the game does not have is left out: the
            // compiler keeps the one there is on its `ChangePBG`.
            let mut found = named.iter().filter_map(|n| read(n).ok().map(|(picture, whole)| (n.clone(), picture, whole)));
            let first = match &own {
                Some(name) => {
                    let (picture, whole) = read(name)?;
                    Some((name.clone(), picture, whole))
                }
                None => found.next(),
            };
            first.map(|(name, picture, whole)| Panorama {
                name,
                size: (whole.width, whole.height),
                picture,
                whole,
                changes: map.events.iter().flat_map(|e| &e.pages).flat_map(|p| &p.event_commands).any(|c| c.code.to_i32() == CHANGE_PBG),
                changed_loops: changed,
                looped: (lx, ly),
                auto: (
                    if lx && map.parallax_auto_loop_x { map.parallax_sx } else { 0 },
                    if ly && map.parallax_auto_loop_y { map.parallax_sy } else { 0 },
                ),
                extras: found.map(|(name, picture, whole)| Extra { name, size: (whole.width, whole.height), picture }).collect(),
                none_first: own.is_none(),
                extras_left: None,
            })
        }
        _ => None,
    };
    // A panorama the map's pictures are drawn into keeps them only while it
    // is the one shown: swapping it would take them away.
    if let Some(p) = panorama.as_mut().filter(|p| !p.extras.is_empty() && !p.none_first) {
        if !game.map_pictures.is_empty() && crate::map_pictures::fixed_to_map(p, (drawn.width * 16, drawn.height * 16)) {
            p.extras_left = Some("the map's pictures are drawn into its own panorama".to_string());
        }
    }
    let mut layers = if panorama.is_some() {
        drawn.render_over_panorama(&atlas)?
    } else {
        drawn.render(&atlas)?
    };
    crate::decor::compose(&mut layers, &request.decor);
    // Above everything, as RM2k draws pictures. Not into a picture a
    // `ChangePBG` names in a map without a panorama of its own: there they
    // are drawn into the map, as they were before those were carried.
    let into = panorama.as_mut().filter(|p| !p.none_first);
    let front = crate::map_pictures::compose(
        game,
        id,
        &game.map_pictures,
        (drawn.width * 16, drawn.height * 16),
        &mut layers,
        into,
    )?;
    let blocked: Vec<usize> = request
        .decor
        .iter()
        .filter(|d| d.blocks())
        .map(|d| d.y as usize * drawn.width + d.x as usize)
        .collect();
    let fused = request
        .fuse_tiles
        .map_or(0, |max| crate::background::fuse::fuse_lower(&mut layers, max));
    // The cells a `TileSubstitution` will need and the map does not draw,
    // in rows of their own below it: see `Drawn::extended`.
    let extra: &[(i32, i32)] = request.panorama.as_ref().map_or(&[], |b| &b.extra);
    let extended = if panorama.is_some() && !extra.is_empty() {
        let mut map = drawn.clone();
        let rows = extra.len().div_ceil(map.width);
        for k in 0..rows * map.width {
            let (l, u) = extra[k.min(extra.len() - 1)];
            map.lower_layer.push(i64::from(l));
            map.upper_layer.push(i64::from(u));
        }
        map.height += rows;
        let mut layers = map.render_over_panorama(&atlas)?;
        crate::decor::compose(&mut layers, &request.decor);
        Some((map, layers))
    } else {
        None
    };
    Ok(Drawn {
        map: drawn,
        chipset,
        layers,
        fused,
        panorama,
        extended,
        blocked,
        front,
    })
}

/// The two layers converted, with the panorama if the map shows it, and
/// how it shows it.
///
/// **The way is the map's and the panorama's to say**, and nobody else's:
/// the same game gives the same ways. In order —see [`Way`]—:
///
/// 1. if the layer behind the hero covers it everywhere, it is hidden;
/// 2. if it does not move against the map —a map no bigger than RM2k's
///    screen, which RM2k's camera never scrolls, and no scrolling of its
///    own—, it is baked into the background;
/// 3. if the map draws nothing above the hero, mode 3;
/// 4. if it does, flattened if that puts little on the wrong side of the
///    hero ([`ABOVE_LOST_MAX`]), and mode 1 if it puts more.
///
/// A way that does not fit —more tiles than any layout leaves— gives way
/// to the next that can: baked to the moving ones, mode 1 and flattened to
/// each other, and any of them to black, the map as it was before there
/// were panoramas. A way the request forces is that one, or the error.
pub fn convert(drawn: &Drawn, request: &LayersRequest) -> Result<Converted> {
    let mut done = convert_ways(drawn, request)?;
    // What the map's pictures put in front of the hero, by the priority of
    // the panorama's cells: only in mode 3, where it is BG2. In any other
    // way they are only drawn into the map.
    if let Some(front) = &drawn.front {
        let width = drawn.map.width * 16;
        done.in_front = Some(match (done.way, done.panorama.as_mut()) {
            (Some(Way::Mode3), Some(p)) => crate::map_pictures::raise(&mut p.tilemap, front, width),
            // Already done, with the edges exact: see `painted`.
            (Some(Way::Painted), _) => done.in_front.unwrap_or((0, 0)),
            _ => {
                let total = front.iter().filter(|&&f| f).count();
                (total, total)
            }
        });
    }
    // The pictures its `ChangePBG`s name that it does not carry, and why.
    if let Some(p) = &drawn.panorama {
        let layered = on_a_layer(&done);
        for (k, extra) in p.extras.iter().enumerate() {
            let why = match done.panorama.as_ref().and_then(|q| q.extras.get(k)) {
                Some(Ok(_)) => continue,
                Some(Err(why)) => why.clone(),
                None if layered => done.extras_left.clone().unwrap_or_default(),
                None => format!("its panorama goes {}, which has no layer of its own to swap", done.way.map_or("nowhere", Way::name)),
            };
            done.dropped.push((extra.name.clone(), why));
        }
        done.unseen = done.way == Some(Way::Hidden);
    }
    Ok(done)
}

/// Whether the map shows its panorama on a layer of its own.
fn on_a_layer(done: &Converted) -> bool {
    matches!(done.way, Some(Way::Mode3 | Way::Flattened | Way::Mode1))
}

/// [`draw`] and [`convert`]. A map without a panorama of its own whose
/// `ChangePBG`s name some gets a layer for them if a way gives it one;
/// if not, it is drawn and converted as it was before those were carried,
/// and the pictures go in [`Converted::dropped`].
pub fn draw_converted(game: &Game, request: &LayersRequest) -> Result<(Drawn, Converted)> {
    let drawn = draw(game, request)?;
    let Some(p) = drawn.panorama.as_ref().filter(|p| p.none_first) else {
        let converted = convert(&drawn, request)?;
        return Ok((drawn, converted));
    };
    let mut names = vec![p.name.clone()];
    names.extend(p.extras.iter().map(|e| e.name.clone()));
    let (why, unseen) = match convert(&drawn, request) {
        Ok(done) if on_a_layer(&done) => return Ok((drawn, done)),
        Ok(done) => (
            format!("its panorama would go {}, which has no layer of its own to swap", done.way.map_or("nowhere", Way::name)),
            done.unseen,
        ),
        Err(e) => (e.to_string(), false),
    };
    let drawn = draw_with(game, request, false)?;
    let mut converted = convert(&drawn, request)?;
    converted.dropped = names.into_iter().map(|n| (n, why.clone())).collect();
    converted.unseen = unseen;
    Ok((drawn, converted))
}

fn convert_ways(drawn: &Drawn, request: &LayersRequest) -> Result<Converted> {
    let (Some(p), Some(budget)) = (&drawn.panorama, &request.panorama) else {
        return Ok(crate::background::convert_with(&drawn.layers, request.window_colors, None)?);
    };
    let wc = request.window_colors;
    let attempt = |way: Way| -> std::result::Result<Converted, String> {
        let done = match way {
            Way::Hidden | Way::Black => crate::background::convert_with(&on_black(&drawn.layers), wc, None),
            Way::Painted => {
                // The layer above's tiles the layout leaves: the roofs' edges.
                let above = budget.of_mode(4).map(|l| l.above).max().unwrap_or(1);
                return painted(drawn, p, wc, above);
            }
            Way::Baked => {
                let done = crate::background::convert_with(&baked(&drawn.layers, &p.whole), wc, None)
                    .map_err(|e| e.to_string())?;
                if done.background.tiles.len() / 64 > budget.baked {
                    return Err(format!(
                        "baked, the background spends {} tiles and the most it can get is {}",
                        done.background.tiles.len() / 64,
                        budget.baked
                    ));
                }
                Ok(done)
            }
            Way::Mode3 | Way::Flattened | Way::Mode1 => {
                let (mode, number) = if way == Way::Mode1 { (Mode::One, 1) } else { (Mode::Three, 3) };
                let flat;
                let layers = if way == Way::Flattened {
                    flat = flattened(drawn.extended.as_ref().map_or(&drawn.layers, |(_, l)| l));
                    &flat
                } else {
                    &drawn.layers
                };
                let with = |extras: Vec<&picture::Picture>| -> std::result::Result<Converted, String> {
                    let mut why = format!("there is no layout for mode {number}");
                    for layout in budget.of_mode(number) {
                        let ask = crate::background::PanoramaAsk {
                            picture: &p.picture,
                            mode,
                            tiles: layout.panorama,
                            extras: extras.clone(),
                        };
                        let done = crate::background::convert_with(layers, wc, Some(&ask)).map_err(|e| e.to_string())?;
                        let spent = done.background.tiles.len() / 64;
                        if spent <= layout.background {
                            let mut done = Converted { way: Some(way), ..done };
                            if way == Way::Flattened {
                                let unflat = drawn.extended.as_ref().map_or(&drawn.layers, |(_, l)| l);
                                done.above_lost = raise_above(&mut done, &unflat.upper).0;
                            }
                            return Ok(done);
                        }
                        why = format!(
                            "in mode {number} the background spends {spent} tiles and the layouts leave it {} at most",
                            layout.background.max(budget.of_mode(number).map(|l| l.background).max().unwrap_or(0))
                        );
                    }
                    Err(why)
                };
                // With the other pictures its `ChangePBG`s name, which take
                // VRAM and colours from the same budget; and if they do not
                // fit, the map as it was without them.
                if p.extras.is_empty() || p.extras_left.is_some() {
                    return with(Vec::new()).map(|done| Converted { extras_left: p.extras_left.clone(), ..done });
                }
                return match with(p.extras.iter().map(|e| &e.picture).collect()) {
                    Ok(done) => Ok(done),
                    Err(why) => with(Vec::new()).map(|done| Converted {
                        extras_left: Some(format!("with them, {why}")),
                        ..done
                    }),
                };
            }
        };
        done.map(|d| Converted { way: Some(way), ..d }).map_err(|e| e.to_string())
    };
    if let Some(way) = budget.way {
        return attempt(way).map_err(|why| Bad::answer(format!("map {}: its panorama can't go {}: {why}", request.map, way.name())));
    }
    if !shows(&drawn.layers) {
        return attempt(Way::Hidden).map_err(Bad::answer);
    }
    let mut tried = Vec::new();
    let mut order = Vec::new();
    // Baked, what goes in front of the hero would be BG1's at priority 1,
    // which is in front of the message window too.
    if still(drawn, p) && drawn.front.is_none() {
        order.push(Way::Baked);
    }
    // Painted, if the project asks for it and the panorama is the map: before
    // the ways that group its cells, and after baked, whose 8 bits keep more
    // colours.
    if budget.painted && paintable(drawn, p) {
        order.push(Way::Painted);
    }
    if !draws_above(&drawn.layers) {
        order.push(Way::Mode3);
    } else if order.is_empty() {
        // Flattened first, kept only if it puts little on the wrong side of
        // the hero; then mode 1; then flattened anyway, if mode 1 does not
        // fit.
        match attempt(Way::Flattened) {
            Ok(mut done) if done.above_lost <= ABOVE_LOST_MAX => {
                done.tried = tried;
                return Ok(done);
            }
            Ok(done) => {
                tried.push(format!(
                    "flattened: {} pixels go to the wrong side of the hero, more than {ABOVE_LOST_MAX}",
                    done.above_lost
                ));
                order.extend([Way::Mode1, Way::Flattened]);
            }
            Err(why) => {
                tried.push(format!("flattened: {why}"));
                order.push(Way::Mode1);
            }
        }
    } else {
        order.extend([Way::Flattened, Way::Mode1]);
    }
    for way in order {
        match attempt(way) {
            Ok(mut done) => {
                done.tried = tried;
                return Ok(done);
            }
            Err(why) => tried.push(format!("{}: {why}", way.name())),
        }
    }
    let mut done = attempt(Way::Black).map_err(Bad::answer)?;
    done.tried = tried;
    Ok(done)
}

/// The tilemap priority bit: a BG1 cell with it goes in front of the
/// objects of priority 1 and 2, the hero and the events.
const PRIORITY: u16 = 0x2000;

/// A flattened map's cells that draw something above the hero, raised in
/// front of him: BG1's priority bit. Mode 3 puts BG1 1 in front of objects
/// 2 and 1, so the hero walks behind what RM2k draws above him, as he does
/// behind the layer above in a map without a panorama. What is lost is the
/// grain: a whole 8x8 cell goes in front or behind. So a cell goes in front
/// only if the upper layer draws at least half of it: in front, the
/// background's pixels in it cover the hero too, and on the edge of
/// something —the tip of the Hover-Tram over the captain— a square of floor
/// over his head looked like a mistake, where his head over the edge looks
/// like any RM2k game. The message window is BG2 and would be behind them:
/// the runtime hides BG1 under it, see `pano_ppu`.
///
/// Answers how many pixels end up on the wrong side of the hero —the upper
/// layer's in a cell left behind, the background's in a cell raised— and
/// how many the upper layer draws.
fn raise_above(done: &mut Converted, upper: &picture::Picture) -> (usize, usize) {
    let (mut wrong, mut total) = (0, 0);
    for (cy, row) in done.background.tilemap.iter_mut().enumerate() {
        for (cx, entry) in row.iter_mut().enumerate() {
            let drawn = (0..8)
                .flat_map(|y| (0..8).map(move |x| (x, y)))
                .filter(|&(x, y)| upper.get((cx * 8 + x) as i64, (cy * 8 + y) as i64)[3] != 0)
                .count();
            total += drawn;
            if drawn * 2 >= 64 {
                *entry |= PRIORITY;
                wrong += 64 - drawn;
            } else {
                wrong += drawn;
            }
        }
    }
    (wrong, total)
}

/// The most pixels a flattened map may put on the wrong side of the hero
/// —see [`raise_above`]— and still go flattened rather than in mode 1: four
/// RM2k cells. It is the "little" of "what goes above the hero is little":
/// flattening keeps the panorama's colours and the map's, mode 1 keeps
/// what goes above the hero exactly and loses colours of both, so the line
/// is drawn where the first loss stops being small. Measured on A Blurred
/// Line on 2026-10-05: the intro (1) loses 201 pixels of 167511, the
/// Linkage Block (2) 217, the overlooks (109, 126) 889 and the roof of the
/// escape (33) 192; and the warehouse with the Hover-Tram (32) loses its
/// fences, the bridge's underside (255) its chains, the mountain path
/// (105) 3888 pixels and CoreRetro (6) 9520.
pub const ABOVE_LOST_MAX: usize = 4 * 16 * 16;

/// Whether the panorama shows anywhere: a pixel that neither layer draws,
/// in any drawing of the animation.
fn shows(layers: &Layers) -> bool {
    let upper = &layers.upper.rgba;
    std::iter::once(&layers.lower)
        .chain(layers.variants.iter().flat_map(|(_, gs)| gs))
        .any(|lower| {
            lower
                .rgba
                .chunks_exact(4)
                .zip(upper.chunks_exact(4))
                .any(|(l, u)| l[3] == 0 && u[3] == 0)
        })
}

/// Whether the map can go painted: its panorama is the map —see
/// `map_pictures::fixed_to_map`— and the ChipSet draws nothing on it, in
/// neither layer, so that the painting is all there is. A map whose ChipSet
/// draws, animates or changes its cells with a `TileSubstitution` needs its
/// blocks in BG1, which the painting takes.
fn paintable(drawn: &Drawn, p: &Panorama) -> bool {
    let empty = |pic: &picture::Picture| pic.rgba.chunks_exact(4).all(|px| px[3] == 0);
    crate::map_pictures::fixed_to_map(p, (drawn.map.width * 16, drawn.map.height * 16))
        && drawn.layers.variants.is_empty()
        && drawn.extended.is_none()
        && empty(&drawn.layers.lower)
        && empty(&drawn.layers.upper)
}

/// A painted map: the panorama, with what the map's pictures drew into it,
/// in BG1 at 4 bits, a tile per cell —see `background::painted`—. The map's
/// own layers draw nothing: its background is one black tile and its layer
/// above none, and the painting's palettes travel as the layer above's, as a
/// mode-3 panorama's do.
fn painted(drawn: &Drawn, p: &Panorama, window_colors: usize, above: usize) -> std::result::Result<Converted, String> {
    let (w, h) = (drawn.map.width * 16, drawn.map.height * 16);
    let mut whole = picture::Picture::transparent(w, h);
    for y in 0..h {
        for x in 0..w {
            let mut px = p.whole.get((x % p.whole.width) as i64, (y % p.whole.height) as i64);
            px[3] = 255;
            whole.rgba[(y * w + x) * 4..(y * w + x) * 4 + 4].copy_from_slice(&px);
        }
    }
    let blank = Layers {
        lower: picture::Picture::transparent(w, h),
        upper: picture::Picture::transparent(w, h),
        variants: Vec::new(),
    };
    let mut done = crate::background::convert_with(&on_black(&blank), window_colors, None).map_err(|e| e.to_string())?;
    // That black tile is never seen —BG1 shows the painting's cells, see
    // `runtime/painted.s`—, so it takes no colour: with a message window of
    // fifteen, its one entry would fall on the painting's first palette.
    done.background.cgram.clear();
    done.background.used = 0;
    let (mut pano, decided) = crate::background::painted::painted(&whole).map_err(|e| e.to_string())?;
    // What goes in front of the hero: BG1's priority, and the edges in BG2,
    // the layer above's place, in its tiles but the blank one.
    if let Some(front) = &drawn.front {
        let (tiles, tilemap, wrong, total) =
            crate::background::painted::roofs(&mut pano, front, w, above.saturating_sub(1));
        done.above.tiles = tiles;
        done.above.tilemap = tilemap;
        done.in_front = Some((wrong, total));
    }
    done.above.first = pano.first / crate::background::layers::COLORS_PER_PALETTE;
    done.above.cgram = pano.cgram.iter().flat_map(|w| w.to_le_bytes()).collect();
    done.pictures.push(crate::background::Decided { name: "panorama".to_string(), picture: decided });
    done.panorama = Some(pano);
    done.way = Some(Way::Painted);
    Ok(done)
}

/// Whether the map draws anything above the hero.
fn draws_above(layers: &Layers) -> bool {
    layers.upper.rgba.chunks_exact(4).any(|p| p[3] != 0)
}

/// Whether the panorama stays where it is against the map: RM2k's camera
/// never moves in a map no bigger than its screen, and then
/// `Game_Map::Parallax` puts the panorama's corner on the map's, unless it
/// scrolls on its own.
fn still(drawn: &Drawn, p: &Panorama) -> bool {
    drawn.map.width * 16 <= RM2K_SCREEN.0 && drawn.map.height * 16 <= RM2K_SCREEN.1 && p.auto == (0, 0) && !p.changes
}

/// The layer behind the hero, and each drawing of its animation, with
/// `under` drawn where it draws nothing: `under` repeats, as RM2k draws a
/// panorama smaller than the screen.
fn under(layers: &Layers, under: impl Fn(usize, usize) -> [u8; 4]) -> Layers {
    let fill = |below: &picture::Picture| {
        let mut out = below.clone();
        let w = out.width;
        for (i, px) in out.rgba.chunks_exact_mut(4).enumerate() {
            if px[3] == 0 {
                px.copy_from_slice(&under(i % w, i / w));
            }
        }
        out
    };
    Layers {
        lower: fill(&layers.lower),
        upper: layers.upper.clone(),
        variants: layers
            .variants
            .iter()
            .map(|(f, gs)| (*f, gs.iter().map(fill).collect()))
            .collect(),
    }
}

/// The layers as they were before panoramas: black where one would show.
fn on_black(layers: &Layers) -> Layers {
    under(layers, |_, _| [0, 0, 0, 255])
}

/// The layers with the panorama baked in, its corner on the map's.
fn baked(layers: &Layers, whole: &picture::Picture) -> Layers {
    under(layers, |x, y| {
        let mut p = whole.get((x % whole.width) as i64, (y % whole.height) as i64);
        p[3] = 255;
        p
    })
}

/// The layers with the upper one drawn over the lower one, in every drawing
/// of the animation, and nothing left above.
fn flattened(layers: &Layers) -> Layers {
    let over = |below: &picture::Picture| {
        let mut out = below.clone();
        for (px, up) in out.rgba.chunks_exact_mut(4).zip(layers.upper.rgba.chunks_exact(4)) {
            if up[3] != 0 {
                px.copy_from_slice(up);
            }
        }
        out
    };
    Layers {
        lower: over(&layers.lower),
        upper: picture::Picture::transparent(layers.upper.width, layers.upper.height),
        variants: layers
            .variants
            .iter()
            .map(|(f, gs)| (*f, gs.iter().map(over).collect()))
            .collect(),
    }
}

/// Each cell's passability —both layers resolved, as the hero meets them—
/// and the map in blocks.
///
/// A map converted with the rows of [`Drawn::extended`] makes its blocks
/// with them, so that they are in the table, and then loses them: its
/// cells, its passability and its tilemaps are the map's.
pub fn blocks(drawn: &Drawn, converted: &mut Converted) -> Result<(Vec<u8>, Blocks)> {
    let rows = drawn.map.height * 2;
    if converted.background.tilemap.len() > rows {
        let map = &drawn.extended.as_ref().expect("a tilemap past the map comes from its extension").0;
        let (mut passability, mut made) = blocks_of(drawn, map, converted)?;
        let cells = drawn.map.width * drawn.map.height;
        passability.truncate(cells);
        made.cells.truncate(cells);
        converted.background.tilemap.truncate(rows);
        converted.background.cells = converted.background.tilemap.iter().map(Vec::len).sum();
        converted.above.tilemap.truncate(rows);
        return Ok((passability, made));
    }
    blocks_of(drawn, &drawn.map, converted)
}

fn blocks_of(drawn: &Drawn, map: &Map, converted: &Converted) -> Result<(Vec<u8>, Blocks)> {
    let flags = passability_table(&map.passable_lower, &map.passable_upper);
    let lower: Vec<i32> = map.lower_layer.iter().map(|&t| t as i32).collect();
    let upper: Vec<i32> = map.upper_layer.iter().map(|&t| t as i32).collect();
    let mut passability: Vec<u8> = lower
        .iter()
        .zip(&upper)
        .map(|(&l, &u)| rm2k_rules::passability::cell(&flags, l, u))
        .collect();
    for &cell in &drawn.blocked {
        passability[cell] = 0;
    }
    let terrain: Vec<i32> = lower.iter().map(|&l| terrain_of(&drawn.chipset, l)).collect();
    let made = blocks::blocks(
        &blocks::Map {
            width: map.width,
            height: map.height,
            lower: &lower,
            upper: &upper,
            passability: &passability,
            terrain: &terrain,
        },
        &converted.background.tilemap,
        &converted.above.tilemap,
    )?;
    Ok((passability, made))
}

fn write_file(dir: &Path, name: &str, bytes: &[u8]) -> Result<()> {
    std::fs::write(dir.join(name), bytes)
        .map_err(|e| Bad::usage(format!("{}: {e}", dir.join(name).display())))
}

/// Writes the conversion into `out`: the tiles, the runs and the block
/// table as binaries, what was decided as indexed PNGs, and the rest in
/// `layers.json`.
pub fn write(
    out: &Path,
    converted: &Converted,
    panorama: Option<&Panorama>,
    passability: &[u8],
    made: &Blocks,
) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let bg = &converted.background;
    let above = &converted.above;
    write_file(out, BACKGROUND_TILES, &bg.tiles)?;
    write_file(out, ABOVE_TILES, &above.tiles)?;
    write_file(out, ABOVE_CGRAM, &above.cgram)?;
    write_file(out, BLOCK_TABLE, &made.table)?;
    write_file(out, BLOCK_PASSABILITY, &made.passability)?;
    write_file(out, BLOCK_TERRAIN, &made.terrain)?;
    let mut runs = Vec::new();
    for run in &bg.runs {
        let mut files = Vec::new();
        for (d, drawing) in run.drawings.iter().enumerate() {
            let name = run_file(run, d);
            write_file(out, &name, drawing)?;
            files.push(name);
        }
        runs.push(json!({"family": run.family.name(), "base": run.base,
                         "tiles": run.tiles, "drawings": files}));
    }
    let mut pictures = Vec::new();
    for decided in &converted.pictures {
        let name = format!("{}.png", decided.name);
        voodoo::image::write(&out.join(&name), &decided.picture)
            .map_err(|e| Bad::usage(e.to_string()))?;
        pictures.push(json!({"name": decided.name, "file": name}));
    }
    let pano = match (&converted.panorama, panorama) {
        (Some(p), Some(source)) => {
            write_file(out, PANORAMA_TILES, &p.tiles)?;
            // The other pictures its `ChangePBG`s name that it carries, in
            // the order the bytecode numbers them after this one.
            let mut images = Vec::new();
            for (extra, converted) in source.extras.iter().zip(&p.extras) {
                let Ok(q) = converted else { continue };
                let file = format!("panorama-{}.bin", images.len() + 1);
                write_file(out, &file, &q.tiles)?;
                images.push(json!({
                    "name": extra.name,
                    "size": [extra.size.0, extra.size.1],
                    "stretch": [extra.picture.width, extra.picture.height],
                    "tiles": q.tiles.len() / if q.mode.number() == 1 { 16 } else { 32 },
                    "file": file,
                    "tilemap": q.tilemap,
                    "first": q.first,
                    "cgram": q.cgram,
                    "backdrop": q.backdrop,
                    "distinct": q.distinct,
                    "colors": q.colors,
                    "kept": q.kept,
                    "merges": merges_json(&q.merges),
                }));
            }
            json!({
                "images": images,
                "none_first": source.none_first,
                "name": source.name,
                "mode": p.mode.number(),
                "size": [source.size.0, source.size.1],
                "stretch": [source.picture.width, source.picture.height],
                "loop": [source.looped.0, source.looped.1],
                "auto": [source.auto.0, source.auto.1],
                "tiles": p.tiles.len() / if p.mode.number() == 1 { 16 } else { 32 },
                "tilemap": p.tilemap,
                "first": p.first,
                "cgram": p.cgram,
                "backdrop": p.backdrop,
                "distinct": p.distinct,
                "colors": p.colors,
                "kept": p.kept,
                "merges": merges_json(&p.merges),
                "above_bg1": converted.way == Some(Way::Flattened),
            })
        }
        _ => Value::Null,
    };
    let answer = json!({
        "panorama": pano,
        "panorama_way": converted.way.map(Way::name),
        "panorama_tried": converted.tried,
        "panorama_dropped": converted.dropped.iter().map(|(n, why)| json!([n, why])).collect::<Vec<_>>(),
        "panorama_unseen": converted.unseen,
        "panorama_above_lost": converted.above_lost,
        "pictures_in_front": converted.in_front.map(|(wrong, total)| json!({"wrong": wrong, "pixels": total})),
        "background": {
            "bpp": bg.bpp,
            "tiles": bg.tiles.len() / 64,
            "cgram": bg.cgram,
            "tilemap": bg.tilemap,
            "colors": bg.colors,
            "used": bg.used,
            "budget": bg.budget,
            "merges": merges_json(&bg.merges),
            "cells": bg.cells,
            "runs": runs,
        },
        "above": {
            "tilemap": above.tilemap,
            "first": above.first,
            "merges": merges_json(&above.merges),
        },
        "pictures": pictures,
        "passability": passability,
        "blocks": {
            "cells": made.cells,
            "combos": made.combos.iter().map(|&((l, u), b)| json!([l, u, b])).collect::<Vec<_>>(),
        },
    });
    write_file(out, ANSWER_FILE, answer.to_string().as_bytes())
}

/// A global merge as `[victim, target, pixels]`, or a palette-local one as
/// `[palette, victim, target, pixels]`; a colour is `[r, g, b]`.
fn merges_json(merges: &[Merge]) -> Vec<Value> {
    merges
        .iter()
        .map(|m| match m.palette {
            Some(palette) => json!([palette, m.victim, m.target, m.pixels]),
            None => json!([m.victim, m.target, m.pixels]),
        })
        .collect()
}

/// The whole `layers` command: the request's map, drawn and converted,
/// into `out`.
pub fn run(game: &Game, request: &LayersRequest, out: &Path) -> Result<()> {
    let (drawn, mut converted) = draw_converted(game, request)?;
    let (passability, made) = blocks(&drawn, &mut converted)?;
    write(out, &converted, drawn.panorama.as_ref(), &passability, &made)
}
