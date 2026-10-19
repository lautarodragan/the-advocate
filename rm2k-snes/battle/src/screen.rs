//! The battle's text screen: where each thing goes on it, and the texts
//! the console composes on it.
//!
//! It draws nothing: the console composes it with the text screens'
//! variable-width font, on the same grid of 32 by 28 cells the equipment
//! and shop screens use —a write is a run of letters that starts at a
//! cell—. What goes from here is the geometry —in cells; the caller turns
//! it into what its tables need— and the texts, already cut to what fits.
//!
//! **The words are RM2k's**, all from the database, none made up. What is
//! not RM2k's is declared where it is: escaping is a fifth command and not
//! the party's menu, the commands stay on the left without sliding, and
//! some lines are cut shorter than the original's.

use crate::db::Db;
use crate::fail::{Bad, Result};
use rm2k_snes_text::font;
use serde_json::{json, Map, Value};

// The battle is RM2k's: the scene on top with nothing written over it, and
// every window **in the band below it**, on the 96 lines the 128 of the
// scene leave —RM2k's 80 of 240—, each with the System's frame and its
// cursor the System's bar. A line of text is two cell rows, and the band's
// go on the **odd** rows 17 to 25: five lines of 16, with the frame's eight
// lines above the first and below the last. The description of an item or
// a skill is the one thing that goes up, in a window of
// [`BA_HELP_SCENE_ROWS`] tile rows the console takes from the scene while a
// list is open, which is RM2k's `Window_Help`.
//
// The windows are pictures, which the screens stage draws with the System
// —see `battle_layers` in `rm2k-snes-screens`— from the rectangles here;
// the text goes in cells, inside them. Until 2026-10-04 the enemies' names
// went over the scene, with the party's lines and two of commands and
// messages under it, and later that day the band had no windows.

/// A window or a bar, in screen pixels: x, y, width, height.
pub type Rect = (usize, usize, usize, usize);

/// The first line of the band, and how many it has.
pub const BA_BAND_ROW0: i64 = 17;
pub const BA_BAND_LINES: i64 = 5;
/// The band's top, in pixels, and its height: the scene's bottom.
pub const BA_BAND_Y: usize = 128;
pub const BA_BAND_HEIGHT: usize = 96;

/// The two windows of choosing a command, RM2k's after its slide: the
/// party's status on the left and the commands on the right. **The
/// command window starts at 178**, which leaves the commands 63 pixels
/// —"AgentTrain" is 59 with A Blurred Line's font— and the party's line
/// 169 to the frame, which in the System this was drawn with is its two
/// outer pixels.
pub const BA_PARTY_WINDOW: Rect = (0, BA_BAND_Y, 178, BA_BAND_HEIGHT);
pub const BA_COMMAND_WINDOW: Rect = (178, BA_BAND_Y, 78, BA_BAND_HEIGHT);
/// The enemies to attack, over the party's window —RM2k's target window
/// covers the status window's names; here the party's line is too tight
/// for half a window, so it covers it all—.
pub const BA_TARGET_WINDOW: Rect = BA_PARTY_WINDOW;
/// The item and skill lists, the battle's message, a troop page's and the
/// victory: one window as wide as the screen.
pub const BA_WIDE_WINDOW: Rect = (0, BA_BAND_Y, 256, BA_BAND_HEIGHT);
/// And the description, on top.
pub const BA_HELP_WINDOW: Rect = (0, 0, 256, 32);

/// The bars, per line: x and width, and they take the line's 16 pixels.
pub const BA_PARTY_BAR: (usize, usize) = (4, 170);
pub const BA_COMMAND_BAR: (usize, usize) = (182, 70);
pub const BA_TARGET_BAR: (usize, usize) = BA_PARTY_BAR;
/// The lists' bar, per column.
pub const BA_LIST_BARS: [(usize, usize); 2] = [(4, 124), (132, 120)];

/// The window layouts, in the order the cartridge numbers them, and which
/// windows each draws, in order: the later one covers.
pub const BA_LAYOUT_COMMAND: i64 = 0;
pub const BA_LAYOUT_TARGET: i64 = 1;
pub const BA_LAYOUT_WIDE: i64 = 2;
pub fn layout_windows(layout: i64) -> Vec<Rect> {
    match layout {
        BA_LAYOUT_COMMAND => vec![BA_PARTY_WINDOW, BA_COMMAND_WINDOW],
        BA_LAYOUT_TARGET => vec![BA_PARTY_WINDOW, BA_COMMAND_WINDOW, BA_TARGET_WINDOW],
        _ => vec![BA_WIDE_WINDOW],
    }
}
/// A layout's bars: two sets, A and B, each a list of rectangles. With
/// the command windows, A is the party's lines —or the enemies'— and B
/// the commands; with the wide one, A is the list's places, by rows.
pub fn layout_bars(layout: i64) -> [Vec<Rect>; 2] {
    let line = |k: i64| BA_BAND_Y + 8 + 16 * k as usize;
    let at = |(x, w): (usize, usize), k: i64| (x, line(k), w, 16);
    let commands: Vec<Rect> = (0..BA_BAND_LINES).map(|k| at(BA_COMMAND_BAR, k)).collect();
    match layout {
        BA_LAYOUT_COMMAND => [(0..4).map(|k| at(BA_PARTY_BAR, k)).collect(), commands],
        BA_LAYOUT_TARGET => [
            (0..BA_BAND_LINES).map(|k| at(BA_TARGET_BAR, k)).collect(),
            commands,
        ],
        _ => [
            (0..2 * BA_BAND_LINES)
                .map(|p| at(BA_LIST_BARS[(p % 2) as usize], p / 2))
                .collect(),
            vec![],
        ],
    }
}
/// How many bars a set has at most: the list's ten.
pub const BA_BARS_MAX: i64 = 2 * BA_BAND_LINES;

/// The enemies to attack: only the living ones that show, in troop order,
/// five at a time —the window scrolls to keep the cursor in view—.
pub const BA_ENEMY_ROW0: i64 = BA_BAND_ROW0;
pub const BA_TARGET_ROWS: i64 = BA_BAND_LINES;
pub const BA_ENEMY_NAME_COL: i64 = 1;
pub const BA_ENEMY_NAME_WIDTH: usize = 20;

/// The commands, a column in their window, [`BA_COMMAND_CELLS`] cells
/// wide.
pub const BA_COMMAND_ROW0: i64 = BA_BAND_ROW0;
pub const BA_COMMAND_COL: i64 = 23;
pub const BA_COMMAND_CELLS: usize = 8;
/// How many letters of a command the cartridge keeps.
pub const BA_COMMAND_WIDTH: usize = 10;

/// The commands, in the original's order —Attack, the skill, Defend, Use
/// Item, as a capture of the real game shows them— and Escape fifth,
/// **only in a battle that can be escaped from**. In RM2k escaping is the
/// party's, from the menu before the commands, which this port does not
/// have: it is a command of RPG Maker 2000 PLUS, and choosing it does what
/// RM2k's menu does —see `ba_flee_failed` in the runtime—.
pub const BA_COMMAND_ATTACK: i64 = 0;
pub const BA_COMMAND_SKILL: i64 = 1;
pub const BA_COMMAND_DEFEND: i64 = 2;
pub const BA_COMMAND_USE: i64 = 3;
pub const BA_COMMAND_ESCAPE: i64 = 4;

/// Per command, which term names it, one per line.
pub const BA_COMMANDS: [&str; 5] = ["attack", "skill", "defend", "use", "escape"];

/// The commands the console grays out always: none since the skill was
/// done. It stays because it is where the next half-done one would go.
pub const BA_COMMAND_UNDONE: [i64; 0] = [];

/// The party, one line per actor: RM2k's `Window_BattleStatus` —`Talan
/// Normal  HP 49/ 49  SP 49`—. The bar marks who is giving commands, or
/// whom an item goes to. The state is the database's `normal_status`, or
/// the dead state's name for a fallen one: the actors have no other states
/// in battle —only enemies get them, see `Held` in `simulate`—.
///
/// The HP and SP are **one run each**, from their cell: the term, the
/// number in three places and, in the HP, the slash and the maximum. That
/// is 54 pixels with A Blurred Line's font, which ends before the SP's
/// cell, and the SP's 30 end before the window's frame;
/// [`check_party_line`] says it when a font does not fit.
pub const BA_PARTY_ROW0: i64 = BA_BAND_ROW0;
pub const BA_NAME_COL: i64 = 1;
pub const BA_NAME_WIDTH: usize = 5;
pub const BA_STATE_COL: i64 = 6;
pub const BA_STATE_WIDTH: usize = 5;
pub const BA_HP_COL: i64 = 11;
pub const BA_SP_COL: i64 = 18;

/// The battle's message —"X attacks", the damage, the escape—, a troop
/// page's `ShowMessage` and the victory, in RM2k's message window: the
/// wide window, from its first line down, up to four. A line is **thirty**
/// cells wide, from column 1 to the frame: the converter reflows the
/// pages' boxes for this window, as it does the map's for theirs, and the
/// console cuts at the edge whatever still does not fit —both measure the
/// line in pixels, with the font's advances—.
pub const BA_MSG_ROW1: i64 = BA_BAND_ROW0;
pub const BA_MSG_ROW2: i64 = BA_BAND_ROW0 + 2;
pub const BA_MSG_LINES: i64 = 4;
pub const BA_PAGE_MSG_ROW0: i64 = BA_BAND_ROW0;
pub const BA_PAGE_MSG_COL: i64 = 1;
pub const BA_PAGE_MSG_WIDTH: usize = 30;

/// The description of the item or the skill under the cursor, in its
/// window on top: one line, on row 1, inside the frame. The window is four
/// tile rows, 32 lines, which is RM2k's 32 of 240.
pub const BA_HELP_ROW: i64 = 1;
pub const BA_HELP_COL: i64 = 1;
pub const BA_HELP_WIDTH: usize = 30;
pub const BA_HELP_SCENE_ROWS: i64 = 4;

/// The skill list: two columns, by rows, with the name and the cost
/// —`Memorize  -  5`—, five rows that scroll. **The description goes whole
/// in the cartridge and the console cuts it at [`BA_HELP_WIDTH`] cells**,
/// in pixels: the original writes it whole with a smaller font, and what
/// does not fit is declared debt. Until 2026-10-04 it was cut at
/// thirty-one letters, `BA_SKILL_DESC_WIDTH`, from when a letter took a
/// cell.
pub const BA_SKILL_DESC_ROW: i64 = BA_HELP_ROW;
pub const BA_SKILL_DESC_COL: i64 = BA_HELP_COL;
pub const BA_SKILL_ROW0: i64 = BA_BAND_ROW0;
pub const BA_SKILL_ROWS: i64 = BA_BAND_LINES;
pub const BA_SKILL_COLUMNS: i64 = 2;
/// From one column to the next.
pub const BA_SKILL_COLUMN_DX: i64 = 16;
/// Relative to the start of the column.
pub const BA_SKILL_NAME_COL: i64 = 1;
pub const BA_SKILL_NAME_WIDTH: usize = 11;
/// **The cartridge keeps a skill's name whole**, and an enemy's: the
/// console cuts them at their cells, in pixels, with the font's advances.
/// What made it keep fewer was a row's record in the text layer
/// —`TL_RECORD` in `text_layer.s`, 56 bytes—, which has to hold both
/// columns of the skill list: since 2026-10-04 the list writes each name
/// **by reference** (`TL_BY_REF`), a run of six bytes however long the name
/// is, and the row is its length and per column the name's, the dash's and
/// the cost's. The item list writes its names the same way.
///
/// Until then it kept thirteen letters, which is what the record left with
/// the letters copied, and before 2026-10-03 eleven, from when a letter
/// took a cell: 26 of A Blurred Line's battle skills came out cut by
/// letters and not by pixels, and its fourteen longest enemies too.
const TL_RECORD: usize = 56;
// The leading 1 is the record's length byte and `TL_RECORD - 1` is the bound
// the runtime checks a run against (`cmp #(TL_RECORD - 1)` in
// `text_layer.s`): clippy's simplification would hide both.
#[allow(clippy::int_plus_one)]
const _: () = assert!(
    1 + 2 * ((3 + 3) + (3 + 1) + (3 + 2)) <= TL_RECORD - 1,
    "a row of the skill list does not fit in its record"
);
/// The party's line: name, state, the HP's run with "HP" copied and seven
/// places, the SP's with "SP" and three, and the command on its line.
// Written as the runtime counts it, as the one above.
#[allow(clippy::int_plus_one)]
const _: () = assert!(
    1 + (3 + 3) + (3 + 3) + (3 + 2 + 7) + (3 + 2 + 3) + (3 + 3) <= TL_RECORD - 1,
    "a line of the party and the commands does not fit in its record"
);
pub const BA_SKILL_DASH_COL: i64 = 12;
/// **Two digits and not three**, which is what lets the two columns fit in
/// the window. No cost the battle offers reaches 100: see `skill_usable`.
pub const BA_SKILL_COST_COL: i64 = 13;
pub const BA_SKILL_COST_DIGITS: i64 = 2;

/// The item list, the skill list's twin —`Potion  : 99`—: the same two
/// columns and five rows, the colon where the dash goes and the count where
/// the cost.
pub const BA_ITEM_ROW0: i64 = BA_BAND_ROW0;
pub const BA_ITEM_ROWS: i64 = BA_BAND_LINES;
pub const BA_ITEM_NAME_WIDTH: usize = BA_SKILL_NAME_WIDTH;
pub const BA_ITEM_COUNT_COL: i64 = BA_SKILL_COST_COL;

/// How many lines the victory term may take: the first page is the term
/// and the experience, in the window's four.
pub const BA_VICTORY_TERM_MAX: usize = 2;

/// The party's line, measured with the game's font: the HP's run has to
/// end before the SP's cell, and the SP's before the window's frame, its
/// last two pixels. The numbers are three places of the font's digit.
/// `None` if it fits; if not, what does not.
pub fn check_party_line(font: &rm2k_snes_text::font::Font, hp: &str, sp: &str) -> Option<String> {
    let digits = 3 * font.advance('0');
    let hp_run = font.width(hp) + digits + font.advance('/') + digits;
    let sp_run = font.width(sp) + digits;
    let x = |col: i64| col as usize * 8 + 1;
    let mut bad = Vec::new();
    if x(BA_HP_COL) + hp_run > x(BA_SP_COL) {
        bad.push(format!("the HP ({hp_run} pixels) runs into the SP's cell"));
    }
    let edge = BA_PARTY_WINDOW.0 + BA_PARTY_WINDOW.2 - 2;
    if x(BA_SP_COL) + sp_run > edge {
        bad.push(format!(
            "the SP ({sp_run} pixels) runs into the window's frame"
        ));
    }
    (!bad.is_empty()).then(|| bad.join("; "))
}

/// What the text screens' font can write: the characters it has, a letter
/// it lacks as its plain ASCII stand-in —see `rm2k_snes_text::plain`—, a
/// '?' instead of the others, and cut to `width`. It is the screens' rule,
/// over the font's range.
pub fn item_text(text: &str, width: usize) -> String {
    let first = font::FIRST as usize;
    rm2k_snes_text::plain::plain_text(text)
        .0
        .chars()
        .map(|c| {
            if (first..first + font::GLYPHS).contains(&(c as usize)) {
                c
            } else {
                '?'
            }
        })
        .take(width)
        .collect()
}

/// A text cut to `width` characters, as the console writes it —the
/// caller writes every text through [`item_text`], so which letters
/// survive is not this one's business—.
pub fn cut(text: &str, width: usize) -> String {
    text.chars().take(width).collect()
}

/// Python's `str.strip()`: the whitespace at both ends.
fn strip(text: &str) -> &str {
    text.trim_matches(|c: char| c.is_whitespace())
}

/// One of the commands as the screen writes it: the database's terms carry
/// leading spaces —" Escape"—, which would shift the text out of its
/// column, so it goes trimmed, and the console does not have to know how
/// to trim.
pub fn command_text(term: &str) -> String {
    cut(strip(term), BA_COMMAND_WIDTH)
}

/// The victory term split into the message window's lines, at the spaces:
/// measured in pixels with the game's `font` —[`BA_PAGE_MSG_WIDTH`] cells—
/// as the console cuts every other line of the battle, or without one in
/// characters, one per cell. **The leading spaces stay**: RM2k writes them.
/// Until 2026-10-04 it was always in characters, and A Blurred Line's "The
/// combat has resulted in victory!" took two lines where RM2k takes one.
pub fn victory_lines_in(
    term: &str,
    font: Option<&rm2k_snes_text::font::Font>,
) -> Result<Vec<String>> {
    match font {
        Some(font) => split_lines(term, &|s: &str| font.width(s), BA_PAGE_MSG_WIDTH * 8),
        None => victory_lines(term, BA_PAGE_MSG_WIDTH),
    }
}

/// The victory term split into lines of `width` characters, at the spaces.
pub fn victory_lines(term: &str, width: usize) -> Result<Vec<String>> {
    split_lines(term, &|s: &str| s.chars().count(), width)
}

fn split_lines(term: &str, measure: &dyn Fn(&str) -> usize, width: usize) -> Result<Vec<String>> {
    // The indent is the leading spaces, which is what RM2k's terms indent
    // with.
    let indent: String = term.chars().take_while(|&c| c == ' ').collect();
    let mut lines = Vec::new();
    let mut current = indent;
    for word in term.split_whitespace() {
        let empty = strip(&current).is_empty();
        let together = if empty {
            format!("{current}{word}")
        } else {
            format!("{current} {word}")
        };
        if measure(&together) <= width {
            current = together;
            continue;
        }
        if empty {
            return Err(Bad::answer(format!(
                "the victory term has a word longer than the line: {word:?}"
            )));
        }
        lines.push(current);
        current = word.to_string();
    }
    lines.push(current);
    Ok(lines)
}

/// RM2k's `GetExperienceGainedMessage` without placeholders: the number
/// stuck to the term.
pub fn exp_line(db: &Db, exp: i64) -> String {
    format!("{exp}{}", db.terms.exp_received)
}

/// `GetLevelUpMessage`: "<name> <level> <n><level_up>", which in the game
/// this was measured against is "Kersh LEVEL 21 achieved!".
pub fn level_line(db: &Db, name: &str, level: i64) -> String {
    format!("{name} {} {level}{}", db.terms.level, db.terms.level_up)
}

/// `GetLearningMessage`: the name stuck to the term.
pub fn skill_line(db: &Db, skill: &str) -> String {
    format!("{skill}{}", db.terms.skill_learned)
}

/// `GetGoldReceivedMessage` without placeholders: `gold_recieved_a`, a
/// space, the number stuck to `gold`, and `gold_recieved_b`.
pub fn gold_line(db: &Db, gold: i64) -> String {
    let t = &db.terms;
    format!(
        "{} {gold}{}{}",
        t.gold_recieved_a, t.gold, t.gold_recieved_b
    )
}

/// `GetItemReceivedMessage`: the name, as the cartridge carries it —cut to
/// the item screens' `name_width`—, stuck to `item_recieved`, with no space
/// in between: that one is RM2k3's.
pub fn item_line(db: &Db, name: &str, name_width: usize) -> String {
    format!("{}{}", item_text(name, name_width), db.terms.item_recieved)
}

/// What the battle writes after the name of a fallen one an item revived:
/// the dead state's `message_recovery`, which
/// `BattleMessage::GetStateRecoveryMessage` sticks to the name.
pub fn revived_text(db: &Db) -> Result<String> {
    db.states
        .get(&1)
        .map(|s| s.message_recovery.clone())
        .ok_or_else(|| Bad::answer("there is no state 1, the dead one, in the database"))
}

/// What a fallen actor's line says where the state goes: the dead state's
/// name, which is what `Window_BattleStatus` draws for the state an actor
/// at zero HP has.
pub fn dead_text(db: &Db) -> Result<String> {
    db.states
        .get(&1)
        .map(|s| s.name.clone())
        .ok_or_else(|| Bad::answer("there is no state 1, the dead one, in the database"))
}

/// The answer is no if a victory line does not fit in
/// [`BA_PAGE_MSG_WIDTH`]: the console builds them by joining pieces and
/// does not split them, so a long one would spill onto the line below.
/// Levels are measured with two digits, which is RM2k's cap.
pub fn check_victory(
    db: &Db,
    exp_max: i64,
    actors: &[String],
    skills: &[String],
    gold_max: i64,
    items: &[String],
    name_width: usize,
    font: Option<&rm2k_snes_text::font::Font>,
) -> Result<()> {
    let mut lines = vec![exp_line(db, exp_max), gold_line(db, gold_max)];
    lines.extend(items.iter().map(|n| item_line(db, n, name_width)));
    lines.extend(actors.iter().map(|n| level_line(db, n, 99)));
    lines.extend(skills.iter().map(|h| skill_line(db, h)));
    // In pixels with the game's font, which is how the console cuts; in
    // characters without one.
    let fits = |r: &String| match font {
        Some(f) => f.width(r) <= BA_PAGE_MSG_WIDTH * 8,
        None => r.chars().count() <= BA_PAGE_MSG_WIDTH,
    };
    let long: Vec<&String> = lines.iter().filter(|r| !fits(r)).collect();
    if !long.is_empty() {
        return Err(Bad::answer(format!(
            "these victory lines do not fit in the window's {} cells: {long:?}",
            BA_PAGE_MSG_WIDTH
        )));
    }
    Ok(())
}

/// The geometry, by the names the caller emits it with.
pub fn layout() -> Value {
    let mut out = Map::new();
    for (name, value) in [
        ("BA_BAND_ROW0", BA_BAND_ROW0),
        ("BA_BAND_LINES", BA_BAND_LINES),
        ("BA_LAYOUT_COMMAND", BA_LAYOUT_COMMAND),
        ("BA_LAYOUT_TARGET", BA_LAYOUT_TARGET),
        ("BA_LAYOUT_WIDE", BA_LAYOUT_WIDE),
        ("BA_BARS_MAX", BA_BARS_MAX),
        ("BA_ENEMY_ROW0", BA_ENEMY_ROW0),
        ("BA_TARGET_ROWS", BA_TARGET_ROWS),
        ("BA_ENEMY_NAME_COL", BA_ENEMY_NAME_COL),
        ("BA_ENEMY_NAME_WIDTH", BA_ENEMY_NAME_WIDTH as i64),
        ("BA_COMMAND_ROW0", BA_COMMAND_ROW0),
        ("BA_COMMAND_COL", BA_COMMAND_COL),
        ("BA_COMMAND_CELLS", BA_COMMAND_CELLS as i64),
        ("BA_COMMAND_WIDTH", BA_COMMAND_WIDTH as i64),
        ("BA_COMMAND_ATTACK", BA_COMMAND_ATTACK),
        ("BA_COMMAND_SKILL", BA_COMMAND_SKILL),
        ("BA_COMMAND_DEFEND", BA_COMMAND_DEFEND),
        ("BA_COMMAND_USE", BA_COMMAND_USE),
        ("BA_COMMAND_ESCAPE", BA_COMMAND_ESCAPE),
        ("BA_PARTY_ROW0", BA_PARTY_ROW0),
        ("BA_NAME_COL", BA_NAME_COL),
        ("BA_NAME_WIDTH", BA_NAME_WIDTH as i64),
        ("BA_STATE_COL", BA_STATE_COL),
        ("BA_STATE_WIDTH", BA_STATE_WIDTH as i64),
        ("BA_HP_COL", BA_HP_COL),
        ("BA_SP_COL", BA_SP_COL),
        ("BA_MSG_ROW1", BA_MSG_ROW1),
        ("BA_MSG_ROW2", BA_MSG_ROW2),
        ("BA_MSG_LINES", BA_MSG_LINES),
        ("BA_HELP_ROW", BA_HELP_ROW),
        ("BA_HELP_COL", BA_HELP_COL),
        ("BA_HELP_WIDTH", BA_HELP_WIDTH as i64),
        ("BA_HELP_SCENE_ROWS", BA_HELP_SCENE_ROWS),
        ("BA_SKILL_DESC_ROW", BA_SKILL_DESC_ROW),
        ("BA_SKILL_DESC_COL", BA_SKILL_DESC_COL),
        ("BA_SKILL_ROW0", BA_SKILL_ROW0),
        ("BA_SKILL_ROWS", BA_SKILL_ROWS),
        ("BA_SKILL_COLUMNS", BA_SKILL_COLUMNS),
        ("BA_SKILL_COLUMN_DX", BA_SKILL_COLUMN_DX),
        ("BA_SKILL_NAME_COL", BA_SKILL_NAME_COL),
        ("BA_SKILL_NAME_WIDTH", BA_SKILL_NAME_WIDTH as i64),
        ("BA_SKILL_DASH_COL", BA_SKILL_DASH_COL),
        ("BA_SKILL_COST_COL", BA_SKILL_COST_COL),
        ("BA_SKILL_COST_DIGITS", BA_SKILL_COST_DIGITS),
        ("BA_ITEM_ROW0", BA_ITEM_ROW0),
        ("BA_ITEM_ROWS", BA_ITEM_ROWS),
        ("BA_ITEM_NAME_WIDTH", BA_ITEM_NAME_WIDTH as i64),
        ("BA_ITEM_COUNT_COL", BA_ITEM_COUNT_COL),
        ("BA_PAGE_MSG_ROW0", BA_PAGE_MSG_ROW0),
        ("BA_PAGE_MSG_COL", BA_PAGE_MSG_COL),
        ("BA_PAGE_MSG_WIDTH", BA_PAGE_MSG_WIDTH as i64),
    ] {
        out.insert(name.into(), json!(value));
    }
    out.insert("BA_COMMANDS".into(), json!(BA_COMMANDS.to_vec()));
    out.insert(
        "BA_COMMAND_UNDONE".into(),
        json!(BA_COMMAND_UNDONE.to_vec()),
    );
    out.insert("BA_VICTORY_TERM_MAX".into(), json!(BA_VICTORY_TERM_MAX));
    out.insert("BATTLE_SEED".into(), json!(crate::simulate::BATTLE_SEED));
    out.insert("ACTIONS_MAX".into(), json!(crate::rules::ACTIONS_MAX));
    out.insert(
        "COMMAND_ATTACK".into(),
        json!(crate::simulate::COMMAND_ATTACK),
    );
    out.insert(
        "COMMAND_DEFEND".into(),
        json!(crate::simulate::COMMAND_DEFEND),
    );
    out.insert(
        "COMMAND_ESCAPE".into(),
        json!(crate::simulate::COMMAND_ESCAPE),
    );
    out.insert("COMMAND_ITEM".into(), json!(crate::simulate::COMMAND_ITEM));
    out.insert(
        "COMMAND_SKILL".into(),
        json!(crate::simulate::COMMAND_SKILL),
    );
    out.insert("VICTORY".into(), json!(crate::simulate::VICTORY));
    out.insert("ESCAPE".into(), json!(crate::simulate::ESCAPE));
    out.insert("DEFEAT".into(), json!(crate::simulate::DEFEAT));
    Value::Object(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_victory_term_splits_at_spaces_and_keeps_its_indent() {
        let lines = victory_lines(" The skirmish has ended in victory!", 31).unwrap();
        assert_eq!(lines, [" The skirmish has ended in", "victory!"]);
    }

    #[test]
    fn a_word_longer_than_the_line_is_a_no() {
        assert!(victory_lines("abcdefghij", 5).is_err());
    }

    #[test]
    fn commands_go_trimmed_and_cut() {
        assert_eq!(command_text(" Escape"), "Escape");
        assert_eq!(command_text("  A very long command "), "A very lon");
    }
}
