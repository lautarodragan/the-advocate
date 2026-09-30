//! What goes at the end of the sprite bank besides the characters: the
//! timer's digits, the raindrops, a `ShowPicture` picture and the battle
//! animation's box, each with its tiles and the palette it takes.
//!
//! The first two share a palette with whoever has room; the last two take a
//! whole one each, above the characters', because what is in it fades or
//! changes with them.

use crate::character::{OBJ_COLORS, OBJ_PALETTES};
use crate::fail::{Bad, Result};
use adeleine::Color;
use rm2k_render::Picture;
use std::collections::{BTreeMap, BTreeSet};
use voodoo::pack_tile;

/// The timer: eleven 8x16 glyphs of the System —ten digits and the colon—
/// in a row, which is all RM2k's timer draws.
pub const TIMER_GLYPHS: usize = 11;
pub const TIMER_GLYPH_W: usize = 8;
pub const TIMER_GLYPH_H: usize = 16;

/// The rain's three greys, at 15 bits, from above to below the streak.
pub const RAIN_COLORS: [Color; 3] = [[16, 16, 18], [11, 11, 13], [6, 6, 7]];

/// The battle animation's box: one row of blocks, four 32x32 objects.
pub const ANIMATION_TILES: usize = 64;

/// A row of blocks: what the arithmetic of 32x32 objects needs whole.
const BLOCK_ROW: usize = 64;

fn rounded_to_row(tiles: usize) -> usize {
    tiles.div_ceil(BLOCK_ROW) * BLOCK_ROW
}

fn grow(tiles: &mut Vec<u8>, count: usize) {
    if count * 32 > tiles.len() {
        tiles.resize(count * 32, 0);
    }
}

fn put(tiles: &mut [u8], number: usize, cell: &[[u8; 8]; 8]) {
    tiles[number * 32..(number + 1) * 32].copy_from_slice(&pack_tile(cell, 4));
}

/// The colours the timer's glyphs use, sorted. They are needed before the
/// split: in a map that fills all eight palettes, someone has to lose a
/// colour to make room for them.
pub fn timer_colors(glyphs: &Picture) -> Vec<Color> {
    let mut colors = BTreeSet::new();
    for y in 0..TIMER_GLYPH_H as i64 {
        for x in 0..(TIMER_GLYPHS * TIMER_GLYPH_W) as i64 {
            let p = glyphs.get(x, y);
            if p[3] != 0 {
                colors.insert([p[0] >> 3, p[1] >> 3, p[2] >> 3]);
            }
        }
    }
    colors.into_iter().collect()
}

/// The first palette —but the leaders'— where `colors` fit without merging
/// anything, or a new one if one is left under `cap`: it is grown or added,
/// and its number returned. `None` if there is no room.
pub fn first_place(
    palettes: &mut Vec<Vec<Color>>,
    avoid: &BTreeSet<usize>,
    colors: &[Color],
    cap: usize,
) -> Option<usize> {
    for number in 0..palettes.len() {
        if avoid.contains(&number) {
            continue;
        }
        let mut union = palettes[number].clone();
        union.extend(colors.iter().filter(|c| !palettes[number].contains(c)));
        if union.len() <= OBJ_COLORS {
            palettes[number] = union;
            return Some(number);
        }
    }
    if palettes.len() < cap {
        palettes.push(colors.to_vec());
        return Some(palettes.len() - 1);
    }
    None
}

/// The timer's glyphs at the end of the bank, each as two stacked tiles: a
/// row of sixteen fits all eleven, glyph `i` at `base + i` and `base + 16 +
/// i`, from a row of blocks on. Their colours go into the first palette
/// with room —but the leaders', which the console overwrites—, or a new
/// one. Returns the base and the palette.
pub fn timer_digits(
    glyphs: &Picture,
    tiles: &mut Vec<u8>,
    palettes: &mut Vec<Vec<Color>>,
    leader_owned: &BTreeSet<usize>,
    cap: usize,
) -> Result<(usize, usize)> {
    let wanted = timer_colors(glyphs);
    if wanted.len() > OBJ_COLORS {
        return Err(Bad::new(format!(
            "the timer digits use {} colors and {OBJ_COLORS} fit",
            wanted.len()
        )));
    }
    let mut which = None;
    for number in 0..palettes.len() {
        if leader_owned.contains(&number) {
            continue;
        }
        let mut union = palettes[number].clone();
        union.extend(wanted.iter().filter(|c| !palettes[number].contains(c)));
        if union.len() <= OBJ_COLORS {
            palettes[number] = union;
            which = Some(number);
            break;
        }
    }
    let which = match which {
        Some(n) => n,
        None => {
            if palettes.len() >= cap {
                return Err(Bad::new(format!(
                    "the timer doesn't fit: the map already uses the {cap} sprite palettes it \
                     gets and none has room for its {} colors",
                    wanted.len()
                )));
            }
            palettes.push(wanted.clone());
            palettes.len() - 1
        }
    };
    let palette = &palettes[which];
    let index: BTreeMap<Color, u8> = wanted
        .iter()
        .map(|c| (*c, palette.iter().position(|p| p == c).unwrap() as u8 + 1))
        .collect();
    let base = rounded_to_row(tiles.len() / 32);
    grow(tiles, base + 16 + TIMER_GLYPHS);
    for i in 0..TIMER_GLYPHS {
        for half in 0..2 {
            let mut cell = [[0u8; 8]; 8];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, v) in row.iter_mut().enumerate() {
                    let p = glyphs.get((i * TIMER_GLYPH_W + x) as i64, (half * 8 + y) as i64);
                    if p[3] != 0 {
                        *v = index[&[p[0] >> 3, p[1] >> 3, p[2] >> 3]];
                    }
                }
            }
            put(tiles, base + half * 16 + i, &cell);
        }
    }
    Ok((base, which))
}

/// The pixels of a drop with its corner at (x, y): a 4x16 streak going down
/// to the left, one pixel every four rows.
pub fn rain_pixels(x: i32, y: i32) -> Vec<(i32, i32)> {
    (0..16).map(|r| (x + 3 - r / 4, y + r)).collect()
}

/// The six raindrop tiles —above and below the streak, in the three
/// greys— and the palette their colours go in: the first with room but the
/// leaders' and the timer's. With the timer, in its row of sixteen, which
/// has five places to spare. `None` if there is no room: that map draws no
/// rain, and nobody loses a colour for it.
pub fn rain_drops(
    tiles: &mut Vec<u8>,
    palettes: &mut Vec<Vec<Color>>,
    leader_owned: &BTreeSet<usize>,
    timer: Option<(usize, usize)>,
    cap: usize,
) -> Option<(usize, usize)> {
    let mut avoid = leader_owned.clone();
    if let Some((_, pal)) = timer {
        avoid.insert(pal);
    }
    let which = first_place(palettes, &avoid, &RAIN_COLORS, cap)?;
    let palette = palettes[which].clone();
    let base = match timer {
        Some((base, _)) if base != 0 => base + TIMER_GLYPHS,
        _ => rounded_to_row(tiles.len() / 32),
    };
    grow(tiles, base + 16 + 3);
    let streak: BTreeSet<(i32, i32)> = rain_pixels(0, 0).into_iter().collect();
    for (hue, color) in RAIN_COLORS.iter().enumerate() {
        let index = palette.iter().position(|p| p == color).unwrap() as u8 + 1;
        for half in 0..2 {
            let mut cell = [[0u8; 8]; 8];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, v) in row.iter_mut().enumerate() {
                    if streak.contains(&(x as i32, (half * 8 + y) as i32)) {
                        *v = index;
                    }
                }
            }
            put(tiles, base + half * 16 + hue, &cell);
        }
    }
    Some((base, which))
}

/// A `ShowPicture` picture, already cut into tiles by whoever decided it
/// is this map's: tile number (from the base) to its 8x8 cell of 4-bit
/// indices, and how many tiles it reserves.
#[derive(Clone, Debug, Default)]
pub struct Image {
    pub tiles: usize,
    pub cells: Vec<(usize, [[u8; 8]; 8])>,
}

/// The picture at the end of the bank, and **a whole palette just for it**,
/// the first free one —not added to the list: it goes above the characters'
/// and its colours are uploaded with its fade—. `None` if the map already
/// uses all eight. After the timer or the drops, it starts two rows of
/// sixteen later, rounded to a row of blocks.
pub fn picture_of_image(
    image: &Image,
    tiles: &mut Vec<u8>,
    palettes: &[Vec<Color>],
    previous_base: usize,
) -> Option<(usize, usize)> {
    if palettes.len() >= OBJ_PALETTES {
        return None;
    }
    let which = palettes.len();
    let base = if previous_base != 0 {
        (previous_base + 2 * 16).div_ceil(BLOCK_ROW) * BLOCK_ROW
    } else {
        rounded_to_row(tiles.len() / 32)
    };
    grow(tiles, base + image.tiles);
    for (number, cell) in &image.cells {
        put(tiles, base + number, cell);
    }
    Some((base, which))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The timer's eleven glyphs in two colours, black and pure red, like
    /// the System's.
    fn glyphs() -> Picture {
        let mut picture = Picture::transparent(88, 16);
        for (i, px) in picture.rgba.chunks_mut(4).enumerate() {
            if i % 3 != 0 {
                px.copy_from_slice(if i % 2 == 0 { &[248, 0, 0, 255] } else { &[0, 0, 0, 255] });
            }
        }
        picture
    }

    /// Made-up palettes, with colours the timer does not use.
    fn palettes(colors: u8, how_many: u8) -> Vec<Vec<Color>> {
        (0..how_many).map(|i| (0..colors).map(|k| [1, i, k]).collect()).collect()
    }

    /// With the eight palettes taken but with room, the digits go into one
    /// that exists and none is added.
    #[test]
    fn the_digits_go_into_a_palette_that_exists() {
        let mut p = palettes(13, 8);
        let mut tiles = vec![0; 32 * 64];
        let (_, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES).unwrap();
        assert_eq!(p.len(), OBJ_PALETTES);
        assert!(p[which].len() <= OBJ_COLORS);
    }

    /// With the eight full there is nothing to be done, and it says so.
    #[test]
    fn if_they_really_do_not_fit_it_says_so() {
        let mut p = palettes(15, 8);
        let mut tiles = vec![0; 32 * 64];
        assert!(timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES).is_err());
    }

    /// The console overwrites the leaders' slot with the colours of whoever
    /// leads, so a digit there would lose its red: the first palette with
    /// room is skipped if it is a leader's. No map of the game reaches this
    /// path, which is why it is made up.
    #[test]
    fn the_timer_does_not_land_in_a_leaders_slot() {
        let mut p = vec![(0..4).map(|k| [1, 1, k]).collect(), (0..4).map(|k| [2, 2, k]).collect()];
        let mut tiles = vec![0; 32 * 64];
        let (_, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::from([0]), OBJ_PALETTES).unwrap();
        assert_eq!(which, 1);
    }

    /// The other palette the console uploads again untinted is the
    /// timer's: the digits go above the screen's tint and the rain below
    /// it, so a drop in there would stay grey on a tinted screen.
    #[test]
    fn the_drops_do_not_land_in_the_timers_palette() {
        let mut p = vec![(0..4).map(|k| [1, 1, k]).collect(), (0..4).map(|k| [2, 2, k]).collect()];
        let mut tiles = vec![0; 32 * 64];
        let (base, which) = rain_drops(&mut tiles, &mut p, &BTreeSet::new(), Some((64, 0)), OBJ_PALETTES).unwrap();
        assert_eq!(base, 64 + TIMER_GLYPHS);
        assert_ne!(which, 0);
    }

    /// The glyphs start at a row of blocks, eleven across and two tiles
    /// tall.
    #[test]
    fn the_digits_start_at_a_row_of_blocks() {
        let mut p = palettes(4, 2);
        let mut tiles = vec![0; 32 * 70];
        let (base, _) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES).unwrap();
        assert_eq!(base, 128);
        assert_eq!(tiles.len(), (base + 16 + TIMER_GLYPHS) * 32);
    }
}

/// The battle animation's box at the end of the bank: its tiles, left
/// blank —the console uploads each frame—, and a whole palette, after the
/// picture's if it took one. `None` without a palette.
pub fn map_animation(tiles: &mut Vec<u8>, palettes: &[Vec<Color>], used: usize) -> Option<(usize, usize)> {
    let which = palettes.len() + used;
    if which >= OBJ_PALETTES {
        return None;
    }
    let base = rounded_to_row(tiles.len() / 32);
    grow(tiles, base + ANIMATION_TILES);
    Some((base, which))
}
