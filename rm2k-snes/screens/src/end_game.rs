//! The pause menu's End Game screen: RM2k's `Scene_End`.
//!
//! Two windows over black: on top the question —the database's
//! `exit_game_message`— and below "Yes" and "No", with the System's bar
//! over the one being chosen. The rules are easyrpg-player's
//! `Scene_End::CreateCommandWindow` and `CreateHelpWindow`, and at 320x240
//! the windows, the text and the bar land on the same pixels as in a
//! capture of the 2015 RPG_RT.
//!
//! **It is drawn whole, as a picture**, and not with the text screens'
//! one-letter-per-cell font: it is a fixed screen of three words, so the
//! letters can go at the font's 6 pixels, as in RM2k.
//!
//! **The cursor does not move tiles: it changes colours.** The two
//! pictures —the bar on "Yes" and on "No"— share the tiles and the
//! tilemap, and what tells them apart are the pixels of the two bars. Each
//! pair (colour with the cursor on Yes, colour with the cursor on No) that
//! appears is a palette entry of its own; moving the cursor is writing the
//! other picture's palette. That way there is no second tilemap and no
//! extra tiles.

use crate::cells::{self, Bank, Color, BLACK, CELL, COLS, HEIGHT, ROWS, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use rm2k_render::picture::Picture;
use std::collections::{BTreeSet, HashMap};
use voodoo::pack::Indices;

/// The question and the two commands, from the database, with the same
/// fallback texts as easyrpg if a term is empty.
pub fn texts(game: &Game) -> Result<(String, String, String)> {
    let one = |name: &str, fallback: &str| -> Result<String> {
        let value = game.term(name)?;
        Ok(if value.is_empty() { fallback.to_string() } else { value })
    };
    Ok((
        one("exit_game_message", "Do you really want to quit?")?,
        one("yes", "Yes")?,
        one("no", "No")?,
    ))
}

/// How wide RM2k makes a window for `text`: its letters' advances.
fn width_of(game: &Game, text: &str) -> usize {
    game.font.width(text)
}

/// The screen with the cursor on `chosen`, opaque. `width`, `height` and
/// `y_shift` at 320, 240 and 0 give RM2k's.
pub fn draw(game: &Game, skin: &Skin, chosen: usize, width: usize, height: usize, y_shift: usize) -> Result<Picture> {
    let (question, yes, no) = texts(game)?;
    if width_of(game, &question) + 2 * BORDER > width {
        // RM2k would let it run off the screen; here it would be cut
        // without warning.
        return Err(Bad::answer(format!(
            "the End Game question, {question:?}, does not fit in {width} pixels"
        )));
    }
    let font = &game.font;
    let mut out = Picture::filled(width, height, [0, 0, 0, 255]);

    // The question: `Window_Help`, as wide as the text plus the borders,
    // with the text at (0, 2) of its contents.
    let w = width_of(game, &question) + 2 * BORDER;
    let (x, y) = ((width / 2 - w / 2) as i64, END_Y_QUESTION as i64 - y_shift as i64);
    cells::paste(&mut out, &skin.window(w, 2 * LINE), x, y);
    skin.draw_line(&mut out, x + BORDER as i64, y + BORDER as i64 + 2, &question, 0, font);

    // The commands: `Window_Command`, as wide as the longest plus the
    // borders and sixteen per command plus the borders tall. The bar is
    // `UpdateCursorRect`'s: four more on each side of the contents.
    let commands = [yes, no];
    let w = commands.iter().map(|c| width_of(game, c)).max().unwrap_or(0) + 2 * BORDER;
    let (x, y) = ((width / 2 - w / 2) as i64, END_Y_COMMANDS as i64 - y_shift as i64);
    cells::paste(&mut out, &skin.window(w, commands.len() * LINE + 2 * BORDER), x, y);
    cells::paste(
        &mut out,
        &skin.cursor(w - 2 * BORDER + 8, LINE),
        x + BORDER as i64 - 4,
        y + (BORDER + chosen * LINE) as i64,
    );
    for (n, command) in commands.iter().enumerate() {
        skin.draw_line(
            &mut out,
            x + BORDER as i64,
            y + (BORDER + n * LINE + LINE / 8) as i64,
            command,
            0,
            font,
        );
    }
    Ok(out)
}

/// The screen as the cartridge uploads it: BG2 at 4bpp, the tiles —0 the
/// empty one—, the tilemap words of the cell rows that have something from
/// `row0`, and the two palettes: the bar on "Yes" and the bar on "No".
#[derive(Debug, Clone)]
pub struct EndGame {
    pub tiles: Vec<Indices>,
    pub rows: Vec<u16>,
    pub row0: usize,
    pub palettes: [Vec<Color>; 2],
}

pub fn convert(game: &Game, skin: &Skin) -> Result<EndGame> {
    let colors15: Vec<Vec<Color>> = [END_YES, END_NO]
        .iter()
        .map(|&n| {
            Ok(draw(game, skin, n, WIDTH, HEIGHT, END_Y_SHIFT)?
                .rgba
                .chunks_exact(4)
                .map(|p| cells::rgb15([p[0], p[1], p[2], p[3]]))
                .collect())
        })
        .collect::<Result<_>>()?;
    let pairs_seen: BTreeSet<(Color, Color)> =
        colors15[0].iter().copied().zip(colors15[1].iter().copied()).collect();
    let mut pairs: Vec<(Color, Color)> = pairs_seen.into_iter().filter(|p| *p != (BLACK, BLACK)).collect();
    // 0: transparent, the black background.
    pairs.insert(0, (BLACK, BLACK));
    if pairs.len() > END_COLORS_MAX {
        return Err(Bad::answer(format!(
            "the End Game screen uses {} pairs of colours and a 4bpp palette has {END_COLORS_MAX}",
            pairs.len()
        )));
    }
    let index: HashMap<(Color, Color), u8> = pairs.iter().enumerate().map(|(i, p)| (*p, i as u8)).collect();
    let pixels: Vec<u8> = colors15[0]
        .iter()
        .zip(&colors15[1])
        .map(|(a, b)| index[&(*a, *b)])
        .collect();
    let mut bank = Bank::default();
    let mut mapping = Vec::with_capacity(ROWS * COLS);
    for row in 0..ROWS {
        for col in 0..COLS {
            let mut cell = [[0u8; CELL]; CELL];
            for (y, line) in cell.iter_mut().enumerate() {
                let at = (row * CELL + y) * WIDTH + col * CELL;
                line.copy_from_slice(&pixels[at..at + CELL]);
            }
            // Mirrored too, with the tilemap's flip bits: the window frame
            // is symmetric.
            let (at, flip) = bank.add_mirrored(cell);
            mapping.push(at as u16 | flip);
        }
    }
    let used: Vec<usize> = (0..ROWS)
        .filter(|&f| mapping[f * COLS..(f + 1) * COLS].iter().any(|&w| w != 0))
        .collect();
    let (row0, row1) = (used[0], used[used.len() - 1] + 1);
    let palette = |n: usize| -> Vec<Color> {
        let mut out: Vec<Color> = pairs.iter().map(|p| if n == 0 { p.0 } else { p.1 }).collect();
        out.resize(END_COLORS_MAX, BLACK);
        out
    };
    Ok(EndGame {
        tiles: bank.tiles,
        rows: mapping[row0 * COLS..row1 * COLS].to_vec(),
        row0,
        palettes: [palette(0), palette(1)],
    })
}
