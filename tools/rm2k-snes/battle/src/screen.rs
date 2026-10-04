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
// every window **in the band below it**, on black —the 96 lines the 128 of
// the scene leave—. A line of text is two cell rows, and the band's go on
// the **odd** rows 17 to 25: five lines of 16, with ten lines of air above
// the first glyph and eight below the last. The description of an item or
// a skill is the one thing that goes up: on a band of
// [`BA_HELP_SCENE_ROWS`] tile rows the console takes from the scene while
// a list is open, which is RM2k's `Window_Help`.
//
// Until 2026-10-04 the enemies' names went over the scene, with the party's
// lines and two of commands and messages under it.

/// The first line of the band, and how many it has.
pub const BA_BAND_ROW0: i64 = 17;
pub const BA_BAND_LINES: i64 = 5;

/// The list of enemies to attack, on the left, which is RM2k's target
/// window: only the living ones that show, in troop order, five at a time
/// —the window scrolls to keep the cursor in view—. It covers the party's
/// names and states, as in RM2k, and their HP and SP stay.
pub const BA_ENEMY_ROW0: i64 = BA_BAND_ROW0;
pub const BA_TARGET_ROWS: i64 = BA_BAND_LINES;
/// Where every list's cursor goes, and an enemy's name.
pub const BA_CURSOR_COL: i64 = 0;
pub const BA_ENEMY_NAME_COL: i64 = 1;
pub const BA_ENEMY_NAME_WIDTH: usize = 19;

/// The commands, a column on the left —RM2k has them on the right, after
/// the party's window slides over; here they stay put, and on the left,
/// which is what taro chose—. The cursor in column 0 and the text from 1,
/// [`BA_COMMAND_CELLS`] cells wide: the widest of A Blurred Line's,
/// "AgentTrain", is 59 pixels with its font and spacing.
pub const BA_COMMAND_ROW0: i64 = BA_BAND_ROW0;
pub const BA_COMMAND_COL: i64 = 1;
pub const BA_COMMAND_CELLS: usize = 8;
/// How many letters of a command the cartridge keeps.
pub const BA_COMMAND_WIDTH: usize = 10;

/// The commands, in the original's order —Attack, the skill, Defend, Use
/// Item, as a capture of the real game shows them— and Escape fifth,
/// **only in a battle that can be escaped from**. In RM2k escaping is the
/// party's, from the menu before the commands, which this port does not
/// have: it is a command of RPG Maker 2000 PLUS, and choosing it does what
/// RM2k's menu does —see `ba_flee_all` in the runtime—.
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

/// The party, on the right of the commands: one line per actor, RM2k's
/// `Window_BattleStatus` —`Talan  Normal  HP 49/ 49  SP 49`—. The cursor
/// marks who is giving commands, or whom an item goes to. The state is the
/// database's `normal_status`, or the dead state's name for a fallen one:
/// the battle has no other states.
///
/// The HP and SP are **one run each**, from their cell: the term, the
/// number in three places and, in the HP, the slash and the maximum. That
/// is 54 pixels with A Blurred Line's font, which ends before the SP's
/// cell, and the SP's 30 end at the screen's edge with one to spare;
/// [`check_party_line`] says it when a font does not fit.
pub const BA_PARTY_ROW0: i64 = BA_BAND_ROW0;
pub const BA_PARTY_CURSOR_COL: i64 = 9;
pub const BA_NAME_COL: i64 = 10;
pub const BA_NAME_WIDTH: usize = 6;
pub const BA_STATE_COL: i64 = 16;
pub const BA_STATE_WIDTH: usize = 5;
pub const BA_HP_COL: i64 = 21;
pub const BA_SP_COL: i64 = 28;

/// The battle's message —"X attacks", the damage, the escape—, a troop
/// page's `ShowMessage` and the victory, in RM2k's message window: the
/// whole band, from its first line down, up to four. A line is
/// **thirty-one** cells wide, which is what fits from column 1: the
/// converter reflows the pages' boxes for this window, as it does the
/// map's for theirs, and the console cuts at the edge whatever still does
/// not fit —both measure the line in pixels, with the font's advances—.
/// The victory's lines are checked here in characters, one per cell, which
/// holds for any font no wider than a cell.
pub const BA_MSG_ROW1: i64 = BA_BAND_ROW0;
pub const BA_MSG_ROW2: i64 = BA_BAND_ROW0 + 2;
pub const BA_MSG_LINES: i64 = 4;
pub const BA_PAGE_MSG_ROW0: i64 = BA_BAND_ROW0;
pub const BA_PAGE_MSG_COL: i64 = 1;
pub const BA_PAGE_MSG_WIDTH: usize = 31;

/// The description of the item or the skill under the cursor, on top: one
/// line on row 1, or an item's two —the item screens split it— on rows 0
/// and 2. The band is four tile rows, 32 lines, which is RM2k's 32 of 240.
pub const BA_HELP_ROW: i64 = 1;
pub const BA_HELP_ROW1: i64 = 0;
pub const BA_HELP_ROW2: i64 = 2;
pub const BA_HELP_COL: i64 = 1;
/// Thirty cells: from column 1 to the 31st, which leaves the same eight
/// pixels on the right as on the left.
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
pub const BA_SKILL_NAME_WIDTH: usize = 12;
/// **The cartridge keeps a skill's name whole**, and an enemy's: the
/// console cuts them at their cells, in pixels, with the font's advances.
/// What made it keep fewer was a row's record in the text layer
/// —`TL_RECORD` in `text_layer.s`, 56 bytes—, which has to hold both
/// columns of the skill list: since 2026-10-04 the list writes each name
/// **by reference** (`TL_BY_REF`), a run of six bytes however long the name
/// is, and the row is its length, the cursor's run and per column the
/// name's, the dash's and the cost's. The item list writes its names the
/// same way.
///
/// Until then it kept thirteen letters, which is what the record left with
/// the letters copied, and before 2026-10-03 eleven, from when a letter
/// took a cell: 26 of A Blurred Line's battle skills came out cut by
/// letters and not by pixels, and its fourteen longest enemies too.
const TL_RECORD: usize = 56;
const _: () = assert!(
    1 + (3 + 1) + 2 * ((3 + 3) + (3 + 1) + (3 + 2)) <= TL_RECORD - 1,
    "a row of the skill list does not fit in its record"
);
pub const BA_SKILL_DASH_COL: i64 = 13;
/// **Two digits and not three**, which is what lets the two columns fit in
/// the 32 cells. No cost the battle offers reaches 100: see
/// `skill_usable`.
pub const BA_SKILL_COST_COL: i64 = 14;
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
/// end before the SP's cell, and the SP's before the screen's edge. The
/// numbers are three places of the font's digit. `None` if it fits; if not,
/// what does not.
pub fn check_party_line(font: &rm2k_snes_text::font::Font, hp: &str, sp: &str) -> Option<String> {
    let digits = 3 * font.advance('0');
    let hp_run = font.width(hp) + digits + font.advance('/') + digits;
    let sp_run = font.width(sp) + digits;
    let x = |col: i64| col as usize * 8 + 1;
    let mut bad = Vec::new();
    if x(BA_HP_COL) + hp_run > x(BA_SP_COL) {
        bad.push(format!("the HP ({hp_run} pixels) runs into the SP's cell"));
    }
    if x(BA_SP_COL) + sp_run > 256 {
        bad.push(format!("the SP ({sp_run} pixels) runs off the screen"));
    }
    (!bad.is_empty()).then(|| bad.join("; "))
}

/// What the text screens' font can write: the characters it has, with a
/// '?' instead of the others, and cut to `width`. It is the screens' rule,
/// over the font's range.
pub fn item_text(text: &str, width: usize) -> String {
    let first = font::FIRST as usize;
    text.chars()
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

/// The victory term split into lines of `width`, at the spaces. **The
/// leading spaces stay**: RM2k writes them.
pub fn victory_lines(term: &str, width: usize) -> Result<Vec<String>> {
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
        if together.chars().count() <= width {
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
) -> Result<()> {
    let mut lines = vec![exp_line(db, exp_max), gold_line(db, gold_max)];
    lines.extend(items.iter().map(|n| item_line(db, n, name_width)));
    lines.extend(actors.iter().map(|n| level_line(db, n, 99)));
    lines.extend(skills.iter().map(|h| skill_line(db, h)));
    let long: Vec<&String> = lines
        .iter()
        .filter(|r| r.chars().count() > BA_PAGE_MSG_WIDTH)
        .collect();
    if !long.is_empty() {
        return Err(Bad::answer(format!(
            "these victory lines do not fit in the window's {} characters: {long:?}",
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
        ("BA_ENEMY_ROW0", BA_ENEMY_ROW0),
        ("BA_TARGET_ROWS", BA_TARGET_ROWS),
        ("BA_CURSOR_COL", BA_CURSOR_COL),
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
        ("BA_PARTY_CURSOR_COL", BA_PARTY_CURSOR_COL),
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
        ("BA_HELP_ROW1", BA_HELP_ROW1),
        ("BA_HELP_ROW2", BA_HELP_ROW2),
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
