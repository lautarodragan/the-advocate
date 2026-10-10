//! Reading the answers other stages wrote, which come in the request as
//! they are: a field that is missing or has another type is a request this
//! stage cannot use, and it says which.

use crate::fail::{Bad, Result};
use crate::snes::Color;
use serde_json::Value;

/// `value[key]`, or why not.
pub fn at<'a>(value: &'a Value, key: &str) -> Result<&'a Value> {
    value
        .get(key)
        .ok_or_else(|| Bad::answer(format!("the request has no `{key}` where it should")))
}

pub fn int(value: &Value) -> Result<i64> {
    value
        .as_i64()
        .or_else(|| value.as_bool().map(i64::from))
        .ok_or_else(|| Bad::answer(format!("{value} is not a whole number")))
}

/// `value[key]` as a whole number.
pub fn int_at(value: &Value, key: &str) -> Result<i64> {
    int(at(value, key)?)
}

pub fn list(value: &Value) -> Result<&Vec<Value>> {
    value
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{} is not a list", short(value))))
}

pub fn list_at<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>> {
    list(at(value, key)?)
}

pub fn ints(value: &Value) -> Result<Vec<i64>> {
    list(value)?.iter().map(int).collect()
}

pub fn ints_at(value: &Value, key: &str) -> Result<Vec<i64>> {
    ints(at(value, key)?)
}

pub fn text(value: &Value) -> Result<&str> {
    value
        .as_str()
        .ok_or_else(|| Bad::answer(format!("{} is not text", short(value))))
}

pub fn text_at<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    text(at(value, key)?)
}

/// Hex text, as bytes.
pub fn bytes(value: &Value) -> Result<Vec<u8>> {
    crate::hex::decode(text(value)?)
}

pub fn bytes_at(value: &Value, key: &str) -> Result<Vec<u8>> {
    bytes(at(value, key)?)
}

pub fn color(value: &Value) -> Result<Color> {
    let c = ints(value)?;
    match c[..] {
        [r, g, b] => Ok([r as u8, g as u8, b as u8]),
        _ => Err(Bad::answer(format!("{} is not a colour", short(value)))),
    }
}

pub fn colors(value: &Value) -> Result<Vec<Color>> {
    list(value)?.iter().map(color).collect()
}

/// An 8x8 tile, as rows of indices.
pub fn tile(value: &Value) -> Result<Vec<Vec<u8>>> {
    list(value)?
        .iter()
        .map(|row| Ok(ints(row)?.into_iter().map(|v| v as u8).collect()))
        .collect()
}

pub fn tiles(value: &Value) -> Result<Vec<Vec<Vec<u8>>>> {
    list(value)?.iter().map(tile).collect()
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
