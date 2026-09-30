//! The text boxes: the block of the ROM where they live, and the shape of
//! each one.
//!
//! `OP_MESSAGE` carries an offset within the block and not a text, so the
//! whole cartridge shares one numbering, and a box the game repeats —whole
//! boxes are repeated often— is stored once: the content is the key.

use crate::fail::{Bad, Result, Step, Stop};
use std::collections::{BTreeMap, HashMap};

/// The escape that starts a code, and the two this compiler knows how to
/// run: a pause and "close without waiting".
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
/// **Any other escape still does not compile**, and that is on purpose: the
/// three `\V` of the common events —the value of a variable inserted into
/// the text— require composing the text when opening it, which is something
/// else. Drawing them as two letters would show.
const ESCAPE: char = '\\';
const ESCAPE_PAUSE: char = '|';
const ESCAPE_CLOSE: char = '^';

/// How many pauses fit in the box's header: four bits. The most the game
/// uses is three in a row (`\|\|\|\^`, twice, on map 108); more than fifteen
/// does not fit in the high nibble and the page does not compile instead of
/// lasting too little.
pub const PAUSES_MAX: usize = 15;

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
#[derive(Debug, Clone, Copy)]
pub struct Window {
    pub columns: usize,
    pub lines: usize,
}

/// The lines without their escape tail, how many pauses it has and whether
/// it closes on its own.
///
/// The two escapes are accepted only as a tail at the end of the box's last
/// line, spaces in between included —a space at the end of a line draws
/// nothing—. Any other escape, or one in the middle, does not compile: a
/// pause halfway through a window drawn all at once cannot be modeled.
///
/// Across the 328 maps both escapes appear **always as a tail at the end of
/// the box's last line** —measured: 40 boxes, and not one with an escape in
/// the middle nor on a line other than the last—, so that is the only thing
/// accepted. One in the middle still does not compile, which is the honest
/// thing: with the window drawn all at once, a pause halfway through the
/// text cannot be modeled without making up how much text had been drawn.
///
/// The tail may carry spaces in between —it happens only once, in map 98's
/// `RunDirectorScene`, which writes `\| \| \| \^`— and it eats them: a space
/// at the end of a line does not draw a single pixel, so removing it does
/// not change the screen.
///
/// `rm2k-snes-text` has the same rule, in its `refit.rs`: that copy is the
/// one the boxes are reflowed around for the console's window, before the
/// compiler sees them. `tests/escapes.json` holds the two together.
pub fn escape_tail(lines: &[String]) -> Step<(Vec<String>, usize, bool)> {
    let mut lines: Vec<String> = lines.to_vec();
    let mut pauses = 0;
    let mut auto_close = false;
    if let Some(last) = lines.last() {
        let text: Vec<char> = last.chars().collect();
        let mut i = text.len();
        let mut cut = text.len();
        let mut escapes = 0;
        while i > 0 {
            if i >= 2
                && text[i - 2] == ESCAPE
                && (text[i - 1] == ESCAPE_PAUSE || text[i - 1] == ESCAPE_CLOSE)
            {
                i -= 2;
                cut = i;
                escapes += 1;
            } else if text[i - 1] == ' ' {
                i -= 1;
            } else {
                break;
            }
        }
        if escapes > 0 {
            let tail: String = text[cut..].iter().collect();
            pauses = tail.matches("\\|").count();
            auto_close = tail.contains("\\^");
            let n = lines.len();
            lines[n - 1] = text[..cut].iter().collect();
        }
    }
    if lines.iter().any(|t| t.contains(ESCAPE)) || pauses > PAUSES_MAX {
        return Err(Stop::Cannot);
    }
    Ok((lines, pauses, auto_close))
}

/// A box as the ROM reads it: the header, and each line with its length.
/// The characters go as an index into the font, that is ASCII minus 32; a
/// letter the font does not have stops the conversion. All of the game's
/// text fits there: it was measured, and it does not have a single accented
/// letter.
pub fn message_bytes(
    lines: &[String],
    pauses: usize,
    auto_close: bool,
    window: Window,
) -> Result<Vec<u8>> {
    assert!(pauses <= PAUSES_MAX);
    let mut out = vec![
        lines.len().min(window.lines) as u8
            | if auto_close { HEADER_AUTO_CLOSE } else { 0 }
            | (pauses << 4) as u8,
    ];
    for text in lines.iter().take(window.lines) {
        let text: Vec<char> = text.chars().take(window.columns).collect();
        out.push(text.len() as u8);
        for ch in text {
            let c = ch as u32;
            if !(32..127).contains(&c) {
                return Err(Bad::answer(format!(
                    "the message has a character that is not in the font: {ch:?}"
                )));
            }
            out.push((c - 32) as u8);
        }
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
    where_: HashMap<Key, usize>,
    texts: BTreeMap<usize, Vec<String>>,
}

impl Messages {
    pub fn new(step: usize, window: Window) -> Messages {
        Messages {
            step,
            window,
            data: Vec::new(),
            where_: HashMap::new(),
            texts: BTreeMap::new(),
        }
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
    pub fn add(&mut self, lines: &[String]) -> Step<usize> {
        let (lines, pauses, auto_close) = escape_tail(lines)?;
        let lines: Vec<String> = lines
            .iter()
            .take(self.window.lines)
            .map(|t| t.chars().take(self.window.columns).collect())
            .collect();
        let key = (lines, pauses, auto_close);
        if let Some(&w) = self.where_.get(&key) {
            return Ok(w / self.step);
        }
        while !self.data.len().is_multiple_of(self.step) {
            self.data.push(0);
        }
        let w = self.data.len();
        let bytes = message_bytes(&key.0, pauses, auto_close, self.window).map_err(Stop::Fatal)?;
        self.data.extend(bytes);
        if w / self.step > 0xFFFF {
            return Err(Stop::Fatal(Bad::answer(format!(
                "this ROM's messages are {} bytes and the OP_MESSAGE operand is 16 bits, counting by {} bytes",
                self.data.len(),
                self.step
            ))));
        }
        self.texts.insert(w, key.0.clone());
        self.where_.insert(key, w);
        Ok(w / self.step)
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

    const WINDOW: Window = Window {
        columns: 39,
        lines: 4,
    };

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|t| t.to_string()).collect()
    }

    #[test]
    fn the_tail_comes_off_and_says_how_long_the_box_lasts() {
        let (lines, pauses, close) = escape_tail(&s(&["Hi", "there\\| \\|\\^"])).unwrap();
        assert_eq!((lines, pauses, close), (s(&["Hi", "there"]), 2, true));
        assert!(escape_tail(&s(&["a \\| b"])).is_err());
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
    fn the_tail_comes_off_before_the_line_is_trimmed() {
        // The other way around a full line would eat its own tail, and the
        // box would wait for a key RM2k does not ask for.
        let mut m = Messages::new(1, WINDOW);
        let full = "x".repeat(WINDOW.columns);
        let at = m.add(&[format!("{full}\\|\\^")]).ok().unwrap();
        assert_eq!(m.data[at], 1 | HEADER_AUTO_CLOSE | 1 << 4);
        assert_eq!(m.data[at + 1] as usize, WINDOW.columns);
    }
}
