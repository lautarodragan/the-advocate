//! The title's menu: the game's two options over the title picture, on
//! BG2 at four bits per pixel, with one tilemap per option chosen.
//!
//! The picture behind is not this crate's: it is a full-screen picture, and
//! the menu only has to leave its index 0 transparent so the picture shows
//! through.

use crate::cells::{self, Bank, Color, Counts, BLACK, COLS};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use voodoo::pack::Indices;

/// The menu's tiles, its palette, and one tilemap of 32x32 per option.
#[derive(Debug, Clone)]
pub struct TitleMenu {
    pub texts: Vec<String>,
    pub tiles: Vec<Indices>,
    pub palette: Vec<Color>,
    pub tilemaps: Vec<Vec<u16>>,
}

/// The menu's texts, as the game says them and not as we would: the
/// database's `new_game` and `load_game` terms.
pub fn options(game: &Game) -> Result<Vec<String>> {
    Ok(vec![game.term("new_game")?, game.term("load_game")?])
}

/// The menu, drawn once per option with the cursor on it, with the same
/// font and ink as the messages: that the title and a message look the same
/// is what means there is no second font to maintain.
///
/// The tiles are gathered from **all** the variants before deduplicating:
/// there is a single bank and the tilemaps index it. Palette index 0 is
/// transparent and goes to the empty cell, which is almost the whole
/// screen.
pub fn menu(game: &Game, skin: &Skin) -> Result<TitleMenu> {
    let texts = options(game)?;
    let font_id = game.font_id();
    let layers: Vec<_> = (0..texts.len())
        .map(|chosen| {
            let mut layer = cells::layer();
            for (n, text) in texts.iter().enumerate() {
                let mark = if n == chosen { TITLE_CURSOR } else { TITLE_NO_CURSOR };
                skin.draw_line(
                    &mut layer,
                    TITLE_MENU_X as i64,
                    (TITLE_MENU_Y + n * TITLE_MENU_STEP) as i64,
                    &format!("{mark}{text}"),
                    0,
                    font_id,
                );
            }
            layer
        })
        .collect();

    let mut seen = Counts::default();
    for layer in &layers {
        seen.add_picture(layer);
    }
    if seen.len() > 15 {
        return Err(Bad::answer(format!(
            "the title menu uses {} colours and 4bpp fits 15. The System's text gradient is the \
             suspect",
            seen.len()
        )));
    }
    let mut palette = vec![BLACK];
    palette.extend(seen.by_use());
    let index = cells::index_of(&palette);

    let mut bank = Bank::default();
    let mut tilemaps = Vec::new();
    for layer in &layers {
        let mut mapping = Vec::with_capacity(32 * COLS);
        for ty in 0..32 {
            for tx in 0..COLS {
                let cell = cells::cut(layer, tx, ty, &index)?;
                mapping.push(bank.add(cell) as u16);
            }
        }
        tilemaps.push(mapping);
    }
    Ok(TitleMenu {
        texts,
        tiles: bank.tiles,
        palette,
        tilemaps,
    })
}
