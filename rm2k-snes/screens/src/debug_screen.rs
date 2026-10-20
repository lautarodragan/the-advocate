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
//! come the variables'. The same here, **in the console's 512-wide mode**,
//! mode 5, since 2026-10-20 —taro's: the names did not fit at 256—: the
//! letters are the font's same pixels, each half as wide on screen, so a
//! line holds twice as many. The ranges' window is as wide as its text, and
//! a name is cut only if it does not fit in what is left.
//!
//! What goes to the cartridge: the windows, drawn at 256 wide like every
//! other screen's and **each pixel twice** —BG2 at 2bpp, a 16-pixel cell
//! per tilemap word—, a tilemap and a cursor bar per row of each window;
//! and one block of data with the names, which the runtime writes by
//! reference: see `debug_screen.s` in the runtime.

use crate::borders::Screen;
use crate::cells::{self, Color, Counts, BLACK, CELL, COLS, ROWS, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::{Rect, SCR_TEXT_X};
use crate::texts::item_text;
use rm2k_snes_text::font::Font;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap};
use voodoo::pack::Indices;

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
/// How many of the font's pixels a pixel of the 256-wide screen holds: the
/// 512-wide mode's two.
pub const WIDE: usize = 2;
/// The windows' colours: BG2's eight palettes of four at 2bpp, which in
/// mode 5 are the first 32 entries of the colour memory; the first of each
/// is transparent. The text's go after them —see `debug_screen.s`—.
pub const DBG_PALETTES: usize = 8;
pub const DBG_CGRAM: usize = 0;
/// A tilemap word names 1024 tiles, and a cell takes two.
pub const DBG_TILES_MAX: usize = 1024;
/// The longest range's label and the widest number, to measure with.
const RANGE_TEXT: &str = "S[0000-0000]";
const NUMBER_TEXT: &str = "0000:";
const OFF_TEXT: &str = "[OFF]";
/// A variable's widest value: the runtime's are sixteen bits, signed.
const VALUE_TEXT: &str = "-00000";
/// The gap between a name and what follows it, in the font's pixels.
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
        // The cells a text takes from a cell's start: the font's pixels,
        // two to a pixel of the screen.
        let cells = |px: usize| (SCR_TEXT_X + px.div_ceil(WIDE)).div_ceil(CELL);
        let range_cols = 1 + cells(font.width(RANGE_TEXT)) + 1;
        let number_col = range_cols + 1;
        let name_col = number_col + cells(font.width(NUMBER_TEXT) + font.width(" "));
        // The list's last cell is the one before the frame's.
        let last = COLS - 2;
        let onoff_col = last + 1 - cells(font.width(OFF_TEXT));
        // Where things start, in the font's pixels.
        let at = |col: usize| WIDE * (col * CELL + SCR_TEXT_X);
        let name_x = at(name_col);
        let switch_name_px = at(onoff_col).saturating_sub(name_x + GAP);
        let value_x = WIDE * (last + 1) * CELL - font.width(VALUE_TEXT);
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
    /// The windows' tiles, colours and tilemaps.
    pub borders: Wide,
    pub says: Vec<String>,
}

/// The windows as BG2 draws them in mode 5: 2bpp, and **each tilemap word a
/// cell 16 pixels wide**, tiles N and N + 1 side by side, the drawing's
/// pixels each twice. So the windows look as they do at 256 wide, with
/// their colours in BG2's eight palettes of three: a System with more, or
/// with more than three in a cell, loses some —Adeleine's `reduce_colors`
/// decides which—, which taro accepted for this screen. No flips: a
/// mirrored cell is a cell of its own.
#[derive(Debug, Clone)]
pub struct Wide {
    /// The tiles, two per distinct cell —its left half, then its right—:
    /// indices 0 to 3, 0 transparent. The first two are the empty cell's.
    pub tiles: Vec<Indices>,
    /// The colour memory's first 32 entries: eight palettes of four, the
    /// first of each black, which is transparent.
    pub colors: Vec<Color>,
    /// The tilemap, row by row, and per cursor position the cell rows it
    /// takes with the cursor on top.
    pub maps: (Vec<u16>, Vec<Vec<u16>>),
}

/// A cell of a drawing: each pixel's colour, `None` where it is transparent
/// or black —the backdrop's, as in every other screen's windows—.
type Cell = [[Option<Color>; CELL]; CELL];

fn cell_of(picture: &rm2k_render::picture::Picture, col: usize, row: usize) -> Cell {
    let mut out = [[None; CELL]; CELL];
    for (y, line) in out.iter_mut().enumerate() {
        for (x, pixel) in line.iter_mut().enumerate() {
            let (px, py) = (col * CELL + x, row * CELL + y);
            if px >= picture.width || py >= picture.height {
                continue;
            }
            let at = (py * picture.width + px) * 4;
            let p = &picture.rgba[at..at + 4];
            if p[3] != 0 {
                let color = cells::rgb15([p[0], p[1], p[2], p[3]]);
                if color != BLACK {
                    *pixel = Some(color);
                }
            }
        }
    }
    out
}

/// `screen`'s windows for mode 5's BG2. See [`Wide`].
pub fn wide_borders(screen: &Screen) -> Result<Wide> {
    let rows_of = |image: &rm2k_render::picture::Picture, rows: std::ops::Range<usize>| {
        rows.flat_map(|row| (0..COLS).map(move |col| (col, row)))
            .map(|(col, row)| cell_of(image, col, row))
            .collect::<Vec<Cell>>()
    };
    let mut places: Vec<Vec<Cell>> = vec![rows_of(&screen.background, 0..ROWS)];
    for (image, row, rows) in &screen.bars {
        places.push(rows_of(image, *row..*row + *rows));
    }
    // The distinct cells, and every colour with its pixels.
    let mut distinct: Vec<Cell> = Vec::new();
    let mut seen: HashMap<Cell, usize> = HashMap::new();
    let mut counts = Counts::default();
    for cell in places.iter().flatten() {
        if !seen.contains_key(cell) {
            seen.insert(*cell, distinct.len());
            distinct.push(*cell);
        }
        for color in cell.iter().flatten().flatten() {
            counts.add(*color, 1);
        }
    }
    let sets: Vec<adeleine::Colors> = distinct
        .iter()
        .map(|cell| cell.iter().flatten().flatten().copied().collect())
        .collect();
    let reduced = adeleine::reduce_colors(&counts.in_order(), &sets, DBG_PALETTES, 3)?;
    let palettes: Vec<Vec<Color>> = reduced
        .palettes
        .iter()
        .map(|p| p.iter().copied().collect())
        .collect();
    let mut colors = Vec::with_capacity(4 * DBG_PALETTES);
    for p in 0..DBG_PALETTES {
        colors.push(BLACK);
        for i in 0..3 {
            colors.push(
                palettes
                    .get(p)
                    .and_then(|c| c.get(i))
                    .copied()
                    .unwrap_or(BLACK),
            );
        }
    }
    // Each distinct cell as its two tiles, and its tilemap word.
    const BLANK: Indices = [[0; CELL]; CELL];
    let mut tiles: Vec<Indices> = vec![BLANK, BLANK];
    let mut pairs: HashMap<(Indices, Indices), usize> = HashMap::from([((BLANK, BLANK), 0)]);
    let mut words = Vec::with_capacity(distinct.len());
    for ((cell, set), decided) in distinct.iter().zip(&sets).zip(&reduced.tiles) {
        let Some(p) = decided.palette else {
            words.push(0u16);
            continue;
        };
        let mut into: HashMap<Color, u8> = HashMap::new();
        for (from, to) in set.iter().zip(&decided.mapping) {
            let at = palettes[p].iter().position(|c| c == to).ok_or_else(|| {
                Bad::answer("the debug screen's windows: a colour fell out of its palette")
            })?;
            into.insert(*from, (at + 1) as u8);
        }
        let (mut left, mut right) = (BLANK, BLANK);
        for (y, line) in cell.iter().enumerate() {
            for (x, pixel) in line.iter().enumerate() {
                let index = pixel.map_or(0, |c| into[&c]);
                let half = if x < CELL / 2 { &mut left } else { &mut right };
                let wx = (x % (CELL / 2)) * 2;
                half[y][wx] = index;
                half[y][wx + 1] = index;
            }
        }
        let at = *pairs.entry((left, right)).or_insert_with(|| {
            tiles.push(left);
            tiles.push(right);
            tiles.len() - 2
        });
        words.push(at as u16 | (p as u16) << 10);
    }
    if tiles.len() > DBG_TILES_MAX {
        return Err(Bad::answer(format!(
            "the debug screen's windows take {} tiles and BG2 names {DBG_TILES_MAX}",
            tiles.len()
        )));
    }
    let mut maps = places.iter().map(|cells| {
        cells
            .iter()
            .map(|cell| words[seen[cell]])
            .collect::<Vec<u16>>()
    });
    let background = maps.next().expect("the background is the first");
    Ok(Wide {
        tiles,
        colors,
        maps: (background, maps.collect()),
    })
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
    let borders = wide_borders(&screen)?;
    let blob = blob(
        &game.font,
        &geometry,
        &game.switch_names,
        &game.variable_names,
        slots,
    )?;
    let says = vec![format!(
        "  debug screen: {} switches and {} variables ({} kept), {} B of names, windows in {} tiles \
         and {} palettes",
        game.switch_names.len(),
        game.variable_names.len(),
        slots.keys().filter(|&&v| v >= 1 && v as usize <= game.variable_names.len()).count(),
        blob.len(),
        borders.tiles.len(),
        borders.colors.chunks(4).filter(|p| p[1..].iter().any(|c| *c != BLACK)).count()
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
    let (layout, bars) = &b.borders.maps;
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

    /// A cell is two tiles, its left half and its right one, each pixel
    /// twice; the empty cell is the first two; and a cell's word names its
    /// left tile and its palette.
    #[test]
    fn a_cell_goes_to_mode_5_as_two_tiles_with_its_pixels_doubled() {
        let mut background = cells::layer();
        // In cell (1, 0): a white column at x = 0 and a grey pixel at x = 5.
        let mut put = |x: usize, y: usize, rgba: [u8; 4]| {
            let at = (y * background.width + x) * 4;
            background.rgba[at..at + 4].copy_from_slice(&rgba);
        };
        for y in 0..CELL {
            put(CELL, y, [255, 255, 255, 255]);
        }
        put(CELL + 5, 3, [128, 128, 128, 255]);
        let wide = wide_borders(&Screen {
            background,
            bars: Vec::new(),
        })
        .unwrap();
        assert_eq!(wide.tiles.len(), 4);
        assert_eq!(wide.colors.len(), 4 * DBG_PALETTES);
        let (map, bars) = &wide.maps;
        assert!(bars.is_empty());
        assert_eq!(map.len(), COLS * ROWS);
        assert_eq!(map[0], 0, "an empty cell is the empty pair");
        assert_eq!(map[1], 2, "the cell's left tile, palette 0");
        let white = 1 + wide.colors[1..4]
            .iter()
            .position(|c| *c == [31, 31, 31])
            .unwrap() as u8;
        let grey = 1 + wide.colors[1..4]
            .iter()
            .position(|c| *c == [16, 16, 16])
            .unwrap() as u8;
        let (left, right) = (wide.tiles[2], wide.tiles[3]);
        for y in 0..CELL {
            assert_eq!(&left[y][..2], &[white, white]);
            assert!(left[y][2..].iter().all(|&i| i == 0));
        }
        assert_eq!(
            &right[3][2..4],
            &[grey, grey],
            "x = 5 is the right half's third and fourth"
        );
        assert_eq!(right.iter().flatten().filter(|&&i| i != 0).count(), 2);
    }
}
