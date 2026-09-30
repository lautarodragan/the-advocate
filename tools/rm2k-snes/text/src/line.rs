//! A line of text drawn the way RM2k draws it: each glyph as a mask over
//! the System's colour block, with its shadow one pixel down and to the
//! right.
//!
//! It is easyrpg-player's `Font::Render`, and none of its numbers is
//! guessed: they come from `font.cpp`. The colour of a glyph pixel is not a
//! flat colour but the pixel at the same place of the System's 16x16 block
//! —text colour `n`, or the shadow's—, so a letter comes out with the
//! block's vertical gradient:
//!
//! ```text
//! text    the block of colour n, from (2, 4): the 12-row glyph rests
//!         against the foot of the 16-row block
//! shadow  the shadow's block, from (0, 0), drawn first and shifted one
//!         pixel in x and in y
//! ```
//!
//! Whatever goes past the picture it is drawn on is cut.

use crate::font;
use rm2k_render::picture::Picture;
use rm2k_render::system;

/// Where, inside the colour block, glyph pixel `(0, 0)` takes its colour
/// from.
pub const TEXT_OFFSET: (usize, usize) = (2, 4);

/// The two blocks a line of text in colour `color` takes its pixels from.
pub struct Ink {
    text: Picture,
    shadow: Picture,
}

impl Ink {
    /// The ink of text colour `color`, 0 to 19, of `system`, the System
    /// already read with its colour key.
    pub fn new(system: &Picture, color: i32) -> Ink {
        Ink {
            text: system::text_color(system, color),
            shadow: system::shadow(system),
        }
    }

    /// The colour glyph pixel `(x, y)` is drawn with.
    pub fn text_at(&self, x: usize, y: usize) -> [u8; 4] {
        self.text
            .get((TEXT_OFFSET.0 + x) as i64, (TEXT_OFFSET.1 + y) as i64)
    }

    /// The colour the shadow of glyph pixel `(x, y)` is drawn with.
    pub fn shadow_at(&self, x: usize, y: usize) -> [u8; 4] {
        self.shadow.get(x as i64, y as i64)
    }
}

/// Draws `text` on `dest` from `(x, y)` in text colour `color` with its
/// shadow, and returns the `x` it ended at: one glyph is [`font::WIDTH`]
/// wide.
///
/// Pixel by pixel, the shadow first and the letter after, so the letter
/// covers the shadow where they overlap —it is easyrpg's order and it
/// shows on the diagonals—. A pixel is **replaced**, not blended: the
/// colour block's alpha only says whether it is drawn.
#[allow(clippy::too_many_arguments)]
pub fn draw_line(
    dest: &mut Picture,
    system: &Picture,
    x: i64,
    y: i64,
    text: &str,
    color: i32,
    font_id: i32,
) -> i64 {
    let ink = Ink::new(system, color);
    let mut x = x;
    for ch in text.chars() {
        for (px, py) in font::pixels(ch, font_id) {
            for (d, pixel) in [(1, ink.shadow_at(px, py)), (0, ink.text_at(px, py))] {
                let dx = x + px as i64 + d;
                let dy = y + py as i64 + d;
                if pixel[3] != 0
                    && dx >= 0
                    && dy >= 0
                    && (dx as usize) < dest.width
                    && (dy as usize) < dest.height
                {
                    let at = (dy as usize * dest.width + dx as usize) * 4;
                    dest.rgba[at..at + 4].copy_from_slice(&pixel);
                }
            }
        }
        x += font::WIDTH as i64;
    }
    x
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A System whose text colour 0 is all red and whose shadow is all
    /// blue, and nothing else.
    fn system() -> Picture {
        let mut out = Picture::transparent(160, 80);
        let (tx, ty) = rm2k_rules::system::text_color_origin(0);
        let (sx, sy) = rm2k_rules::system::SHADOW;
        for y in 0..16 {
            for x in 0..16 {
                let t = ((ty as usize + y) * 160 + tx as usize + x) * 4;
                out.rgba[t..t + 4].copy_from_slice(&[255, 0, 0, 255]);
                let s = ((sy as usize + y) * 160 + sx as usize + x) * 4;
                out.rgba[s..s + 4].copy_from_slice(&[0, 0, 255, 255]);
            }
        }
        out
    }

    #[test]
    fn the_letter_covers_its_shadow_and_is_cut_at_the_edge() {
        let mut dest = Picture::transparent(8, 8);
        let end = draw_line(&mut dest, &system(), 0, -1, "ll", 0, font::MINCHO);
        assert_eq!(end, 12);
        let mut red = 0;
        let mut blue = 0;
        for p in dest.rgba.chunks(4) {
            match p {
                [255, 0, 0, 255] => red += 1,
                [0, 0, 255, 255] => blue += 1,
                _ => {}
            }
        }
        assert!(red > 0 && blue > 0);
    }
}
