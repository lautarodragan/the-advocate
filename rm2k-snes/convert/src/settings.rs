//! The project file's settings, as JSON: what goes into a request as the
//! game declared it.
//!
//! A missing key is an error that names it, never a default: a default
//! here would be some other game's value.

use crate::fail::{Result, Stop};
use rm2k_project::Project;
use serde_json::{Map, Value};

/// A custom menu of the project: see [`Settings::menus`].
#[derive(Debug, Clone)]
pub struct CustomMenu {
    pub name: String,
    pub spec: Value,
}

impl CustomMenu {
    /// What the event compiler needs of it: the common event it replaces
    /// and the ones it runs before a page.
    pub fn hooks(&self) -> Value {
        let mut before = Vec::new();
        find_before(&self.spec, &mut before);
        before.sort();
        before.dedup();
        serde_json::json!({"replaces_common": self.spec.get("replaces_common"), "before": before})
    }

    /// The variables it reads, which the cartridge has to keep: the
    /// conditions', the tables' and counters', and each `\V[n]`.
    pub fn variables(&self) -> Vec<i64> {
        let mut out = Vec::new();
        find_variables(&self.spec, None, &mut out);
        out.sort();
        out.dedup();
        out
    }

    /// The switches its conditions ask for, `{ switch = n }`, which the
    /// ROM's switch table has to hold: see `switch_top` in the event
    /// compiler.
    pub fn switches(&self) -> Vec<i64> {
        fn find(v: &Value, out: &mut Vec<i64>) {
            match v {
                Value::Object(o) => {
                    for (k, x) in o {
                        if k == "switch" {
                            out.extend(x.as_i64());
                        }
                        find(x, out);
                    }
                }
                Value::Array(a) => a.iter().for_each(|x| find(x, out)),
                _ => {}
            }
        }
        let mut out = Vec::new();
        find(&self.spec, &mut out);
        out
    }
}

fn find_before(v: &Value, out: &mut Vec<i64>) {
    match v {
        Value::Object(o) => {
            for (k, x) in o {
                if k == "before" {
                    if let Some(n) = x.get("common").and_then(Value::as_i64) {
                        out.push(n);
                    }
                }
                find_before(x, out);
            }
        }
        Value::Array(a) => a.iter().for_each(|x| find_before(x, out)),
        _ => {}
    }
}

fn find_variables(v: &Value, key: Option<&str>, out: &mut Vec<i64>) {
    match v {
        Value::Object(o) => {
            for (k, x) in o {
                if k == "variable" {
                    if let Some(n) = x.as_i64() {
                        out.push(n);
                    }
                }
                find_variables(x, Some(k), out);
            }
        }
        Value::Array(a) => {
            // A table's rows are [name, variable, cap], a counter
            // [label, variable]; a cap "vN" is a variable too.
            if matches!(key, Some("rows") | Some("counters")) {
                for row in a {
                    if let Some(r) = row.as_array() {
                        if let Some(n) = r.get(1).and_then(Value::as_i64) {
                            out.push(n);
                        }
                        if let Some(n) = r
                            .get(2)
                            .and_then(Value::as_str)
                            .and_then(|s| s.strip_prefix('v'))
                            .and_then(|s| s.parse().ok())
                        {
                            out.push(n);
                        }
                    }
                }
            }
            a.iter().for_each(|x| find_variables(x, None, out));
        }
        Value::String(s) => {
            let mut rest = s.as_str();
            while let Some(at) = rest.find("\\V[").or_else(|| rest.find("\\v[")) {
                let after = &rest[at + 3..];
                if let Some(end) = after.find(']') {
                    if let Ok(n) = after[..end].parse() {
                        out.push(n);
                    }
                }
                rest = after;
            }
        }
        _ => {}
    }
}

pub struct Settings<'a> {
    pub project: &'a Project,
}

fn to_json(value: &toml::Value) -> Value {
    match value {
        toml::Value::String(s) => Value::String(s.clone()),
        toml::Value::Integer(i) => Value::from(*i),
        toml::Value::Float(f) => {
            serde_json::Number::from_f64(*f).map_or(Value::Null, Value::Number)
        }
        toml::Value::Boolean(b) => Value::Bool(*b),
        toml::Value::Datetime(d) => Value::String(d.to_string()),
        toml::Value::Array(a) => Value::Array(a.iter().map(to_json).collect()),
        toml::Value::Table(t) => {
            let mut out = Map::new();
            for (k, v) in t {
                out.insert(k.clone(), to_json(v));
            }
            Value::Object(out)
        }
    }
}

impl<'a> Settings<'a> {
    /// A list setting.
    pub fn list(&self, keys: &[&str]) -> Result<Vec<Value>> {
        Ok(self.project.list(keys)?.iter().map(to_json).collect())
    }

    /// A table setting, as an object in the file's order.
    pub fn table(&self, keys: &[&str]) -> Result<Value> {
        let t = self.project.table(keys)?;
        let mut out = Map::new();
        for (k, v) in t {
            out.insert(k.clone(), to_json(v));
        }
        Ok(Value::Object(out))
    }

    /// The custom menus the project declares in `[menus]`: each one's
    /// name, its file —relative to the project file— and that file's
    /// contents as JSON, in the order they are written, which is the order
    /// the cartridge numbers them. None if there is no `[menus]`: a game
    /// without custom menus says nothing.
    pub fn menus(&self) -> Result<Vec<CustomMenu>> {
        let Some(table) = self.project.settings().get("menus") else {
            return Ok(Vec::new());
        };
        let table = table
            .as_table()
            .ok_or_else(|| Stop::new("`[menus]` of the project file is not a table"))?;
        let mut out = Vec::new();
        for (name, file) in table {
            let file = file
                .as_str()
                .ok_or_else(|| Stop::new(format!("`menus.{name}` is not the path of a file")))?;
            let path = self.project.directory().join(file);
            let text = std::fs::read_to_string(&path)
                .map_err(|e| Stop::new(format!("menu {name:?}: {}: {e}", path.display())))?;
            let parsed: toml::Table = toml::from_str(&text)
                .map_err(|e| Stop::new(format!("menu {name:?}: {}: {e}", path.display())))?;
            let spec = to_json(&toml::Value::Table(parsed));
            out.push(CustomMenu {
                name: name.clone(),
                spec,
            });
        }
        Ok(out)
    }

    pub fn string(&self, keys: &[&str]) -> Result<String> {
        Ok(self.project.string(keys)?.to_string())
    }

    /// `[rom] msu`: `"optional"`, or `"required"` for a game whose ROM
    /// does not reach without the `.msu`. **Missing is `"optional"`**,
    /// against this module's rule, because it is a knob at rest: what
    /// every game is, and what each one should go back to.
    ///
    /// The converter does not decide it by itself when the ROM runs out,
    /// and that is on purpose: needing the MSU-1 changes what the player
    /// needs —a console or emulator that has it, and the `.msu` next to
    /// the ROM—, and a map more must not change that without anyone
    /// deciding it. A game that does not fit says so, as always.
    pub fn msu(&self) -> Result<&'static str> {
        if self.project.value(&["rom", "msu"]).is_err() {
            return Ok("optional");
        }
        match self.project.string(&["rom", "msu"])? {
            "optional" => Ok("optional"),
            "required" => Ok("required"),
            other => Err(Stop::new(format!(
                "`[rom] msu` is {other:?}, and it can be \"optional\" or \"required\""
            ))),
        }
    }

    /// A text that ends up in the ROM as is: printable ASCII without
    /// quotes, exactly `length` long or at most `max_length`.
    pub fn ascii(
        &self,
        keys: &[&str],
        length: Option<usize>,
        max_length: Option<usize>,
    ) -> Result<String> {
        self.project
            .ascii(keys, length, max_length)
            .map(str::to_string)
            .map_err(|e| Stop::new(e.0))
    }
}
