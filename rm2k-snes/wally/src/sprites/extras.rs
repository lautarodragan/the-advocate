//! What goes at the end of the sprite bank besides the characters: the
//! timer's digits, the raindrops, a `ShowPicture` picture and the battle
//! animation's box, each with its tiles and the palette it takes.
//!
//! The first two share a palette with whoever has room; the last two take a
//! whole one each, above the characters', because what is in it fades or
//! changes with them.

use crate::sprites::character::{nearest, OBJ_COLORS, OBJ_PALETTES};
use crate::sprites::fail::{Bad, Result};
use adeleine::{luma_distance, Color};
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

/// The raindrops' tiles across: one per grey, each two tall.
pub const RAIN_TILES: usize = 3;

/// The battle animation's box: one row of blocks, four 32x32 objects.
pub const ANIMATION_TILES: usize = 64;

/// A row of blocks: what the arithmetic of 32x32 objects needs whole.
const BLOCK_ROW: usize = 64;

fn rounded_to_row(tiles: usize) -> usize {
    tiles.div_ceil(BLOCK_ROW) * BLOCK_ROW
}

/// Where a strip `width` tiles across and two tall —the timer's glyphs,
/// the raindrops— goes after a bank `tiles` long: in the columns the last
/// row of blocks leaves free, if it is partly taken and they are enough,
/// or at the next row of blocks.
///
/// The free columns are worth slots: a map with a cache gets as many as
/// fit after the extras, so a strip that always took a new row cost it up
/// to four —Vampires Dawn's 51 went from 30 to 26 when its rain came back,
/// 2026-10-16—. The console reads the strip's tiles by number, which is
/// any, and nobody uploads a pose into a block past the slots.
///
/// A row is taken by blocks when it ends where a block's last tile row
/// does, `3 * 16 + 4` past the block's first tile; anything else —a bank
/// cut short, another strip— is not looked into and the strip goes on.
pub fn strip_base(tiles: usize, width: usize) -> usize {
    let row = tiles / BLOCK_ROW * BLOCK_ROW;
    let used = tiles - row;
    if used == 0 {
        return row;
    }
    if used >= 3 * 16 + 4 && (used - 3 * 16) % 4 == 0 {
        let column = used - 3 * 16;
        if column + width <= 16 {
            return row + column;
        }
    }
    row + BLOCK_ROW
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

/// Which entries of `palette` the timer's `colors` take, one bit per entry,
/// counting the transparent one as entry 0: each colour at the first entry
/// that has it, which is the one its glyphs were painted with —or at its
/// nearest, if the timer was lent the palette: see `timer_digits`—. The
/// console uploads **those** again untinted after a tint, and not the whole
/// palette, because the palette belongs to a character that is tinted.
pub fn timer_mask(colors: &[Color], palette: &[Color]) -> u16 {
    colors
        .iter()
        .map(|c| entry_of(palette, *c))
        .fold(0, |mask, at| mask | 1 << (at + 1))
}

/// Where a glyph colour is painted in `palette`: its first entry, or its
/// nearest's when the timer was lent the palette.
fn entry_of(palette: &[Color], color: Color) -> usize {
    let at = nearest(palette, color);
    palette.iter().position(|p| *p == at).unwrap()
}

/// The timer's colours with how many pixels of the glyphs each paints.
fn timer_counts(glyphs: &Picture) -> BTreeMap<Color, u64> {
    let mut counts = BTreeMap::new();
    for y in 0..TIMER_GLYPH_H as i64 {
        for x in 0..(TIMER_GLYPHS * TIMER_GLYPH_W) as i64 {
            let p = glyphs.get(x, y);
            if p[3] != 0 {
                *counts.entry([p[0] >> 3, p[1] >> 3, p[2] >> 3]).or_insert(0) += 1;
            }
        }
    }
    counts
}

/// The palette —but the leaders'— whose nearest colours draw the timer
/// with the least change: pixels times distance, the same measure
/// `nearest` uses. `None` if every palette is a leader's.
fn closest_for_timer(glyphs: &Picture, palettes: &[Vec<Color>], leader_owned: &BTreeSet<usize>) -> Option<usize> {
    let counts = timer_counts(glyphs);
    let mut best: Option<(u64, usize)> = None;
    for (number, palette) in palettes.iter().enumerate() {
        if leader_owned.contains(&number) || palette.is_empty() {
            continue;
        }
        let cost: u64 = counts.iter().map(|(c, n)| n * luma_distance(nearest(palette, *c), *c) as u64).sum();
        if best.is_none_or(|(b, _)| cost < b) {
            best = Some((cost, number));
        }
    }
    best.map(|(_, n)| n)
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
    for (number, palette) in palettes.iter_mut().enumerate() {
        if avoid.contains(&number) {
            continue;
        }
        let mut union = palette.clone();
        union.extend(colors.iter().filter(|c| !palette.contains(c)));
        if union.len() <= OBJ_COLORS {
            *palette = union;
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
///
/// **And with no room anywhere, the timer is lent a palette**, as a
/// character is: the one whose nearest colours change it the least, each
/// glyph colour drawn with its nearest. It is the last way out, after the
/// split brought a character down a colour if it could. It was born for
/// Paradise (ABL's 108) with every leader of the game, where all eight
/// palettes are full and lend themselves: black is in all of them, and the
/// red becomes the nearest red. A timer a little off is better than none
/// in a map where it runs; `extras` says which palette in a WARNING.
pub fn timer_digits(
    glyphs: &Picture,
    tiles: &mut Vec<u8>,
    palettes: &mut Vec<Vec<Color>>,
    leader_owned: &BTreeSet<usize>,
    cap: usize,
    rain: bool,
) -> Result<(usize, usize)> {
    let wanted = timer_colors(glyphs);
    if wanted.len() > OBJ_COLORS {
        return Err(Bad::new(format!(
            "the timer digits use {} colors and {OBJ_COLORS} fit",
            wanted.len()
        )));
    }
    let mut which = None;
    for (number, palette) in palettes.iter_mut().enumerate() {
        if leader_owned.contains(&number) {
            continue;
        }
        let mut union = palette.clone();
        union.extend(wanted.iter().filter(|c| !palette.contains(c)));
        if union.len() <= OBJ_COLORS {
            *palette = union;
            which = Some(number);
            break;
        }
    }
    let which = match which {
        Some(n) => n,
        None => {
            if palettes.len() >= cap {
                closest_for_timer(glyphs, palettes, leader_owned).ok_or_else(|| {
                    Bad::new(format!(
                        "the timer doesn't fit: the map uses the {cap} sprite palettes it gets \
                         and all of them are the leaders'"
                    ))
                })?
            } else {
                palettes.push(wanted.clone());
                palettes.len() - 1
            }
        }
    };
    let palette = &palettes[which];
    let index: BTreeMap<Color, u8> = wanted.iter().map(|c| (*c, entry_of(palette, *c) as u8 + 1)).collect();
    let base = strip_base(tiles.len() / 32, TIMER_GLYPHS + if rain { RAIN_TILES } else { 0 });
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
/// has five places to spare; without it, where [`strip_base`] says.
///
/// **With no palette with room, the drops are lent one**, as the timer
/// is: see [`lend_to_rain`]. Nobody loses a colour for it. Until
/// 2026-10-17 such a map drew no rain, and taro's word is that the rain is
/// not given up: a drop is a 4x16 streak in three greys, and one a shade
/// off is still rain. `None` only if every palette is a leader's or the
/// timer's.
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
    let which = match first_place(palettes, &avoid, &RAIN_COLORS, cap) {
        Some(n) => n,
        None => lend_to_rain(palettes, &avoid)?,
    };
    let palette = palettes[which].clone();
    let base = match timer {
        Some((base, _)) if base != 0 => base + TIMER_GLYPHS,
        _ => strip_base(tiles.len() / 32, RAIN_TILES),
    };
    grow(tiles, base + 16 + RAIN_TILES);
    let streak: BTreeSet<(i32, i32)> = rain_pixels(0, 0).into_iter().collect();
    for (hue, color) in RAIN_COLORS.iter().enumerate() {
        let index = entry_of(&palette, *color) as u8 + 1;
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

/// The palette —but the `avoid`ed— the drops are lent when none has room
/// for their three greys: each takes in the greys it has room for, the
/// farthest from what it has first, and the one whose nearest colours are
/// then closest to the rest wins, the first on a tie. It is grown with
/// those greys and its number returned; `None` if all are avoided.
fn lend_to_rain(palettes: &mut [Vec<Color>], avoid: &BTreeSet<usize>) -> Option<usize> {
    let mut best: Option<(u64, usize, Vec<Color>)> = None;
    for (number, palette) in palettes.iter().enumerate() {
        if avoid.contains(&number) || palette.is_empty() {
            continue;
        }
        let mut grown = palette.clone();
        let mut missing: Vec<Color> = RAIN_COLORS.iter().copied().filter(|c| !palette.contains(c)).collect();
        missing.sort_by_key(|c| std::cmp::Reverse(luma_distance(nearest(palette, *c), *c)));
        let room = OBJ_COLORS.saturating_sub(palette.len());
        grown.extend(missing.iter().take(room));
        let cost: u64 = RAIN_COLORS.iter().map(|c| luma_distance(nearest(&grown, *c), *c) as u64).sum();
        if best.as_ref().is_none_or(|(b, ..)| cost < *b) {
            best = Some((cost, number, grown));
        }
    }
    let (_, number, grown) = best?;
    palettes[number] = grown;
    Some(number)
}

/// The `ShowPicture` pictures of a map, already cut into tiles by whoever
/// decided they are this map's: tile number (from the base) to its 8x8
/// cell of 4-bit indices, and how many tiles they reserve.
#[derive(Clone, Debug, Default)]
pub struct Image {
    pub tiles: usize,
    pub cells: Vec<(usize, [[u8; 8]; 8])>,
}

/// The pictures at the end of the bank, and **the `shared` whole palettes
/// their colours go in**, from the last one down —the first takes palette
/// 7—: not added to the list, because a picture's colours are its own and
/// are uploaded with its fade, and from the top because the palettes 4 to 7
/// are the ones the console can blend. `None` if the map's palettes leave
/// fewer than that. After the timer or the drops, they start
/// two rows of sixteen later, rounded to a row of blocks.
pub fn picture_of_image(
    image: &Image,
    tiles: &mut Vec<u8>,
    palettes: &[Vec<Color>],
    previous_base: usize,
    shared: usize,
) -> Option<(usize, usize)> {
    if palettes.len() + shared > OBJ_PALETTES {
        return None;
    }
    let base = if previous_base != 0 {
        (previous_base + 2 * 16).div_ceil(BLOCK_ROW) * BLOCK_ROW
    } else {
        rounded_to_row(tiles.len() / 32)
    };
    grow(tiles, base + image.tiles);
    for (number, cell) in &image.cells {
        put(tiles, base + number, cell);
    }
    Some((base, shared))
}

/// The battle animation's box at the end of the bank: its tiles, left
/// blank —the console uploads each frame—, and a whole palette, the first
/// free one under the `top` the pictures took. `None` without a palette.
pub fn map_animation(tiles: &mut Vec<u8>, palettes: &[Vec<Color>], top: usize) -> Option<(usize, usize)> {
    let which = palettes.len();
    if which + top >= OBJ_PALETTES {
        return None;
    }
    let base = rounded_to_row(tiles.len() / 32);
    grow(tiles, base + ANIMATION_TILES);
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
        let (_, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES, false).unwrap();
        assert_eq!(p.len(), OBJ_PALETTES);
        assert!(p[which].len() <= OBJ_COLORS);
    }

    /// With the eight full the timer is lent the palette that draws it with
    /// the least change, as a character would be, and none grows: here the
    /// one with black and a red close to the System's. Until 2026-10-14
    /// this stopped the conversion.
    #[test]
    fn with_the_eight_full_the_timer_is_lent_the_closest() {
        let mut p = palettes(15, 8);
        p[5][3] = [0, 0, 0];
        p[5][9] = [29, 2, 1];
        let before = p.clone();
        let mut tiles = vec![0; 32 * 64];
        let (base, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::from([0, 1]), OBJ_PALETTES, false).unwrap();
        assert_eq!(which, 5);
        assert_eq!(p, before, "no palette grows");
        // Glyph 0's first row, as the System draws it: entry 4 for black and
        // entry 10 for red.
        let mask = timer_mask(&timer_colors(&glyphs()), &p[5]);
        assert_eq!(mask, 1 << 4 | 1 << 10);
        let row: Vec<u8> = (0..8)
            .map(|x| {
                let bit = 7 - x;
                (0..4).map(|plane| {
                    let byte = tiles[base * 32 + [0, 1, 16, 17][plane]];
                    (byte >> bit & 1) << plane
                }).sum()
            })
            .collect();
        let want: Vec<u8> = (0..8)
            .map(|x| match (x % 3, x % 2) {
                (0, _) => 0,
                (_, 0) => 10,
                _ => 4,
            })
            .collect();
        assert_eq!(row, want);
    }

    /// With the eight full and all of them the leaders', there is nothing
    /// to lend, and it says so.
    #[test]
    fn if_every_palette_is_a_leaders_it_says_so() {
        let mut p = palettes(15, 8);
        let mut tiles = vec![0; 32 * 64];
        let leaders: BTreeSet<usize> = (0..8).collect();
        assert!(timer_digits(&glyphs(), &mut tiles, &mut p, &leaders, OBJ_PALETTES, false).is_err());
    }

    /// The console overwrites the leaders' slot with the colours of whoever
    /// leads, so a digit there would lose its red: the first palette with
    /// room is skipped if it is a leader's. No map of the game reaches this
    /// path, which is why it is made up.
    #[test]
    fn the_timer_does_not_land_in_a_leaders_slot() {
        let mut p = vec![(0..4).map(|k| [1, 1, k]).collect(), (0..4).map(|k| [2, 2, k]).collect()];
        let mut tiles = vec![0; 32 * 64];
        let (_, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::from([0]), OBJ_PALETTES, false).unwrap();
        assert_eq!(which, 1);
    }

    /// With the eight palettes full the drops are lent the one whose
    /// nearest colours are closest, never a leader's, and drawn with those
    /// entries; one with room for a grey takes it in. Until 2026-10-17
    /// such a map drew no rain.
    #[test]
    fn with_the_eight_full_the_drops_are_lent_the_closest() {
        let mut p = palettes(15, 8);
        p[0] = RAIN_COLORS.iter().copied().chain((3..15).map(|k| [9, 9, k])).collect();
        p[4][0] = [15, 15, 17];
        p[4][1] = [7, 7, 7];
        p[6].pop();
        p[6][0] = [16, 16, 18];
        p[6][1] = [6, 6, 7];
        let mut tiles = vec![0; 32 * 64];
        let (base, which) = rain_drops(&mut tiles, &mut p, &BTreeSet::from([0]), None, OBJ_PALETTES).unwrap();
        assert_eq!(which, 6, "two greys and room for the third beat two near ones");
        assert_eq!(p[6].len(), OBJ_COLORS);
        assert!(RAIN_COLORS.iter().all(|c| p[6].contains(c)));
        // Without palette 6's room, 4 is the closest: drawn with its own
        // entries, and it does not grow.
        let mut p = palettes(15, 8);
        p[4][0] = [15, 15, 17];
        p[4][1] = [7, 7, 7];
        let before = p.clone();
        let (_, which) = rain_drops(&mut tiles, &mut p, &BTreeSet::new(), None, OBJ_PALETTES).unwrap();
        assert_eq!(which, 4);
        assert_eq!(p, before);
        // The top half of the lightest grey's tile: entry 1, [15, 15, 17].
        let pixel = |tile: usize, x: usize, y: usize| -> u8 {
            let bit = 7 - x;
            (0..4).map(|plane| (tiles[tile * 32 + [0, 1, 16, 17][plane] + 2 * y] >> bit & 1) << plane).sum()
        };
        assert_eq!(pixel(base, 3, 0), 1);
        // And with every palette a leader's, no rain.
        let mut p = palettes(15, 8);
        assert!(rain_drops(&mut tiles, &mut p, &(0..8).collect(), None, OBJ_PALETTES).is_none());
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

    /// The mask names the entries the glyphs were painted with: a palette
    /// that already had one of the timer's colours keeps it where it was,
    /// and the other is appended.
    #[test]
    fn the_mask_is_where_the_digits_colours_ended_up() {
        let mut p = vec![vec![[9, 9, 9], [0, 0, 0], [5, 5, 5]]];
        let mut tiles = vec![0; 32 * 64];
        let (_, which) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES, false).unwrap();
        assert_eq!(p[which], [[9, 9, 9], [0, 0, 0], [5, 5, 5], [31, 0, 0]]);
        // Black is entry 2 and red entry 4, counting the transparent one.
        assert_eq!(timer_mask(&timer_colors(&glyphs()), &p[which]), 0b10100);
    }

    /// A strip goes into the columns the last row of blocks leaves free,
    /// and to the next row when they are not enough or the row is whole.
    #[test]
    fn a_strip_goes_where_the_last_row_of_blocks_has_room() {
        // Blocks 0 to 4: block 4 alone in the second row, columns 4 to 15 free.
        let five = 64 + 3 * 16 + 4;
        assert_eq!(strip_base(five, RAIN_TILES), 64 + 4);
        assert_eq!(strip_base(five, TIMER_GLYPHS), 64 + 4);
        assert_eq!(strip_base(five, TIMER_GLYPHS + RAIN_TILES), 128);
        // Blocks 0 to 6: columns 12 to 15, room for the drops alone.
        let seven = 64 + 8 + 3 * 16 + 4;
        assert_eq!(strip_base(seven, RAIN_TILES), 64 + 12);
        assert_eq!(strip_base(seven, TIMER_GLYPHS), 128);
        // A whole row, or nothing: the next row starts there.
        assert_eq!(strip_base(128, RAIN_TILES), 128);
        assert_eq!(strip_base(0, RAIN_TILES), 0);
        // A bank cut short is not looked into.
        assert_eq!(strip_base(70, RAIN_TILES), 128);
    }

    /// The drops in the free columns of the last row: the bank does not
    /// grow, and they go at the top of the first free block.
    #[test]
    fn the_drops_take_no_row_of_their_own() {
        let mut p = palettes(4, 2);
        let blocks = 64 + 3 * 16 + 4;
        let mut tiles = vec![0; 32 * blocks];
        let (base, _) = rain_drops(&mut tiles, &mut p, &BTreeSet::new(), None, OBJ_PALETTES).unwrap();
        assert_eq!(base, 64 + 4);
        assert_eq!(tiles.len(), 32 * blocks);
    }

    /// The glyphs start at a row of blocks, eleven across and two tiles
    /// tall.
    #[test]
    fn the_digits_start_at_a_row_of_blocks() {
        let mut p = palettes(4, 2);
        let mut tiles = vec![0; 32 * 70];
        let (base, _) = timer_digits(&glyphs(), &mut tiles, &mut p, &BTreeSet::new(), OBJ_PALETTES, false).unwrap();
        assert_eq!(base, 128);
        assert_eq!(tiles.len(), (base + 16 + TIMER_GLYPHS) * 32);
    }
}
