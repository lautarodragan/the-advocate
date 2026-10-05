//! The check: what the built cartridges decided against what is versioned,
//! told as **which decision changed**.
//!
//! It is not a text diff: a file that differs only in a comment says
//! nothing, and one where a merge changed has to say **which**. It is the
//! only thing that makes the check useful: "the file differs" sends you to
//! run `diff` and guess whether the change matters.
//!
//! The messages quote the values the way the Python that first wrote them
//! printed them —`None` for a missing field, a list as `[1, 2]`, a sheet
//! with its quotes—, so the check says the same thing it always said.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use toml::{Table, Value};

use crate::{io, only_for_tests, toml_files, Key, Kind};

pub(crate) fn read(path: &Path) -> Result<Table, String> {
    let text = std::fs::read_to_string(path).map_err(io(path))?;
    text.parse().map_err(|e| format!("{}: {e}", path.display()))
}

pub(crate) fn key_of(doc: &Table, kind: Kind, path: &Path) -> Result<Key, String> {
    match doc.get(kind.key()) {
        Some(Value::Integer(n)) => Ok(Key::Number(*n)),
        Some(Value::String(t)) => Ok(Key::Text(t.clone())),
        _ => Err(format!("{}: has no `{}`", path.display(), kind.key())),
    }
}

/// The ones with a versioned patch of `kind`, that is the playable ROM's.
/// The key is read from inside the file and not from its name: a battler's
/// is a text, and its file name does not carry the spaces.
pub fn versioned(auto: &Path, kind: Kind) -> Result<Vec<Key>, String> {
    let folder = auto.join(kind.directory());
    if !folder.is_dir() {
        return Ok(Vec::new());
    }
    let mut keys = Vec::new();
    for name in toml_files(&folder)? {
        let path = folder.join(name);
        keys.push(key_of(&read(&path)?, kind, &path)?);
    }
    keys.sort();
    Ok(keys)
}

// --- Values as the messages print them --------------------------------------

/// A value as Python's `str` prints it; `None` when it is missing.
fn shown(value: Option<&Value>) -> String {
    match value {
        None => "None".into(),
        Some(Value::String(s)) => s.clone(),
        Some(v) => quoted(Some(v)),
    }
}

/// A value as Python's `repr` prints it: a text with its quotes.
fn quoted(value: Option<&Value>) -> String {
    match value {
        None => "None".into(),
        Some(Value::String(s)) => repr(s),
        Some(Value::Integer(n)) => n.to_string(),
        Some(Value::Float(f)) => f.to_string(),
        Some(Value::Boolean(b)) => if *b { "True" } else { "False" }.into(),
        Some(Value::Array(items)) => format!(
            "[{}]",
            items.iter().map(|v| quoted(Some(v))).collect::<Vec<_>>().join(", ")
        ),
        Some(v) => v.to_string(),
    }
}

/// A text with its quotes: single ones, unless it has a single quote and no
/// double one.
fn repr(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::from(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32))
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

fn color(value: &Value) -> String {
    match value.as_array() {
        Some(c) if c.len() == 3 => format!(
            "[{}, {}, {}]",
            shown(c.first()),
            shown(c.get(1)),
            shown(c.get(2))
        ),
        _ => shown(Some(value)),
    }
}

fn sides(pair: Option<&Value>) -> String {
    match pair.and_then(Value::as_array) {
        Some(p) if !p.is_empty() => format!("{}x{}", shown(p.first()), shown(p.get(1))),
        _ => "nothing".into(),
    }
}

fn field<'a>(doc: &'a Table, path: &[&str]) -> Option<&'a Value> {
    let (last, tables) = path.split_last()?;
    let mut table = doc;
    for name in tables {
        table = table.get(*name)?.as_table()?;
    }
    table.get(*last)
}

// --- What changed, per kind -------------------------------------------------

type MergeRow<'a> = (&'a Value, &'a Value, Option<&'a Value>);

fn merges<'a>(doc: &'a Table, layer: &str) -> Vec<MergeRow<'a>> {
    field(doc, &["capas", layer, "fusiones"])
        .and_then(Value::as_array)
        .map(|rows| {
            rows.iter()
                .filter_map(|f| Some((f.get("de")?, f.get("a")?, f.get("pixeles"))))
                .collect()
        })
        .unwrap_or_default()
}

fn map_diff(old: &Table, new: &Table) -> Vec<String> {
    let mut out = Vec::new();
    for layer in ["fondo", "encima"] {
        let (before, after) = (merges(old, layer), merges(new, layer));
        for name in ["colores", "presupuesto"] {
            let a = field(old, &["capas", layer, name]);
            let b = field(new, &["capas", layer, name]);
            if a != b {
                out.push(format!(
                    "layer {layer}: {name} went from {} to {}",
                    shown(a),
                    shown(b)
                ));
            }
        }
        if before.len() != after.len() {
            out.push(format!(
                "layer {layer}: it merged {} color(s) and now merges {}",
                before.len(),
                after.len()
            ));
        }
        for (i, (a, b)) in before.iter().zip(&after).enumerate() {
            if (a.0, a.1) != (b.0, b.1) {
                out.push(format!(
                    "layer {layer}: merge {i} sent {} to {} and now sends {} to {}",
                    color(a.0),
                    color(a.1),
                    color(b.0),
                    color(b.1)
                ));
            } else if a.2 != b.2 {
                out.push(format!(
                    "layer {layer}: merge {i} of {} moved {} pixel(s) and now moves {}",
                    color(a.0),
                    shown(a.2),
                    shown(b.2)
                ));
            }
        }
        for (v, d, _) in after.iter().skip(before.len()) {
            out.push(format!("layer {layer}: extra merge {} -> {}", color(v), color(d)));
        }
        for (v, d, _) in before.iter().skip(after.len()) {
            out.push(format!(
                "layer {layer}: no longer merges {} -> {}",
                color(v),
                color(d)
            ));
        }
    }
    for name in ["camino", "imagen", "modo", "tiles", "distintos", "colores", "quedan"] {
        let a = field(old, &["panorama", name]);
        let b = field(new, &["panorama", name]);
        if a != b {
            out.push(format!("panorama: {name} went from {} to {}", shown(a), shown(b)));
        }
    }
    let rows = |doc: &Table| field(doc, &["panorama", "fusiones"]).and_then(Value::as_array).cloned().unwrap_or_default();
    let (before, after) = (rows(old), rows(new));
    if before != after {
        out.push(format!(
            "panorama: it merged {} color(s) and now merges {}, or other ones",
            before.len(),
            after.len()
        ));
    }
    out
}

/// What matters is the first line: **the size it is drawn at**. The others
/// say why it changed —the animation measures something else in RM2k, or
/// has other frames—, and they can come out alone: the box not moving does
/// not mean the animation is the same.
fn animation_diff(old: &Table, new: &Table) -> Vec<String> {
    let mut out = Vec::new();
    if old.get("tamano") != new.get("tamano") {
        out.push(format!(
            "it was drawn at {} and now it is drawn at {}",
            sides(old.get("tamano")),
            sides(new.get("tamano"))
        ));
    }
    if old.get("original") != new.get("original") {
        out.push(format!(
            "it came from {} in RM2k and now comes from {}",
            sides(old.get("original")),
            sides(new.get("original"))
        ));
    }
    if old.get("cuadros") != new.get("cuadros") {
        out.push(format!(
            "it had {} frame(s) and now has {}",
            shown(old.get("cuadros")),
            shown(new.get("cuadros"))
        ));
    }
    if old.get("hoja") != new.get("hoja") {
        out.push(format!(
            "it came from sheet {} and now comes from {}",
            quoted(old.get("hoja")),
            quoted(new.get("hoja"))
        ));
    }
    out
}

/// First whether another color is lost, then why.
fn battler_diff(old: &Table, new: &Table) -> Vec<String> {
    let palette = |doc: &Table| -> Vec<Value> {
        doc.get("paleta")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };
    let (before, after) = (palette(old), palette(new));
    let mut out = Vec::new();
    for c in &after {
        if !before.contains(c) {
            out.push(format!("keeps {}, which used to be merged", color(c)));
        }
    }
    for c in &before {
        if !after.contains(c) {
            out.push(format!("loses {}, which used to stay", color(c)));
        }
    }
    if out.is_empty() && before != after {
        out.push("the same colors in another palette order".into());
    }
    for name in ["tamano", "colores", "imagen", "tono"] {
        if old.get(name) != new.get(name) {
            out.push(format!(
                "{name} went from {} to {}",
                shown(old.get(name)),
                shown(new.get(name))
            ));
        }
    }
    if old.get("fusiones") != new.get("fusiones") {
        out.push(format!(
            "{} merges were needed and now {}",
            shown(old.get("fusiones")),
            shown(new.get("fusiones"))
        ));
    }
    out
}

fn diff(kind: Kind, old: &Table, new: &Table) -> Vec<String> {
    match kind {
        Kind::Map => map_diff(old, new),
        Kind::Animation => animation_diff(old, new),
        Kind::Battler => battler_diff(old, new),
    }
}

// --- The check ----------------------------------------------------------------

/// What each kind has only in some cartridge and not versioned, with the
/// cartridges that have it: `{Map: {7: ["test-special"]}}`.
pub type Own = BTreeMap<Kind, BTreeMap<Key, Vec<String>>>;

/// What [`check`] found.
#[derive(Debug, Default)]
pub struct Checked {
    /// Each one a paragraph, without indentation on its first line.
    pub complaints: Vec<String>,
    pub own: Own,
}

/// The builds' patches against the versioned ones in `auto`.
///
/// `builds` are directories of built cartridges, and **all** of them are
/// looked at; the cartridge's name is the directory's. What is not versioned
/// is not a complaint: it is a situation the playable ROM does not have —a
/// map it does not carry, an animation it does not show—, so the test
/// cartridge decided on its own and that is not versioned; it comes out in
/// `own`, which is information about how much the cartridges resemble the
/// game and not an error. For the playable ROM, on the other hand,
/// everything has to be versioned **except what it carries only for the
/// tests** —see [`only_for_tests`], with the project's test maps in
/// `tests`—, which also comes out in `own`.
///
/// What **is** versioned is compared against what is committed in every
/// cartridge that carries it. For today's kinds that cannot differ —none of
/// them looks at the cartridge— and that is why it complains: if it did
/// differ, what broke is that independence, and it is better to find out
/// here than when the converter starts reading these files.
///
/// The paths in the messages are relative to `base`, the directory the
/// caller runs in.
pub fn check(
    auto: &Path,
    builds: &[PathBuf],
    tests: &BTreeSet<i64>,
    base: &Path,
) -> Result<Checked, String> {
    let mut checked = Checked::default();
    for kind in Kind::ALL {
        let mine = check_kind(kind, auto, builds, tests, base, &mut checked.complaints)?;
        if !mine.is_empty() {
            checked.own.insert(kind, mine);
        }
    }
    Ok(checked)
}

fn check_kind(
    kind: Kind,
    auto: &Path,
    builds: &[PathBuf],
    tests: &BTreeSet<i64>,
    base: &Path,
    complaints: &mut Vec<String>,
) -> Result<BTreeMap<Key, Vec<String>>, String> {
    let mut own: BTreeMap<Key, Vec<String>> = BTreeMap::new();
    let have: BTreeSet<Key> = versioned(auto, kind)?.into_iter().collect();
    let mut seen = BTreeSet::new();
    // One complaint per situation **and per set of differences**: four
    // cartridges that carry the same map all say the same thing, and
    // repeating it four times buries the others'. If one decided differently
    // from the rest, its differences are different and its complaint comes
    // out anyway, with its name.
    let mut said = BTreeSet::new();
    for build in builds {
        let folder = build.join(kind.in_build());
        if !folder.is_dir() {
            continue;
        }
        let cartridge = rm2k_project::absolute(build)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        for name in toml_files(&folder)? {
            let path = folder.join(&name);
            let doc = read(&path)?;
            let which = key_of(&doc, kind, &path)?;
            if !have.contains(&which) {
                if cartridge == crate::PLAYABLE && !only_for_tests(build, kind, &which, tests)? {
                    // What the playable ROM converts **has** to be versioned:
                    // otherwise the game loses something somewhere and it is
                    // not written down. In a test cartridge, on the other
                    // hand, it is normal and nothing is said.
                    complaints.push(format!(
                        "{} {which} went into «{cartridge}», the playable ROM, and has no \
                         versioned patch: run `rm2k-snes-patches` on its build.",
                        kind.article()
                    ));
                } else {
                    own.entry(which).or_default().push(cartridge.clone());
                }
                continue;
            }
            let versioned_path = auto.join(kind.directory()).join(&name);
            let committed = auto.join(kind.directory()).join(kind.file_name(&which));
            let changes = diff(kind, &read(&committed)?, &doc);
            seen.insert(which.clone());
            if !changes.is_empty() && said.insert((which.clone(), changes.clone())) {
                complaints.push(format!(
                    "{} is stale (cartridge «{cartridge}» says so), and what changed in {} \
                     {which} is this:\n    {}\n  If the change is the one intended, run \
                     `rm2k-snes-patches` on the playable ROM's build and commit; if not, \
                     something moved what is seen.",
                    rm2k_project::relative(&versioned_path, base).display(),
                    kind.article(),
                    changes.join("\n    ")
                ));
            }
        }
    }
    for which in have.difference(&seen) {
        complaints.push(format!(
            "{} {which} has a versioned patch and none of the built cartridges converts it: \
             either the game stopped carrying it —and then the file is left over— or the \
             cartridge that has it is not built.",
            kind.article()
        ));
    }
    Ok(own)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_text_is_quoted_the_way_python_quotes_it() {
        assert_eq!(repr("hit"), "'hit'");
        assert_eq!(repr("it's"), "\"it's\"");
        assert_eq!(repr("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(repr("back\\slash\n"), "'back\\\\slash\\n'");
    }

    #[test]
    fn a_missing_value_is_none() {
        assert_eq!(shown(None), "None");
        assert_eq!(sides(None), "nothing");
        let pair = Value::Array(vec![Value::Integer(64), Value::Integer(49)]);
        assert_eq!(shown(Some(&pair)), "[64, 49]");
        assert_eq!(sides(Some(&pair)), "64x49");
    }
}
