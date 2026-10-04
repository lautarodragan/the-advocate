//! The message window as a cartridge carries it: its tiles, its palette,
//! its cells, and the font with the tables the cartridge composes the text
//! with.
//!
//! **Why the text is composed on the fly.** A composed page of the window
//! is some 240 4bpp tiles, 7.5 KB, and a game has thousands of lines of
//! text: one window per message does not come close to fitting. The way
//! out is Final Fantasy VI's —the font in the cartridge and the text built
//! by the 65816—, so what goes here is the empty window, the font, and the
//! numbers the cartridge needs to draw a letter the way RM2k's
//! `Font::Render` draws it.

use crate::cells::{self, rgb15, Color, BLACK, CELL};
use crate::fail::{Bad, Result};
use crate::game::Skin;
use crate::layout::*;
use rm2k_render::picture::Picture;
use rm2k_snes_text::font::{self, Font};
use rm2k_snes_text::line;
use std::collections::{BTreeSet, HashMap};
use voodoo::pack::{pack_tile, Indices};

/// How many colours a 4bpp palette has, 0 being transparent.
const COLORS_PER_PALETTE: usize = 16;

/// The message window, cut.
#[derive(Debug, Clone)]
pub struct Window {
    /// The tiles of the empty window, deduplicated, 4bpp.
    pub tiles: Vec<u8>,
    /// The sixteen colour-memory words of its palette.
    pub cgram: Vec<u16>,
    /// The 32x10 tilemap, with the text area's tiles already numbered.
    pub cells: Vec<Vec<usize>>,
    /// The first tile of the text area.
    pub base: usize,
    /// The text area's tiles without text, in order, 4bpp.
    pub background: Vec<u8>,
    /// The palette index of each of the glyph's twelve rows.
    pub color: Vec<u8>,
    /// The shadow's palette index.
    pub shadow: u8,
    /// The tiles of the arrow of a message waiting for a key, from left to
    /// right: [`WINDOW_ARROW_CELLS`] over the frame, and as many over
    /// nothing, for the window without a background. They are among
    /// `tiles`, before `base`; the cartridge puts them on the tilemap and
    /// takes them off, and the window's own cells there are in `cells`.
    pub arrow: Vec<usize>,
    /// The text area's background with the System's cursor on each line, in
    /// the order and the size of `background`: line `k`'s tiles are those
    /// of `background` with the cursor on line `k`. A choice's highlighted
    /// option is composed on these instead.
    pub bar: Vec<u8>,
    /// And one line's, with the cursor over nothing: the window without a
    /// background. It is the same on every line.
    pub bar_bare: Vec<u8>,
}

/// A picture cut to the console's colours, pixel by pixel: over black if
/// `bare` is false —the window's background is opaque—, and with its
/// transparent pixels left as `None` if it is true, which is BG2's
/// transparent index. A half-transparent pixel goes over black either way:
/// the System's are only ever opaque or transparent.
fn cut(picture: &Picture, bare: bool) -> Vec<Option<Color>> {
    over_black(picture)
        .into_iter()
        .zip(picture.rgba.chunks_exact(4))
        .map(|(c, p)| if bare && p[3] == 0 { None } else { Some(c) })
        .collect()
}

/// `picture` over opaque black, at fifteen bits: Pillow's
/// `alpha_composite`, whose rounding this copies.
fn over_black(picture: &Picture) -> Vec<Color> {
    const PRECISION: u32 = 7;
    let div255 = |a: u32| ((a >> 8) + a) >> 8;
    picture
        .rgba
        .chunks_exact(4)
        .map(|p| {
            let a = p[3] as u32;
            if a == 0 {
                return BLACK;
            }
            let blend = 255 * (255 - a);
            let outa255 = a * 255 + blend;
            let coef1 = a * 255 * 255 * (1 << PRECISION) / outa255;
            let channel = |v: u8| (div255(v as u32 * coef1 + (0x80 << PRECISION)) >> PRECISION) as u8;
            rgb15([channel(p[0]), channel(p[1]), channel(p[2]), 255])
        })
        .collect()
}

/// The message window: tiles, palette, cells and what the font needs.
///
/// The picture is the empty window of the System, cut into 8x8 cells, with
/// the fixed part separated from what the cartridge composes. The palette
/// carries the colours of the empty window **plus** those of the text and
/// the shadow, even though the empty window does not use them: they are
/// the ones the cartridge is going to write. Index 0 is left free, which is
/// BG2's transparent and no window tile uses.
///
/// `reserved` is where whatever follows the window in colour memory
/// starts: the window may not reach it.
pub fn convert(skin: &Skin, reserved: usize) -> Result<Window> {
    let empty = skin.window(WINDOW_WIDTH, WINDOW_HEIGHT);
    let (width, height) = (empty.width, empty.height);
    let pixels = cut(&empty, false);

    // What the cartridge puts over the empty window, each drawn whole and
    // cut like it: the arrow on the bottom edge, and the cursor on each
    // line. Over the window, and over nothing for the one without a
    // background.
    let arrow = rm2k_render::system::arrow_down(&skin.picture);
    let (arrow_x, arrow_y) = ((WINDOW_ARROW_COL * CELL) as i64, (WINDOW_ARROW_ROW * CELL) as i64);
    let mut with_arrow = empty.clone();
    cells::paste(&mut with_arrow, &arrow, arrow_x, arrow_y);
    let mut bare_arrow = Picture::transparent(width, height);
    cells::paste(&mut bare_arrow, &arrow, arrow_x, arrow_y);
    let cursor = skin.cursor(MESSAGE_WIDTH - CHOICE_BAR_TRIM, WINDOW_LINE);
    let bar_x = (WINDOW_TEXT_COL * CELL + CHOICE_BAR_X) as i64;
    let bar_y = |line: usize| (WINDOW_TEXT_ROW * CELL + line * WINDOW_LINE) as i64;
    let lines = WINDOW_TEXT_ROWS * CELL / WINDOW_LINE;
    let with_bar: Vec<Vec<Option<Color>>> = (0..lines)
        .map(|line| {
            let mut p = empty.clone();
            cells::paste(&mut p, &cursor, bar_x, bar_y(line));
            cut(&p, false)
        })
        .collect();
    let mut bare_bar = Picture::transparent(width, height);
    cells::paste(&mut bare_bar, &cursor, bar_x, bar_y(0));
    let with_arrow = cut(&with_arrow, false);
    let bare_arrow = cut(&bare_arrow, true);
    let bare_bar = cut(&bare_bar, true);

    // The text colours come from the System's 16x16 block, the ones
    // `Font::Render` uses as a mask. Each row of the glyph takes a single
    // one —the gradient is horizontally uniform—, so they are twelve
    // colours, not a block, and the shadow is a single one.
    let ink = line::Ink::new(&skin.picture, 0);
    let mut color_row = Vec::new();
    for py in 0..font::HEIGHT {
        let row: BTreeSet<Color> = (0..font::INK_MAX).map(|px| rgb15(ink.text_at(px, py))).collect();
        if row.len() != 1 {
            return Err(Bad::answer(format!(
                "row {py} of the text colour has {} distinct colours; the cartridge composes it \
                 with a single one",
                row.len()
            )));
        }
        color_row.push(*row.iter().next().expect("one colour"));
    }
    let shadow = rgb15(ink.shadow_at(0, 0));

    // The arrow and the cursor count even though the empty window does not
    // draw them, as the text does: they are the cartridge's to put.
    let mut colors: BTreeSet<Color> = BTreeSet::new();
    for drawn in [&pixels, &with_arrow, &bare_arrow, &bare_bar].into_iter().chain(&with_bar) {
        colors.extend(drawn.iter().flatten().copied());
    }
    colors.extend(color_row.iter().copied());
    colors.insert(shadow);
    if colors.len() > COLORS_PER_PALETTE - 1 {
        return Err(Bad::answer(format!(
            "the window, its arrow and its cursor use {} colours and {} fit",
            colors.len(),
            COLORS_PER_PALETTE - 1
        )));
    }
    // What follows starts where this ends, so if the window grew it would
    // step on it and the cartridge would draw the text with a colour of the
    // map. The highest entry is the number of colours —0 is transparent and
    // the rest go in order—, and not how many words are nonzero: a black
    // colour has word zero and would not be counted.
    if colors.len() >= reserved {
        return Err(Bad::answer(format!(
            "the message window, its arrow and its cursor use colour-memory entries up to {} and \
             what follows starts at {reserved}",
            colors.len()
        )));
    }
    let colors: Vec<Color> = colors.into_iter().collect();
    let index: HashMap<Color, u8> = colors.iter().enumerate().map(|(i, c)| (*c, i as u8 + 1)).collect();

    let cell_of = |drawn: &[Option<Color>], tx: usize, ty: usize| -> Indices {
        let mut cell = [[0u8; CELL]; CELL];
        for (y, row) in cell.iter_mut().enumerate() {
            for (x, v) in row.iter_mut().enumerate() {
                *v = drawn[(ty * CELL + y) * width + tx * CELL + x].map_or(0, |c| index[&c]);
            }
        }
        cell
    };
    let in_text = |tx: usize, ty: usize| {
        (WINDOW_TEXT_ROW..WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS).contains(&ty)
            && (WINDOW_TEXT_COL..WINDOW_TEXT_COL + WINDOW_TEXT_COLS).contains(&tx)
    };

    // The cells without text are deduplicated as always, and the arrow's
    // after them; the ones in the text area are numbered consecutively from
    // there.
    let mut tiles: Vec<Indices> = Vec::new();
    let mut seen: HashMap<Indices, usize> = HashMap::new();
    let mut tile_of = |c: Indices| -> usize {
        *seen.entry(c).or_insert_with(|| {
            tiles.push(c);
            tiles.len() - 1
        })
    };
    let mut cells = vec![vec![0usize; width / CELL]; height / CELL];
    for (ty, row) in cells.iter_mut().enumerate() {
        for (tx, cell) in row.iter_mut().enumerate() {
            if in_text(tx, ty) {
                continue;
            }
            *cell = tile_of(cell_of(&pixels, tx, ty));
        }
    }
    let mut arrow_tiles = Vec::new();
    for drawn in [&with_arrow, &bare_arrow] {
        for k in 0..WINDOW_ARROW_CELLS {
            arrow_tiles.push(tile_of(cell_of(drawn, WINDOW_ARROW_COL + k, WINDOW_ARROW_ROW)));
        }
    }
    let base = tiles.len();
    let text_tiles = |drawn: &[Option<Color>], rows: std::ops::Range<usize>| -> Vec<u8> {
        let mut out = Vec::new();
        for ty in rows {
            for tx in WINDOW_TEXT_COL..WINDOW_TEXT_COL + WINDOW_TEXT_COLS {
                out.extend(pack_tile(&cell_of(drawn, tx, ty), 4));
            }
        }
        out
    };
    let text_rows = WINDOW_TEXT_ROW..WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS;
    for (n, ty) in text_rows.clone().enumerate() {
        for (m, tx) in (WINDOW_TEXT_COL..WINDOW_TEXT_COL + WINDOW_TEXT_COLS).enumerate() {
            cells[ty][tx] = base + n * WINDOW_TEXT_COLS + m;
        }
    }
    let background = text_tiles(&pixels, text_rows);
    let rows_per_line = WINDOW_LINE / CELL;
    let line_rows = |line: usize| {
        let first = WINDOW_TEXT_ROW + line * rows_per_line;
        first..first + rows_per_line
    };
    let bar: Vec<u8> = with_bar
        .iter()
        .enumerate()
        .flat_map(|(line, drawn)| text_tiles(drawn, line_rows(line)))
        .collect();
    let bar_bare = text_tiles(&bare_bar, line_rows(0));
    if base + WINDOW_TEXT_ROWS * WINDOW_TEXT_COLS > 256 {
        return Err(Bad::answer(format!(
            "the window needs {} tiles —{base} of its frame and its arrow— and the bank has 256",
            base + WINDOW_TEXT_ROWS * WINDOW_TEXT_COLS
        )));
    }

    let mut cgram = vec![0u16];
    cgram.extend(colors.iter().map(|c| cgram_word(*c)));
    cgram.resize(COLORS_PER_PALETTE, 0);
    let color: Vec<u8> = color_row.iter().map(|c| index[c]).collect();
    Ok(Window {
        tiles: tiles.iter().flat_map(|t| pack_tile(t, 4)).collect(),
        cgram,
        cells,
        base,
        background,
        color,
        shadow: index[&shadow],
        arrow: arrow_tiles,
        bar,
        bar_bare,
    })
}

/// A colour-memory word: 0BBB BBGG GGGR RRRR.
pub fn cgram_word(c: Color) -> u16 {
    (c[2] as u16) << 10 | (c[1] as u16) << 5 | c[0] as u16
}

/// The 95 glyphs, twelve rows of eight bits each, **with the bits
/// reversed**: in the font's table bit 0 is the leftmost pixel, and in the
/// console's tile format the leftmost is bit 7. Reversing them here and not
/// in the cartridge comes for free.
///
/// A glyph wider than [`font::INK_MAX`] does not fit the composer: with its
/// shadow it would touch a third cell.
pub fn font_bytes(font: &Font) -> Result<Vec<u8>> {
    if font.ink_width() > font::INK_MAX {
        return Err(Bad::answer(format!(
            "the font has a glyph {} pixels wide, and the console's composer takes {}",
            font.ink_width(),
            font::INK_MAX
        )));
    }
    let mut out = Vec::with_capacity(FONT_GLYPHS * font::HEIGHT);
    for n in 0..FONT_GLYPHS {
        for &row in font.rows(Font::console_char(n)) {
            let mut reversed = 0u8;
            for px in 0..font::INK_MAX {
                if row >> px & 1 != 0 {
                    reversed |= 1 << (7 - px);
                }
            }
            out.push(reversed);
        }
    }
    Ok(out)
}

/// How many columns each of the 95 glyphs paints from where it starts: its
/// ink and its shadow, one column further. It is what the composer checks
/// against the edge of the window before drawing a letter, so that a line
/// that grows on the console —a variable's digits— is cut where it would
/// leave the buffer.
pub fn font_reach(font: &Font) -> Vec<u8> {
    (0..FONT_GLYPHS)
        .map(|n| {
            let ink = font.rows(Font::console_char(n)).iter().map(|r| 16 - r.leading_zeros()).max().unwrap_or(0);
            if ink == 0 {
                0
            } else {
                ink as u8 + 1
            }
        })
        .collect()
}

/// The window's glyphs already composed, for each of the eight phases a
/// character can land on: with a variable-width font a letter starts at
/// any column of a cell. Until 2026-10-03 there were four —x was the
/// border plus six times the column, so modulo 8 it gave 0, 6, 4 or 2 and
/// never anything else—. Per glyph and phase go the cell rows it touches
/// —its twelve, and one more of shadow— and per row the two cells it can
/// step on, each with three words: what is kept of what is there, and what
/// is set in planes 0-1 and in 2-3. The cartridge does
/// `buf = buf & keep | set`.
///
/// The shadow and the glyph come already combined, with `Font::Render`'s
/// order: on a row land the glyph and the shadow of the row above, shifted
/// one pixel, and where they overlap the glyph wins.
///
/// `source` is [`font_bytes`], `colors` the palette index of each glyph
/// row and `shadow` the shadow's. The eight tables, one per phase.
pub fn font_prerender(source: &[u8], colors: &[u8], shadow: u8) -> Vec<Vec<u8>> {
    let glyphs = source.len() / FONT_HEIGHT;
    let mut tables = Vec::new();
    for phase in 0u32..FONT_PHASES as u32 {
        let mut out = Vec::new();
        for c in 0..glyphs {
            let rows = &source[c * FONT_HEIGHT..(c + 1) * FONT_HEIGHT];
            let run: Vec<u32> = rows.iter().map(|&f| ((f as u32) << 8) >> phase).collect();
            for k in 0..FONT_PRE_ROWS {
                let glyph = if k < FONT_HEIGHT { run[k] } else { 0 };
                let color = if k < FONT_HEIGHT { colors[k] as u32 } else { 0 };
                let mut shadow_m = if k >= 1 { run[k - 1] >> 1 } else { 0 };
                shadow_m &= !glyph & 0xFFFF;
                for cell in 0..2 {
                    let shift = if cell == 0 { 8 } else { 0 };
                    let g = (glyph >> shift) & 0xFF;
                    let s = (shadow_m >> shift) & 0xFF;
                    let keep = !((g | s) * 0x0101) & 0xFFFF;
                    let mut words = vec![keep];
                    for bits in [0u32, 2] {
                        let mut word = 0u32;
                        for (m, col) in [(g, color), (s, shadow as u32)] {
                            if col >> bits & 1 != 0 {
                                word |= m;
                            }
                            if col >> (bits + 1) & 1 != 0 {
                                word |= m << 8;
                            }
                        }
                        words.push(word);
                    }
                    for word in words {
                        out.push((word & 0xFF) as u8);
                        out.push((word >> 8) as u8);
                    }
                }
            }
        }
        tables.push(out);
    }
    tables
}
