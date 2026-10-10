//! A project as the tools resolve it, as one JSON value: what
//! `rm2k-snes-project` prints.
//!
//! For whatever needs to know what the tools know about a game without being
//! one of them —a game's tests, in another language—. Answering from here
//! keeps one reader of the project file and one set of rules: a caller that
//! read the TOML on its own would be a second model of the same format.

use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};

use crate::{suite, Error, Project};

/// One object with three keys:
///
/// * `project`: where the game is and how it is laid out —its root, its
///   file, each `[paths]` entry resolved against the file, and the two
///   folders the tools look for inside the patches—;
/// * `suite`: where this suite's own files are —its `directory`, the one
///   that holds the tools; the `root` above it; and the `runtime`—, for the
///   checkout the binary was built from: see [`suite`];
/// * `settings`: the whole project file, keys in the order the file writes
///   them.
///
/// It checks what every tool checks —the file parses, `[paths]` declares
/// what it has to— and nothing a single tool asks of one setting: that a
/// setting fits in the ROM is said by the tool that puts it there.
pub fn resolved(project: &Project) -> Result<Value, Error> {
    let paths: [(&str, PathBuf); 8] = [
        ("directory", project.directory().to_path_buf()),
        ("file", project.file()),
        ("build", project.build()?),
        ("data", project.data()?),
        ("patches", project.patches()?),
        ("manual_patches", project.manual_patches()?),
        ("auto_patches", project.auto_patches()?),
        ("cases", project.cases()?),
    ];
    Ok(json!({
        "project": paths.iter().map(|(k, p)| (k.to_string(), path(p))).collect::<Map<_, _>>(),
        "suite": {
            "directory": path(suite::tools()),
            "root": path(suite::root()),
            "runtime": path(suite::runtime()),
        },
        "settings": table(project.settings()),
    }))
}

fn path(p: impl AsRef<Path>) -> Value {
    Value::String(p.as_ref().to_string_lossy().into_owned())
}

fn table(table: &toml::Table) -> Value {
    Value::Object(table.iter().map(|(k, v)| (k.clone(), to_json(v))).collect())
}

/// A TOML value as JSON. By hand and not through serde: a TOML date has no
/// JSON form, and serde would write it as an object with a private key. It
/// goes as the text the file wrote.
fn to_json(value: &toml::Value) -> Value {
    match value {
        toml::Value::String(s) => Value::String(s.clone()),
        toml::Value::Integer(i) => json!(i),
        toml::Value::Float(f) => json!(f),
        toml::Value::Boolean(b) => Value::Bool(*b),
        toml::Value::Datetime(d) => Value::String(d.to_string()),
        toml::Value::Array(items) => Value::Array(items.iter().map(to_json).collect()),
        toml::Value::Table(t) => table(t),
    }
}
