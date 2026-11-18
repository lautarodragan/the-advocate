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
use rm2k_rules::reach::{Stander, Standing};
use std::collections::{BTreeMap, BTreeSet};

/// `SetEventLocation`, `SwapEventLocations` and `FlashSprite`, liblcf's
/// codes: an event one of them names is not drawn into its cell.
const SET_EVENT_LOCATION: i32 = 10860;
const SWAP_EVENT_LOCATIONS: i32 = 10870;
const FLASH_SPRITE: i32 = 11320;
/// `MoveEvent`: one that names "this event" from a common event can walk
/// whoever calls it.
const MOVE_EVENT: i32 = 11330;
/// `EraseEvent` and `CallEvent`: one of its own pages that erases it, or
/// calls what may, can hide it.
const ERASE_EVENT: i32 = 12320;
const CALL_EVENT: i32 = 12330;
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
    /// How many pixels its poses were moved, `(x, y)`, to fit its cell:
    /// see [`shift_into_the_cell`]. `(0, 0)` for one that already fits.
    pub shift: (i32, i32),
    /// The layer its pages put it on, the highest if they differ: where
    /// RM2k stacks it among the others.
    pub layer: i32,
    /// What its poses draw past its cell, the same in all of them, as a
    /// 24x32 drawing with nothing inside the cell —`poses` keep only what
    /// is inside—; `None` for one that fits its cell. See [`spill`].
    pub spill: Option<Picture>,
    /// The events, by index, that have to go into the background too for
    /// its spill to be right: still ones that stand behind it, whose
    /// sprites would be drawn over it.
    pub relies: BTreeSet<usize>,
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
    /// `baked_events_nudge`: how many pixels, in x and in y, a pose drawn past
    /// its cell may be moved to fit it. 0 takes only the ones that fit.
    pub nudge: i32,
    /// Where every character's feet can ever be, if the caller knows: with
    /// it, a pose may be drawn past its cell where nobody can be behind it
    /// —see [`spill`]—; `None`, only inside it.
    pub standing: Option<&'a [Standing]>,
    pub height: usize,
}

/// Whether every pixel a pose draws is inside the 16x16 of its cell.
pub fn inside_the_cell(frame: &Picture) -> bool {
    shift_into_the_cell(&[frame], 0) == Some((0, 0))
}

/// The shift, `(x, y)` in pixels, that puts every pixel `frames` draw
/// inside the 16x16 of their cell, the same for all of them and the
/// smallest on each axis; `None` if it would have to be more than `max`
/// pixels on either.
///
/// One shift for all the poses because they are one event: if each moved
/// on its own, a chest would jump a pixel as it opens. A Blurred Line's
/// chests, `BLObjs` character 2, draw 1 px right and 2 px up of their
/// cell: nothing is cropped, the whole drawing moves.
pub fn shift_into_the_cell(frames: &[&Picture], max: i32) -> Option<(i32, i32)> {
    let (mut x0, mut y0, mut x1, mut y1) = (i64::MAX, i64::MAX, i64::MIN, i64::MIN);
    for frame in frames {
        for y in 0..frame.height {
            for x in 0..frame.width {
                if frame.rgba[(y * frame.width + x) * 4 + 3] != 0 {
                    (x0, y0) = (x0.min(x as i64), y0.min(y as i64));
                    (x1, y1) = (x1.max(x as i64), y1.max(y as i64));
                }
            }
        }
    }
    if x0 > x1 {
        return Some((0, 0));
    }
    let tile = TILE as i64;
    // On one axis: the cell is `[start, start + 16)` of the frame, and the
    // drawing `[low, high]`.
    let axis = |start: i64, low: i64, high: i64| -> Option<i32> {
        let (least, most) = (start - low, start + tile - 1 - high);
        if least > most {
            return None;
        }
        let d = 0.clamp(least, most);
        (d.abs() <= max as i64).then_some(d as i32)
    };
    Some((
        axis(-OFFSET_X as i64, x0, x1)?,
        axis(-OFFSET_Y as i64, y0, y1)?,
    ))
}

/// `frame` moved `(dx, dy)` pixels inside its own size; what would fall
/// out of it is lost, which [`shift_into_the_cell`] never lets happen.
pub fn shifted(frame: &Picture, (dx, dy): (i32, i32)) -> Picture {
    if (dx, dy) == (0, 0) {
        return frame.clone();
    }
    let mut rgba = vec![0u8; frame.rgba.len()];
    for y in 0..frame.height as i64 {
        for x in 0..frame.width as i64 {
            let (tx, ty) = (x + dx as i64, y + dy as i64);
            if tx < 0 || ty < 0 || tx >= frame.width as i64 || ty >= frame.height as i64 {
                continue;
            }
            let from = (y as usize * frame.width + x as usize) * 4;
            let to = (ty as usize * frame.width + tx as usize) * 4;
            rgba[to..to + 4].copy_from_slice(&frame.rgba[from..from + 4]);
        }
    }
    Picture {
        width: frame.width,
        height: frame.height,
        rgba,
    }
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
    let mut past = Vec::new();
    for npc in npcs {
        let e = npc.event;
        if wants.taken.contains(&e) {
            continue;
        }
        let event = &events[e];
        let why = why_not(drawer, event, npc, wants, &named)?;
        match why {
            Err(why) => not.entry(why).or_default().push(event.id),
            Ok((posed, true)) => out.push(posed),
            Ok((posed, false)) => past.push((posed, npc)),
        }
    }
    // Those drawn past their cell, once it is known which others go into
    // the background with them.
    let others: BTreeSet<usize> = out
        .iter()
        .chain(past.iter().map(|(p, _)| p))
        .map(|p| p.event)
        .collect();
    for (posed, npc) in past {
        let id = posed.id;
        match spill(posed, &events[npc.event], npc, events, wants, &others) {
            Err(why) => not.entry(why).or_default().push(id),
            Ok(posed) => out.push(posed),
        }
    }
    out.sort_by_key(|p| p.event);
    Ok((out, not))
}

/// Why a still event drawn past its cell —whose poses do not fit it, even
/// moved— cannot be drawn into the background as it is, or the event as it
/// goes: its poses cut to the cell, and what they draw past it in
/// [`Posed::spill`], which the map draws into the cells around it once and
/// for all.
///
/// The background is under every character, so what it draws past its cell
/// is drawn under anyone there; RM2k draws a character on the hero's layer
/// over another only if it stands lower, or as low and further right
/// —easyrpg's `Game_Character::GetScreenZ`—, and one on the layer below
/// under every other. So the spill is right only where every character
/// whose sprite can cover one of its pixels is one RM2k draws over it: none
/// that can stand behind it —the cell above, or the one to its left on its
/// row—, which [`Wants::standing`] answers; and no other still event's
/// sprite there, which `relies` keeps.
///
/// **Only what is the same in every pose and never goes away**: the cells
/// around it are drawn once, and the console writes only its own cell when
/// its pose changes. So all its pages draw something, the first asks for
/// nothing —there is always a page—, none erases it or calls what may, and
/// it stays on one layer.
///
/// What it does not see: a character on its own cell —one on the layer
/// below walking under it, or one through walls— draws its 4 px sides over
/// the event's cell, as it does over any event drawn into its cell; here it
/// is taken as behind it, and so as something that rules the spill out.
pub fn spill(
    mut posed: Posed,
    event: &Event,
    npc: &Npc,
    events: &[Event],
    wants: &Wants,
    others: &BTreeSet<usize>,
) -> std::result::Result<Posed, &'static str> {
    let Some(standing) = wants.standing else {
        return Err("a pose is drawn past its cell");
    };
    if !always_there(event, npc) {
        return Err("it is drawn past its cell and can go away");
    }
    if npc.layers.iter().any(|&l| l != posed.layer) {
        return Err("it is drawn past its cell and changes layer");
    }
    let layer = posed.layer;
    // What every pose draws past the cell, which has to be the same.
    let outside = |frame: &Picture| -> Picture {
        let mut out = frame.clone();
        for (k, px) in out.rgba.chunks_mut(4).enumerate() {
            if in_cell(k % frame.width, k / frame.width) {
                px.copy_from_slice(&[0, 0, 0, 0]);
            }
        }
        out
    };
    let spill = outside(&posed.poses[0].2);
    if posed
        .poses
        .iter()
        .any(|(_, _, f)| outside(f).rgba != spill.rgba)
    {
        return Err("what it draws past its cell changes with its pose");
    }
    // Its pixels on the map, and the cells they fall on.
    let (x0, y0) = (
        i64::from(posed.x) * TILE as i64 + OFFSET_X as i64,
        i64::from(posed.y) * TILE as i64 + OFFSET_Y as i64,
    );
    let mut pixels = Vec::new();
    for (k, px) in spill.rgba.chunks(4).enumerate() {
        if px[3] != 0 {
            pixels.push((x0 + (k % spill.width) as i64, y0 + (k / spill.width) as i64));
        }
    }
    let (w, h) = (wants.width as i64, wants.height as i64);
    let tile = TILE as i64;
    for &(x, y) in &pixels {
        if x < 0 || y < 0 || x >= w * tile || y >= h * tile {
            return Err("it is drawn past the map's edge");
        }
        let at = (y / tile * w + x / tile) as usize;
        if wants.apart.contains(&wants.lower[at]) || wants.apart.contains(&wants.upper[at]) {
            return Err("it is drawn past its cell onto a cell a substitution swaps");
        }
    }
    // Who can be behind it.
    let by_id = |id: i32| events.iter().position(|e| e.id == id);
    let own = posed.y as usize * wants.width + posed.x as usize;
    let me = (posed.x, posed.y, layer, posed.id);
    let mut relies = BTreeSet::new();
    for s in standing {
        let (layers, index): (Vec<i32>, Option<usize>) = match s.who {
            Stander::Hero => (vec![LAYER_SAME], None),
            Stander::Event(id) => match by_id(id) {
                Some(e) => (events[e].pages.iter().map(|p| p.layer).collect(), Some(e)),
                None => continue,
            },
            Stander::AnyEvent => (vec![LAYER_BELOW, LAYER_SAME], None),
        };
        if let Some(e) = index {
            let at = events[e].y as usize * wants.width + events[e].x as usize;
            let still = s.cells.len() == 1 && s.cells.contains(&at) && s.risen.is_empty();
            // Itself, and the others that go into the background and never
            // move, which the map draws in RM2k's order: see `cells`.
            if e == posed.event || (still && wants.taken.contains(&e)) {
                continue;
            }
            if still && others.contains(&e) {
                if covers(
                    at,
                    false,
                    &pixels,
                    wants.width,
                    me,
                    &layers,
                    Some(events[e].id),
                ) {
                    relies.insert(e);
                }
                continue;
            }
        }
        for (cells, risen) in [(&s.cells, false), (&s.risen, true)] {
            for &at in cells {
                // Its own cell, for one that collides with it: it is always
                // there, and closes it.
                let collides = layer == LAYER_SAME && layers.iter().all(|&l| l == LAYER_SAME);
                if at == own && collides && !s.phases {
                    continue;
                }
                let who = match s.who {
                    Stander::Event(id) => Some(id),
                    Stander::Hero | Stander::AnyEvent => None,
                };
                if covers(at, risen, &pixels, wants.width, me, &layers, who) {
                    return Err("someone can stand behind what it draws past its cell");
                }
            }
        }
    }
    let inside = |frame: &Picture| -> Picture {
        let mut out = frame.clone();
        for (k, px) in out.rgba.chunks_mut(4).enumerate() {
            if !in_cell(k % frame.width, k / frame.width) {
                px.copy_from_slice(&[0, 0, 0, 0]);
            }
        }
        out
    };
    for (_, _, frame) in posed.poses.iter_mut() {
        *frame = inside(frame);
    }
    posed.spill = Some(spill);
    posed.relies = relies;
    Ok(posed)
}

/// Whether pixel `(x, y)` of a 24x32 pose is inside its 16x16 cell.
fn in_cell(x: usize, y: usize) -> bool {
    let (left, top) = (-OFFSET_X as usize, -OFFSET_Y as usize);
    (left..left + TILE as usize).contains(&x) && (top..top + TILE as usize).contains(&y)
}

/// Whether one on cell `at` —16 px higher if `risen`—, on one of `layers`,
/// is drawn under the event `(x, y, layer, id)` where what it draws past
/// its cell is not, and its sprite's 24x32 covers one of `pixels`. `who`
/// is its event id, `None` for the hero or anyone.
///
/// RM2k draws the one on the cell above under it, and on its row the one
/// to its left; on its own cell the one with the lower id, the hero under
/// every event. **The one to its left is let through**: it draws its 4 px
/// side over the event's cell already, wherever it is drawn into the
/// background as an event that fits its cell is —the book's "Still events
/// drawn into the background"—, and what the event draws past its cell
/// adds the same 4 px over its side and over its head on the row above;
/// and that one stands as close as the event's own neighbour. On A Blurred
/// Line's Hover-Tram, 3 px of a seated person's 120 past the cell fall on
/// the cell to its left.
fn covers(
    at: usize,
    risen: bool,
    pixels: &[(i64, i64)],
    width: usize,
    (x, y, layer, id): (i32, i32, i32, i32),
    layers: &[i32],
    who: Option<i32>,
) -> bool {
    let (cx, cy) = ((at % width) as i32, (at / width) as i32);
    let below = |l: i32| {
        l < layer || (l == layer && (cy < y || (cy == y && cx == x && who.is_none_or(|w| w < id))))
    };
    let behind = layers.iter().any(|&l| below(l));
    if !behind {
        return false;
    }
    let tile = TILE as i64;
    let left = i64::from(cx) * tile + OFFSET_X as i64;
    let top = i64::from(cy) * tile + OFFSET_Y as i64 - if risen { tile } else { 0 };
    let bottom = i64::from(cy) * tile + tile;
    pixels.iter().any(|&(px, py)| {
        (left..left + POSE_WIDTH as i64).contains(&px) && (top..bottom).contains(&py)
    })
}

/// Whether it is drawn whatever the game does: every page draws it, the
/// first asks for nothing, so some page always holds, and none of its own
/// erases it or calls a common event that may.
fn always_there(event: &Event, npc: &Npc) -> bool {
    npc.visible
        && npc.graphics.iter().all(Option::is_some)
        && event.pages.first().is_some_and(|p| p.conditions.is_empty())
        && !event
            .pages
            .iter()
            .flat_map(|p| &p.commands)
            .any(|(code, _)| matches!(*code, ERASE_EVENT | CALL_EVENT))
}

/// The event drawn into the background, and whether its poses fit their
/// cell —moved, if they have to—; or why it cannot be.
fn why_not(
    drawer: &mut Drawer,
    event: &Event,
    npc: &Npc,
    wants: &Wants,
    named: &BTreeSet<usize>,
) -> Result<std::result::Result<(Posed, bool), &'static str>> {
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
        poses.push((g, pose, frame));
    }
    let frames: Vec<&Picture> = poses.iter().map(|(_, _, f)| f).collect();
    let shift = shift_into_the_cell(&frames, wants.nudge);
    if let Some(shift) = shift {
        for (_, _, frame) in poses.iter_mut() {
            *frame = shifted(frame, shift);
        }
    }
    let start = npc.visible.then(|| {
        let key = (npc.charset.clone(), npc.index);
        let g = graphics.iter().position(|k| *k == key).unwrap_or(0);
        (g, npc.pose)
    });
    let layer = drawn
        .iter()
        .map(|(k, _)| npc.layers[*k])
        .max()
        .unwrap_or(LAYER_SAME);
    Ok(Ok((
        Posed {
            event: e,
            id: event.id,
            x: npc.x,
            y: npc.y,
            graphics,
            poses,
            start,
            shift: shift.unwrap_or((0, 0)),
            layer,
            spill: None,
            relies: BTreeSet::new(),
        },
        shift.is_some(),
    )))
}

/// The most characters one event's pages can draw: the row says which in
/// three bits of its attributes.
pub const MAX_GRAPHICS: usize = 8;

/// A cell of the extension: the map's cell whose tiles it repeats, and
/// what is drawn over them, in order, each a 24x32 drawing standing on the
/// cell that far, in cells, from it —`(0, 0)` its own—, and only what falls
/// inside the cell.
pub type Cell = (usize, Vec<((i32, i32), Picture)>);

/// The order RM2k stacks one in: layer, row, column and id —easyrpg's
/// `Game_Character::GetScreenZ`—, back to front.
fn order(p: &Posed) -> (i32, i32, i32, i32) {
    (p.layer, p.y, p.x, p.id)
}

/// The cells `posed` asks for, in the order the extension draws them: the
/// event's cell and each pose's drawing, between what the others draw past
/// their cells onto it —see [`spill`]—, the ones behind it under it and the
/// ones in front over it, as the map draws them on its cell without it.
pub fn cells(posed: &[Posed], width: usize) -> Vec<Cell> {
    let tile = TILE as i64;
    // Whether `q`'s spill draws a pixel on `p`'s cell.
    let onto = |q: &Posed, p: &Posed| -> bool {
        let Some(spill) = &q.spill else {
            return false;
        };
        let (dx, dy) = (i64::from(p.x - q.x) * tile, i64::from(p.y - q.y) * tile);
        spill.rgba.chunks(4).enumerate().any(|(k, px)| {
            let (x, y) = (
                (k % spill.width) as i64 + OFFSET_X as i64 - dx,
                (k / spill.width) as i64 + OFFSET_Y as i64 - dy,
            );
            px[3] != 0 && (0..tile).contains(&x) && (0..tile).contains(&y)
        })
    };
    posed
        .iter()
        .flat_map(|p| {
            let at = p.y as usize * width + p.x as usize;
            let mut over: Vec<&Posed> = posed
                .iter()
                .filter(|q| q.event != p.event && onto(q, p))
                .collect();
            over.sort_by_key(|q| order(q));
            let spilled =
                |q: &&Posed| ((q.x - p.x, q.y - p.y), q.spill.clone().expect("it spills"));
            let behind: Vec<_> = over
                .iter()
                .filter(|q| order(q) < order(p))
                .map(spilled)
                .collect();
            let front: Vec<_> = over
                .iter()
                .filter(|q| order(q) > order(p))
                .map(spilled)
                .collect();
            p.poses.iter().map(move |(_, _, f)| {
                let mut stack = behind.clone();
                stack.push(((0, 0), f.clone()));
                stack.extend(front.iter().cloned());
                (at, stack)
            })
        })
        .collect()
}

/// The cells of the map whose drawing `p` changes: its own, and those it
/// draws past its cell onto.
pub fn written(p: &Posed, width: usize) -> Vec<usize> {
    let own = p.y as usize * width + p.x as usize;
    let mut out = vec![own];
    if let Some(spill) = &p.spill {
        let tile = TILE as i64;
        for (k, px) in spill.rgba.chunks(4).enumerate() {
            let x = i64::from(p.x) * tile + OFFSET_X as i64 + (k % spill.width) as i64;
            let y = i64::from(p.y) * tile + OFFSET_Y as i64 + (k / spill.width) as i64;
            if px[3] != 0 && x >= 0 && y >= 0 {
                out.push((y / tile) as usize * width + (x / tile) as usize);
            }
        }
    }
    out.sort_unstable();
    out.dedup();
    out
}

/// What `posed` draw past their cells, each a 24x32 drawing on its cell,
/// back to front: what [`crate::layers::draw`] paints into the map once.
pub fn spills(posed: &[Posed], width: usize) -> Vec<(usize, Picture)> {
    let mut out: Vec<&Posed> = posed.iter().filter(|p| p.spill.is_some()).collect();
    out.sort_by_key(|p| order(p));
    out.iter()
        .map(|p| {
            (
                p.y as usize * width + p.x as usize,
                p.spill.clone().expect("it spills"),
            )
        })
        .collect()
}

/// `frame` drawn standing on cell `at` of a map `width` cells wide, over
/// `picture`; only inside `clip`, a cell, if there is one.
fn paint(
    picture: &mut Picture,
    width: usize,
    at: (i64, i64),
    frame: &Picture,
    clip: Option<usize>,
) {
    let tile = TILE as i64;
    let (x0, y0) = (at.0 * tile + OFFSET_X as i64, at.1 * tile + OFFSET_Y as i64);
    let clip = clip.map(|c| ((c % width) as i64 * tile, (c / width) as i64 * tile));
    for py in 0..frame.height {
        for px in 0..frame.width {
            let from = (py * frame.width + px) * 4;
            if frame.rgba[from + 3] == 0 {
                continue;
            }
            let (x, y) = (x0 + px as i64, y0 + py as i64);
            if let Some((cx, cy)) = clip {
                if !(cx..cx + tile).contains(&x) || !(cy..cy + tile).contains(&y) {
                    continue;
                }
            }
            if x < 0 || y < 0 || x >= picture.width as i64 || y >= picture.height as i64 {
                continue;
            }
            let to = (y as usize * picture.width + x as usize) * 4;
            picture.rgba[to..to + 4].copy_from_slice(&frame.rgba[from..from + 4]);
        }
    }
}

/// Every drawing of the lower layer.
fn lower_drawings(layers: &mut Layers) -> impl Iterator<Item = &mut Picture> {
    std::iter::once(&mut layers.lower)
        .chain(layers.variants.iter_mut().flat_map(|(_, d)| d.iter_mut()))
}

/// Paints each cell's drawings over its cell of the extension, from
/// `first`, in every drawing of the lower layer: what
/// [`crate::layers::draw`] calls.
pub fn compose(layers: &mut Layers, width: usize, first: usize, posed: &[Cell]) {
    for picture in lower_drawings(layers) {
        for (k, (_, stack)) in posed.iter().enumerate() {
            let cell = first + k;
            let (x, y) = ((cell % width) as i64, (cell / width) as i64);
            for ((dx, dy), frame) in stack {
                paint(
                    picture,
                    width,
                    (x + i64::from(*dx), y + i64::from(*dy)),
                    frame,
                    Some(cell),
                );
            }
        }
    }
}

/// Paints what the still events draw past their cells into the map, in
/// every drawing of the lower layer: see [`spills`].
pub fn compose_spills(layers: &mut Layers, width: usize, spills: &[(usize, Picture)]) {
    for picture in lower_drawings(layers) {
        for (at, frame) in spills {
            paint(
                picture,
                width,
                ((at % width) as i64, (at / width) as i64),
                frame,
                None,
            );
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

    /// A Blurred Line's chest, 1 px right and 2 px up of its cell: with 2
    /// pixels allowed it moves back, the smallest shift on each axis; with
    /// 1 it does not fit, and one that fits is not moved.
    #[test]
    fn a_pose_past_its_cell_is_moved_back_by_the_least_it_needs() {
        let chest = frame(&[(5, 14), (20, 28)]);
        assert_eq!(shift_into_the_cell(&[&chest], 2), Some((-1, 2)));
        assert_eq!(shift_into_the_cell(&[&chest], 3), Some((-1, 2)));
        assert_eq!(shift_into_the_cell(&[&chest], 1), None);
        let inside = frame(&[(4, 16), (19, 31)]);
        assert_eq!(shift_into_the_cell(&[&inside], 3), Some((0, 0)));
        assert_eq!(shift_into_the_cell(&[&frame(&[])], 0), Some((0, 0)));
        // Wider than the cell: no shift fits it, however many pixels.
        assert_eq!(
            shift_into_the_cell(&[&frame(&[(3, 20), (19, 20)])], 8),
            None
        );
        // And the drawing moves whole: nothing is lost.
        let moved = shifted(&chest, (-1, 2));
        assert!(inside_the_cell(&moved));
        let opaque = |p: &Picture| p.rgba.chunks(4).filter(|c| c[3] != 0).count();
        assert_eq!(opaque(&moved), 2);
        assert_eq!(moved.rgba[(16 * 24 + 4) * 4 + 3], 255);
    }

    /// The poses of one event share one shift: two that need different
    /// ones fit together if one shift puts both inside, and not if their
    /// drawings together are taller than the cell.
    #[test]
    fn the_poses_of_one_event_share_their_shift() {
        let up = frame(&[(8, 14), (8, 29)]);
        let down = frame(&[(8, 18), (8, 29)]);
        assert_eq!(shift_into_the_cell(&[&up], 2), Some((0, 2)));
        assert_eq!(shift_into_the_cell(&[&down], 2), Some((0, 0)));
        assert_eq!(shift_into_the_cell(&[&up, &down], 2), Some((0, 2)));
        let low = frame(&[(8, 17), (8, 31)]);
        let high = frame(&[(8, 14)]);
        assert_eq!(shift_into_the_cell(&[&high], 2), Some((0, 2)));
        assert_eq!(shift_into_the_cell(&[&low], 2), Some((0, 0)));
        // Together they are 18 pixels tall: no shift fits them.
        assert_eq!(shift_into_the_cell(&[&high, &low], 2), None);
    }

    /// What a seated person at (3, 2) draws past its cell —its head, on
    /// (3, 1)— is under whoever RM2k draws behind it there: anyone on the
    /// row above, the hero on its own cell, an event of a lower id on it.
    /// Not the one to its right, nor a later event on its cell; and the one
    /// to its left is let through.
    #[test]
    fn who_stands_behind_a_head_drawn_past_its_cell() {
        let width = 8;
        let at = |x: usize, y: usize| y * width + x;
        // Two pixels of its head, on the left and the right of the cell above.
        let head = [(48, 20), (63, 20)];
        let me = (3, 2, LAYER_SAME, 10);
        let same = [LAYER_SAME];
        // The row above: right over it and beside it.
        assert!(covers(at(3, 1), false, &head, width, me, &same, None));
        assert!(covers(at(2, 1), false, &head, width, me, &same, None));
        assert!(covers(at(4, 1), false, &head, width, me, &same, None));
        // Two cells off, its sprite does not reach the head.
        assert!(!covers(at(5, 1), false, &head, width, me, &same, None));
        // Its own row: to its right in front, to its left let through.
        assert!(!covers(at(4, 2), false, &head, width, me, &same, None));
        assert!(!covers(at(2, 2), false, &head, width, me, &same, None));
        // Its own cell: the hero and an earlier event behind it, a later
        // event in front.
        assert!(covers(at(3, 2), false, &head, width, me, &same, None));
        assert!(covers(at(3, 2), false, &head, width, me, &same, Some(9)));
        assert!(!covers(at(3, 2), false, &head, width, me, &same, Some(11)));
        // The row below is in front; risen in a jump, 16 px higher, still.
        assert!(!covers(at(3, 3), true, &head, width, me, &same, None));
        // One on the layer below is behind it wherever it is.
        assert!(covers(
            at(2, 2),
            false,
            &head,
            width,
            me,
            &[LAYER_BELOW],
            None
        ));
    }

    /// The cell of one whose neighbour below draws its head onto it carries
    /// the head over its pose; the neighbour above's spill goes under it.
    #[test]
    fn what_others_draw_onto_a_cell_is_stacked_in_rm2k_order() {
        let posed = |id: i32, y: i32, spill: Option<Picture>| Posed {
            event: id as usize,
            id,
            x: 1,
            y,
            graphics: vec![("p".into(), 0)],
            poses: vec![(0, 0, frame(&[(10, 20)]))],
            start: Some((0, 0)),
            shift: (0, 0),
            layer: LAYER_SAME,
            spill,
            relies: BTreeSet::new(),
        };
        // Both draw their heads on the row above.
        let head = frame(&[(10, 5)]);
        let set = [posed(1, 1, Some(head.clone())), posed(2, 2, Some(head))];
        let cells = cells(&set, 4);
        assert_eq!(cells.len(), 2);
        // The first one's cell: its pose, then the second one's head.
        let (at, stack) = &cells[0];
        assert_eq!(*at, 5);
        assert_eq!(
            stack.iter().map(|(d, _)| *d).collect::<Vec<_>>(),
            [(0, 0), (0, 1)]
        );
        // The second one's: nothing lands on it but its pose.
        assert_eq!(cells[1].1.len(), 1);
        // And the spills, back to front, at their cells.
        let spills = spills(&set, 4);
        assert_eq!(spills.iter().map(|(at, _)| *at).collect::<Vec<_>>(), [5, 9]);
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
            shift: (0, 0),
            layer: LAYER_SAME,
            spill: None,
            relies: BTreeSet::new(),
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
            shift: (0, 0),
            layer: LAYER_SAME,
            spill: None,
            relies: BTreeSet::new(),
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
        compose(&mut layers, 2, 2, &[(0, vec![((0, 0), f)])]);
        let at = |x: usize, y: usize| layers.lower.rgba[(y * 32 + x) * 4];
        assert_eq!(at(0, 16), 200);
        assert_eq!(at(1, 16), 7);
        assert_eq!(at(0, 0), 7);
    }
}
