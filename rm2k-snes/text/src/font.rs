//! The letters: a font as a table of glyphs and how far each one moves the
//! line, and where a game's comes from.
//!
//! **A font is a sheet**: an indexed PNG with the 95 printable ASCII
//! characters, each in its cell, which is what a person edits by hand —see
//! [`Font::from_sheet`] for its shape—. The engine carries one,
//! `fonts/low-variable.png`, a variable-width font for the console's 256
//! pixels; a game names it, or the path of its own sheet, in its project
//! file.
//!
//! The other way is RM2k's own: easyrpg-player's two 6x12 fonts, every
//! letter six pixels wide, and which of the two is decided by the game's
//! `font_id` —[`Font::rm2k`]—. It is what the screens drew with until
//! 2026-10-03, and it is still a font like any other: a sheet of fixed
//! advance.
//!
//! Printable ASCII, and a sheet may carry Latin-1 too —U+00A0 to U+00FF,
//! six more rows of cells—: the engine's does. A character without a glyph
//! is drawn as a space; the text that reaches the cartridge has already
//! stood a plain ASCII letter in for it —see [`crate::plain`]—.

use crate::glyphs;

/// RM2k's glyph: six pixels wide, twelve tall.
pub const WIDTH: usize = 6;
pub const HEIGHT: usize = 12;

/// The two values of `font_id` in RM2k's System (`lcf::rpg::System::Font`).
pub const GOTHIC: i32 = 0;
pub const MINCHO: i32 = 1;

/// The first character with a glyph, and how many there are: the space to
/// the tilde.
pub const FIRST: u32 = 32;
pub const GLYPHS: usize = 95;

/// The first Latin-1 character a sheet may carry, and how many: U+00A0, the
/// no-break space, to U+00FF, `ÿ`. They are RM2k's: its font has them, and
/// the games in Spanish, German or French use them.
pub const LATIN_FIRST: u32 = 0xA0;
pub const LATIN_GLYPHS: usize = 96;

/// A blank as wide as `>`, which a sheet does not have: it goes in front of
/// the options a cursor is not on, so that the options do not move when it
/// does —`ShowChoice`'s and `InputNumber`'s digits—. With RM2k's font a
/// space did that; with a variable-width one a space is narrower than the
/// cursor. It is DEL, the one ASCII code after the tilde, so on the console
/// it is simply glyph 95: see [`CONSOLE_GLYPHS`].
pub const CURSOR_BLANK: char = '\u{7f}';

/// How many glyphs the console's tables carry: the sheet's 95 and
/// [`CURSOR_BLANK`].
pub const CONSOLE_GLYPHS: usize = GLYPHS + 1;

/// A blank as wide as a digit, which pads a number on the left so that
/// numbers line up in a column: the screens' "%3d". It is not a glyph of the
/// tables but a letter the console's text layer knows —`TL_FIGURE`, 96—,
/// and in a text it is Unicode's figure space.
pub const FIGURE_BLANK: char = '\u{2007}';

/// The widest a glyph's ink can be in a font for the console's low
/// resolution: with its shadow one pixel further, that is nine columns,
/// and from any of a cell's eight starting columns it still touches two
/// cells and no more. It is what the cartridge's composer is built on.
pub const INK_MAX: usize = 8;

/// The most pixels [`Font::with_spacing`] adds between letters: the project
/// file's `[text] letter_spacing` goes from 0 to this. It is a knob to try
/// how a font reads with more air, not a way to design one —that is the
/// sheet's advance row—, and the 3 is taro's, 2026-10-03.
pub const SPACING_MAX: i64 = 3;

/// The widest a letter's advance can be once spaced: a cell. The battle
/// checks its victory lines counting letters, one per cell —see
/// `check_victory` in `rm2k-snes-battle`, which does not know the font—,
/// and that holds only while no letter moves the line further than a cell.
pub const SPACED_ADVANCE_MAX: usize = 8;

/// The fonts the engine carries, by the name a project file gives them.
const BUNDLED: [(&str, &[u8]); 1] = [("low-variable", include_bytes!("../fonts/low-variable.png"))];

/// The name that asks for RM2k's own fixed-width fonts, the one `font_id`
/// picks.
pub const RM2K: &str = "rm2k";

/// A font: each glyph's twelve rows and how many columns the line moves
/// after it. Bit `b` of a row is the pixel of column `b`, bit 0 the
/// leftmost. The 95 of ASCII, and after them, when the sheet has them, the
/// 96 of Latin-1.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Font {
    rows: Vec<[u16; HEIGHT]>,
    advance: Vec<u8>,
}

impl Font {
    /// RM2k's: easyrpg's Mincho for `font_id` 1 and Gothic for anything
    /// else, as easyrpg does, every letter six pixels wide.
    pub fn rm2k(font_id: i32) -> Font {
        let table = if font_id == MINCHO {
            &glyphs::MINCHO
        } else {
            &glyphs::GOTHIC
        };
        Font {
            rows: table.iter().map(|g| g.map(u16::from)).collect(),
            advance: vec![WIDTH as u8; GLYPHS],
        }
    }

    /// The font `spec` names: [`RM2K`], one the engine carries, or the path
    /// of a sheet. `font_id` is the game's, which only RM2k's uses.
    pub fn named(spec: &str, font_id: i32) -> Result<Font, String> {
        if spec == RM2K {
            return Ok(Font::rm2k(font_id));
        }
        if let Some((_, bytes)) = BUNDLED.iter().find(|(name, _)| *name == spec) {
            return Font::from_sheet(bytes).map_err(|e| format!("the font {spec:?}: {e}"));
        }
        let bytes = std::fs::read(spec).map_err(|e| {
            format!(
                "the font {spec:?} is not {RM2K:?}, nor one of the engine's ({}), nor a sheet that \
                 can be read: {e}",
                BUNDLED.map(|(n, _)| n).join(", ")
            )
        })?;
        Font::from_sheet(&bytes).map_err(|e| format!("{spec}: {e}"))
    }

    /// This font with `pixels` more of air after every letter: the project
    /// file's `[text] letter_spacing`. Each glyph's advance already carries
    /// its own air —see the sheet's advance row—, and this adds to it, the
    /// space and the digits too, so numbers still line up and a space is
    /// still the gap between two words of spaced letters. The glyphs do not
    /// change. It goes here, where the advance is born, so that whoever
    /// measures a line —the reflow, the screens, the table the cartridge
    /// carries— measures the same.
    ///
    /// It applies to RM2k's font as well: it is a font like any other, of
    /// fixed advance, and it stays fixed, six pixels and these.
    ///
    /// From 0 to [`SPACING_MAX`], and no letter may end up wider than
    /// [`SPACED_ADVANCE_MAX`]; otherwise the error says why.
    pub fn with_spacing(mut self, pixels: i64) -> Result<Font, String> {
        if !(0..=SPACING_MAX).contains(&pixels) {
            return Err(format!(
                "{pixels} is not a spacing: it goes from 0 —the font as its sheet draws it— to \
                 {SPACING_MAX}, pixels added after every letter; a negative one would put a letter's \
                 shadow on the next one, since each letter's air is where its shadow falls"
            ));
        }
        let widest = (0..self.advance.len())
            .max_by_key(|&i| self.advance[i])
            .unwrap_or(0);
        // An empty Latin-1 cell stays empty: no advance, not drawn.
        let undrawn: Vec<usize> = (GLYPHS..self.advance.len())
            .filter(|&g| self.advance[g] == 0)
            .collect();
        let spaced = self.advance[widest] as usize + pixels as usize;
        if spaced > SPACED_ADVANCE_MAX {
            return Err(format!(
                "with {pixels} more pixels {:?} would move the line {spaced}, more than a cell \
                 ({SPACED_ADVANCE_MAX}): the battle checks its victory lines one letter per cell",
                glyph_char(widest)
            ));
        }
        for a in &mut self.advance {
            *a += pixels as u8;
        }
        for g in undrawn {
            self.advance[g] = 0;
        }
        Ok(self)
    }

    /// A font from its sheet: an indexed PNG with the 95 characters in
    /// ASCII order, sixteen per row, each in a cell `w` columns wide and 13
    /// rows tall with a one-pixel grid line between cells and around them.
    /// Six rows of cells; or twelve, and the last six are Latin-1's 96, from
    /// U+00A0 —the cell after the tilde's, DEL's, stays empty—.
    ///
    /// What counts is the **index**, not the colour, so the palette can be
    /// changed to see better: 0 is the background, 1 the glyph, 2 the mark of
    /// the advance and 3 the grid, which is ignored. Rows 0 to 11 of a cell
    /// are the glyph, on RM2k's baseline; row 12 is the advance: as many
    /// marks, stuck to the left, as columns the line moves after the glyph.
    /// The space between letters goes in the advance, not in the glyph. The
    /// shadow is not drawn: whoever draws the line adds it.
    ///
    /// It is the format of the sheets Espinillo drew on 2026-09-30, and their
    /// reader was the Python that drew the mock-ups with them.
    pub fn from_sheet(png_bytes: &[u8]) -> Result<Font, String> {
        let (indices, width, height) = read_indexed(png_bytes)?;
        let cell = (width - 1) / PER_ROW - 1;
        let latin = (width, height) == sheet_size(cell, true);
        if !latin && (width, height) != sheet_size(cell, false) {
            return Err(format!(
                "it is {width}x{height}, and a sheet of {cell}-column cells is {}x{}, or {}x{} with \
                 Latin-1",
                sheet_size(cell, false).0,
                sheet_size(cell, false).1,
                sheet_size(cell, true).0,
                sheet_size(cell, true).1
            ));
        }
        if cell > 16 {
            return Err(format!(
                "its cells are {cell} wide, and a glyph is at most 16"
            ));
        }
        let at = |x: usize, y: usize| indices[y * width + x];
        let mut rows = Vec::with_capacity(GLYPHS + LATIN_GLYPHS);
        let mut advance = Vec::with_capacity(GLYPHS + LATIN_GLYPHS);
        let glyphs = if latin { GLYPHS + LATIN_GLYPHS } else { GLYPHS };
        for g in 0..glyphs {
            let ch = glyph_char(g);
            // The cell: Latin-1's start at the seventh row, past DEL's.
            let i = if g < GLYPHS { g } else { g + 1 };
            let (x0, y0) = (
                1 + (i % PER_ROW) * (cell + 1),
                1 + (i / PER_ROW) * (CELL_ROWS + 1),
            );
            let mut glyph = [0u16; HEIGHT];
            for (y, row) in glyph.iter_mut().enumerate() {
                for x in 0..cell {
                    match at(x0 + x, y0 + y) {
                        BACKGROUND | GRID => {}
                        INK => *row |= 1 << x,
                        v => {
                            return Err(format!(
                                "{ch:?} has index {v} at ({x}, {y}): a glyph takes only \
                                 {BACKGROUND} and {INK}"
                            ))
                        }
                    }
                }
            }
            let marks: Vec<bool> = (0..cell).map(|x| at(x0 + x, y0 + HEIGHT) == MARK).collect();
            let n = marks.iter().filter(|m| **m).count();
            if marks[..n].iter().any(|m| !m) {
                return Err(format!(
                    "the advance mark of {ch:?} is not stuck to the left"
                ));
            }
            rows.push(glyph);
            advance.push(n as u8);
        }
        Ok(Font { rows, advance })
    }

    /// The twelve rows of `ch`'s glyph, or the space's if the font lacks it.
    pub fn rows(&self, ch: char) -> &[u16; HEIGHT] {
        &self.rows[self.index(ch)]
    }

    /// How many columns the line moves after `ch`.
    pub fn advance(&self, ch: char) -> usize {
        if ch == CURSOR_BLANK {
            return self.advance('>');
        }
        if ch == FIGURE_BLANK {
            return self.advance('0');
        }
        self.advance[self.index(ch)] as usize
    }

    /// How many columns `text` moves the line: from where it starts to
    /// where the next letter would.
    pub fn width(&self, text: &str) -> usize {
        text.chars().map(|c| self.advance(c)).sum()
    }

    /// The lit pixels of `ch`'s glyph, `(x, y)`, row by row and left to
    /// right.
    pub fn pixels(&self, ch: char) -> Vec<(usize, usize)> {
        let mut out = Vec::new();
        for (y, row) in self.rows(ch).iter().enumerate() {
            for x in 0..16 {
                if row >> x & 1 != 0 {
                    out.push((x, y));
                }
            }
        }
        out
    }

    /// How many columns the widest glyph's ink spans, from column 0.
    pub fn ink_width(&self) -> usize {
        self.rows
            .iter()
            .flatten()
            .map(|r| 16 - r.leading_zeros() as usize)
            .max()
            .unwrap_or(0)
    }

    /// How many columns `ch` paints from where it starts: its ink and its
    /// shadow, one column further; 0 for a blank. It is the console's
    /// `font_reach`.
    pub fn reach(&self, ch: char) -> usize {
        if ch == CURSOR_BLANK || ch == FIGURE_BLANK {
            return 0;
        }
        let ink = self
            .rows(ch)
            .iter()
            .map(|r| 16 - r.leading_zeros() as usize)
            .max()
            .unwrap_or(0);
        if ink == 0 {
            0
        } else {
            ink + 1
        }
    }

    /// Whether every letter moves the line the same: RM2k's.
    pub fn is_fixed(&self) -> bool {
        self.advance.iter().all(|a| *a == self.advance[0])
    }

    /// The advance of each of the 95 glyphs of ASCII, in order.
    pub fn advances(&self) -> &[u8] {
        &self.advance[..GLYPHS]
    }

    /// The advance of each glyph the console carries, in order: the 95 and
    /// [`CURSOR_BLANK`].
    pub fn console_advances(&self) -> Vec<u8> {
        let mut out = self.advance[..GLYPHS].to_vec();
        out.push(self.advance('>') as u8);
        out
    }

    /// Whether the font draws `ch`: printable ASCII, and the Latin-1 its
    /// sheet carries. A Latin-1 cell without advance marks is one the sheet
    /// does not draw: the engine's leaves out the four wider than ASCII's
    /// widest, `®`, `¾`, `Ø` and `ø`, which `letter_spacing` would push
    /// past a cell.
    pub fn draws(&self, ch: char) -> bool {
        let code = ch as u32;
        if (FIRST..FIRST + GLYPHS as u32).contains(&code) {
            return true;
        }
        let latin = (LATIN_FIRST..LATIN_FIRST + LATIN_GLYPHS as u32).contains(&code);
        latin
            && self
                .advance
                .get(GLYPHS + (code - LATIN_FIRST) as usize)
                .is_some_and(|&a| a > 0)
    }

    /// The Latin-1 letters it draws, with their advances: every one its
    /// sheet carries but the no-break space and the soft hyphen, which a
    /// space and a hyphen stand in for —see [`crate::plain`]—. Empty for a
    /// font without them, RM2k's included.
    pub fn latin_letters(&self) -> Vec<(char, u8)> {
        (GLYPHS..self.advance.len())
            .map(|g| (glyph_char(g), self.advance[g]))
            .filter(|&(c, _)| self.draws(c) && !matches!(c, '\u{a0}' | '\u{ad}'))
            .collect()
    }

    /// The advances a line is measured with, from the space on: the
    /// console's —see [`Font::console_advances`]— up to DEL, nothing for
    /// U+0080 to U+009F, and each Latin-1 letter the font draws —see
    /// [`Font::latin_letters`]—, 0 for one it does not. See
    /// `refit::Measure`.
    pub fn measure_advances(&self) -> Vec<u8> {
        let mut out = self.console_advances();
        out.resize((LATIN_FIRST - FIRST) as usize, 0);
        let mut latin = vec![0u8; LATIN_GLYPHS];
        for (c, a) in self.latin_letters() {
            latin[(c as u32 - LATIN_FIRST) as usize] = a;
        }
        out.extend(latin);
        out
    }

    /// The character the console's glyph `n` is.
    pub fn console_char(n: usize) -> char {
        char::from_u32(FIRST + n as u32).expect("ASCII")
    }
}

/// The character glyph `g` of a font is: ASCII's 95 and then Latin-1's.
fn glyph_char(g: usize) -> char {
    let code = if g < GLYPHS {
        FIRST + g as u32
    } else {
        LATIN_FIRST + (g - GLYPHS) as u32
    };
    char::from_u32(code).expect("ASCII or Latin-1")
}

impl Font {
    /// The glyph `ch` is drawn with: its own, or the space.
    fn index(&self, ch: char) -> usize {
        let code = ch as u32;
        if (FIRST..FIRST + GLYPHS as u32).contains(&code) {
            (code - FIRST) as usize
        } else if self.draws(ch) {
            GLYPHS + (code - LATIN_FIRST) as usize
        } else {
            0
        }
    }
}

// A sheet: its indices and its shape.
const BACKGROUND: u8 = 0;
const INK: u8 = 1;
const MARK: u8 = 2;
const GRID: u8 = 3;
const PER_ROW: usize = 16;
const CELL_ROWS: usize = HEIGHT + 1;

/// A sheet's size in pixels, with Latin-1's six rows of cells or without.
fn sheet_size(cell: usize, latin: bool) -> (usize, usize) {
    let rows = GLYPHS.div_ceil(PER_ROW) + if latin { LATIN_GLYPHS / PER_ROW } else { 0 };
    (PER_ROW * (cell + 1) + 1, rows * (CELL_ROWS + 1) + 1)
}

/// The indices of an indexed PNG, one byte per pixel, and its size.
fn read_indexed(bytes: &[u8]) -> Result<(Vec<u8>, usize, usize), String> {
    let mut decoder = png::Decoder::new(bytes);
    decoder.set_transformations(png::Transformations::IDENTITY);
    let mut reader = decoder
        .read_info()
        .map_err(|e| format!("not a PNG this can read: {e}"))?;
    let mut buffer = vec![0; reader.output_buffer_size()];
    let frame = reader.next_frame(&mut buffer).map_err(|e| e.to_string())?;
    if frame.color_type != png::ColorType::Indexed {
        return Err(format!(
            "it is {:?}, and a sheet is indexed: what counts is the index, not the colour",
            frame.color_type
        ));
    }
    let (width, height) = (frame.width as usize, frame.height as usize);
    let depth = frame.bit_depth as usize;
    let mut out = Vec::with_capacity(width * height);
    for y in 0..height {
        let line = &buffer[y * frame.line_size..(y + 1) * frame.line_size];
        for x in 0..width {
            let bit = x * depth;
            let byte = line[bit / 8];
            let shift = 8 - depth - bit % 8;
            out.push((byte >> shift) & ((1u16 << depth) - 1) as u8);
        }
    }
    Ok((out, width, height))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_character_the_font_lacks_is_a_space() {
        let font = Font::rm2k(MINCHO);
        assert_eq!(font.rows('é'), font.rows(' '));
        assert!(font.pixels(' ').is_empty());
    }

    #[test]
    fn rm2k_s_font_is_the_one_the_game_asks_for() {
        assert_ne!(Font::rm2k(MINCHO).rows('g'), Font::rm2k(GOTHIC).rows('g'));
        assert_eq!(Font::rm2k(7), Font::rm2k(GOTHIC));
        assert_eq!(Font::named(RM2K, MINCHO).unwrap(), Font::rm2k(MINCHO));
        assert!(Font::rm2k(MINCHO).is_fixed());
        assert_eq!(Font::rm2k(MINCHO).width("abc"), 18);
    }

    #[test]
    fn the_engine_s_font_reads_and_fits_the_console() {
        let font = Font::named("low-variable", MINCHO).unwrap();
        assert!(!font.is_fixed());
        assert!(font.ink_width() <= INK_MAX);
        // Every glyph's ink and its shadow fit in its advance, so a line
        // never reaches the cell where the next text starts.
        for i in 0..GLYPHS {
            let ch = char::from_u32(FIRST + i as u32).unwrap();
            let ink = font
                .rows(ch)
                .iter()
                .map(|r| 16 - r.leading_zeros() as usize)
                .max()
                .unwrap();
            assert!(ink == 0 || ink < font.advance(ch), "{ch:?}");
        }
        // The digits are all the same width, so numbers line up.
        let digit = font.advance('0');
        assert!("0123456789".chars().all(|c| font.advance(c) == digit));
    }

    #[test]
    fn spacing_adds_to_every_advance_and_nothing_else() {
        let font = Font::named("low-variable", MINCHO).unwrap();
        assert_eq!(font.clone().with_spacing(0).unwrap(), font);
        let spaced = font.clone().with_spacing(2).unwrap();
        for i in 0..GLYPHS {
            let ch = Font::console_char(i);
            assert_eq!(spaced.advance(ch), font.advance(ch) + 2, "{ch:?}");
            assert_eq!(spaced.rows(ch), font.rows(ch), "{ch:?}");
        }
        assert_eq!(spaced.advance(CURSOR_BLANK), spaced.advance('>'));
        assert_eq!(spaced.advance(FIGURE_BLANK), spaced.advance('0'));
        assert_eq!(spaced.width("ab"), font.width("ab") + 4);
        assert!(Font::rm2k(MINCHO).with_spacing(1).unwrap().is_fixed());
    }

    #[test]
    fn spacing_says_why_it_is_refused() {
        let font = Font::named("low-variable", MINCHO).unwrap();
        let e = font.clone().with_spacing(-1).unwrap_err();
        assert!(e.contains("shadow"), "{e}");
        let e = font.clone().with_spacing(SPACING_MAX + 1).unwrap_err();
        assert!(e.contains("from 0"), "{e}");
        // Its widest letters are six: three more pass a cell.
        let e = font.with_spacing(3).unwrap_err();
        assert!(e.contains("victory"), "{e}");
    }

    /// The engine's sheet carries Latin-1, each letter fitting the console
    /// like the rest; RM2k's does not, and draws none.
    #[test]
    fn the_engine_s_font_draws_latin_1() {
        let font = Font::named("low-variable", MINCHO).unwrap();
        assert!(font.draws('é') && font.draws('ß') && font.draws('¿'));
        assert!(!font.draws('…') && !font.draws('\u{7f}'));
        assert_ne!(font.rows('é'), font.rows('e'));
        // An accent over the body of its own letter.
        assert_eq!(font.rows('é')[3..], font.rows('e')[3..]);
        assert_eq!(font.advance('é'), font.advance('e'));
        assert_eq!(font.latin_letters().len(), LATIN_GLYPHS - 2 - 4);
        assert!(!font.draws('ø'));
        for (c, a) in font.latin_letters() {
            let ink = font
                .rows(c)
                .iter()
                .map(|r| 16 - r.leading_zeros() as usize)
                .max()
                .unwrap();
            assert!(ink == 0 || ink < a as usize, "{c:?}");
        }
        let m = font.measure_advances();
        assert_eq!(m[('é' as u32 - FIRST) as usize] as usize, font.advance('é'));
        assert_eq!(m[(0x85 - FIRST) as usize], 0);
        assert_eq!(font.advances().len(), GLYPHS);
        let rm2k = Font::rm2k(MINCHO);
        assert!(!rm2k.draws('é') && rm2k.latin_letters().is_empty());
    }

    #[test]
    fn a_name_that_is_neither_is_a_path() {
        let e = Font::named("/nowhere/at/all.png", MINCHO).unwrap_err();
        assert!(e.contains("low-variable"), "{e}");
    }
}
