//! Reading what the request still carries as JSON: the geometry of the
//! screens and the battle, numbers and lists of numbers by name, which the
//! emission writes out by name. One that has another type is a request
//! this stage cannot use, and it says which.

use crate::fail::{Bad, Result};
use serde_json::Value;

pub fn int(value: &Value) -> Result<i64> {
    value
        .as_i64()
        .or_else(|| value.as_bool().map(i64::from))
        .ok_or_else(|| Bad::answer(format!("{value} is not a whole number")))
}

pub fn list(value: &Value) -> Result<&Vec<Value>> {
    value
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{} is not a list", short(value))))
}

pub fn ints(value: &Value) -> Result<Vec<i64>> {
    list(value)?.iter().map(int).collect()
}

pub fn text(value: &Value) -> Result<&str> {
    value
        .as_str()
        .ok_or_else(|| Bad::answer(format!("{} is not text", short(value))))
}

/// An object's entries in the order of their keys as text, for what
/// writes them out one after another.
///
/// Not the order the object came in: the converter links `serde_json` with
/// `preserve_order`, and cargo turns it on for this crate too there, so in
/// the converter an object keeps the order its stage inserted the keys in,
/// where this crate's own binary, reading the request from a file, saw them
/// sorted until 2026-11-27. The `.inc` had to come out the same from both,
/// and with the sort it still comes out as it did.
pub fn by_key(object: &serde_json::Map<String, Value>) -> Vec<(&String, &Value)> {
    let mut entries: Vec<_> = object.iter().collect();
    entries.sort_by(|a, b| a.0.cmp(b.0));
    entries
}

fn short(value: &Value) -> String {
    let text = value.to_string();
    if text.len() > 60 {
        format!(
            "{}…",
            &text[..text.char_indices().nth(60).map_or(text.len(), |c| c.0)]
        )
    } else {
        text
    }
}
