//! The requests the executable takes and the answers it writes, as JSON.
//!
//! A colour is `[r, g, b]`. A colour with its pixels is `[r, g, b, pixels]`.
//! A tile is the list of the colours it draws with, in any order: the pixels
//! it has are already in the counts, and where each one is does not change
//! what is decided.

use crate::fail::{Bad, Result};
use crate::merge::{Merge, Merged};
use crate::pack::{Colors, Reduced};
use crate::{Color, USABLE_COLORS};
use serde_json::{json, Map, Value};

/// `{"counts": [[r, g, b, pixels], ...], "keep": N}`: merge until `keep`
/// colours are left.
pub struct MergeRequest {
    pub counts: Vec<(Color, u64)>,
    pub keep: usize,
}

/// `{"tiles": [[[r, g, b], ...], ...], "palettes": N, "per_palette": 15}`:
/// group the tiles' colours into `palettes` palettes, merging nothing.
pub struct PackRequest {
    pub tiles: Vec<Colors>,
    pub palettes: usize,
    pub per_palette: usize,
}

/// `{"counts": ..., "tiles": ..., "palettes": N, "per_palette": 15}`: merge
/// until the tiles fit in `palettes` palettes.
pub struct ReduceRequest {
    pub counts: Vec<(Color, u64)>,
    pub tiles: Vec<Colors>,
    pub palettes: usize,
    pub per_palette: usize,
}

pub fn merge_request(text: &str) -> Result<MergeRequest> {
    let fields = object(text, &["counts", "keep"])?;
    Ok(MergeRequest {
        counts: counts(field(&fields, "counts")?)?,
        keep: size(field(&fields, "keep")?, "keep")?,
    })
}

pub fn pack_request(text: &str) -> Result<PackRequest> {
    let fields = object(text, &["tiles", "palettes", "per_palette"])?;
    Ok(PackRequest {
        tiles: tiles(field(&fields, "tiles")?)?,
        palettes: size(field(&fields, "palettes")?, "palettes")?,
        per_palette: per_palette(&fields)?,
    })
}

pub fn reduce_request(text: &str) -> Result<ReduceRequest> {
    let fields = object(text, &["counts", "tiles", "palettes", "per_palette"])?;
    Ok(ReduceRequest {
        counts: counts(field(&fields, "counts")?)?,
        tiles: tiles(field(&fields, "tiles")?)?,
        palettes: size(field(&fields, "palettes")?, "palettes")?,
        per_palette: per_palette(&fields)?,
    })
}

/// `{"mapping": [[r, g, b], ...], "merges": [[victim, target, pixels], ...]}`:
/// the mapping in the order of the request's counts.
pub fn merged_answer(merged: &Merged) -> Value {
    json!({
        "mapping": merged.mapping.iter().map(|c| color_value(*c)).collect::<Vec<_>>(),
        "merges": merges_value(&merged.merges),
    })
}

/// `{"palettes": [[[r, g, b], ...], ...]}`, each palette's colours in order,
/// or `{"palettes": null}` if they do not fit.
pub fn packed_answer(palettes: Option<&[Colors]>) -> Value {
    json!({ "palettes": palettes.map(palettes_value) })
}

/// `{"mapping": ..., "merges": ..., "palettes": ...}`.
pub fn reduced_answer(reduced: &Reduced) -> Value {
    // The keys go in alphabetical order on purpose. Built alone, serde_json
    // sorts them; built in the workspace, another crate switches on
    // `preserve_order` and they come out as written here. In this order the
    // answer is the same bytes either way.
    json!({
        "mapping": reduced.mapping.iter().map(|c| color_value(*c)).collect::<Vec<_>>(),
        "merges": merges_value(&reduced.merges),
        "palettes": palettes_value(&reduced.palettes),
    })
}

fn color_value(c: Color) -> Value {
    json!([c[0], c[1], c[2]])
}

fn palettes_value(palettes: &[Colors]) -> Value {
    Value::Array(
        palettes
            .iter()
            .map(|p| Value::Array(p.iter().map(|c| color_value(*c)).collect()))
            .collect(),
    )
}

fn merges_value(merges: &[Merge]) -> Value {
    Value::Array(
        merges
            .iter()
            .map(|m| json!([color_value(m.victim), color_value(m.target), m.pixels]))
            .collect(),
    )
}

fn object(text: &str, known: &[&str]) -> Result<Map<String, Value>> {
    let value: Value = serde_json::from_str(text)
        .map_err(|e| Bad::usage(format!("the request is not JSON: {e}")))?;
    let Value::Object(fields) = value else {
        return Err(Bad::usage("the request is not a JSON object"));
    };
    if let Some(unknown) = fields.keys().find(|k| !known.contains(&k.as_str())) {
        return Err(Bad::usage(format!(
            "the request has \"{unknown}\", and knows only {}",
            known.join(", ")
        )));
    }
    Ok(fields)
}

fn field<'a>(fields: &'a Map<String, Value>, name: &str) -> Result<&'a Value> {
    fields
        .get(name)
        .ok_or_else(|| Bad::usage(format!("the request has no \"{name}\"")))
}

fn size(value: &Value, name: &str) -> Result<usize> {
    value
        .as_u64()
        .and_then(|n| usize::try_from(n).ok())
        .ok_or_else(|| Bad::usage(format!("\"{name}\" is not a whole number")))
}

fn per_palette(fields: &Map<String, Value>) -> Result<usize> {
    match fields.get("per_palette") {
        None => Ok(USABLE_COLORS),
        Some(value) => size(value, "per_palette"),
    }
}

fn channel(value: &Value) -> Option<u8> {
    value.as_u64().and_then(|n| u8::try_from(n).ok())
}

fn color(value: &Value) -> Result<Color> {
    match value.as_array().map(Vec::as_slice) {
        Some([r, g, b]) => match (channel(r), channel(g), channel(b)) {
            (Some(r), Some(g), Some(b)) => Ok([r, g, b]),
            _ => Err(Bad::usage(format!(
                "{value} is not a colour: channels go from 0 to 255"
            ))),
        },
        _ => Err(Bad::usage(format!("{value} is not a colour, [r, g, b]"))),
    }
}

fn counts(value: &Value) -> Result<Vec<(Color, u64)>> {
    let list = value
        .as_array()
        .ok_or_else(|| Bad::usage("\"counts\" is not a list"))?;
    list.iter()
        .map(|entry| match entry.as_array().map(Vec::as_slice) {
            Some([r, g, b, pixels]) => {
                let c = color(&json!([r, g, b]))?;
                let n = pixels.as_u64().ok_or_else(|| {
                    Bad::usage(format!("{entry}: the pixels are not a whole number"))
                })?;
                Ok((c, n))
            }
            _ => Err(Bad::usage(format!(
                "{entry} is not a count, [r, g, b, pixels]"
            ))),
        })
        .collect()
}

fn tiles(value: &Value) -> Result<Vec<Colors>> {
    let list = value
        .as_array()
        .ok_or_else(|| Bad::usage("\"tiles\" is not a list"))?;
    list.iter()
        .map(|tile| {
            tile.as_array()
                .ok_or_else(|| Bad::usage(format!("{tile} is not a tile, a list of colours")))?
                .iter()
                .map(color)
                .collect()
        })
        .collect()
}
