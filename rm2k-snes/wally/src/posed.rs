//! The still events that change pose, drawn into the background's cells:
//! one block per pose they can show, and the console writes the cell again
//! when the pose changes.
//!
//! A floor switch, a chest, a lever: an event that never walks and whose
//! drawing changes only when a page or a route turns it. As an object it
//! costs the console a 32x32 sprite —four slivers on each of its lines, of
//! the 34 the PPU draws per line— and a pass through the placing of
//! sprites every frame; Zounds' map 96 lines fifty-six such switches up and
//! drops slivers and frames. Here the event keeps its row —it triggers,
//! blocks, has pages and routes— but its row draws no object: its cell of
//! the grid points at the block of the pose it shows, and `posed.s` in the
//! runtime rewrites that cell and its four tilemap words when the row's
//! page or pose changes, in the same frame the object would have changed.
//!
//! **The background, not the layer above.** Mode 3 puts BG2 in front of the
//! characters' objects at priority 1 and behind the background at 0, so
//! nothing on BG2 can be under the hero and over the floor: the book's
//! "Still events drawn into the background" says what was measured. BG1 at
//! priority 0 is under every character, which is where RM2k draws an event
//! below the hero; one on the hero's layer goes only if every pose stays
//! inside its 16x16 cell, as a decorative one —see [`crate::decor`]—, so
//! the only character that overlaps it is one in front of it.
//!
//! The rest of what keeps one an object is what the cell cannot follow:
//! anything that moves it —a route that steps, `SetEventLocation`,
//! `SwapEventLocations`—, flashes it or makes it translucent, a page that
//! animates it or puts it above the hero, a route that gives it another
//! graphic, and turning toward the hero, which swaps the row's tile for the
//! turn slot's.

use crate::events::{unbaked, Event, BAKED_SUFFIX, LAYER_BELOW, LAYER_SAME, UPPER_BASE};
use crate::fail::Result;
use crate::moves::ScannedPage;
use crate::sheets::Drawer;
use crate::sprites::character::Key;
use crate::sprites::npc::Npc;
use crate::sprites::split::TILE_PREFIX;
use rm2k_render::{Layers, Picture};
use rm2k_rules::charset::{character_origin, OFFSET_X, OFFSET_Y, POSE_HEIGHT, POSE_WIDTH};
use rm2k_rules::chipset::TILE;
use rm2k_rules::passability::ABOVE;
use std::collections::{BTreeMap, BTreeSet};

/// `SetEventLocation`, `SwapEventLocations` and `FlashSprite`, liblcf's
/// codes: an event one of them names is not drawn into its cell.
const SET_EVENT_LOCATION: i32 = 10860;
const SWAP_EVENT_LOCATIONS: i32 = 10870;
const FLASH_SPRITE: i32 = 11320;
/// `MoveEvent`: one that names "this event" from a common event can walk
/// whoever calls it.
const MOVE_EVENT: i32 = 11330;
/// "This event" in a command's event parameter.
const THIS_EVENT: i32 = 10005;

/// The triggers that turn an event toward the hero: see `moves`.
const TURNING_TRIGGERS: [i32; 3] = [0, 1, 2];

/// One event drawn into the background.
#[derive(Clone, Debug)]
pub struct Posed {
    /// Its index in the map's table, its RM2k id and its cell.
    pub event: usize,
    pub id: i32,
    pub x: i32,
    pub y: i32,
    /// The characters its pages draw, in the order they first show: the
    /// console's row says which by its index.
    pub graphics: Vec<Key>,
    /// Each pose it can show, as `(graphic, pose)`, with its 24x32 drawing.
    pub poses: Vec<(usize, i32, Picture)>,
    /// What its row starts showing, or `None` if it starts hidden.
    pub start: Option<(usize, i32)>,
}

/// What of the map the choice reads besides its events and rows.
pub struct Wants<'a> {
    pub pages: &'a [ScannedPage],
    /// Events someone else sends walking, by index.
    pub also_walk: &'a BTreeSet<usize>,
    /// Events already baked or decorative, by index: they are not rows.
    pub taken: &'a BTreeSet<usize>,
    /// The events routes give a graphic —command 34—, by index.
    pub dressed: &'a BTreeSet<usize>,
    /// The common events' commands, and the test pages': what they name.
    pub common: &'a [(i32, Vec<i32>)],
    /// The tile ids a substitution names: a cell with one swaps its block.
    pub apart: &'a BTreeSet<i32>,
    pub width: usize,
    pub lower: &'a [i32],
    pub upper: &'a [i32],
    /// The ChipSet's passability, per tile id.
    pub flags: &'a [u8],
}

/// Whether every pixel a pose draws is inside the 16x16 of its cell.
pub fn inside_the_cell(frame: &Picture) -> bool {
    let (left, top) = (-OFFSET_X as usize, -OFFSET_Y as usize);
    let tile = TILE as usize;
    (0..frame.height).all(|y| {
        (0..frame.width).all(|x| {
            let inside = (left..left + tile).contains(&x) && (top..top + tile).contains(&y);
            inside || frame.rgba[(y * frame.width + x) * 4 + 3] == 0
        })
    })
}

/// The events of the map named by a command that moves or flashes them,
/// by index; `None` if a common event does it to "this event", which can
/// be anyone that calls it.
fn named(events: &[Event], common: &[(i32, Vec<i32>)]) -> Option<BTreeSet<usize>> {
    let targets = |code: i32, params: &[i32]| -> Vec<i32> {
        match code {
            SET_EVENT_LOCATION | FLASH_SPRITE => params.iter().take(1).copied().collect(),
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
        let mut all = targets(*code, params);
        if *code == MOVE_EVENT {
            all.extend(params.first().copied());
        }
        for t in all {
            if t == THIS_EVENT {
                return None;
            }
            out.extend(by_id(t));
        }
    }
    Some(out)
}

/// The rows that can be drawn into the background, and why each of the
/// others is not, as `(why, RM2k ids)`.
pub fn select(
    drawer: &mut Drawer,
    events: &[Event],
    npcs: &[Npc],
    wants: &Wants,
) -> Result<(Vec<Posed>, BTreeMap<&'static str, Vec<i32>>)> {
    let mut out = Vec::new();
    let mut not: BTreeMap<&'static str, Vec<i32>> = BTreeMap::new();
    let Some(named) = named(events, wants.common) else {
        let ids = npcs.iter().map(|n| events[n.event].id).collect();
        not.insert("a common event moves or flashes \"this event\"", ids);
        return Ok((out, not));
    };
    for npc in npcs {
        let e = npc.event;
        if wants.taken.contains(&e) {
            continue;
        }
        let event = &events[e];
        let why = why_not(drawer, event, npc, wants, &named)?;
        match why {
            Err(why) => not.entry(why).or_default().push(event.id),
            Ok(posed) => out.push(posed),
        }
    }
    Ok((out, not))
}

fn why_not(
    drawer: &mut Drawer,
    event: &Event,
    npc: &Npc,
    wants: &Wants,
    named: &BTreeSet<usize>,
) -> Result<std::result::Result<Posed, &'static str>> {
    let e = npc.event;
    if npc.dressed() || wants.dressed.contains(&e) {
        return Ok(Err("a route gives it a graphic"));
    }
    if wants.also_walk.contains(&e) || named.contains(&e) {
        return Ok(Err("a command moves or flashes it"));
    }
    if event.pages.iter().any(|p| p.move_type != 0 || p.own_route) {
        return Ok(Err("it walks on its own"));
    }
    if npc.animates || event.pages.iter().any(|p| matches!(p.animation, 1 | 3 | 5)) {
        return Ok(Err("it animates standing still"));
    }
    let drawn: Vec<(usize, &(String, i32, i32))> = npc
        .graphics
        .iter()
        .enumerate()
        .filter_map(|(k, g)| g.as_ref().map(|g| (k, g)))
        .collect();
    if drawn
        .iter()
        .any(|(k, _)| !matches!(npc.layers[*k], LAYER_BELOW | LAYER_SAME))
    {
        return Ok(Err("a page puts it above the hero"));
    }
    for (_, (name, _, _)) in &drawn {
        if name.contains(&format!("{BAKED_SUFFIX}:")) {
            return Ok(Err("it is translucent"));
        }
        let base = unbaked(name);
        if let Some(index) = base.strip_prefix(TILE_PREFIX) {
            let tile = index.rsplit(':').next().and_then(|i| i.parse::<i32>().ok());
            if tile.is_none_or(|t| wants.flags[(UPPER_BASE + t) as usize] & ABOVE != 0) {
                return Ok(Err("its tile goes above the hero"));
            }
        }
    }
    let turns_to_hero = wants
        .pages
        .iter()
        .any(|p| p.event == e && p.compiles && p.turns && TURNING_TRIGGERS.contains(&p.trigger));
    if turns_to_hero {
        return Ok(Err("it turns toward the hero"));
    }
    // Routes that only turn it are a pose change; any other moves it.
    let routed: Vec<&ScannedPage> = wants
        .pages
        .iter()
        .filter(|p| p.compiles && p.route_targets.contains(&e))
        .collect();
    if routed.iter().any(|p| !p.route_turns.contains(&e)) {
        return Ok(Err("a route moves it"));
    }
    let turner = !routed.is_empty();
    let at = npc.y as usize * wants.width + npc.x as usize;
    if wants.apart.contains(&wants.lower[at]) || wants.apart.contains(&wants.upper[at]) {
        return Ok(Err("a substitution swaps its cell"));
    }
    // The poses: each page's, and the four facings of its column if a route
    // turns it.
    let mut graphics: Vec<Key> = Vec::new();
    let mut wanted: BTreeSet<(usize, i32)> = BTreeSet::new();
    for (_, (name, index, pose)) in &drawn {
        let key = (name.clone(), *index);
        let g = match graphics.iter().position(|k| *k == key) {
            Some(g) => g,
            None => {
                graphics.push(key);
                graphics.len() - 1
            }
        };
        wanted.insert((g, *pose));
        if turner {
            for facing in 0..4 {
                wanted.insert((g, facing * 3 + pose % 3));
            }
        }
    }
    if graphics.len() > MAX_GRAPHICS {
        return Ok(Err("its pages draw too many characters"));
    }
    let mut poses = Vec::new();
    for &(g, pose) in &wanted {
        let (name, index) = &graphics[g];
        let Some(sheet) = drawer.draw(name)? else {
            return Ok(Err("its CharSet is missing"));
        };
        let (ox, oy) = character_origin(*index);
        let frame = sheet.crop(
            (ox + pose % 3 * POSE_WIDTH) as i64,
            (oy + pose / 3 * POSE_HEIGHT) as i64,
            POSE_WIDTH as usize,
            POSE_HEIGHT as usize,
        );
        if !inside_the_cell(&frame) {
            return Ok(Err("a pose is drawn past its cell"));
        }
        poses.push((g, pose, frame));
    }
    let start = npc.visible.then(|| {
        let key = (npc.charset.clone(), npc.index);
        let g = graphics.iter().position(|k| *k == key).unwrap_or(0);
        (g, npc.pose)
    });
    Ok(Ok(Posed {
        event: e,
        id: event.id,
        x: npc.x,
        y: npc.y,
        graphics,
        poses,
        start,
    }))
}

/// The most characters one event's pages can draw: the row says which in
/// three bits of its attributes.
pub const MAX_GRAPHICS: usize = 8;

/// The cells `posed` asks for, in the order the extension draws them: the
/// event's cell and each pose's drawing.
pub fn cells(posed: &[Posed], width: usize) -> Vec<(usize, Picture)> {
    posed
        .iter()
        .flat_map(|p| {
            let at = p.y as usize * width + p.x as usize;
            p.poses.iter().map(move |(_, _, f)| (at, f.clone()))
        })
        .collect()
}

/// Paints each pose over its cell of the extension, from `first`, in every
/// drawing of the lower layer: what [`crate::layers::draw`] calls.
pub fn compose(layers: &mut Layers, width: usize, first: usize, posed: &[(usize, Picture)]) {
    let paint = |picture: &mut Picture| {
        for (k, (_, frame)) in posed.iter().enumerate() {
            let cell = first + k;
            let (x0, y0) = (
                (cell % width) as i64 * TILE as i64 + OFFSET_X as i64,
                (cell / width) as i64 * TILE as i64 + OFFSET_Y as i64,
            );
            for py in 0..frame.height {
                for px in 0..frame.width {
                    let at = (py * frame.width + px) * 4;
                    if frame.rgba[at + 3] == 0 {
                        continue;
                    }
                    let (x, y) = (x0 + px as i64, y0 + py as i64);
                    if x < 0 || y < 0 || x >= picture.width as i64 || y >= picture.height as i64 {
                        continue;
                    }
                    let to = (y as usize * picture.width + x as usize) * 4;
                    picture.rgba[to..to + 4].copy_from_slice(&frame.rgba[at..at + 4]);
                }
            }
        }
    };
    paint(&mut layers.lower);
    for (_, drawings) in layers.variants.iter_mut() {
        for picture in drawings.iter_mut() {
            paint(picture);
        }
    }
}

/// What the console reads of one, once its blocks are known: the table of
/// blocks by `(graphic, pose)` —twelve per graphic, the poses it never
/// shows filled with its first—, the block of its cell without it, and the
/// key it starts with: `graphic * 12 + pose`, or $FF hidden.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Placed {
    pub event: usize,
    pub x: i32,
    pub y: i32,
    pub graphics: Vec<Key>,
    pub blocks: Vec<u16>,
    pub none: u16,
    pub start: u8,
}

/// The key a row with no pose shows: its cell without the event.
pub const HIDDEN: u8 = 0xFF;

/// Each one's table, from the blocks the extension's cells got —`blocks`,
/// one per pose in the order of [`cells`]— and the block of its cell as the
/// map draws it.
pub fn placed(posed: &[Posed], blocks: &[u16], own: impl Fn(&Posed) -> u16) -> Vec<Placed> {
    let mut k = 0;
    let mut out = Vec::new();
    for p in posed {
        let mut table = vec![None; p.graphics.len() * 12];
        for (g, pose, _) in &p.poses {
            table[g * 12 + *pose as usize] = Some(blocks[k]);
            k += 1;
        }
        let first = table.iter().flatten().next().copied().unwrap_or(0);
        let mut filled = Vec::with_capacity(table.len());
        for g in 0..p.graphics.len() {
            let mine = table[g * 12..g * 12 + 12].iter().flatten().next().copied();
            for pose in 0..12 {
                filled.push(table[g * 12 + pose].or(mine).unwrap_or(first));
            }
        }
        out.push(Placed {
            event: p.event,
            x: p.x,
            y: p.y,
            graphics: p.graphics.clone(),
            blocks: filled,
            none: own(p),
            start: p
                .start
                .map_or(HIDDEN, |(g, pose)| (g * 12) as u8 + pose as u8),
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(opaque: &[(usize, usize)]) -> Picture {
        let (w, h) = (POSE_WIDTH as usize, POSE_HEIGHT as usize);
        let mut rgba = vec![0u8; w * h * 4];
        for &(x, y) in opaque {
            rgba[(y * w + x) * 4 + 3] = 255;
        }
        Picture {
            width: w,
            height: h,
            rgba,
        }
    }

    /// A pose's 24x32 frame stands on its cell with 4 pixels each side and
    /// 16 above: a pixel there is past the cell.
    #[test]
    fn a_pose_inside_its_cell_is_told_from_one_past_it() {
        assert!(inside_the_cell(&frame(&[(4, 16), (19, 31)])));
        assert!(!inside_the_cell(&frame(&[(3, 20)])));
        assert!(!inside_the_cell(&frame(&[(10, 15)])));
    }

    /// Twelve blocks per character, the poses it never shows filled with
    /// its first; the cell without it; and the key it starts with.
    #[test]
    fn each_pose_gets_its_block_and_the_rest_the_first() {
        let posed = Posed {
            event: 3,
            id: 21,
            x: 2,
            y: 1,
            graphics: vec![("object2".into(), 4)],
            poses: vec![(0, 7, frame(&[])), (0, 10, frame(&[]))],
            start: Some((0, 7)),
        };
        let placed = placed(&[posed], &[5, 6], |p| (p.x * 10 + p.y) as u16);
        let p = &placed[0];
        assert_eq!(p.blocks.len(), 12);
        assert_eq!(p.blocks[7], 5);
        assert_eq!(p.blocks[10], 6);
        assert!(p.blocks.iter().enumerate().all(|(k, &b)| k == 10 || b == 5));
        assert_eq!(p.none, 21);
        assert_eq!(p.start, 7);
    }

    /// One that starts hidden starts with the cell without it.
    #[test]
    fn a_hidden_start_is_the_cell_without_it() {
        let posed = Posed {
            event: 0,
            id: 1,
            x: 0,
            y: 0,
            graphics: vec![("a".into(), 0), ("b".into(), 1)],
            poses: vec![(1, 4, frame(&[]))],
            start: None,
        };
        let placed = placed(&[posed], &[9], |_| 2);
        assert_eq!(placed[0].start, HIDDEN);
        assert_eq!(placed[0].none, 2);
        // The first character shows nothing of its own: the map's first.
        assert_eq!(placed[0].blocks[..12], [9; 12]);
        assert_eq!(placed[0].blocks[16], 9);
    }

    /// Each pose is painted over its own cell of the extension, and only
    /// its opaque pixels.
    #[test]
    fn a_pose_is_painted_over_its_cell_below_the_map() {
        let blank = Picture {
            width: 32,
            height: 32,
            rgba: vec![7u8; 32 * 32 * 4],
        };
        let mut layers = Layers {
            lower: blank.clone(),
            upper: blank,
            variants: Vec::new(),
        };
        // Two cells across, the extension's first one at cell 2: (0, 1).
        let mut f = frame(&[(4, 16)]);
        f.rgba[(16 * 24 + 4) * 4] = 200;
        compose(&mut layers, 2, 2, &[(0, f)]);
        let at = |x: usize, y: usize| layers.lower.rgba[(y * 32 + x) * 4];
        assert_eq!(at(0, 16), 200);
        assert_eq!(at(1, 16), 7);
        assert_eq!(at(0, 0), 7);
    }
}
