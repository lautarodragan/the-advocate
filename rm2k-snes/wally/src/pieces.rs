//! The still pieces of a painted map: the events that always show one
//! look, painted into a panorama fixed to the map, and drawn as no object.
//!
//! A game drawn as a painting —RM2k's "parallax mapping"— puts its map in
//! the panorama and builds what stands on it out of events: a wall, a roof,
//! a window, each a CharSet's pose in a cell, hundreds on a town. As
//! objects they cost the console a 32x32 sprite each, four slivers of the
//! 34 a line holds, a slot in the cache and a pass of the sprite placing
//! every frame. Here, when the project asks for it on a map —`painted_events`
//! in the request—, the ones that never change are painted into the
//! panorama in the order RM2k draws them, with the ChipSet's layers folded
//! in, and the map is one picture: a [painted map](crate::background) if it
//! is larger than the screen.
//!
//! **Which ones** ([`select`]): every page draws the same CharSet pose on the
//! same layer; nothing moves it —no move type, no route, nobody names it,
//! none of what its pages reach names "this event"—, nothing animates it in
//! place or turns it toward the hero; the first page asks for nothing, so
//! some page always holds; and nothing it reaches erases it. A `CallEvent`
//! counts only by what it reaches: the common event or the map event's page
//! it calls, and theirs in turn, so a page that calls the message box does
//! not keep its piece an object. A call by a variable reaches anything.
//!
//! **What is kept**: the event keeps its pages —they run, block and
//! trigger, as one that draws nothing—, and one that has nothing else —one
//! page, no commands, no conditions, nobody names it— stops being an event,
//! as a decorative one does ([`Piece::gone`]).
//!
//! **What goes in front of the hero**: what RM2k would draw over a
//! character. A piece above the hero, whole; one on his layer, the pixels
//! it draws past its cell onto a cell above it, or to its left on its row,
//! where someone can stand; the ChipSet's layer above, but on the cells no
//! character can ever cover. The painted map puts those in front by its
//! cells' priority and BG2's tiles: see `map_pictures::raise` and
//! `Way::Painted`.
//!
//! What is lost: a character beside a piece, on its row, is drawn under the
//! piece's top half where RM2k draws the one to the right over it; and what
//! goes in front does so by the painted map's grain, 8x8 cells and the edge
//! tiles there is room for.

use crate::events::{unbaked, Event, BAKED_SUFFIX, LAYER_SAME};
use crate::fail::Result;
use crate::moves::ScannedPage;
use crate::sheets::Drawer;
use crate::sprites::npc::Npc;
use crate::sprites::split::TILE_PREFIX;
use rm2k_render::{Layers, Picture};
use rm2k_rules::charset::{character_origin, OFFSET_X, OFFSET_Y, POSE_HEIGHT, POSE_WIDTH};
use rm2k_rules::chipset::TILE;
use rm2k_rules::event::TRANSLUCENT_OPACITY;
use rm2k_rules::reach::Standing;
use std::collections::{BTreeMap, BTreeSet};

/// The layer above the hero.
pub const LAYER_ABOVE: i32 = 2;
/// `EraseEvent` and `CallEvent`, liblcf's codes.
const ERASE_EVENT: i32 = 12320;
const CALL_EVENT: i32 = 12330;
/// A `CallEvent`'s kinds: a common event by its id, a map event's page by
/// their ids. Any other —by variables— can reach anything.
const CALL_COMMON: i32 = 0;
const CALL_MAP_EVENT: i32 = 1;
/// "This event", in the commands that name one.
const THIS_EVENT: i32 = 10005;

/// One piece, ready to paint.
#[derive(Clone, Debug)]
pub struct Piece {
    /// Its index in the map's table, or `None` for one the RAM's trim left
    /// out of it, which only the painting draws.
    pub event: Option<usize>,
    pub id: i32,
    pub x: i64,
    pub y: i64,
    pub layer: i32,
    /// Its pose, 24x32.
    pub frame: Picture,
    pub translucent: bool,
    /// One flag per pixel of `frame`: in front of the hero.
    pub front: Vec<bool>,
    /// Whether it stops being an event: nothing but its looks.
    pub gone: bool,
}

impl Piece {
    /// Whether it closes its cell: an event on the hero's layer does. Only
    /// asked of the ones that stop being events, whose pages do not say it
    /// any more.
    pub fn blocks(&self) -> bool {
        self.layer == LAYER_SAME
    }
}

/// The map's common events' commands, by id: what a `CallEvent` reaches.
pub type Commons = BTreeMap<i32, Vec<(i32, Vec<i32>)>>;

/// What running event `e`'s pages can reach: their own commands, and those
/// of every common event and map event page a call among them reaches, and
/// theirs. `None` if a call by a variable reaches what nobody can say.
fn reached<'a>(
    events: &'a [Event],
    e: usize,
    commons: &'a Commons,
) -> Option<Vec<&'a (i32, Vec<i32>)>> {
    let mut out: Vec<&(i32, Vec<i32>)> = Vec::new();
    let mut seen_common: BTreeSet<i32> = BTreeSet::new();
    let mut seen_page: BTreeSet<(i32, i32)> = BTreeSet::new();
    let mut todo: Vec<&[(i32, Vec<i32>)]> = events[e]
        .pages
        .iter()
        .map(|p| p.commands.as_slice())
        .collect();
    while let Some(commands) = todo.pop() {
        for command in commands {
            out.push(command);
            let (code, params) = command;
            if *code != CALL_EVENT {
                continue;
            }
            match (params.first().copied(), params.get(1).copied()) {
                (Some(CALL_COMMON), Some(id)) => {
                    if seen_common.insert(id) {
                        if let Some(c) = commons.get(&id) {
                            todo.push(c);
                        }
                    }
                }
                (Some(CALL_MAP_EVENT), Some(id)) => {
                    let page = params.get(2).copied().unwrap_or(1);
                    if !seen_page.insert((id, page)) {
                        continue;
                    }
                    // An `EraseEvent` there erases the event called, not the
                    // caller —easyrpg's `GetThisEventId` is the frame's—; it
                    // is counted anyway, so a runtime that erases the caller
                    // keeps it right. "This event" is the caller; RM2k
                    // numbers pages from 1.
                    let target = if id == THIS_EVENT { events[e].id } else { id };
                    let found = events
                        .iter()
                        .find(|ev| ev.id == target)
                        .and_then(|ev| ev.pages.get((page - 1).max(0) as usize));
                    if let Some(p) = found {
                        todo.push(&p.commands);
                    }
                }
                _ => return None,
            }
        }
    }
    Some(out)
}

/// What the request gives the choice.
pub struct Wants<'a> {
    pub pages: &'a [ScannedPage],
    /// The ids the map's pages, the common events and the test pages name.
    pub named: &'a BTreeSet<i32>,
    /// Events someone else sends walking, by index.
    pub also_walk: &'a BTreeSet<usize>,
    pub commons: &'a Commons,
    /// Where each character's feet can be; `None`, anywhere.
    pub standing: Option<&'a [Standing]>,
    /// The map's size, in cells.
    pub size: (usize, usize),
}

/// Why event `npc` is no piece, or `None` if it is one.
fn why_not(events: &[Event], npc: &Npc, wants: &Wants) -> Option<&'static str> {
    let e = npc.event;
    let event = &events[e];
    let reaches = reached(events, e, wants.commons);
    let names_itself = |list: &[&(i32, Vec<i32>)]| {
        list.iter()
            .any(|(code, params)| crate::decor::names(*code, params).contains(&THIS_EVENT))
    };
    if event.pages.iter().any(|p| p.move_type != 0 || p.own_route)
        || wants.also_walk.contains(&e)
        || wants.named.contains(&event.id)
        || wants
            .pages
            .iter()
            .any(|p| p.compiles && p.route_targets.contains(&e))
        || reaches.as_deref().is_some_and(names_itself)
    {
        return Some("something moves it");
    }
    if npc.animates || event.pages.iter().any(|p| matches!(p.animation, 1 | 3 | 5)) {
        return Some("it animates standing still");
    }
    if !npc.visible
        || npc.graphics.iter().any(|g| g != &npc.graphics[0])
        || npc.graphics[0].is_none()
        || npc.layers.iter().any(|&l| l != npc.layers[0])
    {
        return Some("its pages change its look");
    }
    let Some(reaches) = reaches else {
        return Some("a call by a variable can erase it");
    };
    if event.pages.first().is_none_or(|p| !p.conditions.is_empty())
        || reaches.iter().any(|(code, _)| *code == ERASE_EVENT)
    {
        return Some("it can go away");
    }
    if wants
        .pages
        .iter()
        .any(|p| p.event == e && p.compiles && p.turns && matches!(p.trigger, 0..=2))
    {
        return Some("it turns toward the hero");
    }
    if unbaked(&npc.graphics[0].as_ref()?.0).starts_with(TILE_PREFIX) {
        return Some("it is drawn with a ChipSet tile");
    }
    None
}

/// Whether pixel `(x, y)` of a 24x32 pose is inside its 16x16 cell.
fn in_cell(x: usize, y: usize) -> bool {
    let (left, top) = (-OFFSET_X as usize, -OFFSET_Y as usize);
    (left..left + TILE as usize).contains(&x) && (top..top + TILE as usize).contains(&y)
}

/// The pieces among `npcs`, in the order RM2k draws them —layer, then y, x
/// and id—, and why each other one is not, by reason, as ids. `trimmed`:
/// they are events the RAM's trim left out, with no row nor pages.
pub fn select(
    drawer: &mut Drawer,
    events: &[Event],
    npcs: &[Npc],
    wants: &Wants,
    trimmed: bool,
) -> Result<(Vec<Piece>, BTreeMap<&'static str, Vec<i32>>)> {
    let mut out = Vec::new();
    let mut not: BTreeMap<&'static str, Vec<i32>> = BTreeMap::new();
    let standable: Option<BTreeSet<usize>> = wants.standing.map(|s| {
        s.iter()
            .flat_map(|s| s.cells.iter().chain(s.risen.iter()).copied())
            .collect()
    });
    let (width, height) = wants.size;
    for npc in npcs {
        let event = &events[npc.event];
        if let Some(why) = why_not(events, npc, wants) {
            not.entry(why).or_default().push(event.id);
            continue;
        }
        let Some((name, index, pose)) = npc.graphics[0].clone() else {
            continue;
        };
        let translucent = name.contains(&format!("{BAKED_SUFFIX}:"));
        let base = if translucent {
            unbaked(&name).to_string()
        } else {
            name.clone()
        };
        let Some(sheet) = drawer.draw(&base)? else {
            not.entry("its CharSet is missing")
                .or_default()
                .push(event.id);
            continue;
        };
        let (ox, oy) = character_origin(index);
        let frame = sheet.crop(
            (ox + pose % 3 * POSE_WIDTH) as i64,
            (oy + pose / 3 * POSE_HEIGHT) as i64,
            POSE_WIDTH as usize,
            POSE_HEIGHT as usize,
        );
        let layer = npc.layers[0];
        let mut front = vec![false; frame.width * frame.height];
        for (k, f) in front.iter_mut().enumerate() {
            if frame.rgba[k * 4 + 3] == 0 {
                continue;
            }
            if layer == LAYER_ABOVE {
                *f = true;
                continue;
            }
            let (px, py) = (k % frame.width, k / frame.width);
            if layer != LAYER_SAME || in_cell(px, py) {
                continue;
            }
            // A pixel past its cell, on a cell of the map: RM2k draws a
            // character standing on a cell above the piece's row, or on its
            // row to its left, before the piece, so under that pixel.
            let mx = i64::from(npc.x) * TILE as i64 + OFFSET_X as i64 + px as i64;
            let my = i64::from(npc.y) * TILE as i64 + OFFSET_Y as i64 + py as i64;
            if mx < 0 || my < 0 || mx >= (width * 16) as i64 || my >= (height * 16) as i64 {
                continue;
            }
            let (cx, cy) = (mx / 16, my / 16);
            let behind = cy < i64::from(npc.y) || (cy == i64::from(npc.y) && cx < i64::from(npc.x));
            let cell = cy as usize * width + cx as usize;
            if behind && standable.as_ref().is_none_or(|s| s.contains(&cell)) {
                *f = true;
            }
        }
        let gone = !trimmed
            && event.pages.len() == 1
            && event.pages[0].commands.is_empty()
            && event.pages[0].conditions.is_empty();
        out.push(Piece {
            event: (!trimmed).then_some(npc.event),
            id: event.id,
            x: i64::from(npc.x),
            y: i64::from(npc.y),
            layer,
            frame,
            translucent,
            front,
            gone,
        });
    }
    out.sort_by_key(|p| (p.layer, p.y, p.x, p.id));
    Ok((out, not))
}

/// `p` painted on `picture`, a picture of the map; what it puts in front of
/// the hero marked in `front`, one flag per pixel of the map.
fn paint(picture: &mut Picture, p: &Piece, front: &mut [bool]) {
    let alpha = TRANSLUCENT_OPACITY as u32;
    let (x0, y0) = (
        p.x * TILE as i64 + OFFSET_X as i64,
        p.y * TILE as i64 + OFFSET_Y as i64,
    );
    for py in 0..p.frame.height {
        for px in 0..p.frame.width {
            let (x, y) = (x0 + px as i64, y0 + py as i64);
            if x < 0 || y < 0 || x >= picture.width as i64 || y >= picture.height as i64 {
                continue;
            }
            let at = (py * p.frame.width + px) * 4;
            if p.frame.rgba[at + 3] == 0 {
                continue;
            }
            let to = (y as usize * picture.width + x as usize) * 4;
            if p.translucent {
                for c in 0..3 {
                    let (o, u) = (p.frame.rgba[at + c] as u32, picture.rgba[to + c] as u32);
                    picture.rgba[to + c] = ((o * alpha + u * (255 - alpha)) / 255) as u8;
                }
            } else {
                picture.rgba[to..to + 3].copy_from_slice(&p.frame.rgba[at..at + 3]);
                // A translucent one in front would show the hero through
                // it: it stays behind him.
                if p.front[py * p.frame.width + px] {
                    front[y as usize * picture.width + x as usize] = true;
                }
            }
        }
    }
}

/// The map as one picture: its panorama `whole` —of the map's size, fixed to
/// it— with the ChipSet's layers and the pieces over it in RM2k's order:
/// the lower layer, the pieces below and with the hero, the upper layer,
/// the pieces above. The layers are left empty: everything is in the
/// panorama. Answers what goes in front of the hero, one flag per pixel of
/// the map, or `None` if nothing does; `never_covered` are the cells no
/// character can ever cover, by index, whose layer above stays behind.
pub fn fold(
    whole: &mut Picture,
    layers: &mut Layers,
    pieces: &[Piece],
    width: usize,
    never_covered: &BTreeSet<usize>,
) -> Option<Vec<bool>> {
    let (w, h) = (whole.width, whole.height);
    let mut front = vec![false; w * h];
    // RM2k gives a panorama no colour key: it is opaque.
    for px in whole.rgba.chunks_mut(4) {
        px[3] = 255;
    }
    let over = |whole: &mut Picture, from: &Picture, front: Option<&mut Vec<bool>>| {
        let mut front = front;
        for (k, px) in from.rgba.chunks(4).enumerate().take(w * h) {
            if px[3] == 0 {
                continue;
            }
            whole.rgba[k * 4..k * 4 + 4].copy_from_slice(&[px[0], px[1], px[2], 255]);
            let cell = (k / w / 16) * width + (k % w) / 16;
            if let Some(f) = front.as_deref_mut() {
                if !never_covered.contains(&cell) {
                    f[k] = true;
                }
            }
        }
    };
    over(whole, &layers.lower, None);
    for piece in pieces.iter().filter(|p| p.layer != LAYER_ABOVE) {
        paint(whole, piece, &mut front);
    }
    over(whole, &layers.upper, Some(&mut front));
    for piece in pieces.iter().filter(|p| p.layer == LAYER_ABOVE) {
        paint(whole, piece, &mut front);
    }
    layers.lower = Picture::transparent(layers.lower.width, layers.lower.height);
    layers.upper = Picture::transparent(layers.upper.width, layers.upper.height);
    front.iter().any(|&f| f).then_some(front)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::Page;

    fn page(commands: Vec<(i32, Vec<i32>)>) -> Page {
        Page {
            name: "Town".into(),
            index: 0,
            pose: 1,
            layer: LAYER_SAME,
            speed: 3,
            animation: 0,
            move_type: 0,
            own_route: false,
            translucent: false,
            conditions: Vec::new(),
            commands,
        }
    }

    fn event(id: i32, pages: Vec<Page>) -> Event {
        Event {
            id,
            x: 0,
            y: 0,
            pages,
        }
    }

    #[test]
    fn a_call_erases_only_if_what_it_reaches_erases() {
        let erases = |events: &[Event], commons: &Commons| {
            reached(events, 0, commons).map(|r| r.iter().any(|(c, _)| *c == ERASE_EVENT))
        };
        let commons: Commons = BTreeMap::from([
            (2, vec![(11110, vec![1])]),
            (3, vec![(CALL_EVENT, vec![CALL_COMMON, 4, 0])]),
            (4, vec![(ERASE_EVENT, vec![])]),
        ]);
        // The message box's common event: nothing erases.
        let box_only = [event(
            1,
            vec![page(vec![(CALL_EVENT, vec![CALL_COMMON, 2, 0])])],
        )];
        assert_eq!(erases(&box_only, &commons), Some(false));
        // One that calls one that calls one that erases.
        let through = [event(
            1,
            vec![page(vec![(CALL_EVENT, vec![CALL_COMMON, 3, 0])])],
        )];
        assert_eq!(erases(&through, &commons), Some(true));
        // Another event's page that erases.
        let other = [
            event(
                1,
                vec![page(vec![(CALL_EVENT, vec![CALL_MAP_EVENT, 2, 1])])],
            ),
            event(2, vec![page(vec![(ERASE_EVENT, vec![])])]),
        ];
        assert_eq!(erases(&other, &commons), Some(true));
        // By a variable: anything.
        let variable = [event(1, vec![page(vec![(CALL_EVENT, vec![2, 5, 6])])])];
        assert_eq!(erases(&variable, &commons), None);
        // A common event that calls itself ends.
        let looping: Commons = BTreeMap::from([(7, vec![(CALL_EVENT, vec![CALL_COMMON, 7, 0])])]);
        let calls = [event(
            1,
            vec![page(vec![(CALL_EVENT, vec![CALL_COMMON, 7, 0])])],
        )];
        assert_eq!(erases(&calls, &looping), Some(false));
    }
}
