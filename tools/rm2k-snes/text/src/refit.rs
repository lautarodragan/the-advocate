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

/// A box whose escapes a console cannot show: it is left as it is.
#[derive(Debug, PartialEq, Eq)]
pub struct CannotCompile;

/// The lines without their escape tail, how many pauses it has and whether
/// it closes on its own.
///
/// Both escapes are accepted only **as a tail at the end of the box's last
/// line**, which is where a game puts them; the tail may carry spaces in
/// between, and it eats them. An escape anywhere else, or more pauses than
/// [`PAUSES_MAX`], is [`CannotCompile`].
///
/// It is the event compiler's rule, `escape_tail` in `rm2k-snes-events`,
/// which cuts the tail off when it compiles the box: this copy is the one
/// the reflow works around, before the compiler sees the boxes. The two
/// read the same cases, the compiler's `tests/escapes.json`.
pub fn escape_tail(lines: &[String]) -> Result<(Vec<String>, usize, bool), CannotCompile> {
    let mut lines = lines.to_vec();
    let mut pauses = 0;
    let mut auto_close = false;
    if let Some(last) = lines.last() {
        let text: Vec<char> = last.chars().collect();
        let mut i = text.len();
        let mut cut = text.len();
        let mut escapes = 0;
        while i > 0 {
            if i >= 2 && text[i - 2] == ESCAPE && matches!(text[i - 1], ESCAPE_PAUSE | ESCAPE_CLOSE) {
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
            let tail = &text[cut..];
            pauses = tail
                .windows(2)
                .filter(|w| w[0] == ESCAPE && w[1] == ESCAPE_PAUSE)
                .count();
            auto_close = tail.windows(2).any(|w| w[0] == ESCAPE && w[1] == ESCAPE_CLOSE);
            let n = lines.len();
            lines[n - 1] = text[..cut].iter().collect();
        }
    }
    if lines.iter().any(|t| t.contains(ESCAPE)) || pauses > PAUSES_MAX {
        return Err(CannotCompile);
    }
    Ok((lines, pauses, auto_close))
}

/// How many columns a text takes: one character, one column. The font is
/// fixed-width, and the only escapes that compile go in the tail, outside
/// of this.
pub fn width(text: &str) -> usize {
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
    let trimmed = word.trim_end_matches(['"', '\'', ')']);
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
    if text.is_empty() || width(text) > 20 || text != text.to_uppercase() {
        return false;
    }
    if text.chars().all(|c| c == '?') {
        return true;
    }
    !text.ends_with(['.', '!', '?', ','])
}

/// Whether the box is fully visible, not counting its escape tail.
pub fn fits(lines: &[String], columns: usize, rows: usize) -> Result<bool, CannotCompile> {
    let (untailed, _, _) = escape_tail(lines)?;
    Ok(untailed.len() <= rows && untailed.iter().all(|t| width(t) <= columns))
}

/// The box's escape tail, exactly as written, and the lines without it.
fn tail(lines: &[String]) -> Result<(Vec<String>, String), CannotCompile> {
    let (untailed, _, _) = escape_tail(lines)?;
    match untailed.last() {
        None => Ok((untailed, String::new())),
        Some(last) => {
            let kept = width(last);
            let tail = lines[lines.len() - 1].chars().skip(kept).collect();
            Ok((untailed, tail))
        }
    }
}

fn prefix(text: &str, n: usize) -> String {
    text.chars().take(n).collect()
}

/// The words of the body, and after which of them the author cut.
///
/// A word wider than a line is split by force: there is no other way to
/// show it.
fn words_of(rows: &[String], columns: usize) -> (Vec<String>, Vec<usize>) {
    let mut words = Vec::new();
    let mut cuts = Vec::new();
    for row in rows {
        for word in split_words(row) {
            let mut word = word;
            while width(&word) > columns {
                words.push(prefix(&word, columns));
                word = word.chars().skip(columns).collect();
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
fn fragment_cost(words: &[String]) -> f64 {
    let missing = (TAIL_MIN - width(&joined(words)) as i64).max(0);
    (missing * missing) as f64 / WEIGHT_TAIL
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
fn line_cost(words: &[String], cuts: &[usize], i: usize, j: usize, columns: usize) -> Cost {
    let n = words.len();
    let length = width(&joined(&words[i..j])) as i64;
    let ends: Vec<usize> = (i..j).filter(|&k| ends_sentence(&words[k])).collect();
    let starts_sentence = i == 0 || ends_sentence(&words[i - 1]);
    let mut cost = Cost::Int(0);
    // The end of a sentence that started on the line above.
    if !starts_sentence && (j == n || (!ends.is_empty() && ends[0] < j - 1)) {
        let last = if ends.is_empty() { j } else { ends[0] + 1 };
        cost = cost.add_float(fragment_cost(&words[i..last]));
    }
    if j == n {
        if j - i == 1 && i > 0 {
            cost = cost.add_int(COST_ORPHAN);
        }
        return cost;
    }
    // The start of a sentence that continues on the line below.
    if !ends_sentence(&words[j - 1]) && !ends.is_empty() {
        cost = cost.add_float(fragment_cost(&words[ends[ends.len() - 1] + 1..j]));
    }
    let gap = columns as i64 - length;
    if ends_sentence(&words[j - 1]) && starts_sentence {
        cost = cost.add_float((gap * gap) as f64 / WEIGHT_GAP);
    } else if ends_pause(&words[j - 1]) {
        cost = cost.add_float((gap * gap) as f64 / WEIGHT_GAP_PAUSE);
    } else {
        cost = cost.add_float(WEIGHT_GAP_SPLIT * (gap as f64 / columns as f64).powf(3.0));
    }
    cost.add_int(cut_cost(words, cuts, j - 1))
}

/// The words in lines, choosing the cuts that cost the least.
///
/// It is TeX's paragraph algorithm in miniature: dynamic programming over
/// where each line ends, keeping count of how many there are so far.
fn rows_of(words: &[String], cuts: &[usize], columns: usize, limit: Option<usize>) -> Vec<String> {
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
            if width(&joined(&words[i..j])) > columns {
                break;
            }
            if best[i].is_empty() {
                continue;
            }
            let own = line_cost(words, cuts, i, j, columns);
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
fn stretches_of(words: &[String], cuts: &[usize], columns: usize, body: usize) -> Vec<Vec<String>> {
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
        rows_of(&words[a..b], &local, columns, Some(body))
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
/// `columns` characters and `rows` lines.
///
/// Returns the box untouched if it already fits, or if it carries an
/// escape that does not compile —[`CannotCompile`]—: that box does not
/// reach a console, so there is nothing to arrange.
pub fn refit(lines: &[String], columns: usize, rows: usize) -> Vec<Vec<String>> {
    match fits(lines, columns, rows) {
        Err(CannotCompile) | Ok(true) => return vec![lines.to_vec()],
        Ok(false) => {}
    }
    let (mut untailed, tail) = match tail(lines) {
        Ok(t) => t,
        Err(CannotCompile) => return vec![lines.to_vec()],
    };
    let mut head = Vec::new();
    if untailed.len() > 1 && is_speaker(&untailed[0]) {
        head.push(untailed.remove(0));
    }
    let body = rows - head.len();
    let (words, cuts) = words_of(&untailed, columns);
    let mut stretches = stretches_of(&words, &cuts, columns, body);
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
        let (lines, pauses, close) = escape_tail(&s(&["Hi", "there\\| \\|\\^"])).unwrap();
        assert_eq!(lines, s(&["Hi", "there"]));
        assert_eq!((pauses, close), (2, true));
        assert!(escape_tail(&s(&["a \\| b"])).is_err());
    }

    #[test]
    fn a_speaker_is_a_short_line_in_capitals() {
        assert!(is_speaker("KERSH"));
        assert!(is_speaker("?????"));
        assert!(!is_speaker("WHAT?"));
        assert!(!is_speaker("Kersh"));
    }

    #[test]
    fn a_box_that_fits_is_left_alone() {
        let lines = s(&["                  < Kiss >"]);
        assert_eq!(refit(&lines, 39, 4), vec![lines]);
    }
}
