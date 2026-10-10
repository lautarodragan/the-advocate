//! A CharSet: the picture characters are drawn from.
//!
//! It holds 4 characters across by 2 down; each one takes 72x128 and has 12
//! poses, 3 walking columns by 4 directions, of 24x32 each.

use ditto::schema::{EventPageDirection, EventPageFrame};

/// A pose.
pub const POSE_WIDTH: i32 = 24;
pub const POSE_HEIGHT: i32 = 32;
/// A character: 3 columns by 4 rows of poses.
pub const CHARACTER_WIDTH: i32 = 3 * POSE_WIDTH;
pub const CHARACTER_HEIGHT: i32 = 4 * POSE_HEIGHT;
/// How many characters a CharSet has across.
pub const CHARACTERS_ACROSS: i32 = 4;
pub const POSES: i32 = 12;

/// Where a pose is drawn from its 16x16 cell: it is wider and taller than
/// the cell, so it is centered across and stands on its feet.
pub const OFFSET_X: i32 = -(POSE_WIDTH - crate::chipset::TILE) / 2;
pub const OFFSET_Y: i32 = -(POSE_HEIGHT - crate::chipset::TILE);

/// The walking column a pattern draws: the walk is four phases over three
/// columns, and the fourth —`middle2`— draws the middle one again.
pub fn column(pattern: EventPageFrame) -> i32 {
    match pattern {
        EventPageFrame::Middle2 => 1,
        other => other.to_i32(),
    }
}

/// The pose, 0 to 11, a direction and a pattern draw: the rows of a
/// character are the directions, in the format's order —up, right, down,
/// left—.
pub fn pose(direction: EventPageDirection, pattern: EventPageFrame) -> i32 {
    direction.to_i32() * 3 + column(pattern)
}

/// Where character `index`, 0 to 7, starts in the CharSet.
pub fn character_origin(index: i32) -> (i32, i32) {
    (
        (index % CHARACTERS_ACROSS) * CHARACTER_WIDTH,
        (index / CHARACTERS_ACROSS) * CHARACTER_HEIGHT,
    )
}
