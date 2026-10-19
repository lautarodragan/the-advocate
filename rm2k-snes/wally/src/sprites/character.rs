//! A character of a CharSet as a Super Nintendo object: its colours, its
//! palette and its poses as tiles.
//!
//! An RM2k CharSet is 4 characters across by 2 down; each takes 72x128 and
//! has 12 poses of 24x32, three walking frames in four directions. The
//! console has no 24x32 object: the smallest that covers a pose is 32x32,
//! so it is padded with transparency at the sides. And objects are always
//! 4 bits a pixel: a character has to fit in fifteen colours.

use crate::sprites::fail::{Bad, Result};
use adeleine::{lab_distance, merge_least_visible, Color};
use rm2k_render::Picture;
use std::collections::{BTreeSet, HashMap};
use voodoo::pack_tile;

pub const SPRITE_W: usize = 24;
pub const SPRITE_H: usize = 32;
/// The object's real size on screen.
pub const OBJ_W: usize = 32;
pub const OBJ_H: usize = 32;
/// Four bits a pixel, and 0 is transparent.
pub const OBJ_COLORS: usize = 15;
pub const SPRITE_POSES: i32 = 12;
/// Facing down, the middle frame.
pub const INITIAL_POSE: i32 = 2 * 3 + 1;
/// Eight object palettes, with or without the timer.
pub const OBJ_PALETTES: usize = 8;
/// The object name table is 16 tiles wide, so a 32x32 object is a 4x4
/// square inside that grid and not sixteen tiles in a row.
pub const OBJ_ROW: usize = 16;
/// A pose in the cartridge: its sixteen tiles in a row, by rows.
pub const POSE_BYTES: usize = 16 * 32;

/// A (CharSet, index) pair: a character, by the name the port gives its
/// sheet.
pub type Key = (String, i32);

/// The sheets the characters are cut from, by name; `None` for one that
/// could not be drawn.
pub type Sheets = HashMap<String, Option<Picture>>;

/// The poses a character can show; `None` for all twelve.
pub type Poses = Option<BTreeSet<i32>>;

/// The sheet of `name`, or the answer that it is missing.
pub fn sheet<'a>(sheets: &'a Sheets, name: &str) -> Result<&'a Picture> {
    sheets
        .get(name)
        .and_then(Option::as_ref)
        .ok_or_else(|| Bad::new(format!("can't find CharSet {name:?}")))
}

/// Where a pose starts inside the CharSet.
pub fn pose_origin(index: i32, pose: i32) -> (i64, i64) {
    (
        ((index % 4) * SPRITE_W as i32 * 3 + (pose % 3) * SPRITE_W as i32) as i64,
        ((index / 4) * SPRITE_H as i32 * 4 + (pose / 3) * SPRITE_H as i32) as i64,
    )
}

/// All twelve poses.
pub fn all_poses() -> BTreeSet<i32> {
    (0..SPRITE_POSES).collect()
}

/// The character's colours at 15 bits, with how many pixels each one
/// covers, over the poses it can show —all twelve with `None`—. They come
/// in the order they are first met, pose by pose and row by row: a merge
/// breaks its ties by the colour and not by this order, but a fixed one
/// keeps every run the same.
///
/// **Counting all twelve when three are seen gives colour memory away**: a
/// save point that animates facing up can have three times the colours in
/// its whole block than in the three frames it shows.
pub fn sprite_colors(
    image: &Picture,
    index: i32,
    poses: Option<&BTreeSet<i32>>,
) -> Vec<(Color, u64)> {
    let all = all_poses();
    let poses = poses.unwrap_or(&all);
    let mut order = Vec::new();
    let mut count: HashMap<Color, u64> = HashMap::new();
    for &pose in poses {
        let (ox, oy) = pose_origin(index, pose);
        for y in 0..SPRITE_H as i64 {
            for x in 0..SPRITE_W as i64 {
                let p = image.get(ox + x, oy + y);
                if p[3] == 0 {
                    continue;
                }
                let c = [p[0] >> 3, p[1] >> 3, p[2] >> 3];
                let n = count.entry(c).or_insert_with(|| {
                    order.push(c);
                    0
                });
                *n += 1;
            }
        }
    }
    order.into_iter().map(|c| (c, count[&c])).collect()
}

/// A character's palette, and how each colour maps to an index.
///
/// It is the same computation for the pose that goes to VRAM and for the
/// cartridge's pose bank, and it has to be: a pose uploaded on the fly is
/// drawn with the palette already in colour memory.
///
/// `cap` lowers the colours below fifteen —to make room for the timer—, and
/// `poses` are the ones the event can show: the fifteen colours are chosen
/// looking only at those. Who decides both is the split of the map's
/// palettes; here they are only obeyed.
///
/// The mapping covers **every** colour of the twelve poses, not only those
/// of `poses`: a colour left out of the count goes to the nearest of the
/// survivors —by distance, then by colour—, so asking for one pose too many
/// draws it and does not fail.
///
/// Returns the palette, sorted; each colour of it to its index, from 1; and
/// each colour of the sheet to the one of the palette it becomes.
/// What [`character_palette`] makes: the palette, each colour's index, and
/// what each colour of the sheet becomes.
pub type CharacterPalette = (Vec<Color>, HashMap<Color, u8>, HashMap<Color, Color>);

pub fn character_palette(
    image: &Picture,
    index: i32,
    cap: Option<usize>,
    poses: Option<&BTreeSet<i32>>,
) -> Result<CharacterPalette> {
    let cap = cap.unwrap_or(OBJ_COLORS);
    let counts = sprite_colors(image, index, poses);
    let mut mapping: HashMap<Color, Color> = if counts.len() <= cap {
        counts.iter().map(|&(c, _)| (c, c)).collect()
    } else {
        let merged = merge_least_visible(&counts, cap)?;
        counts.iter().map(|&(c, _)| c).zip(merged.mapping).collect()
    };
    let palette: Vec<Color> = mapping
        .values()
        .copied()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    if poses.is_some() && !palette.is_empty() {
        for (color, _) in sprite_colors(image, index, None) {
            if mapping.contains_key(&color) {
                continue;
            }
            // Sorted, so the first on a tie is the lowest colour.
            mapping.insert(color, nearest(&palette, color));
        }
    }
    let lookup = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, (i + 1) as u8))
        .collect();
    Ok((palette, lookup, mapping))
}

/// The sixteen tiles of a pose, by rows: four rows of four, which is the
/// order the PPU reads a 32x32 object in, and why a pose is uploaded with
/// four transfers of 128 bytes.
pub fn pose_tiles(
    image: &Picture,
    index: i32,
    pose: i32,
    lookup: &HashMap<Color, u8>,
    mapping: &HashMap<Color, Color>,
) -> Result<Vec<Vec<u8>>> {
    let (ox, oy) = pose_origin(index, pose);
    let margin = (OBJ_W - SPRITE_W) / 2;
    let mut whole = [[0u8; OBJ_W]; OBJ_H];
    for (y, row) in whole.iter_mut().enumerate().take(SPRITE_H) {
        for x in 0..SPRITE_W {
            let p = image.get(ox + x as i64, oy + y as i64);
            if p[3] == 0 {
                continue;
            }
            let c = [p[0] >> 3, p[1] >> 3, p[2] >> 3];
            let entry = mapping.get(&c).and_then(|m| lookup.get(m)).ok_or_else(|| {
                Bad::new(format!("colour {c:?} of pose {pose} has no palette entry"))
            })?;
            row[margin + x] = *entry;
        }
    }
    let mut tiles = Vec::with_capacity(16);
    for ty in 0..4 {
        for tx in 0..4 {
            let mut cell = [[0u8; 8]; 8];
            for (y, row) in cell.iter_mut().enumerate() {
                row.copy_from_slice(&whole[ty * 8 + y][tx * 8..tx * 8 + 8]);
            }
            tiles.push(pack_tile(&cell, 4));
        }
    }
    Ok(tiles)
}

/// The tile number where a 32x32 block starts: four blocks fit across the
/// sixteen-wide name grid.
pub fn block_tile(block: usize) -> usize {
    (block / 4) * 64 + (block % 4) * 4
}

/// The nearest colour of `palette` to `color`, the first one on a tie.
///
/// Nearest as it looks, in CIE Lab, and not by the luma distance the merges
/// use: what lands here is a colour drawn with one it is not, often of
/// someone else's palette, and the luma distance, which barely sees blue,
/// sends a grey to an olive of its light. Until 2026-10-17 it was the luma
/// one.
pub fn nearest(palette: &[Color], color: Color) -> Color {
    let mut best = palette[0];
    for &p in &palette[1..] {
        if lab_distance(p, color) < lab_distance(best, color) {
            best = p;
        }
    }
    best
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A sheet whose character 0 draws `colors` colours in blocks.
    fn sheet(colors: u8) -> Picture {
        let mut picture = Picture::transparent(288, 256);
        for y in 0..128 {
            for x in 0..72 {
                let k = ((x / 3 + y / 4) % colors as usize) as u8;
                let at = (y * 288 + x) * 4;
                picture.rgba[at..at + 4].copy_from_slice(&[k * 8, 255 - k * 8, k * 4, 255]);
            }
        }
        picture
    }

    #[test]
    fn a_block_is_a_four_by_four_square_of_the_grid() {
        assert_eq!(block_tile(0), 0);
        assert_eq!(block_tile(3), 12);
        assert_eq!(block_tile(4), 64);
        assert_eq!(block_tile(5), 68);
    }

    #[test]
    fn a_palette_is_fifteen_colours_and_covers_every_pose() {
        let image = sheet(30);
        let (palette, lookup, mapping) = character_palette(&image, 0, None, None).unwrap();
        assert_eq!(palette.len(), OBJ_COLORS);
        assert!(palette.windows(2).all(|w| w[0] < w[1]), "sorted");
        assert_eq!(lookup[&palette[0]], 1);
        for (c, _) in sprite_colors(&image, 0, None) {
            assert!(palette.contains(&mapping[&c]));
        }
        // Counting one pose, the colours of the others still map somewhere.
        let one = BTreeSet::from([7]);
        let (_, _, mapping) = character_palette(&image, 0, Some(4), Some(&one)).unwrap();
        for (c, _) in sprite_colors(&image, 0, None) {
            assert!(mapping.contains_key(&c));
        }
    }

    #[test]
    fn a_pose_is_sixteen_tiles() {
        let image = sheet(5);
        let (_, lookup, mapping) = character_palette(&image, 0, None, None).unwrap();
        let tiles = pose_tiles(&image, 0, INITIAL_POSE, &lookup, &mapping).unwrap();
        assert_eq!(tiles.len(), 16);
        assert!(tiles.iter().all(|t| t.len() == 32));
    }

    #[test]
    fn the_nearest_colour_is_the_first_on_a_tie() {
        // The same distance from (20, 10, 5), in tenths of Lab.
        let palette = [[19, 9, 5], [20, 11, 6]];
        assert_eq!(
            lab_distance(palette[0], [20, 10, 5]),
            lab_distance(palette[1], [20, 10, 5])
        );
        assert_eq!(nearest(&palette, [20, 10, 5]), [19, 9, 5]);
    }

    #[test]
    fn the_nearest_colour_sees_hue() {
        // To the luma distance an olive of nearly its light is nearer a
        // grey than a grey three steps darker.
        assert_eq!(
            nearest(&[[13, 13, 13], [17, 17, 8]], [16, 16, 16]),
            [13, 13, 13]
        );
    }
}
