//! The System's windows behind the text screens, on BG1 at 8bpp: item and
//! equipment, the shop, and the actor choice. And what the cartridge
//! stores of them, which is much less than a tilemap per cursor position.
//!
//! At 8bpp a pixel is directly its colour-memory entry, so there are no
//! palettes to split: the windows' colours go in a row from where the
//! screen leaves room, and black is 0, the transparent one, which lets the
//! backdrop colour show through, which is black.

use crate::cells::{self, Bank, Color, Counts, BLACK, CELL, COLS, ROWS, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use rm2k_render::picture::Picture;
use std::collections::HashMap;
use voodoo::pack::Indices;

/// A screen's windows: the screen-sized picture without a cursor, and each
/// cursor position's with the first cell row it takes and how many.
pub struct Screen {
    pub background: Picture,
    pub bars: Vec<(Picture, usize, usize)>,
}

fn windows(skin: &Skin, rects: &[Rect]) -> Picture {
    let mut out = cells::layer();
    for &(x, y, width, height) in rects {
        cells::paste(&mut out, &skin.window(width, height), x as i64, y as i64);
    }
    out
}

fn bar(skin: &Skin, out: &mut Picture, x: usize, y: usize, width: usize, height: usize) {
    cells::paste(out, &skin.cursor(width, height), x as i64, y as i64);
}

/// The item screen's windows, with the cursor on row `bar` of the list.
pub fn item_windows(skin: &Skin, cursor: Option<usize>) -> Picture {
    let mut out = windows(skin, &ITEM_WINDOWS);
    if let Some(k) = cursor {
        bar(skin, &mut out, ITEM_BAR_X, ITEM_LIST_Y + 2 * CELL * k, ITEM_BAR_WIDTH, 2 * CELL);
    }
    out
}

pub fn item_layers(skin: &Skin) -> Screen {
    Screen {
        background: item_windows(skin, None),
        bars: (0..ITEM_ROWS)
            .map(|k| (item_windows(skin, Some(k)), ITEM_LIST_Y / CELL + 2 * k, 2))
            .collect(),
    }
}

/// The first cell row of the equipment screen's cursor `bar`: the slot
/// number, or `EQUIPMENT_SLOTS` plus the visible row of the list.
pub fn eq_bar_row(bar: usize) -> usize {
    if bar < EQUIPMENT_SLOTS {
        EQ_SLOT_ROW0 + 2 * bar
    } else {
        EQ_LIST_ROW0 + 2 * (bar - EQUIPMENT_SLOTS)
    }
}

pub fn equipment_windows(skin: &Skin, cursor: Option<usize>) -> Picture {
    let mut out = windows(skin, &EQ_WINDOWS);
    if let Some(k) = cursor {
        let (x, width) = if k < EQUIPMENT_SLOTS { EQ_BAR_SLOT } else { EQ_BAR_LIST };
        bar(skin, &mut out, x, eq_bar_row(k) * CELL, width, 2 * CELL);
    }
    out
}

/// The slots and then the list rows, in the order the cartridge indexes
/// them.
pub fn equipment_layers(skin: &Skin) -> Screen {
    Screen {
        background: equipment_windows(skin, None),
        bars: (0..EQUIPMENT_SLOTS + EQ_LIST_ROWS)
            .map(|k| (equipment_windows(skin, Some(k)), eq_bar_row(k), 2))
            .collect(),
    }
}

/// The shop's windows in layout `layer`, with the cursor on position `bar`
/// of `shop_bars(layer)`.
pub fn shop_windows(skin: &Skin, layer: usize, cursor: Option<usize>) -> Picture {
    let mut rects = vec![(0, 0, WIDTH, TI_MIDDLE_Y)];
    rects.extend(ti_windows(layer));
    let mut out = windows(skin, &rects);
    if let Some(k) = cursor {
        let (x, width, row) = shop_bars(layer)[k];
        bar(skin, &mut out, x, row * CELL, width, 2 * CELL);
    }
    out
}

pub fn shop_layers(skin: &Skin) -> Vec<Screen> {
    [TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_SALE]
        .iter()
        .map(|&layer| Screen {
            background: shop_windows(skin, layer, None),
            bars: shop_bars(layer)
                .iter()
                .enumerate()
                .map(|(k, (_, _, row))| (shop_windows(skin, layer, Some(k)), *row, 2))
                .collect(),
        })
        .collect()
}

/// The actor choice's windows: the two on the left with "Owned Items";
/// with `cursor`, the bar on that party row.
pub fn target_windows(game: &Game, skin: &Skin, cursor: Option<usize>) -> Result<Picture> {
    let mut out = windows(skin, &TARGET_WINDOWS);
    skin.draw_line(
        &mut out,
        (TARGET_NAME_COL * CELL + GLYPH_DX) as i64,
        (TARGET_COUNT_ROW * CELL + GLYPH_DY) as i64,
        &game.term(TI_TERM_OWNED)?,
        1,
        game.font_id(),
    );
    if let Some(k) = cursor {
        let (x, y, width, height) = TARGET_BAR;
        bar(skin, &mut out, x, k * MENU_ACTOR_ROWS * CELL + y, width, height);
    }
    Ok(out)
}

/// The pause menu's bar, over nothing: with `cursor`, on that party row.
/// It shares the actor choice's tiles and colours —see `MENU_BAR`—.
pub fn menu_bar(skin: &Skin, cursor: Option<usize>) -> Picture {
    let mut out = cells::layer();
    if let Some(k) = cursor {
        let (x, y, width, height) = MENU_BAR;
        bar(skin, &mut out, x, k * MENU_ACTOR_ROWS * CELL + y, width, height);
    }
    out
}

/// The pause menu's bar as one more screen for `borders`: the same on
/// every row, so only the first one's.
pub fn menu_bar_layer(skin: &Skin) -> Screen {
    Screen {
        background: menu_bar(skin, None),
        bars: vec![(menu_bar(skin, Some(0)), 0, MENU_ACTOR_ROWS)],
    }
}

/// The actor choice, with the bar on each party row, from the first cell
/// row of the actor's row.
pub fn target_layer(game: &Game, skin: &Skin) -> Result<Screen> {
    Ok(Screen {
        background: target_windows(game, skin, None)?,
        bars: (0..MENU_PARTY_ROWS)
            .map(|k| Ok((target_windows(game, skin, Some(k))?, k * MENU_ACTOR_ROWS, MENU_ACTOR_ROWS)))
            .collect::<Result<_>>()?,
    })
}

/// The windows of several screens as the cartridge uploads them.
#[derive(Debug, Clone)]
pub struct Borders {
    /// 8bpp tiles: each pixel is its colour-memory entry.
    pub tiles: Vec<Indices>,
    /// The colours, from the first entry given.
    pub colors: Vec<Color>,
    /// Per screen, its tilemap row by row, and per cursor position the
    /// cell rows it takes with the cursor on top, which is what the
    /// cartridge copies over the tilemap to paint it.
    pub maps: Vec<(Vec<u16>, Vec<Vec<u16>>)>,
}

/// The windows of `screens`, with **a single set of tiles and colours for
/// all**: the screens are never open at the same time and upload their
/// tiles to the same place, so each one uploads the whole set and each
/// one's tilemap indexes it the same way.
///
/// `first_tile` is the number of the first tile, counted from BG1's base;
/// the colours go from entry `cgram`, and cannot go past `cap`. The tiles
/// are also deduplicated mirrored, with the tilemap's flip bits: the frame
/// is symmetric, and without that the windows and the cursor did not fit.
pub fn borders(screens: &[Screen], first_tile: usize, cgram: usize, cap: usize) -> Result<Borders> {
    let mut counts = Counts::default();
    for screen in screens {
        for image in std::iter::once(&screen.background).chain(screen.bars.iter().map(|b| &b.0)) {
            for p in image.rgba.chunks_exact(4) {
                if p[3] != 0 {
                    let color = cells::rgb15([p[0], p[1], p[2], p[3]]);
                    if color != BLACK {
                        counts.add(color, 1);
                    }
                }
            }
        }
    }
    let colors = counts.by_use();
    if cgram + colors.len() > cap {
        return Err(Bad::answer(format!(
            "the windows use {} colours and from {cgram} there is room for {}",
            colors.len(),
            cap - cgram
        )));
    }
    let mut index: HashMap<Color, u8> =
        colors.iter().enumerate().map(|(i, c)| (*c, (cgram + i) as u8)).collect();
    index.insert(BLACK, 0);
    let mut bank = Bank::default();
    let mut words = |image: &Picture, rows: std::ops::Range<usize>| -> Result<Vec<u16>> {
        let mut out = Vec::new();
        for row in rows {
            for col in 0..COLS {
                let cell = cells::cut(image, col, row, &index)?;
                let (at, flip) = bank.add_mirrored(cell);
                out.push((first_tile + at) as u16 | flip);
            }
        }
        Ok(out)
    };
    let mut maps = Vec::new();
    for screen in screens {
        let background = words(&screen.background, 0..ROWS)?;
        let bars = screen
            .bars
            .iter()
            .map(|(image, row, rows)| words(image, *row..*row + *rows))
            .collect::<Result<_>>()?;
        maps.push((background, bars));
    }
    Ok(Borders {
        tiles: bank.tiles,
        colors,
        maps,
    })
}

/// What the cartridge stores of the actor choice's windows.
#[derive(Debug, Clone)]
pub struct CompactTarget {
    /// The tilemap, without the bar.
    pub map: Vec<u16>,
    /// **The bar, only where it changes**: the rectangle covering what
    /// differs between each party row with the bar and without it, the same
    /// for the four rows.
    pub bars: Vec<Vec<u16>>,
    pub row0: usize,
    pub rows: usize,
    pub col0: usize,
    pub cols: usize,
    /// The pause menu's bar: its rectangle on the first party row, as
    /// `(row0, rows, col0, cols)`, and its words row by row. Outside it
    /// BG1 is empty, so erasing it is writing zeros.
    pub menu_bar: Vec<u16>,
    pub menu_bar_at: (usize, usize, usize, usize),
}

/// The actor choice's windows as the cartridge stores them, with the pause
/// menu's bar third. If what it assumes does not hold, it is an error and
/// not a different tilemap.
pub fn compact_target(maps: &[(Vec<u16>, Vec<Vec<u16>>)]) -> Result<CompactTarget> {
    let (with_map, bars_with) = &maps[0];
    let (menu_map, menu_bars) = &maps[1];
    let mut distinct = std::collections::BTreeSet::new();
    for (k, bar) in bars_with.iter().enumerate() {
        let base = &with_map[k * MENU_ACTOR_ROWS * COLS..(k + 1) * MENU_ACTOR_ROWS * COLS];
        for (i, (a, b)) in base.iter().zip(bar).enumerate() {
            if a != b {
                distinct.insert((i / COLS, i % COLS));
            }
        }
    }
    let row0 = distinct.iter().map(|d| d.0).min().unwrap_or(0);
    let rows = distinct.iter().map(|d| d.0).max().unwrap_or(0) + 1 - row0;
    let col0 = distinct.iter().map(|d| d.1).min().unwrap_or(0);
    let cols = distinct.iter().map(|d| d.1).max().unwrap_or(0) + 1 - col0;
    let clip = |bar: &Vec<u16>| -> Vec<u16> {
        (0..rows)
            .flat_map(|f| (0..cols).map(move |c| (f, c)))
            .map(|(f, c)| bar[(row0 + f) * COLS + col0 + c])
            .collect()
    };
    let bars: Vec<Vec<u16>> = bars_with.iter().map(clip).collect();
    if menu_map.iter().any(|&w| w != 0) {
        return Err(Bad::answer("the pause menu's BG1 is not empty without the bar"));
    }
    let menu_bar = &menu_bars[0];
    let used: Vec<(usize, usize)> =
        (0..menu_bar.len()).filter(|&i| menu_bar[i] != 0).map(|i| (i / COLS, i % COLS)).collect();
    let m_row0 = used.iter().map(|d| d.0).min().unwrap_or(0);
    let m_rows = used.iter().map(|d| d.0).max().unwrap_or(0) + 1 - m_row0;
    let m_col0 = used.iter().map(|d| d.1).min().unwrap_or(0);
    let m_cols = used.iter().map(|d| d.1).max().unwrap_or(0) + 1 - m_col0;
    let menu_bar_words = (0..m_rows)
        .flat_map(|f| (0..m_cols).map(move |c| (f, c)))
        .map(|(f, c)| menu_bar[(m_row0 + f) * COLS + m_col0 + c])
        .collect();
    Ok(CompactTarget {
        map: with_map.clone(),
        bars,
        row0,
        rows,
        col0,
        cols,
        menu_bar: menu_bar_words,
        menu_bar_at: (m_row0, m_rows, m_col0, m_cols),
    })
}

/// A bar's rectangle: `(row, col, rows, cols, source)`.
pub type BarPatch = (usize, usize, usize, usize, usize);

/// What the cartridge stores of the shop's windows.
#[derive(Debug, Clone)]
pub struct CompactShop {
    /// The stored tilemap rows, 32 words each, with the help's `top` ones
    /// first.
    pub rows: Vec<Vec<u16>>,
    pub top: usize,
    /// Per layout, its runs from row `top` on, as `(row, source, how
    /// many)` with `source` the index in `rows`.
    pub layers: Vec<Vec<(usize, usize, usize)>>,
    /// The bars' words, one after another.
    pub patches: Vec<u16>,
    /// Per layout, the rectangle of each bar as `(row, col, rows, cols,
    /// source)`, with `source` the index of its first word in `patches`.
    pub bars: Vec<Vec<BarPatch>>,
}

/// The shop's windows as the cartridge stores them:
///
/// * **the three layouts share the help rows**, which are uploaded once on
///   opening: it is checked that they are equal;
/// * **the rest of each layout, as runs of rows**, and a run already
///   stored —from another layout, or earlier in the same one— is not
///   stored again;
/// * **each bar, only where it changes**: the rectangle of cells that
///   differs from its cursorless layout, and a rectangle equal to another
///   is not repeated.
pub fn compact_shop(maps: &[(Vec<u16>, Vec<Vec<u16>>)]) -> Result<CompactShop> {
    let top = TI_MIDDLE_Y / CELL;
    let row = |map: &[u16], n: usize| map[n * COLS..(n + 1) * COLS].to_vec();
    let backdrops: Vec<&Vec<u16>> = maps.iter().map(|m| &m.0).collect();
    if backdrops
        .iter()
        .any(|f| (0..top).any(|n| row(f, n) != row(backdrops[0], n)))
    {
        return Err(Bad::answer("the shop's layers do not share the help"));
    }
    let mut rows: Vec<Vec<u16>> = (0..top).map(|n| row(backdrops[0], n)).collect();
    let mut layers = Vec::new();
    for map in &backdrops {
        let mut stretches: Vec<(usize, usize, usize)> = Vec::new();
        let mut n = top;
        while n < ROWS {
            let (mut length, mut source) = (0, 0);
            for o in 0..rows.len() {
                let mut k = 0;
                while n + k < ROWS && o + k < rows.len() && rows[o + k] == row(map, n + k) {
                    k += 1;
                }
                if k > length {
                    length = k;
                    source = o;
                }
            }
            if length == 0 {
                rows.push(row(map, n));
                length = 1;
                source = rows.len() - 1;
            }
            match stretches.last_mut() {
                Some(last) if last.0 + last.2 == n && last.1 + last.2 == source => last.2 += length,
                _ => stretches.push((n, source, length)),
            }
            n += length;
        }
        layers.push(stretches);
    }
    let mut patches: Vec<u16> = Vec::new();
    let mut seen: HashMap<Vec<u16>, usize> = HashMap::new();
    let mut bars = Vec::new();
    for (layer, (map, cursors)) in maps.iter().enumerate() {
        let mut pieces = Vec::new();
        for ((_, _, row0), cursor) in shop_bars(layer).iter().zip(cursors) {
            let distinct: Vec<(usize, usize)> = (0..2)
                .flat_map(|f| (0..COLS).map(move |c| (f, c)))
                .filter(|&(f, c)| cursor[f * COLS + c] != map[(row0 + f) * COLS + c])
                .collect();
            let f0 = distinct.iter().map(|d| d.0).min().unwrap_or(0);
            let nf = distinct.iter().map(|d| d.0).max().unwrap_or(0) + 1 - f0;
            let c0 = distinct.iter().map(|d| d.1).min().unwrap_or(0);
            let nc = distinct.iter().map(|d| d.1).max().unwrap_or(0) + 1 - c0;
            let piece: Vec<u16> = (0..nf)
                .flat_map(|f| (0..nc).map(move |c| (f, c)))
                .map(|(f, c)| cursor[(f0 + f) * COLS + c0 + c])
                .collect();
            let at = match seen.get(&piece) {
                Some(&at) => at,
                None => {
                    let at = patches.len();
                    patches.extend(&piece);
                    seen.insert(piece, at);
                    at
                }
            };
            pieces.push((row0 + f0, c0, nf, nc, at));
        }
        bars.push(pieces);
    }
    Ok(CompactShop {
        rows,
        top,
        layers,
        patches,
        bars,
    })
}
