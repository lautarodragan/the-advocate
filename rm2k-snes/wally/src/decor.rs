//! The decorative events: the ones that are only a drawing, painted into the
//! background and gone as events.
//!
//! An event is decorative if nothing about it is anything but its looks: one
//! page, no commands, no conditions, a CharSet, no way of moving —no move
//! type, no route— and **nobody names it**: no command of the map's pages, of
//! the common events or of a test page moves it, places it, flashes it, asks
//! where it looks, draws an animation on it. What is left is a picture that
//! sits in a cell.
//!
//! It is drawn into the map's lower layer —every drawing of the layer's
//! animation— over what is there, in the order RM2k stacks events (layer,
//! then y, x and id), blended at RM2k's opacity if the page is translucent.
//! One that animates in place goes with **the water family**: RM2k walks a
//! character's three columns in the cycle 0, 1, 2, 1, which is the water
//! autotiles' cycle, so drawing `d` of the family shows column `d`. Their
//! pace is the family's and not the event's speed.
//!
//! Two kinds are left as they were. A page above the hero would go in the
//! upper layer, which has no drawings to animate and whose colours are
//! decided apart. And one on the hero's own layer whose pose leaves its
//! cell would be drawn behind a hero standing in front of it —the hero
//! would walk over the head of what stands in the cell below him—: only the
//! ones that stay inside their 16x16 are baked. An event on the hero's layer
//! blocks, and that moves to the map's passability: [`Decoration::blocks`].

use crate::events::{unbaked, Event, BAKED_SUFFIX, LAYER_BELOW, LAYER_SAME};
use crate::fail::Result;
use crate::sheets::Drawer;
use crate::sprites::split::DITHER_SUFFIX;
use rm2k_render::{Family, Layers, Picture};
use rm2k_rules::charset::{character_origin, OFFSET_X, OFFSET_Y, POSE_HEIGHT, POSE_WIDTH};
use rm2k_rules::chipset::TILE;
use rm2k_rules::event::TRANSLUCENT_OPACITY;
use std::collections::{BTreeMap, BTreeSet};

/// `ShowBattleAnimation`, `ChangeEventLocation`, `TradeEventLocations`,
/// `FlashSprite`, `MoveEvent` and `ConditionalBranch`, liblcf's codes: the
/// commands that name an event.
const SHOW_BATTLE_ANIMATION: i32 = 11210;
const CHANGE_EVENT_LOCATION: i32 = 10860;
const TRADE_EVENT_LOCATIONS: i32 = 10870;
const FLASH_SPRITE: i32 = 11320;
const MOVE_EVENT: i32 = 11330;
const COND_BRANCH: i32 = 12010;
/// A `ConditionalBranch` of the kind that asks where an event looks.
const BRANCH_EVENT_FACING: i32 = 6;

/// The event ids a command names, if it names any.
pub fn names(code: i32, parameters: &[i32]) -> Vec<i32> {
    let at = |i: usize| parameters.get(i).copied();
    match code {
        SHOW_BATTLE_ANIMATION => at(1).into_iter().collect(),
        FLASH_SPRITE | MOVE_EVENT | CHANGE_EVENT_LOCATION => at(0).into_iter().collect(),
        TRADE_EVENT_LOCATIONS => parameters.iter().take(2).copied().collect(),
        COND_BRANCH if at(0) == Some(BRANCH_EVENT_FACING) => at(1).into_iter().collect(),
        _ => Vec::new(),
    }
}

/// The ids named by the map's pages, the common events —which a
/// `CallEvent` brings into any map— and the test pages that run here.
pub fn named(events: &[Event], common: &[(i32, Vec<i32>)], tests: &[(i32, Vec<i32>)]) -> BTreeSet<i32> {
    let own = events.iter().flat_map(|e| &e.pages).flat_map(|p| p.commands.iter());
    own.chain(common).chain(tests).flat_map(|(code, parameters)| names(*code, parameters)).collect()
}

/// One decorative event, ready to paint.
#[derive(Clone, Debug)]
pub struct Decoration {
    /// Its index in the map's table, and its RM2k id.
    pub event: usize,
    pub id: i32,
    /// Its cell and its layer: 0 below the hero, 1 with him.
    pub x: i64,
    pub y: i64,
    pub layer: i32,
    /// Its poses of 24x32: one if it does not animate, the three columns if
    /// it does.
    pub frames: Vec<Picture>,
    pub translucent: bool,
    /// The CharSet it is cut from: what the colours it brings are grouped by.
    pub sheet: String,
    /// What a translucent one is drawn with when blending does not fit: its
    /// poses dithered, as a sprite would be.
    pub dithered: Option<Vec<Picture>>,
}

impl Decoration {
    /// Whether it closes its cell to the hero and to everybody else: an
    /// event on the hero's layer does.
    pub fn blocks(&self) -> bool {
        self.layer == LAYER_SAME
    }

    /// The same event with its translucency done as a dither, which draws
    /// nothing new: the water and the ground's own colours.
    pub fn dithered(&self) -> Decoration {
        match &self.dithered {
            Some(frames) => Decoration { frames: frames.clone(), translucent: false, ..self.clone() },
            None => self.clone(),
        }
    }

    pub fn animated(&self) -> bool {
        self.frames.len() > 1
    }
}

/// What of the request the choice reads.
pub struct Wants<'a> {
    pub named: &'a BTreeSet<i32>,
    /// Events someone else sends walking, by index.
    pub also_walk: &'a BTreeSet<usize>,
    /// Events already baked as tiles, by index.
    pub baked: &'a BTreeMap<usize, (usize, i32)>,
}

/// Whether every pixel a pose draws is inside the 16x16 of its cell.
fn inside_the_cell(frame: &Picture) -> bool {
    let (left, top) = (-OFFSET_X as usize, -OFFSET_Y as usize);
    let tile = TILE as usize;
    (0..frame.height).all(|y| {
        (0..frame.width).all(|x| {
            let inside = (left..left + tile).contains(&x) && (top..top + tile).contains(&y);
            inside || frame.rgba[(y * frame.width + x) * 4 + 3] == 0
        })
    })
}

/// The events of the map that are decorative, in the order they are drawn:
/// first by layer, then y, x and id, back to front.
pub fn select(drawer: &mut Drawer, events: &[Event], wants: &Wants) -> Result<Vec<Decoration>> {
    let mut out = Vec::new();
    for (number, event) in events.iter().enumerate() {
        let [page] = event.pages.as_slice() else { continue };
        if !page.commands.is_empty() || !page.conditions.is_empty() || page.move_type != 0 || page.own_route {
            continue;
        }
        // A CharSet: a tile keeps its own way, which imposes its passability.
        if page.name.is_empty() || page.name.starts_with(crate::sprites::split::TILE_PREFIX) {
            continue;
        }
        // Spin turns on its own.
        if page.animation == 5 || !matches!(page.layer, LAYER_BELOW | LAYER_SAME) {
            continue;
        }
        if wants.named.contains(&event.id) || wants.also_walk.contains(&number) || wants.baked.contains_key(&number) {
            continue;
        }
        let translucent = page.name.contains(&format!("{BAKED_SUFFIX}:"));
        let name = if translucent { unbaked(&page.name) } else { page.name.as_str() };
        let Some(sheet) = drawer.draw(name)? else { continue };
        let (ox, oy) = character_origin(page.index);
        let row = page.pose / 3;
        let dither_sheet = if translucent { drawer.draw(&format!("{name}{DITHER_SUFFIX}"))? } else { None };
        let columns: Vec<i32> = if matches!(page.animation, 1 | 3) { vec![0, 1, 2] } else { vec![page.pose % 3] };
        let frames: Vec<Picture> = columns
            .iter()
            .map(|c| sheet.crop((ox + c * POSE_WIDTH) as i64, (oy + row * POSE_HEIGHT) as i64, POSE_WIDTH as usize, POSE_HEIGHT as usize))
            .collect();
        let cut = |sheet: &Picture| -> Vec<Picture> {
            columns
                .iter()
                .map(|c| sheet.crop((ox + c * POSE_WIDTH) as i64, (oy + row * POSE_HEIGHT) as i64, POSE_WIDTH as usize, POSE_HEIGHT as usize))
                .collect()
        };
        let dithered = dither_sheet.as_ref().map(cut);
        if page.layer == LAYER_SAME && !frames.iter().all(inside_the_cell) {
            continue;
        }
        out.push(Decoration {
            event: number,
            id: event.id,
            x: event.x as i64,
            y: event.y as i64,
            layer: page.layer,
            frames,
            translucent,
            sheet: name.to_string(),
            dithered,
        });
    }
    out.sort_by_key(|d| (d.layer, d.y, d.x, d.id));
    Ok(out)
}

/// `frame` painted on `picture` at the cell of `d`.
fn paint(picture: &mut Picture, d: &Decoration, frame: &Picture) {
    let alpha = TRANSLUCENT_OPACITY as u32;
    let (x0, y0) = (d.x * TILE as i64 + OFFSET_X as i64, d.y * TILE as i64 + OFFSET_Y as i64);
    for py in 0..frame.height {
        let y = y0 + py as i64;
        if y < 0 || y >= picture.height as i64 {
            continue;
        }
        for px in 0..frame.width {
            let x = x0 + px as i64;
            if x < 0 || x >= picture.width as i64 {
                continue;
            }
            let at = (py * frame.width + px) * 4;
            if frame.rgba[at + 3] == 0 {
                continue;
            }
            let to = (y as usize * picture.width + x as usize) * 4;
            if d.translucent {
                for c in 0..3 {
                    let (over, under) = (frame.rgba[at + c] as u32, picture.rgba[to + c] as u32);
                    picture.rgba[to + c] = ((over * alpha + under * (255 - alpha)) / 255) as u8;
                }
                picture.rgba[to + 3] = 255;
            } else {
                picture.rgba[to..to + 4].copy_from_slice(&frame.rgba[at..at + 4]);
            }
        }
    }
}

/// Paints the decorations into every drawing of the lower layer. An animated
/// one joins the water family, which the layers get if the map has no water.
pub fn compose(layers: &mut Layers, decor: &[Decoration]) {
    if decor.is_empty() {
        return;
    }
    if decor.iter().any(Decoration::animated) && !layers.variants.iter().any(|(f, _)| *f == Family::Water) {
        let clean = vec![layers.lower.clone(); Family::Water.drawings() - 1];
        layers.variants.insert(0, (Family::Water, clean));
    }
    let each = |picture: &mut Picture, step: usize| {
        for d in decor.iter().filter(|d| d.layer == LAYER_BELOW || d.layer == LAYER_SAME) {
            let frame = if d.animated() { &d.frames[step] } else { &d.frames[0] };
            paint(picture, d, frame);
        }
    };
    each(&mut layers.lower, 0);
    for (family, drawings) in layers.variants.iter_mut() {
        for (i, picture) in drawings.iter_mut().enumerate() {
            each(picture, if *family == Family::Water { i + 1 } else { 0 });
        }
    }
}
