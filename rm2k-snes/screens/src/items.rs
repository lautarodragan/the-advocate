//! The inks of the text screens —items, equipment, shop, and the battle's
//! text—: one palette per colour the screens write in —white, gray, "goes
//! up" and red—, all with the same layout, and the font precomposed for that
//! layout.
//!
//! Until 2026-10-03 this was a font: each character in two cells, in four
//! colours, which the cartridge wrote two tilemap words per letter. The text
//! is composed now —see `text_layer.s` in the runtime—, from tables like the
//! message window's: each glyph already shifted to each of the eight columns
//! of a cell and already painted, so drawing it is reading, masking and
//! writing. **The palettes share a layout** so that one table paints every
//! colour: entry 1 + k is the colour of the glyph's row k, and entry 13 the
//! shadow's. Which colour a cell shows is its palette in the tilemap.
//!
//! It was measured: painting a letter from the font's own bits, with the
//! colour applied as it goes, took the item screen nine frames to change a
//! description; with the tables, a letter costs less than half.

use crate::cells::{rgb15, Color, BLACK};
use crate::fail::{Bad, Result};
use crate::game::Skin;
use crate::layout::*;
use crate::message_window;
use rm2k_snes_text::font::{self, Font};
use rm2k_snes_text::line::Ink;

/// The palette index of the glyph's row k: 1 + k. And the shadow's.
pub const INK_ROW_FIRST: u8 = 1;
pub const INK_SHADOW: u8 = INK_ROW_FIRST + font::HEIGHT as u8;

/// The screens' colours: a palette per colour —`ITEM_WHITE` and the
/// others, which are also the tilemap's palette number—, and the font
/// precomposed for their layout, one table per phase.
///
/// The font is the console's 96 glyphs, then a blank where the text
/// layer's `TL_FIGURE` goes —a letter it draws as a digit's blank, and not
/// from these tables—, then the two halves of each icon in `icons`, in that
/// order: glyph 97 + 2k and 98 + 2k are icon `icons[k]`'s. `advances` and
/// `reach` say how far each of those moves the line and paints.
#[derive(Debug, Clone)]
pub struct Inks {
    pub palettes: Vec<Vec<Color>>,
    pub prerender: Vec<Vec<u8>>,
    pub advances: Vec<u8>,
    pub reach: Vec<u8>,
    pub icons: Vec<usize>,
}

/// The glyph the text layer draws the first half of the first icon with:
/// past the console's 96 and `TL_FIGURE`'s place. See [`Inks`].
pub const ICON_GLYPH_FIRST: usize = font::CONSOLE_GLYPHS + 1;

/// The colour of each of the glyph's rows in System colour `color`, and the
/// shadow's. Each row is a single colour —the gradient is vertical—, which
/// is what lets the cartridge paint a row with one index.
pub fn ink_colors(skin: &Skin, color: i32) -> Result<(Vec<Color>, Color)> {
    let ink = Ink::new(&skin.picture, color);
    let mut rows = Vec::new();
    for y in 0..font::HEIGHT {
        let row: std::collections::BTreeSet<Color> = (0..font::INK_MAX)
            .map(|x| rgb15(ink.text_at(x, y)))
            .collect();
        if row.len() != 1 {
            return Err(Bad::answer(format!(
                "row {y} of System colour {color} has {} distinct colours; the cartridge paints a \
                 row with a single one",
                row.len()
            )));
        }
        rows.push(*row.iter().next().expect("one colour"));
    }
    Ok((rows, rgb15(ink.shadow_at(0, 0))))
}

/// The icons the text layer's tables carry, of `icons` —see
/// `texts::screen_icons`—, and the glyphs they carry after the console's
/// 96: `TL_FIGURE`'s place, a blank, and each icon's two halves. A font
/// without the game's ExFont carries no icon. The screens' tables and the
/// menu's bank's carry the same, so a letter is the same glyph in both: a
/// skill's name is written by reference from one text in the battle's list
/// and on the actor choice.
pub fn glyphs_after(font: &Font, icons: &[usize]) -> Result<(Vec<usize>, Vec<char>)> {
    let icons: Vec<usize> = if font.has_exfont() {
        icons.to_vec()
    } else {
        Vec::new()
    };
    if ICON_GLYPH_FIRST + 2 * icons.len() + font::FIRST as usize > 256 {
        return Err(Bad::answer(format!(
            "the text screens draw {} icons, and a byte names {}",
            icons.len(),
            (256 - font::FIRST as usize - ICON_GLYPH_FIRST) / 2
        )));
    }
    let mut after = vec![' '];
    after.extend(
        icons
            .iter()
            .flat_map(|&i| rm2k_snes_text::exfont::halves(i)),
    );
    Ok((icons, after))
}

pub fn text_inks(skin: &Skin, font: &Font, icons: &[usize]) -> Result<Inks> {
    let mut palettes = Vec::new();
    for variant in [ITEM_WHITE, ITEM_GRAY, ITEM_UP, ITEM_RED] {
        let (rows, shadow) = ink_colors(skin, ITEM_COLORS[variant])?;
        let mut palette = vec![BLACK];
        palette.extend(rows);
        palette.push(shadow);
        palette.resize(16, BLACK);
        palettes.push(palette);
    }
    let (icons, after) = glyphs_after(font, icons)?;
    let mut advances = font.console_advances();
    advances.push(font.advance('0') as u8);
    advances.extend(after[1..].iter().map(|&c| font.advance(c) as u8));
    let bytes = message_window::font_bytes_with(font, &after)?;
    Ok(Inks {
        palettes,
        prerender: ink_prerender(&bytes),
        advances,
        reach: message_window::font_reach_with(font, &after),
        icons,
    })
}

/// Glyphs —`font_bytes`'s rows— precomposed for the inks' shared layout, a
/// table per phase: the text screens' and the debug screen's, which has a
/// font of its own.
pub fn ink_prerender(bytes: &[u8]) -> Vec<Vec<u8>> {
    let rows: Vec<u8> = (0..font::HEIGHT as u8).map(|k| INK_ROW_FIRST + k).collect();
    message_window::font_prerender(bytes, &rows, INK_SHADOW)
}
