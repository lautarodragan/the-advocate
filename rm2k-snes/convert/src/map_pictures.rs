//! The `ShowPicture` pictures that are part of a map: the ones a game
//! paints its map with, which the cartridge draws into the map itself
//! instead of showing them as pictures.
//!
//! A game drawn as a painting —its map is a panorama the size of the map,
//! its ChipSet draws nothing— puts what RM2k would call the layer above the
//! hero, and its lights, shadows and mists, in pictures that stay where they
//! are for as long as one is on the map. Sunset Over Imdahl does it on 62
//! of its 65 maps. As a picture, each would be a big one: the map hidden,
//! and a mist at 95 % a black screen. As part of the map they cost nothing:
//! `wally` blends them into the map before converting it, and the opaque
//! ones —the roofs, cut out of the painting— go in front of the hero by the
//! priority of the cells they cover. Their `ShowPicture`s, `MovePicture`s
//! and `ErasePicture`s are then accepted without being done: the
//! conversion did them. The study, with what each group loses:
//! `ports/sunset-over-imdahl/research/2026-10-11-the-pictures-over-the-map.md` in the
//! book.
//!
//! **A project opts in**, `[graphics] map_pictures = true`: the same rule
//! on A Blurred Line takes its "meanwhile" card on 81 and the montage on 217
//! for parts of their maps, which they are not.
//!
//! What RM2k does that this reads:
//!
//! * **where it is seen**: a `Teleport` changes the map the rest of its page
//!   shows pictures on —the game shows the square's roofs in the door of the
//!   street, after the jump—;
//! * **where it lands**: one that goes with the map takes its place on the
//!   screen when it is shown and then moves with the map
//!   (`Game_Pictures::OnMapScrolled` in easyrpg), so its place on the map is
//!   the screen's plus RM2k's camera then. After a `Teleport` that camera is
//!   known —`Game_Player::GetDefaultPanX`: the hero nine cells from the left
//!   and seven from the top, clamped to the map—; on a map of one screen it
//!   never moves; otherwise it is not known, and the picture is centred on
//!   the map, which is where every one of Sunset's whose camera is known
//!   lands;
//! * **how it settles**: the `MovePicture`s that follow it in its page, if
//!   they leave it where it is and at its size, give the tone and the
//!   transparency it stays at;
//! * **whether it stays**: one its own page erases further on, from the
//!   show's branch or one further out, was part of a scene and not of the
//!   map. It is
//!   not drawn into it, and its commands are accepted without being done, as
//!   before: the scene loses it while it plays. Desert Nightmare's warehouse,
//!   map 21, opens on a piece of wall shown over its door and erased when the
//!   scene ends; drawn into the map, it stayed in front of the hero for good.

use crate::fail::{Result, Stop};
use crate::game::{Command, GameMap};
use rm2k_snes_events::codes::{
    COND_BRANCH, COND_ELSE, DEFEAT_HANDLER, ERASE_PICTURE, ESCAPE_HANDLER, MOVE_PICTURE,
    SHOW_CHOICE, SHOW_CHOICE_OPTION, SHOW_PICTURE, TELEPORT, VICTORY_HANDLER,
};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::{Path, PathBuf};

/// RM2k's screen, and where its camera puts the hero's cell from the
/// screen's corner: `Game_Player::GetDefaultPanX`.
const SCREEN: (i32, i32) = (320, 240);
const HERO: (i32, i32) = (9 * 16, 7 * 16);
const TILE: i32 = 16;
/// The largest picture the objects take: one that fits there is drawn as a
/// picture, as before. See `WIDTH_MAX` in [`crate::pictures`].
const SMALL: (i32, i32) = (
    crate::pictures::WIDTH_MAX as i32,
    crate::pictures::HEIGHT_MAX as i32,
);
/// The effects a picture can have and still be part of the map: none, or
/// the wave, which is not done —Sunset's sun rays wave at strength 1 and 95
/// % transparency—.
const EFFECT_NONE: i32 = 0;
const EFFECT_WAVE: i32 = 2;
/// How much of an opaque picture has to be its transparent colour for it
/// to be part of the map and not a card over it: Sunset's roofs leave 52 to
/// 99 % of themselves transparent; its test map's card, 0.
pub const OPAQUE_HOLES_MIN: f64 = 0.25;

/// One picture of a map, as `wally` draws it: see `map_pictures` in its
/// request.
#[derive(Clone, Debug, PartialEq)]
pub struct OnMap {
    pub number: i32,
    pub name: String,
    pub path: PathBuf,
    /// Its corner on the map, in pixels.
    pub corner: (i32, i32),
    /// The transparency and the tone it stays at: RM2k's 0 to 100, and
    /// `[red, green, blue, saturation]`.
    pub transparency: i32,
    pub tone: [i32; 4],
    pub transparent_color: bool,
    /// Whether it goes with the screen on a map that scrolls: a mist, which
    /// is repeated over the whole map so that it is wherever the camera goes.
    pub repeat: bool,
    /// Whether `path` is a file of this conversion's and not the game's:
    /// the part several drawings have in common —see [`Parts`]—. Wally is
    /// then given the file and not the name.
    pub derived: bool,
}

impl OnMap {
    pub fn to_json(&self) -> Value {
        let mut out = json!({
            "number": self.number,
            "name": self.name,
            "corner": [self.corner.0, self.corner.1],
            "transparency": self.transparency,
            "tone": self.tone,
            "transparent_color": self.transparent_color,
            "repeat": self.repeat,
        });
        if self.derived {
            out["path"] = json!(self.path.display().to_string());
        }
        out
    }
}

/// What the rule decided for the cartridge: each map's pictures, in the
/// order RM2k stacks them —by number—, and, by the map whose pages show
/// them, the names whose every `ShowPicture` there is one of them: those
/// the compiler is not given, so their commands are accepted without being
/// done.
#[derive(Clone, Debug, Default)]
pub struct MapPictures {
    pub per_map: BTreeMap<i32, Vec<OnMap>>,
    pub done_from: BTreeMap<i32, BTreeSet<String>>,
    /// The translucent big ones the rule could not take, which stay big
    /// pictures: shown over black, with the map hidden. For the
    /// degradations.
    pub hidden: Vec<Hidden>,
    /// By the map, the number and the name, lowercase, the file a
    /// drawing's `ShowPicture` shows instead of its own: what it has that
    /// the others do not. See [`Parts`]. By the number too: Desert
    /// Nightmare's shrine (161) shows the same ten digits under four
    /// numbers, one per wheel, each at its own place.
    pub parts: BTreeMap<(i32, i32, String), PathBuf>,
}

/// A translucent `ShowPicture` that is not part of its map and does not
/// fit the objects: the map the page is on, its event and cell, the
/// picture, its transparency, and why.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Hidden {
    pub map: i32,
    pub event: i32,
    pub at: (i32, i32),
    pub name: String,
    pub transparency: i32,
    pub why: &'static str,
}

impl MapPictures {
    /// The file `name` is shown from under `number` on `map`, if it is one
    /// of several drawings under that number: see [`Parts`]. Such a show is
    /// done, though its name is [`done`](Self::done) under another number.
    pub fn part(&self, map: i32, number: i32, name: &str) -> Option<&Path> {
        self.parts
            .get(&(map, number, name.to_lowercase()))
            .map(PathBuf::as_path)
    }

    pub fn of(&self, map: i32) -> &[OnMap] {
        self.per_map.get(&map).map_or(&[], Vec::as_slice)
    }

    /// Whether the compiler is not to be given `name` in `map`'s pages.
    pub fn done(&self, map: i32, name: &str) -> bool {
        self.done_from
            .get(&map)
            .is_some_and(|names| names.contains(&name.to_lowercase()))
    }
}

/// What the file of a picture says: its size and how much of it is the
/// transparent colour, index 0.
#[derive(Clone, Copy, Debug)]
struct File {
    size: (i32, i32),
    holes: f64,
}

/// How much of the picture at `path` is its transparent colour, index 0: 0
/// for one that is not indexed. See [`crate::pictures::still_over`] too.
pub fn holes(path: &Path) -> Result<f64> {
    Ok(read_file(path)?.holes)
}

fn read_file(path: &Path) -> Result<File> {
    let open = std::fs::File::open(path).map_err(|e| crate::fail::io(path, e))?;
    let decoder = png::Decoder::new(open);
    let mut reader = decoder
        .read_info()
        .map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let mut buf = vec![0; reader.output_buffer_size()];
    let frame = reader
        .next_frame(&mut buf)
        .map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let (w, h) = (frame.width as usize, frame.height as usize);
    // Only an indexed picture has an index 0; any other has no holes.
    let holes = if frame.color_type == png::ColorType::Indexed {
        let bits = frame.bit_depth as usize;
        let per_byte = 8 / bits;
        let mut zeros = 0usize;
        for row in buf[..frame.buffer_size()].chunks(frame.line_size) {
            for x in 0..w {
                let byte = row[x / per_byte];
                let shift = 8 - bits * (x % per_byte + 1);
                if (byte >> shift) & ((1 << bits) - 1) as u8 == 0 {
                    zeros += 1;
                }
            }
        }
        zeros as f64 / (w * h).max(1) as f64
    } else {
        0.0
    };
    Ok(File {
        size: (w as i32, h as i32),
        holes,
    })
}

/// One `ShowPicture`, where it is seen and how it settles.
#[derive(Clone, Debug)]
struct Shown {
    /// The map whose page shows it, and the map it is seen on.
    from: i32,
    seen: i32,
    /// The event whose page shows it, and its cell: where a loss is noted.
    event: i32,
    at: (i32, i32),
    number: i32,
    name: String,
    /// Its centre on the map, if RM2k's camera is known; or on the screen.
    on_map: bool,
    centre: Option<(i32, i32)>,
    zoom: i32,
    by_variable: bool,
    effect: i32,
    transparent_color: bool,
    transparency: i32,
    tone: [i32; 4],
    /// Where its `ShowPicture` puts it on the screen, and whether a
    /// `MovePicture` of its page takes it elsewhere or to another size.
    screen: (i32, i32),
    moves_place: bool,
    moves_size: bool,
    /// The branch its `ShowPicture` is in —see `walk`—, and whether its page
    /// erases it further on, in that branch or one further out.
    branch: Vec<usize>,
    erased: bool,
    /// Whether its page runs when the player asks —the action key, a
    /// touch— and not on its own: see [`Parts`].
    on_demand: bool,
}

/// RM2k's camera on `map` with the hero at cell `(x, y)`.
fn camera(size: (i32, i32), (x, y): (i32, i32)) -> (i32, i32) {
    let clamp = |hero: i32, centre: i32, map: i32, screen: i32| {
        (hero * TILE - centre).clamp(0, (map * TILE - screen).max(0))
    };
    (
        clamp(x, HERO.0, size.0, SCREEN.0),
        clamp(y, HERO.1, size.1, SCREEN.1),
    )
}

fn one_screen(size: (i32, i32)) -> bool {
    size.0 * TILE <= SCREEN.0 && size.1 * TILE <= SCREEN.1
}

/// Every `ShowPicture` of `maps`' pages, with the map it is seen on.
fn shown(maps: &[&GameMap]) -> Vec<Shown> {
    let sizes: HashMap<i32, (i32, i32)> =
        maps.iter().map(|m| (m.id, (m.width, m.height))).collect();
    let mut out = Vec::new();
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                let from = out.len();
                walk(
                    map.id,
                    (event.id, (event.x, event.y)),
                    &page.commands,
                    &sizes,
                    &mut out,
                );
                // Autostart and parallel run on their own; the rest, when
                // the player asks.
                for s in &mut out[from..] {
                    s.on_demand = page.trigger < 3;
                }
            }
        }
    }
    out
}

fn walk(
    from: i32,
    (event, at): (i32, (i32, i32)),
    commands: &[Command],
    sizes: &HashMap<i32, (i32, i32)>,
    out: &mut Vec<Shown>,
) {
    let mut seen = from;
    let mut cam = sizes.get(&from).filter(|s| one_screen(**s)).map(|_| (0, 0));
    // The page's last `ShowPicture` under each number, which its moves act on.
    let mut last: HashMap<i32, usize> = HashMap::new();
    // Where each branching command at an indent was seen from: each of its
    // branches starts there, and not where the one before it ended. Read in
    // a row, a choice's second branch moved the first one's pictures: the
    // statue's portal on Sunset over Imdahl's map 15 shows the spring
    // pictures after its teleport to map 13 and the summer branch moves
    // pictures 2 and 3 before its own, which took the spring ones out of
    // map 13 and left them big pictures over it, on 2026-10-16.
    let mut branched: HashMap<i32, (i32, Option<(i32, i32)>)> = HashMap::new();
    // Which branch a command is in: per indent outside its own, the last
    // command seen at that indent —the condition, the choice's option, the
    // else, the loop that opened it—. An erase reaches a show only from its
    // branch or one further out: one whose branch starts with the erase's.
    let mut heads: Vec<usize> = Vec::new();
    for (i, c) in commands.iter().enumerate() {
        let p = &c.parameters;
        let indent = usize::try_from(c.indent).unwrap_or(0);
        heads.truncate(indent);
        heads.resize(indent, usize::MAX);
        match c.code {
            SHOW_CHOICE | COND_BRANCH => {
                branched.insert(c.indent, (seen, cam));
            }
            SHOW_CHOICE_OPTION | COND_ELSE | VICTORY_HANDLER | ESCAPE_HANDLER | DEFEAT_HANDLER => {
                if let Some(&(s, k)) = branched.get(&c.indent) {
                    (seen, cam) = (s, k);
                }
                last.clear();
            }
            TELEPORT if p.len() >= 3 => {
                seen = p[0];
                cam = sizes.get(&seen).map(|&s| camera(s, (p[1], p[2])));
            }
            SHOW_PICTURE if p.len() >= 13 => {
                let on_map = p[4] != 0 || sizes.get(&seen).is_some_and(|s| one_screen(*s));
                let centre = if p[1] != 0 {
                    None
                } else if on_map {
                    let c0 = if p[4] != 0 { cam } else { Some((0, 0)) };
                    c0.map(|(cx, cy)| (p[2] + cx, p[3] + cy))
                } else {
                    Some((p[2], p[3]))
                };
                last.insert(p[0], out.len());
                out.push(Shown {
                    from,
                    seen,
                    event,
                    at,
                    number: p[0],
                    name: c.string.clone(),
                    on_map,
                    centre,
                    zoom: p[5],
                    by_variable: p[1] != 0,
                    effect: p[12],
                    transparent_color: p[7] != 0,
                    transparency: p[6],
                    tone: [p[8], p[9], p[10], p[11]],
                    screen: (p[2], p[3]),
                    moves_place: false,
                    moves_size: false,
                    branch: heads.clone(),
                    erased: false,
                    on_demand: false,
                });
            }
            ERASE_PICTURE if !p.is_empty() => {
                if let Some(&k) = last.get(&p[0]) {
                    if out[k].branch.starts_with(&heads) {
                        out[k].erased = true;
                    }
                }
            }
            MOVE_PICTURE if p.len() >= 12 => {
                if let Some(&k) = last.get(&p[0]) {
                    let s = &mut out[k];
                    // Also one that goes with the map: whether RM2k leaves
                    // it where it is depends on the engine's version
                    // (`ignore_position` in easyrpg's `Picture::Move`, only
                    // with `IsLegacy`), and a move that may not happen is
                    // not one to draw into the map.
                    s.moves_place |= p[1] != 0 || (p[2], p[3]) != s.screen;
                    s.moves_size |= p[5] != s.zoom;
                    s.transparency = p[6];
                    s.tone = [p[8], p[9], p[10], p[11]];
                }
            }
            _ => {}
        }
        heads.push(i);
    }
}

/// Whether a `ShowPicture` is part of its map, and if so where: its corner
/// and whether it repeats. If not, why, when it is a translucent one the
/// objects do not take —one that stays a big picture, over black, with the
/// map hidden—; `None` for the rest, which lose nothing by this rule.
fn placed(
    s: &Shown,
    file: &File,
    size: (i32, i32),
) -> std::result::Result<((i32, i32), bool), Option<&'static str>> {
    let fits_objects = file.size.0 <= SMALL.0 && file.size.1 <= SMALL.1;
    let opaque = s.transparency <= 0;
    let translucent = !opaque && s.transparency < 100;
    let hidden = |why| Err(translucent.then_some(why));
    if fits_objects || s.transparency >= 100 {
        return Err(None);
    }

    if s.by_variable {
        return hidden("its place is by a variable");
    }
    if s.zoom != 100 || s.moves_size {
        return hidden("it is zoomed");
    }
    if s.effect != EFFECT_NONE && s.effect != EFFECT_WAVE {
        return hidden("it rotates");
    }
    if opaque && (!s.transparent_color || file.holes < OPAQUE_HOLES_MIN) {
        return Err(None);
    }
    let half = (file.size.0 / 2, file.size.1 / 2);
    if s.on_map {
        if s.moves_place {
            return hidden("a MovePicture moves it");
        }
        let (cx, cy) = s.centre.unwrap_or((size.0 * TILE / 2, size.1 * TILE / 2));
        return Ok(((cx - half.0, cy - half.1), false));
    }
    // With the screen, on a map that scrolls: only something to see
    // through, a mist, and repeated. Where it drifts to is not done.
    if opaque {
        return Err(None);
    }
    // And not one a `MovePicture` moves: Desert Nightmare's game-over
    // text comes in from off the screen that way, on a map that scrolls,
    // and repeated it was drawn into the map six times over. None of
    // Sunset's mists is moved (measured on 2026-10-16).
    if s.moves_place {
        return hidden("a MovePicture moves it");
    }
    let Some((cx, cy)) = s.centre else {
        return hidden("its place is by a variable");
    };
    Ok(((cx - half.0, cy - half.1), true))
}

/// **Several drawings under one number of a map, at one place**: a menu
/// drawn whole once per option, each with its option lit. Desert
/// Nightmare's start menu, on map 1, is three 320x240 pictures under number
/// 1 —"With Intro", "No Intro" and "Quit", each with its own box lit— that
/// the arrows swap; drawn into the map as one, the arrows changed nothing
/// on the screen.
///
/// So what they have in common —each pixel as most of them have it— is
/// drawn into the map, and each `ShowPicture` shows, as a small picture,
/// only what its drawing has that the common part does not: its lit box.
/// The common part is a drawing of none of them where they all differ
/// —ten digits make a glyph of none—, which is seen only before the first
/// show; and every part covers all its drawing differs in, so the one up
/// is always whole.
/// That part goes with the map, where the common one is, and not with the
/// screen —which the console scales—: the compiler is told so by the
/// picture's `with_map` (see `pictures_of` in rm2k-snes-events).
///
/// Only when it can be done whole: every show of the number on the map one
/// of the drawings —none of them a scene's, which its own page erases: that
/// rule wins—, all opaque —a small picture is drawn so— and at the same
/// size and tone; and **every show from a page that runs on its own**,
/// autostart or parallel, as the menu's. A page the player starts shows a
/// screen on demand: Desert Nightmare's safe (115) and shrine (161) are
/// such, a lock's symbols shown when the lock is looked at and erased by
/// another page when it closes; split, their common part stayed in the
/// room for good, and the safe's parts did not fit the map's VRAM, so its
/// symbols were never seen. Otherwise the one shown most is drawn, as
/// before.
pub struct Parts {
    /// The common part, drawn into the map.
    pub common: OnMap,
    /// Each drawing's own, by its name in lowercase.
    pub own: Vec<(String, PathBuf)>,
}

impl Parts {
    pub fn of(map: i32, number: i32, drawings: &[&OnMap], out_dir: &Path) -> Result<Option<Parts>> {
        let first = drawings[0];
        let names: BTreeSet<String> = drawings.iter().map(|d| d.name.to_lowercase()).collect();
        if names.len() < 2
            || names.len() != drawings.len()
            || first.transparency != 0
            || drawings.iter().any(|d| {
                d.corner != first.corner
                    || d.transparency != first.transparency
                    || d.tone != first.tone
                    || d.transparent_color != first.transparent_color
                    || d.repeat
            })
        {
            return Ok(None);
        }
        let mut arts = Vec::new();
        for d in drawings {
            let read = if d.transparent_color {
                rm2k_render::picture::read_rm2k(&d.path)
            } else {
                rm2k_render::picture::read_unkeyed(&d.path)
            };
            let art = read.map_err(|e| Stop::new(format!("{}: {e}", d.path.display())))?;
            // Only whole pixels: one half seen through has no index.
            if art.rgba.chunks_exact(4).any(|p| p[3] != 0 && p[3] != 255) {
                return Ok(None);
            }
            arts.push(art);
        }
        let (w, h) = (arts[0].width, arts[0].height);
        if arts.iter().any(|a| (a.width, a.height) != (w, h)) {
            return Ok(None);
        }
        let pixel = |a: &rm2k_render::Picture, i: usize| -> [u8; 4] {
            let p = &a.rgba[i * 4..i * 4 + 4];
            if p[3] == 0 {
                [0; 4]
            } else {
                [p[0], p[1], p[2], 255]
            }
        };
        // Each pixel as most drawings have it; of equals, the first's. Not
        // only where all are the same: the menu's three pictures each have
        // a palette of their own, and its unlit boxes differ by a shade
        // from one to the next, so the parts took the three boxes whole,
        // 704 tiles, and the map had no room for them (measured on
        // 2026-11-20). What most have is the unlit box, and each part only
        // its lit one.
        let mut common = vec![[0u8; 4]; w * h];
        for (i, c) in common.iter_mut().enumerate() {
            let mut best = (0, pixel(&arts[0], i));
            for a in &arts {
                let p = pixel(a, i);
                let votes = arts.iter().filter(|b| pixel(b, i) == p).count();
                if votes > best.0 {
                    best = (votes, p);
                }
            }
            *c = best.1;
        }
        let mut own = Vec::new();
        let mut files = Vec::new();
        for a in &arts {
            let mut part = vec![[0u8; 4]; w * h];
            for (i, p) in part.iter_mut().enumerate() {
                let mine = pixel(a, i);
                if mine != common[i] {
                    // A hole where the common part has none: a picture over
                    // the map cannot open it.
                    if mine[3] == 0 {
                        return Ok(None);
                    }
                    *p = mine;
                }
            }
            // One the same as the common part shows nothing: the one before
            // it would stay up.
            if part.iter().all(|p| p[3] == 0) {
                return Ok(None);
            }
            files.push(part);
        }
        let dir = out_dir.join("map-pictures");
        std::fs::create_dir_all(&dir).map_err(|e| crate::fail::io(&dir, e))?;
        let common_path = dir.join(format!("map{map:04}-{number}.png"));
        if !write_indexed(&common_path, w, h, &common)? {
            return Ok(None);
        }
        for (k, (d, part)) in drawings.iter().zip(&files).enumerate() {
            let path = dir.join(format!("map{map:04}-{number}-{k}.png"));
            if !write_indexed(&path, w, h, part)? {
                return Ok(None);
            }
            own.push((d.name.to_lowercase(), path));
        }
        let joined: Vec<&str> = drawings.iter().map(|d| d.name.as_str()).collect();
        Ok(Some(Parts {
            common: OnMap {
                name: format!("what {} have in common", joined.join(", ")),
                path: common_path,
                transparent_color: true,
                derived: true,
                ..first.clone()
            },
            own,
        }))
    }
}

/// `pixels` as an indexed PNG with index 0 its transparent colour, as RM2k
/// reads a picture; false if they have more than 255 colours.
fn write_indexed(path: &Path, w: usize, h: usize, pixels: &[[u8; 4]]) -> Result<bool> {
    let mut colours: Vec<[u8; 3]> = Vec::new();
    let mut index: HashMap<[u8; 3], u8> = HashMap::new();
    let mut data = Vec::with_capacity(w * h);
    for p in pixels {
        if p[3] == 0 {
            data.push(0);
            continue;
        }
        let rgb = [p[0], p[1], p[2]];
        let k = match index.get(&rgb) {
            Some(&k) => k,
            None => {
                if colours.len() == 255 {
                    return Ok(false);
                }
                colours.push(rgb);
                let k = colours.len() as u8;
                index.insert(rgb, k);
                k
            }
        };
        data.push(k);
    }
    // Index 0 is a colour none of the others is, so nothing reads it as
    // one of them.
    let mut key = [255u8, 0, 255];
    while colours.contains(&key) {
        key[1] = key[1].wrapping_add(1);
    }
    let mut palette: Vec<u8> = key.to_vec();
    palette.extend(colours.iter().flatten());
    let file = std::fs::File::create(path).map_err(|e| crate::fail::io(path, e))?;
    let mut encoder = png::Encoder::new(std::io::BufWriter::new(file), w as u32, h as u32);
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_palette(palette);
    let stop = |e: png::EncodingError| Stop::new(format!("{}: {e}", path.display()));
    let mut writer = encoder.write_header().map_err(stop)?;
    writer.write_image_data(&data).map_err(stop)?;
    Ok(true)
}

/// The rule, over the cartridge's maps: see the module.
/// `out` is where the parts of the drawings that share a number are
/// written: see [`Parts`].
pub fn decide(maps: &[&GameMap], game_dir: &Path, out_dir: &Path) -> Result<MapPictures> {
    let sizes: HashMap<i32, (i32, i32)> =
        maps.iter().map(|m| (m.id, (m.width, m.height))).collect();
    let mut files: HashMap<String, Option<(PathBuf, File)>> = HashMap::new();
    let mut per: BTreeMap<(i32, i32), Vec<OnMap>> = BTreeMap::new();
    // By the map whose pages show it and the name: whether every show is
    // part of its map.
    let mut all_in: BTreeMap<(i32, String), bool> = BTreeMap::new();
    let mut hidden = Vec::new();
    // The (map, number)s some of whose shows come from another map's page,
    // after a `Teleport`: those are not split into parts, since the part
    // is given to the pages of the map it is seen on.
    let mut crossed: BTreeSet<(i32, i32)> = BTreeSet::new();
    // And those some page shows when the player asks: see `Parts`.
    let mut on_demand: BTreeSet<(i32, i32)> = BTreeSet::new();
    // And those with a show that is not part of the map: the drawings that
    // are, are not all the number shows there.
    let mut unplaced: BTreeSet<(i32, i32)> = BTreeSet::new();
    for s in shown(maps) {
        let lower = s.name.to_lowercase();
        if !files.contains_key(&lower) {
            let found = match crate::pictures::path_of(game_dir, &s.name) {
                Some(path) => Some((path.clone(), read_file(&path)?)),
                None => None,
            };
            files.insert(lower.clone(), found);
        }
        let place = match (&files[&lower], sizes.get(&s.seen)) {
            (Some((path, file)), Some(&size)) => match placed(&s, file, size) {
                Ok(p) => Some((path.clone(), p)),
                Err(why) => {
                    if let Some(why) = why {
                        hidden.push(Hidden {
                            map: s.from,
                            event: s.event,
                            at: s.at,
                            name: s.name.clone(),
                            transparency: s.transparency,
                            why,
                        });
                    }
                    None
                }
            },
            _ => None,
        };
        let entry = all_in.entry((s.from, lower)).or_insert(true);
        *entry &= place.is_some();
        // Part of a scene: its commands are accepted without being done, and
        // the map does not keep it. See the module.
        let place = place.filter(|_| !s.erased);
        // After the scene's rule, not before: a number one of whose shows is
        // a scene's is not split into parts —see `Parts`—, since that show
        // would be accepted without being done while the other drawings'
        // parts stayed up as sprites. The scene's rule wins.
        if place.is_none() {
            unplaced.insert((s.seen, s.number));
        }
        if let Some((path, (corner, repeat))) = place {
            if s.from != s.seen {
                crossed.insert((s.seen, s.number));
            }
            if s.on_demand {
                on_demand.insert((s.seen, s.number));
            }
            per.entry((s.seen, s.number)).or_default().push(OnMap {
                number: s.number,
                name: s.name.clone(),
                path,
                corner,
                transparency: s.transparency.max(0),
                tone: s.tone,
                transparent_color: s.transparent_color,
                repeat,
                derived: false,
            });
        }
    }
    let mut out = MapPictures::default();
    for ((map, number), shows) in per {
        // Under one number a map can show several: a door with its ceiling
        // and another with a second one. The one shown most stays, and of
        // equals the first: the map has one drawing.
        let mut counts: Vec<(usize, &OnMap)> = Vec::new();
        for s in &shows {
            match counts
                .iter_mut()
                .find(|(_, o)| o.name.eq_ignore_ascii_case(&s.name) && o.corner == s.corner)
            {
                Some((n, _)) => *n += 1,
                None => counts.push((1, s)),
            }
        }
        let best = counts
            .iter()
            .max_by(|a, b| a.0.cmp(&b.0).then(std::cmp::Ordering::Greater))
            .map(|(_, o)| (*o).clone());
        let drawings: Vec<&OnMap> = counts.iter().map(|(_, o)| *o).collect();
        if !crossed.contains(&(map, number))
            && !unplaced.contains(&(map, number))
            && !on_demand.contains(&(map, number))
        {
            if let Some(parts) = Parts::of(map, number, &drawings, out_dir)? {
                out.per_map.entry(map).or_default().push(parts.common);
                out.parts.extend(
                    parts
                        .own
                        .into_iter()
                        .map(|(name, path)| ((map, number, name), path)),
                );
                continue;
            }
        }
        if let Some(best) = best {
            out.per_map.entry(map).or_default().push(best);
        }
    }
    for ((from, name), all) in all_in {
        if all {
            out.done_from.entry(from).or_default().insert(name);
        }
    }
    out.hidden = hidden;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shown(on_map: bool, moves_place: bool) -> Shown {
        Shown {
            from: 1,
            seen: 1,
            event: 1,
            at: (0, 0),
            number: 3,
            name: "Mask".to_string(),
            on_map,
            centre: Some((160, 120)),
            zoom: 100,
            by_variable: false,
            effect: EFFECT_NONE,
            transparent_color: true,
            transparency: 35,
            tone: [100; 4],
            screen: (160, 120),
            moves_place,
            moves_size: false,
            branch: Vec::new(),
            erased: false,
            on_demand: false,
        }
    }

    const SCREEN_SIZED: File = File {
        size: (320, 240),
        holes: 0.5,
    };
    const SCROLLS: (i32, i32) = (20, 19);

    #[test]
    fn a_translucent_mask_that_stays_put_is_part_of_its_map() {
        assert_eq!(
            placed(&shown(true, false), &SCREEN_SIZED, SCROLLS),
            Ok(((0, 0), false))
        );
        assert_eq!(
            placed(&shown(false, false), &SCREEN_SIZED, SCROLLS),
            Ok(((0, 0), true))
        );
    }

    #[test]
    fn one_a_move_picture_moves_is_not_whether_it_goes_with_the_map_or_the_screen() {
        assert_eq!(
            placed(&shown(true, true), &SCREEN_SIZED, SCROLLS),
            Err(Some("a MovePicture moves it"))
        );
        assert_eq!(
            placed(&shown(false, true), &SCREEN_SIZED, SCROLLS),
            Err(Some("a MovePicture moves it"))
        );
    }

    fn c(code: i32, indent: i32, string: &str, parameters: &[i32]) -> Command {
        Command {
            code,
            indent,
            string: string.to_string(),
            parameters: parameters.to_vec(),
        }
    }

    /// Each branch of a choice starts where the choice was: the second one
    /// neither moves the first one's picture nor sees it on the first one's
    /// map. The statue's portal on Sunset over Imdahl's map 15, shrunk.
    #[test]
    fn a_branch_does_not_move_the_picture_of_the_branch_before() {
        let show = |name: &str| {
            c(
                SHOW_PICTURE,
                1,
                name,
                &[2, 0, 160, 192, 1, 100, 80, 1, 100, 100, 100, 100, 0, 0],
            )
        };
        let moved = c(
            MOVE_PICTURE,
            1,
            "",
            &[
                2, 0, 160, 0, 0, 100, 100, 0, 100, 100, 100, 100, 0, 0, 15, 0,
            ],
        );
        let page = [
            c(SHOW_CHOICE, 0, "Spring/Summer", &[0]),
            c(SHOW_CHOICE_OPTION, 0, "Spring", &[0]),
            c(TELEPORT, 1, "", &[13, 10, 10]),
            show("Spring"),
            c(SHOW_CHOICE_OPTION, 0, "Summer", &[1]),
            moved.clone(),
            show("Before"),
            moved,
            c(TELEPORT, 1, "", &[14, 10, 10]),
        ];
        let sizes = HashMap::from([(13, (20, 15)), (14, (20, 15)), (15, (20, 15))]);
        let mut out = Vec::new();
        walk(15, (4, (10, 10)), &page, &sizes, &mut out);
        let seen: Vec<_> = out
            .iter()
            .map(|s| (s.name.as_str(), s.seen, s.moves_place))
            .collect();
        assert_eq!(seen, [("Spring", 13, false), ("Before", 15, true)]);
    }

    /// A scene's picture, which its page erases when the scene ends, is not
    /// part of the map; one a branch erases stays in the others, and so does
    /// one another branch erases. Desert Nightmare's warehouse, map 21, and
    /// a number lock like the shrine's on map 161, shrunk.
    #[test]
    fn a_picture_its_page_erases_is_a_scenes() {
        let show_at = |indent: i32, number: i32, name: &str| {
            c(
                SHOW_PICTURE,
                indent,
                name,
                &[number, 0, 160, 120, 1, 100, 0, 1, 100, 100, 100, 100, 0, 0],
            )
        };
        let show = |number: i32, name: &str| show_at(0, number, name);
        let page = [
            show(2, "Wall"),
            show(3, "Light"),
            c(COND_BRANCH, 0, "", &[0, 1, 0, 0, 0, 0]),
            c(ERASE_PICTURE, 1, "", &[3]),
            c(ERASE_PICTURE, 0, "", &[2]),
            // A digit a branch shows, which the next branch erases to show
            // its own: in each, the one shown stays.
            c(COND_BRANCH, 0, "", &[1, 1, 0, 0, 0, 0]),
            show_at(1, 4, "Zero"),
            c(COND_BRANCH, 0, "", &[1, 1, 0, 1, 0, 0]),
            c(ERASE_PICTURE, 1, "", &[4]),
            show_at(1, 4, "One"),
            c(COND_ELSE, 0, "", &[]),
            c(ERASE_PICTURE, 1, "", &[4]),
        ];
        let sizes = HashMap::from([(21, (20, 15))]);
        let mut out = Vec::new();
        walk(21, (8, (0, 0)), &page, &sizes, &mut out);
        let erased: Vec<_> = out.iter().map(|s| (s.name.as_str(), s.erased)).collect();
        assert_eq!(
            erased,
            [
                ("Wall", true),
                ("Light", false),
                ("Zero", false),
                ("One", false)
            ]
        );
    }

    #[test]
    fn what_loses_nothing_by_the_rule_has_no_why() {
        let small = File {
            size: (64, 64),
            holes: 0.5,
        };
        assert_eq!(placed(&shown(true, true), &small, SCROLLS), Err(None));
        let mut invisible = shown(true, false);
        invisible.transparency = 100;
        assert_eq!(placed(&invisible, &SCREEN_SIZED, SCROLLS), Err(None));
    }

    /// A menu of three options drawn whole three times, each with its own
    /// lit: Desert Nightmare's start menu on map 1, shrunk to 4x3 —a
    /// transparent column, then an option per row—.
    fn menu(dir: &Path, lit: usize, transparency: i32) -> OnMap {
        let (w, h) = (4usize, 3usize);
        let mut pixels = vec![[0u8; 4]; w * h];
        for y in 0..h {
            // Column 0 is transparent, column 1 the frame, the same in all.
            pixels[y * w + 1] = [60, 20, 0, 255];
            for x in 2..w {
                pixels[y * w + x] = if y == lit {
                    [250, 200, 0, 255]
                } else {
                    [90, 40, 0, 255]
                };
            }
        }
        let path = dir.join(format!("menu-{lit}.png"));
        assert!(write_indexed(&path, w, h, &pixels).unwrap());
        OnMap {
            number: 1,
            name: format!("Menu_{lit}"),
            path,
            corner: (0, 0),
            transparency,
            tone: [100; 4],
            transparent_color: true,
            repeat: false,
            derived: false,
        }
    }

    fn read(path: &Path) -> Vec<[u8; 4]> {
        let art = rm2k_render::picture::read_rm2k(path).unwrap();
        art.rgba
            .chunks_exact(4)
            .map(|p| [p[0], p[1], p[2], p[3]])
            .collect()
    }

    #[test]
    fn drawings_under_one_number_are_drawn_in_common_and_each_shows_its_own() {
        let dir = std::env::temp_dir().join(format!("convert-parts-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let drawings: Vec<OnMap> = (0..3).map(|k| menu(&dir, k, 0)).collect();
        let refs: Vec<&OnMap> = drawings.iter().collect();
        let parts = Parts::of(1, 1, &refs, &dir)
            .unwrap()
            .expect("the menu splits");
        // The common part is the frame and the three rows unlit, as most
        // drawings have each; each part, its own row lit.
        let common = read(&parts.common.path);
        for (i, p) in common.iter().enumerate() {
            match i % 4 {
                0 => assert_eq!(p[3], 0, "common, pixel {i}"),
                1 => assert_eq!(*p, [60, 20, 0, 255], "common, pixel {i}"),
                _ => assert_eq!(*p, [90, 40, 0, 255], "common, pixel {i}"),
            }
        }
        assert!(parts.common.derived);
        for (k, (name, path)) in parts.own.iter().enumerate() {
            assert_eq!(*name, format!("menu_{k}"));
            let own = read(path);
            for (i, p) in own.iter().enumerate() {
                let lit = i / 4 == k && i % 4 > 1;
                if lit {
                    assert_eq!(*p, [250, 200, 0, 255], "part {k}, pixel {i}");
                } else {
                    assert_eq!(p[3], 0, "part {k}, pixel {i}");
                }
            }
        }
        // Seen through, a small picture would be drawn opaque: not split.
        let faint: Vec<OnMap> = (0..3).map(|k| menu(&dir, k, 30)).collect();
        let refs: Vec<&OnMap> = faint.iter().collect();
        assert!(Parts::of(1, 1, &refs, &dir).unwrap().is_none());
        std::fs::remove_dir_all(&dir).ok();
    }

    /// The two rules over one number: three drawings of a menu are split
    /// into parts on the map that keeps them, and not on one whose page
    /// erases the number at its end —the scene's rule wins over the number,
    /// whose shows stay accepted without being done—, nor on one whose page
    /// the player starts.
    #[test]
    fn a_scene_s_drawings_are_not_split_into_parts() {
        use crate::game::{Event, Page};
        let dir = std::env::temp_dir().join(format!("convert-parts-scene-{}", std::process::id()));
        let pictures = dir.join("Picture");
        std::fs::create_dir_all(&pictures).unwrap();
        let (w, h) = (320usize, 240usize);
        for lit in 0..3 {
            let mut pixels = vec![[0u8; 4]; w * h];
            for y in 0..30 {
                for x in 0..100 {
                    let on = y / 10 == lit;
                    pixels[y * w + x] = if on {
                        [250, 200, 0, 255]
                    } else {
                        [90, 40, 0, 255]
                    };
                }
            }
            let path = pictures.join(format!("Menu_{lit}.png"));
            assert!(write_indexed(&path, w, h, &pixels).unwrap());
        }
        let show = |lit: i32| {
            c(
                SHOW_PICTURE,
                0,
                &format!("Menu_{lit}"),
                &[1, 0, 160, 120, 0, 100, 0, 1, 100, 100, 100, 100, 0, 0],
            )
        };
        let map = |id: i32, mut commands: Vec<Command>, erase: bool, trigger: i32| {
            if erase {
                commands.push(c(ERASE_PICTURE, 0, "", &[1]));
            }
            GameMap {
                id,
                chipset_id: 1,
                width: 20,
                height: 15,
                scroll_type: 0,
                events: vec![Event {
                    id: 1,
                    x: 0,
                    y: 0,
                    pages: vec![Page {
                        id: 1,
                        character_name: String::new(),
                        dump_name: String::new(),
                        character_index: 0,
                        direction: 2,
                        pattern: 1,
                        layer: 0,
                        animation_type: 0,
                        translucent: false,
                        trigger,
                        commands,
                    }],
                }],
                lower_layer: Vec::new(),
                upper_layer: Vec::new(),
                twins: Vec::new(),
            }
        };
        // Autostart, as Desert Nightmare's map 1; and the same from a page
        // the action key starts, as its locks.
        let menu = map(1, (0..3).map(show).collect(), false, 3);
        let scene = map(2, (0..3).map(show).collect(), true, 3);
        let lock = map(3, (0..3).map(show).collect(), false, 0);
        let out = dir.join("out");
        let decided = decide(&[&menu, &scene, &lock], &dir, &out).unwrap();
        assert!(decided.part(1, 1, "Menu_1").is_some());
        assert_eq!(decided.of(1).len(), 1);
        assert!(decided.of(1)[0].derived);
        // Only the last show is the one the erase reaches —a picture shown
        // again under its number is not taken as erased, see `walk`—, so the
        // other two stay as before the parts: the one shown first is drawn.
        assert!(decided.part(2, 1, "Menu_1").is_none());
        assert_eq!(decided.of(2).len(), 1);
        assert!(!decided.of(2)[0].derived);
        assert!(decided.done(2, "Menu_2"));
        // On demand: not split, the one shown first drawn, as before.
        assert!(decided.part(3, 1, "Menu_1").is_none());
        assert_eq!(decided.of(3).len(), 1);
        assert!(!decided.of(3)[0].derived);
        std::fs::remove_dir_all(&dir).ok();
    }
}
