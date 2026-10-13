//! The title's menu: RM2k's `Scene_Title` command window —the game's three
//! options in a window of its System, with the System's bar on the chosen
//! one— over the title picture, on BG2 at four bits per pixel, with one
//! tilemap per option chosen and per whether there is a save.
//!
//! The picture behind is not this crate's: it is a full-screen picture, and
//! the menu only has to leave its index 0 transparent so the picture shows
//! through. The window itself is opaque, as in RPG_RT: its black is a
//! colour of the palette, not index 0.

use crate::cells::{self, Bank, Color, Counts, BLACK, COLS, HEIGHT, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use rm2k_render::picture::Picture;
use std::collections::HashMap;
use voodoo::pack::Indices;

/// The menu's tiles, its palette, and one tilemap of 32x32 per option and
/// per whether there is a save: the `texts.len()` without a save first,
/// then as many with one.
#[derive(Debug, Clone)]
pub struct TitleMenu {
    pub texts: Vec<String>,
    pub tiles: Vec<Indices>,
    pub palette: Vec<Color>,
    pub tilemaps: Vec<Vec<u16>>,
    /// How many colours were merged to fit the palette: 0 if they fitted.
    pub merged: usize,
}

/// The menu's texts, as the game says them and not as we would: the
/// database's `new_game`, `load_game` and `exit_game` terms.
///
/// The third one stays on a console, where nothing closes: choosing it fades
/// the screen and the song out and stops, which is what the player sees of
/// RPG_RT closing. See `title_loop` in the runtime.
pub fn options(game: &Game) -> Result<Vec<String>> {
    Ok(vec![game.term("new_game")?, game.term("load_game")?, game.term("exit_game")?])
}

/// The option that cannot be chosen without a save.
pub const LOAD: usize = 1;

/// The window on a transparent `width` x `height` layer, with the bar on
/// `chosen` and `load_game` greyed if there is no save. At 320x240 it is
/// RM2k's.
pub fn draw(game: &Game, skin: &Skin, chosen: usize, saved: bool, width: usize, height: usize) -> Result<Picture> {
    let texts = options(game)?;
    let font = &game.font;
    // `Window_Command`: as wide as the longest command plus the borders,
    // sixteen per command plus the borders tall.
    let w = texts.iter().map(|t| font.width(t)).max().unwrap_or(0) + 2 * BORDER;
    let h = texts.len() * LINE + 2 * BORDER;
    if w > width {
        return Err(Bad::answer(format!(
            "the title's menu is {w} pixels wide and the screen {width}: {texts:?}"
        )));
    }
    let (x, y) = (
        (width / 2 - w / 2) as i64,
        (height * TITLE_BOTTOM.0 / TITLE_BOTTOM.1) as i64 - h as i64,
    );
    let mut out = Picture::transparent(width, height);
    cells::paste(&mut out, &skin.window(w, h), x, y);
    // The bar is `UpdateCursorRect`'s: four more on each side of the
    // contents, as in End Game.
    cells::paste(
        &mut out,
        &skin.cursor(w - 2 * BORDER + 8, LINE),
        x + BORDER as i64 - 4,
        y + (BORDER + chosen * LINE) as i64,
    );
    for (n, text) in texts.iter().enumerate() {
        let ink = if n == LOAD && !saved { INK_DISABLED } else { 0 };
        skin.draw_line(&mut out, x + BORDER as i64, y + (BORDER + n * LINE + LINE / 8) as i64, text, ink, font);
    }
    Ok(out)
}

/// The menu as the cartridge uploads it. The tiles are gathered from
/// **all** the variants before deduplicating: there is a single bank and
/// the tilemaps index it. Palette index 0 is transparent and goes to the
/// empty cell, which is almost the whole screen.
///
/// A System with more colours than the palette holds —a gradient behind the
/// window, the greyed command's own text gradient— is reduced by Adeleine,
/// as End Game is: the least visible colour into its nearest, until they
/// fit.
pub fn menu(game: &Game, skin: &Skin) -> Result<TitleMenu> {
    let texts = options(game)?;
    let mut layers = Vec::new();
    for saved in [false, true] {
        for chosen in 0..texts.len() {
            layers.push(draw(game, skin, chosen, saved, WIDTH, HEIGHT)?);
        }
    }

    let mut seen = Counts::default();
    for layer in &layers {
        seen.add_picture(layer);
    }
    let used = seen.in_order();
    let mut merged = 0;
    let mut to: HashMap<Color, Color> = used.iter().map(|(c, _)| (*c, *c)).collect();
    if used.len() > TITLE_COLORS {
        let reduced = adeleine::merge_least_visible(&used, TITLE_COLORS)?;
        to = used.iter().map(|(c, _)| *c).zip(reduced.mapping.iter().copied()).collect();
        merged = reduced.merges.len();
    }
    let mut kept = Counts::default();
    for (c, n) in &used {
        kept.add(to[c], *n);
    }
    // Black goes in too if the window has it: index 0 is the picture behind,
    // and `index_of` keeps the last entry of a repeated colour.
    let mut palette = vec![BLACK];
    palette.extend(kept.by_use());
    let reduced = cells::index_of(&palette);
    let index: HashMap<Color, u8> = to.iter().map(|(from, into)| (*from, reduced[into])).collect();

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
        merged,
    })
}
