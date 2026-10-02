//! The project file's settings, as JSON: what goes into a request as the
//! game declared it.
//!
//! A missing key is an error that names it, never a default: a default
//! here would be some other game's value.

use crate::fail::{Result, Stop};
use rm2k_project::Project;
use serde_json::{Map, Value};

pub struct Settings<'a> {
    pub project: &'a Project,
}

fn to_json(value: &toml::Value) -> Value {
    match value {
        toml::Value::String(s) => Value::String(s.clone()),
        toml::Value::Integer(i) => Value::from(*i),
        toml::Value::Float(f) => serde_json::Number::from_f64(*f).map_or(Value::Null, Value::Number),
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

    pub fn string(&self, keys: &[&str]) -> Result<String> {
        Ok(self.project.string(keys)?.to_string())
    }

    /// A text that ends up in the ROM as is: printable ASCII without
    /// quotes, exactly `length` long or at most `max_length`.
    pub fn ascii(&self, keys: &[&str], length: Option<usize>, max_length: Option<usize>) -> Result<String> {
        self.project
            .ascii(keys, length, max_length)
            .map(str::to_string)
            .map_err(|e| Stop::new(e.0))
    }
}
