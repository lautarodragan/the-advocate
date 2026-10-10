//! A custom menu: a screen the engine draws and walks by itself, which a
//! game declares as data instead of building it out of pictures and
//! `KeyInputProc`.
//!
//! RPG Maker 2000 has no such thing, and games build one out of a common
//! event that shows pictures and waits for keys: a page per picture, the
//! text painted into them. Here the game writes a file with what each page
//! says, and the engine draws it with the System's windows and the font,
//! in the text layer the item screen uses, and walks it with the pause
//! menu's keys. It is opened from one more option of the pause menu and,
//! if the file says so, from the common event it replaces.
//!
//! **What a menu is**: a list of *subjects* —an actor of the party, or a
//! fixed entry—, each with its *tabs*, each tab with its *pages*: the first
//! one whose condition holds is the one shown, and a tab with none goes in
//! gray. A page is text, a table of name / value / cap with the values that
//! mean something else written as words, or counters over a text.
//!
//! The file, in TOML; the converter hands it over as JSON:
//!
//! ```toml
//! label = "Notes"                # its option in the pause menu
//! title = "Field Notes"          # the header over the subjects
//! visible = { item = 81 }        # when the option is there
//! replaces_common = 39           # the common event that opens it
//!
//! [[subject]]
//! actor = 14                     # shown while the actor is in the party
//! portrait = "PortraitHero"      # a picture of the game's Picture/
//! crop = [6, 6, 150, 188]        # the part of it that is the portrait
//!
//! [[subject.tab]]
//! label = "Skills"
//! help = "What shows at the bottom while the tab is chosen."
//!
//! [[subject.tab.page]]
//! when = { switch = 133 }
//! table = "auras"
//!
//! [[subject.tab.page]]
//! text = "TALAN does not have any skills."
//! ```
//!
//! What the cartridge carries is one block of bytes the runtime walks
//! —[`Built::blob`], whose format is in `custom_menu.s`—, the windows of
//! each arrangement as BG1 tilemaps, the inks the menu writes in besides
//! the text screens' four, and each portrait as 4bpp object tiles with its
//! palette.

use crate::borders::{self, Screen};
use crate::cells::{self, rgb15, Color, Counts, BLACK, CELL, COLS, HEIGHT, WIDTH};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::items::{ink_colors, INK_ROW_FIRST};
use crate::layout::{Rect, ITEM_FIRST_CHAR, ITEM_CHARS, SCR_TEXT_X};
use rm2k_render::picture::{self, FilterType};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap};
use voodoo::pack::Indices;

// --- the geometry -------------------------------------------------------------
//
// Everything in cells of 8x8 and lines of two cell rows, which is how the
// text layer writes. Full screen: the map does not show, and the screen has
// the whole VRAM.

/// The header, on top of every arrangement: the title or what is being
/// looked at, and where in the list it is.
pub const CM_HEADER: Rect = (0, 0, WIDTH, 32);
pub const CM_HEADER_ROW: usize = 1;
pub const CM_TEXT_COL: usize = 1;
/// Where "< 1 / 4 >" starts.
pub const CM_INDEX_COL: usize = 25;
/// The subjects: the portrait on the left, the name and the tabs on the
/// right, and the chosen tab's help below.
pub const CM_PORTRAIT_WINDOW: Rect = (0, 32, 112, 144);
pub const CM_PORTRAIT_X: usize = 8;
pub const CM_PORTRAIT_Y: usize = 40;
pub const CM_PORTRAIT_W: usize = 96;
pub const CM_PORTRAIT_H: usize = 120;
/// The portrait in tiles: twelve by fifteen, which the cartridge shows as
/// three by four objects of 32x32; the last tile row of those is empty.
pub const CM_PORTRAIT_COLS: usize = CM_PORTRAIT_W / CELL;
pub const CM_PORTRAIT_ROWS: usize = CM_PORTRAIT_H / CELL;
pub const CM_INFO_WINDOW: Rect = (112, 32, WIDTH - 112, 64);
pub const CM_INFO_COL: usize = 15;
pub const CM_NAME_ROW: usize = 5;
pub const CM_CLASS_ROW: usize = 7;
pub const CM_LEVEL_ROW: usize = 9;
/// The level's number, after the term.
pub const CM_LEVEL_NUM_COL: usize = 17;
pub const CM_TABS_WINDOW: Rect = (112, 96, WIDTH - 112, 80);
pub const CM_TAB_COL: usize = 16;
pub const CM_TAB_ROW0: usize = 13;
pub const CM_TABS_MAX: usize = 4;
/// The bar under the chosen tab: the System's cursor, four pixels wider
/// than the text on the left.
pub const CM_BAR_X: usize = CM_TAB_COL * CELL - 4;
pub const CM_BAR_WIDTH: usize = WIDTH - 8 - CM_BAR_X;
pub const CM_HELP_WINDOW: Rect = (0, 176, WIDTH, HEIGHT - 176);
pub const CM_HELP_ROW0: usize = 23;
pub const CM_HELP_LINES: usize = 2;
/// The pages: below the header, one window or two.
pub const CM_BODY_Y: usize = 32;
/// The first row of a page's body, and of a table's rows, under its heading.
pub const CM_BODY_ROW0: usize = (CM_BODY_Y + 8) / CELL;
pub const CM_TABLE_ROW0: usize = CM_BODY_ROW0 + 2;
/// How wide a line of a page may be, in pixels: the window's inside from
/// where a text starts in its first cell.
pub const CM_TEXT_WIDTH: usize = (COLS - 2) * CELL - SCR_TEXT_X;
/// The table's columns: the name from `CM_TEXT_COL`, the value ending with
/// cell `CM_VALUE_COL`, a slash and the cap ending with `CM_CAP_COL`.
pub const CM_VALUE_COL: usize = 24;
pub const CM_SLASH_COL: usize = 25;
pub const CM_CAP_COL: usize = 28;
/// A counter's value ends with this cell.
pub const CM_COUNTER_COL: usize = 29;
/// How many rows a table can have.
pub const CM_TABLE_ROWS_MAX: usize = 10;
/// The colours the text layer writes in: its palettes. The first four are
/// the text screens' —see `ITEM_COLORS`—; a menu brings the rest.
pub const CM_WHITE: u8 = 0;
pub const CM_GRAY: u8 = 1;
pub const CM_RED: u8 = 3;
pub const CM_INKS_FIRST: usize = 4;
pub const CM_INKS_MAX: usize = 8;
/// The System colours of the first four palettes, in their order.
const BASE_INKS: [(i32, u8); 4] = [(0, 0), (3, 1), (2, 2), (1, 3)];
/// Where the windows' colours go: after the eight palettes the text may
/// use, and before the portrait's object palette, the last one.
pub const CM_BORDER_CGRAM: usize = 128;
pub const CM_BORDER_CGRAM_END: usize = 240;
/// The arrangements' first one: the subjects'.
pub const CM_LAYOUT_SUBJECTS: usize = 0;
/// What a variable is written as when a text is cut to the window: its
/// value is not known until the console shows it.
const VALUE_WIDTH: &str = "000";

/// The kinds of page, as the cartridge reads them.
const PAGE_TEXT: u8 = 0;
const PAGE_TABLE: u8 = 1;
const PAGE_COUNTERS: u8 = 2;
/// The escape that, in a line the cartridge writes letter by letter, says a
/// variable's value goes there: the byte, and its slot times two.
const ESCAPE_VARIABLE: u8 = 1;
/// A line's two ways: its letters by reference, or letter by letter
/// because it has variables.
const LINE_PLAIN: u8 = 0;
const LINE_ESCAPED: u8 = 1;
/// The conditions, as the cartridge reads them: a kind and two words.
const COND_ALWAYS: u8 = 0;
const COND_SWITCH: u8 = 1;
const COND_VARIABLE: u8 = 2;
const COND_ITEM: u8 = 3;
const COND_ACTOR: u8 = 4;

/// What the cartridge decided that a menu needs to be written down: where
/// each variable is kept, and the shared body each `before` runs.
#[derive(Debug, Clone, Default)]
pub struct Context {
    pub variables: BTreeMap<i32, usize>,
    pub before_bodies: BTreeMap<i32, u8>,
}

/// A condition of the file: the ones RM2k's pages have.
#[derive(Debug, Clone, PartialEq)]
pub enum Cond {
    Always,
    Switch(i32),
    VariableAtLeast(i32, i64),
    Item(i32),
    Actor(i32),
}

/// A piece of a line: letters, or a variable's value.
#[derive(Debug, Clone, PartialEq)]
enum Piece {
    Text(String),
    Variable(i32),
}

/// A line as written: its pieces, in a colour, from a cell.
#[derive(Debug, Clone, PartialEq)]
struct Line {
    col: usize,
    color: i32,
    pieces: Vec<Piece>,
}

#[derive(Debug, Clone)]
struct Table {
    title: String,
    columns: (String, String),
    special: Vec<(i64, String)>,
    sheets: Vec<Sheet>,
}

#[derive(Debug, Clone)]
struct Sheet {
    title: String,
    color: i32,
    rows: Vec<(String, i32, Cap)>,
}

#[derive(Debug, Clone)]
enum Cap {
    Fixed(i64),
    Variable(i32),
    None,
}

/// A row's cap as the cartridge reads it: the kind —0 a number, 1 a
/// variable's slot times two, 2 none— and its word.
const CAP_FIXED: u8 = 0;
const CAP_VARIABLE: u8 = 1;
const CAP_NONE: u8 = 2;

#[derive(Debug, Clone)]
enum Body {
    Text,
    Table(String),
    Counters(Vec<(String, i32, Cap)>),
}

#[derive(Debug, Clone)]
struct Page {
    when: Cond,
    before: Option<i32>,
    body: Body,
    lines: Vec<Line>,
}

#[derive(Debug, Clone)]
struct Tab {
    label: String,
    help: Vec<Line>,
    pages: Vec<Page>,
}

#[derive(Debug, Clone)]
struct Subject {
    actor: Option<i32>,
    when: Cond,
    name: String,
    class: String,
    portrait: Option<(String, [usize; 4])>,
    tabs: Vec<Tab>,
}

/// A menu file, read.
#[derive(Debug, Clone)]
pub struct Menu {
    pub name: String,
    pub label: String,
    pub title: String,
    pub visible: Cond,
    pub replaces_common: Option<i32>,
    subjects: Vec<Subject>,
    tables: BTreeMap<String, Table>,
}

// --- reading the file ---------------------------------------------------------

struct Reader<'a> {
    whose: &'a str,
}

impl Reader<'_> {
    fn bad(&self, what: &str) -> Bad {
        Bad::answer(format!("{}: {what}", self.whose))
    }

    fn text(&self, v: &Value, key: &str) -> Result<Option<String>> {
        match v.get(key) {
            None | Some(Value::Null) => Ok(None),
            Some(Value::String(s)) => Ok(Some(s.clone())),
            Some(other) => Err(self.bad(&format!("`{key}` is {other}, and not a text"))),
        }
    }

    fn int(&self, v: &Value, key: &str) -> Result<Option<i64>> {
        match v.get(key) {
            None | Some(Value::Null) => Ok(None),
            Some(n) => n
                .as_i64()
                .map(Some)
                .ok_or_else(|| self.bad(&format!("`{key}` is {n}, and not a number"))),
        }
    }

    fn list<'v>(&self, v: &'v Value, key: &str) -> Result<&'v [Value]> {
        match v.get(key) {
            None | Some(Value::Null) => Ok(&[]),
            Some(Value::Array(a)) => Ok(a),
            Some(other) => Err(self.bad(&format!("`{key}` is {other}, and not a list"))),
        }
    }

    fn cond(&self, v: Option<&Value>) -> Result<Cond> {
        let Some(v) = v.filter(|v| !v.is_null()) else {
            return Ok(Cond::Always);
        };
        let o = v
            .as_object()
            .ok_or_else(|| self.bad(&format!("a condition is {v}, and not a table")))?;
        let number = |key: &str| -> Result<i64> {
            o.get(key)
                .and_then(Value::as_i64)
                .ok_or_else(|| self.bad(&format!("the condition {v} has no number `{key}`")))
        };
        let cond = if o.contains_key("switch") {
            Cond::Switch(number("switch")? as i32)
        } else if o.contains_key("variable") {
            Cond::VariableAtLeast(number("variable")? as i32, number("at_least")?)
        } else if o.contains_key("item") {
            Cond::Item(number("item")? as i32)
        } else if o.contains_key("actor") {
            Cond::Actor(number("actor")? as i32)
        } else {
            return Err(self.bad(&format!(
                "the condition {v} is none of `switch`, `variable` and `at_least`, `item` or `actor`"
            )));
        };
        Ok(cond)
    }
}

/// `\V[n]` and `\N[n]` in a text: the variable's value, which the
/// cartridge writes, and the actor's name, which goes in now —the
/// cartridge carries no way of renaming an actor—.
fn pieces(game: &Game, text: &str) -> Result<Vec<Piece>> {
    let mut out = Vec::new();
    let mut letters = String::new();
    let mut rest = text;
    while let Some(at) = rest.find('\\') {
        letters.push_str(&rest[..at]);
        let after = &rest[at + 1..];
        let code = after.chars().next().map(|c| c.to_ascii_uppercase());
        let number = after
            .get(1..)
            .filter(|a| a.starts_with('['))
            .and_then(|a| a.find(']').map(|end| (&a[1..end], end + 2)));
        match (code, number) {
            (Some(c @ ('V' | 'N')), Some((digits, used))) => {
                let n: i32 = digits
                    .parse()
                    .map_err(|_| Bad::answer(format!("{text:?}: \\{c}[{digits}] is not a number")))?;
                if c == 'V' {
                    if !letters.is_empty() {
                        out.push(Piece::Text(std::mem::take(&mut letters)));
                    }
                    out.push(Piece::Variable(n));
                } else {
                    letters.push_str(&game.actor_name(n)?);
                }
                rest = &after[used..];
            }
            _ => {
                letters.push('\\');
                rest = after;
            }
        }
    }
    letters.push_str(rest);
    if !letters.is_empty() {
        out.push(Piece::Text(letters));
    }
    Ok(out)
}

/// What a line takes, in pixels, with each variable as wide as
/// [`VALUE_WIDTH`].
fn width(game: &Game, pieces: &[Piece]) -> usize {
    pieces
        .iter()
        .map(|p| match p {
            Piece::Text(t) => game.font.width(t),
            Piece::Variable(_) => game.font.width(VALUE_WIDTH),
        })
        .sum()
}

/// A paragraph cut into lines of at most `room` pixels, by words, keeping
/// the paragraph's indentation on each of them.
fn wrap(game: &Game, paragraph: &str, room: usize) -> Result<Vec<Vec<Piece>>> {
    let indent: String = paragraph.chars().take_while(|c| *c == ' ').collect();
    let words: Vec<&str> = paragraph.split(' ').filter(|w| !w.is_empty()).collect();
    if words.is_empty() {
        return Ok(vec![Vec::new()]);
    }
    let mut lines: Vec<String> = Vec::new();
    let mut current = indent.clone();
    for word in words {
        let candidate = if current.trim().is_empty() {
            format!("{current}{word}")
        } else {
            format!("{current} {word}")
        };
        if width(game, &pieces(game, &candidate)?) <= room || current.trim().is_empty() {
            current = candidate;
        } else {
            lines.push(current);
            current = format!("{indent}{word}");
        }
    }
    lines.push(current);
    lines.iter().map(|l| pieces(game, l)).collect()
}

/// A page's or a help's text: `text`, a string whose paragraphs —split at
/// its line breaks— are cut to the window; or `lines`, each a string that
/// goes as it is or a table with `text` and optionally `color` and
/// `center`.
fn text_lines(game: &Game, r: &Reader, v: &Value, room: usize) -> Result<Vec<Line>> {
    let mut out = Vec::new();
    if let Some(text) = r.text(v, "text")? {
        for paragraph in text.split('\n') {
            for pieces in wrap(game, paragraph.trim_end(), room)? {
                out.push(Line { col: CM_TEXT_COL, color: 0, pieces });
            }
        }
    }
    for line in r.list(v, "lines")? {
        let (text, color, center) = match line {
            Value::String(s) => (s.clone(), 0, false),
            Value::Object(_) => (
                r.text(line, "text")?.unwrap_or_default(),
                r.int(line, "color")?.unwrap_or(0) as i32,
                line.get("center").and_then(Value::as_bool).unwrap_or(false),
            ),
            other => return Err(r.bad(&format!("a line is {other}"))),
        };
        let pieces = pieces(game, &text)?;
        let taken = width(game, &pieces);
        if taken > room {
            return Err(r.bad(&format!("the line {text:?} takes {taken} pixels and {room} fit")));
        }
        let col = if center {
            CM_TEXT_COL + (room - taken) / 2 / CELL
        } else {
            CM_TEXT_COL
        };
        out.push(Line { col, color, pieces });
    }
    Ok(out)
}

impl Menu {
    /// The menu `name` from its file, as JSON.
    pub fn read(game: &Game, name: &str, spec: &Value) -> Result<Menu> {
        let whose = format!("menu {name:?}");
        let r = Reader { whose: &whose };
        let label = r
            .text(spec, "label")?
            .ok_or_else(|| r.bad("no `label`: the pause menu option needs one"))?;
        let mut tables = BTreeMap::new();
        if let Some(t) = spec.get("table").filter(|t| !t.is_null()) {
            let t = t
                .as_object()
                .ok_or_else(|| r.bad("`table` is not a table of tables"))?;
            for (key, table) in t {
                let columns = r.list(table, "columns")?;
                let column = |k: usize| columns.get(k).and_then(Value::as_str).unwrap_or("").to_string();
                let mut special = Vec::new();
                if let Some(s) = table.get("special").and_then(Value::as_object) {
                    for (value, text) in s {
                        let value: i64 = value
                            .parse()
                            .map_err(|_| r.bad(&format!("table {key:?}: special value {value:?}")))?;
                        let text = text
                            .as_str()
                            .ok_or_else(|| r.bad(&format!("table {key:?}: special {value} is not a text")))?;
                        special.push((value, text.to_string()));
                    }
                }
                let mut sheets = Vec::new();
                for sheet in r.list(table, "sheet")? {
                    let mut rows = Vec::new();
                    for row in r.list(sheet, "rows")? {
                        let row = row
                            .as_array()
                            .filter(|a| a.len() == 3)
                            .ok_or_else(|| r.bad(&format!("table {key:?}: a row is {row}, and not [name, variable, cap]")))?;
                        let name = row[0].as_str().unwrap_or("").to_string();
                        let variable = row[1]
                            .as_i64()
                            .ok_or_else(|| r.bad(&format!("table {key:?}: {name:?} has no variable")))?
                            as i32;
                        let cap = match &row[2] {
                            Value::Number(n) => Cap::Fixed(n.as_i64().unwrap_or(0)),
                            Value::String(s) if s.starts_with('v') => Cap::Variable(
                                s[1..]
                                    .parse()
                                    .map_err(|_| r.bad(&format!("table {key:?}: cap {s:?}")))?,
                            ),
                            other => return Err(r.bad(&format!("table {key:?}: cap {other}"))),
                        };
                        rows.push((name, variable, cap));
                    }
                    if rows.len() > CM_TABLE_ROWS_MAX {
                        return Err(r.bad(&format!(
                            "table {key:?} has a sheet of {} rows and {CM_TABLE_ROWS_MAX} fit",
                            rows.len()
                        )));
                    }
                    sheets.push(Sheet {
                        title: r.text(sheet, "title")?.unwrap_or_default(),
                        color: r.int(sheet, "color")?.unwrap_or(0) as i32,
                        rows,
                    });
                }
                if sheets.is_empty() {
                    return Err(r.bad(&format!("table {key:?} has no sheet")));
                }
                tables.insert(
                    key.clone(),
                    Table {
                        title: r.text(table, "title")?.unwrap_or_default(),
                        columns: (column(0), column(1)),
                        special,
                        sheets,
                    },
                );
            }
        }
        let mut subjects = Vec::new();
        for s in r.list(spec, "subject")? {
            let actor = r.int(s, "actor")?.map(|a| a as i32);
            let name = match (r.text(s, "name")?, actor) {
                (Some(n), _) => n,
                (None, Some(a)) => game.actor_name(a)?,
                (None, None) => return Err(r.bad("a subject with no `actor` needs a `name`")),
            };
            let class = match (r.text(s, "class")?, actor) {
                (Some(c), _) => c,
                (None, Some(a)) => game.actors.get(&a).map(|x| x.title.clone()).unwrap_or_default(),
                (None, None) => String::new(),
            };
            let portrait = match r.text(s, "portrait")? {
                None => None,
                Some(p) => {
                    let crop = r.list(s, "crop")?;
                    let crop = if crop.is_empty() {
                        [0, 0, 0, 0]
                    } else {
                        let c: Vec<usize> = crop.iter().map(|c| c.as_u64().unwrap_or(0) as usize).collect();
                        if c.len() != 4 {
                            return Err(r.bad(&format!("{name}: `crop` is not [x, y, width, height]")));
                        }
                        [c[0], c[1], c[2], c[3]]
                    };
                    Some((p, crop))
                }
            };
            let mut tabs = Vec::new();
            for t in r.list(s, "tab")? {
                let label = r
                    .text(t, "label")?
                    .ok_or_else(|| r.bad(&format!("{name}: a tab has no `label`")))?;
                let help = match r.text(t, "help")? {
                    None => Vec::new(),
                    Some(h) => text_lines(game, &r, &json!({"text": h}), CM_TEXT_WIDTH)?,
                };
                if help.len() > CM_HELP_LINES {
                    return Err(r.bad(&format!(
                        "{name}, {label}: the help takes {} lines and {CM_HELP_LINES} fit",
                        help.len()
                    )));
                }
                let mut pages = Vec::new();
                for p in r.list(t, "page")? {
                    let before = match p.get("before").filter(|b| !b.is_null()) {
                        None => None,
                        Some(b) => Some(
                            b.get("common")
                                .and_then(Value::as_i64)
                                .ok_or_else(|| r.bad(&format!("{name}, {label}: `before` is not {{ common = n }}")))?
                                as i32,
                        ),
                    };
                    let body = if let Some(table) = r.text(p, "table")? {
                        if !tables.contains_key(&table) {
                            return Err(r.bad(&format!("{name}, {label}: there is no table {table:?}")));
                        }
                        Body::Table(table)
                    } else if p.get("counters").is_some() {
                        let mut counters = Vec::new();
                        for c in r.list(p, "counters")? {
                            let c = c
                                .as_array()
                                .filter(|c| c.len() == 2 || c.len() == 3)
                                .ok_or_else(|| r.bad(&format!("{name}, {label}: a counter is {c}, and not [label, variable] or [label, variable, cap]")))?;
                            let cap = match c.get(2) {
                                None => Cap::None,
                                Some(Value::Number(n)) => Cap::Fixed(n.as_i64().unwrap_or(0)),
                                Some(Value::String(s)) if s.starts_with('v') => Cap::Variable(
                                    s[1..].parse().map_err(|_| r.bad(&format!("{name}, {label}: cap {s:?}")))?,
                                ),
                                Some(other) => return Err(r.bad(&format!("{name}, {label}: cap {other}"))),
                            };
                            counters.push((
                                c[0].as_str().unwrap_or("").to_string(),
                                c[1].as_i64().unwrap_or(0) as i32,
                                cap,
                            ));
                        }
                        Body::Counters(counters)
                    } else {
                        Body::Text
                    };
                    let lines = text_lines(game, &r, p, CM_TEXT_WIDTH)?;
                    pages.push(Page { when: r.cond(p.get("when"))?, before, body, lines });
                }
                tabs.push(Tab { label, help, pages });
            }
            if tabs.len() > CM_TABS_MAX {
                return Err(r.bad(&format!("{name} has {} tabs and {CM_TABS_MAX} fit", tabs.len())));
            }
            if tabs.is_empty() {
                return Err(r.bad(&format!("{name} has no tab")));
            }
            subjects.push(Subject {
                actor,
                when: r.cond(s.get("when"))?,
                name,
                class,
                portrait,
                tabs,
            });
        }
        if subjects.is_empty() {
            return Err(r.bad("no subject"));
        }
        Ok(Menu {
            name: name.to_string(),
            label,
            title: r.text(spec, "title")?.unwrap_or_default(),
            visible: r.cond(spec.get("visible"))?,
            replaces_common: r.int(spec, "replaces_common")?.map(|n| n as i32),
            subjects,
            tables,
        })
    }

    /// The common events this menu runs before a page: their numbers.
    pub fn befores(&self) -> Vec<i32> {
        let mut out: Vec<i32> = self
            .subjects
            .iter()
            .flat_map(|s| s.tabs.iter())
            .flat_map(|t| t.pages.iter())
            .filter_map(|p| p.before)
            .collect();
        out.sort();
        out.dedup();
        out
    }

    /// The variables this menu reads.
    pub fn variables(&self) -> Vec<i32> {
        let mut out = Vec::new();
        let cond = |c: &Cond, out: &mut Vec<i32>| {
            if let Cond::VariableAtLeast(v, _) = c {
                out.push(*v);
            }
        };
        let lines = |ls: &[Line], out: &mut Vec<i32>| {
            for l in ls {
                for p in &l.pieces {
                    if let Piece::Variable(v) = p {
                        out.push(*v);
                    }
                }
            }
        };
        cond(&self.visible, &mut out);
        for s in &self.subjects {
            cond(&s.when, &mut out);
            for t in &s.tabs {
                lines(&t.help, &mut out);
                for p in &t.pages {
                    cond(&p.when, &mut out);
                    lines(&p.lines, &mut out);
                    if let Body::Counters(c) = &p.body {
                        for (_, v, cap) in c {
                            out.push(*v);
                            if let Cap::Variable(cv) = cap {
                                out.push(*cv);
                            }
                        }
                    }
                }
            }
        }
        for t in self.tables.values() {
            for sheet in &t.sheets {
                for (_, v, cap) in &sheet.rows {
                    out.push(*v);
                    if let Cap::Variable(c) = cap {
                        out.push(*c);
                    }
                }
            }
        }
        out.sort();
        out.dedup();
        out
    }
}

/// What a request carries of each menu: its name and its file, as JSON.
pub fn read_all(game: &Game, menus: &[(String, Value)]) -> Result<Vec<Menu>> {
    menus.iter().map(|(name, spec)| Menu::read(game, name, spec)).collect()
}

// --- writing it down ----------------------------------------------------------

/// The block of bytes, with the offsets the cartridge follows: each record
/// is appended and its offset handed back. Offset 0 is the root, so a field
/// that names none says 0.
#[derive(Default)]
struct Blob {
    bytes: Vec<u8>,
}

impl Blob {
    fn at(&self) -> u16 {
        self.bytes.len() as u16
    }

    fn word(&mut self, w: u16) {
        self.bytes.extend(w.to_le_bytes());
    }

    fn patch(&mut self, at: usize, w: u16) {
        self.bytes[at..at + 2].copy_from_slice(&w.to_le_bytes());
    }
}

/// What the screens' letters are: the font's characters, `?` for the
/// others.
fn letters(text: &str) -> Vec<u8> {
    text.chars()
        .map(|c| {
            let n = c as usize;
            if (ITEM_FIRST_CHAR..ITEM_FIRST_CHAR + ITEM_CHARS).contains(&n) {
                n as u8
            } else {
                b'?'
            }
        })
        .collect()
}

/// The inks a menu writes in: the four of the text screens and the ones its
/// colours add, by System colour.
#[derive(Debug, Clone)]
struct Inks {
    of: BTreeMap<i32, u8>,
}

impl Inks {
    fn new() -> Inks {
        Inks { of: BASE_INKS.iter().copied().collect() }
    }

    fn get(&mut self, color: i32) -> Result<u8> {
        if let Some(&k) = self.of.get(&color) {
            return Ok(k);
        }
        let k = self.of.len();
        if k >= CM_INKS_MAX {
            return Err(Bad::answer(format!(
                "the custom menus write in more than {CM_INKS_MAX} System colours: the text layer has a palette each"
            )));
        }
        self.of.insert(color, k as u8);
        Ok(k as u8)
    }

    /// The colours past the first four, in palette order.
    fn extra(&self) -> Vec<i32> {
        let mut by: Vec<(u8, i32)> = self.of.iter().map(|(c, k)| (*k, *c)).collect();
        by.sort();
        by.into_iter().filter(|(k, _)| *k as usize >= CM_INKS_FIRST).map(|(_, c)| c).collect()
    }
}

struct Writer<'a> {
    ctx: &'a Context,
    blob: Blob,
    inks: Inks,
    strings: HashMap<Vec<u8>, u16>,
}

impl Writer<'_> {
    fn string(&mut self, text: &str) -> Result<u16> {
        let l = letters(text);
        if l.len() > 255 {
            return Err(Bad::answer(format!("{text:?} is longer than 255 letters")));
        }
        if let Some(&at) = self.strings.get(&l) {
            return Ok(at);
        }
        let at = self.blob.at();
        self.blob.bytes.push(l.len() as u8);
        self.blob.bytes.extend(&l);
        self.strings.insert(l, at);
        Ok(at)
    }

    fn slot(&self, variable: i32) -> Result<u16> {
        self.ctx
            .variables
            .get(&variable)
            .map(|s| (*s * 2) as u16)
            .ok_or_else(|| Bad::answer(format!("variable {variable} has no slot in the cartridge")))
    }

    fn cond(&mut self, c: &Cond) -> Result<()> {
        let (kind, a, b): (u8, u16, u16) = match c {
            Cond::Always => (COND_ALWAYS, 0, 0),
            Cond::Switch(n) => (COND_SWITCH, (*n >> 3) as u16, 1 << (*n & 7)),
            Cond::VariableAtLeast(v, at) => (COND_VARIABLE, self.slot(*v)?, *at as i16 as u16),
            Cond::Item(i) => (COND_ITEM, *i as u16, 0),
            Cond::Actor(a) => (COND_ACTOR, *a as u16, 0),
        };
        self.blob.bytes.push(kind);
        self.blob.word(a);
        self.blob.word(b);
        Ok(())
    }

    /// A list of lines, each on `row0 + 2k`: the count, and each line's
    /// row, cell, ink, way, length and bytes.
    fn lines(&mut self, lines: &[Line], row0: usize) -> Result<u16> {
        let mut encoded = Vec::new();
        for (k, line) in lines.iter().enumerate() {
            let ink = self.inks.get(line.color)?;
            let escaped = line.pieces.iter().any(|p| matches!(p, Piece::Variable(_)));
            let mut bytes = Vec::new();
            for p in &line.pieces {
                match p {
                    Piece::Text(t) => bytes.extend(letters(t)),
                    Piece::Variable(v) => {
                        bytes.push(ESCAPE_VARIABLE);
                        bytes.extend(self.slot(*v)?.to_le_bytes());
                    }
                }
            }
            if bytes.len() > 255 {
                return Err(Bad::answer("a line of a custom menu is longer than 255 bytes"));
            }
            encoded.push((row0 + 2 * k, line.col, ink, escaped, bytes));
        }
        let at = self.blob.at();
        self.blob.bytes.push(encoded.len() as u8);
        for (row, col, ink, escaped, bytes) in encoded {
            self.blob.bytes.extend([row as u8, col as u8, ink, if escaped { LINE_ESCAPED } else { LINE_PLAIN }]);
            self.blob.bytes.push(bytes.len() as u8);
            self.blob.bytes.extend(bytes);
        }
        Ok(at)
    }

    fn cap(&self, cap: &Cap) -> Result<(u8, u16)> {
        Ok(match cap {
            Cap::Fixed(n) => (CAP_FIXED, *n as u16),
            Cap::Variable(v) => (CAP_VARIABLE, self.slot(*v)?),
            Cap::None => (CAP_NONE, 0),
        })
    }

    fn plain(&self, text: &str, color: i32, col: usize) -> Line {
        Line { col, color, pieces: vec![Piece::Text(text.to_string())] }
    }
}

/// A page's arrangement of windows: below the header, the windows its
/// body takes.
fn page_windows(rows_on_top: Option<usize>, text_below: bool) -> Vec<Rect> {
    let mut out = vec![CM_HEADER];
    match rows_on_top {
        None => out.push((0, CM_BODY_Y, WIDTH, HEIGHT - CM_BODY_Y)),
        // Without a text below, the table's window takes the rest.
        Some(_) if !text_below => out.push((0, CM_BODY_Y, WIDTH, HEIGHT - CM_BODY_Y)),
        Some(rows) => {
            let h = 16 + 16 * rows;
            out.push((0, CM_BODY_Y, WIDTH, h));
            if CM_BODY_Y + h < HEIGHT {
                out.push((0, CM_BODY_Y + h, WIDTH, HEIGHT - CM_BODY_Y - h));
            }
        }
    }
    out
}

/// The first cell row of the lines of a window that starts at `y`.
fn first_row(y: usize) -> usize {
    (y + 8) / CELL
}

/// How many lines fit in a window that starts at `y` and ends at the
/// bottom of the screen.
fn lines_in(y: usize) -> usize {
    (HEIGHT - 8 - (y + 8)) / 16
}

/// Everything the cartridge carries of its custom menus.
pub struct Built {
    pub menus: Vec<Menu>,
    pub blob: Vec<u8>,
    /// The offset of each menu's record in the blob.
    pub offsets: Vec<u16>,
    /// The arrangements of windows: the subjects' first, and each page's.
    pub layouts: Vec<Vec<Rect>>,
    pub borders: borders::Borders,
    /// The palettes of the inks past the text screens' four.
    pub inks: Vec<Vec<Color>>,
    /// Each portrait: its tiles, row by row, and its palette.
    pub portraits: Vec<(Vec<Indices>, Vec<Color>)>,
    pub says: Vec<String>,
}

/// The windows of the arrangement `rects`, with the bar on each tab for the
/// subjects'.
fn layout_screen(skin: &Skin, rects: &[Rect], tabs: bool) -> Screen {
    let draw = |bar: Option<usize>| {
        let mut out = cells::layer();
        for &(x, y, w, h) in rects {
            cells::paste(&mut out, &skin.window(w, h), x as i64, y as i64);
        }
        if let Some(t) = bar {
            let y = (CM_TAB_ROW0 + 2 * t) * CELL;
            cells::paste(&mut out, &skin.cursor(CM_BAR_WIDTH, 2 * CELL), CM_BAR_X as i64, y as i64);
        }
        out
    };
    Screen {
        background: draw(None),
        bars: if tabs {
            (0..CM_TABS_MAX).map(|t| (draw(Some(t)), CM_TAB_ROW0 + 2 * t, 2)).collect()
        } else {
            Vec::new()
        },
    }
}

/// A portrait: the part of the picture `crop` says, brought down to the
/// portrait's size and to fifteen colours —the ones that show the least go,
/// Adeleine's `merge_least_visible`—, in 4bpp tiles. Black is the
/// transparent index, as on the faces: the window behind is black.
fn portrait(game: &Game, name: &str, crop: [usize; 4]) -> Result<(Vec<Indices>, Vec<Color>)> {
    let path = game.game_dir.join("Picture").join(format!("{name}.png"));
    let whole = picture::read_rm2k(&path)?;
    let [x, y, mut w, mut h] = crop;
    if w == 0 || h == 0 {
        w = whole.width - x;
        h = whole.height - y;
    }
    let part = whole.crop(x as i64, y as i64, w, h);
    let small = part.resized(CM_PORTRAIT_W, CM_PORTRAIT_H, FilterType::Lanczos3);
    let color_at = |px: usize, py: usize| -> Color {
        let p = small.get(px as i64, py as i64);
        if p[3] == 0 {
            BLACK
        } else {
            rgb15(p)
        }
    };
    let mut used = Counts::default();
    for py in 0..CM_PORTRAIT_H {
        for px in 0..CM_PORTRAIT_W {
            let c = color_at(px, py);
            if c != BLACK {
                used.add(c, 1);
            }
        }
    }
    let counts = used.in_order();
    let (palette, mapping): (Vec<Color>, HashMap<Color, Color>) = if counts.len() > 15 {
        let merged = adeleine::merge_least_visible(&counts, 15)?;
        let mut palette = merged.mapping.clone();
        palette.sort();
        palette.dedup();
        (palette, counts.iter().map(|(c, _)| *c).zip(merged.mapping).collect())
    } else {
        (used.by_use(), counts.iter().map(|(c, _)| (*c, *c)).collect())
    };
    let mut colors = vec![BLACK];
    colors.extend(palette);
    let index = |c: Color| -> u8 {
        if c == BLACK {
            return 0;
        }
        let target = mapping[&c];
        colors.iter().position(|p| *p == target).expect("in the palette") as u8
    };
    let mut tiles = Vec::new();
    for ty in 0..CM_PORTRAIT_ROWS {
        for tx in 0..CM_PORTRAIT_COLS {
            let mut tile: Indices = [[0; CELL]; CELL];
            for (yy, line) in tile.iter_mut().enumerate() {
                for (xx, v) in line.iter_mut().enumerate() {
                    *v = index(color_at(tx * CELL + xx, ty * CELL + yy));
                }
            }
            tiles.push(tile);
        }
    }
    colors.resize(16, BLACK);
    Ok((tiles, colors))
}

/// The cartridge's custom menus, written down.
pub fn build(game: &Game, skin: &Skin, menus: Vec<Menu>, ctx: &Context) -> Result<Built> {
    let mut w = Writer { ctx, blob: Blob::default(), inks: Inks::new(), strings: HashMap::new() };
    let mut layouts: Vec<Vec<Rect>> = vec![vec![
        CM_HEADER,
        CM_PORTRAIT_WINDOW,
        CM_INFO_WINDOW,
        CM_TABS_WINDOW,
        CM_HELP_WINDOW,
    ]];
    let layout_of = |rects: Vec<Rect>, layouts: &mut Vec<Vec<Rect>>| -> u8 {
        match layouts.iter().position(|l| *l == rects) {
            Some(k) => k as u8,
            None => {
                layouts.push(rects);
                (layouts.len() - 1) as u8
            }
        }
    };
    let mut portraits: Vec<(Vec<Indices>, Vec<Color>)> = Vec::new();
    let mut portrait_of: BTreeMap<(String, [usize; 4]), u8> = BTreeMap::new();
    let mut says = Vec::new();

    // The root: the level term, and each menu's offset, patched at the end.
    let term = game.term("lvl_short")?;
    let level_at = w.blob.at() as usize;
    w.blob.word(0);
    w.blob.bytes.push(menus.len() as u8);
    let offsets_at = w.blob.bytes.len();
    for _ in &menus {
        w.blob.word(0);
    }
    let level = w.string(&term.chars().take(2).collect::<String>())?;
    w.blob.patch(level_at, level);

    let mut offsets = Vec::new();
    let mut pages_n = 0;
    for menu in &menus {
        // The tables first: a page names one by its offset.
        let mut table_at: BTreeMap<String, u16> = BTreeMap::new();
        for (key, table) in &menu.tables {
            let heading = vec![
                w.plain(&table.columns.0, 1, CM_TEXT_COL),
                w.plain(&table.columns.1, 1, CM_VALUE_COL - 4),
            ];
            // The two headings go on the same row.
            let heading_at = w.blob.at();
            w.blob.bytes.push(2);
            for line in &heading {
                let ink = w.inks.get(line.color)?;
                let Piece::Text(t) = &line.pieces[0] else { unreachable!() };
                let l = letters(t);
                w.blob.bytes.extend([first_row(CM_BODY_Y) as u8, line.col as u8, ink, LINE_PLAIN, l.len() as u8]);
                w.blob.bytes.extend(l);
            }
            let mut special = Vec::new();
            for (value, text) in &table.special {
                let s = w.string(text)?;
                let taken = game.font.width(text);
                // Ending with the cap's cell, like the numbers.
                let col = (CM_CAP_COL + 1).saturating_sub(taken.div_ceil(CELL));
                special.push((*value, s, col));
            }
            let mut sheets = Vec::new();
            for sheet in &table.sheets {
                let ink = w.inks.get(sheet.color)?;
                let prefix = format!("{} - ", table.title);
                let lead = letters(&prefix);
                let name_col = CM_TEXT_COL + (SCR_TEXT_X + game.font.width(&prefix)).div_ceil(CELL);
                let header_at = w.blob.at();
                w.blob.bytes.push(2);
                w.blob.bytes.extend([CM_HEADER_ROW as u8, CM_TEXT_COL as u8, 0, LINE_PLAIN, lead.len() as u8]);
                w.blob.bytes.extend(&lead);
                let title = letters(&sheet.title);
                w.blob.bytes.extend([CM_HEADER_ROW as u8, name_col as u8, ink, LINE_PLAIN, title.len() as u8]);
                w.blob.bytes.extend(&title);
                let mut rows = Vec::new();
                for (name, variable, cap) in &sheet.rows {
                    let s = w.string(name)?;
                    let v = w.slot(*variable)?;
                    let (kind, c) = w.cap(cap)?;
                    rows.push((s, v, kind, c));
                }
                let at = w.blob.at();
                w.blob.word(header_at);
                w.blob.bytes.push(rows.len() as u8);
                for (s, v, kind, c) in rows {
                    w.blob.word(s);
                    w.blob.word(v);
                    w.blob.bytes.push(kind);
                    w.blob.word(c);
                }
                sheets.push(at);
            }
            let at = w.blob.at();
            w.blob.bytes.push(sheets.len() as u8);
            w.blob.word(heading_at);
            w.blob.bytes.push(special.len() as u8);
            for (value, s, col) in special {
                w.blob.word(value as u16);
                w.blob.word(s);
                w.blob.bytes.push(col as u8);
            }
            for s in sheets {
                w.blob.word(s);
            }
            table_at.insert(key.clone(), at);
        }

        let mut subject_at = Vec::new();
        for subject in &menu.subjects {
            let mut tabs = Vec::new();
            for tab in &subject.tabs {
                let label = w.string(&tab.label)?;
                let help = if tab.help.is_empty() { 0 } else { w.lines(&tab.help, CM_HELP_ROW0)? };
                let mut pages = Vec::new();
                for page in &tab.pages {
                    let header = w.plain(&format!("{} - {}", subject.name, tab.label), 0, CM_TEXT_COL);
                    let header = w.lines(&[header], CM_HEADER_ROW)?;
                    let (kind, rows_on_top, extra) = match &page.body {
                        Body::Text => (PAGE_TEXT, None, 0),
                        Body::Table(key) => {
                            let rows = menu.tables[key].sheets.iter().map(|s| s.rows.len()).max().unwrap_or(0);
                            (PAGE_TABLE, Some(rows + 1), table_at[key])
                        }
                        Body::Counters(counters) => {
                            let mut encoded = Vec::new();
                            for (label, variable, cap) in counters {
                                let (kind, c) = w.cap(cap)?;
                                encoded.push((w.string(label)?, w.slot(*variable)?, kind, c));
                            }
                            let at = w.blob.at();
                            w.blob.bytes.push(encoded.len() as u8);
                            for (s, v, kind, c) in encoded {
                                w.blob.word(s);
                                w.blob.word(v);
                                w.blob.bytes.push(kind);
                                w.blob.word(c);
                            }
                            (PAGE_COUNTERS, Some(counters.len()), at)
                        }
                    };
                    let rects = page_windows(rows_on_top, !page.lines.is_empty());
                    let body_y = match rows_on_top {
                        None => CM_BODY_Y,
                        Some(rows) => CM_BODY_Y + 16 + 16 * rows,
                    };
                    let visible = if body_y >= HEIGHT { 0 } else { lines_in(body_y) };
                    if page.lines.len() > visible && kind != PAGE_TEXT {
                        return Err(Bad::answer(format!(
                            "menu {:?}, {}, {}: the text under the {} takes {} lines and {visible} fit",
                            menu.name,
                            subject.name,
                            tab.label,
                            if kind == PAGE_TABLE { "table" } else { "counters" },
                            page.lines.len()
                        )));
                    }
                    let row0 = first_row(body_y);
                    let body = w.lines(&page.lines, row0)?;
                    let layout = layout_of(rects, &mut layouts);
                    let before = match page.before {
                        None => 0xFF,
                        Some(c) => *ctx.before_bodies.get(&c).ok_or_else(|| {
                            Bad::answer(format!(
                                "menu {:?}: common event {c}, which runs before a page, was not compiled",
                                menu.name
                            ))
                        })?,
                    };
                    let at = w.blob.at();
                    w.cond(&page.when)?;
                    w.blob.bytes.extend([before, kind, layout]);
                    w.blob.word(header);
                    w.blob.word(body);
                    w.blob.bytes.extend([row0 as u8, visible as u8]);
                    w.blob.word(extra);
                    pages.push(at);
                    pages_n += 1;
                }
                let list = w.blob.at();
                w.blob.bytes.push(pages.len() as u8);
                for p in pages {
                    w.blob.word(p);
                }
                tabs.push((label, help, list));
            }
            let portrait = match &subject.portrait {
                None => 0xFF,
                Some((name, crop)) => match portrait_of.get(&(name.clone(), *crop)) {
                    Some(&k) => k,
                    None => {
                        portraits.push(portrait(game, name, *crop)?);
                        let k = (portraits.len() - 1) as u8;
                        portrait_of.insert((name.clone(), *crop), k);
                        k
                    }
                },
            };
            let name = w.string(&subject.name)?;
            let class = if subject.class.is_empty() { 0 } else { w.string(&subject.class)? };
            let at = w.blob.at();
            match subject.actor {
                Some(a) => w.cond(&Cond::Actor(a))?,
                None => w.cond(&Cond::Always)?,
            }
            w.cond(&subject.when)?;
            w.blob.bytes.push(subject.actor.map_or(0xFF, |a| a as u8));
            w.blob.bytes.push(portrait);
            w.blob.word(name);
            w.blob.word(class);
            w.blob.bytes.push(tabs.len() as u8);
            for (label, help, list) in tabs {
                w.blob.word(label);
                w.blob.word(help);
                w.blob.word(list);
            }
            subject_at.push(at);
        }
        let title = w.string(&menu.title)?;
        let at = w.blob.at();
        w.cond(&menu.visible)?;
        w.blob.word(title);
        w.blob.bytes.push(subject_at.len() as u8);
        for s in subject_at {
            w.blob.word(s);
        }
        offsets.push(at);
    }
    for (k, at) in offsets.iter().enumerate() {
        w.blob.patch(offsets_at + 2 * k, *at);
    }
    if w.blob.bytes.len() > 0x8000 {
        return Err(Bad::answer(format!(
            "the custom menus take {} bytes and their block has to fit in half a bank",
            w.blob.bytes.len()
        )));
    }

    let screens: Vec<Screen> = layouts
        .iter()
        .enumerate()
        .map(|(k, rects)| layout_screen(skin, rects, k == CM_LAYOUT_SUBJECTS))
        .collect();
    let borders = borders::borders(&screens, 0, CM_BORDER_CGRAM, CM_BORDER_CGRAM_END)?;
    let mut inks = Vec::new();
    for color in w.inks.extra() {
        let (rows, shadow) = ink_colors(skin, color)?;
        let mut palette = vec![BLACK];
        palette.extend(rows);
        palette.push(shadow);
        palette.resize(16, BLACK);
        debug_assert_eq!(palette[INK_ROW_FIRST as usize], palette[1]);
        inks.push(palette);
    }
    says.push(format!(
        "  custom menus: {} ({} pages), {} B of data, {} arrangement(s) of windows in {} tiles and {} \
         colours, {} portrait(s), {} ink(s) past the text screens' four",
        menus.iter().map(|m| format!("{:?}", m.name)).collect::<Vec<_>>().join(", "),
        pages_n,
        w.blob.bytes.len(),
        layouts.len(),
        borders.tiles.len(),
        borders.colors.len(),
        portraits.len(),
        inks.len()
    ));
    Ok(Built {
        menus,
        blob: w.blob.bytes,
        offsets,
        layouts,
        borders,
        inks,
        portraits,
        says,
    })
}

/// The geometry the runtime writes with, by name.
pub fn publish() -> Value {
    let mut m = Map::new();
    macro_rules! put {
        ($($name:ident),* $(,)?) => {
            $( m.insert(stringify!($name).to_string(), json!($name)); )*
        };
    }
    put!(
        CM_HEADER_ROW, CM_TEXT_COL, CM_INDEX_COL, CM_PORTRAIT_X, CM_PORTRAIT_Y, CM_PORTRAIT_COLS,
        CM_PORTRAIT_ROWS, CM_INFO_COL, CM_NAME_ROW, CM_CLASS_ROW, CM_LEVEL_ROW, CM_LEVEL_NUM_COL,
        CM_TAB_COL, CM_TAB_ROW0, CM_TABS_MAX, CM_HELP_ROW0, CM_VALUE_COL, CM_SLASH_COL, CM_CAP_COL,
        CM_COUNTER_COL, CM_BODY_ROW0, CM_TABLE_ROW0, CM_WHITE, CM_GRAY, CM_RED, CM_INKS_FIRST, CM_BORDER_CGRAM, CM_LAYOUT_SUBJECTS,
    );
    Value::Object(m)
}

/// The answer's part for the custom menus.
pub fn to_json(b: &Built) -> Value {
    json!({
        "labels": b.menus.iter().map(|m| m.label.clone()).collect::<Vec<_>>(),
        "blob": b.blob.iter().map(|x| format!("{x:02x}")).collect::<String>(),
        "offsets": b.offsets,
        "layouts": b.borders.maps.iter().map(|(map, _)| map.clone()).collect::<Vec<_>>(),
        "bars": b.borders.maps.first().map(|(_, bars)| bars.clone()).unwrap_or_default(),
        "tiles": crate::convert::tiles_json(&b.borders.tiles),
        "colors": crate::convert::colors_json(&b.borders.colors),
        "inks": b.inks,
        "portraits": b.portraits.iter().map(|(tiles, palette)| json!({
            "tiles": crate::convert::tiles_json(tiles),
            "palette": palette,
        })).collect::<Vec<_>>(),
        "layout": publish(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_page_without_a_body_window_on_top_takes_the_whole_screen() {
        assert_eq!(page_windows(None, true), vec![CM_HEADER, (0, 32, 256, 192)]);
        assert_eq!(page_windows(Some(9), false), vec![CM_HEADER, (0, 32, 256, 192)]);
        assert_eq!(lines_in(CM_BODY_Y), 11);
        assert_eq!(first_row(CM_BODY_Y), 5);
    }

    #[test]
    fn a_table_of_nine_rows_leaves_a_line_below() {
        let w = page_windows(Some(9), true);
        assert_eq!(w[1], (0, 32, 256, 160));
        assert_eq!(w[2], (0, 192, 256, 32));
        assert_eq!(lines_in(192), 1);
    }
}
