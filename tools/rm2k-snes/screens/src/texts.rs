//! What the screens write, as text: cut to what fits, in the letters the
//! font has, with numbers as RM2k formats them.

use crate::fail::Result;
use crate::game::{Game, ITEM_MEDICINE, ITEM_SWITCH};
use crate::layout::*;
use ditto::schema::{Actor, Item};
use std::collections::BTreeSet;

/// What the screen can write: the characters the font has, with a '?'
/// instead of the others, and cut to `width`.
pub fn item_text(text: &str, width: usize) -> String {
    text.chars()
        .map(|c| {
            let code = c as usize;
            if (ITEM_FIRST_CHAR..ITEM_FIRST_CHAR + ITEM_CHARS).contains(&code) {
                c
            } else {
                '?'
            }
        })
        .take(width)
        .collect()
}

/// `text` padded with spaces to `width` characters, like Python's `ljust`.
pub fn ljust(text: &str, width: usize) -> String {
    let n = text.chars().count();
    let mut out = text.to_string();
    out.extend(std::iter::repeat_n(' ', width.saturating_sub(n)));
    out
}

/// `value` right-aligned in `width` columns, and only its last `width`
/// characters if it is longer: `("%*d" % (width, value))[-width:]`.
pub fn right(value: i64, width: usize) -> String {
    let text = format!("{value:>width$}");
    let n = text.chars().count();
    text.chars().skip(n.saturating_sub(width)).collect()
}

/// A description in two lines, cut at a space. What does not fit in two is
/// lost.
pub fn split_description(text: &str) -> Vec<String> {
    let width = ITEM_DESC_WIDTH;
    let mut rows = Vec::new();
    let mut current = String::new();
    for word in text.split(' ') {
        let candidate = if current.is_empty() {
            word.to_string()
        } else {
            format!("{current} {word}")
        };
        if candidate.chars().count() <= width {
            current = candidate;
            continue;
        }
        rows.push(current);
        current = word.chars().take(width).collect();
    }
    rows.push(current);
    let mut rows: Vec<String> = rows.iter().map(|r| item_text(r, width)).collect();
    rows.resize(rows.len().max(ITEM_DESC_LINES), String::new());
    rows.truncate(ITEM_DESC_LINES);
    rows
}

/// A name split into `rows` lines of `width`, by words; a word that does
/// not fit is cut where it reaches. Padded with spaces, which are what
/// erase whatever was there.
pub fn name_in_lines(name: &str, width: usize, rows: usize) -> Vec<String> {
    let mut out = Vec::new();
    let mut line = String::new();
    for word in name.split_whitespace() {
        let mut word: String = word.to_string();
        while word.chars().count() > width {
            if !line.is_empty() {
                out.push(std::mem::take(&mut line));
            }
            out.push(word.chars().take(width).collect());
            word = word.chars().skip(width).collect();
        }
        if line.is_empty() {
            line = word;
        } else if line.chars().count() + 1 + word.chars().count() <= width {
            line = format!("{line} {word}");
        } else {
            out.push(std::mem::replace(&mut line, word));
        }
    }
    if !line.is_empty() {
        out.push(line);
    }
    out.resize(out.len().max(rows), String::new());
    out.truncate(rows);
    out.iter().map(|r| ljust(r, width)).collect()
}

/// The level an actor starts at, as the database says it: `initial_level`,
/// or 1 if it says 0.
pub fn level_of(actor: &Actor) -> i64 {
    match actor.initial_level {
        0 => 1,
        level => level as i64,
    }
}

/// An actor's max HP at `level` —its starting one without it—: the
/// database's curve, from level 1, and 0 past its end.
pub fn max_hp(actor: &Actor, level: Option<i64>) -> i64 {
    let values = &actor.parameters.maxhp;
    let level = level.unwrap_or_else(|| level_of(actor));
    let at = level - 1;
    if at >= values.len() as i64 {
        return 0;
    }
    // A level of 0 or less counts from the end, which is how the drawing
    // this replaces indexed it.
    let at = if at < 0 { values.len() as i64 + at } else { at };
    values.get(at as usize).map_or(0, |&v| v as i64)
}

/// An actor's four parameters with its equipment on: the level's plus what
/// the items add, each clamped to 1..999, like `Game_Actor::GetAtk` and its
/// siblings.
pub fn equipped_params(game: &Game, actor: i32, equipment: &[i32]) -> Vec<i64> {
    let a = &game.actors[&actor];
    let level = level_of(a);
    let curve = |values: &[i16]| -> i64 {
        let at = level - 1;
        if at >= values.len() as i64 {
            0
        } else {
            let at = if at < 0 { values.len() as i64 + at } else { at };
            values.get(at as usize).map_or(0, |&v| v as i64)
        }
    };
    let p = &a.parameters;
    let mut base = [curve(&p.attack), curve(&p.defense), curve(&p.spirit), curve(&p.agility)];
    for &item in equipment {
        if item == 0 {
            continue;
        }
        if let Some(it) = game.items.get(&item) {
            let points = [it.atk_points1, it.def_points1, it.spi_points1, it.agi_points1];
            for (b, p) in base.iter_mut().zip(points) {
                *b += p as i64;
            }
        }
    }
    base.iter().map(|b| (*b).clamp(1, 999)).collect()
}

/// The actor's name as the cartridge composes it: one letter per cell,
/// with the ones the font lacks turned into '?' and padded with spaces to
/// `cols`. The padding erases whatever was there.
pub fn name_text(game: &Game, actor: i32, cols: usize) -> Result<String> {
    Ok(ljust(&item_text(&game.actor_name(actor)?, cols), cols))
}

/// The two digits of the level, right-aligned as RM2k says them. Without
/// `level`, the starting one.
pub fn level_text(game: &Game, actor: i32, level: Option<i64>) -> String {
    let level = level.unwrap_or_else(|| game.actors.get(&actor).map_or(0, level_of));
    right(level, LEVEL_DIGITS)
}

/// The actor's max HP after its slash: "/168". Without `level`, those of
/// the starting one.
pub fn max_text(game: &Game, actor: i32, level: Option<i64>) -> String {
    let maximum = game.actors.get(&actor).map_or(0, |a| max_hp(a, level));
    let text = ljust(&format!("/{maximum}"), MENU_MAX_DIGITS);
    text.chars().take(MENU_MAX_DIGITS).collect()
}

/// The experience as `DrawActorExp` writes it: `"%6d/%6d"`, the current one
/// and the one the next level asks for, or dashes at the cap. Without
/// `level` or `exp`, the starting ones.
pub fn exp_text(game: &Game, actor: i32, level: Option<i64>, exp: Option<i64>) -> String {
    use rm2k_rules::actor as rules;
    let a = &game.actors[&actor];
    let level = level.unwrap_or_else(|| rules::initial_level(a));
    let exp = exp.unwrap_or_else(|| rules::initial_exp(a));
    let next = rules::next_exp(a, level);
    if next == -1 {
        let dashes = "-".repeat(MENU_EXP_DIGITS);
        return format!("{dashes}/{dashes}");
    }
    format!("{exp:>w$}/{next:>w$}", w = MENU_EXP_DIGITS)
}

/// The digits of a number capped at `how_many`, without leading zeros: 0 is
/// "0". The menu's gold and each actor's HP use it.
pub fn digits_of(value: i64, how_many: u32) -> String {
    value.clamp(0, 10_i64.pow(how_many) - 1).to_string()
}

/// Which letters the menu's bank needs: those of what is composed —each
/// actor's name, level and maximum—, plus the ten digits and the space,
/// which the gold and the current HP use, the experience's slash and dash,
/// and `extra` —the names of the medicines, which the actor choice
/// writes—. A cartridge with three actors does not pay for the others'
/// letters.
pub fn glyphs_of(game: &Game, actors: &[i32], extra: &str) -> Result<Vec<char>> {
    let mut letters: BTreeSet<char> = "0123456789 ".chars().collect();
    letters.extend(extra.chars());
    letters.extend("/-".chars());
    for &actor in actors {
        letters.extend(name_text(game, actor, MENU_NAME_COLS)?.chars());
        letters.extend(level_text(game, actor, None).chars());
        letters.extend(max_text(game, actor, None).chars());
    }
    Ok(letters.into_iter().collect())
}

/// Whether the item goes in white and A does something with it on the
/// map: `Game_Party::IsItemUsable` outside battle. The switch ones that can
/// be used on the field, and the medicines, which open the actor choice.
pub fn item_usable(item: &Item) -> bool {
    let kind = item.r#type.to_i32();
    (kind == ITEM_SWITCH && item.occasion_field2) || kind == ITEM_MEDICINE
}

/// Whether using it opens the actor choice: the medicines.
pub fn item_needs_actor(item: &Item) -> bool {
    item.r#type.to_i32() == ITEM_MEDICINE
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_description_goes_in_two_lines_cut_at_a_space() {
        let lines = split_description("A small bottle of something that heals a little bit of health.");
        assert_eq!(lines.len(), 2);
        assert!(lines.iter().all(|l| l.chars().count() <= ITEM_DESC_WIDTH));
        assert_eq!(split_description("")[0], "");
    }

    #[test]
    fn a_long_word_is_cut_where_it_reaches() {
        assert_eq!(
            name_in_lines("Sandwich-HP", 11, 2),
            vec!["Sandwich-HP".to_string(), " ".repeat(11)]
        );
        assert_eq!(
            name_in_lines("Supercalifragilistic", 11, 2),
            vec!["Supercalifr".to_string(), "agilistic  ".to_string()]
        );
    }

    #[test]
    fn numbers_as_rm2k_writes_them() {
        assert_eq!(right(7, 2), " 7");
        assert_eq!(right(123, 2), "23");
        assert_eq!(digits_of(1_234_567, 6), "999999");
        assert_eq!(digits_of(-5, 3), "0");
        assert_eq!(item_text("Café", 10), "Caf?");
    }
}
