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
        bar(
            skin,
            &mut out,
            ITEM_BAR_X,
            ITEM_LIST_Y + 2 * CELL * k,
            ITEM_BAR_WIDTH,
            2 * CELL,
        );
    }
    skin.redraw(&mut out);
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
        let (x, width) = if k < EQUIPMENT_SLOTS {
            EQ_BAR_SLOT
        } else {
            EQ_BAR_LIST
        };
        bar(skin, &mut out, x, eq_bar_row(k) * CELL, width, 2 * CELL);
    }
    skin.redraw(&mut out);
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
    skin.redraw(&mut out);
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

/// Where the actor choice's bar goes: on one party row, or over the first
/// `n` rows at once, which is `Window_ActorTarget`'s cursor for a skill on
/// the whole party —`SetIndex(-100)`, one rectangle from the first row's
/// top to the last one's bottom—.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TargetCursor {
    Row(usize),
    All(usize),
}

/// The actor choice's windows: the two on the left with "Owned Items";
/// with `cursor`, the bar on that party row.
pub fn target_windows(game: &Game, skin: &Skin, cursor: Option<usize>) -> Result<Picture> {
    target_windows_for(game, skin, TI_TERM_OWNED, cursor.map(TargetCursor::Row))
}

/// The actor choice's windows with the term `term` in the lower left one
/// —"Owned Items" for a medicine, the cost's for a skill
/// (`Window_TargetStatus`)— and the bar where `cursor` says.
pub fn target_windows_for(
    game: &Game,
    skin: &Skin,
    term: &str,
    cursor: Option<TargetCursor>,
) -> Result<Picture> {
    let mut out = windows(skin, &TARGET_WINDOWS);
    skin.draw_line(
        &mut out,
        (TARGET_NAME_COL * CELL + GLYPH_DX) as i64,
        (TARGET_COUNT_ROW * CELL + GLYPH_DY) as i64,
        &game.term(term)?,
        1,
        &game.font,
    );
    let (x, y, width, height) = TARGET_BAR;
    let row = MENU_ACTOR_ROWS * CELL;
    match cursor {
        Some(TargetCursor::Row(k)) => bar(skin, &mut out, x, k * row + y, width, height),
        Some(TargetCursor::All(n)) if n > 0 => {
            bar(skin, &mut out, x, y, width, (n - 1) * row + height)
        }
        _ => {}
    }
    skin.redraw(&mut out);
    Ok(out)
}

/// The pause menu's bar, over nothing: with `cursor`, on that party row.
/// It shares the actor choice's tiles and colours —see `MENU_BAR`—.
pub fn menu_bar(skin: &Skin, cursor: Option<usize>) -> Picture {
    let mut out = cells::layer();
    if let Some(k) = cursor {
        let (x, y, width, height) = MENU_BAR;
        bar(
            skin,
            &mut out,
            x,
            k * MENU_ACTOR_ROWS * CELL + y,
            width,
            height,
        );
    }
    skin.redraw(&mut out);
    out
}

/// The pause menu's bar as one more screen for `borders`: the same on
/// every row, so only the first one's, with every cell row it reaches
/// —one more than the party row's, see `MENU_BAR`—.
pub fn menu_bar_layer(skin: &Skin) -> Screen {
    let (_, y, _, height) = MENU_BAR;
    Screen {
        background: menu_bar(skin, None),
        bars: vec![(menu_bar(skin, Some(0)), 0, (y + height).div_ceil(CELL))],
    }
}

/// The pause menu's command cursor, over nothing: with `cursor`, on that
/// command. It shares the actor choice's tiles and colours —see
/// `MENU_CMD_BAR`—.
pub fn menu_cmd_bar(skin: &Skin, cursor: Option<usize>) -> Picture {
    let mut out = cells::layer();
    if let Some(k) = cursor {
        let (x, y, width, height) = MENU_CMD_BAR;
        bar(skin, &mut out, x, k * MENU_OPT_STEP + y, width, height);
    }
    skin.redraw(&mut out);
    out
}

/// The command cursor as one more screen for `borders`: the same on every
/// command, whose rows are whole cells, so only the first one's.
pub fn menu_cmd_layer(skin: &Skin) -> Screen {
    let (_, y, _, height) = MENU_CMD_BAR;
    Screen {
        background: menu_cmd_bar(skin, None),
        bars: vec![(
            menu_cmd_bar(skin, Some(0)),
            y / CELL,
            (y % CELL + height).div_ceil(CELL),
        )],
    }
}

/// The slot cursor's rectangle on the first slot: `Window_SaveFile`'s,
/// `width("File") + width(" ") * 5 / 2 + 8` wide —the number goes half a
/// space after the term, in two places—. See `SLOT_BAR_X`.
pub fn slot_bar_rect(game: &Game) -> Result<Rect> {
    let file = game.term("file")?;
    let width = game.font.width(&file) + game.font.width(" ") * 5 / 2 + 8;
    Ok((SLOT_BAR_X, SLOT_Y, width, LINE))
}

/// The slot screen's cursor, over nothing: with `cursor`, on that slot.
pub fn slot_bar(game: &Game, skin: &Skin, cursor: Option<usize>) -> Result<Picture> {
    let mut out = cells::layer();
    if let Some(k) = cursor {
        let (x, y, width, height) = slot_bar_rect(game)?;
        bar(skin, &mut out, x, k * SLOT_STEP + y, width, height);
    }
    skin.redraw(&mut out);
    Ok(out)
}

/// The slot cursor as one more screen for `borders`: the same on every
/// slot, whose rows are whole cells, so only the first one's.
pub fn slot_bar_layer(game: &Game, skin: &Skin) -> Result<Screen> {
    let (_, y, _, height) = slot_bar_rect(game)?;
    Ok(Screen {
        background: slot_bar(game, skin, None)?,
        bars: vec![(
            slot_bar(game, skin, Some(0))?,
            y / CELL,
            (y % CELL + height).div_ceil(CELL),
        )],
    })
}

/// The actor choice, with the bar on each party row, from the first cell
/// row of the actor's row.
pub fn target_layer(game: &Game, skin: &Skin) -> Result<Screen> {
    Ok(Screen {
        background: target_windows(game, skin, None)?,
        bars: (0..MENU_PARTY_ROWS)
            .map(|k| {
                Ok((
                    target_windows(game, skin, Some(k))?,
                    k * MENU_ACTOR_ROWS,
                    MENU_ACTOR_ROWS,
                ))
            })
            .collect::<Result<_>>()?,
    })
}

/// The actor choice for a skill: the cost's term where the medicine's
/// count goes, and the bar over the first `n` rows for each party size, all
/// of the party's cell rows. The bar on one row is the medicine's: the term
/// changes nothing on the right.
pub fn target_skill_layer(game: &Game, skin: &Skin) -> Result<Screen> {
    Ok(Screen {
        background: target_windows_for(game, skin, TARGET_TERM_COST, None)?,
        bars: (1..=MENU_PARTY_ROWS)
            .map(|n| {
                let picture =
                    target_windows_for(game, skin, TARGET_TERM_COST, Some(TargetCursor::All(n)))?;
                Ok((picture, 0, MENU_PARTY_ROWS * MENU_ACTOR_ROWS))
            })
            .collect::<Result<_>>()?,
    })
}

/// Every screen that uploads the actor choice's tiles and colours, in the
/// order `compact_target` reads their maps: the actor choice for a
/// medicine, the pause menu's bar, the choice for a skill, the menu's
/// command cursor and the slot cursor. The last three go over nothing.
pub fn target_screens(game: &Game, skin: &Skin) -> Result<Vec<Screen>> {
    Ok(vec![
        target_layer(game, skin)?,
        menu_bar_layer(skin),
        target_skill_layer(game, skin)?,
        menu_cmd_layer(skin),
        slot_bar_layer(game, skin)?,
    ])
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
    let room = cap.saturating_sub(cgram);
    if room == 0 {
        return Err(Bad::answer(format!(
            "the windows' colours start at {cgram} and there is no room"
        )));
    }
    // A System with more colours than there is room for —a gradient
    // background stretched over a whole screen— is reduced by Adeleine's
    // `merge_least_visible`, as the message window is: every colour goes to
    // the entry of the one it became. One that fits never comes here, so its
    // windows are the ones they always were.
    let (colors, to): (Vec<Color>, HashMap<Color, Color>) = if counts.len() > room {
        let used = counts.in_order();
        let merged = adeleine::merge_least_visible(&used, room)?;
        let to: HashMap<Color, Color> = used
            .iter()
            .map(|(c, _)| *c)
            .zip(merged.mapping.iter().copied())
            .collect();
        let mut kept = Counts::default();
        for (c, n) in &used {
            kept.add(to[c], *n);
        }
        (kept.by_use(), to)
    } else {
        (counts.by_use(), HashMap::new())
    };
    let mut index: HashMap<Color, u8> = colors
        .iter()
        .enumerate()
        .map(|(i, c)| (*c, (cgram + i) as u8))
        .collect();
    for (from, into) in &to {
        index.insert(*from, index[into]);
    }
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
    /// The pause menu's command cursor on the first command, the same way:
    /// its row is counted on the screen, and the others go one command
    /// further down each.
    pub menu_cmd: Vec<u16>,
    pub menu_cmd_at: (usize, usize, usize, usize),
    /// The slot cursor on the first slot, the same way.
    pub slot_bar: Vec<u16>,
    pub slot_bar_at: (usize, usize, usize, usize),
}

/// The actor choice's windows as the cartridge stores them: `maps` are
/// those of `target_screens`, in its order. If what it assumes does not
/// hold, it is an error and not a different tilemap.
pub fn compact_target(maps: &[(Vec<u16>, Vec<Vec<u16>>)]) -> Result<CompactTarget> {
    let (with_map, bars_with) = &maps[0];
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
    let (menu_bar, menu_bar_at) = alone(&maps[1], 0, "the pause menu's bar")?;
    let (menu_cmd, menu_cmd_at) = alone(
        &maps[3],
        MENU_CMD_BAR.1 / CELL,
        "the pause menu's command cursor",
    )?;
    let (slot_bar, slot_bar_at) = alone(&maps[4], SLOT_Y / CELL, "the slot cursor")?;
    Ok(CompactTarget {
        map: with_map.clone(),
        bars,
        row0,
        rows,
        col0,
        cols,
        menu_bar,
        menu_bar_at,
        menu_cmd,
        menu_cmd_at,
        slot_bar,
        slot_bar_at,
    })
}

/// A bar drawn over nothing —the pause menu's, its command cursor, the
/// slot cursor—: its words where it is not empty, row by row, and that
/// rectangle as `(row0, rows, col0, cols)`, with `row0` counted on the
/// screen —`first` is the cell row its bar picture starts at—. Outside it
/// BG1 is empty, so erasing it is writing zeros; if the screen without
/// the bar is not empty, that does not hold, and it is an error.
type Alone = (Vec<u16>, (usize, usize, usize, usize));
fn alone(screen: &(Vec<u16>, Vec<Vec<u16>>), first: usize, what: &str) -> Result<Alone> {
    let (map, bars) = screen;
    if map.iter().any(|&w| w != 0) {
        return Err(Bad::answer(format!("{what} is not over an empty BG1")));
    }
    let bar = &bars[0];
    let used: Vec<(usize, usize)> = (0..bar.len())
        .filter(|&i| bar[i] != 0)
        .map(|i| (i / COLS, i % COLS))
        .collect();
    let row0 = used.iter().map(|d| d.0).min().unwrap_or(0);
    let rows = used.iter().map(|d| d.0).max().unwrap_or(0) + 1 - row0;
    let col0 = used.iter().map(|d| d.1).min().unwrap_or(0);
    let cols = used.iter().map(|d| d.1).max().unwrap_or(0) + 1 - col0;
    let words = (0..rows)
        .flat_map(|f| (0..cols).map(move |c| (f, c)))
        .map(|(f, c)| bar[(row0 + f) * COLS + col0 + c])
        .collect();
    Ok((words, (first + row0, rows, col0, cols)))
}

/// What the cartridge stores of the actor choice for a skill, over the
/// medicine's: the cost's term, and the bar over the whole party.
#[derive(Debug, Clone)]
pub struct CompactTargetSkill {
    /// The cells where the term differs from "Owned Items", as `(row0,
    /// rows, col0, cols)`, and their words row by row: copied over the
    /// medicine's tilemap.
    pub term_at: (usize, usize, usize, usize),
    pub term: Vec<u16>,
    /// The bar over the party: its rectangle —the union of the four party
    /// sizes'—, as `(row0, rows, col0, cols)`; its distinct cell rows,
    /// `cols` words each; and per party size, one to four, which of those
    /// goes on each of the rectangle's rows. It never moves, so it is
    /// painted once, row by row, and never erased.
    pub all_at: (usize, usize, usize, usize),
    pub all_rows: Vec<Vec<u16>>,
    pub all: Vec<Vec<u8>>,
}

/// The rectangle of the cells that differ between two tilemaps of whole
/// rows: `(row0, rows, col0, cols)`.
fn differing(a: &[u16], b: &[u16]) -> Option<(usize, usize, usize, usize)> {
    let cells: Vec<(usize, usize)> = a
        .iter()
        .zip(b)
        .enumerate()
        .filter(|(_, (x, y))| x != y)
        .map(|(i, _)| (i / COLS, i % COLS))
        .collect();
    let r0 = cells.iter().map(|c| c.0).min()?;
    let r1 = cells.iter().map(|c| c.0).max()?;
    let c0 = cells.iter().map(|c| c.1).min()?;
    let c1 = cells.iter().map(|c| c.1).max()?;
    Some((r0, r1 + 1 - r0, c0, c1 + 1 - c0))
}

/// The actor choice for a skill as the cartridge stores it: `item` is the
/// medicine's screen in `borders`' maps, `skill` the one of
/// [`target_skill_layer`], whose bars take the whole tilemap. If the term
/// reaches the party's window, it is an error: the bars of one row are
/// copied from the medicine's tilemap.
pub fn compact_target_skill(
    item: &(Vec<u16>, Vec<Vec<u16>>),
    skill: &(Vec<u16>, Vec<Vec<u16>>),
) -> Result<CompactTargetSkill> {
    let (item_map, _) = item;
    let (skill_map, alls) = skill;
    let term_at = differing(item_map, skill_map).unwrap_or((TARGET_COUNT_ROW, 1, 0, 1));
    if term_at.2 + term_at.3 > TARGET_LEFT / CELL {
        return Err(Bad::answer(
            "the actor choice's cost term reaches the party's window",
        ));
    }
    let (r0, rows, c0, cols) = term_at;
    let term = (r0..r0 + rows)
        .flat_map(|r| (c0..c0 + cols).map(move |c| skill_map[r * COLS + c]))
        .collect();
    let mut union: Option<(usize, usize, usize, usize)> = None;
    for bar in alls {
        if let Some((a0, an, b0, bn)) = differing(skill_map, bar) {
            union = Some(match union {
                None => (a0, an, b0, bn),
                Some((u0, un, v0, vn)) => {
                    let (top, bottom) = (u0.min(a0), (u0 + un).max(a0 + an));
                    let (left, right) = (v0.min(b0), (v0 + vn).max(b0 + bn));
                    (top, bottom - top, left, right - left)
                }
            });
        }
    }
    let all_at =
        union.ok_or_else(|| Bad::answer("the actor choice's bar over the party draws nothing"))?;
    let (r0, rows, c0, cols) = all_at;
    let mut all_rows: Vec<Vec<u16>> = Vec::new();
    let mut all = Vec::new();
    for bar in alls {
        let mut which = Vec::new();
        for r in r0..r0 + rows {
            let words: Vec<u16> = bar[r * COLS + c0..r * COLS + c0 + cols].to_vec();
            let k = match all_rows.iter().position(|w| *w == words) {
                Some(k) => k,
                None => {
                    all_rows.push(words);
                    all_rows.len() - 1
                }
            };
            which.push(
                u8::try_from(k)
                    .map_err(|_| Bad::answer("the bar over the party has too many rows"))?,
            );
        }
        all.push(which);
    }
    Ok(CompactTargetSkill {
        term_at,
        term,
        all_at,
        all_rows,
        all,
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
