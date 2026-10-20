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
use std::collections::{BTreeMap, BTreeSet, HashMap};
use voodoo::pack::{pack_tile, Indices};

/// How many colours a 4bpp palette has, 0 being transparent.
const COLORS_PER_PALETTE: usize = 16;

/// The window's bank of tiles, and what of it its frame and its arrow
/// have: what the text area leaves —see [`WINDOW_TEXT_ROW`]—.
const WINDOW_TILES: usize = 256;
pub const FRAME_TILES_MAX: usize = WINDOW_TILES - WINDOW_TEXT_ROWS * WINDOW_TEXT_COLS;

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
    /// How many tiles the frame and the arrow took before they were fused
    /// to fit: `None` if they fitted, and the window is as RM2k draws it.
    pub frame_fused: Option<usize>,
    /// The palette index each of the glyph's twelve rows takes in an option
    /// nobody can pick —an inn's "Yes" without the gold—: System colour 3,
    /// `Font::ColorDisabled`, as **the nearest of the window's own
    /// entries**. The palette has no room for colours of its own: the
    /// maps' backgrounds start right after it, so a grey of its own would
    /// take an entry from every map. See `msg_ink_char` in the runtime.
    pub disabled: Vec<u8>,
    /// How many entries of the palette, from 1, are the window's.
    pub entries: usize,
    /// The entry the box's ink takes, the last one the window reserves:
    /// `None` in a cartridge whose messages use no text colour but 0. See
    /// [`inks`].
    pub ink: Option<u8>,
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
            let channel =
                |v: u8| (div255(v as u32 * coef1 + (0x80 << PRECISION)) >> PRECISION) as u8;
            rgb15([channel(p[0]), channel(p[1]), channel(p[2]), 255])
        })
        .collect()
}

/// The colour-memory entries the message window takes: as many as its
/// colours, from entry 1 —0 is transparent—, so the highest one is this
/// number. They are the System's —the window, its arrow, its cursor, the
/// text and its shadow—, so the game's and not the engine's. **Counted by
/// colour, not by non-zero word**: a black has word zero, and counting
/// words gives one less.
///
/// The converter asks for it once and hands it to everyone who shares
/// colour memory with the window: each map's background starts after it.
///
/// With [`Skin::ink`] the box's ink is the last of them, and the count is
/// the same as without it: the window gives up one of its own colours to
/// leave it room —see [`draw`] and [`inks`]—.
pub fn colors(skin: &Skin) -> Result<usize> {
    colors_with(skin, None)
}

/// [`colors`], with the text's colours laid out by `rows` —see
/// [`TextRows`]—: two Systems' entries may hold the same colour twice.
pub fn colors_with(skin: &Skin, rows: Option<&TextRows>) -> Result<usize> {
    Ok(draw(skin, rows, PALETTE_ENTRIES)?.entries(rows) + skin.ink as usize)
}

/// The entries a window may take after the transparent one: a palette's.
const PALETTE_ENTRIES: usize = COLORS_PER_PALETTE - 1;

/// Which of the glyph's twelve rows go with one palette index, the same in
/// every System the cartridge switches between: the rows each System
/// colours alike, split as finely as any of them splits them —see
/// [`common_rows`]—. **It is what lets the font's composed tables be one
/// for every System**: they carry the index of each row and not its colour,
/// so with the indices fixed a System is only its palette, and the eight
/// tables, some 116 KB, are not carried twice. Entry `k + 1` is class `k`'s
/// colour, and the shadow's is the next one.
pub type TextRows = Vec<Vec<usize>>;

/// The classes of the glyph's rows this System colours alike, in the order
/// of their first row.
pub fn text_rows(skin: &Skin) -> Result<TextRows> {
    let (color_row, _) = text_colors(skin)?;
    let mut classes: Vec<(Color, Vec<usize>)> = Vec::new();
    for (row, c) in color_row.iter().enumerate() {
        match classes.iter_mut().find(|(k, _)| k == c) {
            Some((_, rows)) => rows.push(row),
            None => classes.push((*c, vec![row])),
        }
    }
    Ok(classes.into_iter().map(|(_, rows)| rows).collect())
}

/// The coarsest split of the glyph's rows that is as fine as every one of
/// `each`: two rows go together only if every System colours them alike.
/// In the order of their first row.
pub fn common_rows(each: &[TextRows]) -> TextRows {
    let class_of = |classes: &TextRows, row: usize| classes.iter().position(|c| c.contains(&row));
    let mut out: Vec<(Vec<Option<usize>>, Vec<usize>)> = Vec::new();
    for row in 0..font::HEIGHT {
        let key: Vec<Option<usize>> = each.iter().map(|c| class_of(c, row)).collect();
        match out.iter_mut().find(|(k, _)| *k == key) {
            Some((_, rows)) => rows.push(row),
            None => out.push((key, vec![row])),
        }
    }
    out.into_iter().map(|(_, rows)| rows).collect()
}

/// The empty window and what the cartridge puts over it, each cut to the
/// console's colours, and the colours of all of them together.
#[derive(Clone)]
struct Drawn {
    width: usize,
    height: usize,
    pixels: Vec<Option<Color>>,
    with_arrow: Vec<Option<Color>>,
    bare_arrow: Vec<Option<Color>>,
    with_bar: Vec<Vec<Option<Color>>>,
    bare_bar: Vec<Option<Color>>,
    color_row: Vec<Color>,
    shadow: Color,
    colors: BTreeSet<Color>,
    /// How many colours the System brought, before [`Drawn::reduce`].
    brought: usize,
    /// What [`Drawn::reduce`] merged: empty if they fitted.
    merges: Vec<adeleine::Merge>,
    /// How many tiles the frame and the arrow took before [`fit_frame`]
    /// fused them: `None` if they fitted.
    frame_fused: Option<usize>,
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
/// starts: the window may not reach it. [`colors`] says where it ends.
pub fn convert(skin: &Skin, reserved: usize) -> Result<Window> {
    convert_with(skin, reserved, None)
}

/// [`convert`], with the text's colours at the entries `rows` fixes —see
/// [`TextRows`]—, for a cartridge that switches System: every System's
/// window then composes its letters with the same tables.
///
/// **A System the cartridge switches to fits in what the starting one
/// takes**, `reserved` minus one: if it brings more, it is reduced like one
/// that does not fit a palette. The maps' backgrounds start after the
/// window, so a second System never takes colours from them; what it loses
/// is its own, and the converter writes it in the game's patches.
pub fn convert_with(skin: &Skin, reserved: usize, rows: Option<&TextRows>) -> Result<Window> {
    let drawn = draw(skin, rows, reserved.saturating_sub(1).min(PALETTE_ENTRIES))?;
    let entries = drawn.entries(rows);
    let (palette, index, color, shadow) = drawn.palette(rows);
    let Drawn {
        width,
        height,
        pixels,
        with_arrow,
        bare_arrow,
        with_bar,
        bare_bar,
        frame_fused,
        ..
    } = drawn;
    // What follows starts where this ends, so if the window grew it would
    // step on it and the cartridge would draw the text with a colour of the
    // map. The highest entry is the number of colours —0 is transparent and
    // the rest go in order—, and not how many words are nonzero: a black
    // colour has word zero and would not be counted. The box's ink, if the
    // window keeps one, is the last entry before what follows: the same in
    // every System, whose own colours may stop short of it.
    let ink = skin
        .ink
        .then(|| reserved.saturating_sub(1).min(PALETTE_ENTRIES) as u8);
    if entries + skin.ink as usize >= reserved {
        return Err(Bad::answer(format!(
            "the message window, its arrow and its cursor use colour-memory entries up to {entries} and \
             what follows starts at {reserved}"
        )));
    }

    let cell_of = |drawn: &[Option<Color>], tx: usize, ty: usize| -> Indices {
        let mut cell = [[0u8; CELL]; CELL];
        for (y, row) in cell.iter_mut().enumerate() {
            for (x, v) in row.iter_mut().enumerate() {
                *v = drawn[(ty * CELL + y) * width + tx * CELL + x].map_or(0, |c| index[&c]);
            }
        }
        cell
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
            arrow_tiles.push(tile_of(cell_of(
                drawn,
                WINDOW_ARROW_COL + k,
                WINDOW_ARROW_ROW,
            )));
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
    // `draw` already fused the frame until it fitted: this is the net.
    if base > FRAME_TILES_MAX {
        return Err(Bad::answer(format!(
            "the window needs {} tiles —{base} of its frame and its arrow— and the bank has {WINDOW_TILES}",
            base + WINDOW_TEXT_ROWS * WINDOW_TEXT_COLS
        )));
    }

    let disabled = ink_colors(skin, INK_DISABLED)
        .iter()
        .map(|c| nearest(&palette, *c))
        .collect();
    let mut cgram = vec![0u16];
    cgram.extend(palette.iter().map(|c| cgram_word(*c)));
    cgram.resize(COLORS_PER_PALETTE, 0);
    Ok(Window {
        disabled,
        ink,
        entries: palette.len(),
        tiles: tiles.iter().flat_map(|t| pack_tile(t, 4)).collect(),
        cgram,
        cells,
        base,
        background,
        color,
        shadow,
        arrow: arrow_tiles,
        bar,
        bar_bare,
        frame_fused,
    })
}

/// Whether the cell `(tx, ty)` of the window is in the text area, whose
/// tiles are the cartridge's to write and are not deduplicated.
fn in_text(tx: usize, ty: usize) -> bool {
    (WINDOW_TEXT_ROW..WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS).contains(&ty)
        && (WINDOW_TEXT_COL..WINDOW_TEXT_COL + WINDOW_TEXT_COLS).contains(&tx)
}

/// The window's cells outside the text area: its frame, and what of its
/// background the text area leaves.
fn frame_cells() -> Vec<(usize, usize)> {
    (0..WINDOW_ROWS_INC)
        .flat_map(|ty| (0..WINDOW_COLS_INC).map(move |tx| (tx, ty)))
        .filter(|&(tx, ty)| !in_text(tx, ty))
        .collect()
}

/// `arrow` pasted at its place over `under`.
fn arrow_over(under: &Picture, arrow: &Picture) -> Picture {
    let mut out = under.clone();
    let (x, y) = (
        (WINDOW_ARROW_COL * CELL) as i64,
        (WINDOW_ARROW_ROW * CELL) as i64,
    );
    cells::paste(&mut out, arrow, x, y);
    out
}

/// How many tiles the frame and the arrow take, counted as [`convert`]
/// counts them: the empty window and the arrow over it cut over black, and
/// the arrow over nothing with its transparency.
fn frame_tiles(empty: &Picture, arrow: &Picture) -> usize {
    let opaque = |t: adeleine::Tile| t.map(|row| row.map(|p| Some(p.unwrap_or(BLACK))));
    let mut seen: BTreeSet<adeleine::Tile> = frame_cells()
        .into_iter()
        .map(|(tx, ty)| opaque(cells::tile_at(empty, tx, ty)))
        .collect();
    let over = arrow_over(empty, arrow);
    let bare = arrow_over(&Picture::transparent(empty.width, empty.height), arrow);
    for k in 0..WINDOW_ARROW_CELLS {
        seen.insert(opaque(cells::tile_at(
            &over,
            WINDOW_ARROW_COL + k,
            WINDOW_ARROW_ROW,
        )));
        seen.insert(cells::tile_at(
            &bare,
            WINDOW_ARROW_COL + k,
            WINDOW_ARROW_ROW,
        ));
    }
    seen.len()
}

/// A frame with more tiles than the bank leaves it is drawn with fewer. It
/// is a System whose stretched background is a gradient that shows through
/// the frame: every row of the gradient makes the edge a cell of its own.
/// So **the background under the frame** has its cells most alike fused
/// —[`cells::group_cells`]—, as few as it takes for the frame and the arrow
/// to fit, and the frame goes over them as it is: what changes is the
/// gradient seen through it, in bands. The text area has a tile per cell
/// anyway, and its background stays as RM2k draws it. Answers how many
/// tiles the frame and the arrow took before, or `None` if they fitted and
/// nothing was touched.
fn fit_frame(skin: &Skin, empty: &mut Picture, arrow: &Picture) -> Option<usize> {
    let spent = frame_tiles(empty, arrow);
    if spent <= FRAME_TILES_MAX {
        return None;
    }
    let background = skin.window_background(WINDOW_WIDTH, WINDOW_HEIGHT);
    let at = frame_cells();
    // How many tiles a group costs depends on the frame over it, so they
    // are asked for one fewer at a time: the ring is some eighty cells.
    let mut ask = cells::group_cells(&mut background.clone(), &at, usize::MAX);
    loop {
        ask -= 1;
        let mut fused = background.clone();
        cells::group_cells(&mut fused, &at, ask);
        rm2k_render::system::frame_over(&mut fused, &skin.picture);
        *empty = fused;
        if ask <= 1 || frame_tiles(empty, arrow) <= FRAME_TILES_MAX {
            return Some(spent);
        }
    }
}

/// The colour of each of the glyph's twelve rows and the shadow's, from
/// the System's 16x16 block, the one `Font::Render` uses as a mask. Each
/// row of the glyph takes a single one —the gradient is horizontally
/// uniform—, so they are twelve colours, not a block, and the shadow is a
/// single one.
///
/// A row that is not uniform is drawn with the colour most of it has, the
/// leftmost of those that tie: the cartridge composes a row with one. Until
/// 2026-10-12 that stopped the game, and no System any game started with
/// had one; Vampires Dawn switches to one —see [`mixed_text_rows`]—.
fn text_colors(skin: &Skin) -> Result<(Vec<Color>, Color)> {
    let ink = line::Ink::new(&skin.picture, 0);
    Ok((ink_colors(skin, 0), rgb15(ink.shadow_at(0, 0))))
}

/// The colour of each of the glyph's twelve rows in text colour `color`:
/// the one most of the row has, the leftmost of those that tie.
fn ink_colors(skin: &Skin, color: i32) -> Vec<Color> {
    let ink = line::Ink::new(&skin.picture, color);
    let mut color_row = Vec::new();
    for py in 0..font::HEIGHT {
        let row: Vec<Color> = (0..font::INK_MAX)
            .map(|px| rgb15(ink.text_at(px, py)))
            .collect();
        let most = row
            .iter()
            .max_by_key(|c| {
                (
                    row.iter().filter(|d| d == c).count(),
                    std::cmp::Reverse(row.iter().position(|d| d == *c)),
                )
            })
            .copied()
            .expect("a row has pixels");
        color_row.push(most);
    }
    color_row
}

/// The entry of `palette` —which starts at entry 1— nearest to `c`, by the
/// distance between the fifteen-bit channels; the first of those that tie.
fn nearest(palette: &[Color], c: Color) -> u8 {
    let far = |p: &Color| -> u32 {
        (0..3)
            .map(|k| (p[k] as i32 - c[k] as i32).pow(2) as u32)
            .sum()
    };
    palette
        .iter()
        .enumerate()
        .min_by_key(|(i, p)| (far(p), *i))
        .map_or(0, |(i, _)| i as u8 + 1)
}

/// The text in the System's twenty colours, `\c[n]`, as the console draws
/// it: for each colour, the word the box's ink entry takes when that colour
/// is the box's ink, and the palette index each of the glyph's twelve rows
/// takes with it and without it.
#[derive(Debug, Clone, PartialEq)]
pub struct Inks {
    /// One per text colour, 0 to 19.
    pub colours: Vec<Ink>,
}

/// One text colour: see [`Inks`].
#[derive(Debug, Clone, PartialEq)]
pub struct Ink {
    /// The colour the ink entry takes for it: the mean of its rows'
    /// colours, weighted by how many of the font's pixels each row has.
    pub word: u16,
    /// Each glyph row's entry when it is the box's ink: the ink's, or one
    /// of the window's if it is nearer.
    pub inked: Vec<u8>,
    /// And when another colour has the ink: the window's nearest.
    pub plain: Vec<u8>,
}

/// The colours a box can type, for `window`, drawn with `font`.
///
/// **One entry for all of them, the box's ink.** RM2k draws a colour with
/// the System's 16x16 block, a gradient of some eight shades, and the
/// console's window has no room for them: its palette is 0, the maps'
/// backgrounds start right after it, and Systems that fill the fifteen
/// entries are common. So a cartridge whose boxes use a colour keeps one
/// entry for it —[`Skin::ink`]—, which one of the window's own colours gives
/// up —see [`draw`]—, and the first colour other than 0 a box types takes
/// it: the console writes its `word` there and recolours that
/// colour's letters with `inked`. Another colour in the same box is drawn
/// with `plain`, the window's nearest, as the grey of an option nobody can
/// pick is —see `disabled`—. Colour 0 is the window's own: its rows are the
/// font's.
pub fn inks(skin: &Skin, window: &Window, font: &Font) -> Inks {
    let palette: Vec<Color> = window.cgram[1..=window.entries]
        .iter()
        .map(|&w| [(w & 31) as u8, (w >> 5 & 31) as u8, (w >> 10 & 31) as u8])
        .collect();
    // How many of the font's pixels each row has, over its printable ASCII:
    // what the ink's one colour has to look like most.
    let mut weight = [0u32; font::HEIGHT];
    for ch in (33u8..127).map(char::from) {
        for (_, py) in font.pixels(ch) {
            if py < font::HEIGHT {
                weight[py] += 1;
            }
        }
    }
    let total: u32 = weight.iter().sum::<u32>().max(1);
    let colours = (0..rm2k_snes_text::refit::COLOURS as i32)
        .map(|n| {
            if n == 0 {
                return Ink {
                    word: 0,
                    inked: window.color.clone(),
                    plain: window.color.clone(),
                };
            }
            let rows = ink_colors(skin, n);
            let mean: Color = std::array::from_fn(|k| {
                let sum: u32 = rows.iter().zip(weight).map(|(c, w)| c[k] as u32 * w).sum();
                ((sum + total / 2) / total) as u8
            });
            let plain: Vec<u8> = rows.iter().map(|c| nearest(&palette, *c)).collect();
            let inked = match window.ink {
                None => plain.clone(),
                Some(entry) => {
                    let far = |p: &Color, c: &Color| -> u32 {
                        (0..3)
                            .map(|k| (p[k] as i32 - c[k] as i32).pow(2) as u32)
                            .sum()
                    };
                    rows.iter()
                        .zip(&plain)
                        .map(|(c, &own)| {
                            let window_far = far(&palette[own as usize - 1], c);
                            if far(&mean, c) <= window_far {
                                entry
                            } else {
                                own
                            }
                        })
                        .collect()
                }
            };
            Ink {
                word: cgram_word(mean),
                inked,
                plain,
            }
        })
        .collect();
    Inks { colours }
}

/// RM2k's `Window_Gold`, which `ShowInn` opens next to its greeting: the
/// empty window, 88x32, with the gold term written at its right edge in
/// text colour 1, cut into 8x8 tiles row by row for the console's
/// objects; and the sprite palette they go in. The number is not drawn:
/// the console composes it, right-aligned to `right`, with the window's
/// font tables —see `gold_compose` in the runtime—.
///
/// It is `Window_Base::DrawCurrencyValue(gold, contents width, 2)`: the
/// term right-aligned at the contents' edge and the number right-aligned
/// where the term starts, both two pixels below the contents' top.
#[derive(Debug, Clone)]
pub struct Gold {
    /// The 44 tiles, 4bpp, eleven per row and four rows.
    pub tiles: Vec<u8>,
    /// The sixteen words of the sprite palette: the window's own entries
    /// as they are, and after them the colours the window does not have
    /// —the term's, mostly—, the most used first, while they fit. One that
    /// does not fit is drawn with the nearest.
    pub cgram: Vec<u16>,
    /// Where the number ends, in pixels from the window's left edge.
    pub right: usize,
}

pub fn gold(skin: &Skin, window: &Window, font: &Font, term: &str) -> Result<Gold> {
    let mut picture = skin.window(GOLD_WIDTH, GOLD_HEIGHT);
    let edge = GOLD_WIDTH - BORDER;
    let term_width = font.width(term);
    if term_width + font.width("999999") > edge - BORDER {
        return Err(Bad::answer(format!(
            "the gold term {term:?} and six digits do not fit in the gold window"
        )));
    }
    let right = edge - term_width;
    line::draw_line(
        &mut picture,
        &skin.picture,
        right as i64,
        GOLD_TEXT_Y as i64,
        term,
        1,
        font,
    );
    let pixels = cut(&picture, true);
    let mut palette: Vec<Color> = window.cgram[1..=window.entries]
        .iter()
        .map(|&w| [(w & 31) as u8, (w >> 5 & 31) as u8, (w >> 10 & 31) as u8])
        .collect();
    let mut counts: BTreeMap<Color, usize> = BTreeMap::new();
    for c in pixels.iter().flatten() {
        if !palette.contains(c) {
            *counts.entry(*c).or_default() += 1;
        }
    }
    let mut extra: Vec<(usize, Color)> = counts.into_iter().map(|(c, n)| (n, c)).collect();
    extra.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
    for (_, c) in extra
        .into_iter()
        .take(COLORS_PER_PALETTE - 1 - palette.len())
    {
        palette.push(c);
    }
    let index = |c: &Option<Color>| -> u8 {
        match c {
            None => 0,
            Some(c) => match palette.iter().position(|p| p == c) {
                Some(i) => i as u8 + 1,
                None => nearest(&palette, *c),
            },
        }
    };
    let mut tiles = Vec::new();
    for ty in 0..GOLD_HEIGHT / CELL {
        for tx in 0..GOLD_WIDTH / CELL {
            let mut cell = [[0u8; CELL]; CELL];
            for (y, row) in cell.iter_mut().enumerate() {
                for (x, v) in row.iter_mut().enumerate() {
                    *v = index(&pixels[(ty * CELL + y) * GOLD_WIDTH + tx * CELL + x]);
                }
            }
            tiles.extend(pack_tile(&cell, 4));
        }
    }
    let mut cgram = vec![0u16];
    cgram.extend(palette.iter().map(|c| cgram_word(*c)));
    cgram.resize(COLORS_PER_PALETTE, 0);
    Ok(Gold {
        tiles,
        cgram,
        right,
    })
}

/// The rows of the glyph whose text colour is not uniform in this System,
/// which the window draws with one colour each —see `text_colors`—: what
/// the conversion warns about.
pub fn mixed_text_rows(skin: &Skin) -> Vec<usize> {
    let ink = line::Ink::new(&skin.picture, 0);
    (0..font::HEIGHT)
        .filter(|&py| {
            (0..font::INK_MAX)
                .map(|px| rgb15(ink.text_at(px, py)))
                .collect::<BTreeSet<Color>>()
                .len()
                > 1
        })
        .collect()
}

/// The window drawn, with its colours taken to `cap` entries at most —see
/// [`Drawn::entries`]—; and if it keeps the box's ink, to one fewer than it
/// would take without it.
///
/// **The window pays for its ink, not the maps**: the entries it takes are
/// the same with the ink as without it, and one of its own colours is
/// merged to leave the ink room —Adeleine decides which, and the converter
/// writes it in the game's patches like any colour a System loses—. Taking
/// an entry past the window instead would take it from every map's
/// background, which starts right after: in the test game's meadow that
/// was a dark green of the bushes, 2,168 pixels of every capture.
fn draw(skin: &Skin, rows: Option<&TextRows>, cap: usize) -> Result<Drawn> {
    if !skin.ink {
        return draw_colours(skin, rows, cap);
    }
    let plain = draw_colours(skin, rows, cap)?.entries(rows);
    draw_colours(skin, rows, plain.min(cap).saturating_sub(1).max(1))
}

/// [`draw`], without the ink.
fn draw_colours(skin: &Skin, rows: Option<&TextRows>, cap: usize) -> Result<Drawn> {
    let mut empty = skin.window(WINDOW_WIDTH, WINDOW_HEIGHT);
    let arrow = rm2k_render::system::arrow_down(&skin.picture);
    let frame_fused = fit_frame(skin, &mut empty, &arrow);
    let (width, height) = (empty.width, empty.height);
    let pixels = cut(&empty, false);

    // What the cartridge puts over the empty window, each drawn whole and
    // cut like it: the arrow on the bottom edge, and the cursor on each
    // line. Over the window, and over nothing for the one without a
    // background.
    let (arrow_x, arrow_y) = (
        (WINDOW_ARROW_COL * CELL) as i64,
        (WINDOW_ARROW_ROW * CELL) as i64,
    );
    let mut with_arrow = empty.clone();
    cells::paste(&mut with_arrow, &arrow, arrow_x, arrow_y);
    let mut bare_arrow = Picture::transparent(width, height);
    cells::paste(&mut bare_arrow, &arrow, arrow_x, arrow_y);
    // The bar: the System's cursor on the rectangle
    // `Window_Message::UpdateCursorRect` gives for each line.
    let bar_x = (WINDOW_TEXT_COL * CELL + CHOICE_BAR_X) as i64;
    let bar_y = |line: usize| (WINDOW_TEXT_ROW * CELL + line * WINDOW_LINE) as i64;
    let bar = |dest: &mut Picture, line: usize| {
        let (w, h) = (MESSAGE_WIDTH - CHOICE_BAR_TRIM, WINDOW_LINE);
        rm2k_render::system::cursor_over(dest, &skin.picture, bar_x, bar_y(line), w, h, 0);
    };
    let lines = WINDOW_TEXT_ROWS * CELL / WINDOW_LINE;
    let with_bar: Vec<Vec<Option<Color>>> = (0..lines)
        .map(|line| {
            let mut p = empty.clone();
            bar(&mut p, line);
            cut(&p, false)
        })
        .collect();
    let mut bare_bar = Picture::transparent(width, height);
    bar(&mut bare_bar, 0);
    let with_arrow = cut(&with_arrow, false);
    let bare_arrow = cut(&bare_arrow, true);
    let bare_bar = cut(&bare_bar, true);

    let (color_row, shadow) = text_colors(skin)?;

    let mut drawn = Drawn {
        width,
        height,
        pixels,
        with_arrow,
        bare_arrow,
        with_bar,
        bare_bar,
        color_row,
        shadow,
        colors: BTreeSet::new(),
        brought: 0,
        merges: Vec::new(),
        frame_fused,
    };
    drawn.colors = drawn.all_colors();
    drawn.brought = drawn.colors.len();
    if drawn.entries(rows) > cap {
        // With the text's rows fixed a colour may take two entries, so the
        // colours are taken to one fewer at a time until the entries fit.
        let whole = drawn.clone();
        let mut colors = cap;
        loop {
            drawn = whole.clone();
            drawn.reduce(colors)?;
            if drawn.entries(rows) <= cap || colors <= 1 {
                break;
            }
            colors -= 1;
        }
    }
    Ok(drawn)
}

impl Drawn {
    /// How many colour-memory entries the window takes after the
    /// transparent one: one per colour; or, with the text's rows fixed, one
    /// per class of rows, the shadow's, and one per other colour.
    fn entries(&self, rows: Option<&TextRows>) -> usize {
        match rows {
            None => self.colors.len(),
            Some(rows) => {
                let text: BTreeSet<Color> = self
                    .color_row
                    .iter()
                    .copied()
                    .chain([self.shadow])
                    .collect();
                rows.len() + 1 + self.colors.difference(&text).count()
            }
        }
    }

    /// The palette from entry 1, each colour's index, each glyph row's and
    /// the shadow's. Without `rows`, the colours in order. With them, class
    /// `k`'s colour at `k + 1`, the shadow's after them and the rest in
    /// order; a colour of the text that the frame uses too takes the text's
    /// entry.
    fn palette(&self, rows: Option<&TextRows>) -> (Vec<Color>, HashMap<Color, u8>, Vec<u8>, u8) {
        let Some(rows) = rows else {
            let palette: Vec<Color> = self.colors.iter().copied().collect();
            let index: HashMap<Color, u8> = palette
                .iter()
                .enumerate()
                .map(|(i, c)| (*c, i as u8 + 1))
                .collect();
            let color = self.color_row.iter().map(|c| index[c]).collect();
            let shadow = index[&self.shadow];
            return (palette, index, color, shadow);
        };
        let mut palette: Vec<Color> = rows.iter().map(|class| self.color_row[class[0]]).collect();
        palette.push(self.shadow);
        let mut index: HashMap<Color, u8> = HashMap::new();
        for (i, c) in palette.iter().enumerate() {
            index.entry(*c).or_insert(i as u8 + 1);
        }
        for c in &self.colors {
            if !index.contains_key(c) {
                palette.push(*c);
                index.insert(*c, palette.len() as u8);
            }
        }
        let color = (0..font::HEIGHT)
            .map(|row| {
                rows.iter()
                    .position(|class| class.contains(&row))
                    .expect("every row has a class") as u8
                    + 1
            })
            .collect();
        (palette, index, color, rows.len() as u8 + 1)
    }

    /// Every colour the cartridge may put in the window. The arrow and the
    /// cursor count even though the empty window does not draw them, as
    /// the text does: they are the cartridge's to put.
    fn all_colors(&self) -> BTreeSet<Color> {
        let mut colors: BTreeSet<Color> = BTreeSet::new();
        for drawn in [
            &self.pixels,
            &self.with_arrow,
            &self.bare_arrow,
            &self.bare_bar,
        ]
        .into_iter()
        .chain(&self.with_bar)
        {
            colors.extend(drawn.iter().flatten().copied());
        }
        colors.extend(self.color_row.iter().copied());
        colors.insert(self.shadow);
        colors
    }

    /// A System whose window, arrow, cursor and text do not fit in one
    /// palette: Adeleine's `merge_least_visible` takes them to `colors`, and
    /// every drawing is repainted with what is left. Each colour weighs the
    /// pixels it covers in the empty window, the arrow over nothing and one
    /// line's cursor over nothing —what is seen of each, once—; and the
    /// text's, which the empty window does not draw, weigh **a whole row of
    /// the text area on every line**: each of the glyph's rows, and the
    /// shadow, as if every line were full of letters. Counted only by what
    /// the empty window shows, the text would be the first to go, and it is
    /// what the window is for.
    ///
    /// A System that already fits never comes here, so its window is the
    /// one it always was.
    fn reduce(&mut self, colors: usize) -> Result<()> {
        let mut counts: BTreeMap<Color, u64> = BTreeMap::new();
        for drawn in [&self.pixels, &self.bare_arrow, &self.bare_bar] {
            for c in drawn.iter().flatten() {
                *counts.entry(*c).or_default() += 1;
            }
        }
        let lines = WINDOW_TEXT_ROWS * CELL / WINDOW_LINE;
        let text_row = (WINDOW_TEXT_COLS * CELL * lines) as u64;
        for c in self.color_row.iter().chain([&self.shadow]) {
            *counts.entry(*c).or_default() += text_row;
        }
        // The arrow and the cursor over the window only bring colours of
        // the drawings above, but if one did not, it still needs a place:
        // it weighs a pixel.
        for c in self.all_colors() {
            counts.entry(c).or_insert(1);
        }
        let counts: Vec<(Color, u64)> = counts.into_iter().collect();
        let merged = adeleine::merge_least_visible(&counts, colors)?;
        let to: HashMap<Color, Color> = counts
            .iter()
            .map(|(c, _)| *c)
            .zip(merged.mapping.iter().copied())
            .collect();
        for drawn in [
            &mut self.pixels,
            &mut self.with_arrow,
            &mut self.bare_arrow,
            &mut self.bare_bar,
        ]
        .into_iter()
        .chain(self.with_bar.iter_mut())
        {
            for c in drawn.iter_mut().flatten() {
                *c = to[c];
            }
        }
        for c in self.color_row.iter_mut().chain([&mut self.shadow]) {
            *c = to[c];
        }
        self.colors = self.all_colors();
        self.merges = merged.merges;
        Ok(())
    }
}

/// What a System lost to fit its window in one palette: how many colours
/// the window brought, and Adeleine's merges in the order they were made
/// —none if it already fitted—. It is a decision of the game's, and the
/// converter writes it in the game's patches.
pub fn reduction(skin: &Skin) -> Result<(usize, Vec<adeleine::Merge>)> {
    reduction_with(skin, None)
}

/// [`reduction`], with the text's rows fixed: see [`TextRows`].
pub fn reduction_with(
    skin: &Skin,
    rows: Option<&TextRows>,
) -> Result<(usize, Vec<adeleine::Merge>)> {
    reduction_capped(skin, rows, PALETTE_ENTRIES)
}

/// [`reduction_with`], fitted in `cap` entries: a System the cartridge
/// switches to, in what the starting one takes —see [`convert_with`]—.
pub fn reduction_capped(
    skin: &Skin,
    rows: Option<&TextRows>,
    cap: usize,
) -> Result<(usize, Vec<adeleine::Merge>)> {
    let drawn = draw(skin, rows, cap.min(PALETTE_ENTRIES))?;
    Ok((drawn.brought, drawn.merges))
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
    font_bytes_with(font, &[])
}

/// The console's glyphs, and after them `letters`: the Latin-1 the message
/// boxes draw —see `Window::carrying` in `rm2k-snes-events`—.
fn console_chars(letters: &[char]) -> impl Iterator<Item = char> + '_ {
    (0..FONT_GLYPHS)
        .map(Font::console_char)
        .chain(letters.iter().copied())
}

/// [`font_bytes`], with `letters` after the console's glyphs: the message
/// window's, whose boxes draw them.
pub fn font_bytes_with(font: &Font, letters: &[char]) -> Result<Vec<u8>> {
    if let Some(&c) = letters.iter().find(|&&c| !font.draws(c)) {
        return Err(Bad::answer(format!(
            "the boxes draw {c:?}, and the font does not have it"
        )));
    }
    if font.ink_width() > font::INK_MAX {
        return Err(Bad::answer(format!(
            "the font has a glyph {} pixels wide, and the console's composer takes {}",
            font.ink_width(),
            font::INK_MAX
        )));
    }
    let mut out = Vec::with_capacity((FONT_GLYPHS + letters.len()) * font::HEIGHT);
    for c in console_chars(letters) {
        for &row in font.rows(c) {
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
    font_reach_with(font, &[])
}

/// [`font_reach`], with `letters` after the console's glyphs, like
/// [`font_bytes_with`].
pub fn font_reach_with(font: &Font, letters: &[char]) -> Vec<u8> {
    console_chars(letters)
        .map(|c| {
            let ink = font
                .rows(c)
                .iter()
                .map(|r| 16 - r.leading_zeros())
                .max()
                .unwrap_or(0);
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

#[cfg(test)]
mod tests {
    use super::*;

    /// The letters the boxes draw go after the console's 96 glyphs, each
    /// with its rows and its reach; one the font lacks is refused.
    #[test]
    fn the_letters_the_boxes_draw_go_after_the_console_s_glyphs() {
        let f = Font::named("low-variable", font::MINCHO).unwrap();
        let ascii = font_bytes(&f).unwrap();
        let with = font_bytes_with(&f, &['é', 'ñ']).unwrap();
        assert_eq!(with.len(), ascii.len() + 2 * font::HEIGHT);
        assert_eq!(with[..ascii.len()], ascii);
        assert_ne!(
            with[ascii.len()..ascii.len() + font::HEIGHT],
            with[ascii.len() + font::HEIGHT..]
        );
        assert_eq!(font_reach_with(&f, &['é']).len(), FONT_GLYPHS + 1);
        assert!(font_bytes_with(&Font::rm2k(font::MINCHO), &['é']).is_err());
    }
}
