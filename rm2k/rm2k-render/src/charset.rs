//! What an event is drawn with: a CharSet, or a tile of the ChipSet, and a
//! translucent one blended over what is behind it.
//!
//! Everything comes out as a **CharSet sheet**, the picture whose 24x32
//! poses the event is cut from: RM2k's layout, 4 characters by 2 of 12
//! poses each. Cutting a pose, and whatever a pose becomes afterwards, is
//! the caller's.
//!
//! * **A CharSet** is its file with the colour key applied, and nothing
//!   else: the poses are already where RM2k looks for them.
//! * **An event drawn with a tile** has no CharSet: RM2k draws tile `n` of
//!   the ChipSet's upper layer where the event stands, in every direction
//!   and step. Here it is a made-up sheet with that tile in the twelve poses
//!   of character 0, standing on its cell the way a pose stands on it, so it
//!   can be cut, moved and turned like any other.
//! * **A translucent page** is drawn by RM2k at
//!   [`TRANSLUCENT_OPACITY`](rm2k_rules::event::TRANSLUCENT_OPACITY) over
//!   whatever is behind. Given what is behind and the cell the event stands
//!   on, [`translucent`] blends every pose over the piece of it the pose
//!   would cover, and the sheet comes out opaque where the event has pixels:
//!   it is each pose as the screen would show it on that cell.
//!
//! What to put behind —which layers, what an event covers— is the caller's
//! to decide, as is whether the blend stays in a picture at all.

use crate::picture::Picture;
use rm2k_rules::charset::{self as rules, CHARACTER_HEIGHT, CHARACTER_WIDTH};
use rm2k_rules::chipset::{common_origin, TILE, TILES_PER_LAYER};
use rm2k_rules::event::TRANSLUCENT_OPACITY;

/// A CharSet sheet: 4 characters across by 2 down.
pub const SHEET_WIDTH: usize = (rules::CHARACTERS_ACROSS * CHARACTER_WIDTH) as usize;
pub const SHEET_HEIGHT: usize = (2 * CHARACTER_HEIGHT) as usize;

/// Upper-layer tile `index` —0 to 143, the id `UPPER + index`— of a ChipSet
/// already read with its colour key, as a 16x16 picture over transparency.
///
/// It is copied **through its alpha twice**, ChipSet to a cell and cell to
/// the tile: that is how the tile reached an event when the drawings this
/// replaces took it from the expanded atlas. With an indexed ChipSet, alpha
/// 0 or 255, it is a plain copy; with half transparencies each pass rounds,
/// and the pixels have to be those.
pub fn upper_tile(chipset: &Picture, index: i32) -> Picture {
    let (x, y) = common_origin(TILES_PER_LAYER + index);
    let side = TILE as usize;
    let mut cell = Picture::transparent(side, side);
    cell.blit(0, 0, chipset, x as i64, y as i64, TILE as i64, TILE as i64);
    let mut tile = Picture::transparent(side, side);
    tile.blit(0, 0, &cell, 0, 0, TILE as i64, TILE as i64);
    tile
}

/// The sheet of an event drawn with upper-layer tile `index`: the tile in
/// the twelve poses of character 0, standing on the cell —a pose is drawn
/// at `OFFSET_X`, `OFFSET_Y` of its cell, so the tile goes at the opposite
/// of that inside each pose—. The rest of the sheet is transparent.
pub fn tile_sheet(chipset: &Picture, index: i32) -> Picture {
    let tile = upper_tile(chipset, index);
    let mut sheet = Picture::transparent(SHEET_WIDTH, SHEET_HEIGHT);
    for pose in 0..rules::POSES {
        let x = (pose % 3) * rules::POSE_WIDTH - rules::OFFSET_X;
        let y = (pose / 3) * rules::POSE_HEIGHT - rules::OFFSET_Y;
        sheet.put(x as usize, y as usize, &tile);
    }
    sheet
}

/// `sheet` drawn translucent on cell `(x, y)` of `behind`: every pixel the
/// sheet has is mixed with the one of `behind` its pose covers there, at
/// RM2k's opacity for a translucent page, and comes out opaque. The pixels
/// it does not have stay as they are, transparent.
///
/// All the poses stand on the same cell, so each one is blended over the
/// same piece of `behind`, and a pixel's place inside its pose is all that
/// is needed. Past the edges of `behind` there is nothing drawn, and RM2k
/// shows black there.
///
/// The mix is `(over * 160 + under * 95) / 255`, **rounded down**, and the
/// sheet's own alpha does not weigh in —any pixel that is not fully
/// transparent is mixed whole—: those are the pixels of the drawing this
/// replaces.
pub fn translucent(sheet: &Picture, behind: &Picture, x: i64, y: i64) -> Picture {
    let alpha = TRANSLUCENT_OPACITY as u32;
    let origin_x = x * TILE as i64 + rules::OFFSET_X as i64;
    let origin_y = y * TILE as i64 + rules::OFFSET_Y as i64;
    let mut out = sheet.clone();
    for py in 0..sheet.height {
        let by = origin_y + (py as i64 % rules::POSE_HEIGHT as i64);
        for px in 0..sheet.width {
            let at = (py * sheet.width + px) * 4;
            if sheet.rgba[at + 3] == 0 {
                continue;
            }
            let bx = origin_x + (px as i64 % rules::POSE_WIDTH as i64);
            let under = behind.get(bx, by);
            for (c, under) in under.iter().take(3).enumerate() {
                let over = sheet.rgba[at + c] as u32;
                out.rgba[at + c] = ((over * alpha + *under as u32 * (255 - alpha)) / 255) as u8;
            }
            out.rgba[at + 3] = 255;
        }
    }
    out
}
