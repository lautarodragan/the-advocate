//! Text boxes reflowed for a narrower window.
//!
//! RM2k has no auto-wrap: every break in a `ShowMessage` was put there by
//! hand by the author, thinking of a 320 px window. A narrower one —so
//! many characters per line, so many lines— truncates whatever does not
//! fit, unless the box is reflowed.
//!
//! [`refit`] takes the lines of **one** box and returns one or more boxes
//! that fit. It is a pure function: the same box always gives the same
//! result, which is what allows applying it on every build instead of
//! storing its output.
//!
//! **A line is measured in pixels, with the font's advances** —see
//! [`Measure`]—: with a variable-width font "how many letters fit" has no
//! answer, and a line of narrow letters takes more of them than one of wide
//! ones. The costs below were tuned counting letters of RM2k's fixed font,
//! so the lengths among them are in **letters as wide as the `n`**: a
//! font's `n` is what one of them is worth in pixels. With RM2k's font,
//! every letter as wide as the `n`, it all comes out exactly as when the
//! reflow counted characters, to the last bit of each cost: the pixels are
//! the letters times six, and the divisions that compare them are exact.
//!
//! The rules, and where each one comes from:
//!
//! * **A box that fits is returned as is**, with its breaks and its
//!   spaces. Most fit, and that way they keep everything the author
//!   decided.
//! * **The speaker's line is not touched** —`KERSH`, `MANTA`, `?????`— and
//!   the body has one line less.
//! * **An original break is a good place to cut, not a mandatory one.**
//!   Treating it as mandatory left a word alone on a line ("it still /
//!   is.") and made more boxes not fit.
//! * **A line that splits a sentence goes full**; one with whole sentences
//!   may be short. What reads badly is a line that stops long before the
//!   edge —"Remember," alone, and the rest below—, and that happens when
//!   cutting at a period comes out cheaper than filling.
//! * **What does not fit in one box is split into several**, cutting
//!   between sentences when possible, and **each one repeats the speaker's
//!   line.** It is what games do with consecutive boxes of the same
//!   character.
//! * **The escape tail** —`\|` and `\^`, see [`escape_tail`]— goes at the
//!   end of the last box, which is where the player saw it.
//!
//! What is lost in a reflowed box are the extra spaces between words: the
//! words are joined again with one. In one that fits, nothing is lost.
//!
//! The costs are floating point, and they are added up in the order the
//! reflow this replaces added them: two layouts that tie or nearly tie are
//! decided by those sums, and the boxes have to be those.

use crate::font::Font;
use std::collections::BTreeMap;

// The costs. They are taste and not a measurement: with other values the
// same box comes out differently. They were tried on A Blurred Line's
// introduction and first city, and tuned on what was played of it,
// comparing against the previous version on every box of the game.
//
// Cutting a line after a word:
const COST_SENTENCE_END: i64 = 0;
const COST_PAUSE: i64 = 15;
const COST_ANYWHERE: i64 = 40;
/// Where the author cut.
const DISCOUNT_ORIGINAL_BREAK: i64 = 10;
/// A lone word on the last line.
const COST_ORPHAN: i64 = 200;
/// Between a proper name and its number —"Sector / 33."—. It is almost
/// forbidden: it costs more than an extra box.
const COST_BEFORE_NUMBER: i64 = 1000;

// The gap a line that is not the last one leaves. How much it weighs
// depends on where it cuts, and that is the rule that most changes what is
// seen: **a line that splits a sentence has to go full.** One with whole
// sentences may be short —"Time is running out." / "There's no turning
// back."—, because it reads as a break the author intended. With a single
// weight for all, cutting at an end of sentence was so cheap against the
// gap that the reflow left "Remember," or "Well," alone on a line so that
// the ones below would end in a period.
/// Whole sentences: the gap squared, over this.
const WEIGHT_GAP: f64 = 20.0;
/// Cuts at a comma: squared, over this.
const WEIGHT_GAP_PAUSE: f64 = 8.0;
/// Splits a sentence: cubed, relative to the width, times this.
const WEIGHT_GAP_SPLIT: f64 = 1000.0;

/// The piece of sentence left on the other side of a cut —"sure." at the
/// start of a line, "There" at the end—, if it is shorter than this. It is
/// the generalized orphan: "in time?" alone below looks as cut off as
/// "Well," above.
const TAIL_MIN: i64 = 16;
/// What it is short of, squared, over this.
const WEIGHT_TAIL: f64 = 3.0;

/// An extra box is an extra key press for the player. If the nicest layout
/// does not fit in one box but there is one that fits and costs at most
/// this much more, the one that fits wins.
const COST_EXTRA_BOX: f64 = 300.0;

/// RM2k's text escape, and the two that may end a box: a pause, and
/// closing on its own.
pub const ESCAPE: char = '\\';
pub const ESCAPE_PAUSE: char = '|';
pub const ESCAPE_CLOSE: char = '^';
/// How many pauses a box's tail may carry.
pub const PAUSES_MAX: usize = 15;

/// A box a console cannot show: it is left as it is. Since 2026-10-15 only
/// a tail of more pauses than [`PAUSES_MAX`] is one; an escape no longer is.
#[derive(Debug, PartialEq, Eq)]
pub struct CannotCompile;

/// A box without its escape tail: what [`escape_tail`] answers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Untailed {
    /// The lines, with the waits in the middle, the colour, the speed and
    /// the instant text as [`Control`] marks, a `\\` as [`backslash_mark`]
    /// and without the escapes in [`Untailed::dropped`].
    pub lines: Vec<String>,
    /// How many `\|` the tail carries.
    pub pauses: usize,
    /// Whether the box closes on its own: a `\^` in the tail, or anywhere.
    pub auto_close: bool,
    /// Each escape the console cannot show, as written —`\$`, `\_`—,
    /// in the order of the box: they are not in `lines`, and whoever
    /// compiles the box says it lost them.
    pub dropped: Vec<String>,
}

/// The lines without their escape tail, how many pauses it has, whether it
/// closes on its own, and the escapes it drops.
///
/// Both tail escapes are taken **as a tail at the end of the box's last
/// line**, which is where a game puts them; the tail may carry spaces in
/// between, and it eats them. `\\.`, `\\!` and `\\|` anywhere else are waits
/// in the middle of the box, and come out as one [`wait_mark`] each; the
/// colour, the speed and the instant text are [`Control`] marks too; a `\\^`
/// anywhere else closes the box on its own all the same, since RPG_RT closes
/// it at the end of the box and not where the `\\^` is (easyrpg's
/// `Window_Message`, `kill_page`).
///
/// **Any other escape is dropped**, with its argument if it takes one, and
/// listed in [`Untailed::dropped`]: the box compiles without it, and the
/// event compiler notes each one as a loss, so it is played without the
/// gold window or the half space and the build says so. taro's, from
/// 2026-10-15: a game is played before each escape is done. Until that day
/// any escape but the tail, the waits, `\c[n]` and `\s[n]` left the page
/// out; until 2026-10-20 the colour, the speed and the instant text were
/// dropped too. Which ones and what each one loses is in `with_wait_marks`.
/// More pauses than [`PAUSES_MAX`] is still [`CannotCompile`].
///
/// It is the only copy: the reflow works around it before the event
/// compiler sees the boxes, and the compiler, `rm2k-snes-events`, cuts the
/// tail off with it when it compiles the box. Its cases are
/// `tests/escapes.json`.
pub fn escape_tail(lines: &[String]) -> Result<Untailed, CannotCompile> {
    let mut lines = lines.to_vec();
    let mut pauses = 0;
    let mut auto_close = false;
    if let Some(last) = lines.last() {
        let text: Vec<char> = last.chars().collect();
        let cut = tail_start(last);
        let tail = &text[cut..];
        pauses = tail
            .windows(2)
            .filter(|w| w[0] == ESCAPE && w[1] == ESCAPE_PAUSE)
            .count();
        auto_close = tail
            .windows(2)
            .any(|w| w[0] == ESCAPE && w[1] == ESCAPE_CLOSE);
        let n = lines.len();
        lines[n - 1] = text[..cut].iter().collect();
    }
    let mut dropped = Vec::new();
    for line in lines.iter_mut() {
        let (marked, closes) = with_wait_marks(line, &mut dropped);
        *line = marked;
        auto_close |= closes;
    }
    if pauses > PAUSES_MAX {
        return Err(CannotCompile);
    }
    Ok(Untailed {
        lines,
        pauses,
        auto_close,
        dropped,
    })
}

/// Where the escape tail of a box's last line starts, in characters: the
/// `\|`s and `\^`s at its end, with the spaces between them; the line's
/// length if it ends in neither.
fn tail_start(last: &str) -> usize {
    let text: Vec<char> = last.chars().collect();
    let mut i = text.len();
    let mut cut = text.len();
    while i > 0 {
        if i >= 2 && text[i - 2] == ESCAPE && matches!(text[i - 1], ESCAPE_PAUSE | ESCAPE_CLOSE) {
            i -= 2;
            cut = i;
        } else if text[i - 1] == ' ' {
            i -= 1;
        } else {
            break;
        }
    }
    cut
}

/// The waits RM2k's message window knows in the middle of a box, by the
/// letter of their escape: `\.` a quarter of a second, `\|` a second and
/// `\!` a key. As a [`wait_mark`] each is a single character, so the reflow
/// and the event compiler carry it inside a line like a letter that takes
/// no room.
pub const WAITS: [char; 3] = ['.', '|', '!'];

/// Where the wait marks start: Unicode's last private use plane, past the
/// marks of a variable's value —`VARIABLE_MARK` in `rm2k-snes-events`,
/// `0xF0000` plus a byte—. No text of a game can carry one: the compiler
/// stops at anything that is not printable ASCII.
const WAIT_MARK: u32 = 0xF0100;

/// The mark of a literal backslash, RM2k's `\\`: the character right after the
/// waits'. It is a mark and not a plain backslash so that [`escape_tail`],
/// which refuses any backslash left in a line, and the reflow, which parses
/// escapes, never take it for the start of one. It draws the font's `\`
/// glyph and moves the line by its advance.
const BACKSLASH_MARK: u32 = WAIT_MARK + WAITS.len() as u32;

/// The mark of a literal backslash.
pub fn backslash_mark() -> char {
    char::from_u32(BACKSLASH_MARK).unwrap()
}

/// Whether `c` is [`backslash_mark`].
pub fn is_backslash_mark(c: char) -> bool {
    c as u32 == BACKSLASH_MARK
}

/// The mark of the wait whose escape letter is `escape`, one of [`WAITS`].
pub fn wait_mark(escape: char) -> char {
    let i = WAITS
        .iter()
        .position(|&w| w == escape)
        .expect("a wait's escape");
    char::from_u32(WAIT_MARK + i as u32).unwrap()
}

/// The escape letter of a wait mark, or `None` if `c` is not one.
pub fn wait_of(c: char) -> Option<char> {
    let i = (c as u32).checked_sub(WAIT_MARK)? as usize;
    WAITS.get(i).copied()
}

/// How many text colours a System has: RPG_RT's `\c[n]` takes 0 to 19, and
/// one past that is colour 0 (easyrpg's `Window_Message::UpdateMessage`).
pub const COLOURS: u8 = 20;

/// The speeds `\s[n]` takes, clamped as RPG_RT clamps them: 1, the one a box
/// starts at, to 20.
pub const SPEED_MIN: u8 = 1;
pub const SPEED_MAX: u8 = 20;

/// Where the marks of the colour, the speed and the instant text start,
/// past the waits' and the backslash's: one character each, `+ n` for
/// colour `n`, `SPEED_MARK + n` for speed `n`, and the instant text's two.
const COLOUR_MARK: u32 = WAIT_MARK + 0x10;
const SPEED_MARK: u32 = COLOUR_MARK + COLOURS as u32;
const INSTANT_MARK: u32 = SPEED_MARK + SPEED_MAX as u32 + 1;

/// What a box carries between its letters that is not drawn: the marks a
/// line holds in place of RM2k's escapes, each one character that takes no
/// room. The console does each one where it is, as RPG_RT does: see
/// `runtime/message_pace.s`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Control {
    /// `\.`, `\|` or `\!`, by the escape's letter: see [`WAITS`].
    Wait(char),
    /// `\c[n]`, the text colour from here on, 0 to 19.
    Colour(u8),
    /// `\s[n]`, the typing speed from here on, 1 to 20.
    Speed(u8),
    /// `\>` (true) and `\<` (false): the instant text, which lasts at most
    /// to the end of the line.
    Instant(bool),
}

/// The mark that carries `control` in a line.
pub fn control_mark(control: Control) -> char {
    let code = match control {
        Control::Wait(w) => return wait_mark(w),
        Control::Colour(n) => {
            assert!(n < COLOURS, "a colour past {COLOURS}");
            COLOUR_MARK + n as u32
        }
        Control::Speed(n) => {
            assert!((SPEED_MIN..=SPEED_MAX).contains(&n), "a speed past 1-20");
            SPEED_MARK + n as u32
        }
        Control::Instant(on) => INSTANT_MARK + if on { 0 } else { 1 },
    };
    char::from_u32(code).unwrap()
}

/// What the mark `c` carries, or `None` if it is not one.
pub fn control_of(c: char) -> Option<Control> {
    if let Some(w) = wait_of(c) {
        return Some(Control::Wait(w));
    }
    let code = c as u32;
    if (COLOUR_MARK..SPEED_MARK).contains(&code) {
        return Some(Control::Colour((code - COLOUR_MARK) as u8));
    }
    if (SPEED_MARK + SPEED_MIN as u32..INSTANT_MARK).contains(&code) {
        return Some(Control::Speed((code - SPEED_MARK) as u8));
    }
    match code.checked_sub(INSTANT_MARK) {
        Some(0) => Some(Control::Instant(true)),
        Some(1) => Some(Control::Instant(false)),
        _ => None,
    }
}

/// Whether `c` is a mark that draws nothing: a wait, a colour, a speed or
/// the instant text.
pub fn is_control(c: char) -> bool {
    control_of(c).is_some()
}

/// The escape RM2k writes for `control`.
fn control_escape(control: Control) -> String {
    match control {
        Control::Wait(w) => format!("{ESCAPE}{w}"),
        Control::Colour(n) => format!("{ESCAPE}c[{n}]"),
        Control::Speed(n) => format!("{ESCAPE}s[{n}]"),
        Control::Instant(true) => format!("{ESCAPE}>"),
        Control::Instant(false) => format!("{ESCAPE}<"),
    }
}

/// The line with its marks written back as RM2k's escapes: what the reflow
/// answers, so that a box it rebuilt is RM2k text again and goes through
/// [`escape_tail`] like any other.
pub fn with_wait_escapes(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    for c in line.chars() {
        match control_of(c) {
            Some(control) => out.push_str(&control_escape(control)),
            None if is_backslash_mark(c) => {
                out.push(ESCAPE);
                out.push(ESCAPE);
            }
            None => out.push(c),
        }
    }
    out
}

/// The colour and the speed a box is left at after `lines`, starting from
/// `colour` and `speed`: what a box the reflow cut has to start with again.
pub fn state_after(lines: &[String], colour: u8, speed: u8) -> (u8, u8) {
    let (mut colour, mut speed) = (colour, speed);
    for c in lines.iter().flat_map(|l| l.chars()) {
        match control_of(c) {
            Some(Control::Colour(n)) => colour = n,
            Some(Control::Speed(n)) => speed = n,
            _ => {}
        }
    }
    (colour, speed)
}

/// The escapes that take an argument in brackets, by their letter: the
/// color, the speed, an actor's name and a variable's value. The last two
/// the event compiler writes before —see `with_names` and `with_variables`
/// in `rm2k-snes-events`—, so what reaches here of them is what it could
/// not: an actor past 255, a variable inside a variable.
const WITH_ARGUMENT: [char; 8] = ['c', 'C', 's', 'S', 'n', 'N', 'v', 'V'];

/// The line with the escapes the console does as marks —see [`Control`]—:
/// the waits that are not in the tail, `\.` (a quarter of a second), `\|` (a
/// second) and `\!` (a key); the colour `\c[n]`, the speed `\s[n]`, and the
/// instant text `\>` and `\<`. The console types the box as easyrpg's
/// `Window_Message` does and does each one where it is: see
/// `runtime/message_pace.s`. A `\\` is RM2k's literal backslash: it comes
/// out as one [`backslash_mark`], so the letter after it is not taken as an
/// escape either. A `\^` comes off, and the second answer says the line had
/// one: the box closes on its own.
///
/// The colour's and the speed's argument is read as RPG_RT reads it
/// (easyrpg's `Game_Message::ParseParam`): without a `[` it is 0 and only the
/// letter goes; inside, the digits up to the first thing that is not one,
/// and the rest up to the `]` —or to the end of the line— is skipped. A
/// colour past 19 is 0 and a speed is clamped to 1-20, as in RPG_RT.
///
/// **Every other escape is dropped and pushed to `dropped`**, as written:
/// they take no room on screen, and being dropped here they are not
/// measured either. What each one loses:
///
/// * A colour or a speed whose argument carries a `\V[n]`, which RPG_RT
///   reads at run time: up to its `]`, past the `\V[n]`.
/// * `\n[n]` and `\v[n]` the event compiler did not write, the same way.
/// * `\$` the gold window, and `\_` the half space, which the line loses:
///   making it a narrow space wants a mark the composer in `runtime/`
///   advances by, and it is done when a game misses it.
/// * Any other letter, and a backslash at the end of the line: RPG_RT
///   shows nothing for them either (the `default` of easyrpg's
///   `Window_Message`), and only the letter goes, so a `[3]` after it is
///   drawn as RPG_RT draws it. They are listed so that a patch's code or a
///   slip in the game does not go unseen.
fn with_wait_marks(line: &str, dropped: &mut Vec<String>) -> (String, bool) {
    let mut out = String::with_capacity(line.len());
    let mut closes = false;
    let chars: Vec<char> = line.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c != ESCAPE {
            out.push(c);
            i += 1;
            continue;
        }
        match chars.get(i + 1) {
            Some(&w @ ('.' | '!' | '|')) => {
                out.push(wait_mark(w));
                i += 2;
            }
            Some(&ESCAPE) => {
                out.push(backslash_mark());
                i += 2;
            }
            Some(&ESCAPE_CLOSE) => {
                closes = true;
                i += 2;
            }
            Some(&on @ ('>' | '<')) => {
                out.push(control_mark(Control::Instant(on == '>')));
                i += 2;
            }
            Some(&letter @ ('c' | 'C' | 's' | 'S')) => {
                let (value, end) = match chars.get(i + 2) {
                    Some('[') => {
                        let end = argument_end(&chars, i + 2);
                        (argument_value(&chars[i + 3..end]), end)
                    }
                    _ => (Some(0), i + 2),
                };
                match value {
                    Some(n) if matches!(letter, 'c' | 'C') => {
                        let n = if n < COLOURS as u32 { n as u8 } else { 0 };
                        out.push(control_mark(Control::Colour(n)));
                    }
                    Some(n) => {
                        let n = n.clamp(SPEED_MIN as u32, SPEED_MAX as u32) as u8;
                        out.push(control_mark(Control::Speed(n)));
                    }
                    None => dropped.push(chars[i..end].iter().collect()),
                }
                i = end;
            }
            Some(&letter) if WITH_ARGUMENT.contains(&letter) && chars.get(i + 2) == Some(&'[') => {
                let end = argument_end(&chars, i + 2);
                dropped.push(chars[i..end].iter().collect());
                i = end;
            }
            Some(_) => {
                dropped.push(chars[i..i + 2].iter().collect());
                i += 2;
            }
            None => {
                dropped.push(ESCAPE.to_string());
                i += 1;
            }
        }
    }
    (out, closes)
}

/// The value of an argument as RPG_RT reads it, from what follows its `[`
/// to its `]` or to the end of the line: the digits up to the first thing
/// that is not one, 0 if there are none. `None` if it carries a variable,
/// `\V[n]`, whose value is only known at run time. It saturates where
/// RPG_RT would overflow, but anything that large is colour 0 or speed 20
/// either way.
fn argument_value(inside: &[char]) -> Option<u32> {
    let inside = match inside.last() {
        Some(']') => &inside[..inside.len() - 1],
        _ => inside,
    };
    if inside
        .windows(2)
        .any(|w| w[0] == ESCAPE && matches!(w[1], 'v' | 'V'))
    {
        return None;
    }
    Some(
        inside
            .iter()
            .take_while(|c| c.is_ascii_digit())
            .fold(0u32, |v, c| {
                v.saturating_mul(10).saturating_add(*c as u32 - '0' as u32)
            }),
    )
}

/// Where the argument that opens at `open` —a `[`— ends: past its `]`,
/// counting the brackets of a `\V[n]` inside, or the end of the line if it
/// does not close. Another `[` inside is a letter, as RPG_RT reads it.
fn argument_end(chars: &[char], open: usize) -> usize {
    let mut depth = 0;
    for (k, &c) in chars.iter().enumerate().skip(open) {
        let variable = k >= 2 && chars[k - 2] == ESCAPE && matches!(chars[k - 1], 'v' | 'V');
        match c {
            '[' if k == open || variable => depth += 1,
            ']' => {
                depth -= 1;
                if depth == 0 {
                    return k + 1;
                }
            }
            _ => {}
        }
    }
    chars.len()
}

/// How a line is measured: the advances of the font it will be drawn
/// with, how many pixels it may take, and how many pixels a letter is
/// worth for the costs —the font's `n`—.
///
/// The tail's escapes are outside of what is measured, and a wait in the
/// middle —a [`wait_mark`]— takes no room.
#[derive(Debug, Clone)]
pub struct Measure {
    advances: Vec<u8>,
    /// The pixels a line may take.
    pub width: usize,
    /// What one letter of the costs is, in pixels.
    letter: usize,
}

impl Measure {
    /// Lines of `width` pixels in `font`, its Latin-1 letters included.
    pub fn new(font: &Font, width: usize) -> Measure {
        Measure::from_advances(font.measure_advances(), width)
    }

    /// Lines of `width` pixels in a font whose glyphs, from the space on,
    /// move the line by `advances`: how a request carries a font that is
    /// only measured.
    pub fn from_advances(advances: Vec<u8>, width: usize) -> Measure {
        let letter = advances
            .get(('n' as usize) - 32)
            .copied()
            .unwrap_or(1)
            .max(1) as usize;
        Measure {
            advances,
            width,
            letter,
        }
    }

    /// The advances it measures with, from the space on.
    pub fn advances(&self) -> &[u8] {
        &self.advances
    }

    /// Lines of `columns` characters of a fixed-width font: RM2k's, which
    /// is how the reflow measured until 2026-10-03.
    pub fn columns(columns: usize) -> Measure {
        Measure::new(
            &Font::rm2k(crate::font::MINCHO),
            columns * crate::font::WIDTH,
        )
    }

    /// The pixels `text` takes: from where it starts to where the next
    /// letter would.
    pub fn of(&self, text: &str) -> usize {
        text.chars().map(|c| self.advance(c)).sum()
    }

    /// What `c` moves the line: its glyph's advance. A Latin-1 letter is
    /// measured with its own glyph when `advances` goes that far and has it
    /// —see `Font::measure_advances`—; one the font does not draw moves it
    /// as what stands in for it —see [`crate::plain`]—, which is what the
    /// compiler draws: `ß` as two letters, `…` as three. Any other
    /// character is a space.
    pub fn advance(&self, c: char) -> usize {
        if is_control(c) {
            return 0; // a wait, a colour, a speed: they draw nothing
        }
        if c as u32 >= crate::font::LATIN_FIRST {
            if let Some(&a) = self
                .advances
                .get((c as u32 - 32) as usize)
                .filter(|&&a| a > 0)
            {
                return a as usize;
            }
        }
        if let Some(p) = crate::plain::plain(c) {
            return self.of(p);
        }
        let c = if is_backslash_mark(c) { ESCAPE } else { c };
        let code = c as u32;
        let i = (code.wrapping_sub(32)) as usize;
        let i = if code >= 32 && i < self.advances.len() {
            i
        } else {
            0
        };
        self.advances[i] as usize
    }

    /// The longest start of `word` that fits in a line, in characters: at
    /// least one, so that a word wider than anything still advances.
    fn prefix_that_fits(&self, word: &str) -> usize {
        let mut taken = 0;
        let mut used = 0;
        for c in word.chars() {
            used += self.advance(c);
            if used > self.width {
                break;
            }
            taken += 1;
        }
        taken.max(1)
    }
}

/// How many characters a text has. It is what makes a speaker's line
/// "short", and what cuts a box's tail off; the width on screen is
/// [`Measure::of`].
fn chars(text: &str) -> usize {
    text.chars().count()
}

/// Python's whitespace, which is what splits words: Unicode's, and the
/// four separators `\x1c`..`\x1f`.
fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

fn split_words(text: &str) -> Vec<String> {
    text.split(is_space)
        .filter(|w| !w.is_empty())
        .map(str::to_string)
        .collect()
}

/// Whether the word ends a sentence, with the quotes or parenthesis that
/// close it: cutting there is free. `...` counts.
fn ends_sentence(word: &str) -> bool {
    ends_with(word, &['.', '!', '?'])
}

/// Whether the word ends in a minor pause: cutting there costs little.
fn ends_pause(word: &str) -> bool {
    ends_with(word, &[',', ';', ':', '-'])
}

fn ends_with(word: &str, marks: &[char]) -> bool {
    // A wait after the period —`Wait.\|`— still ends the sentence.
    let trimmed = word.trim_end_matches(|c| matches!(c, '"' | '\'' | ')') || is_control(c));
    trimmed.chars().last().is_some_and(|c| marks.contains(&c))
}

/// Whether the line names the speaker: all caps, short, and with no
/// sentence punctuation at the end.
///
/// `?????` is the odd case that has to match —a game uses it while it is
/// not known who is speaking—, so a question mark at the end only counts
/// if there is nothing but question marks. "WHAT?" is a shouted sentence,
/// not a name.
pub fn is_speaker(line: &str) -> bool {
    let text = line.trim_matches(is_space);
    if text.is_empty() || chars(text) > 20 || text != text.to_uppercase() {
        return false;
    }
    if text.chars().all(|c| c == '?') {
        return true;
    }
    !text.ends_with(['.', '!', '?', ','])
}

/// Whether the box is fully visible, not counting its escape tail.
pub fn fits(lines: &[String], measure: &Measure, rows: usize) -> Result<bool, CannotCompile> {
    let untailed = escape_tail(lines)?.lines;
    Ok(untailed.len() <= rows && untailed.iter().all(|t| measure.of(t) <= measure.width))
}

/// What a reflow takes apart: the lines without the tail, the tail exactly
/// as written, and the escapes the box drops, written together.
struct Parts {
    untailed: Vec<String>,
    tail: String,
    dropped: String,
}

/// The box's escape tail, exactly as written, the lines without it and
/// what the box drops.
///
/// The tail is cut from the line as it was written, and not by the length
/// of what `escape_tail` left: an escape in the middle of the last line is
/// a mark there, one character for two, and counting with it cut the tail
/// short. A `\^` in the middle of the box goes to the tail, which is where
/// it acts.
fn tail(lines: &[String]) -> Result<Parts, CannotCompile> {
    let Untailed {
        lines: untailed,
        auto_close,
        dropped,
        ..
    } = escape_tail(lines)?;
    let mut tail: String = match lines.last() {
        None => String::new(),
        Some(last) => last.chars().skip(tail_start(last)).collect(),
    };
    if auto_close && !tail.contains(&format!("{ESCAPE}{ESCAPE_CLOSE}")) {
        tail.push(ESCAPE);
        tail.push(ESCAPE_CLOSE);
    }
    Ok(Parts {
        untailed,
        tail,
        dropped: dropped.concat(),
    })
}

fn prefix(text: &str, n: usize) -> String {
    text.chars().take(n).collect()
}

/// The words of the body, and after which of them the author cut.
///
/// A word wider than a line is split by force: there is no other way to
/// show it.
fn words_of(rows: &[String], m: &Measure) -> (Vec<String>, Vec<usize>) {
    let mut words = Vec::new();
    let mut cuts = Vec::new();
    for row in rows {
        for word in split_words(row) {
            let mut word = word;
            while m.of(&word) > m.width {
                let n = m.prefix_that_fits(&word);
                words.push(prefix(&word, n));
                word = word.chars().skip(n).collect();
            }
            words.push(word);
        }
        if !words.is_empty() && !cuts.contains(&(words.len() - 1)) {
            cuts.push(words.len() - 1);
        }
    }
    (words, cuts)
}

fn joined(words: &[String]) -> String {
    words.join(" ")
}

fn cut_cost(words: &[String], cuts: &[usize], i: usize) -> i64 {
    let word = &words[i];
    let mut cost = if ends_sentence(word) {
        COST_SENTENCE_END
    } else if ends_pause(word) {
        COST_PAUSE
    } else {
        COST_ANYWHERE
    };
    if cuts.contains(&i) {
        cost -= DISCOUNT_ORIGINAL_BREAK;
    }
    let first_upper = word.chars().next().is_some_and(char::is_uppercase);
    let last_alpha = word.chars().last().is_some_and(char::is_alphabetic);
    let next_digit = words
        .get(i + 1)
        .and_then(|w| w.chars().next())
        .is_some_and(|c| c.is_numeric());
    if first_upper && last_alpha && next_digit {
        cost += COST_BEFORE_NUMBER;
    }
    cost
}

/// A piece of sentence separated from the rest by a line break.
///
/// The lengths are pixels and the constants letters, so the square is
/// divided by the letter's, squared too.
fn fragment_cost(words: &[String], m: &Measure) -> f64 {
    let letter = m.letter as i64;
    let missing = (TAIL_MIN * letter - m.of(&joined(words)) as i64).max(0);
    (missing * missing) as f64 / (WEIGHT_TAIL * (letter * letter) as f64)
}

/// A cost that is still an integer or already a float, like the sums of
/// the reflow this replaces: an integer is added exactly, and becomes a
/// float only when a float joins it.
#[derive(Clone, Copy, Debug, PartialEq)]
enum Cost {
    Int(i64),
    Float(f64),
}

impl Cost {
    fn add_int(self, v: i64) -> Cost {
        match self {
            Cost::Int(a) => Cost::Int(a + v),
            Cost::Float(a) => Cost::Float(a + v as f64),
        }
    }

    fn add_float(self, v: f64) -> Cost {
        match self {
            Cost::Int(a) => Cost::Float(a as f64 + v),
            Cost::Float(a) => Cost::Float(a + v),
        }
    }

    fn add(self, other: Cost) -> Cost {
        match other {
            Cost::Int(v) => self.add_int(v),
            Cost::Float(v) => self.add_float(v),
        }
    }

    fn value(self) -> f64 {
        match self {
            Cost::Int(a) => a as f64,
            Cost::Float(a) => a,
        }
    }

    fn lt(self, other: Cost) -> bool {
        match (self, other) {
            (Cost::Int(a), Cost::Int(b)) => a < b,
            _ => self.value() < other.value(),
        }
    }
}

/// What a line with the words from `i` to `j` costs: its gap, the cut it
/// ends with and the pieces of sentence it leaves loose.
///
/// The last line does not pay for its gap —it ends where the text ends—,
/// but it does pay for being left with a single word or with a short piece
/// of the sentence above.
fn line_cost(words: &[String], cuts: &[usize], i: usize, j: usize, m: &Measure) -> Cost {
    let n = words.len();
    let length = m.of(&joined(&words[i..j])) as i64;
    let columns = m.width;
    let square = (m.letter * m.letter) as f64;
    let ends: Vec<usize> = (i..j).filter(|&k| ends_sentence(&words[k])).collect();
    let starts_sentence = i == 0 || ends_sentence(&words[i - 1]);
    let mut cost = Cost::Int(0);
    // The end of a sentence that started on the line above.
    if !starts_sentence && (j == n || (!ends.is_empty() && ends[0] < j - 1)) {
        let last = if ends.is_empty() { j } else { ends[0] + 1 };
        cost = cost.add_float(fragment_cost(&words[i..last], m));
    }
    if j == n {
        if j - i == 1 && i > 0 {
            cost = cost.add_int(COST_ORPHAN);
        }
        return cost;
    }
    // The start of a sentence that continues on the line below.
    if !ends_sentence(&words[j - 1]) && !ends.is_empty() {
        cost = cost.add_float(fragment_cost(&words[ends[ends.len() - 1] + 1..j], m));
    }
    let gap = columns as i64 - length;
    if ends_sentence(&words[j - 1]) && starts_sentence {
        cost = cost.add_float((gap * gap) as f64 / (WEIGHT_GAP * square));
    } else if ends_pause(&words[j - 1]) {
        cost = cost.add_float((gap * gap) as f64 / (WEIGHT_GAP_PAUSE * square));
    } else {
        cost = cost.add_float(WEIGHT_GAP_SPLIT * (gap as f64 / columns as f64).powf(3.0));
    }
    cost.add_int(cut_cost(words, cuts, j - 1))
}

/// The words in lines, choosing the cuts that cost the least.
///
/// It is TeX's paragraph algorithm in miniature: dynamic programming over
/// where each line ends, keeping count of how many there are so far.
fn rows_of(words: &[String], cuts: &[usize], m: &Measure, limit: Option<usize>) -> Vec<String> {
    let n = words.len();
    if n == 0 {
        return Vec::new();
    }
    // best[j][k]: the cost of putting the first j words in k lines, and
    // where the last one starts.
    let mut best: Vec<BTreeMap<usize, (Cost, usize)>> = vec![BTreeMap::new(); n + 1];
    best[0].insert(0, (Cost::Int(0), 0));
    for j in 1..=n {
        for i in (0..j).rev() {
            if m.of(&joined(&words[i..j])) > m.width {
                break;
            }
            if best[i].is_empty() {
                continue;
            }
            let own = line_cost(words, cuts, i, j, m);
            let before: Vec<(usize, Cost)> = best[i].iter().map(|(k, (c, _))| (*k, *c)).collect();
            for (k, previous) in before {
                let cost = previous.add(own);
                // `<` and not `<=`: on a tie the longest line wins, which is
                // the one found first. It is what makes it deterministic.
                let better = match best[j].get(&(k + 1)) {
                    None => true,
                    Some((current, _)) => cost.lt(*current),
                };
                if better {
                    best[j].insert(k + 1, (cost, i));
                }
            }
        }
    }
    let mut options: Vec<(usize, Cost)> = best[n].iter().map(|(k, (c, _))| (*k, *c)).collect();
    options.sort_by(|a, b| {
        a.1.value()
            .partial_cmp(&b.1.value())
            .unwrap()
            .then(a.0.cmp(&b.0))
    });
    let mut chosen = options[0].0;
    if let Some(limit) = limit {
        if chosen > limit {
            // The nicest layout does not fit in one box. If there is one
            // that fits and is not much worse, that one is used: an extra
            // box is an extra key press.
            if let Some(fit) = options.iter().find(|(k, _)| *k <= limit) {
                if fit.1.value() < options[0].1.value() + COST_EXTRA_BOX {
                    chosen = fit.0;
                }
            }
        }
    }
    let mut out = Vec::new();
    let (mut j, mut k) = (n, chosen);
    while j > 0 {
        let i = best[j][&k].1;
        out.push(joined(&words[i..j]));
        j = i;
        k -= 1;
    }
    out.reverse();
    out
}

/// The words spread over as many boxes as needed.
///
/// Each box is filled with whole sentences while they fit. A sentence that
/// does not fit in a box on its own is split by lines.
fn stretches_of(words: &[String], cuts: &[usize], m: &Measure, body: usize) -> Vec<Vec<String>> {
    let mut sentences = Vec::new();
    let mut first = 0;
    for (i, word) in words.iter().enumerate() {
        if ends_sentence(word) || i == words.len() - 1 {
            sentences.push((first, i + 1));
            first = i + 1;
        }
    }
    let lines_of = |a: usize, b: usize| -> Vec<String> {
        let local: Vec<usize> = cuts
            .iter()
            .filter(|&&c| a <= c && c < b)
            .map(|&c| c - a)
            .collect();
        rows_of(&words[a..b], &local, m, Some(body))
    };
    let mut stretches = Vec::new();
    let (mut start, mut end) = (0, 0);
    for (a, b) in sentences {
        if lines_of(start, b).len() <= body {
            end = b;
            continue;
        }
        if end > start {
            stretches.push(lines_of(start, end));
            // `end` too, but both ways below set it again.
            start = a;
        }
        if lines_of(a, b).len() <= body {
            end = b;
            continue;
        }
        // The sentence alone does not fit in a box: it is spread by lines.
        let every = lines_of(a, b);
        let mut k = 0;
        while k + body < every.len() {
            stretches.push(every[k..k + body].to_vec());
            k += body;
        }
        let rest = &every[(every.len() - 1) / body * body..];
        start = b - split_words(&rest.join(" ")).len();
        end = b;
    }
    if end > start {
        stretches.push(lines_of(start, end));
    }
    stretches
}

/// The boxes that replace this one, each a list of lines, for a window of
/// `columns` characters of RM2k's fixed-width font and `rows` lines.
pub fn refit(lines: &[String], columns: usize, rows: usize) -> Vec<Vec<String>> {
    refit_measured(lines, &Measure::columns(columns), rows)
}

/// The boxes that replace this one, each a list of lines, for a window
/// whose lines are measured with `measure` and that shows `rows` of them.
///
/// Returns the box untouched if it already fits, or if it carries an
/// escape that does not compile —[`CannotCompile`]—: that box does not
/// reach a console, so there is nothing to arrange.
pub fn refit_measured(lines: &[String], measure: &Measure, rows: usize) -> Vec<Vec<String>> {
    match fits(lines, measure, rows) {
        Err(CannotCompile) | Ok(true) => return vec![lines.to_vec()],
        Ok(false) => {}
    }
    let Parts {
        mut untailed,
        tail,
        dropped,
    } = match tail(lines) {
        Ok(t) => t,
        Err(CannotCompile) => return vec![lines.to_vec()],
    };
    let mut head = Vec::new();
    if untailed.len() > 1 && is_speaker(&untailed[0]) {
        head.push(untailed.remove(0));
    }
    let body = rows - head.len();
    let (words, cuts) = words_of(&untailed, measure);
    let mut stretches = stretches_of(&words, &cuts, measure, body);
    if stretches.is_empty() {
        stretches.push(Vec::new());
    }
    let mut frames: Vec<Vec<String>> = stretches
        .into_iter()
        .map(|s| head.iter().cloned().chain(s).collect())
        .collect();
    let last = frames.last_mut().expect("at least one box");
    if last.is_empty() {
        last.push(String::new());
    }
    last.last_mut().expect("a line").push_str(&tail);
    // A box the reflow cut goes on in the colour and at the speed the one
    // before it was left at: RPG_RT typed it all as one page, and a new page
    // starts at colour 0 and speed 1. The repeated speaker's line goes first
    // with its own, and the body takes back what the box before ended in.
    let mut carried = (0, SPEED_MIN);
    for (k, frame) in frames.iter_mut().enumerate() {
        let h = head.len();
        if k > 0 && h < frame.len() {
            let (colour, speed) = state_after(&frame[..h], 0, SPEED_MIN);
            let mut marks = String::new();
            if carried.0 != colour {
                marks.push(control_mark(Control::Colour(carried.0)));
            }
            if carried.1 != speed {
                marks.push(control_mark(Control::Speed(carried.1)));
            }
            frame[h].insert_str(0, &marks);
        }
        carried = state_after(frame, 0, SPEED_MIN);
    }
    // What the box drops goes at the start of the first one, where the
    // compiler finds it to say it was lost: where it was among the words is
    // gone with the reflow. The colour and the speed keep their place: they
    // are marks inside their words, like the waits.
    frames
        .iter_mut()
        .flatten()
        .next()
        .expect("a line")
        .insert_str(0, &dropped);
    for line in frames.iter_mut().flatten() {
        *line = with_wait_escapes(line);
    }
    frames
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(lines: &[&str]) -> Vec<String> {
        lines.iter().map(|l| l.to_string()).collect()
    }

    #[test]
    fn the_tail_comes_off_with_its_spaces() {
        let t = escape_tail(&s(&["Hi", "there\\| \\|\\^"])).unwrap();
        assert_eq!(t.lines, s(&["Hi", "there"]));
        assert_eq!((t.pauses, t.auto_close), (2, true));
        let middle = escape_tail(&s(&["a \\| b\\. c\\!"])).unwrap().lines;
        let marks: String = [
            'a',
            ' ',
            wait_mark('|'),
            ' ',
            'b',
            wait_mark('.'),
            ' ',
            'c',
            wait_mark('!'),
        ]
        .iter()
        .collect();
        assert_eq!(middle, vec![marks]);
    }

    /// A wait in the middle takes no room, the reflow carries it inside its
    /// word and answers it as the escape it was; and the tail of a last line
    /// that also has one in the middle comes off whole.
    #[test]
    fn a_wait_in_the_middle_goes_through_the_reflow() {
        let m = Measure::columns(10);
        assert_eq!(m.of(&format!("abc{}", wait_mark('!'))), m.of("abc"));
        let b = s(&["one two\\. three four five six\\! seven\\|\\^"]);
        let boxes = refit_measured(&b, &m, 4);
        let all = boxes.concat().join(" ");
        assert!(
            all.contains("two\\.") && all.contains("six\\!"),
            "{boxes:?}"
        );
        assert!(
            boxes
                .last()
                .unwrap()
                .last()
                .unwrap()
                .ends_with("seven\\|\\^"),
            "{boxes:?}"
        );
        for b in &boxes {
            assert!(fits(b, &m, 4).unwrap(), "{b:?}");
        }
    }

    /// A reflowed box keeps what it drops, at the start of its first box, so
    /// the compiler still says it lost it; and a `\^` in the middle goes to
    /// the tail of the last one, where it closes the box.
    #[test]
    fn what_a_reflowed_box_drops_is_still_there() {
        let m = Measure::columns(10);
        let b = s(&["one \\$two\\_ three\\^ four five six seven"]);
        let boxes = refit_measured(&b, &m, 2);
        assert!(boxes.len() > 1, "{boxes:?}");
        assert!(boxes[0][0].starts_with("\\$\\_one"), "{boxes:?}");
        assert!(
            boxes.last().unwrap().last().unwrap().ends_with("seven\\^"),
            "{boxes:?}"
        );
        let dropped: Vec<String> = boxes
            .iter()
            .flat_map(|b| escape_tail(b).unwrap().dropped)
            .collect();
        assert_eq!(dropped, s(&["\\$", "\\_"]));
        assert!(boxes.iter().all(|b| fits(b, &m, 2).unwrap()), "{boxes:?}");
    }

    /// The colour and the speed stay among their words through the reflow,
    /// take no room, and a box the reflow cut starts in the colour and at
    /// the speed the one before it was left at: after its speaker's line,
    /// which brings its own.
    #[test]
    fn a_reflowed_box_keeps_its_colour_and_its_speed() {
        let m = Measure::columns(12);
        assert_eq!(
            m.of(&format!("ab{}", control_mark(Control::Colour(2)))),
            m.of("ab")
        );
        let b = s(&[
            "\\c[5]ODILE\\c[0]",
            "one \\s[7]two \\c[2]three four five six seven eight nine ten",
        ]);
        let boxes = refit_measured(&b, &m, 2);
        assert!(boxes.len() > 2, "{boxes:?}");
        assert_eq!(boxes[0][0], "\\c[5]ODILE\\c[0]", "{boxes:?}");
        assert!(boxes[0][1].starts_with("one \\s[7]two"), "{boxes:?}");
        for b in &boxes[1..] {
            assert_eq!(b[0], "\\c[5]ODILE\\c[0]", "{boxes:?}");
        }
        // The box where `\c[2]` was written has it there, and every one after
        // starts its body with it and with the speed.
        let at = boxes
            .iter()
            .position(|b| b[1].contains("\\c[2]three"))
            .expect("the colour where it was written");
        assert!(boxes[at][1].starts_with("\\s[7]"), "{boxes:?}");
        for b in &boxes[at + 1..] {
            assert!(b[1].starts_with("\\c[2]\\s[7]"), "{boxes:?}");
        }
        assert!(boxes.iter().all(|b| fits(b, &m, 2).unwrap()), "{boxes:?}");
        let dropped: Vec<String> = boxes
            .iter()
            .flat_map(|b| escape_tail(b).unwrap().dropped)
            .collect();
        assert!(dropped.is_empty(), "{dropped:?}");
    }

    #[test]
    fn a_speaker_is_a_short_line_in_capitals() {
        assert!(is_speaker("ODILE"));
        assert!(is_speaker("?????"));
        assert!(!is_speaker("WHAT?"));
        assert!(!is_speaker("Odile"));
    }

    #[test]
    fn a_box_that_fits_is_left_alone() {
        let lines = s(&["                  < Wave >"]);
        assert_eq!(refit(&lines, 39, 4), vec![lines]);
    }
}
