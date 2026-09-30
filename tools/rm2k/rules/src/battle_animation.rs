//! A battle animation's sheet: the picture in `Battle/` its cells are cut
//! from.
//!
//! Five cells across, each a square of 96 —or 128 if the animation is
//! `large`, whose sheet is in `Battle2/`—, numbered row by row. It is
//! easyrpg's `BattleAnimation::DrawAt`: `cell_id % 5`, `cell_id / 5`, and
//! `size = large ? 128 : 96`.

/// The side of a cell of a sheet, and of a large one.
pub const CELL: i32 = 96;
pub const LARGE_CELL: i32 = 128;
/// How many cells a sheet has across.
pub const COLUMNS: i32 = 5;

/// The side of the cells of an animation's sheet.
pub fn cell_side(large: bool) -> i32 {
    if large {
        LARGE_CELL
    } else {
        CELL
    }
}

/// Where cell `cell_id` starts in the sheet. A negative id, which the
/// editor never writes, falls in a row above the sheet, outside it: there
/// is nothing to draw.
pub fn cell_origin(cell_id: i32, large: bool) -> (i32, i32) {
    let side = cell_side(large);
    (
        cell_id.rem_euclid(COLUMNS) * side,
        cell_id.div_euclid(COLUMNS) * side,
    )
}
