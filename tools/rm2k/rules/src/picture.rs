//! A picture of `ShowPicture`: what RM2k does to the file before putting it
//! on the screen.
//!
//! easyrpg's `Game_Pictures` and `Sprite_Picture`.

/// The opacity, out of 255, of a picture drawn at `top_trans` percent of
/// transparency: `Sprite_Picture`'s `255 * (100 - trans) / 100`, rounded
/// down. RM2k's editor keeps the value between 0 and 100.
pub fn opacity(top_trans: i32) -> u8 {
    (255 * (100 - top_trans.clamp(0, 100)) / 100) as u8
}
