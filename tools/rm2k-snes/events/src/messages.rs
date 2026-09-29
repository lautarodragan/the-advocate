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
const ESCAPE: char = '\\';
const ESCAPE_PAUSE: char = '|';
const ESCAPE_CLOSE: char = '^';

/// How many pauses fit in the box's header: four bits.
pub const PAUSES_MAX: usize = 15;

/// The header byte of a box: bits 0-2 are how many lines, bit 3 is "it
/// closes on its own" and bits 4-7 how many pauses.
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
/// letter the font does not have stops the conversion.
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
#[derive(Debug, Clone)]
pub struct Messages {
    /// How many bytes at a time the offset in the bytecode counts: each box
    /// starts at a multiple of it. Inside, everything is in bytes.
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
    /// The escape tail comes off **here**, so that every box goes through
    /// the same place; then each line is trimmed to what fits, and only
    /// then deduplicated —two texts that differ only in what gets cut are
    /// the same box on screen—. The key carries the tail: the same text
    /// with another tail lasts another time.
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
