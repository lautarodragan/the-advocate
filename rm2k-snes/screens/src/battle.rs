//! The battle's windows: RM2k's, with the System's frame and its bar, in
//! the band below the scene and in the description's band on top. Where
//! each window and each bar goes is `rm2k-snes-battle`'s —`screen.rs`—, and
//! this draws them and turns them into what the cartridge stores.
//!
//! They go on BG1 at 8bpp, the scene's layer: the cells the scene does not
//! take, in its own tilemap. So, like the item screens' windows —see
//! `borders`—, a pixel is its colour-memory entry and there are no
//! palettes to split; the colours go from [`BATTLE_WINDOW_CGRAM`], which is
//! the scene's last battler palette —the converter keeps a troop's battlers
//! to the seven before it—, and black is 0. The tiles go where the text
//! layer's pool ended until then, numbered from the scene's base: see
//! [`BATTLE_WINDOW_FIRST`].

use crate::borders::{self, Screen};
use crate::cells::{self, COLS};
use crate::fail::{Bad, Result};
use crate::game::Skin;
use rm2k_render::picture::Picture;
use rm2k_snes_battle::screen::{self as bs, Rect};
use serde_json::{json, Value};
use std::collections::HashMap;

/// The windows' first colour-memory entry, and how many they may take.
pub const BATTLE_WINDOW_CGRAM: usize = 240;
pub const BATTLE_WINDOW_COLORS: usize = 16;
/// Their tiles' first number, counted from BG1's base —the scene's, at word
/// $4000—: 768 is word $2000, past the 255 pairs of the battle's text.
pub const BATTLE_WINDOW_FIRST: usize = 768;
/// And how many fit before the scene's tilemap, at word $3800.
pub const BATTLE_WINDOW_TILES_MAX: usize = (0x3800 - 0x2000) / 32;

fn picture(skin: &Skin, windows: &[Rect], bar: Option<Rect>) -> Picture {
    let mut out = cells::layer();
    for &(x, y, w, h) in windows {
        cells::paste(&mut out, &skin.window(w, h), x as i64, y as i64);
    }
    if let Some((x, y, w, h)) = bar {
        cells::paste(&mut out, &skin.cursor(w, h), x as i64, y as i64);
    }
    out
}

/// A layout's screen, with its bars of set A and then of set B.
fn layout_screen(skin: &Skin, layout: i64) -> Screen {
    let windows = bs::layout_windows(layout);
    let [a, b] = bs::layout_bars(layout);
    Screen {
        background: picture(skin, &windows, None),
        bars: a
            .iter()
            .chain(b.iter())
            .map(|&r| (picture(skin, &windows, Some(r)), r.1 / cells::CELL, r.3.div_ceil(cells::CELL)))
            .collect(),
    }
}

/// What the cartridge stores, as JSON for the emission:
///
/// * `tiles` and `colors`, uploaded when the battle starts;
/// * per layout, `band`: its tilemap rows from the band's first, which the
///   console writes over the scene's when the layout changes;
/// * `help`: the description's window, the tilemap rows it takes on top;
/// * per layout and set, each bar **only where it changes**: `[row, col,
///   rows, cols, source]`, `source` the first of its words in `patches`,
///   and a piece equal to another is not repeated.
pub fn battle_windows(skin: &Skin) -> Result<Value> {
    let layouts = [bs::BA_LAYOUT_COMMAND, bs::BA_LAYOUT_TARGET, bs::BA_LAYOUT_WIDE];
    let mut screens: Vec<Screen> = layouts.iter().map(|&l| layout_screen(skin, l)).collect();
    screens.push(Screen { background: picture(skin, &[bs::BA_HELP_WINDOW], None), bars: vec![] });
    let made = borders::borders(
        &screens,
        BATTLE_WINDOW_FIRST,
        BATTLE_WINDOW_CGRAM,
        BATTLE_WINDOW_CGRAM + BATTLE_WINDOW_COLORS,
    )?;
    if made.tiles.len() > BATTLE_WINDOW_TILES_MAX {
        return Err(Bad::answer(format!(
            "the battle's windows take {} tiles and there is room for {BATTLE_WINDOW_TILES_MAX}",
            made.tiles.len()
        )));
    }
    let band0 = bs::BA_BAND_Y / cells::CELL;
    let band_rows = bs::BA_BAND_HEIGHT / cells::CELL;
    let help_rows = bs::BA_HELP_SCENE_ROWS as usize;
    let rows = |map: &[u16], from: usize, n: usize| map[from * COLS..(from + n) * COLS].to_vec();
    let mut patches: Vec<u16> = Vec::new();
    let mut seen: HashMap<Vec<u16>, usize> = HashMap::new();
    let mut bands = Vec::new();
    let mut bars = Vec::new();
    for (k, &layout) in layouts.iter().enumerate() {
        let (map, with_bar) = &made.maps[k];
        bands.push(rows(map, band0, band_rows));
        let [a, b] = bs::layout_bars(layout);
        let mut sets = vec![Vec::new(), Vec::new()];
        for (i, cursor) in with_bar.iter().enumerate() {
            let (set, rect) = if i < a.len() { (0, a[i]) } else { (1, b[i - a.len()]) };
            let row0 = rect.1 / cells::CELL;
            let n = rect.3.div_ceil(cells::CELL);
            let differs: Vec<(usize, usize)> = (0..n)
                .flat_map(|f| (0..COLS).map(move |c| (f, c)))
                .filter(|&(f, c)| cursor[f * COLS + c] != map[(row0 + f) * COLS + c])
                .collect();
            if differs.is_empty() {
                return Err(Bad::answer(format!("a bar of battle layout {layout} draws nothing")));
            }
            let f0 = differs.iter().map(|d| d.0).min().unwrap();
            let nf = differs.iter().map(|d| d.0).max().unwrap() + 1 - f0;
            let c0 = differs.iter().map(|d| d.1).min().unwrap();
            let nc = differs.iter().map(|d| d.1).max().unwrap() + 1 - c0;
            let piece: Vec<u16> = (0..nf)
                .flat_map(|f| (0..nc).map(move |c| (f, c)))
                .map(|(f, c)| cursor[(f0 + f) * COLS + c0 + c])
                .collect();
            let at = *seen.entry(piece.clone()).or_insert_with(|| {
                patches.extend(&piece);
                patches.len() - piece.len()
            });
            sets[set].push(json!([row0 + f0, c0, nf, nc, at]));
        }
        bars.push(sets);
    }
    let help = rows(&made.maps[layouts.len()].0, 0, help_rows);
    Ok(json!({
        "tiles": made.tiles,
        "colors": made.colors,
        "first": BATTLE_WINDOW_FIRST,
        "cgram": BATTLE_WINDOW_CGRAM,
        "band_row": band0,
        "band": bands,
        "help": help,
        "patches": patches,
        "bars": bars,
    }))
}
