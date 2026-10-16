//! The `ShowPicture` pictures that are part of the map: drawn into it here,
//! before it is converted, instead of being shown as pictures.
//!
//! Which ones they are is the caller's to say —`map_pictures` in the
//! request, see `map_pictures.rs` in rm2k-snes-convert—: pictures that stay
//! where they are on the map for as long as one is there, which is how a
//! game drawn as a painting adds what goes above the hero, its lights, its
//! shadows and its mists. Each comes with its corner on the map and the
//! tone and transparency it stays at, and they are drawn **in the order
//! they come, which is RM2k's**: by number, higher on top.
//!
//! * **Over a panorama fixed to the map** —one the size of the map, or a
//!   map RM2k's camera never scrolls—, which is what such a game draws its
//!   map with, each one is blended into the panorama itself, the opaque
//!   ones too. What the opaque ones cover goes **in front of the hero** by
//!   the priority bit of the panorama's cells, in mode 3 —BG2 at 1 is in
//!   front of the objects at 1—: [`raise`]. No tiles and no colours of
//!   their own: an opaque one is the painting's own pixels, cut out.
//! * **Without one**, the opaque ones are drawn into the layer above the
//!   hero and the others are blended into the lower layer where it draws.
//!
//! What is lost: the characters are neither shaded nor lit by what is
//! translucent; nothing of it changes over time; and what goes in front of
//! the hero goes by whole 8x8 cells. The study:
//! `ports/sunset-over-imdahl/research/2026-10-11-the-pictures-over-the-map.md` in the
//! book.

use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::layers::Panorama;
use rm2k_render::{picture, Layers, Picture};
use serde_json::Value;

/// One picture of the map: see `map_pictures` in the request.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MapPicture {
    pub number: i32,
    pub name: String,
    /// Its corner on the map, in pixels.
    pub corner: (i64, i64),
    /// RM2k's transparency, 0 to 100, and tone, `[red, green, blue,
    /// saturation]` with 100 for nothing.
    pub transparency: i32,
    pub tone: [i32; 4],
    pub transparent_color: bool,
    /// Repeated over the whole map from its corner: a mist that goes with
    /// the screen on a map that scrolls.
    pub repeat: bool,
}

/// `map_pictures`, which can be missing: a list of
/// `{"number", "name", "corner": [x, y], "transparency", "tone": [r, g, b,
/// s], "transparent_color", "repeat"}`.
pub fn from_json(data: &Value, whose: &str) -> Result<Vec<MapPicture>> {
    let Some(list) = data.get("map_pictures").filter(|v| !v.is_null()) else {
        return Ok(Vec::new());
    };
    let bad = |what: &str| Bad::answer(format!("{whose}: a map picture's {what}"));
    let int = |v: &Value, what: &str| v.as_i64().ok_or_else(|| bad(what));
    list.as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: `map_pictures` is not a list")))?
        .iter()
        .map(|p| {
            let corner = p["corner"].as_array().filter(|a| a.len() == 2).ok_or_else(|| bad("corner"))?;
            let tone = p["tone"].as_array().filter(|a| a.len() == 4).ok_or_else(|| bad("tone"))?;
            let mut t = [0; 4];
            for (k, v) in tone.iter().enumerate() {
                t[k] = int(v, "tone")? as i32;
            }
            Ok(MapPicture {
                number: int(&p["number"], "number")? as i32,
                name: p["name"].as_str().ok_or_else(|| bad("name"))?.to_string(),
                corner: (int(&corner[0], "corner")?, int(&corner[1], "corner")?),
                transparency: int(&p["transparency"], "transparency")? as i32,
                tone: t,
                transparent_color: p["transparent_color"].as_bool().ok_or_else(|| bad("transparent colour"))?,
                repeat: p["repeat"].as_bool().ok_or_else(|| bad("repeat"))?,
            })
        })
        .collect()
}

/// RM2k's screen: a map no bigger than it is never scrolled.
const SCREEN: (usize, usize) = (320, 240);

/// Whether the panorama stays put on the map on both axes: one the size of
/// the map —`Game_Map::Parallax` takes it from edge to edge with the
/// camera—, or a map RM2k's camera never scrolls; and it moves on its own
/// on neither, nor can a `ChangePBG` make it. One that only swaps the
/// picture —a door that opens, on Sunset's 26 and 36— still is: the console
/// keeps the first.
pub fn fixed_to_map(p: &Panorama, map: (usize, usize)) -> bool {
    let axis = |m: usize, screen: usize, size: usize| m <= screen || size == m;
    p.looped == (false, false)
        && p.auto == (0, 0)
        && p.changed_loops == (false, false)
        && axis(map.0, SCREEN.0, p.size.0)
        && axis(map.1, SCREEN.1, p.size.1)
}

/// A channel of RM2k's tone: below 100 it scales, above it brings the
/// channel toward white —easyrpg's `ToneBlit`—.
fn tint(c: i32, v: i32) -> i32 {
    if v <= 100 {
        c * v / 100
    } else {
        255 - (200 - v) * (255 - c) / 100
    }
    .clamp(0, 255)
}

/// RM2k's tone on a pixel: saturation first, then the colour.
fn toned(px: [u8; 4], t: [i32; 4]) -> [u8; 4] {
    if t == [100; 4] {
        return px;
    }
    let mut c = [px[0] as i32, px[1] as i32, px[2] as i32];
    if t[3] != 100 {
        let luma = (19595 * c[0] + 38470 * c[1] + 7471 * c[2]) >> 16;
        for v in c.iter_mut() {
            *v = (luma + (*v - luma) * t[3] / 100).clamp(0, 255);
        }
    }
    [tint(c[0], t[0]) as u8, tint(c[1], t[1]) as u8, tint(c[2], t[2]) as u8, px[3]]
}

/// `over` on `under` with `alpha` of 255, the colour only: `under` keeps
/// its own alpha.
fn blend(under: &mut [u8], over: [u8; 4], alpha: u32) {
    for k in 0..3 {
        let (u, o) = (under[k] as u32, over[k] as u32);
        under[k] = ((u * (255 - alpha) + o * alpha + 127) / 255) as u8;
    }
}

/// The map's pixels a picture covers, with its pixel there: every place of
/// the map once, the repeated ones from their corner.
fn covered(p: &MapPicture, art: &Picture, map: (usize, usize)) -> Vec<(usize, usize, [u8; 4])> {
    let (w, h) = (art.width as i64, art.height as i64);
    let mut out = Vec::new();
    for y in 0..map.1 as i64 {
        for x in 0..map.0 as i64 {
            let (mut sx, mut sy) = (x - p.corner.0, y - p.corner.1);
            if p.repeat {
                sx = sx.rem_euclid(w);
                sy = sy.rem_euclid(h);
            }
            let px = art.get(sx, sy);
            if px[3] != 0 {
                out.push((x as usize, y as usize, px));
            }
        }
    }
    out
}

/// Draws the map's pictures into `layers` and `panorama`. Answers, for a
/// panorama fixed to the map, which of the map's pixels an opaque one
/// covers: what goes in front of the hero, for [`raise`]. None if there is
/// nothing to raise.
pub fn compose(
    game: &Game,
    id: i32,
    pictures: &[MapPicture],
    map: (usize, usize),
    layers: &mut Layers,
    panorama: Option<&mut Panorama>,
) -> Result<Option<Vec<bool>>> {
    if pictures.is_empty() {
        return Ok(None);
    }
    let mut panorama = panorama.filter(|p| fixed_to_map(p, map));
    let mut front = vec![false; map.0 * map.1];
    for p in pictures {
        let path = game.resource("Picture", &p.name).ok_or_else(|| {
            Bad::answer(format!("map {id}: picture {:?} is in none of the search directories", p.name))
        })?;
        let art = if p.transparent_color { picture::read_rm2k(&path)? } else { picture::read_unkeyed(&path)? };
        let alpha = rm2k_rules::picture::opacity(p.transparency) as u32;
        let opaque = alpha == 255;
        for (x, y, px) in covered(p, &art, map) {
            let px = toned(px, p.tone);
            let a = alpha * px[3] as u32 / 255;
            let at = (y * map.0 + x) * 4;
            match panorama.as_deref_mut() {
                Some(pano) => {
                    // The whole picture is the map's corner on: see
                    // `fixed_to_map`. The stretch is cut from it after.
                    if x < pano.whole.width && y < pano.whole.height {
                        let k = (y * pano.whole.width + x) * 4;
                        blend(&mut pano.whole.rgba[k..k + 4], px, a);
                    }
                    if opaque && px[3] == 255 {
                        front[y * map.0 + x] = true;
                    }
                }
                None if opaque => {
                    layers.upper.rgba[at..at + 4].copy_from_slice(&[px[0], px[1], px[2], 255]);
                }
                None => {
                    // Into the layer above the hero too: RM2k's picture
                    // is over the whole map, and with only the lower one
                    // blended, a dark mask left the top edge of a room's
                    // walls lit (Desert Nightmare's WC, map 7).
                    for layer in std::iter::once(&mut layers.lower)
                        .chain(std::iter::once(&mut layers.upper))
                        .chain(layers.variants.iter_mut().flat_map(|(_, gs)| gs.iter_mut()))
                    {
                        if layer.rgba[at + 3] != 0 {
                            blend(&mut layer.rgba[at..at + 4], px, a);
                        }
                    }
                }
            }
        }
    }
    let Some(pano) = panorama else {
        return Ok(None);
    };
    pano.picture = pano.whole.crop(0, 0, pano.picture.width, pano.picture.height);
    Ok(front.iter().any(|&f| f).then_some(front))
}

/// The tilemap priority bit: in mode 3 a BG2 cell with it goes in front of
/// the objects of priority 1, the hero and the events on his layer, and
/// behind those of 2, the ones above him.
const PRIORITY: u16 = 0x2000;

/// The panorama's cells that `front` covers at least half of, raised in
/// front of the hero. A whole 8x8 cell goes in front or behind: answers how
/// many pixels end up on the wrong side —the picture's in a cell left
/// behind, the painting's in a cell raised— and how many `front` has.
pub fn raise(tilemap: &mut [Vec<u16>], front: &[bool], width: usize) -> (usize, usize) {
    let (mut wrong, mut total) = (0, 0);
    let height = front.len() / width.max(1);
    for (cy, row) in tilemap.iter_mut().enumerate() {
        for (cx, entry) in row.iter_mut().enumerate() {
            let drawn = (0..8)
                .flat_map(|y| (0..8).map(move |x| (cx * 8 + x, cy * 8 + y)))
                .filter(|&(x, y)| x < width && y < height && front[y * width + x])
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_cell_goes_in_front_when_half_of_it_is_covered() {
        // A 16x8 map: the first cell covered in 32 pixels, the second in 31.
        let mut front = vec![false; 16 * 8];
        for y in 0..8 {
            for x in 0..4 {
                front[y * 16 + x] = true;
            }
            for x in 8..12 {
                front[y * 16 + x] = !(y == 0 && x == 8);
            }
        }
        let mut tilemap = vec![vec![5u16, 6u16]];
        let (wrong, total) = raise(&mut tilemap, &front, 16);
        assert_eq!(tilemap, vec![vec![5 | PRIORITY, 6]]);
        assert_eq!((wrong, total), (32 + 31, 63));
    }

    #[test]
    fn the_tone_brightens_and_grays_as_rm2k() {
        assert_eq!(toned([100, 50, 0, 255], [100; 4]), [100, 50, 0, 255]);
        assert_eq!(toned([100, 50, 0, 255], [200, 100, 50, 100]), [255, 50, 0, 255]);
        assert_eq!(toned([100, 100, 100, 7], [100, 100, 100, 0]), [100, 100, 100, 7]);
    }
}
