//! RPG Maker 2000 PLUS's `ShowWindow`: a window the console draws from the
//! System and the message window's font, where a game drew a picture.
//!
//! RM2k's editor has no new commands and the game has to keep running in
//! RPG_RT, so it is written as a `Comment` —code 12410, and its lines
//! 22410— whose first line is a directive:
//!
//! ```text
//! @window <id> <x> <y> <w> <h> [plain]
//! <a line of text>
//! <another one>
//! ```
//!
//! and `@window_erase <id>`. RPG_RT skips comments. **When the command
//! right after the directive is a `ShowPicture` of picture `id`, that
//! picture is not shown: the window takes its place**, and an
//! `ErasePicture` of `id` takes the window down too. So a game keeps its
//! pictures for RPG_RT and its windows for the console in the same page,
//! one beside the other: a picture replaced one to one. Without a
//! `ShowPicture` after it, the directive shows the window alone, which
//! RPG_RT never draws.
//!
//! `x`, `y`, `w` and `h` are pixels of **the console's** 256x224 screen, all
//! multiples of 8: RPG_RT never draws the window, so there is no RM2k
//! position to translate, and a window is laid out for the screen it is
//! seen on. A framed window's text starts 8 pixels in, a `plain` one's —its
//! background without the frame— at its corner; each line is 16 pixels,
//! as a message's. The lines take RM2k's escapes as a message's do: `\c[n]`
//! the colour, `\V[n]` a variable.
//!
//! What the runtime does with it is `show_window.s`; the decision, in the
//! book, among RPG Maker 2000 PLUS's.

use crate::codes::{COMMENT, COMMENT_2, ERASE_PICTURE, SHOW_PICTURE};
use crate::fail::{Bad, Result};
use crate::game::Command;
use crate::messages::Window;
use std::collections::BTreeMap;

/// What a directive's first line starts with.
pub const SHOW: &str = "@window";
pub const ERASE: &str = "@window_erase";

/// The console's screen, in pixels.
pub const SCREEN: (i64, i64) = (256, 224);
/// A line of text: two cell rows, as a message's.
pub const LINE: i64 = 16;
/// The frame's width, and where a framed window's text starts.
pub const BORDER: i64 = 8;
/// The text tiles the message window's bank has, and the last of them,
/// which the runtime keeps for the windows' background.
pub const TEXT_TILES: usize = 240;
pub const BACKGROUND_TILE: usize = TEXT_TILES - 1;
/// How many lines a window can have: a framed one the screen's height.
pub const LINES_MAX: usize = ((SCREEN.1 - 2 * BORDER) / LINE) as usize;

/// `@window`'s style: the System's frame and background, or only the
/// background.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Style {
    Framed = 0,
    Plain = 1,
}

/// A directive, read.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Directive {
    Show(Shown),
    Erase(i64),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Shown {
    pub id: i64,
    pub x: i64,
    pub y: i64,
    pub w: i64,
    pub h: i64,
    pub style: Style,
    pub lines: Vec<String>,
}

impl Shown {
    /// Where its text starts, in pixels from its corner.
    pub fn inset(&self) -> i64 {
        match self.style {
            Style::Framed => BORDER,
            Style::Plain => 0,
        }
    }

    /// How wide its text may be, in pixels.
    pub fn text_width(&self) -> i64 {
        self.w - 2 * self.inset()
    }
}

/// The directive a comment is, if it is one: its first line and the lines
/// after it. A comment that is not one is `Ok(None)`; one that is and is
/// written wrong stops the build, saying what: it is ours, not the game's.
pub fn directive(first: &str, rest: &[String]) -> Result<Option<Directive>> {
    let words: Vec<&str> = first.split_whitespace().collect();
    let bad = |why: String| Bad::answer(format!("`{first}`: {why}"));
    let number = |w: &str| -> Result<i64> {
        w.parse::<i64>()
            .map_err(|_| bad(format!("{w:?} is not a number")))
    };
    match words.first().copied() {
        Some(ERASE) => {
            if words.len() != 2 || !rest.is_empty() {
                return Err(bad("an erase is `@window_erase <id>` alone".into()));
            }
            Ok(Some(Directive::Erase(number(words[1])?)))
        }
        Some(SHOW) => {
            if !(6..=7).contains(&words.len()) {
                return Err(bad(
                    "a window is `@window <id> <x> <y> <w> <h> [plain]`".into()
                ));
            }
            let style = match words.get(6) {
                None => Style::Framed,
                Some(&"plain") => Style::Plain,
                Some(other) => {
                    return Err(bad(format!("{other:?} is not a style: `plain` or nothing")))
                }
            };
            let shown = Shown {
                id: number(words[1])?,
                x: number(words[2])?,
                y: number(words[3])?,
                w: number(words[4])?,
                h: number(words[5])?,
                style,
                lines: rest.to_vec(),
            };
            check(&shown).map_err(bad)?;
            Ok(Some(Directive::Show(shown)))
        }
        _ => Ok(None),
    }
}

fn check(w: &Shown) -> std::result::Result<(), String> {
    if !(1..=255).contains(&w.id) {
        return Err(format!("the id {} is not a picture's, 1 to 255", w.id));
    }
    for (name, v) in [("x", w.x), ("y", w.y), ("w", w.w), ("h", w.h)] {
        if v < 0 || v % 8 != 0 {
            return Err(format!("{name} is {v}, and it goes in multiples of 8"));
        }
    }
    if w.w < 2 * w.inset() + 8 || w.h < 2 * w.inset() + 8 {
        return Err(format!("{}x{} is too small", w.w, w.h));
    }
    if w.x + w.w > SCREEN.0 || w.y + w.h > SCREEN.1 {
        return Err(format!(
            "it goes past the console's {}x{} screen",
            SCREEN.0, SCREEN.1
        ));
    }
    let room = ((w.h - 2 * w.inset()) / LINE) as usize;
    if w.lines.len() > room {
        return Err(format!(
            "{} lines of text, and a window {} pixels tall holds {room}",
            w.lines.len(),
            w.h
        ));
    }
    Ok(())
}

/// The directive a command is, with the lines `extra` its comment carries.
pub fn of_command(cmd: &Command, extra: &[String]) -> Result<Option<Directive>> {
    if cmd.code != COMMENT {
        return Ok(None);
    }
    directive(&cmd.string, extra)
}

/// The commands of a page grouped as the compiler walks them, a comment
/// with its lines: each directive, by the index of its comment.
pub fn directives(commands: &[Command]) -> Result<Vec<(usize, Directive)>> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < commands.len() {
        let mut j = i + 1;
        if commands[i].code == COMMENT {
            while j < commands.len() && commands[j].code == COMMENT_2 {
                j += 1;
            }
            let extra: Vec<String> = commands[i + 1..j]
                .iter()
                .map(|c| c.string.clone())
                .collect();
            if let Some(d) = of_command(&commands[i], &extra)? {
                out.push((i, d));
            }
        }
        i = j;
    }
    Ok(out)
}

/// The `ShowPicture`s of a page a window takes the place of: the command
/// right after a `@window` comment and its lines, when it shows the same
/// picture.
pub fn replaced_pictures(commands: &[Command]) -> Result<Vec<usize>> {
    let mut out = Vec::new();
    for (i, d) in directives(commands)? {
        let Directive::Show(w) = d else { continue };
        let mut j = i + 1;
        while j < commands.len() && commands[j].code == COMMENT_2 {
            j += 1;
        }
        if let Some(next) = commands.get(j) {
            if next.code == SHOW_PICTURE && next.parameters.first().map(|&p| p as i64) == Some(w.id)
            {
                out.push(j);
            }
        }
    }
    Ok(out)
}

/// Whether `cmd` is an `ErasePicture` of a picture some window has the
/// number of.
pub fn erased_window(cmd: &Command, registry: &Registry) -> Option<u8> {
    if cmd.code != ERASE_PICTURE {
        return None;
    }
    registry.slot(cmd.parameters.first().copied()? as i64)
}

/// The game's windows: each id's slot —its place among the ids, lowest
/// first— and its text tiles. Every `@window` of the game counts, whether
/// its page compiles or not: a window's tiles are fixed for the game, so
/// two windows up at once never write each other's.
///
/// **An id's tiles are the most one `@window` of it takes**: its lines
/// packed, two rows of each line's own cells. Two `@window`s of the same id
/// are never up together —the second takes the first's place, as a picture
/// of the same number does—, so they share the id's tiles, and each line
/// goes where the lines before it in that window end: the runtime packs
/// them from the cells `OP_WINDOW` gives each. Until 2026-11-20 each line of
/// an id had room for the widest text the game wrote on that line of that
/// id, and Desert Nightmare's keys and notes, which are its inventory's
/// windows with other text, did not fit beside the inventory.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Registry {
    /// By id: its first tile and how many it has.
    pub windows: BTreeMap<i64, (usize, usize)>,
}

impl Registry {
    /// From every page of the game, measured with `window`'s font.
    pub fn new<'a>(
        pages: impl IntoIterator<Item = &'a [Command]>,
        window: &Window,
    ) -> Result<Registry> {
        let mut most: BTreeMap<i64, usize> = BTreeMap::new();
        for commands in pages {
            for (_, d) in directives(commands)? {
                if let Directive::Show(w) = d {
                    for line in &w.lines {
                        let c = line_cells(line, window);
                        if (c * 8) as i64 > w.text_width() {
                            return Err(Bad::answer(format!(
                                "window {}'s line {line:?} is {} pixels and the window has {}",
                                w.id,
                                line_pixels(line, window),
                                w.text_width()
                            )));
                        }
                    }
                    let each = most.entry(w.id).or_default();
                    *each = (*each).max(tiles(&w.lines, window));
                }
            }
        }
        let mut windows = BTreeMap::new();
        let mut next = 0;
        for (id, tiles) in most {
            windows.insert(id, (next, tiles));
            next += tiles;
        }
        if next > BACKGROUND_TILE {
            return Err(Bad::answer(format!(
                "the game's windows take {next} text tiles together and the message window's bank has \
                 {BACKGROUND_TILE} for them: {}",
                windows
                    .iter()
                    .map(|(id, (_, tiles))| format!("{id} {tiles} tiles"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        if windows.len() > u8::MAX as usize {
            return Err(Bad::answer("more than 255 window ids"));
        }
        Ok(Registry { windows })
    }

    /// The slot of window `id`, if the game has one.
    pub fn slot(&self, id: i64) -> Option<u8> {
        self.windows.keys().position(|&k| k == id).map(|s| s as u8)
    }

    pub fn is_empty(&self) -> bool {
        self.windows.is_empty()
    }
}

/// The ids of every `@window` in these pages, lowest first: the slots the
/// runtime keeps. The converter asks it to size them.
pub fn window_ids<'a>(pages: impl IntoIterator<Item = &'a [Command]>) -> Result<Vec<i64>> {
    let mut ids = std::collections::BTreeSet::new();
    for commands in pages {
        for (_, d) in directives(commands)? {
            if let Directive::Show(w) = d {
                ids.insert(w.id);
            }
        }
    }
    Ok(ids.into_iter().collect())
}

/// How many pixels a line of text takes in `window`'s font, the escapes
/// taken as the boxes take them: a colour draws nothing, a variable is a
/// digit.
pub fn line_pixels(line: &str, window: &Window) -> usize {
    match rm2k_snes_text::refit::escape_tail(&[line.to_string()]) {
        Ok(t) => t
            .lines
            .first()
            .map_or(0, |l| l.chars().map(|c| window.advance(c)).sum()),
        Err(_) => line.chars().map(|c| window.advance(c)).sum(),
    }
}

/// The text tiles a window with these lines takes: two rows of each line's
/// cells.
pub fn tiles(lines: &[String], window: &Window) -> usize {
    lines.iter().map(|l| 2 * line_cells(l, window)).sum()
}

/// The cells a line inks: its pixels, and two more for the last letter's
/// reach past its advance and its shadow. None for an empty one.
pub fn line_cells(line: &str, window: &Window) -> usize {
    let px = line_pixels(line, window);
    if px == 0 {
        0
    } else {
        (px + 2).div_ceil(8)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cmd(code: i32, s: &str, p: Vec<i32>) -> Command {
        Command::new(code, 0, s, p)
    }

    #[test]
    fn a_window_is_read_from_its_comment() {
        let d = directive("@window 7 8 8 72 96", &["Inventory".into(), "Keys".into()]).unwrap();
        assert_eq!(
            d,
            Some(Directive::Show(Shown {
                id: 7,
                x: 8,
                y: 8,
                w: 72,
                h: 96,
                style: Style::Framed,
                lines: vec!["Inventory".into(), "Keys".into()],
            }))
        );
        assert_eq!(
            directive("@window_erase 7", &[]).unwrap(),
            Some(Directive::Erase(7))
        );
        assert_eq!(directive("just a comment", &[]).unwrap(), None);
        assert!(matches!(
            directive("@window 7 8 8 72 96 plain", &[]).unwrap(),
            Some(Directive::Show(Shown {
                style: Style::Plain,
                ..
            }))
        ));
    }

    #[test]
    fn a_window_off_the_grid_or_the_screen_stops_the_build() {
        assert!(directive("@window 7 4 8 72 96", &[]).is_err());
        assert!(directive("@window 7 200 8 72 96", &[]).is_err());
        assert!(directive("@window 7 8 8 72 32", &["a".into(), "b".into()]).is_err());
        assert!(directive("@window 0 8 8 72 32", &[]).is_err());
        assert!(directive("@window 7 8 8 72 32 round", &[]).is_err());
    }

    #[test]
    fn the_picture_after_the_window_is_the_one_it_replaces() {
        let page = vec![
            cmd(COMMENT, "@window 7 8 8 72 32", vec![]),
            cmd(COMMENT_2, "Keys", vec![]),
            cmd(SHOW_PICTURE, "Keys", vec![7, 0, 160, 120]),
            cmd(COMMENT, "@window 8 8 8 72 32", vec![]),
            cmd(SHOW_PICTURE, "Other", vec![9, 0, 160, 120]),
        ];
        assert_eq!(replaced_pictures(&page).unwrap(), vec![2]);
    }

    #[test]
    fn each_id_gets_the_tiles_its_widest_window_takes() {
        let window = Window::columns(40, 4); // six pixels a letter
        let a = vec![
            cmd(COMMENT, "@window 9 0 0 160 48", vec![]),
            cmd(COMMENT_2, "abcd", vec![]),
            cmd(COMMENT_2, "ab", vec![]),
        ];
        let b = vec![
            cmd(COMMENT, "@window 9 0 0 160 48", vec![]),
            cmd(COMMENT_2, "a", vec![]),
            cmd(COMMENT_2, "\\c[1]abcdefgh", vec![]),
            cmd(COMMENT, "@window 3 0 0 64 32", vec![]),
            cmd(COMMENT_2, "abc", vec![]),
        ];
        let r = Registry::new([a.as_slice(), b.as_slice()], &window).unwrap();
        // 3: "abc" is 18 pixels and two more, three cells. 9: "abcd" 26,
        // four, and "ab" two, six cells; or "a" one and "abcdefgh" 50,
        // seven, eight: the most one of its windows takes, and not the
        // widest of each line, eleven. Id 3 goes first.
        assert_eq!(r.windows[&3], (0, 6));
        assert_eq!(r.windows[&9], (6, 16));
        assert_eq!(r.slot(3), Some(0));
        assert_eq!(r.slot(9), Some(1));
        assert_eq!(r.slot(5), None);
    }

    #[test]
    fn windows_past_the_bank_stop_the_build() {
        let window = Window::columns(40, 4);
        let line = "a".repeat(28);
        let pages: Vec<Vec<Command>> = (1..=6)
            .map(|id| {
                vec![
                    cmd(COMMENT, &format!("@window {id} 0 0 256 48"), vec![]),
                    cmd(COMMENT_2, &line, vec![]),
                    cmd(COMMENT_2, &line, vec![]),
                ]
            })
            .collect();
        assert!(Registry::new(pages.iter().map(|p| p.as_slice()), &window).is_err());
    }
}
