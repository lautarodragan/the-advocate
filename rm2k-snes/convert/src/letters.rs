//! The Latin-1 letters the text screens write: the ones the cartridge
//! composes at run time out of the database —an actor's name, an item's,
//! a skill's, an enemy's, a condition's, the terms, a 2003 game's battle
//! commands—, the project's `[battle.terms]` and the names `ChangeHeroName`
//! gives. The screens stage carries those its font draws after the message
//! boxes' —see `texts::ScreenLetters` there—, and the text screens write
//! them; every other one is its plain stand-in, as all of them were until
//! 2026-11-22.
//!
//! What the screens stage draws when building —End Game's question, the
//! title's options, the menu's commands— draws the database's text as it
//! is, and does not need them.

use crate::fail::Result;
use ditto::dump::Dump;
use rm2k_snes_text::font::Font;
use serde_json::Value;
use std::collections::BTreeSet;
use std::path::Path;

/// The five bytes cp1252 does not define, which Ditto keeps as their C1
/// characters: a text with one is a Shift-JIS leftover read as cp1252
/// —Zounds' conditions and terms in the editor's Japanese—, and its
/// "letters" are noise. The screens stage refuses those texts the same
/// way: see `C1` in its `game.rs`.
const C1: [char; 5] = ['\u{81}', '\u{8d}', '\u{8f}', '\u{90}', '\u{9d}'];

/// The letters `font` draws of the texts the text screens compose: those
/// of the dump's database in `dump`, of `battle_terms` —the project's,
/// which stand in for the database's— and of `names`. In code point order,
/// each once.
pub fn screen_letters(
    dump: &Path,
    font: &Font,
    battle_terms: &Value,
    names: &[String],
) -> Result<Vec<char>> {
    let mut texts = database_texts(&Dump::open(dump)?, battle_terms)?;
    texts.extend(names.iter().cloned());
    if let Some(terms) = battle_terms.as_object() {
        texts.extend(terms.values().filter_map(Value::as_str).map(str::to_string));
    }
    let drawn: BTreeSet<char> = font.latin_letters().into_iter().map(|(c, _)| c).collect();
    let mut out = BTreeSet::new();
    for text in texts.iter().filter(|t| !t.chars().any(|c| C1.contains(&c))) {
        out.extend(text.chars().filter(|c| drawn.contains(c)));
    }
    Ok(out.into_iter().collect())
}

/// The database's texts the text screens and the battle compose at run
/// time. A 2003 game's battle never shows the terms of
/// `UNSHOWN_IN_2003` —the mapdata stage's—, so whatever its database
/// holds in them is not the game's: the project's or English stand in.
fn database_texts(dump: &Dump, battle_terms: &Value) -> Result<Vec<String>> {
    let section = |name: &str| -> Result<Value> { Ok(dump.section::<Value>(name)?) };
    let mut out = Vec::new();
    let mut take = |list: &Value, fields: &[&str]| {
        for x in list.as_array().into_iter().flatten() {
            for f in fields {
                if let Some(t) = x.get(*f).and_then(Value::as_str) {
                    out.push(t.to_string());
                }
            }
        }
    };
    take(&section("actors")?, &["name"]);
    take(&section("items")?, &["name", "description"]);
    take(
        &section("skills")?,
        &["name", "description", "using_message1", "using_message2"],
    );
    take(&section("enemies")?, &["name"]);
    take(
        &section("states")?,
        &[
            "name",
            "message_actor",
            "message_enemy",
            "message_already",
            "message_affected",
            "message_recovery",
        ],
    );
    let is_2003 = section("system")?.get("ldb_id").and_then(Value::as_i64) == Some(2003);
    if is_2003 {
        if let Ok(commands) = section("battlecommands") {
            take(&commands["commands"], &["name"]);
        }
    }
    let unshown: Vec<&str> = rm2k_snes_mapdata::emit::UNSHOWN_IN_2003
        .iter()
        .map(|(name, _)| *name)
        .collect();
    if let Some(terms) = section("terms")?.as_object() {
        for (name, value) in terms {
            let replaced =
                battle_terms.get(name).is_some() || (is_2003 && unshown.contains(&name.as_str()));
            if let (false, Some(t)) = (replaced, value.as_str()) {
                out.push(t.to_string());
            }
        }
    }
    Ok(out)
}
