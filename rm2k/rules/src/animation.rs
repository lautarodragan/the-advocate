//! The ChipSet's animation: two of them, unrelated, running at once, both in
//! easyrpg's `TilemapLayer::Draw`.
//!
//! ```text
//! the A/B/C water autotiles   3 drawings, one every WATER_FRAMES_* frames
//! the animated tiles          4 drawings, one every ANIMATED_FRAMES
//! ```
//!
//! The clock is the system's frame counter, which does not restart when the
//! map changes.

use ditto::schema::ChipsetAnimType;

/// Frames per water step, by the ChipSet's `animation_speed`: 0 is slow, and
/// anything else fast —`Game_Map::GetAnimationSpeed`—.
pub const WATER_FRAMES_SLOW: u32 = 24;
pub const WATER_FRAMES_FAST: u32 = 12;

/// Three drawings walked in four steps, the fourth repeating the second. It
/// is the same shape in both places RM2k has it: the water with
/// `animation_type` reciprocating —the default—, and a character's walk,
/// which has three columns and draws column 1 on step 3.
pub const CYCLE_OF_THREE: [u32; 4] = [0, 1, 2, 1];

/// Frames per step of the animated tiles, and how many drawings they have.
pub const ANIMATED_FRAMES: u32 = 6;
pub const ANIMATED_STEPS: u32 = 4;

/// Which of the three water drawings shows at `frame`.
///
/// Reciprocating goes 0, 1, 2, 1; any other type —cyclic, or a number the
/// table does not name—, 0, 1, 2 in a circle, because easyrpg only asks
/// whether it is zero.
pub fn water_drawing(frame: u32, animation_type: ChipsetAnimType, animation_speed: i32) -> u32 {
    let frames = if animation_speed == 0 {
        WATER_FRAMES_SLOW
    } else {
        WATER_FRAMES_FAST
    };
    let step = frame / frames;
    if animation_type.to_i32() != 0 {
        step % 3
    } else {
        CYCLE_OF_THREE[(step % 4) as usize]
    }
}

/// Which of the four drawings of the animated tiles shows at `frame`.
pub fn animated_drawing(frame: u32) -> u32 {
    (frame / ANIMATED_FRAMES) % ANIMATED_STEPS
}
