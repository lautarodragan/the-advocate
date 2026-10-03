//! What the screens write, as text: cut to what fits, in the letters the
//! font has, with numbers as RM2k formats them.

use crate::fail::Result;
use rm2k_snes_text::font::Font;
use crate::game::{Game, ITEM_MEDICINE, ITEM_SWITCH};
use crate::layout::*;
use ditto::schema::{Actor, Item};
use rm2k_rules::actor as rules;

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

/// As much of `text` as fits in `cells` cells: the letters whose advances
/// add up to `8 * cells` pixels at most. It is the console's `scr_cap`,
/// which until 2026-10-03 counted letters, one per cell.
pub fn fit_cells(font: &Font, text: &str, cells: usize) -> String {
    let mut width = 0;
    text.chars()
        .take_while(|&c| {
            width += font.advance(c);
            width <= 8 * cells
        })
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

/// A description in two lines, cut at a space, each as wide as
/// [`DESC_WIDTH_PX`] in `font`. What does not fit in two is lost. With the
/// variable-width font a whole description fits in one line most of the
/// time: RM2k's help window has one.
pub fn split_description(font: &Font, text: &str) -> Vec<String> {
    let width = DESC_WIDTH_PX;
    let fit = |t: &str| -> String {
        let mut used = 0;
        t.chars()
            .take_while(|&c| {
                used += font.advance(c);
                used <= width
            })
            .collect()
    };
    let mut rows = Vec::new();
    let mut current = String::new();
    for word in text.split(' ') {
        let candidate = if current.is_empty() {
            word.to_string()
        } else {
            format!("{current} {word}")
        };
        if font.width(&candidate) <= width {
            current = candidate;
            continue;
        }
        rows.push(current);
        current = fit(word);
    }
    rows.push(current);
    let mut rows: Vec<String> = rows.iter().map(|r| item_text(r, r.chars().count())).collect();
    rows.resize(rows.len().max(ITEM_DESC_LINES), String::new());
    rows.truncate(ITEM_DESC_LINES);
    rows
}

/// A name split into `rows` lines of `width` cells, by words; a word that
/// does not fit is cut where it reaches. A line fits if it is no wider than
/// its cells' pixels and has no more letters than cells —the cartridge keeps
/// `width` letters per line—. Padded with spaces to `width` letters: the
/// cartridge drops the padding when it composes the line.
pub fn name_in_lines(font: &Font, name: &str, width: usize, rows: usize) -> Vec<String> {
    let fits = |text: &str| text.chars().count() <= width && font.width(text) <= 8 * width;
    let mut out = Vec::new();
    let mut line = String::new();
    for word in name.split_whitespace() {
        let mut word: String = word.to_string();
        while !fits(&word) {
            if !line.is_empty() {
                out.push(std::mem::take(&mut line));
            }
            let mut cut = String::new();
            for c in word.chars() {
                cut.push(c);
                if !fits(&cut) {
                    cut.pop();
                    break;
                }
            }
            word = word.chars().skip(cut.chars().count()).collect();
            out.push(cut);
        }
        if line.is_empty() {
            line = word;
        } else if fits(&format!("{line} {word}")) {
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

/// What the cartridge composes of a text that may take `cells` cells: the
/// stored text —`stored`, padded with spaces— without its padding, and of
/// that as much as fits in the cells' pixels. It is `tl_strip`'s.
pub fn strip_text(font: &Font, stored: &str, cells: usize) -> String {
    let letters: String = stored.chars().take(cells).collect();
    fit_cells(font, letters.trim_end_matches(' '), cells)
}

/// An actor's max HP at `level` —its starting one without it—: RM2k's
/// curve ([`rules::curve_at`]), and 0 where it has nothing.
pub fn max_hp(actor: &Actor, level: Option<i64>) -> i64 {
    let level = level.unwrap_or_else(|| rules::level_of(actor));
    rules::curve_at(&actor.parameters.maxhp, level).unwrap_or(0)
}

/// An actor's four parameters at its starting level with this equipment
/// on: RM2k's ([`rules::with_equipment`]), with a curve that has nothing
/// at the level read as 0 and an item the database lacks left out.
pub fn equipped_params(game: &Game, actor: i32, equipment: &[i32]) -> Vec<i64> {
    let a = &game.actors[&actor];
    let level = rules::level_of(a);
    let base = rules::EQUIPPED.map(|which| {
        rules::curve(a, which)
            .and_then(|values| rules::curve_at(values, level))
            .unwrap_or(0)
    });
    let items = equipment
        .iter()
        .filter(|&&item| item != 0)
        .filter_map(|item| game.items.get(item));
    rules::with_equipment(base, items).to_vec()
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
    let level = level.unwrap_or_else(|| game.actors.get(&actor).map_or(0, rules::level_of));
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

/// The letters the menu's bank carries as glyphs, one per cell: those of
/// the numbers —the gold, the level, the HP, the experience— and nothing
/// else. Until 2026-10-03 it also carried the letters of every name it
/// wrote; the names are composed now, see `tl_strip` in the runtime.
pub const NUMBER_GLYPHS: &str = " -/0123456789";

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
        let font = Font::rm2k(rm2k_snes_text::font::MINCHO);
        let lines = split_description(&font, "A small bottle of something that heals a little bit of health.");
        assert_eq!(lines.len(), 2);
        assert!(lines.iter().all(|l| font.width(l) <= DESC_WIDTH_PX));
        assert_eq!(split_description(&font, "")[0], "");
    }

    #[test]
    fn a_long_word_is_cut_where_it_reaches() {
        // RM2k's font, six pixels a letter: 11 cells are 88 pixels, and 14
        // letters would fit in them, but a line keeps 11.
        let font = Font::rm2k(rm2k_snes_text::font::MINCHO);
        assert_eq!(
            name_in_lines(&font, "Sandwich-HP", 11, 2),
            vec!["Sandwich-HP".to_string(), " ".repeat(11)]
        );
        assert_eq!(
            name_in_lines(&font, "Supercalifragilistic", 11, 2),
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
