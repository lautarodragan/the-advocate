//! The battle's text screen: where each thing goes on it, and the texts
//! the console composes on it.
//!
//! It draws nothing: the console writes it one letter per cell with the
//! text screens' font, over a flat colour or the scene, on the same grid
//! of 32 by 28 cells the equipment and shop screens use. What goes from
//! here is the geometry —in cells; the caller turns it into what its
//! tables need— and the texts, already cut to what fits.
//!
//! **The words are RM2k's**, all from the database, none made up. What is
//! not RM2k's is declared where it is: escaping is an actor's command and
//! not the party's, and some lines are cut shorter than the original's.

use crate::db::Db;
use crate::fail::{Bad, Result};
use rm2k_snes_text::font;
use serde_json::{json, Map, Value};

// The rows of the grid: the enemies at the top, the party below, and the
// two message lines at the bottom.
pub const BA_ENEMY_ROW0: i64 = 0;
pub const BA_PARTY_ROW0: i64 = 16;
pub const BA_MSG_ROW1: i64 = 24;
pub const BA_MSG_ROW2: i64 = 26;
pub const BA_CURSOR_COL: i64 = 0;
pub const BA_NAME_COL: i64 = 2;
pub const BA_NAME_WIDTH: usize = 14;
/// **An enemy's HP is not shown**, as in RM2k: its line is just the name.
/// A cartridge built for debugging shows it in these same columns.
pub const BA_HP_COL: i64 = 18;
/// Three digits.
pub const BA_HP_NUM: i64 = 21;
pub const BA_BAR_COL: i64 = 24;
/// And the three of the maximum, in the party.
pub const BA_HP_MAX_NUM: i64 = 25;

/// The width of a command: the longest of the game's, `Tech Skill` and
/// `AgentTrain`, which is Kersh's.
pub const BA_COMMAND_WIDTH: usize = 10;

/// The five commands, in the original's order —Attack, the skill, Defend,
/// Use Item, as a capture of the real game shows them— and Escape fifth:
/// escaping is a party command in RM2k, from another menu, and here it is
/// each actor's. It is a declared simplification.
pub const BA_COMMAND_ATTACK: i64 = 0;
pub const BA_COMMAND_SKILL: i64 = 1;
pub const BA_COMMAND_DEFEND: i64 = 2;
pub const BA_COMMAND_USE: i64 = 3;
pub const BA_COMMAND_ESCAPE: i64 = 4;

/// Per command: which term names it, which of the two message lines it
/// goes on and in which column. **The skill's column leaves ten free
/// cells**: its text is the actor's `skill_name`, and ten letters leave no
/// room for the next one's cursor, which goes one cell before its text.
/// That is why the top line is 1 / 11 / 22 and not 1 / 11 / 21.
pub const BA_COMMANDS: [(&str, i64, i64); 5] = [
    ("attack", 0, 1),
    ("skill", 0, 11),
    ("defend", 0, 22),
    ("use", 1, 1),
    ("escape", 1, 13),
];

/// The commands the console grays out always: none since the skill was
/// done. It stays because it is where the next half-done one would go.
pub const BA_COMMAND_UNDONE: [i64; 0] = [];

/// The skill list, on the same lines as the item list: the description of
/// the one under the cursor at the very top —**cut at thirty-one**: the
/// original writes it whole with a smaller font, and it is declared debt—
/// and below, two columns with the name and the cost. It reads by rows.
pub const BA_SKILL_DESC_ROW: i64 = 0;
pub const BA_SKILL_DESC_COL: i64 = 1;
pub const BA_SKILL_DESC_WIDTH: usize = 31;
pub const BA_SKILL_ROW0: i64 = 2;
pub const BA_SKILL_ROWS: i64 = 7;
pub const BA_SKILL_COLUMNS: i64 = 2;
/// From one column to the next.
pub const BA_SKILL_COLUMN_DX: i64 = 16;
/// Relative to the start of the column.
pub const BA_SKILL_NAME_COL: i64 = 2;
pub const BA_SKILL_NAME_WIDTH: usize = 11;
pub const BA_SKILL_DASH_COL: i64 = 13;
/// **Two digits and not three**, which is what lets the two columns fit in
/// the 32 cells. No cost the battle offers reaches 100: see
/// `skill_usable`.
pub const BA_SKILL_COST_COL: i64 = 14;
pub const BA_SKILL_COST_DIGITS: i64 = 2;

/// The item list takes the enemies' lines: while choosing what to use, the
/// party is what is needed.
pub const BA_ITEM_COUNT_COL: i64 = 18;

/// A troop page's `ShowMessage`, and what the victory reports: RM2k's
/// message window covers the party's status, and here that is the party's
/// four lines. The line is cut at **thirty-one** characters, which is what
/// fits from column 1; the map's window carries thirty-nine. It is declared
/// debt.
pub const BA_PAGE_MSG_ROW0: i64 = BA_PARTY_ROW0;
pub const BA_PAGE_MSG_COL: i64 = 1;
pub const BA_PAGE_MSG_WIDTH: usize = 31;

/// How many lines the victory term may take: the first page is the term
/// and the experience, in the window's four.
pub const BA_VICTORY_TERM_MAX: usize = 2;

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
    out.insert("BA_ENEMY_ROW0".into(), json!(BA_ENEMY_ROW0));
    out.insert("BA_PARTY_ROW0".into(), json!(BA_PARTY_ROW0));
    out.insert("BA_MSG_ROW1".into(), json!(BA_MSG_ROW1));
    out.insert("BA_MSG_ROW2".into(), json!(BA_MSG_ROW2));
    out.insert("BA_CURSOR_COL".into(), json!(BA_CURSOR_COL));
    out.insert("BA_NAME_COL".into(), json!(BA_NAME_COL));
    out.insert("BA_NAME_WIDTH".into(), json!(BA_NAME_WIDTH));
    out.insert("BA_HP_COL".into(), json!(BA_HP_COL));
    out.insert("BA_HP_NUM".into(), json!(BA_HP_NUM));
    out.insert("BA_BAR_COL".into(), json!(BA_BAR_COL));
    out.insert("BA_HP_MAX_NUM".into(), json!(BA_HP_MAX_NUM));
    out.insert("BA_COMMAND_WIDTH".into(), json!(BA_COMMAND_WIDTH));
    out.insert("BA_COMMAND_ATTACK".into(), json!(BA_COMMAND_ATTACK));
    out.insert("BA_COMMAND_SKILL".into(), json!(BA_COMMAND_SKILL));
    out.insert("BA_COMMAND_DEFEND".into(), json!(BA_COMMAND_DEFEND));
    out.insert("BA_COMMAND_USE".into(), json!(BA_COMMAND_USE));
    out.insert("BA_COMMAND_ESCAPE".into(), json!(BA_COMMAND_ESCAPE));
    out.insert(
        "BA_COMMANDS".into(),
        json!(BA_COMMANDS
            .iter()
            .map(|(t, l, c)| json!([t, l, c]))
            .collect::<Vec<_>>()),
    );
    out.insert(
        "BA_COMMAND_UNDONE".into(),
        json!(BA_COMMAND_UNDONE.to_vec()),
    );
    out.insert("BA_SKILL_DESC_ROW".into(), json!(BA_SKILL_DESC_ROW));
    out.insert("BA_SKILL_DESC_COL".into(), json!(BA_SKILL_DESC_COL));
    out.insert("BA_SKILL_DESC_WIDTH".into(), json!(BA_SKILL_DESC_WIDTH));
    out.insert("BA_SKILL_ROW0".into(), json!(BA_SKILL_ROW0));
    out.insert("BA_SKILL_ROWS".into(), json!(BA_SKILL_ROWS));
    out.insert("BA_SKILL_COLUMNS".into(), json!(BA_SKILL_COLUMNS));
    out.insert("BA_SKILL_COLUMN_DX".into(), json!(BA_SKILL_COLUMN_DX));
    out.insert("BA_SKILL_NAME_COL".into(), json!(BA_SKILL_NAME_COL));
    out.insert("BA_SKILL_NAME_WIDTH".into(), json!(BA_SKILL_NAME_WIDTH));
    out.insert("BA_SKILL_DASH_COL".into(), json!(BA_SKILL_DASH_COL));
    out.insert("BA_SKILL_COST_COL".into(), json!(BA_SKILL_COST_COL));
    out.insert("BA_SKILL_COST_DIGITS".into(), json!(BA_SKILL_COST_DIGITS));
    out.insert("BA_ITEM_COUNT_COL".into(), json!(BA_ITEM_COUNT_COL));
    out.insert("BA_PAGE_MSG_ROW0".into(), json!(BA_PAGE_MSG_ROW0));
    out.insert("BA_PAGE_MSG_COL".into(), json!(BA_PAGE_MSG_COL));
    out.insert("BA_PAGE_MSG_WIDTH".into(), json!(BA_PAGE_MSG_WIDTH));
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
