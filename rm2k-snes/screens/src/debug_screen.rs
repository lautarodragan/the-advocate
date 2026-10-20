//! The debug screen: RPG_RT's F9 —`Scene_Debug` in a test play— as one
//! more option of the pause menu, since the console has no F9. A project
//! asks for it with `[debug] debug_screen`; without it the cartridge
//! carries nothing of this.
//!
//! **What RPG_RT 2000 shows**, measured under Wine: two windows 176 tall,
//! the ranges on the left —ten rows of `S[0001-0010]`— and the list on the
//! right —ten rows of `0001: Name` with `[OFF]` or `[ON]` at its right
//! edge, or a variable's value—. Up and down go round the ten ranges of a
//! page, left and right flip pages of ten, and after the switches' pages
//! come the variables'. The same here, at 256 wide: what is cut is the
//! width, so the ranges' window is as wide as its text and the names are
//! cut to what is left.
//!
//! What goes to the cartridge: the windows, as the custom menus' do —BG1 at
//! 8bpp, a tilemap and a cursor bar per row of each window—, and one block
//! of data with the names, which the runtime writes by reference: see
//! `debug_screen.s` in the runtime.

use crate::borders::{self, Screen};
use crate::cells::{self, CELL, COLS, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::{Rect, SCR_TEXT_X};
use crate::texts::item_text;
use rm2k_snes_text::font::Font;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;

/// The label of its option in the pause menu. RM2k has no term for it: the
/// editor's F9 is not translated.
pub const LABEL: &str = "Debug";

/// The windows' top: centred, as RPG_RT's are at y = 32 of 240.
pub const DBG_WINDOW_Y: usize = 24;
/// Ten rows a window, and two cell rows a row.
pub const DBG_ROWS: usize = 10;
pub const DBG_WINDOW_H: usize = 16 + 16 * DBG_ROWS;
/// The first row's first cell row.
pub const DBG_ROW0: usize = (DBG_WINDOW_Y + 8) / CELL;
/// The windows' colours, at 8bpp, after the text's eight palettes; and the
/// tiles from BG1's base up to the end of the VRAM, which is all the screen
/// has: no objects show.
pub const DBG_CGRAM: usize = 128;
pub const DBG_CGRAM_END: usize = 256;
pub const DBG_TILES_MAX: usize = 512;
/// The longest range's label and the widest number, to measure with.
const RANGE_TEXT: &str = "S[0000-0000]";
const NUMBER_TEXT: &str = "0000:";
const OFF_TEXT: &str = "[OFF]";
/// A variable's widest value: the runtime's are sixteen bits, signed.
const VALUE_TEXT: &str = "-00000";
/// The gap between a name and what follows it, in pixels.
const GAP: usize = 4;

/// Where each thing goes, measured with the game's font: the ranges'
/// window is as wide as its widest label, and the list takes the rest.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Geometry {
    /// The ranges' window, in cells: its text goes at cell 1.
    pub range_cols: usize,
    /// The list's number, its name and the switch's `[OFF]`, by cell.
    pub number_col: usize,
    pub name_col: usize,
    pub onoff_col: usize,
    /// How many pixels a switch's name and a variable's take at most.
    pub switch_name_px: usize,
    pub variable_name_px: usize,
}

impl Geometry {
    pub fn of(font: &Font) -> Geometry {
        let cells = |px: usize| (SCR_TEXT_X + px).div_ceil(CELL);
        let range_cols = 1 + cells(font.width(RANGE_TEXT)) + 1;
        let number_col = range_cols + 1;
        let name_col = number_col + cells(font.width(NUMBER_TEXT) + font.width(" "));
        // The list's last cell is the one before the frame's.
        let last = COLS - 2;
        let onoff_col = last + 1 - cells(font.width(OFF_TEXT));
        let name_x = name_col * CELL + SCR_TEXT_X;
        let switch_name_px = (onoff_col * CELL + SCR_TEXT_X).saturating_sub(name_x + GAP);
        let value_x = (last + 1) * CELL - font.width(VALUE_TEXT);
        let variable_name_px = value_x.saturating_sub(name_x + GAP);
        Geometry {
            range_cols,
            number_col,
            name_col,
            onoff_col,
            switch_name_px,
            variable_name_px,
        }
    }

    /// The two windows: the ranges and the list.
    pub fn windows(&self) -> [Rect; 2] {
        let split = self.range_cols * CELL;
        [
            (0, DBG_WINDOW_Y, split, DBG_WINDOW_H),
            (split, DBG_WINDOW_Y, WIDTH - split, DBG_WINDOW_H),
        ]
    }

    /// The cursor of `window` —0 the ranges, 1 the list— on row `row`, as
    /// RPG_RT draws it: four pixels in from each side, a row tall.
    fn bar(&self, window: usize, row: usize) -> Rect {
        let (x, _, w, _) = self.windows()[window];
        (x + 4, (DBG_ROW0 + 2 * row) * CELL, w - 8, 2 * CELL)
    }
}

/// Everything the cartridge carries of the screen.
pub struct Built {
    pub geometry: Geometry,
    /// How many switches and variables the database has: the list shows
    /// them all.
    pub switches: usize,
    pub variables: usize,
    pub blob: Vec<u8>,
    /// The windows' tilemap, and per window and row the two cell rows with
    /// the cursor on top: the ranges' ten, then the list's.
    pub borders: borders::Borders,
    pub says: Vec<String>,
}

/// The windows without a cursor, or with it on `bar`.
fn picture(
    skin: &Skin,
    geometry: &Geometry,
    bar: Option<(usize, usize)>,
) -> rm2k_render::picture::Picture {
    let mut out = cells::layer();
    for (x, y, w, h) in geometry.windows() {
        cells::paste(&mut out, &skin.window(w, h), x as i64, y as i64);
    }
    if let Some((window, row)) = bar {
        let (x, y, w, h) = geometry.bar(window, row);
        cells::paste(&mut out, &skin.cursor(w, h), x as i64, y as i64);
    }
    out
}

/// A name as the screen writes it: in the font's letters and cut to `px`.
fn fitted(font: &Font, name: &str, px: usize) -> String {
    let mut width = 0;
    item_text(name, 255)
        .chars()
        .take_while(|&c| {
            width += font.advance(c);
            width <= px
        })
        .collect::<String>()
        .trim_end()
        .to_string()
}

/// The data block, as `debug_screen.s` reads it with `lda f:dbg_data, x`:
///
///   +0 word  how many switches the database has, n
///   +2 word  how many variables, m
///   +4       n words: switch k's name, by offset, 0 none
///            m pairs of words: variable k's name, and its slot times two,
///            $FFFF if the cartridge does not keep it
///   strings: a length byte and the letters
///
/// The switch's bit needs no table: it is its number. A variable is kept
/// only if a page of the cartridge names it —see `VARIABLES_N` in the
/// runtime—, and one that is not shows no value.
fn blob(
    font: &Font,
    geometry: &Geometry,
    switches: &[String],
    variables: &[String],
    slots: &BTreeMap<i32, usize>,
) -> Result<Vec<u8>> {
    let mut out: Vec<u8> = Vec::new();
    let word = |out: &mut Vec<u8>, w: u16| out.extend(w.to_le_bytes());
    word(&mut out, switches.len() as u16);
    word(&mut out, variables.len() as u16);
    let table = out.len();
    out.resize(table + 2 * switches.len() + 4 * variables.len(), 0);
    let mut strings: BTreeMap<String, u16> = BTreeMap::new();
    let mut string = |out: &mut Vec<u8>, text: String| -> Result<u16> {
        if text.is_empty() {
            return Ok(0);
        }
        if let Some(&at) = strings.get(&text) {
            return Ok(at);
        }
        let at = u16::try_from(out.len())
            .map_err(|_| Bad::answer("the debug screen's names do not fit in a bank"))?;
        out.push(text.len() as u8);
        out.extend(text.bytes());
        strings.insert(text, at);
        Ok(at)
    };
    for (k, name) in switches.iter().enumerate() {
        let at = string(&mut out, fitted(font, name, geometry.switch_name_px))?;
        out[table + 2 * k..table + 2 * k + 2].copy_from_slice(&at.to_le_bytes());
    }
    let vars = table + 2 * switches.len();
    for (k, name) in variables.iter().enumerate() {
        let at = string(&mut out, fitted(font, name, geometry.variable_name_px))?;
        let slot = slots
            .get(&(k as i32 + 1))
            .map_or(0xFFFF, |s| (2 * s) as u16);
        out[vars + 4 * k..vars + 4 * k + 2].copy_from_slice(&at.to_le_bytes());
        out[vars + 4 * k + 2..vars + 4 * k + 4].copy_from_slice(&slot.to_le_bytes());
    }
    if out.len() > 0x10000 {
        return Err(Bad::answer(format!(
            "the debug screen's data takes {} bytes and has to fit in a bank",
            out.len()
        )));
    }
    Ok(out)
}

/// The screen for `game`, whose variables the cartridge keeps in `slots`
/// —number to slot—.
pub fn build(game: &Game, skin: &Skin, slots: &BTreeMap<i32, usize>) -> Result<Built> {
    let geometry = Geometry::of(&game.font);
    let screen = Screen {
        background: picture(skin, &geometry, None),
        bars: (0..2)
            .flat_map(|window| (0..DBG_ROWS).map(move |row| (window, row)))
            .map(|(window, row)| {
                (
                    picture(skin, &geometry, Some((window, row))),
                    DBG_ROW0 + 2 * row,
                    2,
                )
            })
            .collect(),
    };
    let borders = borders::borders(&[screen], 0, DBG_CGRAM, DBG_CGRAM_END)?;
    if borders.tiles.len() > DBG_TILES_MAX {
        return Err(Bad::answer(format!(
            "the debug screen's windows take {} tiles and BG1 has room for {DBG_TILES_MAX}",
            borders.tiles.len()
        )));
    }
    let blob = blob(
        &game.font,
        &geometry,
        &game.switch_names,
        &game.variable_names,
        slots,
    )?;
    let says = vec![format!(
        "  debug screen: {} switches and {} variables ({} kept), {} B of names, windows in {} tiles \
         and {} colours",
        game.switch_names.len(),
        game.variable_names.len(),
        slots.keys().filter(|&&v| v >= 1 && v as usize <= game.variable_names.len()).count(),
        blob.len(),
        borders.tiles.len(),
        borders.colors.len()
    )];
    Ok(Built {
        geometry,
        switches: game.switch_names.len(),
        variables: game.variable_names.len(),
        blob,
        borders,
        says,
    })
}

/// The geometry the runtime writes with, and the counts it walks, by name.
pub fn publish(b: &Built) -> Value {
    let g = &b.geometry;
    // Pages of ten ranges of ten: the switches' first, then the variables'.
    let pages = |n: usize| n.div_ceil(DBG_ROWS * DBG_ROWS);
    let mut m = Map::new();
    for (name, value) in [
        ("DBG_SWITCHES", b.switches),
        ("DBG_VARIABLES", b.variables),
        ("DBG_SWITCH_PAGES", pages(b.switches)),
        ("DBG_PAGES", pages(b.switches) + pages(b.variables)),
        // Where the variables' table starts in the block: see [`blob`].
        ("DBG_VAR_TABLE", 4 + 2 * b.switches),
        ("DBG_ROWS", DBG_ROWS),
        ("DBG_ROW0", DBG_ROW0),
        ("DBG_CGRAM", DBG_CGRAM),
        ("DBG_RANGE_COLS", g.range_cols),
        ("DBG_NUMBER_COL", g.number_col),
        ("DBG_NAME_COL", g.name_col),
        ("DBG_ONOFF_COL", g.onoff_col),
        // The value's last cell: a right-aligned number ends with it.
        ("DBG_VALUE_COL", COLS - 2),
    ] {
        m.insert(name.to_string(), json!(value));
    }
    Value::Object(m)
}

/// The answer's part for the screen.
pub fn to_json(b: &Built) -> Value {
    let (layout, bars) = &b.borders.maps[0];
    json!({
        "label": LABEL,
        "blob": b.blob.iter().map(|x| format!("{x:02x}")).collect::<String>(),
        "layout": layout,
        "bars": bars,
        "tiles": crate::convert::tiles_json(&b.borders.tiles),
        "colors": crate::convert::colors_json(&b.borders.colors),
        "geometry": publish(b),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cells::HEIGHT;

    #[test]
    fn the_windows_fill_the_width_and_fit_the_height() {
        let g = Geometry {
            range_cols: 11,
            number_col: 12,
            name_col: 16,
            onoff_col: 27,
            switch_name_px: 80,
            variable_name_px: 70,
        };
        let [ranges, list] = g.windows();
        assert_eq!(ranges.0 + ranges.2, list.0);
        assert_eq!(list.0 + list.2, WIDTH);
        const { assert!(DBG_WINDOW_Y + DBG_WINDOW_H <= HEIGHT) };
        // The last row's two cell rows end before the frame's.
        const { assert!((DBG_ROW0 + 2 * DBG_ROWS) * CELL <= DBG_WINDOW_Y + DBG_WINDOW_H - 8) };
        assert_eq!(g.bar(1, 0), (92, 32, 160, 16));
    }
}
