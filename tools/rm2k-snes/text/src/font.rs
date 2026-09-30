//! The letters: easyrpg-player's 6x12 fonts, and which one a game asks for.
//!
//! **Which of the two is used is decided by the game, not by us.** The
//! database's System carries `font_id`, and easyrpg's `Font::Default()`
//! picks rmg2000 when it is 1 —Mincho— and ttyp0 when it is 0 —Gothic—.
//! Both are here so the choice comes from the data: a window drawn with
//! the other one has the right colours and the wrong letters.
//!
//! Only printable ASCII: a character without a glyph is drawn as a space.

use crate::glyphs;

/// A glyph's size, in pixels.
pub const WIDTH: usize = 6;
pub const HEIGHT: usize = 12;

/// The two values of `font_id` in RM2k's System (`lcf::rpg::System::Font`).
pub const GOTHIC: i32 = 0;
pub const MINCHO: i32 = 1;

/// The first character with a glyph, and how many there are: the space to
/// the tilde.
pub const FIRST: u32 = 32;
pub const GLYPHS: usize = 95;

/// Every glyph of the font `font_id` asks for: Mincho for 1, Gothic for
/// anything else, as easyrpg does.
pub fn table(font_id: i32) -> &'static [[u8; HEIGHT]; GLYPHS] {
    if font_id == MINCHO {
        &glyphs::MINCHO
    } else {
        &glyphs::GOTHIC
    }
}

/// The twelve rows of `ch`'s glyph —bit `b` of a row is the pixel of
/// column `b`, bit 0 the leftmost—, or the space's if the font lacks it.
pub fn rows(ch: char, font_id: i32) -> &'static [u8; HEIGHT] {
    let table = table(font_id);
    let code = ch as u32;
    if (FIRST..FIRST + GLYPHS as u32).contains(&code) {
        &table[(code - FIRST) as usize]
    } else {
        &table[0]
    }
}

/// The lit pixels of `ch`'s glyph, `(x, y)`, row by row and left to right.
pub fn pixels(ch: char, font_id: i32) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    for (y, row) in rows(ch, font_id).iter().enumerate() {
        for x in 0..WIDTH {
            if row >> x & 1 != 0 {
                out.push((x, y));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_character_the_font_lacks_is_a_space() {
        assert_eq!(rows('é', MINCHO), rows(' ', MINCHO));
        assert!(pixels(' ', MINCHO).is_empty());
    }

    #[test]
    fn the_font_is_the_one_the_game_asks_for() {
        assert_ne!(rows('g', MINCHO), rows('g', GOTHIC));
        assert_eq!(rows('g', 7), rows('g', GOTHIC));
    }
}
