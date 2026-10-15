//! The text boxes: the block of the ROM where they live, and the shape of
//! each one.
//!
//! `OP_MESSAGE` carries an offset within the block and not a text, so the
//! whole cartridge shares one numbering, and a box the game repeats —whole
//! boxes are repeated often— is stored once: the content is the key.

use crate::fail::{Bad, Result, Step, Stop};
use rm2k_snes_text::font::{CONSOLE_GLYPHS, WIDTH};
use rm2k_snes_text::refit::{is_backslash_mark, wait_of, Measure, ESCAPE};
use std::collections::{BTreeMap, HashMap};

/// The first byte value that stands for a pair of letters and not for one.
///
/// A letter goes as its index in the font, ASCII minus 32, and the font has
/// the 95 printable ASCII characters and, after them, the cursor's blank
/// —`CURSOR_BLANK` in `rm2k-snes-text`, DEL—: 0 to 95. Every value from 96
/// up is one the text never uses, so each can mean two letters: that is DTE,
/// dual tile encoding, of a single level —a pair is two letters, never a
/// letter and another pair—. The ROM's composer looks a value from here up
/// in the pair table and draws the two letters one after the other, as if
/// they had come in two bytes. It was 95 until the cursor's blank, on
/// 2026-10-03.
pub const PAIR_FIRST: u8 = 96;

/// The byte that stands for **a variable's value**, `\V[n]`: the next byte
/// is the variable's slot, and the ROM's composer writes its digits there
/// when it opens the box —see `msg_letter` in runtime/message_letter.s—.
///
/// It is the last of the pair range, taken from the pairs, and not a value
/// below `PAIR_FIRST`: those are the font's 96 letters, all of them used. The
/// pair it displaces is the least frequent of the table.
pub const VARIABLE: u8 = 0xFF;

/// The byte that stands for **a wait in the middle of the box**, `\.`,
/// `\|` or `\!`: the next byte says which —see [`WAIT_KEY`]—, and the
/// ROM's composer stops there, shows what it has drawn, waits and goes on
/// —see runtime/message_waits.s—. It is the one before [`VARIABLE`], taken
/// from the pairs like it.
///
/// It counts in the line's length like a letter, and the composer takes it
/// off when it reads it: that way a wait at the end of a line —after its
/// last letter, where nothing would read it— is still inside the line.
pub const WAIT: u8 = 0xFE;

/// What follows [`WAIT`]: the frames, or a key. `\.` is 16 frames and not
/// the quarter of a second the help says, and `\|` 61 and not 60: easyrpg's
/// `Window_Message`, measured on RPG_RT, at the speed the console has
/// —`\s[n]` is dropped—. The frame RPG_RT adds when the line has an odd
/// number of characters is not modeled.
pub const WAIT_KEY: u8 = 0;
pub const WAIT_QUARTER: u8 = 16;
pub const WAIT_SECOND: u8 = 61;

/// And one that is not a wait: it opens the first line of every box that
/// carries one, so the composer knows from its first letter that the box
/// is drawn in stretches —and that the page holds its tail, `\|` and `\^`,
/// until the last one is on screen—.
pub const WAIT_ANNOUNCE: u8 = 0xFF;

/// How many pairs fit: the values from `PAIR_FIRST` up to the one before
/// [`WAIT`].
pub const PAIRS_MAX: usize = WAIT as usize - PAIR_FIRST as usize;

/// How a `\V[n]` travels inside a line between the compiler and this
/// module: one character of Unicode's last private use plane, this plus the
/// slot. No text of a game can carry it —[`units`] stops at anything outside
/// printable ASCII— so it cannot be mistaken for a letter, and as a single
/// character it goes through the escape tail, the trimming and the
/// deduplication key like any other.
const VARIABLE_MARK: u32 = 0xF0000;

/// The mark of a variable's value, with its slot: see [`VARIABLE_MARK`].
pub fn variable_mark(slot: u8) -> char {
    char::from_u32(VARIABLE_MARK + slot as u32).unwrap()
}

/// One unit of a line: a letter, as its index in the font, or a variable's
/// value, as its slot.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Unit {
    Letter(u8),
    Variable(u8),
    /// A wait, as what follows [`WAIT`].
    Wait(u8),
}

/// What follows [`WAIT`] for the wait whose escape letter is `escape`.
fn wait_byte(escape: char) -> u8 {
    match escape {
        '.' => WAIT_QUARTER,
        '|' => WAIT_SECOND,
        _ => WAIT_KEY,
    }
}

/// The pair table of a text block: which two letters each value from
/// `PAIR_FIRST` up stands for.
///
/// **A pair never leaves a line**, and that is what keeps it from splitting
/// anything: a line is only letters —the escapes travel in the box's header,
/// see `HEADER_LINES`, and the length goes in its own byte before the line—,
/// so two neighbouring letters of a line are always two letters. And the
/// length byte keeps counting letters, not bytes: the composer goes letter
/// by letter, at the same pace as without pairs, and a box draws exactly the
/// same.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Pairs {
    table: Vec<(u8, u8)>,
    code: HashMap<(u8, u8), u8>,
}

impl Pairs {
    /// The `PAIRS_MAX` most frequent pairs of neighbouring letters across
    /// `lines`, each line as font indices.
    ///
    /// By plain frequency, ties broken by the pair itself so that the table
    /// does not depend on the order of a `HashMap`. Re-counting after each
    /// choice —the one-level variant of byte pair encoding— was measured
    /// too, on `release`'s block, and came out 144 bytes bigger out of
    /// 94 KB: not worth the loop.
    pub fn choose<'a>(lines: impl IntoIterator<Item = &'a [u8]>) -> Pairs {
        let mut count: HashMap<(u8, u8), usize> = HashMap::new();
        for line in lines {
            for w in line.windows(2) {
                *count.entry((w[0], w[1])).or_default() += 1;
            }
        }
        let mut ranked: Vec<((u8, u8), usize)> = count.into_iter().collect();
        ranked.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        Pairs::from_table(ranked.into_iter().take(PAIRS_MAX).map(|(p, _)| p).collect())
    }

    pub fn from_table(table: Vec<(u8, u8)>) -> Pairs {
        assert!(table.len() <= PAIRS_MAX);
        let code = table
            .iter()
            .enumerate()
            .map(|(i, &p)| (p, PAIR_FIRST + i as u8))
            .collect();
        Pairs { table, code }
    }

    /// One line of letters in as few bytes as the table allows.
    ///
    /// Greedy from the left, and it is not a shortcut: each pair taken saves
    /// one byte, so the fewest bytes is the most pairs that do not overlap,
    /// and along a line that is choosing intervals of two —taking the one
    /// that ends first, which is the one that starts here, is optimal—.
    pub fn encode(&self, letters: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(letters.len());
        let mut i = 0;
        while i < letters.len() {
            match letters
                .get(i + 1)
                .and_then(|&b| self.code.get(&(letters[i], b)))
            {
                Some(&code) => {
                    out.push(code);
                    i += 2;
                }
                None => {
                    out.push(letters[i]);
                    i += 1;
                }
            }
        }
        out
    }

    /// The table as the ROM reads it: two bytes per value from `PAIR_FIRST`
    /// up, the first letter and then the second, so that one 16-bit read
    /// brings both. Never empty: the assembler needs the label resolved even
    /// if the ROM never reads it.
    pub fn bytes(&self) -> Vec<u8> {
        if self.table.is_empty() {
            return vec![0];
        }
        self.table.iter().flat_map(|&(a, b)| [a, b]).collect()
    }

    pub fn len(&self) -> usize {
        self.table.len()
    }

    pub fn is_empty(&self) -> bool {
        self.table.is_empty()
    }
}

/// How many pauses fit in the box's header: four bits. The most the game
/// uses is three in a row (`\|\|\|\^`, twice, on map 108); more than fifteen
/// does not fit in the high nibble and the page does not compile instead of
/// lasting too little. `rm2k-snes-text`'s number, with its escape tail.
pub use rm2k_snes_text::refit::PAUSES_MAX;

/// The header byte of a box: bits 0-2 are how many lines, bit 3 is "it
/// closes on its own" and bits 4-7 how many pauses.
///
/// The escapes go here and not in one more operand of `OP_MESSAGE` because
/// here they come for free: a window's lines are four at most, so the byte
/// that counts them had five unused bits. One more operand would cost one
/// byte for each of the game's 2895 boxes and it would have to be emitted
/// anyway in the 2855 that carry no tail.
///
/// ```text
/// bits 0-2   how many lines it carries, from 0 to 4
/// bit  3     it closes on its own: the `\^`
/// bits 4-7   how many pauses, from 0 to 15: the `\|`s
/// ```
///
/// The order is not arbitrary: the lines go at the bottom because it is what
/// the ROM reads in the compositor's loop —`and #HEADER_LINES` and done— and
/// the pauses at the top because they are read only once, on opening, where
/// an extra `lsr` does not show.
pub const HEADER_LINES: u8 = 0x07;
pub const HEADER_AUTO_CLOSE: u8 = 0x08;

/// The size of the console's message window, which the request brings: the
/// runtime draws it, and the converter is where its size is written.
///
/// A line is measured **in pixels**, with the advance of each glyph of the
/// font the console draws it with: `advances`, from the space on, the
/// cursor's blank last. Until 2026-10-03 it was `columns` letters, every one
/// six pixels wide; [`Window::columns`] is still that.
#[derive(Debug, Clone, Copy)]
pub struct Window {
    pub width: usize,
    pub lines: usize,
    pub advances: [u8; CONSOLE_GLYPHS],
}

impl Window {
    /// A window of `columns` letters of RM2k's fixed six-pixel font.
    pub const fn columns(columns: usize, lines: usize) -> Window {
        Window {
            width: columns * WIDTH,
            lines,
            advances: [WIDTH as u8; CONSOLE_GLYPHS],
        }
    }

    /// What `c` moves the line. A variable's value counts as **one digit**:
    /// how many it takes is known only when the box opens, and the ROM cuts
    /// at the edge what grows past it. A character the font does not have
    /// is a space, and [`units`] stops the conversion on it anyway.
    pub fn advance(&self, c: char) -> usize {
        if wait_of(c).is_some() {
            return 0; // a wait draws nothing
        }
        let c = if is_backslash_mark(c) { ESCAPE } else { c };
        let code = c as u32;
        if (VARIABLE_MARK..VARIABLE_MARK + 0x100).contains(&code) {
            return self.advances[('0' as usize) - 32] as usize;
        }
        match code.checked_sub(32) {
            Some(i) if (i as usize) < CONSOLE_GLYPHS => self.advances[i as usize] as usize,
            _ => self.advances[0] as usize,
        }
    }

    /// How the reflow measures a line of this window.
    pub fn measure(&self) -> Measure {
        Measure::from_advances(self.advances.to_vec(), self.width)
    }

    /// The longest start of `text` that fits in a line.
    pub fn fit(&self, text: &str) -> String {
        let mut used = 0;
        text.chars()
            .take_while(|&c| {
                used += self.advance(c);
                used <= self.width
            })
            .collect()
    }
}

/// The lines without their escape tail, how many pauses it has and whether
/// it closes on its own.
///
/// The two escapes are accepted only as a tail at the end of the box's last
/// line, spaces in between included —a space at the end of a line draws
/// nothing—. `\.`, `\!` and `\|` in the middle are waits, and come out as
/// marks in the lines —see [`WAIT`]—; any other escape does not compile.
///
/// Across ABL's 328 maps both escapes appear **always as a tail at the end
/// of the box's last line** —measured: 40 boxes, and not one with an escape
/// in the middle nor on a line other than the last—. Other games do put
/// them in the middle, and since 2026-10-12 the ROM stops there: until then
/// the window was drawn all at once and they were dropped.
///
/// The tail may carry spaces in between —it happens only once, in map 98's
/// `RunDirectorScene`, which writes `\| \| \| \^`— and it eats them: a space
/// at the end of a line does not draw a single pixel, so removing it does
/// not change the screen.
///
/// The escape codes the game's text uses: `\|` is a pause and `\^` closes
/// the box without waiting for the player to press anything. Both are time
/// and not text, and since 2026-09-13 both are done: they travel in the
/// box's header —see `HEADER_LINES`— and the ROM's interpreter reads them
/// from there.
///
/// They are done for real and not by quietly deleting them, which was the
/// cheap temptation: with `\^` the box closes on its own, so the ROM would
/// be left waiting for an A that RM2k never asked for and the whole page
/// would last as long as the player takes.
///
/// **Any other escape still does not compile**, and that is on purpose:
/// drawing one as its letters would show. `\V[n]`, the value of a variable,
/// is the exception, and it does not come through here: the compiler turns
/// it into a mark before —see [`VARIABLE`]— and the ROM writes the digits
/// when the box opens.
///
/// **The rule is `rm2k-snes-text`'s**, `refit::escape_tail`, with its
/// cases: the boxes are reflowed around it for the console's window before
/// the compiler sees them, and the compiler cuts the tail off with the same
/// one. What it cannot compile stops the page.
pub fn escape_tail(lines: &[String]) -> Step<(Vec<String>, usize, bool)> {
    rm2k_snes_text::refit::escape_tail(lines).map_err(|_| Stop::Cannot)
}

/// The units of what fits of a line: each letter as its font index, that is
/// ASCII minus 32 —the cursor's blank, DEL, is 95—, and each variable mark
/// as its slot; a letter the font does not have is an error. `Messages::add`
/// asks first, and stops the page that shows one: A Blurred Line does not
/// have a single accented letter, but a game in French or German does.
fn units(text: &str, window: Window) -> Result<Vec<Unit>> {
    window
        .fit(text)
        .chars()
        .map(|ch| {
            let ch = if is_backslash_mark(ch) { ESCAPE } else { ch };
            let c = ch as u32;
            if let Some(w) = wait_of(ch) {
                return Ok(Unit::Wait(wait_byte(w)));
            }
            if (VARIABLE_MARK..VARIABLE_MARK + 0x100).contains(&c) {
                return Ok(Unit::Variable((c - VARIABLE_MARK) as u8));
            }
            if !(32..32 + CONSOLE_GLYPHS as u32).contains(&c) {
                return Err(Bad::answer(format!(
                    "the message has a character that is not in the font: {ch:?}"
                )));
            }
            Ok(Unit::Letter((c - 32) as u8))
        })
        .collect()
}

/// The runs of letters of a line, cut at each variable and each wait: a
/// pair never takes a letter from each side of one, because between them
/// the ROM writes digits, or stops.
fn letter_runs(units: &[Unit]) -> Vec<Vec<u8>> {
    let mut runs = vec![vec![]];
    for u in units {
        match *u {
            Unit::Letter(l) => runs.last_mut().unwrap().push(l),
            Unit::Variable(_) | Unit::Wait(_) => runs.push(vec![]),
        }
    }
    runs.retain(|r| !r.is_empty());
    runs
}

/// A box as the ROM reads it: the header, and each line with its length
/// **in letters** and then its letters through the pair table —see
/// `Pairs`—. With an empty table each letter is its byte, as it was before
/// there were pairs.
///
/// A variable's value is [`VARIABLE`] and its slot, and counts as **one**
/// letter in the length: how many digits it takes is known only when the
/// box opens, and the ROM adds the rest to the line's length there. A line
/// that grows past the window is cut by the composer at the edge.
///
/// A wait is [`WAIT`] and which one, and counts as one letter too, which the
/// ROM takes off when it reads it. A box that carries one opens with
/// [`WAIT_ANNOUNCE`], on its first line.
pub fn message_bytes(
    lines: &[String],
    pauses: usize,
    auto_close: bool,
    window: Window,
    pairs: &Pairs,
) -> Result<Vec<u8>> {
    assert!(pauses <= PAUSES_MAX);
    let mut out = vec![
        lines.len().min(window.lines) as u8
            | if auto_close { HEADER_AUTO_CLOSE } else { 0 }
            | (pauses << 4) as u8,
    ];
    let mut boxed = lines
        .iter()
        .take(window.lines)
        .map(|t| units(t, window))
        .collect::<Result<Vec<_>>>()?;
    if boxed.iter().flatten().any(|u| matches!(u, Unit::Wait(_))) {
        boxed[0].insert(0, Unit::Wait(WAIT_ANNOUNCE));
    }
    for text in boxed {
        out.push(text.len() as u8);
        let mut run = Vec::new();
        for u in text {
            match u {
                Unit::Letter(l) => run.push(l),
                Unit::Variable(slot) => {
                    out.extend(pairs.encode(&run));
                    run.clear();
                    out.extend([VARIABLE, slot]);
                }
                Unit::Wait(which) => {
                    out.extend(pairs.encode(&run));
                    run.clear();
                    out.extend([WAIT, which]);
                }
            }
        }
        out.extend(pairs.encode(&run));
    }
    Ok(out)
}

type Key = (Vec<String>, usize, bool);

/// The ROM's text block, and the offset of each box.
///
/// It belongs to the whole ROM and not to the map: `OP_MESSAGE` carries an
/// offset within this block, so all maps share the numbering and the
/// converter emits it only once. What is repeated is stored only once —the
/// game repeats whole boxes, 418 of 2895— and it comes for free because the
/// content already is the key.
#[derive(Debug, Clone)]
pub struct Messages {
    /// How many bytes at a time the offset in the bytecode counts: each box
    /// starts at a multiple of it. Inside, everything is in bytes: the step
    /// is applied going in and going out.
    ///
    /// The game's block goes by four —`MESSAGES_STEP` in the converter's
    /// events.py, which has the why—, so the block can be 256 KB with a
    /// 16-bit operand; the others, like the troops', by one.
    pub step: usize,
    pub window: Window,
    pub data: Vec<u8>,
    /// The pairs its letters are written with; empty, one byte per letter.
    pub pairs: Pairs,
    /// Whether a block past what the operand reaches stops the compilation.
    /// Only `measuring` turns it off: see there.
    capped: bool,
    where_: HashMap<Key, usize>,
    texts: BTreeMap<usize, Vec<String>>,
}

impl Messages {
    pub fn new(step: usize, window: Window) -> Messages {
        Messages {
            step,
            window,
            data: Vec::new(),
            pairs: Pairs::default(),
            capped: true,
            where_: HashMap::new(),
            texts: BTreeMap::new(),
        }
    }

    /// One that writes its letters with `pairs`.
    pub fn with_pairs(step: usize, window: Window, pairs: Pairs) -> Messages {
        Messages {
            pairs,
            ..Messages::new(step, window)
        }
    }

    /// One that only gathers the texts so that the pairs can be chosen over
    /// them —see `choose_pairs`—, without the cap of the operand: without
    /// pairs the block can pass the 256 KB that it will not pass with them,
    /// and stopping there would stop the cartridge for a block that is never
    /// emitted.
    pub fn measuring(step: usize, window: Window) -> Messages {
        Messages {
            capped: false,
            ..Messages::new(step, window)
        }
    }

    /// The pair table for the boxes it holds: the ones left after every
    /// `rewind`, which are the ones that go into the cartridge.
    pub fn choose_pairs(&self) -> Result<Pairs> {
        let mut runs = Vec::new();
        for t in self.texts.values().flatten() {
            runs.extend(letter_runs(&units(t, self.window)?));
        }
        Ok(Pairs::choose(runs.iter().map(|l| l.as_slice())))
    }

    /// The offset of this box, storing it the first time.
    ///
    /// The escape tail comes off **here** —see `escape_tail`— and not in the
    /// compiler, so that everyone who builds a box goes through the same
    /// place: the game's `ShowMessage`s and those of the test pages —which
    /// is how this is tested: `autocierre` in the suite— and a
    /// `ShowChoice`'s options.
    ///
    /// Trimming to what fits in a line is done after the tail and before
    /// deduplicating: two texts that differ only in what gets cut are the
    /// same box on screen, and giving them two different offsets would emit
    /// the same bytes twice. The other way around —trimming first— a
    /// 39-character line would eat its own `\|\^` and the box would be left
    /// waiting for an A that RM2k does not ask for.
    ///
    /// **The deduplication key carries the tail**, and it is not a detail:
    /// two boxes with the same text and different tails are two different
    /// boxes —one waits for the player and the other does not— and sharing
    /// an offset would make them last the same.
    ///
    /// **The waits in the middle are dropped here**, without waiting: this
    /// is the box of a choice, an inn, a number or a troop page, which the
    /// ROM draws without stopping. A `ShowMessage` goes through
    /// [`Messages::add_waiting`].
    pub fn add(&mut self, lines: &[String]) -> Step<usize> {
        let (lines, pauses, auto_close) = escape_tail(lines)?;
        let lines: Vec<String> = lines
            .iter()
            .map(|t| t.chars().filter(|&c| wait_of(c).is_none()).collect())
            .collect();
        self.store(lines, pauses, auto_close)
    }

    /// The same as [`Messages::add`], but the box **keeps its waits** in the
    /// middle —`\.`, `\|`, `\!`—, and the ROM stops at each one: the
    /// `ShowMessage`'s, which is the only window that does it in RM2k too.
    /// What is not a `ShowMessage` does not go through here: a choice's or
    /// a number's box is composed with another opcode watching it, and the
    /// troops' is drawn by the battle, which does not know how to stop.
    pub fn add_waiting(&mut self, lines: &[String]) -> Step<usize> {
        let (lines, pauses, auto_close) = escape_tail(lines)?;
        self.store(lines, pauses, auto_close)
    }

    fn store(&mut self, lines: Vec<String>, pauses: usize, auto_close: bool) -> Step<usize> {
        let lines: Vec<String> = lines
            .iter()
            .take(self.window.lines)
            .map(|t| self.window.fit(t))
            .collect();
        // A letter the console's font does not have stops this page and not
        // the game: RM2k's font has Latin-1 and the console's only ASCII.
        if lines.iter().any(|t| units(t, self.window).is_err()) {
            return Err(Stop::Cannot);
        }
        let key = (lines, pauses, auto_close);
        if let Some(&w) = self.where_.get(&key) {
            return Ok(self.operand(w));
        }
        while !self.data.len().is_multiple_of(self.step) {
            self.data.push(0);
        }
        let w = self.data.len();
        let bytes = message_bytes(&key.0, pauses, auto_close, self.window, &self.pairs)
            .map_err(Stop::Fatal)?;
        self.data.extend(bytes);
        if self.capped && w / self.step > 0xFFFF {
            return Err(Stop::Fatal(Bad::answer(format!(
                "this ROM's messages are {} bytes and the OP_MESSAGE operand is 16 bits, counting by {} bytes",
                self.data.len(),
                self.step
            ))));
        }
        self.texts.insert(w, key.0.clone());
        self.where_.insert(key, w);
        Ok(self.operand(w))
    }

    /// The offset as the bytecode carries it. Past the cap it only happens
    /// while `measuring`, and there it wraps to 16 bits on purpose: that
    /// pass's bytecode is thrown away —only its texts are kept—, but the
    /// compiler still writes each offset in a word, and a value that does not
    /// fit would make every box past 256 KB "not compile", stopping a common
    /// event the plan said compiles. The word's length is all that pass
    /// needs, and wrapping keeps it.
    fn operand(&self, w: usize) -> usize {
        let at = w / self.step;
        if self.capped {
            at
        } else {
            at & 0xFFFF
        }
    }

    pub fn mark(&self) -> usize {
        self.data.len()
    }

    /// Undoes what was added since `mark`: a page that is cut at its last
    /// command leaves none of its texts behind.
    ///
    /// It is needed because a page is compiled command by command and can be
    /// cut at the last one: without this, the text of all the pages that
    /// **do not** compile would stay in the cartridge anyway. It is not a
    /// micro-optimization, it is the whole game's 161 KB against the few
    /// that are needed.
    pub fn rewind(&mut self, mark: usize) {
        self.data.truncate(mark);
        self.where_.retain(|_, v| *v < mark);
        self.texts.retain(|k, _| *k < mark);
    }

    /// How many distinct boxes it holds.
    pub fn count(&self) -> usize {
        self.texts.len()
    }

    /// The block, never empty: the assembler needs the label resolved even
    /// if the ROM never reads it.
    pub fn bytes(&self) -> Vec<u8> {
        if self.data.is_empty() {
            vec![0]
        } else {
            self.data.clone()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const WINDOW: Window = Window::columns(39, 4);

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|t| t.to_string()).collect()
    }

    #[test]
    fn the_tail_comes_off_and_says_how_long_the_box_lasts() {
        let (lines, pauses, close) = escape_tail(&s(&["Hi", "there\\| \\|\\^"])).unwrap();
        assert_eq!((lines, pauses, close), (s(&["Hi", "there"]), 2, true));
        let middle = format!("a {} b", rm2k_snes_text::refit::wait_mark('|'));
        assert_eq!(escape_tail(&s(&["a \\| b"])).unwrap().0, vec![middle]);
        assert!(escape_tail(&s(&["\\V[1]"])).is_err());
    }

    #[test]
    fn a_box_is_stored_once_and_rewinding_forgets_it() {
        let mut m = Messages::new(4, WINDOW);
        assert_eq!(m.add(&s(&["A"])).ok(), Some(0));
        let mark = m.mark();
        assert_eq!(m.add(&s(&["BB"])).ok(), Some(1));
        assert_eq!(m.add(&s(&["A"])).ok(), Some(0));
        m.rewind(mark);
        assert_eq!(m.count(), 1);
        assert_eq!(m.add(&s(&["C"])).ok(), Some(1));
        assert_eq!(m.bytes(), [1, 1, 33, 0, 1, 1, 35]);
    }
    /// A letter the console's font does not have —RM2k's has Latin-1, and
    /// the games in French or German use it— stops the page that shows it,
    /// and not the whole game: it is one more thing a page cannot compile.
    #[test]
    fn a_letter_the_font_does_not_have_stops_the_page() {
        let mut m = Messages::new(1, WINDOW);
        assert!(matches!(m.add(&s(&["Côte"])), Err(Stop::Cannot)));
        assert_eq!(m.count(), 0);
        assert_eq!(m.add(&s(&["Cote"])).ok(), Some(0));
    }

    #[test]
    fn two_boxes_with_the_same_text_and_another_tail_are_two() {
        // One waits for the player and the other does not.
        let mut m = Messages::new(1, WINDOW);
        let bare = m.add(&s(&["Ready?"])).ok().unwrap();
        let tailed = m.add(&s(&["Ready?\\|\\^"])).ok().unwrap();
        assert_ne!(bare, tailed);
        assert_eq!(m.data[bare], 1);
        assert_eq!(m.data[tailed], 1 | HEADER_AUTO_CLOSE | 1 << 4);
        assert_eq!(m.add(&s(&["Ready?\\|\\^"])).ok(), Some(tailed));
    }

    #[test]
    fn a_pair_is_one_byte_and_the_length_still_counts_letters() {
        // "e " and " t" are the two pairs; "the tee" is t, h, `e `, t, e, e:
        // the greedy split takes `e ` and so cannot take ` t`.
        let pairs = Pairs::from_table(vec![(69, 0), (0, 84)]);
        let mut m = Messages::with_pairs(1, WINDOW, pairs.clone());
        let at = m.add(&s(&["the tee"])).ok().unwrap();
        assert_eq!(m.data[at..], [1, 7, 84, 72, PAIR_FIRST, 84, 69, 69]);
        assert_eq!(pairs.bytes(), [69, 0, 0, 84]);
        // A line never borrows a letter from the next one.
        let at = m.add(&s(&["e", " t"])).ok().unwrap();
        assert_eq!(m.data[at..], [2, 1, 69, 2, PAIR_FIRST + 1]);
    }

    #[test]
    fn the_pairs_are_chosen_by_how_often_and_then_by_the_pair() {
        let mut m = Messages::measuring(4, WINDOW);
        m.add(&s(&["abab", "ba"])).ok().unwrap();
        let mark = m.mark();
        // One that is taken back does not count.
        m.add(&s(&["zzzzzzzz"])).ok().unwrap();
        m.rewind(mark);
        let pairs = m.choose_pairs().unwrap();
        // ab twice, ba twice: the tie goes to the smaller pair.
        assert_eq!(pairs.bytes(), [65, 66, 66, 65]);
        assert_eq!(pairs.len(), 2);
        let many = Messages::measuring(1, WINDOW);
        assert!(many.choose_pairs().unwrap().is_empty());
    }

    #[test]
    fn a_pair_never_takes_a_letter_from_each_side_of_a_variable() {
        // "ab" twice in a row, and the variable between the b and the a: the
        // pair "ba" is not there to count, and the line goes out as a pair,
        // the variable, and the pair again.
        let line = format!("ab{}ab", variable_mark(3));
        let mut m = Messages::measuring(1, WINDOW);
        m.add(&[line.clone()]).ok().unwrap();
        let pairs = m.choose_pairs().unwrap();
        assert_eq!(pairs.bytes(), [65, 66]);
        let mut m = Messages::with_pairs(1, WINDOW, pairs);
        let at = m.add(&[line]).ok().unwrap();
        assert_eq!(m.data[at..], [1, 5, PAIR_FIRST, VARIABLE, 3, PAIR_FIRST]);
        // Two fewer than when the font had 95 letters and there were no
        // waits: the 96th letter is the cursor's blank, and `WAIT` took the
        // value before `VARIABLE`.
        assert_eq!(PAIRS_MAX, 158);
    }

    #[test]
    fn a_wait_in_the_middle_is_a_byte_and_its_kind_and_counts_in_the_length() {
        let pairs = Pairs::from_table(vec![(65, 66)]);
        let mut m = Messages::with_pairs(1, WINDOW, pairs);
        // "ab\.ab" and a second line that ends in a key: the box opens
        // announcing it, the pair does not cross the wait, and each wait is
        // one more in its line's length.
        let at = m.add_waiting(&s(&["ab\\.ab", "c\\!"])).ok().unwrap();
        assert_eq!(
            m.data[at..],
            [2, 6, WAIT, WAIT_ANNOUNCE, PAIR_FIRST, WAIT, WAIT_QUARTER, PAIR_FIRST, 2, 67, WAIT, WAIT_KEY]
        );
        let second = m.add_waiting(&s(&["x\\|y\\|\\^"])).ok().unwrap();
        assert_eq!(
            m.data[second..],
            [1 | HEADER_AUTO_CLOSE | 1 << 4, 4, WAIT, WAIT_ANNOUNCE, 88, WAIT, WAIT_SECOND, 89]
        );
        // Without waiting, the same box is the one without them.
        let plain = m.add(&s(&["ab\\.ab", "c\\!"])).ok().unwrap();
        assert_eq!(m.data[plain..], [2, 4, PAIR_FIRST, PAIR_FIRST, 1, 67]);
        assert_eq!(m.add(&s(&["abab", "c"])).ok(), Some(plain));
    }

    #[test]
    fn a_wait_takes_no_room_in_the_line() {
        let full = "x".repeat(39);
        let mut m = Messages::new(1, WINDOW);
        let at = m.add_waiting(&[format!("{full}\\!")]).ok().unwrap();
        assert_eq!(m.data[at + 1] as usize, 39 + 2);
        assert_eq!(m.data[at + 1 + 2 + 1 + 39..], [WAIT, WAIT_KEY]);
    }

    #[test]
    fn measuring_does_not_stop_at_the_operand() {
        let mut m = Messages::measuring(1, WINDOW);
        for k in 0..2000 {
            let line = format!("{k:>39}");
            assert!(m.add(&s(&[&line, &line])).is_ok());
        }
        assert!(m.mark() > 0x10000);
        let mut capped = Messages::new(1, WINDOW);
        let stopped = (0..2000).any(|k| {
            let line = format!("{k:>39}");
            matches!(capped.add(&s(&[&line, &line])), Err(Stop::Fatal(_)))
        });
        assert!(stopped);
    }

    #[test]
    fn the_tail_comes_off_before_the_line_is_trimmed() {
        // The other way around a full line would eat its own tail, and the
        // box would wait for a key RM2k does not ask for.
        let mut m = Messages::new(1, WINDOW);
        let full = "x".repeat(39);
        let at = m.add(&[format!("{full}\\|\\^")]).ok().unwrap();
        assert_eq!(m.data[at], 1 | HEADER_AUTO_CLOSE | 1 << 4);
        assert_eq!(m.data[at + 1] as usize, 39);
    }
}
