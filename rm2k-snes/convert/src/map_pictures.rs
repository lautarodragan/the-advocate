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
//!   transparency it stays at.

use crate::fail::{Result, Stop};
use crate::game::{Command, GameMap};
use rm2k_snes_events::codes::{MOVE_PICTURE, SHOW_PICTURE, TELEPORT};
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
const SMALL: (i32, i32) = (crate::pictures::WIDTH_MAX as i32, crate::pictures::HEIGHT_MAX as i32);
/// The effects a picture can have and still be part of the map: none, or
/// the wave, which is not done —Sunset's sun rays wave at strength 1 and 95
/// % transparency—.
const EFFECT_NONE: i32 = 0;
const EFFECT_WAVE: i32 = 2;
/// How much of an opaque picture has to be its transparent colour for it
/// to be part of the map and not a card over it: Sunset's roofs leave 52 to
/// 99 % of themselves transparent; its test map's card, 0.
const OPAQUE_HOLES_MIN: f64 = 0.25;

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
}

impl OnMap {
    pub fn to_json(&self) -> Value {
        json!({
            "number": self.number,
            "name": self.name,
            "corner": [self.corner.0, self.corner.1],
            "transparency": self.transparency,
            "tone": self.tone,
            "transparent_color": self.transparent_color,
            "repeat": self.repeat,
        })
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
    pub fn of(&self, map: i32) -> &[OnMap] {
        self.per_map.get(&map).map_or(&[], Vec::as_slice)
    }

    /// Whether the compiler is not to be given `name` in `map`'s pages.
    pub fn done(&self, map: i32, name: &str) -> bool {
        self.done_from.get(&map).is_some_and(|names| names.contains(&name.to_lowercase()))
    }
}

/// What the file of a picture says: its size and how much of it is the
/// transparent colour, index 0.
#[derive(Clone, Copy, Debug)]
struct File {
    size: (i32, i32),
    holes: f64,
}

fn read_file(path: &Path) -> Result<File> {
    let open = std::fs::File::open(path).map_err(|e| crate::fail::io(path, e))?;
    let decoder = png::Decoder::new(open);
    let mut reader = decoder.read_info().map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let mut buf = vec![0; reader.output_buffer_size()];
    let frame = reader.next_frame(&mut buf).map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
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
    Ok(File { size: (w as i32, h as i32), holes })
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
}

/// RM2k's camera on `map` with the hero at cell `(x, y)`.
fn camera(size: (i32, i32), (x, y): (i32, i32)) -> (i32, i32) {
    let clamp = |hero: i32, centre: i32, map: i32, screen: i32| (hero * TILE - centre).clamp(0, (map * TILE - screen).max(0));
    (clamp(x, HERO.0, size.0, SCREEN.0), clamp(y, HERO.1, size.1, SCREEN.1))
}

fn one_screen(size: (i32, i32)) -> bool {
    size.0 * TILE <= SCREEN.0 && size.1 * TILE <= SCREEN.1
}

/// Every `ShowPicture` of `maps`' pages, with the map it is seen on.
fn shown(maps: &[&GameMap]) -> Vec<Shown> {
    let sizes: HashMap<i32, (i32, i32)> = maps.iter().map(|m| (m.id, (m.width, m.height))).collect();
    let mut out = Vec::new();
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                walk(map.id, (event.id, (event.x, event.y)), &page.commands, &sizes, &mut out);
            }
        }
    }
    out
}

fn walk(from: i32, (event, at): (i32, (i32, i32)), commands: &[Command], sizes: &HashMap<i32, (i32, i32)>, out: &mut Vec<Shown>) {
    let mut seen = from;
    let mut cam = sizes.get(&from).filter(|s| one_screen(**s)).map(|_| (0, 0));
    // The page's last `ShowPicture` under each number, which its moves act on.
    let mut last: HashMap<i32, usize> = HashMap::new();
    for c in commands {
        let p = &c.parameters;
        match c.code {
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
                });
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
    }
}

/// Whether a `ShowPicture` is part of its map, and if so where: its corner
/// and whether it repeats. If not, why, when it is a translucent one the
/// objects do not take —one that stays a big picture, over black, with the
/// map hidden—; `None` for the rest, which lose nothing by this rule.
fn placed(s: &Shown, file: &File, size: (i32, i32)) -> std::result::Result<((i32, i32), bool), Option<&'static str>> {
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
        }
    }

    const SCREEN_SIZED: File = File { size: (320, 240), holes: 0.5 };
    const SCROLLS: (i32, i32) = (20, 19);

    #[test]
    fn a_translucent_mask_that_stays_put_is_part_of_its_map() {
        assert_eq!(placed(&shown(true, false), &SCREEN_SIZED, SCROLLS), Ok(((0, 0), false)));
        assert_eq!(placed(&shown(false, false), &SCREEN_SIZED, SCROLLS), Ok(((0, 0), true)));
    }

    #[test]
    fn one_a_move_picture_moves_is_not_whether_it_goes_with_the_map_or_the_screen() {
        assert_eq!(placed(&shown(true, true), &SCREEN_SIZED, SCROLLS), Err(Some("a MovePicture moves it")));
        assert_eq!(placed(&shown(false, true), &SCREEN_SIZED, SCROLLS), Err(Some("a MovePicture moves it")));
    }

    #[test]
    fn what_loses_nothing_by_the_rule_has_no_why() {
        let small = File { size: (64, 64), holes: 0.5 };
        assert_eq!(placed(&shown(true, true), &small, SCROLLS), Err(None));
        let mut invisible = shown(true, false);
        invisible.transparency = 100;
        assert_eq!(placed(&invisible, &SCREEN_SIZED, SCROLLS), Err(None));
    }
}

/// The rule, over the cartridge's maps: see the module.
pub fn decide(maps: &[&GameMap], game_dir: &Path) -> Result<MapPictures> {
    let sizes: HashMap<i32, (i32, i32)> = maps.iter().map(|m| (m.id, (m.width, m.height))).collect();
    let mut files: HashMap<String, Option<(PathBuf, File)>> = HashMap::new();
    let mut per: BTreeMap<(i32, i32), Vec<OnMap>> = BTreeMap::new();
    // By the map whose pages show it and the name: whether every show is
    // part of its map.
    let mut all_in: BTreeMap<(i32, String), bool> = BTreeMap::new();
    let mut hidden = Vec::new();
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
        if let Some((path, (corner, repeat))) = place {
            per.entry((s.seen, s.number)).or_default().push(OnMap {
                number: s.number,
                name: s.name.clone(),
                path,
                corner,
                transparency: s.transparency.max(0),
                tone: s.tone,
                transparent_color: s.transparent_color,
                repeat,
            });
        }
    }
    let mut out = MapPictures::default();
    for ((map, _number), shows) in per {
        // Under one number a map can show several: a door with its ceiling
        // and another with a second one. The one shown most stays, and of
        // equals the first: the map has one drawing.
        let mut counts: Vec<(usize, &OnMap)> = Vec::new();
        for s in &shows {
            match counts.iter_mut().find(|(_, o)| o.name.eq_ignore_ascii_case(&s.name) && o.corner == s.corner) {
                Some((n, _)) => *n += 1,
                None => counts.push((1, s)),
            }
        }
        let best = counts.iter().max_by(|a, b| a.0.cmp(&b.0).then(std::cmp::Ordering::Greater)).map(|(_, o)| (*o).clone());
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
